# BETA-INFRA-SCHEMA-RECONSTRUCTION-001 — RUNTIME CONTRACT FORENSICS

```
NO PRODUCTION MUTATION:  YES
NO MIGRATION EXECUTION:  YES
NO CODE MODIFICATION:    YES
NO SECRETS EXPOSED:      YES
```

Baseline `09536c92`. Nijedna tabela nije kreirana, nijedna migracija napisana,
nijedan produkcijski fajl menjan. Prateći artefakt:
`BETA_INFRA_SCHEMA_RECONSTRUCTION_MATRIX.csv`.

---

# ISPRAVKA MOJE PREMISE

U pripremi sam prijavio da `reported_errors` ima **0 produkcijskih referenci** i
da je najverovatniji kandidat za mrtav kod. **To je bilo netačno.**

Grepovao sam `--include=*.py`. Poziv se izvršava **iz pregledača**
(`static/vindex.js:8068`, direktan Supabase `insert` pod RLS `insert-own`), pa
ga takva pretraga strukturno nije mogla videti. Verifikovano.

Posledica te greške bi bila najskuplja moguća: preporuka „obriši mrtav kod" nad
funkcijom koja stoji ispod **svakog AI odgovora u proizvodu**.

---

# FINALNA TABELA

| Objekat | Zašto ga runtime očekuje | Živ? | Ekvivalent? | Otkaz | Bezbednost | Beta | Preporuka |
|---|---|---|---|---|---|---|---|
| **`rokovi`** | 13 čitanja u 9 fajlova | 3 LIVE / 10 uslovno | **`predmet_hronologija`** | 6× **500** + 6× tiho + 1× lažni uspeh | P1 | 1 ruta kritična | **`REMOVE_DEAD_CODE`** + rewire portala |
| **`api_costs`** | 1 upis, **0 čitanja** | pisac živ | **`ai_forensics`** | progutan `APIError`, bez Sentry | P1 | važno | **`REUSE_EXISTING_SCHEMA`** |
| **`ratio_decidendi`** | keš ratio decidendi | **LIVE**, auto-okida se | nijedan | **100% promašaj → plaćen LLM** | P1 | važno | **`CREATE_NEW_SCHEMA`** |
| **`reported_errors`** | prijava netačnog odgovora | **LIVE** | nijedan | **korisnik vidi grešku, prijava se gubi** | P1 | **kritično** | **`CREATE_NEW_SCHEMA`** (uz odluku) |

---

# `public.rokovi` — nije šema koja nedostaje

## Strukturni nalaz koji rešava pitanje

**Svih 13 referenci su `SELECT`. Nula `INSERT`/`UPDATE`/`UPSERT`/`DELETE` — u
celom repou.** Verifikovano nezavisno.

WRITE ugovor je **prazan**. Čak i da tabela bude kreirana tačno po izvedenoj
šemi, ostala bi **trajno prazna** — nema rute, UI kontrole, AI putanje ni seed-a
koji bi upisao red. Ovo nije nedostajuća šema nego **čitalačka polovina ugovora
čija druga polovina nikad nije napisana.**

`predmet_rokovi` ima **nula** referenci u kodu.

## Najgora posledica — javna ruta

`GET /api/portal/predmet` (`api.py:2639`) je **javna, neautentifikovana** ruta.
Poziv stoji u `asyncio.gather` **bez `return_exceptions`** i **van `try`** —
verifikovano čitanjem koda. Jedan `PGRST205` obara ceo odgovor.

> **Klijentski portal je 100% mrtav.** Advokat pošalje klijentu link, klijent
> dobije grešku.

## Ostale semantike otkaza

- **6 tihih gubitaka** — „nightly repair" iz `dashboard.py` (2026-07-24), koji je
  dodao `rokovi` kao drugi izvor, **nikad nije radio nijedan dan**, bez ijednog loga.
- **Lažni uspeh** — `POST /api/briefing/cron` vraća `{"ok": true, "poslato": 0}`
  uz 100% otkaza.
