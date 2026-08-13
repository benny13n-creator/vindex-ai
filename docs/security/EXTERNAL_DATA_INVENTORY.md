# EXTERNAL DATA INVENTORY — §6 + §7 (NO BLIND SPOTS)

**Datum:** 2026-08-13
**Metod:** statička forenzika nad `git ls-files` skupom (724 praćena `.py`, 5 `.js`, 897 `.html`). Nula izmena produkcijskog koda. Nula mrežnih poziva.
**Pravilo dokaza:** svaka tvrdnja nosi `fajl:linija`. Gde dokaza nema — `UNKNOWN`.

**Ulazna tačka procesa:** `Dockerfile:33` (`uvicorn api:app`) i `Procfile:1` (`gunicorn api:app`). Dakle `api.py` je jedini produkcijski `app`. `main.py` NEMA sopstveni `FastAPI()` i uvozi se iz `api.py:95` — tek POSLE instalacije guard-a (`api.py:27-28`), pa su i njegovi AI pozivi pokriveni.

---

## 0. IZVRŠNI SAŽETAK

| | |
|---|---|
| Produkcijskih OpenAI SDK pozivnih mesta | **91** — svi pokriveni class-level patch-om |
| Klasa koje guard majmun-patchuje | **8** (`Completions`, `AsyncCompletions`, `Embeddings`, `AsyncEmbeddings`, `Transcriptions`, `AsyncTranscriptions`, `Speech`, `AsyncSpeech`) |
| **STVARNIH** bypass-eva chokepoint-a | **3** (1 ŽIV, 1 uspavan, 1 mrtav) |
| Lažnih bypass-eva (odbačeno dokazom) | 91 SDK poziva + Azure redirekcija |
| Pozadinskih AI puteva BEZ korisničkog konteksta | **3**, svi ŽIVI |
| `store=False` / ZDR / org-project zaglavlja u kodu | **NIJEDNO** — retencija 100% zavisi od politike provajdera |
| Eksternih destinacija ukupno | **29** (10 uključeno po defaultu, 19 iza env varijable ili mrtvo) |

---

## 1. KORAK 1 — EGRESS SWEEP

### 1.1 Metod i njegov ISPRAVLJENI oblik

Prvobitni sweep je tražio SAMO sirove mrežne primitive (`requests.`, `httpx.`, `aiohttp`, `urllib`, `websocket(s)`, `fetch(`, `XMLHttpRequest`, `sendBeacon`, `new WebSocket`, `<script src=`, `smtplib`, `boto3`).

**Ta metoda je imala slepu tačku i ovde se to eksplicitno priznaje.** Najveći tokovi klijentskih podataka u Vindexu NE koriste nijedan od tih primitiva — idu kroz SDK-ove (`openai`, `pinecone`, `supabase`, `twilio`). Sirovi-primitiv grep bi propustio Supabase Storage, Pinecone upsert i svih 91 OpenAI poziv.

Metod je zato proširen drugim prolazom nad SDK simbolima: `Pinecone(`, `.upsert(`, `storage.from_`, `.upload(`, `chat.completions.create`, `embeddings.create`, `audio.transcriptions.create`, `audio.speech.create`, `twilio.rest.Client`, `sentry_sdk.init`, `webpush(`. Nalazi ispod su unija oba prolaza. Vidi §5 (negativne kontrole) gde je ovaj propust i otkriven.

### 1.2 Produkcijski egress (routers/, shared/, services/, app/, workers/, security/, api.py, main.py)

