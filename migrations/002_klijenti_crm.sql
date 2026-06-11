-- =============================================================================
-- Migracija 002: Klijenti CRM — Sve faze (P1–P8)
--
-- Pokretanje: Supabase SQL Editor ili supabase db push
-- Idempotentna: sve DDL naredbe koriste IF NOT EXISTS / IF EXISTS
-- =============================================================================

-- ─── FAZA 5: user_roles ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_roles (
    user_id     UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    rola        TEXT        NOT NULL DEFAULT 'advokat'
                            CHECK (rola IN ('sekretarica', 'pripravnik', 'advokat', 'partner')),
    dodelio     UUID        REFERENCES auth.users(id),
    kreirano    TIMESTAMPTZ NOT NULL DEFAULT now(),
    azurirano   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS: čita svako, upisuje/menja samo service_role (API poziva direktno)
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "user_roles_select_own" ON user_roles;
CREATE POLICY "user_roles_select_own"
    ON user_roles FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "user_roles_service_all" ON user_roles;
CREATE POLICY "user_roles_service_all"
    ON user_roles FOR ALL
    USING (auth.role() = 'service_role');


-- ─── FAZA 1: klijenti — proširenje postojeće tabele ──────────────────────────

-- Enkripcija identifikacionih podataka (NIKAD plaintext za jmbg_mb)
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS jmbg_encrypted            TEXT;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS broj_pasosa_encrypted     TEXT;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS pib_encrypted             TEXT;

-- Status enum (proširujemo postojeći)
DO $$
BEGIN
    -- Ako kolona status već postoji, samo dodajemo CHECK constraint
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='klijenti' AND column_name='status'
    ) THEN
        ALTER TABLE klijenti ADD COLUMN status TEXT NOT NULL DEFAULT 'aktivan';
    END IF;
END
$$;

ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS deleted_at               TIMESTAMPTZ;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS datum_poslednje_aktivnosti TIMESTAMPTZ DEFAULT now();
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS connected_persons         JSONB;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS saglasnost_datum         DATE;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS saglasnost_dokument_id   UUID;
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS aktivan                  BOOLEAN NOT NULL DEFAULT TRUE;

-- FAZA 8: Pravni osnov obrade (GDPR)
ALTER TABLE klijenti ADD COLUMN IF NOT EXISTS pravni_osnov_obrade      TEXT NOT NULL DEFAULT 'legitimni_interes'
    CHECK (pravni_osnov_obrade IN ('ugovor', 'zakonska_obaveza', 'legitimni_interes', 'saglasnost'));

-- Ukloni stari plaintext jmbg_mb ako postoji (migracija podataka na encrypted)
-- NAPOMENA: Pre pokretanja ove linije, pokrenite enkriptovani update svim
--           postojećim vrednostima kroz API endpoint /api/admin/migrate-jmbg.
-- ALTER TABLE klijenti DROP COLUMN IF EXISTS jmbg_mb;

-- Indeksi za pretragu (nikad po enkriptovanim vrednostima)
CREATE INDEX IF NOT EXISTS idx_klijenti_status      ON klijenti (status);
CREATE INDEX IF NOT EXISTS idx_klijenti_user_status ON klijenti (user_id, status);
CREATE INDEX IF NOT EXISTS idx_klijenti_aktivan     ON klijenti (aktivan);
CREATE INDEX IF NOT EXISTS idx_klijenti_posljednj_akt ON klijenti (datum_poslednje_aktivnosti);


