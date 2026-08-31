# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 012 -- Document/Event Duplication & Race Gaps.
Closes LIVINGSYS-DEBT-012 (TOCTOU sub-item), -021, -045, -046.
LIVINGSYS-DEBT-020 explicitly NOT touched -- blocked on a product decision
(silently skip vs. surface "looks like a duplicate" to the lawyer), named as
such in the debt register; not this coordinator's call to make unilaterally.
LIVINGSYS-DEBT-042 explicitly NOT touched -- the register's own assessment is
that it needs new cron infrastructure and its own design pass, not a bounded
mechanical fix.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "POST", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope, receive=receive)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-012 (TOCTOU sub-item) -- UsageService.consume() read "seconds
# since last call" before the corresponding write committed; two concurrent
# requests could both see the cooldown satisfied and both proceed.
# ═══════════════════════════════════════════════════════════════════════════

def _stateful_feature_usage_supa():
    """Fake `feature_usage` table enforcing UNIQUE(user_id, feature_key, dan)
    and actually evaluating .lt("updated_at", cutoff) against mutable state."""
    rows: dict = {}

    class _Builder:
        def __init__(self, kind, payload=None):
            self.kind = kind
            self.payload = payload
            self.filters = {}
            self.lt_filters = {}

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def lt(self, col, val):
            self.lt_filters[col] = val
            return self

        def maybe_single(self):
            return self

        def execute(self):
            res = MagicMock()
            key = (self.filters.get("user_id"), self.filters.get("feature_key"), self.filters.get("dan"))
            if self.kind == "select":
                row = rows.get(key)
                res.data = dict(row) if row else None
                return res
            if self.kind == "insert":
                ins_key = (self.payload["user_id"], self.payload["feature_key"], self.payload["dan"])
                if ins_key in rows:
                    raise Exception('duplicate key value violates unique constraint "feature_usage_user_id_feature_key_dan_key"')
                row = dict(self.payload)
                row.setdefault("updated_at", __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc).isoformat())  # simulates DB's DEFAULT now()
                row["id"] = f"row-{len(rows) + 1}"
                rows[ins_key] = row
                res.data = [row]
                return res
            if self.kind == "update":
                row = rows.get(key)
                matched = row is not None and all(
                    row.get(k, "") < v for k, v in self.lt_filters.items()
                )
                if matched:
                    rows[key].update(self.payload)
                    res.data = [rows[key]]
                else:
                    res.data = []
                return res
            res.data = None
            return res

    def _table(name):
        assert name == "feature_usage"
        t = MagicMock()
        t.select.side_effect = lambda *a, **k: _Builder("select")
        t.insert.side_effect = lambda payload: _Builder("insert", payload)
        t.update.side_effect = lambda payload: _Builder("update", payload)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, rows


@pytest.mark.anyio
async def test_cooldown_claim_first_call_of_day_succeeds():
    import shared.usage as usage

    supa, _rows = _stateful_feature_usage_supa()
    with patch.object(usage, "_get_supa", return_value=supa):
        claimed = await usage._claim_cooldown_atomic("u1", "voice", 3)

    assert claimed is True


@pytest.mark.anyio
async def test_cooldown_claim_concurrent_calls_only_one_wins():
    """Original-scenario reproduction: two calls for the same user+feature
    within the cooldown window -- only ONE may proceed."""
    import shared.usage as usage

    supa, _rows = _stateful_feature_usage_supa()
    with patch.object(usage, "_get_supa", return_value=supa):
        first = await usage._claim_cooldown_atomic("u1", "voice", 3)
        second = await usage._claim_cooldown_atomic("u1", "voice", 3)

    assert first is True
    assert second is False


