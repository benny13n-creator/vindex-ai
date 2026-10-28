-- migrations/142_email_podsetnik_dogadjaj.sql
-- Sektor 2 (odluke osnivača D2–D4): rezervacija email podsetnika po DOGAĐAJU, ne po predmetu.
-- Pokrenuti u Supabase SQL Editor. Bezbedno za ponovno pokretanje. Isključivo DODAJE — `email_notif_log` (021/022)
-- se ne menja: stari kod i nedeljni pregled rade nepromenjeno nad njim.
--
-- REDOSLED: ova migracija PRE koda koji je koristi. Stari kod nad novom šemom: radi kao do sada (nove tabele ne
-- čita). Nov kod nad starom šemom: dnevno slanje vraća greska i NE šalje ništa (posao crven) — ništa se ne gubi
-- trajno osim podsetnika tog dana.
-- VRAĆANJE KODA: nov kod NE piše `email_notif_log`, pa stari kod vraćen ISTOG dana ponovo šalje podsetnike koje je
-- nov kod tog dana već poslao (najviše jedan duplikat po predmetu/datumu/pragu). Vraćati kod POSLE dnevnog slanja
-- ili sledećeg dana pre njega. Tabele ostaju (stari kod ih ignoriše); vidi OPORAVAK na kraju fajla.
--
-- Ključ: (user_id, tip, dogadjaj_id, datum_dogadjaja, svrha)
--   tip             'rok' (predmet_hronologija.id) | 'rociste' (rocista.id)
--   datum_dogadjaja datum POJAVE — pomereno ročište je nova pojava i dobija svoje podsetnike
--   svrha           'prag_1' | 'prag_3' | 'prag_7' (redovni) | 'kasni' (dodatni, kad redovni više ne stiže)
-- Stanja:
--   rezervisano  pokušaj u toku ili prekinut — ishod NEPOZNAT, ne ponavlja se
--   poslato      SMTP je prihvatio poruku (NIJE potvrda prijema u sanduče)
--   neuspeh      poruka sigurno NIJE predata (veza/TLS/prijava/odbijen primalac pre sadržaja, 4xx) — sme ponovo
--   odbijeno     provajder je trajno odbio poruku (5xx) — ne ponavlja se
--   nepoznato    veza je pukla posle predaje sadržaja — ne ponavlja se
-- Istorija iz `email_notif_log` se NE prepisuje u ovu tabelu: stari red pokriva predmet, ne događaje, pa bi prepis
-- izmislio pokrivenost. Kod je čita pri odlučivanju (događaj izvršiv pre slanja starog reda smatra se pokrivenim).

CREATE TABLE IF NOT EXISTS public.email_podsetnik_dogadjaj (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT        NOT NULL,
    predmet_id       TEXT        NOT NULL,
    tip              TEXT        NOT NULL CHECK (tip IN ('rok', 'rociste')),
    dogadjaj_id      TEXT        NOT NULL,
    datum_dogadjaja  DATE        NOT NULL,
    svrha            TEXT        NOT NULL CHECK (svrha IN ('prag_1', 'prag_3', 'prag_7', 'kasni')),
    stanje           TEXT        NOT NULL DEFAULT 'rezervisano'
                                 CHECK (stanje IN ('rezervisano', 'poslato', 'neuspeh', 'odbijeno', 'nepoznato')),
    pokusaja         SMALLINT    NOT NULL DEFAULT 1 CHECK (pokusaja >= 1),
    greska           TEXT,
    prijavljeno_at   TIMESTAMPTZ,      -- nepoznat/zaglavljen ishod uračunat u brojače dnevnog slanja (jednom)
    rezervisano_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    azurirano_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT email_podsetnik_dogadjaj_kljuc UNIQUE (user_id, tip, dogadjaj_id, datum_dogadjaja, svrha)
);

CREATE INDEX IF NOT EXISTS idx_email_podsetnik_dogadjaj_korisnik
    ON public.email_podsetnik_dogadjaj (user_id, datum_dogadjaja);

ALTER TABLE public.email_podsetnik_dogadjaj ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON public.email_podsetnik_dogadjaj TO service_role;

-- Dan za koji je dnevno slanje već pokrenuto (Europe/Belgrade kalendar). Hitna provera posle advokatove radnje šalje
-- redovni prag odmah SAMO ako je današnje dnevno slanje već prošlo; inače ga ostavlja dnevnom slanju.
CREATE TABLE IF NOT EXISTS public.email_podsetnik_pokretanje (
    dan            DATE        PRIMARY KEY,
    pokrenuto_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.email_podsetnik_pokretanje ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON public.email_podsetnik_pokretanje TO service_role;

-- OPORAVAK JE NEDESTRUKTIVAN (runbook docs/release/S2_PODSETNICI_142_RUNBOOK.md): pauza
-- (VINDEX_EMAIL_PODSETNICI_PAUZA=1) ili vraćanje koda POSLE dnevnog slanja; tabele i istorija OSTAJU.
-- [ODUSTAJANJE] SAMO ako 142 nikad nije zabeležila nijedan stvaran podsetnik — blok odbija brisanje čim postoji zapis:
-- DO $$ BEGIN
--   LOCK TABLE public.email_podsetnik_dogadjaj, public.email_podsetnik_pokretanje IN ACCESS EXCLUSIVE MODE;
--   IF EXISTS (SELECT 1 FROM public.email_podsetnik_dogadjaj) OR EXISTS (SELECT 1 FROM public.email_podsetnik_pokretanje) THEN
--     RAISE EXCEPTION 'email_podsetnik_* ima zapise — ne brisati (istorija slanja); koristiti pauzu/vraćanje koda';
--   END IF;
--   DROP TABLE public.email_podsetnik_pokretanje;
--   DROP TABLE public.email_podsetnik_dogadjaj;
-- END $$;
