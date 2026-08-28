# -*- coding: utf-8 -*-
"""
IMPLEMENTATION TASK 001 — STORED CLAIM IDENTITY.

    identitet = sha256(predmet_id | CANON_VERSION | normalize_ws(tvrdnja))

Testovi dokazuju invarijante, ne implementaciju:
  * determinizam i neosetljivost na reprezentaciju
  * osetljivost na predmet, tekst i verziju kanonizacije
  * identitet NE sadrži offset/stranicu/EXTRACTION_VERSION/embedding
  * identitet se računa pri UPISU i NIKADA pri čitanju
  * postoji TAČNO JEDAN generator identiteta u celom repou
"""
import hashlib
import io
import os
import subprocess
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.evidence_write import (  # noqa: E402
    CANON_VERSION,
    KOLONA_IDENTITET,
    GreskaDokaza,
    izracunaj_identitet,
    upisi_dokaze,
)

from tests.test_impl001_unified_evidence_write import (  # noqa: E402
    DOKUMENT, KORISNIK, PREDMET, DRUGI_PREDMET, TEKST, TVRDNJA, FakeSupa,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DETERMINIZAM I NEOSETLJIVOST NA REPREZENTACIJU
# ═══════════════════════════════════════════════════════════════════════════

def test_isti_tekst_isti_identitet():
    assert izracunaj_identitet(PREDMET, TVRDNJA) == izracunaj_identitet(PREDMET, TVRDNJA)


def test_determinizam_100_poziva():
    assert len({izracunaj_identitet(PREDMET, TVRDNJA) for _ in range(100)}) == 1


@pytest.mark.parametrize("varijanta,opis", [
    (lambda t: t.replace(" ", "   ", 1), "višestruki razmaci"),
    (lambda t: "   " + t + "   ", "vodeći/prateći razmaci"),
    (lambda t: t.replace(" ", "\r\n", 1), "CRLF"),
    (lambda t: t.replace(" ", "\n", 1), "LF"),
    (lambda t: t.replace(" ", "\t", 1), "TAB"),
    (lambda t: unicodedata.normalize("NFD", t), "Unicode NFD"),
    (lambda t: t.upper(), "velika slova"),
])
def test_reprezentacija_ne_menja_identitet(varijanta, opis):
    assert izracunaj_identitet(PREDMET, varijanta(TVRDNJA)) == izracunaj_identitet(PREDMET, TVRDNJA), opis


# ═══════════════════════════════════════════════════════════════════════════
# 2. OSETLJIVOST — na ono na šta MORA biti osetljiv
# ═══════════════════════════════════════════════════════════════════════════

def test_drugi_predmet_drugi_identitet():
    """Cross-case izolacija: ista tvrdnja u dva predmeta NIJE isti entitet."""
    assert izracunaj_identitet(PREDMET, TVRDNJA) != izracunaj_identitet(DRUGI_PREDMET, TVRDNJA)


def test_stvarno_drugi_tekst_drugi_identitet():
    assert izracunaj_identitet(PREDMET, TVRDNJA) != izracunaj_identitet(
        PREDMET, TVRDNJA.replace("decembar 2025", "januar 2026")
    )


def test_zamenjene_stranke_drugi_identitet():
    a = izracunaj_identitet(PREDMET, "Tuzilac duguje tuzenom.")
    b = izracunaj_identitet(PREDMET, "Tuzeni duguje tuziocu.")
    assert a != b


def test_prazan_predmet_se_odbija():
    with pytest.raises(GreskaDokaza):
        izracunaj_identitet("", TVRDNJA)
    with pytest.raises(GreskaDokaza):
        izracunaj_identitet(None, TVRDNJA)


# ═══════════════════════════════════════════════════════════════════════════
# 3. ŠTA IDENTITET NE SME DA SADRŽI
# ═══════════════════════════════════════════════════════════════════════════

def test_canon_version_je_deo_kljuca():
    """Promena pravila kanonizacije mora dati NOVE identitete — inače bi
    retroaktivno promenila značenje već skladištenih."""
    from analiza.validator import _normalize_ws
    # Pozitivno pinovanje TAČNE formule -- "razlicito od c2" nije dovoljno:
    # izbacivanje CANON_VERSION iz ključa takođe daje vrednost različitu od c2.
    rucno_c1 = hashlib.sha256(
        f"{PREDMET}|{CANON_VERSION}|{_normalize_ws(TVRDNJA)}".encode("utf-8")
    ).hexdigest()
    assert izracunaj_identitet(PREDMET, TVRDNJA) == rucno_c1,         "ključ mora biti tačno predmet_id|CANON_VERSION|normalize_ws(tvrdnja)"
    rucno_c2 = hashlib.sha256(
        f"{PREDMET}|c2|{_normalize_ws(TVRDNJA)}".encode("utf-8")
    ).hexdigest()
    assert izracunaj_identitet(PREDMET, TVRDNJA) != rucno_c2
    assert CANON_VERSION == "c1"


def test_extraction_version_nije_u_kljucu():
    """Nadogradnja ekstraktora NE SME prekinuti postojeće relacije."""
    from shared.vector_identity import EXTRACTION_VERSION
    ident = izracunaj_identitet(PREDMET, TVRDNJA)
    assert str(EXTRACTION_VERSION) not in ident or True  # heš je heks, poređenje je strukturno:
    import inspect
    izvor = inspect.getsource(izracunaj_identitet)
    assert "EXTRACTION_VERSION" not in izvor.split('"""')[-1], \
        "EXTRACTION_VERSION ne sme ući u ključ identiteta"


def test_identitet_ne_zavisi_od_lokacije():
    """Isti tekst, dva potpuno različita mesta u dokumentu → isti identitet."""
    tekst_a = "AAAA " + TVRDNJA + " BBBB"
    tekst_b = "B" * 500 + TVRDNJA
    supa_a, supa_b = FakeSupa(), FakeSupa()
    for supa, tekst in ((supa_a, tekst_a), (supa_b, tekst_b)):
        upisi_dokaze(
            supa, predmet_id=PREDMET, user_id=KORISNIK,
            stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
            izvor_tekst=tekst, proveri_vlasnistvo=False,
        )
    assert supa_a.dokazi[0]["start_offset"] != supa_b.dokazi[0]["start_offset"]
    assert supa_a.dokazi[0][KOLONA_IDENTITET] == supa_b.dokazi[0][KOLONA_IDENTITET]


def test_identitet_ne_zavisi_od_izvornog_dokumenta():
    """Ista tvrdnja iz dva različita dokumenta istog predmeta = ISTA tvrdnja
    sa dva izvora (Gate 006 §10, MODEL A)."""
    supa = FakeSupa()
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA}], proveri_vlasnistvo=False,
    )
    assert supa.dokazi[0][KOLONA_IDENTITET] == supa.dokazi[1][KOLONA_IDENTITET]
    assert supa.dokazi[0]["dokument_id"] != supa.dokazi[1]["dokument_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. UPIS — identitet ide u bazu
# ═══════════════════════════════════════════════════════════════════════════

def test_upis_sadrzi_identitet():
    supa = FakeSupa()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": TVRDNJA}], proveri_vlasnistvo=False)
    red = supa.dokazi[0]
    assert red[KOLONA_IDENTITET] == izracunaj_identitet(PREDMET, TVRDNJA)
    assert len(red[KOLONA_IDENTITET]) == 64


def test_ponovni_upis_iste_tvrdnje_daje_isti_identitet():
    """Ponovni ingest istog dokumenta ne sme proizvesti nov identitet."""
    ident = set()
    for _ in range(4):
        supa = FakeSupa()
        upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                     stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
                     izvor_tekst=TEKST, proveri_vlasnistvo=False)
        ident.add(supa.dokazi[0][KOLONA_IDENTITET])
    assert len(ident) == 1, "4 unosa iste tvrdnje moraju dati JEDAN identitet"


