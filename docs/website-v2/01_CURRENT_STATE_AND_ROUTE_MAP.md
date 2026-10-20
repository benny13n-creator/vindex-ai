# 01 — Trenutno stanje i mapa ruta (Website V2)

**Provereno 2026-10-20.**

- `origin/main` = produkcija = `77733e11a1cce9d95b4c893216742fcb396e80ec`. Provera: `/health` vraća `commit: 77733e1`.
- U produkciji je spojen PR #47 (NS4) i primenjene su migracije 138–140. Read-only sonda je pokazala:
  - RPC funkcije 139/140 postoje;
  - kolone `promocija_*` postoje;
  - `anon` dobija 401 za tabele memorije.
- Grana ovog rada: `website/v2-master`, od `77733e11`.

Stari izveštaji (`docs/website/*`, `docs/ns004-site-claims.md`) korišćeni su samo kao pokazivači. Svaka tvrdnja ispod je ponovo izmerena: čitanjem koda na `77733e11` i GET zahtevima nad produkcijom (samo čitanje).

## 1. Javne rute pre ovog rada (produkcija, 2026-10-20)

| Ruta | Odgovor | Izvor |
|---|---|---|
| `/` | 200, „Vindex — predmeti, rokovi i spisi…“ | `site/index.html`, `api.py::root`, `Cache-Control: public, max-age=300` |
| `/kako-radi`, `/sposobnosti`, `/za-advokate` | 301 → `/#rad` | `api.py::_POVUCENE_STRANICE` (NS004) |
| `/bezbednost` | 301 → `/#nacela` | isto |
| `/beta`, `/kontakt` | 301 → `/#pristup` | isto |
| `/web3`, `/vizija`, `/tehnologija` | 301 → `/` | isto |
| `/platforma`, `/funkcionalnosti`, `/razvoj` | 404 | ne postoje |
| `/privacy`, `/terms` | 200 | `privacy.html`, `terms.html` |
| `/security`, `/dpa`, `/ai-disclosure`, `/bezbednosni-list`, `/status` | 200 | `static/*.html` |
| `/robots.txt`, `/sitemap.xml` | 200 | `api.py::robots`, `api.py::sitemap` (domen se izvodi iz zahteva) |

**Devet ranijih stranica nije aktivno.** U `site/` na `77733e11` postoji samo `index.html`. U radnoj kopiji osnivača devet starih fajlova (`site/beta.html` …) stoji kao obrisano u indeksu. Ruta za njih ne postoji. Raniji izveštaj o devet stranica ne opisuje trenutno stanje.

`website/index.html` nije zakačen ni za jednu rutu. Nije aktivan i nije korišćen.

## 2. Ulaz u aplikaciju i ekran sa snimka

| Ruta | Šta se servira (produkcija) |
|---|---|
| `/app` | V2 NG (prekidač `VINDEX_V2_NG_PRIMARY_ENABLED` je uključen). Naslov „Aktivni predmeti · Vindex“. HTML `no-store`. |
| `/app-legacy` | Klasična aplikacija (`index.html`, ~418 KB). Uvek dostupna kao operativna rezerva. |
| `/app-legacy?posle=app` | Isto, uz skript koji posle prijave vraća korisnika na `/app` (`api.py::_V2_NG_POVRATAK_SKRIPT`). |
| `/app-v2`, `/app-v2/*` | Stariji V2 (Wave 1), zaseban dokument. |
| `/v2/preview/` | 307 → `?rezim=live`. Preview je uključen u produkciji. |

**Gde se vidi ekran sa snimka (`#vx-landing`):**

1. Neprijavljen korisnik otvara `/app` (V2).
2. V2 nema sopstvenu prijavu (`frontend-v2-ng/src/session.js` samo čita sesiju). Prikazuje „Niste prijavljeni“ i link „Prijavite se“ na `VxRuntime.prijava` = `/app-legacy?posle=app` (`frontend-v2-ng/src/runtime.js:63`).
3. Na `/app-legacy` bez sesije `static/vindex.js::updateAuthUI` prikazuje `#vx-landing` (`index.html`, ranije linija 4150).

Isto važi za direktnu posetu `/app-legacy`. Linkovi za potvrdu naloga i reset lozinke (`#access_token…`, `#login`, `#register`) vode tamo preko `runtime.js:48`.

Ekran je pre ovog rada nosio sledeće tvrdnje: „847 zakona Srbije pretraženo za manje od 10 sekundi“, „Automatska obaveštenja 7, 2 i 1 dan pre isteka“, „Poverljivi podaci zaštićeni AES-256“, „Beta · Ograničen broj mesta“, „Besplatno tokom beta faze“, „Pravo na dohvat ruke“. Modal prijave je otvarao sa naslovom „15 besplatnih upita“ čak i u režimu prijave.

## 3. Izvori vizuelnog identiteta

