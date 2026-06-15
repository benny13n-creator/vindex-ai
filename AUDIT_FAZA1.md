# AUDIT FAZA 1 — IA Restructure

> Datum audita: 2026-06-15
> Fajl koji je analiziran: `index.html` (11 695 linija, monolitni HTML/CSS/JS)

---

## 1. Mapa trenutnih tabova

| # | Label (ono što vidi korisnik) | HTML element ID | Klasa / onclick | Panel ID | Poziva pri switchu |
|---|-------------------------------|-----------------|-----------------|----------|--------------------|
| 1 | Centar | *(nema id na btn)* | `onclick="setTab(this,'h')"` | `tab-h` | `dash_load()` |
| 2 | Predmeti | *(nema id na btn)* | `onclick="setTab(this,'p')"` | `tab-p` | `pred_load()` |
| 3 | Klijenti | *(nema id na btn)* | `onclick="setTab(this,'k')"` | `tab-k` | `ucitajKlijente()` |
| 4 | Istraživanje | *(nema id na btn)* | `onclick="setTab(this,'q')"` | `tab-q` | *(nema posebnog load-a)* |
| 5 | Analiza | *(nema id na btn)* | `onclick="setTab(this,'a')"` | `tab-a` | *(nema posebnog load-a)* |
| 6 | Nacrti | `tab-btn-n` | `onclick="setTab(this,'n')"` | `tab-n` | `updatePodnesakHint()`, `ucitajPlaybookStatus()` |
| 7 | Sudska praksa | *(nema id na btn)* | `onclick="setTab(this,'s')"` | `tab-s` | `praksa_load_initial()` |
| 8 | Strategija | `tab-btn-t` | `onclick="setTab(this,'t')"` | `tab-t` | *(nema posebnog load-a)* |
| 9 | Web3 | `tab-btn-w` | `onclick="setTab(this,'w')"` | `tab-w` | `web3InitTab()` |
| 10 | Kalendar | `tab-btn-kal` | `onclick="setTab(this,'kal')"` | `tab-kal` | `kalendarLoad()` |
| 11 | Intelligence | `tab-btn-pi` | `onclick="setTab(this,'pi')"` | `tab-pi` | `piLoad()` |

**Napomena uz tabelu:**
- Tab "Intelligence" (pi) je podrazumevano skriven: `style="display:none"` na samom dugmetu. Prikazuje se dinamički iz JS-a (`tab-btn-pi` se unhide-uje kad korisnik ima admin flag).
- Nacrti, Strategija i Web3 imaju `t-tab-pro` klasu i PRO gate u `setTab()`.
- Istraživanje (`q`) je default aktivan tab pri prvom učitavanju (deklarisan `active` u HTML-u, `var activeTab = 'q'` u JS-u).

---

## 2. Klasifikacija

### PRIMARNA NAV (ostaje top-level)

| Tab | Ključ | Obrazloženje |
|-----|-------|--------------|
| Centar | `h` | Dashboard — ulazna tačka, pregled stanja kancelarije |
| Predmeti | `p` | CRM predmeta — srce aplikacije, sadrži sub-panel (pred-detail) |
| Klijenti | `k` | CRM klijenata |
| Kalendar | `kal` | Rokovi i ročišta — vezani za predmete, ali su primarni ekran |

### RADNI ALATI HUB (kandidati za novi hub tab)

| Tab | Ključ | Tip | PRO? |
|-----|-------|-----|------|
| Istraživanje | `q` | Ad-hoc RAG pretraga zakona | Ne |
| Sudska praksa | `s` | Ad-hoc pretraga VKS/VS odluka | Ne |
| Nacrti | `n` | Standalone generator podnesaka/ugovora | Da (PRO) |
| Strategija | `t` | Red Team / Litigation Simulator / Procena ishoda | Da (PRO) |
| Web3 | `w` | ZDI/MiCA Compliance alati | Da (PRO) |

Svi ovi tabovi su **standalone, ad-hoc alati** — ne zahtevaju izabrani predmet, nemaju kontekstualni link sa `pred-detail`. Logički ih grupiše ista stvar: unesi tekst/pitanje, dobij AI odgovor.

### PREDMET KONTEKSTUALNO (ne diraj — vec postoje unutar pred-detail)

Ovi delovi su `section` unutar `#pred-detail` (skriven `<div>` koji se prikazuje klikomna predmet u tab-p):

