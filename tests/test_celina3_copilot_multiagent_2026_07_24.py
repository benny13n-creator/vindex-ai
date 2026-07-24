# -*- coding: utf-8 -*-
"""
Regression tests — Celina 3: Legal Assistant & Multi-Agent Engine
(Copilot, Chat & Legal Reasoning) (2026-07-24).

routers/chat.py NE POSTOJI u ovoj bazi koda -- "Chat" funkcionalnost su u
stvari api.py::/api/pitanje, /api/pitanje/stream, /api/bot/ask (koji interno
pozivaju main.py::ask_agent). "Multi-Agent Engine" iz naslova zadatka je
routers/multi_agent.py (6 specijalizovanih agenata), koji NIJE bio u
korisnikovoj eksplicitnoj listi fajlova ali direktno odgovara nazivu celine.

1. routers/copilot.py:
   - @llm_retry dodat na svih 8 direktnih GPT-4o-mini poziva (kroz zajednički
     _pozovi_gpt4o_mini wrapper) -- ranije NIJEDAN od njih nije imao retry,
     za razliku od main.py::_pozovi_openai (ima @llm_retry od Faze 2).
   - _sentry_capture dodat na sve prethodno tihe (samo logger) except blokove.
2. routers/multi_agent.py:
   - @llm_retry dodat na sva 3 direktna OpenAI poziva (auto-select ruter,
     glavni /run poziv, /run-parallel poziv) -- ranije NIJEDAN nije imao retry.
   - BUG FIX (2026-07-24, zatečen u kodu) sinhroni OpenAI() poziv preko
     asyncio.to_thread je već bio ispravljen pre ove celine; ovde je dodat
     samo retry sloj oko tih poziva.
   - _sentry_capture dodat na sve prethodno tihe except blokove.
3. routers/legal_reasoning.py:
   - Potvrđeno (ne menjano): Phase 0 je i dalje "wired to nothing" —
     founder-ova odluka od 2026-07-23. Test ispod je regresiona brana koja
     eksplicitno puca ako neko ubuduće tiho poveže LRE sa Copilot-om bez
     svesne odluke da promeni ovaj test.
4. api.py::/api/pitanje/stream:
   - Docstring je tvrdio "chunk po chunk" OpenAI streaming, a stvarna
     implementacija čeka KOMPLETAN guard-verifikovan odgovor pa ga veštački
     deli na 80-karakterne delove (namerna guard-complete arhitektura, ne
     bug). Docstring ispravljen da opisuje stvarno ponašanje; mrtav
     `from openai import OpenAI as _OAI` import uklonjen.
"""
import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _fake_chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


def _rate_limit_error():
    from openai import RateLimitError
    return RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)


# ─── 1a. copilot.py: _pozovi_gpt4o_mini — zajednički retry wrapper ─────────

def test_pozovi_gpt4o_mini_retries_rate_limit_do_uspeha():
    """Novi zajednički helper mora imati @llm_retry -- 2 prolazne greške pa uspeh."""
    from routers.copilot import _pozovi_gpt4o_mini

    calls = {"n": 0}

    def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response('{"ok": true}')

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_gpt4o_mini(oai, model="gpt-4o-mini", messages=[]))

    assert calls["n"] == 3
    assert out.choices[0].message.content == '{"ok": true}'


def test_oai_parse_json_koristi_retry_zasticen_wrapper():
    """_oai_parse_json (koristi ga _handle_naplati_radnju) mora ići kroz
    _pozovi_gpt4o_mini, ne kroz direktan nezaštićen poziv."""
    from routers.copilot import _oai_parse_json

    with patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(return_value=_fake_chat_response('{"sati":2}'))) as mock_call, \
         patch("openai.AsyncOpenAI"):
        out = asyncio.run(_oai_parse_json("system", "korisnicka poruka"))

    assert out == '{"sati":2}'
    assert mock_call.await_count == 1


# ─── 1b. copilot.py: _detect_intent — retry + graceful fallback ───────────

def test_detect_intent_gracefully_falls_back_posle_iscrpljenog_retry_ja():
    """Kad OpenAI konstantno vraća 429, llm_retry mora pokušati 3x (ne 1x),
    a zatim _detect_intent mora fail-soft vratiti PRAVNO_PITANJE (ne pući)."""
    from routers.copilot import _detect_intent

    calls = {"n": 0}

    def _side_effect(**kw):
        calls["n"] += 1
        raise _rate_limit_error()

    with patch("openai.AsyncOpenAI") as MockCls:
        MockCls.return_value.chat.completions.create = AsyncMock(side_effect=_side_effect)
        intent = asyncio.run(_detect_intent("Da li je zastarelo potraživanje iz 2019?"))

    assert intent == "PRAVNO_PITANJE"
    assert calls["n"] == 3  # dokazuje da je retry stvarno pokušao 3x, ne odustao na prvoj grešci


def test_detect_intent_uspeva_normalno_bez_greske():
    from routers.copilot import _detect_intent

    with patch("openai.AsyncOpenAI") as MockCls:
        MockCls.return_value.chat.completions.create = AsyncMock(
            return_value=_fake_chat_response("ZASTARELOST")
        )
        intent = asyncio.run(_detect_intent("Da li je zastarelo potraživanje?"))

    assert intent == "ZASTARELOST"


def test_detect_intent_nepoznata_rec_pada_na_ostalo():
    from routers.copilot import _detect_intent

    with patch("openai.AsyncOpenAI") as MockCls:
        MockCls.return_value.chat.completions.create = AsyncMock(
            return_value=_fake_chat_response("NEŠTO_NEPOZNATO")
        )
        intent = asyncio.run(_detect_intent("random poruka"))

    assert intent == "OSTALO"


