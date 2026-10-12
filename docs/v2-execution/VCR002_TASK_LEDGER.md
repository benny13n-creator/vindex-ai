# VCR002 — knjiga zadataka

Grana `program/vcr002-beta-operational-closure`, osnova `main` = produkcija `b36235a3` (PR #19).
Dokazi VCR001 se ne ponavljaju; referenca: `VCR001_TASK_LEDGER.md`, `VCR001_R1_GATE.md`, `VCR001_R2_GATE.md`.
Nivoi dokaza: LOCAL · ISOLATED · BROWSER_INTEGRATION · LIVE · REAL_USER_ACCEPTED.

---

## T00 — Stvarnost izdanja i osnovica posle spajanja — `PASS_LIVE`

- **Početni SHA:** `b36235a3`.
- **Problem:** posle spajanja PR #19 nije bilo utvrđeno šta tačno radi u produkciji ni koji testovi padaju.
- **Šta je provereno:**
  - `origin/main` = `b36235a3` (Merge PR #19). Izveštaj OPERATION LIVE nije spojen, kao što je i bilo namereno.
  - Produkcija: `GET https://vindex.rs/health` → `"commit":"b36235a"`, `redis:true`, `workers:1`.
  - `/app` → 200, asseti `/v2/app/@b36235a/…`.
  - VCR001 moduli se serviraju (200): `agenti-predmeta.js`, `nacrt-predmeta.js`, `zadaci-predmeta.js`, `zastarelost-kalkulator.js`, `dokaz-unos.js`.
  - `/app-legacy` → 200.
- **Minimalni ugovor ruta (bez prijave):**

  | Ruta | Odgovor |
  |---|---|
  | `GET /api/predmeti` | 401 |
  | `GET /api/workspace` | 401 („Prijava je obavezna…“) |
  | `GET /api/staging/x` | 401 |
  | `POST /email-notif/send-reminders` bez ključa | 403 „Restricted to founder or valid cron key.“ |
  | `POST /api/cron/autonomy` bez ključa | 401 |

- **CI na `b36235a3`, poređenje identiteta palih testova sa `6ad0b13a`:**

  | Workflow | Rezultat | Padovi | Novo | Nestalo |
  |---|---|---|---|---|
  | Security Checks (run 38213977242) | success | — | — | — |
  | Test Suite 3.11 / 3.13 (run 38213977142) | failure | 174 / 174, prethodno 175 / 175 | **0** | `test_ca_trust_boundary.py::test_M19_dokaz_prezivljava_granu_sa_predmetom` (ispravljen u VCR001 T04) |
  | Production Runtime Parity (run 38213977151) | failure | pun paket 196 (8162 passed) | **0** | M19 |

  - Production Runtime Parity: byte-compile i Docker build/boot su zeleni.
  - Prividna razlika „test_wave7_failure_matri…“ je skraćena linija u logu. Parametrizovani skup je identičan sa obe strane.
- **Bezbednosni izuzeci:** JWT CVE-2026-85394 je prihvaćen do 2027-01-09 (JRC001, CI kontrola roka) i nije proširen.
- **Kritični putevi koji ostaju nedokazani:**
  - prijavljeni tok u produkciji (T01);
  - OCR na produkcionom serveru (T02);
  - podsetnici (T04);
  - autonomija (migracija 136 nije primenjena; T09).
- **Izmenjeni fajlovi:** samo dokumentacija.
- **Status:** `PASS_LIVE` (javni ugovor i identitet izdanja). Prijavljeni deo pripada T01.

## T01 — Prijavljena produkciona QA sesija — `BLOCKED_AUTHENTICATION`

- **Šta je provereno:**
  - U ovom izvršnom okruženju nema QA kredencijala: ni promenljive okruženja, ni lokalnog `.env` ključa, ni sačuvanog pregledača.
  - TinyFish profil nije dostupan ovoj sesiji, a poslednji put je zatečen odjavljen.
- **Šta namerno NIJE urađeno** (direktiva):
  - nova registracija;
  - pravljenje naloga preko Supabase SQL-a;
  - preuzimanje tuđe sesije;
  - izmišljanje lozinke.
- **Za otključavanje:** osnivač dostavlja kanal za QA nalog: e-pošta + lozinka u lokalnoj promenljivoj okruženja (npr. `VX_QA_EMAIL` / `VX_QA_PASSWORD`, nikad u repo-u) ili prijavljen profil pregledača. Posle toga se izvršavaju koraci 1–7 iz direktive.
- **Status:** `BLOCKED_AUTHENTICATION`. Nezavisni zadaci se nastavljaju.

## T02 — OCR i Smart Intake na kontrolisanom korpusu — `PASS_ISOLATED` (živo: `BLOCKED_AUTHENTICATION`)

- **Problem:** OCR na stvarnom produkcionom putu otpremanja nikad nije nezavisno dokazan.
- **Izvor istine (nepromenjen):**
  - `routers/smart_intake.py` (otpremanje, pregled, prikačivanje);
  - `shared/intake_worker.py`;
  - `uploaded_doc/extractor.py` (Tesseract po strani, VCR001 T01);
  - migracije 073 / 092 / 095.
- **Postojeći dokazi (ne ponavljaju se):** NS005 Gate B matrica A/B/B2/C/D/E/F i NS005 T14:
  - skeniran PDF → pregled;
  - izolacija A/B;
  - dedupe;
  - odbijen pregled;
  - nečitljiv sken;
  - nepodržan format;
  - idempotentno prikačivanje;
  - ćirilica kroz worker.
- **Dodato:** `tests/test_vcr002_t02_ocr_korpus.py` (11 testova). Svi su sintetički, a imena i brojevi su izmišljeni:

  | # | Slučaj | Ugovor |
  |---|---|---|
  | A | digitalni PDF (latinica) | tačni redovi u `tekst_sadrzaj`, `ocr_koriscen=false` |
  | D | DOCX | poznat pasus doslovno u tekstu dokumenta predmeta |
  | C | mešovit PDF (digitalna latinica + rasterizovan ćirilični sken) kroz **stvaran worker** do prikačenog dokumenta | `ocr_koriscen=true`; digitalni red doslovno; ćirilica ≥ 75 % reči sa srpskim paketom (OCR tolerancija); bez paketa skenirana strana nije tiho izostavljena; ponovno čitanje ne pravi novo stanje |
  | — | isto ime, različit sadržaj | dva posla i dva dokumenta |
  | — | > 25 MB | odbijeno, bez posla i bez skladišta |
  | — | oštećen PDF | nikad `completed`, bez entiteta i bez dokumenta |
  | — | prolazna greška baze **posle ekstrakcije** | posao je vraćen u red (`attempts=1`); posle ponovnog pokušaja tačno jedan `intake_documents`; entiteti nisu udvostručeni |
  | — | greška baze **pri prikačivanju** | nije uspeh (5xx bez sirove greške baze); do isteka zauzeća iskren 409 i nijedan dokument; posle isteka tačno jedan dokument |
  | — | ponovljeno prikačivanje bez ključa | jedan dokument, jedan vektorski upis |
  | — | prikačivanje u tuđ predmet | 403/404, bez traga |
  | — | mreža | nijedan spoljni pokušaj |

- **Rezultati:**
  - Lokalno (bez Tesseract-a): `10 passed, 11 skipped` (zajedno sa NS005 T14). Preskočen je samo test C, jer traži stvaran OCR.
  - Test je dodat u oba CI OCR koraka `production-runtime.yml`:
    - runner sa `tesseract-ocr`;
    - **produkciona Docker slika** sa `VINDEX_REQUIRE_OCR=1 VINDEX_EXPECT_SRP=1`, gde je nedostatak OCR-a pad.
- **Negativna kontrola (mutacije, binarni režim):**
  - M1 (limit ×4): UHVAĆENA.
  - M2 (pad workera obeležen kao završen): UHVAĆENA.
  - M3 (zauzeće bez prozora zastarelosti): neodlučna, jer lažni RPC tumači `0` kao podrazumevanih 120 s. Nije prijavljena kao dokaz.
- **Uočeno ograničenje `LIM-T02-1`:**
  - Šta se dešava: posle neočekivane greške baze tokom prikačivanja, zauzeće (`finalizing_at`, migracija 092) se ne oslobađa. Ponovni pokušaj zato oko 120 s dobija 409 „Finalizacija je već u toku… za par sekundi“.
  - Integritet je očuvan: nema lažnog uspeha i nema duplikata, a test to dokazuje.
  - Problem je poruka: „par sekundi“ ne odgovara stvarnih ~2 minuta.
  - Zašto nije menjano: ispravka traži zahvat u funkciju od oko 1.300 linija, izvan ovog zadatka. Predlog je poseban mali zadatak (CAS oslobađanje zauzeća u `except` grani).
- **Živo:** zavisi od T01 (`BLOCKED_AUTHENTICATION`). Postupak za živu proveru je u `VCR002_RELEASE_HANDOFF.md` §8.
- **Status:** `PASS_ISOLATED`. LIVE: `BLOCKED_AUTHENTICATION`.

## T03 — Bojanov tok sa više dokumenata — `PASS_ISOLATED` + jedna ispravka integriteta (živo: `BLOCKED_AUTHENTICATION`)

- **Početni SHA:** `514d0f24`.
- **Scenario** (izmišljen): Zlatibor Fiktivić protiv Primer Gradnja DOO, P 4711/2026, tri dokumenta:
  - Tužba: rešenje uručeno 17.03.2025;
  - Dostavnica: uručeno 25.03.2025 — namerna protivrečnost;
  - Zapisnik: rok za izjašnjenje za 14 dana.

  Nedostaje ugovor o radu.
- **Šta prolazi stvarnim putem** (`tests/test_vcr002_t03_visedokumentni_predmet.py`):
  - Smart Intake rute;
  - intake worker i pypdf;
  - kanonski pisac tvrdnji;
  - Case Evolution dispečer;
  - osvežavanje Genome-a (zamenjen je samo model; on vraća SAMO oznake `DOK-NN` i `CLAIM-NNN` iz stvarnog prompta, a server ih razrešava);
  - sinhronizacija rokova;
  - Case Actions;
  - lanac odluka o roku;
  - pravno pitanje i istorija;
  - brisanje dokumenta.
- **Ispravka `FIX-T03-1`** (problem → reprodukcija → ispravka):
  - **Problem:** obrisan dokument je ostajao merodavan. `predmet_dokazi.dokument_id` je `ON DELETE SET NULL` (016), pa su AI tvrdnje obrisanog dokumenta ostajale aktivne bez izvora. Nastavljale su da ulaze:
    - u Genome (`EVIDENCE VAULT … CLAIM-001: Rok za izjasnjenje…`);
    - u kontekst pravnog pitanja kao „Utvrđene činjenice“;
    - u Analizu.
  - **Ispravka** (`api.py::predmet_dokument_obrisi`):
    - pre atomskog brisanja se pročitaju tvrdnje tog dokumenta koje je napisao sistem: `izvor_tvrdnje='ai_klasifikacija'`, ili zastarele tvrdnje pronađene u tekstu (`nacin_pronalaska` egzaktan/normalizovan);
    - posle potvrđenog brisanja te tvrdnje dobijaju `deleted_at` (meko brisanje, isti mehanizam kao `delete_dokaz`);
    - **advokatove tvrdnje (`covek`) se ne diraju**;
    - broj povučenih tvrdnji ide u odgovor i u nepromenljivi audit (`tvrdnje_povucene`).
  - **Bez migracije.**
  - **Ostatak rizika:** pad procesa između brisanja reda i povlačenja ostavlja tvrdnje kao ranije. To nije gore od zatečenog stanja, a greška se beleži u logu kao `error`.
- **Rezultati:**
  - `7 passed`.
  - Mutacije M1 (bez povlačenja), M2 (povlači i advokatove) i M3 (čitanje posle gubitka veze): **sve 3 UHVAĆENE**.
  - Regresija: postojeći testovi brisanja (NS001 FAZA 2, Wave 2 2D) 35/35. Šira grupa (brisanje, dokazi, evidence, OSB002/003, VCR001, NS006, FRG001, Wave 2): **484 passed, 1 skipped**.

| Zahtev | Dokaz | Status |
|---|---|---|
| **B6** više dokumenata u jednom predmetu | 3 dokumenta, 3 stabilna identiteta, jedan predmet; svaka tvrdnja nosi svoj `dokument_id`; nema „preskakanja“ | `PASS_ISOLATED` |
| **B8** hronologija sa izvorom | `genome-v2` hronologija: oba datuma uručenja → tačan `dokument_id` | `PASS_ISOLATED` |
| **B9** rok potvrđuje advokat | rok iz Zapisnika: `AI_AUTONOMOUS`, `dokument_id` = Zapisnik, akcija „čeka vašu potvrdu“; posle ponovnog osvežavanja i dalje 1 rok i 1 akcija; potvrda je trajna i zatvara akciju; B ne može da odluči o tuđem roku | `PASS_ISOLATED` |
| **B11** akcije iz nalaza u dokumentu | `PLANIRATI_ROKOVE` sa `hronologija_id` + `dokument_id` | `PASS_ISOLATED` |
| **B12** Genome sa identitetom izvora | protivrečnost razrešena u dva STVARNA reda tvrdnji iz dva različita dokumenta; `CLAIM-NNN` nije sačuvan kao identitet; poslednje osvežavanje vidi sve dokumente; posle brisanja ne vidi obrisan | `PASS_ISOLATED` |
| pravno pitanje u predmetu | kontekst nosi tvrdnje sva tri dokumenta, u granici poverenja; B ne dobija kontekst; istorija upisana jednom, vlasniku | `PASS_ISOLATED` |
| **B13** sintetički | ceo lanac iznad | `PASS_ISOLATED` |
| **B13** stvaran pilot | nema pilot predmeta ni prijavljene sesije | `BLOCKED_AUTHORITY` (pilot) / `BLOCKED_AUTHENTICATION` |

- **Zapažanje `OBS-T03-1`** (nije menjano):
  - Kontekst pravnog pitanja prikazuje obe protivrečne AI tvrdnje kao „Utvrđene činjenice … snaga=jaka“, bez oznake protivrečnosti.
  - Advokat to ne vidi, jer je reč o promptu modela. Ipak, „utvrđene“ je preširoka reč za AI izvod.
  - Promena teksta prompta je promena ponašanja proizvoda, pa je predložena kao posebna odluka, ne tiha izmena.
- **Zapažanje `OBS-T03-2`:**
  - Rok iz obrisanog dokumenta ostaje u hronologiji bez izvora (126: „čuva istorijski događaj“, namerno).
  - Ostaje **NEPOTVRĐEN**, pa nikad ne postaje operativna obaveza. Test to proverava.