| Sekcija | Element ID | Opis |
|---------|------------|------|
| Pravna procena | `pred-procena-result` | AI analiza predmeta (upload doc, cinjenice) |
| Copilot | `pred-copilot-messages` | Agent chat vezan za predmet |
| Naplata | `pred-billing-wrap` | Tajmer, AKS tarifa, faktura |
| Hronologija dokaza | `pred-hronologija-list` | Dokazni timeline |
| Beleške | `pred-beleske-list` | Slobodne beleske na predmetu |
| Dokumenti | `pred-upload-zone` | Upload PDF/DOCX za predmet |
| Komentari tima | `pred-kom-lista` | Tim collaboration |

**Ovo su contextual tools — ne treba ih dirati.** Oni su deo Predmeti taba, ne zasebni tabovi.

### OSTALO (posebna kategorija)

| Tab | Ključ | Status | Napomena |
|-----|-------|--------|----------|
| Analiza | `a` | Ambivalentno — RADNI ALAT | Upload ugovora/presude za standalone analizu. Nema veze sa konkretnim predmetom. Treba ga svrstati u RADNI ALATI HUB. |
| Intelligence | `pi` | ADMIN ONLY | Skriven za obicne korisnike. Ostaje kao skriveni admin tab — ne ulazi u restructure. |

---

## 3. Tab switching mehanizam

### Centralna funkcija: `setTab(el, t)`

Definisana na liniji 4185. Potpuna logika:

```
function setTab(el, t) {
  // 1. PRO gate za tabove 'n', 't', 'w' — otvara ProUpgradeModal i izlazi ako nije PRO
  // 2. Uklanja klasu 'active' sa svih .t-tab elemenata
  // 3. Dodaje 'active' na kliknuti element
  // 4. Iterira kroz sve poznate tab ID-eve: ['h','q','n','a','s','p','t','k','w','kal','pi']
  //    i sakriva sve (display:none), pa prikazuje ciljni (display:block)
  // 5. Setuje globalnu var activeTab = t
  // 6. Kontrolise vidljivost t-exec-row i t-credits-row za tabove koji nemaju input
  // 7. Poziva odgovarajucu load funkciju za tab
  // 8. Poziva piTrack() za analytics
  // 9. Resetuje podnesak-preview, mic, resp
}
```

### Kako se cuva active state

- **CSS**: `.t-tab.active` klasa na dugmetu u navigaciji
- **JS varijabla**: globalna `var activeTab = 'q'` (inicijalna vrednost)
- **Nema localStorage** za aktivni tab — potvrdjeno grep-om. `localStorage` se koristi samo za `vindex_session_id`, `vindex_firma` i `vx_notif_read`.

### URL/hash i deep linking

- **Nema URL deep linking-a za tabove.** Jedina upotreba `window.location.hash` je za Supabase recovery token (linija 7257): `if (hash.indexOf('type=recovery') !== -1)`.
- Nema `?tab=` query parametra. Nema `#tab=` hash routing-a.
- Nema History API (`pushState` / `replaceState`).

### Default tab logika pri load-u

Dva scenarija:

| Scenarij | Koji tab se prikazuje |
|----------|-----------------------|
| Korisnik je ulogovan (`SIGNED_IN` / `INITIAL_SESSION`) | `setTab(hTab, 'h')` — Centar |
| Korisnik nije ulogovan / odjavio se | `setTab(qTab, 'q')` — Istraživanje |

Logika je u `sb.auth.onAuthStateChange` callback-u (linije 3506–3516).

### Tabovi registrovani u setTab iterator-u

Hard-kodovana lista na liniji 4193:
```js
['h','q','n','a','s','p','t','k','w','kal','pi']
```
Svaki novi tab mora biti dodat u ovu listu.

---

## 4. "Radni alati" hub — plan

### Trenutno stanje

**Hub ne postoji.** Grep za `radni-alati`, `alati`, `hub`, `tools` vraca 0 pogodaka relevantnih za navigacionu komponentu. Nema hub stranice, nema wrapper panela koji grupiše alate.

Trenutno je navigacija ravna lista od 11 tabova, prikazana horizontalnim scrollable strip-om (`.t-tabs` unutar `.t-bar`).

### Konkretan plan kreiranja hub-a

Pristup: **novi tab "Alati" koji renderuje hub stranicu sa linkovima ka postojecim tabovima** (q, a, n, s, t, w). Tabovi ostaju kao zasebni paneli — hub je samo vizuelna landing page za grupu.

**Fajl: `index.html`**

