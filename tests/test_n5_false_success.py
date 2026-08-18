# -*- coding: utf-8 -*-
"""
N5 — FALSE-SUCCESS CLOSURE: M1 (workspace/dashboard), M2 (billing), M3 (voice).

CENTRALNI INVARIJANT
  FAILED != EMPTY · UNKNOWN != SUCCESS · PARTIAL != COMPLETE
  Nijedan pad izvora ne sme postati pozitivna tvrdnja ni dozvoljena akcija.
  Validno prazno mora ostati validno prazno.

PRE-STATE (dokazano izvrsenjem u N5 forensic pass-u)
  A-001 `routers/workspace.py` — timeout na SVIM upitima -> HTTP 200,
        `ukupno_aktivnih=0`, nula objave -> UI: zeleni ✓ „Sve je pod kontrolom".
  A-002 `routers/billing.py`   — `billing_entries` pada (42703) -> `ukupno_rsd=0`
        -> UI boji „Ukupno duguje 0" u ZELENO (`vindex.js:2582`).
  A-003 `routers/voice.py::_fetch_rocista` — pad -> `[]` -> advokat CUJE
        „Nema zakazanih rocista u narednih 14 dana."
  A-004 `routers/dashboard.py::_safe` — svaki pao izvor -> `[]`, nula objave.
"""
import asyncio
import io

import pytest
from unittest.mock import MagicMock, patch

import routers.billing as billing
import routers.dashboard as dashboard
import routers.voice as voice
import routers.workspace as workspace
import shared.query_timeout as qt

UID = "00000000-0000-0000-0000-000000000001"
KORISNIK = {"user_id": UID, "email": "advokat@vindex.rs", "role": "advokat"}

KVAROVI = {
    "42703_kolona": Exception("column does not exist (code 42703)"),
    "PGRST205_tabela": Exception("Could not find the table (PGRST205)"),
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "neocekivani": ValueError("neocekivano stanje drajvera"),
}


# ═══════════════════════════════════════════════════════════════════════════
# Lanac-verni dvojnik: vraca redove SAMO ako je pozvan tacan lanac poziva.
# Fake koji na svaki `.bilo_sta()` vraca MagicMock ne moze da razlikuje
# ispravan upit od pogresnog — pa „kontrola" prolazi vakuumski.
# ═══════════════════════════════════════════════════════════════════════════

class _Lanac:
    def __init__(self, tabela, ocekivan, redovi, greska):
        self._t = tabela
        self._o = list(ocekivan)
        self._i = 0
        self._redovi = redovi
        self._greska = greska

    def __getattr__(self, ime):
        def poziv(*a, **k):
            if self._greska is not None:
                raise self._greska
            if self._i >= len(self._o) or self._o[self._i] != ime:
                ocek = self._o[self._i] if self._i < len(self._o) else "<kraj>"
                raise AssertionError(
                    "tabela %r: ocekivan poziv %r na koraku %d, dobijen %r"
                    % (self._t, ocek, self._i, ime))
            self._i += 1
            if ime == "execute":
                r = MagicMock()
                r.data = self._redovi
                return r
            return self
        return poziv


def _supa_rocista(redovi=None, greska=None, greska_predmeti=None, redovi_predmeti=None):
    """Dvojnik koji sprovodi TACAN lanac iz `_fetch_rocista`."""
    m = MagicMock()

    def _table(ime):
        if ime == "rocista":
            return _Lanac("rocista",
                          ["select", "eq", "eq", "gte", "lte", "order", "limit", "execute"],
                          redovi if redovi is not None else [], greska)
        if ime == "predmeti":
            return _Lanac("predmeti", ["select", "in_", "execute"],
                          redovi_predmeti if redovi_predmeti is not None else [],
                          greska_predmeti)
        raise AssertionError("neocekivana tabela: %r" % ime)

    m.table.side_effect = _table
    return m


# ═══════════════════════════════════════════════════════════════════════════
# M3 — voice::_fetch_rocista
# ═══════════════════════════════════════════════════════════════════════════

ROCISTE = {"datum": "2026-08-25", "vreme": "09:30", "sud": "Prvi osnovni",
           "sudnica": "12", "predmet_id": "p-1", "status": "zakazano"}


