# SCHEMA RECON — `api_costs` · `ratio_decidendi` · `reported_errors`

**Tip sprinta:** čisto forenzički. Nula izmena koda, nula migracija, nula tabela.
**Baseline:** `09536c92`
**Datum:** 2026-08-13
**Sonde:** READ-ONLY PostgREST (OpenAPI schema dump + `Prefer: count=exact` + kolonske
`select` sonde). Nijedan red podataka nije preuzet; samo imena kolona, tipovi i brojači.

---

## 0. IZMERENO STANJE (dokaz, ne tvrdnja)

### 0.1 Tri mete — potvrđeno odsutne

Sonda: `GET /rest/v1/<tabela>?select=*&limit=1` sa `service_role` ključem.

| Tabela | HTTP | PostgREST kod | Poruka |
|---|---|---|---|
| `public.api_costs` | **404** | `PGRST205` | `Could not find the table 'public.api_costs' in the schema cache` |
| `public.ratio_decidendi` | **404** | `PGRST205` | `Could not find the table 'public.ratio_decidendi' in the schema cache` |
| `public.reported_errors` | **404** | `PGRST205` | `Could not find the table 'public.reported_errors' in the schema cache` |

Ukupno tabela vidljivih PostgREST-u: **166**. Nijedna od tri nije među njima.

**Nijedna migracija ih ne kreira.** `grep -l 'api_costs\|ratio_decidendi\|reported_errors'
migrations/` → **0 pogodaka** preko svih 103 `.sql` fajla u `migrations/`. Jedini izvor
`CREATE TABLE` definicija je nenumerisani `supabase_migration.sql` (234 linije), čije je
izvršavanje stalo posle linije ~113: `conversations` (l.93) **postoji**, `reported_errors`
(l.115) **ne postoji**.

> Ovo nije migration drift. Ovo je **nedostajuća šema**: definicija postoji samo u
> fajlu koji nikada nije bio deo numerisanog lanca, i koji je zaustavljen na pola.

### 0.2 Postojeće tabele koje su kandidati za ekvivalent (izmereno)

| Tabela | Kolone | Redova u produkciji |
|---|---|---|
| `ai_forensics` | 38 | **124** |
| `feature_usage_log` | 12 | **0** |
| `feature_usage` | 8 | 9 |
| `usage_events` | 7 | 2 906 |
| `audit_log` | 8 | 297 |
| `response_audit` | 13 | 432 |
| `ai_cache` | 5 | 16 |
| `feedback` | **4** | **1** |
| `support_tickets` | 8 | 1 |
| `predmet_istorija` | 7 | 144 |
| `conversations` | 7 | 0 |

Kolonski sastav ključnih kandidata (iz PostgREST OpenAPI definicija):

```
ai_forensics(38):  id, user_id, endpoint, model, prompt_hash, documents_count,
                   document_hashes, temperature, max_tokens, input_chars,
                   injection_risk_score, injection_flags, started_at, finished_at,
                   latency_ms, response_hash, tokens_prompt, tokens_completion,
                   prompt_version, tenant_id, predmet_id, document_id, module_name,
                   operation_name, model_provider, model_version, system_prompt_hash,
                   user_prompt_hash, retrieved_context_ids, knowledge_sources,
                   retrieval_query, confidence_score, hallucination_check_result,
                   parent_event_id, correlation_id, audit_reference, status,
                   error_message
                   ↳ NEMA kolonu cost_usd (provereno: 42703 column does not exist)

feature_usage_log(12): id, user_id, feature_key, krediti_potroseni, ai_model,
                   tokens_prompt, tokens_completion, latency_ms, estimated_cost_usd,
                   created_at, predmet_id, correlation_id

ai_cache(5):       cache_key, odgovor, metadata, created_at, expires_at

feedback(4):       id, user_id, tip, created_at
                   ↳ NEMA q_hash, NEMA pitanje, NEMA odgovor (sve tri: 42703)
```

### 0.3 Popunjenost `ai_forensics` (ključno za §5 kod `api_costs`)

| Filter | Redova |
|---|---|
| ukupno | 124 |
| `tokens_prompt IS NOT NULL` | **124 (100 %)** |
| `tokens_prompt > 0` | **124 (100 %)** |
| `tokens_completion > 0` | 66 (ostalo su embedding pozivi — legitimno 0) |
| `model IS NOT NULL` | **124 (100 %)** |
| `user_id IS NOT NULL` | **124 (100 %)** |
| `endpoint IS NOT NULL` | **124 (100 %)** |
| `correlation_id IS NOT NULL` | **124 (100 %)** |
| `tenant_id IS NOT NULL` | **0 (0 %)** |

---

# TABELA 1 — `public.api_costs`

## §1 INVENTAR REFERENCI

| # | FILE | LINE | FUNCTION | OPERATION | R/W | Kolone | Ponašanje pri grešci | Posledica za korisnika |
|---|---|---|---|---|---|---|---|---|
| 1 | `shared/cost.py` | 97–107 | `log_cost_to_db` | `.table("api_costs").insert(...)` | **WRITE** | `user_id, endpoint, prompt_tokens, completion_tokens, total_tokens, cost_usd, model, calls` | `except Exception:` → `logger.warning("[COST] DB log neuspešan — ne blokira odgovor")` | **Nijedna.** Upis je `asyncio.create_task(...)` — nikad se ne čeka, nikad se ne vidi. |
| 2 | `shared/cost.py` | 55, 60 | `estimate_cost` | komentar/log koji **imenuje** `api_costs` | — | — | `logger.warning` na nepoznat model | — |
| 3 | `supabase_migration.sql` | 199–234 | — | `CREATE TABLE` + 2 indeksa + RLS + `GRANT SELECT, INSERT` | DDL | v. §2 | nikad izvršeno | — |

**Nema nijednog READ-a.** Nijedan endpoint, izveštaj, admin panel ni skripta nikad ne
čitaju `api_costs`. Jedini „čitalac" je zakomentarisani admin upit u
`supabase_migration.sql:228–234`.

### 1.1 Pozivaoci `log_cost_to_db` (4, svi živi)

| FILE:LINE | endpoint string | Prati li `UsageService.consume`? |
|---|---|---|
| `api.py:3391` | `"pitanje"` | da (pre-deduct + refund) |
| `routers/strategija.py:729` | `"kompletna_analiza"` | da (`multiplier` iz registry-ja) |
| `routers/strategija.py:913` | `"strategija_v2"` | da (`multiplier=1`) |
| `routers/hearing_cc.py:468` | `"hearing_command_center"` | da (`hearing_prep`) |

### 1.2 Pozivaoci `record_cost` — samo 3, i to je drugi kvar

| FILE:LINE | pokriva |
|---|---|
| `main.py:2316` | `_pozovi_openai` → put `ask_agent` → endpoint `"pitanje"` |
| `strategija.py:833` | `orkestrator_kompletna_analiza_sync` → `"kompletna_analiza"` |
| `strategija.py:857` | isto |

`routers/hearing_cc.py:386,570` koristi **sirov** `AsyncOpenAI(...)` — bez `record_cost`.
`routers/strategija.py:81` (`_pozovi_strategija_v2_api`) — takođe sirov, bez `record_cost`.

