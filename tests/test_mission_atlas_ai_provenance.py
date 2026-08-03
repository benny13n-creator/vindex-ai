# -*- coding: utf-8 -*-
"""
Mission Atlas (2026-08-03) — AI Provenance & Decision Traceability.

Covers:
1. shared/ai_provenance.py — request/case context propagation, nesting/restore,
   correlation_id generation, hashing.
2. security/ai_forensics.py::log_provenance_from_wrapper — the persistence
   sink, including the "try extended schema, fall back to legacy columns"
   pre-migration compatibility path.
3. shared/ai_client.py — the canonical wrapper now captures provenance for
   every chat-completion AND embedding call, automatically, with zero
   per-call-site changes (same structural guarantee SEC-003 already proved
   for the prompt-injection guard).
4. Wrapper coverage — Completions/AsyncCompletions/Embeddings/AsyncEmbeddings
   are ALL patched at the class level (mirrors test_sec003_llm_wrapper.py's
   TestStructuralPatchIsActive pattern).
5. The migration draft (089) contains the immutability trigger and required
   columns.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Uvoz api.py pokreće _patch_openai_module()/_patch_prompt_guard() bootstrap.
from api import app  # noqa: E402,F401
from openai.resources.chat.completions.completions import AsyncCompletions, Completions  # noqa: E402
from openai.resources.embeddings import AsyncEmbeddings, Embeddings  # noqa: E402

import shared.ai_client as ai_client  # noqa: E402
import shared.ai_provenance as ai_provenance  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_ai_provenance_context():
    """set_request_context() intentionally has no restore (see module
    docstring — safe in production because each request is its own asyncio
    Task), but pytest test functions in this file share a thread/context, so
    reset explicitly here to keep this file's tests from leaking global
    request-context state into other test files in the same run."""
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


# ═══════════════════════════════════════════════════════════════════════════
# 1. shared/ai_provenance.py — context propagation
# ═══════════════════════════════════════════════════════════════════════════

class TestContextPropagation:
    def test_request_context_visible_via_current_context(self):
        ai_provenance.set_request_context(user_id="user-1", tenant_id="firm-1")
        ctx = ai_provenance.current_context()
        assert ctx["user_id"] == "user-1"
        assert ctx["tenant_id"] == "firm-1"

    def test_case_context_adds_predmet_and_module_fields(self):
        ai_provenance.set_request_context(user_id="user-2")
        with ai_provenance.case_context(predmet_id="pred-1", module_name="case_dna", operation_name="genome_extraction"):
            ctx = ai_provenance.current_context()
            assert ctx["predmet_id"] == "pred-1"
            assert ctx["module_name"] == "case_dna"
            assert ctx["operation_name"] == "genome_extraction"
            assert ctx["user_id"] == "user-2"  # request context still visible

    def test_case_context_restores_previous_value_on_exit(self):
        with ai_provenance.case_context(predmet_id="outer"):
            with ai_provenance.case_context(predmet_id="inner"):
                assert ai_provenance.current_context()["predmet_id"] == "inner"
            assert ai_provenance.current_context()["predmet_id"] == "outer"

    def test_case_context_yields_a_correlation_id(self):
        with ai_provenance.case_context(module_name="x") as cid:
            assert isinstance(cid, str)
            assert len(cid) > 0
            assert ai_provenance.current_context()["correlation_id"] == cid

    def test_case_context_respects_explicit_correlation_id(self):
        with ai_provenance.case_context(module_name="x", correlation_id="fixed-id") as cid:
            assert cid == "fixed-id"

    def test_sha256_text_deterministic_and_none_safe(self):
        assert ai_provenance.sha256_text(None) is None
        assert ai_provenance.sha256_text("") is None
        h1 = ai_provenance.sha256_text("isti tekst")
        h2 = ai_provenance.sha256_text("isti tekst")
        assert h1 == h2
        assert h1 != ai_provenance.sha256_text("drugi tekst")

    def test_new_correlation_id_unique(self):
        assert ai_provenance.new_correlation_id() != ai_provenance.new_correlation_id()


# ═══════════════════════════════════════════════════════════════════════════
# 2. security/ai_forensics.py::log_provenance_from_wrapper
# ═══════════════════════════════════════════════════════════════════════════

class TestLogProvenanceFromWrapper:
    @pytest.mark.anyio
    async def test_writes_full_extended_record_when_schema_supports_it(self):
        from security.ai_forensics import log_provenance_from_wrapper

        inserted = []
        chain = MagicMock()
        chain.insert = MagicMock(side_effect=lambda rec: inserted.append(rec) or chain)
        chain.execute = MagicMock(return_value=MagicMock())
        supa = MagicMock()
        supa.table = MagicMock(return_value=chain)

        with patch("api._get_supa", return_value=supa):
            await log_provenance_from_wrapper(
                module_name="case_dna", operation_name="genome_extraction",
                model_provider="openai", model_name="gpt-4o",
                system_prompt_hash="sh1", user_prompt_hash="uh1",
                token_usage_input=100, token_usage_output=50, latency_ms=1200,
                output_hash="oh1", correlation_id="corr-1", user_id="user-1",
                predmet_id="pred-1",
            )

        assert len(inserted) == 1
        rec = inserted[0]
        assert rec["module_name"] == "case_dna"
        assert rec["correlation_id"] == "corr-1"
        assert rec["predmet_id"] == "pred-1"
        assert rec["status"] == "success"

    @pytest.mark.anyio
    async def test_falls_back_to_legacy_columns_when_extended_insert_fails(self):
        """Pre-migration compatibility: if the extended columns don't exist
        yet, the first insert.execute() raises (simulated), and the function
        must retry with only the 043-era legacy columns instead of losing
        the row entirely."""
        from security.ai_forensics import log_provenance_from_wrapper

        attempts = []

        def _make_chain(should_fail: bool):
            c = MagicMock()

            def _insert(rec):
                attempts.append(rec)
                return c

            def _execute():
                if should_fail:
                    raise Exception('column "module_name" does not exist')
                return MagicMock()

            c.insert = MagicMock(side_effect=_insert)
            c.execute = MagicMock(side_effect=_execute)
            return c

        call_count = {"n": 0}

        def _table(name):
            call_count["n"] += 1
            return _make_chain(should_fail=(call_count["n"] == 1))

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("api._get_supa", return_value=supa):
            await log_provenance_from_wrapper(
                module_name="strategija", operation_name="red_team",
                model_provider="openai", model_name="gpt-4o",
                latency_ms=500, correlation_id="corr-2",
            )

        assert len(attempts) == 2  # wide attempt, then legacy fallback
        legacy_attempt = attempts[1]
        assert "module_name" not in legacy_attempt  # legacy-only subset
        assert legacy_attempt.get("model") == "gpt-4o"

    @pytest.mark.anyio
    async def test_never_raises_even_if_supabase_completely_unreachable(self):
        from security.ai_forensics import log_provenance_from_wrapper

        with patch("api._get_supa", side_effect=Exception("no network")):
            await log_provenance_from_wrapper(
                module_name="copilot", model_provider="openai", model_name="gpt-4o-mini",
            )  # must not raise


# ═══════════════════════════════════════════════════════════════════════════
# 3 & 4. shared/ai_client.py — canonical wrapper capture + structural coverage
# ═══════════════════════════════════════════════════════════════════════════

class TestWrapperCoverageStructural:
    """Mirrors tests/test_sec003_llm_wrapper.py's TestStructuralPatchIsActive
    — proves the SAME patch point used for the security guard also carries
    provenance capture, for both chat completions and embeddings."""

    def test_completions_create_is_patched(self):
        assert Completions.create.__name__ == "_guarded_create"

    def test_async_completions_create_is_patched(self):
        assert AsyncCompletions.create.__name__ == "_guarded_acreate"

    def test_embeddings_create_is_patched(self):
        assert Embeddings.create.__name__ == "_tracked_embed"

    def test_async_embeddings_create_is_patched(self):
        assert AsyncEmbeddings.create.__name__ == "_tracked_aembed"


class TestChatProvenanceCapture:
    def _fake_response(self):
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="AI odgovor tekst"))],
            usage=types.SimpleNamespace(prompt_tokens=120, completion_tokens=40),
            model="gpt-4o-2024-08-06",
        )

    def test_sync_call_triggers_provenance_capture_with_hashes_and_tokens(self):
        captured = {}

        def _fake_log_provenance(**kwargs):
            captured.update(kwargs)

        fake_self = types.SimpleNamespace(_client=types.SimpleNamespace())

        with patch.object(ai_client, "_orig_create", return_value=self._fake_response()), \
             patch("security.ai_forensics.log_provenance_from_wrapper", side_effect=_fake_log_provenance):
            with ai_provenance.case_context(predmet_id="pred-99", module_name="test_module", operation_name="test_op"):
                result = Completions.create(
                    fake_self,
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Sistemska instrukcija"},
                        {"role": "user", "content": "Korisnicko pitanje"},
                    ],
                )

        assert result.choices[0].message.content == "AI odgovor tekst"
        assert captured["module_name"] == "test_module"
        assert captured["predmet_id"] == "pred-99"
        assert captured["token_usage_input"] == 120
        assert captured["token_usage_output"] == 40
        assert captured["model_name"] == "gpt-4o-2024-08-06"  # response.model wins over requested kwarg
        assert captured["system_prompt_hash"] == ai_provenance.sha256_text("Sistemska instrukcija")
        assert captured["user_prompt_hash"] == ai_provenance.sha256_text("Korisnicko pitanje")
        assert captured["output_hash"] == ai_provenance.sha256_text("AI odgovor tekst")
        assert captured["correlation_id"]
        assert captured["status"] == "success"
        assert isinstance(captured["latency_ms"], int)

    def test_capture_runs_on_error_path_too_with_status_error(self):
        captured = {}

        def _fake_log_provenance(**kwargs):
            captured.update(kwargs)

        fake_self = types.SimpleNamespace(_client=types.SimpleNamespace())

        with patch.object(ai_client, "_orig_create", side_effect=RuntimeError("upstream boom")), \
             patch("security.ai_forensics.log_provenance_from_wrapper", side_effect=_fake_log_provenance):
            with pytest.raises(RuntimeError):
                Completions.create(fake_self, model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        assert captured["status"] == "error"
        assert "upstream boom" in captured["error_message"]

    @pytest.mark.anyio
    async def test_async_call_triggers_provenance_capture(self):
        """The async wrapper path schedules the capture via loop.create_task
        (fire-and-forget, same convention as this codebase's audit logging
        and Event Bus publish()) rather than awaiting it inline -- so the
        test must yield control back to the loop once before the scheduled
        task has actually run."""
        import asyncio
        captured = {}

        async def _fake_log_provenance(**kwargs):
            captured.update(kwargs)

        fake_self = types.SimpleNamespace(_client=types.SimpleNamespace())

        async def _fake_orig_acreate(self, *args, **kwargs):
            return self._fake_response_holder

        fake_self._fake_response_holder = self._fake_response()

        with patch.object(ai_client, "_orig_acreate", new=_fake_orig_acreate), \
             patch("security.ai_forensics.log_provenance_from_wrapper", side_effect=_fake_log_provenance):
            result = await AsyncCompletions.create(
                fake_self, model="gpt-4o", messages=[{"role": "user", "content": "async pitanje"}],
            )
            await asyncio.sleep(0)  # let the fire-and-forget capture task run

        assert result.choices[0].message.content == "AI odgovor tekst"
        assert captured["status"] == "success"
        assert captured["user_prompt_hash"] == ai_provenance.sha256_text("async pitanje")


class TestEmbeddingProvenanceCapture:
    def test_sync_embedding_call_triggers_capture(self):
        captured = {}

        def _fake_log_provenance(**kwargs):
            captured.update(kwargs)

        fake_response = types.SimpleNamespace(
            usage=types.SimpleNamespace(prompt_tokens=15),
            model="text-embedding-3-small",
        )
        fake_self = types.SimpleNamespace(_client=types.SimpleNamespace())

        with patch.object(ai_client, "_orig_embed", return_value=fake_response), \
             patch("security.ai_forensics.log_provenance_from_wrapper", side_effect=_fake_log_provenance):
            with ai_provenance.case_context(module_name="retrieve", operation_name="embedding"):
                Embeddings.create(fake_self, input="tekst za embedovanje", model="text-embedding-3-small")

        assert captured["module_name"] == "retrieve"
        assert captured["token_usage_input"] == 15
        assert captured["model_name"] == "text-embedding-3-small"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Migration draft — immutability trigger + required columns present
# ═══════════════════════════════════════════════════════════════════════════

class TestMigrationDraft:
    @pytest.fixture(scope="class")
    def migration_sql(self):
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "migrations" / "089_ai_provenance_extension.sql"
        assert path.exists(), "Migration 089 draft must exist"
        return path.read_text(encoding="utf-8")

    def test_has_update_blocking_trigger(self, migration_sql):
        assert "BEFORE UPDATE ON ai_forensics" in migration_sql
        assert "RAISE EXCEPTION" in migration_sql

    def test_does_not_block_delete(self, migration_sql):
        """Deliberate: services/retention_service.py's GDPR-driven cleanup
        job must keep working -- immutability here means no silent rewrite,
        not 'delete is architecturally impossible'."""
        assert "BEFORE UPDATE OR DELETE ON ai_forensics" not in migration_sql

    def test_has_required_provenance_columns(self, migration_sql):
        for col in (
            "tenant_id", "predmet_id", "document_id", "module_name",
            "operation_name", "model_provider", "model_version",
            "system_prompt_hash", "user_prompt_hash", "retrieved_context_ids",
            "knowledge_sources", "retrieval_query", "confidence_score",
            "hallucination_check_result", "parent_event_id", "correlation_id",
            "audit_reference",
        ):
            assert col in migration_sql, f"Missing column: {col}"

    def test_has_replay_indexes(self, migration_sql):
        assert "idx_ai_forensics_correlation_id" in migration_sql
        assert "idx_ai_forensics_predmet_id" in migration_sql
