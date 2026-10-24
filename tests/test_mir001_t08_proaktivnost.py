# -*- coding: utf-8 -*-
"""MIR001 TASK-08 (MIR-05) — ograničena proaktivnost: posle materijalne promene (DOK-08 kroz STVARAN prijem) Vindex,
BEZ zasebnog zahteva advokata, u ciklusu autonomije (NS007 `run_autonomy_cycle`) priprema interni pregled promene
(`CASE_CHANGE_BRIEF`) za ljudski pregled.

Stvarno: prijem, trajni događaji, Genome verzije i istorija, Case Actions, planer i izvršilac `case_change_brief`, ceo
ciklus (zauzimanje, zakup, upis rezultata, revizija), API radnog proizvoda. Baza: NS006/NS007 lažna baza (RPC
`autonomy_claim_work_item` po pravilima migracije 136; atomičnost pod konkurencijom dokazuju PG testovi NS007).
Zamenjen je samo Genome model (TASK-07). Izvršilac NE poziva model.
"""
import asyncio

import pytest

import tests.ns007_fake as f7
from tests import mir001_golden_case as gc
from tests.test_mir001_t07_dogadjaj_posledica import ROK, _dodaj, spis, treba_ocr  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


@pytest.fixture
def auto(spis, monkeypatch):
    k, b, pid, doks = spis
    b.rpc_impl["autonomy_claim_work_item"] = f7._zauzmi
    for t in ("autonomy_cycles", "autonomy_work_items", "usage_events"):
        b.tabele.setdefault(t, [])
    import services.agent_tasks.precedents_radar as pr

    async def _bez_prakse(supa):                                       # van opsega: nijedna nova odluka
        return {"kandidati": [], "ponisteni": [], "preskoceno": {}}
    monkeypatch.setattr(pr, "planiraj", _bez_prakse)
    return k, b, pid, doks


def _ciklus(b, run):
    from workers.background_agents import run_autonomy_cycle
    return asyncio.run(run_autonomy_cycle(run))


def _pregledi(b, pid, status=None):
    return [w for w in b.tabele["autonomy_work_items"] if w["predmet_id"] == pid and w["work_type"] == "CASE_CHANGE_BRIEF"
            and (status is None or w["status"] == status)]


def _verzija(b, pid):
    return next(p for p in b.tabele["predmeti"] if p["id"] == pid)["case_dna"]["verzija"]


@treba_ocr
def test_promena_bez_zahteva_priprema_pregled_sa_izvorom_i_razlogom(auto):
    k, b, pid, doks = auto
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    v = _verzija(b, pid)
    n_genome = len(b.genome_pozivi)
    rez = _ciklus(b, "mir001-c1")
    assert rez["spremno"] >= 1 and rez["neuspeh"] == 0, rez
    [w] = _pregledi(b, pid)
    assert w["status"] == "READY_FOR_REVIEW" and w["user_id"] == "uid-A" and w["source_version"] == v
    assert w["trigger_type"] == "GENOME_VERSION" and w["cost_class"] == "FREE" and w["quality_state"] == "DETERMINISTIC"
    assert "primljen dokument" in w["reason"] and f"v{v}" in w["reason"] and "samo ako" in w["reason"]
    c = w["content_json"]
    assert c["schema"] == "cb-1" and c["verzija"] == v and c["prethodna_verzija"] == v - 1
    # promena iz DOK-08: nov rok u analizi (sa poreklom), i ništa nije izmišljeno van NS006 diff-a
    assert any(ROK in str(p.get("novo")) or ROK in str(p.get("opis")) for p in c["promene"]), c["promene"]
    assert {"vrsta": "genome_verzija", "predmet_id": pid, "verzija": v} in w["source_refs"]
    # radnje: SAMO nove iz ove promene (rok iz DOK-08), ne i ranije otvorene protivrečnosti koje je događaj osvežio
    assert [x["tip"] for x in c["radnje"]] == ["PLANIRATI_ROKOVE"] and ROK in c["radnje"][0]["razlog"]
    assert len(b.genome_pozivi) == n_genome                            # izvršilac ne poziva model
    assert not [u for u in b.tabele["usage_events"] if u.get("feature") == "autonomy"]   # FREE: bez naplate
    assert not [x for x in b.tabele.get("staging_memory", []) if x.get("predmet_id") == pid]   # ništa se ne šalje/ne piše
    # API radnog proizvoda: vlasnik vidi, korisnik B ne
    r = k.get(f"/api/autonomy/work-items/{w['id']}", headers=A)
    assert r.status_code == 200 and r.json()["content_json"]["schema"] == "cb-1", r.text
    assert k.get(f"/api/autonomy/work-items/{w['id']}", headers=B).status_code == 404


