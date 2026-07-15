# -*- coding: utf-8 -*-
"""
Tests for Smart Intake Engine Faza 0 (docs/adr/, migracija 073):
shared/intake_queue.py (Postgres-backed job queue, ADR-0002) and
services/event_bus.py's dispatch_pending_events (durable outbox, ADR-0001).

Faza 0 namerno ne menja AI ponašanje — ovi testovi pokrivaju samo job
lifecycle (enqueue/claim/complete/retry/dead-letter) i durable dispatch,
ne klasifikaciju/ekstrakciju (Faza 1).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit", "is_", "in_", "lt", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# shared/intake_queue.py — enqueue_job
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_enqueue_job_calls_rpc_with_correct_params():
    from shared import intake_queue as iq

    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain("job-123"))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        job_id = await iq.enqueue_job(
            "dropzone", "sha256abc", "predmet/x/doc.pdf", "user-1",
            kancelarija_id="kanc-1", idempotency_key="idem-1",
        )

    assert job_id == "job-123"
    supa.rpc.assert_called_once_with("enqueue_intake_job", {
        "p_source": "dropzone",
        "p_content_sha256": "sha256abc",
        "p_storage_path": "predmet/x/doc.pdf",
        "p_uploaded_by": "user-1",
        "p_kancelarija_id": "kanc-1",
        "p_idempotency_key": "idem-1",
    })


@pytest.mark.anyio
async def test_enqueue_job_rejects_invalid_source():
    from shared import intake_queue as iq
    with pytest.raises(ValueError):
        await iq.enqueue_job("carrier_pigeon", "sha", "path", "user-1")


@pytest.mark.anyio
async def test_enqueue_job_raises_if_rpc_returns_no_id():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain(None))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        with pytest.raises(RuntimeError):
            await iq.enqueue_job("dropzone", "sha", "path", "user-1")


# ═══════════════════════════════════════════════════════════════════════════
# shared/intake_queue.py — claim_next_job
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_claim_next_job_returns_row():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain([{"id": "job-1", "status": "preprocessing"}]))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        job = await iq.claim_next_job("received", "preprocessing")
    assert job["id"] == "job-1"
    supa.rpc.assert_called_once_with("claim_intake_job", {"p_from_status": "received", "p_to_status": "preprocessing"})


@pytest.mark.anyio
async def test_claim_next_job_returns_none_when_empty():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain([]))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        job = await iq.claim_next_job("received", "preprocessing")
    assert job is None


@pytest.mark.anyio
async def test_claim_next_job_rejects_invalid_status():
    from shared import intake_queue as iq
    with pytest.raises(ValueError):
        await iq.claim_next_job("received", "teleported")


# ═══════════════════════════════════════════════════════════════════════════
# shared/intake_queue.py — completion / retry / dead-letter
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_mark_job_completed_calls_atomic_rpc():
    from shared import intake_queue as iq

    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain(None))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.mark_job_completed("job-1")

    supa.rpc.assert_called_once_with("complete_intake_job", {"p_job_id": "job-1"})


@pytest.mark.anyio
async def test_mark_job_failed_schedules_retry_below_max_attempts():
    from shared import intake_queue as iq

    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain(None))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.mark_job_failed("job-1", "OCR timeout", attempts=1, max_attempts=5)

    supa.rpc.assert_called_once()
    call_name, call_args = supa.rpc.call_args[0]
    assert call_name == "fail_intake_job"
    assert call_args["p_job_id"] == "job-1"
    assert call_args["p_new_attempts"] == 2
    assert call_args["p_max_attempts"] == 5
    assert call_args["p_next_retry_at"] is not None
    assert call_args["p_error"] == "OCR timeout"


@pytest.mark.anyio
async def test_mark_job_failed_dead_letters_at_max_attempts():
    from shared import intake_queue as iq

    supa = MagicMock()
    supa.rpc = MagicMock(return_value=_make_chain(None))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.mark_job_failed("job-1", "OCR timeout", attempts=4, max_attempts=5)

    call_name, call_args = supa.rpc.call_args[0]
    assert call_name == "fail_intake_job"
    assert call_args["p_new_attempts"] == 5
    assert call_args["p_next_retry_at"] is None


@pytest.mark.anyio
async def test_write_audit_inserts_row():
    from shared import intake_queue as iq
    supa = MagicMock()
    chain = _make_chain([{"id": "audit-1"}])
    supa.table = MagicMock(return_value=chain)
    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.write_audit("job-1", "job_created", "system", after={"status": "received"})
    chain.insert.assert_called_once()
    insert_payload = chain.insert.call_args[0][0]
    assert insert_payload["intake_job_id"] == "job-1"
    assert insert_payload["event_type"] == "job_created"
    assert insert_payload["actor"] == "system"


@pytest.mark.anyio
async def test_write_audit_swallows_errors():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.write_audit("job-1", "job_created", "system")  # must not raise


# ═══════════════════════════════════════════════════════════════════════════
# shared/intake_queue.py — reaper (restart-safety)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reap_stale_jobs_requeues_stuck_job():
    from shared import intake_queue as iq

    stale_row = {"id": "job-stuck", "attempts": 0, "max_attempts": 5}
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([stale_row]))
    supa.rpc = MagicMock(return_value=_make_chain(None))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        reaped = await iq.reap_stale_jobs(stale_after_seconds=300)

    assert reaped == 1
    # reap_stale_jobs delegates to mark_job_failed -> fail_intake_job RPC
    supa.rpc.assert_called_once()
    call_name, call_args = supa.rpc.call_args[0]
    assert call_name == "fail_intake_job"
    assert call_args["p_job_id"] == "job-stuck"


@pytest.mark.anyio
async def test_reap_stale_jobs_noop_when_nothing_stuck():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([]))
    supa.rpc = MagicMock(return_value=_make_chain(None))

    with patch("shared.intake_queue._get_supa", return_value=supa):
        reaped = await iq.reap_stale_jobs()

    assert reaped == 0
    supa.rpc.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# shared/intake_queue.py — metrics + heartbeat (operational observability)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_queue_metrics_returns_view_row():
    from shared import intake_queue as iq
    metrics_row = {"queue_depth": 3, "failed_count": 1, "retrying_count": 0}
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([metrics_row]))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        metrics = await iq.get_queue_metrics()
    assert metrics["queue_depth"] == 3


@pytest.mark.anyio
async def test_get_outbox_metrics_returns_view_row():
    from shared import intake_queue as iq
    metrics_row = {"undispatched_backlog": 2}
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([metrics_row]))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        metrics = await iq.get_outbox_metrics()
    assert metrics["undispatched_backlog"] == 2


@pytest.mark.anyio
async def test_record_heartbeat_upserts():
    from shared import intake_queue as iq
    supa = MagicMock()
    chain = _make_chain(None)
    supa.table = MagicMock(return_value=chain)
    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.record_heartbeat("worker-1", jobs_processed=10, jobs_failed=1)
    chain.upsert.assert_called_once()
    payload = chain.upsert.call_args[0][0]
    assert payload["worker_id"] == "worker-1"
    assert payload["jobs_processed"] == 10


@pytest.mark.anyio
async def test_record_heartbeat_swallows_errors():
    from shared import intake_queue as iq
    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        await iq.record_heartbeat("worker-1", 0, 0)  # must not raise


@pytest.mark.anyio
async def test_get_worker_heartbeats_returns_rows():
    from shared import intake_queue as iq
    rows = [{"worker_id": "w1"}, {"worker_id": "w2"}]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))
    with patch("shared.intake_queue._get_supa", return_value=supa):
        result = await iq.get_worker_heartbeats()
    assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════
# services/event_bus.py — dispatch_pending_events (durable outbox)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dispatch_pending_events_calls_handler_and_marks_dispatched():
    from services import event_bus as eb

    row = {"id": "evt-1", "event_type": "predmet_kreiran", "user_id": "u-1",
           "predmet_id": "p-1", "payload": {}, "dispatch_attempts": 0}

    marked = []
    def _table(name):
        chain = _make_chain([row] if name == "events" else [])
        orig_update = chain.update
        def _capture(payload):
            marked.append(payload)
            return chain
        chain.update = MagicMock(side_effect=_capture)
        return chain
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    fake_handler = AsyncMock()
    with patch("shared.deps._get_supa", return_value=supa), \
         patch.object(eb.bus, "_handlers", {eb.EventType.PREDMET_KREIRAN: [fake_handler]}):
        result = await eb.dispatch_pending_events()

    assert result["dispecovano"] == 1
    fake_handler.assert_awaited_once()
    assert any("dispatched_at" in m for m in marked)


@pytest.mark.anyio
async def test_dispatch_pending_events_handles_unknown_event_type():
    from services import event_bus as eb

    row = {"id": "evt-2", "event_type": "SomeFutureEventNotYetDefined", "user_id": "u-1",
           "predmet_id": None, "payload": {}, "dispatch_attempts": 0}

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([row]))

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.dispatch_pending_events()

    assert result["nepoznat_tip"] == 1
    assert result["dispecovano"] == 0


@pytest.mark.anyio
async def test_dispatch_pending_events_records_error_without_crashing_batch():
    from services import event_bus as eb

    row = {"id": "evt-3", "event_type": "predmet_kreiran", "user_id": "u-1",
           "predmet_id": "p-1", "payload": {}, "dispatch_attempts": 0}

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([row]))

    async def _boom(event):
        raise RuntimeError("handler exploded")

    with patch("shared.deps._get_supa", return_value=supa), \
         patch.object(eb.bus, "publish_async", side_effect=_boom):
        result = await eb.dispatch_pending_events()

    assert result["greske"] == 1
    assert result["dispecovano"] == 0


@pytest.mark.anyio
async def test_dispatch_pending_events_empty_batch_is_noop():
    from services import event_bus as eb
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([]))
    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.dispatch_pending_events()
    assert result == {"obradjeno": 0, "dispecovano": 0, "nepoznat_tip": 0, "greske": 0}