- **Naplaćena analiza sa lažnom premisom** — `zadaci/ai-analiziraj` guta grešku,
  šalje GPT-u „Nadolazeći rokovi: nema", pa **naplati kredit**.
- **Curenje šeme** — `decision_replay` vraća `str(e)` klijentu.

## Zašto ne `zadaci` ni `rocista` — izmereno, ne procenjeno

- **`zadaci` NE**: **nema `user_id` uopšte** (ima `kreirao_uid`, `dodeljen_uid`,
  `kancelarija_id`), a **9 od 13 upita filtrira `.eq("user_id", uid)`**. Uz to
  `zadaci.py:634/641` dohvata **obe** u istom `gather`-u — dakle kod ih tretira
  kao različite objekte.
- **`rocista` NE**: nema `naziv` (potvrda: `whatsapp_notif.py:447` uvek pada na
  fallback `sud`), nema `tip`. Ročište ima `vreme`, `sud`, `sudnicu` — drugi
  domenski objekat. **6 mesta ih dohvata zajedno** i prikazuje odvojeno.

**Stvarni vlasnik domena je `predmet_hronologija`** — ima `user_id`,
`predmet_id` (VERIFIED FK), `datum_iso`, `dogadjaj`, `vaznost`, i **10 živih
pisaca**. Mapiranje **već postoji u produkciji**: `case_dna.py:655` uzima objekat
tačno oblika roka i upisuje ga tamo.

## Zašto `REMOVE_DEAD_CODE`, a ne nova tabela

Tabela sa nula pisaca bila bi kreirana prazna i ostala prazna. Rešila bi 500-ke
time što bi svaki upit vraćao 0 redova — što postiže i uklanjanje upita, ali
**bez nove RLS površine**: tri upita nemaju `user_id` filter, a `api.py:2641`
nema **nikakvu** proveru vlasništva, pa bi tabela bez RLS-a bila **IDOR rupa u
klijentskom portalu**.

Uz to bi institucionalizovala **dva vlasnika pojma „rok"**, što krši
„1 koncept = 1 vlasnik = 1 istina".

---

# `api_costs` — ekvivalent postoji i bolji je

**0 čitalaca.** Jedini pisac je `shared/cost.py:97`.

Izmereno na 124 živa reda `ai_forensics`:

```
model              124/124   (embedding 58 · gpt-4o 25 · gpt-4o-mini 41)
tokens_prompt      124/124   zbir 97.551
tokens_completion   66/124   zbir 14.492   (embedding nema completion — tačno)
user_id · endpoint · model_provider   124/124
```

**Trošak je potpuno izvodljiv** — `shared/cost.py::estimate_cost()` je već ta
formula. `ai_forensics` uz to nosi `predmet_id`, `correlation_id` i `latency_ms`,
kojih predložena `api_costs` šema **nema**.

Uz to postoji `feature_usage_log` (migracije 065+112) sa `estimated_cost_usd` —
**projektovani naslednik**, koji već čita živi `/admin/pi/revenue-intelligence`.

**Otkaz:** `APIError` progutan na `cost.py:108`, log ne imenuje ni tabelu ni HTTP
kod, **bez `_sentry_capture`**. Naplata **nije** pogođena — krediti idu kroz
`user_credits`.

## Nalaz van opsega, izmeren

**`feature_usage_log` ima 0 redova**, dok `feature_usage` ima 9 a `usage_events`
**2.906**. `UsageService` dakle radi, ali njegov COGS zapis nikad ne stiže —
`_log_usage_event` guta sve na `logger.debug`. Cela Revenue Intelligence COGS
slika je prazna.

---

# `ratio_decidendi` — jedina putanja koja troši novac van svakog brojača

Write ugovor se **100% poklapa** sa `CREATE TABLE` iz `supabase_migration.sql`,
uključujući `UNIQUE(decision_number)` koji `on_conflict` traži.

`praksa_fetch_ratios` se **automatski okida** iz `praksa_render_results()` pri
svakom renderu pretrage — do **20 `gpt-4o-mini` poziva po prikazu**. Endpoint:

