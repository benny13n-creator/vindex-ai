# -*- coding: utf-8 -*-
"""NS008 Task 19 — HARD GATE: matrica poverljivosti Law Brain-a kroz STVARNE rute.

Akteri: A i B u kancelariji K1; C u kancelariji K2; R uklonjen iz K1 (REMOVED); S suspendovan (SUSPENDED);
I pozvan (INVITED). A ima: privatan zatvoren predmet (sa ljudskim ishodom), advokatski odobren rad na tom predmetu,
ručnu belešku o sudiji (opšta, kancelarijska), belešku vezanu za svoj predmet i vezu u grafu sa ishodom.

Pravila (direktiva + Task 0):
  • B NE vidi A-ov sirov predmet, rad, ishod ni predmetnu belešku (kanonski ACL = vlasnik + delegiranje);
    B VIDI opštu belešku kancelarije (postojeći izričit put deljenja).
  • B ne sme da nasluti A-ov predmet iz brojeva, naslova, ID-eva, sličnosti, statistike ishoda ni grešaka:
    svaki B-ov odgovor je BAJT-IDENTIČAN u svetu sa i bez A-ovih podataka.
  • C (druga kancelarija), R/S/I (nisu aktivni članovi) ne vide ništa od znanja K1.
  • Promena članstva važi od SLEDEĆEG zahteva (nema keša).
"""
import json

import pytest

import tests.ns008_fake as f8

K1, K2 = "e1e1e1e1-1919-4000-8000-000000000001", "e2e2e2e2-1919-4000-8000-000000000002"
PA_OLD = "aaaaaaaa-1919-4000-8000-000000000001"
PA_CUR = "aaaaaaaa-1919-4000-8000-000000000002"
PB_CUR = "bbbbbbbb-1919-4000-8000-000000000001"
PC_CUR = "cccccccc-1919-4000-8000-000000000001"
NEPOSTOJI = "dddddddd-1919-4000-8000-000000000009"
SUD = "Osnovni sud u Beogradu"
TAJNO = ("Petrović protiv Gradnja Invest DOO", PA_OLD, "s-tajni", "Tajna tužba A", "o-tajni", "Klijent A popušta", "g-tajna")

f8_tokeni = {"tok-R": "uid-R", "tok-S": "uid-S", "tok-I": "uid-I"}


def _p(pid, uid, naziv, status):
    return {"id": pid, "user_id": uid, "naziv": naziv, "tip": "radni", "oblast": "radno", "status": status,
            "case_dna": {"verzija": 2}, "updated_at": "2026-09-01"}


def _svet(sa_a=True):
    predmeti = [_p(PB_CUR, "uid-B", "B tekući", "aktivan"), _p(PC_CUR, "uid-C", "C tekući", "aktivan"),
                _p(PA_CUR, "uid-A", "A tekući", "aktivan")]
    roc = [{"predmet_id": x, "user_id": u, "sud": SUD, "status": "odrzano"}
           for x, u in ((PB_CUR, "uid-B"), (PC_CUR, "uid-C"), (PA_CUR, "uid-A"))]
    dok = [{"predmet_id": x, "user_id": u, "kategorija": "svedok"} for x, u in ((PB_CUR, "uid-B"), (PC_CUR, "uid-C"), (PA_CUR, "uid-A"))]
    t = {
        "predmeti": predmeti, "rocista": roc, "predmet_dokazi": dok, "outcome_log": [], "predmet_issues": [],
        "predmet_contradictions": [], "predmet_delegiranja": [], "staging_memory": [], "lessons_learned": [],
        "klijenti": [], "memory_graph_edges": [],
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}, {"id": K2, "admin_uid": "uid-Y"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-R", "status": "REMOVED"},
                                {"kancelarija_id": K1, "user_id": "uid-S", "status": "SUSPENDED"},
                                {"kancelarija_id": K1, "user_id": "uid-I", "status": "INVITED"},
                                {"kancelarija_id": K2, "user_id": "uid-C", "status": "ACTIVE"}],
        # podmetnut red: korisnik C (druga kancelarija) „odobren" rad na A-ovom predmetu — ne sme da se pojavi nikome
        "staging_memory_podmetnut": [{"id": "s-podmetnut", "user_id": "uid-C", "kancelarija_id": K2, "predmet_id": PA_CUR,
                                      "tip": "tuzba", "naziv": "Podmetnut C rad", "tekst": "Podmetnut C tekst",
                                      "confidence_score": 0.99, "is_lawyer_approved": True,
                                      "approved_at": "2026-08-01T00:00:00+00:00", "status": "approved", "pinecone_indexed": True}],
        "memory_entries": [{"id": "m-opsta", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "sudija",
                            "entity_id": "Petrović", "entity_name": "Sudija Petrović", "tip": "obrazac",
                            "sadrzaj": "Traži tabelu rokova.", "aktivan": True, "izvor": "manual", "potvrde_count": 1}],
    }
    t["staging_memory"] += t.pop("staging_memory_podmetnut")
    if sa_a:
        t["predmeti"].append(_p(PA_OLD, "uid-A", TAJNO[0], "zatvoren"))
        t["rocista"].append({"predmet_id": PA_OLD, "user_id": "uid-A", "sud": SUD, "status": "odrzano"})
        t["predmet_dokazi"].append({"predmet_id": PA_OLD, "user_id": "uid-A", "kategorija": "svedok"})
        t["outcome_log"].append({"id": "o-tajni", "predmet_id": PA_OLD, "user_id": "uid-A", "ishod": "pobeda", "presudni_faktori": ["svedoci"]})
        t["staging_memory"].append({"id": "s-tajni", "user_id": "uid-A", "kancelarija_id": K1, "predmet_id": PA_OLD,
                                    "tip": "tuzba", "naziv": "Tajna tužba A", "tekst": "Tajna tužba A tekst", "confidence_score": 0.95,
                                    "is_lawyer_approved": True, "approved_at": "2026-08-01T00:00:00+00:00", "status": "approved",
                                    "pinecone_indexed": True})
        t["memory_entries"].append({"id": "m-pred", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "predmet",
                                    "entity_id": PA_OLD, "entity_name": TAJNO[0], "tip": "napomena",
                                    "sadrzaj": "Klijent A popušta pod pritiskom.", "aktivan": True, "izvor": "manual"})
        t["memory_graph_edges"].append({"id": "g-tajna", "kancelarija_id": K1, "from_type": "argument", "from_id": "zast",
                                        "from_naziv": "Zastarelost", "to_type": "predmet", "to_id": PA_OLD,
                                        "to_naziv": TAJNO[0], "relacija": "primenjen_u", "predmet_id": PA_OLD, "ishod": "pobeda"})
    return t


