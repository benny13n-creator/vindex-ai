# NS001-P0-001 — FINALNI FORENZIČKI IZVEŠTAJ

**Sprint:** NIGHT STABILIZATION 002
**Baseline:** `da62879d` (potvrđen; worktree čist, `origin/main` u sinhronizaciji)
**Datum:** 2026-08-16

---

## VERDICT

# 🟡 BLOCKED

Korenski uzrok **jednog** od dva mehanizma je dokazan i popravka je napisana,
izmerena — i **vraćena**, jer je merljivo pogoršala stvarni scenario. Drugi
mehanizam zahteva odluku o slabljenju bezbednosne kontrole, koju ovaj sprint
nema pravo da donese (`RULE 15`).

**Produkcijski kod nije menjan.** Isporučeno je: dokaz, karakterizacioni testovi
i tačno definisana odluka koja blocker zatvara.

---

## ROOT CAUSE

Kada zakonski korpus slabo pogodi pitanje, odgovor se odbacuje pre nego što
činjenica iz advokatovog dokumenta dobije priliku — prvo instant-odbijanjem koje
uopšte ne gleda dokument (MEHANIZAM 1), a ako se sinteza ipak pokrene, blokadom
odgovora koja odnosi i dokumentarnu činjenicu zajedno sa pravnim delom
(MEHANIZAM 2).

---

## MEHANIZAM 1 — DOKAZAN

`main.py::ask_agent`, blok „DOC GATE BIAS".

Mehanizam postoji baš zato da odgovor iz advokatovog dokumenta ne bude odbijen
kad zakonski korpus slabo pogodi: ako pasus dokumenta ima skor ≥ 0.5, pojas
pouzdanosti se podiže za jedan stepen. Ali je zaključan iza:

```python
if extra_namespaces:
```

`extra_namespaces` je parametar **stare** šeme (`tmp_<session>`, firmin
namespace). Od BR-003 dokumenti predmeta stižu drugim putem — vlasnički
namespace se **izvodi** unutar `retrieve_documents` iz identiteta, pa je
`extra_namespaces` za kanonsko pitanje o predmetu `None`.

**Za taj tok se mehanizam ne izvršava nijednom.**

Posledica: `ask_agent` KORAK 2 (`if confidence == "LOW"`) vraća
`_format_low_response(...)` **pre ijednog LLM poziva i bez gledanja u `docs`** —
„Nemam pouzdan odgovor u trenutnoj bazi zakona", za činjenicu koja doslovno piše
u dokumentu.

Dokaz je deterministički i ne zavisi od modela: `tests/test_ns002_document_fact_authority.py`
— `test_1` (kanonski tok: odbijeno pre modela) naspram `test_1b` (stari tok:
sinteza pokrenuta, isti ulaz). Razlika je **isključivo** `extra_namespaces`.

---

## MEHANIZAM 2 — OPSERVIRAN, OKIDAČ NIJE DOKAZAN

Kada sinteza krene, pasus dokumenta stigne modelu (`test_3` to meri na stvarnom
model inputu) i model vrati činjenicu. Ali kada guard obori odgovor
(`[MEDIUM→BLOCK] Commit3 guard`), **ceo** tekst se zamenjuje kanonskim „Opšta
pravna logika — nema direktnog člana u bazi". Blokada je sve-ili-ništa, pa uz
neproverljivi pravni deo odlazi i dokumentarna činjenica.

To je doslovno tekst koji je NS001 merio kao neuspeh.

**Šta NIJE dokazano:** tačan okidač blokade u produkciji. U harness-u guard puca
na `[COMMIT3] JSON parse greška` (lažni model vraća tekst umesto JSON-a); u
stvarnom prolasku model vraća ispravan JSON i blokada se svejedno dešava. Uzrok
te blokade nije izolovan i **ovde se ne tvrdi**.

---

## POKUŠANA POPRAVKA I ZAŠTO JE VRAĆENA

