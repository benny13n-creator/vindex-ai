-- ============================================================================
-- Vindex AI — Migration 098: Case Intelligence Summaries (Program Omega,
-- Sprint 002, 2026-08-06)
--
-- "Case Intelligence Aggregation Engine" — the durable, queryable record of
-- WHAT CHANGED in a case as a result of a canonical refresh
-- (services/case_evolution.py::refresh_case_intelligence). One row per
-- (predmet_id, triggering durable event_id) — never overwritten, so the
-- full history of "what did this batch/event actually change" stays
-- auditable, matching Agent 3's own "no conclusion without source" rule:
-- every number in `detalji` traces back to real rows (documents, evidence,
-- risk-engine findings) computed at the time of this specific refresh, not
-- a live, mutable, unsourced aggregate.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.case_intelligence_summaries (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id                  TEXT NOT NULL,
    event_id                    UUID REFERENCES public.events(id),
    reason                      TEXT NOT NULL,
    correlation_id              TEXT,
    dokumenata_dodato           INTEGER NOT NULL DEFAULT 0,
    novi_dokazi                 INTEGER NOT NULL DEFAULT 0,
    novi_dogadjaji              INTEGER NOT NULL DEFAULT 0,
    kontradikcije_pronadjene    INTEGER NOT NULL DEFAULT 0,
    rizici_koji_zahtevaju_paznju INTEGER NOT NULL DEFAULT 0,
    novi_rokovi                 INTEGER NOT NULL DEFAULT 0,
    dokumenti_niska_sigurnost   INTEGER NOT NULL DEFAULT 0,
    genome_verzija_pre          INTEGER,
    genome_verzija_posle        INTEGER,
    -- Puni izvor svake gornje brojke -- dokazivo, ne samo tvrđeno. Oblik:
    -- {"kontradikcije": [{"opis": "...", "lokacija_1": "DOK-03 str.2", ...}],
    --  "nedostajuci_dokazi": [...], "rizici": [{"problem": "...", "ozbiljnost": "..."}],
    --  "job_ids": [...]}
    detalji                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_case_intelligence_summaries_predmet
    ON public.case_intelligence_summaries(predmet_id, created_at DESC);

COMMENT ON TABLE public.case_intelligence_summaries IS
    'Program Omega Sprint 002 -- jedan red po (predmet, dogadjaj koji je pokrenuo refresh_case_intelligence). Nikad se ne prepisuje -- istorijski, dokaziv zapis "sta se promenilo", ne live mutable agregat.';

ALTER TABLE public.case_intelligence_summaries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "case_intelligence_summaries_service_role" ON public.case_intelligence_summaries;
CREATE POLICY "case_intelligence_summaries_service_role" ON public.case_intelligence_summaries
    FOR ALL USING (auth.role() = 'service_role');
