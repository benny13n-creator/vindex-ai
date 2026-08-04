# -*- coding: utf-8 -*-
"""
Program Gamma (2026-08-04) -- routers/court_predictor.py's argument_reputation
and judge_profile prompts each state a checkable, deterministic derivation
rule for a categorical field ('boja' from uspesnost_procena; 'pouzdanost_
profila' from ukupno_odluka_analizirano) but the raw LLM output was returned
unrecomputed -- the same "LLM rezonuje, platforma racuna" defect class
Program Beta fixed for strategija.py::sistemsko_upozorenje. Neither field was
audited by Program Beta (its own Court Predictor coverage was scoped to
confidence_check only). judge_profile's pouzdanost_profila was actually
ALREADY partly code-derived (niska/visoka), just missing the middle band
(5-9 odluka), which silently passed the raw LLM value through -- closed here.
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
    c.execute = MagicMock(return_value=MagicMock(data=[{"id": "row-1"}]))
    return c


@pytest.mark.anyio
async def test_argument_reputation_boja_derived_not_raw_llm():
    """LLM returns an internally-inconsistent 'boja' (says 'crvena' for a
    high score) -- the endpoint must override it using the prompt's own
    stated rule (>=65 zelena, 35-64 zuta, <35 crvena), not trust the raw value."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    raw_llm_json = json.dumps({
        "argumenti_analiza": [
            {"argument": "Zastarelost potraživanja", "uspesnost_procena": 80, "boja": "crvena",  # WRONG per rule
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 5},
            {"argument": "Nedostatak forme", "uspesnost_procena": 40, "boja": "crvena",  # also wrong (should be zuta)
             "obrazlozenje": "x", "preporuka": "x", "relevantne_odluke": 3},
        ],
        "ukupna_snaga": 60, "slabosti": [], "preporuceni_redosled": [], "alternativni_argumenti": [],
    })

    payload = cp.ArgumentReputationRequest(tip_spora="radni spor", argumenti=["Zastarelost potraživanja", "Nedostatak forme"])

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", False), \
         patch.object(cp, "_pozovi_arg_reputation_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.argument_reputation(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    analiza = result["argumenti_analiza"]
    assert analiza[0]["boja"] == "zelena"  # 80 >= 65
    assert analiza[1]["boja"] == "žuta"    # 35 <= 40 < 65


@pytest.mark.anyio
async def test_judge_profile_pouzdanost_srednja_band_no_longer_passthrough():
    """Olympus Faza 10-shaped gap: 5-9 odluka fell out of the existing
    if/elif and silently kept whatever raw value the LLM returned. Must now
    be explicitly 'srednja'."""
    from routers import court_predictor as cp

    supa = MagicMock()
    supa.table = MagicMock(return_value=_insert_chain())

    raw_llm_json = json.dumps({
        "sud": "Viši sud u Beogradu", "sudija": "nije naveden",
        "ukupno_odluka_analizirano": 0,  # overwritten by code from odluke_count
        "pouzdanost_profila": "visoka",  # WRONG -- must become 'srednja' for 5-9 odluka
        "obrasci_odlucivanja": [], "preporuke": [],
    })

    payload = cp.JudgeProfileRequest(sud="Viši sud u Beogradu", tip_postupka="parnica")

    fake_matches = [MagicMock(metadata={"text": "presuda tekst", "court": "Viši sud u Beogradu"}) for _ in range(7)]

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_RAG_AVAILABLE", True), \
         patch.object(cp, "retrieve_sudska_praksa", return_value=fake_matches), \
         patch.object(cp, "_pozovi_judge_profile_api", return_value=raw_llm_json), \
         patch.object(cp.UsageService, "consume", new=AsyncMock(return_value=5)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cp.judge_profile(_req(), payload, user={"user_id": "u1", "email": "a@b.com"})

    assert result["ukupno_odluka_analizirano"] == 7
    assert result["pouzdanost_profila"] == "srednja"
