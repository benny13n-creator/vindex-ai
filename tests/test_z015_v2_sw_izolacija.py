# -*- coding: utf-8 -*-
"""
Z015 §11 — SERVICE WORKER: V2 IZOLACIJA, LEGACY NEPROMENJEN.

Kvar koji se ovde zatvara nije ocigledan iz koda:

  `static/sw.js` ima scope `/`, dakle presrece i `/app-v2`. Njegova grana za
  navigaciju pri padu mreze radi `caches.match("/offline")`, a `/offline`
  servira LEGACY `index.html`. Posledica: korisnik otvori `/app-v2` bez mreze
  i dobije STARI Vindex pod V2 adresom. To nije prazan ekran nego POGRESAN
  PROIZVOD, i gore je od greske jer izgleda kao da V2 radi.

  V2 je u Wave 1 online-only. Dozvoljen ishod je nativna mrezna greska.

Drugi deo ugovora je jednako vazan: legacy `/app` MORA zadrzati svoj offline
app-shell. Popravka koja bi usput ugasila legacy offline bila bi regresija na
proizvodu koji je danas jedini u upotrebi.

Zasto je test staticki: ponasanje service worker-a se ne moze pouzdano
izvrsiti u pytest procesu, a invarijanta koju cuvamo JESTE strukturna —
postojanje i POZICIJA grane. Ponasanje je dokazano u pregledacu i zabelezeno
u Z015 izvestaju (offline `/app-v2` -> mrezna greska; offline `/app` -> 200,
411 kB legacy shell).
"""
import os
import re

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SW = os.path.join(KOREN, "static", "sw.js")


def _izvor():
    with open(SW, encoding="utf-8") as f:
        return f.read()


def test_sw_ima_granu_za_app_v2():
    s = _izvor()
    assert '"/app-v2"' in s
    assert '"/app-v2/"' in s
    assert '"/v2/"' in s


def test_grana_stoji_PRE_navigacione_grane():
    """Ako bypass dodje POSLE `request.mode === 'navigate'`, navigacija na
    /app-v2 vec je presretnuta i grana je mrtva."""
    s = _izvor()
    i_bypass = s.index('url.pathname === "/app-v2"')
    i_nav = s.index('event.request.mode === "navigate"')
    assert i_bypass < i_nav, "V2 bypass mora stajati pre navigacione grane"


def test_grana_stoji_PRE_svake_grane_koja_odgovara():
    """Ista logika za API granu i staticku granu — obe rade respondWith."""
    s = _izvor()
    i_bypass = s.index('url.pathname === "/app-v2"')
    for grana in ['url.pathname.startsWith("/api/")', "stale-while-revalidate"]:
        if grana in s:
            assert i_bypass < s.index(grana), f"bypass mora biti pre: {grana}"


def test_bypass_ne_poziva_respondWith():
    """Bypass mora ostaviti zahtev pretrazivacu. Ako bi imao respondWith,
    service worker bi i dalje bio u putanji i mogao da vrati kes."""
    s = _izvor()
    poc = s.index('url.pathname === "/app-v2"')
    kraj = s.index("}", s.index("return;", poc))
    # Komentari se skidaju: rec "respondWith" sme da stoji u objasnjenju ZASTO
    # je grana prazna. Meri se kod, ne proza oko njega.
    isecak = " ".join(red.split("//")[0] for red in s[poc:kraj].splitlines())
    assert "respondWith" not in isecak
    assert "caches" not in isecak


def test_bypass_je_ogranicen_na_sopstveni_origin():
    s = _izvor()
    poc = max(0, s.index('url.pathname === "/app-v2"') - 300)
    assert "self.location.origin" in s[poc:s.index('url.pathname === "/app-v2"') + 200]


def test_legacy_offline_fallback_je_NETAKNUT():
    """Legacy /app mora zadrzati svoj app-shell pri padu mreze."""
    s = _izvor()
    assert 'caches.match("/offline")' in s
    assert '"/offline"' in s.split("const PRECACHE")[1][:400]


def test_navigaciona_grana_i_dalje_postoji_za_legacy():
    s = _izvor()
    i_nav = s.index('event.request.mode === "navigate"')
    isecak = s[i_nav:i_nav + 600]
    assert "respondWith" in isecak
    assert 'caches.match("/offline")' in isecak


def test_cache_name_je_podignut():
    """Pravilo repo-a: CACHE_NAME raste na svaki deploy koji dira frontend
    sloj. Ovde je diran sam service worker, pa stari kes mora biti odbacen."""
    m = re.search(r'const CACHE_NAME = "vindex-v(\d+)"', _izvor())
    assert m, "CACHE_NAME nije pronadjen"
    assert int(m.group(1)) > 148, "CACHE_NAME nije podignut iznad produkcionog v148"


def test_v2_dokument_ne_registruje_service_worker():
    """V2 ne sme sam da registruje SW — u Wave 1 je online-only. Sme samo da
    zatrazi azuriranje vec instaliranog legacy SW-a, da stara verzija bez
    bypass-a ne ostane aktivna."""
    with open(os.path.join(KOREN, "v2", "boot.js"), encoding="utf-8") as f:
        boot = f.read()
    assert "serviceWorker.register" not in boot
    assert "getRegistration" in boot and ".update()" in boot