| Fajl:linija | Mehanizam | Cilj | Env-gejt | Živ? |
|---|---|---|---|---|
| `services/voice_orchestrator.py:47,531-538` | `websockets.connect` | `wss://api.openai.com/v1/realtime` | `VINDEX_VOICE_KILL` + tarifa | **DA** |
| `routers/voice.py:45` | OpenAI SDK | Whisper STT | ne (`OPENAI_API_KEY`) | DA |
| `routers/voice.py:52` | OpenAI SDK | OpenAI TTS | ne | DA |
| 91 mesta (v. §5.3) | OpenAI SDK | `api.openai.com` (ili Azure) | ne | DA |
| `app/services/retrieve.py:560` | `cohere.Client` | `api.cohere.ai` | **3 gejta**, default OFF | NE (uspavan) |
| `shared/ai_fabric.py:309,320` | `anthropic.Anthropic` | `api.anthropic.com` | `ANTHROPIC_API_KEY` | **NE (mrtav kod)** |
| `shared/ai_fabric.py:365-382` | `google.generativeai` | `generativelanguage.googleapis.com` | `GEMINI_API_KEY` | **NE (mrtav kod)** |
| `routers/knowledge_base.py:105-118` | Pinecone SDK | Pinecone `kb_{uid}` | ne | DA |
| `interni_stavovi.py:81` | Pinecone SDK | Pinecone `interni_stavovi_{uid}` | ne | DA |
| `drafting/playbook.py:86` | Pinecone SDK | Pinecone `pb_{uid}` ns | ne | DA |
| `klijenti/router.py:811` | Supabase SDK | Supabase Storage `klijent-dokumenti` | ne | DA |
| `routers/client_portal.py:594` | Supabase SDK | Supabase Storage `portal-uploads` | ne | DA |
| `routers/smart_intake.py:187`, `api.py:5051`, `shared/intake_worker.py:480` | Supabase SDK | Supabase Storage `intake-dokumenti` | ne | DA |
| `api.py:39-49` | `sentry_sdk.init` | Sentry | `SENTRY_DSN` | samo ako DSN |
| `routers/billing.py:798` | `smtplib.SMTP` | `EMAIL_SMTP_HOST` | da | DA |
| `routers/email_notif.py:112` | `smtplib.SMTP` | `EMAIL_SMTP_HOST` | da | DA (cron) |
| `routers/morning_briefing.py:523` | `smtplib.SMTP` | `EMAIL_SMTP_HOST` | da | DA (ručno) |
| `routers/support.py:171` | `smtplib.SMTP` | `EMAIL_SMTP_HOST` | da | DA |
| `routers/waitlist.py:130` | `smtplib.SMTP` | `EMAIL_SMTP_HOST` | da | DA (javno) |
| `routers/sms.py:87` | Twilio SDK | Twilio API | `TWILIO_*` | DA (cron) |
| `routers/whatsapp_notif.py:97` | Twilio SDK | Twilio WhatsApp | `TWILIO_*` | DA |
| `routers/viber.py:44,71-99` | `httpx` | `https://chatapi.viber.com/pa` | `VIBER_AUTH_TOKEN` | DA |
| `routers/push.py:87` | `pywebpush` | browser push relay | `VAPID_*` | DA (samo test string) |
| `routers/integrations.py:334` | `httpx` | `https://oauth2.googleapis.com/token` | `GCAL_*` | DA |
| `routers/integrations.py:420` | `httpx` | `https://www.googleapis.com/calendar/v3/...` | `GCAL_*` | DA |
| `routers/sef.py:68-70,173` | `urllib.request` | `efaktura.mfin.gov.rs` | per-user API ključ | DA |
| `routers/apr.py:68,74` | `httpx` | `pretraga.apr.gov.rs` | ne | DA |
| `routers/portal_monitoring.py:86,100-109` | `httpx` | `portal.sud.rs` | ne | DA (cron) |
| `routers/wallet_provenance.py:45,90` | `httpx` | `api.etherscan.io` | `ETHERSCAN_API_KEY` | DA |
| `routers/zakon_monitoring.py:59,82` | `urlopen` | `pravno-informacioni-sistem.rs` RSS | ne | DA — **ULAZ, ne izlaz** |
| `routers/auto_discovery.py:254` | `urlopen` | URL iz `discovery_queue` reda | ne | DA — **ULAZ** |
| `shared/deps.py:140` | `urlopen` | Supabase JWKS | ne | DA — **ULAZ** |
| `routers/integracije.py:369-379` | `urllib.request` | korisnički webhook URL | ne | test-ruta ŽIVA, fire-putanja MRTVA |
| `routers/integrations.py:229-238` | `httpx` | korisnički webhook URL | ne | test-ruta ŽIVA, fire-putanja MRTVA |

### 1.3 Frontend egress (pretraživač → treća strana)

Servirane žive stranice: `index.html` (`api.py:2554`), `client_portal.html` (`api.py:2559`), `privacy.html` (`api.py:1634`), `terms.html` (`api.py:1667`), `site/*.html` (`api.py:1545-1628`), `/static` (`api.py:817`), `/word_addin` (`api.py:826-831`).

| Fajl:linija | Host | SRI? | Šta odlazi |
|---|---|---|---|
| `index.html:26-30` | `cdn.jsdelivr.net` (EmailJS) | **DA** | ništa — biblioteka učitana ali **uspavana**: ključ je placeholder `'VAŠ_PUBLIC_KEY'` (`static/vindex.js:1062-1066`), `emailjs.send()` nema nijedno pozivno mesto |
| `index.html:32-36,37-41` | `cdnjs.cloudflare.com` (html2pdf, html2canvas) | **DA** | ništa nakon učitavanja |
| `index.html:42-46` | `cdnjs.cloudflare.com` (Font Awesome) | **DA** | — |
| `index.html:47-51` | `unpkg.com` (lucide) | **DA** | — |
| `index.html:52-56` | `cdn.jsdelivr.net` (chart.js) | **DA** | — |
| `index.html:15` + svih 9 `site/*.html` | `fonts.googleapis.com` → `fonts.gstatic.com` | **NE** (nemoguće — dinamičan CSS po UA) | UA + `Accept-Language` |
| `static/vindex.js:242` | `czsxymueizfqrbbgqqob.supabase.co` | N/A | **lozinke pri prijavi, sesijski tokeni, reset-email, izmene profila** — direktno iz pretraživača, mimo FastAPI backend-a |
| `integrations/word_addin/taskpane.html:20`, `commands.html:14` | `appsforoffice.microsoft.com` | **NE** | Office.js runtime; stranica čita sadržaj Word dokumenta |

**CSP** (`api.py:1149-1161`) — `connect-src` dozvoljava `https://api.openai.com` i `https://api.emailjs.com`, ali NIJEDAN klijentski kod ih ne koristi (grep `api.openai.com` po `static/*.js` i `*.html`: 0 pogodaka). Dozvola je šira od upotrebe. `script-src` NE sadrži `appsforoffice.microsoft.com`, a middleware nema izuzetak za `/word_addin/*` — Word add-in i CSP su u međusobnoj kontradikciji. `'unsafe-inline'` u `script-src` ozbiljno umanjuje vrednost CSP-a kao anti-XSS mere.

