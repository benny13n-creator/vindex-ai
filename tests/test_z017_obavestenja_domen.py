# -*- coding: utf-8 -*-
"""
Z017.17 — OBAVESTENJA (H7) i PLAN (H9), domen.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. PRAZAN SPISAK NIJE ISTO STO I NEPROCITAN SPISAK.
     `/notifications` na gresku vraca 200 sa praznim nizom — to je do sada
     bila TVRDNJA da obavestenja nema, nastala iz pale pretrage. Zastavica
     `procitano_uspesno` mora biti IZRICITO `true`; odsutna (stariji server)
     znaci „ne znam". `test_neuspesno_citanje_nije_prazan_spisak`.

  2. GRUPA NOSI SVE SVOJE ID-JEVE.
     Backend spaja vise obavestenja istog tipa u jedan red uz `ids`.
     Oznaciti procitanim samo predstavnika ostavilo bi ostale neprocitane, a
     spisak bi IZGLEDAO procitano jer se ponovo skuplja u istog predstavnika
     (F21). `test_grupa_salje_sve_id_jeve`.

  3. `procitano` MORA BITI IZRICITO `true`.
     Odsutno polje nije dokaz da je obavestenje procitano — fail-closed.
     `test_odsutno_procitano_je_neprocitano`.

  4. VAZNIJE PRVO, PA NAJNOVIJE.
     `test_redosled_po_prioritetu_pa_vremenu`.

  5. ISTEKLA PRETPLATA NIJE „VAZI DO".
     Datum u proslosti prikazan kao rok koji tece je tvrdnja koja ne stoji.
     `test_prosli_datum_je_istekao`.

  6. GRANICA KOJA NIJE OBJAVLJENA NIJE „NEOGRANICENO".
     `dnevni_limit: null` znaci da granica nije poslata, ne da je nema.
     `test_odsutna_granica_ostaje_null`.
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(modul: str, telo: str):
    skripta = textwrap.dedent(f"""
        import * as M from "file:///{V2}/domain/{modul}.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _o(telo):
    return _js("obavestenja", telo)


def _k(telo):
    return _js("kancelarija", telo)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


GRUPA = {"id": "n1", "ids": ["n1", "n2", "n3"], "count": 3, "tip": "rok_7d",
         "naslov": "3 × Rok za 7 dana", "poruka": "Tri roka",
         "prioritet": "high", "procitano": False,
         "created_at": "2026-09-05T10:00:00+00:00"}
POJEDINACNO = {"id": "n9", "tip": "neaktivnost", "naslov": "Predmet bez aktivnosti",
               "poruka": "30 dana", "prioritet": "low", "procitano": False,
               "predmet_id": "p1", "created_at": "2026-09-04T10:00:00+00:00"}


# ── 1. Prazno vs neprocitano ─────────────────────────────────────────────────
@nodemark
def test_uspesno_citanje_praznog_spiska():
    r = _o('return M.uObavestenja({ notifications: [], ukupno: 0, '
           "procitano_uspesno: true });")
    assert r["procitanoUspesno"] is True
    assert r["svi"] == []


@nodemark
def test_neuspesno_citanje_nije_prazan_spisak():
    """Prazan niz uz 200 iz pale pretrage NE SME da znaci „nema obaveštenja"."""
    r = _o('return M.uObavestenja({ notifications: [], ukupno: 0, '
           "procitano_uspesno: false });")
    assert r["procitanoUspesno"] is False


@nodemark
def test_odsutna_zastavica_je_neuspesno():
    """Stariji server ne salje polje — „ne znam" nije „uspelo je"."""
    r = _o("return M.uObavestenja({ notifications: [], ukupno: 0 });")
    assert r["procitanoUspesno"] is False


@nodemark
def test_string_true_nije_uspesno():
    r = _o('return M.uObavestenja({ notifications: [], '
           'procitano_uspesno: "true" });')
    assert r["procitanoUspesno"] is False


