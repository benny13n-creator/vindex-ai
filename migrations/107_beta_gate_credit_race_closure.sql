-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 107
-- Beta Gate Blocker Closure: atomic credit consumption + atomic credit refund
--
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run.
-- Contains no schema/table changes — function definitions and privileges only.
-- ═══════════════════════════════════════════════════════════════════════════
--
-- WHY THIS MIGRATION EXISTS (root cause, recorded honestly):
--
-- Final Beta Gate (2026-08-08) identified finding F5: deduct_n_credits had no
-- balance guard, allowing concurrent requests to consume more credits than a
-- user holds. The fix was written — but it was written by EDITING
-- migrations/smart_contract_analyses.sql, a migration first applied on
-- 2026-06-11. Editing an already-applied migration in place means there is no
-- new artifact for the operator to run, so the fix never reached production.
-- Read-only catalog verification on 2026-08-08 confirmed the vulnerable body
-- was still live:
--
--     SET credits_remaining = GREATEST(0, credits_remaining - p_n)
--     WHERE user_id = p_user_id            -- no balance predicate at all
--
-- This migration is the correction: a NEW, separately-numbered artifact.
-- smart_contract_analyses.sql has been restored to its as-applied 2026-06-11
-- content so migration history stays truthful; THIS file is the authoritative
-- definition of deduct_n_credits from 2026-08-08 onward.
--
--
-- SECOND FINDING CLOSED HERE (same invariant, different door):
--
-- shared/deps.py::_refund_one_credit calls rpc("refund_one_credit"), but that
-- function is defined in NO migration anywhere in this repository. Every
-- refund therefore fell through to the Python except-branch, which does a
-- non-atomic read-modify-write:
--     SELECT credits_remaining  →  UPDATE credits_remaining = <read value> + 1
-- Two concurrent refunds lose one credit (classic lost update). Worse, a
-- refund racing a deduction can overwrite the deduction entirely — the refund
-- writes back a balance it read BEFORE the charge, erasing it and yielding
-- free AI usage. That is the same accounting-invariant violation F5 describes,
-- reached through the refund path instead of the consume path.
--
-- Both refund functions below are defined atomically so that branch is never
-- taken again.


-- ─── 1. deduct_n_credits — atomic guarded consumption ───────────────────────
--
-- CONTRACT (established from the only production caller,
-- shared/usage.py::UsageService.consume via shared/deps.py::_deduct_n_credits):
--
--   returns >= 0  →  CHARGED. Value is the user's new balance.
--   returns  -1   →  NOT CHARGED. Caller must raise 402 and must not deliver
--                    the paid operation. Never a valid balance.
--
--   p_n IS NULL or p_n <= 0   → -1, zero mutation (non-positive consumption
--                               must never mutate credits; a negative p_n
--                               under the previous body would have INCREASED
--                               the balance).
--   no user_credits row       → -1, zero mutation (the previous body returned
--                               0 here, which the caller read as success).
--   balance < p_n             → -1, zero mutation.
--   balance >= p_n            → balance := balance - p_n, returns new balance.
--
-- ATOMICITY: the check and the deduction are ONE statement. Postgres takes a
-- row-level lock for the UPDATE; a concurrent updater blocks, and on unblock
-- (READ COMMITTED, via EvalPlanQual) re-evaluates the WHERE clause against the
-- COMMITTED-NEWEST row version. A request that would push the balance below
-- zero therefore fails the predicate on re-check and matches zero rows. There
-- is no window between "check sufficient" and "deduct" for another session to
-- occupy, because there is no separate check.
--
-- SECURITY DEFINER + explicit search_path: matches deduct_credit's own
-- hardening (supabase_setup.sql). The previous deduct_n_credits body had NO
-- search_path setting, which is a privilege-escalation vector for a
-- SECURITY DEFINER function.

CREATE OR REPLACE FUNCTION public.deduct_n_credits(p_user_id UUID, p_n INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_balance INTEGER;
BEGIN
  -- Non-positive / NULL consumption must never mutate credits.
  IF p_n IS NULL OR p_n <= 0 THEN
    RETURN -1;
  END IF;

  UPDATE public.user_credits
     SET credits_remaining = credits_remaining - p_n,
         updated_at        = NOW()
   WHERE user_id = p_user_id
     AND credits_remaining >= p_n
  RETURNING credits_remaining INTO new_balance;

  -- No row matched: either no such user, or insufficient balance.
  -- Both mean NOT CHARGED.
  IF NOT FOUND THEN
    RETURN -1;
  END IF;

  RETURN new_balance;
END;
$$;


-- ─── 2. refund_n_credits — atomic compensating credit return ────────────────
--
-- CONTRACT:
--   returns >= 0  →  refunded, value is the new balance
--   returns  -1   →  nothing refunded (no such user, or p_n <= 0)
--
-- Single-statement increment: no read-modify-write, so concurrent refunds and
-- refund/deduct interleavings cannot lose an update.

CREATE OR REPLACE FUNCTION public.refund_n_credits(p_user_id UUID, p_n INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_balance INTEGER;
BEGIN
  IF p_n IS NULL OR p_n <= 0 THEN
    RETURN -1;
  END IF;

  UPDATE public.user_credits
     SET credits_remaining = credits_remaining + p_n,
         updated_at        = NOW()
   WHERE user_id = p_user_id
  RETURNING credits_remaining INTO new_balance;

  IF NOT FOUND THEN
    RETURN -1;
  END IF;

  RETURN new_balance;
END;
$$;


-- ─── 3. refund_one_credit — the function the backend already calls ──────────
-- shared/deps.py::_refund_one_credit has called this since it was written; it
-- never existed. Defined here as a thin delegation so there is exactly one
-- refund implementation, not two that can drift.

CREATE OR REPLACE FUNCTION public.refund_one_credit(p_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN public.refund_n_credits(p_user_id, 1);
END;
$$;


-- ─── 4. Privilege lockdown ──────────────────────────────────────────────────
--
-- CREATE OR REPLACE FUNCTION preserves an existing function's ACL, so
-- migration 102's verified lockdown on deduct_n_credits survives section 1
-- above. The REVOKEs are re-asserted anyway (idempotent, costs nothing) so
-- this migration is self-sufficient on a fresh database, and so the two NEW
-- functions get the same treatment rather than inheriting Postgres's
-- EXECUTE-to-PUBLIC default.
--
-- Same pattern as migrations/102_lambda002_rpc_ownership_lockdown.sql.

REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.deduct_n_credits(UUID, INTEGER) TO service_role;

REVOKE ALL ON FUNCTION public.refund_n_credits(UUID, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.refund_n_credits(UUID, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.refund_n_credits(UUID, INTEGER) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.refund_n_credits(UUID, INTEGER) TO service_role;

REVOKE ALL ON FUNCTION public.refund_one_credit(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.refund_one_credit(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.refund_one_credit(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.refund_one_credit(UUID) TO service_role;


-- ─── 5. POST-MIGRATION VERIFICATION (read-only, run separately) ─────────────
-- Re-run QUERY A in docs/beta_gate/VERIFY_MIGRATIONS_102_103_READONLY.sql.
-- Required:
--   row '3 · F5 credit-race body'  →  PASS - balance guard deployed
--   all five '1 · mig102 privilege' rows  →  still PASS
--     (proves CREATE OR REPLACE did not reopen execute privileges)