def test_m3_A_happy_ima_rocista():
    """KONTROLA koja MORA proci kroz stvarni lanac upita."""
    r = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(
        redovi=[dict(ROCISTE)],
        redovi_predmeti=[{"id": "p-1", "naziv": "Spor 1/2026", "tuzilac": "A", "tuzeni": "B"}],
    ), days_ahead=14))
    assert r["uspeh"] is True and r["stanje"] == "ok"
    assert len(r["rocista"]) == 1
    assert r["rocista"][0]["predmet_naziv"] == "Spor 1/2026", "naziv predmeta nije spojen"


def test_m3_B_legitimno_prazno():
    """Validno prazno mora ostati validno prazno."""
    r = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(redovi=[]), days_ahead=14))
    assert r["uspeh"] is True and r["stanje"] == "prazno" and r["rocista"] == []


@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_m3_CDF_svaki_kvar_je_neuspeh(kvar):
    r = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(greska=KVAROVI[kvar]), days_ahead=14))
    assert r["uspeh"] is False and r["stanje"] == "neuspeh", kvar
    assert r["rocista"] == []


def test_m3_D_timeout_je_neuspeh():
    r = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(greska=TimeoutError("timeout")), days_ahead=14))
    assert r["uspeh"] is False


def test_m3_E_parcijalni_pad_ne_brise_rocista():
    """Nazivi predmeta su ukras; postojanje rocista je cinjenica.
    Ranije je pad OVOG upita rusio ceo poziv u `[]` = „nema rocista"."""
    r = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(
        redovi=[dict(ROCISTE)], greska_predmeti=KVAROVI["42501_rls"]), days_ahead=14))
    assert r["uspeh"] is True and r["stanje"] == "ok"
    assert len(r["rocista"]) == 1, "parcijalni pad je progutao poznato rociste"
    assert r["rocista"][0]["predmet_naziv"] == ""


def test_m3_H_neuspeh_nikad_ne_postaje_recenica_o_odsustvu():
    """Kljucna posledica: sta advokat CUJE."""
    izvor = io.open("routers/voice.py", encoding="utf-8").read()
    assert "_ROCISTA_NEUSPEH_ODGOVOR" in izvor
    i = izvor.index("if need_rocista:")
    # sidro je STVARNI poziv koji izgovara odsustvo, ne bilo koji pomen te
    # recenice (komentari je takodje sadrze)
    j = izvor.index('context_parts.append("Nema zakazanih', i)
    blok = izvor[i:j]
    assert 'if not _rez_rocista.get("uspeh")' in blok, "grana neuspeha ne postoji"
    assert "_ROCISTA_NEUSPEH_ODGOVOR" in blok, \
        "recenica o odsustvu je dostizna pre provere uspeha"


def test_m3_G_odgovor_pri_padu_nije_isti_kao_prazno():
    pad = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(greska=KVAROVI["42703_kolona"])))
    prazno = asyncio.run(voice._fetch_rocista(UID, _supa_rocista(redovi=[])))
    assert pad != prazno and pad["uspeh"] != prazno["uspeh"]


# ═══════════════════════════════════════════════════════════════════════════
# M2 — billing.py, cetiri endpointa
# ═══════════════════════════════════════════════════════════════════════════

def _supa_billing(puca=None, redovi=None):
    puca = puca or set()
    redovi = redovi or {}
    m = MagicMock()

    def _table(ime):
        t = MagicMock()
        if ime in puca:
            def boom(*a, **k):
                raise KVAROVI["42703_kolona"]
            t.select.side_effect = boom
        else:
            def _rec(*a, **k):
                r = MagicMock()
                r.data = redovi.get(ime, [])
                return r
            t.select.return_value = _Prolaz(_rec)
        return t

    m.table.side_effect = _table
    return m


class _Prolaz:
    """Prihvata bilo koji lanac filtera; `.execute()` vraca konfigurisane redove."""
    def __init__(self, izvrsi):
        self._izvrsi = izvrsi

    def __getattr__(self, ime):
        # `not_` je u postgrest-u SVOJSTVO, ne poziv: `.not_.in_(...)`.
        if ime == "not_":
            return self

        def poziv(*a, **k):
            if ime == "execute":
                return self._izvrsi()
            return self
        return poziv


