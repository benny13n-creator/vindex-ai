"""NS004 — detalj predmeta i tekst dokumenta: tuđ/nepostojeći = 404, nikad podaci.

Izvršavaju se STVARNE rute `get_predmet` i `predmet_dokument_preview` kroz
TestClient. Zamenjeni su samo rezultat prijave i Supabase klijent. Lažni klijent
ponavlja ponašanje postgrest-a 2.28.3 (requirements: supabase==2.28.3):
`maybe_single()` vraća None kad red ne postoji, `single()` baca grešku — i puca
na svaki upis.

Dokazuje:
  • vlasnik čita svoj predmet; upit je ograničen na user_id iz tokena;
  • tuđ, nepostojeći i obrisan predmet → 404 (ranije 500 zbog None), bez podataka;
  • postojeće delegirano čitanje: aktivno → čitljivo, opozvano → 404 (ugovor nije proširen);
  • tekst dokumenta: samo vlasnik; tuđ dokument (i preko svog predmeta) → 404, bez teksta;
  • nijedan upis u podatke.
"""
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api

TOKENI = {"tok-A": "korisnik-A", "tok-B": "korisnik-B", "tok-D": "korisnik-D"}


def _p(vlasnik, i, brisanje=None):
    return {"id": f"{vlasnik}-{i}", "user_id": vlasnik, "naziv": f"Predmet {vlasnik} {i}", "status": "aktivan",
            "broj_predmeta": f"P {i}/2026", "brisanje_zapoceto": brisanje, "created_at": "2026-10-01T10:00:00+00:00"}


TABELE = {
    "predmeti": [_p("korisnik-A", 0), _p("korisnik-A", 1, brisanje="2026-10-05T00:00:00+00:00"), _p("korisnik-B", 0), _p("korisnik-B", 1)],
    "predmet_dokumenti": [
        {"id": "dA", "predmet_id": "korisnik-A-0", "user_id": "korisnik-A", "naziv_fajla": "a.pdf", "tekst_sadrzaj": "TEKST-A",
         "pinecone_namespace": "", "velicina_kb": 1, "status": "indeksirano", "created_at": "2026-10-01"},
        {"id": "dB", "predmet_id": "korisnik-B-0", "user_id": "korisnik-B", "naziv_fajla": "b.pdf", "tekst_sadrzaj": "TAJNI-TEKST-B",
         "pinecone_namespace": "", "velicina_kb": 1, "status": "indeksirano", "created_at": "2026-10-01"},
    ],
    "predmet_delegiranja": [{"id": "x1", "predmet_id": "korisnik-B-1", "na_user_id": "korisnik-D", "status": "aktivno"},
                            {"id": "x2", "predmet_id": "korisnik-B-0", "na_user_id": "korisnik-D", "status": "opozvano"}],
}


class _Upit:
    def __init__(self, tabela, dnevnik):
        self.tabela, self.dnevnik, self.filteri, self.jedan = tabela, dnevnik, [], None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self
    def in_(self, *a): return self
    def is_(self, *a): return self

    def eq(self, k, v):
        self.dnevnik.append((self.tabela, k, v)); self.filteri.append((k, v)); return self

    def maybe_single(self):
        self.jedan = "maybe"; return self

    def single(self):
        self.jedan = "single"; return self

    def execute(self):
        redovi = [dict(r) for r in TABELE.get(self.tabela, []) if all(r.get(k) == v for k, v in self.filteri)]
        if self.jedan:
            if not redovi:
                if self.jedan == "single":
                    raise RuntimeError("postgrest APIError: 0 rows")
                return None   # postgrest 2.28.3
            return types.SimpleNamespace(data=redovi[0])
        return types.SimpleNamespace(data=redovi)

    def __getattr__(self, ime):
        if ime in ("insert", "update", "upsert", "delete", "rpc"):
            raise AssertionError(f"UPIS je zabranjen: {ime}")
        raise AttributeError(ime)


