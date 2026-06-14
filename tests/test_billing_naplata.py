# -*- coding: utf-8 -*-
"""
Tests for routers/billing.py — Naplata extensions (Vindex OS PRIORITET 4):
  GET /billing/dugovanja
  GET /billing/naplata-status
  GET /billing/po-klijentu/{klijent_id}
All tests run without live Supabase (mocked with table-name routing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/billing/dugovanja"):
    scope = {"type":"http","method":"GET","headers":[],"query_string":b"","path":path,
             "app":MagicMock(),"state":MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


PID  = "cccc0000-0000-0000-0000-000000000003"
PID2 = "dddd0000-0000-0000-0000-000000000004"
KID  = "kkkk0000-0000-0000-0000-000000000005"


def _make_chain(data):
    chain = MagicMock()
    for attr in ['select','eq','neq','gte','lte','order','limit','execute',
                 'in_','insert','update','delete','is_','desc']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _supa_by_table(**table_data):
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda name: _make_chain(table_data.get(name, [])))
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. /billing/dugovanja
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dugovanja_empty():
    from routers.billing import billing_dugovanja
    supa = _supa_by_table(billing_entries=[], predmeti=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_dugovanja(request=_req(), user=_user())
    assert result["dugovanja"] == []
    assert result["ukupno_rsd"] == 0.0
    assert result["predmeta"] == 0
    assert result["stavki"] == 0


@pytest.mark.anyio
async def test_dugovanja_groups_by_predmet():
    from routers.billing import billing_dugovanja
    entries = [
        {"id": "e1", "predmet_id": PID,  "opis": "Konsultacija", "iznos_rsd": 3000, "datum": "2026-06-01", "tip": "stavka", "tarifa_naziv": "T17"},
        {"id": "e2", "predmet_id": PID,  "opis": "Tužba",        "iznos_rsd": 6000, "datum": "2026-06-02", "tip": "stavka", "tarifa_naziv": "T01"},
        {"id": "e3", "predmet_id": PID2, "opis": "Žalba",        "iznos_rsd": 2000, "datum": "2026-06-01", "tip": "stavka", "tarifa_naziv": "T04"},
    ]
    predmeti = [
        {"id": PID,  "naziv": "Predmet A"},
        {"id": PID2, "naziv": "Predmet B"},
    ]
    supa = _supa_by_table(billing_entries=entries, predmeti=predmeti)
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_dugovanja(request=_req(), user=_user())
    assert result["predmeta"] == 2
    assert result["stavki"] == 3
    # Sorted by iznos desc: PID first (9000), PID2 second (2000)
    assert result["dugovanja"][0]["predmet_id"] == PID
    assert result["dugovanja"][0]["ukupno_rsd"] == 9000.0
    assert result["dugovanja"][1]["ukupno_rsd"] == 2000.0
    assert result["ukupno_rsd"] == 11000.0


@pytest.mark.anyio
async def test_dugovanja_naziv_resolved():
    from routers.billing import billing_dugovanja
    entries  = [{"id": "e1", "predmet_id": PID, "opis": "X", "iznos_rsd": 1000, "datum": "2026-01-01", "tip": "stavka", "tarifa_naziv": None}]
    predmeti = [{"id": PID, "naziv": "Moj predmet"}]
    supa = _supa_by_table(billing_entries=entries, predmeti=predmeti)
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_dugovanja(request=_req(), user=_user())
    assert result["dugovanja"][0]["predmet_naziv"] == "Moj predmet"


@pytest.mark.anyio
async def test_dugovanja_required_keys():
    from routers.billing import billing_dugovanja
    supa = _supa_by_table(billing_entries=[], predmeti=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_dugovanja(request=_req(), user=_user())
    assert {"dugovanja","ukupno_rsd","predmeta","stavki"}.issubset(result.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# 2. /billing/naplata-status
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_naplata_status_empty():
    from routers.billing import billing_naplata_status
    supa = _supa_by_table(billing_entries=[], fakture=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_naplata_status(request=_req("/billing/naplata-status"), user=_user())
    for k in ("ukupno_stavke","neobracunato","fakturisano","naplaceno","neizmireno","nacrt_iznos"):
        assert result[k] == 0.0
    assert result["fakture_ukupno"] == 0


@pytest.mark.anyio
async def test_naplata_status_calculates_correctly():
    from routers.billing import billing_naplata_status
    entries = [
        {"iznos_rsd": 5000, "obracunato": False},
        {"iznos_rsd": 3000, "obracunato": True},
    ]
    fakture = [
        {"iznos_sa_pdv": 6000, "iznos_bez_pdv": 5000, "status": "placena", "datum_fakture": "2026-06-01", "broj_fakture": "001"},
        {"iznos_sa_pdv": 4000, "iznos_bez_pdv": 3300, "status": "izdata",  "datum_fakture": "2026-06-05", "broj_fakture": "002"},
        {"iznos_sa_pdv": 2000, "iznos_bez_pdv": 1600, "status": "nacrt",   "datum_fakture": "2026-06-10", "broj_fakture": "003"},
    ]
    supa = _supa_by_table(billing_entries=entries, fakture=fakture)
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_naplata_status(request=_req("/billing/naplata-status"), user=_user())
    assert result["ukupno_stavke"]   == 8000.0
    assert result["neobracunato"]    == 5000.0
    assert result["fakturisano"]     == 12000.0
    assert result["naplaceno"]       == 6000.0
    assert result["neizmireno"]      == 4000.0
    assert result["nacrt_iznos"]     == 2000.0
    assert result["fakture_ukupno"]  == 3
    assert result["fakture_placene"] == 1
    assert result["fakture_izdate"]  == 1


@pytest.mark.anyio
async def test_naplata_status_required_keys():
    from routers.billing import billing_naplata_status
    supa = _supa_by_table(billing_entries=[], fakture=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_naplata_status(request=_req("/billing/naplata-status"), user=_user())
    required = {"ukupno_stavke","neobracunato","fakturisano","naplaceno",
                "neizmireno","nacrt_iznos","fakture_ukupno","fakture_placene","fakture_izdate"}
    assert required.issubset(result.keys())


@pytest.mark.anyio
async def test_naplata_status_handles_none_iznos():
    from routers.billing import billing_naplata_status
    entries = [{"iznos_rsd": None, "obracunato": False}]
    fakture = [{"iznos_sa_pdv": None, "status": "placena", "datum_fakture": "2026-01-01", "broj_fakture": "001"}]
    supa    = _supa_by_table(billing_entries=entries, fakture=fakture)
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_naplata_status(request=_req("/billing/naplata-status"), user=_user())
    assert result["ukupno_stavke"] == 0.0
    assert result["naplaceno"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. /billing/po-klijentu/{klijent_id}
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_po_klijentu_no_predmeti_returns_empty():
    from routers.billing import billing_po_klijentu
    supa = _supa_by_table(predmet_klijenti=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_po_klijentu(klijent_id=KID, request=_req(), user=_user())
    assert result["klijent_id"] == KID
    assert result["predmeti"]   == []
    assert result["stavke"]     == []
    assert result["fakture"]    == []
    assert result["ukupno_rsd"] == 0.0
    assert result["naplaceno"]  == 0.0
    assert result["neizmireno"] == 0.0


@pytest.mark.anyio
async def test_po_klijentu_aggregates_correctly():
    from routers.billing import billing_po_klijentu
    pk       = [{"predmet_id": PID}, {"predmet_id": PID2}]
    entries  = [
        {"id": "e1", "predmet_id": PID,  "iznos_rsd": 5000, "obracunato": False},
        {"id": "e2", "predmet_id": PID2, "iznos_rsd": 3000, "obracunato": True},
    ]
    fakture  = [
        {"id": "f1", "predmet_id": PID, "iznos_sa_pdv": 7000, "status": "placena"},
        {"id": "f2", "predmet_id": PID, "iznos_sa_pdv": 2000, "status": "izdata"},
    ]
    predmeti = [
        {"id": PID,  "naziv": "A", "status": "aktivan"},
        {"id": PID2, "naziv": "B", "status": "aktivan"},
    ]
    supa = _supa_by_table(predmet_klijenti=pk, billing_entries=entries,
                          fakture=fakture, predmeti=predmeti)
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_po_klijentu(klijent_id=KID, request=_req(), user=_user())
    assert result["klijent_id"] == KID
    assert len(result["predmeti"]) == 2
    assert len(result["stavke"])   == 2
    assert len(result["fakture"])  == 2
    assert result["ukupno_rsd"]    == 8000.0
    assert result["naplaceno"]     == 7000.0
    assert result["neizmireno"]    == 2000.0


@pytest.mark.anyio
async def test_po_klijentu_required_keys():
    from routers.billing import billing_po_klijentu
    supa = _supa_by_table(predmet_klijenti=[])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_po_klijentu(klijent_id=KID, request=_req(), user=_user())
    assert {"klijent_id","predmeti","stavke","fakture","ukupno_rsd","naplaceno","neizmireno"}.issubset(result.keys())


@pytest.mark.anyio
async def test_po_klijentu_single_predmet():
    from routers.billing import billing_po_klijentu
    pk      = [{"predmet_id": PID}]
    entries = [{"id": "e1", "predmet_id": PID, "iznos_rsd": 1000, "obracunato": False}]
    supa    = _supa_by_table(predmet_klijenti=pk, billing_entries=entries,
                              fakture=[], predmeti=[{"id": PID, "naziv": "X", "status": "aktivan"}])
    with patch("routers.billing._get_supa", return_value=supa):
        result = await billing_po_klijentu(klijent_id=KID, request=_req(), user=_user())
    assert result["ukupno_rsd"] == 1000.0
    assert result["naplaceno"]  == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Router paths present
# ═══════════════════════════════════════════════════════════════════════════════

def test_billing_router_dugovanja():
    from routers.billing import router
    paths = [r.path for r in router.routes]
    assert "/billing/dugovanja" in paths


def test_billing_router_naplata_status():
    from routers.billing import router
    paths = [r.path for r in router.routes]
    assert "/billing/naplata-status" in paths


def test_billing_router_po_klijentu():
    from routers.billing import router
    paths = [r.path for r in router.routes]
    assert "/billing/po-klijentu/{klijent_id}" in paths
