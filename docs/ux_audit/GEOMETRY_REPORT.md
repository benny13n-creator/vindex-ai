# GEOMETRY / VISUAL UX AUDIT — Vindex AI

**Datum:** 2026-08-12
**Metod:** stvarno iscrtavanje u Chromium 148.0.7778.96 (Playwright), merenje
`getBoundingClientRect()` i `document.elementFromPoint()` u živoj stranici.
**Nijedan nalaz u ovom dokumentu nije izveden iz CSS deklaracija.** Svaki broj je
očitan iz iscrtanog DOM-a.

**Izmenjen fajl:** samo ovaj. Nula izmena CSS-a, HTML-a, JS-a.

---

## 0. METOD — tačno kako je stranica iscrtana i šta je moralo da se stubuje

### 0.1 Server

`uvicorn api:app --port 8123 --host 127.0.0.1`, pokrenut kao podproces sa
**sanitizovanim okruženjem** (proces ne nasleđuje ceo `os.environ`; prosleđen mu je
samo minimalni Windows skup + lažni ključevi):

```
SUPABASE_URL=https://fake.supabase.co
SUPABASE_SERVICE_KEY=test-only
SUPABASE_ANON_KEY=test-only-anon
SUPABASE_JWT_SECRET=test-only-jwt-secret-longer-than-32-chars
OPENAI_API_KEY=sk-test
PINECONE_API_KEY=test
FOUNDER_EMAILS=f@test.rs
FIELD_ENCRYPTION_KEY=<base64 32 bajta>
ENVIRONMENT=development
```

`load_dotenv()` u `api.py:23` ne prepisuje već postavljene promenljive
(python-dotenv, `override=False`), pa `.env` nije mogao da vrati produkcione
vrednosti preko ovih.

Izlaz uvicorn-a preusmeren je u fajl (`uvicorn.log`), **ne** u `subprocess.PIPE` —
sa PIPE-om se bafer napuni i server se zaglavi pre nego što se veže za port.
Server je potvrđen sa `GET /app` → `200`, 422005 bajtova.

### 0.2 Blokada mreže

`context.route("**/*")` propušta samo `127.0.0.1:8123` i CDN hostove koje
`index.html` zaista koristi (`cdn.jsdelivr.net`, `unpkg.com`,
`cdnjs.cloudflare.com`, `fonts.googleapis.com`, `fonts.gstatic.com`). Sve ostalo
je prekinuto (`route.abort()`) — uključujući produkcioni Supabase host
(`czsxymueizfqrbbgqqob.supabase.co`) koji je tvrdo upisan u
`static/vindex.js:235`. Tokom svih prolaza lista prekinutih zahteva bila je
prazna, tj. stranica nije ni pokušala izlazak van dozvoljenih hostova.

### 0.3 Šta je moralo da se stubuje da bi se dashboard iscrtao

Dashboard **jeste** iscrtan u potpunosti — `#kc-body.innerHTML` = **24 064
znaka** na svih 7 širina. Da bi se to postiglo, stubovano je tačno ovo:

1. **`window.fetch`** (kroz `page.add_init_script`, dakle pre učitavanja
   `vindex.js`) — presreće `/api/*`, `/notifications`, `/zastarelost/*`,
   `/analytics/track`, `/billing*`, `*.supabase.co` i vraća kontrolisan JSON u
   obliku koji backend stvarno vraća. Oblici su preuzeti iz izvora, ne
   izmišljeni:
   - `routers/dashboard.py:385-418` → `/api/dashboard/command-center`
   - `routers/workspace.py:272-282` → `/api/workspace`
   - `routers/inbox.py:165-172` → `/api/inbox`
   - `/api/firm/health-index`, `/api/cio/daily`, `/notifications` → validni
     prazni/popunjeni oblici
   Svaki traženi URL je zabeležen u `window.__FETCHLOG`; nepoklopljeni u
   `window.__FETCHUNMATCHED` (bilo ih je 2: `/api/nacrt/types`, `/api/courts` —
   dodati u stub u drugom prolazu).

2. **Stanje prijave.** `vindex.js` je klasičan skript, pa su `var currentUser` i
   `var currentSession` (linije 257–258) svojstva `window`-a. Posle učitavanja
   stranice postavljeno je:
   ```js
   window.currentUser    = {id:'stub-user-0000', email:'test@vindex.local', ...};
   window.currentSession = {access_token:'stub-token', user: window.currentUser, ...};
   window.currentUserIsPro = true;
   updateAuthUI();                                  // vindex.js:393
   setTab(document.getElementById('tab-btn-h'),'h'); // vindex.js:1996 -> dash_load()
   ```
   `updateAuthUI()` prebacuje `#vx-shell` na `display:flex` i `#vx-landing` na
   `display:none`; `setTab(...,'h')` poziva `dash_load()` (`vindex.js:1267`) koji
   fetch-uje command-center + inbox i puni `#kc-body` preko `_dashRender`
   (`vindex.js:1589`). **Prava prijava nije korišćena.**

