-- ============================================================================
-- Vindex AI — Migracija 045: Firm Intelligence Layer
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: posle 044
--
-- Kreira:
--   1. pinecone_namespace kolona u kancelarije (per-firma RAG)
--   2. ai_corrections — nevidljivo hvatanje korekcija AI outputa
--   3. firm_style_profile — automatski profil pisanja kancelarije
--   4. zakoni_monitoring — praćenje promena Sl. glasnika
--   5. zadaci — timski zadaci sa dodeljivanjem
--   6. case_profitability — ROI po predmetu (computed view)
--   7. case_benchmarks — anonimizovani podaci za mrežne efekte
-- ============================================================================

-- ─── 1. Per-firma Pinecone namespace ─────────────────────────────────────────

ALTER TABLE kancelarije
    ADD COLUMN IF NOT EXISTS pinecone_namespace TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS firma_slug         TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS logo_url           TEXT,
    ADD COLUMN IF NOT EXISTS adresa             TEXT,
    ADD COLUMN IF NOT EXISTS telefon            TEXT,
    ADD COLUMN IF NOT EXISTS settings           JSONB DEFAULT '{}';

-- Automatski generiši namespace za postojeće firme (slug iz ID-a)
UPDATE kancelarije
SET pinecone_namespace = 'firm_' || LEFT(REPLACE(id::text, '-', ''), 16)
WHERE pinecone_namespace IS NULL;

-- ─── 2. AI Corrections — nevidljivo hvatanje korekcija ───────────────────────

