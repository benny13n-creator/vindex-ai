# -*- coding: utf-8 -*-
"""
P0-B — pozivi globalnih funkcija koje ne postoje (BTM-P0-11).

ZAŠTO OVAJ TEST POSTOJI

`static/vindex.js` je ~22.000 linija bez ijednog modula, bundlera ili linter-a.
Ime funkcije se ne proverava dok se linija ne izvrši. Tri poziva su tako živela
u produkciji:

  `apiFetch`       :15494, :15499  — uveden u c659042f (2026-06-28) zajedno sa
                                     svoja dva poziva i nijednom definicijom.
                                     Ubijao je CEO onboarding: `onboardingStep`
                                     zove `onboardingDismiss` u prvoj liniji,
                                     ReferenceError se baca SINHRONO sa mesta
                                     poziva, `.catch()` ga ne hvata, navigacija
                                     se nikad ne izvrši.
  `crm_load`       :4767           — posle uspešnog CSV uvoza; toast na istoj
                                     liniji se nikad ne prikaže, lista se ne
                                     osveži. Ispravno: `ucitajKlijente`.
  `pred_fetchList` :10042          — POSLE uspešnog PATCH-a, nezaštićen; greška
                                     pada u `catch` i prikazuje "Veza sa
                                     serverom nije uspela" za radnju koja je na
                                     serveru PROŠLA. Ispravno: `pred_load`.

Testiranje tri imena poimence ne bi sprečilo četvrto. Ovaj test skenira ceo
fajl i traži SVAKI poziv globalne funkcije bez definicije — to je trajna
invarijanta, imena su samo današnji primeri.

METOD I NJEGOVE GRANICE

Ovo nije JS parser. Komentari, stringovi i regex literali se ispiraju uz
očuvanje brojeva linija, pa se traže `ime(` bez tačke ispred. Definicije se
skupljaju iz `vindex.js` I iz inline `<script>` blokova u `index.html`.

Namerno se prijavljuje SAMO ono što nije nigde vezano. Metode objekata
(`obj.metoda()`) se ne gledaju — statička analiza ne može da im nađe vlasnika.
Test je dakle konzervativan: može propustiti neki defekt, ali ne sme lažno da
optuži. Ako ikad počne da laže, popravlja se detektor — ne briše se tvrdnja.
"""
import os
import re
import subprocess
import sys

import pytest

_KOREN = os.path.join(os.path.dirname(__file__), "..")
_VINDEX = os.path.join(_KOREN, "static", "vindex.js")
_INDEX = os.path.join(_KOREN, "index.html")

# Ugrađeni JS/DOM/browser globali i biblioteke koje stižu preko <script src>.
# Tri CDN-a (Chart, html2canvas, html2pdf) su ovde jer ih `index.html` učitava
# spolja i svaki poziv im je ionako zaštićen `typeof ... === 'undefined'`
# proverom u samom kodu.
_UGRADJENI = {
    # jezik
    "Array", "Boolean", "Date", "Error", "Function", "JSON", "Map", "Math",
    "Number", "Object", "Promise", "Proxy", "RegExp", "Set", "String", "Symbol",
    "WeakMap", "WeakSet", "BigInt", "Intl", "Reflect", "TypeError", "RangeError",
    "SyntaxError", "ReferenceError", "EvalError", "URIError", "AggregateError",
    "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent",
    "decodeURIComponent", "encodeURI", "decodeURI", "eval", "structuredClone",
    "queueMicrotask", "require", "import",
    # browser / DOM
    "alert", "confirm", "prompt", "fetch", "setTimeout", "setInterval",
    "clearTimeout", "clearInterval", "requestAnimationFrame",
    "cancelAnimationFrame", "getComputedStyle", "matchMedia", "atob", "btoa",
    "open", "close", "print", "scrollTo", "scrollBy", "postMessage", "addEventListener",
    "removeEventListener", "dispatchEvent", "FormData", "Blob", "File", "FileReader",
    "URL", "URLSearchParams", "Headers", "Request", "Response", "AbortController",
    "WebSocket", "Worker", "Notification", "Image", "Audio", "AudioContext",
    "MediaRecorder", "Event", "CustomEvent", "MutationObserver",
    "IntersectionObserver", "ResizeObserver", "TextEncoder", "TextDecoder",
    "Uint8Array", "Int16Array", "Float32Array", "ArrayBuffer", "DataView",
    "localStorage", "sessionStorage", "navigator", "location", "history",
    "document", "window", "console", "crypto", "performance", "screen",
    "speechSynthesis", "SpeechSynthesisUtterance", "RTCPeerConnection",
    "webkitSpeechRecognition", "SpeechRecognition", "DOMParser", "XMLHttpRequest",
    # spolja učitane biblioteke (index.html <script src>)
    "Chart", "html2canvas", "html2pdf", "supabase", "createClient",
}

