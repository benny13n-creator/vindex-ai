-- Migration 023: Stability prep za 500+ korisnika
-- Run in Supabase SQL Editor

-- 1. Index na ai_cache za brze expire eviction
CREATE INDEX IF NOT EXISTS ai_cache_expires_idx
  ON ai_cache (expires_at)
  WHERE expires_at < now() + interval '1 second';

-- 2. Index na email_notif_log za brze lookup po korisniku (weekly digest query)
CREATE INDEX IF NOT EXISTS email_notif_log_user_tip_idx
  ON email_notif_log (user_id, tip, created_at DESC);

-- 3. Index na predmeti za brze filtriranje po user_id + status (dashboard query)
CREATE INDEX IF NOT EXISTS predmeti_user_status_idx
  ON predmeti (user_id, status, created_at DESC)
  WHERE obrisan = false;

-- 4. Index na rokovi za brze lookup predstojećih rokova (kalendar + notifikacije)
CREATE INDEX IF NOT EXISTS rokovi_datum_user_idx
  ON rokovi (user_id, datum)
  WHERE obrisan = false;

-- 5. Partial index na klijenti za aktivan lookup
CREATE INDEX IF NOT EXISTS klijenti_user_aktivan_idx
  ON klijenti (user_id, created_at DESC)
  WHERE obrisan = false;

-- NAPOMENA: Supabase connection pooling
-- U Supabase Dashboard > Settings > Database > Connection Pooling:
-- Mode: Transaction (za kratke API pozive)
-- Pool size: 15 (za 4 Gunicorn workera × ~3 istovremena poziva)
-- Koristi SUPABASE_DB_URL (Transaction pooler) u env varijabli umesto direktne konekcije.
