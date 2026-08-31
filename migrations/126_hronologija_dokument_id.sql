-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 126: KANONSKI IZVOR DOGADJAJA U HRONOLOGIJI (B8)
--
-- ⚠ NIJE IZVRSENA. Pokrece je osnivac.
--
-- ─── STA ZATVARA ───────────────────────────────────────────────────────────
--
-- `predmet_hronologija` danas pamti izvor kao `dokument_naziv` -- TEKST. A001
-- je vec utvrdio da ime fajla nije identitet: menja se pri preimenovanju, a dva
-- dokumenta istog predmeta smeju da se zovu isto. Posledica: advokat vidi
-- "Rok za zalbu: 15 dana" i ne moze da klikne na resenje koje ga je pokrenulo.
--
-- Mereno pre izmene (produkcija, 52 reda): 49 redova ima `dokument_naziv`,
-- 0 redova ima bilo kakvu referencu na `predmet_dokumenti.id`.
--
-- ─── ZASTO JE KOLONA ZAISTA POTREBNA ───────────────────────────────────────
--
-- Pravilo sprinta je: ne uvoditi kolonu ako postojeca struktura moze da nosi
-- podatak. `dokument_naziv` NE moze -- on je prikaz, ne identitet. Nijedna
-- druga kolona (`akter`, `dogadjaj`, `vaznost`) ne referencira dokument.
--
-- ─── STA JE VEC URADJENO BEZ MIGRACIJE ─────────────────────────────────────
--
-- Aplikacioni deo je vec zatvoren i dokazan uzivo (7/7) BEZ ove kolone:
--   * `case_dna.rokovi_kriticni[].dokument_id` nosi kanonski identitet
--     (razresen iz `DOK-NN` preko `predmet_dokumenti.redni_broj`, istim
--     `_DOK_PATTERN` mehanizmom koji A002 vec koristi za kontradikcije);
--   * `predmet_hronologija.dokument_naziv` se sada IZVODI iz tog identiteta,
--     a ne prepisuje iz LLM teksta.
--
-- Ova migracija dodaje poslednji korak: samu referencu u hronologiji.
--
-- ─── POSLE POKRETANJA ──────────────────────────────────────────────────────
--
-- Tek kada ova kolona postoji, `_sync_rokovi_to_hronologija` sme da je upisuje.
-- Do tada kod NAMERNO ne salje `dokument_id` -- upis nepostojece kolone bi
-- oborio svaki sync roka (zakljucano testom
-- `test_hronologija_ne_upisuje_dokument_id_pre_migracije`).
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE public.predmet_hronologija
    ADD COLUMN IF NOT EXISTS dokument_id UUID
    REFERENCES public.predmet_dokumenti(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.predmet_hronologija.dokument_id IS
  'B8 -- kanonski izvor dogadjaja: predmet_dokumenti.id iz kog dogadjaj (rok) potice. NULL je TACNA vrednost kada izvor nije jednoznacno razresen -- nikad se ne pogadja. `dokument_naziv` ostaje kao prikaz, ali vise nije jedini identifikator izvora. ON DELETE SET NULL: brisanje dokumenta ne sme obrisati istorijski dogadjaj.';

-- Citanje po dokumentu ("sta je sve ovaj dokument pokrenuo") -- parcijalni
-- indeks jer ce vecina istorijskih redova ostati NULL.
CREATE INDEX IF NOT EXISTS idx_hronologija_dokument
    ON public.predmet_hronologija (dokument_id)
    WHERE dokument_id IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════════════
-- STA OVAJ FAJL SVESNO NE RESAVA
--
-- 1. POSTOJECIH 52 REDA OSTAJE BEZ `dokument_id`. Nema backfill-a: ime fajla
--    se ne sme retroaktivno pretvarati u identitet -- to je tacno pogadjanje
--    koje A001 zabranjuje. Stari redovi zadrzavaju `dokument_naziv`.
--
-- 2. Ostali pisci u `predmet_hronologija` (`routers/intake.py`,
--    `routers/copilot.py`, `routers/learning.py`) NISU dirani -- oni ne
--    proizvode dogadjaj iz Genome roka i van su opsega B8.
--
-- ROLLBACK:
--   DROP INDEX IF EXISTS public.idx_hronologija_dokument;
--   ALTER TABLE public.predmet_hronologija DROP COLUMN IF EXISTS dokument_id;
-- ═══════════════════════════════════════════════════════════════════════════