@pytest.fixture
def svet(monkeypatch):
    import tests.ns005_harness as h5
    for tok, uid in f8_tokeni.items():
        monkeypatch.setitem(h5.TOKENI, tok, uid)
    stanje = {}

    def _napravi(sa_a=True):
        if "k" in stanje:
            f8.ocisti()
        stanje["k"], stanje["b"] = f8.pripremi(monkeypatch, _svet(sa_a))
        import shared.permissions as perm
        import services.law_brain_sinteza as S

        async def _politika(feature):
            return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

        async def _nista(*a, **kw):
            return None

        async def _model(prompt, pid):
            stanje.setdefault("promptovi", []).append(prompt)
            return json.dumps({"tvrdnje": []})
        monkeypatch.setattr(perm, "get_policy", _politika)
        monkeypatch.setattr(perm, "_check_dependencies", _nista)
        monkeypatch.setattr(S, "_pozovi_model_sinteze", _model)
        import shared.usage as us

        async def _c(*a, **kw):
            return None
        monkeypatch.setattr(us.UsageService, "consume", staticmethod(_c))
        return stanje["k"], stanje["b"]
    yield _napravi, stanje
    f8.ocisti()


def H(ko):
    return {"Authorization": f"Bearer tok-{ko}"}


def _odgovori(k, ko, pid):
    out = {}
    for put in ("/api/law-brain/znanje", f"/api/law-brain/predmeti/{pid}", f"/api/law-brain/predmeti/{PA_OLD}",
                f"/api/law-brain/predmeti/{NEPOSTOJI}"):
        r = k.get(put, headers=H(ko))
        out["GET " + put.replace(PA_OLD, "<A>")] = (r.status_code, r.text)
    for put in (f"/api/law-brain/predmeti/{pid}/sinteza", f"/api/law-brain/predmeti/{PA_OLD}/sinteza"):
        r = k.post(put, headers=H(ko))
        out["POST " + put.replace(PA_OLD, "<A>")] = (r.status_code, r.text)
    return out


def test_vlasnik_vidi_sve_svoje(svet):
    napravi, _ = svet
    k, _ = napravi()
    d = k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=H("A")).json()
    assert [s["predmet_id"] for s in d["similar_cases"]["stavke"]] == [PA_OLD]
    assert [a["source_ref"]["id"] for a in d["verified_artifacts"]["stavke"]] == ["s-tajni"]
    assert d["descriptive_outcomes"]["po_ishodu"] == {"pobeda": 1}
    z = k.get("/api/law-brain/znanje", headers=H("A")).json()
    assert {b["source_ref"]["id"] for b in z["memorija_kancelarije"]["stavke"]} == {"m-opsta", "m-pred"}
    assert [v["source_ref"]["id"] for v in z["memorija_kancelarije"]["veze"]] == ["g-tajna"]


