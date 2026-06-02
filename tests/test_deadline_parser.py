# -*- coding: utf-8 -*-
"""Tests for P3.1 — uploaded_doc.deadline_parser.ekstrahuj_rokove."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.deadline_parser import ekstrahuj_rokove


# ─── T1: Apsolutni datum DD.MM.YYYY ──────────────────────────────────────────

def test_apsolutni_datum_dd_mm_yyyy():
    """Standard DD.MM.YYYY datum mora biti parsiran kao apsolutni rok."""
    tekst = "Rok za podnošenje žalbe ističe 15.11.2025. godine."
    rokovi = ekstrahuj_rokove(tekst)
    assert len(rokovi) >= 1
    r = rokovi[0]
    assert r["tip"] == "apsolutni"
    assert r["vrednost"] == "15.11.2025"
    assert "15.11.2025" in r["kontekst"]


def test_apsolutni_datum_jednocifreni_dan():
    """Jednocifreni dan treba biti zero-padded: 5.3.2025 → 05.03.2025."""
    tekst = "Ugovor je zaključen dana 5.3.2025."
    rokovi = ekstrahuj_rokove(tekst)
    assert len(rokovi) >= 1
    assert rokovi[0]["vrednost"] == "05.03.2025"


def test_vise_datuma_u_tekstu():
    """Tekst sa više datuma treba da vrati sve."""
    tekst = "Ugovor od 01.01.2024. Rok za ispunjenje: 31.03.2024."
    rokovi = ekstrahuj_rokove(tekst)
    vrednosti = {r["vrednost"] for r in rokovi}
    assert "01.01.2024" in vrednosti
    assert "31.03.2024" in vrednosti


# ─── T2: Relativni rok "u roku od N dana" ────────────────────────────────────

def test_relativni_rok_dana():
    """'u roku od 8 dana' mora biti relativni rok sa vrednosti '8 dana'."""
    tekst = "Zaposleni ima pravo da podnese prigovor u roku od 8 dana od prijema rešenja."
    rokovi = ekstrahuj_rokove(tekst)
    relativni = [r for r in rokovi if r["tip"] == "relativni"]
    assert len(relativni) >= 1
    vrednosti = {r["vrednost"] for r in relativni}
    assert any("8" in v and "dan" in v for v in vrednosti)


def test_relativni_rok_30_dana():
    """'u roku od 30 dana' mora biti parsiran."""
    tekst = "Žalba se podnosi u roku od 30 dana od dostavljanja presude."
    rokovi = ekstrahuj_rokove(tekst)
    relativni = [r for r in rokovi if r["tip"] == "relativni"]
    assert len(relativni) >= 1
    assert any("30" in r["vrednost"] for r in relativni)


def test_relativni_rok_meseci():
    """'u roku od 3 meseca' mora biti parsiran."""
    tekst = "Ugovornik je obavezan da isporuku izvrši u roku od 3 meseca."
    rokovi = ekstrahuj_rokove(tekst)
    relativni = [r for r in rokovi if r["tip"] == "relativni"]
    assert len(relativni) >= 1
    assert any("3" in r["vrednost"] for r in relativni)


# ─── T3: Kategorija zastarelosti ─────────────────────────────────────────────

def test_kategorija_zastarelost():
    """Rok pored reči 'zastar...' → kategorija 'zastarelost'."""
    tekst = "Potraživanje zastareva u roku od 3 godine od nastanka štete (ZOO čl. 376)."
    rokovi = ekstrahuj_rokove(tekst)
    assert len(rokovi) >= 1
    kat = [r["kategorija"] for r in rokovi]
    assert "zastarelost" in kat


def test_kategorija_zastarelost_datum():
    """Apsolutni datum u kontekstu zastarelosti → kategorija 'zastarelost'."""
    tekst = "Rok zastarelosti ističe 20.05.2027. Nije moguće tužiti posle toga."
    rokovi = ekstrahuj_rokove(tekst)
    kat = [r["kategorija"] for r in rokovi]
    assert "zastarelost" in kat


# ─── T4: Kategorija žalbe ────────────────────────────────────────────────────

def test_kategorija_zalba():
    """Rok pored reči 'žalb...' → kategorija 'zalba'."""
    tekst = "Rok za podnošenje žalbe je 15 dana od dostave prvostepene odluke."
    rokovi = ekstrahuj_rokove(tekst)
    assert len(rokovi) >= 1
    kat = [r["kategorija"] for r in rokovi]
    assert "zalba" in kat


def test_kategorija_zalba_datum():
    """Apsolutni datum u kontekstu žalbe → kategorija 'zalba'."""
    tekst = "Žalba mora biti podneta do 31.12.2025. godine."
    rokovi = ekstrahuj_rokove(tekst)
    assert len(rokovi) >= 1
    # At least one with zalba category
    kat = [r["kategorija"] for r in rokovi]
    assert "zalba" in kat


# ─── T5: Prazan tekst → prazna lista ─────────────────────────────────────────

def test_prazan_tekst():
    """Prazan string → prazna lista, bez greške."""
    assert ekstrahuj_rokove("") == []


def test_whitespace_tekst():
    """Tekst samo od razmaka → prazna lista."""
    assert ekstrahuj_rokove("   \n\t  ") == []


def test_tekst_bez_rokova():
    """Tekst koji ne sadrži nikakve rokove → prazna lista."""
    tekst = "Ovo je ugovor o prijateljstvu i nema nikakvih rokova."
    rokovi = ekstrahuj_rokove(tekst)
    assert rokovi == []
