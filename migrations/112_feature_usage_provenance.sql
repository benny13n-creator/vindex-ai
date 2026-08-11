-- ============================================================================
-- Migracija 112 — feature_usage_log PROVENANCE (Wave 9, §17)
--
-- PROBLEM
-- `feature_usage_log` (migracija 065:175) belezi KO je sta potrosio, ali ne i
-- U KOM KONTEKSTU. Nedostaju `predmet_id` i `correlation_id`, pa se lanac
--
--     user -> operation -> predmet -> correlation_id -> billing event -> AI provenance
--
-- ne moze dokazati spajanjem: naplata i AI provenance (`ai_forensics`,
-- migracije 043/089) zive u dve tabele koje nemaju zajednicki kljuc. Kad
-- advokat pita „zasto mi je naplaceno 6 kredita na ovom predmetu", odgovor se
-- danas ne moze izvesti iz baze.
--
-- RESENJE
-- Dve NULLABLE kolone. `correlation_id` je isti join kljuc koji vec nose
-- `events`, `audit_immutable` (migracija 090) i `ai_forensics` (089) —
-- Mission Ledger ga stampa jednom po HTTP zahtevu iz
-- `shared/ai_provenance.py::set_request_context`. Time naplata ulazi u
-- POSTOJECI lanac korelacije umesto da se pravi novi.
--
-- ZASTO JE BEZBEDNA
--   * Obe kolone su NULLABLE i BEZ DEFAULT vrednosti — Postgres ih dodaje kao
--     cisto metapodatkovnu izmenu (nema prepisa tabele, nema duge ACCESS
--     EXCLUSIVE brave nad velikom tabelom naplate).
--   * Postojeci redovi ostaju netaknuti (NULL = „nije bilo zabelezeno").
--   * Naplatna semantika se NE menja: nijedna kolona koja ucestvuje u
--     obracunu (`krediti_potroseni`) nije dirana, nijedan constraint dodat.
--   * VIEW `feature_analytics` (065) bira imenovane kolone, pa ga dodavanje
--     novih kolona ne obara i ne zahteva ponovno kreiranje.
--
-- ZASTO JE IDEMPOTENTNA
-- Sve je `IF NOT EXISTS` — ponovno pokretanje ne radi nista i ne baca gresku.
--
-- ZASTO NEMA FOREIGN KEY NA predmeti(id)
-- Namerno. Tri razloga:
--   1. Ovo je knjigovodstveni/telemetrijski log. FK sa ON DELETE CASCADE bi
--      BRISAO istoriju naplate kad se predmet obrise — gubitak finansijskog
--      traga. FK sa RESTRICT bi obrnuto onemogucio brisanje predmeta.
--      ON DELETE SET NULL bi tiho pojeo dokaz.
--   2. Upis je STROGO fail-soft (`shared/usage.py::_log_usage_event` gutа
--      greske da naplata nikad ne padne zbog telemetrije). FK violation bi
--      pretvorio trku „predmet obrisan u medjuvremenu" u tihi gubitak celog
--      reda loga.
--   3. `predmet_id` se ovde puni iz runtime konteksta (contextvar), koji nije
--      garantovano validan predmet — najgori slucaj sme biti „neupotrebljiv
--      metapodatak", ne „izgubljen red naplate".
-- Integritet se obezbedjuje na citanju (JOIN-om), ne na upisu.
-- ============================================================================

ALTER TABLE public.feature_usage_log ADD COLUMN IF NOT EXISTS predmet_id     uuid;
ALTER TABLE public.feature_usage_log ADD COLUMN IF NOT EXISTS correlation_id text;

-- Tip `uuid` za predmet_id je provereni izbor, ne pretpostavka:
-- `supabase_setup.sql:301` definise `public.predmeti.id UUID PRIMARY KEY`.

-- Indeks nad correlation_id — ovo je JEDINI pristupni obrazac koji ove kolone
-- opravdava: „daj mi sve sto se desilo u okviru jednog zahteva" (spajanje sa
-- events / audit_immutable / ai_forensics). Bez indeksa bi svaki forenzicki
-- upit bio sekvencijalno citanje cele tabele naplate.
-- Parcijalan (WHERE NOT NULL) jer ce svi redovi upisani PRE ove migracije, kao
-- i svaki upis van HTTP zahteva, imati NULL — nema svrhe indeksirati ih.
CREATE INDEX IF NOT EXISTS feature_usage_log_correlation_idx
    ON public.feature_usage_log (correlation_id)
    WHERE correlation_id IS NOT NULL;

-- Indeks nad predmet_id: obrazac „sve naplate na ovom predmetu" (prikaz
-- troska po predmetu advokatu). Takodje parcijalan iz istog razloga.
CREATE INDEX IF NOT EXISTS feature_usage_log_predmet_idx
    ON public.feature_usage_log (predmet_id, created_at DESC)
    WHERE predmet_id IS NOT NULL;

COMMENT ON COLUMN public.feature_usage_log.predmet_id IS
    'Wave 9 (§17) — predmet u cijem je kontekstu funkcija naplacena. NULLABLE i '
    'best-effort: puni se iz shared/ai_provenance contextvar-a ili iz eksplicitnog '
    'consume(predmet_id=...) argumenta. NULL znaci „nije zabelezeno" (npr. operacija '
    'nije vezana za predmet, ili poziv nije bio unutar case_context bloka), NIKAD '
    '„predmet ne postoji". Bez FOREIGN KEY namerno — vidi zaglavlje migracije 112: '
    'istorija naplate ne sme nestati kad se predmet obrise.';

COMMENT ON COLUMN public.feature_usage_log.correlation_id IS
    'Wave 9 (§17) — isti join kljuc kao events.correlation_id, '
    'audit_immutable.correlation_id (migracija 090) i ai_forensics.correlation_id '
    '(089). Postavlja ga shared/ai_provenance.py::set_request_context jednom po HTTP '
    'zahtevu. Zatvara lanac user -> operation -> correlation_id -> billing event -> '
    'AI provenance: posto ai_forensics nosi I correlation_id I predmet_id, predmet se '
    'moze dobiti tranzitivno cak i kad je predmet_id ovde NULL.';

DO $$
BEGIN
    RAISE NOTICE 'Migracija 112 zavrsena: feature_usage_log ima predmet_id i correlation_id.';
    RAISE NOTICE 'Forenzicki upit: SELECT l.*, f.predmet_id FROM feature_usage_log l '
                 'LEFT JOIN ai_forensics f USING (correlation_id) '
                 'WHERE l.correlation_id = ''<id>'';';
END $$;
