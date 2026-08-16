# BETA READINESS — END-TO-END PRODUCT FORENSICS

**BASELINE / HEAD:** `add57c7a` · **BRANCH:** `main` · **WORKTREE:** čisto
**Režim:** samo čitanje. Nijedan produkcioni fajl, migracija ni šema nisu menjani.

---

## VERDICT: **NO-GO**

**Vindex NIJE spreman za beta pilot.**

Lanac „dokument → AI" je prekinut na dva mesta, nezavisno jedno od drugog, i
oba su izmerena nad produkcionim podacima. Sva 43 dokumenta koja u sistemu
postoje imaju status `sacuvano` — ne `indeksirano` — i **nijedan nema ijedan
vektor** u Pinecone-u. Ruta kojom advokat postavlja pitanje o dokumentu predmeta
proverava vlasništvo upitom `predmeti.id = <namespace-sufiks>`, a taj sufiks
nikada nije `predmeti.id` — presek izmerenih vrednosti je **nula**, pa ta ruta
za svaki postojeći dokument vraća `404`. Sistem pritom **ne laže**: status
`sacuvano` je istinit i tačno razlikuje „sačuvano" od „indeksirano", što je
zasluga ranijeg rada. Ali advokat koji uploaduje ugovor i pita „šta piše u
članu 5" ne dobija odgovor. Osim toga, veza klijent↔predmet nije dokaziva:
19 predmeta, 5 klijenata, **0 veza** u `predmet_klijenti`. Ponašanje trenutnog
koda za **nov** upload nije izvedeno, pa ostaje UNKNOWN — a UNKNOWN na
kritičnom toku je po mandatu takođe NO-GO.

---

## 2. CORE WORKFLOW MATRIX

| TOK | STATUS | DOKAZ | RUČNI KORACI | BLOCKER |
|---|---|---|---|---|
| Klijent — kreiranje | **UNKNOWN** | 5 klijenata postoji; tok nije izveden | — | — |
| Predmet — kreiranje | **UNKNOWN** | 19 predmeta postoji; tok nije izveden | — | — |
| **Klijent ↔ predmet veza** | **RED** | `predmet_klijenti` = **0 redova** uz 19 predmeta i 5 klijenata; `predmeti` **nema nijednu klijentsku kolonu**; svi pisci gutaju grešku (`logger.warning`/`debug`) | UNKNOWN | **BR-02** |
| Dokument — upload | **UNKNOWN** | 43 reda postoje sa `storage_path` | — | — |
| **Obrada → indeksiranje** | **RED** | **43/43 dokumenta status `sacuvano`**, nijedan `indeksirano`; **0 vektora** u Pinecone-u za svih 43 | — | **BR-01** |
| **Povezivanje dokument↔AI** | **RED** | Ruta traži `predmeti.id = <32-hex>`; presek sa stvarnim namespace-ima = **0** → `404` uvek | — | **BR-01** |
| AI pitanje — kontekst predmeta | **YELLOW** | `shared/case_context.py:348` čita `tekst_sadrzaj` **iz baze**, ne iz Pinecone-a → tekst dokumenta jeste dostupan modelu | — | — |
| **AI pitanje — o dokumentu** | **RED** | `/api/dokument/pitanje` sa `pred_` → `404` (dva nezavisna uzroka) | — | **BR-01** |
| Provenijencija | **UNKNOWN** | nije izvedeno do UI-ja | — | — |
| Rokovi | **YELLOW** | domen kanonizovan (`shared/rokovi.py`), 52 reda u hronologiji; pun životni ciklus nije izveden E2E | — | — |
| Hronologija | **YELLOW** | 52 reda; 3 sekundarna pisca gutaju grešku upisa | — | — |

---

## 3. END-TO-END SCENARIO

**Scenario A** (nov advokat → nov predmet → dokument → pitanje):

| # | Korak | Ishod |
|---|---|---|
| 1 | prijava | **PASS** (dokazano u `RLS-AB-001`: `signInWithPassword` radi) |
| 2 | kreiranje klijenta | **UNKNOWN** |
| 3 | kreiranje predmeta | **UNKNOWN** |
| 4 | povezivanje klijent↔predmet | **FAIL** — 0 veza u produkciji |
| 5 | upload dokumenta | **UNKNOWN** |
| 6 | obrada / indeksiranje | **FAIL** — 43/43 `sacuvano`, 0 vektora |
| 7 | dostupnost dokumenta AI sloju | **FAIL** — `404` na svakoj postojećoj instanci |
| 8 | pitanje nad predmetom (opšti kontekst) | **PASS uslovno** — tekst ide iz baze |
| 9 | provera izvora | **UNKNOWN** |
| 10–14 | rokovi / hronologija / povratak | **UNKNOWN / YELLOW** |

