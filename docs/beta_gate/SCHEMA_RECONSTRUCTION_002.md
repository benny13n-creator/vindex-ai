# BETA-INFRA-SCHEMA-RECONSTRUCTION-002 — PRODUCTION SCHEMA CONTRACT

```
NO PRODUCTION MUTATION: YES · NO MIGRATION EXECUTION: YES
NO CODE MODIFICATION:   YES · NO SECRETS EXPOSED:     YES
```

Baseline `2a2e799c`. Postojeća suita: **5.418 passed / 2 skipped / 0 failed** —
nepromenjeno, jer sprint ne dira kod.

---

# 1. EXECUTIVE VERDICT

## 🔴 RED

Ne zbog nepoznanica nego zato što je dokazana **aktivna kritična neispravnost**.
Mandat definiše RED kao *„evidence reveals active critical vulnerability or
destructive ambiguity"* — ovde postoji oboje.

**Presudni nalaz:** provera sukoba interesa vraća **„nema sukoba" uvek**.
Advokatu se prikazuje `✅ Nije pronađen sukob interesa.` na jedinom ekranu gde
lažno-negativan nalaz nosi **disciplinsku odgovornost i licencu**.

`5.418` zelenih testova stoji naporedo sa tim. Broj testova ovde ne znači ništa
— suita meri ono što je neko napisao da meri, a ovaj sprint je tražio baš ono
što niko nije.

---

# 2. PRODUCTION BASELINE

```
166 tabela/view-ova · 1.631 kolona · 16 RPC funkcija
```

Izvučeno iz PostgREST OpenAPI korena. Nedostupno i deklarisano kao takvo:
`pg_catalog`, `information_schema`, indeksi, RLS politike, trigeri, funkcije,
komentari, enumi. **Ograda nije zaobiđena kredencijalima.**

---

# 3. UGOVOR ZA 166 OBJEKATA

`docs/beta_gate/SCHEMA_CONTRACT_166.csv` — 172 reda (166 produkcijskih + 6
fantoma). Sweep nad **1.816 fajlova** → 1.533 direktna + 29 razrešenih
indirektnih pristupa, svaki zatim **sondiran u produkciji**.

| Kategorija | Broj |
|---|---|
| backend + frontend | 1 (`profiles`) |
| samo backend | 147 |
| samo frontend | 1 (`conversations`) |
| samo test kod | 3 |
| **niko ne referencira** | **14** |

Četiri statička nalaza su **odbačena kao lažno pozitivna** posle ručnog čitanja
izvora — cross-contamination promenljive između dva handlera u istom fajlu.

---

# 4. FANTOMSKA ŠEMA

## Kategorija D — najvredniji nalaz sprinta, uz ispravku ozbiljnosti

**23 tabele / 64 kolone** koje kod referencira a ne postoje. Ali ozbiljnost
zavisi od **oblika pristupa**, i to sam morao da izmerim posebno:

| Oblik | Broj | Posledica |
|---|---|---|
| **kolona IMENOVANA u `select()`** | **100 pozivnih mesta, 16 tabela** | **HTTP 400** — PostgREST odbija **ceo** zahtev |
| `select("*")` + `.get("kolona")` | ostatak | **tiho `None`** — advokat vidi prazno polje |

Ovo su dve različite težine i dve različite popravke. Prvi prolaz je pomešao
oba; brojka 100 je posle isključivanja **embed sintakse** (`predmeti(naziv)`),
koja je davala lažne pogotke.

### Gde su najgušći

```
12  routers/decision_replay.py     11  routers/billing_reports.py
 7  routers/case_intelligence.py    5  routers/case_commander.py
 5  routers/multi_agent.py          4  routers/client_twin.py
```

**`billing_reports.py` je najozbiljniji** — `fakture.iznos_rsd`,
`fakture.klijent_id`, `billing_entries.iznos/kolicina/ukupno/fakturisano`.
Izveštavanje o naplati po ovome ne može da se izvrši.

**`predmeti`**, centralni objekat aplikacije, ima **11 nepostojećih kolona** u
upitima (`sud`, `oblast`, `stranke`, `klijent_id`, `ishod`, `tip_spora`,
`datum_otvaranja`…). `id`, `naziv`, `tip`, `status` postoje — zato osnovne rute
rade, i zato je ovo preživelo 5.418 zelenih testova.

## A / B / C

