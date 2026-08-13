# SCHEMA RECON — `public.rokovi`

**Baseline:** `09536c92`
**Datum:** 2026-08-13
**Metod:** statička analiza repoa + READ-ONLY PostgREST sonde nad produkcijom (OpenAPI schema dump + `SELECT`)
**Ništa nije kreirano, izmenjeno ni obrisano.** Nula migracija, nula DDL-a, nula write-ova.

---

## 0. Dokazana osnova

| Tvrdnja | Dokaz | Status |
|---|---|---|
| Produkcija ima 166 tabela | PostgREST OpenAPI `definitions` count | VERIFIED |
| `public.rokovi` ne postoji | `GET /rest/v1/rokovi?select=id&limit=1` → `HTTP 404 PGRST205 "Could not find the table 'public.rokovi' in the schema cache"` | VERIFIED |
| `public.predmet_rokovi` ne postoji | isto, `PGRST205`, hint: `"Perhaps you meant the table 'public.predmet_dokazi'"` | VERIFIED |
| `public.rokovi_lanac` ne postoji | odsutna iz OpenAPI definicija | VERIFIED |
| Nijedna migracija ne kreira `rokovi` | `grep -iE "create +table[^;]*\brokovi\b" migrations/ *.sql` → 0 pogodaka | VERIFIED |
| Klijentska biblioteka baca izuzetak | `supabase-py` / `postgrest 2.28.3` → `postgrest.exceptions.APIError` (i sa `.maybe_single()`) | VERIFIED (empirijski) |
| `predmet_rokovi` nema **nijednu** referencu u kodu | grep celog repoa → samo 3 pogotka, svi u `docs/` | VERIFIED |

### 0.1 Latentni artefakt: `migrations/023_stability_500_users.sql`

```sql
-- 4. Index na rokovi za brze lookup predstojećih rokova (kalendar + notifikacije)
CREATE INDEX IF NOT EXISTS rokovi_datum_user_idx
  ON rokovi (user_id, datum)
  WHERE obrisan = false;
```

`CREATE INDEX IF NOT EXISTS` **ne tolerantiše nepostojeću tabelu** — `IF NOT EXISTS` se odnosi na indeks, ne na relaciju. Nad ovom bazom migracija 023 puca na koraku 4 sa `ERROR 42P01: relation "rokovi" does not exist`.

Posledice ovog nalaza:
1. Migracija 023 **nikada nije uspešno izvršena do kraja** nad ovom bazom, ili je izvršena ručno uz preskakanje koraka 4. Koraci 5+ (`klijenti_user_aktivan_idx`) su tada takođe izostali.
2. Ovo je nezavisna potvrda da `rokovi` **nikada nije postojao** u ovoj instanci — nije reč o tabeli koja je naknadno obrisana.
3. Migracija 023 dodatno pretpostavlja kolonu `rokovi.obrisan` (soft-delete) koju **nijedna linija runtime koda ne čita niti piše**.

**Status koraka 5–N migracije 023 = UNKNOWN.** Van opsega ovog sprinta, ali evidentirano.

---

## 1. §1 KOMPLETAN INVENTAR

**Ukupno stvarnih referenci ka tabeli: 13, u 9 fajlova.**
Brojane su isključivo `supa.table("rokovi")` konstrukcije. Odbačeni su: `predmet_rokovi`, `rokovi_lanac`, `rokovi_hitni`, ključevi u JSON/dict literalima (`{"rokovi": [...]}`), imena lokalnih promenljivih (`rokovi`, `rokovi_r`, `rokovi_txt`), imena ruta (`/api/rokovi/...`), `tags=["rokovi"]`, srpske reči u komentarima i promptovima, i sve pod `tests/`, `docs/`, `.vindex_ai_team/`, `data/`, `static/vindex.js.bak`.

**Sve 13 su `SELECT`. Nula `INSERT` / `UPDATE` / `UPSERT` / `DELETE`.**

| # | FILE | LINE | FUNCTION | ENDPOINT | OP | R/W | Očekivane kolone |
|---|---|---|---|---|---|---|---|
| 1 | `api.py` | 2639 | `portal_predmet_data` | `GET /api/portal/predmet` | SELECT | READ | `naziv, datum, tip, predmet_id` |
| 2 | `routers/dashboard.py` | 141 | `command_center` | `GET /api/dashboard/command-center` | SELECT | READ | `id, naziv, datum, tip, predmet_id, opis, user_id` |
| 3 | `routers/case_commander.py` | 134 | `_dohvati_predmet_kontekst` | `POST /api/commander/analiza`, `/quick-check`, `/checklist` | SELECT | READ | `naziv, datum, tip, opis, predmet_id` |
| 4 | `routers/case_commander.py` | 610 | `_dohvati_sve_predmete_za_analizu` | `GET /api/commander/jutarnji`, `POST /api/commander/jutarnji/refresh` | SELECT | READ | `id, naziv, datum, opis, predmet_id, status, user_id` |
| 5 | `routers/morning_briefing.py` | 115 | `_generiši_briefing` | `GET /api/briefing/daily`, `POST /api/briefing/send-email`, `POST /api/briefing/cron` | SELECT | READ | `id, naziv, datum, tip, predmet_id, opis, user_id` |
| 6 | `routers/morning_briefing.py` | 140 | `_generiši_briefing` | isto | SELECT | READ | isto (prošli rokovi, prozor −90d) |
| 7 | `routers/morning_briefing.py` | 1137 | `today_focus` | `GET /today-focus` | SELECT | READ | `predmet_id, naziv, datum, tip, user_id` |
| 8 | `routers/integrations.py` | 395 | `gcal_sync_rokovi` | `POST /api/integrations/gcal/sync-rokovi` | SELECT | READ | `naziv, datum, opis, predmet_id, user_id` |
| 9 | `routers/decision_replay.py` | 97 | `_gather_timeline_events` | `GET /api/predmeti/{id}/replay`, `/replay/timeline` | SELECT | READ | `naziv, datum, status, tip, predmet_id, user_id` |
| 10 | `routers/whatsapp_notif.py` | 303 | `posalji_rok` | `POST /api/whatsapp/posalji-rok` | SELECT | READ | `id, naziv, datum, opis, predmet_id, user_id` |
| 11 | `routers/whatsapp_notif.py` | 415 | `dnevni_brifing_wa` | `POST /api/whatsapp/dnevni-brifing-wa` | SELECT | READ | `naziv, datum, opis, user_id` |
| 12 | `routers/zadaci.py` | 642 | `ai_analiziraj_predmet` | `POST /api/zadaci/ai-analiziraj/{id}` | SELECT | READ | `naziv, datum, status, predmet_id` |
| 13 | `routers/zastarelost.py` | 505 | `guardian_scan` | `POST /api/rokovi/guardian/scan` | SELECT | READ | `id, naziv, datum, tip, predmet_id, opis, user_id` |

