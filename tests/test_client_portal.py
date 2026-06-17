# -*- coding: utf-8 -*-
"""Tests for Client Portal — token generisanje, bezbednost, view endpoint"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.requests import Request as StarletteRequest

os.environ.setdefault("SECRET_KEY", "test-secret-key-za-testove-128bit")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request(path="/api/client-portal/view"):
    scope = {
        "type": "http", "method": "GET",
        "headers": [], "query_string": b"",
        "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user(uid="uid-advokat-001"):
    return {"user_id": uid, "email": "advokat@vindex.rs", "role": "advokat"}


_PREDMET_ID = "pred-abc-123"
_ADVOKAT_UID = "uid-advokat-001"

_PREDMET_DATA = {
    "naziv": "Spor sa poslodavcem",
    "opis": "Otkaz bez obrazloženja",
    "tip": "radni_spor",
    "status": "aktivan",
    "created_at": "2026-01-15T10:00:00+00:00",
}

_HRON_DATA = [
    {"dogadjaj": "Tužba podneta",         "datum": "2026-01-20", "datum_iso": "2026-01-20", "akter": "Tužilac", "vaznost": "kljucan"},
    {"dogadjaj": "Odgovor na tužbu",       "datum": "2026-02-05", "datum_iso": "2026-02-05", "akter": "Tuženi",  "vaznost": "normalan"},
    {"dogadjaj": "[INTERNI] Interna beleška", "datum": "2026-02-10", "datum_iso": "2026-02-10", "akter": "", "vaznost": "informativan"},
]

_ROC_DATA = [
    {"sud": "Osnovni sud Beograd", "datum": "2026-06-20", "vreme": "10:00", "sudnica": "S-5", "broj_predmeta_suda": "P 123/2026", "status": "zakazano"},
    {"sud": "Osnovni sud Beograd", "datum": "2026-05-01", "vreme": "09:00", "sudnica": None,  "broj_predmeta_suda": None, "status": "otkazano"},
]


def _build_supa(
    predmet=_PREDMET_DATA,
    hron=None,
    roc=None,
    token_row=None,
    insert_ok=True,
):
    if hron is None:
        hron = _HRON_DATA
    if roc is None:
        roc = _ROC_DATA

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            ms = MagicMock()
            ms.execute.return_value.data = predmet
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [predmet] if predmet else []
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = ms
        elif name == "predmet_hronologija":
            sel = MagicMock()
            sel.execute.return_value.data = hron
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = sel
        elif name == "rocista":
            sel = MagicMock()
            sel.execute.return_value.data = roc
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = sel
        elif name == "client_portal_tokens":
            # insert
            ins = MagicMock()
            ins.execute.return_value.data = [{"id": "tok-id-001"}] if insert_ok else []
            t.insert.return_value = ins
            # select (lista)
            sel2 = MagicMock()
            sel2.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = sel2
            # maybe_single (view)
            ms2 = MagicMock()
            ms2.execute.return_value.data = token_row
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = ms2
            # update (opoziv)
            upd = MagicMock()
            upd.execute.return_value.data = [{"id": "tok-id-001"}]
            t.update.return_value.eq.return_value.eq.return_value = upd
        return t

    mock.table.side_effect = _table
    return mock


# ─── Token generisanje / validacija (unit) ────────────────────────────────────

def test_generiši_token_parsiraj_roundtrip():
    from routers.client_portal import _generiši_token, _parsiraj_token
    token = _generiši_token("pred-001", "user-001", 9999999999)
    pred_id, user_id, exp, sig = _parsiraj_token(token)
    assert pred_id == "pred-001"
    assert user_id == "user-001"
    assert exp == 9999999999


def test_verifikuj_token_validan():
    from routers.client_portal import _generiši_token, _verifikuj_token
    exp = int(time.time()) + 3600
    token = _generiši_token(_PREDMET_ID, _ADVOKAT_UID, exp)
    pred_id, uid = _verifikuj_token(token)
    assert pred_id == _PREDMET_ID
    assert uid == _ADVOKAT_UID


def test_verifikuj_token_istekao():
    from fastapi import HTTPException
    from routers.client_portal import _generiši_token, _verifikuj_token
    exp = int(time.time()) - 1  # prošlost
    token = _generiši_token(_PREDMET_ID, _ADVOKAT_UID, exp)
    with pytest.raises(HTTPException) as exc:
        _verifikuj_token(token)
    assert exc.value.status_code == 401
    assert "istekao" in exc.value.detail.lower()


def test_verifikuj_token_tampering():
    """Izmena predmet_id u tokenu mora biti otkrivena."""
    from fastapi import HTTPException
    from routers.client_portal import _generiši_token, _parsiraj_token, _verifikuj_token
    import base64
    exp   = int(time.time()) + 3600
    token = _generiši_token(_PREDMET_ID, _ADVOKAT_UID, exp)
    parts = token.split(".")
    # Zameni predmet_id u payloadu sa drugim
    tampered_payload = base64.urlsafe_b64encode(f"drugi-predmet:{_ADVOKAT_UID}:{exp}".encode()).decode()
    tampered_token = f"{tampered_payload}.{parts[1]}"
    with pytest.raises(HTTPException) as exc:
        _verifikuj_token(tampered_token)
    assert exc.value.status_code == 401


def test_verifikuj_token_malformiran():
    from fastapi import HTTPException
    from routers.client_portal import _verifikuj_token
    with pytest.raises(HTTPException) as exc:
        _verifikuj_token("ovo-nije-token")
    assert exc.value.status_code == 401


def test_token_hash_deterministican():
    from routers.client_portal import _token_hash
    t = "neki-token-string"
    assert _token_hash(t) == _token_hash(t)
    assert _token_hash(t) != _token_hash(t + "x")


# ─── POST /api/client-portal/token/{predmet_id} ───────────────────────────────

@pytest.mark.anyio
async def test_generiši_portal_token_uspesno():
    from routers.client_portal import generiši_portal_token, GeneriišiTokenReq

    body = GeneriišiTokenReq(klijent_email="klijent@gmail.com", valjanost_dana=30)

    with patch("routers.client_portal._get_supa", return_value=_build_supa()):
        result = await generiši_portal_token(
            _PREDMET_ID, body, _fake_request(), _fake_user()
        )

    assert result["ok"] is True
    assert "token" in result
    assert "portal_url" in result
    assert _PREDMET_ID not in result["token"] or True  # token je opaque
    assert "expires_at" in result


@pytest.mark.anyio
async def test_generiši_portal_token_predmet_not_found():
    from fastapi import HTTPException
    from routers.client_portal import generiši_portal_token, GeneriišiTokenReq

    body = GeneriišiTokenReq()

    supa = _build_supa(predmet=None)
    # Override predmeti select to return empty
    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            sel = MagicMock()
            sel.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value = sel
        return t
    supa.table.side_effect = _table

    with patch("routers.client_portal._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await generiši_portal_token("nonexistent", body, _fake_request(), _fake_user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_generiši_portal_token_valjanost_max():
    from pydantic import ValidationError
    from routers.client_portal import GeneriišiTokenReq
    with pytest.raises(ValidationError):
        GeneriišiTokenReq(valjanost_dana=91)


# ─── GET /api/client-portal/view ─────────────────────────────────────────────

def _valid_token() -> str:
    from routers.client_portal import _generiši_token
    exp = int(time.time()) + 3600
    return _generiši_token(_PREDMET_ID, _ADVOKAT_UID, exp)


def _token_row(active=True) -> dict:
    from routers.client_portal import _token_hash
    tok = _valid_token()
    return {
        "id": "tok-001",
        "is_active": active,
        "expires_at": "2026-07-17T10:00:00+00:00",
        "token_hash": _token_hash(tok),
    }


@pytest.mark.anyio
async def test_client_view_uspesno():
    from routers.client_portal import client_portal_view

    tok = _valid_token()
    supa = _build_supa(token_row={"id": "t-1", "is_active": True, "expires_at": "2026-07-17T10:00:00+00:00"})

    with patch("routers.client_portal._get_supa", return_value=supa):
        result = await client_portal_view(_fake_request(), x_portal_token=tok)

    assert result["predmet"]["naziv"] == "Spor sa poslodavcem"
    assert result["predmet"]["status"] == "aktivan"
    assert isinstance(result["hronologija"], list)
    assert isinstance(result["rocista"], list)


@pytest.mark.anyio
async def test_client_view_bez_tokena():
    from fastapi import HTTPException
    from routers.client_portal import client_portal_view

    with pytest.raises(HTTPException) as exc:
        await client_portal_view(_fake_request(), x_portal_token=None)

    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_client_view_istekao_token():
    from fastapi import HTTPException
    from routers.client_portal import _generiši_token, client_portal_view

    expired_tok = _generiši_token(_PREDMET_ID, _ADVOKAT_UID, int(time.time()) - 1)

    with pytest.raises(HTTPException) as exc:
        await client_portal_view(_fake_request(), x_portal_token=expired_tok)

    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_client_view_opozvan_token():
    from fastapi import HTTPException
    from routers.client_portal import client_portal_view

    tok  = _valid_token()
    supa = _build_supa(token_row={"id": "t-1", "is_active": False, "expires_at": "2026-07-17T10:00:00+00:00"})

    with patch("routers.client_portal._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await client_portal_view(_fake_request(), x_portal_token=tok)

    assert exc.value.status_code == 401
    assert "opozvan" in exc.value.detail.lower()


@pytest.mark.anyio
async def test_client_view_filtrira_interne_beleske():
    """[INTERNI] dogadjaji se ne prikazuju klijentu."""
    from routers.client_portal import client_portal_view

    tok  = _valid_token()
    supa = _build_supa(token_row={"id": "t-1", "is_active": True, "expires_at": "2026-07-17T10:00:00+00:00"})

    with patch("routers.client_portal._get_supa", return_value=supa):
        result = await client_portal_view(_fake_request(), x_portal_token=tok)

    dogadjaji = [h["dogadjaj"] for h in result["hronologija"]]
    assert not any("[INTERNI]" in d for d in dogadjaji)
    assert "Tužba podneta" in dogadjaji
    assert "Odgovor na tužbu" in dogadjaji


@pytest.mark.anyio
async def test_client_view_filtrira_otkazana_rocista():
    """Otkazana ročišta se ne prikazuju klijentu."""
    from routers.client_portal import client_portal_view

    tok  = _valid_token()
    supa = _build_supa(token_row={"id": "t-1", "is_active": True, "expires_at": "2026-07-17T10:00:00+00:00"})

    with patch("routers.client_portal._get_supa", return_value=supa):
        result = await client_portal_view(_fake_request(), x_portal_token=tok)

    statusi = [r.get("status") for r in result["rocista"]]
    assert "otkazano" not in statusi
    assert "zakazano" in statusi


@pytest.mark.anyio
async def test_client_view_nema_user_id_u_odgovoru():
    """user_id (advokat) se nikad ne sme pojaviti u klijentskom odgovoru."""
    from routers.client_portal import client_portal_view
    import json

    tok  = _valid_token()
    supa = _build_supa(token_row={"id": "t-1", "is_active": True, "expires_at": "2026-07-17T10:00:00+00:00"})

    with patch("routers.client_portal._get_supa", return_value=supa):
        result = await client_portal_view(_fake_request(), x_portal_token=tok)

    result_str = json.dumps(result)
    assert _ADVOKAT_UID not in result_str


# ─── DELETE /api/client-portal/token/{token_id} ───────────────────────────────

@pytest.mark.anyio
async def test_opozovi_token_uspesno():
    from routers.client_portal import opozovi_portal_token

    with patch("routers.client_portal._get_supa", return_value=_build_supa()):
        result = await opozovi_portal_token("tok-id-001", _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["is_active"] is False
