# -*- coding: utf-8 -*-
"""
Program Delta, Sprint 001 (2026-08-05) — "Canonical Case Evolution Engine".
Tests for services/case_evolution.py, the ONE canonical mechanism deciding
and executing what automatically follows a case-changing event: Case
Changed → Determine Consequences → Execute → Verify → Audit → Complete.

Mission's own required test scenarios, checked directly:
1. New document — every consequence occurs exactly once.
2. Crash after Genome, retry — no duplicate execution.
3. Crash after Timeline (the last consequence in this sprint's registry),
   retry — resumes correctly (a full no-op, since everything already done).
4. Two parallel/concurrent events — no cross-contamination between them.
5. Replay — the same event produces no new consequences.
6. Audit — every consequence for one event shares the same correlation_id.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import Event, EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _now_iso_for_tests() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_seconds_ago_for_tests(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _event(event_id="evt-1", predmet_id="pred-1", correlation_id="corr-1", dokumenti=None):
    return Event(
        type=EventType.DOCUMENT_ACCEPTED,
        user_id="user-1",
        predmet_id=predmet_id,
        payload={"dokumenti": dokumenti or ["tuzba.pdf"]},
        correlation_id=correlation_id,
        event_id=event_id,
    )


def _make_consequence_table(existing_rows=None):
    """existing_rows: dict[(event_id, consequence_name)] -> row dict, the
    pre-existing state of case_evolution_consequences before this call.

    Program Lambda, Certification 004 (2026-08-06): rewritten to model real
    Postgres/PostgREST semantics for _try_claim_consequence's own atomic
    claim (services/case_evolution.py) -- `upsert(..., ignore_duplicates=
    True)` must NOT insert (and must return empty `.data`) when the
    composite (event_id, consequence_name) key already exists, and a
    conditional `.eq("status", prior_status)` on `.update(...)` must only
    apply (and only return non-empty `.data`) when the row's CURRENT status
    actually matches that precondition -- exactly the row-level compare-
    and-swap behavior the real fix relies on for its own correctness."""
    existing_rows = dict(existing_rows or {})
    inserted_or_updated = []

    def _select_chain(event_id_holder):
        def _eq_event(col, val):
            inner = MagicMock()
            def _eq_name(col2, val2):
                leaf = MagicMock()
                row = existing_rows.get((val, val2))
                leaf.maybe_single.return_value.execute.return_value.data = row
                return leaf
            inner.eq.side_effect = _eq_name
            return inner
        return _eq_event

    def _table(name):
        t = MagicMock()
        if name == "case_evolution_consequences":
            t.select.return_value.eq.side_effect = _select_chain(None)

            def _upsert(row, on_conflict=None, ignore_duplicates=False):
                # supabase-py's own chain is .upsert(...).execute() -- must
                # return an intermediate node with its OWN .execute(), not
                # the result directly (an earlier version of this fix did
                # exactly that, making res.execute() hit a fresh,
                # always-truthy auto-mock instead of the configured result).
                node = MagicMock()

                def _execute():
                    key = (row["event_id"], row["consequence_name"])
                    res = MagicMock()
                    if ignore_duplicates and key in existing_rows:
                        res.data = []  # conflict -- real INSERT ... ON CONFLICT DO NOTHING inserts nothing
                        return res
                    existing_rows[key] = {**existing_rows.get(key, {}), **row}
                    inserted_or_updated.append(("upsert", dict(row)))
                    res.data = [row]
                    return res
                node.execute.side_effect = _execute
                return node
            t.upsert.side_effect = _upsert

            def _update_chain(payload):
                def _make_level(eq_filters: dict, lt_filters: dict):
                    node = MagicMock()

                    def _eq_next(col, val):
                        return _make_level({**eq_filters, col: val}, lt_filters)
                    node.eq.side_effect = _eq_next

                    def _lt_next(col, val):
                        return _make_level(eq_filters, {**lt_filters, col: val})
                    node.lt.side_effect = _lt_next

                    def _execute():
                        res = MagicMock()
                        key = (eq_filters.get("event_id"), eq_filters.get("consequence_name"))
                        current = existing_rows.get(key, {})
                        # event_id/consequence_name are always present in
                        # this table's own keying; an optional `status`
                        # eq-filter (compare-and-swap precondition) and/or
                        # `updated_at` lt-filter (staleness gate for the
                        # 'pending' reclaim path) are checked against the
                        # row's CURRENT stored state, not blindly applied
                        # -- real Postgres UPDATE...WHERE semantics.
                        if "status" in eq_filters and current.get("status") != eq_filters["status"]:
                            res.data = []
                            return res
                        if "updated_at" in lt_filters:
                            # Missing updated_at defaults to "now" (matches
                            # the real column's own DEFAULT now() on a
                            # freshly-inserted row) -- always fails a
                            # staleness check unless a test explicitly sets
                            # an old value to simulate an abandoned claim.
                            row_updated_at = current.get("updated_at") or _now_iso_for_tests()
                            if not (row_updated_at < lt_filters["updated_at"]):
                                res.data = []
                                return res
                        existing_rows[key] = {**current, **payload}
                        inserted_or_updated.append(("update", key, dict(payload)))
                        res.data = [existing_rows[key]]
                        return res
                    node.execute.side_effect = _execute
                    return node
                return _make_level({}, {})
            t.update.side_effect = _update_chain
        return t

    return _table, existing_rows, inserted_or_updated


@pytest.mark.anyio
async def test_missing_event_id_refuses_to_run():
    """No durable identity to key idempotency on -- must refuse, not
    silently proceed without a retry-safety guarantee."""
    from services.case_evolution import handle_case_changed
    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u", predmet_id="p", event_id=None)
    with pytest.raises(RuntimeError, match="event_id"):
        await handle_case_changed(event)


@pytest.mark.anyio
async def test_scenario1_new_document_every_consequence_runs_exactly_once():
    from services.case_evolution import handle_case_changed

    genome_calls = []
    timeline_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    async def _fake_timeline(event):
        timeline_calls.append(event.event_id)
        return "row-1"

    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution._consequence_genome_refresh", _fake_genome), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 __import__("services.case_evolution", fromlist=["ConsequenceDef"]).ConsequenceDef("genome_refresh", _fake_genome),
                 __import__("services.case_evolution", fromlist=["ConsequenceDef"]).ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_event())

    assert genome_calls == ["evt-1"]
    assert timeline_calls == ["evt-1"]
    assert rows[("evt-1", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-1", "timeline_entry")]["status"] == "completed"
    assert mock_log.await_count == 2  # one audit entry per consequence


@pytest.mark.anyio
async def test_scenario2_crash_after_genome_retry_no_duplicate():
    """Genome already completed from a prior (crashed) attempt; timeline
    never attempted. A retry must skip genome entirely and only run
    timeline -- genome's executor must be called ZERO additional times."""
    from services.case_evolution import handle_case_changed, ConsequenceDef

    genome_calls = []
    timeline_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    async def _fake_timeline(event):
        timeline_calls.append(event.event_id)
        return "row-1"

    _table, rows, _ = _make_consequence_table(existing_rows={
        ("evt-1", "genome_refresh"): {"status": "completed", "result_ref": "v2"},
    })
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 ConsequenceDef("genome_refresh", _fake_genome),
                 ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_event())

    assert genome_calls == []  # NOT re-executed
    assert timeline_calls == ["evt-1"]
    assert rows[("evt-1", "timeline_entry")]["status"] == "completed"
    assert mock_log.await_count == 1  # only the newly-completed consequence is audited


