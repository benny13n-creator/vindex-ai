# -*- coding: utf-8 -*-
"""
Regression tests — routers/doc_templates.py::sacuvaj_dokument (SEC-001).

NIGHTLY REPAIR (2026-07-24), Faza 1 item 3: POST /api/doc-templates/sacuvaj
inserted into predmet_beleske using req.predmet_id with NO check that the
case belonged to the calling user -- any authenticated user could write a
note into another user's case file by guessing/obtaining a predmet_id.
Same vulnerability class as SEC-001 (already fixed elsewhere: api.py's
dodaj_belesku, shared/voice_tools.py's _tool_dodaj_belesku), just missed
in this one file.

Pure unit tests -- no live Supabase.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request as StarletteRequest  # noqa: E402
import routers.doc_templates as doc_templates  # noqa: E402


def _req() -> StarletteRequest:
    """Real starlette Request -- @limiter.limit radi isinstance(request, Request)
    proveru i čita request.client za rate-limit ključ."""
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/api/doc-templates/sacuvaj",
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "insert", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


def test_sacuvaj_rejects_unowned_predmet_id():
    select_chain = _chain(MagicMock(data=None))
    supa = MagicMock()
    supa.table.return_value = select_chain

    req = doc_templates.SacuvajReq(predmet_id="tudje-ili-nepostojece", naziv="Tuzba", sadrzaj="Sadrzaj dokumenta ovde.")
    with patch.object(doc_templates, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(doc_templates.sacuvaj_dokument(request=_req(), req=req, user={"user_id": "u1", "email": "a@b.com"}))

    assert exc_info.value.status_code == 404
    # Insert se NIKAD ne sme desiti kad vlasništvo nije potvrđeno.
    select_chain.insert.assert_not_called()


def test_sacuvaj_succeeds_for_owned_predmet():
    select_chain = _chain(MagicMock(data={"id": "p1"}))
    insert_chain = _chain(MagicMock(data=[{"id": "beleska-1"}]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else insert_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    req = doc_templates.SacuvajReq(predmet_id="p1", naziv="Tuzba", sadrzaj="Sadrzaj dokumenta ovde.")
    with patch.object(doc_templates, "_get_supa", return_value=supa):
        result = asyncio.run(doc_templates.sacuvaj_dokument(request=_req(), req=req, user={"user_id": "u1", "email": "a@b.com"}))

    assert result["ok"] is True
    assert result["beleska_id"] == "beleska-1"
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["predmet_id"] == "p1"
    assert inserted["user_id"] == "u1"


def test_sacuvaj_ownership_check_scoped_to_calling_user():
    """Provera mora da filtrira i po predmet_id I po user_id -- ne samo da
    predmet postoji negde u bazi."""
    select_chain = _chain(MagicMock(data=None))
    supa = MagicMock()
    supa.table.return_value = select_chain

    req = doc_templates.SacuvajReq(predmet_id="p1", naziv="Tuzba", sadrzaj="Sadrzaj dokumenta ovde.")
    with patch.object(doc_templates, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException):
            asyncio.run(doc_templates.sacuvaj_dokument(request=_req(), req=req, user={"user_id": "napadac", "email": "x@y.com"}))

    eq_calls = [c.args for c in select_chain.eq.call_args_list]
    assert ("id", "p1") in eq_calls
    assert ("user_id", "napadac") in eq_calls
