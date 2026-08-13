# EXTERNAL_BOUNDARY_002 — Granica podataka prema spolja

**Baseline:** `2a2e799c`
**Datum:** 2026-08-13
**Metod:** READ-ONLY forenzička analiza koda i toka podataka. Nijedan fajl nije izmenjen, nijedna migracija pokrenuta, nijedan podatak poslat spolja.

---

## §0. OGRANIČENJE KOJE OVAJ DOKUMENT POŠTUJE DOSLOVNO

Mandat §5 kaže: *„DO NOT infer provider policy from memory. This phase is code/data-flow analysis only."*

Zato ovaj dokument razdvaja **dve vrste tvrdnji** i nikad ih ne meša:

| Oznaka | Značenje |
|---|---|
| **DOKAZANO IZ KODA** | Pročitano je u repozitorijumu na navedenoj liniji. Tvrdnja o tome šta kod radi. |
| **UNKNOWN — zahteva zasebnu verifikaciju** | Tiče se politike provajdera (retencija, treniranje, logovanje, lokacija obrade), ugovora (DPA), ili stanja žive produkcione infrastrukture. Kod ovo ne može da dokaže. **§10 zabranjuje pretvaranje ovoga u zaključak.** |

Svako polje „retencija / treniranje / logovanje kod provajdera" u tabelama ispod je **UNKNOWN po konstrukciji**. To nije propust ovog izveštaja — to je granica onoga što analiza koda sme da tvrdi.

Jedino što ovaj dokument tvrdi o provajderima jeste **šta Vindex tehnički kontroliše ili ne kontroliše u svom kodu**.

---

## §1. NALAZ NAJVIŠEG PRIORITETA — TEHNIČKE KONTROLE KOJE NE POSTOJE

Pretraženo je celo `.py` stablo (produkcioni kod, bez `tests/`, `scripts/`, `diag_*`):

```
grep -rn "store\s*=\s*(True|False)"        →  0 pogodaka
grep -rn "extra_headers"                    →  0 pogodaka
grep -rn "default_headers"                  →  0 pogodaka
grep -rn "organization="                    →  0 pogodaka
grep -rn "OPENAI_ORG"                       →  0 pogodaka
grep -rn "base_url="                        →  0 pogodaka
```

| Kontrola | Postoji u kodu? | Dokaz |
|---|---|---|
| `store=False` na Chat Completions pozivima | **NE** | 0 pogodaka u celom repou |
| Zero-Data-Retention (ZDR) endpoint / zaglavlje | **NE** | 0 pogodaka |
| `OpenAI-Organization` / `project=` scoping | **NE** | 0 pogodaka; koristi se samo `OPENAI_API_KEY` |
| Custom `base_url` (npr. EU proxy) | **NE** | 0 pogodaka |
| Redakcija PII pre slanja LLM-u | **NE** | `security/prompt_guard.py` je **detektor prompt-injectiona**, ne redaktor. `analyze()` (`:177`) vraća `blocked` bool + `risk_score`; `sanitized` je „neizmenjen ugovor" (`:241`). Nijedno polje se ne maskira. |
| Azure OpenAI redirekcija (podaci u EU) | **KOD POSTOJI, AKTIVACIJA UNKNOWN** | `shared/ai_client.py:200-248`: aktivira se samo ako su `AZURE_OPENAI_KEY` **i** `AZURE_OPENAI_ENDPOINT` postavljeni. Da li jesu u produkciji — **UNKNOWN, zahteva proveru env-a.** |

**Posledica koja SE SME tvrditi iz koda:** svaki prompt koji Vindex šalje OpenAI-u odlazi bez ijedne aplikativne kontrole retencije. Šta OpenAI sa njim radi — **UNKNOWN — zahteva zasebnu verifikaciju (DPA / ZDR ugovor).**

---

## §2. ARHITEKTURA GRANICE — ŠTA JEDINI CHOKE-POINT JESTE, A ŠTA NIJE

