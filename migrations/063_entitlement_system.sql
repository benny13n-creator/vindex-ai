-- ============================================================================
-- Vindex AI — Migracija 063: Enterprise Entitlement System — šema
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 062.
--
-- Kontekst: potpuni refaktor sistema tarifa (docs/ENTITLEMENT_AUDIT_PHASE1.md).
-- Zamenjuje is_pro boolean kao jedini izvor istine sa subscription_type
-- (basic/professional/enterprise) + addons (niz, npr. digital_assets za
-- Digitalnu imovinu — zaseban proizvod, NIKAD deo tarife).
--
-- BEZBEDNOST MIGRACIJE (founder-ov zahtev, poglavlje 9-10 spec-a):
--   - Nijedan postojeći korisnik ne sme izgubiti pristup funkcijama koje
--     već ima. Rešenje: "Legacy Professional" — svi is_pro=true nalozi
--     dobijaju subscription_type='professional' + subscription_expires_at
--     = now() + 30 dana. Posle isteka, ako ne kupe Professional, padaju na
--     'basic' (to se dešava u aplikativnom kodu pri čitanju profila, ne
--     ovde — ova migracija samo postavlja početno stanje).
--   - is_pro kolona SE NE BRIŠE u ovoj migraciji (bezbednost — stari kod
--     koji je još uvek nepromenjen nastavlja da radi dok se PermissionService
--     ne uvede svuda). Brisanje ide u kasniju migraciju, tek posle potvrde
--     da je ceo projekat prešao na novi sistem.
--   - digitalna_imovina_aktivirano/standalone (migracije 060, 062) SE NE
--     BRIŠU — frontend ih i dalje čita direktno. Njihova vrednost se
--     backfilluje u novo addons polje radi buduće PermissionService
--     integracije, ali stari flag-ovi ostaju izvor istine za postojeći
--     frontend kod dok se on posebno ne migrira.
-- ============================================================================

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS subscription_type text NOT NULL DEFAULT 'basic'
        CHECK (subscription_type IN ('basic', 'professional', 'enterprise')),
    ADD COLUMN IF NOT EXISTS addons jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS subscription_expires_at timestamptz,
    ADD COLUMN IF NOT EXISTS subscription_seats_extra integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.profiles.subscription_type IS
    'Jedini izvor istine za tarifu. basic/professional/enterprise. NIKAD "digital_assets" — to je addon, ne tarifa.';
COMMENT ON COLUMN public.profiles.addons IS
    'Niz zasebno kupljenih proizvoda van osnovne tarife. Trenutno moguće vrednosti: "digital_assets" (39€ dodatak uz postojeću tarifu), "digital_assets_standalone" (79€ samostalno, bez ostatka platforme).';
COMMENT ON COLUMN public.profiles.subscription_expires_at IS
    'NULL = trajno (redovna plaćena tarifa ili founder). Postavljeno = privremeni status (npr. Legacy Professional tranzicija), po isteku aplikativni kod tretira nalog kao da ima subscription_type default vrednost dok se ne obnovi.';
COMMENT ON COLUMN public.profiles.subscription_seats_extra IS
    'Broj DODATNO kupljenih mesta preko 3 uključena u Enterprise (49€/mesečno po mestu). Relevantno samo za subscription_type=enterprise.';

-- ── Backfill: postojeći korisnici ────────────────────────────────────────────

-- 1) is_pro = true → Legacy Professional (30 dana da obnove ili kupe)
UPDATE public.profiles
SET subscription_type = 'professional',
    subscription_expires_at = now() + interval '30 days'
WHERE is_pro = true;

-- 2) is_pro = false (ili null) → basic (eksplicitno, DEFAULT ne dira postojeće redove)
UPDATE public.profiles
SET subscription_type = 'basic'
WHERE is_pro IS DISTINCT FROM true
  AND subscription_type IS NULL;  -- no-op safety, DEFAULT već pokriva NOT NULL kolonu

-- 3) Backfill addons iz postojećih Digitalna imovina flag-ova (samo za prikaz/
--    buduću PermissionService integraciju — stari flag-ovi ostaju živi)
UPDATE public.profiles
SET addons = CASE
    WHEN digitalna_imovina_standalone = true THEN '["digital_assets_standalone"]'::jsonb
    WHEN digitalna_imovina_aktivirano = true THEN '["digital_assets"]'::jsonb
    ELSE addons
END
WHERE digitalna_imovina_aktivirano = true OR digitalna_imovina_standalone = true;

-- ============================================================================
-- Provera (opciono)
-- SELECT subscription_type, count(*) FROM public.profiles GROUP BY subscription_type;
-- SELECT id, email, is_pro, subscription_type, subscription_expires_at, addons
--   FROM public.profiles WHERE subscription_expires_at IS NOT NULL;
-- ============================================================================
