# INTERACTION FORENSICS — Vindex AI

Datum: 2026-08-12
Obim: `index.html`, `static/vindex.js`, `api.py` + `routers/*`
Metod: AST analiza (acorn), ne regex — svaki nalaz ima dokaz (fajl:linija)
Status: **AUDIT — nijedan fajl nije menjan osim ovog dokumenta**

---

## 1. Metodologija i njena ograničenja

Praćen je ceo lanac: `DOM element → JS rukovalac → API poziv → backend ruta → odgovor → ishod u UI`.

**Kako su prikupljeni podaci** (skripte u scratchpad-u, nisu commit-ovane):

| Korak | Metod | Rezultat |
|---|---|---|
| Registrovane rute | `import api; api.app.routes` sa sanitizovanim env-om | **618 ruta** |
| Rukovaoci (inline event atributi) | acorn AST + parsiranje string literala iz `vindex.js` | **828 atributa** (620 `index.html`, 208 dinamički generisan HTML) |
| Globalne definicije | AST: `function X`, `var/let/const X` na Program nivou, `window.X =`, hoisted `var` | **1093 globala** |
| `fetch` pozivi | AST `CallExpression`, rekonstrukcija punog URL šablona (dinamički delovi → `«*»`) | **303 poziva** |
| DOM ID lookup-ovi | AST: `getElementById('x')`, `querySelector('#x')` | **1490 lookup-ova** vs **1034 statička + 50 dinamička ID-a** |
| `href` linkovi | regex nad HTML-om izvan `<script>` blokova | **23 linka** |

**Zašto regex nije bio dovoljan.** Prvi prolaz regexom prijavio je 0 rukovalaca zato što se
`onclick` u `vindex.js` gradi konkatenacijom sa escape-ovanim navodnicima
(`onclick="fn(\''+id+'\')"`). Tek AST daje raspakovanu (`cooked`) vrednost string literala.
Isto važi za URL-ove: `BASE_URL + '/api/x/' + id + '/y'` je bez AST-a nevidljiv kao ruta.

**Priznata ograničenja (ne tvrdim više nego što sam dokazao):**

- Analiza je **statička**. Nijedan klik nije izvršen u browseru. Nalazi tipa "korisnik ne vidi
  rezultat" izvedeni su iz nepostojanja DOM čvora, ne iz posmatranog ponašanja.
- 12 `fetch` poziva ima potpuno dinamičan URL (`FULLY_DYNAMIC`); svaki je **ručno pročitan**
  i verifikovan — svi vode na postojeće rute (sekcija 6).
- Rukovalac koji postoji ne znači da je logika ispravna. Provereno je postojanje lanca,
  ne semantička ispravnost odgovora.
- `window.X = ...` unutar funkcije računat je kao globalna definicija. Ako se ta funkcija
  nikad ne izvrši, rukovalac bi u praksi bio mrtav. Nije nađen takav slučaj među korišćenim
  imenima, ali metod ga ne bi uhvatio sa sigurnošću → to je granica dokaza.

---

## 2. Zbirni rezultat po statusu

| Status | Broj | Šta znači |
|---|---|---|
| `VERIFIED` | 290 fetch poziva + 826 handler-atributa | Lanac potpun |
| `PARTIALLY_VERIFIED` | 4 | Radi delimično / pod uslovom, bez poruke korisniku |
| `BROKEN` | 6 elemenata (5 lanaca) | Lanac prekinut, dokazano |
| `DEAD` | 2 funkcije + ~18 legacy ID-jeva | Rukovalac postoji ali ga niko ne poziva / ruta ne postoji |
| `UNVERIFIED` | 12 fetch poziva → svih 12 ručno razrešeno u `VERIFIED` | — |

**Ključni pozitivan nalaz:** od 430 različitih imena funkcija pozvanih iz DOM-a,
**nijedno nije nedefinisano**. Klasična "mrtva dugmad" (`onclick` → nepostojeća funkcija)
u ovoj aplikaciji **ne postoje**. Sve prave greške su dublje u lancu — na nivou
**DOM ID-jeva** i **jedne URL rute**.

---

## 3. Glavna tabela — elementi sa prekinutim ili delimičnim lancem

