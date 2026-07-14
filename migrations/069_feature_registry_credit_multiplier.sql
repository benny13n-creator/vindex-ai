-- ============================================================================
-- Vindex AI — Migracija 069: credit_multiplier u feature_registry
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 068.
--
-- Kontekst: 3 endpointa (strategija/kompletna-analiza, digital_twin/
-- kreiraj-simulaciju, strategy_simulator/nova-partija) koštaju N puta
-- baznu cenu iz feature_registry (6×/3×/2×), ali je taj faktor bio
-- hardkodovan u Python kodu (UsageService.consume(..., multiplier=6)) —
-- founder je mogao promeniti BAZNU cenu preko Admin Console-a, ali ne i
-- sam faktor množenja, bez deploy-a. Ovo je taj isti "dva izvora istine"
-- problem koji je feature_registry rešio za osnovnu cenu, sada za faktor.
--
-- Default 1 za sve postojeće redove (bez promene ponašanja za funkcije
-- koje ne koriste multiplier) — seed ispod postavlja stvarne vrednosti
-- SAMO za ta 3 feature_key-a, identične onima koje su bile hardkodovane
-- (bez promene stvarne cene, samo premeštanje izvora).
-- ============================================================================

ALTER TABLE public.feature_registry
    ADD COLUMN IF NOT EXISTS credit_multiplier numeric NOT NULL DEFAULT 1;

COMMENT ON COLUMN public.feature_registry.credit_multiplier IS
    'Faktor množenja bazne cene (krediti) za operacije koje su N puta skuplje od standardnog poziva iste funkcije (npr. kompletna analiza pokreće 6 modula). UsageService.consume() ga čita automatski kad pozivalac ne prosledi eksplicitan multiplier= (koji ostaje rezervisan za DINAMIČKE slučajeve, npr. broj agenata izračunat u runtime-u — ne za statične poslovne odluke, te MORAJU biti ovde, ne u kodu).';

UPDATE public.feature_registry SET credit_multiplier = 6 WHERE feature_key = 'strategija';
UPDATE public.feature_registry SET credit_multiplier = 3 WHERE feature_key = 'digital_twin';
UPDATE public.feature_registry SET credit_multiplier = 2 WHERE feature_key = 'strategy_simulator';
