"""NS006 Task 3 — profesionalni ugovor živog predmeta (shared/genome_contract.py).

Prihvatni kriterijumi iz mandata:
  • isti izvorni redovi → isti ugovor (i pri drugačijem redosledu redova iz baze);
  • nepoznata DOK referenca → nikad se ne veže za drugi dokument;
  • nepoznata CLAIM oznaka → nikad ne postaje pouzdana kontradikcija (ugovor je ne prenosi);
  • nedostajući izvor → eksplicitna nesigurnost, nikad prazno;
  • stari potrošači nepromenjeni (ulaz se ne menja; /case-dna ruta nije dirana);
  • 3A: neispravni datumi / vrednosti van skupa se obaraju i beleže;
  • 3B: nijedan pravni osnov iz modela nije „potvrđen";
  • 3C: svaka brojčana vrednost ima klasu; nijedna nije verovatnoća ishoda.
"""
import copy
import json
import random

import pytest

from shared import genome_contract as gc

PID = "11111111-1111-4111-8111-11111111111a"
D1, D2, D3 = "d1000000-0000-4000-8000-000000000001", "d2000000-0000-4000-8000-000000000002", "d3000000-0000-4000-8000-000000000003"
TUDJI_DOK = "dddddddd-0000-4000-8000-0000000000ff"

PREDMET = {"id": PID, "naziv": "Petrović protiv ABC DOO", "tip": "radno", "status": "aktivan",
           "tuzilac": "Marko Petrović", "tuzeni": "ABC DOO Beograd"}
DOKUMENTI = [
    {"id": D1, "naziv_fajla": "resenje_o_otkazu.pdf", "redni_broj": 1, "tip_dokaza": "sudska_odluka"},
    {"id": D2, "naziv_fajla": "ugovor_o_radu.pdf", "redni_broj": 2, "tip_dokaza": "ugovor"},
    {"id": D3, "naziv_fajla": "platni_listici.pdf", "redni_broj": 3, "tip_dokaza": "finansijska_dokumentacija"},
]
DOKAZI = [
    {"id": "c1000000-0000-4000-8000-000000000001", "predmet_id": PID, "dokument_id": D1,
     "tvrdnja": "Radni odnos je prestao 15.03.2025. rešenjem poslodavca.", "kategorija": "cinjenica",
     "nacin_pronalaska": "egzaktan", "start_offset": 120, "end_offset": 175, "stranica": 1, "izvor_snage": "dc005", "snaga": "jaka"},
    {"id": "c2000000-0000-4000-8000-000000000002", "predmet_id": PID, "dokument_id": None,
     "tvrdnja": "Klijent tvrdi da otkaz nije uručen lično.", "kategorija": "cinjenica",
     "nacin_pronalaska": "nije_pronadjen", "izvor_snage": "covek", "snaga": "srednja"},
    {"id": "c3000000-0000-4000-8000-000000000003", "predmet_id": PID, "dokument_id": D3,
     "tvrdnja": "Neisplaćena zarada iznosi 480.000,00 RSD.", "kategorija": "dokaz",
     "nacin_pronalaska": "nije_pronadjen", "izvor_snage": "podrazumevano", "izvor_tvrdnje": "ai_klasifikacija"},
    {"id": "c4000000-0000-4000-8000-000000000004", "predmet_id": PID, "dokument_id": None,
     "tvrdnja": "Stara tvrdnja bez zabeleženog porekla.", "kategorija": "ostalo", "izvor_snage": None},
]
GENOME = {
    "verzija": 18,
    "pravna_teorija": {"pravni_identitet": "Radni spor — nezakonit otkaz — Petrović vs. ABC DOO",
                       "sustina_spora": "Da li je otkaz zakonito uručen.",
                       "osnov_odgovornosti": "Nezakonit prestanak radnog odnosa.",
                       "relevantni_zakoni": ["Zakon o radu čl. 179", "ZOO čl. 9999", "Pravilnik o nečemu čl. 3"]},
    "stranke": [{"uloga": "tuzilac", "ime": "Marko Petrović"}, {"uloga": "sudija-porotnik", "ime": "N.N."},
                {"uloga": "tuzeni"}],
    "datumi_kljucni": [{"opis": "Prestanak radnog odnosa", "datum": "2025-03-15", "znacaj": "kriticno"},
                       {"opis": "Opomena", "datum": "15. mart 2025", "znacaj": "veoma bitno"}],
    "kontradikcije": [{"issue_label": "datum uručenja", "claim_refs": ["CLAIM-001", "CLAIM-999"],
                       "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-07 str.1", "opis": "Datumi se razlikuju",
                       "dokument_id_1": D1, "dokument_id_2": TUDJI_DOK}],
    "najslabija_tacka": {"rizik": "Nema dokaza o uručenju", "kriticnost": 77, "lokacija": "DOK-01 str.x"},
    "strategija": {"primarni_cilj": "Poništaj rešenja o otkazu", "scenariji": [{"uslov": "Ako sud", "odgovor": "Onda"}]},
    "nedostaje": [{"dokument": "Dostavnica", "hitnost": "kriticno"}, {"dokument": "Svedok", "hitnost": "?"}],
    "snaga_predmeta_procent": 64, "heatmap": {"dokazi": 60, "rokovi": 40},
    "dokazi_rang": [{"naziv": "resenje_o_otkazu.pdf", "snaga_score": 90, "dokument_id": D1}],
    "_analiza_osnov": {"dokumenata": 3, "cinjenica": 4, "pravnih_elemenata": 1},
    "_genome_docs_count": 3, "_genome_docs_preskoceno": 0, "_dokumenti_bez_teksta": [],
    "_verifikacija": {"odluka": "approve_with_warning", "hard_flags": [], "soft_flags": [{}]},
    "genome_kompletnost": "srednja",
}


