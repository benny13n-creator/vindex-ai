# -*- coding: utf-8 -*-
"""
Beta Gate Credit System Closure — second-order audit regressions.

Findings SOA-003, SOA-004, SOA-006, SOA-009, SOA-012, SOA-016. Each is a way
the credit system charged a user for nothing, or hid a paywall behind a
generic 500, or left a re-runnable SQL file that would undo a security
migration.
"""
import ast
import inspect
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── SOA-003 / SOA-004: re-runnable SQL must not undo the lockdown ───────────

def test_setup_sql_no_longer_grants_deduct_credit_to_authenticated():
    """supabase_setup.sql is the file shared/deps.py tells operators to re-run
    when credits look broken. It used to end with
        GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO authenticated;
    which is precisely the live exploit migration 102 exists to close: any
    logged-in user could POST /rest/v1/rpc/deduct_credit with a VICTIM's uuid
    and drain that account. One re-run would silently reopen it."""
    sql = (REPO_ROOT / "supabase_setup.sql").read_text(encoding="utf-8")
    executable = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    assert "GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO authenticated" not in executable
    assert "REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM authenticated" in executable
    assert "REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM anon" in executable


def test_only_one_deduct_credit_definition_exists_in_the_repo():
    """supabase_migration.sql defined a SECOND deduct_credit with the same
    signature but against public.profiles (not user_credits) and a different
    sentinel. Whichever file ran last won; if that one had, user_credits was
    never decremented for anyone and the product was free."""
    defining = []
    for path in list(REPO_ROOT.glob("*.sql")) + list((REPO_ROOT / "migrations").glob("*.sql")):
        executable = "\n".join(
            l for l in path.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith("--")
        )
        if "CREATE OR REPLACE FUNCTION public.deduct_credit" in executable:
            defining.append(path.name)
    assert defining == ["supabase_setup.sql"], (
        f"exactly one file may define deduct_credit, found: {defining}"
    )


def test_only_one_deduct_n_credits_definition_exists_in_the_repo():
    defining = []
    for path in list(REPO_ROOT.glob("*.sql")) + list((REPO_ROOT / "migrations").glob("*.sql")):
        executable = "\n".join(
            l for l in path.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith("--")
        )
        if "CREATE OR REPLACE FUNCTION public.deduct_n_credits" in executable:
            defining.append(path.name)
    assert defining == ["107_beta_gate_credit_race_closure.sql"], (
        f"deduct_n_credits must have exactly one definition, found: {defining}"
    )


# ── SOA-006: prompt-guard block charged and never refunded ──────────────────

def test_prompt_guard_block_refunds_the_credit():
    """The guard-blocked branch is a NORMAL return, so neither except handler
    runs and it sits above the cache-hit refund check -- the credit consumed
    moments earlier was simply kept, for zero AI work."""
    import api

    src = inspect.getsource(api.pitanje)
    head, _, tail = src.partition("if _guard_result.blocked:")
    assert tail, "guard-blocked branch not found"
    blocked_branch = tail.split("return greska_odgovor(400")[0]
    assert "UsageService.refund" in blocked_branch, (
        "a prompt-guard rejection does no AI work and must refund the credit"
    )
    assert "_credit_consumed = False" in blocked_branch, (
        "must clear the flag so the except handlers cannot double-refund"
    )


# ── SOA-012: SSE client disconnect skipped the refund entirely ──────────────

def test_stream_refunds_on_client_disconnect():
    """Starlette closes the generator on disconnect, raising GeneratorExit /
    CancelledError -- BaseException, not Exception -- so every refund path
    was skipped. Closing the tab on a slow answer cost a credit for nothing."""
    import api

    src = inspect.getsource(api.pitanje_stream)
    assert "except BaseException:" in src, (
        "an except BaseException handler is required; except Exception cannot "
        "catch GeneratorExit/CancelledError"
    )
    base_branch = src.split("except BaseException:")[1]
    assert "UsageService.refund" in base_branch
    assert "raise" in base_branch, "must re-raise -- cancellation must not be swallowed"