> **NALAZ AC-1 (drugi red).** Čak i da `api_costs` postoji, **2 od 4** poziva
> (`strategija_v2`, `hearing_command_center`) upisala bi **nulu redova**: akumulator
> `_request_costs` ostaje prazan, pa `log_cost_to_db` izlazi na `shared/cost.py:85`
> (`if not costs: return`) pre nego što uopšte dodirne bazu. Praćenje troška je
> **dvostruko mrtvo** — nema tabele *i* nema instrumentacije na polovini ruta.

## §2 WRITE UGOVOR vs. `CREATE TABLE`

| Polje | Izvor u kodu | Python tip | `supabase_migration.sql:199` | Poklapa se? |
|---|---|---|---|---|
| `user_id` | `user["user_id"]` / `uid` | `str` (UUID) | `UUID REFERENCES auth.users(id) ON DELETE SET NULL` | ✓ |
| `endpoint` | literal (`"pitanje"`, …) | `str` | `TEXT NOT NULL` | ✓ |
| `prompt_tokens` | `get_request_total()[0]` | `int` | `INTEGER NOT NULL DEFAULT 0` | ✓ |
| `completion_tokens` | `get_request_total()[1]` | `int` | `INTEGER NOT NULL DEFAULT 0` | ✓ |
| `total_tokens` | `p + c` (izračunato u Pythonu) | `int` | `INTEGER NOT NULL DEFAULT 0` | ✓ — ali **denormalizovano**, nije generated column |
| `cost_usd` | `estimate_cost()` sumirano | `float` | `NUMERIC(10,6) NOT NULL DEFAULT 0` | ⚠ `float` → `NUMERIC(10,6)`; `round(...,6)` u kodu poklapa skalu, ali **preciznost je odgovornost Pythona, ne baze** |
| `model` | `dominant_model` (argmax po tokenima) | `str` | `TEXT NOT NULL DEFAULT 'gpt-4o'` | ⚠ **semantički gubitak**: request sa više modela svede se na jedan „dominantni" |
| `calls` | `len(costs)` | `int` | `INTEGER NOT NULL DEFAULT 1` | ✓ |
| `id`, `created_at` | ne šalju se | — | `DEFAULT gen_random_uuid()` / `NOW()` | ✓ |

**Nema UNIQUE, nema idempotencije.** Retry istog zahteva bi dao duplirani red.
Očekuje li kod uspeh? **Ne** — izuzetak se guta bez ikakve posledice.

> **NALAZ AC-2.** `dominant_model` je *lossy*. `"kompletna_analiza"` pokreće 6–8 GPT
> poziva koji mešaju `gpt-4o` i `gpt-4o-mini`; `api_costs` bi zabeležio jedan model po
> zahtevu. `ai_forensics` beleži **model po pozivu** — strogo bogatije.

## §3 READ UGOVOR

**Ne postoji.** Nula read-referenci u celom repou (produkcija, testovi, skripte).
Namera je dokumentovana samo kao SQL komentar (`supabase_migration.sql:228–234`):
`SELECT date_trunc('month', created_at), SUM(cost_usd), SUM(total_tokens), COUNT(*)`.

## §4 GRAF VEZA

| Ka | Status | Dokaz |
|---|---|---|
| `auth.users(id)` | **INFERRED** | FK deklarisan u `supabase_migration.sql:201`, ali tabela ne postoji → FK ne postoji u produkciji |
| `predmeti` | **UNKNOWN** | šema nema `predmet_id`; kod ga ne šalje |
| `conversations` | **UNKNOWN** | nema veze |
| `ai_forensics` | **UNKNOWN** | nema `correlation_id` — **ne postoji nijedan način da se red iz `api_costs` spoji sa provenance redom** |
| kancelarije / tenant | **UNKNOWN** | nema `tenant_id`/`firma_id` |
| `audit_log` / `audit_immutable` | **UNKNOWN** | nema veze |

> **NALAZ AC-3.** Šema iz `supabase_migration.sql` je **arhitektonski zastarela** u odnosu
> na ono što platforma danas ima. Nema `correlation_id`, nema `predmet_id`, nema
> `tenant_id` — tri polja koja `ai_forensics` i `feature_usage_log` (migracija 112) danas
> imaju i popunjavaju. Kreiranje ove tabele kakva jeste uvelo bi **četvrti** silos
> telemetrije koji se ne spaja ni sa jednim postojećim.

## §5 POSTOJEĆI EKVIVALENT — **POSTOJI, I BOLJI JE**

### 5.1 `ai_forensics` — izmereni tokeni po pozivu ✅

38 kolona, **124 reda**, i **100 % njih ima `tokens_prompt > 0`, `model`, `endpoint`,
`user_id`, `correlation_id`**. Piše ga `security/ai_forensics.py` (linije 129, 179, 377,
411) preko `shared/ai_client.py:416,489` — dakle na **svaki** AI poziv koji ide kroz
zajednički klijent, uključujući Cohere rerank (`app/services/retrieve.py:601`).

**Trošak je izvodljiv bez ijedne nove tabele:**

```
cost_usd  =  tokens_prompt/1000 * _PRICES[model]["input"]
           + tokens_completion/1000 * _PRICES[model]["output"]
```

`shared/cost.py::estimate_cost()` je već tačno ta funkcija. Presek po korisniku, po
endpointu, po mesecu, po modelu, **po predmetu** (`predmet_id`) i po zahtevu
(`correlation_id`) je jedan `GROUP BY` nad postojećim redovima.

**Šta `ai_forensics` daje što `api_costs` ne bi:** `predmet_id`, `correlation_id`,
`module_name`/`operation_name`, `latency_ms`, `model_provider`/`model_version`,
`status`/`error_message`, i **model po pojedinačnom pozivu** umesto „dominantnog".

**Šta `api_costs` daje što `ai_forensics` ne daje:** samo **materijalizovanu**
`cost_usd` kolonu. To je izvedena vrednost — pogodnost izveštavanja, ne podatak.
(Provereno: `ai_forensics.cost_usd` → `42703 column does not exist`.)

### 5.2 `feature_usage_log` — namenski naslednik, ali prazan ⚠

Migracija **065** (`feature_usage_log`) + **112** (`predmet_id`, `correlation_id`) je
**dizajnirani naslednik** `api_costs`-a: `user_id, feature_key, krediti_potroseni,
ai_model, tokens_prompt, tokens_completion, latency_ms, estimated_cost_usd, created_at,
predmet_id, correlation_id`. Piše ga `shared/usage.py:401` (`_log_usage_event`), a
**čita ga živi admin endpoint** `routers/product_intelligence.py:716–733`
(`/admin/pi/revenue-intelligence` → `ai_cost_mtd_usd`, `ai_cost_today_usd`, Gross
Profit/Margin po funkciji).

Ali: **0 redova u produkciji.**

> **NALAZ AC-4 (kritičan, izvan prvobitnog opsega).** Postoji potpuno ožičen,
> pročitan, dokumentovan sloj troška — `UsageService.consume()` → `feature_usage_log`
> → Revenue Intelligence — i on ima **nula redova** iako `feature_usage` (agregat, ista
> `consume()` putanja) ima 9, `ai_forensics` 124, a `usage_events` 2 906. `consume()`
> se očigledno izvršava. `_log_usage_event` je poslednji korak u `consume()` i ceo mu je
> `except` na `logger.debug` nivou (`shared/usage.py:427`) — dakle otkaz je nevidljiv i
> u logovima na INFO nivou. **Ovo zahteva zasebnu istragu**; naznačeno ovde jer direktno
> menja preporuku za `api_costs` (ekvivalent postoji na papiru, ali danas ne teče).
>
> Napomena: `estimated_cost_usd` koji `consume()` upisuje je **statička procena iz
> `feature_registry`** (`shared/usage.py:487`: `est_cost = policy.get("estimated_cost_usd")`),
> **ne** izmereni tokeni. Izmereni tokeni postoje samo u `ai_forensics`.

