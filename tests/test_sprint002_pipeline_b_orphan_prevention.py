# -*- coding: utf-8 -*-
"""
Program Intake Sprint 002 (2026-08-05) — regression tests for Pipeline B
(routers/smart_intake.py::upload_intake_documents) orphan-blob prevention.

Sprint 002 Fork C found the Storage blob duplication trigger was broader
than the already-known INTAKE-002 (RPC-failure only): an ORDINARY
sequential duplicate resubmit (no failure needed) always re-uploaded a
fresh encrypted blob under a new uuid4 key, even though enqueue_intake_job
would then just return the ALREADY-EXISTING job_id without ever recording
the new blob anywhere. Two fixes:

1. A pre-check SELECT by idempotency_key before the Storage upload even
   runs — short-circuits duplicate resubmits, never uploads a blob that
   would be orphaned.
2. A compensating delete of the just-uploaded blob if `enqueue_job` itself
   throws (the true-concurrent-race case, where the pre-check passed but a
   second request won the unique-index race first).
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


@pytest.mark.anyio
async def test_duplicate_resubmit_skips_storage_upload_entirely():
    """A duplicate submission (same idempotency_key already has a job row)
    must never reach the Storage upload at all -- the whole point is to
    avoid creating a blob that would immediately become orphaned."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = MagicMock()
    existing_row = MagicMock(data={"id": "existing-job-1"})
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = existing_row
    mock_encrypt = MagicMock(return_value=b"should-not-be-called")
    mock_enqueue = AsyncMock(return_value="should-not-be-called")

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", mock_encrypt), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=mock_enqueue):
        result = await upload_intake_documents(_fake_request(), [_upload_file("tuzba.pdf")], _fake_user())

    assert result["rezultati"][0]["ok"] is True
    assert result["rezultati"][0]["job_id"] == "existing-job-1"
    assert result["rezultati"][0]["already_submitted"] is True
    mock_encrypt.assert_not_called()  # no wasted Storage upload
    mock_supa.storage.from_.return_value.upload.assert_not_called()
    mock_enqueue.assert_not_awaited()


@pytest.mark.anyio
async def test_fresh_submission_still_uploads_and_enqueues_normally():
    """No existing job for this idempotency_key -- must proceed exactly as
    before (no regression on the ordinary first-time-upload path)."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = MagicMock()
    no_existing = MagicMock(data=None)
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = no_existing
    mock_supa.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_supa.storage.from_.return_value.upload.return_value = None

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(return_value="job-new-1")):
        result = await upload_intake_documents(_fake_request(), [_upload_file("tuzba.pdf")], _fake_user())

    assert result["rezultati"][0]["ok"] is True
    assert result["rezultati"][0]["job_id"] == "job-new-1"
    assert "already_submitted" not in result["rezultati"][0]
    mock_supa.storage.from_.return_value.upload.assert_called_once()


@pytest.mark.anyio
async def test_enqueue_failure_deletes_the_just_uploaded_blob():
    """True concurrent race: pre-check passes (no existing job yet), the
    Storage upload succeeds, but enqueue_job then throws (e.g. the other
    concurrent request won the idempotency_key unique-index race first).
    The just-uploaded blob must be deleted -- otherwise it's a permanent,
    untracked orphan (INTAKE-002)."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = MagicMock()
    no_existing = MagicMock(data=None)
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = no_existing
    mock_supa.storage.from_.return_value.upload.return_value = None
    mock_supa.storage.from_.return_value.remove = MagicMock(return_value=None)

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(side_effect=Exception("unique_violation"))):
        result = await upload_intake_documents(_fake_request(), [_upload_file("tuzba.pdf")], _fake_user())

    assert result["rezultati"][0]["ok"] is False
    mock_supa.storage.from_.return_value.upload.assert_called_once()
    mock_supa.storage.from_.return_value.remove.assert_called_once()
    removed_keys = mock_supa.storage.from_.return_value.remove.call_args[0][0]
    assert len(removed_keys) == 1  # exactly the key that was just uploaded


@pytest.mark.anyio
async def test_enqueue_failure_cleanup_itself_failing_does_not_mask_original_error():
    """If the compensating delete ALSO fails, the user-facing response must
    still be the honest 'upload failed' message -- cleanup failure is
    logged, never surfaced as a different or crashing response."""
    from routers.smart_intake import upload_intake_documents

    mock_supa = MagicMock()
    no_existing = MagicMock(data=None)
    mock_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = no_existing
    mock_supa.storage.from_.return_value.upload.return_value = None
    mock_supa.storage.from_.return_value.remove = MagicMock(side_effect=Exception("bucket unreachable"))

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake._encrypt", return_value=b"encrypted-bytes"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(side_effect=Exception("unique_violation"))):
        result = await upload_intake_documents(_fake_request(), [_upload_file("tuzba.pdf")], _fake_user())

    assert result["rezultati"][0]["ok"] is False  # same honest failure, not a crash
    assert "greska" in result["rezultati"][0]
