# BETA-INFRA-MIGRATION-FORENSICS-001 — FINAL MATRIX & ACTION QUEUE

**Baseline `e811433d`. Nijedna migracija nije pokrenuta. Nijedan
INSERT/UPDATE/DELETE/ALTER/CREATE/DROP/TRUNCATE. Nijedan produkcijski fajl
menjan.** Sve je čitanje fajlova, statička analiza i read-only sonde.

---

# ISPRAVKA PREMISE ZADATKA

Repo **nema 112 migracija**.

```
.sql u migrations/:        103   (102 numerisana + smart_contract_analyses.sql)
raspon brojeva:            2..112
rupe:                      9     (27–35) — ti brojevi ne postoje
duplikati:                 0
.sql VAN migrations/:      3     supabase_setup.sql, supabase_migration.sql,
                                 supabase_migration_v3.sql
```

**112 je najveći broj, ne broj migracija.** Tri korenska fajla nikad nisu bila
ni u jednom inventaru — i baš u jednom od njih je najveći nalaz ovog sprinta.

---

# FAZA 2 — MIGRATION HISTORY

## `PUBLIC MIGRATION HISTORY = ABSENT`

Sedam kandidata u `public` (`schema_migrations`, `supabase_migrations`,
`migrations`, `_migrations`, `migration_history`, `vindex_migrations`,
`applied_migrations`) — **svih sedam 404**.

Nema `supabase/` direktorijuma, nema `config.toml`, i **nijedan** Procfile,
Dockerfile ni CI workflow ne pokreće migracije.

## Ograda koju ne prećutkujem

Ne-public šeme (`supabase_migrations`, `storage`, `auth`, `realtime`) PostgREST
odbija sa **`406 Invalid schema`**. To **nije dokaz da ne postoje** — to je
granica metode. Za njih: **UNKNOWN**, razrešivo jednim upitom u SQL Editoru.

## Jedini nefalsifikovan dokaz izvršenja u celom repou

**Migracija 111** je jedina koja ostavlja provenance pečat:
`updated_by = 'migration_111_phantom_ai_charges'` na sva 3 reda. Nijedna druga
migracija ne ostavlja trag koji se ne bi mogao proizvesti i ručno.

---

# FAZA 11 — ZBIR

```
UKUPNO ARTEFAKATA              106   (103 u migrations/ + 3 korenska)
MIGRATION VERIFIED APPLIED      17   10 (opseg 002–072) + 7 (073–112)
MIGRATION VERIFIED NOT APPLIED   2   023, 109
PARTIAL EXECUTION / DRIFT        1   supabase_migration.sql
SCHEMA PRESENT / EXEC UNVERIF.  79   51 + 28
UNKNOWN                          7   078, 081, 084, 097, 100, 104, 106
```

**79 od 106 je „šema postoji, izvršenje nedokazivo".** To nije neuspeh
forenzike nego tačan opis sistema bez migration history-ja: kad ledger ne
postoji, prisustvo tabele ne razlikuje „migracija je pokrenuta" od „neko je
ručno dodao kolonu".

17 je dobilo `VERIFIED APPLIED` jer za njih postoji **dokaz na nivou podataka**,
ne šeme — npr. 064: broj redova 70 se rekonciliše tačno kao 69 + 1(066) +
1(083) − 1(075); 068: sve tri cene 29/79/249; 069: multiplikatori 6/3/2.

---

# NAJVEĆI NALAZ — NIJE BIO NI NA ČIJOJ LISTI

## `supabase_migration.sql` je stao na liniji 115

Nije numerisan, pa nikad nije ni ušao u inventar. Jedini je definitor četiri
tabele, a produkcija ih ima **po monotonom prefiksu** — sve pre linije 115
postoji, sve posle nedostaje:

| Linija | Tabela | Stanje |
|---|---|---|
| 93 | `conversations` | **POSTOJI** |
| 115 | `reported_errors` | **NE POSTOJI** |
| 167 | `ratio_decidendi` | **NE POSTOJI** |
| 199 | `api_costs` | **NE POSTOJI** |

Verifikovano nezavisno, dva puta.

## Dve žive posledice koje objašnjavaju ranije probleme

- **`shared/cost.py:97`** upisuje u `api_costs` i guta izuzetak →
  **praćenje troška AI poziva je mrtvo od početka.** Komentar u istom fajlu
  kaže *„api_costs will misreport actual spend"* — a tabela ne postoji uopšte.
- **`routers/praksa.py:311,330`** čita i upisuje `ratio_decidendi` → **keš
  uvek promašuje, svaki ratio decidendi se ponovo plaća LLM-u.**

---

# DRUGI NALAZ ISTE TEŽINE — `public.rokovi` NE POSTOJI

`023_stability_500_users.sql` je `MIGRATION VERIFIED NOT APPLIED`: **4 od 5
indeksa gađaju objekte koji dokazano ne postoje.**

