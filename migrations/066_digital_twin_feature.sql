-- ============================================================================
-- Vindex AI — Migracija 066: nedostajući feature_key za Digital Twin
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 065.
--
-- Otkriveno pri mapiranju endpoint-a na Feature Registry (Faza 70, pred
-- ožičavanje): routers/digital_twin.py (3-scenario simulacija + "šta ako"
-- analiza, oba GPT-4o) nikad nije dobio red u feature_registry — propust iz
-- migracije 064. Bez ovoga PermissionService.require("digital_twin") bi
-- bacio RuntimeError pri prvom pozivu. Ne "nova funkcija Registry-ja" —
-- popravka nedostajućeg podatka pre nego što se endpoint ožiči.
-- ============================================================================

INSERT INTO public.feature_registry
    (feature_key, naziv, kategorija, minimum_plan, addon, krediti, dnevni_limit, mesecni_limit, ai_model, priority, estimated_cost_usd, opis)
VALUES
    ('digital_twin', 'Digital Twin (3-scenario simulacija)', 'litigation', 'professional', NULL, 3, NULL, NULL, 'gpt-4o', 'MEDIUM', 0.054,
     'kreiraj_simulaciju = 3 kredita, sta_ako_analiza = 1 kredit — endpoint sam bira preko multiplier parametra UsageService.consume().')
ON CONFLICT (feature_key) DO NOTHING;
