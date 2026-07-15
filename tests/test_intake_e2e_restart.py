# -*- coding: utf-8 -*-
"""
Smart Intake Engine, Faza 0 — end-to-end restart-safety test.

Founder's explicit Definition of Done for Faza 0: upload -> job written ->
worker claims -> worker crashes mid-processing -> restart -> reaper
requeues the stuck job -> a second worker completes it -> outbox is fully
dispatched -> audit trail is complete -> NOTHING is lost -> the successful
completion happens effectively-once (not duplicated) despite the crash.

This drives the REAL production code (shared.intake_queue, shared.
intake_worker.IntakeWorker, services.event_bus) against a minimal in-memory
fake of the Postgres RPC/table surface — not a reimplementation of the
logic under test. The one thing this CANNOT verify (honestly disclosed,
not glossed over): actual Postgres row-level locking (FOR UPDATE SKIP
LOCKED) and transaction atomicity are properties of the SQL in migration
073 itself, not of this Python fake — those are only verifiable against a
live Postgres instance once the founder runs the migration. What this test
DOES verify: the orchestration logic (worker + queue + event bus) reacts
correctly to a crash-mid-processing scenario and produces no duplicate or
lost terminal state.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Row(dict):
    """dict with attribute-style access is not needed — Supabase client
    returns plain dicts. Kept as a thin subclass only for readability at
    call sites (fake_db.jobs[id] is a _Row, i.e. a dict)."""


class FakeIntakeDB:
    """Minimal in-memory backing store implementing exactly the operations
    shared/intake_queue.py issues — enough to run the real orchestration
    code end-to-end. Mirrors migration 073's RPC semantics in Python
    (single-threaded, so no real lock contention — see module docstring)."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.audit: list[dict] = []
        self.events: list[dict] = []
        self.heartbeats: dict[str, dict] = {}

    # ── RPC simulation (mirrors migration 073's Postgres functions) ────────

    def enqueue_intake_job(self, p_source, p_content_sha256, p_storage_path, p_uploaded_by, p_kancelarija_id, p_idempotency_key):
        if p_idempotency_key:
            for job in self.jobs.values():
                if job.get("idempotency_key") == p_idempotency_key:
                    return job["id"]
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "id": job_id, "source": p_source, "content_sha256": p_content_sha256,
            "storage_path": p_storage_path, "status": "received",
            "uploaded_by": p_uploaded_by, "kancelarija_id": p_kancelarija_id,
            "idempotency_key": p_idempotency_key,
            "attempts": 0, "max_attempts": 5, "next_retry_at": None,
            "claimed_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None, "last_error": None,
        }
        self.audit.append({"intake_job_id": job_id, "event_type": "job_created", "actor": "system"})
        self.events.append({"id": str(uuid.uuid4()), "event_type": "DocumentJobEnqueued",
                             "user_id": p_uploaded_by, "predmet_id": None, "payload": {"intake_job_id": job_id},
                             "dispatched_at": None, "dispatch_attempts": 0, "created_at": datetime.now(timezone.utc).isoformat()})
        return job_id

    def claim_intake_job(self, p_from_status, p_to_status):
        candidates = [j for j in self.jobs.values() if j["status"] == p_from_status]
        if not candidates:
            return []
        job = sorted(candidates, key=lambda j: j["created_at"])[0]
        job["status"] = p_to_status
        job["claimed_at"] = datetime.now(timezone.utc).isoformat()
        return [dict(job)]

    def complete_intake_job(self, p_job_id):
        job = self.jobs[p_job_id]
        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.audit.append({"intake_job_id": p_job_id, "event_type": "job_completed", "actor": "system"})
        self.events.append({"id": str(uuid.uuid4()), "event_type": "DocumentJobCompleted",
                             "user_id": None, "predmet_id": None, "payload": {"intake_job_id": p_job_id},
                             "dispatched_at": None, "dispatch_attempts": 0, "created_at": datetime.now(timezone.utc).isoformat()})

    def fail_intake_job(self, p_job_id, p_error, p_new_attempts, p_max_attempts, p_next_retry_at):
        job = self.jobs[p_job_id]
        if p_new_attempts >= p_max_attempts:
            job["status"] = "failed"
            job["attempts"] = p_new_attempts
            job["last_error"] = p_error
            self.audit.append({"intake_job_id": p_job_id, "event_type": "job_dead_lettered", "actor": "system"})
            self.events.append({"id": str(uuid.uuid4()), "event_type": "DocumentJobFailed",
                                 "user_id": None, "predmet_id": None, "payload": {"intake_job_id": p_job_id},
                                 "dispatched_at": None, "dispatch_attempts": 0, "created_at": datetime.now(timezone.utc).isoformat()})
        else:
            job["status"] = "received"
            job["attempts"] = p_new_attempts
            job["next_retry_at"] = p_next_retry_at
            job["last_error"] = p_error
            job["claimed_at"] = None
            self.audit.append({"intake_job_id": p_job_id, "event_type": "job_retry_scheduled", "actor": "system"})

    # ── table() simulation (only the operations intake_queue.py issues) ────

    def select_stale_jobs(self, statuses, older_than_iso):
        return [
            {"id": j["id"], "attempts": j["attempts"], "max_attempts": j["max_attempts"]}
            for j in self.jobs.values()
            if j["status"] in statuses and j["claimed_at"] and j["claimed_at"] < older_than_iso
        ]

    def select_undispatched_events(self, limit=50):
        rows = [e for e in self.events if e["dispatched_at"] is None]
        return sorted(rows, key=lambda e: e["created_at"])[:limit]

    def mark_event_dispatched(self, event_id):
        for e in self.events:
            if e["id"] == event_id:
                e["dispatched_at"] = datetime.now(timezone.utc).isoformat()


