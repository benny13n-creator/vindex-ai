# -*- coding: utf-8 -*-
"""Settings Master Sprint P1.5 — routers/kancelarija.py nad lažnom bazom koja je VERNA postgrest 2.28.3.

PROBLEM (dokazano izvorom instalirane biblioteke, NS3-N15): `maybe_single().execute()` za 0 redova vraća
None. Svako `res.data` posle toga je AttributeError:
  * GET /api/kancelarija/moja → 503 za svakog ko NIJE administrator (samostalan advokat, član, pozvan);
  * POST /api/kancelarija/pozovi za novu adresu → 500;
  * nepostojeći/tuđ član → 500 umesto 404; ne-administrator na admin ruti → 500 umesto 403.
Ispravka vraća nameravane grane; autorizacija (`_require_firma_admin`, `.eq(kancelarija_id)`) se ne menja.
Dodato: naziv i uloga ostavljaju nepromenljiv trag (log_action), kao i prelazi mesta (SeatService).
"""
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ADMIN, CLAN, SOLO, POZVAN, DRUGI_ADMIN = "u-admin", "u-clan", "u-solo", "u-pozvan", "u-drugi"
EMAIL = {ADMIN: "admin@example.invalid", CLAN: "clan@example.invalid", SOLO: "solo@example.invalid",
         POZVAN: "pozvan@example.invalid", DRUGI_ADMIN: "drugi@example.invalid"}


class _Upit:
    def __init__(self, baza, tabela):
        self.b, self.t, self.f, self.jedan, self.izmena, self.kol = baza, tabela, [], False, None, "*"

    def select(self, kol="*", *a, **k):
        self.kol = kol
        return self

    def eq(self, k, v):
        self.f.append(lambda r: r.get(k) == v)
        return self

    def neq(self, k, v):
        self.f.append(lambda r: r.get(k) != v)
        return self

    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def maybe_single(self):
        self.jedan = True
        return self

    def update(self, polja):
        self.izmena = polja
        return self

    def insert(self, red):
        self.b.ubaci(self.t, red)
        self.izmena = "insert"
        return self

    def _redovi(self):
        return [r for r in self.b.t[self.t] if all(f(r) for f in self.f)]

    def execute(self):
        if self.izmena == "insert":
            return types.SimpleNamespace(data=[self.b.t[self.t][-1]])
        if self.izmena is not None:
            for r in self._redovi():
                r.update(self.izmena)
            self.b.izmene.append((self.t, dict(self.izmena)))
            return types.SimpleNamespace(data=self._redovi())
        redovi = [dict(r) for r in self._redovi()]
        if "kancelarije(*)" in self.kol:
            for r in redovi:
                r["kancelarije"] = next((k for k in self.b.t["kancelarije"] if k["id"] == r["kancelarija_id"]), None)
        if self.jedan:
            if not redovi:
                return None                      # postgrest 2.28.3 — NIJE objekat sa .data = None
            return types.SimpleNamespace(data=redovi[0])
        return types.SimpleNamespace(data=redovi)


class _Baza:
    def __init__(self):
        self.izmene = []
        self.t = {
            "kancelarije": [{"id": "k-1", "naziv": "Kancelarija Jedan", "admin_uid": ADMIN, "created_at": "2026-09-01"},
                            {"id": "k-2", "naziv": "Tuđa kancelarija", "admin_uid": DRUGI_ADMIN, "created_at": "2026-09-01"}],
            "kancelarija_clanovi": [
                {"id": "c-1", "kancelarija_id": "k-1", "email": EMAIL[CLAN], "uloga": "saradnik", "status": "ACTIVE", "user_id": CLAN},
                {"id": "c-2", "kancelarija_id": "k-1", "email": EMAIL[POZVAN], "uloga": "partner", "status": "INVITED", "user_id": None},
                {"id": "c-tudji", "kancelarija_id": "k-2", "email": "tudji@example.invalid", "uloga": "saradnik", "status": "ACTIVE", "user_id": "u-x"},
            ],
        }

    def ubaci(self, tabela, red):
        red = dict(red)
        red.setdefault("id", f"novi-{len(self.t[tabela])}")
        self.t[tabela].append(red)

    def table(self, ime):
        return _Upit(self, ime)


