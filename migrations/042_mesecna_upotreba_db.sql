-- Migration 042: Mesečna upotreba kredita u DB-u
-- Bug #5 fix: _mesecna_upotreba in-memory dict ne funkcioniše sa više Render workera.
-- Dodajemo kolone u user_credits tabelu za atomično praćenje.

ALTER TABLE user_credits
  ADD COLUMN IF NOT EXISTS mesecno_korisceno INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS mesec             TEXT    NOT NULL DEFAULT '';

-- Index za brzo čitanje mesečnih podataka
CREATE INDEX IF NOT EXISTS idx_user_credits_mesec ON user_credits (user_id, mesec);

COMMENT ON COLUMN user_credits.mesecno_korisceno IS 'Broj AI poziva u tekućem mesecu. Reset se vrši automatski kada mesec != trenutni.';
COMMENT ON COLUMN user_credits.mesec IS 'Format YYYY-MM. Koristi se kao signal za reset brojača.';
