# -*- coding: utf-8 -*-
"""Tests for Multi-lawyer collaboration (routers/saradnja.py)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request(path="/api/saradnja"):
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _vlasnik():
    return {"user_id": "uid-vlasnik-001", "email": "vlasnik@advokatska.rs", "role": "advokat"}


def _saradnik_user():
    return {"user_id": "uid-saradnik-002", "email": "kolega@advokatska.rs", "role": "advokat"}


_PREDMET_ID = "pred-xyz-789"

_PREDMET_ROW = {"id": _PREDMET_ID, "naziv": "Spor o naknadi štete", "status": "aktivan"}

_SARADNIK_PROFILE = {"id": "uid-saradnik-002", "email": "kolega@advokatska.rs"}


def _build_supa(
    predmet=_PREDMET_ROW,
    saradnik_profile=_SARADNIK_PROFILE,
    saradnici=None,
    dodele=None,
    saradnja_row=None,
    uloga_row=None,
):
    mock = MagicMock()

    def _table(name):
        t = MagicMock()

        if name == "predmeti":
            sel = MagicMock()
            sel.execute.return_value.data = [predmet] if predmet else []
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [predmet] if predmet else []

        elif name == "profiles":
            sel = MagicMock()
            sel.execute.return_value.data = [saradnik_profile] if saradnik_profile else []
            t.select.return_value.eq.return_value.limit.return_value = sel

        elif name == "predmet_saradnici":
            # upsert
            ups = MagicMock()
            ups.execute.return_value.data = [{"id": "sar-id-001"}]
            t.upsert.return_value = ups
            # delete
            del_m = MagicMock()
            del_m.execute.return_value.data = [{"id": "sar-id-001"}]
            t.delete.return_value.eq.return_value.eq.return_value.eq.return_value = del_m
            # select (lista saradnika)
            sel2 = MagicMock()
            sel2.execute.return_value.data = saradnici or []
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = saradnici or []
            # select (moji predmeti — filtrira po saradnik_user_id)
            sel3 = MagicMock()
            sel3.execute.return_value.data = dodele or []
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = dodele or []
            # select (uloga)
            sel4 = MagicMock()
            sel4.execute.return_value.data = [uloga_row] if uloga_row else []
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [uloga_row] if uloga_row else []

        return t

    mock.table.side_effect = _table
    return mock


# ─── Request model validacija ─────────────────────────────────────────────────

def test_dodaj_req_valid():
    from routers.saradnja import DodajSaradnikaReq
    req = DodajSaradnikaReq(saradnik_email="kolega@firma.rs", uloga="saradnja")
    assert req.uloga == "saradnja"


def test_dodaj_req_email_prekratak():
    from pydantic import ValidationError
    from routers.saradnja import DodajSaradnikaReq
    with pytest.raises(ValidationError):
        DodajSaradnikaReq(saradnik_email="ab")


# ─── POST /api/saradnja/dodaj ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_dodaj_saradnika_uspesno():
    from routers.saradnja import dodaj_saradnika, DodajSaradnikaReq

    body = DodajSaradnikaReq(saradnik_email="kolega@advokatska.rs", uloga="saradnja")

    with patch("routers.saradnja._get_supa", return_value=_build_supa()):
        result = await dodaj_saradnika(_PREDMET_ID, body, _fake_request(), _vlasnik())

    assert result["ok"] is True
    assert result["uloga"] == "saradnja"
    assert result["saradnik_uid"] == "uid-saradnik-002"


@pytest.mark.anyio
async def test_dodaj_saradnika_predmet_not_found():
    from fastapi import HTTPException
    from routers.saradnja import dodaj_saradnika, DodajSaradnikaReq

    body = DodajSaradnikaReq(saradnik_email="kolega@advokatska.rs", uloga="citanje")
    supa = _build_supa(predmet=None)

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return t
    supa.table.side_effect = _table

    with patch("routers.saradnja._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await dodaj_saradnika("nonexistent", body, _fake_request(), _vlasnik())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_dodaj_saradnika_sebe_blokira():
    """Vlasnik ne može dodati samog sebe kao saradnika."""
    from fastapi import HTTPException
    from routers.saradnja import dodaj_saradnika, DodajSaradnikaReq

    body = DodajSaradnikaReq(saradnik_email="vlasnik@advokatska.rs", uloga="citanje")

    with patch("routers.saradnja._get_supa", return_value=_build_supa()):
        with pytest.raises(HTTPException) as exc:
            await dodaj_saradnika(_PREDMET_ID, body, _fake_request(), _vlasnik())

    assert exc.value.status_code == 400
    assert "sebe" in exc.value.detail.lower()


@pytest.mark.anyio
async def test_dodaj_saradnika_email_not_found():
    """Email koji nije registrovan → 404."""
    from fastapi import HTTPException
    from routers.saradnja import dodaj_saradnika, DodajSaradnikaReq

    body = DodajSaradnikaReq(saradnik_email="nepostoji@nowhere.rs", uloga="citanje")

    with patch("routers.saradnja._get_supa", return_value=_build_supa(saradnik_profile=None)):
        with pytest.raises(HTTPException) as exc:
            await dodaj_saradnika(_PREDMET_ID, body, _fake_request(), _vlasnik())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_dodaj_saradnika_invalid_uloga():
    """Nevalida uloga → 400."""
    from fastapi import HTTPException
    from routers.saradnja import dodaj_saradnika, DodajSaradnikaReq

    body = DodajSaradnikaReq(saradnik_email="kolega@advokatska.rs", uloga="superadmin")

    with patch("routers.saradnja._get_supa", return_value=_build_supa()):
        with pytest.raises(HTTPException) as exc:
            await dodaj_saradnika(_PREDMET_ID, body, _fake_request(), _vlasnik())

    assert exc.value.status_code == 400


# ─── DELETE /api/saradnja/ukloni ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_ukloni_saradnika_uspesno():
    from routers.saradnja import ukloni_saradnika

    with patch("routers.saradnja._get_supa", return_value=_build_supa()):
        result = await ukloni_saradnika(
            _PREDMET_ID, "uid-saradnik-002", _fake_request(), _vlasnik()
        )

    assert result["ok"] is True


@pytest.mark.anyio
async def test_ukloni_saradnika_nije_vlasnik():
    """Saradnik ne može ukloniti drugog saradnika."""
    from fastapi import HTTPException
    from routers.saradnja import ukloni_saradnika

    supa = _build_supa(predmet=None)

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return t
    supa.table.side_effect = _table

    with patch("routers.saradnja._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await ukloni_saradnika(
                _PREDMET_ID, "uid-saradnik-002", _fake_request(), _saradnik_user()
            )

    assert exc.value.status_code == 404


# ─── GET /api/saradnja/saradnici ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_lista_saradnika_prazna():
    from routers.saradnja import lista_saradnika

    with patch("routers.saradnja._get_supa", return_value=_build_supa(saradnici=[])):
        result = await lista_saradnika(_PREDMET_ID, _fake_request(), _vlasnik())

    assert result["saradnici"] == []


@pytest.mark.anyio
async def test_lista_saradnika_sa_rezultatima():
    saradnici_rows = [
        {"id": "sar-1", "saradnik_user_id": "uid-saradnik-002", "uloga": "saradnja", "created_at": "2026-06-01T10:00:00"},
    ]

    from routers.saradnja import lista_saradnika

    with patch("routers.saradnja._get_supa", return_value=_build_supa(saradnici=saradnici_rows)):
        result = await lista_saradnika(_PREDMET_ID, _fake_request(), _vlasnik())

    assert len(result["saradnici"]) == 1
    assert result["saradnici"][0]["uloga"] == "saradnja"


# ─── GET /api/saradnja/moji-predmeti ─────────────────────────────────────────

@pytest.mark.anyio
async def test_moji_deljeni_predmeti_prazan():
    from routers.saradnja import moji_deljeni_predmeti

    with patch("routers.saradnja._get_supa", return_value=_build_supa(dodele=[])):
        result = await moji_deljeni_predmeti(_fake_request(), _saradnik_user())

    assert result["predmeti"] == []


@pytest.mark.anyio
async def test_moji_deljeni_predmeti_sa_rezultatima():
    dodele = [
        {"predmet_id": _PREDMET_ID, "uloga": "saradnja", "owner_user_id": "uid-vlasnik-001", "created_at": "2026-06-01"},
    ]
    predmet_result = [{"id": _PREDMET_ID, "naziv": "Spor o naknadi štete", "opis": "", "tip": "gradjansko", "status": "aktivan"}]

    from routers.saradnja import moji_deljeni_predmeti

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmet_saradnici":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = dodele
        elif name == "predmeti":
            t.select.return_value.in_.return_value.execute.return_value.data = predmet_result
        return t
    mock.table.side_effect = _table

    with patch("routers.saradnja._get_supa", return_value=mock):
        result = await moji_deljeni_predmeti(_fake_request(), _saradnik_user())

    assert len(result["predmeti"]) == 1
    assert result["predmeti"][0]["uloga"] == "saradnja"
    assert result["predmeti"][0]["naziv"] == "Spor o naknadi štete"


# ─── GET /api/saradnja/uloga ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_uloga_vlasnik():
    from routers.saradnja import moja_uloga_na_predmetu

    with patch("routers.saradnja._get_supa", return_value=_build_supa()):
        result = await moja_uloga_na_predmetu(_PREDMET_ID, _fake_request(), _vlasnik())

    assert result["uloga"] == "vlasnik"


@pytest.mark.anyio
async def test_uloga_saradnik():
    from routers.saradnja import moja_uloga_na_predmetu

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            # nije vlasnik
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        elif name == "predmet_saradnici":
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"uloga": "vodenje"}]
        return t
    mock.table.side_effect = _table

    with patch("routers.saradnja._get_supa", return_value=mock):
        result = await moja_uloga_na_predmetu(_PREDMET_ID, _fake_request(), _saradnik_user())

    assert result["uloga"] == "vodenje"


@pytest.mark.anyio
async def test_uloga_nema_pristupa():
    from routers.saradnja import moja_uloga_na_predmetu

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        return t
    mock.table.side_effect = _table

    with patch("routers.saradnja._get_supa", return_value=mock):
        result = await moja_uloga_na_predmetu("strani-predmet", _fake_request(), _saradnik_user())

    assert result["uloga"] is None
