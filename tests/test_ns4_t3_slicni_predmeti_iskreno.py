# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 3: `GET /api/learning/slicni-predmeti/{id}` ne sme da predstavi istoriju kao predviđanje.

Zatečeno: već za JEDAN sličan predmet ruta je pisala „win rate 100%“ i „X je bio presudni faktor u pobedama“ (tvrdnja
o uzroku iz izbora advokata), prazna istorija je bila prazan string bez stanja, a kad model nije dostupan, svaki
predmet istog tipa dobijao je izmišljenu „sličnost 60“. Model se ovde menja deterministički (nema mreže).
"""
import asyncio
import json
import types

import pytest

import routers.learning as L
import tests.ns008_fake as f8

TEK = "aaaaaaaa-4444-4000-8000-000000000001"


def _zatvoren(i, ishod_tip="radni"):
    return {"id": f"aaaaaaaa-4444-4000-8000-0000000001{i:02d}", "user_id": "uid-A", "naziv": f"Zatvoren {i}",
            "status": "zatvoren", "tip": ishod_tip}


@pytest.fixture
def svet(monkeypatch):
    def napravi(n_sa_ishodom, ishodi=None):
        zatv = [_zatvoren(i) for i in range(n_sa_ishodom)]
        k, baza = f8.pripremi(monkeypatch, {
            "predmeti": [{"id": TEK, "user_id": "uid-A", "naziv": "Tekući", "status": "aktivan", "tip": "radni",
                          "opis": "otkaz"}] + zatv,
            "outcome_log": [{"predmet_id": p["id"], "user_id": "uid-A", "ishod": (ishodi or ["pobeda"] * 99)[i],
                             "presudni_faktori": ["svedoci"], "tip_spora": "radni"} for i, p in enumerate(zatv)],
        })
        monkeypatch.setattr(L, "_get_supa", lambda: baza)

        async def _bez_naplate(*_a, **_k):
            return None
        monkeypatch.setattr(L.UsageService, "consume", _bez_naplate)
        return k, baza, zatv
    yield napravi
    f8.ocisti()


def _model_rangira(monkeypatch, zatv):
    monkeypatch.setenv("OPENAI_API_KEY", "test-nije-pravi")
    odgovor = {"rezultati": [{"predmet_id_prefix": p["id"][:8], "slicnost": 90,
                              "razlog": "isti tip"} for p in zatv]}

    def _lazni(_client, **_kw):
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(odgovor)))])
    monkeypatch.setattr(L, "_pozovi_learning_api", _lazni)


def _lazni_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/api/learning/slicni-predmeti",
                    "headers": [], "query_string": b"", "client": ("127.0.0.1", 0),
                    "server": ("testserver", 80), "scheme": "http", "root_path": "", "app": None})


def _zovi(_k):
    """Handler direktno (zavisnost dozvole `learning` se vezuje pri uvozu rute; ovde se meri samo odgovor)."""
    return asyncio.run(L.slicni_predmeti(predmet_id=TEK, request=_lazni_request(), user={"user_id": "uid-A"}))


def test_bez_istorije_eksplicitno_nedovoljno_podataka(svet, monkeypatch):
    k, _, _ = svet(0)
    rez = _zovi(k)
    assert rez["slicni_predmeti"] == [] and rez.get("stanje") == "NEDOVOLJNO_PODATAKA"


def test_jedan_predmet_nije_stopa_uspeha(svet, monkeypatch):
    k, _, zatv = svet(1)
    _model_rangira(monkeypatch, zatv)
    rez = _zovi(k)
    s = rez["strategija_preporuka"].lower()
    assert "win rate" not in s and "%" not in s, "procenat na uzorku od jednog predmeta"
    assert rez.get("stanje") == "NEDOVOLJNO_PODATAKA" and rez.get("uzorak") == 1


def test_uzorak_prikazan_i_bez_tvrdnje_o_uzroku(svet, monkeypatch):
    k, _, zatv = svet(4, ishodi=["pobeda", "pobeda", "poraz", "pobeda"])
    _model_rangira(monkeypatch, zatv)
    rez = _zovi(k)
    s = rez["strategija_preporuka"]
    assert rez.get("uzorak") == 4 and "4" in s
    assert "presudni faktor u pobedama" not in s, "izbor advokata predstavljen kao uzrok pobede"
    assert "nije predviđanje" in s.lower() or "ne predviđanje" in s.lower()


def test_bez_modela_nema_izmisljene_slicnosti(svet, monkeypatch):
    k, _, zatv = svet(2)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rez = _zovi(k)
    assert rez["slicni_predmeti"], "rezerva po istom tipu spora treba da postoji"
    assert all(x["slicnost"] is None for x in rez["slicni_predmeti"]), "izmišljena ocena sličnosti bez modela"
