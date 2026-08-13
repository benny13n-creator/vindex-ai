# BETA-INFRA-MIGRATION-FORENSICS-003 — CANONICAL SCHEMA BASELINE

**Baseline `23a58e4f`. NO MIGRATION EXECUTED: YES.** Nijedan
`INSERT`/`UPDATE`/`DELETE`/`ALTER`/`CREATE`/`DROP`/`TRUNCATE`. Nijedan
produkcijski fajl ni migracija menjani. Nijedan kredencijal u izlazu.

Prateći artefakt: `docs/beta_gate/BETA_INFRA_MIGRATION_MATRIX.csv` (106 redova).

---

# VERDICT

## 🟡 YELLOW

Bazna linija je **kompletna na nivou tabela i kolona** i po prvi put je
**izmerena, ne pretpostavljena**. Ali 12 artefakata ostaje `UNKNOWN` iz
strukturnog razloga, ne iz nemara — i to su baš oni bezbednosno najvažniji.

---

# FAZA 2 — ŠTA PRODUKCIJA JESTE

Prvi put u ovoj seriji sprintova postoji **merena bazna linija**, izvučena iz
PostgREST OpenAPI dokumenta:

```
tabela/view-ova izloženo:   166
kolona opisano:           1.631
RPC funkcija:                16
```

To je **kanonska bazna linija** ovog sprinta. Snimljena je i korišćena za diff
nad svih 106 artefakata.

## Meta-tabele iz mandata

| Tabela | Stanje |
|---|---|
| `public.rokovi` | **NE POSTOJI** |
| `public.api_costs` | **NE POSTOJI** |
| `ai_forensics` | postoji — 38 kolona, PK `id`, **2 NOT NULL** |
| `feature_usage` | postoji — 8 kolona, 1 FK, 8 NOT NULL |
| `discovered_bilteni` | postoji — 11 kolona, 1 FK, 7 NOT NULL |
| `case_benchmarks` | postoji — 11 kolona, **0 FK**, 2 NOT NULL |
| `zakoni_monitoring` | postoji — 9 kolona, **0 FK**, 3 NOT NULL |

## Granica metode — navedena, ne zaobiđena

PostgREST izlaže **isključivo `public`**. Nedostupno ostaje: `pg_catalog`,
`information_schema`, indeksi, RLS politike, trigeri, funkcije, komentari,
grantovi, enum tipovi.

**Ogradu nisam zaobišao kredencijalima** — mandat to izričito traži. Umesto
toga je tačno popisano šta se moglo, a šta ne.

---

# FAZA 3 — KLASIFIKACIJA SVIH 106

```
TOTAL ARTIFACTS        106
VERIFIED APPLIED         0
VERIFIED MISSING         1     023
PARTIAL / DRIFT          1     supabase_migration.sql
SCHEMA MATCH ONLY       92
UNKNOWN                 12     066, 075, 077, 079, 083, 097,
                               100, 102, 103, 107, 108, 111
```

## `VERIFIED APPLIED = 0` — i to nije neuspeh nego tačan nalaz

Nijedan artefakt ne može dobiti `VERIFIED APPLIED` jer **ledger ne postoji**.
Prisustvo tabele dokazuje **kompatibilnost šeme**, ne **poreklo ni izvršenje**.
Prethodni sprint je 17 označio kao `VERIFIED APPLIED` na osnovu dokaza na nivou
podataka (npr. cene 29/79/249) — to je jači dokaz od šeme, ali i dalje dokaz da
je **neko** te vrednosti upisao, ne da je **migracija** to uradila.

**Šta bi svaku `SCHEMA MATCH ONLY` stavku pretvorilo u `VERIFIED APPLIED`:**
jedan red u `supabase_migrations.schema_migrations` sa odgovarajućom verzijom.
Ništa drugo.

**Šta bi 12 `UNKNOWN` stavki pretvorilo u dokazive:** `SELECT * FROM pg_indexes`,
`pg_policies`, `pg_trigger`, `pg_proc`. Sve četiri su read-only.

---

# TRI ISPRAVKE MOG SOPSTVENOG ENGINE-a

Prvi prolaz mog diff engine-a dao je rezultate koje sam **odbacio kao netačne**
pre objavljivanja. Navodim ih jer je metod deo nalaza:

1. **Nije proveravao ciljeve indeksa** → 023 je ispao `UNKNOWN`. Posle
   proširenja (target tabela + kolone iz `CREATE INDEX ... ON t(c)`) postao je
   `VERIFIED MISSING` **sa dokazom**.
