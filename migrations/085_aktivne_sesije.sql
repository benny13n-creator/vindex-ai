-- ============================================================
-- Migracija 085 — Zaštita od deljenja naloga (session limiting)
-- Pokrenuti u Supabase Dashboard → SQL Editor
--
-- NAPOMENA (2026-07-26, Production Readiness Report 2026-07-25 #3):
-- ovaj fajl je originalno bio supabase_migrations/044_aktivne_sesije.sql
-- -- broj 044 se kolizionirao sa migrations/044_anomaly_detection.sql
-- (odvojen, stariji fajl, i dalje na broju 044). Sadržaj je nepromenjen,
-- samo premešten u jedinstveni migrations/ direktorijum i prenumerisan
-- na sledeći slobodan broj. Ako je ovo VEĆ pokrenuto u produkciji pod
-- starim imenom, nema potrebe za ponovnim pokretanjem -- SQL je isti.
-- ============================================================

-- Tabela aktivnih sesija
CREATE TABLE IF NOT EXISTS public.aktivne_sesije (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  device_id            text        NOT NULL,
  poslednja_aktivnost  timestamptz NOT NULL DEFAULT now(),
  created_at           timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT uq_sesija_user_device UNIQUE (user_id, device_id)
);

-- Indeksi
CREATE INDEX IF NOT EXISTS idx_sesije_user_id
  ON public.aktivne_sesije (user_id);

CREATE INDEX IF NOT EXISTS idx_sesije_poslednja_aktivnost
  ON public.aktivne_sesije (poslednja_aktivnost);

-- RLS
ALTER TABLE public.aktivne_sesije ENABLE ROW LEVEL SECURITY;

-- Korisnik čita/menja samo svoje sesije
CREATE POLICY "sesije_sopstvene" ON public.aktivne_sesije
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Service role (backend) ima neograničen pristup
CREATE POLICY "sesije_service_role" ON public.aktivne_sesije
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ============================================================
-- Provjera (opciono)
-- SELECT * FROM public.aktivne_sesije LIMIT 5;
-- ============================================================
