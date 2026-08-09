# -*- coding: utf-8 -*-
"""
Sprint 6C-1 — authorization precondition for /api/nacrt and /api/podnesak.

THE DEFECT
req.predmet_id on both endpoints is Optional[str] = Field(None, max_length=100),
a free string from the request body. Nothing verified it belonged to the caller
before the GPT call. The only ownership check in routers/drafting.py lives
inside _stage_draft_for_review, which runs AFTER generation and as a
fire-and-forget task.

  order was:  SUBJECT (unverified) -> AI -> OWNERSHIP
  order must be:  AUTHENTICATION -> AUTHORIZATION -> SUBJECT -> AI -> PROVENANCE

/api/nacrt already bound provenance to req.predmet_id, so user B could send user
A's predmet UUID and write audit rows attributed to A's case. No data leaked --
the model only ever sees req.opis, text the caller supplied -- but a forgeable
audit trail is not an audit trail.

HARNESS NOTE, recorded because the first attempt at this file was wrong.
routers/drafting.py::_pokreni is `await asyncio.to_thread(fn, *args)`, so the
function it dispatches runs IN A THREAD and must be SYNCHRONOUS. Patching
_drafting_generate with an `async def` produced a coroutine that to_thread
returned without ever executing, so the assertions never ran and the tests
failed for a reason that had nothing to do with the production change. The mocks
below are sync, which is what the real call chain looks up.

Every unauthorized-path test asserts PROVIDER CALL COUNT == 0. A status code
alone would not prove the model was never reached, and that is the whole claim.
"""
import asyncio
import os
import sys
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
    """The predmeti lookup the canonical helper performs."""
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
        "path": "/api/nacrt", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


async def _call_nacrt(dr, predmet_id="predmet-A", user_id="user-A"):
    from shared.ai_provenance import set_request_context
    set_request_context(user_id=user_id)
    return await dr.nacrt(
        dr.NacrtReq(vrsta="tuzba", opis="Opis predmeta koji je dovoljno dug.",
                    predmet_id=predmet_id),
        _http(), {"user_id": user_id, "email": "a@b.rs"},
    )


class _Provider:
    """Counts real invocations and records the subject at the moment of the call.

    Sync on purpose: _pokreni dispatches through asyncio.to_thread.
    """

    def __init__(self, result=None):
        self.calls = 0
        self.subjects = []
        self._result = result or {"status": "success", "data": "Nacrt tuzbe..."}

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.subjects.append(_subject())
        return self._result


def _env(dr, provider, owned=True):
    """The minimum patch set that leaves the real control flow intact."""
    return [
        patch("routers.copilot_ambient._get_supa", return_value=_supa(owned)),
        patch.object(dr, "_drafting_generate", provider),
        patch.object(dr, "_recent_generation_exists", new=AsyncMock(return_value=False)),
        patch.object(dr, "_stage_draft_for_review", new=AsyncMock()),
        patch("shared.usage.UsageService.balance", new=AsyncMock(return_value=50)),
        patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=49)),
    ]


async def _run(dr, provider, owned=True, predmet_id="predmet-A", user_id="user-A"):
    """Returns (outcome, raised) — the endpoint may signal failure either way."""
    from contextlib import ExitStack
    with ExitStack() as st:
        for p in _env(dr, provider, owned):
            st.enter_context(p)
        try:
            return await _call_nacrt(dr, predmet_id, user_id), None
        except Exception as exc:
            return None, exc


# ── A. authorized: the good path must still work ──────────────────────────

@pytest.mark.anyio
async def test_a_authorized_predmet_is_bound_and_the_model_runs():
    import routers.drafting as dr

    prov = _Provider()
    out, raised = await _run(dr, prov)

    assert raised is None, f"an owned case must not fail: {raised!r}"
    assert prov.calls == 1, "the model must run for an authorized case"
    assert prov.subjects == ["predmet-A"], (
        f"provenance must carry the VERIFIED case, got {prov.subjects}"
    )


# ── B. cross-user attack: the core claim ──────────────────────────────────

