# -*- coding: utf-8 -*-
"""FAZA 6.2.1 — GRANICA PROVENIJENCIJE: sta kapija radi kad signal NIJE dostupan.

STA OVAJ FAJL DOKAZUJE
======================
FAZA 6.2 je uvela `shared/rokovi.py::sme_pokrenuti_obavezu` i poreklo cita iz
POSTOJECEG polja `akter`. Ovaj audit napada bas tu pretpostavku.

NALAZ (RED): `akter` NIJE polje provenijencije. Ono je PREOPTERECENO:

  * vecina pisaca upisuje POTPIS PROIZVODJACA  ("Genome (AI)", "Smart Intake",
    "Advokat", "Automatski — ZPP lanac | ...");
  * ali `api.py::predmet_upload_auto_analyze` (`POST /api/predmeti/{id}/upload`)
    upisuje `str(ev.get("akter"))` — **tekst koji je vratio model**, po sopstvenoj
    shemi "Ko je preduzeo radnju (osoba, firma, sud...)".

Zato AI-ekstrahovan rok stize do kapije sa `akter="Poslodavac DOO Sever"` i
prolazi kao ljudski unos.

Izmereno na produkciji u trenutku audita: **49/55 redova prolazi kapiju**, svih
49 ima `dokument_naziv` (postavlja ga bas taj AI put), a **27 njih je podobno za
podsetnik** (`kritičan`/`važan`).

STA OVAJ FAJL NE RADI
=====================
Ne popravlja rupu. Izbor izmedju fail-open (tiha opasnost) i fail-closed (tihi
gubitak legitimnih rokova) je bezbednosna politika, ne inzenjerska sitnica, i
trazi odluku vlasnika. Testovi ovde ZAKLJUCAVAJU izmerenu istinu da se ne bi
izgubila i da bi popravka imala od cega da krene.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rokovi import je_ai_poreklo, sme_pokrenuti_obavezu  # noqa: E402


def _red(**kw):
    r = {"id": "r-1", "vaznost": "kritičan", "predmet_id": "p-1"}
    r.update(kw)
    return r


# ═══════════════════════════════════════════════════════════════════════════
# 1. TRUTH TABLE — stvarno ponasanje, mereno pozivanjem funkcije
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("opis,red,ocekivano", [
    ("Known AI #1 — Genome",        _red(akter="Genome (AI)"),          False),
    ("Known AI #2 — Pipeline",      _red(akter="Pipeline (AI)"),        False),
    ("Human — advokat",             _red(akter="Advokat"),              True),
    ("NULL akter",                  _red(akter=None),                   True),
    ("Empty akter",                 _red(akter=""),                     True),
    ("Missing akter kljuc",         _red(),                             True),
    ("Unknown provenance",          _red(akter="Future AI Agent"),      True),
    ("Unknown — 'Unknown'",         _red(akter="Unknown"),              True),
])
def test_truth_table_stvarno_ponasanje(opis, red, ocekivano):
    """DENY = False, ALLOW = True. Bez potvrda (`set()`), kao u produkciji danas."""
    assert sme_pokrenuti_obavezu(red, set()) is ocekivano, opis


@pytest.mark.parametrize("akter,je_ai", [
    ("Genome (AI)", True), ("Pipeline (AI)", True),
    (None, False), ("", False), ("Unknown", False), ("Future AI Agent", False),
    # Stvarne vrednosti iz produkcije, sve sa AI upload puta:
    ("Poslodavac DOO Sever", False), ("Zaposleni Marko Petrović", False),
    ("DOO Alfa Trejd", False),
])
def test_je_ai_poreklo_je_whitelist_a_ne_detekcija(akter, je_ai):
    """`je_ai_poreklo` je poredjenje sa fiksnom listom. Sve van nje je 'ljudsko',
    ukljucujuci imena stranaka koja upisuje AI ekstrakcija."""
    assert je_ai_poreklo(akter) is je_ai


# ═══════════════════════════════════════════════════════════════════════════
# 2. MISSING-1..6 — izmereni ishodi
# ═══════════════════════════════════════════════════════════════════════════

def test_MISSING_1_poznat_ai_je_DENY():
    assert sme_pokrenuti_obavezu(_red(akter="Genome (AI)"), set()) is False


def test_MISSING_2_odsutan_kljuc_je_ALLOW():
    """Odsutan `akter` -> `red.get()` vrati None -> `("" ) in AI_AKTERI` = False."""
    assert sme_pokrenuti_obavezu(_red(), set()) is True


def test_MISSING_3_none_je_ALLOW():
    assert sme_pokrenuti_obavezu(_red(akter=None), set()) is True


def test_MISSING_4_prazan_string_je_ALLOW():
    assert sme_pokrenuti_obavezu(_red(akter=""), set()) is True


def test_MISSING_5_nepoznat_ai_agent_je_ALLOW():
    assert sme_pokrenuti_obavezu(_red(akter="Future AI Agent"), set()) is True


def test_MISSING_6_unknown_je_ALLOW():
    assert sme_pokrenuti_obavezu(_red(akter="Unknown"), set()) is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. STVARNI OBLIK REDA SA AI UPLOAD PUTA
# ═══════════════════════════════════════════════════════════════════════════

def _red_sa_upload_puta():
    """Tacan oblik koji gradi `api.py::predmet_upload_auto_analyze` (linija 6100):
    `akter` je `str(ev.get("akter") or "")` — tekst iz LLM odgovora."""
    return {
        "id": "r-upload-1",
        "predmet_id": "p-1",
        "user_id": "u-1",
        "dokument_naziv": "resenje_o_otkazu.docx",
        "datum": "15.02.2026",
        "datum_iso": "2026-02-15",
        "dogadjaj": "Poslodavac dostavio resenje o otkazu",
        "akter": "Poslodavac DOO Sever",
        "vaznost": "kritičan",
    }


def test_ai_ekstrahovan_rok_sa_upload_puta_PROLAZI_kapiju():
    """DOKUMENTOVANA RUPA, ne zeljeno ponasanje.

    Ovaj rok je proizveo model iz advokatovog dokumenta, niko ga nije potvrdio,
    i `vaznost` je `kritičan` — dakle podoban je za email i SMS. Kapija ga
    propusta jer `akter` nosi ime stranke, ne potpis proizvodjaca."""
    assert sme_pokrenuti_obavezu(_red_sa_upload_puta(), set()) is True


@pytest.mark.xfail(strict=True, reason=(
    "OTVORENA RUPA (FAZA 6.2.1): `akter` je preopterecen — `predmet_upload_auto_"
    "analyze` upisuje LLM tekst u isto polje iz kog kapija cita poreklo. Kad se "
    "granica popravi, ovaj test pocinje da PROLAZI i treba ga pretvoriti u "
    "obican assert. Do tada `strict=True` javlja ako neko misli da je zatvoreno."))
def test_CILJ_ai_ekstrahovan_rok_treba_da_bude_DENY():
    assert sme_pokrenuti_obavezu(_red_sa_upload_puta(), set()) is False


def test_upload_put_i_dalje_upisuje_llm_tekst_u_akter():
    """Izvor rupe. Ako se ovo promeni, gornji `xfail` treba ponovo proceniti."""
    with open(os.path.join(os.path.dirname(__file__), "..", "api.py"), encoding="utf-8") as fh:
        s = fh.read()
    assert '"akter":          str(ev.get("akter") or "")[:200],' in s, \
        "izvor `akter` na upload putu je promenjen — proveriti granicu ponovo"


def test_potvrda_i_dalje_otvara_kapiju_za_poznat_ai():
    """Regresija FAZE 6.2: mehanizam potvrde nije pokvaren ovim auditom."""
    assert sme_pokrenuti_obavezu(_red(akter="Genome (AI)"), {"r-1"}) is True
