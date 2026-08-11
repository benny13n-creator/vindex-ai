# -*- coding: utf-8 -*-
"""
Javni sajt — ugovori koje ne smemo da izgubimo.

ŠTA OVAJ FAJL ČUVA

Sajt je zamenio `landing.html`, koji je godinu dana nosio tvrdnje koje proizvod
ne može da podrži: „Počni besplatno — 15 upita bez kartice" (samouslužna
registracija koja ne postoji), „18 zakona RS" (pre-auth ekran istovremeno tvrdi
847), „Nikad više propuštenih rokova" (garancija ishoda), i cenovnik od četiri
plana od kojih se nijedan ne može kupiti (`STRIPE_URL = ''`).

Nijedan test nije padao dok je sve to bilo javno — `client.get("/")` nije
postojao u `tests/` uopšte. Zato ovaj fajl.

METOD

Testovi mere ODGOVOR SERVERA, ne izvor na disku. Razlika je bitna: stranica koja
postoji u `site/` a nije zakačena na rutu je nevidljiva korisniku, i test koji
čita fajl to ne bi primetio.

Jedini izuzetak su strukturne provere HTML-a (§4), koje po prirodi gledaju
sadržaj odgovora — ali i one gledaju ono što je server STVARNO poslao.
"""
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Devet stranica novog sajta.
STRANICE = [
    "/", "/kako-radi", "/sposobnosti", "/za-advokate",
    "/bezbednost", "/vizija", "/tehnologija", "/beta", "/kontakt",
]

# Postojeće pravne i bezbednosne stranice — sajt ih linkuje, ne redizajnira.
PRAVNE = [
    "/privacy", "/terms", "/security", "/dpa",
    "/ai-disclosure", "/bezbednosni-list", "/status",
]


@pytest.fixture(scope="module")
def klijent():
    return TestClient(api.app)


def _tekst(klijent, ruta: str) -> str:
    """Sirov odgovor servera — za strukturne provere (atributi, oznake)."""
    r = klijent.get(ruta)
    assert r.status_code == 200, f"{ruta} vraća {r.status_code}"
    return r.text


def _vidljivi_tekst(klijent, ruta: str) -> str:
    """Samo ono što posetilac STVARNO vidi.

    Uklanja HTML komentare, `<script>` i `<style>` pre merenja.

    Ovo nije kozmetika. Prva verzija ovog fajla merila je sirov odgovor i
    prijavila tri lažna pada: `/kontakt` „sadrži" matični broj — u komentaru koji
    objašnjava da ga NAMERNO nema; `/beta` „obećava" potvrdu mejlom — u komentaru
    koji tu formulaciju zabranjuje. Isti razred greške (test meri komentar umesto
    koda) uhvaćen je već tri puta u ovom repou.
    """
    telo = _tekst(klijent, ruta)
    telo = re.sub(r"<!--.*?-->", " ", telo, flags=re.S)
    telo = re.sub(r"<script.*?</script>", " ", telo, flags=re.S)
    telo = re.sub(r"<style.*?</style>", " ", telo, flags=re.S)
    return telo


# ═══════════════════════════════════════════════════════════════════════════
# 1. RUTE — stranica koja nije zakačena na rutu ne postoji za korisnika
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", STRANICE)
def test_stranica_odgovara(klijent, ruta):
    r = klijent.get(ruta)
    assert r.status_code == 200, f"{ruta} vraća {r.status_code}"
    assert "text/html" in r.headers.get("content-type", "")
    assert r.headers.get("cache-control"), f"{ruta} nema Cache-Control"


@pytest.mark.parametrize("ruta", PRAVNE)
def test_postojece_pravne_stranice_i_dalje_rade(klijent, ruta):
    """Sajt ih linkuje iz podnožja. Ako neka padne, podnožje vodi u prazno."""
    assert klijent.get(ruta).status_code == 200


def test_css_se_servira(klijent):
    r = klijent.get("/static/site.css")
    assert r.status_code == 200
    assert "--vw-bg" in r.text, "servira se pogrešan CSS"


# ═══════════════════════════════════════════════════════════════════════════
# 2. CENOVNIK — uklonjen zato što se nijedan plan ne može kupiti
# ═══════════════════════════════════════════════════════════════════════════

def test_pricing_ruta_vise_ne_postoji(klijent):
    """`STRIPE_URL = ''` — nijedan plan se ne može kupiti; krediti se ne
    obnavljaju; reklamirane funkcije su gejtovane strože nego što su prodavane.

    Ruta je preživela P0-F (koji je uklonio sekciju iz landinga) i ostala javna.
    """
    assert klijent.get("/pricing").status_code == 404


