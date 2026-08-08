# -*- coding: utf-8 -*-
"""
Program Intake Sprint 005 (2026-08-05) — Canonical Document Segmentation,
integration tests for IntakeWorker._process()/_process_segments().

Uses the REAL shared/intake_segment.py engine (segment_document,
uncertain_boundaries) against literal page texts crafted to trigger real
signals — not a mocked engine — so these tests exercise the genuine
integration between the engine and the worker, matching how
tests/test_intake_segment.py already exhaustively covers the pure engine
itself in isolation.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_partial_single_document():
    """None of these tests are about the single-document idempotency path
    (tests/test_intake_worker_phase1a.py already covers that exhaustively)."""
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None, "entities": [], "review": None})):
        yield


def _job(job_id="job-1"):
    return {"id": job_id, "storage_path": "u1/abc", "original_filename": "podnesci.pdf",
            "mime_type": "application/pdf", "attempts": 0, "max_attempts": 5}


# Two genuinely separate documents bundled in one 3-page upload: pages 1-2
# are a ТУЖБА (case 100/24), page 3 is a ПРЕСУДА (case 200/24) — new heading
# AND new case number both fire (2 strong signals -> auto-split, per the
# mission's own combination table).
_PAGE_1 = "ТУЖБА\nП. бр. 100/24\nОсновни суд у Београду\n\nТужилац подноси тужбу против туженог ради накнаде штете."
_PAGE_2 = "Наставак образложења тужбе, страна 2.\nТужилац додатно наводи чињенице у прилог захтеву."
_PAGE_3 = "ПРЕСУДА\nП. бр. 200/24\nОсновни суд у Београду\n\nСуд доноси следећу пресуду по горе наведеној тужби."

# A single lone strong signal (case number changes, no heading change, no
# corroboration) -- real evidence, but too thin to auto-split (mission
# mandate: route to review instead of guessing).
_PAGE_2_UNCERTAIN = "П. бр. 555/24\nОвде се наводи претходни предмет ради упоређивања."


def _classification(doc_type="lawsuit", confidence=0.95):
    return {"document_type": doc_type, "confidence": confidence, "method": "heuristic"}


@pytest.mark.anyio
async def test_ordinary_multi_page_upload_creates_no_segment_rows_stays_one_document():
    """The overwhelmingly common case (a multi-page upload that is still
    ONE document) must behave byte-for-byte like pre-Sprint-005 processing
    -- zero intake_job_segments rows, exactly one intake_documents row."""
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    text = _PAGE_1 + "\n\n" + _PAGE_2
    with patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=(text, False, False, [_PAGE_1, _PAGE_2], None)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch.object(w, "_classify", new=AsyncMock(return_value=_classification())), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")) as mock_create_doc, \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()), \
         patch("shared.intake_segments.create_segments", new=AsyncMock()) as mock_create_segments:
        result = await w._process(_job())

    mock_create_segments.assert_not_awaited()  # no segmentation bookkeeping engaged at all
    mock_create_doc.assert_awaited_once()
    mock_review.assert_not_awaited()
    assert result is False


@pytest.mark.anyio
async def test_two_bundled_documents_produce_two_segments_and_two_documents():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    pages = [_PAGE_1, _PAGE_2, _PAGE_3]
    seg_rows = [
        {"id": "seg-A", "segment_index": 0, "status": "pending", "attempts": 0, "max_attempts": 2},
        {"id": "seg-B", "segment_index": 1, "status": "pending", "attempts": 0, "max_attempts": 2},
    ]

    def _classify_side_effect(text):
        if "ПРЕСУДА" in text:
            return _classification("judgment")
        return _classification("lawsuit")

    with patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, False, pages, None)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_segments.create_segments", new=AsyncMock(return_value=seg_rows)) as mock_create_segments, \
         patch.object(w, "_classify", new=AsyncMock(side_effect=_classify_side_effect)), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(side_effect=["doc-A", "doc-B"])) as mock_create_doc, \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()) as mock_outcome, \
         patch("shared.intake_segments.mark_segment_processing", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_completed", new=AsyncMock()) as mock_completed, \
         patch("shared.intake_segments.mark_segment_failed", new=AsyncMock()) as mock_failed:
        result = await w._process(_job())

    mock_create_segments.assert_awaited_once()
    segments_passed = mock_create_segments.call_args[0][1]
    assert len(segments_passed) == 2
    assert segments_passed[0].start_page == 1 and segments_passed[0].end_page == 2
    assert segments_passed[1].start_page == 3 and segments_passed[1].end_page == 3

    assert mock_create_doc.await_count == 2
    assert mock_outcome.await_count == 2
    assert mock_completed.await_count == 2  # both segments confidently classified
    mock_failed.assert_not_awaited()
    mock_review.assert_not_awaited()
    assert result is False  # every segment completed confidently -> job as a whole is not awaiting review


@pytest.mark.anyio
async def test_one_segment_permanently_failing_does_not_lose_or_block_its_sibling():
    """Phase 6 (partial failure recovery) -- segment B fails every attempt
    (both in-process retries exhausted, dead-lettered); segment A must
    still be fully processed, not lost, not blocked, not retried itself."""
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    pages = [_PAGE_1, _PAGE_2, _PAGE_3]
    seg_rows = [
        {"id": "seg-A", "segment_index": 0, "status": "pending", "attempts": 0, "max_attempts": 2},
        {"id": "seg-B", "segment_index": 1, "status": "pending", "attempts": 0, "max_attempts": 2},
    ]

    async def _classify_side_effect(text):
        if "ПРЕСУДА" in text:
            raise RuntimeError("openai down")
        return _classification("lawsuit")

    with patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, False, pages, None)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_segments.create_segments", new=AsyncMock(return_value=seg_rows)), \
         patch.object(w, "_classify", new=AsyncMock(side_effect=_classify_side_effect)), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-A")) as mock_create_doc, \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()), \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()), \
         patch("shared.intake_documents.delete_partial_document", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_processing", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_completed", new=AsyncMock()) as mock_completed, \
         patch("shared.intake_segments.mark_segment_failed", new=AsyncMock(return_value=False)) as mock_failed_retry:
        # First call to mark_segment_failed returns False (retry), second returns True (dead-letter).
        mock_failed_retry.side_effect = [False, True]
        result = await w._process(_job())

    mock_create_doc.assert_awaited_once()  # ONLY segment A ever got a document -- B never succeeded
    mock_completed.assert_awaited_once_with("seg-A", "doc-A")
    assert mock_failed_retry.await_count == 2  # one retry, then dead-letter
    assert result is True  # segment B's permanent failure means the JOB needs a human look


@pytest.mark.anyio
async def test_resume_skips_already_completed_segment_only_processes_pending_one():
    """A job whose segmentation already ran on a prior (crashed) attempt:
    segment A already completed, segment B still pending. Resume must NOT
    recreate segment rows and must NOT reprocess segment A."""
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    pages = [_PAGE_1, _PAGE_2, _PAGE_3]
    existing_rows = [
        {"id": "seg-A", "segment_index": 0, "status": "completed", "document_id": "doc-A", "attempts": 0, "max_attempts": 2},
        {"id": "seg-B", "segment_index": 1, "status": "pending", "attempts": 0, "max_attempts": 2},
    ]

    with patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, False, pages, None)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=existing_rows)), \
         patch("shared.intake_worker.intake_segments.create_segments", new=AsyncMock()) as mock_create_segments, \
         patch.object(w, "_classify", new=AsyncMock(return_value=_classification("judgment"))), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-B")) as mock_create_doc, \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()), \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_processing", new=AsyncMock()) as mock_processing, \
         patch("shared.intake_segments.mark_segment_completed", new=AsyncMock()) as mock_completed:
        result = await w._process(_job())

    mock_create_segments.assert_not_awaited()  # rows already existed -- never recreated
    mock_processing.assert_awaited_once_with("seg-B")  # only the pending segment touched
    mock_create_doc.assert_awaited_once()  # only segment B got a fresh document
    mock_completed.assert_awaited_once_with("seg-B", "doc-B")
    assert result is False  # A already completed, B now completes confidently too


@pytest.mark.anyio
async def test_thin_segmentation_evidence_routes_to_review_without_splitting():
    """Phase 2's own conservatism mandate: one lone strong signal (a case
    number change with no heading change, no corroboration) is NOT enough
    to auto-split -- the document stays whole, but a human is asked to
    confirm via a 'segmentation_uncertain' review entry, rather than the
    engine silently doing nothing."""
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()

    pages = [_PAGE_1, _PAGE_2_UNCERTAIN]
    with patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, False, pages, None)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_segments.create_segments", new=AsyncMock()) as mock_create_segments, \
         patch.object(w, "_classify", new=AsyncMock(return_value=_classification())), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as mock_review, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()):
        result = await w._process(_job())

    mock_create_segments.assert_not_awaited()  # stayed ONE document -- no segment rows
    mock_review.assert_awaited_once()
    call_args = mock_review.call_args[0]
    assert call_args[2] == "segmentation_uncertain"
    assert result is True  # thin evidence still routes the job to human review
