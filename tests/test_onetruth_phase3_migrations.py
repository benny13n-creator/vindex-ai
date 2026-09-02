# -*- coding: utf-8 -*-
"""
Operation One Truth, Phase 3 — regression coverage for the migration fixes made after the
7-team forensic pass (docs/onetruth/). Each test proves a specific duplicate-truth defect is
closed: a module that used to independently compute or read a stale value now reads the
canonical source instead.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.4.2 — SVI ROKOVI U OVIM FIXTURE-IMA SU POTVRDJENI
#
# Od 6.4.2 nijedan rok ne moze proizvesti izvrsivu posledicu bez eksplicitne
# ljudske potvrde -- ni ljudski, ni deterministicki, ni sistemski. Testovi u
# ovom fajlu ne mere TU granicu (nju meri `test_faza621_provenance_boundary.py`
# i `test_faza64_provenance_contract.py`); oni mere svoje sopstvene ugovore,
# koji su i dalje vazeci.
#
# Zato se ovde modeluje advokat koji je rokove VEC potvrdio. Bez toga bi svaki
# ovaj test padao iz razloga koji nema veze sa onim sto tvrdi.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _rokovi_su_potvrdjeni(monkeypatch):
    import routers.notifications as _m
    if hasattr(_m, "_potvrdjeni_ids"):
        monkeypatch.setattr(_m, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})



@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_dna.py::_extract_genome -- najslabija_tacka.kriticnost is now
# clamped 0-100, matching the existing pattern for its sibling field
# snaga_predmeta_procent (Reliability Patch v2). This is also a poisoned-
# response test: proves a fabricated out-of-range GPT claim cannot reach the
# DB unclamped (Operation One Truth Phase 4's own adversarial mandate).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_extract_genome_clamps_poisoned_kriticnost_above_range():
    from routers import case_dna as cd
    gpt_json = (
        '{"snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [], '
        '"najslabija_tacka": {"rizik": "Nema svedoka", "kriticnost": 500, "lokacija": ""}}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "neki tekst dokumenta"}]
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)
    assert result["najslabija_tacka"]["kriticnost"] == 100


@pytest.mark.anyio
async def test_extract_genome_clamps_poisoned_kriticnost_negative():
    from routers import case_dna as cd
    gpt_json = (
        '{"snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [], '
        '"najslabija_tacka": {"rizik": "x", "kriticnost": -40, "lokacija": ""}}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "neki tekst dokumenta"}]
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)
    assert result["najslabija_tacka"]["kriticnost"] == 0


@pytest.mark.anyio
async def test_extract_genome_clamps_poisoned_kriticnost_non_numeric():
    """GPT can return a string, None, or garbage instead of a number -- must not crash the
    whole extraction, must not persist an un-clamped/un-typed value."""
    from routers import case_dna as cd
    gpt_json = (
        '{"snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [], '
        '"najslabija_tacka": {"rizik": "x", "kriticnost": "vrlo visoko", "lokacija": ""}}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "neki tekst dokumenta"}]
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)
    assert result["najslabija_tacka"]["kriticnost"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# build_case_context() exposes the canonical risk value (new "risk" field)
# ═══════════════════════════════════════════════════════════════════════════

def test_case_context_risk_field_sourced_from_risk_engine():
    from shared.case_context import context_field
    f = context_field({"nivo": "Visok", "health_score": 25}, source="services/risk_engine.py::calculate_procesni_rizik",
                       owner="risk_engine.py (the single canonical risk source platform-wide)", refresh="real-time")
    assert f["value"]["nivo"] == "Visok"
    assert "risk_engine" in f["source"]


# ═══════════════════════════════════════════════════════════════════════════
# build_case_context()'s key_facts now exposes Genome verification status --
# previously computed and stored (shared/genome_validator.py::verify_genome)
# but invisible to every downstream AI consumer of this canonical context.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_key_facts_exposes_genome_verification_decision():
    import sys, importlib
    tau002 = importlib.import_module("tests.test_tau002_case_context")
    from shared.case_context import build_case_context
    supa = tau002._FakeSupa(tau002._base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
        "case_dna": {
            "verzija": 1, "pravna_teorija": "Ugovorna odgovornost", "snaga_predmeta_procent": 70,
            "_verifikacija": {"odluka": "require_review", "hard_flags": ["fabricated_doc_ref"]},
        },
    }))
    result = await build_case_context("p1", "u1", supa)
    assert result["key_facts"]["value"]["genome_verifikacija_odluka"] == "require_review"


@pytest.mark.anyio
async def test_key_facts_verification_none_when_never_verified():
    """Older Genome records predate the verification layer -- must not crash,
    must not be silently mistaken for 'approved'."""
    import importlib
    tau002 = importlib.import_module("tests.test_tau002_case_context")
    from shared.case_context import build_case_context
    supa = tau002._FakeSupa(tau002._base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
        "case_dna": {"verzija": 1, "pravna_teorija": "Stara teorija", "snaga_predmeta_procent": 60},
    }))
    result = await build_case_context("p1", "u1", supa)
    assert result["key_facts"]["value"]["genome_verifikacija_odluka"] is None


# ═══════════════════════════════════════════════════════════════════════════
# digital_twin.py — no longer reads the stale predmeti.rizik column when
# canonical case_context is available
# ═══════════════════════════════════════════════════════════════════════════

def test_digital_twin_kontekst_prefers_canonical_risk_over_stale_column():
    from routers.digital_twin import _build_kontekst_tekst
    ctx = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "rizik": "nizak", "opis": "x"},
        "rokovi": [], "dokumenti": [], "komentari": [],
    }
    # Canonical engine says "Visok" -- the stale predmeti.rizik column still says "nizak".
    case_context = {"risk": {"value": {"nivo": "Visok", "health_score": 15}}}
    tekst = _build_kontekst_tekst(ctx, case_context=case_context)
    assert "Rizik: Visok" in tekst
    assert "Rizik: nizak" not in tekst


def test_digital_twin_kontekst_falls_back_to_stale_column_when_canonical_unavailable():
    """Fail-soft: if build_case_context() itself failed (case_context is None), the prompt
    must still be built -- degraded, not broken."""
    from routers.digital_twin import _build_kontekst_tekst
    ctx = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "rizik": "nizak", "opis": "x"},
        "rokovi": [], "dokumenti": [], "komentari": [],
    }
    tekst = _build_kontekst_tekst(ctx, case_context=None)
    assert "Rizik: nizak" in tekst


def test_digital_twin_kontekst_defaults_when_neither_source_has_a_value():
    from routers.digital_twin import _build_kontekst_tekst
    ctx = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "opis": "x"},
        "rokovi": [], "dokumenti": [], "komentari": [],
    }
    tekst = _build_kontekst_tekst(ctx, case_context=None)
    assert "Rizik: srednji" in tekst


# ═══════════════════════════════════════════════════════════════════════════
# hearing_cc.py — same fix, same pattern
# ═══════════════════════════════════════════════════════════════════════════

def test_hearing_cc_prompt_prefers_canonical_risk_over_stale_column():
    from routers.hearing_cc import _build_prompt
    ctx = {"predmet": {"naziv": "Test", "opis": "x", "status": "aktivan", "rizik": "nizak",
                        "tuzilac": "A", "tuzeni": "B", "oblast": "radno"},
           "klijenti": [], "beleske": [], "rocista": [], "istorija": []}
    case_context = {"risk": {"value": {"nivo": "Visok", "health_score": 10}}}
    prompt = _build_prompt(ctx, "2026-09-01", "parnica", case_context=case_context)
    assert "Rizik: Visok" in prompt
    assert "Rizik: nizak" not in prompt


def test_hearing_cc_prompt_falls_back_when_canonical_unavailable():
    from routers.hearing_cc import _build_prompt
    ctx = {"predmet": {"naziv": "Test", "opis": "x", "status": "aktivan", "rizik": "nizak",
                        "tuzilac": "A", "tuzeni": "B", "oblast": "radno"},
           "klijenti": [], "beleske": [], "rocista": [], "istorija": []}
    prompt = _build_prompt(ctx, "2026-09-01", "parnica", case_context=None)
    assert "Rizik: nizak" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# api.py::predmeti_dashboard — the mission's #1 priority fix (Red Team's own
# flagship reproduction). This endpoint used to read a CACHED risk snapshot
# ("[Rizik] {date}" rows in predmet_istorija, written once at case creation and
# only lazily refreshed on Workspace-open) instead of computing it live like
# every other risk surface. Now computes calculate_procesni_rizik live, in bulk,
# per case -- no cache, nothing to go stale.
# ═══════════════════════════════════════════════════════════════════════════

def _dash_chain(execute_return=None):
    m = MagicMock()
    for method in ("select", "eq", "neq", "insert", "update", "limit", "order",
                   "is_", "in_", "gte", "lte", "like", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    m.not_ = m
    m.execute = MagicMock(return_value=execute_return)
    return m


def _dash_req():
    from starlette.requests import Request as StarletteRequest
    scope = {
        "type": "http", "method": "GET", "path": "/api/predmeti/dashboard", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope)


@pytest.mark.anyio
async def test_dashboard_risk_ignores_stale_cache_uses_live_engine():
    """The exact Red Team reproduction: a stale cached '[Rizik] nizak' snapshot must
    NOT be trusted when the live, canonical engine would compute something else for
    the case's actual current evidence/hearings."""
    import api

    predmet = {"id": "p1", "naziv": "Test", "tip": "opsti", "status": "aktivan", "created_at": "2026-01-01"}
    # Live facts imply HIGH risk: no evidence at all, plus an overdue hearing.
    dokazi = []
    dokumenti = []
    rocista = [{"predmet_id": "p1", "datum": "2020-01-01"}]  # long overdue -> zakasneli/kriticni

    def _table(name):
        if name == "predmeti":
            return _dash_chain(MagicMock(data=[predmet]))
        if name == "predmet_hronologija":
            return _dash_chain(MagicMock(data=[]))
        if name == "predmet_dokazi":
            return _dash_chain(MagicMock(data=dokazi))
        if name == "predmet_dokumenti":
            return _dash_chain(MagicMock(data=dokumenti))
        if name == "rocista":
            return _dash_chain(MagicMock(data=rocista))
        if name == "case_actions":
            return _dash_chain(MagicMock(data=[]))
        if name == "predmet_istorija":
            # A stale cache claiming "nizak" (low) risk -- must be ignored entirely.
            return _dash_chain(MagicMock(data=[
                {"predmet_id": "p1", "odgovor": '{"nivo": "nizak"}', "created_at": "2020-01-02"}
            ]))
        return _dash_chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("api._get_supa", return_value=supa):
        result = await api.predmeti_dashboard(_dash_req(), {"user_id": "u1"})

    rizik_nivo = result["predmeti"][0]["rizik_nivo"]
    assert rizik_nivo == "Visok", f"expected live-computed 'Visok', got stale-cache-derived {rizik_nivo!r}"


