# -*- coding: utf-8 -*-
"""
Operation Lawyer Zero, LZ-001 (2026-08-03): the automatic email deadline
reminder (routers/email_notif.py::posalji_podsetnike) is a real, already-
scheduled, already-working cron -- but its query filtered on
vaznost=="kritican" exactly, while every AI-extraction deadline-writing path
uses a different string (Smart Intake: "vazan"; the primary intake_kreiraj
flow: "bitan"; the deadline-chain calculator's own internal mapping:
"kljucan"/"normalan"/"info"). The reminder had never fired for an
AI-extracted deadline.

Fix is deliberately read-side only (broaden the cron's filter), not a writer
change -- api.py's own existing _VAZNOST_ORDER and a separate filter already
depend on "bitan" existing as a real value, so changing any writer risked
breaking that without a full reader audit this mission doesn't have budget
for tonight.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/email-notif/send-reminders", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_cron_user():
    return {"user_id": "cron", "email": "cron@vindex.rs", "role": "cron"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(rok_vaznost: str, target_iso: str):
    """Supabase mock: one active email profile (dan_7 enabled), one profile
    with a real email, and one predmet_hronologija row with the given
    vaznost value on the target date -- the exact shape a real AI-extracted
    deadline produces."""
    supa = MagicMock()
    inserted_log_rows = []

    def _table(name):
        t = MagicMock()
        if name == "korisnik_email_notif":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": "uid-001", "aktivan": True, "dan_7": True, "dan_3": False, "dan_1": False}
            ]
        elif name == "profiles":
            t.select.return_value.execute.return_value.data = [
                {"id": "uid-001", "email": "advokat@vindex.rs"}
            ]
        elif name == "email_notif_log":
            # duplicate-check: nothing sent yet
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            def _insert(row):
                inserted_log_rows.append(row)
                i = MagicMock()
                i.execute.return_value = MagicMock()
                return i
            t.insert.side_effect = _insert
        elif name == "predmet_hronologija":
            sel = MagicMock()
            def _eq_uid(col, val):
                assert col == "user_id"
                return sel
            sel.eq.side_effect = _eq_uid
            def _in_vaznost(col, values):
                assert col == "vaznost"
                sel._matched = rok_vaznost in values
                return sel
            sel.in_.side_effect = _in_vaznost
            def _eq_datum(col, val):
                assert col == "datum_iso"
                result = MagicMock()
                if getattr(sel, "_matched", False) and val == target_iso:
                    result.execute.return_value.data = [
                        {"dogadjaj": "Rok za žalbu", "datum_iso": target_iso, "predmet_id": "pred-001"}
                    ]
                else:
                    result.execute.return_value.data = []
                return result
            sel.eq.side_effect = _eq_uid
            # allow chaining .eq(...).in_(...).eq(...)
            outer = MagicMock()
            outer.select.return_value.eq.return_value = sel
            sel.in_ = MagicMock(side_effect=_in_vaznost)
            sel.eq = MagicMock(side_effect=_eq_datum)
            return outer
        return t

    supa.table.side_effect = _table
    return supa, inserted_log_rows


@pytest.mark.anyio
async def test_reminder_fires_for_smart_intake_deadline_vazan():
    """Smart Intake's AI-extracted deadlines use vaznost='vazan' -- the
    reminder must now fire for them."""
    from routers.email_notif import posalji_podsetnike

    target_iso = (date.today() + timedelta(days=7)).isoformat()
    mock_supa, log_rows = _make_supa("važan", target_iso)

    with patch("routers.email_notif._get_supa", return_value=mock_supa), \
         patch("routers.email_notif._smtp_send") as mock_send:
        result = await posalji_podsetnike(_fake_request(), _fake_cron_user())

    assert result["poslato"] == 1, "reminder must fire for a 'važan' (Smart Intake) deadline"
    mock_send.assert_called_once()


@pytest.mark.anyio
async def test_reminder_fires_for_intake_kreiraj_deadline_bitan():
    """The primary AI-assisted case-creation path writes vaznost='bitan' --
    the reminder must now fire for it too."""
    from routers.email_notif import posalji_podsetnike

    target_iso = (date.today() + timedelta(days=7)).isoformat()
    mock_supa, log_rows = _make_supa("bitan", target_iso)

    with patch("routers.email_notif._get_supa", return_value=mock_supa), \
         patch("routers.email_notif._smtp_send") as mock_send:
        result = await posalji_podsetnike(_fake_request(), _fake_cron_user())

    assert result["poslato"] == 1, "reminder must fire for a 'bitan' (intake_kreiraj) deadline"
    mock_send.assert_called_once()


@pytest.mark.anyio
async def test_reminder_still_fires_for_original_kritican_value():
    """The original, always-worked value must keep working -- this fix is
    additive, not a replacement."""
    from routers.email_notif import posalji_podsetnike

    target_iso = (date.today() + timedelta(days=7)).isoformat()
    mock_supa, log_rows = _make_supa("kritičan", target_iso)

    with patch("routers.email_notif._get_supa", return_value=mock_supa), \
         patch("routers.email_notif._smtp_send") as mock_send:
        result = await posalji_podsetnike(_fake_request(), _fake_cron_user())

    assert result["poslato"] == 1
    mock_send.assert_called_once()


@pytest.mark.anyio
async def test_reminder_does_not_fire_for_informativan():
    """Informational (non-actionable) deadlines must NOT page a lawyer by
    email -- the exclusion is deliberate, not an oversight."""
    from routers.email_notif import posalji_podsetnike

    target_iso = (date.today() + timedelta(days=7)).isoformat()
    mock_supa, log_rows = _make_supa("informativan", target_iso)

    with patch("routers.email_notif._get_supa", return_value=mock_supa), \
         patch("routers.email_notif._smtp_send") as mock_send:
        result = await posalji_podsetnike(_fake_request(), _fake_cron_user())

    assert result["poslato"] == 0
    mock_send.assert_not_called()


def test_actionable_vaznost_constant_excludes_informational_values():
    from routers.email_notif import _ACTIONABLE_VAZNOST
    assert "informativan" not in _ACTIONABLE_VAZNOST
    assert "info" not in _ACTIONABLE_VAZNOST
    for v in ("kritičan", "važan", "bitan", "kljucan", "normalan"):
        assert v in _ACTIONABLE_VAZNOST
