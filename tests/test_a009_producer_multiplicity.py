# -*- coding: utf-8 -*-
"""A009 — MNOGOSTRUKOST KONTRADIKCIJA NA NIVOU PROIZVOĐAČA.

A005 je izmerio da isti par dokumenata može nositi dve nezavisne sporne tačke,
i da ih proizvođač ume da vrati kao jedan zapis. Uzrok je bio ugovor: svako
drugo listovno polje u promptu ima izričitu kardinalnost (`snaga_faktori`
min 3 / max 8, `dokazi_rang` „Ukljuci SVE dokumente", `strategija.scenariji`
min 2 / max 5), a `kontradikcije` nije imalo nijedno pravilo o broju i šema je
prikazivala tačno jedan objekat.

## Slojevi ovih testova (§8 mandata)

A. UGOVOR      — deterministički, nad tekstom prompta i nad validatorom.
B. MOCK        — STVARNI `_extract_genome`, lažiran isključivo GPT odgovor.
                 Dokazuje da parser, A002 rezolucija i validator NE gube
                 nijednu stavku iz višestrukog izlaza.
C. LIVE LLM    — NIJE ovde. Ponašanje modela nije determinističko i ne sme se
                 lažirati da bi test bio zelen (v. izveštaj, §9).
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.case_dna as cd  # noqa: E402
from shared.genome_validator import (  # noqa: E402
    _validate_kontradikcije_oblik, verify_genome,
)

UUID_A = "aaaaaaaa-1111-1111-1111-111111111111"
UUID_B = "bbbbbbbb-2222-2222-2222-222222222222"
UUID_C = "cccccccc-3333-3333-3333-333333333333"


def _doc(did, naziv, rb):
    return {"id": did, "naziv_fajla": naziv, "redni_broj": rb,
            "tekst_sadrzaj": "Sadrzaj dokumenta dovoljne duzine za analizu.",
            "velicina_kb": 10, "pravni_elementi": []}


DOCS = [_doc(UUID_A, "tuzba.docx", 1), _doc(UUID_B, "odgovor.docx", 2),
        _doc(UUID_C, "zapisnik.docx", 3)]


async def _izvuci(genome, docs=DOCS):
    """STVARNI `_extract_genome`; lažira se isključivo GPT odgovor."""
    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content=json.dumps(genome)))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    with patch("openai.AsyncOpenAI", return_value=klijent):
        return await cd._extract_genome(docs)


def _k(opis, l1, l2, tez="vazna"):
    return {"opis": opis, "lokacija_1": l1, "lokacija_2": l2, "tezina": tez}


def _genome(*kontradikcije):
    return {"kontradikcije": list(kontradikcije), "dokazi_rang": [],
            "snaga_predmeta_procent": 55}


# ═══════════════════════════════════════════════════════════════════════════
# SLOJ A — UGOVOR PROIZVOĐAČA
# ═══════════════════════════════════════════════════════════════════════════

def test_ugovor_eksplicitno_kaze_da_je_lista_neogranicena():
    p = cd._GENOME_SYSTEM
    assert "kontradikcije: LISTA je" in p
    assert "broj stavki NIJE ogranicen" in p
    assert "SVAKU nezavisnu" in p


def test_ugovor_izricito_zabranjuje_spajanje_dve_sporne_tacke():
    p = cd._GENOME_SYSTEM
    assert "ZABRANJENO je spojiti dve sporne tacke u jedan zapis" in p
    for razlog in ("isti\n  dokument", "istu stranu", "istu lokaciju", "isti pravni kontekst"):
        assert razlog.replace("\n  ", " ") in p.replace("\n  ", " ")


def test_ugovor_daje_konkretan_negativan_primer():
    """Generički zapis „postoje razlike izmedju dokumenata" mora biti imenovan
    kao neispravan — to je tačno oblik koji je A005 izmerio."""
    p = cd._GENOME_SYSTEM
    assert "postoje razlike izmedju dokumenata" in p
    assert "NEISPRAVAN" in p
    assert "DATUMA" in p and "IZNOSA" in p


def test_ugovor_dozvoljava_praznu_listu_i_zabranjuje_izmisljanje():
    """Oba dela su nužna: prazna lista mora biti dozvoljena, ali model ne sme
    da je popunjava izmišljenim nalazom da bi izgledala „korisno"."""
    p = cd._GENOME_SYSTEM
    assert "Prazna lista je ispravna" in p
    assert "ne izmisljaj je da bi lista bila puna" in p


def test_ugovor_pokriva_intra_dokumentnu_kontradikciju():
    p = cd._GENOME_SYSTEM
    assert "ISTOG dokumenta" in p and "dva svedoka u istom zapisniku" in p