### 1.1 Ponašanje pri grešci i posledica po korisnika

| # | U `try`? | `return_exceptions`? | Ishod | Posledica za korisnika |
|---|---|---|---|---|
| 1 | NE | `asyncio.gather` **bez** `return_exceptions` | Izuzetak propagira | **HTTP 500. Ceo klijentski portal ne radi.** Klijent koji otvori link od advokata vidi grešku. Padaju i uspešni upiti `predmeti`+`profiles` u istom `gather`-u. |
| 2 | — | `gather_with_timeout` → `return_exceptions=True`, pa `_safe()` | Progutano → `[]` | **Tiho.** Home tab prikazuje rokove samo iz `predmet_hronologija`. „Nightly repair" od 2026-07-24 koji je dodao drugi izvor **nikada nije radio ni jedan dan.** |
| 3 | — | `return_exceptions=True`, pa `_safe()` | Progutano → `[]` | **Tiho + AI.** GPT dobija kontekst predmeta sa `ROKOVI: []` i tvrdi da rokova nema. |
| 4 | — | `return_exceptions=True`, pa `_d()` | Progutano → `[]` | **Tiho + AI.** Portfolio prioritizacija ne vidi nijedan rok; `hitni` lista (`:878`) je uvek prazna. |
| 5 | NE | `asyncio.gather` **bez** `return_exceptions` | Propagira | **HTTP 500** na `/api/briefing/daily` i `/send-email`. Kredit se troši *posle* poziva → nema gubitka kredita. |
| 6 | NE | isto | Propagira | isto |
| 7 | DA (`except Exception: pass`) | — | Progutano → `[]` | **Tiho.** `hitni_rokovi` uvek prazna; `/today-focus` tvrdi da nema hitnih rokova. |
| 8 | NE | — | Propagira | **HTTP 500** na Google Calendar sync. |
| 9 | DA (kod pozivaoca, `:252`/`:280`) | `gather` bez `return_exceptions` | `HTTPException(500, str(e))` | **HTTP 500** + **curenje internog teksta greške klijentu** (`str(e)` sadrži PostgREST poruku i ime tabele). |
| 10 | NE | `.maybe_single()` **ne guta** `PGRST205` | Propagira | **HTTP 500** umesto namenjenog `404 "Rok nije pronadjen"`. |
| 11 | NE | `gather` bez `return_exceptions`, unutar `for` petlje bez zaštite | Propagira iz petlje | **HTTP 500 na celom cron-u.** Brojači `poslato/preskoceno/greske` se gube. Prekida se na PRVOM pretplatniku — ostali se ni ne pokušavaju. |
| 12 | — | `return_exceptions=True` | Progutano → `[]` | **Tiho + naplaćeno.** Vidi §7.3. |
| 13 | NE | — | Propagira | **HTTP 500.** AI Deadline Guardian scan uvek puca. |

---

## 2. §2 WRITE UGOVOR

**PRAZAN. Nijedan `INSERT`, `UPDATE`, `UPSERT` ni `DELETE` nad `rokovi` ne postoji nigde u repou** — ni u `routers/`, `services/`, `shared/`, `workers/`, `integrations/`, `api.py`, ni u `migrations/` (nema `INSERT INTO rokovi`, nema seed-a).

Ovo je najvažniji strukturni nalaz celog izveštaja i on obrće ceo problem:

> Čak i da `public.rokovi` bude kreirana tačno po izvedenoj šemi, **ostala bi trajno prazna.** Svih 13 upita vratilo bi 0 redova. Nijedan korisnik nikada ne bi mogao da unese rok u nju — ne postoji ni API ruta, ni UI kontrola, ni AI putanja, ni migracija koja bi red upisala.

Zato ovo **nije šema koja nedostaje**. Ovo je čitalačka polovina ugovora čija druga polovina nikada nije napisana — a domenski objekat je u međuvremenu dobio drugog, stvarnog vlasnika (§5).

Dokaz sa suprotne strane: svaka kandidat-tabela iz §5 IMA stvarne pisce.

