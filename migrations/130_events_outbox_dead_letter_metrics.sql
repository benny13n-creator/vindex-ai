-- ============================================================================
-- Migration 130 -- events_outbox_metrics: dead-letter observability
--
-- RENUMBERED (Wave 2 mainline integration, 2026-09-20): authored and
-- production-applied as migration 129 on the isolated Wave 2 branch
-- (v1-wave2-case-evolution-integrity). origin/main independently reached
-- 129 for an unrelated migration (129_hronologija_vrsta_stanje.sql, Z016.2)
-- during the ~99 commits this branch diverged from main -- same number,
-- different content, both already applied to production at different
-- times. Renumbered to 130 here to integrate onto current main without a
-- collision. SQL body byte-identical to the original 129; already applied
-- to production under that number -- CREATE OR REPLACE is idempotent, so
-- re-running this file (now under 130) is a safe no-op reconciliation, not
-- a destructive recreate.
--
-- VINDEX AI V1, Wave 2, Task 2A (VINDEX-V1-EXECUTION-CONTRACT.md).
--
-- PROVEN PROBLEM (Wave 1 investigation): services/event_bus.py marks a
-- terminally failed event (dispatch exhausted after MAX_DISPATCH_ATTEMPTS,
-- see DEAD_LETTER_MARKER in services/event_bus.py) with `dispatched_at` SET
-- -- the poller stops retrying it -- and `last_error` carrying an explicit
-- "DEAD_LETTER after N attempts: ..." prefix. The ORIGINAL version of this
-- view (migration 073) computed every metric off `dispatched_at IS NULL`:
--   - undispatched_backlog / oldest_undispatched_at / events_with_errors all
--     EXCLUDED dead-lettered rows (their dispatched_at is set).
--   - avg_dispatch_latency_s INCLUDED them, silently inflating "successful
--     dispatch latency" with rows that never actually succeeded.
-- Net effect: a permanently failed Case Evolution consequence (genome
-- refresh, case_actions reconciliation, notification projection -- any
-- registered consequence) was indistinguishable from a clean dispatch on
-- the only operational surface for this queue (GET /api/smart-intake/
-- admin/health -> shared/intake_queue.py::get_outbox_metrics()).
--
-- FIX: classify each row into exactly the three categories
-- services/event_bus.py::classify_outbox_event() also computes in Python
-- (PENDING_RETRYABLE / SUCCESS / DEAD_LETTER), using the same
-- DEAD_LETTER_MARKER text ("DEAD_LETTER") that function's own docstring
-- documents as the single sync point between this SQL and that Python
-- classifier. If the marker text ever changes in event_bus.py, this view
-- must change with it.
--
-- Existing field NAMES and their MEANING for already-pending/backlog rows
-- are preserved unchanged (no consumer of undispatched_backlog/
-- oldest_undispatched_at needs to change). Two existing fields had their
-- SQL corrected in place because their current name already promises a
-- semantics the old SQL did not deliver:
--   - avg_dispatch_latency_s: name promises "successful dispatch latency"
--     -- now actually excludes dead-lettered rows instead of silently
--     averaging them in as if they were fast successes.
--   - events_with_errors: now counts dispatch_attempts > 0 regardless of
--     dispatched_at, so a dead-lettered row (which by definition has
--     dispatch_attempts > 0) is no longer excluded merely because
--     dispatched_at got set to stop the poller.
-- New fields are added (dead_letter_count, oldest_dead_letter_at) rather
-- than repurposing an existing name, per Wave 2 Task 2A's own instruction
-- to prefer narrowly-named additions over silently changing an unrelated
-- meaning.
-- ============================================================================

CREATE OR REPLACE VIEW public.events_outbox_metrics AS
SELECT
    count(*) FILTER (WHERE dispatched_at IS NULL)                             AS undispatched_backlog,
    min(created_at) FILTER (WHERE dispatched_at IS NULL)                      AS oldest_undispatched_at,

    -- Corrected: only rows that actually reached a real handler success
    -- (dispatched_at set AND not a dead-letter) count toward "successful
    -- dispatch latency". A dead-lettered row no longer masquerades as a
    -- fast success.
    avg(extract(epoch FROM (dispatched_at - created_at)))
        FILTER (
            WHERE dispatched_at IS NOT NULL
              AND (last_error IS NULL OR last_error NOT LIKE 'DEAD_LETTER%')
        )                                                                     AS avg_dispatch_latency_s,

    -- Corrected: previously required dispatched_at IS NULL, which silently
    -- excluded every dead-lettered row (dispatch_attempts > 0 is exactly
    -- what makes a row eligible for dead-lettering in the first place).
    -- Now counts any row that has ever recorded a dispatch error, whether
    -- still retrying or terminally failed.
    count(*) FILTER (WHERE dispatch_attempts > 0)                             AS events_with_errors,

    -- New: explicit terminal-failure visibility. This is the field Task 2A
    -- exists to add -- an operator (or an automated alert) can now detect
    -- dead-letter presence from this one view without querying raw events
    -- rows.
    count(*) FILTER (WHERE last_error LIKE 'DEAD_LETTER%')                    AS dead_letter_count,
    min(created_at) FILTER (WHERE last_error LIKE 'DEAD_LETTER%')             AS oldest_dead_letter_at
FROM public.events;

COMMENT ON VIEW public.events_outbox_metrics IS
    'Outbox backlog, dispatch latencija i terminal-failure vidljivost -- ADR-0001 postoji specifično da spreči gubitak događaja; ovaj view je kako se to proverava u produkciji, ne samo veruje na reč. Wave 2 Task 2A (2026-09-19): dead_letter_count/oldest_dead_letter_at dodati, avg_dispatch_latency_s i events_with_errors ispravljeni da terminalno mrtav red vise ne izgleda kao uspesan dispatch. last_error LIKE ''DEAD_LETTER%'' mora ostati u sinhronizaciji sa services/event_bus.py::DEAD_LETTER_MARKER.';
