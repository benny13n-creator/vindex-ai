-- ============================================================================
-- Vindex AI — Migracija 064: Feature Registry — centralna, admin-editabilna
-- monetizaciona konfiguracija
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 063.
--
-- Kontekst: founder je eksplicitno zabranio hardkodirane cene/limite u kodu
-- (docs/ENTITLEMENT_AUDIT_PHASE1.md nastavak). feature_registry je JEDINI
-- izvor istine za: koja tarifa/addon otključava funkciju, koliko kredita
-- košta, dnevni/mesečni limit, koji AI model koristi. PermissionService i
-- UsageService čitaju ISKLJUČIVO odavde (shared/feature_registry.py, sa
-- in-memory kešom koji se invalidira na svaku admin izmenu).
--
-- Menjanje cene/limita/tarife posle ove migracije = UPDATE reda u tabeli
-- (ili Admin Feature Console), NIKAD izmena Python koda.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.feature_registry (
    feature_key         text PRIMARY KEY,
    naziv                text NOT NULL,
    kategorija           text NOT NULL DEFAULT 'ostalo',
    minimum_plan         text CHECK (minimum_plan IN ('basic', 'professional', 'enterprise') OR minimum_plan IS NULL),
    addon                text,
    krediti              numeric NOT NULL DEFAULT 0,
    krediti_po_minutu    numeric,
    dnevni_limit         integer,
    mesecni_limit        integer,
    ai_model             text,
    aktivno              boolean NOT NULL DEFAULT true,
    opis                 text,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    updated_by           text
);

COMMENT ON TABLE public.feature_registry IS
    'Jedini izvor istine za monetizacionu politiku svake funkcije platforme. PermissionService/UsageService čitaju odavde, ne iz koda. Menja se preko Admin Feature Console-a, ne preko deploy-a.';
COMMENT ON COLUMN public.feature_registry.minimum_plan IS
    'NULL = funkcija se otključava isključivo preko addon-a (npr. Digitalna imovina), ne kroz osnovnu tarifu.';
COMMENT ON COLUMN public.feature_registry.addon IS
    'NULL = nije addon-gated. "digital_assets" = zahteva Digitalna imovina & Usklađenost dodatak (39€ ili 79€ standalone), nezavisno od subscription_type.';
COMMENT ON COLUMN public.feature_registry.aktivno IS
    'Kill-switch — kad je false, funkcija je nedostupna SVIMA (uključujući plan koji bi je inače otključao). Za hitno gašenje funkcije bez deploy-a (npr. trošak van kontrole).';

ALTER TABLE public.feature_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY "feature_registry_service_role" ON public.feature_registry
    FOR ALL USING (auth.role() = 'service_role');
-- Čitanje je dozvoljeno i običnim ulogovanim korisnicima (frontend treba da zna
-- cene za prikaz "Nedovoljno kredita — potrebno je X" poruka), ali ne izmena.
CREATE POLICY "feature_registry_authenticated_read" ON public.feature_registry
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── Usage tracking — generičko, po feature_key, ne po fiksnoj koloni ────────
-- (rešava problem iz starog korisnik_usage: dodavanje nove funkcije nikad
-- više ne zahteva ALTER TABLE za novu kolonu)

CREATE TABLE IF NOT EXISTS public.feature_usage (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL,
    feature_key         text NOT NULL REFERENCES public.feature_registry(feature_key),
    dan                 date NOT NULL DEFAULT CURRENT_DATE,
    mesec               text NOT NULL,
    broj_koriscenja     integer NOT NULL DEFAULT 0,
    krediti_potroseni   numeric NOT NULL DEFAULT 0,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, feature_key, dan)
);

CREATE INDEX IF NOT EXISTS feature_usage_user_month_idx ON public.feature_usage (user_id, feature_key, mesec);

ALTER TABLE public.feature_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "feature_usage_self" ON public.feature_usage
    FOR ALL USING (user_id::text = auth.uid()::text);
