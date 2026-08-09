# -*- coding: utf-8 -*-
"""
Sprint 6E — Copilot authorization gate.

THE DEFECT
_load_predmet_context did an owner-scoped lookup but returned "" on failure and
let execution continue. That is a context filter, not a gate:

    consume -> _load_predmet_context ("" on foreign) -> _detect_intent (AI!)
            -> dispatch -> handler AI call

A foreign predmet_id leaked no content, but it still spent the model and wrote
an audit trail for a case whose ownership was never proved.

TWO THINGS THIS FILE HAS TO PROVE, NOT ASSERT
1. _detect_intent is itself a provider call and runs BEFORE any handler, so
   "provider_calls == 0" only holds if the gate precedes it. Every unauthorized
   test therefore counts BOTH provider surfaces, not just the handler's.
2. HTTPException subclasses Exception, so a raise inside the helper's own try
   would be swallowed by its `except Exception` and silently return "". The
   authorized/unauthorized pair below is what distinguishes a real gate from
   that failure mode -- a test that only checked the unauthorized side would
   pass just as happily against a helper that never called the model at all.

HARNESS NOTE
_handle_pravno_pitanje dispatches main.ask_agent through asyncio.to_thread, so
that mock is SYNC. _pozovi_gpt4o_mini is awaited directly, so that one is async.
The thread hop is also the reason test 7 exists: contextvars are not guaranteed
across every concurrency boundary, and the subject has to survive this one.
"""
import asyncio
import os
import sys
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _subject():
    from shared.ai_provenance import current_context
    return current_context().get("predmet_id")


class _Spy:
    """One counter across BOTH provider surfaces: _detect_intent and the handler.

    Records the subject visible at each call so binding and count are proved by
    the same instrument.
    """

    def __init__(self, intent="PRAVNO_PITANJE"):
        self.calls = 0
        self.subjects = []
        self.intent = intent

    def _record(self):
        self.calls += 1
        self.subjects.append(_subject())

    async def gpt(self, *a, **k):
        self._record()
        r = MagicMock()
        r.choices = [MagicMock()]
        # First call is the classifier; later ones are _handle_ostalo's answer.
        r.choices[0].message.content = self.intent if self.calls == 1 else "Odgovor."
        return r

    def ask(self, *a, **k):
        self._record()
        return {"status": "success", "data": "odgovor", "izvori": []}


def _supa(mode: str):
    """mode: 'owned' | 'missing' (data=None) | 'raises' (what .single() really does)."""
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
        ex.side_effect = Exception("PGRST116: JSON object requested, 0 rows")
    supa = MagicMock()
    supa.table.return_value = chain
    return supa


def _http():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/copilot", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


def _env(cp, spy, mode):
    return [
        patch.object(cp, "_get_supa", return_value=_supa(mode)),
        patch.object(cp, "_pozovi_gpt4o_mini", spy.gpt),
        patch("main.ask_agent", spy.ask),
        patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)),
    ]


async def _call(cp, predmet_id="predmet-A", user_id="user-A"):
    from shared.ai_provenance import set_request_context
    set_request_context(user_id=user_id)
    return await cp.copilot_chat(
        cp.CopilotReq(poruka="Koliki je rok za zalbu na presudu?", predmet_id=predmet_id),
        _http(), {"user_id": user_id, "email": "a@b.rs"},
    )


async def _run(cp, spy, mode="owned", predmet_id="predmet-A", user_id="user-A"):
    with ExitStack() as st:
        for p in _env(cp, spy, mode):
            st.enter_context(p)
        try:
            return await _call(cp, predmet_id, user_id), None
        except Exception as exc:
            return None, exc


# ── 1: authorized — the model MUST be reached (guards against a vacuous suite) ──

@pytest.mark.anyio
async def test_1_authorized_reaches_the_provider():
    import routers.copilot as cp

    spy = _Spy()
    out, raised = await _run(cp, spy)

    assert raised is None, f"an owned case must not fail: {raised!r}"
    assert spy.calls >= 2, (
        f"classifier + handler must both run for an owned case, got {spy.calls}"
    )


# ── 2: foreign case — the core claim ──────────────────────────────────────

@pytest.mark.anyio
async def test_2_foreign_predmet_reaches_no_provider_call():
    """user A sends a predmet owned by user B. .single() raises on 0 rows, which
    is the path the real database takes, so this is the realistic attack."""
    import routers.copilot as cp

    spy = _Spy()
    out, raised = await _run(cp, spy, mode="raises", predmet_id="predmet-OD-USERA-B")

    assert spy.calls == 0, "THE INVARIANT: zero provider calls for a foreign case"
    assert isinstance(raised, HTTPException) and raised.status_code == 404


