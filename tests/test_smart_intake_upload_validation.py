# -*- coding: utf-8 -*-
"""
Tests for POST /api/smart-intake/documents' upload-time suffix validation —
Mission 001 / Night Shift M-001 (2026-08-02).

User Scenario Test (per this project's Definition-of-Done rule,
.vindex_ai_team/agents/11_qa_engineering.md): a lawyer uploads a photo of a
served document. Before this mission, this would be silently accepted, enqueued,
then fail deep in the background worker with no clear signal why. After this
mission: an image is accepted and enqueued exactly like a PDF; an unsupported
format is rejected immediately, in the same response, with a clear reason —
never silently queued to fail later.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from fastapi import UploadFile
from starlette.requests import Request as StarletteRequest


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/documents", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _upload_file(filename: str, content: bytes = b"fake bytes for test") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers=Headers({"content-type": "application/octet-stream"}))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mock_supa_and_queue():
    mock_supa = MagicMock()
    mock_supa.storage.from_.return_value.upload.return_value = None
    mock_supa.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    # Program Intake Sprint 002 (2026-08-05): upload_intake_documents now
    # does a pre-check SELECT by idempotency_key before uploading (avoids
    # orphaning a Storage blob on an ordinary duplicate resubmit). Without
    # this, the chain's default MagicMock return would be truthy AND
    # non-subscriptable, making every upload in these pre-existing tests
    # crash on `_existing_job_data["id"]` instead of proceeding normally --
    # configure it to report "no existing job" so these tests keep
    # exercising the storage+enqueue path they were written for.
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    return mock_supa


@pytest.mark.anyio
async def test_image_upload_accepted_and_enqueued():
    """User scenario: lawyer uploads a photographed document (.jpg) -- it
    must be accepted exactly like a PDF would be, not silently mis-typed
    or rejected."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = _mock_supa_and_queue()

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(return_value="job-abc123")):
        result = await upload_intake_documents(
            _fake_request(), [_upload_file("served_decision.jpg")], _fake_user(),
        )

    assert result["rezultati"][0]["ok"] is True
    assert result["rezultati"][0]["job_id"] == "job-abc123"


@pytest.mark.anyio
async def test_png_upload_accepted():
    from routers.smart_intake import upload_intake_documents

    mock_supa = _mock_supa_and_queue()

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(return_value="job-def456")):
        result = await upload_intake_documents(
            _fake_request(), [_upload_file("skenirano_resenje.png")], _fake_user(),
        )

    assert result["rezultati"][0]["ok"] is True


@pytest.mark.anyio
async def test_unsupported_extension_rejected_immediately_not_enqueued():
    """An unsupported file type must be rejected in THIS response, with a
    clear reason -- never silently enqueued to fail deep in the background
    worker."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = _mock_supa_and_queue()
    mock_enqueue = AsyncMock(return_value="should-not-be-called")

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=mock_enqueue):
        result = await upload_intake_documents(
            _fake_request(), [_upload_file("malware.exe")], _fake_user(),
        )

    assert result["rezultati"][0]["ok"] is False
    assert "format" in result["rezultati"][0]["greska"].lower()
    mock_enqueue.assert_not_awaited()


@pytest.mark.anyio
async def test_doc_extension_still_rejected_not_silently_accepted():
    """.doc is a KNOWN, separately-tracked gap (SEC-028: accepted by other
    upload paths but unhandled by the extractor) -- this endpoint must not
    newly start accepting it while fixing images; it should be rejected
    cleanly, same as any other unsupported type, until SEC-028 is fixed on
    its own."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = _mock_supa_and_queue()
    mock_enqueue = AsyncMock()

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=mock_enqueue):
        result = await upload_intake_documents(
            _fake_request(), [_upload_file("stari_dokument.doc")], _fake_user(),
        )

    assert result["rezultati"][0]["ok"] is False
    mock_enqueue.assert_not_awaited()


@pytest.mark.anyio
async def test_mixed_batch_valid_and_invalid_reported_independently():
    """A batch upload with both a good and a bad file must report each
    independently -- one bad file must not affect the other's outcome."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = _mock_supa_and_queue()

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(return_value="job-xyz")):
        result = await upload_intake_documents(
            _fake_request(),
            [_upload_file("photo.jpg"), _upload_file("virus.exe")],
            _fake_user(),
        )

    assert result["ukupno"] == 2
    by_name = {r["filename"]: r for r in result["rezultati"]}
    assert by_name["photo.jpg"]["ok"] is True
    assert by_name["virus.exe"]["ok"] is False
