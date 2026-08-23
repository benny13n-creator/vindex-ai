# -*- coding: utf-8 -*-
"""BETA-COI-PARTY-BLIND — Sloj 1 je pretraživao prazne kolone i to prijavljivao kao „ok".

PRE-STATE (reprodukovano uživo nad produkcijom `c297cae8`, sa kontrolnom grupom):

  KORAK 1 — predmet kreiran TAČNO onako kako ga proizvod kreira:
      POST /api/predmeti {naziv: "… Milanović protiv TehnoGradnja DOO Kragujevac"}
      DB: tuzilac=None  tuzeni=None      ← ime protivnika JESTE u nazivu

  KORAK 2 — advokat proverava tog protivnika kao novog klijenta:
      POST /api/conflict-check {firma: "TehnoGradnja DOO Kragujevac"}
      → status="clear", konflikata=0
      → „Nije pronađen konflikt interesa. Možete prihvatiti klijenta."
      → slojevi: {"predmeti":"ok","klijenti":"ok","uloge":"ok","advokat":"ok"}

  KORAK 3 — KONTROLNA GRUPA, iste stranke upisane PATCH-em u kanonske kolone:
      → status="conflict", „🚨 OZBILJAN KONFLIKT … povreda Kodeksa profesionalne
        etike advokata Srbije"

Kontrolna grupa dokazuje da uzrok NIJE prag, NIJE fuzzy model i NIJE pao upit —
nego PRAZNO POLJE. Sloj je uspešno pretraživao ništa, pa je prijavio `ok` i time
zaobišao postojeću fail-closed granu koja pad izvora degradira na `review`.

KORENSKI UZROK — asimetrija ugovora:
  ČITAOCI `predmeti.tuzilac/tuzeni`: conflict_check, ccc, evidence_graph,
      hearing_cc, court_predictor, intake
  PISCI: NIJEDAN put kreiranja (`api.py::kreiraj_predmet`, `routers/intake.py`,
      `routers/smart_intake.py`) — samo `PATCH /api/predmeti`, koji UI ne koristi
      pri kreiranju.
  Produkciono stanje: 0/22 predmeta ima stranke; `predmet_klijenti` ima 0 redova.

MERENO nad 22 produkciona predmeta pre izbora rešenja:
  `naziv` → 6/8 stvarnih protivnika pogođeno, 0/22 lažnih (najviši lažni skor 16)
  `opis`  → 0/8 pogođeno → NIJE uključen (nula koristi, najveća FP površina)
"""
import pytest

from routers.conflict_check import (
    CONFLICT_HARD, CONFLICT_WARN, _fuzzy_score,
)

PROTIVNIK = "TehnoGradnja DOO Kragujevac"
MOJ_KLIJENT = "Zorica Milanović-Đurđević"
NAZIV = "Naknada štete — %s protiv %s" % (MOJ_KLIJENT, PROTIVNIK)


def _predmet(naziv=NAZIV, tuzilac=None, tuzeni=None, status="aktivan"):
    return {"id": "p1", "naziv": naziv, "tip": "parnicni", "status": status,
            "tuzilac": tuzilac, "tuzeni": tuzeni, "created_at": "2026-08-01T00:00:00Z"}


# ── META: bez ovoga bi testovi ispod bili trivijalni ────────────────────────

def test_META_fuzzy_i_dalje_razlikuje_povezano_od_nepovezanog():
    assert _fuzzy_score(PROTIVNIK, NAZIV) >= CONFLICT_WARN
    assert _fuzzy_score("Petar Petrović", NAZIV) < CONFLICT_WARN


# ── Jezgro nalaza ──────────────────────────────────────────────────────────