@pytest.fixture
def okruzenje(monkeypatch):
    import routers.kancelarija as kr
    from shared.deps import get_current_user
    from shared.rate import limiter
    baza, trag, prelazi = _Baza(), [], []
    monkeypatch.setattr(kr, "_get_supa", lambda: baza)
    monkeypatch.setattr(limiter, "enabled", False)

    async def _log(akcija, **kw):
        trag.append((akcija, kw))
        return "id"
    monkeypatch.setattr(kr, "log_action", _log, raising=False)

    async def _mesto(*a, **k):
        return {}

    async def _prelaz(**kw):
        prelazi.append(kw)
    monkeypatch.setattr(kr.SeatService, "assert_seat_available", staticmethod(_mesto))
    monkeypatch.setattr(kr.SeatService, "transition", staticmethod(_prelaz))
    app = FastAPI()
    app.include_router(kr.router)
    korisnik = {"uid": SOLO}
    app.dependency_overrides[get_current_user] = lambda: {"user_id": korisnik["uid"], "email": EMAIL[korisnik["uid"]]}
    k = TestClient(app, raise_server_exceptions=False)

    def kao(uid):
        korisnik["uid"] = uid
        return k
    return types.SimpleNamespace(kao=kao, baza=baza, trag=trag, prelazi=prelazi)


# ─── GET /moja: svaka uloga dobija svoju granu, ne 503 ───────────────────────

def test_samostalan_advokat_nema_kancelariju_a_ne_gresku(okruzenje):
    r = okruzenje.kao(SOLO).get("/api/kancelarija/moja")
    assert r.status_code == 200 and r.json() == {"status": "no_firma"}


def test_clan_vidi_svoju_kancelariju_i_ulogu(okruzenje):
    r = okruzenje.kao(CLAN).get("/api/kancelarija/moja")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "aktivan" and d["moja_uloga"] == "saradnik" and d["firma"]["id"] == "k-1"
    assert all(c["email"] != "tudji@example.invalid" for c in d["clanovi"])


def test_pozvan_vidi_poziv(okruzenje):
    r = okruzenje.kao(POZVAN).get("/api/kancelarija/moja")
    assert r.status_code == 200 and r.json()["status"] == "pending_invite" and r.json()["firma_naziv"] == "Kancelarija Jedan"


def test_administrator_vidi_samo_svoje_clanove(okruzenje):
    d = okruzenje.kao(ADMIN).get("/api/kancelarija/moja").json()
    assert d["moja_uloga"] == "admin" and {c["id"] for c in d["clanovi"]} == {"c-1", "c-2"}


# ─── Admin rute: ne-administrator 403, tuđ član 404, bez upisa ───────────────

ADMIN_RUTE = [
    ("put", "/api/kancelarija/naziv", {"naziv": "Novo ime"}),
    ("put", "/api/kancelarija/uloga/c-1", {"uloga": "partner"}),
    ("post", "/api/kancelarija/suspenduj/c-1", None),
    ("post", "/api/kancelarija/reaktiviraj/c-1", None),
    ("delete", "/api/kancelarija/ukloni/c-1", None),
    ("post", "/api/kancelarija/pozovi", {"email": "novi@example.invalid", "uloga": "saradnik"}),
]


@pytest.mark.parametrize("ko", [CLAN, SOLO, POZVAN])
@pytest.mark.parametrize("metod,putanja,telo", ADMIN_RUTE)
def test_ne_administrator_dobija_403_i_nista_se_ne_menja(okruzenje, ko, metod, putanja, telo):
    k = okruzenje.kao(ko)
    r = getattr(k, metod)(putanja, json=telo) if telo is not None else getattr(k, metod)(putanja)
    assert r.status_code == 403, (r.status_code, r.text)
    assert okruzenje.baza.izmene == [] and okruzenje.prelazi == [] and okruzenje.trag == []


