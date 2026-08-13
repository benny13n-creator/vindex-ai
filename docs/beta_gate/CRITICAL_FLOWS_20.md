# CRITICAL_FLOWS_20 — 20 kritičnih tokova, end-to-end

**Baseline:** `2a2e799c`
**Datum:** 2026-08-13
**Metod:** READ-ONLY forenzičko praćenje kroz kod. Nijedan fajl nije izmenjen, nijedna migracija pokrenuta, nijedan podatak poslat spolja.
**Entrypoint pod analizom:** `api:app` (`Procfile:1` gunicorn, `Dockerfile:33` uvicorn). `main.py` NIJE FastAPI aplikacija — to je biblioteka koju `api.py:95` uvozi.

---

## §0. PRAVILA DOKAZA KOJA OVAJ DOKUMENT POŠTUJE

| Oznaka | Značenje |
|---|---|
| **DOKAZANO** | pročitano u repou na navedenoj liniji |
| **UNKNOWN** | zahteva sondu žive baze / env-a / DPA. §10 zabranjuje pretvaranje u zaključak. |

Posebna napomena o šemi: repo **nema mehanizam praćenja migracija**. Postojanje tabele ili ograničenja u živoj bazi dokazuje se **isključivo sondom šeme**, nikad čitanjem `.sql` fajla. Svuda gde ovaj dokument kaže „tabela ne postoji", tačna tvrdnja je: **„nema `CREATE TABLE` nigde u repou; stanje žive baze je UNKNOWN".**

### Ispravka ranijeg nalaza unutar ove misije
Jedan paralelni trag je tvrdio da `record_cost()` nema nijednog pozivaoca. **Netačno** — poziva se preko aliasa `_rc` na `main.py:2317` i `strategija.py:834, 858`. Grep za `record_cost(` promašuje alias. Ispravljen nalaz je u Toku 18. Ovo je zabeleženo jer je pravilo kuće da se tuđi (i sopstveni) nalaz re-dokazuje, ne prepisuje.

---

## §1. ARHITEKTONSKE ČINJENICE KOJE VAŽE ZA SVE TOKOVE

Ove četiri stvari nisu bug u jednom toku — one su podloga ispod svih 20.

**A1. RLS je zaobiđen na svakoj API putanji.** Jedini Supabase klijent koristi `SUPABASE_SERVICE_KEY` (`shared/deps.py:93`, `api.py:169`). `SUPABASE_ANON_KEY` postoji u `.env.example:14` i **nijedan Python kod ga ne čita**. Kod sam ovo priznaje (`shared/ownership.py:9-14`): *„onih 250 `CREATE POLICY` u repou štiti samo pristup iz pregledača anon-ključem. Za API saobraćaj izostavljen `.eq("user_id", ...)` nema ništa ispod sebe."* → **svaka izolacija tenanata je ručno napisan Python filter.**

**A2. Audit je best-effort na svakom mestu.** `shared/audit_immutable.py:270-272` i `:295`: `logger.warning("[AUDIT_IMMUTABLE] greška upisa (nije kritično)")` → `return None`. Pozivaoci koriste sirov `asyncio.create_task` (ne `shared/bg.py::spawn`), pa zadatak može biti pokupljen od GC-a pre izvršenja. **Svaka operacija u ovom dokumentu može da uspe bez ijednog audit traga, uz HTTP 200.**

**A3. Provenance je best-effort, i to na nižem nivou od audita.** `shared/ai_client.py:478-479`: `logger.debug("[AI_PROVENANCE] capture greška (nije kritično)")` — `debug`, dakle nevidljivo na produkcionom log nivou. Unutrašnji pisac (`security/ai_forensics.py:411-413`) je popravljen na `logger.error`, ali ga spoljni `except → logger.debug` guta.

**A4. AI choke-point JESTE strukturan — i to treba priznati.** `shared/ai_client.py:808-809, 863-864, 923-926` menja metode na SDK **klasama**, pa ~150 mesta koja konstruišu sirov `OpenAI()` **ne zaobilaze** prompt guard, Response Firewall, provenance ni 60 s timeout. Van njega su tačno dve putanje: **Cohere** (`app/services/retrieve.py:1359`) i **sirov Realtime WSS** (`services/voice_orchestrator.py:47`).

---

## §2. LANCI — 20 TOKOVA

Format svakog lanca:
`START → zavisnosti → DB → storage → eksterni provajder → kriterijum uspeha → kriterijum otkaza → ŠTA KORISNIK VIDI → audit/provenance → putanja brisanja`

---

### TOK 1 — LOGIN / AUTH · **DELIMIČNO FUNKCIONALAN**

**START:** `static/vindex.js:640` — `sb.auth.signInWithPassword(...)`, **direktno iz browsera ka Supabase GoTrue**.

**Ključna činjenica:** *backend nema login endpoint.* Backend nikad ne vidi uspešnu prijavu.

- **Zavisnosti:** `python-jose[cryptography]==3.5.0`; dva nezavisna, skoro duplirana verifikatora — `shared/deps.py:171-257` (Depends stil) i `api.py:210-327` (ručni header stil)
- **DB:** `auth.users` (write, Admin API `api.py:2746`), `profiles`, `user_credits`, `aktivne_sesije`, `user_roles`, `audit_immutable`, `audit_log`
- **Storage:** —
- **Eksterni provajder:** Supabase GoTrue (`/auth/v1/token`, `/auth/v1/.well-known/jwks.json`)
- **Kriterijum uspeha:** JWT potpis validan (`exp` proveren, `aud` namerno isključen)
- **Kriterijum otkaza:** 401 `"Vaša sesija je istekla. Prijavite se ponovo."` (`shared/deps.py:302`)
- **Audit:** `login_failed` (`shared/deps.py:266`) i `logout` (`api.py:2902`). **`login_success` je registrovan u `AUDITABLE_ACTIONS` (`shared/audit_immutable.py:84`) i nema nijednog pozivaoca u celom repou.**
- **Putanja brisanja:** `DELETE /api/gdpr/account` → v. Tok 14

**Potpis JESTE proveren.** Iscrpan grep za `verify_signature` / `algorithms=` daje samo `options={"verify_aud": False}`. `alg=none` nije dohvatljiv (`_jwt_alg` bi vratio `"none"`, što ne pogađa ni HS256 ni `("RS256","ES256")` granu → `return None`). **Ovo je uredno i treba to reći.**

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F1-01** 🔴 | `api.py:2887-2904` | `{"ok": True, "poruka": "Odjavili ste se sa svih uređaja."}` | **Odjava je zagarantovan no-op.** `supa.auth.admin.sign_out(uid)` — a **potvrđeno protiv instalirane biblioteke** (`supabase==2.28.3`, `supabase_auth/_sync/gotrue_admin_api.py:70`): `def sign_out(self, jwt: str, scope=...)`. Prosleđuje se **UUID umesto JWT-a** → `Authorization: Bearer <uuid>` ka GoTrue `/logout` → 401 → `except Exception` (`:2897`) guta. Token ostaje potpuno validan. Red u `aktivne_sesije` se takođe ne briše. Advokat na tuđem/ukradenom računaru dobija poruku „odjavljeni ste sa svih uređaja" a sesija je živa. |
| **F1-02** 🔴 | `klijenti/permissions.py:126-143` | rola korisnika | `except → return DEFAULT_ROLE` gde je `DEFAULT_ROLE = Role.ADVOKAT` (`:42`). **Fail-OPEN.** Neuspelo čitanje `user_roles` diže `sekretarica`/`pripravnik` na `ADVOKAT`, što po `ROLE_FIELD_ACCESS` (`:89-90`) otključava `jmbg_encrypted`, `broj_pasosa_encrypted`, `pib_encrypted` i `download_document`. `shared/ownership.py:46-48` je fail-CLOSED — dva modula se ne slažu oko smera. |
| **F1-03** 🟠 | `routers/sesije.py:52-62` | broj aktivnih sesija | `except → return 0` → `if broj >= lim` nikad tačno → **neograničen broj paralelnih sesija.** Kontrola deljenja naloga se sama gasi na svaki treptaj baze. |
| **F1-04** 🟠 | `routers/sesije.py:138-148` | `{"status": "ok", "poruka": "Sesija registrovana", "aktivnih": broj+1}` | Insert je u `try/except → logger.error`, `return` je van njega. Nema reda u tabeli; `aktivnih` je izmišljen broj. |
| **F1-05** 🟠 | `shared/deps.py:452-513` | HTTP 200, profil korisnika | 4 od 5 čitanja profila gutaju izuzetak i vraćaju **degradaciju kao činjenicu**: `is_pro_db=False`, `subscription_type="basic"`, `addons=[]`. Enterprise kancelarija na delimičnoj grešci baze tiho postaje „basic" i dobija 403 sa porukom „Vaša trenutna tarifa: Basic." |
| **F1-06** 🟡 | `shared/permissions.py:62-88` | pretplata važi | Neparsiv `subscription_expires_at` → `return False` (= nije istekao). Fail-open na entitlement, namerno i dokumentovano. |
| **F1-07** 🟡 | `api.py:2761-2767`, `:2818-2831` | registracija uspela, `access_token` izdat | `profiles` upsert i `_setup_trial` oba gutaju izuzetak → korisnik ima `auth.users` red **bez `profiles` reda** i bez trial polja. |
| **F1-08** 🟡 | `api.py:2882-2884` | `{"plan":"trial","trial_aktivan":True,"dani_ostalo":30}` | Vraća se **posle** `except` — bilo koja greška baze proizvodi izmišljen 30-dnevni trial. |
| **F1-09** 🟡 | `api.py:2847-2853` | `"Dobrodošli u Vindex AI!"` | `except → logger.warning`, `return` van njega. Onboarding update možda nije upisan. |
| **F1-10** 🟡 | `shared/deps.py:290, 297-299` | — | `login_failed` audit ide kroz sirov `asyncio.create_task` (bez reference, bez done-callback-a), a unutra `_log_login_failed` (`:266-281`) ima svoj `except → logger.debug`. **Dva sloja tišine.** Uz nepostojeći `login_success`, nepromenljivi ledger ne može da odgovori na pitanje „ko se prijavio, odakle, kada". |
| **F1-11** 🟡 | `shared/deps.py:154-157` | JWKS ključ odgovara traženom `alg` | `if k.get("alg","") == alg or k.get("kty","") in ("EC","RSA")` — `or` čini poređenje `alg`-a kozmetičkim; vraća se prvi EC/RSA ključ. Koristi se sa `algorithms=[alg]` gde `alg` **dolazi od napadača** (`:209`). Danas nije iskoristivo jer jose proverava tip ključa, ali brana nije ona za koju kod misli da jeste. |

---

### TOK 2 — KREIRANJE PREDMETA · **DELIMIČNO FUNKCIONALAN**

**START:** `POST /api/predmeti` → `api.py:3809 kreiraj_predmet`. **Šest različitih puteva kreira predmet** — i oni se drastično razlikuju po kvalitetu.

| # | Ruta | Sanitizacija | Dup-guard | Event/Pipeline | Audit |
|---|---|---|---|---|---|
| 1 | `POST /api/predmeti` `api.py:3809` | ✔ | ✔ 5 s | ✔ durable | ✔ |
| 2 | `POST /v1/predmeti` `routers/integracije.py:255` | ✘ | ✘ | ✘ | ✘ |
| 3 | `POST /v1/webhook/clio` `routers/integracije.py:275` | ✘ | ✘ | ✘ | ✘ |
| 4 | `POST /api/onboarding/demo-predmet` `routers/onboarding.py:171` | n/a | ✔ | ✘ | ✘ |
| 5 | Smart Intake finalize `routers/smart_intake.py:711` | n/a | ✔ | ✔ | ✔ |
| 6 | Bulk CSV `routers/intake.py:997` | ✘ | ✘ | ✘ | ✔ |