CREATE POLICY "feature_usage_service_role" ON public.feature_usage
    FOR ALL USING (auth.role() = 'service_role');


-- ============================================================================
-- Seed — inicijalne vrednosti izvedene iz docs/ENTITLEMENT_AUDIT_PHASE1.md.
-- OVO SU POČETNE PROCENE, NE KONAČNE CENE — podesivo bez koda preko Admin
-- Feature Console-a čim je izgrađen (sledeći korak posle ove migracije).
-- Programatski generisano i verifikovano (svaki red ima tačno 11 vrednosti,
-- svaki FEATURE_* iz shared/features.py ima tačno jedan red — nema viška,
-- nema manjka).
-- ============================================================================

INSERT INTO public.feature_registry (feature_key, naziv, kategorija, minimum_plan, addon, krediti, krediti_po_minutu, dnevni_limit, mesecni_limit, ai_model, opis) VALUES
('predmeti_crud', 'Predmeti', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('klijenti_crud', 'Klijenti', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('dokumenti_basic', 'Dokumenti (bez AI analize)', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('rokovi', 'Rokovi i ročišta', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('finansije', 'Finansije i naplata', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('crm', 'CRM osnovno', 'crm', 'basic', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('ai_pravna_pitanja', 'AI pravna pitanja', 'ai_osnovno', 'basic', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('sudska_praksa', 'Sudska praksa', 'ai_osnovno', 'basic', NULL, 0, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('case_dna', 'Case DNA / Case Genome', 'litigation', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', NULL),
('case_intelligence', 'Case Intelligence Briefing', 'litigation', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('case_commander', 'Case Commander', 'litigation', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('case_pipeline', 'Case Pipeline (9-step)', 'litigation', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', NULL),
('cio', 'Chief Intelligence Officer', 'litigation', 'professional', NULL, 5, NULL, NULL, 60, 'gpt-4o', 'Dnevni portfolio sken — mesečni limit sprečava zloupotrebu'),
('client_twin', 'Client Twin', 'komunikacija', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('confidence_audit', 'AI Pouzdanost / Confidence Audit', 'kvalitet', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('conflict_check', 'Provera sukoba interesa', 'compliance', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('corrections', 'Ispravke i učenje stila', 'kvalitet', 'professional', NULL, 0, NULL, NULL, NULL, 'gpt-4o-mini', 'Namerno besplatno — nulta frikcija za feedback petlju'),
('cross_doc', 'Poređenje dokumenata', 'dokumenti', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', NULL),
('decision_replay', 'Decision Replay', 'litigation', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', NULL),
('document_analysis', 'Analiza dokumenta', 'dokumenti', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('document_templates', 'Šabloni dokumenata (AI generisanje)', 'dokumenti', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('drafting', 'Nacrti i podnesci', 'dokumenti', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('evidence', 'Evidence Vault', 'dokazi', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('evidence_graph', 'Evidence Graph', 'dokazi', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('firm_memory', 'Law Firm Brain', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('health_index', 'Firm Health Index', 'analitika', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('hearing_prep', 'Priprema za ročište / Hearing CC', 'litigation', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', NULL),
('intake_ai', 'AI Intake / ekstrakcija', 'crm', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('interni_stavovi', 'Interni pravni stavovi', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('knowledge_base', 'Knowledge Base', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('knowledge_graph', 'Knowledge Graph', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('knowledge_hygiene', 'Knowledge Hygiene', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('knowledge_transfer', 'Knowledge Transfer', 'znanje', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('learning', 'Learning / Lessons Learned', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('matter_intel', 'Matter Intelligence', 'analitika', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('memory_graph', 'Memory Graph', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('morning_briefing', 'Jutarnji brifing', 'dnevni_rad', 'professional', NULL, 0, NULL, 5, NULL, 'gpt-4o-mini', 'Namerno besplatno — daily habit driver'),
('multi_agent', 'Tim savetnika (Multi-Agent)', 'litigation', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', 'Cena po pozvanom agentu'),
('oblasti', 'Specijalizovane pravne oblasti', 'ai_osnovno', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('outcome_intel', 'Outcome Intelligence', 'analitika', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('precedenti', 'Law Firm Brain — precedenti', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('profitabilnost_ai', 'AI analiza profitabilnosti', 'finansije', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('strategija', 'Strategija (Red Team, AI Judge...)', 'litigation', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', 'Kompletna analiza (6 modula) troši 6x — posebna logika u endpoint-u'),
('strategy_simulator', 'Strategy Simulator', 'litigation', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('style_checker', 'Style Checker', 'kvalitet', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('court_predictor', 'Court Predictor (ishod, sudija...)', 'litigation', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('copilot', 'Vindex Copilot', 'ai_osnovno', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('vindex_memory', 'Vindex Memory', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('voice', 'Glasovne komande', 'ai_osnovno', 'professional', NULL, 0, 2, NULL, NULL, 'whisper+tts', NULL),
('zadaci_ai', 'AI analiza zadataka', 'crm', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('zastarelost_guardian', 'Zastarelost Guardian', 'litigation', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('zakon_monitoring', 'Praćenje izmena zakona', 'znanje', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('region_ai', 'Regionalni AI savet', 'ai_osnovno', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('procena', 'Pravna procena predmeta', 'litigation', 'professional', NULL, 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('predmet_upload_ai', 'AI analiza pri upload-u dokumenta', 'dokumenti', 'professional', NULL, 3, NULL, NULL, NULL, 'gpt-4o', '3 paralelna poziva po upload-u'),
('predmet_ai_preporuka', 'AI preporuka za predmet', 'litigation', 'professional', NULL, 1, NULL, NULL, NULL, 'gpt-4o-mini', NULL),
('predmet_workspace_ai', 'Workspace AI cockpit summary', 'litigation', 'professional', NULL, 1, NULL, 50, NULL, 'gpt-4o-mini', 'Pokreće se pri svakom otvaranju predmeta — dnevni limit je bezbednosni ventil'),
('kancelarija_team', 'Tim kancelarije', 'enterprise', 'enterprise', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('enterprise_delegacija', 'Delegiranje i firma-statistike', 'enterprise', 'enterprise', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('klijenti_audit_log', 'Audit log klijenata', 'enterprise', 'enterprise', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('api_external', 'Eksterni API pristup', 'enterprise', 'enterprise', NULL, 0, NULL, NULL, NULL, NULL, NULL),
('da_regulatory_review', 'Regulatory Review (ZDI/MiCA/CARF)', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_due_diligence', 'Due Diligence (Documentation Health)', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_wallet_risk_assessment', 'Wallet Risk Assessment', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_source_of_funds', 'Source of Funds Dossier', 'digital_assets', NULL, 'digital_assets', 2, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_smart_contract', 'Pametni ugovor — pravna analiza', 'digital_assets', NULL, 'digital_assets', 5, NULL, NULL, NULL, 'gpt-4o', 'Najskuplji alat u modulu'),
('da_whitepaper_analysis', 'AI analiza projekta (Whitepaper)', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_aml_audit', 'AML/KYC revizija', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL),
('da_reporting_simulator', 'Exchange Reporting Simulator', 'digital_assets', NULL, 'digital_assets', 1, NULL, NULL, NULL, 'gpt-4o', NULL)
ON CONFLICT (feature_key) DO NOTHING;

-- ============================================================================
-- Provera (opciono)
-- SELECT feature_key, naziv, minimum_plan, addon, krediti FROM public.feature_registry ORDER BY kategorija, feature_key;
-- SELECT count(*) FROM public.feature_registry;  -- očekivano: 69
-- ============================================================================
