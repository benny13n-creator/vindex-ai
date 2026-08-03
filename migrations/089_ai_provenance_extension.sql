-- ============================================================================
-- Vindex AI — Migracija 089: AI Provenance Extension (Mission Atlas)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 088.
--
-- Kontekst: migracija 043 (Security Bulletproof, 2026-07-07) je već napravila
-- `ai_forensics` — tabelu i namenu skoro identičnu ovoj misiji ("Omogućava
-- potpunu rekonstrukciju bilo kog AI odgovora čak i godinama kasnije"), ali
-- security/ai_forensics.py::ForensicsRecord/log_ai_call_sync nikad nisu bili
-- pozvani ni sa jednog od ~130 AI pozivnih mesta (potvrđeno gre-om pre ove
-- migracije) — infrastruktura je postojala, nije bila povezana. Mission
-- Atlas (2026-08-03) povezuje `shared/ai_client.py`'s već postojeći SEC-003
-- patch point (Completions.create/AsyncCompletions.create/Embeddings.create,
-- presretnuti na nivou klase za SVAKI poziv u aplikaciji) da automatski piše
-- u ovu tabelu — ova migracija samo DODAJE kolone koje taj wrapper ume da
-- popuni a stara šema nije imala, i dodaje immutability zaštitu koja je
-- nedostajala.
--
-- Dodaje:
--   1. Nove kolone na `ai_forensics` (ADD COLUMN IF NOT EXISTS — bezbedno za
--      ponovno pokretanje, isti idiom kao migracija 072/073).
--   2. UPDATE-blokirajući trigger (immutability, Phase 6) — NAMERNO ne
--      blokira i DELETE: services/retention_service.py::_cleanup_ai_forensics
--      već legitimno briše redove starije od AI_FORENSICS_RETENTION_DAYS radi
--      GDPR storage-limitation usklađenosti — kopiranje audit_immutable's
--      punog UPDATE+DELETE bloka bi pokvarilo tu postojeću, ispravnu
--      funkcionalnost. "Immutable" ovde znači "ne može se TIHO PREPISATI",
--      ne "nikad se ne sme obrisati po unapred poznatoj retencionoj politici".
--   3. Indeksi za replay upite (correlation_id, predmet_id, module_name).
-- ============================================================================

ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS tenant_id                 TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS predmet_id                TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS document_id               TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS module_name               TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS operation_name            TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS model_provider            TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS model_version             TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS system_prompt_hash        VARCHAR(64);
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS user_prompt_hash          VARCHAR(64);
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS retrieved_context_ids     JSONB DEFAULT '[]';
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS knowledge_sources         JSONB DEFAULT '[]';
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS retrieval_query           TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS confidence_score          NUMERIC;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS hallucination_check_result TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS parent_event_id           UUID;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS correlation_id            TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS audit_reference           TEXT;
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS status                    TEXT DEFAULT 'success';
ALTER TABLE ai_forensics ADD COLUMN IF NOT EXISTS error_message             TEXT;

-- unique_ai_action_id (mission's schema field) — ai_forensics.id already
-- serves this purpose (UUID PRIMARY KEY DEFAULT gen_random_uuid()) since
-- migration 043; no new column needed, documented here for traceability
-- against the mission's own required-field list.

-- ─── Immutability (Phase 6) — UPDATE-only block, DELETE deliberately allowed ──

CREATE OR REPLACE FUNCTION protect_ai_forensics_from_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RAISE EXCEPTION 'ai_forensics tabela je zaštićena — UPDATE nije dozvoljen. Provenance zapisi su append-only. Ovo je pokušaj izmene AI provenance zapisa.';
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_ai_forensics_update ON ai_forensics;
CREATE TRIGGER trg_protect_ai_forensics_update
    BEFORE UPDATE ON ai_forensics
    FOR EACH ROW EXECUTE FUNCTION protect_ai_forensics_from_update();

-- ─── Indeksi za replay/traceability upite ────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ai_forensics_correlation_id ON ai_forensics (correlation_id);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_predmet_id     ON ai_forensics (predmet_id);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_module_name    ON ai_forensics (module_name);
CREATE INDEX IF NOT EXISTS idx_ai_forensics_status         ON ai_forensics (status) WHERE status = 'error';

COMMENT ON TABLE ai_forensics IS
    'AI Provenance & Decision Traceability (Mission Atlas, 2026-08-03) — svaki AI poziv u aplikaciji '
    'upisuje se ovde automatski preko shared/ai_client.py-ovog kanonskog wrapper-a (isti presretnuti '
    'sloj kao SEC-003 prompt guard). Append-only (UPDATE blokiran triggerom); DELETE dozvoljen samo '
    'preko services/retention_service.py-ove retencione politike (AI_FORENSICS_RETENTION_DAYS), ne '
    'ad hoc. Čitanje: SELECT * FROM ai_forensics WHERE correlation_id=... ili predmet_id=... ORDER BY started_at.';

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 089 završena: ai_forensics prošireno za AI Provenance (Mission Atlas).';
    RAISE NOTICE 'VAŽNO: Verifikujte da trigger trg_protect_ai_forensics_update radi:';
    RAISE NOTICE '  UPDATE ai_forensics SET model=''test'' WHERE FALSE;';
    RAISE NOTICE 'Pre ovoga: AI Provenance capture je već aktivan u kodu (shared/ai_client.py), ali';
    RAISE NOTICE 'upisuje samo u legacy kolone (043) dok se ova migracija ne pokrene -- fail-soft fallback,';
    RAISE NOTICE 'ne greška. Posle ovoga: puna šema (correlation_id, predmet_id, model_provider, itd.) se popunjava.';
END $$;
