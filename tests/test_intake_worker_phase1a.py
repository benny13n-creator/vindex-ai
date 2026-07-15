# -*- coding: utf-8 -*-
"""
Tests for IntakeWorker._process() Phase 1A pipeline (decrypt+OCR →
classify → extract → review routing → processing_outcomes).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _job(job_id="job-1", storage_path="u1/abc", original_filename="presuda.pdf", mime_type="application/pdf"):
    return {"id": job_id, "storage_path": storage_path, "original_filename": original_filename,
            "mime_type": mime_type, "attempts": 0, "max_attempts": 5}


@pytest.mark.anyio
async def test_process_skips_already_processed_job_idempotent():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    existing = {"document": {"id": "doc-1"}, "entities": [], "review": None}
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=existing)), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock()) as mock_download:
        await w._process(_job())

    mock_download.assert_not_awaited()  # never re-downloaded — idempotency guard fired


@pytest.mark.anyio
async def test_process_ocr_failed_routes_to_review_fail_soft_not_exception():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    no_existing = {"document": None, "entities": [], "review": None}
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=no_existing)), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"%PDF-fake-bytes")), \
         patch.object(w, "_extract_text", return_value=("", True, False)), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")) as mock_create_doc, \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()) as mock_outcome:
        await w._process(_job())  # must NOT raise — OCR failure is fail-soft, not an exception

    mock_create_doc.assert_awaited_once()
    assert mock_create_doc.call_args[0][1] == "other"  # document_type fallback
    mock_review.assert_awaited_once()
    assert mock_review.call_args[0][2] == "ocr_failed"
    mock_outcome.assert_awaited_once()


@pytest.mark.anyio
async def test_process_success_path_no_review_when_all_confident():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    no_existing = {"document": None, "entities": [], "review": None}
    high_confidence_entities = [
        {"entity_type": "case_number", "value": "П 341/26", "confidence": 0.95, "extraction_method": "regex"},
        {"entity_type": "deadline", "value": "15.11.2026", "confidence": 0.9, "extraction_method": "regex"},
    ]

    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=no_existing)), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("ТУЖБА текст...", False, False)), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "lawsuit", "confidence": 0.95, "method": "heuristic"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=high_confidence_entities)), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()) as mock_outcome:
        await w._process(_job())

    mock_review.assert_not_awaited()  # everything above threshold — no review needed
    mock_outcome.assert_awaited_once()


@pytest.mark.anyio
async def test_process_low_confidence_field_routes_to_review_with_specific_fields_only():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    no_existing = {"document": None, "entities": [], "review": None}
    mixed_entities = [
        {"entity_type": "case_number", "value": "П 341/26", "confidence": 0.95, "extraction_method": "regex"},
        {"entity_type": "deadline", "value": None, "confidence": 0.0, "extraction_method": "regex"},  # low
        {"entity_type": "amount", "value": "1.000 РСД", "confidence": 0.92, "extraction_method": "regex"},
        {"entity_type": "judge", "value": None, "confidence": 0.0, "extraction_method": "llm"},  # low
    ]

    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=no_existing)), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("tekst", False, False)), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "judgment", "confidence": 0.95, "method": "heuristic"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=mixed_entities)), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()):
        await w._process(_job())

    mock_review.assert_awaited_once()
    call_args = mock_review.call_args[0]
    reason, low_confidence_fields = call_args[2], call_args[3]
    assert reason == "low_confidence_extraction"
    # Exactly the 2 uncertain fields — NOT all 4 entities, matching the
    # product Definition of Done ("nesigurnost oko DVE stavke, ne dvadeset").
    assert set(low_confidence_fields) == {"deadline", "judge"}


@pytest.mark.anyio
async def test_process_low_confidence_classification_adds_document_type_to_review():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    no_existing = {"document": None, "entities": [], "review": None}
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=no_existing)), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("nejasan tekst", False, False)), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "other", "confidence": 0.4, "method": "llm"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()):
        await w._process(_job())

    mock_review.assert_awaited_once()
    low_confidence_fields = mock_review.call_args[0][3]
    assert "document_type" in low_confidence_fields


def test_guess_suffix_prefers_original_filename():
    from shared.intake_worker import IntakeWorker
    assert IntakeWorker._guess_suffix("presuda.docx", "application/pdf") == ".docx"
    assert IntakeWorker._guess_suffix(None, "application/pdf") == ".pdf"
    assert IntakeWorker._guess_suffix(None, "text/plain") == ".txt"
    assert IntakeWorker._guess_suffix(None, None) == ".pdf"
