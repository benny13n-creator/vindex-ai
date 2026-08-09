# -*- coding: utf-8 -*-
"""
Sprint 6K — F-6J-001: /tts turned a billing rejection into an empty success.

THE DEFECT
UsageService.consume raises HTTPException(402) with no credits and (429) on
cooldown / daily / monthly limit -- six raise sites, verified in shared/usage.py.
The call sits inside voice_tts's try, whose only handler was `except Exception`.
HTTPException subclasses Exception, so the rejection was swallowed and returned
as `_Resp(status_code=204, content=b"")`.

204 is what makes this the worst of the five 6J findings. The other four degrade
into 500, which at least says "something went wrong". Here a user out of credits
received an empty SUCCESS, and the frontend reads 204 as "no audio, fall back to
browser speech" -- indistinguishable from a genuine TTS outage.

WHAT THE MOCK MUST BE
consume is mocked, but it raises the exact HTTPException production raises. A
mock that merely returned would make the defect unreproducible and the test
vacuous.

ORDERING NOTE, recorded because it contradicts an assumption worth correcting.
consume runs AFTER the TTS provider call (line 489 vs 480-487), so a billing
rejection cannot have provider_calls == 0 on this endpoint -- the audio is
already generated and paid for by the time the user is told they cannot afford
it. That is a separate ordering issue, deliberately NOT fixed here; this file
asserts the true current ordering rather than an invariant the code does not
have.
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


class _Meter:
    """Counts the real TTS provider surface."""

    def __init__(self, boom=False):
        self.provider = 0
        self.boom = boom

    def tts(self, *a, **k):
        self.provider += 1
        if self.boom:
            raise RuntimeError("OpenAI TTS unreachable")
        r = MagicMock()
        r.content = b"ID3-audio-bytes"
        return r


def _http():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/tts", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


async def _run(v, meter, consume):
    """consume: an async callable standing in for UsageService.consume."""
    with ExitStack() as st:
        st.enter_context(patch.object(v, "_pozovi_tts_api", meter.tts))
        st.enter_context(patch("shared.usage.UsageService.consume", consume))
        try:
            out = await v.voice_tts(
                v.VoiceTtsReq(text="Poštovani, ovo je test."),
                _http(), {"user_id": "user-A", "email": "a@b.rs"},
            )
            return out, None
        except HTTPException as exc:
            return None, exc


def _status(out, raised):
    if raised is not None:
        return raised.status_code
    return getattr(out, "status_code", 200)


def _no_credits(*a, **k):
    """Exactly what shared/usage.py raises when the balance is exhausted."""
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="Potrošili ste sve kredite.",
    )


def _rate_limited(*a, **k):
    """Exactly what shared/usage.py raises on cooldown / daily / monthly limit."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Previše zahteva. Sačekajte trenutak.",
    )


# ── 1: no credits — the finding ───────────────────────────────────────────

@pytest.mark.anyio
async def test_1_no_credits_returns_402_not_an_empty_success():
    import routers.voice as v

    m = _Meter()
    out, raised = await _run(v, m, _no_credits)

    assert _status(out, raised) == 402, (
        f"a billing rejection must reach the client as 402, got {_status(out, raised)}"
    )
    assert raised is not None, "and must propagate as an HTTPException, not a body"


@pytest.mark.anyio
async def test_1b_no_credits_is_never_reported_as_success():
    """The specific harm: 204 is a 2xx. The client cannot tell it from working."""
    import routers.voice as v

    out, raised = await _run(v, _Meter(), _no_credits)
    code = _status(out, raised)

    assert not (200 <= code < 300), f"a rejection must never be a 2xx, got {code}"


# ── 2: cooldown / rate limit ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_2_rate_limited_returns_429():
    import routers.voice as v

    out, raised = await _run(v, _Meter(), _rate_limited)

    assert _status(out, raised) == 429
    assert raised is not None


# ── 3: generic exception regression — 204 fallback must survive ───────────

@pytest.mark.anyio
async def test_3_genuine_tts_failure_still_returns_204():
    """The narrow fix must not steal the browser-fallback path. A real provider
    outage is NOT an HTTPException and must keep its existing 204."""
    import routers.voice as v

    m = _Meter(boom=True)
    out, raised = await _run(v, m, AsyncMock(return_value=49))

    assert raised is None, "an infrastructure failure must not surface as HTTPException"
    assert _status(out, raised) == 204, "the existing browser-fallback contract stands"
    assert m.provider == 1, "and the failure must have happened at the provider"


# ── 4: success path untouched ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_4_authorized_request_still_returns_audio():
    import routers.voice as v

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run(v, m, consume)

    assert raised is None
    code = _status(out, raised)
    assert code not in (402, 429), f"a paid-up request must not be rejected: {code}"
    assert m.provider == 1, "the provider must be reached"
    assert out.body == b"ID3-audio-bytes", "and the audio must come back unchanged"
    assert consume.await_count == 1, "and billing must still happen exactly once"


# ── 5: the ordering this endpoint actually has ────────────────────────────

@pytest.mark.anyio
async def test_5_provider_runs_before_the_billing_rejection():
    """Documents, rather than asserts away, that consume sits AFTER the provider:
    the audio is generated before the user is told they cannot afford it. Left
    unchanged on purpose -- moving consume is outside this sprint."""
    import routers.voice as v

    m = _Meter()
    out, raised = await _run(v, m, _no_credits)

    assert _status(out, raised) == 402
    assert m.provider == 1, (
        "provider_calls == 0 is NOT achievable here without reordering consume"
    )
