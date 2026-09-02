# -*- coding: utf-8 -*-
"""FAZA 6.2.1 → 6.4 — GRANICA PROVENIJENCIJE: rupa je zatvorena, evo dokaza.

ISTORIJA
========
FAZA 6.2 je kapiju vezala za `akter`. FAZA 6.2.1 je dokazala da je to pogresno:
`api.py::predmet_upload_auto_analyze` upisuje u `akter` TEKST IZ MODELA (prompt:
"Ko je preduzeo radnju (osoba, firma, sud...)"), pa je AI-ekstrahovan rok stizao
kao "Poslodavac DOO Sever" i prolazio kao ljudski unos.

Izmereno tada: **49/55 redova je prolazilo kapiju bez ijedne potvrde**, od toga
27 podobno za email/SMS podsetnik.

STA JE SADA (migracija 127)
===========================
Kanonska provenijencija je `predmet_hronologija.izvor` — `NOT NULL`, `CHECK` nad
sest vrednosti, **BEZ DEFAULT-a**. `akter` je vracen na svoje jedino znacenje:
ko je izvrsio radnju u dogadjaju.

Ovaj fajl vise ne dokumentuje rupu — dokazuje da je zatvorena, i da `akter`
NIKAKO ne moze da utice na odluku kapije.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rokovi import (  # noqa: E402
    IZVOR_DOZVOLJENI, je_ai_poreklo, sme_pokrenuti_obavezu,
)


def _red(**kw):
    r = {"id": "r-1", "vaznost": "kritičan", "predmet_id": "p-1"}
    r.update(kw)
    return r


# ═══════════════════════════════════════════════════════════════════════════
# 1. TRUTH TABLE — sada nad `izvor`, ne nad `akter`
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("opis,red,ocekivano", [
    ("AI autonomno — nepotvrdjeno",  _red(izvor="AI_AUTONOMOUS"),  False),
    ("Legacy — poreklo nedokazivo",  _red(izvor="LEGACY_UNKNOWN"), False),
    ("AI asistirano",                _red(izvor="AI_ASSISTED"),    False),
    ("Ljudski unos",                 _red(izvor="HUMAN_DIRECT"),   False),
    ("Deterministicki katalog",      _red(izvor="DETERMINISTIC"),  False),
    ("Sistemski zapis",              _red(izvor="SYSTEM"),         False),
    ("`izvor` kljuc ODSUTAN",        _red(),                       False),
    ("`izvor` je None",              _red(izvor=None),             False),
    ("`izvor` nepoznata vrednost",   _red(izvor="NESTO_TRECE"),    False),
])
def test_truth_table_nad_izvorom(opis, red, ocekivano):
    """DENY = False, ALLOW = True, bez potvrda (`set()`).

    FAZA 6.4.2: provenijencija VISE NE ODLUCUJE. Nijedna vrednost `izvor`-a ne
    otvara kapiju — ni `HUMAN_DIRECT`. Jedino ovlascenje je ljudska potvrda."""
    assert sme_pokrenuti_obavezu(red, set()) is ocekivano, opis


def test_odsutan_izvor_je_fail_closed():
    """`izvor` je `NOT NULL`, pa odsutan kljuc moze znaciti SAMO da ga upit nije
    dovukao. Pogadjanje na osnovu nedostajuceg podatka je otvorilo prethodnu rupu.

    Meri se BEZ potvrde: potvrda je jaci signal od provenijencije, pa red koji je
    covek izricito odobrio sme da prodje i kad mu poreklo nije poznato."""
    assert sme_pokrenuti_obavezu({"id": "x", "vaznost": "kritičan"}, set()) is False
    # a potvrdjen red prolazi -- potvrda je ovlascenje, provenijencija nije
    assert sme_pokrenuti_obavezu({"id": "x", "vaznost": "kritičan"}, {"x"}) is True


def test_potvrda_otvara_kapiju_za_SVAKU_klasu():
    """Potvrda je jedina osa koja daje ALLOW — i vazi jednako za sve klase."""
    for izvor in IZVOR_DOZVOLJENI:
        assert sme_pokrenuti_obavezu(_red(izvor=izvor), {"r-1"}) is True, izvor


def test_sest_kanonskih_vrednosti_i_ni_jedna_vise():
    assert IZVOR_DOZVOLJENI == (
        "AI_AUTONOMOUS", "AI_ASSISTED", "HUMAN_DIRECT",
        "DETERMINISTIC", "SYSTEM", "LEGACY_UNKNOWN")
    # FAZA 6.4.2: pojam "klase koje smeju bez potvrde" VISE NE POSTOJI.
    import shared.rokovi as _R
    assert not hasattr(_R, "IZVOR_SME_BEZ_POTVRDE"),         "vratio se koncept 'provenijencija sme bez potvrde' — to je RED-1"
    assert not hasattr(_R, "IZVOR_TRAZI_POTVRDU")


# ═══════════════════════════════════════════════════════════════════════════
# 2. §17 — `akter` i `izvor` su RAZDVOJENI
# ═══════════════════════════════════════════════════════════════════════════

def test_stvarni_red_iz_rupe_je_sada_DENY():
    """Tacan oblik koji je u FAZI 6.2.1 prolazio: `akter` je ime stranke koje je
    izvukao model. Sa `izvor='AI_AUTONOMOUS'` sada pada."""
    red = {
        "id": "r-upload-1", "predmet_id": "p-1", "user_id": "u-1",
        "dokument_naziv": "resenje_o_otkazu.docx",
        "datum_iso": "2026-02-15", "dogadjaj": "Poslodavac dostavio resenje",
        "akter": "Poslodavac DOO Sever",
        "izvor": "AI_AUTONOMOUS",
        "vaznost": "kritičan",
    }
    assert sme_pokrenuti_obavezu(red, set()) is False


@pytest.mark.parametrize("akter", [
    "Poslodavac DOO Sever", "Advokat", "Genome (AI)", "", None, "Sud u Beogradu",
])
def test_akter_NE_UTICE_na_odluku(akter):
    """Ista `izvor` vrednost mora dati isti ishod bez obzira na `akter`.
    Ovo je invarijanta koja je nedostajala i zbog koje je rupa i nastala."""
    ai = sme_pokrenuti_obavezu(_red(akter=akter, izvor="AI_AUTONOMOUS"), set())
    hum = sme_pokrenuti_obavezu(_red(akter=akter, izvor="HUMAN_DIRECT"), set())
    assert ai is False and hum is False, akter          # bez potvrde: oba DENY
    assert sme_pokrenuti_obavezu(_red(akter=akter, izvor="HUMAN_DIRECT"), {"r-1"}) is True


def test_akter_koji_izgleda_kao_ai_ne_blokira_ljudski_red():
    """Obrnut smer: `akter='Genome (AI)'` uz `izvor='HUMAN_DIRECT'` je validna
    kombinacija (npr. advokat opisuje sta je AI uradio) i NE SME biti blokiran."""
    assert sme_pokrenuti_obavezu(
        _red(akter="Genome (AI)", izvor="HUMAN_DIRECT"), {"r-1"}) is True


def test_je_ai_poreklo_vise_nije_deo_odluke():
    """Funkcija je zadrzana za prikaz i istoriju. Da je jos u kapiji, gornji
    test bi pao."""
    assert je_ai_poreklo("Genome (AI)") is True          # i dalje tacna tvrdnja o `akter`
    assert sme_pokrenuti_obavezu(                        # ali bez uticaja na kapiju
        _red(akter="Genome (AI)", izvor="HUMAN_DIRECT"), {"r-1"}) is True


def test_upload_put_i_dalje_upisuje_llm_tekst_u_akter():
    """Izvor je NEPROMENJEN — i to je ispravno. `akter` sme da nosi ime stranke;
    greska je bila citati ga kao poreklo. Ovaj test cuva da se ne "popravi"
    pogresna strana problema."""
    with open(os.path.join(os.path.dirname(__file__), "..", "api.py"), encoding="utf-8") as fh:
        s = fh.read()
    assert '"akter":          str(ev.get("akter") or "")[:200],' in s
