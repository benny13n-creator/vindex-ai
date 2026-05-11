# -*- coding: utf-8 -*-
"""Tests for POST /api/dokument/pitanje endpoint.

Uses same pre-import mocking pattern as test_uploaded_doc_api.py.
"""

import sys
import os
from unittest.mock import MagicMock, patch

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

    with patch("uploaded_doc.session.validate_session", return_value=True):
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
    sys.modules["main"].ask_agent.return_value = _HAPPY_RESPONSE
    sys.modules["main"].ask_agent.reset_mock()

    with patch("uploaded_doc.session.validate_session", return_value=True):
        resp = client.post("/api/dokument/pitanje", json={
            "session_id": _VALID_SESSION,
            "pitanje": _VALID_PITANJE,
        })

    assert resp.status_code == 200
    sys.modules["main"].ask_agent.assert_called_once()
    call_args = sys.modules["main"].ask_agent.call_args
    # Third positional arg or 'extra_namespaces' kwarg should be ["tmp_validSession123"]
    extra_ns = (
        call_args.kwargs.get("extra_namespaces")
        or (call_args.args[2] if len(call_args.args) > 2 else None)
    )
    assert extra_ns == [f"tmp_{_VALID_SESSION}"]
