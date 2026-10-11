"""NS006 Task 4 — graf dokaza (shared/evidence_graph.py) kroz `GET /api/predmeti/{id}/genome-v2`.

Tvrdnje nastaju STVARNIM putevima: ljudska kroz `POST /api/evidence/predmeti/{id}/dokaz`, a tvrdnje
modela kroz `routers/evidence.py::klasifikuj_i_sacuvaj` (model zamenjen fiksnim odgovorom — bez
poziva). V2 kontradikcija je upisana u tabele 119 onako kako ih ostavlja RPC.

Dokazuje:
  • ljudska tvrdnja ≠ tvrdnja modela (migracija 135: `izvor_tvrdnje`), i bez migracije 135
    ljudska se i dalje prepoznaje, a ništa se ne izmišlja;
  • tvrdnja pronađena u dokumentu → SOURCE_FACT sa lokacijom; nepronađena → AI_ANALYSIS, bez lokacije;
  • pravni element, potpora, protivrečnost po tvrdnji (iz V2), ili eksplicitno NEPOZNATO;
  • pala klasifikacija dokumenta ostaje NEUSPESNA (nikad „ostalo" kao uspeh);
  • čitanje ne upisuje NIŠTA; B ne vidi A (404 identičan nepostojećem predmetu).
"""
import json

import pytest

from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
D1, D2, D3 = "d1000000-0000-4000-8000-000000000001", "d2000000-0000-4000-8000-000000000002", "d3000000-0000-4000-8000-000000000003"
TEKST_D1 = ("REŠENJE O OTKAZU UGOVORA O RADU. Radni odnos zaposlenog Marka Petrovića prestaje "
            "dana 15.03.2025. godine zbog povrede radne obaveze. Rešenje je uručeno 17.03.2025.")
NEPOSTOJECI = "99999999-9999-4999-8999-999999999999"


def _tabele():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv ABC DOO", "tip": "radno",
                      "status": "aktivan", "tuzilac": "Marko Petrović", "tuzeni": "ABC DOO", "case_dna": {}}],
        "predmet_dokumenti": [
            {"id": D1, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "resenje.pdf", "redni_broj": 1,
             "tekst_sadrzaj": TEKST_D1},
            {"id": D2, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "zalba.pdf", "redni_broj": 2,
             "tip_dokaza": "ostalo", "klasifikovan_at": "2026-10-01T10:00:00+00:00",
             "ai_tags": json.dumps({"_klasifikacija_greska": True})},
            {"id": D3, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "nov.pdf", "redni_broj": 3},
        ],
        "predmet_dokazi": [], "predmet_genome_history": [],
        "predmet_issues": [], "predmet_contradictions": [], "predmet_contradiction_claims": [], "events": [],
    }


@pytest.fixture
def okruzenje(monkeypatch):
    k, baza = pripremi(monkeypatch, _tabele())
    import routers.evidence as ev
    monkeypatch.setattr(ev, "_klasifikuj_dokument", lambda naziv, tekst: {
        "tip_dokaza": "sudska_odluka", "pravni_elementi": ["prestanak radnog odnosa", "uručenje"],
        "ai_tags": {},
        "kljucne_cinjenice": ["Radni odnos zaposlenog Marka Petrovića prestaje dana 15.03.2025. godine zbog povrede radne obaveze.",
                              "Poslodavac je zaposlenom isplatio otpremninu u celosti."]})
    yield k, baza
    ocisti()


def _napuni(k, baza):
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Klijent tvrdi da rešenje nije primio lično.",
                                                          "pravni_element": "Uručenje"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    from routers.evidence import klasifikuj_i_sacuvaj
    klasifikuj_i_sacuvaj(PA, D1, "resenje.pdf", TEKST_D1, "uid-A")
    def _jedan(pocetak):
        nadjeni = [d for d in baza.tabele["predmet_dokazi"] if d["tvrdnja"].startswith(pocetak)]
        assert len(nadjeni) == 1, (pocetak, [d["tvrdnja"] for d in baza.tabele["predmet_dokazi"]])
        return nadjeni[0]
    covek = _jedan("Klijent tvrdi")
    lociran = _jedan("Radni odnos")
    nelociran = _jedan("Poslodavac je")
    # V2 kontradikcija kakvu ostavlja RPC 120/121 (issue + contradiction + 2 člana)
    baza.tabele["predmet_issues"].append({"id": "i1", "predmet_id": PA, "user_id": "uid-A", "label": "uručenje rešenja", "status": "DISCOVERED"})
    baza.tabele["predmet_contradictions"].append({"id": "k1", "issue_id": "i1", "relation_type": "cinjenica_cinjenica", "state": "OPEN", "tezina": "vazna"})
    for c in (covek, lociran):
        baza.tabele["predmet_contradiction_claims"].append({"contradiction_id": "k1", "dokaz_id": c["id"], "removed_at": None})
    return covek, lociran, nelociran


