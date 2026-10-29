# -*- coding: utf-8 -*-
"""CG001 Task 3 — pokušaj obaranja read-only statusa kontinuiteta (`shared/issue_v2.status_kontinuiteta`).

Četiri ishoda koja se NE smeju pomešati:
  dokazan kontinuitet  → bez oznake (domen bi opažanje upisao kao nastavak);
  nejasan kontinuitet  → NIJE_POTVRDJEN (domen bi tražio pregled);
  nepotpuni izvori     → odluka se donosi bez filtera živih tvrdnji (nepročitano ne gasi oznaku);
  nepoznato stanje     → NEPOZNAT (opažanje nije ono iz kog je nastala V2 slika) ili None (nema opažanja) — nikad
                         „bez oznake“ izvedeno iz ustajalog opažanja.
Nijedna provera ne spaja skupove tvrdnji i ništa ne upisuje."""
import asyncio
import copy

import pytest

from shared.issue_v2 import (KLJUC_VERZIJE_OPAZANJA, ODLUKA_NASTAVAK, ODLUKA_NOVA, ODLUKA_PREGLED,
                             razresi_kontinuitet, status_kontinuiteta)
from tests.ns006_fake import dispecuj, zaglavlje
from tests.test_cg001_incident_uplata import A, B, C, D, D1, D2, KONTR, P, dokazi_v2
from tests import test_cg001_lanac as L
from tests.test_cg001_lanac import lanac  # noqa: F401 — fixture

E, F = "e0000000-0000-4000-8000-0000000000e1", "f0000000-0000-4000-8000-0000000000f1"
CC = "cinjenica_cinjenica"


def _k(cid, iid, *claims, rel=CC, state="OPEN"):
    return {"id": cid, "issue_id": iid, "issue_status": "DISCOVERED", "state": state, "relation_type": rel,
            "claim_ids": list(claims)}


def _dna(*skupovi, verzija=None, rel=CC, label="Razlika u iznosu uplate"):
    g = {"verzija": 2, "kontradikcije": [{"claim_ids": sorted(s), "relation_type": rel, "issue_label": label}
                                         for s in skupovi]}
    if verzija is not None:
        g[KLJUC_VERZIJE_OPAZANJA] = verzija
    return g


def _teme(v2):
    t = {}
    for k in v2:
        if k["state"] == "OPEN":
            t.setdefault(k["issue_id"], {"issue_id": k["issue_id"], "status": "DISCOVERED", "claim_set": frozenset()})
            t[k["issue_id"]]["claim_set"] |= frozenset(k["claim_ids"])
    return list(t.values())


AB = [_k("k1", "i1", A, B)]


# ── 1–3: odnos skupova ──────────────────────────────────────────────────────────────────────────────

def test_1_delimicno_preklapanje_nije_potvrdjeno_i_ne_spaja():
    st = status_kontinuiteta(AB, _dna({A, C, D}, verzija=2), 2)
    assert st["oznake"] == {"k1": "NIJE_POTVRDJEN"}
    [n] = st["nerazreseno"]
    assert n["claim_ids"] == sorted([A, C, D]) and n["kontradikcije"] == ["k1"]
    assert razresi_kontinuitet(frozenset({A, C, D}), _teme(AB))["odluka"] == ODLUKA_PREGLED   # isti domen
    assert AB[0]["claim_ids"] == [A, B]                                                       # ulaz netaknut


def test_2_nadskup_je_dokazan_kontinuitet():
    st = status_kontinuiteta(AB, _dna({A, B, C}, verzija=2), 2)
    assert st == {"oznake": {}, "nerazreseno": []}
    assert razresi_kontinuitet(frozenset({A, B, C}), _teme(AB))["odluka"] == ODLUKA_NASTAVAK


def test_3_disjunktni_skupovi_su_nova_tema_ne_nastavak_ni_oznaka():
    st = status_kontinuiteta(AB, _dna({C, D}, verzija=2), 2)
    assert st == {"oznake": {}, "nerazreseno": []}
    assert razresi_kontinuitet(frozenset({C, D}), _teme(AB))["odluka"] == ODLUKA_NOVA


