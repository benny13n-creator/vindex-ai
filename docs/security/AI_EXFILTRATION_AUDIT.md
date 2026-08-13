# AI Exfiltration & Log Leakage Forensics

**Program:** BETA-DATA-CONFIDENTIALITY-001 · Agent C
**Datum:** 2026-08-13
**Baseline commit:** `0df948ec`
**Status:** Nalazi popisani. **Nijedan produkcijski fajl nije izmenjen.**

---

## 0. Metodologija — zašto se ovim brojevima može verovati

Ključne tvrdnje u ovom dokumentu su **izmerene, ne pročitane**. Kod je presretnut
na SDK granici — tačno na mestu gde bi OpenAI SDK poslao HTTP zahtev — pa je
snimljen doslovan payload.

**Tačka presretanja:** `shared/ai_client.py::_orig_create` / `_orig_acreate`.
Zamenjene su *ispod* kanonske kapije, pa se **sve iznad izvršava stvarno**:
prompt guard, response firewall, AI provenance, timeout. Merena je prava
putanja, ne njena imitacija.

**Dokaz da nijedan bajt nije napustio mašinu:**

| Mera | Kako |
|---|---|
| `socket.socket.connect` / `connect_ex` | prepisani — sve osim `127.0.0.1` diže `NetworkBlocked` |
| `socket.create_connection` | isto |
| `socket.getaddrinfo` | prepisan — DNS za svaki spoljni host diže `NetworkBlocked` |
| API ključevi | isključivo lažni (`sk-test-NIJE-PRAVI-KLJUC-...`); `dotenv.load_dotenv` neutralisan da `.env` sa živim ključevima nikad ne bude učitan |
| Supabase / Pinecone | lažni URL-ovi i ključevi; upis provenance zapisa presretnut pred bazu |

Loopback je namerno dozvoljen jer ga `asyncio` na Windows-u koristi za interni
self-pipe. Nijedan spoljni host nije bio dostupan ni preko IP-a ni preko imena.

**Nula mutacija produkcionih podataka.** Nijedan test nije pogodio stvarni
OpenAI, Pinecone ni Supabase.

---

## 1. Šta tačno odlazi OpenAI-ju — izmereno

### 1.1 Analiza dokumenta (`main.py::ask_analiza`, `/api/analiza`)

Ulaz: sintetički ugovor o kupoprodaji (966 karaktera) sa punim setom ličnih
podataka. Izmereni payload: **4.622 karaktera**, 2 poruke (`system` 3.556,
`user` 1.065).

| Podatak | Ishod |
|---|---|
| Pun tekst dokumenta | **ODLAZI** — doslovno, bez skraćivanja |
| Ime klijenta (`MILAN PETROVIĆ`) | **ODLAZI** |
| Ime protivnika (`Jelena Stanković`) | **ODLAZI** |
| Naziv firme (`ADRIA GRADNJA`) | **ODLAZI** |
| Ime punomoćnika (`Dragan Jovanović`) | **ODLAZI** |
| Adrese (`Kneza Miloša 42`, `Vojvode Stepe 118`) | **ODLAZI** |
| Katastarski podaci (`list nepokretnosti 4412`) | **ODLAZI** |
| Iznos posla (`145.000,00 EUR`) | **ODLAZI** |
| JMBG (oba) | maskiran → `[JMBG-MASKED]` |
| PIB | maskiran → `[PIB-MASKED]` |
| E-mail, telefon, IBAN, broj lične karte | maskirani |
| Broj sudskog predmeta | maskiran → `[PREDMET-MASKED]` |
| **Matični broj `21234567`** | **ODLAZI — v. `EXF-007`** |

**Zaključak:** maska hvata *strukturirane identifikatore*. Ne hvata **nijedno
ime, nijednu firmu, nijednu adresu, ni sam sadržaj predmeta**. Za advokatsku
tajnu, imena stranaka i sadržaj ugovora su poverljiviji od JMBG-a.

### 1.2 Strategija — Red Team / AI Sudija / Litigation / Due Diligence (`strategija.py`)

Četiri putanje merene pojedinačno. **Sve četiri identično:**