def _blok_kontradikcija(p: str) -> str:
    """Blok `"kontradikcije": [ … ]` sa UPARENOM zagradom.

    Ranija verzija je sekla na prvom `],`. A014 je u šemu uveo ugnežđenu listu
    (`"claim_refs": ["CLAIM-001", …]`), pa je takvo sečenje počelo da vraća samo
    početak prvog objekta i test je padao iako šema i dalje prikazuje dva.
    Tvrdnje ispod su nepromenjene — popravljeno je samo izdvajanje."""
    poc = p.index('"kontradikcije": [')
    i = p.index("[", poc)
    dubina = 0
    for j in range(i, len(p)):
        if p[j] == "[":
            dubina += 1
        elif p[j] == "]":
            dubina -= 1
            if dubina == 0:
                return p[poc:j + 1]
    raise AssertionError("nezatvoren blok kontradikcija u semi")


def test_sema_prikazuje_VISE_od_jednog_objekta():
    """Primer sa tačno jednim objektom psihološki usmerava model na jedan
    nalaz (hipoteza E iz mandata). Šema mora pokazati dva."""
    blok = _blok_kontradikcija(cd._GENOME_SYSTEM)
    assert blok.count('"opis"') >= 2, "sema i dalje prikazuje samo jednu kontradikciju"
    assert "DRUGA, nezavisna sporna tacka" in blok


def test_META_izdvajanje_bloka_hvata_ugnezdenu_listu():
    """Ako izdvajanje ne bi umelo da preskoči ugnežđenu listu, gornji test bi
    merio pogrešan tekst i mogao bi da prođe/padne iz pogrešnog razloga."""
    uzorak = '"kontradikcije": [\n  {"claim_refs": ["A", "B"], "opis": "x"},\n  {"opis": "y"}\n]'
    assert _blok_kontradikcija(uzorak).count('"opis"') == 2


def test_ugovor_nema_gornju_granicu_broja_kontradikcija():
    p = cd._GENOME_SYSTEM
    poc = p.index("- kontradikcije: LISTA je")
    blok = p[poc:poc + 900]
    for zabranjeno in ("max 1", "maksimalno 1", "samo jednu", "najvise jedn"):
        assert zabranjeno not in blok.lower()


# ═══════════════════════════════════════════════════════════════════════════
# SLOJ A — VALIDATOR OBLIKA (deterministički)
# ═══════════════════════════════════════════════════════════════════════════

def test_validator_prazna_lista_je_validna():
    h, s = _validate_kontradikcije_oblik({"kontradikcije": []})
    assert h == [] and s == []


def test_validator_odsutno_polje_ne_daje_flag():
    assert _validate_kontradikcije_oblik({}) == ([], [])


def test_validator_skalar_umesto_liste_je_hard_flag():
    h, _ = _validate_kontradikcije_oblik({"kontradikcije": "jedna kontradikcija"})
    assert len(h) == 1 and "mora biti lista" in h[0]["razlog"]


def test_validator_izoluje_neispravnu_stavku_a_ne_susede():
    """Jedna malformirana stavka ne sme sakriti ni oboriti ispravne susede."""
    g = {"kontradikcije": [_k("prva", "DOK-01", "DOK-02"), "nije objekat",
                           _k("treca", "DOK-01", "DOK-03")]}
    h, _ = _validate_kontradikcije_oblik(g)
    assert len(h) == 1 and h[0]["polje"] == "kontradikcije[1]"


def test_validator_prazan_nalaz_je_hard_flag():
    h, _ = _validate_kontradikcije_oblik({"kontradikcije": [{"tezina": "vazna"}]})
    assert len(h) == 1 and "prazan nalaz" in h[0]["razlog"]


def test_validator_doslovan_duplikat_je_soft_a_ne_brisanje():
    g = {"kontradikcije": [_k("ista", "DOK-01", "DOK-02"), _k("ista", "DOK-01", "DOK-02")]}
    h, s = _validate_kontradikcije_oblik(g)
    assert h == [] and len(s) == 1 and "duplikat" in s[0]["razlog"]
    assert len(g["kontradikcije"]) == 2, "validator ne sme menjati ulaz"


def test_validator_dve_RAZLICITE_nad_istim_dokumentima_nisu_duplikat():
    g = {"kontradikcije": [_k("datum prestanka", "DOK-01", "DOK-02"),
                           _k("iznos duga", "DOK-01", "DOK-02")]}
    h, s = _validate_kontradikcije_oblik(g)
    assert h == [] and s == [], "razliciti opisi nad istim parom nisu duplikat"


