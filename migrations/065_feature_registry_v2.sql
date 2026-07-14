-- ============================================================================
-- Vindex AI — Migracija 065: Feature Registry v2 — puni životni ciklus funkcije
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 064.
--
-- Kontekst: founder-ova druga runda povratnih informacija na Feature Registry.
-- Jedan red u feature_registry treba da opiše KOMPLETAN životni ciklus funkcije
-- (ne samo tarifu/cenu): cooldown protiv brute-force zloupotrebe, prioritet za
-- buduće load-shedding, procenjeni AI trošak za internu profitabilnost,
-- verziju za A/B testiranje, status životnog ciklusa (ACTIVE/BETA/...), i
-- vidljivost u UI-ju nezavisno od toga da li je funkcija tehnički dostupna.
--
-- Dodato i: trajan audit log svake izmene (feature_registry_audit), tabela
-- zavisnosti između funkcija (feature_dependencies — namerno NEPOPUNJENA,
-- vidi napomenu ispod), i feature_usage_log — događaj-po-događaj log
-- (ne dnevni agregat kao feature_usage) iz kog se feature_analytics VIEW
-- računa uživo, bez posebne tabele koja bi mogla da se raziđe sa izvorom.
-- ============================================================================

ALTER TABLE public.feature_registry
    ADD COLUMN IF NOT EXISTS cooldown_seconds    integer,
    ADD COLUMN IF NOT EXISTS priority            text NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
    ADD COLUMN IF NOT EXISTS estimated_cost_usd   numeric,
    ADD COLUMN IF NOT EXISTS version              text NOT NULL DEFAULT 'v1',
    ADD COLUMN IF NOT EXISTS status               text NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'BETA', 'DEPRECATED', 'INTERNAL', 'COMING_SOON')),
    ADD COLUMN IF NOT EXISTS visible              text NOT NULL DEFAULT 'visible'
        CHECK (visible IN ('visible', 'hidden', 'internal', 'enterprise_only'));

COMMENT ON COLUMN public.feature_registry.cooldown_seconds IS
    'Minimalan razmak između dva poziva ISTOG korisnika za ovu funkciju, nezavisno od kredita/limita. Sprečava brute-force (npr. 500 poziva za 10 sekundi) čak i kad korisnik ima dovoljno kredita.';
COMMENT ON COLUMN public.feature_registry.priority IS
    'Za budući load-shedding mehanizam pod visokim opterećenjem/troškom — LOW se gasi prvo (npr. Voice), HIGH se ne gasi nikad (npr. Case DNA, Predmeti). Trenutno samo informativno, kill-switch (aktivno) je i dalje ručni mehanizam.';
COMMENT ON COLUMN public.feature_registry.estimated_cost_usd IS
    'Procenjen AI trošak PO POZIVU, u USD. NIKAD prikazano korisniku — isključivo za founder-ovu internu profitabilnost (krediti_naplaćeni vs. estimated_cost_usd po funkciji). Početne vrednosti su gruba procena iz ai_model+krediti, tačne vrednosti dolaze iz feature_usage_log kad se prikupi stvarna potrošnja.';
COMMENT ON COLUMN public.feature_registry.version IS
    'Podržava buduće A/B testiranje (npr. case_dna v1 vs v2 promptovanje). Trenutno samo v1 svuda — mehanizam za izbor verzije po korisniku nije još izgrađen.';
COMMENT ON COLUMN public.feature_registry.status IS
    'Životni ciklus funkcije. ACTIVE/BETA su dostupne (BETA se može posebno označiti u UI-ju). DEPRECATED i COMING_SOON blokiraju pristup svima. INTERNAL ograničava na foundera/admin nezavisno od tarife.';
COMMENT ON COLUMN public.feature_registry.visible IS
    'UI vidljivost, nezavisno od tehničke dostupnosti — "hidden" znači funkcija radi (npr. dostupna preko API-ja) ali se ne prikazuje u meniju/UI-ju. Izbegava potrebu da se dugmad uklanjaju/vraćaju u kodu.';

-- ── Priority + estimated_cost_usd — početne vrednosti izvedene iz ai_model/
--    krediti u migraciji 064. Grube procene, editabilno preko Admin Console. ──

UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.018 WHERE feature_key = 'ai_pravna_pitanja';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'case_commander';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.054 WHERE feature_key = 'case_dna';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'case_intelligence';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.054 WHERE feature_key = 'case_pipeline';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.09 WHERE feature_key = 'cio';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'client_twin';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'confidence_audit';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.006 WHERE feature_key = 'conflict_check';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'copilot';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.003 WHERE feature_key = 'corrections';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.036 WHERE feature_key = 'court_predictor';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'crm';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.054 WHERE feature_key = 'cross_doc';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'da_aml_audit';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'da_due_diligence';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'da_regulatory_review';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'da_reporting_simulator';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.09 WHERE feature_key = 'da_smart_contract';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'da_source_of_funds';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'da_wallet_risk_assessment';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'da_whitepaper_analysis';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.054 WHERE feature_key = 'decision_replay';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.036 WHERE feature_key = 'document_analysis';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'document_templates';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'dokumenti_basic';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.036 WHERE feature_key = 'drafting';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'evidence';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'evidence_graph';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'finansije';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'firm_memory';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.036 WHERE feature_key = 'health_index';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.054 WHERE feature_key = 'hearing_prep';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'intake_ai';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'interni_stavovi';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'klijenti_crud';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'knowledge_base';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'knowledge_graph';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.006 WHERE feature_key = 'knowledge_hygiene';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.036 WHERE feature_key = 'knowledge_transfer';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'learning';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'matter_intel';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.006 WHERE feature_key = 'memory_graph';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.003 WHERE feature_key = 'morning_briefing';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'multi_agent';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'oblasti';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.006 WHERE feature_key = 'outcome_intel';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.006 WHERE feature_key = 'precedenti';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'predmet_ai_preporuka';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.054 WHERE feature_key = 'predmet_upload_ai';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.006 WHERE feature_key = 'predmet_workspace_ai';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'predmeti_crud';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.036 WHERE feature_key = 'procena';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'profitabilnost_ai';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'region_ai';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = NULL WHERE feature_key = 'rokovi';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.018 WHERE feature_key = 'strategija';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.036 WHERE feature_key = 'strategy_simulator';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'style_checker';
UPDATE public.feature_registry SET priority = 'HIGH', estimated_cost_usd = 0.003 WHERE feature_key = 'sudska_praksa';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.018 WHERE feature_key = 'vindex_memory';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.015 WHERE feature_key = 'voice';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.006 WHERE feature_key = 'zadaci_ai';
UPDATE public.feature_registry SET priority = 'LOW', estimated_cost_usd = 0.006 WHERE feature_key = 'zakon_monitoring';
UPDATE public.feature_registry SET priority = 'MEDIUM', estimated_cost_usd = 0.018 WHERE feature_key = 'zastarelost_guardian';

-- ── Cooldown — samo za funkcije bez kreditnog troška (0 krediti = nema
--    prirodne prepreke za rapid-fire pozive) ili automatske/ponavljajuće ──
UPDATE public.feature_registry SET cooldown_seconds = 2 WHERE feature_key = 'sudska_praksa';
UPDATE public.feature_registry SET cooldown_seconds = 3 WHERE feature_key = 'voice';
UPDATE public.feature_registry SET cooldown_seconds = 5 WHERE feature_key = 'predmet_workspace_ai';


-- ============================================================================
-- Trajan audit log — svaka izmena feature_registry mora ostati zauvek
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.feature_registry_audit (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    feature_key  text NOT NULL,
    changed_by   text NOT NULL,
    changed_at   timestamptz NOT NULL DEFAULT now(),
    old_values   jsonb,
    new_values   jsonb
);

CREATE INDEX IF NOT EXISTS feature_registry_audit_key_idx ON public.feature_registry_audit (feature_key, changed_at DESC);

ALTER TABLE public.feature_registry_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY "feature_registry_audit_service_role" ON public.feature_registry_audit
    FOR ALL USING (auth.role() = 'service_role');
-- Namerno NEMA UPDATE/DELETE politike ni za service_role u praksi (aplikativni
-- kod samo INSERT-uje) — isti obrazac kao klijenti_audit (append-only).


