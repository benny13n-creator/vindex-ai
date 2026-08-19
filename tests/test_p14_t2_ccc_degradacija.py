# -*- coding: utf-8 -*-
"""
NIGHT2-A-001 — Command Center ne sme tvrditi odsustvo iz palog izvora.

PRE-STATE (dokazano izvrsenjem 2026-08-19):
  `routers/ccc.py::get_ccc` gura 7 izvora kroz `return_exceptions=True` i
  svaki pad svodi na `[]` (8 mesta), bez ijednog polja o degradaciji.
  Frontend (`vindex.js::ccc_load`) nije proveravao `r.ok`, a `_ccc_render`
  izdaje „smart action" cipove na osnovu ODSUSTVA podatka.

  Mereno, sa ispravnom kontrolom:
    kontrola  `predmet_dokazi` vraca 2 reda -> `dok_stats.ukupno == 2`, bez cipa
    kvar      `predmet_dokazi` pada (42703) -> `ukupno == 0` -> CRVENI cip
              „Uploaduj prvi dokument" za predmet koji dokaze IMA.
  Isto vazi za `kritican_rok = None` -> izostanak crvenog cipa o roku, sto je
  tvrdnja da kritican rok ne postoji.

INVARIJANTA: odsustvo se sme tvrditi samo iz izvrsenog upita.
"""
import asyncio

import pytest
from unittest.mock import MagicMock, patch

import routers.ccc as ccc

KORISNIK = {"user_id": "u-1", "email": "advokat@vindex.rs", "role": "advokat"}

KVAROVI = {
    "42703_kolona": Exception("column does not exist (42703)"),
    "PGRST205_tabela": Exception("Could not find the table (PGRST205)"),
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "timeout": TimeoutError("connection timeout expired"),
    "neocekivani": ValueError("neocekivano stanje drajvera"),
}

REDOVI = {
    "predmeti": [{"id": "p1", "naziv": "Spor 1/2026", "status": "aktivan", "tip": "parnica"}],
    "predmet_dokazi": [{"id": "e1", "snaga": "jaka", "kategorija": "isprava"},
                       {"id": "e2", "snaga": "srednja", "kategorija": "isprava"}],
}


class _P:
    def __init__(self, redovi, greska=None):
        self._r = redovi
        self._g = greska

    def __getattr__(self, ime):
        if ime == "not_":
            return self

        def poziv(*a, **k):
            if ime == "execute":
                if self._g is not None:
                    raise self._g
                m = MagicMock()
                m.data = list(self._r)
                return m
            return self
        return poziv


def _supa(puca=None, kvar=None):
    puca = puca or set()
    kvar = kvar or KVAROVI["42703_kolona"]
    m = MagicMock()

    def _table(ime):
        t = MagicMock()
        t.select.return_value = _P(REDOVI.get(ime, []), kvar if ime in puca else None)
        return t

    m.table.side_effect = _table
    return m


def _ccc(puca=None, kvar=None):
    fn = getattr(ccc.get_ccc, "__wrapped__", ccc.get_ccc)
    with patch.object(ccc, "_get_supa", return_value=_supa(puca, kvar)):
        return asyncio.run(fn(predmet_id="p1", user=KORISNIK))


# ── A. kontrola ─────────────────────────────────────────────────────────────

def test_A_kontrola_izvori_procitani():
    """Bez ovoga bi svaki test ispod prolazio vakuumski."""
    d = _ccc()
    assert d["dok_stats"]["ukupno"] == 2, "kontrola ne cita dokaze — test ne bi merio nista"
    assert d["provera_potpuna"] is True
    assert d["degradirani_izvori"] == []


# ── C/D/F. kvarovi ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_CDF_pad_dokaza_se_objavljuje(kvar):
    d = _ccc(puca={"predmet_dokazi"}, kvar=KVAROVI[kvar])
    assert d["dok_stats"]["ukupno"] == 0
    assert d["provera_potpuna"] is False, kvar
    assert "dokazi" in d["degradirani_izvori"], kvar


@pytest.mark.parametrize("tabela,ime", [
    ("predmet_dokazi", "dokazi"),
    ("predmet_dokumenti", "dokumenti"),
    ("rocista", "rokovi"),
    ("predmet_hronologija", "hronologija"),
    ("billing_entries", "naplata"),
    ("predmet_klijenti", "klijenti"),
])
def test_E_svaki_izvor_se_imenuje(tabela, ime):
    """Meri se IME izvora, ne samo da je lista neprazna."""
    d = _ccc(puca={tabela})
    assert ime in d["degradirani_izvori"], \
        "pad %s nije objavljen kao %r (dobijeno %r)" % (tabela, ime, d["degradirani_izvori"])
    assert d["provera_potpuna"] is False


def test_G_pad_i_prazno_daju_RAZLICIT_odgovor():
    assert _ccc(puca={"predmet_dokazi"}) != _ccc()


def test_H_nijedan_tihi_gutac_nije_ostao():
    import io
    src = io.open("routers/ccc.py", encoding="utf-8").read()
    assert "Exception) else []" not in src, "stara tiha koercija jos postoji"
    assert src.count('_izvor(') >= 9  # 1 definicija + 8 poziva
