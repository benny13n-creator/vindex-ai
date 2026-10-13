-- ============================================================================
-- PREDLOG MIGRACIJE 138 — NIJE PRIMENJEN. Čeka izričito odobrenje osnivača.
-- Namerno NIJE u migrations/ da ga niko ne bi pokrenuo kao redovnu migraciju.
--
-- OCR001 (konkurentna finalizacija): atomska zaštita od drugog reda za ISTI dokument ISTOG Smart Intake posla.
--
-- Zašto: dva finalize procesa nad istim poslom (prvi radi duže od 120 s, drugi preuzme zastarelo zauzeće)
-- upisivala su isti dokument dvaput — dokazano: tests/test_ocr001_konkurentna_finalizacija.py. Aplikaciona ispravka
-- (routers/smart_intake.py::_potvrdi_zauzece) zatvara trku osim jednog prozora koji aplikacija ne može da zatvori:
-- upis poslat dok je zauzeće važilo, a koji „visi“ duže od rezerve (30 s) i stigne posle upisa drugog procesa.
-- Taj prozor zatvara samo ovaj indeks (tests/test_ocr001_trka_postgres.py, pravi PostgreSQL).
--
-- Opseg: samo redovi Smart Intake-a (source_intake_job_id IS NOT NULL). Ručno otpremanje u predmet (api.py,
-- Pipeline A) svesno dozvoljava isti sadržaj dvaput u istom predmetu i NIJE pogođeno (tamo je source_intake_job_id
-- NULL). Dva RAZLIČITA posla sa istim sadržajem nisu u opsegu ovog indeksa.
--
-- Bezbedno i bez ove migracije: kod obrađuje 23505 na ovom indeksu kao „isti dokument već postoji“ (poveže
-- postojeći red), pa se može primeniti pre ili posle spajanja koda. Ne menja nijedan postojeći red.
-- ============================================================================

-- [PROVERA] 1) Postojeći podaci — MORA vratiti 0 redova pre koraka 2. Ako vrati redove: NE brisati ništa
--             automatski; to su već nastali duplikati i odluka o njima je osnivačeva.
SELECT source_intake_job_id, content_sha256, predmet_id, count(*) AS redova, array_agg(id::text) AS dokumenti
FROM public.predmet_dokumenti
WHERE source_intake_job_id IS NOT NULL AND content_sha256 IS NOT NULL
GROUP BY source_intake_job_id, content_sha256, predmet_id
HAVING count(*) > 1;

-- [PRIMENA] 2) Indeks. Tabela je mala (beta), zato bez CONCURRENTLY: kratko zaključavanje upisa u predmet_dokumenti
--             dok se indeks gradi; CONCURRENTLY ne može u transakciji SQL editora i ostavlja INVALID indeks ako padne.
CREATE UNIQUE INDEX IF NOT EXISTS uq_predmet_dokumenti_posao_sadrzaj
    ON public.predmet_dokumenti (source_intake_job_id, content_sha256)
    WHERE source_intake_job_id IS NOT NULL AND content_sha256 IS NOT NULL;

-- [POTVRDA] 3) Očekivano: jedan red, indisunique = true, indisvalid = true.
SELECT c.relname, i.indisunique, i.indisvalid, pg_get_indexdef(i.indexrelid) AS definicija
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'uq_predmet_dokumenti_posao_sadrzaj';

-- [ROLLBACK] Uklanja samo indeks; podaci ostaju netaknuti. Kod radi i bez indeksa (vraća se preostali prozor).
-- DROP INDEX IF EXISTS public.uq_predmet_dokumenti_posao_sadrzaj;
