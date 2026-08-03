# -*- coding: utf-8 -*-
"""
Operation Lawyer Day (2026-08-03): POST /api/predmeti/{predmet_id}/upload
(api.py::predmet_upload_auto_analyze) is the ONLY document-upload path a
lawyer can actually reach today -- Smart Intake (routers/smart_intake.py),
which DOES accept images, has zero frontend callers (see
.vindex_ai_team/decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md).

Night Shift M-001 (2026-08-02) claimed "photo upload now works end to end"
as a removed Beta Critical Path blocker (scenario #3), but that fix only
touched Smart Intake's own upload validation -- THIS endpoint's
_ALLOWED_MIMES/_ALLOWED_SUFFIXES were never updated, so a lawyer with phone
photos of a document could not upload them anywhere reachable in the app.
uploaded_doc/extractor.py::extract() already dispatches .jpg/.jpeg/.png to
extract_image() with the exact same (text, is_scanned, ocr_used) contract
this endpoint already consumes for PDF/DOCX -- extract_image()'s own
docstring explicitly anticipated this caller needing zero special-casing.

User Scenario Test: a lawyer uploads a phone photo of a served document to
an existing case. Before this fix: HTTP 415, "Podržani formati: PDF, DOCX" --
silently impossible, no workaround inside the app. After this fix: accepted
exactly like a PDF, reaches the same OCR/analysis pipeline.

Mirrors tests/test_smart_intake_upload_validation.py's UploadFile-construction
pattern and tests/test_sec001_predmet_ownership.py's api.py auth-mocking
pattern (api.py uses _require_auth + inline PermissionService.require(),
not the router files' Depends(get_current_user)).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import UploadFile

import api


def _fake_user(uid: str = "user-0000-0000-0000-000000000001", email: str = "advokat@vindex.rs"):
    return types.SimpleNamespace(id=uid, email=email)


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-1/upload", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _upload_file(filename: str, content_type: str, content: bytes = b"fake bytes for test") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


async def _fake_permission_dependency(user=None):
    return user


def _mock_supa_owns_predmet(predmet_id: str = "pred-1", uid: str = "user-0000-0000-0000-000000000001"):
    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": predmet_id, "naziv": "Test predmet", "tip": "opsti",
    }
    return supa


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _StopAfterGuard(Exception):
    """Sentinel raised by a patched extract() so the test can prove the
    upload-validation guard was passed without needing to mock the rest of
    this endpoint's large downstream pipeline (RAG, chunking, Pinecone,
    multiple GPT-4o calls)."""


@pytest.mark.anyio
async def test_jpg_photo_upload_passes_validation_and_reaches_extract():
    mock_supa = _mock_supa_owns_predmet()

    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=mock_supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", side_effect=_StopAfterGuard("reached extract()")):
        with pytest.raises(_StopAfterGuard):
            await api.predmet_upload_auto_analyze(
                "pred-1", _fake_request(),
                _upload_file("fotografija_dokumenta.jpg", "image/jpeg"),
                authorization="Bearer test-token",
            )


@pytest.mark.anyio
async def test_png_photo_upload_passes_validation_and_reaches_extract():
    mock_supa = _mock_supa_owns_predmet()

    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=mock_supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", side_effect=_StopAfterGuard("reached extract()")):
        with pytest.raises(_StopAfterGuard):
            await api.predmet_upload_auto_analyze(
                "pred-1", _fake_request(),
                _upload_file("skenirano.png", "image/png"),
                authorization="Bearer test-token",
            )


@pytest.mark.anyio
async def test_unsupported_format_still_rejected_before_reaching_extract():
    """An unsupported type must never even reach extract() -- proves the
    fix only widened the allowlist, it didn't remove the guard."""
    mock_supa = _mock_supa_owns_predmet()

    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=mock_supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", side_effect=_StopAfterGuard("must not be reached")):
        with pytest.raises(Exception) as exc_info:
            await api.predmet_upload_auto_analyze(
                "pred-1", _fake_request(),
                _upload_file("malware.exe", "application/octet-stream"),
                authorization="Bearer test-token",
            )
    assert not isinstance(exc_info.value, _StopAfterGuard)
    assert getattr(exc_info.value, "status_code", None) == 415


@pytest.mark.anyio
async def test_pdf_upload_unaffected_by_the_image_allowlist_widening():
    """Regression guard: widening the allowlist for images must not change
    PDF's own already-working acceptance."""
    mock_supa = _mock_supa_owns_predmet()

    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=mock_supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", side_effect=_StopAfterGuard("reached extract()")):
        with pytest.raises(_StopAfterGuard):
            await api.predmet_upload_auto_analyze(
                "pred-1", _fake_request(),
                _upload_file("tuzba.pdf", "application/pdf"),
                authorization="Bearer test-token",
            )


def test_allowed_mimes_and_suffixes_include_images():
    """Direct guard against an accidental future revert of this exact fix."""
    assert "image/jpeg" in api._ALLOWED_MIMES
    assert "image/png" in api._ALLOWED_MIMES
    assert ".jpg" in api._ALLOWED_SUFFIXES
    assert ".jpeg" in api._ALLOWED_SUFFIXES
    assert ".png" in api._ALLOWED_SUFFIXES
    # Pre-existing formats must still be present -- this was a widening, not a replacement.
    assert "application/pdf" in api._ALLOWED_MIMES
    assert ".pdf" in api._ALLOWED_SUFFIXES
    assert ".docx" in api._ALLOWED_SUFFIXES
