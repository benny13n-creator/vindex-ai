-- Vindex AI 2.0 — Epistemic Confidence Layer
-- Svaki AI zakljucak mora znati sta zna, na cemu bazira i koliko sme da veruje sebi.
-- Pokrenuti u Supabase SQL Editor

-- ─── Lessons Learned — Confidence metadata ───────────────────────────────────
-- Status tok: predlog_ai → usvojena_praksa (partner potvrdi) | odbijena | zastarela
-- "Lekcija zasnovana na 4 predmeta, period 2024-2026, pouzdanost: niska"
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS broj_predmeta  INT           DEFAULT 1;
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS period_od      DATE;
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS period_do      DATE;
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS oblast_prava   TEXT;
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS status_lekcije TEXT          DEFAULT 'predlog_ai'
    CHECK (status_lekcije IN ('predlog_ai','usvojena_praksa','odbijena','zastarela'));
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS pouzdanost     TEXT          DEFAULT 'niska'
    CHECK (pouzdanost IN ('niska','srednja','visoka'));
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS potvrdio       UUID;
ALTER TABLE lessons_learned ADD COLUMN IF NOT EXISTS potvrdjeno_at  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_lessons_status
    ON lessons_learned(user_id, status_lekcije, pouzdanost DESC)
    WHERE zastarela = FALSE;

-- ─── Firm DNA — Verzionisanje ─────────────────────────────────────────────────
-- Kancelarije evoluiraju. DNA v1 → v2 → v3. Istorija organizacionog ucenja.
-- "Od 2028. kancelarija je promenila pristup privrednim sporovima."
ALTER TABLE firm_dna ADD COLUMN IF NOT EXISTS verzija     INT     DEFAULT 1;
ALTER TABLE firm_dna ADD COLUMN IF NOT EXISTS aktuelna    BOOLEAN DEFAULT TRUE;
ALTER TABLE firm_dna ADD COLUMN IF NOT EXISTS verzija_od  DATE    DEFAULT CURRENT_DATE;

-- Ukloni stari UNIQUE constraint koji ne uzima verziju u obzir
ALTER TABLE firm_dna DROP CONSTRAINT IF EXISTS firm_dna_user_id_pattern_key;

-- Novi UNIQUE: isti pattern moze postojati u razlicitim verzijama
CREATE UNIQUE INDEX IF NOT EXISTS idx_firm_dna_versioned
    ON firm_dna(user_id, pattern, verzija);

CREATE INDEX IF NOT EXISTS idx_firm_dna_aktuelna
    ON firm_dna(user_id, aktuelna, frekvencija DESC);

-- ─── Counterfactual Log — Disclaimer ─────────────────────────────────────────
-- Eksplicitno: ovo je simulacija, ne predikcija. UI ne moze da ignoriše.
ALTER TABLE counterfactual_log ADD COLUMN IF NOT EXISTS tip_odgovora TEXT DEFAULT 'simulacija'
    CHECK (tip_odgovora IN ('simulacija','procena','istorijski_obrazac'));
ALTER TABLE counterfactual_log ADD COLUMN IF NOT EXISTS disclaimer   TEXT DEFAULT
    'Ovo je simulacija zasnovana na dostupnim podacima i obrascima, a ne tvrdnja o tome sta bi se sigurno dogodilo.';

-- ─── Impact Metrics ───────────────────────────────────────────────────────────
-- Tvrdih brojki koje menjaju razgovor sa kupcem.
-- "AI preporuke prihvacene u 68% slucajeva. Win rate 72%. 8/23 lekcija potvrdjeno."
CREATE TABLE IF NOT EXISTS impact_metrics (
    id                             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                        UUID        NOT NULL,
    period_od                      DATE        NOT NULL,
    period_do                      DATE        NOT NULL,
    preporuke_prihvacene_procenat  FLOAT,
    preporuke_ocenjeno_n           INT         DEFAULT 0,
    lekcije_potvrdjene_n           INT         DEFAULT 0,
    lekcije_aktivne_n              INT         DEFAULT 0,
    predmeta_sa_ishodom            INT         DEFAULT 0,
    win_rate_procenat              FLOAT,
    avg_trajanje_meseci            FLOAT,
    created_at                     TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE impact_metrics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "impact_own" ON impact_metrics;
CREATE POLICY "impact_own" ON impact_metrics FOR ALL USING (auth.uid() = user_id);
