-- ============================================================================
-- Vindex AI — Migracija 051: korisnik_plan / korisnik_usage schema drift
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 050.
--
-- routers/plans.py je od pisanja prosiren novim resursima
-- (court_predictor, battle_reports, hearing_prep, commander, simulator,
-- digital_twin, evidence_graph, nacrti) i novim nazivima planova
-- (starter, enterprise -- vidi _PLAN_ALIAS) ali migracija 024 nikad nije
-- azurirana da prati te promene:
--   - korisnik_usage nema kolone za nove resurse (INSERT/UPSERT bi pukao
--     "column does not exist" cim se enforce_and_increment() pozove sa
--     jednim od njih -- trenutno se to jos ne desava nigde u kodu, ali
--     cim se bilo koja od tih funkcija poveze na enforcement ovo bi bio
--     zivi bug)
--   - korisnik_plan.plan_type CHECK dozvoljava samo 'free','advokat','pro',
--     'firma' -- ako iko ikad upise 'starter'/'enterprise' direktno (novi
--     nazivi iz plans.py), CHECK constraint odbija upis
-- ============================================================================

ALTER TABLE public.korisnik_usage
    ADD COLUMN IF NOT EXISTS nacrti           integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS court_predictor  integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS battle_reports   integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS hearing_prep     integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS commander        integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS simulator        integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS digital_twin     integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS evidence_graph   integer NOT NULL DEFAULT 0;

ALTER TABLE public.korisnik_plan
    DROP CONSTRAINT IF EXISTS korisnik_plan_plan_type_check;

ALTER TABLE public.korisnik_plan
    ADD CONSTRAINT korisnik_plan_plan_type_check
    CHECK (plan_type IN ('free','advokat','pro','firma','starter','enterprise'));
