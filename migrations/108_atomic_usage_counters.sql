-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 108
-- Atomic usage counters: close the read-modify-write races on the counters
-- that ENFORCE daily/monthly limits.
--
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run. Function definitions and privileges only —
-- NO schema changes; every constraint this relies on already exists.
-- ═══════════════════════════════════════════════════════════════════════════
--
-- WHY (findings B1/B2/B3, second-order audit 2026-08-08)
--
-- shared/usage.py::_increment_usage did:
--     SELECT broj_koriscenja  →  UPDATE broj_koriscenja = <read value> + 1
-- as two separate PostgREST round-trips. Two concurrent calls for the same
-- (user_id, feature_key, dan) both read N and both write N+1 — one use is
-- lost, permanently, in the user's favour.
--
-- That counter is not cosmetic. It is what `dnevni_limit` / `mesecni_limit`
-- are checked against, and for the two features priced at ZERO credits it is
-- the ONLY budget protection that exists:
--     copilot_ambient   dnevni_limit = 200, krediti = 0   (migration 083)
--     morning_briefing  dnevni_limit = 5,   krediti = 0   (migration 064)
-- A lawyer running the Word add-in and the browser at once systematically
-- undercounts and walks past the cap.
--
-- The INSERT branch was worse: on the day's first call, two concurrent
-- requests both saw no row and both INSERTed; one hit
-- UNIQUE (user_id, feature_key, dan) and the 23505 was swallowed by a bare
-- `except Exception` and logged non-fatal — that call was never counted at all.
--
-- Separately (B2) the limit CHECK was itself check-then-act: read at the top
-- of consume(), increment ~one AI call later. Everything in between — the
-- credit deduction and the whole LLM operation — sat inside the window.
--
-- Both are fixed here by making check-and-increment ONE statement, the same
-- shape migration 107 used for deduct_n_credits.


-- ─── 1. increment_feature_usage — atomic check + increment ──────────────────
--
-- CONTRACT (mirrors deduct_n_credits deliberately, so there is one convention):
--
--   returns >= 0  →  COUNTED. Value is the new broj_koriscenja for today.
--   returns  -1   →  NOT COUNTED, because the daily limit is already reached.
--                    Caller must reject the request.
--
--   p_dnevni_limit IS NULL  →  no limit; always counts.
--
-- ATOMICITY: a single INSERT ... ON CONFLICT DO UPDATE. The conflict target
-- UNIQUE (user_id, feature_key, dan) already exists (migration 064). The
-- WHERE on the DO UPDATE branch is evaluated by Postgres against the
-- CURRENT committed row while holding the row lock, so a concurrent caller
-- that would push the count past the limit matches zero rows and gets -1.
-- There is no window between "check" and "increment" because there is no
-- separate check.
--
-- NOTE ON THE INSERT PATH: a brand-new row is created with broj_koriscenja=1
-- unconditionally. That is correct — the first use of the day can never
-- exceed a positive limit — and it removes the swallowed-23505 hole, because
-- a losing concurrent INSERT now falls into DO UPDATE instead of erroring.

CREATE OR REPLACE FUNCTION public.increment_feature_usage(
    p_user_id        UUID,
    p_feature        TEXT,
    p_dan            DATE,
    p_mesec          TEXT,
    p_credits        DOUBLE PRECISION DEFAULT 0,
    p_dnevni_limit   INTEGER DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_count INTEGER;
BEGIN
  INSERT INTO public.feature_usage
        (user_id, feature_key, dan, mesec, broj_koriscenja, krediti_potroseni)
  VALUES (p_user_id, p_feature, p_dan, p_mesec, 1, COALESCE(p_credits, 0))
  ON CONFLICT (user_id, feature_key, dan) DO UPDATE
     SET broj_koriscenja   = public.feature_usage.broj_koriscenja + 1,
         krediti_potroseni = COALESCE(public.feature_usage.krediti_potroseni, 0)
                             + COALESCE(EXCLUDED.krediti_potroseni, 0)
   WHERE p_dnevni_limit IS NULL
      OR public.feature_usage.broj_koriscenja < p_dnevni_limit
  RETURNING public.feature_usage.broj_koriscenja INTO new_count;

  IF NOT FOUND THEN
    RETURN -1;          -- limit already reached; nothing was counted
  END IF;

  RETURN new_count;
END;
$$;


-- ─── 2. increment_monthly_usage — atomic monthly counter on user_credits ────
--
-- Finding B3. shared/deps.py::_increment_monthly_usage read
-- (mesecno_korisceno, mesec) and wrote back read+1 — the same lost-update
-- shape, on every successful charge.
--
-- Currently informational: its only reader is require_credits, which has zero
-- Depends() call sites (verified by grep). Fixed anyway because it is a trap —
-- the moment anyone re-adopts require_credits or surfaces the number in an
-- admin panel it becomes an enforced gate backed by a lossy counter, and the
-- undercount is always in the user's favour.
--
-- Returns the new count, or -1 when no user_credits row exists.

CREATE OR REPLACE FUNCTION public.increment_monthly_usage(
    p_user_id UUID,
    p_mesec   TEXT
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_count INTEGER;
BEGIN
  UPDATE public.user_credits
     SET mesecno_korisceno = CASE WHEN mesec IS NOT DISTINCT FROM p_mesec
                                  THEN COALESCE(mesecno_korisceno, 0) + 1
                                  ELSE 1 END,
         mesec             = p_mesec,
         updated_at        = NOW()
   WHERE user_id = p_user_id
  RETURNING mesecno_korisceno INTO new_count;

  IF NOT FOUND THEN
    RETURN -1;
  END IF;

  RETURN new_count;
END;
$$;


-- ─── 3. Privilege lockdown ──────────────────────────────────────────────────
-- Same pattern as migrations 102 and 107. Without these, a newly created
-- function inherits Postgres's EXECUTE-to-PUBLIC default, which would let any
-- authenticated user inflate or manipulate their own usage counters directly
-- through PostgREST.

REVOKE ALL ON FUNCTION public.increment_feature_usage(UUID, TEXT, DATE, TEXT, DOUBLE PRECISION, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.increment_feature_usage(UUID, TEXT, DATE, TEXT, DOUBLE PRECISION, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.increment_feature_usage(UUID, TEXT, DATE, TEXT, DOUBLE PRECISION, INTEGER) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.increment_feature_usage(UUID, TEXT, DATE, TEXT, DOUBLE PRECISION, INTEGER) TO service_role;

REVOKE ALL ON FUNCTION public.increment_monthly_usage(UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.increment_monthly_usage(UUID, TEXT) FROM anon;
REVOKE ALL ON FUNCTION public.increment_monthly_usage(UUID, TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.increment_monthly_usage(UUID, TEXT) TO service_role;


-- ─── 4. POST-MIGRATION VERIFICATION (read-only, run separately) ─────────────
--   SELECT proname, proacl::text
--     FROM pg_proc
--    WHERE proname IN ('increment_feature_usage','increment_monthly_usage');
-- Expected: proacl shows only the owner and service_role — no PUBLIC entry.
