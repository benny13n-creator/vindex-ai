# -*- coding: utf-8 -*-
"""
Beta Gate Blocker Closure — REAL PostgreSQL concurrency proof for
migrations/107_beta_gate_credit_race_closure.sql.

WHY THIS FILE EXISTS
────────────────────
Final Beta Gate finding F5 (CRITICAL) was "fixed" once before and never
reached production, and the entire test suite stayed green throughout —
because every existing credit test mocks the RPC. Mocks validate the
contract the *code expects*; they cannot validate the contract the
*database actually offers*. That blind spot is precisely what let a
vulnerable function body sit live in production while CI was green.

So this file does not mock the database. It:
  1. connects to a real PostgreSQL server,
  2. executes migrations/107_beta_gate_credit_race_closure.sql VERBATIM
     (the shipped artifact, not a copy of it),
  3. drives it with genuinely concurrent connections from multiple threads,
  4. asserts the accounting invariant holds.

THE INVARIANT UNDER TEST
────────────────────────
    successful_consumptions * credits_per_request + final_balance
        == initial_balance
    AND final_balance >= 0

i.e. a user can never obtain more paid operations than their balance funds,
no matter how requests interleave.

RUNNING IT
──────────
Auto-discovers a server in this order:
  1. $VINDEX_TEST_PG_DSN
  2. 127.0.0.1:55432 (throwaway cluster; see the closure report for setup)
  3. 127.0.0.1:5432  (local default, trust auth only)
Skips with a clear reason if none is reachable, so environments without a
PostgreSQL server (e.g. a bare CI runner) stay green — the skip is an
environment fact, never a way to dodge a failing assertion.
"""
import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_107 = REPO_ROOT / "migrations" / "107_beta_gate_credit_race_closure.sql"

psycopg = pytest.importorskip("psycopg", reason="psycopg not installed — real-DB credit tests skipped")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Server discovery ────────────────────────────────────────────────────────

def _candidate_dsns():
    env = os.getenv("VINDEX_TEST_PG_DSN")
    if env:
        return [env]
    return [
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
    reason=(
        "no reachable PostgreSQL server (tried $VINDEX_TEST_PG_DSN, 127.0.0.1:55432, "
        "127.0.0.1:5432) — real-DB credit-race proof skipped"
    ),
)


