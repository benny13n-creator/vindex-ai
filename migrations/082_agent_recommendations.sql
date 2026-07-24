-- Migracija 082 — agent_recommendations
-- KORAK B: Autonomni "Background" Action Agenti (2026-07-24)
--
-- Skladiste za proaktivne preporuke koje generisu pozadinski agenti
-- (services/agent_tasks/court_portal_watcher.py, precedents_radar.py),
-- pregledane/prihvacene/odbacene preko routers/agent_notifications.py.
--
-- dedup_key sprecava da isti agent isti dan-za-danom iznova kreira ISTU
-- preporuku (npr. ista promena statusa na portalu, ista sudska odluka) --
-- UNIQUE(user_id, dedup_key) + upsert-sa-ignore na insert strani.

CREATE TABLE IF NOT EXISTS agent_recommendations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    predmet_id   UUID REFERENCES predmeti(id) ON DELETE CASCADE,
    agent_type   TEXT NOT NULL CHECK (agent_type IN ('court_portal_watcher', 'precedents_radar')),
    naslov       TEXT NOT NULL,
    opis         TEXT,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedup_key    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    UNIQUE (user_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_recommendations_user_status
    ON agent_recommendations (user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_recommendations_predmet
    ON agent_recommendations (predmet_id);

ALTER TABLE agent_recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_recommendations_own_select"
    ON agent_recommendations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "agent_recommendations_own_update"
    ON agent_recommendations FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- INSERT se radi isključivo preko service-role klijenta iz pozadinskih
-- agenata (workers/background_agents.py) -- namerno nema INSERT policy za
-- obične korisnike, isti obrazac kao ostale sistemski-generisane tabele
-- (npr. audit_immutable, portal_status_log).

COMMENT ON TABLE agent_recommendations IS
    'Proaktivne preporuke pozadinskih agenata (KORAK B, 2026-07-24). '
    'dedup_key = agent-specifičan ključ (npr. "portal:{praceni_predmet_id}:{status_datum}" '
    'ili "precedent:{predmet_id}:{decision_number}") koji sprečava dupliranje preporuke '
    'na sledećem cron run-u.';