def test_verify_genome_ne_puca_i_ne_sece_listu():
    g = _genome(_k("a", "DOK-01", "DOK-02"), _k("b", "DOK-01", "DOK-03"),
                _k("c", "DOK-02", "DOK-03"))
    v = verify_genome(g, DOCS)
    assert isinstance(v, dict) and "odluka" in v
    assert len(g["kontradikcije"]) == 3


# ═══════════════════════════════════════════════════════════════════════════
# SLOJ B — M1..M10 nad STVARNIM `_extract_genome`
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_M1_dve_sporne_tacke_nad_ISTIM_parom_dokumenata_prezive():
    r = await _izvuci(_genome(_k("Razlika u datumu prestanka radnog odnosa", "DOK-01", "DOK-02"),
                              _k("Razlika u iznosu neisplacenih zarada", "DOK-01", "DOK-02")))
    ks = r["kontradikcije"]
    assert len(ks) == 2, "A005 kvar: mnogostrukost izgubljena u produceru"
    assert {k["opis"] for k in ks} == {"Razlika u datumu prestanka radnog odnosa",
                                       "Razlika u iznosu neisplacenih zarada"}
    for k in ks:
        assert k["dokument_id_1"] == UUID_A and k["dokument_id_2"] == UUID_B


@pytest.mark.asyncio
async def test_M2_clanovi_podrzani_ugovorom_su_svi_prisutni():
    """Postojeći oblik zapisa nosi TAČNO dve strane (`lokacija_1/2`). Tri
    konkurentne tvrdnje o istom pitanju se u ovom obliku izražavaju kao dva
    zapisa. Test tvrdi da nijedan nije izgubljen — ne da ih mora biti tri."""
    r = await _izvuci(_genome(_k("datum: 15.02 vs 20.02", "DOK-01", "DOK-02"),
                              _k("datum: 15.02 vs 25.02", "DOK-01", "DOK-03")))
    assert len(r["kontradikcije"]) == 2
    assert all(k.get("lokacija_1") and k.get("lokacija_2") for k in r["kontradikcije"])


@pytest.mark.asyncio
async def test_M3_dve_intra_dokumentne_kontradikcije_prezive():
    """A005 je dokazao da proizvođač ume da spoji dve teme unutar jednog
    dokumenta. Kad ih vrati odvojeno, ništa ih ne sme sažeti."""
    r = await _izvuci(_genome(_k("svedoci se ne slazu o sastanku", "DOK-03 Snezana", "DOK-03 Milos"),
                              _k("svedoci se ne slazu o upozorenju", "DOK-03 str.2", "DOK-03 str.3")))
    ks = r["kontradikcije"]
    assert len(ks) == 2
    for k in ks:
        assert k["dokument_id_1"] == UUID_C and k["dokument_id_2"] == UUID_C


@pytest.mark.asyncio
async def test_M4_cinjenica_protiv_cinjenice():
    r = await _izvuci(_genome(_k("A tvrdi X, B tvrdi Y", "DOK-01 str.1", "DOK-02 str.4")))
    k = r["kontradikcije"][0]
    assert k["dokument_id_1"] == UUID_A and k["dokument_id_2"] == UUID_B


@pytest.mark.asyncio
async def test_M5_cinjenica_protiv_norme_prezivljava_sa_None_na_normi():
    """Obe strane NISU nužno dokumenti — `e0a54af1` v1 u produkciji nosi
    `DOK-01 ↔ "Zakon o radu cl. 179"`. Strana koja nije dokument ostaje `None`,
    fail-closed, a kontradikcija se NE odbacuje."""
    r = await _izvuci(_genome(_k("otkaz protivan zakonu", "DOK-01 str.1", "Zakon o radu cl. 179")))
    ks = r["kontradikcije"]
    assert len(ks) == 1
    assert ks[0]["dokument_id_1"] == UUID_A
    assert ks[0]["dokument_id_2"] is None


@pytest.mark.asyncio
async def test_M6_dodavanje_dokumenta_ne_uklanja_stavke_iz_izlaza():
    """Deterministički sloj: za ISTI izlaz proizvođača, veći korpus ne sme
    ukloniti nijednu stavku. (Da li model nad većim korpusom nađe iste nalaze
    je pitanje LIVE sloja — v. izveštaj §9.)"""
    g = _genome(_k("datum", "DOK-01", "DOK-02"), _k("iznos", "DOK-01", "DOK-02"))
    mali = await _izvuci(g, DOCS[:2])
    veliki = await _izvuci(g, DOCS)
    assert len(mali["kontradikcije"]) == len(veliki["kontradikcije"]) == 2
    assert {k["opis"] for k in mali["kontradikcije"]} == {k["opis"] for k in veliki["kontradikcije"]}


