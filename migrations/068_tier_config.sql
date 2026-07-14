-- ============================================================================
-- Vindex AI — Migracija 068: Tier Configuration — jedinstven izvor tarifnih
-- činjenica (cena, uključena mesta), po istom obrascu kao feature_registry.
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 067.
--
-- Kontekst: feature_registry (064-066) je jedini izvor za pristup/cenu PO
-- FUNKCIJI. profiles.subscription_type je jedini izvor za tarifu NALOGA.
-- Nedostajao je jedini izvor za činjenice O SAMOJ TARIFI — mesečna/godišnja
-- cena, broj uključenih mesta — koje su do sada bile hardkodovane na 3 mesta:
--   shared/seats.py:BASE_INCLUDED_SEATS, routers/product_intelligence.py:
--   _TIER_PRICE_EUR, routers/plans.py:_plan_display_name(). Bez ove tabele,
--   promena cene tarife bi zahtevala deploy — isti problem koji je
--   feature_registry rešio za funkcije, sada za same tarife.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tier_config (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_key              TEXT NOT NULL UNIQUE
                          CHECK (tier_key IN ('basic', 'professional', 'enterprise')),
    display_name          TEXT NOT NULL,
    monthly_price_eur     NUMERIC NOT NULL DEFAULT 0,
    yearly_price_eur      NUMERIC,
    included_seats        INTEGER NOT NULL DEFAULT 1,
    extra_seat_price_eur  NUMERIC,
    max_devices           INTEGER,
    description            TEXT,
    sort_order             INTEGER NOT NULL DEFAULT 0,
    is_active              BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by              TEXT
);

COMMENT ON TABLE public.tier_config IS
    'Jedini izvor istine za tarifne činjenice (cena, uključena mesta) — isti obrazac kao feature_registry, ali po tier_key umesto feature_key. Menja se preko Admin Feature Console-a, ne preko deploy-a.';
COMMENT ON COLUMN public.tier_config.extra_seat_price_eur IS
    'Cena po dodatnom mestu iznad included_seats — trenutno relevantno samo za enterprise (49€/mesečno). NULL = dodatna mesta se ne prodaju za ovu tarifu.';
COMMENT ON COLUMN public.tier_config.max_devices IS
    'Rezervisano za budući device-limit — danas se nigde ne čita/piše (nema device-tracking sistema), dodato unapred da se izbegne šema-migracija kad se doda.';

ALTER TABLE public.tier_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tier_config_service_role" ON public.tier_config
    FOR ALL USING (auth.role() = 'service_role');
-- Čitanje dozvoljeno i običnim ulogovanim korisnicima (frontend treba cene
-- za Settings/pricing prikaz), isti obrazac kao feature_registry.
CREATE POLICY "tier_config_authenticated_read" ON public.tier_config
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── tier_config_audit — trajan, append-only zapis svake promene cene ────────
-- Isti obrazac kao feature_registry_audit/kancelarija_seat_audit.

CREATE TABLE IF NOT EXISTS public.tier_config_audit (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_key     TEXT NOT NULL,
    changed_by   TEXT NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_values   JSONB,
    new_values   JSONB
);

CREATE INDEX IF NOT EXISTS idx_tier_config_audit_tier ON public.tier_config_audit(tier_key, changed_at DESC);

ALTER TABLE public.tier_config_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tier_config_audit_service_role" ON public.tier_config_audit
    FOR ALL USING (auth.role() = 'service_role');
-- Namerno NEMA UPDATE/DELETE politike — append-only.


-- ── Seed — vrednosti iz founder-ovog originalnog spec-a za novi sistem ──────
-- (29€/79€/249€ + 49€/dodatno Enterprise mesto, 3 uključena mesta na
-- Enterprise) — iste cifre koje su do sada bile hardkodovane u tri fajla.

INSERT INTO public.tier_config
    (tier_key, display_name, monthly_price_eur, yearly_price_eur, included_seats, extra_seat_price_eur, sort_order, description)
VALUES
    ('basic', 'Basic', 29, 278.40, 1, NULL, 1,
     'Za pojedinačnog advokata — osnovne AI funkcije, jedan korisnik.'),
    ('professional', 'Professional', 79, 758.40, 1, NULL, 2,
     'Za aktivnu praksu — proširen AI fond, sve osnovne funkcije bez ograničenja.'),
    ('enterprise', 'Enterprise', 249, 2390.40, 3, 49, 3,
     'Za timove — 3 uključena mesta, dodatna mesta 49€/mesečno po korisniku.')
ON CONFLICT (tier_key) DO NOTHING;
