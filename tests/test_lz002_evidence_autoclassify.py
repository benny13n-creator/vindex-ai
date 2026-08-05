# -*- coding: utf-8 -*-
"""
Operation Lawyer Zero, LZ-002 (2026-08-03): Evidence Vault's real classifier
(routers/evidence.py::klasifikuj_i_sacuvaj) was never auto-triggered on
document ingestion -- only reachable via the manual /reklasifikuj action.
This also starved services/risk_engine.py's missing-document detector,
which reads predmet_dokumenti.tip_dokaza and compares it against
shared/constants.py's EXPECTED_DOCS vocabulary -- a DIFFERENT vocabulary
than the one Smart Intake's own coarse classifier was already (silently,
uselessly) writing into that same field.

This test exercises the real finalize_intake_job endpoint end to end
(mocking only external I/O: Supabase, Pinecone ingest, OpenAI-backed
classification), capturing the scheduled background task and awaiting it,
the same way tests/test_intake.py's M-013 tests verified the Case Pipeline
trigger earlier this session.
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
                "original_filename": "presuda.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-001"}]
        elif name == "predmet_dokumenti":
            t.insert.return_value.execute.return_value.data = [{"id": new_doc_id}]
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            # Program Intake Sprint 007 -- no cross-upload duplicate, no
            # crash-recovery needed (fresh job, first finalize attempt).
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
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


@pytest.mark.anyio
async def test_finalize_triggers_evidence_classification_in_background():
    """Program Delta, Sprint 002 (2026-08-05): the direct
    `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))` call
    this test originally proved was replaced by a durable
    NEW_EVIDENCE_REGISTERED emission -- services/case_evolution.py::
    _consequence_evidence_classify now owns actually calling
    klasifikuj_i_sacuvaj (tested in tests/test_delta_sprint002_event_
    migration.py). This test now asserts on finalize's OWN responsibility:
    emit the right event, with the right dokument_id, once."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq
    from services.event_bus import EventType

    mock_supa = _make_supa()
    job_result = {
        "document": {"id": "dok-001", "document_type": "judgment"},
        "entities": [],
        "review": None,
    }

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])), \
         patch("shared.intake_segments._get_supa", return_value=mock_supa), \
         patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")), \
         patch("uploaded_doc.extractor.extract", return_value=("Presuda teksta ovde.", False, False, None)), \
         patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}), \
         patch("uploaded_doc.ingest.ingest_session", return_value=None), \
         patch("uploaded_doc.session.generate_session_id", return_value="sess-001"), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("shared.vector_origin.now_iso", return_value="2026-08-03T00:00:00Z"), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:

        result = await finalize_intake_job(
            "job-1", _fake_request(), FinalizeReq(), _fake_user(),
        )

    assert result["predmet_id"] == "pred-001"
    evidence_calls = [c for c in mock_emit.call_args_list if c.args[0] == EventType.NEW_EVIDENCE_REGISTERED]
    assert len(evidence_calls) == 1
    call_args = evidence_calls[0].args
    assert call_args[1] == "00000000-0000-0000-0000-000000000001"  # uid
    assert call_args[2] == "pred-001"  # predmet_id
    assert call_args[3]["dokument_id"] == "dok-001"
    assert call_args[3]["naziv"] == "presuda.pdf"


@pytest.mark.anyio
async def test_finalize_evidence_classification_failure_does_not_break_response():
    """Program Delta, Sprint 002 (2026-08-05): fire-and-forget discipline
    preserved through the migration -- if the durable NEW_EVIDENCE_REGISTERED
    insert itself fails (a classifier failure now happens later, async, in
    the Canonical Consequence Engine -- tested separately), the case must
    still be created and the response must still succeed."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    mock_supa = _make_supa()
    job_result = {"document": {"id": "dok-001", "document_type": "judgment"}, "entities": [], "review": None}

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])), \
         patch("shared.intake_segments._get_supa", return_value=mock_supa), \
         patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")), \
         patch("uploaded_doc.extractor.extract", return_value=("Presuda teksta ovde.", False, False, None)), \
         patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}), \
         patch("uploaded_doc.ingest.ingest_session", return_value=None), \
         patch("uploaded_doc.session.generate_session_id", return_value="sess-001"), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("shared.vector_origin.now_iso", return_value="2026-08-03T00:00:00Z"), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})), \
         patch("services.event_bus.emit_durable", new=AsyncMock(side_effect=RuntimeError("boom"))):

        result = await finalize_intake_job(
            "job-1", _fake_request(), FinalizeReq(), _fake_user(),
        )

    assert result["predmet_id"] == "pred-001"
