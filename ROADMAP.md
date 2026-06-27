# VINDEX AI — MASTER ROADMAP
## Redosled implementacije: od kritičnog do strateškog

---

## FAZA 0 — KRITIČNI BUGOVI (Fix pre svega ostalog)

Ovo su broken stvari koje oštećuju produkciju ili korisničko iskustvo odmah.

---

### F0.1 — Fix Matter Intel async bug
**Fajlovi:** `routers/matter_intel.py`
**Problem:** Supabase pozivi se izvršavaju sinhrono direktno u async funkciji — blokira event loop, usporava ceo server pod opterećenjem.
**Šta uraditi:**
- Svaki `supa.table(...).execute()` poziv obmotati u `asyncio.to_thread(lambda: ...)`
- Verifikovati iste probleme u `routers/copilot.py`, `routers/ccc.py` — fix gde postoji

---

### F0.2 — OCR za skenirane dokumente
**Fajlovi:** `routers/dokument.py`, `requirements.txt`
**Problem:** `is_scanned=True` vraća HTTP 422. 70%+ sudskih dokumenata je skenirano.
**Šta uraditi:**
- Instalirati `pytesseract` + `pdf2image` (Poppler dependency na serveru)
- Ako je `is_scanned=True`: konvertovati PDF stranice u slike → Tesseract OCR → spojiti tekst
- Alternativa: AWS Textract API poziv (bolji kvalitet, pay-per-use) — env var `OCR_PROVIDER=tesseract|textract`
- Ukloniti HTTP 422, vratiti ekstraktovani tekst (sa napomenom da je OCR)
- Dodati `ocr_quality_score` u response (Tesseract confidence %)

---

### F0.3 — Knowledge Base — Semantička pretraga i RAG injektovanje
**Fajlovi:** `routers/knowledge_base.py`, `static/vindex.js`, `index.html`
**Problem:** Trenutno je samo CRUD lista beleški bez ikakve AI vrednosti. Nema search-a.
**Šta uraditi:**
- Pinecone namespace per user: `kb_{user_id}` — pri čuvanju beleške odmah embedduj i upsertuj
- `GET /knowledge-base/search?q=...` endpoint — semantic search u user namespace-u
- Pri svakom AI pozivu (pitanje, strategija, copilot) — dohvati top-3 relevantne beleške i injektuj u kontekst kao `[MOJE BELEŠKE]` blok
- GPT-4o-mini auto-tagovanje pri čuvanju beleške (predlaže 3 taga)
- Deljenje beleški unutar kancelarije (flag `shared=True`)
- Frontend: search bar u Knowledge Base tabu, prikaz relevantnih beleški pored AI odgovora

---

### F0.4 — Voice: Whisper STT backend
**Fajlovi:** `routers/voice.py`, `static/vindex.js`, `index.html`
**Problem:** Nema server-side STT — browser Web Speech API je nepouzdan i ne radi u PWA desktop.
**Šta uraditi:**
- `POST /voice/transcribe` endpoint: prima audio blob (webm/mp4) → OpenAI Whisper API → vraća transkript
- Frontend: MediaRecorder API snima audio → šalje na backend → transkript se ubacuje u aktivni input (pitanje, copilot, nacrt)
- OpenAI TTS (`tts-1`, glas `onyx`) za čitanje AI odgovora — `POST /voice/tts` endpoint
- Voice mode toggle u UI (mikrofon ikona) — radi u svim glavnim modulima (pitanje, copilot, nacrti)
- Bonus: "Diktiraj i popuni" — glas → auto-popunjava polja predmeta/klijenta iz CRM-a

---

