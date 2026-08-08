# -*- coding: utf-8 -*-
"""
Tests for Institutional Memory Architecture V2 (2026-07-26):
  STUB 1 — Quality Gate & Staging Memory
  STUB 2 — Origin & Lineage
  STUB 3 — Memory Decay & Temporal Validity
  STUB 4 — Explainable Retrieval

See docs/INSTITUTIONAL_MEMORY_V2_IMPLEMENTATION.md for the full architecture
report this implements.
"""
import asyncio
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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


def _iso_years_ago(years: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=int(years * 365.25))).isoformat()


@contextmanager
def _stub_retrieve_llm():
    """Stub the OpenAI chat client used throughout retrieve.py.

    retrieve_documents() unconditionally fires several gpt-4o-mini calls that
    have nothing to do with Pinecone: _dekomponuj_query / decompose_query and
    _generiši_hyde (both in a ThreadPoolExecutor), _prosiri_query_gpt_wrapper,
    _gpt_rerank when Cohere is unavailable, and _oceni_relevantnost in the
    CRAG loop. All of them build their client through retrieve._get_client(),
    which the TestTimeDecayRanking / TestMatchBreakdown cases below never
    patched -- so mocking _get_index/_get_embeddings/_get_cohere still left
    real, billed requests going out on every call.

    The stub returns an empty completion, which drives each call site down
    its own documented empty/neutral branch: no sub-queries, no HyDE text, no
    GPT expansion, rerank falls back to the internal score order, CRAG treats
    the docs as RELEVANTNO and stops. The time-decay and origin-weight
    ranking under test is a property of that internal scoring, so it is now
    measured against a deterministic ordering rather than against whatever a
    live gpt-4o-mini reranker happened to return.
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


# ═══════════════════════════════════════════════════════════════════════════
# STUB 1a — services/quality_gate.py
# ═══════════════════════════════════════════════════════════════════════════

class TestQualityGate:
    def test_verified_citations_raise_confidence(self):
        from services.quality_gate import evaluate_draft_quality

        tekst = "Tuženi duguje na osnovu čl. 172 ZOO. Sud utvrđuje obavezu tužioca."
        with patch("app.services.retrieve._direktan_fetch_clana", return_value=[MagicMock()]):
            result = asyncio.run(evaluate_draft_quality(tekst, "tuzba_naknada_stete"))

        assert result["detail"]["citations_found"] == 1
        assert result["detail"]["citations_verified"] == 1
        assert result["confidence_score"] > 0.5

    def test_unverifiable_citation_lowers_confidence(self):
        from services.quality_gate import evaluate_draft_quality

        tekst = "Tuženi duguje na osnovu čl. 99999 nepostojećeg zakona."
        with patch("app.services.retrieve._direktan_fetch_clana", return_value=[]):
            result = asyncio.run(evaluate_draft_quality(tekst, "tuzba_naknada_stete"))

        assert result["detail"]["citations_verified"] == 0
        assert result["detail"]["citation_score"] == 0.0

    def test_no_citations_is_neutral_not_penalized_to_zero(self):
        from services.quality_gate import evaluate_draft_quality

        result = asyncio.run(evaluate_draft_quality("Urgencija bez ijednog citata zakona.", "urgencija_sudu"))
        assert result["detail"]["citations_found"] == 0
        assert result["confidence_score"] > 0.0

    def test_formal_completeness_checks_present(self):
        from services.quality_gate import evaluate_draft_quality

        tekst = "Osnovni sud u Beogradu. Tužilac protiv Tuženog. Član 172 ZOO."
        with patch("app.services.retrieve._direktan_fetch_clana", return_value=[MagicMock()]):
            result = asyncio.run(evaluate_draft_quality(tekst, "tuzba_naknada_stete"))

        checks = result["detail"]["completeness_checks"]
        assert checks["sud"] is True
        assert checks["stranke"] is True
        assert checks["pravni_osnov"] is True


# ═══════════════════════════════════════════════════════════════════════════
# STUB 2/3 — shared/vector_origin.py
# ═══════════════════════════════════════════════════════════════════════════

class TestVectorOrigin:
    def test_origin_weights_match_spec(self):
        from shared.vector_origin import ORIGIN_WEIGHTS, ORIGIN_LAW, ORIGIN_COURT, ORIGIN_LAWYER_VERIFIED, ORIGIN_CLIENT_DOC, ORIGIN_AI_GENERATED
        assert ORIGIN_WEIGHTS[ORIGIN_LAW] == 1.0
        assert ORIGIN_WEIGHTS[ORIGIN_COURT] == 1.0
        assert ORIGIN_WEIGHTS[ORIGIN_LAWYER_VERIFIED] == 0.95
        assert ORIGIN_WEIGHTS[ORIGIN_CLIENT_DOC] == 0.80
        assert ORIGIN_WEIGHTS[ORIGIN_AI_GENERATED] == 0.00

    def test_law_and_court_never_decay(self):
        from shared.vector_origin import freshness_weight, ORIGIN_LAW, ORIGIN_COURT
        old = _iso_years_ago(20)
        assert freshness_weight(ORIGIN_LAW, old) == 1.0
        assert freshness_weight(ORIGIN_COURT, old) == 1.0

    def test_client_doc_older_than_3_years_decays(self):
        from shared.vector_origin import freshness_weight, ORIGIN_CLIENT_DOC
        fresh = freshness_weight(ORIGIN_CLIENT_DOC, _iso_years_ago(1))
        stale = freshness_weight(ORIGIN_CLIENT_DOC, _iso_years_ago(8))
        assert fresh == 1.0
        assert stale < fresh
        assert stale >= 0.5  # never below the floor

    def test_golden_template_exempt_from_decay(self):
        from shared.vector_origin import freshness_weight, ORIGIN_LAWYER_VERIFIED
        w = freshness_weight(ORIGIN_LAWYER_VERIFIED, _iso_years_ago(15), golden_template=True)
        assert w == 1.0

    def test_deprecated_status_heavily_penalized(self):
        from shared.vector_origin import freshness_weight, ORIGIN_LAWYER_VERIFIED
        w = freshness_weight(ORIGIN_LAWYER_VERIFIED, _iso_years_ago(0.1), status="DEPRECATED")
        assert w == 0.1

    def test_expired_valid_until_heavily_penalized(self):
        from shared.vector_origin import freshness_weight, ORIGIN_LAWYER_VERIFIED
        w = freshness_weight(ORIGIN_LAWYER_VERIFIED, _iso_years_ago(0.1), valid_until=_iso_years_ago(0.05))
        assert w == 0.1


# ═══════════════════════════════════════════════════════════════════════════
# STUB 1b/2 — routers/drafting.py: staging gate (never direct-index)
# ═══════════════════════════════════════════════════════════════════════════

class TestStagingNeverAutoIndexes:
    def test_unapproved_draft_never_reaches_pinecone(self):
        """Core regression test for STUB 1: generating a draft (with predmet_id)
        must NEVER call ingest_session -- it only creates a staging_memory row."""
        from routers.drafting import _stage_draft_for_review

        supa = MagicMock()
        staging_insert_mock = MagicMock()
        staging_insert_mock.execute.return_value = MagicMock(data=[{"id": "stg-1"}])

        def _table(name):
            m = MagicMock()
            if name == "predmeti":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"id": "pred-1"})
            elif name == "staging_memory":
                m.insert.return_value = staging_insert_mock
                # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-031): _stage_draft_for_review
                # now checks for a recent duplicate before inserting -- empty data means
                # "no duplicate found", so the insert path below still runs.
                m.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = \
                    MagicMock(data=[])
            return m

        supa.table.side_effect = _table

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value="kanc-1")), \
             patch("uploaded_doc.ingest.ingest_session") as mock_ingest:
            asyncio.run(_stage_draft_for_review(
                {"user_id": "u1"}, "pred-1", "tuzba_naknada_stete", "Tužba", "Tekst nacrta bez potvrde.",
            ))

        mock_ingest.assert_not_called()
        staging_insert_mock.execute.assert_called_once()

    def test_staging_row_carries_quality_score(self):
        from routers.drafting import _stage_draft_for_review

        supa = MagicMock()
        captured = {}

        def _table(name):
            m = MagicMock()
            if name == "predmeti":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"id": "pred-1"})
            elif name == "staging_memory":
                def _insert(payload):
                    captured.update(payload)
                    r = MagicMock()
                    r.execute.return_value = MagicMock(data=[{"id": "stg-1"}])
                    return r
                m.insert.side_effect = _insert
                # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-031): see same note above.
                m.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = \
                    MagicMock(data=[])
            return m

        supa.table.side_effect = _table

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
             patch("services.quality_gate.evaluate_draft_quality", new=AsyncMock(return_value={
                 "confidence_score": 0.42, "detail": {"citations_found": 0},
             })):
            asyncio.run(_stage_draft_for_review({"user_id": "u1"}, "pred-1", "tip", "Naziv", "Tekst."))

        # is_lawyer_approved/status nisu eksplicitno u insert payload-u --
        # oslanjaju se na DB DEFAULT false/'pending' (migracija 088).
        assert captured["confidence_score"] == 0.42
        assert captured["predmet_id"] == "pred-1"
        assert captured["tekst"] == "Tekst."

    def test_skips_when_predmet_not_owned(self):
        from routers.drafting import _stage_draft_for_review

        supa = MagicMock()
        supa.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
            MagicMock(data=None)

        with patch("routers.drafting._get_supa", return_value=supa), \
             patch("uploaded_doc.ingest.ingest_session") as mock_ingest:
            asyncio.run(_stage_draft_for_review({"user_id": "u1"}, "not-mine", "tip", "Naziv", "Tekst."))

        mock_ingest.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# STUB 1c — routers/drafting.py: approve promotes ONLY with both conditions
# ═══════════════════════════════════════════════════════════════════════════

class TestApprovalGate:
    def test_approved_draft_gets_lawyer_verified_and_is_indexed(self):
        """Approved + confidence >= 0.85 -> promoted with origin=LAWYER_VERIFIED,
        lineage back to AI_GENERATED preserved via origin_chain/parent_id."""
        from routers.drafting import _promote_staged_draft_to_pinecone

        supa = MagicMock()

        def _table(name):
            m = MagicMock()
            if name == "predmet_dokumenti":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = \
                    MagicMock(data=[])
                m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "dok-1"}])
            return m

        supa.table.side_effect = _table

        staging_row = {
            "id": "stg-1", "user_id": "u1", "kancelarija_id": "kanc-1",
            "predmet_id": "pred-1", "tip": "tuzba_naknada_stete", "naziv": "Tužba",
            "tekst": "Puni tekst odobrenog nacrta.", "confidence_score": 0.90,
        }

        with patch("uploaded_doc.ingest.ingest_session", return_value=1) as mock_ingest:
            promoted = asyncio.run(_promote_staged_draft_to_pinecone(supa, staging_row))

        assert promoted is True
        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs["namespace_override"] == "kancelarija_kanc-1"
        meta = call_kwargs["extra_metadata"]
        assert meta["origin"] == "LAWYER_VERIFIED"
        assert meta["parent_id"] == "stg-1"
        assert meta["origin_chain"] == ["AI_GENERATED", "LAWYER_VERIFIED"]
        assert meta["type"] == "draft_final"

    def test_low_confidence_approval_does_not_promote(self):
        """Business rule: is_lawyer_approved alone is NOT sufficient -- the
        /api/staging/{id}/approve route must not call the promotion helper
        at all when confidence_score is below the 0.85 threshold."""
        from routers.drafting import _APPROVAL_CONFIDENCE_THRESHOLD

        assert _APPROVAL_CONFIDENCE_THRESHOLD == 0.85

    def test_approve_endpoint_skips_promotion_below_threshold(self):
        from fastapi.testclient import TestClient
        from shared.deps import get_current_user
        from api import app

        supa = MagicMock()
        staging_row = {
            "id": "stg-low", "user_id": "u1", "kancelarija_id": None,
            "predmet_id": "pred-1", "tip": "tip", "naziv": "Naziv",
            "tekst": "Tekst.", "confidence_score": 0.40,
        }

        def _table(name):
            m = MagicMock()
            if name == "staging_memory":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data=staging_row)
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[staging_row])
            return m

        supa.table.side_effect = _table

        async def _fake_user():
            return {"user_id": "u1", "email": "advokat@example.com"}

        app.dependency_overrides[get_current_user] = _fake_user
        try:
            with patch("routers.drafting._get_supa", return_value=supa), \
                 patch("uploaded_doc.ingest.ingest_session") as mock_ingest:
                client = TestClient(app, raise_server_exceptions=False)
                r = client.post("/api/staging/stg-low/approve")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert r.status_code == 200
        body = r.json()
        assert body["indexed"] is False
        mock_ingest.assert_not_called()

    def test_reject_endpoint_never_touches_pinecone(self):
        from fastapi.testclient import TestClient
        from shared.deps import get_current_user
        from api import app

        supa = MagicMock()

        def _table(name):
            m = MagicMock()
            if name == "staging_memory":
                m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"id": "stg-x"})
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "stg-x"}])
            return m

        supa.table.side_effect = _table

        async def _fake_user():
            return {"user_id": "u1", "email": "advokat@example.com"}

        app.dependency_overrides[get_current_user] = _fake_user
        try:
            with patch("routers.drafting._get_supa", return_value=supa), \
                 patch("uploaded_doc.ingest.ingest_session") as mock_ingest:
                client = TestClient(app, raise_server_exceptions=False)
                r = client.post("/api/staging/stg-x/reject")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
        mock_ingest.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# STUB 3 — retrieve.py: decayed document ranks lower than fresh valid one
# ═══════════════════════════════════════════════════════════════════════════

class TestTimeDecayRanking:
    def test_deprecated_document_ranks_below_fresh_valid_one(self):
        """Two matches with IDENTICAL raw similarity score: one DEPRECATED
        (sporni/prevaziđen status), one fresh and valid -- the fresh one
        must win despite equal raw Pinecone score, proving the decay factor
        actually changes ranking, not just metadata."""
        from app.services.retrieve import retrieve_documents

        _match_deprecated = MagicMock()
        _match_deprecated.metadata = {
            "predmet_id": "pred-1", "type": "draft_final", "origin": "LAWYER_VERIFIED",
            "status": "DEPRECATED", "created_at": _iso_years_ago(5),
            "chunk_index": 0, "article_label": "", "text": "Stav baziran na ukinutom tumačenju zakona.",
        }
        _match_deprecated.score = 0.80

        _match_fresh = MagicMock()
        _match_fresh.metadata = {
            "predmet_id": "pred-2", "type": "draft_final", "origin": "LAWYER_VERIFIED",
            "created_at": _iso_years_ago(0.2),
            "chunk_index": 0, "article_label": "", "text": "Stav baziran na trenutno važećem tumačenju zakona.",
        }
        _match_fresh.score = 0.80  # identical raw score

        mock_index = MagicMock()

        def _side_effect(**kwargs):
            ns = kwargs.get("namespace", "")
            res = MagicMock()
            res.matches = [_match_deprecated, _match_fresh] if ns == "kancelarija_kanc-1" else []
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
            _, meta = retrieve_documents("upit", kancelarija_namespace="kancelarija_kanc-1")

        passages = meta["doc_passages"]
        assert passages[0]["predmet_id"] == "pred-2", "Sveži važeći dokument mora pobediti prevaziđen uprkos istom sirovom skoru"
        assert passages[0]["score"] > passages[1]["score"]

    def test_ai_generated_origin_never_surfaces_even_if_present(self):
        """Defense in depth (STUB 2): even if an AI_GENERATED-origin vector
        somehow ended up in the kancelarija namespace, retrieval must exclude
        it entirely, not just down-rank it."""
        from app.services.retrieve import retrieve_documents

        _match_ai = MagicMock()
        _match_ai.metadata = {"predmet_id": "pred-1", "type": "draft_final", "origin": "AI_GENERATED",
                               "chunk_index": 0, "article_label": "", "text": "Neproveren AI tekst koji ne sme da se pojavi."}
        _match_ai.score = 0.99  # highest possible score -- must still be excluded

        mock_index = MagicMock()

        def _side_effect(**kwargs):
            res = MagicMock()
            res.matches = [_match_ai] if kwargs.get("namespace") == "kancelarija_kanc-1" else []
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
            docs, meta = retrieve_documents("upit", kancelarija_namespace="kancelarija_kanc-1")

        assert meta["doc_passages"] == []
        assert not any("Neproveren AI tekst" in d for d in docs)


# ═══════════════════════════════════════════════════════════════════════════
# STUB 4 — retrieve.py returns match_breakdown
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchBreakdown:
    def test_match_breakdown_present_and_shaped(self):
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

        assert "match_breakdown" in meta
        assert isinstance(meta["match_breakdown"], list)

    def test_match_breakdown_fields_for_kancelarija_passage(self):
        from app.services.retrieve import retrieve_documents

        _match = MagicMock()
        _match.metadata = {
            "predmet_id": "pred-1", "type": "case_doc", "origin": "CLIENT_DOC",
            "chunk_index": 0, "article_label": "Član 5", "text": "Dovoljno dug tekst pasusa da prođe prag od 50 karaktera.",
        }
        _match.score = 0.77

        mock_index = MagicMock()

        def _side_effect(**kwargs):
            res = MagicMock()
            res.matches = [_match] if kwargs.get("namespace") == "kancelarija_kanc-1" else []
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
            _, meta = retrieve_documents("upit", kancelarija_namespace="kancelarija_kanc-1")

        breakdown = meta["match_breakdown"]
        assert len(breakdown) >= 1
        kanc_entries = [b for b in breakdown if b["origin_label"] == "Dokaz/dokument iz predmeta"]
        assert len(kanc_entries) == 1
        assert kanc_entries[0]["matched_by_law_article"] == "Član 5"