Uklonjen je uslov `if extra_namespaces:` — mehanizam se oslanja na
`retrieval_meta["doc_passages"]`, koji je već popunjen bez obzira kojim putem su
pasusi stigli (`app/services/retrieve.py:2261`). Prag 0.5 i mapa pojaseva
nepromenjeni; menja se isključivo **kada** se mehanizam konsultuje.

Izmereno posle izmene, stvarni E2E, isti dokument i ista pitanja:

| Scenario | Pre | Posle |
|---|---|---|
| A — direktna činjenica iz dokumenta | 10/10 | **10/10** |
| J — kombinovano (zakon + dokument) | 4/5 | **1/10** |

Zatvaranje MEHANIZMA 1 gura više pitanja u sintezu, gde ih MEHANIZAM 2 obori.
Devet od deset J odgovora bilo je doslovno „nema direktnog člana u bazi".

**Popravka koja merljivo pogoršava stvarni scenario nije popravka.** Vraćena je;
`main.py` je bit-identičan baseline-u.

---

## E2E DOKAZ

| Test | Pokušaja | PASS | FAIL | Verdikt |
|---|---|---|---|---|
| A — DIRECT FACT (baseline) | 10 | 10 | 0 | PASS |
| B — PARAPHRASED (baseline) | 5 | 5 | 0 | PASS |
| E — COMPETING GENERAL KNOWLEDGE (baseline) | 5 | 5 | 0 | PASS |
| J — SOURCE PRIORITY (baseline) | 5 | 4 | 1 | **FAIL** |
| A — posle pokušane popravke | 10 | 10 | 0 | PASS |
| J — posle pokušane popravke | 10 | 1 | 9 | **FAIL** |
| G — FACT NOT PRESENT | 5 + 4 | v. napomenu | — | **NEDOVOLJNO IZMERENO** |

**Napomena o G (poštenje merenja):** prvi prolaz je prijavio 0/5, ali je uzrok
bio **moj detektor**, ne proizvod — regex je davao lažne negative. Ručna
provera četiri odgovora pokazuje da sistem uredno kaže „Iznos ugovorenog
depozita nije naveden u dostavljenom kontekstu" i **ne izmišlja iznos**. Nalaz
je povučen; scenario nije ponovo izmeren u punom obimu i vodi se kao
**neizmeren**, ne kao PASS.

Mandatom traženih **20/20 nije dostignuto ni u jednom stanju koda**, pa
certifikacija nije moguća.

---

## REAL INFRASTRUCTURE

| Sloj | Status |
|---|---|
| Supabase | PASS — prava baza, jednokratan nalog |
| Pinecone | PASS — pravi indeks, pravi vektori |
| Embedding | PASS — pravi `text-embedding-3-large` |
| Model | PASS — pravi odgovori, bez mock-a |
| Auth | PASS — pravi Supabase ES256 token (`sign_in_with_password`) |
| API put | PASS — `POST /api/pitanje` sa `predmet_id`, isti koji UI zove |

Mock je korišćen **isključivo** u determinističkim testovima uzroka, i nijedan
mock nije jedini dokaz nijedne tvrdnje o proizvodu.

---

## SOURCE AUTHORITY

| Pitanje | Status |
|---|---|
| Činjenice iz dokumenta | **DELIMIČNO** — 10/10 na direktno pitanje, 1/10 na kombinovano |
| Pravni izvori | PASS — nepromenjeni |
| Kombinovana pitanja | **FAIL** — v. MEHANIZAM 2 |
| Nepostojeća činjenica | NEIZMERENO u punom obimu (v. napomenu o G) |

Kanonski ugovor o autoritetu izvora (FAZA 3 mandata) **nije implementiran** —
implementacija bez zatvorenog MEHANIZMA 2 bila bi deklaracija bez dejstva.

---

## VARIANCE

**20/20 nije dostignuto.** Najbolje izmereno: A = 10/10; J = 1/10.

---

## MUTATION