### F0.5 — Copilot: Kompletna servis integracija
**Fajlovi:** `routers/copilot.py`
**Problem:** Namere NACRT i ANALIZA_PREDMETA vraćaju GPT direktan odgovor umesto da pozivaju pravi drafting/analiza servis.
**Šta uraditi:**
- Svaka namera poziva odgovarajući interni endpoint:
  - `NACRT` → poziv drafting servisa sa parametrima
  - `ANALIZA_PREDMETA` → poziv matter_intel servisa
  - `STRATEGIJA` → poziv strategija endpoint-a
  - `PRETRAGE` → poziv RAG pipeline-a
- Proširiti intent detection sa 14 na 20 namera (dodati: `ZASTARELOST`, `CONFLICT_CHECK`, `BILLING`, `ROČIŠTE`)
- Prikazati korisniku: "Detektujem: Nacrt tužbe → generišem..." pre odgovora (transparency)

---

## FAZA 1 — VISOK PRIORITET (Direktan uticaj na konverziju i retenciju)

---

### F1.1 — DOCX Export nacrta + Kancelarijski header
**Fajlovi:** `routers/drafting.py`, `requirements.txt`, `static/vindex.js`
**Šta uraditi:**
- Instalirati `python-docx`
- `GET /drafting/{nacrt_id}/export/docx` endpoint — generisanje .docx fajla
- Kancelarijski header iz `firma` podešavanja: naziv, PIB, adresa, telefon, logo (ako postoji)
- Pravilna tipografija: Times New Roman 12pt, margine 2.5cm, numeracija strana
- PDF export opcija: `python-docx` → `libreoffice --headless --convert-to pdf` ili WeasyPrint
- Draft history: svaka verzija se čuva sa timestampom i napomenom u `predmet_nacrti` tabela
- Frontend: dugme "Preuzmi .docx" i "Preuzmi .pdf" pored svakog nacrta

---

### F1.2 — AKS Tarifa: 28 → 80+ stavki
**Fajlovi:** `routers/tarife.py`, `routers/billing.py`
**Šta uraditi:**
- Uneti svih 80+ stavki iz Sl. gl. RS 56/2025 (kompletna AKS tabela)
- `BOD_RSD` izvući iz env vara ili `sys_config` Supabase tabele (ne hardkodovano)
- Dodati kategorije: Prekršajni postupak, Upravni spor, Arbitraža, Međunarodni postupci
- Podstanke po tačkama (T01a, T01b) gde postoje gradacije
- Automatski sekvencijalni broj fakture: `{GODINA}/{REDNI_BROJ:04d}` (npr. 2026/0042)
- `GET /tarife/search?q=zastupanje` endpoint za brzu pretragu stavke

---

### F1.3 — Conflict Check: Fuzzy matching
**Fajlovi:** `routers/conflict_check.py`, `requirements.txt`
**Šta uraditi:**
- Instalirati `rapidfuzz`
- Normalizacija pre poređenja: ćirilica → latinica, lowercase, ukloni dijakritike, skraćenice → pune forme ("d.o.o." → "doo", "a.d." → "ad")
- Levenshtein threshold: score ≥ 85 = potencijalni konflikt, 70-84 = upozorenje
- Sloj 4 (advokat suprotne strane) proširiti — čitati i iz `predmet_beleske` i `predmet_dokumenti` nazivi
- Provera nad zatvorenim predmetima sa oznakom `[BIVŠI KLIJENT]` u rezultatu
- AI rationale: GPT objasni ZAŠTO je konflikt (npr. "Isti PIB u predmetu br. 23/2024")
- Migracija: dodati `normalized_name` kolonu u `klijenti` tabelu za brže pretraživanje

---

### F1.4 — RAG Engine: Rekalibracija + Embedding cache
**Fajlovi:** `app/services/retrieve.py`
**Šta uraditi:**
- LRU embedding cache: `functools.lru_cache` sa TTL wrapperom (1h) — isti query ne embedduj dva puta
- Po završetku 87k ingesta: rekalibracija thresholds — testirati 50 reprezentativnih pitanja, podesiti `HIGH_CONF` i `LOW_CONF` granično
- LAW_HINTS proširiti sa ~200 na ~500 ključnih reči (dodati sve oblasti iz novog corpora: krivično, porodično, radno, nasledno)
- Async CRAG: kompletno async bez `asyncio.to_thread` wrapping-a (native async Pinecone klijent)
- Pinecone hybrid search: kombinovati semantic + keyword (sparse+dense) za bolje pokrivanje

