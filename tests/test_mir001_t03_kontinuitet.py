# -*- coding: utf-8 -*-
"""MIR001 TASK-03 (MIR-01) — kontinuitet spisa i integritet izvora nad celim Golden Case spisom (7 dokumenata).

Isti put kao TASK-02 (stvarne rute, stvaran worker, stvaran OCR, stvaran dispečer, stvarno Genome osvežavanje i
V2 projekcija). Zamenjeni su SAMO modeli, deterministički i nad STVARNIM ulazom koji server šalje modelu:
- klasifikacija dokumenta: tvrdnje = rečenice STVARNO izvučenog teksta (bez zaglavlja);
- Genome: čita STVARAN prompt — oznake `[DOK-NN: ime` i `CLAIM-NNN: tekst` — i vraća hronologiju i protivrečnosti
  koje se pozivaju SAMO na te oznake. Ako neki dokument ili tvrdnja nije stigla u prompt, model je ne može navesti
  i test pada: meri se da li server modelu daje ceo spis i da li njegove reference razrešava u stvarne izvore.

Šta ovaj test NE meri: da li stvaran model razume spis (to je TASK-04/05).
"""
import asyncio
import copy
import json
import re
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from tests import mir001_golden_case as gc
from tests import ns006_realni_predmet as rp
from tests.test_mir001_t02_prijem_spisa import _OCR, _dok_predmeta, primi_spis
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — DOK-05 (sken) se ne može pročitati")
_ZAGLAVLJA = ("PRIVREDNI SUD", "Broj predmeta", "SINTETICKI PREDMET")


def _dmy(iso):
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def _klasifikuj(naziv, tekst):
    """Zamena modela: ključni navodi (N-xx) STVARNO prisutni u izvučenom tekstu prvi, pa ostale rečenice. Proizvod
    zadržava najviše 20 po dokumentu (routers/evidence.py, MIR001 C2; ranije 5)."""
    recenice = [l.strip() for l in (tekst or "").splitlines()
                if l.strip() and not any(z in l for z in _ZAGLAVLJA) and not l.strip().isupper()]
    kljucne = [r for r in recenice if any(n["tekst"] in r for n in gc.NAVODI.values())]
    return {"tip_dokaza": "dopis", "pravni_elementi": [], "ai_tags": {},
            "kljucne_cinjenice": kljucne + [r for r in recenice if r not in kljucne]}


def _sekcije(prompt):
    """{ime fajla: (DOK oznaka, tekst sekcije)} iz STVARNOG Genome prompta."""
    out = {}
    delovi = re.split(r"\[(DOK-\d+): ([^\]|]+?)(?: \|[^\]]*)?\]", prompt)
    for i in range(1, len(delovi) - 2, 3):
        out[delovi[i + 1].strip()] = (delovi[i], delovi[i + 2])
    return out


def _genome_model(pozivi):
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        sek = _sekcije(combined)
        claim = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["stranke"] = [{"uloga": "tuzilac", "ime": gc.TUZILAC}, {"uloga": "tuzeni", "ime": gc.TUZENI}]
        g["rokovi_kriticni"], g["kontradikcije"], g["datumi_kljucni"] = [], [], []
        for iso, opis, oz in gc.HRONOLOGIJA:
            ime = gc.po_oznaci(oz)["ime"]
            if ime in sek and _dmy(iso) in sek[ime][1]:          # samo ono što je STVARNO u promptu, iz TOG dokumenta
                g["datumi_kljucni"].append({"opis": opis, "datum": iso, "znacaj": "visok", "lokacija": sek[ime][0]})
        for k in gc.PROTIVRECNOSTI:
            ca = [c for c, t in claim.items() if k["vrednosti"][0] in t and gc.NAVODI[k["strane"][0]]["tekst"][:12] in t]
            cb = [c for c, t in claim.items() if k["vrednosti"][1] in t]
            ia, ib = (gc.po_oznaci(gc.NAVODI[x]["dok"])["ime"] for x in k["strane"])
            if ca and cb and ia in sek and ib in sek:
                g["kontradikcije"].append({"issue_label": k["pitanje"], "claim_refs": [ca[0], cb[0]],
                                           "relation_type": "cinjenica_cinjenica", "opis": f"{k['vrednosti'][0]} naspram {k['vrednosti'][1]}",
                                           "lokacija_1": sek[ia][0], "lokacija_2": sek[ib][0], "tezina": "kriticna"})
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def spis(solo, monkeypatch):
    k, b = solo
    import routers.case_dna as cd
    import routers.evidence as ev
    import shared.audit_immutable as audit
    from api import _get_supa
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_model(b.genome_pozivi))
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)

    async def _log(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        r = _get_supa().table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                                       "resource_id": resource_id, "metadata": metadata or {}}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(audit, "log_action", _log)
    pid, doks, _ = primi_spis(k, b)
    return k, b, pid, {oz: d["id"] for oz, d in doks.items()}


