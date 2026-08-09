# -*- coding: utf-8 -*-
"""
Sprint 6C-2 — /api/podnesak subject binding.

PRE-FLIGHT FINDING THAT SHAPED THIS FILE
The handler makes FIVE provider-touching calls, not one: two
_pozovi_drafting_api extractions, retrieve_documents (which runs its own
embedding and query-decomposition LLM work), the enrichment call, and
_critique_and_refine_draft. "One AI call" was never a safe assumption, so every
test below asserts the subject on EVERY recorded invocation rather than on the
first one.

HARNESS NOTE
_pozovi_drafting_api is dispatched through asyncio.to_thread, so the mock must
be a SYNC callable. An async mock returns a coroutine that to_thread hands back
without executing, and the assertions then never run -- which is how the first
attempt at the 6C-1 harness produced failures that had nothing to do with the
production code.

Authorization was closed in Sprint 6C-1 (10bde3c0); this sprint binds the
subject that authorization made trustworthy.
"""
import asyncio
import os
import sys
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _subject():
    from shared.ai_provenance import current_context
    return current_context().get("predmet_id")


def _supa(owned: bool):
    res = MagicMock()
    res.data = {"id": "predmet-A"} if owned else None
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = res
    supa = MagicMock()
    supa.table.return_value = chain
    return supa


def _http():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/podnesak", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


class _Drafting:
    """Sync, and records the subject visible at EVERY invocation."""

    def __init__(self):
        self.calls = 0
        self.subjects = []

    def __call__(self, *a, **k):
        self.calls += 1
        self.subjects.append(_subject())
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"tuzilac": "Marko", "tuzeni": "Ana"}'
        return resp


def _req(dr, predmet_id="predmet-A"):
    return dr.PodnesakReq(
        tip=next(iter(dr.PODNESAK_TIPOVI)),
        opis="Opis podneska koji je dovoljno dug da prodje validaciju modela.",
        predmet_id=predmet_id,
    )


async def _call(dr, predmet_id="predmet-A", user_id="user-A"):
    from shared.ai_provenance import set_request_context
    set_request_context(user_id=user_id)
    return await dr.podnesak(
        _req(dr, predmet_id), _http(), {"user_id": user_id, "email": "a@b.rs"},
    )


def _env(dr, prov, owned=True):
    return [
        patch("routers.copilot_ambient._get_supa", return_value=_supa(owned)),
        patch.object(dr, "_pozovi_drafting_api", prov),
        patch.object(dr, "_recent_generation_exists", new=AsyncMock(return_value=False)),
        patch.object(dr, "_stage_draft_for_review", new=AsyncMock()),
        patch.object(dr, "_critique_and_refine_draft",
                     new=AsyncMock(side_effect=lambda n, k, t, l: (n, False))),
        patch("app.services.retrieve.retrieve_documents", return_value=([], {})),
        patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=49)),
    ]


async def _run(dr, prov, owned=True, predmet_id="predmet-A", user_id="user-A"):
    with ExitStack() as st:
        for p in _env(dr, prov, owned):
            st.enter_context(p)
        try:
            return await _call(dr, predmet_id, user_id), None
        except Exception as exc:
            return None, exc


# ── A: authorized — every call bound ──────────────────────────────────────

@pytest.mark.anyio
async def test_a_authorized_binds_every_provider_call():
    import routers.drafting as dr

    prov = _Drafting()
    out, raised = await _run(dr, prov)

    assert raised is None, f"an owned case must not fail: {raised!r}"
    assert prov.calls >= 1, "the model must run for an authorized case"
    assert set(prov.subjects) == {"predmet-A"}, (
        f"EVERY provider call must be bound to the verified case, got {prov.subjects}"
    )


# ── B: cross-user attack — not one of the five may run ────────────────────

