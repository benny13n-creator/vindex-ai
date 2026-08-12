# SEMANTICS MAP — Da li korisnik razume šta koja kontrola znači

**Tip:** UX Semantics / Information Architecture audit
**Datum:** 2026-08-12
**Predmet analize:** `index.html` (4.832 linije), `static/vindex.js` (23.681 linija), `static/vindex.css`, `routers/support.py`, `routers/drafting.py`, `routers/voice.py`
**Metod:** Za svaku kontrolu pročitana je labela, zatim rukovalac, zatim zaledina (endpoint). Tvrdnja bez pročitanog koda označena je sa `UNVERIFIED`.

> **Ovo je audit. Nijedan fajl nije izmenjen. Svi predlozi su predlozi — nijedan nije izvršen.**

---

## 0. Sažetak nalaza

### Mrtve i lažne kontrole

| # | Nalaz | Dokaz | Težina |
|---|---|---|---|
| S-01 | **„Pomoć & podrška"** u sidebaru nema nikakav rukovalac — izgleda klikabilno, ne radi ništa | `index.html:533`; nema slušaoca nigde u `static/` | Kritično |
| S-02 | **„Generiši nacrt tužbe"** ne radi ništa — cilj `#tab-n` ne postoji | `index.html:4036` → `vindex.js:7962`; `grep -c 'id="tab-n"'` = **0** | Kritično |
| S-03 | **„Pošalji u Strategiju"** upiše tekst u polje koje korisnik ne vidi i ne prebaci ga tamo | `index.html:4037` → `vindex.js:7970`; navigacija cilja `.t-tab[onclick*="'t'"]` koji ne postoji | Kritično |
| S-04 | **„Pokreni analizu"** otvara prazno polje za pitanje o zakonu — nikakva analiza | `index.html:206` → `openAITool('q')` → `vindex.js:2244-2252` | Kritično |
| S-05 | Dugme za feedback (💬) je na desktopu **prekriveno** glasovnim dugmetom sa višim z-indeksom | `index.html:214` vs `vindex.css:3630-3641` | Kritično |
| S-06 | **„Digital Twin — simulacija razvoja"** obećava 3 scenarija; rukovalac ima 3 linije i samo otkriva panel | `index.html:1256` → `vindex.js:19241-19244` | Visoko |
| S-07 | **„Pokreni kompletnu analizu"** 3 sekunde prikazuje „Analiziram…" iako ništa ne analizira | `index.html:1596` (inline `setTimeout`) | Visoko |

### Rečnik i informaciona arhitektura

| # | Nalaz | Težina |
|---|---|---|
| S-08 | 15 kontrola nosi naziv rezultata („Analiza rizika", „Procena ishoda"), a samo otvara praznu formu | Visoko |
| S-09 | Reč „feedback" pokriva **tri različite zaledine** (podrška / netačan odgovor / interesovanje za cenu) | Visoko |
| S-10 | Tri glagola za jednu radnju: **otpremi / upload / dodaj** — ponekad u istom widgetu | Visoko |
| S-11 | „Prijavite se" znači **i prijavu na nalog i upis na listu čekanja** | Visoko |
| S-12 | „Dokumenti" je **dve različite stvari** (spisi predmeta vs. pravni akti Vindeksa) | Visoko |
| S-13 | Ograničenje 5 poruka/sat **deli se** između podrške i feedbacka — ocenjivanje blokira prijavu kvara | Visoko |
| S-14 | „Odgovorićemo u roku od 24h" prikazuje se i kada slanje e-pošte tiho zakaže | Visoko |
| S-15 | Pet kontrola tiho odustane kad nema otvorenog predmeta — **bez ijedne poruke** | Visoko |
| S-16 | „Zadatci" i „Zadaci" u **istom elementu** (tooltip vs. labela) | Srednje |
| S-17 | Navigacija kaže „Rokovi", stranica kaže „Kalendar" | Srednje |
| S-18 | Tekst pomoći upućuje na „Intake čarobnjak" — taj naziv ne postoji u interfejsu | Srednje |
| S-19 | „Šabloni dokumenata" izgleda kao tab, ali otvara modal | Srednje |
| S-20 | „Wallet Risk Assessment" je istovremeno naziv grupe i naziv modula u toj grupi | Srednje |
| S-21 | Četiri kontakt adrese na dva domena (`.ai` i `.rs`) | Srednje |

---

## 1. Mapa funkcija — pomoć / podrška / povratna informacija / incident / glas

Vlasnik je tačno postavio pitanje: to nisu iste stvari. Evo šta aplikacija stvarno ima.