def _ugovor(**k):
    return gc.sastavi(predmet=k.get("predmet", PREDMET), case_dna=k.get("case_dna", GENOME),
                      dokumenti=k.get("dokumenti", DOKUMENTI), dokazi=k.get("dokazi", DOKAZI),
                      izvori=k.get("izvori"), osvezeno="2026-10-09T10:00:00+00:00")


def test_isti_izvori_isti_ugovor_bez_obzira_na_redosled():
    a = _ugovor()
    for seme in range(5):
        r = random.Random(seme)
        dz, dk = copy.deepcopy(DOKAZI), copy.deepcopy(DOKUMENTI)
        r.shuffle(dz)
        r.shuffle(dk)
        assert json.dumps(_ugovor(dokazi=dz, dokumenti=dk), sort_keys=True) == json.dumps(a, sort_keys=True)
    assert [s["id"] for s in a["cinjenice"]["stavke"]] == sorted(d["id"] for d in DOKAZI)
    assert all(s["id_vrsta"] == "izvor" for s in a["cinjenice"]["stavke"])


def test_identitet_ai_stavke_je_sadrzaj_i_tako_se_i_naziva():
    a, b = _ugovor(), _ugovor()
    for sekcija in ("hronologija", "strategija"):
        assert [s["id"] for s in a[sekcija]["stavke"]] == [s["id"] for s in b[sekcija]["stavke"]]
        assert all(s["id_vrsta"] == "sadrzaj" and s["id"].startswith("ai:") for s in a[sekcija]["stavke"])


def test_poreklo_tvrdnji():
    po_id = {s["id"]: s for s in _ugovor()["cinjenice"]["stavke"]}
    assert po_id["c1000000-0000-4000-8000-000000000001"]["poreklo"] == gc.SOURCE_FACT
    assert po_id["c1000000-0000-4000-8000-000000000001"]["lokacija"]["dokument_id"] == D1
    assert po_id["c2000000-0000-4000-8000-000000000002"]["poreklo"] == gc.HUMAN_CONFIRMED
    assert po_id["c3000000-0000-4000-8000-000000000003"]["poreklo"] == gc.AI_ANALYSIS
    assert po_id["c4000000-0000-4000-8000-000000000004"]["poreklo"] == gc.UNKNOWN
    # snaga se prikazuje SAMO kad je stvarno procenjena (čovek ili DC-005)
    assert po_id["c3000000-0000-4000-8000-000000000003"]["snaga"] is None
    assert po_id["c3000000-0000-4000-8000-000000000003"]["snaga_procenjena"] is False


