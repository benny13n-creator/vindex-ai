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
-- Atomically deducts p_n credits for a user, floor at 0.
-- Used by smart contract analyzer (5 credits per analysis).

CREATE OR REPLACE FUNCTION public.deduct_n_credits(p_user_id UUID, p_n INTEGER)
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

GRANT EXECUTE ON FUNCTION public.deduct_n_credits(UUID, INTEGER) TO service_role;
