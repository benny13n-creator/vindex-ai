# -*- coding: utf-8 -*-
"""
Program Delta, Sprint 004 (2026-08-06) — "Orchestration Certification: Final
Architectural Certification of the Case Evolution Engine". Forensic
verification, not development — this file exists to try to BREAK the
architecture, not to prove it works.

Sprints 001-003's own tests all construct an `Event(...)` object directly
and call `handle_case_changed(event)` directly — none of them ever proved
the REAL chain: a raw row in the `events` table, picked up by the REAL
`dispatch_pending_events()`, parsed into an `Event`, dispatched through
`bus.publish_async()`, reaching `handle_case_changed()`. This file closes
that gap first (Phase 4's own core requirement), then covers the
architectural-invariant and repo-wide-bypass proofs Phase 5/6 require.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import EventType, bus


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_full_chain_supa(existing_consequence_rows=None, verzija_start=3):
    """Combines an 'events' outbox table (for claim_pending_events'
    fallback plain-select path) with case_evolution_consequences and
    predmeti (genome verzija) and predmet_hronologija (timeline) -- enough
    to drive a REAL dispatch_pending_events() call end to end for
    DOCUMENT_ACCEPTED."""
    existing_rows = dict(existing_consequence_rows or {})
    verzija_state = {"n": verzija_start}
    dispatched_ids = set()

    events_rows = [{
        "id": "evt-real-1", "event_type": "DocumentAccepted", "user_id": "u1",
        "predmet_id": "pred-1", "payload": {"dokumenti": ["tuzba.pdf"]},
        "correlation_id": "corr-real-1", "dispatch_attempts": 0,
    }]

    def _events_table():
        t = MagicMock()
        def _select_execute():
            res = MagicMock()
            res.data = [r for r in events_rows if r["id"] not in dispatched_ids]
            return res
        chain = t.select.return_value.is_.return_value.order.return_value.limit.return_value
        chain.execute.side_effect = _select_execute

        def _update_chain(payload):
            inner = MagicMock()
            def _eq(col, val):
                if "dispatched_at" in payload:
                    dispatched_ids.add(val)
                leaf = MagicMock(); leaf.execute.return_value = MagicMock()
                return leaf
            inner.eq.side_effect = _eq
            return inner
        t.update.side_effect = _update_chain
        return t

    def _cec_table():
        t = MagicMock()
        def _select_eq(col, val):
            inner = MagicMock()
            def _eq_name(col2, val2):
                leaf = MagicMock()
                leaf.maybe_single.return_value.execute.return_value.data = existing_rows.get((val, val2))
                return leaf
            inner.eq.side_effect = _eq_name
            return inner
        t.select.return_value.eq.side_effect = _select_eq
        def _upsert(row, on_conflict=None):
            key = (row["event_id"], row["consequence_name"])
            existing_rows[key] = {**existing_rows.get(key, {}), **row}
            res = MagicMock(); res.data = [row]
            return res
        t.upsert.side_effect = _upsert
        def _update_chain(payload):
            inner = MagicMock()
            def _eq1(col, val):
                inner2 = MagicMock()
                def _eq2(col2, val2):
                    key = (val, val2)
                    existing_rows[key] = {**existing_rows.get(key, {}), **payload}
                    leaf = MagicMock(); leaf.execute.return_value = MagicMock()
                    return leaf
                inner2.eq.side_effect = _eq2
                return inner2
            inner.eq.side_effect = _eq1
            return inner
        t.update.side_effect = _update_chain
        return t

    def _predmeti_table():
        t = MagicMock()
        def _execute():
            verzija_state["n"] += 1
            res = MagicMock(); res.data = {"case_dna": {"verzija": verzija_state["n"]}}
            return res
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = _execute
        return t

    def _hronologija_table():
        t = MagicMock()
        t.insert.return_value.execute.return_value.data = [{"id": "hron-real-1"}]
        return t

    def _table(name):
        if name == "events":
            return _events_table()
        if name == "case_evolution_consequences":
            return _cec_table()
        if name == "predmeti":
            return _predmeti_table()
        if name == "predmet_hronologija":
            return _hronologija_table()
        t = MagicMock()
        t.insert.return_value.execute.return_value.data = [{"id": "row-1"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    # No claim_pending_events RPC deployed in this test env -- exercise the
    # documented plain-select fallback path (dispatch_pending_events' own
    # narrow _is_missing_function_error check).
    supa.rpc = MagicMock(side_effect=Exception("PGRST202: Could not find the function public.claim_pending_events"))
    return supa, existing_rows, dispatched_ids


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 core proof — raw events row -> real dispatch -> completed
# consequence, replay, crash-recovery, correlation continuity
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_full_chain_raw_event_row_through_real_dispatch_to_completed_consequence():
    """The gap Sprints 001-003 never closed: does a REAL row in the events
    table, run through the REAL dispatch_pending_events(), actually reach
    handle_case_changed() and complete both DOCUMENT_ACCEPTED consequences?
    No test before this one ever proved this — every prior test hand-built
    an Event() and called handle_case_changed() directly."""
    from services.event_bus import dispatch_pending_events

    supa, rows, dispatched = _make_full_chain_supa()

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await dispatch_pending_events()

    assert result["dispecovano"] == 1
    assert "evt-real-1" in dispatched
    assert rows[("evt-real-1", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-real-1", "timeline_entry")]["status"] == "completed"
    assert rows[("evt-real-1", "refresh_case_actions")]["status"] == "completed"
    # Program Omega Sprint 003 appended refresh_case_actions as a 3rd
    # DOCUMENT_ACCEPTED consequence: one case_evolution_consequence_completed
    # row per consequence (3) + refresh_case_actions's own domain-specific
    # case_action_refreshed row = 4 total.
    assert mock_log.await_count == 4


@pytest.mark.anyio
async def test_full_chain_replay_same_row_produces_no_duplicate_work():
    """A row already marked dispatched (simulating a replay -- the SAME
    event_id reprocessed, e.g. an operator manually re-queuing it, or a
    duplicate insert) must not re-execute already-completed consequences."""
    from services.case_evolution import handle_case_changed
    from services.event_bus import Event

    supa, rows, _ = _make_full_chain_supa(existing_consequence_rows={
        ("evt-real-1", "genome_refresh"): {"status": "completed", "result_ref": "9"},
        ("evt-real-1", "timeline_entry"): {"status": "completed", "result_ref": "hron-real-1"},
        ("evt-real-1", "refresh_case_actions"): {"status": "completed", "result_ref": "created=0 updated=0 closed=0"},
    })
    genome_bg = AsyncMock()

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={"dokumenti": ["tuzba.pdf"]}, correlation_id="corr-real-1", event_id="evt-real-1")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(event)   # replay
        await handle_case_changed(event)   # replay again, for good measure

    genome_bg.assert_not_awaited()
    assert mock_log.await_count == 0  # nothing NEW to audit either time


@pytest.mark.anyio
async def test_full_chain_crash_after_one_consequence_real_dispatch_retry_resumes():
    """Simulates a REAL crash mid-dispatch: the first dispatch_pending_events()
    call completes genome_refresh then the process dies before
    timeline_entry runs (modeled here by pre-seeding genome_refresh as
    already-completed, matching exactly what the DB would show after such a
    crash) -- the row is NOT yet marked dispatched_at (crash happened before
    that final step too). A second dispatch_pending_events() call (the
    retry) must resume: skip genome_refresh, complete only timeline_entry,
    and THEN mark the row dispatched."""
    from services.event_bus import dispatch_pending_events

    supa, rows, dispatched = _make_full_chain_supa(existing_consequence_rows={
        ("evt-real-1", "genome_refresh"): {"status": "completed", "result_ref": "9"},
    })
    genome_bg = AsyncMock()

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await dispatch_pending_events()

    genome_bg.assert_not_awaited()  # NOT re-run
    assert result["dispecovano"] == 1
    assert "evt-real-1" in dispatched  # retry completed successfully this time
    assert rows[("evt-real-1", "timeline_entry")]["status"] == "completed"
    assert rows[("evt-real-1", "refresh_case_actions")]["status"] == "completed"
    # 2 newly-completed consequences (timeline_entry, refresh_case_actions)
    # -> 2 case_evolution_consequence_completed rows + refresh_case_actions's
    # own domain-specific case_action_refreshed row = 3 total.
    assert mock_log.await_count == 3


@pytest.mark.anyio
async def test_full_chain_correlation_id_flows_from_raw_row_to_audit_call():
    """Provenance/correlation continuity, proven at the raw-row level: the
    correlation_id written into the events table row must be the SAME id
    that appears in every audit call downstream -- not regenerated, not
    dropped, not replaced at any hop (row -> Event -> handle_case_changed
    -> log_action)."""
    from services.event_bus import dispatch_pending_events

    supa, rows, _ = _make_full_chain_supa()

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await dispatch_pending_events()

    correlation_ids = {c.kwargs.get("correlation_id") for c in mock_log.await_args_list}
    assert correlation_ids == {"corr-real-1"}


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6 — Architectural Invariants, proven structurally (not narrated)
# ═══════════════════════════════════════════════════════════════════════════

def test_consequences_never_emit_further_business_events():
    """A canonical architectural invariant this certification asserts
    explicitly: no consequence executor in services/case_evolution.py may
    itself emit a further Event Bus event (no cascading). Proven by
    absence -- grep the module source for any call to emit_durable/
    bus.publish/event_bus.emit. If this ever starts failing, someone added
    event-to-event cascading, a real architecture change that needs its own
    review, not a silent addition."""
    path = os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    for forbidden in ("emit_durable(", "bus.publish(", "bus.publish_async(", "event_bus.emit("):
        assert forbidden not in content, f"services/case_evolution.py now cascades via {forbidden!r} -- invariant violated"


def test_no_in_process_only_emit_for_any_case_evolution_event():
    """None of the 6 Case-Evolution-owned event types may EVER be emitted
    via the non-durable in-process emit()/bus.publish() path -- only
    emit_durable()/direct events-table inserts, which alone provide the
    event_id handle_case_changed requires. Confirmed by repo-wide grep: the
    only two EventType members emitted via in-process emit() are
    ROK_KRITICAN/HEALTH_SCORE_PROMENJEN (routers/matter_intel.py) -- both
    OUTSIDE Case Evolution's own domain (Project Sentinel's pre-existing,
    still-open SENT-001), not one of the 6 this test protects."""
    case_evolution_events = {
        EventType.DOCUMENT_ACCEPTED, EventType.REVIEW_ACCEPTED, EventType.REVIEW_REJECTED,
        EventType.NEW_CLIENT_LINKED, EventType.NEW_EVIDENCE_REGISTERED, EventType.ROCISTE_ZAKAZANO,
    }
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    offenders = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "tests", "__pycache__", "venv", ".venv")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            with open(full, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for et in case_evolution_events:
                # Narrow, deliberate pattern: a bare emit(EventType.X call
                # (the in-process, non-durable helper) -- NOT emit_durable(.
                needle = f"emit(EventType.{et.name}"
                if needle in content and "emit_durable" not in content.split(needle)[0][-40:]:
                    offenders.append((os.path.relpath(full, repo_root), et.name))
    assert offenders == [], f"Case Evolution event(s) emitted via non-durable emit(): {offenders}"


def test_one_owner_per_wired_event_type():
    """Architectural Invariant: exactly one handler per Case-Evolution-owned
    event type, always handle_case_changed, never a second subscriber."""
    from services.case_evolution import handle_case_changed
    for et in (EventType.DOCUMENT_ACCEPTED, EventType.REVIEW_ACCEPTED, EventType.REVIEW_REJECTED,
               EventType.NEW_CLIENT_LINKED, EventType.NEW_EVIDENCE_REGISTERED, EventType.ROCISTE_ZAKAZANO):
        assert bus._handlers[et] == [handle_case_changed], f"{et.name} has more than one owner: {bus._handlers[et]}"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7 — Self-Consistency: registry claims vs. live code, re-verified
# fresh this sprint (not trusted forward from Sprint 003)
# ═══════════════════════════════════════════════════════════════════════════

def test_event_type_total_member_count_matches_documentation():
    """Sprint 003's own CASE_EVOLUTION_REGISTRY.md claimed 19 EventType
    members -- Sprint 004's own certification found the real count was 20
    (DOCUMENT_JOB_FAILED was described in prose but never given its own row
    in the 'other 10' table, undercounting by one). Program Omega Sprint 002
    (2026-08-06) added a 21st member (DOCUMENT_BATCH_COMPLETED). This test
    pins the true count so it can never silently drift again without a
    documentation update being forced to keep pace."""
    assert len(list(EventType)) == 21


def test_registry_100_percent_matches_event_bus_wiring():
    from services.case_evolution import CONSEQUENCE_REGISTRY, handle_case_changed
    wired_to_canonical = {
        et for et, handlers in bus._handlers.items()
        if any(h is handle_case_changed for h in handlers)
    }
    assert wired_to_canonical == set(CONSEQUENCE_REGISTRY.keys())


def test_no_new_direct_call_bypass_of_canonical_consequence_functions():
    """Re-run of Sprint 003's own repo-wide bypass test -- re-verified fresh
    this sprint, not assumed still true."""
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    allowed_prefixes = {
        "_run_genome_background(": {"routers\\case_dna.py", "routers/case_dna.py", "services\\case_evolution.py", "services/case_evolution.py"},
        "klasifikuj_i_sacuvaj(": {"routers\\evidence.py", "routers/evidence.py", "services\\case_evolution.py", "services/case_evolution.py"},
        "_run_conflict_check(": {"routers\\intake.py", "routers/intake.py", "services\\case_evolution.py", "services/case_evolution.py"},
    }
    for needle, allowed_files in allowed_prefixes.items():
        offenders = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "tests", "__pycache__", "venv", ".venv")]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, repo_root)
                with open(full, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if needle in content and rel not in allowed_files:
                    offenders.append(rel)
        assert offenders == [], f"New direct-call bypass found for {needle!r}: {offenders}"