### 5.3 Ostali

| Tabela | Pokriva li trošak? |
|---|---|
| `feature_usage` (9 redova) | ne — samo brojači `broj_koriscenja` / `krediti_potroseni` po danu |
| `usage_events` (2 906) | ne — `feature/action/metadata`, bez tokena i cene |
| `audit_log` (297) | ne — `akcija/q_hash/ip_hash` |
| `response_audit` (432) | ne — `confidence/top_score/latency_ms`, bez tokena |

## §6 MRTAV KOD

| Simbol | Status |
|---|---|
| `begin_cost_tracking()` | **LIVE** (4 poziva) |
| `record_cost()` | **LIVE** (3 poziva, pokriva 2/4 ruta) |
| `estimate_cost()` | **LIVE** — ali samo unutar `get_request_total()` |
| `get_request_total()` | **CONDITIONALLY LIVE** — zove ga samo `log_cost_to_db` |
| `log_cost_to_db()` | **LIVE POZVAN / DEAD EFEKAT** — izvršava se 4× po putanjama, uvek bez ijedne posledice |
| **tabela `api_costs`** | **DEAD** — 1 write-referenca, 0 read-referenci, 0 redova, tabela ne postoji |

## §7 SEMANTIKA OTKAZA (najvažnije)

Tačan lanac, korak po korak:

1. `asyncio.create_task(log_cost_to_db(uid, endpoint))` — **fire-and-forget**. Rezultat
   task-a se nikad ne `await`-uje niti se hvata; `Task exception was never retrieved`
   se ne javlja jer izuzetak biva uhvaćen unutra.
2. Za `strategija_v2` i `hearing_command_center`: `costs` je prazna lista →
   **`return` na `cost.py:85`**, baza se nikad ne dodirne. Tiho, bez ijednog loga.
3. Za `pitanje` i `kompletna_analiza`: `_get_supa().table("api_costs").insert(...)`
   → PostgREST **HTTP 404 `PGRST205`** → `postgrest.exceptions.APIError`.
4. `except Exception:` → `logger.warning("[COST] DB log neuspešan — ne blokira odgovor")`.
   **Poruka ne sadrži ni ime tabele, ni HTTP kod, ni tekst PostgREST greške**, pa je i
   u logu neraspoznatljiva od prolazne mrežne greške.
5. `_sentry_capture` se **NE** poziva → **nema Sentry događaja**. Za razliku od
   `praksa.py:323,335` gde se isti razred greške *šalje* u Sentry.

| Pitanje | Odgovor |
|---|---|
| Koji izuzetak se guta? | `postgrest.exceptions.APIError` (`PGRST205`, HTTP 404) |
| Koja operacija pada? | jedini `INSERT`; ceo zapis o trošku |
| Koje stanje se gubi? | tokeni, USD, model, broj poziva — **po zahtevu, nepovratno** (ContextVar umre sa zahtevom) |
| Vidi li korisnik išta? | **Ne.** Nula uticaja na odgovor, latenciju, kredite. |
| Postaje li trošak nemerljiv? | **Iz `api_costs` — da, 100 %.** **Iz `ai_forensics` — ne**, izmereni tokeni postoje za sve pozive koji idu kroz `shared/ai_client.py` (124 reda, 100 % popunjeno). |
| Naplata? | **Ne pogađa.** Korisniku se naplaćuje u **kreditima** preko `deduct_n_credits` / `user_credits` (migracija 107) — potpuno nezavisno od `api_costs`. Nijedan evro ni kredit ne zavisi od ove tabele. |
| Governance / COGS? | **Pogađa.** `/admin/pi/revenue-intelligence` računa Gross Margin iz `feature_usage_log`, ne iz `api_costs`; ali pošto je i on prazan (§5.2), **osnivač danas nema nijedan izvor stvarnog COGS-a osim ručnog izračuna nad `ai_forensics`.** |
| Audit? | **Ne pogađa.** Audit trag AI poziva je `ai_forensics` + `audit_immutable`, oba žive. |

**Zaključna ocena:** otkaz je **potpuno tih i potpuno bezbolan za korisnika**, i to je
upravo ono što ga je održalo nevidljivim od prvog dana. Ne postoji nijedan test,
nijedan alarm i nijedan ekran koji bi ga otkrio.

## §8 PROIZVODNI UGOVOR

- **Poslovna sposobnost:** interno merenje AI COGS-a po korisniku/endpointu/mesecu.
- **Vidljivo korisniku:** **NE** — `migrations/065:35` izričito kaže
  *„NIKAD prikazano korisniku — isključivo za founder-ovu internu profitabilnost"*.
- **Obećano korisniku:** ne.
- **Nužno za betu:** ne za funkcionisanje; **da** za kontrolu potrošnje tokom pilota.
- **Klasifikacija:** **POST-BETA** za tabelu; **BETA-IMPORTANT** za sposobnost (i
  sposobnost je već izgrađena drugde — v. §5).

## §9 BEZBEDNOST

| Osa | Ocena | Obrazloženje |
|---|---|---|
| Poverljivost | **NONE** | ne čuva sadržaj — samo brojače i ime endpointa |
| Integritet | **P3** | gubitak telemetrije, nema uticaja na poslovne podatke |
| Izolacija tenanta | **P2** | predložena šema **nema** `tenant_id`; kreiranje kakva jeste stvorilo bi tabelu bez tenant granice u proizvodu koji ide ka kancelarijama |
| Auditabilnost | **P3** | audit AI poziva pokriva `ai_forensics` |
| GDPR / ZZPL | **NONE** | `SEC002_DATA_RETENTION_ANALYSIS.md:104` klasifikuje kao internu telemetriju bez klijentskog sadržaja |
| Naplata | **NONE** | naplata ide kroz `user_credits`, nezavisno |
| AI governance | **P2** | nemogućnost dokazivanja stvarnog troška po modelu je governance rupa — ali rešiva iz `ai_forensics` |

**Najviši prioritet: P2.**

## §10 PREPORUKA

> ## `REUSE_EXISTING_SCHEMA`

**Ne kreirati `api_costs`.** Domen je već pokriven, i to bogatije:

1. **Izmereni tokeni + model + endpoint + user + predmet + correlation** već postoje u
   `ai_forensics` (124/124 popunjeno). `cost_usd` je izvedena vrednost —
   `shared/cost.py::estimate_cost()` je već ta formula.
2. **Namenski agregacioni sloj** `feature_usage_log` već postoji (migracije 065 + 112),
   ima `estimated_cost_usd`, i **već ga čita živi admin endpoint**
   (`routers/product_intelligence.py:716`).
3. Kreiranje `api_costs` kakav je definisan u `supabase_migration.sql` dodalo bi
   **četvrti** silos telemetrije, bez `correlation_id`/`predmet_id`/`tenant_id`, koji
   se ne spaja ni sa jednim postojećim (§4, NALAZ AC-3).

**Uslovljeno prethodnim razrešenjem NALAZA AC-4** (`feature_usage_log` = 0 redova). Dok
se to ne razreši, „ekvivalent postoji" je tačno na nivou šeme, a ne na nivou podataka.

