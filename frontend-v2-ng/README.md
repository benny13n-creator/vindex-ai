# Vindex V2 NG — prototip 001: početni radni prostor

**Status:** čeka pregled i odobrenje foundera. Ovo NIJE odobren design system.
**Obim:** samo početni desktop ekran (Aktivni predmeti + Zahteva pažnju). Bez backend-a i bez drugih modula.

## Izolacija

- Lokacija u repozitorijumu: `frontend-v2-ng/` (Repository Integration Foundation v1.0). Odobreni prototip razvijen je u `C:\vindex-v2-ng-001` i prenet bez izmena koda.
- **Nije povezan sa produkcijom**: nijedna ruta u `api.py` ne servira ovaj direktorijum (`/static`, `/word_addin` i `/app-v2` imaju sopstvene korene sa proverom putanje). Postojeći V1 (`index.html`, `static/`) i prethodni V2 (`v2/`, `index-v2.html`) nisu dirani i nisu osnova ovog koda.
- Podrazumevano (DEMO) bez backend-a: samo demonstracioni podaci (`src/demo-data.js`). LIVE režim samo čita postojeći `GET /api/predmeti` — vidi „LIVE režim (samo čitanje)“. Nema `.py` fajlova, pa ga `pytest` (`testpaths = tests`) i `compileall` u CI-ju ne vide.
- Iz starog koda preuzeti su samo **nazivi modula** (iz `v2/domain/spaces.js` na `origin/main`, čitano preko `git show`) i princip svetlosnih tačaka. Kod, CSS i design system nisu preuzeti.

## Pokretanje

Potreban je Node 18+ (testirano na 24.15).

```
cd C:\vindex-v2-ng-integration-001\frontend-v2-ng   # ili <repo>\frontend-v2-ng
npm install                      # samo za testove (Playwright + izvori fontova)
npx playwright install chromium  # jednom, ako Chromium nije instaliran
npm run serve                    # http://127.0.0.1:4317/
npm run verify                   # u drugom terminalu: provere + snimci u shots/
npm run verify:pozadina          # ciljane provere pozadine
npm run perf                     # merenje performansi pozadine
npm run verify:refinement        # Refinement 01: tipografija, dugi nazivi, ćirilica, panel, STVARNI zoom 200%
npm run measure -- <oznaka>      # computed vrednosti → shots/refinement-01/measure-<oznaka>.md
```

`verify:refinement` koristi pun Chromium (`channel: "chromium"`) i test-proširenje
`tests/fixtures/zoom-ext/` za stvarni zoom pregledača (`chrome.tabs.setZoom`).

Ekran radi bez interneta, jer su fontovi lokalni.

### Demo scenariji (URL parametri)

| URL | Šta prikazuje |
|---|---|
| `/` | 12 predmeta, 5 stavki u panelu |
| `/?predmeti=veliko` | 240 predmeta (deterministički generisani) |
| `/?predmeti=prazno` | prazna lista |
| `/?paznja=prazno` | prazan panel „Zahteva pažnju“ |

Parametri se mogu kombinovati. Za vraćanje teme i navigacije na početno stanje obriši `localStorage` ključeve `vx-ng-tema` i `vx-ng-nav`.

## LIVE režim (samo čitanje) — Night Sprint 001

> **LIVE PRODUCTION DATA NOT VERIFIED IN THIS SPRINT.** Sav dokaz je nad lokalnim
> fixture-om koji ponavlja ugovor `api.py`; ni produkciona prijava ni produkcioni
> `/api/predmeti` nisu korišćeni.

**DEMO** (podrazumevano, kao do sada): `npm run serve` → `http://127.0.0.1:4317/`.

**LIVE**: dodaj `?rezim=live`. Bilo koja druga vrednost `rezim` je glasna greška
konfiguracije. LIVE nikad ne prikazuje demo podatke — ni kada nešto ne uspe.

- Prijava: koristi se POSTOJEĆA sesija (kanonski Supabase zapis `sb-<ref>-auth-token`
  u `localStorage` istog izvora — isti mehanizam kao produkcioni `/app-v2`). V2 nema
  svoj login, ne kopira i ne osvežava token; istekla sesija je stanje „istekla“.
- Podaci: `GET /api/predmeti?status=aktivan&limit=500&offset=…`, sve strane do
  `ukupno`. Bez `user_id` — pripadnost određuje server iz tokena.

**Lokalni LIVE fixture** (bez backend-a, bez pravih podataka): testovi `npm run verify:live-*`
sami podižu fixture (`tests/fixtures/predmeti-api.mjs`) koji ponavlja ugovor `api.py`.