@pytest.mark.anyio
async def test_b_cross_user_predmet_never_reaches_the_model():
    """user A sends user B's predmet_id. The canonical helper finds no row for
    (id, caller) and raises 404 BEFORE case_context and before the model.

    Asserted on the call count, not the status: a 404 could be produced by a
    dozen other things, and only the count proves nothing was generated."""
    import routers.drafting as dr

    prov = _Provider()
    out, raised = await _run(dr, prov, owned=False, predmet_id="predmet-OD-USERA-B")

    assert prov.calls == 0, "THE INVARIANT: no model call for an unauthorized case"
    assert prov.subjects == [], "and therefore no provenance subject at all"
    assert raised is not None or getattr(out, "status_code", 200) >= 400, (
        "the request must fail closed, not return a normal result"
    )


@pytest.mark.anyio
async def test_b2_no_provenance_context_survives_a_rejected_request():
    import routers.drafting as dr

    prov = _Provider()
    await _run(dr, prov, owned=False, predmet_id="tudji")
    assert _subject() is None, "a rejected case must leave no subject behind"


# ── C. nonexistent case ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_c_nonexistent_predmet_never_reaches_the_model():
    import routers.drafting as dr

    prov = _Provider()
    out, raised = await _run(dr, prov, owned=False, predmet_id="00000000-nema-ovoga")

    assert prov.calls == 0
    assert raised is not None or getattr(out, "status_code", 200) >= 400


# ── D. no subject: the ad-hoc path must be untouched ──────────────────────

@pytest.mark.anyio
async def test_d_case_less_drafting_is_not_gated_and_stays_unbound():
    """predmet_id=None is a legitimate ad-hoc draft. It must not acquire an
    ownership check it cannot satisfy, and it must remain unbound."""
    import routers.drafting as dr

    checked = {"n": 0}

    async def _count(predmet_id, user_id):
        checked["n"] += 1

    prov = _Provider()
    from contextlib import ExitStack
    with ExitStack() as st:
        st.enter_context(patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", _count))
        for p in _env(dr, prov):
            st.enter_context(p)
        await _call_nacrt(dr, predmet_id=None)

    assert checked["n"] == 0, "the case-less path must not be gated"
    assert prov.calls == 1, "and must still generate"
    assert prov.subjects == [None], "and must stay unbound"


# ── E. provider failure keeps the verified subject ────────────────────────

@pytest.mark.anyio
async def test_e_provider_failure_carries_the_same_verified_subject():
    import routers.drafting as dr

    prov = _Provider(result={"status": "error", "message": "Sistem je trenutno zauzet"})
    out, raised = await _run(dr, prov)

    assert prov.calls == 1
    assert prov.subjects == ["predmet-A"], (
        "a failed generation must be attributed to the same verified case"
    )


# ── ordering, proved rather than asserted in a comment ────────────────────

@pytest.mark.anyio
async def test_authorization_runs_before_the_subject_is_established():
    """authentication -> authorization -> case_context -> AI."""
    import routers.drafting as dr

    order = []

    async def _check(predmet_id, user_id):
        order.append(("authorization", _subject()))

    class _P(_Provider):
        def __call__(self, *a, **k):
            order.append(("ai", _subject()))
            return super().__call__(*a, **k)

    prov = _P()
    from contextlib import ExitStack
    with ExitStack() as st:
        st.enter_context(patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", _check))
        for p in _env(dr, prov):
            st.enter_context(p)
        await _call_nacrt(dr)

    assert [s for s, _ in order] == ["authorization", "ai"]
    assert order[0][1] is None, "the subject must NOT be set during authorization"
    assert order[1][1] == "predmet-A", "and must be set by the time the model runs"


# ── podnesak carries the same precondition ────────────────────────────────

def test_podnesak_authorizes_before_generating():
    """Court filings: an audit row attributed to the wrong case is worse here.
    The handler makes two sequential GPT calls behind a heavier setup, so the
    invariant is proved on the executed source order of the real function."""
    import inspect
    import routers.drafting as dr

    src = inspect.getsource(dr.podnesak)
    executable = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    auth = executable.index("_proveri_vlasnistvo_predmeta")
    first_ai = executable.index("_pozovi_drafting_api")
    assert auth < first_ai, "authorization must precede the first generation call"
