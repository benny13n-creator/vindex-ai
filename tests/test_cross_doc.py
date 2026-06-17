# -*- coding: utf-8 -*-
"""Tests for POST /api/analiza/cross-doc (Cross-Document Analysis)"""
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
        "path": "/api/analiza/cross-doc",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "u-001", "email": "test@vindex.rs", "role": "advokat"}


_DOC_A = {
    "naziv": "Ugovor o radu",
    "tekst": "Zaposleni je obavezan da radi 8 sati dnevno. Otkaz se daje sa 15 dana otkaznog roka.",
}
_DOC_B = {
    "naziv": "Interni pravilnik",
    "tekst": "Otkazni rok iznosi 30 dana za sve zaposlene. Radno vreme je 8 sati dnevno.",
}
_DOC_C = {
    "naziv": "Ponuda za posao",
    "tekst": "Radno vreme je 40 sati nedeljno. Otkazni rok nije naveden.",
}

_GPT_RESP = {
    "rezime": "Postoji konflikt između Ugovora o radu i Pravilnika u dužini otkaznog roka.",
    "konflikti": [
        {
            "dokument_a": "Ugovor o radu",
            "dokument_b": "Interni pravilnik",
            "opis": "Otkazni rok u ugovoru je 15 dana, a u pravilniku 30 dana.",
            "ozbiljnost": "visoka",
        }
    ],
    "slicnosti": [
        {
            "dokumenti": ["Ugovor o radu", "Interni pravilnik"],
            "opis": "Oba dokumenta propisuju 8 sati radnog dana.",
        }
    ],
    "preporuke": [
        {
            "prioritet": 1,
            "akcija": "Uskladiti otkazni rok u ugovoru sa pravilnikom.",
            "obrazloženje": "Pravilnik ima prednost kao interni akt poslodavca.",
        }
    ],
    "pravni_zakljucak": "Ugovor o radu i Pravilnik su u konfliktu po pitanju otkaznog roka.",
}


def _patch_gpt(content=None):
    if content is None:
        content = json.dumps(_GPT_RESP)
    resp = MagicMock()
    resp.choices[0].message.content = content
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return patch("openai.OpenAI", return_value=client)


# ─── Validacija modela ────────────────────────────────────────────────────────

def test_req_model_validan():
    from routers.cross_doc import CrossDocReq, DokumentUnos
    req = CrossDocReq(
        dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)],
        pravno_pitanje="Da li postoji konflikt između otkaznih rokova?",
    )
    assert len(req.dokumenti) == 2


def test_req_model_jedan_dokument_odbijen():
    from routers.cross_doc import CrossDocReq, DokumentUnos
    with pytest.raises(ValidationError):
        CrossDocReq(
            dokumenti=[DokumentUnos(**_DOC_A)],
            pravno_pitanje="Da li postoji konflikt?",
        )


def test_req_model_vise_od_5_dokumenata():
    from routers.cross_doc import CrossDocReq, DokumentUnos
    docs = [DokumentUnos(naziv=f"Doc{i}", tekst=f"Tekst dokumenta broj {i} koji je dovoljno dug.") for i in range(6)]
    with pytest.raises(ValidationError):
        CrossDocReq(dokumenti=docs, pravno_pitanje="Da li postoji konflikt?")


def test_req_model_dupli_nazivi_odbijeni():
    from routers.cross_doc import CrossDocReq, DokumentUnos
    with pytest.raises(ValidationError):
        CrossDocReq(
            dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_A)],
            pravno_pitanje="Da li postoji konflikt?",
        )


def test_req_model_kratko_pravno_pitanje():
    from routers.cross_doc import CrossDocReq, DokumentUnos
    with pytest.raises(ValidationError):
        CrossDocReq(
            dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)],
            pravno_pitanje="Kratko",
        )


# ─── _format_dokumenti helper ─────────────────────────────────────────────────

def test_format_dokumenti_sadrzi_nazive():
    from routers.cross_doc import DokumentUnos, _format_dokumenti
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]
    fmt = _format_dokumenti(docs)
    assert "Ugovor o radu" in fmt
    assert "Interni pravilnik" in fmt
    assert "DOKUMENT 1" in fmt
    assert "DOKUMENT 2" in fmt


def test_format_dokumenti_razdvaja_dokumenta():
    from routers.cross_doc import DokumentUnos, _format_dokumenti
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]
    fmt = _format_dokumenti(docs)
    assert "---" in fmt


# ─── _cross_doc_sync logika ───────────────────────────────────────────────────