**Sporedno, za posebnu odluku (ne implementirati sada):** `shared/cost.py` je danas
mrtav sloj koji troši ContextVar-e i pravi 4 task-a po zahtevu bez ijednog efekta —
kandidat za `REMOVE_DEAD_CODE` **tek nakon** što se izmereni tokeni dovedu u
`feature_usage_log`; do tada `record_cost` ostaje jedini mehanizam koji uopšte
akumulira tokene po zahtevu.

---

# TABELA 2 — `public.ratio_decidendi`

## §1 INVENTAR REFERENCI

| # | FILE | LINE | FUNCTION | OPERATION | R/W | Kolone | Ponašanje pri grešci | Posledica |
|---|---|---|---|---|---|---|---|---|
| 1 | `routers/praksa.py` | 310–315 | `_get_ratio_from_cache` | `.select("ratio").eq("decision_number", dn).limit(1)` | **READ** | `ratio`, `decision_number` | `_sentry_capture(e)` + `logger.debug` → `return None` | keš **uvek** promašuje |
| 2 | `routers/praksa.py` | 330–333 | `_save_ratio_to_cache` | `.upsert({...}, on_conflict="decision_number")` | **WRITE** | `decision_number`, `ratio` | `_sentry_capture(e)` + `logger.warning` | rezultat se ne čuva |
| 3 | `supabase_migration.sql` | 167–184 | — | `CREATE TABLE` + UNIQUE + RLS + GRANT | DDL | v. §2 | nikad izvršeno | — |

**Lanac pozivalaca (svi LIVE):**

```
static/vindex.js:8500  praksa_render_results()  → praksa_fetch_ratios(decisions, base)
static/vindex.js:8755  fetch POST /api/praksa/ratio        (lista rezultata pretrage)
static/vindex.js:8921  fetch POST /api/praksa/ratio        (grupisani prikaz)
        ↓
routers/praksa.py:569  @router.post("/api/praksa/ratio")  @limiter.limit("20/minute")
routers/praksa.py:586  asyncio.to_thread(_extract_ratio_sync, dn, text)   ← paralelno, do 20
routers/praksa.py:364  _get_ratio_from_cache(dn)          ← 404, uvek None
routers/praksa.py:375  _pozovi_ratio_api(...)             ← gpt-4o-mini, PLAĆENO
routers/praksa.py:383  _save_ratio_to_cache(dn, ratio)    ← 404, gubi se
```

`praksa_fetch_ratios` se okida **automatski iz `praksa_render_results()`** — dakle na
**svako** iscrtavanje rezultata pretrage prakse, uključujući „učitaj još" (`append`).
Korisnik ne bira da pokrene ratio — on se pokreće sam.

## §2 WRITE UGOVOR vs. `CREATE TABLE`

| Polje | Izvor | Tip u kodu | `supabase_migration.sql:167` | Poklapa se? |
|---|---|---|---|---|
| `decision_number` | `d["decision_number"].strip()` (iz Pinecone metadata) | `str` | `TEXT NOT NULL`, `UNIQUE` | ✓ |
| `ratio` | izlaz `gpt-4o-mini`, ≤ 220 tokena | `str` | `TEXT NOT NULL` | ✓ |
| `id`, `created_at` | ne šalju se | — | `DEFAULT gen_random_uuid()` / `NOW()` | ✓ |

`on_conflict="decision_number"` **zahteva** `CONSTRAINT ratio_decidendi_dn_key UNIQUE
(decision_number)` (l.172) — **postoji u definiciji**. Ugovor je **potpuno usklađen**.

Očekuje li kod uspeh? Ne — `_extract_ratio_sync` je dokumentovan kao „never throws".
**Ali za razliku od `api_costs`, greška ide u Sentry** (`_sentry_capture`) — dakle
signal postoji, samo ga niko nije povezao sa uzrokom.

> **NALAZ RD-1.** Nema `expires_at`. `ai_cache` (postojeći, živi keš) ima TTL. Ratio
> ekstrakcija je deterministička po ulaznom tekstu, ali **promena `_RATIO_SYSTEM_PROMPT`
> ili modela ne bi invalidirala nijedan keširan red** — nema `prompt_version` ni
> `model` kolone. To je latentna „stale cache" rupa u samoj definiciji.

## §3 READ UGOVOR

| Osa | Vrednost |
|---|---|
| Kolone | `ratio` |
| Filter | `decision_number = <str>` (tačno poklapanje) |
| Sortiranje | nema |
| Agregacija | nema |
| Kardinalnost | `.limit(1)` — očekuje **0 ili 1** |
| `r.data` neprazno | **HIT** → vrati keširan ratio, **0 USD, ~50 ms** |
| `r.data` prazno | **MISS** → GPT poziv (`praksa.py:316` — namerno ne baca) |
| izuzetak | **ono što se danas dešava** → `PGRST205` → Sentry + `debug` log → `None` → tretira se kao MISS |

> **NALAZ RD-2.** Kod eksplicitno razlikuje „prazan keš" od „greška keša"
> (`praksa.py:319–322` komentar), i grešku šalje u Sentry. Ali oba puta vode u
> **isti ishod** (`return None`) — pa se razlika nikad ne materijalizuje u ponašanju.
> Sentry je od prvog dana primao ovaj događaj na **svaku odluku u svakoj pretrazi**;
> pretpostavka je da je odavno postao šum koji se ignoriše.

## §4 GRAF VEZA

| Ka | Status | Dokaz |
|---|---|---|
| `users` / `profiles` | **VERIFIED: NEMA** — i to je ispravno | `docs/lambda/CACHE_ISOLATION_REPORT.md:78`: *„CERTIFIED — caches PUBLIC jurisprudence, correctly global"* |
| `predmeti` | **UNKNOWN** — nema veze | ratio je svojstvo presude, ne predmeta |
| Pinecone `sudska_praksa` / `upravna_praksa` | **INFERRED** | `decision_number` je logički ključ ka Pinecone metadata (`praksa.py:431`); nije FK i ne može biti |
| `ai_forensics` | **INFERRED, danas prekinuto** | `_pozovi_ratio_api` (`praksa.py:345`) instancira **sirov** `OpenAI(...)`, ne `shared/ai_client` → ovi pozivi **ne dobijaju provenance red** |
| audit / kancelarije | **UNKNOWN** | nema veze; javna sudska praksa |

> **NALAZ RD-3.** Ratio GPT pozivi zaobilaze `shared/ai_client.py`, pa **ne postoje ni u
> `ai_forensics`**. Njihov trošak je nevidljiv u *svakom* postojećem sloju telemetrije.
> Kombinovano sa §7, to znači da je najskuplji ponavljajući gubitak na platformi
> istovremeno i najmanje vidljiv.

## §5 POSTOJEĆI EKVIVALENT

| Kandidat | Kolone | Pokriva? | Obrazloženje |
|---|---|---|---|
| **`ai_cache`** | `cache_key, odgovor, metadata, created_at, expires_at` | **DELIMIČNO — jedini realan kandidat** | Generički KV keš sa TTL-om, **16 živih redova**, service-role-only (`main.py:180`: `CREATE POLICY "service_only" ... USING (false)`). `cache_key = "ratio:" + decision_number`, `odgovor = ratio`, `metadata = {model, prompt_version}`. Semantički odgovara. |
| `case_genome` | — | **ne postoji** u produkciji (provereno) | — |
| `predmet_istorija` | `predmet_id, user_id, pitanje, odgovor, confidence` | **NE** | per-korisnik, per-predmet; ratio je **globalan, javni** podatak — upis tamo bi ga duplirao po korisniku i uveo lažnu tenant granicu |
| `response_audit` | `query_hash, confidence, top_score…` | **NE** | audit metrika, ne sadržaj; nema polje za tekst |
| `ai_forensics` | — | **NE** | čuva **heševe** (`response_hash`), ne sadržaj — po dizajnu |

