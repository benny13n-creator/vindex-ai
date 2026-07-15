-- ============================================================================
-- Vindex AI — Migracija 071: Business Groups — poslovne celine za Pricing Modal
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 070.
--
-- Kontekst: Pricing Modal redizajn (Faza 73) zahteva da se 60 prodajnih
-- funkcija (52 SUBSCRIPTION + 8 ADDON) prikažu kao 7 poslovnih celina koje
-- korisnik razume ("AI pravna analiza", "Strategija predmeta"...), ne kao
-- ravna lista od 60 stavki niti po internoj 'kategorija' koloni (tehnička
-- klasifikacija, korišćena samo kao seeding aid — feature_registry.kategorija
-- OSTAJE internog karaktera, nikad prikazana korisniku).
--
-- Arhitektonsko pravilo (founder, ova faza): business_group je POSLOVNA
-- vrednost koju korisnik kupuje, ne tehnička arhitektura. Zato assignment
-- ispod ponegde odstupa od 'kategorija' grupisanja (npr. health_index je
-- kategorija='analitika' ali ide u 'Upravljanje kancelarijom' jer je to
-- metrika cele kancelarije — "Firm Health Index" — ne metrika po predmetu).
--
-- FOUNDATION (6 redova) i COMING_SOON (4 enterprise reda) NAMERNO ostaju bez
-- business_group_id (NULL) — nikad se ne pojavljuju u Pricing Matrix-u, po
-- migraciji 070's feature_type pravilu.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.business_groups (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key            TEXT NOT NULL UNIQUE,
    display_name   TEXT NOT NULL,
    description    TEXT,
    icon           TEXT,
    display_order  INTEGER NOT NULL DEFAULT 0,
    visible        BOOLEAN NOT NULL DEFAULT true,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by     TEXT
);

COMMENT ON TABLE public.business_groups IS
    'Poslovne celine za Pricing Modal (Nivo 1 kartice). feature_registry.business_group_id referencira ovu tabelu. Jedini izvor grupisanja — Pricing Matrix se IZVODI spajanjem feature_registry + business_groups + tier_config u trenutku upita, nikad se ne čuva kao zaseban pricing_matrix red.';
COMMENT ON COLUMN public.business_groups.key IS
    'Stabilan identifikator (npr. ai_pravna_analiza) — koristi se u kodu/testovima, display_name se menja slobodno preko Admin Console-a bez uticaja na logiku.';

ALTER TABLE public.business_groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY "business_groups_service_role" ON public.business_groups
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "business_groups_authenticated_read" ON public.business_groups
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── business_groups_audit — trajan, append-only zapis svake promene ─────────
CREATE TABLE IF NOT EXISTS public.business_groups_audit (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_key    TEXT NOT NULL,
    changed_by   TEXT NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_values   JSONB,
    new_values   JSONB
);

CREATE INDEX IF NOT EXISTS idx_business_groups_audit_key ON public.business_groups_audit(group_key, changed_at DESC);

ALTER TABLE public.business_groups_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY "business_groups_audit_service_role" ON public.business_groups_audit
    FOR ALL USING (auth.role() = 'service_role');


-- ── Seed — 7 poslovnih celina, founder-ova finalna struktura ────────────────

INSERT INTO public.business_groups (key, display_name, description, display_order) VALUES
    ('ai_pravna_analiza',        'AI pravna analiza',              'Pitate AI, dobijate pravni odgovor — pouzdan, proveren, na srpskom/regionalnom pravu.', 1),
    ('strategija_predmeta',      'Strategija predmeta',            'Šta da uradim — simulacija, predviđanje ishoda, priprema za ročište, tim AI savetnika.', 2),
    ('inteligencija_predmeta',   'Inteligencija predmeta',         'Koliko dobro razumem predmet — DNA, briefing, replay odluka, procena, workspace pregled.', 3),
    ('dokumenti_automatizacija', 'Dokumenti i automatizacija',     'AI radi sa vašim dokumentima i dokazima — nacrti, analiza, poređenje, upload obrada.', 4),
    ('znanje_kancelarije',       'Znanje kancelarije',             'Institucionalno znanje koje raste sa vama — presedani, interni stavovi, praćenje propisa.', 5),
    ('upravljanje_kancelarijom', 'Upravljanje kancelarijom',       'AI-osnažene operativne funkcije — provera sukoba interesa, intake, zadaci, profitabilnost.', 6),
    ('digitalna_imovina',        'Digitalna imovina & usklađenost','Zaseban compliance proizvod — CARF/DAC8, OFAC, wallet provenance, source of funds.', 7)
ON CONFLICT (key) DO NOTHING;


-- ── feature_registry.business_group_id — FK ka gornjoj tabeli ───────────────

ALTER TABLE public.feature_registry
    ADD COLUMN IF NOT EXISTS business_group_id UUID REFERENCES public.business_groups(id);

COMMENT ON COLUMN public.feature_registry.business_group_id IS
    'Poslovna celina za Pricing Modal (Nivo 1). NULL za FOUNDATION i COMING_SOON funkcije — te se nikad ne prikazuju u Pricing Matrix-u. Jedna funkcija pripada tačno jednoj grupi.';

-- G1 — AI pravna analiza (9)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'ai_pravna_analiza')
WHERE feature_key IN ('ai_pravna_pitanja', 'copilot', 'oblasti', 'region_ai', 'sudska_praksa', 'voice',
                       'confidence_audit', 'corrections', 'style_checker');

-- G2 — Strategija predmeta (7)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'strategija_predmeta')
WHERE feature_key IN ('strategy_simulator', 'court_predictor', 'hearing_prep', 'case_commander',
                       'digital_twin', 'multi_agent', 'strategija');

-- G3 — Inteligencija predmeta (12)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'inteligencija_predmeta')
WHERE feature_key IN ('case_dna', 'case_intelligence', 'decision_replay', 'cio', 'matter_intel',
                       'outcome_intel', 'case_pipeline', 'predmet_workspace_ai', 'predmet_ai_preporuka',
                       'procena', 'zastarelost_guardian', 'client_twin');

-- G4 — Dokumenti i automatizacija (7)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'dokumenti_automatizacija')
WHERE feature_key IN ('cross_doc', 'document_analysis', 'document_templates', 'drafting',
                       'predmet_upload_ai', 'evidence', 'evidence_graph');

-- G5 — Znanje kancelarije (11)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'znanje_kancelarije')
WHERE feature_key IN ('knowledge_base', 'knowledge_graph', 'firm_memory', 'memory_graph',
                       'knowledge_hygiene', 'interni_stavovi', 'learning', 'vindex_memory',
                       'precedenti', 'zakon_monitoring', 'knowledge_transfer');

-- G6 — Upravljanje kancelarijom (6)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'upravljanje_kancelarijom')
WHERE feature_key IN ('conflict_check', 'intake_ai', 'zadaci_ai', 'morning_briefing',
                       'profitabilnost_ai', 'health_index');

-- G7 — Digitalna imovina & usklađenost (8, ADDON)
UPDATE public.feature_registry SET business_group_id = (SELECT id FROM public.business_groups WHERE key = 'digitalna_imovina')
WHERE addon = 'digital_assets';
