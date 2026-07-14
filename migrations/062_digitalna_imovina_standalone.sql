-- ============================================================================
-- Vindex AI — Migracija 062: Digitalna imovina & Usklađenost — standalone tarifa
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 061.
--
-- Kontekst: "Vindex AI - Digitalna imovina & usklađenost" postaje zasebna,
-- četvrta tarifa (pored Solo/PRO/Kancelarija), sa dva ulaza:
--   - 79 EUR/mes — potpuno samostalno, bez ostatka platforme (npr. banka)
--   - 39 EUR/mes — dodatak za postojeće PRO korisnike
-- Nema pravu naplatu (Stripe nije integrisan) — isti ručni tok kao ostale
-- tarife: korisnik kontaktira preko pricing modala, osnivač ručno aktivira
-- nalog u Supabase-u.
--
-- Za standalone (79 EUR) naloge, osnivač ručno postavlja SVA TRI flag-a:
--   is_pro = true                          (potrebno da prođu postojeći
--                                            require_pro gate-ovi na backend
--                                            /web3/* rutama — ne otvara
--                                            ništa drugo jer je ostatak
--                                            platforme sakriven u UI-ju kad
--                                            je digitalna_imovina_standalone
--                                            = true)
--   digitalna_imovina_aktivirano = true    (otključava AIWS mod)
--   digitalna_imovina_standalone = true    (sakriva ostatak platforme,
--                                            landuje direktno u modul)
--
-- Za add-on (39 EUR) naloge — korisnik je već is_pro = true, osnivač samo
-- postavlja digitalna_imovina_aktivirano = true (standalone ostaje false,
-- korisnik zadržava pristup ostatku platforme).
-- ============================================================================

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS digitalna_imovina_standalone boolean NOT NULL DEFAULT false;

-- ============================================================================
-- Provera (opciono)
-- SELECT id, email, is_pro, digitalna_imovina_aktivirano, digitalna_imovina_standalone
--   FROM public.profiles WHERE digitalna_imovina_standalone = true;
-- ============================================================================
