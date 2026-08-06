-- ============================================================================
-- Vindex AI — Migration 099: Canonical Action Engine (Program Omega,
-- Sprint 003, 2026-08-06)
--
-- "Autonomous Legal Office — Canonical Action Engine". The ONE table every
-- deterministic "what does the lawyer need to do next" action lives in —
-- see docs/omega/CANONICAL_ACTION_ENGINE.md and ACTION_PRODUCER_REGISTRY.md
-- for the full forensic discovery of what this replaces/unifies (nothing
-- was migrated OFF its own existing table this sprint — identify_case_
-- problems()/calculate_procesni_rizik() remain the canonical NUMBER source,
-- this table is the NEW stateful, lifecycle-managed layer on top).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.case_actions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id        TEXT NOT NULL,
    tip               TEXT NOT NULL CHECK (tip IN (
                          'PRIPREMITI_PODNESAK', 'PRIBAVITI_DOKAZ', 'RAZRESITI_KONTRADIKCIJU',
                          'OJACATI_DOKAZE', 'PLANIRATI_ROKOVE'
                      )),
    razlog            TEXT NOT NULL,
    -- Dokaz -- TAČNO koja činjenica je proizvela ovu akciju (rok datum,
    -- opis nedostajućeg dokaza, kontradikcija objekat sa lokacijom...).
    -- Agent 4's own "no conclusion without source" rule -- ovo polje NIKAD
    -- nije prazno.
    dokaz             JSONB NOT NULL DEFAULT '{}'::jsonb,
    prioritet         TEXT NOT NULL CHECK (prioritet IN ('critical', 'high', 'medium', 'low', 'informational')),
    rok               DATE,
    status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    kreirao           TEXT NOT NULL DEFAULT 'system',
    correlation_id    TEXT,
    -- Deterministicki-izracunate akcije su UVEK pune sigurnosti (1.0) --
    -- ovo polje postoji za shemsku kompletnost / buduce ne-deterministicke
    -- izvore, ne zato sto TRENUTNI izvor ikad vraca nista drugo.
    confidence        NUMERIC NOT NULL DEFAULT 1.0,
    izvor_dokumenti   JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Stabilan identitet OVE cinjenice, ne ovog reda -- omogucava
    -- refresh_case_actions() da bezbedno re-pokrene bez dupliranja
    -- (UNIQUE indeks ispod) i da UPDATE-uje umesto zatvori+ponovo-otvori
    -- kad se detalji promene (npr. rok produzen), a da ZATVORI kad
    -- cinjenica vise ne postoji (npr. dokaz pribavljen).
    dedupe_key        TEXT NOT NULL,
    event_id          UUID REFERENCES public.events(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at         TIMESTAMPTZ
);

-- Samo JEDNA otvorena akcija po (predmet, cinjenica) -- zatvorena akcija za
-- istu cinjenicu koja se kasnije PONOVO pojavi dobija nov red (nova istorija
-- ulazi/izlazi), ne obnavlja stari zatvoren red.
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_actions_open_dedupe
    ON public.case_actions(predmet_id, dedupe_key)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_case_actions_predmet_status
    ON public.case_actions(predmet_id, status);

COMMENT ON TABLE public.case_actions IS
    'Program Omega Sprint 003 -- kanonski model za SVE deterministicki-izracunate poslovne akcije. Jedan model, jedan vlasnik (services/case_evolution.py::_consequence_refresh_case_actions). Nijedan drugi modul ne sme pisati direktno u ovu tabelu.';

ALTER TABLE public.case_actions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "case_actions_service_role" ON public.case_actions;
CREATE POLICY "case_actions_service_role" ON public.case_actions
    FOR ALL USING (auth.role() = 'service_role');