def _wire_fake_supa(fake: FakeIntakeDB):
    """Builds a MagicMock-based fake Supabase client whose .rpc()/.table()
    calls route into `fake`'s methods — thin enough to stay honest about
    being a fake, complete enough to drive the real production code."""
    from unittest.mock import MagicMock

    supa = MagicMock()

    def _rpc(name, params):
        chain = MagicMock()
        if name == "enqueue_intake_job":
            data = fake.enqueue_intake_job(**params)
        elif name == "claim_intake_job":
            data = fake.claim_intake_job(**params)
        elif name == "complete_intake_job":
            fake.complete_intake_job(**params)
            data = None
        elif name == "fail_intake_job":
            fake.fail_intake_job(**params)
            data = None
        else:
            raise AssertionError(f"unexpected rpc: {name}")
        chain.execute = MagicMock(return_value=MagicMock(data=data))
        return chain
    supa.rpc = MagicMock(side_effect=_rpc)

    def _table(name):
        chain = MagicMock()
        state = {"filters": {}, "in_status": None, "lt_field": None, "lt_value": None}

        def _eq(field, value):
            state["filters"][field] = value
            return chain
        def _in_(field, values):
            state["in_status"] = values
            return chain
        def _lt(field, value):
            state["lt_value"] = value
            return chain
        def _select(*a, **k):
            return chain
        def _order(*a, **k):
            return chain
        def _limit(n):
            state["limit"] = n
            return chain
        def _is_(field, value):
            return chain
        def _insert(payload):
            if name == "intake_audit_log":
                fake.audit.append(payload)
            return chain
        def _upsert(payload, on_conflict=None):
            if name == "intake_worker_heartbeat":
                fake.heartbeats[payload["worker_id"]] = payload
            return chain
        def _update(payload):
            if name == "events" and "dispatched_at" in payload:
                # dispatch_pending_events updates one row by id via .eq("id", row_id)
                pass
            return chain

        chain.eq = MagicMock(side_effect=_eq)
        chain.in_ = MagicMock(side_effect=_in_)
        chain.lt = MagicMock(side_effect=_lt)
        chain.select = MagicMock(side_effect=_select)
        chain.order = MagicMock(side_effect=_order)
        chain.limit = MagicMock(side_effect=_limit)
        chain.is_ = MagicMock(side_effect=_is_)
        chain.insert = MagicMock(side_effect=_insert)
        chain.upsert = MagicMock(side_effect=_upsert)
        chain.update = MagicMock(side_effect=_update)

        def _execute():
            if name == "intake_jobs" and state["in_status"] is not None:
                data = fake.select_stale_jobs(state["in_status"], state["lt_value"])
            elif name == "events" and state.get("limit") is not None:
                data = fake.select_undispatched_events(state["limit"])
            elif name == "intake_jobs" and "id" in state["filters"]:
                job = fake.jobs.get(state["filters"]["id"])
                data = [job] if job else []
            elif name == "intake_worker_heartbeat":
                data = list(fake.heartbeats.values())
            elif name == "events" and "id" in state["filters"]:
                fake.mark_event_dispatched(state["filters"]["id"])
                data = []
            else:
                data = []
            return MagicMock(data=data)
        chain.execute = MagicMock(side_effect=_execute)
        return chain
    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_e2e_worker_crash_mid_processing_no_lost_events_effectively_once():
    from shared import intake_queue as iq
    from shared.intake_worker import IntakeWorker
    from services import event_bus as eb

    fake = FakeIntakeDB()
    supa = _wire_fake_supa(fake)

    with patch("shared.intake_queue._get_supa", return_value=supa), \
         patch("shared.deps._get_supa", return_value=supa):

        # 1. Upload — job written (real enqueue_job, real RPC path).
        job_id = await iq.enqueue_job(
            "dropzone", "sha-abc123", "u1/deadbeef", "user-1",
            idempotency_key="user-1:sha-abc123",
        )
        assert fake.jobs[job_id]["status"] == "received"
        assert len(fake.events) == 1  # DocumentJobEnqueued, undispatched

        # 2. Worker A claims it (real claim_next_job).
        worker_a = IntakeWorker(worker_id="worker-A", reap_every_n_ticks=1000)
        job = await iq.claim_next_job("received", "preprocessing")
        assert job["id"] == job_id
        assert fake.jobs[job_id]["status"] == "preprocessing"
        assert fake.jobs[job_id]["claimed_at"] is not None

        # 3. Worker A "crashes" — never calls mark_job_completed. Simulate
        #    time passing by backdating claimed_at past the staleness threshold.
        fake.jobs[job_id]["claimed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()

        # 4. Restart: reaper detects the stuck job and requeues it through
        #    the normal retry path (attempts 0 -> 1, well under max_attempts).
        reaped = await iq.reap_stale_jobs(stale_after_seconds=300)
        assert reaped == 1
        assert fake.jobs[job_id]["status"] == "received"
        assert fake.jobs[job_id]["attempts"] == 1
        assert fake.jobs[job_id]["claimed_at"] is None

        # Backdate next_retry_at so the retried job is immediately claimable
        # again in this test (real deployment would wait out the backoff).
        fake.jobs[job_id]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        # 5. Worker B (the restarted process) claims and completes it.
        worker_b = IntakeWorker(worker_id="worker-B", reap_every_n_ticks=1000)
        did_work = await worker_b._tick()
        assert did_work is True
        assert fake.jobs[job_id]["status"] == "completed"
        assert worker_b.jobs_processed == 1
        assert worker_b.jobs_failed == 0

        # 6. Durable dispatch loop processes the full outbox — nothing lost.
        result = await eb.dispatch_pending_events(batch_size=50)
        assert result["greske"] == 0

    # 7. Final assertions — the whole point of the scenario.
    undispatched = [e for e in fake.events if e["dispatched_at"] is None]
    assert undispatched == [], "no event should be left undispatched after the loop runs"

    completed_events = [e for e in fake.events if e["event_type"] == "DocumentJobCompleted"]
    assert len(completed_events) == 1, "completion must happen effectively-once despite the crash+restart+reclaim cycle"

    audit_types = [a["event_type"] for a in fake.audit]
    assert audit_types == ["job_created", "job_retry_scheduled", "job_completed"], \
        "audit trail must be complete and in order: created -> retried (after reap) -> completed"

    assert fake.jobs[job_id]["status"] == "completed"