| Element | Rukovalac | API | Backend ruta | Ishod | Status | Dokaz |
|---|---|---|---|---|---|---|
| Dugme „Generisi graf" | `evidenceGraph_generiši(_egPredmetId)` | `POST /api/evidence-graph/generi%C5%A1i` | **ne postoji** (backend sluša `/generisi`) | 405/404; toast „Greška pri generisanju grafa." | `BROKEN` | `vindex.js:22817` → `:22769`; `routers/evidence_graph.py:178` |
| Dugme „↺ Regenerisi" | `evidenceGraph_generiši(_egPredmetId)` | isto | isto | isto | `BROKEN` | `vindex.js:23031` → `:22769` |
| Upload dokumenta (`onchange`) | `pred_upload_doc(this.files[0])` | `POST /api/predmeti/{id}/upload` — **radi** | postoji | Upload uspeva, ali AI procena i upozorenja se upisuju u `#pred-procena-result` koji **ne postoji** → korisnik ne vidi ništa | `BROKEN` | `index.html:1085`; `vindex.js:20048`, `:20130` |
| Upload zona (klik + drag&drop) | `pred_upload_trigger()` / `pred_upload_doc(...)` | isto | postoji | isto kao gore | `BROKEN` | `index.html:1086` |
| Dugme „Štampaj" | `pred_print()` | — | — | Sakriva svih 12 `.pred-subtab-pane`, pa pokušava da prikaže `#pred-pane-ccc` koji **ne postoji** → štampa prazan sadržaj predmeta | `BROKEN` | `index.html:769`; `vindex.js:19925-19934` |
| Dugme „Sačuvaj u predmet" | `analizaSacuvajUPredmet()` | — | — | Prebaci na tab Predmeti; traži `#pred-novi-btn` i `[onclick*="predmetNovi"]` — **nijedno ne postoji** → analiza se ne sačuva | `BROKEN` | `index.html:4035`; `vindex.js:7953-7959` |
| Dugme „Generiši nacrt tužbe" | `analizaGenerisiNacrt()` | — | — | `_analizaSwitchTab('n')` traži `.t-tab[onclick*="'n'"]` — **ne postoji**; `#tab-n textarea` — **ne postoji** → ni prelaz ni prenos teksta | `BROKEN` | `index.html:4036`; `vindex.js:7962-7968` |
| Dugme „Pošalji u Strategiju" | `analizaDodajUStrategiju()` | — | — | `_analizaSwitchTab('t')` ne nalazi tab → nema navigacije; `#strat-tekst` **se popuni**, ali nevidljivo | `PARTIALLY_VERIFIED` | `index.html:4037`; `vindex.js:7970-7977` |
| Copilot akcija `generate_document` | dispatch → `#tip-podneska` | — | — | Prelaz na „nacrti" radi; **predselekcija tipa podneska tiho izostane** (ID ne postoji) | `PARTIALLY_VERIFIED` | `vindex.js:16951` |
| Dugme „← Pravni alati" | `setTab(getElementById('tab-btn-alati'),'alati')` | — | — | `getElementById` vraća `null`, ali `setTab` ima alias granu `t==='alati'` → preusmeri na `#tab-btn-aiws` (postoji) → **radi** | `PARTIALLY_VERIFIED` | `index.html:1881`; `vindex.js:1998-2003` |
| Dashboard brza akcija + panel | isti `setTab(...'tab-btn-alati'...)` | — | — | isto — radi samo preko alias fallback-a | `PARTIALLY_VERIFIED` | `vindex.js:1630`, `:1927` |
| `pred_submitProcena()` | — | `POST` (procena) | — | Funkcija postoji, **niko je ne poziva**; čitala bi `#pred-cinjenice` (ne postoji) bez null-provere → `TypeError` da je ikad povezana | `DEAD` | `vindex.js:20144-20146` |
| `aic3_submit()` | — | — | — | Definisana, **nema DOM reference**; `#aic3-q/-btn/-result` ne postoje | `DEAD` | `vindex.js:10624-10631` |

---

## 4. Mrtva dugmad (`onclick` → nepostojeća funkcija)