---

### F1.5 — Konverzacijska memorija
**Fajlovi:** `routers/copilot.py`, `api.py` (`/api/pitanje`), Supabase migracija
**Šta uraditi:**
- Nova Supabase tabela `ai_sessions`: `id`, `user_id`, `session_id`, `messages (JSONB)`, `created_at`, `updated_at`
- Čuvati posled 5 razmena (10 poruka) po sesiji
- `session_id` se generiše na frontendu (UUID) i šalje u svakom zahtevu
- Sesija ističe posle 2h neaktivnosti (TTL check)
- Frontend: vidljiva "konverzacijska traka" u AI Pitanju i Copilotu — korisnik vidi istoriju razgovora
- Dugme "Nova sesija" za reset konteksta
- Predmet kontekst: ako je otvoren predmet → automatski dodaj predmet metadata u system prompt

---

## FAZA 2 — SREDNJI PRIORITET (Produbljivanje postojećih funkcija)

---

### F2.1 — Auto-Evidence klasifikacija
**Fajlovi:** `routers/evidence.py`, `routers/dokument.py`
**Šta uraditi:**
- Triggeruj klasifikaciju automatski pri svakom `POST /predmeti/{id}/upload`
- Klasifikacija na osnovu punog teksta (ne samo 1500 znakova) — chunkovani pristup
- `pravni_elementi` mapirati na konkretne zakonske članove: "uzročna veza" → "čl. 155 ZOO", "odgovornost za štetu" → "čl. 154 ZOO"
- Evidence gap analysis endpoint: `GET /predmeti/{id}/evidence/gaps` — koji pravni elementi nemaju pokriće dokazima
- Bulk klasifikacija: `POST /predmeti/{id}/evidence/classify-all` za sve postojeće dokumente
- Vizuelna "matrica dokaza" u frontend-u: pravni elementi po X osi, dokumenti po Y osi, popunjenost bojom

---

### F2.2 — Procesni Rokovi + Sudski Kalendar
**Fajlovi:** `routers/zastarelost.py`, `routers/kalendar.py`, `routers/rokovi_lanac.py`
**Šta uraditi:**
- Baza srpskih državnih praznika i sudskih odmora (API iz data.gov.rs ili statički JSON koji se godišnje ažurira)
- Kalkulator radnih dana: `working_days_add(start_date, n)` — preskače vikende i praznike
- ZPP rokovi: žalbeni rok (15 radnih dana), prigovor (8 dana), revizija (30 dana)
- KZ rokovi: žalba na presudu (15 dana), zahtev za ponavljanje (30 dana)
- ZR rokovi: otkaz (8, 15, 30 dana po tipu)
- Rok lanca: svaki rok generiše listu sledećih rokova automatski — prikazati "stablo rokova"
- Sudski calendar API: sudski odmori (januar, jul-avgust) kao neradni dani u izračunu
- Frontend: interaktivno "stablo rokova" u tabu Rokovi predmeta

---

### F2.3 — Sudska Praksa Search: Keyword fallback + Kompletna lista sudova
**Fajlovi:** `routers/praksa.py`
**Šta uraditi:**
- BM25 keyword fallback: kada semantic score < 0.45, pokrenuti keyword pretragu kao backup
- Kompletna lista sudova po mreži sudova 2023 (Sl. gl. RS 101/2019): svih 66 sudova sa tačnim nazivima i sedištem
- `year` Pinecone metadata polje verifikacija — dodati u ingestion skriptu ako nedostaje
- Ratio decidendi verifikacija: posle GPT ekstrakcije, CRAG-like provera da li je zaista pravni stav
- Srodne odluke: uz svaki rezultat prikaži 2-3 odluke iz istog predmeta/materije
- Export pretrage: `GET /praksa/export?format=pdf|docx` — lista rezultata sa linkovima

