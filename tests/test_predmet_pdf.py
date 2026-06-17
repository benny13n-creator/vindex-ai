# -*- coding: utf-8 -*-
"""
Phase 5.3 — Export predmeta (PDF izveštaj)
Tests for predmet_pdf.py + GET /api/predmeti/{id}/pdf-export
"""
from __future__ import annotations

import os
import sys
from io import BytesIO
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

# ─── Sample data ──────────────────────────────────────────────────────────────

FAKE_USER = {"user_id": "uid-001", "email": "advokat@test.rs", "role": "pro"}

SAMPLE_PREDMET = {
    "id":         "pred-001",
    "user_id":    "uid-001",
    "naziv":      "Tužba za naknadu štete — Petrović",
    "opis":       "Predmet se odnosi na naknadu štete nastale u saobraćajnoj nesreći.",
    "tip":        "gradjansko",
    "status":     "aktivan",
    "created_at": "2024-01-15T10:00:00+00:00",
    "updated_at": "2024-05-20T14:30:00+00:00",
}

SAMPLE_DOCS = [
    {"naziv_fajla": "ugovor.pdf",   "status": "obradjeno", "velicina_kb": 125, "created_at": "2024-01-20T10:00:00+00:00"},
    {"naziv_fajla": "zapisnik.docx","status": "obradjeno", "velicina_kb": 84,  "created_at": "2024-02-10T09:00:00+00:00"},
]

SAMPLE_BELESKE = [
    {"sadrzaj": "Klijent želi brzo rešenje. Rok za odgovor je 15.02.2024.", "created_at": "2024-01-16T08:00:00+00:00"},
    {"sadrzaj": "Protivna strana odbila vansudsko poravnanje.",             "created_at": "2024-02-01T11:00:00+00:00"},
]

SAMPLE_HRON = [
    {"dogadjaj": "Prijem tužbe",        "akter": "Advokat", "datum": "15.01.2024", "datum_iso": "2024-01-15", "vaznost": "kritičan"},
    {"dogadjaj": "Odgovor na tužbu",    "akter": "Sud",     "datum": "10.02.2024", "datum_iso": "2024-02-10", "vaznost": "važan"},
    {"dogadjaj": "Ročište zakazano",    "akter": "Sud",     "datum": "05.03.2024", "datum_iso": "2024-03-05", "vaznost": "informativan"},
]


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _make_supa(predmet=None, not_found=False):
    supa = MagicMock()

    def _table(name):
        tbl = MagicMock()
        sel = MagicMock()

        if name == "predmeti":
            if not_found:
                sel.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
            else:
                sel.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=predmet or SAMPLE_PREDMET
                )
        elif name == "predmet_dokumenti":
            sel.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=SAMPLE_DOCS)
        elif name == "predmet_beleske":
            sel.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=SAMPLE_BELESKE)
        elif name == "predmet_hronologija":
            sel.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=SAMPLE_HRON)
        else:
            sel.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        tbl.select.return_value = sel
        return tbl

    supa.table.side_effect = _table
    return supa


@pytest.fixture
def client():
    supa = _make_supa()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.export._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


@pytest.fixture
def client_not_found():
    supa = _make_supa(not_found=True)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.export._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: generiši_predmet_pdf
# ═══════════════════════════════════════════════════════════════════════════════

from predmet_pdf import generiši_predmet_pdf, _fmt_date


def test_pdf_bytes_non_empty():
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 100


def test_pdf_starts_with_pdf_magic():
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET)
    assert pdf[:4] == b"%PDF"


def test_pdf_with_all_sections():
    pdf = generiši_predmet_pdf(
        SAMPLE_PREDMET, SAMPLE_DOCS, SAMPLE_BELESKE, SAMPLE_HRON
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_pdf_empty_predmet():
    pdf = generiši_predmet_pdf({"id": "x", "naziv": "Test"})
    assert pdf[:4] == b"%PDF"


def test_pdf_only_hronologija():
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, hronologija=SAMPLE_HRON)
    assert len(pdf) > 500


def test_pdf_only_dokumenti():
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, dokumenti=SAMPLE_DOCS)
    assert len(pdf) > 500


def test_pdf_only_beleske():
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, beleske=SAMPLE_BELESKE)
    assert len(pdf) > 500


def test_pdf_hronologija_multiple_priorities():
    hron = [
        {"dogadjaj": "Tužba",   "akter": "A", "datum_iso": "2024-01-01", "vaznost": "kritičan"},
        {"dogadjaj": "Ročište", "akter": "B", "datum_iso": "2024-02-01", "vaznost": "važan"},
        {"dogadjaj": "Odluka",  "akter": "C", "datum_iso": "2024-03-01", "vaznost": "informativan"},
    ]
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, hronologija=hron)
    assert pdf[:4] == b"%PDF"


def test_pdf_special_chars_in_naziv():
    predmet = {**SAMPLE_PREDMET, "naziv": "Predmet Đorđević / Žičara — Šabac"}
    pdf = generiši_predmet_pdf(predmet)
    assert pdf[:4] == b"%PDF"


def test_pdf_missing_opis():
    predmet = {k: v for k, v in SAMPLE_PREDMET.items() if k != "opis"}
    pdf = generiši_predmet_pdf(predmet)
    assert pdf[:4] == b"%PDF"


def test_pdf_long_beleska():
    beleske = [{"sadrzaj": "X" * 2000, "created_at": "2024-01-01T00:00:00+00:00"}]
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, beleske=beleske)
    assert len(pdf) > 500


def test_pdf_many_dokumenti():
    docs = [
        {"naziv_fajla": f"doc_{i}.pdf", "status": "obradjeno",
         "velicina_kb": 100, "created_at": "2024-01-01T00:00:00+00:00"}
        for i in range(20)
    ]
    pdf = generiši_predmet_pdf(SAMPLE_PREDMET, dokumenti=docs)
    assert pdf[:4] == b"%PDF"


# ─── Unit: _fmt_date ──────────────────────────────────────────────────────────

def test_fmt_date_iso():
    assert _fmt_date("2024-01-15T10:00:00+00:00") == "15.01.2024"


def test_fmt_date_none():
    assert _fmt_date(None) == "—"


def test_fmt_date_empty():
    assert _fmt_date("") == "—"


def test_fmt_date_date_only():
    assert _fmt_date("2024-06-17") == "17.06.2024"


# ═══════════════════════════════════════════════════════════════════════════════
# API: GET /api/predmeti/{predmet_id}/pdf-export
# ═══════════════════════════════════════════════════════════════════════════════

def test_pdf_export_200(client):
    r = client.get("/api/predmeti/pred-001/pdf-export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_pdf_export_content_disposition(client):
    r = client.get("/api/predmeti/pred-001/pdf-export")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".pdf" in cd


def test_pdf_export_non_empty_body(client):
    r = client.get("/api/predmeti/pred-001/pdf-export")
    assert len(r.content) > 500


def test_pdf_export_404(client_not_found):
    r = client_not_found.get("/api/predmeti/nonexistent/pdf-export")
    assert r.status_code == 404


def test_pdf_export_requires_auth():
    from fastapi.testclient import TestClient
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/api/predmeti/pred-001/pdf-export")
    assert r.status_code == 401


def test_pdf_export_filename_contains_naziv(client):
    r = client.get("/api/predmeti/pred-001/pdf-export")
    cd = r.headers.get("content-disposition", "")
    assert "vindex_predmet_" in cd
