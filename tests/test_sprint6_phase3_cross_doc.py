# -*- coding: utf-8 -*-
"""
Sprint 6, Phase 3, batch 1 — subject binding for /api/analiza/cross-doc/predmet.

WHY THIS ENDPOINT FIRST
routers/cross_doc.py had ZERO case_context declarations, so every
cross-document analysis produced a provenance row with predmet_id NULL. The
audit trail could not answer which case an AI comparison of two client documents
had been performed for. Case Genome, Court Predictor and Copilot turned out to
be bound already, so this was the highest-risk genuinely unbound path in the
priority domains.

WHY req.predmet_id IS AUTHORITATIVE HERE
It is not asserted, it is enforced by code that already existed: the document
fetch filters .eq("predmet_id", req.predmet_id).eq("user_id", user_id) and the
handler raises 422 unless at least two rows come back. A predmet belonging to
another user therefore yields no rows and the request fails before any AI call.
Nothing about authorization was changed by this sprint.

These tests drive the real handler. None of them asserts that the source
contains the string "case_context".
"""
import asyncio
import contextvars
import os
import sys
from starlette.requests import Request as StarletteRequest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _subject():
    from shared.ai_provenance import current_context
    ctx = current_context()
    return (ctx.get("user_id"), ctx.get("predmet_id"))


def _rows(n=2):
    return [{"id": f"dok-{i}", "naziv_fajla": f"f{i}.pdf", "storage_path": f"p{i}"} for i in range(n)]


def _supa_with(rows):
    res = MagicMock()
    res.data = rows
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = res
    supa = MagicMock()
    supa.table.return_value = chain
    return supa


def _req(predmet_id="predmet-A"):
    from routers.cross_doc import CrossDocPredmetReq
    return CrossDocPredmetReq(
        predmet_id=predmet_id,
        dokument_ids=["dok-0", "dok-1"],
        pravno_pitanje="Da li se iskazi razlikuju?",
    )


# ── the premise, established rather than assumed ──────────────────────────

@pytest.mark.anyio
async def test_asyncio_to_thread_propagates_the_context():
    """The whole fix rests on this. asyncio.to_thread copies the current
    contextvars.Context, unlike a raw ThreadPoolExecutor.submit — which does
    not, and which is what broke the RAG path in Sprint 2. If this were false,
    wrapping around to_thread would bind nothing."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        seen = await asyncio.to_thread(_subject)

    assert seen == ("user-A", "predmet-A")


# ── TEST 1 — success carries the subject ──────────────────────────────────

@pytest.mark.anyio
async def test_success_binds_the_analysis_to_the_case():
    import routers.cross_doc as cd

    captured = {}

    def _fake_sync(dokumenti, pitanje, _extra):
        captured["subject"] = _subject()
        return {"ok": True}

    with patch.object(cd, "_get_supa", return_value=_supa_with(_rows())), \
         patch("routers.dokument._fetch_session_tekst", return_value="Tekst dokumenta " * 40), \
         patch.object(cd, "_cross_doc_sync", _fake_sync), \
\
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=5)):
        out = await _call(cd)

    assert out == {"ok": True}
    assert captured["subject"][1] == "predmet-A", (
        f"the AI call must run bound to the case, got {captured['subject']}"
    )


async def _call(cd, predmet_id="predmet-A", user_id="user-A"):
    """Drives the real handler with its document-text step stubbed."""
    from shared.ai_provenance import set_request_context
    set_request_context(user_id=user_id)
    req = StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/analiza/cross-doc/predmet", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })
    return await cd.cross_doc_predmet(
        _req(predmet_id),
        req,
        {"user_id": user_id, "email": "a@b.rs"},
    )


# ── TEST 2 — failure carries the SAME subject ─────────────────────────────

@pytest.mark.anyio
async def test_provider_failure_still_carries_the_subject():
    """A provenance trail that only records successes cannot answer what
    happened when something went wrong. The error record must name the same
    case."""
    import routers.cross_doc as cd

    captured = {}

    def _boom(dokumenti, pitanje, _extra):
        captured["subject"] = _subject()
        raise RuntimeError("provider down")

    with patch.object(cd, "_get_supa", return_value=_supa_with(_rows())), \
         patch("routers.dokument._fetch_session_tekst", return_value="Tekst dokumenta " * 40), \
         patch.object(cd, "_cross_doc_sync", _boom), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=5)):
        out = await _call(cd)

    # The handler converts the failure into a 500 JSONResponse.
    assert getattr(out, "status_code", None) == 500
    assert captured["subject"][1] == "predmet-A", (
        "the failing AI call must still have been bound to the case"
    )


# ── TEST 3 — a foreign case never reaches the provider ────────────────────

@pytest.mark.anyio
async def test_a_case_that_is_not_yours_is_rejected_before_the_ai_call():
    """The ownership filter returns no rows for another user's predmet, so the
    handler must fail before any provider call. Asserting the provider was NOT
    invoked is the point — a 4xx alone would not prove it."""
    from fastapi import HTTPException
    import routers.cross_doc as cd

    called = {"n": 0}

    def _must_not_run(*a, **k):
        called["n"] += 1
        return {}

    with patch.object(cd, "_get_supa", return_value=_supa_with([])), \
         patch("routers.dokument._fetch_session_tekst", return_value="x"), \
         patch.object(cd, "_cross_doc_sync", _must_not_run), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=5)):
        with pytest.raises(HTTPException) as exc:
            await _call(cd, predmet_id="predmet-TUDJ")

    assert exc.value.status_code in (404, 422)
    assert called["n"] == 0, "the provider must never be reached for a foreign case"


# ── TEST 4 — the subject does not outlive the request ─────────────────────

@pytest.mark.anyio
async def test_the_case_subject_does_not_leak_into_the_next_operation():
    """Otherwise a later AI call with no case would be filed against whichever
    case the previous request happened to analyse."""
    import routers.cross_doc as cd

    with patch.object(cd, "_get_supa", return_value=_supa_with(_rows())), \
         patch("routers.dokument._fetch_session_tekst", return_value="Tekst dokumenta " * 40), \
         patch.object(cd, "_cross_doc_sync", lambda *a: {"ok": True}), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=5)):
        await _call(cd)

    assert _subject()[1] is None, "predmet_id must not survive the endpoint"


# ── adversarial: two cases, two users, concurrently ───────────────────────

@pytest.mark.anyio
async def test_two_concurrent_analyses_never_cross_subjects():
    """The security invariant, driven through the real handler rather than
    through the context manager directly."""
    import routers.cross_doc as cd

    seen = {}

    def _record(dokumenti, pitanje, _extra):
        subj = _subject()
        seen.setdefault(subj[0], []).append(subj[1])
        return {"ok": True}

    with patch.object(cd, "_get_supa", return_value=_supa_with(_rows())), \
         patch("routers.dokument._fetch_session_tekst", return_value="Tekst dokumenta " * 40), \
         patch.object(cd, "_cross_doc_sync", _record), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=5)):
        await asyncio.gather(
            _call(cd, predmet_id="predmet-A", user_id="user-A"),
            _call(cd, predmet_id="predmet-B", user_id="user-B"),
        )

    assert seen.get("user-A") == ["predmet-A"], seen
    assert seen.get("user-B") == ["predmet-B"], seen
