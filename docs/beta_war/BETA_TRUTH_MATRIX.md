# VINDEX AI — BETA TRUTH MATRIX

Stanje: `HEAD b984a039`, radno stablo **DIRTY** (`landing.html`, `strategija.py` nekomitovani).
Talas 1, read-only. Nijedan fajl nije menjan, nijedna migracija pokrenuta, nijedan naplativi poziv.

**Status dokumenta: KOMPLETAN za Talas 1** — uneseni domeni A, B, C, D, E, F.

> **Ovo je SNIMAK stanja na dan 2026-08-10, ne živi dokument.**
> Vrednost matrice je u tome što beleži šta je tačno bilo istinito u trenutku merenja, pri `HEAD b984a039`.
> Napredak na zatvaranju P0 stavki se prati odvojeno, u `docs/beta_war/P0_CLOSURE_LEDGER.md` — ovaj fajl se
> ne prepravlja kako se stavke zatvaraju. Ispravljanje evidencije unazad bi uništilo ono zbog čega postoji.

Klasifikacija: **P0** = blokira betu · **P1** = rizik u beti · **P2** = posle bete · **P3** = istraživanje.
Dokaz: `PROVEN` = potvrđeno iz koda · `PARTLY` = delimično · `UNVERIFIED — REQUIRES DB` = granica bez `SUPABASE_DB_URL`.

---

## 1. KONVERGENCIJE — nalazi koje su dva nezavisna specijalista pogodila odvojeno

Ovo su najjači nalazi u matrici: dva agenta bez međusobne komunikacije stigla do istog mesta.

| # | Nalaz | Ko je našao | Zašto je konvergencija bitna |
|---|---|---|---|
| **K-1** | `static/vindex.js:3590` šalje **samo** `opis_predmeta`; `dokumenti` i `iskazi_svedoka` nikad ne stignu | **B** (ugovor obećanja) + **D** (grounding) | B je to našao gledajući šta landing obećava; D gledajući šta model prima. Isti red koda, dva pravca. |
| **K-2** | Migracija 107 je primenjena u bazi, ali **Python ispravka `0561e6c` nije potvrđena u deploy-u** — pa kreditna trka može biti i dalje otvorena | **E** (naplata) + **F** (release) | Oba su udarila u isti zid nezavisno: SQL je dokazan, build nije. Migracija bez odgovarajućeg build-a ne zatvara ranjivost. |
| **K-3** | Tri nezavisna izvora istine o tarifama: `landing.html`, `feature_registry`/`tier_config` u bazi, i `is_pro` boolean u frontendu | **B** + **E** | Krši „1 koncept = 1 vlasnik = 1 istina" iz Core Consolidation. |
| **K-4** | Skripte na disku prave naplative pozive i pišu u **produkcioni** Pinecone bez ikakvog nadzora | **C** (16 neverzionisanih dijagnostičkih skriptova) + **F** (nema izolovanog okruženja) | C je našao izvršioce, F je našao razlog zašto gađaju produkciju. Zajedno objašnjavaju ranije zabeležen incident „testovi su brisali iz produkcionog Pinecone-a". |
| **K-5** | `static/vindex.js:3590` — treći nezavisni pogodak na isti red | **A** (tok 7) uz **B** i **D** | Tri specijalista, tri različita ugla (obećanje / grounding / korisnički tok), jedan red koda. Najbolje potkrepljen nalaz u celoj matrici. |

### Ispravka moje ranije tvrdnje

U ranijim izveštajima sam tvrdio da je **`openai` jedini uvezen SDK** i da monkey-patch nad `Completions.create` daje strukturnu pokrivenost svih pozivnih mesta. **Netačno.** `cohere` je živ produkcijski provajder — `app/services/retrieve.py:34` (import), `:1265` (`co.rerank`), 4 pozivaoca — potpuno van patch-a. Pokrivenost je **62% prompt guard / 67% audit**, ne strukturna.

---

## 2. MATRICA PO DOMENIMA

