# -*- coding: utf-8 -*-
"""
Early Access, Faza B1 (2026-11-02) — stranica /beta nosi tekst ranog pristupa koji je osnivač
odobrio, DOSLOVNO, i nudi dva postojeća puta:

  1. „Isprobajte Vindex“ → /app#register — postojeća samostalna registracija (POST /api/register).
  2. „Zatražite pristup za kancelariju“ → #zahtev — postojeća forma (POST /waitlist/prijava).

Ugovori:
  • svaki blok odobrenog teksta je tačan tekst jednog elementa, istim redom, sa istim nivoom naslova;
  • u odeljcima teksta nema nijedne rečenice koja nije odobrena (bez samostalnog dopisivanja);
  • oba dugmeta vode na rute koje stvarno postoje i rade ono što tekst kaže;
  • nema obećanja neograničenog pristupa, mesečnog punjenja kredita, automatskog odobrenja ni cene;
  • na sajtu nema plaćanja karticom ni automatske naplate;
  • forma, njena napomena o privatnosti i pravni linkovi su sačuvani;
  • generator je determinističan.
"""
import html as _html
import os
import re
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Odobreni tekst osnivača („FOUNDER HANDOFF: APPROVED EARLY ACCESS COPY“, 2026-11-02), blok po blok.
# (oznaka elementa, tekst). Markdown `#`/`##`/`###` → h1/h2/h3; podebljano → <strong>.
ODOBRENO = [
    ("h1", "Rani pristup Vindexu"),
    ("h2", "Upoznajte Vindex u svojoj pravnoj praksi."),
    ("p", "Vindex je pravni operativni sistem koji povezuje predmete, dokumente, dokaze, rokove, pravno "
          "istraživanje i pripremu podnesaka u jedinstven radni prostor."),
    ("p", "U periodu ranog pristupa Vindex možete isprobati bez plaćanja pretplate. Novi nalog uključuje "
          "ograničen fond AI kredita za upoznavanje sa dostupnim funkcionalnostima."),
    ("p", "Sami odlučujete koje podatke unosite, a predložene informacije i dokumente pregledate pre "
          "profesionalne upotrebe."),
    ("h3", "Isprobajte Vindex"),
    ("p", "Otvorite nalog i upoznajte način rada, bez kartice i bez automatske naplate."),
    ("h3", "Potreban vam je pristup za kancelariju?"),
    ("p", "Pošaljite zahtev za prošireni pristup. Razmotrićemo potrebe vaše kancelarije i mogućnosti "
          "odgovarajućeg paketa."),
    ("h3", "Kako funkcioniše pristup?"),
    ("p", "Tokom ranog pristupa pretplata se ne naplaćuje. AI funkcije koriste ograničen broj uključenih "
          "kredita. Po njihovom isteku dodatno korišćenje tih funkcija zahteva novo odobrenje ili odgovarajući "
          "paket — bez automatskog zaduživanja."),
    ("p", "Vindex pruža podršku profesionalnom radu; pravne zaključke, rokove i dokumente proverava advokat."),
]
PODEBLJANO = [
    "U periodu ranog pristupa Vindex možete isprobati bez plaćanja pretplate.",
    "Vindex pruža podršku profesionalnom radu; pravne zaključke, rokove i dokumente proverava advokat.",
]
# Oznake dugmadi su nazivi dva puta iz ugovora osnivača (B1: „Isprobajte Vindex“, „Zatražite pristup za kancelariju“).
DUGMAD = [("/app#register", "Isprobajte Vindex"), ("#zahtev", "Zatražite pristup za kancelariju")]


@pytest.fixture(scope="module")
def k():
    return TestClient(api.app)


@pytest.fixture(scope="module")
def beta(k):
    r = k.get("/beta")
    assert r.status_code == 200
    return r.text


def _cist(s: str) -> str:
    s = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _tekst_odeljaka(beta: str) -> str:
    """Sadržaj <main> PRE forme (#zahtev): to je deo koji nosi odobreni tekst."""
    main = re.search(r"<main[^>]*>(.*?)</main>", beta, flags=re.S).group(1)
    return re.split(r'<section[^>]*id="zahtev"', main)[0]


def _elementi(deo: str) -> list[tuple[str, str]]:
    return [(m.group(1), _cist(m.group(2))) for m in re.finditer(r"<(h1|h2|h3|p)\b[^>]*>(.*?)</\1>", deo, flags=re.S)]


def test_odobreni_tekst_je_doslovan_istim_redom_i_istim_nivoima(beta):
    elementi = [e for e in _elementi(_tekst_odeljaka(beta)) if e[1]]
    assert elementi == ODOBRENO, "\n".join(f"{a!r} ≠ {b!r}" for a, b in zip(elementi, ODOBRENO) if a != b) or elementi


def test_nema_nijedne_neodobrene_recenice_u_tekstu_ranog_pristupa(beta):
    """Pored odobrenog teksta stoje samo oznake dva dugmeta; sve ostalo bi bilo samostalno dopisivanje."""
    ceo = _cist(_tekst_odeljaka(beta))
    for _, blok in ODOBRENO:
        assert blok in ceo
        ceo = ceo.replace(blok, " ", 1)
    for _, oznaka in DUGMAD:
        ceo = ceo.replace(oznaka, " ", 1)
    assert ceo.strip() == "", f"neodobren tekst: {ceo.strip()!r}"


