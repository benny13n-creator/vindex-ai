# §3 FALSE-SUCCESS SWEEP — INVENTAR

**Datum:** 2026-08-13
**Baseline:** `2a2e799c`
**Režim:** READ-ONLY. Nijedan produkcijski fajl, test ni migracija nije izmenjen. Nijedna migracija nije pokrenuta. Sve DB sonde su isključivo `GET` (PostgREST `select`, `Range: 0-0`) i `GET /storage/v1/bucket`.
**Definicija:** *false success* = sistem tvrdi da je operacija uspela (ili tiho nastavlja) iako operacija NIJE uspela.

---

## 0. REZIME

| Klasa | Broj nalaza |
|---|---|
| **FS-P0** — gubitak poverljivih podataka / zaobiđena bezbednosna granica / cross-tenant | **4** |
| **FS-P1** — gubitak podataka korisnika / gubitak novca / GDPR-audit rupa / laž o pravnom sadržaju | **42** |
| **FS-P2** — pouzdanost, observability | **26** |
| **FS-P3** — kozmetika | **7** |
| **UKUPNO** | **79** |

Od 42 FS-P1 nalaza: **17** nosi direktan ili posredan gubitak novca, **9** je laž o pravnom sadržaju, **8** je GDPR/audit rupa, **13** je gubitak podataka korisnika (kategorije se preklapaju).

**Dva nalaza nisu dostižna u današnjem kodu** i eksplicitno su tako označena — FS-P0-04 (`klijenti/permissions.py`, nema pozivaoca) i FS-P1-42 (`shared/ai_fabric.py`, nema pozivaoca). Obrađeni su kao napunjene zamke, ne kao aktivne breše.

### Sistemski (mereni) obim, ne pojedinačni nalazi

| Merenje (AST nad produkcijskim kodom) | Vrednost |
|---|---|
| `.insert()/.update()/.delete()/.upsert()` + `.execute()` čiji se rezultat **odbacuje kao izraz** | **415** |
| od toga na **kritičnim** tabelama (novac, predmet, klijent, dokaz, audit, sesija) | **122** |
| `except` blokova koji progutaju izuzetak **bez** `raise` i **bez** Sentry-ja | **489** |
| `except ...: pass` (potpuno nemi) | **118** |
| sirovih `asyncio.create_task(` u produkcijskom kodu | **128** |
| od toga registrovanih u `shared/bg.py::spawn` (jedini mehanizam koji uopšte primeti pad taska) | **6** |
| route handler-a koji progutaju grešku upisa **i svejedno vrate uspeh** | **23** |
| `fetch()` upisa (POST/PUT/PATCH/DELETE) u `static/vindex.js` | **170** |
| od toga koji **nikad** ne pogledaju `res.ok` / status | **26** |

---

## 1. DOKAZANO STANJE PRODUKCIJSKE ŠEME (READ-ONLY SONDA)

Ovo je tvrdi dokaz, ne pretpostavka. Sonda: `GET /rest/v1/<tabela>?select=*` sa `Range: 0-0`, `Prefer: count=exact`, service-role ključ. `PGRST205` = tabela ne postoji u schema cache-u; `42703` = kolona ne postoji.

### 1.1 Tabele u koje produkcijski kod PIŠE, a koje NE POSTOJE (5)

| Tabela | HTTP | Pisci u kodu | Posledica |
|---|---|---|---|
| `api_costs` | 404 PGRST205 | `shared/cost.py:97` | **svako** logovanje troška AI-ja je no-op |
| `rokovi` | 404 PGRST205 | 13 mesta (v. §3.4) | **svaki** upit za rokove vraća grešku ili praznu listu |
| `ratio_decidendi` | 404 PGRST205 | `routers/praksa.py:311, :330` | GPT keš nikad ne pogađa i nikad se ne puni |
| `klijenti_dokumenti` | 404 PGRST205 | `klijenti/router.py:1422` | dokumenti klijenta se ne mogu izlistati |
| `user_activity_profile` | 404 PGRST205 | `security/anomaly_detection.py:153` | bihevioralni profil uvek „ne postoji" |

`rokovi`, `klijenti_dokumenti` i `user_activity_profile` nemaju `CREATE TABLE` **nigde u repou** — ni u `migrations/`, ni u `supabase_*.sql`. `api_costs` i `ratio_decidendi` postoje samo u legacy `supabase_migration.sql`, koji očigledno nikad nije primenjen na ovu bazu.

### 1.2 Kolone koje NE POSTOJE, a kod ih upisuje

| Kolona | HTTP | Pisac |
|---|---|---|
| `feedback.q_hash` | 400 `42703` | `routers/drafting.py:832` |
| `feedback.pitanje` | 400 `42703` | (legacy šema) |
| `predmet_klijenti.user_id` | 400 `42703` | (v. FS-P0-01) |

### 1.3 Tabele koje POSTOJE ali imaju 0 redova, a kod tvrdi da u njih piše (izbor)

`feature_usage_log` **0** (dok `usage_events` ima **2.906**), `predmet_klijenti` **0**, `zadaci` **0**, `rocista` **0**, `billing_entries` **0**, `fakture` **0**, `timer_sessions` **0**, `tarife` **0**, `sef_log` **0**, `notification_log` **0**, `client_portal_uploads` **0**, `law_docs` **0**, `email_log` **0**, `ingest_jobs` **0**. Ukupno **100 od 153** referenciranih tabela je prazno.

> Prazna tabela sama po sebi nije dokaz otkaza (baza je beta, ima 19 predmeta i 12 profila). Navedena je jer za `predmet_klijenti` i `feature_usage_log` postoji **nezavisan** dokaz otkaza u kodu — v. FS-P0-01 i FS-P1-12.

### 1.4 Storage bucket-i — ZATVOREN ranije otvoren nalaz

`GET /storage/v1/bucket`:

| Bucket | `public` |
|---|---|
| `portal-uploads` | **false** |
| `intake-dokumenti` | **false** |

Oba su privatna. Time je nalaz „orphan fajl posle brisanja" spušten sa FS-P0 na FS-P1 (zadržavanje podatka posle brisanja, ne javno izlaganje).

---

## 2. FS-P0 — GUBITAK POVERLJIVIH PODATAKA / ZAOBIĐENA GRANICA

---

### FS-P0-01 — Provera sukoba interesa vraća „nema sukoba" **uvek**, i UI to boji u zeleno

| Polje | Vrednost |
|---|---|
| **FILE** | `klijenti/router.py` (backend) + `static/vindex.js` (frontend) |
| **LINE** | `klijenti/router.py:692` (`except`), `:695`, `:707-711` (return) — endpoint od `:619`; `static/vindex.js:5027-5029` |
| **FUNCTION** | `check_conflict` / `crmPokreniKonflikt` |
| **Okidač** | Advokat u CRM-u pokreće proveru sukoba interesa za novog klijenta. **Svaki poziv, bez izuzetka.** |
| **Tvrđeni ishod** | HTTP 200, `{"conflict_detected": false}`, UI ispisuje: `✅ Nije pronađen sukob interesa.` |
| **Stvarni ishod** | Provera se **strukturno nikad ne izvrši do kraja**, i to iz dva nezavisna razloga koji se sabiraju. |

**Dokaz — razlog A (šema):** unutrašnji upit čita `predmet_klijenti` (`klijenti/router.py:669-672`). Sonda: `predmet_klijenti` ima **0 redova**, a `predmet_klijenti.user_id` **ne postoji** (`42703`). Petlja `for pk in (pk_res.data or [])` nikad se ne izvrši → `conflicts` ostaje `[]` → `conflict_detected = len(conflicts) > 0` je **`False` za svaki mogući ulaz**. Nijedan izuzetak se ne diže.

**Dokaz — razlog B (progutan izuzetak):** cela pretraga je u jednom `try`:
```python
    except Exception as e:
        logger.error("[CONFLICT] greška: %s", e)

    conflict_detected = len(conflicts) > 0
```
Nema `raise`, nema Sentry-ja, nema polja u odgovoru koje bi reklo da je pretraga pukla. Odgovor je bit-po-bit identičan čistoj proveri.

**Dokaz — razlog C (frontend):** `static/vindex.js:5026-5029` čita `await r.json()` **bez provere `r.ok`**. Na 401/403/429/500 telo je `{"detail": ...}`, pa je `d.conflict_detected` `undefined` → falsy → grana „nema sukoba" se izvrši. Treći nezavisni put do istog zelenog čekiranja.

**Dokaz — razlog D (uzročni lanac):** `predmet_klijenti` je prazan **jer se svi upisi u nju progutaju**: `routers/intake.py:267` (`except → logger.warning`), `routers/intake.py:858`, `routers/intake.py:1013`, `routers/copilot.py:972`, `routers/onboarding.py:234`, `routers/smart_intake.py:1177`, `api.py:6436` — 7 mesta, nijedno ne proverava `.data`. Veza klijent↔predmet nikad ne nastane, pa provera sukoba nema šta da nađe.

| Polje | Vrednost |
|---|---|
| **Scenario otkaza** | Advokat proverava potencijalnog klijenta koji je protivna strana u njegovom postojećem predmetu. Sistem kaže `✅ Nije pronađen sukob interesa.` Advokat prihvata zastupanje. |
| **Gubitak podataka** | Ne |
| **Zaobiđena bezbednosna granica** | **Da.** Provera sukoba interesa JESTE kontrola koja sprečava zloupotrebu poverljivih informacija jednog klijenta protiv njega, u korist drugog. Njen potpuni otkaz je cross-client poverljivosna granica koja ne postoji. |
| **Gubitak novca** | Posredno — disciplinska odgovornost, malpraksa, gubitak licence |
| **Da li se korisniku laže** | **Da — najjače moguće.** Zelena kvačica i rečenica u indikativu na jedinom ekranu gde lažno-negativan nalaz može da košta advokatsku licencu. |
| **Test** | Ne. `tests/test_conflict_check.py` testira DRUGI endpoint (`routers/conflict_check.py`), ne ovaj. Nijedan test ne pokriva `klijenti/router.py::check_conflict`. |
| **Mutation test** | **Da, obavezan.** Mutacija koja natera `predmet_klijenti` upit da baci mora da obori test. |
| **Kanonska popravka** | (1) Endpoint mora vratiti `provera_potpuna: false` i HTTP 503 kada bilo koji sloj pretrage padne — nikad 200 sa praznom listom. (2) Popraviti `predmet_klijenti` upis (proveriti `.data`, dići grešku). (3) Frontend: `if (!r.ok) { showUserError(...); return; }` pre čitanja `d`. (4) UI ne sme prikazati zelenu potvrdu bez `provera_potpuna === true`. |

