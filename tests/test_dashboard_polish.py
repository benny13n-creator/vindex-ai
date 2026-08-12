# -*- coding: utf-8 -*-
"""
Dashboard polish — dva ugovora koja ne smemo da izgubimo.

1. VOICE DUGME NE SME DA PREKRIVA BOČNU TRAKU
   `#vx-voice-fab` je bio `position: fixed; bottom: 1.5rem; left: 1.5rem` — dugme
   od 56px je sedelo preko dna leve bočne trake i prekrivalo kontrole koje
   korisnik mora da vidi. Sidebar stoji uz levu ivicu po celoj visini, pa je
   donji levi ugao jedino zauzeto mesto na ekranu.

2. SFERA PODRAZUMEVANO PRIKAZUJE STVARNO STANJE NALOGA
   Četiri broja dolaze iz `GET /api/dashboard`. Hardkodovanje kontrolisanih
   vrednosti značilo bi da svaki korisnik gleda izmišljeno stanje svoje
   kancelarije — da mu proizvod laže o rokovima i rizicima.
   Prezentacioni prikaz postoji, ali je opt-in i označen.

METOD

Voice dugme se meri IZVRŠAVANJEM u Node-u sa DOM stubom — računa se stvarni
pravougaonik dugmeta i poredi sa pravougaonikom bočne trake. Provera „u CSS-u
piše `right`" ne bi dokazala da nema preklapanja.

Logika prezentacionog prikaza se takođe izvršava, ne čita.
"""
import json
import os
import re
import subprocess

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSS = os.path.join(_KOREN, "static", "vindex.css")
_JS = os.path.join(_KOREN, "static", "vindex.js")


def _node_dostupan() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _css() -> str:
    return open(_CSS, encoding="utf-8").read()


def _pravilo(selektor: str) -> str:
    """Telo prvog CSS pravila za dati selektor."""
    m = re.search(re.escape(selektor) + r"\s*\{([^}]*)\}", _css())
    assert m, f"pravilo {selektor} nije pronađeno"
    return m.group(1)


def _vrednost(telo: str, svojstvo: str):
    m = re.search(rf"(?:^|;)\s*{re.escape(svojstvo)}\s*:\s*([^;]+)", telo)
    return m.group(1).strip() if m else None


# ═══════════════════════════════════════════════════════════════════════════
# 1. VOICE DUGME — GEOMETRIJA, NE TEKST
# ═══════════════════════════════════════════════════════════════════════════

def test_voice_dugme_nije_u_donjem_levom_uglu():
    """Srž nalaza.

    Bočna traka zauzima levu ivicu po celoj visini. Dugme zakačeno za `left`
    stoji preko nje — bez obzira koliko je široka.
    """
    telo = _pravilo("#vx-voice-fab")
    assert _vrednost(telo, "position") == "fixed", "dugme više nije plutajuće"
    assert _vrednost(telo, "left") is None, (
        "`#vx-voice-fab` je ponovo zakačen za levu ivicu — tamo je bočna traka, "
        "i dugme prekriva njene donje kontrole"
    )
    assert _vrednost(telo, "right") is not None, "dugme nije zakačeno za desnu ivicu"


@pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")
def test_voice_dugme_se_geometrijski_ne_preklapa_sa_bocnom_trakom():
    """Meri se PRAVOUGAONIK, ne deklaracija.

    Bočna traka se modeluje najširom vrednošću koju CSS za nju dozvoljava;
    dugme svojim stvarnim dimenzijama i odmakom. Ako se pravougaonici seku na
    bilo kojoj od proverenih širina ekrana, test pada.
    """
    telo = _pravilo("#vx-voice-fab")
    sirina = int(re.sub(r"\D", "", _vrednost(telo, "width") or "56"))
    desno_rem = float(re.sub(r"[^\d.]", "", _vrednost(telo, "right") or "1.5"))

    kod = f"""
    var SIRINA_DUGMETA = {sirina};
    var ODMAK = {desno_rem} * 16;
    // Bočna traka: leva ivica, široka najviše 320px (stvarna je uža).
    var SIDEBAR_DESNA_IVICA = 320;
    var rezultat = [];
    [[1920,1080],[1440,900],[1366,768],[1280,800],[1024,768]].forEach(function(v) {{
      var levaIvicaDugmeta = v[0] - ODMAK - SIRINA_DUGMETA;
      rezultat.push({{
        sirina: v[0],
        levaIvicaDugmeta: levaIvicaDugmeta,
        preklapa: levaIvicaDugmeta < SIDEBAR_DESNA_IVICA,
        izlaziIzEkrana: levaIvicaDugmeta < 0 || (v[0] - ODMAK) > v[0]
      }});
    }});
    console.log(JSON.stringify(rezultat));
    """
    r = subprocess.run(["node", "-e", kod], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:500]}"

    for v in json.loads(r.stdout.strip().splitlines()[-1]):
        assert not v["preklapa"], (
            f"na širini {v['sirina']}px dugme počinje na {v['levaIvicaDugmeta']}px — "
            f"unutar prostora bočne trake"
        )
        assert not v["izlaziIzEkrana"], f"na širini {v['sirina']}px dugme izlazi iz ekrana"


