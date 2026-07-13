# -*- coding: utf-8 -*-
"""Tests for GET /api/rokovi/tipovi-dogadjaja and POST /api/rokovi/lanac"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
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
        "path": "/api/rokovi/lanac",
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


# ─── T1: GET tipovi — vraća sve tipove ───────────────────────────────────────

@pytest.mark.anyio
async def test_get_tipovi_dogadjaja():
    from routers.rokovi_lanac import get_tipovi_dogadjaja
    result = await get_tipovi_dogadjaja()
    tipovi = result["tipovi"]
    assert len(tipovi) >= 6
    kljucevi = {t["kljuc"] for t in tipovi}
    assert "dostava_presude_prvostepene" in kljucevi
    assert "dostava_presude_drugostepene" in kljucevi
    assert "dostava_tuzbe" in kljucevi
    assert "dostava_resenja" in kljucevi


# ─── T2: POST lanac bez predmet_id — samo generiše, ne čuva ──────────────────

@pytest.mark.anyio
async def test_lanac_bez_predmeta():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_presude_prvostepene", datum_pocetka="2026-06-01")

    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is False
    assert result["predmet_id"] is None
    assert len(result["lanac"]) == 3  # zalba, odgovor_na_zalbu, pravosnaznost

    # Rok za žalbu = +15 dana
    zalba = next(r for r in result["lanac"] if r["tip_roka"] == "zalba")
    assert zalba["dana"] == 15
    assert zalba["vaznost"] == "kritican"
    assert zalba["datum_iso"] == "2026-06-16"
    assert zalba["zakonski_osnov"] == "ZPP čl. 374 st. 1"


# ─── T3: POST lanac sa predmet_id — čuva u hronologiju ──────────────────────

@pytest.mark.anyio
async def test_lanac_sa_predmetom():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    pred = {"id": "pred-abc", "naziv": "Test predmet"}
    body = LanacReq(
        tip_dogadjaja="dostava_presude_prvostepene",
        datum_pocetka="2026-06-01",
        predmet_id="pred-abc",
    )

    with patch("routers.rokovi_lanac._get_supa", return_value=_build_supa(pred)):
        result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is True
    assert result["predmet_id"] == "pred-abc"


# ─── T4: POST lanac sa predmet_id koji ne postoji → 404 ─────────────────────

@pytest.mark.anyio
async def test_lanac_predmet_not_found():
    from fastapi import HTTPException
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(
        tip_dogadjaja="dostava_tuzbe",
        datum_pocetka="2026-06-01",
        predmet_id="nonexistent",
    )

    with patch("routers.rokovi_lanac._get_supa", return_value=_build_supa(None)):
        with pytest.raises(HTTPException) as exc:
            await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert exc.value.status_code == 404


# ─── T5: Validacija — nepoznat tip_dogadjaja ─────────────────────────────────

def test_lanac_req_invalid_tip():
    from pydantic import ValidationError
    from routers.rokovi_lanac import LanacReq

    with pytest.raises(ValidationError):
        LanacReq(tip_dogadjaja="nepostojeci_tip", datum_pocetka="2026-06-01")


# ─── T6: Validacija — neispravan datum ───────────────────────────────────────

def test_lanac_req_invalid_datum():
    from pydantic import ValidationError
    from routers.rokovi_lanac import LanacReq

    with pytest.raises(ValidationError):
        LanacReq(tip_dogadjaja="dostava_tuzbe", datum_pocetka="nije-datum")


# ─── T7: Datum u formatu DD.MM.YYYY ──────────────────────────────────────────

@pytest.mark.anyio
async def test_lanac_datum_srb_format():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_tuzbe", datum_pocetka="01.06.2026")
    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert result["datum_pocetka_iso"] == "2026-06-01"
    odgovor = next(r for r in result["lanac"] if r["tip_roka"] == "odgovor_na_tuzbu")
    assert odgovor["datum_iso"] == "2026-06-16"  # +15 dana


# ─── T8: Tip dostava_presude_drugostepene ────────────────────────────────────

@pytest.mark.anyio
async def test_lanac_drugostepena():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_presude_drugostepene", datum_pocetka="2026-06-01")
    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert len(result["lanac"]) == 2
    revizija = next(r for r in result["lanac"] if r["tip_roka"] == "revizija")
    assert revizija["dana"] == 30
    assert revizija["datum_iso"] == "2026-07-01"
    assert revizija["vaznost"] == "kritican"


# ─── T9: Tip dostava_zalbe — jedan rok ───────────────────────────────────────

@pytest.mark.anyio
async def test_lanac_dostava_zalbe():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_zalbe", datum_pocetka="2026-06-01")
    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert len(result["lanac"]) == 1
    r = result["lanac"][0]
    assert r["tip_roka"] == "odgovor_na_zalbu"
    assert r["dana"] == 8
    assert r["datum_iso"] == "2026-06-09"


# ─── T10: DB greška pri upisivanju — sacuvano=False, ne puca ─────────────────

@pytest.mark.anyio
async def test_lanac_db_insert_greska_non_fatal():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    pred = {"id": "pred-xyz", "naziv": "Predmet"}
    body = LanacReq(
        tip_dogadjaja="dostava_resenja",
        datum_pocetka="2026-06-01",
        predmet_id="pred-xyz",
    )

    with patch("routers.rokovi_lanac._get_supa", return_value=_build_supa(pred, insert_ok=False)):
        result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sacuvano_u_predmet"] is False
    assert len(result["lanac"]) == 1


# ─── T11: Sve vaznosti su ispravno mapirane ──────────────────────────────────

@pytest.mark.anyio
async def test_lanac_vaznosti():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_presude_prvostepene", datum_pocetka="2026-06-01")
    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    vaznosti = {r["tip_roka"]: r["vaznost"] for r in result["lanac"]}
    assert vaznosti["zalba"] == "kritican"
    assert vaznosti["odgovor_na_zalbu"] == "vazno"
    assert vaznosti["pravosnaznost"] == "info"


# ─── T12: datum_display je u srpskom formatu ─────────────────────────────────

@pytest.mark.anyio
async def test_lanac_datum_display_format():
    from routers.rokovi_lanac import LanacReq, post_rokovi_lanac

    body = LanacReq(tip_dogadjaja="dostava_zalbe", datum_pocetka="2026-06-01")
    result = await post_rokovi_lanac(body, _fake_request(), _fake_user())

    r = result["lanac"][0]
    assert r["datum_display"] == "09.06.2026"
    assert result["datum_pocetka_display"] == "01.06.2026"
