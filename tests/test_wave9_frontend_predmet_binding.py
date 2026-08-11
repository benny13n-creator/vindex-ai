# -*- coding: utf-8 -*-
"""
Wave 9 (§5) — `predmet_id` stvarno napušta pretraživač za svih 7 pojedinačnih
strategija modula.

ZAŠTO OVAJ FAJL POSTOJI ODVOJENO OD BACKEND TESTOVA

`tests/test_wave9_strategy_context.py` dokazuje da ruta prima `predmet_id`,
proverava vlasništvo i propušta kanonski kontekst do prompta. To je pola lanca.
Druga polovina je da ga frontend UOPŠTE POŠALJE — a to nijedan Python test ne
može da vidi, jer se dešava u pretraživaču.

Isti razred rupe je već jednom nađen na ovom projektu (P0-D2): backend je bio
ispravan mesecima, a `stratOrkestratorPokreni` polje nikad nije slao, pa je
kanonski kontekst bio mrtav kod na živoj putanji.

ODAKLE VREDNOST — I ZAŠTO NE `activePredmetId`

`_predAutoFill` upisuje `dataset.predId` na `#strat-tekst` kad polje popuni iz
predmeta. Taj atribut prati TEKST. `activePredmetId` prati UI izbor i menja se
čim advokat otvori drugi predmet — analiza pokrenuta nad tekstom predmeta A
završila bi vezana za predmet B.

METOD

`stratPokreni` se STVARNO IZVRŠAVA u Node-u; čita se telo `fetch` poziva.
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


def _izvuci() -> str:
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(
        r"(var _stratModulUToku = false;\s*\n\s*async function stratPokreni\(\)\s*\{.*?\n\})",
        js, re.S,
    )
    assert m, "`stratPokreni` nije pronađena u static/vindex.js"
    return m.group(1)


_HARNESS = r"""
var _zahtevi = [];
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
var activePredmetId = "AKTIVNI-PREDMET-IZ-UI";   // namerno RAZLIČIT od dataset.predId
var _stratAktivniModul = "__MODUL__";
var STRAT_MODULI = {
  red_team:      { naziv: "n", endpoint: "/strategija/red-team",      min: 50 },
  litigation:    { naziv: "n", endpoint: "/strategija/litigation",    min: 50 },
  sudija:        { naziv: "n", endpoint: "/strategija/sudija",        min: 50 },
  due_diligence: { naziv: "n", endpoint: "/strategija/due-diligence", min: 100 },
  revizor:       { naziv: "n", endpoint: "/strategija/revizor",       min: 100 },
  witness:       { naziv: "n", endpoint: "/strategija/witness",       min: 50 },
  sudija_v2:     { naziv: "n", endpoint: "/strategija/sudija-v2",     min: 100 },
  court_predictor: { naziv: "n", endpoint: "/api/predictor/analiza",  min: 80 }
};
function openModal() {}
function showToast() {}
function piTrack() {}
function _htmlEsc(s) { return s; }
function _friendlyErr(e) { return String(e); }
function _stratGreskaHtml() { return ""; }
function stratFormatirajRezultat() { return ""; }
function strat_job_poll() { return Promise.resolve(); }

function fetch(url, opts) {
  _zahtevi.push({ url: url, body: JSON.parse(opts.body) });
  return Promise.resolve({ status: 200, ok: true,
                           json: function(){ return Promise.resolve({ rezultat: "x" }); } });
}

__FUNKCIJA__

var polje = _el("strat-tekst");
polje.value = "x".repeat(300);
__PRIPREMA__