`security/compute_sri.py` je ručna offline alatka bez ijednog uvoznika (`grep compute_sri *.py` → samo self-reference); ne postoji automatska provera da `integrity=` heševi u `index.html` i dalje odgovaraju živom CDN sadržaju.

### 1.4 Testovi i skripte — evidentirano, NE meša se sa produkcijom

- `scripts/scrape_*.py` (24 fajla), `data/sudska_praksa/scraper_phase10.py`, `vindex_scraper_output/scraper.py`, root-level `scrape_*.py`, `diag_*.py`, `ingest_*.py` — `httpx`/`requests` ka javnim srpskim pravnim izvorima. **Šalju upite, ne klijentske podatke.**
- `tests/` — `tests/test_network_guard.py:24,37` dokazuje da testovi imaju mrežni guard; `tests/prod_db_guard.py` fizički odvaja produkcijsku bazu.
- `.github/workflows/email-cron.yml:13` i `sms-cron.yml:13` — `curl` ka `https://vindex.rs/...` (sopstvena infrastruktura), nose `CRON_TOKEN`. **`CRON_TOKEN` NIJE u `.env.example`.**

---

## 2. KORAK 2 — BYPASS ANALIZA

### 2.1 Šta chokepoint zaista pokriva (i zašto 91 poziv NIJE bypass)

`shared/ai_client.py::_patch_prompt_guard()` (def `:566`) zamenjuje metode NA SAMIM SDK KLASAMA:

- `Completions.create` / `AsyncCompletions.create` — `shared/ai_client.py:808-809`
- `Embeddings.create` / `AsyncEmbeddings.create` — `:863-864`
- `Transcriptions.create` / `AsyncTranscriptions.create` / `Speech.create` / `AsyncSpeech.create` — `:923-926`

Instaliran je na uvozu modula `api.py`, pre svih router uvoza: `api.py:26-28`.

Posledica: `client.chat.completions.create(...)` iz BILO KOG fajla prolazi kroz wrapper, jer je zamenjena metoda klase, a ne pozivno mesto. **Zato nijedno od 91 SDK pozivnih mesta nije bypass.**

Azure redirekcija (`shared/ai_client.py:200-248`) zamenjuje samo KONSTRUKTOR (`openai.OpenAI` → `AzureOpenAI`); resursne klase ostaju iste patch-ovane klase. **Azure takođe NIJE bypass** — samo menja destinaciju (EU rezidentnost) unutar istog guard-a.

### 2.2 STVARNI BYPASS-EVI — tačno 3

#### BYPASS-1 — Raw WebSocket ka OpenAI Realtime · **ŽIV**

`services/voice_orchestrator.py:47` (`_REALTIME_URL = "wss://api.openai.com/v1/realtime"`), veza se otvara na `:531-538` preko `websockets.connect`.

- **Zašto zaobilazi:** ne koristi `openai` SDK uopšte, pa ga patch fizički ne vidi. Repo to sam priznaje: `security/response_firewall.py:29-30`.
- **Šta odlazi:** živi audio stream advokatskog razgovora + Whisper transkripcija (`services/voice_orchestrator.py:358`) + sistemske instrukcije (`:50-57`) + rezultati alata iz `shared/voice_tools.py`. **DA — može sadržati pun tekst dokumenta**, jer alat `pretraga_prakse_i_zakona` vraća isečke u istu sesiju.
- **Šta NE prolazi:** `security/prompt_guard.py` (ulazna sanitizacija) i `security/response_firewall.py` (izlazna kontrola).
- **Šta IMA sopstveno:** tvrda entitlement kapija sa contextvar tokenom koji se ne može konstruisati spolja (`:99-160`), fail-closed odbijanje bez governance odluke (`:140-160`), provenance upis sa `model_provider="openai-realtime-raw-wss"` (`:274-276`), i — bitno — **JESTE postavljen korisnički kontekst** (`:239` `_prov.set_request_context(user_id=uid, ...)`).
- **Gejt:** `VINDEX_VOICE_KILL` (`:73`) + tarifna provera. Odbija se pod Azure/EU konfiguracijom (`:516-527`).
- **Ruter:** `routers/voice_realtime.py:140`, registrovan `api.py:734`.

#### BYPASS-2 — Cohere rerank · **USPAVAN**

`app/services/retrieve.py:560` (`_cohere_lib.Client(api_key)`).

- **Zašto zaobilazi:** drugi SDK; patch se kači na OpenAI klase.
- **Šta bi odlazilo:** korisnikov upit + do 1000 znakova po isečku dokumenta/sudske prakse (`app/services/retrieve.py:517-519`).
- **Zašto je uspavan — TRI nezavisna uslova** (`_cohere_dozvoljen()`, `:532-549`): (1) paket `cohere` instaliran — **NIJE u `requirements.txt`** (proveren ceo fajl); (2) `COHERE_API_KEY` neprazan; (3) `VINDEX_COHERE_RERANK` eksplicitno uključen. Default: ISKLJUČENO. Fallback je `_gpt_rerank`, upravljan poziv.
- **Ako se ikad uključi:** ima sopstveni provenance upis u istu `ai_forensics` tabelu (`:601-619`) i strukturisan `logger.warning` koji radi i kad baza padne (`:593-599`). Ali **ne prolazi kroz prompt_guard ni response_firewall.**
- `COHERE_API_KEY` JESTE u `.env.example:20` — samo ključ nije dovoljan, opt-in je i dalje potreban (dokumentovano na `.env.example:137`).