def test_stream_refund_is_idempotent_across_all_three_paths():
    """Adding the BaseException handler must not create a double refund."""
    import api

    src = inspect.getsource(api.pitanje_stream)
    assert "_refunded = False" in src
    # UPDATED by NIGHT-005 (2026-08-09). The BaseException (disconnect) handler
    # is now guarded by `if not _refunded and not _delivered:` rather than
    # `if not _refunded:`, so the literal count dropped to 1 and this assertion
    # started failing on a STRICTER version of the code.
    #
    # The reason for the extra condition: on the SUCCESS path _refunded was
    # still False when the disconnect handler ran, so a client that read the
    # whole answer and then dropped the connection before [DONE] received the
    # full gpt-4o answer AND got its credit back — repeatable at the 10/min
    # limit, with refund_n_credits having no cap and no link to a charge.
    #
    # What this test is actually for — no double refund — is unchanged, so
    # assert that property instead of one particular spelling of it.
    # UPDATED by BETA-HARDENING-002 (2026-08-13).
    #
    # Counting exact guard literals broke when the Exception branch grew a
    # second condition (`_refund_dugovan`), added because the `not _delivered`
    # guard from SE-007 was ALSO suppressing a legitimate refund retry: on a
    # cache hit or `status == "error"` the first refund() can fail, `_refunded`
    # stays False, and the handler then refused to try again because the answer
    # had been delivered. The user stayed charged for a cached/failed answer.
    #
    # The invariant is unchanged — no double refund — so it is now asserted as
    # a PROPERTY: every branch that calls refund() must be guarded by
    # `_refunded`. That survives future edits to the other conditions.
    import re as _re
    _grane = [g for g in _re.findall(r"if not _refunded[^\n:]*:", src)]
    assert len(_grane) >= 2, (
        "both the Exception and BaseException handlers must be guarded by the "
        f"_refunded flag; found {len(_grane)} guarded branches: {_grane}"
    )
    # And every refund call site inside the generator must sit under such a
    # guard or under the success-path condition — never unguarded.
    assert "await UsageService.refund" in src
    assert src.count("_refunded = True") >= 3, (
        "each refund path must mark _refunded, or the next handler will refund again"
    )

    # NOTE (NIGHT-005 lesson, kept deliberately): the old assertion here was
    # `assert "_delivered = True" in src` — a STRING-PRESENCE check. It passed
    # for months while the flag was assigned AFTER the chunk loop, where a
    # disconnected client never reached it, handing out full answers for free.
    # The behavioural proof now lives in tests/test_beta_hardening_001.py, which
    # drives the real generator and disconnects at 1/25/50/75/90/98/99%.
    assert "_delivered = True" in src, (
        "the disconnect handler must be able to tell a pre-delivery abort from "
        "a post-delivery one; POSITION is proven in test_beta_hardening_001.py"
    )


def test_stream_does_not_hardcode_plus_one_for_refund_display():
    """SOA-016: the displayed balance was `preostalo + 1`, wrong for any
    feature priced above 1 credit."""
    import api

    src = inspect.getsource(api.pitanje_stream)
    assert "preostalo = preostalo + 1" not in src
    assert "UsageService.balance" in src, "read the real balance instead of guessing"


# ── SOA-009: genuine 402/429 masked as a generic 500 ────────────────────────

def _masking_sites_without_guard(path: Path):
    """Finds `except Exception` handlers that raise HTTPException(500) with no
    preceding `except HTTPException: raise` in the same try statement."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        names = []
        for h in node.handlers:
            n = ""
            if isinstance(h.type, ast.Name):
                n = h.type.id
            elif isinstance(h.type, ast.Tuple):
                n = ",".join(e.id for e in h.type.elts if isinstance(e, ast.Name))
            names.append(n)
        for idx, h in enumerate(node.handlers):
            if names[idx] != "Exception":
                continue
            raises500 = any(
                isinstance(s, ast.Raise) and "500" in ast.dump(s) for s in ast.walk(h)
            )
            if raises500 and "HTTPException" not in names[:idx]:
                bad.append(h.lineno)
    return bad


@pytest.mark.parametrize("relpath", ["routers/strategija.py", "routers/web3.py"])
def test_consume_402_is_not_masked_as_500(relpath):
    """HTTPException subclasses Exception, so consume()'s 402 NO_CREDITS /
    429 COOLDOWN was converted to 500 and the frontend paywall (which keys on
    402) never fired -- while the cooldown claim had already been spent."""
    bad = _masking_sites_without_guard(REPO_ROOT / relpath)
    assert bad == [], (
        f"{relpath}: `except Exception` -> HTTPException(500) with no preceding "
        f"`except HTTPException: raise` at lines {bad}"
    )
