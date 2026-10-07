"""NS002 Task 4 — autoritativna summary projekcija `GET /api/predmeti?view=summary`.

Izvršava se STVARNA ruta `lista_predmeta` kroz TestClient. Zamenjeni su samo
rezultat prijave (`api._require_auth`) i Supabase klijent (`api._get_supa`) —
lažni klijent beleži projekciju i svaki `.eq()` filter i PUCA na svaki upis.

Dokazuje:
  • summary vraća tačno id, naziv, tip, status, broj_predmeta, created_at,
    updated_at, brisanje_zapoceto, tuzilac, tuzeni — bez case_dna i bez sud;
  • podrazumevani odgovor (bez view) je nepromenjen: select("*"), isti oblik;
  • vlasnik dolazi ISKLJUČIVO iz tokena; `?user_id=` iz klijenta nema autoritet;
  • status=aktivan se primenjuje na serveru;
  • `ukupno` i dalje broji i predmete u brisanju (globalni ugovor nepromenjen),
    a sami takvi predmeti se ne vraćaju;
  • nijedan upis.
"""
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api

SUMMARY = {"id", "naziv", "tip", "status", "broj_predmeta", "created_at", "updated_at",
           "brisanje_zapoceto", "tuzilac", "tuzeni"}
TOKENI = {"tok-A": "korisnik-A", "tok-B": "korisnik-B"}


def _red(vlasnik, i, status="aktivan", brisanje=None):
    return {"id": f"{vlasnik}-{i:03d}", "user_id": vlasnik, "naziv": f"Predmet {vlasnik} {i}", "tip": "parnicni",
            "status": status, "broj_predmeta": f"P {i}/2026", "tuzilac": f"Tužilac {i}", "tuzeni": f"Tuženi {i}",
            "opis": "x", "rizik": None, "created_at": f"2026-10-0{1 + i % 5}T10:00:00+00:00",
            "updated_at": "2026-10-06T10:00:00+00:00", "brisanje_zapoceto": brisanje,
            "case_dna": {"cinjenice": ["veliki objekat"] * 50}}


class _Upit:
    def __init__(self, baza, dnevnik):
        self.baza, self.dnevnik, self.filteri, self.opseg = baza, dnevnik, [], None

    def select(self, kolone, count=None):
        self.dnevnik.append(("select", kolone, count)); self.kolone = kolone; return self

    def eq(self, k, v):
        self.dnevnik.append(("eq", k, v)); self.filteri.append((k, v)); return self

    def ilike(self, k, v):
        self.dnevnik.append(("ilike", k, v)); return self

    def order(self, *a, **k):
        return self

    def range(self, a, b):
        self.opseg = (a, b); return self

    def limit(self, n):
        self.opseg = (0, n - 1); return self

    def execute(self):
        redovi = [r for r in self.baza if all(r.get(k) == v for k, v in self.filteri)]
        ukupno = len(redovi)
        if self.opseg:
            redovi = redovi[self.opseg[0]:self.opseg[1] + 1]
        if self.kolone != "*":
            polja = [c.strip() for c in self.kolone.split(",")]
            redovi = [{c: r.get(c) for c in polja} for r in redovi]
        return types.SimpleNamespace(data=redovi, count=ukupno)

    def __getattr__(self, ime):
        if ime in ("insert", "update", "upsert", "delete", "rpc"):
            raise AssertionError(f"UPIS je zabranjen: {ime}")
        raise AttributeError(ime)


class _Supa:
    def __init__(self, baza):
        self.baza, self.dnevnik, self.tabele = baza, [], []

    def table(self, ime):
        self.tabele.append(ime)
        return _Upit(self.baza, self.dnevnik)

    def rpc(self, *a, **k):
        raise AssertionError("rpc je zabranjen")


def _auth(authorization):
    if not authorization or not authorization.startswith("Bearer ") or authorization[7:] not in TOKENI:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return types.SimpleNamespace(id=TOKENI[authorization[7:]])