| Podatak | Ishod |
|---|---|
| Ime klijenta, ime protivnika, naziv firme | **ODLAZI** |
| **JMBG `0101980710123`** | **ODLAZI — NEMASKIRAN** |
| **PIB `108234567`** | **ODLAZI — NEMASKIRAN** |
| Adresa, broj predmeta, vrednost spora | **ODLAZI** |
| **Privatna beleška advokata** (`INTERNO: klijent laže o datumu`) | **ODLAZI** |

Ove putanje **ne pozivaju `_skini_pii` uopšte**. Za razliku od `/api/analiza`,
ovde JMBG i PIB odlaze u čistom obliku.

Izmerena pokrivenost prompt guard-a po pozivu:

| Putanja | `system` | `user` | Guard analizira |
|---|---|---|---|
| Red Team | 729 | 663 | 663 / 1.393 (**48 %**) |
| AI Sudija | 741 | 561 | 561 / 1.303 (**43 %**) |
| Litigation Simulator | 1.255 | 559 | 559 / 1.815 (**31 %**) |
| Due Diligence | 1.239 | 929 | 929 / 2.169 (**43 %**) |
| Nacrt podneska | 1.689 | 348 | 348 / 2.038 (**17 %**) |
| Glasovna komanda | 4.899 | 72 | 72 / 4.972 (**1 %**) |

### 1.3 Nacrt podneska (`main.py::ask_nacrt`)

Primenjuje `_skini_pii` — JMBG, PIB i broj predmeta maskirani. **Ali** ime
klijenta, naziv firme, adresa, iznos i **privatna beleška advokata odlaze
nemaskirani.**

### 1.4 Glasovna sesija (`routers/voice.py`, `services/voice_orchestrator.py`)

Dve odvojene putanje:

- **`routers/voice.py`** — `audio.transcriptions.create` (Whisper): odlazi
  **sirov audio bajt-tok** izgovorenog razgovora. Guard se ne primenjuje (ulaz
  nije tekst — to je ispravno). Zatim `_handle_query` šalje kontekst predmeta +
  transkript, **bez PII maske**.
- **`services/voice_orchestrator.py:47`** — `wss://api.openai.com/v1/realtime`,
  sirov WebSocket. **Potpuno zaobilazi kanonsku kapiju** — v. `EXF-006`.

### 1.5 Pravno pitanje (RAG)

Jedina putanja koja koristi masku dosledno (`api.py:3358`, `:3443`). Pitanje se
maskira pre klasifikacije i pre embedovanja. **Ovo je uzoran obrazac** i jedini
u repou koji radi ono što `docs` tvrde.

### 1.6 Kompletan popis pozivnih mesta (AST, cela produkcija)

| Mera | Broj |
|---|---|
| Ukupno AI pozivnih mesta | **84** (77 `chat`, 5 `embeddings`, 2 `audio`) |
| U fajlovima koji **uopšte ne pominju** `_skini_pii` | **75 (89 %)** |
| U fajlovima koji je pominju, ali ne na toj putanji | 9 |

Samo **4 fajla** u celoj produkciji dodiruju PII masku na AI granici:
`main.py`, `api.py`, `routers/drafting.py`, `routers/oblasti.py`.

---

## 2. Postoji li ijedan sanitizator PII pre slanja modelu

### Odgovor: **DA — ali samo jedan, i pokriva manjinu putanja.**

**`main.py:1076::_skini_pii`** postoji i **radi** — izmereno, ne pročitano.
Maskira: JMBG, PIB, matični broj, ličnu kartu, pasoš, telefon, IBAN, broj
računa, broj sudskog predmeta, e-mail, i adrese po heuristici `ulica X 12`.

**Šta NE radi ni na jednoj putanji:**

- ne uklanja **imena fizičkih lica** — nema takvog obrasca
- ne uklanja **nazive pravnih lica**
- ne uklanja **sadržaj predmeta** (sam tekst ugovora, presude, beleške)
- ne uklanja **naziv predmeta** ni **naziv fajla**

### Sanitizatori koji NE postoje ili ne rade