3. **`?prikaz=demo`** — uključuje `_PRIKAZ_DEMO_VREDNOSTI`
   (`vindex.js:1580`, `{aktivni:19, hitniRok:1, noviDok:6, visokRiz:3}`) tako da
   sfera nije prazna i kvadranti imaju stvarnu veličinu.

4. **Animacije pauzirane** pre merenja
   (`*{animation-play-state:paused;transition:none}`) da bi koordinate bile
   reproducibilne — sfera i orbitalni prstenovi su `requestAnimationFrame`
   animacija.

### 0.4 Šta je mereno

Sedam širina × dve pozicije skrola (vrh i dno skrol-kontejnera
`.vx-panels-wrap`), plus tri scenarija sa otvorenim modalom (Intake Wizard,
`intakeOtvori()`):

| širina × visina | scenariji |
|---|---|
| 1920×1080 | vrh, dno, modal |
| 1440×900 | vrh, dno |
| 1366×768 | vrh, dno, modal |
| 1280×800 | vrh, dno |
| 1024×768 | vrh, dno |
| 768×1024 | vrh, dno |
| 390×844 (`is_mobile`, `has_touch`) | vrh, dno, modal |

Selektor interaktivnih elemenata:
`a[href], button, input:not([type=hidden]), select, textarea, summary,
[role=button|tab|link|menuitem|checkbox|switch], [onclick],
[tabindex]:not([tabindex="-1"]), label[for], [contenteditable=true]`.

Vidljivost: `rect.w≥1 && rect.h≥1`, `display≠none`, `visibility≠hidden`,
`opacity>0` (uključujući nasleđenu, uz `el.checkVisibility()`).

**Test nedostupnosti (najjači dokaz u ovom izveštaju):** preko svake kontrole
položena je **mreža 7×7 = 49 tačaka**; u svakoj se poziva
`document.elementFromPoint(x,y)`. Ako vraćeni element nije sama kontrola, ni njen
predak, ni potomak — ta tačka je **nedostupna kliku**. Prijavljuje se procenat
blokirane površine i identitet blokatora. `elementFromPoint` poštuje
`pointer-events`, pa sloj sa `pointer-events:none` ispravno **ne** računa kao
blokator (npr. `#toast-container`, `canvas#cv`, `#cursor`).

Sirovi podaci: koordinate svakog merenog elementa, sve preseke i sve tačke mreže
sadrže `raw.json` i `coverage.json` iz radnog direktorijuma merenja; ključni
brojevi su prepisani niže u tabele.

---

## 1. NALAZI — sažetak

