# -*- coding: utf-8 -*-
"""OSB003 Task 3 — dokument → trajni događaj → Case Evolution → tvrdnje → Genome → Case Actions → V2 projekcija,
kroz STVARNE rute i STVARAN dispečer (tests/test_osb002_solo_tok.py harness), sa ubacivanjem kvarova.

Invarijanta: izvor koji NIJE PROČITAN nikad ne sme da postane dokaz da ništa ne postoji (akcije se ne zatvaraju).
"""
import asyncio
from datetime import date, timedelta

from tests.ns006_fake import dispecuj
from tests.test_osb002_solo_tok import (  # noqa: F401 — `solo` je pytest fixture
    A, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _pdf, _prijem_dokumenta, _radnik, solo,
)


def _otvorene(b, pid):
    return sorted((a["tip"], a["dedupe_key"]) for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a.get("status") == "open")


def _posledice(b, ime):
    return [c for c in b.tabele["case_evolution_consequences"] if c["consequence_name"] == ime]


def _sa_rocistem(k, b):
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    _do_kraja_dogadjaja(b)
    r = k.post("/api/rocista", json={"predmet_id": pid, "sud": "Osnovni sud u Beogradu",
                                     "datum": (date.today() + timedelta(days=9)).isoformat(), "vreme": "09:30"}, headers=A)
    assert r.status_code == 200, r.text
    _do_kraja_dogadjaja(b)
    return pid


def test_ceo_lanac_svaka_posledica_zavrsena_i_vidljiva_u_v2(solo):
    k, b = solo
    pid = _sa_rocistem(k, b)
    assert all(e.get("dispatched_at") for e in b.tabele["events"])
    for ime in ("evidence_classification", "genome_refresh", "timeline_entry", "refresh_case_actions"):
        c = _posledice(b, ime)
        assert c and all(x["status"] == "completed" for x in c), (ime, [(x["status"], x.get("result_ref")) for x in c])
    otv = _otvorene(b, pid)
    assert ("PRIPREMITI_PODNESAK",) in {(t,) for t, _ in otv}, otv
    akc = k.get(f"/api/case-actions/predmeti/{pid}", headers=A).json()
    assert {a["tip"] for a in akc["akcije"]} >= {"PRIPREMITI_PODNESAK"}
    ziv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    dok_ids = {d["id"] for d in b.tabele["predmet_dokumenti"]}
    assert ziv["dokazi"]["tvrdnje"] and all(t["dokument_id"] in dok_ids for t in ziv["dokazi"]["tvrdnje"])
    assert pid in k.get("/api/workspace", headers=A).text


def test_nepročitan_izvor_ne_zatvara_postojece_akcije(solo):
    k, b = solo
    pid = _sa_rocistem(k, b)
    pre = _otvorene(b, pid)
    assert pre
    for tabela in ("rocista", "predmet_dokazi", "predmet_dokumenti"):
        b.greske[tabela] = Exception('{"code": "57014", "message": "statement timeout"}')
        from services.event_bus import EventType, emit_durable
        dok = b.tabele["predmet_dokumenti"][0]
        b.greske.pop(tabela)                             # emit sme da prođe; kvar važi tokom obrade
        asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", pid, {"dokument_id": dok["id"], "naziv": "x", "trigger": "t"}))
        b.greske[tabela] = Exception('{"code": "57014", "message": "statement timeout"}')
        dispecuj()
        b.greske.pop(tabela)
        greske = [e.get("last_error") or "" for e in b.tabele["events"] if not e.get("dispatched_at")]
        assert any("nije pročitan" in g or "57014" in g for g in greske), greske   # usklađivanje JESTE pokušano i odbijeno
        assert _otvorene(b, pid) == pre, f"akcije su promenjene iako izvor '{tabela}' nije pročitan"
        assert not any(a["status"] != "open" for a in b.tabele["case_actions"] if a["predmet_id"] == pid)
        _do_kraja_dogadjaja(b)                           # posle oporavka sve se završava
        assert _otvorene(b, pid) == pre


def test_ponovna_isporuka_dogadjaja_ne_duplira_nista(solo):
    k, b = solo
    pid = _sa_rocistem(k, b)
    stanje = lambda: (len(b.tabele["predmet_dokazi"]), _otvorene(b, pid), len(b.tabele["predmet_hronologija"]),
                      b.tabele["predmeti"][-1]["case_dna"].get("verzija") if b.tabele["predmeti"] else None)
    pre = stanje()
    for e in b.tabele["events"]:                         # replay SVIH događaja (isti event_id)
        e["dispatched_at"] = None
        e["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    assert stanje() == pre, (pre, stanje())


def test_pad_genome_pa_oporavak_zadrzava_identitet_dogadjaja(solo, monkeypatch):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    import routers.case_dna as cd
    pravi = cd._pozovi_genome_api

    async def _pad(*a, **kw):
        raise RuntimeError("model nedostupan")
    monkeypatch.setattr(cd, "_pozovi_genome_api", _pad)
    _prijem_dokumenta(k, b, pid)
    dispecuj()
    ev = next(e for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted")
    assert not ev.get("dispatched_at") and ev.get("last_error")
    monkeypatch.setattr(cd, "_pozovi_genome_api", pravi)
    ev["claimed_at"] = None
    _do_kraja_dogadjaja(b)
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert red["case_dna"]["verzija"] == 1
    assert len([e for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted"]) == 1   # isti događaj, ne nov
    assert len([h for h in b.tabele["predmet_genome_history"] if h.get("predmet_id") == pid]) <= 1


def test_beta_def_004_pad_upisa_dogadjaja_posle_dokumenta(solo):
    """BETA-DEF-004 — ISPRAVLJENO u FRG001 (puna matrica: tests/test_frg001_dogadjaj_dokumenta.py). Upis događaja
    padne odmah posle upisa dokumenta: finalizacija više ne vraća 200 i posao ne postaje „prikačen“; ponovni
    pokušaj dovršava isti dokument (bez duplikata) i tvrdnje nastaju."""
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid = _otpremi(k, _pdf()).json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    if b.tabele["intake_jobs"][0]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    pre = len(b.tabele["events"])
    b.greske["events"] = Exception('{"code": "08006", "message": "connection failure"}')
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    del b.greske["events"]
    assert f.status_code == 503 and len(b.tabele["predmet_dokumenti"]) == 1
    assert len(b.tabele["events"]) == pre and not b.tabele["intake_jobs"][0]["assimilation_complete"]
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    assert b.tabele["predmet_dokazi"] and len(b.tabele["predmet_dokumenti"]) == 1
