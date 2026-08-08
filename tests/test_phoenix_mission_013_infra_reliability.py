# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 013 -- Infra Reliability.
Closes LIVINGSYS-DEBT-040 (no per-call timeout on Dashboard/Workspace's
highest-traffic endpoints) and LIVINGSYS-DEBT-041 (no explicit app-level
timeout on document upload).
LIVINGSYS-DEBT-005 explicitly NOT touched -- the register's own assessment is
that a real fix needs a firm-wide autosave/state-persistence architecture
decision, not a bounded mechanical fix. LIVINGSYS-DEBT-035 explicitly NOT
touched -- blocked on a founder product decision (re-fetch vs. staleness
warning). LIVINGSYS-DEBT-023 explicitly NOT touched -- a genuine new
capability (OCR confidence scoring), not a fix.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope, receive=receive)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-040 -- shared/query_timeout.py primitives
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_gather_with_timeout_returns_real_results_when_fast():
    from shared.query_timeout import gather_with_timeout

    async def _fast(v):
        return v

    results = await gather_with_timeout(_fast(1), _fast(2), _fast(3), timeout=5.0)
    assert list(results) == [1, 2, 3]


@pytest.mark.anyio
async def test_gather_with_timeout_returns_timeout_placeholders_on_hang():
    """Original-scenario reproduction: an unbounded, hung query must not
    hang the whole request forever -- fails open with a TimeoutError
    placeholder for every coroutine, the same shape return_exceptions=True
    callers already handle."""
    from shared.query_timeout import gather_with_timeout

    async def _hangs():
        await asyncio.sleep(3600)

    async def _fast():
        return "ok"

    results = await asyncio.wait_for(
        gather_with_timeout(_hangs(), _fast(), timeout=0.05), timeout=2.0
    )
    assert isinstance(results[0], asyncio.TimeoutError)
    assert isinstance(results[1], asyncio.TimeoutError)  # bounded as a unit, not per-coroutine


@pytest.mark.anyio
async def test_gather_with_timeout_still_returns_real_exceptions_when_not_timed_out():
    """Regression: a genuine per-query failure (not a hang) must still surface
    as ITS OWN exception, not be masked into a generic timeout placeholder."""
    from shared.query_timeout import gather_with_timeout

    async def _fails():
        raise ValueError("real db error")

    async def _ok():
        return "ok"

    results = await gather_with_timeout(_fails(), _ok(), timeout=5.0)
    assert isinstance(results[0], ValueError)
    assert results[1] == "ok"


@pytest.mark.anyio
async def test_single_with_timeout_returns_empty_placeholder_on_hang():
    from shared.query_timeout import single_with_timeout

    async def _hangs():
        await asyncio.sleep(3600)

    result = await asyncio.wait_for(single_with_timeout(_hangs(), timeout=0.05), timeout=2.0)
    assert result.data == []


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-040 -- wired into the 3 named highest-traffic endpoints
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_command_center_degrades_gracefully_on_query_timeout():
    """Original-scenario reproduction: every underlying query times out --
    the endpoint must still return a valid, degraded response instead of
    hanging or crashing. Mocks command_center's own imported gather_with_
    timeout directly (rather than trying to make the REAL 15s default fire
    quickly) -- a default keyword argument is bound once at function
    definition time, so patching the module-level constant after import has
    no effect on it; this is the reliable way to exercise the timeout branch."""
    import routers.dashboard as dashboard

    with patch.object(dashboard, "_get_supa", return_value=MagicMock()), \
         patch.object(dashboard, "gather_with_timeout", new=AsyncMock(
             return_value=(asyncio.TimeoutError("t"),) * 13
         )):
        result = await asyncio.wait_for(
            dashboard.command_center(_req(), {"user_id": "u1"}), timeout=3.0
        )

    # Must return a valid (degraded/empty) response, not hang or crash.
    assert isinstance(result, dict)


@pytest.mark.anyio
async def test_matter_health_score_returns_503_not_404_on_ownership_check_timeout():
    """A timeout on the ownership-check query must be distinguishable from a
    genuine 'case not found' -- misreporting a timeout as 404 would be
    actively misleading to the lawyer. Patches dashboard's own imported
    gather_with_timeout reference (not shared.query_timeout's original --
    the import already bound a separate reference in dashboard's namespace)."""
    import routers.dashboard as dashboard
    from fastapi import HTTPException

    with patch.object(dashboard, "_get_supa", return_value=MagicMock()), \
         patch.object(dashboard, "gather_with_timeout", new=AsyncMock(
             return_value=(asyncio.TimeoutError("t"),) * 6
         )):
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(
                dashboard.matter_health_score("p1", _req(), {"user_id": "u1"}), timeout=3.0
            )

    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_get_workspace_degrades_gracefully_on_query_timeout():
    """Original-scenario reproduction: every underlying query times out (the
    predmeti fetch AND the main 3-way gather) -- the endpoint must still
    return a valid, empty operational board instead of hanging or crashing."""
    import routers.workspace as workspace

    class _Empty:
        data = []

    async def _all_timeout(*coros, **kw):
        return tuple(asyncio.TimeoutError("t") for _ in coros)

    with patch.object(workspace, "_get_supa", return_value=MagicMock()), \
         patch("routers.workspace.single_with_timeout", new=AsyncMock(return_value=_Empty())), \
         patch("routers.workspace.gather_with_timeout", new=_all_timeout):
        result = await asyncio.wait_for(workspace.get_workspace(_req(), {"user_id": "u1"}), timeout=3.0)

    assert result["danas"] == []
    assert result["ukupno_aktivnih"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-041 -- frontend explicit app-level upload timeout
# ═══════════════════════════════════════════════════════════════════════════

def test_fetch_with_timeout_helper_present_and_used_by_pred_upload_doc():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    assert "async function _fetchWithTimeout(url, options, timeoutMs) {" in vindex_js
    assert "controller.abort()" in vindex_js
    assert "_fetchWithTimeout(BASE_URL + '/api/predmeti/' + activePredmetId + '/upload'" in vindex_js


def test_pred_upload_doc_distinguishes_timeout_error_message():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    marker = "async function pred_upload_doc(file) {"
    assert marker in vindex_js
    body = vindex_js.split(marker, 1)[1][:6000]
    assert "AbortError" in body
    assert "predugo trajalo" in body