- **DB:** `predmeti(user_id, naziv, opis, tip, status)` — DDL `supabase_setup.sql:300-309`
- **Tenant scoping:** **samo `user_id`.** `predmeti` **nema kolonu `kancelarija_id`** (potvrđeno DDL-om i svim `ALTER TABLE ... predmeti` u `migrations/`). Tabele `kancelarije`/`kancelarija_clanovi` su potpuno odvojene od vlasništva nad predmetom.
- **Validacija:** nema pydantic modela — `body = await request.json()` (`:3813`). `naziv`/`opis` su **neograničene dužine** (`sanitize_text(..., max_len=1_000_000)`). `tip` se uzima sirov, **bez allowlist-a** (za razliku od `update_kanban_faza`, `api.py:4339`, koji ga ima).
- **Putanja brisanja:** **NE POSTOJI** — v. Tok 13

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F2-01** 🔴 | `routers/integracije.py:301-317` | `{"status":"ok","kreiran_predmet": naziv}` | **`user_id` — cela dodela tenanta — čita se direktno iz tela zahteva** (`payload.get("vindex_user_id")`), bez provere ijedne tabele. Ko ima `CLIO_WEBHOOK_SECRET` može da podmetne predmet u bilo čiji nalog. Grana `if not user_id` vraća HTTP **200** `"primljeno"` iako ništa nije upisano. Završni `return` ne proverava `result.data`. |
| **F2-02** 🔴 | `routers/integracije.py:271-272` | HTTP **201** `{"status":"kreiran"}` | `new_pred = result.data[0] if result.data else {}` → `{"predmet": {}, "status":"kreiran"}` kad ništa nije kreirano. Uz to: bez sanitizacije (XSS kroz API ključ), bez `PREDMET_KREIRAN` eventa (**nikad Case Pipeline za API-kreirane predmete**), bez audita, bez per-user rate limita (`api.py:1076-1077` — middleware izlazi za sve što ne počinje sa `/api/`), bez access-log audita (`shared/audit.py:15` prati samo `/api/predmeti`). API ključ se poredi **u čistom tekstu** (`:75` `.eq("kljuc", api_key)`). |
| **F2-03** 🟠 | `api.py:3875-3942` | HTTP 200, predmet kreiran | Durable `PREDMET_KREIRAN` outbox upis ima 3 pokušaja, pa `except → logger.error` i **`return {"predmet": ...}` svejedno**. Ceo 9-korački Case Pipeline (izvlačenje rokova, mini-strategija, HCC brifing, snimak rizika) **nikad ne pokreće**, a odgovor to ne pominje. Oporavak zavisi od `reap_missing_pipeline_events` (`services/event_bus.py:828`) koji nema zakazanog pozivaoca. |
| **F2-04** 🟠 | `services/case_pipeline.py:247-640` | `PipelineResult` sa 9 koraka | **Nijedan korak ne diže izuzetak** — svi se degradiraju u `StepStatus.FAILED`, a `routers/case_pipeline.py:54-56` vraća HTTP 200. Najgore: `:381-382` — neuspeo upis izvučenih **zakonskih rokova** loguje se na `logger.debug` i odbacuje. |
| **F2-05** 🟠 | `api.py:3843` | — | Sinhroni blokirajući `.execute()` unutar `async def`. Svi susedni pozivi u istoj funkciji (`:3826, :3903, :3914`) koriste `await asyncio.to_thread`. Isto na `api.py:4277-4280`. Blokira ceo event loop. |
| **F2-06** 🟡 | `api.py:3850` | — | `novi_predmet = row.data[0]` bez zaštite → `IndexError` → generički 500, **a red je već upisan**. Korisnik ponavlja i dobija 409 ili duplikat. `routers/integracije.py:271` i `routers/onboarding.py:227` imaju zaštitu. |
| **F2-07** 🟡 | `api.py:3929-3940` | — | Audit kroz sirov `create_task`, unutra `log_action` guta. Uz to `metadata` upisuje **naziv predmeta** u nepromenljiv, neizbrisiv hash-lanac — što `api.py:4319-4322` **izričito zabranjuje** za `predmet_update`. Dva handler-a, dve različite politike PII-a. |
| **F2-08** 🟡 | `services/event_bus.py:391-413` | event objavljen | `loop.create_task(_run())` bez registra i bez done-callback-a; svaki `raise` iz handler-a umire na `:405`. Samo durable putanja (`publish_async`) stvarno propagira. |
| **F2-09** 🟡 | `routers/onboarding.py:196-197, 211-269` | demo predmet kreiran | Provera idempotencije guta izuzetak → **pravi duplikat**. Klijent, veza `predmet_klijenti`, rok i zadatak — sva četiri se gutaju (`logger.debug`). |

---

### TOK 3 — UPLOAD DOKUMENTA · **DELIMIČNO FUNKCIONALAN** (9 ruta, 1 potpuno slomljena)

**START:** devet multipart ruta. Glavna korisnička je `POST /api/predmeti/{predmet_id}/upload` (`api.py:5030-5817`).

- **Zavisnosti:** `_require_auth_async` → `PermissionService.require("predmet_upload_ai")` → vlasništvo `.eq("user_id", user.id)`
- **DB:** `predmet_dokumenti`, `predmet_hronologija`, `predmet_istorija`, `audit_immutable`, events outbox
- **Storage:** `intake-dokumenti`, AES-256-GCM pre upload-a, ključ `{user.id}/{predmet_id}/{uuid4}{suffix}`
- **Eksterni:** OpenAI embeddings + `gpt-4o`/`gpt-4o-mini` ×3, Pinecone
- **Kriterijum uspeha:** `_dok_id` nije `None` (tvrdo nametnuto, `api.py:5325-5329` — **ovo je ispravno urađeno**)
- **Audit:** `dokument_upload` (`api.py:5353`), fire-and-forget
- **Putanja brisanja:** **NE POSTOJI** — v. Tok 12

**Nedoslednosti između 9 ruta (same po sebi nalaz):**

| Ruta | Limit | Ekstenzije | Magic bytes | Enkripcija | AV |
|---|---|---|---|---|---|
| `api.py:5030` | 10 MB (samo posle `read()`) | + `.doc`, MIME allowlist **uključuje `application/octet-stream`** | ✘ | ✔ | ✘ |
| `routers/dokument.py:219` | 25 MB (dva puta) | `.pdf/.docx` | ✘ | n/a (original se briše) | ✘ |
| `routers/smart_intake.py:108` | 25 MB | 6 tipova | ✘ | ✔ | ✘ |
| `routers/law_upload.py:184` | 30 MB | `.pdf` | ✘ | n/a | ✘ |
| **`routers/client_portal.py:514`** | 10 MB | 7 tipova | **✔ jedina** | **✘ plaintext** | ✘ |
| `routers/drafting.py:541` | 2 MB | `.txt/.docx` | ✘ | n/a | ✘ |
| `klijenti/router.py:758` | 10 MB | **nikakva provera tipa** | ✘ | ✔ | ✘ |

**Nijedna od 9 ruta nema antivirusnu proveru.** Grep za `clamav|clamd|virus|malware|yara` → 0 pogodaka u aplikativnom kodu.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F3-01** 🔴 | `routers/drafting.py:569, 571` | — | **Endpoint je 100% slomljen, provereno.** `tekst, _ = await asyncio.to_thread(extract_docx, tmp_path)` — a `extract_docx` vraća **5-torku** (`uploaded_doc/extractor.py:301`), isto `extract_txt` (`:306`). → `ValueError: too many values to unpack`. Okolni `except` hvata samo `DocumentSafetyLimitExceeded` (`:572`). **Svaki playbook upload je nehvatan 500.** Docstring ekstraktora (`:382-385`) tvrdi *„sva 4 pozivna mesta destrukturiraju ovu torku identično, potvrđeno grep-om"* — `drafting.py` nikad nije bio u tom grep-u. Isto na `uploaded_doc/__main__.py:32`. |
| **F3-02** 🔴 | `api.py:5096-5110` + `:5284` | HTTP 200, dokument otpremljen | Upis **originalnog fajla** u Storage je best-effort: `except → logger.warning` pa se nastavlja. `storage_path` se onda upisuje kao `f"session/{session_id}"` — **izmišljena labela koja ne pokazuje ni na šta** (kod to priznaje na `:5278-5283`). Potpisan PDF advokata je nepovratno izgubljen, a spis kaže da je dokument tu. Jedini signal je `"original_preserved": bool(...)` (`:5817`) — boolean koji frontend mora da zna da pročita. **Smart Intake (`smart_intake.py:1450`) upisuje istu izmišljenu labelu BEZUSLOVNO** — Pipeline C nikad ne čuva original, a njegovi redovi su nerazlučivi od Pipeline A redova koji jesu. |
| **F3-03** 🟠 | `routers/dokument.py:319-326` | HTTP 200 + `chunk_count` | Nepotpun Pinecone ingest se loguje `logger.error` i **propada dalje bez zastavice**. `api.py:5237-5242` i `smart_intake.py:1436-1443` rade istu proveru i **ispravno** spuštaju status na `"sacuvano"`; `dokument.py` je jedini bez toga. |
| **F3-04** 🟠 | `routers/dokument.py:331-334`, `api.py:5250-5254` | HTTP 200, `chunk_count: 0` | `je_kvota_greska` (`uploaded_doc/ingest.py:240-245`) vraća `True` za **bilo koju poruku koja sadrži `"429"`** — uključujući OpenAI rate-limit, koji je prolazan i nije kvota. Dokument završi potpuno neindeksiran, odgovor kaže uspeh. |
| **F3-05** 🟠 | `routers/smart_intake.py:1518-1531` | dokument sačuvan | „Merdevine" od 6 varijanti insert-a hvataju **svaku** klasu izuzetka i loguju na `logger.debug` (nevidljivo). Dizajnirane su za nedostajuće migracije, ali sakrivaju i obične loše vrednosti — kod sam dokumentuje (`:1476-1489`) da je već jednom tiho ispustio i `tip_dokaza` i `tekst_sadrzaj`. Mehanizam koji je to sakrio je nepromenjen. Ista, uža varijanta u `api.py:5299-5309` — **sa tri ugnežđena `except Exception:` bez ijednog log poziva na srednjem stepeniku.** |
| **F3-06** 🟠 | `routers/dokument.py:108-118` | `{"ok": True, "klasifikacija": {...}}` | Na grešku GPT-a vraća **uverljivo izmišljenu klasifikaciju** (`tip_dokaza: "ostalo"`, `snaga_dokaza: "niska"`) **bez ikakvog markera greške**. `routers/evidence.py:116-121` je popravio tačno ovaj bug dodavanjem `"_klasifikacija_greska": True` uz komentar *„stvaran kvar GPT-a je tiho pran u uspeh koji izgleda uverljivo"* — ispravka nikad nije preneta na `dokument.py`, koji je dohvatljiva ruta. |
| **F3-07** 🟠 | `api.py:5397-5410`, `smart_intake.py:1592, 1657` | HTTP 200 | Obe durable emisije su `except → logger.warning(... "non-fatal")`. Izgubljen `NEW_EVIDENCE_REGISTERED` znači: dokument nikad nije klasifikovan, nikad ne ulazi u Evidence Vault, nikad se ne pojavljuje na Timeline-u — uz HTTP 200 i nijedan trag za korisnika. |
| **F3-08** 🟡 | `api.py:5192-5200` | `mozda_duplikat: false` | `except → logger.warning("nastavljam")` → korisniku se javlja „nije duplikat" iako provera nikad nije izvršena. |
| **F3-09** 🟡 | `api.py:5269-5272`, `smart_intake.py:1306` | DOK-NN numeracija | Neuspelo čitanje `redni_broj` → `_next_rn = 1` → numeracija tiho kreće iz početka i sudara se sa postojećim dokumentima. |
| **F3-10** 🟡 | `routers/dokument.py:358-365` | — | Pozadinska klasifikacija: sirov `create_task`, bez reference. Log linija čita `rezultat.get("tip", "?")` a ključ je **`tip_dokaza`** (`:95`) → jedini signal observabilnosti **uvek ispisuje `?`**. |

---

### TOK 4 — STORAGE · **DELIMIČNO FUNKCIONALAN**

Tri bucket-a, **tri različita režima** — nedoslednost je sama po sebi nalaz.