### 1.1 Namere korisnika i gde ih aplikacija prima

| Namera korisnika | Ime kontrole | Gde se nalazi | Zaledina | Stanje |
|---|---|---|---|---|
| „Kako se ovo koristi?" | **Pomoć i podrška** → 6 najčešćih pitanja | Podešavanja, `:3731` | statički tekst, `pomocFaqToggle()` | Radi |
| „Kako se ovo koristi?" | **Pomoć & podrška** (sidebar) | Sidebar dno, `:533` | **nema rukovaoca** | **Mrtvo** |
| „Imam problem pri korišćenju" | **Pošalji poruku** → *Tehnički problem* | Podešavanja, `:3813` | `POST /api/support/poruka` | Radi |
| „Imam predlog / primedbu" | **Pošalji poruku** → *Predlog / ideja* | Podešavanja, `:3801` | isti endpoint | Radi |
| „Imam predlog / primedbu" | **Pošaljite feedback** (💬) | Dole desno, `:214` | isti endpoint, kategorija zakucana na `feedback` | Radi, ali **prekriveno** |
| „AI je dao netačan odgovor" | **Prijavi netačan odgovor** | Uz svaki AI odgovor, `vindex.js:7832` | `reported_errors` + `POST /api/feedback` | Radi |
| „AI je dao netačan odgovor" | **Pošalji poruku** → *Tačnost odgovora* | Podešavanja, `:3804` | e-pošta, **bez spornog odgovora** | Duplikat, slabiji |
| „Sistem je u kvaru" | **Status servisa → Otvori** | Podešavanja, `:3510` | `/status`, samo za čitanje | Radi |
| „Želim da prijavim kvar" | — | **ne postoji zaseban kanal** | pada u *Tehnički problem* | Nedostaje |
| „Hoću da komandujem glasom" | **Govori** | Gornja traka, `:569` | `voice_start()` → Web Speech API | Radi |
| „Hoću da komandujem glasom" | 🎙 (bez teksta) | Dole desno, `:4416` | `vxLiveOpen()` → WebSocket | Radi — **drugi sistem** |
| „Hoću da diktiram tekst" | 🎤 uz polja | npr. `:2865` | `micToggle(id)` | Radi |

### 1.2 Zaključak mape

**Pet namera, dva odredišta.** Sve što korisnik napiše — problem, predlog, ocena, primedba — završi na **istom mestu**: e-pošta osnivačima + tabela `support_tickets`. Dokaz, `routers/support.py:197-217`: jedan endpoint, jedan `_send_support_email`, jedan `_save_ticket`. Polje `kategorija` menja **isključivo naslov e-poruke** (`:95`) — ne primaoca, ne prioritet, ne tok obrade.

Posledica: nema razlike u ishodu između „Prijavi tehnički problem" i „Oceni aplikaciju sa 5 zvezdica". Advokat sa hitnom smetnjom i advokat koji šalje pohvalu koriste isti kanal, sa istim obećanim rokom.

**Glas je suprotan slučaj — jedna reč, tri stvari.** „Glasovna komanda" imenuje dva odvojena tehnička sistema:

| | `voice_start()` | `vxLiveOpen()` |
|---|---|---|
| Lokacija | `vindex.js:16664` | `vindex.js:17102` |
| Ulaz | dugme **„Govori"** (`:569`) | 🎙 plutajuće dugme (`:4416`) |
| Tehnologija | prepoznavanje u pregledaču | WebSocket ka serveru |
| Režim | jedna komanda | razgovor |
| Uslov | Chrome/Edge + HTTPS | Web Audio API |

Treći, `micToggle()`, je **diktat** — ne komanda — ali nosi zbunjujuće sličan naziv „Glasovni unos".

---

## 2. Kontrole gde labela NE POKLAPA sa ishodom

Legenda: `POKLAPA` · `DELIMIČNO` · `NE POKLAPA`

### 2.1 Mrtve kontrole

| Kontrola | Šta obećava | Šta radi | Poklapanje |
|---|---|---|---|
| **Pomoć & podrška**<br>`:533` | Otvoriće pomoć | **Ništa.** Nema `onclick`, nema slušaoca. CSS `vindex.css:4969-4980` daje `cursor:pointer` + hover, pa *izgleda* klikabilno | **NE POKLAPA** |
| **Generiši nacrt tužbe**<br>`:4036` | Napraviće nacrt tužbe | **Ništa.** `analizaGenerisiNacrt()` (`vindex.js:7962`) traži `.t-tab[onclick*="'n'"]` — ne postoji; zatim `#tab-n textarea` — **`#tab-n` ne postoji** (provereno: 0 pojava). Bez navigacije, bez poruke o grešci | **NE POKLAPA** |
| **Pošalji u Strategiju**<br>`:4037` | Prebaciće analizu u Strategiju | Navigacija ne uspe (isti razlog), ali tekst **jeste** upisan u `#strat-tekst` (postoji). Korisnik ostaje na istom ekranu i ne vidi da se išta desilo | **NE POKLAPA** |