> **Napomena o klasifikaciji:** po slovu taksonomije ovo je „korisnik je slagan o pravnom sadržaju" (FS-P1). Klasifikovano je kao FS-P0 jer je predmet laži *kontrola koja štiti poverljivost između klijenata*, a otkaz je 100%-tan i nevidljiv.

---

### FS-P0-02 — Dešifrovani JMBG / pasoš / PIB se izdaju i kad obavezni audit upisa padne

| Polje | Vrednost |
|---|---|
| **FILE** | `klijenti/audit.py` + `klijenti/router.py` |
| **LINE** | `klijenti/audit.py:47-66` (`log_event`), pozivaoci `klijenti/router.py:415` i `:954` |
| **FUNCTION** | `log_event` / `get_klijent` / download dokumenta klijenta |
| **Okidač** | Bilo koja DB greška pri upisu u `klijenti_audit` u trenutku kada se čitaju CONFIDENTIAL polja |
| **Tvrđeni ishod** | `log_event` vraća `None` — identično uspešnom upisu. Endpoint nastavlja i dešifruje PII. |
| **Stvarni ishod** | PII (JMBG, broj pasoša, PIB) i dešifrovan dokument klijenta se **isporučuju bez ijednog zapisa o pristupu** |
| **Scenario otkaza** | Docstring same funkcije kaže: „MORA biti pozvan pre vraćanja CONFIDENTIAL podataka". `router.py:415` ga `await`-uje i **ignoriše ishod**, pa odmah dešifruje na `:422-431`. |
| **Gubitak podataka** | Ne — gubi se **dokaz o pristupu** |
| **Zaobiđena granica** | **Da** — obavezna kontrola pristupa poverljivim podacima postaje neobavezna |
| **Gubitak novca** | Ne |
| **Laže li se korisniku** | Da (implicitno — sistem tvrdi da je pristup evidentiran) |
| **Test** | Ne. `tests/test_beta_gate_klijent_delete_audit.py` mock-uje `log_event` u celosti. |
| **Mutation test** | Da |
| **Kanonska popravka** | `log_event` vraća `bool`; oba `await`-ovana poziva vraćaju 503 ako je `False`. Preostalih 12 `asyncio.create_task(log_event(...))` (`klijenti/router.py:292, 401, 514, 552, 609, 699, 881, 1076, 1188, 1368, 1680`) prebaciti na `shared.bg.spawn`. |

---

### FS-P0-03 — Obrisana beleška iz baze znanja ostaje u celosti pretraživa

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/knowledge_base.py` |
| **LINE** | `:381-394` (`_delete_from_pinecone` + `create_task`), `:404` (return), leak na `:236-245` |
| **FUNCTION** | `knowledge_delete` |
| **Okidač** | Pinecone nedostupan, ili Render restart ubije fire-and-forget task |
| **Tvrđeni ishod** | `{"ok": true, "id": entry_id}` — beleška obrisana |
| **Stvarni ishod** | Postgres red obrisan; **vektor ostaje**. `knowledge_search` čita **pun tekst beleške iz Pinecone metapodataka** (`"sadrzaj": m.metadata.get("sadrzaj", "")`), ne iz baze — obrisana beleška se vraća doslovno, zauvek. |
| **Gubitak podataka** | Da (obrnut smer — podatak ne nestaje kad treba) |
| **Zaobiđena granica** | Delimično. Namespace je `kb_{uid}` — **nije cross-tenant** (provereno: `:230` query koristi `namespace=f"kb_{uid}"`). Granica koja pada je pravo na brisanje. |
| **Gubitak novca** | Ne |
| **Laže li se korisniku** | Da |
| **Test** | Ne za Pinecone granu |
| **Mutation test** | Da |
| **Kanonska popravka** | Obrisati vektor **pre** DB reda, verifikovati brisanje (obrazac koji `shared/vector_deletion.py:206-215` već implementira), i tek onda vratiti `ok`. |

---

### FS-P0-04 — Fail-open razrešavanje role daje ADVOKAT pristup poverljivim poljima

| Polje | Vrednost |
|---|---|
| **FILE** | `klijenti/permissions.py` |
| **LINE** | `:126-143` (`_role_from_db`), `DEFAULT_ROLE` na `:42` |
| **FUNCTION** | `_role_from_db` |
| **Okidač** | Bilo koja greška čitanja `user_roles` (mreža, RLS, pool) |
| **Tvrđeni ishod** | Vraća se validna rola |
| **Stvarni ishod** | Vraća se `DEFAULT_ROLE = Role.ADVOKAT`, koji zadovoljava `ROLE_FIELD_ACCESS[FC.CONFIDENTIAL]` (`:89`) i `ACTION_MIN_ROLE["access_confidential"]` (`:102`) → sekretarica se unapređuje u rolu koja čita JMBG/pasoš/PIB |
| **Gubitak podataka** | Ne |
| **Zaobiđena granica** | **Da** |
| **Laže li se korisniku** | Ne |
| **REACHABLE DANAS** | **NE.** `make_role_dependency` (`:146`) nema nijednog produkcijskog pozivaoca — grep potvrđuje samo `scripts/` i sam modul. Ovo je **napunjena zamka**, ne aktivna breša. |
| **Test** | Test POSTOJI ali testira DRUGU kopiju: `tests/test_lambda003_klijenti_role_fail_closed.py` proverava `klijenti/router.py:65-73::_get_role`, koji **jeste** fail-closed. Ova druga implementacija nikad nije zakrpljena. |
| **Mutation test** | Da |
| **Kanonska popravka** | `return Role.SEKRETARICA` u `except`, identično `klijenti/router.py:73`. Ili obrisati mrtvu implementaciju. |

---

## 3. FS-P1 — GUBITAK PODATAKA / NOVCA / GDPR-AUDIT / LAŽ O PRAVNOM SADRŽAJU

---

### FS-P1-01 — Cross-doc analiza: „Nisu pronađeni konflikti" kada analiza uopšte nije prošla, uz naplaćen kredit

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/cross_doc.py` + `static/vindex.js` |
| **LINE** | `routers/cross_doc.py:221-224` (`except json.JSONDecodeError → result = {}`), `:236-241` (return), `:271` (naplata); UI `static/vindex.js:12010-12011` |
| **FUNCTION** | `_cross_doc_sync` / `cross_doc_analiza` |
| **Okidač** | GPT-4o odgovor nije validan JSON. **Realan okidač:** `max_tokens=2000` uz `response_format={"type":"json_object"}` (`:39-42`) — analiza 5 dugih ugovora obori limit, JSON se **preseče**, `json.loads` baci. Verovatnoća raste upravo sa težinom predmeta. |
| **Tvrđeni ishod** | HTTP 200; UI ispisuje: **`Nisu pronađeni konflikti između odabranih dokumenata.`** Kredit naplaćen. |
| **Stvarni ishod** | `result = {}` → `konflikti: []`, `rezime: ""`, `preporuke: []`, `pravni_zakljucak: ""`. Analiza nikad nije proizvela nijedan nalaz. |
| **Gubitak podataka** | Ne |
| **Gubitak novca** | **Da** — pun kredit za nulti rezultat, plus plaćen GPT-4o poziv |
| **Laže li se korisniku** | **Da, o pravnom sadržaju.** Odsustvo konflikta između ugovora je pravna tvrdnja, ne UI stanje. |
| **Test** | **Postoji i UČVRŠĆUJE bag:** `tests/test_cross_doc.py:228::test_sync_gpt_invalid_json_ne_pada` tvrdi prazan rezultat kao ispravan. |
| **Mutation test** | Da — i postojeći test mora biti obrnut |
| **Kanonska popravka** | Ne hvatati `JSONDecodeError` — pustiti ga u postojeću 500 granu (`:279-284`). Ne naplaćivati. UI: razlikovati „nema konflikata" od „analiza nije završena". |

---

### FS-P1-02 — `/api/praksa/ratio`: nemeren, nekeširan, neograničen GPT trošak + laž o pravnom stavu

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/praksa.py` + `static/vindex.js` |
| **LINE** | `:308-322` (`_get_ratio_from_cache`), `:328-338` (`_save_ratio_to_cache`), `:340-356` (`_pozovi_ratio_api`), `:569-596` (endpoint); UI `static/vindex.js:8500`, `:8730`, `:8748-8750` |
| **FUNCTION** | `praksa_ratio` / `_extract_ratio_sync` / `praksa_fetch_ratios` |
| **Okidač** | **Svako** renderovanje rezultata pretrage sudske prakse. Korisnik ne klikne ništa — `praksa_fetch_ratios` se poziva automatski (`:8500`). |
| **Tvrđeni ishod** | Ratio decidendi prikazan; ako nije — UI ispisuje `Pravni stav nije utvrđen iz dostavljenog teksta.` |
| **Stvarni ishod** | Četiri nezavisna defekta koji se množe. |

**Dokaz 1 — keš je fizički nemoguć.** `ratio_decidendi` tabela **NE POSTOJI** (sonda: `PGRST205`). `_get_ratio_from_cache` uvek baci → progutano na `logger.debug` → vraća `None`. `_save_ratio_to_cache` uvek baci → progutano na `logger.warning`. **Svaki prikaz svake odluke plaća GPT poziv iznova, zauvek.**

**Dokaz 2 — nema naplate.** Endpoint (`:571`) koristi samo `Depends(get_current_user)`. **Nema** `PermissionService.require`, **nema** `UsageService.consume`. Uporedi sa susedom `argument_map` (`:726`, `:784`) koji ima oba.

**Dokaz 3 — trošak je nevidljiv u svim NAPLATNIM sistemima.**

> **ISPRAVKA ranije tvrdnje (uključujući formulaciju u mandatu).** Tvrdnja „sirov `OpenAI()` klijent → nema ni reda u `ai_forensics`" je **NETAČNA** i ovde se povlači. `shared/ai_client.py` nije wrapper koji se poziva, nego **monkeypatch** na `openai.OpenAI` / `Completions.create`, instaliran na startu (`api.py:26`). Sirova konstrukcija klijenta je zato *očekivan* obrazac i **jeste** presretnuta. Produkcijska sonda to potvrđuje: `ai_forensics` sadrži **10 redova sa `endpoint = "praksa.py:_pozovi_ratio_api:347"`**. Prompt guard i Response Firewall takođe rade.

Ono što raw klijent **ne** dobija je **naplata**. Posledica, po sistemu:
> | Sistem | Zapis o ovom trošku |
> |---|---|
> | `ai_forensics` | **DA** (10 redova) — forenzika radi |
> | `feature_usage_log` | **NE** — nema `UsageService.consume` (tabela ionako ima 0 redova) |
> | `api_costs` | **NE** — tabela ne postoji (`PGRST205`) |
> | oduzeti krediti | **NE** — 0 |
>
> Dakle: zna se *da* je poziv napravljen, ne zna se *ko plaća* i *koliko*.

**Dokaz 4 — obim.** `@limiter.limit("20/minute")` × do 20 odluka po pozivu = **do 400 `gpt-4o-mini` poziva u minuti po korisniku**, svaki do 6.000 znakova ulaza, plus `@llm_retry` (do 3 pokušaja).

| Polje | Vrednost |
|---|---|
| **Gubitak podataka** | Ne |
| **Gubitak novca** | **Da, neograničen i neatribuiran.** Nijedan sistem ne zna da je novac potrošen. |
| **Laže li se korisniku** | **Da, o pravnom sadržaju.** `Pravni stav nije utvrđen iz dostavljenog teksta.` je tvrdnja o presudi; stvarno značenje je „ekstrakcija je pukla". |
| **Test** | Ne |
| **Mutation test** | Da |
| **Kanonska popravka** | (1) Kreirati `ratio_decidendi` ili ukloniti keš-put. (2) Rutirati kroz `shared/ai_client.py`. (3) Dodati `UsageService.consume` i `PermissionService.require`. (4) UI mora razlikovati „nema obrazloženja" od „ekstrakcija nije uspela". |

---

### FS-P1-03 — Kanal za prijavu netačnog AI odgovora je mrtav na dva nezavisna nivoa

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` + `routers/drafting.py` |
| **LINE** | `static/vindex.js:8047-8087` (`sendFeedback`); `routers/drafting.py:820-841` (`/api/feedback`) |
| **FUNCTION** | `sendFeedback` / `feedback` |
| **Okidač** | Korisnik prijavljuje netačan pravni odgovor |

