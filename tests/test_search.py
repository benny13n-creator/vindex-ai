# -*- coding: utf-8 -*-
"""
Phase 8 — Global pretraga
Tests for GET /api/search
"""
from __future__ import annotations

import os
import sys
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

SAMPLE_PREDMET = {"id": "p-001", "naziv": "Tužba Petrović", "opis": "Naknada štete", "tip": "gradjansko", "status": "aktivan"}
# B-U-002 (2026-08-22) — OLD/NEW/WHY, zamena a ne slabljenje:
#   OLD: {"naziv_firme": None, ..., "pib": "123456789"}
#   NEW: {"firma": None, ..., "status": "aktivan"}   (bez `pib`)
#   WHY: `klijenti.naziv_firme` i `klijenti.pib` NE POSTOJE u produkcionoj bazi
#        (sondirano: 42703 za obe). Fikstura je opisivala šemu koja ne postoji,
#        pa je test bio zelen dok je produkcija vraćala `nepotpuno: ["klijenti"]`
#        na svaki upit. Kanonske kolone su `firma` (isto ime koje koristi
#        `GET /klijenti`, klijenti/router.py:331) i `pib_encrypted` (PIB se
#        čuva samo šifrovan, pa `ilike` nad njim nema smisla). `status` je
#        dodat jer pretraga sada, kao i `GET /klijenti`, isključuje
#        soft-deleted klijente.
SAMPLE_KLIJENT = {"id": "kl-001", "ime": "Nikola", "prezime": "Petrović", "firma": None, "email": "n@test.rs", "status": "aktivan"}
SAMPLE_DOK     = {"id": "d-001", "naziv_fajla": "ugovor_petrovic.pdf", "predmet_id": "p-001", "status": "indeksirano", "tekst_sadrzaj": "Ugovor izmedju Petrović i ABC d.o.o.", "created_at": "2026-01-01"}
SAMPLE_BILLING = {"id": "b-001", "opis": "Konsultacija Petrović", "iznos_rsd": 7500.0, "predmet_id": "p-001", "datum": "2026-06-01"}
SAMPLE_HRON    = {"id": "h-001", "predmet_id": "p-001", "dogadjaj": "Prijem tužbe Petrović", "datum_iso": "2026-01-15", "vaznost": "kritičan"}
SAMPLE_BELESKA = {"id": "be-001", "predmet_id": "p-001", "sadrzaj": "Klijent Petrović želi hitno rešenje.", "created_at": "2026-01-16T10:00:00"}


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _make_supa(predmeti=None, klijenti=None, dokumenti=None, billing=None, hron=None, beleske=None):
    supa  = MagicMock()
    _cache: dict = {}

    def _table(name):
        if name in _cache:
            return _cache[name]
        tbl = MagicMock()
        sel = MagicMock()

        def _chain(**kw):
            q = sel
            q.eq.return_value = q
            q.or_.return_value = q
            q.ilike.return_value = q
            q.in_.return_value = q
            q.limit.return_value = q
            return q

        if name == "predmeti":
            preds = predmeti if predmeti is not None else [SAMPLE_PREDMET]
            sel.eq.return_value = sel
            sel.or_.return_value = sel
            sel.ilike.return_value = sel
            sel.in_.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=preds)
            sel.eq.return_value.or_.return_value = sel
            sel.eq.return_value.or_.return_value.limit.return_value = sel

        elif name == "klijenti":
            kls = klijenti if klijenti is not None else [SAMPLE_KLIJENT]
            sel.eq.return_value = sel
            sel.or_.return_value = sel
            sel.ilike.return_value = sel
            sel.in_.return_value = sel
            sel.limit.return_value = sel
            # B-U-002: `.neq(...)` je ranije nedostajao u lancu, pa je vraćao
            # svež MagicMock i cela grana bi pukla čim ga pretraga pozove.
            sel.neq.return_value = sel
            sel.execute.return_value = MagicMock(data=kls)

        elif name == "predmet_dokumenti":
            docs = dokumenti if dokumenti is not None else [SAMPLE_DOK]
            sel.eq.return_value = sel
            sel.or_.return_value = sel
            sel.ilike.return_value = sel
            sel.in_.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=docs)

        elif name == "billing_entries":
            bil = billing if billing is not None else [SAMPLE_BILLING]
            sel.eq.return_value = sel
            sel.or_.return_value = sel
            sel.ilike.return_value = sel
            sel.in_.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=bil)

        elif name == "predmet_hronologija":
            h = hron if hron is not None else [SAMPLE_HRON]
            sel.eq.return_value = sel
            sel.in_.return_value = sel
            sel.ilike.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=h)

        elif name == "predmet_beleske":
            b = beleske if beleske is not None else [SAMPLE_BELESKA]
            sel.eq.return_value = sel
            sel.in_.return_value = sel
            sel.ilike.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=b)

        tbl.select.return_value = sel
        _cache[name] = tbl
        return tbl

    supa.table.side_effect = _table
    return supa