**Dev API proxy** (samo za lokalni razvoj, protiv LOKALNOG backend-a):

```
VINDEX_LOCAL_API_ORIGIN=http://127.0.0.1:8000 npm run serve
# zatim http://127.0.0.1:4317/?rezim=live
```

> **Bezbednost:** proxy prihvata ISKLJUČIVO loopback cilj (`http://127.0.0.1:PORT` ili
> `http://localhost:PORT`). Za `https://vindex.rs`, Railway, Supabase ili bilo koji drugi
> host server odbija da se pokrene. Prosleđuje samo `GET /api/*` (ostalo je 405) i ne
> ispisuje zaglavlja. Nije produkciona arhitektura.

Pošto lokalni izvor (`127.0.0.1:4317`) nema produkcionu sesiju u `localStorage`, LIVE
protiv lokalnog backend-a prikazuje „Niste prijavljeni“ dok se lokalna sesija ne napravi.

**Šta još NIJE povezano:** panel „Zahteva pažnju“ (u LIVE pošteno kaže da nije povezan),
detalj predmeta, dokumenti, OCR, AI, rokovi i obaveze, ostali moduli navigacije. Sud i
klijent se ne prikazuju jer ih odgovor `/api/predmeti` ne sadrži.

**LIVE testovi:** `verify:live-runtime`, `verify:live-api`, `verify:live-session`,
`verify:live-matters`, `verify:live-states`, `verify:live-isolation`,
`verify:live-matrix` (stvarni Chromium; DEMO piksel-poređenje sa `1eb20976`),
`verify:demo-otisak`.

## Struktura

```
index.html            jedini ekran
src/tokens.css        PRIVREMENI tokeni (Dark podrazumevana, Light alternativa)
src/app.css           raspored i komponente; čita samo tokene
src/app.js            pretraga, sortiranje, tema, navigacija, fioke
src/demo-data.js      demonstracioni podaci + fiksan demo datum 05.10.2026.
fonts/                Source Serif 4 + IBM Plex Sans (OFL-1.1), latinica, latin-ext, ćirilica
serve.mjs             statički server bez zavisnosti (samo 127.0.0.1)
tests/verify.mjs      ponovljive Playwright provere → shots/
```

## Tipografija: privremena zamena

Tiempos Headline i Söhne (Klim) **nisu korišćeni** jer nemamo licencu. Zamene su:

| Uloga | Preferirano | Privremeno | Licenca | Srpski |
|---|---|---|---|---|
| Serif (naslovi, wordmark) | Tiempos Headline | **Source Serif 4** | OFL-1.1 | latinica + latin-ext + ćirilica |
| Sans (rad, tabele, forme) | Söhne | **IBM Plex Sans** | OFL-1.1 | latinica + latin-ext + ćirilica |
| Mono | — | ne koristi se | — | — |

Mono nije potreban jer brojevi predmeta i datumi koriste `tabular-nums` iz Plex Sans. Najmanja veličina teksta je 12px, bez razmaknutih velikih slova i bez dekorativnih naslova.

## Pozadina — potpisni efekat (Signature Identity Pass 01, Phase B)

Aktivni modul je `src/signature-background.js`: doslovan prenos originalne funkcije `drawBg` iz legal-agent `static/vindex.js` (blok `/* CANVAS */`, origin/main).

- Zadržano po odlukama: D2 mreža na 80 px, D3 originalne boje (`0,212,255` tamna i `0,153,187` svetla) i originalne prozirnosti, D4 tekstura samo u ljusci.
- Uklonjeno po odluci D1: radijalni sjaj oko kursora i slušalac `mousemove`.
- Tehničke izmene:
  - tema se čita iz `html[data-theme]`;
  - kretanje je vezano za vreme (1 jedinica = 1 frejm originala pri 60 Hz);
  - platno se skalira za DPR, najviše 2 i najviše 5,18 Mpx;
  - uz reduced-motion se crta jedan statičan frejm;
  - animacija se pauzira dok je stranica skrivena i nastavlja bez skoka;
  - `destroy()` oslobađa sve slušaoce i resurse;
  - seme `window.VX_BG_SEED` služi samo testovima, a bez njega se koristi `Math.random` kao u originalu.
- Prethodna aproksimacija (`src/background.js`) nije runtime zavisnost i nije preneta u repozitorijum.
- `tests/fixtures/original.html` je referentna kopija originalnog koda, bez izmena, i služi samo za poređenje.