# ── 2. Grupa ─────────────────────────────────────────────────────────────────
@nodemark
def test_grupa_nosi_sve_id_jeve():
    r = _o(f"return M.uObavestenje({_j(GRUPA)});")
    assert r["ids"] == ["n1", "n2", "n3"], r


@nodemark
def test_pojedinacno_nosi_svoj_id():
    r = _o(f"return M.uObavestenje({_j(POJEDINACNO)});")
    assert r["ids"] == ["n9"], r


@nodemark
def test_grupa_salje_sve_id_jeve():
    """F21: oznaciti samo predstavnika ostavilo bi ostale neprocitane."""
    r = _o(f"const d = M.uObavestenja({{ notifications: [{_j(GRUPA)}, "
           f"{_j(POJEDINACNO)}], procitano_uspesno: true }});"
           "return M.idZaOznacavanje(d.neprocitani);")
    assert set(r) == {"n1", "n2", "n3", "n9"}, r


@nodemark
def test_procitana_se_ne_oznacavaju_ponovo():
    """Poziva se nad CELIM spiskom, ne nad vec filtriranim: `idZaOznacavanje`
    mora i sama da preskoci procitana, jer je izvezena i moze se pozvati
    bilo gde."""
    r = _o(f"const d = M.uObavestenja({{ notifications: "
           f"[{_j(dict(GRUPA, procitano=True))}, {_j(POJEDINACNO)}], "
           "procitano_uspesno: true });"
           "return M.idZaOznacavanje(d.svi);")
    assert r == ["n9"], r


@nodemark
def test_oznacavanje_nad_neprocitanima_daje_isto():
    r = _o(f"const d = M.uObavestenja({{ notifications: "
           f"[{_j(dict(GRUPA, procitano=True))}, {_j(POJEDINACNO)}], "
           "procitano_uspesno: true });"
           "return M.idZaOznacavanje(d.neprocitani);")
    assert r == ["n9"], r


# ── 3. `procitano` izricito ──────────────────────────────────────────────────
@nodemark
def test_odsutno_procitano_je_neprocitano():
    o = dict(GRUPA)
    o.pop("procitano")
    assert _o(f"return M.uObavestenje({_j(o)});")["procitano"] is False


@nodemark
def test_string_true_procitano_je_neprocitano():
    assert _o('return M.uObavestenje({ id: "x", naslov: "N", '
              'procitano: "true" });')["procitano"] is False


# ── 4. Redosled ──────────────────────────────────────────────────────────────
@nodemark
def test_redosled_po_prioritetu_pa_vremenu():
    stari_high = dict(GRUPA, id="a", ids=["a"],
                      created_at="2026-01-01T00:00:00+00:00")
    novi_low = dict(POJEDINACNO, id="b", prioritet="low",
                    created_at="2026-09-06T00:00:00+00:00")
    r = _o(f"return M.uObavestenja({{ notifications: [{_j(novi_low)}, "
           f"{_j(stari_high)}], procitano_uspesno: true }}).svi.map(x => x.id);")
    assert r == ["a", "b"], r


@nodemark
def test_isti_prioritet_najnovije_prvo():
    a = dict(POJEDINACNO, id="a", created_at="2026-09-01T00:00:00+00:00")
    b = dict(POJEDINACNO, id="b", created_at="2026-09-05T00:00:00+00:00")
    r = _o(f"return M.uObavestenja({{ notifications: [{_j(a)}, {_j(b)}], "
           "procitano_uspesno: true }).svi.map(x => x.id);")
    assert r == ["b", "a"], r


@nodemark
def test_prazno_obavestenje_se_izostavlja():
    r = _o('return M.uObavestenja({ notifications: [{ id: "x" }, '
           '{ id: "y", naslov: "Pravo" }], procitano_uspesno: true }).svi.length;')
    assert r == 1


