# -*- coding: utf-8 -*-
"""Tests for uploaded_doc.ingest — mocked Pinecone + Embeddings."""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.ingest import ingest_session
from uploaded_doc.schema import ChunkingManifest, UploadedDocChunk
from uploaded_doc.session import parse_expires


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_manifest(n_chunks: int, long_text: bool = False) -> ChunkingManifest:
    now = datetime.now(tz=timezone.utc)
    text = "X" * 50_000 if long_text else "Zaposleni preuzima obaveze prema zakonu."
    chunks = [
        UploadedDocChunk(
            chunk_id=f"chunk-{i:04d}",
            session_id="__local__",
            source_filename="test.docx",
            source_format="docx",
            source_sha256="abc123",
            chunk_index=i,
            chunk_mode="article_aware",
            article_label=f"Član {i + 1}",
            text=text,
            token_count=10,
            char_count=len(text),
            created_at=now,
        )
        for i in range(n_chunks)
    ]
    return ChunkingManifest(
        source_filename="test.docx",
        source_format="docx",
        source_sha256="abc123",
        is_scanned=False,
        total_chunks=n_chunks,
        chunk_mode_used="article_aware",
        article_labels_detected=[f"Član {i+1}" for i in range(n_chunks)],
        token_p10=10,
        token_p50=10,
        token_p90=10,
        chunks=chunks,
    )


# ─── Test 1: correct upsert count ────────────────────────────────────────────

def test_ingest_session_upserts_correct_count():
    manifest = _make_manifest(5)
    session_id = "abc123session"

    mock_index = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents.return_value = [[0.1] * 3072] * 5

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
         patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
        count = ingest_session(manifest, session_id, ttl_hours=24)

    assert count == 5
    mock_index.upsert.assert_called_once()
    call_kwargs = mock_index.upsert.call_args
    vectors = call_kwargs.kwargs.get("vectors") or call_kwargs.args[0]
    namespace = call_kwargs.kwargs.get("namespace")
    assert namespace == f"tmp_{session_id}"
    assert len(vectors) == 5


# ─── Test 2: metadata includes expires_at ────────────────────────────────────

def test_ingest_session_metadata_includes_expires_at():
    manifest = _make_manifest(2)
    session_id = "exptest"

    mock_index = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents.return_value = [[0.0] * 3072] * 2

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
         patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
        ingest_session(manifest, session_id, ttl_hours=24)

    vectors = mock_index.upsert.call_args.kwargs.get("vectors") or \
              mock_index.upsert.call_args.args[0]

    for v in vectors:
        exp_iso = v["metadata"]["expires_at"]
        exp_dt = parse_expires(exp_iso)
        now = datetime.now(tz=timezone.utc)
        # Should be ~24h in future (±1 minute tolerance)
        assert abs((exp_dt - now).total_seconds() - 86400) < 60, (
            f"expires_at not ~24h in future: {exp_iso}"
        )


# ─── Test 3: long text truncated to 40000 chars ──────────────────────────────

def test_ingest_session_truncates_long_text():
    manifest = _make_manifest(1, long_text=True)
    session_id = "trunctest"

    mock_index = MagicMock()
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents.return_value = [[0.0] * 3072]

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
         patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
        ingest_session(manifest, session_id, ttl_hours=24)

    vectors = mock_index.upsert.call_args.kwargs.get("vectors") or \
              mock_index.upsert.call_args.args[0]

    stored_text = vectors[0]["metadata"]["text"]
    assert len(stored_text) == 40_000, (
        f"Expected text truncated to 40000 chars, got {len(stored_text)}"
    )


# ─── Test 4: empty manifest skips upsert ─────────────────────────────────────

def test_ingest_handles_empty_manifest():
    manifest = _make_manifest(0)
    session_id = "emptytest"

    mock_index = MagicMock()
    mock_embeddings = MagicMock()

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
         patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
        count = ingest_session(manifest, session_id, ttl_hours=24)

    assert count == 0
    mock_index.upsert.assert_not_called()
    mock_embeddings.embed_documents.assert_not_called()
