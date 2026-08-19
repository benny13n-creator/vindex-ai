# -*- coding: utf-8 -*-
"""
P1-4 klasa E — jutarnji brifing ne sme tvrditi odsustvo rokova iz palog upita.

PRE-STATE (dokazano izvrsenjem 2026-08-19):
  `routers/morning_briefing.py::_generiši_briefing` racuna `_kljucni_rok`
  ISKLJUCIVO iz praznine listi (`rocista_danas` / `rokovi_hitni` /
  `rokovi_uskoro`). Signal `rokovi_dostupni` — koji vec cuva i prompt modela
  (:210) i `_otvaranje` (:378) — na to polje nije bio primenjen.

  Posledica, mereno: kad citanje rokova padne, `ai_briefing` sadrzi ISTOVREMENO
    "⚠ Rokovi trenutno nisu dostupni — odsustvo rokova ... NE znaci da ih nema"
  i
    "Nema hitnih rokova u narednih 7 dana."
  Dve protivrecne recenice u istom tekstu; druga je neistinita. Brifing je
  artefakt koji advokat cita svako jutro pre planiranja dana.

INVARIJANTA: FAILURE != EMPTY. Odsustvo se sme tvrditi samo iz izvrsenog upita.
"""
import asyncio

import pytest
from unittest.mock import MagicMock, patch

import routers.morning_briefing as mb

UID = "00000000-0000-0000-0000-000000000001"

TVRDNJA_ODSUSTVA = "Nema hitnih rokova u narednih 7 dana."
UPOZORENJE = "nisu pročitani iz baze"

KVAROVI = {
    "42703_kolona": Exception("column predmet_hronologija.naziv does not exist (42703)"),
    "PGRST205_tabela": Exception("Could not find the table (PGRST205)"),
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "timeout": TimeoutError("connection timeout expired"),
    "neocekivani": ValueError("neocekivano stanje drajvera"),
}


class _P:
    """Prihvata bilo koji lanac filtera; `execute()` vraca redove ili puca."""

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


def _supa(greska_rokova=None, redovi_hronologije=None, pada_samo_poziv=None):
    """`predmet_hronologija` je kanonski vlasnik rokova (shared/rokovi.py).

    `pada_samo_poziv=N` obara SAMO N-ti (1-indeksiran) upit nad tom tabelom —
    brifing je cita dvaput (aktuelni rokovi + propusteni). Bez toga se ne moze
    razlikovati parcijalni pad od potpunog.
    """
    m = MagicMock()
    brojac = {"n": 0}

    def _table(ime):
        t = MagicMock()
        if ime == "predmet_hronologija":
            brojac["n"] += 1
            g = greska_rokova
            if pada_samo_poziv is not None:
                g = KVAROVI["42703_kolona"] if brojac["n"] == pada_samo_poziv else None
            t.select.return_value = _P(redovi_hronologije or [], g)
        else:
            t.select.return_value = _P([])
        return t

    m.table.side_effect = _table
    return m


# Svaka recenica kojom brifing tvrdi ODSUSTVO obaveza. Nijedna ne sme izaci
# kad rokovi nisu procitani — ni ona iz `_kljucni_rok`, ni ona iz `_otvaranje`.
TVRDNJE_ODSUSTVA = (
    "Nema hitnih rokova u narednih 7 dana.",
    "Nema hitnih obaveza za danas",
    "miran dan",
)


def _brifing(supa):
    # AI sinteza je zamenjena: meri se DETERMINISTICKI sastavljen tekst
    # ( iz sablona), a ne odgovor modela. Bez ovoga bi test zvao
    # naplativi API i bio nedeterministican.
    def _bez_modela(*a, **k):
        raise RuntimeError("model namerno nedostupan u testu")

    with patch.object(mb, "_get_supa", return_value=supa),          patch.object(mb, "_chat_completion", side_effect=_bez_modela, create=True),          patch("openai.OpenAI", side_effect=_bez_modela):
        b = asyncio.run(mb._generiši_briefing(UID, supa))
    tekst = " ".join(str(v) for v in b.values() if isinstance(v, str))
    return b, tekst


# ── A. kontrola: legitimno prazno mora ostati legitimno prazno ───────────────

def test_A_legitimno_prazno_i_dalje_tvrdi_odsustvo():
    """Bez ovoga bi „popravka" koja uvek cuti prolazila kao ispravna."""
    b, tekst = _brifing(_supa())
    assert b["rokovi_dostupni"] is True
    assert TVRDNJA_ODSUSTVA in tekst, "izvrsen upit sa nula redova SME tvrditi odsustvo"
    assert UPOZORENJE not in tekst


# ── C/D/F. svaki kvar citanja rokova ────────────────────────────────────────

@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_CDF_pad_citanja_rokova_ne_tvrdi_odsustvo(kvar):
    b, tekst = _brifing(_supa(greska_rokova=KVAROVI[kvar]))
    assert b["rokovi_dostupni"] is False, kvar
    for tvrdnja in TVRDNJE_ODSUSTVA:
        assert tvrdnja not in tekst, \
            "pao upit je proizveo tvrdnju o odsustvu %r (%s)" % (tvrdnja, kvar)
    assert UPOZORENJE in tekst, kvar


@pytest.mark.parametrize("poziv", [1, 2])
def test_E_parcijalni_pad_je_i_dalje_nedostupnost(poziv):
    """Brifing cita rokove DVAPUT (aktuelni + propusteni). Pad BILO KOG od ta
    dva citanja znaci da odsustvo rokova nije dokazano."""
    b, tekst = _brifing(_supa(pada_samo_poziv=poziv))
    assert b["rokovi_dostupni"] is False, "pad %d. citanja nije oznacen" % poziv
    for tvrdnja in TVRDNJE_ODSUSTVA:
        assert tvrdnja not in tekst, \
            "parcijalni pad (%d. citanje) proizveo tvrdnju %r" % (poziv, tvrdnja)


def test_G_pad_i_prazno_daju_RAZLICIT_brifing():
    _, t_pad = _brifing(_supa(greska_rokova=KVAROVI["42703_kolona"]))
    _, t_prazno = _brifing(_supa())
    assert t_pad != t_prazno


def test_H_nema_protivrecnosti_u_istom_tekstu():
    """Tacan pre-state defekt: upozorenje i tvrdnja su stajali zajedno."""
    _, tekst = _brifing(_supa(greska_rokova=KVAROVI["42501_rls"]))
    assert not (TVRDNJA_ODSUSTVA in tekst and UPOZORENJE in tekst), \
        "brifing istovremeno upozorava i tvrdi odsustvo"


def test_I_sve_tvrdnje_o_odsustvu_su_iza_guarda():
    """Staticka brana: svaka recenica o odsustvu rokova mora biti u grani
    koja je iza provere `rokovi_dostupni`."""
    import io
    src = io.open("routers/morning_briefing.py", encoding="utf-8").read()
    for recenica in (TVRDNJA_ODSUSTVA, "Nema hitnih rokova ni rocista"):
        i = src.index('= "%s' % recenica) if '= "%s' % recenica in src else src.index(recenica)
        # 600 znakova unazad mora sadrzati proveru dostupnosti
        assert "rokovi_dostupni" in src[max(0, i - 600):i], \
            "recenica %r nije iza provere `rokovi_dostupni`" % recenica