**Nema ih. Nula.**

Provereno je svih **828** inline event atributa (`onclick` 754, `onchange` 33, `oninput` 22,
`onmouseover` 7, `onmouseout` 6, `onkeydown` 4, `onfocus` 1, `onblur` 1), iz kojih je izvučeno
**430 različitih imena funkcija**. Svako ime razrešeno je na globalnu definiciju
(`function X` / `var|let|const X` na Program nivou / `window.X =`).

Analiza je prijavila 2 „nedostajuća" imena, oba **lažno pozitivna** — ključna reč `function`
iz fragmenta `onclick="cmdkClose();(function(){...})()"` (`vindex.js:13365`, `:13372`).

**Pozitivna kontrola metoda:** upravo ta 2 lažna pozitiva dokazuju da mehanizam prijave radi —
identifikator koji nije u skupu globala **jeste** prijavljen. Da postoji stvarno mrtvo dugme,
bilo bi uhvaćeno istim putem.

**Posebna napomena — funkcije sa srpskim dijakriticima u imenu.** Postoji grupa globalnih
funkcija čije ime sadrži `š`/`ć`: `evidenceGraph_generiši`, `ugovor_generiši`, `docTplGeneriši`,
`pred_rokokiGeneriši`. U JavaScript-u je to legalno i **sve su ispravno razrešene** (definicija i
poziv se poklapaju). Ali to je isti obrazac neusaglašenosti latinice/dijakritika koji je na
mrežnom sloju proizveo jedini pravi 404 (sekcija 6) — vredi ga tretirati kao sistemski rizik,
ne kao stvar stila.

---

## 5. Mrtvi linkovi (`href`)

Provereno svih **23** `href` atributa.

**Sve interne stranice postoje kao registrovane rute:**
`/manifest.json`, `/static/vindex.css`, `/static/icon-192-v3.png`, `/security`, `/dpa`,
`/status`, `/privacy`, `/terms`, `/ai-disclosure` — svaka ima `GET` handler u `api.py`.

**`href="#"` — 2 pojave, obe benigne:**

| Lokacija | Element | Ocena |
|---|---|---|
| `index.html:4168` | `<a href="#" class="vx-land-logo">Vindex<em>AI</em></a>` | Logo u landing nav-u, bez `onclick`. Klik skroluje na vrh. Kozmetički no-op, **nije kvar funkcije**. |
| `index.html:4169` | `<a href="#" id="nav-cta-btn" onclick="openModal();return false;">` | Ima rukovalac + `return false` → korektan obrazac. `VERIFIED`. |

**Eksterni linkovi:** `fonts.googleapis.com`, `cdnjs.cloudflare.com`,
`https://www.pravno-informacioni-sistem.rs/` (`vindex.js:6718`) — van obima provere.

**Zaključak: mrtvih linkova nema.**

---

## 6. `fetch` pozivi ka nepostojećim rutama

Od **303** `fetch` poziva, poređenih sa **618** registrovanih ruta uz rekonstrukciju punog
URL šablona i poređenje metoda:

| Ishod | Broj |
|---|---|
| `OK` (putanja + metod se poklapaju) | 290 |
| `FULLY_DYNAMIC` (URL iz promenljive — ručno provereno) | 12 |
| **`METHOD_MISMATCH` / nepostojeća ruta** | **1** |

### 6.1 Jedini pravi nalaz — `/api/evidence-graph/generiši`

```
frontend  (vindex.js:22769):  POST BASE_URL + '/api/evidence-graph/generi%C5%A1i'
                              → ASGI dekodira → /api/evidence-graph/generiši
backend   (routers/evidence_graph.py:178):  @router.post("/generisi")
                              → /api/evidence-graph/generisi     (bez dijakritike)
```

Putanja se **ne poklapa**. Zahtev pada na `GET /api/evidence-graph/{predmet_id}`
(`evidence_graph.py:286`), koji hvata `generiši` kao `predmet_id`, ali je `GET`-only →
odgovor **405 Method Not Allowed**. Frontend to obrađuje kao generičku grešku:
`showToast('Greška pri generisanju grafa.')`.