def test_nepoznata_dok_referenca_se_ne_vezuje():
    a = _ugovor()
    nt = next(s for s in a["strategija"]["stavke"] if s["vrsta"] == "najslabija_tacka")
    assert nt["lokacija"]["dokument_id"] == D1 and nt["lokacija"]["strana_po_analizi"] is None, "str.x nije broj strane"
    raz = gc.Razresavac(DOKUMENTI)
    assert raz.lokacija("DOK-07 str.1", "t")["dokument_id"] is None
    assert raz.lokacija("DOK-02", "t")["dokument_id"] == D2
    assert raz.lokacija("ugovor_o_radu.pdf", "t")["dokument_id"] is None, "nikad po nazivu fajla"
    dupli = DOKUMENTI + [{"id": "d9", "naziv_fajla": "x.pdf", "redni_broj": 2}]
    assert gc.Razresavac(dupli).lokacija("DOK-02", "t")["dokument_id"] is None, "dva kandidata = nerazrešeno"
    assert raz.dokument_id(TUDJI_DOK, "t") is None
    assert len(raz.nerazreseno) == 3


def test_tudji_dokument_u_tvrdnji_se_obara():
    dz = copy.deepcopy(DOKAZI)
    dz[0]["dokument_id"] = TUDJI_DOK
    s = next(x for x in _ugovor(dokazi=dz)["cinjenice"]["stavke"] if x["id"] == dz[0]["id"])
    assert s["dokument_id"] is None and s["lokacija"] is None


def test_claim_oznake_iz_genome_ne_postaju_pouzdane():
    a = _ugovor()
    tekst = json.dumps(a, ensure_ascii=False)
    assert "CLAIM-001" not in tekst and "CLAIM-999" not in tekst, "efemerne oznake ne smeju u ugovor"
    assert "kontradikcije" not in a, "pouzdane kontradikcije dolaze samo iz V2 perzistencije (Task 5)"


def test_nedostajuci_genome_je_nesigurnost_a_ne_prazno():
    a = _ugovor(case_dna={})
    assert a["metapodaci"]["kompletnost"] == gc.NEPOZNATO and a["metapodaci"]["genome_verzija"] is None
    for s in ("pravna_pitanja", "hronologija", "strategija", "nedostaje"):
        assert a[s]["stanje"] == gc.NEPOZNATO, s
    assert any(n["vrsta"] == "genome_nije_izracunat" for n in a["nesigurnost"])
    assert a["cinjenice"]["stanje"] == gc.OK, "tvrdnje postoje nezavisno od analize"


def test_pao_izvor_nije_prazan():
    a = _ugovor(izvori={"dokazi": "GRESKA", "dokumenti": "GRESKA"})
    assert a["cinjenice"]["stanje"] == gc.DEGRADIRANO and a["cinjenice"]["stavke"] == []
    assert a["metapodaci"]["kompletnost"] == gc.DEGRADIRANO and a["metapodaci"]["dokumenata_u_predmetu"] is None
    assert {n.get("izvor") for n in a["nesigurnost"] if n["vrsta"] == "izvor_nedostupan"} == {"dokazi", "dokumenti"}
    b = _ugovor(izvori={"genome": "GRESKA"})
    assert b["metapodaci"]["genome_verzija"] is None and any(n["vrsta"] == "genome_nije_procitan" for n in b["nesigurnost"])
    c = _ugovor(case_dna={"greska": "timeout"})
    assert any(n["vrsta"] == "genome_greska" for n in c["nesigurnost"])


def test_stari_potrosaci_nepromenjeni_ulaz_se_ne_menja():
    g, dz, dk, p = (copy.deepcopy(x) for x in (GENOME, DOKAZI, DOKUMENTI, PREDMET))
    gc.sastavi(predmet=p, case_dna=g, dokumenti=dk, dokazi=dz)
    assert (g, dz, dk, p) == (GENOME, DOKAZI, DOKUMENTI, PREDMET)


def test_3a_neispravni_datumi_i_vrednosti_se_obaraju():
    a = _ugovor()
    datumi = {s["vrednost"]: s for s in a["hronologija"]["stavke"]}
    assert datumi["Prestanak radnog odnosa"]["datum"] == "2025-03-15" and datumi["Prestanak radnog odnosa"]["znacaj"] == "kriticno"
    assert datumi["Opomena"]["datum"] is None and datumi["Opomena"]["datum_neispravan"] is True
    assert datumi["Opomena"]["znacaj"] is None
    assert a["hronologija"]["neispravnih"] == 1
    uloge = {s["vrednost"]: s for s in a["stranke"]["stavke"] if s["poreklo"] == gc.AI_ANALYSIS}
    assert uloge["N.N."]["uloga"] is None and uloge["N.N."]["uloga_neispravna"] is True
    assert a["stranke"]["odbaceno"] == 1, "stranka bez imena se ne prikazuje"
    # analiza je samo ponovila tužioca koga je advokat uneo → jedna stavka, poreklo advokata, uz potvrdu analize
    mp = [s for s in a["stranke"]["stavke"] if s["vrednost"] == "Marko Petrović"]
    assert len(mp) == 1 and mp[0]["poreklo"] == gc.HUMAN_CONFIRMED and mp[0]["potvrdjeno_analizom"] is True, mp


