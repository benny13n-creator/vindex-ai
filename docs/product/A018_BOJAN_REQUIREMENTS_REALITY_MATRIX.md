# A018 — BOJAN REQUIREMENTS REALITY MATRIX

**Datum:** 2026-08-31 · **HEAD:** `8f9432ba` · **Produkcija:** `8f9432b` · **Izmena: 0** (kod, testovi, migracije, baza)

---

# 1. FINAL VERDICT

# 🟡 PILOT POSSIBLE WITH KNOWN LIMITATIONS

Bojan **može** danas da uzme stvaran predmet i prođe jezgro toka: predmet → dokumenti → dokazi → kontradikcije → Genome. Ali od njegove četiri izričite stavke, **jedna ne radi** (podsetnici) i **jedna nije nikad izvršena** (OCR skeniranog dokumenta).

---

# 2. BOJAN REQUIREMENTS MATRIX

| ID | Zahtev | Šta Vindex radi | Dokaz | Status | Nedostaje |
|---|---|---|---|---|---|
| **B1** | kreiranje predmeta | `POST /api/predmeti` (34 rute za predmete); vlasništvo po `user_id` | 22 predmeta u produkciji; ruta vraća 401 bez auth; `predmeti.py` nema nijednu `_is_founder` granu → tenant izolacija po `user_id` | 🟢 | — |
| **B2** | unos dokumenta u predmet | Smart Intake: `POST /api/smart-intake/documents` → `/jobs/{id}/finalize` → `predmet_dokumenti` | 43 dokumenta u produkciji, 5 `intake_jobs`; sve iz fixture predmeta | 🟡 | dokaz na stvarnom predmetu |
| **B3** | **skenirani dokument (OCR)** | `Dockerfile` instalira `tesseract-ocr` + `poppler-utils` + `tesseract-ocr-srp/srp-latn`; `pytesseract`/`pdf2image`/`pymupdf` u `requirements.txt`; ulaz `uploaded_doc/extractor.py` | **`intake_documents`: 2/2 reda `ocr_used=False`, metod `heuristic`** — OCR **nikad nije izvršen** u produkciji | 🟡 | **0 dokaza izvršenja.** BLOCKED — REAL DATA REQUIRED (treba skeniran PDF bez tekstualnog sloja) |
| **B4** | pravilno čuvanje + identitet | `predmet_dokumenti.id` kanonski; `case_dna.dokazi_rang[].dokument_id` (A001), `kontradikcije.dokument_id_1/2` (A002) | A018 živi test 6/6; deployovano u `8f9432b` | 🟢 | — |
| **B5** | izvlačenje činjenica/dokaza | `shared/evidence_write.py` — jedan pisac (IMPL-001); `claim_refs` → `predmet_dokazi.id` (A014) | 12 dokaza u produkciji (svi fixture); A014 dokazan sa stvarnim GPT-om | 🟡 | dokaz na stvarnom predmetu |
| **B6** | povezivanje više dokumenata | Genome čita do 25 dokumenata; katalog `CLAIM-NNN` je predmet-scoped; tvrdnje se vezuju za konkretan `predmet_dokazi.id` | A017 T6: 3 spora nad istim parom dokumenata ostaju 3 kroz sva 4 sloja | 🟡 | dokazano na ≤4 fixture dokumenta, ne na stvarnom spisu |
| **B7** | kontradikcije | V2: `contradiction_id` kanonski, `claim_refs`, lifecycle, delta, projekcija, paketna atomičnost, stale zaštita | A017 T1–T6 **33/33**, failure semantics **23/23**; A016.9 T3 5/5, T8 4/4+3/3; mutacije 18/18, 11/11, 6/6 | 🟢 | — |
| **B8** | hronologija | `_sync_rokovi_to_hronologija` (`case_dna.py:829`) piše u `predmet_hronologija` | 52 reda u produkciji | 🟡 | **`predmet_hronologija` nema `dokument_id`** — izvor je `dokument_naziv` (tekst), ne identitet |
| **B9** | rokovi | Genome vadi `rokovi_kriticni`/`datumi_kljucni`; upisuje se u `predmet_hronologija` | BLK-1 zatvoren („sistem više ne izmišlja rokove"); tabela `rokovi` **ne postoji** i nijedan kod je ne gađa | 🟡 | nema zasebnog entiteta roka; dokaz samo na fixture podacima |
| **B10** | **podsetnici** | `POST /email-notif/send-reminders` (founder/cron); `POST /api/cron/daily`; slanje kroz `smtplib` + `EMAIL_SMTP_*` | **Nema internog planera** — `/api/cron/daily` traži SPOLJNI cron (Render/cron-job.org). `EMAIL_SMTP_*` se čita pri importu; lokalno UNSET, produkciono neproverljivo odavde. BLK-3 evidentiran kao BLOCKED | 🔴 | planer + potvrđen SMTP; lanac rok → podsetnik nije dokazan ni jednom |
| **B11** | obaveze/akcije | `case_actions` piše `case_evolution.py:1171` (Rule engine); V2 projekcija ima prednost (A015) | 31 akcija u produkciji — **sve istog tipa**, iz `identify_case_problems` (risk engine) | 🟡 | nijedna akcija ne potiče iz nalaza u dokumentu |
| **B12** | Genome / case_dna | `case_dna` sada nosi `dokument_id`, `claim_refs`, V2 redove | A018: kanonski test „`case_dna` sadrži UUID" prešao iz NE u DA (6/6) | 🟡 | **produkcioni blobovi su stariji od A001 → 0 UUID-a**; identitet dolazi tek na prvom refresh-u |
| **B13** | jedan predmet, više dokumenata, jedan lanac | ceo lanac postoji i deployovan je | dokazan **samo na fixture podacima**; nijedan stvaran predmet nikad nije prošao | 🟡 | BLOCKED — REAL DATA REQUIRED |

---

# 3. BOJAN END-TO-END READINESS

Predmet sa najmanje 4 dokumenta, kroz:

| # | Karika | Status |
|---|---|---|
| 1 | predmet | 🟢 dokazano |
| 2 | dokumenti | 🟡 tehnički postoji, dokazano samo na fixture |
| 3 | **OCR** | 🟡 infrastruktura postoji, **0 izvršenja** |
| 4 | činjenice/dokazi | 🟡 |
| 5 | kontradikcije | 🟢 dokazano |
| 6 | rokovi | 🟡 |
| 7 | hronologija | 🟡 (izvor je ime fajla, ne identitet) |
| 8 | **podsetnici** | 🔴 nedostaje |
| 9 | obaveze | 🟡 (samo iz risk engine-a) |
| 10 | Genome/case_dna | 🟡 (identitet tek od prvog novog refresh-a) |

**2 × 🟢 · 7 × 🟡 · 1 × 🔴**

---

# 4. TOP 5 BLOCKERS

1. **Podsetnik se ne aktivira sam.** Nema internog planera; `/api/cron/daily` traži spoljni cron, a `EMAIL_SMTP_*` nije potvrđen u produkciji. Bojanovo „novi podsetnici aktivirani" danas ne radi.
2. **OCR nikad nije izvršen.** Sistemske zavisnosti su u `Dockerfile`-u, ali 2/2 obrađena dokumenta imaju `ocr_used=False`. Za „skeniranu dokumentaciju" nemamo nijedan dokaz.
3. **Hronologija ne pamti izvor kao identitet.** `predmet_hronologija` nema `dokument_id`, samo `dokument_naziv` — advokat ne može da klikne sa stavke u hronologiji na dokument.
4. **Obaveze ne nastaju iz nalaza u dokumentu.** Svih 31 `case_actions` dolazi iz risk engine-a; nijedna iz pronađene činjenice/roka.
5. **Ceo lanac nikad nije prošao stvaran predmet.** Sve je dokazano na fixture podacima. BLOCKED — REAL DATA REQUIRED.

---

# 5. MINIMAL DEVELOPMENT PATH

| Sprint | Cilj | Problem | Rezultat | Verifikacija | GREEN kriterijum |
|---|---|---|---|---|---|
| **S1** | **Stvarni pilot predmet** | ništa nije prošlo stvaran spis | 1 predmet, 3–4 stvarna dokumenta (bar 1 skeniran, bar 1 sa rokom) | živo merenje lanca B1→B13 nad tim predmetom | svih 10 karika ima izmeren ishod, ne pretpostavku |
| **S2** | **OCR dokaz** | `ocr_used=False` u 2/2 | skeniran PDF bez tekstualnog sloja daje upotrebljiv tekst | `intake_documents.ocr_used=true` + `ocr_confidence` | tekst iz skena stiže do `predmet_dokumenti.tekst_sadrzaj` |
| **S3** | **Podsetnik uživo** | nema planera, SMTP nepotvrđen | rok iz dokumenta → podsetnik koji Bojan stvarno primi | jedan pravi rok → jedna prava poruka | lanac DOKUMENT→ROK→PODSETNIK izmeren od kraja do kraja |
| **S4** | **Identitet u hronologiji** | `dokument_naziv` umesto `dokument_id` | stavka hronologije vodi na konkretan dokument | migracija + živi upis | svaka nova stavka nosi `dokument_id` |
| **S5** | **Obaveza iz nalaza** | akcije samo iz risk engine-a | pronađen rok/činjenica kreira obavezu sa poreklom | živi test nad pilot predmetom | `case_actions` sa poreklom ≠ 0 |

Redosled je diktiran zavisnostima: **S1 prvi**, jer bez stvarnog predmeta S2–S5 nemaju nad čim da se mere.

---

# 6. WHAT WE MUST NOT TOUCH NOW

⚫ prijem klijenata · prisustvovanje ročištima · autonomni advokat · marketing · Web3 · digitalna imovina · novi agenti

**OUT OF SCOPE / KNOWN LIMITATION** (evidentirano, ne dira se): `event_id` persistence · duplirani Genome pipeline · `SUPERSEDED`/`MERGED` writer · `xmin` opseg · legacy collapse · HTTP status semantika · 19 fixture predmeta kao talog · `FOUNDER_EMAILS` = admin (čeka tvoju odluku) · Phase 0.5 / LRE (blokiran istim nedostatkom stvarnih podataka).

**A016/A017 se ne otvaraju ponovo** — dokazani su i deployovani.

---

# 7. TAČAN SLEDEĆI SPRINT

> **S1 — PRVI STVARNI PILOT PREDMET.**
> Bojan (ili ti) unosi **jedan stvaran predmet sa 3–4 dokumenta** kroz Smart Intake — od kojih je **bar jedan skeniran** (da bi se B3 uopšte mogao izmeriti) i **bar jedan sadrži rok** (da bi se izmerio B9→B10).
> Zatim merim lanac B1→B13 nad tim predmetom i ovu matricu prepisujem sa stvarnim brojevima umesto fixture dokaza.

Sve ostalo čeka taj podatak.
