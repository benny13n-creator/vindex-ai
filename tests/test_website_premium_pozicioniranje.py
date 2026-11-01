# -*- coding: utf-8 -*-
"""
Website Premium Positioning (founder, 2026-11-01) — ugovori javnog sajta.

  1. Nula oznaka verzije proizvoda na svemu što posetilac vidi ili čuje: tekst, naslov,
     meta/OG opisi, alt, aria-label. Tehničke adrese asseta (/v2/site/…) i interni
     `data-status` nisu korisnički tekst i ne mere se.
  2. Nema internih naziva projekta, sprintova, zahteva, migracija ni CI statistike.
  3. MIR (Miroslav): nijedna nepotvrđena sposobnost se ne prikazuje kao dostupna —
     nacrt iz spisa (MIR-03, C3b FAIL), korporativni rad (MIR-04 BLOCKED_REQUIREMENTS_DETAIL),
     samostalna/pozadinska AI obrada (MIR-05 BLOCKED_AUTHORITY).
  4. Email podsetnici: isporuka nije potvrđena (LIVE_EMAIL_DELIVERY_NOT_VERIFIED), a
     podešavanje i slanje postoje u kodu — sajt ne tvrdi ni „šalje“ ni „ne šalje“.
  5. Nema apsolutnih garancija ishoda ni tačnosti.
Dokaz tvrdnji: docs/website-v2/07_PREMIUM_POSITIONING_RELEASE.md.
"""
import html as _html
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402

STRANICE = ["/", "/kako-radi", "/funkcionalnosti", "/za-advokate", "/bezbednost", "/beta"]


@pytest.fixture(scope="module")
def k():
    return TestClient(api.app)


def _povrsine(telo: str) -> str:
    """Sve što posetilac vidi ili čuje: vidljiv tekst + title + meta/OG opisi + alt + aria-label + title atributi."""
    bez = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", telo, flags=re.S)
    atributi = [a for a in re.findall(r'\s(?:alt|aria-label|title|content|placeholder)="([^"]*)"', bez)
                if not re.match(r"(https?:)?/", a)]   # adrese (og:image, canonical) nisu tekst za posetioca
    tekst = re.sub(r"<[^>]+>", " ", bez)
    return _html.unescape(re.sub(r"\s+", " ", tekst + " " + " ".join(atributi)))


OZNAKE_VERZIJE = [r"\bV\s?2\b", r"\bV\s?3\b", r"version\s*2", r"verzij[aeiu]\s*2", r"legacy", r"klasičn",
                  r"stara aplikacija", r"nova aplikacija", r"stari interfejs", r"novi interfejs", r"nova generacija",
                  r"next[- ]gen", r"preview"]
INTERNO = [r"\bMIR-?0\d", r"Miroslav", r"\bBojan", r"\bsprint", r"migracij", r"\bCI\b", r"\bPR #", r"pytest",
           r"\bOCR001\b", r"\bNS0\d\d", r"\bVCR0", r"feature flag", r"\bstaging\b", r"\bbackend\b", r"\bendpoint"]


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_oznake_verzije_proizvoda(k, ruta):
    t = _povrsine(k.get(ruta).text)
    nadjeno = [rx for rx in OZNAKE_VERZIJE if re.search(rx, t, re.I)]
    assert not nadjeno, f"{ruta}: oznaka verzije {nadjeno}"


def test_generator_nikad_ne_objavljuje_klasicni_prikaz():
    """Odbrana i na nivou generatora, ne samo podataka: LEGACY_ONLY nije javni status i nema javnu oznaku."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import gradi_sajt
    assert "LEGACY_ONLY" not in gradi_sajt.JAVNI_STATUSI
    assert gradi_sajt.registar()["statusi"]["LEGACY_ONLY"]["javno"] is None


def test_poruke_forme_nemaju_oznaku_verzije(k):
    js = re.sub(r"/\*.*?\*/", " ", k.get("/v2/site/sajt.js").text, flags=re.S)   # komentari nisu poruke
    poruke = " ".join(re.findall(r'"([^"]{12,})"', js))
    assert not [rx for rx in OZNAKE_VERZIJE if re.search(rx, poruke, re.I)]


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_internih_naziva_ni_statistike(k, ruta):
    t = _povrsine(k.get(ruta).text)
    nadjeno = [rx for rx in INTERNO if re.search(rx, t, re.I)]
    assert not nadjeno, f"{ruta}: interni pojmovi {nadjeno}"


@pytest.mark.parametrize("ruta", STRANICE)
def test_miroslav_sposobnosti_nisu_oglasene_kao_dostupne(k, ruta):
    t = _povrsine(k.get(ruta).text).lower()
    for rx in (r"iz spisa", r"na osnovu (celog )?spisa", r"spreman za (sud|podnošenje)", r"gotov podnesak za",
               r"korporativ", r"ugovorni tim", r"due diligence", r"svakog jutra analizir", r"automatski analizir",
               r"u pozadini", r"samostaln[aio] (pripremа|priprema|analizira|radi)", r"autonomn", r"umesto vas"):
        assert not re.search(rx, t), f"{ruta}: {rx}"
    # Nacrt je uvek polazna tačka koju overava advokat, gde god se pominje.
    if "nacrt podneska" in t:
        assert "polazn" in _povrsine(k.get("/kako-radi").text).lower()


@pytest.mark.parametrize("ruta", STRANICE)
def test_podsetnici_se_ne_tvrde_ni_poricu(k, ruta):
    t = _povrsine(k.get(ruta).text).lower()
    assert "podsetni" not in t, f"{ruta}: tvrdnja o podsetnicima bez potvrđene isporuke"


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_apsolutnih_garancija(k, ruta):
    t = _povrsine(k.get(ruta).text).lower()
    for rx in (r"garan(t|cij)", r"uvek tačn", r"potpuno tačn", r"bez greš", r"nikad(a)? ne propust", r"sve rokove",
               r"automatski (šalje|prati|upisuje|potvrđuje)", r"enterprise", r"revolucion", r"sudu spreman",
               r"zamenjuje (advokat|pravn)"):
        assert not re.search(rx, t), f"{ruta}: {rx}"


def test_pocetna_je_kraca_i_vodi_jednim_pozivom(k):
    """Hijerarhija početne: uvod → vrednost → tok sa stvarnim ekranima → poverenje → poziv. Bez kataloga svih funkcija."""
    t = k.get("/").text
    sekcije = re.findall(r'<section class="([^"]+)" aria-labelledby="([^"]+)"', t)
    assert [s[1] for s in sekcije] == ["naslov", "vrednost-naslov", "tok-naslov", "poverenje-naslov", "zavrsni-naslov"]
    assert len(re.findall(r'class="vrednost otkrij"', t)) == 4
    assert 'class="stavka' not in t                                   # bez kataloga na početnoj
    assert len(re.findall(r'<a class="dugme dugme--istaknuto" href="/beta">', t)) == 2


def test_za_advokate_je_jedan_tok_jednog_predmeta(k):
    t = k.get("/za-advokate").text
    koraci = re.findall(r'<li class="prica__korak">', t)
    assert 5 <= len(koraci) <= 8
    vidljivo = _povrsine(t)
    assert "Okolnosti su izmišljene" in vidljivo
    for rx in (r"dobi(li|o) (smo )?spor", r"presuda u korist", r"uštede?l", r"sati manje", r"\d+\s*%"):
        assert not re.search(rx, vidljivo, re.I), rx            # bez izmišljenog ishoda
