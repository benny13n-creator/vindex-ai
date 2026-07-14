# -*- coding: utf-8 -*-
"""Tests for /api/dokument/upload and /api/dokument/cleanup endpoints.

Uses FastAPI TestClient with mocked ingest + cleanup modules.
Heavy api.py dependencies (main, supabase, pinecone) are pre-mocked
before import so no live connections are needed.
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

# ─── Pre-import environment + module mocks ───────────────────────────────────
os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

_mock_main = MagicMock()
sys.modules.setdefault("main", _mock_main)
sys.modules.setdefault("app.services.audit_log", MagicMock())
sys.modules.setdefault("templates.podnesci", MagicMock())
sys.modules.setdefault("knowledge.vks_standards", MagicMock())
sys.modules.setdefault("pinecone", MagicMock())
sys.modules.setdefault("supabase", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402 — must come after mocks
from fastapi.testclient import TestClient

# Override get_current_user so tests don't need a real JWT.
# /api/dokument/upload now uses PermissionService.require("document_analysis"),
# whose inner dependency closure resolves user via shared.deps.get_current_user —
# overriding that (not the retired require_credits) satisfies the route. get_policy()
# still runs its kill-switch check even for this user, so feature_registry must also
# be seeded — see fixture below.
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

FIXTURES = Path(__file__).parent / "fixtures" / "uploaded_doc"
UGOVOR_DOCX = FIXTURES / "sample_ugovor.docx"
UGOVOR_PDF = FIXTURES / "sample_ugovor.pdf"

_UPLOAD_MOCK_RESPONSE = {
    "session_id": "abc123mockid",
    "chunk_count": 9,
    "chunk_mode_used": "article_aware",
    "article_labels_detected": [f"Član {i+1}" for i in range(8)],
    "expires_at": "2026-05-11T22:00:00Z",
    "ttl_seconds": 86000,
}


# ─── Test 5: DOCX happy path ─────────────────────────────────────────────────

def test_upload_docx_happy_path():
    from uploaded_doc.api_models import UploadResponse

    with patch("uploaded_doc.ingest.ingest_session", return_value=9), \
         patch("uploaded_doc.cleanup.cleanup_expired", return_value={"namespaces_deleted": 0, "chunks_deleted": 0, "namespaces_inspected": 0}), \
         patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        with open(UGOVOR_DOCX, "rb") as f:
            resp = client.post(
                "/api/dokument/upload",
                files={"file": ("sample_ugovor.docx",
                                f,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "session_id" in data
    assert data["chunk_count"] == 9
    assert data["chunk_mode_used"] == "article_aware"
    assert len(data["article_labels_detected"]) >= 8
    assert "expires_at" in data
    assert data["ttl_seconds"] > 0


# ─── Test 6: PDF happy path ──────────────────────────────────────────────────

def test_upload_pdf_happy_path():
    with patch("uploaded_doc.ingest.ingest_session", return_value=9), \
         patch("uploaded_doc.cleanup.cleanup_expired", return_value={"namespaces_deleted": 0, "chunks_deleted": 0, "namespaces_inspected": 0}), \
         patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        with open(UGOVOR_PDF, "rb") as f:
            resp = client.post(
                "/api/dokument/upload",
                files={"file": ("sample_ugovor.pdf", f, "application/pdf")},
            )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["chunk_count"] == 9
    assert "session_id" in data


# ─── Test 7: oversized file rejected ─────────────────────────────────────────

def test_upload_rejects_oversized():
    # Set Content-Length header > 25MB (_MAX_UPLOAD_BYTES) to trigger fast-path rejection
    resp = client.post(
        "/api/dokument/upload",
        files={"file": ("big.docx", b"x" * 100,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers={"Content-Length": str(26 * 1024 * 1024)},
    )
    assert resp.status_code == 413, f"Expected 413, got {resp.status_code}"


# ─── Test 8: unsupported MIME type rejected ──────────────────────────────────

def test_upload_rejects_unsupported_mime():
    resp = client.post(
        "/api/dokument/upload",
        files={"file": ("memo.txt", b"some text", "text/plain")},
    )
    assert resp.status_code == 415, f"Expected 415, got {resp.status_code}: {resp.text}"


# ─── Test 9: scanned PDF rejected ────────────────────────────────────────────

def test_upload_rejects_scanned_pdf():
    with patch("uploaded_doc.extractor.extract", return_value=("", True, False)):
        with open(UGOVOR_PDF, "rb") as f:
            resp = client.post(
                "/api/dokument/upload",
                files={"file": ("scan.pdf", f, "application/pdf")},
            )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert "skenirani" in resp.json()["detail"].lower() or "Skenirani" in resp.json()["detail"]


# ─── Test 10: empty document rejected ────────────────────────────────────────

def test_upload_rejects_empty_chunks():
    from uploaded_doc.schema import ChunkingManifest
    empty_manifest = ChunkingManifest(
        source_filename="empty.docx",
        source_format="docx",
        source_sha256="abc",
        is_scanned=False,
        total_chunks=0,
        chunk_mode_used="recursive",
        article_labels_detected=[],
        token_p10=0, token_p50=0, token_p90=0,
        chunks=[],
    )
    with patch("uploaded_doc.extractor.extract", return_value=("some text", False, False)), \
         patch("uploaded_doc.chunker.chunk_document", return_value=empty_manifest):
        with open(UGOVOR_DOCX, "rb") as f:
            resp = client.post(
                "/api/dokument/upload",
                files={"file": ("empty.docx", f,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─── Test 11: cleanup requires token ─────────────────────────────────────────

def test_cleanup_endpoint_requires_token():
    resp = client.post("/api/dokument/cleanup")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ─── Test 12: cleanup with valid token ───────────────────────────────────────

def test_cleanup_endpoint_with_valid_token():
    with patch("uploaded_doc.cleanup.cleanup_expired",
               return_value={"namespaces_deleted": 2, "chunks_deleted": 15, "namespaces_inspected": 5}):
        resp = client.post(
            "/api/dokument/cleanup",
            headers={"X-Admin-Token": "test-admin-token-12345"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["namespaces_deleted"] == 2
    assert data["chunks_deleted"] == 15
    assert data["namespaces_inspected"] == 5