def _graf(k, kor="A", pid=PA):
    return k.get(f"/api/predmeti/{pid}/genome-v2", headers=zaglavlje(kor))


def test_graf_odgovara_na_pitanja_o_svakoj_tvrdnji(okruzenje):
    k, baza = okruzenje
    covek, lociran, nelociran = _napuni(k, baza)
    assert covek["izvor_tvrdnje"] == "covek" and lociran["izvor_tvrdnje"] == nelociran["izvor_tvrdnje"] == "ai_klasifikacija"
    pre = len(baza.dnevnik)
    r = _graf(k)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    pisanja = [z for z in baza.dnevnik[pre:] if z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")]
    assert pisanja == [], f"čitanje ne sme da piše: {pisanja}"
    g = r.json()["dokazi"]
    t = {s["id"]: s for s in g["tvrdnje"]}
    assert t[covek["id"]]["poreklo"] == "HUMAN_CONFIRMED" and t[covek["id"]]["potpora"] == "BEZ_POTPORE"
    assert t[lociran["id"]]["poreklo"] == "SOURCE_FACT" and t[lociran["id"]]["potpora"] == "LOCIRANA_U_DOKUMENTU"
    assert t[lociran["id"]]["lokacija"]["dokument_id"] == D1 and t[lociran["id"]]["lokacija"]["start"] is not None
    assert t[nelociran["id"]]["poreklo"] == "AI_ANALYSIS" and t[nelociran["id"]]["lokacija"] is None
    assert t[nelociran["id"]]["potpora"] == "DOKUMENT_BEZ_LOKACIJE"
    assert t[covek["id"]]["pravni_element"] == "Uručenje"
    assert t[covek["id"]]["protivrecnosti"] == ["k1"] and t[lociran["id"]]["protivrecnosti"] == ["k1"]
    assert t[nelociran["id"]]["protivrecnosti"] == []
    assert {"od": min(covek["id"], lociran["id"]), "do": max(covek["id"], lociran["id"]),
            "vrsta": "protivrecnost", "kontradikcija_id": "k1"} in g["veze"]
    el = {e["kljuc"]: e for e in g["pravni_elementi"]}
    assert set(el["element:uručenje"]["tvrdnje"]) >= {covek["id"]}
    s = g["sazetak"]
    assert s["po_poreklu"]["HUMAN_CONFIRMED"] == 1 and s["po_poreklu"]["SOURCE_FACT"] == 1 and s["po_poreklu"]["AI_ANALYSIS"] == 1
    assert s["u_protivrecnosti"] == 2 and s["bez_potpore"] == 1


def test_pala_klasifikacija_ostaje_neuspeh(okruzenje):
    k, baza = okruzenje
    _napuni(k, baza)
    dok = {d["id"]: d for d in _graf(k).json()["dokazi"]["dokumenti"]}
    assert dok[D2]["klasifikacija"] == {"stanje": "NEUSPESNA", "tip": None}, "„ostalo“ posle pada nije rezultat"
    assert dok[D3]["klasifikacija"] == {"stanje": "NIJE_KLASIFIKOVAN", "tip": None}
    assert dok[D1]["klasifikacija"] == {"stanje": "USPESNA", "tip": "sudska_odluka"}
    assert _graf(k).json()["dokazi"]["sazetak"]["neuspesnih_klasifikacija"] == 1


def test_bez_migracije_135_nista_se_ne_izmislja(okruzenje):
    k, baza = okruzenje
    baza.nepostojece_kolone["predmet_dokazi"] = {"izvor_tvrdnje"}
    covek, lociran, nelociran = _napuni(k, baza)
    assert "izvor_tvrdnje" not in covek, "pisac izostavlja kolonu koje nema"
    r = _graf(k)
    assert r.status_code == 200, r.text
    t = {s["id"]: s for s in r.json()["dokazi"]["tvrdnje"]}
    assert t[covek["id"]]["poreklo"] == "UNKNOWN", "bez zapisa o autoru i bez procene snage: nepoznato, ne „ljudsko“"
    assert t[lociran["id"]]["poreklo"] == "SOURCE_FACT", "pronađena u tekstu dokumenta i bez kolone"
    assert t[nelociran["id"]]["poreklo"] == "UNKNOWN"
    r2 = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Sa sopstvenom procenom.", "snaga": "jaka"},
                headers=zaglavlje("A"))
    t2 = {s["id"]: s for s in _graf(k).json()["dokazi"]["tvrdnje"]}
    assert t2[r2.json()["id"]]["poreklo"] == "HUMAN_CONFIRMED", "izvor_snage=covek dokazuje ljudski unos i bez 135"


