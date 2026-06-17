# -*- coding: utf-8 -*-
"""Tests for POST /api/praksa/slicni-predmeti (Semantic Precedent Matching)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": "/api/praksa/slicni-predmeti",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "u-001", "email": "test@vindex.rs", "role": "advokat"}


def _pinecone_match(dn: str, court: str = "VKS", date: str = "2024-01-10",
                    matter: str = "Građanska", text: str = "Tekst odluke", score: float = 0.70):
    m = MagicMock()
    m.id = f"id-{dn}"
    m.score = score
    m.metadata = {
        "decision_number": dn,
        "court": court,
        "decision_date": date,
        "matter": matter,
        "text": text,
    }
    return m


_MATCHES = [
    _pinecone_match("Rev 101/2024", text="Otkaz ugovora o radu tužiocu", score=0.72),
    _pinecone_match("Rev 202/2023", text="Prestanak radnog odnosa invalidnost", score=0.68),
    _pinecone_match("Rev 303/2022", text="Zarada i beneficije zaposlenog", score=0.65),
]

_PROCESSED = [
    {"decision_number": "Rev 101/2024", "court": "VKS", "date": "2024-01-10",
     "matter": "Građanska", "text": "Otkaz ugovora o radu tužiocu", "score": 0.72},
    {"decision_number": "Rev 202/2023", "court": "VKS", "date": "2023-05-20",
     "matter": "Građanska", "text": "Prestanak radnog odnosa invalidnost", "score": 0.68},
    {"decision_number": "Rev 303/2022", "court": "VKS", "date": "2022-11-01",
     "matter": "Građanska", "text": "Zarada i beneficije zaposlenog", "score": 0.65},
]

_GPT_RESP = json.dumps({
    "slicni": [
        {"decision_number": "Rev 101/2024", "slicnost_pct": 88, "slicnost_opis": "Isti pravni osnov — otkaz ugovora o radu."},
        {"decision_number": "Rev 202/2023", "slicnost_pct": 70, "slicnost_opis": "Sličan ishod po pitanju prestanka radnog odnosa."},
        {"decision_number": "Rev 303/2022", "slicnost_pct": 45, "slicnost_opis": "Marginalno relevantna za pitanje zarade."},
    ]
})


def _patch_retrieve():
    return patch("app.services.retrieve.retrieve_sudska_praksa", return_value=_MATCHES)


def _patch_process():
    return patch("app.services.retrieve.process_praksa_chunks", return_value=_PROCESSED)


def _patch_gpt(content=_GPT_RESP):
    resp = MagicMock()
    resp.choices[0].message.content = content
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return patch("openai.OpenAI", return_value=client)


# ─── Request model validacija ─────────────────────────────────────────────────

def test_req_model_valid():
    from routers.praksa import SlicniPredmetiReq
    req = SlicniPredmetiReq(
        cinjenice="Tužilac je dobio otkaz ugovora o radu bez obrazloženja.",
        pravno_pitanje="Da li je otkaz zakonit?",
        top_k=5,
    )
    assert req.top_k == 5
    assert "otkaz" in req.cinjenice


def test_req_model_cinjenice_prekratke():
    from routers.praksa import SlicniPredmetiReq
    with pytest.raises(ValidationError):
        SlicniPredmetiReq(cinjenice="Kratko")


def test_req_model_top_k_max():
    from routers.praksa import SlicniPredmetiReq
    with pytest.raises(ValidationError):
        SlicniPredmetiReq(
            cinjenice="Validan opis činjenica koji je dovoljno dug za validaciju.",
            top_k=99,
        )


def test_req_model_top_k_min():
    from routers.praksa import SlicniPredmetiReq
    with pytest.raises(ValidationError):
        SlicniPredmetiReq(
            cinjenice="Validan opis činjenica koji je dovoljno dug za validaciju.",
            top_k=0,
        )


# ─── _slicni_predmeti_sync logika ────────────────────────────────────────────

def test_sync_vraca_rangirane_rezultate():
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.",
            "Da li je otkaz zakonit?",
            top_k=3,
        )

    assert result["ukupno_pronadjeno"] == 3
    slicni = result["slicni"]
    assert slicni[0]["decision_number"] == "Rev 101/2024"
    assert slicni[0]["slicnost_pct"] == 88
    assert "otkaz" in slicni[0]["slicnost_opis"].lower()
    assert slicni[0]["score"] == 0.72


def test_sync_sortira_po_slicnosti():
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.", None, top_k=3,
        )

    pcts = [d["slicnost_pct"] for d in result["slicni"]]
    assert pcts == sorted(pcts, reverse=True)


def test_sync_top_k_ogranicava_izlaz():
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.", None, top_k=2,
        )

    assert len(result["slicni"]) <= 2


def test_sync_prazni_rezultati_kad_nema_kandidata():
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=[]):
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.", None, top_k=5,
        )

    assert result["ukupno_pronadjeno"] == 0
    assert result["slicni"] == []


def test_sync_gpt_greska_ne_pada():
    """Ako GPT baci grešku → endpoint ne puca, vraća vektorske rezultate."""
    from routers.praksa import _slicni_predmeti_sync

    resp = MagicMock()
    resp.choices[0].message.content = "nije json"
    broken_client = MagicMock()
    broken_client.chat.completions.create.return_value = resp

    with _patch_retrieve(), _patch_process(), \
         patch("openai.OpenAI", return_value=broken_client):
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.", None, top_k=5,
        )

    # Mora da vrati nešto, ne baci izuzetak
    assert "slicni" in result
    assert isinstance(result["slicni"], list)


def test_sync_query_used_sadrzi_cinjenice():
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.",
            "Da li je otkaz zakonit?",
            top_k=3,
        )

    assert "otkaz" in result["query_used"].lower()


def test_sync_metadata_polja_prisutna():
    """Svaka stavka ima decision_number, court, decision_date, score."""
    from routers.praksa import _slicni_predmeti_sync

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = _slicni_predmeti_sync(
            "Tužilac dobio otkaz ugovora o radu bez obrazloženja.", None, top_k=3,
        )

    for item in result["slicni"]:
        assert "decision_number" in item
        assert "court" in item
        assert "decision_date" in item
        assert "score" in item
        assert "slicnost_pct" in item
        assert "slicnost_opis" in item


# ─── HTTP endpoint testovi ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_endpoint_vraca_200():
    from routers.praksa import slicni_predmeti, SlicniPredmetiReq

    req_body = SlicniPredmetiReq(
        cinjenice="Tužilac dobio otkaz ugovora o radu bez obrazloženja od strane poslodavca.",
        pravno_pitanje="Da li je otkaz zakonit?",
        top_k=3,
    )

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = await slicni_predmeti(req_body, _fake_request(), _fake_user())

    assert result["ukupno_pronadjeno"] > 0
    assert len(result["slicni"]) <= 3


@pytest.mark.anyio
async def test_endpoint_bez_pravnog_pitanja():
    from routers.praksa import slicni_predmeti, SlicniPredmetiReq

    req_body = SlicniPredmetiReq(
        cinjenice="Tužilac dobio otkaz ugovora o radu bez obrazloženja od strane poslodavca.",
    )

    with _patch_retrieve(), _patch_process(), _patch_gpt():
        result = await slicni_predmeti(req_body, _fake_request(), _fake_user())

    assert "slicni" in result
