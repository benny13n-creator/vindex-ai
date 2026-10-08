# Vindex V2 — strategija oporavka sposobnosti

**Misija:** CAPABILITY RECOVERY FORENSICS 001 · **Osnova:** `51164c92` · **Datum:** 2026-10-08
**Status:** samo mapa i plan. Ništa nije implementirano, ništa nije uklonjeno, ništa nije deployovano.

---

## 1. Odgovor na ključno pitanje

> *Da li su sposobnosti starog Vindexa zaista obrisane, ili su uglavnom ostale u backendu/legacy sloju ali su izgubile V2 UI?*

**Ostale su. Izgubljen je put do njih, ne kod.**

| Mera | Broj | Dokaz |
|---|---|---|
| Sposobnosti u popisu | 131 | `VINDEX_CAPABILITY_CENSUS.csv`; svih 629 API ruta je dodeljeno nekoj sposobnosti |
| Sposobnosti čiji je kod obrisan | **3 reda** (8 fajlova): 1 HISTORICAL_CODE_REMOVED, 1 INTENTIONALLY_RETIRED, 1 SUPERSEDED | `git log --diff-filter=D` nad kodnim direktorijumima |
| Registrovane API rute | 629 | stvarni `import api` |
| Rute dostupne običnom korisniku kroz V2 (`/app`) | **3** (sve GET) | `frontend-v2-ng/src/api.js` je GET-only |
| Rute iza founder-only `/app-v2` | 126 | `v2/boot.js` → `v2_pristup` |
| Rute samo u legacy UI-ju (nelinkovan `/app-legacy`) | 230 | statičko poklapanje putanja |
| Rute bez ikakvog frontend pozivaoca | 270 | od toga ≈ 90 namerno (cron, webhook, admin, javno, `/v1`) |
| Router fajlovi koji postoje a nisu registrovani | 0 | — |

**Raspodela 131 sposobnosti po primarnom statusu:**

| Status | Broj |
|---|---|
| 01 V2_LIVE_PROVEN | 5 (3 proizvodne + sajt + ljuska aplikacije) |
| 02 LEGACY_LIVE_PROVEN | 1 (prijava/nalog) |
| 03 BACKEND_ACTIVE_UI_DISCONNECTED | 10 |
| 04 BACKEND_PRESENT_UNPROVEN | 11 |
| 05 LEGACY_UI_PRESENT | 65 (UI postoji u legacy ili founder `/app-v2`) |
| 07 PARTIALLY_BROKEN | 10 |
| 08 DEPENDENCY_MISSING | 2 |
| 10, 12, 14 uklonjeno / zamenjeno / penzionisano | 5 |
| 11 SPEC_ONLY_NEVER_PROVEN | 2 |
| 13 DUPLICATE_IMPLEMENTATION | 20 |

**Zaključak.** Oko 110 od 131 sposobnosti ima živ, registrovan i auth-zaštićen backend. Oko 75 već ima gotov frontend ugovor (`/app-v2` `api.js` ili legacy `vindex.js`) koji se može ponovo upotrebiti. **Oporavak je pretežno posao povezivanja V2 ekrana sa postojećim backendom, ne ponovne izgradnje.**

---

## 2. Posebne istrage

### §20 OCR — prepoznavanje teksta sa skeniranih dokumenata

