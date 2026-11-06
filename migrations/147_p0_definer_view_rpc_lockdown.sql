-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migracija 147: P0 zaključavanje SECURITY DEFINER view-ova i
--                            internih worker RPC-ja
-- ⚠ NIJE IZVRŠENA. Pokreće je osnivač (Supabase SQL Editor), posle 146.
-- ═══════════════════════════════════════════════════════════════════════════
--
-- UZROK (dokazano, P0 sprint 2026-11-06):
--   Supabase u šemi `public` ima podrazumevane privilegije
--     ALTER DEFAULT PRIVILEGES ... GRANT ALL ON TABLES/FUNCTIONS TO anon, authenticated, service_role
--   pa SVAKI novi view i SVAKA nova funkcija dobijaju DIREKTAN grant za `anon`
--   i `authenticated`. Migracije 073/091/092/095 rade samo
--     REVOKE ALL ON FUNCTION ... FROM PUBLIC
--   što uklanja isključivo pseudo-ulogu PUBLIC, a direktne grantove ostavlja.
--   View-ovi su u vlasništvu `postgres` i bez `security_invoker`, pa se
--   izvršavaju sa pravima vlasnika i zaobilaze RLS osnovnih tabela.
--   Izmereno na produkcionom Data API-ju javnim (publishable) ključem:
--     case_profitability → 153 reda (osnovna tabela predmeti → 0).
--
-- ODLUKA (Opcija A za svih 7 view-ova i 7 funkcija):
--   Nijedan od ovih objekata nema korisnički (frontend) potrošač — backend ih
--   čita/poziva isključivo `service_role` ključem (shared/deps.py::_get_supa)
--   i sam filtrira po user_id. Zato se uklanja SAV pristup PUBLIC/anon/
--   authenticated. Postojeća prava `service_role` se NE smanjuju (ima ih
--   iz podrazumevanih privilegija); migracija samo garantuje SELECT na
--   view-ovima i EXECUTE na worker RPC-jima koje backend koristi.
--   Bez security_invoker: view-ovi agregiraju više korisnika i ostaju
--   backend-only; RLS se ne menja; tela funkcija i view-ova se ne menjaju.
--
-- NE DIRA: osam trigger funkcija (ne mogu se pozvati direktno — samo kao
--   triger; EXECUTE se proverava samo pri CREATE TRIGGER), RLS politike,
--   podatke, vlasništvo, podrazumevane privilegije (globalno — posebna odluka).
--
-- IDEMPOTENTNO: REVOKE/GRANT se mogu ponoviti. Ako neki objekat/potpis ne
--   postoji, migracija PADA i cela transakcija se vraća (namerno — pogrešan
--   potpis ne sme tiho da ostavi funkciju otvorenom).
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. View-ovi iz repozitorijuma (045, 002, 065, 073/130) ─────────────────
REVOKE ALL ON TABLE public.case_profitability            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.klijenti_retention_candidates FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.feature_analytics             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.intake_queue_metrics          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.events_outbox_metrics         FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE public.case_profitability            TO service_role;  -- routers/profitabilnost.py
GRANT SELECT ON TABLE public.klijenti_retention_candidates TO service_role;  -- GDPR retencija (operativno)
GRANT SELECT ON TABLE public.feature_analytics             TO service_role;
GRANT SELECT ON TABLE public.intake_queue_metrics          TO service_role;  -- shared/intake_queue.py
GRANT SELECT ON TABLE public.events_outbox_metrics         TO service_role;  -- shared/intake_queue.py, services/event_bus.py

-- ── 2. View-ovi koji NISU u repozitorijumu (Security Advisor) ──────────────
-- `v_manual_queue` i `v_qualified_jobs` pripadaju drugom sistemu u istom
-- projektu (tabele jobs/applications); Vindex kod ih ne dodiruje. Definicija
-- se ne menja — samo se zatvara javni pristup. Ako ne postoje, preskače se.
DO $$
DECLARE
    v TEXT;
BEGIN
    FOREACH v IN ARRAY ARRAY['v_manual_queue', 'v_qualified_jobs'] LOOP
        IF to_regclass('public.' || v) IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', v);
            EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', v);
        END IF;
    END LOOP;
END
$$;

