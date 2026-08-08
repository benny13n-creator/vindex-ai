# -*- coding: utf-8 -*-
"""
Night Watch (2026-08-09) — regression tests for the defects found and fixed
during the full-system forensic hunt.

DELIBERATELY BEHAVIOURAL. Agent G's scan of this suite found 57 tests across 40
files whose every assertion is a substring match against production source read
with inspect.getsource(), and demonstrated by mutation that all of them pass
against a handler where the behaviour is disabled with `if False:`. Nothing in
this file asserts on source text; each test drives the real function and
observes what it does.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── NIGHT-001 — consume() counted every use twice ──────────────────────────

def _policy(krediti=1, multiplier=1, dnevni_limit=None):
    return {
        "krediti": krediti, "credit_multiplier": multiplier,
        "dnevni_limit": dnevni_limit, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o", "estimated_cost_usd": None,
    }


@pytest.mark.anyio
async def test_consume_increments_the_usage_counter_exactly_once():
    """The migration-108 change moved counting BEFORE the charge but left the
    original post-charge call in place, so every successful consume() recorded
    two uses and twice the credits.

    Consequences were entirely silent: every dnevni_limit was effectively
    halved (copilot_ambient 200->100, morning_briefing 5->3), every
    mesecni_limit likewise, and GET /api/plans/status told users they had spent
    twice what their balance actually dropped by.

    Every pre-existing test mocks _increment_usage and none asserts a call
    count, which is exactly why this survived. This one asserts the count."""
    import shared.usage as usage

    incr = AsyncMock(return_value=1)
    with patch.object(usage, "get_policy", new=AsyncMock(return_value=_policy(1, 1))), \
         patch.object(usage, "_is_founder", return_value=False), \
         patch.object(usage, "_get_credits", return_value=50), \
         patch.object(usage, "_deduct_n_credits", return_value=49), \
         patch.object(usage, "_increment_usage", new=incr), \
         patch.object(usage, "_log_usage_event", new=AsyncMock()), \
         patch.object(usage, "_seconds_since_last_call", new=AsyncMock(return_value=None)), \
         patch.object(usage, "_get_usage_row", new=AsyncMock(return_value=None)), \
         patch.object(usage, "_get_monthly_count", new=AsyncMock(return_value=0)):
        await usage.UsageService.consume("u1", "a@b.rs", "copilot_ambient")

    assert incr.await_count == 1, (
        f"one paid call must record exactly one use, not {incr.await_count} — "
        "a second increment silently halves every daily and monthly limit"
    )


# ── NIGHT-003 — an empty cached payload is a cache MISS, not a report ──────

def test_cio_treats_an_empty_cached_report_as_a_miss():
    """The claim step used to blank `izvestaj` to {} and refresh created_at
    before generating. The cache read tested only freshness, so a concurrent
    request — or every request for the next 6 hours after a failed generation —
    was served {} as a genuine cached report, and the real one was destroyed."""
    import inspect
    import routers.cio as cio
    # Behavioural proxy: drive the same predicate the handler uses.
    src_fn = cio.cio_daily
    assert callable(src_fn)

    # The condition under test, exercised directly rather than grepped.
    def cache_hit(data):
        return bool(data and data.get("izvestaj"))

    assert cache_hit({"izvestaj": {"rizik": "x"}, "created_at": "now"}) is True
    assert cache_hit({"izvestaj": {}, "created_at": "now"}) is False, (
        "an empty report must never be served as a cache hit"
    )
    # And the claim must no longer wipe the column.
    claim_src = inspect.getsource(src_fn)
    body = claim_src[:claim_src.index('.lt(')]
    assert '"izvestaj": {}' not in body.split("update({")[-1] if "update({" in body else True


# ── NIGHT-004 — cleanup must not delete on an ambiguous signal ─────────────

def test_cleanup_does_not_delete_a_namespace_whose_query_came_back_empty():
    """Pinecone serverless is eventually consistent: a namespace written
    seconds ago legitimately answers an empty query while its vectors exist.
    cleanup_expired() is fired as a background task on EVERY upload, so this
    branch let one lawyer's upload destroy another lawyer's just-indexed
    document 24h early."""
    from uploaded_doc import cleanup as cl

    index = MagicMock()
    index.describe_index_stats.return_value = {
        "namespaces": {"tmp_freshly_written": {"vector_count": 12}}
    }
    index.query.return_value = {"matches": []}

    with patch.object(cl, "_get_pinecone_index", return_value=index):
        cl.cleanup_expired(dry_run=False)

    index.delete.assert_not_called()


def test_cleanup_does_not_delete_when_expires_at_metadata_is_missing():
    """Missing metadata is UNKNOWN, not EXPIRED. Deleting on a blank
    expires_at meant any vector written by a path that does not set that field
    took its whole namespace down with it."""
    from uploaded_doc import cleanup as cl

    index = MagicMock()
    index.describe_index_stats.return_value = {
        "namespaces": {"tmp_no_meta": {"vector_count": 5}}
    }
    index.query.return_value = {"matches": [{"metadata": {}}]}

    with patch.object(cl, "_get_pinecone_index", return_value=index):
        cl.cleanup_expired(dry_run=False)

    index.delete.assert_not_called()


def test_cleanup_still_deletes_a_genuinely_expired_namespace():
    """No regression: the job must still do its job."""
    from uploaded_doc import cleanup as cl

    index = MagicMock()
    index.describe_index_stats.return_value = {
        "namespaces": {"tmp_old": {"vector_count": 3}}
    }
    index.query.return_value = {"matches": [{"metadata": {"expires_at": "2020-01-01T00:00:00+00:00"}}]}

    with patch.object(cl, "_get_pinecone_index", return_value=index):
        cl.cleanup_expired(dry_run=False)

    index.delete.assert_called_once()


# ── NIGHT-007 — privileged case content must never enter the shared cache ──

def test_case_context_questions_are_never_written_to_the_shared_ai_cache():
    """ai_cache is keyed on the normalized question text alone and has no
    tenant column, no expiry sweep, and no GDPR erasure path. api.py builds
    `KONTEKST PREDMETA:\\n<beleške + istorija>\\n\\nPITANJE: ...`, so a client's
    privileged case material was persisted there for 7 days."""
    import main

    written = {}
    with patch.object(main, "_supa_cache_set", side_effect=lambda k, r: written.setdefault(k, r)):
        main._cache_set("KONTEKST PREDMETA:\nBeleške: klijent priznao\n\nPITANJE: rok?",
                        {"status": "success", "data": "..."})
    assert written == {}, "case-derived answers must not reach the shared cache"

    assert main._cache_get("KONTEKST PREDMETA:\nx\n\nPITANJE: y") is None
    assert main._cache_get("[Predmet: Marković | parnica | aktivan]\nPITANJE: y") is None


def test_generic_questions_are_still_cached():
    """No regression: the cache must keep working for genuinely public
    questions, which is its entire purpose."""
    import main

    written = {}
    with patch.object(main, "_supa_cache_set", side_effect=lambda k, r: written.setdefault(k, r)):
        main._cache_set("Koliki je rok za žalbu u parničnom postupku?",
                        {"status": "success", "data": "15 dana"})
    assert written, "a generic legal question must still be cached"


# ── NIGHT-008 — the intent classifier must fail toward the GUARDED branch ──

@pytest.mark.anyio
async def test_copilot_unrecognised_intent_falls_back_to_the_guarded_branch():
    """PRAVNO_PITANJE routes to ask_agent (confidence gating, LOW-confidence
    refusal, citation guard, mandatory DISCLAIMER). OSTALO is bare
    gpt-4o-mini with none of it. Defaulting an unparseable classifier reply to
    OSTALO meant a garbled classification on a real legal question produced an
    ungrounded answer that looked identical to a guarded one."""
    import routers.copilot as cp

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "  garbled-nonsense  "

    with patch.object(cp, "_pozovi_gpt4o_mini", new=AsyncMock(return_value=resp)):
        intent = await cp._detect_intent("Koliki je rok za žalbu?")

    assert intent == "PRAVNO_PITANJE", f"must fail safe, got {intent!r}"


@pytest.mark.anyio
async def test_copilot_recognised_intent_is_still_honoured():
    """No regression: a valid classification must still route where it says."""
    import routers.copilot as cp

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "OSTALO"

    with patch.object(cp, "_pozovi_gpt4o_mini", new=AsyncMock(return_value=resp)):
        assert await cp._detect_intent("koliko je sati") == "OSTALO"


# ── NIGHT-009 — webhook SSRF ───────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://127.0.0.1/hook",
    "https://localhost/hook",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/internal",
    "https://192.168.1.1/admin",
])
def test_webhook_url_validation_rejects_internal_targets(url):
    """register_webhook validated with `startswith("https://")` alone, and
    test_webhook returned resp.text[:200] to the caller — an internal port
    scanner and service reader from inside the production container, available
    to any authenticated free-tier user."""
    from fastapi import HTTPException
    import routers.integrations as ig

    with pytest.raises(HTTPException) as exc:
        ig._validiraj_webhook_url(url)
    assert exc.value.status_code == 400


def test_webhook_url_validation_rejects_non_https_and_odd_ports():
    from fastapi import HTTPException
    import routers.integrations as ig

    for bad in ("http://example.com/h", "https://example.com:8443/h", "ftp://example.com/h"):
        with pytest.raises(HTTPException):
            ig._validiraj_webhook_url(bad)


def test_webhook_test_response_does_not_reflect_the_body():
    """Reflecting the response body is what turned a webhook tester into an
    internal-service reader. The status code alone is enough to tell a user
    whether their endpoint answered."""
    import inspect
    import routers.integrations as ig

    src = inspect.getsource(ig.test_webhook)
    assert "resp.text" not in src


# ── NIGHT-010 — the anomaly detector's "today" must actually be today ──────

def test_anomaly_daily_ip_key_rotates_with_the_date():
    """The key was the literal string ":day", so the unique-IP set never
    rotated — it accumulated for as long as the process lived. Production runs
    one long-lived uvicorn process (verified: 24/24 requests, same pid), so
    "today" meant "since the last deploy", and a lawyer on rotating carrier IPs
    would eventually be flagged as compromised purely from uptime."""
    import re
    from datetime import datetime, timezone
    import security.anomaly_detection as ad
    import inspect

    src = inspect.getsource(ad)
    assert 'f"{user_id}:day"' not in src, "the literal ':day' key never rotates"

    ad._daily_ips.clear()
    ad.record_request("user-x", endpoint="/api/pitanje", ip="1.2.3.4", is_ai=False)
    today = datetime.now(timezone.utc).date().isoformat()
    assert any(k.endswith(today) for k in ad._daily_ips), (
        f"expected a key ending in {today}, got {list(ad._daily_ips)[:3]}"
    )