def test_podebljani_delovi_su_kao_u_odobrenom_tekstu(beta):
    podebljano = [_cist(m) for m in re.findall(r"<strong>(.*?)</strong>", _tekst_odeljaka(beta), flags=re.S)]
    assert podebljano == PODEBLJANO


def test_izvor_i_generisana_stranica_nose_isti_tekst():
    with open(os.path.join(KOREN, "site", "_izvor", "beta.html"), encoding="utf-8") as f:
        izvor = _cist(f.read())
    with open(os.path.join(KOREN, "site", "beta.html"), encoding="utf-8") as f:
        sacuvano = _cist(f.read())
    for _, blok in ODOBRENO:
        assert blok in izvor and blok in sacuvano, blok


# ── Dva puta ────────────────────────────────────────────────────────────────

def test_dva_puta_vode_na_postojecu_registraciju_i_postojecu_formu(beta):
    dugmad = re.findall(r'<li class="kartica put"[^>]*>.*?<a class="dugme[^"]*" href="([^"]+)">([^<]+)</a>', beta, flags=re.S)
    assert dugmad == DUGMAD


def test_isprobajte_vodi_na_stvarnu_registraciju(k):
    """/app#register: klasični /app otvara modal u režimu registracije; V2 /app isti hash
    prosleđuje klasičnoj prijavi (/app-legacy#register). Ruta registracije postoji i traži samo
    e-poštu i lozinku — bez kartice i bez ikakvog podatka o plaćanju."""
    assert k.get("/app").status_code == 200
    with open(os.path.join(KOREN, "static", "vindex.js"), encoding="utf-8") as f:
        legacy = f.read()
    assert re.search(r"hash === '#register'\)\s*\{\s*openModal\(\);\s*setAuthMode\('register'\);", legacy)
    with open(os.path.join(KOREN, "frontend-v2-ng", "src", "runtime.js"), encoding="utf-8") as f:
        v2 = f.read()
    assert 'h === "#register"' in v2 and 'root.location.replace("/app-legacy" + h)' in v2
    assert set(api.RegisterReq.model_fields) == {"email", "password"}
    r = k.post("/api/register", json={})
    assert r.status_code == 422, r.status_code


def test_zahtev_kancelarije_je_postojeca_forma_sa_napomenom_o_privatnosti(k, beta):
    zahtev = re.search(r'<section[^>]*id="zahtev"[^>]*>(.*?)</section>', beta, flags=re.S)
    assert zahtev, "nema odeljka #zahtev"
    telo = zahtev.group(1)
    assert 'id="beta-forma"' in telo and 'id="beta-posalji"' in telo
    for polje in ("ime", "email", "firma", "telefon", "poruka"):
        assert f'name="{polje}"' in telo, polje
    assert 'href="/privacy#beta-prijava"' in telo
    assert 'id="beta-prijava"' in k.get("/privacy").text
    assert 'fetch("/waitlist/prijava"' in k.get("/v2/site/sajt.js").text
    assert "Automatska potvrda se ne šalje e-poštom; prijavu pregledamo pojedinačno." in _cist(telo)


def test_pravni_linkovi_ostaju(beta):
    for put in ("/privacy", "/terms", "/dpa", "/ai-disclosure", "/app"):
        assert f'href="{put}"' in beta, put


# ── Šta stranica NE sme da obeća ────────────────────────────────────────────

@pytest.mark.parametrize("izraz", [
    r"neograničen", r"bez ograničenja", r"automatsk\w* odobr", r"odmah aktiv", r"svakog meseca",
    r"mesečn\w* (punjenj|obnov|dopun)", r"obnavlja", r"reset", r"€", r"\bEUR\b", r"\bcen[aeu]\b",
    r"\b(29|69|79|249)\b", r"kreditn\w* kartic", r"broj kartice", r"potvrd\w* (je )?posla\w* e-poštom",
])
def test_beta_ne_obecava_vise_nego_sto_postoji(beta, izraz):
    assert not re.search(izraz, _cist(beta), re.I), izraz


def test_kartica_se_pominje_samo_kao_bez_kartice(beta):
    assert re.findall(r"\w*kartic\w*", _cist(beta), re.I) == ["kartice"]
    assert "bez kartice" in _cist(beta)


def test_sajt_nema_placanja_ni_automatske_naplate():
    sajt = os.path.join(KOREN, "site")
    for ime in sorted(os.listdir(sajt)):
        if not ime.endswith((".html", ".js")):
            continue
        with open(os.path.join(sajt, ime), encoding="utf-8") as f:
            t = f.read().lower()
        for zabranjeno in ("stripe", "checkout", "paypal", "paddle", "card-number", "cardnumber", "autorenew", "auto-renew"):
            assert zabranjeno not in t, f"{ime}: {zabranjeno}"


# ── Gradnja ─────────────────────────────────────────────────────────────────

def test_generator_je_deterministican_i_uskladjen():
    for _ in range(2):
        r = subprocess.run([sys.executable, os.path.join("scripts", "gradi_sajt.py"), "--provera"], cwd=KOREN,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stdout + r.stderr


def test_stilovi_za_dva_puta_postoje():
    with open(os.path.join(KOREN, "site", "sajt.css"), encoding="utf-8") as f:
        css = f.read()
    for pravilo in (".sajt .uvod__podnaslov", ".sajt .put {", ".sajt .put .akcije"):
        assert pravilo in css, pravilo
