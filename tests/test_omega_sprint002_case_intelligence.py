# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 002 (2026-08-06) — "Case Intelligence Aggregation
Engine". Tests for `DOCUMENT_BATCH_COMPLETED`'s own 2 consequences
(`genome_refresh`, reused unchanged; `case_intelligence_summary`, new) and
the 5 required extreme scenarios from the mission's own Phase 5.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import Event, EventType, bus


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_combined_supa(existing_consequence_rows=None, case_dna_after=None, dokazi=None, dokumenti=None, rocista=None):
    """case_evolution_consequences + predmeti (case_dna) + predmet_dokazi/
    predmet_dokumenti/rocista (risk-engine inputs) + case_intelligence_summaries."""
    existing_rows = dict(existing_consequence_rows or {})
    verzija_state = {"n": 3}
    inserted_summaries = []

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
        def _upsert(row, on_conflict=None, ignore_duplicates=False):
            node = MagicMock()
            def _execute():
                key = (row["event_id"], row["consequence_name"])
                res = MagicMock()
                if ignore_duplicates and key in existing_rows:
                    res.data = []
                    return res
                existing_rows[key] = {**existing_rows.get(key, {}), **row}
                res.data = [row]
                return res
            node.execute.side_effect = _execute
            return node
        t.upsert.side_effect = _upsert
        def _update_chain(payload):
            def _make_level(filters: dict):
                node = MagicMock()
                def _eq_next(col, val):
                    return _make_level({**filters, col: val})
                node.eq.side_effect = _eq_next
                def _execute():
                    res = MagicMock()
                    key = (filters.get("event_id"), filters.get("consequence_name"))
                    current = existing_rows.get(key, {})
                    if "status" in filters and current.get("status") != filters["status"]:
                        res.data = []
                        return res
                    existing_rows[key] = {**current, **payload}
                    res.data = [existing_rows[key]]
                    return res
                node.execute.side_effect = _execute
                return node
            return _make_level({})
        t.update.side_effect = _update_chain
        return t

    def _predmeti_table():
        t = MagicMock()
        def _execute():
            verzija_state["n"] += 1
            res = MagicMock()
            dna = dict(case_dna_after or {})
            dna["verzija"] = verzija_state["n"]
            res.data = {"case_dna": dna, "tip": "parnicno"}
            return res
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = _execute
        return t

    def _simple_select_table(rows):
        t = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=rows or [])
        t.select.return_value.eq.return_value = chain
        t.select.return_value.eq.return_value.is_.return_value = chain
        t.select.return_value.eq.return_value.order.return_value = chain
        return t

    def _cis_table():
        t = MagicMock()
        def _insert(row):
            row = dict(row)
            row["id"] = f"summary-{len(inserted_summaries) + 1}"
            inserted_summaries.append(row)
            res = MagicMock(); res.data = [row]
            return res
        t.insert.side_effect = _insert
        return t

    def _table(name):
        if name == "case_evolution_consequences":
            return _cec_table()
        if name == "predmeti":
            return _predmeti_table()
        if name == "predmet_dokazi":
            return _simple_select_table(dokazi)
        if name == "predmet_dokumenti":
            return _simple_select_table(dokumenti)
        if name == "rocista":
            return _simple_select_table(rocista)
        if name == "case_intelligence_summaries":
            return _cis_table()
        t = MagicMock()
        t.insert.return_value.execute.return_value.data = [{"id": "row-1"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, existing_rows, inserted_summaries


def _batch_event(event_id="evt-batch-1", predmet_id="pred-1", correlation_id="corr-1", **payload_overrides):
    payload = {
        "reason": "DOCUMENT_BATCH_COMPLETED",
        "dokumenata_dodato": 5,
        "dokumenti_za_proveru": 1,
        "rokovi_dodati": 1,
        "job_ids": ["job-1", "job-2", "job-3", "job-4", "job-5"],
        "pre_verzija": 3,
        "pre_kontradikcije": 1,
        "pre_dogadjaji": 2,
    }
    payload.update(payload_overrides)
    return Event(type=EventType.DOCUMENT_BATCH_COMPLETED, user_id="user-1", predmet_id=predmet_id,
                 payload=payload, correlation_id=correlation_id, event_id=event_id)


# ═══════════════════════════════════════════════════════════════════════════
# Registry wiring
# ═══════════════════════════════════════════════════════════════════════════

def test_document_batch_completed_wired_to_canonical_dispatcher():
    from services.case_evolution import handle_case_changed
    assert bus._handlers[EventType.DOCUMENT_BATCH_COMPLETED] == [handle_case_changed]


def test_document_batch_completed_registry_is_genome_refresh_then_summary_in_order():
    """Program Omega, Sprint 003: timeline_entry was added between
    genome_refresh and case_intelligence_summary, reused from
    DOCUMENT_ACCEPTED, because the batch endpoint now suppresses its own
    per-job DOCUMENT_ACCEPTED emission (which used to be the only source of
    a Timeline entry for batch-processed documents). refresh_case_actions
    was appended last (Sprint 003, Canonical Action Engine) so it always
    reads a freshly-refreshed Genome/summary."""
    from services.case_evolution import (
        CONSEQUENCE_REGISTRY, _consequence_genome_refresh,
        _consequence_timeline_entry, _consequence_case_intelligence_summary,
        _consequence_refresh_case_actions,
    )
    consequences = CONSEQUENCE_REGISTRY[EventType.DOCUMENT_BATCH_COMPLETED]
    # Program Omega, Final Sprint 007 appended project_notifications as the
    # new trailing consequence, always reading the just-refreshed
    # case_actions rows (never stale) -- see
    # _consequence_project_case_actions_to_notifications's own docstring.
    assert [c.name for c in consequences] == [
        "genome_refresh", "timeline_entry", "case_intelligence_summary",
        "refresh_case_actions", "project_notifications",
    ]
    assert consequences[0].executor is _consequence_genome_refresh
    assert consequences[1].executor is _consequence_timeline_entry
    assert consequences[2].executor is _consequence_case_intelligence_summary
    assert consequences[3].executor is _consequence_refresh_case_actions


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — one predmet, 500 documents (one batch)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario1_single_case_large_batch_produces_one_summary_with_correct_diffs():
    from services.case_evolution import handle_case_changed

    case_dna_after = {
        "kontradikcije": [{"opis": "A"}, {"opis": "B"}, {"opis": "C"}],  # 1 pre -> 3 posle = 2 nove
        "datumi_kljucni": [{"opis": "d1"}, {"opis": "d2"}, {"opis": "d3"}, {"opis": "d4"}, {"opis": "d5"}],  # 2 pre -> 5 posle = 3 nova
    }
    supa, rows, summaries = _make_combined_supa(
        case_dna_after=case_dna_after,
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano"}],
        rocista=[],
    )
    genome_bg = AsyncMock()

    event = _batch_event(dokumenata_dodato=500)
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(event)

    genome_bg.assert_awaited_once()
    assert rows[("evt-batch-1", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-batch-1", "case_intelligence_summary")]["status"] == "completed"
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["dokumenata_dodato"] == 500
    assert summary["kontradikcije_pronadjene"] == 2
    assert summary["novi_dogadjaji"] == 3
    assert summary["rizici_koji_zahtevaju_paznju"] >= 0
    actions = [c.args[0] for c in mock_log.await_args_list]
    assert actions.count("case_intelligence_refreshed") == 1


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — one predmet, 500 documents, 5 upload sessions
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario2_five_separate_batches_for_the_same_case_each_produce_their_own_summary():
    """5 DIFFERENT DOCUMENT_BATCH_COMPLETED events (5 different event_ids)
    for the SAME predmet_id -- each is a legitimately distinct real event,
    so each must run independently (not deduplicated against each other --
    idempotency is per event_id, never per predmet_id)."""
    from services.case_evolution import handle_case_changed

    supa, rows, summaries = _make_combined_supa(case_dna_after={"kontradikcije": [], "datumi_kljucni": []})
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        for i in range(5):
            event = _batch_event(event_id=f"evt-session-{i}", dokumenata_dodato=100)
            await handle_case_changed(event)

    assert genome_bg.await_count == 5  # each session's own real refresh, none skipped
    assert len(summaries) == 5
    for i in range(5):
        assert rows[(f"evt-session-{i}", "genome_refresh")]["status"] == "completed"
        assert rows[(f"evt-session-{i}", "case_intelligence_summary")]["status"] == "completed"

    # Replaying any ONE of the 5 sessions again must NOT re-run it.
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_batch_event(event_id="evt-session-2", dokumenata_dodato=100))

    assert genome_bg.await_count == 5  # unchanged -- replay was a full no-op
    assert len(summaries) == 5  # no 6th summary


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3 — two users, same case, concurrent upload
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario3_two_concurrent_batches_same_case_no_cross_contamination():
    from services.case_evolution import handle_case_changed

    supa, rows, summaries = _make_combined_supa(case_dna_after={"kontradikcije": [], "datumi_kljucni": []})

    calls = []
    async def _fake_genome(predmet_id, uid, snaga, trigger=None):
        await asyncio.sleep(0)  # encourage interleaving
        calls.append(predmet_id)

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", _fake_genome), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await asyncio.gather(
            handle_case_changed(_batch_event(event_id="evt-userA", predmet_id="pred-shared", dokumenata_dodato=200)),
            handle_case_changed(_batch_event(event_id="evt-userB", predmet_id="pred-shared", dokumenata_dodato=300)),
        )

    assert len(calls) == 2
    assert rows[("evt-userA", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-userB", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-userA", "case_intelligence_summary")]["status"] == "completed"
    assert rows[("evt-userB", "case_intelligence_summary")]["status"] == "completed"
    assert len(summaries) == 2
    assert {s["dokumenata_dodato"] for s in summaries} == {200, 300}


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4 — crash after genome, before summary; restart resumes
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario4_crash_after_genome_before_summary_retry_does_not_redo_genome():
    from services.case_evolution import handle_case_changed

    supa, rows, summaries = _make_combined_supa(
        existing_consequence_rows={("evt-batch-1", "genome_refresh"): {"status": "completed", "result_ref": "9"}},
        case_dna_after={"kontradikcije": [], "datumi_kljucni": []},
    )
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_batch_event())

    genome_bg.assert_not_awaited()  # NOT redone -- already completed before the "crash"
    assert rows[("evt-batch-1", "case_intelligence_summary")]["status"] == "completed"
    assert len(summaries) == 1  # exactly one summary, no duplicate
    actions = [c.args[0] for c in mock_log.await_args_list]
    assert actions.count("case_intelligence_refreshed") == 1


@pytest.mark.anyio
async def test_scenario4_failed_summary_step_propagates_for_outer_retry():
    """If case_intelligence_summary itself fails (e.g. a DB error), it must
    be marked 'failed' and re-raise so the Event Bus's own retry mechanism
    picks it up -- not swallowed."""
    from services.case_evolution import handle_case_changed

    supa, rows, summaries = _make_combined_supa(
        existing_consequence_rows={("evt-batch-1", "genome_refresh"): {"status": "completed", "result_ref": "9"}},
    )
    # Force the risk-engine query step to fail by making the "predmeti"
    # table raise, while every other table keeps its normal mock behavior.
    orig_table = supa.table.side_effect
    def _table(name):
        if name == "predmeti":
            raise RuntimeError("db unavailable")
        return orig_table(name)
    supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        with pytest.raises(RuntimeError, match="db unavailable"):
            await handle_case_changed(_batch_event())

    assert rows[("evt-batch-1", "case_intelligence_summary")]["status"] == "failed"
    assert summaries == []


# ═══════════════════════════════════════════════════════════════════════════
# Executor-level unit tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_summary_skips_when_batch_added_zero_documents():
    from services.case_evolution import _consequence_case_intelligence_summary
    event = _batch_event(dokumenata_dodato=0)
    result = await _consequence_case_intelligence_summary(event)
    assert result == "skipped_no_new_documents"


@pytest.mark.anyio
async def test_summary_skips_when_no_predmet_id():
    from services.case_evolution import _consequence_case_intelligence_summary
    event = _batch_event(predmet_id=None)
    result = await _consequence_case_intelligence_summary(event)
    assert result == "skipped_no_predmet_id"
