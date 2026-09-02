# FAZA 6.3 — PROVENANCE WRITER INVENTORY

## 1. Executive Summary

**16 pisaca** u `predmet_hronologija`. Svi PROVEN, svi direktni `.insert()`.
**0 DB-side pisaca** (nema trigera ni RPC-a), **0 indirektnih**, **0 dinamickih**,
**0 u `scripts/`**, **0 UPDATE/DELETE putanja** — red je nepromenjiv posle upisa.

**15/16 pisaca upisuje u `akter` stabilan potpis** (tacna vrednost ili stabilan
prefiks). **Tacno JEDAN** — `W-UPLOAD` — upisuje **slobodan tekst iz modela**, i
bas on objasnjava **49/55 zivih redova**. Jedan pisac je unistio semantiku polja
za ceo sistem.

**UNCLASSIFIED = 0**, ali postoje **2 taksonomska ruba** (§19) i **49 legacy
redova** koji se ne mogu deterministicki klasifikovati (§22).

## 2. Environment Proof
0 izmena koda · 0 migracija · 0 GPT poziva · 0 email/SMS · 0 push/deploy ·
0 novih produkcionih redova · fixture netaknut.

## 3. Starting SHA
```
HEAD (lokalno)  5ab3990d      origin/main = production  044c5310
```

## 4. Scope Lock Verification
`git status` nad `shared/ routers/ api.py services/ migrations/ static/ tests/` = **0 izmena**.

## 5. Search Methodology
- **M1 direktna pretraga** — `predmet_hronologija` + `.insert(` → 16 pogodaka.
- **M2 sema/migracije** — 4 migracije pominju tabelu (`076` komentar, `077` FK,
  `126` kolona, `096` komentar). **Trigera/funkcija koje pisu: 0.**
- **M3 call-chain** — za svaki pisac utvrdjen entry point, ruta i vrednost `akter`.
- **M4 negativna pretraga** — dinamicka imena tabela (`supa.table(t)`) postoje na
  8 mesta, **sva SELECT-only** (`admin_dashboard`, `copilot` pretraga,
  `data_export`, `onboarding`, `proof`). RPC pozivi: krediti + intake red,
  **nijedan ne dira hronologiju**. `scripts/` samo cita.

## 6–14. COMPLETE WRITER INVENTORY

| ID | Lokacija | Entry point | INITIATOR | CONTENT GENERATOR | `akter` danas | Prolazi kapiju? | Kandidat klasa | Conf. |
|---|---|---|---|---|---|---|---|---|
| **W-UPLOAD** | `api.py:6108` → `_insert_hronologija_rows` | `POST /api/predmeti/{id}/upload` | covek (upload) | **AI autonomno** | **`str(ev["akter"])` — LLM tekst** | **DA** 🔴 | AI_AUTONOMOUS | PROVEN |
| W-GENOME | `case_dna.py:899` | `_sync_rokovi_to_hronologija` (event/refresh) | sistem/covek | **AI autonomno** | `"Genome (AI)"` | ne | AI_AUTONOMOUS | PROVEN |
| W-PIPELINE | `case_pipeline.py:376` | pipeline korak | sistem | **AI autonomno** | `"Pipeline (AI)"` | ne | AI_AUTONOMOUS | PROVEN |
| **W-SMARTINTAKE** | `smart_intake.py:1384` | `POST /jobs/{id}/finalize` | covek (klik) | **AI autonomno** | `"Smart Intake"` | **DA** 🔴 | AI_AUTONOMOUS | PROVEN |
| W-CONFIRMLINKS | `api.py:7187` | `POST /api/predmeti/{id}/confirm-links` | covek | covek potvrdio | `"Auto-detect (AI)"` | DA | AI_ASSISTED | PROVEN |
| W-COPILOT | `copilot.py:812` | `_handle_akcija_rok` (advokat kuca) | covek | covek (AI parsira) | `"Copilot (AI)"` | DA | AI_ASSISTED | HIGH |
| W-INTAKE-ROK | `intake.py:318` | `POST /api/intake/kreiraj` (`body.prvi_rok`) | covek | covek (forma) | `"Intake Wizard (AI)"` | DA | AI_ASSISTED | PROVEN |
| W-ROCISTE | `rocista.py:399` | `POST /api/rociste/followup` | covek | covek | `"Advokat"` | DA | HUMAN_DIRECT | PROVEN |
| W-UGOVOR | `ugovor_zastupanja.py:337` | `POST /api/ugovor-zastupanja/generiši` | covek | covek | `f"Advokat {ime}"` | DA | HUMAN_DIRECT | PROVEN |
| W-CLOSE | `predmeti_close.py:190` | `PATCH /api/predmeti/{id}/zatvori` | covek | covek | `"Advokat (ručno zatvaranje)"` + tekst | DA | HUMAN_DIRECT | PROVEN |
| W-INTAKE-TPL1 | `intake.py:451` | `POST /api/intake/kreiraj` (`template_id`) | covek | **staticki katalog** `_TEMPLATES` | `"Intake Wizard — šablon"` | DA | DETERMINISTIC | PROVEN |
| W-INTAKE-TPL2 | `intake.py:1042` | `POST /api/intake/from-template` | covek | **staticki katalog** `_TEMPLATES` | `"Template (AI)"` ⚠ | DA | DETERMINISTIC | PROVEN |
| W-ROKOVILANAC | `rokovi_lanac.py:450` | `POST /api/rokovi/lanac` | covek | **staticki katalog** `_TIPOVI` (ZPP) | `"Automatski — ZPP lanac \| …"` | DA | DETERMINISTIC | PROVEN |
| W-EVOLUTION | `case_evolution.py:399` | `_consequence_timeline_entry` (event bus) | sistem | sistem | `"Case Evolution Engine"` | DA | SYSTEM | PROVEN |
| W-LEARNING | `learning.py:274` | `POST /outcome` | covek | sistem | `"Learning Engine"` | DA | SYSTEM | PROVEN |
| W-ONBOARDING | `onboarding.py:246` | `POST /api/onboarding/demo-predmet` | covek | staticki demo | `"Demo predmet"` | DA | SYSTEM | PROVEN |