ENDPOINTI = [
    ("billing_pregled", {}),
    ("billing_dugovanja", {}),
    ("billing_naplata_status", {}),
]


@pytest.mark.parametrize("ime,kw", ENDPOINTI)
def test_m2_A_happy_prazna_baza_je_200(ime, kw):
    fn = getattr(billing, ime).__wrapped__
    with patch.object(billing, "_get_supa", return_value=_supa_billing()):
        d = asyncio.run(fn(request=MagicMock(), user=KORISNIK, **kw))
    assert isinstance(d, dict), ime


@pytest.mark.parametrize("ime,kw", ENDPOINTI)
@pytest.mark.parametrize("izvor", ["billing_entries", "fakture"])
def test_m2_C_pad_izvora_koji_nosi_broj_je_503(ime, kw, izvor):
    """DB failure != 0 RSD. Nikada „duguje 0"."""
    from fastapi import HTTPException
    fn = getattr(billing, ime).__wrapped__
    with patch.object(billing, "_get_supa", return_value=_supa_billing(puca={izvor})):
        try:
            d = asyncio.run(fn(request=MagicMock(), user=KORISNIK, **kw))
        except HTTPException as e:
            assert e.status_code == 503, (ime, izvor)
            assert "netačan" in str(e.detail) or "nije dostupan" in str(e.detail)
            return
        # Endpoint koji taj izvor uopste ne cita sme da vrati 200 —
        # ali tada NE SME imati iznos izveden iz njega.
        assert izvor not in _izvori_endpointa(ime), \
            "%s cita %s a pad nije oborio odgovor: %r" % (ime, izvor, d)


def _izvori_endpointa(ime):
    import ast
    src = io.open("routers/billing.py", encoding="utf-8").read()
    t = ast.parse(src)
    fn = next(n for n in ast.walk(t)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == ime)
    seg = ast.get_source_segment(src, fn) or ""
    return {x for x in ("billing_entries", "fakture", "predmeti") if x in seg}


def test_m2_E_parcijalni_pad_dopunskog_izvora_se_imenuje():
    """`predmeti` nosi samo naziv — izvestaj ostaje upotrebljiv, ali se objavi."""
    fn = billing.billing_dugovanja.__wrapped__
    with patch.object(billing, "_get_supa", return_value=_supa_billing(puca={"predmeti"})):
        d = asyncio.run(fn(request=MagicMock(), user=KORISNIK))
    assert d["nepotpuno"] == ["nazivi predmeta"]
    assert "ukupno_rsd" in d


def test_m2_B_cist_slucaj_nema_objave():
    fn = billing.billing_dugovanja.__wrapped__
    with patch.object(billing, "_get_supa", return_value=_supa_billing()):
        d = asyncio.run(fn(request=MagicMock(), user=KORISNIK))
    assert d["nepotpuno"] == [] and d["ukupno_rsd"] == 0


def test_m2_G_nijedan_tihi_fallback_nije_ostao():
    src = io.open("routers/billing.py", encoding="utf-8").read()
    assert "if not isinstance(" not in src, "stari tihi fallback jos postoji"
    assert src.count("_mora(") >= 7 and src.count("_dopuna(") >= 3


def test_m2_H_ugovor_je_identican_kanonskom():
    import routers.billing_reports as br
    for ime in ("_mora", "_dopuna"):
        assert hasattr(billing, ime) and hasattr(br, ime)


# ═══════════════════════════════════════════════════════════════════════════
# M1 — workspace.py + dashboard.py
# ═══════════════════════════════════════════════════════════════════════════

def _supa_prolaz(puca=None, redovi=None):
    puca = puca or set()
    redovi = redovi or {}
    m = MagicMock()

    def _table(ime):
        t = MagicMock()
        if ime in puca:
            def boom(*a, **k):
                raise KVAROVI["42703_kolona"]
            t.select.side_effect = boom
        else:
            def _rec():
                r = MagicMock()
                r.data = redovi.get(ime, [])
                return r
            t.select.return_value = _Prolaz(_rec)
        return t

    m.table.side_effect = _table
    return m


PREDMET_RED = [{"id": "p-1", "naziv": "Spor 1/2026"}]


