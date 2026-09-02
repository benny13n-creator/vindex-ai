# -*- coding: utf-8 -*-
"""FAZA 6.4 — UGOVOR O PROVENIJENCIJI: 16 pisaca, NOT NULL, bez DEFAULT-a.

STA OVAJ FAJL DOKAZUJE
======================
1. Migracija 127 daje `NOT NULL` + `CHECK` + **BEZ DEFAULT-a** (§14).
2. Svih 16 pisaca eksplicitno salje `izvor` (§15).
3. Backfill je deterministican: sve postojece -> `LEGACY_UNKNOWN` (§16).
4. Matrica bezbednosti akcija (§18).

GRANICA
=======
Migracija NIJE pokrenuta — nema DDL kanala, pokrece je vlasnik. Testovi ovde
mere UGOVOR (sadrzaj migracije + kod pisaca), ne zivo stanje seme. Zivi dokaz
finalne seme se izvodi posle pokretanja, upitom iz zaglavlja migracije.
"""
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

KOREN = os.path.join(os.path.dirname(__file__), "..")
MIGRACIJA = os.path.join(KOREN, "migrations", "127_hronologija_izvor_provenance.sql")

KANONSKE = ("AI_AUTONOMOUS", "AI_ASSISTED", "HUMAN_DIRECT",
            "DETERMINISTIC", "SYSTEM", "LEGACY_UNKNOWN")


def _sql():
    return io.open(MIGRACIJA, encoding="utf-8").read()