| Tabela | Pisci | Broj |
|---|---|---|
| `predmet_hronologija` | `api.py:4705`, `api.py:6100`, `case_dna.py:672`, `rokovi_lanac.py:436`, `predmeti_close.py:189`, `intake.py:282/415/885`, `copilot.py:810`, `learning.py:274` | 10 |
| `rocista` | `rocista.py:186` (insert), `:302` (update), `:469` (delete) | 3 |
| `zadaci` | `zadaci.py:209/814`, `onboarding.py:260`, + update/delete | 5+ |
| `case_actions` | `case_evolution.py:1056/1061/1077`, `predmeti_close.py:212/397` | 5 |
| `notifications` | `notifications.py:139/356`, `case_evolution.py:1207` | 3 |
| `proactive_alerts` | `shared/proactive_alerts.py:84` (kanonski jedini) | 1 |
| **`rokovi`** | **— nema —** | **0** |

---

## 3. §3 READ UGOVOR

Unija svih traženih kolona kroz 13 upita:

| Kolona | Tip koji kod pretpostavlja | Dokaz iz koda | Nullable po ponašanju koda |
|---|---|---|---|
| `id` | uuid/text | prosleđuje se kao `rok_id` u `whatsapp_notif.py:305` `.eq("id", req.rok_id)` | ne |
| `user_id` | uuid | `.eq("user_id", uid)` u 9/13 upita | ne |
| `predmet_id` | uuid, FK→`predmeti.id` | `.eq("predmet_id", predmet_id)`; join u memoriji `predmeti_map[r["predmet_id"]]` | **da** — `zastarelost.py:514` eksplicitno „fail-open" za orphan `predmet_id` |
| `datum` | `date` (ISO `YYYY-MM-DD`) | `.gte`/`.lte`/`.lt` sa `.isoformat()`; `date.fromisoformat(str(rok["datum"])[:10])` | ne — `morning_briefing.py:174` čita `r["datum"]` **bez `.get()`** → `KeyError` na null |
| `naziv` | text | uvek preko `.get("naziv", "Rok")` / `or "Rok"` | da |
| `opis` | text | uvek `.get("opis", "")`, fallback za `naziv` | da |
| `tip` | text | `.get("tip")`, u `dashboard.py:267` mapira se u polje `vaznost` | da |
| `status` | text | `decision_replay.py:159`: `status in ("prekoracen","propusten")` → kriticnost | da |
| `obrisan` | boolean | **samo `migrations/023`**, nijedan runtime čitalac | n/a |

**Filteri:** `user_id` (9×), `predmet_id` (5×), `id` (1×), opsezi po `datum` (`gte`/`lte`/`lt`).
**Join-ovi:** nijedan SQL join. Sve je in-memory spajanje preko `predmet_id` na već dohvaćenu `predmeti` mapu.
**Sortiranje:** `.order("datum")` u 10/13; `.order("datum", desc=True)` u `morning_briefing.py:145`.
**Agregacija:** nijedna u bazi. Sve brojanje/grupisanje je u Pythonu.
**Paginacija:** nema offset/cursor paginacije. Fiksni `.limit()`: 5 (`zadaci`, `whatsapp` cron), 10 (`api.py`, `case_commander:134`, `today-focus`), 20 (`morning_briefing:146`), 50 (`integrations`, `case_commander:610`), 100 (`dashboard`). **Tri upita nemaju `.limit()` uopšte** — `morning_briefing:115`, `morning_briefing:123`, `decision_replay:97`, `zastarelost:505` — oslanjaju se na implicitni PostgREST cap.

**Očekivana kardinalnost i značenje po pozivaocu:**

| Upit | 0 redova znači | 1 red | >1 red |
|---|---|---|---|
| `api.py:2639` | portal prikazuje praznu sekciju rokova — klijent zaključuje da nema rokova | normalno | normalno, cap 10 |
| `dashboard.py:141` | drugi izvor rokova ne doprinosi; `rokovi_7` ostaje samo iz hronologije | normalno | normalno |
| `case_commander:134/610` | **GPT dobija „nema rokova" kao činjenicu** | normalno | normalno |
| `morning_briefing:115` | „nema hitnih rokova" u brifingu | normalno | normalno |
| `morning_briefing:140` | nema propuštenih rokova (BLACKSWAN-CRIT-002 putanja) | normalno | normalno |
| `whatsapp:303` | `.maybe_single()` → `404 "Rok nije pronadjen"` | očekivano, jedini validan slučaj | **nemoguće** — `.maybe_single()` bi bacio na >1 red; implicira `UNIQUE(id)` |
| `zastarelost:505` | rani izlaz sa `"Nema rokova u narednih 30 dana."` | normalno | normalno |
| `decision_replay:97` | manje događaja; `<2` ukupno → `"Nedovoljno dogadjaja za replay analizu"` | normalno | normalno |

---

## 4. §4 GRAF VEZA

