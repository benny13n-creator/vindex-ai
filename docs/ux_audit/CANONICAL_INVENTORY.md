# APP INTERACTION FORENSICS — KANONSKI INVENTAR

**Baseline:** `16e9ef8cc6fd3e0c35d8c92d07917ad79df515bf` · 4989 passed / 1 skipped / 0 failed
**Datum:** 2026-08-12
**Promena UI-ja u ovom sprintu:** **NULA.** Nijedan `index.html`, `static/vindex.js`
ni `static/vindex.css` nije dirnut. Ovo je audit, ne popravka.

Šest agenata je radilo nezavisno. Ovaj dokument je **jedina odluka**. Gde se
izveštaji ne slažu, ovde stoji šta je stvarno tačno i zašto — sa dokazom koji
sam sam ponovo izmerio, ne prepisao.

---

# 0. ŠTA JE POPISANO

| | |
|---|---|
| Interaktivnih elemenata | **1.014** (781 statičkih, 233 dinamički generisanih) |
| Registrovanih backend ruta | 618 |
| `fetch` poziva iz frontenda | 303 |
| Različitih imena rukovalaca iz DOM-a | 430–445 |
| Funkcionalnih grupa | 36 |

Puni popis reda-po-red: **`UX_INVENTORY.md`** (2.979 linija). Ovaj dokument ne
ponavlja 1.014 redova — navodi **svaku kontrolu koja NIJE čista**, jer se odluke
donose samo o njima. Sve ostalo je `VERIFIED / GO`.

---

# 1. PRVO — ČETIRI STVARI KOJE SU AGENTI POGREŠILI

Orkestrator ne prepisuje. Ovo su tačke gde sam morao da presudim.

### 1.1 „Nula dugmadi bez rukovaoca" — **NETAČNO kako je formulisano**

Kartograf i Forenzičar su nezavisno prijavili **0 od 430** imena rukovalaca koja
ne postoje. To jeste tačno — ali meri pogrešnu stvar. Pitanje nije „da li
`onclick="X()"` pokazuje na postojeće `X`", nego **„da li kontrola radi kad se
klikne"**.

Kontrola koja **uopšte nema `onclick`** ne ulazi u tu proveru. Sam sam našao
najmanje jednu takvu, i ona je mrtva:

```
index.html:533   <div class="vx-foot-row vx-sidebar-help">  ← nema onclick
grep -rn 'vx-sidebar-help' static/ index.html
  → 6 pogodaka, SVIH 6 su CSS. Nijedan addEventListener. Nijedan rukovalac.
static/vindex.css:4980  .vx-sidebar-help:hover { color: ... }  ← izgleda živo
```

**Presuda: „Pomoć & podrška" je mrtva kontrola.** Semantički agent ju je našao,
druga dva je nisu ni tražila. Metodološka pouka: „ime rukovaoca postoji" nikad
neće uhvatiti „rukovaoca nema".

### 1.2 Vidljiv fokus — **agent je oborio polaznu pretpostavku, i bio je u pravu**

Ušao sam u sprint sa tvrdnjom da fokusa nema (`focus-visible` = 0 pojava).
Agent za pristupačnost je to izmerio piksel-diffom i pokazao suprotno: Chromium-ov
adaptivni prsten radi (razlika kanala **152–255**, ručni `outline` daje 247), jer
`outline:none` nigde nije globalan — svih 22 pojave su ciljane.

**Prihvatam ispravku.** Ali sa dve ograde koje agent takođe navodi: 6 od 7
porodica polja gasi outline i zamenjuje ga promenom `border-color` od **1,86:1**
(prag je 3:1), a `vindex.css:2922` ima `outline:none !important` na `.t-tab` —
što je latentna zamka opisana u §4.1.

### 1.3 `landing.html:46` — **nalaz je zastareo**

Zadao sam agentu da proveri `landing.html:46`. Taj fajl je obrisan u `f1865d4b`
tokom Website sprinta. Agent je to primetio i odbio nalaz. Tačno.

