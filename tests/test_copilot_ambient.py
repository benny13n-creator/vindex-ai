# -*- coding: utf-8 -*-
"""
Regression tests — KORAK C: Ambient Context & Word/Browser Copilot (2026-07-24).

Pokriva:
  1. services/ambient_analyzer.py — kratak pasus se preskače bez LLM poziva,
     RAG timeout/greška degradira na prazan kontekst (fail-soft), LLM
     timeout/greška degradira na praznu listu sugestija (fail-soft),
     parsiranje odbacuje nevalidne/nepoznate tipove sugestija i seče na 3.
  2. routers/copilot_ambient.py — SEC-001 vlasništvo nad predmet_id (404 za
     tuđi/nepostojeći predmet), uspešan poziv bez predmet_id-a, i
     UsageService.consume-ov 429 (dnevni limit) SE propagira ka klijentu
     (namerno nije progutan — to je stvarna budžetska zaštita, ne
     kozmetički log).

Pure unit/integration tests -- no live Supabase, no OpenAI.
"""
import asyncio
import os
import sys
import time as _time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════════════
# 1. services/ambient_analyzer.py
# ═══════════════════════════════════════════════════════════════════════════

def test_short_passage_skips_analysis_entirely():
    import services.ambient_analyzer as amb

    with patch.object(amb, "_brzi_rag_kontekst", new=AsyncMock()) as rag_mock, \
         patch.object(amb, "_pozovi_sugestije_api") as llm_mock:
        result = asyncio.run(amb.analyze_paragraph("Prekratko.", user_id="u1"))

    assert result["sugestije"] == []
    rag_mock.assert_not_called()
    llm_mock.assert_not_called()


def test_rag_failure_degrades_to_empty_context_not_exception():
    import services.ambient_analyzer as amb
    pasus = "Ovo je dovoljno dug pasus da prođe minimalnu proveru dužine za analizu."

    with patch("app.services.retrieve.retrieve_documents", side_effect=RuntimeError("pinecone down")), \
         patch("app.services.retrieve.retrieve_sudska_praksa", side_effect=RuntimeError("pinecone down")):
        kontekst = asyncio.run(amb._brzi_rag_kontekst(pasus))

    assert kontekst == ""


def test_rag_timeout_degrades_to_empty_context():
    """asyncio.to_thread pokreće blokirajući poziv u REALNOM OS thread-u --
    cancel na asyncio nivou (wait_for timeout) ne prekida taj thread, samo
    prestaje da ga čeka. Zato test koristi kratak (0.3s) stvarni sleep, ne
    proizvoljno dug -- dovoljno da wait_for(timeout=0.05) sigurno istekne
    pre njega, a da ne drži pytest worker thread predugo."""
    import services.ambient_analyzer as amb

    with patch.object(amb, "_RAG_TIMEOUT_SECONDS", 0.05), \
         patch("app.services.retrieve.retrieve_documents", side_effect=lambda *a, **k: _time.sleep(0.3) or ([], {})), \
         patch("app.services.retrieve.retrieve_sudska_praksa", return_value=[]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=[]):
        kontekst = asyncio.run(amb._brzi_rag_kontekst("dovoljno dug pasus za test timeout ponašanja ovde"))

    assert kontekst == ""


def test_full_analyze_paragraph_never_raises_on_llm_failure():
    import services.ambient_analyzer as amb
    pasus = "Ugovor o radu je raskinut bez poštovanja otkaznog roka predviđenog zakonom."

    with patch.object(amb, "_brzi_rag_kontekst", new=AsyncMock(return_value="")), \
         patch.object(amb, "_pozovi_sugestije_api", side_effect=RuntimeError("openai down")):
        result = asyncio.run(amb.analyze_paragraph(pasus, user_id="u1"))

    assert result["sugestije"] == []
    assert "trajanje_ms" in result


def test_full_analyze_paragraph_returns_parsed_suggestions():
    import services.ambient_analyzer as amb
    pasus = "Ugovor o radu je raskinut bez poštovanja otkaznog roka predviđenog zakonom."
    raw_llm = (
        '{"sugestije": [{"tip": "clan_zakona", "tekst": "Proverite čl. 179 ZR.", "izvor": "ZR čl. 179"}]}'
    )

    with patch.object(amb, "_brzi_rag_kontekst", new=AsyncMock(return_value="Zakon o radu, čl. 179...")), \
         patch.object(amb, "_pozovi_sugestije_api", return_value=raw_llm):
        result = asyncio.run(amb.analyze_paragraph(pasus, user_id="u1"))

    assert len(result["sugestije"]) == 1
    assert result["sugestije"][0]["tip"] == "clan_zakona"
    assert result["sugestije"][0]["izvor"] == "ZR čl. 179"


def test_parsiraj_sugestije_drops_invalid_and_caps_at_three():
    import services.ambient_analyzer as amb
    raw = (
        '{"sugestije": ['
        '{"tip": "clan_zakona", "tekst": "A", "izvor": "1"},'
        '{"tip": "nepoznat_tip", "tekst": "B", "izvor": "2"},'
        '{"tip": "upozorenje", "tekst": "", "izvor": "3"},'
        '{"tip": "sudska_praksa", "tekst": "C", "izvor": "4"},'
        '{"tip": "upozorenje", "tekst": "D", "izvor": "5"},'
        '{"tip": "clan_zakona", "tekst": "E", "izvor": "6"}'
        ']}'
    )
    sugestije = amb._parsiraj_sugestije(raw)
    # "nepoznat_tip" (nevažeći tip) i prazan tekst su odbačeni pre sečenja na 3
    assert len(sugestije) == 3
    assert all(s["tip"] in ("clan_zakona", "sudska_praksa", "upozorenje") for s in sugestije)
    assert all(s["tekst"] for s in sugestije)


