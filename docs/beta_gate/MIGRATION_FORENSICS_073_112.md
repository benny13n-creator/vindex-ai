# MIGRATION FORENSICS — 073 → 112 + korenski SQL fajlovi

**Datum:** 2026-08-13 · **Baseline:** `e811433d` · **Obim:** migracije 073–112 (40),
`migrations/smart_contract_analyses.sql`, `supabase_setup.sql`,
`supabase_migration.sql`, `supabase_migration_v3.sql` — **44 fajla ukupno**.

**Misija je čisto forenzička.** Nijedna migracija nije pokrenuta. Nijedan
`INSERT`/`UPDATE`/`DELETE`/`ALTER`/`CREATE`/`DROP`/`TRUNCATE` nije izvršen.
Nijedan produkcijski fajl, migracija ni test nije izmenjen.

---

## 1. Metod i šta on stvarno može da dokaže

Sonde su isključivo READ-ONLY:

| Sonda | Šta dokazuje |
|---|---|
| PostgREST OpenAPI (`GET /rest/v1/`) | **166 tabela** sa punom listom kolona |
| OpenAPI `description` polje | **PRIMARY KEY i FOREIGN KEY** po koloni |
| OpenAPI `required` niz | **NOT NULL bez DEFAULT-a** po koloni |
| RPC poziv sa namerno nevalidnim argumentom | funkcija **postoji** (abortira pri kastovanju argumenta, telo se nikad ne izvršava) |
| `GET /storage/v1/bucket` | **spisak storage bucket-a** |
| `select(count="exact").limit(0)` | broj redova — **nijedan red se ne čita** |

Negativna kontrola je prošla: izmišljena funkcija vraća `PGRST202`, pa
"funkcija nedostaje" nije artefakt pokvarene sonde.

> **Ispravka polazne pretpostavke.** Zadatak je predviđao da su constraint-i
> nevidljivi kroz PostgREST. To nije tačno za **PK, FK i NOT NULL** — OpenAPI
> ih izlaže. Time su stavke 5 i 7 unakrsne provere postale **dokazive**, a ne
> `UNKNOWN`.

**I dalje nevidljivo → `UNKNOWN`, nikad "ne postoji":** indeksi, trigeri, tela
funkcija, RLS politike, CHECK constraint-i, grantovi, enumi, komentari.

### Hijerarhija dokaza (zašto neke migracije dobijaju jaču ocenu)

Pravilo iz zadatka — *prisustvo šeme NIKAD nije dokaz izvršenja* — poštovano je
doslovno. `MIGRATION VERIFIED APPLIED` dodeljen je samo tamo gde dokaz **ne može**
da se objasni ručnim kreiranjem šeme:

- **Provenance pečat** koji imenuje samu migraciju (111).
- **Destruktivni efekat** nad objektom za koji je nezavisno dokazano da je postojao (075).
- **Interni scaffold migracije** — pomoćna funkcija koju niko ne pravi ručno (077).
- **Prethodni katalog-nivo zapis** (`pg_get_functiondef`, `has_function_privilege`)
  sačuvan u `docs/beta_gate/` — dokaz koji ja **ne mogu** samostalno da ponovim
  jer `SUPABASE_DB_URL` i dalje nije dostupan (102, 103, 107, 110).

---

## 2. Zbir po verdiktima

| Verdikt | Broj | Fajlovi |
|---|---|---|
| `MIGRATION VERIFIED APPLIED` (sopstvena sonda) | **3** | 075, 077, 111 |
| `MIGRATION VERIFIED APPLIED` (raniji katalog zapis) | **4** | 102, 103, 107, 110 |
| `MIGRATION VERIFIED NOT APPLIED` | **1** | 109 |
| `PARTIAL EXECUTION / SCHEMA DRIFT` | **1** | `supabase_migration.sql` |
| `SCHEMA VERIFIED PRESENT — MIGRATION EXECUTION UNVERIFIABLE` | **28** | 073, 074, 076, 079, 080, 082, 083, 085, 086, 087, 088, 089, 090, 091, 092, 093, 094, 095, 096, 098, 099, 101, 105, 108, 112, `smart_contract_analyses.sql`, `supabase_setup.sql`, `supabase_migration_v3.sql` |
| `UNKNOWN` (nijedan artefakt vidljiv kroz PostgREST) | **7** | 078, 081, 084, 097, 100, 104, 106 |
| **Ukupno** | **44** | |