`shared/ai_client.py::_patch_prompt_guard()` (pozvan u `api.py:27-28`, pre uvoza ijednog routera) menja metode **na SDK klasama**, ne na instancama:

```python
Completions.create      = _guarded_create        # :808
AsyncCompletions.create = _guarded_acreate       # :809
Embeddings.create       = _tracked_embed         # :863
AsyncEmbeddings.create  = _tracked_aembed        # :864
Transcriptions.create / Speech.create            # :923-926
```

**Posledica:** ~150 mesta u kodu koja konstruišu sirov `OpenAI()` / `AsyncOpenAI()` **NE zaobilaze** prompt guard, Response Firewall, provenance ni podrazumevani 60 s timeout. Pokrivenost je strukturna. To je stvarna, merljiva jačina ove arhitekture i mora se priznati.

### Ali choke-point pokriva manje nego što se čini

| Putanja | Prolazi kroz guard? | Dokaz |
|---|---|---|
| Chat Completions (sync + async) | **DA** — guard + firewall + provenance + timeout | `ai_client.py:711-800` |
| Embeddings | **DELIMIČNO** — provenance + timeout, **BEZ ulaznog guard-a i BEZ firewall-a, namerno** | `ai_client.py:825-841`; obrazloženje `:836-849` |
| Audio (Whisper STT / TTS) | **DELIMIČNO** — provenance + timeout, bez guard-a (ulaz su bajtovi) | `ai_client.py:890-926` |
| **Cohere rerank** | **NE** — sopstveni SDK, van patch-a | `app/services/retrieve.py:552-561`, `1359-1405` |
| **OpenAI Realtime preko sirovog WSS** | **NE** — `websockets`, ne SDK; bez guard-a, bez firewall-a, bez timeout-a | `services/voice_orchestrator.py:47` |
| **Anthropic / Gemini kroz `shared/ai_fabric.py`** | **NE** — ali je **MRTAV KOD**: nula produkcionih pozivalaca | `shared/ai_fabric.py:285-320`; grep nalazi samo sam fajl |

### Choke-point se može tiho degradirati

```python
# shared/ai_client.py:865-866
except Exception as exc:
    logger.warning("[AI_PROVENANCE] Embeddings provenance patch neuspešan (nije kritično): %s", exc)
```

Ako patch embeddings/audio klasa padne, `governance_status()` (`:943`) i dalje javlja `active: true`. Nijedan health check ne razlikuje „puna pokrivenost" od „samo chat". **Tehnička kontrola koja tvrdi da radi a ne radi.**

---

## §3. TABELA GRANICE — SVAKI ODLAZNI POZIV

Legenda kolona: **PT** = pun tekst dokumenta može da napusti Vindex · **ET** = izvučeni (ekstrahovani) tekst može · **TID/PID/DID/FN** = tenant_id / predmet_id / document_id / ime fajla napuštaju Vindex.

### 3.1 OpenAI — Chat Completions (`api.openai.com`)

