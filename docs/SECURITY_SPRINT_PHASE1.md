# Vindex AI — Security & Production Sprint, Opcija A (2026-07-26)

**Status:** Implementirano i verifikovano. Nula regresija (2242 passed, 1
skipped — identičan broj kao pre ovog sprinta, pošto ovaj sprint dodaje
CI/verifikacionu infrastrukturu, ne nove funkcionalne testove).

---

## 1. DevSecOps GitHub Actions Workflow

### 1.1 Korekcija premise — 3 od 4 skenera VEĆ POSTOJE

Pre bilo kakve izmene, `.github/workflows/security.yml` je pregledan u
celosti. Rezultat: **Gitleaks, Bandit i pip-audit su već implementirani**
(Celina 5, 2026-07-24, `secret-scan`/`sast-core`+`sast-full`/
`dependency-scan` job-ovi), pokrenuti na `push`/`pull_request` ka `main`
grani + `workflow_dispatch`. **Jedini nedostajući skener iz zahteva je
Semgrep.**

**Odluka: dopunjen postojeći `security.yml`, NIJE kreiran novi
`security_scan.yml`.** Kreiranje drugog fajla koji ponovo pokreće
Gitleaks/Bandit/pip-audit bi značilo duplirane CI provere (2x potrošeno
CI vreme, 2 mesta za održavanje istih pravila, rizik da se izmene rade
samo na jednom od dva fajla ubuduće). Ako founder ipak želi tačno ime
`security_scan.yml` (npr. zbog eksternog alata koji ga referencira po
imenu), fajl se može preimenovati u jednom potezu bez gubitka istorije
(`git mv`) — nema drugih referenci na `security.yml` po imenu nigde u
repou (provereno).

### 1.2 Dodato: `semgrep-core` + `semgrep-full`

Isti dvoslojni obrazac kao postojeći Bandit job-ovi:

- **`semgrep-core`** — BLOKIRAJUĆI. Skoniran na isti obim kao
  `sast-core` (`api.py main.py routers/ shared/ security/ services/
  app/`), `p/security-audit` + `p/python` public registry rulesets (ne
  zahtevaju Semgrep nalog/token), samo `ERROR` severity.
- **`semgrep-full`** — INFORMATIVNI. Ceo repo (bez `tests/migrations/
  data/vindex_scraper_output`), sve severity nivoe, `continue-on-error:
  true`, JSON izveštaj kao artifact — identičan obrazac kao
  `sast-full`/`bandit-full-report`.

### 1.3 Lokalno pokrenuto, stvaran nalaz, ispravljen (ne sakriven)

Semgrep instaliran lokalno (`pip install semgrep`, v. 1.171.0) i pokrenut
protiv `semgrep-core`-obima:

```
semgrep scan --config=p/security-audit --config=p/python --severity=ERROR \
  api.py main.py routers/ shared/ security/ services/ app/
```

**Pre ispravke: 1 nalaz** — `python.lang.security.use-defused-xml`,
`routers/sef.py:149`. Istraženo pre bilo kakve izmene: `_find()` helper
funkcija unutar `_validate_ubl_xml()` je u OBA svoja grananja
(`_use_lxml=True/False`) uvozila modul (`lxml.etree`/
`xml.etree.ElementTree`) koji se **nikad nije referencirao** u telu
funkcije — `doc.find(path, ns)` poziva metodu na objektu koji je VEĆ
bezbedno parsiran ranije u istoj funkciji (linija 121 lxml, ili linija
130-132 `defusedxml.ElementTree`, ovo drugo već ranije popravljeno u
Celina 5). **Nije bio stvaran XXE rizik** — mrtav, neiskorišćen import
koji je Semgrep-ovo pravilo ispravno prepoznalo kao "nebezbedan xml modul
uvezen", ali koji se nikad nije koristio za stvaran parse. Očišćen (oba
grananja svedena na `return doc.find(path, ns)`, mrtvi importi uklonjeni,
komentar objašnjava zašto). Testovi: `tests/test_sef.py` 17/17 i dalje
prolazi.

**Posle ispravke: 0 nalaza** u `semgrep-core` obimu → job je bezbedno
BLOKIRAJUĆI od prvog dana, neće odmah pocrveneti CI.

**Whole-repo (`semgrep-full`) sweep, informativno:** 31 nalaz (27
WARNING, 4 ERROR — sva 4 ERROR su van `semgrep-core` obima: 3 u
`routers/client_portal.py`, ostatak u `scripts/`/`security/` pomoćnim
fajlovima). Nisu triažirani pojedinačno u ovom sprintu (namerno —
`semgrep-full` je INFORMATIVNI po dizajnu, isti tretman kao postojećih
~35 Bandit MEDIUM nalaza), ali dostupni u CI artifact-u za buduću
triažu.