#### BYPASS-3 — Anthropic + Gemini adapteri u AI Fabric-u · **MRTAV KOD**

`shared/ai_fabric.py:287-339` (Anthropic, `client.messages.create` na `:320`) i `:344-400` (Gemini, `gm.generate_content` na `:378`).

- **Zašto zaobilazi:** potpuno drugi SDK-ovi.
- **Dokaz da je mrtav:** `get_gateway()` / `AIRequest` / `ai_fabric` imaju pogodke u tačno 4 fajla — `shared/ai_fabric.py` (sam sebe), `tests/test_ai_fabric_governance.py`, `tests/test_ai_fabric_contract.py`, i `shared/audit_immutable.py:211` (samo string `"ai_fabric_call"` u listi dozvoljenih akcija). **Nijedan ruter ni servis ga ne poziva.** `ANTHROPIC_API_KEY` i `GEMINI_API_KEY` NISU u `.env.example`; `anthropic` i `google-generativeai` NISU u `requirements.txt`.
- **Šta ima:** provider-neutralnu ulaznu kapiju `_govern_request()` (`:508-539`) koja poziva `security.prompt_guard.sanitize_prompt` — ali sa `except ImportError: pass` (`:537-538`), dakle fail-OPEN ako guard nedostaje.
- **Šta nema:** `response_firewall` i upis u `ai_forensics`. Audit ide u `audit_immutable` bez sadržaja (`:640-660`).
- **Latentni rizik za budućnost:** `AI_FABRIC_SHADOW_PROVIDER` (`:582`) — ako se ikad postavi, SVAKI prompt se duplo šalje i drugom provajderu (`_run_shadow`, `:587-603`), a ishod se tiho odbacuje (`except Exception: logger.info`). To je „tihi dupli egress" ugrađen u dizajn.

### 2.3 Provereno i ODBAČENO kao bypass

- Svih 91 OpenAI SDK pozivnih mesta — pokriveni class patch-om (§2.1).
- Azure OpenAI — ista patch-ovana klasa.
- `boto3` / S3 — **nema ga nigde** u repou.
- Sirov HTTP POST na `api.openai.com` iz `requests`/`httpx` — **ne postoji**; jedini pogodci na taj host su `api.py:1155` (CSP tekst), `services/voice_orchestrator.py:9,47,505` (WSS + komentari), i test fajlovi.
- `vindex_web3/web3_adapter.py` — `aiohttp` uvoz postoji, ali jedini RPC URL je docstring primer (`web3_integracija/web3_adapter.py:92`, `"https://mainnet.infura.io/v3/KEY"` — literal placeholder).

---

## 3. KORAK 3 — POZADINSKI POSLOVI (§7)

### 3.1 Popis

| # | Lokacija | Šta radi | Korisnički kontekst | Živ |
|---|---|---|---|---|
| 1 | `api.py:849` `@app.on_event("startup")` | Pokreće 2 trajne petlje; drenira ih na `shutdown` (`api.py:864-888`) | N/A (bootstrap) | DA |
| 2 | `shared/intake_worker.py:69` `asyncio.create_task(self._run())` | Beskonačna petlja: preuzima `intake_jobs`, OCR, pa **AI klasifikacija** (`shared/intake_classify.py:30`) i **AI ekstrakcija** (`shared/intake_extract.py:34`) | **NEMA** — grep `set_request_context`/`case_context`/`user_id` po `shared/intake_worker.py`: **0 pogodaka**, iako `intake_jobs.uploaded_by` postoji i jeste `NOT NULL` (`migrations/073_intake_foundations.sql:78`) | DA |
| 3 | `services/event_bus.py:785` | Durable outbox dispečer; **nema AI pozive** | N/A | DA |
| 4 | `workers/background_agents.py:201` `run_background_agents()` iz cron dispečera | Fan-out po korisnicima, `asyncio.gather` (`:273-278`) | `user_id` JESTE Python argument (`:249`) | DA |
| 5 | `services/agent_tasks/precedents_radar.py:47-62` | **AI poziv** (`client.chat.completions.create`) — klasifikuje da li nova odluka podržava teoriju predmeta | `user_id` je argument `run()` (`:99`), ali se **nikad ne prosleđuje** u `ai_provenance` (0 pogodaka za `case_context`/`set_request_context`) | DA |
| 6 | `services/agent_tasks/court_portal_watcher.py:82-88` → `drafting/router.py:465` → `:80` | **AI poziv** — generisanje nacrta na promenu statusa | `user_id` putuje kao parametar, ali `drafting/router.py` nikad ne zove `case_context`/`set_request_context` | DA |
| 7 | `security/ai_forensics.py:171` `threading.Thread` | Sinhroni fallback za `log_ai_call_sync` | — | **MRTAV** — nema uvoznika (`:187-188`) |
| 8 | `shared/llm_retry.py:32` tenacity `@retry` | 3 pokušaja, eksponencijalni backoff, samo prolazne greške (`:45-47`) | nasleđuje kontekst pozivaoca | DA |
| 9 | `.github/workflows/email-cron.yml` 08:00, `sms-cron.yml` 07:00 | `curl` na sopstvenu infrastrukturu | server-side | DA |

`/api/cron/daily` (`api.py:1782`) autentifikuje se statičkim `X-Cron-Secret` (`api.py:1805`) i **nikad ne zove `get_current_user`**, pa `set_request_context` (jedina 4 poziva: `api.py:3734`, `api.py:3763`, `shared/deps.py:326`, `services/voice_orchestrator.py:239`) nikad ne odradi za ovaj tok. Ambijentalni `_request_ctx` ostaje `{}`.