def _ws(puca=None, redovi=None):
    #  mora vratiti bar jedan red, inace  ostane prazan
    # i podupiti se NIKAD ne izvrse — tada test ne bi merio nista.
    redovi = redovi if redovi is not None else {"predmeti": PREDMET_RED}
    with patch.object(workspace, "_get_supa", return_value=_supa_prolaz(puca, redovi)):
        return asyncio.run(getattr(workspace.get_workspace, "__wrapped__", workspace.get_workspace)(request=MagicMock(), user=KORISNIK))


def test_m1_A_cisto_prazno_ostaje_cisto_prazno():
    d = _ws(redovi={})
    assert d["degradirani_izvori"] == []
    assert d["provera_potpuna"] is True
    assert d["ukupno_aktivnih"] == 0


@pytest.mark.parametrize("izvor,ocekivano", [
    ("predmeti", "predmeti"),
    ("case_actions", "otvorene akcije"),
    ("zadaci", "zadaci na čekanju"),
    ("intake_jobs", "stavke za pregled"),
])
def test_m1_C_pad_jednog_izvora_se_objavljuje(izvor, ocekivano):
    """Meri se IME izvora, ne samo da je lista neprazna.

    Slabija verzija ovog testa (`assert d["degradirani_izvori"]`) prestala je
    da bude nosiva onog trenutka kad je dodat drugi guard nad istom tabelom:
    `case_actions` pada i u `_fetch_recently_completed`, pa bi lista bila
    neprazna čak i da je guard u glavnom gather-u uklonjen.
    """
    d = _ws(puca={izvor})
    assert ocekivano in d["degradirani_izvori"], \
        "pad izvora %s nije objavljen kao %r (dobijeno %r)" % (izvor, ocekivano, d["degradirani_izvori"])
    assert d["provera_potpuna"] is False


def test_m1_D_timeout_na_svemu_nije_cisto():
    """Doslovan pre-state A-001: timeout je davao HTTP 200 + nula objave."""
    async def _tajmaut(coro, timeout=None):
        if asyncio.iscoroutine(coro):
            coro.close()
        raise asyncio.TimeoutError()

    with patch.object(workspace, "_get_supa", return_value=_supa_prolaz()), \
         patch.object(qt.asyncio, "wait_for", _tajmaut):
        d = asyncio.run(getattr(workspace.get_workspace, "__wrapped__", workspace.get_workspace)(request=MagicMock(), user=KORISNIK))
    assert d["ukupno_aktivnih"] == 0
    assert d["provera_potpuna"] is False, "timeout je i dalje predstavljen kao potpuna provera"
    assert d["degradirani_izvori"], "nijedan izvor nije imenovan"


def test_m1_E_parcijalni_pad_nije_potpun():
    d = _ws(puca={"case_actions"})
    assert d["provera_potpuna"] is False
    assert "predmeti" not in d["degradirani_izvori"], "izvor koji je procitan ne sme biti prijavljen"


def test_m1_F_zavrsene_stavke_takodje_prijavljuju_pad():
    """`_fetch_recently_completed` je bio poslednji tihi gutač u ovoj ruti:
    korpa „Završeno nedavno" bi bila lažno prazna, a `provera_potpuna` bi
    tvrdio `True` — dakle sam signal potpunosti bi bio netačan."""
    d = _ws(puca={"case_actions"})
    assert "završene akcije" in d["degradirani_izvori"], d["degradirani_izvori"]
    assert d["provera_potpuna"] is False


def test_m1_G_odgovor_pri_padu_nije_isti_kao_prazno():
    assert _ws(puca={"case_actions"}) != _ws()


def test_m1_dashboard_objavljuje_pad():
    with patch.object(dashboard, "_get_supa", return_value=_supa_prolaz(puca={"fakture"})):
        d = asyncio.run(getattr(dashboard.command_center, "__wrapped__", dashboard.command_center)(request=MagicMock(), user=KORISNIK))
    assert d["provera_potpuna"] is False
    assert "fakture" in d["degradirani_izvori"]


def test_m1_dashboard_cisto_prazno():
    with patch.object(dashboard, "_get_supa", return_value=_supa_prolaz()):
        d = asyncio.run(getattr(dashboard.command_center, "__wrapped__", dashboard.command_center)(request=MagicMock(), user=KORISNIK))
    assert d["degradirani_izvori"] == [] and d["provera_potpuna"] is True
