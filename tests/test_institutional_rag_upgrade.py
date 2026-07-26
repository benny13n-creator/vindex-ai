# -*- coding: utf-8 -*-
"""
Tests for the Institutional Learning & RAG Audit (2026-07-26) upgrade:
  1. Pinecone namespace refactor (kancelarija_{id}/user_{id} + metadata)
  2. Cross-case retrieval with same-case prioritization
  3. Auto-indexing of finalized AI drafts (type=draft_final)

See docs/INTELLIGENCE_AND_RAG_AUDIT.md for the audit this implements.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "founder@example.com")

from uploaded_doc.schema import ChunkingManifest, UploadedDocChunk


def _make_manifest(n_chunks: int = 1) -> ChunkingManifest:
    now = datetime.now(tz=timezone.utc)
    chunks = [
        UploadedDocChunk(
            chunk_id=f"chunk-{i:04d}", session_id="__local__",
            source_filename="nacrt.txt", source_format="txt", source_sha256="abc",
            chunk_index=i, chunk_mode="recursive", article_label=None,
            text="Tekst pasusa broj " + str(i), token_count=10, char_count=20,
            created_at=now,
        )
        for i in range(n_chunks)
    ]
    return ChunkingManifest(
        source_filename="nacrt.txt", source_format="txt", source_sha256="abc",
        is_scanned=False, total_chunks=n_chunks, chunk_mode_used="recursive",
        article_labels_detected=[], token_p10=10, token_p50=10, token_p90=10,
        chunks=chunks,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. shared/kancelarija_utils.py
# ═══════════════════════════════════════════════════════════════════════════

class TestRagOwnerNamespace:
    def test_uses_kancelarija_when_present(self):
        from shared.kancelarija_utils import rag_owner_namespace
        assert rag_owner_namespace("user-1", "kanc-abc") == "kancelarija_kanc-abc"

    def test_falls_back_to_user_when_no_kancelarija(self):
        from shared.kancelarija_utils import rag_owner_namespace
        assert rag_owner_namespace("user-1", None) == "user_user-1"


class TestGetKancelarijaId:
    def test_admin_branch(self):
        from shared.kancelarija_utils import get_kancelarija_id

        supa = MagicMock()
        supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
            MagicMock(data={"id": "kanc-1"})

        result = asyncio.run(get_kancelarija_id(supa, "admin-uid"))
        assert result == "kanc-1"

    def test_member_branch_when_not_admin(self):
        from shared.kancelarija_utils import get_kancelarija_id

        supa = MagicMock()
        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            m = MagicMock()
            if name == "kancelarije":
                m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
            else:
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"kancelarija_id": "kanc-2"})
            return m

        supa.table.side_effect = _table
        result = asyncio.run(get_kancelarija_id(supa, "member-uid"))
        assert result == "kanc-2"

    def test_solo_user_returns_none(self):
        from shared.kancelarija_utils import get_kancelarija_id

        supa = MagicMock()

        def _table(name):
            m = MagicMock()
            m.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
            m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
            return m

        supa.table.side_effect = _table
        result = asyncio.run(get_kancelarija_id(supa, "solo-uid"))
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. uploaded_doc/ingest.py — namespace_override + extra_metadata
# ═══════════════════════════════════════════════════════════════════════════

class TestIngestSessionOwnerNamespace:
    def test_namespace_override_bypasses_prefix(self):
        from uploaded_doc.ingest import ingest_session

        manifest = _make_manifest(2)
        mock_index = MagicMock()
        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 3072] * 2

        with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
             patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
            ingest_session(
                manifest, "sess-1",
                namespace_override="kancelarija_kanc-1",
                extra_metadata={"predmet_id": "pred-1", "kancelarija_id": "kanc-1", "type": "case_doc"},
            )

        call = mock_index.upsert.call_args
        assert call.kwargs.get("namespace") == "kancelarija_kanc-1"

    def test_extra_metadata_merged_into_every_vector(self):
        from uploaded_doc.ingest import ingest_session

        manifest = _make_manifest(3)
        mock_index = MagicMock()
        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 3072] * 3

        with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
             patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
            ingest_session(
                manifest, "sess-2",
                namespace_override="user_u1",
                extra_metadata={"predmet_id": "pred-2", "kancelarija_id": "", "type": "draft_final"},
            )

        vectors = mock_index.upsert.call_args.kwargs.get("vectors")
        assert len(vectors) == 3
        for v in vectors:
            assert v["metadata"]["predmet_id"] == "pred-2"
            assert v["metadata"]["type"] == "draft_final"

    def test_no_override_keeps_original_prefix_behavior(self):
        """Backward compat: existing tmp_/pred_ callers (e.g. routers/dokument.py's
        ad-hoc analysis) are completely unaffected by the new parameters."""
        from uploaded_doc.ingest import ingest_session

        manifest = _make_manifest(1)
        mock_index = MagicMock()
        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 3072]

        with patch("uploaded_doc.ingest._get_pinecone_index", return_value=mock_index), \
             patch("uploaded_doc.ingest._get_embeddings_client", return_value=mock_embeddings):
            ingest_session(manifest, "sess-3")

        assert mock_index.upsert.call_args.kwargs.get("namespace") == "tmp_sess-3"


# ═══════════════════════════════════════════════════════════════════════════
# 3. app/services/doc_formatter.py — same_case labeling
# ═══════════════════════════════════════════════════════════════════════════

class TestFormatDocPassageSameCase:
    def _match(self):
        m = MagicMock()
        m.metadata = {
            "chunk_index": 1, "article_label": "", "source_filename": "ugovor.pdf",
            "text": "Neki tekst pasusa.",
        }
        return m

    def test_default_label_unchanged(self):
        from app.services.doc_formatter import format_doc_passage
        result = format_doc_passage(self._match())
        assert result.startswith("KORISNIKOV DOKUMENT [")

    def test_same_case_true_label(self):
        from app.services.doc_formatter import format_doc_passage
        result = format_doc_passage(self._match(), same_case=True)
        assert "OVAJ PREDMET" in result

    def test_same_case_false_label(self):
        from app.services.doc_formatter import format_doc_passage
        result = format_doc_passage(self._match(), same_case=False)
        assert "RANIJI PREDMET IZ KANCELARIJE" in result


# ═══════════════════════════════════════════════════════════════════════════
# 4. app/services/retrieve.py — cross-case retrieval (task item #4, main test)
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossCaseRetrieval:
    def test_returns_document_from_past_case_in_same_kancelarija(self):
        """The core regression test requested: a document indexed under a
        PAST predmet (different predmet_id) in the same kancelarija namespace
        must still be retrievable when querying from a NEW/current predmet --
        cross-case search must not filter other cases out."""
        from app.services.retrieve import retrieve_documents

        _match_current = MagicMock()
        _match_current.metadata = {
            "predmet_id": "predmet-NEW", "type": "case_doc", "chunk_index": 0,
            "article_label": "", "text": "Klauzula o raskidu ugovora u NOVOM predmetu.",
        }
        _match_current.score = 0.60

        _match_past = MagicMock()
        _match_past.metadata = {
            "predmet_id": "predmet-OLD", "type": "case_doc", "chunk_index": 0,
            "article_label": "", "text": "Klauzula o raskidu ugovora iz RANIJEG predmeta iste kancelarije.",
        }
        _match_past.score = 0.62  # slightly higher raw score than the current-case match

        mock_index = MagicMock()

        def _side_effect(**kwargs):
            ns = kwargs.get("namespace", "")
            res = MagicMock()
            if ns == "kancelarija_kanc-1":
                res.matches = [_match_current, _match_past]
            else:
                res.matches = []
            return res

        mock_index.query.side_effect = _side_effect

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 3072
        mock_cohere = MagicMock()
        mock_cohere.rerank.side_effect = Exception("no cohere")

        with patch("app.services.retrieve._get_index", return_value=mock_index), \
             patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
             patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
            docs, meta = retrieve_documents(
                "Da li postoji klauzula o raskidu ugovora?",
                kancelarija_namespace="kancelarija_kanc-1",
                current_predmet_id="predmet-NEW",
            )

        # Both the current-case AND the past-case passage must be present --
        # cross-case search must not have filtered the past case out.
        joined = "\n".join(docs)
        assert "NOVOM predmetu" in joined
        assert "RANIJEG predmeta" in joined

        passages = meta["doc_passages"]
        assert len(passages) == 2
        same_case_flags = {p["predmet_id"]: p["same_case"] for p in passages}
        assert same_case_flags["predmet-NEW"] is True
        assert same_case_flags["predmet-OLD"] is False

    def test_current_case_is_prioritized_despite_lower_raw_score(self):
        """The current predmet's match has a LOWER raw Pinecone score than the
        past-case match (0.60 vs 0.62) -- after the same-case boost it must
        rank first, proving prioritization actually happens, not just presence."""
        from app.services.retrieve import retrieve_documents

        _match_current = MagicMock()
        _match_current.metadata = {"predmet_id": "predmet-NEW", "type": "case_doc",
                                    "chunk_index": 0, "article_label": "", "text": "Sadržaj A iz trenutnog predmeta."}
        _match_current.score = 0.60

        _match_past = MagicMock()
        _match_past.metadata = {"predmet_id": "predmet-OLD", "type": "case_doc",
                                 "chunk_index": 0, "article_label": "", "text": "Sadržaj B iz ranijeg predmeta."}
        _match_past.score = 0.62

        mock_index = MagicMock()

        def _side_effect(**kwargs):
            ns = kwargs.get("namespace", "")
            res = MagicMock()
            res.matches = [_match_current, _match_past] if ns == "kancelarija_kanc-1" else []
            return res

        mock_index.query.side_effect = _side_effect
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 3072
        mock_cohere = MagicMock()
        mock_cohere.rerank.side_effect = Exception("no cohere")

        with patch("app.services.retrieve._get_index", return_value=mock_index), \
             patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
             patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
            _, meta = retrieve_documents(
                "upit", kancelarija_namespace="kancelarija_kanc-1", current_predmet_id="predmet-NEW",
            )

        passages = meta["doc_passages"]
        assert passages[0]["predmet_id"] == "predmet-NEW", (
            "Trenutni predmet mora biti prvi posle boost-a uprkos nižem sirovom skoru"
        )
        assert passages[0]["score"] > passages[1]["score"]

    def test_no_kancelarija_namespace_behaves_exactly_as_before(self):
        """Backward compat: existing callers that never pass kancelarija_namespace
        get the identical, unaffected behavior."""
        from app.services.retrieve import retrieve_documents

        mock_index = MagicMock()
        mock_index.query.return_value = MagicMock(matches=[])
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 3072
        mock_cohere = MagicMock()
        mock_cohere.rerank.side_effect = Exception("no cohere")

        with patch("app.services.retrieve._get_index", return_value=mock_index), \
             patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
             patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
            docs, meta = retrieve_documents("upit bez kancelarije")

        assert meta["doc_passages"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. routers/drafting.py — auto-index finalized drafts (draft_final)
# ═══════════════════════════════════════════════════════════════════════════

class TestIndexFinalizedDraft:
    def test_skips_when_predmet_not_owned_by_user(self):
        from routers.drafting import _index_finalized_draft

        supa = MagicMock()
        supa.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
            MagicMock(data=None)

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("uploaded_doc.ingest.ingest_session") as mock_ingest:
            asyncio.run(_index_finalized_draft({"user_id": "u1"}, "not-mine", "tuzba_naknada_stete", "Tužba", "Tekst nacrta."))

        mock_ingest.assert_not_called()

    def test_indexes_as_draft_final_when_owned(self):
        from routers.drafting import _index_finalized_draft

        supa = MagicMock()

        def _table(name):
            m = MagicMock()
            if name == "predmeti":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"id": "pred-1"})
            elif name == "predmet_dokumenti":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = \
                    MagicMock(data=[])
                m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "dok-1"}])
            return m

        supa.table.side_effect = _table

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value="kanc-1")), \
             patch("uploaded_doc.ingest.ingest_session", return_value=1) as mock_ingest:
            asyncio.run(_index_finalized_draft(
                {"user_id": "u1"}, "pred-1", "tuzba_naknada_stete", "Tužba za naknadu štete", "Puni tekst finalizovanog nacrta.",
            ))

        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs["namespace_override"] == "kancelarija_kanc-1"
        assert call_kwargs["extra_metadata"]["type"] == "draft_final"
        assert call_kwargs["extra_metadata"]["predmet_id"] == "pred-1"

    def test_pinecone_failure_does_not_raise(self):
        """Fire-and-forget guarantee: even if ingest_session raises, this must
        never propagate (it runs via asyncio.create_task, uncaught here would
        be a silently-swallowed-but-logged exception at worst -- but the
        function itself must not raise when awaited directly, as this test does)."""
        from routers.drafting import _index_finalized_draft

        supa = MagicMock()

        def _table(name):
            m = MagicMock()
            if name == "predmeti":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"id": "pred-1"})
            elif name == "predmet_dokumenti":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = \
                    MagicMock(data=[])
                m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "dok-1"}])
            return m

        supa.table.side_effect = _table

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
             patch("uploaded_doc.ingest.ingest_session", side_effect=RuntimeError("pinecone down")):
            # Should not raise:
            asyncio.run(_index_finalized_draft({"user_id": "u1"}, "pred-1", "tip", "Naziv", "Tekst."))