-- ─── FAZA 2: klijenti_audit (append-only) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS klijenti_audit (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL,
    user_email  TEXT        NOT NULL DEFAULT '',
    user_role   TEXT        NOT NULL DEFAULT 'advokat',
    akcija      TEXT        NOT NULL,
    entitet_tip TEXT        NOT NULL DEFAULT 'klijent',
    entitet_id  UUID,
    detalji     JSONB       NOT NULL DEFAULT '{}',
    ip_adresa   TEXT,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indeks za brze upite po klijentu i korisniku
CREATE INDEX IF NOT EXISTS idx_klijenti_audit_entitet  ON klijenti_audit (entitet_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_klijenti_audit_user     ON klijenti_audit (user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_klijenti_audit_akcija   ON klijenti_audit (akcija, timestamp DESC);

-- RLS: APPEND-ONLY — service_role insert, advokat/partner čitaju
ALTER TABLE klijenti_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audit_insert_service" ON klijenti_audit;
CREATE POLICY "audit_insert_service"
    ON klijenti_audit FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS "audit_select_service" ON klijenti_audit;
CREATE POLICY "audit_select_service"
    ON klijenti_audit FOR SELECT
    USING (auth.role() = 'service_role');

-- Sprečava UPDATE i DELETE za sve (uključujući service_role)
-- Koristimo trigger umesto RLS jer RLS USING za UPDATE/DELETE ne radi pouzdano
CREATE OR REPLACE FUNCTION klijenti_audit_no_mutate()
    RETURNS TRIGGER LANGUAGE plpgsql AS
$$
BEGIN
    RAISE EXCEPTION 'Audit log je append-only. UPDATE i DELETE nisu dozvoljeni.';
END;
$$;

DROP TRIGGER IF EXISTS trg_klijenti_audit_no_update ON klijenti_audit;
CREATE TRIGGER trg_klijenti_audit_no_update
    BEFORE UPDATE ON klijenti_audit
    FOR EACH ROW EXECUTE FUNCTION klijenti_audit_no_mutate();

DROP TRIGGER IF EXISTS trg_klijenti_audit_no_delete ON klijenti_audit;
CREATE TRIGGER trg_klijenti_audit_no_delete
    BEFORE DELETE ON klijenti_audit
    FOR EACH ROW EXECUTE FUNCTION klijenti_audit_no_mutate();


-- ─── FAZA 1+3: predmet_klijenti — proširenje uloge ───────────────────────────

-- Dodaj kolone ako ne postoje
ALTER TABLE predmet_klijenti ADD COLUMN IF NOT EXISTS uloga_klijenta TEXT NOT NULL DEFAULT 'stranka';
ALTER TABLE predmet_klijenti ADD COLUMN IF NOT EXISTS napomena TEXT;
ALTER TABLE predmet_klijenti ADD COLUMN IF NOT EXISTS kreirano TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_pk_uloga ON predmet_klijenti (uloga_klijenta);
CREATE INDEX IF NOT EXISTS idx_pk_klijent ON predmet_klijenti (klijent_id);


-- ─── FAZA 4: klijent_dokumenti (Document Trezor) ─────────────────────────────

CREATE TABLE IF NOT EXISTS klijent_dokumenti (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    klijent_id              UUID        NOT NULL REFERENCES klijenti(id) ON DELETE RESTRICT,
    predmet_id              UUID        REFERENCES predmeti(id) ON DELETE SET NULL,
    storage_key             TEXT        NOT NULL,          -- encrypted_blob_<uuid>
    tip_dokumenta           TEXT        NOT NULL DEFAULT 'ostalo'
                                        CHECK (tip_dokumenta IN (
                                            'lk','pasos','ugovor','presuda','resenje',
                                            'punomocje','ostalo','medicina','finansije'
                                        )),
    naziv_fajla_encrypted   TEXT,                          -- enc_v1:... — NIKAD plaintext
    mime_type               TEXT        NOT NULL DEFAULT 'application/octet-stream',
    velicina                BIGINT,
    uploaded_by             UUID        NOT NULL REFERENCES auth.users(id),
    uploaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,                   -- soft-delete
    CONSTRAINT uq_storage_key UNIQUE (storage_key)
);

CREATE INDEX IF NOT EXISTS idx_kdok_klijent     ON klijent_dokumenti (klijent_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_kdok_predmet     ON klijent_dokumenti (predmet_id) WHERE predmet_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kdok_tip         ON klijent_dokumenti (tip_dokumenta);

ALTER TABLE klijent_dokumenti ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "kdok_service_all" ON klijent_dokumenti;
CREATE POLICY "kdok_service_all"
    ON klijent_dokumenti FOR ALL
    USING (auth.role() = 'service_role');


-- ─── FAZA 7: klijent_komunikacija ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS klijent_komunikacija (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    klijent_id  UUID        NOT NULL REFERENCES klijenti(id) ON DELETE RESTRICT,
    tip         TEXT        NOT NULL DEFAULT 'ostalo'
                            CHECK (tip IN ('poziv','email','sastanak','whatsapp','viber','beleska','ostalo')),
    datum_vreme TIMESTAMPTZ NOT NULL DEFAULT now(),
    ucesnik_id  UUID        NOT NULL REFERENCES auth.users(id),
    kratak_opis TEXT        NOT NULL DEFAULT '',
    kreirano    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sadržaj komunikacije se NE čuva, samo metadata (datum, tip, učesnik, kratak opis)
COMMENT ON COLUMN klijent_komunikacija.kratak_opis IS 'Max 500 znakova — opis svrhe kontakta, bez punog sadržaja';

CREATE INDEX IF NOT EXISTS idx_kkom_klijent ON klijent_komunikacija (klijent_id, datum_vreme DESC);
CREATE INDEX IF NOT EXISTS idx_kkom_ucesnik ON klijent_komunikacija (ucesnik_id);

ALTER TABLE klijent_komunikacija ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "kkom_service_all" ON klijent_komunikacija;
CREATE POLICY "kkom_service_all"
    ON klijent_komunikacija FOR ALL
    USING (auth.role() = 'service_role');


-- ─── FAZA 8: Retention view ───────────────────────────────────────────────────

-- View za brzo identifikovanje kandidata za arhiviranje (>5 godina bez aktivnosti)
CREATE OR REPLACE VIEW klijenti_retention_candidates AS
SELECT
    id,
    ime,
    prezime,
    firma,
    tip,
    status,
    datum_poslednje_aktivnosti,
    now() - datum_poslednje_aktivnosti AS neaktivan_period,
    pravni_osnov_obrade
FROM klijenti
WHERE
    status = 'aktivan'
    AND aktivan = TRUE
    AND datum_poslednje_aktivnosti < now() - INTERVAL '5 years';

COMMENT ON VIEW klijenti_retention_candidates IS 'GDPR retention — klijenti bez aktivnosti >5 godina';


-- ─── Grant za service_role (Supabase API key) ─────────────────────────────────

GRANT ALL ON user_roles                    TO service_role;
GRANT ALL ON klijenti_audit               TO service_role;
GRANT ALL ON klijent_dokumenti            TO service_role;
GRANT ALL ON klijent_komunikacija         TO service_role;
GRANT SELECT ON klijenti_retention_candidates TO service_role;

-- Sekvence (ako postoje)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO service_role;
