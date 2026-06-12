-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Supabase migracija v3
-- Novi moduli: Usage Analytics + Notification Engine
--
-- Pokrenite SAMO ovaj fajl u Supabase SQL Editoru.
-- Bezbedno za ponovljeno pokretanje (CREATE TABLE IF NOT EXISTS).
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. USAGE_EVENTS — tračking korišćenja funkcija ─────────────────────────
-- Svaki poziv analytics/track upisuje jedan red.
-- Koristi se za aggregirane statistike: top funkcije, top predmeti, aktivnost.

CREATE TABLE IF NOT EXISTS public.usage_events (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  feature    TEXT        NOT NULL,
  action     TEXT        NOT NULL,
  predmet_id UUID        REFERENCES public.predmeti(id) ON DELETE SET NULL,
  metadata   JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS usage_events_user_created_idx
  ON public.usage_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS usage_events_feature_idx
  ON public.usage_events(feature, created_at DESC);

ALTER TABLE public.usage_events ENABLE ROW LEVEL SECURITY;

-- Korisnik upisuje samo sopstvene evente
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'usage_events' AND policyname = 'usage_events_insert_own'
  ) THEN
    CREATE POLICY "usage_events_insert_own" ON public.usage_events
      FOR INSERT WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

-- Backend (service_role) ima pun pristup
GRANT SELECT, INSERT ON public.usage_events TO service_role;


-- ─── 2. NOTIFICATIONS — obaveštenja za advokate ──────────────────────────────
-- Generiše ih backend automatski (rokovi, neaktivnost, konflikti).
-- Advokat ih vidi i oznacava kao procitane.

CREATE TABLE IF NOT EXISTS public.notifications (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tip        TEXT        NOT NULL,
  naslov     TEXT        NOT NULL,
  poruka     TEXT        NOT NULL,
  predmet_id UUID        REFERENCES public.predmeti(id) ON DELETE CASCADE,
  prioritet  TEXT        NOT NULL DEFAULT 'normalan'
                         CHECK (prioritet IN ('hitan', 'normalan', 'info')),
  procitano  BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS notifications_user_created_idx
  ON public.notifications(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS notifications_user_unread_idx
  ON public.notifications(user_id, procitano)
  WHERE procitano = FALSE;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Korisnik cita sopstvena obaveštenja
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'notifications' AND policyname = 'notifications_select_own'
  ) THEN
    CREATE POLICY "notifications_select_own" ON public.notifications
      FOR SELECT USING (auth.uid() = user_id);
  END IF;
END $$;

-- Korisnik može da update (procitano = true) samo sopstvena
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'notifications' AND policyname = 'notifications_update_own'
  ) THEN
    CREATE POLICY "notifications_update_own" ON public.notifications
      FOR UPDATE USING (auth.uid() = user_id);
  END IF;
END $$;

-- Backend (service_role) ima pun pristup
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notifications TO service_role;