| Tvrdnja | Izmereno stanje |
|---|---|
| `sanitize_for_ai()` | **NE POSTOJI** u repou |
| `security.prompt_guard.sanitize_prompt` | **NE POSTOJI.** `shared/ai_fabric.py:535` ga uvozi u `try/except ImportError: pass`. Potvrđeno izvršavanjem: `ImportError: cannot import name 'sanitize_prompt'`. Deklarisani „REUSE postojećeg prompt guard-a" je **tihi no-op** — `ai_fabric` ne sanitizuje ništa. |
| `prompt_guard.wrap_for_ai()` — deklarisani „Sloj 4: izolacija" | **MRTAV KOD.** Nula poziva u produkciji (jedini pogoci: sopstvena definicija, dva komentara, jedan test). Docstring modula ga navodi kao „arhitekturalnu odbranu koja ostaje aktivna nezavisno od detekcije" — ona nije aktivna nigde. |
| `escHtml` | XSS zaštita u frontendu, ne PII maska — nije relevantan za odlazni AI payload |

### Heš funkcije — jesu, ali nisu sanitizatori odlaznog payload-a

`_hash_za_log`, `ai_provenance.sha256_text`, `prompt_guard._short_hash` rade
ispravno i koriste se za **logovanje**, ne za ono što odlazi modelu. Ne treba ih
mešati sa sanitizacijom.

---

## 3. Zlonamerni dokument kao kanal instrukcija — **NAJVAŽNIJI DEO**

### 3.1 Ispravka pretpostavke iz zadatka

Zadatak je pretpostavio da guard možda „gleda samo korisnikovo pitanje".
**Izmereno: ne — guard vidi i sadržaj dokumenta.**

`ask_analiza` sastavlja jednu `user` poruku oblika
`SPECIFIČNO PITANJE: …\n\nDOKUMENT ZA ANALIZU:\n<tekst>`, pa
`_extract_user_text` prosleđuje analizatoru i pitanje i dokument zajedno.

### 3.2 Eksperiment i rezultat

| # | Scenario | `analyze()` score | Stigao do OpenAI? |
|---|---|---|---|
| A | `IGNORE ALL PREVIOUS INSTRUCTIONS…` u telu dokumenta (324 kar.) | **1.00 — blocked** | **NE** |
| B | `Zanemari sve prethodne instrukcije…` (srpski, 190 kar.) | **1.00 — blocked** | **NE** |
| C | **Ista injekcija posle 71.892 karaktera** | **0.00 — nije blocked** | **DA** |
| D | Kontrola: čist pravni dokument | 0.00 | DA (ispravno) |
| E | Kontrola smera: injekcija u pitanju, dokument čist | 1.00 | **NE** |

Kontrolna grupa D potvrđuje da merenje nije lažno pozitivno, a E da mehanizam
radi u oba smera.

### 3.3 `EXF-001` — KRITIČNO: guard je slep iza 60.000 karaktera

`security/prompt_guard.py:96` postavlja `MAX_INPUT_CHARS = 60_000`, a
`analyze()` na liniji 176 radi `truncated = normalized[:MAX_INPUT_CHARS]`
**pre** pattern matching-a. Sve iza te granice se ne analizira.

Izmerena granica, karakter po karakter:

| Pozicija injekcije | Score | Blokiran |
|---|---|---|
| 0 | 1.00 | DA |
| 50.000 | 1.00 | DA |
| 59.000 | 1.00 | DA |
| **60.100** | **0.00** | **NE** |
| **100.000** | **0.00** | **NE** |

**Posledica koja je izmerena, ne pretpostavljena:** u scenariju C dokument od
72.024 karaktera prošao je guard sa ocenom `0.00`, i **75.654 karaktera je
poslato modelu — sa injekcijom doslovno u payload-u.** `ask_analiza` ne skraćuje
dokument pre slanja, pa se šalje ceo, dok se analizira samo prvih 60.000.

**Zašto je ovo realno, a ne teoretski:** 60.000 karaktera je otprilike 25–30
strana. Ugovori, presude, veštačenja i optužnice tu granicu prelaze redovno.
Napadač ne mora ni da zna za granicu — dovoljno je da pošalje dugačak dokument.
Napadač koji zna za nju samo doda uvodni tekst i injekcija postaje nevidljiva.

