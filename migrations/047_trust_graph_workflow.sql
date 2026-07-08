-- ============================================================================
-- Vindex AI — Migracija 047: Trust Scores, Memory Graph, Workflow Engine
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: posle 046
--
-- Kreira:
--   1. Trust score kolone u memory_entries
--   2. memory_graph_edges — eksplicitne veze između entiteta
--   3. workflow_templates — predlošci za životni ciklus predmeta
--   4. workflow_instances — aktivni workflow po predmetu
--   5. workflow_steps — koraci workflow-a sa praćenjem i eskalacijom
-- ============================================================================

-- ─── 1. Trust Score kolone u memory_entries ──────────────────────────────────

ALTER TABLE memory_entries
    ADD COLUMN IF NOT EXISTS confidence      NUMERIC(3,2) DEFAULT 1.0
                             CHECK (confidence >= 0 AND confidence <= 1),
    ADD COLUMN IF NOT EXISTS izvor           TEXT         DEFAULT 'manual'
                             CHECK (izvor IN ('manual', 'auto', 'korekcija', 'benchmark')),
    ADD COLUMN IF NOT EXISTS potvrde_count   INT          DEFAULT 1,
    ADD COLUMN IF NOT EXISTS potvrdjeno_od   TEXT[]       DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS expires_at      DATE,
    ADD COLUMN IF NOT EXISTS zastarela       BOOLEAN      DEFAULT FALSE;

-- Auto sources start with lower confidence
UPDATE memory_entries SET confidence = 0.6 WHERE izvor = 'auto' AND confidence = 1.0;

CREATE INDEX IF NOT EXISTS idx_memory_trust ON memory_entries (confidence, zastarela, expires_at);

-- ─── 2. Memory Graph Edges — eksplicitne veze između entiteta ────────────────

CREATE TABLE IF NOT EXISTS memory_graph_edges (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id UUID        NOT NULL REFERENCES kancelarije(id),
    -- Source node
    from_type      TEXT        NOT NULL
                   CHECK (from_type IN ('partner', 'klijent', 'sudija', 'predmet', 'argument', 'strategija')),
    from_id        TEXT        NOT NULL,
    from_naziv     TEXT,
    -- Target node
    to_type        TEXT        NOT NULL
                   CHECK (to_type IN ('partner', 'klijent', 'sudija', 'predmet', 'argument', 'strategija')),
    to_id          TEXT        NOT NULL,
    to_naziv       TEXT,
    -- Edge data
    relacija       TEXT        NOT NULL,
    predmet_id     UUID,
    ishod          TEXT,
    snaga          NUMERIC(3,2) DEFAULT 1.0,
    kontekst       TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE memory_graph_edges ENABLE ROW LEVEL SECURITY;
CREATE POLICY "mge_firma_read" ON memory_graph_edges FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_graph_from ON memory_graph_edges (kancelarija_id, from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_graph_to   ON memory_graph_edges (kancelarija_id, to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_graph_rel  ON memory_graph_edges (kancelarija_id, relacija);

GRANT SELECT, INSERT ON memory_graph_edges TO service_role;

-- ─── 3. Workflow Templates — predlošci životnog ciklusa ───────────────────────

CREATE TABLE IF NOT EXISTS workflow_templates (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id UUID        REFERENCES kancelarije(id),
    naziv          TEXT        NOT NULL,
    tip_predmeta   TEXT,
    opis           TEXT,
    -- JSON lista koraka: [{"naziv":"..","opis":"..","rok_dana":5,"auto_assign":"partner","eskalacija_dana":3}]
    koraci         JSONB       NOT NULL DEFAULT '[]',
    aktivan        BOOLEAN     DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE workflow_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "wt_firma_read" ON workflow_templates FOR SELECT
    USING (
        kancelarija_id IS NULL
        OR kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

GRANT SELECT, INSERT, UPDATE ON workflow_templates TO service_role;

-- ─── 4. Workflow Instances — aktivni workflow po predmetu ─────────────────────

CREATE TABLE IF NOT EXISTS workflow_instances (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id  UUID        NOT NULL REFERENCES kancelarije(id),
    predmet_id      UUID        NOT NULL,
    template_id     UUID        REFERENCES workflow_templates(id),
    naziv           TEXT        NOT NULL,
    kreirao_uid     TEXT        NOT NULL,
    status          TEXT        DEFAULT 'aktivan'
                    CHECK (status IN ('aktivan', 'pauziran', 'zavrsen', 'otkazan')),
    current_step    INT         DEFAULT 0,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE workflow_instances ENABLE ROW LEVEL SECURITY;
CREATE POLICY "wi_firma_read" ON workflow_instances FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_wi_predmet ON workflow_instances (predmet_id, status);
CREATE INDEX IF NOT EXISTS idx_wi_firma   ON workflow_instances (kancelarija_id, status);

GRANT SELECT, INSERT, UPDATE ON workflow_instances TO service_role;

-- ─── 5. Workflow Steps — koraci sa praćenjem i eskalacijom ────────────────────

CREATE TABLE IF NOT EXISTS workflow_steps (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID        NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    kancelarija_id  UUID        NOT NULL,
    step_idx        INT         NOT NULL,
    naziv           TEXT        NOT NULL,
    opis            TEXT,
    assigned_uid    TEXT,
    status          TEXT        DEFAULT 'ceka'
                    CHECK (status IN ('ceka', 'aktivan', 'zavrseno', 'preskoceno', 'eskaliran')),
    rok_datum       DATE,
    eskalacija_dana INT         DEFAULT 3,
    completed_at    TIMESTAMPTZ,
    ishod           TEXT,
    komentar        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ws_firma_read" ON workflow_steps FOR SELECT
    USING (
        kancelarija_id IN (
            SELECT kancelarija_id FROM kancelarija_clanovi
            WHERE user_id = auth.uid()::text AND status = 'aktivan'
        )
        OR kancelarija_id IN (
            SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
        )
    );

CREATE INDEX IF NOT EXISTS idx_ws_workflow ON workflow_steps (workflow_id, step_idx);
CREATE INDEX IF NOT EXISTS idx_ws_assigned ON workflow_steps (assigned_uid, status);
CREATE INDEX IF NOT EXISTS idx_ws_eskal    ON workflow_steps (rok_datum, status) WHERE status = 'aktivan';

GRANT SELECT, INSERT, UPDATE ON workflow_steps TO service_role;

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 047_trust_graph_workflow uspesno primenjena.';
    RAISE NOTICE '  1. memory_entries: trust score kolone (confidence, izvor, potvrde_count, expires_at, zastarela)';
    RAISE NOTICE '  2. memory_graph_edges: eksplicitni graf veza izmedju entiteta';
    RAISE NOTICE '  3. workflow_templates: predlosci zivotnog ciklusa predmeta';
    RAISE NOTICE '  4. workflow_instances: aktivni workflow po predmetu';
    RAISE NOTICE '  5. workflow_steps: koraci sa eskalacijom i pracenjem';
END $$;