| Polje | Nalaz |
|---|---|
| **Tačan izvor payload-a** | `messages` sastavljen na ~150 pozivnih mesta. Reprezentativna: `api.py:5608-5612` (`_call_procena` / `_call_hronologija` / `_call_metapodaci` nad izvučenim tekstom dokumenta), `routers/case_dna.py:222` (`f"Dokumenti predmeta ({n}):\n\n{combined}"`), `main.py:3385-3388` (RAG odgovor + dohvaćeni chunk-ovi) |
| **PT — pun tekst dokumenta** | **DA.** Nema globalnog limita. Pojedina mesta seku (`case_intelligence.py:46` `[:10000]`, `cio.py:228` `[:14000]`, `client_twin.py:144` `[:8000]`), ali `case_dna.py:222` šalje `combined` bez reza. Prompt guard seče na `MAX_INPUT_CHARS = 60_000` **samo za analizu**, ne za slanje. |
| **ET — izvučeni tekst** | **DA** — to je primarni sadržaj |
| **Metapodaci** | naziv predmeta, tip spora, imena stranaka, hronologija, iznosi — sve u telu prompta |
| **tenant_id / predmet_id / document_id / ime fajla** | Ne kao strukturisana polja API-ja (nema `metadata=`), **ali se pojavljuju u telu prompta** gde ih pozivalac ubaci (npr. `case_commander.py:406` `f"Predmet:\n\n{predmet_tekst}"`) |
| **Granica enkripcije** | TLS u tranzitu. **Payload je plaintext na strani provajdera.** Nema aplikativne enkripcije. |
| **Zavisnost od retencije** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Skladištenje kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Treniranje** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Logovanje kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Mehanizam brisanja kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju.** Kod ne poziva nijedan provider-side delete API. |
| **POSTOJEĆA tehnička kontrola Vindexa** | ✔ prompt-injection guard (`security/prompt_guard.py`) ✔ Response Firewall (`security/response_firewall.py`) ✔ provenance red u `ai_forensics` (samo heševi) ✔ 60 s timeout ✔ fail-closed AI kill-switch ako guard ne uspe da se instalira (`ai_client.py:124-181`) — **✘ store=False ✘ ZDR ✘ org/project scoping ✘ PII redakcija ✘ limit dužine payload-a** |

### 3.2 OpenAI — Embeddings (`api.openai.com`)

| Polje | Nalaz |
|---|---|
| **Tačan izvor** | `uploaded_doc/ingest.py:75` — `texts = [c.text for c in manifest.chunks]`; `routers/law_upload.py:84`; `app/services/retrieve.py:484-488` (upit korisnika) |
| **PT** | **DA — u chunk-ovima koji pokrivaju ceo dokument.** Model `text-embedding-3-large`, 3072-d |
| **ET** | DA |
| **tenant/predmet/document/ime fajla** | **NE** — embeddings API prima samo listu stringova |
| **Granica enkripcije** | TLS u tranzitu; plaintext kod provajdera |
| **Retencija / treniranje / logovanje / brisanje** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **POSTOJEĆA kontrola** | ✔ provenance ✔ 60 s timeout ✔ odbijanje delimičnog odgovora (`ingest.py:88-92`) — **✘ ulazni guard NAMERNO isključen** (`ai_client.py:836-849`: pravni podnesci prirodno sadrže citirane naredbe, false-positive bi trajno ne-indeksirao dokaz) **✘ store=False ✘ ZDR** |

### 3.3 OpenAI — Audio: Whisper STT i TTS

| Polje | Nalaz |
|---|---|
| **Tačan izvor** | `routers/voice.py:445+` — sirovi audio bajtovi koje korisnik snimi/otpremi (≤10 MB, `voice.py:418`) |
| **PT/ET** | **DA — govorni sadržaj advokata/klijenta u sirovom obliku** |
| **Metapodaci** | ime fajla se prepisuje iz `content_type` (`voice.py:421-431`), pa originalno ime NE odlazi |
| **Retencija / treniranje / logovanje / brisanje** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **POSTOJEĆA kontrola** | ✔ provenance + timeout (dodato S2-1, `ai_client.py:890-926`) ✔ `PermissionService.require("voice")` — **✘ guard nije primenljiv na bajtove ✘ transkript se NE proverava firewall-om** |

### 3.4 OpenAI Realtime — sirov WebSocket (`wss://api.openai.com/v1/realtime`)

| Polje | Nalaz |
|---|---|
| **Tačan izvor** | `services/voice_orchestrator.py` — dvosmerni relej: audio browsera ↔ OpenAI; `input_audio_transcription: {"model": "whisper-1"}` (`:358`); model `gpt-4o-realtime-preview` (`:48`) |
| **PT/ET** | **DA — uživo, kontinuirano, uključujući sve što se izgovori u kancelariji dok je sesija otvorena** |
| **Granica enkripcije** | WSS u tranzitu |
| **Retencija / treniranje / logovanje / brisanje** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **POSTOJEĆA kontrola** | ✔ fail-closed autorizacija sesije (`voice_orchestrator.py:168` `proveri_voice_dozvolu`) ✔ eksplicitna odluka korisnika pre otvaranja (`:135-163`) ✔ jedan provenance red po sesiji (`:245-276`) ✔ human-in-the-loop potvrda za function-call (`:425-458`) — **✘ BEZ prompt guard-a ✘ BEZ Response Firewall-a ✘ BEZ timeout-a ✘ BEZ per-poruka provenance-a.** Kod sam ovo priznaje (`ai_client.py:664-666`). |