# ── 4–5: identitet nije oznaka ni relacija ──────────────────────────────────────────────────────────

def test_4_dve_teme_istog_labela_ne_dele_identitet():
    v2 = [_k("k1", "i1", A, B), _k("k2", "i2", C, D)]                      # obe „Razlika u iznosu uplate“
    # opažanje dodiruje obe → obe nepotvrđene, nijedna se ne bira
    assert status_kontinuiteta(v2, _dna({A, C}, verzija=2), 2)["oznake"] == {"k1": "NIJE_POTVRDJEN", "k2": "NIJE_POTVRDJEN"}
    # nastavak prve ne dira drugu
    assert status_kontinuiteta(v2, _dna({A, B}, verzija=2), 2)["oznake"] == {}
    # isti label, tuđe tvrdnje → ništa (label ne učestvuje u odluci)
    assert status_kontinuiteta(v2, _dna({E, F}, verzija=2), 2)["oznake"] == {}


def test_5_dve_kontradikcije_razlicite_relacije_iste_teme():
    v2 = [_k("k1", "i1", A, B), _k("k2", "i1", A, E, rel="cinjenica_norma")]   # tema = {A,B,E}
    assert status_kontinuiteta(v2, _dna({A, B}, verzija=2), 2)["oznake"] == {}        # podskup teme
    assert status_kontinuiteta(v2, _dna({A, C}, verzija=2), 2)["oznake"] == {"k1": "NIJE_POTVRDJEN",
                                                                               "k2": "NIJE_POTVRDJEN"}
    # zasebne teme po relaciji: preklapanje sa jednom ne označava drugu
    v2b = [_k("k1", "i1", A, B), _k("k2", "i2", E, F, rel="cinjenica_norma")]
    assert status_kontinuiteta(v2b, _dna({A, C}, verzija=2), 2)["oznake"] == {"k1": "NIJE_POTVRDJEN"}


# ── 6–7: nedostupni izvori ──────────────────────────────────────────────────────────────────────────

def test_6_nedostupni_dokazi_ne_gase_oznaku_a_poznato_povucene_iskljucuje():
    assert status_kontinuiteta(AB, _dna({A, C, D}, verzija=2), 2, None)["oznake"] == {"k1": "NIJE_POTVRDJEN"}
    # poznato da su C i D povučeni → opažanje {A} nije skup o kome se odlučuje
    assert status_kontinuiteta(AB, _dna({A, C, D}, verzija=2), 2, {A, B})["oznake"] == {}


def test_6_projekcija_pad_citanja_tvrdnji_ne_gasi_oznaku():
    from services.v2_projection import oznacene_kontradikcije

    class _Pad:
        def table(self, *_):
            raise RuntimeError("predmet_dokazi nedostupan")
    assert asyncio.run(oznacene_kontradikcije(_Pad(), P, AB, _dna({A, C, D}, verzija=2), 2)) == {"k1": "NIJE_POTVRDJEN"}


def test_7_nedostupan_v2_izvor_je_degradirano_ne_potvrdjeno():
    from shared.genome_contract import sastavi_kontradikcije
    k = sastavi_kontradikcije(v2=None, case_dna=_dna({A, C, D}, verzija=2), dokazi=dokazi_v2(), dokumenti=[],
                              izvori={"kontradikcije": "GRESKA"}, observation_version=2)
    assert k["stanje"] == "DEGRADED" and k["aktivne"] == [] and k["za_pregled"] == []
    assert status_kontinuiteta([], _dna({A, C, D}, verzija=2), 2) == {"oznake": {}, "nerazreseno": []}


@pytest.mark.parametrize("case_dna", [None, {}, {"greska": "x", "kontradikcije": []}, {"kontradikcije": "x"}])
def test_7_bez_opazanja_nema_odluke(case_dna):
    assert status_kontinuiteta(AB, case_dna, 2) is None