@pytest.fixture()
def okruzenje(monkeypatch):
    baza = ([_red("korisnik-A", i) for i in range(12)] + [_red("korisnik-B", i) for i in range(7)] +
            [_red("korisnik-A", 100 + i, status="zatvoren") for i in range(3)])
    supa = _Supa(baza)
    monkeypatch.setattr(api, "_get_supa", lambda: supa)
    monkeypatch.setattr(api, "_require_auth", _auth)
    try:
        api.limiter.reset()
    except Exception:
        pass
    return supa, baza, TestClient(api.app)


def _select(supa):
    return [d for d in supa.dnevnik if d[0] == "select"]


def test_summary_vraca_tacno_autoritativna_polja(okruzenje):
    supa, _, k = okruzenje
    r = k.get("/api/predmeti?view=summary&status=aktivan", headers={"Authorization": "Bearer tok-A"})
    assert r.status_code == 200
    kolone = {c.strip() for c in _select(supa)[0][1].split(",")}
    assert kolone == SUMMARY, kolone
    for p in r.json()["predmeti"]:
        assert set(p) == SUMMARY, set(p)


def test_summary_nema_case_dna_ni_sud(okruzenje):
    supa, _, k = okruzenje
    r = k.get("/api/predmeti?view=summary", headers={"Authorization": "Bearer tok-A"})
    projekcija = _select(supa)[0][1]
    assert "case_dna" not in projekcija and "sud" not in projekcija.split(",") and projekcija != "*"
    assert "case_dna" not in r.text


def test_podrazumevani_odgovor_nepromenjen(okruzenje):
    supa, _, k = okruzenje
    r = k.get("/api/predmeti", headers={"Authorization": "Bearer tok-A"})
    assert r.status_code == 200
    assert _select(supa)[0][1] == "*", "bez view mora ostati select('*')"
    assert set(r.json()) == {"predmeti", "ukupno", "limit", "offset"}
    assert "case_dna" in r.json()["predmeti"][0], "podrazumevani odgovor i dalje nosi sve kolone"


def test_vlasnik_samo_iz_tokena_user_id_parametar_nema_autoritet(okruzenje):
    supa, _, k = okruzenje
    r = k.get("/api/predmeti?view=summary&status=aktivan&user_id=korisnik-B", headers={"Authorization": "Bearer tok-A"})
    assert ("eq", "user_id", "korisnik-A") in supa.dnevnik
    assert ("eq", "user_id", "korisnik-B") not in supa.dnevnik
    assert r.json()["predmeti"] and all(p["id"].startswith("korisnik-A") for p in r.json()["predmeti"])


def test_aktivan_filter_na_serveru(okruzenje):
    supa, _, k = okruzenje
    r = k.get("/api/predmeti?view=summary&status=aktivan", headers={"Authorization": "Bearer tok-A"})
    assert ("eq", "status", "aktivan") in supa.dnevnik
    assert all(p["status"] == "aktivan" for p in r.json()["predmeti"])
    assert r.json()["ukupno"] == 12


def test_ukupno_i_dalje_broji_predmete_u_brisanju(okruzenje):
    supa, baza, k = okruzenje
    baza[0]["brisanje_zapoceto"] = "2026-10-06T10:00:00+00:00"
    r = k.get("/api/predmeti?view=summary&status=aktivan", headers={"Authorization": "Bearer tok-A"})
    telo = r.json()
    assert telo["ukupno"] == 12, "globalni `ukupno` ugovor je nepromenjen"
    assert len(telo["predmeti"]) == 11 and "korisnik-A-000" not in {p["id"] for p in telo["predmeti"]}


def test_bez_tokena_401_i_bez_upisa(okruzenje):
    supa, _, k = okruzenje
    assert k.get("/api/predmeti?view=summary").status_code == 401
    assert k.get("/api/predmeti?view=summary", headers={"Authorization": "Bearer lazni"}).status_code == 401
    assert supa.tabele == [], "bez prijave ne sme biti nijednog upita"
