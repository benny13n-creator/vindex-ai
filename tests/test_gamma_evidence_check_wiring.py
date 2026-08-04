# -*- coding: utf-8 -*-
"""
Program Gamma (2026-08-04) -- widens the Program Beta-proven "referenced
entity must exist in scope" evidence-check pattern (originally
validate_dok_reference, wired into routers/case_dna.py::compare_docs) to two
more AI-decision endpoints found with zero of the three Evidence Chain
links (provenance/evidence-validation/UI trust signal): routers/
evidence_graph.py::generisi_graf (contradiction/POMINJE/etc. edges that can
reference an invented node) and routers/case_commander.py::_cross_case_
analiza (cross-case findings that can reference an invented/misattributed
predmet). Same fail-soft convention as verify_genome/compare_docs -- never
blocks the response, just surfaces the flag.
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
             "path": "/api/evidence-graph/generisi", "app": MagicMock(), "state": MagicMock(),
             "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _chain(data=None):
    c = MagicMock()
    for attr in ["select", "eq", "order", "limit", "insert"]:
        setattr(c, attr, MagicMock(return_value=c))
    c.execute = MagicMock(return_value=MagicMock(data=data))
    return c


# ─── evidence_graph.py::generisi_graf ──────────────────────────────────────

@pytest.mark.anyio
async def test_generisi_graf_flags_edge_referencing_invented_node():
    from routers import evidence_graph as eg

    predmet_chain = _chain(data=[{"id": "p1", "naziv": "Test", "tip": "parnica", "oblast": "", "opis": "",
                                    "tuzilac": "", "tuzeni": ""}])
    empty_chain = _chain(data=[])
    tables = {"predmeti": predmet_chain, "predmet_dokumenti": empty_chain,
              "predmet_komentari": empty_chain, "rocista": empty_chain,
              "evidence_grafovi": _chain(data=None)}
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda n: tables.get(n, empty_chain))

    graf_json = {
        "nodes": [{"id": "lice_01", "label": "Petar", "tip": "lice", "opis": "x"}],
        "edges": [{"izvor": "lice_01", "cilj": "dok_izmisljen", "tip_veze": "OSPORAVA", "opis": "x"}],
    }

    req = eg.GenerisiRequest(predmet_id="p1")

    with patch.object(eg, "_get_supa", return_value=supa), \
         patch.object(eg, "_pozovi_gpt", return_value=graf_json), \
         patch.object(eg.UsageService, "consume", new=AsyncMock(return_value=3)):
        result = await eg.generisi_graf(req, _req(), user={"user_id": "u1", "email": "a@b.com"})

    ev = result["_evidence_check"]
    assert ev["odluka"] == "require_review"
    assert any("dok_izmisljen" in f["razlog"] for f in ev["hard_flags"])


@pytest.mark.anyio
async def test_generisi_graf_approves_when_all_edges_reference_real_nodes():
    from routers import evidence_graph as eg

    predmet_chain = _chain(data=[{"id": "p1", "naziv": "Test", "tip": "parnica", "oblast": "", "opis": "",
                                    "tuzilac": "", "tuzeni": ""}])
    empty_chain = _chain(data=[])
    tables = {"predmeti": predmet_chain, "predmet_dokumenti": empty_chain,
              "predmet_komentari": empty_chain, "rocista": empty_chain,
              "evidence_grafovi": _chain(data=None)}
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda n: tables.get(n, empty_chain))

    graf_json = {
        "nodes": [{"id": "lice_01", "label": "Petar"}, {"id": "dok_01", "label": "Ugovor"}],
        "edges": [{"izvor": "lice_01", "cilj": "dok_01", "tip_veze": "POMINJE", "opis": "x"}],
    }

    req = eg.GenerisiRequest(predmet_id="p1")

    with patch.object(eg, "_get_supa", return_value=supa), \
         patch.object(eg, "_pozovi_gpt", return_value=graf_json), \
         patch.object(eg.UsageService, "consume", new=AsyncMock(return_value=3)):
        result = await eg.generisi_graf(req, _req(), user={"user_id": "u1", "email": "a@b.com"})

    assert result["_evidence_check"]["odluka"] == "approve"
    assert result["_evidence_check"]["hard_flags"] == []


# ─── case_commander.py::_cross_case_analiza ────────────────────────────────

@pytest.mark.anyio
async def test_cross_case_analiza_flags_finding_with_unknown_predmet_prefix():
    from routers import case_commander as cc

    podaci = {"predmeti": [
        {"id": "aaaaaaaa-1111", "naziv": "Predmet A", "tip_postupka": "parnica", "protivnik": "", "sud": "",
         "opis": "", "rokovi": [], "dokumenti": [], "komentari": []},
    ]}

    raw = json.dumps({
        "nalazi": [{
            "tip": "kontradikcija", "predmet_naziv": "Predmet B", "predmet_id_prefix": "ffffffff",  # invented
            "naslov": "x", "opis": "x",
        }],
        "prioritet": {"predmet_naziv": "Predmet A", "predmet_id_prefix": "aaaaaaaa", "razlog": "x"},
        "rezime": "x",
    })

    with patch.object(cc, "_pozovi_cross_case_api", return_value=raw), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rezultat = await cc._cross_case_analiza(podaci, "Advokat Test")

    ev = rezultat["_evidence_check"]
    assert ev["odluka"] == "require_review"
    assert any("ffffffff" in f["razlog"] for f in ev["hard_flags"])


@pytest.mark.anyio
async def test_cross_case_analiza_approves_when_all_refs_valid():
    from routers import case_commander as cc

    podaci = {"predmeti": [
        {"id": "aaaaaaaa-1111", "naziv": "Predmet A", "tip_postupka": "parnica", "protivnik": "", "sud": "",
         "opis": "", "rokovi": [], "dokumenti": [], "komentari": []},
    ]}

    raw = json.dumps({
        "nalazi": [{
            "tip": "rizik", "predmet_naziv": "Predmet A", "predmet_id_prefix": "aaaaaaaa",
            "naslov": "x", "opis": "x",
        }],
        "prioritet": {"predmet_naziv": "Predmet A", "predmet_id_prefix": "aaaaaaaa", "razlog": "x"},
        "rezime": "x",
    })

    with patch.object(cc, "_pozovi_cross_case_api", return_value=raw), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rezultat = await cc._cross_case_analiza(podaci, "Advokat Test")

    assert rezultat["_evidence_check"]["odluka"] == "approve"
    assert rezultat["_evidence_check"]["hard_flags"] == []


@pytest.mark.anyio
async def test_cross_case_analiza_flags_real_prefix_wrong_naziv():
    """Olympus Faza 10 (Evidence Integrity nalaz): REALAN prefiks ali
    POGRESNO pripisan naziv (GPT pomesao dva predmeta u portfoliju) mora
    biti uhvacen -- pre ove popravke bio je arhitektonski nevidljiv."""
    from routers import case_commander as cc

    podaci = {"predmeti": [
        {"id": "aaaaaaaa-1111", "naziv": "Petrović protiv Marković", "tip_postupka": "parnica",
         "protivnik": "", "sud": "", "opis": "", "rokovi": [], "dokumenti": [], "komentari": []},
        {"id": "bbbbbbbb-2222", "naziv": "Jovanović nasledstvo", "tip_postupka": "vanparnica",
         "protivnik": "", "sud": "", "opis": "", "rokovi": [], "dokumenti": [], "komentari": []},
    ]}

    raw = json.dumps({
        "nalazi": [{
            # realan prefiks (aaaaaaaa postoji) ali pripisan pogresnom nazivu
            "tip": "rizik", "predmet_naziv": "Jovanović nasledstvo", "predmet_id_prefix": "aaaaaaaa",
            "naslov": "x", "opis": "x",
        }],
        "prioritet": None,
        "rezime": "x",
    })

    with patch.object(cc, "_pozovi_cross_case_api", return_value=raw), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rezultat = await cc._cross_case_analiza(podaci, "Advokat Test")

    ev = rezultat["_evidence_check"]
    assert ev["odluka"] == "require_review"
    assert any(f["polje"] == "predmet_naziv" for f in ev["hard_flags"])


# ─── case_dna.py::_delta_hitnost (Fix E — deduplicated inline formula) ─────

def test_delta_hitnost_extracted_helper_matches_original_formula():
    from routers.case_dna import _delta_hitnost

    assert _delta_hitnost({"snaga_delta": 20, "kontr_nove": 0}) == "hitna"        # |20| >= 15
    assert _delta_hitnost({"snaga_delta": -20, "kontr_nove": 0}) == "hitna"       # abs() applied
    assert _delta_hitnost({"snaga_delta": 5, "kontr_nove": 2}) == "hitna"         # kontr_nove > 1
    assert _delta_hitnost({"snaga_delta": 5, "kontr_nove": 0}) == "normalna"
    assert _delta_hitnost({}) == "normalna"