| # | Ozbiljnost | Nalaz | Širine |
|---|---|---|---|
| G-001 | **KRITIČNO** | `#feedback-fab` je **100% nedostupan** — 49/49 tačaka blokirano | **svih 7** |
| G-002 | **KRITIČNO** | `#intake-btn-next` („Dalje →", glavni CTA Intake Wizard-a) **100% nedostupan** | 390 |
| G-003 | **VISOKO** | `#vx-voice-fab` **100% nedostupan** | 390 |
| G-004 | **VISOKO** | „+ Iz dokumenta" odsečen desnom ivicom, 81,8% van ekrana, nedohvatljivo | 1024, 768 |
| G-005 | **VISOKO** | `#tab-h` ima **34px horizontalnog preliva** (dokument-nivo skrol = 0) | 390 |
| G-006 | SREDNJE | `#intake-btn-next` 14,3% blokiran plutajućim mikrofonom **iznad modala** | 1920, 1366 |
| G-007 | SREDNJE | 2 kvadranta sfere 100% blokirana donjom navigacijom (na početnom skrolu) | 768 |
| G-008 | SREDNJE | Poslednji red inbox-a 100% blokiran donjom navigacijom (na početnom skrolu) | 390 |
| G-009 | SREDNJE | `#vx-back-btn`: nominalno 44px visine, **stvarno klikabilno 30px** | 390, 768 |
| G-010 | SREDNJE | Bočna traka odseca tekst 2 stavke, `overflow-x:hidden` → nedohvatljivo | 1024 |
| G-011 | SREDNJE | 4 dodirne mete ispod 44px na 390 (najmanja 16×16) | 390 |
| G-012 | NISKO | Donja navigacija završava na `bottom=1025` pri `innerHeight=1024` | 768 |

**Horizontalni skrol na nivou dokumenta: 0 na svih 7 širina i u sva 3 modalna
scenarija.** (Ali vidi G-005 — preliv postoji na nivou kontejnera.)

---

## 2. G-001 — `#feedback-fab` je nedostupan na svakoj izmerenoj širini

Dugme za povratnu informaciju (💬) ima veličinu, vidljivo je po CSS-u, i
**nijedna njegova tačka nije klikabilna ni na jednoj od 7 širina.**

### Dokaz — `elementFromPoint`, mreža 7×7

| širina | `#feedback-fab` rect [x,y,w,h] | blokirano | blokator | z-index blokatora |
|---|---|---|---|---|
| 1920 | `[1860, 1020, 42, 42]` | **49/49 = 100%** | `button#vx-voice-fab` | 9990 vs 7000 |
| 1440 | `[1380, 840, 42, 42]` | **49/49 = 100%** | `button#vx-voice-fab` | 9990 vs 7000 |
| 1366 | `[1306, 708, 42, 42]` | **49/49 = 100%** | `button#vx-voice-fab` | 9990 vs 7000 |
| 1280 | `[1220, 740, 42, 42]` | **49/49 = 100%** | `button#vx-voice-fab` | 9990 vs 7000 |
| 1024 | `[964, 708, 42, 42]` | **49/49 = 100%** | `button#vx-voice-fab` | 9990 vs 7000 |
| 768 | `[706, 962, 44, 44]` | **49/49 = 100%** | `button#mob-btn-mob-more` u `div#vx-mobile-nav` | 9999 vs 7000 |
| 390 | `[328, 782, 44, 44]` | **49/49 = 100%** | `button#mob-btn-mob-more` u `div#vx-mobile-nav` | 9999 vs 7000 |

### Geometrija preseka (1920×1080)

```
#feedback-fab   x: 1860 → 1902   y: 1020 → 1062   (42 × 42 = 1764 px²)
#vx-voice-fab   x: 1840 → 1896   y: 1000 → 1056   (56 × 56)
presek          x: 1860 → 1896   y: 1020 → 1056   = 36.0 × 36.0 = 1296 px²
```

Presek pokriva 73,5% površine. Preostalih 26,5% je „L" traka po desnoj i donjoj
ivici — ali sve 49 tačaka mreže (koje su na 1/14, 3/14, … 13/14 širine i visine)
padaju u blokirani deo, pa je i centar (`1881, 1041`) blokiran. Praktično: dugme
se ne može kliknuti.

Na 768 i 390 mesto blokatora preuzima donja navigacija (`#vx-mobile-nav`,
`z=9999`, `[0, 784, 390, 60]` na 390) — dakle **nema širine na kojoj ovo dugme
radi**.

---

## 3. G-002 — „Dalje →" u Intake Wizard-u je nedostupan na telefonu

Otvoren scenario: `intakeOtvori()` na 390×844, korak 1/5.

```
#intake-btn-next   rect = [23, 786, 345, 44]      (z-index 2101, u .intake-panel z=2101)
#vx-mobile-nav     rect = [0, 784, 390, 60]       (position: fixed, z-index 9999)
presek             x: 23 → 368   y: 786 → 830     = 345 × 44 = 15 180 px² = 100% dugmeta
```

`elementFromPoint` u svih 49 tačaka vraća dugmad donje navigacije:

```
button#mob-btn-p  ("Predmeti")  x14 tačaka
button#mob-btn-k  ("Klijenti")  x14 tačaka
button#mob-btn-h  ("Početna")   x7  tačaka
button#mob-btn-kal("Rokovi")    ...
→ blokirano 49/49 = 100.0%
```

Modal (`#intake-overlay` z=2100, `.intake-panel` z=2101) je **ispod** donje
navigacije (z=9999). Snimak `shot_390_modal.png` to potvrđuje vizuelno: od
podnožja čarobnjaka vidi se samo tanka linija iznad navigacije.

**Posledica:** čarobnjak za novi predmet se na telefonu ne može odvesti dalje od
koraka 1. Isto važi i za `← Nazad` u istom podnožju (`#intake-panel-footer`,
`[1, ~786, 389, ...]`).

Dodatno, ceo modal je 14,3% (7/49 tačaka) prekriven donjom navigacijom —
`#intake-overlay` i `.intake-panel` oboje `[0, 0, 390, 844]`, donja traka od
`y=784`.

---

## 4. G-003 — `#vx-voice-fab` nedostupan na 390

```
#vx-voice-fab   rect = [18, 780, 48, 48]   position: fixed, z-index 9990
#vx-mobile-nav  rect = [0, 784, 390, 60]   position: fixed, z-index 9999
presek          x: 18 → 66   y: 784 → 828  = 48 × 44 = 2112 px² (91,7% dugmeta)
```

`elementFromPoint`: 42/49 tačaka → `button#mob-btn-h` („Početna"),
7/49 → `div#vx-mobile-nav`. **Blokirano 49/49 = 100%.**

Ista tri plutajuća elementa se na 390 gomilaju u istoj traci:

| element | rect | z-index |
|---|---|---|
| `div#vx-mobile-nav` | `[0, 784, 390, 60]` | 9999 |
| `button#vx-mobile-fab` | `[320, 716, 52, 52]` | 9998 |
| `button#vx-voice-fab` | `[18, 780, 48, 48]` | 9990 |
| `button#feedback-fab` | `[328, 782, 44, 44]` | 7000 |

Dva od četiri (`voice-fab`, `feedback-fab`) su potpuno pokrivena.

---

## 5. G-004 — „+ Iz dokumenta" je odsečen i nedohvatljiv na 1024 i 768

| širina | rect | desna ivica | van ekrana | vidljivo | `elementFromPoint` u centru |
|---|---|---|---|---|---|
| 1920 | `[1797.4, 9.5, 106.6, 28]` | 1904.0 | 0 px | 100% | OK |
| 1366 | `[1243.4, 9.5, 106.6, 28]` | 1350.0 | 0 px | 100% | OK |
| 1280 | `[1157.4, 9.5, 106.6, 28]` | 1264.0 | 0 px | 100% | OK |
| **1024** | `[1004.6, 9.5, 106.6, 28]` | **1111.3** | **87.3 px** | **18.2%** | **`CENTAR VAN EKRANA`** |
| **768** | `[712.5, 1.5, 106.6, 44]` | **819.1** | **51.1 px** | **52.1%** | OK (centar još pada u ekran) |
| 390 | `[259.2, 1.5, 120.8, 44]` | 380.0 | 0 px | 100% | OK (mobilni raspored) |

Na 1024 centar dugmeta je na `x = 1057.9`, izvan `innerWidth = 1024` — kontrola
se ne može ni testirati klikom u centar, jer centra nema na ekranu.

**Nedohvatljivo je, ne samo odsečeno.** Roditelj `.vx-body` ima
`overflow-x: hidden` uz `scrollWidth = 931 > clientWidth = 844` — 87px viška
postoji u rasporedu ali se do njega ne može doskrolovati. Dokument-nivo
`scrollWidth` ostaje 1024, pa test „ima li horizontalnog skrola" ovo **ne**
hvata.

Vizuelna potvrda: `shot_1024_top.png` — u gornjem desnom uglu vidi se samo „+".

---

## 6. G-005 — horizontalni preliv unutar `#tab-h` na 390 (dokument-nivo test ga ne vidi)

| širina | `#tab-h` `scrollWidth` | `clientWidth` | preliv | `maxScrollLeft` | `documentElement.scrollWidth − innerWidth` |
|---|---|---|---|---|---|
| 1920 | 1680 | 1680 | 0 | 0 | 0 |
| 1366 | 1126 | 1126 | 0 | 0 | 0 |
| 1280 | 1040 | 1040 | 0 | 0 | 0 |
| 1024 | 844 | 844 | 0 | 0 | 0 |
| 768 | 768 | 768 | 0 | 0 | 0 |
| **390** | **424** | **390** | **34 px** | **34** | **0** |

Krivac je izmeren:

```
div#kc-panel-aktivni.kc-panel   rect = [14, 1275.8, 409.7, 358]   right = 423.7
viewport width = 390            →   33.7 px izvan desne ivice
```

Panel „Aktivni predmeti" je širi od ekrana za 33,7px. Zbog toga svih 12
interaktivnih elemenata u njemu i u panelu „Poslednje aktivnosti" ima
`right = 402.7 > 390`:

```
span.kc-panel-hd-cta  "Vidi sve →"            rect=[327.7, 1300.8, 75,   16]   right=402.7
div.kc-panel-row      "Petrović protiv ..."   rect=[35,   1339.8, 367.7, 49]   right=402.7
div.kc-panel-row      "Jovanović — radni ..." rect=[35,   1388.8, 367.7, 49]   right=402.7
div.kc-panel-row      "Milić — naknada ..."   rect=[35,   1437.8, 367.7, 49]   right=402.7
div.kc-panel-row      "DOO Vektor — ..."      rect=[35,   1486.8, 367.7, 49]   right=402.7
div.kc-panel-row      "Stanković — ..."       rect=[35,   1535.8, 367.7, 49]   right=402.7
div.kc-panel-expand   "Još 14 predmeta ▾"     rect=[35,   1588.8, 367.7, 24]   right=402.7
span.kc-panel-hd-cta  "Vidi sve →"            rect=[327.7, 1668.8, 75,   16]   right=402.7
div.kc-panel-row      "Ročište — Petrović..." rect=[35,   1724.0, 367.7, 49]   right=402.7
div.kc-panel-row      "Ročište — Milić ..."   rect=[35,   1773.0, 367.7, 49]   right=402.7
div.kc-panel-row      "Presuda P-1123-..."    rect=[35,   1822.0, 367.7, 49]   right=402.7
div.kc-panel-row      "Ugovor o poslovnoj..." rect=[35,   1871.0, 367.7, 48]   right=402.7
```

Pošto je `overflow-x: auto`, sadržaj se **može** doskrolovati bočno
(`maxScrollLeft = 34`) — ali to znači da dashboard na telefonu ima bočni skrol
unutar sebe, dok stranica u celini nema. Desni deo teksta „Vidi sve →" i desna
ivica svih redova su pri mirovanju van ekrana.

---

## 7. G-006 — plutajući mikrofon stoji IZNAD modala i seče njegov glavni CTA

| scenario | `#intake-btn-next` rect | blokirano | blokator |
|---|---|---|---|
| modal 1920 | `[1363, 1031, 535, 35]` | 7/49 = **14,3%** | `button#vx-voice-fab` z=9990 |
| modal 1366 | `[809, 719, 535, 35]` | 7/49 = **14,3%** | `button#vx-voice-fab` z=9990 |

Modal `.intake-panel` ima `z-index: 2101`; `#vx-voice-fab` ima `9990`. Mikrofon
zato ostaje iznad otvorenog modala i pokriva desnu sedminu dugmeta „Dalje →".
Isto važi i za samu panel-površinu (`.intake-panel` 2,0% blokirano).

Sve **ostale** kontrole zaklonjene u modalnim scenarijima (37 na 1920, 32 na
1366, 19 na 390) jesu kontrole **ispod** modala — 13 stavki bočne trake, globalna
pretraga, 4 brze akcije, redovi inbox-a — i to je **očekivano ponašanje modala**,
ne defekt. Nabrojane su u sirovim podacima radi potpunosti, ali se ne računaju kao
nalaz.

---

## 8. G-007 / G-008 — donja navigacija pokriva sadržaj na početnoj poziciji skrola

### 768×1024, skrol na vrhu

| kontrola | rect | blokirano | blokator |
|---|---|---|---|
| `div.kc-sphere-quad.clickable` „19 Aktivnih predmeta" | `[82.1, 957.5, 89, 98.2]` | **35/35 = 100%** | `#mob-btn-h` (30), `#mob-btn-p` (5) |
| `div.kc-sphere-quad.clickable` „1 Hitnih rokova" | `[171.1, 957.5, 89, 98.2]` | **35/35 = 100%** | `#mob-btn-p` (35) |

(35 od 49 tačaka je testirano; 14 je ispod `innerHeight` pa je izostavljeno.)
`#vx-mobile-nav` = `[0, 964, 768, 60]`, z=9999. Presek sa prvim kvadrantom =
4290 px², sa drugim = 5340 px².

### 390×844, skrol na vrhu

| kontrola | rect | blokirano | blokator |
|---|---|---|---|
| `div.kc-inbox-row` „Priprema za ročište" | `[35, 790.8, 320, 47]` | **49/49 = 100%** | `#mob-btn-p`/`#mob-btn-k`/`#mob-btn-h` |
| `div.kc-inbox-row` „Novi dokument čeka pregled" | `[35, 837.8, 320, 47]` | **7/7 = 100%** | isti |
| `div.kc-inbox-row` „Odgovor na tužbu — rok za 3 dana" | `[35, 743.8, 320, 47]` | 13/49 = 26,5% | `#vx-mobile-fab` (4), `#vx-voice-fab` (2), nav (7) |
| `div.kc-inbox-row` „Rok za žalbu ističe sutra" | `[35, 696.8, 320, 47]` | 4/49 = 8,2% | `#vx-mobile-fab` z=9998 |

**Ovo je oporavljivo skrolovanjem — i provereno je.** Pri maksimalnom skrolu
`.vx-panels-wrap` na 390, nijedan red sadržaja nije zaklonjen; zaklonjeni ostaju
samo `#feedback-fab` i `#vx-voice-fab` (G-001, G-003). Dakle donji padding
skrol-kontejnera **jeste** dovoljan da poslednji sadržaj izađe ispod navigacije.
Problem je samo u tome što se pri mirovanju kontrole nalaze ispod trake.

Za razliku od toga, `#vx-mobile-fab` (z=9998, `[320, 716, 52, 52]`) je *fiksan* i
trajno seče 4–8% dva reda inbox-a bez obzira na skrol.

---

## 9. G-009 — `#vx-back-btn`: 44px nominalno, 30px stvarno

Mapa 7×7 tačaka, 390×844 (`.` = dostupno, ostalo = element koji vraća
`elementFromPoint`):

```
#vx-back-btn  rect = [12, 40.5, 71.7, 44]   →  y: 40.5 … 84.5

red 1 (y≈43.6)  div.vx-topbar | div.vx-topbar | div.vx-topbar | ... x7   ← BLOKIRANO
red 2 (y≈49.9)  .  .  .  .  .  .  .
red 3 (y≈56.2)  .  .  .  .  .  .  .
red 4 (y≈62.5)  .  .  .  .  .  .  .
red 5 (y≈68.8)  .  .  .  .  .  .  .
red 6 (y≈75.1)  .  .  .  .  .  .  .
red 7 (y≈81.4)  div#tab-h | div#tab-h | div#tab-h | ... x7               ← BLOKIRANO

blokirano 14/49 = 28,6%
```

Uzrok je izmeren:

```
div.vx-topbar         rect = [0, 0,  390, 48]     → donja ivica y=48
div#vx-breadcrumb-bar                              → traka visine 30px, y: 48 … 78
div#tab-h             rect = [0, 78, 390, 2271.8] → gornja ivica y=78
button#vx-back-btn    rect = [12, 40.5, 71.7, 44] → y: 40.5 … 84.5
```

Dugme je 44px visoko u traci od 30px: 7,5px prelazi ispod `.vx-topbar`, 6,5px
ispod `#tab-h`. **Stvarna klikabilna visina je 30px, ne 44px.** Identično na
768×1024 (`rect = [20, 40.5, 71.7, 44]`, isto 14/49).

Na desktop širinama (1920/1366/1280/1024) dugme je `[*, 48.5, 71.7, 28]` i
mapa je čista 49/49 — problem postoji samo u mobilnom rasporedu, gde se visina
podigla na 44 a traka ostala 30.

---

## 10. G-010 — bočna traka odseca svoje stavke na 1024

| širina | `.vx-sidebar` rect | `scrollWidth` | `clientWidth` | `overflow-x` | odsečenih stavki |
|---|---|---|---|---|---|
| 1920 | `[0, 0, 240, 1080]` | 239 | 239 | hidden | 0 |
| 1280 | `[0, 0, 240, 800]` | 239 | 239 | hidden | 0 |
| **1024** | `[0, 0, 180, 768]` | **189** | **179** | **hidden** | **2** |

```
div#tab-btn-aiws     "Vindex Intelligence"     rect=[0, 341, 179, 40]   preliv  2px
div#tab-btn-pi-nav   "Portfolio kancelarije"   rect=[0, 717, 179, 40]   preliv 10px
```

Bounding box stavki ostaje unutar ekrana (`right = 179`), pa test „izlazak iz
ekrana" ovo ne prijavljuje — ali sadržaj stavke prelazi kontejner koji ga seče sa
`overflow-x: hidden`. Vizuelno potvrđeno na `shot_1024_top.png`: ikonice tih
stavki su presečene levom ivicom, tekst desnom.

---

## 11. G-011 — dodirne mete ispod 44×44 na 390

| element | put | izmerena veličina | rect |
|---|---|---|---|
| `div#notif-bell` | `div#notif-bell` | **16.0 × 16.0** | `[106.4, 15.5, 16, 16]` |
| `span.kc-panel-hd-cta` „Vidi sve →" | `#kc-panel-aktivni > .kc-panel-hd > span` | **75.0 × 16.0** | `[327.7, 1300.8, 75, 16]` |
| `span.kc-panel-hd-cta` „Vidi sve →" | `#kc-panel-aktivnosti > .kc-panel-hd > span` | **75.0 × 16.0** | `[327.7, 1668.8, 75, 16]` |
| `div.kc-panel-expand` „Još 14 predmeta ▾" | `#kc-panel-aktivni > .kc-panel-expand` | **367.7 × 24.0** | `[35, 1588.8, 367.7, 24]` |
| `button#vx-back-btn` (stvarna, ne nominalna) | `#vx-breadcrumb-bar > button` | **71.7 × 30** (nominalno 44) | `[12, 40.5, 71.7, 44]` |

Ostale kontrole na 390 su ≥44px u obe ose (redovi 47–49px, mobilna navigacija
60px, FAB-ovi 44–52px). Na 768 lista je slična (5 stavki), plus
`div.vx-global-search` = 380 × 28.

Za poređenje, na 1920 ima 26 kontrola ispod 44px u nekoj osi — ali to je
desktop-pokazivač, gde granica od 44px nije relevantna, pa se ne prijavljuje kao
nalaz.

---

## 12. G-012 — donja navigacija 1px preko dna na 768

```
div#vx-mobile-nav   rect = [0, 965, 768, 60]   →  bottom = 1025
innerHeight = 1024
```

Svih 5 dugmadi (`#mob-btn-h`, `#mob-btn-p`, `#mob-btn-kal`, `#mob-btn-k`,
`#mob-btn-mob-more`, svako `153.6 × 60`) završava na `bottom = 1025`. Kozmetički;
poslednji piksel trake je odsečen. (U prolazu sa `is_mobile=true` ista traka je
izmerena kao `[0, 964, 768, 60]` → `bottom = 1024`, pa je razlika u zaokruživanju
zavisna od emulacije uređaja.)

---

## 13. Inventar `position: fixed` / `sticky` i z-index

### Desktop (1920×1080, dashboard)

| element | position | z-index | rect | `pointer-events` |
|---|---|---|---|---|
| `div#cursor` | fixed | 9999 | `[-3, -3, 6, 6]` | none |
| `div#cursor-ring` | fixed | 9999 | `[-14, -14, 28, 28]` | none |
| `button#vx-voice-fab` | fixed | **9990** | `[1840, 1000, 56, 56]` | auto |
| `div#toast-container` | fixed | 9000 | `[492, 1054, 936, 2]` | none |
| `button#feedback-fab` | fixed | **7000** | `[1860, 1020, 42, 42]` | auto |
| `canvas#cv` | fixed | 0 | `[0, 0, 1920, 1080]` | none |

### Mobilni (390×844, dashboard)

| element | position | z-index | rect | `pointer-events` |
|---|---|---|---|---|
| `div#vx-mobile-nav` | fixed | **9999** | `[0, 784, 390, 60]` | auto |
| `button#vx-mobile-fab` | fixed | **9998** | `[320, 716, 52, 52]` | auto |
| `button#vx-voice-fab` | fixed | **9990** | `[18, 780, 48, 48]` | auto |
| `div#toast-container` | fixed | 9000 | `[109.5, 774, 171, 2]` | none |
| `button#feedback-fab` | fixed | **7000** | `[328, 782, 44, 44]` | auto |
| `canvas#cv` | fixed | 0 | `[0, 0, 390, 844]` | none |

### Mobilni sa otvorenim modalom (390×844)

Dodatno:

| element | position | z-index | rect |
|---|---|---|---|
| `div.intake-panel` | fixed | **2101** | `[0, 0, 390, 844]` |
| `div#intake-overlay.open` | fixed | **2100** | `[0, 0, 390, 844]` |

**Sistemski uzrok G-001/G-002/G-003/G-006:** četiri plutajuća sloja
(`9999 / 9998 / 9990 / 7000`) žive u istom donjem uglu bez ijednog pravila koje
ih razdvaja, a modal (`2100/2101`) je numerički **ispod** sva četiri. Nijedan od
plutajućih slojeva se ne sklanja kad se modal otvori.

Slojevi sa `pointer-events: none` (`#toast-container`, `canvas#cv`, `#cursor`,
`#cursor-ring`) ispravno **ne** blokiraju ništa — `elementFromPoint` ih preskače.
To je jedini razlog zašto `canvas#cv` preko celog ekrana nije problem.

---

## 14. Horizontalni skrol — puna tabela

| scenario | `documentElement.scrollWidth` | `innerWidth` | višak |
|---|---|---|---|
| 1920 vrh / dno | 1920 / 1920 | 1920 | 0 / 0 |
| 1440 vrh / dno | 1440 / 1440 | 1440 | 0 / 0 |
| 1366 vrh / dno | 1366 / 1366 | 1366 | 0 / 0 |
| 1280 vrh / dno | 1280 / 1280 | 1280 | 0 / 0 |
| 1024 vrh / dno | 1024 / 1024 | 1024 | 0 / 0 |
| 768 vrh / dno | 768 / 768 | 768 | 0 / 0 |
| 390 vrh / dno | 390 / 390 | 390 | 0 / 0 |
| modal 1920 / 1366 / 390 | 1920 / 1366 / 390 | isto | 0 / 0 / 0 |

**Na nivou dokumenta horizontalnog skrola nema nigde.** Ali to je nedovoljan
test: preliv je izmešten u kontejnere sa sopstvenim `overflow`-om, gde ga
dokument-nivo provera ne vidi:

- `#tab-h` na 390: `scrollWidth 424 > clientWidth 390` (G-005)
- `.vx-body` na 1024: `scrollWidth 931 > clientWidth 844`, `overflow-x: hidden`
  (G-004)
- `.vx-body` na 768: `scrollWidth 819 > clientWidth 768`, `overflow-x: hidden`
- `.vx-sidebar` na 1024: `scrollWidth 189 > clientWidth 179`, `overflow-x: hidden`
  (G-010)

---

## 15. Preklapanja po širini ekrana — pregled

Broji se samo presek dva **interaktivna** elementa gde nijedan nije predak
drugog, i gde bar jedan ima `pointer-events ≠ none`.

| širina | vrh skrola | dno skrola | najveći presek na vrhu |
|---|---|---|---|
| 1920 | **1** | 2 | 1296 px² — `#feedback-fab` × `#vx-voice-fab` |
| 1440 | **1** | 1 | 1296 px² — `#feedback-fab` × `#vx-voice-fab` |
| 1366 | **5** | 7 | 1306 px² — poslednji red inbox-a × `#vx-voice-fab` |
| 1280 | **3** | 6 | 1296 px² — `#feedback-fab` × `#vx-voice-fab` |
| 1024 | **5** | 6 | 1296 px² — `#feedback-fab` × `#vx-voice-fab` |
| 768 | **4** | 13 | 5340 px² — kvadrant sfere × `#mob-btn-p` |
| 390 | **23** | 4 | 3666 px² — red inbox-a × `#mob-btn-p` |
| modal 1920 | 54 | — | 75 106 px² — red inbox-a × `#intake-overlay` (očekivano) |
| modal 1366 | 56 | — | 49 068 px² — red inbox-a × `#intake-overlay` (očekivano) |
| modal 390 | 77 | — | isto (očekivano) |

### Napomena o brojevima na „dnu skrola"

Većina dodatnih preklapanja na dnu (npr. 1366: 7, 768: 13) su redovi sadržaja
koji su **skrolovani ispod** `.vx-topbar` (`[240, 0, 1126, 48]`, z=20) i
`#vx-breadcrumb-bar`. Primer sa 1366:

```
div.vx-global-search    rect=[336.9, 9.5, 380, 28]     z=20
div.kc-panel-row        rect=[281, 15.5, 496, 49]      z=1
presek 380 × 22 = 8360 px²
```

To je normalno ponašanje skrolovanja ispod zaglavlja i **nije defekt** — ali je
navedeno jer ulazi u sirove brojeve. Nalazi G-001…G-012 iz njih su isključeni.

### Preklapanja na 390 (vrh skrola) — svih 23, po veličini

Osam najvećih (ostalih 15 su varijacije istih parova sa manjim presekom):

```
3666 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#mob-btn-p
3666 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#mob-btn-kal
3666 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#mob-btn-k
2064 px²  button#mob-btn-h                          ×  button#vx-voice-fab
2021 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#mob-btn-h
2021 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#mob-btn-mob-more
1804 px²  button#feedback-fab                       ×  button#mob-btn-mob-more
1153 px²  div.kc-inbox-row "Priprema za ročište"   ×  button#vx-voice-fab
```

---

## 16. ŠTA NIJE IZMERENO — i zašto

Ovo je najvažniji deo izveštaja za tumačenje gornjih brojeva.

1. **Prava prijava nije korišćena.** `currentUser`/`currentSession` su ubačeni
   ručno, i `currentUserIsPro` je postavljen na `true`. Sve što zavisi od
   stvarnih entitlement-a (PRO kapije na tabovima `n` i `t`, `vindex.js:2003`)
   nije provereno u produkcionom stanju. Ako neki od tih tabova doda još jedan
   plutajući sloj, on nije u inventaru u odeljku 13.

2. **Svi `/api/*` odgovori su izmišljeni fixture-i.** Oblici su prepisani iz
   `routers/dashboard.py`, `routers/workspace.py`, `routers/inbox.py`, ali
   **količina podataka je moja.** Geometrija dashboard-a zavisi od količine:
   sa više inbox stavki ili dužim nazivima predmeta, više redova pada u zonu
   donje navigacije (G-008), a duži naslovi mogu prelomiti red na dva i pomeriti
   sve ispod. Nalazi vezani za *fiksne* slojeve (G-001, G-002, G-003, G-006,
   G-009, G-012) ne zavise od podataka. Nalazi G-005, G-007, G-008 **zavise** i
   treba ih ponoviti na stvarnom nalogu.

3. **Izmeren je samo tab „Pregled dana" (`h`).** Nisu mereni: Predmeti (`p`),
   Klijenti (`k`), Rokovi i ročišta (`kal`), Vindex Intelligence (`aiws`),
   Sudska praksa (`s`), Dokumenti (`dok`), Zadatci, Finansije, Kancelarija,
   Podešavanja, Portfolio. Svaki od njih ima sopstveni `*_load()` koji povlači
   sopstvene endpoint-e koje nisam fixture-ovao. **Za njih ovaj izveštaj ne tvrdi
   ništa.**

4. **Izmeren je samo jedan modal, i to njegov korak 1/5.** `intakeOtvori()`,
   korak „Klijent". Nisu mereni: koraci 2–5 čarobnjaka (podnožje se možda menja),
   `auth-modal`, `wl-overlay` (waitlist), PRO upgrade modal, `notif` dropdown,
   `docTplOpen()`, brzi akcioni panel (`vx2-qa-item`). Nalaz G-002 se odnosi na
   podnožje čarobnjaka koje je isto na svim koracima (`#intake-panel-footer`), ali
   to nije potvrđeno merenjem na koracima 2–5.

5. **Samo Chromium 148, samo emulacija viewport-a.** Nisu testirani iOS Safari
   ni Android Chrome na stvarnom uređaju. Za nalaz G-002/G-003 to je bitno:
   Safari na iOS-u ima dinamičku donju traku i `safe-area-inset-bottom`, što menja
   stvarnu poziciju `#vx-mobile-nav` i može problem pogoršati (traka viša) ili
   pomeriti.

6. **Samo portret na mobilnom.** 390×844 je merena samo u portretu. Pejzaž
   (844×390) nije meren, a tamo je vertikalni prostor ~390px i preklapanja
   plutajućih slojeva su verovatno gora.

7. **Širina skrolbara.** Chromium u headless režimu koristi overlay skrolbare
   (širina 0). Desktop pretraživač na Windows-u sa klasičnim skrolbarom uzima
   ~15px, što bi **pogoršalo** G-004 (odsecanje „+ Iz dokumenta") i moglo da
   uvede preliv i na 1280. Nalaz G-004 je dakle donja granica, ne gornja.

8. **Font-ovi sa CDN-a su bili dostupni.** Ako u produkciji `unpkg.com`
   (lucide ikone) ili Google Fonts padne, metrike teksta se menjaju i sve širine
   iz odeljka 11 se pomeraju. Nije mereno stanje sa neuspelim CDN-om.

9. **Dva `/api` poziva nisu bila prepoznata prvim stubom**
   (`/api/nacrt/types`, `/api/courts`) i dobila su generički prazan odgovor.
   Ako neki od njih puni kontrolu koja se iscrtava na dashboard-u, ta kontrola u
   merenju nedostaje. Oba su izgledala kao popune za forme u drugim tabovima.

10. **Nije merena tastaturna dostupnost ni redosled fokusa.** Zaklonjena kontrola
    (`#feedback-fab`) je i dalje u tab-redosledu i može se aktivirati tastaturom —
    ovaj izveštaj tvrdi samo da je **nedostupna klikom/dodirom**.

---

## 17. Reprodukcija

Skripte korišćene za merenje (privremene, van repozitorijuma):

| fajl | uloga |
|---|---|
| `serve.py` | pokreće uvicorn sa sanitizovanim okruženjem, izlaz u fajl |
| `stub.js` | `add_init_script` — presretanje `fetch`, fixture odgovori, `__FETCHLOG` |
| `measure.js` | rects, preseci, izlazak iz ekrana, `elementFromPoint` u centru, fixed/z-index |
| `coverage.js` | mreža 7×7 po kontroli → % nedostupne površine + identitet blokatora |
| `run.py` | 7 širina × 2 pozicije skrola + 3 modalna scenarija → `raw.json` |
| `run2.py` | isti scenariji, coverage mreža → `coverage.json` |
| `verify.py` | ciljana provera G-004, G-005, G-009 |

Snimci ekrana: `shot_{1920,1440,1366,1280,1024,768,390}_{top,bottom}.png`,
`shot_{1920,1366,390}_modal.png`.
