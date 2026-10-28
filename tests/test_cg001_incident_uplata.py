# -*- coding: utf-8 -*-
"""CG001 — produkcioni incident „TEST — Bojan E2E / Evidencija uplate“ (28.10.2026), reprodukovan na istim
identifikatorima (sintetički predmet, izmišljeni iznosi — nema klijentskih podataka).

Lanac (dokazan čitanjem produkcije, samo čitanje):
  21:58:00/08  DOK-01 + 7 tvrdnji (A=40.000, B=ostatak 80.000, …)
  21:58:09     DOK-02 evidentiran — tekst postoji, tvrdnje JOŠ NE
  21:58:21     Genome v1: 2 dokumenta u analizi, katalog = 7 tvrdnji SAMO iz DOK-01. Model opisuje 40.000 (DOK-01)
               naspram 30.000 (DOK-02), a bira CLAIM-004 (A) + CLAIM-002 (B) — obe iz DOK-01. Materijalizacija je to
               prihvatila (reference postoje) → V2 sporna tačka {A,B} OPEN.
  21:58:33     8 tvrdnji iz DOK-02 (C=30.000, D=„TEST 01 navodi 40.000, TEST 02 30.000“)
  21:58:45     Genome v2 {A,C,D} — domen: preklapanje bez sadržavanja → REVIEW_REQUIRED → NIJE upisano (ispravno),
               ali se taj ishod nigde ne vidi: analiza prikazuje {A,B} kao aktivnu, istorija „nova + više se ne opaža“,
               radnja „Razrešiti protivrečnost“ nad {A,B}.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.claim_catalog import napravi_katalog
from shared.contradiction_materializer import ODBIJEN_IZVORI, materializuj
from shared.genome_contract import promene_genome, sastavi_kontradikcije
from shared.issue_v2 import ODLUKA_PREGLED, nepotvrdjen_kontinuitet, razresi_paket

P = "3267fab3-1319-47f9-bcde-5889174ed0f4"
D1 = "08e6c642-7c82-4a50-a863-c62797a6a0fd"
D2 = "05b0b81a-f54b-4859-938a-1db1acbc0527"
A = "45adcf3f-ca2d-4085-a215-0404c015f881"   # 40.000 (DOK-01)
B = "0b825558-9ae7-418a-846e-0d1eb451da49"   # ostatak 80.000 (DOK-01)
C = "119067f5-d635-4ca7-92ac-865bc5ffe0ce"   # 30.000 (DOK-02)
D = "1663a433-71cf-4218-92da-6b8c31e278c2"   # razlika 40.000/30.000 (DOK-02)
ISSUE = "9cc91156-d8a5-4b4f-9f65-ab82eaea5b4b"
KONTR = "744415d7-cc6d-44f9-83b2-154a3532855e"

_DOK01 = [("0163dd29-0000-4000-8000-000000000001", "Dogovorena demonstraciona usluga od 120.000 RSD."),
          (A, "Test klijent navodi delimičnu uplatu od 40.000 RSD."),
          (B, "Prema toj izjavi, preostali iznos je 80.000 RSD."),
          ("6208afa2-0000-4000-8000-000000000001", "To je navod stranke, a ne potvrđena činjenica."),
          ("e6a0c035-0000-4000-8000-000000000001", "Nijedan datum ne predstavlja pravni rok."),
          ("1b6e3b93-0000-4000-8000-000000000001", "Nije stvarni ugovor ni račun."),
          ("c166703d-0000-4000-8000-000000000001", "Iznosi su izmišljeni.")]
_DOK02 = [("ab9fb533-0000-4000-8000-000000000002", "Demonstraciona vrednost usluge: 120.000 RSD."),
          ("b9f6f9a1-0000-4000-8000-000000000002", "Datum zamišljene uplate: 15. oktobar 2026."),
          (C, "Interna evidencija prikazuje uplatu od 30.000 RSD."),
          ("54b5cb12-0000-4000-8000-000000000002", "Preostali iznos prema ovoj evidenciji: 90.000 RSD."),
          (D, "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD."),
          ("9a309f20-0000-4000-8000-000000000002", "Nijedna stavka nije stvarni dokaz."),
          ("a540360c-0000-4000-8000-000000000002", "Nije stvarni ugovor ni račun."),
          ("d5f06ab9-0000-4000-8000-000000000002", "Iznosi su izmišljeni.")]


def _red(cid, tekst, dok, **dod):
    return {"id": cid, "predmet_id": P, "user_id": "uid-T", "dokument_id": dok, "tvrdnja": tekst,
            "kategorija": "cinjenica", "pravni_element": None, "deleted_at": None, "izvor_tvrdnje": "ai_klasifikacija", **dod}


def dokazi_v1():
    return [_red(i, t, D1) for i, t in _DOK01]


def dokazi_v2():
    return dokazi_v1() + [_red(i, t, D2) for i, t in _DOK02]


def _oznake(katalog, *ids):
    inv = {v: k for k, v in katalog.items()}
    return [inv[i] for i in ids]


def _sirova(refs, **dod):
    return {"opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.",
            "issue_label": "Razlika u iznosu uplate", "relation_type": "cinjenica_cinjenica", "claim_refs": refs,
            "lokacija_1": "DOK-01", "lokacija_2": "DOK-02", "dokument_id_1": D1, "dokument_id_2": D2, **dod}


def _mat(dokazi, ids, **dod):
    katalog = napravi_katalog(dokazi, P)
    return materializuj([_sirova(_oznake(katalog, *ids), **dod)], katalog, P, {d["id"]: d for d in dokazi})


# ═══ TASK 1 — granica poverenja: tvrdnje moraju pokrivati navedene izvore ═══

def test_incident_v1_par_iz_jednog_dokumenta_ne_postaje_v2_veza():
    """Tačno produkcioni ulaz v1: katalog bez ijedne tvrdnje DOK-02, izbor A+B, opis i izvori DOK-01 ↔ DOK-02."""
    katalog = napravi_katalog(dokazi_v1(), P)
    assert _oznake(katalog, A, B) == ["CLAIM-004", "CLAIM-002"]          # iste oznake kao u produkciji
    m = _mat(dokazi_v1(), (A, B))
    assert m["kandidati"] == []
    assert [o["razlog"] for o in m["odbijeni"]] == [ODBIJEN_IZVORI]
    assert m["odbijeni"][0]["opis"]                                        # odbijen kandidat nosi opis — vidljiv, ne tih


def test_incident_v2_acd_pokriva_oba_izvora_i_prolazi():
    m = _mat(dokazi_v2(), (A, C, D))
    assert len(m["kandidati"]) == 1 and set(m["kandidati"][0]["claim_refs"]) == {A, C, D}


def test_konflikt_u_istom_dokumentu_ostaje_dozvoljen():
    m = _mat(dokazi_v1(), (A, B), lokacija_2="DOK-01", dokument_id_2=D1)
    assert len(m["kandidati"]) == 1 and m["odbijeni"] == []


def test_dve_sporne_tacke_izmedju_ista_dva_dokumenta_ostaju_dve():
    dz = dokazi_v2()
    katalog = napravi_katalog(dz, P)
    m = materializuj([_sirova(_oznake(katalog, A, C)),
                      _sirova(_oznake(katalog, B, "54b5cb12-0000-4000-8000-000000000002"), issue_label="Preostali iznos")],
                     katalog, P, {d["id"]: d for d in dz})
    assert len(m["kandidati"]) == 2 and m["odbijeni"] == []
    rez = razresi_paket(m["kandidati"], P, {d["id"]: d for d in dz}, [])
    assert len({r["claim_set"] for r in rez}) == 2


def test_tri_konkurentne_tvrdnje_i_kontekstna_tvrdnja_prolaze():
    assert len(_mat(dokazi_v2(), (A, C, D))["kandidati"]) == 1
    assert len(_mat(dokazi_v2(), (A, C, "0163dd29-0000-4000-8000-000000000001"))["kandidati"]) == 1


@pytest.mark.parametrize("dod", [
    {"dokument_id_2": None},                     # lokacija nije razrešena → provera se ne izvodi (nema čime)
    {"dokument_id_1": None, "dokument_id_2": None},
    {"relation_type": "cinjenica_norma"},          # druga strana je norma, ne dokument
])
def test_bez_dva_razresena_dokumenta_pravilo_ne_odlucuje(dod):
    m = _mat(dokazi_v1(), (A, B), **dod)
    assert len(m["kandidati"]) == 1


def test_tvrdnja_bez_dokumenta_ne_obara_kandidata():
    """Tvrdnja koju je uneo advokat nema dokument — ne zna se da li je ona „druga strana“, pa se ne odbija."""
    dz = dokazi_v1() + [_red("f0000000-0000-4000-8000-00000000000f", "Klijent tvrdi 30.000 RSD.", None, izvor_tvrdnje="covek")]
    assert len(_mat(dz, (A, "f0000000-0000-4000-8000-00000000000f"))["kandidati"]) == 1


def test_redosled_obrade_ne_menja_odluku():
    dz = list(reversed(dokazi_v1()))
    assert _mat(dz, (A, B))["odbijeni"][0]["razlog"] == ODBIJEN_IZVORI
    assert len(_mat(list(reversed(dokazi_v2())), (A, C, D))["kandidati"]) == 1


def test_ponovljen_upload_tvrdnje_iz_kopije_a_navod_originala_se_odbija():
    """DOK-03 je kopija DOK-02 (drugi `predmet_dokumenti.id`). Navedeni izvor DOK-02 nema nijednu izabranu tvrdnju —
    veza se ne može dokazati, pa ne postaje V2 (vidljiva ostaje u analizi kao nepovezana)."""
    D3 = "0d300000-0000-4000-8000-000000000003"
    dz = dokazi_v1() + [_red("c3000000-0000-4000-8000-000000000003", "Interna evidencija prikazuje uplatu od 30.000 RSD.", D3)]
    m = _mat(dz, (A, "c3000000-0000-4000-8000-000000000003"))
    assert m["odbijeni"][0]["razlog"] == ODBIJEN_IZVORI


def test_tudja_i_obrisana_tvrdnja_i_dalje_padaju_kao_ranije():
    tudja = _red("e0000000-0000-4000-8000-00000000000e", "x", D2, predmet_id="drugi-predmet")
    dz = dokazi_v1()
    katalog = napravi_katalog(dz, P)
    katalog["CLAIM-099"] = tudja["id"]
    m = materializuj([_sirova([_oznake(katalog, A)[0], "CLAIM-099"])], katalog, P,
                     {**{d["id"]: d for d in dz}, tudja["id"]: tudja})
    assert m["odbijeni"][0]["razlog"] == "UNRESOLVED_CLAIM_REF"


def test_producer_ne_upisuje_trajne_claim_ids_za_nedoslednu_vezu():
    """`case_dna.kontradikcije[].claim_ids` (poređenje verzija, prikaz) i V2 materijalizacija moraju reći isto."""
    import routers.case_dna as cd
    katalog = napravi_katalog(dokazi_v1(), P)
    sirovo = {"kontradikcije": [{k: v for k, v in _sirova(_oznake(katalog, A, B)).items()
                                 if k not in ("dokument_id_1", "dokument_id_2")}], "snaga_faktori": []}
    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content=json.dumps(sirovo)))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    docs = [{"id": D1, "redni_broj": 1, "naziv_fajla": "Vindex_TEST_01_Beleska_klijenta.pdf", "tekst_sadrzaj": "40.000"},
            {"id": D2, "redni_broj": 2, "naziv_fajla": "Vindex_TEST_02_Interna_evidencija.pdf", "tekst_sadrzaj": "30.000"}]
    with patch("openai.AsyncOpenAI", return_value=klijent):
        g = asyncio.run(cd._extract_genome(docs, dokazi=dokazi_v1(), predmet_id=P))
    k = g["kontradikcije"][0]
    assert (k["dokument_id_1"], k["dokument_id_2"]) == (D1, D2)
    assert k["claim_ids"] is None


def test_kontekst_tvrdnji_nosi_dokument():
    """Bez `dokument_id` u kontekstu provera izvora ne bi imala šta da uporedi (bila bi uvek „ne odlučuje“)."""
    import inspect
    import routers.case_dna as cd
    assert "dokument_id" in inspect.getsource(cd._fetch_dokazi_kontekst)


# ═══ TASK 2 — najnovije opažanje naspram sačuvane V2 veze ═══

def _v2(clanovi=(A, B), tezina="manja", cid=KONTR, issue=ISSUE, label="Razlika u iznosu uplate", state="OPEN"):
    return {"id": cid, "issue_id": issue, "issue_label": label, "issue_status": "DISCOVERED",
            "relation_type": "cinjenica_cinjenica", "state": state, "state_reason": None, "tezina": tezina,
            "created_at": "2026-10-28T21:58:21Z", "updated_at": "2026-10-28T21:58:21Z",
            "clanovi": [{"dokaz_id": c, "uklonjen": False, "razlog_uklanjanja": None} for c in sorted(clanovi)],
            "claim_ids": sorted(clanovi)}


def _genome(*stavke):
    return {"verzija": 2, "kontradikcije": [
        {"issue_label": lab, "relation_type": "cinjenica_cinjenica", "tezina": tez, "claim_ids": sorted(ids),
         "opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.",
         "lokacija_1": "DOK-01", "lokacija_2": "DOK-02", "dokument_id_1": D1, "dokument_id_2": D2}
        for lab, tez, ids in stavke]}


_DOKUMENTI = [{"id": D1, "naziv_fajla": "Vindex_TEST_01_Beleska_klijenta.pdf", "redni_broj": 1},
              {"id": D2, "naziv_fajla": "Vindex_TEST_02_Interna_evidencija.pdf", "redni_broj": 2}]


def _k(v2, genome, dokazi=None):
    return sastavi_kontradikcije(v2=v2, case_dna=genome, dokazi=dokazi_v2() if dokazi is None else dokazi,
                                 dokumenti=_DOKUMENTI, izvori={})


def test_incident_aktivna_veza_nosi_nepotvrdjen_kontinuitet_a_novije_opazanje_trazi_pregled():
    k = _k([_v2()], _genome(("Razlika u iznosu uplate", "kriticna", (A, C, D))))
    akt = k["aktivne"]
    assert len(akt) == 1 and akt[0]["id"] == KONTR
    assert akt[0]["kontinuitet"] == "NIJE_POTVRDJEN"
    assert {u["tvrdnja_id"] for u in akt[0]["ucesnici"]} == {A, B}         # sačuvano članstvo NETAKNUTO
    assert akt[0]["tezina"] == "manja"                                       # ni težina se ne prepisuje
    assert akt[0]["napomena"]
    assert len(k["za_pregled"]) == 1
    p = k["za_pregled"][0]
    assert p["stanje"] == "ZA_PREGLED" and p["kontinuitet"] == "NIJE_POTVRDJEN" and p["poreklo"] == "AI_ANALYSIS"
    assert {u["tvrdnja_id"] for u in p["ucesnici"]} == {A, C, D}
    assert p["dokumenti"] == sorted([D1, D2]) and p["tezina"] == "kriticna"
    assert p["povezane_aktivne"] == [KONTR]
    assert KONTR not in json.dumps(p["napomena"]) and ISSUE not in json.dumps(akt[0]["napomena"])  # bez UUID-a advokatu
    assert k["sazetak"]["za_pregled"] == 1 and k["sazetak"]["aktivnih"] == 1


@pytest.mark.parametrize("ids", [(A, B), (A, B, C), (A,)])
def test_dokazan_kontinuitet_ili_bez_spora_nema_oznake(ids):
    """Isti skup ili nadskup = nastavak (A008); jedna tvrdnja nije spor."""
    k = _k([_v2()], _genome(("Razlika u iznosu uplate", "manja", ids)))
    assert "kontinuitet" not in k["aktivne"][0] and k["za_pregled"] == []


def test_disjunktno_opazanje_ne_oznacava_aktivnu():
    k = _k([_v2()], _genome(("Razlika u iznosu uplate", "manja", (C, D))))
    assert "kontinuitet" not in k["aktivne"][0] and k["za_pregled"] == []


def test_dve_sporne_tacke_istog_naziva_oznacava_se_samo_ona_sa_preklapanjem():
    druga = _v2(clanovi=(C, "54b5cb12-0000-4000-8000-000000000002"), cid="k2", issue="i2")
    k = _k([_v2(), druga], _genome(("Razlika u iznosu uplate", "kriticna", (A, D, "ab9fb533-0000-4000-8000-000000000002"))))
    po_id = {x["id"]: x for x in k["aktivne"]}
    assert po_id[KONTR].get("kontinuitet") == "NIJE_POTVRDJEN" and "kontinuitet" not in po_id["k2"]


def test_zatvorena_kontradikcija_ne_ucestvuje_u_odluci():
    """Tema bez OTVORENE kontradikcije nije kandidat kontinuiteta (isto kao `_ucitaj_postojece_teme`)."""
    zatvorena = _v2(state="NOT_OBSERVED")
    druga = _v2(clanovi=(C, "54b5cb12-0000-4000-8000-000000000002"), cid="k2", issue="i2")
    k = _k([zatvorena, druga], _genome(("Razlika u iznosu uplate", "kriticna", (A, D))))
    assert k["za_pregled"] == [] and "kontinuitet" not in k["aktivne"][0]


def test_povucena_tvrdnja_nije_ucesnik_novijeg_opazanja():
    zive = [d for d in dokazi_v2() if d["id"] != D]
    k = _k([_v2()], _genome(("Razlika u iznosu uplate", "kriticna", (A, C, D))), dokazi=zive)
    assert {u["tvrdnja_id"] for u in k["za_pregled"][0]["ucesnici"]} == {A, C}


def test_tudja_tvrdnja_u_opazanju_nikad_nije_ucesnik():
    """`claim_ids` iz case_dna su opsegom predmeta pri nastanku; i da nisu, prikaz čita samo tvrdnje ovog predmeta i
    korisnika, pa tuđa tvrdnja ispada iz opažanja (ne prikazuje se i ne utiče na odluku)."""
    tudja = "77777777-0000-4000-8000-000000000077"
    k = _k([_v2()], _genome(("Razlika u iznosu uplate", "kriticna", (A, C, tudja))))
    assert {u["tvrdnja_id"] for u in k["za_pregled"][0]["ucesnici"]} == {A, C}
    assert tudja not in json.dumps(k)


def test_neprocitane_tvrdnje_ne_gase_oznaku():
    """Pad čitanja tvrdnji ne sme izgledati kao „nema nerazrešenog“ (lanac je to našao: prazna lista = sve povučeno)."""
    k = sastavi_kontradikcije(v2=[_v2()], case_dna=_genome(("Razlika u iznosu uplate", "kriticna", (A, C, D))),
                              dokazi=[], dokumenti=_DOKUMENTI, izvori={"dokazi": "GRESKA"})
    assert k["aktivne"][0]["kontinuitet"] == "NIJE_POTVRDJEN" and len(k["za_pregled"]) == 1


def test_opazanje_bez_trajnih_veza_ili_bez_genome_ne_izmislja_oznaku():
    for g in ({"kontradikcije": [{"issue_label": "x", "relation_type": "cinjenica_cinjenica", "claim_ids": None}]},
              None, {"greska": "pad"}):
        k = _k([_v2()], g)
        assert "kontinuitet" not in k["aktivne"][0] and k["za_pregled"] == []


def test_necitljive_kontradikcije_ostaju_degradirane():
    k = sastavi_kontradikcije(v2=None, case_dna=_genome(("x", "manja", (A, C, D))), dokazi=dokazi_v2(),
                              dokumenti=_DOKUMENTI, izvori={})
    assert k["stanje"] == "DEGRADED" and k["za_pregled"] == []


def test_domen_je_jedini_vlasnik_odluke():
    teme = [{"issue_id": ISSUE, "status": "DISCOVERED", "claim_set": frozenset({A, B})}]
    r = nepotvrdjen_kontinuitet([frozenset({A, C, D})], teme)
    assert r == [{"indeks": 0, "kandidati": [ISSUE]}]
    assert razresi_paket([{"claim_refs": [A, C, D], "relation_type": "cinjenica_cinjenica"}], P,
                         {d["id"]: d for d in dokazi_v2()}, teme)[0]["odluka"] == ODLUKA_PREGLED


# ═══ TASK 3A — istorija ═══

def _snimak(*stavke):
    return {"verzija": 1, "kontradikcije": [{"issue_label": lab, "relation_type": rel, "claim_ids": sorted(ids)}
                                            for lab, rel, ids in stavke]}


def _promene(stari, novi):
    return [(p["vrsta"], p["opis"]) for p in promene_genome(stari, novi)["promene"] if p["vrsta"].startswith("kontradikcija")]


CC = "cinjenica_cinjenica"


def test_incident_istorija_ne_prijavljuje_nestanak_nego_nepotvrdjen_kontinuitet():
    pr = _promene(_snimak(("Razlika u iznosu uplate", CC, (A, B))), _snimak(("Razlika u iznosu uplate", CC, (A, C, D))))
    assert pr == [("kontradikcija_promenjena",
                   "Povezane tvrdnje su se promenile; kontinuitet sporne tačke nije potvrđen: Razlika u iznosu uplate")]


@pytest.mark.parametrize("staro,novo", [((A, B), (A, B)), ((A, B), (A, B, C)), ((A, B, C), (A, B))])
def test_isti_dodat_ili_uklonjen_clan_uz_kontinuitet_nije_promena(staro, novo):
    assert _promene(_snimak(("x", CC, staro)), _snimak(("x", CC, novo))) == []


def test_disjunktni_skupovi_ostaju_nova_i_neopazena():
    pr = _promene(_snimak(("x", CC, (A, B))), _snimak(("x", CC, (C, D))))
    assert sorted(v for v, _ in pr) == ["kontradikcija_dodata", "kontradikcija_nestala"]


def test_dva_nezavisna_istog_naziva_i_razlicit_tip_relacije():
    pr = _promene(_snimak(("x", CC, (A, B)), ("x", "cinjenica_norma", (C, D))),
                  _snimak(("x", CC, (A, B)), ("x", CC, (C, D))))
    # isti claim skup, drugi tip relacije = druga kontradikcija; nema preklapanja istog tipa → nova + neopažena
    assert sorted(v for v, _ in pr) == ["kontradikcija_dodata", "kontradikcija_nestala"]


def test_pomerene_claim_oznake_bez_promene_uuid_nisu_promena():
    st = _snimak(("x", CC, (A, B)))
    st["kontradikcije"][0]["claim_refs"] = ["CLAIM-004", "CLAIM-002"]
    nv = _snimak(("x", CC, (A, B)))
    nv["kontradikcije"][0]["claim_refs"] = ["CLAIM-003", "CLAIM-001"]
    assert _promene(st, nv) == []


def test_prethodna_verzija_bez_trajnih_veza_je_nepoznata_ne_nestala():
    st = {"verzija": 1, "kontradikcije": [{"issue_label": "x", "relation_type": CC, "claim_ids": None}]}
    r = promene_genome(st, _snimak(("x", CC, (A, C, D))))
    assert [p for p in r["promene"] if p["vrsta"].startswith("kontradikcija")] == []
    assert [n["oblast"] for n in r["nepoznato"]] == ["kontradikcije"]


# ═══ TASK 3B — Case Actions ═══

def test_radnja_nosi_isti_signal_bez_promene_identiteta_i_prioriteta():
    from services.v2_projection import u_akciju
    k = {**_v2(), "dokument_ids": [D1], "kontinuitet": "NIJE_POTVRDJEN"}
    a = u_akciju(k)
    assert a["dedupe_key"] == f"v2:contradiction:{KONTR}" and a["prioritet"] == "medium"
    assert a["dokaz"]["claim_ids"] == sorted([A, B]) and a["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN"
    assert a["razlog"].startswith("Razlika u iznosu uplate") and "nije potvrđen" in a["razlog"]
    b = u_akciju({**_v2(), "dokument_ids": [D1]})
    assert b["razlog"] == "Razlika u iznosu uplate" and "kontinuitet" not in b["dokaz"]
    assert a["dedupe_key"] == b["dedupe_key"]


class _Upit:
    def __init__(self, redovi):
        self._r = list(redovi)

    def select(self, *a, **k):
        return self

    def eq(self, kol, v):
        return _Upit([r for r in self._r if r.get(kol) == v])

    def in_(self, kol, vs):
        return _Upit([r for r in self._r if r.get(kol) in set(vs)])

    def execute(self):
        o = MagicMock()
        o.data = self._r
        return o


def _supa_v2():
    tabele = {
        "predmet_issues": [{"id": ISSUE, "predmet_id": P, "label": "Razlika u iznosu uplate", "status": "DISCOVERED"}],
        "predmet_contradictions": [{"id": KONTR, "issue_id": ISSUE, "relation_type": CC, "state": "OPEN", "tezina": "manja"}],
        "predmet_contradiction_claims": [{"contradiction_id": KONTR, "dokaz_id": x, "removed_at": None} for x in (A, B)],
        "predmet_dokazi": dokazi_v2(),
    }
    s = MagicMock()
    s.table.side_effect = lambda ime: _Upit(tabele[ime])
    return s


def test_projekcija_akcija_iz_baze_i_najnovijeg_genome():
    from services.v2_projection import v2_akcije_za_predmet
    g = _genome(("Razlika u iznosu uplate", "kriticna", (A, C, D)))
    a = asyncio.run(v2_akcije_za_predmet(_supa_v2(), P, case_dna=g))
    assert len(a) == 1 and a[0]["dedupe_key"] == f"v2:contradiction:{KONTR}"
    assert a[0]["prioritet"] == "medium" and a[0]["dokaz"]["kontinuitet"] == "NIJE_POTVRDJEN"
    bez = asyncio.run(v2_akcije_za_predmet(_supa_v2(), P))
    assert "kontinuitet" not in bez[0]["dokaz"] and bez[0]["razlog"] == "Razlika u iznosu uplate"
