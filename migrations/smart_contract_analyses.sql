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


-- ─── 2. deduct_n_credits RPC ──────────────────────────────────────────────────
-- Atomically deducts p_n credits for a user IF AND ONLY IF the balance covers
-- it (matches deduct_credit's own WHERE-guard pattern). Used by every
-- multiplier feature (strategija 6-module, multi_agent, strategy_simulator,
-- digital_twin, smart contract analyzer, ...).
--
-- FIX (Final Beta Gate F5, CRITICAL): the prior version had NO WHERE guard —
-- it always succeeded via GREATEST(0, ...) regardless of balance, so two
-- concurrent requests near/at exhaustion could both "succeed" (free AI
-- usage under this app's real 4-gunicorn-worker topology). The guard below
-- makes the UPDATE itself atomically conditional on sufficient balance; the
-- Python caller (shared/deps.py::_deduct_n_credits) MUST treat a -1 return
-- as "not charged, insufficient balance" — never trust a floor-at-0 value
-- as proof of success.

CREATE OR REPLACE FUNCTION public.deduct_n_credits(p_user_id UUID, p_n INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  new_balance INTEGER;
BEGIN
  UPDATE public.user_credits
    SET credits_remaining = credits_remaining - p_n
  WHERE user_id = p_user_id
    AND credits_remaining >= p_n
  RETURNING credits_remaining INTO new_balance;

  IF NOT FOUND THEN
    RETURN -1;
  END IF;

  RETURN new_balance;
END;
$$;

GRANT EXECUTE ON FUNCTION public.deduct_n_credits(UUID, INTEGER) TO service_role;