| Domen | Status | Dokaz | Rizik |
|---|---|---|---|
| **Komercijalni ugovor** (cenovnik, planovi, kupovina) | **FAILED** | `landing.html:1022-1094` vs `migrations/068_tier_config.sql:77-82` | P0 |
| **Naplata — atomičnost u bazi** | PARTLY | `migrations/107,108`; 59 testova preskočeno | P0 |
| **Naplata — trenutak odbitka** | **FAILED** | 21/116 poziva naplaćuje pre posla, 17 bez refunda | P0 |
| **Release governance / migracije** | **FAILED** | nema tabele verzija, nema runnera, drift dokazan | P0 |
| **Izolacija okruženja** | **FAILED** | jedan Supabase projekat za dev i produkciju | P0 |
| **Identitet build-a u produkciji** | **FAILED** | nijedan endpoint ne izlaže verziju ni git SHA | P0 |
| **Strategic Orchestrator (flagship PRO)** | **FAILED** | 5/6 modula; nijedan korak ne vidi i opis i dokumente | P0 |
| **Provenance / poreklo konteksta** | **FAILED** | `source` se odbacuje kod svih 9 potrošača | P1 |
| **RAG — `izvori` ugovor** | **FAILED** | `izvori` = rezultati pretrage, ne citati odgovora | P1 |
| **Prompt kontaminacija propisima** | PARTLY | 2 očišćena (nekomitovano), 4 nisu | P1 |
| **Confidence signal** | **FAILED** | korisnikov dokument diže confidence na HIGH | P1 |
| **PRO gating konzistentnost** | **FAILED** | `is_pro` (FE) vs `subscription_type` (BE) | P1 |
| **Audit — čitljivost za korisnika** | **FAILED** | audit se piše, nijedna korisnička ruta ga ne čita | P1 |
| **Transakcione granice** | **FAILED** | nula `BEGIN/COMMIT` u celoj aplikaciji | P1 |
| **Web3 / Compliance kao PRO** | **FAILED** | traži zaseban addon, PRO dobija 403 | P1 |
| **SLA 99.9%** | **FAILED** | uptime se ne meri nigde | P1 |
| **Onboarding (prvi ekran novog korisnika)** | **FAILED** | `apiFetch` nije definisan; sva 4 CTA inertna | P0 |
| **Izrada nacrta → trajni zapis** | **FAILED** | `predmet_id` se ne šalje; `staging_memory` prazan | P0 |
| **Cross-doc analiza** | **FAILED** | namespace neslaganje → uvek 422 | P0 |
| **Poruka o nedostatku kredita** | **FAILED** | 7 od ~51 mesta; `[object Object]` | P0 |
| **Registracija rutera** | PROVEN OK | svih 111 registrovano, nema mrtvog rutera | — |
| **Frontend → ruta razrešivost** | PROVEN OK | svih 292 `fetch()` putanja pogađa postojeću rutu | — |
| **Export (PDF/ZIP/DOCX/CSV/ICS)** | **PROVEN OK** | jedini tok koji prolazi ceo lanac bez prekida | — |
| **AI governance pokrivenost** | **FAILED** | 62% guard / 67% audit; 29 mesta bez audita | P0 |
| **Glasovna modalnost (Vindex Live)** | **FAILED** | sirov WSS, nula audita nad privilegovanim razgovorom | P0 |
| **Osmotrivost audit sloja** | **FAILED** | 6 mesta guta izuzetak na `logger.debug` | P0 |
| **Obrada greške na AI pozivima** | PARTLY | 8 mesta bez ijednog handlera, 2 u produkcionom procesu | P1 |
| **Cross-tenant autorizacija** | PROVEN OK | 10 nezavisnih sweep-ova (V49–V58), nula nalaza | — |
| **Neograničen retry** | PROVEN OK | 0 mesta; `stop_after_attempt(3)` svuda | — |
| **RPC lockdown (102/103)** | PROVEN | posredno, `docs/beta_gate/`, 2026-08-08 | — |
| **RLS lockdown (110)** | PROVEN | `docs/beta_gate/MIGRATION_110_VERIFICATION.md` | — |

---

## 3. P0 — BLOKIRA BETU

### BTM-P0-01 · Naplata pre isporuke, bez povraćaja — 17 mesta
**GDE** `routers/web3.py:573` (5 kredita), `routers/source_of_funds.py:72` (2), `routers/case_dna.py:1067` (3, sa 7 `await`-a posle naplate), `routers/zastarelost.py:476`, `routers/voice.py:541`, `routers/cio.py:671,759`, `routers/drafting.py:662,708`, `api.py:4483,5731`
**ŠTA** AST analiza 116 stvarnih `UsageService.consume` poziva: 21 naplaćuje pre awaited posla, **17 nema nikakav refund**. Na grešci ide 500, krediti ostaju potrošeni.
**ZAŠTO** Refund uopšte postoji za **3 feature key-a od 71** (`ai_pravna_pitanja`, `copilot`, `predmet_upload_ai`).
**DOKAZ** PROVEN · **RIZIK** Advokat plaća i ne dobija ništa. Najskuplji slučaj: 5 kredita.

### BTM-P0-02 · Nulti mehanizam praćenja primenjenosti migracija
**GDE** `migrations/` (101 fajl), `migrations/110_rls_lockdown_idempotent.sql:5-11`
**ŠTA** Nema `schema_migrations` tabele, nema runnera, nema changeloga. Migracije se ručno lepe u Supabase SQL Editor.
**ZAŠTO JE DOKAZANO, NE TEORIJSKI** `017_scraper_state.sql` **nikad nije primenjen** — otkriveno tek kad je migracija 109 pukla na `discovered_bilteni`, **93 migracije kasnije**. Repo je 100+ migracija verovao da je 017 primenjen.
**DOKAZ** PROVEN · **RIZIK** Primenjenost bilo koje od 101 migracije se ne može utvrditi iz repoa.

### BTM-P0-03 · Nijedno izolovano okruženje — sve je produkcija
**GDE** `.env` (14 ključeva, bez `ENVIRONMENT`), `api.py:46`
**ŠTA** Jedan `SUPABASE_URL`, jedan servisni ključ, jedna baza za dev i produkciju. `ENVIRONMENT` se čita **samo** kao Sentry tag i ne grana nijednu odluku. Nula pogodaka za `DEBUG/IS_PROD/APP_ENV/NODE_ENV/VINDEX_ENV`.
**DOKAZ** PROVEN · **RIZIK** Svaki lokalni test piše u produkcionu bazu. Ovo je uzrok, ne posledica — objašnjava zašto su testovi ranije brisali iz produkcionog Pinecone-a.

### BTM-P0-04 · Nemoguće utvrditi koji build vrti produkcija
**GDE** `api.py:1536-1545` (`/health` vraća `status/pid/redis/workers`)
**ŠTA** Nula `GIT_SHA / COMMIT_SHA / BUILD_ID / APP_VERSION` u celom backendu. Jedini de-facto marker je `static/sw.js:4` (`vindex-v119`), nedostupan preko API-ja.
**ZAŠTO JE P0** Tri CRITICAL/HIGH ispravke kreditne trke su u **Python** kodu (`0561e6c`, `4e6e4f1`), ne u SQL-u. Ako produkcija vrti stariji build, putanja od 1 kredita — dominantna cena za `ai_pravna_pitanja`, `copilot`, `strategija` i ~25 drugih — **ostaje eksploatabilna uprkos primenjenoj migraciji 107**.
**DOKAZ** PROVEN (odsustvo) + UNVERIFIED — REQUIRES DEPLOY ACCESS
**NAPOMENA** Ovo je direktan nastavak incidenta „Focus IP Core Engine": jedini način da se aplikacija identifikuje bez izmene koda je `GET /openapi.json` → `info.title`, što je slučajnost, ne namera.

