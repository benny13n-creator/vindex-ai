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


async def _run_finalize_and_drain(mock_supa, job_result, body, conflict_result):
    from routers.smart_intake import finalize_intake_job

    captured_coros = []

    def _capture_create_task(coro, *a, **kw):
        captured_coros.append(coro)
        return MagicMock()

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
         patch("routers.evidence.klasifikuj_i_sacuvaj"), \
         patch("routers.intake._run_conflict_check", new=AsyncMock(return_value=conflict_result)) as mock_cc, \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})), \
         patch("asyncio.create_task", side_effect=_capture_create_task):

        result = await finalize_intake_job("job-1", _fake_request(), body, _fake_user())
        for coro in captured_coros:
            try:
                await coro
            except Exception:
                pass

    return result, mock_cc


@pytest.mark.anyio
async def test_finalize_surfaces_alert_when_conflict_detected():
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [
            {"entity_type": "plaintiff", "value": "Marko Marković"},
            {"entity_type": "defendant", "value": "Ana Jović"},
        ],
    }
    conflict_result = {
        "conflict_detected": True, "has_blocker": True,
        "conflicts": [{"opis": "Ana Jović je vaš postojeći klijent."}],
        "preporuka": "Postoji BLOKIRAJUCI sukob interesa.",
    }

    captured_alerts = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "proactive_alerts":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_alerts.append(row)
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    result, mock_cc = await _run_finalize_and_drain(
        mock_supa, job_result,
        FinalizeReq(klijent_strana="defendant"),
        conflict_result,
    )

    assert result["predmet_id"] == "pred-001"
    mock_cc.assert_called_once()
    call_args = mock_cc.call_args[0]
    assert call_args[0] == "00000000-0000-0000-0000-000000000001"  # uid
    assert call_args[1] == "Ana Jović"  # klijent_ime (the defendant side, per klijent_strana)
    assert call_args[3] == "Marko Marković"  # protivna_strana (the other side)

    assert len(captured_alerts) == 1
    assert captured_alerts[0]["tip"] == "sukob_interesa"
    assert captured_alerts[0]["urgentnost"] == "hitna"
    assert captured_alerts[0]["predmet_id"] == "pred-001"


@pytest.mark.anyio
async def test_finalize_does_not_create_alert_when_no_conflict():
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [
            {"entity_type": "plaintiff", "value": "Marko Marković"},
            {"entity_type": "defendant", "value": "Ana Jović"},
        ],
    }
    conflict_result = {"conflict_detected": False, "has_blocker": False, "conflicts": [], "preporuka": ""}

    captured_alerts = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "proactive_alerts":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_alerts.append(row)
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    result, mock_cc = await _run_finalize_and_drain(
        mock_supa, job_result, FinalizeReq(klijent_strana="defendant"), conflict_result,
    )

    assert result["predmet_id"] == "pred-001"
    assert captured_alerts == []


@pytest.mark.anyio
async def test_finalize_conflict_check_failure_does_not_break_case_creation():
    """Fire-and-forget, same discipline as LZ-002's evidence classifier: if
    the conflict check itself raises, the case must still be created."""
    from routers.smart_intake import FinalizeReq, finalize_intake_job

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [{"entity_type": "plaintiff", "value": "Marko Marković"}],
    }

    captured_coros = []

    def _capture_create_task(coro, *a, **kw):
        captured_coros.append(coro)
        return MagicMock()

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
         patch("routers.evidence.klasifikuj_i_sacuvaj"), \
         patch("routers.intake._run_conflict_check", new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})), \
         patch("asyncio.create_task", side_effect=_capture_create_task):

        result = await finalize_intake_job(
            "job-1", _fake_request(), FinalizeReq(klijent_strana="plaintiff"), _fake_user(),
        )
        for coro in captured_coros:
            try:
                await coro
            except Exception:
                pass

    assert result["predmet_id"] == "pred-001"