---

### F2.4 — CRM: CSV Import + Duplicates guard
**Fajlovi:** `routers/` (novi fajl `import.py`), `static/vindex.js`
**Šta uraditi:**
- `POST /klijenti/import/csv` endpoint: upload CSV → mapiranje kolona → preview → potvrda → import
- Podržani formati: CSV, XLSX (openpyxl)
- Standardno mapiranje kolona: ime, prezime, email, telefon, PIB, adresa, naziv_kompanije
- Duplicates guard pre kreiranja klijenta: provera po email-u (exact) + imenu (fuzzy ≥ 90%) + PIB-u
- Ako duplikat nađen: ponuditi merge ili skip ili override
- `normalized_name` kolona u `klijenti` tabeli (indeksovana) za brzu duplikat proveru
- Predmet workflow state machine: status enum `otvoren | aktivan | u_zalbi | suspendovan | zatvoren` sa prisilnim prelaskom

---

### F2.5 — SEF: XSD Validacija + Sandbox + Prava enkripcija
**Fajlovi:** `routers/sef.py`
**Šta uraditi:**
- Skinuti SEF XSD schema (javna na sef.gov.rs) i validovati generirani UBL XML pre slanja
- Ako XSD validacija ne prođe: vratiti preciznu grešku (koji element, koji red) — ne slati SEF
- `SEF_SANDBOX=true` env var → koristi SEF testni endpoint za development/staging
- Enkriptovanje SEF API ključa: Supabase Vault ili `cryptography.fernet` (ne base64)
- Batch slanje: `POST /sef/batch` — više faktura u jednom pozivu
- Status praćenje: `GET /sef/status/{invoice_id}` — proveri status u SEF sistemu

---

### F2.6 — Billing: Proforma faktura + Unapređeni PDF
**Fajlovi:** `routers/billing.py`, `requirements.txt`
**Šta uraditi:**
- Proforma faktura: ista logika kao faktura, status `proforma`, ne šalje na SEF, konvertuje se u fakturu jednim klikom
- WeasyPrint ili ReportLab za profesionalni PDF umesto HTML rendering-a
- PDF template: zaglavlje sa logoim firme, QR kod za SEF verifikaciju, elektronski potpis placeholder
- Automatski email kada faktura kasni > 30 dana (payment reminder)
- Recurring billing: za klijente na mesečnom retejneru — automatsko generisanje fakture

---

### F2.7 — Notifikacije: Real-time + Prošireni tipovi
**Fajlovi:** `routers/notifications.py`, `static/vindex.js`
**Šta uraditi:**
- Supabase Realtime subscription (WebSocket) umesto polling svakih 6h — instant notifikacije
- Novi tipovi notifikacija: nova poruka u inboxu, saradnik dodelio zadatak, faktura plaćena, SEF status
- iOS Safari push verifikacija (VAPID + Service Worker manifest na Safari 16.4+)
- Notifikacija priority levels: URGENT (rok sutra), HIGH (rok 3 dana), NORMAL (obaveštenje)
- Grupovanje notifikacija: "5 rokova ove nedelje" umesto 5 posebnih notifikacija
- "Tihi period" podešavanja: ne slati push između 22:00 i 08:00

---

### F2.8 — Hearing CC: Privrednopravni + RAG + Cross-examination
**Fajlovi:** `routers/hearing_cc.py`
**Šta uraditi:**
- 5. tip system prompta: Privredni sud (ZPD čl., ZOSL, Zakon o privrednim društvima specifičnosti)
- RAG injektovanje: pre generisanja brifinga, dohvati top-5 relevantnih odluka iz Pinecone-a za dati predmet
- Uploadovani dokumenti predmeta kao dodatni kontekst u brifingu
- Cross-examination generator: poseban endpoint `POST /hearing-cc/cross-exam` → lista pitanja za svedoke/vještake
- Checklistu za ročište: šta poneti, šta proveriti, rokovi do ročišta
- Export brifinga: .docx sa celom pripremom za ročište