# ── 8–10: verzija opažanja ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dna_v, pred_v", [(3, 2), (1, 2), (2, None), ("2", 3)])
def test_8_9_neusaglasena_verzija_je_nepoznato_cak_i_kad_bi_bilo_nastavak(dna_v, pred_v):
    for skup in ({A, B, C}, {A, C, D}, {C, D}):
        st = status_kontinuiteta(AB, _dna(skup, verzija=dna_v), pred_v)
        assert st == {"oznake": {"k1": "NEPOZNAT"}, "nerazreseno": []}       # ustajalo ne ide ni u „pregled“


def test_8_9_ista_verzija_kao_string_i_broj():
    assert status_kontinuiteta(AB, _dna({A, C, D}, verzija=2), "2")["oznake"] == {"k1": "NIJE_POTVRDJEN"}


def test_8_case_dna_pre_cg001_bez_zapisa_verzije_odlucuje_kao_ranije():
    # zatečeno produkciono stanje: verzija se ne može proveriti — odluka iz opažanja (oznaka je konzervativna)
    assert status_kontinuiteta(AB, _dna({A, C, D}), 2)["oznake"] == {"k1": "NIJE_POTVRDJEN"}


def test_zatvorene_nisu_teme_i_nisu_nepoznate():
    v2 = [_k("k1", "i1", A, B, state="RESOLVED")]
    assert status_kontinuiteta(v2, _dna({A, C, D}, verzija=1), 2) == {"oznake": {}, "nerazreseno": []}


def test_10_citanje_usred_osvezavanja_je_nepoznato_pa_posle_nije_potvrdjeno(lanac):
    """Stvarni lanac: čitanje se izvršava POSLE upisa V2 paketa a PRE upisa `case_dna` (isti refresh)."""
    otvori, pozivi = lanac
    g1 = L._g(1, [A, B], "manja")
    g1[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza, cd = otvori(L._tabele(dokazi_v2(), v2_ab=True, case_dna=g1))
    from routers.case_dna import sastavi_zivi_predmet, ucitaj_zivi_predmet
    from services.v2_projection import uz_trenutni_kontinuitet
    vidjeno = {}
    pravi = cd._sync_rokovi_to_hronologija

    async def _usred(supa, *a, **kw):
        vidjeno["verzija"] = baza.tabele["predmeti"][0]["observation_version"]
        vidjeno["dna"] = baza.tabele["predmeti"][0]["case_dna"].get(KLJUC_VERZIJE_OPAZANJA)
        izv = await ucitaj_zivi_predmet(baza, P, L.UID)
        vidjeno["kontr"] = sastavi_zivi_predmet(izv)["kontradikcije"]
        red = {"id": "akc-x", "predmet_id": P, "razlog": L.LABEL, "prioritet": "medium",
               "dokaz": {"source_type": "v2_contradiction", "source_id": KONTR}}
        vidjeno["akcija"] = (await uz_trenutni_kontinuitet(baza, [red]))[0]
        return await pravi(supa, *a, **kw)
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(cd, "_sync_rokovi_to_hronologija", _usred)
    try:
        L._refresh(cd, baza, pozivi)
    finally:
        mp.undo()
    assert vidjeno["verzija"] == 2 and vidjeno["dna"] == 1                     # paket upisan, case_dna još star
    [akt] = vidjeno["kontr"]["aktivne"]
    assert akt["kontinuitet"] == "NEPOZNAT" and "nije proveren" in akt["napomena"]
    assert vidjeno["kontr"]["za_pregled"] == []
    assert vidjeno["akcija"]["dokaz"]["kontinuitet"] == "NEPOZNAT" and "nije proveren" in vidjeno["akcija"]["razlog"]
    assert vidjeno["akcija"]["prioritet"] == "medium"
    # posle osvežavanja: case_dna nosi verziju paketa iz kog je nastao
    assert baza.tabele["predmeti"][0]["case_dna"][KLJUC_VERZIJE_OPAZANJA] == baza.tabele["predmeti"][0]["observation_version"] == 2
    _, ug = L._gv2(k)
    assert ug["kontradikcije"]["aktivne"][0]["kontinuitet"] == "NIJE_POTVRDJEN"
    assert len(ug["kontradikcije"]["za_pregled"]) == 1


def test_10_neuspeo_upis_case_dna_posle_paketa_ostaje_nepoznat(lanac):
    otvori, pozivi = lanac
    g1 = L._g(1, [A, B], "manja")
    g1[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza, cd = otvori(L._tabele(dokazi_v2(), v2_ab=True, case_dna=g1))

    async def _pad(*a, **kw):
        raise RuntimeError("upis hronologije nije uspeo")
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(cd, "_sync_rokovi_to_hronologija", _pad)
    try:
        from services.event_bus import EventType, emit_durable
        asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, L.UID, P, {"dokument_id": D2, "trigger": "cg001"}))
        dispecuj(4)                                   # prvi pokušaj + ponovljeni (svaki upiše paket, nijedan case_dna)
    finally:
        mp.undo()
    assert baza.tabele["predmeti"][0]["observation_version"] > 1 and baza.tabele["predmeti"][0]["case_dna"] == g1
    _, ug = L._gv2(k)
    assert ug["kontradikcije"]["aktivne"][0]["kontinuitet"] == "NEPOZNAT" and ug["kontradikcije"]["za_pregled"] == []


