-- ============================================================================
-- Vindex AI — Migracija 070: feature_type + chargeable u feature_registry
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 069.
--
-- Kontekst: pri pripremi Pricing Modal redizajna (Faza 73), analiza celog
-- Feature Registry-ja (70 redova) otkrila je da 12 redova (17%) nema NIKAKVU
-- vezu sa kodom (audit_dead_features.py) — ali iz TRI različita razloga koji
-- zahtevaju različit tretman, ne jedno rešenje za sve:
--
--   A) 6 redova (predmeti_crud/klijenti_crud/dokumenti_basic/crm/finansije/
--      rokovi) — osnovna CRUD funkcionalnost dostupna SVIM registrovanim
--      korisnicima (endpoint proverava samo autentifikaciju, ne subscription_
--      type) — nikad nisu bili "premium" funkcije, samo su POGREŠNO stavljeni
--      u tarifnu tabelu kao da su basic-tier prednost.
--   B) 2 reda (firm_memory/knowledge_hygiene) — potvrđeno čitanjem koda da
--      NEMAJU nijedan LLM poziv, ispravno ostavljeni negejtovani — ali
--      Registry i dalje tvrdi "professional, 1 kredit", što je netačno.
--   C) 4 reda (api_external/enterprise_delegacija/kancelarija_team/
--      klijenti_audit_log) — čist placeholder, NIŠTA implementirano. Founder
--      eksplicitno zabranio reklamiranje funkcija koje ne postoje.
--
-- Rešenje — feature_registry meša 4 različite stvari (funkcionalnost,
-- monetizacija, roadmap, sistemske funkcije). feature_type ih razdvaja:
--   FOUNDATION   — nikad u Pricing tabeli, uvek dostupno registrovanim korisnicima
--   SUBSCRIPTION — ide u Basic/Professional/Enterprise kolone
--   ADDON        — zaseban proizvod (Digitalna imovina), svoje kartice
--   INTERNAL     — nikad vidljivo korisnicima (rezervisano za buduće interne alate)
--
-- chargeable — odvojeno od feature_type: da li OVA funkcija (kad se koristi)
-- stvarno troši kredite. False SAMO za funkcije koje su deo pretplate ali
-- imaju krediti=0 zato što nemaju AI poziv uopšte (firm_memory/knowledge_
-- hygiene) — NE za funkcije koje su namerno besplatne kao poslovna odluka
-- (npr. morning_briefing/voice/sudska_praksa ostaju chargeable=true sa
-- krediti=0 — to je "trenutno besplatno po ceni", ne "ovo ne radi ništa").
-- ============================================================================

ALTER TABLE public.feature_registry
    ADD COLUMN IF NOT EXISTS feature_type text NOT NULL DEFAULT 'SUBSCRIPTION'
        CHECK (feature_type IN ('FOUNDATION', 'SUBSCRIPTION', 'ADDON', 'INTERNAL')),
    ADD COLUMN IF NOT EXISTS chargeable boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN public.feature_registry.feature_type IS
    'FOUNDATION = osnovna funkcionalnost, nikad u Pricing tabeli. SUBSCRIPTION = ide u Basic/Professional/Enterprise. ADDON = zaseban proizvod (Digitalna imovina). INTERNAL = nikad vidljivo korisnicima.';
COMMENT ON COLUMN public.feature_registry.chargeable IS
    'False = deo je pretplate ali NE troši kredite jer nema AI poziv uopšte (ne isto što i krediti=0 kao poslovna odluka o ceni — to ostaje chargeable=true).';

-- A) Foundation Layer — osnovna funkcionalnost, izbačeno iz Pricing tabele
UPDATE public.feature_registry SET feature_type = 'FOUNDATION'
WHERE feature_key IN ('predmeti_crud', 'klijenti_crud', 'dokumenti_basic', 'crm', 'finansije', 'rokovi');

-- Add-on Layer — Digitalna imovina, uvek bio zaseban proizvod (addon kolona
-- u Registry-ju već postoji otkad je uveden), sada i eksplicitno feature_type
UPDATE public.feature_registry SET feature_type = 'ADDON'
WHERE addon = 'digital_assets';

-- C) Placeholder Enterprise funkcije — nisu izgrađene, prebačene na COMING_SOON
-- (postoji upravo za ovo — roadmap, ne Pricing) dok se stvarno ne implementiraju
UPDATE public.feature_registry SET status = 'COMING_SOON'
WHERE feature_key IN ('api_external', 'enterprise_delegacija', 'kancelarija_team', 'klijenti_audit_log');

-- B) firm_memory/knowledge_hygiene — ostaju SUBSCRIPTION (deo Professional
-- pretplate, korisnik ih dobija kad plati Professional), ali krediti=0 i
-- chargeable=false jer stvarno ne troše ništa — Registry više ne laže.
UPDATE public.feature_registry SET krediti = 0, chargeable = false
WHERE feature_key IN ('firm_memory', 'knowledge_hygiene');
