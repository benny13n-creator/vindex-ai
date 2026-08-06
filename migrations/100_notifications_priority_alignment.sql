-- ============================================================================
-- Vindex AI — Migration 100: Align notifications.prioritet CHECK constraint
-- with the vocabulary the application code actually writes.
--
-- Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
-- Trigger Engine.
--
-- FOUND: migration 009 (2026-ish) declared
--   prioritet TEXT CHECK (prioritet IN ('hitan', 'normalan', 'info'))
-- but routers/notifications.py::NOTIF_TIPOVI (the table every insert in this
-- file has always read its own priority value from) uses a DIFFERENT,
-- 5-value vocabulary: 'urgent'/'high'/'normal'/'low'/'info'. Only 'info'
-- overlaps between the two. Every insert whose NOTIF_TIPOVI priority is
-- 'urgent', 'high', or 'low' (the MAJORITY of the 16 declared notification
-- types — hitan_rok, rok_3, rok_1, rociste_sutra, saradnja_predmet,
-- faktura_kasnjenje, neaktivnost, predmet_zatvoren) would violate this
-- CHECK constraint and fail to insert — caught by _generate_notifications'
-- own bare try/except (routers/notifications.py), silently logged, never
-- surfaced. Confirmed via code read: no other migration ever widened this
-- constraint, and no other file in the repo writes to `notifications`.
--
-- This migration aligns the constraint with NOTIF_TIPOVI's own,
-- already-canonical (Program Omega Sprint 006, shared/attention_priority.py
-- ::NOTIFICATIONS_TO_CANONICAL) vocabulary. Removing 'hitan'/'normalan' from
-- the allowed list is safe: as of Sprint 006, no code path writes those
-- values anymore (both were fixed to derive from NOTIF_TIPOVI instead) — a
-- CHECK constraint only validates NEW writes, never invalidates rows already
-- stored under the old constraint.
--
-- Bezbedno za ponovljeno pokretanje.
-- Pokreni SAMO ovaj fajl u Supabase SQL Editoru (isti obrazac kao svaka
-- prethodna migracija u ovom projektu — osnivac pokrece rucno).
-- ============================================================================

ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_prioritet_check;

ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_prioritet_check
  CHECK (prioritet IN ('urgent', 'high', 'normal', 'low', 'info'));

-- Also widen the DEFAULT to match — 'normalan' is no longer a valid value
-- under the new constraint (it would itself violate the CHECK it now sits
-- next to on any insert that omits `prioritet` entirely).
ALTER TABLE public.notifications
  ALTER COLUMN prioritet SET DEFAULT 'normal';
