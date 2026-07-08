-- ============================================================================
-- Vindex AI — Migracija 046: Firm Memory Engine
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: posle 045
--
-- Kreira:
--   1. memory_entries      — generalne memorije o ponašanju (partner/klijent/sudija)
--   2. partner_profiles    — profil svakog partnera (preferencije, odbijene strategije)
--   3. judge_patterns      — obrazci ponašanja sudija
--   4. client_memory       — memorija o klijentima (stavovi, preferencije)
--   5. tip_korekcije kolona u ai_corrections
-- ============================================================================

-- ─── 1. tip_korekcije u ai_corrections ───────────────────────────────────────
ALTER TABLE ai_corrections
    ADD COLUMN IF NOT EXISTS tip_korekcije TEXT,
    ADD COLUMN IF NOT EXISTS partner_uid   TEXT;

-- ─── 2. memory_entries — generalne memorije o ponašanju ──────────────────────

CREATE TABLE IF NOT EXISTS memory_entries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id   UUID        NOT NULL REFERENCES kancelarije(id),
    user_id          UUID,                     -- koji korisnik je kreirao memoriju
    entity_type      TEXT        NOT NULL,     -- 'partner'|'klijent'|'sudija'|'firma'|'predmet'
    entity_id        TEXT        NOT NULL,     -- uid partnera / ime sudije / id klijenta
    entity_name      TEXT,                     -- human-readable ime
    tip              TEXT        NOT NULL,     -- 'preferencija'|'odbijanje'|'obrazac'|'napomena'
    sadrzaj          TEXT        NOT NULL,     -- sama memorija
    kontekst         TEXT,                     -- dodatni kontekst (predmet_id, etc.)
    vaznost          TEXT        DEFAULT 'normalna'
                     CHECK (vaznost IN ('visoka', 'normalna', 'niska')),
    aktivan          BOOLEAN     DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE memory_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "memory_firma_read" ON memory_entries FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_memory_firma       ON memory_entries (kancelarija_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_memory_entity      ON memory_entries (entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_memory_tip         ON memory_entries (tip, aktivan);

GRANT SELECT, INSERT, UPDATE ON memory_entries TO service_role;

-- ─── 3. partner_profiles — profil pisanja i preferencija partnera ─────────────

CREATE TABLE IF NOT EXISTS partner_profiles (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id       UUID        NOT NULL REFERENCES kancelarije(id),
    partner_uid          TEXT        NOT NULL,
    partner_ime          TEXT,
    -- Stilske preferencije
    preferira_krace      BOOLEAN     DEFAULT FALSE,
    preferira_bullet     BOOLEAN     DEFAULT FALSE,
    preferira_formalan   BOOLEAN     DEFAULT TRUE,
    -- Odbijene strategije (JSON lista tekstova)
    odbijene_strategije  JSONB       DEFAULT '[]',
    -- Preferirane fraze koje partner koristi
    preferirane_fraze    JSONB       DEFAULT '[]',
    -- Oblasti prava u kojima je specijalista
    oblasti_specijalizacije JSONB    DEFAULT '[]',
    -- Agregati
    ukupno_korekcija     INT         DEFAULT 0,
    prosecna_izmena_pct  NUMERIC(5,2) DEFAULT 0,
    -- Slobodni napomene
    napomene             TEXT,
    last_updated         TIMESTAMPTZ DEFAULT NOW(),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (kancelarija_id, partner_uid)
);

ALTER TABLE partner_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "pp_firma_read" ON partner_profiles FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_pp_firma_partner ON partner_profiles (kancelarija_id, partner_uid);

GRANT SELECT, INSERT, UPDATE ON partner_profiles TO service_role;

-- ─── 4. judge_patterns — obrazci ponašanja sudija ─────────────────────────────

CREATE TABLE IF NOT EXISTS judge_patterns (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id       UUID        NOT NULL REFERENCES kancelarije(id),
    sudija_ime           TEXT        NOT NULL,
    sud                  TEXT,
    oblast_prava         TEXT,
    -- Procesne preference
    insistira_na         JSONB       DEFAULT '[]',  -- procesne forme na kojima insistira
    odbija               JSONB       DEFAULT '[]',  -- šta redovno odbija
    -- Statistika ishoda
    pobede               INT         DEFAULT 0,
    porazi               INT         DEFAULT 0,
    nagodbe              INT         DEFAULT 0,
    -- Slobodni opis
    opis_ponasanja       TEXT,
    napomene             TEXT,
    pouzdanost           TEXT        DEFAULT 'niska'
                         CHECK (pouzdanost IN ('visoka', 'srednja', 'niska')),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (kancelarija_id, sudija_ime, sud)
);

ALTER TABLE judge_patterns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "jp_firma_read" ON judge_patterns FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_jp_firma_sudija ON judge_patterns (kancelarija_id, sudija_ime);
CREATE INDEX IF NOT EXISTS idx_jp_oblast       ON judge_patterns (oblast_prava);

GRANT SELECT, INSERT, UPDATE ON judge_patterns TO service_role;

-- ─── 5. client_memory — memorija o klijentima ────────────────────────────────

CREATE TABLE IF NOT EXISTS client_memory (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id       UUID        NOT NULL REFERENCES kancelarije(id),
    klijent_id           UUID,       -- FK na klijenti tabelu (opcionalno)
    klijent_ime          TEXT        NOT NULL,
    -- Preferencije
    prihvata_nagodbu     BOOLEAN,    -- NULL = nepoznato, FALSE = nikad ne prihvata
    preferira_brze       BOOLEAN     DEFAULT FALSE,
    komunikacija_tip     TEXT,       -- 'email'|'telefon'|'lično'|'whatsapp'
    -- Karakteristike
    rizik_profil         TEXT        DEFAULT 'srednji'
                         CHECK (rizik_profil IN ('visok', 'srednji', 'nizak')),
    -- Istorija odluka (JSON lista)
    kljucne_odluke       JSONB       DEFAULT '[]',
    -- Slobodne napomene
    napomene             TEXT,
    oznake               TEXT[]      DEFAULT '{}',
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (kancelarija_id, klijent_ime)
);

ALTER TABLE client_memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY "cm_firma_read" ON client_memory FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_cm_firma_klijent ON client_memory (kancelarija_id, klijent_ime);
CREATE INDEX IF NOT EXISTS idx_cm_klijent_id    ON client_memory (klijent_id);

GRANT SELECT, INSERT, UPDATE ON client_memory TO service_role;

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 046_firm_memory uspesno primenjena.';
    RAISE NOTICE '  1. ai_corrections: dodati tip_korekcije i partner_uid';
    RAISE NOTICE '  2. memory_entries - generalne memorije o ponasanju';
    RAISE NOTICE '  3. partner_profiles - profil pisanja i preferencija partnera';
    RAISE NOTICE '  4. judge_patterns - obrasci ponasanja sudija';
    RAISE NOTICE '  5. client_memory - memorija o klijentima';
END $$;
