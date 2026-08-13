# BETA-INFRA-MIGRATION-FORENSICS-002 — REMOTE HISTORY VERIFICATION

**Baseline `d2ee2d9f`. READ-ONLY. Nijedna migracija nije pokrenuta. Nijedan
`INSERT`/`UPDATE`/`DELETE`/`ALTER`/`CREATE`/`DROP`. Nijedan produkcijski fajl
menjan** — samo ovaj dokument.

---

# 1. REMOTE MIGRATION HISTORY

## `PUBLIC SUPABASE MIGRATION HISTORY = ABSENT`

I to je sada **dokaz, ne pretpostavka**. OpenAPI koren kaže
`info.title = "standard public schema"` i izlaže **183 putanje** — dakle cela
`public` šema je vidljiva. `public.supabase_migrations` i
`public.schema_migrations` u njoj **ne postoje** (404). Kad je šema u celosti
izložena, odsustvo tabele jeste dokaz odsustva.

## Ostale šeme — `UNKNOWN`, i to ne ublažavam

| Šema.tabela | Ishod |
|---|---|
| `supabase_migrations.schema_migrations` | **406 Invalid schema** |
| `auth.schema_migrations` | 406 |
| `realtime.schema_migrations` | 406 |
| `storage.migrations` | 406 |
| `graphql.schema_migrations` | 406 |

**PostgREST izlaže isključivo `public`.** `406` znači „ova šema nije izložena",
**ne** „tabela ne postoji". Za CLI ledger (`supabase_migrations.schema_migrations`)
odgovor ostaje **UNKNOWN** i može ga razrešiti samo SQL Editor.

Uz to: nema `supabase/` direktorijuma, nema `config.toml`, i nijedan
Procfile/Dockerfile/CI ne pokreće migracije — pa i da ledger postoji, ne bi ga
punio nijedan automatski proces.

---

# 2. LOCAL VS REMOTE LEDGER

**Matrica se ne može napraviti.** Nijedan ledger nije dohvatljiv, pa bi svaka
kolona `REMOTE HISTORY` imala istu vrednost — `UNKNOWN`. To bi bila tabela od
106 redova koja ne kaže ništa.

Ostaje raspodela iz prethodnog sprinta, sada sa preciznijim imenom kolone:

```
HISTORY_VERIFIED_APPLIED         0    (nijedan ledger nije čitljiv)
HISTORY_ABSENT_SCHEMA_PRESENT   96
HISTORY_ABSENT_SCHEMA_ABSENT     2    023, 109
PARTIAL_OR_DRIFT                 1    supabase_migration.sql
UNKNOWN                          7
```

**Jedini nefalsifikovan dokaz izvršenja u celom repou i dalje je migracija
111** — jedina koja ostavlja pečat (`updated_by = 'migration_111_phantom_ai_charges'`).

---

# 3. MIGRACIJA 017 vs 110 — **UNKNOWN, i to je ispravka prethodnog sprinta**

Prethodni sprint je zaključio da ispravka iz 110 „nije primenjena" zato što
`discovered_bilteni` **danas postoji**, a 110 ju je preskočio uz komentar da ne
postoji. **Postojanje tabele nije dokaz o politici.**

## Šta sam izmerio i zašto prvi pokušaj nije značio ništa

Prvi test je bio anon `GET` na sedam tabela — svih sedam vratilo **200**. To
**ne dokazuje ništa**: RLS koji blokira vraća `200` sa **nula redova**, ne `403`.
Dokaz da je test bio neispravan stoji u samom rezultatu — i `predmeti`, koja
sigurno ima RLS, vratila je 200.

Ispravan test poredi **broj redova koji anon vidi** sa brojem koji vidi
service-role:

| Tabela | anon | service | Zaključak |
|---|---:|---:|---|
| `predmeti` | 0 | 19 | RLS blokira — ispravno |
| `klijenti` | 0 | 5 | RLS blokira — ispravno |
| `ai_forensics` | 0 | 124 | RLS blokira — ispravno |
| **`feature_usage`** | **0** | **9** | **RLS blokira — meta 110-ke izgleda zaštićeno** |
| `feature_registry` | 0 | 70 | RLS blokira |
| `tier_config` | 0 | 3 | RLS blokira |
| **`discovered_bilteni`** | **0** | **0** | **prazna — test NEODLUČAN** |
| **`case_benchmarks`** | **0** | **0** | **prazna — test NEODLUČAN** |
| **`zakoni_monitoring`** | **0** | **0** | **prazna — test NEODLUČAN** |