**Ključna razlika u odnosu na `ai_costs`:** ovde ekvivalent (`ai_cache`) nosi **različit
ugovor za promašaj**. `ai_cache` je keyed na `cache_key` bez UNIQUE-a na poslovnom polju
i ima `expires_at` koji `_get_ratio_from_cache` ne poznaje. Reuse je **moguć ali nije
besplatan** — traži izmenu `praksa.py` (rewire), ne samo migraciju.

## §6 MRTAV KOD

| Simbol | Status |
|---|---|
| `praksa_fetch_ratios` (JS) | **LIVE** — auto-okida iz `praksa_render_results` |
| `POST /api/praksa/ratio` | **LIVE** — 2 frontend pozivaoca, rate-limit 20/min |
| `_extract_ratio_sync` | **LIVE** |
| `_pozovi_ratio_api` | **LIVE** — plaćeni `gpt-4o-mini` poziv |
| `_get_ratio_from_cache` | **LIVE POZVAN / DEAD EFEKAT** — uvek vrati `None` |
| `_save_ratio_to_cache` | **LIVE POZVAN / DEAD EFEKAT** — uvek padne |
| **tabela `ratio_decidendi`** | **DEAD (nepostojeća), ali funkcija koju opslužuje je LIVE i plaćena** |

## §7 SEMANTIKA OTKAZA — **ponovljeni plaćeni LLM poziv**

**Da. Otkaz znači ponovljeni skupi LLM poziv, i to na najgori mogući način: 100 % promašaj, uvek.**

Kvantifikacija po jednom prikazu rezultata pretrage:

| Osa | Vrednost |
|---|---|
| Odluka po zahtevu | do **20** (`praksa.py:575`) |
| Model | `gpt-4o-mini` (`praksa.py:348`) |
| Ulaz po pozivu | ≤ 6 000 znakova ≈ **~1 800 tokena** |
| Izlaz po pozivu | ≤ **220** tokena (`max_tokens=220`) |
| Cena (`shared/cost.py:25`) | in `$0.00015`/1k, out `$0.0006`/1k |
| **Trošak po odluci** | ≈ `1.8·0.00015 + 0.22·0.0006` ≈ **$0.00040** |
| **Trošak po punom prikazu (20)** | ≈ **$0.008** |
| Očekivana stopa keširanja | **~0 %** (nema tabele) |
| Stopa keširanja da tabela postoji | **visoka** — javna sudska praksa, isti `decision_number` se vraća u svakoj pretrazi po istoj oblasti |

**Učestalost:** okida se na *svako* iscrtavanje rezultata, **bez ikakvog gejta**:
- `praksa_ratio` **ne poziva `UsageService.consume`** — korisniku se **ne naplaćuje
  nijedan kredit**, ne postoji dnevni/mesečni limit, ne postoji cooldown.
- Jedina kočnica je `@limiter.limit("20/minute")` — dakle **do 400 GPT poziva u minuti
  po korisniku** (20 zahteva × 20 odluka).
- `retry` politika: `@llm_retry` na `_pozovi_ratio_api` → neuspeh se i **ponavlja**.

> **NALAZ RD-4 (najveći trošak/rizik u ovom sprintu).** Ovo je **nemetriran, nenaplaćen,
> neograničen i nevidljiv** OpenAI trošak koji bi keš eliminisao za ~90 %+, i koji se
> ne pojavljuje ni u `api_costs` (ne postoji), ni u `feature_usage_log` (nema
> `consume()`), ni u `ai_forensics` (sirov OpenAI klijent — NALAZ RD-3).
> **To je jedina putanja na platformi koja troši novac i ne postoji ni u jednom brojaču.**

**Šta korisnik vidi:** ništa loše — ratio se prikaže, samo sporije (svaki put pun GPT
poziv umesto ~50 ms iz keša) i uz veću šansu za `""` pri GPT otkazu
(`praksa.py:377–380`), kada dobije *„Pravni stav nije utvrđen iz dostavljenog teksta."*
(`vindex.js:8751`) — poruka koja **pogrešno pripisuje uzrok presudi umesto sistemu**.

## §8 PROIZVODNI UGOVOR