- **A** (ni produkcija ni migracije): `rokovi` (13 mesta), `klijenti_dokumenti`
  (tipfeler — produkcija ima `klijent_dokumenti`), `user_activity_profile`
- **B** (migracije, ne produkcija): `api_costs`, `ratio_decidendi`,
  `reported_errors` — sve tri **samo** u legacy `supabase_migration.sql`
- **C** (šema se razlikuje): `feedback`, `evidence_grafovi`, `push_subscriptions`

**Fantomskih RPC poziva: 0.** Obrnuto — 4 RPC-a u produkciji nema ko da pozove.
**`predmet_rokovi` NIJE fantom** — ime postoji samo u nazivu test funkcije.

---

# 5. FALSE-SUCCESS INVENTAR

```
FS-P0  4  ·  FS-P1  42  ·  FS-P2  26  ·  FS-P3  7   →  79 ukupno
```

Sistemski obim, mereno AST-om: **415 neproverenih upisa** (122 na kritičnim
tabelama), **489 progutanih izuzetaka bez Sentry-ja**, **118 `except: pass`**,
**128 sirovih `create_task`** naspram 6 upotreba `shared/bg.py::spawn`, **23
handlera** koji progutaju grešku upisa i vrate uspeh, **26/170** frontend upisa
bez provere `res.ok`.

## FS-P0-01 — najgori nalaz u celoj seriji sprintova

**`klijenti/router.py:692` + `static/vindex.js:5027` — provera sukoba interesa.**

Vraća „nema sukoba" **uvek**, iz četiri nezavisna razloga koji se sabiraju:

1. čita `predmet_klijenti`, koja je **prazna (0 redova)** i **nema `user_id`
   kolonu** → petlja se nikad ne izvrši, izuzetak se ni ne digne
2. cela pretraga je u jednom `try` čiji `except` samo loguje i pušta kod dalje
   do `conflict_detected = len([]) > 0`
3. frontend **ne proverava `r.ok`** → i HTTP 500 završi u grani „nema sukoba"
4. `predmet_klijenti` je prazna **jer se svih 7 upisa u nju progutaju**

Verifikovano nezavisno: `predmet_klijenti` — **0 redova**, `user_id` **ne
postoji**.

Nema Sentry-ja, nema testa, nema polja u odgovoru koje bi odalo nepotpunu
pretragu. **Korisnik gubi najviše, a vidi najmanje — zelenu kvačicu.**

## Ostala tri FS-P0

- **FS-P0-02** — dešifrovan JMBG/pasoš/PIB **bez audit zapisa**
- **FS-P0-03** — obrisana beleška **ostaje pretraživa u celosti**
- **FS-P0-04** — fail-open rola (danas nedostižno, imenovano)

## Nalaz koji menja redosled svake buduće popravke

**Pet postojećih testova učvršćuje bagove** (`test_cross_doc.py:228`,
`test_evidence_klasifikacija.py:93`, `test_batch_ingest.py:248`,
`test_gdpr_delete.py`, `test_lambda003_*`). Moraju se **obrnuti pre** ispravki —
inače će tačne popravke pasti kao „regresija".

---

# 6. TRAGOVI 20 KRITIČNIH TOKOVA

**76 tačaka lažnog uspeha** (21 kritična / 33 ozbiljne / 22 lakše).

| Status | Broj | Tokovi |
|---|---|---|
| **potpuno funkcionalan** | **1/20** | OCR (lokalni Tesseract) |
| delimično | 12/20 | 1,2,3,4,6,7,8,9,10,11,14,18 |
| **ne radi** | **7/20** | 12, 13, 15, 16, 17, 19, 20 |

## F20-01 — potvrđeno mojim merenjem, bez ijednog `INSERT`-a

`rokovi_lanac.py` računa rokove po ZPP-u **ispravno**, prikazuje ih advokatu
crveno kao `KRITIČAN` uz citat `ZPP čl. 374 st. 1` — i **nikad ih ne upisuje**.

```
u bazi (52 reda):  kritičan 17 · važan 13 · informativan 22
kod piše:          kljucan · normalan · info
```

**Nijedna kod-ova vrednost ne postoji u bazi** → CHECK ograničenje važi → upis
pada. Dugme „Sačuvaj" **ne opali ni error ni success granu — ćuti**. Test
`test_rokovi_lanac.py:214` kodifikuje kvar kao ugovor.

## Ostalo teško

