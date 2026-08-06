# -*- coding: utf-8 -*-
"""
Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario 5): POST
/api/intake/conflict-check existed and worked, but only in the older
name-first CRM Intake Wizard flow -- the document-first Smart Intake flow
never called it, even though party names extracted from the uploaded
document (value_map's plaintiff/defendant) are already available at exactly
the moment finalize creates the case. A case could be created with a
conflict of interest never having been checked, silently, every time.

Fix, in two parts:
1. routers/intake.py's conflict-check logic was extracted into a plain
   async helper (_run_conflict_check) so Smart Intake's finalize can call it
   directly (Rule Zero -- reuse, don't duplicate the matching logic). The
   existing HTTP endpoint (tests/test_intake_conflict_check.py) is
   unaffected -- it's now a thin wrapper delegating to the same function.
2. routers/smart_intake.py's finalize_intake_job calls it as a background
   task (non-blocking -- a false-positive name match must never silently
   block a lawyer from opening a real case) and surfaces any conflict found
   via the existing proactive_alerts mechanism (same table Case Genome
   already uses for its own alerts).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


# ═══════════════════════════════════════════════════════════════════════════
# _run_conflict_check — direct call, extracted from the HTTP endpoint
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_run_conflict_check_callable_directly_without_request_or_body():
    """The whole point of the extraction: callable with plain args, no
    Request/rate-limiter/pydantic body needed."""
    from routers.intake import _run_conflict_check

    clients = [{"id": "kl-001", "ime": "Ana", "prezime": "Jović", "firma": "", "pib_encrypted": None}]
    predmeti = [{"id": "pred-001", "naziv": "Radni spor", "tuzilac": "", "tuzeni": ""}]
    pk = {"kl-001": [{"predmet_id": "pred-001", "uloga_klijenta": "stranka"}]}

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = clients
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = predmeti
        elif name == "predmet_klijenti":
            def _pk_chain(col, val):
                inner = MagicMock()
                inner.execute.return_value.data = pk.get(val, [])
                return inner
            t.select.return_value.eq.side_effect = _pk_chain
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await _run_conflict_check(
            "00000000-0000-0000-0000-000000000001",
            "Marko Marković", "", "Ana Jović", "",
        )

    assert result["conflict_detected"] is True
    assert result["has_blocker"] is True


@pytest.mark.anyio
async def test_run_conflict_check_no_conflict_when_names_unrelated():
    from routers.intake import _run_conflict_check

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = []
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await _run_conflict_check(
            "00000000-0000-0000-0000-000000000001", "Potpuno Novo Ime", "", "", "",
        )

    assert result["conflict_detected"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Smart Intake finalize — auto-surfaced conflict check
# ═══════════════════════════════════════════════════════════════════════════

def _make_supa():
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "storage_path": "session/xyz",
                "original_filename": "tuzba.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-001"}]
        elif name == "predmet_dokumenti":
            t.insert.return_value.execute.return_value.data = [{"id": "dok-001"}]
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            # Program Intake Sprint 007 -- no cross-upload duplicate, no
            # crash-recovery needed (fresh job, first finalize attempt).
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "klijenti":
            # Program Intake Sprint 006 -- resolve_client_ownership() queries
            # .eq().ilike().neq().execute() (no .limit(), it fetches every
            # candidate to detect ambiguity, never picks arbitrarily).
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "proactive_alerts":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "intake_job_segments":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    supa.table.side_effect = _table
    return supa


async def _run_finalize(mock_supa, job_result, body, emit_side_effect=None):
    """Program Delta, Sprint 002 (2026-08-05): the conflict-check call is no
    longer a direct in-process `asyncio.create_task(_conflict_check_bg())`
    -- it's a durable NEW_CLIENT_LINKED event emission
    (services/event_bus.py::emit_durable), captured here directly instead
    of draining asyncio.create_task coroutines. Running the actual conflict
    check + surfacing an alert is now services/case_evolution.py::
    _consequence_conflict_check's own responsibility, tested in
    tests/test_delta_sprint002_event_migration.py -- this harness verifies
    only finalize's OWN responsibility: emit the right event, once."""
    from routers.smart_intake import finalize_intake_job

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])), \
         patch("shared.intake_segments._get_supa", return_value=mock_supa), \
         patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")), \
         patch("uploaded_doc.extractor.extract", return_value=("Tuzba teksta ovde.", False, False, None)), \
         patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}), \
         patch("uploaded_doc.ingest.ingest_session", return_value=None), \
         patch("uploaded_doc.session.generate_session_id", return_value="sess-001"), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("shared.vector_origin.now_iso", return_value="2026-08-03T00:00:00Z"), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1", "finalizing_at": "2026-08-07T00:00:00+00:00"})), \
         patch("services.event_bus.emit_durable", new=AsyncMock(side_effect=emit_side_effect)) as mock_emit:

        result = await finalize_intake_job("job-1", _fake_request(), body, _fake_user())

    return result, mock_emit


@pytest.mark.anyio
async def test_finalize_emits_new_client_linked_durably():
    """Program Delta, Sprint 002: finalize must emit NEW_CLIENT_LINKED
    exactly once with the correct predmet_id/klijent_ime/protivna_strana
    payload, regardless of whether a conflict actually exists (finalize no
    longer knows the outcome -- that decision moved to the Canonical
    Consequence Engine)."""
    from routers.smart_intake import FinalizeReq
    from services.event_bus import EventType

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [
            {"entity_type": "plaintiff", "value": "Marko Marković"},
            {"entity_type": "defendant", "value": "Ana Jović"},
        ],
    }

    result, mock_emit = await _run_finalize(mock_supa, job_result, FinalizeReq(klijent_strana="defendant"))

    assert result["predmet_id"] == "pred-001"
    client_linked_calls = [c for c in mock_emit.call_args_list if c.args[0] == EventType.NEW_CLIENT_LINKED]
    assert len(client_linked_calls) == 1
    call_args = client_linked_calls[0].args
    assert call_args[1] == "00000000-0000-0000-0000-000000000001"  # uid
    assert call_args[2] == "pred-001"  # predmet_id
    assert call_args[3]["klijent_ime"] == "Ana Jović"
    assert call_args[3]["protivna_strana"] == "Marko Marković"


@pytest.mark.anyio
async def test_finalize_emit_failure_does_not_break_case_creation():
    """Fire-and-forget discipline preserved through the migration: if the
    durable NEW_CLIENT_LINKED insert itself fails (DB error, not a conflict
    check finding), the case must still be created — same guarantee the
    old in-process background task provided, now proven at the emission
    layer instead of at _run_conflict_check's own call site."""
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [{"entity_type": "plaintiff", "value": "Marko Marković"}],
    }

    result, _mock_emit = await _run_finalize(
        mock_supa, job_result, FinalizeReq(klijent_strana="plaintiff"),
        emit_side_effect=RuntimeError("boom"),
    )

    assert result["predmet_id"] == "pred-001"