Pogođena dugmad — **oba**:
- `vindex.js:22817` — „Generisi graf" (prazno stanje modala)
- `vindex.js:23031` — „↺ Regenerisi" (zaglavlje modala)

Funkcija Evidence Graph je time **potpuno nedostupna** — nema trećeg puta do generisanja.
`GET /api/evidence-graph/{predmetId}` (`vindex.js:22807`) je ispravan, ali samo čita
graf koji nikad ne može biti kreiran.

**Zašto testovi ovo nikad nisu uhvatili:**
`tests/test_gamma_evidence_check_wiring.py:32` koristi `"path": "/api/evidence-graph/generisi"` —
ispravnu ASCII putanju. Test dokazuje da **backend** radi. Nijedan test ne proverava da li
**frontend gađa putanju koju backend sluša**. To je struktura propuštanja, ne slučajnost.

### 6.2 Kontrolni slučaj — `/api/ugovor-zastupanja/generiši` **RADI**

Postoji još tačno jedan `%C5%A1` u URL-u (`vindex.js:22598`), ali on **nije bug**:

```
frontend:  POST '/api/ugovor-zastupanja/generi%C5%A1i'
backend (routers/ugovor_zastupanja.py:283):  @router.post("/api/ugovor-zastupanja/generiši")
```

Backend ruta **sadrži `š`**. Nakon ASGI dekodiranja putanje, poklapanje je tačno → **radi**.

To je jedina ne-ASCII ruta u celoj aplikaciji (1 od 618). Odatle i kvar: dva susedna modula
donela su suprotnu odluku o dijakritici u putanji, frontend je oba pozvao istim
URL-enkodovanim oblikom, i tačno jedan je promašio.

### 6.3 Dinamički URL-ovi — svih 12 ručno verifikovano

| Lokacija | Stvarni URL | Ruta |
|---|---|---|
| `vindex.js:1320` | `/api/firm/health-index` | postoji |
| `vindex.js:3203` | `modul.endpoint` → 8× `/strategija/*`, `/api/predictor/analiza` | sve postoje |
| `vindex.js:4543` | `/klijenti?pretraga=` | postoji |
| `vindex.js:4883` | `/klijenti` / `/klijenti/{id}` | postoji |
| `vindex.js:5263` | `modul.endpoint` → 11× `/web3/*` | sve postoje |
| `vindex.js:6189` | `/api/nacrt/types` | postoji |
| `vindex.js:7664` | `eps[dispatchTab]` → `/api/pitanje`, `/api/analiza`, `/api/nacrt`\|`/api/podnesak` | sve postoje |
| `vindex.js:13332` | `/api/search?q=` | postoji |
| `vindex.js:13909`, `:13984` | `/billing/report/po-klijentu`, `/billing/report/csv` | postoje |
| `vindex.js:17672` | `/api/cio/run` \| `/api/cio/daily` | postoje |
| `vindex.js:20034` | `_fetchWithTimeout` — generički omotač, URL od pozivaoca | n/a |

Svih 19 tabelarnih `endpoint:` vrednosti (`vindex.js:2995-3046`, `:5035-5117`) provereno
jedan po jedan — **svih 19 postoji** sa ispravnim `POST` metodom.

---

## 7. Prazni rukovaoci

Provereno je **881** parsiranih definicija funkcija, od kojih **430** referenciranih iz DOM-a.

| Kategorija | Broj |
|---|---|
| Prazno telo `{}` | **0** |
| Samo `console.log` | **0** |
| Odmah `return` kao prva naredba | **0** |
| `TODO`/`FIXME`/stub marker u kratkom telu | **0** |

**Praznih rukovalaca nema.** Ne postoji nijedno dugme koje izgleda aktivno a čija funkcija
ne radi ništa.

Međutim — i to je suština nalaza — **pravi ekvivalent praznog rukovaoca u ovoj aplikaciji
je funkcija koja radi puni posao i zatim upiše rezultat u DOM čvor koji ne postoji.**
Telo funkcije je puno; ishod za korisnika je isti kao da je prazno. Vidi sekciju 9.

---

## 8. Uslovne funkcije bez objašnjenja korisniku

