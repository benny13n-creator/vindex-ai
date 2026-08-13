# BETA-CLOSURE-089 — FINAL FORENSIC REPORT

# VERDICT

## 🟡 YELLOW

**Runtime zavisnost je dokazana. Poreklo šeme nije.**

Sve što `GT-001` suštinski traži — da provenance upis ne gubi join ključ —
sada je **izmereno u produkciji, ne pretpostavljeno**. Ali stroga lista
prihvatanja traži i „no schema drift", a indekse i trigger iz 089 aplikacija
ne može da vidi. Zato ne GREEN.

---

# BASELINE

```
commit:  b2825d88
git:     čist (samo zatečeni untracked skriptovi/podaci)
testovi: 47 passed / 1 skipped / 0 failed  (relevantni provenance subset)
```

**Produkcijskih izmena: NULA. Migracija izvršenih: NULA.**

---

# MIGRATION 089

```
fajl:      migrations/089_ai_provenance_extension.sql
svrha:     AI Provenance Extension (Mission Atlas) — povezuje postojeći
           SEC-003 patch point sa tabelom `ai_forensics` iz migracije 043
tabela:    ai_forensics   (jedina)
kolone:    19  (ADD COLUMN IF NOT EXISTS — idempotentno)
indeksi:   4   (correlation_id, predmet_id, module_name, status WHERE 'error')
funkcija:  protect_ai_forensics_from_update()
trigger:   trg_protect_ai_forensics_update  (BEFORE UPDATE)
transakcija: NE (nema BEGIN/COMMIT)
destruktivno: NE
zavisnost: 043 (kreira tabelu), pokreće se posle 088
```

Trigger **namerno** ne blokira `DELETE` — `services/retention_service.py`
legitimno briše redove starije od retencionog roka (GDPR).

---

# MIGRATION HISTORY

```
mehanizam praćenja: NE POSTOJI
```

Ovo nije „nismo našli" nego **strukturna činjenica**, utvrđena forenzički:

* nema `schema_migrations`, `supabase_migrations` ni ekvivalentne tabele
* `Procfile` i `Dockerfile` **ne pokreću migracije** — deploy je `gunicorn api:app`
* nema Supabase CLI konfiguracije
* 5 GitHub Actions workflow-a, nijedan ne primenjuje migracije
* zaglavlje same 089 kaže: *„Pokrenuti u: Supabase Dashboard → SQL Editor"*

**Migracije se primenjuju ručno.** Kolona „History" u trostrukoj matrici zato
nije `UNKNOWN` — ona **ne postoji kao artefakt**. To je najvažniji nalaz ovog
sprinta, jer menja pitanje: ne „da li je zabeleženo", nego „da li je šema tu".

---

# ACTUAL DATABASE SCHEMA — IZMERENO

Metod: `select(<kolona>).limit(0)` po koloni. **Nijedan red nije pročitan.**
Nikakav `INSERT`/`UPDATE`/`DELETE`/DDL. Tehnika je identična postojećoj
`scripts/audit_state.py::audit_migrations` — nije pisan nov mehanizam.

```
ai_forensics: tabela postoji

19 kolona iz 089:   19/19  POSTOJI     (0 nedostaje)
10 legacy iz 043:   10/10  POSTOJI
```

Sve pojedinačno potvrđeno: `tenant_id`, `predmet_id`, `document_id`,
`module_name`, `operation_name`, `model_provider`, `model_version`,
`system_prompt_hash`, `user_prompt_hash`, `retrieved_context_ids`,
`knowledge_sources`, `retrieval_query`, `confidence_score`,
`hallucination_check_result`, `parent_event_id`, **`correlation_id`**,
`audit_reference`, **`status`**, `error_message`.

---

# THREE-WAY RECONCILIATION

| Stavka | 089 očekuje | History | Stvarna šema | Verdikt |
|---|---|---|---|---|
| `correlation_id` | DA | *n/p — nema mehanizma* | **DA** | ŠEMA POTVRĐENA |
| `predmet_id` | DA | *n/p* | **DA** | ŠEMA POTVRĐENA |
| `status` | DA | *n/p* | **DA** | ŠEMA POTVRĐENA |
| ostalih 16 kolona | DA | *n/p* | **DA** | ŠEMA POTVRĐENA |
| 4 indeksa | DA | *n/p* | **NEIZMERENO** | otvoreno (Q2) |
| trigger + funkcija | DA | *n/p* | **NEIZMERENO** | otvoreno (Q3/Q4) |

