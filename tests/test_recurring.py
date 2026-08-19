# -*- coding: utf-8 -*-
"""
Phase 7 — Ponavljajuće fakture + Email dostava faktura
Tests for routers/recurring.py + POST /billing/faktura/{id}/posalji-email
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

TODAY      = date.today().isoformat()
NEXT_MONTH = (date.today() + timedelta(days=32)).replace(day=1).isoformat()

SAMPLE_TPL = {
    "id":             "tpl-001",
    "user_id":        "uid-001",
    "naziv":          "Mesečni retainer",
    "ucestalost":     "mesecno",
    "iznos_rsd":      50000.0,
    "opis":           "Mesečno pravno savetovanje",
    "pdv_procenat":   20.0,
    "aktivan":        True,
    "sledeci_datum":  TODAY,
    "klijent_id":     "kl-001",
    "predmet_id":     None,
    "created_at":     "2026-01-01T00:00:00+00:00",
    "updated_at":     "2026-01-01T00:00:00+00:00",
}

SAMPLE_FAKTURA = {
    "id":            "fak-001",
    "user_id":       "uid-001",
    "broj_fakture":  "2026/001",
    "iznos_rsd":     50000.0,
    "iznos_sa_pdv":  60000.0,
    "bruto_rsd":     60000.0,
    "datum_fakture": "2026-06-17",
    "klijent_id":    "kl-001",
    "klijent_email": "klijent@firma.rs",
    "status":        "nacrt",
}


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _make_supa_recurring(tpl=None, tpl_list=None, faktura_row=None):
    supa  = MagicMock()
    _cache: dict = {}

    def _table(name):
        if name in _cache:
            return _cache[name]
        tbl = MagicMock()
        sel = MagicMock()

        if name == "recurring_templates":
            tpl_data = tpl or SAMPLE_TPL
            tbl.insert.return_value.execute.return_value  = MagicMock(data=[tpl_data])
            tbl.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[tpl_data])
            # V36-B: ranije MagicMock(data=[]) -- "nije nas briga za ishod DELETE-a",
            # što je bilo tačno dok je delete_recurring odbacivao rezultat. Otkad
            # handler ima zero-row guard, prazan data znači "nijedan red nije
            # obrisan" i daje 404. Uspešan DELETE vraća obrisani red, kao u
            # fixture-ima ostalih ruta sa istim guardom.
            tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[tpl_data])
            sel.eq.return_value.order.return_value.execute.return_value  = MagicMock(data=tpl_list or [SAMPLE_TPL])
            sel.eq.return_value.order.return_value.eq.return_value.execute.return_value = MagicMock(data=tpl_list or [SAMPLE_TPL])
            sel.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=tpl_data)
            sel.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=tpl_data)
            sel.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[tpl_data])

        elif name == "fakture":
            fak = faktura_row or SAMPLE_FAKTURA
            tbl.insert.return_value.execute.return_value = MagicMock(data=[fak])
            sel.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=fak)

        elif name in ("klijenti", "email_log", "billing_entries"):
            tbl.insert.return_value.execute.return_value = MagicMock(data=[{}])
            sel.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"email": "klijent@firma.rs"}
            )
            # N2 (harness rupa): `generisi_iz_sablona` čita naziv klijenta
            # lancem `.eq("id", ...).eq("user_id", uid).maybe_single()` — dva
            # `eq`, koja ovaj mock nije modelovao, pa je vraćao MagicMock i
            # `" ".join(...)` je pucao. Dodaje se SAMO taj lanac, sa
            # realističnim redom; nijedna asercija nije menjana.
            sel.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"ime": "Nikola", "prezime": "Petrović", "firma": None,
                      "email": "klijent@firma.rs"}
            )
            sel.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        tbl.select.return_value = sel
        _cache[name] = tbl
        return tbl

    supa.table.side_effect = _table
    return supa


@pytest.fixture
def client():
    supa = _make_supa_recurring()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.recurring._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /billing/recurring
# ═══════════════════════════════════════════════════════════════════════════════

def test_create_recurring_201(client):
    r = client.post("/billing/recurring", json={
        "naziv":         "Mesečni retainer Petrović",
        "ucestalost":    "mesecno",
        "iznos_rsd":     50000,
        "opis":          "Mesečno pravno savetovanje",
        "sledeci_datum": NEXT_MONTH,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "kreiran"
    assert "template" in data


def test_create_recurring_sa_klijentom(client):
    r = client.post("/billing/recurring", json={
        "naziv":         "Kvartal klijent",
        "ucestalost":    "kvartalno",
        "iznos_rsd":     120000,
        "opis":          "Kvartalni retainer",
        "sledeci_datum": NEXT_MONTH,
        "klijent_id":    "kl-001",
        "pdv_procenat":  20,
    })
    assert r.status_code == 201


def test_create_recurring_invalid_ucestalost(client):
    r = client.post("/billing/recurring", json={
        "naziv":         "Test",
        "ucestalost":    "nedeljno",
        "iznos_rsd":     5000,
        "opis":          "Test opis",
        "sledeci_datum": NEXT_MONTH,
    })
    assert r.status_code == 422


def test_create_recurring_iznos_zero(client):
    r = client.post("/billing/recurring", json={
        "naziv":         "Test",
        "ucestalost":    "mesecno",
        "iznos_rsd":     0,
        "opis":          "Test",
        "sledeci_datum": NEXT_MONTH,
    })
    assert r.status_code == 422


def test_create_recurring_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/billing/recurring", json={
        "naziv": "Test", "ucestalost": "mesecno", "iznos_rsd": 5000,
        "opis": "Test", "sledeci_datum": NEXT_MONTH,
    })
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/recurring
# ═══════════════════════════════════════════════════════════════════════════════

def test_list_recurring_200(client):
    r = client.get("/billing/recurring")
    assert r.status_code == 200
    data = r.json()
    assert "templates" in data
    assert "total"     in data
    assert "aktivnih"  in data
    assert isinstance(data["templates"], list)


def test_list_recurring_aktivan_filter(client):
    r = client.get("/billing/recurring?aktivan=true")
    assert r.status_code == 200


def test_list_recurring_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/billing/recurring")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# GET /billing/recurring/{id}
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_recurring_200(client):
    r = client.get("/billing/recurring/tpl-001")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "tpl-001"


def test_get_recurring_not_found():
    supa = _make_supa_recurring(tpl=None)
    supa.table("recurring_templates").select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
    supa.table("recurring_templates").select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.recurring._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.get("/billing/recurring/nonexistent")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH /billing/recurring/{id}
# ═══════════════════════════════════════════════════════════════════════════════

def test_patch_recurring_naziv(client):
    r = client.patch("/billing/recurring/tpl-001", json={"naziv": "Novi naziv retainera"})
    assert r.status_code == 200
    assert r.json()["status"] == "izmenjeno"


def test_patch_recurring_deactivate(client):
    r = client.patch("/billing/recurring/tpl-001", json={"aktivan": False})
    assert r.status_code == 200


def test_patch_recurring_empty_body(client):
    r = client.patch("/billing/recurring/tpl-001", json={})
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE /billing/recurring/{id}
# ═══════════════════════════════════════════════════════════════════════════════

def test_delete_inactive_recurring_204():
    inactive = {**SAMPLE_TPL, "aktivan": False}
    supa = _make_supa_recurring(tpl=inactive)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.recurring._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=True)
        r = c.delete("/billing/recurring/tpl-001")
    assert r.status_code == 204


def test_delete_active_recurring_409(client):
    r = client.delete("/billing/recurring/tpl-001")
    assert r.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════════
# POST /billing/recurring/{id}/generisi
# ═══════════════════════════════════════════════════════════════════════════════

def test_generisi_faktura_201(client):
    r = client.post("/billing/recurring/tpl-001/generisi")
    assert r.status_code == 201
    data = r.json()
    assert data["status"]        == "generisano"
    assert "faktura_id"          in data
    assert "sledeci_datum"       in data
    # N2 (OOS-B2-1): ranije `data["iznos_rsd"]` — polje imenovano po koloni koju
    # `fakture` NEMA (`42703`), pa je prolazilo samo zato što ga je mock
    # izmišljao. Ista poslovna provera („ruta vraća iznos upravo kreirane
    # fakture") izražena je kanonskom kolonom koju ruta stvarno čita.
    # `SAMPLE_FAKTURA` nije menjan — `iznos_sa_pdv: 60000.0` je već postojao i
    # jednak je starom `bruto_rsd`, što potvrđuje da je isti podatak.
    assert data["iznos_sa_pdv"]  == SAMPLE_FAKTURA["iznos_sa_pdv"]


def test_generisi_pomera_mesecno_datum():
    from routers.recurring import _next_datum
    d = date(2026, 1, 15)
    assert _next_datum(d, "mesecno")   == date(2026, 2, 15)
    assert _next_datum(d, "kvartalno") == date(2026, 4, 15)
    assert _next_datum(d, "godisnje")  == date(2027, 1, 15)


def test_generisi_inactive_409():
    inactive = {**SAMPLE_TPL, "aktivan": False}
    supa = _make_supa_recurring(tpl=inactive)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.recurring._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/recurring/tpl-001/generisi")
    assert r.status_code == 409


def test_generisi_not_found_404():
    supa = _make_supa_recurring()
    # Override da vrati None za template
    supa.table("recurring_templates").select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
    supa.table("recurring_templates").select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.recurring._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/recurring/nonexistent/generisi")
    assert r.status_code == 404


def test_generisi_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/billing/recurring/tpl-001/generisi")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: _next_datum edge cases
# ═══════════════════════════════════════════════════════════════════════════════

def test_next_datum_jan31_mesecno():
    from routers.recurring import _next_datum
    # Jan 31 + 1 mesec = Feb 28/29 (relativedelta handles this)
    d = date(2026, 1, 31)
    nxt = _next_datum(d, "mesecno")
    assert nxt.month == 2


def test_next_datum_godisnje():
    from routers.recurring import _next_datum
    d = date(2026, 6, 15)
    assert _next_datum(d, "godisnje") == date(2027, 6, 15)


# N2 (OOS-B2-1): oba testa su tvrdila `bruto_rsd` i `iznos_rsd` — kolone koje
# `fakture` NIKADA nije imala (sonda: `42703: column fakture.<x> does not
# exist`; `migrations/003_billing.sql:7-25` je jedina definicija tabele). Time
# su kodifikovala kvar zbog kojeg nijedna ponavljajuća faktura nije mogla biti
# izdata. Ista poslovna očekivanja se ovde zadržavaju, samo izražena kanonskim
# kolonama: neto -> `iznos_bez_pdv`, bruto -> `iznos_sa_pdv`. Vrednosti
# (12000 / 10000 / 8000) i provera `status == "nacrt"` su NEPROMENJENE.
def test_build_faktura_row_bruto():
    from routers.recurring import _build_faktura_row
    tpl = {**SAMPLE_TPL, "iznos_rsd": 10000.0, "pdv_procenat": 20.0}
    row = _build_faktura_row(tpl, "uid-001", "2026/0001", "Nikola Petrović")
    assert row["iznos_sa_pdv"]  == 12000.0
    assert row["iznos_bez_pdv"] == 10000.0
    assert row["status"]        == "nacrt"


def test_build_faktura_row_bez_pdv():
    from routers.recurring import _build_faktura_row
    tpl = {**SAMPLE_TPL, "iznos_rsd": 8000.0, "pdv_procenat": 0.0}
    row = _build_faktura_row(tpl, "uid-001", "2026/0002", "Nikola Petrović")
    assert row["iznos_sa_pdv"] == 8000.0


# ═══════════════════════════════════════════════════════════════════════════════
# POST /billing/faktura/{id}/posalji-email
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def email_client():
    supa = _make_supa_recurring()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing._get_supa", return_value=supa), \
         patch("routers.billing._EMAIL_SMTP_HOST", "smtp.test.com"), \
         patch("routers.billing._EMAIL_FROM", "noreply@vindex.ai"):
        yield TestClient(api.app, raise_server_exceptions=True)


def test_posalji_email_200(email_client):
    with patch("routers.billing._send_email_smtp") as mock_send, \
         patch("routers.billing._generate_pdf", return_value=b"%PDF-fake"):
        r = email_client.post("/billing/faktura/fak-001/posalji-email")
    assert r.status_code == 200
    data = r.json()
    assert data["status"]     == "poslato"
    assert data["faktura_id"] == "fak-001"
    assert "@" in data["poslato_na"]
    mock_send.assert_called_once()


def test_posalji_email_smtp_not_configured():
    supa = _make_supa_recurring()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing._get_supa", return_value=supa), \
         patch("routers.billing._EMAIL_SMTP_HOST", ""):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/faktura/fak-001/posalji-email")
    assert r.status_code == 503


def test_posalji_email_not_found():
    supa = _make_supa_recurring()
    supa.table("fakture").select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing._get_supa", return_value=supa), \
         patch("routers.billing._EMAIL_SMTP_HOST", "smtp.test.com"):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/faktura/nonexistent/posalji-email")
    assert r.status_code == 404


def test_posalji_email_no_email_422():
    supa = _make_supa_recurring(faktura_row={**SAMPLE_FAKTURA, "klijent_email": None, "klijent_id": None})
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing._get_supa", return_value=supa), \
         patch("routers.billing._EMAIL_SMTP_HOST", "smtp.test.com"):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/faktura/fak-001/posalji-email")
    assert r.status_code == 422


def test_posalji_email_smtp_error_502():
    supa = _make_supa_recurring()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.billing._get_supa", return_value=supa), \
         patch("routers.billing._EMAIL_SMTP_HOST", "smtp.test.com"), \
         patch("routers.billing._generate_pdf", return_value=b"%PDF-fake"), \
         patch("routers.billing._send_email_smtp", side_effect=Exception("Connection refused")):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.post("/billing/faktura/fak-001/posalji-email")
    assert r.status_code == 502


def test_posalji_email_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/billing/faktura/fak-001/posalji-email")
    assert r.status_code == 401
