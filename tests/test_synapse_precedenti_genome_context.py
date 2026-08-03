# -*- coding: utf-8 -*-
"""
Project Synapse (2026-08-03): routers/precedenti.py (Firm Brain / Similar
Cases) never read the current case's own already-computed Case Genome
before synthesizing similarity to closed cases -- confirmed via a full
cognitive audit (grepped for "case_dna": zero matches). Fixed by folding a
compact Genome summary into the same ctx_predmet string this endpoint
already builds -- purely additive context, no change to the similar-case
matching logic itself.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    scope = {
        "type": "http", "method": "GET", "headers": [], "query_string": b"",
        "path": "/api/precedenti/predmeti/pred-1", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope)


def _make_supa(predmet: dict, slicni: list):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            # First call: ownership + current predmet -- .select().eq("id",..).eq("user_id",..).execute()
            # Second call (by tip): .select().eq("user_id",..).eq("tip",..).neq("id",..).limit(10).execute()
            # Both share the same .eq().eq() mock node; they diverge at the
            # next call (.execute() vs .neq()), so both can be configured
            # independently on the same underlying chain.
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [predmet]
            t.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value.data = slicni
        elif name == "predmet_istorija":
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_hronologija":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa.table.side_effect = _table
    return supa


def _fake_gpt_response(text="Analiza teksta."):
    msg = MagicMock()
    msg.message.content = text
    resp = MagicMock()
    resp.choices = [msg]
    return resp


@pytest.mark.anyio
async def test_genome_summary_included_when_case_dna_present():
    from routers.precedenti import get_precedenti

    predmet = {
        "id": "pred-1", "naziv": "Test", "tip": "radno", "status": "aktivan", "oblast": "",
        "opis": "Opis predmeta",
        "case_dna": {
            "snaga_predmeta_procent": 68, "snaga_predmeta": "Srednja",
            "najslabija_tacka": {"rizik": "Nedostaje dokaz o otkazu"},
        },
    }
    slicni = [{"id": "pred-2", "naziv": "Sličan predmet", "tip": "radno", "status": "zatvoren", "opis": "x"}]
    supa = _make_supa(predmet, slicni)

    captured = {}

    def _capture_gpt(client, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.precedenti.get_supa", return_value=supa), \
         patch("routers.precedenti._pozovi_precedenti_api", side_effect=_capture_gpt), \
         patch("routers.precedenti.UsageService.consume", new=AsyncMock()):
        await get_precedenti(request=_fake_request(), predmet_id="pred-1", user={"user_id": "u1", "email": "a@b.rs"})

    user_ctx = captured["messages"][1]["content"]
    assert "Case Genome" in user_ctx
    assert "68%" in user_ctx
    assert "Nedostaje dokaz o otkazu" in user_ctx


@pytest.mark.anyio
async def test_no_genome_section_when_case_dna_absent():
    from routers.precedenti import get_precedenti

    predmet = {"id": "pred-1", "naziv": "Test", "tip": "radno", "status": "aktivan", "oblast": "",
               "opis": "Opis predmeta", "case_dna": None}
    slicni = [{"id": "pred-2", "naziv": "Sličan predmet", "tip": "radno", "status": "zatvoren", "opis": "x"}]
    supa = _make_supa(predmet, slicni)

    captured = {}

    def _capture_gpt(client, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.precedenti.get_supa", return_value=supa), \
         patch("routers.precedenti._pozovi_precedenti_api", side_effect=_capture_gpt), \
         patch("routers.precedenti.UsageService.consume", new=AsyncMock()):
        await get_precedenti(request=_fake_request(), predmet_id="pred-1", user={"user_id": "u1", "email": "a@b.rs"})

    user_ctx = captured["messages"][1]["content"]
    assert "Case Genome" not in user_ctx