@pytest.mark.parametrize("ko,pid", [("B", PB_CUR), ("C", PC_CUR)])
def test_bez_signala_postojanja_bajt_identicno(svet, ko, pid):
    napravi, stanje = svet
    k, _ = napravi(sa_a=True)
    sa = _odgovori(k, ko, pid)
    prompt_sa = list(stanje.get("promptovi", []))
    k, _ = napravi(sa_a=False)
    stanje["promptovi"] = []
    bez = _odgovori(k, ko, pid)
    assert sa == bez, {x: (sa[x][0], bez[x][0]) for x in sa if sa[x] != bez[x]}
    assert prompt_sa == stanje.get("promptovi", []), "ni model ne sme da dobije drugačiji kontekst"
    sve = json.dumps(sa, ensure_ascii=False)
    for t in TAJNO:
        assert t not in sve, t
    assert sa[f"GET /api/law-brain/predmeti/<A>"] == sa[f"GET /api/law-brain/predmeti/{NEPOSTOJI}"], "tuđ = nepostojeći"
    assert sa[f"POST /api/law-brain/predmeti/<A>/sinteza"][0] == 404


def test_kolega_vidi_samo_opstu_belesku(svet):
    napravi, _ = svet
    k, _ = napravi()
    z = k.get("/api/law-brain/znanje", headers=H("B")).json()
    assert [b["source_ref"]["id"] for b in z["memorija_kancelarije"]["stavke"]] == ["m-opsta"]
    assert z["memorija_kancelarije"]["veze"] == [] and z["verifikovani_radovi"]["state"] == "EMPTY"


@pytest.mark.parametrize("ko", ["C", "R", "S", "I"])
def test_druga_kancelarija_i_neaktivni_ne_vide_znanje_k1(svet, ko):
    napravi, _ = svet
    k, _ = napravi()
    z = k.get("/api/law-brain/znanje", headers=H(ko)).json()
    assert z["memorija_kancelarije"]["stavke"] == [] and z["memorija_kancelarije"]["veze"] == []
    assert "Traži tabelu rokova" not in json.dumps(z, ensure_ascii=False)


def test_promena_clanstva_vazi_od_sledeceg_zahteva(svet):
    napravi, _ = svet
    k, b = napravi()
    pre = k.get("/api/law-brain/znanje", headers=H("B")).json()
    assert pre["memorija_kancelarije"]["stavke"]
    next(c for c in b.tabele["kancelarija_clanovi"] if c["user_id"] == "uid-B")["status"] = "REMOVED"
    posle = k.get("/api/law-brain/znanje", headers=H("B")).json()
    assert posle["memorija_kancelarije"]["stavke"] == [] and posle["memorija_kancelarije"]["kancelarija"] is False


def test_delegiranje_otvara_samo_delegirani_predmet_i_opoziv_ga_zatvara(svet):
    napravi, _ = svet
    k, b = napravi()
    b.tabele["predmet_delegiranja"].append({"predmet_id": PA_OLD, "na_user_id": "uid-B", "status": "aktivno"})
    d = k.get(f"/api/law-brain/predmeti/{PB_CUR}", headers=H("B")).json()
    assert [s["predmet_id"] for s in d["similar_cases"]["stavke"]] == [PA_OLD]
    assert [a["source_ref"]["id"] for a in d["verified_artifacts"]["stavke"]] == ["s-tajni"]
    b.tabele["predmet_delegiranja"][0]["status"] = "opozvano"
    d = k.get(f"/api/law-brain/predmeti/{PB_CUR}", headers=H("B")).json()
    assert d["similar_cases"]["stavke"] == [] and d["verified_artifacts"]["stavke"] == []


def test_greske_ne_odaju_postojanje(svet):
    napravi, _ = svet
    k, _ = napravi()
    for put in ("/api/law-brain/predmeti/{}", "/api/law-brain/predmeti/{}/sinteza"):
        a = (k.get if "sinteza" not in put else k.post)(put.format(PA_OLD), headers=H("B"))
        n = (k.get if "sinteza" not in put else k.post)(put.format(NEPOSTOJI), headers=H("B"))
        assert (a.status_code, a.content) == (n.status_code, n.content)


def test_podmetnut_tudj_rad_na_predmetu_se_nikome_ne_prikazuje(svet):
    napravi, _ = svet
    k, _ = napravi()
    for ko, put in (("A", f"/api/law-brain/predmeti/{PA_CUR}"), ("A", "/api/law-brain/znanje"), ("C", "/api/law-brain/znanje")):
        assert "Podmetnut" not in k.get(put, headers=H(ko)).text, (ko, put)