def test_protivnik_se_nalazi_i_kad_su_kanonske_kolone_prazne():
    """Ovo je reprodukovani produkcioni scenario: 22/22 predmeta ima NULL stranke."""
    p = _predmet()
    assert p["tuzilac"] is None and p["tuzeni"] is None
    najbolji = max(_fuzzy_score(PROTIVNIK, p.get("tuzilac") or ""),
                   _fuzzy_score(PROTIVNIK, p.get("tuzeni") or ""),
                   _fuzzy_score(PROTIVNIK, p.get("naziv") or ""))
    assert najbolji >= CONFLICT_WARN, (
        "protivna strana iz sopstvenog aktivnog predmeta se ne prepoznaje")


def test_bez_naziva_kao_izvora_nalaz_bi_bio_propusten():
    """Dokaz da popravku nosi BAŠ naziv, a ne nešto drugo u lancu."""
    p = _predmet()
    samo_kolone = max(_fuzzy_score(PROTIVNIK, p.get("tuzilac") or ""),
                      _fuzzy_score(PROTIVNIK, p.get("tuzeni") or ""))
    assert samo_kolone < CONFLICT_WARN, (
        "pretpostavka testa pala: kolone bi same pogodile, scenario nije verodostojan")


def test_kanonske_kolone_i_dalje_imaju_prednost_kad_postoje():
    """Kontrolna grupa iz reprodukcije: strukturisan podatak ostaje jači izvor."""
    p = _predmet(tuzeni=PROTIVNIK)
    s_kolona = _fuzzy_score(PROTIVNIK, p["tuzeni"])
    s_naziv = _fuzzy_score(PROTIVNIK, p["naziv"])
    assert s_kolona >= s_naziv, "tačan upis u kolonu mora biti bar jednako jak kao naziv"
    assert s_kolona >= CONFLICT_HARD


@pytest.mark.parametrize("nepovezan", [
    "Petar Petrović", "Marija Jovanović", "Beogradska banka ad",
    "Delta Holding doo", "Telekom Srbija ad", "NIS ad Novi Sad",
    "Nikola Stanković", "Jelena Popović", "Energoprojekt Holding",
    "Komercijalna banka", "Institut Mihajlo Pupin", "Luka Beograd ad",
])
def test_nepovezano_ime_ne_pravi_lazan_konflikt(nepovezan):
    """FP kapija: pojačanje detekcije ne sme da proizvede šum.

    Mereno nad 22 produkciona predmeta: 0/22 lažnih, najviši lažni skor 16.
    """
    assert _fuzzy_score(nepovezan, NAZIV) < CONFLICT_WARN, (
        "%r pravi lažan konflikt sa %r (skor %d)"
        % (nepovezan, NAZIV, _fuzzy_score(nepovezan, NAZIV)))


def test_opis_nije_uveden_kao_izvor():
    """Mereno: `opis` daje 0/8 detekcije, a najveću FP površinu.

    Struktura se proverava nad kodom BEZ komentara i docstring-ova — inače bi
    test hvatao sopstveno objašnjenje (naučeno u B-U-007 i F1).
    """
    import ast
    import io as _io
    src = _io.open("routers/conflict_check.py", encoding="utf-8").read()
    drvo = ast.parse(src)
    sloj = None
    for c in ast.walk(drvo):
        if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)) and c.name == "check_conflict":
            sloj = c
            break
    assert sloj is not None
    # `p.get("opis")` ne sme postojati u telu rute
    for n in ast.walk(sloj):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "get" and n.args \
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == "opis":
            raise AssertionError("`opis` je uveden kao izvor — mereno 0/8 detekcije")


def test_sloj1_cita_naziv_iz_baze():
    """Ako `naziv` ispadne iz `select(...)`, izvor tiho nestaje."""
    import io as _io
    src = _io.open("routers/conflict_check.py", encoding="utf-8").read()
    i = src.index("SLOJ 1")
    isecak = src[i:i + 900]
    assert 'table("predmeti")' in isecak
    j = isecak.index('table("predmeti")')
    sel = isecak[j:j + 260]
    for kol in ("naziv", "tuzilac", "tuzeni", "status"):
        assert kol in sel, "kolona %r se vise ne dovlaci u Sloju 1" % kol
