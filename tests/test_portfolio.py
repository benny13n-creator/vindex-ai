# -*- coding: utf-8 -*-
"""Phase 11 — Portfolio Intelligence
Tests for GET /portfolio/dashboard
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

TODAY     = date.today().isoformat()
IN_3_DAYS = (date.today() + timedelta(days=3)).isoformat()
IN_10_DAYS= (date.today() + timedelta(days=10)).isoformat()

SAMPLE_PREDMETI = [
    {"id": "p1", "naziv": "Tužba Petrović", "tip": "gradjansko", "status": "aktivan",   "updated_at": TODAY},
    {"id": "p2", "naziv": "Spor Nikolić",   "tip": "radno",      "status": "aktivan",   "updated_at": TODAY},
    {"id": "p3", "naziv": "Stečaj DOO",     "tip": "privredno",  "status": "zatvoren",  "updated_at": TODAY},
]

SAMPLE_ROKOVI = [
    {"predmet_id": "p1", "dogadjaj": "Ročište",       "datum_iso": IN_3_DAYS,  "vaznost": "kritičan"},
    {"predmet_id": "p2", "dogadjaj": "Rok za odgovor","datum_iso": IN_10_DAYS, "vaznost": "normalan"},
]

SAMPLE_HRON_RECENT = [
    {"predmet_id": "p1"},
]
SAMPLE_BEL_RECENT = []


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _make_supa(predmeti=None, rokovi=None, hron=None, bel=None):
    supa  = MagicMock()
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
        sel.limit.return_value = sel

        if name == "predmeti":
            sel.execute.return_value = MagicMock(data=predmeti if predmeti is not None else SAMPLE_PREDMETI)
        elif name == "predmet_hronologija":
            sel.execute.return_value = MagicMock(data=rokovi if rokovi is not None else SAMPLE_ROKOVI)
            # Second call for hron_recent uses same table
        elif name == "predmet_beleske":
            sel.execute.return_value = MagicMock(data=bel if bel is not None else SAMPLE_BEL_RECENT)
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
    with patch("routers.portfolio._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


# ─── Osnovna struktura ────────────────────────────────────────────────────────

def test_dashboard_200(client):
    r = client.get("/portfolio/dashboard")
    assert r.status_code == 200


def test_dashboard_auth_required():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/portfolio/dashboard")
    assert r.status_code == 401


def test_dashboard_struktura(client):
    d = client.get("/portfolio/dashboard").json()
    for field in ("ukupno_predmeta", "ukupno_aktivnih", "po_statusu", "po_tipu",
                  "rokovi_7_dana", "rokovi_14_dana", "hitni_rokovi",
                  "neaktivni_30_dana", "summary"):
        assert field in d, f"Nedostaje: {field}"


# ─── Vrednosti ────────────────────────────────────────────────────────────────

def test_ukupno_predmeta(client):
    d = client.get("/portfolio/dashboard").json()
    assert d["ukupno_predmeta"] == 3


def test_ukupno_aktivnih(client):
    d = client.get("/portfolio/dashboard").json()
    assert d["ukupno_aktivnih"] == 2  # p1 + p2; p3 zatvoren


def test_po_statusu_sadrzaj(client):
    d = client.get("/portfolio/dashboard").json()
    assert "aktivan"  in d["po_statusu"]
    assert "zatvoren" in d["po_statusu"]
    assert d["po_statusu"]["aktivan"]  == 2
    assert d["po_statusu"]["zatvoren"] == 1


def test_po_tipu_sadrzaj(client):
    d = client.get("/portfolio/dashboard").json()
    assert "gradjansko" in d["po_tipu"]
    assert "radno"      in d["po_tipu"]


def test_rokovi_7_dana(client):
    d = client.get("/portfolio/dashboard").json()
    rokovi7 = d["rokovi_7_dana"]
    assert isinstance(rokovi7, list)
    assert len(rokovi7) == 1
    assert rokovi7[0]["dogadjaj"] == "Ročište"


def test_rokovi_14_dana(client):
    d = client.get("/portfolio/dashboard").json()
    rokovi14 = d["rokovi_14_dana"]
    assert isinstance(rokovi14, list)
    assert len(rokovi14) == 1
    assert rokovi14[0]["dogadjaj"] == "Rok za odgovor"


def test_hitni_rokovi(client):
    d = client.get("/portfolio/dashboard").json()
    hitni = d["hitni_rokovi"]
    assert isinstance(hitni, list)
    assert len(hitni) == 1
    assert hitni[0]["vaznost"] == "kritičan"


def test_neaktivni_30_dana():
    # Kad nema hron/bel aktivnosti, svi aktivni predmeti su neaktivni
    supa = _make_supa(predmeti=SAMPLE_PREDMETI, rokovi=[], hron=[], bel=[])
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.portfolio._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=True)
        d = c.get("/portfolio/dashboard").json()
    neaktivni_ids = [n["predmet_id"] for n in d["neaktivni_30_dana"]]
    assert "p1" in neaktivni_ids
    assert "p2" in neaktivni_ids
    assert "p3" not in neaktivni_ids  # p3 je zatvoren → ne prikazuje se


def test_summary_nije_prazan(client):
    d = client.get("/portfolio/dashboard").json()
    assert isinstance(d["summary"], str)
    assert len(d["summary"]) > 5


def test_summary_sadrzi_aktivne(client):
    d = client.get("/portfolio/dashboard").json()
    assert "2" in d["summary"] or "aktivn" in d["summary"]


def test_rokovi_entry_struktura(client):
    d = client.get("/portfolio/dashboard").json()
    if d["rokovi_7_dana"]:
        r = d["rokovi_7_dana"][0]
        assert "predmet_id"    in r
        assert "predmet_naziv" in r
        assert "dogadjaj"      in r
        assert "datum_iso"     in r


def test_prazni_predmeti():
    supa = _make_supa(predmeti=[], rokovi=[], hron=[], bel=[])
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.portfolio._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=True)
        d = c.get("/portfolio/dashboard").json()
    assert d["ukupno_predmeta"] == 0
    assert d["ukupno_aktivnih"] == 0
    assert d["rokovi_7_dana"]   == []
    assert d["hitni_rokovi"]    == []
