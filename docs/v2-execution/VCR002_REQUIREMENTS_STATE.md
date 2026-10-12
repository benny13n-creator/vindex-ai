# VCR002 T10 — Stvarno stanje zahteva (Bojan, Miroslav)

**Izvori:**
- `docs/product/A018_BOJAN_REQUIREMENTS_REALITY_MATRIX.md` (B1–B13, jedina sourced šema);
- `docs/v2-execution/VCR001_REQUIREMENTS_MATRIX.csv` (prethodno stanje).

**Pravilo:** stari izveštaji se ne podižu na nov nivo dokaza bez novog posmatranja.

**Kvalitet dokaza:** PROVEN (posmatrano u ovom programu ili u CI-ju na istom kodu) · INFERRED (sledi iz koda i dokazanog ugovora) · ASSUMED · UNKNOWN.

**Nivoi:** LOCAL · ISOLATED · BROWSER_INTEGRATION · LIVE · REAL_USER_ACCEPTED.

## Bojan B1–B13

| ID | Traženi ishod | Vlasnik | V2 ulaz | Dokaz (VCR002) | Najviši nivo | Ograničenje | Status |
|---|---|---|---|---|---|---|---|
| B1 | nov predmet | `routers/predmeti.py`, intake | Nov predmet | VCR001 R1 (nepromenjeno); e2e paketi zeleni u VCR002 | BROWSER_INTEGRATION — PROVEN | prijavljena produkcija nije proverena | PASS (sintetički) |
| B2 | predmet iz dokumenta | `smart_intake.finalize` | Prijem | VCR001 T02; T03 test sa 3 dokumenta kroz stvarne rute | ISOLATED — PROVEN | stvaran predmet | PASS_ISOLATED |
| **B3** | stvaran skeniran OCR | `uploaded_doc/extractor.py`, worker | Prijem | **T02: 32 testa u PRODUKCIONOJ Docker slici** (srp+srp_latn+eng, `VINDEX_REQUIRE_OCR=1`), uključujući mešovit PDF sa ćiriličnim skenom kroz stvaran worker do teksta prikačenog dokumenta | ISOLATED (produkciona slika) — PROVEN | **produkcioni upload nije posmatran** (nema QA sesije) | PASS_ISOLATED; LIVE = BLOCKED_AUTHENTICATION |
| B4 | dokument vezan za predmet | intake + `predmet_dokumenti` | Dokumenti | T02/T03: identitet, tuđ predmet 403/404 bez traga | ISOLATED — PROVEN | — | PASS_ISOLATED |
| B5 | tvrdnje iz dokumenata | `shared/evidence_write.py` | Analiza | T03: tvrdnje po dokumentu sa `dokument_id`; **FIX-T03-1**: obrisan dokument povlači svoje AI tvrdnje | ISOLATED — PROVEN | stvaran predmet | PASS_ISOLATED |
| **B6** | više dokumenata u jednom predmetu | ceo lanac | Prijem → Analiza | **T03: 3 dokumenta, 3 stabilna identiteta, tvrdnje ne „preskaču“ dokument** | ISOLATED — PROVEN | stvaran spis | **PASS_ISOLATED** (bilo PARTIAL) |
| B7 | protivrečnost | Genome + V2 paket | Pregled „Zahteva pažnju“ | T03: protivrečnost razrešena u dva stvarna reda tvrdnji iz dva dokumenta | ISOLATED — PROVEN | model zamenjen (deterministički izlaz) | PASS_ISOLATED |
| **B8** | hronologija sa izvorom | `genome_contract` | Analiza | T03: `genome-v2` → tačan `dokument_id` za oba datuma | ISOLATED — PROVEN | stari Genome blobovi dobijaju izvor tek na osvežavanju | PASS_ISOLATED |
| **B9** | rok potvrđuje advokat | `case_dna._sync_rokovi_to_hronologija` + lanac odluka | Danas, Pregled | T03: rok iz Zapisnika → „čeka potvrdu“; posle ponovnog osvežavanja i dalje 1 rok i 1 akcija; potvrda trajna; B ne može | ISOLATED — PROVEN | stvaran predmet | PASS_ISOLATED |
| **B10** | podsetnik za potvrđen rok | `routers/email_notif.py` + `email-cron.yml` | (email) | T04: kapija potvrde kroz stvarnu kapiju; **FIX-T04-1** (dva roka istog dana su gubila podsetnik), **FIX-T04-2** (predmet u brisanju); dijagnoza 403 = `CRON_SECRET` ≠ `CRON_TOKEN` ili nije postavljen | ISOLATED — PROVEN | zakazan posao 6/6 pada sa 403; isporuka nikad posmatrana | **BLOCKED_AUTHORITY** (tajna + test primalac) |
| **B11** | akcije iz nalaza u dokumentu | `case_evolution` Rule 6 | Pregled | T03: `PLANIRATI_ROKOVE` sa `hronologija_id` + `dokument_id`; bez duplikata posle ponavljanja | ISOLATED — PROVEN | — | PASS_ISOLATED |
| **B12** | Genome sa identitetom izvora | `routers/case_dna.py` | Analiza | T03: poslednje osvežavanje vidi sve dokumente; posle brisanja ne vidi obrisan dokument ni njegove tvrdnje | ISOLATED — PROVEN | produkcioni blobovi pre A001 | PASS_ISOLATED |
| B13 sintetički | ceo lanac | — | — | T03 (backend) + VCR001 R1/R2 + T07 e2e (UI) | ISOLATED / BROWSER_INTEGRATION — PROVEN | — | PASS_ISOLATED |
| **B13 stvaran** | prihvaćen ceo tok na stvarnom predmetu | — | — | nema pilot predmeta, nema dozvole za stvarne podatke, nema QA sesije | — UNKNOWN | — | **BLOCKED_AUTHORITY** (pilot) |

Nijedan zahtev nema nivo LIVE ni REAL_USER_ACCEPTED.

## Miroslav

**Pretraženo u VCR002:**
- repo i `docs/`;
- `.vindex_ai_team/`;
- memorija projekta (VCR001);
- **Google Drive osnivača:** pretraga celog teksta „Miroslav“ dala je **0 rezultata**.

Autentičan izvor zahteva M-01…M-07 nije pronađen. Istorijski ID-jevi misija nisu dokaz identiteta zahteva, pa **nijedan zahtev nije izmišljen**.

**Status:** `BLOCKED_REQUIREMENTS_SOURCE`. Potpuno Miroslavljevo prihvatanje se **ne** proglašava.