| Od → Ka | Kolona | Osnov | Status |
|---|---|---|---|
| `rokovi` → `predmeti.id` | `predmet_id` | `.eq("predmet_id", …)` gde je vrednost `predmeti.id`; in-memory join `pred_by_id[r["predmet_id"]]`; `zastarelost.py:502` upoređuje sa `predmeti.status` | **INFERRED** — semantički siguran, ali fizički FK constraint ne postoji jer tabela ne postoji |
| `rokovi` → `auth.users.id` | `user_id` | `.eq("user_id", uid)` gde je `uid = user["user_id"]` iz JWT-a | **INFERRED** — sve sestrinske tabele (`rocista`, `predmet_hronologija`, `notifications`) imaju `user_id uuid`, ali nijedna nema deklarisan FK ka `auth.users` u OpenAPI spec-u |
| `rokovi` → `klijenti` | — | **nema nijedne reference** | **UNKNOWN / ne postoji** |
| `rokovi` → `predmet_dokumenti` | — | nema. Jedina veza je posredna: oba se dohvataju u istom `gather`-u i spajaju preko `predmet_id` | **UNKNOWN / ne postoji** |
| `rokovi` → audit (`predmet_istorija`, `events`, `audit_log`) | — | **nema nijednog upisa u audit prilikom čitanja rokova** | **UNKNOWN / ne postoji** |
| `rokovi` → `kancelarije` | — | **nema.** Tenant model je isključivo per-user (`user_id`), ne per-kancelarija — za razliku od `zadaci` koja ima `kancelarija_id` sa **VERIFIED** FK ka `kancelarije.id` | **UNKNOWN / ne postoji** |

Za poređenje, VERIFIED FK-ovi u postojećoj šemi (iz OpenAPI `description` anotacija):
- `rocista.predmet_id` → `predmeti.id` — **VERIFIED**
- `predmet_hronologija.predmet_id` → `predmeti.id` — **VERIFIED**
- `notifications.predmet_id` → `predmeti.id` — **VERIFIED**
- `zadaci.kancelarija_id` → `kancelarije.id` — **VERIFIED**
- `case_actions.event_id` → `events.id` — **VERIFIED**
- `zadaci.predmet_id` → **nema deklarisan FK** (INFERRED)
- `case_actions.predmet_id` je `text`, ne `uuid` — **nema FK**

---

## 5. §5 POSTOJEĆI EKVIVALENT — najvažniji deo

### 5.1 Metod razdvajanja

Postoji jak, mehanički dokaz koji tabelu treba isključiti: **ako se tabela X dohvata u ISTOM `asyncio.gather`-u kao `rokovi` i njen rezultat se koristi za drugu svrhu, onda X nije `rokovi`.** Kod bi inače dvaput čitao isti skup.

| Kandidat | Dohvata se paralelno sa `rokovi` u istom `gather`-u? | Gde |
|---|---|---|
| `rocista` | **DA, 6 mesta** | `dashboard.py:83/133/165`, `morning_briefing.py:123/149`, `morning_briefing.py:1166`, `decision_replay.py:104`, `whatsapp_notif.py:424`, `zadaci.py:663` |
| `zadaci` | **DA** | `zadaci.py:634` (`zadaci_r`) i `zadaci.py:641` (`rokovi_r`) u **istom** `gather`-u; prompt na `:723-724` ih ispisuje kao **dve odvojene stavke** („Aktivni zadaci:" vs „Nadolazeći rokovi:") |
| `predmet_hronologija` | **DA** | `dashboard.py:89` (`rokovi_r`) i `dashboard.py:141` (`rokovi_tabela_r`) u istom `gather`-u |
| `proactive_alerts` | **DA** | `decision_replay.py:129` |
| `predmet_istorija` | **DA** | `dashboard.py:104/123` |

### 5.2 Ocena po kandidatu

#### `zadaci` — **NE MOŽE**
Kolone: `id, kancelarija_id, predmet_id, kreirao_uid, dodeljen_uid, naziv, opis, prioritet, status, rok_datum, zavrseno_u, komentar, created_at, updated_at`

| Zahtev | Ispunjeno? |
|---|---|
| `naziv`, `opis`, `status`, `predmet_id` | ✓ |
| `datum` | ✓ preko `rok_datum` (`date`) |
| **`user_id`** | **✗ KOLONA NE POSTOJI.** `zadaci` ima `kreirao_uid` (text), `dodeljen_uid` (text), `kancelarija_id` (uuid). **9 od 13 upita filtrira `.eq("user_id", uid)`** — svih 9 bi puklo sa `PGRST204 column does not exist`. |
| `tip` | ✗ |
| Semantika | ✗ **`zadaci.py:634+641` dohvata OBE u istom `gather`-u i tretira ih kao disjunktne skupove.** |
| Tenant model | ✗ `zadaci` je **per-kancelarija** (FK ka `kancelarije.id`, brisanje na `:439` ide preko `kancelarija_id`); `rokovi` je **per-user**. Različiti modeli izolacije. |

**Presuda: `zadaci` NE MOŽE da zadovolji ni read ni write ugovor.** Nedostaje `user_id` (blokira 9/13 upita), nedostaje `tip`, i kod ih dokazano tretira kao različite objekte.

#### `rocista` — **NE MOŽE**
Kolone: `id, predmet_id, user_id, sud, broj_predmeta_suda, datum, vreme, sudnica, status, napomena, created_at, updated_at`

| Zahtev | Ispunjeno? |
|---|---|
| `user_id`, `predmet_id`, `datum`, `status`, `id` | ✓ |
| `naziv` | ✗ (`whatsapp_notif.py:447` čita `r.get("naziv")` sa `rocista` i **uvek pada na fallback** `r.get("sud")` — potvrda da kolone nema) |
| `opis` | ~ `napomena` |
| `tip` | ✗ |
| Semantika | ✗ **`rocista` = ročišta (događaj u sudu, ima `vreme`, `sud`, `sudnica`). `rokovi` = procesni rokovi (samo datum).** Različiti domenski objekti. |
| Dvostruko brojanje | ✗ **6 mesta dohvata obe u istom `gather`-u** i prikazuje ih u odvojenim sekcijama („ROČIŠTA DANAS" vs „HITNI ROKOVI"). Spajanje bi svaki rok prikazalo kao ročište i obrnuto. |

