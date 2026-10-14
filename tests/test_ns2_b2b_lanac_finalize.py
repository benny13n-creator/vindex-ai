"""NS2 B2b (nezavisni pregled): lanac OCR ogranicenje -> finalize i nastavak posla (resume) nose ocr_used. Preuzeto iz probe recenzenta."""
from unittest.mock import AsyncMock, patch

import pytest

from shared import intake_documents
from shared.intake_worker import IntakeWorker, _ocr_entiteti_na_pregled
from tests.test_blk1_deadline_safety import _blk1_finalize, _blk1_supa


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _row(e, reviewed=False, corrected=None):
    return {"id": "e-" + e["entity_type"], "entity_type": e["entity_type"], "value": e["value"],
            "confidence": e["confidence"], "reviewed": reviewed, "corrected_value": corrected,
            "extraction_method": e["extraction_method"]}


_DL = [{"entity_type": "deadline", "value": "27.09.2026", "confidence": 0.95, "extraction_method": "regex"}]


@pytest.mark.anyio
async def test_chain_ocr_rok_nepotvrdjen_ne_ulazi():
    [e] = _ocr_entiteti_na_pregled(_DL, True)
    supa = _blk1_supa()
    r = await _blk1_finalize(supa, [_row(e)])
    assert r["rok_dodat"] is False and r["rok_preskocen_razlog"] == "niska_pouzdanost" and supa.blk1_upisi == []


@pytest.mark.anyio
async def test_chain_ocr_rok_potvrdjen_istom_vrednoscu_ulazi():
    [e] = _ocr_entiteti_na_pregled(_DL, True)
    supa = _blk1_supa()
    r = await _blk1_finalize(supa, [_row(e, reviewed=True, corrected="27.09.2026")])
    assert r["rok_dodat"] is True and supa.blk1_upisi[0]["datum_iso"] == "2026-09-27"


@pytest.mark.anyio
async def test_chain_digitalni_rok_ulazi_bez_potvrde():
    [e] = _ocr_entiteti_na_pregled(_DL, False)
    supa = _blk1_supa()
    r = await _blk1_finalize(supa, [_row(e)])
    assert r["rok_dodat"] is True


@pytest.mark.anyio
async def test_resume_segmenti_nose_ocr_used():
    """Resume (existing_segment_rows) path: pending segment re-processed after crash must still be capped."""
    from tests.test_sprint005_segmentation_worker import _PAGE_1, _PAGE_2, _PAGE_3
    pages = [_PAGE_1, _PAGE_2, _PAGE_3]
    seg_rows = [{"id": "seg-A", "segment_index": 0, "status": "completed", "attempts": 0, "max_attempts": 2},
                {"id": "seg-B", "segment_index": 1, "status": "pending", "attempts": 0, "max_attempts": 2}]
    w = IntakeWorker()
    job = {"id": "job-1", "storage_path": "u1/abc", "original_filename": "sken.pdf", "mime_type": "application/pdf",
           "attempts": 1, "max_attempts": 5}
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None, "entities": [], "review": None})), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, True, pages, 0.93)), \
         patch.object(w, "_nepotpuno_procitano", return_value=[]), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=seg_rows)), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "lawsuit", "confidence": 0.95, "method": "heuristic"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(side_effect=lambda t: [dict(e) for e in _DL])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(side_effect=["doc-B"])), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])) as ins, \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()), \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_processing", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_completed", new=AsyncMock()) as done, \
         patch("shared.intake_segments.mark_segment_awaiting_review", new=AsyncMock()) as aw, \
         patch("shared.intake_segments.mark_segment_failed", new=AsyncMock()):
        rezultat = await w._process(job)
    assert ins.await_count == 1, ins.call_args_list
    assert all(e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD for e in ins.call_args[0][1])
    assert aw.await_count == 1 and done.await_count == 0 and rezultat is True