-- ── 3. Interni worker RPC-ji (073, 091, 095) — pun potpis ──────────────────
REVOKE ALL ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_intake_job(TEXT, TEXT)                                 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_intake_job(UUID)                                    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_intake_job(UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ)   FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_pending_events(INTEGER, INTEGER)                       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_intake_finalize(UUID, INTEGER)                         FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)     TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_intake_job(TEXT, TEXT)                               TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_intake_job(UUID)                                  TO service_role;
GRANT EXECUTE ON FUNCTION public.fail_intake_job(UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_pending_events(INTEGER, INTEGER)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_intake_finalize(UUID, INTEGER)                       TO service_role;

-- ── 4. V2 provera kontradikcije (123) ──────────────────────────────────────
-- Poziva je isključivo trigger omotač (v2_trg_kontradikcija / v2_trg_clanstvo,
-- SECURITY DEFINER, vlasnik postgres) — direktan RPC nema potrošača, a poruke
-- izuzetka otkrivaju stanje i predmet tuđe kontradikcije. Pravila provere
-- se ne menjaju; service_role se ne dira.
REVOKE ALL ON FUNCTION public.v2_proveri_kontradikciju(UUID) FROM PUBLIC, anon, authenticated;

-- ── 5. Samoprovera: ako bilo šta ostane otvoreno, cela migracija se vraća ──
DO $$
DECLARE
    r       RECORD;
    uloga   TEXT;
    otvoreno TEXT[] := '{}';
BEGIN
    -- Svaki overload ovih imena, ne samo potpisi iznad.
    FOR r IN
        SELECT p.oid::regprocedure AS fn
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN ('enqueue_intake_job', 'claim_intake_job', 'complete_intake_job',
                             'fail_intake_job', 'claim_pending_events', 'claim_intake_finalize',
                             'v2_proveri_kontradikciju')
    LOOP
        FOREACH uloga IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF has_function_privilege(uloga, r.fn, 'EXECUTE') THEN
                otvoreno := otvoreno || format('%s EXECUTE %s', uloga, r.fn);
            END IF;
        END LOOP;
    END LOOP;

    FOR r IN
        SELECT c.oid::regclass AS rel
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname IN ('case_profitability', 'klijenti_retention_candidates', 'feature_analytics',
                             'intake_queue_metrics', 'events_outbox_metrics',
                             'v_manual_queue', 'v_qualified_jobs')
    LOOP
        FOREACH uloga IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            -- has_table_privilege ne vidi grantove na nivou kolone, pa se proveravaju i oni.
            IF has_table_privilege(uloga, r.rel, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_any_column_privilege(uloga, r.rel, 'SELECT,INSERT,UPDATE,REFERENCES') THEN
                otvoreno := otvoreno || format('%s pristup %s', uloga, r.rel);
            END IF;
        END LOOP;
        IF NOT has_table_privilege('service_role', r.rel, 'SELECT') THEN
            otvoreno := otvoreno || format('service_role bez SELECT %s', r.rel);
        END IF;
    END LOOP;

    IF NOT has_function_privilege('service_role', 'public.claim_intake_job(text,text)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.enqueue_intake_job(text,text,text,text,text,text)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.complete_intake_job(uuid)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.fail_intake_job(uuid,text,integer,integer,timestamptz)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.claim_pending_events(integer,integer)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.claim_intake_finalize(uuid,integer)', 'EXECUTE') THEN
        otvoreno := otvoreno || 'service_role izgubio EXECUTE na worker RPC'::text;
    END IF;

    IF array_length(otvoreno, 1) > 0 THEN
        RAISE EXCEPTION 'Migracija 147: privilegije nisu zatvorene: %', array_to_string(otvoreno, '; ');
    END IF;
END
$$;

COMMIT;

-- ── PROVERA (read-only, posle izvršenja) ────────────────────────────────────
-- SELECT c.relname, r.rolname, has_table_privilege(r.rolname, c.oid, 'SELECT') AS select_dozvoljen
--   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--   CROSS JOIN (VALUES ('anon'), ('authenticated'), ('service_role')) r(rolname)
--  WHERE n.nspname = 'public'
--    AND c.relname IN ('case_profitability','klijenti_retention_candidates','feature_analytics',
--                      'intake_queue_metrics','events_outbox_metrics','v_manual_queue','v_qualified_jobs')
--  ORDER BY 1, 2;                                   -- anon/authenticated: false; service_role: true
-- SELECT p.oid::regprocedure, r.rolname, has_function_privilege(r.rolname, p.oid, 'EXECUTE')
--   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--   CROSS JOIN (VALUES ('anon'), ('authenticated'), ('service_role')) r(rolname)
--  WHERE n.nspname = 'public'
--    AND p.proname IN ('enqueue_intake_job','claim_intake_job','complete_intake_job','fail_intake_job',
--                      'claim_pending_events','claim_intake_finalize','v2_proveri_kontradikciju')
--  ORDER BY 1, 2;                                   -- anon/authenticated: false; service_role: true
-- Data API (javni ključ, HEAD + Prefer: count=exact) nad case_profitability → 401/403, ne 200.
--
-- ── ROLLBACK ─────────────────────────────────────────────────────────────────
-- NE vraćati grantove za anon/authenticated — to ponovo otvara P0 izloženost.
-- Ako legitimni backend tok padne, uzrok je nedostajući service_role grant:
-- dodati TAČNO taj GRANT ... TO service_role, nikad anon/authenticated.
