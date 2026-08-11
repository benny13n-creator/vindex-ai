# -*- coding: utf-8 -*-
"""
Wave 8 — zaštita od dvostrukog pokretanja kompletne analize.

POZNAT NALAZ (Wave 2, frontend forenzika)

`#strat-ork-btn` se zaključava sa `disabled`, ali analiza ima još ČETIRI ulazne
tačke koje taj atribut ne diraju:

    index.html:782    „Quick action" kartica u predmetu
    index.html:1138   klikabilan `<div>` — BEZ IKAKVOG guard-a
    index.html:1596   dugme u pod-tabu AI Analiza
    vindex.js:13070   CMD-K paleta

Sve četiri idu kroz `pred_launchKompletnaAnaliza()` → `stratOrkestratorPokreni()`,
koja nikad nije proveravala `orkBtn.disabled` pre nego što krene. Sa njih su dva
paralelna posla bila moguća.

ZAŠTO DEDUPE NIJE BIO DOVOLJAN

`create_job_deduped` (`routers/jobs.py:60`) to hvata — ali je to POSLEDNJA
odbrana i radi samo unutar jednog worker procesa, što fajl na `:48-55` izričito
priznaje. Prva odbrana pripada mestu gde je klik nastao.

METOD

Repo nema JS test framework (`tests/test_iron_lawyer_frontend_fixes.py:5-10` to
dokumentuje). Umesto grep-a po izvoru, ovde se `stratOrkestratorPokreni`
STVARNO IZVRŠAVA u Node-u, sa minimalnim DOM stubom — pa se meri ponašanje, ne
prisustvo stringa.
"""
import json
import os
import re
import subprocess
import sys

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VINDEX = os.path.join(_KOREN, "static", "vindex.js")


def _node_dostupan() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _izvuci(ime: str) -> str:
    """Izvor jedne funkcije + deklaraciju zastavice iznad nje."""
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(
        r"(var _stratOrkUToku = false;\s*\n\s*async function "
        + re.escape(ime) + r"\(\)\s*\{.*?\n\})",
        js, re.S,
    )
    assert m, f"{ime} ili zastavica nisu pronađeni"
    return m.group(1)


_HARNESS = r"""
// Minimalni DOM/API stub -- samo ono što funkcija stvarno dodiruje.
var _pozivi = { fetch: 0, toast: [] };
var _elementi = {};
function _el(id) {
  if (!_elementi[id]) _elementi[id] = { id: id, value: "", dataset: {}, style: {},
                                        innerHTML: "", textContent: "", disabled: false,
                                        classList: { add: function(){}, remove: function(){} } };
  return _elementi[id];
}
var document = { getElementById: _el };
var BASE_URL = "http://test";
var currentUser = { id: "u1" };
var currentUserIsPro = true;
var currentSession = { access_token: "t" };
function openModal() {}
function showToast(m, t) { _pozivi.toast.push(String(m)); }
function piTrack() {}
function _htmlEsc(s) { return s; }
function _friendlyErr(e) { return String(e); }
function _strat6ModuliHtml() { return ""; }
function renderKompletnaAnaliza() { return ""; }
function stratFormatirajRezultat() { return ""; }
function strat_job_poll() { return new Promise(function(r){ setTimeout(r, 40); }); }

// Provajder: broji pozive i traje 30ms, da druga invokacija stigne u letu.
function fetch(url, opts) {
  _pozivi.fetch += 1;
  return new Promise(function(res) {
    setTimeout(function() {
      res({ status: 202, ok: true, json: function() { return Promise.resolve({ job_id: "abcdef123456" }); } });
    }, 30);
  });
}

__FUNKCIJA__

// Polje je popunjeno i vezano za predmet.
var polje = _el("strat-tekst");
polje.value = "x".repeat(200);
polje.dataset.predId = "pred-alfa";

__SCENARIO__
"""


