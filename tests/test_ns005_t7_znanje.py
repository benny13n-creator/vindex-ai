# -*- coding: utf-8 -*-
"""NS005 Task 7 — sudska praksa i interni stavovi: stvarne rute.

POST /api/praksa/search (routers/praksa.py): javni korpus odluka, ali samo uz prijavu;
     filteri se validiraju (400), pad servisa je 500 (ne prazna lista).
POST /interni-stavovi/dodaj|pretraga (routers/interni.py → interni_stavovi.py):
     namespace = `interni_stavovi_<user_id iz tokena>` — stav korisnika A nije
     vidljiv korisniku B. Pinecone i embedding su zamenjeni indeksom u memoriji
     koji STVARNO razdvaja namespace-ove.
"""
import types

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI


class _Indeks:
    """Pinecone u memoriji: upsert/query po namespace-u, kosinus nije bitan (score 0.9)."""

    def __init__(self):
        self.ns = {}
        self.upiti = []

    def upsert(self, vectors, namespace):
        self.ns.setdefault(namespace, []).extend(vectors)

    def query(self, vector, top_k, namespace, include_metadata=True, **kw):
        self.upiti.append(namespace)
        return types.SimpleNamespace(matches=[types.SimpleNamespace(score=0.9, metadata=v["metadata"], id=v["id"])
                                              for v in self.ns.get(namespace, [])][:top_k])


class _Emb:
    def embed_query(self, t):
        return [0.1] * 8

    def embed_documents(self, ts):
        return [[0.1] * 8 for _ in ts]


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, {})
    import shared.permissions as perm
    import shared.usage as us

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
    import interni_stavovi as IS
    idx = _Indeks()
    monkeypatch.setattr(IS, "_get_pinecone_index", lambda: idx)
    monkeypatch.setattr(IS, "_get_embeddings_client", lambda: _Emb())
    yield k, idx
    ocisti()


STAV = "Kancelarija zastupa stav da se zastarelost potraživanja iz radnog odnosa računa od dospeća svake pojedinačne zarade."


def test_stav_A_nije_vidljiv_B(ok):
    k, idx = ok
    r = k.post("/interni-stavovi/dodaj", json={"naslov": "Zastarelost zarade", "tekst": STAV}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert set(idx.ns) == {"interni_stavovi_uid-A"}
    a = k.post("/interni-stavovi/pretraga", json={"upit": "zastarelost zarade"}, headers=zaglavlje("A")).json()
    assert a["pretraga_neuspesna"] is False and a["rezultati"] and a["rezultati"][0]["naslov"] == "Zastarelost zarade"
    bb = k.post("/interni-stavovi/pretraga", json={"upit": "zastarelost zarade"}, headers=zaglavlje("B")).json()
    assert bb["rezultati"] == [] and bb["pretraga_neuspesna"] is False
    assert idx.upiti[-1] == "interni_stavovi_uid-B"


def test_user_id_iz_tela_ne_menja_namespace(ok):
    k, idx = ok
    r = k.post("/interni-stavovi/dodaj", json={"naslov": "Podmetnut", "tekst": STAV, "user_id": "uid-B"}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert "interni_stavovi_uid-B" not in idx.ns


def test_pad_pretrage_stavova_nije_prazno(ok, monkeypatch):
    k, idx = ok
    def _puca(**kw):
        raise RuntimeError("pinecone dole")
    monkeypatch.setattr(idx, "query", _puca)
    d = k.post("/interni-stavovi/pretraga", json={"upit": "zastarelost zarade"}, headers=zaglavlje("A")).json()
    assert d["pretraga_neuspesna"] is True and d["rezultati"] == []


def test_stavovi_bez_tokena_401(ok):
    k, _ = ok
    assert k.post("/interni-stavovi/pretraga", json={"upit": "zastarelost"}).status_code == 401


def test_praksa_trazi_prijavu_i_validira_filter(ok, monkeypatch):
    k, _ = ok
    assert k.post("/api/praksa/search", json={"query": "otkaz"}).status_code == 401
    r = k.post("/api/praksa/search", json={"query": "otkaz", "matter": "Izmišljena"}, headers=zaglavlje("A"))
    assert r.status_code == 400


def test_praksa_vraca_odluke_i_pad_je_500(ok, monkeypatch):
    k, _ = ok
    import routers.praksa as P
    odluka = {"decision_number": "Rev 123/2024", "decision_date": "2024-05-10", "court": "Vrhovni sud", "matter": "Građanska",
              "izreka_preview": "Revizija se odbija.", "citat_format": "Vrhovni sud, Rev 123/2024, od 10.05.2024."}
    monkeypatch.setattr(P, "_praksa_search_sync", lambda *a, **kw: {"decisions": [odluka], "total": 1, "page": 1, "limit": 10})
    d = k.post("/api/praksa/search", json={"query": "otkaz", "matter": "Građanska"}, headers=zaglavlje("A")).json()
    assert d["decisions"][0]["decision_number"] == "Rev 123/2024"

    def _puca(*a, **kw):
        raise RuntimeError("pinecone dole")
    monkeypatch.setattr(P, "_praksa_search_sync", _puca)
    r = k.post("/api/praksa/search", json={"query": "otkaz"}, headers=zaglavlje("A"))
    assert r.status_code == 500 and "decisions" not in r.json()


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