### 3.5 Cohere Rerank (`api.cohere.com`) — PODRAZUMEVANO ISKLJUČENO

| Polje | Nalaz |
|---|---|
| **Tačan izvor** | `app/services/retrieve.py:1359-1405` — upit korisnika + tekst dohvaćenih chunk-ova (uključujući chunk-ove iz `kancelarija_*` namespace-a, tj. **dokumenata predmeta**) |
| **PT** | Ne pun dokument; **DA za dohvaćene chunk-ove** (do 1000 znakova po dokumentu) |
| **Aktivacija** | Traži SVA TRI uslova: paket instaliran **I** `COHERE_API_KEY` **I** `VINDEX_COHERE_RERANK` eksplicitno uključen (`:532-549`). Da li je uključen u produkciji — **UNKNOWN, zahteva proveru env-a.** |
| **Retencija / treniranje / logovanje / brisanje** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **POSTOJEĆA kontrola** | ✔ trostruki opt-in (namerno teško slučajno uključiti) ✔ ručni provenance u istu `ai_forensics` tabelu (`:564-628`), upit se beleži kao SHA-256, dokumenti samo kao broj ✔ deterministički fallback na `_gpt_rerank` — **✘ van SDK patch-a: bez prompt guard-a, bez firewall-a** |

### 3.6 Pinecone (`*.pinecone.io`) — NAJVEĆI TRAJNI IZLAZ SADRŽAJA

| Polje | Nalaz |
|---|---|
| **Tačan izvor payload-a** | `uploaded_doc/ingest.py:150-171` |
| **PT — pun tekst** | **DA, I TRAJNO SE SKLADIŠTI KOD PROVAJDERA.** `_TEXT_TRUNCATE = 40_000` (`:12`); metadata polje `"text": chunk.text[:40000]` (`:159`). Chunk-ovi pokrivaju ceo dokument → **ceo tekst dokumenta živi u Pinecone metapodacima.** Isto: `law_upload.py:140`, `interni_stavovi.py:82`, `batch_ingest.py:96`, `auto_discovery.py:203`, `knowledge_base.py:112` |
| **ET** | DA |
| **Ime fajla** | **DA, u čistom tekstu** — `"source_filename": manifest.source_filename` (`ingest.py:155`) |
| **tenant_id (kancelarija_id)** | **DA** — `extra_metadata` (`api.py:5219`) |
| **predmet_id** | **DA** — `api.py:5218` + `metapodaci_identiteta` (`ingest.py:167-170`) |
| **document_id** | **DA** — `vx_document_id` |
| **Dodatno** | `session_id`, `chunk_index`, `origin`, `created_at`, namespace `kancelarija_{id}` ili `user_{id}` — sam naziv namespace-a **je** tenant identifikator |
| **Granica enkripcije** | TLS u tranzitu. **Nema aplikativne enkripcije metapodataka.** Isti sadržaj koji je u `intake-dokumenti` bucket-u AES-GCM šifrovan, u Pinecone-u stoji **u čistom tekstu**. Enkripcija se primenjuje na blob a ne na derivat istog sadržaja — nedosledna granica. |
| **Retencija kod provajdera** | Iz koda: **neograničena.** Nema TTL na `kancelarija_*` / `pred_*` / `user_*` namespace-ovima. `services/retention_service.py:102` čisti **samo `tmp_*`** (`uploaded_doc/cleanup.py:38-42`). |
| **Treniranje / interno logovanje kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Mehanizam brisanja** | `shared/vector_deletion.py::obrisi_vektore_dokumenta` je napisan, testiran, fail-closed — i ima **NULA produkcionih pozivalaca** (samo `tests/` i `scripts/ingest_case_law.py`). **Mehanizam postoji; nijedna ruta ga ne poziva.** |
| **POSTOJEĆA kontrola** | ✔ server-side ACL filter u samom `index.query` (`shared/rag_acl.py:136`) ✔ determinističke ID-jeve i odbijanje bez identiteta (`ingest.py:141-147`) ✔ odbijanje delimičnog ingest-a (`:88-92`) — **✘ tekst u metapodacima nešifrovan ✘ ime fajla nešifrovano ✘ nijedna putanja brisanja nije povezana ✘ nijedna retencija na trajnim namespace-ovima** |

