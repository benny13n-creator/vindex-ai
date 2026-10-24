# -*- coding: utf-8 -*-
"""MIR001 TASK-07 (MIR-01, MIR-05) — događaj → posledica → sledeća radnja nad Golden Case spisom, kroz POSTOJEĆI
Case Evolution (`services/case_evolution.py`, Rule 6: rok iz dokumenta čeka odluku advokata) i `case_actions`.

Stvarno: prijem DOK-08 (rute, worker), trajni događaji i dispečer, Genome osvežavanje, sinhronizacija rokova u
hronologiju, rekoncilijacija `case_actions`, brisanje izvora, V2 čitanje radnji. Zamenjen je samo Genome model
(TASK-03): rok iz DOK-08 navodi SAMO ako je tekst DOK-08 stvarno u promptu, sa oznakom tog dokumenta.
"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t02_prijem_spisa import _OCR, _obradi_sve, _otpremi_sve, _prikaci, primi_spis
from tests.test_mir001_t03_kontinuitet import _genome_model, _klasifikuj, _sekcije
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — DOK-05 (sken) se ne može pročitati")
ROK = gc.KASNIJA_PROMENA["rok"]


def _genome_sa_rokom(pozivi):
    unutra = _genome_model(pozivi)

    async def _pozovi(client, combined, n):
        g = json.loads(await unutra(client, combined, n))
        sek = _sekcije(combined)
        ime = gc.KASNIJI["ime"]
        if ime in sek and "rok od 8 dana od dana dopune" in sek[ime][1]:
            g["rokovi_kriticni"] = [{"naziv": "Rok za izjasnjenje na dopunu nalaza vestaka", "datum": ROK, "status": "aktivan",
                                     "opis": "8 dana od dana dopune nalaza (20.10.2026)", "lokacija": sek[ime][0]}]
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def spis(solo, monkeypatch):
    k, b = solo
    import routers.case_dna as cd
    import routers.evidence as ev
    import shared.audit_immutable as audit
    from api import _get_supa
    from shared import rokovi
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_sa_rokom(b.genome_pozivi))
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)

    async def _log(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        r = _get_supa().table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                                       "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(audit, "log_action", _log)
    rokovi._resetuj_sondu()
    pid, doks, _ = primi_spis(k, b)
    yield k, b, pid, {oz: d["id"] for oz, d in doks.items()}
    rokovi._resetuj_sondu()


def _dodaj(k, b, pid, dok):
    [x] = _otpremi_sve(k, [dok])
    assert x["ok"], x
    _obradi_sve()
    f = _prikaci(k, x["job_id"], pid)
    assert f.status_code == 200 and f.json()["dokumenata_povezano"] == 1, f.text
    _do_kraja_dogadjaja(b, najvise=40)
    return next(d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid and d["naziv_fajla"] == dok["ime"])


def _otvorene(b, pid):
    return [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == "open"]


def _rok_akcije(b, pid, status="open"):
    return [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == status
            and (a.get("dokaz") or {}).get("izvor") == "predmet_hronologija"]


@treba_ocr
def test_nova_cinjenica_otvara_radnju_sa_izvorom_i_razlogom_bez_duplikata(spis):
    k, b, pid, doks = spis
    pre = {a["dedupe_key"] for a in _otvorene(b, pid)}
    assert _rok_akcije(b, pid) == []                                  # spis bez DOK-08 nema rok koji čeka odluku
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    # posledica: rok iz DOK-08 u hronologiji (sa izvorom) i JEDNA radnja koja čeka potvrdu advokata
    [rok] = [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta") == "rok"
             and h.get("akter") == "Genome (AI)"]
    assert rok["datum_iso"] == ROK and rok["dokument_id"] == d8
    akc = [a for a in _rok_akcije(b, pid) if a["dokaz"].get("hronologija_id") == rok["id"]]
    assert len(akc) == 1 and akc[0]["tip"] == "PLANIRATI_ROKOVE", akc
    a = akc[0]
    assert a["dokaz"]["dokument_id"] == d8 and a["dokaz"]["stanje_odluke"] == "UNCONFIRMED"
    assert "čeka vašu potvrdu" in a["razlog"]
    assert a.get("correlation_id")                                     # događaj koji ju je proizveo je zabeležen
    # V2 (kartica Rad / Danas) dobija razlog i izvor iz iste rute
    v2 = k.get(f"/api/case-actions/predmeti/{pid}", headers=A)
    assert v2.status_code == 200, v2.text
    tekst_v2 = json.dumps(v2.json(), ensure_ascii=False)
    assert a["id"] in tekst_v2 and "čeka vašu potvrdu" in tekst_v2
    # isti događaj ponovo (ponovljena isporuka + ponovno osvežavanje) → bez nove otvorene radnje
    from services.event_bus import EventType, emit_durable
    broj = len(b.tabele["case_actions"])
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, "uid-A", pid, {"dokument_id": d8, "trigger": "mir001-ponovo"}))
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, "uid-A", pid, {"dokument_id": d8, "trigger": "mir001-ponovo"}))
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202, 409)
    _do_kraja_dogadjaja(b, najvise=40)
    assert len(b.tabele["case_actions"]) == broj
    assert [x["id"] for x in _rok_akcije(b, pid) if x["dokaz"].get("hronologija_id") == rok["id"]] == [a["id"]]
    # korisnik B ne vidi radnje predmeta A
    rb = k.get(f"/api/case-actions/predmeti/{pid}", headers=B)
    assert rb.status_code in (403, 404) or a["id"] not in rb.text


@treba_ocr
def test_povucen_izvor_ne_ostavlja_posledicu_tiho_aktivnom(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    [a] = [x for x in _rok_akcije(b, pid) if x["dokaz"].get("dokument_id") == d8]
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *x, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{d8}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=40)
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202, 409)
    _do_kraja_dogadjaja(b, najvise=40)
    sada = next(x for x in b.tabele["case_actions"] if x["id"] == a["id"])
    # radnja koja se oslanja na povučen izvor ne ostaje otvorena („čeka vašu potvrdu“ za rok iz nepostojećeg dokumenta)
    assert sada["status"] != "open", sada
    assert [x for x in _rok_akcije(b, pid) if (x.get("dokaz") or {}).get("hronologija_id") == a["dokaz"]["hronologija_id"]] == []
    # rok ostaje u hronologiji kao istorija, bez izvora i NEpotvrđen (nikad operativan)
    [rok] = [h for h in b.tabele["predmet_hronologija"] if h["id"] == a["dokaz"]["hronologija_id"]]
    assert rok["dokument_id"] is None and rok["dokument_naziv"] == gc.KASNIJI["ime"]
    # ostale posledice spisa (koje ne zavise od DOK-08) ostaju otvorene
    assert any(x["tip"] == "RAZRESITI_KONTRADIKCIJU" for x in b.tabele["case_actions"] if x["predmet_id"] == pid and x["status"] == "open")


@treba_ocr
def test_terminalan_predmet_ne_dobija_nove_otvorene_radnje(spis):
    k, b, pid, doks = spis
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    red["status"] = sorted(TERMINALNI_STATUSI_PREDMETA)[0]
    _dodaj(k, b, pid, gc.KASNIJI)
    assert _otvorene(b, pid) == []


@treba_ocr
def test_dokument_bez_materijalne_promene_ne_izmislja_radnju(spis):
    """No-consequence (TASK9 Phase 2 §3): obrađen događaj, nema materijalne promene → nema opravdane nove radnje."""
    k, b, pid, doks = spis
    pre = sorted(a["dedupe_key"] for a in _otvorene(b, pid))
    neutralan = {"oznaka": "DOK-N", "ime": "09 Punomocje.pdf", "skeniran": False,
                 "redovi": [gc.SUD, f"Broj predmeta: {gc.BROJ}", "PUNOMOCJE (SINTETICKI PREDMET)",
                            "Tuzilac ovlascuje advokata da ga zastupa u ovom postupku."]}
    _dodaj(k, b, pid, neutralan)
    assert sorted(a["dedupe_key"] for a in _otvorene(b, pid)) == pre


@treba_ocr
def test_granice_pravila_povucenog_izvora(spis):
    """Skida se SAMO Genome rok sa nazivom izvora, bez `dokument_id`, i bez dokumenta tog naziva u predmetu."""
    k, b, pid, doks = spis
    from datetime import date, timedelta
    from services.event_bus import EventType, emit_durable
    from shared import rokovi
    datum = (date.today() + timedelta(days=20)).isoformat()
    postojeci = gc.DOKUMENTI[6]["ime"]
    osnova = {"predmet_id": pid, "user_id": "uid-A", "datum": datum, "datum_iso": datum, "vrsta": rokovi.VRSTA_ROK,
              "izvor": rokovi.IZVOR_AI_AUTONOMOUS, "dokument_id": None}
    b.tabele["predmet_hronologija"] += [
        {**osnova, "id": "rok-si", "akter": "Smart Intake", "dogadjaj": "Rok SI", "dokument_naziv": "nema_ga.pdf"},
        {**osnova, "id": "rok-g-star", "akter": "Genome (AI)", "dogadjaj": "Rok stari", "dokument_naziv": postojeci},
        {**osnova, "id": "rok-g-obrisan", "akter": "Genome (AI)", "dogadjaj": "Rok obrisan", "dokument_naziv": "obrisan.pdf"},
    ]
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "mir001"}))
    _do_kraja_dogadjaja(b, najvise=20)
    otvoreni = {a["dokaz"].get("hronologija_id") for a in _rok_akcije(b, pid)}
    assert {"rok-si", "rok-g-star"} <= otvoreni and "rok-g-obrisan" not in otvoreni, otvoreni


def _obrisi(k, b, pid, did):
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *x, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{did}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=40)


@treba_ocr
def test_brisanje_izvora_zatvara_radnje_protivrecnosti_bez_rucnog_osvezavanja(spis):
    """Klasa (GATE-07): posledica koja se oslanja na povučen izvor zatvara se u ISTOM usklađivanju posle brisanja."""
    k, b, pid, doks = spis
    kon = [a for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert len(kon) == 2                                               # K-01 i K-02 (obe imaju stranu u DOK-02)
    n_genome = len(b.genome_pozivi)
    _obrisi(k, b, pid, doks["DOK-02"])
    assert len(b.genome_pozivi) == n_genome                            # bez osvežavanja Genome-a
    assert [a for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"] == []


@treba_ocr
def test_brisanje_nepovezanog_dokumenta_ne_zatvara_protivrecnosti(spis):
    k, b, pid, doks = spis
    pre = sorted(a["id"] for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU")
    assert len(pre) == 2
    _obrisi(k, b, pid, doks["DOK-04"])
    assert sorted(a["id"] for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU") == pre


@treba_ocr
def test_kandidati_oznacavaju_rok_ciji_je_izvor_povucen(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    def _kand():
        r = k.get("/api/rokovi/kandidati", params={"predmet_id": pid, "dana": 60}, headers=A)
        assert r.status_code == 200, r.text
        return [x for x in r.json()["rokovi"] if x.get("datum_iso") == ROK and x.get("akter") == "Genome (AI)"]
    [pre] = _kand()
    assert pre["izvor_povucen"] is False
    _obrisi(k, b, pid, d8)
    [posle] = _kand()
    assert posle["izvor_povucen"] is True and posle["stanje_odluke"] == "UNCONFIRMED"


@treba_ocr
def test_povlacenje_pojedinacnih_tvrdnji_zatvara_bez_vaskrsavanja(spis):
    """GATE-07 (2. prolaz): advokat povuče tvrdnje DOK-02 iz obe sporne tačke, dokument ostaje. Sporne tačke se
    zatvaraju i NE vraćaju se iz sačuvanog Genome-a pod drugim (legacy) ključem."""
    k, b, pid, doks = spis
    pre = {a["id"] for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"}
    assert len(pre) == 2
    ids_u_spornim = {c["dokaz_id"] for c in b.tabele["predmet_contradiction_claims"]}
    dok2 = [t for t in b.tabele["predmet_dokazi"] if t["dokument_id"] == doks["DOK-02"] and t["id"] in ids_u_spornim]
    assert len(dok2) == 2
    for t in dok2:                                                     # isto što atomski RPC 133 radi za jednu tvrdnju
        t["deleted_at"] = "2099-01-01T00:00:00+00:00"
    from services.event_bus import EventType, emit_durable
    for t in dok2:
        asyncio.run(emit_durable(EventType.SOURCE_INVALIDATED, "uid-A", pid, {"source_type": "dokaz", "source_id": t["id"]}))
    _do_kraja_dogadjaja(b, najvise=40)
    assert [a for a in _otvorene(b, pid) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"] == []
    assert any(d["id"] == doks["DOK-02"] for d in b.tabele["predmet_dokumenti"])     # dokument je i dalje u predmetu
