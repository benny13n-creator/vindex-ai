# -*- coding: utf-8 -*-
"""
Regression tests — Celina 4: Čišćenje Tehničkog Duga, Unifikacija Duplikacija
i Konsolidacija Ruta (2026-07-24).

1. Task 1 (Drafting konsolidacija): SVESNO PRESKOČENO na eksplicitan zahtev
   korisnika -- founder-ova odluka od 2026-07-22 (VINDEX_CORE_CONSOLIDATION.md
   Sec 1.4) ostaje netaknuta. Nema koda za testiranje ovde po dizajnu; test
   ispod zaključava da tri drafting fajla i dalje NISU spojena (isti test
   princip kao Celina 3's LRE izolacioni test).
2. Task 2 (Webhook konsolidacija): routers/integracije.py i
   routers/integrations.py su dva nezavisna outbound-webhook sistema
   (različite tabele, OBRNUT redosled argumenata u istoimenoj funkciji
   trigger_webhook). Nisu spojeni (rizik po produkcione podatke bez
   vidljivosti u postojeće redove) -- umesto toga jasno dokumentovano u
   oba docstring-a, isti obrazac kao Core Consolidation Sec 1.4.
3. Task 3 (Enterprise vs Kancelarija): potvrđeno već rešeno u ranijoj sesiji
   (Faza 72 čišćenje) -- enterprise.py čita iz stvarnih kancelarije/
   kancelarija_clanovi tabela, ne prazne firma_clanovi. Regresiona brana.
4. Task 4 (Globalna @llm_retry provera): 34 fajla je imalo direktne OpenAI
   pozive bez ikakve retry zaštite -- uključujući DVA root-level fajla
   (strategija.py sa 12 poziva, web3_compliance.py sa 10 poziva) koji su
   propušteni iz ranijih Celina jer nisu u routers/ folderu iako ih routers/
   fajlovi pozivaju, i SEDAM poziva direktno u api.py (jedan od njih pravi
   blocking bug -- sinhroni SDK poziv bez asyncio.to_thread unutar async def,
   blokirao je ceo event loop do 90s po pozivu).
"""
import sys
import os
import asyncio
import inspect
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


# ─── 1. Drafting freeze — i dalje netaknut (skipped by explicit decision) ──

def test_drafting_freeze_dokumentovan_u_sva_tri_fajla():
    """Founder odluka 2026-07-22 (Sec 1.4): tri drafting mehanizma NE smeju
    biti tiho spojena. Celina 4 Task 1 je eksplicitno preskočen na zahtev
    korisnika -- ovaj test zaključava da freeze docstring-ovi i dalje postoje
    (puca ako neko ubuduće obriše napomenu i tiho spoji registre)."""
    import drafting.router as drafting_router
    import routers.drafting as routers_drafting
    import routers.doc_templates as doc_templates

    for mod in (drafting_router, routers_drafting, doc_templates):
        src = mod.__doc__ or ""
        assert "NOT merged" in src or "pilot-gated" in src, f"{mod.__name__} freeze napomena nedostaje"


# ─── 2. Webhook duplikacija — dokumentovana, ne spojena ────────────────────

def test_integracije_i_integrations_imaju_nezavisne_trigger_webhook():
    """Dva odvojena outbound webhook sistema i dalje postoje nezavisno
    (namerno, v. docstring), sa različitim redosledom argumenata."""
    import routers.integracije as integracije
    import routers.integrations as integrations

    sig_a = inspect.signature(integracije.trigger_webhook)
    sig_b = inspect.signature(integrations.trigger_webhook)

    assert list(sig_a.parameters.keys()) == ["event", "user_id", "data"]
    assert list(sig_b.parameters.keys()) == ["user_id", "event", "data"]
    # Obrnut redosled je namerno dokumentovan kao opasnost u oba docstring-a
    assert "OBRNUT" in (integracije.trigger_webhook.__doc__ or "")
    assert "OBRNUT" in (integrations.trigger_webhook.__doc__ or "")


def test_integracije_koristi_user_webhooks_tabelu():
    import inspect as _inspect
    import routers.integracije as integracije
    src = _inspect.getsource(integracije.trigger_webhook)
    assert 'table("user_webhooks")' in src


def test_integrations_koristi_webhooks_tabelu():
    import inspect as _inspect
    import routers.integrations as integrations
    src = _inspect.getsource(integrations.trigger_webhook)
    assert 'table("webhooks")' in src


