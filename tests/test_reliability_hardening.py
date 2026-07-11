# -*- coding: utf-8 -*-
"""
Tests za Reliability & UX Hardening Sprint (2026-07-11).

Pokriva kritične scenarije:
  T1 — APR autofill: mrežni neuspeh nikad ne blokira ručni unos.
  T2 — Portal monitoring: duplicate-protection preskače nedavno proveravane predmete.
  T3 — cron_daily: pad jednog modula ne sprečava heartbeat/ostale module.
  T4 — Notifikacije: tihi period ispravno odlaže/propušta slanje.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import datetime as dt_module
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "cccc0000-0000-0000-0000-000000000003", "email": "test@vindex.rs"}


def _make_chain(data=None, count=None):
    c = MagicMock()
    for a in ["select", "eq", "neq", "gte", "lte", "gt", "lt", "order", "limit",
              "execute", "is_", "in_", "upsert", "insert", "update", "delete", "maybe_single"]:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock()
    r.data = data
    r.count = count
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(table_data: dict | None = None):
    """table_data: {table_name: data} — vraćeni podaci za tu tabelu, default None za ostale."""
    table_data = table_data or {}
    supa = MagicMock()
    supa.table.side_effect = lambda name: _make_chain(table_data.get(name))
    return supa


# ── T1: APR autofill — mrežni neuspeh nikad ne blokira ručni unos ────────────

class _TimeoutClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **kw):
        raise httpx.TimeoutException("timeout")


class _Http500Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **kw):
        resp = MagicMock()
        resp.status_code = 500
        return resp


@pytest.mark.anyio
async def test_apr_lookup_timeout_returns_editable_fallback():
    from routers.apr import _apr_lookup
    with patch("routers.apr.httpx.AsyncClient", return_value=_TimeoutClient()):
        result = await _apr_lookup("12345678")
    assert result["greska"] == "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
    assert result["naziv"] == "" and result["pib"] == "" and result["adresa"] == ""
    assert result["source"] == "APR"
    assert result["fetched_at"]  # timing/metadata se svejedno beleže


@pytest.mark.anyio
async def test_apr_lookup_http_error_returns_editable_fallback():
    from routers.apr import _apr_lookup
    with patch("routers.apr.httpx.AsyncClient", return_value=_Http500Client()):
        result = await _apr_lookup("12345678")
    assert result["greska"] == "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
    assert result["naziv"] == ""  # forma ostaje prazna/editabilna, ne puca


# ── T2: Portal monitoring — duplicate protection preskače nedavne provere ────

@pytest.mark.anyio
async def test_cron_proveri_skips_recently_checked_predmet():
    from routers.portal_monitoring import cron_proveri

    nedavno = (dt_module.datetime.now(dt_module.timezone.utc) - dt_module.timedelta(minutes=5)).isoformat()
    predmeti = [{
        "id": "pp1", "user_id": "u1", "naziv": "Test predmet",
        "broj_predmeta": "P 1/2024", "sud_naziv": "Osnovni sud",
        "poslednji_status": "U toku", "poslednja_provera": nedavno,
    }]
    supa = _make_supa({"praceni_predmeti": predmeti})

    with patch("routers.portal_monitoring._get_supa", return_value=supa), \
         patch("routers.portal_monitoring._is_founder", return_value=True), \
         patch("routers.portal_monitoring._scrape_portal_status", new=AsyncMock()) as mock_scrape:
        result = await cron_proveri(MagicMock(), x_cron_secret=None, user=_user(), run_id="test-run")

    mock_scrape.assert_not_called()
    assert result["preskoceno"] == 1
    assert result["provereno"] == 0


@pytest.mark.anyio
async def test_cron_proveri_checks_stale_predmet():
    from routers.portal_monitoring import cron_proveri

    davno = (dt_module.datetime.now(dt_module.timezone.utc) - dt_module.timedelta(hours=5)).isoformat()
    predmeti = [{
        "id": "pp2", "user_id": "u1", "naziv": "Test predmet 2",
        "broj_predmeta": "P 2/2024", "sud_naziv": "Osnovni sud",
        "poslednji_status": "U toku", "poslednja_provera": davno,
    }]
    supa = _make_supa({"praceni_predmeti": predmeti})
    scrape_result = {"status": "U toku", "datum": "2026-07-11", "greska": None, "kind": "ok"}

    with patch("routers.portal_monitoring._get_supa", return_value=supa), \
         patch("routers.portal_monitoring._is_founder", return_value=True), \
         patch("routers.portal_monitoring._scrape_portal_status", new=AsyncMock(return_value=scrape_result)) as mock_scrape:
        result = await cron_proveri(MagicMock(), x_cron_secret=None, user=_user(), run_id="test-run")

    mock_scrape.assert_called_once()
    assert result["preskoceno"] == 0
    assert result["provereno"] == 1


# ── T3: cron_daily — pad jednog modula ne sprečava heartbeat/ostale module ───

@pytest.mark.anyio
async def test_cron_daily_module_failure_does_not_block_heartbeat(monkeypatch):
    monkeypatch.delenv("BRIEFING_CRON_SECRET", raising=False)
    import api

    class _FakeReq:
        headers = {}

    supa = _make_supa()

    with patch("api._get_supa", return_value=supa), \
         patch("routers.workflow._check_escalations", new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("routers.zakon_monitoring._skeniraj_sl_glasnik", new=AsyncMock(return_value={"pronadjeno": 0, "promena": 0})), \
         patch("routers.portal_monitoring.cron_proveri", new=AsyncMock(return_value={"provereno": 0, "promena": 0})):
        result = await api.cron_daily(_FakeReq())

    assert result["workflow"]["status"] == "greska"
    assert result["portal_monitoring"]["status"] == "ok"
    assert result["heartbeat"]["status"] == "ok"  # heartbeat se izvršio uprkos grešci u workflow modulu
    assert result["ok"] is False  # ukupan run ima grešku, ali nije pukao


# ── T4: Notifikacije — tihi period ispravno odlaže/propušta slanje ──────────

def _frozen_hour(hour: int):
    class _Frozen(dt_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 1, hour, 0, 0)
    return patch("shared.notify_quiet.datetime", _Frozen)


def test_quiet_hours_no_profile_never_quiet():
    from shared.notify_quiet import is_quiet_now
    assert is_quiet_now(None) is False


def test_quiet_hours_not_configured_never_quiet():
    from shared.notify_quiet import is_quiet_now
    assert is_quiet_now({"quiet_start": None, "quiet_end": None}) is False


def test_quiet_hours_overnight_window_defers_normal_notification():
    from shared.notify_quiet import is_quiet_now
    profile = {"quiet_start": 22, "quiet_end": 8, "allow_critical_override": True}
    with _frozen_hour(23):
        assert is_quiet_now(profile, critical=False) is True


def test_quiet_hours_critical_bypasses_when_override_allowed():
    from shared.notify_quiet import is_quiet_now
    profile = {"quiet_start": 22, "quiet_end": 8, "allow_critical_override": True}
    with _frozen_hour(23):
        assert is_quiet_now(profile, critical=True) is False


def test_quiet_hours_critical_still_deferred_when_override_disallowed():
    from shared.notify_quiet import is_quiet_now
    profile = {"quiet_start": 22, "quiet_end": 8, "allow_critical_override": False}
    with _frozen_hour(23):
        assert is_quiet_now(profile, critical=True) is True


def test_quiet_hours_outside_window_never_quiet():
    from shared.notify_quiet import is_quiet_now
    profile = {"quiet_start": 22, "quiet_end": 8, "allow_critical_override": True}
    with _frozen_hour(12):
        assert is_quiet_now(profile, critical=False) is False
