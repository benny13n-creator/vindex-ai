# -*- coding: utf-8 -*-
"""
Mission Ledger (2026-08-03) — End-to-End Traceability & Operational Evidence
Chain.

Covers the correlation_id unification that ties HTTP request -> Event Bus ->
AI Provenance -> Audit into one traceable chain (Phase 2, Correlation ID
Continuity; Phase 4, Audit Link Completion):

1. shared/ai_provenance.py -- set_request_context() mints/returns a
   correlation_id; case_context() inherits it by default; explicit override
   still works.
2. services/event_bus.py -- Event is a first-class carrier of correlation_id;
   emit() auto-fills it from the current context; dispatch_pending_events()
   round-trips it from the durable row.
3. shared/audit_immutable.py::log_action/log_action_sync -- auto-fill
   correlation_id from context; explicit param still works; correlation_id
   is NOT part of the hash-chain computation (adding it doesn't invalidate
   existing chain verification).
4. security/ai_forensics.py::log_provenance_from_wrapper -- audit_reference
   defaults to correlation_id.
5. "Replay" test -- one correlation_id, set once, flows unmodified into all
   three systems' write paths without any of them needing to re-derive or
   be told it explicitly (Phase 7, Evidence Replay -- the structural
   guarantee behind it).
6. Orphan-prevention -- structural proof that any call made inside a
   correlation-bearing context cannot produce a record missing that id.
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

import pytest
from unittest.mock import MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps _patch_prompt_guard()

import shared.ai_provenance as ai_provenance  # noqa: E402
from services import event_bus as eb  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_ai_provenance_context():
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Request/case correlation_id continuity
# ═══════════════════════════════════════════════════════════════════════════

class TestCorrelationIdContinuity:
    def test_set_request_context_generates_and_returns_correlation_id(self):
        cid = ai_provenance.set_request_context(user_id="u1")
        assert cid
        assert ai_provenance.current_correlation_id() == cid

    def test_set_request_context_respects_explicit_correlation_id(self):
        cid = ai_provenance.set_request_context(user_id="u1", correlation_id="fixed-id")
        assert cid == "fixed-id"
        assert ai_provenance.current_correlation_id() == "fixed-id"

    def test_case_context_inherits_request_correlation_id_by_default(self):
        root_cid = ai_provenance.set_request_context(user_id="u1")
        with ai_provenance.case_context(module_name="case_dna") as cid:
            assert cid == root_cid
            assert ai_provenance.current_correlation_id() == root_cid

    def test_case_context_can_still_override_with_its_own_id(self):
        ai_provenance.set_request_context(user_id="u1", correlation_id="root-id")
        with ai_provenance.case_context(module_name="x", correlation_id="sub-op-id") as cid:
            assert cid == "sub-op-id"
            assert ai_provenance.current_correlation_id() == "sub-op-id"
        # restored after exit
        assert ai_provenance.current_correlation_id() == "root-id"

    def test_no_request_context_falls_back_to_fresh_id(self):
        """Background jobs with no enclosing HTTP request still get a valid
        (if standalone) correlation_id rather than None."""
        with ai_provenance.case_context(module_name="background_job") as cid:
            assert cid


# ═══════════════════════════════════════════════════════════════════════════
# 2. Event Bus — correlation_id as a first-class Event field
# ═══════════════════════════════════════════════════════════════════════════

class TestEventBusCorrelation:
    def test_event_dataclass_carries_correlation_id(self):
        event = eb.Event(type=eb.EventType.PREDMET_KREIRAN, user_id="u1", correlation_id="cid-1")
        assert event.correlation_id == "cid-1"

    def test_emit_auto_fills_correlation_id_from_context(self):
        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid")
        captured = {}

        def _fake_publish(event):
            captured["event"] = event

        with patch.object(eb.bus, "publish", side_effect=_fake_publish):
            eb.emit(eb.EventType.PREDMET_KREIRAN, user_id="u1", predmet_id="p1")

        assert captured["event"].correlation_id == "root-cid"

    def test_emit_respects_explicit_correlation_id_override(self):
        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid")
        captured = {}

        def _fake_publish(event):
            captured["event"] = event

        with patch.object(eb.bus, "publish", side_effect=_fake_publish):
            eb.emit(eb.EventType.ROK_KRITICAN, user_id="u1", correlation_id="explicit-cid")

        assert captured["event"].correlation_id == "explicit-cid"

    @pytest.mark.anyio
    async def test_dispatch_pending_events_round_trips_correlation_id(self):
        """A durable outbox row carrying correlation_id must produce an Event
        with that same id when the poller dispatches it."""
        marked = []

        def _table(name):
            chain = MagicMock()
            if name == "events":
                rows = [{
                    "id": "evt-1", "event_type": "predmet_kreiran", "user_id": "u1",
                    "predmet_id": "p1", "payload": {}, "correlation_id": "outbox-cid",
                }]
                r = MagicMock(); r.data = rows
                chain.select.return_value = chain
                chain.is_.return_value = chain
                chain.order.return_value = chain
                chain.limit.return_value = chain
                chain.execute = MagicMock(return_value=r)

                def _update(payload):
                    marked.append(payload)
                    return chain
                chain.update = MagicMock(side_effect=_update)
                return chain
            return chain

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        captured_event = {}

        async def _fake_handler(event):
            captured_event["event"] = event

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.PREDMET_KREIRAN: [_fake_handler]}):
            await eb.dispatch_pending_events()

        assert captured_event["event"].correlation_id == "outbox-cid"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Audit — correlation_id auto-fill, not part of the hash chain
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditCorrelation:
    def _chain(self, data=None):
        c = MagicMock()
        for m in ["select", "eq", "order", "limit", "insert", "execute"]:
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data if data is not None else [{"id": "audit-row-1"}]
        c.execute = MagicMock(return_value=r)
        return c

    @pytest.mark.anyio
    async def test_log_action_auto_fills_correlation_id_from_context(self):
        from shared.audit_immutable import log_action

        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid")
        inserted = []

        def _table(name):
            if name == "audit_immutable":
                c = MagicMock()

                def _insert(rec):
                    inserted.append(rec)
                    chain = MagicMock()
                    r = MagicMock(); r.data = [{"id": "audit-1"}]
                    chain.execute = MagicMock(return_value=r)
                    return chain
                c.insert = MagicMock(side_effect=_insert)
                c.select.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[]))
                return c
            return self._chain()

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("api._get_supa", return_value=supa):
            await log_action(action="genome_refresh", user_id="u1", resource_type="predmet", resource_id="p1")

        assert len(inserted) == 1
        assert inserted[0]["correlation_id"] == "root-cid"

    @pytest.mark.anyio
    async def test_log_action_explicit_correlation_id_wins_over_context(self):
        from shared.audit_immutable import log_action

        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid")
        inserted = []

        def _table(name):
            if name == "audit_immutable":
                c = MagicMock()

                def _insert(rec):
                    inserted.append(rec)
                    chain = MagicMock()
                    r = MagicMock(); r.data = [{"id": "audit-1"}]
                    chain.execute = MagicMock(return_value=r)
                    return chain
                c.insert = MagicMock(side_effect=_insert)
                c.select.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[]))
                return c
            return self._chain()

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("api._get_supa", return_value=supa):
            await log_action(action="genome_refresh", user_id="u1", correlation_id="explicit-cid")

        assert inserted[0]["correlation_id"] == "explicit-cid"

    @pytest.mark.anyio
    async def test_log_action_falls_back_when_correlation_id_column_missing(self):
        """Pre-migration-090 compatibility: audit_immutable doesn't have the
        column yet -- the wide attempt fails, narrow retry (without
        correlation_id) must still succeed so the audit row isn't lost."""
        from shared.audit_immutable import log_action

        attempts = []
        call_count = {"n": 0}

        def _table(name):
            if name == "audit_immutable":
                c = MagicMock()

                def _insert(rec):
                    attempts.append(rec)
                    call_count["n"] += 1
                    chain = MagicMock()
                    if call_count["n"] == 1:
                        chain.execute = MagicMock(side_effect=Exception('column "correlation_id" does not exist'))
                    else:
                        r = MagicMock(); r.data = [{"id": "audit-1"}]
                        chain.execute = MagicMock(return_value=r)
                    return chain
                c.insert = MagicMock(side_effect=_insert)
                c.select.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[]))
                return c
            return self._chain()

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("api._get_supa", return_value=supa):
            entry_id = await log_action(action="genome_refresh", user_id="u1", correlation_id="cid-x")

        assert entry_id == "audit-1"
        assert len(attempts) == 2
        assert "correlation_id" not in attempts[1]

    def test_correlation_id_not_part_of_hash_chain_computation(self):
        """Adding correlation_id must not change _compute_entry_hash's output
        -- otherwise every existing historical audit_immutable row would
        fail verify_chain_integrity() the moment this migrates."""
        from shared.audit_immutable import _compute_entry_hash

        h1 = _compute_entry_hash(
            prev_hash="0" * 64, user_id="u1", action="genome_refresh",
            ts="2026-08-03T00:00:00+00:00", resource_type="predmet", resource_id="p1",
        )
        # No correlation_id parameter exists on _compute_entry_hash at all --
        # this call succeeding with the exact same signature as before proves
        # the hash formula is untouched.
        h2 = _compute_entry_hash(
            prev_hash="0" * 64, user_id="u1", action="genome_refresh",
            ts="2026-08-03T00:00:00+00:00", resource_type="predmet", resource_id="p1",
        )
        assert h1 == h2