---

## 2. SEC-031-stil Production Readiness Verification Tooling

### 2.1 Korekcija premise — alat već postoji, LIVE testiran

Pre pisanja novog `scripts/verify_production_security.py` od nule,
pretraga repoa je otkrila **`scripts/audit_deployment_consistency.py`**
— već postojeći, generički alat koji radi TAČNO ono što zahtev traži:
parsira SVAKU `migrations/*.sql` datoteku za `CREATE TABLE`/`ALTER TABLE
... ADD COLUMN` naredbe, pa za svaku proverava da li stvarno postoji u
živoj Supabase bazi preko istog `shared/deps._get_supa()` klijenta koji
aplikacija koristi (PostgREST `PGRST205` = tabela ne postoji, `42703` =
kolona ne postoji).

**Odluka: iskorišćen postojeći alat, nije kreiran duplikat.** Zahtev
sam kaže "npr. `scripts/verify_production_security.py` **ili odgovarajući
alat**" — postojeći alat je taj "odgovarajući alat", generičkiji je
(pokriva svih 79 migracija, ne samo 085-088) i već je bio testiran u
produkciji (V. `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md`).

### 2.2 Verifikovano parsiranje migracija 085-088 (traženo eksplicitno)

```
085_aktivne_sesije.sql            -> tables: {'aktivne_sesije'}
086_portal_monitoring.sql         -> tables: {'praceni_predmeti', 'portal_status_log'}
087_pinecone_capacity_monitoring.sql -> tables: {'pinecone_capacity_snapshots'}
088_staging_memory.sql            -> tables: {'staging_memory'}
```

Sve 4 ispravno prepoznate, potvrđeno direktnim pozivom parsing funkcije.

### 2.3 STVARNO pokrenuto protiv žive baze — rezultat

`python scripts/audit_deployment_consistency.py` pokrenut protiv
konfigurisane Supabase baze (`.env` kredencijali dostupni u ovom
okruženju, read-only provere — `.select(...).limit(1)`, nula pisanja):

```
Ukupno migracija:     79
APPLIED:              66
NOT APPLIED:          3
UNVERIFIABLE:         10
```

**Ključni nalaz za ovaj sprint:** migracije **085, 086, 087 su POTVRĐENE
APPLIED** (nisu na "NOT APPLIED" listi — njihove tabele `aktivne_sesije`/
`praceni_predmeti`/`portal_status_log`/`pinecone_capacity_snapshots`
stvarno postoje u živoj bazi). Ovo potvrđuje ono što je već bilo
pretpostavljeno kad su ove migracije preimenovane (2026-07-26, Production
Readiness fix sprint): SQL sadržaj je već bio primenjen pod STARIM imenima
(`supabase_migrations/044,045` i `migrations/050_pinecone_...`) pre
preimenovanja — preimenovanje nije zahtevalo ponovno pokretanje, sada
DOKAZANO, ne samo pretpostavljeno.

**Migracija 088 (`staging_memory`) je POTVRĐENA NOT APPLIED** — očekivano
i tačno: kreirana je ove sesije (Institutional Memory V2), founder je
još nije ručno pokrenuo. V. §2.4 za dry-run/rollback pre pokretanja.

**2 dodatna nalaza, van obima ovog sprinta ali vredna pomena:**
`017_scraper_state.sql` (`discovered_bilteni` tabela) i
`058_briefing_saradnja_memory_webhooks.sql` (`vindex_memory` tabela) —
oba prijavljena kao NOT APPLIED. `058` je verovatno lažno pozitivan nalaz
alata: `075_remove_vindex_memory.sql` postoji u istom repou i po imenu
sugeriše da je `vindex_memory` NAMERNO uklonjena kasnijom migracijom —
alat trenutno ne zna da prepozna "tabela je namerno obrisana kasnije",
tretira odsustvo kao "nikad primenjeno". Nije ispravljano u ovom sprintu
(van eksplicitnog obima — 085-088), ali vredi founderu na znanje.

### 2.4 Dry-Run i Rollback postupak — migracija 088 (konkretan primer + opšti obrazac)

Ovo je genuinski NOVI deo ovog sprinta (alat iz §2.1 ne pokriva
dry-run/rollback planiranje, samo POST-FACTO proveru).

**Pre pokretanja u Supabase SQL Editor-u:**