| Bucket | Enkripcija | Kreiran migracijom | Ime fajla |
|---|---|---|---|
| `intake-dokumenti` | ✔ AES-256-GCM | ✔ `migrations/073:362-364`, `public=false` | zamenjeno UUID-om |
| `klijent-dokumenti` | ✔ AES-256-GCM | ✘ **nijedna migracija ne kreira bucket** | šifrovano |
| `portal-uploads` | **✘ plaintext** | ✘ samo komentar `migrations/013:5` „napravite ručno" | **originalno ime u putanji, plaintext** |

- **Ključ:** jedan simetričan `FIELD_ENCRYPTION_KEY` za **blobove I PII polja** (`security/crypto.py:122-140`). Blobovi **nemaju key-id prefiks** (polja ga imaju, `crypto.py:30`) → **rotacija ključa trajno onesposobljava sve postojeće blobove.**
- **RLS na `storage.objects`:** **nula `CREATE POLICY`** u 103 migracije. Izolacija = nepogodivost `uuid4` putanje + aplikativne provere.
- **Signed URL:** jedno jedino mesto, `client_portal.py:702-703`, TTL 3600 s
- **Javnost bucket-a `portal-uploads` / `klijent-dokumenti`:** **UNKNOWN** — traži `SELECT id, public FROM storage.buckets;`

**⚠ TAČKE LAŽNOG USPEHA:** F3-02 (gore) je i nalaz ovog toka. Dodatno:

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F4-01** 🟠 | `client_portal.py:776-816` | `{"ok": True}` + nepromenljiv audit red `client_portal_upload_delete` | Brisanje blob-a je `except → logger.warning`, pa se **nastavlja**. Ako DB brisanje uspe, ruta vraća uspeh i upisuje audit dokaz o brisanju — **a plaintext fajl ostaje u `portal-uploads`, sada bez ijednog pokazivača.** Nijedan posao rekoncilijacije ne postoji; `retention_service.py` ne dodiruje Storage. |
| **F4-02** 🟡 | `api.py:5330-5346` i sl. | — | Sva kompenzujuća brisanja su `except → logger.warning`. Ako i ono padne, blob je trajno siroče koje ništa ne prati. |

---

### TOK 5 — OCR · **FUNKCIONALAN**

**Ovo je jedan od retkih tokova koji radi ispravno i to treba reći.**

- **Provajder: lokalni `pytesseract` + `PyMuPDF`. Nema cloud OCR-a.** Potvrđeno: nema `mistral`, `image_url`, Azure/Google/Textract nigde. `pdf2image` je u `requirements.txt:39` ali se **nikad ne uvozi**.
- **Slika dokumenta NE napušta mašinu radi OCR-a.** (Izvučeni tekst posle toga ide OpenAI-u — to je Tok 7.)
- **Lanac:** `extract_pdf` (`extractor.py:178-261`) → `is_scanned = avg_chars < 30 or total_chars < 80` (`:215`) → `fitz get_pixmap(dpi=300)` → `_ocr_image` (`:104-156`): grayscale, kontrast ×2, MedianFilter, `pytesseract.image_to_data(timeout=45)`
- **Jezik:** `srp+srp_latn+eng` (`:159-175`)
- **Zaštite:** `MAX_DECOMPRESSED_BYTES=50MB`, `MAX_RATIO=100`, `MAX_ZIP_ENTRIES=2000` (`:40-42`), `MAX_PDF_PAGES=500` (`:94`), `MAX_IMAGE_PIXELS=40M` (`:101`) — dekompresiona bomba pokrivena
- **Kriterijum uspeha:** `len(ocr_text.strip()) > 100`
- **Kriterijum otkaza:** `("", True, False, None, None)` — sentinel `is_scanned=True`
- **Korisnik vidi:** 422 sa tri konkretna koraka: *„Probajte jasniju fotografiju/sken, digitalni PDF ili DOCX."* (`routers/dokument.py:266-276`) — **poštena, upotrebljiva poruka**
- **Audit:** `security_events` tipa `ocr_error` (`extractor.py:11-24`)

**Bez novih tačaka lažnog uspeha u samom OCR-u.**

---

### TOK 6 — EKSTRAKCIJA TEKSTA · **DELIMIČNO FUNKCIONALAN**

- `pdf_tools.py` **ne radi ekstrakciju** — 12 linija monkey-patch-a `ssl.create_default_context`. Ime fajla obmanjuje.
- `docx_export.py` je samo pisanje (`tekst_u_docx`).
- Stvarne biblioteke: `pypdf==6.15.0`, `python-docx==1.2.0`, `pymupdf`. Nema `pdfplumber` ni `PyPDF2`.

| Pozivno mesto | Prazan tekst |
|---|---|
| `routers/dokument.py:290` | 422 ✔ |
| `api.py:5153` | 422 ✔ |
| `law_upload.py:233` | `status="failed"` + 422 ✔ |
| `auto_discovery.py` | 422 ✔ |
| **`routers/smart_intake.py:1330-1334`** | `{"povezan": False, "razlog": "prazan_tekst"}` u **HTTP 200** |

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F6-01** 🟠 | `routers/law_upload.py:49-58` | zakon učitan | `for page in reader.pages: try: ... except: pass`. Zakon od 400 strana gde 399 padne daje „zakon" od 1 strane, koji prođe prag `>= 100` znakova i bude ingestovan i označen `done`. |
| **F6-02** 🟠 | `routers/smart_intake.py:1286-1291` | HTTP 200, predmet kreiran | Neuspeh dekripcije/ekstrakcije **celog posla** guta se u `logger.warning`, `text` ostaje `""`, svi dokumenti dobiju `povezan: False`, i funkcija **normalno nastavlja** do `:1703-1728`. Advokat u listi predmeta dobija stvaran predmet **sa nula dokumenata**. |
| **F6-03** 🟡 | svuda | tekst izvučen | Ekstrakcija od 101 znaka prolazi prag i tiho se čuva kao potpun dokument. |

---

### TOK 7 — EMBEDDING · **FUNKCIONALAN, uz jednu rupu**

- **Model:** `text-embedding-3-large`, 3072-d (`app/services/retrieve.py:70`)
- **Šta se šalje:** tekst chunk-ova (`uploaded_doc/ingest.py:75`) — dakle **sirov tekst pravnog dokumenta odlazi OpenAI-u**
- **Tri različita klijenta:** `langchain_openai.OpenAIEmbeddings` (ingest), sirov `OpenAI().embeddings.create` (law upload), `embed_query` sa memo kešom (upit)
- **Ulazni guard NAMERNO isključen** za embeddings (`ai_client.py:836-849`) — obrazloženje je dobro: pravni podnesci prirodno sadrže citirane naredbe, false-positive bi trajno ne-indeksirao dokaz u predmetu
- **Kriterijum uspeha:** `len(vectors_raw) == len(manifest.chunks)` — **`ingest.py:88-92` diže `RuntimeError` na neslaganje. Ovo je ispravno i tako treba.** Isto `law_upload.py:129-133`, `interni_stavovi.py:68-72`.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F7-01** 🟠 | `drafting/playbook.py` | playbook ingestovan | **Jedini pisac bez provere dužine oko `zip(chunks, vectors)`.** `interni_stavovi.py:68` ima identičan kod **plus** zaštitu. Delimičan odgovor embedding provajdera tiho upisuje podskup. (Akademski dok F3-01 drži ceo endpoint u 500 — ali čim se F3-01 popravi, ovo postaje aktivno.) |
| **F7-02** 🟡 | `ai_client.py:865-866` | `governance_status() → active: true` | Ako patch embeddings klasa padne, samo `logger.warning("nije kritično")`. **Nijedan health check ne razlikuje punu pokrivenost od chat-only.** |

---

### TOK 8 — PINECONE UPSERT · **FUNKCIONALAN po upisu, SLOMLJEN po brisanju**

- **Index:** jedan. **Dva različita env imena za istu stvar:** `PINECONE_INDEX_NAME` (`retrieve.py:461`) vs `PINECONE_INDEX` (`law_upload.py:91`). Deployment koji postavi samo prvo šalje zakone u default `vindex-ai` bez obzira na sve.
- **Namespace-ovi:** `zakoni_rs`, `sudska_praksa`, `misljenja`, `kancelarija_{id}` / `user_{id}` (trajni), `tmp_{session}` (24 h), `kb_{uid}`, `interni_stavovi_{uid}`
- **Metapodaci:** `"text": chunk.text[:40000]`, `source_filename`, `predmet_id`, `kancelarija_id`, `session_id`, `vx_*` identitet — v. `EXTERNAL_BOUNDARY_002.md §3.6`
- **Identitet:** determinističan, `canonical_vector_id(scope, verzija, chunk_index)`; **fail-closed bez verzije** (`ingest.py:141-147`) — dobro urađeno

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F8-01** 🔴 | `routers/law_upload.py:149-163` | `status: "done"` u admin listi | `except → logger.error` **pa `continue`**, zatim `if upserted > 0: _db_update(supa, doc_id, "done", ...)`. **99 od 100 batch-eva može da padne i zakon je „done".** To je *pravni* korpus — RAG odgovara na pitanja o zakonu čiji članovi nikad nisu indeksirani. Susedna embed petlja (`:118-126`) je **izričito popravljena** iz `continue` u `raise`, uz komentar da je `continue` bio bug; upsert petlja 25 redova niže je ostavljena. |
| **F8-02** 🔴 | `shared/kancelarija_utils.py:41-42` | dokument indeksiran u kancelarijskom namespace-u | `except: return None` → `rag_owner_namespace(uid, None)` vraća `f"user_{uid}"`. Prolazan kvar baze pri upload-u **upisuje dokument kancelarije u lični namespace uploader-a**: nevidljiv svim kolegama, nevidljiv `kancelarija_{id}` pretrazi, a `predmet_dokumenti.pinecone_namespace` beleži pogrešan namespace pa bi i brisanje tražilo na pogrešnom mestu. Tiho, trajno i samo-prikrivajuće. |
| **F8-03** 🔴 | `shared/vector_deletion.py` | — | `obrisi_vektore_dokumenta` je **potpun, fail-closed, testiran brisač sa post-verifikacijom** — i ima **NULA produkcionih pozivalaca.** Grep celog repoa: samo `tests/test_pine01_vector_deletion.py` (6 mesta) i `scripts/ingest_case_law.py:547` (koji uvozi samo `dozvoli_globalno_brisanje`). **Sposobnost po GDPR čl. 17 je izgrađena, testirana i nedohvatljiva.** Ovo je udžbenički primer principa iz memorije: zelen test koji meri samo jednu stranu ugovora ne dokazuje korisniku ništa. |
| **F8-04** 🟠 | `routers/knowledge_base.py:123-125, 194-198` | `{"ok": True, "id": entry_id}` | Coroutine `_kb_embed_and_upsert` guta svaki kvar (`logger.warning`) **i** koristi sirov `asyncio.create_task` umesto `shared/bg.spawn` (defekt koji `shared/bg.py:12-24` postoji da eliminiše). Beleška zauvek živi u `user_knowledge` i **nikad nije pretraživa**. |

---

### TOK 9 — RAG RETRIEVAL · **FUNKCIONALAN po ACL-u, OPASAN po tišini**

**ACL je server-side i ispravan — to treba priznati.** `shared/rag_acl.py:136` gradi Pinecone metadata filter `{"type": {"$in": tipovi}, "predmet_id": {"$in": dozvoljeni}}` koji ide **u sam `index.query`**, ne posle. `dozvoljeni_predmeti` (`:54-84`) je verno ogledalo `api.py::get_predmet`: vlasnik + aktivno `predmet_delegiranja`. Članstvo u kancelariji **namerno nije** osnov (`:34-40`). `None` sentinel je nosiv: `retrieve.py:963` radi `if filter:`, pa bi `{}` tiho uklonio filter — modul to izričito sprečava (`:99-105`).

