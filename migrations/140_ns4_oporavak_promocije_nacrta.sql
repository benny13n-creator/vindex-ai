-- ============================================================================
-- Vindex AI — Migracija 140: oporavljiva promocija odobrenog nacrta (NS4 O3)
-- ============================================================================
-- PROBLEM: odobren nacrt čiji upis u bazu znanja nije potvrđen kao potpun ostaje `pinecone_indexed=false`
--   zauvek — ponovno odobravanje ga ne dodaje (stanje više nije 'pending'), a oporavak ne postoji.
--   NS4-R2 ga ispravno NE služi kao overen izvor (fail-closed); nedostaje bezbedan ponovni pokušaj.
--
-- ZAŠTO NE BEZ ŠEME: `staging_memory` nema kolonu koja može da nosi „pokušaj u toku" (pinecone_indexed je
--   NOT NULL boolean, nema updated_at). Bez nje dva istovremena ponovna pokušaja (ili ponovni pokušaj tokom
--   prvog odobravanja) oba upisuju, a pokušaj prekinut padom procesa ne može da se razlikuje od aktivnog.
--   Identitet vektora je već stabilan (shared/vector_identity: predmet + heš teksta + redni broj dela) —
--   ponovljen upis istog teksta PREPISUJE iste ID-eve, ne duplira.
--
-- REŠENJE (aditivno):
--   • `promocija_token` (uuid) + `promocija_preuzeta_at` — jedan aktivan pokušaj po nacrtu, sa rokom
--     (napušten pokušaj se može preuzeti posle `p_istek_sekundi`);
--   • `preuzmi_ponovni_upis_nacrta` — atomsko preuzimanje SAMO za podoban nacrt: vlasnik, 'approved',
--     is_lawyer_approved, nije potvrđeno indeksiran, ocena ≥ prag, nema aktivnog pokušaja;
--   • `zavrsi_promociju_nacrta` — zatvara pokušaj SAMO sa istim tokenom (zastareo radnik ne prepisuje
--     noviji ishod); `pinecone_indexed=true` samo ako je nacrt i dalje odobren;
--   • jedinstven indeks knjigovodstvenog reda nacrta u `predmet_dokumenti` (`storage_path`
--     'draft/staging/<id>') — ponovni pokušaj ažurira isti red, baza odbija duplikat.
--
-- Postojeći redovi: nove kolone su NULL (= nema pokušaja). Postojeći knjigovodstveni redovi nacrta koriste
--   'draft/<nasumičan session_id>' i ne potpadaju pod indeks (ne menjaju se). Produkcija 2026-10-19:
--   staging_memory = 0 redova.
--
-- BEZBEDNOST: SECURITY INVOKER (poziva backend kao service_role); EXECUTE oduzet od PUBLIC/anon/authenticated;
--   `search_path` fiksiran; objekti kvalifikovani šemom.
-- Zaključavanje: ADD COLUMN bez DEFAULT-a je samo katalog; CREATE UNIQUE INDEX čita `predmet_dokumenti`
--   jednom (SHARE brava — blokira upise u tu tabelu tokom izgradnje; tabela je mala, nije CONCURRENTLY jer
--   je u transakciji). Idempotentno.
-- ============================================================================

BEGIN;

ALTER TABLE public.staging_memory
    ADD COLUMN IF NOT EXISTS promocija_token        uuid,
    ADD COLUMN IF NOT EXISTS promocija_preuzeta_at  timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_predmet_dokumenti_nacrt_staging
    ON public.predmet_dokumenti (storage_path)
    WHERE storage_path LIKE 'draft/staging/%';

CREATE OR REPLACE FUNCTION public.preuzmi_ponovni_upis_nacrta(
    p_staging_id     uuid,
    p_user_id        text,
    p_prag           numeric,
    p_istek_sekundi  integer
) RETURNS SETOF public.staging_memory
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
    UPDATE public.staging_memory s
       SET promocija_token = gen_random_uuid(),
           promocija_preuzeta_at = pg_catalog.now()
     WHERE s.id = p_staging_id
       AND s.user_id = p_user_id
       AND s.status = 'approved'
       AND s.is_lawyer_approved
       AND NOT s.pinecone_indexed
       AND s.confidence_score >= GREATEST(p_prag, 0)
       AND (s.promocija_token IS NULL
            OR s.promocija_preuzeta_at < pg_catalog.now() - pg_catalog.make_interval(secs => GREATEST(p_istek_sekundi, 60)))
    RETURNING s.*;
$$;

CREATE OR REPLACE FUNCTION public.zavrsi_promociju_nacrta(
    p_staging_id  uuid,
    p_token       uuid,
    p_indeksiran  boolean
) RETURNS boolean
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
    WITH z AS (
        UPDATE public.staging_memory s
           SET pinecone_indexed = (COALESCE(p_indeksiran, false) AND s.status = 'approved' AND s.is_lawyer_approved),
               promocija_token = NULL,
               promocija_preuzeta_at = NULL
         WHERE s.id = p_staging_id
           AND p_token IS NOT NULL
           AND s.promocija_token = p_token
        RETURNING s.pinecone_indexed
    )
    SELECT COALESCE((SELECT pinecone_indexed FROM z), false);
$$;

REVOKE ALL ON FUNCTION public.preuzmi_ponovni_upis_nacrta(uuid, text, numeric, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.zavrsi_promociju_nacrta(uuid, uuid, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.preuzmi_ponovni_upis_nacrta(uuid, text, numeric, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.zavrsi_promociju_nacrta(uuid, uuid, boolean) TO service_role;

COMMIT;

-- ─── Provera posle primene ───────────────────────────────────────────────────
-- SELECT column_name FROM information_schema.columns
--  WHERE table_schema='public' AND table_name='staging_memory' AND column_name LIKE 'promocija_%';   -- 2 reda
-- SELECT indexname FROM pg_indexes WHERE indexname = 'uq_predmet_dokumenti_nacrt_staging';            -- 1 red
-- SELECT has_function_privilege('authenticated','public.preuzmi_ponovni_upis_nacrta(uuid,text,numeric,integer)','EXECUTE'); -- f
--
-- ─── Povratak (kod NS4 release-a se vraća PRE ovoga) ─────────────────────────
-- DROP FUNCTION IF EXISTS public.zavrsi_promociju_nacrta(uuid, uuid, boolean);
-- DROP FUNCTION IF EXISTS public.preuzmi_ponovni_upis_nacrta(uuid, text, numeric, integer);
-- DROP INDEX IF EXISTS public.uq_predmet_dokumenti_nacrt_staging;
-- Kolone `promocija_*` ostaviti (aditivne, NULL); brisati ih samo ako je potvrđeno da ih ništa ne čita.