Isti mehanizam pogađa i legitimne dokumente: injekciju ubačenu u dokument koji
je *protivna strana* dostavila advokat ne bi ni video.

### 3.4 `EXF-008` — `system` poruka se nikad ne analizira

`_extract_user_text` (`shared/ai_client.py:251`) namerno preskače `system`
poruke. To je ispravan ugovor **dok god** `system` sadrži isključivo konstante
koje autor rute kontroliše. Provereno statički: na svim pregledanim putanjama
`system` jeste konstanta — **danas ovo nije aktivna rupa**, ali je nezaštićena
konvencija, ne ograničenje. Prvi `system` prompt sastavljen od korisničkih
podataka biće potpuno nevidljiv guard-u. Izmerena pokrivenost od 1 % do 48 %
(tabela u §1.2) pokazuje koliko je površine izvan analize.

---

## 4. Logovi, telemetrija, greške

### 4.1 Infrastruktura — tri činjenice koje određuju sve ostalo

1. **Nema nijednog redaktujućeg logging filtera.** U celoj produkciji nema
   `logging.Filter` podklase, `dictConfig`-a, ni `setFormatter`-a koji bilo šta
   uklanja. Samo dva gola `logging.basicConfig` (`api.py:108`, `main.py:26`).
2. **`logger.debug` se na produkciji NE izvršava.** Nivo je tvrdo kodiran na
   `logging.INFO`; nema `LOG_LEVEL` env var nigde. Sva `debug` curenja su
   **uspavana** — realna, ali uslovna.
3. **Sentry nema `before_send` ni `event_scrubber`.** `send_default_pii=False`
   jeste postavljen (`api.py:47`) i to je dobro, ali `attach_stacktrace=True` uz
   odsustvo scrubbing-a znači da svaki `detail=f"…{exc}"` odlazi Sentry-ju
   neredaktovan.

### 4.2 Grupa A — sirov sadržaj (AKTIVNO, izvršava se na INFO)

| Lokacija | Nivo | Šta curi |
|---|---|---|
| `api.py:3398` | error | **ceo `rezultat` dict — kompletan LLM odgovor korisniku** |
| `app/services/retrieve.py:2204` | info | **200 kar. sadržaja svakog od top-3 dokumenta**, uključujući chunkove iz `DOC_NS` (korisnikov otpremljen dokument) — na **svakom** RAG pozivu |
| `api.py:5627` | warning | sirov LLM JSON izveden iz dokumenta predmeta (150 kar.) |
| `app/services/retrieve.py:2199, 2210` | info/error | sirovo korisničko pitanje (80 kar.) |
| `retrieve.py:903, 907, 1820, 1859, 2423, 2650, 2741` | mešano | sirovo pitanje (60 kar.) — 7 mesta |
| `api.py:5399` | info | RAG upit izveden iz teksta dokumenta (60 kar.) |
| `routers/voice.py:260` | info | 80 kar. LLM odgovora korisniku |
| `routers/voice.py:532` | info | 120 kar. sirove glasovne komande |
| `routers/sef.py:212` | warning | 300 kar. sirovog odgovora e-faktura API-ja |

### 4.3 Grupa A — uspavano (`debug`, ne izvršava se pri INFO)

`main.py:3695` (200 kar. teksta dokumenta), `main.py:3710` (300 kar. LLM
odgovora), `main.py:4206` (200 kar. LLM JSON-a), `retrieve.py:1283` (HyDE
tekst), `routers/integrations.py:428`.

### 4.4 Grupa B — identiteti (aktivno)

Puni e-mail korisnika: `api.py:351`, `shared/deps.py:660`, `api.py:2727`,
`:2758`, `routers/kancelarija.py:402/473/516/556/628`, `routers/waitlist.py:176`,
`routers/support.py:216`, `routers/client_portal.py:155`,
`routers/morning_briefing.py:546/666/967`, `routers/billing.py:872`.