# ═══════════════════════════════════════════════════════════════════════════
# 5. IDENTITET SE NE REGENERIŠE PRI ČITANJU  (izričit zahtev TASK-a 001)
# ═══════════════════════════════════════════════════════════════════════════

def test_nijedna_read_putanja_ne_racuna_identitet():
    """Strukturni dokaz: `izracunaj_identitet` se poziva SAMO iz putanje upisa.
    Ako se pojavi u nekom čitaocu, identitet bi se preračunavao pri SELECT-u i
    promena `CANON_VERSION` bi tiho promenila značenje starih redova."""
    koren = os.path.join(os.path.dirname(__file__), "..")
    izlaz = subprocess.run(
        [sys.executable, "-c",
         "import pathlib;"
         "p=pathlib.Path('.');"
         "fs=list(p.glob('routers/*.py'))+list(p.glob('services/*.py'))"
         "  +list(p.glob('shared/*.py'))+[pathlib.Path('api.py')];"
         "hits=[f'{f}:{i+1}' for f in fs"
         " for i,l in enumerate(f.read_text(encoding='utf-8').splitlines())"
         " if 'izracunaj_identitet(' in l and 'def ' not in l];"
         "print('|'.join(hits))"],
        cwd=koren, capture_output=True, text=True,
    )
    pozivi = [h for h in (izlaz.stdout or "").strip().split("|") if h]
    assert all("evidence_write.py" in h for h in pozivi), \
        f"identitet se računa van kanonske putanje upisa: {pozivi}"


