-- Migration 022: Weekly digest email opt-in
-- Run in Supabase SQL Editor

-- Add nedeljni column to korisnik_email_notif (opt-in for weekly digest)
ALTER TABLE korisnik_email_notif
  ADD COLUMN IF NOT EXISTS nedeljni BOOLEAN NOT NULL DEFAULT TRUE;

-- Allow NULL for predmet_id in email_notif_log (weekly digest has no specific predmet)
ALTER TABLE email_notif_log
  ALTER COLUMN predmet_id DROP NOT NULL;