---

### F2.9 — Multi-agent: RAG integracija + Pipeline orkestracija
**Fajlovi:** `routers/multi_agent.py`
**Šta uraditi:**
- Research Agent direktno poziva RAG retrieve pipeline (ne GPT bez konteksta)
- Billing Agent prima `billing_entries` za predmet iz DB-a pre odgovora
- Agent pipeline: mogućnost sekvencijalnog lanca — "Intake → Research → Draft" u jednom toku
- Svaki agent vraća `suggested_next_agent` (sugestija koji agent treba sledeći)
- Inter-agent memory: rezultat prethodnog agenta dostupan sledećem u lancu
- Agent sessions: čuvati konverzaciju sa svakim agentom posebno (Supabase)

---

### F2.10 — Strategija: Win-rate kalibracija + Novi corpus
**Fajlovi:** `routers/strategija.py`
**Šta uraditi:**
- Litigation Simulator % kalibrisati sa Outcome Intel podacima (stvarni predmeti kancelarije)
- Posle 87k ingesta: ažurirati sve strategija prompts da uključe novi `sudska_praksa` namespace
- Zajednički `_fetch_praksa_ctx` helper funkcija (eliminisati duplikate across modula)
- Dodati Privredni postupak kao 5. tip u Red Team analizi
- AI Sudija v2: uključi konkretne sudske odluke iz Pinecone-a kao osnov procene
- Witness Analyzer: proširiti sa cross-examination pitanjima

---

## FAZA 3 — STRATEŠKI RAZVOJ (Tržišna dominacija)

---

### F3.1 — AI Court Predictor
**Novi modul — killer feature koji niko u regionu nema**
**Šta uraditi:**
- Analiza faktora: sud + sudija (ako poznat) + materija + vrednost + procesna istorija
- Na osnovu 95k odluka: statistička analiza ishoda po parametrima (win rate % po materiji po sudu)
- GPT-4o za narativnu procenu + statistički podaci iz corpora
- Confidence interval prikaz (ne samo %, nego i raspon)
- "Faktor osetljivosti": šta bi promenilo ishod (npr. "Viši sud u Beogradu drugačije sudi ovu vrstu")
- Disclamer pravne odgovornosti

---

### F3.2 — Proširenje RAG baze: 95k → 500k dokumenata
**Šta uraditi:**
- Ingesta ministarskih mišljenja (Ministarstvo pravde, finansija) — javno dostupni
- Komentari zakona iz naučnih časopisa (JPPKP, CRIMEN) — uz dozvole
- EU direktive i uredbe na srpskom (transponovane)
- EU MiCA regulativa za Web3 modul
- Sl. glasnik RS — svi zakoni u prečišćenom tekstu (scraper ili API)
- Sudska praksa nižih instanci (Osnovni sudovi) — dogovor ili manual ingesta
- Ažuriranje ECHR klastera (610500-611309) posle završetka glavnog crawla

---

### F3.3 — Onboarding Flow + Free Trial
**Fajlovi:** novi `routers/onboarding.py`, `index.html`, `static/vindex.js`
**Šta uraditi:**
- 30-dnevni free trial sa guided setup (5 koraka)
- Korak 1: Unesi ime kancelarije + logo
- Korak 2: Importuj ili unesi prvog klijenta
- Korak 3: Kreiraj prvi predmet
- Korak 4: Probaj AI pitanje (sa primerima)
- Korak 5: Podesi notifikacije
- Progress tracker u sidebar-u tokom onboarding perioda
- Day 1, Day 3, Day 7 onboarding emailovi (welcome + tutorial + feature spotlight)
- Conversion nudge: na dan 25 od 30 — ponuda za upgrade sa popustom