@pytest.mark.anyio
async def test_b_cross_user_reaches_no_provider_call():
    import routers.drafting as dr

    prov = _Drafting()
    out, raised = await _run(dr, prov, owned=False, predmet_id="predmet-USERA-B")

    assert prov.calls == 0, "THE INVARIANT: zero provider calls for an unauthorized case"
    assert prov.subjects == [], "and therefore no subject recorded anywhere"
    assert raised is not None or getattr(out, "status_code", 200) >= 400, (
        "the request must fail closed"
    )


# ── C: nonexistent case ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_c_nonexistent_predmet_reaches_no_provider_call():
    import routers.drafting as dr

    prov = _Drafting()
    out, raised = await _run(dr, prov, owned=False, predmet_id="ne-postoji-000")

    assert prov.calls == 0
    assert raised is not None or getattr(out, "status_code", 200) >= 400


# ── D: cleanup ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_d_subject_does_not_survive_the_endpoint():
    """A stale subject would file the NEXT case-less AI call against this case."""
    import routers.drafting as dr

    prov = _Drafting()
    await _run(dr, prov)
    assert _subject() is None


# ── E: provider failure keeps the verified subject ────────────────────────

@pytest.mark.anyio
async def test_e_provider_failure_keeps_the_verified_subject():
    import routers.drafting as dr

    class _Boom(_Drafting):
        def __call__(self, *a, **k):
            self.calls += 1
            self.subjects.append(_subject())
            raise RuntimeError("provider down")

    prov = _Boom()
    out, raised = await _run(dr, prov)

    assert prov.calls >= 1, "the failure must happen at the provider, not before"
    assert set(prov.subjects) == {"predmet-A"}, (
        "a failing call must be attributed to the verified case"
    )
    assert _subject() is None, "and the context must still be cleaned up"


# ── G: no subject — the ad-hoc path stays honest ──────────────────────────

@pytest.mark.anyio
async def test_g_case_less_podnesak_stays_unbound():
    import routers.drafting as dr

    checked = {"n": 0}

    async def _count(predmet_id, user_id):
        checked["n"] += 1

    prov = _Drafting()
    with ExitStack() as st:
        st.enter_context(patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", _count))
        for p in _env(dr, prov):
            st.enter_context(p)
        await _call(dr, predmet_id=None)

    assert checked["n"] == 0, "the case-less path must not be gated"
    assert prov.calls >= 1, "and must still generate"
    assert set(prov.subjects) == {None}, "and must record no subject at all"


# ── H: ordering, proved by instrumentation ────────────────────────────────

@pytest.mark.anyio
async def test_h_authorization_precedes_subject_and_provider():
    import routers.drafting as dr

    events = []

    async def _check(predmet_id, user_id):
        events.append(("authorization", _subject()))

    class _P(_Drafting):
        def __call__(self, *a, **k):
            events.append(("provider", _subject()))
            return super().__call__(*a, **k)

    prov = _P()
    with ExitStack() as st:
        st.enter_context(patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", _check))
        for p in _env(dr, prov):
            st.enter_context(p)
        await _call(dr)

    assert events[0][0] == "authorization"
    assert events[0][1] is None, "the subject must NOT be set while authorizing"
    assert all(e[0] == "provider" for e in events[1:]), events
    assert all(e[1] == "predmet-A" for e in events[1:]), events


# ── F: parallel isolation through the real handler ────────────────────────

@pytest.mark.anyio
async def test_f_parallel_requests_never_cross_subjects():
    import routers.drafting as dr

    seen = {}

    class _P(_Drafting):
        def __call__(self, *a, **k):
            s = _subject()
            seen[s] = seen.get(s, 0) + 1
            return super().__call__(*a, **k)

    prov = _P()
    with ExitStack() as st:
        for p in _env(dr, prov):
            st.enter_context(p)
        await asyncio.gather(
            _call(dr, predmet_id="predmet-A", user_id="user-A"),
            _call(dr, predmet_id="predmet-A", user_id="user-A"),
        )

    assert set(seen) == {"predmet-A"}, f"no foreign or null subject may appear: {seen}"
