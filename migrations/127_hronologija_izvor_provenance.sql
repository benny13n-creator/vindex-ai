-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 127: predmet_hronologija.izvor — PROVENIJENCIJA SADRZAJA
-- Run in: Supabase Dashboard -> SQL Editor -> New query -> Run All
-- Idempotentna: bezbedno je pokrenuti vise puta.
--
-- ZASTO POSTOJI (forenzicki utvrdjeno, FAZA 6.1-6.3):
--   FAZA 6.2 je postavila bezbednosnu kapiju koja je poreklo zapisa citala iz
--   kolone `akter`. FAZA 6.2.1 je dokazala da je to pogresno: `akter` NIJE
--   provenijencija. `api.py::predmet_upload_auto_analyze` upisuje u `akter`
--   TEKST KOJI JE VRATIO MODEL (prompt: "Ko je preduzeo radnju (osoba, firma,
--   sud...)"), pa je AI-ekstrahovan rok stizao do kapije kao "Poslodavac DOO
--   Sever" i prolazio kao ljudski unos. Mereno: 49/55 redova je prolazilo
--   kapiju bez ijedne potvrde, 27 njih podobno za email/SMS podsetnik.
--
--   FAZA 6.3 je popisala SVE pisce: 16 direktnih `.insert()`, 0 DB-side,
--   0 indirektnih, 0 UPDATE/DELETE putanja. 15/16 upisuje stabilan potpis u
--   `akter`; tacno jedan (W-UPLOAD) upisuje slobodan LLM tekst i objasnjava
--   49/55 redova. Jedan pisac je unistio semantiku polja za ceo sistem.
--
-- CETIRI ODVOJENE OSE koje se od sada NE SMEJU mesati:
--   `akter`   — KO je izvrsio radnju (stranka u dogadjaju)
--   `izvor`   — KAKO je sadrzaj zapisa nastao        <- ova migracija
--   potvrda   — DA LI je covek odobrio izvrsivu upotrebu (audit_immutable)
--   `vaznost` — KOLIKO je dogadjaj vazan
--
-- SUSTINA UGOVORA: **NEMA DEFAULT-a.**
--   Default bi maskirao propust buduceg pisca i tiho ga svrstao u neku klasu.
--   Bez njega, 17. pisac koji zaboravi `izvor` dobija 23502 i pada GLASNO.
--   Model koji dozvoljava "insert bez provenijencije -> implicitno ljudski"
--   je time strukturno onemogucen.
--
-- REDOSLED PRIMENE (obavezan):
--   1) OVA MIGRACIJA          <- prvo
--   2) tek onda deploy koda koji salje `izvor`
--   Obrnut redosled obara SVAKI upis u hronologiju (kolona ne postoji).
--
-- ROLLBACK:
--   ALTER TABLE public.predmet_hronologija DROP CONSTRAINT IF EXISTS predmet_hronologija_izvor_check;
--   ALTER TABLE public.predmet_hronologija ALTER COLUMN izvor DROP NOT NULL;
--   ALTER TABLE public.predmet_hronologija DROP COLUMN IF EXISTS izvor;
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── KORAK 1: kolona, jos uvek NULLABLE i BEZ DEFAULT-a ─────────────────────
-- Nullable je PRIVREMENO stanje unutar ove transakcije: postojecih 55 redova
-- mora dobiti vrednost pre nego sto NOT NULL moze da se aktivira.
ALTER TABLE public.predmet_hronologija
  ADD COLUMN IF NOT EXISTS izvor TEXT;

-- ─── KORAK 2: BACKFILL — svi postojeci redovi su LEGACY_UNKNOWN ─────────────
-- BEZ IZUZETAKA I BEZ HEURISTIKE.
--
-- Razmatrano i ODBACENO: klasifikovati redove sa `akter IN ('Genome (AI)',
-- 'Pipeline (AI)')` kao AI_AUTONOMOUS. Odbaceno zato sto bi i to bila
-- heuristika NAD `akter` poljem — tacno onim cija je nepouzdanost i dovela do
-- ove migracije. W-UPLOAD upisuje proizvoljan LLM tekst u to isto polje, pa
-- nijedna njegova vrednost nije dokaz o piscu.
--
-- LEGACY_UNKNOWN NIJE "ljudski" i NIJE "AI". To je eksplicitno priznanje da
-- poreklo nije dokazivo. Kapija ga tretira fail-closed.
UPDATE public.predmet_hronologija
   SET izvor = 'LEGACY_UNKNOWN'
 WHERE izvor IS NULL;

-- ─── KORAK 3: CHECK — nepoznata vrednost pada sa 23514, ne postaje "ljudska" ─
ALTER TABLE public.predmet_hronologija
  DROP CONSTRAINT IF EXISTS predmet_hronologija_izvor_check;

ALTER TABLE public.predmet_hronologija
  ADD CONSTRAINT predmet_hronologija_izvor_check
  CHECK (izvor IN (
      'AI_AUTONOMOUS',   -- model proizveo sadrzaj bez da ga je covek video pre upisa
      'AI_ASSISTED',     -- covek dao/video vrednost, model je samo strukturirao
      'HUMAN_DIRECT',    -- covek uneo sadrzaj rukom
      'DETERMINISTIC',   -- staticki katalog u kodu, covek izabrao
      'SYSTEM',          -- posledica lifecycle dogadjaja, nije opazanje
      'LEGACY_UNKNOWN'   -- nastalo pre ugovora, poreklo nedokazivo
  ));

-- ─── KORAK 4: NOT NULL ──────────────────────────────────────────────────────
-- Aktivira se TEK posle backfill-a, inace bi pao na postojecim redovima.
ALTER TABLE public.predmet_hronologija
  ALTER COLUMN izvor SET NOT NULL;

-- ─── KORAK 5: eksplicitno ukloni DEFAULT ako ga je iko ikad postavio ────────
-- `ADD COLUMN` iznad ga ne postavlja, ali ovo je brava protiv buduceg
-- "pomocnog" DEFAULT-a koji bi tiho ponistio celu svrhu ugovora.
ALTER TABLE public.predmet_hronologija
  ALTER COLUMN izvor DROP DEFAULT;

-- ─── DOKUMENTACIJA ──────────────────────────────────────────────────────────
COMMENT ON COLUMN public.predmet_hronologija.izvor IS
  'PROVENIJENCIJA SADRZAJA: kako je zapis nastao. NIJE `akter` (ko je izvrsio radnju), NIJE potvrda (da li je covek odobrio), NIJE `vaznost` (koliko je vazno). NOT NULL i BEZ DEFAULT-a namerno: pisac koji zaboravi provenijenciju mora pasti sa 23502, ne postati tiho ljudski. LEGACY_UNKNOWN znaci "poreklo nije dokazivo" i tretira se fail-closed.';

-- ─── PROVERA FINALNOG STANJA (ne verovati tome da SQL nije prijavio gresku) ──
-- Ocekivano: is_nullable='NO', column_default=NULL, 55 redova LEGACY_UNKNOWN.
--
--   SELECT column_name, data_type, is_nullable, column_default
--     FROM information_schema.columns
--    WHERE table_name = 'predmet_hronologija' AND column_name = 'izvor';
--
--   SELECT izvor, count(*) FROM public.predmet_hronologija GROUP BY izvor;
--
--   SELECT conname, pg_get_constraintdef(oid)
--     FROM pg_constraint
--    WHERE conrelid = 'public.predmet_hronologija'::regclass
--      AND conname = 'predmet_hronologija_izvor_check';
