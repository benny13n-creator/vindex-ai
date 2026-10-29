# -*- coding: utf-8 -*-
"""CG001 — ceo lanac incidenta kroz STVARNE module (ekstrakcija → materijalizacija → domen → paketni upis →
`case_dna` → `/genome-v2` → `/genome-v2/promene` → Case Actions), nad lažnom bazom ns006 (paketni RPC emuliran iz
migracija 124/125). Model je zamenjen funkcijom koja bira tvrdnje ISKLJUČIVO iz kataloga koji je stvarno u promptu —
kao produkcioni model 28.10.2026: sa katalogom bez DOK-02 bira A+B, sa punim katalogom A+C+D."""
import asyncio
import copy
import json
import re

import pytest

from tests.ns006_fake import dispecuj, ocisti, pripremi, zaglavlje
from tests.test_cg001_incident_uplata import (A, B, C, D, D1, D2, ISSUE, KONTR, P, _DOK01, _DOK02, _red,
                                              dokazi_v1, dokazi_v2)

UID = "uid-A"
LABEL = "Razlika u iznosu uplate"


def _model(pozivi):
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        katalog = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        po_tekstu = {t.split(" [")[0]: c for c, t in katalog.items()}
        tekst = dict(_DOK01 + _DOK02)
        if tekst[C] in po_tekstu:
            refs, tez = [po_tekstu[tekst[C]], po_tekstu[tekst[D]], po_tekstu[tekst[A]]], "kriticna"
        else:
            refs, tez = [po_tekstu[tekst[A]], po_tekstu[tekst[B]]], "manja"
        return json.dumps({"snaga_faktori": [], "kontradikcije": [{
            "opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.", "tezina": tez,
            "claim_refs": refs, "lokacija_1": "DOK-01", "lokacija_2": "DOK-02", "issue_label": LABEL,
            "relation_type": "cinjenica_cinjenica"}]}, ensure_ascii=False)
    return _pozovi


def _tabele(dokazi, *, v2_ab=False, case_dna=None, istorija=()):
    t = {
        "predmeti": [{"id": P, "user_id": UID, "naziv": "TEST — Bojan E2E / Evidencija uplate", "tip": "ostalo",
                      "status": "aktivan", "observation_version": 1 if v2_ab else 0, "case_dna": case_dna or {}}],
        "predmet_dokumenti": [
            {"id": D1, "predmet_id": P, "user_id": UID, "naziv_fajla": "Vindex_TEST_01_Beleska_klijenta.pdf", "redni_broj": 1,
             "tekst_sadrzaj": "Test klijent navodi delimičnu uplatu od 40.000 RSD. Preostali iznos 80.000 RSD."},
            {"id": D2, "predmet_id": P, "user_id": UID, "naziv_fajla": "Vindex_TEST_02_Interna_evidencija.pdf", "redni_broj": 2,
             "tekst_sadrzaj": "Interna evidencija prikazuje uplatu od 30.000 RSD. Preostali iznos 90.000 RSD."}],
        "predmet_dokazi": [{**d, "user_id": UID} for d in dokazi], "predmet_genome_history": list(istorija),
        "predmet_issues": [], "predmet_contradictions": [], "predmet_contradiction_claims": [],
        "case_actions": [], "rocista": [],
    }
    if v2_ab:
        t["predmet_issues"] = [{"id": ISSUE, "predmet_id": P, "user_id": UID, "label": LABEL, "status": "DISCOVERED",
                                "created_at": "2026-10-28T21:58:21Z", "updated_at": "2026-10-28T21:58:21Z", "xmin": "1"}]
        t["predmet_contradictions"] = [{"id": KONTR, "issue_id": ISSUE, "relation_type": "cinjenica_cinjenica", "state": "OPEN",
                                        "tezina": "manja", "state_reason": None, "created_at": "2026-10-28T21:58:21Z",
                                        "updated_at": "2026-10-28T21:58:21Z"}]
        t["predmet_contradiction_claims"] = [{"id": f"cl-{x[:4]}", "contradiction_id": KONTR, "dokaz_id": x, "removed_at": None,
                                              "removed_reason": None, "observed_at": "2026-10-28T21:58:21Z"} for x in (A, B)]
    return t


