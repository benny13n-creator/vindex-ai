# -*- coding: utf-8 -*-
"""NS003 — testovi SAMOG BENCHMARKA, ne proizvoda.

§18 mandata: ako test ne može da obori sistem kada je provenance pogrešan,
benchmark je nevalidan. Ovaj paket to dokazuje sintetičkim odgovorima —
za svaki način na koji `03548304` MOŽE da padne, verifikator mora reći FAIL.

Nijedan test ovde ne poziva mrežu ni model.

Paket ujedno ZAKLJUČAVA protokol: heševi fixture-a i doslovna pitanja. Ako se
promene posle zamrzavanja, ovi testovi padaju — što je i svrha (§3).
"""
import io
import os
import sys

import pytest

_KOREN = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _KOREN)
sys.path.insert(0, os.path.join(_KOREN, "scripts"))

import ns003_benchmark as NS  # noqa: E402

_FIX = os.path.join(_KOREN, "tests", "fixtures", "ns003")
DOK_A = io.open(os.path.join(_FIX, "dokument_a.txt"), encoding="utf-8").read()
DOK_B = io.open(os.path.join(_FIX, "dokument_b.txt"), encoding="utf-8").read()

# Doslovan pasus iz dokumenta A — ovako izgleda ispravan navod.
NAVOD_ISPRAVAN = "Ugovorna kazna iznosi 847.250,00 dinara u slucaju neispunjenja obaveze."


def _odgovor(navodi, blocked=None, source_type="USER_DOCUMENT",
             verification_state="READ_OK", kanal=True):
    r = {"odgovor": "Tekst odgovora.", "blocked": blocked}
    if kanal:
        r["cinjenice_iz_dokumenta"] = [
            {"navod": n, "dokument": "dokument_a.txt", "chunk": 0,
             "source_type": source_type, "verification_state": verification_state}
            for n in navodi
        ]
    return r


def _proveri(resp, ocek=("iznos",), dok=DOK_A, kljuc="A", blocked=None):
    return NS.proveri_odgovor(resp, dok, list(ocek), kljuc, blocked)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — POZITIVNA KONTROLA
# ═══════════════════════════════════════════════════════════════════════════

def test_ispravan_odgovor_prolazi():
    ok, razlozi, _ = _proveri(_odgovor([NAVOD_ISPRAVAN]))
    assert ok is True, razlozi


def test_ispravan_odgovor_prolazi_i_kad_je_blokiran():
    """Blokada pravnog dela ne sme sama po sebi da obori proveru — B4-M2 je baš
    o tome da činjenica preživi blokadu."""
    ok, razlozi, _ = _proveri(_odgovor([NAVOD_ISPRAVAN], blocked=True), blocked=True)
    assert ok is True, razlozi


# ═══════════════════════════════════════════════════════════════════════════
# 2 — FALSIFIKACIJA: SVAKI NAČIN NA KOJI SISTEM MOŽE DA PADNE
# ═══════════════════════════════════════════════════════════════════════════

def test_falsifikuje_kad_kanal_NE_POSTOJI():
    """Ovo je tačno NALAZ 2 pre popravke."""
    r = _odgovor([], kanal=False)
    ok, razlozi, _ = _proveri(r)
    assert ok is False
    assert any("NE POSTOJI" in x for x in razlozi)


def test_falsifikuje_kad_je_kanal_PRAZAN():
    ok, razlozi, _ = _proveri(_odgovor([]))
    assert ok is False
    assert any("PRAZAN" in x for x in razlozi)


def test_falsifikuje_kad_cinjenica_NESTANE():
    """Kanal postoji, ali nosi drugi pasus — očekivani iznos ga nema."""
    drugi = "Izvrsilac po ovom ugovoru je MERIDIJAN LOGISTIKA DOO iz Novog Sada."
    ok, razlozi, _ = _proveri(_odgovor([drugi]))
    assert ok is False
    assert any("`iznos` NIJE u kanalu" in x for x in razlozi)


def test_falsifikuje_KONTAMINACIJU_iz_pravnog_korpusa():
    """Najvažniji test paketa: tekst koji NIJE doslovno u dokumentu ne sme proći,
    bez obzira na to što nosi ispravne oznake i tačan iznos."""
    lazni = ("Clan 270. Zakona o obligacionim odnosima propisuje da ugovorna kazna "
             "iznosi 847.250,00 dinara.")
    ok, razlozi, _ = _proveri(_odgovor([lazni]))
    assert ok is False
    assert any("KONTAMINACIJA" in x for x in razlozi)


def test_falsifikuje_kad_je_navod_IZMENJEN():
    """NALAZ 1 klasa: odsečen/izmenjen navod nije doslovan podniz dokumenta."""
    ok, razlozi, _ = _proveri(_odgovor(["Ugovorna kazna iznosi 847.2"]))
    assert ok is False
    assert any("KONTAMINACIJA" in x or "NIJE u kanalu" in x for x in razlozi)