### BTM-P0-05 · Javni cenovnik ne postoji u backendu
**GDE** `landing.html:1022-1094` vs `migrations/068_tier_config.sql:77-82`, `shared/tier_config.py:31-35`, `migrations/063_entitlement_system.sql:31`
**ŠTA** Landing prodaje 4 plana (Besplatno €0 / Advokat €49 / Pro €89 / Firma €59-seat). Baza zna 3 (`basic` €29 / `professional` €79 / `enterprise` €249), a `CHECK` constraint **fizički zabranjuje četvrtu vrednost**. Aplikacija posle registracije prikazuje DRUGE nazive i DRUGE cene (`static/vindex.js:7820,8012`).
**PODNALAZ** Plan „Advokat" (€49) prodaje `10 analiza dokumenata` i `Nacrti i podnesci` — backend obe gejtuje na `professional` (`migrations/064_feature_registry.sql:106,108`). Kupac bi dobio 403 na obe.
**DOKAZ** PROVEN · **RIZIK** Javna strana **danas**. Ovo je isti razred kao P0 iz `VINDEX_AI_CURRENT_PUBLIC_CLAIMS_AUDIT.md`, ali teži: nije preterivanje, nego cena koju sistem ne može naplatiti.

### BTM-P0-06 · „X AI upita mesečno" nije mesečno
**GDE** `api.py:356` (`BESPLATNI_KREDITI=15`), dodela `api.py:2440`
**ŠTA** 15 kredita se dodeli **jednom** pri registraciji i samo se troši. Nema `pg_cron`, nema reset/refill job-a nigde u `migrations/` ni `workers/`.
**DOKAZ** PROVEN · **RIZIK** Sva tri plaćena plana obećavaju mesečnu kvotu koja se nikad ne obnavlja.

### BTM-P0-07 · Strategic Orchestrator — flagship PRO — radi 5/6 modula i ne vidi dokumente
**GDE** `static/vindex.js:3590` → `routers/strategija.py:364,399` → `strategija.py:666,676,686`
**ŠTA — tri odvojena kvara u istom lancu:**
1. `iskazi_svedoka` se nikad ne šalje → Witness korak uvek pada u skip granu (`strategija.py:701-710`). **Potvrđeno stvarnim run-om TEST-3F.**
2. `dokumenti` se nikad ne šalje → „Legal Audit" i „Due Diligence" analiziraju opis predmeta. `index.html:1133` doslovno tvrdi „čitaju vaše dokumente i činjenice automatski".
3. **Čak i kad bi se dokumenti slali:** `strategija.py:666,676` odbacuju `opis_predmeta` čim `dokumenti` postoje. **Nijedan korak u celom lancu nikada ne vidi i opis i dokumente istovremeno.** Red Team, obe strane debate, presuda i sinteza rezonuju o predmetu čije dokumente nisu videli.
**DOKAZ** PROVEN (B i D nezavisno) · **RIZIK** Najskuplja funkcija (6× multiplier) radi na najtanjem ulazu.

### BTM-P0-08 · Glasovna modalnost je potpuno van audit površine
**GDE** `services/voice_orchestrator.py:246`
**ŠTA** `websockets.connect("wss://api.openai.com/v1/realtime")` — sirov WebSocket, ne SDK. Monkey-patch ga fizički ne može videti. **Nula prompt guard-a, nula provenance-a, nula `log_action`.** Nijedan `ai_forensics` red ne postoji ni za jednu Vindex Live sesiju.
**ZAŠTO JE P0 ZA OVAJ PROIZVOD** Kanal nosi advokatov **izgovoreni privilegovani razgovor sa klijentom** plus Whisper transkript. Za pravni proizvod je to najosetljiviji podatak koji sistem uopšte dodiruje, i jedini je AI kanal bez ijednog traga.
**DOKAZ** PROVEN · **RIZIK** Nemoguće odgovoriti na pitanje „šta je AI video iz mog razgovora sa klijentom".

### BTM-P0-09 · Governance je fail-open i nije osmotriv
**GDE** `shared/ai_client.py:338-341`
**ŠTA** Ako import `Completions` klasa pukne, kod loguje `logger.error`, **postavi `_guard_patched = True`** i vrati se. Aplikacija dalje radi sa nula guard-a i nula provenance-a za **svih 83 pokrivenih mesta**. Zastavica se ne čita nigde — nema health check-a, nema metrike.
**PRIDRUŽENO** 6 mesta guta izuzetak audit sloja na `logger.debug`: `security/ai_forensics.py:325-326` (svaki neuspeh upisa provenance-a), `shared/ai_client.py:223,278,423,480`, `shared/ai_fabric.py:661`.
**DOKAZ** PROVEN · **RIZIK** Pokrivenost auditom se **ne može potvrditi u radu**. Ako svaki upis u `ai_forensics` pada, jedini trag je `DEBUG` linija. Ovo je isti razred kao ranije zabeleženo „declared ≠ enforced control".