**Nije problem:** ~130 `asyncio.create_task` poziva unutar živog HTTP zahteva. `create_task` kopira tekući `contextvars.Context`, a `get_current_user` je već pozvao `set_request_context(user_id=...)` (`shared/deps.py:326`). Dokaz i po direktnom prosleđivanju: `routers/web3.py:66`, `api.py:3364`.

### 3.2 Potvrđen `ai_forensics.user_id NOT NULL` problem

**(a) Šema:** `migrations/043_security_bulletproof.sql:82` — `user_id UUID NOT NULL,` bez default-a. RLS na `:105-107` takođe pretpostavlja ne-NULL.

**(b) Upis:** `security/ai_forensics.py:374`:
```
safe = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in record.items() if v is not None}
```
Kad je `user_id` `None`, kolona se **potpuno izbacuje iz dict-a** (ne šalje se ni kao `NULL`). INSERT tada pada na not-null violation (23502). `_is_missing_column_error` (`shared/audit_immutable.py:329-337`) matchuje samo `42703`/`does not exist`, vraća `False`, izuzetak se re-raise-uje i završava u `except Exception as e:` na `:412` gde se SAMO loguje: `logger.error("[FORENSICS] provenance NIJE upisan — trag je izgubljen: %s", e)` (`:415`).

`user_id` dolazi **isključivo iz contextvar-a**, nikad kao argument: `shared/ai_client.py:454` i `:513` — `user_id=ctx.get("user_id")`.

**Da li obara AI poziv? NE.** `log_provenance_from_wrapper` se izvršava kao odvojen task preko `shared/bg.py::spawn()` (`shared/ai_client.py:474-475`, `:528-529`), i to TEK POSLE povratka od provajdera. Korisnik dobija odgovor; **gubi se samo forenzički trag.**

**(c) Pogođeni pozadinski putevi — 3, svi ŽIVI:**
1. `shared/intake_worker.py` petlja → `shared/intake_classify.py:30` + `shared/intake_extract.py:34`. Radi neprekidno, za svaki intake job svakog korisnika.
2. `services/agent_tasks/precedents_radar.py:51` (dnevni cron fan-out).
3. `services/agent_tasks/court_portal_watcher.py:82` → `drafting/router.py:80` (isti cron).

**Neto efekat: podaci klijenta ODLAZE OpenAI-ju, a red koji to dokazuje se ne upisuje.** Za `intake` to znači da AI obrada upravo uploadovanog klijentskog dokumenta nema forenzički trag.

**UNKNOWN:** da li `routers/workflow.py::_check_escalations` i `routers/zakon_monitoring.py::_skeniraj_sl_glasnik` (takođe cron-daily) prave AI pozive — nije dokazano.

### 3.3 Cron rute bez dokazanog pokretača

Postoje i dostupne su, ali nisu vezane ni za `api.py::cron_daily` ni za ijedan `.yml` u repou. Mogu ih zvati samo ručno ili spoljni raspoređivač van repoa (`cron-job.org` se pominje u docstring-ovima, ali konfiguracija nije u repou → **UNKNOWN**):
`routers/morning_briefing.py:604`, `:886`; `routers/whatsapp_notif.py:348`; `routers/viber.py:340`.

---

## 4. KORAK 4 — INVENTORY

Legenda: **PUN DOK.** = može li primiti pun tekst dokumenta · **GRANICA** = tenant boundary · **KONTROLA** = koliko Vindex stvarno kontroliše · **DEFAULT** = uključeno bez konfiguracije

### 4.1 AI provajderi

| PROVIDER | ŠTA SE ŠALJE | PUN DOK. | PII | IDENTIFIKATORI | RETENCIJA | TRENING | ENKRIPCIJA | GRANICA | BRISANJE | KONTROLA | DEFAULT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **OpenAI Chat** (91 mesta) | promptovi, pun tekst dokumenta (`main.py:3708`), činjenice predmeta | **DA** | DA — maskiranje samo na 4 fajla (§4.4) | `user_id`/`predmet_id` se NE šalju provajderu | **UNKNOWN — nema `store=False`** | UNKNOWN (politika provajdera) | TLS u tranzitu | **nema** — jedan API ključ za sve klijente | **nema** | ulaz: prompt_guard; izlaz: response_firewall | **DA** |
| **OpenAI Embeddings** | tekst chunk-ova pre vektorizacije | DA | DA | — | UNKNOWN | UNKNOWN | TLS | nema | nema | isti guard | DA |
| **OpenAI Whisper STT** (`routers/voice.py:45`) | audio snimak | audio | **DA — glas je biometrija** | — | UNKNOWN | UNKNOWN | TLS | nema | nema | guard (`Transcriptions.create`) | DA |
| **OpenAI TTS** (`routers/voice.py:52`) | tekst za izgovor | delimično | DA | — | UNKNOWN | UNKNOWN | TLS | nema | nema | guard (`Speech.create`) | DA |
| **OpenAI Realtime WSS** | živi audio + transkript + rezultati alata | **DA** | **DA — privilegovani razgovor** | `user_id` u provenance-u, ne provajderu | UNKNOWN | UNKNOWN | WSS | nema | nema | **BYPASS-1** — ima entitlement + provenance, nema prompt_guard/firewall | iza `VINDEX_VOICE_KILL` + tarife |
| **Azure OpenAI** | isto kao OpenAI | DA | DA | — | ugovorno (EU) | Azure ne trenira | TLS | nema | nema | isti guard | NE (`AZURE_OPENAI_KEY`+`ENDPOINT`) |
| **Cohere** | upit + ≤1000 zn./isečak | delimično | DA | — | UNKNOWN | UNKNOWN | TLS | nema | nema | **BYPASS-2**, uspavan; ima provenance | **NE** — 3 gejta |
| **Anthropic** | prompt + `case_context` | DA | DA | `user_id` samo u auditu | — | — | TLS | nema | nema | **BYPASS-3**, mrtav | **NE** — nema ni ključ ni paket |
| **Gemini** | isto | DA | DA | — | — | — | TLS | nema | nema | **BYPASS-3**, mrtav | **NE** |

