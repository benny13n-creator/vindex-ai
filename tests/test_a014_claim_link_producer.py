# -*- coding: utf-8 -*-
"""A014 §12 — ADVERSARIAL SUITA za claim-link producer (CASE A–P).

Meri se lanac koji A014 uvodi:

    predmet_dokazi -> claim_catalog -> (LLM bira oznake) -> materializer -> kandidat

LLM je ovde zamenjen fiksnim izlazima, i to je namerno: predmet merenja NIJE
da li model dobro bira, nego da li sistem **odbija sve što nije deterministički
razrešivo**. Živa provera kroz stvarni GPT poziv izvedena je zasebno i opisana u
`A014_CONTRADICTION_CLAIM_LINK_IMPLEMENTATION_REPORT.md` — mock ovde ni na jednom
mestu nije predstavljen kao dokaz da producer radi.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.claim_catalog import (  # noqa: E402
    MAKS_TVRDNJI,
    GreskaKataloga,
    napravi_katalog,
    razresi_reference,
    redovi_za_prompt,
)
from shared.contradiction_materializer import (  # noqa: E402
    ODBIJEN_MALO_TVRDNJI,
    ODBIJEN_OBLIK,
    ODBIJEN_REFERENCA,
    ODBIJEN_RELACIJA,
    materializuj,
)
from shared.contradiction_identity import contradiction_dedupe_key  # noqa: E402

P = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
DOK1 = "d0000001-0000-4000-8000-000000000001"
DOK2 = "d0000002-0000-4000-8000-000000000002"


def _d(id_, tvrdnja, dok=DOK1, predmet=P, deleted=None, elm=None):
    return {"id": id_, "predmet_id": predmet, "tvrdnja": tvrdnja, "dokument_id": dok,
            "deleted_at": deleted, "pravni_element": elm}


# Šest tvrdnji: tri iz DOK1, tri iz DOK2. Id-jevi su namerno tako izabrani da
# sortiranje daje predvidiv katalog CLAIM-001..006.
DOKAZI = [
    _d("a1", "radni odnos prestao 15.03.2025.", DOK1),
    _d("a2", "neisplacena zarada 480.000 RSD", DOK1),
    _d("a3", "zaposleni bio na neplacenom odsustvu", DOK1),
    _d("b1", "radni odnos prestao 20.03.2025.", DOK2),
    _d("b2", "neisplacena zarada 310.000 RSD", DOK2),
    _d("b3", "clan 179 ZOR propisuje otkazni rok", DOK2),
]
KAT = napravi_katalog(DOKAZI, P)
POZNATI = {d["id"]: d for d in DOKAZI}


def _k(refs, rel="cinjenica_cinjenica", label=None, opis="spor", **extra):
    r = {"claim_refs": refs, "relation_type": rel, "issue_label": label, "opis": opis}
    r.update(extra)
    return r


def _mat(kontradikcije, katalog=KAT, predmet=P, poznati=None):
    return materializuj(kontradikcije, katalog, predmet,
                        POZNATI if poznati is None else poznati)


# ═══════════════════════════════════════════════════════════════════════════
# Katalog — osnovna svojstva
# ═══════════════════════════════════════════════════════════════════════════

def test_katalog_je_deterministican_bez_obzira_na_redosled_iz_baze():
    obrnuto = list(reversed(DOKAZI))
    assert napravi_katalog(obrnuto, P) == KAT


def test_katalog_preskace_tvrdnju_bez_teksta():
    """Ono što model ne vidi ne sme imati oznaku."""
    k = napravi_katalog(DOKAZI + [_d("z9", "   ")], P)
    assert "z9" not in k.values()


def test_katalog_preskace_obrisanu_tvrdnju():
    k = napravi_katalog(DOKAZI + [_d("z9", "obrisana", deleted="2026-01-01")], P)
    assert "z9" not in k.values()


def test_katalog_preskace_tvrdnju_tudjeg_predmeta():
    k = napravi_katalog(DOKAZI + [_d("z9", "tudja", predmet=P2)], P)
    assert "z9" not in k.values()


def test_katalog_postuje_gornju_granicu():
    mnogo = [_d(f"x{i:03d}", f"tvrdnja {i}") for i in range(MAKS_TVRDNJI + 15)]
    assert len(napravi_katalog(mnogo, P)) == MAKS_TVRDNJI


def test_katalog_bez_predmeta_je_greska():
    with pytest.raises(GreskaKataloga):
        napravi_katalog(DOKAZI, "")


def test_redovi_za_prompt_pokrivaju_tacno_katalog():
    redovi = redovi_za_prompt(KAT, DOKAZI)
    assert len(redovi) == len(KAT)
    for oznaka in KAT:
        assert any(r.startswith(oznaka + ":") for r in redovi)


def test_oznake_se_MENJAJU_kad_se_skup_promeni():
    """Ugovor koji pozivalac mora poštovati, zaključan testom.

    Oznaka je efemerna adresa unutar jednog poziva. Nova tvrdnja čiji `id`
    sortira ispred postojećih POMERA oznake. Bezbedno je jedino ako se
    razrešavanje radi katalogom koji je model i video."""
    novi = napravi_katalog(DOKAZI + [_d("a0", "nova tvrdnja")], P)
    assert novi["CLAIM-001"] == "a0"
    assert KAT["CLAIM-001"] == "a1"
    assert novi != KAT


# ═══════════════════════════════════════════════════════════════════════════
# CASE A–P
# ═══════════════════════════════════════════════════════════════════════════

def test_CASE_A_dva_spora_isti_dokumenti_ostaju_dva():
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], label="razlika u datumu"),
        _k(["CLAIM-002", "CLAIM-005"], label="razlika u iznosu"),
    ])
    assert r["odbijeni"] == []
    assert len(r["kandidati"]) == 2
    a, b = r["kandidati"]
    assert set(a["claim_refs"]) != set(b["claim_refs"])
    # Legacy kljuc bi ih spojio — to je tacno kvar koji V2 uklanja.
    legacy = contradiction_dedupe_key({"lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-02 str.1"})
    legacy2 = contradiction_dedupe_key({"lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-02 str.1"})
    assert legacy == legacy2


def test_CASE_B_intra_dokumentna_kontradikcija_je_validna():
    r = _mat([_k(["CLAIM-001", "CLAIM-002"], label="isti dokument")])
    assert r["odbijeni"] == []
    assert len(r["kandidati"]) == 1
    dokumenti = {POZNATI[c]["dokument_id"] for c in r["kandidati"][0]["claim_refs"]}
    assert dokumenti == {DOK1}, "obe tvrdnje moraju biti iz istog dokumenta"


def test_CASE_C_tri_iskljucive_tvrdnje_su_JEDNA_kontradikcija():
    r = _mat([_k(["CLAIM-001", "CLAIM-004", "CLAIM-003"], label="datum")])
    assert len(r["kandidati"]) == 1, "ne sme se razbiti na parove"
    assert len(r["kandidati"][0]["claim_refs"]) == 3


def test_CASE_D_fact_vs_norm_ima_svoj_relation_type():
    r = _mat([_k(["CLAIM-001", "CLAIM-006"], rel="cinjenica_norma", label="norma")])
    assert r["kandidati"][0]["relation_type"] == "cinjenica_norma"


def test_CASE_E_nepoznata_referenca_pada_zatvoreno():
    r = _mat([_k(["CLAIM-999", "CLAIM-001"])])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA
    assert "CLAIM-999" in r["odbijeni"][0]["detalj"]


@pytest.mark.parametrize("token", ["", "   ", "claim-001", "CLAIM-1", "CLAIM_001",
                                   "CLAIM-001 ", None, 1, ["CLAIM-001"], {}])
def test_CASE_E_varijante_neispravnog_tokena(token):
    """`CLAIM-001 ` (sa razmakom) se trimuje i JESTE validan — sve ostalo pada.
    Nema prefiks-poklapanja, nema case-insensitive poklapanja."""
    r = _mat([_k([token, "CLAIM-002"])])
    if isinstance(token, str) and token.strip() in KAT:
        assert len(r["kandidati"]) == 1
    else:
        assert r["kandidati"] == []
        assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA


def test_CASE_F_tvrdnja_iz_drugog_predmeta_pada_zatvoreno():
    """Katalog je vec predmet-scoped, ali se meri i druga brava: cak i ako bi
    oznaka nekako postojala, `poznati_dokazi` odbija tudji predmet."""
    tudji = dict(POZNATI)
    tudji["a1"] = _d("a1", "tudja tvrdnja", predmet=P2)
    r = materializuj([_k(["CLAIM-001", "CLAIM-002"])], KAT, P, tudji)
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA
    assert "drugom predmetu" in r["odbijeni"][0]["detalj"]


def test_CASE_G_duplirana_referenca_je_HARD_FAIL_a_ne_tiha_deduplikacija():
    r = _mat([_k(["CLAIM-001", "CLAIM-001"])])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA
    assert "duplirana" in r["odbijeni"][0]["detalj"]


def test_CASE_H_jedna_tvrdnja_pada():
    r = _mat([_k(["CLAIM-001"])])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_MALO_TVRDNJI


def test_CASE_I_prazna_lista_je_validna():
    r = _mat([])
    assert r == {"kandidati": [], "odbijeni": []}
    assert materializuj(None, KAT, P, POZNATI) == {"kandidati": [], "odbijeni": []}


def test_CASE_J_genericka_kontradikcija_bez_referenci_je_neispravna():
    r = _mat([{"opis": "Dokumenti sadrže različite informacije.",
               "relation_type": "cinjenica_cinjenica", "lokacija_1": "DOK-01",
               "lokacija_2": "DOK-02", "tezina": "vazna"}])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA


def test_CASE_K_isti_opis_razlicit_skup_daju_DVE_kontradikcije():
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], opis="Dokumenti se ne slazu."),
        _k(["CLAIM-002", "CLAIM-005"], opis="Dokumenti se ne slazu."),
    ])
    assert len(r["kandidati"]) == 2
    assert r["kandidati"][0]["_opis"] == r["kandidati"][1]["_opis"]
    assert set(r["kandidati"][0]["claim_refs"]) != set(r["kandidati"][1]["claim_refs"])


def test_CASE_L_isti_claimovi_razlicit_label_daju_ISTI_skup_clanova():
    r1 = _mat([_k(["CLAIM-001", "CLAIM-004"], label="prva formulacija")])
    r2 = _mat([_k(["CLAIM-001", "CLAIM-004"], label="sasvim drugacije receno")])
    assert r1["kandidati"][0]["claim_refs"] == r2["kandidati"][0]["claim_refs"]
    assert r1["kandidati"][0]["issue_label"] != r2["kandidati"][0]["issue_label"]


def test_CASE_M_redosled_referenci_ne_menja_skup_clanova():
    r1 = _mat([_k(["CLAIM-001", "CLAIM-004"])])
    r2 = _mat([_k(["CLAIM-004", "CLAIM-001"])])
    assert set(r1["kandidati"][0]["claim_refs"]) == set(r2["kandidati"][0]["claim_refs"])


def test_CASE_N_nova_tvrdnja_ne_brise_postojecu_kontradikciju():
    """Dodavanje dokumenta prosiruje katalog; postojeci spor i dalje mora da se
    materijalizuje, sa istim clanovima."""
    prosireni = DOKAZI + [_d("c1", "nova tvrdnja iz novog dokumenta", "d0000003-0000-4000-8000-000000000003")]
    kat2 = napravi_katalog(prosireni, P)
    poznati2 = {d["id"]: d for d in prosireni}
    oznaka_a1 = next(o for o, v in kat2.items() if v == "a1")
    oznaka_b1 = next(o for o, v in kat2.items() if v == "b1")
    r = materializuj([_k([oznaka_a1, oznaka_b1])], kat2, P, poznati2)
    assert len(r["kandidati"]) == 1
    assert set(r["kandidati"][0]["claim_refs"]) == {"a1", "b1"}


def test_CASE_O_stara_i_nova_kontradikcija_koegzistiraju():
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], label="stara"),
        _k(["CLAIM-002", "CLAIM-005"], label="nova"),
    ])
    assert len(r["kandidati"]) == 2
    skupovi = [set(k["claim_refs"]) for k in r["kandidati"]]
    assert skupovi[0] & skupovi[1] == set(), "nema deljenih clanova -> nema izgovora za spajanje"


def test_CASE_P_legacy_kljuc_bi_spojio_ono_sto_V2_razdvaja():
    """Dokaz koji §14 trazi PRE skidanja legacy collapse-a.

    Dve kontradikcije nad istim parom lokacija dobijaju IDENTICAN legacy
    `dedupe_key`, dok im V2 skupovi tvrdnji ostaju razliciti. Zato projekcioni
    kljuc ne sme biti legacy `dedupe_key`."""
    sirove = [
        _k(["CLAIM-001", "CLAIM-004"], label="datum",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
        _k(["CLAIM-002", "CLAIM-005"], label="iznos",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
    ]
    legacy = {contradiction_dedupe_key(k) for k in sirove}
    assert len(legacy) == 1, "legacy kljuc bi ih spojio"

    r = _mat(sirove)
    assert len(r["kandidati"]) == 2
    v2 = {tuple(sorted(k["claim_refs"])) for k in r["kandidati"]}
    assert len(v2) == 2, "V2 skupovi tvrdnji moraju ostati razliciti"


# ═══════════════════════════════════════════════════════════════════════════
# Oblik i relacija
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rel", [None, "", "FACT_FACT", "izmisljeno", {}, [], 7])
def test_nepoznat_relation_type_pada_zatvoreno(rel):
    r = _mat([_k(["CLAIM-001", "CLAIM-004"], rel=rel)])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_RELACIJA


@pytest.mark.parametrize("lose", [
    "string", 42, None, {}, {"CLAIM-001"}, ("CLAIM-001", "CLAIM-004"),
])
def test_claim_refs_koji_nije_lista_pada(lose):
    """Tuple i set NISU lista. Prihvatiti ih znacilo bi da oblik ulaza nije
    proveren nego pogodjen — a `set` bi usput i tiho deduplikovao, sto CASE G
    izricito zabranjuje."""
    r = _mat([{"claim_refs": lose, "relation_type": "cinjenica_cinjenica"}])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_REFERENCA
    assert "mora biti lista" in r["odbijeni"][0]["detalj"]


def test_kontradikcije_koje_nisu_lista_padaju_kao_oblik():
    r = _mat({"opis": "objekat umesto liste"})
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == ODBIJEN_OBLIK


def test_stavka_koja_nije_objekat_pada_kao_oblik():
    r = _mat(["tekst", 5, None])
    assert r["kandidati"] == []
    assert len(r["odbijeni"]) == 3
    assert all(o["razlog"] == ODBIJEN_OBLIK for o in r["odbijeni"])


def test_jedan_neispravan_predlog_ne_obara_ispravne():
    """Odbijanje je po predlogu, ne po paketu — inace bi jedna losa stavka
    tiho pojela sve ostale nalaze."""
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], label="dobra"),
        _k(["CLAIM-999"], label="losa"),
        _k(["CLAIM-002", "CLAIM-005"], label="druga dobra"),
    ])
    assert len(r["kandidati"]) == 2
    assert len(r["odbijeni"]) == 1
    assert r["odbijeni"][0]["indeks"] == 1


def test_provenijencija_se_prenosi_ali_ne_odlucuje():
    r = _mat([_k(["CLAIM-001", "CLAIM-004"], label="x", opis="opis teksta",
                 tezina="kriticna", lokacija_1="DOK-01 str.3", lokacija_2="DOK-02 str.9")])
    k = r["kandidati"][0]
    assert k["_opis"] == "opis teksta"
    assert k["_tezina"] == "kriticna"
    assert k["_lokacije"] == ["DOK-01 str.3", "DOK-02 str.9"]
    # ...a clanstvo je i dalje iskljucivo iz claim_refs
    assert set(k["claim_refs"]) == {"a1", "b1"}


def test_issue_label_pada_nazad_na_opis_ali_nikad_na_lokaciju():
    r = _mat([{"claim_refs": ["CLAIM-001", "CLAIM-004"],
               "relation_type": "cinjenica_cinjenica", "opis": "jedini tekst",
               "lokacija_1": "DOK-01"}])
    assert r["kandidati"][0]["issue_label"] == "jedini tekst"


# ═══════════════════════════════════════════════════════════════════════════
# Regresija koju je puna suita nasla: blok konteksta ne sme nestati
# ═══════════════════════════════════════════════════════════════════════════

def _prompt_od(dokazi, predmet_id=None):
    """Tekst koji bi stvarno otisao GPT-u, bez mreznog poziva."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    import routers.case_dna as cd

    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content='{"snaga_faktori": []}'))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "tekst dokumenta"}]
    with patch("openai.AsyncOpenAI", return_value=klijent):
        asyncio.run(cd._extract_genome(docs, dokazi=dokazi, predmet_id=predmet_id))
    return klijent.chat.completions.create.call_args.kwargs["messages"][-1]["content"]