**Nivo 1 (frontend):** `sb.from('reported_errors').insert(...)` na `:8068`. Tabela **NE POSTOJI** (sonda: `PGRST205`). Kod **ispravno** čita `_upis.error` (`:8075`) — ovo NIJE false success — ali:
- korisniku se ispisuje **sirov engleski PostgREST tekst**: `showToast('Prijava NIJE sačuvana: ' + _upis.error.message, 'err')` → srpski advokat vidi `Could not find the table 'public.reported_errors' in the schema cache`, uz curenje imena šeme;
- `return` na `:8079` je **iznad** `fetch(BASE_URL + '/api/feedback')` na `:8082` → **fallback se nikad ne izvrši**.

**Nivo 2 (backend, i da se izvrši):** `routers/drafting.py:832` upisuje `q_hash` u `feedback`. Sonda: `feedback.q_hash` **NE POSTOJI** (`42703`). Insert uvek baci. `except` na `:839-841`:
```python
    except Exception as _exc:
        _sentry_capture(_exc)
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}
```
**Jedini `return`-uspeh-iz-except-bloka u celom repou** (AST potvrda: 1/1). Endpoint tvrdi `ok` na 100% otkaza. `feedback` tabela ima **1 red**, iz 2026-04-17.

| Polje | Vrednost |
|---|---|
| **Gubitak podataka** | **Da** — svaka prijava netačnog pravnog odgovora od 2026-04-17 je izgubljena |
| **Gubitak novca** | Ne |
| **Laže li se korisniku** | Backend: da. Frontend: ne laže, ali govori nerazumljivo i preskače fallback. |
| **Test** | Ne |
| **Mutation test** | Da |
| **Kanonska popravka** | Ukloniti `return {"status":"ok"}` iz `except` (vratiti 500). Uskladiti payload sa stvarnom `feedback` šemom. Premestiti `/api/feedback` poziv **iznad** `return`-a na `:8079`. Prevesti PostgREST greške. |

---

### FS-P1-04 — Tabela `rokovi` ne postoji; GPT dobija „Nadolazeći rokovi: nema" i kredit se naplaćuje

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/zadaci.py` |
| **LINE** | `:642-650` (upit), `:673` (`Exception → []`), `:719` (prompt), `:789` (naplata), `:798`/`:830` (return) |
| **FUNCTION** | `ai_analiziraj_predmet` |
| **Okidač** | Svaki poziv — `rokovi` ne postoji (sonda: `PGRST205`) |
| **Tvrđeni ishod** | `{"ok": true, "kreirano": N, "poruka": "AI je kreirao N zadatak(a)"}` ili `"Predmet je uredan — nema kritičnih zadataka."` |
| **Stvarni ishod** | `asyncio.gather(..., return_exceptions=True)` + `rokovi = (rokovi_r.data if not isinstance(rokovi_r, Exception) else [])` (`:673`) pretvara otkaz u praznu listu. Prompt (`:719`) šalje GPT-u `Nadolazeći rokovi: nema`. |
| **Gubitak podataka** | Ne |
| **Gubitak novca** | **Da** — `UsageService.consume(uid, ..., "zadaci_ai")` na `:789` se izvršava bezuslovno |
| **Laže li se korisniku** | **Da, o pravnom sadržaju.** `"Predmet je uredan"` je zaključak izveden nad podacima koje sistem nikad nije video. Za advokata je propušten rok najskuplja moguća greška. |
| **Test** | Ne za granu otkaza `rokovi` |
| **Mutation test** | Da |
| **Kanonska popravka** | Kreirati `rokovi` (ili ukloniti sve reference). `return_exceptions=True` mora voditi u eksplicitno `nepotpuni_podaci: true` u odgovoru i u promptu; ne naplaćivati analizu nad nepotpunim ulazom. |

---

### FS-P1-05 — `rokovi` blast radius: 13 mesta koja tiho vraćaju „nema rokova"

| Polje | Vrednost |
|---|---|
| **FILE / LINE** | `routers/case_commander.py:134`, `:610`; `routers/dashboard.py:141`; `routers/decision_replay.py:97`; `routers/integrations.py:395`; `routers/morning_briefing.py:115`, `:140`, `:1137`; `routers/whatsapp_notif.py:303`, `:415`; `routers/zadaci.py:642`; `routers/zastarelost.py:505`; `api.py:2639` |
| **Okidač** | Svaki poziv |
| **Tvrđeni ishod** | Dashboard, jutarnji brifing, WhatsApp podsetnici i zastarelost prikazuju stanje rokova |
| **Stvarni ishod** | Tabela ne postoji. Gde postoji `return_exceptions=True` ili `or []` → prazna lista bez signala; gde ne postoji → 500. |
| **Gubitak podataka** | Ne (nema šta da se izgubi — nikad nije ni upisano) |
| **Laže li se korisniku** | **Da** — prazan spisak rokova je neodvojiv od „nemate rokova" |
| **Test** | Ne |
| **Kanonska popravka** | Odlučiti: kreirati `rokovi`, ili priznati da je `predmet_hronologija` jedini nosilac rokova i prepisati svih 13 mesta. Trenutno stanje je najgore od oba. |

---

### FS-P1-06 — `POST /api/briefing/cron` vraća `ok: true` uz 100% otkaza

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/morning_briefing.py` |
| **LINE** | `:115`, `:140` (`rokovi` upiti u `asyncio.gather` **bez** `return_exceptions`), `:664-670` (`except → greske += 1`), `:684` (return) |
| **FUNCTION** | `briefing_cron` / `_generiši_briefing` |
| **Okidač** | Svako jutro, eksterni cron |
| **Tvrđeni ishod** | `{"ok": True, "poslato": 0, "greske": 500, "ukupno": 500}` — HTTP 200 |
| **Stvarni ishod** | `rokovi` ne postoji → `_generiši_briefing` baci za svakog korisnika → `_process_one` uhvati → `greske` raste. `"ok": True` je **hardkodovan** (`:684`) i ne zavisi ni od čega. |
| **Gubitak podataka** | Ne |
| **Laže li se korisniku** | Da — cron servis dobija 200 i nikad ne alarmira |
| **Test** | Ne |
| **Kanonska popravka** | `"ok": greske == 0`; HTTP 500 kada je `poslato == 0` a `ukupno > 0`. |

---

### FS-P1-07 — GDPR brisanje naloga tvrdi uspeh bez provere ijednog upisa

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/gdpr.py` |
| **LINE** | `:219-230` (`_delete`), `:247-254` |
| **FUNCTION** | `gdpr_delete_account` |
| **Okidač** | `.update()` pogodi 0 redova (pogrešan id, RLS), ili `.upsert()` no-op |
| **Tvrđeni ishod** | HTTP 200: *„Vaš korisnički nalog je anonimizovan — email i ime uklonjeni su iz profila."* |
| **Stvarni ishod** | Nijedan od dva rezultata se ne pregleda. Profil može i dalje nositi pravi email i ime. |
| **Gubitak podataka** | Ne — **suprotno**: PII opstaje posle brisanja |
| **GDPR** | **Da** — čl. 17, ispitanik je obavešten o brisanju koje se nije dogodilo |
| **Laže li se korisniku** | **Da** |
| **Test** | `tests/test_gdpr_delete.py` tvrdi samo koje tabele su dodirnute i da je 200 — nikad da je red promenjen |
| **Mutation test** | **Da, prioritetno** |
| **Kanonska popravka** | Proveriti `r.data` na oba poziva; 500 ako je prazno. |

---

### FS-P1-08 — Masovni GDPR izvoz podataka bez trajnog zapisa

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/data_export.py` |
| **LINE** | `:81-86` |
| **FUNCTION** | `export_complete` |
| **Okidač** | GC ili Render redeploy tokom pravljenja ZIP-a |
| **Tvrđeni ishod** | Audit izvoza je „zakazan" |
| **Stvarni ishod** | Sirov `_aio.create_task(_imm_log("data_export", ...))` — nema jake reference, nije u `shared/bg` registru koji `api.py` drenira. Kompletna kopija podataka kancelarije napušta sistem **bez ijednog zapisa ko ju je uzeo**. |
| **GDPR / audit** | **Da** |
| **Test** | `tests/test_sprint4_silent_failures.py` pokriva potpunost arhive, ne ovaj task |
| **Kanonska popravka** | `shared.bg.spawn(...)`, ili `await` pre streamovanja. |

---