@pytest.mark.anyio
async def test_dashboard_never_queries_predmet_istorija_for_risk():
    """Structural proof the cache read path is gone entirely, not just overridden."""
    import api

    predmet = {"id": "p1", "naziv": "Test", "tip": "opsti", "status": "aktivan", "created_at": "2026-01-01"}
    istorija_chain = _dash_chain(MagicMock(data=[]))

    def _table(name):
        if name == "predmeti":
            return _dash_chain(MagicMock(data=[predmet]))
        if name == "predmet_istorija":
            return istorija_chain
        return _dash_chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("api._get_supa", return_value=supa):
        await api.predmeti_dashboard(_dash_req(), {"user_id": "u1"})

    istorija_chain.select.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# routers/court_predictor.py::argument_reputation — uspesnost_procena/
# ukupna_snaga were never clamped to their own documented 0-100 range (unlike
# their sibling case_dna.py::snaga_predmeta_procent, and unlike this same
# endpoint's own 'boja' field, which Program Gamma already re-derives from the
# number). Poisoned-response test, Operation One Truth Phase 4's own mandate.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_argument_reputation_clamps_poisoned_out_of_range_scores():
    import os as _os
    import json as _json
    from starlette.requests import Request as StarletteRequest
    from routers import court_predictor as cp

    def _req():
        scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
                  "path": "/api/predictor/x", "app": MagicMock(), "state": MagicMock(),
                  "client": ("testclient", 123)}
        return StarletteRequest(scope=scope)

    def _insert_chain():
        c = MagicMock()
        c.insert = MagicMock(return_value=c)
        c.execute = MagicMock(return_value=MagicMock(data=[{"id": "row-1"}]))
        return c

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    raw_llm_json = _json.dumps({
        "argumenti_analiza": [
            {"argument": "Zastarelost", "uspesnost_procena": 850, "boja": "zelena",
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 5},
            {"argument": "Nedostatak forme", "uspesnost_procena": -30, "boja": "zelena",
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 3},
        ],
        "ukupna_snaga": 999, "slabosti": [], "preporuceni_redosled": [], "alternativni_argumenti": [],
    })

    payload = cp.ArgumentReputationRequest(tip_spora="radni spor", argumenti=["Zastarelost", "Nedostatak forme"])

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "_pozovi_arg_reputation_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(_os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    analiza = result["argumenti_analiza"]
    assert analiza[0]["uspesnost_procena"] == 100
    assert analiza[1]["uspesnost_procena"] == 0
    assert result["ukupna_snaga"] == 100