# ── 5. Plan (H9) ─────────────────────────────────────────────────────────────
PLAN = {"plan": "basic", "plan_display": "Basic", "addons": [],
        "subscription_expires_at": "2027-08-13T14:35:30Z",
        "subscription_seats_extra": 0, "credits_remaining": 9999,
        "year_month": "2026-09",
        "usage_this_month": [{"feature_key": "confidence_audit",
                              "naziv": "AI Pouzdanost", "broj_koriscenja": 28,
                              "krediti_potroseni": 0.0, "dnevni_limit": None,
                              "mesecni_limit": None}]}


@nodemark
def test_buduci_datum_nije_istekao():
    r = _k(f"return M.uPlan({_j(PLAN)});")
    assert r["isteklo"] is False, r["isteklo"]
    assert r["istice"] == "2027-08-13"


@nodemark
def test_prosli_datum_je_istekao():
    """„Pretplata važi do" nad prošlim datumom je tvrdnja koja ne stoji."""
    r = _k(f"return M.uPlan({_j(dict(PLAN, subscription_expires_at='2020-01-01T00:00:00Z'))});")
    assert r["isteklo"] is True


@nodemark
def test_neprepoznat_datum_ne_tvrdi_nista():
    r = _k(f"return M.uPlan({_j(dict(PLAN, subscription_expires_at='nekad'))});")
    assert r["isteklo"] is None, r["isteklo"]


# ── 6. Granice ───────────────────────────────────────────────────────────────
@nodemark
def test_odsutna_granica_ostaje_null():
    """`null` znaci „granica nije objavljena", ne „neograniceno"."""
    r = _k(f"return M.uPlan({_j(PLAN)});")
    u = r["potrosnja"][0]
    assert u["dnevniLimit"] is None and u["mesecniLimit"] is None
    assert u["koriscenja"] == 28


@nodemark
def test_prazan_plan_ne_ruši():
    r = _k("return M.uPlan(null);")
    assert r["potrosnja"] == [] and r["dodaci"] == []
    assert r["krediti"] is None


# ═══════════════════════════════════════════════════════════════════════════
# BACKEND: pala pretraga NE SME da se predstavi kao „nema obaveštenja"
#
# PRE-STATE: `/notifications` je na svaki izuzetak vraćao
#     {"notifications": [], "ukupno": 0, "neprocitane": 0}
# uz status 200. Klijent nije imao nijedan način da razlikuje „nema
# obaveštenja" od „čitanje nije uspelo", pa je pala pretraga izgledala kao
# uredan prazan spisak. Ista klasa lažne tvrdnje kao N5 i B-U-001.
#
# Odgovor je zadržan (postojeći potrošači ne smeju da puknu), ali sada nosi
# `procitano_uspesno`, koje V2 traži IZRIČITO kao `true`.
# ═══════════════════════════════════════════════════════════════════════════
import asyncio
from unittest.mock import MagicMock, patch


def _lazni_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/notifications",
                    "headers": [], "query_string": b"",
                    "client": ("127.0.0.1", 0), "server": ("testserver", 80),
                    "scheme": "http", "root_path": "", "app": None})


def _pozovi(supa):
    import routers.notifications as N
    with patch.object(N, "_get_supa", return_value=supa):
        return asyncio.run(N.get_notifications(
            request=_lazni_request(), user={"user_id": "u1"},
            samo_neprocitane=False))


def test_uspesno_citanje_nosi_zastavicu():
    supa = MagicMock()
    lanac = MagicMock()
    lanac.execute.return_value = MagicMock(data=[])
    for m in ("select", "eq", "order", "limit"):
        getattr(lanac, m).return_value = lanac
    supa.table.return_value = lanac
    r = _pozovi(supa)
    assert r["procitano_uspesno"] is True, r


def test_pala_pretraga_ne_tvrdi_da_obavestenja_nema():
    """Prazan spisak uz 200 mora NOSITI podatak da čitanje nije uspelo."""
    supa = MagicMock()
    supa.table.side_effect = RuntimeError("veza pukla")
    r = _pozovi(supa)
    assert r["notifications"] == []
    assert r["procitano_uspesno"] is False, r