**Presuda: `rocista` NE MOŽE.** Nedostaju `naziv` i `tip`, a što je važnije — kod ih dokazano tretira kao disjunktne skupove na 6 mesta.

#### `predmet_hronologija` — **MOŽE, i već JESTE stvarni vlasnik domena**
Kolone: `id, predmet_id, user_id, dokument_naziv, datum (text), datum_iso (date), dogadjaj, akter, vaznost, created_at`

| Zahtev `rokovi` | Mapiranje | Ocena |
|---|---|---|
| `id` uuid PK | `id` | ✓ |
| `user_id` uuid | `user_id` | ✓ |
| `predmet_id` uuid FK→`predmeti.id` | `predmet_id` — **VERIFIED FK** | ✓ |
| `datum` date | `datum_iso` (date) | ✓ |
| `naziv` text | `dogadjaj` text | ✓ |
| `tip` text | `vaznost` text (`informativan` / `kritičan`) | ~ približno |
| `opis` text | — | ✗ nedostaje (ali `case_dna.py:668` već rešava spajanjem: `f"{naziv}: {opis}"[:200]` → `dogadjaj`) |
| `status` text (`prekoracen`/`propusten`) | — | ✗ nedostaje; `decision_replay.py:159` i `case_dna.py:661` ga čitaju |

**Odlučujući dokaz — mapiranje već postoji u produkcionom kodu.** `routers/case_dna.py::_sync_rokovi_to_hronologija` (`:655-684`) uzima objekat **tačno oblika `rokovi`** (`{status, datum, naziv, opis}`) i upisuje ga u `predmet_hronologija`:

```python
dogadjaj = f"{naziv}: {(r.get('opis') or '').strip()}"[:200] if r.get("opis") else naziv[:200]
supa.table("predmet_hronologija").insert({
    "predmet_id": predmet_id, "user_id": uid,
    "dogadjaj": dg, "datum": dt, "datum_iso": dt,
    "vaznost": "kritičan", "akter": "Genome (AI)",
})
```

Isto radi `routers/rokovi_lanac.py:436` (ZPP lanac procesnih rokova → `predmet_hronologija`) i `routers/intake.py:415/885` (šablonski rokovi iz Intake Wizard-a → `predmet_hronologija`).

**Presuda: `predmet_hronologija` JESTE kanonski store rokova u ovoj aplikaciji.** Sve stvarne putanje upisa roka — Genome, ZPP lanac, Intake Wizard, Copilot, Learning, zatvaranje predmeta — pišu u nju. Nedostaju samo `opis` (već zaobiđeno konkatenacijom) i `status` (potreban samo za 3/13 čitalaca).

#### Ostali kandidati

| Tabela | Ocena |
|---|---|
| `case_actions` | **DELIMIČNO.** Ima `rok` (date), `predmet_id` (**text, ne uuid, bez FK**), `status`, `prioritet`, `dedupe_key`. **Nema `user_id`** — izolacija ide preko `predmet_id`. To je „šta treba uraditi" (Action Engine), ne „kada nešto ističe". Ne može bez izmene 9 upita. |
| `notifications` | **NE.** Poruka o događaju, ne sam događaj. Ima `procitano`, `poruka`, `naslov`. Nema `datum` roka — samo `created_at`. Projekcija iz `case_actions`, ne izvor. |
| `proactive_alerts` | **NE.** Isti razlog. Nema `datum`/`rok` kolonu uopšte. Dohvata se paralelno sa `rokovi` u `decision_replay.py:129`. |
| `rokovi_lanac` | **NE POSTOJI KAO TABELA.** `routers/rokovi_lanac.py` je čist kalkulator nad statičkim `_TIPOVI` dict-om; jedini `INSERT` (`:436`) ide u `predmet_hronologija`. |
| `predmet_istorija` | **NE.** Q&A log (`pitanje`/`odgovor`). Dohvata se paralelno sa `rokovi` u `dashboard.py`. |
| `kalendar*` | **NE POSTOJI NIJEDNA TABELA.** Sonda za `kalendar`/`calendar`/`deadline`/`task` u imenu → **0 pogodaka** među 166 tabela. `routers/kalendar.py::/api/kalendar/pregled` čita `rocista` + `predmet_hronologija` + `predmeti`. |

### 5.3 Šta korisnik zapravo koristi

Provera `static/vindex.js` — koje rute stvarno pune UI za rokove:

| UI površina | Endpoint | Čita |
|---|---|---|
| Kalendar (`kalMesecPrev` itd.) | `/api/kalendar/pregled` (`vindex.js:14319/14378/14397`) | `rocista` + `predmet_hronologija` + `predmeti` |
| Tab „Rokovi" → Generiši lanac | `/api/rokovi/lanac` (`vindex.js:11836/11885/22605`) | statički `_TIPOVI`, upis u `predmet_hronologija` |
| Rokovi iz dokumenta | `/api/dokument/rokovi` (`vindex.js:9420`) | efemerni parser, ne perzistira |
| Kalkulator zastarelosti | `/api/rokovi/tipovi-dogadjaja` (`vindex.js:11800`) | čista aritmetika |
| Home tab | `/api/dashboard/command-center` (`vindex.js:1278`) | `predmet_hronologija` (radi) + `rokovi` (tiho prazno) |

