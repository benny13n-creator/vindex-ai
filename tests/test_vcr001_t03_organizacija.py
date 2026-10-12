# -*- coding: utf-8 -*-
"""VCR001 T03 — organizacija predmeta iz dokumenata.

A) Hronologija nosi IZVOR (A018 B8): `datumi_kljucni[].lokacija` „DOK-NN“ → `dokument_id` (isti zatvoren razrešavač).
B) Rok iz dokumenta koji čeka odluku → Case Action „Planirati rokove“ sa poreklom (A018 S5 / B11). Potvrda ili odbijanje
   (lanac odluka FAZA 6.5) zatvara akciju preko trajnog događaja MANUAL_CORRECTION_APPLIED. Rok NE postaje
   obavezujuć bez potvrde; nepročitan izvor ne menja akcije.
"""
import asyncio
import uuid
from datetime import date, timedelta

import pytest

from shared import genome_contract as GC
from tests.ns006_fake import dispecuj
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, _novi_predmet, solo  # noqa: F401

D1, D2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
DOKUMENTI = [{"id": D1, "redni_broj": 1, "naziv_fajla": "Tuzba.pdf"}, {"id": D2, "redni_broj": 2, "naziv_fajla": "Resenje.pdf"}]
GENOME = {"verzija": 3, "datumi_kljucni": [
    {"opis": "Rešenje o otkazu uručeno", "datum": "2025-03-17", "znacaj": "kriticno", "lokacija": "DOK-02 str.1"},
    {"opis": "Tužba podneta", "datum": "2025-05-02", "znacaj": "bitno", "lokacija": "DOK-01"},
    {"opis": "Navodni sastanak", "datum": "2025-01-10", "znacaj": "informativno", "lokacija": "DOK-09 str.3"},
    {"opis": "Zaposlenje počelo", "datum": "2019-02-01", "znacaj": "informativno"},
]}


def _hron(sastav):
    return {s["vrednost"]: (s.get("lokacija") or {}).get("dokument_id") for s in sastav["hronologija"]["stavke"]}


# ── A) izvor u hronologiji ────────────────────────────────────────────────────────────────────────────────────────
def test_hronologija_nosi_razresen_izvor_a_nepoznat_ne_izmislja():
    s = GC.sastavi(predmet={"id": "p1", "naziv": "P"}, case_dna=GENOME, dokumenti=DOKUMENTI, dokazi=[])
    h = _hron(s)
    assert h["Rešenje o otkazu uručeno"] == D2 and h["Tužba podneta"] == D1
    assert h["Navodni sastanak"] is None and h["Zaposlenje počelo"] is None        # DOK-09 ne postoji; bez oznake
    datumi = [x["datum"] for x in s["hronologija"]["stavke"]]
    assert datumi == sorted(datumi)                                                # hronološki redosled


def test_neprocitani_dokumenti_ne_daju_izvor():
    s = GC.sastavi(predmet={"id": "p1", "naziv": "P"}, case_dna=GENOME, dokumenti=DOKUMENTI, dokazi=[],
                   izvori={"dokumenti": "GRESKA"})
    assert all(v is None for v in _hron(s).values())


def test_stariji_genome_bez_lokacije_i_dalje_radi():
    g = {"verzija": 1, "datumi_kljucni": [{"opis": "Događaj", "datum": "2025-01-01", "znacaj": "bitno"}]}
    s = GC.sastavi(predmet={"id": "p1", "naziv": "P"}, case_dna=g, dokumenti=DOKUMENTI, dokazi=[])
    assert _hron(s) == {"Događaj": None}


# ── B) rok iz dokumenta → akcija pregleda sa poreklom ─────────────────────────────────────────────────────────────
def _ai_rok(b, pid, izvor="AI_AUTONOMOUS", dana=12, dok=None):
    rid = str(uuid.uuid4())
    d = (date.today() + timedelta(days=dana)).isoformat()
    b.tabele["predmet_hronologija"].append({"id": rid, "predmet_id": pid, "user_id": "uid-A", "dogadjaj": "Rok za žalbu",
                                            "datum": d, "datum_iso": d, "vrsta": "rok", "izvor": izvor, "dokument_id": dok})
    return rid


def _osvezi_akcije(pid):
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "test"}))


def _rok_akcije(b, pid, status="open"):
    return [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == status
            and (a.get("dokaz") or {}).get("izvor") == "predmet_hronologija"]


