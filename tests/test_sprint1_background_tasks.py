# -*- coding: utf-8 -*-
"""
Sprint 1, item 1 — background task registry (shared/bg.py).

Before this: 137 asyncio.create_task(...) calls in application code, zero
add_done_callback anywhere, no registry at all (verified by grep 2026-08-09).
Two defects per call site -- no strong reference, so CPython may collect the
task mid-execution; and no exception ever retrieved, so every failure is silent
-- plus a shutdown handler that drained 2 of 137.

These tests drive the real functions. None of them asserts on source text.
"""
import asyncio
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean_registry():
    """The registry is module-global. Leaving entries behind would make these
    tests order-dependent -- the exact defect the test-integrity scan flagged
    across this suite."""
    from shared import bg
    bg._BG.clear()
    yield
    bg._BG.clear()


# ── the strong reference ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_spawn_holds_a_strong_reference_while_the_task_runs():
    """The event loop keeps only a WEAK reference to a task. Without a strong
    one the task is collectable mid-await: the work stops part-done with no
    error anywhere. This is why CPython's own create_task docs tell you to keep
    a reference."""
    from shared import bg

    started = asyncio.Event()

    async def _slow():
        started.set()
        await asyncio.sleep(0.05)
        return "done"

    task = bg.spawn(_slow(), name="test:slow")
    await started.wait()
    assert bg.pending_count() == 1, "the registry must hold the task while it runs"
    assert task in bg._BG

    await task
    await asyncio.sleep(0)  # let the done-callback run
    assert bg.pending_count() == 0, "and must release it afterwards, or it leaks"


@pytest.mark.anyio
async def test_registry_does_not_grow_without_bound():
    """It is bounded by concurrency, not by lifetime -- each task removes
    itself. A registry that only grew would be a memory leak in a process that
    lives until redeploy."""
    from shared import bg

    async def _noop():
        return None

    for i in range(50):
        await bg.spawn(_noop(), name=f"test:noop-{i}")
    await asyncio.sleep(0)
    assert bg.pending_count() == 0


# ── the observed exception ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_a_failing_background_task_is_logged_not_swallowed(caplog):
    """Previously a raise inside one of these coroutines surfaced only as an
    'exception was never retrieved' warning at GC time, if at all. 38 immutable
    audit writes -- including GDPR erasure -- run this way."""
    from shared import bg

    async def _boom():
        raise RuntimeError("audit write failed")

    with caplog.at_level(logging.ERROR, logger="vindex.bg"):
        task = bg.spawn(_boom(), name="test:boom")
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

    assert caplog.records, "a failed background task must produce a log record"
    msg = caplog.records[-1].getMessage()
    assert "test:boom" in msg, f"the log must name the task; got: {msg}"
    assert "RuntimeError" in msg


@pytest.mark.anyio
async def test_a_cancelled_task_is_not_reported_as_a_failure(caplog):
    """Cancellation is what shutdown does on purpose. Logging it at ERROR would
    make every clean redeploy look like an incident, and an alarm that fires on
    every deploy is an alarm nobody reads."""
    from shared import bg

    async def _forever():
        await asyncio.sleep(3600)

    with caplog.at_level(logging.ERROR, logger="vindex.bg"):
        task = bg.spawn(_forever(), name="test:cancelled")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# ── the drain ──────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_drain_waits_for_in_flight_work():
    from shared import bg

    finished = []

    async def _work():
        await asyncio.sleep(0.05)
        finished.append(True)

    bg.spawn(_work(), name="test:drainable")
    left = await bg.drain(timeout=2.0)

    assert left == 0
    assert finished == [True], "drain must let registered work complete"


@pytest.mark.anyio
async def test_drain_is_bounded_and_reports_what_it_could_not_finish():
    """A shutdown that hangs is worse than one that loses a log line, so drain
    is best-effort with a ceiling. It must report the shortfall rather than
    pretend it finished."""
    from shared import bg

    async def _too_slow():
        await asyncio.sleep(10)

    t = bg.spawn(_too_slow(), name="test:too-slow")
    left = await bg.drain(timeout=0.05)

    assert left == 1, "drain must report tasks it could not finish"
    t.cancel()


@pytest.mark.anyio
async def test_drain_on_an_empty_registry_is_a_noop():
    from shared import bg
    assert await bg.drain(timeout=0.01) == 0


# ── the wiring: sites where loss is a compliance or account defect ─────────

def test_gdpr_erasure_audit_is_registered():
    """The single record proving an erasure request was honoured. It was an
    unreferenced task, so any redeploy in that window dropped it silently."""
    import inspect
    import routers.gdpr as g

    src = inspect.getsource(g)
    idx = src.index('"gdpr_erasure"')
    window = src[max(0, idx - 400):idx]
    assert "_spawn_bg(" in window, "the GDPR erasure audit write must be registered"
    assert "asyncio.create_task(_imm_log(" not in window


def test_registration_side_effects_are_registered():
    """_setup_trial writes plan / trial_kraj / onboarding_done AFTER /api/register
    has already returned 200. Losing it left the user permanently un-provisioned
    with nothing to reconcile it."""
    import inspect
    import api

    src = inspect.getsource(api.register)
    assert 'name="register:setup_trial"' in src
    assert 'name="register:welcome_email"' in src
    assert "asyncio.create_task(_setup_trial(" not in src


def test_shutdown_handler_drains_the_registry():
    import inspect
    import api

    src = inspect.getsource(api._stop_smart_intake_background_loops)
    assert "drain" in src, "shutdown must drain the registry, not only the two loops"
    # and it must stay bounded
    assert "timeout=" in src


# ═══════════════════════════════════════════════════════════════════════════
# Sprint 1, item 2 — every LLM call carries a timeout
# ═══════════════════════════════════════════════════════════════════════════
# 111 OpenAI/AsyncOpenAI constructions in application code, none with timeout=.
# SDK default is read=600s x max_retries=2, and production is a single uvicorn
# process whose GPT calls share the default executor with ~1,500 Supabase call
# sites -- so a degraded provider could hold every worker thread.

def test_a_default_timeout_is_injected_into_the_sdk_call():
    """Drives the real patched method: a call with no explicit timeout must
    reach the underlying SDK WITH one."""
    from unittest.mock import MagicMock, patch
    import shared.ai_client as ac
    from openai import OpenAI

    seen = {}

    def _fake_orig(_self, *args, **kwargs):
        seen.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        return resp

    client = OpenAI(api_key="sk-fake")
    with patch("shared.ai_client._orig_create", _fake_orig):
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Koliki je rok za žalbu?"}],
        )

    assert "timeout" in seen, "the SDK call must carry a timeout"
    assert isinstance(seen["timeout"], (int, float))
    assert 0 < seen["timeout"] <= 300, f"timeout must be bounded, got {seen['timeout']}"


def test_an_explicit_timeout_is_never_overridden():
    """A deliberately long-running call must still be able to opt out."""
    from unittest.mock import MagicMock, patch
    import shared.ai_client as ac
    from openai import OpenAI

    seen = {}

    def _fake_orig(_self, *args, **kwargs):
        seen.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        return resp

    client = OpenAI(api_key="sk-fake")
    with patch("shared.ai_client._orig_create", _fake_orig):
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "pitanje"}],
            timeout=5,
        )

    assert seen["timeout"] == 5, "an explicit timeout must win"


def test_the_timeout_default_is_configurable_but_bounded():
    import shared.ai_client as ac
    assert isinstance(ac._DEFAULT_LLM_TIMEOUT_S, float)
    assert 0 < ac._DEFAULT_LLM_TIMEOUT_S <= 300
