-- ============================================================
-- Vindex AI — Confidence Audit + Explainable Learning + Knowledge Hygiene
-- 041_confidence_audit_hygiene.sql
-- ============================================================

-- ─── Confidence Audit: obogacivanje recommendation_log ───────────────────────

ALTER TABLE recommendation_log
  ADD COLUMN IF NOT EXISTS confidence_band TEXT CHECK(confidence_band IN ('niska','srednja','visoka')),
  ADD COLUMN IF NOT EXISTS izvori_tezina   JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS bila_tacna      BOOLEAN,
  ADD COLUMN IF NOT EXISTS oblast_prava    TEXT;

-- Kalibracija: svaka tacka (preporuka + ishod) je jedan red
CREATE TABLE IF NOT EXISTS confidence_audit_log (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,
  recommendation_id UUID REFERENCES recommendation_log(id) ON DELETE CASCADE,
  confidence_band   TEXT NOT NULL CHECK(confidence_band IN ('niska','srednja','visoka')),
  prihvacena        BOOLEAN NOT NULL,
  ishod             TEXT,             -- pobeda | poraz | nagodba | odustajanje | NULL (jos nije zatvoren)
  bila_tacna        BOOLEAN,          -- TRUE = prihvacena preporuka + pobeda/nagodba
  oblast_prava      TEXT,
  predmet_id        UUID,
  synced_at         TIMESTAMPTZ DEFAULT now(),
  UNIQUE(recommendation_id)           -- jedna tacka po preporuci
);

CREATE INDEX IF NOT EXISTS idx_audit_user_band ON confidence_audit_log(user_id, confidence_band, bila_tacna);
CREATE INDEX IF NOT EXISTS idx_audit_user_ishod ON confidence_audit_log(user_id, ishod, synced_at DESC);

-- ─── Knowledge Hygiene: problemi koje sistem detektuje ───────────────────────

ALTER TABLE lessons_learned
  ADD COLUMN IF NOT EXISTS pristupi          INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS poslednji_pristup TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS grupa_id          UUID;  -- za grupisanje spojenih lekcija

CREATE TABLE IF NOT EXISTS knowledge_hygiene_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL,
  tip_akcije   TEXT NOT NULL CHECK(tip_akcije IN ('duplikat','zastarela','kontradikcija','niska_potvrda')),
  entitet_tip  TEXT NOT NULL CHECK(entitet_tip IN ('lekcija','pattern','preporuka')),
  entitet_id   UUID NOT NULL,
  entitet2_id  UUID,             -- za parove (duplikat A↔B, kontradikcija A↔B)
  opis         TEXT NOT NULL,
  skor         NUMERIC(5,2),     -- jaccard similarity za duplikate, starost za zastarele
  status       TEXT DEFAULT 'pending' CHECK(status IN ('pending','sprovedeno','ignorisano')),
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hygiene_user_status ON knowledge_hygiene_log(user_id, status, tip_akcije);
CREATE INDEX IF NOT EXISTS idx_hygiene_entitet ON knowledge_hygiene_log(entitet_id, tip_akcije);

-- RLS
ALTER TABLE confidence_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_hygiene_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY confidence_audit_own ON confidence_audit_log USING (auth.uid() = user_id);
CREATE POLICY knowledge_hygiene_own ON knowledge_hygiene_log USING (auth.uid() = user_id);