---

### F3.4 — Javna landing page sa cenama
**Šta uraditi:**
- Kreirati `/pricing` stranicu (ili poboljšati postojeću)
- Jasno prikazati 3-4 plana: Free trial / Advokat / Kancelarija / Enterprise
- Feature comparison tabela: šta ima koji plan
- FAQ sekcija: odgovori na top 10 pitanja pre kupovine
- Social proof: testimonijali, broj korisnika, broj analiziranih predmeta
- CTA: "Počni besplatno" (30 dana, bez kreditne kartice)

---

### F3.5 — Enterprise tier (kancelarije 20+ advokata)
**Šta uraditi:**
- Centralizovani admin panel za managing firme: korisnici, uloge, statistike
- Bulk seat management: dodaj/ukloni advokata, prenos predmeta
- Per-lawyer analytics: ko koliko koristi sistem
- Shared knowledge base na nivou firme
- Custom billing: konsolidovana faktura za firmu
- SSO integracija (SAML/OAuth za corporate identity providers)
- SLA i dedicated support

---

### F3.6 — Saradnja: Audit log + Temp access
**Fajlovi:** `routers/saradnja.py`
**Šta uraditi:**
- `predmet_audit_log` tabela: ko, šta, kada — svaka akcija na predmetu loguje se
- Temp access: saradnik dobija pristup sa datumom isteka (npr. "pristup do 15.07.2026")
- Push/email notifikacija saradniku pri dodavanju na predmet
- Fine-grained permissions: čitanje / komentarisanje / editovanje / brisanje posebno
- Activity timeline po saradniku: vidljivo vlasniku

---

### F3.7 — Integracioni hub
**Fajlovi:** `routers/integracije.py`
**Šta uraditi:**
- Webhook system: korisnik može podesiti webhook URL koji prima evente (novi predmet, rok, faktura)
- Zapier/Make.com integracija (no-code automation)
- Google Calendar dvosmerna sinhronizacija (import/export ročišta)
- Microsoft Outlook Calendar sync
- Clio webhook import (za advokate koji prelaze sa Clio-a)
- REST API dokumentacija (Swagger/OpenAPI) javno dostupna

---

### F3.8 — Mobilna optimizacija PWA
**Fajlovi:** `index.html`, `static/vindex.css`, `static/vindex.js`
**Šta uraditi:**
- Audit svakog ekrana na mobilnom (375px, 390px, 414px viewport)
- Bottom navigation bar na mobilnom (umesto sidebar-a)
- Touch-friendly: minimum 44px tap targets, swipe geste za tabove
- Offline mode: predmeti i klijenti čitljivi bez interneta (Service Worker cache strategy)
- Camera input za upload dokumenata (direktno fotografisanje)
- Voice dictation optimizacija za mobilni (iOS + Android)

---

## LEGENDA PRIORITETA

| Simbol | Značenje |
|---|---|
| 🔴 | Kritično — broken ili blokira korisnike |
| 🟡 | Visok — direktan uticaj na konverziju/retenciju |
| 🟢 | Strateški — tržišna dominacija, dugoročno |

## REDOSLED IMPLEMENTACIJE (bez vremenskih procena)

```
F0.1 → F0.2 → F0.3 → F0.4 → F0.5
  ↓
F1.1 → F1.2 → F1.3 → F1.4 → F1.5
  ↓
F2.1 → F2.2 → F2.3 → F2.4 → F2.5
  ↓
F2.6 → F2.7 → F2.8 → F2.9 → F2.10
  ↓
F3.1 → F3.2 → F3.3 → F3.4 → F3.5
  ↓
F3.6 → F3.7 → F3.8
```

**Uvek: završi tekuću fazu pre nego što pređeš na sledeću.**
**Uvek: nakon svake implementacije — testirati, deployjati, dobiti feedback.**