Provere: `npm run verify:pozadina` (izlaz u `shots/background-results.md` i `shots/pozadina/`). Merenje: `npm run perf` (izlaz u `shots/perf-results.md`).

## Pretpostavke i demonstraciono ponašanje

- **Svi predmeti, klijenti, brojevi predmeta i obaveze su izmišljeni.** Nazivi sudova su stvarne institucije, ali nijedan zapis nije stvaran predmet. To je označeno na tri mesta: oznaka u gornjoj traci, napomena u panelu i `caption` tabele.
- Panel „Zahteva pažnju“ **ne prikazuje izračunate pravne rokove ni AI nalaze**. Stavke su ručno napisani primeri, relativni datumi se računaju u odnosu na fiksan demo datum 05.10.2026., a prikazuje se najviše 5 stavki.
- „Aktivni predmeti“ prikazuju stanja *Aktivan* i *Na čekanju*. Završeni predmeti nisu deo ove liste.
- Navigacija ima samo postojeće module: Danas, Predmeti, Znanje, Kancelarija i Usklađenost. Klik na neizgrađen modul, predmet ili stavku prikazuje poruku „nije deo ovog prototipa“.
- Sortiranje je determinističko. Za jednake vrednosti redosled određuje broj predmeta, pa interni id. Nazivi se porede srpskim kolatorom, a brojevi numerički.
- Pretraga ne zavisi od dijakritika („djordjevic“ pronalazi „Đorđević“), a sve otkucane reči moraju postojati u predmetu.
- Tastatura: `/` fokusira pretragu, `Esc` briše pretragu ili zatvara fioku, a prvi `Tab` nudi „Preskoči na listu predmeta“.

## Responsive

| Širina | Ponašanje |
|---|---|
| ≥ 1280 | tri kolone: navigacija 232px, lista, panel 296–328px; panel, razmaci i pomoćne kolone rastu fluidno do 1440px, pa kolona naziva nikad ne postaje uža kad se prozor proširi (Refinement 01 uklonio skok na 1360px) |
| 860–1279 | panel postaje fioka (dugme „Zahteva pažnju N“), lista ne gubi širinu |
| < 860 (uklj. 200% zoom) | navigacija je fioka (☰), red tabele se slaže u dva reda |

## Poznata ograničenja

- Vizuelni kvalitet **nije dokazan testovima**. Testovi dokazuju ponašanje i raspored, a o kvalitetu odlučuje pregled snimaka.
- Testirano samo u Chromium-u (Playwright headless). Firefox, Safari i stvarni čitač ekrana (NVDA ili VoiceOver) nisu provereni.
- Zoom od 200% simuliran je odgovarajućom CSS širinom (720×450 i 640×400 pri DPR 2), a ne stvarnim zoom-om browsera.
- Na PNG snimcima se ne vidi pokret; za to služe video snimci u `shots/pozadina/`, a najbolje je pogledati uživo.
- Fioke nemaju sopstveno zaglavlje ni zamku fokusa. Ostatak strane je `inert`, a zatvaraju se tasterom Esc ili klikom van fioke.
- Lista od 240 redova renderuje se cela, bez virtualizacije ili straničenja. Za demo je to dovoljno, ali stvarni registar ima serversko straničenje.
- Boje, razmaci i veličine su privremeni kandidati i čekaju odluku.

## Workspace Refinement Pass 01 (2026-10-05)

Struktura je zaključana; menjani su samo čitljivost, predvidivost i doslednost. Detalji, merenja i snimci pre i posle: `shots/refinement-01/`.

- Tipografija: naslov 26→28px, radni tekst 14→14,5px, sekundarni 13→13,5px, najmanji relevantan tekst 12→13px.
- Naziv predmeta: najviše 2 reda u listi. Ceo naziv ostaje u DOM-u (čitač ekrana, pretraga), u `title` (miš). Pass 01B: i u fokusu tastature ostaje najviše 2 reda (bez pomeranja rasporeda), a panel je fioka ispod 1280 px.
- Gornja traka: uklonjen breadcrumb koji je ponavljao navigaciju i naslov. Wordmark je 20px, srednje težine, bez praćenja slova.
- Lista: naziv, broj, stanje i datum poravnati po osnovnoj liniji prvog reda.
- Pretraga: placeholder navodi i „vrstu“, koja je već bila pretraživa.
- Panel: vreme je neutralno, a amber se koristi samo za ≤ 2 dana. Kada stavki ima više od 5, piše „Prikazano 5 od N“, bez izmišljenog odredišta. Dugme fioke pokazuje ukupan broj. Prazno stanje ne tvrdi da nema obaveza.