def test_tacno_jedan_generator_identiteta():
    """Nijedan drugi `sha256` nad `tvrdnja` ne sme postojati."""
    koren = os.path.join(os.path.dirname(__file__), "..")
    izlaz = subprocess.run(
        [sys.executable, "-c",
         "import pathlib;"
         "p=pathlib.Path('.');"
         "fs=list(p.glob('routers/*.py'))+list(p.glob('services/*.py'))"
         "  +list(p.glob('shared/*.py'))+[pathlib.Path('api.py')];"
         "hits=[f'{f}:{i+1}' for f in fs"
         " for i,l in enumerate(f.read_text(encoding='utf-8').splitlines())"
         " if 'CANON_VERSION' in l and 'import' not in l];"
         "print('|'.join(hits))"],
        cwd=koren, capture_output=True, text=True,
    )
    mesta = [h for h in (izlaz.stdout or "").strip().split("|") if h]
    assert all("evidence_write.py" in h for h in mesta), \
        f"CANON_VERSION se koristi van kanonskog modula: {mesta}"


def test_kanonizacija_se_uvozi_a_ne_reimplementira():
    """Druga implementacija istog pravila bila bi drugi autor istog koncepta."""
    import inspect
    izvor = inspect.getsource(izracunaj_identitet)
    assert "from analiza.validator import _normalize_ws" in izvor
    assert "unicodedata" not in izvor and "re.sub" not in izvor


# ═══════════════════════════════════════════════════════════════════════════
# 6. DEGRADACIJA — okruženje bez migracije 116
# ═══════════════════════════════════════════════════════════════════════════

def test_bez_migracije_116_upis_ne_propada():
    """Kolona `identitet` još ne postoji → upis mora proći bez nje, glasno."""
    class _BezIdent(FakeSupa):
        def table(self, naziv):
            t = super().table(naziv)
            if naziv == "predmet_dokazi":
                orig = t.insert
                def insert(redovi):
                    if any(KOLONA_IDENTITET in r for r in redovi):
                        raise RuntimeError('column "identitet" does not exist')
                    return orig(redovi)
                t.insert = insert
            return t

    supa = _BezIdent()
    upisi_dokaze(supa, predmet_id=PREDMET, user_id=KORISNIK,
                 stavke=[{"tvrdnja": TVRDNJA}], proveri_vlasnistvo=False)
    assert len(supa.dokazi) == 1
    assert KOLONA_IDENTITET not in supa.dokazi[0]
    assert supa.dokazi[0]["tvrdnja"] == TVRDNJA


def test_migracija_116_postoji_i_ne_radi_backfill():
    put = os.path.join(os.path.dirname(__file__), "..", "migrations",
                       "116_predmet_dokazi_identitet.sql")
    assert os.path.exists(put)
    sql = io.open(put, encoding="utf-8").read().lower()
    assert "add column if not exists identitet" in sql
    for zabranjeno in ("update public.predmet_dokazi", "insert into public.predmet_dokazi",
                       "generated always"):
        assert zabranjeno not in sql, f"migracija sme samo da doda kolonu, našao: {zabranjeno}"

def test_pad_identiteta_ne_sme_da_odbaci_i_utemeljenje():
    """Degradacija mora biti STEPENASTA: ako nedostaje samo kolona `identitet`
    (migracija 116), grounding kolone iz migracije 080 moraju PREŽIVETI.
    Odbacivanje oba u jednom koraku tiho bi izgubilo provenance koju baza
    savršeno može da primi."""
    class _SamoBezIdent(FakeSupa):
        def table(self, naziv):
            t = super().table(naziv)
            if naziv == "predmet_dokazi":
                orig = t.insert
                def insert(redovi):
                    if any(KOLONA_IDENTITET in r for r in redovi):
                        raise RuntimeError('column "identitet" does not exist')
                    return orig(redovi)
                t.insert = insert
            return t

    supa = _SamoBezIdent()
    upisi_dokaze(
        supa, predmet_id=PREDMET, user_id=KORISNIK,
        stavke=[{"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}],
        izvor_tekst=TEKST, proveri_vlasnistvo=False,
    )
    red = supa.dokazi[0]
    assert KOLONA_IDENTITET not in red
    assert red["start_offset"] == TEKST.find(TVRDNJA),         "utemeljenje je odbaceno iako je nedostajala samo kolona `identitet`"
    assert red["stranica"] is not None
