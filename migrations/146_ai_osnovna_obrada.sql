-- ============================================================================
-- Vindex AI — Migracija 146: registry red za AI rad bez posebne funkcije
-- Early Access, Faza A (AI zaštita troška). Pokrenuti u: Supabase Dashboard →
-- SQL Editor. Idempotentno. NE menja nijedan postojeći red.
-- ============================================================================
--
-- ZAŠTO
-- AI budžetska brana (shared/ai_budget.py) ne pušta nijedan poziv provajdera za
-- prijavljenog korisnika bez rezervacije kroz UsageService. Većina AI ruta je
-- vezana za svoju funkciju preko PermissionService.require(feature). Ostatak
-- (ručna autentifikacija, Smart Intake radnik, obrada događaja) do sada nije
-- imao NIKAKVU rezervaciju — a često ni naplatu. Ti pozivi se sada rezervišu na
-- ovaj red, kroz isti mehanizam (atomični `increment_feature_usage`, migr. 108).
--
-- BEZ OVOG REDA: `get_policy('ai_osnovna_obrada')` diže RuntimeError, rezervacija
-- pada i brana te pozive ODBIJA (fail-closed). Zato se ova migracija pokreće PRE
-- puštanja koda sa branom, inače Smart Intake obrada i druge nevezane AI putanje
-- prestaju da rade.
--
-- CENA I LIMIT SU ODLUKA OSNIVAČA (Admin Feature Console):
--   krediti = 0          — isto kao danas: ove putanje nisu naplaćivane, i ova
--                          migracija ne uvodi novu cenu.
--   dnevni_limit = 300   — PREDLOG zaštitnog limita po nalogu i danu (broj AI
--                          operacija, ne kredita), po uzoru na copilot_ambient
--                          (migr. 083: 0 kredita + dnevni limit kao budžetska
--                          zaštita). Menja se bez deploy-a.
--   minimum_plan = basic — red se ne koristi kroz PermissionService; vrednost je
--                          samo dokumentacija.
--   aktivno = true       — postavljanjem na false osnivač odmah gasi SVU AI obradu
--                          koja ide na ovaj red (kill-switch), bez deploy-a.
-- ============================================================================

BEGIN;

INSERT INTO public.feature_registry
    (feature_key, naziv, kategorija, minimum_plan, addon, krediti, dnevni_limit, mesecni_limit,
     ai_model, estimated_cost_usd, opis, updated_by)
VALUES
    ('ai_osnovna_obrada', 'Osnovna AI obrada (bez posebne funkcije)', 'ai_osnovno', 'basic', NULL, 0, 300, NULL,
     'gpt-4o-mini', NULL,
     'AI rad koji nije vezan za posebnu funkciju: Smart Intake obrada, obrada događaja, rute sa ručnom '
     'autentifikacijom. Rezervacija pre poziva provajdera (shared/ai_budget.py). Bez naplate kredita; '
     'dnevni_limit je zaštitni limit operacija po nalogu.',
     'migration_146_ai_osnovna_obrada')
ON CONFLICT (feature_key) DO NOTHING;

COMMIT;

-- ── PROVERA (read-only, posebno) ────────────────────────────────────────────
-- SELECT feature_key, krediti, dnevni_limit, aktivno, status, chargeable
--   FROM public.feature_registry WHERE feature_key = 'ai_osnovna_obrada';
-- Očekivano: 1 red, krediti 0, dnevni_limit 300, aktivno true, status ACTIVE.