### 4.2 Infrastruktura podataka

| PROVIDER | ŠTA SE ŠALJE | PUN DOK. | PII | IDENTIFIKATORI | RETENCIJA | ENKRIPCIJA | GRANICA | BRISANJE | KONTROLA | DEFAULT |
|---|---|---|---|---|---|---|---|---|---|---|
| **Pinecone** | vektori **+ PLAINTEXT metapodaci**: `sadrzaj[:1000]` (`routers/knowledge_base.py:112`), pun chunk `"text": chunk` (`interni_stavovi.py:74`, `drafting/playbook.py:80`) | **DA — u komadima** | **DA** | **`user_id` se UPISUJE u metadata** (`knowledge_base.py:115`, `interni_stavovi.py:71`, `playbook.py:77`) | do brisanja | TLS; **sadržaj NIJE enkriptovan** | **namespace po korisniku** (`kb_{uid}`, `interni_stavovi_{uid}`, `pb_{uid}`) — logička, ne kriptografska | `index.delete(namespace=...)` (`playbook.py:123`, `interni_stavovi.py:125`) | pun (SDK, sopstveni ključ) | **DA** |
| **Supabase Postgres** | svi aplikativni podaci; JMBG/pasoš/PIB polja enkriptovana (`security/crypto.py`) | metapodaci | DA | user_id, predmet_id | do brisanja | AES-256-GCM na nivou polja + at-rest kod provajdera | RLS + `user_id` kolone | GDPR rute (`routers/gdpr.py`) | pun | **DA** |
| **Supabase Storage** | **ŠIFROVANI blob** — AES-256-GCM PRE upload-a (`klijenti/router.py:794-806`); ime fajla enkriptovano (`:820`); putanja randomizovana (`generate_storage_key()`) | ciphertext | ne u čitljivom obliku | randomizovan UUID ključ | do brisanja | **AES-256-GCM aplikativno** — provajder vidi samo šifrat | bucket + putanja | `storage.remove()` (`routers/client_portal.py:779`) | **pun — najjača kontrola u sistemu** | **DA** |
| **Supabase Auth (pretraživač)** | **lozinke, sesijski tokeni, reset-email, izmene profila** — direktno browser→Supabase, mimo backend-a (`static/vindex.js:242`) | ne | **DA** | email | provajder | TLS | po projektu | — | delegirano | **DA** |

### 4.3 Ostalo

| PROVIDER | ŠTA SE ŠALJE | PUN DOK. | PII | RETENCIJA | GRANICA | KONTROLA | DEFAULT |
|---|---|---|---|---|---|---|---|
| **Sentry** | izuzetak + stack trace, `attach_stacktrace=True` (`api.py:48`) | **UNKNOWN — v. §4.5** | `send_default_pii=False` (`:47`), ali **nema `before_send`** | provajder | po projektu | delimična | **NE** (`SENTRY_DSN`) |
| **SMTP** | **PUN PDF fakture** (`routers/billing.py`), nazivi rokova/sudova/predmeta, iznosi; support: **korisnički tekst + screenshot** | fakture: DA | DA | mail server | primalac | pun (sopstveni server) | NE |
| **Twilio SMS** | telefon + naziv roka + datum | NE | DA | Twilio | — | ograničena | NE |
| **Twilio WhatsApp** | telefon + **naziv predmeta** + rok | NE | DA | Twilio + Meta | — | ograničena | NE |
| **Viber** (`chatapi.viber.com`) | Viber ID + nazivi sudova/rokova/broj predmeta | NE | DA | Viber/Rakuten | — | ograničena | NE |
| **Web Push** | **samo fiksni test string** `"Push notifikacije rade ispravno ✓"` (`routers/push.py:92-96`) — jedini pozivalac | NE | ne | relay | — | — | NE |
| **Google Calendar** | naziv roka + **slobodan tekst `opis`** (`routers/integrations.py:411`) + datum | NE | DA | Google | korisnikov kalendar | ograničena | NE |
| **Google OAuth** | auth code + client secret | NE | ne | Google | — | — | NE |
| **SEF** (`efaktura.mfin.gov.rs`) | **pun UBL 2.1 XML**: ime klijenta, PIB, adresa, stavke, iznosi | faktura: DA | **DA** | državni registar (zakonski obavezno) | per-user API ključ | zakonski zahtev | NE |
| **APR** (`pretraga.apr.gov.rs`) | samo `maticni_broj` | NE | ne | — | — | — | DA (javni API) |
| **portal.sud.rs** | **`brPredmeta` + naziv suda** (`routers/portal_monitoring.py:103`) | NE | **DA — identifikuje predmet** | javni portal | — | nikakva | DA |
| **Etherscan** | wallet adresa | NE | pseudonimna | — | — | ograničena | NE |
| **Sl. Glasnik RSS** | ništa — GET | — | — | — | — | — | DA (**ULAZ**) |
| **cdnjs / jsdelivr / unpkg** | HTTP zahtev pretraživača (IP, UA, Referer) | NE | IP | CDN logovi | — | **SRI prisutan** | DA |
| **fonts.googleapis / gstatic** | IP, UA, `Accept-Language` | NE | IP | Google logovi | — | **bez SRI** (nemoguć) | DA |
| **appsforoffice.microsoft.com** | zahtev pretraživača | NE | IP | MS logovi | — | **bez SRI**, i **nije u CSP `script-src`** | samo Word add-in |
| **Korisnički webhook-ovi** | trenutno **ništa** — oba `trigger_webhook` imaju 0 pozivalaca | — | — | — | — | v. §4.6 | NE |