Klasična `MATCH / DRIFT` klasifikacija ovde ne važi kako je zamišljena, jer
srednja kolona ne postoji ni za jednu migraciju u projektu.

---

# ALTERNATIVNI IZVOR — PROVERENO (§6)

Pitanje: **da li je neka druga migracija uvela iste kolone?**

| Migracija | Dodaje li ove kolone na `ai_forensics`? |
|---|---|
| `043_security_bulletproof` | NE — kreira tabelu sa **samo** legacy skupom od 10 |
| `090_ledger_correlation_id` | NE — **nijedan** `ADD COLUMN` |
| `112_feature_usage_provenance` | NE — dodaje `predmet_id`/`correlation_id` na **`feature_usage_log`**, drugu tabelu |
| `089` | **DA — jedini** |

Ovo je bila najozbiljnija zamka: 112 je **potvrđeno pokrenuta**, i njeni nazivi
kolona su identični. Da nisam proverio ciljnu tabelu, zaključio bih da 112
objašnjava šemu.

**Zaključak: 089 je jedini artefakt u repou koji proizvodi ovu šemu.**
To i dalje ne isključuje ručni `ALTER` sa istim DDL-om — v. §DRIFT.

---

# RUNTIME PROVENANCE

```
putanja:  AI poziv → shared/ai_client.py (zakrpa SDK klasa)
          → _capture_chat_provenance
          → security/ai_forensics.py::log_provenance_from_wrapper
          → supa.table("ai_forensics").insert(...)
```

Runtime upisuje **29 kolona** = 19 (089) + 10 (043).
**Svih 29 potvrđeno postoji u produkciji.**

```
fallback:  uski legacy skup, SAMO na „kolona ne postoji" (SQLSTATE 42703)
tih?       NE — od BETA-HARDENING-002 degradacija je merljiva, lepljiva,
           logovana kao ERROR i izložena na /health
health:    {"prosirena_sema": null|true|false, "migracija_089_potvrdjena": bool,
            "degradiranih_upisa": int, "izgubljene_kolone": [...]}
```

Pošto sve kolone postoje, **uska grana se u produkciji ne aktivira** — što je
tačno ono što `GT-001` traži.

---

# DRIFT

## NONE DETECTED — na dimenziji koju sam mogao da izmerim

Nijedna očekivana kolona ne nedostaje. Nema neusklađenosti između onoga što
runtime upisuje i onoga što šema nudi.

## NEIZMERENO (ne isto što i „nema drifta")

| Šta | Zašto nije izmereno |
|---|---|
| 4 indeksa | PostgREST ih ne izlaže |
| `trg_protect_ai_forensics_update` | provera bi zahtevala `UPDATE` — **mutacija**, zabranjena ovim sprintom |
| tipovi kolona / `NOT NULL` / `DEFAULT` | PostgREST ne izlaže metapodatke |

**Zašto je to važno, a nije blocker za GT-001:** ako kolone postoje a indeksi ne,
šema radi ali njeno **poreklo nije 089** (ručni `ALTER`). To je razlika između
*SCHEMA CAPABILITY* (dokazana) i *MIGRATION STATUS* (nije).

**SAFE NEXT ACTION:** `docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql` —
četiri `SELECT` upita, ništa ne piše. Pokrenuti u SQL Editoru i nalepiti izlaz.
Prati postojeći obrazac (`VERIFY_MIGRATION_108_READONLY.sql`,
`VERIFY_MIGRATIONS_102_103_READONLY.sql`) — nije uveden nov mehanizam.

---

# SECURITY

| Provera | Ishod |
|---|---|
| kredencijal ispisan/logovan | **NE** — nijedan URL, ključ, lozinka ni token |
| `/health` izlaže tekst izuzetka (P6b) | **NE** — vraća samo `{"dostupno": false}`; jedini pogodak na `str(_exc)[:120]` je u **komentaru** koji objašnjava popravku |
| sirov izuzetak sa tajnom | **NE** — detalj ide u serverski log preko `exc_info` |
| nova izloženost | **nijedna** |

Sonda je poredila okruženje bez otkrivanja vrednosti:
`sonda URL == runtime URL: True`, otisak `b1397b32e30e`.

---

# CHANGES

```
Production files:      NONE
Migrations executed:   NONE
Migrations created:    NONE
```

