-- migrations/006_tarife.sql
-- Personalizovane tarife: globalna satnica + per-klijent override + custom AKS stavke
-- Safe to re-run (IF NOT EXISTS / OR REPLACE everywhere).
-- Run in Supabase SQL Editor.

-- ─── tarife (globalna satnica + per-klijent override) ────────────────────────
CREATE TABLE IF NOT EXISTS tarife (
  id             UUID          DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id        UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  klijent_id     UUID          REFERENCES klijenti(id) ON DELETE CASCADE,
  tarifa_po_satu NUMERIC(10,2) NOT NULL CHECK (tarifa_po_satu > 0),
  created_at     TIMESTAMPTZ   DEFAULT now(),
  updated_at     TIMESTAMPTZ   DEFAULT now()
);

-- NULL = globalni default (jedan po korisniku); non-NULL = per-klijent (jedan po paru)
CREATE UNIQUE INDEX IF NOT EXISTS tarife_user_global_idx
  ON tarife (user_id)
  WHERE klijent_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS tarife_user_klijent_idx
  ON tarife (user_id, klijent_id)
  WHERE klijent_id IS NOT NULL;

-- ─── tarifne_stavke_custom (custom cene za AKS stavke T01-T30) ───────────────
CREATE TABLE IF NOT EXISTS tarifne_stavke_custom (
  id         UUID          DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id    UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  kod        TEXT          NOT NULL CHECK (kod ~ '^T[0-9]+$'),
  naziv      TEXT,
  iznos      NUMERIC(10,2) NOT NULL CHECK (iznos >= 0),
  updated_at TIMESTAMPTZ   DEFAULT now(),
  UNIQUE (user_id, kod)
);

-- ─── updated_at trigger ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION _tarife_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS tarife_updated ON tarife;
CREATE TRIGGER tarife_updated
  BEFORE UPDATE ON tarife
  FOR EACH ROW EXECUTE FUNCTION _tarife_set_updated_at();

DROP TRIGGER IF EXISTS tarifne_stavke_custom_updated ON tarifne_stavke_custom;
CREATE TRIGGER tarifne_stavke_custom_updated
  BEFORE UPDATE ON tarifne_stavke_custom
  FOR EACH ROW EXECUTE FUNCTION _tarife_set_updated_at();

-- ─── RLS ─────────────────────────────────────────────────────────────────────
ALTER TABLE tarife ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tarife_policy ON tarife;
CREATE POLICY tarife_policy ON tarife
  USING     (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

ALTER TABLE tarifne_stavke_custom ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tarifne_stavke_custom_policy ON tarifne_stavke_custom;
CREATE POLICY tarifne_stavke_custom_policy ON tarifne_stavke_custom
  USING     (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

GRANT SELECT, INSERT, UPDATE, DELETE ON tarife                TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON tarifne_stavke_custom TO service_role;

-- ─── indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS tarife_user_idx ON tarife (user_id);
CREATE INDEX IF NOT EXISTS tarifne_stavke_user_idx ON tarifne_stavke_custom (user_id);
