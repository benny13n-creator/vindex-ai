-- migrations/145_hronologija_dogadjaj_event_id.sql
-- BA04/BA08 (P7714/2026): identitet unosa hronologije koji nastaje iz trajnog događaja (Case Evolution
-- `timeline_entry`). Pokrenuti u Supabase SQL Editor. Bezbedno za ponovno pokretanje. Isključivo DODAJE kolonu i
-- delimičan indeks; postojeći redovi se NE menjaju (ostaju NULL). Nema promene RLS-a ni dozvola.
--
-- Do sada je idempotencija upisa „Dokument prihvaćen — <ime>“ poredila VIDLJIV tekst u prozoru od 300 s, pa su dva
-- RAZLIČITA prihvatanja dokumenata istog imena (dva `scan.pdf`) bila jedan red. Identitet je sada `events.id`
-- događaja koji je unos proizveo: isti događaj ponovljen (pad posle upisa) = isti red; dva događaja = dva reda.
-- Nema FK prema `events` (unos hronologije ostaje i ako se red outbox-a očisti).
--
-- REDOSLED: ova migracija PRE koda koji je koristi. Stari kod nad novom šemom: radi kao do sada (kolonu ne piše,
-- NULL se ne sudara). Nov kod nad starom šemom: radi kao do sada (prozor po tekstu, ERROR u logu).

ALTER TABLE public.predmet_hronologija
    ADD COLUMN IF NOT EXISTS dogadjaj_event_id uuid;

CREATE UNIQUE INDEX IF NOT EXISTS uq_hronologija_dogadjaj_event
    ON public.predmet_hronologija (predmet_id, dogadjaj_event_id)
    WHERE dogadjaj_event_id IS NOT NULL;

COMMENT ON COLUMN public.predmet_hronologija.dogadjaj_event_id IS
  'BA04: events.id trajnog događaja koji je proizveo ovaj unos (Case Evolution timeline_entry). NULL = unos koji nije iz događaja ili nastao pre 145 — ne učestvuje u jedinstvenosti.';

-- [ODUSTAJANJE] (vraća šemu; redovi ostaju, gubi se samo veza unosa sa događajem):
-- DROP INDEX IF EXISTS public.uq_hronologija_dogadjaj_event;
-- ALTER TABLE public.predmet_hronologija DROP COLUMN IF EXISTS dogadjaj_event_id;
