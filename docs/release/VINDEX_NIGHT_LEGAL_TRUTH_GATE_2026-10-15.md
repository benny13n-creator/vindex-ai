# VINDEX — Night Sprint: Legal Truth Gate (15.10.2026)

**Završno stanje:** `PARTIAL_WITH_EXPLICIT_HOLDS`
**QA-08:** `SOURCE_SCOPE_PROVEN` za izričito tražen dokument (oznaka DOK-NN ili tačan naziv fajla) i za evidenciju šta je savetnik stvarno dobio. Ograničenje: dokument opisan samo rečima („prvi ugovor“) se ne prepoznaje; tada sistem ne tvrdi da ga je pročitao, nego kaže koje jeste (vidi D).
**Ništa nije spojeno ni pušteno.** Render nije menjan, nema produkcionih upisa ni migracija. Predmet `QA-TEST-20261015` nije diran.

Oznake dokaza: **PROVEN** = kod, test ili izvršenje; **INFERRED** = obrazloženo, nije izvršeno; **ASSUMED** = pretpostavka; **UNKNOWN** = nedostaje dokaz. Svi testovi koriste sintetičke podatke. Model (OpenAI) je u svim testovima **zamenjen (mock)**, osim ako nije drugačije navedeno.

---

## A. Početno stanje