def test_paket_bez_upisanih_stavki_prijavljuje_stvarnu_novu_verziju(lanac):
    """Samo REVIEW_REQUIRED → RPC bez redova, ali SQL je ipak podigao verziju (migracija 125)."""
    otvori, pozivi = lanac
    k, baza, cd = otvori(L._tabele(dokazi_v2(), v2_ab=True, case_dna=L._g(1, [A, B], "manja")))
    from services.v2_contradiction_persistence import persist_observation_package
    rez = asyncio.run(persist_observation_package(predmet_id=P, user_id=L.UID, event_id=None, predlozi=[],
                                                  tezina_po_indeksu={}, kompletno_opazanje=False))
    assert rez["observation_version"] == baza.tabele["predmeti"][0]["observation_version"] == 2


# ── 11: povučena tvrdnja ────────────────────────────────────────────────────────────────────────────

def test_11_povucena_tvrdnja_kroz_rutu(lanac):
    otvori, _ = lanac
    dz = dokazi_v2()
    for d in dz:
        if d["id"] in (C, D):
            d["deleted_at"] = "2026-10-29T06:00:00Z"
    g = L._g(2, [A, C, D], "kriticna")
    g[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza, cd = otvori(L._tabele(dz, v2_ab=True, case_dna=g))
    _, ug = L._gv2(k)
    [akt] = ug["kontradikcije"]["aktivne"]
    assert "kontinuitet" not in akt and ug["kontradikcije"]["za_pregled"] == []    # opažanje {A} nije skup odluke
    # povučen ČLAN sačuvane veze: kontradikcija sa < 2 živa člana nije otvorena tema
    dz2 = dokazi_v2()
    for d in dz2:
        if d["id"] == B:
            d["deleted_at"] = "2026-10-29T06:00:00Z"
    from services.v2_projection import ucitaj_v2_kontradikcije
    k2, baza2, _ = otvori(L._tabele(dz2, v2_ab=True, case_dna=g))
    assert asyncio.run(ucitaj_v2_kontradikcije(baza2, P)) == []


# ── 12: drugi korisnik ──────────────────────────────────────────────────────────────────────────────

def test_12_korisnik_B_ne_cita_niti_utice_na_odluku(lanac):
    otvori, _ = lanac
    g = L._g(2, [A, B, C], "manja")                    # nadskup sopstvene teme vlasnika = nastavak
    g[KLJUC_VERZIJE_OPAZANJA] = 1
    k, baza = L._zateceno(otvori, g)
    # tuđa sporna tačka zakačena za isti predmet (odbrana u dubinu iza GUARD-a RPC-a), preklapa opažanje
    baza.tabele["predmet_issues"].append({"id": "i-tudja", "predmet_id": P, "user_id": "uid-B", "label": "x",
                                          "status": "DISCOVERED"})
    baza.tabele["predmet_contradictions"].append({"id": "k-tudja", "issue_id": "i-tudja", "relation_type": CC,
                                                  "state": "OPEN", "tezina": "kriticna"})
    baza.tabele["predmet_contradiction_claims"] += [{"id": f"t-{x[:3]}", "contradiction_id": "k-tudja", "dokaz_id": x,
                                                     "removed_at": None} for x in (A, C)]
    pre = copy.deepcopy({t: r for t, r in baza.tabele.items() if r})
    pred, wl, ws, gv = L._sve_povrsine(k)
    [a] = pred.json()["akcije"]
    assert "kontinuitet" not in a["dokaz"] and a["razlog"] == L.LABEL                 # tuđa tema ne menja odluku
    assert "kontinuitet" not in gv.json()["kontradikcije"]["aktivne"][0]
    hb = zaglavlje("B")
    for ruta in (f"/api/predmeti/{P}/genome-v2", f"/api/predmeti/{P}/genome-v2/promene", f"/api/case-actions/predmeti/{P}"):
        assert k.get(ruta, headers=hb).status_code == 404
        assert k.get(ruta).status_code == 401
    assert P not in k.get("/api/case-actions/worklist", headers=hb).text
    assert P not in k.get("/api/workspace", headers=hb).text
    assert {t: r for t, r in baza.tabele.items() if r} == pre


def test_rucno_osvezavanje_pamti_verziju_opazanja(lanac, monkeypatch):
    """Drugi proizvođač opažanja (POST /case-dna/refresh) mora upisati istu vezu kao pozadinski put."""
    import shared.permissions as perm
    import shared.usage as us

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _naplati(*a, **kw):
        return 10
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_naplati))
    monkeypatch.setattr(us.UsageService, "refund", staticmethod(_nista))
    otvori, pozivi = lanac
    k, baza, cd = otvori(L._tabele(dokazi_v2(), v2_ab=True, case_dna=L._g(1, [A, B], "manja")))
    r = k.post(f"/api/predmeti/{P}/case-dna/refresh", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    pred = baza.tabele["predmeti"][0]
    assert pred["case_dna"][KLJUC_VERZIJE_OPAZANJA] == pred["observation_version"] == 2
    _, ug = L._gv2(k)
    assert ug["kontradikcije"]["aktivne"][0]["kontinuitet"] == "NIJE_POTVRDJEN"


def test_8b_jedna_tema_dva_nova_kandidata_oba_traze_pregled_nista_se_ne_spaja():
    st = status_kontinuiteta(AB, _dna({A, C}, {B, D}, verzija=2), 2)
    assert st["oznake"] == {"k1": "NIJE_POTVRDJEN"}
    assert sorted(n["claim_ids"] for n in st["nerazreseno"]) == sorted([sorted([A, C]), sorted([B, D])])


def test_nastavak_u_istom_opazanju_je_dokazan_kontinuitet_a_preklopna_stavka_ide_u_pregled():
    """Opažanje {A,B} (nastavak) + {B,D} (preklapanje): tema je dokazano nastavljena — bez oznake „nije potvrđen“;
    {B,D} i dalje traži pregled, vezan za istu temu."""
    st = status_kontinuiteta(AB, _dna({A, B}, {B, D}, verzija=2), 2)
    assert st["oznake"] == {}
    [n] = st["nerazreseno"]
    assert n["claim_ids"] == sorted([B, D]) and n["kontradikcije"] == ["k1"]
    # dve teme: nastavak prve ne skida oznaku druge koju preklapa druga stavka
    v2 = [_k("k1", "i1", A, B), _k("k2", "i2", C, D)]
    assert status_kontinuiteta(v2, _dna({A, B}, {C, E}, verzija=2), 2)["oznake"] == {"k2": "NIJE_POTVRDJEN"}