Nazivi otpremljenih fajlova: `api.py:5105`, `:5109`,
`routers/smart_intake.py:194`, `:208`, `routers/client_portal.py:643`,
`services/event_bus.py:204`.

Imena i firme klijenata: `shared/case_assimilation.py:203`, `:229`;
broj predmeta `:160`, `routers/portal_monitoring.py:598`,
`routers/integracije.py:316`.

Brojevi telefona u punom obliku: `routers/sms.py:80/88/91/141`,
`routers/whatsapp_notif.py:102/105/232`.

### 4.5 Grupa C — Storage putanje

`routers/client_portal.py:637` loguje **pun storage path**
`{advokat_uid}/{predmet_id}/{uuid}_{naziv_fajla}`. `api.py:5258`, `:5263` — pun
storage ključ originalnog fajla.

**Signed URL se ne loguje nigde** — provereno, i to je ispravno.

### 4.6 Grupa D — tekst izuzetka (ide i korisniku i Sentry-ju)

`api.py:5175` (ceo string Pinecone izuzetka pri ingestu korisnikovog dokumenta),
`api.py:2901`, `routers/dokument.py:319`, `routers/court_predictor.py:490` i još
5 mesta u istom fajlu, `routers/admin_dashboard.py` (7 mesta),
`klijenti/router.py:819`, `routers/law_upload.py:220`,
`routers/auto_discovery.py:498`, `:537`, `routers/export.py:217`.

### 4.7 `retrieval_query` u `ai_forensics` — provereno posebno

**Ranija tvrdnja je tačna u pogledu dizajna, ali netačna u pogledu ponašanja.
Razlika je bitna.**

Izmereno (`security/ai_forensics.py`, presretnuto pred upis u bazu):

```
system_prompt_hash = ad198357e58fe7c3815c68e3849df43537f74b52d04af0348f045790614d443b
user_prompt_hash   = 5e4000f75eb4ddfa761ca68eeb2b9bc661ce6d5129620950e9de06570848bb95
output_hash        = fd26c625ecf9b59c340cad0b0764a1f4c4989f538db547b5871068234b6947d1
retrieval_query    = Klijent Milan Petrovic, JMBG 0101980710123, predmet P. 1234/2024
```

Prompt, odgovor i sistemska instrukcija su **isključivo heš** — to je ispravno i
zaslužuje da bude priznato. `retrieval_query` je jedino polje koje **prihvata i
prosleđuje sirov tekst** (`migrations/089_ai_provenance_extension.sql:43` ga
definiše kao `TEXT`).

**Ali:** iscrpna pretraga cele produkcije nalazi **tačno 2 mesta** koja dodeljuju
`retrieval_query`, i oba su *čitanja* u `shared/ai_client.py:460` i `:517`
(`ctx.get("retrieval_query")`). **Nijedan produkcijski pozivalac ga ne
postavlja** → u praksi je danas uvek `NULL`.

Gornja vrednost je dobijena tako što ju je harness namerno postavio — čime je
dokazano da bi kanal proradio čim ga neko upotrebi. Ovo je **latentan**, ne
aktivan nalaz. Ne treba ga prijaviti kao aktivno curenje.

---

## 5. Treće strane

### 5.1 Aktivno po defaultu — podaci klijenata OBAVEZNO napuštaju sistem

| Servis | Šta odlazi | Neophodno za betu? |
|---|---|---|
| **OpenAI** (`api.openai.com`) | pun tekst dokumenata, upiti, imena stranaka, sadržaj predmeta, sirov audio | **DA** — jezgro proizvoda |
| **Pinecone** | **pun tekst chunkova (do 40.000 kar.) + naziv fajla + `user_id`** u metadata — v. `EXF-002` | **DA** za RAG, ali ne u ovom obliku |
| **Supabase** | sve, uključujući `tekst_sadrzaj` dokumenata i Storage fajlove | **DA** — primarna baza |

### 5.2 Aktivno bez ključa, šalje minimum

| Servis | Šta odlazi |
|---|---|
| `pretraga.apr.gov.rs` | matični broj firme kao query param |
| `portal.sud.rs` | broj predmeta + naziv suda |
| `pravno-informacioni-sistem.rs` | ništa (GET RSS-a) |

