# -*- coding: utf-8 -*-
"""
Tests for Phase 5.1 — Više pravnih oblasti (routers/oblasti.py).
Pokriva: krivicno, privredno, radno endpoints + system prompt sadržaj + request validacija.

Patching strategija: koristimo module-level wrappers (_retrieve, _pii_strip, _gpt_call)
u routers/oblasti.py da bi patch radio i unutar asyncio.to_thread niti.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-128bit")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _mock_usage_service():
    """Testi pozivaju route funkcije direktno (bez FastAPI Depends), pa
    endpoint-ovo eksplicitno await UsageService.consume(...) u telu funkcije
    izvršava se stvarno. feature_registry tabela nije seed-ovana u test okruženju
    (nema pravu Supabase konekciju), pa bez ovog patch-a get_policy() baca
    RuntimeError za svaki feature_key. Ovo NE testira UsageService/Registry —
    to je pokriveno posebnim testovima za shared/usage.py — ovde samo osigurava
    da testovi ostanu fokusirani na GPT/oblast logiku koju stvarno provjeravaju."""
    with patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        yield


def _fake_request(path="/api/oblasti/krivicno"):
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "uid-advokat-001", "email": "a@a.rs", "role": "advokat"}


def _mock_retrieve(confidence="HIGH", top_score=0.87):
    docs = [
        "Krivični zakonik čl. 208 — prevara: Ko u nameri da sebi ili drugom pribavi protivpravnu imovinsku korist...",
        "KZ čl. 209 — teška prevara: Ako je delo iz čl. 208 učinjeno od strane organizovane kriminalne grupe...",
        "ZKP čl. 5 — Zabranjena dokazna sredstva — osnovna načela krivičnog postupka u Republici Srbiji.",
    ]
    meta = {
        "confidence":     confidence,
        "top_score":      top_score,
        "top_article":    "čl. 208",
        "top_law":        "KZ",
        "doc_passages":   [],
        "praksa_matches": [],
    }
    return (docs, meta)


# ════════════════════════════════════════════════════════════════════════════════
# Request model validacija
# ════════════════════════════════════════════════════════════════════════════════

def test_oblast_pitanje_req_valid():
    from routers.oblasti import OblastPitanjeReq
    req = OblastPitanjeReq(pitanje="Koja je kazna za prevaru?")
    assert req.pitanje == "Koja je kazna za prevaru?"
    assert req.history is None


def test_oblast_pitanje_req_prekratko():
    from pydantic import ValidationError
    from routers.oblasti import OblastPitanjeReq
    with pytest.raises(ValidationError):
        OblastPitanjeReq(pitanje="ab")


def test_oblast_pitanje_req_predugacko():
    from pydantic import ValidationError
    from routers.oblasti import OblastPitanjeReq
    with pytest.raises(ValidationError):
        OblastPitanjeReq(pitanje="x" * 2001)


def test_oblast_pitanje_req_sa_history():
    from routers.oblasti import OblastPitanjeReq
    req = OblastPitanjeReq(
        pitanje="Koji su rokovi za žalbu?",
        history=[{"q": "Prethodno pitanje", "a": "Prethodni odgovor"}],
    )
    assert len(req.history) == 1


# ════════════════════════════════════════════════════════════════════════════════
# System prompt sadržaj — provjere ključnih pravnih elemenata
# ════════════════════════════════════════════════════════════════════════════════

def test_krivicno_prompt_sadrzi_kz():
    from routers.oblasti import SYSTEM_PROMPT_KRIVICNO
    assert "KZ" in SYSTEM_PROMPT_KRIVICNO
    assert "Krivični zakonik" in SYSTEM_PROMPT_KRIVICNO


def test_krivicno_prompt_sadrzi_zkp():
    from routers.oblasti import SYSTEM_PROMPT_KRIVICNO
    assert "ZKP" in SYSTEM_PROMPT_KRIVICNO


def test_krivicno_prompt_sadrzi_strukturu():
    from routers.oblasti import SYSTEM_PROMPT_KRIVICNO
    assert "HIJERARHIJA IZVORA" in SYSTEM_PROMPT_KRIVICNO
    assert "KRIVIČNOPRAVNA ANALIZA" in SYSTEM_PROMPT_KRIVICNO
    assert "PRAVNI ZAKLJUČAK" in SYSTEM_PROMPT_KRIVICNO


def test_privredno_prompt_sadrzi_zpd():
    from routers.oblasti import SYSTEM_PROMPT_PRIVREDNO
    assert "ZPD" in SYSTEM_PROMPT_PRIVREDNO
    assert "privrednim društvima" in SYSTEM_PROMPT_PRIVREDNO


def test_privredno_prompt_sadrzi_stecaj():
    from routers.oblasti import SYSTEM_PROMPT_PRIVREDNO
    assert "stečaj" in SYSTEM_PROMPT_PRIVREDNO.lower()


def test_privredno_prompt_sadrzi_strukturu():
    from routers.oblasti import SYSTEM_PROMPT_PRIVREDNO
    assert "HIJERARHIJA IZVORA" in SYSTEM_PROMPT_PRIVREDNO
    assert "PRIVREDNOPRAVNA ANALIZA" in SYSTEM_PROMPT_PRIVREDNO
    assert "PRAVNI ZAKLJUČAK" in SYSTEM_PROMPT_PRIVREDNO


def test_radno_prompt_sadrzi_zr():
    from routers.oblasti import SYSTEM_PROMPT_RADNO
    assert "ZR" in SYSTEM_PROMPT_RADNO
    assert "Zakon o radu" in SYSTEM_PROMPT_RADNO


def test_radno_prompt_sadrzi_otkaz():
    from routers.oblasti import SYSTEM_PROMPT_RADNO
    assert "otkaz" in SYSTEM_PROMPT_RADNO.lower()


def test_radno_prompt_sadrzi_strukturu():
    from routers.oblasti import SYSTEM_PROMPT_RADNO
    assert "HIJERARHIJA IZVORA" in SYSTEM_PROMPT_RADNO
    assert "RADNOPRAVNA ANALIZA" in SYSTEM_PROMPT_RADNO
    assert "PRAVA I OBAVEZE" in SYSTEM_PROMPT_RADNO


def test_svi_prompti_sadrze_antifab():
    from routers.oblasti import SYSTEM_PROMPT_KRIVICNO, SYSTEM_PROMPT_PRIVREDNO, SYSTEM_PROMPT_RADNO
    for prompt in [SYSTEM_PROMPT_KRIVICNO, SYSTEM_PROMPT_PRIVREDNO, SYSTEM_PROMPT_RADNO]:
        assert "ZABRANJENO" in prompt


# ════════════════════════════════════════════════════════════════════════════════
# POST /api/oblasti/krivicno
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_krivicno_uspesno_high_confidence():
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Koja je kazna za krivično delo prevare po KZ?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", return_value="Ovo je testni pravni odgovor."):
        result = await pitanje_krivicno(req, _fake_request(), _user())

    assert result["status"] == "success"
    assert result["oblast"] == "krivicno"
    assert result["confidence"] == "HIGH"
    assert isinstance(result["data"], str)
    assert len(result["data"]) > 10
    assert "Pravna napomena" in result["data"]


@pytest.mark.anyio
async def test_krivicno_low_confidence_ne_zove_gpt():
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Neko pitanje van baze zakona?")
    gpt_mock = MagicMock()

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve(confidence="LOW", top_score=0.21)), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", gpt_mock):
        result = await pitanje_krivicno(req, _fake_request(), _user())
        gpt_mock.assert_not_called()

    assert result["confidence"] == "LOW"
    assert "NISKA" in result["data"]


@pytest.mark.anyio
async def test_krivicno_medium_confidence_sadrzi_hedge():
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Koji rok zastare za krivično gonjenje?")
    captured = {}

    def _capture_gpt(sistem_prompt, user_content, max_tokens):
        captured["user_content"] = user_content
        return "Odgovor sa hedgom."

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve(confidence="MEDIUM", top_score=0.55)), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", side_effect=_capture_gpt):
        result = await pitanje_krivicno(req, _fake_request(), _user())

    uc = captured.get("user_content", "")
    assert "POUZDANOST" in uc and "SREDNJA" in uc


@pytest.mark.anyio
async def test_krivicno_prazan_kontekst_vraca_low():
    """Ako retrieve vrati prazne dokumente → LOW, ne poziva GPT."""
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Pitanje bez konteksta u bazi?")
    prazna_meta = {
        "confidence": "HIGH", "top_score": 0.90,
        "top_article": "", "top_law": "", "doc_passages": [], "praksa_matches": [],
    }
    gpt_mock = MagicMock()

    with patch("routers.oblasti._retrieve", return_value=([], prazna_meta)), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", gpt_mock):
        result = await pitanje_krivicno(req, _fake_request(), _user())
        gpt_mock.assert_not_called()

    assert result["confidence"] == "LOW"


# ════════════════════════════════════════════════════════════════════════════════
# POST /api/oblasti/privredno
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_privredno_uspesno():
    from routers.oblasti import pitanje_privredno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Kako se osniva DOO u Srbiji?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", return_value="DOO se osniva upisom u APR..."):
        result = await pitanje_privredno(req, _fake_request("/api/oblasti/privredno"), _user())

    assert result["status"] == "success"
    assert result["oblast"] == "privredno"
    assert "DOO se osniva" in result["data"]


@pytest.mark.anyio
async def test_privredno_koristi_privredno_prompt():
    """Verifikuj da privredno endpoint šalje SYSTEM_PROMPT_PRIVREDNO GPT-u."""
    from routers.oblasti import pitanje_privredno, OblastPitanjeReq, SYSTEM_PROMPT_PRIVREDNO

    req = OblastPitanjeReq(pitanje="Šta je reorganizacija u stečaju?")
    captured = {}

    def _capture(sistem_prompt, user_content, max_tokens):
        captured["sistem_prompt"] = sistem_prompt
        return "Odgovor."

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", side_effect=_capture):
        await pitanje_privredno(req, _fake_request(), _user())

    assert captured.get("sistem_prompt") == SYSTEM_PROMPT_PRIVREDNO


@pytest.mark.anyio
async def test_privredno_low_confidence():
    from routers.oblasti import pitanje_privredno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Pitanje izvan baze?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve(confidence="LOW", top_score=0.18)), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x):
        result = await pitanje_privredno(req, _fake_request(), _user())

    assert result["confidence"] == "LOW"
    assert result["oblast"] == "privredno"


# ════════════════════════════════════════════════════════════════════════════════
# POST /api/oblasti/radno
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_radno_uspesno():
    from routers.oblasti import pitanje_radno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Koja su prava zaposlenog pri otkazu ugovora o radu?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", return_value="Zaposleni ima pravo na otkazni rok..."):
        result = await pitanje_radno(req, _fake_request("/api/oblasti/radno"), _user())

    assert result["status"] == "success"
    assert result["oblast"] == "radno"
    assert "otkazni rok" in result["data"]


@pytest.mark.anyio
async def test_radno_koristi_radno_prompt():
    """Verifikuj da radno endpoint šalje SYSTEM_PROMPT_RADNO GPT-u."""
    from routers.oblasti import pitanje_radno, OblastPitanjeReq, SYSTEM_PROMPT_RADNO

    req = OblastPitanjeReq(pitanje="Koji su uslovi za otkaz ugovora?")
    captured = {}

    def _capture(sistem_prompt, user_content, max_tokens):
        captured["sistem_prompt"] = sistem_prompt
        return "Odgovor."

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", side_effect=_capture):
        await pitanje_radno(req, _fake_request(), _user())

    assert captured.get("sistem_prompt") == SYSTEM_PROMPT_RADNO


@pytest.mark.anyio
async def test_radno_low_confidence():
    from routers.oblasti import pitanje_radno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Nešto van baze?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve(confidence="LOW", top_score=0.15)), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x):
        result = await pitanje_radno(req, _fake_request(), _user())

    assert result["confidence"] == "LOW"
    assert result["oblast"] == "radno"


# ════════════════════════════════════════════════════════════════════════════════
# Struktura odgovora — zajednička provjera
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_odgovor_sadrzi_disclaimer():
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Test pitanje za disclaimer provjeru?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", return_value="Odgovor."):
        result = await pitanje_krivicno(req, _fake_request(), _user())

    assert "Pravna napomena" in result["data"]
    assert "Vindex AI" in result["data"]


@pytest.mark.anyio
async def test_odgovor_sadrzi_sve_metapodatke():
    from routers.oblasti import pitanje_radno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Test metapodataka u odgovoru?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", return_value="Odgovor."):
        result = await pitanje_radno(req, _fake_request(), _user())

    assert "status"      in result
    assert "oblast"      in result
    assert "data"        in result
    assert "confidence"  in result
    assert "top_score"   in result
    assert "top_article" in result
    assert "top_law"     in result


@pytest.mark.anyio
async def test_history_se_ugradjuje_u_kontekst():
    """Historia razgovora mora biti u user_content poslatom GPT-u."""
    from routers.oblasti import pitanje_privredno, OblastPitanjeReq

    req = OblastPitanjeReq(
        pitanje="Nastavak pitanja o DOO?",
        history=[{"q": "Kako se osniva DOO?", "a": "DOO se osniva upisom u APR."}],
    )
    captured = {}

    def _capture(sistem_prompt, user_content, max_tokens):
        captured["user_content"] = user_content
        return "Odgovor."

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", side_effect=_capture):
        await pitanje_privredno(req, _fake_request(), _user())

    uc = captured.get("user_content", "")
    assert "ISTORIJA RAZGOVORA" in uc
    assert "DOO se osniva" in uc


@pytest.mark.anyio
async def test_retrieve_greska_503():
    """Ako _retrieve baci exception → 503 HTTPException."""
    from fastapi import HTTPException
    from routers.oblasti import pitanje_krivicno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Pitanje za test greške u retrieve?")

    with patch("routers.oblasti._retrieve", side_effect=Exception("Pinecone timeout")), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x):
        with pytest.raises(HTTPException) as exc:
            await pitanje_krivicno(req, _fake_request(), _user())

    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_gpt_greska_503():
    """Ako _gpt_call baci exception → 503 HTTPException."""
    from fastapi import HTTPException
    from routers.oblasti import pitanje_radno, OblastPitanjeReq

    req = OblastPitanjeReq(pitanje="Pitanje za test GPT greške?")

    with patch("routers.oblasti._retrieve", return_value=_mock_retrieve()), \
         patch("routers.oblasti._pii_strip", side_effect=lambda x: x), \
         patch("routers.oblasti._gpt_call", side_effect=Exception("OpenAI rate limit")):
        with pytest.raises(HTTPException) as exc:
            await pitanje_radno(req, _fake_request(), _user())

    assert exc.value.status_code == 503


# ════════════════════════════════════════════════════════════════════════════════
# _OBLASTI mapa — integritet konfiguracije
# ════════════════════════════════════════════════════════════════════════════════

def test_oblasti_mapa_ima_sve_tri():
    from routers.oblasti import _OBLASTI
    assert "krivicno"  in _OBLASTI
    assert "privredno" in _OBLASTI
    assert "radno"     in _OBLASTI


def test_oblasti_mapa_polja():
    from routers.oblasti import _OBLASTI
    for kljuc, cfg in _OBLASTI.items():
        assert "naziv"      in cfg, f"{kljuc}: nedostaje naziv"
        assert "prompt"     in cfg, f"{kljuc}: nedostaje prompt"
        assert "max_tokens" in cfg, f"{kljuc}: nedostaje max_tokens"
        assert cfg["max_tokens"] >= 1000