Napomena o susedu: **„Sačuvaj u predmet"** (`:4035`) radi — `_analizaSwitchTab('p')` pogađa postojeći tab. Dakle od pet dugmadi u istom redu, dva su mrtva, jedno radi nevidljivo, dva rade.

### 2.2 Labela obećava rezultat, rukovalac otvara formu

| Kontrola | Šta obećava | Šta radi | Poklapanje |
|---|---|---|---|
| **Pokreni analizu**<br>`:206` | Pokrenuće analizu | `openAITool('q')` → mod „zakon" sa **praznim poljem za pitanje**. Iza ovog dugmeta ne postoji nikakva analiza | **NE POKLAPA** |
| **Pokreni analizu** / „Analiziraj"<br>`vindex.js:1631-1632` | Pokrenuće analizu | `setTab(…,'alati')`; `tab-btn-alati` ne postoji → alias (`vindex.js:1996-2000`) skoči na `aiws` u **poslednjem korišćenom modu** | **NE POKLAPA** |
| **Digital Twin — simulacija razvoja**<br>`:1256` | Opis obećava „AI simulira 3 scenarija" | `twinPanelShow()` = **tri linije koda**, samo `panel.style.display='block'`. Ne troši ni kredit ni sekundu | **NE POKLAPA** |
| **Analiziraj** / **Pokreni kompletnu analizu**<br>`:782`, `:1596` | Pokrenuće kompletnu analizu | `pred_launchKompletnaAnaliza()` (`vindex.js:10608-10621`) napusti predmet, skoči u Strategiju; ako autofill da < 100 znakova, **samo toast i skrol**. Dugme `:1596` pritom 3 s prikazuje „Analiziram…" | **NE POKLAPA** |
| **Analiza rizika** · **Procena ishoda** · **Predikcija ishoda** · **Analiza svedoka** · **Simulacija parničnog postupka** · **Analiza crvenog tima** · **Revizija dokumenta** · **Sudija v2 — Debata**<br>`:1164-1247`, `:3092-3098` | Svaki naziv je imenica rezultata | `pred_openStrat` (`vindex.js:10577`) i `stratIzaberiModul` (`vindex.js:3073`) **samo menjaju tekst opisa i labelu polja**. Potrebna su još 2 klika i unos od 50-100 znakova | **NE POKLAPA** (15 kontrola) |
| **Analiza dokumenta**<br>`:1074`, `:1739`, `:3396` | Analiziraće dokument | `openAITool('a')` → zona za otpremanje. Analiza kreće tek posle otpremanja i **drugog** dugmeta („Forenzička analiza dokumenta", `:2969`) | **DELIMIČNO** |
| **AI analiza projekta** · **AML/KYC revizija** · **Exchange Reporting Simulator**<br>`:3260-3263` | Rezultat | `dimOpenModul` (`vindex.js:2219`) → prazan textarea | **NE POKLAPA** |

**Obrazac:** aplikacija dosledno imenuje kontrole po **odredištu koje korisnik želi**, a ne po **radnji koja se dešava**. Advokat koji klikne „Analiza rizika" opravdano očekuje analizu rizika; dobija prazno polje i zahtev da sam napiše 100 znakova opisa.

Za poređenje, Web3 sloj je **najpošteniji deo aplikacije**: labele su glagoli („Proveri adrese", „Proveri novčanik", „Generiši dossier") i rukovaoci zaista izvršavaju (`vindex.js:5376`, `5430`, `5530`). Nesklad je samo na nivou iznad — kartice koje otvaraju forme.

### 2.3 Ostale neusklađenosti

| Kontrola | Šta obećava | Šta radi | Poklapanje |
|---|---|---|---|
| **Govori**<br>`:569` | Govoriću aplikaciji | Jednokratna komanda; van Chrome/Edge samo poruka | **DELIMIČNO** |
| 🎙 **plutajuće dugme**<br>`:4416` | *(bez tekstualne labele)* | Drugi glasovni sistem — korisnik iz ikone to ne može zaključiti | **NE POKLAPA** |
| **+ Novi predmet** | Napraviću predmet | `intakeOtvori()` → **petostepeni čarobnjak**; modal se zove „Novi predmet — Intake Wizard" (`:2139`) | **DELIMIČNO** |
| **Svetla tema**<br>`:526` | Prebaciću na svetlu temu | Radi ispravno (labela pokazuje ciljno stanje), ali `toggleLightTheme()` (`vindex.js:19907`) upisuje **tekst** u element predviđen za ikonu → posle klika piše „Tamno Tamna tema" | **DELIMIČNO** |
| **Pozovite kolegu**<br>`:529` | Pozvaću kolegu | `wl_open()` — isti obrazac koji se javno zove „Prijavite se za rani pristup" | **DELIMIČNO** |

### 2.4 Navigacija — naziv u meniju vs. naslov stranice

| Stavka menija | Naslov stranice | Poklapanje |
|---|---|---|
| Predmeti (`:449`) | Predmeti (`:624`) | POKLAPA |
| Klijenti (`:453`) | Klijenti (`:1941`) | POKLAPA |
| **Rokovi** (`:457`) | **Kalendar** (`:2775`) | **NE POKLAPA** |
| Vindex Intelligence (`:464`) | *(razni režimi)* | **DELIMIČNO** — naziv je robna marka, ne kaže šta radi |
| Dokumenti (`:472`) | Dokumenti (`:3380`) | POKLAPA, ali sudar sa Podešavanjima (S-12) |
| **Šabloni dokumenata** (`:478`) | *(modal)* | **NE POKLAPA** — `class="t-tab"` kao pravi tabovi, ali `docTplOpen()` (`vindex.js:15463`) samo otvara overlay; aktivni tab ostaje prethodni |
| **Zadatci** (`:486`) | **Zadaci tima** (`:2594`) | **DELIMIČNO** |
| Finansije (`:490`) | Finansije (`:2618`) | POKLAPA |
| Kancelarija (`:494`) | Kancelarija (`:2672`) | POKLAPA |
| Portfolio kancelarije (`:498`) | — | `UNVERIFIED` — `display:none` u polaznom stanju |

---

## 3. Kontrole koje traže prethodno stanje bez objašnjenja

### 3.1 Tihi odustanak — korisnik ne dobija nikakvu poruku

Najgora kategorija: klik ne proizvede ni rezultat ni objašnjenje.

| Kontrola | Uslov | Dokaz |
|---|---|---|
| **Pokreni simulaciju (3 kredita)**<br>`:1296` | otvoren predmet | `vindex.js:19249` — `if (!wrap \|\| !activePredmetId \|\| !currentSession) return;` bez toasta |
| **Analiziraj** (twin „šta ako")<br>`:1305` | otvoren predmet | `vindex.js:19290` — isti obrazac |
| **AI Briefing — sledeći korak**<br>`:1606` | otvoren predmet | `vindex.js:17530` |
| **Winning Strategy Brief**<br>`:1615` | otvoren predmet | `vindex.js:17591` |
| **Digital Twin** (kartica)<br>`:1256` | — | `vindex.js:19241` — nema **nikakve** provere; otvara panel i kad predmet nije aktivan |

### 3.2 Greška tek posle neuspelog mrežnog poziva

| Kontrola | Dokaz |
|---|---|
| **Generiši / osveži procenu predmeta**<br>`:1603` | `onclick="_voice_refresh_case_dna(activePredmetId)"`; funkcija (`vindex.js:17464`) **nema zaštitu od `null`** → šalje zahtev sa `null` u putanji → generički toast „Greška pri generisanju Procena predmeta" (`:17514`), bez objašnjenja da fali predmet. *(Napomena: i sama poruka je gramatički neispravna.)* |
| **Šabloni dokumenata**<br>`:478` | `docTplOpen()` čita `currentSession.access_token` (`vindex.js:15470`) **bez provere na null**, za razliku od ostalih rukovalaca |

### 3.3 Poruka postoji, ali tek posle klika

Ovde je ponašanje pristojno — labela i dalje ćuti, ali korisnik bar dobije objašnjenje: „Analiza uspeha kancelarije" (`vindex.js:19208`), „Potraži slične predmete" (`:18884`), „Prikaži trendove" (`:18921`), „Analiziraj konflikte" (`:11891`), „Generiši pripremu za ročište" (`:14460`), „AI analiza" zadataka (`:23418`).

### 3.4 Uslovi okruženja koji se saopštavaju tek posle klika

| Kontrola | Neizrečen uslov |
|---|---|
| **Govori** (`:569`) | HTTPS. Tooltip pominje Chrome/Edge, ne i HTTPS (`vindex.js:16670`) |
| 🎙 **Vindex Live** (`:4416`) | Web Audio API + dozvola za mikrofon (`vindex.js:17116`) |

---

## 4. Ista reč — dve različite stvari

| Reč | Značenje A | Značenje B | Dokaz |
|---|---|---|---|
| **Dokumenti** | Spisi predmeta koje advokat otprema | Pravni akti *Vindeksa* (Security Whitepaper, DPA, Status) | `:3380` vs `:3489` |
| **Prijava / Prijavite se** | Prijava na nalog | Upis na listu čekanja | `:87`, `:4169` vs `:4156`, `:4160` |
| **Feedback** | Utisak o aplikaciji (`/api/support/poruka`) | Prijava netačnog AI odgovora (`/api/feedback`) | `vindex.js:4292` vs `:8006` |
| **Feedback** *(treće)* | **Marketinška telemetrija** — interesovanje za cenovni plan poslato kroz kanal za prijavu grešaka | `vindex.js:8255`: `pitanje: 'PRICING_INTEREST: ' + plan` | |
| **Wallet Risk Assessment** | Naziv **grupe** (`ofac_screening` + `wallet_provenance`) | Naziv **jednog modula** u toj grupi | `vindex.js:2174` vs `:2187` |
| **Analiza** | Analiza dokumenta | Analiza rizika, „6 agenata" | `:1074` vs `:1587` |
| **Status** | Status predmeta | Status servisa (dostupnost) | `:1957` vs `:3507` |
| **Zadatci** | Zadaci predmeta | Zadaci kancelarije | `:1777` vs `:2594` |

---

## 5. Dve reči — ista stvar

| Stvar | Nazivi u upotrebi | Dokaz |
|---|---|---|
| **Otpremanje dokumenta** | „Otpremi" · „upload" · „Dodaj" | `:1084` i `:1088` — **u istom widgetu**; FAQ pitanje „Kako da uploadujem" (`:3749`) a odgovor „+ Dodaj dokument" (`:3753`) |
| Zadaci | „Zadatci" · „Zadaci" | `:739` — **u istom elementu**: `title="Zadatci i akcije na predmetu"` a labela `Zadaci` |
| AI izlaz o predmetu | „analiza" · „procena" · „ocena" | `:1588` — **tri pojma u jednoj rečenici**; `:825` „procenu predmeta" vs `:1141` „Kompletna analiza predmeta" |
| Inbox obaveštenja | „Obaveštenja" · „Notifikacije" | `:4588` vs `:4509`; prazna stanja iste liste: `vindex.js:11537` vs `:15003` |
| Čarobnjak za predmet | „+ Novi predmet" · „Intake Wizard" · „Intake čarobnjak" | `:565` · `:2139` · `:3763` |
| Poruka timu | „Pošaljite feedback" · „Pošalji poruku" · „Pomoć i podrška" | `:220` · `:3815` · `:3731` |
| Glasovna komanda | „Govori" · „Glasovna komanda" · „Vindex Live" | `:571` · `:4416` |
| Rokovi | „Rokovi" · „Kalendar" · „Ročišta" · „termini" · „događaji" | `:458` · `:2775` · `:2774` · `:1658` · `vindex.js:14293` |
| Obrazac | „šablon" · „predložak" | `:2505` vs `:2763` |
| Izvoz/uvoz | „Export/Import" · „Izvezi/Uvezi" | `:2114` vs `:2387`; `:3475` vs `:2966` |
| Dosije | „dossier" · „dosije" | `:3353` vs `:3252` — **ista reč, dva pisanja, 100 linija razmaka** |
| Pokretanje | „Start/Stop" · „Pokreni/Zaustavi" | `:726`/`:727` vs `vindex.js:12983`/`13000` — dugme kaže „Start", toast kaže „pokrenut" |
| Kopiranje | „Copy" · „Kopiraj" | `vindex.js:19491` vs `:19493` — **susedne linije** |
| Pregledač | „browser" · „pregledač" | `vindex.js:16666` vs `:16639` |
| Predmet | „predmet" · „slučaj" · „Case" | `:1634` — **oba u istoj rečenici**; `:3043` vs `:3117` |
| Kontakt tima | `privacy@vindex.ai` · `info@vindex.rs` · `kontakt@vindex.ai` · `support@vindex.ai` | `:4687` · `vindex.js:1054` · `vindex.js:8262` · `static/status.html` |

---

## 6. Rečnik proizvoda — brojevi

Brojano je samo korisnički vidljivo (tekstualni čvorovi, `placeholder`, `title`, `aria-label`, opcije, `showToast`). Isključeni su ID-jevi, klase, imena funkcija i komentari.

| Grupa | Dominantan oblik | Konkurenti | Ocena |
|---|---|---|---|
| predmet (262) | **predmet** | slučaj (6), Case (1) | Dobro — samo rezidui |
| dokument (94) | **dokument** | fajl (14), datoteka (0) | Dobro — podela po tehničkom/pravnom kontekstu, uz 3-4 prekršaja |
| analiza (129) | **analiza** | procena (41), provera (~10 stvarnih), obrada (3 kao UI radnja) | **Loše** |
| klijent (72) | **klijent** | stranka (8) | Dobro — podela je semantički opravdana (ugovorni odnos vs. procesna uloga), ali nigde objašnjena osim u legendi `:1556` |
| nacrt/podnesak/šablon | trojni sistem | + „predložak" (peti sinonim) | Srednje |
| rok (87) | **rok** | ročište (26), kalendar (5), termin (2), događaj (1) | Srednje |
| zadaci | podeljeno | Zadatci vs Zadaci | **Loše** |
| obaveštenje (8) | podeljeno | notifikacija (6), upozorenje (5) | **Loše** |
| pretraga (34) | **pretraga** | nema | **Najčistija grupa** — nula anglicizama, nula sinonima |
| otpremanje | podeljeno | otpremi (11), upload (13), dodaj (37) | **Najgora grupa** |

---

## 7. Engleski termini u srpskom interfejsu

### 7.1 Anglicizmi koji **već imaju srpski prevod u istom proizvodu**

Ovo su prave nedoslednosti — proizvod zna srpsku reč, ali je ne koristi svuda.

| Engleski | Srpski koji već postoji | Dokaz |
|---|---|---|
| upload / uploadujte | **otpremi / otpremanje** | `:1088`, `:2189`, `:3749` vs `:638`, `:1084`, `:2320` |
| Export / Import | **Izvezi / Uvezi** | `:2114`, `:3475` vs `:2387`, `:2966` |
| Wizard | **čarobnjak** | `:2139`, `:2465` vs `:3763` |
| Notifikacije | **Obaveštenja** | `:4509`, `:3883` vs `:582`, `:4588` |
| Start / Stop | **Pokreni / Zaustavi** | `:726`, `:727` vs `vindex.js:12983` |
| Copy | **Kopiraj** | `vindex.js:19493` vs `:19491` |
| browser | **pregledač** | `vindex.js:16666` vs `:16639` |
| preview | **Pregled** | `vindex.js:13393` vs `:606` |
| Billing | **Naplata** | `:2238` vs `:2619` |
| Retry | **pokušajte ponovo** | `vindex.js:15007` vs `:13362` |
| dossier | **dosije** | `:3353` vs `:3252` |

### 7.2 Nazivi modula bez ijednog srpskog oblika

Vindex Intelligence · Case Intelligence · Litigation Intelligence · Outcome Intelligence · Judge Intelligence Profiler · Copilot · Intake · Workflow · Workspace · Portfolio · Dashboard · feedback · Brief / Briefing / Battle Report · Playbook · Genome · Law Firm Brain · Hearing Command Center · Digital Twin · Cross-doc · Due Diligence · Regulatory Review · Wallet Risk Assessment · Source of Funds · Exchange Reporting Simulator · Compliance · Screening · Documentation Health · Coverage · Kanban · Waitlist / Early Access · Upgrade · Usage Analytics · Retention · Funnels · Win rate · Follow-up · Soft-delete · Cooldown

**Obrazac:** engleski se gomila u dva sloja — (a) modul za digitalnu imovinu (`vindex.js:2171-2194`), gde je više od pola naziva neprevedeno, i (b) nazivi „inteligentnih" funkcija. Za advokata koji ne radi Web3, prva grana deluje kao druga aplikacija.

### 7.3 Usputni pravopisni nalaz

`:1848` — **„Anonymni benchmark"**; treba „Anonimni".

---

## 8. Predlog ujednačenog rečnika

| Pojam | Preporučen jedan naziv | Obrazloženje |
|---|---|---|
| Predmet | **predmet** | Već dominira (262:6) — samo očistiti „slučaj" i „Case" |
| Spis | **dokument** | Pravnički tačno; „fajl" zadržati samo za CSV/veličinu |
| Slanje dokumenta | **priložite** | Jedan glagol; „upload" izbaciti u potpunosti, uključujući tekst pomoći |
| AI izlaz o predmetu | **procena** | „Analiza" je preopterećena; „ocena" izbaciti |
| Rok | **rok** | „Ročište" zadržati kao podvrstu, ne kao sinonim; „termin" i „događaj" izbaciti |
| Zadaci | **zadaci** | Savremena norma; uskladiti tooltip na `:739` |
| Inbox | **obaveštenja** | „Notifikacije" zadržati samo za kanale dostave (email/SMS/push) |
| Obrazac | **šablon** | „Predložak" izbaciti |
| Poruka timu | **podrška** | Jedna reč za kanal; kategorije razdvajaju nameru |
| Prijava na nalog | **prijava** | Zadržati isključivo za nalog |
| Lista čekanja | **zatražite pristup** | Ukloniti reč „prijava" iz ovog konteksta |
| Glasovna komanda | **brza komanda** / **razgovor** | Dva sistema — dva imena |
| Diktat | **diktiranje** | Jasno razdvojiti od komandovanja |

---

## 9. Kandidati za konsolidaciju

> **Nijedan predlog nije izvršen. Ovo je lista za odluku vlasnika.**

### K-1 · Oživeti „Pomoć & podrška" u sidebaru
**Stanje:** `index.html:533` — stilizovano kao klikabilno, bez slušaoca igde u `static/`.
**Predlog:** povezati sa Podešavanja → `#pomoc-section`.
**Obrazloženje:** sadržaj pomoći već postoji i kvalitetan je. Jedini problem je što do njega vodi samo put kroz Podešavanja, dok stavka koja *izgleda* kao pravi ulaz ćuti. Najjeftinija popravka sa najvećim efektom.

### K-2 · Popraviti ili ukloniti tri mrtve kontrole
**Stanje:** „Generiši nacrt tužbe" (`:4036`) i „Pošalji u Strategiju" (`:4037`) ciljaju navigaciju koja je ukinuta kada su tabovi `n` i `t` pretvoreni u modove unutar `aiws`. `#tab-n` više ne postoji.
**Obrazloženje:** ovo je zaostatak refaktorisanja, ne dizajnerska odluka. Korisnik koji je upravo dobio analizu i hoće da je pretvori u tužbu — što je najvredniji trenutak u celom toku — klikne i ne dobije ništa, čak ni poruku o grešci.

### K-3 · Razdvojiti dva plutajuća dugmeta
**Stanje:** `#feedback-fab` je `right:18px; bottom:18px; 42px; z-index:7000` (`index.html:214`). `#vx-voice-fab` je `right:1.5rem; bottom:1.5rem; 56px; z-index:9990` (`vindex.css:3630-3641`). Preklapaju se preko oko 36×36 px površine feedback dugmeta, a glasovno je iznad.
**Uzrok je dokumentovan u samom kodu.** Komentar iznad pravila (`vindex.css:3626-3629`) tvrdi: *„donji desni je slobodan (nijedan drugi `position: fixed` element ne stoji tamo; **provereno u ovom fajlu**)"*. Provera je bila ograničena na `vindex.css`, a `#feedback-fab` je stilizovan **u liniji unutar `index.html`** — pa je promašen.
**Obim:** samo desktop. Na mobilnom (`vindex.css:3760-3762`) glasovno dugme se pomera levo.

### K-4 · Preimenovati kontrole po radnji, ne po odredištu
**Stanje:** 15 kontrola nosi naziv rezultata a otvara praznu formu (§2.2).
**Predlog:** „Analiza rizika" → **„Pripremi analizu rizika"** ili **„Analiza rizika →"** sa strelicom koja signalizira korak; „Pokreni analizu" (`:206`) → **„Postavi pravno pitanje"**.
**Obrazloženje:** ovo je najrasprostranjeniji semantički problem u proizvodu. Nije reč o kvaru — funkcije rade — nego o tome da svaki takav klik troši poverenje. Advokat nauči da dugmad „ne rade", pa prestane da ih pritiska.

### K-5 · Ukloniti lažni indikator napretka
**Stanje:** `:1596` — inline `setTimeout` menja labelu u „Analiziram…" na 3 sekunde iako se ne poziva nijedan API.
**Obrazloženje:** ovo nije samo neusklađena labela nego aktivna dezinformacija o stanju sistema.

### K-6 · Jedan kanal za poruke, kategorije kao razlika
**Stanje:** dva ulaza vode na isti endpoint; treći („Tačnost odgovora") duplira namensko dugme, ali gubi kontekst — ne šalje sporni odgovor.
**Predlog:** zadržati **jedan** ulaz sa izborom namere; kategoriju „Tačnost odgovora" ukloniti i uputiti korisnika na dugme uz sam odgovor, jer ono jedino nosi kontekst (`reported_errors` čuva i pitanje i odgovor, `vindex.js:7998-8002`).

### K-7 · Razdvojiti deljeno ograničenje podrške i feedbacka
**Stanje:** `routers/support.py:198` — `@limiter.limit("5/hour")` na jedinom endpointu koji opslužuje oba ulaza.
**Posledica:** advokat koji pošalje pet ocena ostaje bez kanala za prijavu kvara narednih sat vremena. Namena sa najvišim prioritetom deli kvotu sa onom sa najnižim.

### K-8 · Ne obećavati odgovor koji možda nije ni poslat
**Stanje:** `routers/support.py:148-150` — ako `EMAIL_SMTP_HOST` nije podešen, funkcija tiho izađe. `_save_ticket` (`:190-193`) guta grešku na `debug` nivou. Endpoint svejedno vrati `{"ok": True, "message": "Poruka je poslata. Odgovorićemo u roku od 24h."}` (`:216`).
**Provereno:** `EMAIL_SMTP_HOST` postoji u `.env.example:85`, ali **ne** u lokalnom `.env`. Stanje u produkciji je `UNVERIFIED`.

### K-9 · Uvesti poruku umesto tihog odustanka
**Stanje:** pet kontrola (§3.1) uradi `return` bez ijedne poruke kad nema otvorenog predmeta.
**Predlog:** ili poruka („Otvorite predmet…", kako to već rade druge kontrole u §3.3), ili onemogućeno dugme sa objašnjenjem.
**Obrazloženje:** aplikacija već ima ustaljen obrazac za ovo na šest mesta — ovih pet su izuzeci, ne nova funkcionalnost.

### K-10 · Odvojiti „Dokumenti" od „Dokumenti"
**Predlog:** sekciju u Podešavanjima preimenovati u „Pravni i bezbednosni akti".
**Obrazloženje:** advokat koji u Podešavanjima vidi „Dokumenti" očekuje podešavanja svojih spisa (format izvoza, memorandum), a dobija Vindeksov whitepaper i DPA.

### K-11 · Uskladiti navigaciju sa naslovima
**Predlog:** „Rokovi" → stranica „Rokovi" (ne „Kalendar"); „Zadatci" → „Zadaci" (uključujući tooltip na `:739`).

### K-12 · „Šabloni dokumenata" ne treba da izgleda kao tab
**Predlog:** ili pravi tab, ili vizuelno razlikovan (dugme sa oznakom da otvara prozor).

### K-13 · Jedan glagol za otpremanje
**Predlog:** izabrati **„priložite"** (ili „dodajte") i sprovesti svuda, uključujući `:1088` gde „upload" stoji direktno ispod dugmeta „Otpremi dokument".

### K-14 · Ujednačiti naziv čarobnjaka
**Predlog:** **„Novi predmet"** svuda — bez „Intake Wizard" i bez „Intake čarobnjak".
**Obrazloženje:** tekst pomoći (`:3763`) upućuje korisnika na „Intake čarobnjak", a ta reč se nigde drugde u interfejsu ne pojavljuje — korisnik je traži i ne nalazi.

### K-15 · Prevesti modul za digitalnu imovinu
**Predlog:** prevesti nazive kartica i modula (`vindex.js:2171-2194`).

### K-16 · Jedna kontakt adresa
**Predlog:** svesti četiri adrese na jednu javnu (npr. `podrska@`), uz zadržavanje `privacy@` gde to nalaže propis.
**Obrazloženje:** dva različita domena (`.ai` i `.rs`) za isti proizvod otvaraju pitanje autentičnosti — korisnik ne zna koja je adresa prava.

### K-17 · Razdvojiti nazive tri glasovne funkcije
**Predlog:** „Govori" → **Brza komanda**; „Vindex Live" → **Razgovor**; „Glasovni unos" → **Diktiraj**.

---

## 10. Šta je ostalo neprovereno

| Stavka | Razlog |
|---|---|
| Sadržaj „Pregled dana" | Generiše se dinamički u `kc-body` |
| „Portfolio kancelarije" | `display:none` u polaznom stanju; uslov otkrivanja nije praćen do kraja |
| Stanje SMTP-a u produkciji | Vidljiv samo lokalni `.env` i `.env.example` |
| Ponašanje na dodirnim uređajima | Tooltipovi (`title`) se na dodir ne prikazuju — pogađa sve kontrole koje se oslanjaju samo na tooltip (npr. oba plutajuća dugmeta), ali nije mereno |
| Mod `'ob'` („Pravne oblasti") | `vindex.js:2244` — nema pozivaoca u glavnom UI, dostupno samo kroz mobilni meni |

---

*Kraj dokumenta. Nijedna izmena nije izvršena ni nad jednim fajlom osim ovog.*