2. **Regex je hvatao imena šema kao tabele** → `110` je „nedostajao objekat
   `public`", `supabase_setup.sql` „`auth`". Oba lažna pozitiva.
3. **Nije prepoznavao namerno obrisane objekte** → `058` je prijavljen kao drift
   zbog `vindex_memory`, koji **migracija 075 namerno briše**. Sada je
   `SCHEMA MATCH ONLY / supersedirano`.

Posle ispravki: `VERIFIED MISSING` je pao sa 2 na 1, `PARTIAL/DRIFT` sa 3 na 1.
**Manje nalaza, ali svaki tačan.**

---

# FAZA 5 — RUNTIME KORELACIJA

| Objekat | Pozivaoci | Način otkaza | Posledica | Sev. |
|---|---|---|---|---|
| **`public.rokovi`** | **13 poziva / 9 fajlova** — `api.py`, `dashboard.py`, `morning_briefing.py`, `case_commander.py`, `decision_replay.py`, `integrations.py`, `whatsapp_notif.py`, `zadaci.py`, `zastarelost.py` | **C + B** — većina **nije** u `try` | rokovi su egzistencijalna funkcija advokata | **P1** |
| **`api_costs`** | `shared/cost.py:97` | **A** — izuzetak se guta, tok nastavlja kao da je uspeo | **praćenje troška AI poziva je mrtvo od početka** | **P1** |
| **`ratio_decidendi`** | `routers/praksa.py:311,330` | **E** — keš uvek promašuje | **svaki ratio se ponovo plaća LLM-u** | **P1** |
| **`reported_errors`** | prijava grešaka | **D** | korisničke prijave se ne beleže | P2 |
| `discovered_bilteni` RLS | — | — | **UNKNOWN**, v. Faza 8 | P0? |

`predmet_rokovi` takođe ne postoji. **Nijedna migracija u repou ne kreira ni
`rokovi` ni `api_costs`** — to nije migration drift nego **nedostajuća šema**.

---

# FAZA 8 — 017 / 110: `UNKNOWN`, i to je konačan odgovor ovog sprinta

Politike nisu čitljive kroz PostgREST. Efektivni test je pokušan i **dao
neodlučan rezultat**, što otvoreno navodim:

| Tabela | anon vidi | service-role vidi | Zaključak |
|---|---:|---:|---|
| `predmeti` | 0 | 19 | RLS blokira — ispravno |
| `ai_forensics` | 0 | 124 | RLS blokira — ispravno |
| `feature_usage` | 0 | 9 | RLS blokira — ispravno |
| **`discovered_bilteni`** | **0** | **0** | **prazna → NEODLUČNO** |
| **`case_benchmarks`** | **0** | **0** | **prazna → NEODLUČNO** |
| **`zakoni_monitoring`** | **0** | **0** | **prazna → NEODLUČNO** |

**RLS koji blokira vraća 200 sa nula redova, ne 403** — zato je poređenje sa
service-role obavezno, a na praznim tabelama ne razlikuje ništa.

**`INSERT` radi dokazivanja nije izvršen** — mandat ga zabranjuje, i to je
ispravno: dokaz koji zahteva mutaciju nije dokaz koji smemo pribaviti.

---

# FAZA 9 — KORENSKI FAJLOVI

| Fajl | Uloga | Stanje |
|---|---|---|
| `supabase_setup.sql` | **bootstrap** — 13 tabela, 32 politike | **svih 13 tabela postoji** |
| `supabase_migration_v3.sql` | dopuna — `usage_events`, `notifications` | **čist** |
| **`supabase_migration.sql`** | dopuna — 6 tabela | **PARTIAL/DRIFT** |

## Prelom oko linije 115 — dokazan monotonim prefiksom

```
l.  5  profiles          POSTOJI
l. 45  feedback          POSTOJI
l. 93  conversations     POSTOJI
l.115  reported_errors   NE POSTOJI   ← prelom
l.167  ratio_decidendi   NE POSTOJI
l.199  api_costs         NE POSTOJI
```

Sve pre 115 postoji, sve od 115 nedostaje. **Izvršavanje je stalo u toj tački**
— najverovatnije greška koja je prekinula skript, ali to je zaključak o obrascu,
ne o uzroku.

Ova tri fajla se **preklapaju** sa numerisanim migracijama (`profiles`,
`feedback`, `predmeti` postoje i tamo), pa nisu zamenljivi njima — a nikad nisu
ni bili u inventaru.

---

# FAZA 6 — QUEUE

## QUEUE A — SAFE TO RECONSTRUCT: **0**

