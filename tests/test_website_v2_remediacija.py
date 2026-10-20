# -*- coding: utf-8 -*-
"""
Website V2 — završna remedijacija istinitosti (P0-A, P0-B).

P0-B: javna prijava za beta (`POST /waitlist/prijava`) ne sme otkriti da li je
adresa već na listi, kakav joj je status ili da li ima aktivan nalog. Odgovor
za novu i poznatu adresu mora biti isti, deduplikacija mora ostati, a dva
istovremena zahteva za istu adresu ne smeju dati dva upisa ni dva obaveštenja.

P0-A: javno dostupni pravni i bezbednosni dokumenti ne smeju tvrditi ono što
nije dokazano (backup na planu koji ga nema, potpisani DPA/SCC bez ugovora,
RLS kao jedina granica dok backend koristi servisni ključ, šifrovanje šire od
stvarnog obuhvata, penetracioni test koji ne postoji).

Baza je zamenjena lažnom PostgREST tabelom koja poštuje jedinstveni indeks
`lower(email)` iz migracije 055 — isto ponašanje koje produkcija ima.
"""
import asyncio
import os
import re
import sys
import threading
import time
from html import unescape
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Lažna `waitlist` tabela (PostgREST + jedinstveni indeks lower(email))
# ═══════════════════════════════════════════════════════════════════════════

class _Upit:
    def __init__(self, tabela, vrsta, red=None):
        self.t, self.vrsta, self.red, self.filteri = tabela, vrsta, red, []

    def select(self, *_a, **_k):
        return self

    def eq(self, kolona, vrednost):
        self.filteri.append(("eq", kolona, vrednost))
        return self

    def ilike(self, kolona, obrazac):
        self.filteri.append(("ilike", kolona, obrazac))
        return self

    def _pogodak(self, red):
        for vrsta, kolona, v in self.filteri:
            if vrsta == "eq" and red.get(kolona) != v:
                return False
            if vrsta == "ilike":
                # PostgREST ilike: `%` i `_` su džokeri, bez obzira na velika slova.
                rx = "^" + "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in v) + "$"
                if not re.match(rx, str(red.get(kolona, "")), flags=re.I):
                    return False
        return True

    def execute(self):
        t = self.t
        if t.kvar:
            raise t.kvar
        if self.vrsta == "select":
            with t.brava:
                procitano = [dict(r) for r in t.redovi if self._pogodak(r)]
            if t.barijera:
                t.barijera.wait()   # oba čitanja završena pre ijednog upisa
            return type("R", (), {"data": procitano})()
        with t.brava:
            if t.kvar_upisa:
                raise t.kvar_upisa
            if any(r["email"].lower() == self.red["email"].lower() for r in t.redovi):
                raise APIError({"code": "23505", "message": 'duplicate key value violates unique constraint "waitlist_email_idx"',
                                "details": None, "hint": None})
            t.redovi.append(dict(self.red))
            return type("R", (), {"data": [dict(self.red)]})()


class _Tabela:
    def __init__(self, redovi=()):
        self.redovi = [dict(r) for r in redovi]
        self.brava = threading.Lock()
        self.barijera = None
        self.kvar = None
        self.kvar_upisa = None

    def select(self, *_a, **_k):
        return _Upit(self, "select")

    def insert(self, red):
        return _Upit(self, "insert", red)


class _Supa:
    def __init__(self, tabela):
        self.tabela = tabela

    def table(self, ime):
        assert ime == "waitlist"
        return self.tabela


@pytest.fixture()
def baza():
    tabela = _Tabela()
    obavestenja = []
    with patch("routers.waitlist._get_supa", return_value=_Supa(tabela)), \
         patch("routers.waitlist._send_notification", side_effect=lambda p: obavestenja.append(p.email)):
        yield tabela, obavestenja


def _prijava(k, email, **dodatno):
    return k.post("/waitlist/prijava", json={"ime": "Test Testović", "email": email, **dodatno})


# ═══════════════════════════════════════════════════════════════════════════
# P0-B.1 — bez statusnog razlikovanja
# ═══════════════════════════════════════════════════════════════════════════

def test_nova_adresa_se_upisuje_jednom_uz_jedno_obavestenje(baza):
    tabela, obavestenja = baza
    r = _prijava(TestClient(api.app), "nova.adresa@example.com", firma="K", telefon="1", poruka="p")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert [x["email"] for x in tabela.redovi] == ["nova.adresa@example.com"]
    time.sleep(0.2)
    assert obavestenja == ["nova.adresa@example.com"]


