-- ============================================================================
-- Vindex AI -- Migracija 079: SEC-034 finalizacija -- predmet_delegiranja.predmet_id FK
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor.
--
-- KONTEKST: scripts/sec034_live_completeness_check.sql (2026-07-23) je
-- pokrenut protiv produkcije i pokazao da predmet_delegiranja ima samo 2
-- od 3 FK koje migracija 054 definise -- oba auth.users FK-a (od_user_id,
-- na_user_id) su prisutna (dodati rucno tokom SEC-031 zavrsetka), ali
-- predmet_id -> predmeti(id) NIKAD nije primenjen, jer je CREATE TABLE IF
-- NOT EXISTS u 054 tiho preskocio celo telo (isti SEC-034 mehanizam).
--
-- ODLUKA O ON DELETE PRAVILU (2026-07-23, potvrdio founder): CASCADE, ne
-- RESTRICT -- iz 3 razloga:
--   1. Konzistentnost sa izvornom definicijom u migraciji 054 (koja je
--      oduvek govorila ON DELETE CASCADE za ovu kolonu).
--   2. Izbegava komplikovanje operativnog koda -- routers/enterprise.py
--      nema nijedan endpoint za brisanje predmet_delegiranja redova, pa bi
--      RESTRICT ucinio SVAKI predmet koji je ikad delegiran trajno
--      neobrisivim kroz aplikaciju.
--   3. Razlicito od SEC-031 po prirodi: SEC-031 je stitio auth.users ->
--      (predmeti, fakture, dokazi...) smer, gde je katastrofalna posledica
--      brisanje korisnika brisalo citavu poslovnu istoriju. Ovde je smer
--      obrnut -- predmet_delegiranja PRIPADA predmetu (predmeti -> njeni
--      podaci), pa je CASCADE ovde ocekivano, ispravno ponasanje: kad
--      predmet nestane, istorija njegovih delegacija logicno nestaje s
--      njim. Sami predmeti su i dalje zasticeni RESTRICT-om prema
--      auth.users (SEC-031), pa brisanje naloga i dalje ne moze slucajno
--      obrisati predmet.
--
-- Ne dira auth.users niti ijedan RESTRICT constraint iz migracije 077 --
-- van domena SEC-031 u potpunosti. Koristi NOT VALID + VALIDATE CONSTRAINT
-- (isti obrazac kao 077) radi minimalnog lock-a, iako je predmet_delegiranja
-- trenutno prazna tabela (0 redova, potvrdjeno live upitom) -- ispravan
-- obrazac bez obzira na trenutni broj redova.
-- ============================================================================

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'predmet_delegiranja_predmet_id_fkey'
  ) THEN
    ALTER TABLE public.predmet_delegiranja
      ADD CONSTRAINT predmet_delegiranja_predmet_id_fkey
      FOREIGN KEY (predmet_id) REFERENCES public.predmeti(id) ON DELETE CASCADE
      NOT VALID;
  END IF;
END $$;

ALTER TABLE public.predmet_delegiranja
  VALIDATE CONSTRAINT predmet_delegiranja_predmet_id_fkey;

COMMIT;

-- ============================================================================
-- VERIFIKACIJA POSLE POKRETANJA (read-only, pokreni odvojeno):
--
-- SELECT conname, confrelid::regclass AS references_table, confdeltype
-- FROM pg_constraint
-- WHERE conrelid = 'public.predmet_delegiranja'::regclass AND contype = 'f'
-- ORDER BY conname;
--
-- Ocekivano: 3 reda -- predmet_delegiranja_predmet_id_fkey (confdeltype='c'
-- za CASCADE), plus oba auth.users FK-a (confdeltype='r' za RESTRICT, iz
-- migracije 077).
-- ============================================================================

-- ============================================================================
-- ROLLBACK (ne pokretati automatski -- samo ako se ispostavi problem):
--
-- BEGIN;
-- ALTER TABLE public.predmet_delegiranja
--   DROP CONSTRAINT IF EXISTS predmet_delegiranja_predmet_id_fkey;
-- COMMIT;
-- ============================================================================
