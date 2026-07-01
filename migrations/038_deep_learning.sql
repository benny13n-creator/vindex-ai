-- Vindex AI 2.0 — Deep Learning Loop
-- Root Cause Analysis, Lessons Learned, Counterfactual Learning, Knowledge Decay, Firm DNA
-- Pokrenuti u Supabase SQL Editor

-- ─── Proširenje outcome_log (Root Cause Analysis) ────────────────────────────
-- Belezi ZASTO je predmet izgubljen/dobijen, ne samo sta se desilo.
ALTER TABLE outcome_log ADD COLUMN IF NOT EXISTS uzroci TEXT[] DEFAULT '{}';
ALTER TABLE outcome_log ADD COLUMN IF NOT EXISTS kontekst_poraza TEXT;

-- ─── Proširenje recommendation_log (Knowledge Decay) ─────────────────────────
-- Preporuke imaju rok trajanja — zakon se menja, praksa se razvija.
ALTER TABLE recommendation_log ADD COLUMN IF NOT EXISTS valid_until DATE;
ALTER TABLE recommendation_log ADD COLUMN IF NOT EXISTS zastarela BOOLEAN DEFAULT FALSE;
ALTER TABLE recommendation_log ADD COLUMN IF NOT EXISTS zastarela_razlog TEXT;

-- ─── Lessons Learned ──────────────────────────────────────────────────────────
-- Automatski generisane lekcije posle svakog zatvorenog predmeta.
-- Institucijska memorija kancelarije — ostaje i kada senior partner ode.
CREATE TABLE IF NOT EXISTS lessons_learned (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID         NOT NULL,
    predmet_id      UUID,
    tip_spora       TEXT,
    lecija          TEXT         NOT NULL,
    kategorija      TEXT         DEFAULT 'ostalo'
                                 CHECK (kategorija IN (
                                     'strategija','procesna','dokaz',
                                     'komunikacija','finansijska','ostalo'
                                 )),
    vaznost         INT          DEFAULT 3 CHECK (vaznost BETWEEN 1 AND 5),
    primenjljivo_na TEXT[]       DEFAULT '{}',
    zastarela       BOOLEAN      DEFAULT FALSE,
    zastarela_razlog TEXT,
    zastarela_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lessons_user
    ON lessons_learned(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lessons_predmet
    ON lessons_learned(predmet_id);
CREATE INDEX IF NOT EXISTS idx_lessons_tip_aktuelne
    ON lessons_learned(user_id, tip_spora, zastarela);
CREATE INDEX IF NOT EXISTS idx_lessons_vaznost
    ON lessons_learned(user_id, vaznost DESC) WHERE zastarela = FALSE;

ALTER TABLE lessons_learned ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lessons_learned_own" ON lessons_learned;
CREATE POLICY "lessons_learned_own" ON lessons_learned
    FOR ALL USING (auth.uid() = user_id);

-- ─── Counterfactual Log ───────────────────────────────────────────────────────
-- "Sta bi se desilo da smo prihvatili nagodbu od 50.000 RSD?"
-- Sistem analizira alternativni razvoj dogadjaja.
CREATE TABLE IF NOT EXISTS counterfactual_log (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID         NOT NULL,
    predmet_id   UUID,
    hipoteza     TEXT         NOT NULL,
    tip_hipoteze TEXT         DEFAULT 'ostalo'
                              CHECK (tip_hipoteze IN (
                                  'nagodba','strateski','takticki','procesni','ostalo'
                              )),
    odgovor      TEXT,
    komentar     TEXT,
    ai_procena   TEXT,
    created_at   TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_counterfactual_user
    ON counterfactual_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_counterfactual_predmet
    ON counterfactual_log(predmet_id);

ALTER TABLE counterfactual_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "counterfactual_log_own" ON counterfactual_log;
CREATE POLICY "counterfactual_log_own" ON counterfactual_log
    FOR ALL USING (auth.uid() = user_id);

-- ─── Firm DNA ─────────────────────────────────────────────────────────────────
-- Obrasci ponasanja kancelarije ekstrahovani iz istorije predmeta.
-- "Kancelarija uvek angažuje veštaka u radnim sporovima"
-- Anti-churn: znanje ostaje u sistemu cak i kada partner ode.
CREATE TABLE IF NOT EXISTS firm_dna (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL,
    pattern     TEXT         NOT NULL,
    tip         TEXT         DEFAULT 'ostalo'
                             CHECK (tip IN (
                                 'argument','procesna','komunikacija','taktika','ostalo'
                             )),
    advokat     TEXT,
    frekvencija INT          DEFAULT 1,
    uzoraka     INT          DEFAULT 1,
    primer      TEXT,
    valid_until DATE,
    created_at  TIMESTAMPTZ  DEFAULT now(),
    updated_at  TIMESTAMPTZ  DEFAULT now(),
    UNIQUE (user_id, pattern)
);

CREATE INDEX IF NOT EXISTS idx_firm_dna_user
    ON firm_dna(user_id, frekvencija DESC);

ALTER TABLE firm_dna ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "firm_dna_own" ON firm_dna;
CREATE POLICY "firm_dna_own" ON firm_dna
    FOR ALL USING (auth.uid() = user_id);
