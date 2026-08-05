-- Vindex AI — migration 096: Canonical Case Evolution Engine (Program Delta, Sprint 001)
--
-- Program Intake (Sprints 001-007) made document intake bulletproof.
-- Program Delta answers the next question: once a document (or any other
-- case-changing event) is accepted, what must AUTOMATICALLY happen next —
-- and who decides that, once, canonically, instead of scattered call sites
-- each independently deciding "what next."
--
-- This table is the ONE new piece of durable state the canonical engine
-- needs: per-(event, consequence) completion tracking, keyed off the
-- ALREADY-DURABLE Event Bus outbox row (public.events, migration 073) —
-- not a parallel event log. Reuses every existing primitive (durable
-- outbox, atomic claim, retry/dead-letter, correlation_id) rather than
-- rebuilding them; the only genuinely new concept is "did THIS consequence,
-- for THIS event, already complete" — a question the event dispatch layer
-- itself does not answer (it only knows "did every handler for this event
-- succeed," not per-consequence-within-a-handler granularity).

CREATE TABLE IF NOT EXISTS public.case_evolution_consequences (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id          UUID NOT NULL REFERENCES public.events(id),
    consequence_name  TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                          'pending', 'completed', 'failed'
                      )),
    result_ref        TEXT,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_evolution_consequence UNIQUE (event_id, consequence_name)
);

COMMENT ON TABLE public.case_evolution_consequences IS
    'Program Delta, Sprint 001 — one row per (event, consequence) pair. The Canonical Consequence Engine (services/case_evolution.py::handle_case_changed) checks this table BEFORE running a consequence''s executor and skips it if already completed — this is what makes "crash after Genome, retry, no duplicate" and "crash after Timeline, retry, resumes where it left off" true by construction, not by convention. The UNIQUE constraint is the DB-enforced guarantee: a consequence can complete for a given event at most once.';

COMMENT ON COLUMN public.case_evolution_consequences.result_ref IS
    'Opaque reference to whatever the consequence produced (a Genome version number, a predmet_hronologija row id, etc.) — verification/audit read this to confirm the consequence''s effect actually landed, not just that the function returned without raising.';

CREATE INDEX IF NOT EXISTS idx_case_evolution_consequences_event
    ON public.case_evolution_consequences(event_id);

ALTER TABLE public.case_evolution_consequences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "case_evolution_consequences_service_role" ON public.case_evolution_consequences;
CREATE POLICY "case_evolution_consequences_service_role" ON public.case_evolution_consequences
    FOR ALL USING (auth.role() = 'service_role');
