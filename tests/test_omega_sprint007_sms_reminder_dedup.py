# -*- coding: utf-8 -*-
"""
Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
Trigger Engine. Tests for routers/sms.py::posalji_podsetnike -- a real,
previously-undiscovered dedup bug found this sprint: the endpoint's own
`vec_poslato` set was function-local (reset every call), so 2 separate
invocations of the SAME cron endpoint on the same day (an accidental
duplicate trigger, a manual re-run, a retry) sent the identical SMS/
WhatsApp reminder twice -- `notification_log` recorded every send but
nothing ever read it back before sending again. Fixed: a persistent,
cross-run dedup check against `notification_log` itself, using a
date-qualified `tip` ("rok_podsetnik:<datum>") as the exact-match key --
mission's own Scenario 2 ("Isti rok. Retry 100 puta. -> i dalje jedna
aktivna notifikacija"), applied to this specific channel.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.4.2 — SVI ROKOVI U OVIM FIXTURE-IMA SU POTVRDJENI
#
# Od 6.4.2 nijedan rok ne moze proizvesti izvrsivu posledicu bez ljudske
# potvrde. Ovaj fajl meri SMS dedup ugovor, ne tu granicu (nju mere
# `test_faza642_*` i `test_faza621_*`), pa se modeluje advokat koji je rokove
# vec potvrdio.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _rokovi_su_potvrdjeni(monkeypatch):
    import routers.sms as _m
    if hasattr(_m, "_potvrdjeni_ids"):
        monkeypatch.setattr(_m, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})



@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
              "path": "/sms/send-reminders", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _founder_user():
    return {"user_id": "founder-uid", "email": "founder@vindex.rs"}


class _Chain:
    def __init__(self, data):
        self._data = data
    def select(self, *_a, **_kw): return self
    def eq(self, *_a, **_kw): return self
    def in_(self, *_a, **_kw): return self
    def like(self, *_a, **_kw): return self
    def gte(self, *_a, **_kw): return self
    def lte(self, *_a, **_kw): return self
    def order(self, *_a, **_kw): return self
    def execute(self):
        return MagicMock(data=self._data)


def _make_sms_supa(profili, rokovi, existing_log_rows):
    log_inserts = []

    def _table(name):
        if name == "korisnik_sms_profil":
            return _Chain(profili)
        if name == "predmet_hronologija":
            return _Chain(rokovi)
        if name == "notification_log":
            t = MagicMock()
            t.select.return_value = _Chain(existing_log_rows)
            def _insert(row):
                log_inserts.append(row)
                leaf = MagicMock()
                leaf.execute.return_value = MagicMock(data=[row])
                return leaf
            t.insert.side_effect = _insert
            return t
        return _Chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa, log_inserts


@pytest.mark.anyio
async def test_second_cron_run_same_day_does_not_resend_sms():
    """The actual bug: 2 separate calls to posalji_podsetnike on the same
    day, for the identical deadline, must send exactly ONE SMS total."""
    from routers.sms import posalji_podsetnike
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    profili = [{"user_id": "u1", "telefon": "+381601234567", "whatsapp": False,
                "quiet_start": None, "quiet_end": None, "allow_critical_override": True}]
    rokovi = [{"id": "rok-o7-a", "izvor": "HUMAN_DIRECT", "user_id": "u1", "dogadjaj": "Odgovor na tužbu", "datum_iso": tomorrow, "predmet_id": "pred-1"}]

    with patch("routers.sms._FOUNDER_EMAILS", {"founder@vindex.rs"}), \
         patch("routers.sms._send_sms", return_value=True) as mock_send:
        # First call: nothing logged yet.
        supa1, log1 = _make_sms_supa(profili, rokovi, existing_log_rows=[])
        with patch("routers.sms._get_supa", return_value=supa1), \
             patch("shared.notify_quiet._get_supa", return_value=supa1):
            result1 = await posalji_podsetnike(_req(), _founder_user())
        assert result1["poslato"] == 1
        assert mock_send.call_count == 1

        # Second call, SAME DAY: notification_log now has the row the first
        # call wrote -- simulate that being visible to the dedup query.
        assert log1, "expected the first call to have logged a send"
        supa2, log2 = _make_sms_supa(profili, rokovi, existing_log_rows=[
            {"user_id": "u1", "ref_id": "pred-1", "tip": f"rok_podsetnik:{tomorrow}"}
        ])
        with patch("routers.sms._get_supa", return_value=supa2), \
             patch("shared.notify_quiet._get_supa", return_value=supa2):
            result2 = await posalji_podsetnike(_req(), _founder_user())

    # The real fix: the second run must NOT send again.
    assert result2["poslato"] == 0
    assert mock_send.call_count == 1  # still just the one real send total


@pytest.mark.anyio
async def test_different_deadline_next_day_still_sends():
    """Dedup must be scoped to the EXACT deadline occurrence, not the whole
    predmet -- a second, later reminder for the SAME case but a DIFFERENT
    deadline date must still go out (mission's own worked example: a lawyer
    gets reminded both 2 days out and again 1 day out for the SAME hearing,
    which are legitimately 2 different log entries with different dates)."""
    from routers.sms import posalji_podsetnike
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    day_after = (date.today() + timedelta(days=2)).isoformat()
    profili = [{"user_id": "u1", "telefon": "+381601234567", "whatsapp": False,
                "quiet_start": None, "quiet_end": None, "allow_critical_override": True}]
    rokovi = [{"id": "rok-o7-b", "izvor": "HUMAN_DIRECT", "user_id": "u1", "dogadjaj": "Ročište", "datum_iso": tomorrow, "predmet_id": "pred-1"}]

    # Already sent the reminder for the day_after occurrence (a different
    # date), not for tomorrow's -- must NOT block today's send.
    existing = [{"user_id": "u1", "ref_id": "pred-1", "tip": f"rok_podsetnik:{day_after}"}]

    with patch("routers.sms._FOUNDER_EMAILS", {"founder@vindex.rs"}), \
         patch("routers.sms._send_sms", return_value=True) as mock_send:
        supa, _log = _make_sms_supa(profili, rokovi, existing_log_rows=existing)
        with patch("routers.sms._get_supa", return_value=supa), \
             patch("shared.notify_quiet._get_supa", return_value=supa):
            result = await posalji_podsetnike(_req(), _founder_user())

    assert result["poslato"] == 1
    assert mock_send.call_count == 1


@pytest.mark.anyio
async def test_log_tip_is_date_qualified_not_the_old_bare_string():
    from routers.sms import posalji_podsetnike
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    profili = [{"user_id": "u1", "telefon": "+381601234567", "whatsapp": False,
                "quiet_start": None, "quiet_end": None, "allow_critical_override": True}]
    rokovi = [{"id": "rok-o7-b", "izvor": "HUMAN_DIRECT", "user_id": "u1", "dogadjaj": "Ročište", "datum_iso": tomorrow, "predmet_id": "pred-1"}]

    with patch("routers.sms._FOUNDER_EMAILS", {"founder@vindex.rs"}), \
         patch("routers.sms._send_sms", return_value=True):
        supa, log_inserts = _make_sms_supa(profili, rokovi, existing_log_rows=[])
        with patch("routers.sms._get_supa", return_value=supa), \
             patch("shared.notify_quiet._get_supa", return_value=supa):
            await posalji_podsetnike(_req(), _founder_user())

    assert log_inserts
    assert log_inserts[0]["tip"] == f"rok_podsetnik:{tomorrow}"
