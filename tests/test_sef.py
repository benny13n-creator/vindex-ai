# -*- coding: utf-8 -*-
"""Tests for SEF e-faktura: UBL XML generator + API endpoints"""
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
        "path": "/api/sef/posalji/f-001",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


_FAKTURA = {
    "id":             "f-001",
    "user_id":        "uid-001",
    "broj_fakture":   "2026-001",
    "datum_fakture":  "2026-06-17",
    "klijent_naziv":  "Test DOO",
    "klijent_adresa": "Terazije 1, Beograd",
    "klijent_pib":    "222222222",
    "iznos_bez_pdv":  10000.0,
    "pdv_iznos":      0.0,
    "iznos_sa_pdv":   10000.0,
    "status":         "izdata",
    "napomena":       None,
}

_ENTRIES = [
    {"id": "e-001", "opis": "Zastupanje na ročištu", "iznos_rsd": 8000.0, "datum": "2026-06-10"},
    {"id": "e-002", "opis": "Pisana konsultacija",   "iznos_rsd": 2000.0, "datum": "2026-06-12"},
]

_SEF_POD = {
    "user_id":       "uid-001",
    "api_key":       "test-api-key-12345",
    "seller_pib":    "111111111",
    "seller_naziv":  "Advokat Petrović",
    "seller_adresa": "Knez Mihailova 10, Beograd",
    "seller_mesto":  "Beograd",
}


def _build_supa(faktura=_FAKTURA, entries=_ENTRIES, pod=_SEF_POD, log_ok=True):
    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "fakture":
            ms = MagicMock()
            ms.execute.return_value.data = faktura
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = ms
        elif name == "billing_entries":
            sel = MagicMock()
            sel.execute.return_value.data = entries
            t.select.return_value.eq.return_value.eq.return_value.order.return_value = sel
        elif name == "sef_podesavanja":
            ms2 = MagicMock()
            ms2.execute.return_value.data = pod
            t.select.return_value.eq.return_value.maybe_single.return_value = ms2
            # upsert
            upsert_m = MagicMock()
            upsert_m.execute.return_value.data = [pod] if pod else []
            t.upsert.return_value = upsert_m
        elif name == "sef_log":
            ins = MagicMock()
            ins.execute.return_value.data = [{}]
            t.insert.return_value = ins
            # dedup check: .select().eq().eq().in_().limit().execute()
            eq2 = t.select.return_value.eq.return_value.eq.return_value
            dedup_sel = MagicMock()
            dedup_sel.execute.return_value.data = []
            eq2.in_.return_value.limit.return_value = dedup_sel
            # log fetch: .select().eq().eq().order().limit().execute()
            sel2 = MagicMock()
            sel2.execute.return_value.data = []
            eq2.order.return_value.limit.return_value = sel2
        return t

    mock.table.side_effect = _table
    return mock


# ─── UBL XML Generator Tests ──────────────────────────────────────────────────

def test_ubl_xml_structure():
    """UBL XML mora imati sve obavezne elemente."""
    from sef_ubl import generiši_ubl_xml
    xml_bytes = generiši_ubl_xml(
        faktura=_FAKTURA, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat Petrović",
        seller_adresa="Knez Mihailova 10", seller_mesto="Beograd",
    )
    xml_str = xml_bytes.decode("utf-8")
    assert "<?xml version=" in xml_str
    assert "UBLVersionID>2.1" in xml_str
    assert "efaktura.mfin.gov.rs" in xml_str
    assert "2026-001" in xml_str
    assert "380" in xml_str  # InvoiceTypeCode
    assert "RSD" in xml_str
    assert "111111111" in xml_str   # seller PIB
    assert "222222222" in xml_str   # buyer PIB
    assert "Test DOO" in xml_str
    assert "Advokat Petrović" in xml_str


def test_ubl_xml_invoice_lines():
    """Svaka billing entry mora biti u XML-u kao InvoiceLine."""
    from sef_ubl import generiši_ubl_xml
    xml_str = generiši_ubl_xml(
        faktura=_FAKTURA, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat",
    ).decode("utf-8")
    assert "InvoiceLine" in xml_str
    assert "Zastupanje na ročištu" in xml_str
    assert "Pisana konsultacija" in xml_str
    assert "8000.00" in xml_str
    assert "2000.00" in xml_str