Nad pokušanom popravkom, pre vraćanja: **3/3 ubijeno** (vraćen
`extra_namespaces` uslov; uklonjen prag 0.5; pojas skače dva stepena).

Nad karakterizacionim testovima koji su ostali: `test_1f` pada čim se uslov
ukloni, `test_1`/`test_2` padaju čim se ponašanje promeni — što je i svrha.

---

## REGRESSION

| | Baseline | Posle |
|---|---|---|
| passed | 5661 | **5672** |
| failed | 1 (poznat flake) | **0** |
| skipped | 1 | 1 |

Baseline prolaz je imao jedan pad — `test_get_supa_thread_safe_single_client_created`
(`BR001-FLAKE-001`), koji samostalno prolazi (`1 passed in 1.94s`) i pada
povremeno u punom prolasku. U završnom prolasku nije pao. **Nula novih padova.**
Nijedan postojeći test nije obrisan ni oslabljen; produkcijski kod je nepromenjen.

---

## FALSE-GREEN CHECK — pet pokušaja da oborim sopstveni rezultat

1. **„Možda test prolazi zbog memorije modela, ne zbog retrieval-a."**
   Kontrolna činjenica je izmišljen iznos uz nasumičan marker
   (`VX-KONTROLA-7719`, 17.350 EUR) koji ne postoji ni u zakonu ni u opštem
   znanju. Model je ne može znati.
2. **„Možda je G stvarno pao."** Provereno ručno — nije. **Moj detektor je bio
   pokvaren.** Nalaz povučen, scenario preveden u „neizmeren".
3. **„Možda MEHANIZAM 1 ne postoji, nego DOC GATE uopšte ne radi."**
   `test_1b` vozi identičan ulaz kroz stari put i sinteza se pokreće. Mehanizam
   radi — samo ne za kanonski tok.
4. **„Možda činjenica ne stiže modelu."** `test_3` čita **stvarni model input**
   (`_pozovi_openai` argumente) i nalazi `17.350` u njemu.
5. **„Možda popravka ipak pomaže, a J je slučajnost."** Uzorak je proširen sa 5
   na 10 pokušaja: 1/10, sa identičnim tekstom u 9 odgovora. Nije slučajnost.
6. **„Možda drugi prompt pregazi ovaj."** `ORIGIN_HIERARCHY_INSTRUCTIONS` je
   definisan na jednom mestu (`app/services/doc_formatter.py:73`) i ubacuje se
   na jednom mestu (`app/services/retrieve.py:2277`).

---

## ODLUKA KOJA ZATVARA BLOCKER

**Sme li odgovor da pretekne sa potvrđenom činjenicom iz advokatovog dokumenta
kada je njegov pravni deo neproverljiv?**

- **DA** → blokada prestaje da bude sve-ili-ništa: dokumentarni deo ostaje,
  pravni se izostavlja uz jasnu oznaku. Zahteva razdvajanje „činjenica iz
  dokumenta" od „pravna tvrdnja" u guard-u.
- **NE** → trenutno ponašanje je namerno, a P0 tok se zatvara drugačije:
  odvojenim odgovorom na dokumentarna pitanja, van pravnog pipeline-a.

Dok odluka ne postoji, uklanjanje `extra_namespaces` uslova **ne treba
ponavljati** — izmereno je da samo za sebe pogoršava stvar.

---

## PRODUCTION SAFETY

Jednokratan nalog, dva kontrolna predmeta, dva sintetička dokumenta. Nijedan
postojeći korisnički podatak, dokument ni namespace nije dirán. Čišćenje je
izvedeno sa višestrukom potvrdom (§ Čišćenje u završnoj poruci).

---

## REMAINING BETA BLOCKERS

- **NS001-P0-001** — i dalje **OTVOREN**. Advokat ne dobija pouzdano činjenicu
  iz sopstvenog dokumenta kada pitanje kombinuje dokument i pravni okvir.

---

## CERTIFICATION

**NS001-P0-001 NIJE ZATVOREN.**

# 🔴 BETA NO-GO