@pytest.mark.anyio
async def test_scenario3_crash_after_timeline_retry_resumes_as_full_noop():
    """Both consequences already completed (this sprint's registry has
    exactly 2, in order genome->timeline -- 'crash after timeline' means
    everything already succeeded). A retry must be a complete no-op:
    neither executor runs again."""
    from services.case_evolution import handle_case_changed, ConsequenceDef

    genome_calls = []
    timeline_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    async def _fake_timeline(event):
        timeline_calls.append(event.event_id)
        return "row-1"

    _table, rows, _ = _make_consequence_table(existing_rows={
        ("evt-1", "genome_refresh"): {"status": "completed", "result_ref": "v2"},
        ("evt-1", "timeline_entry"): {"status": "completed", "result_ref": "row-1"},
    })
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 ConsequenceDef("genome_refresh", _fake_genome),
                 ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_event())

    assert genome_calls == []
    assert timeline_calls == []
    assert mock_log.await_count == 0  # nothing NEW to audit


@pytest.mark.anyio
async def test_scenario4_two_parallel_events_no_cross_contamination():
    """Two DIFFERENT events (different event_id) for the same predmet_id,
    processed concurrently -- each must independently track and complete
    its own consequences; neither's row state leaks into the other's."""
    from services.case_evolution import handle_case_changed, ConsequenceDef

    calls = []

    async def _fake_genome(event):
        await asyncio.sleep(0)  # yield, encourage real interleaving
        calls.append(("genome", event.event_id))
        return "v2"

    async def _fake_timeline(event):
        await asyncio.sleep(0)
        calls.append(("timeline", event.event_id))
        return "row-1"

    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 ConsequenceDef("genome_refresh", _fake_genome),
                 ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await asyncio.gather(
            handle_case_changed(_event(event_id="evt-A")),
            handle_case_changed(_event(event_id="evt-B")),
        )

    assert ("genome", "evt-A") in calls and ("genome", "evt-B") in calls
    assert ("timeline", "evt-A") in calls and ("timeline", "evt-B") in calls
    assert rows[("evt-A", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-B", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-A", "timeline_entry")]["status"] == "completed"
    assert rows[("evt-B", "timeline_entry")]["status"] == "completed"


