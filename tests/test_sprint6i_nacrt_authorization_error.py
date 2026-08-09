# -*- coding: utf-8 -*-
"""
Sprint 6I — F-6H-001: /api/nacrt turned an authorization denial into a 500.

THE DEFECT
_proveri_vlasnistvo_predmeta raises HTTPException(404) at the top of nacrt(),
inside the try that spans the whole handler body. Its only handler was
`except Exception`, and HTTPException subclasses Exception, so the denial was
swallowed and returned as _greska_odgovor(500, "greška na serveru").

WHY THE EXISTING 6C-1 TEST DID NOT CATCH IT
test_b_cross_user_predmet_never_reaches_the_model asserts
`raised is not None or getattr(out, "status_code", 200) >= 400`. _greska_odgovor
returns a JSONResponse with status_code=500, so 500 satisfied `>= 400` and the
test passed against the wrong contract. This file asserts the status EXACTLY.

WHAT WAS AND WAS NOT BROKEN
Never broken: the security invariant. consume and the provider both sit behind
the raise point inside the same try, so a denial reached neither -- 6H proved
this statically and tests 1 and 2 below prove it again by counting. Broken: the
error contract, and the fact that every cross-user attempt was logged via
logger.exception as if the server had failed.
"""
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


class _Meter:
    """Counts the provider and the single consumption point separately."""

    def __init__(self, boom=False):
        self.provider = 0
        self.consumes = 0
        self.boom = boom

    def generate(self, *a, **k):
        self.provider += 1
        if self.boom:
            raise RuntimeError("generator down")
        return {"status": "success", "data": "Nacrt tuzbe..."}

    async def consume(self, *a, **k):
        self.consumes += 1
        return 49


def _supa(owned: bool):
    """The predmeti lookup the canonical ownership helper performs."""
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


async def _run(dr, meter, owned=True, predmet_id="predmet-A", user_id="user-A"):
    """Returns (response, raised) -- the endpoint may signal either way."""
    from shared.ai_provenance import set_request_context
    with ExitStack() as st:
        st.enter_context(patch("routers.copilot_ambient._get_supa", return_value=_supa(owned)))
        st.enter_context(patch.object(dr, "_drafting_generate", meter.generate))
        st.enter_context(patch.object(dr, "_recent_generation_exists", new=AsyncMock(return_value=False)))
        st.enter_context(patch.object(dr, "_stage_draft_for_review", new=AsyncMock()))
        st.enter_context(patch("shared.usage.UsageService.balance", new=AsyncMock(return_value=50)))
        st.enter_context(patch("shared.usage.UsageService.consume", meter.consume))
        set_request_context(user_id=user_id)
        try:
            out = await dr.nacrt(
                dr.NacrtReq(vrsta="tuzba", opis="Opis predmeta koji je dovoljno dug.",
                            predmet_id=predmet_id),
                _http(), {"user_id": user_id, "email": "a@b.rs"},
            )
            return out, None
        except HTTPException as exc:
            return None, exc


def _status(out, raised):
    """One number regardless of which channel the endpoint used."""
    if raised is not None:
        return raised.status_code
    return getattr(out, "status_code", 200)


# ── 1: cross-user — the finding ───────────────────────────────────────────

@pytest.mark.anyio
async def test_1_cross_user_returns_404_not_500():
    import routers.drafting as dr

    m = _Meter()
    out, raised = await _run(dr, m, owned=False, predmet_id="predmet-OD-USERA-B")

    assert _status(out, raised) == 404, (
        f"an authorization denial must be 404, got {_status(out, raised)}"
    )
    assert m.provider == 0, "and must never reach the generator"
    assert m.consumes == 0, "and must never be charged"


# ── 2: nonexistent subject ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_2_nonexistent_returns_404_not_500():
    import routers.drafting as dr

    m = _Meter()
    out, raised = await _run(dr, m, owned=False, predmet_id="00000000-nema-ovoga")

    assert _status(out, raised) == 404
    assert m.provider == 0
    assert m.consumes == 0


# ── 3: no enumeration oracle ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_3_cross_user_and_nonexistent_are_indistinguishable():
    """The fix must not make 'exists but not yours' look different from
    'does not exist' -- both go through the same helper and must stay equal."""
    import routers.drafting as dr

    a = _status(*await _run(dr, _Meter(), owned=False, predmet_id="tudji-postojeci"))
    b = _status(*await _run(dr, _Meter(), owned=False, predmet_id="nepostojeci"))

    assert a == b == 404, f"cross-user={a} nonexistent={b}"


# ── 4: positive control — the working path is untouched ───────────────────

@pytest.mark.anyio
async def test_4_authorized_request_still_works():
    import routers.drafting as dr

    m = _Meter()
    out, raised = await _run(dr, m)

    assert raised is None, f"an owned case must not raise: {raised!r}"
    assert _status(out, raised) != 404
    assert m.provider == 1, "the generator must still run"
    assert m.consumes == 1, "and the existing billing contract must stand"


# ── 5: generic exception control — the 500 path must survive ──────────────

@pytest.mark.anyio
async def test_5_unexpected_exception_is_still_a_generic_500():
    """The whole point of the narrow fix: only HTTPException changes channel."""
    import routers.drafting as dr

    m = _Meter(boom=True)
    out, raised = await _run(dr, m)

    assert raised is None, "an internal failure must not surface as an HTTPException"
    assert _status(out, raised) == 500, "the pre-existing generic handler must still fire"
    assert m.provider == 1, "the failure must have happened at the generator"
    assert m.consumes == 0, "and a failed generation must not be charged"