### 4.4 OpenAI — retencija i pseudonimizacija (KORAK 4, izričito)

**Nema `store=False` nigde u repou.** Nema zero-data-retention endpoint-a. Nema `OpenAI-Organization` ni `OpenAI-Project` zaglavlja. Nema `OPENAI_ORG`/`OPENAI_PROJECT` env varijabli. Provereno nad celim `git ls-files "*.py"` skupom — **0 pogodaka za sve tri kategorije.**

**Posledica: retencija podataka kod OpenAI-ja zavisi 100% od politike provajdera i od podešavanja na OpenAI nalogu (van koda). Kod ne pruža nijednu tehničku garanciju.** Jedina tehnička poluga u repou je Azure redirekcija (`shared/ai_client.py:200-248`), koja NIJE uključena po defaultu.

**Pseudonimizacija** — `main.py:1076` `_skini_pii()`, 13 regex obrazaca (`_PII_ZAMENE`, `main.py:1048-1073`): JMBG, PIB, MB, LK, pasoš, telefon, IBAN, tekući račun, broj sudskog predmeta, email, adresa.

Dva ograničenja koja treba imenovati:
1. **Ne maskira LIČNA IMENA.** Nijedan obrazac ne pokriva ime i prezime.
2. **Primenjuje se u samo 4 fajla** od ~50 sa AI pozivima: `main.py`, `api.py`, `routers/drafting.py`, `routers/oblasti.py`. Putevi kao `routers/court_predictor.py` (7 poziva), `routers/case_dna.py`, `routers/knowledge_base.py`, `shared/intake_classify.py`, `shared/intake_extract.py` šalju sadržaj **bez maskiranja**.

### 4.5 Sentry — nedokazana površina

`api.py:39-49`: `send_default_pii=False`, `traces_sample_rate=0.05`, `attach_stacktrace=True`. **`before_send` nije definisan nigde u repou** (0 pogodaka). Nema `set_user`/`set_context`/`capture_message` poziva.

`send_default_pii=False` suzbija automatsko kačenje IP/korisnika/kolačića — **ali ne isključuje lokalne promenljive u okvirima stack trace-a.** `include_local_variables` nije eksplicitno postavljen na `False`. Ako izuzetak nastane u okviru koji drži tekst dokumenta ili prompt u lokalnoj promenljivoj, taj sadržaj može otići Sentry-ju.

**Ovo je UNKNOWN — nije dokazivo statičkim čitanjem** i traži ili runtime test ili eksplicitno `include_local_variables=False`. Ublažavajuća okolnost: cela putanja je mrtva bez `SENTRY_DSN` (`api.py:33-34`), koji je prazan u `.env.example:63`.

### 4.6 Webhook-ovi — SSRF, ali (još) ne curenje podataka

Dva paralelna sistema, oba sa **0 pozivalaca** za slanje događaja (samodokumentovano `routers/integracije.py:20-27` i potvrđeno grep-om) — dakle registrovani webhook nikad ne dobije podatke o predmetu.

Ali TEST rute su žive i asimetrično zaštićene:

- `routers/integrations.py:196` (`webhooks` tabela) — **JESTE zaštićen**: `_validiraj_webhook_url` (`:165-194`) traži `https`, port 443, i odbija privatne/loopback/link-local/reserved IP-jeve; provera se ponavlja i pri slanju zbog DNS rebinding-a (`:226`); telo odgovora se NE vraća pozivaocu (`:239-241`).
- `routers/integracije.py:481` (`user_webhooks` tabela) — **NIJE zaštićen**: `WebhookReq.url` je običan `str` sa `min_length=10` (`:363`), `webhook_registruj` (`:409`) ne poziva nijednu validaciju, a `_slanje_webhook_sync` (`:369-379`) radi `urllib.request.urlopen` na proizvoljan URL. **Nema https zahteva, nema IP filtera.**

Posledica: autentifikovan korisnik može naterati server da POST-uje na internu adresu. Telo odgovora se ne reflektuje (vraća se samo `{"success", "url", "timestamp"}`), a payload je fiksan test string — dakle **slepi SSRF, ne egress klijentskih podataka.** Rizik postaje ozbiljan onog dana kad se `trigger_webhook` poveže na stvarnog pozivaoca.

---

## 5. KORAK 5 — NEGATIVNE KONTROLE (§9)

Cilj: dokazati da detektor VIDI žive kanonske tokove i da ih ne proglašava bypass-om.

