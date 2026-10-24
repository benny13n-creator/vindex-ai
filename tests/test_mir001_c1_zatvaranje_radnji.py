# -*- coding: utf-8 -*-
"""MIR001 FINAL CLOSURE — TASK-C1: proverljivo zatvaranje radnji pri povlačenju izvora.

Nad Golden Case spisom, kroz STVARNE rute brisanja, atomski RPC događaj `SourceInvalidated`, dispečer i usklađivanje
`case_actions` (`services/case_evolution.py`). Zamenjeni su samo modeli (TASK-03/07) i Pinecone.

Pravila: (1) nijedna promena statusa bez razloga — razlog i izvor su na redu (`dokaz.zatvaranje`, isti UPDATE) i u
nepromenljivom auditu (`closed_actions[].zatvaranje` + `prethodno`); (2) povlačenje izvora zatvara SAMO radnju čija je
veza sa tim izvorom dokaziva iz polja koje je radnja sama nosila; (3) bez dokazive veze status se ne menja, a audit to
beleži (`zadrzane_actions`); (4) ponavljanje istog događaja ništa ne menja; (5) korisnik B ne menja radnje korisnika A.
"""
import asyncio
import copy

from tests import mir001_golden_case as gc
from tests.test_mir001_t07_dogadjaj_posledica import (ROK, _dodaj, _obrisi, _otvorene, _rok_akcije, spis,  # noqa: F401
                                                     treba_ocr)
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401


def _audit(b, od=0):
    return [r for r in b.tabele["audit_immutable"][od:] if r.get("action") == "case_action_refreshed"]


def _zatvorene_u_auditu(b, od=0):
    return {c["id"]: c for r in _audit(b, od) for c in (r.get("metadata") or {}).get("closed_actions", [])}


def _zadrzane_u_auditu(b, od=0):
    return {c["id"]: c for r in _audit(b, od) for c in (r.get("metadata") or {}).get("zadrzane_actions", [])}


def _red(b, aid):
    return next(x for x in b.tabele["case_actions"] if x["id"] == aid)


def _dogadjaj_povlacenja(b, source_id):
    [e] = [e for e in b.tabele["events"] if e.get("event_type") == "SourceInvalidated"
           and (e.get("payload") or {}).get("source_id") == source_id]
    return e


