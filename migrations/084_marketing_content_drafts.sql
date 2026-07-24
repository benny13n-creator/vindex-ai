-- Migracija 084 — marketing_content_drafts + feature_key "marketing_agent"
-- KORAK D: Legal Thought Leadership & Content Agent (2026-07-24)
--
-- Skladiste za nacrte LinkedIn/Blog postova koje generiše
-- services/content_generator.py na osnovu JAVNO DOSTUPNE sudske prakse ili
-- zakonskih izmena (nikad iz poverljivih podataka klijenta) -- pregledani/
-- prihvaceni/odbaceni preko routers/marketing_agent.py. Nijedan nacrt se
-- NIKAD ne šalje spolja automatski (v. shared/social_connectors.py --
-- čist format-adapter, bez stvarnog eksternog poziva).

CREATE TABLE IF NOT EXISTS marketing_content_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    izvor_tip       TEXT NOT NULL CHECK (izvor_tip IN ('sudska_praksa', 'zakonska_izmena')),
    izvor_opis      TEXT,
    oblast_prava    TEXT,
    platforma       TEXT NOT NULL CHECK (platforma IN ('linkedin', 'blog')),
    naslov          TEXT,
    tekst           TEXT NOT NULL,
    etika_ok        BOOLEAN,
    etika_problemi  JSONB NOT NULL DEFAULT '[]'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_marketing_drafts_user_status
    ON marketing_content_drafts (user_id, status, created_at DESC);

ALTER TABLE marketing_content_drafts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "marketing_drafts_own_select"
    ON marketing_content_drafts FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "marketing_drafts_own_update"
    ON marketing_content_drafts FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- INSERT ide isključivo preko service-role klijenta (routers/marketing_agent.py
-- poziva services/content_generator.py, koji piše preko _get_supa()) -- nema
-- INSERT policy za obične korisnike, isti obrazac kao agent_recommendations
-- (migracija 082).

COMMENT ON TABLE marketing_content_drafts IS
    'Nacrti stručnih LinkedIn/Blog postova (KORAK D, 2026-07-24). etika_ok/'
    'etika_problemi beleže rezultat automatske etičke provere (v. '
    'services/content_generator.py::_proveri_etiku) -- HITL pregled '
    '(routers/marketing_agent.py accept/reject) je i dalje obavezan bez obzira '
    'na etika_ok, ovo je pomoćni signal, ne zamena za ljudski pregled.';

-- feature_key za PermissionService.require("marketing_agent") -- bez ovog
-- reda, get_policy() baca RuntimeError na prvi poziv (isti obrazac kao
-- migracija 066/083).
INSERT INTO public.feature_registry
    (feature_key, naziv, kategorija, minimum_plan, addon, krediti, dnevni_limit, mesecni_limit, ai_model, priority, estimated_cost_usd, opis)
VALUES
    ('marketing_agent', 'Legal Thought Leadership Content Agent', 'ai_osnovno', 'professional', NULL, 2, 10, NULL, 'gpt-4o-mini', 'LOW', 0.01,
     'Generisanje nacrta LinkedIn/Blog postova na osnovu javne sudske prakse/zakonskih izmena -- 2 kredita po generisanju (LLM generisanje + odvojen etički pregled), dnevni_limit=10 sprečava zloupotrebu kao masovni content-spam alat.')
ON CONFLICT (feature_key) DO NOTHING;
