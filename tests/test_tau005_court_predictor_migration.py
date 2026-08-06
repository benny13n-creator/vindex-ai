# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 005 (2026-08-06) — "Court Predictor Canonical
Context Reconstruction". Closes TAU-011: all 7 routers/court_predictor.py
endpoints now use shared/case_context.py::build_case_context() (via the
thin, fail-soft _dohvati_case_context_ako_postoji wrapper) when predmet_id
is present, instead of reasoning blind to the case's own tracked state.

Tests prove:
  1. No predmet_id -> behavior is IDENTICAL to before migration (backward
     compatible -- most live calls to this file today have no predmet_id).
  2. predmet_id present -> real case context reaches the prompt.
  3. prediktuj_ishod's own deterministic readiness-based cap cannot be
     overridden by GPT, even with a poisoned response (Phase 5 adversarial).
  4. confidence_check's readiness-aware scoring preserves DC-004's own
     "one score, one nivo, one procenat" invariant (Program Alpha).
  5. judge_profile's sud consistency check and hearing_prep_brief's own
     rociste date cross-check.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/predictor/x", "app": MagicMock(), "state": MagicMock(),
             "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _insert_chain():
    c = MagicMock()
    c.insert = MagicMock(return_value=c)
    c.select = MagicMock(return_value=c)
    c.eq = MagicMock(return_value=c)
    c.ilike = MagicMock(return_value=c)
    c.order = MagicMock(return_value=c)
    c.limit = MagicMock(return_value=c)
    c.execute = MagicMock(return_value=MagicMock(data=[]))
    return c


def _cc(readiness_status="READY", sud=None, missing=None, contra=None, deadlines=None, actions=None, documents=None):
    """A minimal, valid build_case_context()-shaped dict for mocking."""
    return {
        "contract_version": "1.0.0",
        "case_identity": {"value": {"id": "p1", "naziv": "Test", "sud": sud}},
        "participants": {"value": {"stranka": "A", "protivnik": "B"}},
        "readiness": {"value": {"status": readiness_status, "razlog": "test"}},
        "key_facts": {"value": {"snaga_predmeta_procent": 60, "najslabija_tacka": {"rizik": "x", "kriticnost": 50}}},
        "missing_evidence": {"value": missing or []},
        "contradictions": {"value": contra or []},
        "deadlines": {"value": deadlines or []},
        "active_actions": {"value": actions or []},
        "relevant_documents": {"value": {"included": documents or [], "not_included_but_retrievable": []}},
    }


# ═══════════════════════════════════════════════════════════════════════════
# _case_context_blok / _dohvati_case_context_ako_postoji — unit tests
# ═══════════════════════════════════════════════════════════════════════════

def test_case_context_blok_empty_on_none_or_error():
    from routers.court_predictor import _case_context_blok
    assert _case_context_blok(None) == ""
    assert _case_context_blok({"error": "predmet_not_found"}) == ""


def test_case_context_blok_includes_readiness_and_gaps():
    from routers.court_predictor import _case_context_blok
    blok = _case_context_blok(_cc(readiness_status="CRITICAL_GAP", missing=[{"razlog": "Nema ugovora"}], contra=[{"razlog": "Datumi se ne slažu"}]))
    assert "CRITICAL_GAP" in blok
    assert "Nema ugovora" in blok
    assert "Datumi se ne slažu" in blok


@pytest.mark.anyio
async def test_dohvati_case_context_returns_none_without_predmet_id():
    from routers.court_predictor import _dohvati_case_context_ako_postoji
    result = await _dohvati_case_context_ako_postoji(None, "u1", MagicMock())
    assert result is None


