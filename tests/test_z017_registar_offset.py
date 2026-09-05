# -*- coding: utf-8 -*-
"""
Z017 §14 — OFFSET IZA KRAJA REGISTRA JE PRAZNA STRANA, NE 500.

Sta ovaj test cuva, a sto se iz koda ne vidi:

  PostgREST na `range(offset, ...)` gde je `offset` iza poslednjeg reda ne
  vraca praznu listu nego gresku `PGRST103 — Requested range not satisfiable`.
  supabase-py je dize kao `APIError`, pa je cela ruta `/api/predmeti` padala
  u HTTP 500. Mereno uzivo pre popravke na nalogu sa 20 predmeta:

      offset=0     -> 200, 20 redova
      offset=20    -> 200, 0 redova      (granicu PostgREST podnosi)
      offset=500   -> 500 Interna greska
      offset=100000-> 500 Interna greska

  To nije teorijski slucaj: dovoljno je da advokat obelezi vezu na stranu 3,
  pa obrise predmete — sledeci put registar ne prikaze „nema vise redova"
  nego se srusi. Isto vazi za rucno otkucan `offset` i za stranicenje koje
  se nastavi posle promene filtera.

  Ispravno ponasanje: prazna strana SA TACNIM `ukupno`, da klijent moze da
  se vrati na poslednju postojecu stranu umesto da izgubi ceo registar.

  Test namerno NE ide na mrezu — lazni klijent reprodukuje tacno onaj oblik
  greske koji je izmeren uzivo (`code == "PGRST103"`), i dokazuje da se
  svaka DRUGA greska i dalje propagira (tiho gutanje kvarova je gore od 500).

  ISTA KLASA POSTOJI NA DVA MESTA. Prvo prebrojavanje je obuhvatalo samo
  `api.py`, `routers/`, `services/` i `shared/` i naslo je jedno mesto; drugo,
  nad celim repozitorijumom, naslo je i `klijenti/router.py`. Zato pravilo
  sada zivi u `shared/stranicenje.py`, a `test_nijedan_range_nije_nezasticen`
  cuva da se trece mesto ne pojavi neprimeceno.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import api  # noqa: E402

UKUPNO = 20


class _GreskaOpsega(Exception):
    """Oblik koji supabase-py stvarno dize (mereno uzivo)."""
    code = "PGRST103"
    message = "Requested range not satisfiable"


class _DrugaGreska(Exception):
    code = "PGRST301"
    message = "JWT expired"


class _Upit:
    def __init__(self, tabela, greska):
        self.tabela = tabela
        self._greska = greska
        self.pozvan_limit = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def order(self, *a, **k): return self

    def range(self, poc, kraj):
        self._poc = poc
        return self

    def limit(self, n):
        self.pozvan_limit = n
        self._poc = None
        return self

    def execute(self):
        if self._poc is not None and self._poc >= UKUPNO:
            raise self._greska()
        redovi = [{"id": "p%d" % i, "naziv": "Predmet %d" % i}
                  for i in range(min(UKUPNO, 5))]
        return SimpleNamespace(data=(redovi if self._poc is not None else []),
                               count=UKUPNO)


class _Supa:
    def __init__(self, greska=_GreskaOpsega):
        self.greska = greska
        self.upiti = []

    def table(self, ime):
        u = _Upit(ime, self.greska)
        self.upiti.append(u)
        return u


def _ruta():
    r = api.lista_predmeta
    while hasattr(r, "__wrapped__"):
        r = r.__wrapped__
    return r


def _pozovi(supa, **kw):
    async def _auth(_a):
        return SimpleNamespace(id="u1", email="test@test.com")

    with patch.object(api, "_require_auth_async", _auth), \
         patch.object(api, "_get_supa", lambda: supa):
        return asyncio.run(_ruta()(SimpleNamespace(), "Bearer t", **kw))


def test_offset_iza_kraja_vraca_praznu_stranu_a_ne_500():
    supa = _Supa()
    odg = _pozovi(supa, limit=20, offset=500, view="summary")
    assert odg["predmeti"] == []
    assert odg["offset"] == 500


def test_prazna_strana_i_dalje_nosi_tacan_ukupno():
    """
    Bez tacnog `ukupno` klijent ne zna gde je poslednja postojeca strana i
    nema se cime vratiti — prazan registar bi izgledao kao registar bez
    predmeta, sto je pogresna tvrdnja o podacima.
    """
    odg = _pozovi(_Supa(), limit=20, offset=100000, view="summary")
    assert odg["ukupno"] == UKUPNO


def test_strana_u_opsegu_nije_pogodjena():
    odg = _pozovi(_Supa(), limit=20, offset=0, view="summary")
    assert len(odg["predmeti"]) > 0
    assert odg["ukupno"] == UKUPNO


def test_druga_greska_se_NE_guta():
    """
    Popravka sme da proguta tacno jedan uzrok. Da hvata svaki izuzetak,
    pokvaren upit ili istekao token bi se korisniku prikazao kao „registar
    je prazan" — tiha laz umesto glasnog kvara.
    """
    with pytest.raises(_DrugaGreska):
        _pozovi(_Supa(greska=_DrugaGreska), limit=20, offset=500, view="summary")


def test_prebrojavanje_se_radi_tek_kad_opseg_padne():
    """Dodatni upit je cena SAMO retkog slucaja, ne svakog listanja."""
    u_opsegu = _Supa()
    _pozovi(u_opsegu, limit=20, offset=0, view="summary")
    assert len(u_opsegu.upiti) == 1

    van_opsega = _Supa()
    _pozovi(van_opsega, limit=20, offset=500, view="summary")
    assert len(van_opsega.upiti) == 2
    assert van_opsega.upiti[1].pozvan_limit == 1


def test_filter_ostaje_primenjen_i_na_praznoj_strani():
    """
    `ukupno` na praznoj strani mora biti broj redova KOJI ODGOVARAJU FILTERU,
    ne broj svih predmeta. Mereno uzivo: `q=kalibracija&offset=999` daje
    ukupno=13, dok neregulisani registar ima 20.
    """
    supa = _Supa()
    _pozovi(supa, limit=20, offset=999, q="kalibracija", status="aktivan")
    assert len(supa.upiti) == 2, "prebrojavanje mora ici kroz isti skup filtera"


# ═══════════════════════════════════════════════════════════════════════════
# Klasa, ne pojedinacan slucaj
# ═══════════════════════════════════════════════════════════════════════════

def test_nijedan_range_nije_nezasticen():
    """
    Svako `.range(offset, ...)` u proizvodnom kodu mora ici kroz
    `strana_ili_prazna`. Novo mesto koje to zaobidje vraca istu 500 gresku,
    a otkrilo bi se tek na offsetu koji niko ne kuca u razvoju.
    """
    import pathlib
    koren = pathlib.Path(__file__).resolve().parent.parent
    preskoci = {"tests", ".git", "node_modules", "venv", ".venv", "v2"}
    nezasticeni = []
    for put in koren.rglob("*.py"):
        if any(d in preskoci for d in put.relative_to(koren).parts):
            continue
        try:
            tekst = put.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if ".range(" not in tekst:
            continue
        if "strana_ili_prazna" in tekst or put.name == "stranicenje.py":
            continue
        nezasticeni.append(str(put.relative_to(koren)))
    assert not nezasticeni, (
        "Ova mesta stranice bez zastite od offseta iza kraja: %s" % nezasticeni)


def test_zajednicki_pomocnik_propusta_druge_greske():
    from shared.stranicenje import strana_ili_prazna

    class _Drugo(Exception):
        code = "PGRST301"

    def _pao():
        raise _Drugo()

    with pytest.raises(_Drugo):
        strana_ili_prazna(_pao, lambda: SimpleNamespace(count=7))


def test_zajednicki_pomocnik_prebrojava_tek_na_padu():
    from shared.stranicenje import strana_ili_prazna
    brojac = {"n": 0}

    def _prebroj():
        brojac["n"] += 1
        return SimpleNamespace(count=42)

    ok = strana_ili_prazna(lambda: SimpleNamespace(data=[1], count=1), _prebroj)
    assert ok.data == [1] and brojac["n"] == 0

    class _VanOpsega(Exception):
        code = "PGRST103"

    def _pao():
        raise _VanOpsega()

    prazna = strana_ili_prazna(_pao, _prebroj)
    assert prazna.data == [] and prazna.count == 42 and brojac["n"] == 1