**Korak 1 — Dodati nav dugme** (u blok `.t-tabs`, posle Klijenti, pre Istraživanje):

```html
<div class="t-tab" id="tab-btn-alati" onclick="setTab(this,'alati')">Alati</div>
```

**Korak 2 — Dodati panel** (posle `<div id="tab-k" ...>` bloka, pre `<div id="tab-n" ...>`):

```html
<div id="tab-alati" style="display:none">
  <!-- Hub grid sa 6 kartica -->
</div>
```

Svaka kartica u hub-u poziva `setTab` direktno ka ciljanom tabu.

**Korak 3 — Registrovanje u setTab iterator** (linija 4193):

```js
['h','q','n','a','s','p','t','k','w','kal','pi','alati']
```

**Korak 4 — Dodati label u lbl map** (linija 4196):

```js
alati: 'Radni alati'
```

**Korak 5 — Tab ne treba posebnu load funkciju** — renderuje se staticki, bez API poziva.

**Korak 6 — Sakriti tab-ove q, a, n, s, t, w iz primarne navigacije** (ili ostaviti za direktan pristup — videti odluku u sekciji 8).

---

## 5. Overlay/Dropdown audit — backdrop-filter problem

### .terminal backdrop-filter status

**PROBLEM POSTOJI i vec je dokumentovan u kodu (linija 7263).**

CSS za `.terminal` (linija 304):
```css
.terminal {
  backdrop-filter: blur(20px);
  overflow: hidden;         /* <-- klipuje sve position:fixed unutar containera */
  position: relative;
  ...
}
```

Efekat: `backdrop-filter` kreira novi **containing block** za `position:fixed` elemente koji su **descendant** od `.terminal`. To znaci da ti fixed elementi:
- nisu pozicionirani relativno prema viewport-u (kao sto bi ocekivali)
- ostaju zarobljeni unutar `.terminal` bounds-a
- bivaju klipovani od `overflow:hidden` na `.terminal`

Isto vazi za `.terminal-wrap` (linija 960):
```css
.terminal-wrap {
  overflow: hidden;   /* dodatni clip */
  ...
}
```

Programeri su vec svesni ovog problema — vidi komentar u kodu (linije 7263-7265) i resenje koje je vec primenjeno.

### Pogođene komponente

#### Komponente koje su VEC ISPRAVNO PRESELJENE na document.body

Ove tri komponente se pri `DOMContentLoaded` (linija 7266-7271) premestaju na `document.body` ako nisu vec tamo:

| Komponenta | ID | Prvobitna lokacija u HTML-u | Status |
|------------|----|-----------------------------|--------|
| Intake overlay (CRM intake wizard) | `intake-overlay` | Unutar `.terminal > tab-p` | Popravljen — premesten na body |
| CRM overlay (klijent forma) | `crm-overlay` | Unutar `.terminal > tab-k` | Popravljen — premesten na body |
| CRM conflict overlay | `crm-conflict-overlay` | Unutar `.terminal > tab-p` | Popravljen — premesten na body |

#### Ročište overlay — VEC NA BODY, ispravno

```html
<!-- Faza 1: Ročište overlay — montiran na body, van .terminal (izbjegava backdrop-filter bug) -->
<div id="rociste-overlay" class="crm-overlay" style="z-index:3100;">
```
Nalazi se na liniji 10997, van `.terminal` — ispravno. Komentar u kodu eksplicitno belezi razlog.

#### Komponente koje su na document.body iz startera (ispravno)

| Komponenta | ID / selektor | Tip | Napomena |
|------------|---------------|-----|----------|
| Auth modal | `#auth-modal` | `position:fixed` (preko .modal-overlay) | Van .terminal, na body — OK |
| Paywall modal | `#paywall-modal` | `position:fixed` | Van .terminal, na body — OK |
| PRO upgrade modal | `#pro-upgrade-modal` | `position:fixed` | Van .terminal, na body — OK |
| Settings modal | `#settings-modal` | `position:fixed` | Van .terminal, na body — OK |
| Toast container | `.toast-container` | `position:fixed` | Van .terminal, na body — OK |
| Mobile menu | `.mobile-menu` | `position:fixed` | Van .terminal, na body — OK |
| Compare bar | `#compare-bar` | `position:fixed` | Van .terminal (linija 10962) — OK |
| Compare modal | `#compare-modal` | `position:fixed` (vx-modal-overlay) | Van .terminal (linija 10974) — OK |

#### Komponenta sa potencijalnim rizikom

