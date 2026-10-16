# -*- coding: utf-8 -*-
"""TENFRONTS-M09 (KEYSTONE-006) — istek čekanja na pozadinsko osvežavanje Genome-a nije uspeh ni „ništa“.

Stvarna `_genomeBackgroundWatch` iz static/vindex.js izvršava se u Node-u: `setInterval` i `fetch` su lažni,
otkucaji se okidaju ručno. Pre ispravke: posle 6 × 15 s bez nove verzije hint se vraćao na podrazumevani
„Obično traje 15–20 sekundi…“ — ishod koji nije potvrđen izgledao je kao obično stanje."""
import json
import os
import shutil
import subprocess

import pytest

KOREN = os.path.join(os.path.dirname(__file__), "..")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node nije dostupan")
PODRAZUMEVANO = "Obično traje 15–20 sekundi — AI čita sve dokumente predmeta."


def _izvor():
    src = open(os.path.join(KOREN, "static", "vindex.js"), encoding="utf-8").read()
    i = src.index("var _genomeBgWatchTimer = null;")
    j = src.index("\n// Program Phoenix, Mission 013", i)
    return src[i:j]


SKRIPTA = r"""
const scenario = JSON.parse(process.argv[1]);
const hint = {textContent: 'početno'};
const document = { getElementById: (id) => id === 'case-dna-refresh-hint' ? hint : null };
var currentSession = {access_token: 't'}, BASE_URL = '', activePredmetId = 'P1';
let tik = null, ugaseno = false;
function setInterval(fn) { tik = fn; return 1; }
function clearInterval() { ugaseno = true; }
const pozivi = []; let render = 0;
async function fetch(url, opts) {
  pozivi.push({url, metod: (opts && opts.method) || 'GET'});
  if (scenario.mreza_puca) throw new Error('net');
  return {ok: true, json: async () => ({case_dna: {verzija: scenario.nova_od && pozivi.length >= scenario.nova_od ? 2 : 1}})};
}
function _caseDnaRender() { render++; }
%IZVOR%
(async () => {
  _genomeBackgroundWatch('P1', 1);
  const tokom = hint.textContent;
  for (let i = 0; i < 8 && !ugaseno; i++) {
    if (scenario.promena_predmeta_na === i) activePredmetId = 'P2';
    await tik();
  }
  console.log(JSON.stringify({tokom, kraj: hint.textContent, pozivi, render, ugaseno}));
})();
"""


def _pokreni(**scenario):
    r = subprocess.run([NODE, "-e", SKRIPTA.replace("%IZVOR%", _izvor()), json.dumps(scenario)],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_nova_verzija_zavrseno_i_prikazano():
    s = _pokreni(nova_od=2)
    assert s["render"] == 1 and s["kraj"] == PODRAZUMEVANO and s["ugaseno"]


def test_istek_bez_nove_verzije_nije_podrazumevano_stanje():
    s = _pokreni()
    assert len(s["pozivi"]) == 6 and s["ugaseno"] and s["render"] == 0
    assert s["kraj"] != PODRAZUMEVANO, "istek izgleda kao obično stanje"
    assert "nije potvrđen" in s["kraj"] and "u toku" in s["kraj"]


def test_istek_kada_mreza_puca_isto_nepotvrdjeno():
    s = _pokreni(mreza_puca=True)
    assert s["kraj"] != PODRAZUMEVANO and "nije potvrđen" in s["kraj"]


def test_istek_ne_pokrece_novo_osvezavanje():
    s = _pokreni()
    assert all(p["metod"] == "GET" and p["url"].endswith("/case-dna") for p in s["pozivi"])


def test_promena_predmeta_ne_prenosi_poruku_prethodnog_predmeta():
    s = _pokreni(promena_predmeta_na=2)
    assert s["kraj"] == PODRAZUMEVANO and s["render"] == 0 and len(s["pozivi"]) == 2


def test_tokom_cekanja_kaze_da_je_u_toku():
    assert "u toku" in _pokreni(nova_od=2)["tokom"]