### BTM-P0-10 · 29 AI pozivnih mesta bez audita, 16 njih nevidljivo gitu
**GDE** 7 samostalnih ingest skriptova + 1 cohere (`retrieve.py:1265`) + 1 realtime WSS + 4 samostalna LangChain + **16 neverzionisanih dijagnostičkih skriptova** (`diag_*.py`, `scripts/ingest_sudskapraksa.py:204`, `scripts/proof_direct.py:126` …)
**ŠTA** Skripte nisu u gitu, ali su **na disku, izvršive**, prave naplative pozive i **pišu u produkcioni Pinecone**. Nula governance-a, nula audita. Svaki inventar zasnovan na `git ls-files` ih propušta.
**DOKAZ** PROVEN · **RIZIK** Uz `BTM-P0-03` (nema izolovanog okruženja) ovo je kompletan uzročni lanac ranijeg incidenta sa brisanjem iz produkcionog Pinecone-a.

### BTM-P0-11 · Ceo onboarding je inertan — **verifikovao koordinator lično**
**GDE** `static/vindex.js:15487-15494` (`onboardingDismiss`), `:15510-15511` (`onboardingStep`), `:15497-15499` (`checkTrialStatus`); dugmad `index.html:2444,2458,2472,2496`
**ŠTA** `onboardingStep()` u **prvoj liniji** zove `onboardingDismiss()`. Ta funkcija sakrije overlay (`:15489`), prođe `if (!currentUser) return` (korisnik JESTE prijavljen tokom onboardinga), i na `:15494` pogodi **`apiFetch` — funkciju koja ne postoji**. `ReferenceError` se baca sinhrono na poziciji poziva, pa ga priloženi `.catch()` ne hvata. `onboardingStep` prekida pre `:15512` — **navigacija se nikad ne izvrši.**
**KORISNIČKI ISHOD** Novi advokat klikne „Počnimo →" ili bilo koju od 3 kartice. Overlay nestane. **Ništa se ne desi.** `/api/auth/onboarding/complete` se nikad ne pozove. `checkTrialStatus()` umire isto → `#trial-badge` je trajno skriven.
**MOJA VERIFIKACIJA** `grep -rn "apiFetch"` po celom repou → **2 poziva, 0 definicija**. Pogoci: `vindex.js:15494`, `vindex.js:15499`, plus `vindex.js.bak:12416,12421` (defekt je stariji od tekuće verzije fajla).
**OVO ISPRAVLJA RANIJU CERTIFIKACIJU** `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md:3324-3329` (Program Lambda, Certification 007) zaključuje: *„dva nezavisna onboarding sistema, jedan živ, jedan orphan"* — i kao „živ" navodi baš ovaj `apiFetch` poziv. **Netačno: živ nije nijedan.** `routers/onboarding.py` je orphan, a `api.py:2424` se ne doseže jer pozivalac puca. Certification 007 je ocenio ovo kao `Severity: Low — dead code`; stvarna ozbiljnost je P0 na prvom ekranu koji novi korisnik vidi.
**DOKAZ** PROVEN (koordinator, ne samo agent)

### BTM-P0-12 · Nacrti se nikad ne upisuju u predmet
**GDE** `vindex.js:7390-7395` naspram `vindex.js:7386`; `drafting.py:670,1019`
**ŠTA** `predmet_id` je **jedini** ulaz u `_stage_draft_for_review` — jedinog pisca u `staging_memory`. Telo za pitanja (`_qBody`, `:7386`) ga šalje: `if (activePredmetId) _qBody.predmet_id = activePredmetId;`. Telo za nacrte (`:7390`) ga **ne šalje**, iako je `activePredmetId` u istom dosegu, devet linija niže.
**POSLEDICA** Nijedan AI nacrt ne uđe u trajni zapis predmeta. Ekran za overu je strukturno prazan i `_stagingLoad` se tiho sakrije (`vindex.js:21654`). Komentar u samom frontendu (`vindex.js:21631`) tvrdi *„every AI-generated draft … was staged automatically"* — ta tvrdnja je netačna.
**DOKAZ** PROVEN

### BTM-P0-13 · Cross-doc analiza nad dokumentima predmeta ne može uspeti
**GDE** `cross_doc.py:337-340,313`; `dokument.py:123,163`; `api.py:4626,4760,4809`
**ŠTA** Dokumenti predmeta se ingestuju u `_owner_ns` (`kancelarija_{id}` / `user_{id}`). `cross_doc` skida prefiks `"session/"` i zove `_fetch_session_tekst`, čiji je default `namespace_prefix="tmp_"`, a fallback je uklonjen 2026-08-09. Obe grane razrešavaju u nepostojeći namespace → prazan tekst → **422, uvek**.
**DODATNO** Potreban tekst leži u `predmet_dokumenti.tekst_sadrzaj`, koji `cross_doc.py:313` ne selektuje. Docstring na `dokument.py:125` još tvrdi *„falls back to the other prefix"* — zastareo.
**DOKAZ** PROVEN

### BTM-P0-14 · Otvaranje Podešavanja troši kredit za operaciju bez AI — **verifikovao koordinator**
**GDE** `vindex.js:2003` → `:2265 settingsLoad()` → `:2278` bezuslovno `confidenceAuditLoad()` → `:2348` fetch → `routers/confidence_audit.py:47`
**ŠTA** Nema dugmeta, nema potvrde, nema 402 grane. Otvaranje taba Podešavanja naplaćuje 1 kredit.
**MOJA VERIFIKACIJA** `migrations/064_feature_registry.sql:102` → `('confidence_audit', 'AI Pouzdanost / Confidence Audit', 'kvalitet', 'professional', NULL, 1, …, 'gpt-4o-mini', NULL)` — **1 kredit**. `routers/confidence_audit.py:47` poziva `UsageService.consume(...)`.
**DVA DODATNA SLOJA KOJE JE MERENJE OTKRILO**
- Feature je gejtovan na `professional` (`confidence_audit.py:38`), pa korisnik na `basic` tarifi dobija **403 pri otvaranju Podešavanja**.
- Registry deklariše model `gpt-4o-mini`, a `services/confidence_auditor.py` ne sadrži **nijedan** AI poziv — čist Brier proračun nad bazom. Registry je netačan o samoj prirodi funkcije.
**DOKAZ** PROVEN (koordinator)

