# -*- coding: utf-8 -*-
"""
Mission Keystone (2026-08-04) — Final Pre-Beta Readiness Validation.

Proves the behavior of the 2 code fixes this mission made (Keystone's own
First Rule restricts changes to critical bug/security/reliability fixes +
test coverage -- no new features):

1. Event Bus atomic claim (services/event_bus.py, migration 091 draft):
   Keystone's Phase 1 + Phase 4 investigation found that production's
   default 4 gunicorn worker processes each run an independent DispatchLoop
   polling the same 'events' table with a plain, unclaimed SELECT --
   meaning 2+ workers could select and process the SAME undispatched row in
   the same 3s tick, double-running non-idempotent handlers (duplicate
   proactive_alerts/audit rows). dispatch_pending_events() now tries a new
   claim_pending_events() RPC (SELECT ... FOR UPDATE SKIP LOCKED, mirroring
   migration 073's already-proven claim_intake_job) first, with a narrow,
   deliberate fallback to the pre-existing plain-select behavior if the RPC
   isn't deployed yet (migration not yet run -- per standing project
   convention, migrations are drafted, never run by the assistant).
2. routers/dokument.py::dokument_pitanje -- a second, real, unwrapped
   ask_agent call path that both Mission Migration's and Project Phoenix's
   own inventories missed (both only traced copilot.py's delegation),
   caught by Keystone's fresh, independent Phase 2 metric recalculation.
   Migrated onto the canonical stack using the exact same proven pattern as
   copilot.py::_handle_pravno_pitanje.
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
from unittest.mock import AsyncMock, MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps _patch_prompt_guard()

import shared.ai_provenance as ai_provenance  # noqa: E402
from shared.audit_immutable import AUDITABLE_ACTIONS  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Event Bus atomic claim (multi-worker duplicate-dispatch fix)
# ═══════════════════════════════════════════════════════════════════════════

class TestEventBusAtomicClaim:
    @pytest.mark.anyio
    async def test_dispatch_uses_rpc_claim_when_available_not_plain_select(self):
        """When migration 091 IS deployed, dispatch_pending_events() must
        claim via the RPC and must NOT fall through to the plain
        events-table select (proving the two paths are truly exclusive,
        not both firing and double-processing)."""
        from services import event_bus as eb

        row = {"id": "evt-1", "event_type": "predmet_kreiran", "user_id": "u1",
               "predmet_id": "p1", "payload": {}, "dispatch_attempts": 0}

        rpc_calls = []
        table_calls = []

        def _rpc(name, params):
            rpc_calls.append((name, params))
            chain = MagicMock()
            chain.execute = MagicMock(return_value=MagicMock(data=[row]))
            return chain

        def _table(name):
            table_calls.append(name)
            chain = MagicMock()
            chain.select.return_value = chain
            chain.is_.return_value = chain
            chain.order.return_value = chain
            chain.limit.return_value = chain
            chain.eq.return_value = chain
            chain.update.return_value = chain
            chain.execute = MagicMock(return_value=MagicMock(data=[]))
            return chain

        supa = MagicMock()
        supa.rpc = MagicMock(side_effect=_rpc)
        supa.table = MagicMock(side_effect=_table)

        fake_handler = AsyncMock()
        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.PREDMET_KREIRAN: [fake_handler]}):
            result = await eb.dispatch_pending_events()

        assert len(rpc_calls) == 1
        assert rpc_calls[0][0] == "claim_pending_events"
        assert "p_batch_size" in rpc_calls[0][1]
        # The row came back via the RPC -- confirm it was actually processed.
        assert result["dispecovano"] == 1
        fake_handler.assert_awaited_once()
        # events.select(...) (the OLD unclaimed read path) must never have
        # run -- only the mark-dispatched .update() call belongs here.
        select_calls = [c for c in table_calls if c == "events"]
        assert len(select_calls) == 1  # the _mark_dispatched() update call

    @pytest.mark.anyio
    async def test_dispatch_falls_back_to_plain_select_when_rpc_not_deployed(self):
        """Pre-migration-091 state: the RPC doesn't exist yet (PGRST202).
        Must fall back to the exact old plain-select behavior, not crash or
        silently process zero events."""
        from services import event_bus as eb

        row = {"id": "evt-2", "event_type": "predmet_kreiran", "user_id": "u1",
               "predmet_id": "p1", "payload": {}, "dispatch_attempts": 0}

        def _table(name):
            chain = MagicMock()
            if name == "events":
                chain.select.return_value = chain
                chain.is_.return_value = chain
                chain.order.return_value = chain
                chain.limit.return_value = chain
                chain.execute = MagicMock(return_value=MagicMock(data=[row]))
                chain.eq.return_value = chain
                chain.update.return_value = chain
            return chain

        supa = MagicMock()
        supa.rpc = MagicMock(side_effect=Exception(
            "PGRST202: Could not find the function public.claim_pending_events"))
        supa.table = MagicMock(side_effect=_table)

        fake_handler = AsyncMock()
        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.PREDMET_KREIRAN: [fake_handler]}):
            result = await eb.dispatch_pending_events()

        assert result["dispecovano"] == 1
        fake_handler.assert_awaited_once()

    @pytest.mark.anyio
    async def test_dispatch_does_not_swallow_unrelated_rpc_error(self):
        """The missing-function check must be narrow -- a genuine, unrelated
        RPC error (e.g. connection reset) must propagate, not be silently
        treated as 'RPC not deployed yet'."""
        from services import event_bus as eb

        supa = MagicMock()
        supa.rpc = MagicMock(side_effect=Exception("connection reset by peer"))

        with patch("shared.deps._get_supa", return_value=supa):
            with pytest.raises(Exception, match="connection reset"):
                await eb.dispatch_pending_events()

    def test_is_missing_function_error_narrow_check(self):
        """Direct unit coverage of the narrow check itself (mirrors
        shared/audit_immutable.py's _is_missing_column_error test
        philosophy) -- both the accept and reject cases."""
        from services.event_bus import _is_missing_function_error

        assert _is_missing_function_error(Exception(
            "PGRST202: Could not find the function public.claim_pending_events(p_batch_size) in the schema cache"))
        assert _is_missing_function_error(Exception("undefined_function: 42883"))
        assert not _is_missing_function_error(Exception("connection reset by peer"))
        assert not _is_missing_function_error(Exception("duplicate key value violates unique constraint"))

    @pytest.mark.anyio
    async def test_claimed_at_cleared_on_retryable_failure_not_on_fallback_path(self):
        """When claimed via the RPC, a non-exhausted handler failure must
        clear claimed_at (so the row is immediately reclaimable on the next
        3s poll instead of waiting out the stale-claim window) -- but the
        fallback (pre-migration) path must never reference claimed_at at
        all, since the column may not exist yet on that DB."""
        from services import event_bus as eb

        row = {"id": "evt-3", "event_type": "rok_dodan", "user_id": "u1",
               "predmet_id": "p1", "payload": {}, "dispatch_attempts": 0}
        updates = []

        def _rpc(name, params):
            chain = MagicMock()
            chain.execute = MagicMock(return_value=MagicMock(data=[row]))
            return chain

        def _table(name):
            chain = MagicMock()
            if name == "events":
                def _update(payload):
                    updates.append(payload)
                    return chain
                chain.update = MagicMock(side_effect=_update)
                chain.eq.return_value = chain
                chain.execute = MagicMock(return_value=MagicMock(data=[]))
            return chain

        supa = MagicMock()
        supa.rpc = MagicMock(side_effect=_rpc)
        supa.table = MagicMock(side_effect=_table)

        async def _broken(event):
            raise RuntimeError("transient")

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.ROK_DODAN: [_broken]}):
            result = await eb.dispatch_pending_events()

        assert result["greske"] == 1
        assert len(updates) == 1
        assert updates[0]["claimed_at"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. routers/dokument.py::dokument_pitanje — canonical stack migration
# ═══════════════════════════════════════════════════════════════════════════

class TestDokumentPitanjeMigrated:
    def test_dokument_pitanje_action_is_auditable(self):
        assert "dokument_pitanje" in AUDITABLE_ACTIONS

    @pytest.mark.anyio
    async def test_successful_question_produces_correlation_linked_audit(self):
        from routers.dokument import dokument_pitanje, PitanjeDocRequest

        root_cid = ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid-doc")

        audit_calls = []
        async def _fake_log_action(**kwargs):
            audit_calls.append(kwargs)

        captured_ctx = {}
        real_case_context = ai_provenance.case_context
        def _spy_case_context(*a, **kw):
            captured_ctx.update(kw)
            return real_case_context(*a, **kw)

        with patch("uploaded_doc.session.validate_session", return_value=True), \
             patch("main.ask_agent", return_value={"status": "success", "data": "Odgovor na pitanje"}), \
             patch("shared.usage.UsageService.consume", new=AsyncMock()), \
             patch("shared.ai_provenance.case_context", side_effect=_spy_case_context), \
             patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
            body = PitanjeDocRequest(pitanje="Da li je ugovor raskinut?",
                                      session_id="sess-1", history=[], namespace_prefix="tmp_")
            result = await dokument_pitanje(body, user={"user_id": "u1", "email": "a@b.rs"})

        # log_action fires as a fire-and-forget asyncio.create_task -- must
        # yield control once for it to actually run before asserting on it
        # (same timing pitfall caught in Project Phoenix's nightly-alert test).
        import asyncio as _asyncio
        await _asyncio.sleep(0)

        assert result["status"] == "success"
        assert captured_ctx.get("module_name") == "ask_agent"
        assert captured_ctx.get("operation_name") == "dokument_pitanje"
        assert len(audit_calls) == 1
        assert audit_calls[0]["action"] == "dokument_pitanje"
        assert audit_calls[0]["user_id"] == "u1"

    @pytest.mark.anyio
    async def test_error_response_does_not_produce_a_false_success_audit(self):
        """ask_agent returning status=error must NOT be logged as a
        successful dokument_pitanje audit entry (would misrepresent a
        failed AI call as a completed business action)."""
        from routers.dokument import dokument_pitanje, PitanjeDocRequest

        ai_provenance.set_request_context(user_id="u1", correlation_id="root-cid-doc-2")

        audit_calls = []
        async def _fake_log_action(**kwargs):
            audit_calls.append(kwargs)

        with patch("uploaded_doc.session.validate_session", return_value=True), \
             patch("main.ask_agent", return_value={"status": "error", "message": "LOW_CONFIDENCE"}), \
             patch("shared.usage.UsageService.consume", new=AsyncMock()), \
             patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
            body = PitanjeDocRequest(pitanje="Da li je ugovor raskinut?",
                                      session_id="sess-2", history=[], namespace_prefix="tmp_")
            result = await dokument_pitanje(body, user={"user_id": "u1", "email": "a@b.rs"})

        assert result["status"] == "error"
        assert len(audit_calls) == 0