Nađen je **101 rukovalac** sa vodećim „tihim guard-om" (`if (<uslov>) return;` bez ikakve
poruke korisniku). Svaki je proveren u DOM kontekstu — **da li je dugme uopšte vidljivo
kada uslov ne važi.**

| Tip guard-a | Broj | Ocena |
|---|---|---|
| `!currentSession` (nije prijavljen) | 70 | Ceo `#vx-shell` je `display:none` dok se ne prijavi (`vindex.js:99-108`) → dugme nedostupno. **Nije problem.** |
| `!activePredmetId` i sl. (nema otvorenog predmeta) | 31 | Svi su unutar gejtovanih kontejnera — vidi dole. **Nije problem.** |

**Dokaz za `activePredmetId` grupu.** Svih 26 statički deklarisanih dugmadi iz te grupe
(`timer_start`, `evidence_load`, `pred_runPipeline`, `pred_upload_doc`, `brain_load`,
`ccc_load`, `portal_generateLink`, `matter_intel_load`, `workflow_pokreni` …) nalazi se
između linija **703 i 1858** `index.html`-a — unutar `<div id="pred-detail" class="pred-detail">`.

```css
/* static/vindex.css:777-778 */
.pred-detail      { display:none; }
.pred-detail.show { display:block; }
```

Klasa `.show` se dodaje isključivo u `pred_select()` (`vindex.js:10715`), tj. tek kada
korisnik otvori predmet. Dugmad su fizički nevidljiva bez aktivnog predmeta.

**Tri dugmeta van tog kontejnera — sva tri ispravno gejtovana:**

| Rukovalac | Guard | Zaštita u DOM-u |
|---|---|---|
| `pred_bulkAkcija` (`index.html:660-661`) | `!_selectedPredmeti.size` | `#pred-bulk-bar` ima `style="display:none"` |
| `crmSacuvajTarifu` / `crmUkloniTarifu` (`:1991-1992`) | `!crmAktivniId` | `#crm-tarifa-section` ima `style="display:none"` |
| `crmCsvPosalji` (`:2128`) | `!_csvFajl` | `#crm-csv-btn` ima `disabled` + `opacity:0.5` |

**Zaključak: nijedna funkcija ne zahteva stanje o kojem korisnik nije obavešten kroz UI.**
Ovo je kvalitetan obrazac i treba ga zabeležiti kao takav — hipoteza iz zadatka ovde nije
potvrđena, i to je nalaz.

*Preostale dve `PARTIALLY_VERIFIED` stavke iz sekcije 3 (`analizaDodajUStrategiju`,
`generate_document`) nisu guard-problem nego posledica nepostojećih ID-jeva — sekcija 9.*

---

## 9. Nepostojeći DOM ID-jevi — pravi uzrok svih kvarova

Od **1490** `getElementById` / `querySelector('#…')` lookup-ova, **31 ID** ne postoji ni u
`index.html` (1034 statička ID-a), ni u HTML-u koji generiše `vindex.js` (50 dinamičkih ID-a
+ 30 prefiksa iz konkatenacije).

### 9.1 Klik-dostupni — prouzrokuju kvar

| ID | Referenca | Posledica |
|---|---|---|
| `pred-procena-result` | `vindex.js:20048`, `:20130`, `:20148` | **Najteži nalaz — vidi 9.2** |
| `pred-pane-ccc` | `vindex.js:19929` (`pred_print`) | „Štampaj" sakrije svih 12 panela pa pokuša da prikaže preimenovani ID → **štampa prazan predmet**. Sadržaj je preseljen u `#ccc-container` (`index.html:773`). |
| `pred-novi-btn` | `vindex.js:7956` | „Sačuvaj u predmet" ne otvara modal. Fallback selektori `[onclick*="predmetNovi"]`/`[onclick*="noviPredmet"]` daju **0 pogodaka** — prava funkcija je `pred_openNewModal()` (`vindex.js:12537`). Oba puta zastarela. |
| `tab-n` (`#tab-n textarea`) | `vindex.js:7964` | „Generiši nacrt tužbe" — tab `n` ne postoji. Realni tabovi: `aiws, dok, fin, h, k, kal, kanc, p, pi, s, settings`. |
| `tab-btn-alati` | `index.html:1881`, `vindex.js:1630`, `:1927` | Preživljava samo zahvaljujući alias grani u `setTab` — vidi 9.3 |
| `tip-podneska` | `vindex.js:16951` | Copilot `generate_document`: predselekcija tipa podneska tiho izostaje. |