stratPokreni().then(function(){
  console.log(JSON.stringify(_zahtevi));
});
"""

_PRED_ID = "PREDMET-IZ-TEKSTA-9F3"


def _pokreni(modul: str, priprema: str) -> list:
    kod = (_HARNESS
           .replace("__FUNKCIJA__", _izvuci())
           .replace("__MODUL__", modul)
           .replace("__PRIPREMA__", priprema))
    r = subprocess.run(
        ["node", "-e", kod], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")

_SEDAM = ["red_team", "litigation", "sudija", "due_diligence",
          "revizor", "witness", "sudija_v2"]


# ─── 1. ID SE ŠALJE ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("modul", _SEDAM)
def test_a_predmet_id_se_salje_kad_je_tekst_iz_predmeta(modul):
    z = _pokreni(modul, f'polje.dataset.predId = "{_PRED_ID}";')
    assert len(z) == 1, f"očekivan tačno jedan zahtev, dobijeno {len(z)}"
    assert z[0]["body"].get("predmet_id") == _PRED_ID, (
        f"{modul}: `predmet_id` nije poslat — backend prima zahtev bez predmeta, "
        f"pa kanonski kontekst ostaje mrtav kod na živoj putanji (isti razred "
        f"rupe kao P0-D2)"
    )
    assert z[0]["body"].get("tekst"), "postojeće polje `tekst` je izgubljeno"


@pytest.mark.parametrize("modul", _SEDAM)
def test_b_bez_atributa_polje_se_NE_salje(modul):
    """Regresija starog ponašanja.

    `predmet_id` je opciono. Slanje `null` ili praznog stringa nije isto što i
    izostavljanje — prazan string bi na backendu prošao kroz `if req.predmet_id`
    kao lažan, ali bi svaka buduća normalizacija mogla da ga pretvori u 404.
    """
    z = _pokreni(modul, "")  # bez dataset.predId
    assert len(z) == 1
    assert "predmet_id" not in z[0]["body"], (
        f"{modul}: polje je poslato iako tekst nije iz predmeta"
    )


# ─── 2. VEZIVANJE PRATI TEKST, NE UI ────────────────────────────────────────

def test_c_ne_koristi_se_activePredmetId():
    """Najvažniji test u fajlu.

    `activePredmetId` je u harness-u namerno postavljen na DRUGU vrednost. Ako
    bi kod čitao njega, analiza bi se vezala za predmet koji je advokat otvorio
    u međuvremenu, iako je tekst iz prvog.
    """
    z = _pokreni("red_team", f'polje.dataset.predId = "{_PRED_ID}";')
    assert z[0]["body"]["predmet_id"] == _PRED_ID
    assert z[0]["body"]["predmet_id"] != "AKTIVNI-PREDMET-IZ-UI"


def test_ng_bez_atributa_a_sa_aktivnim_predmetom_i_dalje_ne_salje():
    """Negativna kontrola za `test_c`.

    Bez nje bi `test_c` prolazio i da kod čita `dataset.predId || activePredmetId`
    — u tom slučaju bi prvi test i dalje video ispravnu vrednost, a fallback na
    UI izbor bi ostao neprimećen.
    """
    z = _pokreni("red_team", "")
    assert "predmet_id" not in z[0]["body"], (
        "postoji tihi fallback na `activePredmetId` — vezivanje ne prati tekst"
    )


# ─── 3. COURT PREDICTOR JE NAMERNO IZUZET ───────────────────────────────────

def test_d_court_predictor_zadrzava_svoje_vezivanje():
    """Svesna razlika, ne previd.

    `court_predictor` ide na drugi ruter i `activePredmetId` mu je postavljen u
    PROGBETA-001 da bi readiness cap mogao da opali. Menjanje tog vezivanja
    diralo bi bezbednosnu granicu van obima ovog sprinta.

    Test je namerno POZITIVAN: tvrdi da vezivanje JESTE po `activePredmetId`.
    Ako ga neko ujednači sa ostalih sedam, ovo pada i tera ga da pročita razlog
    i proveri da cap i dalje radi.
    """
    z = _pokreni("court_predictor", f'polje.dataset.predId = "{_PRED_ID}";')
    assert z[0]["body"]["predmet_id"] == "AKTIVNI-PREDMET-IZ-UI", (
        "court_predictor je prebačen na `dataset.predId` — proveri da readiness "
        "cap (PROGBETA-001) i dalje opali pre nego što prepišeš ovaj test"
    )