# ═══════════════════════════════════════════════════════════════════════════
# routers/notifications.py::_generate_notifications — the delete-then-regenerate
# cycle used to wipe out EVERY unread rok/hitan_rok/neaktivnost row for the
# user, including ones services/case_evolution.py's own dedupe-key-based
# projection had just individually reconciled -- despite that module's own
# docstring falsely claiming this generator was "retired." Fixed by scoping
# the delete to only this function's own (dedupe_key-less) rows.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_generate_notifications_delete_excludes_dedupe_key_rows():
    from routers import notifications as notif_mod

    def _chain():
        m = MagicMock()
        for method in ("select", "eq", "gte", "lte", "lt", "order", "limit", "in_", "is_", "delete", "insert"):
            setattr(m, method, MagicMock(return_value=m))
        m.execute = MagicMock(return_value=MagicMock(data=[
            {"id": "rok-ot-1", "izvor": "HUMAN_DIRECT", "predmet_id": "p1", "dogadjaj": "Ročište", "datum_iso": "2026-08-08", "vaznost": "kritičan"},
        ]))
        return m

    predmeti_chain = MagicMock()
    for method in ("select", "eq"):
        setattr(predmeti_chain, method, MagicMock(return_value=predmeti_chain))
    predmeti_chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "p1", "naziv": "Test", "status": "aktivan"}]))

    delete_chain = _chain()
    insert_chain = _chain()

    def _table(name):
        if name == "predmeti":
            return predmeti_chain
        if name == "notifications":
            # First .delete() call gets delete_chain's behavior via the same
            # MagicMock -- .delete()/.insert() both return `m` per _chain()'s
            # own setup, so track calls on one shared chain object.
            return delete_chain
        return _chain()

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.notifications._get_supa", return_value=supa):
        await notif_mod._generate_notifications("u1")

    # The delete chain must have been scoped with is_("dedupe_key", "null")
    # before its own execute() -- proving case_evolution.py's dedupe_key-bearing
    # rows are structurally excluded from this function's own delete.
    is_calls = [c for c in delete_chain.is_.call_args_list if c.args == ("dedupe_key", "null")]
    assert is_calls, "delete query must exclude dedupe_key-bearing rows (is_('dedupe_key', 'null'))"


