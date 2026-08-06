# -*- coding: utf-8 -*-
"""
Program Delta, Sprint 002 (2026-08-05) — "Canonical Event Migration I:
Human Decisions Become System Decisions". Tests for the 4 newly-migrated
events (REVIEW_ACCEPTED, REVIEW_REJECTED, NEW_CLIENT_LINKED,
NEW_EVIDENCE_REGISTERED) and their consequence executors in
services/case_evolution.py, plus REVIEW_REJECTED's own new canonical
definition (shared/intake_documents.py::reject_review,
POST /jobs/{job_id}/review/reject).

Mission's own required test scenarios, mapped onto this sprint's 4 events:
1. Review Accepted -> Genome -> Timeline -> Audit -> exactly once.
2. Review Rejected -> rollback (nothing was ever applied -> nothing to
   undo) -> no duplicates.
3. Client Linked -> same event twice -> same result (idempotent).
4. Evidence Added -> parallel execution -> no race condition.
5. Crash after the first consequence, retry -> resumes, no duplicate.
6. Replay -> same correlation_id, same audit, same result.
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


# ═══════════════════════════════════════════════════════════════════════════
# Shared mock-Supabase harness — case_evolution_consequences + predmeti
# (genome verzija) + predmet_hronologija (timeline), combined so the REAL
# CONSEQUENCE_REGISTRY (not overridden) can run end to end.
# ═══════════════════════════════════════════════════════════════════════════

def _make_combined_supa(existing_consequence_rows=None, verzija_start=3):
    existing_rows = dict(existing_consequence_rows or {})
    verzija_state = {"n": verzija_start}

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
            # Program Lambda, Certification 004: .upsert(...).execute() is
            # the real chain -- must return a node with its OWN .execute(),
            # not the result directly, and must honor ignore_duplicates
            # (real INSERT...ON CONFLICT DO NOTHING inserts nothing on an
            # existing key) for _try_claim_consequence's own atomic claim.
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
        def _fake_execute():
            verzija_state["n"] += 1
            res = MagicMock()
            res.data = {"case_dna": {"verzija": verzija_state["n"]}}
            return res
        # first read (before) uses the CURRENT value without incrementing;
        # emulate by reading, then incrementing only on the "after" read --
        # simplest correct model: increment happens once per genome_refresh
        # call via _run_genome_background (mocked separately), so both
        # before/after reads here just return current state at read time.
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = _fake_execute
        return t

    def _hronologija_table():
        t = MagicMock()
        t.insert.return_value.execute.return_value.data = [{"id": "hron-1"}]
        return t

    def _table(name):
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
    return supa, existing_rows


def _review_accepted_event(event_id="evt-1", predmet_id="pred-1", correlation_id="corr-1"):
    return Event(
        type=EventType.REVIEW_ACCEPTED, user_id="user-1", predmet_id=predmet_id,
        payload={"intake_job_id": "job-1", "prior_status": "awaiting_review",
                 "job_status_advanced": True, "review_resolved_now": True},
        correlation_id=correlation_id, event_id=event_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Review Accepted -> Genome -> Timeline -> Audit -> exactly once
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario1_review_accepted_genome_timeline_audit_exactly_once():
    from services.case_evolution import handle_case_changed

    supa, rows = _make_combined_supa()
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_review_accepted_event())

    assert genome_bg.await_count == 1
    assert rows[("evt-1", "genome_refresh")]["status"] == "completed"
    assert rows[("evt-1", "timeline_entry")]["status"] == "completed"
    assert rows[("evt-1", "review_confirmation_audit")]["status"] == "completed"
    # One case_evolution_consequence_completed audit row per consequence (5,
    # since Program Omega Sprint 003 appended refresh_case_actions and Final
    # Sprint 007 appended project_notifications) + one domain-specific
    # dokument_review_resolved row from review_confirmation_audit + one
    # domain-specific case_action_refreshed row from refresh_case_actions =
    # 7 total log_action calls. project_notifications itself skips silently
    # (this harness's own predmeti fake has no user_id -> "skipped_no_owner")
    # and does not add its own domain-specific audit row.
    assert mock_log.await_count == 7
    actions = [c.args[0] for c in mock_log.await_args_list]
    assert actions.count("dokument_review_resolved") == 1
    assert actions.count("case_action_refreshed") == 1
    assert actions.count("case_evolution_consequence_completed") == 5


@pytest.mark.anyio
async def test_review_accepted_pre_finalize_skips_genome_and_timeline():
    """The common case: review resolved BEFORE the job's first finalize
    (predmet_id still None) -- genome_refresh/timeline_entry must no-op
    gracefully (reused DOCUMENT_ACCEPTED executors' own existing
    skipped_no_predmet_id path), only the audit consequence does real
    work."""
    from services.case_evolution import handle_case_changed

    supa, rows = _make_combined_supa()
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_review_accepted_event(predmet_id=None))

    genome_bg.assert_not_awaited()
    assert rows[("evt-1", "genome_refresh")]["result_ref"] == "skipped_no_predmet_id"
    assert rows[("evt-1", "timeline_entry")]["result_ref"] == "skipped_no_predmet_id"
    assert rows[("evt-1", "review_confirmation_audit")]["status"] == "completed"


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Review Rejected -> rollback (nothing applied, nothing to undo)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario2_review_rejected_only_audits_no_genome_no_timeline():
    """REVIEW_REJECTED's own canonical definition: no genome_refresh, no
    timeline_entry are even registered -- 'rollback' is trivial by
    construction (a rejected review never advanced intake_jobs.status to
    'completed', so nothing was ever applied to the case in the first
    place)."""
    from services.case_evolution import handle_case_changed, CONSEQUENCE_REGISTRY

    assert [c.name for c in CONSEQUENCE_REGISTRY[EventType.REVIEW_REJECTED]] == ["review_rejection_audit"]

    supa, rows = _make_combined_supa()
    event = Event(
        type=EventType.REVIEW_REJECTED, user_id="user-1", predmet_id=None,
        payload={"intake_job_id": "job-1", "review_resolved_now": True, "job_status_rejected": True},
        correlation_id="corr-1", event_id="evt-rej-1",
    )

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(event)
        await handle_case_changed(event)  # replay -- no duplicate

    assert rows[("evt-rej-1", "review_rejection_audit")]["status"] == "completed"
    # 2 log_action calls total (dokument_review_rejected + generic
    # consequence-completed), NOT 4 -- the replay was a full no-op.
    assert mock_log.await_count == 2
    actions = [c.args[0] for c in mock_log.await_args_list]
    assert actions.count("dokument_review_rejected") == 1


@pytest.mark.anyio
async def test_reject_review_never_advances_job_to_completed():
    from shared.intake_documents import reject_review

    supa = MagicMock()
    tables: dict = {}

    def _table(name):
        if name in tables:
            return tables[name]
        t = MagicMock()
        if name == "intake_review_queue":
            t.update.return_value.eq.return_value.is_.return_value.execute.return_value.data = [{"id": "rq-1"}]
        elif name == "intake_jobs":
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "job-1", "status": "rejected"}]
        tables[name] = t
        return t
    supa.table.side_effect = _table

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await reject_review("job-1", "advokat@vindex.rs")

    assert result["review_resolved_now"] is True
    assert result["job_status_rejected"] is True
    # Status update must target 'rejected', never 'completed'.
    update_call = tables["intake_jobs"].update.call_args
    assert update_call.args[0]["status"] == "rejected"


@pytest.mark.anyio
async def test_reject_review_idempotent_on_double_call():
    from shared.intake_documents import reject_review

    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_review_queue":
            t.update.return_value.eq.return_value.is_.return_value.execute.return_value.data = []  # already resolved
        elif name == "intake_jobs":
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []  # already not awaiting_review
        return t
    supa.table.side_effect = _table

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await reject_review("job-1", "advokat@vindex.rs")

    assert result == {"review_resolved_now": False, "job_status_rejected": False}


@pytest.mark.anyio
async def test_reject_job_review_endpoint_blocks_when_already_finalized():
    from routers.smart_intake import reject_job_review
    from fastapi import HTTPException

    supa = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "job-1", "status": "completed", "predmet_id": "pred-999",
    }
    supa.table.return_value = t

    with patch("routers.smart_intake._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            await reject_job_review("job-1", _fake_request(), _fake_user())

    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_reject_job_review_endpoint_emits_review_rejected():
    from routers.smart_intake import reject_job_review

    supa = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "job-1", "status": "awaiting_review", "predmet_id": None,
    }
    supa.table.return_value = t

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_documents.reject_review",
               new=AsyncMock(return_value={"review_resolved_now": True, "job_status_rejected": True})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await reject_job_review("job-1", _fake_request(), _fake_user())

    assert result["ok"] is True
    mock_emit.assert_awaited_once()
    assert mock_emit.call_args.args[0] == EventType.REVIEW_REJECTED
    assert mock_emit.call_args.args[2] is None  # predmet_id


def _fake_request():
    from starlette.requests import Request as StarletteRequest
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/review/reject", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Client Linked -> same event twice -> same result
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario3_client_linked_replayed_produces_same_result():
    from services.case_evolution import handle_case_changed

    supa, rows = _make_combined_supa()
    conflict_result = {"conflict_detected": True, "has_blocker": True,
                        "conflicts": [{"opis": "Ana Jović je vaš postojeći klijent."}],
                        "preporuka": "Postoji blokirajući sukob interesa."}
    event = Event(
        type=EventType.NEW_CLIENT_LINKED, user_id="user-1", predmet_id="pred-1",
        payload={"klijent_id": "kl-1", "klijent_ime": "Ana Jović", "protivna_strana": "Marko Marković"},
        correlation_id="corr-1", event_id="evt-cl-1",
    )

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.intake._run_conflict_check", new=AsyncMock(return_value=conflict_result)) as mock_cc, \
         patch("shared.proactive_alerts.create_proactive_alert", new=AsyncMock(return_value=True)) as mock_alert, \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(event)
        await handle_case_changed(event)  # replay -- same event object

    assert mock_cc.await_count == 1  # NOT called twice
    assert mock_alert.await_count == 1  # NOT duplicated
    assert rows[("evt-cl-1", "conflict_check")]["result_ref"] == "conflict_alert_created"


@pytest.mark.anyio
async def test_client_linked_no_conflict_creates_no_alert():
    from services.case_evolution import _consequence_conflict_check

    event = Event(
        type=EventType.NEW_CLIENT_LINKED, user_id="user-1", predmet_id="pred-1",
        payload={"klijent_id": "kl-1", "klijent_ime": "Novo Ime", "protivna_strana": ""},
        event_id="evt-1",
    )
    with patch("routers.intake._run_conflict_check",
               new=AsyncMock(return_value={"conflict_detected": False, "has_blocker": False, "conflicts": [], "preporuka": ""})), \
         patch("shared.proactive_alerts.create_proactive_alert", new=AsyncMock()) as mock_alert:
        result = await _consequence_conflict_check(event)

    assert result == "no_conflict"
    mock_alert.assert_not_awaited()


@pytest.mark.anyio
async def test_client_linked_skips_when_no_klijent_ime():
    from services.case_evolution import _consequence_conflict_check

    event = Event(type=EventType.NEW_CLIENT_LINKED, user_id="user-1", predmet_id="pred-1",
                   payload={"klijent_id": None, "klijent_ime": "", "protivna_strana": ""}, event_id="evt-1")
    result = await _consequence_conflict_check(event)
    assert result == "skipped_no_klijent_ime"


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — Evidence Added -> parallel execution -> no race condition
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario4_evidence_added_parallel_no_race_condition():
    """Two DIFFERENT documents (different dokument_id, different event_id)
    classified concurrently -- each must independently verify and complete
    its own consequence row; neither's klasifikovan_at read/verify state
    leaks into the other's. Per-document-id call-count model: call #1 for a
    given dokument_id is the executor's own 'before' read (klasifikovan_at
    still null), call #2 is the 'after' read (post-classify, set)."""
    from services.case_evolution import handle_case_changed

    classify_calls = []
    per_doc_call_n: dict[str, int] = {"dok-A": 0, "dok-B": 0}

    def _dokumenti_table():
        t = MagicMock()
        def _eq(col, val):
            inner = MagicMock()
            def _execute():
                per_doc_call_n[val] += 1
                res = MagicMock()
                res.data = {
                    "naziv_fajla": f"{val}.pdf", "tekst_sadrzaj": "tekst...",
                    "klasifikovan_at": None if per_doc_call_n[val] == 1 else "2026-08-05T00:00:00Z",
                }
                return res
            inner.maybe_single.return_value.execute.side_effect = _execute
            return inner
        t.select.return_value.eq.side_effect = _eq
        return t

    existing_rows: dict = {}
    def _cec():
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

    def _table(name):
        if name == "case_evolution_consequences":
            return _cec()
        if name == "predmet_dokumenti":
            return _dokumenti_table()
        t = MagicMock()
        t.insert.return_value.execute.return_value.data = [{"id": "row-1"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event_a = Event(type=EventType.NEW_EVIDENCE_REGISTERED, user_id="user-1", predmet_id="pred-1",
                     payload={"dokument_id": "dok-A", "naziv": "a.pdf"}, event_id="evt-A")
    event_b = Event(type=EventType.NEW_EVIDENCE_REGISTERED, user_id="user-1", predmet_id="pred-1",
                     payload={"dokument_id": "dok-B", "naziv": "b.pdf"}, event_id="evt-B")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.evidence.klasifikuj_i_sacuvaj", side_effect=lambda *a, **kw: classify_calls.append(a[1])), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await asyncio.gather(handle_case_changed(event_a), handle_case_changed(event_b))

    assert set(classify_calls) == {"dok-A", "dok-B"}
    assert existing_rows[("evt-A", "evidence_classification")]["status"] == "completed"
    assert existing_rows[("evt-B", "evidence_classification")]["status"] == "completed"


@pytest.mark.anyio
async def test_evidence_classify_skips_when_no_tekst_sadrzaj():
    from services.case_evolution import _consequence_evidence_classify

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "naziv_fajla": "d.pdf", "tekst_sadrzaj": None, "klasifikovan_at": None,
    }
    event = Event(type=EventType.NEW_EVIDENCE_REGISTERED, user_id="user-1", predmet_id="pred-1",
                  payload={"dokument_id": "dok-1"}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa):
        result = await _consequence_evidence_classify(event)

    assert result == "skipped_no_tekst_sadrzaj"


@pytest.mark.anyio
async def test_evidence_classify_verifies_klasifikovan_at_actually_set():
    """Must not trust klasifikuj_i_sacuvaj's own 'no exception' as proof --
    if klasifikovan_at is STILL null after the call (simulating an
    internally-swallowed failure), this must raise, not silently succeed."""
    from services.case_evolution import _consequence_evidence_classify

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "naziv_fajla": "d.pdf", "tekst_sadrzaj": "tekst...", "klasifikovan_at": None,
    }
    event = Event(type=EventType.NEW_EVIDENCE_REGISTERED, user_id="user-1", predmet_id="pred-1",
                  payload={"dokument_id": "dok-1"}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.evidence.klasifikuj_i_sacuvaj"):
        with pytest.raises(RuntimeError, match="verifikacija neuspešna"):
            await _consequence_evidence_classify(event)


# ═══════════════════════════════════════════════════════════════════════════
# Test 5 — Crash after the first consequence, retry -> resumes, no duplicate
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario5_crash_after_first_review_accepted_consequence_retry_resumes():
    from services.case_evolution import handle_case_changed

    supa, rows = _make_combined_supa(existing_consequence_rows={
        ("evt-1", "genome_refresh"): {"status": "completed", "result_ref": "4"},
    })
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        await handle_case_changed(_review_accepted_event())

    genome_bg.assert_not_awaited()  # NOT re-executed
    assert rows[("evt-1", "timeline_entry")]["status"] == "completed"
    assert rows[("evt-1", "review_confirmation_audit")]["status"] == "completed"
    assert rows[("evt-1", "refresh_case_actions")]["status"] == "completed"
    assert rows[("evt-1", "project_notifications")]["status"] == "completed"
    actions = [c.args[0] for c in mock_log.await_args_list]
    # only the 4 newly-completed (genome_refresh already done pre-crash):
    # timeline_entry, review_confirmation_audit, refresh_case_actions,
    # project_notifications (Final Sprint 007).
    assert actions.count("case_evolution_consequence_completed") == 4


# ═══════════════════════════════════════════════════════════════════════════
# Test 6 — Replay -> same correlation_id, same audit, same result
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario6_replay_shares_correlation_id_and_produces_no_new_audit():
    from services.case_evolution import handle_case_changed

    supa, rows = _make_combined_supa()
    genome_bg = AsyncMock()

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        event = _review_accepted_event(correlation_id="corr-ZZZ")
        await handle_case_changed(event)
        first_call_count = mock_log.await_count
        await handle_case_changed(event)  # replay

    assert mock_log.await_count == first_call_count  # no NEW audit rows
    correlation_ids = {c.kwargs.get("correlation_id") for c in mock_log.await_args_list}
    assert correlation_ids == {"corr-ZZZ"}
