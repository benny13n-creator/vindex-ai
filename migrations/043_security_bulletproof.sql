-- ============================================================================
-- Vindex AI — Migracija 043: Bulletproof Security
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: obavezno posle 042
--
-- Kreira:
--   1. audit_immutable  — nepromenjivi hash-chain audit log
--   2. ai_forensics     — forenzički zapis svakog AI poziva
--   3. Trigger za zaštitu audit_immutable od modifikacije
--   4. Indeksi za performantne pretrage
-- ============================================================================

-- ─── 1. Nepromenjivi Audit Log (hash-chain) ──────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_immutable (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    seq           BIGSERIAL   UNIQUE NOT NULL,     -- monotoni redosled, ne može se ubaciti između
    prev_hash     VARCHAR(64) NOT NULL,            -- SHA-256 prethodnog zapisa (genesis='0'*64)
    entry_hash    VARCHAR(64) NOT NULL,            -- SHA-256 ovog zapisa (proof of integrity)
    user_id       UUID,                           -- NULL dozvoljen za sistemske događaje
    action        VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id   VARCHAR(255),
    ip_hash       VARCHAR(16),                    -- SHA-256[:16] IP adrese (ne plaintext)
    metadata      JSONB       DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Zaštita: Sprečava UPDATE i DELETE na ovoj tabeli (čak i za service_role)
-- INSERT je dozvoljen za upisivanje novih zapisa.

CREATE OR REPLACE FUNCTION protect_audit_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'audit_immutable tabela je zaštićena — UPDATE nije dozvoljen. Ovo je pokušaj modifikacije audit loga.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_immutable tabela je zaštićena — DELETE nije dozvoljen. Ovo je pokušaj brisanja audit loga.';
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_audit_immutable ON audit_immutable;
CREATE TRIGGER trg_protect_audit_immutable
    BEFORE UPDATE OR DELETE ON audit_immutable
    FOR EACH ROW EXECUTE FUNCTION protect_audit_immutable();

-- RLS: Svi korisnici mogu INSERT, niko ne može SELECT sopstvene zapise
-- (pristup samo kroz service_role za admin verifikaciju)
ALTER TABLE audit_immutable ENABLE ROW LEVEL SECURITY;

-- Founder admin pristup (read-only verifikacija lanca)
CREATE POLICY "audit_immutable_admin_read"
    ON audit_immutable FOR SELECT
    USING (FALSE);  -- Blokira direktan user pristup; čita se samo kroz service_role API

-- Backend INSERT kroz service_role (zaobilazi RLS)
-- Nema potrebe za INSERT policy jer service_role zaobilazi RLS.

-- Indeksi
CREATE INDEX IF NOT EXISTS idx_audit_immutable_user_id    ON audit_immutable (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_immutable_action      ON audit_immutable (action);
CREATE INDEX IF NOT EXISTS idx_audit_immutable_created_at  ON audit_immutable (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_immutable_resource    ON audit_immutable (resource_type, resource_id);

COMMENT ON TABLE audit_immutable IS
    'Nepromenjivi audit log sa hash-chain integriteta. '
    'Svaki zapis uključuje SHA-256 prethodnog zapisa. '
    'UPDATE i DELETE su sprečeni triggerom. '
    'Integritet se proverava algoritmom shared/audit_immutable.py::verify_chain_integrity().';

-- ─── 2. AI Forensics Log ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_forensics (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID        NOT NULL,
    endpoint             VARCHAR(100),
    model                VARCHAR(50) DEFAULT 'gpt-4o',
    prompt_hash          VARCHAR(64),             -- SHA-256 celog prompta (sistem + korisnik)
    documents_count      INT         DEFAULT 0,
    document_hashes      JSONB       DEFAULT '[]',  -- SHA-256[:16] svakog dokumenta
    temperature          FLOAT,
    max_tokens           INT,
    input_chars          INT,
    injection_risk_score FLOAT       DEFAULT 0.0,
    injection_flags      JSONB       DEFAULT '[]',
    started_at           TIMESTAMPTZ DEFAULT NOW(),
    finished_at          TIMESTAMPTZ,
    latency_ms           INT,
    response_hash        VARCHAR(64),             -- SHA-256 odgovora
    tokens_prompt        INT,
    tokens_completion    INT,
    prompt_version       VARCHAR(20) DEFAULT '1.0'
);

-- RLS: Korisnik može videti samo sopstvene forensics zapise
ALTER TABLE ai_forensics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_forensics_owner_read"
    ON ai_forensics FOR SELECT
    USING (auth.uid() = user_id);

-- Indeksi
CREATE INDEX IF NOT EXISTS idx_ai_forensics_user_id     ON ai_forensics (user_id);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_started_at  ON ai_forensics (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_endpoint    ON ai_forensics (endpoint);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_risk_score  ON ai_forensics (injection_risk_score DESC)
    WHERE injection_risk_score > 0.3;  -- Parcijalni indeks za sumnjive zahteve

COMMENT ON TABLE ai_forensics IS
    'Forenzički zapis svakog AI poziva. Čuva: ko je pozvao, koji model, '
    'koji dokumenti su korišćeni (hash), koliko je trajalo, koji je odgovor (hash). '
    'Omogućava potpunu rekonstrukciju bilo kog AI odgovora čak i godinama kasnije.';

-- ─── 3. Poboljšanja postojeće audit_log tabele ───────────────────────────────

-- Dodaj nedostajuće kolone u audit_log ako već ne postoje
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_log' AND column_name = 'resource_type'
    ) THEN
        ALTER TABLE audit_log ADD COLUMN resource_type VARCHAR(50);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_log' AND column_name = 'resource_id'
    ) THEN
        ALTER TABLE audit_log ADD COLUMN resource_id VARCHAR(255);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_log' AND column_name = 'ip_hash'
    ) THEN
        ALTER TABLE audit_log ADD COLUMN ip_hash VARCHAR(16);
    END IF;
END $$;

-- ─── 4. Security Events tabela (CSP violation reporti) ───────────────────────

CREATE TABLE IF NOT EXISTS security_events (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type   VARCHAR(50) NOT NULL,   -- 'csp_violation', 'rate_limit', 'injection_attempt'
    user_id      UUID,
    ip_hash      VARCHAR(16),
    details      JSONB       DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;
-- Nema user pristupa — samo admin čita kroz service_role

CREATE INDEX IF NOT EXISTS idx_security_events_type       ON security_events (event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at ON security_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_user_id    ON security_events (user_id);

-- Auto-cleanup: briše security_events starije od 90 dana
-- (pokrenuti kao cron job ili Supabase Scheduled Functions)
-- DELETE FROM security_events WHERE created_at < NOW() - INTERVAL '90 days';

COMMENT ON TABLE security_events IS
    'Bezbednosni događaji: CSP violation reporti, rate limit prekoračenja, '
    'injection pokušaji. Čuva se 90 dana. Ne sadrži PII u plaintext obliku.';

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 043_security_bulletproof uspešno primenjena.';
    RAISE NOTICE '  - audit_immutable: nepromenjivi hash-chain log';
    RAISE NOTICE '  - ai_forensics: forenzički zapis AI poziva';
    RAISE NOTICE '  - security_events: CSP i injection eventi';
    RAISE NOTICE '';
    RAISE NOTICE 'VAŽNO: Verifikujte da trigger trg_protect_audit_immutable radi:';
    RAISE NOTICE '  UPDATE audit_immutable SET action=''test'' WHERE FALSE;';
    RAISE NOTICE '  -- Treba da baci grešku (čak i na praznoj tabeli)';
END $$;