def _tvrdnje(b, pid, zive=True):
    return [t for t in b.tabele["predmet_dokazi"] if t["predmet_id"] == pid and (not zive or not t.get("deleted_at"))]


def _osvezi_dogadjajem(k, b, pid):
    """Samo put događaja (kao posle novog dokumenta): bez ručnog refresh-a."""
    n = len(b.genome_pozivi)
    from services.event_bus import EventType, emit_durable
    dok = next(d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, "uid-A", pid, {"dokument_id": dok, "trigger": "mir001"}))
    _do_kraja_dogadjaja(b, najvise=20)
    assert len(b.genome_pozivi) == n + 1, "događaj nije osvežio Genome"


def _osvezi(k, b, pid):
    """Ručno osvežavanje (dugme „Osveži analizu“)."""
    r = k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A)
    assert r.status_code in (200, 202, 409), r.text
    _do_kraja_dogadjaja(b, najvise=20)




def _gv2(k, pid, h=A):
    r = k.get(f"/api/predmeti/{pid}/genome-v2", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _kon(g):
    return {x["sporna_tacka"]: x for x in g["kontradikcije"]["aktivne"]}


async def _nepotpune():
    from routers.case_dna import _Tvrdnje
    out = _Tvrdnje()
    out.potpune = False
    return out


# ── 1. Hronologija: ispravan položaj i izvor svakog ključnog događaja ──────────────────────────────────────────────
@treba_ocr
def test_hronologija_ceo_spis_tacan_redosled_i_izvor(spis):
    k, b, pid, doks = spis
    st = sorted([s for s in _gv2(k, pid)["hronologija"]["stavke"] if s.get("datum")], key=lambda s: s["datum"])
    assert [(s["datum"], s["lokacija"]["dokument_id"]) for s in st] == [(iso, doks[oz]) for iso, _, oz in gc.HRONOLOGIJA]
    assert st[0]["lokacija"]["oznaka"] == "DOK-07"           # prvi događaj (2024) pominje tek zapisnik
    assert {s["poreklo"] for s in st} == {"AI_ANALYSIS"}     # analiza, ne „utvrđeno“


# ── 2. Navodi: svaki ključni navod vezan za stvarni izvor, nijedan nije „utvrđena činjenica“ ──────────────────────
@treba_ocr
def test_svaki_kljucni_navod_ima_stvarni_izvor_i_nije_utvrdjen(spis):
    k, b, pid, doks = spis
    zive = _tvrdnje(b, pid)
    for nid, n in gc.NAVODI.items():
        nadjene = [t for t in zive if n["tekst"] in t["tvrdnja"]]
        assert len(nadjene) == 1, (nid, len(nadjene))
        assert nadjene[0]["dokument_id"] == doks[n["dok"]], nid
    g = _gv2(k, pid)
    stavke = g["cinjenice"]["stavke"]
    assert len(stavke) == len(zive)
    assert {s["poreklo"] for s in stavke} == {"SOURCE_FACT"}  # navod pronađen u dokumentu, ne činjenica suda
    assert g["metapodaci"]["kompletnost"] == "COMPLETE"


# ── 3. Protivrečnosti stranaka: obe aktivne, odvojene, sa izvorima suprotnih strana ─────────────────────────────────
@treba_ocr
def test_obe_protivrecnosti_stranaka_aktivne_i_nisu_spojene(spis):
    k, b, pid, doks = spis
    kon = _kon(_gv2(k, pid))
    assert set(kon) == {x["pitanje"] for x in gc.PROTIVRECNOSTI}, list(kon)
    assert len({c["id"] for c in kon.values()}) == len(gc.PROTIVRECNOSTI)
    for x in gc.PROTIVRECNOSTI:
        c = kon[x["pitanje"]]
        assert sorted(u["dokument_id"] for u in c["ucesnici"]) == sorted(doks[gc.NAVODI[n]["dok"]] for n in x["strane"])
        for n, v in zip(x["strane"], x["vrednosti"]):
            assert any(v in u["tvrdnja"] and u["dokument_id"] == doks[gc.NAVODI[n]["dok"]] for u in c["ucesnici"]), (x["id"], n)
        assert {u["poreklo"] for u in c["ucesnici"]} == {"SOURCE_FACT"}


# ── 4. Ponovljeno osvežavanje: isti identiteti, bez duplikata ────────────────────────────────────────────────────────
@treba_ocr
def test_ponovljeno_osvezavanje_stabilno_bez_duplikata(spis):
    k, b, pid, doks = spis
    pre = _gv2(k, pid)
    tabele = ("predmet_dokazi", "predmet_contradictions", "predmet_contradiction_claims", "predmet_hronologija")
    broj = {t: len(b.tabele[t]) for t in tabele}
    _osvezi(k, b, pid)
    _osvezi(k, b, pid)
    posle = _gv2(k, pid)
    assert {t: len(b.tabele[t]) for t in tabele} == broj
    assert {n: c["id"] for n, c in _kon(posle).items()} == {n: c["id"] for n, c in _kon(pre).items()}
    assert sorted(s["lokacija"]["dokument_id"] for s in posle["hronologija"]["stavke"]) == \
        sorted(s["lokacija"]["dokument_id"] for s in pre["hronologija"]["stavke"])
    assert posle["metapodaci"]["genome_verzija"] > pre["metapodaci"]["genome_verzija"]


# ── 5. Model nije video sve tvrdnje: iskreno PARTIAL, sporne tačke se NE zatvaraju ──────────────────────────────────
@treba_ocr
@pytest.mark.parametrize("put", ["rucno", "dogadjaj"])
def test_odsecen_katalog_tvrdnji_ne_zatvara_sporne_tacke_i_nije_complete(spis, monkeypatch, put):
    k, b, pid, doks = spis
    import routers.case_dna as cd
    import shared.claim_catalog as cc
    monkeypatch.setattr(cd, "_MAKS_TVRDNJI", 20)              # granica pre ispravke: 20 < 31 tvrdnje spisa
    monkeypatch.setattr(cc, "MAKS_TVRDNJI", 20)
    (_osvezi if put == "rucno" else _osvezi_dogadjajem)(k, b, pid)
    g = _gv2(k, pid)
    assert g["metapodaci"]["kompletnost"] == "PARTIAL"
    assert [n["vrsta"] for n in g["nesigurnost"] if n["vrsta"] == "tvrdnje_izostavljene"] == ["tvrdnje_izostavljene"]   # razlog nije prećutan
    assert set(_kon(g)) == {x["pitanje"] for x in gc.PROTIVRECNOSTI}
    assert g["kontradikcije"]["zatvorene"] == []


@treba_ocr
def test_neprocitane_tvrdnje_ne_zatvaraju_sporne_tacke(spis, monkeypatch):
    k, b, pid, doks = spis
    import routers.case_dna as cd

    class _Pada:
        def table(self, ime):
            raise RuntimeError("statement timeout")
    out = asyncio.run(cd._fetch_dokazi_kontekst(_Pada(), pid))
    assert out == [] and out.potpune is False                  # greška čitanja ≠ „predmet nema tvrdnji“
    monkeypatch.setattr(cd, "_fetch_dokazi_kontekst", lambda supa, p: _nepotpune())
    _osvezi(k, b, pid)
    g = _gv2(k, pid)
    assert set(_kon(g)) == {x["pitanje"] for x in gc.PROTIVRECNOSTI} and g["kontradikcije"]["zatvorene"] == []
    assert g["metapodaci"]["kompletnost"] == "PARTIAL"


# ── 6. Povučen izvor: navodi više nisu aktivni ni autoritativni ─────────────────────────────────────────────────────
@treba_ocr
def test_obrisan_izvor_povlaci_navode_i_njihovu_spornu_tacku(spis):
    k, b, pid, doks = spis
    did = doks[gc.POVUCENO["brisanje_izvora"]]
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *a, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{did}", headers=B).status_code == 404
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{did}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=20)
    _osvezi(k, b, pid)
    zive = _tvrdnje(b, pid)
    for nid in ("N-06", "N-07"):
        assert not any(gc.NAVODI[nid]["tekst"] in t["tvrdnja"] for t in zive), nid
    g = _gv2(k, pid)
    kon = _kon(g)
    assert "datum postavljanja solarnih panela" not in kon     # K-02 je izgubila jednu stranu → nije aktivna
    assert "datum prijema reklamacije" in kon                  # K-01 ne zavisi od DOK-03
    assert gc.po_oznaci("DOK-03")["redovi"][3] not in b.genome_pozivi[-1]
    assert did not in json.dumps(g["hronologija"]) and did not in json.dumps(g["cinjenice"])


# ── 7. Korisnik B ne čita ništa iz predmeta A ───────────────────────────────────────────────────────────────────────
@treba_ocr
def test_korisnik_b_ne_cita_genome_promene_ni_dokaze_a(spis):
    k, b, pid, doks = spis
    for put in (f"/api/predmeti/{pid}/genome-v2", f"/api/predmeti/{pid}/genome-v2/promene", f"/api/evidence/predmeti/{pid}"):
        r = k.get(put, headers=B)
        assert r.status_code in (403, 404), (put, r.status_code)
        assert gc.TUZENI not in r.text and "08.09.2025" not in r.text
    r = k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=B)
    assert r.status_code in (403, 404), r.status_code
