-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 128: ROLLOUT entitlement
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
--
-- ZAŠTO POSTOJI
-- Do sada je registar imao tačno dva načina da nešto dodeli korisniku:
--   `minimum_plan` (po tarifi — nije per-user)
--   `addon`        (per-user, ALI se čita iz `profiles.addons`, koje
--                   `/api/plan/status` i GDPR izvoz vraćaju SIROVO korisniku)
-- Zbog toga se interni rollout nije mogao dodeliti nijednom nalogu a da se
-- interni ključ ne pojavi korisniku kao „Dodaci: v2_pristup".
--
-- Ova migracija uvodi TREĆU osu — ROLLOUT — koja je per-user, nekomercijalna,
-- opoziva i nikad user-facing.
--
-- ZAŠTO NE `visible='internal'` KAO SIGNAL
-- `visible` je prezentaciona semantika. Autorizacija ne sme da zavisi od
-- kolone koja opisuje prikaz. `feature_type` je osa tipa capability-ja i
-- zato nosi odluku.
--
-- ZAŠTO NE POSTOJEĆI `feature_type='INTERNAL'`
-- Vrednost postoji u constraint-u, ali `status='INTERNAL'` u istom registru
-- već znači „samo founder". Dva različita značenja pod istim imenom u dve
-- kolone su tačno ona zamka zbog koje je `visible` odbijen kao signal.
-- ROLLOUT je i semantički drugačiji životni ciklus: privremena kapija koja
-- se na kraju otvara svima, a ne alat koji zauvek ostaje interni.
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. PER-USER NOSILAC ROLLOUT DODELA ──────────────────────────────────────
-- jsonb, ne text[] — `profiles.addons` je već `jsonb NOT NULL DEFAULT '[]'`
-- (migracija 063), pa ovo prati zatečenu konvenciju istog stola.
-- DEFAULT '[]' znači: posle migracije NIJEDAN postojeći nalog nema nijednu
-- dodelu — ni founder, ni admin, ni enterprise, ni nalog sa svim addon-ima.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS rollout_flags jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.profiles.rollout_flags IS
    'Per-user dodele za feature_registry redove sa feature_type=ROLLOUT. Lista feature_key stringova, tačno poklapanje. NIKAD se ne vraća korisniku (za razliku od addons) — ne ulazi ni u /api/plan/status ni u GDPR izvoz. Prazna lista = nema pristupa; to je jedino podrazumevano stanje.';


-- ─── 2. feature_type DOBIJA VREDNOST 'ROLLOUT' ───────────────────────────────
-- Postojeći CHECK (migracija 070) dozvoljava FOUNDATION/SUBSCRIPTION/ADDON/
-- INTERNAL. Proširenje je aditivno: nijedan postojeći red ne menja vrednost,
-- pa nijedan postojeći red ne može pasti na novom constraint-u.

ALTER TABLE public.feature_registry
    DROP CONSTRAINT IF EXISTS feature_registry_feature_type_check;

ALTER TABLE public.feature_registry
    ADD CONSTRAINT feature_registry_feature_type_check
    CHECK (feature_type IN ('FOUNDATION', 'SUBSCRIPTION', 'ADDON', 'INTERNAL', 'ROLLOUT'));

COMMENT ON COLUMN public.feature_registry.feature_type IS
    'FOUNDATION = osnovna funkcionalnost, nikad u Pricing tabeli. SUBSCRIPTION = ide u Basic/Professional/Enterprise. ADDON = zaseban proizvod (Digitalna imovina). INTERNAL = nikad vidljivo korisnicima. ROLLOUT = interna kapija za postepeno puštanje; dodeljuje se per-user preko profiles.rollout_flags, ne preko tarife ni addon-a, i founder je NE zaobilazi.';