@pytest.fixture
def client():
    supa = _make_supa()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.search._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Osnovni GET /api/search
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_200(client):
    r = client.get("/api/search?q=Petrović")
    assert r.status_code == 200
    data = r.json()
    assert data["q"] == "Petrović"
    assert "ukupno" in data
    assert isinstance(data["ukupno"], int)


def test_search_struktura_odgovora(client):
    r = client.get("/api/search?q=ugovor")
    assert r.status_code == 200
    data = r.json()
    for tip in ("predmeti", "klijenti", "dokumenti", "billing", "hronologija", "beleske"):
        assert tip in data, f"Nedostaje tip: {tip}"
        assert isinstance(data[tip], list)


def test_search_vraca_predmete(client):
    r = client.get("/api/search?q=Tužba")
    data = r.json()
    assert len(data["predmeti"]) >= 1
    item = data["predmeti"][0]
    assert item["tip"]   == "predmet"
    assert "id"          in item
    assert "naziv"       in item
    assert "meta"        in item


def test_search_vraca_klijente(client):
    r = client.get("/api/search?q=Nikola")
    data = r.json()
    assert len(data["klijenti"]) >= 1
    item = data["klijenti"][0]
    assert item["tip"]  == "klijent"
    assert "naziv"      in item


def test_search_vraca_dokumente(client):
    r = client.get("/api/search?q=ugovor")
    data = r.json()
    assert len(data["dokumenti"]) >= 1
    item = data["dokumenti"][0]
    assert item["tip"] == "dokument"


def test_search_vraca_billing(client):
    r = client.get("/api/search?q=Konsultacija")
    data = r.json()
    assert len(data["billing"]) >= 1
    item = data["billing"][0]
    assert item["tip"]   == "billing"
    assert "RSD"         in item["preview"]


def test_search_vraca_hronologiju(client):
    r = client.get("/api/search?q=tužbe")
    data = r.json()
    assert len(data["hronologija"]) >= 1
    item = data["hronologija"][0]
    assert item["tip"]        == "hronologija"
    assert "predmet_id"       in item["meta"]


def test_search_vraca_beleske(client):
    r = client.get("/api/search?q=hitno")
    data = r.json()
    assert len(data["beleske"]) >= 1
    item = data["beleske"][0]
    assert item["tip"]     == "beleska"
    assert "predmet_id"    in item["meta"]


def test_search_ukupno_sabiranie(client):
    r = client.get("/api/search?q=test")
    data = r.json()
    # ukupno = zbir svih tipova
    total = sum(len(data[t]) for t in ("predmeti","klijenti","dokumenti","billing","hronologija","beleske"))
    assert data["ukupno"] == total


# ═══════════════════════════════════════════════════════════════════════════════
# Filter po vrste
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_samo_predmeti(client):
    r = client.get("/api/search?q=tužba&vrste=predmeti")
    assert r.status_code == 200
    data = r.json()
    assert "predmeti"    in data
    assert "klijenti"    not in data
    assert "dokumenti"   not in data


def test_search_dva_tipa(client):
    r = client.get("/api/search?q=petrovic&vrste=predmeti,klijenti")
    data = r.json()
    assert "predmeti" in data
    assert "klijenti" in data
    assert "billing"  not in data


def test_search_nepostojeci_tip_ignorisan(client):
    r = client.get("/api/search?q=test&vrste=predmeti,nepostojeci")
    assert r.status_code == 200
    data = r.json()
    assert "predmeti" in data
    assert "nepostojeci" not in data


# ═══════════════════════════════════════════════════════════════════════════════
# Validacija
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_q_prekratak_422(client):
    r = client.get("/api/search?q=a")
    assert r.status_code == 422


def test_search_q_dva_znaka_ok(client):
    r = client.get("/api/search?q=ab")
    assert r.status_code == 200


def test_search_bez_q_422(client):
    r = client.get("/api/search")
    assert r.status_code == 422


def test_search_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/api/search?q=test")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# limit parametar
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_limit_param(client):
    r = client.get("/api/search?q=test&limit=3")
    assert r.status_code == 200