```
email_notif_log.tip         42703  NE POSTOJI   (stvarna kolona: poslato_at)
email_notif_log.created_at  42703  NE POSTOJI
predmeti.obrisan            42703  NE POSTOJI   (nema NIJEDNU soft-delete kolonu)
public.rokovi              PGRST205 TABELA NE POSTOJI
klijenti.obrisan            42703  NE POSTOJI   (ima deleted_at)
```

Migracija je pisana prema šemi koja se nikad nije poklopila sa onom koju je
021 stvarno kreirala.

## Kolateral je veći od same migracije

**`public.rokovi` ne postoji, a 13 poziva u 9 produkcijskih fajlova je gađa** —
`api.py`, `dashboard.py`, `morning_briefing.py`, `case_commander.py`,
`decision_replay.py`, `integrations.py`, `whatsapp_notif.py`, `zadaci.py`,
`zastarelost.py`. **Nijedna migracija u repou je ne kreira.** Ni
`predmet_rokovi` ne postoji.

Provereno: većina poziva nije u `try` bloku. Rokovi su za advokata
egzistencijalna funkcija — ovo je P1 najmanje, i objašnjava zašto se ranije
nije mogao naći „izvor istine" za rokove.

---

# FAZA 7 — UNAKRSNA PROVERA (7 stavki)

| # | Stavka | Nalaz |
|---|---|---|
| 1 | **089 AI provenance** | `MIGRACIJA POSTOJI, IZVRŠENJE NEDOKAZIVO`. 19 kolona postoji i 124 mesta ih piše — ali trigger `trg_protect_ai_forensics_update` i 4 indeksa su **nevidljivi kroz PostgREST**. **Append-only je tvrdnja, ne dokaz.** |
| 2 | **`content_sha256`** | 095 radi **samo `ADD COLUMN`, bez backfill-a**. **0/43 NULL je očekivano ponašanje, ne kvar** — v. ispravku dole |
| 3 | **Storage bucket-i** | `MIGRACIJA NE POSTOJI`. `portal-uploads` postoji a nijedna ga migracija ne pravi; `klijent-dokumenti` ne postoji nigde, a `klijenti/router.py:812,965` ga bezuslovno koristi |
| 4 | **RLS nad storage** | `MIGRACIJA NE POSTOJI`. 250 `CREATE POLICY`, **0** nad storage |
| 5 | **`zadaci.predmet_id` FK** | `MIGRACIJA NE POSTOJI` — **dokaz odsustva, ne odsustvo dokaza**: `zadaci.kancelarija_id` **ima** FK u istoj tabeli. Pozitivna kontrola |
| 6 | **`predmet_dokumenti.session_id`** | `MIGRACIJA NE POSTOJI`. **Ispravka ranijeg nalaza**: `intake.py:317-326` ima fallback insert, pa red **jeste** kreiran → posledica je **tihi gubitak provenance**, ne pad |
| 7 | **`ai_forensics.user_id NOT NULL`** | `DOKAZANO PRIMENJENA`, ali krivac je **043:82, ne 089**. Namerno u dizajnu 043 (per-user audit); **089 je tabelu prenamenio u opšti ledger za sistemske operacije i nije revidirao ograničenje** → nenamerna posledica |

## Dve ispravke ranijih izveštaja, uključujući moj

**`content_sha256` prazan na 43/43 NIJE kvar.** U PINE-02 sam to vodio kao rupu
koja traži backfill. Migracija 095 po dizajnu radi samo `ADD COLUMN`. Kolona je
prazna zato što je ništa nikad nije popunilo — tačno kako je napisana. Backfill
i dalje ima smisla, ali kao **novi korak**, ne kao popravka nečega što je
zakazalo.

**`session_id` ne obara insert.** Raniji nalaz je tvrdio pad sa 42703; postoji
fallback grana, pa je posledica tiši i gori oblik — red bez veze ka sesiji.

---

# FAZA 9 — P0

| # | Nalaz | Migracija |
|---|---|---|
| **P0-1** | **064 rerun VRAĆA P0 rupu koju je 110 zatvorio.** 064 kreira `feature_usage_self` `FOR ALL` — politiku koju je 110 obrisao jer je korisnik mogao da obriše svoje `feature_usage` redove i **resetuje sopstvenu kvotu i naplatu** | 064 |
| **P0-2** | `case_benchmarks` i `zakoni_monitoring` kreirani **bez ijednog `ENABLE ROW LEVEL SECURITY`** | 045 |
| **P0-3** | Politika **bez `TO` klauzule → važi za PUBLIC**, sa `USING(true) WITH CHECK(true)`. 110 ima petlju koja to ispravlja, ali je **preskače** uz komentar „does not exist in this database today" — a sonda pokazuje da **tabela `discovered_bilteni` DANAS POSTOJI**. Sekundarno: baca sumnju da li je 110 uopšte primenjen | 017 |
| **P0-4** | 043 rerun: `DROP TRIGGER` + `CREATE TRIGGER` uz 2 neograđene politike; prekid u autocommit-u ostavlja `audit_immutable` (**15.760 redova**) bez zaštite od `UPDATE/DELETE` | 043 |
| **P0-5** | `_sec031_fix_fk` (DDL preko `EXECUTE format`) i dalje živ na `/rpc/`; `DROP FUNCTION` u 077 je **zakomentarisan**, nema `REVOKE`. Ublažavajuće: **nije `SECURITY DEFINER`**, pa je eksploatabilnost niska — ostaje kao schema-existence oracle | 077 |

