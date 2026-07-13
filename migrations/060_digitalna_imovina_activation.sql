-- ============================================================================
-- Vindex AI — Migracija 060: Digitalna imovina & Usklađenost — aktivacija add-ona
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 059.
--
-- Kontekst: modul "Digitalna imovina & Usklađenost" (bivši "Web3 & Kripto")
-- se premešta iz stalne sidebar stavke u enterprise add-on koji se aktivira
-- iz Podešavanja. Nema pravu naplatu iza sebe (Stripe nije integrisan u ovoj
-- platformi) — ovaj flag samo pamti da li je PRO korisnik kliknuo "Aktiviraj
-- modul", da bi se mod pojavio u AI Radnom Prostoru bez ponovnog prijavljivanja.
-- ============================================================================

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS digitalna_imovina_aktivirano boolean NOT NULL DEFAULT false;

-- ============================================================================
-- Provera (opciono)
-- SELECT id, email, is_pro, digitalna_imovina_aktivirano FROM public.profiles
--   WHERE digitalna_imovina_aktivirano = true;
-- ============================================================================