@pytest.mark.parametrize("status", ["pending", "contacted", "active"])
def test_poznata_adresa_dobija_isti_odgovor_kao_nova(baza, status):
    """Negativna kontrola: stari kod je za `active` vraćao „Vaš nalog je već
    aktivan“, a za ostale „Već ste na listi“ — oba se razlikuju od odgovora za
    novu adresu, pa ovaj test na starom kodu pada."""
    tabela, obavestenja = baza
    k = TestClient(api.app)
    nova = _prijava(k, "neko.drugi@example.com")
    tabela.redovi.append({"email": "poznata@example.com", "status": status})
    pre = len(tabela.redovi)
    time.sleep(0.2)
    obavestenja.clear()

    for varijanta in ("poznata@example.com", "  Poznata@Example.COM "):
        r = _prijava(k, varijanta.strip())
        assert r.status_code == nova.status_code == 200
        assert r.json() == nova.json(), f"status '{status}' se vidi u odgovoru: {r.json()} ≠ {nova.json()}"
        assert r.headers.get("content-length") == nova.headers.get("content-length")
    time.sleep(0.2)
    assert len(tabela.redovi) == pre, "poznata adresa je upisana ponovo"
    assert obavestenja == [], "za poznatu adresu je poslato novo obaveštenje"


def test_odgovor_ne_sadrzi_reci_o_nalogu_ili_listi(baza):
    tabela, _ = baza
    tabela.redovi.append({"email": "aktivan@example.com", "status": "active"})
    telo = _prijava(TestClient(api.app), "aktivan@example.com").text.lower()
    for rec in ("aktiv", "nalog", "već", "vec ", "listi", "status", "prijavite se"):
        assert rec not in telo, f"odgovor otkriva stanje adrese: '{rec}' u {telo}"


def test_dzoker_u_adresi_ne_pogadja_tudju_prijavu(baza):
    """`_` je u PostgREST `ilike` džoker: `a_b@` je stari kod tretirao kao već
    upisan `axb@` i nije sačuvao prijavu."""
    tabela, _ = baza
    tabela.redovi.append({"email": "axb@example.com", "status": "pending"})
    r = _prijava(TestClient(api.app), "a_b@example.com")
    assert r.status_code == 200
    assert "a_b@example.com" in [x["email"] for x in tabela.redovi], "nova adresa nije sačuvana"


def test_dve_istovremene_prijave_iste_adrese(baza):
    """Oba zahteva pročitaju praznu tabelu (barijera garantuje redosled), oba
    pokušaju upis; jedinstveni indeks odbije drugi. Oba moraju dobiti isti uspešan odgovor, upis i
    obaveštenje moraju biti po jedan."""
    tabela, obavestenja = baza
    tabela.barijera = threading.Barrier(2, timeout=10)

    async def dve():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            telo = {"ime": "Isti", "email": "ista@example.com"}
            return await asyncio.gather(c.post("/waitlist/prijava", json=telo),
                                        c.post("/waitlist/prijava", json=telo))

    a, b = asyncio.run(dve())
    assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)
    assert a.json() == b.json()
    assert len(tabela.redovi) == 1
    time.sleep(0.3)
    assert obavestenja == ["ista@example.com"]


# ═══════════════════════════════════════════════════════════════════════════
# P0-B.1 — greška nikad nije lažan uspeh
# ═══════════════════════════════════════════════════════════════════════════

def test_neispravna_adresa_je_422_bez_upisa(baza):
    tabela, _ = baza
    r = _prijava(TestClient(api.app), "nije-adresa")
    assert r.status_code == 422 and tabela.redovi == []


@pytest.mark.parametrize("gde", ["citanje", "upis"])
def test_nedostupna_baza_nije_uspeh(baza, gde):
    tabela, obavestenja = baza
    if gde == "citanje":
        tabela.kvar = RuntimeError("baza nedostupna")
    else:
        tabela.kvar_upisa = APIError({"code": "08006", "message": "connection failure", "details": None, "hint": None})
    r = _prijava(TestClient(api.app, raise_server_exceptions=False), "kvar@example.com")
    assert r.status_code >= 500
    assert '"ok":true' not in r.text.replace(" ", "")
    time.sleep(0.2)
    assert obavestenja == []


# ═══════════════════════════════════════════════════════════════════════════
# P0-B.2 — zaštita od zloupotrebe (postojeći globalni limit)
# ═══════════════════════════════════════════════════════════════════════════

def test_globalni_limit_stize_do_forme_i_ne_lomi_legitimnu_prijavu(baza):
    """Ruta nema sopstveni dekorator; SlowAPIMiddleware primenjuje
    `_DEFAULT_LIMITS` (60/hour po klijentu). Prva prijava prolazi, 61. sa iste
    adrese klijenta dobija 429 sa JSON telom, a ni jedan odbijen zahtev ne
    upisuje ništa."""
    from shared.rate import _DEFAULT_LIMITS, limiter
    assert _DEFAULT_LIMITS == ["60/hour"] and limiter.enabled
    tabela, _ = baza
    k = TestClient(api.app)
    prvi = _prijava(k, "limit0@example.com")
    assert prvi.status_code == 200
    for i in range(1, 60):
        assert _prijava(k, f"limit{i}@example.com").status_code == 200, i
    r = _prijava(k, "limit60@example.com")
    assert r.status_code == 429, r.status_code
    assert "greska" in r.json()
    assert len(tabela.redovi) == 60


