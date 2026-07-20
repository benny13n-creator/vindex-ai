# VINDEX AI — UX Simplification Strategy

**Status: FAZA 1, SAMO AUDIT. Nijedna linija koda nije menjana.**
Implementacija čeka završetak CONTRACT 01 ručnog prolaza (aktivan
sprint plan) — ovaj dokument je strategija za POSLE toga, ne sledeći
zadatak.

**Odnos prema `VINDEX_UX_SIMPLIFICATION_AUDIT_2026-07-20.md`:** taj
dokument (napisan par sati ranije istog dana) je stranica-po-stranicu
audit sa 8-pitanja rubrikom i file:line dokazima. Ovaj dokument koristi
ISTI kod-dokaz (ne ponavlja istraživanje od nule) ali ga organizuje
kroz drugačiju analitičku sočivu koju je founder tražio (First 5
Minutes Test, Cognitive Load Audit, Information Hierarchy L1/L2/L3,
Google Principle Test, Zero Thinking Flow) i drugačiji izlazni format
(Top 10 rangirano P0-P3, Nova IA, 10 trajnih pravila, 3-sprint roadmap,
finalni Da/Ne verdikt). Gde se nalazi preklapaju, citiran je isti
file:line dokaz — ne izmišljaju se novi brojevi da izgledaju kao novo
otkriće.

---

# Executive Summary

**Najveći problem:** Vindex AI ne pati od nedostatka funkcija — pati od
toga što SVAKA funkcija pokušava da bude vidljiva odjednom. Četiri
nezavisna AI "glasa" na Dashboard-u, tri skor-widgeta na Pregled
predmeta, sedam AI moda pre prvog pitanja, 22 sekcije u Podešavanjima
— obrazac se ponavlja na svakom glavnom ekranu: **funkcija postoji,
radi ispravno, ali se prikazuje kao da je jednako važna kao sve ostalo
na ekranu, umesto da bude sakrivena dok ne zatreba.**

**Najveća prilika:** kod već sadrži DOKAZ da tim zna kako da reši ovaj
tačan problem — Case Genome panel (`_caseDnaRender`) je 2026-07-19
prošao kroz identičnu disciplinu (sažetak-na-vrhu, detalji-iza-klika,
jedan trust-signal red) i danas je najbolje organizovan ekran u celoj
aplikaciji. Rešenje za Dashboard/Pregled predmeta/AI hub nije novi
dizajn-jezik — kopiranje obrasca koji već postoji i već radi.

**Drugi najveći problem:** "jedan koncept = jedan izvor istine" pravilo
je ove iste sesije već kršeno i POPRAVLJENO jednom (G-027, procesni
rizik Cockpit vs. Matter Intelligence) — ali isti obrazac postoji
nepopravljen na Dashboard-u (4 izvora "šta se danas dešava") i u
modal-komponentama (2 paralelne implementacije istog mehanizma). Ovo
nije izolovan bug — ovo je ponavljajući obrazac koji zaslužuje
STRUKTURNO rešenje (pravilo za svaki budući razvoj), ne pojedinačne
zakrpe (formalizovano niže kao Pravilo 1 od 10).

---

# Current UX Diagnosis

## First 5 Minutes Test

Pretpostavka: advokat prvi put ulazi u Vindex, bez obuke, bez osobe
pored sebe.