**Database-side writers (§9): NIJEDAN.** Migracije `076/096` samo pominju tabelu u
komentaru; `077` menja FK; `126` dodaje kolonu. `grep "CREATE TRIGGER|CREATE OR
REPLACE FUNCTION"` + `hronolog` = **0 pogodaka**.

**Background/async (§10):** `W-GENOME`, `W-PIPELINE`, `W-EVOLUTION` idu kroz event
bus / pozadinski refresh. Ostali su sinhroni HTTP.

**Unknown/legacy writers (§14): 0 u kodu.** Ali 49 zivih redova nema potpis koji
bilo koji pisac osim `W-UPLOAD` proizvodi — v. §17.

## 15. Complete Writer Accounting
```
Writers discovered : 16
  PROVEN           : 15
  HIGH             :  1   (W-COPILOT — granica, v. §19)
  MEDIUM / UNKNOWN :  0
Database-side      :  0    (dokazano)
Indirect/dynamic   :  0    (dokazano — svi dinamicki su SELECT-only)
UPDATE / DELETE    :  0    (dokazano — red je nepromenjiv)

Klasifikacija po CONTENT GENERATOR-u:
  AI_AUTONOMOUS    :  4    W-UPLOAD, W-GENOME, W-PIPELINE, W-SMARTINTAKE
  AI_ASSISTED      :  3    W-CONFIRMLINKS, W-COPILOT, W-INTAKE-ROK
  HUMAN_DIRECT     :  3    W-ROCISTE, W-UGOVOR, W-CLOSE
  DETERMINISTIC    :  3    W-INTAKE-TPL1, W-INTAKE-TPL2, W-ROKOVILANAC
  SYSTEM           :  3    W-EVOLUTION, W-LEARNING, W-ONBOARDING
  UNCLASSIFIED     :  0
```

**Danas kapiju prolazi 14/16 pisaca**, ukljucujuci **2 AI_AUTONOMOUS**
(`W-UPLOAD`, `W-SMARTINTAKE`).

## 16. Semantic Separation Analysis

Kanonski dokaz zasto `akter` nije provenijencija — `W-UPLOAD`, stvarni zivi red:
```
INITIATOR        = COVEK            (advokat klikce Upload)
CONTENT GENERATOR= AI               (model cita dokument i izmislja dogadjaje)
EVENT ACTOR      = "DOO Alfa Trejd" (stranka u dogadjaju)  <- OVO ide u `akter`
SYSTEM WRITER    = api.py::predmet_upload_auto_analyze
```
Cetiri razlicite stvari; polje `akter` nosi **trecu**, a kapija je citala kao da
nosi **drugu**. To je ceo koren rupe iz FAZE 6.2.1.