@pytest.fixture
def lanac(monkeypatch):
    import routers.case_dna as cd
    pozivi = []

    def _otvori(tabele):
        k, baza = pripremi(monkeypatch, tabele)
        monkeypatch.setattr(cd, "_pozovi_genome_api", _model(pozivi))
        return k, baza, cd
    yield _otvori, pozivi
    ocisti()


def _refresh(cd, baza, pozivi):
    """Kao u produkciji (trigger `case_evolution:<event>`): DOCUMENT_ACCEPTED → genome_refresh → refresh_case_actions."""
    from services.event_bus import EventType, emit_durable
    n = len(pozivi)
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, UID, P, {"dokument_id": D2, "trigger": "cg001"}))
    dispecuj(4)
    assert len(pozivi) == n + 1, "događaj nije osvežio Genome"


def _gv2(k, h="A"):
    r = k.get(f"/api/predmeti/{P}/genome-v2", headers=zaglavlje(h))
    return r.status_code, (r.json() if r.status_code == 200 else None)


def _promene(k):
    r = k.get(f"/api/predmeti/{P}/genome-v2/promene", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    return [p for p in r.json()["promene"] if p["vrsta"].startswith("kontradikcija")], r.json()


def _akcije(cd):
    from services.case_evolution import _compute_target_actions
    return [a for a in asyncio.run(_compute_target_actions(P)) if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]


def test_lanac_posle_ispravke_isti_redosled_dogadjaja(lanac):
    otvori, pozivi = lanac
    k, baza, cd = otvori(_tabele(dokazi_v1()))
    # 21:58:21 — dva dokumenta, katalog samo DOK-01
    _refresh(cd, baza, pozivi)
    assert "CLAIM-007" in pozivi[-1] and "CLAIM-008" not in pozivi[-1]
    assert baza.tabele["predmet_issues"] == [] and baza.tabele["predmet_contradictions"] == []
    g1 = baza.tabele["predmeti"][0]["case_dna"]
    assert g1["verzija"] == 1 and g1["kontradikcije"][0]["claim_ids"] is None
    _, ugovor = _gv2(k)
    kon = ugovor["kontradikcije"]
    assert kon["izvor"] == "analiza" and kon["aktivne"][0]["stanje"] == "NEPOTVRDJENA_TVRDNJAMA"   # vidljivo, ne tiho
    assert kon["aktivne"][0]["ucesnici"] == [] and kon["aktivne"][0]["reference_proverene"] is False

    # 21:58:33 — tvrdnje DOK-02 izdvojene; 21:58:45 — drugi refresh
    baza.tabele["predmet_dokazi"].extend(_red(i, t, D2, user_id=UID) for i, t in _DOK02)
    _refresh(cd, baza, pozivi)
    [kontr] = [x for x in baza.tabele["predmet_contradictions"] if x["state"] == "OPEN"]
    assert {c["dokaz_id"] for c in baza.tabele["predmet_contradiction_claims"] if c["contradiction_id"] == kontr["id"]} == {A, C, D}
    assert kontr["tezina"] == "kriticna" and len(baza.tabele["predmet_issues"]) == 1
    _, ugovor = _gv2(k)
    kon = ugovor["kontradikcije"]
    assert kon["izvor"] == "v2" and kon["za_pregled"] == [] and "kontinuitet" not in kon["aktivne"][0]
    pr, celo = _promene(k)
    assert pr == [] and [n["oblast"] for n in celo["nepoznato"]] == ["kontradikcije"]   # ne „nestala“, nego nepoznato
    [akc] = _akcije(cd)
    assert akc["prioritet"] == "critical" and akc["dedupe_key"] == f"v2:contradiction:{kontr['id']}"
    assert akc["dokaz"]["dokument_ids"] == sorted([D1, D2])


def test_lanac_zatecenog_produkcionog_stanja(lanac):
    """Produkcija danas: V2 {A,B} OPEN (nastalo pre ispravke), case_dna v1 sa claim_ids A,B. Refresh v2 ({A,C,D})."""
    otvori, pozivi = lanac
    g1 = {"verzija": 1, "_analiza_osnov": {"cinjenica": 7, "dokumenata": 2}, "kontradikcije": [{
        "opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.", "tezina": "manja",
        "claim_ids": sorted([A, B]), "claim_refs": ["CLAIM-004", "CLAIM-002"], "lokacija_1": "DOK-01", "lokacija_2": "DOK-02",
        "issue_label": LABEL, "dokument_id_1": D1, "dokument_id_2": D2, "relation_type": "cinjenica_cinjenica"}]}
    k, baza, cd = otvori(_tabele(dokazi_v2(), v2_ab=True, case_dna=g1))
    from services.v2_projection import u_akcije, ucitaj_v2_kontradikcije
    baza.tabele["case_actions"] = [{**a, "id": "akc-1", "predmet_id": P, "status": "open", "kreirao": "system",
                                    "updated_at": "2026-10-28T21:58:47Z"}
                                   for a in u_akcije(asyncio.run(ucitaj_v2_kontradikcije(baza, P)))]
    clanovi_pre = copy.deepcopy(baza.tabele["predmet_contradiction_claims"])
    kontr_pre = copy.deepcopy(baza.tabele["predmet_contradictions"])

    _refresh(cd, baza, pozivi)
    g2 = baza.tabele["predmeti"][0]["case_dna"]
    assert g2["verzija"] == 2 and g2["kontradikcije"][0]["claim_ids"] == sorted([A, C, D])
    # Persistence: REVIEW_REQUIRED se ne upisuje, ništa se ne zatvara, članstvo i težina netaknuti
    assert baza.tabele["predmet_contradiction_claims"] == clanovi_pre
    assert [(x["id"], x["state"], x["tezina"]) for x in baza.tabele["predmet_contradictions"]] == \
           [(x["id"], x["state"], x["tezina"]) for x in kontr_pre]
    assert len(baza.tabele["predmet_issues"]) == 1
    assert len(baza.tabele["predmet_genome_history"]) == 1                              # istorija sačuvana

    _, ugovor = _gv2(k)
    kon = ugovor["kontradikcije"]
    [akt] = kon["aktivne"]
    assert akt["id"] == KONTR and akt["kontinuitet"] == "NIJE_POTVRDJEN" and akt["tezina"] == "manja"
    assert {u["tvrdnja_id"] for u in akt["ucesnici"]} == {A, B}
    [pr] = kon["za_pregled"]
    assert {u["tvrdnja_id"] for u in pr["ucesnici"]} == {A, C, D} and pr["tezina"] == "kriticna"
    dim = next(d for d in ugovor["spremnost"]["dimenzije"] if d["kljuc"] == "kontradikcije")
    assert dim["vrednost"]["za_pregled"] == 1

    promene, _ = _promene(k)
    assert [p["vrsta"] for p in promene] == ["kontradikcija_promenjena"]

    [akc] = _akcije(cd)
    assert akc["dedupe_key"] == f"v2:contradiction:{KONTR}" and akc["prioritet"] == "medium"
    assert akc["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN" and akc["dokaz"]["claim_ids"] == sorted([A, B])
    otvorene = [a for a in baza.tabele["case_actions"] if a["tip"] == "RAZRESITI_KONTRADIKCIJU" and a["status"] == "open"]
    assert len(otvorene) == 1 and otvorene[0]["id"] == "akc-1"                          # bez duplikata, isti red
    assert "kontinuitet nije potvrđen" in otvorene[0]["razlog"] and otvorene[0]["prioritet"] == "medium"

    # Ponovljen isti refresh: stabilno, bez novih redova i bez promene identiteta
    _refresh(cd, baza, pozivi)
    assert baza.tabele["predmet_contradiction_claims"] == clanovi_pre
    assert len([a for a in baza.tabele["case_actions"] if a["status"] == "open" and a["tip"] == "RAZRESITI_KONTRADIKCIJU"]) == 1


def test_drugi_korisnik_ne_vidi_ni_analizu_ni_promene(lanac):
    otvori, _ = lanac
    k, baza, cd = otvori(_tabele(dokazi_v2(), v2_ab=True))
    assert _gv2(k, "B")[0] == 404
    assert k.get(f"/api/predmeti/{P}/genome-v2/promene", headers=zaglavlje("B")).status_code == 404
    assert k.get(f"/api/predmeti/{P}/genome-v2").status_code == 401


def test_citanje_analize_ne_poziva_model(lanac):
    otvori, pozivi = lanac
    k, baza, cd = otvori(_tabele(dokazi_v2(), v2_ab=True))
    _gv2(k)
    _promene(k)
    assert pozivi == []


# ═══ CG001 Task 1 — šta advokat vidi ODMAH posle deploy-a, bez novog događaja i bez reconcile-a ═══

def _g(verzija, claim_ids, tezina):
    return {"verzija": verzija, "_analiza_osnov": {"cinjenica": 15, "dokumenata": 2}, "kontradikcije": [{
        "opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.", "tezina": tezina,
        "claim_ids": sorted(claim_ids), "lokacija_1": "DOK-01", "lokacija_2": "DOK-02", "issue_label": LABEL,
        "dokument_id_1": D1, "dokument_id_2": D2, "relation_type": "cinjenica_cinjenica"}]}


def _zateceno(otvori, case_dna, *, razlog_sa_oznakom=False):
    """Produkcija u trenutku deploy-a: V2 {A,B} OPEN, `case_dna` već v2, radnja upisana STARIM kodom (bez oznake)."""
    k, baza, cd = otvori(_tabele(dokazi_v2(), v2_ab=True, case_dna=case_dna))
    from services.v2_projection import u_akcije, ucitaj_v2_kontradikcije
    kontr = asyncio.run(ucitaj_v2_kontradikcije(baza, P))
    if razlog_sa_oznakom:
        kontr = [{**x, "kontinuitet": "NIJE_POTVRDJEN"} for x in kontr]
    baza.tabele["case_actions"] = [{**a, "id": "akc-1", "predmet_id": P, "status": "open", "kreirao": "system",
                                    "event_id": None, "correlation_id": None, "confidence": None,
                                    "created_at": "2026-10-28T21:58:26Z", "updated_at": "2026-10-28T21:58:47Z"}
                                   for a in u_akcije(kontr)]
    return k, baza


def _sve_povrsine(k, kor="A"):
    h = zaglavlje(kor)
    pred = k.get(f"/api/case-actions/predmeti/{P}", headers=h)
    wl = k.get("/api/case-actions/worklist", headers=h)
    ws = k.get("/api/workspace", headers=h)
    gv = k.get(f"/api/predmeti/{P}/genome-v2", headers=h)
    assert wl.status_code == 200 and ws.status_code == 200, (wl.text, ws.text)
    wl_akc = [a for c in wl.json()["predmeti"] if c["predmet_id"] == P for a in c["akcije"]]
    ws_akc = [s for kanta in ("danas", "kriticno", "predstojece") for s in ws.json().get(kanta) or []
              if s.get("predmet_id") == P and s.get("vrsta") == "case_action"]
    return pred, wl_akc, ws_akc, gv


def test_posle_deploya_bez_dogadjaja_sve_povrsine_nose_kontinuitet(lanac):
    otvori, pozivi = lanac
    k, baza = _zateceno(otvori, _g(2, [A, C, D], "kriticna"))
    assert "kontinuitet" not in baza.tabele["case_actions"][0]["razlog"]          # upisano starim kodom
    pre = copy.deepcopy(baza.tabele)

    pred, wl_akc, ws_akc, gv = _sve_povrsine(k)
    assert pred.status_code == 200
    [a_pred], [a_wl], [a_ws] = pred.json()["akcije"], wl_akc, ws_akc
    for a in (a_pred, a_wl):
        assert a["id"] == "akc-1" and a["prioritet"] == "medium"                     # isti red, prioritet se ne penje
        assert a["razlog"].startswith(LABEL) and "kontinuitet nije potvrđen" in a["razlog"]
        assert a["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN" and a["dokaz"]["claim_ids"] == sorted([A, B])
    assert a_ws["id"] == "akc-1" and a_ws["prioritet"] == "medium" and "kontinuitet nije potvrđen" in a_ws["naslov"]
    assert a_ws["izvor"]["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN"
    # Analiza kaže isto: A/B aktivna sa oznakom, A/C/D za pregled
    kon = gv.json()["kontradikcije"]
    assert kon["aktivne"][0]["kontinuitet"] == "NIJE_POTVRDJEN" and len(kon["za_pregled"]) == 1

    # GET ništa ne upisuje (lažna baza pri čitanju napravi praznu tabelu koju ne poznaje — to nije red)
    assert {t: r for t, r in baza.tabele.items() if r} == {t: r for t, r in pre.items() if r}
    assert pozivi == []                                                            # ni model, ni reconcile
    assert not baza.tabele.get("events")                                           # nijedan događaj


def test_posle_deploya_kontinuitet_potvrdjen_skida_staru_oznaku(lanac):
    """Obrnuto: red nosi oznaku iz ranijeg usklađivanja, a najnovije opažanje je nastavak (A/B → A/B/C)."""
    otvori, _ = lanac
    k, baza = _zateceno(otvori, _g(3, [A, B, C], "manja"), razlog_sa_oznakom=True)
    assert "kontinuitet nije potvrđen" in baza.tabele["case_actions"][0]["razlog"]
    [a] = _sve_povrsine(k)[0].json()["akcije"]
    assert a["razlog"] == LABEL and "kontinuitet" not in a["dokaz"]


@pytest.mark.parametrize("case_dna", [{}, {"verzija": 2, "greska": "model nije odgovorio"},
                                      {"verzija": 2, "kontradikcije": "nije lista"}])
def test_bez_odlucivog_opazanja_red_ostaje_kakav_je_upisan(lanac, case_dna):
    otvori, _ = lanac
    for sa_oznakom in (False, True):
        k, baza = _zateceno(otvori, case_dna, razlog_sa_oznakom=sa_oznakom)
        upisan = baza.tabele["case_actions"][0]
        [a] = _sve_povrsine(k)[0].json()["akcije"]
        assert (a["razlog"], a["dokaz"]) == (upisan["razlog"], upisan["dokaz"])


def test_nedostupan_izvor_ne_menja_red_i_ne_rusi_tablu(lanac, monkeypatch):
    otvori, _ = lanac
    k, baza = _zateceno(otvori, _g(2, [A, C, D], "kriticna"))
    import services.v2_projection as vp

    async def _pad(*a, **kw):
        raise RuntimeError("predmet_contradictions nedostupan")
    monkeypatch.setattr(vp, "ucitaj_v2_kontradikcije", _pad)
    pred, wl_akc, ws_akc, _ = _sve_povrsine(k)
    [a] = pred.json()["akcije"]
    assert a["razlog"] == baza.tabele["case_actions"][0]["razlog"] and "kontinuitet" not in a["dokaz"]
    assert len(wl_akc) == 1 and len(ws_akc) == 1


def test_drugi_korisnik_ne_dobija_radnju_predmeta(lanac):
    otvori, _ = lanac
    k, _ = _zateceno(otvori, _g(2, [A, C, D], "kriticna"))
    assert k.get(f"/api/case-actions/predmeti/{P}", headers=zaglavlje("B")).status_code == 404
    h = zaglavlje("B")
    wl = k.get("/api/case-actions/worklist", headers=h).json()
    ws = k.get("/api/workspace", headers=h).json()
    assert all(c["predmet_id"] != P for c in wl["predmeti"])
    assert all(s.get("predmet_id") != P for kanta in ("danas", "kriticno", "predstojece") for s in ws.get(kanta) or [])
    assert k.get(f"/api/case-actions/predmeti/{P}").status_code == 401