def test_evidence_blok_se_NIKAD_ne_gubi_bez_predmet_id():
    """Nadjeno punom suitom, ne pregledom.

    Prva verzija A014 je `predmet_id` zakljucivala iz redova; kad ga nema,
    katalog je prazan i CEO blok je TIHO nestajao iz prompta — cime bi se vratio
    forenzicki nalaz od 2026-07-22 („Genome nikad ne cita predmet_dokazi")."""
    p = _prompt_od([{"tvrdnja": "Tuzeni je otkazao ugovor", "pravni_element": "uzrocna veza"}])
    assert "EVIDENCE VAULT" in p
    assert "Tuzeni je otkazao ugovor" in p
    assert "CLAIM-" not in p, "bez opsega ne sme biti oznaka koje model ne moze da razresi"


def test_sa_predmet_id_blok_nosi_oznake():
    p = _prompt_od([_d("a1", "prva tvrdnja"), _d("a2", "druga tvrdnja")], predmet_id=P)
    assert "EVIDENCE VAULT" in p
    assert "CLAIM-001: prva tvrdnja" in p
    assert "CLAIM-002: druga tvrdnja" in p
    assert "JEDINE dozvoljene vrednosti" in p


def test_predmet_id_se_NE_zakljucuje_iz_redova():
    """Opseg je ulaz, ne nagadjanje. Redovi nose `predmet_id`, ali ga pozivalac
    nije prosledio — oznake se NE smeju pojaviti."""
    p = _prompt_od([_d("a1", "prva tvrdnja"), _d("a2", "druga tvrdnja")])
    assert "EVIDENCE VAULT" in p
    assert "CLAIM-" not in p


def test_kandidat_je_tacno_ono_sto_adapter_ocekuje():
    """Materializer i adapter dele ugovor — bez prevodioca izmedju njih."""
    from shared.issue_v2 import validiraj_predlog_teme
    r = _mat([_k(["CLAIM-001", "CLAIM-004"], label="spor")])
    v = validiraj_predlog_teme(r["kandidati"][0], P, POZNATI)
    assert v["ok"] is True
    assert v["claim_set"] == frozenset({"a1", "b1"})
    assert v["relation_type"] == "cinjenica_cinjenica"
