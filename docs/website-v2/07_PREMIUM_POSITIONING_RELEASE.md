# 07 — Premium Positioning & Product Truth (javni sajt), 2026-11-01

Grana `website/premium-positioning` od `main` = produkcija `2c6663a8` (`/api/version` → `commit_source: RENDER_GIT_COMMIT`).
Interni dokument: **ne objavljuje se**, registar `site/funkcije.json` se ne servira (test `test_planovi_razvoja_nisu_javni`).

## 1. Šta se promenilo

| Oblast | Pre | Posle |
|---|---|---|
| Kategorija i hero | „Pravni radni prostor“ / „Od dokumenata do jasnih odluka.“ | „Pravni operativni sistem“ / **„Jedan prostor za čitav predmet.“** |
| Početna | 7 odeljaka: 6 kartica, 4 funkcije u formatu Problem/Šta radi/Korist, tok, **10 sektora**, zaštita, poziv | 5 odeljaka: uvod → 4 vrednosti → tok rada + 3 stvarna ekrana → poverljivost → poziv. Sektori uklonjeni |
| Visina početne | 8.281 px (1440) / 12.517 px (390) | 6.078 px / 8.508 px (−27 % / −32 %; posle prihvatanja §10) |
| Kako radi | 7 koraka × 4 polja („Ne pretpostavlja“ kao zaseban niz upozorenja) | 6 koraka × 3 polja (Vindex / Vi odlučujete / Dobro je znati); materijalne granice zadržane |
| Za advokate | 8 nepovezanih primera | jedan predmet (naknada štete zbog povrede na radu, tužena strana) od tužbe do nacrta, izmišljene okolnosti |
| Funkcionalnosti | 49 stavki, od toga 5 „klasični interfejs“; J01 „V2 koristi istu sesiju“, interna adresa `/app-legacy?posle=app` vidljiva | 46 stavki, sve sa putanjom u aplikaciji; nula oznaka verzije; nova stavka C08 (odluka o protivrečnosti) |
| Bezbednost | izvoz i brisanje „u klasičnom interfejsu“ | stvarna putanja: Podešavanja → Privatnost i podaci (PR #57); sve materijalne činjenice zadržane |
| Beta | „lično upoznavanje sa aplikacijom“ (nepotvrđeno ponašanje) | „prijave pregledamo pojedinačno, uključujemo postepeno“; tri puta razdvojena (rani pristup / sami otvarate nalog / prijava) |

Izbor naslova (od tri kandidata): „Jedan prostor za čitav predmet.“ — kratko, predmet kao centar (MIR-01 smer), tačno danas i
posle Miroslavljevog izdanja; „Ceo predmet. Jedan tok rada.“ — slabije razumljivo; „Od dokumenata do jasnih odluka.“ (staro) —
nagoveštava da Vindex donosi odluke.

**Napomena o sukobu pravila (Canonical Rules §12):** `tests/test_website_public.py::test_pre_auth_ulaz_nema_zastarelih_tvrdnji` zabranjuje
„operativni sistem“ na pre-auth ekranu `/app-legacy` (raniji mandat). Taj ekran se NE menja; nova kategorija važi samo za javni sajt,
po izričitoj instrukciji osnivača. Ako osnivač želi istu kategoriju i na pre-auth ekranu, to je zasebna odluka.

## 2. Usklađivanje registra sa `main` 2c6663a8

Registar je bio proveren 2026-10-20 (`77733e11`). Posle toga spojeno 13 PR-ova (#48–#64). Nalazi (PROVEN, dokaz u kodu):

| ID | Promena | Dokaz |
|---|---|---|
| J07 | `LEGACY_ONLY` → `AVAILABLE_WITH_LIMITATIONS`, javno: Podešavanja → Privatnost i podaci | `frontend-v2-ng/index.html:515-536`, `src/podesavanja-privatnost.js:54,75` (PR #57) |
| H01 | uklonjeno „članovi i uloge se uređuju u klasičnom interfejsu“ | `src/podesavanja-kancelarija.js` (PR #57) |
| H02 | `LEGACY_ONLY` → `AVAILABLE_WITH_LIMITATIONS`, **javno: ne** (poziv se ne šalje e-poštom, prihvatanje samo u klasičnom prikazu, beta za samostalne advokate) | `podesavanja-kancelarija.js:3-9`, `kancelarija.js:55` |
| A09, D09, G03 | ostaju samo u klasičnom prikazu → **javno: ne** (OMIT) | nema poziva iz `frontend-v2-ng` |
| D02 | + održano / odloženo / otkazano | `src/rocista-predmeta.js:20-23`; `e2e:n3-rocista` 24/24 (PR #64) |
| C08 (nova) | odluka advokata o protivrečnosti | `routers/sporna_tacka.py`, `src/analiza-predmeta.js:128-170`; `e2e:s02-protivrecnost` 21/21, `e2e:s02-tacka-vise` 11/11 |
| J01 | bez „V2“ i bez interne adrese u javnom tekstu | — |
| D07 | `IMPLEMENTED_NOT_EXPOSED` → `EXPERIMENTAL`, javno: ne | v. §4 |
| K02 | plan ostaje, ograničenje ispravljeno | v. §4 |
| F06 (nova) | `EXPERIMENTAL`, javno: ne — nacrt iz spisa (MIR-03) | v. §3 |
| status `LEGACY_ONLY` | javna oznaka `null`; generator ga više ne prikazuje | `scripts/gradi_sajt.py` `JAVNI_STATUSI` |

Nije dodato (OMIT, nedovoljan dokaz u CI-ju): izveštaj o predmetu (PDF), status fakture izdata/plaćena, hronologija iz dokumenata —
browser testovi postoje (`live-n5`, `live-n6`, `live-ba01-hronologija.mjs`) ali nisu upisani u `package.json` i ne izvršavaju se.

## 3. Evidencija tvrdnji (sve značajne javne tvrdnje)

Status: PC = PROVEN_CURRENT, PL = PROVEN_LIMITED. Odluka: P = PUBLISH, Q = QUALIFY, O = OMIT, N = PREPARE_NOT_PUBLIC.

| # | Formulacija (skraćeno) | Gde | Status | Dokaz (registar / kod / test) | Granica | Odluka |
|---|---|---|---|---|---|---|
| 1 | „Pravni operativni sistem“, „Jedan prostor za čitav predmet.“ | `/` uvod, title | pozicioniranje | Canonical Rules §1 | kategorija, ne funkcija | P |
| 2 | dokumenti, činjenice, dokazi, rokovi, pravna pitanja i nacrti jednog predmeta u jednom toku | `/` uvod, meta | PL | A06, B01–B05, C01–C04, D01–D05, E01, F01 | deo zavisi od paketa naloga | Q (katalog i /beta: „zavise od paketa“) |
| 3 | podaci i tvrdnje izdvojeni iz dokumenata vezani za dokument; rok, podatak i nacrt važeći tek kad advokat potvrdi | `/`, `/kako-radi` | PC (u tom obimu) | J03, C02, D01, B04, F02 | ne važi za ručne unose; stavka analize može imati poreklo UNKNOWN (v. §10) | P |
| 4 | član koji ne postoji u izvorima se odbija; kada izvori nisu dostupni, to piše | `/` vrednost 03 | PL | E01 (`verify:live-pravno-pitanje`) | baza propisa nije potpuna | Q (`/kako-radi` k5) |
| 5 | predloženi rok, podatak, protivrečnost i nacrt važeći tek posle odluke; AI rezultat označen | `/` vrednost 04 | PC | D01, B04, C08, F02, J03 | — | P |
| 6 | više dokumenata odjednom; OCR ćirilica/latinica; vrsta + polja sa pouzdanošću | `/`, `/kako-radi`, `/za-advokate` | PL | B01–B04; OCR korak production-runtime (67 passed, PR #64) | kvalitet skena; .doc nije podržan | Q |
| 7 | Rad na predmetu: ročišta, beleške, hronologija, zadaci; Analiza sa poreklom; šta se promenilo i sledeći korak | `/` ist-2 | PL | A06, D02, D05, C01, C04 | deo analize je AI, zavisi od paketa | Q |
| 8 | protivrečnost potvrđujete ili odbacujete; posle promene izvora ponovo čeka | `/`, `/kako-radi` k3, C08 | PC | `routers/sporna_tacka.py`; e2e s02 21/21, 11/11 | — | P |
| 9 | Danas: radna lista, potvrđeni rokovi i ročišta 30 dana; rok obaveza tek posle potvrde | `/` ist-3, `/kako-radi` k4 | PC | D01, D03, D04 | potvrda ≠ provera tačnosti (piše) | P |
| 10 | ročište održano / odloženo / otkazano | `/kako-radi`, `/za-advokate`, D02 | PC | e2e:n3-rocista 24/24 | istorija izmena bez ekrana (ne tvrdi se) | P |
| 11 | kalkulator zastarelosti uz zakonski osnov; prekid i zastoj se ne računaju | `/kako-radi`, `/za-advokate` | PL | D06 | prekid/zastoj | Q |
| 12 | nacrt kao polazna tačka, označena mesta bez potkrepljenja, overa tačno sačuvanog teksta, Word | `/kako-radi` k5, `/za-advokate` | PL | F01–F03 | nacrt iz opisa korisnika; ništa se ne šalje sudu | Q |
| 13 | savetnik razmatra predmet iz izabranog ugla | `/kako-radi` k5 | PL | E02 | status provere citata se prikazuje | Q |
| 14 | stavke po tarifi/satu/iznosu, tajmer, nacrt fakture (nije izdata faktura) | `/kako-radi` k6, `/za-advokate` | PL | I01–I03 | nije poslata/prijavljena u SEF | Q |
| 15 | server vraća samo predmete kojima nalog ima pristup | `/` poverenje, `/bezbednost` | PL | J02 | servisni ključ; granica na serveru (piše na /bezbednost) | Q |
| 16 | izvoz ZIP i anonimizacija iz Podešavanja | `/` poverenje, `/bezbednost`, J07 | PL | PR #57; `test_opis_izvoza_i_brisanja_odgovara_kodu` | bez originala; spisi se zadržavaju | Q |
| 17 | probleme i netačne odgovore prijavljujete iz aplikacije | `/`, `/beta` | PC | `routers/support.py`, `src/prijava-problema.js` (test_website_v3_rast §4–5) | — | P |
| 18 | prijave pregledamo pojedinačno; automatska potvrda se ne šalje | `/beta`, `sajt.js` | PC | `routers/waitlist.py`; forma: 7 scenarija u Chromium-u | — | P |
| 19 | nalog možete otvoriti sami; ograničen broj kredita | `/beta` | PC | J01; `test_registracija_je_stvarno_otvorena` | broj kredita se ne navodi | P |
| 20 | dobavljači, lokacije, SCC nije potvrđen, bez rezervnih kopija, Pinecone segmenti, bez sertifikacije | `/bezbednost` | PC | `test_bezbednost_ne_krije_materijalne_cinjenice` | — | P (nepromenjeno) |
| — | „Lično upoznavanje sa aplikacijom“ | `/beta` (staro) | UNKNOWN | nema dokaza o procesu | — | O |
| — | 10 sektora / „moguća primena“ | `/` (staro) | REJECTED (MIR-04) | `MIR001_TASK_LEDGER.md` MIR-04 | — | O |
| — | „Vindex danas ne šalje podsetnike“ | `/kako-radi`, `/za-advokate` (staro) | REJECTED (zastarelo) | v. §4 | — | O |
| — | znanje kancelarije na početnoj | `/` (staro) | PL, bez stvarnih zapisa | G01/G02: vrednost nije empirijski potvrđena | — | O na početnoj (ostaje u katalogu sa granicom) |

## 4. Email podsetnici — zašto sajt ćuti

PROVEN: podešavanje postoji (Podešavanja → Obaveštenja, PR #53/#57); slanje postoji u kodu i ne zavisi samo od GitHub cron-a
(`routers/email_notif.py` `proveri_hitne_podsetnike` posle potvrde roka/ročišta; petlja na Render-u, `_petlja_ukljucena`).
UNKNOWN: Render pauza/petlja; isporuka nikad nije posmatrana (`LIVE_EMAIL_DELIVERY_NOT_VERIFIED`, `BOJAN_BETA_AUTOMATION_CLOSURE.md`).
Zato je stara rečenica „Vindex danas ne šalje podsetnike“ netačna, a tvrdnja „šalje“ nedokazana. Odluka: sajt ne kaže ni jedno
(test `test_podsetnici_se_ne_tvrde_ni_poricu`).

## 5. Miroslav (MIR-01…MIR-05) — matrica spremnosti

Izvor: `docs/v2-execution/MIR001_TASK_LEDGER.md` (definicije :57-61, presuda :424-428), `MIR001_FINAL_CLOSURE_REPORT.md`;
za MIR-03 noviji `MIR001_C3B_FINAL_CLOSURE_REPORT.md` (§8 ograničenja kvaliteta, §10 presuda) i
`MIR001_FINAL_RELEASE_GATES_LEDGER.md` (GATE-R1…R4, :339). Kod je u `main` od `30cfbd5a` (predak `2c6663a8`); to nije
dokaz da je tok pušten i dostupan korisniku u produkciji.

| MIR | Presuda u ledgeru | Šta sajt danas kaže | Šta ne kaže | Dokaz potreban za objavu |
|---|---|---|---|---|
| MIR-01 povezan predmet | PARTIAL_READY, ograničenja obelodanjena; LIVE nije dokazan | narativ „jedan prostor za čitav predmet“; samo pojedinačno dokazane funkcije (prijem, poreklo, protivrečnosti, stanje predmeta) | „Vindex čita ceo spis“, broj dokumenata/strana, sinteza preko celog spisa | LIVE prijem stvarnog višedokumentnog spisa (≥7 procesnih dokumenata) + prihvatanje korisnika |
| MIR-02 strategija iz spisa | „Da, kao radni materijal“; DEBT-MIR-04/05 otvoreni | savetnik razmatra predmet iz izabranog ugla (E02, postojeće) | strategija „iz spisa“, procena ishoda | zatvoreni DEBT-MIR-04-1/2; merenje kvaliteta nad dugim stvarnim spisom |
| MIR-03 nacrt iz spisa | kontrola: `C3B_CONTROLLED_DRAFTING_READY`; puštanje: GATE-R1…R4 PASS → `READY_FOR_FOUNDER_PRODUCTION_APPROVAL`; kvalitet AI teksta: materijalna ograničenja ostaju (v. ispod) | nacrt kao polazna tačka iz opisa advokata (F01–F03) | nacrt iz spisa, „spreman za sud“, „proveren“ nacrt | odobrenje osnivača i potvrđeno puštanje (uklj. migraciju 141 i odluku o izvodu DOK-nn); posmatrana dostupnost korisniku u produkciji; prihvatanje stvarnog korisnika |
| MIR-04 korporativni rad | BLOCKED_REQUIREMENTS_DETAIL | ništa (sektori uklonjeni) | ugovori, korporativni timovi, due diligence | definisani procesi (TASK-09) + izgrađen i proveren tok |
| MIR-05 kontrolisana proaktivnost | BLOCKED_AUTHORITY (migracija 136, cron) | posledice radnji u predmetu kroz Danas/Rad (postojeće, deterministički) | pozadinska/dnevna AI obrada, „Vindex je pripremio“ | odobrena aktivacija osnivača, primenjena 136, posmatran rad u produkciji |

Arhitektura je spremna bez novog redizajna: nova sposobnost ulazi kao stavka registra (`javno: true` posle dokaza), jedan
`istaknuto` blok na početnoj (tok već ima korak „Pitanje i nacrt“) i jedan korak u `/za-advokate`. Bez prekidača u runtime-u.

### Neobjavljeni kandidat-tekstovi (PREPARE_NOT_PUBLIC — ne stavljati u `site/_izvor/` pre dokaza)

- **MIR-03 / F06**: „Radni predlog nacrta iz dokumenata predmeta: savetnik za pisanje podnesaka predlaže tekst uz izvore
  iz dokumenata koje ste priložili. Predlog nije proveren tekst: svaku stavku usvajate ili odbijate, tekst pišete i
  ispravljate vi, a kao Word dokument se izvozi samo tekst koji ste odobrili.“ (Ranija verzija kandidata obećavala je da
  napomena kaže „šta je sud već odlučio“; slepa merenja pokazuju da predlog ponekad prećuti odluku suda, pa je izbačeno.)
- **MIR-01**: „Dokumenti celog spisa, od tužbe do zapisnika, ulaze u isti predmet; Vindex pokazuje gde se navodi stranaka
  razlikuju i šta je sporno.“
- **MIR-05 / K01**: „Kada se u predmetu nešto promeni, Vindex pripremi kratak pregled promene koji čeka vaš pregled. Ništa se
  ne izvršava bez vas.“
- **D07 / K02**: „Podsetnik e-poštom pre roka koji ste potvrdili, uz izbor koliko dana unapred.“

## 6. Provera javnih oznaka (hard gate §9)

Test `tests/test_website_premium_pozicioniranje.py` meri vidljiv tekst + `title`, meta/OG opise, `alt`, `aria-label` svih 6
stranica i poruke forme u `sajt.js`: **0 pogodaka** za V2/V3, Version 2, verzija 2, legacy, klasičn, stara/nova aplikacija,
nova generacija, preview; 0 za MIR-, Miroslav, Bojan, sprint, migracij, CI, PR #, interne kodove; 0 za podsetnike; 0 za
garancije/„uvek tačno“/„automatski šalje“. Tehničke adrese `/v2/site/…` i `data-status` nisu korisnički tekst i ostaju.

Mutacije (vrati staro ponašanje → test mora da padne): **9/9 ubijene** — oznaka „V2“ u formulaciji, javna LEGACY stavka,
LEGACY u generatoru, rečenica o podsetnicima, vraćeni sektori, „nacrt iz spisa“, „garancija tačnosti“, putanja anonimizacije
„klasični interfejs“, interni naziv na /beta.

## 7. Pregledač (Chromium, lokalni server, sintetički podaci)

- 6 stranica × 7 širina (320, 375, 390, 768, 1024, 1440, 1920): `scrollWidth == clientWidth` svuda, 1 H1, poziv vidljiv na prvom
  ekranu, 0 grešaka konzole, 0 neuspelih resursa (pre i posle).
- Mobilni meni, nazad/napred, ponovno učitavanje, „Preskoči na sadržaj“ + vidljiv fokus tastature: PASS.
- Kontrast novih elemenata 6,20–14,67 : 1 (≥ 4,5).
- Bez JavaScript-a: sav sadržaj vidljiv na 6 stranica (posle CSS ulazne animacije), /beta kaže da je potreban JavaScript.
- `prefers-reduced-motion`: bez pokreta. Spori snimci (3 s): H1 i poziv vidljivi pre slika.
- Forma (POST presretnut u pregledaču, **nijedan upis**): uspeh, 422, 429, 500, 503, 200 bez `ok`, prekid veze — nijedan
  neuspeh ne prikazuje uspeh. Forma NIJE provereno end-to-end na produkciji (namerno: zabrana upisa).
- Snimci: `docs/website-v2/snimci/premium-pre-*.webp` (produkcija `2c6663a8`) i `premium-posle-*.webp` (grana).

## 8. Nezavisni adversarijalni pregled (5 perspektiva) i ispravke

Pregled je radio nad kodom, ne nad registrom. Svaki nalaz je ponovo proveren u kodu pre ispravke (PROVEN).

| # | Ozbiljnost | Nalaz | Dokaz | Ispravka |
|---|---|---|---|---|
| 1 | HIGH | /za-advokate: „rok prepoznat u dopisu suda čeka potvrdu na Danas“, a rok za odgovor teče od dostavljanja i ne preračunava se u datum | `uploaded_doc/deadline_parser.py` N03-FD3; `routers/rok_odluka.py` | „Takav rok Vindex ne preračunava sam: datum roka unosite vi…“ |
| 2 | MEDIUM | „označena mesta gde član nije potkrepljen izvorom“: samoprovera modela propušta opštepoznate članove, a bez provere nema oznaka | `shared/drafting_grounding.py:34-38`; `nacrt-predmeta.js:562` | „gde model nije našao izvor za navedeni član; i neoznačene navode proveravate“ (F01, /kako-radi, /za-advokate) |
| 3 | MEDIUM | anonimizacija ne gasi prijavu na nalog (prikriveno) | `routers/gdpr.py:232-235`; `frontend-v2-ng/index.html:532` | /bezbednost i J07: „Anonimizacija ne gasi prijavu na nalog.“ |
| 4 | MEDIUM | „Odobren nacrt postaje rad kancelarije“, a ne uvek (ocena kvaliteta, indeksiranje, nacrt iz spisa) | `nacrt-predmeta.js:145-148` | uklonjeno sa /za-advokate; G02: „može postati … aplikacija to kaže“ |
| 5 | MEDIUM | „prijava za rani pristup“ vs samostalna registracija: posetilac misli da mora da čeka | `/api/register` | završni odeljak početne: „Nalog sa ograničenim brojem kredita možete otvoriti i sami, u aplikaciji.“ |
| 6 | LOW | uvod: „svaki podatak važeći tek kad ga advokat potvrdi“ — stavke AI analize se ne potvrđuju | C01 | „predloženi rok, podatak i nacrt postaju važeći…“ |
| 7 | LOW | „podatke naloga izvozite“ — izvoz nema profil i podešavanja | `frontend-v2-ng/index.html:519` | „podatke predmeta izvozite“ |
| 8 | LOW | kalkulator ne računa duži rok za štetu iz krivičnog dela (čl. 377), relevantno za povredu na radu | `zastarelost.py:42,68` | dodato u /kako-radi, /za-advokate i D06 |

Regresioni test: `test_granice_iz_nezavisnog_pregleda_ostaju_vidljive` (mutacija nalaza 1 → test pada).
Proizvodni nalaz VAN sajta (ne ispravlja se ovde): `routers/zastarelost.py:95-170` (`/api/rokovi/procesni`, kalkulator procesnih
rokova u klasičnom prikazu) ima pogrešne vrednosti (odgovor na tužbu kao 30 radnih dana, neradni dani suda, brojevi članova).
Sajt ga ne pominje (D10, javno: ne); zaseban zadatak za osnivača.

## 9. Preostali rizici

- Snimci aplikacije su od 2026-10-21/24; tokovi koje prikazuju (registar, dokumenti, rad na predmetu, Danas) nisu promenjeni na
  način koji bi ih učinio netačnim, ali novi elementi (dugmad odluke o protivrečnosti, status ročišta) nisu na snimcima.
- Tipografija sajta je IBM Plex Sans + Source Serif 4 (zatečeno); Canonical Rules §8 navodi Source Sans 3 za UI. Nije menjano
  (zabrana rebrendiranja); usklađivanje je odluka osnivača.
- Tvrdnje sa granicom „zavisi od paketa naloga“ (analiza, savetnik, nacrt) su na početnoj opisane bez te granice; granica je u
  katalogu i na /beta.

## 10. Prihvatanje osnivača (vizuelni smer odobren, spajanje još nije) — ispravke nad `77bfc916`

### A. Preciznost tvrdnji

Univerzalne formulacije su zamenjene tačnim obimom. Dokaz da univerzalna verzija nije tačna:
- `shared/genome_contract.py:61,197,211`: klasa porekla `UNKNOWN` („poreklo nije zabeleženo — neproveren“);
- `frontend-v2-ng/src/analiza-predmeta.js:18`: prikaz „Poreklo nepoznato“;
- registar C01: starije analize dobijaju vezu sa izvorom tek pri osvežavanju; E02: status provere citata može biti „nepoznato“;
- beleške, zadaci i ročišta koje advokat unese nemaju dokument kao izvor.

| Bilo | Sada | Gde |
|---|---|---|
| „Svaki podatak ostaje vezan za izvor iz kog potiče“ | „Podaci i tvrdnje izdvojeni iz dokumenata ostaju vezani za dokument iz kog potiču“ | `/` uvod, meta opis |
| „Svaki podatak sa svojim izvorom“ / „Odluka uvek ostaje vama“ | „Izdvojeni podaci vezani za dokument“ / „Konačnu odluku donosite vi“ | `/` uvod |
| „odakle potiče svaki podatak“ | „iz kog dokumenta potiče izdvojeni podatak“ | `/` Zašto Vindex |
| „svaku stavku sa poreklom“ | „uz oznaku porekla stavke: dokument, vaša potvrda, proračun ili AI analiza“ | `/` istaknuto 2 |
| „Svaka stavka analize nosi poreklo, a AI rezultat … čeka vašu odluku“ | „Stavke analize su označene po poreklu, a AI rezultat kao AI rezultat. Rok, podatak i nacrt čekaju vašu odluku.“ | `/` poverenje |
| C01/J03: „Svaka stavka (analize) nosi poreklo …“ | „Stavke su označene po poreklu …; kada poreklo nije zabeleženo, i to piše“ | `/funkcionalnosti` |
| E02: „Uz svaki odgovor … provereni, neprovereni ili ih nema“ | „… da ih nema ili da ishod provere nije poznat“ | `/funkcionalnosti` |
| „Svaki [pružalac] dobija samo podatke potrebne za svoj deo posla“ (minimizacija nije dokazana) | „Tabela pokazuje koji pružalac obrađuje koje podatke.“ | `/bezbednost` |

Zadržane univerzalne tvrdnje (dokazane u celom obimu): „Svaki predloženi rok potvrđujete ili odbijate“ (lanac odluka o rokovima,
`e2e:rok-odluka`); „Svaka funkcija na ovoj stranici dostupna je u aplikaciji, uz putanju“ (generator objavljuje samo javne statuse,
test traži „U aplikaciji:“ na svakoj stavci); „provera na serveru pri svakom zahtevu“ (J02). Regresija:
`test_poreklo_se_ne_tvrdi_univerzalno` (6 stranica); mutacija (stara početna i katalog) → 2 pada.

### B. Prazni okviri na `premium-posle-pocetna-390.webp`

**Presuda: artefakt snimanja, ne kvar.** Stari snimač (`snimi.py`) pravio je snimak cele strane odmah posle `networkidle`, bez
skrolovanja: slike sa `loading="lazy"` ispod prvog ekrana se tada još ne traže, a `.otkrij` sekcije koje nikad nisu bile u ekranu
ostaju na `opacity: 0`. Ponašanje sajta nije menjano.

Dokaz (Chromium, bez `reduced-motion`, 320/375/390 + 1440, svih 6 stranica):
- pre skrolovanja `dokumenti.webp`, `rad-predmeta.webp` i `danas.webp` imaju `complete=false` (stanje koje je stari snimač video);
- posle skrolovanja do svake slike: `complete=true`, `naturalWidth` 780/1600, ispravan `currentSrc`, puna providnost, isečak nije
  prazan (std. odstupanje piksela 10,7–32,6); 0 neuspelih zahteva, 0 odgovora ≥ 400, 0 grešaka konzole;
- 162/162 `.otkrij` elementa postaje vidljivo čim uđe u ekran, i posle skoka sa dna strane (18 kombinacija stranica × širina).

Novi snimci (postepeno skrolovanje, provera da nijedna sekcija nije skrivena, pa snimak): `premium-posle-pocetna-320/375/390`,
`premium-posle-kako-radi-390`, `premium-posle-za-advokate-390` i ponovo `premium-posle-*-1440` (stari 1440 snimci su bili od pre
ispravki iz §8).

Zamke merenja (nisu kvar sajta): lokalni server posle mnogo zahteva sa 127.0.0.1 vraća 429 na `sajt.js`, pa sekcije ostaju bez
klase `vidljivo` — restart servera pre svakog merenja; `scroll-behavior: smooth` uz brze skokove u skripti može preskočiti mali
element, zato skripta skroluje sa `behavior: 'instant'`; provera „bez JS“ čeka 1,2 s na CSS ulaznu animaciju heroja.

### C. MIR-03

Matrica u §5 i registar F06 usklađeni su sa `MIR001_C3B_FINAL_CLOSURE_REPORT.md` i `MIR001_FINAL_RELEASE_GATES_LEDGER.md`. Stara
oznaka „C3b FAIL“ više nije tačna. Kandidat-tekst MIR-03 ostaje neobjavljen.
