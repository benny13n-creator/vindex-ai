# -*- coding: utf-8 -*-
"""
Sprint 6L — F-6J-002 and F-6J-003: cross-doc degraded 402/429 into 500.

THE DEFECT
UsageService.consume raises HTTPException(402) with no credits and (429) on
cooldown or a daily/monthly limit. In both cross-doc endpoints the call sits
inside a try whose only handler was `except Exception`, so a billing rejection
came back as a generic 500 "Greška pri analizi dokumenata".

AUTHORIZATION IS NOT INVOLVED, AND THAT WAS VERIFIED RATHER THAN ASSUMED
cross_doc_analiza works on documents pasted into the request body -- there is no
predmet_id and no owner check to swallow. cross_doc_predmet does have one, but
the owner-scoped filter (.eq("predmet_id").eq("user_id")) and its 422 outcome
for a foreign case are raised ABOVE the try, so they never entered the generic
handler. Test 9 pins that down so the fix cannot be credited with something it
did not do -- and so a future edit that moves the check into the try is caught.

MOCK DISCIPLINE
consume is mocked to raise the EXACT HTTPException production raises. A mock
that returned a value would make the defect unreproducible and the test vacuous.
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


def _no_credits(*a, **k):
    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail="Potrošili ste sve kredite.")


def _rate_limited(*a, **k):
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Previše zahteva. Sačekajte trenutak.")


class _Meter:
    def __init__(self, boom=False):
        self.provider = 0
        self.boom = boom

    def sync(self, *a, **k):
        self.provider += 1
        if self.boom:
            raise RuntimeError("analysis engine down")
        return {"konflikti": [], "preporuke": []}


class _Chain:
    """Permissive query builder: any method chains, execute() returns the rows."""

    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        if name == "execute":
            return lambda: MagicMock(data=self._data)
        return lambda *a, **k: self


def _http(path):
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": path, "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


def _status(out, raised):
    if raised is not None:
        return raised.status_code
    return getattr(out, "status_code", 200)


# ── /api/analiza/cross-doc ────────────────────────────────────────────────

async def _run_analiza(cd, meter, consume):
    with ExitStack() as st:
        st.enter_context(patch.object(cd, "_cross_doc_sync", meter.sync))
        st.enter_context(patch("shared.usage.UsageService.consume", consume))
        try:
            req = cd.CrossDocReq(
                dokumenti=[
                    cd.DokumentUnos(naziv="Ugovor A", tekst="Tekst prvog ugovora. " * 20),
                    cd.DokumentUnos(naziv="Ugovor B", tekst="Tekst drugog ugovora. " * 20),
                ],
                pravno_pitanje="Postoji li konflikt izmedju ova dva ugovora?",
            )
            return await cd.cross_doc_analiza(req, _http("/api/analiza/cross-doc"),
                                              {"user_id": "user-A", "email": "a@b.rs"}), None
        except HTTPException as exc:
            return None, exc


@pytest.mark.anyio
async def test_1_analiza_no_credits_returns_402():
    import routers.cross_doc as cd

    out, raised = await _run_analiza(cd, _Meter(), _no_credits)
    assert _status(out, raised) == 402, f"got {_status(out, raised)}"
    assert raised is not None


@pytest.mark.anyio
async def test_2_analiza_rate_limited_returns_429():
    import routers.cross_doc as cd

    out, raised = await _run_analiza(cd, _Meter(), _rate_limited)
    assert _status(out, raised) == 429


@pytest.mark.anyio
async def test_3_analiza_generic_exception_still_returns_500():
    """The narrow fix must not steal the existing error boundary."""
    import routers.cross_doc as cd

    m = _Meter(boom=True)
    out, raised = await _run_analiza(cd, m, AsyncMock(return_value=49))

    assert raised is None, "an internal failure must not surface as HTTPException"
    assert _status(out, raised) == 500
    assert m.provider == 1


@pytest.mark.anyio
async def test_4_analiza_success_is_unchanged():
    import routers.cross_doc as cd

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run_analiza(cd, m, consume)

    assert raised is None
    assert _status(out, raised) not in (402, 429, 500)
    assert m.provider == 1
    assert consume.await_count == 1, "exactly one charge, no double consume"


# ── /api/analiza/cross-doc/predmet ────────────────────────────────────────

ROWS = [
    {"id": "d1", "naziv_fajla": "Tuzba.pdf", "storage_path": "p/d1"},
    {"id": "d2", "naziv_fajla": "Odgovor.pdf", "storage_path": "p/d2"},
]


async def _run_predmet(cd, meter, consume, rows=None):
    supa = MagicMock()
    supa.table.return_value = _Chain(ROWS if rows is None else rows)
    with ExitStack() as st:
        st.enter_context(patch.object(cd, "_get_supa", return_value=supa))
        st.enter_context(patch("routers.dokument._fetch_session_tekst",
                               return_value="Rekonstruisani tekst dokumenta. " * 30))
        st.enter_context(patch.object(cd, "_cross_doc_sync", meter.sync))
        st.enter_context(patch("shared.usage.UsageService.consume", consume))
        try:
            req = cd.CrossDocPredmetReq(
                predmet_id="predmet-A", dokument_ids=["d1", "d2"],
                pravno_pitanje="Postoji li konflikt izmedju ova dva dokumenta?",
            )
            return await cd.cross_doc_predmet(
                req, _http("/api/analiza/cross-doc/predmet"),
                {"user_id": "user-A", "email": "a@b.rs"}), None
        except HTTPException as exc:
            return None, exc


@pytest.mark.anyio
async def test_5_predmet_no_credits_returns_402():
    import routers.cross_doc as cd

    out, raised = await _run_predmet(cd, _Meter(), _no_credits)
    assert _status(out, raised) == 402, f"got {_status(out, raised)}"


@pytest.mark.anyio
async def test_6_predmet_rate_limited_returns_429():
    import routers.cross_doc as cd

    out, raised = await _run_predmet(cd, _Meter(), _rate_limited)
    assert _status(out, raised) == 429


@pytest.mark.anyio
async def test_7_predmet_generic_exception_still_returns_500():
    import routers.cross_doc as cd

    m = _Meter(boom=True)
    out, raised = await _run_predmet(cd, m, AsyncMock(return_value=49))

    assert raised is None
    assert _status(out, raised) == 500
    assert m.provider == 1


@pytest.mark.anyio
async def test_8_predmet_success_is_unchanged():
    import routers.cross_doc as cd

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run_predmet(cd, m, consume)

    assert raised is None
    assert _status(out, raised) not in (402, 429, 500)
    assert m.provider == 1
    assert consume.await_count == 1


# ── authorization control: unchanged, and proved to be so ─────────────────

@pytest.mark.anyio
async def test_9_foreign_predmet_is_still_rejected_above_the_try():
    """The owner-scoped filter returns no rows for another user's case, and the
    resulting 422 is raised BEFORE the try -- so it was never swallowed and this
    fix did not change it. Provider and billing must both stay untouched."""
    import routers.cross_doc as cd

    m = _Meter()
    consume = AsyncMock(return_value=49)
    out, raised = await _run_predmet(cd, m, consume, rows=[])

    assert raised is not None and raised.status_code == 422, (
        f"a foreign or empty case must be rejected, got {_status(out, raised)}"
    )
    assert m.provider == 0, "no analysis may run for a case with no owned documents"
    assert consume.await_count == 0, "and nothing may be charged"
