# -*- coding: utf-8 -*-
"""
Sprint 6M — F-6J-004 and F-6J-005: /api/analiza and /api/sazmi degraded
402/429 into 500. Last two findings of the 6J chain.

THE DEFECT
UsageService.consume raises HTTPException(402) with no credits and (429) on
cooldown or a daily/monthly limit. In both handlers the call sits inside a try
whose only handler was `except Exception`, so a billing rejection was rewritten
as a generic 500.

CONSUME IS THE ONLY HTTPException SOURCE IN EITHER BLOCK, VERIFIED NOT ASSUMED
UsageService.balance -- called in /api/analiza's else branch -- raises none
(zero raise sites). Neither request model carries a predmet_id, so there is no
ownership check inside either try that this change could affect: AnalizaReq is
tekst+pitanje, SazmiReq is odgovor+format. That makes these two the cleanest of
the five 6J findings: pure error contract, nothing else in reach.

TEST HYGIENE
Nothing here touches .env, a real key, the network, or PostgreSQL. _OAI is
patched so /api/sazmi never constructs a real client -- in Sprint 6K a fresh
worktree without .env made every path return the same status for the wrong
reason, which is exactly how a negative control turns into fiction.

The providers are dispatched through asyncio.to_thread, so their mocks are SYNC.
"""
import os
import sys
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


DETAIL_402 = "Potrošili ste sve kredite."
DETAIL_429 = "Previše zahteva. Sačekajte trenutak."


def _no_credits(*a, **k):
    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail=DETAIL_402)


def _rate_limited(*a, **k):
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=DETAIL_429, headers={"Retry-After": "60"})


class _Meter:
    """Counts the real provider surface. Sync: both go through to_thread."""

    def __init__(self, boom=False):
        self.provider = 0
        self.boom = boom

    def analiza(self, *a, **k):
        self.provider += 1
        if self.boom:
            raise RuntimeError("analysis engine down")
        return {"status": "success", "data": "Analiza dokumenta."}

    def drafting(self, *a, **k):
        self.provider += 1
        if self.boom:
            raise RuntimeError("provider down")
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].message.content = "Sažetak za klijenta."
        return r


def _http(path):
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": path, "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


USER = {"user_id": "user-A", "email": "a@b.rs"}


def _status(out, raised):
    if raised is not None:
        return raised.status_code
    return getattr(out, "status_code", 200)


# ── /api/analiza ──────────────────────────────────────────────────────────

async def _run_analiza(dr, meter, consume):
    with ExitStack() as st:
        st.enter_context(patch.object(dr, "ask_analiza", meter.analiza))
        st.enter_context(patch.object(dr, "_audit", new=AsyncMock()))
        st.enter_context(patch("shared.usage.UsageService.consume", consume))
        st.enter_context(patch("shared.usage.UsageService.balance", new=AsyncMock(return_value=50)))
        try:
            req = dr.AnalizaReq(tekst="Tekst ugovora koji se analizira. " * 5,
                                pitanje="Koji su rizici?")
            return await dr.analiza(req, _http("/api/analiza"), USER), None
        except HTTPException as exc:
            return None, exc


@pytest.mark.anyio
async def test_1_analiza_no_credits_returns_402_with_detail_intact():
    import routers.drafting as dr

    m = _Meter()
    out, raised = await _run_analiza(dr, m, _no_credits)

    assert _status(out, raised) == 402, f"got {_status(out, raised)}"
    assert raised is not None, "it must propagate, not be rendered into a body"
    assert raised.detail == DETAIL_402, "the original detail must survive"
    assert m.provider == 1, "the rejection happens at billing, not before"


@pytest.mark.anyio
async def test_2_analiza_rate_limited_returns_429_with_headers_intact():
    import routers.drafting as dr

    out, raised = await _run_analiza(dr, _Meter(), _rate_limited)

    assert _status(out, raised) == 429
    assert raised.detail == DETAIL_429
    assert raised.headers == {"Retry-After": "60"}, (
        f"headers must survive untouched, got {raised.headers}"
    )


@pytest.mark.anyio
async def test_3_analiza_generic_exception_still_returns_500():
    """The fix must not steal the existing error boundary."""
    import routers.drafting as dr

    m = _Meter(boom=True)
    out, raised = await _run_analiza(dr, m, AsyncMock(return_value=49))

    assert raised is None, "an internal failure must not surface as HTTPException"
    assert _status(out, raised) == 500
    assert m.provider == 1


@pytest.mark.anyio
async def test_4_analiza_success_is_unchanged():
    import routers.drafting as dr

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run_analiza(dr, m, consume)

    assert raised is None
    assert _status(out, raised) not in (402, 429, 500)
    assert m.provider == 1
    assert consume.await_count == 1, "exactly one charge, no double consume"


# ── /api/sazmi ────────────────────────────────────────────────────────────

async def _run_sazmi(dr, meter, consume):
    with ExitStack() as st:
        # sazmi does `from openai import OpenAI as _OAI` INSIDE the function, so
        # the module attribute does not exist -- the real target is the source.
        st.enter_context(patch("openai.OpenAI", MagicMock()))
        st.enter_context(patch.object(dr, "_pozovi_drafting_api", meter.drafting))
        st.enter_context(patch("shared.usage.UsageService.consume", consume))
        try:
            req = dr.SazmiReq(odgovor="Pravni odgovor advokata koji treba prepisati.",
                              format="email")
            return await dr.sazmi(req, _http("/api/sazmi"), USER), None
        except HTTPException as exc:
            return None, exc


@pytest.mark.anyio
async def test_5_sazmi_no_credits_returns_402_with_detail_intact():
    import routers.drafting as dr

    m = _Meter()
    out, raised = await _run_sazmi(dr, m, _no_credits)

    assert _status(out, raised) == 402, f"got {_status(out, raised)}"
    assert raised.detail == DETAIL_402
    assert m.provider == 1


@pytest.mark.anyio
async def test_6_sazmi_rate_limited_returns_429_with_headers_intact():
    import routers.drafting as dr

    out, raised = await _run_sazmi(dr, _Meter(), _rate_limited)

    assert _status(out, raised) == 429
    assert raised.detail == DETAIL_429
    assert raised.headers == {"Retry-After": "60"}


@pytest.mark.anyio
async def test_7_sazmi_generic_exception_still_returns_500():
    import routers.drafting as dr

    m = _Meter(boom=True)
    out, raised = await _run_sazmi(dr, m, AsyncMock(return_value=49))

    assert raised is None
    assert _status(out, raised) == 500
    assert m.provider == 1


@pytest.mark.anyio
async def test_8_sazmi_success_is_unchanged():
    import routers.drafting as dr

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run_sazmi(dr, m, consume)

    assert raised is None
    assert isinstance(out, dict) and out.get("status") == "ok", out
    assert out.get("sazetak") == "Sažetak za klijenta."
    assert m.provider == 1
    assert consume.await_count == 1