**Scenario B** (drugi korisnik / drugi predmet): **NIJE IZVEDEN.** Svi dokumenti
u produkciji pripadaju **jednom** korisniku (`384a7149…`), pa se cross-case
izolacija dokumenata iz podataka ne može posmatrati. Izolacija je dokazana na
nivou baze u `RLS-AB-001`, ali **ne** na nivou dokumentnog toka.

---

## 4. AUTOMATIZACIJA

**Šta Vindex automatski radi (dokazano):** ekstrakcija teksta (43/43 imaju
`tekst_sadrzaj`), dodela `predmet_id` i `user_id` dokumentu, ZPP lanac rokova,
kontekst predmeta za AI iz baze.

**Šta ne radi automatski a trebalo bi:** indeksiranje dokumenta u vektorsko
skladište — **0/43**.

**Šta advokat mora sam:** ne mogu da tvrdim, jer tok nije izveden. Ali
**nijedan ručni korak ne bi popravio BR-01**: advokat nema kontrolu kojom bi
pokrenuo indeksiranje, niti bi trebalo da je ima.

---

## 5. DATA LINEAGE

| Identitet | Kreiran | Sačuvan | Prenesen | Korišćen | Prikazan |
|---|---|---|---|---|---|
| `user_id` | ✅ | ✅ 43/43 | ✅ | ✅ | ✅ |
| `client_id` | ✅ (5) | ✅ | ❌ **prekid** — 0 veza ka predmetu | ❌ | ❌ |
| `predmet_id` | ✅ (19) | ✅ 43/43 na dokumentu | ✅ | ✅ | ✅ |
| `document_id` | ✅ (43) | ✅ | ✅ | ⚠ samo kroz `tekst_sadrzaj` | ✅ |
| `chunk_id` | ❌ **ne postoji** | — | — | — | — |
| `source/reference` | ❌ za dokumente predmeta | — | — | — | — |
| `rok_id` | ✅ (`predmet_hronologija.id`) | ✅ 52 | ✅ | ✅ | ✅ |
| `content_sha256` | ❌ **0/43** | — | — | — | — |

---

## 6. BETA BLOCKERS

### BR-01 — Dokument nikad ne postane dostupan AI sloju kao dokument

| | |
|---|---|
| **Tok** | upload → obrada → indeksiranje → AI pitanje o dokumentu |
| **Root cause** | dva nezavisna: (a) Pinecone ingest nije uspeo ni za jedan dokument; (b) `_verify_pred_namespace_ownership` proverava `predmeti.id = session_id`, a `session_id` je sufiks namespace-a, ne `predmeti.id` |
| **Posledica** | `/api/dokument/pitanje` vraća `404` za svaki od 43 dokumenta |
| **Dokaz** | `predmet_dokumenti`: 43 reda, **svi `status='sacuvano'`**, nijedan `'indeksirano'`. Pinecone `describe_index_stats`: 6 `pred_*` namespace-a / 30 vektora, i **svih 6 su orfani** (ne postoje u bazi). Presek {43 sačuvana namespace-a} ∩ {17 `pred_<predmet_id>`} = **0**. |
| **Reprodukcija** | otvoriti bilo koji predmet sa dokumentom → „pitaj o dokumentu" → `404` |
| **Popravljivo pre bete** | (a) da — ponovno indeksiranje; (b) da — uskladiti identitet sesije. **Nije rađeno u ovom prolazu** (mandat zabranjuje popravku u prvom prolazu) |
| **Status** | **OTVOREN** |

### BR-02 — Klijent i predmet nisu povezani

