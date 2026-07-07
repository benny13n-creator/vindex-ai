-- ============================================================================
-- Vindex AI — Migracija 044: Behavioral Anomaly Detection
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: obavezno posle 043
--
-- Kreira:
--   1. user_daily_activity — dnevne statistike po korisniku (bazni profil)
--   2. chain_anchors — spoljni ankeri hash-chain integriteta
--   3. RPC funkcija get_activity_averages za anomaly detection
-- ============================================================================

-- ─── 1. Dnevna aktivnost korisnika (bazni profil za anomaly detection) ───────

CREATE TABLE IF NOT EXISTS user_daily_activity (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL,
    date       DATE        NOT NULL,
    ai_calls   INT         DEFAULT 0,
    api_calls  INT         DEFAULT 0,
    ip_count   INT         DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

ALTER TABLE user_daily_activity ENABLE ROW LEVEL SECURITY;

-- Korisnik može videti sopstvenu aktivnost
CREATE POLICY "uda_owner_read"
    ON user_daily_activity FOR SELECT
    USING (auth.uid() = user_id);

-- Backend upisuje kroz service_role (zaobilazi RLS)

CREATE INDEX IF NOT EXISTS idx_uda_user_date ON user_daily_activity (user_id, date DESC);

-- Auto-cleanup: briše zapise starije od 90 dana
-- (pokrenuti periodično kao cron):
-- DELETE FROM user_daily_activity WHERE date < CURRENT_DATE - INTERVAL '90 days';

-- ─── 2. Chain Anchors tabela ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chain_anchors (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    date         DATE        NOT NULL UNIQUE,    -- jedan anchor po danu
    root_hash    VARCHAR(64) NOT NULL,           -- Merkle-style root hash
    record_count INT         DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Zaštita identična audit_immutable: UPDATE/DELETE zabranjeni
CREATE OR REPLACE FUNCTION protect_chain_anchors()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'chain_anchors je zaštićen — UPDATE nije dozvoljen.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'chain_anchors je zaštićen — DELETE nije dozvoljen.';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_chain_anchors ON chain_anchors;
CREATE TRIGGER trg_protect_chain_anchors
    BEFORE UPDATE OR DELETE ON chain_anchors
    FOR EACH ROW EXECUTE FUNCTION protect_chain_anchors();

ALTER TABLE chain_anchors ENABLE ROW LEVEL SECURITY;

-- Nema korisničkog pristupa — samo admin čita
CREATE POLICY "chain_anchors_deny_all"
    ON chain_anchors FOR SELECT
    USING (FALSE);

-- ─── 3. RPC: prosečna dnevna aktivnost korisnika ─────────────────────────────

CREATE OR REPLACE FUNCTION get_activity_averages(p_user_id UUID)
RETURNS TABLE (
    days_count   BIGINT,
    avg_ai_calls NUMERIC,
    avg_api_calls NUMERIC,
    avg_ip_count  NUMERIC
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        COUNT(*)                AS days_count,
        AVG(ai_calls)::NUMERIC  AS avg_ai_calls,
        AVG(api_calls)::NUMERIC AS avg_api_calls,
        AVG(ip_count)::NUMERIC  AS avg_ip_count
    FROM user_daily_activity
    WHERE user_id = p_user_id
      AND date >= CURRENT_DATE - INTERVAL '30 days'
      AND date < CURRENT_DATE;
$$;

GRANT EXECUTE ON FUNCTION get_activity_averages(UUID) TO service_role;

-- ─── 4. Dodaj GRANT za service_role na novim tabelama (ako nije automatski) ──

GRANT SELECT, INSERT, UPDATE ON user_daily_activity TO service_role;
GRANT SELECT, INSERT ON chain_anchors TO service_role;

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 044_anomaly_detection uspešno primenjena.';
    RAISE NOTICE '  - user_daily_activity: bazni profil korisničke aktivnosti';
    RAISE NOTICE '  - chain_anchors: spoljni ankeri hash-chain (INSERT-only)';
    RAISE NOTICE '  - get_activity_averages(): RPC za anomaly scoring';
    RAISE NOTICE '';
    RAISE NOTICE 'SLEDEĆI KORAK: Aktivirajte dnevni anchor cron job:';
    RAISE NOTICE '  python -c "import asyncio; from security.chain_anchor import anchor_today; asyncio.run(anchor_today())"';
END $$;
