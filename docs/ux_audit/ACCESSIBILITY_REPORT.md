# Izveštaj o pristupačnosti i kvalitetu interakcije — Vindex AI

**Datum:** 2026-08-12
**Obim:** `index.html` (4832 linije), `static/vindex.js` (23681 linija), `static/vindex.css` (9706 linija)
**Metod:** statička analiza + merenje u pregledaču (Playwright/Chromium 1500×950) nad lokalno posluženom aplikacijom (`python -m http.server`, bez ikakvih kredencijala)
**Standard:** WCAG 2.1 AA

## Rezime

| Oblast | Ocena | Najteži nalaz |
|---|---|---|
| 1. Pristup tastaturom | **BLOKIRA** | Cela glavna navigacija (15 tabova) nedostupna tastaturom |
| 2. Vidljiv fokus | OTEŽAVA | Podrazumevani prsten POSTOJI i vidljiv je; 6 od 7 porodica polja ga gasi i menja indikatorom < 3:1 |
| 3. Pristupačna imena | OTEŽAVA | 175 od 203 polja bez programske labele; 0 `aria-pressed`/`aria-expanded` |
| 4. Stanja | OTEŽAVA | Stanja učitavanja su dobra; 143 tiha neuspeha |
| 5. Kontrast | OTEŽAVA | 27,8 % tekstualnih deklaracija pada u tamnoj temi, 48,5 % u svetloj |
| 6. Čitač ekrana | **BLOKIRA** | `aria-live` = 0 pojava; svih 353 obaveštenja neizgovoreno |

### Ispravka polazne pretpostavke