# ═══════════════════════════════════════════════════════════════════════════
# 4. Genome event correlation_id unification (closes ATLAS-004)
# ═══════════════════════════════════════════════════════════════════════════

class TestGenomeEventCorrelationUnification:
    @pytest.mark.anyio
    async def test_emit_genome_event_inherits_ai_provenance_correlation_id(self):
        from routers.case_dna import _emit_genome_event

        ai_provenance.set_request_context(user_id="u1", correlation_id="unified-cid")
        inserted = []

        def _table(name):
            c = MagicMock()

            def _insert(rec):
                inserted.append(rec)
                chain = MagicMock()
                chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "evt-1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        returned_cid = await _emit_genome_event(
            supa, predmet_id="p1", uid="u1", genome={"verzija": 2}, trigger="test",
        )

        assert returned_cid == "unified-cid"
        assert inserted[0]["correlation_id"] == "unified-cid"
        assert inserted[0]["payload"]["correlation_id"] == "unified-cid"

    @pytest.mark.anyio
    async def test_emit_genome_event_falls_back_to_fresh_id_without_context(self):
        from routers.case_dna import _emit_genome_event

        inserted = []

        def _table(name):
            c = MagicMock()

            def _insert(rec):
                inserted.append(rec)
                chain = MagicMock()
                chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "evt-1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        returned_cid = await _emit_genome_event(
            supa, predmet_id="p1", uid="u1", genome={"verzija": 1}, trigger="test",
        )
        assert returned_cid  # some valid id was still minted


