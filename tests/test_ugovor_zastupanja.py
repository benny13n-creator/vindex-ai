# -*- coding: utf-8 -*-
"""Tests for GET /api/ugovor-zastupanja/tipovi and POST /api/ugovor-zastupanja/generiši"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user():
    return {"user_id": "uid-001", "email": "test@vindex.rs", "role": "advokat"}


def _fake_request():
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": "/api/ugovor-zastupanja/generiši",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _build_supa(pred: dict | None, insert_ok: bool = True):
    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            single = MagicMock()
            single.execute.return_value.data = pred
            t.select.return_value.eq.return_value.eq.return_value.single.return_value = single
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = single
        elif name == "predmet_hronologija":
            ins = MagicMock()
            if insert_ok:
                ins.execute.return_value.data = [{}]
            else:
                ins.execute.side_effect = Exception("DB error")
            t.insert.return_value = ins
        return t

    mock.table.side_effect = _table
    return mock


# ─── T1: GET tipovi — vraća oblasti i tipove nagrade ─────────────────────────

@pytest.mark.anyio
async def test_get_tipovi():
    from routers.ugovor_zastupanja import get_tipovi_ugovora
    result = await get_tipovi_ugovora()
    oblasti = {o["kljuc"] for o in result["oblasti_prava"]}
    nagrade = {n["kljuc"] for n in result["tipovi_nagrade"]}
    assert "parnicno" in oblasti
    assert "krivicno" in oblasti
    assert "pausal" in nagrade
    assert "po_satu" in nagrade
    assert "po_aks_tarifi" in nagrade


# ─── T2: Generisanje bez predmet_id ──────────────────────────────────────────

@pytest.mark.anyio
async def test_generiši_bez_predmeta():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Petar Petrović",
        klijent_adresa="Bulevar Kralja Aleksandra 1, Beograd",
        advokat_ime="Marko Marković",
        predmet_opis="Naknada štete iz saobraćajne nezgode od 12.03.2026",
        oblast_prava="parnicno",
        nagrada_tip="pausal",
        nagrada_iznos="50.000 RSD",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is False
    assert result["predmet_id"] is None
    tekst = result["ugovor_tekst"]
    assert "Petar Petrović" in tekst
    assert "Marko Marković" in tekst
    assert "Naknada štete" in tekst
    assert "Parnični postupak" in tekst
    assert "50.000 RSD" in tekst
    assert "Paušalna naknada" in tekst
    assert "Vindex AI" in tekst


# ─── T3: Generisanje sa predmet_id — čuva u hronologiju ─────────────────────

@pytest.mark.anyio
async def test_generiši_sa_predmetom():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    pred = {"id": "pred-001", "naziv": "Šteta Petrović"}
    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Petar Petrović",
        advokat_ime="Marko Marković",
        predmet_opis="Naknada štete",
        predmet_id="pred-001",
    )

    with patch("routers.ugovor_zastupanja._get_supa", return_value=_build_supa(pred)):
        result = await post_generiši_ugovor(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is True
    assert result["predmet_id"] == "pred-001"


# ─── T4: Predmet ne postoji → 404 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_generiši_predmet_not_found():
    from fastapi import HTTPException
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Petar Petrović",
        advokat_ime="Marko Marković",
        predmet_opis="Naknada štete",
        predmet_id="nonexistent",
    )

    with patch("routers.ugovor_zastupanja._get_supa", return_value=_build_supa(None)):
        with pytest.raises(HTTPException) as exc:
            await post_generiši_ugovor(body, _fake_request(), _fake_user())

    assert exc.value.status_code == 404


# ─── T5: Validacija — nepoznata oblast_prava ─────────────────────────────────

def test_ugovor_req_invalid_oblast():
    from pydantic import ValidationError
    from routers.ugovor_zastupanja import UgovorZastupanjaReq

    with pytest.raises(ValidationError):
        UgovorZastupanjaReq(
            klijent_ime_prezime="Test",
            advokat_ime="Test",
            predmet_opis="Test predmet",
            oblast_prava="nepostojeca_oblast",
        )


# ─── T6: Validacija — nepoznat nagrada_tip ───────────────────────────────────

def test_ugovor_req_invalid_nagrada():
    from pydantic import ValidationError
    from routers.ugovor_zastupanja import UgovorZastupanjaReq

    with pytest.raises(ValidationError):
        UgovorZastupanjaReq(
            klijent_ime_prezime="Test",
            advokat_ime="Test",
            predmet_opis="Test predmet",
            nagrada_tip="zlatni_paket",
        )


# ─── T7: Satnica — tekst nagrade sadrži pravi opis ───────────────────────────

@pytest.mark.anyio
async def test_generiši_satnica():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Ana Anić",
        advokat_ime="Jovan Jovanović",
        predmet_opis="Radni spor — nezakoniti otkaz",
        oblast_prava="radno",
        nagrada_tip="po_satu",
        nagrada_iznos="3.000 RSD/h",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())

    tekst = result["ugovor_tekst"]
    assert "Radno pravo" in tekst
    assert "Satnica" in tekst
    assert "3.000 RSD/h" in tekst
    assert "mesečno" in tekst


# ─── T8: Firma klijenta se prikazuje u ugovoru ───────────────────────────────

@pytest.mark.anyio
async def test_generiši_firma_klijenta():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Dragan Dragić",
        klijent_firma="Dragić DOO",
        advokat_ime="Svetlana Svetlić",
        predmet_opis="Privredni spor — neispunjenje ugovora",
        oblast_prava="privredno",
        nagrada_tip="po_aks_tarifi",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())
    tekst = result["ugovor_tekst"]
    assert "Dragić DOO" in tekst
    assert "Privredno pravo" in tekst
    assert "Advokatska tarifa" in tekst or "AKS" in tekst


# ─── T9: DB greška pri upisivanju — sacuvano=False, ne puca ──────────────────

@pytest.mark.anyio
async def test_generiši_db_greška_non_fatal():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    pred = {"id": "pred-xyz", "naziv": "Test"}
    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Test Klijent",
        advokat_ime="Test Advokat",
        predmet_opis="Testni predmet spor",
        predmet_id="pred-xyz",
    )

    with patch("routers.ugovor_zastupanja._get_supa", return_value=_build_supa(pred, insert_ok=False)):
        result = await post_generiši_ugovor(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is False
    assert "Vindex AI" in result["ugovor_tekst"]


# ─── T10: Datum se prikazuje u srpskom formatu ───────────────────────────────

@pytest.mark.anyio
async def test_generiši_datum_format():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Test Lice",
        advokat_ime="Test Advokat",
        predmet_opis="Testni predmet datum",
        datum_zakljucenja="2026-06-17",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())
    assert result["datum_zakljucenja"] == "17.06.2026"
    assert "17.06.2026" in result["ugovor_tekst"]


# ─── T11: Broj ugovora se generiše ───────────────────────────────────────────

@pytest.mark.anyio
async def test_generiši_broj():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Test Lice",
        advokat_ime="Test Advokat",
        predmet_opis="Testni predmet broj",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())
    assert "/2026" in result["broj"]
    assert result["broj"] in result["ugovor_tekst"]


# ─── T12: Pro bono nagrada ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_generiši_pro_bono():
    from routers.ugovor_zastupanja import UgovorZastupanjaReq, post_generiši_ugovor

    body = UgovorZastupanjaReq(
        klijent_ime_prezime="Test Lice",
        advokat_ime="Test Advokat",
        predmet_opis="Testni predmet probono",
        nagrada_tip="besplatno",
    )

    result = await post_generiši_ugovor(body, _fake_request(), _fake_user())
    assert "pro bono" in result["ugovor_tekst"].lower()
