# -*- coding: utf-8 -*-
"""
Final Beta Gate — F27 (MEDIUM), weekly-digest half: posalji_nedeljni_sazetak's
predmet_hronologija/rocista queries never filtered by predmeti.status -- a
case closed today still showed up in next Monday's digest email listing its
deadline/hearing next week. Same aktivni_ids idiom the daily reminder cron
(posalji_podsetnike, same file) already used.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "POST", "path": "/email-notif/nedeljni-sazetak", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _chain_mock(data):
    m = MagicMock()
    for meth in ("select", "eq", "gte", "lte", "order", "limit", "in_"):
        getattr(m, meth).return_value = m
    m.not_ = m  # supabase-py's .not_ is a property returning the same builder, not a method call
    m.execute.return_value = MagicMock(data=data)
    return m


@pytest.mark.anyio
async def test_weekly_digest_filters_hronologija_and_rocista_to_active_cases():
    from routers import email_notif as en

    tables = {}

    def _table(name):
        if name in tables:
            return tables[name]
        if name == "korisnik_email_notif":
            m = _chain_mock([{"user_id": "u1"}])
        elif name == "profiles":
            m = _chain_mock([{"id": "u1", "email": "advokat@vindex.rs", "full_name": "Advokat"}])
        elif name == "predmeti":
            m = _chain_mock([{"id": "p-active", "user_id": "u1", "status": "aktivan"}])
        elif name == "email_notif_log":
            m = _chain_mock([])  # no dup sent yet
        elif name == "predmet_hronologija":
            m = _chain_mock([{"dogadjaj": "Rok", "datum_iso": "2026-08-10", "vaznost": "kritičan", "predmet_id": "p-active"}])
        elif name == "rocista":
            m = _chain_mock([{"sud": "Sud A", "datum": "2026-08-11", "vreme": None, "status": "zakazano"}])
        elif name == "billing_entries":
            m = _chain_mock([])
        else:
            m = _chain_mock([])
        tables[name] = m
        return m

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(en, "_get_supa", return_value=supa), \
         patch.object(en, "_smtp_send", return_value=None):
        result = await en.posalji_nedeljni_sazetak(_req(), user={"user_id": "founder", "email": "founder@vindex.rs"})

    assert result["poslato"] == 1
    assert result["greske"] == 0

    # predmeti was queried with the active-case exclusion filter (not_.in_)
    tables["predmeti"].not_.in_.assert_called_once_with("status", ["zatvoren", "arhiviran", "odbijen"])

    # predmet_hronologija (used for BOTH rokovi and hitnih) and rocista were
    # each filtered to the active-case id set -- called at least once with
    # exactly that list.
    hron_in_calls = [c for c in tables["predmet_hronologija"].in_.call_args_list if c.args[0] == "predmet_id"]
    assert hron_in_calls, "predmet_hronologija must be filtered by predmet_id"
    assert all(c.args[1] == ["p-active"] for c in hron_in_calls)

    rocista_in_calls = [c for c in tables["rocista"].in_.call_args_list if c.args[0] == "predmet_id"]
    assert rocista_in_calls, "rocista must be filtered by predmet_id"
    assert all(c.args[1] == ["p-active"] for c in rocista_in_calls)


@pytest.mark.anyio
async def test_weekly_digest_zero_active_cases_sends_empty_digest_not_a_crash():
    from routers import email_notif as en

    tables = {}

    def _table(name):
        if name in tables:
            return tables[name]
        if name == "korisnik_email_notif":
            m = _chain_mock([{"user_id": "u1"}])
        elif name == "profiles":
            m = _chain_mock([{"id": "u1", "email": "advokat@vindex.rs", "full_name": "Advokat"}])
        elif name == "predmeti":
            m = _chain_mock([])  # zero active cases
        elif name == "email_notif_log":
            m = _chain_mock([])
        elif name == "billing_entries":
            m = _chain_mock([])
        else:
            m = _chain_mock([])
        tables[name] = m
        return m

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(en, "_get_supa", return_value=supa), \
         patch.object(en, "_smtp_send", return_value=None):
        result = await en.posalji_nedeljni_sazetak(_req(), user={"user_id": "founder", "email": "founder@vindex.rs"})

    assert result["poslato"] == 1
    assert result["greske"] == 0
    # predmet_hronologija/rocista must never even be queried when there are
    # zero active cases (no .in_("predmet_id", []) edge case).
    assert "predmet_hronologija" not in tables
    assert "rocista" not in tables
