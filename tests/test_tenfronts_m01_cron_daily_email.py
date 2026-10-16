# -*- coding: utf-8 -*-
"""TENFRONTS-M01 — `/api/cron/daily` ne sme da prijavi email podsetnike kao uspešne kada email modul
prijavi grešku ili nepotvrđenu isporuku.

Stvarni dispečer (`api.cron_daily`) kroz TestClient; ostali moduli i baza zamenjeni harness-om iz
`test_cron_daily_dispatcher` (isti fixture-i). Email modul vraća zadat rezultat."""
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_cron_daily_dispatcher import (  # noqa: F401  (autouse fixture-i)
    _patch_submodules, _patch_supa, _post_cron_daily, _client)


@pytest.fixture(autouse=True)
def _bez_mreze():
    """Postojeći harness ne zamenjuje tri `reap_*` modula — oni bez toga pokušavaju stvaran mrežni poziv
    (getaddrinfo) i svaki put obaraju ukupni `ok`. Ovde su zamenjeni da `ok` meri samo email modul."""
    with patch("services.event_bus.reap_missing_pipeline_events", new=AsyncMock(return_value={"checked": 0, "backfilled": 0})), \
         patch("services.event_bus.reap_missing_rociste_events", new=AsyncMock(return_value={"checked": 0, "backfilled": 0})), \
         patch("routers.billing.reap_orphan_fakture", new=AsyncMock(return_value={"reaped": 0})):
        yield


def _ok(**k):
    return {"poslato": 0, "greske": 0, "preskoceno": 0, "neisporuceno": 0, **k}


def _pokreni(rezultat=None, izuzetak=None):
    mock = AsyncMock(side_effect=izuzetak) if izuzetak else AsyncMock(return_value=rezultat)
    with patch("routers.email_notif.posalji_podsetnike", new=mock):
        r = _post_cron_daily(_client())
    assert r.status_code == 200, r.text            # HTTP ugovor dispečera nepromenjen
    return r.json()


@pytest.mark.parametrize("rez,status", [
    (_ok(poslato=3), "ok"),
    (_ok(), "ok"),
    (_ok(poslato=1, preskoceno=2), "ok"),
    (_ok(napomena="Nema aktivnih profila"), "nema_primalaca"),
])
def test_legitiman_ishod_ne_povecava_greske(rez, status):
    body = _pokreni(rez)
    assert body["email_podsetnici"]["status"] == status
    assert body["ok"] is True and body["heartbeat"]["broj_gresaka"] == 0


@pytest.mark.parametrize("rez,status", [
    (_ok(greske=1), "greska"),
    (_ok(poslato=2, greske=1), "greska"),
    (_ok(neisporuceno=1), "neisporuceno"),
    (_ok(poslato=2, neisporuceno=1), "neisporuceno"),
    (_ok(greske=1, neisporuceno=1), "greska"),
    ({}, "greska"),
    (None, "greska"),
    ({"poslato": 4, "greske": 0}, "greska"),                 # nedostaju brojači
    (_ok(poslato="1"), "greska"),
    (_ok(greske=True), "greska"),
    (_ok(poslato=-1), "greska"),
    ("ok", "greska"),
])
def test_neuspeh_ili_nevalidan_rezultat_nije_ok(rez, status):
    body = _pokreni(rez)
    assert body["email_podsetnici"]["status"] == status, body["email_podsetnici"]
    assert body["ok"] is False
    assert body["heartbeat"]["broj_gresaka"] >= 1


def test_izuzetak_email_modula_je_greska():
    body = _pokreni(izuzetak=RuntimeError("smtp"))
    assert body["email_podsetnici"]["status"] == "greska" and body["ok"] is False


def test_timeout_email_modula():
    import asyncio
    body = _pokreni(izuzetak=asyncio.TimeoutError())
    assert body["email_podsetnici"]["status"] == "timeout" and body["ok"] is False


def test_neuspeh_emaila_ne_obara_ostale_module_i_ne_ponavlja_poziv():
    mock = AsyncMock(return_value=_ok(neisporuceno=1))
    with patch("routers.email_notif.posalji_podsetnike", new=mock):
        body = _post_cron_daily(_client()).json()
    assert mock.await_count == 1
    assert body["retention_cleanup"]["status"] == "ok"
    assert body["heartbeat"]["status"] == "ok"


def test_brojaci_ostaju_vidljivi_u_odgovoru():
    body = _pokreni(_ok(poslato=2, neisporuceno=1))
    em = body["email_podsetnici"]
    assert (em["poslato"], em["neisporuceno"]) == (2, 1)