### 3.7 Supabase Postgres (`*.supabase.co`)

| Polje | Nalaz |
|---|---|
| **Tačan izvor** | Jedan globalni klijent: `shared/deps.py:93` i `api.py:169` — `create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)` |
| **PT / ET** | **DA** — `predmet_dokumenti.tekst_sadrzaj` čuva `text[:100_000]` (`api.py:5260`) |
| **tenant/predmet/document/ime fajla** | **DA, sve, u čistom tekstu** — `naziv_fajla` (`api.py:5277`), `predmet_id`, `user_id` |
| **Granica enkripcije** | **Selektivna, na nivou polja.** AES-256-GCM (`security/crypto.py`) samo za `jmbg_encrypted`, `broj_pasosa_encrypted`, `pib_encrypted` (`klijenti/router.py:279-283`) i SEF API ključ (`routers/sef.py:293`). **Sav ostali sadržaj — tekst dokumenata, imena predmeta, komunikacija — je plaintext u bazi.** Google Calendar `access_token`/`refresh_token` se upisuju **nešifrovano** (`routers/integrations.py:359-360`). |
| **RLS** | **ZAOBIĐEN ZA CEO APLIKATIVNI KOD.** Jedini klijent koristi `SUPABASE_SERVICE_KEY`. RLS politike (ako postoje) ne štite ništa što ide kroz aplikaciju; izolacija u potpunosti počiva na `.eq("user_id", ...)` filterima koje pozivalac mora da se seti da doda. |
| **Retencija** | Delimično u kodu: `services/retention_service.py` briše `security_events` (90 d), `user_daily_activity` (90 d), `ai_forensics` (180 d). **Predmeti, klijenti, dokumenti, izvučeni tekst — bez retencije, namerno** (`retention_service.py:14-18`). |
| **Lokacija obrade / treniranje / interno logovanje kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju** |
| **Mehanizam brisanja** | GDPR ruta menja **2 tabele** (`routers/gdpr.py:219-228`). Nema brisanja predmeta ni dokumenata. |
| **POSTOJEĆA kontrola** | ✔ field-level AES-GCM za 4 polja ✔ fail-fast validacija ključa na startu (`crypto.py:55-117`) ✔ jedan klijent umesto ~50 (`deps.py:76`) — **✘ RLS zaobiđen ✘ tekst dokumenta plaintext ✘ OAuth tokeni plaintext ✘ nema retencije za sadržaj predmeta** |

### 3.8 Supabase Storage (`*.supabase.co/storage`)

Tri bucket-a, **tri različita režima enkripcije** — nedoslednost je sama po sebi nalaz.

| Bucket | Šta ulazi | Enkripcija | Kreiran migracijom? |
|---|---|---|---|
| `intake-dokumenti` | originalni PDF/DOCX/slike predmeta (Pipeline A `api.py:5100-5108`, Smart Intake `smart_intake.py:181-192`) | **AES-256-GCM pre upload-a** | DA — `migrations/073:362-364`, `public=false` |
| `klijent-dokumenti` | klijentski trezor (`klijenti/router.py:812`) | **AES-256-GCM pre upload-a** (`:800-805`) | **NE — nijedna migracija ga ne kreira** |
| `portal-uploads` | dokument koji **klijent** otprema kroz javni portal (`client_portal.py:591-599`) | **NIJEDNA — plaintext** | **NE — samo komentar u `migrations/013:5` „napravite ručno u Dashboard-u"** |