@pytest.mark.asyncio
async def test_M7b_ISTI_opis_a_razlicite_lokacije_ostaju_DVA_nalaza():
    """Dva različita spora smeju imati identičan opis (npr. „svedoci se ne
    slazu") a različite izvore. Bilo kakvo grupisanje po tekstu opisa ih spaja
    i tiho gubi jedan — isti oblik kvara kao A005, samo po drugom ključu."""
    isti = "Svedoci se ne slazu"
    r = await _izvuci(_genome(_k(isti, "DOK-01", "DOK-02"),
                              _k(isti, "DOK-02", "DOK-03")))
    ks = r["kontradikcije"]
    assert len(ks) == 2, "grupisanje po opisu je tihi gubitak"
    assert {(k["dokument_id_1"], k["dokument_id_2"]) for k in ks} == {
        (UUID_A, UUID_B), (UUID_B, UUID_C)}


@pytest.mark.asyncio
async def test_M7_dva_slicno_formulisana_nalaza_prolaze_oba():
    """Producer sloj NE rešava identitet — to je posao V2 domena. Oba nalaza
    moraju proći; nikakva heuristika ih ne sme spojiti ovde."""
    r = await _izvuci(_genome(_k("datum prestanka se razlikuje", "DOK-01", "DOK-02"),
                              _k("razlicit dan prestanka radnog odnosa", "DOK-01", "DOK-02")))
    assert len(r["kontradikcije"]) == 2


@pytest.mark.asyncio
async def test_M8_prazna_lista_ostaje_prazna_bez_izmisljanja():
    r = await _izvuci(_genome())
    assert r["kontradikcije"] == []


@pytest.mark.asyncio
async def test_M9_pet_kontradikcija_prezivi_sve():
    """Dokaz da ne postoji implicitni „one contradiction" plafon."""
    ulaz = [_k(f"sporna tacka {i}", f"DOK-0{(i % 3) + 1}", f"DOK-0{((i + 1) % 3) + 1}")
            for i in range(5)]
    r = await _izvuci(_genome(*ulaz))
    assert len(r["kontradikcije"]) == 5
    assert len({k["opis"] for k in r["kontradikcije"]}) == 5


@pytest.mark.asyncio
async def test_M10_malformirana_stavka_ne_unistava_susede():
    """Per-item izolacija u A002 petlji: skalarna stavka se preskače, a
    ispravni susedi zadržavaju svoj razrešen identitet."""
    g = {"kontradikcije": [_k("prva", "DOK-01", "DOK-02"), "skalar",
                           _k("treca", "DOK-01", "DOK-03")],
         "dokazi_rang": [], "snaga_predmeta_procent": 55}
    r = await _izvuci(g)
    ks = r["kontradikcije"]
    assert len(ks) == 3, "sibling nalazi ne smeju nestati zbog jedne neispravne stavke"
    assert ks[0]["dokument_id_1"] == UUID_A and ks[0]["dokument_id_2"] == UUID_B
    assert ks[2]["dokument_id_1"] == UUID_A and ks[2]["dokument_id_2"] == UUID_C
    assert ks[1] == "skalar", "neispravna stavka se ne prepravlja niti brise"


@pytest.mark.asyncio
@pytest.mark.parametrize("loše", [None, "", {}, {"lokacija_1": None, "lokacija_2": None}])
async def test_M10b_razne_malformacije_ne_obaraju_ekstrakciju(loše):
    g = {"kontradikcije": [_k("dobra", "DOK-01", "DOK-02"), loše],
         "dokazi_rang": [], "snaga_predmeta_procent": 55}
    r = await _izvuci(g)
    assert "greska" not in r
    assert r["kontradikcije"][0]["dokument_id_1"] == UUID_A


@pytest.mark.asyncio
async def test_redosled_kontradikcija_u_izlazu_je_ocuvan():
    """Nema sortiranja ni preuređivanja — potrošač mora videti tačno ono što
    je proizvođač vratio, istim redom."""
    r = await _izvuci(_genome(_k("prva", "DOK-01", "DOK-02"),
                              _k("druga", "DOK-02", "DOK-03"),
                              _k("treca", "DOK-01", "DOK-03")))
    assert [k["opis"] for k in r["kontradikcije"]] == ["prva", "druga", "treca"]


@pytest.mark.asyncio
async def test_isti_dokument_na_obe_strane_je_dozvoljen():
    """Intra-dokumentna kontradikcija je 26% stvarnih slučajeva (A006).
    `dokument_id_1 == dokument_id_2` je VALIDNO, ne greška."""
    r = await _izvuci(_genome(_k("dva svedoka u istom zapisniku", "DOK-03 A", "DOK-03 B")))
    k = r["kontradikcije"][0]
    assert k["dokument_id_1"] == k["dokument_id_2"] == UUID_C