@treba_ocr
def test_ponovljen_ciklus_bez_duplikata_nova_verzija_zastareva_staru(auto):
    k, b, pid, doks = auto
    _dodaj(k, b, pid, gc.KASNIJI)
    _ciklus(b, "mir001-c1")
    [prvi] = _pregledi(b, pid)
    _ciklus(b, "mir001-c2")                                            # isti okidač, ista verzija
    assert [w["id"] for w in _pregledi(b, pid)] == [prvi["id"]]
    neutralan = {"oznaka": "DOK-N", "ime": "09 Punomocje.pdf", "skeniran": False,
                 "redovi": [gc.SUD, f"Broj predmeta: {gc.BROJ}", "PUNOMOCJE (SINTETICKI PREDMET)",
                            "Tuzilac ovlascuje advokata da ga zastupa u ovom postupku."]}
    _dodaj(k, b, pid, neutralan)                                       # nova verzija analize
    _ciklus(b, "mir001-c3")
    stari = next(w for w in b.tabele["autonomy_work_items"] if w["id"] == prvi["id"])
    # pregled v7→v8 poredi dve fiksne verzije: nova verzija ga ne poništava (materijalni pregled ne nestaje)
    assert stari["status"] == "READY_FOR_REVIEW"
    novi = [w for w in _pregledi(b, pid) if w["id"] != prvi["id"]]
    assert len(novi) == 1 and novi[0]["source_version"] == _verzija(b, pid)
    # punomoćje menja samo brojače analize → nema materijalne promene → pošten neuspeh, bez proizvoda za pregled
    assert novi[0]["status"] == "FAILED" and novi[0]["safe_error_code"] == "NO_MATERIAL_CHANGE"
    assert novi[0]["content_json"] is None


@treba_ocr
def test_prihvatanje_i_odbijanje_samo_vlasnik_bez_spoljnog_efekta(auto):
    k, b, pid, doks = auto
    _dodaj(k, b, pid, gc.KASNIJI)
    _ciklus(b, "mir001-c1")
    [w] = _pregledi(b, pid)
    assert k.post(f"/api/autonomy/work-items/{w['id']}/accept", json={}, headers=B).status_code == 404
    pre = {t: len(v) for t, v in b.tabele.items() if t not in ("autonomy_work_items", "audit_immutable", "events")}
    r = k.post(f"/api/autonomy/work-items/{w['id']}/accept", json={}, headers=A)
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED", r.text
    posle = {t: len(v) for t, v in b.tabele.items() if t not in ("autonomy_work_items", "audit_immutable", "events")}
    assert posle == pre                                                # prihvatanje ne menja predmet niti išta šalje
    assert any("AUTONOMY" in str(a.get("action", "")).upper() for a in b.tabele["audit_immutable"])


@treba_ocr
def test_terminalan_predmet_ponistava_pregled_i_ne_dobija_nov(auto):
    k, b, pid, doks = auto
    _dodaj(k, b, pid, gc.KASNIJI)
    from workers.background_agents import _work_agents
    import services.agent_tasks.case_change_brief as ccb
    plan = asyncio.run(ccb.planiraj(b))
    assert [x["predmet_id"] for x in plan["kandidati"]] == [pid]
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    next(p for p in b.tabele["predmeti"] if p["id"] == pid)["status"] = sorted(TERMINALNI_STATUSI_PREDMETA)[0]
    plan = asyncio.run(ccb.planiraj(b))
    assert plan["kandidati"] == [] and plan["preskoceno"].get("PREDMET_ZAVRSEN") == 1
    assert "CASE_CHANGE_BRIEF" in _work_agents()                     # registrovan u JEDINOM registru agenata


@treba_ocr
def test_bez_novog_dokumenta_nema_posla(auto):
    k, b, pid, doks = auto
    import services.agent_tasks.case_change_brief as ccb
    for e in b.tabele["events"]:                                       # događaji prijema stariji od prozora
        if e.get("event_type") in ("DocumentAccepted", "DocumentBatchCompleted"):
            e["created_at"] = "2020-01-01T00:00:00+00:00"
    assert asyncio.run(ccb.planiraj(b))["kandidati"] == []


@treba_ocr
def test_izvrsenje_za_tudji_predmet_nema_proizvoda(auto):
    k, b, pid, doks = auto
    _dodaj(k, b, pid, gc.KASNIJI)
    import services.agent_tasks.case_change_brief as ccb
    from services import autonomy as au
    item = {"id": "w-x", "user_id": "uid-B", "predmet_id": pid, "source_version": _verzija(b, pid), "lease_owner": "o"}
    with pytest.raises(au.NeuspehPosla) as e:
        asyncio.run(ccb.izvrsi(b, item))
    assert str(e.value.kod if hasattr(e.value, "kod") else e.value) == "MATTER_NOT_ACCESSIBLE"


@treba_ocr
def test_osvezavanje_bez_novog_dokumenta_ne_tvrdi_nov_dokument(auto):
    """GATE-08 P1: ručno osvežavanje u prozoru događaja prijema → verzija nije nastala iz dokumenta → nema pregleda."""
    k, b, pid, doks = auto
    _dodaj(k, b, pid, gc.KASNIJI)
    _ciklus(b, "mir001-c1")
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202)
    from tests.test_osb002_solo_tok import _do_kraja_dogadjaja
    _do_kraja_dogadjaja(b, najvise=20)
    v = _verzija(b, pid)
    _ciklus(b, "mir001-c2")
    [w] = [x for x in _pregledi(b, pid) if x["source_version"] == v]
    assert w["status"] == "FAILED" and w["safe_error_code"] == "CHANGE_NOT_FROM_DOCUMENT" and w["content_json"] is None
