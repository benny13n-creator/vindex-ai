# -*- coding: utf-8 -*-
"""
Phase 9 — Billing izveštaji
Tests for routers/billing_reports.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
import api
from shared.deps import get_current_user

FAKE_USER = {"user_id": "uid-001", "email": "a@test.rs", "role": "pro"}

YEAR = date.today().year
TODAY = date.today().isoformat()
JAN15 = f"{YEAR}-01-15"
MAR10 = f"{YEAR}-03-10"
D90   = (date.today() - timedelta(days=90)).isoformat()
D45   = (date.today() - timedelta(days=45)).isoformat()
D15   = (date.today() - timedelta(days=15)).isoformat()

SAMPLE_ENTRIES = [
    {"id": "e1", "datum": JAN15, "iznos_rsd": 7500.0, "obracunato": True,  "predmet_id": "p1", "klijent_id": "kl1", "tarifa_sifra": "T17", "tarifa_naziv": "Konsultacija", "opis": "Savetovanje", "sati": 1.0, "faktura_id": "f1"},
    {"id": "e2", "datum": MAR10, "iznos_rsd": 12000.0,"obracunato": False, "predmet_id": "p2", "klijent_id": "kl2", "tarifa_sifra": "T01", "tarifa_naziv": "Tužba",       "opis": "Izrada tužbe","sati": 0.0, "faktura_id": None},
    {"id": "e3", "datum": JAN15, "iznos_rsd": 6000.0, "obracunato": False, "predmet_id": "p1", "klijent_id": "kl1", "tarifa_sifra": "T10", "tarifa_naziv": "Ročište",     "opis": "Zastupanje", "sati": 2.0, "faktura_id": None},
]
SAMPLE_FAKTURE = [
    {"id": "f1", "iznos_sa_pdv": 9000.0, "iznos_rsd": 7500.0, "status": "placena",   "datum_fakture": JAN15, "klijent_id": "kl1"},
    {"id": "f2", "iznos_sa_pdv": 14400.0,"iznos_rsd": 12000.0,"status": "izdata",    "datum_fakture": MAR10, "klijent_id": "kl2"},
]
SAMPLE_PREDMETI = [
    {"id": "p1", "naziv": "Tužba Petrović", "tip": "gradjansko"},
    {"id": "p2", "naziv": "Spor Nikolić",   "tip": "radno"},
]
SAMPLE_KLIJENTI = [
    {"id": "kl1", "ime": "Nikola", "prezime": "Petrović", "naziv_firme": None},
    {"id": "kl2", "ime": None,     "prezime": None,        "naziv_firme": "Nikolić d.o.o."},
]

# Aged entries
AGED_ENTRIES = [
    {"id": "a1", "datum": D90,  "iznos_rsd": 5000.0,  "opis": "Stara stavka",  "predmet_id": "p1", "klijent_id": "kl1"},
    {"id": "a2", "datum": D45,  "iznos_rsd": 8000.0,  "opis": "Srednja stavka","predmet_id": "p2", "klijent_id": "kl2"},
    {"id": "a3", "datum": D15,  "iznos_rsd": 3000.0,  "opis": "Nova stavka",   "predmet_id": "p1", "klijent_id": "kl1"},
]


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _make_supa(entries=None, fakture=None, predmeti=None, klijenti=None, aged=None):
    supa   = MagicMock()
    _cache: dict = {}

    def _table(name):
        if name in _cache:
            return _cache[name]
        tbl = MagicMock()
        sel = MagicMock()

        sel.eq.return_value  = sel
        sel.gte.return_value = sel
        sel.lte.return_value = sel
        sel.order.return_value = sel

        if name == "billing_entries":
            rows = aged if aged is not None else (entries or SAMPLE_ENTRIES)
            sel.execute.return_value = MagicMock(data=rows)
        elif name == "fakture":
            sel.execute.return_value = MagicMock(data=fakture or SAMPLE_FAKTURE)
        elif name == "predmeti":
            sel.execute.return_value = MagicMock(data=predmeti or SAMPLE_PREDMETI)
        elif name == "klijenti":
            sel.execute.return_value = MagicMock(data=klijenti or SAMPLE_KLIJENTI)
        else:
            sel.execute.return_value = MagicMock(data=[])

        tbl.select.return_value = sel
        _cache[name] = tbl
        return tbl

    supa.table.side_effect = _table
    return supa


@pytest.fixture
def client():
    supa = _make_supa()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing_reports._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/report/godisnji
# ═══════════════════════════════════════════════════════════════════════════════

def test_godisnji_200(client):
    r = client.get("/billing/report/godisnji")
    assert r.status_code == 200
    data = r.json()
    assert "godina" in data
    assert data["godina"] == YEAR


def test_godisnji_struktura(client):
    r = client.get("/billing/report/godisnji")
    data = r.json()
    for field in ("ukupno_uneseno_rsd", "ukupno_fakturisano", "ukupno_naplaceno_rsd",
                  "stopa_naplate_pct", "po_mesecima", "top_klijenti", "top_tipovi_predmeta"):
        assert field in data, f"Nedostaje: {field}"


def test_godisnji_meseci_12(client):
    r = client.get("/billing/report/godisnji")
    data = r.json()
    assert len(data["po_mesecima"]) == 12


def test_godisnji_meseci_format(client):
    r = client.get("/billing/report/godisnji")
    for m in r.json()["po_mesecima"]:
        assert "mesec"    in m
        assert "uneseno"  in m
        assert "naplaceno" in m
        assert "stavki"   in m


def test_godisnji_top_klijenti(client):
    r = client.get("/billing/report/godisnji")
    kl = r.json()["top_klijenti"]
    assert isinstance(kl, list)
    if kl:
        assert "naziv" in kl[0]
        assert "iznos" in kl[0]


def test_godisnji_top_tipovi(client):
    r = client.get("/billing/report/godisnji")
    tt = r.json()["top_tipovi_predmeta"]
    assert isinstance(tt, list)
    tipovi = [t["tip"] for t in tt]
    assert "gradjansko" in tipovi or "radno" in tipovi


def test_godisnji_stopa_naplate_calc(client):
    # fakture: 9000 placena, 14400 izdata → naplaceno=9000, fakturisano=23400
    r = client.get("/billing/report/godisnji")
    data = r.json()
    assert data["ukupno_naplaceno_rsd"] == 9000.0
    assert data["ukupno_fakturisano"]   == 23400.0
    assert data["stopa_naplate_pct"]    == round(9000/23400*100, 1)


def test_godisnji_custom_godina(client):
    r = client.get(f"/billing/report/godisnji?godina={YEAR-1}")
    assert r.status_code == 200
    assert r.json()["godina"] == YEAR - 1


def test_godisnji_invalid_godina(client):
    r = client.get("/billing/report/godisnji?godina=1800")
    assert r.status_code == 422


def test_godisnji_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/billing/report/godisnji")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/report/csv
# ═══════════════════════════════════════════════════════════════════════════════

def test_csv_200(client):
    r = client.get("/billing/report/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")


def test_csv_content_disposition(client):
    r = client.get("/billing/report/csv")
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".csv" in cd


def test_csv_header_row(client):
    r = client.get("/billing/report/csv")
    lines = r.text.split("\n")
    header = lines[0]
    assert "Datum" in header
    assert "Iznos RSD" in header
    assert "Obračunato" in header


def test_csv_data_rows(client):
    r = client.get("/billing/report/csv")
    lines = [l for l in r.text.strip().split("\n") if l]
    assert len(lines) >= 2  # header + at least one data row


def test_csv_sa_periodom(client):
    r = client.get(f"/billing/report/csv?od={YEAR}-01-01&do={YEAR}-12-31")
    assert r.status_code == 200


def test_csv_invalid_datum(client):
    r = client.get("/billing/report/csv?od=invalid")
    assert r.status_code == 422


def test_csv_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/billing/report/csv")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/report/zastarele
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def aged_client():
    supa = _make_supa(aged=AGED_ENTRIES)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing_reports._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


def test_zastarele_200(aged_client):
    r = aged_client.get("/billing/report/zastarele")
    assert r.status_code == 200


def test_zastarele_struktura(aged_client):
    data = aged_client.get("/billing/report/zastarele").json()
    assert "ukupno_nenaplaceno_rsd" in data
    assert "aging"                   in data
    assert "top_duznici"             in data
    for bucket in ("do_30_dana", "31_60_dana", "61_90_dana", "starije_90"):
        assert bucket in data["aging"]


def test_zastarele_ukupno(aged_client):
    data = aged_client.get("/billing/report/zastarele").json()
    expected = round(5000.0 + 8000.0 + 3000.0, 2)
    assert data["ukupno_nenaplaceno_rsd"] == expected


def test_zastarele_aging_bucket_do30(aged_client):
    data = aged_client.get("/billing/report/zastarele").json()
    assert data["aging"]["do_30_dana"]["iznos"] == 3000.0
    assert data["aging"]["do_30_dana"]["stavki"] == 1


def test_zastarele_aging_bucket_31_60(aged_client):
    data = aged_client.get("/billing/report/zastarele").json()
    assert data["aging"]["31_60_dana"]["iznos"] == 8000.0


def test_zastarele_top_duznici(aged_client):
    data = aged_client.get("/billing/report/zastarele").json()
    assert isinstance(data["top_duznici"], list)
    if data["top_duznici"]:
        assert "naziv" in data["top_duznici"][0]
        assert "iznos" in data["top_duznici"][0]


def test_zastarele_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/billing/report/zastarele")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/report/po-tipu
# ═══════════════════════════════════════════════════════════════════════════════

def test_po_tipu_200(client):
    r = client.get("/billing/report/po-tipu")
    assert r.status_code == 200


def test_po_tipu_struktura(client):
    data = client.get("/billing/report/po-tipu").json()
    assert "od"          in data
    assert "do"          in data
    assert "ukupno_rsd"  in data
    assert "po_tipu"     in data
    assert isinstance(data["po_tipu"], list)


def test_po_tipu_fields(client):
    data = client.get("/billing/report/po-tipu").json()
    for t in data["po_tipu"]:
        assert "tip"          in t
        assert "iznos_rsd"    in t
        assert "stavki"       in t
        assert "ucesce_pct"   in t
        assert "predmeta"     in t


def test_po_tipu_sortiran_desc(client):
    data = client.get("/billing/report/po-tipu").json()
    iznosi = [t["iznos_rsd"] for t in data["po_tipu"]]
    assert iznosi == sorted(iznosi, reverse=True)


def test_po_tipu_ucesce_suma_100(client):
    data = client.get("/billing/report/po-tipu").json()
    if data["po_tipu"]:
        total = sum(t["ucesce_pct"] for t in data["po_tipu"])
        assert abs(total - 100.0) < 0.5  # rounding tolerance


def test_po_tipu_sa_periodom(client):
    r = client.get(f"/billing/report/po-tipu?od={YEAR}-01-01&do={YEAR}-06-30")
    assert r.status_code == 200


def test_po_tipu_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/billing/report/po-tipu")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: helpers
# ═══════════════════════════════════════════════════════════════════════════════

def test_month_range_12():
    from routers.billing_reports import _month_range
    months = _month_range(2026)
    assert len(months) == 12
    assert months[0]  == "2026-01"
    assert months[11] == "2026-12"


def test_ym_extracts():
    from routers.billing_reports import _ym
    assert _ym("2026-06-17") == "2026-06"
    assert _ym("")            == ""
    assert _ym("2026-12-31") == "2026-12"