Zadatak navodi da `landing.html:46` gasi `outline` na dugmadima. **`landing.html` više ne postoji** — obrisan je u commit-u `f1865d4b` („novi javni sajt zamenjuje landing") i zamenjen sa `site/*.html`. Nalaz se više ne odnosi ni na jedan živi fajl. Merenje ispod pokazuje šta zaista važi danas.

---

## 1. Pristup tastaturom

### 1.1 Glavna navigacija je nedostupna tastaturom — `BLOKIRA`

`index.html:444–511` — svih 15 stavki glavne navigacije su `<div>` sa `onclick`, bez `role` i bez `tabindex`:

```html
444: <div class="t-tab" id="tab-btn-h"   onclick="setTab(this,'h')">      <!-- Pregled dana -->
448: <div class="t-tab" id="tab-btn-p"   onclick="setTab(this,'p')">      <!-- Predmeti -->
452: <div class="t-tab" id="tab-btn-k"   onclick="setTab(this,'k')">      <!-- Klijenti -->
456: <div class="t-tab" id="tab-btn-kal" onclick="setTab(this,'kal');...">  <!-- Rokovi -->
464: <div class="t-tab" id="tab-btn-aiws" onclick="setTab(this,'aiws')">  <!-- Vindex Intelligence -->
468: <div class="t-tab" id="tab-btn-s"   onclick="setTab(this,'s')">      <!-- Sudska praksa -->
472: <div class="t-tab" id="tab-btn-dok" onclick="setTab(this,'dok')">    <!-- Dokumenti -->
478: <div class="t-tab" id="tab-btn-doctpl" onclick="docTplOpen()">       <!-- Šabloni dokumenata -->
486: <div class="t-tab" id="tab-btn-zadaci-g" onclick="setTab(this,'zadaci-g')"> <!-- Zadatci -->
490: <div class="t-tab" id="tab-btn-fin" onclick="setTab(this,'fin')">    <!-- Finansije -->
494: <div class="t-tab" id="tab-btn-kanc" onclick="setTab(this,'kanc')">  <!-- Kancelarija -->
498: <div class="t-tab" id="tab-btn-pi-nav" onclick="...">                <!-- Portfolio kancelarije -->
504: <div class="t-tab" id="tab-btn-settings" onclick="setTab(this,'settings')"> <!-- Podešavanja -->
509: <div class="t-tab vx-hidden-tab" id="tab-btn-notif" onclick="notif_toggleDropdown()">
511: <div class="t-tab vx-hidden-tab" id="tab-btn-pi" onclick="setTab(this,'pi')">
```

**Izmereno u pregledaču:** za svih 15 elemenata `element.tabIndex === -1`. Nakon 60 uzastopnih pritisaka `Tab`, broj zaustavljanja na `.t-tab` elementu iznosi **0**.

Posledica: korisnik koji ne koristi miša ne može da pređe iz jednog dela aplikacije u drugi. Nijedan ekran osim početnog nije dostupan.

Obrazac je poznat u ovoj bazi koda i primenjen je na drugom mestu — `index.html:1147–1157` (`.vx-phase-tabs`) ispravno koristi `role="tablist"` / `role="tab"` / `aria-selected`. Glavna navigacija ga jednostavno ne koristi.

### 1.2 181 od 184 klikabilnih ne-dugmadi bez `role` i `tabindex` — `BLOKIRA`

| Fajl | `<div>/<span>/<li>/<td>` sa `onclick` | Ima `role` + `tabindex` |
|---|---|---|
| `index.html` | 121 | **0** |
| `static/vindex.js` | 63 | 3 |

U celom `index.html` nema **nijednog** `tabindex` atributa niti `role="button"` (0 pojava). Jedine `role` vrednosti su `tablist`/`tab` (`index.html:1147–1157`) i `navigation` (`index.html:4384`).

Mereno u pregledaču nad početnim DOM-om: 561 elemenata sa `onclick`, od toga 124 nisu native kontrole — i **sva 124 nemaju ni `role` ni `tabindex`**.

Primeri (svaki nedostupan tastaturom):

| Lokacija | Kontrola |
|---|---|
| `index.html:222–226` | 5 zvezdica za ocenu (`.feedback-star`, `onclick="feedbackSetRating(n)"`) |
| `index.html:529` | „Pozovite kolegu advokata" (`.vx-foot-row`, `onclick="wl_open()"`) |
| `index.html:544` | Globalna pretraga (`.vx-global-search`, `onclick="cmdkOpen()"`) |
| `index.html:582` | Zvono za obaveštenja (`#notif-bell`) |
| `index.html:1164` | Kartice strategije (`.strat-feature-card`, `onclick="pred_openStrat(...)"`) |
| `index.html:1631` | Kartice agenata (`.agent-card`) |
| `index.html:2857–2860` | Predloženi upiti (`.t-chip`, `onclick="fillQ(...)"`) |
| `index.html:3738` | FAQ akordeon, 6 stavki (`.pomoc-faq-q`) |
| `vindex.js:1307`, `1774` | „Pokušaj ponovo" nakon greške — **oporavak od greške nedostupan tastaturom** |
| `vindex.js:1726` | Redovi inbox-a (`_dashGoToPredmet`) |
| `vindex.js:2526` | Izbor predmeta (`pred_select`) |
| `vindex.js:6242` | Izbor sudske prakse (`_sud_select`) |
| `vindex.js:8797` | Grupe Za/Protiv (razvijanje/skupljanje) |
| `vindex.js:11546` | Stavke obaveštenja (`notif_click`) |
| `vindex.js:14158` | Ćelije kalendara (`kalDayClick`) |
| `vindex.js:15614` | Izbor šablona dokumenta (`docTplIzaberi`) |
| `vindex.js:21548` | Uklanjanje otpremljenog fajla (`siRemoveFile`) |
| `vindex.js:23291` | Pokretanje workflow-a (`workflow_pokreni`) |

### 1.3 Enter/Space rade — ali samo za 4 elementa — `SITNO`

`vindex.js:483–489` sadrži ispravan generički rukovalac:

```js
483: document.addEventListener('keydown', function(e) {
484:   if (e.key !== 'Enter' && e.key !== ' ') return;
485:   var el = e.target.closest && e.target.closest('[role="button"][tabindex]');
486:   if (!el) return;
487:   e.preventDefault();
488:   el.click();
489: });
```

Mehanizam je dobar, ali selektor `[role="button"][tabindex]` u celoj aplikaciji pogađa samo 4 elementa: `vindex.js:1494`, `1550` (uslovno), `1649`, `1654`.

### 1.4 Nijedan modal nema zamku fokusa — `BLOKIRA`

Pretraga celog `vindex.js`: `key === 'Tab'` → 0, `keyCode === 9` → 0, `firstFocusable` → 0, `activeElement` → 0, `lastFocused`/`previouslyFocused`/`returnFocus` → 0. Takođe `role="dialog"` → 0 i `aria-modal` → 0 u oba fajla.

| Modal | Otvaranje | Fokus na otvaranju | Zamka fokusa | Vraćanje fokusa | Escape |
|---|---|---|---|---|---|
| `auth-modal` | `vindex.js:421` | NE | NE | NE | NE |
| `wl-overlay` (rani pristup) | `vindex.js:431` | DA (`:435`) | NE | NE | DA (`:477`) |
| `crm-overlay` (klijent) | `vindex.js:4839` | NE | NE | NE | NE |
| `crm-conflict-overlay` | `vindex.js:4928` | NE | NE | NE | NE |
| `cmdk-overlay` (⌘K) | `vindex.js:13292` | DA (`:13298`) | NE | NE | DA (`:13432`) |
| `intake-tpl-overlay` | `vindex.js:15395` | NE | NE | NE | NE |
| `intake-overlay` (novi predmet) | `vindex.js:20661` | NE | NE | NE | NE |
| `vx-dialog-overlay` (potvrda/unos) | `vindex.js:16534`/`16556` | Samo unos (`:16570`) | NE | NE | NE |

Posledice:
- Fokus „iscuri" iza otvorenog modala na sadržaj ispod — korisnik tastature kuca u nevidljiva polja.
- Fokus se nikad ne vraća na dugme koje je otvorilo modal; posle zatvaranja korisnik je vraćen na početak dokumenta.
- 6 od 8 modala se ne mogu zatvoriti tasterom `Escape`. `vx-dialog-overlay` — zamena za native `confirm()`/`prompt()` — nema Escape (jedini keydown je `Enter`, `vindex.js:16580`).

---

## 2. Vidljiv fokus

### 2.1 `focus-visible` — potvrđeno 0 pojava

```
static/vindex.css   focus-visible: 0     :focus: 26     outline:none/0: 22
index.html          focus-visible: 0     :focus: 0
static/site.css     focus-visible: 3     :focus: 3
```

### 2.2 Podrazumevani prsten fokusa POSTOJI i vidljiv je — nalaz demantovan

Za razliku od pretpostavke, `outline` **nije** globalno ugašen. Nema `*` reseta koji ga uklanja; svih 22 `outline:none` su ciljane na pojedinačne klase. Native kontrole zadržavaju Chromium-ov adaptivni prsten (`outline-style: auto`), koji se sam prilagođava tamnoj podlozi.

**Merenje piksela** (snimak regiona oko kontrole, 6 px oboda, pre i posle fokusa; maksimalna razlika po kanalu 0–255):

| Kontrola | Max razlika kanala | Promenjenih px | Presuda |
|---|---|---|---|
| BUTTON (glasovna komanda) | 224 | 310 | VIDLJIV |
| A „VindexAI" | 254 | 596 | VIDLJIV |
| A „Prijavite se" | 254 | 1112 | VIDLJIV |
| BUTTON „Zatražite rani pristup" | 252 | 1294 | VIDLJIV |
| BUTTON „Već imam nalog" | 252 | 888 | VIDLJIV |
| A „Politika privatnosti" | 152 | 386 | VIDLJIV |
| A „Uslovi korišćenja" | 152 | 340 | VIDLJIV |
| BUTTON (feedback) | 255 | 692 | VIDLJIV |
| *kontrola: isti element sa `outline:2px solid #00d4ff`* | *247* | *424* | *— referenca* |

Podrazumevani prsten daje jednak ili jači vizuelni signal od eksplicitnog cyan prstena. **Za native kontrole indikator fokusa nije problem.**

Stvarni problem je što ga većina kontrola nikad ne dobije, jer nisu fokusabilne (odeljak 1).

### 2.3 Zamenski indikator na poljima pada ispod 3:1 — `OTEŽAVA`

Tamo gde je `outline:none` primenjen, zamena je samo promena `border-color`. WCAG 2.1 kriterijum 1.4.11 (Non-text Contrast) traži ≥ 3:1. Mereno prema `--vx-panel-bg #0d1117`:

| Polje (fajl:linija) | Boja pri fokusu | vs podloga | vs neaktivna ivica | Presuda |
|---|---|---|---|---|
| `.crm-field` `:1084`, `.crm-search` `:1068`, `.kom-input` `:974`, `.intake-field` `:1139` | `rgba(0,212,255,0.28)` | **1,86** | 1,44 | PADA |
| `.tarife-stavka-iznos` `:318`, `.crm-tarifa-input` `:325` | `rgba(0,212,255,0.28)` | **1,86** | 1,44 | PADA |
| `.aic3-textarea` `:6207` | `rgba(0,212,255,0.28)` | **1,86** | 1,44 | PADA |
| `.strat-textarea` `:732` | `rgba(0,212,255,0.30)` | **1,97** | 1,53 | PADA |
| `.rok-datum-inp` `:685`, `.zast-sel`/`.zast-inp` `:703` | `rgba(0,212,255,0.35)` | **2,27** | 1,76 | PADA |
| `#tab-s select` `:655` | `rgba(0,212,255,0.50)` | 3,43 | 2,66 | OK |
| `.vx-input`/`.vx-select`/`.vx-textarea` `:8973` | `rgba(0,212,255,0.55)` + `box-shadow` | 3,92 | 3,22 | OK |

6 od 7 porodica polja gasi vidljiv prsten i menja ga signalom koji je ispod praga. Kanonske `.vx-*` komponente (`:8973`) su ispravne — starije, nemigrirane klase nisu.

### 2.4 Latentno: glavna navigacija gasi outline — `SITNO` (danas), `BLOKIRA` (posle popravke 1.1)

`static/vindex.css:2922` — pravilo za `.t-tab` sadrži `outline: none !important;`. Danas je bez posledica jer element ionako nije fokusabilan. Čim se doda `tabindex` (popravka nalaza 1.1), tabovi će primati fokus **bez ikakvog vidljivog indikatora**, a `!important` će nadjačati svako naknadno pravilo.

---

## 3. Pristupačna imena

### 3.1 Dugmad — nalaz je dobar

Mereno nad početnim DOM-om: 436 `<button>` elemenata, **0 bez pristupačnog imena**. 20 `<a>`, 0 bez imena. 0 `<img>` bez `alt`.

Ovo je stvarna snaga aplikacije — ikonična dugmad dosledno imaju tekst ili `title`.

### 3.2 175 od 203 polja bez programske labele — `OTEŽAVA`

Izmereno: `input`/`select`/`textarea` bez `aria-label`, bez `title`, bez `<label for>` i bez roditeljskog `<label>` = **175 od 203 (86 %)**. Sva se oslanjaju isključivo na `placeholder`.

`placeholder` nije labela: nestaje čim korisnik počne da kuca, čitači ekrana ga nedosledno izgovaraju, a kontrast mu je 2,47:1 (odeljak 5).

Primeri:

```
INPUT#login-email        type=email     placeholder="Email adresa"
INPUT#login-password     type=password  placeholder="Lozinka"
INPUT#reg-name           type=text      placeholder="Ime i prezime"
INPUT#reg-email          type=email     placeholder="Email adresa"
INPUT#reg-password       type=password  placeholder="Lozinka"
INPUT#reg-confirm-password type=password placeholder="Potvrdi lozinku"
INPUT#forgot-email       type=email     placeholder="Email adresa"
INPUT#reset-password     type=password  placeholder="Nova lozinka (min. 8 karaktera)"
INPUT#reset-password2    type=password  placeholder="Potvrdite novu lozinku"
TEXTAREA#feedback-opis                  placeholder="Šta ste primetili? ..."
INPUT#uz-klijent-ime     type=text      placeholder="Petar Petrović"
INPUT#uz-klijent-adresa  type=text      placeholder="Ul. Knez Mihailova 1, Beograd"
INPUT#uz-klijent-firma   type=text      placeholder="Kompanija d.o.o."
INPUT#uz-advokat-ime     type=text      placeholder="Marko Marković"
INPUT#uz-advokat-adresa  type=text      placeholder="Ul. Terazije 10, Beograd"
```

Kod polja sa primerom vrednosti (`Petar Petrović`, `Ul. Terazije 10`) problem je dvostruk — korisnik čitača ekrana čuje ime izmišljene osobe umesto naziva polja.

### 3.3 Dinamička stanja se ne objavljuju — `OTEŽAVA`

Potvrđeno prebrojavanjem u oba fajla:

| Atribut | `vindex.js` | `index.html` |
|---|---|---|
| `aria-pressed` | 0 | 0 |
| `aria-expanded` | 0 | 0 |
| `aria-current` | 0 | 0 |
| `aria-selected` | 2 | 4 |
| `aria-label` | 4 | 8 |
| `aria-describedby` | 0 | 0 |

Konkretne posledice:
- **Aktivan tab se ne objavljuje.** `.t-tab.active` je isključivo vizuelno stanje (`vindex.css`), bez `aria-selected`/`aria-current`. Korisnik čitača ekrana ne zna gde se nalazi.
- **Akordeoni ne objavljuju otvoreno/zatvoreno.** `index.html:3738` (6 FAQ stavki), `vindex.js:8797` (grupe Za/Protiv), `vindex.js:5950` (`scToggle`) — nijedan nema `aria-expanded`.
- 4 pojave `aria-selected` u `index.html:1148–1157` odnose se na `.vx-phase-tab` — jedinu ispravno označenu komponentu.

---

## 4. Stanja

### 4.1 Stanje učitavanja — dobro, bez nalaza

Sve četiri duge radnje imaju vidljivo stanje učitavanja i onemogućeno dugme:

| Radnja | Dokaz |
|---|---|
| AI upit / analiza / nacrt | `vindex.js:7580–7582` — `execBtn.disabled = true`, `'Vindex AI pretražuje bazu...'` / `'Generišem nacrt...'` |
| Otpremanje dokumenta | `vindex.js:8892–8899`, `index.html:2938` — `<span class="upload-spinner">Otpremanje i obrada dokumenta...` |
| Analiza dokumenta | `vindex.js:8973` — `'Analiziram dokument...'`; `vindex.js:9219` — `'Forenzička analiza u toku... (30-60s)'` |
| Pretraga prakse | `vindex.js:8468`, `8509` — `praksa_show_state('loading')`, `'Učitavam…'` |
| Strategija (6 modula) | `vindex.js:3760–3763` — `'Analiziram (6 modula)...'` + skeleton |
| Brzi AI upit | `vindex.js:10632` — `'Istražujem...'` + rotirajuće faze (`vindex.js:3597–3607`) |

Postoji i generička `.vx-skeleton` shimmer animacija u CSS-u.

### 4.2 143 tiha neuspeha — `OTEŽAVA`

| Tip | Broj |
|---|---|
| Prazan `catch (e) {}` | 72 |
| Prazan `.catch(function(){})` | 64 |
| `catch` sa samo `console.warn` | 7 |
| **Ukupno bez ikakve poruke korisniku** | **143** |

Najozbiljniji, jer je unutar duge radnje:

```
vindex.js:21137   _intakeRunEkstrakcija() — poziv /api/dokument/analiza po fajlu
                  unutar Promise.all, catch (e) {} prazan.
                  Ako pojedinačni fajl padne, njegovi nalazi se tiho izostave.
                  Korisnik vidi uspešno završenu ekstrakciju sa nepotpunim podacima
                  i nema nikakav signal da je fajl preskočen.
```

Ostali primeri: `vindex.js:8521` (`praksa_load_more` — „Učitaj još" tiho padne, dugme se samo vrati u normalu), `vindex.js:21038` (pretraga klijenta u intake-u), `vindex.js:7391` (satnica), `vindex.js:7477` (tarifa), `156`, `170`, `184`, `8261`, `9962`, `11024`, `11326`, `11338`, `11492`, `11737`, `13507`, `13573`, `13787`, `15081`, `15226`, `15343`, `15507`, `20857`, `22088`, `22456`, `22538`, `22643`.

Samo u konzoli: `vindex.js:338` (krediti), `993` (`saveTurn`), `1016` (`loadHistory`), `4119` (API ključevi), `4335` (playbook), `16523` (service worker), `19021` (MI).

### 4.3 Stanje greške — uglavnom dobro, uz curenje tehničkih detalja — `SITNO`

Ključni tokovi koriste `_friendlyErr()` (`vindex.js:546–555`) koji nikad ne prosleđuje `err.message` ni `[object Object]`. Poruke su na srpskom i razumljive, npr.:

```
vindex.js:7684  502/503 → 'Server trenutno nije dostupan. Zahtev je možda već obrađen —
                 proverite stanje pre nego što pokušate ponovo, da ne biste bili naplaćeni dvaput.'
vindex.js:7700  429    → 'Previše zahteva u kratkom vremenskom periodu. Sačekajte koji sekund...'
vindex.js:8937  413    → 'Fajl je preko 25MB. Probajte manji.'
vindex.js:8983  404    → 'Sesija je istekla. Ponovo otpremite dokument.'
```

Odstupanja:

| Lokacija | Tekst | Problem |
|---|---|---|
| `vindex.js:16390` | `'Greška: ' + escHtml(String(e))` | Prikazuje sirov `String(e)` — npr. `TypeError: Cannot read properties of undefined` |
| `vindex.js:7724` | `'Server nije vratio odgovor. HTTP ' + r.status + '. Proverite konzolu (F12)...'` | Upućuje advokata na DevTools |
| `vindex.js:8942`, `20085`, `3802`, `8482`, `10649` | `'Greška servera (' + r.status + ')'` | Sirov HTTP broj u poruci |
| `vindex.js:13878` | `alert('SEF log (poslednih N):\n\n' + txt)` | Dugačak tehnički log kroz native `alert()` |

Native `alert()` se koristi 9 puta (`vindex.js:4725`, `4879`, `4920`, `5008`, `9448`, `13878`, `20799`) — nijedan u četiri glavna toka.

### 4.4 Isključeno stanje — vizuelno da, objašnjenje ne — `OTEŽAVA`

Vizuelni stil postoji: `vindex.css:8858` — `.vx-btn:disabled { opacity: 0.40; cursor: not-allowed; }`, slično na `:736`, `:766`, `:870`, `:1120`, `:1190`, `:1385`, `:4600`, `:5562`, `:6225`.

Ali **zašto** je kontrola isključena nigde se ne saopštava:
- Pretraga `\.disabled\s*=\s*true[^;]*;[^}]*title` u celom `vindex.js` → **0 pogodaka**. Nijedno od 86 mesta koja postavljaju `disabled = true` ne postavlja istovremeno `title`.
- `index.html:4008` — glavno dugme `#exec-btn` nema `title` atribut.

Uz `opacity: 0.40`, tekst dugmeta koji je već na 4,09:1 pada na oko **1,6:1** — praktično nečitljiv. Korisnik vidi sivo dugme, ne zna zašto, i ne može da pročita šta na njemu piše.

### 4.5 Prazno stanje — postoji, ali je nečitljivo — `OTEŽAVA`

Prazna stanja su dosledno implementirana i dobro sročena:

```
vindex.js:9348   'Nisu pronađeni rokovi u dokumentu.'
vindex.js:11934  'Nisu pronađeni konflikti između odabranih dokumenata.'
vindex.js:13368  'Nema rezultata.'
vindex.js:4548   vxGridEmpty('crm-lista-empty','users','Nemate klijenata','Dodajte prvog klijenta da počnete.')
vindex.js:4707   'Nema predmeta.'   :4744 'Nema aktivnosti.'   :4758 'Nema dokumenata.'
index.html:1923  'Nema rezultata za zadate filtere.'
```

Problem je kontrast baš tih poruka:

| Klasa (fajl:linija) | Boja | Odnos | Presuda |
|---|---|---|---|
| `.rokovi-empty` `vindex.css:679` | `rgba(255,255,255,0.32)` | **2,87:1** | PADA |
| `.pck-loading` `vindex.css:811` | `rgba(255,255,255,.28)` | **2,47:1** | PADA |
| `.t-tab-pro.locked` `vindex.css:179` | `rgba(255,255,255,0.22)` | **1,98:1** | PADA |

Stanje praznine i stanje učitavanja su upravo trenuci kada korisnik najviše traži objašnjenje — a ispisani su najsvetlijim sivim tonom u sistemu.

---

## 5. Kontrast

### Metod

Sve `color:` deklaracije u `static/vindex.css` parsirane su programski, `rgba` vrednosti alfa-kompozitovane preko stvarne podloge, odnos izračunat po WCAG 2.1 formuli (relativna luminancija sa sRGB linearizacijom). Pravila unutar `body.light-theme` mere se prema svetlim podlogama (`#f0f4f8`, `#ffffff`), ostala prema tamnim (`#0a1220`, `#0d1117`). Svetla tema je dostupna korisniku — prekidač na `vindex.js:19903`, trajno pamćenje na `:19912`.

### Ukupan rezultat

| Tema | Podloge | Deklaracija | Pada < 4,5:1 | Udeo |
|---|---|---|---|---|
| Tamna | `#0a1220`, `#0d1117` | 1224 | **340** | **27,8 %** |
| Svetla | `#f0f4f8`, `#ffffff` | 233 | **113** | **48,5 %** |

*Napomena o tačnosti:* skener ne uzima u obzir elemente koji imaju sopstvenu pozadinu. Ručnom proverom potvrđeni su lažni pozitivi — npr. `.podnesak-preview-pdf` (`vindex.css:210`) ima `background:#00d4ff; color:#010308`, što je zapravo 10,69:1. Stvarni broj padova je nešto niži od navedenog; svi pojedinačni nalazi u tabelama ispod su ručno provereni.

### Tokeni sistema — izmereno

| Token | Vrednost | `#010308` | `#0a1220` | `#0d1117` | Presuda |
|---|---|---|---|---|---|
| `--tx-1` | `rgba(255,255,255,0.88)` | 15,74 | 14,53 | 14,66 | AAA |
| `--tx-2` | `rgba(255,255,255,0.52)` | 5,67 | 5,64 | 5,67 | AA |
| **`--tx-3`** | `rgba(255,255,255,0.28)` | **2,31** | **2,47** | **2,47** | **PADA** |
| **`--tx-4`** | `rgba(255,255,255,0.14)` | **1,37** | **1,48** | **1,48** | **PADA** |
| `--vx-text-primary` | `rgba(255,255,255,0.92)` | 17,28 | 15,87 | 16,01 | AAA |
| `--vx-text-secondary` | `rgba(255,255,255,0.55)` | 6,26 | 6,18 | 6,22 | AA |
| `--tx-blue` / `--vx-accent` | `#00d4ff` | 11,65 | 10,59 | 10,69 | AAA |
| `--gold` | `#c9a84c` | 9,03 | 8,20 | 8,28 | AAA |
| `--vx-success` | `#4ade80` | 11,84 | 10,76 | 10,86 | AAA |
| `--vx-danger` | `#f87171` | 7,46 | 6,78 | 6,84 | AA |
| `--vx-warning` | `#f0b429` | 11,07 | 10,06 | 10,15 | AAA |
| `--danger` | `#ef4444` | 5,48 | 4,98 | 5,03 | AA (4,39 na `--s2` — pada) |
| **`--vx-accent-dim`** | `rgba(0,212,255,0.55)` | **3,92** | **3,92** | **3,92** | **PADA za tekst** (OK za ivicu) |

Nalaz iz zadatka o `--tx-3` je **potvrđen**: izmereno 2,47:1 na `#0a1220` (zadatak navodi 2,44:1 — razlika potiče od izbora podloge; na `#010308` je 2,31:1). Token je i dalje u upotrebi na **23 mesta**, `--tx-4` na **16 mesta**.

### Najčešće boje koje padaju — tamna tema

| Boja | Broj | Odnos | Prvi selektor (fajl:linija) |
|---|---|---|---|
| `rgba(255,255,255,0.4)` | 31 | 3,82 | `.resp-odgovor .resp-section-lbl` `:12` |
| `rgba(255,255,255,0.3)` | 30 | 2,67 | `.pg-score-nepoznato` `:56` |
| `rgba(255,255,255,0.35)` | 28 | 3,20 | `.pg-group-lbl-nepoznato` `:65` |
| `rgba(255,255,255,0.28)` | 28 | 2,47 | `.pg-decision-meta` `:69` |
| `var(--tx-3)` | 23 | 2,47 | `.cyr-toggle-lbl` `:3238` |
| `var(--tx-4)` | 16 | 1,48 | `.vx-search-kbd` `:3053` |
| `rgba(255,255,255,0.38)` | 13 | 3,56 | `.resp-disclaimer-box .disc-text` `:298` |
| `rgba(255,255,255,0.42)` | 12 | 4,09 | `.resp-disclaimer-box` `:112` |
| `rgba(255,255,255,0.25)` | 11 | 2,21 | `.manual-compare-inputs span` `:895` |
| `rgba(255,255,255,0.18)` | 10 | 1,71 | `.ratio-loading` `:42` |
| `rgba(255,255,255,0.22)` | 10 | 1,98 | `.t-tab-pro.locked` `:179` |
| `rgba(255,255,255,0.2)` | 6 | 1,84 | `.chat-privacy-note` `:624` |
| `rgba(0,212,255,0.35)` | 6 | 2,29 | `.pred-tl-hint` `:839` |
| `rgba(255,255,255,0.32)` | 4 | 2,87 | `.rokovi-empty` `:679` |
| `#334155` | 3 | 1,83 | `.cc-intel-sec-lbl` `:8129` |
| `#64748b` | 3 | 3,98 | `.cc-ni-opis` `:8157` |

Posebno vredi istaći, jer nose pravni sadržaj:
- `.resp-disclaimer-box` (`:112`) i `.disc-text` (`:298`) — **pravno odricanje odgovornosti na 4,09:1 i 3,56:1**
- `.chat-privacy-note` (`:624`) — **obaveštenje o privatnosti na 1,84:1**
- `.ratio-loading` (`:42`) — 1,71:1
- `.cyr-toggle-lbl` (`:3238`) — labela prekidača ćirilica/latinica na 2,47:1
- `.vx-search-kbd` (`:3053`) — prikaz tastaturne prečice na 1,48:1

### Najčešće boje koje padaju — svetla tema (48,5 %)

| Boja | Broj | Odnos | Prvi selektor (fajl:linija) |
|---|---|---|---|
| `rgba(0,0,0,0.50)` | 7 | 3,98 | `body.light-theme .t-tab` `:6446` |
| `rgba(0,0,0,0.45)` | 7 | 3,35 | `body.light-theme .kc-row-sub` `:6462` |
| `rgba(0,0,0,0.38)` | 6 | 2,68 | `body.light-theme .kc-row-datum` `:6463` |
| `rgba(10,18,32,0.45)` | 6 | 3,03 | `body.light-theme .t-title` `:6613` |
| `rgba(10,18,32,0.35)` | 6 | 2,27 | `body.light-theme #dok-preview-empty` `:6667` |
| `rgba(10,18,32,0.38)` | 5 | 2,47 | `body.light-theme #dok-preview-meta` `:6659` |
| `rgba(10,18,32,0.55)` | 5 | 4,16 | `body.light-theme #doctpl-predmet-row label` `:6696` |
| `rgba(10,18,32,0.40)` | 4 | 2,62 | `body.light-theme .vx-sidebar-help` `:6605` |
| `rgba(10,18,32,0.30)` | 3 | 1,99 | `body.light-theme .vx-nav-group-lbl` `:6599` |
| `rgba(0,153,187,0.60)` | 2 | 2,05 | `body.light-theme .hub-tool-cta` `:6786` |
| `rgba(0,153,187,0.70)` | 3 | 2,32 | `body.light-theme .kc-sphere-lbl` `:6764` |
| `#ef4444` | 2 | 3,76 | `body.light-theme .kc-kpi-n.warn` `:6872` |

Svetla tema je znatno lošija od tamne — skoro polovina njenog teksta pada. Naslov ekrana (`.t-title`, 3,03:1) i naziv navigacione grupe (`.vx-nav-group-lbl`, 1,99:1) su ispod praga.

### Pozitivno

`vindex.css:6345–6351` sadrži namenski blok „Accessibility: minimum font sizes" koji podiže veličine na 12–14 px. Postoje 2 `prefers-reduced-motion` pravila. `prefers-contrast` — 0 pravila.

---

## 6. Čitač ekrana — semantika

### 6.1 `aria-live` = 0 — `BLOKIRA`

Potvrđeno statički (`vindex.js` 0, `index.html` 0) i mereno u pregledaču (`document.querySelectorAll('[aria-live]').length === 0`).

Istovremeno, `showToast()` (`vindex.js:502–518`) poziva se **353 puta**. Postoji i `showUserError()` (`vindex.js:528`).

Znači: **nijedno od 353 obaveštenja — potvrde, greške, upozorenja o kreditima, rezultati AI analize — nije izgovoreno korisniku čitača ekrana.** Poruka se pojavi i nestane bez traga. To uključuje i kritične poruke poput one o dvostrukoj naplati (`vindex.js:7684`).

Isto važi za rezultat AI analize koji se ispisuje efektom kucanja (`vindex.js:7768–7801`) u kontejner bez `aria-live` — sadržaj se pojavi neobjavljen.

### 6.2 Struktura naslova je narušena — `OTEŽAVA`

Redosled naslova u dokumentu, izmeren u pregledaču:

```
1. H2  "Vindex Intelligence."
2. H1  ""                        <- prazan (#portal-pred-naziv, index.html:4077)
3. H2  "Pridružite se Vindex AI"
4. H1  "VindexAI"                <- index.html:4178
5. H3  "Podešavanja kancelarije"
6. H4  "Tarife i naknade"
7. H2  "Uporedna analiza presuda"
```

Problemi:
- **Dva `<h1>`** na stranici, od kojih je jedan prazan.
- Dokument **počinje sa `<h2>`**, pre bilo kog `<h1>`.
- Za ceo aplikacijski deo (predmeti, klijenti, rokovi, dokumenti…) **ne postoji `<h1>`**. Jedini neprazan `<h1>` je logo `VindexAI`.
- Naslovi panela su vizuelno stilizovani (`.t-title`, `.vx-panel-hd`) umesto da budu semantički elementi, pa navigacija po naslovima ne radi.

### 6.3 Orijentiri — delimično — `SITNO`

Izmereno: 6 orijentira u DOM-u (`<nav>` ×2, `<main>`, `<header>`, `<footer>`, `<aside>`, `role="navigation"` na `index.html:4384`).

Osnova postoji. Nedostaje:
- **Nema „preskoči na sadržaj" veze** (pretraga `skip-link`/`skip to` → 0 pogodaka). Uz 15 stavki navigacije, korisnik tastature mora kroz sve pri svakom učitavanju — kada tabovi postanu fokusabilni.
- Glavna navigacija (`index.html:444–511`) nije unutar `<nav>` niti ima `role="tablist"`.

---

## Prilog A — Kontrole bez pristupačnog imena

**Dugmad i veze: 0 nalaza.** 436 `<button>` i 20 `<a>` — sve imaju ime. 0 `<img>` bez `alt`.

**Polja za unos: 175 od 203 (86 %)** bez `aria-label`, `title`, `<label for>` ili roditeljskog `<label>` — oslanjaju se samo na `placeholder`. Spisak sa uzorkom u odeljku 3.2.

**Klikabilni ne-native elementi: 124 od 124** u početnom DOM-u nemaju ni `role` ni `tabindex`, pa za pomoćnu tehnologiju nisu kontrole uopšte — ni ime, ni uloga, ni stanje. Spisak u odeljku 1.2.

## Prilog B — Zbirna tabela nalaza

| # | Nalaz | Lokacija | Težina |
|---|---|---|---|
| A1 | Glavna navigacija (15 tabova) nedostupna tastaturom | `index.html:444–511` | **BLOKIRA** |
| A2 | 181/184 klikabilnih ne-dugmadi bez `role`+`tabindex`; `index.html` ima 0 `tabindex` | `index.html`, `vindex.js` | **BLOKIRA** |
| A3 | Nijedan modal nema zamku fokusa ni vraćanje fokusa | 8 modala, tabela 1.4 | **BLOKIRA** |
| A4 | 6/8 modala se ne zatvara tasterom Escape | tabela 1.4 | OTEŽAVA |
| A5 | Enter/Space rukovalac pokriva samo 4 elementa | `vindex.js:483–489` | SITNO |
| B1 | `focus-visible` = 0 pojava | `static/vindex.css` | SITNO |
| B2 | 6/7 porodica polja gasi outline, zamena < 3:1 (min. 1,86:1) | tabela 2.3 | OTEŽAVA |
| B3 | `.t-tab` ima `outline:none !important` (latentno) | `vindex.css:2922` | SITNO → BLOKIRA posle A1 |
| C1 | 175/203 polja bez programske labele | Prilog A | OTEŽAVA |
| C2 | 0 `aria-pressed` / `aria-expanded` / `aria-current` | oba fajla | OTEŽAVA |
| C3 | Aktivan tab bez `aria-selected`/`aria-current` | `index.html:444–511` | OTEŽAVA |
| D1 | 143 tiha neuspeha (72+64 prazna `catch` + 7 console-only) | odeljak 4.2 | OTEŽAVA |
| D2 | Ekstrakcija dokumenata tiho preskače pale fajlove | `vindex.js:21137` | OTEŽAVA |
| D3 | Isključena dugmad bez objašnjenja (`title` = 0/86) | odeljak 4.4 | OTEŽAVA |
| D4 | Sirov `String(e)` prikazan korisniku | `vindex.js:16390` | SITNO |
| D5 | HTTP status i „konzola (F12)" u porukama | `vindex.js:7724`, `8942`, `20085` | SITNO |
| E1 | `--tx-3` = 2,47:1, u upotrebi 23× | `vindex.css` | OTEŽAVA |
| E2 | `--tx-4` = 1,48:1, u upotrebi 16× | `vindex.css` | OTEŽAVA |
| E3 | 27,8 % tekstualnih deklaracija pada (tamna tema) | odeljak 5 | OTEŽAVA |
| E4 | 48,5 % tekstualnih deklaracija pada (svetla tema) | odeljak 5 | OTEŽAVA |
| E5 | Pravno odricanje 4,09/3,56:1; obaveštenje o privatnosti 1,84:1 | `vindex.css:112,298,624` | OTEŽAVA |
| E6 | Prazna stanja i stanja učitavanja na 2,47–2,87:1 | `vindex.css:679,811` | OTEŽAVA |
| F1 | `aria-live` = 0; svih 353 obaveštenja neizgovoreno | `vindex.js:502–518` | **BLOKIRA** |
| F2 | Dva `<h1>` (jedan prazan), dokument počinje sa `<h2>` | `index.html:4077,4178` | OTEŽAVA |
| F3 | Nema „preskoči na sadržaj" veze | `index.html` | SITNO |

---

## Šta nije bilo moguće proveriti

- **Ekrani iza prijave nisu mereni u radnom stanju.** Nije korišćen nijedan produkcioni kredencijal. DOM je analiziran u odjavljenom stanju, gde je aplikacijska ljuska prisutna ali skrivena. Nalazi o `.t-tab` potvrđeni su i programski (`element.tabIndex === -1` nakon otkrivanja elemenata čistim CSS-om, bez prijave) i statički u izvoru.
- **Sadržaj koji se generiše tek posle poziva API-ja** (rezultati AI analize, tabele predmeta, kalendar) nije mogao biti fokus-testiran uživo. Nalazi za te delove izvedeni su iz izvornog koda `vindex.js`, uz navedene linije.
- **Nije testirano stvarnim čitačem ekrana** (NVDA/JAWS/VoiceOver). Nalazi u odeljku 6 zasnovani su na odsustvu ARIA atributa, što je nužan ali ne i dovoljan uslov — stvarno ponašanje može biti i gore od opisanog.
- **Skener kontrasta ne modeluje elemente sa sopstvenom pozadinom**, zbog čega su zbirni procenti (27,8 % / 48,5 %) blago precenjeni. Svi pojedinačno navedeni nalazi ručno su provereni u izvoru.
