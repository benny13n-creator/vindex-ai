-- migrations/003_billing.sql
-- Billing module: billing_entries, fakture, timer_sessions
-- Safe to re-run (IF NOT EXISTS / OR REPLACE everywhere).
-- Run in Supabase SQL Editor.

-- ─── FAKTURE (invoice headers) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fakture (
  id              UUID          DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id         UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  predmet_id      UUID          REFERENCES predmeti(id) ON DELETE SET NULL,
  broj_fakture    TEXT          NOT NULL,
  datum_fakture   DATE          NOT NULL DEFAULT CURRENT_DATE,
  klijent_naziv   TEXT          NOT NULL,
  klijent_adresa  TEXT,
  klijent_pib     TEXT,
  iznos_bez_pdv   NUMERIC(12,2) NOT NULL DEFAULT 0,
  pdv_iznos       NUMERIC(12,2) NOT NULL DEFAULT 0,
  iznos_sa_pdv    NUMERIC(12,2) NOT NULL DEFAULT 0,
  status          TEXT          NOT NULL DEFAULT 'nacrt',
  napomena        TEXT,
  created_at      TIMESTAMPTZ   DEFAULT now(),
  updated_at      TIMESTAMPTZ   DEFAULT now(),
  CONSTRAINT fakture_status_check
    CHECK (status IN ('nacrt','izdata','placena','stornirana'))
);

-- ─── BILLING ENTRIES (billable line items) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS billing_entries (
  id              UUID          DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id         UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  predmet_id      UUID          NOT NULL REFERENCES predmeti(id) ON DELETE RESTRICT,
  faktura_id      UUID          REFERENCES fakture(id) ON DELETE SET NULL,
  opis            TEXT          NOT NULL,
  tip             TEXT          NOT NULL DEFAULT 'ostalo',
  tarifa_sifra    TEXT,
  tarifa_naziv    TEXT,
  bodovi          NUMERIC(10,2),
  sati            NUMERIC(10,2),
  iznos_rsd       NUMERIC(12,2) NOT NULL DEFAULT 0,
  datum           DATE          NOT NULL DEFAULT CURRENT_DATE,
  obracunato      BOOLEAN       NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ   DEFAULT now(),
  updated_at      TIMESTAMPTZ   DEFAULT now(),
  CONSTRAINT billing_tip_check
    CHECK (tip IN ('tarifa','satnica','pausal','ostalo'))
);

-- ─── TIMER SESSIONS (time tracking) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS timer_sessions (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  predmet_id  UUID        NOT NULL REFERENCES predmeti(id) ON DELETE CASCADE,
  opis        TEXT,
  start_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  stop_at     TIMESTAMPTZ,
  trajanje_s  INTEGER,
  aktivan     BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Exactly one active timer per user (partial unique index — no extension required)
CREATE UNIQUE INDEX IF NOT EXISTS timer_jedan_aktivan_idx
  ON timer_sessions (user_id)
  WHERE aktivan IS TRUE;

-- ─── UPDATED_AT TRIGGER ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION _billing_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS billing_entries_updated ON billing_entries;
CREATE TRIGGER billing_entries_updated
  BEFORE UPDATE ON billing_entries
  FOR EACH ROW EXECUTE FUNCTION _billing_set_updated_at();

DROP TRIGGER IF EXISTS fakture_updated ON fakture;
CREATE TRIGGER fakture_updated
  BEFORE UPDATE ON fakture
  FOR EACH ROW EXECUTE FUNCTION _billing_set_updated_at();

-- ─── FAKTURA IMMUTABILITY ─────────────────────────────────────────────────────
-- Financial fields become read-only once the invoice leaves 'nacrt' state.
CREATE OR REPLACE FUNCTION faktura_immutability_check()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'nacrt' THEN
    IF ( NEW.iznos_bez_pdv <> OLD.iznos_bez_pdv OR
         NEW.iznos_sa_pdv  <> OLD.iznos_sa_pdv  OR
         NEW.pdv_iznos     <> OLD.pdv_iznos      OR
         NEW.broj_fakture  <> OLD.broj_fakture   OR
         NEW.klijent_naziv <> OLD.klijent_naziv  ) THEN
      RAISE EXCEPTION
        'Faktura % je izdata — finansijska polja su nepromenjiva.', OLD.broj_fakture;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS faktura_immutability ON fakture;
CREATE TRIGGER faktura_immutability
  BEFORE UPDATE ON fakture
  FOR EACH ROW EXECUTE FUNCTION faktura_immutability_check();

-- ─── BROJ FAKTURE RPC ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_next_broj_fakture(p_user_id UUID)
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_year  TEXT    := to_char(now(), 'YYYY');
  v_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM fakture
  WHERE user_id = p_user_id
    AND EXTRACT(YEAR FROM datum_fakture) = EXTRACT(YEAR FROM now());
  RETURN v_year || '-' || LPAD((v_count + 1)::TEXT, 3, '0');
END;
$$;

-- ─── ROW LEVEL SECURITY ───────────────────────────────────────────────────────
ALTER TABLE billing_entries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS billing_entries_policy ON billing_entries;
CREATE POLICY billing_entries_policy ON billing_entries
  USING     (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

ALTER TABLE fakture ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fakture_policy ON fakture;
CREATE POLICY fakture_policy ON fakture
  USING     (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

ALTER TABLE timer_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS timer_policy ON timer_sessions;
CREATE POLICY timer_policy ON timer_sessions
  USING     (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ─── INDEXES ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS billing_entries_predmet_idx ON billing_entries (predmet_id);
CREATE INDEX IF NOT EXISTS billing_entries_user_idx    ON billing_entries (user_id);
CREATE INDEX IF NOT EXISTS billing_entries_faktura_idx ON billing_entries (faktura_id);
CREATE INDEX IF NOT EXISTS fakture_user_idx            ON fakture (user_id);
CREATE INDEX IF NOT EXISTS fakture_predmet_idx         ON fakture (predmet_id);
CREATE INDEX IF NOT EXISTS timer_user_idx              ON timer_sessions (user_id);
CREATE INDEX IF NOT EXISTS timer_predmet_idx           ON timer_sessions (predmet_id);