# ─── 1c. copilot.py: Sentry sweep — strukturna provera ─────────────────────

def test_copilot_ima_sentry_i_retry_infrastrukturu_uvezenu():
    import routers.copilot as cp
    assert hasattr(cp, "_sentry_capture")
    assert hasattr(cp, "llm_retry")
    assert hasattr(cp, "_pozovi_gpt4o_mini")


def test_handle_akcija_rok_prijavljuje_db_gresku_na_sentry():
    """DB insert greška u _handle_akcija_rok ranije je samo logovana --
    sada mora ići i na _sentry_capture."""
    from routers.copilot import _handle_akcija_rok

    async def _fake_pozovi(oai, **kw):
        return _fake_chat_response(json.dumps({
            "dogadjaj": "Ročište", "datum_iso": "2026-08-01", "vaznost": "bitan",
        }))

    fake_supa = MagicMock()
    fake_supa.table.return_value.insert.return_value.execute.side_effect = Exception("db down")

    with patch("routers.copilot._pozovi_gpt4o_mini", side_effect=_fake_pozovi), \
         patch("openai.AsyncOpenAI"), \
         patch("routers.copilot._get_supa", return_value=fake_supa), \
         patch("routers.copilot._sentry_capture") as mock_sentry:
        result = asyncio.run(_handle_akcija_rok("Dodaj rok za ročište 1.8.2026", "pred-1", "user-1"))

    assert result["uspeh"] is False
    mock_sentry.assert_called_once()


def test_handle_ostalo_prijavljuje_gresku_na_sentry():
    from routers.copilot import _handle_ostalo

    with patch("openai.AsyncOpenAI") as MockCls, \
         patch("routers.copilot._sentry_capture") as mock_sentry:
        MockCls.return_value.chat.completions.create = AsyncMock(side_effect=Exception("boom"))
        result = asyncio.run(_handle_ostalo("Opšte pitanje", ""))

    assert result["tip"] == "OSTALO"
    mock_sentry.assert_called_once()


# ─── 2a. multi_agent.py: sync helperi — retry ──────────────────────────────

def _assert_sync_retries_then_succeeds(fn, *args):
    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response('{"agent":"research","razlog":"x"}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = fn(client, *args)

    assert calls["n"] == 3
    return out


def test_pozovi_router_api_retry():
    from routers.multi_agent import _pozovi_router_api
    _assert_sync_retries_then_succeeds(_pozovi_router_api, "neki zahtev")


def test_pozovi_agent_api_retry():
    from routers.multi_agent import _pozovi_agent_api
    _assert_sync_retries_then_succeeds(_pozovi_agent_api, "system prompt", "user msg")


def test_pozovi_para_api_retry_async():
    """/run-parallel koristi AsyncOpenAI -- retry mora raditi i ovde."""
    from routers.multi_agent import _pozovi_para_api

    calls = {"n": 0}

    def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response("odgovor agenta")

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_para_api(oai, "system prompt", "base msg"))

    assert calls["n"] == 3
    assert out.choices[0].message.content == "odgovor agenta"


def test_multi_agent_ima_sentry_i_retry_infrastrukturu_uvezenu():
    import routers.multi_agent as ma
    assert hasattr(ma, "_sentry_capture")
    assert hasattr(ma, "llm_retry")
    assert hasattr(ma, "_pozovi_router_api")
    assert hasattr(ma, "_pozovi_agent_api")
    assert hasattr(ma, "_pozovi_para_api")


# ─── 3. legal_reasoning.py: Phase 0 "wired to nothing" — regresiona brana ──

def test_legal_reasoning_ostaje_izolovan_od_copilota_i_multi_agenta():
    """Founder-ova odluka (2026-07-23): LRE Phase 0 se ne sme automatski
    pokretati niti imati downstream potrošača van svog sopstvenog routera.
    Celina 3, pitanje 2, eksplicitno je pitalo da li LRE treba povezati sa
    Copilot-om -- odgovor je NE dok founder ne da eksplicitno "go" za Phase 1+.
    Ovaj test puca namerno ako neko ubuduće tiho doda tu vezu."""
    import inspect
    import routers.copilot as copilot_mod
    import routers.multi_agent as ma_mod

    copilot_src = inspect.getsource(copilot_mod)
    ma_src = inspect.getsource(ma_mod)

    assert "legal_reasoning" not in copilot_src
    assert "generate_reasoning_graph" not in copilot_src
    assert "legal_reasoning" not in ma_src
    assert "generate_reasoning_graph" not in ma_src


def test_legal_reasoning_docstring_potvrdjuje_wired_to_nothing():
    import routers.legal_reasoning as lre
    assert "wired to nothing" in lre.__doc__


# ─── 4. api.py::/api/pitanje/stream — dokumentaciona ispravka ─────────────

def test_pitanje_stream_docstring_vise_ne_tvrdi_lazno_streaming():
    """Docstring je ranije tvrdio 'stream-uje chunk po chunk... bez čekanja
    na kompletan odgovor', što ne odgovara stvarnoj guard-complete arhitekturi
    (kompletan odgovor se čeka PRE prvog chunk-a). Ispravljeno da opisuje
    stvarno ponašanje."""
    import api
    doc = api.pitanje_stream.__doc__ or ""
    assert "NIJE token-level streaming" in doc or "nije token-level streaming" in doc.lower()
