-- ============================================================================
-- Vindex AI — Migracija 049: Beta Readiness & Production Hardening Sprint
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 048.
--
-- Kreira / proširuje (dodavano fazno tokom sprinta — videti sekcije ispod):
--   Faza 3 — APR & Portal health:
--     1. portal_status_log — ALTER: result_kind, response_ms
--     2. praceni_predmeti  — ALTER: consecutive_failures (per-predmet backoff)
-- ============================================================================

-- ─── Faza 3.1 — Portal status log: podaci za health metrike ─────────────────

ALTER TABLE public.portal_status_log
    ADD COLUMN IF NOT EXISTS result_kind text
        CHECK (result_kind IN ('ok','unavailable','error')),
    ADD COLUMN IF NOT EXISTS response_ms int;

CREATE INDEX IF NOT EXISTS idx_status_log_kind_time
    ON public.portal_status_log (result_kind, created_at DESC);

-- ─── Faza 3.2 — Praćeni predmeti: per-predmet exponential backoff ────────────

ALTER TABLE public.praceni_predmeti
    ADD COLUMN IF NOT EXISTS consecutive_failures int NOT NULL DEFAULT 0;

-- ============================================================================
-- Provera (opciono)
-- SELECT result_kind, count(*) FROM public.portal_status_log
--   WHERE created_at > now() - interval '24 hours' GROUP BY 1;
-- SELECT id, consecutive_failures, current_status FROM public.praceni_predmeti
--   ORDER BY consecutive_failures DESC LIMIT 10;
-- ============================================================================