## Verdikt

- **P0-3 (017 politika bez `TO` → PUBLIC `USING(true)`): `UNKNOWN`.** Tabela je
  prazna, pa čitanje ne razlikuje „politika propušta" od „nema šta da se vidi".
  Jedini konačan test bio bi `INSERT` — **zabranjen**.
- **P0-2 (045 bez `ENABLE RLS`): `UNKNOWN`**, iz istog razloga.
- **Ono što jeste izmereno:** anon **ne vidi nijedan red** ni u jednoj tabeli
  koja ima podatke, uključujući `feature_usage`. To ne dokazuje da je 110
  primenjen, ali **obara tvrdnju da je njegova meta danas otvorena**.

Razrešava `SELECT * FROM pg_policies WHERE tablename IN
('discovered_bilteni','case_benchmarks','zakoni_monitoring');` u SQL Editoru.

---

# 6. NENUMERISANI ARTEFAKTI — sva tri, ne jedan

Prethodni sprint je pregledao samo `supabase_migration.sql`. Ima ih tri.

## `supabase_migration.sql` — **PARTIAL / DRIFT, potvrđeno**

Prelom po **monotonom prefiksu** na liniji 115:

| Linija | Tabela | Stanje |
|---|---|---|
| 5 | `profiles` | POSTOJI |
| 45 | `feedback` | POSTOJI |
| 93 | `conversations` | POSTOJI |
| **115** | **`reported_errors`** | **NE POSTOJI** |
| **167** | **`ratio_decidendi`** | **NE POSTOJI** |
| **199** | **`api_costs`** | **NE POSTOJI** |

Sve pre 115 postoji, sve od 115 nedostaje. Izvršavanje je stalo u toj tački.

## `supabase_migration_v3.sql` — **ČIST**

`usage_events` i `notifications` postoje. Nema drift-a.

## `supabase_setup.sql` — **ČIST na nivou tabela**