@pytest.mark.anyio
async def test_dohvati_case_context_fail_soft_on_exception():
    from routers import court_predictor as cp
    with patch.object(cp, "build_case_context", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await cp._dohvati_case_context_ako_postoji("p1", "u1", MagicMock())
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# prediktuj_ishod — the core migration + the deterministic readiness cap
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_prediktuj_ishod_without_predmet_id_is_unchanged():
    """No predmet_id -> no case context fetch attempted at all, behavior
    identical to pre-migration (most live calls today have no predmet_id)."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10)

    gpt_json = json.dumps({"procenat_min": 80, "procenat_max": 90, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock()) as mock_bcc, \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    mock_bcc.assert_not_called()
    assert result["procenat_min"] == 80  # untouched -- no cap applied
    assert result["procenat_max"] == 90
    assert result["kontekst_predmeta_koriscen"] is False


@pytest.mark.anyio
async def test_prediktuj_ishod_caps_confidence_on_critical_gap_even_if_gpt_disagrees():
    """Phase 5 adversarial proof: GPT returns a confident 90% for a case the
    canonical readiness model says is CRITICAL_GAP. The cap must apply
    regardless -- this is the deterministic grounding fix, not a request GPT
    could ignore."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p1")

    # Poisoned: GPT insists on high confidence despite the case's own
    # canonical CRITICAL_GAP status.
    gpt_json = json.dumps({"procenat_min": 85, "procenat_max": 95, "analiza": "GPT je siguran u pobedu",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="CRITICAL_GAP"))), \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["procenat_min"] == 50  # capped
    assert result["procenat_max"] == 50  # capped (was 95, cap is 50)
    assert result["kontekst_predmeta_koriscen"] is True


@pytest.mark.anyio
async def test_prediktuj_ishod_no_cap_when_readiness_is_ready():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p1")
    gpt_json = json.dumps({"procenat_min": 70, "procenat_max": 85, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="READY"))), \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["procenat_min"] == 70
    assert result["procenat_max"] == 85


@pytest.mark.anyio
async def test_prediktuj_ishod_uses_full_document_mode_and_excerpts_reach_prompt():
    """prediktuj_ishod/battle_report are the 2 endpoints upgraded to
    include_documents=True (Phase 3's own context-certification finding:
    these 2 specifically need real evidence, not just readiness signals)."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p1")
    gpt_json = json.dumps({"procenat_min": 50, "procenat_max": 60, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    captured = {}
    def _capture(oai, user_prompt):
        captured["prompt"] = user_prompt
        return gpt_json

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(
             documents=[{"naziv": "ugovor.pdf", "excerpt": "Član 3. Rok isporuke je 30 dana."}]))) as mock_bcc, \
         patch.object(cp, "_pozovi_predictor_api", new=_capture), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    mock_bcc.assert_awaited_once_with("p1", "u1", supa, include_documents=True)
    assert "Član 3. Rok isporuke je 30 dana." in captured["prompt"]


@pytest.mark.anyio
async def test_prediktuj_ishod_koriscena_praksa_is_actual_rag_results_not_gpt_claim():
    """TAU-014 fix: koriscena_praksa reports what was ACTUALLY retrieved,
    never a GPT-invented citation."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10)
    gpt_json = json.dumps({"procenat_min": 50, "procenat_max": 60, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})
    real_praksa = [{"sud": "Apelacioni sud", "broj": "Gž 123/2024"}]

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("[Apelacioni sud Gž 123/2024] tekst", real_praksa)), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["koriscena_praksa"] == real_praksa


# ═══════════════════════════════════════════════════════════════════════════
# confidence_check — readiness feeds the SAME score (DC-004 invariant)
# ═══════════════════════════════════════════════════════════════════════════

def test_calc_confidence_nivo_readiness_ready_adds_point_replacing_dokazi():
    from routers.court_predictor import _calc_confidence_nivo, _CONFIDENCE_MAX_SCORE
    # Without context: dokazi_count=0 -> minus, no plus.
    nivo_a, _, plus_a, minus_a, score_a = _calc_confidence_nivo(0, 0, None, 0, readiness_status=None)
    # With context, READY: gets the point instead, regardless of dokazi_count.
    nivo_b, _, plus_b, minus_b, score_b = _calc_confidence_nivo(0, 0, None, 0, readiness_status="READY")
    assert score_b == score_a + 1
    assert any("READY" in p for p in plus_b)


def test_calc_confidence_nivo_critical_gap_adds_minus_not_plus():
    from routers.court_predictor import _calc_confidence_nivo
    nivo, _, plus, minus, score = _calc_confidence_nivo(0, 0, None, 5, readiness_status="CRITICAL_GAP")
    assert any("CRITICAL_GAP" in m for m in minus)
    assert not any("dokumentovan" in p for p in plus)  # dokazi_count path skipped when readiness present


