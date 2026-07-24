-- Migracija 083 — feature_key za Ambient Copilot
-- KORAK C: Ambient Context & Word/Browser Copilot (2026-07-24)
--
-- routers/copilot_ambient.py koristi PermissionService.require("copilot_ambient")
-- -- bez ovog reda, get_policy() baca RuntimeError na PRVI poziv (isti
-- propust-obrazac kao migracija 066 za digital_twin). krediti=0 jer je ovo
-- zamišljeno kao česta, debounced pozadinska pomoć dok advokat kuca (Word/
-- browser) -- naplata po pozivu bi bila neprijatna; dnevni_limit=200 je
-- budžetska zaštita umesto kredita (gpt-4o-mini je jeftin, ali ne besplatan).

INSERT INTO public.feature_registry
    (feature_key, naziv, kategorija, minimum_plan, addon, krediti, dnevni_limit, mesecni_limit, ai_model, priority, estimated_cost_usd, opis)
VALUES
    ('copilot_ambient', 'Ambient Copilot (Word/Browser)', 'ai_osnovno', 'professional', NULL, 0, 200, NULL, 'gpt-4o-mini', 'LOW', 0.003,
     'Brza ekspresna analiza pasusa dok advokat kuca van aplikacije (MS Word add-in / browser ekstenzija) -- kratki predlozi članova zakona/prakse, bez kredit naplate po pozivu.')
ON CONFLICT (feature_key) DO NOTHING;