**Nijedna UI površina za rokove ne zavisi od tabele `rokovi`.** Korisnik danas ima funkcionalan kalendar i lanac rokova — preko `predmet_hronologija`.

---

## 6. §6 TEST MRTVOG KODA

Svi router-i su registrovani u `api.py` (`zastarelost:685`, `dashboard:711`, `whatsapp_notif:730`, `integrations:756`, `morning_briefing:758`, `case_commander:759`, `decision_replay:773`, `zadaci:806`). **Nijedna referenca nije nedostupna na HTTP nivou.** Razlika je u tome da li ih iko poziva.

Jedini konfigurisan cron u repou je `email-cron.yml` → `POST /email-notif/send-reminders`, koji čita **`predmet_hronologija`** (`email_notif.py:516`), ne `rokovi`.

| # | Referenca | Pozivalac | Klasa |
|---|---|---|---|
| 1 | `api.py:2639` | `client_portal.html:267` — `fetch("/api/portal/predmet?token=…")` | **LIVE** |
| 2 | `dashboard.py:141` | `static/vindex.js:1278` — na svakom učitavanju home taba | **LIVE** |
| 12 | `zadaci.py:642` | `static/vindex.js:23543` — dugme „AI analiziraj predmet" | **LIVE** |
| 3 | `case_commander.py:134` | **nema.** Jedini pogodak `commander/analiza` u `vindex.js:1301` je **unutar komentara**, ne `fetch`. `grep "api/commander" static/vindex.js index.html client_portal.html` → samo taj komentar. | **CONDITIONALLY LIVE** |
| 4 | `case_commander.py:610` | `/api/commander/jutarnji` postoji samo u `static/vindex.js.bak` (mrtav backup), ne u živom `vindex.js` | **CONDITIONALLY LIVE** |
| 5,6 | `morning_briefing.py:115,140` | `/api/briefing/daily` i `/send-email` samo u `vindex.js.bak:1334/1381`. `/api/briefing/cron` nema cron konfiguraciju. Capability map: `IMPLEMENTED_UNWIRED`, „kartica namerno uklonjena" | **CONDITIONALLY LIVE** |
| 7 | `morning_briefing.py:1137` | `/today-focus` — 0 pogodaka bilo gde u frontendu, čak ni u `.bak` | **CONDITIONALLY LIVE** |
| 8 | `integrations.py:395` | `gcal`/`sync-rokovi` — 0 pogodaka u `vindex.js`/`index.html` | **CONDITIONALLY LIVE** |
| 9 | `decision_replay.py:97` | `/replay` — 0 pogodaka u frontendu | **CONDITIONALLY LIVE** |
| 10 | `whatsapp_notif.py:303` | `/api/whatsapp/posalji-rok` — 0 pogodaka. `PošaljiRokReq.rok_id` je dokumentovan kao „UUID roka iz tabele rokovi" | **CONDITIONALLY LIVE** |
| 11 | `whatsapp_notif.py:415` | cron endpoint, **nijedan cron ga ne zove** (jedini cron je email) | **CONDITIONALLY LIVE** |
| 13 | `zastarelost.py:505` | `guardian` — 0 pogodaka u `vindex.js`. Capability map: `IMPLEMENTED_UNWIRED` — „Troši AI, a niko ga ne poziva." | **CONDITIONALLY LIVE** |

**Podela: 3 LIVE · 10 CONDITIONALLY LIVE · 0 DEAD · 0 UNKNOWN.**

Nijedna referenca nije klasifikovana kao DEAD jer su svi endpointi registrovani i dostupni preko HTTP-a autentifikovanom korisniku (a `/api/portal/predmet` i **bez autentifikacije**, samo sa tokenom). „CONDITIONALLY LIVE" znači: nedostupno iz UI-ja, ali živo za svakoga ko pozove API direktno, kao i za svaki budući reconnect UI-ja.

---

## 7. §7 SEMANTIKA OTKAZA

### 7.1 Tvrdi otkazi (HTTP 500) — 6 referenci

| Endpoint | Ref | Napomena |
|---|---|---|
| `GET /api/portal/predmet` | 1 | **LIVE.** Klijentski portal je potpuno nedostupan. Advokat pošalje klijentu link, klijent dobije grešku. |
| `GET /api/briefing/daily`, `POST /api/briefing/send-email` | 5,6 | Kredit se troši *posle* — bez gubitka kredita |
| `POST /api/integrations/gcal/sync-rokovi` | 8 | |
| `GET /api/predmeti/{id}/replay(/timeline)` | 9 | `HTTPException(500, str(e))` — **curi interna poruka o šemi** |
| `POST /api/whatsapp/posalji-rok` | 10 | 500 umesto namenjenog 404 |
| `POST /api/rokovi/guardian/scan` | 13 | AI Deadline Guardian |
| `POST /api/whatsapp/dnevni-brifing-wa` | 11 | 500 na celom cron-u, prekid na prvom pretplatniku |

### 7.2 Tihi gubici / lažno stanje uspeha — 6 referenci

| Ref | Manifestacija |
|---|---|
| 2 | Home tab: `rokovi_tabela_r` uvek `[]`. Popravka od 2026-07-24 nikada nije radila. **Nema nijednog loga** — `_safe()` guta bez `logger`. |
| 3,4 | GPT kontekst: `ROKOVI: []`. AI tvrdi da rokova nema. |
| 7 | `/today-focus`: `hitni_rokovi` uvek `[]` (`except Exception: pass`, bez loga). |
| 12 | GPT prompt: `"Nadolazeći rokovi: nema"`. |
| `POST /api/briefing/cron` | Vraća `{"ok": True, "poslato": 0, "greske": N}` — **`ok: True` iako 100% brifinga padne.** |