@pytest.mark.anyio
async def test_scenario5_replay_same_event_produces_no_new_consequences():
    from services.case_evolution import handle_case_changed, ConsequenceDef

    call_count = {"genome": 0, "timeline": 0}

    async def _fake_genome(event):
        call_count["genome"] += 1
        return "v2"

    async def _fake_timeline(event):
        call_count["timeline"] += 1
        return "row-1"

    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 ConsequenceDef("genome_refresh", _fake_genome),
                 ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        event = _event()
        await handle_case_changed(event)   # first run: both execute
        await handle_case_changed(event)   # replay: same event, same object

    assert call_count == {"genome": 1, "timeline": 1}


@pytest.mark.anyio
async def test_scenario6_every_consequence_shares_the_same_correlation_id():
    from services.case_evolution import handle_case_changed, ConsequenceDef

    async def _fake_genome(event):
        return "v2"

    async def _fake_timeline(event):
        return "row-1"

    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [
                 ConsequenceDef("genome_refresh", _fake_genome),
                 ConsequenceDef("timeline_entry", _fake_timeline),
             ]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_event(correlation_id="corr-XYZ"))

    assert mock_log.await_count == 2
    correlation_ids = {c.kwargs.get("correlation_id") for c in mock_log.await_args_list}
    assert correlation_ids == {"corr-XYZ"}


@pytest.mark.anyio
async def test_a_failed_consequence_is_marked_failed_and_propagates():
    """A failing executor must mark the consequence 'failed' (not silently
    'completed') and re-raise so the Event Bus's own retry/dead-letter
    mechanism (dispatch_pending_events) takes over."""
    from services.case_evolution import handle_case_changed, ConsequenceDef

    async def _failing_genome(event):
        raise RuntimeError("genome boom")

    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [ConsequenceDef("genome_refresh", _failing_genome)]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="genome boom"):
            await handle_case_changed(_event())

    assert rows[("evt-1", "genome_refresh")]["status"] == "failed"


@pytest.mark.anyio
async def test_genome_refresh_executor_verifies_verzija_actually_changed():
    """The genome_refresh executor must not trust _run_genome_background's
    own silent-swallow behavior -- it verifies verzija actually incremented,
    and raises if not (simulating a Genome-internal failure that was
    swallowed by Genome's own outer try/except, unchanged/untouched by this
    sprint)."""
    from services.case_evolution import _consequence_genome_refresh

    mock_supa = MagicMock()
    # Both before and after reads return the SAME verzija -- simulates a
    # genome refresh that silently failed internally.
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "case_dna": {"verzija": 3},
    }

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="verification failed"):
            await _consequence_genome_refresh(_event())


@pytest.mark.anyio
async def test_genome_refresh_executor_succeeds_when_verzija_increments():
    from services.case_evolution import _consequence_genome_refresh

    call_state = {"n": 0}
    mock_supa = MagicMock()

    def _fake_execute():
        call_state["n"] += 1
        res = MagicMock()
        res.data = {"case_dna": {"verzija": 3 if call_state["n"] == 1 else 4}}
        return res
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = _fake_execute

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()):
        result = await _consequence_genome_refresh(_event())

    assert result == "4"


