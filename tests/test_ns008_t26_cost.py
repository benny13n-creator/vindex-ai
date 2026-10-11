# -*- coding: utf-8 -*-
"""NS008 Task 26 — granica troška: tačno gde Law Brain poziva model.

Brojači: poziv modela sinteze (jedina kompletacija), embedding upita (`_ugradi_query`), naplata kredita, i
svaki drugi pokušaj konstrukcije OpenAI klijenta (mora biti 0). Očekivano:
  otvori Znanje 0 · otvori kontekst predmeta 0 · sličnost 0 · opis ishoda 0 · izričita sinteza 1 (+1 kredit) ·
  ponavljanje istim ključem 1 · pretraga overenog znanja 0 kompletacija / 1 embedding (izričit upit) ·
  pad baze → bez plaćenog „pomoćnog" odgovora · autonomija ne poziva sintezu.
"""
import inspect
import types
import uuid
from datetime import date

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb
from tests.test_ns008_t11_api import PA_CUR, _tabele


@pytest.fixture
def merac(monkeypatch):
    k, b = f8.pripremi(monkeypatch, _tabele())
    import openai
    import shared.permissions as perm
    import shared.usage as us
    import services.law_brain_sinteza as S
    from app.services import retrieve as rt
    c = {"sinteza": 0, "embedding": 0, "kredit": 0, "drugi_klijent": 0}

    def _zabranjen(*a, **kw):
        c["drugi_klijent"] += 1
        raise AssertionError("neočekivan OpenAI klijent")
    monkeypatch.setattr(openai, "OpenAI", _zabranjen)
    monkeypatch.setattr(openai, "AsyncOpenAI", _zabranjen)

    async def _model(prompt, pid):
        c["sinteza"] += 1
        return '{"tvrdnje": []}'

    async def _pol(f):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _kredit(*a, **kw):
        c["kredit"] += 1

    def _emb(q):
        c["embedding"] += 1
        return [0.1]
    monkeypatch.setattr(S, "_pozovi_model_sinteze", _model)
    monkeypatch.setattr(perm, "get_policy", _pol)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_kredit))
    monkeypatch.setattr(rt, "_ugradi_query", _emb)
    monkeypatch.setattr(rt, "_pretraga_ns", lambda vec, ns, kk, filt: [])
    yield k, b, c
    f8.ocisti()


def _bez_troska(c):
    return c == {"sinteza": 0, "embedding": 0, "kredit": 0, "drugi_klijent": 0}


def test_citanja_su_besplatna(merac):
    k, b, c = merac
    assert k.get("/api/law-brain/znanje", headers=f8.zaglavlje("A")).status_code == 200
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).status_code == 200
    lb.slicni_predmeti(b, "uid-A", PA_CUR)
    lb.descriptive_outcomes(lb.slicni_predmeti(b, "uid-A", PA_CUR)["_profili"])
    assert _bez_troska(c), c


def test_sinteza_jedan_poziv_i_jedan_kredit_i_ponavljanje(merac):
    k, _, c = merac
    h = {**f8.zaglavlje("A"), "Idempotency-Key": str(uuid.uuid4())}
    k.post(f"/api/law-brain/predmeti/{PA_CUR}/sinteza", headers=h)
    k.post(f"/api/law-brain/predmeti/{PA_CUR}/sinteza", headers=h)
    assert c == {"sinteza": 1, "embedding": 0, "kredit": 1, "drugi_klijent": 0}


def test_pretraga_overenog_znanja_samo_embedding(merac):
    _, b, c = merac
    lb.pretrazi_znanje_kancelarije(b, "uid-A", "otkaz", today=date(2026, 10, 10))
    assert c == {"sinteza": 0, "embedding": 1, "kredit": 0, "drugi_klijent": 0}
    lb.pretrazi_znanje_kancelarije(b, "uid-A", "   ", today=date(2026, 10, 10))
    assert c["embedding"] == 1, "prazan upit ne troši"


def test_pad_baze_bez_placenog_odgovora(merac):
    k, b, c = merac
    b.greske["predmeti"] = Exception("down")
    assert k.post(f"/api/law-brain/predmeti/{PA_CUR}/sinteza", headers=f8.zaglavlje("A")).status_code == 503
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).status_code == 503
    assert _bez_troska(c), c


def test_autonomija_ne_poziva_sintezu():
    import workers.background_agents as ba
    from services.agent_tasks import hearing_prep, precedents_radar
    for mod in (ba, hearing_prep, precedents_radar):
        src = inspect.getsource(mod)
        assert "law_brain" not in src, mod.__name__


def test_ruta_pretrage_izricita_bez_kredita_i_pad_je_degraded(merac):
    k, b, c = merac
    r = k.get("/api/law-brain/pretraga?q=otkaz", headers=f8.zaglavlje("A"))
    assert r.status_code == 200 and r.json()["stanje"] == "EMPTY"
    assert c == {"sinteza": 0, "embedding": 1, "kredit": 0, "drugi_klijent": 0}
    assert k.get(f"/api/law-brain/pretraga?q=x&predmet_id={PA_CUR}", headers=f8.zaglavlje("B")).status_code == 404
    from app.services import retrieve as rt
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(rt, "_pretraga_ns", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("pinecone down")))
    try:
        d = k.get("/api/law-brain/pretraga?q=otkaz", headers=f8.zaglavlje("A")).json()
        assert d["stanje"] == "DEGRADED" and d["stavke"] == [], "pad pretrage nije „nema rezultata“"
    finally:
        mp.undo()
    assert c["sinteza"] == 0 and c["kredit"] == 0
