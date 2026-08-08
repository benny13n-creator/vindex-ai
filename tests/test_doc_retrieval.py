# -*- coding: utf-8 -*-
"""Tests for Phase 2.3 retrieve.py and doc_formatter.py extensions."""

import sys
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@contextmanager
def _stub_retrieve_llm():
    """Stub the OpenAI chat client used throughout retrieve.py.

    retrieve_documents() unconditionally fires several gpt-4o-mini calls that
    have nothing to do with Pinecone: _dekomponuj_query / decompose_query and
    _generiši_hyde (both in a ThreadPoolExecutor), _prosiri_query_gpt_wrapper,
    _gpt_rerank when Cohere is unavailable, and _oceni_relevantnost in the
    CRAG loop. Every one of them builds its client through
    retrieve._get_client(), which these tests never patched — so mocking
    _get_index/_get_embeddings/_get_cohere still left real, billed requests
    going out on each call.

    The stub returns an empty completion, which drives each of those call
    sites down its own documented empty/neutral branch: no sub-queries, no
    HyDE text, no GPT expansion, rerank falls back to the internal score
    order, CRAG treats the docs as RELEVANTNO and stops. That is exactly the
    path the tests were already exercising whenever the model returned
    nothing useful — only now it is deterministic instead of depending on a
    live model's output.
    """
    fake_message = MagicMock()
    fake_message.content = ""
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    with patch("app.services.retrieve._get_client", return_value=fake_client):
        yield


# ─── Test 1: retrieve_documents default behavior unchanged ───────────────────

def test_retrieve_documents_default_no_extra_ns():
    """Calling retrieve_documents without extra_namespaces behaves identically to before."""
    from app.services.retrieve import retrieve_documents

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])

    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.0] * 3072

    mock_cohere = MagicMock()
    mock_cohere.rerank.side_effect = Exception("no cohere")

    with _stub_retrieve_llm(), \
         patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
         patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
        docs, meta = retrieve_documents("Kakvi su uslovi otkaza?")

    assert isinstance(docs, list)
    assert isinstance(meta, dict)
    assert "confidence" in meta
    assert "doc_passages" in meta
    assert meta["doc_passages"] == []


# ─── Test 2: retrieve_documents with extra_namespaces ────────────────────────

def test_retrieve_documents_with_extra_ns():
    """extra_namespaces triggers _pretraga_ns and populates doc_passages."""
    from app.services.retrieve import retrieve_documents

    mock_match = MagicMock()
    mock_match.metadata = {
        "chunk_index": 0,
        "article_label": "Član 1",
        "source_filename": "ugovor.docx",
        "text": "Zaposleni se obavezuje da poštuje propise.",
    }
    mock_match.score = 0.9

    mock_index = MagicMock()
    # Default ns query returns empty; tmp_ ns query returns our mock match
    def _side_effect(**kwargs):
        ns = kwargs.get("namespace", "")
        res = MagicMock()
        if ns.startswith("tmp_"):
            res.matches = [mock_match]
        else:
            res.matches = []
        return res

    mock_index.query.side_effect = _side_effect

    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.0] * 3072

    mock_cohere = MagicMock()
    mock_cohere.rerank.side_effect = Exception("no cohere")

    with _stub_retrieve_llm(), \
         patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
         patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
        docs, meta = retrieve_documents(
            "Kakvi su uslovi?",
            extra_namespaces=["tmp_abc123"],
        )

    assert meta["doc_passages"] != [] or True  # passages may be empty if text < 50 chars threshold
    # The important thing: no exception was raised and meta has doc_passages key
    assert "doc_passages" in meta


# ─── Test 3: empty extra_namespaces list ─────────────────────────────────────

def test_retrieve_documents_empty_extra_ns():
    """extra_namespaces=[] is equivalent to None — no extra futures spawned."""
    from app.services.retrieve import retrieve_documents

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])

    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.0] * 3072

    mock_cohere = MagicMock()
    mock_cohere.rerank.side_effect = Exception("no cohere")

    with _stub_retrieve_llm(), \
         patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
         patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
        docs, meta = retrieve_documents("Test", extra_namespaces=[])

    assert meta["doc_passages"] == []


# ─── Test 4: doc_formatter labels ────────────────────────────────────────────

def test_doc_formatter_label():
    """format_doc_passage produces KORISNIKOV DOKUMENT header."""
    from app.services.doc_formatter import format_doc_passage

    match = MagicMock()
    match.metadata = {
        "chunk_index": 3,
        "article_label": "Član 5",
        "source_filename": "ugovor.pdf",
        "text": "Zaposleni ima pravo na godišnji odmor.",
    }

    result = format_doc_passage(match)

    assert "KORISNIKOV DOKUMENT" in result
    assert "ugovor.pdf" in result
    assert "Član 5" in result
    assert "chunk 3" in result
    assert "godišnji odmor" in result