def test_parsiraj_sugestije_malformed_json_returns_empty_list():
    import services.ambient_analyzer as amb
    assert amb._parsiraj_sugestije("not valid json{{{") == []
    assert amb._parsiraj_sugestije('{"nesto_drugo": []}') == []
    assert amb._parsiraj_sugestije('{"sugestije": "not a list"}') == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. routers/copilot_ambient.py (integracija preko TestClient-a)
# ═══════════════════════════════════════════════════════════════════════════

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.deps import get_current_user as _shared_get_current_user  # noqa: E402
import shared.feature_registry as _fr  # noqa: E402

_FAKE_USER = {"user_id": "test-user-id", "email": "test@test.com"}
_FAKE_PROFILE = {
    "credits_remaining": 100, "is_pro": True,
    "subscription_type": "professional", "addons": [], "subscription_expires_at": None,
}


@pytest.fixture(autouse=True)
def _setup_overrides():
    api.app.dependency_overrides[_shared_get_current_user] = lambda: _FAKE_USER
    _fr._CACHE["copilot_ambient"] = {
        "feature_key": "copilot_ambient", "aktivno": True, "status": "ACTIVE",
        "addon": None, "minimum_plan": None, "krediti": 0,
        "dnevni_limit": 200, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o-mini", "estimated_cost_usd": 0.003,
    }
    _fr._CACHE_LOADED_AT = _time.monotonic()
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE):
        yield
    api.app.dependency_overrides.pop(_shared_get_current_user, None)


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app, raise_server_exceptions=True)


def test_analyze_without_predmet_id_succeeds(client):
    fake_result = {"sugestije": [], "trajanje_ms": 42}
    with patch("services.ambient_analyzer.analyze_paragraph", new=AsyncMock(return_value=fake_result)), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=100)):
        resp = client.post("/api/copilot/ambient/analyze", json={
            "tekst": "Ovo je dovoljno dug pasus teksta za testiranje ambijentalne analize ovde.",
        })

    assert resp.status_code == 200
    assert resp.json() == fake_result


def test_analyze_with_unowned_predmet_id_returns_404(client):
    select_chain = MagicMock()
    for m in ("select", "eq"):
        setattr(select_chain, m, MagicMock(return_value=select_chain))
    select_chain.maybe_single = MagicMock(return_value=select_chain)
    select_chain.execute = MagicMock(return_value=MagicMock(data=None))

    with patch("routers.copilot_ambient._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = select_chain
        resp = client.post("/api/copilot/ambient/analyze", json={
            "tekst": "Ovo je dovoljno dug pasus teksta za testiranje ambijentalne analize ovde.",
            "predmet_id": "tudje-ili-nepostojece",
        })

    assert resp.status_code == 404


def test_analyze_with_owned_predmet_id_succeeds(client):
    select_chain = MagicMock()
    for m in ("select", "eq"):
        setattr(select_chain, m, MagicMock(return_value=select_chain))
    select_chain.maybe_single = MagicMock(return_value=select_chain)
    select_chain.execute = MagicMock(return_value=MagicMock(data={"id": "p1"}))

    fake_result = {"sugestije": [{"tip": "upozorenje", "tekst": "X", "izvor": ""}], "trajanje_ms": 10}

    with patch("routers.copilot_ambient._get_supa") as mock_supa, \
         patch("services.ambient_analyzer.analyze_paragraph", new=AsyncMock(return_value=fake_result)) as analyze_mock, \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=100)):
        mock_supa.return_value.table.return_value = select_chain
        resp = client.post("/api/copilot/ambient/analyze", json={
            "tekst": "Ovo je dovoljno dug pasus teksta za testiranje ambijentalne analize ovde.",
            "predmet_id": "p1",
            "tip_dokumenta": "tuzba",
        })

    assert resp.status_code == 200
    assert resp.json() == fake_result
    analyze_mock.assert_awaited_once()
    _, kwargs = analyze_mock.call_args
    assert kwargs["predmet_id"] == "p1"
    assert kwargs["tip_dokumenta"] == "tuzba"


def test_daily_limit_exceeded_propagates_as_429(client):
    """UsageService.consume baca HTTPException(429) kad je dnevni_limit
    dostignut -- ovo NE sme biti progutano (v. routers/copilot_ambient.py
    komentar), to je stvarna budžetska zaštita definisana u migraciji 083."""
    from fastapi import HTTPException

    fake_result = {"sugestije": [], "trajanje_ms": 5}
    with patch("services.ambient_analyzer.analyze_paragraph", new=AsyncMock(return_value=fake_result)), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(
             side_effect=HTTPException(status_code=429, detail={"code": "DNEVNI_LIMIT"})
         )):
        resp = client.post("/api/copilot/ambient/analyze", json={
            "tekst": "Ovo je dovoljno dug pasus teksta za testiranje ambijentalne analize ovde.",
        })

    assert resp.status_code == 429


def test_analyze_rejects_empty_tekst(client):
    resp = client.post("/api/copilot/ambient/analyze", json={"tekst": ""})
    assert resp.status_code == 422


def test_analyze_rejects_oversized_tekst(client):
    resp = client.post("/api/copilot/ambient/analyze", json={"tekst": "x" * 5000})
    assert resp.status_code == 422