@pytest.mark.parametrize("metod,putanja,telo", [
    ("put", "/api/kancelarija/uloga/c-tudji", {"uloga": "partner"}),
    ("post", "/api/kancelarija/suspenduj/c-tudji", None),
    ("post", "/api/kancelarija/reaktiviraj/c-tudji", None),
    ("delete", "/api/kancelarija/ukloni/c-tudji", None),
    ("put", "/api/kancelarija/uloga/ne-postoji", {"uloga": "partner"}),
    ("delete", "/api/kancelarija/ukloni/ne-postoji", None),
])
def test_administrator_ne_dira_clana_druge_kancelarije_404(okruzenje, metod, putanja, telo):
    k = okruzenje.kao(ADMIN)
    r = getattr(k, metod)(putanja, json=telo) if telo is not None else getattr(k, metod)(putanja)
    assert r.status_code == 404, (r.status_code, r.text)
    assert okruzenje.baza.izmene == [] and okruzenje.prelazi == []
    assert next(c for c in okruzenje.baza.t["kancelarija_clanovi"] if c["id"] == "c-tudji")["uloga"] == "saradnik"


def test_poziv_nove_adrese_radi(okruzenje):
    r = okruzenje.kao(ADMIN).post("/api/kancelarija/pozovi", json={"email": "Novi@Example.invalid ", "uloga": "citanje"})
    assert r.status_code == 201, r.text
    assert r.json() == {"ok": True, "action": "invited", "email": "novi@example.invalid", "uloga": "citanje"}
    assert okruzenje.prelazi[-1]["action"] == "invite" and okruzenje.prelazi[-1]["kancelarija_id"] == "k-1"


@pytest.mark.parametrize("uloga", ["admin", "vlasnik", "", "ADMIN"])
def test_uloga_admin_ili_nepoznata_odbijena(okruzenje, uloga):
    k = okruzenje.kao(ADMIN)
    assert k.put("/api/kancelarija/uloga/c-1", json={"uloga": uloga}).status_code == 422
    assert k.post("/api/kancelarija/pozovi", json={"email": "x@example.invalid", "uloga": uloga}).status_code == 422
    assert okruzenje.baza.izmene == []


def test_promena_uloge_upisuje_samo_u_svoju_kancelariju_i_ostavlja_trag(okruzenje):
    r = okruzenje.kao(ADMIN).put("/api/kancelarija/uloga/c-1", json={"uloga": "partner"})
    assert r.status_code == 200 and r.json() == {"ok": True, "uloga": "partner"}
    assert next(c for c in okruzenje.baza.t["kancelarija_clanovi"] if c["id"] == "c-1")["uloga"] == "partner"
    (akcija, kw), = okruzenje.trag
    assert akcija == "kancelarija_uloga_promena" and kw["user_id"] == ADMIN and kw["resource_id"] == "c-1"
    assert kw["metadata"] == {"kancelarija_id": "k-1", "clan_email": EMAIL[CLAN], "stara_uloga": "saradnik", "nova_uloga": "partner"}


def test_promena_naziva_ostavlja_trag(okruzenje):
    r = okruzenje.kao(ADMIN).put("/api/kancelarija/naziv", json={"naziv": "  Kancelarija Dva  "})
    assert r.status_code == 200 and r.json() == {"ok": True, "naziv": "Kancelarija Dva"}
    assert okruzenje.baza.t["kancelarije"][0]["naziv"] == "Kancelarija Dva"
    assert okruzenje.baza.t["kancelarije"][1]["naziv"] == "Tuđa kancelarija"
    (akcija, kw), = okruzenje.trag
    assert akcija == "kancelarija_naziv_promena" and kw["metadata"] == {"stari_naziv": "Kancelarija Jedan", "novi_naziv": "Kancelarija Dva"}


def test_administrator_ne_uklanja_sebe(okruzenje):
    okruzenje.baza.t["kancelarija_clanovi"].append({"id": "c-ja", "kancelarija_id": "k-1", "email": EMAIL[ADMIN],
                                                    "uloga": "partner", "status": "ACTIVE", "user_id": ADMIN})
    assert okruzenje.kao(ADMIN).delete("/api/kancelarija/ukloni/c-ja").status_code == 400 and okruzenje.prelazi == []


def test_prihvati_bez_poziva_je_404_ne_500(okruzenje):
    assert okruzenje.kao(SOLO).post("/api/kancelarija/prihvati").status_code == 404
    assert okruzenje.kao(SOLO).post("/api/kancelarija/odbij").status_code == 404
    assert okruzenje.kao(SOLO).delete("/api/kancelarija/napusti").status_code == 404


def test_nove_akcije_su_registrovane_za_nepromenljiv_dnevnik():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert {"kancelarija_naziv_promena", "kancelarija_uloga_promena"} <= set(AUDITABLE_ACTIONS)