def test_sync_vraća_strukturirane_sekcije():
    from routers.cross_doc import _cross_doc_sync, DokumentUnos
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]

    with _patch_gpt():
        result = _cross_doc_sync(docs, "Da li postoji konflikt?", None)

    assert result["pravno_pitanje"] == "Da li postoji konflikt?"
    assert result["broj_dokumenata"] == 2
    assert result["nazivi"] == ["Ugovor o radu", "Interni pravilnik"]
    assert len(result["konflikti"]) == 1
    assert result["konflikti"][0]["ozbiljnost"] == "visoka"
    assert len(result["slicnosti"]) == 1
    assert len(result["preporuke"]) == 1
    assert result["preporuke"][0]["prioritet"] == 1
    assert "zakljucak" in result["pravni_zakljucak"].lower() or len(result["pravni_zakljucak"]) > 0


def test_sync_preporuke_sortirane_po_prioritetu():
    from routers.cross_doc import _cross_doc_sync, DokumentUnos

    gpt_data = {
        **_GPT_RESP,
        "preporuke": [
            {"prioritet": 3, "akcija": "Treća akcija", "obrazloženje": "..."},
            {"prioritet": 1, "akcija": "Prva akcija",  "obrazloženje": "..."},
            {"prioritet": 2, "akcija": "Druga akcija", "obrazloženje": "..."},
        ],
    }
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]

    with _patch_gpt(json.dumps(gpt_data)):
        result = _cross_doc_sync(docs, "Analiza konflikata?", None)

    prioriteti = [p["prioritet"] for p in result["preporuke"]]
    assert prioriteti == sorted(prioriteti)


def test_sync_tri_dokumenta():
    from routers.cross_doc import _cross_doc_sync, DokumentUnos
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B), DokumentUnos(**_DOC_C)]

    with _patch_gpt():
        result = _cross_doc_sync(docs, "Koji dokument ima prednost?", "Radno pravo")

    assert result["broj_dokumenata"] == 3
    assert len(result["nazivi"]) == 3


def test_sync_kontekst_opcioni():
    from routers.cross_doc import _cross_doc_sync, DokumentUnos
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]

    with _patch_gpt():
        result = _cross_doc_sync(docs, "Da li postoji konflikt?", None)

    assert result["broj_dokumenata"] == 2


def test_sync_gpt_invalid_json_ne_pada():
    from routers.cross_doc import _cross_doc_sync, DokumentUnos
    docs = [DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)]

    with _patch_gpt("nije json"):
        result = _cross_doc_sync(docs, "Da li postoji konflikt?", None)

    assert result["konflikti"] == []
    assert result["slicnosti"] == []
    assert result["preporuke"] == []


# ─── HTTP endpoint ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_endpoint_uspesno():
    from routers.cross_doc import cross_doc_analiza, CrossDocReq, DokumentUnos

    req_body = CrossDocReq(
        dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)],
        pravno_pitanje="Da li postoji konflikt između otkaznih rokova u ova dva dokumenta?",
    )

    with _patch_gpt():
        result = await cross_doc_analiza(req_body, _fake_request(), _fake_user())

    assert result["broj_dokumenata"] == 2
    assert "konflikti" in result
    assert "slicnosti" in result
    assert "preporuke" in result
    assert "pravni_zakljucak" in result


@pytest.mark.anyio
async def test_endpoint_sa_kontekstom():
    from routers.cross_doc import cross_doc_analiza, CrossDocReq, DokumentUnos

    req_body = CrossDocReq(
        dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)],
        pravno_pitanje="Da li postoji konflikt između otkaznih rokova u ova dva dokumenta?",
        kontekst="Zaposleni sa 5 godina staža",
    )

    with _patch_gpt():
        result = await cross_doc_analiza(req_body, _fake_request(), _fake_user())

    assert result["pravno_pitanje"] is not None


@pytest.mark.anyio
async def test_endpoint_gpt_greška_vraća_500():
    from fastapi.responses import JSONResponse
    from routers.cross_doc import cross_doc_analiza, CrossDocReq, DokumentUnos

    broken_client = MagicMock()
    broken_client.chat.completions.create.side_effect = Exception("OpenAI timeout")

    req_body = CrossDocReq(
        dokumenti=[DokumentUnos(**_DOC_A), DokumentUnos(**_DOC_B)],
        pravno_pitanje="Da li postoji konflikt između otkaznih rokova u ova dva dokumenta?",
    )

    with patch("openai.OpenAI", return_value=broken_client):
        result = await cross_doc_analiza(req_body, _fake_request(), _fake_user())

    assert isinstance(result, JSONResponse)
    assert result.status_code == 500