### 9.2 NAJTEŽI NALAZ — `#pred-procena-result` (regresija)

`pred_upload_doc()` (`vindex.js:20040-20143`) je **živ rukovalac** sa tri ulazne tačke:
- `index.html:1085` — `onchange="pred_upload_doc(this.files[0])"`
- `index.html:1086` — `onclick="pred_upload_trigger()"` (drop zona)
- `index.html:1086` — `ondrop="…pred_upload_doc(event.dataTransfer.files[0])"`

Upload **radi**: `POST /api/predmeti/{id}/upload` postoji, backend odgovara. Ali sve što
funkcija sastavi upisuje se u `resEl = document.getElementById('pred-procena-result')`,
koji je `null`. Zbog `if (resEl)` zaštite nema izuzetka — **sve nestaje tiho**:

| Šta se gubi | Linija |
|---|---|
| Spinner „Analiziram predmet…" | `:20061` |
| **AI procena dokumenta** (`pred_renderProcena` / `pred_renderPresuda`) | `:20097-20101` |
| Poruke o grešci (415/422/413/5xx) — `resEl.innerHTML=''` | `:20077`, `:20082`, `:20087` |
| ⚠ „Originalni fajl nije sačuvan u trezoru" | `:20110` |
| ⚠ „Moguć duplikat" | `:20114` |
| Kartica za potvrdu auto-povezivanja (`pred_renderConfirmCard`) | `:20120` |

**Ovo je dokazana regresija, ne propust u dizajnu:**

```
index.html.bak:1004   <div id="pred-procena-result" style="margin-top:0.3rem;"></div>
index.html (danas)    — nema ga
```

`git log -S"pred-procena-result" -- index.html` → uklonjen u
**`010082aa`** *„feat(ia): AI Analiza flagship showcase — Case DNA hero + merged Evidence/Law Firm Brain"*.
Redizajn je uklonio kontejner; `vindex.js` i dalje piše u njega.

**Zašto je ovo najozbiljnije:** komentar u kodu na `:20103-20107` izričito kaže da su
`original_preserved` / `mozda_duplikat` dodati u okviru **Final Beta Gate F7/F20** upravo zato
što je advokat čiji original **nije** sačuvan u trezoru video isti ekran uspeha kao onaj čiji
jeste. Ta ispravka je napisana, merge-ovana, i **nikad ne može da se prikaže** — mount čvor je
uklonjen u nepovezanom redizajnu. Bezbednosno upozorenje o gubitku originalnog dokumenta je
mrtvo od commit-a `010082aa`.

### 9.3 Latentni rizik — `tab-btn-alati`

`vindex.js:1998` sadrži komentar:

> `tab-btn-alati ostaje u DOM-u kao skriveni shim jer ga dashboard (zakljucan kod) i dalje direktno referencira po id-ju`

**Tvrdnja je netačna — tog elementa nema u `index.html`.** Tri dugmeta rade isključivo zato što
`setTab` ima alias granu (`vindex.js:2002`):

```js
if (t === 'alati') { t = 'aiws'; el = document.getElementById('tab-btn-aiws') || el; }
if (!el) return;
```

`#tab-btn-aiws` postoji, pa `el` bude ne-null. Ukloni li neko taj `||` fallback verujući
komentaru da shim postoji, sva tri dugmeta umiru istog trenutka bez ijedne greške u konzoli.

### 9.4 Mrtav kod — nije klik-dostupno