| Komponenta | ID | Tip | Rizik |
|------------|----|-----|-------|
| Notif dropdown | `#notif-dropdown` | `position:absolute` | **SREDNJI** — nalazi se unutar `.terminal > .t-bar`. Koristi `position:absolute` (ne fixed), pa backdrop-filter containing block problem ne primenjuje direktno, ali `overflow:hidden` na `.t-bar` ili `.terminal` moze ga klipovati ako premasuje bounds. Videti napomenu ispod. |
| Inline modali generisani JS-om | `document.body.appendChild(modal)` | `position:fixed` (inline style) | **NIZAK** — vec se appenduju direktno na body (linija 6468). |

**Notif dropdown detalj** (linija 2263):
```html
<div id="notif-dropdown" style="display:none; position:absolute; top:100%; right:0; z-index:200; width:min(340px,92vw); max-height:380px; overflow-y:auto; ...">
```
Dropdown je u `.t-bar` div-u koji ima `overflow:hidden`. Ako dropdown premasuje visinu `.t-bar`, bice klipovan. U praksi radi jer se otvara nadole iz nav-trake i `z-index:200` ga postavlja iznad tab sadrzaja, ali pri manjem ekranu moze biti parcijalno klipovan.

### Preporuka za implementaciju novog taba

Kada se doda novi "Alati" hub tab, svi overlay-i koje taj tab moze otvoriti (PRO upgrade modal, bilo kakvi novi slide-in paneli) moraju biti:

1. **Generisani direktno na `document.body`** (kao sto je uradjeno sa intake-overlay i crm-overlay), ILI
2. **Postavljeni u HTML van `.terminal`** (kao sto je uradjeno sa rociste-overlay na liniji 10997).

Alternativa: refaktorisati `.terminal` CSS da ukloni `backdrop-filter` i zameni sa pseudo-elementom koji nema taj efekat — ali to je veca promena i nije preporucena bez vizuelnog testiranja.

---

## 6. Shared state i breaking change rizici

### localStorage — nema tab state-a

Aktivni tab se **ne cuva u localStorage**. Potvrdjeno iscrpnim grep-om. localStorage sadrzi iskljucivo:
- `vindex_session_id` — Supabase chat session ID
- `vindex_firma` — podaci firme (naziv, PIB, adresa)
- `vx_notif_read` — Set procitanih notifikacija

**Rizik: NEMA** — promena tab strukture ne moze pokvariti localStorage.

### Hard-kodovana lista tabova u setTab

Linija 4193 — iterator koji sakriva/prikazuje panele:
```js
['h','q','n','a','s','p','t','k','w','kal','pi']
```
**Rizik: VISOK** — ako se doda novi tab `alati` a ne doda se u ovu listu, panel nece biti sakriven pri siwtch-u na drugi tab. Obavezan update.

### execQuery() — pretpostavlja aktivan tab

Funkcija `execQuery()` (linija 6839+) koristi `activeTab` za odredjivanje:
- Labela na dugmetu (linija 6839)
- Koji endpoint se poziva (linija 6884)
- Koji body se salje (linija 6887)

Mapa endpoints-a ukljucuje kljuceve `q`, `n`, `a`, `s`. Ako korisnik bude na hub tabu `alati` i klikne execute (sto ne bi trebalo da se desi jer `t-exec-row` nece biti vidljiv), dobice `undefined` endpoint.

**Rizik: NIZAK** — `t-exec-row` se vec sakriva za tabove koji nemaju input (linija 4200). Isti uslov treba dodati za `alati`:
```js
(t === 'h' || t === 't' || t === 'k' || t === 'w' || t === 'kal' || t === 'pi' || t === 'alati')
```

### piTrack — analytics po tabu

Linija 6841:
```js
var _trackFeature = {q:'pravno_istrazivanje',n:'drafting',a:'dokument',s:'sudska_praksa'}[activeTab]||activeTab;
```
**Rizik: NIZAK** — fallback je `activeTab` sam po sebi, pa `alati` ce se trackirati kao string `'alati'` sto je prihvatljivo.

### lbl map u setTab

Linija 4196 — mapa label-a za `btn-lbl`:
```js
var lbl = {h:'Kontrolni centar', q:'Pretraži pravnu bazu', ...};
```
Ako `alati` nije u mapi, `btn-lbl` ce biti prazan string. Treba dodati entry.

### Auth redirect — moze pregaziti tab

