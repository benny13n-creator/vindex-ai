# -*- coding: utf-8 -*-
"""Settings Master Sprint P1.6 — GET/POST /api/sef/podesavanja nad lažnom bazom vernom postgrest 2.28.3.

Ranije (dokazano): bez reda `maybe_single().execute()` vraća None → `.data` AttributeError →
  * GET je to hvatao i vraćao „nije konfigurisano“ + pogrešnu poruku „tabela ne postoji — pokrenite migraciju“;
    istom granom je SVAKA greška baze izgledala kao „nije konfigurisano“ (lažno prazno stanje);
  * POST bez ključa pri prvom čuvanju → 500 „DB greška: 'NoneType' ...“ (sirov izuzetak u odgovoru) umesto 422.
Pregled ključa u pregledaču je nosio 8 znakova tajne (prva 4 + poslednja 4); sada samo poslednja 4."""
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

UID = "u-sef"
KLJUC = "SEFKEY-abcdefgh-12345678-WXYZ"


class _Upit:
    def __init__(self, baza):
        self.b, self.jedan, self.red = baza, False, None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self

    def maybe_single(self):
        self.jedan = True
        return self

    def upsert(self, red, **k):
        self.red = red
        return self

    def execute(self):
        if self.b.puca:
            raise RuntimeError("connection reset by peer; host=db.internal password=***")
        if self.red is not None:
            self.b.red = dict(self.red)
            return types.SimpleNamespace(data=[self.b.red])
        if self.b.red is None:
            return None                      # postgrest 2.28.3
        return types.SimpleNamespace(data=dict(self.b.red))


class _Baza:
    def __init__(self, red=None):
        self.red, self.puca = red, False

    def table(self, ime):
        return _Upit(self)


@pytest.fixture
def klijent(monkeypatch):
    import routers.sef as sef
    from shared.deps import get_current_user
    from shared.rate import limiter
    baza = _Baza()
    monkeypatch.setattr(sef, "_get_supa", lambda: baza)
    monkeypatch.setattr(sef, "encrypt_field", lambda v: "enc_v1:" + v[::-1])
    monkeypatch.setattr(sef, "decrypt_field", lambda v: v[len("enc_v1:"):][::-1])
    monkeypatch.setattr(limiter, "enabled", False)
    app = FastAPI()
    app.include_router(sef.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": UID, "email": "sef@example.invalid"}
    return TestClient(app, raise_server_exceptions=False), baza


TELO = {"seller_pib": "123456789", "seller_naziv": "Advokat Test", "seller_adresa": "Ulica 1", "seller_mesto": "Beograd"}


def test_bez_reda_nije_konfigurisano_bez_lazne_poruke_o_migraciji(klijent):
    k, _ = klijent
    r = k.get("/api/sef/podesavanja")
    assert r.status_code == 200 and r.json() == {"konfigurisano": False, "podaci": None}


def test_greska_baze_nije_prazno_stanje(klijent):
    k, baza = klijent
    baza.puca = True
    r = k.get("/api/sef/podesavanja")
    assert r.status_code == 503 and "konfigurisano" not in r.json()
    assert "password" not in r.text and "db.internal" not in r.text


def test_prvo_cuvanje_bez_kljuca_je_422_ne_500(klijent):
    k, baza = klijent
    r = k.post("/api/sef/podesavanja", json=TELO)
    assert r.status_code == 422 and baza.red is None


def test_cuvanje_sifruje_kljuc_a_pregled_nosi_samo_poslednja_4_znaka(klijent):
    k, baza = klijent
    assert k.post("/api/sef/podesavanja", json={**TELO, "api_key": KLJUC}).status_code == 200
    assert baza.red["api_key"].startswith("enc_v1:") and KLJUC not in baza.red["api_key"]
    r = k.get("/api/sef/podesavanja")
    assert r.status_code == 200
    pregled = r.json()["podaci"]["api_key_preview"]
    assert pregled == "***WXYZ"
    assert KLJUC[:4] not in r.text and KLJUC not in r.text


def test_cuvanje_bez_kljuca_zadrzava_postojeci(klijent):
    k, baza = klijent
    k.post("/api/sef/podesavanja", json={**TELO, "api_key": KLJUC})
    sifrovan = baza.red["api_key"]
    assert k.post("/api/sef/podesavanja", json={**TELO, "seller_naziv": "Novo ime"}).status_code == 200
    assert baza.red["api_key"] == sifrovan and baza.red["seller_naziv"] == "Novo ime"


def test_greska_upisa_ne_vraca_sirov_izuzetak(klijent):
    k, baza = klijent
    baza.puca = True
    r = k.post("/api/sef/podesavanja", json={**TELO, "api_key": KLJUC})
    assert r.status_code in (500, 503) and "password" not in r.text and "db.internal" not in r.text


@pytest.mark.parametrize("pib", ["12345678", "1234567890", "12345678a", ""])
def test_neispravan_pib_odbijen(klijent, pib):
    k, baza = klijent
    assert k.post("/api/sef/podesavanja", json={**TELO, "seller_pib": pib, "api_key": KLJUC}).status_code == 422 and baza.red is None


def test_nedesifrovan_kljuc_nije_prikazan_kao_upotrebljiv(klijent, monkeypatch):
    import routers.sef as sef
    k, baza = klijent
    baza.red = {"seller_pib": "123456789", "seller_naziv": "A", "seller_adresa": "", "seller_mesto": "",
                "api_key": "enc_v1:OSTECENO-abcd"}
    monkeypatch.setattr(sef, "decrypt_field", lambda v: (_ for _ in ()).throw(ValueError("los kljuc")))
    d = k.get("/api/sef/podesavanja").json()["podaci"]
    assert d["kljuc_citljiv"] is False and d["api_key_preview"] == "***" and "abcd" not in str(d)