### 5.3 Isključeno po defaultu (uslovljeno env var-om)

**Cohere** — traži tri uslova istovremeno (paket + `COHERE_API_KEY` +
`VINDEX_COHERE_RERANK` opt-in); u `.env.example` prazno. Kad bi bio uključen,
odlazili bi sirov upit i isečci do 1.000 kar. iz Pinecone matcheva — dakle i
isečci klijentovog dokumenta. Kod sam konstatuje da Cohere SDK ne prolazi kroz
prompt guard ni `ai_forensics`.

**Isključeni:** Sentry, SMTP, Twilio SMS/WhatsApp, Viber, Web Push, Google
Calendar, Etherscan, Azure OpenAI.

**Ne postoje:** Stripe/Paddle, Anthropic, Gemini, AWS, Slack/Zapier,
Mixpanel/Segment.

**OCR je LOKALAN** — `pytesseract` + PyMuPDF/pypdf, nula mrežnih poziva
(`uploaded_doc/extractor.py:104-363`). Nema Google Vision / Azure DI / Textract.
Dobra vest; ali OCR-ovani tekst potom ide u OpenAI i Pinecone.

**OFAC screening i chain anchoring su lokalni** — bez spoljnih poziva.

### 5.4 Frontend

**Nula analytics.** Grep za gtag, GA, Plausible, PostHog, Hotjar, Mixpanel,
Amplitude, Segment, Clarity, Facebook pixel, Sentry browser SDK → **0 pogodaka**.
To je bolje od većine proizvoda u ovoj fazi i treba to reći.

Eksterni resursi: `fonts.googleapis.com` / `fonts.gstatic.com` (bez SRI — Google
Fonts CSS ga ne podržava), `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`,
`unpkg.com`. **SRI je prisutan na svih 6 skriptovanih CDN resursa.**

Odlazi samo ono što svaki HTTP GET nosi — IP, User-Agent, Referer. Nema
payload-a. **Ali:** Google, Cloudflare, jsDelivr i Unpkg time vide IP svakog
advokata i vreme korišćenja aplikacije. To je obaveza objave u privacy policy.

CSP postoji kao HTTP header (`api.py:1149-1161`). Tri slabosti:

1. `script-src 'unsafe-inline'` — poništava veći deo XSS zaštite
2. `connect-src https://api.openai.com` — nijedan frontend `fetch()` ne zove
   OpenAI; suvišan unos koji sugeriše da je ključ nekad bio u browseru
3. `connect-src https://api.emailjs.com` uz mrtav EmailJS kod
   (`EMAILJS_PUBLIC_KEY = 'VAŠ_PUBLIC_KEY'` placeholder)

---

## 6. Nalazi