### FS-P1-09 — Verifikacija integriteta audit lanca proverava NAJSTARIJE zapise i javlja „potvrđen"

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/audit_immutable.py` + `api.py` + `routers/admin_dashboard.py` |
| **LINE** | `shared/audit_immutable.py:472-478` (`.order("seq", desc=False).limit(limit)`), `:535`; `api.py:2343-2353`; `routers/admin_dashboard.py:266` |
| **FUNCTION** | `_verify_chain_sync` / `admin_audit_verify` |
| **Okidač** | Tabela ima više od `limit` redova. `audit_immutable` ima **15.764 reda**, `limit=1000`. |
| **Tvrđeni ishod** | `{"ok": True, "message": "Integritet lanca potvrđen za 1000 zapisa."}`, a docstring endpointa doslovno kaže *„Skenira poslednjih 1000 zapisa"* |
| **Stvarni ishod** | `desc=False` vraća **prvih 1.000 ikad upisanih**. **14.764 najnovijih zapisa — tačno onih gde bi tampering i bio — nikad se ne pregleda.** Admin dashboard je još gori: `limit=200`. |
| **Gubitak podataka** | Ne |
| **Audit rupa** | **Da** — alat za detekciju tamperinga je zelen po konstrukciji |
| **Laže li se korisniku** | **Da, dvaput** — i u kodu i u docstring-u endpointa |
| **Test** | `tests/test_celina5_secops_2026_07_24.py` testira detekciju prekida, ne pokrivenost/redosled |
| **Mutation test** | Da |
| **Kanonska popravka** | `desc=True`, obrnuti niz, re-usidriti `prev_hash` iz reda pre prozora. |

---

### FS-P1-10 — Greška čitanja račva hash lanac i proizvodi lažnu uzbunu o tamperingu

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/audit_immutable.py` |
| **LINE** | `:421-436` (`_get_last_hash`) — `except Exception: pass` → `return _GENESIS_HASH` |
| **FUNCTION** | `_get_last_hash` |
| **Okidač** | Bilo koja tranzijentna greška čitanja `audit_immutable` |
| **Tvrđeni ishod** | `log_action` vrati id → pozivalac vidi uspeh |
| **Stvarni ishod** | Novi red se usidri na **genesis hash**. Lanac je račvan. Kasniji `verify_chain_integrity` javlja *„Lanac je polupan na seq=N. Mogući tampering."* za ono što je bio mrežni treptaj. |
| **Audit rupa** | **Da** — integritetni dokaz je pokvaren, i uz to se proizvodi lažni bezbednosni incident |
| **Test** | Ne |
| **Kanonska popravka** | Propagirati grešku čitanja. Upis u lanac koji ne može pročitati prethodnika mora **pasti**, ne usidriti se na genesis. |

---

### FS-P1-11 — `shared/cost.py`: tabela `api_costs` ne postoji, trošak AI-ja se ne meri nigde

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/cost.py` |
| **LINE** | `:97` (insert), `:107-108` (`except → logger.warning`) |
| **FUNCTION** | `log_cost_to_db` |
| **Okidač** | Svaki poziv |
| **Tvrđeni ishod** | Trošak zapisan; docstring modula (`:8`) uputstvo daje kao standardni obrazac |
| **Stvarni ishod** | `api_costs` **NE POSTOJI** (sonda: `PGRST205`). Svaki `asyncio.create_task(log_cost_to_db(...))` (npr. `api.py:3391`, `routers/strategija.py:729`, `:913`, `routers/hearing_cc.py:468`) je no-op sa `logger.warning`. Nema Sentry-ja. |
| **Gubitak novca** | **Da, u smislu vidljivosti** — nula podataka o potrošnji po korisniku/endpointu |
| **Laže li se korisniku** | Ne (interno) |
| **Test** | Ne |
| **Kanonska popravka** | Kreirati `api_costs` ili obrisati modul; u oba slučaja `_sentry_capture` u `except`. |

---

### FS-P1-12 — `feature_usage_log` ima 0 redova; telemetrija naplate se guta na `logger.debug`

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/usage.py` |
| **LINE** | `:400-401` (`_insert`), `:423-426` (`except → logger.debug`) |
| **FUNCTION** | `_log_usage_event` |
| **Okidač** | Svaki naplaćeni poziv |
| **Tvrđeni ishod** | Red telemetrije naplate upisan |
| **Stvarni ishod** | **Sonda: `feature_usage_log` = 0 redova**, dok `usage_events` ima **2.906** i `ai_forensics` **124**. Kolone `predmet_id` i `correlation_id` **postoje** (migracija 112 primenjena), pa uzrok NIJE nedostajuća kolona — a `except` na `:423` guta sve na `debug` nivou, tako da uzrok nije nigde zabeležen. |
| **Gubitak podataka** | **Da** — cela naplatna telemetrija |
| **Gubitak novca** | Posredno — nemoguće rekonstruisati ko je šta potrošio |
| **Test** | Ne |
| **Mutation test** | Da |
| **Kanonska popravka** | Podići na `logger.error` + `_sentry_capture`; dodati readiness provajder koji poredi `usage_events` i `feature_usage_log` i pada kad se raziđu. |

---

### FS-P1-13 — `_increment_usage` fail-open ukida jedinu zaštitu za besplatne funkcije

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/usage.py` |
| **LINE** | `:229-241` |
| **FUNCTION** | `_increment_usage` |
| **Okidač** | Bilo koji otkaz RPC-a `increment_feature_usage` |
| **Tvrđeni ishod** | Upotreba prebrojana |
| **Stvarni ishod** | `return 0` → zahtev **dozvoljen**. Za `copilot_ambient` (dnevni 200) i `morning_briefing` (dnevni 5), koje su na **0 kredita**, ovaj brojač je — po komentaru u samom kodu (`:207-210`) — *jedina* budžetska zaštita. Otkaz = neograničena besplatna AI potrošnja. |
| **Gubitak novca** | **Da** |
| **Laže li se korisniku** | Ne |
| **Test** | Ne za granu otkaza |
| **Kanonska popravka** | Fail-open je svesna odluka i to je u redu, ali mora imati `_sentry_capture` + metriku; danas je samo `logger.warning`. |

---

### FS-P1-14 — Evidence reklasifikacija: kredit naplaćen, ništa upisano

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/evidence.py` |
| **LINE** | `:271-272`, `:320-321` (progutani upisi), `:485-490` (provera i naplata) |
| **FUNCTION** | `klasifikuj_i_sacuvaj` / `reklasifikuj` |
| **Okidač** | GPT uspe, oba DB upisa padnu |
| **Tvrđeni ishod** | `{"ok": True, "poruka": "Reklasifikacija završena."}` + naplaćen kredit |
| **Stvarni ishod** | Endpoint proverava **samo** `_klasifikacija_greska` (da li je GPT pao). Otkaz upisa u `predmet_dokumenti` i `predmet_dokazi` je nevidljiv. |
| **Gubitak podataka** | Da |
| **Gubitak novca** | Da |
| **Test** | **Postoji i UČVRŠĆUJE bag:** `tests/test_evidence_klasifikacija.py:93::test_never_raises_even_if_both_fail` |
| **Kanonska popravka** | `klasifikuj_i_sacuvaj` vraća ishod upisa; `ok` i naplata vezani za njega. |

---

### FS-P1-15 — Auto Discovery: „PDF je uspešno obrađen i upisano 0 vektora"

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/auto_discovery.py` |
| **LINE** | `:175-178` (nulti vektori kao popuna), `:196-198` (`continue`), `:276-280` (`status: processed`), `:549-557` (poruka) |
| **FUNCTION** | `_embed_chunks` / `_upiši_pinecone` / `discovery_upload` |
| **Okidač** | Bilo koja greška embedding batch-a |
| **Tvrđeni ishod** | HTTP 200: *„PDF je uspešno obrađen i upisano N vektora u Pinecone."*, red u redu čekanja `processed` |
| **Stvarni ishod** | `_EMBED_BATCH = 100` (`:67`) — svaki pali batch tiho odbaci **100 chunk-ova ≈ 80.000 reči** pravnog teksta. Bez gornje granice: svi batch-evi mogu pasti a pipeline se i dalje „završi". |
| **Gubitak podataka** | **Da, do 100%** |
| **Laže li se korisniku** | **Da** — doslovno „uspešno obrađen" uz 0 upisanih |
| **Test** | Ne |
| **Kanonska popravka** | Dići izuzetak pri otkazu embedding-a (obrazac već primenjen u `routers/law_upload.py:120-126`); označiti red `error` kad `upsertovano < len(chunks)`. |

---

### FS-P1-16 — Auto Discovery: nedostaje `len()` provera → embedding se pari sa POGREŠNIM tekstom

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/auto_discovery.py` |
| **LINE** | `:168`, `:195` |
| **FUNCTION** | `_embed_chunks` / `_upiši_pinecone` |
| **Okidač** | OpenAI vrati kraći niz od poslatog batch-a |
| **Tvrđeni ishod** | Vektori i tekstovi upareni |
| **Stvarni ishod** | Nema provere `len(resp.data) != len(batch)`. `zip(chunks, embeddings)` pomeri sve naredne parove → `metadata["text"]` se čuva uz embedding **drugog** chunk-a. Semantička pretraga vraća **pogrešan tekst zakona** sa visokim skorom. |
| **Gubitak podataka** | Tiha korupcija, gora od gubitka |
| **Laže li se korisniku** | **Da, o pravnom sadržaju, nevidljivo** |
| **Dokaz da je propust** | Identična provera postoji u sva tri srodna pisca sa objašnjenjem: `drafting/playbook.py:75-79`, `interni_stavovi.py:69-73`, `routers/law_upload.py:129-133` |
| **Test** | Ne |
| **Kanonska popravka** | Kopirati provera iz srodnih modula i dići izuzetak. |

---

### FS-P1-17 — `law_upload` / `batch_ingest`: `status="done"` posle delimičnog upisa

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/law_upload.py`, `routers/batch_ingest.py` |
| **LINE** | `law_upload.py:150-158`, `:178-179`; `batch_ingest.py:150-160`, `:138-139` |
| **FUNCTION** | `_run_ingest_sync` (oba) |
| **Okidač** | 1 od N batch-eva prođe |
| **Tvrđeni ishod** | `status = "done"`; `GET /api/admin/law/lista` prikazuje `done` |
| **Stvarni ishod** | `if upserted > 0: _db_update(..., "done", ...)`. Zakon je u `zakoni_rs` sa rupama do 99%. `_db_update` i sam guta (`:178-179`), pa se i sam status može ne upisati. `batch_ingest.py:138-139` dodatno tiho odbaci repne chunk-ove bez inkrementiranja `failed`. |
| **Gubitak podataka** | **Da** |
| **Laže li se korisniku** | **Da** — RAG kasnije citira nepotpun zakon kao potpun |
| **Test** | `tests/test_batch_ingest.py:248` **tvrdi** `done`; nema testa za delimični otkaz |
| **Kanonska popravka** | `status = "done" if failed == 0 else "partial"`. |

---

### FS-P1-18 — Soft-delete zakona ostavlja vektore; povučen zakon se i dalje citira

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/law_upload.py` |
| **LINE** | `:280-291` |
| **FUNCTION** | `obrisi_zakon` |
| **Okidač** | Svako brisanje zakona |
| **Tvrđeni ishod** | `{"ok": True, "naziv": ...}` |
| **Stvarni ishod** | Samo `law_docs.status = "obrisan"`. **Svi vektori ostaju u `zakoni_rs`** i `app/services/retrieve.py::_semanticka_pretraga` (`:899`) ih i dalje vraća. Povučen ili pogrešan zakon se nastavlja citirati advokatu kao važeći. |
| **Gubitak podataka** | Ne — **suprotno** |
| **Laže li se korisniku** | **Da, o pravnom sadržaju** |
| **Test** | Ne |
| **Kanonska popravka** | Ili obrisati vektore, ili dodati `deleted` metadata filter u retrieval upit. |