# ═══════════════════════════════════════════════════════════════════════════
# Program Lambda, Certification 004 -- _try_claim_consequence's own atomic
# claim (closes LAMBDA003-EVT-001, Certification 003's own TOCTOU finding,
# given a broader confirmed real-world blast radius by this sprint's
# Distributed Systems Engineer fork: 5 of 9 consequence executors would
# have produced a visible duplicate row under the old read-then-write race).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_try_claim_consequence_fresh_key_wins():
    from services.case_evolution import _try_claim_consequence
    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        won = await _try_claim_consequence("evt-x", "genome_refresh")

    assert won is True
    assert rows[("evt-x", "genome_refresh")]["status"] == "pending"


@pytest.mark.anyio
async def test_try_claim_consequence_second_attempt_on_still_pending_row_loses():
    """The exact race LAMBDA003-EVT-001 named: a second caller attempting
    to claim the SAME (event_id, consequence_name) while the FIRST claim's
    own row is still 'pending' (not yet completed or failed) must NOT also
    win -- the old read-then-write upsert let this happen (both calls
    would see 'not completed' on read, both would upsert to 'pending',
    both would proceed to execute)."""
    from services.case_evolution import _try_claim_consequence
    _table, rows, _ = _make_consequence_table()
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        first = await _try_claim_consequence("evt-x", "timeline_entry")
        second = await _try_claim_consequence("evt-x", "timeline_entry")

    assert first is True
    assert second is False, "a second claim attempt on a still-pending row must not also win"


@pytest.mark.anyio
async def test_try_claim_consequence_reclaims_a_failed_row():
    """A legitimate retry after a prior failure must still be able to
    reclaim and re-execute -- this is NOT the race case, it's the
    crash/failure-recovery guarantee the whole mechanism exists for."""
    from services.case_evolution import _try_claim_consequence
    _table, rows, _ = _make_consequence_table(
        existing_rows={("evt-x", "conflict_check"): {
            "event_id": "evt-x", "consequence_name": "conflict_check", "status": "failed", "error": "boom",
        }}
    )
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        won = await _try_claim_consequence("evt-x", "conflict_check")

    assert won is True
    assert rows[("evt-x", "conflict_check")]["status"] == "pending"


@pytest.mark.anyio
async def test_try_claim_consequence_never_reclaims_a_completed_row():
    """No regression to the core retry-safe guarantee: a genuinely
    completed consequence must never be reclaimed/re-executed."""
    from services.case_evolution import _try_claim_consequence
    _table, rows, _ = _make_consequence_table(
        existing_rows={("evt-x", "genome_refresh"): {
            "event_id": "evt-x", "consequence_name": "genome_refresh", "status": "completed", "result_ref": "v4",
        }}
    )
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        won = await _try_claim_consequence("evt-x", "genome_refresh")

    assert won is False
    assert rows[("evt-x", "genome_refresh")]["status"] == "completed"


@pytest.mark.anyio
async def test_try_claim_consequence_reclaims_a_stale_pending_row():
    """Crash-recovery path: a consequence claimed by a worker that then
    crashed (never reached 'completed' or 'failed') must eventually be
    reclaimable, once the claim is old enough to be considered abandoned
    -- otherwise it would be stuck at 'pending' forever."""
    from services.case_evolution import _try_claim_consequence, _CONSEQUENCE_STALE_PENDING_SECONDS
    old_ts = _iso_seconds_ago_for_tests(_CONSEQUENCE_STALE_PENDING_SECONDS + 60)
    _table, rows, _ = _make_consequence_table(
        existing_rows={("evt-x", "timeline_entry"): {
            "event_id": "evt-x", "consequence_name": "timeline_entry", "status": "pending", "updated_at": old_ts,
        }}
    )
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        won = await _try_claim_consequence("evt-x", "timeline_entry")

    assert won is True, "a genuinely stale pending claim must eventually be reclaimable"


@pytest.mark.anyio
async def test_try_claim_consequence_does_not_reclaim_a_fresh_pending_row():
    """No regression / restates the race-closing test above with an
    explicit, recent timestamp: a claim made moments ago must NOT be
    reclaimable by a concurrent second caller."""
    from services.case_evolution import _try_claim_consequence
    recent_ts = _now_iso_for_tests()
    _table, rows, _ = _make_consequence_table(
        existing_rows={("evt-x", "timeline_entry"): {
            "event_id": "evt-x", "consequence_name": "timeline_entry", "status": "pending", "updated_at": recent_ts,
        }}
    )
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa):
        won = await _try_claim_consequence("evt-x", "timeline_entry")

    assert won is False


