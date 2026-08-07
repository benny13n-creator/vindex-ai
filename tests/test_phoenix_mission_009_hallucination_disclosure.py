# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 009 -- Hallucination Disclosure Mitigations.
Closes LIVINGSYS-DEBT-047, LIVINGSYS-DEBT-015.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


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
    c.execute = MagicMock(return_value=MagicMock(data=[{"id": "row-1"}]))
    return c


def _match(court, text):
    m = MagicMock()
    m.metadata = {"court": court, "text": text}
    return m


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-047 -- argument_reputation only retrieves RAG grounding for
# the first 5 of up to 10 arguments; args 6-10's "relevantne_odluke" claim
# was pure model output with zero disclosure of that fact.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_argument_reputation_discloses_grounded_argument_as_true():
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    raw_llm_json = json.dumps({
        "argumenti_analiza": [
            {"argument": "Zastarelost potraživanja", "uspesnost_procena": 70, "boja": "zelena",
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 5},
        ],
        "ukupna_snaga": 70, "slabosti": [], "preporuceni_redosled": [], "alternativni_argumenti": [],
    })

    def _retrieve(query, k):
        return [_match("Vrhovni sud", "tekst odluke")] if "Zastarelost" in query else []

    payload = cp.ArgumentReputationRequest(tip_spora="radni spor", argumenti=["Zastarelost potraživanja"])

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", True), \
         patch.object(cp, "retrieve_sudska_praksa", side_effect=_retrieve), \
         patch.object(cp, "_pozovi_arg_reputation_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["argumenti_analiza"][0]["rag_grounded"] is True


@pytest.mark.anyio
async def test_argument_reputation_discloses_ungrounded_argument_as_false():
    """No decision matches came back for this argument's query -- must be disclosed as
    ungrounded rather than silently presented the same as a grounded one."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    raw_llm_json = json.dumps({
        "argumenti_analiza": [
            {"argument": "Nepostojeći presedan", "uspesnost_procena": 60, "boja": "žuta",
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 3},
        ],
        "ukupna_snaga": 60, "slabosti": [], "preporuceni_redosled": [], "alternativni_argumenti": [],
    })

    payload = cp.ArgumentReputationRequest(tip_spora="radni spor", argumenti=["Nepostojeći presedan"])

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", True), \
         patch.object(cp, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(cp, "_pozovi_arg_reputation_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["argumenti_analiza"][0]["rag_grounded"] is False


@pytest.mark.anyio
async def test_argument_reputation_arguments_beyond_fifth_never_grounded():
    """Reproduces the debt item's exact scenario: arguments 6-10 never get a retrieval pass
    at all, regardless of what retrieve_sudska_praksa would have returned for them."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    argumenti = [f"Argument {i}" for i in range(1, 7)]  # 6 arguments
    raw_llm_json = json.dumps({
        "argumenti_analiza": [
            {"argument": a, "uspesnost_procena": 70, "boja": "zelena",
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 5}
            for a in argumenti
        ],
        "ukupna_snaga": 70, "slabosti": [], "preporuceni_redosled": [], "alternativni_argumenti": [],
    })

    payload = cp.ArgumentReputationRequest(tip_spora="radni spor", argumenti=argumenti)

    # Every retrieval call would succeed if made -- proves the 6th argument's False comes
    # from never being queried (payload.argumenti[:5]), not from an empty RAG result.
    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", True), \
         patch.object(cp, "retrieve_sudska_praksa", return_value=[_match("Sud", "tekst")]), \
         patch.object(cp, "_pozovi_arg_reputation_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    analiza = result["argumenti_analiza"]
    assert all(a["rag_grounded"] is True for a in analiza[:5])
    assert analiza[5]["rag_grounded"] is False


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-015 -- _critique_and_refine_draft's exception handler (and
# its "reported a problem but returned no fix" branch) silently returned the
# unreviewed draft with no field indicating the critique pass didn't run.
# ═══════════════════════════════════════════════════════════════════════════

def _fake_chat_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return resp


@pytest.mark.anyio
async def test_critique_and_refine_draft_signals_true_when_verified_clean():
    import asyncio
    from routers.drafting import _critique_and_refine_draft

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": False, "izmisljeni_navodi": [], "nedostaju_elementi": [],
        "ispravljen_tekst": "",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        nacrt, critique_applied = await _critique_and_refine_draft(
            "ORIGINALNI NACRT", "[IZVOR-1]\ntekst", "tuzba_naknada_stete", "qid")

    assert nacrt == "ORIGINALNI NACRT"
    assert critique_applied is True


@pytest.mark.anyio
async def test_critique_and_refine_draft_signals_false_on_exception():
    from routers.drafting import _critique_and_refine_draft

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = Exception("mrežna greška")
        nacrt, critique_applied = await _critique_and_refine_draft(
            "ORIGINALNI NACRT", "[IZVOR-1]\ntekst", "tuzba_naknada_stete", "qid")

    assert nacrt == "ORIGINALNI NACRT"
    assert critique_applied is False


@pytest.mark.anyio
async def test_critique_and_refine_draft_signals_false_when_problem_reported_but_unfixed():
    from routers.drafting import _critique_and_refine_draft

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": True, "izmisljeni_navodi": ["nešto sporno"],
        "nedostaju_elementi": [], "ispravljen_tekst": "",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        nacrt, critique_applied = await _critique_and_refine_draft(
            "ORIGINALNI NACRT", "[IZVOR-1]\ntekst", "tuzba_naknada_stete", "qid")

    assert nacrt == "ORIGINALNI NACRT"
    assert critique_applied is False


def test_podnesak_response_includes_critique_applied_field():
    src = open(os.path.join(REPO_ROOT, "routers", "drafting.py"), encoding="utf-8").read()
    marker = 'nacrt, critique_applied = await _critique_and_refine_draft(nacrt, kontekst, req.tip, log_id)'
    assert marker in src
    block = src.split(marker, 1)[1][:2500]
    assert '"critique_applied": critique_applied' in block


def test_frontend_shows_critique_warning_banner_when_not_applied():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    assert "podnesak-preview-critique-warn" in vindex_js
    assert "d.critique_applied === false" in vindex_js