# ─── Schema fixture ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg_dsn():
    """Creates an isolated database, installs the minimal schema the migration
    depends on, then executes migration 107 verbatim. Drops the database
    afterwards. Touches nothing outside its own database."""
    dbname = f"vindex_creditrace_{uuid.uuid4().hex[:12]}"
    admin = _SERVER_DSN

    with psycopg.connect(admin, autocommit=True) as c:
        # Roles the migration's GRANT/REVOKE statements reference. Created
        # NOLOGIN so they can never be used to connect; they exist purely so
        # the shipped privilege statements execute verbatim rather than being
        # stripped for the test (a stripped test would not prove the real file
        # runs cleanly).
        for role in ("anon", "authenticated", "service_role"):
            # Role names are fixed literals from the migration, never user input.
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    target = admin.replace("dbname=postgres", f"dbname={dbname}")

    try:
        with psycopg.connect(target, autocommit=True) as c:
            # Minimal real shape of public.user_credits (supabase_setup.sql),
            # minus the auth.users FK which does not exist outside Supabase.
            c.execute("""
                CREATE TABLE public.user_credits (
                  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id           UUID        NOT NULL UNIQUE,
                  credits_remaining INTEGER     NOT NULL DEFAULT 15,
                  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            # The artifact under test, executed exactly as shipped.
            c.execute(MIGRATION_107.read_text(encoding="utf-8"))
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (dbname,),
            )
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


@pytest.fixture
def make_user(pg_dsn):
    """Creates a user_credits row with a given starting balance."""
    def _make(balance: int) -> str:
        uid = str(uuid.uuid4())
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute(
                "INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s, %s)",
                (uid, balance),
            )
        return uid
    return _make


def _balance(dsn, uid) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        row = c.execute(
            "SELECT credits_remaining FROM public.user_credits WHERE user_id = %s", (uid,)
        ).fetchone()
    return row[0] if row else None


def _deduct(dsn, uid, n) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT public.deduct_n_credits(%s, %s)", (uid, n)).fetchone()[0]


def _refund(dsn, uid, n) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT public.refund_n_credits(%s, %s)", (uid, n)).fetchone()[0]


# ═══════════════════════════════════════════════════════════════════════════
# §7 — Normal behaviour (T1–T6)
# ═══════════════════════════════════════════════════════════════════════════

def test_T1_exact_balance_succeeds_and_zeroes(pg_dsn, make_user):
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, 10) == 0
    assert _balance(pg_dsn, uid) == 0


def test_T2_insufficient_balance_fails_and_does_not_mutate(pg_dsn, make_user):
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, 11) == -1
    assert _balance(pg_dsn, uid) == 10, "a rejected charge must not consume anything"


def test_T3_partial_consumption(pg_dsn, make_user):
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, 4) == 6
    assert _balance(pg_dsn, uid) == 6


def test_T4_zero_request_consumes_nothing(pg_dsn, make_user):
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, 0) == -1, "p_n=0 is not a charge; contract says -1"
    assert _balance(pg_dsn, uid) == 10


def test_T5_negative_request_never_increases_credits(pg_dsn, make_user):
    """The pre-107 body computed GREATEST(0, balance - p_n); a negative p_n
    therefore INCREASED the balance -- a free-credit generator for anything
    that could reach the RPC."""
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, -5) == -1
    assert _balance(pg_dsn, uid) == 10, "negative p_n must never mint credits"


def test_T6_nonexistent_user_fails_safely(pg_dsn, make_user):
    other = make_user(7)
    ghost = str(uuid.uuid4())
    assert _deduct(pg_dsn, ghost, 3) == -1
    assert _balance(pg_dsn, ghost) is None
    assert _balance(pg_dsn, other) == 7, "unrelated rows must be untouched"


def test_null_amount_fails_safely(pg_dsn, make_user):
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, None) == -1
    assert _balance(pg_dsn, uid) == 10


def test_balance_can_never_go_negative_by_construction(pg_dsn, make_user):
    """Drain to zero one credit at a time, then keep pushing."""
    uid = make_user(3)
    assert [_deduct(pg_dsn, uid, 1) for _ in range(3)] == [2, 1, 0]
    for _ in range(5):
        assert _deduct(pg_dsn, uid, 1) == -1
    assert _balance(pg_dsn, uid) == 0


# ═══════════════════════════════════════════════════════════════════════════
# §8 / §9 — Adversarial concurrency. The core of this mission.
# ═══════════════════════════════════════════════════════════════════════════

def _run_concurrent(dsn, uid, requests):
    """Fires len(requests) genuinely concurrent deductions, each on its own
    connection, released simultaneously by a barrier to maximise contention.
    Returns (successes, insufficient, errors) where successes is a list of the
    per-request amounts that were actually charged."""
    barrier = threading.Barrier(len(requests))
    successes, insufficient, errors = [], [], []
    lock = threading.Lock()

    def worker(amount):
        try:
            with psycopg.connect(dsn, autocommit=True) as c:
                barrier.wait(timeout=30)
                ret = c.execute("SELECT public.deduct_n_credits(%s, %s)", (uid, amount)).fetchone()[0]
            with lock:
                if ret is None:
                    errors.append(("null-return", amount))
                elif ret >= 0:
                    successes.append(amount)      # SUCCESS
                else:
                    insufficient.append(amount)   # INSUFFICIENT_CREDITS
        except Exception as exc:                  # ERROR
            with lock:
                errors.append((type(exc).__name__, amount))

    threads = [threading.Thread(target=worker, args=(a,)) for a in requests]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "a worker deadlocked"
    return successes, insufficient, errors


def _assert_invariant(dsn, uid, initial, successes, insufficient, errors, label):
    final = _balance(dsn, uid)
    charged = sum(successes)
    assert not errors, f"{label}: unexpected errors {errors}"
    assert final >= 0, f"{label}: balance went negative ({final})"
    assert charged + final == initial, (
        f"{label}: accounting broken -- charged {charged} + final {final} != initial {initial}"
    )
    assert len(successes) + len(insufficient) == len(successes) + len(insufficient)
    return final, charged


def test_scenario_A_10_balance_20x2(pg_dsn, make_user):
    """§9 Scenario A: balance 10, twenty concurrent requests of 2.
    At most five may succeed."""
    uid = make_user(10)
    s, i, e = _run_concurrent(pg_dsn, uid, [2] * 20)
    final, charged = _assert_invariant(pg_dsn, uid, 10, s, i, e, "A")
    assert len(s) <= 5, f"A: {len(s)} requests succeeded, funding allows at most 5"
    assert len(s) * 2 + final == 10
    assert len(i) == 20 - len(s)


def test_scenario_B_100_balance_100x3(pg_dsn, make_user):
    """§9 Scenario B: balance 100, one hundred concurrent requests of 3."""
    uid = make_user(100)
    s, i, e = _run_concurrent(pg_dsn, uid, [3] * 100)
    final, charged = _assert_invariant(pg_dsn, uid, 100, s, i, e, "B")
    assert len(s) <= 33, f"B: {len(s)} succeeded, funding allows at most 33"
    assert final == 100 - 3 * len(s)


def test_scenario_C_1_balance_50x1(pg_dsn, make_user):
    """§9 Scenario C: balance 1, fifty concurrent requests of 1.
    Exactly one may win."""
    uid = make_user(1)
    s, i, e = _run_concurrent(pg_dsn, uid, [1] * 50)
    final, charged = _assert_invariant(pg_dsn, uid, 1, s, i, e, "C")
    assert len(s) == 1, f"C: exactly one request may win, got {len(s)}"
    assert final == 0
    assert len(i) == 49


def test_scenario_D_10_balance_50x1(pg_dsn, make_user):
    """§9 Scenario D: balance 10, fifty concurrent requests of 1."""
    uid = make_user(10)
    s, i, e = _run_concurrent(pg_dsn, uid, [1] * 50)
    final, charged = _assert_invariant(pg_dsn, uid, 10, s, i, e, "D")
    assert len(s) == 10, f"D: exactly ten may win, got {len(s)}"
    assert final == 0


def test_scenario_E_mixed_request_sizes(pg_dsn, make_user):
    """§9 Scenario E: balance 100, concurrent mixed sizes 1/2/3/5/10."""
    uid = make_user(100)
    requests = ([1] * 10) + ([2] * 10) + ([3] * 10) + ([5] * 10) + ([10] * 10)
    s, i, e = _run_concurrent(pg_dsn, uid, requests)
    final, charged = _assert_invariant(pg_dsn, uid, 100, s, i, e, "E")
    assert charged <= 100


def test_concurrent_deduct_and_refund_cannot_lose_an_update(pg_dsn, make_user):
    """The second race found in this mission: the old Python refund fallback
    did SELECT-then-UPDATE, so a refund could write back a pre-charge balance
    and erase a deduction. Migration 107's refund is a single statement, so
    interleaving deducts and refunds must still balance exactly."""
    uid = make_user(100)
    barrier = threading.Barrier(40)
    results = []
    lock = threading.Lock()

    def worker(kind):
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            barrier.wait(timeout=30)
            fn = "deduct_n_credits" if kind == "d" else "refund_n_credits"
            ret = c.execute(f"SELECT public.{fn}(%s, %s)", (uid, 2)).fetchone()[0]
        with lock:
            results.append((kind, ret))

    kinds = (["d"] * 20) + ["r"] * 20
    threads = [threading.Thread(target=worker, args=(k,)) for k in kinds]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    charged = sum(2 for k, r in results if k == "d" and r >= 0)
    refunded = sum(2 for k, r in results if k == "r" and r >= 0)
    assert _balance(pg_dsn, uid) == 100 - charged + refunded
    assert _balance(pg_dsn, uid) >= 0


# ═══════════════════════════════════════════════════════════════════════════
# §10 — Failure injection / rollback
# ═══════════════════════════════════════════════════════════════════════════

def test_rollback_after_deduction_restores_balance(pg_dsn, make_user):
    """A deduction inside a transaction that later rolls back must leave no
    trace -- proves the function participates in the caller's transaction and
    does not commit independently (it has no COMMIT of its own)."""
    uid = make_user(10)
    with psycopg.connect(pg_dsn) as c:          # autocommit=False
        got = c.execute("SELECT public.deduct_n_credits(%s, %s)", (uid, 4)).fetchone()[0]
        assert got == 6
        c.rollback()
    assert _balance(pg_dsn, uid) == 10, "rolled-back charge must not persist"


def test_committed_deduction_persists(pg_dsn, make_user):
    uid = make_user(10)
    with psycopg.connect(pg_dsn) as c:
        c.execute("SELECT public.deduct_n_credits(%s, %s)", (uid, 4))
        c.commit()
    assert _balance(pg_dsn, uid) == 6


def test_deduct_then_compensating_refund_is_net_zero(pg_dsn, make_user):
    """The architecture uses compensating refunds (UsageService.refund), not
    transaction rollback, for downstream AI failure -- charge and refund must
    cancel exactly."""
    uid = make_user(20)
    assert _deduct(pg_dsn, uid, 12) == 8
    assert _refund(pg_dsn, uid, 12) == 20
    assert _balance(pg_dsn, uid) == 20


def test_refund_contract_rejects_non_positive(pg_dsn, make_user):
    uid = make_user(10)
    assert _refund(pg_dsn, uid, 0) == -1
    assert _refund(pg_dsn, uid, -3) == -1
    assert _balance(pg_dsn, uid) == 10, "a negative refund must never drain credits"


def test_refund_nonexistent_user_is_safe(pg_dsn):
    assert _refund(pg_dsn, str(uuid.uuid4()), 5) == -1


def test_refund_one_credit_delegates(pg_dsn, make_user):
    uid = make_user(5)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        assert c.execute("SELECT public.refund_one_credit(%s)", (uid,)).fetchone()[0] == 6
    assert _balance(pg_dsn, uid) == 6


# ═══════════════════════════════════════════════════════════════════════════
# §11 — Retry / duplicate request
# ═══════════════════════════════════════════════════════════════════════════

def test_retry_charges_twice_by_design_and_stays_consistent(pg_dsn, make_user):
    """There is deliberately NO idempotency key on credit consumption in this
    product -- two submits of the same logical operation are two chargeable
    operations, and callers (api.py) compensate with refunds on failure rather
    than deduplicating. This test pins that documented behaviour so a future
    change to it is a conscious decision, and proves the balance stays exact
    either way."""
    uid = make_user(10)
    assert _deduct(pg_dsn, uid, 3) == 7
    assert _deduct(pg_dsn, uid, 3) == 4
    assert _balance(pg_dsn, uid) == 4


def test_concurrent_duplicate_requests_cannot_overdraw(pg_dsn, make_user):
    """Even if a retry storm submits the same operation many times at once,
    the invariant holds -- that is the protection that matters here, not
    deduplication."""
    uid = make_user(5)
    s, i, e = _run_concurrent(pg_dsn, uid, [5] * 12)
    final, charged = _assert_invariant(pg_dsn, uid, 5, s, i, e, "dup")
    assert len(s) == 1, "only one of twelve identical 5-credit retries may be funded"
    assert final == 0


# ═══════════════════════════════════════════════════════════════════════════
# §6 / §13 — Migration hygiene: idempotency + privilege preservation.
#
# §13 explicitly forbids ASSUMING migration 102's lockdown survives
# CREATE OR REPLACE FUNCTION. These execute it and check.
# ═══════════════════════════════════════════════════════════════════════════

_EXPECTED_ACL = "{postgres=X/postgres,service_role=X/postgres}"


def _acl(conn, sig="public.deduct_n_credits(uuid,integer)"):
    return conn.execute(
        "SELECT proacl::text FROM pg_proc WHERE oid = %s::regprocedure", (sig,)
    ).fetchone()[0]


def _privs(conn, sig="public.deduct_n_credits(uuid,integer)"):
    return {
        r: conn.execute(
            "SELECT has_function_privilege(%s, %s, 'EXECUTE')", (r, sig)
        ).fetchone()[0]
        for r in ("anon", "authenticated", "service_role")
    }


def test_migration_107_produces_the_verified_production_acl(pg_dsn):
    """The ACL migration 107 produces must be byte-identical to the state
    read out of production on 2026-08-08 for the migration-102 lockdown:
    only the owner and service_role, no PUBLIC entry."""
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        assert _acl(c) == _EXPECTED_ACL
        assert _privs(c) == {"anon": False, "authenticated": False, "service_role": True}


def test_migration_107_is_idempotent(pg_dsn):
    """Re-running the whole migration changes nothing (it is labelled
    idempotent, and operators do re-run migrations)."""
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(MIGRATION_107.read_text(encoding="utf-8"))
        assert _acl(c) == _EXPECTED_ACL
        assert _privs(c) == {"anon": False, "authenticated": False, "service_role": True}
        # and the function still behaves
    uid = str(uuid.uuid4())
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s, 5)", (uid,))
    assert _deduct(pg_dsn, uid, 6) == -1
    assert _deduct(pg_dsn, uid, 5) == 0


def test_bare_create_or_replace_does_not_reopen_execute_privileges(pg_dsn):
    """The specific §13 concern: replacing the function body WITHOUT any
    accompanying GRANT/REVOKE must not silently restore Postgres's
    EXECUTE-to-PUBLIC default. If this ever fails, every CREATE OR REPLACE in
    this repo is a latent privilege regression."""
    sql = MIGRATION_107.read_text(encoding="utf-8")
    body = sql.split("-- ─── 2.")[0].split("CREATE OR REPLACE FUNCTION public.deduct_n_credits", 1)[1]
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("CREATE OR REPLACE FUNCTION public.deduct_n_credits" + body)
        assert _acl(c) == _EXPECTED_ACL, "CREATE OR REPLACE reopened the ACL"
        assert _privs(c)["anon"] is False
        assert _privs(c)["authenticated"] is False
        assert _privs(c)["service_role"] is True


def test_new_refund_functions_are_locked_down_too(pg_dsn):
    """The two functions created by 107 would otherwise inherit
    EXECUTE-to-PUBLIC."""
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        for sig in ("public.refund_n_credits(uuid,integer)", "public.refund_one_credit(uuid)"):
            p = _privs(c, sig)
            assert p == {"anon": False, "authenticated": False, "service_role": True}, f"{sig}: {p}"


# ═══════════════════════════════════════════════════════════════════════════
# NEGATIVE CONTROL — proof this harness actually detects the defect.
#
# A test suite that passes against both the vulnerable and the fixed body
# proves nothing. This installs the REAL pre-107 production body (copied from
# the live catalog dump taken 2026-08-08) under a separate name and shows the
# identical scenario violates the invariant. If this ever starts passing the
# invariant, the harness has lost its teeth and every test above is worthless.
# ═══════════════════════════════════════════════════════════════════════════

_LEGACY_VULNERABLE_BODY = """
CREATE OR REPLACE FUNCTION public.deduct_n_credits_legacy(p_user_id UUID, p_n INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  new_balance INTEGER;
BEGIN
  UPDATE public.user_credits
    SET credits_remaining = GREATEST(0, credits_remaining - p_n)
  WHERE user_id = p_user_id
  RETURNING credits_remaining INTO new_balance;
  RETURN COALESCE(new_balance, 0);
END;
$$;
"""


def test_negative_control_legacy_body_DOES_overdraw(pg_dsn, make_user):
    """Balance 1, fifty concurrent requests of 1, against the body that was
    actually live in production until this migration.

    Expected: every single request 'succeeds' (the old body has no balance
    predicate at all, so the UPDATE always matches and floors at zero), which
    is exactly the CRITICAL finding -- 50 paid operations funded by 1 credit.
    """
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(_LEGACY_VULNERABLE_BODY)

    uid = make_user(1)
    barrier = threading.Barrier(50)
    rets = []
    lock = threading.Lock()

    def worker():
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            barrier.wait(timeout=30)
            r = c.execute("SELECT public.deduct_n_credits_legacy(%s, %s)", (uid, 1)).fetchone()[0]
        with lock:
            rets.append(r)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    granted = [r for r in rets if r >= 0]
    final = _balance(pg_dsn, uid)

    assert len(granted) == 50, (
        "negative control failed to reproduce: the legacy body should grant every "
        f"request, got {len(granted)}/50"
    )
    assert len(granted) * 1 + final != 1, (
        "negative control did NOT violate the invariant -- the harness cannot "
        "distinguish the vulnerable body from the fixed one, so every other "
        "assertion in this file is meaningless"
    )
    assert final == 0

    # And the fixed function, same scenario, on a fresh user: exactly one wins.
    uid2 = make_user(1)
    s, i, e = _run_concurrent(pg_dsn, uid2, [1] * 50)
    assert len(s) == 1, "fixed body must fund exactly one request"
    assert _balance(pg_dsn, uid2) == 0


# ═══════════════════════════════════════════════════════════════════════════
# §12 — AI-path integration: the Python contract vs the REAL database.
#
# This is the specific blind spot that let a vulnerable body live in
# production while CI was green. Every other credit test in this repository
# mocks the RPC, so they validate the contract the code EXPECTS. These drive
# the real UsageService.consume() against the real function.
# ═══════════════════════════════════════════════════════════════════════════

class _RealPgSupabaseShim:
    """Minimal stand-in for the Supabase client exposing only .rpc(...).execute(),
    routed to the real PostgreSQL function under test."""

    _ALLOWED = {
        "deduct_n_credits": "SELECT public.deduct_n_credits(%(p_user_id)s, %(p_n)s)",
        "deduct_credit":    "SELECT public.deduct_credit_shim(%(p_user_id)s)",
        "refund_n_credits": "SELECT public.refund_n_credits(%(p_user_id)s, %(p_n)s)",
    }

    def __init__(self, dsn):
        self._dsn = dsn

    def rpc(self, name, params):
        sql = self._ALLOWED[name]
        dsn = self._dsn

        class _Call:
            def execute(self_inner):
                from types import SimpleNamespace
                with psycopg.connect(dsn, autocommit=True) as c:
                    val = c.execute(sql, params).fetchone()[0]
                return SimpleNamespace(data=val)

        return _Call()


_DEDUCT_CREDIT_SHIM = """
CREATE OR REPLACE FUNCTION public.deduct_credit_shim(p_user_id UUID)
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE new_credits INTEGER;
BEGIN
  UPDATE public.user_credits
     SET credits_remaining = GREATEST(credits_remaining - 1, 0), updated_at = NOW()
   WHERE user_id = p_user_id AND credits_remaining > 0
  RETURNING credits_remaining INTO new_credits;
  IF NOT FOUND THEN
    SELECT credits_remaining INTO new_credits FROM public.user_credits WHERE user_id = p_user_id;
    RETURN COALESCE(new_credits, 0);
  END IF;
  RETURN new_credits;
END; $$;
"""


@pytest.fixture
def consume_against_real_db(pg_dsn, monkeypatch):
    """Wires UsageService.consume()/refund() to the real database."""
    from unittest.mock import AsyncMock
    import shared.deps as deps
    import shared.usage as usage

    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(_DEDUCT_CREDIT_SHIM)

    shim = _RealPgSupabaseShim(pg_dsn)
    monkeypatch.setattr(deps, "_get_supa", lambda: shim)
    monkeypatch.setattr(deps, "_increment_monthly_usage", lambda *a, **k: None)
    monkeypatch.setattr(usage, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(usage, "_get_credits", lambda uid: _balance(pg_dsn, uid) or 0)
    # return_value is NOT optional here. Since migration 108 consume() runs the
    # daily-counter increment BEFORE the charge and compares its result against
    # 0 to detect a rejected daily limit. A bare AsyncMock() returns a mock, and
    # `mock < 0` raises TypeError -- which every concurrency test below would
    # report as an unexplained worker error rather than a failed invariant.
    # Nobody caught it because these tests skip without a PostgreSQL server.
    monkeypatch.setattr(usage, "_increment_usage", AsyncMock(return_value=1))
    monkeypatch.setattr(usage, "_log_usage_event", AsyncMock())

    def _policy(krediti, multiplier=1):
        async def _get(_feature):
            return {
                "krediti": krediti, "credit_multiplier": multiplier,
                "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None,
                "ai_model": "gpt-4o", "estimated_cost_usd": None,
            }
        return _get

    return _policy


@pytest.mark.anyio
async def test_consume_charges_the_real_multiplier_amount(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """strategija-shaped feature: 2 credits x 6 multiplier = 12 actually leave
    the balance in the real database."""
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    uid = make_user(20)
    left = await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
    assert left == 8
    assert _balance(pg_dsn, uid) == 8


@pytest.mark.anyio
async def test_consume_raises_402_and_charges_nothing_when_underfunded(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """The exact CRITICAL scenario, end to end: the real function returns -1
    and the real Python code must turn that into 402 WITHOUT delivering."""
    from fastapi import HTTPException
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    uid = make_user(5)   # 5 < 12 required
    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")

    assert exc.value.status_code == 402
    assert _balance(pg_dsn, uid) == 5, "a rejected charge must not consume anything"


@pytest.mark.anyio
async def test_consume_refund_roundtrip_is_symmetric_for_multiplier_features(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """Charge/refund symmetry: refund() used to return `krediti` while
    consume() charged `krediti * multiplier`, silently costing the user 10
    credits on every failed 6x operation."""
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    uid = make_user(20)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
    assert _balance(pg_dsn, uid) == 8

    await usage.UsageService.refund(uid, "advokat@vindex.rs", "strategija")
    assert _balance(pg_dsn, uid) == 20, "refund must return exactly what consume took"


@pytest.mark.anyio
async def test_consume_fractional_price_still_charges_nothing(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """0 < krediti*multiplier < 1 resolves to n=0. Migration 107 rejects
    p_n<=0 with -1, so the app must not route this to the RPC at all --
    otherwise a fractional-priced feature would start 402-ing."""
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(0.5, 1))

    uid = make_user(10)
    left = await usage.UsageService.consume(uid, "advokat@vindex.rs", "cheap_feature")
    assert left == 10
    assert _balance(pg_dsn, uid) == 10


@pytest.mark.anyio
async def test_consume_at_one_credit_does_not_route_to_deduct_credit(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """CREDIT-CONSUME-001 (CRITICAL) regression.

    consume() used to send n_credits == 1 to deduct_credit, whose production
    body returns COALESCE(new_credits, 0) on its NOT-FOUND branch -- the
    CURRENT BALANCE, never a negative. `preostalo < 0` was therefore
    unreachable, no 402 fired, and the operation was delivered free.

    _RealPgSupabaseShim routes "deduct_credit" to deduct_credit_shim, which is
    a VERBATIM copy of that vulnerable production body. If consume() ever
    routes a 1-credit charge there again, the underfunded case below silently
    succeeds instead of raising 402 and this test fails.
    """
    from fastapi import HTTPException
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(1, 1))

    uid = make_user(0)                       # underfunded: 0 credits, price 1
    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "ai_pravna_pitanja")

    assert exc.value.status_code == 402
    assert _balance(pg_dsn, uid) == 0


@pytest.mark.anyio
async def test_concurrent_consume_at_one_credit_cannot_overdraw(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """The reproduction the adversarial review used: balance 1, 40 concurrent
    1-credit consume() calls. Before the fix this granted ~37 of them.

    n == 1 is the dominant price in feature_registry (ai_pravna_pitanja,
    copilot, strategija at multiplier=1, ~25 more), so this is the widest
    credit path in the product -- and it was the one branch the previous
    migration-107 work never exercised."""
    import asyncio as _asyncio
    from fastapi import HTTPException
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(1, 1))

    uid = make_user(1)

    async def one():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", "ai_pravna_pitanja")
            return "SUCCESS"
        except HTTPException as e:
            return "INSUFFICIENT" if e.status_code == 402 else f"ERROR:{e.status_code}"

    results = await _asyncio.gather(*[one() for _ in range(40)])
    granted = results.count("SUCCESS")

    assert granted == 1, f"exactly one 1-credit charge may be funded by a 1-credit balance, got {granted}"
    assert _balance(pg_dsn, uid) == 0
    assert granted * 1 + _balance(pg_dsn, uid) == 1


@pytest.mark.anyio
async def test_negative_control_deduct_credit_reports_success_when_it_charged_nothing(
    pg_dsn, make_user, monkeypatch, consume_against_real_db
):
    """NEGATIVE CONTROL for CREDIT-CONSUME-001.

    Proves the branch consume() used to take is genuinely unsafe, so the
    regression tests above are not passing vacuously. deduct_credit_shim is a
    verbatim copy of production's body; called for a user with ZERO credits it
    charges nothing yet returns 0 -- and 0 is not < 0, so consume()'s only
    failure check could never fire. That single missing minus sign is the
    whole defect."""
    import shared.deps as deps

    uid = make_user(0)
    got = deps._get_supa().rpc("deduct_credit", {"p_user_id": uid}).execute().data

    assert got == 0, f"expected the vulnerable contract to report 0, got {got}"
    assert got >= 0, (
        "deduct_credit never returns a negative -- so `if preostalo < 0` in consume() "
        "was unreachable and the 402 could never fire"
    )
    assert _balance(pg_dsn, uid) == 0, "nothing was charged, yet the return value said success"

    # Contrast: the function consume() now uses gets the identical case right.
    assert _deduct(pg_dsn, uid, 1) == -1


@pytest.mark.anyio
async def test_consume_never_calls_deduct_credit_for_any_amount(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """Structural half of CREDIT-CONSUME-001: there must be exactly ONE
    charging primitive. Two primitives with different return contracts is
    what produced the defect."""
    import shared.deps as deps
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(1, 1))

    called = []
    real_shim = deps._get_supa()

    class _Spy:
        def rpc(self, name, params):
            called.append(name)
            return real_shim.rpc(name, params)

    monkeypatch.setattr(deps, "_get_supa", lambda: _Spy())

    uid = make_user(5)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "ai_pravna_pitanja")

    assert "deduct_credit" not in called, f"consume() must not use deduct_credit: {called}"
    assert "deduct_n_credits" in called
    assert _balance(pg_dsn, uid) == 4


@pytest.mark.anyio
async def test_refund_with_explicit_credits_cannot_mint(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """CREDIT-REFUND-002 (HIGH) regression. A caller that charged at an
    explicit multiplier=1 against a registry credit_multiplier of 6 (exactly
    what routers/strategija.py does) previously got 6 credits back for a
    1-credit charge -- minting 5 per failure."""
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(1, 6))

    uid = make_user(20)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=1)
    assert _balance(pg_dsn, uid) == 19, "charged exactly 1"

    # The safe call form: refund exactly what was charged.
    await usage.UsageService.refund(uid, "advokat@vindex.rs", "strategija", credits=1)
    assert _balance(pg_dsn, uid) == 20, "refund must not mint"

    # And the matching-multiplier form is equally exact.
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=1)
    await usage.UsageService.refund(uid, "advokat@vindex.rs", "strategija", multiplier=1)
    assert _balance(pg_dsn, uid) == 20


@pytest.mark.anyio
async def test_concurrent_consume_through_real_python_path_cannot_overdraw(pg_dsn, make_user, monkeypatch, consume_against_real_db):
    """The full stack under contention: 20 concurrent UsageService.consume()
    calls for a 12-credit feature against a 60-credit balance. At most 5 may
    be granted; everything else must 402; the balance must reconcile exactly.

    This is the assertion that would have caught the production gap: it fails
    against the legacy body no matter what the mocks say."""
    import asyncio as _asyncio
    from fastapi import HTTPException
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    uid = make_user(60)

    async def one():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
            return "SUCCESS"
        except HTTPException as e:
            return "INSUFFICIENT" if e.status_code == 402 else f"ERROR:{e.status_code}"
        except Exception as e:
            return f"ERROR:{type(e).__name__}"

    results = await _asyncio.gather(*[one() for _ in range(20)])

    granted = results.count("SUCCESS")
    assert all(r in ("SUCCESS", "INSUFFICIENT") for r in results), f"unexpected: {results}"
    assert granted <= 5, f"{granted} grants funded by 60 credits at 12 each"
    assert _balance(pg_dsn, uid) == 60 - 12 * granted
    assert _balance(pg_dsn, uid) >= 0


# ═══════════════════════════════════════════════════════════════════════════
# INV-006 — a REJECTED charge must never consume monthly quota
# ═══════════════════════════════════════════════════════════════════════════
# The consume_against_real_db fixture stubs _increment_monthly_usage to a
# no-op, which is right for the balance-accounting tests above but means no
# test in this file ever observed it. That left INV-006 proven only by a
# mocked unit test (test_beta_gate_credit_race.py::test_deps_deduct_n_credits_
# propagates_insufficient_sentinel), which asserts what the code intends
# rather than what the database does.
#
# The failure it guards against is not theoretical: monthly usage is what
# enforces mesecni_limit. If a 402'd request still burned a month-slot, a user
# who ran out of credits mid-month would ALSO lose monthly allowance they never
# received anything for -- charged twice for nothing, in two different
# currencies.

@pytest.mark.anyio
async def test_INV006_rejected_charge_does_not_consume_monthly_quota(
    pg_dsn, make_user, monkeypatch, consume_against_real_db
):
    from fastapi import HTTPException
    import shared.deps as deps
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    seen: list[str] = []
    monkeypatch.setattr(deps, "_increment_monthly_usage", lambda uid, *a, **k: seen.append(uid))

    uid = make_user(5)  # 5 < 12 required — the real RPC will return -1
    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")

    assert exc.value.status_code == 402
    assert _balance(pg_dsn, uid) == 5, "money untouched"
    assert seen == [], (
        "a charge the database refused must not consume monthly quota — "
        f"_increment_monthly_usage was called {len(seen)} time(s)"
    )


@pytest.mark.anyio
async def test_INV006_accepted_charge_does_consume_monthly_quota(
    pg_dsn, make_user, monkeypatch, consume_against_real_db
):
    """The other half — without this, INV-006 could be satisfied by never
    incrementing monthly usage at all, and mesecni_limit would stop working."""
    import shared.deps as deps
    import shared.usage as usage
    monkeypatch.setattr(usage, "get_policy", consume_against_real_db(2, 6))

    seen: list[str] = []
    monkeypatch.setattr(deps, "_increment_monthly_usage", lambda uid, *a, **k: seen.append(uid))

    uid = make_user(20)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")

    assert _balance(pg_dsn, uid) == 8
    assert seen == [uid], "a successful charge must consume exactly one month-slot"