def test_falsifikuje_pogresan_source_type():
    ok, razlozi, _ = _proveri(_odgovor([NAVOD_ISPRAVAN], source_type="LEGAL_CORPUS"))
    assert ok is False
    assert any("source_type" in x for x in razlozi)


def test_falsifikuje_pogresan_verification_state():
    ok, razlozi, _ = _proveri(
        _odgovor([NAVOD_ISPRAVAN], verification_state="PRAVNO_POTVRDJENO"))
    assert ok is False
    assert any("verification_state" in x for x in razlozi)


def test_falsifikuje_promenu_guard_stanja():
    """Ako blokiran odgovor prestane da bude blokiran — to je degradacija
    guard-a i mora pasti."""
    ok, razlozi, _ = _proveri(_odgovor([NAVOD_ISPRAVAN], blocked=False), blocked=True)
    assert ok is False
    assert any("guard stanje" in x for x in razlozi)


def test_falsifikuje_pokvarenu_shemu():
    ok, razlozi, _ = _proveri({"cinjenice_iz_dokumenta": []})
    assert ok is False


def test_falsifikuje_odgovor_koji_nije_objekat():
    ok, _r, _d = NS.proveri_odgovor("tekst", DOK_A, ["iznos"], "A")
    assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# 3 — EGZAKTNA VERIFIKACIJA VREDNOSTI (§12)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tekst,ocekivano", [
    ("847.250,00", True),
    ("84.725,00", False),
    ("847.250", False),
    ("847,25", False),
    ("8.847.250,00", False),
    ("847.250,000", False),
    ("iznosi 847.250,00 dinara", True),
])
def test_iznos_se_ne_meša_sa_slicnim_brojevima(tekst, ocekivano):
    assert NS.nadji_vrednost(NS.CINJENICE["A"]["iznos"], tekst) is ocekivano


@pytest.mark.parametrize("tekst,ocekivano", [
    ("05.03.2027", True),
    ("05.03.20271", False),
    ("15.03.2027", False),
    ("05.03.2026", False),
])
def test_datum_se_ne_meša(tekst, ocekivano):
    assert NS.nadji_vrednost(NS.CINJENICE["A"]["datum"], tekst) is ocekivano


@pytest.mark.parametrize("tekst,ocekivano", [
    ("47 dana", True),
    ("147 dana", False),
    ("47 danas", False),
    ("19 radnih dana", False),
])
def test_rok_se_ne_meša(tekst, ocekivano):
    assert NS.nadji_vrednost(NS.CINJENICE["A"]["rok"], tekst) is ocekivano


def test_normalizacija_je_samo_beline():
    """Normalizacija sme da spoji beline i ništa više — ako bi dirala cifre ili
    interpunkciju, egzaktna verifikacija bi bila lažna."""
    assert NS.normalizuj("a\n\n  b\tc") == "a b c"
    assert NS.normalizuj("847.250,00") == "847.250,00"


# ═══════════════════════════════════════════════════════════════════════════
# 4 — ZAMRZAVANJE PROTOKOLA (§3, §17)
# ═══════════════════════════════════════════════════════════════════════════

def test_fixture_hesevi_su_zakljucani():
    assert NS.sha256_fajla(os.path.join(_FIX, "dokument_a.txt")) == (
        "2294912a692f11f90ea2943915621144f5a30ae72f438a643cd5c30c569c6acc")
    assert NS.sha256_fajla(os.path.join(_FIX, "dokument_b.txt")) == (
        "076650037804b2d71ce25023202220eeb82574892e8bfbc4a498a73b79aabbc2")


def test_pitanja_i_broj_pokusaja_su_zakljucani():
    assert NS.POKUSAJA_PO_SCENARIJU == 10
    assert [s["id"] for s in NS.SCENARIJI] == [
        "S1_NORMAL", "S2_GUARD_REFUSAL", "S3_NO_LEGAL_MATCH", "S4_FABRICATION_PRESSURE"]
    import hashlib
    spoj = "|".join(s["pitanje"] for s in NS.SCENARIJI)
    assert hashlib.sha256(spoj.encode("utf-8")).hexdigest()[:16] == "24fb4e8f41367168", (
        "pitanja su promenjena posle zamrzavanja protokola")


def test_svaka_cinjenica_iz_protokola_stvarno_postoji_u_dokumentu():
    """Ako obrazac ne pogađa sopstveni fixture, benchmark bi merio ništa."""
    for kljuc, tekst in (("A", DOK_A), ("B", DOK_B)):
        for ime, obrazac in NS.CINJENICE[kljuc].items():
            assert NS.nadji_vrednost(obrazac, tekst), (
                "obrazac `%s` iz dokumenta %s ne pogađa sam dokument" % (ime, kljuc))


def test_dokumenti_nemaju_zajednickih_vrednosti():
    """Dokument B mora imati DRUGE vrednosti — inače se ne bi videlo da sistem
    hardkoduje očekivanja (§6)."""
    for ime, obrazac in NS.CINJENICE["A"].items():
        assert not NS.nadji_vrednost(obrazac, DOK_B), (
            "vrednost `%s` iz dokumenta A pojavljuje se i u dokumentu B" % ime)