---

### FS-P1-19 — Playbook / interni stavovi: brisanje vraća `0` i HTTP 200 i kad je puklo

| Polje | Vrednost |
|---|---|
| **FILE** | `drafting/playbook.py`, `interni_stavovi.py` |
| **LINE** | `drafting/playbook.py:123-136`; `interni_stavovi.py:125-138`; pozivaoci `routers/drafting.py:597-599`, `routers/interni.py:55-57` |
| **FUNCTION** | `delete_playbook` / `obrisi_stavove` |
| **Okidač** | Pinecone greška |
| **Tvrđeni ishod** | HTTP 200, `{"deleted_chunks": 0}` / `{"obrisano_vektora": 0}` |
| **Stvarni ishod** | `except → return 0` — potpuni otkaz je neodvojiv od „namespace je već bio prazan". Poverljiva biblioteka klauzula kancelarije i interni pravni stavovi ostaju pretraživi. Čak i „uspešna" grana broji preko `describe_index_stats()` **pre** brisanja, bez naknadne provere. |
| **Gubitak podataka** | Ne — **suprotno** |
| **Laže li se korisniku** | **Da** |
| **Test** | Ne za nijedan od dva |
| **Kanonska popravka** | Vratiti eksplicitan ishod + verifikacija posle brisanja; nikad ne mapirati izuzetak u `0`. |

---

### FS-P1-20 — Playbook ingest: parcijalni upis pri prijavljenom potpunom otkazu

| Polje | Vrednost |
|---|---|
| **FILE** | `drafting/playbook.py`, `interni_stavovi.py` |
| **LINE** | `drafting/playbook.py:92-97`; `interni_stavovi.py:87-92` |
| **FUNCTION** | `ingest_playbook` / `ingest_stav` |
| **Okidač** | Batch 1 prođe, batch 2 padne |
| **Tvrđeni ishod** | HTTP 500 — „ništa nije sačuvano" |
| **Stvarni ishod** | Vektori batch-a 1 su **trajno** u Pinecone-u. ID-jevi nose `uuid4()` (`:82`/`:76`), pa svaki ponovni pokušaj dodaje **novi duplirani set** koji se ne može ukloniti osim `delete_all`. |
| **Gubitak podataka** | Obrnuta laž — rečeno da je palo, podatak delimično upisan i neuklonjiv |
| **Test** | `tests/test_playbook.py` pokriva samo srećan put |
| **Kanonska popravka** | Skupljati upisane ID-jeve i rollback-ovati pri parcijalnom otkazu. |

---

### FS-P1-21 — `shared/vector_deletion.py` je ispravan i potpuno nepozvan; GDPR čl. 17 za dokumenta predmeta nije implementiran

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/vector_deletion.py` |
| **LINE** | `:126` (`obrisi_vektore_dokumenta`) |
| **Stvarni ishod** | Jedini fail-closed, verifikovani, per-dokument brisač vektora u repou nema **nijednog** produkcijskog pozivaoca (grep: samo `tests/test_pine01_vector_deletion.py`). Uz to, **ne postoji nijedan endpoint koji briše red iz `predmet_dokumenti`.** |
| **GDPR** | **Da** — sposobnost je dokumentovana (docstring `:8-11`), a nije povezana ni sa čim |
| **Kanonska popravka** | Napraviti `DELETE /api/predmeti/{id}/dokumenti/{doc_id}` koji poziva ovaj modul. |

---

### FS-P1-22 — `ingest_misljenja.py`: `✓ Ingest završen` i exit 0 uz odbačene batch-eve

| Polje | Vrednost |
|---|---|
| **FILE** | `ingest_misljenja.py` |
| **LINE** | `:243-246` (`except → continue`), `:249` (`zip` bez provere), `:270` |
| **Okidač** | Greška embedding-a |
| **Stvarni ishod** | `BATCH_SIZE = 50` → 50 mišljenja odbačeno po batch-u; skripta ispisuje `✓ Ingest završen` i **izlazi sa kodom 0**, pa je i CI zelen |
| **Gubitak podataka** | Da |
| **Kanonska popravka** | Brojati `skipped` i `sys.exit(1)` kad nije nula. |

---

### FS-P1-23 — `--force` u `ingest_misljenja.py` briše tuđi namespace i nastavlja pri otkazu

| Polje | Vrednost |
|---|---|
| **FILE** | `ingest_misljenja.py` |
| **LINE** | `:217-225` |
| **Stvarni ishod** | `idx.delete(delete_all=True, namespace="misljenja")`. Isti namespace piše i `routers/batch_ingest.py` (`ALLOWED_NAMESPACES`, `:28`). Ovo je **tačno scenario koji `shared/vector_deletion.py::dozvoli_globalno_brisanje` (`:257-300`) postoji da odbije** — a skripta ga ne poziva. Pri otkazu brisanja nastavlja dalje i pravi duplikate. |
| **Gubitak podataka** | Da (tuđi vektori) |
| **Kanonska popravka** | Rutirati kroz `dozvoli_globalno_brisanje`; prekinuti pri otkazu. |

---

### FS-P1-24 — SEF: e-faktura poslata Poreskoj upravi bez zapisa

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/sef.py` |
| **LINE** | `:501-504` (`except → logger.warning`), `:508-512` (return) |
| **FUNCTION** | `sef_posalji` |
| **Okidač** | `sef_log` insert padne posle uspešnog slanja na SEF |
| **Tvrđeni ishod** | `{"ok": True, "sef_id": ..., "sef_status": ...}` |
| **Stvarni ishod** | Faktura je **stvarno poslata** poreskom sistemu, a lokalno ne postoji nikakav zapis o tome (`sef_log` ima 0 redova). |
| **Gubitak podataka** | **Da** — poreski/pravni trag |
| **Gubitak novca** | Posredno (nemogućnost rekonstrukcije, rizik dvostrukog slanja) |
| **Test** | Ne |
| **Kanonska popravka** | Upisati log **pre** vraćanja; ako ne uspe, 500 sa jasnom porukom da je slanje uspelo ali nije evidentirano. |

---

### FS-P1-25 — Enterprise delegiranje predmeta: `ok: true` bez provere insert-a

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/enterprise.py` |
| **LINE** | `:257-265` (insert), `:268` (return) |
| **FUNCTION** | `delegiraj_predmet` |
| **Stvarni ishod** | `predmet_delegiranja` insert bez provere `.data`; nula-red insert prijavljuje uspešno delegiranje. Kolega nikad ne dobije predmet, a onaj ko je delegirao misli da jeste. |
| **Gubitak podataka** | Da (delegacija) |
| **Test** | `tests/test_enterprise_delegation.py` pokriva authz, ne ishod upisa |
| **Kanonska popravka** | `if not r.data: raise HTTPException(500)`. |

---

### FS-P1-26 — Klijentov upload: fajl ostaje u bucket-u posle „obrisano"

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/client_portal.py` |
| **LINE** | `:776-782` |
| **FUNCTION** | `client_portal_obrisi_upload` |
| **Stvarni ishod** | `supa.storage.from_("portal-uploads").remove([...])` je u `try/except → logger.warning`. DB red se briše (i to je **ispravno** provereno na `:800`), blob ostaje. Uz to, `remove()` u supabase-py vraća listu i **ne baca** za nepostojeću putanju, pa ni „uspeh" ništa ne dokazuje. |
| **GDPR** | Da (zadržavanje posle brisanja) |
| **Poverljivost** | Ograničena — bucket je **privatan** (sonda potvrdila) |
| **Kanonska popravka** | Verifikovati listu uklonjenih objekata pre brisanja DB reda. |

---

### FS-P1-27 — Frontend: dokaz se „doda", tekst nestane, ništa nije sačuvano

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` |
| **LINE** | `:18942-18946` |
| **FUNCTION** | `evidence_addDokaz` |
| **Stvarni ishod** | `.then(function(r){ return r.json(); }).then(function(){ evidence_load(); showToast('Dokaz dodat ✓'); })` — `r.ok` se nikad ne gleda, i **nema `.catch()`**. Tekst tvrdnje je došao iz `prompt()` i nepovratan je. |
| **Gubitak podataka** | **Da** |
| **Laže li se korisniku** | Da |
| **Dokaz da je propust** | Susedna `evidence_reklasifikuj` (`:18930-18936`) **proverava** `d.ok` i **ima** `.catch` |
| **Kanonska popravka** | `if (!r.ok) throw` + `.catch` sa err toast-om. |

---

### FS-P1-28 — Frontend: komentar na predmet se briše iz polja pre potvrde servera

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` |
| **LINE** | `:4515-4522` |
| **FUNCTION** | `dodajKomentar` |
| **Stvarni ishod** | Nema provere `r.ok`, **prazan `catch(e) {}`**, a `inp.value = ''` (`:4520`) se izvršava pre bilo kakve potvrde. Otkucan komentar je izgubljen. |
| **Gubitak podataka** | **Da** |
| **Kanonska popravka** | Čistiti polje tek unutar `r.ok` grane. |

---

### FS-P1-29 — Frontend: naplativi sati se brišu pre nego što se sačuvaju

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` |
| **LINE** | `:11237` vs `:11254-11271` |
| **FUNCTION** | `timer_stop` |
| **Stvarni ishod** | Toast **jeste iskren** (`:11271` javlja grešku), ali je `localStorage.removeItem(key)` (`:11237`) i reset prikaza (`:11244`) izvršen **pre** POST-a. Kad POST padne, izmereno naplativo vreme je nepovratno. |
| **Gubitak podataka** | **Da — naplativi sati** |
| **Gubitak novca** | **Da, direktno** |
| **Kanonska popravka** | `localStorage.removeItem` samo unutar `r.ok` grane. |

---

### FS-P1-30 — Frontend: prihvatanje Uslova korišćenja se ne evidentira

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` |
| **LINE** | `:778-784` |
| **FUNCTION** | `tosAccept` |
| **Stvarni ishod** | `await fetch('/api/tos/accept', ...)` bez provere `.ok`, **prazan `catch(e) {}`**, overlay se zatvara bezuslovno. Server možda nema zapis o prihvatanju. `tos_acceptances` ima 2 reda. |
| **Gubitak podataka** | Pravni zapis |
| **Laže li se korisniku** | Da |
| **Kanonska popravka** | Zadržati overlay i ponuditi ponovni pokušaj pri otkazu. |

---