Deklarisano u obimu: **46 tabela, 45 dodatih kolona, 2 view-a, 19 funkcija,
5 trigera, 71 indeks, 82 politike.**

**Nijedna tabela, kolona, funkcija ni view iz migracija 073–112 ne nedostaje u
produkciji.** Jedini nedostajući objekti u celom obimu potiču iz
`supabase_migration.sql`.

---

## 3. `NOT APPLIED` i `PARTIAL` — tačni objekti koji nedostaju

### 3.1 `supabase_migration.sql` — `PARTIAL EXECUTION / SCHEMA DRIFT` (dokazano)

Ovo je **najveći nalaz revizije** i nije bio na listi poznatih rupa.

Fajl je jedini u celom repou koji definiše četiri tabele. Produkcija ih ima
tačno do jedne tačke preseka, i to u redosledu pisanja u fajlu:

| Linija | Objekat | Produkcija |
|---|---|---|
| 5 | `profiles` | postoji |
| 45 | `feedback` | postoji |
| 93 | `conversations` | **postoji** |
| 115 | `reported_errors` | **NEDOSTAJE** |
| 167 | `ratio_decidendi` | **NEDOSTAJE** |
| 199 | `api_costs` | **NEDOSTAJE** |

`conversations` je kreiran **isključivo** ovim fajlom i postoji → skripta je
izvršena bar do linije 114. `reported_errors` je kreiran **isključivo** ovim
fajlom i ne postoji → skripta je stala na liniji 115. Monotoni prefiks
(sve pre → postoji, sve posle → ne postoji) isključuje slučajnost.

**Živa posledica — dva plaćena sistema tiho ne rade:**

- `shared/cost.py:97` upisuje u `api_costs` unutar `try/except Exception`
  koji samo loguje `"[COST] DB log neuspešan — ne blokira odgovor"`.
  → **Praćenje troška svakog AI poziva je mrtvo od početka.** Nema podatka o
  potrošnji po korisniku/endpointu, a niko to ne vidi jer izuzetak je progutan.
- `routers/praksa.py:311,330` čita i upisuje `ratio_decidendi` keš.
  → Keš **uvek** promašuje i upis **uvek** pada. Svaki *ratio decidendi* se
  ponovo generiše LLM-om pri svakom pozivu — **plaćeni poziv koji je trebalo
  da bude keširan**, plus stalan šum u Sentry (`_sentry_capture`).
- `reported_errors` — nijedna živa referenca u kodu. P3.

### 3.2 Migracija 109 — `MIGRATION VERIFIED NOT APPLIED`

`docs/beta_gate/MIGRATION_110_VERIFICATION.md` i docstring
`scripts/migration_drift_check.py` beleže da je 109 abortirao na
`relation "public.discovered_bilteni" does not exist`. Zamenjen je migracijom
110 (idempotentna verzija), koja **jeste** primenjena i katalog-verifikovana.

Napomena: `discovered_bilteni` **danas postoji** u produkciji, pa je uzrok
aborta u međuvremenu otklonjen. Sadržajno stanje je pokriveno kroz 110 — 109
ne treba ponovo pokretati.

---

## 4. UNAKRSNA PROVERA SA RANIJIM NALAZIMA (7 stavki)

### 1. Migracija 089 — AI provenance
**`MIGRACIJA POSTOJI, IZVRŠENJE NEDOKAZIVO`**

Razdvojeno kako je traženo:

- **Šema (dokazano):** svih **19** kolona koje 089 dodaje postoje. `ai_forensics`
  ima ukupno **38 kolona** (19 legacy iz 043 + 19 iz 089).
- **Podaci (dokazano):** 124/124 reda imaju popunjen `correlation_id` **i**
  `module_name` — kolone koje postoje tek posle 089. Dakle kolone nisu samo
  prisutne, nego se i **aktivno pišu**.
- **Izvršenje migracije (NEDOKAZIVO):** 089 pored kolona pravi i trigger
  `trg_protect_ai_forensics_update` (append-only zaštita, blokira `UPDATE`) i
  **4 indeksa**. PostgREST ne vidi ni trigere ni indekse. Da li je
  append-only garancija stvarno na snazi — **UNKNOWN**.

> Raniji sprint je tvrdio "vlasnik je ručno izvršio 089, 19+10 kolona postoji".
> Broj kolona se potvrđuje (19 iz 089), ali **"kolone postoje" ne dokazuje da
> trigger postoji**. Append-only tvrdnja o `ai_forensics` je i dalje nedokazana.

