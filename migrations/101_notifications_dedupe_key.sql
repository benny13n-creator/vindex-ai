-- ============================================================================
-- Vindex AI — Migration 101: notifications gets a dedupe_key, mirroring
-- case_actions' own already-proven concurrency pattern (migration 099).
--
-- Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
-- Trigger Engine, Phase 3 (Trigger Consolidation).
--
-- WHY: services/case_evolution.py::_consequence_project_case_actions_to_
-- notifications (new this sprint) projects case_actions' own deadline
-- findings (tip='PRIPREMITI_PODNESAK') into the notifications table, so a
-- lawyer sees the SAME deadline fact whether they look at Workspace or the
-- bell icon -- replacing routers/notifications.py's own independent
-- rok/hitan_rok detection (OMEGA-020, Sprint 006's own debt register). The
-- projection reuses case_actions' own stable per-fact `dedupe_key`
-- (`_stable_key("rociste", rociste_id)`) directly -- this column, plus a
-- partial UNIQUE index scoped to unread rows, is what makes the projection
-- idempotent and race-safe: exactly the same mechanism already proven for
-- case_actions itself, not a new pattern.
--
-- Bezbedno za ponovljeno pokretanje.
-- Pokreni SAMO ovaj fajl u Supabase SQL Editoru (osnivac pokrece rucno).
-- ============================================================================

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

-- Samo JEDNO nepročitano obaveštenje po (korisnik, činjenica). Isti obrazac
-- kao case_actions' own idx_case_actions_open_dedupe (migration 099) -- DB
-- ograničenje, ne aplikaciona logika, garantuje bezbednost pri konkurentnim
-- projekcijama (2 paralelna Case Evolution dogadjaja za isti predmet).
-- Partial (dedupe_key IS NOT NULL) jer stariji/ručno-kreirani redovi (npr.
-- neaktivnost, ili trigger_notifikacija-ovi budući pozivaoci bez sopstvenog
-- dedupe koncepta) nemaju i ne moraju imati dedupe_key -- ne ulaze u ovo
-- ograničenje.
CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_open_dedupe
  ON public.notifications(user_id, dedupe_key)
  WHERE procitano = FALSE AND dedupe_key IS NOT NULL;

COMMENT ON COLUMN public.notifications.dedupe_key IS
  'Stabilan identitet ČINJENICE (ne reda) za projekcije iz case_actions -- omogućava idempotentno kreiranje/ažuriranje/zatvaranje bez duplikata. NULL za notifikacije bez projektovanog izvora (npr. neaktivnost, ručni trigger_notifikacija pozivi).';
