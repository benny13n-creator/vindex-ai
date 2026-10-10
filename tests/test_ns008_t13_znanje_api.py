# -*- coding: utf-8 -*-
"""NS008 Task 13 — GET /api/law-brain/znanje: pregled znanja kancelarije bez modela, kredita i upisa."""
import json

import pytest

import tests.ns008_fake as f8
from tests.test_ns008_t11_api import PA_OLD, _tabele


@pytest.fixture
def svet(monkeypatch):
    k, b = f8.pripremi(monkeypatch, _tabele())
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("model")))
    from shared.usage import UsageService
    krediti = []

    async def _c(*a, **kw):
        krediti.append(a)
    monkeypatch.setattr(UsageService, "consume", _c)
    yield k, b, krediti
    f8.ocisti()


def test_pregled_za_vlasnika(svet):
    k, b, krediti = svet
    b.dnevnik.clear()
    d = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("A")).json()
    assert {d[s]["state"] for s in ("iskustvo", "verifikovani_radovi", "potvrdjene_lekcije", "memorija_kancelarije")} == {"OK"}
    g = d["iskustvo"]["grupe"]
    assert len(g) == 1 and g[0]["tip"] == "radni" and g[0]["po_ishodu"] == {"nagodba": 1} and d["iskustvo"]["zavrsenih"] == 1
    r = d["verifikovani_radovi"]["stavke"]
    assert [x["source_ref"]["id"] for x in r] == ["s-ok"] and r[0]["predmet_naziv"] == "Petrović protiv Gradnja Invest DOO"
    assert [x["source_ref"]["id"] for x in d["potvrdjene_lekcije"]["stavke"]] == ["l1"]
    assert d["potvrdjene_lekcije"]["kandidata"] == 1
    assert krediti == [] and {x["radnja"] for x in b.dnevnik if x["tabela"] not in ("audit_log",)} == {"select"}


def test_kolega_ne_vidi_tudje(svet):
    k, _, _ = svet
    d = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("B")).json()
    t = json.dumps(d, ensure_ascii=False)
    for z in ("Petrović protiv", PA_OLD, "s-ok", "Pribaviti", "nagodba"):
        assert z not in t
    assert d["iskustvo"]["state"] == "EMPTY" and d["memorija_kancelarije"]["state"] == "OK"


def test_pad_izvora_degraded(svet):
    k, b, _ = svet
    b.greske["staging_memory"] = Exception("down")
    d = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("A")).json()
    assert d["verifikovani_radovi"]["state"] == "DEGRADED"
    assert d["data_quality"]["nedostupni_izvori"] == ["iskustvo", "verifikovani_radovi"], "profil čita i staging"


def test_pad_autorizacije_503_i_bez_tokena_401(svet):
    k, b, _ = svet
    assert k.get("/api/law-brain/znanje").status_code == 401
    b.greske["predmeti"] = Exception("down")
    assert k.get("/api/law-brain/znanje", headers=f8.zaglavlje("A")).status_code == 503
