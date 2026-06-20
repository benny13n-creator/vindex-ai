-- Migration 024: Planovi i praćenje potrošnje
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS korisnik_plan (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  plan_type     TEXT NOT NULL DEFAULT 'free' CHECK (plan_type IN ('free','advokat','pro','firma')),
  seats         INT  NOT NULL DEFAULT 1,
  billing_cycle TEXT NOT NULL DEFAULT 'monthly' CHECK (billing_cycle IN ('monthly','yearly')),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS korisnik_usage (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  year_month          TEXT NOT NULL,  -- format: '2026-06'
  ai_queries          INT NOT NULL DEFAULT 0,
  doc_analyses        INT NOT NULL DEFAULT 0,
  strategies          INT NOT NULL DEFAULT 0,
  overage_queries     INT NOT NULL DEFAULT 0,
  overage_docs        INT NOT NULL DEFAULT 0,
  overage_strategies  INT NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, year_month)
);

-- Limiti po planu (read-only referentna tabela)
CREATE TABLE IF NOT EXISTS plan_limits (
  plan_type    TEXT PRIMARY KEY,
  ai_queries   INT,   -- NULL = neograničeno
  doc_analyses INT,
  strategies   INT
);

INSERT INTO plan_limits VALUES
  ('free',    15,  2,  0),
  ('advokat', 100, 10, 2),
  ('pro',     300, NULL, 5),
  ('firma',   200, 20, 10)
ON CONFLICT (plan_type) DO UPDATE SET
  ai_queries   = EXCLUDED.ai_queries,
  doc_analyses = EXCLUDED.doc_analyses,
  strategies   = EXCLUDED.strategies;

-- Indeksi
CREATE INDEX IF NOT EXISTS korisnik_usage_user_month_idx ON korisnik_usage (user_id, year_month);
CREATE INDEX IF NOT EXISTS korisnik_plan_user_idx ON korisnik_plan (user_id);

-- RLS
ALTER TABLE korisnik_plan  ENABLE ROW LEVEL SECURITY;
ALTER TABLE korisnik_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "korisnik_plan_self"  ON korisnik_plan  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "korisnik_usage_self" ON korisnik_usage FOR ALL USING (auth.uid() = user_id);

-- plan_limits je javna (readonly za sve)
ALTER TABLE plan_limits ENABLE ROW LEVEL SECURITY;
CREATE POLICY "plan_limits_public_read" ON plan_limits FOR SELECT USING (true);
