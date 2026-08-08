-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration: smart_contract_analyses table + deduct_n_credits RPC
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. smart_contract_analyses TABLE ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.smart_contract_analyses (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  contract_source   TEXT        NOT NULL,
  contract_name     TEXT,
  solidity_version  TEXT,
  analysis_result   JSONB,
  is_proxy_detected BOOLEAN     NOT NULL DEFAULT FALSE,
  confidence_tier   TEXT        CHECK (confidence_tier IN ('HIGH','MEDIUM','LOW','INSUFFICIENT')),
  tokens_used       INTEGER     DEFAULT 0
);

ALTER TABLE public.smart_contract_analyses ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'smart_contract_analyses'
      AND policyname = 'Korisnici citaju sopstvene analize ugovora'
  ) THEN
    CREATE POLICY "Korisnici citaju sopstvene analize ugovora"
      ON public.smart_contract_analyses FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'smart_contract_analyses'
      AND policyname = 'Korisnici brisu sopstvene analize ugovora'
  ) THEN
    CREATE POLICY "Korisnici brisu sopstvene analize ugovora"
      ON public.smart_contract_analyses FOR DELETE
      USING (auth.uid() = user_id);
  END IF;
END $$;

GRANT SELECT, INSERT, DELETE ON public.smart_contract_analyses TO service_role;


-- ─── 2. deduct_n_credits RPC — SUPERSEDED, DEFINITION MOVED ──────────────────
--
-- ⚠ THE AUTHORITATIVE DEFINITION OF deduct_n_credits IS NOW
--   migrations/107_beta_gate_credit_race_closure.sql
--
-- History (recorded accurately rather than rewritten):
--
-- This file was first applied on 2026-06-11 and originally defined
-- deduct_n_credits with an unguarded body:
--
--     UPDATE public.user_credits
--       SET credits_remaining = GREATEST(0, credits_remaining - p_n)
--     WHERE user_id = p_user_id
--     RETURNING credits_remaining INTO new_balance;
--     RETURN COALESCE(new_balance, 0);
--
-- That body has no balance predicate, so it succeeds unconditionally and
-- floors at zero — concurrent requests at exhaustion each read a
-- non-negative return and are all treated as charged (Final Beta Gate
-- finding F5, CRITICAL).
--
-- On 2026-08-08 the Beta Gate fix was written by EDITING THIS FILE IN PLACE.
-- That was the wrong mechanism: this migration had already been applied two
-- months earlier, so editing it produced no new artifact for the operator to
-- run, and the fix never reached production. Read-only catalog verification
-- on 2026-08-08 proved the original unguarded body was still live.
--
-- The executable definition has therefore been REMOVED from this file rather
-- than corrected in place, for two reasons:
--   1. this file must continue to reflect what was actually applied on
--      2026-06-11 — it is a historical record, not a live spec;
--   2. leaving ANY deduct_n_credits definition here is an active hazard: on a
--      fresh rebuild, filename ordering puts "107_…" BEFORE
--      "smart_contract_analyses.sql", so a definition here would silently
--      overwrite the fixed one and reintroduce the vulnerability.
--
-- The table in section 1 above is unchanged and remains the purpose of this
-- migration.
