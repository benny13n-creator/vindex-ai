-- 114 — BETA-DEL-001: TOMBSTONE ZA BRISANJE PREDMETA
--
-- ZAŠTO
--
-- Dokazano uživo 3/3 na produkcionom commitu 27cb670: `DELETE /api/predmeti/{id}`
-- briše Pinecone vektore PRE redova u bazi. Kad brisanje redova padne (FK
-- `case_evolution_consequences.event_id -> events.id`, migracija 096, bez
-- `ON DELETE`), predmet ostaje živ — a njegovi vektori su nepovratno obrisani.
-- Korisnik dobija „operacija se moze ponoviti", što je neistina: identičan
-- retry deterministički pada opet.
--
-- Popravka pomera brisanje vektora IZA svih brisanja u bazi. Da bi to bilo
-- bezbedno, predmet mora biti nevidljiv dok traje brisanje — inače bi pad na
-- koraku vektora ostavio vidljiv predmet sa polovično uklonjenim podacima.
-- Ova kolona je to stanje.
--
-- ZAŠTO NE POSTOJEĆA KOLONA `status`
--
-- `predmeti.status` je POSLOVNO polje korisnika (danas: 22/22 = 'aktivan').
-- Upis stanja brisanja u nju trajno bi prepisao korisnikovu vrednost kad
-- brisanje padne — dakle gubitak podatka, tačno klasa greške koju ova migracija
-- postoji da spreči. Zato zasebna, jednonamenska kolona.
--
-- SEMANTIKA
--
--   brisanje_zapoceto IS NULL      predmet je ACTIVE
--   brisanje_zapoceto IS NOT NULL  brisanje je u toku ili je palo (DELETING)
--   reda nema                      DELETED
--
-- BEZBEDNOST DEPLOY-A
--
-- Aditivna i idempotentna. Kod NE pretpostavlja da je primenjena: ako upis
-- tombstone-a ne uspe, ishod je PERMANENT_FAILURE i NIŠTA se ne dira. Zato je
-- bezbedan bilo koji redosled (kod pre migracije ili migracija pre koda).
--
-- ROLLBACK
--
--   ALTER TABLE public.predmeti DROP COLUMN IF EXISTS brisanje_zapoceto;
--
-- Gubi se samo evidencija započetih brisanja; nijedan korisnički podatak.
-- Posle rollback-a kod ponovo vraća PERMANENT_FAILURE i ne dira ništa.

ALTER TABLE public.predmeti
    ADD COLUMN IF NOT EXISTS brisanje_zapoceto TIMESTAMPTZ;

COMMENT ON COLUMN public.predmeti.brisanje_zapoceto IS
    'BETA-DEL-001 tombstone. NULL = predmet je aktivan. NOT NULL = brisanje je '
    'zapoceto; predmet je iskljucen iz liste, iz pojedinacnog dohvatanja i iz '
    'RAG retrieval-a (shared/rag_acl.dozvoljeni_predmeti), pa njegovi vektori '
    'ne mogu doci u kontekst. Postavlja se PRE prvog destruktivnog koraka i '
    'brise se samo brisanjem samog reda.';

-- Delimičan indeks: pogađa samo tombstonovane redove, pa ne opterećuje
-- uobičajene upite nad aktivnim predmetima. Služi operativnom pitanju
-- „koja brisanja su zapoceta a nisu zavrsena".
CREATE INDEX IF NOT EXISTS idx_predmeti_brisanje_u_toku
    ON public.predmeti (user_id, brisanje_zapoceto)
    WHERE brisanje_zapoceto IS NOT NULL;
