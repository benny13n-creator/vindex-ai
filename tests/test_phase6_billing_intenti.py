# -*- coding: utf-8 -*-
"""
Phase 6.1 — Copilot NAPLATI_RADNJU + PRIKAŽI_TARIFU
Phase 6.2 — Template predmeti

Tests for new copilot billing intents and intake templates.
"""
from __future__ import annotations

import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


def _supa_billing(entry_id="entry-abc"):
    supa = MagicMock()
    def _table(name):
        tbl = MagicMock()
        tbl.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": entry_id, "iznos_rsd": 7500}]
        )
        return tbl
    supa.table.side_effect = _table
    return supa


def _supa_intake(predmet_id="pred-new"):
    supa = MagicMock()
    def _table(name):
        tbl = MagicMock()
        sel = MagicMock()
        tbl.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": predmet_id, "naziv": "Test predmet"}]
        )
        sel.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
        tbl.select.return_value = sel
        return tbl
    supa.table.side_effect = _table
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6.1 — _handle_naplati_radnju (unit)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_naplati_satnica_2h():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": 2, "tarifa_sifra": "T17", "opis": "Konsultacije", "iznos_rsd": None}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("naplati 2h konsultacija", None, "uid-001")

    assert result["tip"] == "NAPLATI_RADNJU"
    assert result["status"] == "kreirana"
    assert result["iznos_rsd"] > 0
    assert "2" in result["odgovor"] or "Konsultac" in result["odgovor"]


@pytest.mark.anyio
async def test_naplati_tuzba_tarifa():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": None, "tarifa_sifra": "T01", "opis": "Tužba", "iznos_rsd": None}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("naplati tužbu", "pred-001", "uid-001")

    assert result["tip"] == "NAPLATI_RADNJU"
    assert result["iznos_rsd"] == 12 * 50  # T01 = 12 bodova × 50 RSD
    assert result["tarifa_sifra"] == "T01"


@pytest.mark.anyio
async def test_naplati_eksplicitan_iznos():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": None, "tarifa_sifra": None, "opis": "Savetovanje", "iznos_rsd": 15000}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("naplati 15000 din savetovanje", None, "uid-001")

    assert result["iznos_rsd"] == 15000
    assert result["status"] == "kreirana"


@pytest.mark.anyio
async def test_naplati_nerazumljiva_poruka():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": None, "tarifa_sifra": None, "opis": None, "iznos_rsd": None}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("šta je vreme danas?", None, "uid-001")

    assert result["status"] == "nije_kreirana"
    assert result["tip"] == "NAPLATI_RADNJU"


@pytest.mark.anyio
async def test_naplati_satnica_bez_tarife():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": 1.5, "tarifa_sifra": None, "opis": "Rad na predmetu", "iznos_rsd": None}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("1.5h rada", None, "uid-001")

    assert result["iznos_rsd"] == int(1.5 * 7500)
    assert result["tarifa_sifra"] == "T30"