@treba_ocr
def test_brisanje_relevantnog_dokumenta_zatvara_sa_razlogom_izvorom_i_prethodnim_stanjem(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    [a] = [x for x in _rok_akcije(b, pid) if x["dokaz"].get("dokument_id") == d8]
    pre = copy.deepcopy(a)
    n = len(b.tabele["audit_immutable"])
    _obrisi(k, b, pid, d8)
    ev = _dogadjaj_povlacenja(b, d8)
    sada = _red(b, a["id"])
    assert sada["status"] == "closed" and sada["closed_at"]
    # na redu: razlog, izvor i događaj — razlog otvaranja i ostatak dokaza netaknuti
    z = sada["dokaz"]["zatvaranje"]
    assert z["razlog"] == "IZVOR_POVUCEN" and z["source_type"] == "dokument" and z["source_id"] == d8
    assert z["veza"] == "dokument_id" and z["event_type"] == "SourceInvalidated" and z["event_id"] == ev["id"]
    assert sada["razlog"] == pre["razlog"]
    assert {k2: v for k2, v in sada["dokaz"].items() if k2 != "zatvaranje"} == pre["dokaz"]
    # u nepromenljivom auditu: isti razlog + prethodno stanje
    c = _zatvorene_u_auditu(b, n)[a["id"]]
    assert c["zatvaranje"] == z and c["dedupe_key"] == pre["dedupe_key"]
    assert c["prethodno"]["status"] == "open" and c["prethodno"]["razlog"] == pre["razlog"]
    assert c["prethodno"]["dokaz"] == pre["dokaz"] and c["prethodno"]["tip"] == pre["tip"]
    # nijedna druga radnja nije zatvorena tim brisanjem
    assert set(_zatvorene_u_auditu(b, n)) == {a["id"]}


@treba_ocr
def test_brisanje_nepovezanog_dokumenta_ne_zatvara_nista(spis):
    k, b, pid, doks = spis
    _dodaj(k, b, pid, gc.KASNIJI)
    pre = {a["id"]: a["status"] for a in b.tabele["case_actions"] if a["predmet_id"] == pid}
    n = len(b.tabele["audit_immutable"])
    _obrisi(k, b, pid, doks["DOK-04"])
    assert {a["id"]: a["status"] for a in b.tabele["case_actions"] if a["predmet_id"] == pid} == pre
    assert _audit(b, n) and _zatvorene_u_auditu(b, n) == {}


@treba_ocr
def test_brisanje_dokumenta_protivrecnosti_zatvara_obe_preko_dokazive_veze(spis):
    k, b, pid, doks = spis
    kon = [a for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert len(kon) == 2
    n = len(b.tabele["audit_immutable"])
    _obrisi(k, b, pid, doks["DOK-02"])
    zat = _zatvorene_u_auditu(b, n)
    for a in kon:
        z = _red(b, a["id"])["dokaz"]["zatvaranje"]
        assert _red(b, a["id"])["status"] == "closed" and z["razlog"] == "IZVOR_POVUCEN"
        assert z["source_id"] == doks["DOK-02"] and z["veza"] in ("dokument_ids", "dokument_id_1", "dokument_id_2")
        assert zat[a["id"]]["zatvaranje"] == z


@treba_ocr
def test_povlacenje_tvrdnje_zatvara_preko_claim_ids(spis):
    k, b, pid, doks = spis
    from services.event_bus import EventType, emit_durable
    ids_u_spornim = {c["dokaz_id"] for c in b.tabele["predmet_contradiction_claims"]}
    dok2 = [t for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == doks["DOK-02"] and t["id"] in ids_u_spornim]
    kon = {a["id"]: a for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"}
    n = len(b.tabele["audit_immutable"])
    for t in dok2:                                                     # isto što atomski RPC 133 radi za tvrdnju
        t["deleted_at"] = "2099-01-01T00:00:00+00:00"
    zatvorene = set()
    for t in dok2:                                                     # događaj po događaj
        m = len(b.tabele["audit_immutable"])
        asyncio.run(emit_durable(EventType.SOURCE_INVALIDATED, "uid-A", pid, {"source_type": "dokaz", "source_id": t["id"]}))
        _do_kraja_dogadjaja(b, najvise=40)
        # ovaj događaj zatvara TAČNO otvorene radnje čiji `claim_ids` sadrži ovu tvrdnju; ostale nestale su zadržane
        ocekivano = {aid for aid, a in kon.items() if t["id"] in a["dokaz"]["claim_ids"] and aid not in zatvorene}
        assert set(_zatvorene_u_auditu(b, m)) == ocekivano, (t["id"], ocekivano)
        assert not (set(_zadrzane_u_auditu(b, m)) & ocekivano)
        zatvorene |= ocekivano
    for aid, a in kon.items():
        z = _red(b, aid)["dokaz"]["zatvaranje"]
        assert _red(b, aid)["status"] == "closed" and z["veza"] == "claim_ids" and z["source_id"] in a["dokaz"]["claim_ids"]
    assert set(_zatvorene_u_auditu(b, n)) == set(kon)


@treba_ocr
def test_nedokaziva_veza_ne_menja_status_i_belezi_se(spis):
    """Genome rok imenuje dokument samo NAZIVOM (bez `dokument_id`): posle brisanja tog dokumenta pravilo povučenog
    izvora ga skida iz ciljnog skupa, ali veza radnje sa obrisanim dokumentom NIJE dokaziva → status ostaje `open`."""
    k, b, pid, doks = spis
    from datetime import date, timedelta
    from services.event_bus import EventType, emit_durable
    from shared import rokovi
    datum = (date.today() + timedelta(days=20)).isoformat()
    ime = gc.po_oznaci("DOK-04")["ime"]
    b.tabele["predmet_hronologija"].append(
        {"id": "rok-po-nazivu", "predmet_id": pid, "user_id": "uid-A", "datum": datum, "datum_iso": datum,
         "vrsta": rokovi.VRSTA_ROK, "izvor": rokovi.IZVOR_AI_AUTONOMOUS, "dokument_id": None,
         "akter": rokovi.AKTER_GENOME, "dogadjaj": "Rok po nazivu", "dokument_naziv": ime})
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "mir001-c1"}))
    _do_kraja_dogadjaja(b, najvise=20)
    [a] = [x for x in _rok_akcije(b, pid) if x["dokaz"].get("hronologija_id") == "rok-po-nazivu"]
    assert a["dokaz"].get("dokument_id") is None
    a = copy.deepcopy(a)                                               # snimak PRE brisanja (red u bazi se menja)
    n = len(b.tabele["audit_immutable"])
    _obrisi(k, b, pid, doks["DOK-04"])
    sada = _red(b, a["id"])
    ev = _dogadjaj_povlacenja(b, doks["DOK-04"])
    assert sada["status"] == "open" and "zatvaranje" not in sada["dokaz"]
    # zadržavanje je zapisano NA REDU, sa izvorom i događajem
    zr = sada["dokaz"]["zadrzano"]
    assert zr["razlog"] == "VEZA_SA_POVUCENIM_IZVOROM_NIJE_DOKAZIVA" and zr["source_type"] == "dokument"
    assert zr["source_id"] == doks["DOK-04"] and zr["event_id"] == ev["id"]
    assert {k2: v for k2, v in sada["dokaz"].items() if k2 != "zadrzano"} == a["dokaz"]     # ostatak dokaza netaknut
    zad = _zadrzane_u_auditu(b, n)[a["id"]]
    assert zad["razlog"] == "VEZA_SA_POVUCENIM_IZVOROM_NIJE_DOKAZIVA" and zad["event_id"] == ev["id"]
    assert a["id"] not in _zatvorene_u_auditu(b, n)
    # ponovljena isporuka istog povlačenja ne prepisuje zadržavanje
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event
    snimak = copy.deepcopy(_red(b, a["id"]))
    asyncio.run(_consequence_refresh_case_actions(Event(type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=pid,
                                                        payload=ev["payload"], event_id=ev["id"])))
    assert _red(b, a["id"]) == snimak
    # sledeće usklađivanje DRUGIM događajem je zatvara — sa razlogom koji NAVODI ranije zadržavanje i obrisani izvor
    m = len(b.tabele["audit_immutable"])
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "mir001-c1-2"}))
    _do_kraja_dogadjaja(b, najvise=20)
    z = _red(b, a["id"])["dokaz"]["zatvaranje"]
    assert _red(b, a["id"])["status"] == "closed" and z["razlog"] == "CINJENICA_VISE_NE_VAZI"
    assert z["event_type"] == EventType.MANUAL_CORRECTION_APPLIED.value
    assert z["posle_zadrzavanja"] == zr
    assert _zatvorene_u_auditu(b, m)[a["id"]]["zatvaranje"] == z


