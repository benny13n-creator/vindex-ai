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

NS004 (founder direktiva „nema tvrdnje bez živog puta u proizvodu"): sajt je
jedna početna strana u V2 identitetu. Marketinške stranice bez živog puta su
povučene (301 na odgovarajući odeljak). Ugovori tih stranica (Beta forma, /web3
ograde, devet stranica) prevedeni su u: povučena ruta preusmerava, njen stari
sadržaj više nije dostupan, a početna ne ponavlja nijednu od tih tvrdnji.
Matrica tvrdnji: docs/ns004-site-claims.md.

WEBSITE V2 (founder mandat „Website V2 Master Implementation“, 2026-10-20): sajt je
ponovo višestraničan, ali svaka funkcija na njemu dolazi iz JEDNOG registra
(`site/funkcije.json`) sa statusom i dokazom. Povučene adrese koje sada imaju
stranicu (/kako-radi, /za-advokate, /bezbednost, /beta) to više nisu; ostale
stare adrese preusmeravaju na stranicu koja ih nasleđuje. §9 meri ugovor sadržaja:
javna stranica ne sme reći ni više ni manje od registra.
"""
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Website V2: javne stranice (generiše scripts/gradi_sajt.py).
STRANICE = ["/", "/kako-radi", "/funkcionalnosti", "/za-advokate", "/bezbednost", "/beta"]

# Stare adrese bez sopstvene stranice → 301 na stranicu koja ih nasleđuje.
POVUCENE = {
    "/sposobnosti": "/funkcionalnosti", "/platforma": "/kako-radi", "/kontakt": "/beta", "/razvoj": "/funkcionalnosti",
    "/web3": "/", "/vizija": "/", "/tehnologija": "/",
}

# Ulaz u aplikaciju: `/app` (founder). Isključen V2 primarni prekidač → legacy
# aplikacija sa prijavom; uključen → V2, koji prijavu vodi kroz /app-legacy.
APP_ULAZ = "/app"

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


def _cist_tekst(klijent, ruta: str) -> str:
    """Vidljiv tekst bez HTML oznaka, sa sažetim razmakom.

    Obavezno za poređenje REČENICA. Rečenica u HTML-u je prelomljena kroz redove
    i uvučena, pa doslovan podniz ne pogađa ništa — a `„Rezultat NE predstavlja
    potpunu blockchain forenzičku analizu."` na stranici JESTE, samo u dva reda.
    Prva verzija ovog testa je zbog toga prijavila lažan pad.
    """
    telo = re.sub(r"<[^>]+>", " ", _vidljivi_tekst(klijent, ruta))
    return re.sub(r"\s+", " ", telo)


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
    r = klijent.get("/static/site-v4.css")
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
    # NS004 founder lista: generičke i apsolutne tvrdnje.
    "budućnost prava",
    "revolucij",
    "transformacij",
    "najmoćniji",
    "najpametniji",
    "AI advokat",
    "nikada više",
    "nikad više",
    "sve što vam treba",
    "jedina platforma",
    "sve na jednom mestu",
    "AI-powered",
    "pokreće AI",
    "AI analizira",
    "propustite rok",
    "pratite rokove",
    "automatski prat",
    # Website V2 founder lista zabranjenih tvrdnji (bez svežeg dokaza).
    "manje od 10 sekundi",
    "nikad više nećete propustiti",
    "automatski šalje sva obaveštenja",
    "100% tačn",
    "AES-256",
    "potpuno GDPR",
    "sertifikovana bezbednost",
    "potpuno automatizovan",
    "donosi ispravne pravne odluke",
    "zamenjuje advokata",
    "najnaprednij",
    "uštedite",
    "hiljade zadovoljnih",
    "zadovoljnih korisnika",
    "najbolji pravni",
    "jedini sistem",
    "besplatno zauvek",
    "ograničeno na",
    "ograničen broj mesta",
    "transformacija advokature",
    "game changer",
    "pametniji od čoveka",
    "bez napora",
    "jednim klikom",
    "neverovatn",
    "naučio iz hiljada",
    "AI menja sve",
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

@pytest.mark.parametrize("ruta,cilj", sorted(POVUCENE.items()))
def test_povucena_stranica_trajno_preusmerava(klijent, ruta, cilj):
    """Stari linkovi i pretraživači ne pucaju, a stari sadržaj nije dostupan."""
    r = klijent.get(ruta, follow_redirects=False)
    assert r.status_code == 301, f"{ruta} vraća {r.status_code}"
    assert r.headers["location"] == cilj
    assert "<html" not in r.text.lower(), f"{ruta} i dalje šalje stari sadržaj"


def test_pocetna_ne_linkuje_povucene_stranice(klijent):
    telo = _tekst(klijent, "/")
    for ruta in POVUCENE:
        assert f'href="{ruta}"' not in telo, f"početna linkuje povučenu stranicu {ruta}"


def test_beta_forma_postoji_samo_na_stranici_beta(klijent):
    """Website V2: jedna prijavna putanja — /beta, POST /waitlist/prijava (sajt.js).
    Nijedna druga stranica nema formu."""
    for ruta in STRANICE:
        ima = "<form" in _tekst(klijent, ruta)
        assert ima == (ruta == "/beta"), f"{ruta}: forma {'postoji' if ima else 'ne postoji'}"
    telo = _tekst(klijent, "/beta")
    for polje in ('name="ime"', 'name="email"', 'name="firma"', 'name="telefon"', 'name="poruka"'):
        assert polje in telo, f"/beta nema polje {polje}"
    assert "/waitlist/prijava" in klijent.get("/v2/site/sajt.js").text


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


@pytest.mark.parametrize("ruta", STRANICE)
def test_sajt_ne_obecava_email_potvrdu(klijent, ruta):
    """SMTP se tiho preskače ako env nije podešen — sajt ne sme obećati mejl.
    Poruke ishoda beta prijave piše sajt.js, pa se meri i on."""
    tela = [_vidljivi_tekst(klijent, ruta).lower(), klijent.get("/v2/site/sajt.js").text.lower()]
    for telo in tela:
        for izraz in ("proverite inboks", "potvrda je poslata", "poslali smo vam mejl",
                      "poslali smo vam email", "proverite e-poštu", "dobićete potvrdu"):
            assert izraz not in telo, f"{ruta} obećava mejl koji možda nije poslat: {izraz!r}"


@pytest.mark.parametrize("ruta", STRANICE)
@pytest.mark.parametrize("izraz", [r"\bcen[aeu]\b", r"€", r"\bRSD\b",
                                  r"dinara\s+mesečno", r"pretplat"])
def test_sajt_ne_pominje_cenu(klijent, ruta, izraz):
    """Nijedan plan se ne može kupiti; sajt ne govori o ceni.

    Granica reči je obavezna: `cena` kao podniz pogađa `proCENAt` i `proCENA`.
    """
    telo = re.sub(r"<[^>]+>", " ", _vidljivi_tekst(klijent, ruta))
    assert not re.search(izraz, telo, re.I), f"{ruta} pominje {izraz!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. SEO
# ═══════════════════════════════════════════════════════════════════════════

def test_sitemap_navodi_pocetnu_i_pravne_a_ne_povucene(klijent):
    r = klijent.get("/sitemap.xml")
    assert r.status_code == 200
    from urllib.parse import urlparse
    lokacije = [urlparse(u).path or "/" for u in re.findall(r"<loc>([^<]+)</loc>", r.text)]
    for ruta in STRANICE:
        assert ruta in lokacije, f"sitemap ne navodi {ruta}"
    for ruta in ("/privacy", "/terms", "/security", "/dpa", "/ai-disclosure", "/bezbednosni-list"):
        assert ruta in lokacije, f"sitemap ne navodi {ruta}"
    for ruta in POVUCENE:
        assert ruta not in lokacije, f"sitemap oglašava povučenu stranicu {ruta}"


def test_robots_i_dalje_stiti_api(klijent):
    """Postojeći test (`test_api_security.py:121`) čuva ovaj ugovor — ovde se
    potvrđuje da ga dodavanje `Sitemap:` linije nije slomilo."""
    telo = klijent.get("/robots.txt").text
    assert "User-agent" in telo
    assert "/api/" in telo
    assert "Sitemap:" in telo

# ═══════════════════════════════════════════════════════════════════════════
# 7. PRISTUP APLIKACIJI — put od sajta do stvarnog proizvoda
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", STRANICE)
def test_svaka_stranica_nudi_ulaz_u_aplikaciju(klijent, ruta):
    """Poziv na akciju za ulaz u aplikaciju mora biti na SVAKOJ stranici.

    Sajt je nastao zamenom landinga koji je imao „POČNI BESPLATNO" kao jedini
    ulaz. Ta formulacija je uklonjena jer nije bila tačna — ali je sa njom
    nestao i svaki put do proizvoda. Posetilac koji već ima nalog nije imao gde
    da klikne.
    """
    assert f'href="{APP_ULAZ}"' in _tekst(klijent, ruta), (
        f"{ruta} nema poziv na akciju ka aplikaciji ({APP_ULAZ})"
    )


def test_ulaz_u_aplikaciju_vodi_na_zivu_rutu(klijent):
    """CTA ne sme voditi u prazno.

    `/app` mora stvarno da odgovori i da servira aplikaciju, ne stari landing.
    """
    r = klijent.get("/app")
    assert r.status_code == 200, f"/app vraća {r.status_code}"
    telo = r.text
    assert "setAuthMode" in telo or "#register" in telo, (
        "/app ne servira aplikaciju sa modalom za prijavu"
    )
    # Stari landing je obrisan; ako se ikad vrati na ovu rutu, ovo pada.
    assert "Počni besplatno" not in telo, "/app servira stari landing"


def test_registracija_je_stvarno_otvorena(klijent):
    """CTA „Otvori nalog" sme da postoji SAMO ako registracija radi.

    Mandat je izričit: ako registracija nije dostupna, dugme se ne prikazuje.
    Ovde se meri postojanje rute, ne njen ishod — poziv bez podataka mora vratiti
    422 (validacija), ne 404 (ruta ne postoji).
    """
    r = klijent.post("/api/register", json={})
    assert r.status_code != 404, "ruta /api/register ne postoji — ukloni CTA za nalog"
    assert r.status_code in (400, 422), f"neočekivan odgovor: {r.status_code}"


@pytest.mark.parametrize("ruta", STRANICE)
def test_pozivi_na_akciju_vode_samo_na_beta_ili_prijavu(klijent, ruta):
    """Website V2: primarni poziv je prijava za beta (/beta), sporedni je ulaz u
    aplikaciju (/app). Nijedno dugme ne vodi nigde drugde. Bez obećanja
    besplatnog ili automatskog naloga."""
    telo = _tekst(klijent, ruta)
    ulazi = set(re.findall(r'<a[^>]+class="dugme[^"]*"[^>]+href="([^"]+)"', telo))
    assert ulazi <= {APP_ULAZ, "/beta"} and ulazi, f"{ruta}: pozivi na akciju vode na {ulazi}"
    vidljivo = _vidljivi_tekst(klijent, ruta).lower()
    for izraz in ("besplatno", "odmah dobijate nalog", "automatski nalog"):
        assert izraz not in vidljivo, f"početna obećava nalog: {izraz!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. DIGITALNA IMOVINA (/web3)
# ═══════════════════════════════════════════════════════════════════════════

def test_web3_stranica_je_povucena_a_pocetna_je_ne_reklamira(klijent):
    """Digitalna imovina nema V2 korisnički tok u NS004 — stranica je povučena
    (301 na početnu), a početna je ne reklamira. Obim modula (usklađenost i
    provera porekla, nikad trgovanje) ostaje u proizvodu; sajt o njemu ćuti."""
    assert klijent.get("/web3", follow_redirects=False).status_code == 301
    for ruta in STRANICE:
        telo = _cist_tekst(klijent, ruta).lower()
        for izraz in ("web3", "digitalna imovina", "kripto", "blockchain", "trgovanj", "defi", "prinos"):
            assert izraz not in telo, f"{ruta} pominje {izraz!r}"



# ═══════════════════════════════════════════════════════════════════════════
# 9. UGOVOR SADRŽAJA — sajt kaže tačno ono što registar kaže (Website V2)
# ═══════════════════════════════════════════════════════════════════════════
#
# `site/funkcije.json` je jedini izvor istine o funkcijama, statusu i dokazu
# (docs/website-v2/02_PRODUCT_CAPABILITY_TRUTH_MATRIX.md je izveden iz njega).
# Meri se ODGOVOR SERVERA: stavka koja postoji u registru a server je ne pošalje,
# ili stranica koja tvrdi nešto čega u registru nema, oba su pad.

import html as _html  # noqa: E402
import json  # noqa: E402

JAVNI_KATALOG = {"V2_AVAILABLE", "AVAILABLE_WITH_LIMITATIONS", "LEGACY_ONLY"}


def _registar():
    with open(os.path.join(_KOREN, "site", "funkcije.json"), encoding="utf-8") as f:
        return json.load(f)


def _html_tekst(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s)))


def _stavke(telo: str) -> dict:
    """{id: (status, vidljiv tekst stavke)} iz elemenata sa data-id."""
    out = {}
    obrazac = r'<(li|article) class="(?:stavka|plan)" id="f-[^"]+" data-id="([^"]+)" data-status="([^"]+)"[^>]*>(.*?)</\1>'
    for m in re.finditer(obrazac, telo, flags=re.S):
        out[m.group(2)] = (m.group(3), _html_tekst(m.group(4)))
    return out


def test_generisane_stranice_su_uskladjene_sa_izvorom():
    """Ručna izmena generisane stranice ili registra bez ponovne gradnje = pad."""
    sys.path.insert(0, os.path.join(_KOREN, "scripts"))
    import gradi_sajt
    for put, sadrzaj in gradi_sajt.izgradi().items():
        with open(put, "rb") as f:
            sacuvano = f.read().decode("utf-8").replace("\r\n", "\n")
        assert sacuvano == sadrzaj, f"{put} nije usklađen — pokrenite python scripts/gradi_sajt.py"


def test_registar_je_potpun_i_dosledan():
    reg = _registar()
    obavezno = {"id", "oblast", "naziv", "status", "radnja", "v2_ulaz", "backend", "pravo", "test", "ogranicenje",
                "podaci", "javno", "javni_opis", "izvor", "verifikovano"}
    ids = [f["id"] for f in reg["funkcije"]]
    assert len(ids) == len(set(ids)), "dupli ID u registru"
    oblasti = {o["id"] for o in reg["oblasti"]}
    for f in reg["funkcije"]:
        assert obavezno <= set(f), f"{f.get('id')}: nedostaju polja {obavezno - set(f)}"
        assert f["status"] in reg["statusi"], f"{f['id']}: nepoznat status"
        assert f["oblast"] in oblasti, f"{f['id']}: nepoznata oblast"
        if f["javno"]:
            assert f["javni_opis"].strip(), f"{f['id']}: javna stavka bez javne formulacije"
            assert reg["statusi"][f["status"]]["javno"], f"{f['id']}: status {f['status']} se ne sme prikazati javno"
        if f["status"] == "PLANNED_APPROVED" and f["javno"]:
            assert f.get("problem") and f.get("umesto"), f"{f['id']}: plan bez problema/zamene"
        if f["status"] == "AVAILABLE_WITH_LIMITATIONS":
            assert f["ogranicenje"].strip(), f"{f['id']}: „uz ograničenje“ bez navedenog ograničenja"


def test_katalog_prikazuje_tacno_javne_funkcije_sa_tacnim_statusom(klijent):
    reg = _registar()
    na_sajtu = _stavke(_tekst(klijent, "/funkcionalnosti"))
    ocekivano = {f["id"]: f for f in reg["funkcije"] if f["javno"] and f["status"] in JAVNI_KATALOG}
    assert set(na_sajtu) == set(ocekivano), (
        f"nedostaje: {sorted(set(ocekivano) - set(na_sajtu))}; višak: {sorted(set(na_sajtu) - set(ocekivano))}")
    for fid, (status, tekst) in na_sajtu.items():
        f = ocekivano[fid]
        assert status == f["status"], f"{fid}: status na sajtu {status}, u registru {f['status']}"
        assert reg["statusi"][status]["javno"] in tekst, f"{fid}: nema vidljive oznake statusa"
        # Ograničenje je deo javne formulacije — ne sme se izgubiti putem.
        assert re.sub(r"\s+", " ", f["javni_opis"]) in tekst, f"{fid}: javna formulacija nije prikazana u celosti"


def test_razvoj_nije_javna_roadmap_stranica(klijent):
    """Razvojna mapa ne izlaže planove konkurenciji kroz javnu rutu."""
    r = klijent.get("/razvoj", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/funkcionalnosti"
    for ruta in STRANICE:
        t = _tekst(klijent, ruta)
        assert 'href="/razvoj"' not in t
    assert "/razvoj" not in klijent.get("/sitemap.xml").text


@pytest.mark.parametrize("ruta", STRANICE)
def test_nijedna_neobjavljiva_funkcija_nije_na_sajtu(klijent, ruta):
    """IMPLEMENTED_NOT_EXPOSED, EXPERIMENTAL, UNVERIFIED_OR_REJECTED i stavke sa
    javno=false ne pojavljuju se ni kao stavka ni po nazivu; plan nikad nije u katalogu."""
    reg = _registar()
    stavke = _stavke(_tekst(klijent, ruta))
    vidljivo = _cist_tekst(klijent, ruta).lower()
    for f in reg["funkcije"]:
        if not f["javno"] or not reg["statusi"][f["status"]]["javno"]:
            assert f["id"] not in stavke, f"{ruta} prikazuje neobjavljivu stavku {f['id']}"
            assert f["naziv"].lower() not in vidljivo, f"{ruta} pominje neobjavljivu funkciju {f['naziv']!r}"
        if f["status"] == "PLANNED_APPROVED" and ruta == "/funkcionalnosti":
            assert f["id"] not in stavke, f"plan {f['id']} prikazan u katalogu dostupnih funkcija"


@pytest.mark.parametrize("ruta", STRANICE)
def test_nema_izmisljene_socijalne_potvrde(klijent, ruta):
    """Nema preporuka, ocena, broja korisnika ni strukturisanih podataka o oceni."""
    telo = _tekst(klijent, ruta)
    vidljivo = _cist_tekst(klijent, ruta).lower()
    for izraz in ("★", "korisnika koristi", "kancelarija koristi", "preporučuju", "recenzij", "partneri", "rekli su"):
        assert izraz not in vidljivo, f"{ruta}: {izraz!r}"
    assert "aggregateRating" not in telo and '"Review"' not in telo


@pytest.mark.parametrize("ruta", STRANICE)
def test_svaki_snimak_je_oznacen_kao_demonstracioni(klijent, ruta):
    telo = _tekst(klijent, ruta)
    for fig in re.findall(r'<figure class="snimak[^"]*">.*?</figure>', telo, flags=re.S):
        assert "Demonstracioni prikaz" in fig and "izmišljen" in fig, f"{ruta}: snimak bez oznake demonstracionog prikaza"


@pytest.mark.parametrize("ruta", STRANICE)
def test_slike_postoje_i_imaju_opis_i_dimenzije(klijent, ruta):
    for img in re.findall(r"<img\b[^>]*>", _tekst(klijent, ruta)):
        src = re.search(r'src="([^"]+)"', img).group(1)
        assert 'alt="' in img and 'width="' in img and 'height="' in img, f"{ruta}: {img[:80]}"
        assert klijent.get(src).status_code == 200, f"{ruta}: slika {src} ne postoji"


@pytest.mark.parametrize("ruta", STRANICE)
def test_svi_unutrasnji_linkovi_rade(klijent, ruta):
    """Nema mrtvih linkova: svaka unutrašnja adresa posle preusmerenja odgovara 200."""
    for href in set(re.findall(r'href="(/[^"#]*)', _tekst(klijent, ruta))):
        r = klijent.get(href, follow_redirects=True)
        assert r.status_code == 200, f"{ruta}: link {href} → {r.status_code}"


@pytest.mark.parametrize("ruta", STRANICE)
def test_sidra_unutar_sajta_postoje(klijent, ruta):
    for strana, sidro in set(re.findall(r'href="(/[^"#]*)#([^"]+)"', _tekst(klijent, ruta))):
        assert f'id="{sidro}"' in _tekst(klijent, strana or ruta), f"{ruta}: sidro {strana}#{sidro} ne postoji"


def test_naslovi_i_opisi_su_jedinstveni_a_canonical_tacan(klijent):
    naslovi, opisi = set(), set()
    for ruta in STRANICE:
        telo = _tekst(klijent, ruta)
        naslov = re.search(r"<title>([^<]+)</title>", telo).group(1)
        opis = re.search(r'<meta name="description" content="([^"]+)"', telo).group(1)
        assert naslov not in naslovi and opis not in opisi, f"{ruta}: ponovljen naslov ili opis"
        naslovi.add(naslov)
        opisi.add(opis)
        assert f'<link rel="canonical" href="https://vindex.rs{ruta}">' in telo
        assert f'<meta property="og:url" content="https://vindex.rs{ruta}">' in telo


def test_stil_skript_i_snimci_su_dostupni_bez_legacy_kesa(klijent):
    """Asseti sajta žive pod /v2/site/, koje legacy /sw.js preskače."""
    for put, tip in (("/v2/site/sajt.css", "text/css"), ("/v2/site/sajt.js", "javascript"),
                     ("/v2/site/snimci/registar.webp", "image/webp"), ("/v2/site/potpis.js", "javascript")):
        r = klijent.get(put)
        assert r.status_code == 200 and tip in r.headers["content-type"], put
    assert 'url.pathname.startsWith("/v2/")' in klijent.get("/sw.js").text


def test_stare_adrese_koje_sada_imaju_stranicu_ne_preusmeravaju(klijent):
    for ruta in ("/kako-radi", "/za-advokate", "/bezbednost", "/beta"):
        r = klijent.get(ruta, follow_redirects=False)
        assert r.status_code == 200 and "<h1" in r.text, ruta


def test_beta_prijava_neuspeh_baze_nije_uspeh():
    """Kada upis ne uspe, server ne sme vratiti ok:true (sajt bi prikazao uspeh)."""
    from unittest.mock import MagicMock, patch
    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    supa.table.return_value.insert.return_value.execute.side_effect = RuntimeError("baza nedostupna")
    k = TestClient(api.app, raise_server_exceptions=False)
    with patch("routers.waitlist._get_supa", return_value=supa):
        r = k.post("/waitlist/prijava", json={"ime": "Test", "email": "neuspeh.website@example.com"})
    assert r.status_code >= 500
    assert '"ok":true' not in r.text.replace(" ", "")


def test_beta_prijava_sa_neispravnom_adresom_je_422(klijent):
    r = klijent.post("/waitlist/prijava", json={"ime": "Test", "email": "nije-adresa"})
    assert r.status_code == 422
    assert any("email" in (d.get("loc") or []) for d in r.json()["detail"])


# ═══════════════════════════════════════════════════════════════════════════
# 10. PRE-AUTH ULAZ (/app-legacy — kuda V2 /app šalje neprijavljenog korisnika)
# ═══════════════════════════════════════════════════════════════════════════

def _pre_auth_ulaz(klijent) -> str:
    telo = _vidljivi_tekst(klijent, "/app-legacy")
    m = re.search(r'<div id="vx-landing" class="vx-landing vxp">(.*?)\n</div>\n', telo, flags=re.S)
    assert m, "pre-auth ulaz (#vx-landing.vxp) nije pronađen"
    return m.group(1)


def test_pre_auth_ulaz_nema_zastarelih_tvrdnji(klijent):
    ulaz = _pre_auth_ulaz(klijent)
    tekst = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", ulaz)).lower()
    for izraz in ZABRANJENO + ["847", "10 sekundi", "aes", "obaveštenja 7", "ograničen broj", "besplatn",
                               "dohvat ruke", "operativni sistem", "radi umesto vas"]:
        assert izraz.lower() not in tekst, f"pre-auth ulaz sadrži {izraz!r}"


def test_pre_auth_ulaz_cuva_ugovor_prijave_i_vodi_na_beta(klijent):
    ulaz = _pre_auth_ulaz(klijent)
    assert 'id="nav-cta-btn"' in ulaz and "openModal()" in ulaz, "prijava mora ostati postojeći modal"
    assert 'href="/beta"' in ulaz
    assert "/v2/site/brand/Vindex_Transparent_EXACT_LOOK.svg" in ulaz
    telo = _tekst(klijent, "/app-legacy")
    assert '<div class="modal-title" id="auth-modal-title">Dobrodošli.</div>' in telo
    assert "15 besplatnih upita.</div>" not in telo, "početni naslov modala prijave ne sme biti tekst registracije"


def test_nova_pozicija_i_rani_pristup(klijent):
    pocetna = _tekst(klijent, "/")
    assert "Više vremena za odluke" in pocetna
    assert "Prijavi se za rani pristup" in pocetna
    assert 'id="sektori"' in pocetna
    assert "potencijalne profesionalne scenarije" in pocetna
    assert "nije samo AI odgovor" not in pocetna.lower()  # ne tvrditi neupotrebljivu superlativnu prednost
    bezbednost = _tekst(klijent, "/bezbednost")
    for provider in ("Supabase", "Render", "Pinecone", "OpenAI API"):
        assert provider in bezbednost
    assert "Originalni PDF/DOCX fajlovi nisu deo" in bezbednost
    assert "bezbedniji od ChatGPT Business/Enterprise" in bezbednost
