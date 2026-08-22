# -*- coding: utf-8 -*-
"""B-U-006 — važnost roka se nikad ne sme tiho smanjiti.

PRE-STATE (mereno uživo nad produkcijom `e74f0c7`, 2026-08-22, 14 scenarija):
  `POST /api/predmeti/{id}/confirm-links` sa `vaznost` van tačno tri kanonske
  vrednosti vraćao je `HTTP 200, rok_dodat: true`, a u bazu upisivao
  `informativan` — najniži nivo, koji `routers/email_notif.py` NE uključuje u
  podsetnike. 10 od 14 varijanti završilo je tako:

      'kritican' (bez dijakritike) -> informativan   (kanonski: važan)
      'KRITICAN'                   -> informativan   (kanonski: važan)
      'критичан' (ćirilica)        -> informativan   (kanonski: važan)
      'bitan'                      -> informativan   (kanonski: važan)
      ' kritičan ' (razmaci)       -> informativan   (kanonski: važan)
      '' / izostavljeno            -> informativan   (kanonski: važan)

  Srpski se piše oba pisma; advokat koji otkuca `критичан` dobijao je
  informativan rok koji ga nikad ne podseti.

KANONSKI UGOVOR (postojao je i pre ovog sprinta, samo ga tri pisca nisu zvala):
  `shared/rokovi.py::normalizuj_vaznost` — docstring:
  „ZAOKRUŽUJE SE NAVIŠE, NIKAD NANIŽE. Tiho snižavanje roka je gore od
   precenjivanja: precenjen rok advokat vidi i odbaci, potcenjen ne vidi."

DOKAZANO NAD PRODUKCIONOM BAZOM:
  CHECK `vaznost IN ('kritičan','važan','informativan')` STVARNO postoji —
  5/5 pokušaja upisa van skupa palo je na 23514. Svih 52 reda su kanonska.

INVARIJANTA: nijedan ulaz ne sme da proizvede rok koji izgleda evidentiran
(`rok_dodat: true`) a ispada iz alertinga zbog nepoznate vrednosti.
"""
import ast
import io

import pytest

from shared.rokovi import normalizuj_vaznost, VAZNOST_DOZVOLJENE
from routers.email_notif import _ACTIONABLE_VAZNOST

# Tri write path-a koja su B-U-006 uzrokovala. Ako se neki odveže od
# normalizatora, `test_W*` pada.
WRITE_PATHS = [
    ("api.py", "predmet_upload_auto_analyze"),
    ("api.py", "predmet_confirm_links"),
    ("routers/copilot.py", "_handle_akcija_rok"),
]

# Ulaz -> očekivana kanonska vrednost. Nije prepisano iz koda nego iz UGOVORA:
# poznata vrednost ostaje, sve ostalo ide NAVIŠE (nikad `informativan`).
MATRIKS = [
    ("kritičan",        "kritičan"),
    ("važan",           "važan"),
    ("informativan",    "informativan"),   # eksplicitno nizak JESTE dozvoljen
    ("kritican",        "važan"),          # bez dijakritike
    ("KRITICAN",        "važan"),
    ("KRITIČAN",        "važan"),
    (" kritičan ",      "važan"),          # razmaci
    ("критичан",        "važan"),          # ćirilica
    ("critical",        "važan"),
    ("bitan",           "važan"),          # sinonim koji kanonska mapa zna
    ("kljucan",         "kritičan"),       # sinonim za CRITICAL
    ("IZMISLJENO_XYZ",  "važan"),
    ("",                "važan"),
    (None,              "važan"),
    ("x" * 300,         "važan"),
]


# ── META: bez ovoga bi ceo fajl mogao da bude prazan ────────────────────────

def test_META_ugovor_i_domen_su_ono_sto_mislimo():
    """Ako se kanonski domen ili alert lista promene, svi testovi ispod menjaju
    značenje — pa se najpre pribijaju oni sami."""
    assert VAZNOST_DOZVOLJENE == ("kritičan", "važan", "informativan")
    assert _ACTIONABLE_VAZNOST == ["kritičan", "važan"], _ACTIONABLE_VAZNOST
    assert "informativan" not in _ACTIONABLE_VAZNOST


# ── 1. Kanonska normalizacija ───────────────────────────────────────────────

@pytest.mark.parametrize("ulaz,ocekivano", MATRIKS)
def test_1_normalizacija(ulaz, ocekivano):
    assert normalizuj_vaznost(ulaz) == ocekivano


@pytest.mark.parametrize("ulaz,_", MATRIKS)
def test_2_rezultat_je_UVEK_prihvatljiv_bazi(ulaz, _):
    """Normalizator ne sme da vrati vrednost koju CHECK odbija — inače bi
    popravka samo pomerila tihi gubitak sa alertinga na upis."""
    assert normalizuj_vaznost(ulaz) in VAZNOST_DOZVOLJENE


# ── 3. KLJUČNA INVARIJANTA: nepoznato ne ispada iz alertinga ────────────────