@pytest.fixture
def audit_lanac(monkeypatch):
    """Harness (tests/ns005_harness.py) namerno gasi `log_action`; lanac odluka o rokovima (FAZA 6.5) je INSERT-only
    `audit_immutable` sa rastućim `seq` — ovde se upisuje u fake tabelu (harness emulira `seq`)."""
    import shared.audit_immutable as audit
    from api import _get_supa

    async def _log(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        r = _get_supa().table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                                       "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(audit, "log_action", _log)


@pytest.fixture(autouse=True)
def _sonda_129():
    from shared import rokovi
    rokovi._resetuj_sondu()
    yield
    rokovi._resetuj_sondu()


def test_ai_rok_daje_akciju_sa_poreklom_a_potvrda_je_zatvara(solo, audit_lanac):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    rid = _ai_rok(b, pid, dok=D1)
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    akc = _rok_akcije(b, pid)
    assert len(akc) == 1 and akc[0]["tip"] == "PLANIRATI_ROKOVE"
    assert akc[0]["dokaz"]["hronologija_id"] == rid and akc[0]["dokaz"]["dokument_id"] == D1
    assert "čeka vašu potvrdu" in akc[0]["razlog"] and akc[0]["dokaz"]["stanje_odluke"] == "UNCONFIRMED"
    r = k.post(f"/api/rokovi/{rid}/potvrdi", json={}, headers=A)
    assert r.status_code == 200 and r.json()["stanje_odluke"] == "CONFIRMED", r.text
    _do_kraja_dogadjaja(b)                                       # MANUAL_CORRECTION_APPLIED → refresh_case_actions
    assert _rok_akcije(b, pid) == [] and len(_rok_akcije(b, pid, "closed")) == 1


def test_odbijanje_takodje_zatvara_i_ne_brise_rok(solo, audit_lanac):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    rid = _ai_rok(b, pid)
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    assert len(_rok_akcije(b, pid)) == 1
    assert k.post(f"/api/rokovi/{rid}/odbij", json={}, headers=A).json()["stanje_odluke"] == "REJECTED"
    _do_kraja_dogadjaja(b)
    assert _rok_akcije(b, pid) == []
    assert any(h["id"] == rid for h in b.tabele["predmet_hronologija"])      # odbijen rok se ne briše


def test_rucno_unet_rok_ne_trazi_potvrdu(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _ai_rok(b, pid, izvor="HUMAN_DIRECT")
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    assert _rok_akcije(b, pid) == []


def test_neprocitana_hronologija_ne_menja_akcije(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _ai_rok(b, pid)
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    pre = [(a["id"], a["status"]) for a in b.tabele["case_actions"]]
    assert len(_rok_akcije(b, pid)) == 1
    b.greske["predmet_hronologija"] = Exception('{"code": "57014", "message": "statement timeout"}')
    _osvezi_akcije(pid)
    dispecuj()
    del b.greske["predmet_hronologija"]
    assert [(a["id"], a["status"]) for a in b.tabele["case_actions"]] == pre      # akcija NIJE zatvorena


def test_neprocitan_lanac_odluka_ne_otvara_ponovo_potvrdjen_rok(solo, audit_lanac):
    """Rok je potvrđen (akcija zatvorena). Kad lanac odluka postane nečitljiv, odsustvo odluke se NE sme pročitati kao
    „nepotvrđeno“ (to bi lažno ponovo otvorilo akciju) — `odluke(strogo=True)` diže izuzetak, akcije ostaju."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    rid = _ai_rok(b, pid)
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    assert k.post(f"/api/rokovi/{rid}/potvrdi", json={}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    assert _rok_akcije(b, pid) == []
    pre = [(a["id"], a["status"]) for a in b.tabele["case_actions"]]
    b.greske["audit_immutable"] = Exception('{"code": "57014", "message": "statement timeout"}')
    _osvezi_akcije(pid)
    dispecuj()
    del b.greske["audit_immutable"]
    assert [(a["id"], a["status"]) for a in b.tabele["case_actions"]] == pre
    assert _rok_akcije(b, pid) == []


def test_bez_migracije_129_pravilo_se_preskace(solo, monkeypatch):
    from shared import rokovi
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _ai_rok(b, pid)
    monkeypatch.setattr(rokovi, "_sema_ima_129", lambda supa: False)
    _osvezi_akcije(pid)
    _do_kraja_dogadjaja(b)
    assert _rok_akcije(b, pid) == []
