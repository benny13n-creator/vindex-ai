# -*- coding: utf-8 -*-
"""Tests for Phase 2.1 — uploaded_doc chunker module."""

import sys
import os
from pathlib import Path

import tiktoken
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.extractor import extract_txt, extract_docx, extract
from uploaded_doc.chunker import chunk_document, _count
from uploaded_doc.schema import UploadedDocChunk, ChunkingManifest

FIXTURES = Path(__file__).parent / "fixtures" / "uploaded_doc"
UGOVOR_TXT = FIXTURES / "sample_ugovor_o_radu.txt"
NO_ARTICLES_TXT = FIXTURES / "sample_no_articles.txt"
UGOVOR_DOCX = FIXTURES / "sample_ugovor.docx"


def _meta(path: Path, text: str, is_scanned: bool = False) -> dict:
    import hashlib
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    fmt = path.suffix.lstrip(".").lower()
    return {
        "source_filename": path.name,
        "source_format": fmt,
        "source_sha256": sha,
        "is_scanned": is_scanned,
        "session_id": "__local__",
    }


# ─── Test 1: extract_txt smoke ────────────────────────────────────────────────

def test_extract_txt_smoke():
    text, is_scanned = extract_txt(UGOVOR_TXT)
    assert len(text) > 500, "Expected >500 chars from ugovor fixture"
    assert is_scanned is False
    assert "Član" in text, "Expected 'Član' in ugovor text"
    assert "UGOVOR O RADU" in text


# ─── Test 2: extract_docx smoke ───────────────────────────────────────────────

def test_extract_docx_smoke():
    text, is_scanned = extract_docx(UGOVOR_DOCX)
    assert len(text) > 500, "Expected >500 chars from docx fixture"
    assert is_scanned is False
    assert "UGOVOR O RADU" in text
    assert "Član 1" in text or "lan 1" in text


# ─── Test 3: article_aware mode ──────────────────────────────────────────────

def test_chunker_article_aware_mode():
    text, is_scanned = extract_txt(UGOVOR_TXT)
    meta = _meta(UGOVOR_TXT, text, is_scanned)
    manifest = chunk_document(text, meta)

    assert manifest.chunk_mode_used in ("article_aware", "mixed"), (
        f"Expected article_aware or mixed, got {manifest.chunk_mode_used!r}"
    )
    assert len(manifest.article_labels_detected) >= 8, (
        f"Expected >=8 article labels, got {manifest.article_labels_detected}"
    )
    # All article-aware chunks must have article_label set
    article_chunks = [c for c in manifest.chunks if c.chunk_mode == "article_aware"]
    assert article_chunks, "Expected at least one article_aware chunk"
    for c in article_chunks:
        assert c.article_label is not None, (
            f"Article-aware chunk {c.chunk_index} has no article_label"
        )


# ─── Test 4: recursive mode ──────────────────────────────────────────────────

def test_chunker_recursive_mode():
    text, is_scanned = extract_txt(NO_ARTICLES_TXT)
    meta = _meta(NO_ARTICLES_TXT, text, is_scanned)
    manifest = chunk_document(text, meta)

    assert manifest.chunk_mode_used == "recursive", (
        f"Expected recursive mode, got {manifest.chunk_mode_used!r}"
    )
    assert manifest.total_chunks >= 1

    # All chunks within [400, 800] tokens range (or shorter if document is short)
    for c in manifest.chunks:
        assert c.token_count <= 800, (
            f"Chunk {c.chunk_index} has {c.token_count} tokens > 800"
        )

    # Verify overlap: last ~100 tokens of chunk_i appear at start of chunk_{i+1}
    if len(manifest.chunks) >= 2:
        enc = tiktoken.get_encoding("cl100k_base")
        c0_tokens = enc.encode(manifest.chunks[0].text)
        c1_tokens = enc.encode(manifest.chunks[1].text)
        tail_c0 = c0_tokens[-100:] if len(c0_tokens) >= 100 else c0_tokens
        head_c1 = c1_tokens[:100] if len(c1_tokens) >= 100 else c1_tokens
        # At least some tokens must overlap
        overlap = set(tail_c0) & set(head_c1)
        assert overlap, "Expected token overlap between chunk 0 and chunk 1"


# ─── Test 5: schema validates ─────────────────────────────────────────────────

def test_schema_validates():
    text, is_scanned = extract_txt(UGOVOR_TXT)
    meta = _meta(UGOVOR_TXT, text, is_scanned)
    manifest = chunk_document(text, meta)

    # Validate manifest itself
    assert isinstance(manifest, ChunkingManifest)

    # Validate each chunk as UploadedDocChunk (round-trip via model_dump)
    for i, chunk in enumerate(manifest.chunks):
        try:
            validated = UploadedDocChunk.model_validate(chunk.model_dump())
        except Exception as e:
            pytest.fail(f"Chunk {i} failed schema validation: {e}")
        assert validated.chunk_id == chunk.chunk_id


# ─── Test 6: token_count accuracy ────────────────────────────────────────────

def test_token_count_accuracy():
    enc = tiktoken.get_encoding("cl100k_base")
    text, is_scanned = extract_txt(UGOVOR_TXT)
    meta = _meta(UGOVOR_TXT, text, is_scanned)
    manifest = chunk_document(text, meta)

    for chunk in manifest.chunks:
        expected = len(enc.encode(chunk.text))
        assert chunk.token_count == expected, (
            f"Chunk {chunk.chunk_index}: token_count={chunk.token_count}, "
            f"actual={expected}"
        )


# ─── Test 7: max tokens enforced (mixed mode) ─────────────────────────────────

def test_max_tokens_enforced():
    # Build a synthetic document with one huge "article" (~2000 tokens)
    long_sentence = "Zaposleni preuzima sve navedene obaveze u skladu sa zakonom. " * 40
    synthetic = "\n".join([
        "UGOVOR",
        "",
        "Član 1",
        "PREDMET UGOVORA",
        "",
        long_sentence,
        "",
        "Član 2",
        "TRAJANJE",
        "",
        "Radni odnos traje na neodređeno vreme.",
        "",
        "Član 3",
        "OSTALE ODREDBE",
        "",
        "Ostale odredbe uređuju se posebnim propisima.",
    ])

    import hashlib
    sha = hashlib.sha256(synthetic.encode("utf-8")).hexdigest()
    meta = {
        "source_filename": "synthetic_long.txt",
        "source_format": "txt",
        "source_sha256": sha,
        "is_scanned": False,
        "session_id": "__local__",
    }

    manifest = chunk_document(synthetic, meta)

    # The long article must have been sub-split
    assert manifest.chunk_mode_used == "mixed", (
        f"Expected 'mixed' mode, got {manifest.chunk_mode_used!r}"
    )
    for chunk in manifest.chunks:
        assert chunk.token_count <= 800, (
            f"Chunk {chunk.chunk_index} exceeds MAX_CHUNK_TOKENS: {chunk.token_count}"
        )