-- ============================================================================
-- Feature dependencies — mehanizam postoji, NAMERNO NEPOPUNJEN
-- ============================================================================
-- Founder je dao Source of Funds → Wallet Risk kao ILUSTRATIVNI primer, ne
-- potvrđenu tehničku zavisnost. Trenutni kod (routers/source_of_funds.py)
-- wallet proveru tretira kao OPCIONU sekciju dosijea, ne kao tvrdi preduslov
-- — stvarna zavisnost nije verifikovana. Tabela je spremna za kad se pravi
-- zavisnosti identifikuju (kroz Fazu 70 ožičavanja ili kasniji audit), ali
-- se ne nagađa/pretpostavlja ovde.

CREATE TABLE IF NOT EXISTS public.feature_dependencies (
    feature_key  text NOT NULL REFERENCES public.feature_registry(feature_key),
    depends_on   text NOT NULL REFERENCES public.feature_registry(feature_key),
    PRIMARY KEY (feature_key, depends_on),
    CHECK (feature_key <> depends_on)
);

COMMENT ON TABLE public.feature_dependencies IS
    'Ako je depends_on funkcija neaktivna (feature_registry.aktivno=false ili status=DEPRECATED/COMING_SOON), feature_key funkcija je takođe blokirana — proverava PermissionService. Namerno prazna tabela do prve verifikovane zavisnosti.';

ALTER TABLE public.feature_dependencies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "feature_dependencies_service_role" ON public.feature_dependencies
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "feature_dependencies_authenticated_read" ON public.feature_dependencies
    FOR SELECT USING (auth.role() = 'authenticated');


-- ============================================================================
-- feature_usage_log — događaj-po-događaj, za analitiku (feature_usage ostaje
-- kao brzi dnevni/mesečni agregat za enforcement limita, ovo je detaljniji
-- sloj ispod njega)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.feature_usage_log (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL,
    feature_key         text NOT NULL,
    krediti_potroseni   numeric NOT NULL DEFAULT 0,
    ai_model            text,
    tokens_prompt       integer,
    tokens_completion   integer,
    latency_ms          integer,
    estimated_cost_usd  numeric,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS feature_usage_log_feature_time_idx ON public.feature_usage_log (feature_key, created_at DESC);
CREATE INDEX IF NOT EXISTS feature_usage_log_user_feature_idx ON public.feature_usage_log (user_id, feature_key, created_at DESC);

ALTER TABLE public.feature_usage_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "feature_usage_log_service_role" ON public.feature_usage_log
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE public.feature_usage_log IS
    'Detaljan log po pozivu — token/latencija/AI model se popunjavaju POSTEPENO kako se svaki endpoint ožičava na UsageService (Faza 70), nisu odmah dostupni za sve funkcije. feature_analytics VIEW ispod agregira ovo uživo.';


-- ============================================================================
-- feature_analytics — VIEW, ne tabela — izbegava da agregat i sirovi podaci
-- ikad budu neusklađeni (ista greška koju smo upravo ispravili sa FEATURE_*
-- konstantama u kodu — jedan izvor istine, ne dva)
-- ============================================================================

CREATE OR REPLACE VIEW public.feature_analytics AS
SELECT
    l.feature_key,
    r.naziv,
    r.kategorija,
    r.priority,
    count(*)                                   AS poziva,
    sum(l.krediti_potroseni)                   AS krediti_ukupno,
    sum(l.estimated_cost_usd)                  AS ai_cost_ukupno_usd,
    round(avg(l.latency_ms))                   AS avg_latency_ms,
    round(avg(l.tokens_prompt))                AS avg_tokens_prompt,
    round(avg(l.tokens_completion))             AS avg_tokens_completion,
    max(l.created_at)                          AS poslednji_poziv
FROM public.feature_usage_log l
JOIN public.feature_registry r ON r.feature_key = l.feature_key
GROUP BY l.feature_key, r.naziv, r.kategorija, r.priority;

COMMENT ON VIEW public.feature_analytics IS
    'Uživo agregacija feature_usage_log — nema posebnu tabelu za održavanje, pa ne može da se raziđe od izvora. Prazno dok se endpoint-i ne ožičaju na UsageService (Faza 70).';

-- ============================================================================
-- Provera (opciono)
-- SELECT feature_key, priority, estimated_cost_usd, status, visible, version FROM public.feature_registry ORDER BY priority, feature_key;
-- SELECT * FROM public.feature_analytics ORDER BY ai_cost_ukupno_usd DESC;
-- ============================================================================