### 7.3 Ponovljena skupa operacija / naplata

`POST /api/zadaci/ai-analiziraj/{id}` (ref 12) je jedini gde se skupa operacija **izvrši i naplati** uprkos otkazu:
1. `rokovi_r` padne → progutano → `rokovi = []`
2. GPT poziv se svejedno izvrši sa promptom `"Nadolazeći rokovi: nema"`
3. `UsageService.consume(uid, …, "zadaci_ai")` na `:795` — **kredit se troši**

Docstring endpointa eksplicitno obećava: *„Da li su rokovi prekoračeni ili bliže ističu"*. **Ta provera ne može da se izvrši nikada**, a korisnik je plaća.

---

## 8. §8 PROIZVODNI UGOVOR

**Poslovna sposobnost:** perzistentni registar procesnih rokova po predmetu, sa vlasništvom, datumom, tipom i statusom, koji hrani kalendar, brifinge, notifikacije i AI kontekst.

**Da li je Vindex obećava?** Da — ali obećanje je vezano za *funkcionalnost*, ne za tabelu:

| Izvor | Tvrdnja | Ispunjeno preko |
|---|---|---|
| `site/index.html:320`, `site/za-advokate.html:289`, `site/sposobnosti.html:184` | „…rokove, beleške, praksu, procenu rizika…" u radnom prostoru predmeta | `predmet_hronologija` ✓ |
| `site/za-advokate.html:121` | „predmet, stranke i rokovi" iz otpremljenog spisa | `intake.py` → `predmet_hronologija` ✓ |
| Capability map `:109` | Lanac ZPP procesnih rokova → `PRODUCTION` | `rokovi_lanac.py:436` → `predmet_hronologija` ✓ |
| Capability map `:118` | „Rok koji AI nađe u dokumentu ne ostaje zaključan" → `PRODUCTION` | `case_dna.py:672` → `predmet_hronologija` ✓ |
| Capability map `:133` | Deadline Guardian → **`IMPLEMENTED_UNWIRED`**, „Troši AI, a niko ga ne poziva" | `rokovi` ✗ |
| Capability map `:190` | Jutarnji brifing → **`IMPLEMENTED_UNWIRED`**, kartica namerno uklonjena | `rokovi` ✗ |

**Ključni zaključak:** svako marketinško obećanje o rokovima **već je ispunjeno preko `predmet_hronologija`**. Tabela `rokovi` ne stoji iza nijedne tvrdnje koju Vindex daje javno. Dve sposobnosti koje je koriste (`Deadline Guardian`, `Jutarnji brifing`) već su **interno klasifikovane kao `IMPLEMENTED_UNWIRED`** — nezavisna potvrda ovog nalaza.

### Klasifikacija

| Aspekt | Klasa | Obrazloženje |
|---|---|---|
| Popravka `GET /api/portal/predmet` (500) | **BETA-CRITICAL** | Jedina javno dostupna, neautentifikovana ruta koja pada. Advokat šalje link klijentu — klijent vidi grešku. Ovo je funkcija okrenuta ka *klijentu advokata*, ne ka advokatu. |
| Popravka `dashboard/command-center` tihog izvora | **BETA-IMPORTANT** | Home tab i dalje prikazuje rokove iz `predmet_hronologija`; gubi se samo drugi izvor koji je ionako uvek bio prazan. Nema gubitka podataka, ali postoji mrtvi kod koji lažno sugeriše da postoje dva izvora. |
| `zadaci/ai-analiziraj` naplaćena analiza sa lažnom premisom | **BETA-IMPORTANT** | Korisnik plaća AI koji tvrdi „nema rokova". |
| Sama tabela `rokovi` kao šema | **DEAD-OBSOLETE** | Nula pisaca, nula UI površina, nula ispunjenih obećanja, domen već pokriven. |
| `Deadline Guardian`, `Jutarnji brifing`, `gcal sync`, `WhatsApp brifing`, `decision replay`, `today-focus`, `commander jutarnji` | **POST-BETA** | Već označeni `IMPLEMENTED_UNWIRED`; nisu u beta scope-u. |

---

## 9. §9 BEZBEDNOST

