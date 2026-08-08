# -*- coding: utf-8 -*-
"""
Regression tests — routers/dokument.py::dokument_upload (Faza 3 item 9).

NIGHTLY REPAIR (2026-07-24): evidence classification (_klasifikuj_dokaz)
used to run inside the SAME asyncio.gather as Pinecone ingestion during
upload, blocking the upload response on a GPT call the caller didn't need
synchronously. Now fire-and-forget (asyncio.create_task, same pattern as
the existing _background_cleanup two lines below it) -- the upload
response no longer waits on it, and returns klasifikacija=None with a
klasifikacija_napomena pointing at the pre-existing
POST /api/dokument/klasifikuj-sesija endpoint for on-demand results.

Pure unit tests -- no live Supabase, no OpenAI, no real Pinecone.
"""
import asyncio
import io
import os
import sys
import time as _time
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.deps import get_current_user as _shared_get_current_user  # noqa: E402
import shared.feature_registry as _fr  # noqa: E402

_FAKE_USER = {"user_id": "test-user-id", "email": "test@test.com"}
_FAKE_PROFILE = {
    "credits_remaining": 100, "is_pro": True,
    "subscription_type": "professional", "addons": [], "subscription_expires_at": None,
}


@pytest.fixture(autouse=True)
def _setup_overrides():
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


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app, raise_server_exceptions=True)


class _FakeManifest:
    chunk_mode_used = "paragraph"
    article_labels_detected = []
    total_chunks = 3


def _do_upload(client, klasifikuj_mock=None):
    fake_manifest = _FakeManifest()

    with patch("uploaded_doc.extractor.extract", return_value=("Tekst dokumenta.", False, False, None, None)), \
         patch("uploaded_doc.chunker.chunk_document", return_value=fake_manifest), \
         patch("uploaded_doc.ingest.ingest_session", return_value=3), \
         patch("uploaded_doc.cleanup.cleanup_expired", return_value={"deleted": 0}), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=100)), \
         patch("routers.dokument._klasifikuj_dokaz", new=(klasifikuj_mock or AsyncMock(return_value={"tip": "ugovor"}))):
        resp = client.post(
            "/api/dokument/upload",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
        )
    return resp


def test_upload_response_does_not_include_synchronous_klasifikacija(client):
    """Core regression: the response must not carry a computed
    classification result -- it's now fire-and-forget."""
    resp = _do_upload(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["klasifikacija"] is None
    assert "klasifikuj-sesija" in body["klasifikacija_napomena"]


def test_upload_succeeds_even_when_background_classification_fails(client):
    """Fail-soft: a classification failure must never affect the upload
    response -- it happens in a detached background task."""
    failing_klasifikuj = AsyncMock(side_effect=RuntimeError("openai down"))
    resp = _do_upload(client, klasifikuj_mock=failing_klasifikuj)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["chunk_count"] == 3


def test_upload_schedules_classification_as_background_task(client):
    """Confirms classification is scheduled via asyncio.create_task (fire-
    and-forget) rather than awaited inline as part of the response path."""
    klasifikuj_mock = AsyncMock(return_value={"tip": "ugovor"})
    created_tasks = []
    real_create_task = asyncio.create_task

    def _tracking_create_task(coro, *a, **kw):
        t = real_create_task(coro, *a, **kw)
        created_tasks.append(t)
        return t

    with patch("asyncio.create_task", side_effect=_tracking_create_task):
        resp = _do_upload(client, klasifikuj_mock=klasifikuj_mock)

    assert resp.status_code == 200
    # 2 background tasks now: cleanup + classification (previously only cleanup).
    assert len(created_tasks) >= 2