def test_ubl_xml_pdv_zero_kategorija_E():
    """PDV=0 → kategorija E (oslobođeno)."""
    from sef_ubl import generiši_ubl_xml
    xml_str = generiši_ubl_xml(
        faktura=_FAKTURA, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat",
    ).decode("utf-8")
    assert "<cbc:ID>E</cbc:ID>" in xml_str


def test_ubl_xml_pdv_20_kategorija_S():
    """PDV=20% → kategorija S (standardna)."""
    from sef_ubl import generiši_ubl_xml
    faktura_pdv = {**_FAKTURA, "iznos_bez_pdv": 10000.0, "pdv_iznos": 2000.0, "iznos_sa_pdv": 12000.0}
    xml_str = generiši_ubl_xml(
        faktura=faktura_pdv, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat",
    ).decode("utf-8")
    assert "<cbc:ID>S</cbc:ID>" in xml_str
    assert "20.00" in xml_str


def test_ubl_xml_rok_placanja():
    """Due date mora biti 30 dana od datuma fakture (default)."""
    from sef_ubl import generiši_ubl_xml
    xml_str = generiši_ubl_xml(
        faktura=_FAKTURA, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat",
    ).decode("utf-8")
    assert "<cbc:DueDate>2026-07-17</cbc:DueDate>" in xml_str


def test_ubl_xml_xss_escape():
    """Korisnički podaci moraju biti XSS-escaped u XML-u."""
    from sef_ubl import generiši_ubl_xml
    faktura_xss = {**_FAKTURA, "klijent_naziv": '<Script>alert("xss")</Script>'}
    xml_str = generiši_ubl_xml(
        faktura=faktura_xss, entries=[],
        seller_pib="111111111", seller_naziv="Advokat",
    ).decode("utf-8")
    assert "<Script>" not in xml_str
    assert "&lt;Script&gt;" in xml_str


def test_ubl_xml_bez_buyer_pib():
    """Faktura bez PIB kupca → nema PartyIdentification za kupca (ne puca)."""
    from sef_ubl import generiši_ubl_xml
    faktura_bez_pib = {**_FAKTURA, "klijent_pib": None}
    xml_bytes = generiši_ubl_xml(
        faktura=faktura_bez_pib, entries=_ENTRIES,
        seller_pib="111111111", seller_naziv="Advokat",
    )
    assert len(xml_bytes) > 500


# ─── SEF API Endpoint Tests ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_podesavanja_konfigurisano():
    """GET /sef/podesavanja → vraća maskiran API key kad je konfigurisan."""
    from routers.sef import get_sef_podesavanja

    with patch("routers.sef._get_supa", return_value=_build_supa()):
        result = await get_sef_podesavanja(_fake_request(), _fake_user())

    assert result["konfigurisano"] is True
    assert result["podaci"]["seller_pib"] == "111111111"
    assert "***" in result["podaci"]["api_key_preview"]
    assert "test-api-key-12345" not in result["podaci"]["api_key_preview"]


@pytest.mark.anyio
async def test_get_podesavanja_nije_konfigurisano():
    """GET /sef/podesavanja → konfigurisano=False kad nema zapisa."""
    from routers.sef import get_sef_podesavanja
    supa = _build_supa(pod=None)
    # Override maybe_single for sef_podesavanja to return None
    def _table(name):
        t = MagicMock()
        if name == "sef_podesavanja":
            ms = MagicMock()
            ms.execute.return_value.data = None
            t.select.return_value.eq.return_value.maybe_single.return_value = ms
        return t
    supa.table.side_effect = _table

    with patch("routers.sef._get_supa", return_value=supa):
        result = await get_sef_podesavanja(_fake_request(), _fake_user())

    assert result["konfigurisano"] is False


