# -*- coding: utf-8 -*-
"""A014 §17 — MUTACIJE M1–M15 nad claim-link producerom.

Svaka mutacija vraća tačno jedan poznati kvar i dokazuje da ga postojeći test
hvata. Obrazac je svuda isti i namerno dosadan:

    1. primeni mutaciju  -> pokazi da se ponasanje STVARNO promenilo
    2. pokreni kanonski put -> pokazi da on daje ISPRAVAN rezultat

Ako drugi korak nedostaje, „ubijena mutacija" ne znači ništa — mogla bi da
prolazi i nad pokvarenim kodom.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.claim_catalog import GreskaKataloga, napravi_katalog, razresi_reference  # noqa: E402
from shared.contradiction_identity import contradiction_dedupe_key  # noqa: E402
from shared.contradiction_materializer import materializuj  # noqa: E402
from shared.issue_v2 import MIN_TVRDNJI, RELACIJE  # noqa: E402

from test_a014_claim_link_producer import (  # noqa: E402
    DOK1, DOK2, DOKAZI, KAT, P, P2, POZNATI, _d, _k, _mat,
)

import routers.case_dna as cd  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# M1 — ukloni claim_refs iz producer ugovora
# ═══════════════════════════════════════════════════════════════════════════

def test_M1_ugovor_bez_claim_refs_je_ubijen():
    p = cd._GENOME_SYSTEM
    mutant = p.replace("claim_refs", "XXXX")
    assert "claim_refs" not in mutant, "mutacija nije primenjena"

    # Kanonski ugovor mora traziti reference, i to obavezno.
    assert "claim_refs" in p
    assert "OBAVEZNO polje" in p
    assert "NIKAD ne izmisljaj oznaku" in p
    assert "ne pisi UUID" in p


def test_M1b_ugovor_mora_zabraniti_izmisljanje_oznake():
    p = cd._GENOME_SYSTEM
    assert "prazna lista je" in p.lower() or "prazna lista kontradikcija" in p
    assert "izmisljena referenca NIJE" in p


# ═══════════════════════════════════════════════════════════════════════════
# M2 — razresavanje po dokumentu umesto po referenci
# ═══════════════════════════════════════════════════════════════════════════

def _razresi_po_dokumentu(refs, katalog, predmet_id, poznati=None):
    """MUTANT: ignorise oznake i uzima SVE tvrdnje iz pomenutih dokumenata."""
    return sorted({d["id"] for d in DOKAZI if d["dokument_id"] in (DOK1, DOK2)})


def test_M2_razresavanje_po_dokumentu_je_ubijeno():
    mut = _razresi_po_dokumentu(["CLAIM-001", "CLAIM-004"], KAT, P)
    assert len(mut) == 6, "mutacija nije primenjena"

    kanon = razresi_reference(["CLAIM-001", "CLAIM-004"], KAT, P, POZNATI)
    assert kanon == ["a1", "b1"], "kanon mora uzeti TACNO referisane tvrdnje"
    assert len(kanon) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M3 — fuzzy / substring poklapanje oznaka
# ═══════════════════════════════════════════════════════════════════════════

def _razresi_fuzzy(refs, katalog, predmet_id, poznati=None):
    """MUTANT: „najbliza tvrdnja" — bira oznaku sa najduzim zajednickim prefiksom.

    Prva verzija ove mutacije bila je preslaba (`startswith` na 7 znakova nije
    pogadjao nista), pa nije ni pokazivala opasnost. Ovaj oblik UVEK vrati nesto,
    i to je tacno ponasanje koje A014 §22 zabranjuje: izmisljena oznaka tiho
    postaje stvarna tvrdnja."""
    def _zajednicki(a, b):
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    out = []
    for r in refs:
        najblizi = max(katalog, key=lambda kljuc: _zajednicki(kljuc, str(r)))
        out.append(katalog[najblizi])
    return out


def test_M3_fuzzy_poklapanje_je_ubijeno():
    mut = _razresi_fuzzy(["CLAIM-999", "CLAIM-001"], KAT, P)
    assert len(mut) == 2, "mutacija nije primenjena — fuzzy je razresio nepostojecu oznaku"

    with pytest.raises(GreskaKataloga) as exc:
        razresi_reference(["CLAIM-999", "CLAIM-001"], KAT, P, POZNATI)
    assert "nepoznata referenca" in str(exc.value)


@pytest.mark.parametrize("blizak", ["CLAIM-01", "CLAIM-0011", "claim-001", "CLAIM-002x"])
def test_M3b_nijedna_bliska_varijanta_se_ne_prima(blizak):
    with pytest.raises(GreskaKataloga):
        razresi_reference([blizak, "CLAIM-002"], KAT, P, POZNATI)


# ═══════════════════════════════════════════════════════════════════════════
# M4 — nepoznata referenca se tiho preskace
# ═══════════════════════════════════════════════════════════════════════════

def _razresi_preskacuci(refs, katalog, predmet_id, poznati=None):
    """MUTANT: nepoznato se preskace umesto da obori predlog."""
    return [katalog[r] for r in refs if r in katalog]


def test_M4_tiho_preskakanje_nepoznate_reference_je_ubijeno():
    mut = _razresi_preskacuci(["CLAIM-999", "CLAIM-001", "CLAIM-004"], KAT, P)
    assert mut == ["a1", "b1"], "mutacija nije primenjena"
    # Pod mutacijom bi predlog PROSAO sa 2 tvrdnje, a jedna referenca je izmisljena.

    r = _mat([_k(["CLAIM-999", "CLAIM-001", "CLAIM-004"])])
    assert r["kandidati"] == [], "kanon je propustio predlog sa izmisljenom referencom"
    assert r["odbijeni"][0]["razlog"] == "UNRESOLVED_CLAIM_REF"


# ═══════════════════════════════════════════════════════════════════════════
# M5 — dozvoli tvrdnju iz drugog predmeta
# ═══════════════════════════════════════════════════════════════════════════

def test_M5_cross_case_tvrdnja_je_ubijena():
    tudji = dict(POZNATI)
    tudji["a1"] = _d("a1", "tudja", predmet=P2)

    # MUTANT: bez `poznati_dokazi` provera vlasnistva se ne izvrsava.
    mut = razresi_reference(["CLAIM-001", "CLAIM-004"], KAT, P, None)
    assert mut == ["a1", "b1"], "mutacija nije primenjena"

    with pytest.raises(GreskaKataloga) as exc:
        razresi_reference(["CLAIM-001", "CLAIM-004"], KAT, P, tudji)
    assert "drugom predmetu" in str(exc.value)

    r = materializuj([_k(["CLAIM-001", "CLAIM-004"])], KAT, P, tudji)
    assert r["kandidati"] == []


def test_M5b_katalog_sam_ne_pusta_tudju_tvrdnju():
    """Prva od tri brave: tudja tvrdnja nikad ne dobija oznaku."""
    k = napravi_katalog(DOKAZI + [_d("z9", "tudja", predmet=P2)], P)
    assert "z9" not in k.values()


# ═══════════════════════════════════════════════════════════════════════════
# M6 — dozvoli jednu tvrdnju
# ═══════════════════════════════════════════════════════════════════════════

def test_M6_prag_od_jedne_tvrdnje_je_ubijen():
    assert MIN_TVRDNJI == 2, "kanonski prag je promenjen"
    razresene = razresi_reference(["CLAIM-001"], KAT, P, POZNATI)
    assert len(set(razresene)) < MIN_TVRDNJI

    # MUTANT: prag 1 -> predlog prolazi
    assert len(set(razresene)) >= 1

    r = _mat([_k(["CLAIM-001"])])
    assert r["kandidati"] == []
    assert r["odbijeni"][0]["razlog"] == "TOO_FEW_CLAIMS"


# ═══════════════════════════════════════════════════════════════════════════
# M7 — tiha deduplikacija dupliranih referenci
# ═══════════════════════════════════════════════════════════════════════════

def _razresi_sa_tihim_dedup(refs, katalog, predmet_id, poznati=None):
    """MUTANT: `set()` proguta duplikat i predlog postane 'validan' ako je
    slucajno bilo jos referenci."""
    return sorted({katalog[r] for r in refs if r in katalog})


def test_M7_tiha_deduplikacija_je_ubijena():
    mut = _razresi_sa_tihim_dedup(["CLAIM-001", "CLAIM-001", "CLAIM-004"], KAT, P)
    assert mut == ["a1", "b1"], "mutacija nije primenjena"
    # Pod mutacijom: 3 reference -> 2 clana, bez ijednog signala da je bio duplikat.

    with pytest.raises(GreskaKataloga) as exc:
        razresi_reference(["CLAIM-001", "CLAIM-001", "CLAIM-004"], KAT, P, POZNATI)
    assert "duplirana referenca" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# M8 / M12 / M13 — identitet iz opisa, labele ili lokacije
# ═══════════════════════════════════════════════════════════════════════════

def _sazmi_po(kljuc, kandidati):
    """MUTANT: sazimanje po tekstualnom polju — tacno stari model."""
    return {k.get(kljuc): k for k in kandidati}


@pytest.mark.parametrize("polje,vrednost", [
    ("_opis", "Dokumenti se ne slazu."),
    ("issue_label", "ista labela"),
])
def test_M8_M12_sazimanje_po_tekstu_je_ubijeno(polje, vrednost):
    sirove = [
        _k(["CLAIM-001", "CLAIM-004"], label=vrednost, opis=vrednost),
        _k(["CLAIM-002", "CLAIM-005"], label=vrednost, opis=vrednost),
    ]
    r = _mat(sirove)
    assert len(r["kandidati"]) == 2, "kanon je izgubio jedan nalaz"

    sazeto = _sazmi_po(polje, r["kandidati"])
    assert len(sazeto) == 1, "mutacija nije primenjena"
    # Kanon ih razlikuje po skupu tvrdnji, koji mutacija uopste ne gleda:
    assert len({tuple(sorted(k["claim_refs"])) for k in r["kandidati"]}) == 2


def test_M13_identitet_iz_lokacije_je_ubijen():
    sirove = [
        _k(["CLAIM-001", "CLAIM-004"], label="datum",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
        _k(["CLAIM-002", "CLAIM-005"], label="iznos",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
    ]
    r = _mat(sirove)
    sazeto = {tuple(k["_lokacije"]): k for k in r["kandidati"]}
    assert len(sazeto) == 1, "mutacija nije primenjena"
    assert len(r["kandidati"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M9 / M10 — sazimanje po paru dokumenata / spajanje u jednu spornu tacku
# ═══════════════════════════════════════════════════════════════════════════

def test_M9_sazimanje_po_paru_dokumenata_je_ubijeno():
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], label="datum"),
        _k(["CLAIM-002", "CLAIM-005"], label="iznos"),
    ])
    parovi = {tuple(sorted({POZNATI[c]["dokument_id"] for c in k["claim_refs"]}))
              for k in r["kandidati"]}
    assert len(parovi) == 1, "mutacija nije primenjena — oba spora dele isti par dokumenata"
    assert len(r["kandidati"]) == 2, "kanon ih je spojio po dokumentima"


def test_M10_spajanje_u_jednu_spornu_tacku_je_ubijeno():
    r = _mat([
        _k(["CLAIM-001", "CLAIM-004"], label="datum"),
        _k(["CLAIM-002", "CLAIM-005"], label="iznos"),
    ])
    # MUTANT: unija svih clanova u jedan kandidat
    spojeno = sorted({c for k in r["kandidati"] for c in k["claim_refs"]})
    assert len(spojeno) == 4, "mutacija nije primenjena"

    skupovi = [set(k["claim_refs"]) for k in r["kandidati"]]
    assert skupovi[0] & skupovi[1] == set()
    assert len(r["kandidati"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M11 — identitet zavisan od redosleda
# ═══════════════════════════════════════════════════════════════════════════

def test_M11_identitet_zavisan_od_redosleda_je_ubijen():
    r1 = _mat([_k(["CLAIM-001", "CLAIM-004"])])["kandidati"][0]["claim_refs"]
    r2 = _mat([_k(["CLAIM-004", "CLAIM-001"])])["kandidati"][0]["claim_refs"]

    # MUTANT: identitet kao uredjena n-torka
    assert tuple(r1) != tuple(r2), "mutacija nije primenjena"
    # Kanon: clanstvo je SKUP
    assert set(r1) == set(r2)

    from shared.issue_v2 import otisak_pocetnog_skupa
    assert otisak_pocetnog_skupa(r1) == otisak_pocetnog_skupa(r2)


# ═══════════════════════════════════════════════════════════════════════════
# M14 — projekcija kroz legacy dedupe_key
# ═══════════════════════════════════════════════════════════════════════════

def test_M14_projekcija_kroz_legacy_dedupe_key_je_ubijena():
    """Dokaz koji §14 trazi pre skidanja legacy collapse-a."""
    sirove = [
        _k(["CLAIM-001", "CLAIM-004"], label="datum",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
        _k(["CLAIM-002", "CLAIM-005"], label="iznos",
           lokacija_1="DOK-01 str.1", lokacija_2="DOK-02 str.1"),
    ]
    # MUTANT: projekcioni kljuc = legacy dedupe_key
    legacy = {contradiction_dedupe_key(k) for k in sirove}
    assert len(legacy) == 1, "mutacija nije primenjena"

    # Kanon: kljuc mora biti izveden iz V2 entiteta. Skupovi tvrdnji su razliciti,
    # pa ce i perzistirani `predmet_contradictions.id` biti razlicit.
    r = _mat(sirove)
    assert len({tuple(sorted(k["claim_refs"])) for k in r["kandidati"]}) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M15 — kljuc obavestenja bez opsega predmeta
# ═══════════════════════════════════════════════════════════════════════════

def test_M15_kljuc_obavestenja_bez_predmeta_je_ubijen():
    """Zakljucava nalaz iz A013 (GAP-4), reprodukovan uzivo kao `23505`.

    `case_actions` je jedinstven po `(predmet_id, dedupe_key)`, a `notifications`
    po `(user_id, dedupe_key)` — bez `predmet_id`. Dok god je projekcioni kljuc
    izveden iz oznaka `DOK-NN`, koje se ponavljaju u svakom predmetu, dva
    predmeta istog advokata kolidiraju."""
    korenska = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(korenska, "migrations", "099_case_actions.sql"),
              encoding="utf-8", errors="ignore") as f:
        m099 = f.read()
    with open(os.path.join(korenska, "migrations", "101_notifications_dedupe_key.sql"),
              encoding="utf-8", errors="ignore") as f:
        m101 = f.read()

    assert "case_actions(predmet_id, dedupe_key)" in m099
    assert "notifications(user_id, dedupe_key)" in m101
    assert "notifications(predmet_id" not in m101, (
        "opseg obavestenja je promenjen — GAP-4 treba ponovo izmeriti")

    # A kljuc koji bi se projektovao je danas izveden iz oznaka dokumenata, koje
    # NISU jedinstvene po predmetu:
    a = contradiction_dedupe_key({"lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-02 str.1"})
    b = contradiction_dedupe_key({"lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-02 str.1"})
    assert a == b, "dva predmeta bi dobila isti kljuc obavestenja"


# ═══════════════════════════════════════════════════════════════════════════
# Vokabular relacija se ne duplira
# ═══════════════════════════════════════════════════════════════════════════

def test_relation_vocabulary_ima_jednog_vlasnika():
    """A014 §7: REUSE postojeceg vokabulara, ne paralelni enum."""
    import shared.contradiction_materializer as cm
    izvor = open(cm.__file__, encoding="utf-8").read()
    kod = izvor.split('"""', 2)[-1]
    assert "from shared.issue_v2 import" in izvor
    for izmisljeno in ('"cinjenica_cinjenica"', "'cinjenica_cinjenica'",
                       "FACT_FACT", "FACT_NORM"):
        assert izmisljeno not in kod, f"materializer prepisuje vokabular: {izmisljeno}"
    assert RELACIJE == frozenset({"cinjenica_cinjenica", "cinjenica_norma"})


def test_prompt_trazi_TACNO_kanonske_vrednosti_relacije():
    p = cd._GENOME_SYSTEM
    for v in sorted(RELACIJE):
        assert f'"{v}"' in p, f"prompt ne trazi kanonsku vrednost {v}"
    assert "FACT_FACT" not in p and "FACT_NORM" not in p, "paralelni vokabular u promptu"