### BTM-P0-15 · Advokat bez kredita ne dobija poruku o kreditima
**GDE** `vindex.js:546-555` (`_friendlyErr`); jedine 402 grane: `:3599, 5043, 5329, 5466, 7463, 9003, 10378` (poslednja u mrtvom kodu)
**ŠTA** Od ~51 poziva koji troše kredite, **7** ima 402 granu. Ostali rade `throw new Error(errD.detail || …)` — ali `detail` je dict `{code:"NO_CREDITS", message:…}`, pa `e.message` postane **`"[object Object]"`** i pada u catch-all: *„Radnja nije uspela. Pokušajte ponovo…"* — dok dugme pored i dalje piše „(3 kredita)".
**DOKAZ** PROVEN · Ispravan obrazac postoji **tačno jednom** (`vindex.js:5329` čita `errData.detail.message`) i nije proširen.

---

## 4. P1 — RIZIK U BETI

| # | Nalaz | `fajl:linija` | Dokaz |
|---|---|---|---|
| **P1-01** | **`izvori` su rezultati pretrage, ne citati odgovora.** Nema veze između `resp["izvori"]` i teksta odgovora. Praksa, mišljenja, korisnikov dokument i kancelarijski pasusi ulaze u kontekst modela ali **nikad** u `izvori` | `retrieve.py:712-730,2085`; `api.py:1429` | PROVEN |
| **P1-02** | **Provenance se odbacuje kod svakog potrošača.** Nula `.get("source")` poziva van mrtvog `ai_fabric.py:217`. Umesto stvarnog `source`-a, promptovi nose **hardkodovane literale** („kanonski izvor", „ne izmišljaj novu") koji ne prate polje | `court_predictor.py:208-251`, +8 modula | PROVEN |
| **P1-03** | **Korisnikov dokument diže confidence.** `DOC_GATE_BIAS` podiže band LOW→MEDIUM→HIGH na osnovu skora korisnikovog sopstvenog dokumenta (≥0.5) | `main.py:3233-3251` | PROVEN |
| **P1-04** | `confidence = "HIGH"` bezuslovno kad je član pronađen u korpusu, bez semantičke relevantnosti; uz to gasi halucinacijski i topic-drift guard | `main.py:3347,3542,3554` | PROVEN |
| **P1-05** | Kontaminacija propisima ostaje u **4 prompta**: Due Diligence (`:483,485,496,497`), Presuda (`:558`), Sinteza (`:583`), + `_RED_TEAM_*`/`_WITNESS_*` van orkestratora. **Nema nikakve provere citata u celom `strategija.py`** | `strategija.py` | PROVEN |
| **P1-06** | Tehnička greška parsiranja postaje „analiza": `{"error":…, "raw": raw[:300]}` se `json.dumps`-uje u `kontekst` i prosleđuje svim narednim koracima | `strategija.py:641,673,683,711,720` | PROVEN |
| **P1-07** | Off-spec `izreka` se **zamenjuje fabrikovanom** `"TUZBA DELIMICNO USVOJENA"`, koja ide i u kontekst i u DC-011 pravilo i u odgovor advokatu | `strategija.py:768-769,781,876` | PROVEN |
| **P1-08** | Sinteza ne vidi argumente **nijedne** strane — `tuzilac_txt`/`branilac_txt` se ne dodaju u `kontekst`, samo presuda | `strategija.py:779-782` | PROVEN |
| **P1-09** | Copilot ne poziva `build_case_context` — gubi dokaze, gapove, readiness, risk, rokove, akcije, kontradikcije; čita `case_dna` sirovo pa Genome označen kao neispravan tretira kao čist | `copilot.py:359-466,417` | PROVEN |
| **P1-10** | Nula transakcionih granica u celoj aplikaciji. Odbitak, mesečni brojač, dnevni brojač i AI rad su 4 nezavisne operacije | `shared/deps.py:83-94` | PROVEN |
| **P1-11** | 59 preskočenih testova = **ceo dokazni lanac atomičnosti naplate se ne izvršava**. Ostali kreditni testovi mock-uju RPC → validiraju ugovor koji kod OČEKUJE, ne onaj koji baza NUDI. Ista slepa tačka koja je pustila ranjivo telo `deduct_n_credits` u produkciju uz zeleni CI | `tests/test_beta_gate_credit_race_postgres.py:64-92` | PROVEN |
| **P1-12** | Dva izvora prava pristupa: FE gejtuje na `is_pro`, BE na `subscription_type`; nema koda koji ih sinhronizuje | `vindex.js:318,3084,3564` vs `shared/permissions.py:91-99` | PROVEN |
| **P1-13** | „Audit log + Export" kao PRO stavka ne postoji kao PRO funkcija — audit se piše u 2 tabele, nijedna korisnička ruta ga ne čita; export je otvoren svima i ne sadrži audit | `routers/data_export.py:66,88-97` | PROVEN |
| **P1-14** | Web3/Compliance označen „PRO" traži zaseban `digital_assets` addon → PRO korisnik dobija 403 | `migrations/064:150-158`; `shared/permissions.py:167-176` | PROVEN |
| **P1-15** | `/openapi.json` javno dostupan (`openapi_url` nije `None` iako `docs_url`/`redoc_url` jesu) — otkriva ~508 ruta neautentifikovano | `api.py:555` | PROVEN |
| **P1-16** | Produkciona deploy konfiguracija (Render) nije u repou; `railway.toml` i `Procfile` opisuju dva protivrečna deploy puta | odsustvo `render.yaml` | PROVEN |
| **P1-17** | Telo funkcija migracije 108 nije verifikovano — dokazano samo da funkcije postoje | `docs/beta_gate/CREDIT_INVARIANTS.md:53-65` | UNVERIFIED — REQUIRES DB |
| **P1-18** | Overage cene (€0.15/€0.50/€1.50) se ne naplaćuju — hard 402 umesto naplate | `shared/usage.py:396-401` | PROVEN |
| **P1-19** | SLA 99.9% se ne meri — status page radi samo trenutne probe, nema uptime istorije | `routers/status_page.py:44-76` | PROVEN |
| **P1-20** | Brojač upotrebe se inkrementira **pre** naplate → odbijena naplata (402) ipak troši dnevni/mesečni limit | `shared/usage.py:385-394` | PROVEN |
| **P1-21** | `refund_n_credits` je bezuslovni `+p_n` bez gornjeg limita — svaka buduća dupla-refund grana kuje kredite | `migrations/107:132-136` | PROVEN |
| **P1-22** | Dedupe pokriva 1 od ~116 naplatnih putanja i samo unutar jednog worker procesa; dupli klik na svemu ostalom naplaćuje dvaput **namerno** | `routers/jobs.py:49-55`; `shared/deps.py:609-612` | PROVEN |
| **P1-23** | Izgubljen odgovor na `deduct_n_credits` → tiha naplata bez isporuke, bez automatske rekonsilijacije, samo log marker | `shared/deps.py:602-618` | PROVEN |
| **P1-24** | `migrations/109` ostaje izvršiv `.sql` fajl; jedina zaštita je komentar `⚠ SUPERSEDED` u prvoj liniji | `migrations/109:1` | PROVEN |
| **P1-25** | **Nacrt stiže advokatu bez ijednog pravnog izvora.** `/api/podnesak` i `/api/nacrt` ne vraćaju `izvori` uopšte; `_vxRenderIzvori` se ne poziva u `dispatchTab === 'n'` grani. Grounding se vidi kod pitanja, a **ne** na dokumentu koji ide sudu | `drafting.py:1021-1027`; `vindex.js:924` vs `:7565` | PROVEN |
| **P1-26** | `.doc` je zagarantovana serverska greška — prolazi `accept` (`index.html:1085`), JS proveru (`vindex.js:19726`) i serverski allowlist (`api.py:4535`), pa `extract()` diže `ValueError` → 500. Poruka korisniku pritom glasi „Podržani formati: PDF, DOCX" | `extractor.py:402` | PROVEN |
| **P1-27** | OCR fotografija je dodat na backendu uz komentar da advokat sa slikama nema gde da ih otpremi — ali klijentska kapija upload zone predmeta blokira slike; isti korisnik preko Smart Intake dugmeta dobija drugačiju podršku formata bez objašnjenja | `index.html:1085` vs `:2331` | PROVEN |
| **P1-28** | **Limit uređaja se ne primenjuje.** Na 409 `SESSION_LIMIT` frontend prikaže toast, prijava se nastavlja, heartbeat kreće bezuslovno; `/api/sesija/ping` radi `_upsert_sesija` **bez provere limita**, pa odbijeni uređaj sam sebi upiše red 60 s kasnije | `vindex.js:649-650`; `sesije.py:149-162` | PROVEN |
| **P1-29** | Smart Intake poll je **beskonačan** — nema brojača pokušaja ni vremenskog limita, a `if (!r.ok) return;` znači da 500 nikad ne pomeri stanje: čarobnjak ostaje zamrznut na „Korak 2/3 — Obrada", bez greške i bez retry-a. Ispravan obrazac postoji u `strat_job_poll` (`:3514`) i nije primenjen ovde | `vindex.js:21301-21342` | PROVEN |
| **P1-30** | `tosAccept()` ne proverava `r.ok`, guta izuzetak i **bezuslovno** sakrije overlay — korisnik veruje da je prihvatio uslove, backend nema zapis | `vindex.js:773-785` | PROVEN |
| **P1-31** | 60 praznih `catch(e){}`, 36 oko `fetch`. `dodajKomentar()` na 4xx/5xx obriše uneti tekst i reload-uje listu kao da je uspelo; `evidence_addDokaz` prikaže „Dokaz dodat ✓" bez provere odgovora | `vindex.js:4280-4295`, `:18509` | PROVEN |
| **P1-32** | 3 od 4 audit prefiksa ne pogađaju nijednu rutu; nacrti pišu provenance sa `predmet_id=NULL`; `predmet_create` audit izostaje iz Smart Intake puta | `shared/audit.py:15`; `smart_intake.py:1423` | PROVEN |
| **P1-33** | `session_id` ne šalje nijedan živi put → serverska memorija `ai_sessions` je neupotrebljiva | `api.py:3025-3031,3096-3102` | PROVEN |
| **P1-34** | Zadatak se ne može dodeliti kolegi — `zadaci/kreiraj` ne šalje `dodeljen_uid` iako tim postoji | `zadaci.py:59` | PROVEN |
| **P1-35** | Ručni dokaz je zauvek `snaga="srednja"` i nevezan za dokument — UI šalje samo `tvrdnju` preko `prompt()` | `evidence.py:370-375` | PROVEN |
| **P1-36** | `smart_intake` hardkoduje `storage_path` na lažni `session/{id}` | `smart_intake.py:1423` | PROVEN |
| **P1-37** | `pred_load()` bez `await`, pa `pred_select(id)` čita stari `_predmeti` keš → prazan naslov predmeta | `vindex.js:21798` | PROVEN |
| **P1-38** | `sw.js` zove `/api/notifications/rokovi-check` — 0 pogodaka u `.py`. Jedina nerazrešiva putanja u celom frontendu | `static/sw.js:193` | PROVEN |
| **P1-39** | Cohere je živ produkcijski provajder bez guard-a, provenance-a i retry-ja; na grešci tiho pada na `_gpt_rerank` | `app/services/retrieve.py:34,1265` | PROVEN |
| **P1-40** | `routers/law_upload.py:84` i `routers/batch_ingest.py:55` su u produkcionom procesu, pišu u Pinecone, a nemaju **ni** `@llm_retry` **ni** `try/except` — delimičan neuspeh ostavlja indeks polu-upisan | — | PROVEN |
| **P1-41** | `retrieve.py:2111` — `except → return []` na proširenju upita, bez retry-ja; pozivalac (kroz dvostruku indirekciju `executor.submit`, `:1777`) ne razlikuje „nema kandidata" od „GPT pao" | `retrieve.py:2111,1777` | PROVEN |
| **P1-42** | Audio provenance redovi trajno nemaju tokene ni `output_hash` — `shared/ai_client.py:460,472` prosleđuje `response=None` **i na uspehu**. Audit izgleda pokriven po broju redova, nije po sadržaju | `shared/ai_client.py:456-473` | PROVEN |
| **P1-43** | Nijedno mesto ne postavlja `max_retries` na klijentu → SDK default 2 × tenacity 3 = **do 9 uzvodnih HTTP zahteva po jednom logičkom pozivu** | `shared/llm_retry.py:33` | PROVEN |