`onAuthStateChange` uvek preusmeri na `h` tab pri loginu (linija 3509-3510). Ako korisnik bude na hub tabu i desi se auto-refresh sessije, bice preusmeren na Centar. Ovo je postojece ponasanje za sve tabove — ne novi rizik, ali vredi dokumentovati.

### Cross-tab komunikacija

Grep za `postMessage`, `BroadcastChannel`, `cross-tab` ne vraca pogotke. Nema cross-tab browser komunikacije.

### Deep linkovi

Nema `?tab=` ili `#tab=` routing-a. Nema `pushState`. Nema spoljnih linkova koji bi mogli biti slomljeni restrukturisanjem navigacije.

### Konkretni querySelector pozivi koji pretpostavljaju tab strukturu

Vise mesta u kodu koristi querySelector da pronadje tab dugme i pozove setTab na njega:

| Linija | Kod | Kontekst |
|--------|-----|----------|
| 9051-9052 | `querySelector('[onclick*="\'p\'"]')` | Navigacija iz notif dropdown na Predmete |
| 10338-10339 | `querySelector('[onclick*="\'p\'"]')` | Navigacija na Predmete posle CRM akcije |
| 10366 | `querySelector('[onclick*="\'p\'"]')` | Isti — redirect na Predmete |
| 7098 | `if (btn) setTab(btn, t)` | Generic helper — koristi prosledjen `t` |

**Rizik: NIZAK** — ovi selektori traze tab `p` (Predmeti), ne prolaze kroz sve tabove. Dodavanje novog taba `alati` ne utice na njih.

---

## 7. Konkretni plan izmena — fajl po fajl

### index.html — Nav HTML izmene

**Lokacija:** `<div class="t-tabs" id="t-tabs-el">` (linija 2243)

**Promena 1 — Dodati hub dugme** posle tab Klijenti (`k`), pre Istraživanje (`q`). Ovo grupiše alate logicki:

```html
<!-- Nova pozicija: izmedju Klijenti i Istraživanje -->
<div class="t-tab" id="tab-btn-alati" onclick="setTab(this,'alati')">Alati</div>
```

**Promena 2 — Dodati hub panel** (posle `</div>` koji zatvara `tab-k`, pre `<div id="tab-n">`):

```html
<div id="tab-alati" style="display:none">
  <div class="t-guide">
    <div class="t-guide-icon">⚙</div>
    <div class="t-guide-text"><span class="t-guide-bold">Radni alati.</span> AI alati za ad-hoc istraživanje, analizu dokumenata i izradu podnesaka — bez veze sa konkretnim predmetom.</div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:0.65rem;margin-top:0.9rem;">
    <!-- Kartica: Istraživanje -->
    <div class="alati-card" onclick="setTab(document.querySelector('[onclick*=\'setTab\'][onclick*=\'\\\'q\\\'\']'),'q')">
      <div class="alati-card-icon">⚖</div>
      <div class="alati-card-naziv">Istraživanje</div>
      <div class="alati-card-opis">Pretraži zakone RS po pitanju</div>
    </div>
    <!-- Kartica: Analiza dokumenta -->
    <div class="alati-card" onclick="setTab(document.querySelector('[onclick*=\'setTab\'][onclick*=\'\\\'a\\\'\']'),'a')">
      <div class="alati-card-icon">🔍</div>
      <div class="alati-card-naziv">Analiza dokumenta</div>
      <div class="alati-card-opis">Analiziraj ugovor ili presudu</div>
    </div>
    <!-- Kartica: Nacrti (PRO) -->
    <div class="alati-card alati-card-pro" onclick="setTab(document.getElementById('tab-btn-n'),'n')">
      <div class="alati-card-icon">📄</div>
      <div class="alati-card-naziv">Nacrti <span class="pro-badge">PRO</span></div>
      <div class="alati-card-opis">Generiši podnesak ili ugovor</div>
    </div>
    <!-- Kartica: Sudska praksa -->
    <div class="alati-card" onclick="setTab(document.querySelector('[onclick*=\'setTab\'][onclick*=\'\\\'s\\\'\']'),'s')">
      <div class="alati-card-icon">📚</div>
      <div class="alati-card-naziv">Sudska praksa</div>
      <div class="alati-card-opis">VKS i VS odluke</div>
    </div>
    <!-- Kartica: Strategija (PRO) -->
    <div class="alati-card alati-card-pro" onclick="setTab(document.getElementById('tab-btn-t'),'t')">
      <div class="alati-card-icon">⚔️</div>
      <div class="alati-card-naziv">Strategija <span class="pro-badge">PRO</span></div>
      <div class="alati-card-opis">Red Team, Simulator, Procena ishoda</div>
    </div>
    <!-- Kartica: Web3 (PRO) -->
    <div class="alati-card alati-card-pro" onclick="setTab(document.getElementById('tab-btn-w'),'w')">
      <div class="alati-card-icon">₿</div>
      <div class="alati-card-naziv">Web3 <span class="pro-badge">PRO</span></div>
      <div class="alati-card-opis">ZDI / MiCA Compliance</div>
    </div>
  </div>
</div>
```

