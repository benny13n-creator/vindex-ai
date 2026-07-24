# -*- coding: utf-8 -*-
"""
Regression tests — KORAK D: Legal Thought Leadership & Content Agent (2026-07-24).

Pokriva:
  1. services/content_generator.py — anonimizacija (brojevi preko
     main._skini_pii + lokalna heuristika za imena), izvor fail-soft (nema
     javnog materijala → ok:False bez izuzetka), generisanje fail-soft na
     LLM grešku, etička provera je fail-CLOSED (tehnička greška → ok=None,
     NIKAD tretirano kao "prošlo"), uspešan tok upisuje nacrt.
  2. shared/social_connectors.py — čist format bez mrežnih poziva,
     nepoznata platforma baca ValueError.
  3. routers/marketing_agent.py — feature-gate, generisanje troši kredite
     SAMO na uspeh, HITL: /format je dostupan isključivo za već PRIHVAĆENE
     nacrte (409 za pending/rejected), ownership na accept/reject, dupli
     resolve odbijen.

Pure unit/integration tests -- no live Supabase, no OpenAI, no real network.
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


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "order", "limit", "insert", "update", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# 1. services/content_generator.py
# ═══════════════════════════════════════════════════════════════════════════

def test_anonimizuj_masks_names_and_numeric_pii():
    import services.content_generator as cg
    tekst = "Petar Petrović je podneo tužbu, JMBG 1234567890123, tel 0641234567."
    ocisceno = cg.anonimizuj(tekst)
    assert "Petrović" not in ocisceno
    assert "[STRANKA]" in ocisceno
    assert "1234567890123" not in ocisceno


def test_anonimizuj_preserves_legal_institution_names():
    """Heuristika za imena je namerno konzervativna -- ne sme da maskira
    nazive sudova/zakona koji takođe počinju velikim slovom."""
    import services.content_generator as cg
    tekst = "Vrhovni sud je potvrdio odluku Apelacionog suda po Zakonu o radu."
    ocisceno = cg.anonimizuj(tekst)
    assert "Vrhovni sud" in ocisceno
    assert "Apelacionog suda" in ocisceno or "Apelacioni" in ocisceno


def test_generate_post_returns_not_ok_when_no_public_source_found():
    import services.content_generator as cg

    with patch("app.services.retrieve.retrieve_sudska_praksa", return_value=[]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=[]):
        result = asyncio.run(cg.generate_post("sudska_praksa", "Radno pravo", "linkedin", "u1", MagicMock()))

    assert result["ok"] is False
    assert result["draft"] is None
    assert "javnog materijala" in result["error"]


def test_generate_post_unknown_izvor_tip_fails_soft():
    import services.content_generator as cg
    result = asyncio.run(cg.generate_post("nepoznat", "Radno pravo", "linkedin", "u1", MagicMock()))
    assert result["ok"] is False
    assert "Nepoznat izvor_tip" in result["error"]


def test_generate_post_never_raises_on_llm_generation_failure():
    import services.content_generator as cg

    fake_odluke = [{"decision_number": "Rev 1/26", "court": "VKS", "date": "2026-01-01",
                     "matter": "", "text": "Sud je odlučio...", "score": 0.9}]
    with patch("app.services.retrieve.retrieve_sudska_praksa", return_value=["raw"]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=fake_odluke), \
         patch.object(cg, "_pozovi_generisanje_api", side_effect=RuntimeError("openai down")):
        result = asyncio.run(cg.generate_post("sudska_praksa", "Radno pravo", "linkedin", "u1", MagicMock()))

    assert result["ok"] is False
    assert result["draft"] is None


def test_generate_post_success_full_flow_inserts_draft():
    import services.content_generator as cg

    fake_odluke = [{"decision_number": "Rev 1/26", "court": "VKS", "date": "2026-01-01",
                     "matter": "", "text": "Sud je odlučio...", "score": 0.9}]
    llm_raw = '{"naslov": "Naslov posta", "tekst": "Edukativan tekst o pravnom principu."}'
    etika_raw = '{"ok": true, "problemi": []}'
    insert_chain = _chain(MagicMock(data=[{"id": "draft1", "status": "pending"}]))
    supa = MagicMock()
    supa.table.return_value = insert_chain

    with patch("app.services.retrieve.retrieve_sudska_praksa", return_value=["raw"]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=fake_odluke), \
         patch.object(cg, "_pozovi_generisanje_api", return_value=llm_raw), \
         patch.object(cg, "_pozovi_etika_api", return_value=etika_raw):
        result = asyncio.run(cg.generate_post("sudska_praksa", "Radno pravo", "linkedin", "u1", supa))

    assert result["ok"] is True
    assert result["draft"]["id"] == "draft1"
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["etika_ok"] is True
    assert inserted["platforma"] == "linkedin"
    assert inserted["user_id"] == "u1"


def test_proveri_etiku_technical_failure_is_fail_closed_not_fail_open():
    """ok=None (tehnička greška) se NIKAD ne sme meriti kao ok=True u
    pozivaocu -- ovaj test zaključava da funkcija vraća None, ne True,
    kad LLM poziv otkaže."""
    import services.content_generator as cg
    with patch.object(cg, "_pozovi_etika_api", side_effect=RuntimeError("timeout")):
        result = asyncio.run(cg._proveri_etiku("neki tekst"))
    assert result["ok"] is None
    assert result["ok"] is not True
    assert len(result["problemi"]) >= 1


def test_proveri_etiku_flags_real_problems():
    import services.content_generator as cg
    raw = '{"ok": false, "problemi": ["Garantuje ishod postupka", "Reklamni jezik"]}'
    with patch.object(cg, "_pozovi_etika_api", return_value=raw):
        result = asyncio.run(cg._proveri_etiku("Uvek pobeđujemo! Kontaktirajte nas odmah!"))
    assert result["ok"] is False
    assert len(result["problemi"]) == 2


def test_parsiraj_generisani_post_rejects_missing_tekst():
    import services.content_generator as cg
    assert cg._parsiraj_generisani_post('{"naslov": "X"}') is None
    assert cg._parsiraj_generisani_post("not json") is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. shared/social_connectors.py
# ═══════════════════════════════════════════════════════════════════════════

def test_format_for_linkedin_never_marks_auto_posted():
    from shared.social_connectors import format_for_linkedin
    result = format_for_linkedin("Naslov", "Tekst posta.", "Rev 1/26")
    assert result["posti_se_automatski"] is False
    assert result["payload_oblik"]["lifecycleState"] == "DRAFT"
    assert "Tekst posta." in result["payload_oblik"]["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]


def test_format_for_blog_never_marks_auto_posted():
    from shared.social_connectors import format_for_blog
    result = format_for_blog("Naslov", "Tekst posta.")
    assert result["posti_se_automatski"] is False
    assert result["payload_oblik"]["status"] == "draft"


def test_format_draft_dispatches_by_platform():
    from shared.social_connectors import format_draft
    assert format_draft("linkedin", "N", "T")["platforma"] == "linkedin"
    assert format_draft("blog", "N", "T")["platforma"] == "blog"


def test_format_draft_unknown_platform_raises():
    from shared.social_connectors import format_draft
    with pytest.raises(ValueError):
        format_draft("twitter", "N", "T")


# ═══════════════════════════════════════════════════════════════════════════
# 3. routers/marketing_agent.py (integracija preko TestClient-a)
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
    _fr._CACHE["marketing_agent"] = {
        "feature_key": "marketing_agent", "aktivno": True, "status": "ACTIVE",
        "addon": None, "minimum_plan": None, "krediti": 2,
        "dnevni_limit": 10, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o-mini", "estimated_cost_usd": 0.01,
    }
    _fr._CACHE_LOADED_AT = _time.monotonic()
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE):
        yield
    api.app.dependency_overrides.pop(_shared_get_current_user, None)


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app, raise_server_exceptions=True)


def test_generate_invalid_izvor_tip_rejected(client):
    resp = client.post("/api/marketing/generate", json={"izvor_tip": "nepoznat", "platforma": "linkedin"})
    assert resp.status_code == 400


def test_generate_invalid_platforma_rejected(client):
    resp = client.post("/api/marketing/generate", json={"izvor_tip": "sudska_praksa", "platforma": "twitter"})
    assert resp.status_code == 400


def test_generate_failure_returns_422_and_does_not_consume_credits(client):
    fake_result = {"ok": False, "draft": None, "error": "Nema dostupnog javnog materijala."}
    with patch("services.content_generator.generate_post", new=AsyncMock(return_value=fake_result)), \
         patch("shared.usage.UsageService.consume", new=AsyncMock()) as consume_mock:
        resp = client.post("/api/marketing/generate", json={"izvor_tip": "sudska_praksa", "platforma": "linkedin"})

    assert resp.status_code == 422
    consume_mock.assert_not_awaited()


def test_generate_success_consumes_credits(client):
    fake_result = {"ok": True, "draft": {"id": "d1", "status": "pending"}, "error": None}
    with patch("services.content_generator.generate_post", new=AsyncMock(return_value=fake_result)), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=98)) as consume_mock:
        resp = client.post("/api/marketing/generate", json={"izvor_tip": "sudska_praksa", "platforma": "linkedin"})

    assert resp.status_code == 200
    assert resp.json()["draft"]["id"] == "d1"
    consume_mock.assert_awaited_once()


def test_format_rejected_for_pending_draft(client):
    with patch("routers.marketing_agent._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data={"id": "d1", "user_id": "test-user-id", "status": "pending"}))
        resp = client.get("/api/marketing/drafts/d1/format")

    assert resp.status_code == 409


def test_format_allowed_for_accepted_draft(client):
    accepted_draft = {
        "id": "d1", "user_id": "test-user-id", "status": "accepted",
        "platforma": "linkedin", "naslov": "N", "tekst": "T", "izvor_opis": "Rev 1/26",
    }
    with patch("routers.marketing_agent._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data=accepted_draft))
        resp = client.get("/api/marketing/drafts/d1/format")

    assert resp.status_code == 200
    assert resp.json()["posti_se_automatski"] is False


def test_format_not_found_for_other_users_draft(client):
    with patch("routers.marketing_agent._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data=None))
        resp = client.get("/api/marketing/drafts/tudje/format")

    assert resp.status_code == 404


def test_accept_rejects_already_resolved(client):
    with patch("routers.marketing_agent._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data={"id": "d1", "status": "accepted"}))
        resp = client.post("/api/marketing/drafts/d1/accept")

    assert resp.status_code == 409


def test_accept_success_updates_status(client):
    select_chain = _chain(MagicMock(data={"id": "d1", "status": "pending"}))
    update_chain = _chain(MagicMock(data=[{"id": "d1", "status": "accepted"}]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else update_chain

    with patch("routers.marketing_agent._get_supa") as mock_supa:
        mock_supa.return_value.table.side_effect = _table
        resp = client.post("/api/marketing/drafts/d1/accept")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert update_chain.update.call_args[0][0]["status"] == "accepted"


def test_lista_nacrta_invalid_status_rejected(client):
    resp = client.get("/api/marketing/drafts?status=nepostojeci")
    assert resp.status_code == 400


def test_lista_nacrta_filters_by_own_user_and_status(client):
    rows = [{"id": "d1", "user_id": "test-user-id", "status": "pending"}]
    with patch("routers.marketing_agent._get_supa") as mock_supa:
        chain = _chain(MagicMock(data=rows))
        mock_supa.return_value.table.return_value = chain
        resp = client.get("/api/marketing/drafts?status=pending")

    assert resp.status_code == 200
    assert resp.json()["ukupno"] == 1
    assert any(c.args == ("user_id", "test-user-id") for c in chain.eq.call_args_list)
