# -*- coding: utf-8 -*-
"""S10 — naziv roka iz Smart Intake prijema i naziv ispravke (nalazi nezavisnog pregleda).

Naziv nosi rečenicu iz dokumenta SAMO kad je jasno koja je: broj obaveza modela za datum = broj dokaznih rečenica,
rečenice se razlikuju i svaka sadrži sam datum. Inače ostaje raniji naziv sa rednim brojem (bez migracije 144 naziv je
deo identiteta — dve obaveze ne smeju dobiti isti naziv, inače se druga tiho gubi kao „već postoji“).
Ispravka izostavlja SAMO ispravljeni datum iz citata (brojčano i sa nazivom meseca), ostali datumi ostaju."""
import os
from datetime import date

os.environ.setdefault("FOUNDER_EMAILS", "ci@example.com")

import pytest

from routers.smart_intake import _citati_nesporni
from shared.rok_ispravka import opis_ispravke
from shared.rokovi import obaveze_po_datumu

D = "2026-11-15"


@pytest.mark.parametrize("tekst,obaveza_modela,ocekivano", [
    ("Rok za odgovor na tuzbu istice 15.11.2026. godine.\nRok za uplatu sudske takse istice 15.11.2026. godine.", 2, True),
    # prelomljen red (sken): obe rečenice su „istice 15.11.2026. godine.“ — isti naziv bi bez 144 spojio dve obaveze
    ("Rok za odgovor na tuzbu\nistice 15.11.2026. godine.\nRok za uplatu takse\nistice 15.11.2026. godine.", 2, False),
    # model je našao samo jednu od dve obaveze: ne zna se koja rečenica je njegova
    ("Rok za odgovor na tuzbu istice 15.11.2026. godine.\nRok za uplatu sudske takse istice 15.11.2026. godine.", 1, False),
    # dve obaveze u istom redu, model dve: jedna rečenica za dve obaveze
    ("Tuzeni do 15.11.2026. podnese odgovor na tuzbu, a rok za uplatu takse istice 15.11.2026. godine.", 2, False),
    # dugačak red: prvih 160 znakova ne sadrže ni obavezu ni datum
    ("U skladu sa odredbama zakona i ranijim aktima suda, a imajuci u vidu sve okolnosti slucaja koje su navedene u "
     "obrazlozenju ovog resenja i u spisima predmeta, rok za odgovor na tuzbu istice 15.11.2026. godine.", 1, False),
])
def test_recenica_je_naziv_samo_kad_je_nesporno_koja_je(tekst, obaveza_modela, ocekivano):
    assert _citati_nesporni(obaveze_po_datumu(tekst).get(D, []), obaveza_modela, D) is ocekivano


@pytest.mark.parametrize("citat,ocekivano", [
    ("Rok iz dokumenta: Rok za odgovor istice 15.11.2026. godine.", "Rok iz dokumenta: Rok za odgovor istice … godine."),
    ("Rok iz dokumenta: Rok za odgovor istice 15. novembra 2026. godine.", "Rok iz dokumenta: Rok za odgovor istice … godine."),
    ("Rok iz dokumenta (OCR, proveriti): Rok istice 15. 11. 2026 godine.", "Rok iz dokumenta (OCR, proveriti): Rok istice … godine."),
    # drugi datum iste rečenice (ročište) NIJE ispravljen — ostaje
    ("Rok iz dokumenta: Rok istice 15.11.2026, rociste je 03.11.2026.", "Rok iz dokumenta: Rok istice …, rociste je 03.11.2026."),
])
def test_ispravka_izostavlja_samo_ispravljeni_datum(citat, ocekivano):
    assert opis_ispravke(None, citat, date(2026, 11, 20), D) == f"{ocekivano} — datum ispravio advokat: 20.11.2026."


def test_ispravka_bez_citata_i_sa_tekstom_advokata_kao_ranije():
    assert opis_ispravke(None, "Rok iz dokumenta (presuda)", date(2026, 11, 20), D) == "Rok iz dokumenta (presuda)"
    assert opis_ispravke("Žalba — tačan rok", "Rok iz dokumenta: x 15.11.2026.", date(2026, 11, 20), D) == "Žalba — tačan rok"
    assert opis_ispravke(None, None, date(2026, 11, 20), D) == "Rok"