### index.html — JS izmene

**Promena 3 — Registrovati `alati` u setTab iterator** (linija 4193):

```js
// STARO:
['h','q','n','a','s','p','t','k','w','kal','pi']
// NOVO:
['h','q','n','a','s','p','t','k','w','kal','pi','alati']
```

**Promena 4 — Dodati label u lbl map** (linija 4196):

```js
// Dodati entry:
alati: 'Radni alati'
```

**Promena 5 — Sakriti exec-row za alati tab** (linija 4200):

```js
// STARO:
if (execRow) execRow.style.display = (t === 'h' || t === 't' || t === 'k' || t === 'w' || t === 'kal' || t === 'pi') ? 'none' : '';
// NOVO:
if (execRow) execRow.style.display = (t === 'h' || t === 't' || t === 'k' || t === 'w' || t === 'kal' || t === 'pi' || t === 'alati') ? 'none' : '';
```

Isto za `credRow` direktno ispod (linija 4201).

### index.html — CSS izmene

**Promena 6 — Dodati `.alati-card` stilove** (u `<style>` blok, blizu `.pred-detail` ili `.kc-*` stilova):

```css
.alati-card {
  background: rgba(74,168,255,0.04);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  padding: 1rem 1.1rem;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.alati-card:hover {
  background: rgba(74,168,255,0.09);
  border-color: rgba(74,168,255,0.25);
}
.alati-card-pro { border-color: rgba(201,168,76,0.18); }
.alati-card-pro:hover { border-color: rgba(201,168,76,0.4); background: rgba(201,168,76,0.05); }
.alati-card-icon { font-size: 1.4rem; margin-bottom: 0.4rem; }
.alati-card-naziv { font-size: 0.88rem; font-weight: 700; color: #e2eeff; margin-bottom: 0.18rem; }
.alati-card-opis { font-size: 0.72rem; color: rgba(255,255,255,0.4); line-height: 1.5; }
```

**Odluka o vidljivosti originalnih tabova q, a, s:**
Preporuka je da ostanu vidljivi u navigaciji. Logika: korisnik koji navikne na direktan pristup ne treba da pravi extra klik kroz hub. Hub je discovery layer za nove korisnike — ne zamena za direktan pristup.

Ako se ipak odlucimo za sklanjanje q/a/s iz nav-a (cleaner UX), to je additional promena — nije bloker za fazu 1.

---

## 8. Sažetak

Audit pokazuje **stabilnu, predvidljivu arhitekturu** bez neocekivanih surpriza.

1. **11 tabova, jedan mehanizam**: `setTab(el, t)` kontrolise sve. Hard-kodovana lista tabova na liniji 4193 je jedino mesto koje mora biti azurirano pri dodavanju novog taba.

2. **Hub ne postoji, ali je lako dodati**: Novi tab `alati` sa grid-om kartica koje vode ka postojecim tabovima. Tabovi `q`, `a`, `n`, `s`, `t`, `w` ostaju funkcionalni kao i pre — hub ih samo grupise vizuelno.

3. **Backdrop-filter bug je poznat i vec ima pattern resenja**: `intake-overlay`, `crm-overlay`, `crm-conflict-overlay` se premestaju na body pri DOMContentLoaded; `rociste-overlay` je staticno van `.terminal`. Svaki novi overlay za hub tab mora slediti isti pattern.

4. **Nema URL routing-a, nema localStorage tab state-a, nema cross-tab komunikacije** — restruktura ne moze slomiti ove mehanizme jer ne postoje.

5. **Jedini realni rizici pri implementaciji**: (a) zaboraviti `alati` u iterator listi na liniji 4193, (b) zaboraviti sakriti exec-row za novi tab, (c) ako se doda bilo koji overlay unutar hub tab panela — mora ici na document.body.

6. **Implementacija je 6 tacno definisanih promena** u jednom fajlu (`index.html`) — sve su lokalizovane, bez kaskadnih efekata na postojece tabove.
