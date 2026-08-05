# -*- coding: utf-8 -*-
"""
Program Intake Sprint 003 (2026-08-05) — regression tests for "Canonical
Document Understanding"'s central fix: a document's classification must end
in exactly one of two states — Canonically Classified, or Review Required.
A third state (silently guessed) must not exist.

Sprint 003 Fork C's headline finding: even Pipeline C (finalize), which
routes through Pipeline B's confidence-gated classifier, let that correctly-
flagged-uncertain classification be silently, unconditionally overwritten by
a SECOND classifier (routers/evidence.py::_klasifikuj_dokument) that has no
confidence field at all — regardless of whether the original classification
was low-confidence or its review-queue entry was ever resolved. Finalize also
never surfaced this uncertainty anywhere in its own response.

Fix (routers/smart_intake.py::finalize_intake_job):
1. `result["review"]` (previously fetched, never read) is now inspected —
   if `document_type` is in `low_confidence_fields`, `classification_uncertain`
   is True.
2. When uncertain, the confidence-blind `_evidence_classify_bg` overwrite
   task is NOT scheduled — Pipeline B's own (uncertain) classification is
   left as the case-file value, rather than silently replaced by an equally
   unfounded but more-confident-looking second guess.
3. The finalize response now always includes `klasifikacija_nesigurna` and
   `nesigurna_polja`, making Review Required an explicit, visible state
   instead of one buried in an endpoint (`GET /jobs/{id}`) nobody revisits
   after finalize.

Mirrors tests/test_lz002_evidence_autoclassify.py's and
tests/test_ztc_scenario_b_attach.py's mocking pattern.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(new_doc_id="dok-001"):
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
            t.insert.return_value.execute.return_value.data = [{"id": new_doc_id}]
        elif name == "klijenti":
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "intake_job_segments":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    supa.table.side_effect = _table
    return supa


def _base_patches(mock_supa, job_result, mock_classify):
    return (
        patch("routers.smart_intake._get_supa", return_value=mock_supa),
        patch("shared.intake_segments._get_supa", return_value=mock_supa),
        patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])),
        patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")),
        patch("uploaded_doc.extractor.extract", return_value=("Tuzba teksta ovde.", False, False, None)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-001"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2026-08-03T00:00:00Z"),
        patch("routers.evidence.klasifikuj_i_sacuvaj", mock_classify),
        patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})),
    )


async def _run_finalize_and_drain(mock_supa, job_result, mock_classify=None):
    import contextlib
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    if mock_classify is None:
        mock_classify = MagicMock()

    captured_coros = []

    def _capture_create_task(coro, *a, **kw):
        captured_coros.append(coro)
        return MagicMock()

    with contextlib.ExitStack() as stack:
        for p in _base_patches(mock_supa, job_result, mock_classify):
            stack.enter_context(p)
        stack.enter_context(patch("asyncio.create_task", side_effect=_capture_create_task))
        result = await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), _fake_user())
        for coro in captured_coros:
            try:
                await coro
            except Exception:
                pass
    return result, mock_classify


@pytest.mark.anyio
async def test_uncertain_classification_skips_evidence_overwrite_and_flags_response():
    """The sprint's central regression: document_type flagged as
    low-confidence by Pipeline B must NOT be silently overwritten by the
    confidence-blind Evidence Vault classifier, and finalize's own response
    must say so explicitly."""
    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "entities": [],
        "review": {"reason": "low_confidence_extraction", "low_confidence_fields": ["document_type", "deadline"]},
    }

    result, mock_classify = await _run_finalize_and_drain(mock_supa, job_result)

    assert result["klasifikacija_nesigurna"] is True
    assert result["nesigurna_polja"] == ["document_type", "deadline"]
    mock_classify.assert_not_called()  # the confidence-blind overwrite must never fire


@pytest.mark.anyio
async def test_confident_classification_still_gets_evidence_vocabulary_correction():
    """Regression guard: the LZ-002 fix (English->Serbian vocabulary
    correction for EXPECTED_DOCS matching) must still run normally for the
    common, high-confidence case -- this sprint narrows the overwrite's
    scope, it does not remove its legitimate purpose."""
    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "entities": [],
        "review": None,
    }

    result, mock_classify = await _run_finalize_and_drain(mock_supa, job_result)

    assert result["klasifikacija_nesigurna"] is False
    assert result["nesigurna_polja"] == []
    mock_classify.assert_called_once()


@pytest.mark.anyio
async def test_review_present_but_document_type_not_flagged_still_allows_overwrite():
    """Only document_type-specific uncertainty should gate the overwrite --
    a low-confidence ENTITY (e.g. deadline) with a confident document_type
    must not block the legitimate vocabulary-correction task."""
    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "entities": [],
        "review": {"reason": "low_confidence_extraction", "low_confidence_fields": ["deadline"]},
    }

    result, mock_classify = await _run_finalize_and_drain(mock_supa, job_result)

    assert result["klasifikacija_nesigurna"] is False
    mock_classify.assert_called_once()


@pytest.mark.anyio
async def test_intake_job_status_flags_staleness_after_finalize():
    """Sprint 003 Fork A's confirmed defect: GET /jobs/{id} kept serving the
    pre-finalize English-vocab classification indefinitely, presented as if
    current, contradicting the real Serbian-vocab value already in the case
    file. After this fix, once predmet_id is set (finalized), the response
    must honestly flag the value as possibly-stale rather than silent."""
    from routers.smart_intake import intake_job_status

    mock_supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "source": "dropzone", "attempts": 0,
                "last_error": None, "created_at": "2026-08-05T00:00:00Z", "completed_at": "2026-08-05T00:01:00Z",
                "original_filename": "tuzba.pdf", "predmet_id": "pred-001",
            }
        return t
    mock_supa.table.side_effect = _table

    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit", "classification_confidence": 0.92, "ocr_used": False},
        "entities": [],
        "review": None,
    }

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])):
        result = await intake_job_status("job-1", _fake_request(), _fake_user())

    assert result["dokument"]["tip_moze_biti_zastareo"] is True
    assert result["dokument"]["napomena"] is not None


@pytest.mark.anyio
async def test_intake_job_status_no_staleness_flag_before_finalize():
    from routers.smart_intake import intake_job_status

    mock_supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "source": "dropzone", "attempts": 0,
                "last_error": None, "created_at": "2026-08-05T00:00:00Z", "completed_at": "2026-08-05T00:01:00Z",
                "original_filename": "tuzba.pdf", "predmet_id": None,
            }
        return t
    mock_supa.table.side_effect = _table

    job_result = {
        "document": {"id": "dok-001", "document_type": "lawsuit", "classification_confidence": 0.92, "ocr_used": False},
        "entities": [],
        "review": None,
    }

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])):
        result = await intake_job_status("job-1", _fake_request(), _fake_user())

    assert result["dokument"]["tip_moze_biti_zastareo"] is False
    assert result["dokument"]["napomena"] is None