# `ime(` gde ispred nije tačka, znak reči, ili `function`/`new` ključna reč.
_POZIV = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(")

_DEFINICIJE = [
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\bcatch\s*\(\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"\bwindow\.([A-Za-z_$][\w$]*)\s*="),
    re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function", re.M),
    # parametri: function f(a, b) / catch / arrow (a, b) =>
    re.compile(r"\bfunction\s*[A-Za-z_$\w]*\s*\(([^)]*)\)"),
    re.compile(r"\(([^)]*)\)\s*=>"),
]

_KLJUCNE = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "function",
    "new", "delete", "void", "in", "of", "do", "else", "try", "throw", "case",
    "await", "yield", "instanceof", "class", "extends", "super", "this",
    "var", "let", "const", "async", "get", "set", "static", "with", "debugger",
}


def _ispiraj(src: str) -> str:
    """Zamenjuje komentare, stringove i regex literale razmacima.

    Broj linija se čuva (novi redovi ostaju) da bi prijavljeni broj linije bio
    upotrebljiv. Ovo je jedini deo detektora koji mora biti tačan — kalibrisan
    je na poznatoj činjenici da `apiFetch` ima tačno 2 poziva.
    """
    out = []
    i, n = 0, len(src)
    stanje = None      # None | '//' | '/*' | "'" | '"' | '`' | '/'
    while i < n:
        c = src[i]
        sled = src[i + 1] if i + 1 < n else ""
        if stanje is None:
            if c == "/" and sled == "/":
                stanje = "//"; out.append("  "); i += 2; continue
            if c == "/" and sled == "*":
                stanje = "/*"; out.append("  "); i += 2; continue
            if c in "'\"`":
                stanje = c; out.append(" "); i += 1; continue
            if c == "/":
                # Regex literal samo ako prethodni ne-beli znak dozvoljava
                # početak izraza; inače je deljenje.
                j = len(out) - 1
                while j >= 0 and out[j] in " \t\n\r":
                    j -= 1
                pret = out[j] if j >= 0 else ""
                if pret in "" or pret in "(,=:[!&|?{};+-*%~^<>" or pret == "":
                    stanje = "/"; out.append(" "); i += 1; continue
            out.append(c); i += 1; continue

        if stanje == "//":
            if c == "\n":
                stanje = None; out.append("\n")
            else:
                out.append(" ")
            i += 1; continue
        if stanje == "/*":
            if c == "*" and sled == "/":
                stanje = None; out.append("  "); i += 2; continue
            out.append("\n" if c == "\n" else " "); i += 1; continue
        # string ili regex
        if c == "\\":
            out.append("  "); i += 2; continue
        if c == stanje:
            stanje = None; out.append(" "); i += 1; continue
        if stanje == "/" and c == "\n":
            stanje = None      # neterminisan regex — ne guta ostatak fajla
        out.append("\n" if c == "\n" else " "); i += 1

    return "".join(out)


def _definisana_imena(*izvori: str) -> set:
    imena = set()
    for src in izvori:
        for rx in _DEFINICIJE:
            for m in rx.finditer(src):
                for deo in m.group(1).split(","):
                    ime = deo.strip().split("=")[0].strip()
                    ime = ime.lstrip(".").strip("{}[] \t")
                    if re.fullmatch(r"[A-Za-z_$][\w$]*", ime or ""):
                        imena.add(ime)
    return imena


def _inline_skripte(html: str) -> str:
    return "\n".join(
        m.group(1) for m in re.finditer(
            r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I
        )
    )


@pytest.fixture(scope="module")
def analiza():
    js = open(_VINDEX, encoding="utf-8").read()
    html = open(_INDEX, encoding="utf-8").read()
    js_cist = _ispiraj(js)
    html_cist = _ispiraj(_inline_skripte(html))
    definisano = _definisana_imena(js_cist, html_cist) | _UGRADJENI | _KLJUCNE

    nedostaju = {}
    for m in _POZIV.finditer(js_cist):
        ime = m.group(1)
        if ime in definisano:
            continue
        linija = js_cist.count("\n", 0, m.start()) + 1
        nedostaju.setdefault(ime, []).append(linija)
    return nedostaju


# ─── 1. TRAJNA INVARIJANTA ──────────────────────────────────────────────────

def test_a_nijedan_poziv_ne_gadja_nepostojecu_funkciju(analiza):
    """Ovo je tvrdnja koja mora važiti zauvek; imena su samo primeri.

    Ako padne sa NOVIM imenom: to je isti razred defekta, nađi pravu funkciju
    (obično je u pitanju preimenovanje koje nije praćeno na svim pozivima) i
    popravi POZIV. Nemoj definisati praznu funkciju da greška nestane, i nemoj
    dodati ime u `_UGRADJENI` osim ako je stvarno globalno iz browsera ili
    <script src> biblioteke.
    """
    assert not analiza, (
        "pozivi globalnih funkcija bez definicije: "
        + "; ".join(f"{k} @ {v}" for k, v in sorted(analiza.items()))
    )