### FS-P1-31 — Frontend: GDPR saglasnost za benchmarking se prikaže kao promenjena bez servera

| Polje | Vrednost |
|---|---|
| **FILE** | `static/vindex.js` |
| **LINE** | `:23689-23694` |
| **FUNCTION** | `profitabilnost_toggleOptIn` |
| **Stvarni ishod** | Nema provere `.ok`; checkbox je već prebačen od strane browsera i nikad se ne vraća. UI pokazuje „isključeno", server drži „uključeno" do reload-a. |
| **GDPR** | **Da** — stanje saglasnosti se razilazi |
| **Kanonska popravka** | Vratiti checkbox i prikazati grešku ako `!r.ok`. |

---

### FS-P1-32 — `UsageService.refund` odbacuje `-1`; **svaki** refund u proizvodu je neproveren

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/usage.py` |
| **LINE** | `:713`; kontrakt `shared/deps.py:649` |
| **FUNCTION** | `UsageService.refund` |
| **Okidač** | Refund koji ne pogodi nijedan red |
| **Tvrđeni ishod** | Krediti vraćeni |
| **Stvarni ishod** | `await asyncio.to_thread(_refund_n_credits, user_id, credits)` — povratna vrednost se **odbacuje**, a `_refund_n_credits` vraća **`-1` kada nije vraćen nijedan kredit** (`shared/deps.py:649`). `refund()` vraća `None` u oba slučaja. |
| **Gubitak novca** | **Da — na štetu korisnika.** Jedina kompenzaciona putanja u celom proizvodu (`routers/copilot.py:1489`, `:1493` — jedini ruter sa refund-om od 50 rutera koji imaju `consume`) izgrađena je na primitivu koji laže. |
| **Laže li se korisniku** | Da |
| **Test** | Ne |
| **Mutation test** | **Da, prioritetno** |
| **Kanonska popravka** | Vratiti stanje; `logger.error` + Sentry na `-1`. Svaka buduća refund popravka mora čekati ovu, inače se gradi na laži. |

---

### FS-P1-33 — SEF: neevidentirana poreska prijava obara zaštitu od dvostrukog podnošenja

> Nadogradnja FS-P1-24 nakon dodatne analize — isti kod, teža posledica.

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/sef.py` |
| **LINE** | `:501-504` (swallow), `:508-512` (return), dedup zaštita na `:414-422`, fail-closed blok na `:426-439` |
| **FUNCTION** | `sef_posalji` |
| **Okidač** | SEF prihvati fakturu (**stvarno podnošenje Poreskoj upravi**), zatim `sef_log` insert padne |
| **Tvrđeni ishod** | `{"ok": True}`, poruka: *„Faktura br. … je uspešno poslata na SEF. ID: …"* |
| **Stvarni ishod** | Faktura JESTE podneta, ali lokalnog zapisa nema. Dedup zaštita na `:414-422` traži `sef_status IN ("Sent","Approved")` — **ne nađe ništa** i **dozvoli ponovno podnošenje**. Time se poništava tačno ono što fail-closed blok na `:426-439` postoji da spreči, 80 linija niže. |
| **Gubitak novca** | **Da, i nepovratno kod trećeg lica** — duplirana e-faktura se poništava isključivo ručnim storniranjem kod Poreske uprave |
| **Laže li se korisniku** | Da |
| **Povezano** | `routers/sef.py:203` — `urlopen(..., timeout=30)` koji istekne **posle** što je SEF prihvatio vraća `ok: False`, korisnik ponovi, duplikat. Ista neidempotentnost. |
| **Test** | `tests/test_sef.py` pokriva samo `test_get_sef_log`; grana otkaza log-insert-a nije pokrivena |
| **Kanonska popravka** | Ako log insert padne posle uspešnog slanja → **502 sa eksplicitnom porukom „podneto ali neevidentirano — proverite pre ponovnog slanja"**, nikad `ok: True`. |

---

### FS-P1-34 — Partner API `/v1/analyze`: nemeren `gpt-4o` iza brojača koji se nikad ne resetuje

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/integracije.py` |
| **LINE** | `:213` (endpoint), `:123` (`model="gpt-4o", max_tokens=1500`), `:89-106` (jedini gate) |
| **FUNCTION** | `post_v1_analyze` / `_resolve_key` |
| **Okidač** | Svaki poziv sa `X-Vindex-Key`, `30/minute` |
| **Tvrđeni ishod** | Merena partnerska API potrošnja |
| **Stvarni ishod** | **Nula `UsageService.consume` u celom fajlu.** Jedina zaštita je `broj_poziva`, koji je: (a) read-modify-write sa izgubljenim ažuriranjem, (b) `except: pass` na `:105-106`, (c) `_API_DAILY_LIMIT` (500) koji se **nigde u repou ne resetuje** — nema cron-a, nema job-a; migracija `019` ga postavi na 0 jednom. |
| **Gubitak novca** | **Da** — 1.800 `gpt-4o` poziva na sat po ključu ≈ **$36/h po ključu**, uz brojač koji podbroji pod konkurentnošću i tiho ne upiše pri DB grešci |
| **Test** | `tests/test_integracije.py` postoji; **ništa ne tvrdi ni brojač ni naplatu** |
| **Kanonska popravka** | `UsageService.consume` posle `_resolve_key`; brojač kao atomičan RPC; dnevni reset job. |

---

### FS-P1-35 — Realtime glas: neograničeno trajanje, 0 kredita, **bez prompt guard-a**

| Polje | Vrednost |
|---|---|
| **FILE** | `services/voice_orchestrator.py` |
| **LINE** | `:531-537` (`websockets.connect` na `wss://api.openai.com/v1/realtime`), gate na `routers/voice_realtime.py:114`, `:148` |
| **FUNCTION** | `_connect_realtime` |
| **Okidač** | Svaka realtime glasovna sesija |
| **Tvrđeni ishod** | Funkcija zaštićena tier proverom i limitom konkurentnih sesija |
| **Stvarni ishod** | Sirov WSS **zaobilazi monkeypatch iz `shared/ai_client.py` u potpunosti** (komentar u samom fajlu na `:250` to priznaje). Posledica: **nema prompt guard-a, nema Response Firewall-a**, nema wrapper-provenance-a. Nema ograničenja trajanja i nema naplate za `gpt-4o-realtime-preview` — najskuplju modalnost u proizvodu. |
| **Gubitak novca** | **Da, neograničen** |
| **Poverljivost** | **Da** — poverljivi sadržaj predmeta ide ka modelu bez ijedne od dve deklarisane kontrole sadržaja |
| **Kontrast** | `routers/voice.py` (HTTP transkripcija/TTS) **naplaćuje** na `:452`, `:489`, `:541` |
| **Test** | Ne |
| **Kanonska popravka** | Naplata po minutu audija iz teardown-a sesije; propustiti audio transkript kroz prompt guard. |

---

### FS-P1-36 — Profitabilnost: kredit naplaćen, a sirov Python izuzetak se servira kao „finansijska analiza"

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/profitabilnost.py` |
| **LINE** | `:321` (naplata) → `:346` (rad) → `:366-368` (otkaz); plus `:181` + `:191-192` |
| **FUNCTION** | `profitabilnost_ai_analiza` / `profitabilnost_predmeta` |
| **Okidač** | OpenAI ispad |
| **Tvrđeni ishod** | HTTP **200** sa poljem `analiza` koje frontend renderuje kao analizu |
| **Stvarni ishod** | `analiza = f"Greška pri AI analizi: {e}"` — **sirov tekst Python izuzetka se prikazuje advokatu kao finansijska analiza predmeta**. Kredit je već potrošen na `:321`, refund putanje nema. |
| **Gubitak novca** | **Da** — 1 kredit po otkazu; tokom ispada svaki ponovni pokušaj troši još jedan |
| **Laže li se korisniku** | **Da** |
| **Dodatno** | `:181` poziva `_ai_profitabilnost_preporuka` (1× `gpt-4o-mini`) sa **samo** `Depends(get_current_user)` — bez `PermissionService`, bez `consume`, `30/minute` — a `:191-192` je `except Exception: pass`, pa se novac potroši i otkaz ne ostavi nikakav trag. |
| **Test** | Ne |
| **Kanonska popravka** | `UsageService.refund` u `except` + `raise HTTPException(502)`; nikad ne servirati tekst greške kao sadržaj. |

---

### FS-P1-37 — Naplata bez refund-a: `source_of_funds`, `web3`

| Polje | Vrednost |
|---|---|
| **FILE / LINE** | `routers/source_of_funds.py:72` (naplata, **2 kredita** na PRO) → `:84-86` (500, bez refund-a); `routers/web3.py:573` (naplata, komentar *„Deduciraj kredite PRE GPT poziva"*) → `:640`, `:644-648` (`gpt-4o`, `max_tokens=4000`, bez refund-a) |
| **Tvrđeni ishod** | Iskren HTTP 500 |
| **Stvarni ishod** | Korisnik je iskreno obavešten o grešci, ali je **tiho ostao bez kredita** |
| **Gubitak novca** | Da |
| **Kanonska popravka** | Refund pre `raise`. Napomena: to zahteva prethodnu popravku FS-P1-32. |

---

### FS-P1-38 — `timer_stop`: naplativi sati uništeni, odgovor `success: True`

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/billing.py` |
| **LINE** | `:457-461` (update tajmera), `:469-479` (insert stavke + return) |
| **FUNCTION** | `timer_stop` |
| **Tvrđeni ishod** | `{"success": True, ..., "entry": null}` |
| **Stvarni ishod** | `entry = er.data[0] if er.data else None` — kad `billing_entries` insert ne proizvede red, funkcija svejedno vraća `success: True` sa `entry: null`. Tajmer je zaustavljen, **izmereni naplativi sati ne postoje nigde**. `timer_sessions` update rezultat se takođe ne proverava, pa tajmer može ostati `aktivan=True`. |
| **Gubitak podataka** | **Da — naplativi sati** |
| **Gubitak novca** | **Da, direktno** |
| **Sadejstvo** | Uparuje se sa FS-P1-29 (frontend briše `localStorage` pre POST-a) — obe strane ugovora gube isti podatak istovremeno |
| **Test** | Ne |
| **Kanonska popravka** | `if not er.data: raise HTTPException(500)`. Isti guard već **ispravno** postoji na `billing.py:275`, `:318`, `:343`, `:888` i `tarife.py:155`, `:221`, `:342`, `:373`. |

---

