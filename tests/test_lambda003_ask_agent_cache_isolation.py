# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 003 (2026-08-06) -- Cache & Session Isolation
Auditor fork found, and the Adversarial Certification fork independently
re-confirmed with added severity, that main.py::ask_agent's response cache
had zero tenant scoping in its key (main.py::_cache_kljuc == md5 of the
normalized question text alone) AND a read/write gate asymmetry: the read
gate checked `history`/`extra_namespaces` but never `memory_context`; all
3 write gates checked only `history`, never `extra_namespaces` or
`memory_context`.

extra_namespaces carries a firm's own private Pinecone institutional-memory
namespace (api.py::/pitanje derives it server-side from the caller's own
kancelarija for every ordinary question, not just uploaded-document Q&A).
memory_context carries a firm's institutional memory injected directly into
the system prompt. Since neither was checked on write, one firm's privately-
influenced answer could be cached under a key derived only from the question
text and later served verbatim to a completely unrelated firm asking a
similarly-normalized question -- the single most severe isolation bug found
across this whole multi-sprint engagement, since it required the attacker to
guess or know NO resource identifier at all, unlike every prior IDOR finding.

Fix: all 4 gates (1 read, 3 write -- LOW/MEDIUM/HIGH confidence paths) now
require `not history and not extra_namespaces and not memory_context`
together. These tests prove: (a) each of the 3 private-context sources
independently disables both read and write, and (b) genuinely generic
questions (all three absent) still cache normally -- no regression to the
legitimate cache's own purpose.
"""
import sys
import os
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as _real_main  # noqa: E402
ask_agent = _real_main.ask_agent
if "main" in sys.modules:
    del sys.modules["main"]


@contextmanager
def _offline_side_pipelines():
    """Stub the two side retrieval pipelines that ask_agent runs BEFORE the
    LOW-confidence exit (KORAK 1.6 sudska praksa, KORAK 1.7 mišljenja).

    Both embed the question through the real OpenAI client
    (retrieve.py::_ugradi_query), so leaving them live meant every one of
    these cache-isolation tests issued a billed embeddings request. Neither
    feeds the LOW path or the cache gates under test — an empty result is
    exactly what the production code sees when nothing matches — so nothing
    these tests assert is weakened by stubbing them.
    """
    with patch.object(_real_main, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(_real_main, "retrieve_misljenja", return_value=[]):
        yield


def _low_confidence_meta():
    docs = ["Neki tekst zakona koji nije naročito relevantan."]
    meta = {
        "confidence": "LOW",
        "top_score": 0.30,
        "top_article": "Član 1",
        "top_law": "zakon o radu",
        "doc_passages": [],
        "praksa_matches": [],
    }
    return docs, meta


def _ask(pitanje, **kwargs):
    docs, meta = _low_confidence_meta()
    with _offline_side_pipelines(), \
         patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_cache_get", return_value=None) as mock_get, \
         patch.object(_real_main, "_cache_set") as mock_set:
        result = ask_agent(pitanje, **kwargs)
    return result, mock_get, mock_set


# ─── Write gate: must NOT cache when any private-context source is present ───


def test_low_confidence_not_cached_when_extra_namespaces_present():
    """A firm's private Pinecone namespace was consulted -- the answer must
    never be written to the shared, tenant-blind cache."""
    result, _mock_get, mock_set = _ask(
        "Koliko traje probni rad?", extra_namespaces=["kancelarija_firma-x"]
    )
    assert result["confidence"] == "LOW"
    mock_set.assert_not_called()


def test_low_confidence_not_cached_when_memory_context_present():
    """A firm's institutional memory shaped the system prompt -- the answer
    must never be written to the shared, tenant-blind cache. This is the
    gap the original write gates missed entirely (they never checked
    memory_context at all, only history)."""
    result, _mock_get, mock_set = _ask(
        "Koliko traje probni rad?", memory_context="Firma X: interna praksa o probnom radu je..."
    )
    assert result["confidence"] == "LOW"
    mock_set.assert_not_called()


def test_low_confidence_not_cached_when_history_present():
    """No-regression: the original history check must still work."""
    result, _mock_get, mock_set = _ask(
        "Koliko traje probni rad?", history=[{"q": "Prethodno pitanje", "a": "Prethodni odgovor"}]
    )
    assert result["confidence"] == "LOW"
    mock_set.assert_not_called()


def test_low_confidence_still_cached_when_no_private_context():
    """No regression to the cache's own legitimate purpose: a genuinely
    generic question with no history/extra_namespaces/memory_context must
    still be cached, exactly as before this fix."""
    result, _mock_get, mock_set = _ask("Koliko traje probni rad?")
    assert result["confidence"] == "LOW"
    mock_set.assert_called_once()


# ─── Read gate: must NOT serve cache when any private-context source is present ───


def test_cache_read_skipped_when_memory_context_present():
    """The original read gate checked history/extra_namespaces but never
    memory_context -- a request with ONLY memory_context set (no history,
    no extra_namespaces) must still skip the cache lookup entirely, or a
    cached answer shaped by a DIFFERENT firm's memory_context could be
    served here."""
    docs, meta = _low_confidence_meta()
    with _offline_side_pipelines(), \
         patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_cache_get") as mock_get, \
         patch.object(_real_main, "_cache_set"):
        ask_agent("Koliko traje probni rad?", memory_context="Firma Y: interna praksa...")
    mock_get.assert_not_called()


def test_cache_read_skipped_when_extra_namespaces_present():
    docs, meta = _low_confidence_meta()
    with _offline_side_pipelines(), \
         patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_cache_get") as mock_get, \
         patch.object(_real_main, "_cache_set"):
        ask_agent("Koliko traje probni rad?", extra_namespaces=["kancelarija_firma-y"])
    mock_get.assert_not_called()


def test_cache_read_still_used_when_no_private_context():
    """No-regression: a genuinely generic question must still consult the
    cache, exactly as before this fix."""
    docs, meta = _low_confidence_meta()
    with _offline_side_pipelines(), \
         patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_cache_get", return_value=None) as mock_get, \
         patch.object(_real_main, "_cache_set"):
        ask_agent("Koliko traje probni rad?")
    mock_get.assert_called_once()


# ─── Structural guard against a future regression re-introducing the gap ─────


def test_cache_key_has_no_tenant_component_documented_as_the_reason_gates_must_be_strict():
    """_cache_kljuc is, by design, derived only from the question text (no
    user/firm/namespace component) -- documenting this explicitly so a
    future reader understands WHY the gates above must stay strict, rather
    than someone "fixing" this by loosening the gates back to history-only."""
    import inspect
    src = inspect.getsource(_real_main._cache_kljuc)
    assert "pitanje" in src
    assert "user" not in src.lower()
    assert "firma" not in src.lower()
    assert "namespace" not in src.lower()