| Polje | Nalaz |
|---|---|
| **PT / ET** | DA — original fajla |
| **Ime fajla** | `klijent-dokumenti`: šifrovano (`encrypt_field(original_name)`). `intake-dokumenti`: **zamenjeno UUID-om** (`api.py:5101`). `portal-uploads`: **originalno ime u putanji, u čistom tekstu** (`client_portal.py:588`) |
| **tenant/predmet u putanji** | DA — `{user_id}/{predmet_id}/{uuid}` (`api.py:5101`), `{advokat_uid}/{predmet_id}/{uuid}_{ime}` (`client_portal.py:588`) |
| **Ključ enkripcije** | **Jedan simetričan ključ `FIELD_ENCRYPTION_KEY`** za blobove **i** PII polja (`crypto.py:122-140`). Blobovi **nemaju key-id prefiks** (za razliku od polja, `crypto.py:30`) → **rotacija ključa trajno onesposobljava sve postojeće blobove.** |
| **RLS na `storage.objects`** | **NE POSTOJI** — nula `CREATE POLICY` nad storage-om u 103 migracije. Izolacija = neproverljivost `uuid4` putanje + aplikativne provere. |
| **Javnost bucket-a** | `intake-dokumenti` = `public:false` **dokazano iz migracije**. `portal-uploads` i `klijent-dokumenti` = **UNKNOWN — kod ih ne kreira; potrebna je sonda `SELECT id, public FROM storage.buckets;`** |
| **Signed URL** | Jedno jedino mesto: `client_portal.py:702-703`, TTL 3600 s |
| **Mehanizam brisanja** | Kompenzujuća brisanja pri neuspehu postoje (`api.py:5330-5346`, `smart_intake.py:216-219`, `client_portal.py:634-637`). **Korisnički vidljivo brisanje dokumenta ne postoji.** GDPR ruta ne dodiruje Storage uopšte. |
| **Retencija / treniranje / logovanje kod provajdera** | **UNKNOWN — zahteva zasebnu verifikaciju** |

### 3.9 Ostali odlazni pozivi (runtime)

| Provajder | Kada | Šta odlazi | PT? | Kontrola / status |
|---|---|---|---|---|
| **SMTP** (`EMAIL_SMTP_HOST`) | notifikacije, portal linkovi, fakture | e-mail adresa, **naziv predmeta**, naziv fajla, portal token u URL-u (`client_portal.py:135-149`) | NE | TLS zavisi od servera; **UNKNOWN koji je server**. Slanje je fire-and-forget sa progutanim izuzetkom (`:156-157`) |
| **Twilio** (SMS / WhatsApp) | `routers/sms.py`, `routers/whatsapp_notif.py` | broj telefona, tekst podsetnika (može sadržati naziv predmeta i rok) | NE | Aktivno samo ako su `TWILIO_*` postavljeni — **UNKNOWN da li jesu** |
| **Viber** (`chatapi.viber.com`) | `routers/viber.py:85-100` | `viber_user_id`, tekst poruke | NE | Aktivno samo uz `VIBER_*` — **UNKNOWN** |
| **Google Calendar** (`googleapis.com`) | `routers/integrations.py:406-425` | naziv i opis roka, datum, `predmet_id` u opisu | NE | **OAuth tokeni čuvani nešifrovano** (`:359-360`). Čita tabelu `rokovi` — **v. §4** |
| **Google OAuth** (`oauth2.googleapis.com`) | `integrations.py:333` | authorization code, client_secret | NE | — |
| **Etherscan** (`api.etherscan.io`) | `routers/wallet_provenance.py:88-135` | **samo adresa novčanika** koju korisnik unese | NE | Nikakav podatak o predmetu ne odlazi |
| **APR** (`pretraga.apr.gov.rs`) | `routers/apr.py:128-150` | **samo matični broj** firme | NE | Circuit breaker + timeout 15 s |
| **portal.sud.rs**, sudovi | `routers/portal_monitoring.py:99` | broj predmeta (javni podatak) | NE | timeout 20 s |
| **SEF eFaktura** (`efaktura.mfin.gov.rs`) | `routers/sef.py` | podaci fakture | NE | API ključ **šifrovan** (`sef.py:293`) — jedina ispravno zaštićena integracija |
| **OFAC** | `routers/ofac_screening.py:41-53` | **NIŠTA — lokalni JSON fajl**, nema mrežnog poziva u runtime-u | — | ✔ |
| **Web Push** (`pywebpush`) | `routers/push.py:86-98` | naslov + telo notifikacije | NE | **MRTAV KOD** — nula produkcionih pozivalaca, samo test ruta |
| **Odlazni webhook-ovi** | `integrations.py:248-290`, `integracije.py:382` | **proizvoljan `data` dict na korisnički zadat URL** — potencijalno neograničen kanal iznošenja | potencijalno DA | **MRTAV KOD — nula pozivalaca `trigger_webhook` u celom repou.** Kanal je izgrađen ali nije povezan. |
| **EmailJS** (browser) | `index.html:26` | — | — | **MRTAV** — ključevi su placeholder-i `'VAŠ_PUBLIC_KEY'` (`static/vindex.js:1062-1064`) |

