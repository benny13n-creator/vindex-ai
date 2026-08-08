# -*- coding: utf-8 -*-
"""
Beta Gate Credit System Closure — CREDIT-DEBUG-001 (CRITICAL).

GET /api/credits-debug is guarded only by Depends(get_current_user) — any
authenticated user, no rate limit — and it used to:

    1. read the balance via _ensure_profile()            (step 4)
    2. call deduct_credit(), a REAL -1 deduction         (step 5)
    3. blind-write credits_remaining = <value from 1>    (step 5 "restore")

Step 3 is an absolute write of a stale read: a lost update by construction.
Any charge committed between (1) and (3) was erased, so looping this endpoint
while running expensive AI operations restored the pre-charge balance
indefinitely — unlimited free AI usage, no authentication bypass required.
It also destroyed credits: when step 4 raised, `profil` was unbound, the
write raised NameError inside a bare `except: pass`, and the caller silently
lost one credit per invocation.

Fixed by replacing the destructive probe with deduct_n_credits(uid, 0),
which migration 107 rejects via its own `p_n <= 0` guard: returns -1 and
mutates nothing.

These tests pin BOTH properties:
  * the endpoint performs no write to user_credits, ever;
  * it calls no deducting RPC.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _RecordingSupa:
    """Records every table mutation and every RPC the endpoint attempts."""

    def __init__(self, rpc_return=-1):
        self.mutations = []
        self.rpc_calls = []
        self._rpc_return = rpc_return

    def table(self, name):
        rec = self.mutations
        outer = self

        class _T:
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def single(self, *a, **k): return self
            def maybe_single(self, *a, **k): return self

            def update(self, payload):
                rec.append(("update", name, payload))
                return self

            def insert(self, payload):
                rec.append(("insert", name, payload))
                return self

            def upsert(self, payload, **k):
                rec.append(("upsert", name, payload))
                return self

            def execute(self):
                r = MagicMock()
                r.data = [{"id": "x", "credits_remaining": 15}]
                return r

        return _T()

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        outer = self

        class _C:
            def execute(self_inner):
                r = MagicMock()
                r.data = outer._rpc_return
                return r

        return _C()


@pytest.mark.anyio
async def test_credits_debug_never_writes_to_user_credits():
    import api

    supa = _RecordingSupa(rpc_return=-1)

    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_ensure_profile", return_value={"credits_remaining": 15, "is_pro": False}):
        await api.credits_debug(user={"user_id": "u1", "email": "a@b.rs"})

    credit_writes = [m for m in supa.mutations if m[1] == "user_credits" and m[0] in ("update", "upsert", "insert")]
    assert credit_writes == [], (
        f"credits-debug must never mutate user_credits, got: {credit_writes}"
    )


@pytest.mark.anyio
async def test_credits_debug_never_calls_a_deducting_rpc():
    import api

    supa = _RecordingSupa(rpc_return=-1)

    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_ensure_profile", return_value={"credits_remaining": 15}):
        await api.credits_debug(user={"user_id": "u1", "email": "a@b.rs"})

    called = [name for name, _ in supa.rpc_calls]
    assert "deduct_credit" not in called, "deduct_credit ALWAYS deducts — never safe as a probe"
    assert "deduct_n_credits" in called, "expected the non-destructive p_n=0 probe"
    params = dict(supa.rpc_calls[[n for n, _ in supa.rpc_calls].index("deduct_n_credits")][1])
    assert params["p_n"] == 0, f"probe must request zero credits, got {params}"


@pytest.mark.anyio
async def test_credits_debug_reports_ok_when_migration_107_is_applied():
    """Guarded body returns -1 for p_n=0."""
    import api

    supa = _RecordingSupa(rpc_return=-1)
    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_ensure_profile", return_value={"credits_remaining": 15}):
        out = await api.credits_debug(user={"user_id": "u1", "email": "a@b.rs"})

    assert "OK" in out["credit_rpc"]
    assert "107" in out["credit_rpc"]


@pytest.mark.anyio
async def test_credits_debug_detects_unapplied_migration_107():
    """The pre-107 body returns the (floored) balance for p_n=0, not -1. The
    endpoint must surface that as CRITICAL rather than 'OK' -- this is the
    application-visible contract-drift detector whose absence allowed a
    vulnerable function body to live in production while CI stayed green."""
    import api

    supa = _RecordingSupa(rpc_return=15)   # old body: returns balance, never -1
    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_ensure_profile", return_value={"credits_remaining": 15}):
        out = await api.credits_debug(user={"user_id": "u1", "email": "a@b.rs"})

    assert "KRITIČNO" in out["credit_rpc"]
    assert any("107" in d for d in out["dijagnoza"]), out["dijagnoza"]


@pytest.mark.anyio
async def test_credits_debug_does_not_write_even_when_profile_lookup_fails():
    """The old code's worst path: _ensure_profile raises, `profil` is unbound,
    and the restore-write either wiped the balance to 0 or silently swallowed
    a NameError after a real deduction had already happened."""
    import api

    supa = _RecordingSupa(rpc_return=-1)
    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_ensure_profile", side_effect=RuntimeError("profile read failed")):
        out = await api.credits_debug(user={"user_id": "u1", "email": "a@b.rs"})

    credit_writes = [m for m in supa.mutations if m[1] == "user_credits"]
    assert credit_writes == [], f"must not write on the failure path either: {credit_writes}"
    assert "GREŠKA" in str(out["_ensure_profile"])


def test_credits_debug_source_has_no_absolute_credit_write():
    """Structural guard on EXECUTABLE lines only (the explanatory comment
    above the fix legitimately mentions the old pattern). The specific defect
    was an absolute `update({"credits_remaining": <stale read>})`; any write
    at all from this diagnostic endpoint is a regression."""
    import api

    executable = "\n".join(
        line for line in inspect.getsource(api.credits_debug).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert ".update(" not in executable, "credits-debug must perform no writes at all"
    assert '"credits_remaining":' not in executable, "must never assign credits_remaining"
    assert 'rpc("deduct_credit"' not in executable, "deduct_credit always deducts — unsafe as a probe"
    assert '"p_n": 0' in executable, "must use the non-destructive p_n=0 probe"