class _Supa:
    def __init__(self):
        self.dnevnik = []

    def table(self, ime):
        return _Upit(ime, self.dnevnik)


def _auth(authorization):
    if not authorization or not authorization.startswith("Bearer ") or authorization[7:] not in TOKENI:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return types.SimpleNamespace(id=TOKENI[authorization[7:]])


@pytest.fixture
def klijent(monkeypatch):
    supa = _Supa()
    monkeypatch.setattr(api, "_require_auth", _auth)
    monkeypatch.setattr(api, "_get_supa", lambda: supa)

    async def _cu(authorization: str = __import__("fastapi").Header(None)):
        return {"user_id": _auth(authorization).id, "email": "t@primer.test"}

    api.app.dependency_overrides[api.get_current_user] = _cu
    import shared.audit_immutable as audit

    async def _bez_audita(*a, **k):
        return None

    monkeypatch.setattr(audit, "log_action", _bez_audita)
    monkeypatch.setattr(api.limiter, "enabled", False)
    k = TestClient(api.app, raise_server_exceptions=False)
    k.supa = supa
    yield k
    api.app.dependency_overrides.pop(api.get_current_user, None)


def _get(k, put, tok):
    return k.get(put, headers={"Authorization": "Bearer " + tok})


def test_vlasnik_cita_svoj_predmet_upit_ogranicen_na_vlasnika(klijent):
    r = _get(klijent, "/api/predmeti/korisnik-A-0", "tok-A")
    assert r.status_code == 200 and r.json()["predmet"]["id"] == "korisnik-A-0"
    assert [d["id"] for d in r.json()["dokumenti"]] == ["dA"]
    assert ("predmeti", "user_id", "korisnik-A") in klijent.supa.dnevnik


@pytest.mark.parametrize("put,tok", [("/api/predmeti/korisnik-B-0", "tok-A"), ("/api/predmeti/nepostoji", "tok-A"),
                                     ("/api/predmeti/korisnik-A-1", "tok-A"), ("/api/predmeti/korisnik-B-0", "tok-D")])
def test_tudj_nepostojeci_obrisan_i_opozvana_delegacija_su_404_bez_podataka(klijent, put, tok):
    r = _get(klijent, put, tok)
    assert r.status_code == 404, (put, tok, r.status_code)
    assert "TAJNI" not in r.text and "predmet\"" not in r.text


def test_aktivna_delegacija_ostaje_citljiva_postojeci_ugovor(klijent):
    r = _get(klijent, "/api/predmeti/korisnik-B-1", "tok-D")
    assert r.status_code == 200 and r.json()["predmet"]["id"] == "korisnik-B-1"


def test_tekst_dokumenta_samo_vlasnik(klijent):
    r = _get(klijent, "/api/predmeti/korisnik-A-0/dokumenti/dA/preview", "tok-A")
    assert r.status_code == 200 and r.json()["tekst"] == "TEKST-A" and r.json()["dostupan"] is True
    assert ("predmet_dokumenti", "user_id", "korisnik-A") in klijent.supa.dnevnik


@pytest.mark.parametrize("put,tok", [("/api/predmeti/korisnik-B-0/dokumenti/dB/preview", "tok-A"),
                                     ("/api/predmeti/korisnik-A-0/dokumenti/dB/preview", "tok-A"),
                                     ("/api/predmeti/korisnik-B-1/dokumenti/dB/preview", "tok-D"),
                                     ("/api/predmeti/korisnik-A-0/dokumenti/nema/preview", "tok-A")])
def test_tudj_dokument_je_404_bez_teksta(klijent, put, tok):
    r = _get(klijent, put, tok)
    assert r.status_code == 404, (put, tok, r.status_code)
    assert "TAJNI" not in r.text


def test_bez_tokena_401(klijent):
    assert klijent.get("/api/predmeti/korisnik-A-0").status_code == 401
    assert klijent.get("/api/predmeti/korisnik-A-0/dokumenti/dA/preview").status_code in (401, 403)