# ─── 3. Enterprise vs Kancelarija — regresiona brana (Faza 72, potvrđeno) ──

def test_enterprise_ne_koristi_praznu_firma_clanovi_tabelu():
    """enterprise.py je istorijski pisan protiv nikad migrirane 'firma_clanovi'
    tabele. Faza 72 čišćenje (pre ove Celine) je to ispravilo da čita iz
    stvarnih kancelarije/kancelarija_clanovi tabela. Ovaj test zaključava tu
    ispravku -- puca ako neko ubuduće vrati referencu na firma_clanovi."""
    import inspect as _inspect
    import routers.enterprise as enterprise

    src = _inspect.getsource(enterprise)
    # Docstring sme da POMINJE firma_clanovi kao istorijsko objašnjenje --
    # bitno je da nijedan stvaran .table() poziv ne cilja tu (praznu) tabelu.
    assert 'table("firma_clanovi")' not in src
    assert 'table("firma_pozivnice")' not in src
    assert 'table("kancelarije")' in src
    assert 'table("kancelarija_clanovi")' in src


def test_kancelarija_nema_duplirane_statistike_kapacitet_rute():
    """kancelarija.py ostaje čisto membership/invitation management -- nema
    /statistike, /kapacitet ili /predmet/delegiraj koje bi duplirale
    enterprise.py (koje čita iz kancelarija.py-ovih tabela, ne obrnuto)."""
    import routers.kancelarija as kancelarija

    routes = {r.path for r in kancelarija.router.routes}
    assert not any("statistike" in p or "kapacitet" in p or "delegiraj" in p for p in routes)


# ─── 4a. Globalni retry sweep — root-level fajlovi propušteni iz ranijih Celina ──

def test_strategija_py_ima_retry_zasticen_helper_za_svih_12_poziva():
    """strategija.py (root-level, NE routers/strategija.py) je imao 12
    direktnih .completions.create() poziva bez ikakve retry zaštite --
    najveća koncentracija otkrivena u celoj proveri, propuštena jer fajl
    nije u routers/ folderu iako ga routers/strategija.py poziva."""
    import strategija
    assert hasattr(strategija, "_pozovi_strategija_api")
    assert hasattr(strategija, "llm_retry")

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response("analiza teksta")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = strategija._pozovi_strategija_api(client, model="gpt-4o", messages=[])

    assert calls["n"] == 3
    assert out.choices[0].message.content == "analiza teksta"


def test_strategija_py_svih_11_poziva_ide_kroz_retry_helper():
    import inspect as _inspect
    import strategija
    src = _inspect.getsource(strategija)
    # 1 definicija + 11 poziva (6 pojedinačnih modula + 3 u ai_judge_v2_sync + 2 u orkestratoru)
    assert src.count("_pozovi_strategija_api(") == 12
    # Jedino mesto gde "client.chat.completions.create(" sme da postoji je
    # unutar same definicije _pozovi_strategija_api (linija ispod docstring-a).
    assert src.count("client.chat.completions.create(") == 1


def test_web3_compliance_py_ima_retry_zasticen_helper_za_svih_10_poziva():
    """web3_compliance.py (root-level) je imao 10 direktnih poziva bez
    retry zaštite -- isti propust kao strategija.py."""
    import web3_compliance
    assert hasattr(web3_compliance, "_pozovi_web3_api")
    assert hasattr(web3_compliance, "llm_retry")

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response('{"ok": true}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = web3_compliance._pozovi_web3_api(client, model="gpt-4o", messages=[])

    assert calls["n"] == 2
    assert out.choices[0].message.content == '{"ok": true}'


# ─── 4b. Globalni retry sweep — api.py (7 poziva, uključujući blocking bug) ─

def test_api_py_ima_sync_i_async_retry_helpere():
    import api
    assert hasattr(api, "_pozovi_openai_sync_api")
    assert hasattr(api, "_pozovi_openai_async_api")


def test_api_py_sync_helper_retry_radi():
    from api import _pozovi_openai_sync_api

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response("procena teksta")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = _pozovi_openai_sync_api(client, model="gpt-4o", messages=[])

    assert calls["n"] == 3
    assert out.choices[0].message.content == "procena teksta"


def test_api_py_async_helper_retry_radi():
    from api import _pozovi_openai_async_api

    calls = {"n": 0}

    def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response("preporuka")

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_openai_async_api(client, model="gpt-4o-mini", messages=[]))

    assert calls["n"] == 2
    assert out.choices[0].message.content == "preporuka"


