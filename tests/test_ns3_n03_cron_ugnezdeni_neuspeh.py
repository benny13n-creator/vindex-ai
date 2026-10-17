# -*- coding: utf-8 -*-
"""NS3-N03 — dnevni dispečer ne sme da prijavi onboarding i nedeljni sažetak kao uspešne kada modul vrati
`greske > 0` ili oblik bez ugovornih brojača.

Ugovor oba modula (`routers/email_notif.py`): `{"poslato": int, "greske": int}` (nedeljni ume da doda
`napomena` kad nema primalaca). Pre ispravke dispečer je posle svakog povratka upisivao `"status": "ok"` i
nije povećavao `broj_gresaka` — isti razred koji je TENFRONTS-M01 zatvorio za email podsetnike.

Stvarni `api.cron_daily` kroz TestClient; ostali moduli i baza iz harness-a `test_cron_daily_dispatcher`.
Nedeljni sažetak radi samo ponedeljkom (UTC): `datetime.datetime` se zamenjuje podklasom čiji je `now()`
ponedeljak, jer dispečer uvozi `datetime` lokalno pri svakom pozivu."""
import asyncio
import datetime as _datetime
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_cron_daily_dispatcher import (  # noqa: F401  (autouse fixture-i)
    _patch_submodules, _patch_supa, _post_cron_daily, _client)


@pytest.fixture(autouse=True)
def _bez_mreze():
    with patch("services.event_bus.reap_missing_pipeline_events", new=AsyncMock(return_value={"checked": 0, "backfilled": 0})), \
         patch("services.event_bus.reap_missing_rociste_events", new=AsyncMock(return_value={"checked": 0, "backfilled": 0})), \
         patch("routers.billing.reap_orphan_fakture", new=AsyncMock(return_value={"checked": 0, "reaped": 0})):
        yield


class _Ponedeljak(_datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 19, 9, 0, tzinfo=tz)      # ponedeljak


def _pokreni(modul, rezultat=None, izuzetak=None, ponedeljak=True):
    mock = AsyncMock(side_effect=izuzetak) if izuzetak else AsyncMock(return_value=rezultat)
    with patch(f"routers.email_notif.{modul}", new=mock):
        if ponedeljak:
            with patch("datetime.datetime", _Ponedeljak):
                r = _post_cron_daily(_client())
        else:
            r = _post_cron_daily(_client())
    assert r.status_code == 200, r.text
    return r.json(), mock


KLJUC = {"onboarding_cron": "onboarding", "posalji_nedeljni_sazetak": "nedeljni_sazetak"}
MODULI = list(KLJUC)


@pytest.mark.parametrize("modul", MODULI)
@pytest.mark.parametrize("rez", [
    {"poslato": 0, "greske": 1},
    {"poslato": 3, "greske": 2},
    None,
    {},
    {"poslato": 2},                       # nedostaje `greske`
    {"poslato": 1, "greske": "1"},
    {"poslato": 1, "greske": True},
    {"poslato": -1, "greske": 0},
    "ok",
], ids=["greska", "delimicno", "None", "prazno", "bez_greske", "string", "bool", "negativno", "tekst"])
def test_neuspeh_ili_nevalidan_ishod_nije_ok(modul, rez):
    body, mock = _pokreni(modul, rez)
    assert mock.await_count == 1                                          # bez ponavljanja
    assert body[KLJUC[modul]]["status"] == "greska", body[KLJUC[modul]]
    assert body["ok"] is False and body["heartbeat"]["broj_gresaka"] >= 1


@pytest.mark.parametrize("modul", MODULI)
@pytest.mark.parametrize("rez", [
    {"poslato": 0, "greske": 0},
    {"poslato": 5, "greske": 0},
])
def test_legitiman_ishod_ostaje_ok(modul, rez):
    body, _ = _pokreni(modul, rez)
    assert body[KLJUC[modul]]["status"] == "ok"
    assert body[KLJUC[modul]]["poslato"] == rez["poslato"]
    assert body["ok"] is True and body["heartbeat"]["broj_gresaka"] == 0


def test_nedeljni_bez_primalaca_je_ok_i_cuva_napomenu():
    rez = {"poslato": 0, "greske": 0, "napomena": "Nema korisnika sa aktivnim nedeljnim sažetkom"}
    body, _ = _pokreni("posalji_nedeljni_sazetak", rez)
    assert body["nedeljni_sazetak"]["status"] == "ok" and body["nedeljni_sazetak"]["napomena"] == rez["napomena"]
    assert body["ok"] is True


@pytest.mark.parametrize("modul", MODULI)
def test_izuzetak_i_timeout(modul):
    body, _ = _pokreni(modul, izuzetak=RuntimeError("smtp"))
    assert body[KLJUC[modul]]["status"] == "greska" and body["ok"] is False
    body, _ = _pokreni(modul, izuzetak=asyncio.TimeoutError())
    assert body[KLJUC[modul]]["status"] == "timeout" and body["ok"] is False


@pytest.mark.parametrize("modul", MODULI)
def test_neuspeh_modula_ne_zaustavlja_ostale(modul):
    body, _ = _pokreni(modul, {"poslato": 0, "greske": 1})
    assert body["email_podsetnici"]["status"] == "ok"
    assert body["retention_cleanup"]["status"] == "ok"
    assert body["heartbeat"]["status"] == "ok"


def test_nedeljni_se_ne_poziva_van_ponedeljka():
    class _Utorak(_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 20, 9, 0, tzinfo=tz)
    mock = AsyncMock(return_value={"poslato": 0, "greske": 1})
    with patch("routers.email_notif.posalji_nedeljni_sazetak", new=mock), patch("datetime.datetime", _Utorak):
        body = _post_cron_daily(_client()).json()
    assert mock.await_count == 0 and body["nedeljni_sazetak"]["status"] == "preskoceno"


def test_poslato_se_broji_samo_kao_validan_ceo_broj():
    body, _ = _pokreni("onboarding_cron", {"poslato": 4, "greske": 0})
    assert body["heartbeat"]["status"] == "ok"