@pytest.mark.parametrize("ulaz", [u for u, _ in MATRIKS if u != "informativan"])
def test_3_nepoznato_NIKAD_ne_ispada_iz_alertinga(ulaz):
    """Srce B-U-006. Samo eksplicitno `informativan` sme da bude van podsetnika."""
    assert normalizuj_vaznost(ulaz) in _ACTIONABLE_VAZNOST, \
        "%r bi zavrsio van alertinga" % (ulaz,)


def test_4_eksplicitan_informativan_SME_da_bude_van_alertinga():
    """Kontrola: popravka koja sve gura u `kritičan` bila bi jednako pogrešna."""
    assert normalizuj_vaznost("informativan") == "informativan"
    assert "informativan" not in _ACTIONABLE_VAZNOST


def test_5_kriticno_ostaje_kriticno():
    """Zaokruživanje naviše ne sme da izjednači nivoe."""
    assert normalizuj_vaznost("kritičan") == "kritičan"
    assert normalizuj_vaznost("kljucan") == "kritičan"
    assert normalizuj_vaznost("važan") == "važan"
    assert normalizuj_vaznost("kritičan") != normalizuj_vaznost("važan")


# ── WIRING: tri pisca moraju zvati kanonski normalizator ────────────────────

def _funkcija(fajl, ime):
    src = io.open(fajl, encoding="utf-8").read()
    drvo = ast.parse(src)
    for c in ast.walk(drvo):
        if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)) and c.name == ime:
            return ast.get_source_segment(src, c) or ""
    raise AssertionError("funkcija %s nije nadjena u %s" % (ime, fajl))


@pytest.mark.parametrize("fajl,fn", WRITE_PATHS)
def test_W1_write_path_zove_kanonski_normalizator(fajl, fn):
    telo = _funkcija(fajl, fn)
    assert "normalizuj_vaznost" in telo, \
        "%s::%s ne prolazi kroz kanonski normalizator" % (fajl, fn)


@pytest.mark.parametrize("fajl,fn", WRITE_PATHS)
def test_W2_write_path_nema_sopstveni_fallback_na_informativan(fajl, fn):
    """Tačan pre-state obrazac: `if vaznost not in {...}: vaznost = 'informativan'`."""
    telo = _funkcija(fajl, fn)
    for red in telo.split("\n"):
        kod = red.split("#")[0]
        if "=" in kod and '"informativan"' in kod and "vaznost" in kod.lower():
            raise AssertionError("%s::%s i dalje pada na 'informativan': %s"
                                 % (fajl, fn, red.strip()[:90]))


def test_W3_nijedan_pisac_ne_pravi_duplikat_normalizatora():
    """Jedan domen, jedan normalizator. Duplikat bi se razišao pri prvoj izmeni."""
    for fajl in ("api.py", "routers/copilot.py", "routers/email_notif.py"):
        src = io.open(fajl, encoding="utf-8").read()
        drvo = ast.parse(src)
        imena = [c.name for c in ast.walk(drvo)
                 if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for ime in imena:
            assert "vaznost" not in ime.lower() or "normalizuj_vaznost" == ime, \
                "%s definise sopstvenu normalizaciju: %s" % (fajl, ime)


# ── ALERTING: izveden iz domena, ne prepisan ────────────────────────────────

def test_A1_alert_lista_je_izvedena_iz_kanonskog_domena():
    src = io.open("routers/email_notif.py", encoding="utf-8").read()
    i = src.index("_ACTIONABLE_VAZNOST =")
    izraz = src[i:i + 200].split("\n")[0]
    assert "VAZNOST_DOZVOLJENE" in izraz, \
        "alert lista je opet prepisana rucno: %s" % izraz


def test_A2_alert_lista_ne_sadrzi_vrednost_koju_baza_ne_moze_da_ima():
    """INVARIJANTA iz mandata: alerting ne sme da zavisi od nekanonske vrednosti.
    `bitan`/`kljucan`/`normalan` CHECK odbija (izmereno: 23514)."""
    for v in _ACTIONABLE_VAZNOST:
        assert v in VAZNOST_DOZVOLJENE, "%r nije u domenu koji baza dozvoljava" % v
    for mrtva in ("bitan", "kljucan", "normalan", "info"):
        assert mrtva not in _ACTIONABLE_VAZNOST


# ── RESPONSE CONTRACT (B-U-006-N1) ─────────────────────────────────────────

def test_R1_copilot_odgovor_nosi_upisanu_vrednost_a_ne_sirov_AI_izlaz():
    """Ranije: DB `informativan`, odgovor `bitan`. Advokat je čitao jedan nivo,
    sistem čuvao drugi."""
    telo = _funkcija("routers/copilot.py", "_handle_akcija_rok")
    assert 'ext.get("vaznost","bitan")' not in telo.replace(" ", ""), \
        "odgovor i dalje vraca sirov AI izlaz"
    assert '"vaznost": _vaznost' in telo, "odgovor ne nosi normalizovanu vrednost"
    # ista promenljiva mora da ide i u insert i u odgovor
    assert telo.count("_vaznost") >= 3


def test_R2_upisana_i_vracena_vrednost_su_ista_promenljiva():
    telo = _funkcija("routers/copilot.py", "_handle_akcija_rok")
    posle_inserta = telo[telo.index('"vaznost":    _vaznost'):]
    assert '"vaznost": _vaznost' in posle_inserta