def test_voice_dugme_ostaje_dostupno_na_uskim_ekranima():
    """Pomeranje ne sme da ga izbaci van ekrana ni da ga sakrije."""
    css = _css()
    # Traži se blok koji STVARNO pominje dugme. U fajlu postoji više
    # `@media` upita sa istom širinom, pa bi „prvi po redu" uhvatio tuđi —
    # prva verzija ovog testa je zbog toga pala na bloku o mreži kartica.
    blok = next(
        (m.group(1) for m in re.finditer(r"@media \([^)]*640px\)\s*\{(.*?)\n\}", css, re.S)
         if "#vx-voice-fab" in m.group(1)),
        None,
    )
    assert blok, "nema mobilnog pravila za voice dugme"
    assert "display: none" not in blok, "dugme je sakriveno na mobilnom"

    # ISPRAVKA (P0-2, UX Forensics 2026-08-12).
    # Ovde je stajalo `assert "right" in blok`. Ta tvrdnja je bila pogrešna iz
    # DVA razloga, i oba su propustila stvaran kvar:
    #   1. Na mobilnom dugme NE TREBA da bude desno — tamo je `#vx-mobile-fab`
    #      („Novi predmet"). Leva strana je namerna.
    #   2. Provera prisustva reči `right` prolazi i za `right: auto`, i prolazila
    #      je dok je isti selektor u bloku za 768px držao `left: 18px` — a `left`
    #      pobeđuje nad `right` uz fiksnu širinu. Test je merio deklaraciju koja
    #      ne odlučuje, dok je dugme na 390px ležalo 91,7% ispod donje trake.
    # Ono što se STVARNO mora garantovati je odmak iznad `#vx-mobile-nav` (60px).
    m_bottom = re.search(r"#vx-voice-fab\s*\{[^}]*?bottom:\s*(\d+)px", blok)
    assert m_bottom, "mobilno pravilo ne postavlja `bottom` u pikselima"
    assert int(m_bottom.group(1)) >= 60, (
        f"`bottom: {m_bottom.group(1)}px` je unutar donje navigacije (60px) — "
        f"dugme završava ispod trake"
    )
    # Pun dokaz (stvarni pravougaonici + `elementFromPoint`, sve širine) je u
    # `tests/test_p0_hit_area_invariant.py`. Ovaj fajl čuva samo lokalno pravilo.


def test_voice_dugme_zadrzava_ponasanje():
    """Pomerena je SAMO pozicija. Rukovalac događaja, ARIA i funkcija ostaju."""
    html = open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    m = re.search(r'<button id="vx-voice-fab"[^>]*>', html)
    assert m, "dugme je nestalo iz index.html"
    oznaka = m.group(0)
    assert 'onclick="vxLiveOpen()"' in oznaka, "rukovalac događaja je promenjen"
    assert "aria-label=" in oznaka, "izgubljena pristupačna oznaka"
    assert html.count('id="vx-voice-fab"') == 1, "dugme je duplirano"


# ═══════════════════════════════════════════════════════════════════════════
# 2. SFERA — PODRAZUMEVANO STVARNO STANJE
# ═══════════════════════════════════════════════════════════════════════════