# FAZA 9 — P1 (izbor)

- **061**: `UPDATE profiles SET onboarding_done = TRUE;` — **jedini `UPDATE` bez `WHERE`** u celom opsegu
- **063**: rerun **ponovo dodeljuje i produžava 30-dnevni Legacy Professional** svakom `is_pro` nalogu
- **065 / 069 / 070**: 68 + 3 + 4 slepa `UPDATE`-a nad `feature_registry`.
  `feature_registry_audit` **već ima 2 reda**, `tier_config_audit` **2 reda** →
  Admin Console **jeste korišćen**, pa bi rerun prebrisao stvarne izmene cena
- **`api_costs` / `ratio_decidendi`** — v. gore
- **056**: ToS/AI-consent zabeležen za **2 od 12** naloga
- **008 / 058**: SEF `api_key` i Google OAuth tokeni u **plaintextu**

---

# FAZA 12 — ACTION QUEUE

## QUEUE A — SAFE TO APPLY (dokazano nedostaje, bezbedno)

**PRAZAN.** Nijedna migracija ne ispunjava oba uslova.

Dve su `VERIFIED NOT APPLIED`, i nijedna nije bezbedna za pokretanje kakva jeste:
- **023** — 4 od 5 indeksa gađa nepostojeće objekte; pokretanje **puca**.
  Popravlja se prepisivanjem prema stvarnoj šemi, ne pokretanjem.
- **109** — v. nalaz drugog tima; ne pokretati bez razrešenja 110.

## QUEUE B — DO NOT APPLY YET

- **Svih 79** sa `SCHEMA PRESENT / EXECUTION UNVERIFIABLE` — šema već postoji;
  rerun nosi rizik duplog DML-a bez ijedne dobiti.
- **23 `UNSAFE_TO_RERUN`** iz opsega 002–072, plus **075 i 111**.
- **6 migracija sa golim `CREATE POLICY` bez `DROP IF EXISTS`** — pucaju na
  `42710`.
- **064, 063, 065, 069, 070, 047, 058, 061** — rerun **aktivno kvari** živo
  stanje (P0-1 vraća rupu; 061 gazi ceo `profiles`).

## QUEUE C — CRITICAL REVIEW (odsustvo objašnjava postojeći problem)

1. **`supabase_migration.sql` L115+** → `api_costs`, `ratio_decidendi`,
   `reported_errors`. Objašnjava mrtvo praćenje troška i ponovno plaćanje ratio
   decidendi.
2. **`public.rokovi`** → 13 poziva u 9 fajlova gađa nepostojeću tabelu.
3. **017 + 110 neslaganje** → politika za PUBLIC `USING(true)` nad tabelom koja
   danas postoji, a 110 ju je preskočio. **Baca sumnju na to da li je 110
   uopšte primenjen** — a 110 je nosio P0 ispravke.
4. **089 trigger i indeksi** → append-only garancija provenance-a je nedokazana.
5. **Storage: 0 RLS politika, `klijent-dokumenti` bucket ne postoji** →
  „Dokumentacioni trezor" ne može raditi.

---

# ODGOVORI NA 8 PITANJA

| | | |
|---|---|---|
| 1 | Dokazano primenjeno | **17 od 106** |
| 2 | Dokazano NIJE primenjeno | **2** (023, 109) + 1 delimično (`supabase_migration.sql`) |
| 3 | Samo schema-match bez dokaza izvršenja | **79** |
| 4 | Drift / delimično | **1** |
| 5 | P0/P1 među missing | P0: 5 · P1: 15 |
| 6 | Bezbedno pokrenuti | **NIJEDNA** — Queue A je prazan |
| 7 | Ne smeju bez dodatnog dokaza | **89** (79 unverifiable + 23 unsafe, sa preklapanjem) |
| 8 | Objašnjavaju ranije probleme | **DA — pet stavki, v. Queue C** |

---

# READY FOR MIGRATION EXECUTION: **NO**

Ne zbog opreza nego zato što je **Queue A prazan**: nijedna migracija nije
istovremeno dokazano nedostajuća i bezbedna za pokretanje. Dve koje nedostaju
tražile bi prepisivanje, ne izvršavanje.

Najkorisniji ishod ovog sprinta nije lista migracija nego dve tabele koje ne
postoje a kod ih svakodnevno gađa — i saznanje da se **17 od 106** može
dokazati, dok se za 79 ne može reći ništa jače od „šema postoji".

**Jedan upit u SQL Editoru** (`SELECT * FROM supabase_migrations.schema_migrations`)
pretvorio bi tih 79 u dokazivo — ili potvrdio da ledger ne postoji ni tamo.
To je jedini sledeći korak koji menja sliku.