### FS-P1-39 — Izveštaji naplate: neuspeo upit se prikazuje kao „nemate nenaplaćenih potraživanja"

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/billing_reports.py`, `routers/billing.py` |
| **LINE** | `billing_reports.py:88-91`, `:187-189`, `:248-249`, `:335-336`, `:421-422`, `:564-565`; `billing.py:930-931`, `:975-976`, `:1026-1027`, `:1100-1102` |
| **FUNCTION** | `_safe` i srodne |
| **Okidač** | Bilo koji otkaz upita u `asyncio.gather(..., return_exceptions=True)` |
| **Tvrđeni ishod** | `{"naplaceno_rsd": 0.0, "ukupno_nenaplaceno_rsd": 0.0, "neizmireno": 0.0}` |
| **Stvarni ishod** | `return [] if isinstance(r, Exception) else (r.data or [])` — **~11 grana, nijedna ne loguje**. Aging izveštaj kaže advokatu da nema dugovanja kada je upit prosto pao. |
| **Gubitak novca** | **Da, posredno ali stvarno** — nenaplaćena potraživanja koja niko ne vidi |
| **Laže li se korisniku** | **Da** |
| **Test** | `tests/test_billing_reports.py` pokriva samo srećan put |
| **Kanonska popravka** | `logger.error` po palom kraku + `nepotpuno: true` po sekciji, koji UI **mora** renderovati. |

---

### FS-P1-40 — Broj fakture se tiho resetuje na `0001`

| Polje | Vrednost |
|---|---|
| **FILE** | `routers/billing.py` |
| **LINE** | `:583-584` |
| **FUNCTION** | `_sledeci_broj_fakture` |
| **Okidač** | Bilo koja tranzijentna greška čitanja |
| **Tvrđeni ishod** | Sledeći broj u nizu |
| **Stvarni ishod** | `except Exception: seq = 1` — **goli `except`, bez ijednog loga**, na funkciji koja dodeljuje **pravni broj fakture**. Numeracija tiho kreće ispočetka: ili kolizija (`23505` → potrošeni pokušaji), ili — u `konvertuj_proformu:741`, koji nema retry — tvrdi 500. |
| **Gubitak novca** | Da (integritet pravnog niza faktura) |
| **Laže li se korisniku** | Da |
| **Test** | Delimično — `tests/test_lambda008_certification.py` pokriva trku, ne ovaj `except` |
| **Kanonska popravka** | `logger.error` + re-raise. Pravni niz se nikad ne sme tiho resetovati. |

---

### FS-P1-41 — Nemereni AI pozivi: `legal_reasoning`, `hearing_cc` bez `record_cost`

| Polje | Vrednost |
|---|---|
| **FILE / LINE** | `routers/legal_reasoning.py:29-33` → `services/legal_reasoning_engine.py:178` (`gpt-4o`, `max_tokens=2500`, `10/minute`, samo `get_current_user`); `routers/hearing_cc.py:373` + `:468` |
| **Stvarni ishod (legal_reasoning)** | Nema `PermissionService`, nema `consume`. ~$0.03 po pozivu × 600/h. |
| **Stvarni ishod (hearing_cc)** | Oba „knjigovodstvena" poziva postoje (`begin_cost_tracking()` na `:373`, `log_cost_to_db` na `:468`), ali fajl sadrži **0 poziva `record_cost`** — koristi sopstveni `AsyncOpenAI` na `:387`/`:570`. `_request_costs` ostaje prazan → `log_cost_to_db` izađe na `shared/cost.py:85` → **nijedan red se ne upiše, a sve izgleda instrumentovano.** |
| **Sistemski obim** | `begin_cost_tracking()` postoji na **4** mesta, `record_cost()` na **3**, u aplikaciji sa ~500 endpoint-a. `api_costs` uz to **ne postoji** i **nema nijednog čitaoca u celom kodu** — nijedan ekran u proizvodu nikad ne prikazuje stvarnu OpenAI potrošnju. |
| **Test** | Ne — svi cost testovi **mock-uju** `log_cost_to_db`, pa nijedan ne može uhvatiti ovo |
| **Kanonska popravka** | Premestiti `record_cost` u sam monkeypatch (`shared/ai_client.py`), gde se ne može zaboraviti. |

---

### FS-P1-42 — `ai_fabric` shadow provider: duplira trošak, i nosi ne-OpenAI SDK-ove van guard-a

| Polje | Vrednost |
|---|---|
| **FILE** | `shared/ai_fabric.py` |
| **LINE** | `:587-603` (`_run_shadow`), `:309` (`anthropic.Anthropic`), `:366` (`google.generativeai`) |
| **Okidač** | Postavljen env `AI_FABRIC_SHADOW_PROVIDER` |
| **Tvrđeni ishod** | Besplatna observability |
| **Stvarni ishod** | **Udvostručuje trošak provajdera po zahtevu**, rezultat se odbacuje, otkaz se loguje na `info`, nema `consume`, nema `api_costs`. Uz to `AnthropicProvider` i `GeminiProvider` koriste **ne-OpenAI SDK-ove**, koje monkeypatch iz `shared/ai_client.py` po konstrukciji ne može presresti → **nula prompt guard-a, nula `ai_forensics`**. |
| **REACHABLE DANAS** | **NE** — `ai_fabric` nema produkcijskih pozivalaca; `tests/test_ai_fabric_governance.py:104` upravo to i tvrdi |
| **Kanonska popravka** | Provući `AIGateway.generate` kroz `UsageService.consume` i dodati guard ne-OpenAI adapterima **pre** nego što se pojavi prvi produkcijski pozivalac. |

---

## 4. FS-P2 — POUZDANOST I OBSERVABILITY (26)

| # | FILE:LINE | FUNCTION | Tvrđeni ishod | Stvarni ishod | Popravka |
|---|---|---|---|---|---|
| P2-01 | **sistemski**: 128 sirovih `asyncio.create_task(` naspram 6 upotreba `shared/bg.py::spawn` | — | „posao je zakazan" | Bez jake reference task može biti GC-ovan usred rada; bez `add_done_callback` izuzetak se nikad ne pročita. Modul `shared/bg.py` je napisan tačno za ovo i **iskorišćen je u 6 od 134 mesta**. | Mehanička zamena; lint pravilo koje zabranjuje sirov `create_task` |
| P2-02 | `shared/audit.py:14-19, 48` | `AuditMiddleware.dispatch` | audit destruktivnih radnji na predmeti/klijenti/billing/gdpr | DB grana je gejtovana kroz `_AUDIT_PATHS` **pre** `_DB_AUDIT_PATHS`. `/api/gdpr` nije u `_AUDIT_PATHS`. Stvarni prefiksi rutera su `/billing` i `/klijenti/{id}`, ne `/api/billing`/`/api/klijenti`. **Samo `/api/predmeti` ikad prođe.** | Razdvojiti dve liste; uskladiti sa stvarnim prefiksima |
| P2-03 | `shared/audit.py:49` | isto | audit zakazan | sirov `create_task`, van `bg` registra | `shared.bg.spawn` |
| P2-04 | `shared/audit.py:72` | `_db_audit` | audit upisan | `except → logger.debug`, bez Sentry-ja | `logger.error` + Sentry |
| P2-05 | `shared/audit_immutable.py:256-258` | `log_action` | zapisano | akcija van `AUDITABLE_ACTIONS` vraća `None` — identično uspehu bez id-a | Razlikovan sentinel; assert u ne-prod |
| P2-06 | `shared/audit_immutable.py:267-272, 293-297, 402-408` | `log_action` / `_build_and_insert` | zapisano | `None` i za grešku i za nula-red insert; **nijedan produkcijski pozivalac ne gleda povratnu vrednost** | Vratiti `bool`/dići izuzetak |
| P2-07 | `security/chain_anchor.py:141-146, 186-195` | `_persist_anchor` / `_load_anchor` | `{"anchored": True}` | Default `ANCHOR_BACKEND="stdout"` (`:42`) → ništa se trajno ne čuva; `_load_anchor` vraća `None` za stdout i file, pa `verify_anchor` **nikad** ne može uspeti | `anchored: False` ako backend ne podržava verifikaciju |
| P2-08 | `security/chain_anchor.py:110-121` | `_compute_root_hash` | root hash dana | `select` bez `.limit()` — PostgREST `max-rows` može tiho odseći dan. **UNKNOWN** (zavisi od deploy konfiguracije) | Eksplicitna paginacija |
| P2-09 | `security/ai_forensics.py:118-132, 171-181` | `_persist` / `log_ai_call_sync` | forenzički red upisan | `except → logger.debug`; `daemon=True` nit se ubija na svaki SIGTERM bez drenaže. **Mrtav kod** — docstring `:184-196` i grep potvrđuju: nijedan od ~130 AI poziva ih ne koristi | Ukloniti ili povezati |
| P2-10 | `security/ai_forensics.py:370-415` | `log_provenance_from_wrapper` | provenance upisan | `logger.error` (bar je error) ali bez trajnog reda. **Podnalaz:** `:374` izbacuje `None` vrednosti, a `migrations/043:82` deklariše `user_id UUID NOT NULL` → **svaki AI poziv izvan request konteksta (workeri, cron, intake worker) gubi ceo provenance red** | Durable outbox; dozvoliti `user_id NULL` ili sintetički system uid |
| P2-11 | `security/anomaly_detection.py:255-282` | `_log_anomaly` | anomalija zabeležena | oba upisa (`security_events` + `audit_immutable`) u **jednom** `try` → otkaz prvog preskače drugi; `except → logger.debug` | Razdvojiti; `logger.error` |
| P2-12 | `security/anomaly_detection.py:142` | `check_anomaly` | zabeleženo | sirov `create_task` | `shared.bg.spawn` |
| P2-13 | `security/anomaly_detection.py:210-252` | `_check_db_profile` | baseline detekcija radi | RPC greška → `AnomalySignal(score=0.0)`; detekcija tiho oslabi na samo apsolutne pragove | `logger.warning` + „baseline nedostupan" flag |
| P2-14 | `routers/conflict_check.py:354-378` | `check_conflict` | verdikt o konfliktu | Lažno-čisto je zatvoreno kad je `konflikti` prazno, ali sa ≥1 pogotkom i palim slojem `poruka` ne kaže da je pretraga nepotpuna, iako `provera_potpuna: false` jeste u JSON-u | Prefiksovati `poruka` upozorenjem u svakoj grani |
| P2-15 | `routers/conflict_check.py` (ceo fajl) | `check_conflict` | provera izvršena | Nula audit redova. `Akcija.CONFLICT_FLAGGED` postoji (`klijenti/audit.py:30`) i koristi se drugde, ovde ne | `log_event` na svaki ne-čist ishod |
| P2-16 | `routers/sesije.py:174-182` | `odjavi_sesiju` | `{"status":"ok","poruka":"Sesija odjavljena"}` | `.delete()` u `try/except → logger.warning`, rezultat neproveren. Slot se ne oslobodi; korisnik veruje da je odjavio uređaj | Proveriti `.data`; 500 pri otkazu |
| P2-17 | `routers/sesije.py:43, 73` | `_ocisti_stare` / `_upsert_sesija` | sesija evidentirana | rezultat neproveren | isto |
| P2-18 | `routers/billing.py:697-698` | `faktura_create` | 409 korisniku | Rollback `fakture.delete()` u `except Exception: pass`. Pri otkazu rollback-a ostaje **orphan faktura sa potrošenim pravnim brojem** i nijednom stavkom, potpuno nezabeležena (za razliku od 500-grane na `:689-692` koja bar loguje `ORPHANED`) | Isti `logger.error("ORPHANED")` tretman |
| P2-19 | `routers/admin_dashboard.py:142-155` | `notification_log_retry` | `{"ok": ok, ...}` | `notification_log` insert progutan; `notification_log` ima 0 redova | Provera `.data` |
| P2-20 | `routers/portal_monitoring.py:528-531` | `manual_update` | `{"ok": True, "status": novi}` | `praceni_predmeti` update progutan | Provera `.data` |
| P2-21 | `routers/learning.py:264-287, :316` | `zabeleži_ishod` | `{"ok": True, "ishod": ...}` | Progutan i sam `predmeti.update({"status": novi_status})` — status predmeta se ne promeni, a korisnik vidi potvrdu ishoda | Provera `.data` na statusnom update-u |
| P2-22 | `routers/predmeti_close.py:176-216, :221` | `zatvori_predmet` | `{"ok": True, ...}` | Progutani `predmet_hronologija` insert, `case_benchmarks` insert, `case_actions` update | Delimični ishod u odgovoru |
| P2-23 | `routers/onboarding.py:203-291` | `kreiraj_demo_predmet` | `{"ok": True, "predmet_id": ...}` | 5 progutanih upisa (`klijenti`, `predmet_klijenti`, `predmet_hronologija`, `zadaci`, `predmet_dokumenti`); demo predmet može biti prazna ljuska na prvom utisku | Delimični ishod |
| P2-24 | `routers/client_portal.py:334-347, 680-693` | `lista_portal_tokena` / `client_portal_lista_uploada` | 200 + prazna lista + poruka *„Tabela … ne postoji — pokrenite SQL migraciju"* | Poruka tvrdi uzrok koji nikad nije proveren; „nema aktivnih linkova" je suprotno od istine tokom ispada | 503 ili `nepotpuno: true` |
| P2-25 | `routers/client_portal.py:237-257` | `generiši_portal_token` | 404 „predmet nije pronađen" | `except: pass` oko provere vlasništva. **Danas pada zatvoreno** (nema breše), ali „nisi saradnik" je neodvojivo od „nismo mogli da proverimo" | 503 umesto kolapsa u 404 |
| P2-26 | `routers/import_klijenti.py:183-188, 236-251` | `import_execute` | `uvezeno: N` | (a) otkaz dohvata postojećih email-ova tiho **isključi deduplikaciju**; (b) jedan loš red obori ceo batch od 25 i svih 25 ide u `greske` **bez identiteta u `detalji`** | Per-red obrada i identitet u izveštaju |

---

## 5. FS-P3 — KOZMETIKA (7)

| # | FILE:LINE | FUNCTION | Nalaz |
|---|---|---|---|
| P3-01 | `static/vindex.js:23316` | `zadaci_obrisi` | `showToast('Zadatak obrisan.')` bez `.ok`; red se vrati pri sledećem `load` |
| P3-02 | `static/vindex.js:23795` | `portalUkloni` | isto |
| P3-03 | `static/vindex.js:2689` | `sms_deaktiviraj` | isto |
| P3-04 | `static/vindex.js:15475` | `emailNotifDeaktivaj` | isto |
| P3-05 | `static/vindex.js:13636` | `portal_oznacPregledano` | PATCH bez `.ok`, prazan `catch` |
| P3-06 | `static/vindex.js:6297-6307` | `copyPodnesak` | `_podnesakEdited = false` pre `fetch(...).catch(()=>{})`; gubi se signal za učenje |
| P3-07 | `static/vindex.js:15908-15917` | `onboardingDismiss` | `localStorage.setItem` pre `fetch(...).catch(()=>{})` |

> Ispravan referentni obrazac u istom fajlu: `portal_obrisiUpload` (`:13646-13651`) i `rocisteObrisi` (`:14536-14538`).

---

## 6. NALAZI KOJE SU TESTOVI **UČVRSTILI** (najopasnija kategorija)

Test koji tvrdi pogrešno ponašanje je gori od nepostojećeg testa — svaka buduća ispravka će oboriti CI i biti vraćena.

| Test | Šta tvrdi | Zašto je pogrešno |
|---|---|---|
| `tests/test_cross_doc.py:228::test_sync_gpt_invalid_json_ne_pada` | prazan rezultat pri neuspelom parsiranju je ispravan | učvršćuje FS-P1-01 — „nema konflikata" kao laž |
| `tests/test_evidence_klasifikacija.py:93::test_never_raises_even_if_both_fail` | oba pala upisa ne smeju dići grešku | učvršćuje FS-P1-14 — naplata za nulti upis |
| `tests/test_batch_ingest.py:248::test_run_ingest_sync_sets_running_then_done` | `done` je očekivan ishod | učvršćuje FS-P1-17 — `done` pri delimičnom upisu |
| `tests/test_gdpr_delete.py` | 200 + dodirnute tabele | ne tvrdi da je ijedan red promenjen (FS-P1-07) |
| `tests/test_lambda003_klijenti_role_fail_closed.py` | fail-closed rola | testira **drugu** kopiju; `klijenti/permissions.py` nikad nije zakrpljen (FS-P0-04) |

---

## 7. POTVRDA RANIJE POZNATIH NALAZA

| Poznati nalaz | Status | Dopuna iz ovog sweep-a |
|---|---|---|
| `shared/cost.py:108` — `APIError` progutan, `api_costs` ne postoji | **POTVRĐEN** sondom (`PGRST205`) | FS-P1-11 |
| `/api/feedback` upisuje `q_hash` koji ne postoji, vraća `{"status":"ok"}` | **POTVRĐEN** sondom (`42703`) | Jedini `return`-uspeh-iz-`except` u repou; `feedback` ima 1 red |
| `static/vindex.js:8068` — `reported_errors` ne postoji | **POTVRĐEN** sondom (`PGRST205`) | **KOREKCIJA:** kod **ispravno** čita `_upis.error`. Stvarni defekti su (a) sirov engleski PostgREST tekst korisniku i (b) `return` na `:8079` preskače `/api/feedback` fallback na `:8082` |
| `POST /api/briefing/cron` vraća `{"ok": true, "poslato": 0}` | **POTVRĐEN** | Uzrok dokazan: `rokovi` ne postoji; `"ok": True` je hardkodovan |
| `zadaci/ai-analiziraj` guta grešku, šalje „Nadolazeći rokovi: nema", naplati kredit | **POTVRĐEN** | Uzrok dokazan: `rokovi` `PGRST205`; naplata na `:789` |
| `praksa_fetch_ratios` — do 20 `gpt-4o-mini` bez `UsageService.consume`, sirov `OpenAI()` | **POTVRĐEN I POGORŠAN** | `ratio_decidendi` **ne postoji** → keš nikad ne radi → **svaki prikaz plaća iznova, zauvek**; `20/min × 20` = do 400 poziva/min/korisnik |
| `feature_usage_log` 0 redova vs `usage_events` 2.906 | **POTVRĐEN** sondom | Kolone iz migracije 112 **postoje** → uzrok NIJE nedostajuća kolona; `logger.debug` ga krije |
| `ingest_misljenja.py` / `law_upload.py` — `except → continue` | **POTVRĐEN** | FS-P1-17, FS-P1-22; dodatno `auto_discovery.py` sa gorim oblikom (nulti vektori) |

---

## 8. PREPORUČENI REDOSLED

1. **FS-P0-01** — provera sukoba interesa. Jedini nalaz sa potencijalom gubitka licence.
2. **FS-P1-33** — SEF dvostruko podnošenje. Jedini nalaz čija se posledica **ne može poništiti unutar sistema** (traži ručno storniranje kod Poreske uprave).
3. **FS-P1-01** — cross-doc „nema konflikata". Laž o pravnom sadržaju, uz naplatu, uz test koji je učvršćuje.
4. **FS-P1-32** — `refund` odbacuje `-1`. **Mora prva od svih naplatnih popravki**, jer bi se FS-P1-36 i FS-P1-37 inače gradile na primitivu koji laže.
5. **FS-P1-04 / FS-P1-05** — kreirati ili ukloniti `rokovi`. Rokovi su srce advokatske prakse.
6. **FS-P1-34 / FS-P1-35** — nemeren `gpt-4o` na partner API-ju i neograničen realtime glas (koji uz to nema prompt guard).
7. **FS-P1-07 / FS-P1-08 / FS-P1-09 / FS-P1-10** — GDPR i integritet audita.
8. **FS-P1-38 / FS-P1-29 / FS-P1-39 / FS-P1-40** — naplativi sati, izveštaji potraživanja, broj fakture.
9. **FS-P0-03 / FS-P1-18 / FS-P1-19** — obrisano ostaje pretraživo.
10. **Sekcija 6** — obrnuti 5 testova koji učvršćuju bagove **pre** bilo koje popravke, inače će ispravke biti vraćene kao „regresija".
11. **P2-01** — mehanička zamena 128 sirovih `create_task` sa `shared.bg.spawn` + lint pravilo.

---

## 9. METODOLOŠKE NAPOMENE I GRANICE OVOG SWEEP-a

- **Šta je dokazano sondom:** postojanje/nepostojanje 153 tabele, 10 kolona, 2 storage bucket-a, broj redova, i distribucija `ai_forensics.endpoint`. Ovo su tvrde činjenice, ne procene.
- **Šta je dokazano statičkom analizom (AST):** svi brojevi u tabeli „sistemski obim". Skript je deterministički i ponovljiv.
- **Šta NIJE dokazano:** nijedan nalaz nije reprodukovan runtime-om. Nijedan test nije napisan. Nijedan Playwright scenario nije pokrenut — a po `feedback_vindex_interaction_invariants`, za frontend nalaze (FS-P1-27 … FS-P1-31, FS-P3-*) **Playwright je jedini pravi dokaz**; ovde su dokazani samo na nivou izvornog koda.
- **UNKNOWN, svesno ostavljeno:** `security/chain_anchor.py:110-121` (zavisi od deploy `max-rows`); da li je RPC `increment_feature_usage` prisutan (provera bi zahtevala upis, što je zabranjeno).
- **Jedna tvrdnja iz mandata je povučena kao netačna** — v. ISPRAVKU u FS-P1-02.

---

*Kraj inventara. Nijedan nalaz nije popravljen — ovaj dokument je isključivo popis.*