| | |
|---|---|
| **Tok** | klijent → predmet → svi moduli koji koriste klijenta |
| **Root cause** | UNKNOWN. Pisci (`intake`, `onboarding`, `smart_intake`, `copilot`, `api`) upisuju kolone koje **postoje**, ali **svi gutaju grešku** u `logger.warning`/`debug` |
| **Posledica** | 19 predmeta, 5 klijenata, **0 veza**. Naplata (`billing.py:156`), tarife, COI sloj „klijenti", analitika i `case_pipeline` čitaju tu vezu — svi rade nad praznim skupom |
| **Dokaz** | `predmet_klijenti` `count=0`; `predmeti` nema nijednu klijentsku kolonu; 19/19 predmeta ima prazan `tuzilac` |
| **Reprodukcija** | nije izvedena — zato je root cause UNKNOWN |
| **Popravljivo pre bete** | UNKNOWN dok se tok ne izvede |
| **Status** | **OTVOREN** |

---

## 7. NON-BLOCKING DEBT

`content_sha256` NULL na 43/43 · `api_costs` i `ratio_decidendi` ne postoje
(telemetrija/keš) · `feature_usage_log` prazan uz `usage_events` = 2.909 ·
tri sekundarna pisca hronologije gutaju grešku upisa · 6 orfan namespace-a sa
30 vektora u Pinecone-u.

---

## 8. FALSE-GREEN CHECK

Šta bi moglo stvoriti lažan utisak spremnosti:

1. **5.581 test prolazi** — nijedan ne izvršava lanac upload→vektor→pitanje nad stvarnim skladištima.
2. **Sva 43 dokumenta „uspešno" postoje** sa tekstom i `storage_path` — deluje kao da je obrada prošla.
3. **AI odgovara na pitanja o predmetu** — jer kontekst ide iz `tekst_sadrzaj`, pa deluje kao da indeksiranje radi.
4. **Pinecone ima 434.217 vektora** — ali to su zakoni i sudska praksa; korisničkih dokumenata: **0**.
5. **Svi prethodni sprintovi su zeleni** — mereni su domeni, ne spoj domena.

⚠ Peto je najopasnije: **ovaj audit je prvi koji je spojio module**, i tek je tu prelom postao vidljiv.

---

## 9. TEST EVIDENCE

Nijedan postojeći test ne pokriva E2E lanac dokumenta. Sigurnosna izolacija je
dokazana odvojeno (`RLS-AB-001`, stvarnim identitetima). Broj testova je ovde
**irelevantan** za verdikt i namerno se ne koristi kao argument.

---

## 10. FINAL BETA GATE

| # | Uslov | Status |
|---|---|---|
| 1 | nov klijent može biti kreiran | UNKNOWN |
| 2 | nov predmet može biti kreiran | UNKNOWN |
| 3 | klijent i predmet pravilno povezani | **FAIL** |
| 4 | dokument može biti unet | UNKNOWN |
| 5 | dokument može biti obrađen | **FAIL** (0/43 indeksirano) |
| 6 | dokument automatski dostupan AI toku | **FAIL** |
| 7 | dokument ostaje vezan za pravi predmet | PASS (`predmet_id` 43/43) |
| 8 | AI koristi pravi predmetni kontekst | PASS uslovno (iz baze) |
| 9 | odgovor povezan sa izvorom | UNKNOWN |
| 10 | rokovi kroz životni ciklus | UNKNOWN |
| 11 | hronologija kroz tok | YELLOW |
| 12 | podaci se automatski prenose | **FAIL** (dokument→vektor) |
| 13 | nema neočekivanih ručnih mostova | UNKNOWN |
| 14 | nema lažnog success stanja | **PASS** — `sacuvano` vs `indeksirano` je istinito |
| 15 | greške ne ostavljaju polustanje | **FAIL** — 43 dokumenta u trajnom polustanju |
| 16 | drugi korisnik ne pristupa tuđem | PASS (`RLS-AB-001`) |
| 17 | osnovni tok ponovljiv | **FAIL** |
| 18 | advokat ne mora znati arhitekturu | **FAIL** |

---

## 11. OPEN UNKNOWN

1. Ponašanje **trenutnog** koda za nov upload (43 reda su pisana starijom verzijom — sadašnji kod koristi deljeni `_owner_ns` + `predmet_id` metadata filter).
2. Zašto je Pinecone ingest pao za svih 43.
3. Da li kreiranje predmeta iz klijenta uopšte pokušava vezu.
4. Provenijencija do UI-ja.

---

## 12. NEXT ACTION

Zatvoriti **BR-01**: izvesti jedan stvaran upload kroz pokrenutu aplikaciju i
izmeriti da li nov dokument dobije `status='indeksirano'` i vektore. Time se
razrešava i UNKNOWN #1 — bez toga se ne zna da li je BR-01 istorijski dug ili
živi kvar.