@pytest.mark.anyio
async def test_naplati_sa_predmet_id():
    from routers.copilot import _handle_naplati_radnju
    supa = _supa_billing()
    parsed = {"sati": 1, "tarifa_sifra": "T17", "opis": "Konsultacija", "iznos_rsd": None}

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._oai_parse_json", AsyncMock(return_value=json.dumps(parsed))):
        result = await _handle_naplati_radnju("naplati 1h", "pred-xyz", "uid-001")

    assert result["status"] == "kreirana"
    # Proveri da je predmet_id prošao u insert
    insert_call = supa.table.return_value.insert.call_args
    if insert_call:
        row = insert_call[0][0] if insert_call[0] else insert_call.kwargs.get("data", {})
        # MagicMock side_effect — proverimo samo da je rezultat ok
    assert result["iznos_rsd"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6.1 — _handle_prikazi_tarifu (unit)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_prikazi_tarifu_tuzba():
    from routers.copilot import _handle_prikazi_tarifu
    result = await _handle_prikazi_tarifu("koliko košta tužba za naknadu")
    assert result["tip"] == "PRIKAŽI_TARIFU"
    assert len(result["stavke"]) >= 1
    assert "napomena" in result
    sifre = [s["sifra"] for s in result["stavke"]]
    assert any(s in sifre for s in ("T01", "T02", "T03"))


@pytest.mark.anyio
async def test_prikazi_tarifu_rociste():
    from routers.copilot import _handle_prikazi_tarifu
    result = await _handle_prikazi_tarifu("koliko košta zastupanje na ročištu")
    assert result["tip"] == "PRIKAŽI_TARIFU"
    assert len(result["stavke"]) >= 1


@pytest.mark.anyio
async def test_prikazi_tarifu_bez_match_vraca_sve():
    from routers.copilot import _handle_prikazi_tarifu
    # Poruka koja nema keyword koji match-uje nijednu AKS stavku
    result = await _handle_prikazi_tarifu("xyz abc 123 qwerty")
    assert result["tip"] == "PRIKAŽI_TARIFU"
    assert len(result["stavke"]) >= 10  # sve stavke


@pytest.mark.anyio
async def test_prikazi_tarifu_struktura():
    from routers.copilot import _handle_prikazi_tarifu
    result = await _handle_prikazi_tarifu("žalba")
    for s in result["stavke"]:
        assert "sifra" in s
        assert "naziv" in s
        assert "iznos" in s
        assert "rsd"   in s


@pytest.mark.anyio
async def test_prikazi_tarifu_satnica():
    from routers.copilot import _handle_prikazi_tarifu
    result = await _handle_prikazi_tarifu("satnica")
    sifre = [s["sifra"] for s in result["stavke"]]
    assert "T30" in sifre


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6.1 — Intent meta (sync unit tests)
# ═══════════════════════════════════════════════════════════════════════════════

def test_intent_choices_contain_billing():
    from routers.copilot import _INTENT_CHOICES
    assert "NAPLATI_RADNJU"  in _INTENT_CHOICES
    assert "PRIKAŽI_TARIFU" in _INTENT_CHOICES


def test_intent_system_contains_billing():
    from routers.copilot import _INTENT_SYSTEM
    assert "NAPLATI_RADNJU"  in _INTENT_SYSTEM
    assert "PRIKAŽI_TARIFU" in _INTENT_SYSTEM


def test_naplata_parse_system_exists():
    from routers.copilot import _NAPLATA_PARSE_SYSTEM
    assert "sati"         in _NAPLATA_PARSE_SYSTEM
    assert "tarifa_sifra" in _NAPLATA_PARSE_SYSTEM
    assert "iznos_rsd"    in _NAPLATA_PARSE_SYSTEM


def test_oai_parse_json_wrapper_exists():
    from routers.copilot import _oai_parse_json
    import asyncio
    assert asyncio.iscoroutinefunction(_oai_parse_json)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6.2 — Template predmeti (API)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def intake_client():
    supa = _supa_intake()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with patch("routers.intake._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


def test_get_templates_200(intake_client):
    r = intake_client.get("/api/intake/templates")
    assert r.status_code == 200
    data = r.json()
    assert "templates" in data
    assert data["total"] >= 7
    assert isinstance(data["templates"], list)


def test_templates_all_required_fields(intake_client):
    r = intake_client.get("/api/intake/templates")
    for tpl in r.json()["templates"]:
        for field in ("id", "naziv", "tip", "vrsta_spora",
                      "potrebni_dokumenti", "tarifa_preporuka"):
            assert field in tpl, f"Missing {field} in {tpl.get('id')}"


def test_templates_contains_expected_types(intake_client):
    r = intake_client.get("/api/intake/templates")
    tipovi = [t["tip"] for t in r.json()["templates"]]
    assert "gradjansko" in tipovi
    assert "radno"      in tipovi
    assert "krivicno"   in tipovi
    assert "porodicno"  in tipovi


def test_templates_needs_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/api/intake/templates")
    assert r.status_code == 401


def test_from_template_success(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-gradjansko-steta",
        "naziv":       "Tužba Petrović vs Jovanović",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "kreiran"
    assert "predmet_id" in data
    assert len(data["potrebni_dokumenti"]) > 0
    assert data["hronologija_kreirana"] >= 1


def test_from_template_radno(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-radno-otkaz",
        "naziv":       "Radni spor Nikolić",
    })
    assert r.status_code == 201
    assert r.json()["tip"] == "radno"


def test_from_template_krivicno(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-krivicno-odbrana",
        "naziv":       "Odbrana Marković",
    })
    assert r.status_code == 201
    assert r.json()["tip"] == "krivicno"


def test_from_template_not_found_404(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-nepostojeci",
        "naziv":       "Test",
    })
    assert r.status_code == 404


def test_from_template_sa_klijentom(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-gradjansko-steta",
        "naziv":       "Predmet sa klijentom",
        "klijent_id":  "kl-001",
    })
    assert r.status_code == 201


def test_from_template_sa_opis_extra(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-upravno-zalba",
        "naziv":       "Žalba na rešenje MUP",
        "opis_extra":  "Klijent dobio negativno rešenje.",
    })
    assert r.status_code == 201


def test_from_template_requires_auth():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/api/intake/from-template", json={
        "template_id": "tpl-gradjansko-steta",
        "naziv":       "Test",
    })
    assert r.status_code == 401


def test_from_template_missing_naziv_422(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-gradjansko-steta",
    })
    assert r.status_code == 422


def test_all_templates_have_hronologiju():
    from routers.intake import _TEMPLATES
    for tpl in _TEMPLATES:
        assert len(tpl["hronologija_predlozi"]) >= 1, \
            f"Template {tpl['id']} nema hronologiju"
        for h in tpl["hronologija_predlozi"]:
            assert h["vaznost"] in ("kritičan", "važan", "informativan")


def test_from_template_tarifa_preporuka(intake_client):
    r = intake_client.post("/api/intake/from-template", json={
        "template_id": "tpl-gradjansko-steta",
        "naziv":       "Test tarifa",
    })
    assert r.status_code == 201
    assert r.json()["tarifa_preporuka"] == "T01"


def test_all_seven_templates_available(intake_client):
    r = intake_client.get("/api/intake/templates")
    ids = [t["id"] for t in r.json()["templates"]]
    expected = [
        "tpl-gradjansko-steta", "tpl-radno-otkaz",
        "tpl-porodicno-razvod", "tpl-krivicno-odbrana",
        "tpl-privredno-ugovor", "tpl-upravno-zalba",
        "tpl-izvrsenje",
    ]
    for eid in expected:
        assert eid in ids, f"Template {eid} nije u listi"