### NK-1 — Kanonski enkriptovan upload · PROŠAO
`klijenti/router.py:783-819`. Bajtovi se čitaju (`:783`), enkriptuju AES-256-GCM sa nonce-om iz `os.urandom(12)` (`:798-802`), i tek onda šalju `bucket.upload()` (`:811`). Ime fajla se enkriptuje zasebno (`:820`), putanja je randomizovan UUID.
**Rezultat:** sweep ga NIJE označio kao bypass. Ispravno — nije AI put. Jeste uveden u inventar (§4.2) kao Supabase Storage, i to je jedini tok gde provajder ne vidi plaintext.

### NK-2 — Kanonski download dokumenta · PROŠAO
`klijenti/router.py:941-995`. Audit log PRE isporuke (`:941-948`), `bucket.download()` (`:962`), dekripcija (`:967-973`), PDF watermark sa email-om korisnika (`:982-987`), `StreamingResponse` (`:992`).
**Rezultat:** nije označen kao bypass. Ispravno.

### NK-3 — Kanonski AI poziv · PROŠAO
`app/services/retrieve.py:506` (`return client.chat.completions.create(**kwargs)`) i `main.py:2305`.
Dokaz pokrivenosti: `Completions.create` je zamenjena na klasi (`shared/ai_client.py:808`), patch instaliran na `api.py:28` pre svih router uvoza. Pozivno mesto nema izbora.
**Rezultat:** nije označen kao bypass. Ispravno — u istom modulu (`app/services/retrieve.py`) sweep JESTE prijavio Cohere granu kao bypass. Detektor razlikuje dve grane u istom fajlu, što je traženo razlučivanje.

### NK-4 — Kanonski retrieval · PROŠAO
`app/services/retrieve.py:901,916,930,946,1020` — `index.query(...)` nad namespace-ovima `zakoni_rs`/`misljenja`/`praksa`.
**Rezultat:** nije bypass. Uveden u inventar kao Pinecone (§4.2). Nije pobrkan sa tenant namespace-ovima (`kb_*`, `pb_*`, `interni_stavovi_*`), koji jesu zasebno prijavljeni jer nose plaintext klijentski sadržaj.

### NK-5 — Kontrola nad samim guard-om · PROŠAO
Sweep je našao 91 SDK pozivno mesto i proglasio ih ne-bypass-om NE po imenu fajla, nego po dokazu da je patch instaliran pre uvoza (`api.py:26-28`) i da menja klasu, ne pozivno mesto. Da patch nije instaliran, ista metoda bi svih 91 morala prijaviti.

### ISPRAVKA METODE — priznata slepa tačka

Prvi prolaz (samo sirovi mrežni primitivi) **NIJE video** NK-1, NK-2, NK-3 ni NK-4 — nijedan ne koristi `requests`/`httpx`/`urllib`/`websockets`. Da je izveštaj stao tu, Supabase Storage, Pinecone i svih 91 OpenAI poziv bili bi izostavljeni iz inventara, a §6 bi tvrdio da je egress površina znatno manja nego što jeste.

Metoda je zato dopunjena drugim prolazom nad SDK simbolima (§1.1). **Bez te ispravke inventar bi bio lažno umirujući.** Ovo se navodi jer §9 traži da se neuspeh metode prijavi, a ne zaokruži naviše.

---

## 6. ZAKLJUČAK

**Šta je dokazano dobro:** chokepoint na nivou SDK klasa stvarno pokriva svih 91 pozivno mesto i ne može se slučajno zaobići; enkripcija dokumenata pre Supabase Storage-a je stvarna i provajder vidi samo šifrat; sva tri bypass-a su ranije pronađena, imenovana u kodu i dva od tri su neutralisana (mrtav / trostruko zaključan); CDN skripte imaju SRI; SSRF je zatvoren na jednom od dva webhook sistema.

**Šta ostaje otvoreno — činjenice, bez ublažavanja:**

1. **Nema nijedne tehničke kontrole retencije kod OpenAI-ja.** Bez `store=False`, bez ZDR-a, bez org/project zaglavlja. Sve počiva na politici provajdera i podešavanjima naloga van koda.
2. **Tri živa pozadinska AI puta gube forenzički trag.** `intake_worker`, `precedents_radar`, `court_portal_watcher` — podaci odlaze, `ai_forensics` red pada na `user_id NOT NULL` i tiho se odbacuje.
3. **Pinecone dobija plaintext klijentski sadržaj**, ne samo vektore, sa `user_id` u metapodacima. Granica između klijenata je namespace — logička, ne kriptografska.
4. **Pseudonimizacija pokriva 4 od ~50 fajlova sa AI pozivima i ne maskira imena.**
5. **`routers/integracije.py` webhook test ruta nema SSRF validaciju** koju njen blizanac ima.
6. **Sentry `include_local_variables` nije isključen** — UNKNOWN da li sadržaj dokumenta može završiti u stack trace-u.
7. **`AI_FABRIC_SHADOW_PROVIDER`** je ugrađen mehanizam tihog duplog egressa; danas neaktivan jer je fabric mrtav.
8. **Word add-in i CSP su u kontradikciji** — `appsforoffice.microsoft.com` nije u `script-src`, a middleware nema izuzetak za `/word_addin/*`.
9. **`CRON_TOKEN` nije u `.env.example`** iako ga dva GitHub Actions workflow-a koriste.