### 1.4 `micToggle` vs `vxLiveOpen` — **hipoteza potvrđena, ali sam gledao pogrešan par**

Upozorio sam agenta da to verovatno **nisu** duplikati. Dokazao je da nisu — ne
dele nijednu od pet osa; `micToggle` nema **nijedan** `fetch`.

Ali je našao ono što ja nisam: glasovnih sistema nije dva nego **tri**.
Pravi kandidat za spajanje je **`voice_start`** (dugme „Govori" + `Alt+V`), ne
`micToggle`. Vidi `M-001`.

---

# 2. KANONSKA TABELA — SVE KONTROLE KOJE NISU ČISTE

Rečnik statusa: `VERIFIED` · `PARTIALLY_VERIFIED` · `BROKEN` · `DUPLICATE` ·
`DEAD` · `OBSCURED` · `UNVERIFIED`

## 2.1 `OBSCURED` — kontrola postoji, radi, ali korisnik ne može da je klikne

Ovo je najteža kategorija u celom auditu, jer nijedan test nije ni pokušavao da
je meri. Dokaz je `document.elementFromPoint` nad mrežom 7×7 = 49 tačaka po
kontroli, u stvarnom pregledaču, na 7 širina.

| ID | Kontrola | Lokacija | Funkcija | Radi? | Dokaz | Presuda |
|---|---|---|---|---|---|---|
| **O-001** | `#feedback-fab` 💬 | `index.html:214` | Slanje povratne informacije | **kod radi, klik nemoguć** | **49/49 tačaka blokirano na SVIH 7 širina.** Desktop: `#vx-voice-fab` (z **9990**) preko njega (z **7000**), presek 36×36 px. Mobilni: `#vx-mobile-nav` (z 9999). **Ne postoji širina na kojoj ovo dugme radi.** | `OBSCURED` → **P0 FIX** |
| **O-002** | `#intake-btn-next` „Dalje →" | `index.html:2300` | Glavni CTA čarobnjaka Novi predmet | **nedostupno na 390** | `[23,786,345,44]` ceo ispod `#vx-mobile-nav` `[0,784,390,60]`, z 9999 > modal z 2101. **Čarobnjak se na telefonu ne može odvesti dalje od koraka 1.** Vizuelno potvrđeno snimkom. Na 1920/1366 blokirano 14,3% (mikrofon iznad modala). | `OBSCURED` → **P0 FIX** |
| **O-003** | `#vx-voice-fab` 🎙 | `index.html:4416` | Vindex Live | nedostupno na 390 | 91,7% preseka sa `#vx-mobile-nav` | `OBSCURED` → P1 |
| **O-004** | „+ Iz dokumenta" | Pregled dana | Smart Intake ulaz | nedohvatljivo na 1024 | 87,3 od 106,6 px van ekrana (18,2% vidljivo), centar van ekrana; `.vx-body overflow-x:hidden`, `scrollWidth 931 > clientWidth 844` → **ne može se doskrolovati**. Na 768 odsečeno 51,1px. | `OBSCURED` → P1 |
| **O-005** | `#vx-back-btn` | gornja traka | Nazad | 14/49 blokirano | nominalno 44px, stvarno klikabilno **30px** — traka je 30px | `PARTIALLY_VERIFIED` → P2 |

**Sistemski uzrok O-001…O-003:** četiri fiksna sloja (**9999 / 9998 / 9990 /
7000**) dele isti donji ugao bez ijednog pravila razdvajanja, a **modal je
numerički ispod sva četiri** i nijedan se ne sklanja kad se modal otvori.

**Zašto O-001 nije uhvaćen ranije — i to je najvažnija lekcija sprinta:**
`static/vindex.css:3625` nosi komentar da je donji desni ugao slobodan jer je to
„provereno u ovom fajlu". Provera je bila iskrena i **promašila** — `#feedback-fab`
je stilizovan **inline u `index.html:214`**, pa ga pretraga CSS fajla ne vidi:

```html
<button id="feedback-fab" ... style="position:fixed;right:18px;bottom:18px;z-index:7000;...">
```

Ovo je moja greška iz Dashboard Polish sprinta. Test `test_dashboard_polish.py`
koji sam tada napisao meri geometriju dugmeta prema **bočnoj traci** i prolazi —
jer nikad ne pita šta je već u desnom uglu. Test je bio dobar za problem koji je
rešavao i slep za problem koji je stvarao.

## 2.2 `BROKEN` — klik ne daje obećani ishod

| ID | Kontrola | Lokacija | Uzrok | Presuda |
|---|---|---|---|---|
| **B-001** | Upload dokumenta (**3 ulazne tačke**) | `index.html:1085/1086` | `#pred-procena-result` **ne postoji** u `index.html` (0 pojava), a `vindex.js:20048` i `:20148` pišu u njega. `if (resEl)` zaštita → **tihi gubitak** | `BROKEN` → **P0 FIX** |
| **B-002** | „Generisi graf" + „↺ Regenerisi" | `vindex.js:22817`, `:23031` | frontend zove `/api/evidence-graph/generi%C5%A1i`, backend sluša `/generisi` (`evidence_graph.py:178`) → pada na `GET /{predmet_id}` → **405** | `BROKEN` → **P0 FIX** |
| **B-003** | „Štampaj" | `index.html:769` | `#pred-pane-ccc` ne postoji (0 pojava) → **štampa prazan predmet** | `BROKEN` → P1 |
| **B-004** | „Generiši nacrt tužbe" | `index.html:4036` | cilja tab `n`, `id="tab-n"` ne postoji (0 pojava) | `BROKEN` → P1 |
| **B-005** | „Sačuvaj u predmet" | `index.html:4035` | `#pred-novi-btn` i **oba** rezervna selektora zastareli | `BROKEN` → P1 |
| **B-006** | „Pošalji u Strategiju" | `index.html:4037` | tekst se upiše u `#strat-tekst`, ali navigacija ne uspe (isti uzrok kao B-004) → **korisnik ne vidi da je uspelo** | `PARTIALLY_VERIFIED` → P1 |
| **B-007** | „Pomoć & podrška" | `index.html:533` | **nema rukovaoca uopšte**; CSS mu daje `cursor:pointer` i hover, pa izgleda živo | `DEAD` → P1 |
| **B-008** | „Generiši / osveži procenu predmeta" | — | nema zaštite od `null`, šalje zahtev sa praznim ID-jem → generička greška umesto objašnjenja | `PARTIALLY_VERIFIED` → P2 |

### B-001 je najozbiljniji nalaz u celom auditu

Ne zato što je najveći, nego zato što **izgleda kao uspeh**. B-002 bar prikaže
grešku. B-001 ne prikaže ništa.

`#pred-procena-result` postoji u `index.html.bak:1004` i uklonjen je u commit-u
**`010082aa`** („AI Analiza flagship showcase" redizajn). Upload i dalje radi,
backend i dalje odgovara — ali odgovor nema gde da se ispiše. Tiho nestaje:

- AI procena dokumenta
- sve poruke o grešci
- kartica za automatsko povezivanje sa predmetom
- **⚠ „Originalni fajl nije sačuvan u trezoru"**

Poslednje je presudno. Komentar na `static/vindex.js:20095-20099` doslovno kaže
zašto je to upozorenje dodato:

> *„a lawyer whose signed original failed to persist to Storage saw an identical
> success screen to one whose original was safely stored, with no way to know
> the difference."*

To je nalaz **F7/F20 iz Final Beta Gate-a**. Ispravka je napisana, prihvaćena,
merge-ovana — i **nikad se ne može prikazati**, jer je kontejner u koji piše
obrisan u drugom sprintu. Advokat čiji potpisani original nije sačuvan i danas
vidi isti ekran uspeha. Popravka postoji na papiru, ne u proizvodu.

### B-002 — susedni moduli, suprotne odluke o dijakritici

Od 618 ruta, tačno **jedna** sadrži naše slovo: `/api/ugovor-zastupanja/generiši`
(`ugovor_zastupanja.py:283`). Frontend je oba modula pozvao isto
(`%C5%A1`) — jedan pogodio, drugi promašio. Nije slučajnost nego **odsustvo
pravila**.

Test `test_gamma_evidence_check_wiring.py:32` gađa ispravan ASCII put i prolazi.
Dokazuje backend i **nikad ne proverava da frontend zove istu putanju** — isti
razred greške koji je ovaj sprint našao još dva puta.

## 2.3 `DUPLICATE` — dve implementacije istog posla

**Nijedan potvrđeni duplikat ne traži brisanje dugmeta.** Svih pet su duplirane
*implementacije*, ne suvišne *kontrole*. To je bitna razlika i razlog zašto je
vlasnikovo upozorenje („prvo forenzika, pa deletion") bilo opravdano.

| ID | Par | Isto | Canonical | Presuda |
|---|---|---|---|---|
| **D-001** | `feedbackSubmit` / `pomocPosalji` | isti endpoint `/api/support/poruka` | `feedbackSubmit` (jedini ima ocenu + snimak ekrana + kontekst) | `MERGE` (druga → omotač) |
| **D-002** | `intakeKlijentSearch` / `qiKlijentSearch` | isti `/klijenti?pretraga=`, ista CSS klasa | `qiKlijentSearch` (koristi `escHtml`; druga kopija ima **slabiji escaping**) | `MERGE` — bezbednosni razlog |
| **D-003** | `doc_upload_file` / `intakeUploadFile` | isti `/api/dokument/upload` | `doc_upload_file` (jedini validira tip i veličinu) | `MERGE` |
| **D-004** | `voice_start` / `vxLiveOpen` | isti posao za korisnika, 2 dugmeta, 2 modala, 2 traženja mikrofona | `vxLiveOpen` (radi na iOS-u, ima potvrdu pred izmenu podataka) | `MERGE` — **ali tek posle M-001** |

## 2.4 `DEAD` — funkcija bez ijednog ulaza

| ID | Šta | Dokaz | Presuda |
|---|---|---|---|
| **DE-001** | `pred_openNewModal()` / `#pred-new-modal` | modal ceo postoji u `index.html:379-410`, **nijedan poziv ga ne otvara**. Ide na `POST /api/predmeti` koji — za razliku od intake toka — **ne veže klijenta, ne dodaje rok, ne veže dokumente**. Komentar u `api.py:3695` još ga zove „standardni + Novi predmet tok"; to više nije tačno | `REMOVE` uz potvrdu |
| **DE-002** | `qiOtvori()`, `bulkOtvori()` | dugmad su `display:none`, kod se i dalje održava | `REMOVE` uz potvrdu |
| **DE-003** | ~18 legacy DOM ID-jeva | od 1490 `getElementById` poziva, **31 ID ne postoji** | `REMOVE` uz potvrdu |

## 2.5 `NIJE DUPLIKAT` — izgleda isto, mora ostati

Ovo je polovina vrednosti audita: sprečeno brisanje.

| Izgleda kao | Zašto NE | Presuda |
|---|---|---|
| `voice_start` = „stara verzija" Vindex Live-a | ima **~17 akcija** (`show_tab`, `start_timer`, `export_pdf`, `navigate_predmet`…) koje se izvršavaju **u pregledaču**. Vindex Live ima **3 alata** (`shared/voice_tools.py`) koji rade **na serveru**. Brisanje bi ugasilo 17 funkcija bez zamene | **NE BRISATI** |
| „Prijavi netačan odgovor" = još jedno feedback dugme | ide u tabelu `reported_errors`, ne u tikete podrške. **Jedini kanal kojim advokat prijavljuje netačan pravni odgovor** — za pravnu aplikaciju najvredniji signal koji imate | **NE BRISATI** |
| „+ Novi predmet" = „+ Iz dokumenta" | različiti endpointi; Smart Intake ima ekran za ispravku AI-izvučenih entiteta kojeg u wizard-u nema | **NE BRISATI** |
| 7 upload dugmadi = jedno dugme | 7 različitih poslova (predmet / pitanja nad dokumentom / wizard / smart intake / playbook / klijentski portal / admin) | **NE BRISATI** |
| `pred_launchKompletnaAnaliza` sa 5 ulaza | **prečica, i to referentno urađena** — guard `_stratOrkUToku` živi u funkciji, ne na dugmetu | **NE DIRATI** |
| `micToggle` = `vxLiveOpen` | ne dele nijednu od 5 osa; `micToggle` nema nijedan `fetch` | **NE BRISATI** |

---

# 3. SEMANTIKA — LABELA OBEĆAVA VIŠE NEGO ŠTO DAJE

Ovo nisu kvarovi. Kod radi tačno kako je napisan. Problem je što **korisnik iz
naziva ne može da zaključi šta će se desiti** — a to je u pravnoj aplikaciji
skuplje od kvara, jer advokat nauči da dugmad ne rade i prestane da ih pritiska.

| ID | Kontrola | Obećava | Radi | Presuda |
|---|---|---|---|---|
| **S-001** | „Pokreni kompletnu analizu" (`index.html:1596`) | analizu | **3 sekunde prikazuje „Analiziram…" bez ijednog API poziva** | `RENAME` — **P1, ovo je aktivna dezinformacija o stanju sistema, ne loša labela** |
| **S-002** | „Digital Twin — simulacija razvoja" (`:1256`) | 3 scenarija | rukovalac ima **tri linije**, samo otkriva panel | `RENAME` P2 |
| **S-003** | „Pokreni analizu" (`:206`) | analizu | otvara prazno polje za pitanje o zakonu | `RENAME` P2 |
| **S-004** | 15 kontrola: „Analiza rizika", „Procena ishoda", „Predikcija ishoda", „Analiza svedoka"… | rezultat | menjaju tekst opisa, traže još 2 klika | `RENAME` P2 |

Za kontrast: **Web3 sloj je semantički najpošteniji deo aplikacije** — labele su
glagoli, rukovaoci zaista izvršavaju.

### 3.1 Ista reč, različit posao — i obrnuto, na istom mestu

| | |
|---|---|
| **Isti naziv, različit posao** | „Pokreni analizu" u Quick Actions → `openAITool('q')` = pitanje o zakonu. „Pokreni analizu" u ⌘K → **šestomodulna strateška analiza koja troši kredite** |
| **Različit naziv, isti posao** | ⌘K „Pitaj AI" = Quick Actions „Pokreni analizu" — identičan poziv |

Popravka je **preimenovanje, nula promena ponašanja**.

### 3.2 Pomoć / Podrška / Feedback / Kontakt — pet namera, dva odredišta

Sve — problem, predlog, ocena, primedba — završava na `/api/support/poruka`,
istom mejlu, istoj tabeli. Kategorija menja **isključivo naslov e-poruke**.

Dve posledice koje niko nije projektovao:
- ograničenje **5/sat je deljeno** → pet poslatih ocena blokira **prijavu kvara**
  na sat vremena
- „Odgovorićemo u roku od 24h" prikazuje se **i kada slanje tiho zakaže**

### 3.3 Rečnik — tri najgore nedoslednosti

1. **otpremi / upload / dodaj** — tri glagola za jednu radnju, na `:1084` i
   `:1088` u **istom widgetu**. Pomoć pita „Kako da uploadujem", odgovor kaže
   „+ Dodaj dokument"
2. **analiza / procena / ocena** za isti AI izlaz — `:1588` ima **sva tri pojma
   u jednoj rečenici**
3. **Zadatci / Zadaci** — `:739` ima obe varijante u **istom elementu**
   (tooltip „Zadatci", labela „Zadaci")

Uz to: „Intake čarobnjak" iz pomoći **nigde ne postoji** u interfejsu.

### 3.4 Pet kontrola koje tiho odustanu

„Pokreni simulaciju" · „Analiziraj" (šta-ako) · „AI Briefing" · „Winning Strategy
Brief" · „Digital Twin" — traže otvoren predmet i **ne kažu ništa** ako ga nema.

Aplikacija **već ima ustaljen obrazac** za ovo („Otvorite predmet…") na **šest
drugih mesta**. Ovih pet su izuzeci, ne pravilo — popravka je poznata i lokalna.

---

# 4. PRISTUPAČNOST

## 4.1 `BLOKIRA` — glavna navigacija je nedostupna tastaturom

`index.html:444–511` — **15 stavki**, sve `<div class="t-tab" onclick=...>` bez
`role` i bez `tabindex`. Pregled dana, Predmeti, Klijenti, Rokovi, Vindex
Intelligence, Sudska praksa, Dokumenti, Šabloni, Zadatci, Finansije, Kancelarija,
Portfolio, Podešavanja + 2 skrivena.

Izmereno u pregledaču: `element.tabIndex === -1` za svih 15; **60 pritisaka `Tab`
→ 0 zaustavljanja** na bilo kom `.t-tab`. Sam sam potvrdio: `grep -c tabindex
index.html` = **0**.

**Korisnik bez miša ne može da pređe ni na jedan ekran aplikacije.** To nije rubni
slučaj — to je prva radnja posle prijave.

Ironija: obrazac **već postoji u istom fajlu**. `index.html:1147–1157` ispravno
koristi `role="tablist"` / `role="tab"` / `aria-selected`. Glavna navigacija ga
prosto ne koristi.

**Zamka pri popravci:** `static/vindex.css:2922` ima `outline:none !important` na
`.t-tab`. Kad se doda `tabindex`, tabovi će primati fokus **bez ikakvog vidljivog
traga**, a `!important` će nadjačati svaku popravku koja ne dira baš tu liniju.

Šire: **124 od 124** klikabilna ne-native elementa u početnom DOM-u nemaju ni
`role` ni `tabindex` — uključujući **dugme „Pokušaj ponovo" posle greške**
(`vindex.js:1307`, `:1774`), pa je i oporavak od greške nedostupan.

Nijedan od **8 modala** nema zamku fokusa ni vraćanje fokusa (`activeElement`,
`lastFocused` → 0 pogodaka u celom `vindex.js`); **6 od 8** se ne zatvara
tasterom `Escape`.

## 4.2 `BLOKIRA` — `aria-live` = 0, uz 353 poziva `showToast()`

Sam sam proverio: `grep -c aria-live index.html static/vindex.js` → **0 i 0**.

Nijedna potvrda, greška ni upozorenje nikad nije izgovoreno — **uključujući poruku
o mogućoj dvostrukoj naplati** (`vindex.js:7684`). Rezultat AI analize ispisuje se
efektom kucanja u kontejner bez `aria-live`, pa se pojavi neobjavljen.

## 4.3 Pristupačna imena

| | |
|---|---|
| `<button>` bez imena | **0 od 436** — i 0 od 20 `<a>`, 0 slika bez `alt`. **To je stvarna snaga aplikacije** |
| Polja bez programske labele | **175 od 203 (86%)** — samo `placeholder`. Uključujući **prijavu, registraciju i reset lozinke** |
| Elemenata bez teksta/`title`/`aria-label` | 72 |
| `<label for=...>` | **3** na 62 `<label>` elementa — labele su vizuelne, ne programski povezane |

Kod nekih polja je placeholder **izmišljeno ime** („Petar Petrović"), pa čitač
ekrana izgovara osobu umesto naziva polja.

## 4.4 Kontrast

`--tx-3` = **2,47:1**, u upotrebi **23×**. `--tx-4` = **1,48:1**, **16×**.
Ukupno **27,8%** tekstualnih deklaracija pada u tamnoj temi (340/1224), **48,5%**
u svetloj (113/233) — a svetla tema je dostupna korisniku (`vindex.js:19903`).

Najozbiljnije po sadržaju — baš oni trenuci kad korisnik traži objašnjenje:

| Šta | Odnos | Gde |
|---|---|---|
| **Pravno odricanje odgovornosti** | **4,09:1** i **3,56:1** | `vindex.css:112`, `:298` |
| **Obaveštenje o privatnosti** | **1,84:1** | `:624` |
| Prazna stanja | 2,87:1 | `:679` |
| Stanja učitavanja | 2,47:1 | `:811` |

## 4.5 Stanja

**Stanja učitavanja su dobra** — sve četiri duge radnje ih imaju (spinner +
onemogućeno dugme + tekst tipa „Forenzička analiza u toku… (30-60s)"). Poruke o
greškama uglavnom prolaze kroz `_friendlyErr()` i na srpskom su.

Problem je drugde:

- **143 tiha neuspeha** — 72 prazna `catch (e) {}`, 64 prazna `.catch()`, 7 samo
  `console.warn`. Najgori: `vindex.js:21137` — ekstrakcija dokumenata u intake
  čarobnjaku **tiho preskoči fajl koji padne**, pa korisnik vidi „uspešno
  završeno" sa nepotpunim podacima
- **Isključena dugmad ne kažu zašto** — **0 od 86** mesta koja postavljaju
  `disabled = true` ne postavlja `title`. Uz `opacity:0.40` tekst pada na ~1,6:1:
  korisnik vidi sivo dugme, ne zna zašto, i **ne može da pročita šta piše**

## 4.6 Dodirne mete ispod 44px na 390

`#notif-bell` **16×16** · 2× „Vidi sve →" **75×16** · „Još 14 predmeta ▾"
367,7×24 · `#vx-back-btn` stvarno klikabilnih 30px.

---

# 5. PRESUDE — REDOSLED

**Nijedna izmena nije izvršena.** Ovo je predlog; brisanja traže vašu potvrdu.

## P0 — korisnik gubi funkciju ili podatke, popravka je mala

| ID | Šta | Zašto sada |
|---|---|---|
| **B-001** | vratiti `#pred-procena-result` (ili preusmeriti pisanje) | ⚠ upozorenje o nesačuvanom originalu — nalaz **F7/F20 iz Final Beta Gate-a** — merge-ovano a nikad prikazano. Advokat i danas ne zna da mu original nije sačuvan |
| **B-002** | uskladiti `/api/evidence-graph/generisi` | jedini pokvaren `fetch` od 303; funkcija potpuno nedostupna |
| **O-001** | razdvojiti `#feedback-fab` i `#vx-voice-fab` | dugme nedostupno **na svakoj širini**; moja greška iz Dashboard Polish sprinta |
| **O-002** | `#intake-btn-next` iznad `#vx-mobile-nav` | **čarobnjak Novi predmet je na telefonu neupotrebljiv posle koraka 1** |
| **§4.1** | `role="tab"` + `tabindex` na 15 `.t-tab` + ukloniti `outline:none !important` na `vindex.css:2922` | bez miša aplikacija se ne može koristiti; obrazac već postoji u istom fajlu na `:1147` |

## P1

`B-003` `B-004` `B-005` `B-006` `B-007` · `O-003` `O-004` · `S-001` (dezinformacija
o stanju sistema) · `aria-live` na `showToast` · pet kontrola koje tiho odustanu
(§3.4) · deljeno ograničenje 5/sat na podršci

## P2

`S-002…S-004` preimenovanja · rečnik (§3.3) · `title` na isključenoj dugmadi ·
kontrast `--tx-3`/`--tx-4` · dodirne mete · `<label for>` · `B-008` `O-005`

## MERGE — tek posle P0/P1, nijedan ne briše dugme

`D-002` prvi (**bezbednosni razlog** — slabiji escaping) · zatim `D-001`, `D-003` ·
`D-004` **tek posle M-001**

## M-001 — preduslov za `D-004`

Pre spajanja glasa: preneti **~17 pregledačkih akcija** iz `voice_start` u Vindex
Live. Do tada `voice_start` **ostaje**. Brisanje pre toga gasi 17 funkcija bez
zamene.

## REMOVE — traži vašu izričitu potvrdu

`DE-001` `DE-002` `DE-003`. Ne diram ih sam.

---

# 6. `UNVERIFIED` — nije dokazano, ne tvrdi se

1. **Da li `agent_run()` (glasovne komande `analyze_predmet`/`procena_rizika`)
   gađa isti orkestrator kao `stratOrkestratorPokreni`.** Ako da, **glas je peti
   neguardovan ulaz u naplativu operaciju.** Najvredniji otvoreni trag u auditu
2. Gejtovanje po tarifi — u `index.html` nema nijednog `data-tier`/`pro-only`
   markera; zaključavanje se radi iz JS-a u vreme izvršavanja
3. Geometrija je merena **samo na tabu „Pregled dana"** i **samo na koraku 1/5**
   jednog modala. Ostalih 10 tabova, auth modal, waitlist, PRO upgrade, šabloni —
   **nemereno**
4. Nalazi koliko redova pada u zonu donje navigacije zavise od količine podataka
   u fixture-ima i treba ih ponoviti na stvarnom nalogu. **Nalazi o fiksnim
   slojevima ne zavise od podataka**
5. Nisu testirani pravi uređaji (iOS `safe-area-inset` može **pogoršati** O-002),
   ni pejzaž na mobilnom, ni skrolbar Windows-a (~15px — odsecanje na 1024 je
   **donja granica**)
6. Ponašanje rukovalaca nije izvršavano — provereno je da postoje i da su globalno
   dostupni
7. Da li `support_tickets` i `reported_errors` završavaju u istom pregledu za vas
8. Da li je `voice_start` **namerno** zadržan kao rezerva — u kodu nema ni
   komentara ni feature flag-a

---

# 7. ŠTA OVAJ AUDIT KAŽE O NAČINU RADA

Pet od pet kvarova u §2.2 ima **isti oblik**: ugovor između dva sloja promenjen
s jedne strane, druga strana **nije ni pukla ni prijavila**. Odbrambeni obrazac
`if (!el) return;` pretvorio je svaki glasni `TypeError` u tihi gubitak funkcije.

Tri puta u ovom sprintu se ponovio isti razred greške u **testovima**:
`test_gamma_evidence_check_wiring.py` dokazuje backend rutu i nikad ne pita da
li je frontend zove; `test_dashboard_polish.py` dokazuje da voice dugme ne
prekriva bočnu traku i nikad ne pita šta je već u desnom uglu. Oba testa su
tačna. Oba mere jednu stranu ugovora.

**Dve CI provere bi uhvatile većinu §2.2 istog dana:**

1. svaki `getElementById('X')` u `vindex.js` → `X` postoji u `index.html`
   (uhvatilo bi **B-001, B-003, B-005** i 31 mrtav ID)
2. svaki `fetch(BASE_URL + '/api/…')` → putanja postoji među 618 ruta
   (uhvatilo bi **B-002**)

Treća, za §2.1: geometrijski test koji nad **svim** fiksno pozicioniranim
elementima traži preklapanje — umesto po jednog testa po dugmetu.

Predlažem ih, ne pišem ih. Ovaj sprint je audit.

---

# 8. STANJE

```
HEAD:        16e9ef8cc6fd3e0c35d8c92d07917ad79df515bf   (nepromenjen)
Testovi:     4989 passed / 1 skipped / 0 failed          (nepromenjeno)
index.html:      0 izmena
static/vindex.js: 0 izmena
static/vindex.css: 0 izmena
Novo:        docs/ux_audit/  (7 dokumenata)
```

Šest izveštaja stoji uz ovaj: `UX_INVENTORY.md` (pun popis 1.014 kontrola) ·
`INTERACTION_FORENSICS.md` · `DUPLICATION_REPORT.md` · `GEOMETRY_REPORT.md` ·
`SEMANTICS_MAP.md` · `ACCESSIBILITY_REPORT.md`.

**Ovaj dokument je odluka. Oni su dokaz.**