# ═══════════════════════════════════════════════════════════════════════════
# P0-A — javni pravni i bezbednosni dokumenti
# ═══════════════════════════════════════════════════════════════════════════

DOKUMENTI = ["/privacy", "/security", "/dpa", "/bezbednosni-list", "/ai-disclosure", "/terms"]


@pytest.fixture(scope="module")
def tekstovi():
    k = TestClient(api.app)
    out = {}
    for ruta in DOKUMENTI:
        r = k.get(ruta)
        assert r.status_code == 200, ruta
        t = re.sub(r"<style.*?</style>|<script.*?</script>", " ", r.text, flags=re.S)
        t = unescape(re.sub(r"<[^>]+>", " ", t))
        out[ruta] = re.sub(r"\s+", " ", t)
    return out


# (opis, regex) — svaka stavka je tvrdnja koja je bila javna, a nije dokazana.
NEPODRZANO = [
    ("dnevni automatski backup", r"[Dd]nevni automatski backup|Automatski backup\s*Dnevno"),
    ("rok čuvanja backup-a", r"Backup\s*30 dana|Backup baze\s*30 dana|backup kopije baze.{0,120}30 dana"),
    ("PITR / RTO / RPO obećanje", r"Point-in-Time Recovery\s*Kontinualno|RTO: max|RPO: max"),
    ("potpisan DPA/SCC", r"DPA potpisan|SCC potpisan|SCC\) su potpisani"),
    ("SCC kao primenjen mehanizam", r"primenjuju se sledeće zaštitne mere|Ugovor: EU Standard Contractual|SAD — EU SCC garancije"),
    ("penetracioni test kao primenjena mera", r"[Rr]edovni bezbednosni pregledi i penetracioni testovi"),
    ("RLS kao apsolutna granica", r"čak i direktan DB pristup|greška u aplikativnom kodu ne može|isključivo sopstvenim podacima na nivou baze"),
    ("user_id u svakoj tabeli", r"Svaki red u svakoj tabeli"),
    ("Argon2id za lozinke", r"Lozinke se čuvaju isključivo kao Argon2id"),
    ("sva dokumenta klijenata šifrovana", r"Dokumenti klijenata se enkriptuju"),
    ("GDPR/ZZPL usklađen", r"GDPR \(EU\)\s*Usklađen|ZZPL \(Srbija\)\s*Usklađen"),
    ("zaposleni nemaju pristup", r"Zaposleni Pružaoca usluge nemaju pristup"),
    ("audit svih pristupa", r"Audit logging svih pristupa|Svaki pristup production bazi"),
    ("dvofaktorska prijava (ne postoji u aplikaciji)", r"[Dd]vofaktorska autentifikacija \(opciono\)|Opciona dvofaktorska autentifikacija"),
]


@pytest.mark.parametrize("opis,rx", NEPODRZANO, ids=[o for o, _ in NEPODRZANO])
def test_javni_dokumenti_nemaju_nepodrzanu_tvrdnju(tekstovi, opis, rx):
    nadjeno = {r: m.group(0) for r, t in tekstovi.items() if (m := re.search(rx, t))}
    assert not nadjeno, f"{opis}: {nadjeno}"


def test_dokumenti_kazu_stvarno_stanje_backup_a(tekstovi):
    for ruta in ("/privacy", "/security"):
        assert "ne uključuje automatske backup" in tekstovi[ruta], ruta


def test_dokumenti_kazu_granicu_servisnog_kljuca(tekstovi):
    for ruta in ("/privacy", "/security", "/bezbednosni-list"):
        assert "servisnim ključem" in tekstovi[ruta], ruta


def test_dokumenti_kazu_sta_nije_sifrovano(tekstovi):
    for ruta in ("/security", "/bezbednosni-list"):
        t = tekstovi[ruta]
        assert "klijentski portal" in t and "izdvojeni tekst" in t.lower(), ruta


def test_politika_privatnosti_opisuje_beta_prijavu(tekstovi):
    t = tekstovi["/privacy"]
    m = re.search(r"Prijava za beta testiranje(.*?)Rokovi čuvanja podataka", t)
    assert m, "Politika privatnosti nema odeljak o beta prijavi"
    o = m.group(1)
    for deo in ("ime", "adres", "kancelarij", "telefon", "poruk",       # podaci
                "svrh", "pravni osnov", "čuva", "briš",                 # svrha, osnov, čuvanje
                "Supabase", "e-pošte", "ne otvara nalog", "privacy@"):  # primaoci, granice, kanal
        assert deo.lower() in o.lower(), f"beta odeljak ne pominje: {deo}"
    assert "newsletter" not in o.lower() and "marketin" not in o.lower()


def test_beta_stranica_upucuje_na_odeljak_politike():
    k = TestClient(api.app)
    assert 'href="/privacy#beta-prijava"' in k.get("/beta").text
    assert 'id="beta-prijava"' in k.get("/privacy").text