def test_3a_stranka_sa_drugom_ulogom_ostaje_vidljiva():
    """Neslaganje (analiza kaže da je tužilac zapravo tuženi) se NE sakriva spajanjem."""
    import copy
    pr = dict(PREDMET)
    g = copy.deepcopy(GENOME)
    g["stranke"] = [{"uloga": "tuzeni", "ime": "Marko  Petrović."}]
    a = _ugovor(predmet=pr, case_dna=g)
    mp = [s for s in a["stranke"]["stavke"] if "Petrović" in s["vrednost"]]
    assert sorted(s["poreklo"] for s in mp) == sorted([gc.HUMAN_CONFIRMED, gc.AI_ANALYSIS]), mp
    ned = {s["vrednost"]: s for s in a["nedostaje"]["stavke"]}
    assert ned["Svedok"]["hitnost"] is None


def test_3a_neispravna_savetodavna_sekcija_ne_obara_ugovor():
    g = copy.deepcopy(GENOME)
    g["pravna_teorija"] = "nije objekat"
    g["strategija"] = ["lista umesto objekta"]
    a = _ugovor(case_dna=g)
    assert a["pravna_pitanja"]["stanje"] == gc.NEISPRAVNO
    assert a["cinjenice"]["stanje"] == gc.OK and a["hronologija"]["stanje"] == gc.OK


def test_3b_nijedan_pravni_osnov_nije_potvrdjen():
    pp = _ugovor()["pravna_pitanja"]
    assert pp["potvrdjeni_pravni_izvori"] == [] and pp["potvrda_izvora"]["stanje"] == "NIJE_DOSTUPNA"
    osnovi = {s["vrednost"]: s for s in pp["pravni_osnovi_neprovereni"]}
    assert all(s["poverenje"] == gc.UNVERIFIED_AI_ANALYSIS and s["poreklo"] == gc.AI_ANALYSIS for s in osnovi.values())
    assert osnovi["Zakon o radu čl. 179"]["naziv_zakona_prepoznat"] is True
    assert osnovi["ZOO čl. 9999"]["broj_clana_moguc"] is False
    assert osnovi["Pravilnik o nečemu čl. 3"]["naziv_zakona_prepoznat"] is False
    assert all(s["poreklo"] == gc.AI_ANALYSIS for s in pp["stavke"])


def test_3c_klasifikacija_brojeva():
    m = {x["kljuc"]: x for x in _ugovor()["metrike"]}
    assert m["snaga_predmeta_procent"]["klasa"] == gc.MIXED
    assert m["heatmap.dokazi"]["klasa"] == gc.MODEL_DERIVED
    assert m["najslabija_tacka.kriticnost"]["klasa"] == gc.MODEL_DERIVED
    assert m["dokazi_rang[0].snaga_score"]["klasa"] == gc.MODEL_DERIVED
    assert m["_analiza_osnov.cinjenica"]["klasa"] == gc.DETERMINISTIC
    for x in m.values():
        assert "NIJE verovatnoća ishoda" in x["napomena"]
        assert x["naziv"] and x["naziv"] != x["kljuc"] and x["naziv"][0].isupper() and " " in x["naziv"], x   # ljudska oznaka, ne sirov ključ
    tekst = json.dumps(_ugovor(), ensure_ascii=False).lower()
    for zabranjeno in ("verovatnoća uspeha", "šansa za uspeh", "probability of winning", "predviđanje presude"):
        assert zabranjeno not in tekst


def test_ai_nikad_nije_cinjenica_iz_izvora():
    a = _ugovor()
    for sekcija in ("pravna_pitanja", "hronologija", "strategija", "nedostaje"):
        assert all(s["poreklo"] == gc.AI_ANALYSIS for s in a[sekcija]["stavke"]), sekcija
    assert a["identitet"]["pravni_identitet"]["poreklo"] == gc.AI_ANALYSIS