# ═══════════════════════════════════════════════════════════════════════════
# Program Lambda, Certification 005 (2026-08-07) -- handle_case_changed's own
# claim-failure branch must distinguish "genuinely completed" (silent skip,
# unchanged) from "claimed but not yet stale enough to reclaim" (raise, so
# the OUTER Event Bus dispatch does NOT mark the event dispatched, keeping it
# eligible for retry/dead-letter instead of a silent, permanent loss). Closes
# the cross-layer staleness mismatch a Chaos Engineer fork found between
# event_bus.py's own outer claim_pending_events (was 30s, now 120s) and this
# module's own _CONSEQUENCE_STALE_PENDING_SECONDS (300s) -- a worker crash
# landing in that gap used to strand a consequence at 'pending' forever with
# zero trace anywhere.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_claim_failure_on_fresh_pending_row_raises_instead_of_silently_skipping():
    """The CRITICAL bug this sprint closes: a consequence stuck 'pending'
    from another (possibly crashed) claim, too fresh to be reclaimed as
    stale, must NOT be silently skipped -- skipping it here means the outer
    Event Bus marks the event dispatched and NOTHING ever revisits this
    consequence again. It must raise so the event stays retry-eligible."""
    from services.case_evolution import handle_case_changed, ConsequenceDef, ConsequenceClaimPending

    genome_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    recent_ts = _now_iso_for_tests()
    _table, rows, _ = _make_consequence_table(existing_rows={
        ("evt-1", "genome_refresh"): {
            "event_id": "evt-1", "consequence_name": "genome_refresh",
            "status": "pending", "updated_at": recent_ts,
        },
    })
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [ConsequenceDef("genome_refresh", _fake_genome)]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        # Must be the DISTINCT ConsequenceClaimPending type, not a bare
        # RuntimeError -- event_bus.py's own dispatch loop isinstance-checks
        # for exactly this type to decide whether to fast-clear claimed_at
        # (see that exception's own docstring for why this distinction is
        # load-bearing, not cosmetic).
        with pytest.raises(ConsequenceClaimPending, match="claimed but not completed"):
            await handle_case_changed(_event())

    assert genome_calls == [], "must not execute -- another claim may still be live"
    assert rows[("evt-1", "genome_refresh")]["status"] == "pending", "must not be silently marked done"


@pytest.mark.anyio
async def test_claim_failure_on_genuinely_completed_row_still_silently_skips():
    """No regression: the ordinary retry-safe skip path (Scenario 2/3/5's
    own guarantee) must still work exactly as before when the row really is
    'completed' -- this must NOT raise."""
    from services.case_evolution import handle_case_changed, ConsequenceDef

    genome_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    _table, rows, _ = _make_consequence_table(existing_rows={
        ("evt-1", "genome_refresh"): {
            "event_id": "evt-1", "consequence_name": "genome_refresh",
            "status": "completed", "result_ref": "v2",
        },
    })
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [ConsequenceDef("genome_refresh", _fake_genome)]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event())  # must NOT raise

    assert genome_calls == []


@pytest.mark.anyio
async def test_claim_failure_on_stale_pending_row_reclaims_and_executes():
    """The other half of the fix's own correctness: a GENUINELY stale
    'pending' row must still be reclaimable and executed -- this fix must
    not turn the crash-recovery path itself into a permanent raise loop."""
    from services.case_evolution import handle_case_changed, ConsequenceDef, _CONSEQUENCE_STALE_PENDING_SECONDS

    genome_calls = []

    async def _fake_genome(event):
        genome_calls.append(event.event_id)
        return "v2"

    old_ts = _iso_seconds_ago_for_tests(_CONSEQUENCE_STALE_PENDING_SECONDS + 60)
    _table, rows, _ = _make_consequence_table(existing_rows={
        ("evt-1", "genome_refresh"): {
            "event_id": "evt-1", "consequence_name": "genome_refresh",
            "status": "pending", "updated_at": old_ts,
        },
    })
    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=mock_supa), \
         patch("services.case_evolution.CONSEQUENCE_REGISTRY", {
             EventType.DOCUMENT_ACCEPTED: [ConsequenceDef("genome_refresh", _fake_genome)]
         }), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event())  # must NOT raise -- reclaims and runs

    assert genome_calls == ["evt-1"]
    assert rows[("evt-1", "genome_refresh")]["status"] == "completed"
