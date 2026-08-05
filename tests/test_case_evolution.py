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
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import Event, EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    pre-existing state of case_evolution_consequences before this call."""
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

            def _upsert(row, on_conflict=None):
                key = (row["event_id"], row["consequence_name"])
                existing_rows[key] = {**existing_rows.get(key, {}), **row}
                inserted_or_updated.append(("upsert", dict(row)))
                res = MagicMock()
                res.data = [row]
                return res
            t.upsert.side_effect = _upsert

            def _update_chain(payload):
                inner = MagicMock()
                def _eq1(col, val):
                    inner2 = MagicMock()
                    def _eq2(col2, val2):
                        key = (val, val2)
                        existing_rows[key] = {**existing_rows.get(key, {}), **payload}
                        inserted_or_updated.append(("update", key, dict(payload)))
                        leaf = MagicMock()
                        leaf.execute.return_value = MagicMock()
                        return leaf
                    inner2.eq.side_effect = _eq2
                    return inner2
                inner.eq.side_effect = _eq1
                return inner
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
