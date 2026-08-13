# BETA-CLOSURE-089-POST — FINAL FORENSIC REPORT

# VERDICT

## 🟡 YELLOW

Sve što se moglo dokazati **iz aplikacije** — dokazano je, i prošlo.
Ali tri stavke iz liste prihvatanja (indeksi, trigger, komentar) **nisu
verifikovane**, jer PostgREST ne izlaže sistemski katalog, a jedini put do njih
je izlaz `VERIFY_MIGRATION_089_READONLY.sql` koji još nije vraćen.

Ne proglašavam GREEN na osnovu toga što je SQL Editor rekao „Success".

---

# BASELINE

```
commit:            51a338d4
worktree:          čist (samo zatečeni untracked skriptovi/podaci)
089 SQL fajl:      NIJE menjan ovim taskom
                   (poslednji commit nad njim: 872c7485, Mission Atlas)
izmene aplikacije: NULA
```

---

# MIGRATION

```
089 izvršena:  DA — od strane vlasnika, ručno, u Supabase SQL Editoru
timestamp:     nepoznat (nema ledgera; v. §MIGRATION HISTORY)
```

Formulacija je namerno precizna: **089 je izvršena sada.** Pre ovog događaja
nije bila, i nijedan deo ovog izveštaja ne tvrdi suprotno.

---

# SCHEMA

## 19/19 — POTVRĐENO

Metod: `select(<kolona>).limit(0)` po koloni. **Nijedan red pročitan.**

```
089 kolone:     19/19 postoji
043 legacy:     10/10 postoji
```

Sve pojedinačno: `tenant_id`, `predmet_id`, `document_id`, `module_name`,
`operation_name`, `model_provider`, `model_version`, `system_prompt_hash`,
`user_prompt_hash`, `retrieved_context_ids`, `knowledge_sources`,
`retrieval_query`, `confidence_score`, `hallucination_check_result`,
`parent_event_id`, `correlation_id`, `audit_reference`, `status`,
`error_message`.

## Šta NIJE izmereno na kolonama

`data_type`, `is_nullable`, `column_default` — PostgREST ih ne izlaže.
Pokriva ih **Q1** verifikacione skripte.

---

# INDEXES

## 4/4 — **NIJE VERIFIKOVANO**

```
pg_indexes preko PostgREST-a:  nije izloženo (provereno)
```

Nijedan od četiri indeksa (`idx_ai_forensics_correlation_id`, `_predmet_id`,
`_module_name`, `_status`) ne može se videti iz aplikacije. Ni njihovo
postojanje, ni parcijalni predikat `WHERE status = 'error'`.

**Pokriva ih Q2.**

---

# TRIGGER

## **NIJE VERIFIKOVANO**

```
pg_trigger preko PostgREST-a:  nije izloženo (provereno)
pg_proc    preko PostgREST-a:  nije izloženo (provereno)
```

| | |
|---|---|
| postoji | nepoznato |
| omogućen | nepoznato |
| događaj/timing | nepoznato |
| funkcija | nepoznato |

**Ponašanje nije mutaciono testirano — i neće biti.** Jedini način da se
dokaže da trigger stvarno odbija izmenu jeste `UPDATE`, koji je zabranjen
(§5, §7). Migracija u svom `RAISE NOTICE` predlaže `UPDATE ... WHERE FALSE` —
**nisam to izvršio**, jer je i to `UPDATE` naredba.

Status po traženoj formulaciji: **`TRIGGER STRUCTURE VERIFIED` se NE MOŽE
tvrditi.** Ni struktura nije verifikovana, jer katalog nije dostupan.
Pokrivaju ih **Q3 i Q4**.

---

# COMMENT

## **NIJE VERIFIKOVANO**

`obj_description()` zahteva katalog. Pokriva ga **Q5**.

Podsetnik zašto je baš ovo vredno: i 043 i 089 postavljaju
`COMMENT ON TABLE ai_forensics`, i **089 prepisuje 043-ov**. Tekst je zato
potpis poslednje izvršene migracije — najbliže dokazu izvršenja koje ova baza
poseduje.

---

# RUNTIME