**Posledica za taksonomiju: klasifikuje se po CONTENT GENERATOR-u, nikad po
inicijatoru i nikad po UI kliku.** `W-SMARTINTAKE` je dokaz: covek klikce
„Kreiraj predmet", ali rok koji se upisuje **nikad nije video** — klasifikacija po
kliku bi ga proglasila ljudskim i odmah ponovo otvorila rupu.

## 17. Production Data Cross-Check
```
55 redova · 6 sa prepoznatim potpisom (Genome/Pipeline) · 49 BEZ
49/49 od njih ima `dokument_naziv`   -> trag W-UPLOAD puta
NULL/prazan `akter`: 0
najstariji 2026-07-18 · najnoviji 2026-09-02
```
1. Ima li svaka kategorija trag? **Ne** — samo `AI_AUTONOMOUS` ima zive redove.
2. Redovi ciji se izvor ne moze odrediti iz `akter`? **49.**
3. Legacy? **Da**, svih 49 (nastali pre uvodjenja bilo kakve granice).
4. Pisac koji vise ne postoji? **Nema dokaza** za takav.
5. Obrazac koji nijedan pisac ne objasnjava? **Nema** — `W-UPLOAD` objasnjava svih 49.

⚠ Veza `dokument_naziv` → `W-UPLOAD` je **jaka korelacija, ne dokaz**:
`W-SMARTINTAKE` i `W-GENOME` takodje pisu `dokument_naziv`. Zato se 49 redova
klasifikuje kao **LEGACY_UNKNOWN**, ne kao AI.

## 18. Candidate Provenance Taxonomy

| Klasa | Semantika | Ulazi | NE ulazi | Safety posledica |
|---|---|---|---|---|
| `AI_AUTONOMOUS` | sadrzaj proizveo model bez da ga covek video pre upisa | W-UPLOAD, W-GENOME, W-PIPELINE, W-SMARTINTAKE | sve gde covek unese vrednost | **nikad odmah izvrsivo** |
| `AI_ASSISTED` | covek dao/video vrednost, model je samo obradio | W-CONFIRMLINKS, W-COPILOT, W-INTAKE-ROK | autonomna ekstrakcija | izvrsivo (covek odgovoran) |
| `HUMAN_DIRECT` | covek uneo vrednost rukom | W-ROCISTE, W-UGOVOR, W-CLOSE | sve AI | izvrsivo |
| `DETERMINISTIC` | staticki katalog u kodu, covek izabrao | W-INTAKE-TPL1/TPL2, W-ROKOVILANAC | LLM izlaz | izvrsivo |
| `SYSTEM` | posledica dogadjaja, ne opazanje | W-EVOLUTION, W-LEARNING, W-ONBOARDING | opazanja | nije rok — nije izvrsivo |
| `LEGACY_UNKNOWN` | nastalo pre ugovora, poreklo nedokazivo | 49 zivih redova | novi upisi | **fail-closed** |

## 19. Taxonomy Gaps

1. **`W-COPILOT` je granica.** Advokat kuca „Dodaj rok — rociste 20. jula 2026.";
   datum potice od coveka, ali ga **model parsira**. Pogresno parsiranje upisuje
   pogresan datum bez potvrde. Klasifikovan `AI_ASSISTED` (sadrzaj je covekov),
   ali to je **odluka, ne cinjenica** — trazi potvrdu vlasnika.
2. **`W-SMARTINTAKE` ima ljudski klik i AI sadrzaj.** Klasifikovan po sadrzaju
   (`AI_AUTONOMOUS`). Ako se politika promeni na „klik = pristanak", rupa se vraca.
3. **`"Template (AI)"` je pogresna oznaka** — sadrzaj je staticki `_TEMPLATES`
   katalog, ne AI. Naziv navodi na pogresan zakljucak (OUT-OF-SCOPE, §25).

## 20. Safety Policy Proposal (predlog, NIJE implementiran)
```
AI_AUTONOMOUS   -> NIKAD odmah izvrsivo; trazi eksplicitnu ljudsku potvrdu
LEGACY_UNKNOWN  -> NIKAD odmah izvrsivo (fail-closed)
AI_ASSISTED     -> izvrsivo; covek je video/dao vrednost
HUMAN_DIRECT    -> izvrsivo
DETERMINISTIC   -> izvrsivo; sadrzaj je iz kataloga u kodu
SYSTEM          -> nije rok, ne ulazi u podsetnike
```

## 21. Migration Contract Design (DESIGN ONLY)

**A. Kolona** — `izvor TEXT` sa `CHECK`. Ne enum tip (ALTER TYPE je bolan), ne FK
(sifarnik od 6 vrednosti ne zasluzuje tabelu).