**Šta vidi prvo (posle logina, `dash_load()`→`_dashRender()`,
`vindex.js:1107-1620`):** pozdrav + datum, dugme "+ Novi predmet",
dugme "Izveštaj", pretraga koja ne radi (`title="dolazi uskoro"`,
`vindex.js:1467`), zatim ODMAH četiri odvojena bloka koja svaki
tvrde da sumiraju "stanje kancelarije" — Health Index (score/100 +
"Chief Partner" tekst), AI Command Center ("Analizirao sam X
predmeta..."), 4 KPI kartice, Jutarnji brifing (treći AI tekst), dva-
kolonski raspored sa još 5 podsekcija, "Pravni alati" 4 kartice.

**Da li zna gde da klikne?** Ne odmah — nema JEDNOG jasnog fokusa.
Postoji 6+ vizuelno ravnopravnih blokova pre nego što korisnik vidi
bilo šta specifično za NJEGOV predmet (osim ako ima aktivan hitan rok,
u kom slučaju se "hitno" pojavljuje u 3 od tih 6 blokova istovremeno).

**Da li razume šta sistem radi?** Delimično — svaki pojedinačni blok
ima jasnu poruku, ali njihov ZBIR ne komunicira "ovo je JEDAN pametan
sistem" nego "ovo je nekoliko alata zalepljenih na jednu stranicu."

**Gde zastaje / gde mora da razmišlja?** Tačno na Dashboard-u, pre nego
što uopšte otvori predmet. "Da li da čitam Health Index ili Command
Center ili Jutarnji brifing — koji je merodavan?" je pitanje koje
korisnik ne bi trebalo da postavi sebi, a trenutna struktura ga
direktno postavlja.

## Cognitive Load Audit (po ekranu)

| Ekran | Odjednom vidljivih blokova | Nezavisnih AI/izvora | Ocena |
|---|---|---|---|
| Dashboard | ~10 (topbar, Health Index, CC Briefing, 4×KPI, Jutarnji brifing, 2 kolone×3 sekcije, Pravni alati) | **4** (Health Index/CIO/CC/Briefing) | **Kritično** |
| Pregled predmeta | ~9 (CCC akcije, quick action, Matter Intel bar, status panel, Cockpit, Case Ready Score, Beleške, Zatvori, ZPP rokovi, Ugovor, Portal, Pravni alati) | **3** (Matter Intel/Cockpit/CRS — G-027 delom rešeno) | **Visoko** (poboljšava se) |
| Case Genome | 2-4 (Pregled sažetak + AI Provera + Na osnovu/Nedostaje, detalji iza toggle-a) | 1 (jedan Genome objekat) | **Nisko — dobar primer** |
| AI funkcije (Vindex Intelligence hub) | 7 mod-pilula + guide + chip-ovi + input, PRE odgovora | 1 po modu (nema unakrsnog preklapanja) | **Srednje** (broj opcija, ne broj izvora) |
| Dokumenti (top-level tab) | 2 redirect kartice | 0 | **Nisko — ali nepotrebna stranica** |
| Rokovi | Mesec/Lista + 3 export dugmeta + kalendar | 0 (G-026 credit panel bug je vidljivost bug, ne AI izvor) | **Nisko** |
| Klijenti | Lista + 6 profil podtabova | 0 | **Nisko — standardan CRM obrazac** |
| Podešavanja | **22 sekcije** (17 vidljivih korisniku, 5 admin-only) u jednom dugom scroll-u | 0 | **Visoko za broj sekcija, ali prihvatljivo za "namerno poseti" ekran** |

## Information Hierarchy Audit (L1/L2/L3)

**Dashboard — trenutno stanje: SVE je L1.** Nema L2/L3 razdvajanja —
Health Index, CC Briefing, Jutarnji brifing, KPI red, dve kolone i
Pravni alati su svi renderovani odmah, bez ijednog collapse/toggle.
Jedino "Detaljna analiza" unutar CC Briefing kartice (`cc-ai-nalazi-wrap
hidden`, `vindex.js:1393`) je stvarno L2 (učitava se async, sakriveno
dok ne stigne).

*Predlog klasifikacije za redizajn (ne trenutno stanje):*
- **L1 (mora biti odmah vidljivo):** jedan spojen "šta zahteva pažnju
  danas" blok, 4 KPI broja, prioritetni predmet.
- **L2 (jedan klik):** puna lista hitnih predmeta/rokova/ročišta,
  billing detalji, novi dokumenti.
- **L3 (sakriveno dok se ne traži):** Pravni alati kartice (već postoje
  u sidebar-u), portfolio/CIO detaljna analiza, health komponente
  breakdown.

**Pregled predmeta — trenutno stanje: mahom L1.** Skoro sve (3 skor-
widgeta + 4 admin sekcije) je uvek vidljivo u glavnom scroll-u. Jedini
postojeći L2/L3 primer je "Zatvori predmet" dugme koje otkriva formu
(`pred-zatvori-form`, display:none dok se ne klikne) — obrazac postoji,
nije dosledno primenjen na ostale admin sekcije.

**Case Genome — trenutno stanje: ISPRAVNO L1/L2/L3.** "PREGLED" red je
L1, "Detaljna analiza →" toggle je tačna L2/L3 granica, AI Provera
ostaje namerno L1 (trust signal se ne sme sakriti — ispravna
arhitektonska odluka, ne previd, dokumentovano u samom kodu).

**Podešavanja — trenutno stanje: mešano.** Većina sekcija je uvek-
vidljiva (Nalog, Dokumenti, Plan, itd.) — prihvatljivo za Podešavanja
kontekst gde korisnik svesno traži konkretnu stavku, ne skenira ekran
pasivno. "Detaljni izveštaji" obrazac iz Finansija (collapse dugme) NIJE
primenjen ovde, a mogao bi biti za ređe korišćene sekcije (Integracije,
SEF, SMS podešavanja).

## Google Principle Test

*"Da li bi Google ovako prikazao ovu informaciju?"*

- **Dashboard:** Ne. Google proizvodi (Gmail prioritetni inbox, Google
  Analytics pregled) imaju JEDAN primaran signal na vrhu, ne četiri
  konkurentska narativa. Google princip bi spojio Health Index/CC
  Briefing/Jutarnji brifing/CIO u jedan "danas" blok sa jednim glasom.
- **Pregled predmeta:** Delimično. Google Workspace obrazac (npr.
  Google Drive "Priority" panel) pokazuje JEDAN status po stavci, ne
  tri paralelna skora za isti koncept — G-027 je ispravio PODATAK, UI
  konsolidacija (Sekcija 3, prethodni audit) je preostali korak.
- **Case Genome:** Da. Sažetak-pa-detalji je doslovno Google Search
  "featured snippet + 'more results'" obrazac — ovo je najbliže Google
  principu u celoj aplikaciji danas.
- **AI funkcije:** Delimično. Google-ov "jedan search box, sistem
  razume nameru" princip bi favorizovao JEDNO polje za unos sa AI koji
  prepoznaje da li je pitanje/analiza/nacrt, umesto da korisnik prvo
  bira mod od 7 opcija. Ovo je veći, arhitektonski zahvat — flagovano u
  Roadmap-u niže kao Sprint 3, ne Sprint 1.
- **Podešavanja:** Da, u velikoj meri — Google Podešavanja (Gmail,
  Workspace admin) takođe imaju desetine sekcija u jednoj dugačkoj
  strani, jer je to prihvaćen obrazac za "svesno traženje", ne za
  pasivno skeniranje. 22 sekcije ovde NIJE Google-princip kršenje.

## Zero Thinking Flow — 6 glavnih tokova

Ocena je izvedena iz stvarnog koda ove sesije (CONTRACT 01-04 rad,
`VINDEX_OPERATING_SYSTEM_CONTRACTS.md`, `VINDEX_INTEGRATION_MASTER_PLAN.md`)
i ranijih audit-a u ovoj sesiji, ne nova nagađanja.

1. **Kreiranje predmeta** — `+ Novi predmet` → CRM wizard forma. Nizak
   mentalni teret (standardna forma), ALI: `PredmetKreiran` event se
   nikad ne emituje (G-001/D3, poznato od ranije), pa se ništa
   automatski ne pokreće posle kreiranja — korisnik mora RUČNO da zna
   sledeći korak (upload). Zero Thinking Flow je prekinut ovde ne zbog
   UI-ja nego zbog nedostajuće automatizacije iza njega.
2. **Upload dokumenta** — klik → fajl birač → upload. Nizak teret,
   radi. Posle uploada postoji signal "AI analiza u toku"
   (`_genomeBackgroundWatch`, implementirano u prethodnoj UX rundi) —
   ovo JE Zero Thinking Flow primer koji radi.
3. **AI analiza** — zahteva IZBOR moda (od 7) pre nego što korisnik
   može da postavi pitanje — jedina mentalna odluka u ovom nizu koja
   nije nužna (videti "AI funkcije" gore).
4. **Genome generisanje** — potpuno automatsko posle uploada (pozadinski
   posao, `_run_genome_background`), korisnik ne donosi nijednu odluku.
   **Najbolji primer Zero Thinking Flow u aplikaciji.**
5. **Sledeća akcija** — ovde se lome POSTOJEĆI paralelni izvori: Cockpit
   `sledeca_akcija`, Matter Intel `sledeca_radnja`, Case Ready Score
   `copilot_preporuka`, `workflow.py::sledeci_korak` — **4 nezavisna
   "šta da radim sledeće" sistema** (potvrđeno u ranijem audit-u ove
   sesije, `VINDEX_INTEGRATION_MASTER_PLAN.md`, nijedan ne zna za
   ostale). Korisnik može dobiti 4 različita predloga sledećeg koraka
   za isti predmet. Ovo je NAJTEŽI Zero Thinking Flow prekid u celoj
   platformi — sistem doslovno ne zna svoju sopstvenu preporuku.
6. **Završetak predmeta** — prevlačenje na Kanban "Završen" kolonu.
   Nizak mentalni teret (jedan drag-and-drop), ALI: ne triguje ništa
   automatski (nema fakturisanja, statistike, arhiviranja triggera —
   poznato iz ranijeg audit-a).

---

# Top 10 UX Problems

### 1. Dashboard — 4 nezavisna AI-narativna izvora za isto "stanje danas"
- **Problem:** Health Index, CC Intel Briefing, Jutarnji brifing, CIO
  (`vindex.js:1158,1262,1625,16543`) svaki nezavisno sumira
  rizik/rokove/ročišta.
- **Zašto nastaje:** Svaki je dodat u različitoj fazi razvoja
  (health-index, briefing, command-center, CIO su odvojeni projekti u
  istoriji koda) bez konsolidacije posle.
- **Uticaj na korisnika:** Ne zna koji "glas" da veruje; isti broj vidi
  do 5 puta na jednom ekranu.
- **Ozbiljnost: P0** (utisak, ne funkcija — ali prvi utisak SVAKI dan).
- **Princip:** Jedan poslovni koncept ("šta zahteva pažnju danas") =
  jedan izvor istine, jedan vizuelni blok.

### 2. "Sledeća akcija" ima 4 nezavisna, nekomunicirajuća sistema
- **Problem:** Cockpit/Matter Intel/Case Ready Score/`workflow.py` svaki
  računa svoj predlog sledećeg koraka.
- **Zašto nastaje:** Isti obrazac kao Problem 1 — organski rast,
  nikad konsolidovano (dokumentovano već u
  `VINDEX_INTEGRATION_MASTER_PLAN.md` kao nalaz #7 iz ranijeg audit-a).
- **Uticaj:** Direktno krši "AI treba da uklanja odluke, ne da ih
  dodaje" princip — korisnik može dobiti 4 različita predloga.
- **Ozbiljnost: P0** — ovo je SUŠTINA proizvoda ("Vindex vodi mene, ne
  ja njega"), ne kozmetika.
- **Princip:** Isti kao G-027/AR-01 — jedan deterministički izvor,
  ostali su prezentacija ili input, ne paralelan kalkulator.

### 3. Pregled predmeta — 3 skor-widgeta (delom rešeno kodom)
- **Problem:** Matter Intelligence/Cockpit/Case Ready Score prikazani
  kao 3 odvojena vizuelna bloka iako G-027 (ova sesija) obezbeđuje da
  se brojevi slažu.
- **Zašto nastaje:** Podatak je popravljen, prikaz nije stigao za njim.
- **Uticaj:** I dalje "izgleda" kao 3 sistema iako je sad 1 izvor +
  1 legitimno odvojen koncept (kompletnost).
- **Ozbiljnost: P1** — podatak je već tačan, ovo je čist prikaz dug.
- **Princip:** Vizuelna hijerarhija mora pratiti podatkovnu — kad se
  izvor spoji, prikaz mora da prati.

### 4. Sidebar — 13 stavki naspram 5 na mobilnom
- **Problem:** Desktop navigacija nikad usklađena sa mobilnim IA
  principom koji već postoji u istom kodu.
- **Zašto nastaje:** Mobilna nav je rađena kao posebna faza, desktop
  nikad revidiran u nazad (poznat nalaz, 2× ranije odložen).
- **Uticaj:** Kognitivni teret pri svakoj navigaciji, ne samo prvi put.
- **Ozbiljnost: P1.**
- **Princip:** 7±2 pravilo za primarno vidljivu navigaciju.

### 5. AI funkcije — 7 modova pre prvog pitanja
- **Problem:** Vindex Intelligence hub traži izbor moda PRE unosa
  pitanja (`aiws-modes`, 7 pilula, `index.html:2715-2722`).
- **Zašto nastaje:** Mod-svič arhitektura je nastala konsolidacijom
  nekadašnjih zasebnih tabova (ispravna odluka u svoje vreme) — ali broj
  modova je rastao bez preispitivanja da li svih 7 treba da bude vidljivo
  odjednom.
- **Uticaj:** Krši "AI uklanja odluke" princip u samom ulazu u AI.
- **Ozbiljnost: P1** (P2 za samo preimenovanje "Litigation Intelligence",
  P1 za strukturno grupisanje modova).
- **Princip:** Sistem treba da razume nameru gde god je to izvodljivo
  pre nego što traži od korisnika da bira kategoriju.

### 6. "Dokumenti" top-level tab bez sopstvenog sadržaja
- **Problem:** Redirect-only stranica zauzima mesto u 13-stavki
  sidebar-u.
- **Zašto nastaje:** Verovatno ostatak starije IA pre nego što su
  dokumenti postali isključivo predmet-skopirani.
- **Uticaj:** Mali direktan, ali doprinosi sidebar teretu (Problem 4).
- **Ozbiljnost: P2.**
- **Princip:** Svaka nav stavka mora imati jedinstvenu funkciju koju
  nijedna druga stavka ne pokriva.

### 7. Modal komponente — 2 paralelne implementacije istog mehanizma
- **Problem:** `class="modal-overlay"`/`vx-modal-overlay` naspram
  ručno pisanih inline `style="position:fixed..."` (npr. `voice-modal`,
  `ios-install-modal`, `mi-modal`).
- **Zašto nastaje:** Organski rast, novi modal dodat bez provere
  postojećeg obrasca.
- **Uticaj:** Nizak vidljiv, srednji za održavanje (izmena zajedničkog
  ponašanja mora se raditi na više mesta).
- **Ozbiljnost: P2.**
- **Princip:** Jedan UI mehanizam = jedna implementacija, isti D20.1/
  AR-01 obrazac primenjen na komponente, ne samo podatke.

### 8. Podešavanja — 22 sekcije bez progressive disclosure
- **Problem:** Nema collapse/grupisanje za ređe korišćene sekcije
  (Integracije, SEF, SMS) iako obrazac postoji drugde u istoj
  aplikaciji (Finansije "Detaljni izveštaji").
- **Zašto nastaje:** Svaka sekcija dodata nezavisno tokom vremena.
- **Uticaj:** Nizak — Podešavanja je "namerno poseti" ekran, ne pasivno
  skeniran (Google Principle Test ovo potvrđuje kao prihvatljivo).
- **Ozbiljnost: P3.**
- **Princip:** Primeniti postojeći "Detaljni izveštaji" collapse
  obrazac dosledno, ne kao novu ideju.

### 9. Rokovi — 3 export dugmeta umesto 1 menija
- **Problem:** .ics/Google/Outlook kao 3 odvojena dugmeta u header-u.
- **Zašto nastaje:** Svaka integracija dodata kao zaseban CTA.
- **Uticaj:** Minimalan, čist vizuelni šum.
- **Ozbiljnost: P3.**
- **Princip:** Grupiši varijante iste akcije (izvoz) pod jedan meni.

### 10. Lažna pretraga i dekorativna animacija na Dashboard-u
- **Problem:** Globalna pretraga sa `title="dolazi uskoro"` (funkcija ne
  postoji), 3D constellation canvas bez informativne funkcije.
- **Zašto nastaje:** Pretraga — vizuelni placeholder za buduću funkciju,
  ostavljen vidljiv. Animacija — dekorativni element iz ranije faze
  vizuelnog identiteta.
- **Uticaj:** Pretraga koja ne radi je gore nego da ne postoji (aktivno
  razočarenje pri prvom pokušaju). Animacija ne šteti, ali ne pomaže —
  zauzima prostor i GPU bez svrhe.
- **Ozbiljnost: P2** (pretraga — aktivno frustrirajuća), **P3**
  (animacija — neutralna).
- **Princip:** Ne prikazuj UI za funkciju koja ne postoji; ukloni
  dekoraciju bez funkcionalne svrhe (masterprompt eksplicitna zabrana).

---

# New Information Architecture

**Ne uklanjam funkcije — reorganizujem vidljivost.** Predlog je
STRUKTURA, ne konačan vizuelni dizajn (to je Sprint posao).

## Sidebar — predložena hijerarhija (od 13 na 4+grupe)

**Primarno vidljivo (L1, uvek u sidebar-u):**
1. Danas (bivši "Pregled dana")
2. Predmeti
3. Klijenti
4. Rokovi

**Grupa "Alati" (L2, jedan klik za otvaranje pod-liste):**
- Vindex Intelligence
- Sudska praksa
- Šabloni dokumenata
- Zadatci

**Grupa "Kancelarija" (L2):**
- Finansije
- Kancelarija (tim)
- Portfolio kancelarije

**Uvek na dnu (L1, ali vizuelno odvojeno — nije "sadržaj"):**
- Podešavanja

**Uklonjeno kao zasebna stavka:** "Dokumenti" (Problem 6) — funkcija
ostaje, dostupna kroz Predmeti, kao i danas kad se otvori taj tab.

Ovo tačno prati postojeći mobilni obrazac (Početna/Predmeti/Rokovi/
Klijenti/Više) — ne izmišlja se nova IA, primenjuje se već dokazana.

## Dashboard — predložena hijerarhija informacija

**L1 (odmah vidljivo, JEDAN blok umesto 4):**
- Pozdrav + datum
- 4 KPI broja (aktivni predmeti / hitni rokovi / ročišta danas /
  nenaplaćeno) — JEDAN izvor za sve četiri, ne ponovljeno u 3 druga
  widgeta
- JEDAN "šta zahteva pažnju danas" narativ blok — kombinuje ono što
  danas rade Health Index + CC Briefing + Jutarnji brifing + CIO, sa
  JEDNIM glasom, ne četiri

**L2 (jedan klik):**
- Puna lista prioritetnih predmeta
- Puna lista rokova/ročišta narednih 7 dana
- Billing detalji
- Novi dokumenti (24h)

**L3 (sakriveno dok se ne traži):**
- Pravni alati kartice (već dostupno kroz sidebar "Alati" grupu —
  razmotriti potpuno uklanjanje duplikata, ne samo sakrivanje)
- Detaljna AI analiza (već L2/L3 danas, ostaje)
- Portfolio/CIO breakdown

## Pregled predmeta — predložena hijerarhija

**L1:** naziv predmeta, status, JEDAN spojen skor blok (rizik +
spremnost jasno razdvojeni kao DVA različita koncepta, ne tri
konkurentska), sledeća akcija (JEDAN izvor — videti Problem 2).

**L2:** Beleške, ZPP Rokovi (premešteno u Rokovi subtab gde
konceptualno pripada).

**L3:** Zatvori predmet, Ugovor o zastupanju, Klijentski portal — iza
"Više alata" ili u odgovarajuće postojeće subtab-ove.

---

# Screen-by-Screen Recommendations

## Dashboard
**Trenutno stanje:** 4 nezavisna AI narativa + KPI red + dvokolonski
raspored + Pravni alati, sve L1, `_dashRender()` (`vindex.js:1449`).
**Problem:** Vidi Top 10 #1, #10.
**Nova struktura:** Jedan "danas" narativ blok (spaja 4 izvora u
pozadini, jedan glas napolju) + KPI red + L2 liste na klik. Ukloniti
lažnu pretragu dok ne postoji prava. Ukloniti/premestiti constellation
animaciju i duplirane "Pravni alati" kartice.

## Pregled predmeta
**Trenutno stanje:** 3 skor-widgeta (podatak sad usklađen, G-027) + 4
admin sekcije u glavnom scroll-u, `pred-pane-pregled`
(`index.html:766-1054`).
**Problem:** Vidi Top 10 #3.
**Nova struktura:** Vidi "New Information Architecture" iznad — jedan
spojen skor prikaz, admin sekcije iza "Više alata".

## Case Genome
**Trenutno stanje:** Sažetak-na-vrhu + collapsible detalji + jedan
trust-signal red, `_caseDnaRender()` (`vindex.js:16685-17048`).
**Problem:** Nema — ovo je REFERENTNI obrazac.
**Nova struktura:** Nepromenjeno. Kopirati OBRAZAC (ne kod) na Dashboard
i Pregled predmeta.

## AI funkcije (Vindex Intelligence hub)
**Trenutno stanje:** 7 mod-pilula pre unosa pitanja, `aiws-modes`
(`index.html:2715-2722`).
**Problem:** Vidi Top 10 #5.
**Nova struktura (Sprint 2/3, veći zahvat):** Grupisati manje korišćene
modove (Pravne oblasti, Litigation Intelligence) iza "Više" ili
preimenovati u jezik bliži advokatovom mentalnom modelu. Arhitektura
(mod-svič shell) ostaje — ispravna odluka, ne dirati.

## Dokumenti
**Trenutno stanje:** Redirect-only stranica, `tab-dok`
(`index.html:3252-3281`).
**Problem:** Vidi Top 10 #6.
**Nova struktura:** Ukloniti kao top-level nav stavku (Sprint 1,
najniži rizik u celom dokumentu — čisto uklanjanje mrtve navigacije).

## Rokovi
**Trenutno stanje:** Mesec/Lista toggle + 3 export dugmeta + kalendar,
`tab-kal` (`index.html:2647-2682`). Plus G-026 (credit panel
vidljivost bug, Open, dokumentovano u Gap Registru).
**Problem:** Vidi Top 10 #9. G-026 je zaseban, već praćen nalaz.
**Nova struktura:** Konsolidovati 3 export dugmeta u 1 "Izvezi ▾" meni.

## Klijenti
**Trenutno stanje:** Lista→Profil, 6 profil podtabova, standardan CRM
obrazac (`index.html:1860-1914`).
**Problem:** Nema ozbiljnog nalaza iz ove i prethodne provere.
**Nova struktura:** Nepromenjeno.

## Podešavanja
**Trenutno stanje:** 22 sekcije (17 korisniku vidljivih), sve
uvek-prikazane, jedan dugi scroll (`index.html:3284+`).
**Problem:** Vidi Top 10 #8.
**Nova struktura (Sprint 3, nizak prioritet):** Primeniti postojeći
Finansije "Detaljni izveštaji" collapse obrazac na ređe korišćene
sekcije (Integracije, SEF, SMS podešavanja).

---

# Vindex UX Rules

Deset trajnih pravila — svaki budući razvoj (moj ili bilo kog budućeg
developera) treba da ih proveri pre dodavanja UI elementa.

1. **Jedan poslovni koncept = jedan izvor istine.** Pre nego što se
   doda NOVO polje/widget koje prikazuje rizik/status/rok/prioritet/
   spremnost, proveriti da li već postoji izvor za taj koncept
   (D20.1/AR-01, već formalizovano ovom sesijom, sada primenjeno i na
   UI komponente, ne samo backend polja).
2. **LLM nikad ne određuje poslovno stanje** (AR-01) — objašnjava,
   sumira, predlaže; deterministički sloj određuje broj/status/nivo.
3. **Sažetak pre detalja, uvek.** Svaki ekran sa više od 3 sekcije
   podataka mora imati "šta je najvažnije" red na vrhu PRE punog
   prikaza — kao Case Genome "PREGLED" (`_caseDnaRender`), ne kao
   Dashboard (sve odjednom).
4. **Trust signali ostaju L1, nikad iza klika.** AI Provera obrazac
   (Genome) — upozorenje o pouzdanosti se ne sakriva, čak i kad se sve
   ostalo sažima. Poverenje se gradi vidljivošću, ne kompaktnošću.
5. **Nova nav stavka mora imati funkciju koju nijedna druga ne
   pokriva.** Test iz Top 10 #6 — ako se stavka svodi na redirect ka
   drugoj stavci, ne zaslužuje sopstveno mesto.
6. **Progressive disclosure je podrazumevano, ne izuzetak.** Ako
   sekcija nije potrebna "upravo sada" (masterprompt pitanje 3 iz
   prethodnog audit-a), ide iza klika/collapse-a — obrazac već postoji
   (Finansije "Detaljni izveštaji", Zatvori predmet forma), primeniti
   dosledno.
7. **Jedan UI mehanizam, jedna implementacija.** Modal, dugme, kartica
   — ako već postoji deljena klasa/komponenta za taj obrazac, novi
   slučaj je koristi, ne piše svoju verziju inline stilom.
8. **Ne prikazuj UI za funkciju koja ne postoji.** Placeholder sa
   "dolazi uskoro" koji IZGLEDA funkcionalno (input polje, dugme) je
   gore nego da elementa nema — korisnik pokuša, ne uspe, izgubi
   poverenje.
9. **Svaka AI preporuka "sledeći korak" mora imati TAČNO JEDAN izvor
   po predmetu.** Ako više modula računa svoju verziju (Problem 2),
   to je P0 arhitektonski nalaz, ne UI stilska razlika.
10. **UI izmena mora biti povezana sa merljivim korisničkim ishodom**
    (CONTRACT korak, cognitive load broj, ili L1/L2/L3 klasifikacija) —
    ne "izgleda lepše" bez merila. Isti princip koji je founder već
    postavio za CONTRACT-vezane izmene, sada formalizovan kao opšte
    pravilo za sve UI odluke, ne samo pre-beta period.

---

# Implementation Roadmap

**Napomena o redosledu (nepromenjeno founderovo pravilo iz ove
sesije):** ništa ispod ne počinje pre nego što se CONTRACT 01 ručni
prolaz završi. Sprint 1 ovde znači "prvi UI sprint POSLE CONTRACT 01",
ne trenutni prioritet.

## Sprint 1 — Beta critical UX (nizak rizik, visok uticaj)
- Ukloniti "Dokumenti" top-level nav stavku (Top 10 #6) — čisto
  uklanjanje, gotovo nula rizika.
- Ukloniti lažnu pretragu i constellation animaciju sa Dashboard-a
  (Top 10 #10) — čisto uklanjanje, nema zavisnosti.
- Premestiti admin sekcije (Zatvori/Ugovor/Portal/ZPP rokovi) iza
  "Više alata" na Pregled predmeta (prethodni audit, Sekcija 3) —
  HTML reorganizacija, funkcije se ne menjaju.
- Konsolidovati 3 export dugmeta na Rokovi u 1 meni (Top 10 #9).

## Sprint 2 — High impact improvements (srednji rizik)
- Vizuelno spojiti 3 skor-widgeta na Pregled predmeta u jedan prikaz
  (podatak već usklađen kroz G-027 — ovo je čist prikaz rad).
- Sidebar reorganizacija u L1/L2 grupe (Top 10 #4) — dotiče svaku
  stranicu, zahteva regresiono testiranje.
- G-026 popravka (credit panel vlasništvo nad vidljivošću) — već
  dijagnostikovano, čeka implementaciju.

## Sprint 3 — Advanced polish (viši rizik ili viša neizvesnost)
- Dashboard konsolidacija 4 AI narativa u jedan glas (Top 10 #1) —
  **najveći pojedinačni zahvat u celom dokumentu**, zahteva prvo
  backend odluku (koji izvor postaje "master"), isto kao G-027 ali
  većeg obima. Preporuka: sopstvena empirijska validacija pre
  implementacije, isti obrazac kao G-027.
- "Sledeća akcija" konsolidacija 4 sistema u jedan (Top 10 #2) —
  **arhitektonski najozbiljniji nalaz cele strategije**, zahteva
  odluku KOJI sistem postaje izvor istine (Cockpit? Matter Intel?
  Case Ready Score? `workflow.py`?) — ovo nije UI odluka, ovo je
  proizvod-odluka i mora ići founderu eksplicitno pre bilo kakvog koda.
- AI hub mod-grupisanje/preimenovanje (Top 10 #5).
- Modal mehanizam unifikacija (Top 10 #7) — pre toga, provera da li
  su postojeće razlike namerne (npr. PWA install modal-i).
- Podešavanja progressive disclosure (Top 10 #8) — najniži prioritet,
  Google Principle Test već potvrđuje da trenutno stanje nije kršenje.

---

# Finalni kriterijum

**Pitanje:** Da li bi advokat koji prvi put vidi Vindex mogao za 10
minuta samostalno da razume vrednost proizvoda?

**Odgovor: DELIMIČNO DA, uz jednu ozbiljnu prepreku.**

Ono što RADI za "10 minuta" test: Genome generisanje je potpuno
automatsko i vidljivo (upload → "AI analiza u toku" signal → Case
Genome se pojavljuje bez ijedne dodatne odluke korisnika) — ovo je
tačno "WOW trenutak" mehanizam koji masterprompt traži, i već postoji,
izmeren u prethodnoj UX rundi kao "2-4 minuta do prvog Genome prikaza"
(`project_ux_audit_2026-07-19` memorija, Time-to-WOW procena).

Ono što SPREČAVA čisto DA: Dashboard (prvi ekran, pre nego što korisnik
uopšte otvori predmet) trenutno komunicira suprotno od "jednostavan,
pametan sistem" utiska — četiri nezavisna AI glasa koja ponavljaju iste
brojeve ostavljaju utisak kolekcije alata, ne jednog operativnog
sistema, PRE nego što korisnik i stigne do dela proizvoda (Genome) koji
tu vrednost stvarno dokazuje. Drugi faktor: "sledeća akcija" ima 4
nekomunicirajuća izvora — ako korisnik OTVORI drugi predmet i vidi
drugačiji predlog sledećeg koraka na drugom mestu na ekranu, "sistem
vodi mene" obećanje (osnovni princip cele platforme, po founderovoj
sopstvenoj filozofiji) je direktno narušeno u prvih 10 minuta.

**Šta tačno sprečava čisto DA:** ne nedostatak funkcije — VIŠAK
paralelnih glasova za iste dve stvari (šta se dešava danas, šta da
radim sledeće) na dva najvažnija ekrana (Dashboard, Pregled predmeta).
Popraviti Top 10 #1 i #2 (Sprint 3, ali najviše vredna dva zahvata u
ovom dokumentu) pomera odgovor sa "delimično da" na čisto "da" — sve
ostalo u ovom dokumentu je poboljšanje, ta dva su preduslov za pun
odgovor.