@pytest.mark.anyio
async def test_cooldown_claim_succeeds_again_after_window_elapses():
    """Regression: a genuinely later call (cooldown window elapsed) must still
    be able to claim -- this isn't a permanent lock."""
    import shared.usage as usage

    supa, rows = _stateful_feature_usage_supa()
    with patch.object(usage, "_get_supa", return_value=supa):
        assert await usage._claim_cooldown_atomic("u1", "voice", 3) is True
        # Simulate the window having elapsed: back-date the stored updated_at.
        for row in rows.values():
            row["updated_at"] = "1970-01-01T00:00:00+00:00"
        assert await usage._claim_cooldown_atomic("u1", "voice", 3) is True


@pytest.mark.anyio
async def test_consume_raises_429_when_cooldown_claim_fails():
    from shared.usage import UsageService

    policy = {
        "krediti": 0, "credit_multiplier": 1, "dnevni_limit": None,
        "mesecni_limit": None, "cooldown_seconds": 5,
        "ai_model": "gpt-4o", "estimated_cost_usd": None,
    }
    from fastapi import HTTPException

    with patch("shared.usage.get_policy", new=AsyncMock(return_value=policy)), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._claim_cooldown_atomic", new=AsyncMock(return_value=False)), \
         patch("shared.usage._seconds_since_last_call", new=AsyncMock(return_value=2.0)):
        with pytest.raises(HTTPException) as exc:
            await UsageService.consume("u1", "a@b.com", "voice")

    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "COOLDOWN"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-021 -- unvalidated GPT chronology extraction fed directly
# into the deadline-notification system; a single malformed date dropped the
# entire batch (one bulk insert).
# ═══════════════════════════════════════════════════════════════════════════

def test_validate_hronologija_datum_iso_accepts_valid_date():
    from api import _validate_hronologija_datum_iso

    assert _validate_hronologija_datum_iso("2026-08-08", "p1") == "2026-08-08"


def test_validate_hronologija_datum_iso_rejects_hallucinated_date():
    """Original-scenario reproduction: a syntactically date-shaped but
    semantically invalid value (month 13) must be dropped, not reach the DB."""
    from api import _validate_hronologija_datum_iso

    assert _validate_hronologija_datum_iso("2026-13-45", "p1") is None


def test_validate_hronologija_datum_iso_handles_none_and_placeholders():
    from api import _validate_hronologija_datum_iso

    assert _validate_hronologija_datum_iso(None, "p1") is None
    assert _validate_hronologija_datum_iso("null", "p1") is None
    assert _validate_hronologija_datum_iso("", "p1") is None


def test_insert_hronologija_rows_persists_valid_rows_despite_one_bad_row():
    """Original-scenario reproduction: one row's DB-level failure must not
    drop its siblings (was one bulk .insert(rows) call, rejected atomically)."""
    from api import _insert_hronologija_rows

    def _table(name):
        t = MagicMock()
        def _insert(row):
            if row["dogadjaj"] == "BAD ROW":
                raise Exception("invalid input syntax for type date")
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[{"id": "h1"}])
            return m
        t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    rows = [
        {"dogadjaj": "Dobar dogadjaj 1", "predmet_id": "p1"},
        {"dogadjaj": "BAD ROW", "predmet_id": "p1"},
        {"dogadjaj": "Dobar dogadjaj 2", "predmet_id": "p1"},
    ]

    with patch("api._get_supa", return_value=supa):
        count = _insert_hronologija_rows(rows, "p1")

    assert count == 2


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-045 -- Genome's coalescing guard had a false-failure blind
# spot: a coalesced caller returned before the in-flight rerun actually
# finished, so its own before/after verzija verification could misreport a
# genuinely-in-progress refresh as failed.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_coalesced_caller_waits_for_inflight_run_to_complete():
    """Original-scenario reproduction: 2 concurrent triggers for the same
    predmet_id -- the 2nd (coalesced) caller's own await must not return until
    the in-flight run's rerun loop has actually finished."""
    import routers.case_dna as cd

    cd._genome_refresh_inflight.clear()
    cd._genome_refresh_rerun.clear()
    cd._genome_refresh_done_event.clear()

    completion_order = []

    async def _fake_do_refresh(predmet_id, uid, stari_procent, trigger, event_id=None):
        await asyncio.sleep(0.05)
        completion_order.append("refresh_done")

    with patch.object(cd, "_do_genome_refresh", new=_fake_do_refresh):
        async def _caller_a():
            await cd._run_genome_background("p1", "u1")
            completion_order.append("caller_a_returned")

        async def _caller_b():
            await asyncio.sleep(0.01)  # ensure B arrives while A is in-flight
            await cd._run_genome_background("p1", "u1")
            completion_order.append("caller_b_returned")

        await asyncio.gather(_caller_a(), _caller_b())

    # Both callers must only return AFTER the refresh work actually completed --
    # "caller_b_returned" must never appear before "refresh_done".
    assert completion_order.index("caller_b_returned") > completion_order.index("refresh_done")