@pytest.mark.anyio
async def test_2b_foreign_predmet_returning_no_row_also_gates():
    """The other shape the client can produce (maybe_single-style empty data)."""
    import routers.copilot as cp

    spy = _Spy()
    out, raised = await _run(cp, spy, mode="missing", predmet_id="predmet-OD-USERA-B")

    assert spy.calls == 0
    assert isinstance(raised, HTTPException) and raised.status_code == 404


# ── 3: nonexistent case ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_3_nonexistent_predmet_reaches_no_provider_call():
    import routers.copilot as cp

    spy = _Spy()
    out, raised = await _run(cp, spy, mode="raises", predmet_id="00000000-nema-ovoga")

    assert spy.calls == 0
    assert isinstance(raised, HTTPException) and raised.status_code == 404


def test_3b_unauthorized_and_nonexistent_are_indistinguishable():
    """No oracle: 'exists but not yours' must look exactly like 'does not exist'."""
    import routers.copilot as cp

    async def _both():
        a = await _run(cp, _Spy(), mode="raises", predmet_id="tudji")
        b = await _run(cp, _Spy(), mode="missing", predmet_id="nepostojeci")
        return a[1], b[1]

    foreign, missing = asyncio.run(_both())
    assert foreign.status_code == missing.status_code == 404
    assert foreign.detail == missing.detail


# ── 4: both Copilot paths, on the real call chain ─────────────────────────

@pytest.mark.anyio
async def test_4a_pravno_pitanje_binds_the_verified_subject():
    import routers.copilot as cp

    spy = _Spy(intent="PRAVNO_PITANJE")
    out, raised = await _run(cp, spy)

    assert raised is None
    # The classifier runs before the case scope opens; the handler runs inside it.
    assert spy.subjects[0] is None, "the subject must not be set during classification"
    assert spy.subjects[-1] == "predmet-A", (
        f"the handler call must carry the verified case, got {spy.subjects}"
    )


@pytest.mark.anyio
async def test_4b_ostalo_binds_the_verified_subject():
    import routers.copilot as cp

    spy = _Spy(intent="OSTALO")
    out, raised = await _run(cp, spy)

    assert raised is None
    assert spy.subjects[-1] == "predmet-A", (
        f"_handle_ostalo must carry the verified case, got {spy.subjects}"
    )


@pytest.mark.anyio
async def test_4c_ostalo_is_gated_too():
    import routers.copilot as cp

    spy = _Spy(intent="OSTALO")
    out, raised = await _run(cp, spy, mode="raises", predmet_id="tudji")

    assert spy.calls == 0, "the gate precedes classification, so intent cannot matter"


# ── 5: predmet_id=None stays a legitimate general-purpose call ─────────────

@pytest.mark.anyio
async def test_5_case_less_copilot_is_not_gated_and_stays_unbound():
    """CASE A from the brief: the dispatcher has explicit `if req.predmet_id else`
    fallbacks, so a case-less Copilot call is a supported flow. It must not
    acquire an ownership check it cannot satisfy."""
    import routers.copilot as cp

    spy = _Spy()
    out, raised = await _run(cp, spy, predmet_id=None)

    assert raised is None, f"a case-less call must still work: {raised!r}"
    assert spy.calls >= 2, "and must still reach the model"
    assert set(spy.subjects) == {None}, (
        f"and must record no subject at all, got {spy.subjects}"
    )


# ── 6: cleanup ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_6_subject_does_not_survive_the_endpoint():
    import routers.copilot as cp

    await _run(cp, _Spy())
    assert _subject() is None


# ── 7: the subject survives the to_thread hop ─────────────────────────────

@pytest.mark.anyio
async def test_7_subject_crosses_the_to_thread_boundary():
    """_handle_pravno_pitanje runs ask_agent in a worker thread. If contextvars
    did not propagate there, the binding would be recorded but the AI call would
    execute with an empty context."""
    import routers.copilot as cp

    seen = {}

    class _T(_Spy):
        def ask(self, *a, **k):
            seen["thread"] = __import__("threading").current_thread().name
            seen["subject"] = _subject()
            return super().ask(*a, **k)

    await _run(cp, _T())
    assert seen["subject"] == "predmet-A", (
        f"the subject must be visible inside the worker thread, got {seen}"
    )


# ── 8: parallel isolation ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_8_parallel_requests_never_cross_subjects():
    import routers.copilot as cp

    spy = _Spy()
    with ExitStack() as st:
        for p in _env(cp, spy, "owned"):
            st.enter_context(p)
        await asyncio.gather(
            _call(cp, predmet_id="predmet-A", user_id="user-A"),
            _call(cp, predmet_id=None, user_id="user-B"),
        )

    assert "predmet-A" in spy.subjects
    assert None in spy.subjects, "the case-less request must not inherit a case"