| Stavka | Vrednost | Dokaz |
|---|---|---|
| `origin/main` | `ed0662be` (Merge PR #37) | `git log origin/main` |
| Produkcija | `ed0662be`, `identity_proven: true` | `GET https://vindex.rs/api/version` (samo čitanje) |
| PR #35 | Draft, head `6da18ded`, baza `3ab9343e` | GitHub API |
| PR #36 | Draft, head `62fc2625`, baza `3ab9343e` | GitHub API |
| PR #38 | Draft, head `50cf7988`, baza `3ab9343e` | GitHub API |
| PR #39 | Draft, izveštaj prethodnog sprinta (`8ea70899`) | GitHub API |
| „VINDEX — CANONICAL OPERATING RULES“ i `VINDEX_ZAVRSNI_QA_IZVESTAJ_2026-10-15.md` | **nisu pronađeni** u repou ni u radnom okruženju | pretraga; UNKNOWN |

**Reprodukovana greška pre izmene (PROVEN, `ed0662be`):** poruka koja ide modelu, iz `routers/multi_agent.py::_kontekst_predmeta`:

| Scenario | Šta model dobija | Tražena činjenica u poruci | Šta V2 kaže |
|---|---|---|---|
| 7 dokumenata, traži se DOK-01 | DOK-07, 06, 05, 04, 03 | **nema** | „Savet je dat uz podatke i dokumente ovog predmeta.“ |
| 12 dokumenata, traži se DOK-01 | DOK-12…08; poruka kaže „Dokumenti: 10“ | **nema** | isto |
| Kontrafaktual (različita činjenica u DOK-01) | dve poruke se razlikuju **samo po slučajnom bezbednosnom tokenu** | nema ni u jednoj | isto |
| Predmet bez dokumenata | samo podaci predmeta | — | isto (lažno) |

## B. Nalazi

| # | Nalaz | Status |
|---|---|---|
| B1 | Savetnik nije video izričito tražen stariji dokument; V2 je tvrdio da je savet „uz dokumente predmeta“ | PROVEN, ispravljeno (#40) |
| B2 | „Vlasništvo potvrđeno“ (`kontekst_predmeta: true`) se prikazivalo kao „dokumenti pročitani“ | PROVEN, ispravljeno (#40) |
| B3 | Case Genome je u poruci modelu označen kao „SINGLE SOURCE OF TRUTH“ | PROVEN, ispravljeno (#40): „AI sažetak, nije izvorni dokument“ |
| B4 | Nijedan sistem ne proverava da li činjenica u odgovoru savetnika stvarno postoji u dostavljenom tekstu | PROVEN (nema koda); HOLD, traži novu arhitekturu |
| B5 | Genome rokove upisuje uvek kao `kritičan`; Rule 6 daje `critical` i prošlom datumu | PROVEN; QA-01 paket, bez izmene |
| B6 | Lažna početna protivrečnost: nema dokaza o determinističkom propustu | INFERRED (model); QA-04 HOLD |
| B7 | #38 šalje 74% sintetičkih zaglavlja modelu (ranije 13%); pri padu OpenAI 159/215 postaje `other` (ranije 28/215) | PROVEN (završni nezavisni pregled) |
| B8 | Moji raniji brojevi za #38 („195 slučajeva, oko 145 ka modelu, ranije oko 12“) bili su netačni; tačno je 215 / 159 / 28 | PROVEN, ispravka |

## C. Matrica zadataka

| Task | Status | Dokaz uzroka | Izmena | Testovi | Reviewer | PR | Rizik |
|---|---|---|---|---|---|---|---|
| 01 QA-08 izvori savetnika | **GO_FOR_FOUNDER_REVIEW** | reprodukcija A–D (A) | `routers/multi_agent.py`, `agenti-predmeta.js` | 43 + 387 savetnik + ceo paket (isti 19 padova kao `main`) + Playwright 50/16 | NO-GO → 1 korekcija → GO WITH NOTES | **#40** | srednji (vidi D.6) |
| 02 QA-06 utemeljenost | **PARTIAL + HOLD** | B4 | deo u #40 (oznake nedostavljenih) | u 43 | isti | #40 | lokatori i provera činjenica ostaju otvoreni |
| 03 PR #36 | **GO_FOR_FOUNDER_RELEASE_REVIEW** | — | nema novih izmena | Playwright 1.195/0 nad `main`+#35+#36; CI isti kao `main` | raniji GO WITH NOTES | #36 | nizak |
| 04 PR #35 | **GO_FOR_FOUNDER_RELEASE_REVIEW** | — | nema novih izmena | provenance + kombinovani scenario nad novim `main`; CI isti | raniji GO | #35 | nizak |
| 05 QA-01 rokovi | **PRODUCT HOLD** | §G | nema | — | — | izveštaj | odluke u paketu |
| 06 QA-04 protivrečnosti | **HOLD** | §G | nema | postojeći testovi | — | — | model-zavisno |
| 07 PR #38 | **REQUIRE PRODUCT DECISION** | B7 | nema | 102/102 klasifikacija | završni nezavisni pregled | #38 | trošak i pad |

## D. QA-08 — izvori savetnika

**D.1 Šta je savetnik ranije dobijao:** 10 najnovijih redova sa punim tekstom, od kojih je prvih 5 išlo u poruku, po 2.500 znakova. Stariji dokument nikad, ni kad je izričito tražen.

**D.2 Šta sada dobija (PR #40, `b73d2921`):**
- izričito tražen dokument (DOK-NN, „dokument br. N“, ćirilica, tačan naziv fajla) ide prvi, do 5.000 znakova;
- ostatak su najnoviji dokumenti, do 2.500 znakova;
- ukupno najviše **5 dokumenata i 12.500 znakova**, isto kao ranije;
- metapodaci se čitaju za sve dokumente, a tekst samo za izabrane.

**D.3 Stariji tražen dokument:** ulazi u poruku. Ako ih je traženo više od 5, višak se izričito prijavljuje kao „nije dostavljen (ograničenje)“.

**D.4 Nedostupan dokument:**
- ne postoji → „ne postoji u ovom predmetu“, ali samo kad je ceo spisak stvarno pročitan;
- greška baze ili odsečen spisak → „nije utvrđeno“;
- bez izdvojenog teksta → „nema izdvojen tekst“;
- greška čitanja teksta → „nije pročitan (nije utvrđeno zašto)“.

Sistemska **EVIDENCIJA IZVORA** stoji na kraju konteksta predmeta, posle Genome-a. Natpis „EVIDENCIJA IZVORA“ iz dokumenta, opisa ili Genome-a se neutrališe. Odgovor nosi `izvori_predmeta` i oznake DOK-NN koje odgovor pominje, a čiji tekst savetnik nije dobio. V2 tada prikazuje upozorenje „te tvrdnje nisu proverene u izvoru“. Zelena poruka se prikazuje samo kad su svi dokumenti dostavljeni u celini.

**D.5 Izolacija korisnika (PROVEN):**
- vlasništvo predmeta se proverava pre svakog čitanja dokumenata;
- oba nova upita filtriraju po `predmet_id` (test proverava dnevnik upita);
- isti naziv fajla ili redni broj kod drugog korisnika ne curi;
- tuđ predmet daje `kontekst_predmeta: false` i `izvori_predmeta: null`;
- mutacija koja uklanja filter `predmet_id` je uhvaćena.

**D.6 Trošak i latencija:**

| | Pre (`ed0662be`) | Posle (`b73d2921`) | Dokaz |
|---|---|---|---|
| DB upiti po pozivu | 4 (3 bez dokumenata) | 4 (3) | PROVEN, harness |
| Redova sa punim tekstom | do 10 | do 5 | PROVEN, kod |
| Redova metapodataka | — | svi (count=exact; PostgREST `max-rows` granica prijavljena kao „nije utvrđeno“) | PROVEN, kod i test |
| Znakova dokumenata u poruci | ≤ 12.500 | ≤ 12.500 | PROVEN, test |
| Ukupna poruka (dokumenti od 7.200 znakova) | 13,0 hilj. | 13,6–13,9 hilj. (+~5%, evidencija) | PROVEN, mock merenje |
| Pozivi modela | 1 po savetniku | 1 po savetniku | PROVEN |
| Latencija (mock, medijana 5) | 18–26 ms | 19–28 ms | PROVEN samo za mock; **stvarna latencija UNKNOWN** |
| Kad je tražen veliki dokument | 5 dokumenata | **4** (tražen uzima 5.000 od istih 12.500) | PROVEN, merenje |

**D.7 Nezavisni pregled:**
- Prvi krug (`c57e6ada`): **NO-GO**. Obavezni nalazi N1, N3 i N4: greška baze prikazana kao „ne postoji“, veznik „dok“ čitan kao oznaka dokumenta, neograničen spisak oznaka. Manji nalazi: N2, N5, N6.
- Jedna uska korekcija (`b73d2921`) zatvara svih šest. Za svaki postoji test, a 6/6 mutacija je uhvaćeno.
- Ponovna provera istog recenzenta, ograničena na N1–N6: **GO WITH NOTES**. Svih šest je zatvoreno. Primeri iz njegovih izlaza:
  - 900 nepostojećih oznaka: poruka 10,9 hilj. znakova po savetniku, ranije 76,9 hilj.;
  - pala baza daje `NEPOZNATO`, nikad „ne postoji“;
  - „dok 3 svedoka“ više nije oznaka dokumenta.
- Dug iz pregleda:
  - Genome nije umotan u granicu poverenja; natpis evidencije se neutrališe samo u latiničnom obliku, a sistemska evidencija je i dalje poslednja i jedina važeća;
  - `DOK.NN` (sa tačkom) se više ne prepoznaje.

**D.7b Ceo Python paket (PROVEN):**
- `ed0662be`: 19 padova / 10.658 prolazi;
- `b73d2921`: 19 padova / 10.701 prolazi.

Skup palih testova je **identičan** (`diff` prazan) i jednak ranijem baznom skupu od 19.

**D.8 Ograničenja koja ostaju:**
- opis dokumenta rečima se ne prepoznaje;
- odgovor koji pominje **naziv fajla** (a ne DOK-NN) nepročitanog dokumenta nije označen;
- stvarni model nije pozvan (mock), pa nije dokazano da model uvek poštuje evidenciju; zato postoji deterministička oznaka u V2;
- `/run` i dalje nema `max_length` na zadatku (postojeće stanje).

## E. QA-06 — utemeljenost u dokumentima predmeta

- **Proverljive reference:** Genome `lokacija` „DOK-NN str.X“ se deterministički razrešava u `dokument_id` predmeta (`shared/genome_contract.py::Razresavac`). Strana je samo „strana_po_analizi“ (ono što je model naveo) i nije proverena. Tako je i označena u V2.
- **Samo nazivi dokumenata:** savetnik (`/api/agents/*`) do sada nije imao nikakvu evidenciju. Sada ima evidenciju dostavljenih dokumenata, ali ne i lokaciju unutar dokumenta.
- **Može li sistem lažno navesti dokument kao konsultovan?** Za oznaku DOK-NN: model to i dalje može napisati, ali V2 sada deterministički označava da tekst nije bio dostavljen (PROVEN, test). Za naziv fajla: može, i to nije označeno (otvoreno).
- **`_proveri_citate_agenta`** proverava samo članove zakona protiv pravne baze, nikad činjenice iz dokumenata predmeta. Ove dve domene nisu pomešane (postojeći test `test_clan_ugovora_nije_dokaz_za_clan_zakona`).
- **Nije moguće postojećim podacima:** provera da tvrdnja odgovora postoji u dostavljenom tekstu, precizna stranica ili pasus, nezavisnost i autentičnost dva dokumenta. To traži lokatore na nivou pasusa i proveru tvrdnji, dakle novu arhitekturu → **HOLD**.

## F. Postojeći PR-ovi

- **#35 (`6da18ded`) — GO_FOR_FOUNDER_RELEASE_REVIEW.**
  - Lokalno spojen na novi `main` sa #36, bez konflikata, bez zajedničkih fajlova sa #37.
  - Testovi provenance, dispečera i event bus-a, plus kombinovani scenario (dva korisnika, PDF + JPG, worker → finalize → dispečer): **prolaze**, uz napomenu: bez #38, „PREDLOG TUŽBE“ se i dalje klasifikuje kao `contract`. To je poznata produkciona greška, nije regresija.
  - CI: isti skup padova kao `main` `ed0662be` (174 / 174 / 195).
  - Napomena: #35 rešava pripisivanje identiteta, ne garantuje trajni upis svakog forenzičkog događaja.
- **#36 (`62fc2625`) — GO_FOR_FOUNDER_RELEASE_REVIEW.** Playwright nad `main`+#35+#36: **20 paketa, 1.195 provera, 0 FAIL**, uključujući `live-nazivi-e2e` (stari zapisi, 404 i delimičan `nazivi.js`). CI isti kao `main`. Prevod ne menja klasifikaciju; prikaz „Ugovor“ nije dokaz ispravne klasifikacije.
- **#38 (`50cf7988`) — REQUIRE PRODUCT DECISION.** Završni nezavisni pregled (jedini dozvoljeni):

  | Mera (215 sintetičkih slučajeva) | Stara heuristika | #38 |
  |---|---|---|
  | Tačno | 118 | 40 |
  | Samouvereno pogrešno | 69 | 16 |
  | Ide modelu (gpt-4o-mini) | 28 (13%) | 159 (74%) |
  | Novi lažni pozitivi / lažno negativni | — | 1 / 83 |
  | Pri padu OpenAI → `other` 0,0 | 28 | **159** |
  | 30 novih zaglavlja: pogrešno / ka modelu | 7 / 7 | 1 / 9 |

  - Tokeni: oko 1,4–2,0 hilj. ulaznih i do 100 izlaznih po pozivu. Na 1.000 dokumenata to je oko 610 poziva više (INFERRED, jer su korpusi namerno teški).
  - Cena u novcu nije računata; treba je uzeti iz važećeg OpenAI cenovnika.
  - Testovi klasifikacije: 102/102.

## G. Rokovi i protivrečnosti

**QA-01** (`QA01_DEADLINE_DECISION_PACKAGE.md`): kandidat za rok upisuju četiri AI pisca.
- Genome upisuje `kritičan` u kodu za svaki rok, a naslov roka piše model.
- Prošli datum može postati kandidat, a na Radnoj listi postaje „kritična“ stavka pregleda.
- Odbijen rok može ponovo nastati ako ga model drugačije formuliše.
- Izvršive posledice ostaju zaključane potvrdom advokata (PROVEN).

Nedostaju odluke o četiri kategorije datuma i o tome ko sme da označi „kritičan“. Nema blokera.

**QA-04:** pravila životnog ciklusa su deterministička i testirana:
- najmanje dve različite tvrdnje;
- `NOT_OBSERVED` nikad nije `RESOLVED`;
- zatvoreni zapisi se ne brišu.

Samu protivrečnost i njenu težinu predlaže model. Nema dokaza o determinističkom propustu za početnu lažnu protivrečnost, a produkcioni predmet nije čitan → **HOLD**. Postojeći testovi (`test_contradiction_v2_domain.py`, `test_ns006_t5_contradictions.py`) ostaju čuvar.

## H. Odluke osnivača

1. **Merge #40 (QA-08)?** Merge pokreće Render deploy.
2. **Merge #36**, zatim **#35**, pojedinačno, po proceduri iz izveštaja #39 §9.3 (provera `/api/version`, 60 minuta logova, rollback na prethodni SHA).
3. **#38:** prihvatiti kompromis (manje samouvereno pogrešnih, ali 5,7 puta više poziva modela i lošije ponašanje pri padu OpenAI) ili zadržati produkciono ponašanje.
4. **QA-01:** pet odluka iz paketa (kategorije, „kritičan“, prošli datumi, zaštita odbijenog roka, legacy čitaoci).
5. **QA-06:** da li pokrenuti posebnu arhitekturu za lokatore na nivou pasusa i proveru tvrdnji.

Rollback za svaki merge: Render „Rollback“ na prethodni SHA ili revert merge commit-a. Podaci se ne menjaju.

## I. Spremnost za betu

| Kategorija | Ocena |
|---|---|
| 1. Kontrolisani sintetički QA | **Spremno** uz #40: sistem sada kaže koje je dokumente savetnik pročitao. |
| 2. Supervizirani pilot sa izabranim testerima i odobrenim podacima | **Uslovno**, posle merge-a #40 i uz uputstvo testerima da dokument traže oznakom (DOK-NN) i da proveravaju svaku tvrdnju u izvoru. Tvrdnje iz odgovora i dalje nisu deterministički proverene (QA-06). |
| 3. Stvarna upotreba na poverljivim predmetima | **NIJE SPREMNO.** Nema provere činjenica iz odgovora, lokatora na nivou pasusa ni produktnog modela rokova; #38 i QA-01 čekaju odluke. |

Ocena u jednoj kategoriji ne prenosi se na sledeću.
