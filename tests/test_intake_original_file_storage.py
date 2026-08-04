# -*- coding: utf-8 -*-
"""
Program Intake Sprint 001 (2026-08-04) — regression tests for Pipeline A
(api.py::predmet_upload_auto_analyze) now preserving the original uploaded
file in Supabase Storage.

Before this fix: the endpoint wrote raw bytes to a tempfile purely so OCR
could read them, deleted it in a finally block, and stored a
"session/{session_id}" label in predmet_dokumenti.storage_path that never
pointed to any real object — the original document (scanned image, signed
PDF) was unrecoverable once the request completed. This is a direct
instance of the mission's explicitly forbidden "dokument može nestati"
(document can disappear) condition.

Covers:
1. A successful upload now encrypts the raw bytes (reusing routers/
   smart_intake.py::_encrypt, the same AES-GCM pattern as the Klijenti
   Trezor) and uploads them to the intake-dokumenti bucket; storage_path
   in the predmet_dokumenti insert reflects the real, dereferencable key.
2. A storage-upload failure does not abort the request (best-effort,
   non-blocking by design — this is new protection, not an established
   invariant, so it must not create an availability regression) — the
   endpoint still succeeds, and storage_path honestly falls back to the
   old label instead of falsely claiming the original was preserved.

Mirrors tests/test_sentinel_reliability_fixes.py's api.py auth-mocking and
upload-pipeline mocking pattern.
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


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user(uid: str = "user-0000-0000-0000-000000000001", email: str = "advokat@vindex.rs"):
    return types.SimpleNamespace(id=uid, email=email)


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "insert", "execute", "single", "order", "limit", "is_", "gte", "or_"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock()
    r.data = data
    c.execute = MagicMock(return_value=r)
    return c


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


def _fake_openai_client():
    """The endpoint runs 3 parallel GPT-4o/-mini calls (auto-procena,
    hronologija, metapodaci) via a local `from openai import OpenAI as _OAI`
    import — patch the openai.OpenAI class itself so that local import binds
    to this fake. Each call only needs .choices[0].message.content."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="{}"))]
    client = MagicMock()
    client.chat.completions.create = MagicMock(return_value=resp)
    return MagicMock(return_value=client)


def _supa_upload_succeeds(predmet_id: str = "pred-1", inserted_rows: list = None):
    """predmeti ownership check succeeds; predmet_dokumenti SELECT (redni_broj
    lookup) succeeds empty; predmet_dokumenti INSERT captured for inspection;
    storage.from_(...).upload(...) succeeds (default MagicMock, no exception)."""
    if inserted_rows is None:
        inserted_rows = []

    def _table(name):
        if name == "predmeti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.single.return_value = c
            r = MagicMock(); r.data = {"id": predmet_id, "naziv": "Test predmet", "tip": "opsti"}
            c.execute = MagicMock(return_value=r)
            return c
        if name == "predmet_dokumenti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.order.return_value = c
            c.limit.return_value = c
            sel_r = MagicMock(); sel_r.data = []
            c.execute = MagicMock(return_value=sel_r)

            def _capture_insert(payload):
                inserted_rows.append(payload)
                insert_chain = MagicMock()
                r = MagicMock(); r.data = [dict(payload, id="dok-1")]
                insert_chain.execute = MagicMock(return_value=r)
                return insert_chain
            c.insert = MagicMock(side_effect=_capture_insert)
            return c
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_upload_stores_original_file_and_writes_real_storage_path():
    inserted_rows = []
    supa = _supa_upload_succeeds(inserted_rows=inserted_rows)

    with patch("api._require_auth", return_value=_fake_user("user-42")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False)), \
         patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED-BLOB") as mock_encrypt, \
         patch("openai.OpenAI", new=_fake_openai_client()), \
         patch("api.UsageService.consume", new=AsyncMock()):
        await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(),
            _upload_file("tuzba.pdf", "application/pdf", content=b"original raw pdf bytes"),
            authorization="Bearer test-token",
        )

    mock_encrypt.assert_called_once_with(b"original raw pdf bytes")
    supa.storage.from_.assert_called_once_with("intake-dokumenti")
    supa.storage.from_.return_value.upload.assert_called_once()
    upload_kwargs = supa.storage.from_.return_value.upload.call_args.kwargs
    assert upload_kwargs["file"] == b"ENCRYPTED-BLOB"

    assert len(inserted_rows) == 1
    storage_path = inserted_rows[0]["storage_path"]
    assert storage_path == upload_kwargs["path"]
    assert storage_path.startswith("user-42/pred-1/")
    assert storage_path.endswith(".pdf")
    assert not storage_path.startswith("session/")  # not the old non-dereferenceable label


@pytest.mark.anyio
async def test_upload_still_succeeds_and_falls_back_to_session_label_when_storage_upload_fails():
    inserted_rows = []
    supa = _supa_upload_succeeds(inserted_rows=inserted_rows)
    supa.storage.from_.return_value.upload = MagicMock(side_effect=Exception("storage bucket unreachable"))

    with patch("api._require_auth", return_value=_fake_user("user-42")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False)), \
         patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED-BLOB"), \
         patch("openai.OpenAI", new=_fake_openai_client()), \
         patch("api.UsageService.consume", new=AsyncMock()):
        result = await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(),
            _upload_file("tuzba.pdf", "application/pdf"),
            authorization="Bearer test-token",
        )

    assert result is not None  # request completes normally — best-effort storage never blocks the flow
    assert len(inserted_rows) == 1
    storage_path = inserted_rows[0]["storage_path"]
    assert storage_path.startswith("session/")  # honest fallback, not a value that looks like success