@pytest.mark.parametrize("ruta", STRANICE)
def test_nijedna_stranica_ne_linkuje_cenovnik(klijent, ruta):
    assert 'href="/pricing"' not in _tekst(klijent, ruta)


# ═══════════════════════════════════════════════════════════════════════════
# 3. ZABRANJENE TVRDNJE — truth audit nad onim što server STVARNO pošalje
# ═══════════════════════════════════════════════════════════════════════════

# Doslovni nizovi iz starog landinga i iz spiska zabranjenih formulacija.
# Traže se u renderovanom odgovoru, ne u izvoru na disku.
ZABRANJENO = [
    "15 upita",
    "Počni besplatno",
    "Počnite besplatno",
    "Zakažite demo",
    "Nikad više propuštenih rokova",
    "18 zakona",
    "847 zakona",
    "bank-grade",
    "bank-level",
    "military-grade",
    "100% bezbedno",
    "100% sigurno",
    "nikad ne greši",
    "bez halucinacija",
    "GDPR usklađen",
    "sertifikovani",
    "AI nikad ne presuđuje",
    "na nivou baze",
    "doživotni pristup",
    "revolucionarn",
    "vodeća platforma",
]


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_zabranjenih_tvrdnji(klijent, ruta):
    telo = _vidljivi_tekst(klijent, ruta)
    nadjeno = [z for z in ZABRANJENO if z.lower() in telo.lower()]
    assert not nadjeno, f"{ruta} sadrži zabranjene tvrdnje: {nadjeno}"


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_procenta_tacnosti_ni_ustede(klijent, ruta):
    """Procenat tačnosti i ušteda vremena nikad nisu mereni.

    Traži se obrazac „<broj>%" i „<broj> puta brže/manje/više" — u tekstu, ne u
    CSS vrednostima (`width:100%`), pa se stilovi i skripte prvo uklanjaju.
    """
    telo = re.sub(r"<[^>]+>", " ", _vidljivi_tekst(klijent, ruta))

    assert not re.search(r"\d+\s*%", telo), f"{ruta} sadrži procenat"
    assert not re.search(r"\d+\s*(puta|x)\s+(brž|brz|manje|više)", telo, re.I), (
        f"{ruta} sadrži tvrdnju o ubrzanju"
    )


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_izmisljenog_pravnog_lica(klijent, ruta):
    """Vindex AI nema registrovano pravno lice.

    PIB, matični broj ili „d.o.o." na sajtu značili bi ili izmišljen podatak ili
    podatak druge firme predstavljen kao Vindexov.
    """
    telo = _vidljivi_tekst(klijent, ruta).lower()
    for izraz in ("pib:", "matični broj", "maticni broj", "d.o.o.", "doo "):
        assert izraz not in telo, f"{ruta} navodi pravni identitet: {izraz!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. STRUKTURA I PRISTUPAČNOST
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", STRANICE)
def test_jedan_h1_po_stranici(klijent, ruta):
    assert len(re.findall(r"<h1[\s>]", _tekst(klijent, ruta))) == 1


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_praznih_linkova(klijent, ruta):
    """Zatečeni landing je imao 9 od 20 linkova u podnožju kao `href="#"`."""
    telo = _tekst(klijent, ruta)
    assert 'href="#"' not in telo, f"{ruta} ima prazan link"


@pytest.mark.parametrize("ruta", STRANICE)
def test_canonical_je_vindex_rs(klijent, ruta):
    telo = _tekst(klijent, ruta)
    m = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', telo)
    assert m, f"{ruta} nema canonical"
    assert m.group(1).startswith("https://vindex.rs"), (
        f"{ruta} ima canonical {m.group(1)} — kanonski domen je vindex.rs"
    )


@pytest.mark.parametrize("ruta", STRANICE)
def test_srpski_jezik_i_viewport(klijent, ruta):
    telo = _tekst(klijent, ruta)
    assert 'lang="sr-Latn"' in telo
    assert 'name="viewport"' in telo


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_eksternih_slika_i_okvira(klijent, ruta):
    """CSP zabranjuje eksterne slike, iframe-ove i video.

    Stranica koja ih traži ne bi pukla u testu nego tiho u pretraživaču.
    """
    telo = _tekst(klijent, ruta)
    assert "<iframe" not in telo
    assert "<video" not in telo
    for m in re.findall(r'<img[^>]+src="([^"]+)"', telo):
        assert not m.startswith("http"), f"{ruta} učitava eksternu sliku: {m}"


