# -*- coding: utf-8 -*-
"""
Final Beta Gate — F6 (HIGH): api.py::predmet_upload_auto_analyze charged the
"predmet_upload_ai" credit unconditionally right after its 3 parallel GPT
calls, BEFORE checking whether any of them actually succeeded. During a
sustained OpenAI outage, all 3 fail, the endpoint still returns HTTP 200
(auto_analyzed: false, no content produced) but the credit stays spent.
UsageService.refund() already exists and is used by /api/pitanje for the
identical "consume() pre-deducted, then the real work failed" shape — this
applies that same pattern here: refund only fires when ALL 3 calls failed
(a partial success, e.g. hronologija failed but procena succeeded, still
produced real value and is correctly still charged).

Mirrors tests/test_intake_original_file_storage.py's api.py auth/upload
mocking pattern.
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


def _fake_openai_client_all_fail():
    """Simulates a total OpenAI outage: every chat.completions.create() call
    raises. A plain Exception (not one of llm_retry's 4 retryable OpenAI
    exception types) so tenacity does not retry/sleep in the test."""
    client = MagicMock()
    client.chat.completions.create = MagicMock(side_effect=RuntimeError("openai outage"))
    return MagicMock(return_value=client)


def _fake_openai_client_partial_success():
    """procena succeeds, hronologija/metapodaci fail -- must NOT refund."""
    ok_resp = MagicMock()
    ok_resp.choices = [MagicMock(message=MagicMock(content="Procena teksta."))]

    calls = {"n": 0}

    def _create(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return ok_resp
        raise RuntimeError("openai outage")

    client = MagicMock()
    client.chat.completions.create = MagicMock(side_effect=_create)
    return MagicMock(return_value=client)


def _supa_upload_succeeds(predmet_id: str = "pred-1", inserted_rows: list = None):
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
async def test_upload_refunds_credit_when_all_three_ai_calls_fail():
    inserted_rows = []
    supa = _supa_upload_succeeds(inserted_rows=inserted_rows)

    with patch("api._require_auth", return_value=_fake_user("user-42")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False, None, None)), \
         patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED-BLOB"), \
         patch("openai.OpenAI", new=_fake_openai_client_all_fail()), \
         patch("api.UsageService.consume", new=AsyncMock()) as mock_consume, \
         patch("api.UsageService.refund", new=AsyncMock()) as mock_refund:
        await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(),
            _upload_file("tuzba.pdf", "application/pdf"),
            authorization="Bearer test-token",
        )

    mock_consume.assert_called_once()
    assert mock_consume.call_args.args[2] == "predmet_upload_ai"
    mock_refund.assert_called_once()
    assert mock_refund.call_args.args[2] == "predmet_upload_ai"


@pytest.mark.anyio
async def test_upload_does_not_refund_on_partial_ai_success():
    inserted_rows = []
    supa = _supa_upload_succeeds(inserted_rows=inserted_rows)

    with patch("api._require_auth", return_value=_fake_user("user-42")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False, None, None)), \
         patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED-BLOB"), \
         patch("openai.OpenAI", new=_fake_openai_client_partial_success()), \
         patch("api.UsageService.consume", new=AsyncMock()) as mock_consume, \
         patch("api.UsageService.refund", new=AsyncMock()) as mock_refund:
        await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(),
            _upload_file("tuzba.pdf", "application/pdf"),
            authorization="Bearer test-token",
        )

    mock_consume.assert_called_once()
    mock_refund.assert_not_called()