- **nema `UsageService.consume`** → nenaplaćeno i negejtovano
- koristi **sirov `OpenAI()` klijent** → **nema ni red u `ai_forensics`**

**Promašaj keša je 100%, uvek.** To je jedina putanja na platformi koja troši
novac a **ne postoji ni u jednom brojaču**.

---

# `reported_errors` — jedini otkaz koji korisnik vidi

Dugme „Prijavi netačan odgovor" (`vindex.js:7838`) stoji ispod **svakog** AI
odgovora. `CANONICAL_INVENTORY.md:198` izričito kaže „NE BRISATI".

## Lanac koji je gori od same tabele

1. **Primarni kanal, vidljivo:** advokat dobije crveni toast sa **sirovim
   engleskim PostgREST tekstom** — *„Could not find the table
   'public.reported_errors' in the schema cache"* — pa kod radi `return` i
   **preskače fallback**.
2. **Rezervni kanal, tiho:** `/api/feedback` upisuje `q_hash`, kolonu koja
   **ne postoji** (verifikovano: `feedback` ima samo `id, user_id, tip,
   created_at`). Izuzetak se guta, a endpoint vraća **`{"status":"ok"}`**.

> **Oba kanala su istovremeno pokvarena. 100% prijava netačnih pravnih odgovora
> se gubi, a sistem tvrdi da je prijava primljena.**

To nije schema problem nego **runtime ugovor koji laže**.

## Zašto preporuka nosi ogradu

Čuvanje **punog pitanja i odgovora** je namerni izuzetak od NO-STORAGE/ZZPL
politike i traži odluku o retenciji, kolonskim grantovima i RLS-u pre nego što se
šema napravi. Uz to je predložena šema od 4 kolone **pretanka** — bez
`correlation_id`/`predmet_id` prijava se **ne može spojiti** sa AI pozivom na
koji se žali.

---

# PRIORITETI

| | Stavka |
|---|---|
| **P0** | — nijedna (nema cross-tenant izloženosti ni gubitka poverljivih podataka) |
| **P1** | klijentski portal mrtav · 100% prijava netačnih odgovora izgubljeno · `ratio_decidendi` nenaplaćeni LLM pozivi · trošak AI nemerljiv · `feature_usage_log` prazan · `/api/feedback` laže „ok" |
| **P2** | `record_cost` pokriva 2 od 4 rute · naplaćena analiza sa lažnom premisom |
| **P3** | curenje imena šeme kroz `str(e)` |

---

# ODGOVORI NA DVA ZAVRŠNA PITANJA

## „Koje od četiri zaista zahtevaju novu produkcionu schema strukturu?"

**Dve.**

- **`ratio_decidendi`** — pravi keš sa `UNIQUE` ključem; nijedna postojeća
  tabela ne nosi taj ugovor, a odsustvo košta pri svakom prikazu.
- **`reported_errors`** — nijedna od 166 tabela ne čuva pun tekst pitanja i
  odgovora; sve ostalo čuva heševe **po dizajnu**. Uz izričitu odluku o
  retenciji i sa širom šemom od predložene.

## „Koje su samo nedovršeni ili zastareli runtime ugovori?"

**Dve.**

- **`api_costs`** — nedovršen ugovor. Domen **već postoji** dvaput
  (`ai_forensics` sa podacima, `feature_usage_log` kao projektovani naslednik).
  Treba prevezati pisca, ne praviti treću tabelu.
- **`rokovi`** — nedovršen na najgori način: **13 čitalaca, nula pisaca.**
  Napisana je polovina ugovora. Domen pokriva `predmet_hronologija` sa 10 živih
  pisaca.

---

# ŠTA OVAJ SPRINT NIJE DOKAZAO

Liveness je utvrđen **statički** — grep frontenda i cron konfiguracije, ne
Playwright. Po sopstvenoj invarijanti ovog projekta da je dokaz interakcije samo
Playwright, klasifikacija „CONDITIONALLY LIVE" je **najjača tvrdnja koju
statička analiza nosi**. Ne isključujem poziv sastavljen dinamički koji grep nije
uhvatio.
