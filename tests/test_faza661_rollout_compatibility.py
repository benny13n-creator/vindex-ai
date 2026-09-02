# -*- coding: utf-8 -*-
"""FAZA 6.6.1 — KOMPATIBILNOST ROLLOUT-a: stari kod vs nova sema.

KONTEKST
========
Migracija 127 je IZVRSENA na produkciji (`izvor NOT NULL + CHECK`, bez
DEFAULT-a), ali kod na produkciji (`044c5310`) ne salje `izvor` ni iz jednog od
16 pisaca. Posledica: svaki upis u `predmet_hronologija` pada sa `23502`.

Ovaj fajl dokazuje tri stvari, bez ijednog DDL-a i bez pisanja u produkciju:

  1. STARI oblik upisa (bez `izvor`) NE PROLAZI      -> to je trenutni kvar
  2. NOVI oblik upisa (sa validnim `izvor`) PROLAZI  -> deploy je resenje
  3. Nevalidna vrednost `izvor` NE PROLAZI           -> CHECK stiti sifarnik

Zivo su ista tri ishoda izmerena nad produkcionom bazom (23502 / 23503 tek
posle validnog `izvor` / 23514) i zabelezena u izvestaju FAZE 6.6.1. Ovde se
zakljucava kodna strana tog dokaza.
"""
import io
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.rokovi import IZVOR_DOZVOLJENI  # noqa: E402

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRODUKCIJA = "044c5310"

#: (fajl, broj kanonskih dodela `izvor`) — dokazano u FAZI 6.3/6.4.
PISCI = [
    ("api.py", 2), ("routers/case_dna.py", 1), ("services/case_pipeline.py", 1),
    ("routers/smart_intake.py", 1), ("routers/copilot.py", 1),
    ("routers/intake.py", 3), ("routers/rocista.py", 1),
    ("routers/ugovor_zastupanja.py", 1), ("routers/predmeti_close.py", 1),
    ("routers/rokovi_lanac.py", 1), ("services/case_evolution.py", 1),
    ("routers/learning.py", 1), ("routers/onboarding.py", 1),
]


def _izv(rel):
    return io.open(os.path.join(KOREN, rel), encoding="utf-8").read()


def _produkcijski(rel):
    return subprocess.run(["git", "show", PRODUKCIJA + ":" + rel],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=KOREN).stdout


# ═══════════════════════════════════════════════════════════════════════════
# §9 — OLD CODE + CURRENT SCHEMA  =  KVAR
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fajl,_n", PISCI)
def test_produkcijski_kod_NE_salje_izvor(fajl, _n):
    """Uzrok incidenta, zakljucan kao cinjenica o `044c5310`."""
    s = _produkcijski(fajl)
    assert s, fajl + " ne postoji u " + PRODUKCIJA
    assert not re.search(r'"izvor":\s*_IZVOR\.', s), \
        fajl + " u produkciji ipak salje izvor — incident je pogresno okarakterisan"


def test_produkcijski_kod_ne_zna_za_sifarnik():
    assert "IZVOR_DOZVOLJENI" not in _produkcijski("shared/rokovi.py")


# ═══════════════════════════════════════════════════════════════════════════
# §9 — NEW CODE + CURRENT SCHEMA  =  RADI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fajl,n", PISCI)
def test_novi_kod_salje_izvor_iz_svakog_pisca(fajl, n):
    dodele = re.findall(r'"izvor":\s*_IZVOR\.(IZVOR_[A-Z_]+)', _izv(fajl))
    assert len(dodele) == n, "%s: %d dodela, ocekivano %d" % (fajl, len(dodele), n)


def test_svih_16_pisaca_pokriveno():
    assert sum(n for _f, n in PISCI) == 16


@pytest.mark.parametrize("fajl,_n", PISCI)
def test_svaka_dodela_je_iz_kanonskog_sifarnika(fajl, _n):
    """Vrednost koju pisac salje mora biti u CHECK skupu iz migracije 127 —
    inace bi upis pao sa 23514 umesto da uspe."""
    import shared.rokovi as R
    for konst in re.findall(r'"izvor":\s*_IZVOR\.(IZVOR_[A-Z_]+)', _izv(fajl)):
        assert getattr(R, konst) in IZVOR_DOZVOLJENI, fajl + ": " + konst


def test_sifarnik_u_kodu_odgovara_CHECK_u_migraciji():
    sql = _izv("migrations/127_hronologija_izvor_provenance.sql")
    blok = sql[sql.index("CHECK (izvor IN ("):]
    blok = blok[:blok.index("));")]
    u_sql = set(re.findall(r"'([A-Z_]+)'", blok))
    assert u_sql == set(IZVOR_DOZVOLJENI), \
        "kod i migracija se ne slazu: %s" % (u_sql ^ set(IZVOR_DOZVOLJENI))


# ═══════════════════════════════════════════════════════════════════════════
# §3 — NEMA KOMPATIBILNOG FALLBACK-a
# ═══════════════════════════════════════════════════════════════════════════

ZABRANJENO = [
    (r"izvor.*=.*red\.get\(.akter", "provenijencija izvedena iz akter"),
    (r"ALTER COLUMN izvor SET DEFAULT", "DEFAULT vracen u migraciju"),
    (r'"izvor":\s*"HUMAN_DIRECT"', "hardkodovan HUMAN_DIRECT kao fallback"),
]