Nijedan artefakt ne ispunjava sve uslove. **`CREATE IF NOT EXISTS` nije dokaz
bezbednosti** — 023 ga ima, a ipak bi pukla jer joj ciljne kolone ne postoje.

## QUEUE B — REQUIRES HUMAN REVIEW: **2**

- **`supabase_migration.sql` od l.115** — tri tabele; ali treba **rekonstrukcija
  isečka**, ne pokretanje celog fajla (prve tri tabele već postoje).
- **023** — treba **prepisati prema stvarnoj šemi**: cilja `email_notif_log.tip`
  i `.created_at` (stvarna kolona je `poslato_at`), `predmeti.obrisan`
  (ne postoji nijedna soft-delete kolona), `klijenti.obrisan` (postoji
  `deleted_at`), i tabelu `rokovi` koje nema.

## QUEUE C — MUST NOT RUN AS-IS: **92**

Svih 92 `SCHEMA MATCH ONLY`. Rerun nosi rizik duplog DML-a bez ijedne dobiti.
Posebno: **064** (rerun vraća P0 rupu koju je 110 zatvorio), **061**
(`UPDATE profiles` bez `WHERE`), **065/069/070** (75 slepih `UPDATE`-a nad
`feature_registry`, a audit tabele pokazuju da je Admin Console **korišćen**),
**063**, **047**, **058**, **075**, **111**.

## QUEUE D — NOT NEEDED: **12**

12 `UNKNOWN` artefakata koji sadrže samo indekse/politike/funkcije. Nisu „ne
treba" nego **nedokazivi ovom metodom** — prelaze u B ili C čim se pročita
`pg_policies`/`pg_indexes`.

---

# FAZA 11 — RAZDVAJANJE PROBLEMA

Mandat traži da se ne mešaju. Evo ih razdvojeno:

| Vrsta | Stavke |
|---|---|
| **MIGRATION PROBLEM** | 023 (piše prema šemi koja nikad nije postojala); `supabase_migration.sql` (prekinuto izvršavanje) |
| **SCHEMA PROBLEM** | `rokovi`, `api_costs`, `ratio_decidendi`, `reported_errors` — **nijedna migracija ih ne kreira**; nedostaje im definicija, ne izvršenje |
| **RUNTIME BUG** | `shared/cost.py:97` guta izuzetak i nastavlja kao da je uspelo — to je bug **nezavisan** od šeme |
| **DATA REPAIR** | nijedan u ovom sprintu |
| **PRODUCT DECISION** | da li rokovi uopšte treba da budu zasebna tabela ili izvedeni iz `predmeti` — nije forenzičko pitanje |

```
P0   1    (017/110 politika — UNKNOWN, ne potvrđeno)
P1   3    rokovi · api_costs · ratio_decidendi
P2  12    12 UNKNOWN artefakata
P3  92    schema-match, bez akcije
```

---

# ODGOVORI NA 9 CILJEVA

| # | Pitanje | Odgovor |
|---|---|---|
| 1 | Šta produkcija JESTE | **166 tabela, 1.631 kolona** — izmereno |
| 2 | Šta artefakti ZAHTEVAJU | u CSV-u, po artefaktu |
| 3 | Šta dodaju/menjaju/brišu | u CSV-u (`expected_objects`) |
| 4 | Koji delovi postoje | 92 potpuno, na nivou tabela/kolona |
| 5 | Koji nedostaju | **4 tabele** + 4 kolone (023) |
| 6 | Pogrešan oblik | **0 dokazano** — tipovi nisu poređeni (granica metode) |
| 7 | Bezbedno rekonstruisati | **0** bez ljudskog pregleda; 2 uz njega |
| 8 | Nikako ne pokretati | **92** |
| 9 | Runtime posledice drifta | **3 dokazane** — v. Faza 5 |

---

# NO MIGRATION EXECUTED: **YES**

Potvrđeno eksplicitno. Nijedna migracija, nijedan DDL, nijedan DML. Jedini upisi
u ovom sprintu su dva dokumenta u `docs/beta_gate/`.

---

# ZAVRŠNA REČ

Vrednost ovog sprinta nije u brojkama nego u jednoj rečenici koju sada možemo
reći sa dokazom:

> **Vindex nema migration ledger, pa se za 92 od 106 artefakata ne može reći
> ništa jače od „šema je kompatibilna".**

I u jednoj koja je gora: **četiri tabele koje kod svakodnevno gađa ne postoje ni
u jednoj migraciji.** To nije drift — to je funkcionalnost koja nikad nije ni
bila napisana, a kod se ponaša kao da jeste.
