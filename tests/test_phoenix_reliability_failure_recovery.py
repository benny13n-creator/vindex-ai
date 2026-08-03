# -*- coding: utf-8 -*-
"""
Project Phoenix (2026-08-03) — Enterprise Reliability & Failure Recovery
Validation.

Every test here proves system BEHAVIOR UNDER A SIMULATED FAILURE, not just
line coverage — per the mission's own instruction: "Test mora dokazivati
ponašanje sistema pod kvarom."

Covers:
1. Event Bus retry mechanism -- the CRITICAL finding: `publish_async()`
   previously could not detect a handler failure at all (return_exceptions
   swallowed everything), so `dispatch_pending_events()`'s retry-tracking
   code was structurally unreachable. Proves it's now reachable, AND that a
   permanently-broken handler stops retrying (dead-letters) after
   MAX_DISPATCH_ATTEMPTS instead of retrying forever.
2. Nightly alert-insert retry + durable audit on exhaustion -- the other
   CRITICAL finding (silent data loss, debug-only log, zero retry).
3. The 3 normalized "try wide, fall back narrow" blocks -- proves a
   genuinely unrelated DB error propagates immediately (no wasted retry),
   while a missing-column error still falls back correctly.
4. `predmet_klijenti` TOCTOU race -- proves the losing request of a
   concurrent double-insert gets an honest "already linked" success
   message instead of a false-negative failure.
5. `routers/search.py` degraded-result signal -- proves a failed per-type
   sub-search is distinguishable from a genuine empty result.
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

from services import event_bus as eb  # noqa: E402
import shared.ai_provenance as ai_provenance  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_ai_provenance_context():
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Event Bus — retry mechanism can now actually detect handler failure
# ═══════════════════════════════════════════════════════════════════════════

class TestEventBusRetryDetection:
    @pytest.mark.anyio
    async def test_publish_async_raises_when_a_handler_fails(self):
        """The CRITICAL bug: asyncio.gather(..., return_exceptions=True)
        used to swallow every handler exception, so dispatch_pending_events'
        own except block (which tracks dispatch_attempts/last_error) was
        unreachable for handler-failure. This proves publish_async now
        surfaces the failure."""
        async def _broken_handler(event):
            raise RuntimeError("simulated handler bug")

        test_bus = eb.EventBus()
        test_bus._handlers[eb.EventType.ROK_DODAN] = [_broken_handler]
        event = eb.Event(type=eb.EventType.ROK_DODAN, user_id="u1")

        with pytest.raises(RuntimeError, match="simulated handler bug"):
            await test_bus.publish_async(event)

    @pytest.mark.anyio
    async def test_publish_async_still_runs_all_handlers_even_if_one_fails(self):
        """return_exceptions=True semantics must be preserved -- one broken
        handler must not prevent OTHER handlers (for the same event type)
        from running."""
        ran = {"good": False}

        async def _broken_handler(event):
            raise RuntimeError("boom")

        async def _good_handler(event):
            ran["good"] = True

        test_bus = eb.EventBus()
        test_bus._handlers[eb.EventType.ROK_DODAN] = [_broken_handler, _good_handler]
        event = eb.Event(type=eb.EventType.ROK_DODAN, user_id="u1")

        with pytest.raises(RuntimeError):
            await test_bus.publish_async(event)
        assert ran["good"] is True

    @pytest.mark.anyio
    async def test_dispatch_pending_events_does_not_mark_dispatched_on_handler_failure(self):
        """Proves the actual outbox consequence: a row whose handler fails
        must NOT get dispatched_at set (the old, broken behavior) until
        retries are exhausted -- it must remain retryable."""
        updates = []

        def _table(name):
            c = MagicMock()
            if name == "events":
                rows = [{
                    "id": "evt-1", "event_type": "rok_dodan", "user_id": "u1",
                    "predmet_id": None, "payload": {}, "dispatch_attempts": 0,
                }]
                r = MagicMock(); r.data = rows
                c.select.return_value = c
                c.is_.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=r)

                def _update(payload):
                    updates.append(payload)
                    return c
                c.update = MagicMock(side_effect=_update)
                c.eq.return_value = c
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        async def _broken_handler(event):
            raise RuntimeError("db unavailable")

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.ROK_DODAN: [_broken_handler]}):
            result = await eb.dispatch_pending_events()

        assert result["dispecovano"] == 0
        assert result["greske"] == 1
        assert result["dead_letter"] == 0
        # The only update issued must be the attempts/last_error tracking --
        # NOT a dispatched_at-setting update (that would be the old bug).
        assert len(updates) == 1
        assert "dispatched_at" not in updates[0]
        assert updates[0]["dispatch_attempts"] == 1

    @pytest.mark.anyio
    async def test_permanently_broken_handler_dead_letters_instead_of_retrying_forever(self):
        """Proves the fix to the SECOND half of the CRITICAL finding: once
        detection works, a permanently-failing handler must stop retrying
        after MAX_DISPATCH_ATTEMPTS (not retry forever every poll interval)
        -- and must be recorded as dead-lettered, not silently dropped."""
        updates = []

        def _table(name):
            c = MagicMock()
            if name == "events":
                rows = [{
                    "id": "evt-1", "event_type": "rok_dodan", "user_id": "u1",
                    "predmet_id": None, "payload": {},
                    "dispatch_attempts": eb.MAX_DISPATCH_ATTEMPTS - 1,
                    "correlation_id": "cid-1",
                }]
                r = MagicMock(); r.data = rows
                c.select.return_value = c
                c.is_.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=r)

                def _update(payload):
                    updates.append(payload)
                    return c
                c.update = MagicMock(side_effect=_update)
                c.eq.return_value = c
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        async def _broken_handler(event):
            raise RuntimeError("permanently broken")

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.ROK_DODAN: [_broken_handler]}):
            result = await eb.dispatch_pending_events()

        assert result["dead_letter"] == 1
        assert len(updates) == 1
        assert updates[0]["dispatched_at"] is not None  # stops the poller from retrying forever
        assert "DEAD_LETTER" in updates[0]["last_error"]

    @pytest.mark.anyio
    async def test_dispatch_pending_events_round_trips_correlation_id_on_success(self):
        """Regression guard: the fix must not disturb Mission Ledger's
        correlation_id round-trip for the SUCCESS path."""
        captured = {}

        def _table(name):
            c = MagicMock()
            if name == "events":
                rows = [{
                    "id": "evt-1", "event_type": "rok_dodan", "user_id": "u1",
                    "predmet_id": "p1", "payload": {}, "correlation_id": "cid-success",
                }]
                r = MagicMock(); r.data = rows
                c.select.return_value = c
                c.is_.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=r)
                c.update = MagicMock(return_value=c)
                c.eq.return_value = c
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        async def _ok_handler(event):
            captured["event"] = event

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.ROK_DODAN: [_ok_handler]}):
            result = await eb.dispatch_pending_events()

        assert result["dispecovano"] == 1
        assert captured["event"].correlation_id == "cid-success"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Nightly alert insert — retry + durable audit on exhaustion
# ═══════════════════════════════════════════════════════════════════════════

class TestNightlyAlertRetry:
    @pytest.mark.anyio
    async def test_alert_insert_succeeds_after_transient_failures(self):
        from routers.morning_briefing import nightly_intelligence_run

        attempts = {"n": 0}

        def _table(name):
            c = MagicMock()
            if name == "profiles":
                c.select.return_value = c
                c.not_.is_.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[{"id": "u1", "email": "a@b.rs"}]))
            elif name == "proactive_alerts":
                def _insert(rec):
                    attempts["n"] += 1
                    chain = MagicMock()
                    if attempts["n"] < 3:
                        chain.execute = MagicMock(side_effect=Exception("transient db hiccup"))
                    else:
                        chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "alert-1"}]))
                    return chain
                c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        fake_alert = {"tip": "rok_kritican", "naslov": "Test", "opis": "Test opis", "urgentnost": "hitna", "predmet_id": "p1"}

        with patch("routers.morning_briefing._get_supa", return_value=supa), \
             patch("routers.morning_briefing._generiši_alerts_za_korisnika", new=AsyncMock(return_value=[fake_alert])), \
             patch("routers.morning_briefing._ai_prioritizacija_alertova", new=AsyncMock(return_value="")), \
             patch.dict(os.environ, {"BRIEFING_CRON_SECRET": "secret"}), \
             patch("asyncio.sleep", new=AsyncMock()):
            from starlette.requests import Request as StarletteRequest
            scope = {"type": "http", "method": "POST", "path": "/api/briefing/cron",
                      "headers": [(b"x-cron-secret", b"secret")], "query_string": b"",
                      "app": MagicMock(), "state": MagicMock()}
            result = await nightly_intelligence_run(StarletteRequest(scope=scope))

        assert attempts["n"] == 3  # 2 failures + 1 success
        assert result["ok"] is not False

    @pytest.mark.anyio
    async def test_alert_insert_creates_durable_audit_entry_when_retries_exhausted(self):
        """The CRITICAL fix: a permanently-failing alert insert must no
        longer vanish with only a debug-level log -- it must produce a
        durable, queryable audit trail of the loss."""
        from routers.morning_briefing import nightly_intelligence_run

        audit_calls = []

        async def _fake_log_action(**kwargs):
            audit_calls.append(kwargs)

        def _table(name):
            c = MagicMock()
            if name == "profiles":
                c.select.return_value = c
                c.not_.is_.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[{"id": "u1", "email": "a@b.rs"}]))
            elif name == "proactive_alerts":
                chain = MagicMock()
                chain.execute = MagicMock(side_effect=Exception("permanent db outage"))
                c.insert = MagicMock(return_value=chain)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        fake_alert = {"tip": "rok_kritican", "naslov": "Kritican rok", "opis": "opis", "urgentnost": "hitna", "predmet_id": "p1"}

        with patch("routers.morning_briefing._get_supa", return_value=supa), \
             patch("routers.morning_briefing._generiši_alerts_za_korisnika", new=AsyncMock(return_value=[fake_alert])), \
             patch("routers.morning_briefing._ai_prioritizacija_alertova", new=AsyncMock(return_value="")), \
             patch("shared.audit_immutable.log_action", side_effect=_fake_log_action), \
             patch.dict(os.environ, {"BRIEFING_CRON_SECRET": "secret"}), \
             patch("asyncio.sleep", new=AsyncMock()):
            from starlette.requests import Request as StarletteRequest
            scope = {"type": "http", "method": "POST", "path": "/api/briefing/cron",
                      "headers": [(b"x-cron-secret", b"secret")], "query_string": b"",
                      "app": MagicMock(), "state": MagicMock()}
            await nightly_intelligence_run(StarletteRequest(scope=scope))

        # asyncio.sleep is mocked inside the `with` block above (needed so the
        # retry backoff doesn't actually wait) -- so the flush below must run
        # OUTSIDE it to get the real asyncio.sleep, otherwise this await never
        # actually yields to the event loop and the fire-and-forget audit task
        # (asyncio.create_task(log_action(...))) never gets a chance to run.
        import asyncio
        await asyncio.sleep(0)  # let the fire-and-forget audit task run

        assert len(audit_calls) == 1
        assert audit_calls[0]["action"] == "nightly_alert_insert_failed"
        assert audit_calls[0]["user_id"] == "u1"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Narrow "try wide, fall back narrow" fallback normalization (Finding P-1)
# ═══════════════════════════════════════════════════════════════════════════

class TestNarrowFallbackNormalization:
    @pytest.mark.anyio
    async def test_emit_genome_event_propagates_unrelated_error_without_wasted_retry(self):
        """Before this mission's fix, a bare `except Exception:` would
        blindly retry the insert WITHOUT correlation_id even for a
        completely unrelated error (e.g. connection reset) -- wasting an
        extra round-trip. Now only a genuine missing-column error triggers
        the fallback."""
        from routers.case_dna import _emit_genome_event

        attempts = []

        def _table(name):
            c = MagicMock()
            def _insert(rec):
                attempts.append(rec)
                chain = MagicMock()
                chain.execute = MagicMock(side_effect=Exception("connection reset by peer"))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        # The outer try/except in _emit_genome_event is fail-soft (never
        # raises) -- the proof is in attempt COUNT: exactly 1 (no wasted
        # narrow-fallback retry for an unrelated error).
        await _emit_genome_event(supa, predmet_id="p1", uid="u1", genome={"verzija": 1}, trigger="test")

        assert len(attempts) == 1

    @pytest.mark.anyio
    async def test_emit_genome_event_falls_back_on_genuine_missing_column_error(self):
        from routers.case_dna import _emit_genome_event

        attempts = []

        def _table(name):
            c = MagicMock()
            def _insert(rec):
                attempts.append(rec)
                chain = MagicMock()
                if "correlation_id" in rec:
                    chain.execute = MagicMock(side_effect=Exception('column "correlation_id" does not exist'))
                else:
                    chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "evt-1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        await _emit_genome_event(supa, predmet_id="p1", uid="u1", genome={"verzija": 1}, trigger="test")

        assert len(attempts) == 2  # wide attempt, then narrow fallback
        assert "correlation_id" not in attempts[1]


# ═══════════════════════════════════════════════════════════════════════════
# 4. predmet_klijenti TOCTOU race — honest "already linked" on the losing side
# ═══════════════════════════════════════════════════════════════════════════

class TestPredmetKlijentiRaceHandling:
    @pytest.mark.anyio
    async def test_duplicate_key_on_insert_returns_already_linked_not_generic_failure(self):
        from routers.copilot import _handle_akcija_povezi_klijenta

        fake_gpt_response = __import__("types").SimpleNamespace(
            choices=[__import__("types").SimpleNamespace(message=__import__("types").SimpleNamespace(
                content='{"ime_klijenta": "Petar Petrovic", "uloga": "stranka"}'
            ))]
        )

        def _table(name):
            c = MagicMock()
            if name == "klijenti":
                c.select.return_value = c
                c.eq.return_value = c
                c.or_.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=MagicMock(data=[{"id": "kl-1", "ime": "Petar", "prezime": "Petrovic", "firma": ""}]))
            elif name == "predmet_klijenti":
                c.select.return_value = c
                c.eq.return_value = c
                # Pre-check: not yet linked (the race window)
                c.execute = MagicMock(return_value=MagicMock(data=[]))
                c.insert = MagicMock(side_effect=Exception("duplicate key value violates unique constraint"))
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(return_value=fake_gpt_response)), \
             patch("routers.copilot._get_supa", return_value=supa):
            result = await _handle_akcija_povezi_klijenta("Poveži Petra Petrovica sa predmetom", "pred-1", "u1")

        # The losing request of the race must see an honest SUCCESS message,
        # not a false-negative failure -- the client link DID succeed
        # (via the winning concurrent request).
        assert result["uspeh"] is True
        assert "već vezan" in result["odgovor"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Search — a failed sub-search is no longer indistinguishable from "no results"
# ═══════════════════════════════════════════════════════════════════════════

def _search_request():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "GET", "path": "/api/search",
              "headers": [], "query_string": b"q=ugovor", "app": MagicMock(),
              "state": MagicMock(), "client": ("127.0.0.1", 12345)}
    return StarletteRequest(scope=scope)


class TestSearchDegradedSignal:
    @pytest.mark.anyio
    async def test_failed_subsearch_produces_nepotpuno_marker_not_silent_empty(self):
        from routers.search import global_search

        def _broken_search(supa, uid, q, limit):
            raise Exception("predmet_dokumenti table unavailable")

        with patch.dict("routers.search._SEARCHERS", {"dokumenti": _broken_search}, clear=False), \
             patch("routers.search._get_supa", return_value=MagicMock()):
            result = await global_search(
                request=_search_request(), q="ugovor", vrste="dokumenti",
                user={"user_id": "u1"},
            )

        assert result["dokumenti"] == []
        assert "nepotpuno" in result
        assert "dokumenti" in result["nepotpuno"]

    @pytest.mark.anyio
    async def test_genuine_empty_result_has_no_nepotpuno_marker(self):
        """Regression guard: a real, successful empty result must NOT be
        flagged as degraded."""
        from routers.search import global_search

        def _empty_search(supa, uid, q, limit):
            return []

        with patch.dict("routers.search._SEARCHERS", {"dokumenti": _empty_search}, clear=False), \
             patch("routers.search._get_supa", return_value=MagicMock()):
            result = await global_search(
                request=_search_request(), q="ugovor", vrste="dokumenti",
                user={"user_id": "u1"},
            )

        assert result["dokumenti"] == []
        assert "nepotpuno" not in result
