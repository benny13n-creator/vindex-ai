-- Vindex AI — Learning Loop (Outcome Feedback Engine + Collective Intelligence)
-- Pokrenuti u Supabase SQL Editor

-- outcome_log: ishod i presudni faktori svakog zatvorenog predmeta
CREATE TABLE IF NOT EXISTS outcome_log (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id          UUID          NOT NULL UNIQUE,
    user_id             UUID          NOT NULL,
    ishod               TEXT          NOT NULL CHECK (ishod IN ('pobeda','poraz','nagodba','odustajanje')),
    presudni_faktori    TEXT[]        DEFAULT '{}',
    tip_spora           TEXT,
    trajanje_meseci     INTEGER,
    vrednost_spora_rsd  NUMERIC(14,2),
    komentar            TEXT,
    created_at          TIMESTAMPTZ   DEFAULT now(),
    updated_at          TIMESTAMPTZ   DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outcome_log_user  ON outcome_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_log_tip   ON outcome_log(user_id, tip_spora);
ALTER TABLE outcome_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "outcome_log_own" ON outcome_log;
CREATE POLICY "outcome_log_own" ON outcome_log FOR ALL USING (auth.uid() = user_id);

-- case_patterns: agregirani faktori uspeha/poraza po tipu spora
CREATE TABLE IF NOT EXISTS case_patterns (
    id         UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID    NOT NULL,
    tip_spora  TEXT    NOT NULL,
    faktor     TEXT    NOT NULL,
    pobede     INTEGER DEFAULT 0,
    porazi     INTEGER DEFAULT 0,
    ukupno     INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, tip_spora, faktor)
);
CREATE INDEX IF NOT EXISTS idx_case_patterns_user ON case_patterns(user_id, tip_spora);
ALTER TABLE case_patterns ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "case_patterns_own" ON case_patterns;
CREATE POLICY "case_patterns_own" ON case_patterns FOR ALL USING (auth.uid() = user_id);

-- recommendation_log: svaka AI preporuka + feedback
CREATE TABLE IF NOT EXISTS recommendation_log (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    predmet_id       UUID,
    tip_preporuke    TEXT,
    tekst_preporuke  TEXT,
    kontekst         JSONB       DEFAULT '{}',
    prihvacena       BOOLEAN,
    ishod_pozitivan  BOOLEAN,
    confidence_score INTEGER,
    created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rec_log_user    ON recommendation_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rec_log_predmet ON recommendation_log(predmet_id, created_at DESC);
ALTER TABLE recommendation_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "rec_log_own" ON recommendation_log;
CREATE POLICY "rec_log_own" ON recommendation_log FOR ALL USING (auth.uid() = user_id);