- **F20-03** — oba cron workflow-a šalju `Authorization: Bearer`, server traži
  `X-Cron-Key`; `curl` je **bez `-f`** → **CI je zelen svaki dan uz nula
  poslatih podsetnika**
- **F1-01** — odjava je **zagarantovan no-op**: `sign_out(jwt)`, a kod prosleđuje
  UUID → 401 → progutan → „Odjavili ste se sa svih uređaja"
- **F3-01** — `POST /api/playbook/upload` **100% slomljen** (5-torka pakovana u
  2 promenljive)
- **F14-01** — GDPR „anonimizovan" dodiruje **2 tabele, nula Storage, nula
  Pinecone**, i ne proverava rezultat. `shared/vector_deletion.py` je potpun
  testiran brisač sa **nula produkcionih pozivalaca**
- **F9-01 / F10-01** — ispad Pinecone-a se prikazuje kao **tvrdnja o srpskom
  pravu**; blokiran AI odgovor se vraća kao `status: "success"`

---

# 7. GRANICA PODATAKA

- **Nijedna tehnička kontrola retencije ne postoji:** `store=`,
  `extra_headers`, `organization=`, `base_url=`, ZDR — **0 pogodaka u celom
  repou**.
- **Prompt guard je detektor injectiona, NE redaktor PII-a.**
- **Ceo tekst dokumenta trajno stoji NEŠIFROVAN u Pinecone metapodacima**
  (`text[:40000]`) uz `source_filename`, `predmet_id`, `kancelarija_id` — dok je
  **isti sadržaj u Storage-u AES-GCM šifrovan.** Granica enkripcije je
  nedosledna.
- **RLS je zaobiđen na svakoj API putanji** (jedan `service_role` klijent); ~250
  `CREATE POLICY` je **mrtvo za serverski saobraćaj**. Nula politika na
  `storage.objects`.

**§5 je poštovan doslovno:** svako polje retencija/treniranje/logovanje/lokacija
je **UNKNOWN** (U-01…U-15), jer mandat zabranjuje izvođenje politike provajdera
iz sećanja.

---

# 8. POMIRENJE MIGRACIJA

Iz prethodnog sprinta, nepromenjeno: 106 artefakata · `VERIFIED APPLIED` **0** ·
`VERIFIED MISSING` 1 (023) · `PARTIAL/DRIFT` 1 · `SCHEMA MATCH ONLY` 92 ·
`UNKNOWN` 12.

**`CREATE IF NOT EXISTS` nije dokaz bezbednosti** — 023 ga ima, a ipak bi pukla.

---

# 9. `ratio_decidendi` — PREDLOŽENI UGOVOR (bez SQL-a)

| Polje | Tip | Status |
|---|---|---|
| `decision_number` | text **UNIQUE** | **ZAHTEVA KOD** — `on_conflict` ga traži |
| `ratio` | text | **ZAHTEVA KOD** |
| `created_at` | timestamptz default now() | **ZAHTEVA KOD** |
| `model`, `correlation_id` | text | preporuka dizajna — spaja keš sa `ai_forensics` |
| `tenant/RLS` | — | **nije potrebno**: sadržaj je **javna sudska praksa**, ne klijentski podatak |

Retencija: neograničena (javni sadržaj). Brisanje: nije GDPR predmet.

---

# 10. `reported_errors` — PREDLOŽENI UGOVOR (bez SQL-a)

| Polje | Tip | Status |
|---|---|---|
| `user_id` | uuid → `profiles.id` | **ZAHTEVA KOD** (RLS `insert-own`) |
| `pitanje`, `odgovor` | text | **ZAHTEVA KOD** |
| `created_at` | timestamptz | **ZAHTEVA KOD** |
| `correlation_id` | text | **preporuka** — bez njega se prijava **ne može spojiti** sa AI pozivom na koji se žali |
| `predmet_id` | uuid | preporuka |

**RLS obavezan** (`insert-own`, čitanje samo founder). **Retencija traži odluku
osnivača** — čuvanje punog pitanja i odgovora je namerni izuzetak od
NO-STORAGE/ZZPL politike. Predložena šema od 4 kolone je **pretanka**.

---

# 11. `rokovi` — ODLUKA

## **D) RUNTIME REFACTOR** (uz B kao prelaz)