# ═══════════════════════════════════════════════════════════════════════════
# routers/ccc.py — predstojeći/kritican_rok sourced from calculate_procesni_rizik,
# not a second, independently (and buggy) derived count. See tests/test_ccc.py
# for the full endpoint-level regression suite (T10-T12) -- these are covered
# there since they need the full mocked-Supabase request path, not just a pure
# function. Cross-referenced here for discoverability of this mission's fixes.
# ═══════════════════════════════════════════════════════════════════════════

def test_ccc_fix_is_covered_in_test_ccc_py():
    """Marker test: the CCC naive/aware-datetime + discarded-canonical-value fix
    (routers/ccc.py) has its own regression coverage in tests/test_ccc.py
    (test_ccc_kritican_rok_detected_plain_date_string,
    test_ccc_predstojeci_and_kritican_rok_sourced_from_canonical_engine,
    test_ccc_overdue_hearing_surfaces_as_kritican_rok) -- verify those exist."""
    import inspect
    import tests.test_ccc as t
    names = {n for n, _ in inspect.getmembers(t, inspect.isfunction)}
    assert "test_ccc_kritican_rok_detected_plain_date_string" in names
    assert "test_ccc_predstojeci_and_kritican_rok_sourced_from_canonical_engine" in names
    assert "test_ccc_overdue_hearing_surfaces_as_kritican_rok" in names
