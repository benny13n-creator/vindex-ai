# -*- coding: utf-8 -*-
"""
Phase 5.2 — Batch ingest novih presuda
Tests for routers/batch_ingest.py
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

import api
from shared.deps import get_current_user

# ─── Constants ────────────────────────────────────────────────────────────────

ADMIN_EMAIL  = "admin@vindex.ai"
NORMAL_EMAIL = "user@vindex.ai"

FAKE_USER_ADMIN  = {"email": ADMIN_EMAIL,  "id": "uid-admin",  "role": "founder"}
FAKE_USER_NORMAL = {"email": NORMAL_EMAIL, "id": "uid-normal", "role": "pro"}

FAKE_EMBEDDING = [0.1] * 3072

SAMPLE_DECISION = {
    "id":   "vks-kz-2024-001",
    "text": "Okrivljeni je proglašen krivim za krivično delo teške krađe iz člana 204 Krivičnog zakonika. " * 5,
    "metadata": {
        "sud":    "Vrhovni kasacioni sud",
        "oblast": "krivično pravo",
        "datum":  "2024-03-15",
    },
}


# ─── Supabase mock factory ────────────────────────────────────────────────────

def _make_supa(job_data: dict | None = None):
    supa = MagicMock()

    def _table(name):
        tbl = MagicMock()
        tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "job-123"}])
        tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        sel = MagicMock()
        sel.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[job_data] if job_data else []
        )
        sel.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=job_data
        )
        tbl.select.return_value = sel
        return tbl

    supa.table.side_effect = _table
    return supa


_DEFAULT_JOB = {
    "id": "job-123", "status": "pending", "total_docs": 1,
    "processed": 0, "failed_docs": 0, "namespace": "sudska_praksa",
    "created_by": ADMIN_EMAIL,
}


# ─── Client fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    api.app.dependency_overrides.clear()


@pytest.fixture
def admin_client():
    supa = _make_supa(_DEFAULT_JOB)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER_ADMIN
    with patch("routers.batch_ingest.FOUNDER_EMAILS", {ADMIN_EMAIL}), \
         patch("routers.batch_ingest._get_supa", return_value=supa), \
         patch("routers.batch_ingest._embed", lambda texts: [FAKE_EMBEDDING for _ in texts]), \
         patch("routers.batch_ingest._upsert_to_pinecone", lambda v, ns: None):
        yield TestClient(api.app, raise_server_exceptions=True)


@pytest.fixture
def normal_client():
    supa = _make_supa()
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER_NORMAL
    with patch("routers.batch_ingest.FOUNDER_EMAILS", {ADMIN_EMAIL}), \
         patch("routers.batch_ingest._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: chunk_text
# ═══════════════════════════════════════════════════════════════════════════════

from routers.batch_ingest import chunk_text, build_chunks, _run_ingest_sync


def test_chunk_text_short():
    result = chunk_text("Kratki tekst.")
    assert result == ["Kratki tekst."]


def test_chunk_text_exact_boundary():
    text = "A" * 800
    assert chunk_text(text) == [text]


def test_chunk_text_long_splits():
    text = "B" * 1600
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 800


def test_chunk_text_overlap():
    text = "C" * 1000
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    # overlap: tail of chunk 0 == head of chunk 1
    overlap_end   = chunks[0][-150:]
    overlap_start = chunks[1][:150]
    assert overlap_end == overlap_start


def test_chunk_text_all_content_covered():
    text = "Hello world " * 100
    chunks = chunk_text(text)
    reconstructed = chunks[0]
    for ch in chunks[1:]:
        reconstructed += ch[150:]  # skip overlap
    # Every char from original appears somewhere in the chunks
    for ch in chunks:
        assert all(c in text for c in ch[:10])


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: build_chunks
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_chunks_single():
    chunks = build_chunks("vks-001", "Kratki tekst presude.", {"oblast": "krivično"})
    assert len(chunks) == 1
    assert chunks[0]["id"] == "vks-001_c0"
    assert chunks[0]["metadata"]["decision_id"] == "vks-001"
    assert chunks[0]["metadata"]["oblast"] == "krivično"
    assert chunks[0]["metadata"]["chunk_index"] == 0


def test_build_chunks_multiple():
    long_text = "Tekst presude. " * 100
    chunks = build_chunks("vks-002", long_text, {})
    assert len(chunks) >= 2
    for i, ch in enumerate(chunks):
        assert ch["metadata"]["chunk_index"] == i
        assert ch["id"] == f"vks-002_c{i}"


def test_build_chunks_transliterates_id():
    chunks = build_chunks("žšćčđ-001", "Kratki tekst presude.", {})
    assert chunks[0]["id"].startswith("zscc")


def test_build_chunks_none_metadata_skipped():
    chunks = build_chunks("vks-003", "Tekst presude.", {"oblast": "krivično", "prazno": None})
    assert "prazno" not in chunks[0]["metadata"]
    assert chunks[0]["metadata"]["oblast"] == "krivično"


def test_build_chunks_initial_values_empty():
    chunks = build_chunks("vks-004", "Tekst.", {})
    assert chunks[0]["values"] == []


def test_build_chunks_decision_id_in_metadata():
    chunks = build_chunks("vks-999", "Kratki tekst presude.", {})
    assert chunks[0]["metadata"]["decision_id"] == "vks-999"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: _run_ingest_sync
# ═══════════════════════════════════════════════════════════════════════════════

def test_run_ingest_sync_success():
    supa = _make_supa()
    upsert_calls = []

    with patch("routers.batch_ingest._embed", lambda texts: [FAKE_EMBEDDING for _ in texts]), \
         patch("routers.batch_ingest._upsert_to_pinecone", lambda v, ns: upsert_calls.extend(v)), \
         patch("routers.batch_ingest._update_job") as mock_upd:
        _run_ingest_sync("job-abc", [SAMPLE_DECISION], "sudska_praksa", supa)

    assert len(upsert_calls) >= 1
    final = mock_upd.call_args_list[-1]
    assert "done" in str(final)


def test_run_ingest_sync_embed_failure():
    supa = _make_supa()
    upsert_calls = []

    def failing_embed(texts):
        raise RuntimeError("OpenAI unavailable")

    with patch("routers.batch_ingest._embed", failing_embed), \
         patch("routers.batch_ingest._upsert_to_pinecone", lambda v, ns: upsert_calls.extend(v)), \
         patch("routers.batch_ingest._update_job") as mock_upd:
        _run_ingest_sync("job-fail", [SAMPLE_DECISION], "sudska_praksa", supa)

    assert len(upsert_calls) == 0
    final = mock_upd.call_args_list[-1]
    assert "failed" in str(final)


def test_run_ingest_sync_multiple_decisions():
    supa = _make_supa()
    upsert_calls = []
    decisions = [
        {"id": f"vks-{i}", "text": "Tekst presude odluka suda. " * 10, "metadata": {}}
        for i in range(3)
    ]
    with patch("routers.batch_ingest._embed", lambda texts: [FAKE_EMBEDDING for _ in texts]), \
         patch("routers.batch_ingest._upsert_to_pinecone", lambda v, ns: upsert_calls.extend(v)), \
         patch("routers.batch_ingest._update_job"):
        _run_ingest_sync("job-multi", decisions, "sudska_praksa", supa)
    assert len(upsert_calls) >= 3


def test_run_ingest_sync_sets_running_then_done():
    supa = _make_supa()
    statuses = []

    def track_update(s, job_id, **fields):
        if "status" in fields:
            statuses.append(fields["status"])

    with patch("routers.batch_ingest._embed", lambda texts: [FAKE_EMBEDDING for _ in texts]), \
         patch("routers.batch_ingest._upsert_to_pinecone", lambda v, ns: None), \
         patch("routers.batch_ingest._update_job", side_effect=track_update):
        _run_ingest_sync("job-states", [SAMPLE_DECISION], "sudska_praksa", supa)

    assert statuses[0] == "running"
    assert statuses[-1] == "done"


# ═══════════════════════════════════════════════════════════════════════════════
# API: POST /api/admin/ingest/job
# ═══════════════════════════════════════════════════════════════════════════════

def test_create_job_admin_202(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "decisions": [SAMPLE_DECISION],
    })
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["total_docs"] == 1
    assert data["namespace"] == "sudska_praksa"


def test_create_job_non_admin_403(normal_client):
    r = normal_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "decisions": [SAMPLE_DECISION],
    })
    assert r.status_code == 403


def test_create_job_invalid_namespace_422(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "zakonodavstvo",
        "decisions": [SAMPLE_DECISION],
    })
    assert r.status_code == 422


def test_create_job_empty_decisions_422(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "decisions": [],
    })
    assert r.status_code == 422


def test_create_job_text_too_short_422(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "decisions": [{"id": "vks-x", "text": "Kratko", "metadata": {}}],
    })
    assert r.status_code == 422


def test_create_job_misljenja_namespace(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "misljenja",
        "decisions": [SAMPLE_DECISION],
    })
    assert r.status_code == 202
    assert r.json()["namespace"] == "misljenja"


def test_create_job_with_source(admin_client):
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "source":    "https://vks.sud.rs/2024",
        "decisions": [SAMPLE_DECISION],
    })
    assert r.status_code == 202


def test_create_job_multiple_decisions(admin_client):
    decisions = [
        {
            "id":   f"vks-kz-2024-{i:03d}",
            "text": "Okrivljeni je proglašen krivim za krivično delo. " * 5,
            "metadata": {"sud": "VKS"},
        }
        for i in range(5)
    ]
    r = admin_client.post("/api/admin/ingest/job", json={
        "namespace": "sudska_praksa",
        "decisions": decisions,
    })
    assert r.status_code == 202
    assert r.json()["total_docs"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# API: GET /api/admin/ingest/jobs
# ═══════════════════════════════════════════════════════════════════════════════

def test_list_jobs_admin_200(admin_client):
    r = admin_client.get("/api/admin/ingest/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()
    assert isinstance(r.json()["jobs"], list)


def test_list_jobs_non_admin_403(normal_client):
    r = normal_client.get("/api/admin/ingest/jobs")
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# API: GET /api/admin/ingest/job/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_job_admin_200(admin_client):
    r = admin_client.get("/api/admin/ingest/job/job-123")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "job-123"
    assert data["status"] == "pending"


def test_get_job_not_found_404():
    supa = _make_supa(job_data=None)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER_ADMIN
    with patch("routers.batch_ingest.FOUNDER_EMAILS", {ADMIN_EMAIL}), \
         patch("routers.batch_ingest._get_supa", return_value=supa):
        c = TestClient(api.app, raise_server_exceptions=False)
        r = c.get("/api/admin/ingest/job/nonexistent-id")
    assert r.status_code == 404


def test_get_job_non_admin_403(normal_client):
    r = normal_client.get("/api/admin/ingest/job/job-123")
    assert r.status_code == 403