def _pokusaji_upisa(baza):
    return [z for z in baza.dnevnik if z["tabela"] == "predmet_dokazi" and z["radnja"] == "insert"]


def test_pisac_bez_135_degradira_tacno_jedan_stepen(okruzenje):
    k, baza = okruzenje
    baza.nepostojece_kolone["predmet_dokazi"] = {"izvor_tvrdnje"}
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Tvrdnja.", "snaga": "jaka"}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert len(_pokusaji_upisa(baza)) == 2, "jedan neuspeh (135), jedan uspeh"
    red = baza.tabele["predmet_dokazi"][0]
    assert "izvor_tvrdnje" not in red and red["izvor_snage"] == "covek" and red["identitet"] and red["nacin_pronalaska"]


def test_pisac_bez_118_zadrzava_autora(okruzenje):
    k, baza = okruzenje
    baza.nepostojece_kolone["predmet_dokazi"] = {"izvor_snage"}
    k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Tvrdnja."}, headers=zaglavlje("A"))
    assert len(_pokusaji_upisa(baza)) == 2
    red = baza.tabele["predmet_dokazi"][0]
    assert red["izvor_tvrdnje"] == "covek" and "izvor_snage" not in red


def test_pisac_bez_118_i_135_i_dalje_upisuje(okruzenje):
    k, baza = okruzenje
    baza.nepostojece_kolone["predmet_dokazi"] = {"izvor_snage", "izvor_tvrdnje"}
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Tvrdnja."}, headers=zaglavlje("A"))
    assert r.status_code == 200 and len(baza.tabele["predmet_dokazi"]) == 1
    red = baza.tabele["predmet_dokazi"][0]
    assert "izvor_tvrdnje" not in red and "izvor_snage" not in red


def test_nepoznate_kontradikcije_su_nepoznate_a_ne_prazne(okruzenje):
    k, baza = okruzenje
    _napuni(k, baza)
    baza.greske["predmet_issues"] = RuntimeError("tabela nedostupna (test)")
    g = _graf(k).json()
    assert all(s["protivrecnosti"] is None for s in g["dokazi"]["tvrdnje"])
    assert g["dokazi"]["sazetak"]["u_protivrecnosti"] is None
    assert g["metapodaci"]["izvori"]["kontradikcije"] == "GRESKA"
    del baza.greske["predmet_issues"]
    baza.tabele["predmet_contradictions"].clear()
    baza.tabele["predmeti"][0]["case_dna"] = {"verzija": 3, "kontradikcije": [{"opis": "x", "lokacija_1": "DOK-01"}]}
    g2 = _graf(k).json()["dokazi"]
    assert all(s["protivrecnosti"] is None for s in g2["tvrdnje"]), "samo legacy kontradikcije bez veze na tvrdnje → nepoznato"
    assert "bez trajne veze" in g2["protivrecnosti_razlog"]


def test_pao_izvor_tvrdnji_nije_prazan_graf(okruzenje):
    k, baza = okruzenje
    _napuni(k, baza)
    baza.greske["predmet_dokazi"] = RuntimeError("tvrdnje nedostupne (test)")
    g = _graf(k).json()
    assert g["dokazi"]["stanje"] == "DEGRADED" and g["dokazi"]["sazetak"] is None
    assert g["cinjenice"]["stanje"] == "DEGRADED"


def test_b_ne_vidi_a_i_nema_orakla_postojanja(okruzenje):
    k, baza = okruzenje
    _napuni(k, baza)
    tudji = _graf(k, kor="B")
    nepostojeci = _graf(k, kor="B", pid=NEPOSTOJECI)
    assert tudji.status_code == nepostojeci.status_code == 404
    assert tudji.content == nepostojeci.content, "tuđ predmet i nepostojeći predmet moraju izgledati isto"
    for tajna in ("Petrović", "resenje.pdf", "Uručenje", D1):
        assert tajna not in tudji.text
    assert _graf(k, kor="C").status_code == 404
