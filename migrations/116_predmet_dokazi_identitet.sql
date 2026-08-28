-- Migration 116: predmet_dokazi.identitet — stabilan identitet tvrdnje
-- Run in Supabase SQL Editor
--
-- IMPLEMENTATION TASK 001 (2026-08-27). Odobreno u MASTER GATE 009 kao PRVA
-- IMPLEMENTACIONA GRANICA.
--
--     identitet = sha256(predmet_id | CANON_VERSION | normalize_ws(tvrdnja))
--
-- Računa se TAČNO JEDNOM, pri upisu (shared/evidence_write.py::upisi_dokaze),
-- i NIKADA se ne preračunava pri čitanju. Zato je ovo skladištena kolona, a ne
-- generated/computed column: promena pravila kanonizacije sme da proizvede NOVE
-- identitete, ali NE SME retroaktivno da promeni postojeće.
--
-- ŠTA IDENTITET NAMERNO NE SADRŽI:
--   * offset / stranicu / paragraf  — dokazano krto (Gate 005: dokument prepoznat
--     kao isti, a tvrdnja dobija drugi ID na CRLF ili trailing razmaku)
--   * EXTRACTION_VERSION — inače bi svaka nadogradnja ekstraktora prekinula sve
--     buduće relacije u svim predmetima
--   * embedding — nedeterministički između verzija modela; prag je odluka
--
-- KOLONA JE NULLABLE I BEZ BACKFILL-a. 12 postojećih redova (svi testni, nastali
-- pre 2026-07-22) ostaju sa NULL. Migracija podataka NIJE odobrena ovim taskom;
-- tvrdnja bez identiteta jednostavno ne može biti kraj buduće relacije.

ALTER TABLE public.predmet_dokazi
  ADD COLUMN IF NOT EXISTS identitet TEXT;

COMMENT ON COLUMN public.predmet_dokazi.identitet IS
  'sha256(predmet_id|CANON_VERSION|normalize_ws(tvrdnja)) — izracunato JEDNOM pri upisu, nikad preracunato pri citanju. NULL znaci da identitet nije izracunat ili nije sacuvan za taj red. Ocekivano je za redove nastale pre uvodjenja ove kolone, ali moze nastati i kasnije, kada upis predje na dozvoljeni degradirani fallback (shared/evidence_write.py::_insert_sa_fallback). NULL zato NE dokazuje da migracija 116 nije izvrsena, niti da je red stariji od nje.';

-- Dedup/lookup po identitetu unutar predmeta. NIJE UNIQUE: ista tvrdnja sme
-- postojati više puta dok ne postoji eksplicitna odluka o deduplikaciji
-- (INVARIANT 4 iz TASK-a 001 — ne uvoditi drugi sistem idempotentnosti bez dokaza).
CREATE INDEX IF NOT EXISTS idx_dokaz_identitet
  ON public.predmet_dokazi (predmet_id, identitet)
  WHERE deleted_at IS NULL;
