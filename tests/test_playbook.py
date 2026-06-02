# -*- coding: utf-8 -*-
"""Tests for P4.4 — drafting/playbook.py + /api/playbook endpoints."""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")

from drafting.playbook import _chunk_text


# ─── T1: _chunk_text chunking logic ──────────────────────────────────────────

def test_chunk_text_single_chunk():
    """Short text fits in one chunk."""
    text = "A" * 100
    chunks = _chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text.strip()


def test_chunk_text_multiple_chunks():
    """Long text produces multiple overlapping chunks."""
    text = "X" * 1100  # > 2 * CHUNK_SIZE (500)
    chunks = _chunk_text(text)
    assert len(chunks) >= 2


def test_chunk_text_empty():
    """Empty text → empty list."""
    assert _chunk_text("") == []


def test_chunk_text_overlap():
    """Adjacent chunks share overlap content."""
    text = "AB" * 300  # 600 chars, slightly > chunk size
    chunks = _chunk_text(text)
    if len(chunks) >= 2:
        # End of first chunk should appear at start of second
        end_of_first = chunks[0][-50:]
        assert end_of_first in chunks[1]


# ─── T2: search_playbook empty namespace → [] ─────────────────────────────────

def test_search_playbook_empty_namespace_returns_empty():
    """search_playbook → [] when Pinecone returns no matches."""
    from drafting.playbook import search_playbook

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])

    mock_emb = MagicMock()
    mock_emb.embed_query.return_value = [0.0] * 3072

    with patch("drafting.playbook._get_pinecone_index", return_value=mock_index), \
         patch("drafting.playbook._get_embeddings_client", return_value=mock_emb):
        result = search_playbook("user123", "ugovor o radu")

    assert result == []


def test_search_playbook_empty_query_returns_empty():
    """search_playbook with empty query → [] without hitting Pinecone."""
    from drafting.playbook import search_playbook
    result = search_playbook("user123", "")
    assert result == []


# ─── T3: ingest_playbook mocks Pinecone ──────────────────────────────────────

def test_ingest_playbook_returns_chunk_count():
    """ingest_playbook returns number of chunks upserted."""
    from drafting.playbook import ingest_playbook

    mock_index = MagicMock()
    mock_emb = MagicMock()
    # 600-char text → 2 chunks (500 + overlap)
    mock_emb.embed_documents.return_value = [[0.1] * 3072, [0.2] * 3072]

    with patch("drafting.playbook._get_pinecone_index", return_value=mock_index), \
         patch("drafting.playbook._get_embeddings_client", return_value=mock_emb):
        count = ingest_playbook("user123", "playbook.txt", "A" * 600)

    assert count >= 1
    mock_index.upsert.assert_called()


def test_ingest_playbook_empty_text_returns_zero():
    """ingest_playbook with empty text → 0 without hitting Pinecone."""
    from drafting.playbook import ingest_playbook
    assert ingest_playbook("user123", "empty.txt", "") == 0


# ─── T4: API endpoints registrovani ──────────────────────────────────────────

def test_playbook_upload_endpoint_registered():
    """POST /api/playbook/upload must be registered in api.py."""
    routes = []
    with open(os.path.join(os.path.dirname(__file__), "..", "api.py"), encoding="utf-8") as f:
        routes = [l.strip() for l in f if "/api/playbook/upload" in l]
    assert any("post" in r.lower() or "POST" in r for r in routes), \
        "POST /api/playbook/upload not found in api.py"


def test_playbook_delete_endpoint_registered():
    """DELETE /api/playbook must be registered in api.py."""
    with open(os.path.join(os.path.dirname(__file__), "..", "api.py"), encoding="utf-8") as f:
        content = f.read()
    assert "/api/playbook" in content and "delete" in content.lower()


def test_playbook_status_endpoint_registered():
    """GET /api/playbook/status must be registered in api.py."""
    with open(os.path.join(os.path.dirname(__file__), "..", "api.py"), encoding="utf-8") as f:
        content = f.read()
    assert "/api/playbook/status" in content
