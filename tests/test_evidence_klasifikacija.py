# -*- coding: utf-8 -*-
"""
Tests for routers/evidence.py::klasifikuj_i_sacuvaj — reliability fix
(2026-07-19, posle ispravke migracija 016/074): predmet_dokumenti update i
predmet_dokazi insert su ranije delili JEDAN try/except, tako da bi pad
prvog sprečio da se drugi ikad pokuša, iako su nezavisni upisi. Sada su
razdvojena u dva bloka.

Cisti unit testovi — mock-uje se get_supa() i _klasifikuj_dokument()
(GPT poziv), nema stvarne mreze/baze.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


def _fake_rezultat():
    return {
        "tip_dokaza": "ugovor",
        "pravni_elementi": ["uzročna veza"],
        "ai_tags": {"sud_organ": "Osnovni sud"},
        "kljucne_cinjenice": ["Ugovor potpisan 2026-01-01."],
    }


def test_predmet_dokazi_insert_happens_even_if_predmet_dokumenti_update_fails():
    """Kljucni regresioni test: pre fix-a, pad prvog upisa je sprecavao
    drugi da se ikad pokusa."""
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokumenti_table.update.return_value.eq.return_value.execute.side_effect = Exception("schema gap")
    dokazi_table = MagicMock()

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", return_value=_fake_rezultat()):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "ugovor.pdf", "tekst", "user-1")

    dokazi_table.insert.assert_called_once()
    row = dokazi_table.insert.call_args[0][0][0]
    assert row["tvrdnja"] == "Ugovor potpisan 2026-01-01."


def test_predmet_dokumenti_update_happens_even_if_predmet_dokazi_insert_fails():
    """Obrnut smer: pad drugog upisa ne sme da omete da je prvi vec uspeo
    (ne mora da se ponovo pokusava, samo ne sme da izgleda kao da nikad nije
    ni pokusan)."""
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()
    dokazi_table.insert.return_value.execute.side_effect = Exception("dokazi table down")

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", return_value=_fake_rezultat()):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "ugovor.pdf", "tekst", "user-1")

    dokumenti_table.update.assert_called_once()
    update_payload = dokumenti_table.update.call_args[0][0]
    assert update_payload["tip_dokaza"] == "ugovor"


def test_both_succeed_normally_no_regression():
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", return_value=_fake_rezultat()):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "ugovor.pdf", "tekst", "user-1")

    dokumenti_table.update.assert_called_once()
    dokazi_table.insert.assert_called_once()


def test_never_raises_even_if_both_fail():
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokumenti_table.update.return_value.eq.return_value.execute.side_effect = Exception("boom 1")
    dokazi_table = MagicMock()
    dokazi_table.insert.return_value.execute.side_effect = Exception("boom 2")

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", return_value=_fake_rezultat()):
        # ne sme da baci — pozadinski zadatak ne sme da padne aplikaciju
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "ugovor.pdf", "tekst", "user-1")


def test_no_predmet_dokazi_insert_when_no_kljucne_cinjenice():
    """Ako GPT ne vrati kljucne cinjenice, insert se uopste ne poziva (rows
    prazan) — ne treba prazan insert poziv."""
    from routers import evidence as ev

    supa = MagicMock()
    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa.table = MagicMock(side_effect=_table)

    prazan_rezultat = {"tip_dokaza": "ostalo", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": []}
    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", return_value=prazan_rezultat):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "prazan.pdf", "tekst", "user-1")

    dokazi_table.insert.assert_not_called()
