-- ════════════════════════════════════════════════════════════════════════════
-- MIGRACIJA 129 — MINIMALNI UGOVOR ROKA: VRSTA I STANJE
-- Z016.2 · aditivno · bez backfill-a · bez izmene zatečenog ponašanja
-- ════════════════════════════════════════════════════════════════════════════
--
-- ZAŠTO
--
-- `predmet_hronologija` je istovremeno i događajni dnevnik i de-facto skladište
-- rokova. Mereno: 16 upisnih putanja u 14 fajlova; tabela `rokovi` ne postoji i
-- nema nijednog pisca (`shared/rokovi.py`, BETA-DEADLINE-DOMAIN-001).
--
-- Posledica je da se „šta je ovaj red" moglo utvrditi samo pogađanjem:
-- `routers/kalendar.py::_klasifikuj_dogadjaj` ima catch-all `return
-- "rok_dokument"`, pa „Kraj zaposlenja tužioca kod tuženog" — istorijska
-- činjenica predmeta — izlazi kao ROK.
--
-- Izmereno na produkciji (2026-09-05): u prozoru od 365 dana kroz kandidate
-- prolazi 47 redova, od kojih su 2 predloga roka a 45 istorijske činjenice.
--
-- Ova migracija uvodi DVA eksplicitna signala. Ne uvodi novi entitet, ne dira
-- nijednu postojeću kolonu i ne menja nijedan postojeći red.
--
-- ── ŠTA OVA MIGRACIJA NAMERNO NE RADI ──────────────────────────────────────
--
--   * NEMA `DEFAULT`. Podrazumevana vrednost bi tiho proglasila 55 zatečenih
--     redova nečim što niko nije dokazao. `NULL` znači „nije izjavljeno" i
--     čita se fail-closed.
--   * NEMA backfill-a. Nijedan zatečeni red se ne klasifikuje retroaktivno,
--     ni heuristikom po tekstu, ni po `akter`, ni po `izvor`.
--   * NEMA `NOT NULL`. Postojeći pisci koji ne izjave vrstu i dalje rade.
--   * NE dira `izvor`. Provenijencija (migracija 127) opisuje KAKO je red
--     nastao; `vrsta` opisuje ŠTA red jeste; `stanje` opisuje GDE je u svom
--     životnom ciklusu. FAZA 6.4.1 je dokazala šta se dešava kada jedan
--     atribut preuzme tuđu ulogu — to se ovde ne ponavlja.
--
-- ════════════════════════════════════════════════════════════════════════════

-- ─── 1. VRSTA ZAPISA ────────────────────────────────────────────────────────
-- Odgovara na: šta je ovaj red?
--
--   rok       obaveza sa rokom koja traži postupanje
--   rociste   zakazano ročište (napomena: kanonski entitet je tabela `rocista`;
--             ova vrednost postoji za redove hronologije koji ga projektuju)
--   zadatak   zadatak kancelarije
--   dogadjaj  istorijska činjenica predmeta — NIJE obaveza
--   NULL      nije izjavljeno; ništa se ne tvrdi

ALTER TABLE public.predmet_hronologija
    ADD COLUMN IF NOT EXISTS vrsta text;

ALTER TABLE public.predmet_hronologija
    DROP CONSTRAINT IF EXISTS predmet_hronologija_vrsta_check;

ALTER TABLE public.predmet_hronologija
    ADD CONSTRAINT predmet_hronologija_vrsta_check
    CHECK (vrsta IS NULL OR vrsta IN ('rok', 'rociste', 'zadatak', 'dogadjaj'));


-- ─── 2. STANJE ŽIVOTNOG CIKLUSA ─────────────────────────────────────────────
-- Odgovara na: gde je ovaj rok u svom životnom ciklusu?
--
--   kandidat   predložen, čovek se nije izjasnio      -> „Za proveru"
--   potvrdjen  čovek je potvrdio                      -> „Obaveze"
--   odbijen    čovek je odbio; NIJE obrisan           -> nigde u aktivnom Danas
--   izvrsen    obaveza je izvršena                    -> nigde u aktivnom Danas
--   otkazan    obaveza je otkazana                    -> nigde u aktivnom Danas
--   NULL       nije izjavljeno; čitalac pada na model potvrde (audit trag)
--
-- ZAŠTO POSEBNA KOLONA, A NE SAMO `audit_immutable`
--
-- Audit beleži DOGAĐAJ („čovek je potvrdio u 14:03"), i to mora ostati
-- nepromenljiv trag. Ali `izvrsen` i `otkazan` nisu odluke o poreklu nego
-- poslovno stanje obaveze, i za njih u auditu nema ni akcije ni značenja.
-- Audit ostaje trag; ova kolona je domenski model.

ALTER TABLE public.predmet_hronologija
    ADD COLUMN IF NOT EXISTS stanje text;

ALTER TABLE public.predmet_hronologija
    DROP CONSTRAINT IF EXISTS predmet_hronologija_stanje_check;

ALTER TABLE public.predmet_hronologija
    ADD CONSTRAINT predmet_hronologija_stanje_check
    CHECK (stanje IS NULL OR stanje IN
           ('kandidat', 'potvrdjen', 'odbijen', 'izvrsen', 'otkazan'));


-- ─── 3. INDEKS ZA EKRAN DANAS ───────────────────────────────────────────────
-- Danas čita: moji redovi + vrsta='rok' + datum u prozoru.
-- Parcijalan indeks — pokriva samo rokove, ne ceo dnevnik.

CREATE INDEX IF NOT EXISTS idx_hronologija_rok_danas
    ON public.predmet_hronologija (user_id, datum_iso)
    WHERE vrsta = 'rok';


-- ─── 4. PROVERA POSLE POKRETANJA ────────────────────────────────────────────
--
--   SELECT column_name, data_type, is_nullable, column_default
--     FROM information_schema.columns
--    WHERE table_name = 'predmet_hronologija'
--      AND column_name IN ('vrsta', 'stanje');
--   -- očekivano: 2 reda, is_nullable = YES, column_default = NULL
--
--   SELECT count(*) AS ukupno,
--          count(vrsta) AS sa_vrstom,
--          count(stanje) AS sa_stanjem
--     FROM public.predmet_hronologija;
--   -- očekivano ODMAH POSLE migracije: sa_vrstom = 0, sa_stanjem = 0
--   -- (nijedan zatečeni red nije klasifikovan — to je namerno)
--
--   SELECT vrsta, stanje, count(*)
--     FROM public.predmet_hronologija
--    GROUP BY 1, 2 ORDER BY 3 DESC;
--   -- posle prvog novog roka: pojavljuje se ('rok','kandidat')


-- ─── 5. ROLLBACK ────────────────────────────────────────────────────────────
-- Kod podnosi rollback bez izmene: bez kolona čitanje pada u sopstveni except
-- i vraća `NULL` -> fail-closed, ništa se ne tvrdi.
--
--   DROP INDEX IF EXISTS idx_hronologija_rok_danas;
--   ALTER TABLE public.predmet_hronologija
--       DROP CONSTRAINT IF EXISTS predmet_hronologija_stanje_check,
--       DROP CONSTRAINT IF EXISTS predmet_hronologija_vrsta_check;
--   ALTER TABLE public.predmet_hronologija
--       DROP COLUMN IF EXISTS stanje,
--       DROP COLUMN IF EXISTS vrsta;