**Može li tenant A da dohvati chunk-ove tenanta B?** Kroz ovu putanju — **ne, danas.**

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F9-01** 🔴 | `app/services/retrieve.py:905-970` (5 funkcija) | „nema rezultata" | `except → _sentry_capture → logger.warning → return []`. **Ispad Pinecone-a, greška autentifikacije ili odbijen metadata filter su nerazlučivi od praznog korpusa.** Uzvodno, `main.py` prikazuje prazan retrieval kao **tvrdnju o srpskom pravu**. Repo ovo ZNA — `RetrievalUnavailable` je napravljen na `retrieve.py:974-989` baš zbog toga, uz nalaz da je *„ispad provajdera prikazan advokatu kao pravna činjenica"* — ali je opt-in preko `raise_on_error=` i povezan je u **tačno jednu** funkciju (`_direktan_fetch_clana`). Pet gornjih i dalje vraćaju `[]`. |
| **F9-02** 🟠 | `shared/rag_acl.py:117-127` | pretraga izvršena | Iznad 400 autorizovanih predmeta pretraga se sužava na trenutni predmet, uz samo `logger.warning`. Advokat sa velikim portfoliom **tiho gubi pretragu preko ranijih predmeta**. Smer je ispravan (uže, nikad šire), ali korisnik ne zna. |
| **F9-03** 🟠 | `main.py:207-256` | `{"status":"success"}` iz keša | `ai_cache` je **globalni keš odgovora bez tenant ključa** — `md5(normalizovano_pitanje)`. Jedina izolacija su **dva literalna stringa** (`_PRIVATNI_KONTEKST_MARKERI = ("KONTEKST PREDMETA:", "[Predmet:")`). Svaka buduća putanja koja ubaci kontekst predmeta pod drugim zaglavljem upisuje odgovor specifičan za klijenta u red čitljiv **svim tenantima**, 7 dana. Kod priznaje da je strana upisa „trajni problem". *(`ai_cache` nema `CREATE TABLE` u repou — samo INDEX u `migrations/023:5`; postojanje u živoj bazi UNKNOWN.)* |
| **F9-04** 🟡 | `knowledge_base.py:230`, `interni_stavovi.py:105` | izolacija po korisniku | `kb_{uid}` / `interni_stavovi_{uid}` **nemaju metadata filter** — izolacija je isključivo string namespace-a izveden iz JWT `uid`. |

---

### TOK 10 — AI ODGOVOR · **FUNKCIONALAN, uz pogrešnu semantiku statusa**

- **Model:** `gpt-4o` za 4 RAG teme (`main.py:3385-3388`); `gpt-4o-mini` default u `ai_fabric`
- **Choke-point:** v. §1/A4 — strukturan, pokriva ~150 sirovih klijenata
- **Kontrole na granici:** ✔ prompt guard ✔ Response Firewall ✔ provenance ✔ 60 s timeout ✔ **fail-closed AI kill-switch** (`ai_client.py:124-181`) — ako se guard ne instalira, AI granica se zatvara umesto da se pozivi izvršavaju neupravljano. **Ovo je ozbiljno inženjerstvo i treba to reći.**
- **`shared/ai_fabric.py` je MRTAV KOD** — nula produkcionih pozivalaca. „Jedinstvena AI tkanina" nije povezana ni sa čim.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F10-01** 🔴 | `main.py:3470-3480, 3589-3599, 3675` | `{"status": "success", "blocked": True}` | **Halucinacioni guard je odbio izlaz modela, provera pravne ispravnosti je pala — a omotač i dalje kaže `success`.** Svaki klijent, log agregator ili SLO dashboard koji gleda `status` broji ovo kao uspešan odgovor. `blocked` je susedni ključ koji niko nije obavezan da čita. Isto na `:3356` i `:3377` za LOW-confidence „ništa nismo našli". |
| **F10-02** 🟠 | `services/voice_orchestrator.py:47` | glasovna sesija radi | Sirov WSS ka `wss://api.openai.com/v1/realtime` — **bez prompt guard-a, bez Response Firewall-a, bez timeout-a, bez per-poruka provenance-a.** Kod to priznaje (`ai_client.py:664-666`). Jedan provenance red po sesiji postoji (`:245-276`), i autorizacija sesije JESTE fail-closed (`:168`). |

---

### TOK 11 — PROVENANCE · **DELIMIČNO FUNKCIONALAN**

- **Tabela:** `ai_forensics`. `shared/ai_provenance.py` **ništa ne upisuje** — to je samo contextvar vodovod.
- **Zapisuje:** `user_id`, `tenant_id`, `predmet_id`, `document_id`, `module/operation`, `model_provider/name`, `system_prompt_hash`, `user_prompt_hash`, `output_hash`, tokeni, `latency_ms`, `correlation_id`, `parent_event_id`, `knowledge_sources`, `retrieved_context_ids`, `status`, `error_message` — **samo heševi, nijedan plaintext prompt ili izlaz. Ovo je ispravno.**
- **Redosled je popravljen ispravno:** provenance se upisuje **posle** presude firewall-a, pa je odbijen odgovor zabeležen kao `status="error"`, ne `"success"` (`ai_client.py:741-760`).

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F11-01** 🟠 | `shared/ai_client.py:478-479, 533-534` | AI poziv izvršen i zabeležen | `except → logger.debug("nije kritično")`. **`debug` je nevidljiv na produkcionom nivou.** Unutrašnji pisac je popravljen na `logger.error` (`ai_forensics.py:411-413`) ali ga spoljni sloj guta. |
| **F11-02** 🟠 | `security/ai_forensics.py:389-411` | provenance red upisan | Ako **migracija 089 nije primenjena**, red se upisuje **bez join ključeva** (degradiran). Degradacija je „lepljiva" i merena (dobro urađeno), ali status migracije 089 je **UNKNOWN** — v. `docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql`. |

---

### TOK 12 — BRISANJE DOKUMENTA · **NE POSTOJI**

**Iscrpan dokaz, ne pretpostavka.** Grep `@router.delete` / `@app.delete` / `methods=["DELETE"]` po celom stablu → **29 ruta, nijedna nije dokument.** Najbliže: beleška (`api.py:4397`), stavka dokaza (`evidence.py:416`, soft), zakon (`law_upload.py:273`, soft), portal upload (`client_portal.py:750`).
`methods=["DELETE"]` → 0 registracija ruta (jedini pogodak je CORS na `api.py:954`).
`table("predmet_dokumenti")` + delete → **0 pogodaka**; jedini je UPDATE (`evidence.py:253`).

**Kod sam ovo priznaje** (`shared/audit_immutable.py:68-71`):
> `"dokument_delete"` je REZERVISAN unos — nijedan endpoint za brisanje dokumenta ne postoji danas.

**Posledica:** dokument otpremljen u predmet je **trajan**. DB red, Storage objekat, Pinecone vektori, chunk-ovi — ništa se ne može ukloniti kroz aplikaciju, ni od strane korisnika ni admina.

**⚠ TAČKA LAŽNOG USPEHA — F12-01 🔴:** `shared/vector_deletion.py` postoji, testiran je i nema pozivalaca (= F8-03). Sistem izgleda kao da ima sposobnost brisanja; nema je.

---

### TOK 13 — BRISANJE PREDMETA · **NE POSTOJI**

Isti iscrpan grep, isti ishod. `table("predmeti").delete()` se u celom stablu pojavljuje **tačno jednom** — `routers/intake.py:1021`, kompenzujući rollback unutar *kreiranja*.
`predmeti` **nema `deleted_at`** kolonu (deca `predmet_dokazi`, `predmet_dokumenti` imaju) → **nema ni soft delete.**

Najbliže: `PATCH /api/predmeti/{id}/zatvori` (`predmeti_close.py:67`) — samo promena statusa.
Klijent ima soft delete (`klijenti/router.py:524`) ali **ne kaskadira**: predmeti tog klijenta, njihovi dokumenti i Pinecone vektori ostaju netaknuti i dohvatljivi.

**Jedino stvarno brisanje predmeta je Postgres kaskada** `predmeti.user_id REFERENCES auth.users(id) ON DELETE CASCADE` (`supabase_setup.sql:302`) — brisanje auth korisnika iz Supabase konzole uništava sve predmete, dokumente, beleške i ročišta **bez ijednog aplikativnog audit reda**.

**⚠ TAČKA LAŽNOG USPEHA — F13-01 🟠:** `routers/onboarding.py:167` korisniku poručuje *„možete ga obrisati kad god želite"*. **Ta sposobnost ne postoji.** Ugovor UI-ja je prekršen tekstom koji sistem ne može da ispuni.

---

### TOK 14 — GDPR BRISANJE · **DELIMIČNO FUNKCIONALAN (najozbiljniji nalaz o usklađenosti)**

**`GET /api/gdpr/export` (`gdpr.py:153-196`)** — čita 5 tabela: `profiles`, `predmeti` (samo id/naziv/status/tip/created_at), `billing_entries`, `korisnik_email_notif`, `usage_events` (**ograničeno na 200 redova**, `:179`).
**NE izvozi:** dokumente, tekst dokumenata, dokaze, hronologiju, ročišta, zadatke, beleške, korekcije, AI izlaze i **svaki Storage objekat**. Odgovor napominje samo šifrovana polja (`:183`), nikad izostavljene tabele. Korisnik koji ostvaruje pravo po čl. 20 dobija JSON koji tiho izostavlja **ogromnu većinu** svojih podataka.

**`DELETE /api/gdpr/account` (`gdpr.py:201-254`)** — cela „erazura" je `_delete()` na `:219-228`:
```python
supa.table("profiles").update({"email": anon_email, "full_name": "Obrisani korisnik"}).eq("id", uid).execute()
supa.table("korisnik_email_notif").upsert({"user_id": uid, "aktivan": False}, on_conflict="user_id").execute()
```
- **Dve tabele. Ništa drugo.**
- **Supabase Storage: nikad dodirnut.** Nula referenci na `storage` u fajlu.
- **Pinecone: nikad dodirnut.** Nula referenci. Svaki vektor svakog dokumenta svakog predmeta „obrisanog" korisnika ostaje živ i dohvatljiv.
- **Soft, ne hard:** `auth.users`, `predmeti`, `klijenti`, `predmet_dokumenti` ostaju sa originalnim `user_id`.

**`services/retention_service.py`** briše samo `security_events` (90 d), `user_daily_activity` (90 d), `ai_forensics` (180 d) i `tmp_*` Pinecone namespace-ove. **Trajni namespace-ovi (`kancelarija_*`, `pred_*`, `user_*`) su van svake retencione putanje u sistemu.** Docstring (`:14-18`) obrazlaže izuzeće predmeta kao pravnu odluku — ali ta odluka je doneta za *DB redove*, a tiho izuzima i vektorski indeks, za koji nigde u repou ne postoji pravno opravdanje retencije.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F14-01** 🔴 | `gdpr.py:247-249` | `{"ok": True, "poruka": "Vaš korisnički nalog je anonimizovan..."}` | **Nijedan od dva `.execute()` rezultata se ne proverava.** Ako `profiles` UPDATE pogodi nula redova (pogrešan id, RLS, `migrations/103_lambda002_profiles_column_lockdown.sql`), funkcija i dalje vraća uspeh. Poruka na `:250-253` pošteno kaže da predmeti/klijenti/dokumenti nisu anonimizovani — **ali ne pominje vektorski indeks.** Korisniku je rečeno da je nalog anonimizovan; dokumenti predmeta ostaju zauvek pretraživi i vraćaju se u RAG odgovorima. |
| **F14-02** 🟠 | `gdpr.py:237-245` | erazura evidentirana | Jedini nepromenljivi dokaz da je zahtev po čl. 17 ispoštovan ide kroz `_spawn_bg`, a kod sam piše: *„Lost on any redeploy in that window, silently."* Uz to `log_action` (`audit_immutable.py:270`) guta svaki neuspeh upisa. |
| **F14-03** 🟡 | `retention_service.py:79-81` | `{"status":"ok","obrisano": 0}` | `obrisano = len(result.data or [])` — sa PostgREST `Prefer: return=minimal` `data` je prazan i na uspešnom brisanju, pa je „obrisano 0 jer nije bilo šta" nerazlučivo od „obrisano N ali ne znam". |
| **F14-04** 🟡 | `uploaded_doc/cleanup.py:86-90` | `namespaces_deleted: N` | Brojači se povećavaju **pre** `index.delete()` na `:90`, i u `dry_run=True` režimu se i dalje vraća `namespaces_deleted > 0`. Ta cifra se sabira u `ukupno_obrisano` (`retention_service.py:145`). |

