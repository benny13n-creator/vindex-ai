-- Migration 080: predmet_dokazi — lokacijsko utemeljenje (grounding)
-- Run in Supabase SQL Editor
--
-- Faza 4, AKCIJA 2 (2026-07-24): predmet_dokazi je do sada beležio SAMO
-- dokument_id (IZ KOG dokumenta dokaz potiče), ne i GDE u tom dokumentu.
-- Advokat je morao ručno da pretražuje ceo dokument da proveri tvrdnju.
-- Ove kolone omogućavaju klikom-na-lokaciju verifikaciju, isti princip kao
-- analiza/segmenter.py::Segment (start_offset/end_offset), samo primenjen
-- na Evidence Vault umesto na Forenzički Legal Audit.
--
-- Sve kolone su NULLABLE i bez default vrednosti različite od NULL:
-- postojeći redovi ostaju validni bez migracije podataka, a routers/
-- evidence.py popunjava ih SAMO kad segmentacija stvarno uspe (fail-soft,
-- isto kao ostatak Evidence Vault-a — vidi docs/ENGINEERING_PRINCIPLES.md).

ALTER TABLE public.predmet_dokazi
  ADD COLUMN IF NOT EXISTS stranica      INTEGER,
  ADD COLUMN IF NOT EXISTS paragraf      TEXT,
  ADD COLUMN IF NOT EXISTS start_offset  INTEGER,
  ADD COLUMN IF NOT EXISTS end_offset    INTEGER;

COMMENT ON COLUMN public.predmet_dokazi.stranica IS
  'Procenjena stranica u originalnom dokumentu (1-indeksirano), NULL ako nije izračunato.';
COMMENT ON COLUMN public.predmet_dokazi.paragraf IS
  'ID segmenta/klauzule iz analiza/segmenter.py (npr. "clause_7"), NULL ako dokument nije segmentiran.';
COMMENT ON COLUMN public.predmet_dokazi.start_offset IS
  'Pozicija početka citata u tekst_sadrzaj (karakteri), NULL ako nije izračunato.';
COMMENT ON COLUMN public.predmet_dokazi.end_offset IS
  'Pozicija kraja citata u tekst_sadrzaj (karakteri), NULL ako nije izračunato.';

-- Indeks za "skoči na lokaciju" upite (dokument + stranica)
CREATE INDEX IF NOT EXISTS idx_dokaz_lokacija
  ON public.predmet_dokazi (dokument_id, stranica)
  WHERE deleted_at IS NULL;