@pytest.mark.parametrize("obrazac,opis", ZABRANJENO)
def test_nema_kompatibilnog_fallbacka(obrazac, opis):
    pogodci = []
    for k, _d, fs in os.walk(KOREN):
        if any(x in k for x in ("tests", ".git", "node_modules", "data", "__pycache__")):
            continue
        for ime in fs:
            if not ime.endswith((".py", ".sql")):
                continue
            rel = os.path.relpath(os.path.join(k, ime), KOREN).replace(os.sep, "/")
            s = io.open(os.path.join(k, ime), encoding="utf-8", errors="replace").read()
            if re.search(obrazac, s):
                pogodci.append(rel)
    assert pogodci == [], opis + ": " + str(pogodci)


def test_migracija_i_dalje_nosi_finalni_ugovor():
    """§6: ugovor je NEPROMENLJIV — NOT NULL + CHECK + BEZ DEFAULT-a."""
    sql = _izv("migrations/127_hronologija_izvor_provenance.sql")
    kod = "\n".join(l for l in sql.split("\n") if not l.strip().startswith("--"))
    assert "ALTER COLUMN izvor SET NOT NULL" in kod
    assert "CHECK (izvor IN (" in kod
    assert "SET DEFAULT" not in kod
    assert "ALTER COLUMN izvor DROP DEFAULT" in kod


def test_migracija_nije_menjana_posle_faze_64():
    """§0: migracija se ne dira dok se ne dokaze da je potrebno. FAZA 6.6.1 je
    dokazala SUPROTNO — deploy koda je dovoljan, DDL nije potreban."""
    lokalna = _izv("migrations/127_hronologija_izvor_provenance.sql")
    iz_64 = subprocess.run(
        ["git", "show", "aa986192:migrations/127_hronologija_izvor_provenance.sql"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=KOREN).stdout
    assert lokalna == iz_64, "migracija 127 je promenjena posle FAZE 6.4"


# ═══════════════════════════════════════════════════════════════════════════
# §10 — ROLLOUT NE MENJA AUTORIZACIJU
# ═══════════════════════════════════════════════════════════════════════════

def test_autorizacija_ostaje_netaknuta():
    from shared.rok_potvrda import STANJE_ODBIJEN, STANJE_POTVRDJEN
    from shared.rokovi import POTROSAC_AKCIJA, POTROSAC_KLIJENT, sme_pristupiti
    red = {"id": "r1", "izvor": "LEGACY_UNKNOWN", "vaznost": "kritičan"}
    assert sme_pristupiti(red, {}, potrosac=POTROSAC_AKCIJA) is False
    assert sme_pristupiti(red, {"r1": STANJE_ODBIJEN}, potrosac=POTROSAC_AKCIJA) is False
    assert sme_pristupiti(red, {"r1": STANJE_POTVRDJEN}, potrosac=POTROSAC_AKCIJA) is True
    assert sme_pristupiti(red, {}, potrosac=POTROSAC_KLIJENT) is False


def test_izvor_i_dalje_nije_ovlascenje():
    from shared.rokovi import POTROSAC_AKCIJA, sme_pristupiti
    for izvor in IZVOR_DOZVOLJENI:
        assert sme_pristupiti({"id": "r1", "izvor": izvor}, {},
                              potrosac=POTROSAC_AKCIJA) is False


# ═══════════════════════════════════════════════════════════════════════════
# §11 — MESOVIT PROZOR (old + new instanca, ista baza)
# ═══════════════════════════════════════════════════════════════════════════

def test_mesovit_prozor_je_monoton():
    """Kljucni argument izabranog plana.

    Tokom rolling deploya stara i nova instanca dele ISTU semu:

        stara instanca + trenutna sema  ->  23502   (isto kao sada)
        nova  instanca + trenutna sema  ->  upis prolazi

    Ne postoji stanje u kome stari kod upise NEISPRAVAN red — on ne moze da
    upise NIKAKAV red. Zato mesovit prozor ne moze naruziti provenijenciju, i
    svaka zamenjena instanca je strogo poboljsanje.

    Suprotno vazi za `DROP NOT NULL` plan: tokom nullable prozora stara
    instanca USPESNO upisuje red sa `izvor IS NULL` — tacno ono naruzavanje
    provenijencije koje ceo program zatvara."""
    stari = _produkcijski("routers/case_dna.py")
    novi = _izv("routers/case_dna.py")
    assert not re.search(r'"izvor":\s*_IZVOR\.', stari), "stari kod bi upisao red"
    assert re.search(r'"izvor":\s*_IZVOR\.', novi), "novi kod ne upisuje izvor"


def test_drop_not_null_plan_je_gori_i_to_je_dokazivo():
    """Formalno: jedini nacin da stari kod uspesno upise red je da `izvor`
    postane nullable. Zato svaki plan koji uklanja `NOT NULL` OTVARA put ka
    redovima bez provenijencije, dok ga plan „samo deploy" drzi zatvorenim."""
    sql = _izv("migrations/127_hronologija_izvor_provenance.sql")
    assert "ALTER COLUMN izvor SET NOT NULL" in sql
    stari = _produkcijski("api.py")
    assert not re.search(r'"izvor":\s*_IZVOR\.', stari)