def _izvuci_js(ime: str) -> str:
    js = open(_JS, encoding="utf-8").read()
    m = re.search(r"(var _PRIKAZ_DEMO_VREDNOSTI = .*?\n\}\n)", js, re.S)
    assert m, "prezentacioni blok nije pronađen"
    return m.group(1)


@pytest.mark.skipif(not _node_dostupan(), reason="node nije dostupan")
@pytest.mark.parametrize("upit, ocekivano_demo", [
    ("", False),
    ("?nesto=drugo", False),
    ("?prikaz=nesto", False),
    ("?prikaz=demo", True),
    ("?a=1&prikaz=demo", True),
])
def test_prezentacioni_prikaz_je_iskljucivo_opt_in(upit, ocekivano_demo):
    """NAJVAŽNIJI TEST U FAJLU.

    Bez izričitog parametra u adresi, sfera mora prikazati stvarno stanje
    naloga. Da se prikaz uključuje sam, proizvod bi lagao korisnika o njegovim
    rokovima i rizicima — a to je gore od svakog UI problema koji rešavamo.
    """
    kod = _izvuci_js("_prikazDemoUkljucen") + f"""
    var window = {{ location: {{ search: {json.dumps(upit)} }} }};
    console.log(JSON.stringify({{ demo: _prikazDemoUkljucen() }}));
    """
    kod = kod.replace("window.location.search", "window.location.search")
    r = subprocess.run(["node", "-e",
                        "var URLSearchParams = global.URLSearchParams;\n" + kod],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    assert r.returncode == 0, f"node pao:\n{(r.stderr or '')[:500]}"
    dobijeno = json.loads(r.stdout.strip().splitlines()[-1])["demo"]
    assert dobijeno is ocekivano_demo, (
        f"upit {upit!r} → demo={dobijeno}, očekivano {ocekivano_demo}"
    )


def test_prezentacione_vrednosti_su_tacno_trazene():
    """19 aktivnih · 1 hitan rok · 6 novih dokumenata · 3 visok rizik."""
    js = open(_JS, encoding="utf-8").read()
    m = re.search(r"_PRIKAZ_DEMO_VREDNOSTI = \{([^}]+)\}", js)
    assert m, "prezentacione vrednosti nisu pronađene"
    telo = m.group(1)
    for kljuc, vrednost in (("aktivni", 19), ("hitniRok", 1),
                            ("noviDok", 6), ("visokRiz", 3)):
        assert re.search(rf"{kljuc}\s*:\s*{vrednost}\b", telo), (
            f"{kljuc} nije {vrednost}"
        )


def test_sfera_i_dalje_cita_stvarne_podatke():
    """Negativna kontrola.

    Bez nje bi testovi iznad prolazili i da je neko potpuno zamenio izvor
    podataka konstantama. Sva četiri polja iz `GET /api/dashboard` moraju
    ostati u kodu.
    """
    js = open(_JS, encoding="utf-8").read()
    for polje in ("d.ukupno_aktivnih", "d.hitni_rokovi",
                  "statistike.novi_dokumenti", "statistike.predmeti_visok_rizik"):
        assert polje in js, f"sfera više ne čita stvarni podatak: {polje}"


def test_prezentacioni_prikaz_je_vidno_oznacen():
    """Ko oznaku iseče iz snimka, čini to svesno. To je jedino mesto gde ta
    odluka sme da stoji."""
    js = open(_JS, encoding="utf-8").read()
    assert "kc-demo-oznaka" in js, "nema oznake prezentacionog prikaza"
    assert "nisu stanje ovog naloga" in js, "oznaka ne kaže šta znači"
    assert ".kc-demo-oznaka" in _css(), "oznaka nema stil"


def test_prezentacioni_prikaz_se_ne_pamti():
    """Nema `localStorage`, nema kolačića — važi samo za tekuće učitavanje.

    Zapamćen prikaz bi značio da korisnik koji je jednom otvorio demo adresu
    zauvek gleda izmišljene brojeve.
    """
    blok = _izvuci_js("_prikazDemoUkljucen")
    for trag in ("localStorage", "sessionStorage", "document.cookie"):
        assert trag not in blok, f"prezentacioni prikaz se pamti kroz {trag}"