- **Poslovna sposobnost:** „Pravni stav suda" ispod svake presude u pretrazi prakse.
- **Vidljivo korisniku:** **DA** — sopstveni UI blok (`.ratio-box`, `.ratio-lbl`
  „Pravni stav suda"), plus filter (`praksa_ratio_filter_update`, `vindex.js:8776`).
- **Obećano:** da — funkcija je vidljivo prisutna i označena.
- **Nužno za betu:** **funkcija — da; tabela — ne.** Funkcija radi i bez keša.
- **Klasifikacija:** **BETA-IMPORTANT** (troškovna i latencijska, ne funkcionalna).

## §9 BEZBEDNOST

| Osa | Ocena | Obrazloženje |
|---|---|---|
| Poverljivost | **NONE** | javna sudska praksa; nema klijentskih podataka. Već certifikovano: `CACHE_ISOLATION_REPORT.md:78` |
| Integritet | **P3** | stale-cache rizik (§2, NALAZ RD-1) tek ako se tabela kreira |
| Izolacija tenanta | **NONE** | globalni keš je **ispravan** za javni sadržaj |
| Auditabilnost | **P2** | ratio GPT pozivi nemaju `ai_forensics` red (NALAZ RD-3) — AI izlaz koji se prikazuje advokatu bez provenance traga |
| GDPR / ZZPL | **NONE** | javni dokumenti |
| Naplata | **P1** | nemetriran, neograničen OpenAI trošak koji raste linearno sa upotrebom pretrage (NALAZ RD-4) |
| AI governance | **P2** | v. auditabilnost |

**Najviši prioritet: P1** (troškovni, ne bezbednosni).

## §10 PREPORUKA

> ## `CREATE_NEW_SCHEMA`

Jedina od tri gde kreiranje tabele nosi jasnu, merljivu i trenutnu korist:

1. **Ugovor koda i `CREATE TABLE` definicije se poklapaju 100 %** (§2) — uključujući
   `UNIQUE (decision_number)` koji `on_conflict` zahteva. Nula rewire posla.
2. **Domen je istinski nov.** `ai_cache` je najbliži, ali reuse traži izmenu
   `praksa.py` i gubi `UNIQUE` semantiku upserta — više posla i više rizika nego
   `CREATE TABLE`.
3. **Trenutna, ponovljiva ušteda** — ~90 % eliminacije jedinog nemetriranog OpenAI
   troška na platformi, plus vidljivo brži prikaz.
4. **Nula bezbednosnog rizika** — globalni keš javne sudske prakse, već certifikovan.

Predložene dopune u odnosu na definiciju iz `supabase_migration.sql` (za odluku
osnivača, **ne implementirano**): `prompt_version TEXT` i `model TEXT` — da promena
`_RATIO_SYSTEM_PROMPT`/modela ne ostavi stale redove (NALAZ RD-1).

Odvojeno, i **nezavisno od tabele**: NALAZ RD-3 (sirov `OpenAI` klijent bez provenance)
i RD-4 (bez `UsageService.consume`) su rupe koje keš **ne** zatvara.

---

# TABELA 3 — `public.reported_errors`

## §0 ISPRAVKA ZADATKA — **NIJE 0 PRODUKCIJSKIH REFERENCI**

Zadatak polazi od pretpostavke *„0 produkcijskih referenci — samo van produkcije"*.

**Ta pretpostavka je netačna.** Postoji **jedna živa produkcijska referenca**, i to
u frontendu, koji je produkcija jednako koliko i backend:

```js
static/vindex.js:8068
    var _upis = await sb.from('reported_errors').insert({
      user_id:         currentUser.id,
      original_prompt: pitanje.substring(0, 4000),
      ai_response:     odgovor.substring(0, 8000),
      timestamp:       new Date().toISOString()
    });
```

Poreklo greške u ranijim izveštajima je razumljivo: `grep` po `*.py` daje 0 pogodaka.
Ali `reported_errors` se **namerno** ne piše iz backenda — piše ga pregledač direktno
preko Supabase `anon` ključa, uz RLS `insert-own` politiku
(`supabase_migration.sql:126`). To je dokumentovano na više mesta
(`docs/security/ACCESS_CONTROL_AUDIT.md:577`, `docs/lambda/RLS_CERTIFICATION.md:81`).

> **`reported_errors` NIJE mrtav kod. `REMOVE_DEAD_CODE` je pogrešna preporuka.**

## §1 INVENTAR REFERENCI

| # | FILE | LINE | FUNCTION | OPERATION | R/W | Kolone | Ponašanje pri grešci | Posledica za korisnika |
|---|---|---|---|---|---|---|---|---|
| 1 | `static/vindex.js` | 8068–8073 | `sendFeedback` | `sb.from('reported_errors').insert(...)` (anon ključ, iz pregledača) | **WRITE** | `user_id, original_prompt, ai_response, timestamp` | `if (_upis.error)` → dugme *„⚠ Nije poslato — pokušajte ponovo"* + `showToast(...,'err')` + `return` | **DA — korisnik vidi grešku.** v. §7 |
| 2 | `static/vindex.js` | 7838 | `_feedbackBar` | `<button id="fb-btn" onclick="sendFeedback(...)">Prijavi netačan odgovor</button>` | UI | — | — | dugme se crta ispod **svakog** AI odgovora |
| 3 | `tests/test_faza15_interaction_closure.py` | 344–362 | `test_r004_uspesna_prijava_zaista_upisuje_sadrzaj` | Playwright, mock `window.__supaInsert` | TEST | proverava sva 4 polja | assert | v. NALAZ RE-2 |
| 4 | `supabase_migration.sql` | 115–133 | — | `CREATE TABLE` + RLS + 2 politike | DDL | v. §2 | nikad izvršeno | — |

**Nema nijednog READ-a.** Namera (`reported_errors_service_select`, l.130) je da osnivač
čita preko `service_role` — ali **ne postoji nijedan admin endpoint ni ekran** koji to
radi. Otvoreno pitanje je već evidentirano: `docs/ux_audit/DUPLICATION_REPORT.md:626`
*„Da li `support_tickets` i `reported_errors` završavaju u istom pregledu za osnivača?"*

## §2 WRITE UGOVOR vs. `CREATE TABLE`

| Polje | Izvor | JS tip | `supabase_migration.sql:115` | Poklapa se? |
|---|---|---|---|---|
| `user_id` | `currentUser.id` (Supabase auth) | `string` UUID | `UUID REFERENCES auth.users(id) ON DELETE SET NULL` | ✓ — i RLS `WITH CHECK (auth.uid() = user_id)` to **prinuđuje** |
| `original_prompt` | `decodeURIComponent(pitanjeEnc).substring(0,4000)` | `string` | `TEXT` (nullable) | ✓ |
| `ai_response` | `decodeURIComponent(odgovorEnc).substring(0,8000)` | `string` | `TEXT` (nullable) | ✓ |
| `timestamp` | `new Date().toISOString()` — **klijentski sat** | `string` ISO8601 | `TIMESTAMPTZ DEFAULT NOW()` | ⚠ **klijent nadjačava server default**; podložno pogrešnom satu/spoofingu |
| `id` | ne šalje se | — | `DEFAULT gen_random_uuid()` | ✓ |

**Ugovor se poklapa u imenima i tipovima.** Jedina neusklađenost je semantička:
`timestamp` dolazi iz pregledača umesto iz `NOW()`.

Očekuje li kod uspeh? **DA, izričito.** Ovo je jedini od tri slučaja gde kod
**proverava ishod i saopštava ga korisniku**:

```js
static/vindex.js:8074-8080
    // Supabase JS ne baca izuzetak -- gresku vraca u objektu.
    if (_upis && _upis.error) {
      btn.textContent = '⚠ Nije poslato — pokušajte ponovo';
      btn.disabled = false;
      showToast('Prijava NIJE sačuvana: ' + (_upis.error.message || 'greška baze'), 'err');
      return;
    }
```

## §3 READ UGOVOR

**Ne postoji u kodu.** Namera: `service_role` `SELECT *` bez filtera, sortirano po
`timestamp DESC` — dashboard kvaliteta AI odgovora. **Nikad implementirano.**

## §4 GRAF VEZA

| Ka | Status | Dokaz |
|---|---|---|
| `auth.users(id)` | **INFERRED** | FK deklarisan (l.117) + RLS `WITH CHECK (auth.uid() = user_id)`; tabela ne postoji → ništa od toga ne važi |
| `profiles` | **UNKNOWN** | nema; spajanje bi išlo preko `user_id` |
| `conversations` | **UNKNOWN** | **nema `session_id`** — iako `conversations` postoji i ima `session_id`; prijava se ne može vezati za razgovor |
| `predmeti` | **UNKNOWN** | nema `predmet_id` — prijava se ne može vezati za predmet |
| `ai_forensics` | **UNKNOWN** | **nema `correlation_id`** — nemoguće spojiti prijavu sa provenance redom AI odgovora koji se prijavljuje |
| `feedback` | **INFERRED (paralelan zapis)** | `sendFeedback` posle upisa šalje i `POST /api/feedback` → `feedback` tabela; veže ih samo `user_id` + vreme |
| `audit_log` / kancelarije | **UNKNOWN** | nema veze |

> **NALAZ RE-1.** Predložena šema (4 kolone) je **prekratka za svoju svrhu**. Prijava
> „AI je dao netačan odgovor" bez `correlation_id`/`session_id`/`predmet_id` ne može se
> spojiti ni sa `ai_forensics` redom, ni sa razgovorom, ni sa predmetom — dakle ne može
> se rekonstruisati **koji model, koja verzija prompta i koji izvori** su dali sporni
> odgovor. `docs/ux_audit/CANONICAL_INVENTORY.md:198` ovaj kanal naziva
> *„za pravnu aplikaciju najvredniji signal koji imate"* — a šema mu ne daje kontekst.

## §5 POSTOJEĆI EKVIVALENT — **NE POSTOJI**

| Kandidat | Kolone u produkciji | Redova | Pokriva? |
|---|---|---|---|
| **`feedback`** | `id, user_id, tip, created_at` | 1 | **NE.** `pitanje` i `odgovor` **fizički ne postoje** (provereno: `42703 column feedback.pitanje/odgovor does not exist`). NO-STORAGE politika (`routers/drafting.py:823–825`, ZZPL čl. 5(1)(c)). |
| **`support_tickets`** | `user_id, email, kategorija, poruka, rating, kontekst` | 1 | **NE.** Drugi kanal, druga namera (`/api/support/poruka`). Nosi *korisnikov opis*, ne *sporni AI odgovor*. `DUPLICATION_REPORT.md:227` ih izričito razdvaja. |
| **`response_audit`** | `query_hash, response_hash, confidence, top_score…` | 432 | **NE.** Samo heševi i metrika — po dizajnu bez sadržaja. |
| **`ai_forensics`** | `prompt_hash, response_hash…` | 124 | **NE.** Isto — heševi, ne sadržaj. |
| **`audit_log`** | `akcija, q_hash, ip_hash` | 297 | **NE.** Heševi. |
| **`predmet_istorija`** | `pitanje, odgovor, confidence` | 144 | **DELIMIČNO** — jedina tabela sa punim tekstom pitanja+odgovora, ali samo za pitanja vezana za predmet, i **bez oznake da je odgovor prijavljen kao netačan**. |
| **`conversations`** | `role, content, session_id` | **0** | **NE** — i sama je prazna. |

> **Zaključak §5.** Ekvivalent **ne postoji**, i to nije slučajno: cela platforma je
> namerno projektovana da AI sadržaj čuva **samo kao heš**. `reported_errors` je bio
> jedini **svesni izuzetak** od te politike — jedino mesto gde se puni tekst spornog
> pitanja i odgovora čuva radi ispravke modela. Taj izuzetak nikad nije stigao u bazu.

## §6 MRTAV KOD — **NIJE MRTAV**

| Simbol | Status | Dokaz |
|---|---|---|
| `#fb-btn` „Prijavi netačan odgovor" | **LIVE** | `vindex.js:7838`, crta se u `_feedbackBar()` ispod svakog AI odgovora; `UX_INVENTORY.md` UI-862 |
| `sendFeedback()` | **LIVE** | jedini `onclick` pozivalac; `CANONICAL_INVENTORY.md:198` → **„NE BRISATI"** |
| `sb.from('reported_errors').insert` | **LIVE POZVAN / GARANTOVANO PADA** | `PGRST205` na svaki klik |
| `reported_errors_insert_own` RLS politika | **DEAD** | politika ne postoji jer tabela ne postoji |
| `reported_errors_service_select` | **DEAD** | + nema nijednog čitaoca ni da postoji |
| **tabela `reported_errors`** | **MISSING, ali njen jedini pisac je LIVE i korisniku vidljiv** | — |

**Odgovor na eksplicitno pitanje: NE, `reported_errors` nije mrtav kod.**
Ima **1 živu produkcijsku write-referencu** (frontend), **1 živo UI dugme** ispod
svakog AI odgovora, i **0 read-referenci**.

## §7 SEMANTIKA OTKAZA — **jedini od tri koji je korisniku vidljiv**

Tačan lanac, korak po korak (advokat klikne „Prijavi netačan odgovor"):

1. `sendFeedback` proveri `currentSession && currentUser` → ok.
2. Dugme → *„Šaljem..."*, `disabled = true`.
3. `await _waitSupa(4000)` → Supabase klijent dobijen (ova provera je dodata baš zato
   što je ranije tiho preskakala — komentar `vindex.js:8052–8058`).
4. `sb.from('reported_errors').insert(...)` → PostgREST **HTTP 404**
   `{"code":"PGRST205","message":"Could not find the table 'public.reported_errors' in the schema cache"}`
5. Supabase JS **ne baca** — vraća `{data:null, error:{...}}`.
6. `if (_upis.error)` → **TAČNO**:
   - dugme: **„⚠ Nije poslato — pokušajte ponovo"**, ponovo `enabled`
   - toast: **„Prijava NIJE sačuvana: Could not find the table 'public.reported_errors' in the schema cache"**
   - `return` — **funkcija izlazi**.
7. Zbog tog `return`, `fetch(BASE_URL + '/api/feedback', ...)` (l.8082) se **nikad ne
   izvrši**. Rezervni kanal ne postoji.

| Pitanje | Odgovor |
|---|---|
| Koji izuzetak? | Nijedan — Supabase JS vraća `error` objekat; kod ga **ispravno** obrađuje |
| Koja operacija pada? | jedini `INSERT`; **100 % prijava** |
| Koje stanje se gubi? | **puni tekst spornog pitanja + spornog AI odgovora — nepovratno.** Nigde drugde ne postoji (§5) |
| Vidi li korisnik? | **DA.** Vidi crveni toast sa **sirovom engleskom PostgREST porukom** i imenom nepostojeće tabele |
| Rezervni kanal? | **NE** — `return` na l.8079 preskače `/api/feedback` |
| Da rezervni kanal i radi? | **I on je pokvaren** — v. NALAZ RE-3 |

> **NALAZ RE-2 (test meri jednu stranu ugovora).**
> `tests/test_faza15_interaction_closure.py:344` — `test_r004_uspesna_prijava_zaista_upisuje_sadrzaj`
> **prolazi zeleno**, i tvrdi da „sadržaj prijave zaista biva upisan". Ali test
> **mokuje** Supabase klijent (`window.__supaInsert`) i proverava samo da je JS
> *pokušao* upis u tabelu tog imena sa ta 4 polja. Serverska strana ugovora — da tabela
> postoji i da INSERT prolazi — **nije proverena nigde**. Ovo je tačno razred iz
> `feedback_testovi_mere_jednu_stranu_ugovora`: zelen test koji ne dokazuje ništa korisniku.

> **NALAZ RE-3 (nezavisan, izvan opsega ali blokira isti korisnički scenario).**
> `POST /api/feedback` (`routers/drafting.py:828–833`) upisuje:
> ```python
> _get_supa().table("feedback").insert({"user_id":…, "q_hash": qh, "tip": req.tip})
> ```
> Produkciona tabela `feedback` ima **samo** `id, user_id, tip, created_at` —
> **kolona `q_hash` ne postoji** (provereno: `42703 column feedback.q_hash does not exist`).
> PostgREST odbija ceo INSERT (`PGRST204`), `except Exception` ga proguta
> (`drafting.py:838`) i endpoint **svejedno vraća `{"status":"ok"}`** (l.840).
>
> **Dakle oba kanala za prijavu netačnog AI odgovora su pokvarena istovremeno:**
> primarni vidljivo (nema tabele), rezervni tiho (nema kolone, a odgovor laže „ok").
> `feedback` ima **1 red** — verovatno iz perioda pre nego što je `q_hash` dodat u kod.

## §8 PROIZVODNI UGOVOR

- **Poslovna sposobnost:** jedini kanal kojim advokat prijavljuje **netačan pravni
  odgovor**, sa punim kontekstom pitanja i odgovora. Ulaz u petlju ispravke modela.
- **Vidljivo korisniku:** **DA** — dugme ispod **svakog** AI odgovora (UI-862).
- **Obećano:** **DA, i to eksplicitno.** Dugme piše „Prijavi netačan odgovor"; uspešan
  ishod bi rekao „✓ Prijavljeno — hvala". Danas nikad ne kaže.
- **Nužno za betu:** **DA.** Beta pilot sa advokatima bez kanala za prijavu netačnog
  pravnog odgovora nema mehanizam za merenje sopstvene tačnosti.
  `CANONICAL_INVENTORY.md:198`: *„za pravnu aplikaciju najvredniji signal koji imate"*.
- **Klasifikacija:** **BETA-CRITICAL.**

## §9 BEZBEDNOST

| Osa | Ocena | Obrazloženje |
|---|---|---|
| Poverljivost | **P1 (pri kreiranju)** | jedina tabela na platformi koja bi čuvala **pun tekst** pravnog pitanja i AI odgovora — potencijalno podaci klijenata. Svesan izuzetak od NO-STORAGE politike. Traži RLS + retention + eksplicitnu odluku, ne „samo `CREATE TABLE`". |
| Integritet | **P2** | `timestamp` dolazi iz pregledača (§2), spoofabilan |
| Izolacija tenanta | **P1** | RLS `insert-own` je jedina zaštita (anon ključ iz pregledača); `RLS_CERTIFICATION.md:81` ga ocenjuje SAFE **na papiru** — ali politika ne postoji jer tabela ne postoji. **Nikad nije izvršena u produkciji, dakle nikad nije stvarno testirana.** Nema kolonskog `GRANT`-a kakav migracije 102/103/110 daju drugim frontend-dostupnim tabelama. |
| Auditabilnost | **P1** | **danas se gubi 100 % prijava netačnih AI odgovora.** Nema traga da je advokat ikad išta prijavio. |
| GDPR / ZZPL | **P1 (pri kreiranju)** | pun sadržaj = lični podaci; `services/retention_service.py` je **ne bi pokrivao** — nije u nijednoj listi. Traži retention pravilo pre prvog reda. |
| Naplata | **NONE** | — |
| AI governance | **P0** | **Ovo je najviši nalaz sprinta.** Pravni AI proizvod bez ijednog sačuvanog izveštaja o netačnom odgovoru ne može dokazati da meri, prati ni ispravlja sopstvene greške — ni prema korisniku, ni prema regulatoru, ni prema sebi. Dugme koje to obećava postoji i **javno pada** pred korisnikom. |

**Najviši prioritet: P0** (AI governance + poverenje korisnika).

## §10 PREPORUKA

> ## `CREATE_NEW_SCHEMA` — ali uz obavezan preduslov, **ne kao prosto izvršavanje l.115–133**

Obrazloženje:

1. **`REMOVE_DEAD_CODE` je isključen** (§0, §6): 1 živa produkcijska referenca, živo UI
   dugme, i eksplicitna zabrana brisanja u `CANONICAL_INVENTORY.md:198`.
2. **`REUSE_EXISTING_SCHEMA` je isključen** (§5): nijedna od 166 tabela ne čuva pun
   tekst AI pitanja+odgovora. To je posledica namerne NO-STORAGE politike.
3. **`DEFER` je isključen** (§8, §9): BETA-CRITICAL + P0 AI governance.

**Preduslov (odluka osnivača, ne inženjerska):** čuvanje punog teksta pravnog pitanja i
odgovora je **svestan izuzetak od NO-STORAGE / ZZPL-minimizacije** na kojoj počiva
ostatak platforme. Tabela ne sme nastati dok ne postoje: (a) odluka da se izuzetak pravi,
(b) retention pravilo u `services/retention_service.py`, (c) kolonski `GRANT` po obrascu
migracija 102/103/110, (d) verifikacija RLS `insert-own` politike **u produkciji**
(nikad nije izvršena).

**Ako se odluka donese**, šema iz `supabase_migration.sql:115` je **nedovoljna** —
NALAZ RE-1 traži `correlation_id` (spoj sa `ai_forensics`), `session_id` (spoj sa
`conversations`), `predmet_id`, i `timestamp` da dolazi iz `NOW()` a ne iz pregledača.

**Nezavisno od tabele, a blokira isti scenario:** NALAZ RE-3 (`feedback.q_hash` ne
postoji → rezervni kanal tiho pada uz lažni `{"status":"ok"}`). To je **odvojen kvar
odvojene tabele** i traži odvojenu odluku.

---

# ZBIRNI PREGLED

| Tabela | Žive ref. (W/R) | Redova | Ekvivalent postoji? | Semantika otkaza | Vidi korisnik? | P | **Preporuka** |
|---|---|---|---|---|---|---|---|
| `api_costs` | **1 W / 0 R** | — | **DA — `ai_forensics` (124 reda, 100 % tokena) + `feature_usage_log` (šema, 0 redova)** | tih; izuzetak progutan bez Sentry-ja; 2/4 rute ni ne pokušaju upis | **NE** | P2 | **`REUSE_EXISTING_SCHEMA`** |
| `ratio_decidendi` | **1 W / 1 R** | — | delimično (`ai_cache`, traži rewire) | keš **uvek** promašuje → **ponovljeni plaćeni `gpt-4o-mini` poziv, do 20 po prikazu, ~$0.008, bez `consume()` i bez `ai_forensics`** | posredno (sporije) | P1 | **`CREATE_NEW_SCHEMA`** |
| `reported_errors` | **1 W / 0 R** | — | **NE — nijedna od 166 tabela** | **100 % prijava izgubljeno; advokat vidi crveni toast sa sirovom PostgREST porukom; rezervni kanal preskočen `return`-om** | **DA** | **P0** | **`CREATE_NEW_SCHEMA` uz preduslov** |

## Nalazi izvan prvobitnog opsega (za zasebnu istragu — ništa nije menjano)

| ID | Nalaz | Prioritet |
|---|---|---|
| **AC-4** | `feature_usage_log` ima **0 redova** iako je `UsageService.consume()` očigledno živ (`feature_usage`=9, `usage_events`=2 906, `ai_forensics`=124). `_log_usage_event` guta sve na `logger.debug`. Ceo Revenue Intelligence COGS prikaz je time prazan. | **P1** |
| **RE-3** | `POST /api/feedback` upisuje `q_hash` u `feedback`, ali ta kolona **ne postoji** (`42703`). Izuzetak progutan, endpoint vraća `{"status":"ok"}`. Rezervni feedback kanal je tiho mrtav. | **P1** |
| **RD-3** | `_pozovi_ratio_api` koristi sirov `OpenAI(...)` umesto `shared/ai_client` → ratio pozivi **nemaju `ai_forensics` red**. AI izlaz prikazan advokatu bez provenance traga. | **P2** |
| **RD-4** | `POST /api/praksa/ratio` nema `UsageService.consume` → nenaplaćen, negejtovan OpenAI trošak; do 400 poziva/min po korisniku unutar rate-limita. | **P1** |
| **AC-1** | `record_cost` pokriva 2/4 rute koje zovu `log_cost_to_db`; `strategija_v2` i `hearing_command_center` bi upisali 0 redova i da tabela postoji. | **P2** |
| **RE-2** | `test_r004_uspesna_prijava_zaista_upisuje_sadrzaj` je zelen a mokuje Supabase — dokazuje samo klijentsku stranu ugovora. | **P2** |

---

## Metodološka napomena

Sve tvrdnje o produkcionoj šemi u ovom dokumentu potiču iz READ-ONLY sondi izvršenih
2026-08-13 nad produkcionim PostgREST-om (`SUPABASE_URL` iz `.env`, `service_role`):
OpenAPI definicija (imena kolona i tipovi), `Prefer: count=exact` (brojači redova), i
kolonske `select` sonde (postojanje kolone preko `42703` vs. `200`). **Nijedan red
podataka nije preuzet, nijedna izmena nije izvršena, nijedna tabela nije kreirana.**
Skripte sondi su u scratchpad direktorijumu sesije, izvan repoa.