CREATE TABLE IF NOT EXISTS ai_corrections (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    kancelarija_id   UUID        REFERENCES kancelarije(id),
    predmet_id       UUID,
    context_type     TEXT        NOT NULL, -- 'drafting'|'analiza'|'copilot'|'briefing'|'nacrt'
    original_output  TEXT        NOT NULL, -- šta je AI generisao
    edited_output    TEXT        NOT NULL, -- šta je advokat sačuvao
    edit_distance    INT,                  -- Levenshtein distanca (meri koliko izmene)
    prompt_summary   TEXT,                 -- kratki opis prompta (ne ceo, za analizu)
    tip_dokumenta    TEXT,                 -- 'tuzba'|'ugovor'|'zalba'|'dopis'|'ostalo'
    processed        BOOLEAN     DEFAULT FALSE, -- da li je uključen u stil profil
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE ai_corrections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "corr_owner" ON ai_corrections FOR SELECT USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_corr_firma     ON ai_corrections (kancelarija_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_corr_user      ON ai_corrections (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_corr_unproc    ON ai_corrections (kancelarija_id) WHERE processed = FALSE;

GRANT SELECT, INSERT, UPDATE ON ai_corrections TO service_role;

-- ─── 3. Firm Style Profile — profil pisanja kancelarije ──────────────────────

CREATE TABLE IF NOT EXISTS firm_style_profile (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id   UUID        NOT NULL UNIQUE REFERENCES kancelarije(id),
    korekcija_count  INT         DEFAULT 0,
    stil_data        JSONB       DEFAULT '{
        "ton": "formalan",
        "duzina_recenice": "srednja",
        "preferira_bullet_liste": false,
        "preferira_numerisane_tacke": false,
        "izbegavane_fraze": [],
        "preferirane_fraze": [],
        "tip_dokumenta_stat": {},
        "prosecna_izmena_procenat": 0,
        "oblasti_prava": []
    }',
    last_updated     TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE firm_style_profile ENABLE ROW LEVEL SECURITY;
CREATE POLICY "fsp_member_read" ON firm_style_profile FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
    );

GRANT SELECT, INSERT, UPDATE ON firm_style_profile TO service_role;

-- ─── 4. Zakoni Monitoring — praćenje promena Sl. glasnika ────────────────────

CREATE TABLE IF NOT EXISTS zakoni_monitoring (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    naziv_zakona   TEXT        NOT NULL,
    izvor_url      TEXT,
    datum_objave   DATE        NOT NULL,
    sazetak        TEXT,                  -- AI-generisan sažetak izmene
    oblasti_prava  TEXT[]      DEFAULT '{}',  -- ['radno', 'poresko', ...]
    kljucni_termini TEXT[]     DEFAULT '{}',  -- termini za matching sa predmetima
    status         TEXT        DEFAULT 'aktivan', -- 'aktivan'|'arhiviran'
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(naziv_zakona, datum_objave)
);

CREATE INDEX IF NOT EXISTS idx_zakoni_datum   ON zakoni_monitoring (datum_objave DESC);
CREATE INDEX IF NOT EXISTS idx_zakoni_oblasti ON zakoni_monitoring USING GIN (oblasti_prava);

GRANT SELECT, INSERT, UPDATE ON zakoni_monitoring TO service_role;

-- ─── 5. Zadaci — timski zadaci sa dodeljivanjem ───────────────────────────────

CREATE TABLE IF NOT EXISTS zadaci (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id   UUID        REFERENCES kancelarije(id),
    predmet_id       UUID,
    kreirao_uid      TEXT        NOT NULL,
    dodeljen_uid     TEXT,                 -- user_id kome je dodeljen
    naziv            TEXT        NOT NULL,
    opis             TEXT,
    prioritet        TEXT        DEFAULT 'normalan'
                     CHECK (prioritet IN ('hitno', 'visoko', 'normalan', 'nisko')),
    status           TEXT        DEFAULT 'otvoreno'
                     CHECK (status IN ('otvoreno', 'u_toku', 'ceka', 'zavrseno', 'otkazano')),
    rok_datum        DATE,
    zavrseno_u       TIMESTAMPTZ,
    komentar         TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE zadaci ENABLE ROW LEVEL SECURITY;

-- Vide svi aktivni članovi kancelarije
CREATE POLICY "zadaci_firma_read" ON zadaci FOR SELECT
    USING (
        kreirao_uid = auth.uid()::text
        OR dodeljen_uid = auth.uid()::text
        OR kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
    );

CREATE INDEX IF NOT EXISTS idx_zadaci_firma     ON zadaci (kancelarija_id, status);
CREATE INDEX IF NOT EXISTS idx_zadaci_dodeljen  ON zadaci (dodeljen_uid, status);
CREATE INDEX IF NOT EXISTS idx_zadaci_predmet   ON zadaci (predmet_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON zadaci TO service_role;

-- ─── 6. Case Profitability — ROI po predmetu ────────────────────────────────

-- billing_entries mora imati link na predmet_id (proveriti u 003_billing.sql)
-- Ovo je view koji računa ROI: naplativo vreme × tarifa − troškovi

CREATE OR REPLACE VIEW case_profitability AS
SELECT
    p.id                    AS predmet_id,
    p.user_id,
    p.naziv                 AS predmet_naziv,
    p.tip                   AS predmet_tip,
    p.status                AS predmet_status,
    p.created_at            AS otvoren,

    -- Ukupno naplaćeno (iznos_rsd = already-calculated amount per entry)
    COALESCE(SUM(be.iznos_rsd), 0)::NUMERIC                        AS ukupno_naplaceno_rsd,
    COALESCE(SUM(be.sati), 0)::NUMERIC                             AS ukupno_sati,

    -- Fakturisano (obracunato = TRUE znači vezano za fakturu)
    COALESCE(SUM(CASE WHEN be.obracunato THEN be.iznos_rsd ELSE 0 END), 0)::NUMERIC
                                                                   AS fakturisano_rsd,
    -- Nefakturisano
    COALESCE(SUM(CASE WHEN NOT COALESCE(be.obracunato, FALSE) THEN be.iznos_rsd ELSE 0 END), 0)::NUMERIC
                                                                   AS nefakturisano_rsd,

    -- Broj unosa
    COUNT(be.id)                                                   AS broj_unosa,

    -- Poslednja aktivnost
    MAX(be.created_at)                                             AS poslednja_naplata

FROM predmeti p
LEFT JOIN billing_entries be ON be.predmet_id = p.id
GROUP BY
    p.id, p.user_id, p.naziv, p.tip, p.status, p.created_at;

GRANT SELECT ON case_profitability TO service_role;

-- ─── 7. Case Benchmarks — anonimizovani podaci za mrežne efekte ─────────────

CREATE TABLE IF NOT EXISTS case_benchmarks (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Anonimizovano: nema user_id, nema kancelarija_id, nema naziva
    tip_predmeta     TEXT        NOT NULL,
    oblast_prava     TEXT,
    trajanje_meseci  INT,
    vrednost_rsd     NUMERIC,
    ishod            TEXT,       -- 'pobeda'|'poraz'|'nagodba'
    sud_tip          TEXT,       -- 'osnovni'|'visi'|'apelacioni'|'vrhovni'
    regija           TEXT,       -- 'beograd'|'vojvodina'|'srbija_jug'|'srbija_zapad'
    naplaceno_rsd    NUMERIC,
    opt_in           BOOLEAN     DEFAULT FALSE,  -- korisnik eksplicitno dao saglasnost
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bench_tip   ON case_benchmarks (tip_predmeta, oblast_prava);
CREATE INDEX IF NOT EXISTS idx_bench_datum ON case_benchmarks (created_at DESC);

GRANT SELECT, INSERT ON case_benchmarks TO service_role;

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE '✓ Migracija 045_firm_intelligence uspešno primenjena.';
    RAISE NOTICE '  1. kancelarije.pinecone_namespace — per-firma RAG namespace';
    RAISE NOTICE '  2. ai_corrections — nevidljivo hvatanje korekcija AI outputa';
    RAISE NOTICE '  3. firm_style_profile — profil pisanja kancelarije';
    RAISE NOTICE '  4. zakoni_monitoring — praćenje promena Sl. glasnika';
    RAISE NOTICE '  5. zadaci — timski zadaci sa dodeljivanjem';
    RAISE NOTICE '  6. case_profitability (VIEW) — ROI po predmetu';
    RAISE NOTICE '  7. case_benchmarks — anonimizovani mrežni podaci';
END $$;