@pytest.mark.anyio
async def test_genome_refresh_inflight_state_fully_cleaned_up_after_coalesce():
    """Regression: after both callers finish, no leaked state should remain
    (would silently break the NEXT trigger for this predmet_id)."""
    import routers.case_dna as cd

    cd._genome_refresh_inflight.clear()
    cd._genome_refresh_rerun.clear()
    cd._genome_refresh_done_event.clear()

    async def _fake_do_refresh(predmet_id, uid, stari_procent, trigger, event_id=None):
        await asyncio.sleep(0.01)

    with patch.object(cd, "_do_genome_refresh", new=_fake_do_refresh):
        await asyncio.gather(
            cd._run_genome_background("p1", "u1"),
            cd._run_genome_background("p1", "u1"),
        )

    assert "p1" not in cd._genome_refresh_inflight
    assert "p1" not in cd._genome_refresh_rerun
    assert "p1" not in cd._genome_refresh_done_event


@pytest.mark.anyio
async def test_coalesced_caller_falls_back_after_timeout_instead_of_hanging_forever():
    """Guards against the exact regression this mission's own full-suite run
    surfaced: an earlier version of this fix made a coalesced caller wait
    UNBOUNDED on the in-flight run's completion -- a single hung/slow
    underlying call then hung every OTHER concurrent trigger for the same
    case too, a strictly worse failure mode than the one being fixed. The
    wait must be bounded and fall back to returning (pre-mission behavior)
    on timeout, never block forever."""
    import routers.case_dna as cd

    cd._genome_refresh_inflight.clear()
    cd._genome_refresh_rerun.clear()
    cd._genome_refresh_done_event.clear()

    async def _hangs_forever(predmet_id, uid, stari_procent, trigger, event_id=None):
        await asyncio.sleep(3600)  # never completes within the test

    with patch.object(cd, "_do_genome_refresh", new=_hangs_forever), \
         patch.object(cd, "_GENOME_COALESCE_WAIT_TIMEOUT", 0.05):
        async def _caller_a():
            await cd._run_genome_background("p1", "u1")

        async def _caller_b():
            await asyncio.sleep(0.01)
            await cd._run_genome_background("p1", "u1")

        task_a = asyncio.create_task(_caller_a())
        # caller_b must return via the timeout fallback well within a test-safe bound,
        # even though caller_a's own underlying work never completes.
        await asyncio.wait_for(_caller_b(), timeout=2.0)
        task_a.cancel()
        try:
            await task_a
        except asyncio.CancelledError:
            pass


@pytest.mark.anyio
async def test_refresh_case_dna_endpoint_guard_unaffected_by_this_fix():
    """Regression: the manual /case-dna/refresh endpoint's own independent
    reject-if-busy guard (BLACKSWAN-HIGH-003) still works exactly as before --
    it uses _genome_refresh_inflight as a plain set, untouched by this fix."""
    import routers.case_dna as cd

    cd._genome_refresh_inflight.clear()
    cd._genome_refresh_inflight.add("p1")
    try:
        with pytest.raises(Exception) as exc:
            await cd.refresh_case_dna("p1", _req(), {"user_id": "u1"})
        assert getattr(exc.value, "status_code", None) == 409
    finally:
        cd._genome_refresh_inflight.discard("p1")


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-046 -- CIO /run (force regenerate) had no claim/lock at all,
# unlike /daily's own 2-step claim.
# ═══════════════════════════════════════════════════════════════════════════

