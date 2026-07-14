# -*- coding: utf-8 -*-
"""Tests for POST /api/dokument/pitanje endpoint.

Uses same pre-import mocking pattern as test_uploaded_doc_api.py.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ─── Pre-import environment + module mocks ───────────────────────────────────
os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

_mock_main = MagicMock()
_mock_main.ask_agent.return_value = {
    "status": "success",
    "data": "Prema Vašem dokumentu, zaposleni ima pravo na otkazni rok.",
    "confidence": "HIGH",
    "top_score": 0.92,
    "top_article": "Član 3",
    "top_law": "ugovor.docx",
}
sys.modules.setdefault("main", _mock_main)
sys.modules.setdefault("app.services.audit_log", MagicMock())
sys.modules.setdefault("templates.podnesci", MagicMock())
sys.modules.setdefault("knowledge.vks_standards", MagicMock())
sys.modules.setdefault("pinecone", MagicMock())
sys.modules.setdefault("supabase", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402 — must come after mocks
from fastapi.testclient import TestClient

# Override get_current_user so these unit tests don't need a real JWT.
# dokument_pitanje now uses PermissionService.require("document_analysis"), whose
# inner dependency closure resolves user via shared.deps.get_current_user — overriding
# that (not the retired require_credits) satisfies every PermissionService.require(...)
# route regardless of feature_key. get_policy() still runs its kill-switch check even
# for this user, so feature_registry must also be seeded — see fixture below.
#
# NOTE: this user is NOT relied on to be treated as founder. shared.deps.FOUNDER_EMAILS
# is read from os.environ ONCE at shared.deps import time — whichever test file in the
# full suite happens to import it first wins, so a same-file "is founder" assumption is
# order-dependent and unsafe. Instead PermissionService's tier/addon lookup
# (shared.permissions._ensure_profile, imported by name into that module) is patched
# directly, which works regardless of founder status or import order.
from shared.deps import require_credits as _shared_require_credits, get_current_user as _shared_get_current_user
_FAKE_USER = {"user_id": "test-user-id", "email": "test@test.com", "role": "pro"}
_FAKE_PROFILE = {
    "credits_remaining": 100, "is_pro": True,
    "subscription_type": "enterprise", "addons": [], "subscription_expires_at": None,
}

import time as _time
import shared.feature_registry as _fr


@pytest.fixture(autouse=True)
def _restore_overrides():
    """api.app.dependency_overrides is process-global — several other test files
    (test_search.py, test_portfolio.py, etc.) pop get_current_user in their own
    autouse teardown, which silently wipes any override set once at import time.
    Re-asserting before every test (matching this codebase's established idiom)
    keeps this file order-independent regardless of collection order."""
    api.app.dependency_overrides[_shared_require_credits] = lambda: _FAKE_USER
    api.app.dependency_overrides[api.require_credits]     = lambda: _FAKE_USER
    api.app.dependency_overrides[_shared_get_current_user] = lambda: _FAKE_USER
    _fr._CACHE["document_analysis"] = {
        "feature_key": "document_analysis", "aktivno": True, "status": "ACTIVE",
        "addon": None, "minimum_plan": None, "krediti": 1,
        "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o", "estimated_cost_usd": 0.01,
    }
    _fr._CACHE_LOADED_AT = _time.monotonic()
    with patch("shared.permissions._ensure_profile", return_value=_FAKE_PROFILE):
        yield
    api.app.dependency_overrides.pop(_shared_get_current_user, None)


client = TestClient(api.app, raise_server_exceptions=True)

_VALID_SESSION = "validSession123"
_VALID_PITANJE = "Koji je otkazni rok prema ugovoru?"

_HAPPY_RESPONSE = {
    "status": "success",
    "data": "Prema Vašem dokumentu, zaposleni ima pravo na otkazni rok.",
    "confidence": "HIGH",
    "top_score": 0.92,
    "top_article": "Član 3",
    "top_law": "ugovor.docx",
}


# ─── Test 1: session not found → 404 ─────────────────────────────────────────

def test_pitanje_session_not_found():
    with patch("uploaded_doc.session.validate_session", return_value=False):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": "doesNotExist",
            "pitanje": _VALID_PITANJE,
        })
    assert resp.status_code == 404
    assert "sesija" in resp.json()["detail"].lower() or "sesij" in resp.json()["detail"].lower()


# ─── Test 2: expired session → 404 ───────────────────────────────────────────

def test_pitanje_expired_session():
    with patch("uploaded_doc.session.validate_session", return_value=False):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": "expiredSession",
            "pitanje": _VALID_PITANJE,
        })
    assert resp.status_code == 404


# ─── Test 3: happy path → 200 with data ──────────────────────────────────────

def test_pitanje_happy_path():
    sys.modules["main"].ask_agent.return_value = _HAPPY_RESPONSE

    with patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": _VALID_SESSION,
            "pitanje": _VALID_PITANJE,
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body
    assert len(body["data"]) > 10


# ─── Test 4: invalid shape (missing fields) → 422 ────────────────────────────

def test_pitanje_invalid_shape():
    resp = client.post("/api/dokument/pitanje", json={"session_id": "abc"})
    assert resp.status_code == 422


# ─── Test 5: oversized question → 422 ────────────────────────────────────────

def test_pitanje_oversized():
    with patch("uploaded_doc.session.validate_session", return_value=True):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": _VALID_SESSION,
            "pitanje": "X" * 2001,
        })
    assert resp.status_code == 422


# ─── Test 6: confidence bias — ask_agent called with extra_namespaces ─────────

def test_pitanje_passes_extra_namespace_to_ask_agent():
    """Endpoint must call ask_agent with extra_namespaces=[f'tmp_{session_id}']."""
    from unittest.mock import MagicMock as _MM
    mock_ask = _MM(return_value=_HAPPY_RESPONSE)
    # Patch main.ask_agent directly — the handler does `from main import ask_agent`
    # inside the function body, so patching main.ask_agent is the correct target.
    with patch("main.ask_agent", mock_ask), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": _VALID_SESSION,
            "pitanje": _VALID_PITANJE,
        })

    assert resp.status_code == 200
    mock_ask.assert_called_once()
    call_args = mock_ask.call_args
    extra_ns = (
        call_args.kwargs.get("extra_namespaces")
        or (call_args.args[2] if len(call_args.args) > 2 else None)
    )
    assert extra_ns == [f"tmp_{_VALID_SESSION}"]
