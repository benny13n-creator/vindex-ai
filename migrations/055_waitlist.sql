-- ============================================================================
-- Vindex AI -- Migracija 055: waitlist (HITNO -- aktivno se koristi, nikad migrirano)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 054.
--
-- routers/waitlist.py (POST /waitlist/prijava) je AKTIVNO pozivan sa landing
-- stranice (static/vindex.js:430) i vec ima admin UI (lista/status) u
-- postojecem admin panelu -- za razliku od ostalih orphaned-schema nalaza
-- ove sesije, ovaj je verovatno stvarno costao izgubljene prijave/lead-ove
-- otkad forma postoji, jer INSERT u nepostojecu tabelu baca 500.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.waitlist (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    ime         text        NOT NULL,
    email       text        NOT NULL,
    firma       text        DEFAULT '',
    telefon     text        DEFAULT '',
    poruka      text        DEFAULT '',
    status      text        DEFAULT 'pending',   -- pending | contacted | active
    created_at  timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_idx ON public.waitlist (lower(email));

ALTER TABLE public.waitlist ENABLE ROW LEVEL SECURITY;

-- Samo service role cita/pise (API uvek koristi service key, vidi shared/deps.py _get_supa)
CREATE POLICY "service_only" ON public.waitlist USING (false);
