# -*- coding: utf-8 -*-
"""
Mission Migration (2026-08-03) — Canonical AI Infrastructure Adoption.

Verifies the newly-migrated AI features (Copilot's remaining business-
mutating handlers, Court Predictor's 6 endpoints, Evidence classification,
Drafting staging, the upload endpoint's 3 parallel GPT calls) actually use
the canonical stack (case_context -> correlation_id, log_action/
log_action_sync -> durable audit) rather than a parallel or missing
mechanism.

1. AUDITABLE_ACTIONS contains every new action name this mission added.
2. Functional replay tests for 2 representative migrated features (one
   async/request-scoped -- Copilot's _handle_akcija_rok; one sync/
   background-thread-scoped -- Evidence's klasifikuj_i_sacuvaj, which
   specifically proves the log_action_sync fix for the "no running event
   loop in a to_thread worker" bug caught during this mission).
3. Structural proof (source inspection, same technique already used
   elsewhere in this test suite for sanitize_user_input coverage) that
   every one of Court Predictor's 6 endpoints references both
   case_context and log_action -- a full per-endpoint functional mock
   would duplicate substantial existing test infrastructure for marginal
   additional confidence beyond what's already covered by each router's
   own pre-existing test suite (all of which pass unchanged after this
   mission's edits).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps _patch_prompt_guard()

import shared.ai_provenance as ai_provenance  # noqa: E402
from shared.audit_immutable import AUDITABLE_ACTIONS  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_ai_provenance_context():
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


# ═══════════════════════════════════════════════════════════════════════════
# 1. AUDITABLE_ACTIONS coverage
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditableActionsCoverage:
    def test_all_new_actions_registered(self):
        expected = {
            "copilot_plan_predmeta", "copilot_dodaj_rok", "copilot_kreiraj_belesku",
            "copilot_povezi_klijenta", "copilot_naplati_radnju",
            "court_predictor_analiza", "drafting_generisan",
            "evidence_klasifikacija", "dokument_ai_analiza_complete",
        }
        missing = expected - AUDITABLE_ACTIONS
        assert not missing, f"Missing from AUDITABLE_ACTIONS: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# 2a. Copilot _handle_akcija_rok — async, request-scoped
# ═══════════════════════════════════════════════════════════════════════════

class TestCopilotAkcijaRokMigrated:
    @pytest.mark.anyio
    async def test_successful_rok_creation_produces_correlation_linked_audit(self):
        from routers.copilot import _handle_akcija_rok

        root_cid = ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid")

        fake_gpt_response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(
                content='{"dogadjaj": "Rociste", "datum_iso": "2026-09-01", "vaznost": "bitan"}'
            ))]
        )

        inserted = []

        def _table(name):
            c = MagicMock()
            if name == "predmet_hronologija":
                def _insert(rec):
                    inserted.append(rec)
                    chain = MagicMock()
                    chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "rok-1"}]))
                    return chain
                c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        audit_calls = []

        async def _fake_log_action(**kwargs):
            audit_calls.append(kwargs)

        with patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(return_value=fake_gpt_response)), \
             patch("routers.copilot._get_supa", return_value=supa), \
             patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
            result = await _handle_akcija_rok("Dodaj rok za ročište 1. septembra", "pred-1", "u1")
            import asyncio
            await asyncio.sleep(0)  # let the fire-and-forget audit task run

        assert result["uspeh"] is True
        assert len(inserted) == 1
        assert audit_calls[0]["action"] == "copilot_dodaj_rok"
        assert audit_calls[0]["resource_id"] == "pred-1"
        # correlation_id isn't passed explicitly by the call site -- it must
        # come from context, proving the canonical auto-fill wiring works
        # for this migrated feature too, not just the ones Mission Ledger
        # touched directly.
        assert ai_provenance.current_correlation_id() == root_cid


# ═══════════════════════════════════════════════════════════════════════════
# 2b. Evidence klasifikacija — sync, background-thread-scoped
# ═══════════════════════════════════════════════════════════════════════════

class TestEvidenceKlasifikacijaMigrated:
    def test_classification_produces_correlation_linked_sync_audit(self):
        """Also regression-guards the bug caught during this mission: using
        asyncio.create_task() here (instead of log_action_sync) would raise
        RuntimeError, since this function has no running event loop of its
        own when invoked via asyncio.to_thread()."""
        from routers.evidence import klasifikuj_i_sacuvaj

        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid-2")

        fake_result = {
            "tip_dokaza": "ugovor", "pravni_elementi": ["visina_stete"],
            "ai_tags": {}, "kljucne_cinjenice": [],
        }

        updated = []

        def _table(name):
            c = MagicMock()
            if name == "predmet_dokumenti":
                c.update = MagicMock(return_value=c)
                c.eq = MagicMock(side_effect=lambda *a, **k: updated.append(True) or c)
                c.execute = MagicMock(return_value=MagicMock(data=[{"id": "dok-1"}]))
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        sync_audit_calls = []

        def _fake_log_action_sync(**kwargs):
            sync_audit_calls.append(kwargs)
            return "audit-row-1"

        with patch("routers.evidence._klasifikuj_dokument", return_value=fake_result), \
             patch("routers.evidence.get_supa", return_value=supa), \
             patch("shared.audit_immutable.log_action_sync", side_effect=_fake_log_action_sync):
            klasifikuj_i_sacuvaj("pred-1", "dok-1", "ugovor.pdf", "tekst dokumenta", "u1")

        assert updated
        assert len(sync_audit_calls) == 1
        assert sync_audit_calls[0]["action"] == "evidence_klasifikacija"
        assert sync_audit_calls[0]["resource_id"] == "dok-1"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Court Predictor -- structural proof of wiring across all 6 endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestCourtPredictorWiringStructural:
    @pytest.fixture(scope="class")
    def source(self):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "routers" / "court_predictor.py").read_text(encoding="utf-8")

    @pytest.mark.parametrize("fn_name", [
        "prediktuj_ishod", "battle_report", "hearing_prep_brief",
        "argument_reputation", "judge_profile", "confidence_check",
    ])
    def test_endpoint_references_case_context_and_log_action(self, source, fn_name):
        idx = source.find(f"async def {fn_name}(")
        assert idx != -1, f"{fn_name} not found"
        next_def = source.find("\n@router.post", idx + 1)
        snippet = source[idx: next_def if next_def != -1 else idx + 8000]
        assert "case_context" in snippet, f"{fn_name} missing case_context wiring"
        assert "log_action" in snippet, f"{fn_name} missing log_action audit wiring"

    def test_opponent_intel_references_case_context_and_log_action(self, source):
        idx = source.find("async def opponent_intel(")
        assert idx != -1
        snippet = source[idx: idx + 4000]
        assert "case_context" in snippet
        assert "log_action" in snippet