### 3.10 Granica u browseru — CSP (`api.py:1149-1160`)

```
connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com
            https://api.emailjs.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com
            https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com
script-src  'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com
```

**Postojeća kontrola:** ✔ `frame-ancestors 'none'` ✔ HSTS ✔ `nosniff` ✔ CSP report endpoint ✔ SRI za CDN skripte (`security/compute_sri.py`).

**Nalaz:** `script-src` dozvoljava `'unsafe-inline'` **i** tri treće strane (jsDelivr, cdnjs, unpkg). Kompromitovan paket na bilo kojoj od njih dobija izvršavanje u kontekstu stranice i **već ima dozvolu da šalje na `api.emailjs.com` i `*.supabase.co`**. Ovo je izlazni kanal koji CSP ne zatvara.

---

## §4. NALAZI KOJI SU IZAŠLI IZ ANALIZE GRANICE

1. **Ceo tekst dokumenta stoji nešifrovan u Pinecone metapodacima**, dok isti taj sadržaj u Supabase Storage-u JESTE AES-GCM šifrovan. Enkripcija se primenjuje na blob, ne na derivat — granica je nedosledna.

2. **`portal-uploads` je jedini nešifrovan bucket i jedini u koji piše neautentifikovana treća strana** (klijent kroz portal). Nijedan od 9 upload puteva nema antivirusnu proveru.

3. **RLS je zaobiđen svuda** — jedan `service_role` klijent. Svaka izolacija je aplikativna i ručno napisana.

4. **Nijedan storage bucket nema RLS politiku** — nula `CREATE POLICY` na `storage.objects` u 103 migracije.

5. **7 tabela se čita/piše iz koda a nema `CREATE TABLE` nigde u repou.** Tri su pokrivene kao view (`case_profitability`, `events_outbox_metrics`, `intake_queue_metrics`). Preostaju **`rokovi`, `ai_cache`, `ai_sessions`, `klijenti_dokumenti`**.
   - `rokovi` — 13 produkcionih pozivnih mesta; `migrations/023:19-20` pravi INDEX nad tabelom koju nijedna migracija ne kreira.
   - `klijenti_dokumenti` — **greška u imenu:** pisac koristi `klijent_dokumenti` (postoji, `migrations/002:143`), a čitalac `klijenti/router.py:1422` koristi `klijenti_dokumenti` (ne postoji). Čitanje je u `asyncio.gather` bez `return_exceptions`.
   - Da li ove tabele postoje u živoj bazi — **UNKNOWN. Dokazuje se isključivo sondom šeme, ne kodom.**