# ─── 2. TRI KONKRETNA, POIMENCE ─────────────────────────────────────────────

@pytest.mark.parametrize("mrtvo,ispravno", [
    ("apiFetch", None),                 # zamenjen sirovim fetch-om, bez wrappera
    ("crm_load", "ucitajKlijente"),
    ("pred_fetchList", "pred_load"),
])
def test_b_konkretna_mrtva_imena_su_nestala(mrtvo, ispravno):
    """Test A bi ovo uhvatio, ali bi poruka bila generička.

    Ovi testovi imenuju defekt, pa ko god ga vrati odmah vidi šta je ispravna
    zamena umesto da je ponovo istražuje.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    assert not re.search(r"(?<![\w$.])" + re.escape(mrtvo) + r"\s*\(", _ispiraj(js)), (
        f"`{mrtvo}()` je ponovo pozvan; "
        + (f"ispravno ime je `{ispravno}()`" if ispravno
           else "ne definiši wrapper -- koristi sirov fetch kao ostatak fajla")
    )
    if ispravno:
        assert f"{ispravno}(" in js, f"zamena `{ispravno}` ne postoji u fajlu"


# ─── 3. NAVIGACIJA NIJE SPREGNUTA SA KNJIGOVODSTVOM ─────────────────────────

def test_c_onboarding_navigacija_prezivljava_gresku_u_dismiss(analiza):
    """Pravi uzrok P0-B nije bila nedostajuća funkcija nego SPREGA.

    `onboardingStep` je zavisio od toga da `onboardingDismiss` uspe. Da nije,
    nedostajuća funkcija bi bila tiha greška u konzoli umesto mrtvog prvog
    ekrana. Ovaj test čuva razdvajanje.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(r"function onboardingStep\s*\([^)]*\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "onboardingStep nije pronađen -- ako je preimenovan, prepiši ovaj test"
    telo = m.group(1)
    assert "try" in telo and "onboardingDismiss()" in telo, (
        "onboardingDismiss() mora biti u try/catch unutar onboardingStep -- "
        "inače greška u knjigovodstvu ponovo ubija navigaciju"
    )


def test_d_onboarding_cita_stanje_iz_baze_ne_samo_localStorage():
    """`profiles.onboarding_done` se upisivao, a nikad nije čitao na frontendu.

    Posledica je bila da se onboarding vraćao u svakom novom browseru iako je
    korisnik odavno prošao. localStorage sme da bude keš, ne izvor istine.
    """
    js = open(_VINDEX, encoding="utf-8").read()
    m = re.search(r"function onboardingCheck\s*\([^)]*\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "onboardingCheck nije pronađen"
    assert "onboarding_done" in m.group(1), (
        "onboardingCheck ne čita `onboarding_done` iz backend odgovora"
    )


# ─── 4. SINTAKSA ────────────────────────────────────────────────────────────

def test_e_vindex_js_je_sintaksno_validan():
    """Isti obraz kao `tests/test_iron_lawyer_frontend_fixes.py:22-30`."""
    try:
        r = subprocess.run(["node", "--check", _VINDEX],
                           capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("node nije dostupan")
    assert r.returncode == 0, f"node --check pao:\n{r.stderr}"


# ─── 5. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_detektor_stvarno_hvata_nepostojecu_funkciju():
    """Dokaz da test A meri nešto.

    Bez ovoga bi test A prolazio i da detektor uvek vraća prazan skup -- npr.
    da je `_ispiraj` slomljen pa ispere ceo fajl.
    """
    lazni = "function poznata(){}\nponovoNepostojeca(1);\npoznata();\n"
    cist = _ispiraj(lazni)
    definisano = _definisana_imena(cist) | _UGRADJENI | _KLJUCNE
    nadjeno = {m.group(1) for m in _POZIV.finditer(cist)} - definisano
    assert "ponovoNepostojeca" in nadjeno, "detektor ne vidi nepostojeću funkciju"
    assert "poznata" not in nadjeno, "detektor lažno optužuje definisanu funkciju"


def test_ng_ispiranje_cuva_brojeve_linija():
    """Prijavljen broj linije mora biti upotrebljiv."""
    src = "var a = 1;\n// komentar\n/* blok\nvise redova */\nvar s = 'tekst';\nfoo();\n"
    assert _ispiraj(src).count("\n") == src.count("\n")


def test_ng_ispiranje_ne_gleda_u_stringove():
    """Ime unutar stringa ne sme da se broji kao poziv."""
    cist = _ispiraj("var s = 'nepostojecaUString(1)';\n")
    assert "nepostojecaUString" not in cist