def _stateful_cio_izvestaj_supa():
    rows: dict = {}

    class _Builder:
        def __init__(self, kind, payload=None):
            self.kind = kind
            self.payload = payload
            self.filters = {}
            self.lt_filters = {}

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def lt(self, col, val):
            self.lt_filters[col] = val
            return self

        def single(self):
            return self

        def execute(self):
            res = MagicMock()
            if self.kind == "insert":
                key = (self.payload["user_id"], self.payload["datum"])
                if key in rows:
                    raise Exception('duplicate key value violates unique constraint "cio_dnevni_izvestaj_user_id_datum_key"')
                row = dict(self.payload)
                row.setdefault("created_at", __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc).isoformat())  # simulates DB's DEFAULT now()
                rows[key] = row
                res.data = [rows[key]]
                return res
            if self.kind == "update":
                key = (self.filters.get("user_id"), self.filters.get("datum"))
                row = rows.get(key)
                matched = row is not None and all(
                    row.get(k, "") < v for k, v in self.lt_filters.items()
                )
                if matched:
                    rows[key].update(self.payload)
                    res.data = [rows[key]]
                else:
                    res.data = []
                return res
            if self.kind == "upsert":
                # Real Postgres ON CONFLICT DO UPDATE only touches the columns in the
                # payload (e.g. created_at is NOT in cio_run's own upsert payload) --
                # merge, don't replace, or this mock would silently wipe the claim
                # timestamp the update/insert step just set.
                key = (self.payload["user_id"], self.payload["datum"])
                if key in rows:
                    rows[key].update(self.payload)
                else:
                    rows[key] = dict(self.payload)
                res.data = [rows[key]]
                return res
            res.data = None
            return res

    def _table(name):
        assert name == "cio_dnevni_izvestaj"
        t = MagicMock()
        t.insert.side_effect = lambda payload: _Builder("insert", payload)
        t.update.side_effect = lambda payload: _Builder("update", payload)
        t.upsert = lambda payload, **kw: _Builder("upsert", payload)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, rows


@pytest.mark.anyio
async def test_cio_run_concurrent_calls_charge_only_once():
    """Original-scenario reproduction: two literally-concurrent /run calls
    (double-click) for the same user, same day -- only ONE may charge."""
    import routers.cio as cio

    supa, _rows = _stateful_cio_izvestaj_supa()
    user = {"user_id": "u1", "email": "a@b.com"}

    with patch.object(cio, "_get_supa", return_value=supa), \
         patch.object(cio, "_generiši_cio_izvestaj", new=AsyncMock(return_value={"predmeta_analizirano": 5})), \
         patch.object(cio, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        await cio.cio_run(_req(), user)
        await cio.cio_run(_req(), user)

    assert mock_usage.consume.await_count == 1


@pytest.mark.anyio
async def test_cio_run_still_charges_on_a_genuinely_separate_call():
    """Regression: /run's whole purpose is repeatable force-regeneration --
    a 2nd call well outside the short race-detection window must still
    charge normally, not be permanently locked out."""
    import routers.cio as cio

    supa, rows = _stateful_cio_izvestaj_supa()
    user = {"user_id": "u1", "email": "a@b.com"}

    with patch.object(cio, "_get_supa", return_value=supa), \
         patch.object(cio, "_generiši_cio_izvestaj", new=AsyncMock(return_value={"predmeta_analizirano": 5})), \
         patch.object(cio, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        await cio.cio_run(_req(), user)
        for row in rows.values():
            row["created_at"] = "1970-01-01T00:00:00+00:00"
        await cio.cio_run(_req(), user)

    assert mock_usage.consume.await_count == 2