Odbačeno **C (nova tabela)**: **13 čitalaca, nula pisaca.** Tabela bi bila
kreirana prazna i ostala prazna. Uz to tri upita nemaju `user_id` filter, a
`api.py:2641` nema **nikakvu** proveru vlasništva — tabela bez RLS-a bila bi
**IDOR rupa u klijentskom portalu**.

Odbačeno **A (postojeća tabela) kao neposredan potez**: `predmet_hronologija`
**jeste** vlasnik domena (10 živih pisaca, VERIFIED FK, mapiranje već postoji u
`case_dna.py:655`) — ali prevezivanje svih 13 čitalaca je 13 izmena produkcije,
od kojih 10 na putanjama koje niko ne poziva.

**Beta obim su 3 LIVE reference.** Jedina hitna je javni klijentski portal.
Ostalih 10 čeka odluku o sudbini `Deadline Guardian`-a.

Ni `zadaci` ni `rocista` **ne mogu**: `zadaci` **nema `user_id` uopšte**, a 9 od
13 upita filtrira po njemu.

---

# 12. PRIORITETI

## P0 — 4

| ID | Nalaz | Blast radius |
|---|---|---|
| **FS-P0-01** | provera sukoba interesa uvek „nema sukoba" | **licenca advokata** |
| FS-P0-02 | dešifrovan JMBG/PIB bez audita | GDPR, dokazivost |
| FS-P0-03 | obrisana beleška ostaje pretraživa | poverljivost |
| FS-P0-04 | fail-open rola (nedostižno) | autorizacija |

## P1 — 9 grupa

`F20-01` rokovi se ne čuvaju · `100 select-ova` sa nepostojećom kolonom
(billing najgušći) · `F20-03` cron zelen a ništa ne šalje · `F1-01` odjava
no-op · `F14-01` GDPR ne dodiruje Storage ni Pinecone · `F17` obe prijave
netačnog odgovora se gube · pun tekst nešifrovan u Pinecone-u · `F3-01`
playbook upload slomljen · 42 FS-P1 stavke

## P2 — 26 · P3 — 7

---

# 13. PREDUSLOVI ZA IZVRŠENJE MIGRACIJA

**Nijedan nije ispunjen.** Migracije se ne smeju pokretati dok:

1. se ne pročita `supabase_migrations.schema_migrations` (jedan `SELECT`)
2. se ne pročita `pg_policies` za tri prazne tabele (jedan `SELECT`)
3. se ne **obrne 5 testova koji učvršćuju bagove**
4. se ne razreši da li je 110 uopšte primenjen

---

# 14. EKSPLICITNI UNKNOWN

| # | Stavka | Kako se dokazuje |
|---|---|---|
| U-1 | CLI migration ledger | `SELECT` u SQL Editoru |
| U-2 | RLS politike na 3 prazne tabele | `pg_policies` |
| U-3 | retencija/treniranje kod OpenAI i Pinecone | **politika provajdera, ne kod** |
| U-4 | RLS na `storage.objects` | `pg_policies` |
| U-5 | append-only trigger na `ai_forensics` | `pg_trigger` |
| U-6 | tipovi/nullability 64 nedostajuće kolone | `information_schema` |
| U-7 | liveness 10 `rokovi` ruta | **Playwright**, ne grep |
| U-8…U-15 | v. `EXTERNAL_BOUNDARY_002.md` |

**Nijedan UNKNOWN nije pretvoren u zaključak.**

---

# 15. SLEDEĆIH PET SPRINTOVA

1. **FS-P0-01 — sukob interesa.** Jedini nalaz sa pravnom posledicom po
   advokata. Ne čeka ništa.
2. **Obrnuti 5 testova koji učvršćuju bagove.** Preduslov za sve ostalo —
   inače svaka tačna popravka pada kao regresija.
3. **100 `select`-ova sa nepostojećom kolonom**, počev od `billing_reports.py`.
4. **F20-01 + F20-03 + F1-01** — tri tiha otkaza u kojima korisnik vidi uspeh.
5. **Dva `SELECT`-a** iz §13 — jeftino, a otključava 92 „schema match only".

---

# ZAVRŠNA REČ

Ovaj sprint nije tražio nove funkcije nego istinu o postojećim. Rezultat je da
**jedan od dvadeset kritičnih tokova radi u celosti**, i da sistem na više mesta
**kaže uspeh tamo gde je operacija pala** — uključujući ekran čija je jedina
svrha da advokata upozori.

Ništa nije popravljeno, ništa nije pokrenuto, ništa nije mutirano.