def _izvor_fajla(rel):
    return io.open(os.path.join(KOREN, rel), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# §14 — NOT NULL / CHECK / BEZ DEFAULT-a
# ═══════════════════════════════════════════════════════════════════════════

def test_migracija_postoji():
    assert os.path.exists(MIGRACIJA)


def test_kolona_je_NOT_NULL():
    assert "ALTER COLUMN izvor SET NOT NULL" in _sql()


def test_check_pokriva_tacno_sest_vrednosti():
    s = _sql()
    blok = s[s.index("predmet_hronologija_izvor_check\n  CHECK"):]
    blok = blok[:blok.index(");")]
    for v in KANONSKE:
        assert f"'{v}'" in blok, f"CHECK ne pokriva {v}"
    nadjene = set(re.findall(r"'([A-Z_]+)'", blok))
    assert nadjene == set(KANONSKE), f"CHECK ima vrednosti van kanona: {nadjene ^ set(KANONSKE)}"


def test_NEMA_DEFAULT_a():
    """SUSTINA UGOVORA. Default bi maskirao propust buduceg pisca i tiho ga
    svrstao u neku klasu; bez njega insert pada sa 23502."""
    s = _sql()
    assert "SET DEFAULT" not in s, "migracija postavlja DEFAULT — ugovor je pokvaren"
    assert "ALTER COLUMN izvor DROP DEFAULT" in s, "nedostaje eksplicitno uklanjanje DEFAULT-a"
    # `ADD COLUMN ... DEFAULT ...` je isto zabranjeno
    dodavanje = s[s.index("ADD COLUMN IF NOT EXISTS izvor"):]
    assert "DEFAULT" not in dodavanje[:120]


def test_redosled_je_backfill_pa_not_null():
    """NOT NULL pre backfill-a bi pao na 55 postojecih redova."""
    s = _sql()
    assert s.index("SET izvor = 'LEGACY_UNKNOWN'") < s.index("SET NOT NULL")
    assert s.index("ADD COLUMN IF NOT EXISTS izvor") < s.index("SET izvor = 'LEGACY_UNKNOWN'")


# ═══════════════════════════════════════════════════════════════════════════
# §16 — backfill je determinističan i BEZ heuristike
# ═══════════════════════════════════════════════════════════════════════════

def test_backfill_je_iskljucivo_LEGACY_UNKNOWN():
    s = _sql()
    upisi = re.findall(r"SET izvor = '([A-Z_]+)'", s)
    assert upisi == ["LEGACY_UNKNOWN"], f"backfill upisuje i druge vrednosti: {upisi}"


def test_backfill_ne_koristi_heuristiku():
    """Zabranjeno klasifikovati po `akter`, `dokument_naziv`, `vaznost`, datumu."""
    s = _sql()
    telo = s[s.index("UPDATE public.predmet_hronologija"):s.index("-- ─── KORAK 3")]
    for zabranjeno in ("akter", "dokument_naziv", "vaznost", "dogadjaj", "datum"):
        assert zabranjeno not in telo, f"backfill se oslanja na `{zabranjeno}`"
    assert "WHERE izvor IS NULL" in telo


def test_legacy_nije_human():
    s = _sql()
    assert "'HUMAN_DIRECT'" not in s[s.index("UPDATE"):s.index("-- ─── KORAK 3")]


# ═══════════════════════════════════════════════════════════════════════════
# §15 — svih 16 pisaca salje canonical `izvor`
# ═══════════════════════════════════════════════════════════════════════════

#: (fajl, ocekivan broj insert-a u hronologiju, ocekivane klase)
PISCI = [
    ("api.py",                        2, {"IZVOR_AI_AUTONOMOUS", "IZVOR_AI_ASSISTED"}),
    ("routers/case_dna.py",           1, {"IZVOR_AI_AUTONOMOUS"}),
    ("services/case_pipeline.py",     1, {"IZVOR_AI_AUTONOMOUS"}),
    ("routers/smart_intake.py",       1, {"IZVOR_AI_AUTONOMOUS"}),
    ("routers/copilot.py",            1, {"IZVOR_AI_ASSISTED"}),
    ("routers/intake.py",             3, {"IZVOR_AI_ASSISTED", "IZVOR_DETERMINISTIC"}),
    ("routers/rocista.py",            1, {"IZVOR_HUMAN_DIRECT"}),
    ("routers/ugovor_zastupanja.py",  1, {"IZVOR_HUMAN_DIRECT"}),
    ("routers/predmeti_close.py",     1, {"IZVOR_HUMAN_DIRECT"}),
    ("routers/rokovi_lanac.py",       1, {"IZVOR_DETERMINISTIC"}),
    ("services/case_evolution.py",    1, {"IZVOR_SYSTEM"}),
    ("routers/learning.py",           1, {"IZVOR_SYSTEM"}),
    ("routers/onboarding.py",         1, {"IZVOR_SYSTEM"}),
]


@pytest.mark.parametrize("fajl,_n,klase", PISCI)
def test_pisac_koristi_kanonske_konstante(fajl, _n, klase):
    s = _izvor_fajla(fajl)
    assert "from shared import rokovi as _IZVOR" in s, f"{fajl} ne uvozi kanonski sifarnik"
    nadjene = set(re.findall(r"_IZVOR\.(IZVOR_[A-Z_]+)", s))
    assert nadjene == klase, f"{fajl}: nadjeno {nadjene}, ocekivano {klase}"


@pytest.mark.parametrize("fajl,n,_k", PISCI)
def test_svaki_pisac_dodeljuje_izvor(fajl, n, _k):
    """Svaki pisac doprinosi TACNO JEDNOM kanonskom dodelom `izvor`.

    Ne broje se `.insert(` pozivi: neki pisci grade red odvojeno od poziva
    (`rows.append({...})` u `api.py`, `records = [...]` u `rokovi_lanac.py`), pa
    bi tekstualno uparivanje merilo OBLIK KODA umesto ugovora. Broj kanonskih
    dodela je direktan dokaz da svaki pisac nosi provenijenciju — i pada cim
    neko doda 17. pisca bez nje."""
    s = _izvor_fajla(fajl)
    dodele = re.findall(r'"izvor":\s*_IZVOR\.(IZVOR_[A-Z_]+)', s)
    assert len(dodele) == n, f"{fajl}: {len(dodele)} dodela `izvor`, ocekivano {n}"


def test_ukupan_broj_pisaca_je_16():
    ukupno = sum(n for _f, n, _k in PISCI)
    assert ukupno == 16, f"popis nosi {ukupno} pisaca, FAZA 6.3 je dokazala 16"


KANONSKE_KONSTANTE = {
    "IZVOR_AI_AUTONOMOUS", "IZVOR_AI_ASSISTED", "IZVOR_HUMAN_DIRECT",
    "IZVOR_DETERMINISTIC", "IZVOR_SYSTEM",
}


def test_nijedan_pisac_ne_izvodi_izvor_iz_aktera():
    """Zabranjeno je nagadjati provenijenciju iz `akter` — to je bila rupa.

    Gleda se SAMO dodela u hronologiju (`"izvor": _IZVOR.X`). `case_evolution.py`
    ima nepovezan kljuc `"izvor"` unutar `dokaz` JSON-a za `case_actions` — druga
    tabela, drugi pojam, ne ulazi u ovu proveru."""
    for fajl, _n, _k in PISCI:
        s = _izvor_fajla(fajl)
        for m in re.finditer(r'"izvor":\s*_IZVOR\.([A-Za-z_]+)', s):
            assert m.group(1) in KANONSKE_KONSTANTE, \
                f"{fajl}: nekanonska konstanta {m.group(1)}"
        for linija in s.split("\n"):
            if '"izvor":' in linija and "_IZVOR." in linija:
                assert "akter" not in linija, f"{fajl}: `izvor` izveden iz `akter`"


# ═══════════════════════════════════════════════════════════════════════════
# §18 — matrica bezbednosti akcija
# ═══════════════════════════════════════════════════════════════════════════

from shared.rokovi import sme_pokrenuti_obavezu  # noqa: E402


def _r(izvor, vaznost="kritičan", rid="r-1"):
    return {"id": rid, "izvor": izvor, "vaznost": vaznost,
            "akter": "DOO Alfa Trejd", "predmet_id": "p-1"}


@pytest.mark.parametrize("oznaka,izvor,vaznost,potvrde,ocekivano", [
    ("A  AI_AUTONOMOUS + kritičan + nepotvrdjen", "AI_AUTONOMOUS", "kritičan", set(),      False),
    ("B  AI_AUTONOMOUS + važan   + nepotvrdjen", "AI_AUTONOMOUS", "važan",    set(),      False),
    ("C  AI_ASSISTED   + kritičan + nepotvrdjen", "AI_ASSISTED",   "kritičan", set(),      True),
    ("D  HUMAN_DIRECT  + kritičan + nepotvrdjen", "HUMAN_DIRECT",  "kritičan", set(),      True),
    ("E  LEGACY_UNKNOWN + nepotvrdjen",           "LEGACY_UNKNOWN","kritičan", set(),      False),
    ("G  AI_AUTONOMOUS + POTVRDJEN",              "AI_AUTONOMOUS", "kritičan", {"r-1"},    True),
])
def test_matrica_bezbednosti(oznaka, izvor, vaznost, potvrde, ocekivano):
    assert sme_pokrenuti_obavezu(_r(izvor, vaznost), potvrde) is ocekivano, oznaka


def test_C_ai_assisted_nije_implicitno_potvrdjen():
    """§11: `AI_ASSISTED` prolazi PROVENIJENCIJSKU kapiju, ali time se NE tvrdi
    da je potvrdjen. Provenijencija i ovlascenje su razlicite ose — potvrda se
    i dalje trazi tamo gde je postojeci model zahteva."""
    from shared.rokovi import IZVOR_TRAZI_POTVRDU
    assert "AI_ASSISTED" not in IZVOR_TRAZI_POTVRDU
    # ali NIJE u skupu potvrdjenih -- kapija ne tvrdi nista o odobrenju
    assert sme_pokrenuti_obavezu(_r("AI_ASSISTED"), set()) is True


def test_vaznost_ne_utice_na_kapiju():
    """§19: `vaznost` je prioritet, ne ovlascenje. Ista `izvor` klasa daje isti
    ishod za sve tri vrednosti."""
    for v in ("kritičan", "važan", "informativan"):
        assert sme_pokrenuti_obavezu(_r("AI_AUTONOMOUS", v), set()) is False
        assert sme_pokrenuti_obavezu(_r("HUMAN_DIRECT", v), set()) is True


# ═══════════════════════════════════════════════════════════════════════════
# §9 — kapija vise ne cita `akter`
# ═══════════════════════════════════════════════════════════════════════════

def test_gejtovani_upiti_dovlace_izvor_a_ne_akter():
    for fajl, n in (("routers/email_notif.py", 3), ("routers/sms.py", 2),
                    ("routers/notifications.py", 2)):
        s = _izvor_fajla(fajl)
        gejtovani = [d for d in s.split('table("predmet_hronologija")')[1:]
                     if ".select(" in d[:300] and "izvor" in d[:300]]
        assert len(gejtovani) == n, f"{fajl}: {len(gejtovani)} upita sa `izvor`, ocekivano {n}"
        for d in gejtovani:
            sel = d[d.index(".select(") + 8:]
            sel = sel[:sel.index(")")]
            assert "akter" not in sel, f"{fajl}: gejtovan upit i dalje dovlaci `akter` kao poreklo"


def test_kapija_ne_pominje_akter_u_odluci():
    s = _izvor_fajla("shared/rokovi.py")
    telo = s[s.index("def sme_pokrenuti_obavezu("):s.index("def filtriraj_izvrsive(")]
    # ukloni docstring (istorijski pominje `akter`) i komentare
    if '"""' in telo:
        prvi = telo.index('"""')
        drugi = telo.index('"""', prvi + 3) + 3
        telo = telo[:prvi] + telo[drugi:]
    kod = "\n".join(l for l in telo.split("\n") if not l.strip().startswith("#"))
    assert "akter" not in kod, f"kapija i dalje cita `akter` kao poreklo:\n{kod}"