| ID | Ozbiljnost | Nalaz | Dokaz |
|---|---|---|---|
| **EXF-001** | **KRITIČNO** | Prompt guard je slep iza 60.000 kar. Dokument od 72.024 kar. sa injekcijom prošao sa `score=0.00`; **75.654 kar. poslato modelu sa injekcijom u payload-u** | izmereno, §3.3 |
| **EXF-002** | **KRITIČNO** | Pun neredigovan tekst klijentovog dokumenta (do 40.000 kar./chunk) + naziv fajla + `user_id` čuva se **trajno** u Pinecone metadata. `uploaded_doc/` ne pominje `_skini_pii` nijednom | `uploaded_doc/ingest.py:12,79-88`; grep = 0 pogodaka |
| **EXF-003** | **VISOKO** | 75 od 84 AI pozivnih mesta (89 %) u fajlovima koji PII masku uopšte ne pominju. Strategija putanje šalju **JMBG i PIB u čistom obliku** | AST popis + izmereno, §1.2, §1.6 |
| **EXF-004** | **VISOKO** | Glavna putanja otpremanja dokumenta u predmet nema PII masku — šalje naziv predmeta, sirov tekst, **privatne beleške advokata**, naziv fajla | `api.py:5441-5504`; `_skini_pii` u `api.py` postoji samo na `:3358` i `:3443` |
| **EXF-005** | **VISOKO** | `wrap_for_ai()` — deklarisani „Sloj 4: izolacija" — je mrtav kod, 0 poziva. `sanitize_prompt` ne postoji; `ai_fabric.py:535` ga guta u `except ImportError: pass` → tihi no-op | grep + izvršeno, §2 |
| **EXF-006** | **VISOKO** | `wss://api.openai.com/v1/realtime` (`voice_orchestrator.py:47`) potpuno zaobilazi kanonsku kapiju — nema prompt guard-a, response firewall-a ni provenance-a nad privilegovanim govornim razgovorom | `shared/ai_client.py:663` to i priznaje kao deo ugovora |
| **EXF-007** | **SREDNJE** | PII maska pada na ASCII transliteraciji. `matični broj` je maskiran, **`maticni broj: 21234567` nije** — regex traži dijakritiku. OCR i skenirani dokumenti redovno gube dijakritiku | izmereno, §1.1 |
| **EXF-008** | **SREDNJE** | `system` poruka se nikad ne analizira; izmerena pokrivenost guard-a 1 %–48 %. Danas nije aktivna rupa (svi `system` promptovi su konstante), ali je konvencija, ne ograničenje | izmereno, §3.4 |
| **EXF-009** | **VISOKO** | `api.py:3398` loguje ceo LLM odgovor u ERROR; `retrieve.py:2204` loguje 200 kar. sadržaja dokumenta u INFO na **svakom** RAG pozivu. Nema nijednog redaktujućeg log filtera | §4.1, §4.2 |
| **EXF-010** | **SREDNJE** | Sentry nema `before_send`/`event_scrubber`; ~25 mesta gradi `detail=f"…{exc}"` koji ide i korisniku i Sentry-ju neredaktovan | §4.1, §4.6 |
| **EXF-011** | **NISKO (latentno)** | `retrieval_query` je jedino nehaširano polje u `ai_forensics` i primio bi sirov tekst — **ali nijedan produkcijski pozivalac ga ne postavlja**, danas uvek `NULL` | izmereno, §4.7 |
| **EXF-012** | **NISKO** | CSP dozvoljava `api.openai.com` i `api.emailjs.com` iako nijedan frontend poziv ne postoji; `script-src 'unsafe-inline'` | §5.4 |

### Šta radi ispravno — treba priznati

- AI provenance beleži prompt, odgovor i sistemsku instrukciju **isključivo kao
  SHA-256**, nikad kao tekst (izmereno).
- `prompt_guard` loguje samo heš, score i broj flagova — uzoran obrazac.
- `response_firewall` audit zapis nosi samo determinističke kodove.
- Fail-closed brana na AI granici (`_install_ai_kill_switch`) je stvarna i radi.
- Prompt guard **vidi sadržaj dokumenta** (do 60k) — bolje nego što se
  pretpostavljalo.
- Nula analytics u frontendu; SRI na 6/6 CDN skripti; OCR lokalan; signed URL se
  ne loguje.

---

## 7. Šta NIJE provereno (granice ovog audita)

- Nije mereno ponašanje pod `uvicorn`-om — `basicConfig` je no-op ako root logger
  već ima handlere; redosled inicijalizacije pod gunicorn-om je **UNKNOWN**.
- Nije mereno stvarno stanje Pinecone indeksa na produkciji (koliko klijentskih
  dokumenata je već upisano) — zahtevalo bi pristup produkciji, što je van
  mandata.
- Nisu izvršene sve 84 putanje — 6 je izmereno end-to-end, ostatak je pokriven
  statičkim popisom.
- `F2-001` i 13 odloženih helpera nisu dirani, po nalogu.
- Nije provereno da li OpenAI ugovor (Basic API tier bez DPA, kako
  `main.py:3636` sam navodi) pokriva ovaj obim podataka — to je pravno, ne
  inženjersko pitanje, ali je preduslov za betu.

---

*Nijedan produkcijski fajl nije izmenjen. Nijedan test nije pogodio stvarni
OpenAI, Pinecone ni Supabase. Merni harness je živeo isključivo u scratchpad
direktorijumu.*
