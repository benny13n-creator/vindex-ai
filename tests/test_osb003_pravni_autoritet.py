# -*- coding: utf-8 -*-
"""OSB003 Task 6 — anti-halucinacioni čuvar odgovora (main.py::_proveri_halucinaciju) pod napadom.

Ugovor čuvara (njegov docstring, v2.0): SVAKI citiran broj člana mora postojati u dostavljenom kontekstu.
Mere se: tačan citat prolazi, izmišljen i pogrešan broj člana se blokiraju, izmišljen doslovni citat se
blokira. OGRANIČENJE (karakterizacija, nije u ugovoru): isti broj člana iz DRUGOG zakona prolazi, jer
čuvar ne poredi naziv zakona.
"""
import pytest

KONTEKST = [
    "Zakon o obligacionim odnosima, Član 154: Ko drugome prouzrokuje štetu dužan je naknaditi je, "
    "ukoliko ne dokaže da je šteta nastala bez njegove krivice. " * 3,
    "Zakon o obligacionim odnosima, Član 200: Za pretrpljene fizičke bolove, za pretrpljene duševne bolove "
    "zbog umanjenja životne aktivnosti sud će dosuditi pravičnu novčanu naknadu. " * 3,
]


@pytest.fixture(scope="module")
def cuvar():
    import main
    return main._proveri_halucinaciju


def test_tacan_citat_prolazi(cuvar):
    ok, razlog = cuvar("Prema Članu 154 ZOO, odgovornost postoji osim ako se dokaže odsustvo krivice.", KONTEKST)
    assert ok, razlog


def test_izmisljen_clan_blokiran(cuvar):
    ok, razlog = cuvar("Prema Članu 9999 ZOO tužilac ima pravo na naknadu.", KONTEKST)
    assert not ok and "9999" in razlog


def test_stvaran_izvor_pogresan_broj_clana_blokiran(cuvar):
    ok, razlog = cuvar("Naknada nematerijalne štete propisana je Članom 201 ZOO.", KONTEKST)
    assert not ok and "201" in razlog


def test_mesavina_tacnog_i_pogresnog_blokira_ceo_odgovor(cuvar):
    ok, razlog = cuvar("Član 154 i Član 156 ZOO uređuju odgovornost.", KONTEKST)   # 154/155/200 su izuzeti (ZOO šablon)
    assert not ok and "156" in razlog


@pytest.mark.parametrize("odgovor,broj", [
    ("Prema članu 9999 ZOO tužilac ima pravo na naknadu.", "9999"),
    ("Odgovornost je uređena čl. 9999 ZOO.", "9999"),
    ("Naknada je propisana Članom 201 ZOO.", "201"),
    ("U smislu člana 4321 Zakona o radu otkaz je ništav.", "4321"),
])
def test_padezni_oblici_i_skracenica_ne_zaobilaze_cuvar(cuvar, odgovor, broj):
    """OSB003: ranije su „članu/članom/člana N" i „čl. N" prolazili NEPROVERENI (regex je tražio „Član N")."""
    ok, razlog = cuvar(odgovor, KONTEKST)
    assert not ok and broj in razlog, (odgovor, razlog)


@pytest.mark.parametrize("u_kontekstu", ["Član 179", "člana 179"])
def test_padezni_oblik_tacnog_clana_i_dalje_prolazi(cuvar, u_kontekstu):
    """179 NIJE u listi izuzetaka. Tačan član u padežu/skraćenici prolazi, i kad je kontekst u padežu."""
    kontekst = KONTEKST + [f"Zakon o radu, {u_kontekstu}: Poslodavac može zaposlenom da otkaže ugovor o radu ako za to postoji "
                           "opravdani razlog koji se odnosi na radnu sposobnost zaposlenog i njegovo ponašanje. " * 2]
    for odgovor in ("Prema članu 179 Zakona o radu otkaz je dozvoljen.", "Vidi čl. 179 Zakona o radu.", "Član 179 ZR."):
        ok, razlog = cuvar(odgovor, kontekst)
        assert ok, (odgovor, razlog)


def test_izmisljen_doslovni_citat_blokiran(cuvar):
    ok, razlog = cuvar('CITAT IZ ZAKONA: "Svako lice ima neotuđivo pravo na naknadu bez obzira na krivicu i dokaze."', KONTEKST)
    assert not ok, razlog


def test_ogranicenje_isti_broj_clana_drugi_zakon_prolazi(cuvar):
    """Karakterizacija: Član 200 postoji u kontekstu (ZOO), odgovor ga pripisuje Zakonu o radu — čuvar to ne vidi.
    Ako se ovo ikad promeni (čuvar počne da poredi zakon), test treba obrnuti — tada je ograničenje zatvoreno."""
    ok, _ = cuvar("Prema Članu 200 Zakona o radu zaposleni ima pravo na naknadu.", KONTEKST)
    assert ok is True
