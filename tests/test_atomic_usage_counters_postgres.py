# -*- coding: utf-8 -*-
"""
Migration 108 — atomic usage counters, proven against a REAL PostgreSQL.

Findings B1/B2/B3 (second-order audit, 2026-08-08):

  B1  shared/usage.py::_increment_usage was a read-modify-write across two
      PostgREST round-trips. Concurrent calls for the same
      (user_id, feature_key, dan) both read N and both wrote N+1 -> one use
      permanently lost, in the user's favour. On the day's FIRST call both
      would INSERT, one hit UNIQUE(user_id, feature_key, dan), and the 23505
      was swallowed as non-fatal -> that use was never counted at all.

  B2  The daily-limit CHECK was itself check-then-act: read at the top of
      consume(), counter written an entire AI call later.

  B3  shared/deps.py::_increment_monthly_usage, same RMW shape on
      user_credits.mesecno_korisceno.

This matters because for the two features priced at ZERO credits
(copilot_ambient dnevni_limit=200, morning_briefing dnevni_limit=5) the daily
counter is the ONLY thing standing between a user and unbounded OpenAI spend.

Executes migrations/108_atomic_usage_counters.sql VERBATIM — the shipped
artifact, read from disk — and drives it from real concurrent connections.
Includes a NEGATIVE CONTROL proving the old read-modify-write loses updates
under the identical load, so these assertions cannot pass vacuously.
"""
import os
import sys
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_108 = REPO_ROOT / "migrations" / "108_atomic_usage_counters.sql"

psycopg = pytest.importorskip("psycopg", reason="psycopg not installed")


def _candidate_dsns():
    env = os.getenv("VINDEX_TEST_PG_DSN")
    if env:
        return [env]
    return [
        "host=127.0.0.1 port=55433 user=postgres dbname=postgres",
        "host=127.0.0.1 port=55432 user=postgres dbname=postgres",
        "host=127.0.0.1 port=5432 user=postgres dbname=postgres",
    ]


def _find_server():
    for dsn in _candidate_dsns():
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return dsn
        except Exception:
            continue
    return None


_SERVER_DSN = _find_server()

pytestmark = pytest.mark.skipif(
    _SERVER_DSN is None,
    reason="no reachable PostgreSQL server — atomic usage-counter proof skipped",
)