def test_search_limit_max_10(client):
    r = client.get("/api/search?q=test&limit=99")
    assert r.status_code == 200  # capped na 10, ne vraća grešku


# ═══════════════════════════════════════════════════════════════════════════════
# Prazni rezultati
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_nema_rezultata():
    supa = _make_supa(predmeti=[], klijenti=[], dokumenti=[], billing=[], hron=[], beleske=[])
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.search._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=True)
        r = c.get("/api/search?q=xyzabc123")
    assert r.status_code == 200
    assert r.json()["ukupno"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_predmeti_unit():
    from routers.search import _search_predmeti
    supa = _make_supa()
    res  = _search_predmeti(supa, "uid-001", "Petrović", 5)
    assert isinstance(res, list)
    if res:
        assert res[0]["tip"] == "predmet"


def test_search_klijenti_unit():
    from routers.search import _search_klijenti
    supa = _make_supa()
    res  = _search_klijenti(supa, "uid-001", "Nikola", 5)
    assert isinstance(res, list)
    if res:
        assert res[0]["tip"] == "klijent"
        assert "Nikola" in res[0]["naziv"]


def test_search_billing_unit():
    from routers.search import _search_billing
    supa = _make_supa()
    res  = _search_billing(supa, "uid-001", "Konsultacija", 5)
    assert isinstance(res, list)
    if res:
        assert res[0]["tip"] == "billing"
        assert "RSD" in res[0]["preview"]


def test_q_sql_injection_sanitized(client):
    # % i ' ne smeju da bace grešku
    r = client.get("/api/search?q=test%25OR%271%27%3D%271")
    assert r.status_code == 200


def test_search_hronologija_prazni_pids():
    from routers.search import _search_hronologija
    supa = _make_supa(predmeti=[])
    res  = _search_hronologija(supa, "uid-001", "tužba", 5)
    assert res == []


# ═══════════════════════════════════════════════════════════════════════════════
# Night Shift M-003 (2026-08-02): search must reach predmet_dokumenti, not the
# dead uploaded_documents table (migrations/057_active_orphaned_tables.sql's
# own comment: that table has zero writers anywhere in the codebase).
# ═══════════════════════════════════════════════════════════════════════════════

def test_search_dokumenti_queries_predmet_dokumenti_not_dead_table():
    """The table search actually reads must be predmet_dokumenti -- the one
    Smart Intake's finalize path (routers/smart_intake.py) actually writes
    into. uploaded_documents (dead, zero writers) must not be the query
    target any more."""
    from routers.search import _search_dokumenti

    queried_tables = []
    supa = MagicMock()

    def _table(name):
        queried_tables.append(name)
        t = MagicMock()
        t.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value.data = [SAMPLE_DOK]
        return t

    supa.table.side_effect = _table
    res = _search_dokumenti(supa, "uid-001", "ugovor", 5)

    assert queried_tables == ["predmet_dokumenti"]
    assert "uploaded_documents" not in queried_tables
    assert res[0]["tip"] == "dokument"


def test_search_finds_document_by_content_from_smart_intake_path():
    """User scenario: a lawyer searches for a case using a phrase that only
    appears in a document's OCR/extracted text, ingested through Smart
    Intake's finalize endpoint (which writes into predmet_dokumenti.tekst_sadrzaj,
    not uploaded_documents). Before this fix, this search would have
    returned nothing, regardless of which upload path the document came
    through, because uploaded_documents never receives a row from any code
    path."""
    from routers.search import _search_dokumenti

    doc_from_smart_intake = {
        "id": "d-si-001",
        "naziv_fajla": "presuda.pdf",
        "predmet_id": "p-001",
        "status": "indeksirano",
        "tekst_sadrzaj": "Osnovni sud u Beogradu, rok za žalbu 15 dana od dostavljanja.",
        "created_at": "2026-08-02",
    }
    supa = _make_supa(dokumenti=[doc_from_smart_intake])
    res = _search_dokumenti(supa, "uid-001", "žalbu", 5)

    assert len(res) == 1
    assert res[0]["id"] == "d-si-001"
    assert "žalbu" in res[0]["preview"] or "sud" in res[0]["preview"].lower()


def test_search_dokumenti_preview_uses_text_content():
    from routers.search import _search_dokumenti
    supa = _make_supa()
    res = _search_dokumenti(supa, "uid-001", "ugovor", 5)
    assert "Petrović" in res[0]["preview"] or "ABC" in res[0]["preview"]
