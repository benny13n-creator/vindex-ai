# -*- coding: utf-8 -*-
"""
PRG-P1-COI-CONVERGENCE-001 — Intake COI mora da donosi ISTU odluku kao kanonski.

Isti poslovni pojam ("da li je ovo ista stranka?") imao je tri nezavisne
implementacije. Kanonska (`routers/conflict_check.py`) je popravljena u
`abfbaeca`. Intake (`routers/intake.py`) je zadrzao golu supstring proveru

    return query in candidate or candidate in query

bez praga, a `_norm` ne skida pravne nastavke — pa "firma doo" jeste sadrzano
u "druga firma doo" i Intake Wizard je prikazivao BLOKIRAJUCI sukob interesa
za dve nepovezane firme.

Invarijanta koju ovaj fajl cuva NIJE "nema laznih pozitiva" nego strozija:

    KANONSKA_ODLUKA == INTAKE_ODLUKA

Zato svaki slucaj poredi obe implementacije, a ne samo ocekivanu vrednost.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CLEAR = False
CONFLICT = True

# ── Dokazani lazni pozitivi iz PRG-P1-PREPUSH-001 ────────────────────────────
LAZNI_POZITIVI = [
    ("Firma doo",             "Druga firma doo"),
    ("Nova",                  "Nova Komerc"),
]

# ── Razlicite stranke — ne smeju da daju sukob ───────────────────────────────
RAZLICITE = [
    ("Firma doo",             "Druga firma doo"),
    ("Nova",                  "Nova Komerc"),
    ("AB Komerc",             "XY Komerc"),
    ("Delta doo",             "Delta Inženjering doo"),
    ("Milan Jovanović",       "Milica Jovanović"),
    ("Delta Inženjering doo", "Alfa Trgovina doo"),
    ("Ana Anić",              "Jovan Anić"),
    ("Marko Marković",        "Marko Marić"),
    ("AB",                    "AB Komerc"),
]

# ── Ista stranka — MORA da da sukob (odbrana od laznih negativa) ─────────────
ISTE = [
    ("Petar Petrović",        "Petar Petrović"),
    ("Petar Petrović",        "PETAR  PETROVIĆ"),          # velicina slova + razmaci
    ("Petrović Petar",        "Petar Petrović"),           # redosled reci
    ("Petar M. Petrović",     "Petar Petrović"),           # srednje ime
    ("Delta Inženjering doo", "Delta Inženjering d.o.o."), # varijanta nastavka
    ("Delta doo",             "Delta d.o.o."),             # varijanta nastavka
    ("Delta Inženjering",     "Delta Inženjering Beograd"),# ogranak
    ("Delta Inženjering doo", "Delta Inžinjering doo"),    # tipfeler
    ("Čačak Komerc",          "Cacak Komerc"),             # dijakritici
    ("Петар Петровић",        "Petar Petrović"),           # cirilica -> latinica
    # Parovi u opsegu 70..84 — izmedju CONFLICT_WARN i CONFLICT_HARD. Bez njih
    # matrica ne razlikuje `>= CONFLICT_WARN` od `>= CONFLICT_HARD`, pa bi
    # Intake mogao tiho da koristi strozi prag i da se razidje sa kanonskom.
    ("Petar Petrović",        "Petra Petrovci"),           # skor 84 (dve transpozicije)
    ("Delta Inženjering Beograd Servis",
     "Delta Inženjering Beograd Trgovina"),                # skor 75 (3 od 4 tokena)
]

SVE = ([(a, b, CLEAR) for a, b in RAZLICITE]
       + [(a, b, CONFLICT) for a, b in ISTE])


def _kanonska(a: str, b: str) -> bool:
    """Bulova odluka kanonske implementacije: skor >= CONFLICT_WARN."""
    from routers.conflict_check import CONFLICT_WARN, _fuzzy_score
    return _fuzzy_score(a, b) >= CONFLICT_WARN


def _intake(a: str, b: str) -> bool:
    """Odluka Intake implementacije, tacno kako je pozivaju njena mesta:
    ulaz se prvo provuce kroz `_norm`, pa kroz `_name_match`."""
    from routers.intake import _name_match, _norm
    return bool(_name_match(_norm(a), _norm(b)))


@pytest.mark.parametrize("a,b", LAZNI_POZITIVI, ids=[f"{a}|{b}" for a, b in LAZNI_POZITIVI])
def test_dokazani_lazni_pozitivi_vise_ne_postoje(a, b):
    """Reprodukcija blokera iz PRG-P1-PREPUSH-001. Pada PRE popravke."""
    assert not _intake(a, b), (
        f"Intake i dalje prijavljuje sukob za {a!r} vs {b!r} — "
        f"Intake Wizard prikazuje BLOKIRAJUCI sukob za nepovezane stranke")


@pytest.mark.parametrize("a,b,ocekivano", SVE, ids=[f"{a}|{b}" for a, b, _ in SVE])
def test_intake_donosi_istu_odluku_kao_kanonska(a, b, ocekivano):
    """Strozi ugovor: ne samo tacna odluka, nego ISTA odluka kao kanonska."""
    kan = _kanonska(a, b)
    inp = _intake(a, b)
    assert kan == ocekivano, (
        f"kanonska implementacija se ne slaze sa ocekivanjem za {a!r} vs {b!r}: "
        f"kanonska={kan}, ocekivano={ocekivano} — proveri ocekivanje, ne Intake")
    assert inp == kan, (
        f"{a!r} vs {b!r}: kanonska={kan}, intake={inp} — implementacije se razilaze")


@pytest.mark.parametrize("a,b", [(a, b) for a, b in ISTE], ids=[f"{a}|{b}" for a, b in ISTE])
def test_prave_podudarnosti_prezivljavaju(a, b):
    """Odbrana od laznih negativa: popravka ne sme da oslepi proveru."""
    assert _intake(a, b), (
        f"Intake vise NE prepoznaje istu stranku {a!r} vs {b!r} — "
        f"propusten sukob je teza greska od suvisne oznake")


def test_simetrija_odluke():
    """Redosled stranaka ne sme da menja verdikt."""
    razlike = [(a, b) for a, b, _ in SVE if _intake(a, b) != _intake(b, a)]
    assert not razlike, f"odluka zavisi od redosleda za: {razlike}"


def test_prazan_ulaz_nikad_nije_sukob():
    from routers.intake import _name_match, _norm
    for prazno in ("", "   ", "..."):
        assert not _name_match(_norm(prazno), _norm("Petar Petrović"))
        assert not _name_match(_norm("Petar Petrović"), _norm(prazno))


# ── T8: STVARNI produkcioni put — POST /api/intake/conflict-check ────────────
#
# Jedinicni test nad `_name_match` ne dokazuje sta advokat vidi. Ovde se poziva
# prava funkcija rute, sa pravim `_run_conflict_check` ispod nje, i proverava se
# `has_blocker` — polje na kome Intake Wizard (`static/vindex.js:21690`)
# zaustavlja tok i ispisuje "🚫 Sukob interesa — BLOKIRAJUCI".

def _lazni_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST", "path": "/api/intake/conflict-check",
                    "headers": [], "query_string": b"",
                    "client": ("127.0.0.1", 0), "server": ("testserver", 80),
                    "scheme": "http", "root_path": "", "app": None})


_UID = "aaaa0000-0000-4000-8000-00000000000a"
_KID = "bbbb0000-0000-4000-8000-00000000000b"
_PID = "cccc0000-0000-4000-8000-00000000000c"


def _supa_sa_klijentom(ime, prezime, firma, uloga):
    """`uloga` mora biti iz `_CLIENT_ROLES`/`_OPPOSING_ROLES` — proizvoljna
    vrednost tiho ne bi proizvela nijedan nalaz i test bi lazno prolazio."""
    from unittest.mock import MagicMock
    klijent = {"id": _KID, "ime": ime, "prezime": prezime, "firma": firma}
    veza = {"klijent_id": _KID, "predmet_id": _PID, "uloga_klijenta": uloga}
    predmet = {"id": _PID, "naziv": "Sintetički predmet", "tuzilac": "", "tuzeni": ""}

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [klijent]
        elif name == "predmet_klijenti":
            t.select.return_value.eq.return_value.execute.return_value.data = [veza]
            t.select.return_value.in_.return_value.execute.return_value.data = [veza]
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = [predmet]
        else:
            t.select.return_value.eq.return_value.execute.return_value.data = []
        return t

    mock.table.side_effect = _table
    return mock


async def _pozovi_rutu(novi_ime, novi_firma, protivna, supa):
    from unittest.mock import patch
    import routers.intake as intake

    req = intake.ConflictCheckIntakeReq(
        novi_klijent_ime=novi_ime, novi_klijent_firma=novi_firma,
        protivna_strana=protivna, pib="",
    )
    # `@limiter.limit` zahteva pravi starlette Request; poziva se nedekorisana
    # funkcija rute, ali SVE ispod nje (`_run_conflict_check`, `_name_match`,
    # `_norm`, gradnja odgovora) je produkcioni kod.
    ruta = getattr(intake.intake_conflict_check, "__wrapped__", intake.intake_conflict_check)
    zahtev = _lazni_request()
    with patch.object(intake, "_get_supa", return_value=supa):
        return await ruta(req, zahtev, {"user_id": _UID})


@pytest.mark.anyio
async def test_t8_slucaj_A_nepovezana_firma_NE_blokira_intake():
    """Postoji klijent 'Druga firma doo'; nova protivna strana je 'Firma doo'.

    Pre popravke: `_name_match` je vracao True (supstring), uloga klijenta je u
    `_CLIENT_ROLES`, pa je nastajao BLOKIRAJUCI sukob i Wizard je stao.
    """
    supa = _supa_sa_klijentom("", "", "Druga firma doo", "stranka")
    rez = await _pozovi_rutu("Novi Klijent", "", "Firma doo", supa)

    assert rez["status_provere"] == "NO_CONFLICT", (
        f"nepovezana firma i dalje pravi sukob: {rez.get('conflicts')}")
    assert rez["conflict_detected"] is False
    assert rez["has_blocker"] is False, "Intake Wizard bi i dalje bio blokiran"


@pytest.mark.anyio
async def test_t8_slucaj_B_ista_stranka_i_dalje_blokira_intake():
    """Postoji klijent 'Petar Petrović'; protivna strana je 'Petar Petrović'.

    Popravka ne sme da oslepi proveru — pravi sukob mora i dalje da blokira.
    """
    supa = _supa_sa_klijentom("Petar", "Petrović", "", "stranka")
    rez = await _pozovi_rutu("Novi Klijent", "", "Petar Petrović", supa)

    assert rez["status_provere"] == "CONFLICT_FOUND"
    assert rez["conflict_detected"] is True
    assert rez["has_blocker"] is True, "pravi sukob vise ne blokira Wizard"


@pytest.mark.anyio
async def test_t8_slucaj_C_cirilica_sada_nalazi_sukob():
    """Lazni NEGATIV pre popravke: klijent zaveden latinicom, unos cirilicom."""
    supa = _supa_sa_klijentom("Petar", "Petrović", "", "stranka")
    rez = await _pozovi_rutu("Novi Klijent", "", "Петар Петровић", supa)

    assert rez["has_blocker"] is True, (
        "unos cirilicom i dalje ne nalazi postojeceg klijenta — propusten sukob")