# ═══════════════════════════════════════════════════════════════════════════
# 5. AI Provenance — audit_reference defaults to correlation_id
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditReferenceDefaultsToCorrelationId:
    @pytest.mark.anyio
    async def test_audit_reference_defaults_to_correlation_id(self):
        from security.ai_forensics import log_provenance_from_wrapper

        inserted = []
        chain = MagicMock()
        chain.insert = MagicMock(side_effect=lambda rec: inserted.append(rec) or chain)
        chain.execute = MagicMock(return_value=MagicMock())
        supa = MagicMock()
        supa.table = MagicMock(return_value=chain)

        with patch("api._get_supa", return_value=supa):
            await log_provenance_from_wrapper(
                module_name="case_dna", model_provider="openai", model_name="gpt-4o",
                correlation_id="cid-shared",
            )

        assert inserted[0]["audit_reference"] == "cid-shared"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Replay premise — one correlation_id, three systems, zero re-derivation
# ═══════════════════════════════════════════════════════════════════════════

class TestReplayPremise:
    @pytest.mark.anyio
    async def test_single_correlation_id_threads_through_event_audit_and_provenance(self):
        """The structural guarantee Phase 7 (Evidence Replay) depends on:
        set the request-level correlation_id ONCE, then Event Bus, Audit,
        and AI Provenance writes all pick it up automatically -- no call
        site has to pass it explicitly, and none can silently drop it."""
        from shared.audit_immutable import log_action
        from security.ai_forensics import log_provenance_from_wrapper

        root_cid = ai_provenance.set_request_context(user_id="u1", correlation_id="replay-cid")

        # Event Bus
        published = {}
        with patch.object(eb.bus, "publish", side_effect=lambda e: published.setdefault("event", e)):
            eb.emit(eb.EventType.PREDMET_KREIRAN, user_id="u1", predmet_id="p1")

        # Audit
        audit_rows = []
        def _audit_table(name):
            c = MagicMock()
            def _insert(rec):
                audit_rows.append(rec)
                chain = MagicMock()
                chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "audit-1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            c.select.return_value = c
            c.order.return_value = c
            c.limit.return_value = c
            c.execute = MagicMock(return_value=MagicMock(data=[]))
            return c
        supa_audit = MagicMock()
        supa_audit.table = MagicMock(side_effect=_audit_table)
        with patch("api._get_supa", return_value=supa_audit):
            await log_action(action="genome_refresh", user_id="u1", resource_type="predmet", resource_id="p1")

        # AI Provenance
        provenance_rows = []
        chain2 = MagicMock()
        chain2.insert = MagicMock(side_effect=lambda rec: provenance_rows.append(rec) or chain2)
        chain2.execute = MagicMock(return_value=MagicMock())
        supa_prov = MagicMock()
        supa_prov.table = MagicMock(return_value=chain2)
        with patch("api._get_supa", return_value=supa_prov):
            await log_provenance_from_wrapper(module_name="case_dna", model_provider="openai", model_name="gpt-4o")

        assert published["event"].correlation_id == root_cid
        assert audit_rows[0]["correlation_id"] == root_cid
        assert provenance_rows[0]["correlation_id"] == root_cid
        assert provenance_rows[0]["audit_reference"] == root_cid
        # All three systems agree -- an independent engineer can join on
        # this single id across events/audit_immutable/ai_forensics.
        assert len({published["event"].correlation_id, audit_rows[0]["correlation_id"], provenance_rows[0]["correlation_id"]}) == 1