**B. Nullability** — **`NOT NULL`**. NULL bi znacio „pisac je zaboravio", a to je
tacno stanje koje se zatvara.

**C. Default** — **BEZ DEFAULT-a.** Ovo je najvazniji deo ugovora: default bi
maskirao propust novog pisca i tiho ga svrstao u neku klasu. Bez default-a +
`NOT NULL` = novi pisac koji zaboravi `izvor` dobija **`23502` i pada glasno**.

**D. Constraint** —
`CHECK (izvor IN ('AI_AUTONOMOUS','AI_ASSISTED','HUMAN_DIRECT','DETERMINISTIC','SYSTEM','LEGACY_UNKNOWN'))`.
Nepoznata vrednost = `23514`, ne tiha „ljudska".

**E. Write enforcement** — DB je primarna brava (C). Sekundarno: test koji
prebrojava `table("predmet_hronologija").insert` pogotke i trazi `"izvor"` u
svakom — pada kad neko doda 17. pisca bez provenijencije.

**F. Backfill** — 49 legacy redova → **`LEGACY_UNKNOWN`**, nikad `HUMAN_DIRECT`.
6 redova sa potpisom `Genome (AI)`/`Pipeline (AI)` → `AI_AUTONOMOUS` (jedini
deterministicki klasifikabilni). Nista se ne nagadja iz `dokument_naziv`.

## 22. Legacy / Backfill Constraints
49/55 redova nije deterministicki klasifikabilno: `akter` nosi ime stranke, a
`dokument_naziv` pisu tri razlicita pisca. Moraju ostati `LEGACY_UNKNOWN` i
tretirati se fail-closed. **Backfill po heuristici je izricito odbacen.**

## 23. Future Writer Enforcement
Odgovor na §10: **`NOT NULL` bez `DEFAULT` + `CHECK`.** Novi pisac ne moze upisati
red bez provenijencije — insert pada na nivou baze. Model koji dozvoljava
„insert bez provenance → implicitno human" je REJECTED, i ovaj dizajn ga
strukturno onemogucava.

## 24. Future Adversarial Test Plan (dizajn, NIJE implementirano)
```
T1 AI autonomous writer          -> izvor = 'AI_AUTONOMOUS'
T2 human direct writer           -> izvor = 'HUMAN_DIRECT'
T3 system writer                 -> izvor = 'SYSTEM'
T4 insert bez `izvor`            -> 23502 (NOT NULL), fail-closed
T5 legacy red                    -> 'LEGACY_UNKNOWN', nikad 'HUMAN_DIRECT'
T6 AI sadrzaj + ljudski klik     -> 'AI_AUTONOMOUS' (po generatoru, ne po kliku)
T7 event actor = firma/sud       -> ne utice na `izvor`
T8 nepoznata vrednost `izvor`    -> 23514 (CHECK)
T9 svih 16 pisaca u izvoru       -> svaki sadrzi `"izvor"` u insert payload-u
```

## 25. Out-of-Scope Findings (prijavljeno, NIJE dirano)
1. `intake.py:1042` upisuje `"Template (AI)"` a sadrzaj je **staticki katalog** —
   pogresna oznaka.
2. `W-UPLOAD` prihvata `vaznost` **direktno iz LLM-a** (prompt dozvoljava
   `"kritičan"`), pa model sam sebi dodeljuje najvisi prioritet.
3. `predmet_hronologija` nema nijednu UPDATE/DELETE putanju — rok se ne moze
   ispraviti ni povuci (potvrdjuje nalaz iz FAZE 6.1).

## 26. FINAL VERDICT

🟡 **BLOCKED — potrebna odluka vlasnika**

Svi runtime pisci su pronadjeni i klasifikovani (**16/16, UNCLASSIFIED = 0**), i
migration contract je definisan tako da buduci pisac **ne moze** zaobici
provenijenciju. Ali GREEN nije opravdan jer stoje dve stvari koje nisu inzenjerske:

1. **49/55 zivih redova nije deterministicki klasifikabilno** → moraju ostati
   `LEGACY_UNKNOWN` i biti fail-closed. To znaci da postojeci rokovi prestaju da
   budu izvrsivi dok ih covek ne potvrdi — poslovna odluka, ne tehnicka.
2. **Dva taksonomska ruba** (`W-COPILOT`, `W-SMARTINTAKE`) traze eksplicitno
   pravilo: da li ljudski klik nad AI sadrzajem znaci pristanak.

**NIJE pushovano. NIJE deployovano.** `origin/main` = `044c5310`.