| Pitanje | Odgovor | Dokaz |
|---|---|---|
| Postoji li kod? | **DA, REAL** | `uploaded_doc/extractor.py`. PDF prvo pokušava tekstualni sloj; ako ga nema, renderuje stranu (PyMuPDF) pa koristi `pytesseract.image_to_data`. Slike: `.jpg/.jpeg/.png`. Predobrada: grayscale, kontrast 2.0, median filter. Jezik: `srp`, pa latinica, pa `eng` (timeout 45 s, `eng` fallback 30 s). Vraća `(tekst, is_scanned, ocr_used, strane, pouzdanost)`. |
| Ko ga zove? | 5 mesta | `api.py` upload u predmet; `routers/dokument.py:236`; `routers/drafting.py:564` (docx/txt); `routers/smart_intake.py:1428`; `shared/intake_worker.py:512` |
| Šta ne podržava | HEIC, TIFF | `IMAGE_SUFFIXES` |
| Uslov uspeha | `len(text) > 100`; inače vraća prazno i upisuje `insufficient_text` u `security_events` | kod |
| Da li je dokazano da radi? | **NE** | Jedini test sa pravim OCR-om (`test_b3_ocr_bez_laznog_uspeha.py::test_o2…`) pravi PDF sa oko 20 znakova i **pao je** jedini put kada je pokrenut sa tesseractom (PR #2, Production Runtime job). Na `main` taj CI job pada već pri prikupljanju testova (`test_word_addin_taskpane.py` traži node), pa se OCR u CI-ju **nikad ne izvrši**. |
| Verovatan uzrok pada testa | INFERRED: test tekst (~20 znakova) je ispod praga 100, a/ili je podrazumevani PIL font premali za čitanje | — |
| Produkcija | **UNKNOWN**: Dockerfile instalira `tesseract-ocr` (`srp` je opcion), ali nije dokazano da Render gradi iz Dockerfile-a | — |
| **Odluka** | `INVESTIGATE_BLOCKER`, pa `FIX_BACKEND_THEN_REWIRE` | Prvo dokaz: test sa stvarnim skeniranim dokumentom iznad praga, CI job koji zaista instalira tesseract, a founder potvrđuje Render build mod. Tek onda ide tvrdnja na sajtu. |

### §21 „Office Intelligence" — inteligencija kancelarije

Ovo **nije jedan modul**. U legacy-ju je sekcija „INTELIGENCIJA KANCELARIJE" (`index.html:1250`, „van 4 faze, cross-case statistika"). Sastoji se od:

| Deo | Sposobnost | Stanje |
|---|---|---|
| Analiza uspeha kancelarije | CAP-113 `routers/outcome_intel.py` | legacy UI, radi; bez upisanih ishoda daje prazan rezultat |
| Slični zatvoreni predmeti | CAP-114 `routers/precedenti.py` | legacy UI |
| Upis ishoda pri zatvaranju | CAP-130 `routers/predmeti_close.py` | legacy UI; **preduslov za oba gornja** |
| Digital Twin | CAP-112 | legacy UI; procente daje model, pa sukob sa Deterministic Intelligence principom |
| Zdravlje kancelarije | CAP-095 `/api/firm/health-index` | `/app-v2` i legacy; deterministički |
| Portfolio, profitabilnost, analitika | CAP-090, 099, 097 | `/app-v2` i legacy |
| CIO izveštaj, command center | CAP-098, 096 | legacy; duplikati brifinga |
| Firm memory (partneri, sudije, klijenti) | CAP-132 | **bez UI-ja ikada**; profilisanje sudija i partnera je pravni i etički rizik |
| Product intelligence | `/admin/pi/*` | founder-only, INTERNAL_ONLY |

**Odluka.** U V2 „Kancelarija" treba da bude sastavljena od:
- tima (CAP-091),
- portfolija (CAP-090),
- zdravlja kancelarije (CAP-095),
- uspeha po tipu spora (CAP-113, koji zavisi od CAP-130).

Firm memory **ne** ulazi bez redizajna. Tvrdnju starog sajta „deljenje … memorije firme" treba označiti kao UNSUPPORTED.

### §22 Više agenata (Multi-Agent)

| Deo | Dokaz | Stanje |
|---|---|---|
| `routers/multi_agent.py`: 6 agenata (intake, research, drafting, litigation, billing, deadline) | `/api/agents/run` i `/run-parallel` zove legacy podtab „agenti"; `/pipeline` nema pozivaoca; `/lista` je javna | radi kroz legacy; `PermissionService.require("multi_agent")` |
| Pozadinski agenti | `workers/background_agents.py` + `services/agent_tasks/{court_portal_watcher,precedents_radar}.py`, budžet po organizaciji, audit `AGENT_AUTONOMOUS_EXECUTION` | okidač `/api/cron/daily`; da li ga Render poziva: **UNKNOWN** |
| Feed preporuka | `routers/agent_notifications.py` (3 rute), migracija 082 `agent_recommendations` | **bez UI-ja**; accept/reject nema pozivaoca |
| Izolacija | `security/agent_isolation.py`, `shared/ai_fabric.py` | postoji; `test_ai_fabric_contract.py` ima 2 pada na `main` |
| Copilot | `/copilot/chat` (legacy), `/api/copilot/ambient/analyze` (Word add-in, bez pozivaoca) | legacy / bez UI-ja |