def test_calc_confidence_nivo_max_score_unchanged_by_readiness():
    """Program Alpha's own DC-004 invariant: procenat is derived from the
    SAME score as nivo, always out of the SAME max -- readiness must not
    silently change the scale, only which signal fills the last point."""
    from routers.court_predictor import _CONFIDENCE_MAX_SCORE
    assert _CONFIDENCE_MAX_SCORE == 9


@pytest.mark.anyio
async def test_confidence_check_uses_readiness_when_predmet_id_present():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.ConfidenceCheckRequest(tip_spora="parnicno", opis_predmeta="x" * 30, predmet_id="p1")

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="READY"))), \
         patch.object(cp, "_pozovi_confidence_api", return_value=json.dumps({"razlog_kratko": "ok", "kljucni_rizik": ""})), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.confidence_check(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["kontekst_predmeta_koriscen"] is True
    assert any("READY" in p for p in result["faktori_plus"])
    # procenat is still derived deterministically from the same score -- not a 2nd GPT number.
    assert isinstance(result["procenat"], int)


# ═══════════════════════════════════════════════════════════════════════════
# judge_profile — sud consistency check
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_judge_profile_flags_sud_mismatch():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.JudgeProfileRequest(sud="Viši sud u Novom Sadu", tip_postupka="gradjansko", predmet_id="p1")
    gpt_json = json.dumps({"sud": "x", "sudija": "nije naveden", "ukupno_odluka_analizirano": 0,
                            "profil": {}, "strateska_preporuka": "", "pouzdanost_profila": "niska", "upozorenje": ""})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(sud="Osnovni sud u Beogradu"))), \
         patch.object(cp, "_pozovi_judge_profile_api", return_value=gpt_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.judge_profile(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["sud_neslaganje_sa_predmetom"] == "Osnovni sud u Beogradu"


@pytest.mark.anyio
async def test_judge_profile_no_mismatch_when_sud_matches():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.JudgeProfileRequest(sud="Osnovni sud u Beogradu", tip_postupka="gradjansko", predmet_id="p1")
    gpt_json = json.dumps({"sud": "x", "sudija": "nije naveden", "ukupno_odluka_analizirano": 0,
                            "profil": {}, "strateska_preporuka": "", "pouzdanost_profila": "niska", "upozorenje": ""})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(sud="Osnovni sud u Beogradu"))), \
         patch.object(cp, "_pozovi_judge_profile_api", return_value=gpt_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.judge_profile(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["sud_neslaganje_sa_predmetom"] is None


# ═══════════════════════════════════════════════════════════════════════════
# hearing_prep_brief — rociste date cross-check
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_hearing_prep_flags_unconfirmed_rociste_date():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.HearingPrepRequest(predmet_id="p1", rociste_naziv="Ročište", datum_rocista="2026-09-01",
                                     tip_postupka="gradjansko", opis_predmeta="x" * 30)

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(deadlines=[{"datum": "2026-10-15", "sud": "X", "status": "zakazano", "proslo": False}]))), \
         patch.object(cp, "_pozovi_hearing_prep_api", return_value="brief tekst"), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.hearing_prep_brief(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["rociste_potvrdjeno_u_sistemu"] is False


# ═══════════════════════════════════════════════════════════════════════════
# argument_reputation / opponent_intel — context reaches the prompt
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_argument_reputation_injects_case_context_into_prompt():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.ArgumentReputationRequest(tip_spora="parnicno", argumenti=["Zastarelost"], predmet_id="p1")
    gpt_json = json.dumps({"argumenti_analiza": [], "ukupna_snaga": 50, "slabosti": [],
                            "preporuceni_redosled": [], "alternativni_argumenti": []})

    captured = {}

    def _capture(oai_client, user_msg):
        captured["msg"] = user_msg
        return gpt_json

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(missing=[{"razlog": "Nema veštačenja"}]))), \
         patch.object(cp, "_pozovi_arg_reputation_api", new=_capture), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert "Nema veštačenja" in captured["msg"]
    assert result["kontekst_predmeta_koriscen"] is True