1. **Analiza rizika naredbi** (`migrations/088_staging_memory.sql`):
   - `CREATE TABLE IF NOT EXISTS public.staging_memory (...)` — nova
     tabela, **nula uticaja na postojeće tabele** (nijedan `ALTER TABLE`
     na `predmeti`/`klijenti`/bilo šta postojeće — `predmet_id` je text
     kolona, meka referenca, NE foreign key ka `predmeti.id`). Bez
     zaključavanja postojećih tabela.
   - 2x `CREATE INDEX IF NOT EXISTS` na praznu, novu tabelu — trenutno.
   - `ALTER TABLE public.staging_memory ENABLE ROW LEVEL SECURITY` +
     2x `CREATE POLICY` — na novoj, praznoj tabeli — trenutno.
   - **Očekivano trajanje: < 1 sekunda.** Ovo NIJE ALTER na velikoj
     postojećoj tabeli (za razliku od SEC-031 slučaja u
     `SEC031_MIGRATION_DRY_RUN.md`, koji je opravdano imao detaljniju
     analizu zaključavanja) — dry-run analiza je ovde jednostavnija jer
     je migracija čisto aditivna.
2. **Rollback SQL** (ako nešto krene po zlu ili se odluka promeni):
   ```sql
   DROP TABLE IF EXISTS public.staging_memory;
   ```
   Bezbedno — nijedna druga tabela nema FK KA `staging_memory` (samo
   obrnuto, meko, preko `predmet_id`/`user_id` tekst polja), pa nema
   cascade rizika.
3. **Post-migracija smoke test** (ručno, u SQL Editor-u ili preko
   aplikacije):
   - `INSERT` jedan red kao test-korisnik → potvrdi da RLS politika
     `staging_memory_sopstveni` sprečava DRUGOG korisnika da ga vidi.
   - Pokreni `python scripts/audit_deployment_consistency.py` ponovo —
     `088_staging_memory.sql` mora preći sa "NOT APPLIED" na "APPLIED"
     liste.
   - Funkcionalni test: `POST /api/nacrt` sa `predmet_id` poljem → mora
     uspeti bez greške (pre migracije, insert u `staging_memory` bi
     tiho propao, logovano kao warning, ne bi srušio odgovor — v.
     `routers/drafting.py::_stage_draft_for_review`'s `try/except`).

**Opšti obrazac za BUDUĆE migracije (izvučen iz koraka 1-3 iznad):**
klasifikuj migraciju kao (a) čisto aditivna (nova tabela/kolona,
`IF NOT EXISTS` svuda) → nizak rizik, kratak dry-run kao gore, ILI
(b) menja postojeću veliku tabelu (`ALTER TABLE` na `predmeti`/
`klijenti`/etc.) → zahteva pun SEC-031-stil dry-run (zaključavanje,
test matrica, detaljan rollback plan) PRE pokretanja u produkciji.

---

## 3. Verifikacija

| Provera | Rezultat |
|---|---|
| YAML sintaksa `security.yml` posle izmene | ✓ Validna (Python `yaml.safe_load`), svih 6 job-ova prisutno |
| Semgrep lokalno pokrenut (core obim) | ✓ 1 nalaz → ispravljen → 0 nalaza |
| Semgrep lokalno pokrenut (full obim, informativno) | 31 nalaz (27 WARNING/4 ERROR van core obima), dostupno za buduću triažu |
| Gitleaks | Nije pokrenut lokalno (Go binarni alat, nije trivijalno instalirati u ovom Windows dev okruženju) — već proveren, radi u CI od Celina 5, konfiguracija nepromenjena ovim sprintom |
| `tests/test_sef.py` posle čišćenja mrtvog koda | ✓ 17/17 |
| `scripts/audit_deployment_consistency.py` | ✓ Pokrenut protiv žive baze, 085/086/087 potvrđene APPLIED, 088 potvrđena NOT APPLIED (očekivano) |
| Pun pytest suite | ✓ 2242 passed, 1 skipped (identično stanje pre sprinta — CI/tooling izmene, nula novih funkcionalnih testova) |

---

## Sažetak izmena

| Fajl | Izmena |
|---|---|
| `.github/workflows/security.yml` | Dodata `semgrep-core` (blokirajuće) + `semgrep-full` (informativno) job-ovi |
| `routers/sef.py` | Uklonjen mrtav `import xml.etree.ElementTree`/`lxml.etree` u `_find()` (jedini Semgrep core nalaz) |
| `docs/SECURITY_SPRINT_PHASE1.md` | Ovaj izveštaj |

**Nije kreirano** (namerna odluka, obrazložena gore): `.github/workflows/security_scan.yml`
(duplirao bi postojeći `security.yml`), `scripts/verify_production_security.py`
(duplirao bi postojeći `scripts/audit_deployment_consistency.py`).