---

### TOK 15 — UPLOAD KROZ KLIJENTSKI PORTAL · **DELIMIČNO FUNKCIONALAN (dokument je ćorsokak)**

**START:** `POST /api/client-portal/dokument` (`client_portal.py:514-653`) — **jedina neautentifikovana upload ruta.**

- **Auth:** HMAC magic-link token u `X-Portal-Token` (`_generiši_token` `:81-88` → `base64(predmet_id:user_id:exp).hmac_sha256`), verifikacija `:107-126` (`exp` + `hmac.compare_digest`) + DB provera `is_active` po `sha256(token)`. **Ovo je uredno.**
- **Limiti:** 10 MB, MIME allowlist od 7 tipova, **magic-byte provera (`:573-583`) — jedina u celom repou**, odbijanje praznog fajla. *(Napomena: `text/plain` zaobilazi magic proveru, `:581`; provera veličine je posle `await fajl.read()`, `:563`.)*
- **Storage:** `portal-uploads`, **PLAINTEXT** (`:591-599`) — jedini nešifrovan bucket, i to onaj u koji piše treća strana
- **DB:** jedan red u `client_portal_uploads` (`:610-621`) — **i tu se sve završava**
- **AV:** nema. Ovo je dokumentovan najgori slučaj (SEC-045: *„kanal isporuke malvera od neautentifikovane treće strane u advokatsku kancelariju"*)

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F15-01** 🔴 | `client_portal.py:648-653` | *„Dokument je uspešno dostavljen advokatu."* | Dokument stiže u **jednu sporednu tabelu i ni u jedan AI sistem proizvoda**: nema `predmet_dokumenti`, nema ekstrakcije teksta, nema chunk-ovanja, nema embedding-a, nema Pinecone-a, nema konteksta predmeta, nema provere konflikta, nema Timeline-a. Grep: `client_portal_uploads` čita **samo** advokatska lista na `:682` i ništa drugo u celom repou. **I klijent i advokat razumno čitaju „dostavljeno" kao „u predmetu je".** |
| **F15-02** 🟠 | — | dokument bezbedno uskladišten | Plaintext u bucket-u čiji je `public` flag **UNKNOWN** (nijedna migracija ga ne kreira; potrebna sonda `SELECT id, public FROM storage.buckets;`), bez RLS na `storage.objects`, bez AV provere. |
| **F15-03** 🟡 | `client_portal.py:298-301, 646` | token kreiran, klijent obavešten | `_send_portal_email_bg` i `_notify_advokat_upload_bg` gutaju svaki izuzetak (`:156-157`, `:179-180`). Ako je SMTP dole ili `_EMAIL_ENABLED` False (`:60-63` instalira stub koji uvek diže `RuntimeError`), **klijent nikad nije kontaktiran i niko to ne sazna.** |

*(Ispravno urađeno i vredi zabeležiti: putanja neuspelog DB insert-a ranije JESTE bila lažni uspeh i sada je zatvorena kompenzujućim brisanjem + poštenim 500 — `:623-641`.)*

---

### TOK 16 — ČITANJE KROZ KLIJENTSKI PORTAL · **VEROVATNO NE RADI**

**START:** `GET /api/client-portal/view` (`client_portal.py:385`) i `api.py:2634` (druga portal ruta).

**Dva nezavisna razloga zbog kojih ovaj tok pada, oba u `asyncio.gather` bez `return_exceptions=True`:**

**Razlog 1 — `client_portal.py:424` + `:453`:**
```python
predmet_r, hron_r, roc_r, rokovi_r = await asyncio.gather(   # :424 — bez return_exceptions, bez try/except
    ...
    .select("dogadjaj, datum_iso, vaznost, tip_roka")        # :453 — predmet_hronologija
```
**`tip_roka` nema nijednu definiciju u ijednom `.sql` fajlu** (grep → 0 pogodaka). `predmet_hronologija` je definisana samo u `supabase_setup.sql:406-418` sa kolonama `id, predmet_id, user_id, dokument_naziv, datum, datum_iso, dogadjaj, akter, vaznost, created_at`. PostgREST na nepoznatu kolonu vraća HTTP 400 → supabase-py diže → **bez `return_exceptions=True` ceo portal view umire sa 500**, ne degradiranim panelom, plus tri napuštene korutine.

**Razlog 2 — `api.py:2634-2691`:** ista `gather` bez `return_exceptions`, sa `supa.table("rokovi")` — tabelom koja **nema `CREATE TABLE` nigde u repou** (v. Tok 20).

**Ostale rute portala:** `:313` (lista tokena) i `:658` (lista upload-a) su autentifikovane i rade.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F16-01** 🟠 | `client_portal.py:874` | *„Potvrda pregleda je zabeležena. Hvala."* | UPDATE je u `except Exception: pass` (`:865-866`), filtriran **samo po `token_hash`** bez `user_id`/`predmet_id` scoping-a, na koloni za koju kod sam sumnja da možda ne postoji (`:857`). Klijent vidi potvrdu, advokat dobija mejl obaveštenja (`:869`) — **obe strane veruju da je događaj zabeležen, a nije.** |
| **F16-02** 🟠 | `client_portal.py:347, 693` | HTTP **200** + prazna lista | Na bilo koju grešku baze: `{"tokeni": [], "napomena": "Tabela ... ne postoji"}`. **„Nemate klijentskih upload-a" i „baza je pala" su isti odgovor** za svakog klijenta koji gleda status kod. |
| **F16-03** 🟡 | `client_portal.py:706-707` | red vraćen | Neuspeh generisanja signed URL-a je `except: pass` → `"download_url": None` bez objašnjenja. |

**Napomena o dokazu:** Da li `tip_roka` i `rokovi` postoje u živoj bazi je **UNKNOWN**. Ako ne postoje — portal je mrtav, ne degradiran. Ako postoje (dodati ručno van migracija) — tok radi, ali repo o njemu nema istinu. **Oba ishoda su problem; drugi je gori jer znači da šema nije u verziji.**

---

### TOK 17 — PRIJAVA NETAČNOG ODGOVORA · **NE RADI KAO PROIZVOD**

**Četiri nepovezana ponora za povratnu informaciju**, a onaj izričito napravljen za „AI je pogrešio" je najslabiji.

**17.1 `POST /api/feedback` — `routers/drafting.py:820-841` — ruta za „netačan odgovor":**
```python
    except Exception as _exc:
        _sentry_capture(_exc)
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}          # ← drafting.py:841, UNUTAR except bloka
```
- **`return {"status": "ok"}` unutar `except Exception`.** Doslovan, bezuslovan lažni uspeh.
- Čuva se **samo `q_hash` + `tip`**. Ne čuva se pogrešan odgovor, ne tačan odgovor, ne predmet, ne izvori, ne model. **Prijava je neupotrebljiva po konstrukciji.**
- **Ništa je ne čita.** `grep 'table("feedback")'` → tačno jedan pogodak, ovaj insert. Nema dashboard-a, nema cron-a, nema analitike.

**17.2 `POST /api/corrections/capture` — `routers/corrections.py:232-319` — stvarni signal.** Dobro napravljen: detekcija negacionih markera (`:134-154`, hvata „nije obavezan" → „je obavezan"), semantički prag, GPT-4o-mini klasifikacija. Piše `ai_corrections`, agregira u `firm_style_profile`.
**Ćorsokak potrošnje:** grep `firm_style_profile` van ovog fajla → `routers/proof.py:163` i `scripts/proof_direct.py:79` — **oba su provere postojanja šeme, ne čitaoci.** Profil se piše, spaja, GPT-obogaćuje i **nikad ne vraća ni u jedan prompt.**

**17.3 `POST /api/learning/recommendation-feedback` — `routers/learning.py:396-421`.**
**17.4 `POST /api/voice/feedback` — `routers/voice.py:561-586`.**

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F17-01** 🔴 | `routers/drafting.py:841` | `{"status": "ok"}` | Unutar `except`. Prijava da je AI dao pogrešan odgovor je „primljena" i kad insert padne. A i kad prođe — red čita **ništa, nigde**. |
| **F17-02** 🟠 | `routers/learning.py:414-418` | *„Hvala na povratnoj informaciji. Sistem uči."* | `return` je **van** `try`, rezultat se nikad ne proverava. Odbijanje loše AI preporuke vraća zahvalnicu i kad je update pukao ili pogodio nula redova. Ova tabela **jeste** čitana (`confidence_audit.py:80,143,156`, `court_predictor.py:1829`, `services/confidence_auditor.py:73,145`) → tiho ispuštena odbijenica znači da confidence auditor i dalje ocenjuje preporuku kao neodbijenu. |
| **F17-03** 🟠 | `routers/corrections.py:568-581` | `{"ok": True, "processed": n}` | Svih 50 korekcija se okreće na `processed=True` i kad `firm_style_profile` upsert (`:534-566`) pukne i samo se loguje. **Signal učenja je potrošen i bačen.** |
| **F17-04** 🟠 | `routers/corrections.py:415` | *„Na osnovu N korekcija, sistem uči vaš stil pisanja."* | `firm_style_profile` nema nijednog čitaoca van dve provere šeme. **Tvrdnja je netačna kako je napisana.** |
| **F17-05** 🟡 | `routers/voice.py:583-586` | `{"ok": True}` | `except → logger.warning`, `return` bezuslovan. `usage_events` je izuzet iz retencije i čita se samo za brojače. |

---

### TOK 18 — OBRAČUN TROŠKA AI · **DELIMIČNO FUNKCIONALAN (ispravljen nalaz)**

**Dva nezavisna, nepreklapajuća sistema.**

**18.1 `shared/cost.py` → `api_costs` (USD).** `record_cost` se poziva preko aliasa `_rc` na **`main.py:2317`** i **`strategija.py:834, 858`** *(koreni fajl, koji `routers/strategija.py:28` uvozi)*. Parovi `begin_cost_tracking`/`log_cost_to_db`:

| Par | Da li lanac radi? |
|---|---|
| `api.py:3386/3391` → `/api/pitanje` → `main.py::_pozovi_openai` | **✔ RADI** |
| `routers/strategija.py:695/729` → `kompletna_analiza` → koreni `strategija.py::_gpt_json/_gpt_text` | **✔ RADI** |
| `routers/hearing_cc.py:373/468` | **✘ SLOMLJEN** — GPT poziv na `:387` je sirov `AsyncOpenAI` i nikad ne zove `record_cost` |
| `routers/strategija.py:898/913` (strategija_v2) | **✘ SLOMLJEN** — isti razlog, sirov `AsyncOpenAI` na `:896` |

**18.2 `shared/usage.py::UsageService.consume` → `feature_usage` + `feature_usage_log` (krediti).** Poziva se iz ~113 rutera. **Gejtuje kredite, ne meri dolare.** Modul sam meri (`usage.py:326-332`) da **0 od 113 pozivnih mesta** prosleđuje `predmet_id`; token polja su takođe uglavnom neprosleđena.

**18.3 AI pozivi potpuno van `UsageService`** (18 fajlova, verifikovano): `app/services/retrieve.py`, `drafting/router.py`, `main.py`, `nacrti/checklist_engine.py`, `routers/auto_discovery.py`, `routers/batch_ingest.py`, `routers/integracije.py`, `routers/law_upload.py`, `routers/proof.py`, `services/agent_tasks/precedents_radar.py`, `services/ambient_analyzer.py`, `services/case_pipeline.py`, `services/learning_engine.py`, `services/legal_reasoning_engine.py`, `shared/ai_fabric.py`, `shared/intake_classify.py`, `shared/intake_extract.py`.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F18-01** 🟠 | `shared/cost.py:86-88` | endpoint je instrumentiran za trošak | `if cost_usd == 0.0: return`. Dva endpointa (`hearing_cc`, `strategija_v2`) izgledaju potpuno instrumentirano u code review-u i **nisu upisali nijedan red u `api_costs` otkad postoje.** Kvar je tih po dizajnu. |
| **F18-02** 🟠 | `shared/usage.py:230-242` | HTTP 200, funkcija dozvoljena | `except → logger.warning("use not counted, request allowed") → return 0`. Ako **migracija 108** nije primenjena na nekom okruženju, **svako dnevno ograničenje tiho prestaje da postoji** dok svaki zahtev vraća 200. *(Memorija tvrdi da je 108 primenjena; to je vlasnikova potvrda, ne dokaz gate-a — **UNKNOWN** bez sonde.)* |
| **F18-03** 🟡 | `shared/cost.py:57-64` | trošak zabeležen | `_PRICES` tabela je iz „juna 2025" i sadrži samo gpt-4o/4o-mini/4/3.5-turbo. Svaki noviji model se naplaćuje po gpt-4o cenama uz samo log liniju. |
| **F18-04** 🟡 | `shared/usage.py:424-427` | — | `_log_usage_event` guta na `logger.debug` → red billing telemetrije može da nestane bez signala. |
| **F18-05** 🟠 | `routers/praksa.py:571` | — | v. Tok 19: **do 20 plaćenih poziva po jednom renderu pretrage, bez ijednog kredita.** |

*(`api_costs` nema `CREATE TABLE` u `migrations/` ni `supabase_setup.sql` — DDL postoji samo u legacy `supabase_migration.sql`. Postojanje u živoj bazi **UNKNOWN**.)*

---

### TOK 19 — RATIO DECIDENDI · **RADI ALI JE SKUP I NENAPLAĆEN**

**START:** `POST /api/praksa/ratio` (`routers/praksa.py:569`) → `asyncio.gather` nad **do 20 odluka** (`:575`).
**Nije mrtav kod** — `static/vindex.js:8499-8502` automatski poziva `praksa_fetch_ratios()` na **svaku** pretragu prakse, a `:8460-8462` renderuje kutiju „Pravni stav suda".

- **Klijent:** sirov `OpenAI()` (`:340-345`), `gpt-4o-mini`, `max_tokens=220`, `timeout=25.0`. **Ali:** zbog patch-a na klasi (§1/A4) **prolazi kroz prompt guard i provenance.** Ono što NE dobija je ceo sloj kredita/troška.
- **Zavisnosti:** `user: dict = Depends(get_current_user)` — **i ništa više.** Sestrinske rute u istom fajlu imaju `PermissionService.require("sudska_praksa")` (`:726`) i `UsageService.consume(...)` (`:784`). **Nijedno se ne pojavljuje na ratio putanji.**
- **DB:** `ratio_decidendi` — DDL **samo** u legacy `supabase_migration.sql:167-183`, **nema ga u `migrations/` ni u `supabase_setup.sql`**. U repou postoji zabeležena živa sonda: `docs/beta_gate/SCHEMA_RECON_TRI_TABELE.md:20` → `PGRST205 "Could not find the table 'public.ratio_decidendi'"`.

**⚠ TAČKE LAŽNOG USPEHA**

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F19-01** 🟠 | `routers/praksa.py:319-326` | običan cache miss | `PGRST205 table-not-found` se guta na `logger.debug` i vraća `None` — **bajt-identično legitimnom promašaju.** `_extract_ratio_sync` onda plaća LLM poziv. **Do 20 plaćenih `gpt-4o-mini` poziva po renderu rezultata pretrage, zauvek, bez ijednog kredita i bez ikakvog troškovnog traga.** |
| **F19-02** 🟠 | `routers/praksa.py:333-336` → `:383` | log `"[RATIO] MISS→extracted"`, ratio vraćen | `_save_ratio_to_cache` vraća `None` bez obzira na ishod. Svaki sledeći pregled iste odluke ponovo plaća. |
| **F19-03** 🟡 | `routers/praksa.py:589-597` | HTTP 200 `{"ratios": {...}}` | `return_exceptions=True` pa `if isinstance(r, Exception) or r is None: continue`. Odluka čiji je LLB poziv pukao je **prosto odsutna iz mape**; frontend (`vindex.js:8769`) je razrešava u `null` i prikazuje placeholder. Nema brojača grešaka, nema signala. |

---

### TOK 20 — ROKOVI · **NAJTEŽI NALAZ U CELOJ MISIJI**

Ovo je za pravni SaaS najozbiljniji tok, i pada na **četiri nezavisna načina istovremeno**.

#### 20.1 Deterministički kalkulator JESTE dobar

`routers/rokovi_lanac.py` — `_TIPOVI` (`:30-278`): 16 tipova događaja po ZPP / ZKP / Zakonu o radu / ZUP / ZUS / ZIO, svaki sa `dana`, `zakonski_osnov` (npr. `"ZPP čl. 374 st. 1"` = 15 dana za žalbu), `vaznost`. Srpski praznici (`:304-327`), pomeranje na prvi radni dan (`:328`), čista aritmetika bez LLM-a (`:335`). **Ovo je najbolje inženjerski urađen deo toka.**

*Napomena za budućnost:* pravoslavni Uskrs je hardkodovan **samo za 2025-2027** (`_PRAZNICI_POKRETNI`). Od 2028. `_je_neradan()` prestaje da ga prepoznaje i kalkulator tiho vraća **preran** datum. Tempirana bomba, ne pad.

#### 20.2 🔴 **F20-01 — izračunati rok se NIKAD ne upisuje. CHECK-constraint sudar.**

```sql
-- supabase_setup.sql:414-416
vaznost TEXT NOT NULL DEFAULT 'informativan'
        CHECK (vaznost IN ('kritičan','važan','informativan')),
```
```python
# routers/rokovi_lanac.py:283-287
_VAZNOST_HRON = {"kritican": "kljucan", "vazno": "normalan", "info": "info"}
# :427  "vaznost": _VAZNOST_HRON.get(r["vaznost"], "normalan")
```
**Nijedna od tri vrednosti — `'kljucan'`, `'normalan'`, `'info'` — nije u CHECK skupu. Ni default `.get(..., "normalan")` nije.**
Insert (`:435-440`) je u `except → logger.warning`; `return` (`:448-457`) je bezuslovno `{"ok": True, "lanac": [...15 rokova...], "sacuvano_u_predmet": False}`.

**Šta korisnik vidi — dve različite neistine:**
- `static/vindex.js:22605-22618` — renderuje **svih 15 rokova sa citatima `ZPP čl. 374 st. 1`, obojenih crveno kao `KRITIČAN`**, uz zeleni bedž „Sačuvano u hronologiji" **samo ako** `sacuvano_u_predmet`. Bez tog bedža nema **nikakve** naznake da ništa nije sačuvano. Advokat zatvori tab; rokovi su nestali.
- `static/vindex.js:11881-11905` — dugme *„⛓ Sačuvaj u hronologiju predmeta →"*: `if (!r.ok) {...}` nikad ne opali (HTTP je 200), `if (d.sacuvano_u_predmet) {...}` nikad ne opali (False). **Dugme se tiho vrati u pređašnje stanje. Nijedan toast, nijedna greška, nijedna promena.**

**Isti bug, drugi pisac:** `routers/intake.py:282-294` upisuje `"vaznost": "bitan"` — takođe van CHECK-a. `rok_dodat` se vraća na `:443`, a `grep "rok_dodat" static/vindex.js` → **ništa.** Prvi rok Intake čarobnjaka se nikad ne sačuva i to se nikad ne prikaže.

**Test kodifikuje kvar kao ugovor:** `tests/test_rokovi_lanac.py:212-217` — `assert result["ok"] is True` uz `insert_ok=False`. Zeleno.

**⚠ UNKNOWN koji se MORA navesti:** `routers/email_notif.py:60-79` sadrži dug komentar koji imenuje baš ovaj rečnik (`"bitan"`, `"kljucan"`, `"važan"`) i **proširuje READ filter** na `["kritičan","važan","bitan","kljucan","normalan"]` da bi pokrio vrednosti koje baza po ovoj definiciji **fizički odbija na upisu**.
Dva mogu­ća objašnjenja, oba važna:
1. CHECK je i dalje živ → svaki takav upis pada, a read filter je proširen na redove koji ne mogu postojati.
2. CHECK je ručno proširen van migracija → upisi rade, ali **šema nije u verziji** i repo o njoj nema istinu.
**Koje je tačno je UNKNOWN i dokazuje se isključivo sondom `information_schema.check_constraints`.** Oba ishoda su nalaz.

#### 20.3 🔴 **F20-02 — tabela `rokovi` nema `CREATE TABLE` nigde, a 13 mesta je čita**

Iscrpno po `migrations/*.sql` (103 fajla), `supabase_setup.sql`, `supabase_migration*.sql`: **nula `CREATE TABLE ... rokovi`.**

Jedini trag u šemi je indeks nad tabelom koja se nikad ne kreira:
```sql
-- migrations/023_stability_500_users.sql:19-21
CREATE INDEX IF NOT EXISTS rokovi_datum_user_idx ON rokovi (user_id, datum) WHERE obrisan = false;
```
`CREATE INDEX IF NOT EXISTS` **ne toleriše nedostajuću tabelu** — puca sa `42P01`. Dakle migracija 023 ili nikad nije pokrenuta, ili je pukla na tom mestu i ništa posle nje se nije primenilo.

**13 čitalaca, nula pisaca** (nema nijednog `INSERT` u `rokovi` u celom repou): `api.py:2639` (klijentski portal), `case_commander.py:134, 610`, `dashboard.py:141` (Command Center), `decision_replay.py:97`, `integrations.py:395` (Google Calendar sync), `morning_briefing.py:115, 140, 1137`, `whatsapp_notif.py:303, 415`, `zadaci.py:642`, `zastarelost.py:505` (AI Deadline Guardian).

**Stvarna tabela je `predmet_hronologija`**, i nju ispravno čitaju `kalendar.py:76`, `email_notif.py:315`, `sms.py:254`, `notifications.py:173`, `dashboard.py:88`, `rokovi_lanac.py:435`, `case_dna.py:672`, `intake.py:282`. **Sistem ima dva pojma „rok" i jedan od njih nema tabelu.**

#### 20.4 🔴 **F20-03 — oba cron workflow-a se autentifikuju pogrešnom šemom i zelena su**

```yaml
# .github/workflows/email-cron.yml:12-15  (i sms-cron.yml, identično)
curl -X POST https://vindex.rs/email-notif/send-reminders \
  -H "Authorization: Bearer ${{ secrets.CRON_TOKEN }}"
```
Server (`routers/email_notif.py:84-99`) prihvata **`X-Cron-Key: <CRON_SECRET>`** ili **Supabase JWT čiji je `email` claim founder**. Neprozirni token u `Authorization` zaglavlju ne zadovoljava ni jedno ni drugo → `_verify_token` vraća `None` → **403**.
SMS je gori: `routers/sms.py:217-225` koristi `Depends(get_current_user)`, što traži pravi Supabase JWT → **401 pre nego što se do founder provere uopšte stigne.**

**A kvar je nevidljiv:** `curl` je pozvan **bez `-f` / `--fail`**. `curl` izlazi sa kodom `0` na HTTP 403/401 telu. **GitHub Actions korak uspeva, posao je zelen**, i dashboard prikazuje uspešan dnevni „Email Podsetnici za rokove" svaki dan otkad workflow postoji — dok je poslato nula podsetnika.

*(Vrednost `CRON_TOKEN` je **UNKNOWN**. Jedini scenario u kome ovo radi je da je to founder JWT koji ne ističe — Supabase takve ne izdaje po defaultu.)*

#### 20.5 🟠 **F20-04 — `/api/cron/daily` nema nijednog zakazivača u repou**

`api.py:1809` je dispečer za workflow eskalacije, monitoring zakona, retenciju i `run_background_agents()` (`:2159-2160`). Autentifikacija mu je ispravna i fail-closed (`:1834-1835`).
Ali: grep `cron/daily|BRIEFING_CRON_SECRET` po `*.yml`, `*.toml`, `Procfile`, `*.json` → **nula rezultata.** `Procfile` ima samo `web:` dyno, `railway.toml` nema cron blok. Jedini dokaz rasporeda je **proza u komentaru** (`api.py:1814` „Render.com cron 07:00 UTC", `:1857` „Proveriti cron-job.org"). **Dva različita spoljna zakazivača imenovana u komentarima, nijedan konfigurisan u repou.** Detektor zastarelosti (`:1856`) opali **samo iz unutrašnjosti pokretanja** — ako cron nikad ne krene, ni alarm nikad ne krene.

#### 20.6 Ostale tačke lažnog uspeha u ovom toku

| ID | Mesto | Sistem tvrdi | Stvarnost |
|---|---|---|---|
| **F20-05** 🔴 | `routers/morning_briefing.py:1136-1158` | *„Hitni rokovi ≤3 dana: —"* | Goli `except Exception: pass` oko čitanja `rokovi`. **Advokatu se proaktivno saopštava da nema rok u naredna 3 dana, izvedeno iz tabele koja nema šemu.** Ovo je najopasnija pojedinačna instanca u celom dokumentu. Suprotno tome, `:104-155` istog fajla koristi `gather` **bez** `return_exceptions` pa tvrdo pada — **dve grane iste funkcije, jedna 500-ira, druga laže.** |
| **F20-06** 🟠 | `routers/zastarelost.py:519-522` | *„Nema rokova u narednih 30 dana."* | Ista fantomska tabela. Ovde `.execute()` nije uhvaćen pa bi endpoint 500-irao — ali je gejtovan sa `PermissionService.require("zastarelost_guardian")`, tako da provera dozvole prođe a funkcija pukne. Korisniku je rečeno da ima pristup funkciji koja ne može da se izvrši. |
| **F20-07** 🟠 | `routers/dashboard.py:264-272` | panel rokova sa `"izvor": "rokovi"` | `_safe()` (`:172-175`) pretvara svaki izuzetak u `[]`. Command Center renderuje spajanje dva izvora, tiho ispušta jedan, **i pritom preživele redove žigoše poljem `izvor` koje reklamira spajanje dva izvora.** Uz `gather_with_timeout`, kvar je strukturno nedetektabilan iz odgovora. |
| **F20-08** 🟡 | `routers/integrations.py:394-435` | `{"synced": N, "errors": 0}` | Google Calendar sync čita `rokovi`. Ako bi ikad „popravljeno" da vraća prazno, endpoint bi prijavio čist uspeh za sinhronizaciju koja nije prenela ništa. Uz to: OAuth tokeni se čuvaju **nešifrovano** (`:359-360`). |
| **F20-09** 🟠 | `services/case_pipeline.py:381-382` | pipeline korak završen | Neuspeo insert **izvučenog zakonskog roka** loguje se na `logger.debug` i odbacuje. |

---

## §3. ZBIRNA TABELA — SVE TAČKE LAŽNOG USPEHA

**🔴 = korisnik donosi pravnu odluku na osnovu neistine · 🟠 = tihi gubitak podataka/kontrole · 🟡 = degradacija bez signala**

| ID | Tok | Ozbiljnost | Jednorečenično |
|---|---|---|---|
| F1-01 | 1 | 🔴 | Odjava je zagarantovan no-op; poruka „odjavljeni sa svih uređaja" je neistinita (verifikovano protiv `supabase==2.28.3`) |
| F1-02 | 1 | 🔴 | RBAC fail-OPEN na `ADVOKAT` → pristup šifrovanom PII-u na grešku baze |
| F1-03 | 1 | 🟠 | Limit sesija se sam gasi (`return 0`) |
| F1-04 | 1 | 🟠 | „Sesija registrovana" bez reda u tabeli |
| F1-05 | 1 | 🟠 | Enterprise tiho postaje „basic" na delimičnoj grešci baze |
| F1-06 | 1 | 🟡 | Neparsiv datum isteka = pretplata važi |
| F1-07 | 1 | 🟡 | Registracija uspeva bez `profiles` reda i bez trial polja |
| F1-08 | 1 | 🟡 | Izmišljen 30-dnevni trial na grešku |
| F1-09 | 1 | 🟡 | „Dobrodošli!" i kad onboarding update padne |
| F1-10 | 1 | 🟡 | `login_success` nema pozivaoca; `login_failed` u dva sloja tišine |
| F1-11 | 1 | 🟡 | JWKS izbor ključa: `or` čini `alg` proveru kozmetičkom |
| F2-01 | 2 | 🔴 | Clio webhook uzima `user_id` (tenant) iz tela zahteva |
| F2-02 | 2 | 🔴 | `POST /v1/predmeti` → HTTP 201 „kreiran" sa praznim predmetom; bez sanitizacije/eventa/audita/rate-limita |
| F2-03 | 2 | 🟠 | Case Pipeline trajno izgubljen, HTTP 200 |
| F2-04 | 2 | 🟠 | Pipeline vraća 9× FAILED kao HTTP 200; izgubljeni rokovi na `logger.debug` |
| F2-05 | 2 | 🟠 | Blokirajući `.execute()` u `async def` blokira event loop |
| F2-06 | 2 | 🟡 | `row.data[0]` → 500 posle commit-a |
| F2-07 | 2 | 🟡 | Naziv predmeta u neizbrisiv hash-lanac (zabranjeno u sestrinskom handleru) |
| F2-08 | 2 | 🟡 | Event-bus handler greške umiru u `create_task` |
| F2-09 | 2 | 🟡 | Demo predmet pravi duplikate; 4 pod-objekta se gutaju |
| F3-01 | 3 | 🔴 | **Playbook upload je 100% slomljen** — 5-torka u 2 promenljive, nehvatan 500 |
| F3-02 | 3 | 🔴 | Original fajla nije sačuvan, `storage_path` je izmišljena labela, HTTP 200 |
| F3-03 | 3 | 🟠 | Nepotpun ingest u `dokument.py` bez zastavice (dva sestrinska ga imaju) |
| F3-04 | 3 | 🟠 | Bilo koji „429" = „kvota" → dokument neindeksiran, HTTP 200 |
| F3-05 | 3 | 🟠 | Merdevine od 6 varijanti insert-a gutaju sve na `logger.debug` |
| F3-06 | 3 | 🟠 | Izmišljena klasifikacija dokaza bez markera greške (popravljeno u `evidence.py`, ne u `dokument.py`) |
| F3-07 | 3 | 🟠 | Izgubljen `NEW_EVIDENCE_REGISTERED` = nema klasifikacije/Vault-a/Timeline-a, HTTP 200 |
| F3-08 | 3 | 🟡 | „Nije duplikat" iako provera nije izvršena |
| F3-09 | 3 | 🟡 | DOK-NN numeracija se tiho resetuje |
| F3-10 | 3 | 🟡 | Log klasifikacije uvek ispisuje `?` (pogrešan ključ) |
| F4-01 | 4 | 🟠 | Audit dokazuje brisanje; plaintext fajl ostaje u bucket-u kao siroče |
| F4-02 | 4 | 🟡 | Kompenzujuće brisanje može da padne → nepraćeno siroče |
| F6-01 | 6 | 🟠 | 399 od 400 stranica zakona može da padne — „zakon" ide u korpus |
| F6-02 | 6 | 🟠 | Smart Intake: predmet kreiran sa nula dokumenata, HTTP 200 |
| F6-03 | 6 | 🟡 | 101 znak prolazi kao potpun dokument |
| F7-01 | 7 | 🟠 | `drafting/playbook.py` jedini bez provere dužine `zip`-a |
| F7-02 | 7 | 🟡 | `governance_status()` tvrdi `active:true` i kad embeddings patch padne |
| F8-01 | 8 | 🔴 | 99/100 upsert batch-eva može da padne → zakon je `done` u pravnom korpusu |
| F8-02 | 8 | 🔴 | Treptaj baze → dokument kancelarije u lični namespace, tiho i trajno |
| F8-03 | 8 | 🔴 | `vector_deletion` ima nula produkcionih pozivalaca |
| F8-04 | 8 | 🟠 | Beleška sačuvana, embedding tiho izgubljen, zauvek nepretraživa |
| F9-01 | 9 | 🔴 | Ispad Pinecone-a = „nema rezultata" = tvrdnja o srpskom pravu |
| F9-02 | 9 | 🟠 | >400 predmeta → tiho sužavanje pretrage |
| F9-03 | 9 | 🟠 | `ai_cache` globalan bez tenant ključa, čuvan dvema literalnim niskama |
| F9-04 | 9 | 🟡 | `kb_*` / `interni_stavovi_*` bez metadata filtera |
| F10-01 | 10 | 🔴 | `{"status":"success","blocked":True}` — odbijen odgovor broji se kao uspeh |
| F10-02 | 10 | 🟠 | Realtime WSS bez guard-a/firewall-a/timeout-a |
| F11-01 | 11 | 🟠 | Gubitak provenance-a na `logger.debug` (nevidljivo u produkciji) |
| F11-02 | 11 | 🟠 | Bez migracije 089 provenance je bez join ključeva (status UNKNOWN) |
| F12-01 | 12 | 🔴 | Brisanje dokumenta ne postoji; brisač vektora nije povezan |
| F13-01 | 13 | 🟠 | Onboarding obećava „obrišite ga kad želite" — sposobnost ne postoji |
| F14-01 | 14 | 🔴 | GDPR: „nalog anonimizovan" bez provere rezultata, bez Storage-a, bez Pinecone-a |
| F14-02 | 14 | 🟠 | Jedini dokaz erazure je fire-and-forget („lost on redeploy, silently") |
| F14-03 | 14 | 🟡 | `obrisano: 0` isto za uspeh i za no-op |
| F14-04 | 14 | 🟡 | Brojači brisanja rastu pre `delete()` i u `dry_run` |
| F15-01 | 15 | 🔴 | „Dokument dostavljen advokatu" = red u sporednoj tabeli, nevidljiv svakom AI sistemu |
| F15-02 | 15 | 🟠 | Plaintext, bez AV, bucket public flag UNKNOWN |
| F15-03 | 15 | 🟡 | Mejl klijentu tiho ne stigne |
| F16-01 | 16 | 🟠 | „Potvrda pregleda zabeležena" iza `except: pass` |
| F16-02 | 16 | 🟠 | HTTP 200 + prazna lista = „baza je pala" |
| F16-03 | 16 | 🟡 | `download_url: None` bez objašnjenja |
| F17-01 | 17 | 🔴 | `return {"status":"ok"}` **unutar** `except`; a i uspešan red niko ne čita |
| F17-02 | 17 | 🟠 | „Sistem uči" vraćeno van `try`, rezultat neproveren |
| F17-03 | 17 | 🟠 | 50 korekcija „processed" i kad profil nije upisan |
| F17-04 | 17 | 🟠 | „Sistem uči vaš stil" — `firm_style_profile` nema čitaoca |
| F17-05 | 17 | 🟡 | Glasovni feedback `{"ok":True}` bezuslovno |
| F18-01 | 18 | 🟠 | 2 endpointa izgledaju instrumentirano, upisala su nula redova u `api_costs` |
| F18-02 | 18 | 🟠 | Bez migracije 108 sva dnevna ograničenja tiho nestaju |
| F18-03 | 18 | 🟡 | Cenovnik iz „juna 2025" — noviji modeli pogrešno naplaćeni |
| F18-04 | 18 | 🟡 | `feature_usage_log` može da nestane na `logger.debug` |
| F18-05 | 18 | 🟠 | Ratio: do 20 plaćenih poziva po renderu, bez kredita |
| F19-01 | 19 | 🟠 | `table-not-found` = cache miss → plaća se zauvek |
| F19-02 | 19 | 🟠 | „MISS→extracted" i kad upis keša padne |
| F19-03 | 19 | 🟡 | Pukle odluke tiho odsutne iz mape, bez brojača |
| F20-01 | 20 | 🔴 | **Rokovi se računaju, prikazuju crveno kao KRITIČAN, i nikad ne upisuju** (CHECK sudar); dugme „Sačuvaj" ne daje nikakvu povratnu informaciju |
| F20-02 | 20 | 🔴 | `rokovi` — 13 čitalaca, nula pisaca, nula `CREATE TABLE` |
| F20-03 | 20 | 🔴 | Oba cron-a šalju pogrešnu auth šemu; `curl` bez `-f` → **zelen CI, nula poslatih podsetnika** |
| F20-04 | 20 | 🟠 | `/api/cron/daily` nema zakazivača u repou — samo proza u komentarima |
| F20-05 | 20 | 🔴 | Jutarnji brifing tvrdi „nema hitnih rokova" iz `except: pass` nad fantomskom tabelom |
| F20-06 | 20 | 🟠 | Deadline Guardian: dozvola prođe, funkcija pukne |
| F20-07 | 20 | 🟠 | Command Center žigoše `izvor: "rokovi"` na spajanju iz kog je taj izvor ispao |
| F20-08 | 20 | 🟡 | GCal sync bi prijavio čist uspeh za nula prenesenih; OAuth tokeni plaintext |
| F20-09 | 20 | 🟠 | Izvučen zakonski rok gubi se na `logger.debug` |

**Ukupno: 76 tačaka lažnog uspeha — 21× 🔴, 33× 🟠, 22× 🟡.**

---

## §4. STATUS 20 TOKOVA

### ✅ POTPUNO FUNKCIONALNI — **1 od 20**

| Tok | Obrazloženje |
|---|---|
| **5 — OCR** | Lokalni Tesseract, nikakav izlaz podataka radi OCR-a; kompletne zaštite od dekompresione bombe; poštena, upotrebljiva poruka o grešci (422 sa tri konkretna koraka); `security_events` audit. Nijedna tačka lažnog uspeha. |

### 🟡 DELIMIČNO FUNKCIONALNI — **12 od 20**

| Tok | Šta radi | Šta ne radi |
|---|---|---|
| **1 login/auth** | JWT potpis se stvarno proverava; nema `verify_signature=False`; `alg=none` nedohvatljiv | Odjava je no-op (F1-01); RBAC fail-open (F1-02); limit sesija se sam gasi; nema `login_success` audita |
| **2 kreiranje predmeta** | Glavna ruta (`api.py:3809`) ima sanitizaciju, dup-guard, durable event i audit | 5 alternativnih puteva nema ništa od toga; Clio webhook uzima tenant iz tela; Pipeline se tiho gubi |
| **3 upload dokumenta** | Glavna ruta je najbolje očvrsnut deo repoa (tvrdi `_dok_id` gate, kompenzujuća brisanja, odbijanje delimičnog ingest-a) | 1 od 9 ruta je 100% slomljena (F3-01); original se tiho ne čuva (F3-02); 9/9 bez AV; 8/9 bez magic-byte provere |
| **4 storage** | `intake-dokumenti` privatan i AES-GCM šifrovan; kompenzujuća brisanja postoje | `portal-uploads` plaintext; 2/3 bucket-a bez migracije; nula RLS politika; rotacija ključa uništava blobove |
| **6 ekstrakcija teksta** | 4 od 5 pozivnih mesta ispravno odbijaju prazan tekst | `law_upload` guta greške po stranici; Smart Intake vraća 200 sa nula povezanih dokumenata |
| **7 embedding** | Delimičan odgovor se odbija na 3 od 4 pisca (`RuntimeError`) | `drafting/playbook.py` bez te zaštite; patch može da padne uz `active: true` |
| **8 Pinecone upsert** | Determinističan identitet, fail-closed bez verzije, ACL filter server-side | `law_upload` „done" uz 99% palih batch-eva; namespace misrouting na treptaj baze; brisač nepovezan |
| **9 RAG retrieval** | **ACL je ispravan i server-side**; `None` sentinel pravilno sprečava prazan filter | 5 funkcija pretvara ispad u „nema rezultata" koji se prikazuje kao pravna činjenica |
| **10 AI odgovor** | Strukturan choke-point, prompt guard, Response Firewall, fail-closed kill-switch | `status: "success"` za blokiran odgovor; Realtime WSS potpuno van kontrola |
| **11 provenance** | Samo heševi, nikad plaintext; redosled prema firewall-u ispravan | Gubitak traga na `logger.debug`; migracija 089 UNKNOWN |
| **14 GDPR brisanje** | Export radi za 5 tabela; poruka pošteno navodi da predmeti nisu anonimizovani | Dodiruje 2 tabele; **nula Storage, nula Pinecone**; rezultat se ne proverava; ne pominje vektorski indeks |
| **18 obračun troška** | 2 od 4 para `begin/log` stvarno rade; `UsageService` gejtuje kredite | 2 para su tihi no-op; 18 fajlova AI poziva potpuno van naplate; `api_costs` bez DDL-a u kanonskoj šemi |

### 🔴 NE RADE — **7 od 20**

| Tok | Presuda |
|---|---|
| **12 brisanje dokumenta** | **Endpoint ne postoji.** Iscrpno dokazano gerp-om i priznato u `shared/audit_immutable.py:68-71`. Dokument u predmetu je trajan: DB red, Storage blob, Pinecone vektori — ništa se ne može ukloniti. `shared/vector_deletion.py` je izgrađen, testiran i nepovezan. |
| **13 brisanje predmeta** | **Endpoint ne postoji**, ni soft delete (`predmeti` nema `deleted_at`). Jedino stvarno brisanje je Postgres kaskada iz Supabase konzole, bez ijednog aplikativnog audita. Onboarding korisniku obećava suprotno. |
| **15 upload kroz portal** | Fajl stiže i uskladišti se (plaintext), ali **ne ulazi ni u jedan AI sistem proizvoda** — nema RAG, nema konteksta predmeta, nema provere konflikta, nema Timeline-a. „Dostavljeno advokatu" znači „red u sporednoj tabeli koju čita jedan ekran". Kao proizvodna sposobnost — ne radi. |
| **16 čitanje kroz portal** | Dva nezavisna razloga za tvrd 500: `tip_roka` bez definicije i `rokovi` bez tabele, oba u `gather` bez `return_exceptions`. **Ako te dve stvari ne postoje u živoj bazi, portal je mrtav a ne degradiran.** (Postojanje = UNKNOWN.) |
| **17 prijava netačnog odgovora** | Namenska ruta vraća `{"status":"ok"}` **iz `except` bloka**, čuva samo heš pitanja bez odgovora/predmeta/izvora, i **niko je ne čita**. Kvalitetan sused (`corrections`) piše `firm_style_profile` koji **nema nijednog potrošača** dok UI tvrdi „sistem uči vaš stil". Kao petlja povratne informacije — ne postoji. |
| **19 ratio decidendi** | Funkcija se renderuje i AI radi — ali keš tabela nema DDL u kanonskoj šemi (živa sonda u repou beleži `PGRST205`), pa se **svaki miss plaća zauvek**: do 20 `gpt-4o-mini` poziva po jednom renderu pretrage, **bez ijednog kredita i bez ijednog troškovnog reda**. Kao ekonomski održiva funkcija — ne radi. |
| **20 rokovi** | **Najteži nalaz.** Deterministički kalkulator je odličan; njegov izlaz se **nikad ne upisuje** (CHECK sudar), prikazuje se advokatu crveno kao `KRITIČAN` sa citatom `ZPP čl. 374 st. 1`, dugme „Sačuvaj" ne daje nikakav odgovor, druga „rok" tabela nema šemu i ima 13 čitalaca i nula pisaca, jutarnji brifing tvrdi „nema hitnih rokova" iz `except: pass`, a oba cron-a za podsetnike vraćaju 403/401 **iza zelenog CI bedža.** Svaki od četiri sloja samostalno obara tok. |

---

## §5. ŠTA JE OVAJ AUDIT DOKAZAO — I ŠTA NIJE SMEO

**Dokazano čitanjem koda i verifikacijom protiv instaliranih biblioteka:** svih 76 tačaka lažnog uspeha, sve rute, sve tabele bez DDL-a, sve odsutne kontrole granice, i tri nezavisno re-verifikovane tvrdnje (`sign_out` potpis, `vaznost` CHECK sudar, cron auth neslaganje, `drafting.py` arnost torke).

**Nije dokazano i ne sme se tvrditi (UNKNOWN, §10):**

| # | Pitanje | Kako se dokazuje |
|---|---|---|
| 1 | Postoje li `rokovi`, `ai_cache`, `ai_sessions`, `klijenti_dokumenti`, `ratio_decidendi`, `api_costs` u živoj bazi | sonda `information_schema.tables` |
| 2 | Da li `predmet_hronologija.vaznost` još nosi originalni CHECK, i postoji li `tip_roka` | sonda `information_schema.check_constraints` + `columns` |
| 3 | Da li su migracije **023**, **089**, **108** primenjene | sonde iz `docs/beta_gate/VERIFY_MIGRATION_*_READONLY.sql` |
| 4 | Da li su `portal-uploads` i `klijent-dokumenti` privatni | `SELECT id, public FROM storage.buckets;` |
| 5 | Vrednost `CRON_TOKEN` i da li ijedan cron ikad prođe | prod secret + jedan log poziva |
| 6 | Da li su Azure OpenAI / Cohere / Twilio / Viber / GCal aktivirani | prod env |
| 7 | Sve o politici provajdera (retencija, treniranje, logovanje) | **DPA — v. `EXTERNAL_BOUNDARY_002.md §5`** |

### §5.1 UKRŠTENI DOKAZ IZ NEZAVISNE §2 SONDE — NIJE PROIZVOD OVOG AUDITA

Tokom ove misije u `docs/beta_gate/` je zatečen `SCHEMA_PHANTOM_INVENTORY.md`, proizvod **odvojene §2 sesije** koja je izvršila **žive `GET /rest/v1/...?select=<kolona>&limit=0` PostgREST sonde**. Taj dokument nije napisao ovaj audit i njegovi nalazi ovde stoje **kao ukršteni dokaz, ne kao sopstveni**:

| Stavka | §2 sonda | Efekat na presudu ovog dokumenta |
|---|---|---|
| `rokovi` | `404 PGRST205` (`:366, :512`) | F20-02 prelazi iz „nema DDL-a u repou" u **potvrđeno ne postoji u produkciji** |
| `ratio_decidendi` | `404 PGRST205` (`:376, :514`) | F19-01 potvrđen: **svaki ratio poziv se plaća, zauvek** |
| `klijenti_dokumenti` | `404 PGRST205`, hint `public.klijent_dokumenti` (`:365`) | potvrđen tipfeler na `klijenti/router.py:1422` |
| `tip_roka` | nedostaje pri čitanju (`:221, :227`) | F16 potvrđen: `client_portal.py:452` čita nepostojeću kolonu |

**Šta ovo menja u §4:** tokovi **16 (čitanje kroz portal)**, **19 (ratio decidendi)** i **20 (rokovi)** prelaze iz „verovatno ne radi" u **dokazano ne radi**, pod uslovom da se prihvati tuđa sonda. Po kućnom pravilu („nikad ne veruj tuđem izveštaju bez sopstvene re-provere") ovaj audit tu sondu **nije ponovio** i zato je drži odvojenom od sopstvenih nalaza. Presuda ovog dokumenta ostaje zasnovana isključivo na kodu; §2 je nezavisno slaganje, a ne izvor.

### §5.2 Preostali UNKNOWN posle ukrštanja

Tačke 2 (CHECK nad `predmet_hronologija.vaznost`), 3 (migracije 023/089/108), 4 (`public` flag bucket-a), 5 (`CRON_TOKEN`), 6 (env aktivacije) i 7 (DPA) **ostaju nedokazane.**

**Najvažnija od njih je tačka 2.** F20-01 tvrdi da se rokovi nikad ne upisuju zbog CHECK sudara. Ako je CHECK ručno proširen van migracija, upisi rade i F20-01 pada — ali tada šema nije u verziji, što je zasebno ozbiljno. **Jedna sonda `information_schema.check_constraints` razrešava najteži nalaz u ovom dokumentu u jednom ili drugom smeru.**

**`SUPABASE_DB_URL` je i dalje neisporučen od Black Swan misije** i bez njega tačke 2-4 ostaju nedokazive.