---

## 5. P2 — POSLE BETE

| # | Nalaz | `fajl:linija` |
|---|---|---|
| P2-01 | Praksa se dohvata **dvaput** kroz dva nezavisna pipeline-a i ulazi u prompt dvaput | `retrieve.py:1955` + `main.py:3267-3272` |
| P2-02 | Praksa, mišljenja i **korisnikov dokument** se modelu serviraju pod naslovom „KONTEKST IZ BAZE ZAKONA" | `main.py:3453,3517,3571` |
| P2-03 | `_proveri_halucinaciju` early-return: bilo koje „nije pronađen u bazi" u odgovoru preskače proveru **svih** citata | `main.py:744-752` |
| P2-04 | `_FRAMEWORK_CLANOVI_EXEMPT` je whitelist **samo brojeva** bez zakona — „čl. 374 ZUP" prolazi neproveren | `main.py:720-726` |
| P2-05 | Guard prag: kod `<1 doc / <100 chars`, docstring tvrdi `<3 / <500` — dokumentovani ≠ implementirani | `main.py:735,758` |
| P2-06 | `memory_context` (USER-CONTROLLED) se PREPEND-uje **iznad** anti-halucinacijskih instrukcija | `main.py:3392-3393` |
| P2-07 | Witness nalaže `[Opšti pravni princip]`, Revizor i Red Team ga **zabranjuju** — kontradiktorna pravila u istom lancu | `strategija.py:512` vs `:463,536` |
| P2-08 | `SLUŽBENI IZVOR:` footer se gradi iz konteksta, ne iz odgovora — drugi, nesinhronizovan prikaz porekla | `main.py:1120-1134` |
| P2-09 | `kontekst` raste monotono bez budžeta; K6 nosi 5 slojeva LLM izlaza + do 30.000 karaktera opisa u svih 8 poziva | `strategija.py:673→787` |
| P2-10 | Frakciona cena `0 < krediti×multiplier < 1` tiho postaje besplatna preko `int()` | `shared/usage.py:396` |
| P2-11 | Fail-open na brojačima: greška → zahtev se propušta neizbrojan | `shared/usage.py:229-241` |
| P2-12 | Cena keširana 60 s **po procesu** — promena u Admin Console nije trenutna na svim worker-ima | `shared/feature_registry.py:29,48-68` |
| P2-13 | „AI Sudija (3 runde debate)" — 3 sekvencijalna jednosmerna prompta, bez ijedne runde razmene | `strategija.py:410-452` |
| P2-14 | „Hitni rokovi (do 3 dana)" — backend koristi ručni flag `vaznost=="kritičan"` i `≤2 dana`, dva različita pravila | `api.py:3676`; `routers/dashboard.py:273` |
| P2-15 | Besplatni plan: „5 predmeta" i „Sudska praksa (ograničeno)" — nijedno ograničenje nije implementirano | `api.py` POST `/api/predmeti` |
| P2-16 | Landing **potcenjuje** proizvod: „18 zakona" (app: 847), „5 šablona" (postoji 17) | `landing.html:907,919` |
| P2-17 | Nesklad porta: `Dockerfile` default 8000, `gunicorn.conf.py` default 10000 — direktno relevantno za incident sa `localhost:8000` | `Dockerfile:19,21` vs `gunicorn.conf.py:16` |
| P2-18 | Audit middleware preskače `/healthz`, ruta se zove `/health` → healthcheck svakih 30 s se pune audituje | `shared/audit.py:14` vs `api.py:1536` |
| P2-19 | Mrtav kod: `_deduct_credit` importovan nikad pozvan; `require_credits` nula `Depends()`; `api.py:441-495` duplikati | `shared/usage.py:44` |
| P2-20 | `deduct_credit` sa pogrešnim ugovorom (`RETURN COALESCE(new_credits,0)` → 402 neizvodljiv) i dalje živ u bazi kao zamka | `supabase_setup.sql:134-141` |
| P2-21 | `strategija.py:414` hardkoduje `"credits_deducted": 6` nezavisno od registry cene | `strategija.py:414` |

