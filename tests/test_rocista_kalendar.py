# -*- coding: utf-8 -*-
"""
Faza 1: Tests for /api/rocista (CRUD) and /api/kalendar (pregled + ics)
All tests run without live services (Supabase mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/rocista", method="POST"):
    scope = {
        "type": "http", "method": method, "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaaaaaa-0000-0000-0000-000000000001", "email": "test@vindex.rs", "role": "advokat"}


def _supa_ok(data):
    """Mock Supabase client that returns data on any chained call."""
    supa = MagicMock()
    result = MagicMock()
    result.data = data
    # Build a chainable mock: .table().select().eq().eq().execute()
    chain = MagicMock()
    chain.execute.return_value = result
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.in_.return_value = chain
    supa.table.return_value.select.return_value = chain
    supa.table.return_value.insert.return_value = chain
    supa.table.return_value.update.return_value = chain
    supa.table.return_value.delete.return_value = chain
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Model validation (pure Python, no mocking)
# ═══════════════════════════════════════════════════════════════════════════════

def test_rociste_req_valid():
    from routers.rocista import RocisteReq
    r = RocisteReq(predmet_id="pid-123", sud="Viši sud u Beogradu", datum="2026-09-15")
    assert r.datum == "2026-09-15"
    assert r.vreme is None


def test_rociste_req_with_vreme():
    from routers.rocista import RocisteReq
    r = RocisteReq(predmet_id="pid-1", sud="Okružni", datum="2026-07-01", vreme="10:30")
    assert r.vreme == "10:30"


def test_rociste_req_invalid_datum():
    from routers.rocista import RocisteReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        RocisteReq(predmet_id="pid-1", sud="Sud", datum="not-a-date")
    assert "datum mora biti" in str(exc_info.value)


def test_rociste_req_datum_wrong_format():
    from routers.rocista import RocisteReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RocisteReq(predmet_id="pid-1", sud="Sud", datum="15.09.2026")


def test_rociste_req_invalid_vreme():
    from routers.rocista import RocisteReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        RocisteReq(predmet_id="pid-1", sud="Sud", datum="2026-09-15", vreme="10h30")
    assert "vreme mora biti" in str(exc_info.value)


def test_rociste_req_empty_vreme_becomes_none():
    from routers.rocista import RocisteReq
    r = RocisteReq(predmet_id="pid-1", sud="Sud", datum="2026-09-15", vreme="")
    assert r.vreme is None


def test_rociste_req_max_length_sud():
    from routers.rocista import RocisteReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RocisteReq(predmet_id="pid-1", sud="S" * 301, datum="2026-09-15")


def test_rociste_patch_valid_status():
    from routers.rocista import RocistePatchReq
    r = RocistePatchReq(status="odrzano")
    assert r.status == "odrzano"


def test_rociste_patch_all_valid_statuses():
    from routers.rocista import RocistePatchReq
    for st in ["zakazano", "odrzano", "odlozeno", "otkazano"]:
        r = RocistePatchReq(status=st)
        assert r.status == st


def test_rociste_patch_invalid_status():
    from routers.rocista import RocistePatchReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RocistePatchReq(status="nepoznato")


def test_rociste_patch_none_fields_allowed():
    from routers.rocista import RocistePatchReq
    r = RocistePatchReq()
    assert r.sud is None
    assert r.datum is None
    assert r.status is None


def test_rociste_patch_valid_datum():
    from routers.rocista import RocistePatchReq
    r = RocistePatchReq(datum="2026-12-31")
    assert r.datum == "2026-12-31"


def test_rociste_patch_invalid_datum():
    from routers.rocista import RocistePatchReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RocistePatchReq(datum="31.12.2026")


def test_rociste_patch_vreme_empty_string():
    from routers.rocista import RocistePatchReq
    r = RocistePatchReq(vreme="")
    assert r.vreme is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: Helper utilities (pure Python)
# ═══════════════════════════════════════════════════════════════════════════════

def test_norm_vreme_full():
    from routers.rocista import _norm_vreme
    assert _norm_vreme("10:30:00") == "10:30"


def test_norm_vreme_short():
    from routers.rocista import _norm_vreme
    assert _norm_vreme("09:15") == "09:15"


def test_norm_vreme_none():
    from routers.rocista import _norm_vreme
    assert _norm_vreme(None) is None


def test_norm_vreme_empty():
    from routers.rocista import _norm_vreme
    assert _norm_vreme("") is None


def test_klasifikuj_zastarelost():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Datum zastarelosti potraživanja") == "rok_zastarelost"


def test_klasifikuj_zastarelost_lowercase():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("zastarelost kredita") == "rok_zastarelost"


def test_klasifikuj_dogadjaj_other():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Rok za podnošenje tužbe") == "rok_dokument"


def test_klasifikuj_dogadjaj_empty():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("") == "rok_dokument"


def test_klasifikuj_dogadjaj_case_insensitive():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("ZASTARELOST POTRAŽIVANJA") == "rok_zastarelost"


def test_norm_vreme_kalendar():
    from routers.kalendar import _norm_vreme
    assert _norm_vreme("14:00:00") == "14:00"
    assert _norm_vreme(None) is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: CRUD endpoint tests (mocked Supabase)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kreiraj_rociste_success():
    from routers.rocista import RocisteReq, kreiraj_rociste

    pred_row = {"id": "predmet-1"}
    new_row = {
        "id": "rociste-uuid-1", "predmet_id": "predmet-1",
        "sud": "Viši sud u Beogradu", "datum": "2026-09-20",
        "vreme": "10:00:00", "status": "zakazano",
        "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
    }

    supa = MagicMock()
    # pred check returns row, insert returns new row
    pred_chain = MagicMock()
    pred_result = MagicMock(); pred_result.data = [pred_row]
    pred_chain.execute.return_value = pred_result
    pred_chain.eq.return_value = pred_chain
    pred_chain.select.return_value = pred_chain

    ins_chain = MagicMock()
    ins_result = MagicMock(); ins_result.data = [new_row]
    ins_chain.execute.return_value = ins_result
    ins_chain.insert.return_value = ins_chain

    def table_side(name):
        if name == "predmeti": return pred_chain
        if name == "rocista": return ins_chain
        return MagicMock()

    supa.table.side_effect = table_side

    body = RocisteReq(predmet_id="predmet-1", sud="Viši sud u Beogradu", datum="2026-09-20", vreme="10:00")

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await kreiraj_rociste(body, _req(), _user())

    assert result["ok"] is True
    assert result["rociste"]["sud"] == "Viši sud u Beogradu"


@pytest.mark.anyio
async def test_kreiraj_rociste_predmet_not_found():
    from routers.rocista import RocisteReq, kreiraj_rociste
    from fastapi import HTTPException

    supa = MagicMock()
    chain = MagicMock()
    result = MagicMock(); result.data = []
    chain.execute.return_value = result
    chain.eq.return_value = chain
    chain.select.return_value = chain
    supa.table.return_value = chain

    body = RocisteReq(predmet_id="nonexistent-id", sud="Sud", datum="2026-09-20")

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kreiraj_rociste(body, _req(), _user())

    assert exc.value.status_code == 404
    assert "Predmet" in exc.value.detail


@pytest.mark.anyio
async def test_lista_rocista_all():
    from routers.rocista import lista_rocista

    rows = [
        {"id": "r1", "predmet_id": "p1", "sud": "Sud A", "datum": "2026-07-01", "vreme": "09:00:00", "status": "zakazano"},
        {"id": "r2", "predmet_id": "p2", "sud": "Sud B", "datum": "2026-08-15", "vreme": None, "status": "odrzano"},
    ]
    supa = _supa_ok(rows)

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await lista_rocista(_req(method="GET"), None, _user())

    assert result["ukupno"] == 2
    assert result["rocista"][0]["vreme"] == "09:00"
    assert result["rocista"][1]["vreme"] is None


@pytest.mark.anyio
async def test_lista_rocista_filtered_by_predmet():
    from routers.rocista import lista_rocista

    rows = [{"id": "r1", "predmet_id": "p1", "sud": "Sud A", "datum": "2026-07-01", "vreme": None, "status": "zakazano"}]
    supa = _supa_ok(rows)

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await lista_rocista(_req(method="GET"), "p1", _user())

    assert result["ukupno"] == 1
    assert result["rocista"][0]["predmet_id"] == "p1"


@pytest.mark.anyio
async def test_lista_rocista_empty():
    from routers.rocista import lista_rocista

    supa = _supa_ok([])

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await lista_rocista(_req(method="GET"), None, _user())

    assert result["ukupno"] == 0
    assert result["rocista"] == []


@pytest.mark.anyio
async def test_izmeni_rociste_success():
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "odrzano", "sud": "Sud C", "datum": "2026-07-01", "vreme": None}
    supa = _supa_ok([updated_row])

    body = RocistePatchReq(status="odrzano")

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    assert result["ok"] is True
    assert result["rociste"]["status"] == "odrzano"


@pytest.mark.anyio
async def test_izmeni_rociste_not_found():
    from routers.rocista import RocistePatchReq, izmeni_rociste
    from fastapi import HTTPException

    supa = _supa_ok([])
    body = RocistePatchReq(status="odrzano")

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await izmeni_rociste("nonexistent", body, _req(method="PATCH"), _user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_izmeni_rociste_no_fields():
    from routers.rocista import RocistePatchReq, izmeni_rociste
    from fastapi import HTTPException

    supa = _supa_ok([])
    body = RocistePatchReq()  # all None

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    assert exc.value.status_code == 422
    assert "Nema polja" in exc.value.detail


@pytest.mark.anyio
async def test_obrisi_rociste_success():
    from routers.rocista import obrisi_rociste

    supa = _supa_ok([{"id": "r1"}])

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await obrisi_rociste("r1", _req(method="DELETE"), _user())

    assert result["ok"] is True


@pytest.mark.anyio
async def test_obrisi_rociste_not_found():
    from routers.rocista import obrisi_rociste
    from fastapi import HTTPException

    supa = _supa_ok([])

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await obrisi_rociste("nonexistent", _req(method="DELETE"), _user())

    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: Calendar aggregation logic
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_aggr_events_rociste_classified():
    from routers.kalendar import _aggr_events

    rociste_row = {
        "id": "r1", "predmet_id": "p1",
        "sud": "Viši sud", "sudnica": "4",
        "datum": "2026-08-01", "vreme": "10:00:00",
        "status": "zakazano", "broj_predmeta_suda": None, "napomena": None,
    }
    pred_row = {"id": "p1", "naziv": "Spor ABC"}

    supa = MagicMock()
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.select.return_value = chain

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmet_hronologija":
            c.execute.return_value = MagicMock(data=[])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert len(events) == 1
    assert events[0]["tip"] == "rociste"
    assert events[0]["vreme"] == "10:00"
    assert events[0]["predmet_naziv"] == "Spor ABC"
    assert events[0]["detalji"]["sud"] == "Viši sud"


@pytest.mark.anyio
async def test_aggr_events_hronologija_zastarelost():
    from routers.kalendar import _aggr_events

    hron_row = {"predmet_id": "p1", "dogadjaj": "Zastarelost potraživanja", "datum_iso": "2026-09-01", "vaznost": "kritičan"}
    pred_row = {"id": "p1", "naziv": "Kredit spor"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[])
        elif name == "predmet_hronologija":
            c.execute.return_value = MagicMock(data=[hron_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert len(events) == 1
    assert events[0]["tip"] == "rok_zastarelost"
    assert events[0]["datum"] == "2026-09-01"
    assert events[0]["vreme"] is None


@pytest.mark.anyio
async def test_aggr_events_hronologija_rok_dokument():
    from routers.kalendar import _aggr_events

    hron_row = {"predmet_id": "p1", "dogadjaj": "Rok za dostavu dokumenata", "datum_iso": "2026-08-10", "vaznost": "važan"}
    pred_row = {"id": "p1", "naziv": "Ugovorni spor"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[])
        elif name == "predmet_hronologija":
            c.execute.return_value = MagicMock(data=[hron_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert events[0]["tip"] == "rok_dokument"


@pytest.mark.anyio
async def test_aggr_events_sorted_by_date():
    from routers.kalendar import _aggr_events

    rociste_row = {
        "id": "r1", "predmet_id": "p1", "sud": "Sud",
        "datum": "2026-09-15", "vreme": None,
        "status": "zakazano", "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
    }
    hron_row = {"predmet_id": "p1", "dogadjaj": "Rok dokumenta", "datum_iso": "2026-07-01", "vaznost": "važan"}
    pred_row = {"id": "p1", "naziv": "Spor X"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmet_hronologija":
            c.execute.return_value = MagicMock(data=[hron_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert len(events) == 2
    assert events[0]["datum"] < events[1]["datum"]
    assert events[0]["tip"] == "rok_dokument"
    assert events[1]["tip"] == "rociste"


@pytest.mark.anyio
async def test_aggr_events_empty():
    from routers.kalendar import _aggr_events

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: kalendar_pregled endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kalendar_pregled_default_range():
    from routers.kalendar import kalendar_pregled

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        result = await kalendar_pregled(_req(method="GET"), None, None, _user())

    assert "dogadjaji" in result
    assert "od" in result
    assert "do" in result
    today = date.today()
    assert result["od"] == today.isoformat()
    expected_do = (today + timedelta(days=30)).isoformat()
    assert result["do"] == expected_do


@pytest.mark.anyio
async def test_kalendar_pregled_custom_range():
    from routers.kalendar import kalendar_pregled

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        result = await kalendar_pregled(_req(method="GET"), "2026-01-01", "2026-03-31", _user())

    assert result["od"] == "2026-01-01"
    assert result["do"] == "2026-03-31"


@pytest.mark.anyio
async def test_kalendar_pregled_invalid_date():
    from routers.kalendar import kalendar_pregled
    from fastapi import HTTPException

    supa = _supa_ok([])

    with patch("routers.kalendar._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kalendar_pregled(_req(method="GET"), "not-a-date", None, _user())

    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_kalendar_pregled_range_too_large():
    from routers.kalendar import kalendar_pregled
    from fastapi import HTTPException

    supa = _supa_ok([])

    with patch("routers.kalendar._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kalendar_pregled(_req(method="GET"), "2026-01-01", "2028-01-01", _user())

    assert exc.value.status_code == 422
    assert "365" in exc.value.detail


@pytest.mark.anyio
async def test_kalendar_pregled_returns_ukupno():
    from routers.kalendar import kalendar_pregled

    rociste_row = {
        "id": "r1", "predmet_id": "p1", "sud": "Sud", "sudnica": None,
        "datum": "2026-07-20", "vreme": None,
        "status": "zakazano", "broj_predmeta_suda": None, "napomena": None,
    }
    pred_row = {"id": "p1", "naziv": "Spor Y"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        result = await kalendar_pregled(_req(method="GET"), "2026-07-01", "2026-12-31", _user())

    assert result["ukupno"] == 1
    assert result["dogadjaji"][0]["tip"] == "rociste"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: ICS export endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kalendar_ics_has_vevent():
    from routers.kalendar import kalendar_ics_export

    rociste_row = {
        "id": "r1", "predmet_id": "p1", "sud": "Viši sud", "sudnica": "3",
        "datum": "2026-08-10", "vreme": "11:00:00",
        "status": "zakazano", "broj_predmeta_suda": None, "napomena": None,
    }
    pred_row = {"id": "p1", "naziv": "Spor ICS"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        response = await kalendar_ics_export(_req(method="POST"), "2026-08-01", "2026-09-01", _user())

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "DTSTART" in body


@pytest.mark.anyio
async def test_kalendar_ics_empty_returns_404():
    from routers.kalendar import kalendar_ics_export
    from fastapi import HTTPException

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kalendar_ics_export(_req(method="POST"), "2026-08-01", "2026-09-01", _user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_kalendar_ics_invalid_date():
    from routers.kalendar import kalendar_ics_export
    from fastapi import HTTPException

    supa = _supa_ok([])

    with patch("routers.kalendar._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kalendar_ics_export(_req(method="POST"), "bad-date", None, _user())

    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_kalendar_ics_content_disposition():
    from routers.kalendar import kalendar_ics_export

    rociste_row = {
        "id": "r1", "predmet_id": "p1", "sud": "Sud",
        "datum": "2026-08-20", "vreme": None, "status": "zakazano",
        "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
    }
    pred_row = {"id": "p1", "naziv": "Test"}

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[pred_row])
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        response = await kalendar_ics_export(_req(method="POST"), "2026-08-01", "2026-09-01", _user())

    assert "attachment" in response.headers.get("content-disposition", "")
    assert ".ics" in response.headers.get("content-disposition", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: Edge cases and boundary conditions
# ═══════════════════════════════════════════════════════════════════════════════

def test_rociste_req_napomena_trimmed():
    from routers.rocista import RocisteReq
    r = RocisteReq(predmet_id="pid", sud="Sud", datum="2026-06-15", napomena="  beleška  ")
    assert r.napomena == "  beleška  "  # model doesn't trim, router does


def test_rociste_req_fields_present():
    from routers.rocista import RocisteReq
    r = RocisteReq(
        predmet_id="pid-xyz",
        sud="Prvostepeni sud",
        datum="2026-11-01",
        sudnica="Sudnica 2",
        broj_predmeta_suda="P-99/2026",
        napomena="Važan rok"
    )
    assert r.sudnica == "Sudnica 2"
    assert r.broj_predmeta_suda == "P-99/2026"
    assert r.napomena == "Važan rok"


@pytest.mark.anyio
async def test_aggr_events_predmet_name_fallback():
    from routers.kalendar import _aggr_events

    rociste_row = {
        "id": "r1", "predmet_id": "unknown-pid", "sud": "Sud",
        "datum": "2026-07-10", "vreme": None,
        "status": "zakazano", "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
    }

    supa = MagicMock()

    def table_side(name):
        c = MagicMock()
        c.eq.return_value = c; c.gte.return_value = c
        c.lte.return_value = c; c.order.return_value = c
        c.limit.return_value = c; c.select.return_value = c
        if name == "rocista":
            c.execute.return_value = MagicMock(data=[rociste_row])
        elif name == "predmet_hronologija":
            c.execute.return_value = MagicMock(data=[])
        elif name == "predmeti":
            c.execute.return_value = MagicMock(data=[])  # empty pred map
        else:
            c.execute.return_value = MagicMock(data=[])
        return c

    supa.table.side_effect = table_side

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("uid-1", "2026-07-01", "2026-12-31")

    assert len(events) == 1
    # Falls back to empty string when predmet not found in map
    assert events[0]["predmet_naziv"] == ""


@pytest.mark.anyio
async def test_kreiraj_rociste_insert_fail():
    from routers.rocista import RocisteReq, kreiraj_rociste
    from fastapi import HTTPException

    supa = MagicMock()
    pred_chain = MagicMock()
    pred_chain.execute.return_value = MagicMock(data=[{"id": "p1"}])
    pred_chain.eq.return_value = pred_chain
    pred_chain.select.return_value = pred_chain

    ins_chain = MagicMock()
    ins_chain.execute.return_value = MagicMock(data=[])  # empty = insert failed
    ins_chain.insert.return_value = ins_chain

    def table_side(name):
        if name == "predmeti": return pred_chain
        if name == "rocista": return ins_chain
        return MagicMock()

    supa.table.side_effect = table_side
    body = RocisteReq(predmet_id="p1", sud="Sud", datum="2026-09-01")

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await kreiraj_rociste(body, _req(), _user())

    assert exc.value.status_code == 500


def test_rociste_patch_sud_trimmed():
    from routers.rocista import RocistePatchReq
    r = RocistePatchReq(sud="Viši sud u Novom Sadu")
    assert r.sud == "Viši sud u Novom Sadu"


@pytest.mark.anyio
async def test_obrisi_rociste_user_isolation():
    """DELETE must include user_id eq — mock verifies chain is called."""
    from routers.rocista import obrisi_rociste

    supa = MagicMock()
    del_chain = MagicMock()
    del_chain.execute.return_value = MagicMock(data=[{"id": "r1"}])
    del_chain.eq.return_value = del_chain
    del_chain.delete.return_value = del_chain
    supa.table.return_value = del_chain

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await obrisi_rociste("r1", _req(method="DELETE"), _user())

    assert result["ok"] is True
    # Verify user_id was applied as a filter
    uid_calls = [str(c) for c in del_chain.eq.call_args_list]
    assert any("user_id" in s or "aaaaaaaa" in s for s in uid_calls)