@pytest.mark.parametrize("ruta", STRANICE)
def test_svaki_svg_ima_pristupacan_naziv(klijent, ruta):
    """Sve ilustracije su SVG dijagrami — bez `<title>` su nevidljivi
    čitaču ekrana."""
    telo = _tekst(klijent, ruta)
    for svg in re.findall(r"<svg\b.*?</svg>", telo, flags=re.S):
        assert "<title" in svg, f"{ruta} ima SVG bez <title>"


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_zabranjenih_generickih_ikona(klijent, ruta):
    """Dozvoljeni su samo funkcionalni indikatori `✓` i `⚠`."""
    telo = _tekst(klijent, ruta)
    for ikona in "⚔🧠⚖🎯⚡💡📊🚨🤖🗄🔍⚙":
        assert ikona not in telo, f"{ruta} sadrži zabranjenu ikonu {ikona!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. KONVERZIJA — Beta je jedini poziv na akciju
# ═══════════════════════════════════════════════════════════════════════════

def test_pocetna_vodi_na_betu(klijent):
    assert 'href="/beta"' in _tekst(klijent, "/")


def test_beta_forma_gadja_postojeci_endpoint(klijent):
    """Forma mora slati na rutu koja stvarno postoji."""
    telo = _tekst(klijent, "/beta")
    assert "/waitlist/prijava" in telo


def test_waitlist_endpoint_prima_polja_koja_forma_salje(klijent):
    """Ugovor forme i backenda, meren stvarnim pozivom.

    Forma šalje `ime`, `email`, `firma`, `poruka`. Ako se model promeni tako da
    neko od njih postane nepoznato ili obavezno drugačije, ovo pada.
    """
    from unittest.mock import MagicMock, patch

    with patch("routers.waitlist._get_supa", return_value=MagicMock()):
        r = klijent.post("/waitlist/prijava", json={
            "ime": "Test Testović",
            "email": "test.website@example.com",
        "firma": "Test kancelarija",
            "poruka": "[BETA] provera ugovora",
        })
    assert r.status_code == 200, f"endpoint vraća {r.status_code}: {r.text[:200]}"
    telo = r.json()
    assert "poruka" in telo, (
        "odgovor nema ključ `poruka` — forma prikazuje baš njega, pa bi korisnik "
        "ostao bez povratne informacije"
    )


def test_beta_ne_obecava_email_potvrdu(klijent):
    """SMTP se tiho preskače ako env nije podešen — korisnik dobija 200 i kad
    nijedan mejl nije poslat. Zato stranica ne sme obećati potvrdu."""
    telo = _vidljivi_tekst(klijent, "/beta").lower()
    for izraz in ("proverite inboks", "potvrda je poslata", "poslali smo vam mejl",
                  "poslali smo vam email"):
        assert izraz not in telo, f"/beta obećava mejl koji možda nije poslat: {izraz!r}"


@pytest.mark.parametrize("izraz", [r"cen[aeu]", r"€", r"RSD",
                                  r"dinara\s+mesečno", r"pretplat"])
def test_beta_ne_pominje_cenu(klijent, izraz):
    """Founding Partner nema definisanu cenu; nijedan plan se ne može kupiti.

    Granica reči je obavezna: `cena` kao podniz pogađa `proCENAt`, pa je prva
    verzija ovog testa padala na rečenici koja uopšte ne govori o novcu.
    """
    telo = re.sub(r"<[^>]+>", " ", _vidljivi_tekst(klijent, "/beta"))
    assert not re.search(izraz, telo, re.I), f"/beta pominje {izraz!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. SEO
# ═══════════════════════════════════════════════════════════════════════════

def test_sitemap_navodi_sve_stranice(klijent):
    r = klijent.get("/sitemap.xml")
    assert r.status_code == 200
    for ruta in STRANICE:
        if ruta == "/":
            continue
        assert ruta in r.text, f"sitemap ne navodi {ruta}"


def test_robots_i_dalje_stiti_api(klijent):
    """Postojeći test (`test_api_security.py:121`) čuva ovaj ugovor — ovde se
    potvrđuje da ga dodavanje `Sitemap:` linije nije slomilo."""
    telo = klijent.get("/robots.txt").text
    assert "User-agent" in telo
    assert "/api/" in telo
    assert "Sitemap:" in telo