@treba_ocr
def test_povlacenje_bez_izvora_u_dogadjaju_ne_zatvara_nista(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    [a] = [x for x in _rok_akcije(b, pid) if x["dokaz"].get("dokument_id") == d8]
    d = next(x for x in b.tabele["predmet_dokumenti"] if x["id"] == d8)
    b.tabele["predmet_dokumenti"].remove(d)                            # izvor nestao, ali događaj ga ne imenuje
    for h in b.tabele["predmet_hronologija"]:
        if h.get("dokument_id") == d8:
            h["dokument_id"] = None
    from services.event_bus import EventType, emit_durable
    n = len(b.tabele["audit_immutable"])
    asyncio.run(emit_durable(EventType.SOURCE_INVALIDATED, "uid-A", pid, {}))
    _do_kraja_dogadjaja(b, najvise=20)
    assert _red(b, a["id"])["status"] == "open"
    assert a["id"] in _zadrzane_u_auditu(b, n) and _zatvorene_u_auditu(b, n) == {}


@treba_ocr
def test_ponavljanje_istog_dogadjaja_je_idempotentno(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    _obrisi(k, b, pid, d8)
    ev = _dogadjaj_povlacenja(b, d8)
    snimak = copy.deepcopy([x for x in b.tabele["case_actions"] if x["predmet_id"] == pid])
    from services.case_evolution import _consequence_refresh_case_actions, handle_case_changed
    from services.event_bus import Event, EventType
    dog = Event(type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=pid, payload=ev["payload"], event_id=ev["id"])
    asyncio.run(handle_case_changed(dog))                              # ponovljena isporuka: dedupe posledica
    assert [x for x in b.tabele["case_actions"] if x["predmet_id"] == pid] == snimak
    # i direktno ponovno usklađivanje: ništa se ne zatvara ni otvara; zatvaranja ostaju ista (postojeća UPDATE grana
    # ponovo upisuje iste vrednosti iz ciljnog skupa i nov `updated_at`/`event_id` OTVORENIH radnji)
    assert asyncio.run(_consequence_refresh_case_actions(dog)) == f"created=0 updated={len([x for x in snimak if x['status'] == 'open'])} closed=0"
    polja = ("id", "status", "closed_at", "razlog", "dokaz", "dedupe_key")
    assert [{p: x.get(p) for p in polja} for x in b.tabele["case_actions"] if x["predmet_id"] == pid] == \
        [{p: x.get(p) for p in polja} for x in snimak]


@treba_ocr
def test_korisnik_b_ne_menja_radnje_korisnika_a(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    pre = copy.deepcopy([x for x in b.tabele["case_actions"] if x["predmet_id"] == pid])
    n_ev = len(b.tabele["events"])
    r = k.delete(f"/api/predmeti/{pid}/dokumenti/{d8}", headers=B)
    assert r.status_code in (403, 404), r.text
    _do_kraja_dogadjaja(b, najvise=20)
    assert [x for x in b.tabele["case_actions"] if x["predmet_id"] == pid] == pre
    assert not [e for e in b.tabele["events"][n_ev:] if e.get("event_type") == "SourceInvalidated"]
    assert k.get(f"/api/case-actions/predmeti/{pid}", headers=B).status_code in (403, 404)


def test_veza_sa_izvorom_samo_tacan_izvor_iz_polja_radnje():
    from services.case_evolution import veza_sa_izvorom as v
    rok = {"dokaz": {"izvor": "predmet_hronologija", "dokument_id": "d-8", "hronologija_id": "h-1"}}
    v2 = {"dokaz": {"claim_ids": ["c-1", "c-2"], "dokument_ids": ["d-2", "d-3"]}, "izvor_dokumenti": ["d-2", "d-3"]}
    legacy = {"dokaz": {"dokument_id_1": "d-2", "dokument_id_2": None}, "izvor_dokumenti": ["DOK-02 str. 1"]}
    roc = {"dokaz": {"rociste_id": "r-1"}}
    assert v(rok, "dokument", "d-8") == "dokument_id" and v(rok, "dokument", "d-4") is None
    assert v(v2, "dokument", "d-3") == "dokument_ids" and v(v2, "dokument", "d-9") is None
    assert v(v2, "dokaz", "c-2") == "claim_ids" and v(v2, "dokaz", "c-9") is None
    assert v(legacy, "dokument", "d-2") == "dokument_id_1" and v(legacy, "dokument", "None") is None
    assert v(roc, "rociste", "r-1") == "rociste_id" and v(roc, "rociste", "r-2") is None
    # vrsta izvora mora da se poklapa: oznaka ročišta nije dokument, i obrnuto
    assert v(roc, "dokument", "r-1") is None and v(rok, "rociste", "d-8") is None
    # nepoznata strana (`None`) nikad nije veza, ni u listi
    assert v({"dokaz": {"dokument_ids": [None, "d-2"]}, "izvor_dokumenti": [None]}, "dokument", "None") is None
    # bez izvora ili bez dokaza nema veze
    assert v(rok, "dokument", "") is None and v({}, "dokument", "d-8") is None and v({"dokaz": None}, "dokument", "d-8") is None


@treba_ocr
def test_zavrsen_predmet_zatvara_sa_razlogom(spis):
    k, b, pid, doks = spis
    from services.event_bus import EventType, emit_durable
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    otvorene = {a["id"] for a in _otvorene(b, pid)}
    assert otvorene
    next(p for p in b.tabele["predmeti"] if p["id"] == pid)["status"] = sorted(TERMINALNI_STATUSI_PREDMETA)[0]
    n = len(b.tabele["audit_immutable"])
    asyncio.run(emit_durable(EventType.MATTER_BECAME_TERMINAL, "uid-A", pid, {}))
    _do_kraja_dogadjaja(b, najvise=20)
    for aid in otvorene:
        z = _red(b, aid)["dokaz"]["zatvaranje"]
        assert _red(b, aid)["status"] == "closed" and z["razlog"] == "CINJENICA_VISE_NE_VAZI"
        assert z["event_type"] == EventType.MATTER_BECAME_TERMINAL.value
    assert set(_zatvorene_u_auditu(b, n)) == otvorene