### 2. `content_sha256` (migracija 095)
**`MIGRACIJA POSTOJI, IZVRŠENJE NEDOKAZIVO` — ali NULL vrednosti su OČEKIVANE, ne kvar**

Pregled izvornog koda 095 rešava pitanje definitivno: migracija radi
**samo `ADD COLUMN`** —

```sql
ALTER TABLE public.predmet_dokumenti ADD COLUMN IF NOT EXISTS content_sha256 TEXT;
CREATE INDEX IF NOT EXISTS idx_predmet_dokumenti_content_sha256 ...;
```

**Nema nikakvog backfill-a.** Jedini `UPDATE` u celom fajlu je
`UPDATE public.intake_jobs SET assimilation_complete = true WHERE predmet_id IS NOT NULL`
— druga kolona, druga tabela.

Sonda: `predmet_dokumenti` = **43 reda, 0 sa `content_sha256`**.

To je **tačno ono što migracija propisuje** ("Populated for every document
assimilated from this sprint forward"). 43 postojeća dokumenta su legacy i
migracija ih namerno ne dira. Dakle 0/43 NULL **nije dokaz da 095 nije
primenjena** — raniji nalaz je pogrešno protumačen kao kvar.

Realna posledica ostaje: dedup po sadržaju je **slep za 43 legacy dokumenta**.
Backfill skripta je već napisana ali **nije migracija i nije pokrenuta**:
`docs/beta_gate/PINE_02_BACKFILL_content_sha256.sql`.

### 3. Storage bucket-i
**`MIGRACIJA NE POSTOJI — funkcionalnost nikad nije ni bila napisana`** (za `portal-uploads` i `klijent-dokumenti`)

U **celom repou postoji tačno jedan** dodir `storage.buckets`:
`migrations/073_intake_foundations.sql:362`, koji pravi `intake-dokumenti`.

Produkcija (`GET /storage/v1/bucket`) — **samo dva bucket-a**:

| Bucket | Migracija koja ga pravi | Produkcija | Kod koji ga koristi |
|---|---|---|---|
| `intake-dokumenti` | **073** | postoji (`public=false`) | `routers/smart_intake.py:59`, `shared/intake_worker.py:480` |
| `portal-uploads` | **nijedna** | postoji (`public=false`) | `routers/client_portal.py:591,702,779` |
| `klijent-dokumenti` | **nijedna** | **NE POSTOJI** | `klijenti/router.py:812` (upload), `:965` (download) |

- `portal-uploads` postoji **iako ga nijedna migracija ne pravi** → kreiran
  ručno kroz Dashboard. Radi, ali nije reproducibilan: čista baza iz `migrations/`
  ga neće imati.
- `klijent-dokumenti` **ne postoji nigde** — ni u migracijama ni u produkciji —
  a Trezor kod ga bezuslovno koristi.

### 4. RLS nad storage
**`MIGRACIJA NE POSTOJI — funkcionalnost nikad nije ni bila napisana`**

- `CREATE POLICY` u repou: **250**
- `CREATE POLICY ... ON storage.*`: **0**
- Reference na `storage.objects` u celom repou: **0**

Nijedna migracija nikada nije ni pokušala da postavi RLS nad storage-om.
Oba bucket-a su `public=false`, pa objekti nisu anonimno čitljivi preko javnog
URL-a — ali **razdvajanje po korisniku unutar bucket-a ne postoji na nivou
baze**. Jedina kontrola je aplikativna logika (`storage_key` se izvodi iz
`user_id`) i činjenica da se koristi service-role ključ. Stanje politika koje
je možda ručno postavljeno kroz Dashboard: **UNKNOWN**.

### 5. `zadaci.predmet_id` FK
**`MIGRACIJA NE POSTOJI — funkcionalnost nikad nije ni bila napisana`** — raniji nalaz **POTVRĐEN**

- `migrations/045_firm_intelligence.sql:114` glasi doslovno `predmet_id UUID,` —
  bez `REFERENCES`.
- Nijedna druga migracija ne dodaje taj FK (jedino `idx_zadaci_predmet`, **indeks**, linija 146).
- **Produkcija to potvrđuje:** `zadaci.kancelarija_id` **ima** FK
  (`-> kancelarije.id`), a `zadaci.predmet_id` ga **nema**.

Pozitivna kontrola u istoj tabeli je ključna: PostgREST **prijavljuje** FK-ove
za `zadaci`, pa je odsustvo na `predmet_id` **dokaz odsustva**, a ne slepa mrlja.

Posledica: brisanje predmeta ostavlja `zadaci` redove koji pokazuju na
nepostojeći predmet — tihi orphan, bez zaštite baze.

### 6. `predmet_dokumenti.session_id`
**`MIGRACIJA NE POSTOJI — funkcionalnost nikad nije ni bila napisana`**

`predmet_dokumenti` ima **18 kolona**; `session_id` **nije** među njima. Nijedna
migracija je nikad ne dodaje.

**Bitna ispravka ranijeg nalaza.** Raniji sprint je tvrdio da insert "baca
42703". Prvi insert zaista pada, ali `routers/intake.py:317–326` ima
**fallback**:

```python
try:
    ... .insert({**r, "session_id": sid}).execute()   # 42703, uvek pada
except Exception:
    ... .insert(r).execute()                          # prolazi, bez session_id
```

Dakle red **jeste** kreiran i korisnik ne vidi grešku. Posledica nije gubitak
dokumenta nego **tihi gubitak veze session → dokument** na svakom prolazu, uz
jedan bespotreban neuspeli DB round-trip po dokumentu. Kolona `session_id` je
mrtvo slovo u kodu koje nikad nije stiglo do šeme.

### 7. `ai_forensics.user_id NOT NULL`
**`MIGRACIJA POSTOJI I DOKAZANO PRIMENJENA`** — ali krivac **nije** 089

- **Ko je to postavio:** `migrations/043_security_bulletproof.sql:82` —
  `user_id UUID NOT NULL` u originalnom `CREATE TABLE`.
- **Dokaz da važi i danas:** OpenAPI `required` za `ai_forensics` = `['id', 'user_id']`.
  PostgREST u `required` stavlja isključivo `NOT NULL` kolone bez DEFAULT-a →
  **NOT NULL je potvrđen u produkciji**.
- **089 to nikad ne dira** — dodaje 19 nullable kolona i ne relaksira `user_id`.

**Da li je namerno?** U kontekstu 043 — **da**. Tabela je tada bila
per-user security audit sa RLS politikom `ai_forensics_owner_read` vezanom za
`user_id`; `NOT NULL` je bio deo tog dizajna.

**Ali:** 089 (Mission Atlas) je tabelu prenamenio u opšti AI-provenance ledger
koji pokriva i pozadinske/sistemske operacije **bez korisnika** — i pritom
`NOT NULL` nije revidiran. Dakle ograničenje je *nasleđeno*, ne *odlučeno*:
**nenamerna posledica proširenja obima u 089**, a ne svesna odluka. Zato
pozadinski poslovi gube provenance.

---

## 5. Prioriteti

### P0 — bezbednost

**P0-1 · `_sec031_fix_fk` je i dalje živ i izložen preko PostgREST-a.**
Migracija 077 pravi pomoćnu funkciju koja izvršava proizvoljan DDL preko
`EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', ...)`. `DROP FUNCTION` na
kraju fajla je **zakomentarisan**, pa funkcija nikad nije uklonjena.

Sonda je potvrđuje: `/rpc/_sec031_fix_fk` je u OpenAPI spisku, a poziv vraća
`42P01` (kast u `regclass` pao) — dakle **funkcija postoji i razrešava se**.

- Nema `REVOKE`/`GRANT` u 077 → važi Postgres default: **`EXECUTE` za `PUBLIC`**.
- **Ublažavajuće:** funkcija **nije** `SECURITY DEFINER` (`$BODY$ LANGUAGE plpgsql;`,
  linija 142), pa se izvršava sa privilegijama pozivaoca — `authenticated`
  korisnik ne može stvarno da izvrši `ALTER TABLE` nad tuđim tabelama.
- **Preostali rizik:** funkcija čita `pg_attribute`/`pg_constraint` pre DDL-a,
  pa je upotrebljiva kao **oracle za postojanje tabela i kolona** (poruke greške
  razlikuju "kolona ne postoji" od "FK nije pronađen"). Nepotreban DDL primitiv
  izložen anonimnom/prijavljenom sloju.

Stvarna eksploatabilnost: **NISKA**. Higijena: **treba ukloniti**.

### P1 — GDPR / audit / naplata

| # | Nalaz | Posledica |
|---|---|---|
| P1-1 | `api_costs` ne postoji (§3.1) | praćenje troška AI poziva **potpuno mrtvo**, izuzetak progutan |
| P1-2 | `ratio_decidendi` ne postoji (§3.1) | keš presuda uvek promašuje → **ponovljeni plaćeni LLM pozivi** + Sentry šum |
| P1-3 | `ai_forensics.user_id NOT NULL` (§4.7) | pozadinski poslovi **ne mogu da upišu provenance** → rupa u AI audit tragu |
| P1-4 | `trg_protect_ai_forensics_update` nedokaziv (§4.1) | append-only garancija nad AI audit logom je **tvrdnja, ne dokaz** |
| P1-5 | `klijent-dokumenti` bucket ne postoji (§4.3) | Trezor upload (`klijenti/router.py:812`) i download (`:965`) **padaju u produkciji** |
| P1-6 | 0 RLS politika nad storage-om (§4.4) | izolacija dokumenata po korisniku **nije zagarantovana bazom** |
| P1-7 | `portal-uploads` nije ni u jednoj migraciji (§4.3) | okruženje **nije reproducibilno** iz `migrations/` |

### P2 — funkcionalnost

| # | Nalaz | Posledica |
|---|---|---|
| P2-1 | `zadaci.predmet_id` bez FK (§4.5) | orphan zadaci posle brisanja predmeta |
| P2-2 | `predmet_dokumenti.session_id` ne postoji (§4.6) | tihi gubitak session→dokument veze + suvišan neuspeli insert |
| P2-3 | `content_sha256` NULL na 43/43 (§4.2) | dedup slep za legacy dokumente; backfill napisan, nepokrenut |

### P3 — kozmetika

- `reported_errors` ne postoji — nijedna živa referenca u kodu.
- `feedback` u produkciji nema `q_hash` iz `supabase_setup.sql` — bezopasan drift.

---

## 6. Rizik ponovnog pokretanja

| Klasa | Fajlovi | Obrazloženje |
|---|---|---|
| `SAFE_TO_RERUN` | 073, 074, 076, 079, 080, 081, 082, 084, 085*, 086*, 087*, 088*, 090, 091, 092, 093, 094, 096, 098*, 099*, 101, 102, 103, 104, 105, 106, 108, 110, 112, `smart_contract_analyses.sql`, `supabase_setup.sql`, `supabase_migration_v3.sql` | `IF NOT EXISTS` / `CREATE OR REPLACE` / `DROP POLICY IF EXISTS` pre `CREATE POLICY` / idempotentni `DO` blokovi |
| `CONDITIONALLY_SAFE` | 077, 083, 089, 095, 097, 100, 107, 109, `supabase_migration.sql` | vidi ispod |
| `UNSAFE_TO_RERUN` | **075**, **111** | vidi ispod |

\* `085, 086, 087, 088, 098, 099` koriste goli `CREATE POLICY` **bez**
`DROP POLICY IF EXISTS` — ponovno pokretanje puca na `42710 duplicate_object`.
Nije destruktivno (transakcija se prekida), ali **skripta neće proći do kraja**.
Isto važi za 082.

**`UNSAFE_TO_RERUN`:**

- **075** — `DELETE FROM feature_registry WHERE feature_key='vindex_memory'`
  + `DROP TABLE IF EXISTS public.vindex_memory`. Danas je no-op, ali ako se
  `vindex_memory` ikad vrati kao živa funkcija, ponovno pokretanje je **tiho briše**.
- **111** — četiri `UPDATE`-a nad `feature_registry` koji gaze `krediti`,
  `chargeable`, `ai_model`, `minimum_plan`, `cooldown_seconds`. Ponovno
  pokretanje **poništava svaku kasniju ručnu izmenu cena** za `confidence_audit`,
  `conflict_check`, `da_wallet_risk_assessment`. Direktan uticaj na naplatu.

**`CONDITIONALLY_SAFE` — obrazloženja:**

- **077** — pomoćna funkcija je `CREATE OR REPLACE` (bezbedno), ali
  `_sec031_fix_fk` radi `DROP CONSTRAINT` + `ADD ... NOT VALID` + `VALIDATE`.
  Ponovno pokretanje **kratko ostavlja FK nevalidiranim** i puca (`RAISE EXCEPTION`)
  ako ijedna od 18 tabela/kolona ne postoji — prekid usred bloka ostavlja
  **deo FK-ova promenjen, deo ne**.
- **083** — goli `INSERT INTO feature_registry` bez `ON CONFLICT` →
  `23505 unique_violation` pri ponovnom pokretanju (red već postoji, potvrđeno sondom).
- **089** — sve `ADD COLUMN IF NOT EXISTS` + `CREATE OR REPLACE FUNCTION` +
  `DROP TRIGGER IF EXISTS` pre `CREATE TRIGGER`: **idempotentno**. Uslovno samo
  zato što `CREATE TRIGGER` nakratko skida append-only zaštitu između `DROP` i `CREATE`.
- **095** — `UPDATE intake_jobs SET assimilation_complete = true WHERE predmet_id IS NOT NULL`
  ponovo bi označio kao završene poslove koje je neko u međuvremenu vratio na `false`.
- **097 / 100** — `DROP CONSTRAINT` + `ADD CONSTRAINT`: puca ako ijedan
  postojeći red krši novi `CHECK`.
- **107** — `CREATE OR REPLACE` nad tri kreditne RPC funkcije. Bezbedno po sebi,
  ali vraća tela na verziju iz 107 i poništava svaku kasniju ispravku.
- **109** — dokazano abortira; **ne pokretati**, koristiti 110.
- **`supabase_migration.sql`** — sadrži
  `UPDATE public.profiles SET is_pro = TRUE WHERE email IN (...)` (3 hardkodovana
  naloga, linija 141) i `ALTER TABLE public.klijenti DROP COLUMN IF EXISTS jmbg_mb`.
  Ponovno pokretanje bi **vratilo PRO status** trima nalozima bez obzira na
  trenutnu pretplatu. Nedostajuće tabele treba izvući u **novu** migraciju,
  ne ponovo pokretati ovaj fajl.

---

## 7. Šta je ostalo `UNKNOWN` i zašto

`SUPABASE_DB_URL` i dalje nije dostupan (isti nedostatak zabeležen još od
Black Swan-a). Bez direktne veze na Postgres katalog trajno je nedokazivo:

- **71 indeks** i **5 trigera** deklarisanih u obimu — uključujući
  `trg_protect_ai_forensics_update` (append-only AI audit) i sve `UNIQUE`
  indekse koji nose invarijante (104 `fakture`, 106 `predmet_dokumenti`,
  084 `timer_sessions`, 094 `uq_predmet_dokumenti_source_segment`).
- **82 RLS politike** i svi `GRANT`/`REVOKE` iz 078, 102, 103, 109, 110.
- **Tela funkcija** — 107 i 108 su `CREATE OR REPLACE`; prisustvo funkcije ne
  govori koja je verzija tela živa. (Za 107 i 110 to je zatvoreno *ranijim*
  katalog zapisom u `docs/beta_gate/`, ne ovom revizijom.)
- **CHECK constraint-i** iz 093, 097, 100.
- **Stvarne storage RLS politike** postavljene ručno kroz Dashboard, ako ih ima.

Jedan `psql` pristup pretvorio bi svih 7 `UNKNOWN` migracija i 28
`SCHEMA VERIFIED PRESENT` u definitivan verdikt.

---

## 8. Preporučeni redosled (nijedna akcija nije izvršena)

1. **P1-1/P1-2** — nova migracija koja pravi `api_costs`, `ratio_decidendi`,
   `reported_errors`. Najveći odnos koristi i rizika: dve žive, plaćene
   funkcionalnosti trenutno tiho ne rade.
2. **P1-5** — kreirati `klijent-dokumenti` bucket (i uvesti `portal-uploads` u
   migraciju radi reproducibilnosti).
3. **P0-1** — `DROP FUNCTION IF EXISTS _sec031_fix_fk(regclass, text, text);`
4. **P1-3** — relaksirati `ai_forensics.user_id` na nullable uz sentinel za
   sistemske operacije (zahteva reviziju `ai_forensics_owner_read` politike).
5. **P2-1/P2-2** — FK `zadaci.predmet_id → predmeti.id`; odlučiti da li
   `session_id` dodati u šemu ili ukloniti iz `routers/intake.py`.
6. **Nabaviti `SUPABASE_DB_URL`** i zatvoriti sekciju 7.

---

*Sve tvrdnje u ovom dokumentu su ili (a) citat izvornog koda sa brojem linije,
ili (b) rezultat READ-ONLY sonde nad produkcijom. Tamo gde ni jedno ni drugo
nije bilo moguće, stoji `UNKNOWN` — nikad "ne postoji".*
