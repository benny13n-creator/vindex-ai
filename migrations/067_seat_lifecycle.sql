-- ============================================================================
-- Vindex AI — Migracija 067: Seat Lifecycle — jedinstven model mesta u firmi
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 066.
--
-- Kontekst: PermissionService/UsageService/Feature Registry (migracije 063-066)
-- daju JEDAN izvor istine za feature-pristup, kredite i tarifu. Nedostajao je
-- jedan izvor istine za KORISNIČKA MESTA (seats) — Enterprise tarifa (3
-- uključena mesta + 49€/mesečno po dodatnom, profiles.subscription_seats_extra
-- iz migracije 063) trenutno nema NIKAKVU proveru koliko mesta je zauzeto pre
-- slanja poziva. routers/kancelarija.py's pozovi_clana dozvoljava neograničen
-- broj pozivnica bez obzira na tarifu.
--
-- Postojeći model (3 stanja, migracija 018): pending / aktivan / odbijen —
-- uklanjanje člana je HARD DELETE (nema istorijski trag). Novi model (5
-- stanja, founder-ov zahtev): ACTIVE / INVITED / PENDING / SUSPENDED /
-- REMOVED — REMOVED je istorijski zapis (soft-delete), ne zauzima mesto.
--
-- Mapiranje starih → novih vrednosti (backfill ispod):
--   'aktivan' → 'ACTIVE'    (član aktivno koristi mesto — bez promene značenja)
--   'pending' → 'INVITED'   (poziv poslat, čeka prihvatanje — bez promene značenja)
--   'odbijen' → 'REMOVED'   (odbijena pozivnica — terminalno stanje, isto kao
--                            REMOVED semantički: ne zauzima mesto, trajni zapis)
--
-- 'PENDING' u novom modelu NIJE isto što i staro 'pending' — to je NOVO stanje
-- rezervisano za budući self-serve "zahtev za pridruživanje" tok (korisnik se
-- registruje i čeka odobrenje admina, umesto da ga admin prvi pozove). Danas
-- se ne piše nigde u kodu — dodato u CHECK constraint unapred da se izbegne
-- migracija enum-a kad se taj tok jednog dana doda (founder-ov eksplicitan
-- razlog: "Ako ne razmisliš sada... kasnije će biti migracija.").
-- ============================================================================

-- ── kancelarija_clanovi: prošireni lifecycle ─────────────────────────────────

ALTER TABLE public.kancelarija_clanovi DROP CONSTRAINT IF EXISTS kancelarija_clanovi_status_check;

ALTER TABLE public.kancelarija_clanovi
    ADD COLUMN IF NOT EXISTS suspended_at   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS removed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS removed_reason TEXT;

-- Backfill PRE dodavanja novog CHECK-a — stare vrednosti bi ga inače prekršile.
UPDATE public.kancelarija_clanovi SET status = 'ACTIVE'  WHERE status = 'aktivan';
UPDATE public.kancelarija_clanovi SET status = 'INVITED' WHERE status = 'pending';
UPDATE public.kancelarija_clanovi
    SET status = 'REMOVED', removed_reason = 'declined', removed_at = COALESCE(removed_at, now())
    WHERE status = 'odbijen';

ALTER TABLE public.kancelarija_clanovi
    ADD CONSTRAINT kancelarija_clanovi_status_check
    CHECK (status IN ('ACTIVE', 'INVITED', 'PENDING', 'SUSPENDED', 'REMOVED'));

ALTER TABLE public.kancelarija_clanovi ALTER COLUMN status SET DEFAULT 'INVITED';

COMMENT ON COLUMN public.kancelarija_clanovi.status IS
    'ACTIVE i INVITED troše mesto (iskorišćena_mesta = COUNT(ACTIVE) + COUNT(INVITED)). PENDING/SUSPENDED/REMOVED ne troše. Menja se ISKLJUČIVO preko shared/seats.py SeatService, nikad direktnim UPDATE-om — svaka promena mora upisati red u kancelarija_seat_audit.';
COMMENT ON COLUMN public.kancelarija_clanovi.removed_reason IS
    'declined (odbio poziv) / removed_by_admin / left_voluntarily. NULL dok status nije REMOVED.';

CREATE INDEX IF NOT EXISTS idx_kc_kancelarija_status ON public.kancelarija_clanovi(kancelarija_id, status);


-- ── kancelarija_seat_audit: trajan, append-only zapis svake promene mesta ───
-- Isti obrazac kao feature_registry_audit (migracija 065) — nikad se ne
-- briše niti update-uje, samo INSERT.

CREATE TABLE IF NOT EXISTS public.kancelarija_seat_audit (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id   UUID        NOT NULL REFERENCES public.kancelarije(id) ON DELETE CASCADE,
    clan_id          UUID        REFERENCES public.kancelarija_clanovi(id) ON DELETE SET NULL,
    clan_email       TEXT        NOT NULL,
    actor_uid        TEXT        NOT NULL,
    actor_email      TEXT        NOT NULL,
    action           TEXT        NOT NULL
                      CHECK (action IN ('invite', 'accept', 'decline', 'suspend', 'reactivate', 'remove', 'leave')),
    from_status      TEXT,
    to_status        TEXT        NOT NULL,
    detail           JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_audit_kancelarija ON public.kancelarija_seat_audit(kancelarija_id, created_at DESC);

ALTER TABLE public.kancelarija_seat_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY "kancelarija_seat_audit_service_role" ON public.kancelarija_seat_audit
    FOR ALL USING (auth.role() = 'service_role');
-- Namerno NEMA UPDATE/DELETE politike ni za service_role u praksi (aplikativni
-- kod samo INSERT-uje) — isti obrazac kao feature_registry_audit.

COMMENT ON TABLE public.kancelarija_seat_audit IS
    'Trajan, append-only zapis svake promene stanja mesta (poziv/prihvatanje/odbijanje/suspenzija/reaktivacija/uklanjanje/napuštanje). Nikad se ne briše — izvor istine za sporove oko broja korisnika.';