| ID(-jevi) | Kontekst | Ocena |
|---|---|---|
| `aic3-q`, `aic3-btn`, `aic3-result` | `aic3_submit()` (`vindex.js:10624`) | Funkcija **nema DOM referencu**. `DEAD`. |
| `pred-cinjenice` | `pred_submitProcena()` (`vindex.js:20144`) | Funkcija se **nigde ne poziva**. Čita `.value` **bez null-provere** → `TypeError` da je ikad povezana. `DEAD`, ali zamka za budućnost. |
| `hamburger`, `mobile-menu` | `toggleMenu()` (`vindex.js:1072`) | Bez null-provere → `TypeError`, ali funkcija **nema DOM referencu**. `DEAD`. |
| `tog`, `p1`, `p2`, `pp1`, `pp2` | `toggleAnnual()` (`vindex.js:8037`) | Bez null-provere; funkcija **nema DOM referencu**. `DEAD`. |
| `demo`, `demoTxt`, `demoConf`, `hero`, `nav`, `para-canvas`, `sphereCanvas`, `sphereWrap`, `srp-typing`, `srp-content`, `modBody`, `modLabel`, `modShowcase` | Legacy landing-page IIFE-ovi | Svi imaju `if (!el) return;` → tiho izlaze. Bez posledica, ali ~500 linija mrtvog koda. |
| `ni` | `focusInput()` (`vindex.js:7519`) | Srednji član `||` lanca; `#qi`/`#aitxt` postoje. Bez posledica. |
| `vx-topbar-settings-btn` | `vxSync()` (`vindex.js:99`) | Dodeljen promenljivoj `ts` koja se **nikad ne koristi**. Bez posledica. |

---

## 10. Prioritet za popravku

| # | Nalaz | Zašto |
|---|---|---|
| 1 | `#pred-procena-result` uklonjen (9.2) | Upload je centralni tok. Advokat gubi AI procenu **i** bezbednosno upozorenje o nesačuvanom originalu. Regresija sa poznatim commit-om. |
| 2 | `/api/evidence-graph/generiši` (6.1) | Cela Evidence Graph funkcija nedostupna; oba dugmeta mrtva; test daje lažnu sigurnost. |
| 3 | „Sledeći korak" traka (3, 9.1) | 2 od 3 dugmeta potpuno mrtva, 1 delimično — direktno posle AI analize, gde je poverenje najosetljivije. |
| 4 | `pred_print()` → `#pred-pane-ccc` (9.1) | „Štampaj" daje prazan dokument. |
| 5 | Netačan komentar o `tab-btn-alati` (9.3) | Ne kvari ništa danas; navodi sledećeg čitaoca na regresiju u 3 dugmeta. |
| 6 | Sistemski: dijakritika u rutama (6.2) | 1 ne-ASCII ruta od 618. Dva modula, dve suprotne odluke, jedan promašaj. |

**Sistemska pouka:** svih 5 dokazanih kvarova deli isti oblik — *kontrakt između dva sloja
promenio se sa jedne strane, a druga strana nije ni pukla ni prijavila grešku.* Odbrambeni
`if (!el) return;` i `if (resEl)` obrasci — sami po sebi dobra praksa — pretvorili su svaki
od tih kvarova iz glasnog `TypeError` u tihi gubitak funkcije. Testovi to ne hvataju jer
nijedan ne proverava da frontend gađa isti ID/URL koji druga strana pruža.

---

## 11. Reproducibilnost

Provera se ponavlja bez izmena u repou:

1. **Rute:** import `api` sa sanitizovanim env-om (`SUPABASE_URL=https://fake.supabase.co` itd.),
   pa `[r.path for r in api.app.routes]`; upisati kao UTF-8 (Windows `cp1252` stdout kvari `š`).
2. **Rukovaoci / fetch / ID-jevi:** `npm install acorn`, pa AST prolaz kroz `static/vindex.js`
   i inline `<script>` blokove `index.html`-a. Regex nije dovoljan — vidi sekciju 1.
3. **Poređenje:** ID-lookup-ovi vs unija statičkih i dinamički generisanih ID-jeva;
   `fetch` šabloni vs registrovane rute uz poklapanje metoda i **URL-dekodiranje putanje**.

Predlog trajne zaštite: CI provera koja pada kada `getElementById('x')` referencira ID koji
ne postoji ni u `index.html` ni u generisanom HTML-u, i kada `fetch` šablon ne odgovara
nijednoj registrovanoj ruti. Oba nalaza #1 i #2 bila bi uhvaćena istog dana.
