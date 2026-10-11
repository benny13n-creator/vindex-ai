# -*- coding: utf-8 -*-
"""NS008 Task 7 — lekcije: AI predlog je KANDIDAT dok ga advokat izričito ne potvrdi.

Postojeća šema (039) već beleži potvrdu (`status_lekcije`, `potvrdio`, `potvrdjeno_at`) i postojeća ruta
`PATCH /api/learning/lessons/{id}/potvrdi` je ljudska kapija — Law Brain ih ponovo koristi, bez migracije.
"""
import asyncio
import uuid

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

L_KAND, L_POTV, L_ODB, L_STARA, L_LAZNA, L_ZAST, L_TUDJA = (str(uuid.UUID(int=700 + i)) for i in range(7))


def _l(lid, uid="uid-A", **kw):
    base = {"id": lid, "user_id": uid, "predmet_id": None, "tip_spora": "radni", "lecija": f"Lekcija {lid[-3:]}",
            "kategorija": "dokaz", "status_lekcije": "predlog_ai", "potvrdio": None, "potvrdjeno_at": None,
            "zastarela": False, "created_at": "2026-09-01T00:00:00+00:00"}
    base.update(kw)
    return base


@pytest.fixture
def svet(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "lessons_learned": [
            _l(L_KAND),
            _l(L_POTV, status_lekcije="usvojena_praksa", potvrdio="uid-A", potvrdjeno_at="2026-09-02T00:00:00+00:00"),
            _l(L_ODB, status_lekcije="odbijena", zastarela=True),
            _l(L_STARA, status_lekcije=None),
            _l(L_LAZNA, status_lekcije="usvojena_praksa"),
            _l(L_ZAST, status_lekcije="usvojena_praksa", potvrdio="uid-A", potvrdjeno_at="2026-01-01T00:00:00+00:00",
               zastarela=True),
            _l(L_TUDJA, uid="uid-B", status_lekcije="usvojena_praksa", potvrdio="uid-B",
               potvrdjeno_at="2026-09-02T00:00:00+00:00"),
        ],
        "v2_mutation_idempotency": [], "predmeti": [],
    })
    yield k, baza
    f8.ocisti()


def _stanja(baza):
    return {it.source_id: it for it in lb.ucitaj_lekcije(baza, "uid-A")}


def test_stanja_kapije(svet):
    _, baza = svet
    s = _stanja(baza)
    assert L_TUDJA not in s, "tuđe lekcije nikad"
    assert (s[L_KAND].state, s[L_KAND].trust_class, s[L_KAND].human_verified) == \
        (lb.LESSON_CANDIDATE, lb.AI_CANDIDATE_LESSON, False)
    assert (s[L_POTV].state, s[L_POTV].trust_class, s[L_POTV].validity) == \
        (lb.LESSON_CONFIRMED, lb.LAWYER_VERIFIED_ARTIFACT, lb.UNKNOWN)
    assert s[L_POTV].lineage == ("AI_GENERATED", "LAWYER_CONFIRMED")
    assert (s[L_ODB].state, s[L_ODB].validity) == (lb.LESSON_REJECTED, lb.DEPRECATED)
    assert (s[L_STARA].state, s[L_STARA].trust_class) == (lb.LESSON_UNKNOWN_LEGACY, lb.UNKNOWN_LEGACY)
    assert s[L_LAZNA].trust_class == lb.UNKNOWN_LEGACY, "usvojena bez dokaza ko je potvrdio → nema pogađanja"
    assert (s[L_ZAST].state, s[L_ZAST].validity) == (lb.LESSON_CONFIRMED, lb.STALE)


def test_samo_potvrdjene_su_smernice(svet):
    _, baza = svet
    smernice = {it.source_id for it in lb.lekcije_kao_smernice(lb.ucitaj_lekcije(baza, "uid-A"))}
    assert smernice == {L_POTV, L_ZAST}
    assert L_KAND not in smernice and L_ODB not in smernice and L_STARA not in smernice and L_LAZNA not in smernice


def test_ljudska_potvrda_kroz_rutu_menja_kandidata_u_potvrdjenu(svet):
    k, baza = svet
    r = k.patch(f"/api/learning/lessons/{L_KAND}/potvrdi", json={"akcija": "potvrdi"}, headers=f8.zaglavlje("A"))
    assert r.status_code == 200, r.text
    it = _stanja(baza)[L_KAND]
    assert it.state == lb.LESSON_CONFIRMED and it.trusted


def test_odbijanje_kroz_rutu_nikad_smernica(svet):
    k, baza = svet
    k.patch(f"/api/learning/lessons/{L_POTV}/potvrdi", json={"akcija": "odbaci", "komentar": "netačno"},
            headers=f8.zaglavlje("A"))
    it = _stanja(baza)[L_POTV]
    assert it.state == lb.LESSON_REJECTED and it not in lb.lekcije_kao_smernice([it])


def test_tudja_lekcija_se_ne_moze_potvrditi(svet):
    k, baza = svet
    r = k.patch(f"/api/learning/lessons/{L_TUDJA}/potvrdi", json={"akcija": "odbaci"}, headers=f8.zaglavlje("A"))
    assert r.status_code == 404
    assert next(x for x in baza.tabele["lessons_learned"] if x["id"] == L_TUDJA)["status_lekcije"] == "usvojena_praksa"


def test_ai_generator_ne_moze_upisati_usvojenu_lekciju(svet, monkeypatch):
    _, baza = svet
    from services.learning_engine import learning
    n = asyncio.run(learning.save_lessons("uid-A", None, [
        {"lecija": "Podmetnuto kao usvojena praksa", "status_lekcije": "usvojena_praksa"}], "radni"))
    assert n == 1
    red = next(x for x in baza.tabele["lessons_learned"] if x["lecija"] == "Podmetnuto kao usvojena praksa")
    assert red["status_lekcije"] == "predlog_ai"
    assert lb.lesson_item(red, "uid-A").state == lb.LESSON_CANDIDATE


def test_potvrda_je_idempotentna_po_kljucu(svet):
    k, baza = svet
    h = {**f8.zaglavlje("A"), "Idempotency-Key": str(uuid.uuid4())}
    r1 = k.patch(f"/api/learning/lessons/{L_KAND}/potvrdi", json={"akcija": "potvrdi"}, headers=h)
    r2 = k.patch(f"/api/learning/lessons/{L_KAND}/potvrdi", json={"akcija": "potvrdi"}, headers=h)
    assert r1.json() == r2.json()
    assert sum(1 for d in baza.dnevnik if d["tabela"] == "lessons_learned" and d["radnja"] == "update") == 1


def test_citanje_ne_menja_stanje(svet):
    _, baza = svet
    baza.dnevnik.clear()
    lb.ucitaj_lekcije(baza, "uid-A")
    assert {d["radnja"] for d in baza.dnevnik} == {"select"}