| Dimenzija | Nalaz | Ozbiljnost |
|---|---|---|
| **Dostupnost** | `GET /api/portal/predmet` vraća 500 na svaki poziv. Klijentski portal je 100% nedostupan. Neautentifikovana, javna ruta. | **P1** |
| **Poverljivost — curenje šeme** | `decision_replay.py:266/…` → `HTTPException(500, str(e))` isporučuje klijentu `"Could not find the table 'public.rokovi' in the schema cache"`. Otkriva imena internih tabela i tehnološki stack (PostgREST/Supabase). Antipattern isti kao `zadaci.py:613`. | **P2** |
| **Integritet / lažno stanje** | `POST /api/briefing/cron` vraća `{"ok": true}` uz 100% neuspeha. Monitoring koji gleda `ok` polje ne bi detektovao potpuni otkaz. | **P2** |
| **Izolacija tenanta (buduća)** | Ako se `rokovi` ikada kreira: **3 od 13 upita ne filtriraju po `user_id`** — `api.py:2641` (samo `predmet_id`, **bez ikakve provere vlasništva u samom upitu** — oslanja se isključivo na token gate), `case_commander.py:136`, `zadaci.py:644`. Poslednja dva imaju ownership pre-check (`case_commander:121-130` LAMBDA003 fix, `zadaci:600-608`), ali `api.py` nema — zavisi u potpunosti od RLS-a koji ne postoji jer tabela ne postoji. **Kreiranje `rokovi` bez RLS-a bila bi IDOR rupa u klijentskom portalu.** | **P1 (uslovno — aktivira se samo ako se tabela kreira)** |
| **Auditabilnost** | Nijedno čitanje `rokovi` ne piše audit trag. Dva otkaza (`dashboard`, `today-focus`) nemaju **nijedan log** — `_safe()` i `except Exception: pass` gutaju tiho. Otkaz je nevidljiv i u logovima i u metrikama. | **P2** |
| **Naplata** | `zadaci/ai-analiziraj` naplaćuje kredit za AI analizu koja je grounded na neistinitoj premisi „nema rokova". Nije prekomerna naplata po iznosu, ali jeste naplata za neisporučenu obećanu proveru. Brifing endpointi troše kredit *posle* poziva → bez gubitka. | **P2** |
| **AI governance** | Najozbiljniji nesigurnosni rizik. Četiri AI putanje (`case_commander` ×2, `zadaci`, `morning_briefing`) dobijaju `rokovi = []` kao **činjenicu**, ne kao „nepoznato". GPT zatim s punim samopouzdanjem tvrdi da predmet nema rokova. Za advokatski proizvod je propušten rok najskuplja moguća greška. Trenutno ublaženo time što `predmet_hronologija` nosi stvarne rokove — ali `case_commander._dohvati_predmet_kontekst` **ne čita `predmet_hronologija` uopšte**, pa je njegov rok-kontekst trajno i bezuslovno prazan. | **P1** |
| **GDPR** | Nema uticaja. Tabela ne postoji → nema ličnih podataka, nema retencije, nema DSAR obaveze. | **NONE** |

---

## 10. §10 JEDNA PREPORUKA

# `REMOVE_DEAD_CODE`

*(Ne implementirano. Ovo je nalaz, ne izmena.)*

### Obrazloženje

Odbačene alternative:

- **`CREATE_NEW_SCHEMA` — odbačeno.** Nula pisaca (§2). Tabela bi bila kreirana prazna i ostala prazna zauvek. Rešila bi 6 HTTP 500 grešaka time što bi svaki upit vraćao 0 redova — ali istu stvar postiže i uklanjanje upita, bez nove tabele, bez nove RLS politike, bez nove površine za IDOR (§9), i bez trajne obaveze održavanja. Kreiranje tabele bi dodatno **institucionalizovalo duplog vlasnika** za „rok" — direktno kršenje principa *„1 koncept = 1 vlasnik = 1 algoritam = 1 istina"* (Core Consolidation).

- **`REUSE_EXISTING_SCHEMA` — odbačeno kao *primarna* preporuka, iako je `predmet_hronologija` tačan cilj.** Ponovno vezivanje svih 13 upita na `predmet_hronologija` značilo bi 13 izmena produkcionog koda na putanjama od kojih je **10 nedostupno iz UI-ja i već interno označeno kao `IMPLEMENTED_UNWIRED`**. To je značajan rizik regresije radi oživljavanja funkcija koje nisu u beta scope-u.

- **`DEFER` — odbačeno.** `GET /api/portal/predmet` je LIVE, javan i potpuno pokvaren (P1).

### Šta preporuka konkretno znači

**Faza 1 — BETA-CRITICAL (3 LIVE reference):**

1. `api.py:2634-2646` — ukloniti `rokovi` granu iz `asyncio.gather`. Portal treba da čita rokove iz `predmet_hronologija` (isti izvor koji `/api/kalendar/pregled` već koristi) **ili** da vraća praznu listu dok se ne poveže. Bez ove izmene klijentski portal ostaje mrtav. **Uz to: dodati eksplicitan `user_id`/ownership filter** — trenutni upit nema nikakvu proveru vlasništva u samom upitu (§9).
2. `routers/dashboard.py:141` + `:261-271` — ukloniti `rokovi_tabela_r`. Merge grana je no-op od dana pisanja; njeno postojanje lažno sugeriše dva izvora istine.
3. `routers/zadaci.py:641-649` + `:724` — ukloniti `rokovi_r`, ili ga prevezati na `predmet_hronologija`. Ovo je jedina naplaćena putanja; prompt trenutno tvrdi „nema rokova" AI-ju za koji korisnik plaća.

**Faza 2 — POST-BETA (10 CONDITIONALLY LIVE referenci):** ostale ukloniti ili prevezati zajedno sa odlukom o sudbini `Deadline Guardian`-a, `Jutarnjeg brifinga`, `gcal sync`-a, `WhatsApp` kanala i `decision replay`-a — svi već nose oznaku `IMPLEMENTED_UNWIRED`. Ako se ijedna od tih funkcija oživi, cilj prevezivanja je **`predmet_hronologija`**, uz dodavanje `status` kolone (potrebna za 3 čitaoca) — a ne nova tabela.

**Prateće, van `rokovi`:** `migrations/023_stability_500_users.sql` sadrži DDL koji ne može da se izvrši nad ovom bazom (§0.1). Status koraka 5+ te migracije je UNKNOWN i zaslužuje zasebnu proveru.