6. **`ai_cache` je globalan keš odgovora bez tenant ključa** (`main.py:207-256`). Ključ je `md5(normalizovano_pitanje)`. Jedina izolacija su dva literalna stringa `"KONTEKST PREDMETA:"` / `"[Predmet:"` (`_PRIVATNI_KONTEKST_MARKERI`). Svaka buduća putanja koja ubaci kontekst predmeta pod drugim zaglavljem upisuje odgovor specifičan za klijenta u red čitljiv svim tenantima, 7 dana.

7. **Google OAuth tokeni se čuvaju u čistom tekstu** (`integrations.py:359-360`) iako `security/crypto.py::encrypt_field` postoji i koristi se dva reda dalje u drugim modulima.

---

## §5. SAŽETA TABELA — SVE UNKNOWN STAVKE NA JEDNOM MESTU

Nijedna od stavki ispod se ne sme pretvoriti u zaključak bez zasebne verifikacije (§10).

| # | Pitanje | Zašto kod ne može da odgovori | Kako se dokazuje |
|---|---|---|---|
| U-01 | Retencija promptova kod OpenAI | politika provajdera | DPA / ZDR ugovor |
| U-02 | Treniranje na Vindex podacima (OpenAI) | politika provajdera | DPA |
| U-03 | Interno logovanje kod OpenAI | politika provajdera | DPA |
| U-04 | Retencija / treniranje / logovanje kod Pinecone | politika provajdera | DPA |
| U-05 | Retencija / treniranje / logovanje kod Cohere | politika provajdera | DPA |
| U-06 | Retencija / lokacija obrade kod Supabase | politika provajdera | DPA + izbor regiona |
| U-07 | Retencija Realtime audio sesija (OpenAI) | politika provajdera | DPA |
| U-08 | Da li je Azure OpenAI aktiviran u produkciji | stanje env-a | `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT` u prod env-u |
| U-09 | Da li je Cohere uključen u produkciji | stanje env-a | `VINDEX_COHERE_RERANK` u prod env-u |
| U-10 | Da li su `portal-uploads` i `klijent-dokumenti` privatni | stanje baze | `SELECT id, public FROM storage.buckets;` |
| U-11 | Da li tabele `rokovi` / `ai_cache` / `ai_sessions` / `klijenti_dokumenti` postoje | stanje baze | sonda `information_schema.tables` — **delimično razrešeno tuđom sondom, v. napomenu ispod** |
| U-12 | Da li je migracija 089 primenjena (provenance join ključevi) | stanje baze | `docs/beta_gate/VERIFY_MIGRATION_089_READONLY.sql` |
| U-13 | Da li su Twilio / Viber / SMTP / GCal aktivirani | stanje env-a | prod env |
| U-14 | Da li RLS politike uopšte postoje (i pored toga što ih service_role zaobilazi) | stanje baze | `scripts/export_rls_policies.py` uz `SUPABASE_DB_URL` |
| U-15 | Da li governance patch pokriva embeddings/audio u živoj instanci | runtime stanje | `GET /api/version` → `governance_status()` |

**`SUPABASE_DB_URL` je i dalje neisporučen od Black Swan misije — U-10, U-12 i U-14 ostaju nedokazivi bez njega.**

### Napomena o U-11 — ukršteni dokaz koji nije proizvod ovog audita

`docs/beta_gate/SCHEMA_PHANTOM_INVENTORY.md` (proizvod **odvojene §2 sesije**, ne ovog audita) beleži žive PostgREST sonde: `rokovi` → `404 PGRST205`, `ratio_decidendi` → `404`, `klijenti_dokumenti` → `404` uz hint `public.klijent_dokumenti`. Ovaj audit tu sondu **nije ponovio** i drži je odvojenom od sopstvenih nalaza; navodi se kao nezavisno slaganje, ne kao izvor. `ai_cache` i `ai_sessions` u tom dokumentu nisu razrešeni i **ostaju UNKNOWN**.