---

## 6. POSLEDICA PO VEĆ ISPORUČEN RAD

**Task 1 (Provenance UI, commit `b984a039`) stoji na netačnoj pretpostavci.**
UI prikazuje `izvori` kao „Pravni izvori" ispod odgovora. `P1-01` dokazuje da je `izvori` lista onoga što je **pretraga vratila**, ne onoga što je **odgovor citirao**, i da isključuje praksu, mišljenja i korisnikov dokument koji jesu bili u kontekstu.

Advokatu se, dakle, prikazuje spisak zakona koji odgovor možda nikad nije upotrebio, a izostaju izvori koje jeste. To nije razlog za povlačenje commit-a — prikaz je i dalje bolji od ničega — ali **jeste razlog da se ugovor `izvori` popravi pre nego što se na tu funkciju osloni javna tvrdnja „Vindex zna odakle zna".**

---

## 7. GRANICE OVOG TALASA

| Ograničenje | Posledica |
|---|---|
| `SUPABASE_DB_URL` nedostaje | Telo migracije 108, stvarno stanje RPC GRANT-ova i integritet audit lanca ostaju `UNVERIFIED`. 59 testova naplatnog sloja se ne izvršavaju. |
| Nema pristupa deploy-u | `BTM-P0-04` se ne može zatvoriti iz repoa — ne zna se koji build je živ. |
| Radno stablo DIRTY | Merenja se odnose na stanje koje ne postoji ni u jednom commit-u (`landing.html`, `strategija.py`). |
| Talas 1 je **samo otkrivanje** | Nijedan nalaz nije popravljen. Nijedan test nije napisan. |