def _pokreni(scenario: str) -> dict:
    kod = (_HARNESS
           .replace("__FUNKCIJA__", _izvuci("stratOrkestratorPokreni"))
           .replace("__SCENARIO__", scenario))
    # `encoding="utf-8"` je obavezan: na Windows-u `text=True` podrazumeva
    # cp1252, a izvučena funkcija nosi srpska slova iz svojih komentara.
    r = subprocess.run(
        ["node", "-e", kod], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")


# ─── 1. DVA UZASTOPNA KLIKA ─────────────────────────────────────────────────

def test_a_drugi_klik_u_letu_ne_pokrece_drugi_posao():
    """Srž nalaza: dva klika bez čekanja daju TAČNO JEDAN zahtev.

    Ne proverava da zastavica postoji — pokreće funkciju dvaput i broji stvarne
    `fetch` pozive.
    """
    r = _pokreni("""
      stratOrkestratorPokreni();
      stratOrkestratorPokreni();
      setTimeout(function() {
        console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
      }, 200);
    """)
    assert r["fetch"] == 1, (
        f"dva klika su pokrenula {r['fetch']} zahteva — sa klikabilnog `<div>`-a "
        f"(index.html:1138) i CMD-K to znači dva paralelna posla od po 8 GPT-4o poziva"
    )
    assert any("već u toku" in t for t in r["toast"]), (
        "drugi klik je tiho odbačen — korisnik ne zna zašto se ništa nije desilo"
    )


def test_b_cetiri_brza_klika_daju_jedan_zahtev():
    r = _pokreni("""
      for (var i = 0; i < 4; i++) stratOrkestratorPokreni();
      setTimeout(function() {
        console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
      }, 200);
    """)
    assert r["fetch"] == 1, f"četiri klika -> {r['fetch']} zahteva"


# ─── 2. ZASTAVICA SE OSLOBAĐA ───────────────────────────────────────────────

def test_ng_posle_zavrsetka_nova_analiza_JE_moguca():
    """Negativna kontrola — i najvažnija.

    Bez nje bi `test_a` prolazio i da zastavica trajno zaključa funkciju posle
    prve upotrebe, što bi bio gori kvar od onog koji se rešava.
    """
    r = _pokreni("""
      stratOrkestratorPokreni();
      setTimeout(function() {
        stratOrkestratorPokreni();
        setTimeout(function() {
          console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
        }, 200);
      }, 250);
    """)
    assert r["fetch"] == 2, (
        f"druga analiza posle završetka prve nije pokrenuta ({r['fetch']} zahteva) — "
        f"zastavica se ne oslobađa"
    )


def test_c_greska_oslobadja_zastavicu():
    """`finally`, ne kraj `try`.

    Da se oslobađa samo na uspehu, jedan neuspeh bi trajno zaključao funkciju do
    osvežavanja stranice.
    """
    r = _pokreni("""
      fetch = function() { return Promise.reject(new Error("mrežni pad")); };
      stratOrkestratorPokreni();
      setTimeout(function() {
        fetch = function() { _pozivi.fetch += 1; return new Promise(function(res){
          setTimeout(function(){ res({ status: 202, ok: true,
            json: function(){ return Promise.resolve({ job_id: "abcdef123456" }); } }); }, 20); }); };
        stratOrkestratorPokreni();
        setTimeout(function() {
          console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
        }, 200);
      }, 120);
    """)
    assert r["fetch"] == 1, (
        "posle greške nova analiza nije mogla da krene — zastavica nije "
        "oslobođena u `finally`"
    )


# ─── 3. RANE GRANE NE ZAKLJUČAVAJU ──────────────────────────────────────────

def test_d_prekratak_tekst_ne_zakljucava_funkciju():
    """Zastavica se postavlja POSLE ranih `return` grana.

    Da stoji na vrhu, odbijen pokušaj (prekratak tekst, nije PRO) zaključao bi
    dugme dok se stranica ne osveži.
    """
    r = _pokreni("""
      _el("strat-tekst").value = "prekratko";
      stratOrkestratorPokreni();
      setTimeout(function() {
        _el("strat-tekst").value = "y".repeat(200);
        _el("strat-tekst").dataset.predId = "pred-alfa";
        stratOrkestratorPokreni();
        setTimeout(function() {
          console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
        }, 200);
      }, 60);
    """)
    assert r["fetch"] == 1, (
        "odbijen pokušaj je zaključao funkciju — zastavica se postavlja prerano"
    )
