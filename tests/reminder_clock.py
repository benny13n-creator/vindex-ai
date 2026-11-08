"""Deterministic clock shared by daily-reminder fixtures and delivery code."""
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(params=[
    datetime(2026, 11, 7, 22, 30, tzinfo=timezone.utc),
    datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc),
], ids=["before-belgrade-midnight", "after-belgrade-midnight"])
def reminder_clock(request, monkeypatch):
    from routers import email_notif

    instant = request.param
    monkeypatch.setattr(email_notif, "_sada", lambda: instant)
    return instant


def reminder_day(days=0):
    from routers import email_notif

    return email_notif._danas_beograd(email_notif._sada()) + timedelta(days=days)