@pytest.fixture(scope="module")
def pg_dsn():
    dbname = f"vindex_counters_{uuid.uuid4().hex[:12]}"
    admin = _SERVER_DSN
    with psycopg.connect(admin, autocommit=True) as c:
        for role in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    target = admin.replace("dbname=postgres", f"dbname={dbname}")
    try:
        with psycopg.connect(target, autocommit=True) as c:
            # Real shape of the two tables the migration touches, including the
            # UNIQUE constraint migration 064 already provides — the migration
            # relies on it for ON CONFLICT and must not need a schema change.
            c.execute("""
                CREATE TABLE public.feature_usage (
                  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id           UUID NOT NULL,
                  feature_key       TEXT NOT NULL,
                  dan               DATE NOT NULL,
                  mesec             TEXT,
                  broj_koriscenja   INTEGER NOT NULL DEFAULT 0,
                  krediti_potroseni DOUBLE PRECISION NOT NULL DEFAULT 0,
                  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  UNIQUE (user_id, feature_key, dan)
                );
                CREATE TABLE public.user_credits (
                  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id           UUID NOT NULL UNIQUE,
                  credits_remaining INTEGER NOT NULL DEFAULT 15,
                  mesecno_korisceno INTEGER DEFAULT 0,
                  mesec             TEXT,
                  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            c.execute(MIGRATION_108.read_text(encoding="utf-8"))
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (dbname,))
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


TODAY = date.today()
MONTH = datetime.now(timezone.utc).strftime("%Y-%m")


def _bump(dsn, uid, feature="copilot_ambient", credits=0.0, limit=None):
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute(
            "SELECT public.increment_feature_usage(%s,%s,%s,%s,%s,%s)",
            (uid, feature, TODAY, MONTH, credits, limit),
        ).fetchone()[0]


def _count(dsn, uid, feature="copilot_ambient"):
    with psycopg.connect(dsn, autocommit=True) as c:
        row = c.execute(
            "SELECT broj_koriscenja, krediti_potroseni FROM public.feature_usage "
            "WHERE user_id=%s AND feature_key=%s AND dan=%s", (uid, feature, TODAY)
        ).fetchone()
    return row


def _uid():
    return str(uuid.uuid4())


# ═══ Contract ═══════════════════════════════════════════════════════════════

def test_first_use_creates_row(pg_dsn):
    uid = _uid()
    assert _bump(pg_dsn, uid) == 1
    assert _count(pg_dsn, uid)[0] == 1


def test_sequential_increments_accumulate(pg_dsn):
    uid = _uid()
    assert [_bump(pg_dsn, uid) for _ in range(5)] == [1, 2, 3, 4, 5]


def test_credits_accumulate_alongside_the_count(pg_dsn):
    uid = _uid()
    for _ in range(3):
        _bump(pg_dsn, uid, credits=2.5)
    cnt, spent = _count(pg_dsn, uid)
    assert cnt == 3 and spent == pytest.approx(7.5)


def test_limit_rejects_once_reached_and_counts_nothing(pg_dsn):
    uid = _uid()
    assert [_bump(pg_dsn, uid, limit=3) for _ in range(3)] == [1, 2, 3]
    for _ in range(4):
        assert _bump(pg_dsn, uid, limit=3) == -1
    assert _count(pg_dsn, uid)[0] == 3, "a rejected call must not increment"


def test_null_limit_never_rejects(pg_dsn):
    uid = _uid()
    for i in range(1, 21):
        assert _bump(pg_dsn, uid, limit=None) == i


def test_separate_features_have_separate_counters(pg_dsn):
    uid = _uid()
    _bump(pg_dsn, uid, feature="a", limit=1)
    assert _bump(pg_dsn, uid, feature="a", limit=1) == -1
    assert _bump(pg_dsn, uid, feature="b", limit=1) == 1, "features must not share a counter"


def test_separate_users_have_separate_counters(pg_dsn):
    u1, u2 = _uid(), _uid()
    _bump(pg_dsn, u1, limit=1)
    assert _bump(pg_dsn, u1, limit=1) == -1
    assert _bump(pg_dsn, u2, limit=1) == 1, "one user must not consume another's quota"


# ═══ Concurrency — the actual point ═════════════════════════════════════════

def _hammer(fn, n):
    """Fires n threads simultaneously via a barrier; returns their results."""
    barrier = threading.Barrier(n)
    out, lock = [], threading.Lock()

    def worker(i):
        try:
            barrier.wait(timeout=30)
            r = fn(i)
        except Exception as exc:
            r = f"ERR:{type(exc).__name__}"
        with lock:
            out.append(r)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in ts), "a worker deadlocked"
    return out


def test_concurrent_increments_lose_nothing(pg_dsn):
    """B1: 50 concurrent uses must count as exactly 50."""
    uid = _uid()
    res = _hammer(lambda i: _bump(pg_dsn, uid), 50)
    assert all(isinstance(r, int) for r in res), f"errors: {[r for r in res if not isinstance(r,int)]}"
    assert _count(pg_dsn, uid)[0] == 50
    assert sorted(res) == list(range(1, 51)), "every caller must observe a unique count"


def test_concurrent_first_use_does_not_lose_the_insert_race(pg_dsn):
    """B1's worse half: on the day's first call, concurrent INSERTs used to
    collide on UNIQUE(user_id,feature_key,dan) and the 23505 was swallowed,
    so that use was never counted at all."""
    uid = _uid()
    res = _hammer(lambda i: _bump(pg_dsn, uid), 30)
    assert all(isinstance(r, int) and r > 0 for r in res), f"a first-use call was lost: {res}"
    assert _count(pg_dsn, uid)[0] == 30


def test_concurrent_calls_cannot_exceed_the_daily_limit(pg_dsn):
    """B2: the limit is enforced by the increment itself, so no interleaving
    can push the count past it."""
    uid = _uid()
    res = _hammer(lambda i: _bump(pg_dsn, uid, limit=10), 60)
    granted = [r for r in res if isinstance(r, int) and r > 0]
    denied = [r for r in res if r == -1]
    assert len(granted) == 10, f"exactly 10 may be granted, got {len(granted)}"
    assert len(denied) == 50
    assert _count(pg_dsn, uid)[0] == 10
    assert sorted(granted) == list(range(1, 11))


def test_zero_credit_feature_limit_holds_under_load(pg_dsn):
    """copilot_ambient shape: krediti=0, dnevni_limit=200 — the counter is the
    ONLY budget protection, so it has to hold exactly."""
    uid = _uid()
    res = _hammer(lambda i: _bump(pg_dsn, uid, feature="copilot_ambient", credits=0.0, limit=20), 80)
    granted = [r for r in res if isinstance(r, int) and r > 0]
    assert len(granted) == 20
    assert _count(pg_dsn, uid)[0] == 20


def test_concurrent_credits_sum_is_exact(pg_dsn):
    uid = _uid()
    _hammer(lambda i: _bump(pg_dsn, uid, credits=1.5), 40)
    cnt, spent = _count(pg_dsn, uid)
    assert cnt == 40
    assert spent == pytest.approx(60.0), "krediti_potroseni must not lose updates either"


# ═══ Monthly counter (B3) ═══════════════════════════════════════════════════

def _monthly(dsn, uid, mesec=MONTH):
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT public.increment_monthly_usage(%s,%s)", (uid, mesec)).fetchone()[0]


@pytest.fixture
def credit_user(pg_dsn):
    def _make():
        uid = _uid()
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute("INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s, 100)", (uid,))
        return uid
    return _make


def test_monthly_counter_increments(pg_dsn, credit_user):
    uid = credit_user()
    assert [_monthly(pg_dsn, uid) for _ in range(3)] == [1, 2, 3]


def test_monthly_counter_resets_on_month_change(pg_dsn, credit_user):
    uid = credit_user()
    _monthly(pg_dsn, uid, "2026-07")
    _monthly(pg_dsn, uid, "2026-07")
    assert _monthly(pg_dsn, uid, "2026-08") == 1, "a new month restarts the count"


def test_monthly_counter_missing_user_is_safe(pg_dsn):
    assert _monthly(pg_dsn, _uid()) == -1


def test_concurrent_monthly_increments_lose_nothing(pg_dsn, credit_user):
    """B3: same RMW shape as B1, on user_credits.mesecno_korisceno."""
    uid = credit_user()
    res = _hammer(lambda i: _monthly(pg_dsn, uid), 40)
    assert sorted(res) == list(range(1, 41))
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        got = c.execute(
            "SELECT mesecno_korisceno, credits_remaining FROM public.user_credits WHERE user_id=%s", (uid,)
        ).fetchone()
    assert got[0] == 40
    assert got[1] == 100, "the monthly counter must never touch the balance"


# ═══ NEGATIVE CONTROL — proof the harness detects the old defect ════════════

def test_negative_control_read_modify_write_loses_updates(pg_dsn):
    """Reproduces the PRE-108 implementation (SELECT then UPDATE, two
    statements) under the identical 50-thread load and REQUIRES it to lose
    updates. Without this, the assertions above could pass vacuously — the
    same trap that let a vulnerable deduct_n_credits body sit in production
    while CI was green."""
    uid = _uid()
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(
            "INSERT INTO public.feature_usage (user_id, feature_key, dan, mesec, broj_koriscenja) "
            "VALUES (%s,'legacy',%s,%s,0)", (uid, TODAY, MONTH),
        )

    def legacy(_i):
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            cur = c.execute(
                "SELECT broj_koriscenja FROM public.feature_usage "
                "WHERE user_id=%s AND feature_key='legacy' AND dan=%s", (uid, TODAY)
            ).fetchone()[0]
            c.execute(
                "UPDATE public.feature_usage SET broj_koriscenja=%s "
                "WHERE user_id=%s AND feature_key='legacy' AND dan=%s", (cur + 1, uid, TODAY)
            )
        return cur + 1

    _hammer(legacy, 50)
    final = _count(pg_dsn, uid, feature="legacy")[0]
    assert final < 50, (
        f"negative control did NOT lose updates (final={final}/50) — the harness "
        "cannot distinguish the racy implementation from the atomic one, so every "
        "other assertion in this file is meaningless"
    )

    # And the shipped function, same load, same table: exact.
    uid2 = _uid()
    _hammer(lambda i: _bump(pg_dsn, uid2), 50)
    assert _count(pg_dsn, uid2)[0] == 50