Novi fajlovi (oba dokumentacija, nula uticaja na runtime):
```
docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql
docs/beta_hardening/BETA_CLOSURE_089_FINAL.md
```

---

# TESTS

```
targeted (provenance/hardening):  47 passed / 1 skipped
```

**Nijedan nov test nije dodat.** Namerno: mandat (§12) zabranjuje testove koji
proveravaju „migration fajl postoji" ili „ime kolone se pojavljuje u izvoru", a
jedini pravi dokaz ovde je **read-only sonda produkcione baze**, koja ne sme da
uđe u suitu (pogađala bi produkciju na svakom pokretanju).

Postojeći test `test_gt001_*` iz BETA-HARDENING-002 već pokriva **ponašanje**
runtime-a u obe grane (šema puna / šema legacy) nad stub bazom, i to je ispravna
podela: **ponašanje se testira, stanje produkcije se verifikuje.**

---

# SECOND-EYE REVIEW

Pitanje: *„Postoji li način da proglasimo 089 primenjenom iako produkciona šema
nije kompatibilna?"*

| Scenario | Ishod |
|---|---|
| migration history mismatch | **n/p** — mehanizam ne postoji ni za jednu migraciju |
| schema drift | kolone: isključeno merenjem. Indeksi/trigger: **neizmereno** |
| duplicate migration | isključeno — 043/090/112 provereni po **ciljnoj tabeli** |
| ručna izmena šeme | **NIJE ISKLJUČENO** — glavni preostali scenario |
| legacy tabela / dvojnik | isključeno — `ai_forensics_legacy`, `ai_provenance`, `forensics` **ne postoje** |
| pogrešna baza / okruženje | isključeno — sonda i runtime dele isti `SUPABASE_URL` |
| pogrešan `search_path` | isključeno — isti PostgREST klijent kao runtime, `public` |
| pogrešna provenance tabela | isključeno — runtime piše u `ai_forensics`, sonda merila `ai_forensics` |
| stara lokalna baza | isključeno — nema lokalne baze u toku |
| CI-only stanje | isključeno — nijedan workflow ne primenjuje migracije |

**Neobjašnjen scenario: jedan** — ručni `ALTER` umesto 089. Zato ne GREEN.

---

# FINAL GT-001 STATUS

## OPEN — ali sa bitno promenjenim sadržajem

Ono što je `GT-001` značio do sada:

> „Provenance runtime zavisi od migracije 089, a stvarno stanje produkcione
> šeme **nije potvrđeno** — sistem može mesecima tiho pisati redove bez join
> ključa i niko to neće znati."

**Taj rizik više ne postoji.** Šema je izmerena: svih 29 kolona koje runtime
upisuje postoje. Uska grana se ne aktivira. A i da se aktivira, od
BETA-HARDENING-002 to više ne bi bilo tiho.

Ostatak koji drži `GT-001` otvorenim je uži i drugačiji:

1. **poreklo šeme** — 089 ili ručni `ALTER` (Q2 to razrešava),
2. **nepromenljivost** — trigger nije verifikovan (Q3/Q4).

Druga stavka je zaseban ugovor: bez trigera se provenance red može **tiho
prepisati**, čime prestaje da bude upotrebljiv kao dokaz — što je nezavisno od
toga da li ima join ključ.

---

# FINAL QUESTION

> *„Da li sada imamo dokaz, a ne pretpostavku, da produkciona provenance šema
> odgovara onome što Vindex runtime očekuje?"*

## **DA.**

**Dokaz:** read-only sonda produkcione baze (`select(<kolona>).limit(0)`,
nijedan red pročitan) potvrdila je da svih **19 kolona iz 089** i svih **10
legacy kolona iz 043** postoje na tabeli `ai_forensics` — dakle tačno onih **29
kolona** koje `security/ai_forensics.py::log_provenance_from_wrapper` upisuje.
Identitet okruženja je nezavisno potvrđen (isti `SUPABASE_URL` kao runtime,
ista tabela, bez legacy dvojnika), a 089 je forenzički utvrđena kao **jedini
artefakt u repou** koji tu šemu proizvodi.

**Šta i dalje nedostaje** (i zato verdikt nije GREEN): dokaz da su tu šemu
napravili **089 i njena četiri indeksa**, a ne ručni `ALTER`, i dokaz da
`UPDATE`-blokirajući trigger stvarno postoji. Oboje zatvara jedan `SELECT`
prolaz — `docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql` — koji ne piše
ništa.
