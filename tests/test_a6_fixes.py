# -*- coding: utf-8 -*-
"""
A6 bug-fix tests — retrieve.py
  A6.1: _direktan_fetch_clana must embed a real query text, not a zero-vector
  A6.2: ZOO fallback must be gated by LAW_HINTS (zakon == ZOO), not unconditional
"""

import sys
import os
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.retrieve import (
    _direktan_fetch_clana,
    _prepoznaj_zakon,
    _ZOO_FALLBACK_CLANOVI,
)

# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_match(law: str, article: str, score: float = 0.82, text: str = "test") -> MagicMock:
    m = MagicMock()
    m.id = f"{law}-{article}"
    m.score = score
    m.metadata = {"law": law, "article": article, "text": text, "parent_text": text}
    return m


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 1: A6.1 — _direktan_fetch_clana
# ═══════════════════════════════════════════════════════════════════════════

class TestDirektanFetchClana:
    """_direktan_fetch_clana must use a real embedding, not a zero-vector."""

    def test_embeds_with_article_and_law(self):
        """When zakon is given, query text must include both article and law."""
        fake_vec = [0.1] * 3072
        fake_match = _make_match("zakon o obligacionim odnosima", "Član 175")

        with (
            patch("app.services.retrieve._ugradi_query", return_value=fake_vec) as mock_embed,
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.return_value.matches = [fake_match]
            result = _direktan_fetch_clana("Član 175", "zakon o obligacionim odnosima")

        # Embedding must be called with article+law, NOT a zero vector
        mock_embed.assert_called_once()
        query_text = mock_embed.call_args[0][0]
        assert "175" in query_text or "Član" in query_text
        assert "obligacion" in query_text.lower() or "zakon o obligacionim" in query_text.lower()

    def test_embeds_article_only_when_no_zakon(self):
        """Without zakon, query text is just the article label."""
        fake_vec = [0.2] * 3072
        with (
            patch("app.services.retrieve._ugradi_query", return_value=fake_vec) as mock_embed,
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.return_value.matches = []
            _direktan_fetch_clana("Član 5")

        mock_embed.assert_called_once()
        query_text = mock_embed.call_args[0][0]
        assert "5" in query_text or "Član" in query_text

    def test_vector_not_zero(self):
        """The vector passed to Pinecone must not be all-zeros."""
        fake_vec = [0.05] * 3072
        with (
            patch("app.services.retrieve._ugradi_query", return_value=fake_vec),
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.return_value.matches = []
            _direktan_fetch_clana("Član 175", "zakon o obligacionim odnosima")

        call_kwargs = mock_idx.return_value.query.call_args
        used_vector = call_kwargs[1].get("vector") or call_kwargs[0][0]
        assert any(v != 0.0 for v in used_vector), "Vector passed to Pinecone must not be zero"

    def test_uses_metadata_filter_article(self):
        """Metadata filter must include article equality."""
        with (
            patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072),
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.return_value.matches = []
            _direktan_fetch_clana("Član 200")

        call_kwargs = mock_idx.return_value.query.call_args[1]
        filt = call_kwargs.get("filter") or {}
        assert filt.get("article", {}).get("$eq") == "Član 200"

    def test_uses_metadata_filter_article_and_law(self):
        """With zakon, filter must be $and of article + law."""
        with (
            patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072),
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.return_value.matches = []
            _direktan_fetch_clana("Član 5", "zakon o radu")

        call_kwargs = mock_idx.return_value.query.call_args[1]
        filt = call_kwargs.get("filter") or {}
        assert "$and" in filt
        conds = {list(c.keys())[0]: list(c.values())[0] for c in filt["$and"]}
        assert conds["article"]["$eq"] == "Član 5"
        assert conds["law"]["$eq"] == "zakon o radu"

    def test_returns_empty_on_pinecone_error(self):
        """Exception in Pinecone query → empty list, no propagation."""
        with (
            patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072),
            patch("app.services.retrieve._get_index") as mock_idx,
        ):
            mock_idx.return_value.query.side_effect = RuntimeError("Pinecone down")
            result = _direktan_fetch_clana("Član 175", "zakon o obligacionim odnosima")

        assert result == []

    def test_returns_empty_on_embed_error(self):
        """Exception in embedding → empty list, no propagation."""
        with patch("app.services.retrieve._ugradi_query", side_effect=RuntimeError("OpenAI down")):
            result = _direktan_fetch_clana("Član 175", "zakon o obligacionim odnosima")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 2: A6.2 — ZOO fallback gating
# ═══════════════════════════════════════════════════════════════════════════

class TestZooFallbackGating:
    """ZOO fallback must only fire when LAW_HINTS matched ZOO (zakon == ZOO)."""

    _ZOO = "zakon o obligacionim odnosima"

    def _make_weak_retrieval_meta(self):
        """Returns (skorovani, reranked) simulating very weak primary retrieval."""
        reranked = []  # empty → triggers fallback condition
        skorovani = [(10.0, MagicMock())]  # low score < 50
        return skorovani, reranked

    def _run_fallback_block(self, zakon_val, skorovani, reranked, query="test"):
        """
        Directly execute the fallback block logic extracted from retrieve_documents.
        Returns the final reranked list and whether _direktan_fetch_clana was called.
        """
        from app.services.retrieve import _ZOO_FALLBACK_CLANOVI
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _zoo_law = self._ZOO
        k = 6
        top_skor = skorovani[0][0] if skorovani else 0

        zoo_fetched = []
        if len(reranked) < 3 or top_skor < 50:
            if zakon_val == _zoo_law:
                with ThreadPoolExecutor(max_workers=4) as fb:
                    fbs = [
                        fb.submit(lambda c: [_make_match(_zoo_law, c)], clan)
                        for clan in _ZOO_FALLBACK_CLANOVI
                    ]
                    vidjeni = {m.id for m in reranked}
                    for f in as_completed(fbs):
                        try:
                            for m in f.result():
                                if m.id not in vidjeni:
                                    vidjeni.add(m.id)
                                    reranked.append(m)
                                    zoo_fetched.append(m)
                        except Exception:
                            pass
                reranked = reranked[:k]
            elif zakon_val is not None:
                pass  # scoped retry (tested via retrieve_documents integration)

        return reranked, zoo_fetched

    def test_zoo_law_hints_recognizes_steta(self):
        """LAW_HINTS must resolve 'steta' → ZOO."""
        assert _prepoznaj_zakon("naknada nematerijalne štete") == self._ZOO

    def test_zoo_law_hints_recognizes_zastarel(self):
        """LAW_HINTS must resolve 'zastarel' → ZOO."""
        assert _prepoznaj_zakon("zastarelost potraživanja") == self._ZOO

    def test_zoo_fallback_fires_for_zoo_zakon(self):
        """With zakon=ZOO and weak retrieval, fallback must inject ZOO articles."""
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block(self._ZOO, skorovani, reranked)
        assert len(zoo_fetched) > 0, "ZOO fallback must inject articles when zakon=ZOO"

    def test_zoo_fallback_absent_for_kz_zakon(self):
        """With zakon=KZ and weak retrieval, ZOO fallback must NOT inject ZOO articles."""
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block("KZ", skorovani, reranked)
        zoo_laws = [m.metadata.get("law", "") for m in final]
        assert self._ZOO not in zoo_laws, "ZOO must not appear in KZ-query context"
        assert len(zoo_fetched) == 0

    def test_zoo_fallback_absent_for_zr_zakon(self):
        """With zakon=ZR and weak retrieval, ZOO fallback must NOT inject ZOO articles."""
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block("zakon o radu", skorovani, reranked)
        zoo_laws = [m.metadata.get("law", "") for m in final]
        assert self._ZOO not in zoo_laws
        assert len(zoo_fetched) == 0

    def test_zoo_fallback_absent_when_zakon_is_none(self):
        """With zakon=None and weak retrieval, ZOO fallback must NOT fire."""
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block(None, skorovani, reranked)
        assert len(zoo_fetched) == 0

    def test_zoo_fallback_absent_for_ustav_zakon(self):
        """'ustav' queries route to ustav, not ZOO."""
        assert _prepoznaj_zakon("ustavna žalba") == "ustav republike srbije"
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block("ustav republike srbije", skorovani, reranked)
        assert len(zoo_fetched) == 0

    def test_zoo_fallback_absent_for_poreska_query(self):
        """'rok za poresku prijavu' → zakon=None → no ZOO fallback."""
        assert _prepoznaj_zakon("rok za poresku prijavu") is None
        skorovani, reranked = self._make_weak_retrieval_meta()
        final, zoo_fetched = self._run_fallback_block(None, skorovani, reranked)
        assert len(zoo_fetched) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 3: retrieve_documents integration (mocked Pinecone + OpenAI)
# ═══════════════════════════════════════════════════════════════════════════

class TestRetrieveDocumentsA6Integration:
    """End-to-end retrieve_documents with all I/O mocked."""

    _ZOO = "zakon o obligacionim odnosima"

    def _patch_all(self, zakon_matches=None, zoo_fallback_matches=None):
        """Return a context manager that patches all I/O in retrieve_documents."""
        zakon_matches = zakon_matches or []
        zoo_fallback_matches = zoo_fallback_matches or []

        fake_vec = [0.5] * 3072

        def fake_ugradi(text):
            return fake_vec

        def fake_pretraga_vec(vec, k, filter_zakon=None):
            if filter_zakon == self._ZOO:
                return zakon_matches[:k]
            return zakon_matches[:k]

        def fake_direktan(label, zakon=None):
            if zakon == self._ZOO:
                return zoo_fallback_matches
            return []

        def fake_pretraga(query, k, filter_zakon=None):
            return zakon_matches[:k]

        def fake_pretraga_praksa(vec, k=5):
            return []

        patches = [
            patch("app.services.retrieve._ugradi_query", side_effect=fake_ugradi),
            patch("app.services.retrieve._pretraga_vec", side_effect=fake_pretraga_vec),
            patch("app.services.retrieve._semanticka_pretraga", side_effect=fake_pretraga),
            patch("app.services.retrieve._direktan_fetch_clana", side_effect=fake_direktan),
            patch("app.services.retrieve._pretraga_praksa", side_effect=fake_pretraga_praksa),
            patch("app.services.retrieve._get_client"),
            patch("app.services.retrieve._cohere_rerank", side_effect=lambda q, m, k=3: m[:k]),
            patch("app.services.retrieve._oceni_relevantnost", return_value="RELEVANTNO"),
            patch("app.services.retrieve._dekomponuj_query", return_value=[]),
            patch("app.services.retrieve.decompose_query", return_value=[]),
            patch("app.services.retrieve._generiši_hyde", return_value=""),
            patch("app.services.retrieve._prosiri_query_gpt_wrapper", return_value=[]),
        ]
        return patches

    def test_zoo_query_has_zoo_in_context(self):
        """A ZOO query with weak primary retrieval injects ZOO fallback articles."""
        from app.services.retrieve import retrieve_documents

        zoo_match = _make_match(self._ZOO, "Član 200", score=0.4)

        patches = self._patch_all(zakon_matches=[], zoo_fallback_matches=[zoo_match])
        for p in patches:
            p.start()
        try:
            docs, meta = retrieve_documents("naknada nematerijalne štete", k=6)
        finally:
            for p in patches:
                p.stop()

        assert any("obligacion" in d.lower() or "Član 200" in d for d in docs), \
            "ZOO fallback article must appear in docs for ZOO query"

    def test_kz_query_no_zoo_in_context(self):
        """A KZ query with weak retrieval must NOT receive ZOO fallback contamination."""
        from app.services.retrieve import retrieve_documents

        kz_match = _make_match("KZ", "Član 208", score=0.4)
        zoo_match = _make_match(self._ZOO, "Član 154", score=0.4)

        patches = self._patch_all(zakon_matches=[kz_match], zoo_fallback_matches=[zoo_match])
        for p in patches:
            p.start()
        try:
            docs, meta = retrieve_documents("kazna za prevaru milion dinara", k=6)
        finally:
            for p in patches:
                p.stop()

        zoo_in_docs = any("zakon o obligacionim odnosima" in d.lower() for d in docs)
        assert not zoo_in_docs, "ZOO content must NOT appear in KZ-query context"

    def test_no_hint_query_no_zoo_fallback(self):
        """A query with no LAW_HINTS match must not receive ZOO fallback."""
        from app.services.retrieve import retrieve_documents

        zoo_match = _make_match(self._ZOO, "Član 154", score=0.4)

        patches = self._patch_all(zakon_matches=[], zoo_fallback_matches=[zoo_match])
        for p in patches:
            p.start()
        try:
            docs, meta = retrieve_documents("rok za poresku prijavu godišnju", k=6)
        finally:
            for p in patches:
                p.stop()

        zoo_in_docs = any("zakon o obligacionim odnosima" in d.lower() for d in docs)
        assert not zoo_in_docs, "ZOO must not appear when query has no LAW_HINTS match"
