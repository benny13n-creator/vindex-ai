-- Vindex AI 2.0 — Faza 0: Decision Log + Proactive Alerts
-- Pokrenuti u Supabase SQL Editor

-- ─── Decision Log ─────────────────────────────────────────────────────────────
-- Svaka advokatska akcija se beleži sa kontekstom i alternativama.
-- Osnov za Legal Operating Memory i Organizational Intelligence.

CREATE TABLE IF NOT EXISTS decision_log (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL,
    predmet_id  UUID,
    akcija      TEXT         NOT NULL,
    kontekst    JSONB        DEFAULT '{}',
    alternative JSONB        DEFAULT '[]',
    urgentnost  TEXT         DEFAULT 'normalna'
                             CHECK (urgentnost IN ('normalna', 'visoka', 'hitna')),
    created_at  TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_log_user
    ON decision_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_decision_log_predmet
    ON decision_log(predmet_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_decision_log_akcija
    ON decision_log(akcija, created_at DESC);

-- RLS: korisnik vidi samo svoje odluke
ALTER TABLE decision_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "decision_log_own" ON decision_log;
CREATE POLICY "decision_log_own" ON decision_log
    FOR ALL USING (auth.uid() = user_id);

-- ─── Proactive Alerts ─────────────────────────────────────────────────────────
-- Automatski generisana upozorenja iz Event Bus-a.
-- Prikazuju se u UI (notification bell) i Morning Briefing-u.

CREATE TABLE IF NOT EXISTS proactive_alerts (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL,
    predmet_id  UUID,
    tip         TEXT         NOT NULL,
    naslov      TEXT         NOT NULL,
    opis        TEXT,
    urgentnost  TEXT         DEFAULT 'normalna'
                             CHECK (urgentnost IN ('normalna', 'visoka', 'hitna')),
    procitana   BOOLEAN      DEFAULT false,
    created_at  TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_alerts_user
    ON proactive_alerts(user_id, procitana, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_proactive_alerts_predmet
    ON proactive_alerts(predmet_id, created_at DESC);

-- RLS: korisnik vidi samo svoje alertove
ALTER TABLE proactive_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "proactive_alerts_own" ON proactive_alerts;
CREATE POLICY "proactive_alerts_own" ON proactive_alerts
    FOR ALL USING (auth.uid() = user_id);
