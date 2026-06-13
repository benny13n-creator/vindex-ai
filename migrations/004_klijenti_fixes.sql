-- =============================================================================
-- Migracija 004: Klijenti — Bug fixes (maticni_broj, datum_nastanka, tip constraint)
--
-- Pokretanje: Supabase SQL Editor
-- Idempotentna: sve naredbe koriste IF NOT EXISTS / IF EXISTS / DO block
--
-- Fixes:
--   Bug A — dodaje kolonu maticni_broj (router.py:211 je koristi pri INSERT)
--   Bug B — dodaje kolonu datum_nastanka (router.py:214 je koristi pri INSERT)
--   Bug C — proširuje CHECK constraint na tip kolonu da prihvata
--            'fizicko_lice' i 'pravno_lice' pored starih 'fizicko'/'pravno'
-- =============================================================================

-- ─── Bug A: maticni_broj ─────────────────────────────────────────────────────
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS maticni_broj TEXT;

-- ─── Bug B: datum_nastanka ───────────────────────────────────────────────────
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS datum_nastanka TIMESTAMPTZ DEFAULT now();

-- ─── Bug C: tip CHECK constraint — proširenje na 4 vrednosti ─────────────────
-- Korak 1: Pronađi i ukloni sve postojeće CHECK constraint-e na tip koloni
DO $$
DECLARE
    v_conname TEXT;
BEGIN
    FOR v_conname IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'klijenti'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%tip%'
    LOOP
        EXECUTE 'ALTER TABLE klijenti DROP CONSTRAINT IF EXISTS ' || quote_ident(v_conname);
    END LOOP;
END
$$;

-- Korak 2: Dodaj novi constraint koji prihvata oba seta vrednosti
--   'fizicko'/'pravno'       — backward compat za postojeće redove
--   'fizicko_lice'/'pravno_lice' — vrednosti koje šalje frontend
ALTER TABLE klijenti ADD CONSTRAINT klijenti_tip_check
    CHECK (tip IN ('fizicko', 'pravno', 'fizicko_lice', 'pravno_lice'));