---

## 8. ŠTA JE PROVERENO I **NIJE** NALAZ

Ovo je jednako važan deo matrice. Kandidat bez dokazanog puta izvršenja nije nalaz, i ovde su odbačeni.

| Kandidat | Zašto je odbačen |
|---|---|
| „Mrtvi ruteri" | Svih **111** rutera je registrovano u `api.py`. Nema mrtvog rutera. |
| „Frontend gađa nepostojeće rute" | Svih **292** razrešivih `fetch()` putanja pogađa postojeću rutu. Jedini izuzetak je `sw.js:193` (→ P1-38). |
| „`onclick` bez funkcije" | Nijedan `onclick` u `index.html` ne poziva nepostojeću funkciju. |
| `aic3_submit()` šalje `/api/pitanje` bez `predmet_id` | **Mrtav kod** — `aic3-q`/`aic3-btn` ne postoje u `index.html`. Živi put (`execQuery`, `:7386`) ŠALJE `predmet_id`. |
| `qiKreiraj` šalje 3 od 14 polja i preskače proveru sukoba interesa | Dostupan samo preko `display:none` dugmeta (`index.html:596`) bez ijednog JS pozivaoca. **Mrtva UI površina.** |
| Intake Wizard šalje podskup polja | **Lažno pozitivan.** `_intakeKreiraj` (`:20939-20953`) šalje svih 14 polja i radi conflict-check. |
| „Neograničen retry oko AI poziva" | **0 mesta.** `stop_after_attempt(3)` sa jitter-om svuda; nema `while True`. |
| Cross-tenant autorizacija | 10 nezavisnih sweep-ova (V49–V58), nula puteva. Vlasnički predikat je uvek unutar mutacije; ne postoji putanja prepisivanja vlasništva. |
| Aliasirani/lazy importi sakrivaju AI pozive | Provereno namenski: 118 od 129 `openai` importa je funkcijski-lokalno, svi uhvaćeni podudaranjem po lancu atributa. **Zamka nije prošla.** |

**Automatski diff je našao 33 endpointa gde UI šalje strogi podskup Pydantic modela.** Posle provere dostupnosti i toga da li polje zaista otključava ponašanje, teški su ostali samo `BTM-P0-07` i `BTM-P0-12`. Ostatak je ušao kao P1-33…P1-35 ili je odbačen.

---

## 9. ZBIR

| Klasa | Broj |
|---|---|
| **P0 — blokira betu** | **15** |
| **P1 — rizik u beti** | **43** |
| **P2 — posle bete** | **21** |
| Domeni koji prolaze | 7 |
| `UNVERIFIED — REQUIRES DB` | 3 |

### Predlog verdikta (nije odluka — odluka je vlasnikova)

**BETA NO-GO na trenutnom stanju.** Ne zbog broja nalaza, nego zbog **tri** koja sama po sebi obaraju beta test:

1. **`BTM-P0-11`** — prvi ekran koji novi advokat vidi ne radi. Beta počinje onboardingom; ako on ne prolazi, ne meri se ništa drugo.
2. **`BTM-P0-01` + `BTM-P0-14` + `BTM-P0-15`** — korisnik plaća, ne dobija ništa, i ne vidi ni poruku zašto. Otvaranje Podešavanja mu naplati kredit.
3. **`BTM-P0-03` + `BTM-P0-10`** — beta testeri i razvoj dele istu bazu i isti Pinecone, uz 16 neverzionisanih skriptova koji pišu u produkciju.

Sve tri su popravljive. Nijedna ne traži arhitektonsku promenu.

**Nezavisno od popravki, ovo se ne može zatvoriti iz repoa:** `BTM-P0-04` (koji build vrti produkcija). Dok se to ne zna, tvrdnja da je kreditna trka zatvorena **nije dokaziva** — SQL jeste primenjen, Python ispravka nije potvrđena u deploy-u.