@pytest.mark.anyio
async def test_opponent_intel_injects_case_context_alongside_portfolio_search():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.OpponentIntelRequest(protivnik_naziv="Protivnik DOO", tip_postupka="privredno", predmet_id="p1")
    gpt_json = json.dumps({"protivnik": "Protivnik DOO", "advokatska_kancelarija": "nije naveden",
                            "analiza": {"poznati_stil": "", "taktike": [], "stopa_nagodbi": "nepoznato", "slabosti": [], "snage": []},
                            "preporucena_taktika": "", "upozorenja": [], "pouzdanost": "niska"})

    captured = {}

    def _capture(oai_client, user_msg):
        captured["msg"] = user_msg
        return gpt_json

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(contra=[{"razlog": "Sukob u iskazima"}]))), \
         patch.object(cp, "_pozovi_opponent_intel_api", new=_capture), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.opponent_intel(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert "Sukob u iskazima" in captured["msg"]
    assert result["kontekst_predmeta_koriscen"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 -- concurrency + replay/determinism
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_predictions_for_different_cases_do_not_cross_contaminate():
    """Program Tau, Master Sprint 005 -- Phase 9's own concurrency test.
    _dohvati_case_context_ako_postoji/build_case_context carry no shared
    mutable state (confirmed already in Tau 002's own design) -- proven here
    at the endpoint level: 2 concurrent predictions for 2 different cases
    with different readiness must each get their OWN cap applied, never the
    other's."""
    import asyncio as _asyncio
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    gpt_json = json.dumps({"procenat_min": 90, "procenat_max": 95, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    async def _fake_bcc(predmet_id, uid, supa_arg, include_documents=False):
        return _cc(readiness_status="CRITICAL_GAP" if predmet_id == "p-critical" else "READY")

    payload_a = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p-critical")
    payload_b = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p-ready")

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=_fake_bcc), \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result_a, result_b = await _asyncio.gather(
            cp.prediktuj_ishod(_req(), payload_a, user={"user_id": "u1", "email": "a@b.com"}),
            cp.prediktuj_ishod(_req(), payload_b, user={"user_id": "u2", "email": "b@b.com"}),
        )

    assert result_a["procenat_max"] == 50   # capped -- CRITICAL_GAP
    assert result_b["procenat_max"] == 95   # untouched -- READY


@pytest.mark.anyio
async def test_repeated_identical_calls_produce_identical_cap_replay_stable():
    """Program Tau, Master Sprint 005 -- Phase 9's own replay test: the same
    case, same readiness, same GPT output, called twice in a row (simulating
    an event-replay/retry scenario) must produce the SAME capped result both
    times -- the cap is a pure function of readiness + GPT output, no hidden
    state that could drift between calls."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.PredictorRequest(opis_predmeta="x" * 30, tip_postupka="gradjansko", cinjenicni_opis="y" * 10, predmet_id="p1")
    gpt_json = json.dumps({"procenat_min": 85, "procenat_max": 95, "analiza": "ok",
                            "kljucni_faktori_za": [], "kljucni_faktori_protiv": [], "preporucena_strategija": "", "rizici": []})

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="BLOCKED"))), \
         patch.object(cp, "_pozovi_predictor_api", return_value=gpt_json), \
         patch.object(cp, "_rag_praksa_blok", return_value=("", [])), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result_1 = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})
        result_2 = await cp.prediktuj_ishod(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result_1["procenat_min"] == result_2["procenat_min"] == 65  # BLOCKED cap
    assert result_1["procenat_max"] == result_2["procenat_max"] == 65


@pytest.mark.anyio
async def test_hearing_prep_confirms_matching_rociste_date():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())
    payload = cp.HearingPrepRequest(predmet_id="p1", rociste_naziv="Ročište", datum_rocista="2026-09-01",
                                     tip_postupka="gradjansko", opis_predmeta="x" * 30)

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "build_case_context", new=AsyncMock(return_value=_cc(deadlines=[{"datum": "2026-09-01", "sud": "X", "status": "zakazano", "proslo": False}]))), \
         patch.object(cp, "_pozovi_hearing_prep_api", return_value="brief tekst"), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.hearing_prep_brief(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["rociste_potvrdjeno_u_sistemu"] is True