## Ugovor upisa — POTVRĐEN

```
writer:            security/ai_forensics.py::log_provenance_from_wrapper
                   ← shared/ai_client.py (zakrpa SDK klasa)
kolona u INSERT-u: 29  = 19 (089) + 10 (043)
```

**Jedan `select` nad svih 29 kolona odjednom — PROŠAO.** To je jači dokaz od
29 pojedinačnih: šema pokriva **ceo** INSERT ugovor runtime-a, bez ijedne
kolone viška ili manjka.

Runtime koristi sve tražene 089 kolone: `correlation_id`, `predmet_id`,
`status`, `model_provider`, `model_version`, plus preostalih 14.

**Da li je 089 sada potrebna za pun provenance upis?** DA. Bez nje 19 od 29
kolona ne postoji, `_is_missing_column_error` opali, i upis pada na uski skup
od 10 legacy kolona — **bez join ključa** (`correlation_id`, `predmet_id`) i
bez `status`.

## Šta NIJE dokazano

Da `INSERT` **uspeva**. Dokazan je ugovor **imena kolona**, ne tipova.
`knowledge_sources`/`retrieved_context_ids` idu kroz `json.dumps`,
`confidence_score` je numerički — neusklađenost tipa bi i dalje oborila upis.
Dokaz bi tražio `INSERT`, što je zabranjeno. Pokriva ga **Q1** (`data_type`).

---

# LEGACY FALLBACK

```
i dalje postoji:   DA
uslov:             isključivo SQLSTATE 42703 / „does not exist"
                   (`_is_missing_column_error`) — svaka druga greška se diže
normalni put:      NE ulazi u fallback (svih 29 kolona postoji)
može li sakriti:   NE — od BETA-HARDENING-002 degradacija je merljiva,
                   lepljiva, logovana kao ERROR i izložena na `/health`
```

**Verdikt: safety fallback, ne dead code.** Ostavljen, kako mandat i nalaže.
Štiti od buduće situacije u kojoj kod dobije novu kolonu pre nego što migracija
bude pokrenuta — tačno scenario koji je i proizveo `GT-001`.

---

# HEALTH

```
status:                ok
provenance blok:       prisutan
curenje kredencijala:  NEMA — provereno na postgres:// , supabase.co , eyJ ,
                       password , service_role , sk-
sirov izuzetak:        NE — vraća samo {"dostupno": false}
```

## Nalaz koji prijavljujem, a ne popravljam

U svežem procesu `/health` vraća:

```json
"provenance": { "prosirena_sema": null, "migracija_089_potvrdjena": false, … }
```

`false` ovde znači **„još nije izmereno"**, ne „nije primenjena" — stanje se
meri tek pri prvom provenance upisu. Doslovno je tačno (*nije potvrđena*), ali
naziv polja nosi tvrdnju koju čitalac može pročitati kao definitivan negativan
nalaz.

**Nisam menjao kod** — §4 nalaže nula izmena aplikacije, a ovo nije kvar nego
dvosmislenost naziva. Susedno polje `prosirena_sema: null` već nosi tačno
tro-stanje. Imenovano da vlasnik odluči.

---

# TESTS

```
targeted (provenance/governance/atlas):  79 passed / 1 skipped / 0 failed
full suite:                              5255 passed / 2 skipped / 0 failed
```

Nijedan test nije menjan da bi postao zelen. Nijedan nije dodat — dokaz ovog
sprinta je stanje produkcione baze, koje ne sme ući u suitu.

---

# PRODUCTION DATA MUTATIONS

```
INSERT:  0
UPDATE:  0
DELETE:  0
```

Sve sonde su `select(...).limit(0)` — nijedan red nije ni pročitan, kamoli
izmenjen.

---

# MIGRATION HISTORY

```
Vindex ledger izvršavanja:        NOT PRESENT
Supabase interne migration tabele: NIJE ekvivalent Vindex istoriji
MIGRATION HISTORY:                UNAVAILABLE
```

Utvrđeno forenzički (`a0fcd1e9`): nema `schema_migrations` tabele, `Procfile` i
`Dockerfile` ne pokreću migracije, nema Supabase CLI konfiguracije, nijedan od
5 workflow-a ne primenjuje migracije.