**Konačna klasa: `REAL_BUT_INCOMPLETE`.**
- Ručni agenti rade kroz legacy.
- Autonomni deo nema dokazan okidač ni ekran za preporuke.
- **Ne vraćati u V2 kao „agente".** Pojedinačne korisne izlaze (rokovi, nacrt, istraživanje) treba vratiti kroz njihove kanonske sposobnosti (CAP-070, CAP-060, CAP-040). Agentski sloj treba redizajnirati tek kada postoji ekran za ljudsku odluku (accept/reject).

### Ostale presude po domenu

| Domen | Presuda |
|---|---|
| **RAG / pravno istraživanje** | Srž je netaknuta i jaka: `/api/pitanje` sa citation guard-om, praksa, interni stavovi. Dostupna je samo kroz legacy i founder `/app-v2`. Najveća vrednost po jedinici rada. |
| **Nacrti** | Netaknuto: nacrt, podnesak, šabloni, DOCX, staging kao ljudska kapija. Style checker i ugovor o zastupanju su sporedni ili duplikati. |
| **Rokovi** | Kalkulatori, lanac rokova, ročišta i kalendar su zdravi. **Dva aktivna problema:** (1) ekran za potvrdu ili odbijanje roka postoji samo u founder-only `/app-v2`, pa ga obični korisnici nemaju nigde (ni legacy ga nema); (2) email podsetnici padaju svakog dana. Ovo je najveći *bezbednosni rizik po klijenta* (propušten rok). |
| **Inteligencija predmeta** | Case Genome je deployovan, ali je okružen sa 5 preklapajućih „jedna preporuka" modula. `case_actions` ima otvoren adversarial closure (memorija). |
| **Memorija i učenje** | 9 modula, skoro bez UI-ja, međusobno se preklapaju. Kandidat za konsolidaciju i penzionisanje, ne za oporavak. |

---

## 3. Definicija završenog talasa

Talas je završen **samo** kada je svaka uključena sposobnost:

1. **DISCOVERABLE**: vidljiva iz V2 navigacije bez kucanja URL-a.
2. **USABLE**: korisnik od početka do kraja završi scenario (Playwright dokaz, ne samo zelen unit test).
3. **TENANT-SAFE**: test sa dva naloga: B ne vidi, ne menja i ne briše podatke A (čitanje, pisanje, brisanje, Pinecone).
4. **ERROR-HONEST**: greška backenda se prikazuje kao greška, a ne kao prazno stanje („nema greške" nije dokaz).
5. **TESTED**: mutacioni dokaz da test pada kada se ugovor pokvari.
6. **REAL DATA**: provereno na stvarnom predmetu u produkciji, uz odobrenje foundera.

---

## 4. Talasi

Redosled je izveden iz dokaza: (a) vrednost za advokata, (b) koliko je gotovog koda, (c) rizik.

### TALAS 1 — Predmet je potpun (radni prostor predmeta)

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-004 nov predmet, CAP-005 izmena/brisanje, CAP-006 beleške/istorija, CAP-007 hronologija, CAP-008 workspace agregat, CAP-012 download/brisanje dokumenta, CAP-030/031 klijent i njegov timeline, CAP-032 sukob interesa, CAP-188 potvrda veza, CAP-074 ročišta, CAP-160 pretraga |
| **WHY NOW** | V2 NG već ima registar, detalj i čitač (jedine 3 rute). Advokat danas u `/app` ne može ni da otvori nov predmet ni da zapiše belešku. Svaki sledeći talas zavisi od ovoga. |
| **EXACT CODE TO REUSE** | Backend bez izmena: `api.py` (`/api/predmeti*`, beleške, istorija, hronologija, workspace, dokumenti), `klijenti/router.py`, `routers/conflict_check.py`, `routers/rocista.py`, `routers/search.py`. Frontend ugovori: `v2/features/predmeti/{api,nov}.js`, `v2/features/dosije/{api,izmena,brisanje,citac,prostor}.js`, `v2/features/klijent/*`, `v2/features/pretraga/view.js`. |
| **V2 UI** | U `frontend-v2-ng`: forma „Nov predmet", radnje na detalju, panel beleški i hronologije, kartica klijenta, pretraga u ljusci. Vizuelni pravac ostaje odobren (bez redizajna). |
| **BACKEND CHANGES** | Nijedna za čitanje. Pre upisa: proveriti da GET `workspace` sa insert side-effectom ostaje idempotentan. |
| **DB CHANGES** | Nijedna. |
| **WRITE SIDE EFFECTS** | `predmeti` (insert, update, delete + brisanje Pinecone vektora), `predmet_beleske`, `predmet_istorija`, `klijenti`, `predmet_klijenti`, Storage brisanje. **Brisanje predmeta ili dokumenta = nepovratno → obavezna potvrda.** |
| **SECURITY GATES** | Test sa dva naloga za svaku rutu koja piše; COI ostaje fail-closed; matični podaci klijenta se dešifruju samo za ovlašćene uloge. |
| **TEST GATES** | Playwright: nov predmet → beleška → upload postojećeg tekstualnog PDF-a → čitanje → brisanje beleške. Mutacija: uklonjen owner filter mora oboriti test. |
| **PRODUCTION GATE** | Founder ručno, na sopstvenom test predmetu; `/app-legacy` ostaje rezerva. |
| **WEBSITE CLAIMS UNLOCKED** | „Radni prostor predmeta", „Provera sukoba interesa", „Kartoteka klijenata". |
| **NON-GOALS** | Upload skeniranih dokumenata (zavisi od OCR-a), AI analiza, naplata. |
| **RELATIVE COMPLEXITY** | MEDIUM (ponovna upotreba VERY_HIGH) |

### TALAS 2 — Pravno istraživanje i nacrt

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-040 pravno pitanje, CAP-042 sudska praksa, CAP-045 interni stavovi, CAP-060 nacrt/podnesak, CAP-061 staging (ljudska kapija), CAP-062 šabloni, CAP-063 DOCX, CAP-186 izvoz |
| **WHY NOW** | Ovo je proizvod u očima advokata i najjača tehnologija (citation guard, „nema izvora → nema odgovora"). Backend je potpuno živ. |
| **EXACT CODE TO REUSE** | `api.py` `/api/pitanje`; `routers/praksa.py`; `routers/interni.py`; `routers/drafting.py`; `routers/doc_templates.py`; `routers/export.py`. Frontend ugovori: `v2/features/znanje/{praksa,stavovi,prostor}.js`, `v2/features/predmeti/{podnesak,sabloni}.js`. |
| **V2 UI** | Pitanje u kontekstu predmeta sa listom izvora i oznakom pouzdanosti; panel nacrta sa oznakama izvora i obaveznom napomenom „advokat mora pregledati"; staging odobri/odbij. |
| **BACKEND CHANGES** | Nijedna obavezna. `/api/pitanje/stream` je opcioni. |
| **DB CHANGES** | Nijedna. |
| **WRITE SIDE EFFECTS** | `predmet_istorija` i `predmet_beleske` (pitanje u predmetu), `staging_memory`, krediti/usage. |
| **SECURITY GATES** | Kontekst predmeta A ne ulazi u odgovor za predmet B (dokazano u memoriji: COI / trust boundary; ponoviti sa dva naloga). Prompt injection odbijen (postojeći testovi). |
| **TEST GATES** | Playwright: pitanje bez izvora daje „nema odgovora" (model se ne poziva); nacrt sa izmišljenim članom dobija oznaku „proveriti relevantan član". |
| **PRODUCTION GATE** | Founder na stvarnom pitanju i stvarnom predmetu. |
| **WEBSITE CLAIMS UNLOCKED** | „Odgovor sa izvorom", „Nacrt ne izmišlja član", „Kada izvora nema, nema ni odgovora". |
| **NON-GOALS** | Copilot chat, oblasti, playbook (dok se ne dokaže izolacija namespace-a), style checker. |
| **RELATIVE COMPLEXITY** | MEDIUM (ponovna upotreba VERY_HIGH) |

### TALAS 3 — Rokovi koji se ne propuštaju

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-070 kandidati + **potvrda** roka, CAP-071 lanac rokova, CAP-072 kalkulatori, CAP-075 kalendar, CAP-076 email podsetnici, CAP-080 obaveštenja, CAP-081 Danas/brifing |
| **WHY NOW** | Najveći rizik po klijenta. Ekran za potvrdu roka postoji samo u founder-only `/app-v2`, a email cron pada svakog dana. |
| **EXACT CODE TO REUSE** | `routers/rok_odluka.py`, `routers/rokovi_lanac.py`, `routers/zastarelost.py`, `routers/kalendar.py`, `routers/email_notif.py`, `routers/notifications.py`, `routers/morning_briefing.py`. Frontend ugovori: `v2/features/rokovi/odluka.js`, `v2/features/danas/*`, `v2/features/znanje/rokovi.js`. |
| **V2 UI** | Lista „rokovi na čekanju odluke" sa potvrdi/odbij; kalendar; ekran Danas. |
| **BACKEND CHANGES** | **FIX:** usklađivanje tajne `X-Cron-Key` između GitHub tajne i Render env-a (founder radi; nijedan token se ne ispisuje). `rok_odluka` backend se ne menja; ekran `v2/features/rokovi/odluka.js` se prenosi u V2 NG. |
| **DB CHANGES** | Nijedna očekivana. |
| **WRITE SIDE EFFECTS** | `predmet_hronologija` (potvrđen rok), `email_notif_log`, SMS/Viber slanje iz `potvrdi`. **Spoljna poruka = nepovratno.** |
| **SECURITY GATES** | Podsetnik ide samo vlasniku predmeta; cron endpoint ostaje fail-closed. |
| **TEST GATES** | Playwright: dokument sa rokom → kandidat → potvrda → rok u kalendaru → podsetnik u test sandučetu. Email cron zelen 3 dana zaredom. |
| **PRODUCTION GATE** | Founder prima stvaran podsetnik za test rok. |
| **WEBSITE CLAIMS UNLOCKED** | „Rokovi se prepoznaju pri unosu i čekaju vašu potvrdu", „Podsetnik pre roka". |
| **NON-GOALS** | Viber i WhatsApp (zavisnosti nedostaju), rok guardian (duplikat). |
| **RELATIVE COMPLEXITY** | MEDIUM |

### TALAS 4 — Prijem spisa (Smart Intake + OCR)

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-011 OCR (prvo dokaz), CAP-010 upload + auto-analiza, CAP-020 Smart Intake, CAP-014 protivrečnosti među dokumentima |
| **WHY NOW** | Glavna tvrdnja starog sajta („prevučete ceo folder", „sam pročita sliku") i najveća razlika u odnosu na konkurenciju. Ide **posle** talasa 1–3 jer je OCR nedokazan, a radnik u pozadini traži posebnu proveru. |
| **EXACT CODE TO REUSE** | `uploaded_doc/extractor.py`, `routers/smart_intake.py`, `shared/intake_worker.py`, `services/event_bus.py`, `routers/cross_doc.py`. Frontend ugovori: `v2/features/predmeti/uvoz.js`, `v2/features/dosije/poredjenje.js`. |
| **V2 UI** | Upload foldera, napredak „obrađeno N od M" kroz 5 faza, red za pregled polja ispod praga pouzdanosti, finalizacija. |
| **BACKEND CHANGES** | **INVESTIGATE_BLOCKER:** dokaz OCR-a u CI-ju sa stvarnim tesseractom i dokumentom iznad praga; odluka o pragu od 100 znakova; HEIC/TIFF po potrebi. |
| **DB CHANGES** | Nijedna očekivana (tabele `intake_*` postoje; produkciju potvrđuje founder). |
| **WRITE SIDE EFFECTS** | Storage (šifrovan original), `intake_jobs`, `intake_documents`, `extracted_entities`, novi predmeti, Pinecone vektori. |
| **SECURITY GATES** | Izolacija Storage putanja po korisniku; deduplikacija ne sme spojiti fajlove dva tenant-a. |
| **TEST GATES** | Stvarni skenirani podnesak (fotografija i PDF bez tekstualnog sloja) daje `ocr_used=True` i tačna polja; mutacioni dokaz. |
| **PRODUCTION GATE** | Founder potvrđuje Render build (Docker sa tesseractom), pa jedan stvaran skenirani dokument. |
| **WEBSITE CLAIMS UNLOCKED** | „Prepoznavanje teksta sa skeniranih dokumenata", „Otpremanje celog foldera". |
| **NON-GOALS** | Stari intake wizard (duplikat), case pipeline (forenzika na čekanju). |
| **RELATIVE COMPLEXITY** | HIGH |

### TALAS 5 — Kancelarija i naplata

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-091 tim, CAP-092 saradnja, CAP-093 komentari, CAP-094 zadaci, CAP-090 portfolio, CAP-095 zdravlje kancelarije, CAP-100 naplata/tarifa, CAP-101 izveštaji, CAP-099 profitabilnost, CAP-106 plan, CAP-161 izvoz/GDPR, CAP-184 APR |
| **WHY NOW** | Svakodnevna navika (tajmer, fakture); `/app-v2/kancelarija` već ima gotove ugovore. GDPR izvoz je zakonska obaveza pre gašenja legacy-ja. |
| **EXACT CODE TO REUSE** | `routers/{kancelarija,saradnja,komentari,zadaci,portfolio,health_index,billing,billing_reports,recurring,tarife,profitabilnost,plans,data_export,gdpr,apr}.py`; `v2/features/kancelarija/*`, `v2/features/dosije/{naplata,saradnja,profitabilnost}.js`. |
| **V2 UI** | Ekran Kancelarija i panel naplate na predmetu. |
| **BACKEND CHANGES** | Nijedna obavezna. |
| **DB CHANGES** | Nijedna. |
| **WRITE SIDE EFFECTS** | `billing_entries`, fakture, slanje fakture mejlom, članstvo u kancelariji. |
| **SECURITY GATES** | Uloge unutar kancelarije; član bez ovlašćenja ne vidi naplatu; test sa dva člana i dve kancelarije. |
| **TEST GATES** | Tajmer → stavka po AKS tarifi → faktura → PDF. |
| **PRODUCTION GATE** | Founder fakturiše test predmet. |
| **WEBSITE CLAIMS UNLOCKED** | „Tajmer i advokatska tarifa", „Fakture", „Uloge u kancelariji". **SEF tek posle posebnog dokaza** (CAP-102). |
| **NON-GOALS** | SEF slanje, benchmarking, CIO, analitika. |
| **RELATIVE COMPLEXITY** | MEDIUM |

### TALAS 6 — Strategija i inteligencija predmeta

| Polje | Sadržaj |
|---|---|
| **SCOPE** | CAP-120 Case Genome prikaz, CAP-121 matter intel, CAP-123 dokazi, CAP-126 sledeći korak (`case_actions`), CAP-110 strategija (Red Team, AI sudija, revizor…), CAP-116 priprema ročišta, CAP-130 zatvaranje + ishod, CAP-113 uspeh kancelarije, CAP-114 slični predmeti |
| **WHY NOW** | Posle osnova; vrednost je velika, ali je rizik da brojevi zvuče kao činjenice. |
| **EXACT CODE TO REUSE** | `routers/{case_dna,matter_intel,evidence,case_actions,strategija,hearing_cc,predmeti_close,outcome_intel,precedenti}.py`, `services/{v2_projection,risk_engine,case_evolution}.py`. |
| **V2 UI** | Odeljak „Strategija" na predmetu; „Kancelarija → uspeh po tipu spora". |
| **BACKEND CHANGES** | Zatvoriti otvoren adversarial closure za `case_actions` (Case Evolution Phase 2, uz odobrenje). |
| **DB CHANGES** | Nijedna očekivana. |
| **WRITE SIDE EFFECTS** | `commander_analize`, `decision_log`, `predictor_analize`, krediti. |
| **SECURITY GATES** | Tuđi predmet daje odbijanje pre upita u bazu, pre poziva modela i pre naplate (postojeće pravilo, ponoviti sa dva naloga). |
| **TEST GATES** | Brojevi (rizik, spremnost) dolaze iz koda, ne iz modela: mutacioni dokaz. |
| **PRODUCTION GATE** | Founder plus prvi pilot advokat. |
| **WEBSITE CLAIMS UNLOCKED** | „Alati za preispitivanje sopstvenog predmeta", „Brojeve računa program". |
| **NON-GOALS** | Court predictor u procentima, Digital Twin, strategy simulator, decision replay, legal reasoning graph. |
| **RELATIVE COMPLEXITY** | HIGH |

### TALAS 7 — Konsolidacija, penzionisanje i odvojeni proizvodi (odluke, ne povezivanje)

| Polje | Sadržaj |
|---|---|
| **SCOPE** | Memorija i učenje (CAP-131–136), firm memory (CAP-132), integracije (CAP-162/163/185/187), agenti (CAP-140/141/142/143), Compliance Suite (CAP-150/151), stari intake (CAP-021/022), oblasti (CAP-044), region (CAP-049), Viber/WhatsApp (CAP-078/079) |
| **WHY NOW** | Tek kada talasi 1–6 isprazne legacy, može se odlučiti šta se gasi. Odluka je foundera. |
| **EXACT CODE TO REUSE** | Compliance Suite: `routers/web3.py` i prateći moduli + `v2/features/uskladjenost/*` (zaseban proizvod/tarifa). |
| **V2 UI** | Samo za ono što founder odluči da zadrži. |
| **BACKEND CHANGES** | Spajanje duplikata (jedan vlasnik po konceptu). SSRF provera pre bilo kog odlaznog webhooka. |
| **DB CHANGES** | Moguće (penzionisane tabele). **Founder pokreće sve migracije; iz misije se ne šalje SQL.** |
| **WRITE SIDE EFFECTS** | Zavisi od odluke. |
| **SECURITY GATES** | Profilisanje sudija i partnera (firm memory) traži pravnu i etičku procenu pre bilo kakvog UI-ja. |
| **TEST GATES** | Za svaku penzionisanu rutu: dokaz da je niko ne zove (logovi u produkciji, uz odobrenje). |
| **PRODUCTION GATE** | Founder. |
| **WEBSITE CLAIMS UNLOCKED** | Digitalna imovina (posle porta); ništa iz memorije i agenata. |
| **NON-GOALS** | Brisanje bilo čega pre nego što legacy prestane da bude rezerva. |
| **RELATIVE COMPLEXITY** | HIGH (odluke), LOW–MEDIUM (izvođenje) |

---

## 5. Pre talasa 1 — blokeri koje founder rešava (bez implementacije)

1. **Render:** da li postoji cron koji zove `POST /api/cron/daily`? Da li se build radi iz Dockerfile-a (tesseract)?
2. **GitHub ↔ Render:** uskladiti tajnu za email cron. Ovo zatvara BLK-3.
3. **`v2_pristup`:** ostaje founder-only. Talasi idu u V2 NG (`/app`), ne u `/app-v2`.
4. **CI:** Production Runtime job pada pri prikupljanju (`test_word_addin_taskpane.py` traži node), a 148 async testova se ne izvršava (nema `pytest-asyncio`). Dok se to ne popravi, „zelen CI" ne dokazuje TESTED za async rute.

## 6. Tabela prioriteta

| TALAS | SPOSOBNOSTI | TRENUTNO STANJE | REUSE % | GLAVNI BLOKER | SECURITY RIZIK | V2 POSAO | WEBSITE UNLOCK | GO/NO-GO |
|---|---|---|---|---|---|---|---|---|
| 1 Predmet potpun | CAP-004..008, 012, 030..032, 074, 160, 188 | backend živ; `/app-v2` + legacy UI | VERY_HIGH | nijedan | brisanje (nepovratno), tenant izolacija | forme i radnje u NG | Radni prostor, COI, kartoteka | **GO** |
| 2 Istraživanje + nacrt | CAP-040, 042, 045, 060..063, 186 | backend živ; `/app-v2` + legacy UI | VERY_HIGH | nijedan | kontekst između predmeta | panel pitanja i nacrta | Odgovor sa izvorom, nacrt bez izmišljenog člana | **GO** |
| 3 Rokovi | CAP-070..072, 075, 076, 080, 081 | delimično pokvareno | HIGH | email cron tajna; potvrda roka samo u founder `/app-v2` | spoljne poruke | lista odluka, kalendar, Danas | Rokovi uz potvrdu, podsetnici | **GO posle blokera §5.2** |
| 4 Prijem + OCR | CAP-010, 011, 014, 020 | OCR nedokazan | HIGH | OCR dokaz + Render build | Storage/dedup između tenant-a | upload foldera, red pregleda | Skenirani dokumenti, folder | **NO-GO dok OCR nije dokazan** |
| 5 Kancelarija + naplata | CAP-090..095, 099..101, 106, 161, 184 | backend živ; `/app-v2` UI | VERY_HIGH | nijedan (SEF izuzet) | uloge u kancelariji | ekran Kancelarija | Tajmer, tarifa, fakture, uloge | **GO** |
| 6 Strategija + inteligencija | CAP-110, 113, 114, 116, 120, 121, 123, 126, 130 | legacy UI; `case_actions` otvoren | MEDIUM | adversarial closure `case_actions` | brojevi koji liče na činjenice | odeljak Strategija | Preispitivanje predmeta | **GO posle W1–W2** |
| 7 Konsolidacija | memorija, agenti, integracije, web3, duplikati | većinom bez UI-ja | LOW | odluke foundera | profilisanje, SSRF | samo zadržano | Digitalna imovina (posle porta) | **NO-GO bez odluke foundera** |