@pytest.mark.anyio
async def test_post_podesavanja_uspesno():
    """POST /sef/podesavanja → čuva SEF podešavanja."""
    from routers.sef import SefPodesavanjaReq, post_sef_podesavanja

    body = SefPodesavanjaReq(
        api_key="validApiKey12345678",
        seller_pib="111111111",
        seller_naziv="Advokat Marković",
        seller_adresa="Terazije 5, Beograd",
    )

    with patch("routers.sef._get_supa", return_value=_build_supa()):
        result = await post_sef_podesavanja(body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["seller_pib"] == "111111111"


def test_sef_podesavanja_req_invalid_pib():
    """SefPodesavanjaReq odbija PIB koji nije 9 cifara."""
    from pydantic import ValidationError
    from routers.sef import SefPodesavanjaReq

    with pytest.raises(ValidationError):
        SefPodesavanjaReq(api_key="key12345678", seller_pib="12345", seller_naziv="Advokat")


@pytest.mark.anyio
async def test_posalji_faktura_not_found():
    """POST /sef/posalji → 404 kad faktura ne postoji."""
    from fastapi import HTTPException
    from routers.sef import sef_posalji

    supa = _build_supa(faktura=None)

    def _table(name):
        t = MagicMock()
        if name == "fakture":
            ms = MagicMock()
            ms.execute.return_value.data = None
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = ms
        elif name == "billing_entries":
            sel = MagicMock()
            sel.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.order.return_value = sel
        elif name == "sef_podesavanja":
            ms2 = MagicMock()
            ms2.execute.return_value.data = _SEF_POD
            t.select.return_value.eq.return_value.maybe_single.return_value = ms2
        return t
    supa.table.side_effect = _table

    with patch("routers.sef._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await sef_posalji("nonexistent", _fake_request(), _fake_user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_posalji_nacrt_faktura_blokirana():
    """POST /sef/posalji → 400 kad je faktura u statusu 'nacrt'."""
    from fastapi import HTTPException
    from routers.sef import sef_posalji

    faktura_nacrt = {**_FAKTURA, "status": "nacrt"}
    with patch("routers.sef._get_supa", return_value=_build_supa(faktura=faktura_nacrt)):
        with pytest.raises(HTTPException) as exc:
            await sef_posalji("f-001", _fake_request(), _fake_user())

    assert exc.value.status_code == 400
    assert "nacrt" in exc.value.detail.lower()


@pytest.mark.anyio
async def test_posalji_bez_pib_kupca_blokirana():
    """POST /sef/posalji → 400 kad klijent nema PIB."""
    from fastapi import HTTPException
    from routers.sef import sef_posalji

    faktura_bez_pib = {**_FAKTURA, "klijent_pib": None}
    with patch("routers.sef._get_supa", return_value=_build_supa(faktura=faktura_bez_pib)):
        with pytest.raises(HTTPException) as exc:
            await sef_posalji("f-001", _fake_request(), _fake_user())

    assert exc.value.status_code == 400
    assert "PIB" in exc.value.detail


@pytest.mark.anyio
async def test_posalji_sef_uspesno():
    """POST /sef/posalji → uspešno slanje kad SEF vrati InvoiceId."""
    from routers.sef import sef_posalji

    sef_response = {"ok": True, "data": {"InvoiceId": 99999, "Status": "Sent"}}

    with patch("routers.sef._get_supa", return_value=_build_supa()), \
         patch("routers.sef._sef_post", return_value=sef_response):
        result = await sef_posalji("f-001", _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["sef_id"] == 99999
    assert result["sef_status"] == "Sent"


@pytest.mark.anyio
async def test_posalji_sef_greška_502():
    """POST /sef/posalji → 502 kad SEF API vrati grešku."""
    from fastapi import HTTPException
    from routers.sef import sef_posalji

    sef_fail = {"ok": False, "error": {"ModelErrors": {"Invoice": ["Invalid PIB format"]}}}

    with patch("routers.sef._get_supa", return_value=_build_supa()), \
         patch("routers.sef._sef_post", return_value=sef_fail):
        with pytest.raises(HTTPException) as exc:
            await sef_posalji("f-001", _fake_request(), _fake_user())

    assert exc.value.status_code == 502
    assert "Invalid PIB" in exc.value.detail


@pytest.mark.anyio
async def test_get_sef_log():
    """GET /sef/log/{id} → vraća listu slanja."""
    from routers.sef import get_sef_log
    with patch("routers.sef._get_supa", return_value=_build_supa()):
        result = await get_sef_log("f-001", _fake_request(), _fake_user())
    assert "log" in result
    assert isinstance(result["log"], list)