```
MIGRATION 089 EXECUTION = CONFIRMED BY USER EXECUTION
                        + POST-MIGRATION SCHEMA VERIFICATION (delimična)
```

„Delimična" jer su kolone verifikovane, a indeksi/trigger/komentar nisu.

---

# SECOND-EYE

Pokušaj obaranja zaključka *„089 je uspešno završena"*:

| Scenario | Ishod |
|---|---|
| pogrešno okruženje | **isključeno** — sonda i runtime dele isti `SUPABASE_URL` |
| pogrešna tabela | **isključeno** — runtime piše u `ai_forensics`, sonda merila `ai_forensics` |
| legacy dvojnik | **isključeno** — `ai_forensics_legacy`/`ai_provenance`/`forensics` ne postoje |
| runtime writer mismatch | **isključeno** — 29/29 kolona, nijedna van 089+043 |
| legacy fallback guta greške | **isključeno** — uslov je samo 42703, sve ostalo se diže |
| health mismatch | **djelimično** — v. nalaz o `false` vs „nije mereno" |
| **indeks nedostaje** | **NEISPITANO** — katalog nedostupan |
| **pogrešan predikat na `_status`** | **NEISPITANO** |
| **trigger onemogućen** | **NEISPITANO** |
| **pogrešan događaj/tabela/funkcija trigera** | **NEISPITANO** |
| **pogrešan tip kolone / default** | **NEISPITANO** |

**Pet neispitanih scenarija. Zato YELLOW.**

---

# GT-001

## OPEN — ali samo na jednoj, uskoj dimenziji

Ono što je `GT-001` značio — *„provenance tiho gubi join ključ, i niko to neće
znati"* — **više ne stoji**:

* svih 29 kolona koje runtime upisuje **postoje**, potvrđeno jednim `select`-om
* uska legacy grana se **ne aktivira** na normalnom putu
* i da se aktivira, **nije više tiha**

Ostaje: **integritet i nepromenljivost zapisa** — indeksi i `UPDATE`-blokirajući
trigger. Bez trigera se provenance red može tiho prepisati, čime prestaje da
bude upotrebljiv kao dokaz. To je zaseban ugovor od „ima li join ključ", i
jedini razlog zbog kog `GT-001` ostaje otvoren.

---

# FINAL STATEMENT

> *Da li je produkciona provenance šema sada dokazano kompletna, zaštićena i
> kompatibilna sa runtime writerom?*

## **NE — dve od tri stvari su dokazane.**

| | |
|---|---|
| **kompletna** | **DA** — 19/19 + 10/10; jedan `select` nad svih 29 kolona prolazi |
| **kompatibilna sa writerom** | **DA** — INSERT ugovor od 29 imena kolona u potpunosti pokriven |
| **zaštićena** | **NE ZNA SE** — trigger nije verifikovan, niti može biti iz aplikacije |

## Šta tačno nedostaje

Izlaz jedne skripte koju ste već pokrenuli u SQL Editoru:
**`docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql`** — šest `SELECT` upita,
ništa ne piše.

Konkretno mi trebaju:

| Upit | Zatvara |
|---|---|
| **Q2** | postoje li 4 indeksa i ima li `_status` predikat `WHERE status = 'error'` |
| **Q3** | postoji li trigger, je li **omogućen**, BEFORE/ROW, na UPDATE |
| **Q4** | baca li telo funkcije `RAISE EXCEPTION` (a ne `RETURN NEW`) |
| **Q5** | da li komentar nosi 089 potpis („AI Provenance & Decision Traceability") |
| **Q1** | tipovi i nullability — jedina preostala rupa u dokazu INSERT-a |
| **Q6** | postoji li ipak neki ledger u samoj bazi |

Sa tim izlazom `GT-001` se zatvara ili se imenuje precizan drift. Bez njega
verdikt ostaje YELLOW — ne zato što sumnjam da je migracija prošla, nego zato
što „Success. No rows returned" nije dokaz o objektima koje nisam video.