| Šta | Izvor | Kako ga sajt dobija |
|---|---|---|
| Tokeni (boje, razmaci, radijus) | `frontend-v2-ng/src/tokens.css` (tamna tema) | iste vrednosti u `site/sajt.css` (`:root`) |
| Fontovi | `frontend-v2-ng/fonts/ibm-plex-sans`, `source-serif-4` (lokalno, @fontsource) | `/v2/site/fonts/*` (StaticFiles mount) |
| Logo (tamna) | `frontend-v2-ng/brand/Vindex_Transparent_EXACT_LOOK.svg` | `/v2/site/brand/…` |
| Logo (svetla) | `frontend-v2-ng/brand/Vindex_Protected_Light_Surface.png` + traka `#F6F7F8` | NS003 odluka osnivača; isto na pre-auth ulazu u svetloj temi |
| Pozadina | `frontend-v2-ng/src/signature-background.js` | `/v2/site/potpis.js` |

**Razlika u tipografiji.** Kanonska pravila i `VINDEX_V2_FOUNDER_EXECUTION_DIRECTION.md` navode Source Serif 4, **Source Sans 3** i JetBrains Mono. Implementacija V2 koristi Source Serif 4 i **IBM Plex Sans** (`tokens.css`). Sajt prati implementaciju V2 i ovim radom se tipografija aplikacije ne menja. Razlika je evidentirana kao odluka osnivača.

`website/index.html` uvodi crveno-zlatnu paletu i nije korišćen.

## 4. Konflikti ruta, keš i service worker

- **Legacy `/sw.js`** (scope `/`, registruje ga `static/vindex.js:16892`):
  - preskače sve `/v2/*` (Z015 §11), pa CSS, JS, fontovi i snimci sajta pod `/v2/site/` nikad ne prolaze kroz njega;
  - HTML navigaciju (i javne stranice) obrađuje network-first, pa korisnik na mreži uvek dobija svežu stranicu. Bez mreže može dobiti keširanu stariju verziju ili legacy `/offline`. To je postojeće ponašanje i za `/`; nije menjano.
  - `CACHE_NAME` je podignut `vindex-v156` → `vindex-v157`, jer se menjaju `index.html` i `static/vindex.css`.
- **HTTP keš.** HTML sajta ima `public, max-age=300`. `sajt.css` i `sajt.js` se pozivaju sa `?v=<heš sadržaja>`, pa nova verzija dobija nov URL. Cloudflare je ispred Rendera (`cf-cache-status: DYNAMIC`), pa HTML nije keširan na ivici.
- **Sudari ruta.** Nove rute (`/kako-radi`, `/funkcionalnosti`, `/za-advokate`, `/razvoj`, `/bezbednost`, `/beta`) ne sudaraju se ni sa jednom API rutom. Proveren je spisak `@app.get`/`add_api_route` u `api.py` i prefiksi rutera. Stare adrese bez stranice (`/sposobnosti`, `/kontakt`, `/platforma`, `/web3`, `/vizija`, `/tehnologija`) daju 301.

## 5. Mehanizam prijave za beta testiranje

- `POST /waitlist/prijava` (`routers/waitlist.py`), bez autentifikacije.
- Polja: `ime` (obavezno), `email` (EmailStr), `firma`, `telefon`, `poruka`. Upis ide u tabelu `waitlist`, a obaveštenje osnivaču e-poštom u pozadini (tiho se preskače bez SMTP-a).
- Produkcija: tabela postoji, **0 redova** (read-only, 2026-10-20). Tok nikad nije korišćen.
- Ponovljena adresa vraća `ok: true` sa porukom koja otkriva da li je nalog aktivan („Vaš nalog je već aktivan“). To je nalaz W-01 u `04_PUBLIC_CLAIMS_REVIEW.md`. Sajt tu poruku ne prikazuje.
- Ruta nema sopstveni `@limiter.limit`, a saglasnost se ne beleži. Backend nije menjan (van obima).
- **Samostalna registracija je otvorena:** `POST /api/register` odmah pravi potvrđen nalog sa 15 kredita (`api.py::register`, `BESPLATNI_KREDITI = 15`). Sajt zato ne tvrdi da se nalozi otvaraju samo kroz beta program.

## 6. Pravne i bezbednosne stranice koje ostaju netaknute

`/privacy`, `/terms`, `/dpa`, `/ai-disclosure`, `/security`, `/bezbednosni-list`, `/status`, `/portal`.

Ovim radom nisu menjane. Sajt linkuje `/privacy`, `/terms`, `/dpa`, `/ai-disclosure` i `/status`. `/security` i `/bezbednosni-list` ostaju dostupni na istim adresama i u sitemap-u, ali ih nova navigacija ne linkuje. Razlog je u nalazu S-01: sadrže tvrdnje koje ovaj rad nije mogao da potvrdi.
