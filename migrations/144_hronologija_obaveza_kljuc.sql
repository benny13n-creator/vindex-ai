-- migrations/144_hronologija_obaveza_kljuc.sql
-- BA05 (PR #61, OBLIGATION_IDENTITY_CONTRACT): identitet obaveze roka u `predmet_hronologija`.
-- Pokrenuti u Supabase SQL Editor. Bezbedno za ponovno pokretanje. Isključivo DODAJE kolonu i delimičan indeks;
-- postojeći redovi se NE menjaju (ostaju NULL = zatečen red / identitet nepoznat). Nema promene RLS-a ni dozvola.
--
-- Ključ (64 hex, sha256) računa aplikacija: sadržaj izvornog dokumenta (heš teksta, isti kao
-- `predmet_dokumenti.content_sha256`) + datum + dokazna fraza iz TEKSTA dokumenta (`shared/rokovi.kljuc_obaveze`).
-- Tekst modela i naslov reda nisu deo ključa. Brisanje dokumenta ne menja ključ (heš sadržaja ostaje u ključu), pa
-- ponovo otpremljen isti sadržaj ne pravi nov kandidat, a odluka advokata ostaje na postojećem redu.
--
-- REDOSLED: ova migracija PRE koda koji je koristi (PR #61). Stari kod nad novom šemom: radi kao do sada (kolonu ne
-- piše, NULL se ne sudara). Nov kod nad starom šemom: piše rokove BEZ identiteta (ERROR u logu) — mogući duplikat,
-- nikad potiskivanje obaveze.
-- Jedinstvenost važi po predmetu i između procesa: UNIQUE (predmet_id, obaveza_kljuc) WHERE obaveza_kljuc IS NOT NULL.
-- Dve različite obaveze nikad nemaju isti ključ (drugi dokument = drugi heš; ista dokument/datum = druga fraza).

ALTER TABLE public.predmet_hronologija
    ADD COLUMN IF NOT EXISTS obaveza_kljuc text;

ALTER TABLE public.predmet_hronologija
    DROP CONSTRAINT IF EXISTS predmet_hronologija_obaveza_kljuc_check;

ALTER TABLE public.predmet_hronologija
    ADD CONSTRAINT predmet_hronologija_obaveza_kljuc_check
    CHECK (obaveza_kljuc IS NULL OR obaveza_kljuc ~ '^[0-9a-f]{64}$');

CREATE UNIQUE INDEX IF NOT EXISTS uq_hronologija_obaveza_kljuc
    ON public.predmet_hronologija (predmet_id, obaveza_kljuc)
    WHERE obaveza_kljuc IS NOT NULL;

COMMENT ON COLUMN public.predmet_hronologija.obaveza_kljuc IS
  'BA05: identitet obaveze roka = sha256(sadržaj izvornog dokumenta | datum | dokazna fraza iz teksta). Nikad tekst modela ni naslov. NULL = zatečen red ili identitet nepoznat (izvor nerazrešen) — ne učestvuje u jedinstvenosti.';

-- [ODUSTAJANJE] (vraća šemu; ključevi upisanih rokova se gube, redovi i odluke ostaju):
-- DROP INDEX IF EXISTS public.uq_hronologija_obaveza_kljuc;
-- ALTER TABLE public.predmet_hronologija DROP CONSTRAINT IF EXISTS predmet_hronologija_obaveza_kljuc_check;
-- ALTER TABLE public.predmet_hronologija DROP COLUMN IF EXISTS obaveza_kljuc;
