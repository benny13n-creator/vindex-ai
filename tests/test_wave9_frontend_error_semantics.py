# -*- coding: utf-8 -*-
"""
Wave 9 (§4) — poslovni neuspeh pozadinskog posla stiže advokatu kao poruka,
ne kao tehnički string.

ŠTA JE ZATVORENO

Wave 2 i Wave 6 su prijavili „402/429 degradiraju u generički error string".
Wave 7 je to IZMERIO i ocenu OSLABIO sa P1 na P2: informacija nikad nije
nestajala (`str(HTTPException(402, {...}))` čuva i kod i poruku), nego nije bila
strukturisana. Advokat bez kredita je usred kompletne analize video:

    Greška: 402: {'code': 'NO_CREDITS', 'message': '...'}

Wave 9 je `routers/jobs.py` naučio da uz `error` upiše i `error_status` (broj) i
`error_code` (mašinski kod). Ovaj fajl dokazuje da frontend te vrednosti
STVARNO koristi za odluku šta prikazati.

ZAŠTO GRANANJE PO BROJU, A NE PO TEKSTU

`j.error` je prezentacioni tekst, ne ugovor. Grananje po podnizu „402" opalilo
bi i na poruci koja slučajno sadrži tu cifru (iznos, broj člana, godina), i
puklo bi čim se poruka preformuliše ili prevede.

METOD

Repo nema JS test framework. `_stratGreskaHtml` se STVARNO IZVRŠAVA u Node-u —
meri se izlazni HTML, ne prisustvo stringa u izvoru.
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
    m = re.search(r"(function _stratGreskaHtml\(j\)\s*\{.*?\n\})", js, re.S)
    assert m, "`_stratGreskaHtml` nije pronađena u static/vindex.js"
    return m.group(1)


def _pokreni(ulazi: list) -> list:
    kod = (
        "function _htmlEsc(s){ return String(s).replace(/</g,'&lt;'); }\n"
        + _izvuci()
        + "\nvar _ul = " + json.dumps(ulazi) + ";\n"
        + "console.log(JSON.stringify(_ul.map(function(x){ return _stratGreskaHtml(x); })));"
    )
    r = subprocess.run(
        ["node", "-e", kod], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")


# ─── 1. SVAKI POSLOVNI KOD DOBIJA SVOJU PORUKU ──────────────────────────────

def test_a_402_daje_poruku_o_kreditima_a_ne_tehnicki_string():
    (html,) = _pokreni([{"error": "Potrebno 6 kredita, na raspolaganju 2.",
                         "error_status": 402, "error_code": "NO_CREDITS"}])
    assert "Nema dovoljno kredita" in html, (
        "402 se i dalje prikazuje kao tehnička greška — paywall poruka ne opali"
    )
    assert "Potrebno 6 kredita" in html, "poruka sa servera je izgubljena"
    assert "NIJE naplaćena" in html, (
        "nedostaje jedina informacija koja advokata stvarno zanima kad posao "
        "padne na naplati: da li mu je nešto skinuto"
    )


def test_b_429_i_403_i_404_imaju_svoje_poruke():
    poruke = _pokreni([
        {"error": "Previše zahteva.", "error_status": 429},
        {"error": "Potreban je viši paket.", "error_status": 403},
        {"error": "Predmet nije pronađen.", "error_status": 404},
    ])
    assert "Previše zahteva" in poruke[0]
    assert "strat-pro-gate" in poruke[1], "403 mora ići u tarifnu, ne u error kutiju"
    assert "Predmet nije pronađen" in poruke[2]

    # Tri različita ishoda moraju dati tri RAZLIČITA HTML-a. Bez ove tvrdnje bi
    # test prolazio i da sve tri grane vraćaju istu generičku kutiju.
    assert len(set(poruke)) == 3, "dve poslovne odluke se prikazuju identično"


# ─── 2. TEHNIČKI KVAR NE SME DA IZGLEDA KAO POSLOVNA ODLUKA ─────────────────

def test_c_500_ide_u_genericku_granu():
    (html,) = _pokreni([{"error": "Tehnička greška (TimeoutError).",
                         "error_status": 500}])
    assert "Nema dovoljno kredita" not in html, (
        "tehnički kvar je prikazan kao nedostatak kredita — paywall bi opalio "
        "na svaki pad provajdera"
    )
    assert "Greška:" in html and "Tehnička greška" in html


# ─── 3. FAIL-SAFE: STARIJI ZAPIS POSLA ──────────────────────────────────────

@pytest.mark.parametrize("ulaz", [
    {"error": "Nešto je puklo."},                      # nema error_status uopšte
    {"error": "Nešto je puklo.", "error_status": None},
    {"error": "Nešto je puklo.", "error_status": "402"},  # string, ne broj
    {},                                                  # potpuno prazan zapis
])
def test_d_nepoznat_ili_odsutan_status_pada_u_genericku_granu(ulaz):
    """Stariji zapis posla, drugi worker, starija verzija backend-a.

    Ključno: `"402"` kao STRING ne sme da aktivira kreditnu granu — inače bi
    grananje zavisilo od tipa koji nigde nije garantovan.
    """
    (html,) = _pokreni([ulaz])
    assert "strat-error" in html
    assert "Nema dovoljno kredita" not in html, (
        "nepouzdan ulaz je aktivirao poslovnu granu"
    )


def test_ng_prazan_zapis_ne_daje_prazan_okvir():
    """Odsustvo poruke nikad ne sme da izgleda kao uspeh."""
    (html,) = _pokreni([{}])
    assert "Nepoznata greška" in html, (
        "posao bez poruke prikazuje prazan okvir — advokat ne zna da je pao"
    )


# ─── 4. XSS ─────────────────────────────────────────────────────────────────

def test_e_poruka_sa_servera_je_escapovana():
    (html,) = _pokreni([{"error": "<img src=x onerror=alert(1)>", "error_status": 402}])
    assert "<img" not in html, "poruka greške se ubacuje u DOM neescapovana"
    assert "&lt;img" in html