-- ─── 3. PRVI ROLLOUT RED — v2_pristup ────────────────────────────────────────
-- Tri nezavisna razloga zbog kojih ovaj red ne može da završi u Pricing
-- matrici (routers/plans.py:145 filtrira sva tri):
--   feature_type NOT IN (SUBSCRIPTION, ADDON)   → isključen
--   visible <> 'visible'                         → isključen
--   business_group_id IS NULL                    → isključen
-- `naziv` je NOT NULL pa mora postojati, ali se nigde ne renderuje korisniku.

INSERT INTO public.feature_registry (
    feature_key, naziv, kategorija, feature_type, visible, status, aktivno,
    addon, minimum_plan, krediti, chargeable, priority, business_group_id, opis
) VALUES (
    'v2_pristup',
    'Vindex V2 — interni rollout',
    'interno',
    'ROLLOUT',
    'internal',
    'ACTIVE',
    true,
    NULL,          -- nije komercijalni addon
    NULL,          -- ne zavisi od tarife
    0,             -- ne troši kredite
    false,         -- nije naplativo
    'MEDIUM',
    NULL,          -- bez poslovne grupe → van Pricing matrice
    'Kapija za kontrolisano puštanje Vindex V2 frontenda. Dodeljuje se pojedinačnom nalogu upisom u profiles.rollout_flags. Nije proizvod i ne prikazuje se korisniku.'
)
ON CONFLICT (feature_key) DO UPDATE SET
    feature_type      = EXCLUDED.feature_type,
    visible           = EXCLUDED.visible,
    status            = EXCLUDED.status,
    aktivno           = EXCLUDED.aktivno,
    addon             = EXCLUDED.addon,
    minimum_plan      = EXCLUDED.minimum_plan,
    krediti           = EXCLUDED.krediti,
    chargeable        = EXCLUDED.chargeable,
    business_group_id = EXCLUDED.business_group_id,
    updated_at        = now();


-- ─── 4. PROVERA POSLE POKRETANJA ─────────────────────────────────────────────
-- Očekivano: jedan red, ROLLOUT/internal/ACTIVE, addon i minimum_plan NULL.
--
--   SELECT feature_key, feature_type, visible, status, addon, minimum_plan
--   FROM public.feature_registry WHERE feature_key = 'v2_pristup';
--
-- Očekivano: 0 naloga sa bilo kakvom dodelom (fail-closed posle migracije).
--
--   SELECT count(*) FROM public.profiles WHERE rollout_flags <> '[]'::jsonb;
--
-- DODELA jednom nalogu (zameniti email):
--
--   UPDATE public.profiles
--      SET rollout_flags = rollout_flags || '["v2_pristup"]'::jsonb
--    WHERE email = '...' AND NOT (rollout_flags @> '["v2_pristup"]'::jsonb);
--
-- OPOZIV istog naloga:
--
--   UPDATE public.profiles
--      SET rollout_flags = rollout_flags - 'v2_pristup'
--    WHERE email = '...';


-- ─── 5. ROLLBACK ─────────────────────────────────────────────────────────────
-- Redosled je bitan: red mora otići pre nego što se constraint suzi, inače
-- suženi CHECK pada na sopstvenom redu.
--
--   DELETE FROM public.feature_registry WHERE feature_key = 'v2_pristup';
--
--   ALTER TABLE public.feature_registry
--       DROP CONSTRAINT IF EXISTS feature_registry_feature_type_check;
--   ALTER TABLE public.feature_registry
--       ADD CONSTRAINT feature_registry_feature_type_check
--       CHECK (feature_type IN ('FOUNDATION', 'SUBSCRIPTION', 'ADDON', 'INTERNAL'));
--
--   ALTER TABLE public.profiles DROP COLUMN IF EXISTS rollout_flags;
--
-- Kod podnosi rollback bez izmene: bez kolone `rollout_flags` čitanje pada u
-- sopstveni except i vraća praznu listu → DENY. Bez reda `v2_pristup`
-- `get_policy` baca RuntimeError → DENY. Oba puta fail-closed.
