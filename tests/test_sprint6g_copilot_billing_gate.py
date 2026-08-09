# -*- coding: utf-8 -*-
"""
Sprint 6G — no billing on authorization failure.

THE DEFECT, which Sprint 6E itself opened.
6E moved the ownership check into a real gate but left it BELOW
UsageService.consume:

    consume -> gate -> 404

so a foreign or stale predmet_id was charged a credit for a request that never
reached a single provider call. The two refund branches lower down wrap only
handler(), which sits behind the gate, so nothing gave the credit back.

WHY REORDER RATHER THAN REFUND
consume() is an immediate atomic decrement -- no reservation, no transaction.
"charge, then authorize, then refund" leaves a transient state that a failed
refund turns into a silent loss, and refund is documented as best-effort.
"authorize, then charge" has no such window. consume() at line 1435 is the only
consumption point in the file (two refunds, one consume, grep-confirmed), so the
swap cannot introduce a double charge.

BILLING IS ASSERTED AS STATE, NOT AS CALL COUNT.
The fake below is a ledger: consume decrements, refund increments. Every test
asserts credits_before vs credits_after, which is what the invariant is actually
about. Call counts are asserted too, but only to pin down double-charge and
double-refund separately from the net.
"""
import asyncio
import os
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Ledger:
    """Persistent credit state, not a spy. consume decrements, refund adds back."""

    START = 50

    def __init__(self):
        self.credits = self.START
        self.consumes = 0
        self.refunds = 0
        self.events = []

    async def consume(self, user_id, email, feature, **k):
        self.consumes += 1
        self.credits -= 1
        self.events.append("billing")
        return self.credits

    async def refund(self, user_id, email, feature, **k):
        self.refunds += 1
        self.credits += 1
        return None


class _Spy:
    """Counts both provider surfaces: _detect_intent and the handler."""

    def __init__(self, ledger, intent="PRAVNO_PITANJE", boom=False):
        self.calls = 0
        self.intent = intent
        self.boom = boom
        self.ledger = ledger

    async def gpt(self, *a, **k):
        self.calls += 1
        self.ledger.events.append("provider")
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].message.content = self.intent if self.calls == 1 else "Odgovor."
        return r

    def ask(self, *a, **k):
        self.calls += 1
        self.ledger.events.append("provider")
        if self.boom:
            raise RuntimeError("provider down")
        return {"status": "success", "data": "odgovor", "izvori": []}


def _supa(mode):
    chain = MagicMock()
    ex = chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute
    if mode == "owned":
        res = MagicMock()
        res.data = {"naziv": "Marko protiv Ane", "opis": "Spor",
                    "tip": "parnica", "status": "aktivan"}
        ex.return_value = res
    elif mode == "missing":
        res = MagicMock()
        res.data = None
        ex.return_value = res
    else:
        ex.side_effect = Exception("PGRST116: 0 rows")
    supa = MagicMock()
    supa.table.return_value = chain
    return supa


def _http():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/copilot", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


async def _run(cp, ledger, spy, mode="owned", predmet_id="predmet-A", user_id="user-A"):
    from shared.ai_provenance import set_request_context
    with ExitStack() as st:
        st.enter_context(patch.object(cp, "_get_supa", return_value=_supa(mode)))
        st.enter_context(patch.object(cp, "_pozovi_gpt4o_mini", spy.gpt))
        st.enter_context(patch("main.ask_agent", spy.ask))
        st.enter_context(patch("shared.usage.UsageService.consume", ledger.consume))
        st.enter_context(patch("shared.usage.UsageService.refund", ledger.refund))
        set_request_context(user_id=user_id)
        try:
            out = await cp.copilot_chat(
                cp.CopilotReq(poruka="Koliki je rok za zalbu?", predmet_id=predmet_id),
                _http(), {"user_id": user_id, "email": "a@b.rs"},
            )
            return out, None
        except Exception as exc:
            return None, exc


# ── 1: foreign subject — the whole point of the sprint ────────────────────

@pytest.mark.anyio
async def test_1_foreign_predmet_costs_nothing():
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)
    before = led.credits
    out, raised = await _run(cp, led, spy, mode="raises", predmet_id="predmet-OD-B")

    assert isinstance(raised, HTTPException) and raised.status_code == 404
    assert spy.calls == 0, "no provider call"
    assert led.credits == before, f"credits must be untouched: {before} -> {led.credits}"
    assert led.consumes == 0, "and consume must never have run"
    assert led.refunds == 0, "no refund needed, because nothing was charged"


# ── 2: unknown subject ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_2_unknown_predmet_costs_nothing():
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)
    before = led.credits
    out, raised = await _run(cp, led, spy, mode="missing", predmet_id="ne-postoji")

    assert isinstance(raised, HTTPException) and raised.status_code == 404
    assert spy.calls == 0
    assert led.credits == before
    assert led.consumes == 0


# ── 3: authorized — must still be charged exactly once ────────────────────

@pytest.mark.anyio
async def test_3_authorized_reaches_provider_and_is_charged_once():
    """Guards the opposite failure: a billing bypass would pass tests 1 and 2."""
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)
    out, raised = await _run(cp, led, spy)

    assert raised is None, f"an owned case must not fail: {raised!r}"
    assert spy.calls >= 2, "classifier + handler must both run"
    assert led.consumes == 1, "exactly one consumption point"
    assert led.refunds == 0
    assert led.credits == _Ledger.START - 1, "the existing billing contract stands"


# ── 4: case-less Copilot keeps its old semantics ──────────────────────────

@pytest.mark.anyio
async def test_4_caseless_copilot_billing_is_unchanged():
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)
    out, raised = await _run(cp, led, spy, predmet_id=None)

    assert raised is None, f"a case-less call must still work: {raised!r}"
    assert spy.calls >= 2, "and must still reach the model"
    assert led.consumes == 1, "and must still be charged exactly once"
    assert led.credits == _Ledger.START - 1


# ── 5: provider failure — existing refund semantics untouched ─────────────

@pytest.mark.anyio
async def test_5_provider_failure_still_refunds():
    """6G must not alter what happens AFTER the charge."""
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led, boom=True)
    out, raised = await _run(cp, led, spy)

    assert raised is not None, "the failure must surface"
    assert led.consumes == 1
    assert led.refunds == 1, "the pre-existing refund branch must still fire"
    assert led.credits == _Ledger.START, "charge and refund must net to zero"


# ── 6: ordering, proved by observable behaviour ───────────────────────────

@pytest.mark.anyio
async def test_6_authorization_precedes_billing_precedes_provider():
    """Not code appearance -- the recorded event sequence."""
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)

    async def _gate(predmet_id, user_id):
        led.events.append("authorization")
        return "[Predmet: X]"

    with patch.object(cp, "_load_predmet_context", _gate):
        await _run(cp, led, spy)

    assert led.events[0] == "authorization", led.events
    assert led.events[1] == "billing", led.events
    assert led.events[2] == "provider", led.events


@pytest.mark.anyio
async def test_6b_unauthorized_never_reaches_billing_or_provider():
    import routers.copilot as cp

    led = _Ledger()
    spy = _Spy(led)
    await _run(cp, led, spy, mode="raises", predmet_id="tudji")

    assert led.events == [], f"nothing at all may happen after the gate fails: {led.events}"
