# -*- coding: utf-8 -*-
"""
Program Beta (2026-08-04) -- Olympus Faza 10 governance nalaz (Backend
Reliability): zero tests exercised routers/case_dna.py::compare_docs's new
_evidence_check path (happy or unhappy). This file closes that gap:
end-to-end shape/coverage of the evidence-check, and defensive handling when
the LLM returns a non-dict JSON top-level value (the exact TypeError risk
Backend Reliability flagged -- the fix wraps the block in isinstance(dict)
+ try/except, this proves it doesn't crash the endpoint).
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
             "path": "/api/predmeti/predmet-1/case-dna/compare", "app": MagicMock(), "state": MagicMock(),
             "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _make_supa(docs):
    """predmeti ownership check returns 1 row; predmet_dokumenti returns `docs`."""
    predmeti_chain = MagicMock()
    for attr in ["select", "eq"]:
        setattr(predmeti_chain, attr, MagicMock(return_value=predmeti_chain))
    predmeti_chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "predmet-1"}]))

    dok_chain = MagicMock()
    for attr in ["select", "eq", "in_"]:
        setattr(dok_chain, attr, MagicMock(return_value=dok_chain))
    dok_chain.execute = MagicMock(return_value=MagicMock(data=docs))

    supa = MagicMock()

    def _table(name):
        return predmeti_chain if name == "predmeti" else dok_chain
    supa.table = MagicMock(side_effect=_table)
    return supa


def _docs():
    return [
        {"id": "d1", "naziv_fajla": "ugovor.pdf", "redni_broj": 1, "tekst_sadrzaj": "Tekst prvog dokumenta."},
        {"id": "d2", "naziv_fajla": "aneks.pdf", "redni_broj": 2, "tekst_sadrzaj": "Tekst drugog dokumenta."},
    ]


class _Req:
    def __init__(self, numbers):
        self.numbers = numbers


@pytest.mark.anyio
async def test_compare_docs_evidence_check_shape_matches_verify_genome_contract():
    """Olympus Faza 10 (Architecture Review nalaz): _evidence_check mora imati
    isti oblik kao verify_genome() -- odluka/hard_flags/soft_flags/provereno_u_ms."""
    from routers import case_dna as cd

    llm_json = json.dumps({
        "razlike_kljucne": ["nema razlike"],
        "kontradikcije": [],
        "slicnosti": ["oba pominju isti ugovor"],
        "koji_je_jaci_dokaz": "DOK-99 je jaci dokaz.",  # DOK-99 ne postoji medju [1,2]
        "preporuka_advokata": "Proveriti original.",
        "zakljucak": "Nejasno.",
    })

    with patch.object(cd, "_get_supa", return_value=_make_supa(_docs())), \
         patch.object(cd, "_pozovi_compare_api", new=AsyncMock(return_value=llm_json)), \
         patch.object(cd.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cd.compare_docs(
            "predmet-1", _Req([1, 2]), _req(), user={"user_id": "u1", "email": "a@b.com"},
        )

    ev = result["analiza"]["_evidence_check"]
    assert set(ev.keys()) == {"odluka", "hard_flags", "soft_flags", "provereno_u_ms"}
    assert ev["odluka"] == "require_review"
    assert len(ev["hard_flags"]) == 1
    assert "DOK-99" in ev["hard_flags"][0]["razlog"]
    assert ev["soft_flags"] == []
    assert isinstance(ev["provereno_u_ms"], (int, float))


@pytest.mark.anyio
async def test_compare_docs_evidence_check_covers_kontradikcije_not_just_koji_je_jaci_dokaz():
    """Olympus Faza 10 (AI Grounding nalaz): invented DOK-XX in kontradikcije
    must be caught too, not just koji_je_jaci_dokaz."""
    from routers import case_dna as cd

    llm_json = json.dumps({
        "razlike_kljucne": [],
        "kontradikcije": ["DOK-07 tvrdi suprotno od DOK-01."],  # DOK-07 invented
        "slicnosti": [],
        "koji_je_jaci_dokaz": "ravnopravni",
        "preporuka_advokata": "x",
        "zakljucak": "x",
    })

    with patch.object(cd, "_get_supa", return_value=_make_supa(_docs())), \
         patch.object(cd, "_pozovi_compare_api", new=AsyncMock(return_value=llm_json)), \
         patch.object(cd.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cd.compare_docs(
            "predmet-1", _Req([1, 2]), _req(), user={"user_id": "u1", "email": "a@b.com"},
        )

    ev = result["analiza"]["_evidence_check"]
    assert ev["odluka"] == "require_review"
    assert ev["hard_flags"][0]["polje"] == "kontradikcije"
    assert "DOK-07" in ev["hard_flags"][0]["razlog"]


@pytest.mark.anyio
async def test_compare_docs_evidence_check_approve_when_all_dok_refs_valid():
    from routers import case_dna as cd

    llm_json = json.dumps({
        "razlike_kljucne": ["DOK-01 pominje X, DOK-02 ne."],
        "kontradikcije": [],
        "slicnosti": [],
        "koji_je_jaci_dokaz": "DOK-02",
        "preporuka_advokata": "x",
        "zakljucak": "x",
    })

    with patch.object(cd, "_get_supa", return_value=_make_supa(_docs())), \
         patch.object(cd, "_pozovi_compare_api", new=AsyncMock(return_value=llm_json)), \
         patch.object(cd.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cd.compare_docs(
            "predmet-1", _Req([1, 2]), _req(), user={"user_id": "u1", "email": "a@b.com"},
        )

    ev = result["analiza"]["_evidence_check"]
    assert ev["odluka"] == "approve"
    assert ev["hard_flags"] == []


@pytest.mark.anyio
async def test_compare_docs_survives_non_dict_llm_json_without_crashing():
    """Olympus Faza 10 (Backend Reliability nalaz): response_format=json_object
    garantuje samo da je vrh objekat po OpenAI ugovoru, ali test dokazuje da
    CAK I da json.loads vrati ne-dict (npr. u budu?oj regresiji), endpoint ne
    puca -- isinstance(dict) guard + sopstveni try/except oko evidence-check
    bloka mora spreciti TypeError da probije do global exception handler-a."""
    from routers import case_dna as cd

    with patch.object(cd, "_get_supa", return_value=_make_supa(_docs())), \
         patch.object(cd, "_pozovi_compare_api", new=AsyncMock(return_value=json.dumps(["ovo", "nije", "dict"]))), \
         patch.object(cd.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await cd.compare_docs(
            "predmet-1", _Req([1, 2]), _req(), user={"user_id": "u1", "email": "a@b.com"},
        )

    # analiza je lista (LLM ne posluje po ugovoru) -- endpoint i dalje vraca
    # 200 sa raw analizom, bez _evidence_check (guard ga je preskocio, ne pukao).
    assert result["analiza"] == ["ovo", "nije", "dict"]