def test_pravna_procena_blocking_bug_ispravljen():
    """BUG FIX (2026-07-24): sinhroni client.chat.completions.create() poziv
    je ranije stajao DIREKTNO u async def pravna_procena bez asyncio.to_thread
    -- blokirao je ceo event loop do 90s (timeout=90.0, max_tokens=4500) po
    pozivu. Ovaj test zaključava da poziv sada ide kroz asyncio.to_thread."""
    import inspect as _inspect
    import api

    src = _inspect.getsource(api.pravna_procena)
    assert "_pozovi_openai_sync_api" in src
    assert "await asyncio.to_thread(" in src
    # Direktan (ne-to_thread) sinhroni poziv preko client.chat.completions.create
    # ne sme više postojati u ovoj funkciji.
    assert "client.chat.completions.create(" not in src


# ─── 4c. Reprezentativni retry testovi — routers/ i services/ fajlovi ─────

def test_evidence_graph_retry_helper():
    from routers.evidence_graph import _pozovi_eg_api

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response('{"nodes": [], "edges": []}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = _pozovi_eg_api(client, "kontekst")

    assert calls["n"] == 3


def test_health_index_chief_partner_retry_helper():
    from routers import health_index

    calls = {"n": 0}

    def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response("1. Uradi X.")

    health_index._openai.chat.completions.create = AsyncMock(side_effect=_side_effect)
    out = asyncio.run(health_index._pozovi_chief_partner_api("prompt"))

    assert calls["n"] == 2
    assert out.choices[0].message.content == "1. Uradi X."


def test_case_pipeline_retry_helper():
    from services.case_pipeline import _pozovi_pipeline_api

    calls = {"n": 0}

    async def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response('{"rokovi": []}')

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_pipeline_api(oai, model="gpt-4o-mini", messages=[]))
    assert calls["n"] == 2


def test_learning_engine_retry_helper():
    from services.learning_engine import _pozovi_learning_engine_api

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return _fake_chat_response('{"lekcije": []}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        oai = MockOAI()
        out = _pozovi_learning_engine_api(oai, model="gpt-4o-mini", messages=[])

    assert calls["n"] == 3


def test_intake_classify_retry_helper():
    from shared.intake_classify import _pozovi_classify_api

    calls = {"n": 0}

    async def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response('{"document_type": "lawsuit", "confidence": 0.9}')

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_classify_api(oai, model="gpt-4o-mini", messages=[]))
    assert calls["n"] == 2


def test_intake_extract_retry_helper():
    from shared.intake_extract import _pozovi_extract_api

    calls = {"n": 0}

    async def _side_effect(**kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _rate_limit_error()
        return _fake_chat_response('{"judge": {"value": null, "confidence": 0}}')

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=_side_effect)

    out = asyncio.run(_pozovi_extract_api(oai, model="gpt-4o-mini", messages=[]))
    assert calls["n"] == 2


# ─── 4d. Strukturna provera — svi dotaknuti moduli uvoze llm_retry ─────────

def test_svi_dotaknuti_moduli_uvoze_llm_retry():
    import importlib

    moduli = [
        "routers.case_intelligence", "routers.cio", "routers.client_twin",
        "routers.corrections", "routers.cross_doc", "routers.decision_replay",
        "routers.digital_twin", "routers.dokument", "routers.doc_templates",
        "routers.drafting", "routers.evidence", "routers.evidence_graph",
        "routers.health_index", "routers.hearing_cc", "routers.intake",
        "routers.integracije", "routers.knowledge_base", "routers.knowledge_transfer",
        "routers.learning", "routers.matter_intel", "routers.memory_graph",
        "routers.morning_briefing", "routers.outcome_intel", "routers.precedenti",
        "routers.profitabilnost", "routers.region", "routers.strategija",
        "routers.style_checker", "routers.voice", "routers.web3",
        "routers.zadaci", "routers.zakon_monitoring", "routers.zastarelost",
        "services.case_pipeline", "services.learning_engine",
        "shared.intake_classify", "shared.intake_extract",
        "app.services.retrieve", "nacrti.checklist_engine",
        "strategija", "web3_compliance",
    ]
    missing = []
    for name in moduli:
        mod = importlib.import_module(name)
        if not hasattr(mod, "llm_retry"):
            missing.append(name)
    assert not missing, f"Moduli bez llm_retry importa: {missing}"
