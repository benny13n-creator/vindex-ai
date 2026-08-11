# -*- coding: utf-8 -*-
"""
Wave 9 (§7) — concurrency guard nad DRUGOM naplativom frontend putanjom.

ŠTA JE WAVE 8 ZATVORIO, A ŠTA NIJE

Wave 8 je dokazao da `stratOrkestratorPokreni` ima jedan guard (`_stratOrkUToku`)
koji važi za svih pet ulaznih tačaka kompletne analize. Ostala je druga
naplativa putanja: `stratPokreni` pokreće svih 8 pojedinačnih modula
(red_team, litigation, sudija, due_diligence, revizor, witness, sudija_v2,
court_predictor) i naplaćuje 1-2 kredita po pozivu.

Njena jedina odbrana je bila `submitBtn.disabled`. Mandat §7 to izričito
odbija: „Ne oslanjaj se samo na button.disabled."

ZAŠTO `disabled` NIJE GUARD

`disabled` je svojstvo DUGMETA. Štiti samo dok je klik jedini put do funkcije.
Wave 8 je izmerio tačno taj razred greške na orkestratoru: dugme je bilo
zaključano, a četiri druga ulaza su ga zaobilazila. Guard koji živi u funkciji
važi i za ulaz koji još ne postoji.

METOD

Repo nema JS test framework. Funkcija se STVARNO IZVRŠAVA u Node-u sa minimalnim
DOM stubom, pa se broje stvarni `fetch` pozivi — meri se ponašanje, ne prisustvo
stringa u izvoru.
"""
import json
import os
import re
import subprocess

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VINDEX = os.path.join(_KOREN, "static", "vindex.js")


def _node_dostupan() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _izvuci_funkciju() -> str:
    """Izvor `stratPokreni` + deklaraciju zastavice iznad nje."""
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(
        r"(var _stratModulUToku = false;\s*\n\s*async function stratPokreni\(\)\s*\{.*?\n\})",
        js, re.S,
    )
    assert m, "`_stratModulUToku` ili `stratPokreni` nisu pronađeni u static/vindex.js"
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
var _stratAktivniModul = "red_team";
var STRAT_MODULI = { red_team: { naziv: "Analiza crvenog tima",
                                 endpoint: "/strategija/red-team", min: 50 } };
function openModal() {}
function showToast(m, t) { _pozivi.toast.push(String(m)); }
function piTrack() {}
function _htmlEsc(s) { return s; }
function _friendlyErr(e) { return String(e); }
function stratFormatirajRezultat() { return ""; }
function strat_job_poll() { return new Promise(function(r){ setTimeout(r, 40); }); }

// Provajder: broji pozive i traje 30ms, da druga invokacija stigne u letu.
function fetch(url, opts) {
  _pozivi.fetch += 1;
  return new Promise(function(res) {
    setTimeout(function() {
      res({ status: 200, ok: true, json: function() { return Promise.resolve({ rezultat: "x" }); } });
    }, 30);
  });
}

__FUNKCIJA__

var polje = _el("strat-tekst");
polje.value = "x".repeat(200);

__SCENARIO__
"""


def _pokreni(scenario: str) -> dict:
    kod = (_HARNESS
           .replace("__FUNKCIJA__", _izvuci_funkciju())
           .replace("__SCENARIO__", scenario))
    # `encoding="utf-8"` je obavezan: na Windows-u `text=True` podrazumeva cp1252,
    # a izvučena funkcija nosi srpska slova iz svojih komentara.
    r = subprocess.run(
        ["node", "-e", kod], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")


# ─── 1. DVOSTRUKO POKRETANJE ────────────────────────────────────────────────

def test_a_drugi_poziv_u_letu_ne_salje_drugi_zahtev():
    """Srž: dva poziva bez čekanja daju TAČNO JEDAN zahtev."""
    r = _pokreni("""
      stratPokreni();
      stratPokreni();
      setTimeout(function() {
        console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
      }, 200);
    """)
    assert r["fetch"] == 1, (
        f"dva poziva su poslala {r['fetch']} zahteva — svaki je zaseban naplativ "
        f"AI modul (1-2 kredita)"
    )
    assert any("već u toku" in t for t in r["toast"]), (
        "drugi poziv je tiho odbačen — korisnik ne zna zašto se ništa nije desilo"
    )


def test_b_cetiri_brza_poziva_daju_jedan_zahtev():
    r = _pokreni("""
      for (var i = 0; i < 4; i++) stratPokreni();
      setTimeout(function() {
        console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
      }, 200);
    """)
    assert r["fetch"] == 1, f"četiri poziva -> {r['fetch']} zahteva"


# ─── 2. ZASTAVICA SE OSLOBAĐA ───────────────────────────────────────────────

def test_ng_posle_zavrsetka_nova_analiza_JE_moguca():
    """Negativna kontrola — i najvažniji test u fajlu.

    Bez nje bi `test_a` prolazio i da zastavica trajno zaključa funkciju posle
    prve upotrebe, što bi bio gori kvar od onog koji se rešava.
    """
    r = _pokreni("""
      stratPokreni();
      setTimeout(function() {
        stratPokreni();
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

    Da se oslobađa samo na uspehu, jedan mrežni pad bi trajno zaključao sve
    module do osvežavanja stranice.
    """
    r = _pokreni("""
      fetch = function() { return Promise.reject(new Error("mrežni pad")); };
      stratPokreni();
      setTimeout(function() {
        fetch = function() { _pozivi.fetch += 1; return new Promise(function(res){
          setTimeout(function(){ res({ status: 200, ok: true,
            json: function(){ return Promise.resolve({ rezultat: "x" }); } }); }, 20); }); };
        stratPokreni();
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
    """Zastavica se postavlja POSLE ranih `return` grana."""
    r = _pokreni("""
      _el("strat-tekst").value = "prekratko";
      stratPokreni();
      setTimeout(function() {
        _el("strat-tekst").value = "y".repeat(200);
        stratPokreni();
        setTimeout(function() {
          console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
        }, 200);
      }, 60);
    """)
    assert r["fetch"] == 1, (
        "odbijen pokušaj (prekratak tekst) je zaključao funkciju — zastavica se "
        "postavlja prerano"
    )


def test_e_nije_pro_ne_zakljucava_funkciju():
    """Druga rana grana: PRO kapija."""
    r = _pokreni("""
      currentUserIsPro = false;
      stratPokreni();
      setTimeout(function() {
        currentUserIsPro = true;
        stratPokreni();
        setTimeout(function() {
          console.log(JSON.stringify({ fetch: _pozivi.fetch, toast: _pozivi.toast }));
        }, 200);
      }, 60);
    """)
    assert r["fetch"] == 1, (
        "odbijen pokušaj (nije PRO) je zaključao funkciju za korisnika koji se u "
        "međuvremenu nadogradio"
    )