**Svih 13 tabela postoji** (`profiles`, `user_credits`, `audit_log`, `feedback`,
`response_audit`, `predmeti`, `predmet_dokumenti`, `predmet_hronologija`,
`predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `klijenti`,
`predmet_klijenti`). Njegove **32 politike** ostaju `UNKNOWN` — PostgREST ih ne
izlaže.

*Napomena o metodu: `IF` na l.165 i l.6 je artefakt mog regexa nad
`CREATE TABLE IF NOT EXISTS`, ne nedostajuća tabela.*

---

# 7. RUNTIME IMPACT TRIAGE

| Objekat | Runtime pozivaoci | Način otkaza | Posledica |
|---|---|---|---|
| **`api_costs`** | `shared/cost.py:97` | **izuzetak se guta** | **praćenje troška AI poziva je mrtvo od početka.** Komentar u istom fajlu kaže „api_costs will misreport actual spend" — a tabele nema uopšte |
| **`ratio_decidendi`** | `routers/praksa.py:311,330` | keš uvek promašuje | **svaki ratio decidendi se ponovo plaća LLM-u** — direktan, ponovljiv trošak |
| **`public.rokovi`** | **13 poziva u 9 fajlova** (`api.py`, `dashboard.py`, `morning_briefing.py`, `case_commander.py`, `decision_replay.py`, `integrations.py`, `whatsapp_notif.py`, `zadaci.py`, `zastarelost.py`) | većina **nije** u `try` | **rokovi su za advokata egzistencijalna funkcija** |
| **`reported_errors`** | prijava grešaka | tiho | korisničke prijave se ne beleže |
| `discovered_bilteni` RLS | — | — | **UNKNOWN**, v. §3 |

`predmet_rokovi` takođe **ne postoji**. Nijedna migracija u repou ne kreira
nijednu od te dve tabele.

---

# 8. POMIRENJE BROJA „112"

```
raspon brojeva u imenima:        2..112   → 111 celih brojeva
rupe:                            9        (27–35)
NUMERISANE MIGRACIJE:            102      (111 − 9)
NENUMERISANI u migrations/:      1        smart_contract_analyses.sql
KORENSKI .sql van migrations/:   3        supabase_migration.sql
                                          supabase_migration_v3.sql
                                          supabase_setup.sql
──────────────────────────────────────────
UKUPNO MIGRATION ARTEFAKATA:     106
```

Nema ne-SQL fajlova u `migrations/`, nema duplikata, nema `.bak`/`.old`.
**„112" je najveći broj u imenu fajla — nikad nije bio broj migracija.**

---

# 9. KONAČNI ZBIR

```
TOTAL LOCAL MIGRATION ARTIFACTS   106
HISTORY VERIFIED                    0    nijedan ledger nije čitljiv
HISTORY ABSENT                    106
SCHEMA MATCH ONLY                  96
DRIFT / PARTIAL                     1    supabase_migration.sql
MISSING SCHEMA                      2    023, 109
UNKNOWN                             7
P0                                  2    oba UNKNOWN po merenju (017/045)
P1                                  5    api_costs, ratio_decidendi, rokovi,
                                         reported_errors, 089 append-only
```

---

# 10. NAJVAŽNIJE PITANJE

> **Da li sada imamo dovoljno dokaza da počnemo kontrolisano rešavanje migration
> drift-a?**

## **NO**

Ali razlog nije isti kao prošli put, i to je napredak.

Prošli put je odgovor bio NO zato što nismo znali **šta nedostaje**. Sada znamo
tačno šta nedostaje — četiri tabele i dve migracije. Odgovor je NO zato što ne
znamo **šta je već pokušano**, a to menja svaku popravku:

**Šta tačno nedostaje:**

1. **CLI ledger** — `SELECT * FROM supabase_migrations.schema_migrations;`
   PostgREST ga ne može dohvatiti. Bez njega je svaka od 96 „schema match"
   migracija jednako verovatno pokrenuta i nikad pokrenuta.
2. **Stvarne RLS politike** — `SELECT * FROM pg_policies WHERE tablename IN
   ('discovered_bilteni','case_benchmarks','zakoni_monitoring');`
   Bez njih su **oba P0 nalaza `UNKNOWN`**, a ne potvrđena.

Oba su **jedan `SELECT`**, oba su read-only, i oba menjaju sliku.

---

# ACTION QUEUE

## QUEUE 1 — MUST FIX BEFORE BETA

| Stavka | Zašto |
|---|---|
| **`public.rokovi`** | 13 poziva u 9 fajlova gađa nepostojeću tabelu; rokovi su egzistencijalna funkcija advokata |
| **`api_costs`** | trošak AI poziva se ne meri — nema osnove za naplatu ni kontrolu potrošnje |
| **Razrešiti oba P0 (`pg_policies`)** | dok su `UNKNOWN`, ne sme se tvrditi da je RLS ispravan |

## QUEUE 2 — SAFE AFTER ADDITIONAL DESIGN

- **`ratio_decidendi`** — keš; nedostatak košta, ali ne kvari tačnost.
- **`reported_errors`** — prijave grešaka.
- **089 append-only trigger** — verifikacija, ne popravka.
- **023** — **prepisati prema stvarnoj šemi**, ne pokrenuti kakva jeste.

## QUEUE 3 — DO NOT TOUCH

- **Svih 96 „schema present"** — rerun nosi rizik duplog DML-a bez ijedne dobiti.
- **064, 063, 065, 069, 070, 047, 058, 061, 075, 111** — rerun **aktivno kvari**
  živo stanje.
- **`supabase_setup.sql`, `supabase_migration_v3.sql`** — čisti; ne dirati.

## QUEUE 4 — DOCUMENTATION / HISTORICAL DRIFT

- 9 rupa u numeraciji (27–35) — nikad nisu postojale.
- Tri korenska `.sql` van `migrations/` — trajno van svakog inventara.
- Odsustvo ledgera kao **arhitektonska činjenica**, ne kvar koji se krpi.

---

# READY FOR MIGRATION EXECUTION: **NO**

Nijedna migracija se ne sme pokrenuti dok se ne pročita CLI ledger. Ali dve
tabele koje **nijedna migracija ne kreira** — `rokovi` i `api_costs` — nisu
migration problem nego **nedostajuća šema**, i njihovo rešavanje ne čeka ledger.

Ovaj sprint ništa nije popravio. Rekao je gde se tri stanja ne poklapaju:
**git ima 106 artefakata, produkcija ima 96 od njih, a ledger nema nijedan.**
