# -*- coding: utf-8 -*-
"""
TASK 3G.2 — kontaminacija Strategic Orchestrator promptova konkretnim zakonima.

ODAKLE JE DOŠAO ZUP
Prvi stvarni PRO run (TEST-3F) vratio je "čl. 42 ZUP, Sl. gl. RS 18/2016" kao
formalni nedostatak u PRIVREDNOM SPORU dva d.o.o., gde se Zakon o opštem
upravnom postupku uopšte ne primenjuje. Navod se ponovio u tri modula.

Uzrok NIJE bila halucinacija modela. `_ORK_REVIZOR_SYSTEM` je doslovno sadržao:

    'ZAKONE ... citiraj iz sopstvenog stručnog znanja — "čl. 9 st. 1 ZUP,
     Sl. gl. RS 18/2016", "čl. 101 ZPP" itd. To NIJE halucinacija, to je
     tvoja stručnost.'

Model je prepisao primer iz prompta i preneo ga u pogrešnu granu prava. Isti
obrazac je bio i u JSON šemi izlaza (`zakonski_osnov: "npr. čl. 98 st. 1 ZPP
ili čl. 205 ZUP"`) i u `_ORK_RED_TEAM_SYSTEM`.

ŠTA OVI TESTOVI ŠTITE
Da se konkretan propis ne vrati u prompt kao "primer formata". Opšte pravilo o
zabrani izmišljanja referenci mora ostati -- brisanje primera ne sme oslabiti
anti-halucinacionu zaštitu.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

# Propisi koji su se pojavljivali kao primeri u promptu i curili u izlaz.
ZABRANJENI = ("ZUP", "Sl. gl. RS", "ZPP", 'ZR"')

CILJANI = ("_ORK_REVIZOR_SYSTEM", "_ORK_RED_TEAM_SYSTEM")


def _prompt(name: str) -> str:
    p = getattr(strategija, name, None)
    assert isinstance(p, str) and p, f"{name} ne postoji ili nije string"
    return p


# ─── TEST A / B — ciljani promptovi očišćeni ─────────────────────────────────

@pytest.mark.parametrize("name", CILJANI)
def test_ab_ciljani_prompt_nema_konkretan_propis_kao_primer(name):
    """Nijedan konkretan propis ne sme stajati kao ilustracija formata."""
    p = _prompt(name)
    nadjeno = [z for z in ZABRANJENI if z in p]
    assert not nadjeno, (
        f"{name} i dalje sadrži {nadjeno} -- model prepisuje takav primer u "
        f"izlaz, što je i proizvelo ZUP u privrednom sporu (TEST-3F)"
    )


@pytest.mark.parametrize("name", CILJANI)
def test_ab2_uklonjena_tvrdnja_da_citiranje_nije_halucinacija(name):
    """Formulacija koja ohrabruje citiranje po sećanju ne sme se vratiti."""
    p = _prompt(name).lower()
    assert "nije halucinacija" not in p, (
        f"{name} i dalje modelu poručuje da je citiranje po sećanju stručnost"
    )


# ─── TEST C — opšte pravilo je SAČUVANO ──────────────────────────────────────

@pytest.mark.parametrize("name", CILJANI)
def test_c_opste_anti_halucinaciono_pravilo_ostaje(name):
    """Brisanje primera ne sme oslabiti zabranu izmišljanja referenci."""
    p = _prompt(name)
    assert "ANTI-HALUCINACIJA" in p, f"{name} je izgubio anti-halucinacioni blok"
    assert re.search(r"ZABRANJENO je izmišljati", p), (
        f"{name} više ne zabranjuje izmišljanje"
    )
    assert "proveriti" in p.lower(), (
        f"{name} više ne traži označavanje nesigurne reference kao 'proveriti'"
    )
    assert "relevantn" in p.lower(), (
        f"{name} više ne traži da propis bude relevantan za konkretan predmet"
    )


# ─── OČUVANJE — moduli van obima NISU dirani ─────────────────────────────────

def test_d_moduli_van_obima_nisu_menjani():
    """3G.2 sme da dira SAMO Revizor i Red Team.

    Kontaminacija postoji i u Due Diligence i u Presudi (AI Sudija), ali je
    zadatak izričito zabranio njihovu izmenu. Ovaj test to zaključava: ako neko
    kasnije "usput" očisti i njih, mora to uraditi svesno, sopstvenim taskom.
    """
    assert "ZUP" in strategija._ORK_DUE_DILIGENCE_SYSTEM, (
        "Due Diligence je promenjen van obima 3G.2 -- vidi nalaz F-3G2-001"
    )
    assert "ZUP" in strategija._ORK_PRESUDA_SYSTEM, (
        "Presuda/AI Sudija je promenjena van obima 3G.2 -- AI Sudija je jedini "
        "modul koji je u TEST-3F radio dobro (4/5) i ne dira se bez potrebe"
    )


def test_e_witness_i_synthesis_ostaju_cisti():
    """Ova dva prompta nikad nisu bila kontaminirana -- regresioni pojas."""
    for name in ("_ORK_WITNESS_SYSTEM", "_ORK_SYNTHESIS_SYSTEM"):
        p = _prompt(name)
        assert not [z for z in ZABRANJENI if z in p], f"{name} je kontaminiran"
