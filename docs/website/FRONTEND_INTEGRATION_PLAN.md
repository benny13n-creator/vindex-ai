# VINDEX AI — PLAN INTEGRACIJE SAJTA (Faza B: IZVODLJIVOST)

Pitanje na koje ovaj dokument odgovara: **da li se blueprint iz Faze A može
izvesti a da se ništa ne polomi, i kojim redom.**

Izvori istine:
`docs/website/VINDEX_WEBSITE_ARCHITECTURE.md` (teren) ·
`docs/website/VINDEX_WEBSITE_CONTENT_MAP.md` (odluke o sadržaju).

**Nijedan produkcioni fajl nije menjan u ovoj fazi.** Sve izmene u `api.py`,
`static/sw.js` i testovima su ovde napisane kao **plan**, ne kao dif koji je
primenjen. Razlog je u §„ŠTA NE SMEM DA URADIM BEZ ODLUKE".

Stanje repoa u kome su svi nalazi mereni: grana `main`, `89996be`.

---

# 1. NAČIN ISPORUKE

## 1.1 Kako se javne stranice serviraju danas — obrazac je jedan i ponovljiv

`api.py:1509-1555`, doslovno:

```python
@app.get("/status")
def status_page():
    path = BASE_DIR / "static" / "status.html"
    return FileResponse(path, headers={"Cache-Control": "no-cache"})

@app.get("/security")
def security_whitepaper():
    path = BASE_DIR / "static" / "security.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/dpa")
def dpa_page():
    path = BASE_DIR / "static" / "dpa.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})
```

Obrazac je: **jedna ruta → jedan HTML fajl na disku → `FileResponse` sa
eksplicitnim `Cache-Control`.** Bez šablona, bez renderovanja, bez stanja.
Devet javnih stranica danas radi tačno tako. **Potvrđeno: isti obrazac se može
ponoviti onoliko puta koliko sajt ima stranica, bez ijednog novog mehanizma.**

Dve varijante istog obrasca postoje u kodu:
- `privacy` / `terms` / `pricing` dodaju `if path.exists()` i vraćaju 404 JSON
  ako fajla nema (`api.py:1509-1514`, `1542-1547`, `1550-1555`);
- `status` / `security` / `dpa` / `ai-disclosure` / `bezbednosni-list` ne
  proveravaju postojanje (`api.py:1516-1539`) — ako fajl nestane, ruta baca
  izuzetak i global handler vraća 500 JSON.

Za nove stranice se preuzima **varijanta sa `path.exists()`** — nedostajuća
stranica sajta treba da bude 404, ne 500.

## 1.2 Jedan fajl ili više — preporuka: **VIŠE**

Argumenti su iz koda i iz `CONTENT_MAP §3`, ne iz stila:

| Za više fajlova | Dokaz |
|---|---|
| Podnožje mora da linkuje 6 pravnih stranica koje već imaju **sopstvene rute** | `static/ai-disclosure.html:36-40`, `static/bezbednosni-list.html:78` — te stranice već međusobno linkuju `/terms`, `/privacy`, `/dpa`, `/security`. Sajt koji je jedna stranica sa sidrima ne može da se uklopi u tu mrežu. |
| `CONTENT_MAP §3` traži 9 stranica različitog prioriteta (P0/P1) | Faza D isporučuje početnu, faza E ostalo. Jedan fajl znači da se ništa ne može isporučiti pre nego što je sve gotovo. |
| Postojeći obrazac je već „jedna ruta = jedan fajl" | 9 stranica, 9 fajlova, 0 izuzetaka (§1.1) |
| Deep-link i deljenje | „Preuzmite bezbednosni list" i „Kako radi" moraju biti URL-ovi koji se mogu poslati, ne `#sidra` |

Argument protiv (jedan fajl = nema duplikacije CSS-a) rešava se zajedničkim
stilom, v. §1.4.

## 1.3 Gde fizički stoje fajlovi — preporuka: **`site/`**, ne `static/`, ne koren

Danas su javne stranice na dva mesta:

| Lokacija | Fajlovi | Posledica |
|---|---|---|
| koren repoa | `landing.html`, `privacy.html`, `terms.html`, `pricing.html`, `client_portal.html` | jedan javni URL po stranici |
| `static/` | `security.html`, `dpa.html`, `ai-disclosure.html`, `bezbednosni-list.html`, `status.html` | **dva javna URL-a po stranici** |

**Nalaz.** `api.py:815-817` montira **ceo** `static/` direktorijum:

```python
if os.path.exists(BASE_DIR / "static"):
    app.mount("/static", _StaticFiles(directory=str(BASE_DIR / "static")), name="static")
```

Zato je `static/security.html` dostupan i kao `/security` i kao
`/static/security.html`. `robots.txt` (`api.py:2329-2334`) glasi
`User-agent: *\nAllow: /\nDisallow: /api/\n` — dakle **obe verzije su
indeksibilne**, sa različitim `Cache-Control` (`3600` na ruti,
`86400` na `/static/`, `api.py:1141-1142`). To je duplikat sadržaja koji niko
nije naručio.

Novi sajt ne sme da doda još takvih parova. Provereno: montirana su **samo**
`static/` i `integrations/word_addin` (`api.py:817`, `api.py:826-831`). Bilo koji
drugi direktorijum je nedostupan direktno i vidljiv **isključivo** kroz rutu.

Zato: **nove stranice idu u novi direktorijum `site/`.**
`.gitignore` ga ne isključuje (provereno — nema pravila za `site`), a
`Dockerfile:17` je `COPY . .` bez `.dockerignore` fajla (`.dockerignore` ne
postoji), pa novi direktorijum ulazi u produkcioni image bez ijedne izmene
build konfiguracije.

Zajednički resursi sajta (CSS, eventualni fontovi, SVG, OG slika) **moraju** u
`static/`, jer je to jedini montiran direktorijum.

## 1.4 Kako se deli stil bez build alata — dve opcije

**Opcija A — sve inline u svakoj stranici.** Tačno ono što `landing.html` radi
danas (49,9 KB, jedan `<style>`, nula referenci na `/static/`). Prednost: nula
novih mehanizama, nula problema sa verzionisanjem, stranica je uvek konzistentna
sama sa sobom. Mana: ~20 KB dizajn sistema × 9 stranica, održavanih rukom.
**To je tačno bolest koju je Faza A imenovala kao R14 („sedam vizuelnih
sistema").** Devet kopija istih tokena će se razići.

**Opcija B (preporučeno) — jedan `static/site.css`, uključen iz svake stranice.**
Prednost: jedan izvor istine za tokene. Mana: mora se rešiti verzionisanje, jer
`static/*.css` dobija `public, max-age=3600, stale-while-revalidate=86400`
(`api.py:1139-1140`) i **dodatno** prolazi kroz service worker
stale-while-revalidate (`sw.js:116-129`) — bez `?v=` posetilac može gledati
stari CSS na novom HTML-u.

Mehanizam za to **već postoji i već je testiran**, samo je vezan isključivo za
`index.html` (`api.py:1484-1495`):

```python
def _load_index_html() -> bytes:
    ...
    content = _re.sub(r'\?v=\w+', f"?v={_GIT_HASH}", content)
```

Predlog je da se isti mehanizam izdvoji u `_serve_site_page(ime)` i primeni na
stranice sajta — v. dif-plan u §2.2. To je ~15 linija koje recikliraju postojeći,
dokazan kod, umesto da uvode novi.

## 1.5 Build alat — **NE. Nema ga, i ne uvodi se.**

Dokaz, ne pretpostavka:

| Provera | Rezultat |
|---|---|
| `package.json` bilo gde u repou (`find . -maxdepth 3 -name package.json`, bez `node_modules`) | **0 pogodaka** |
| `package-lock.json`, `webpack.config.js`, `vite.config.js`, `rollup.config.js`, `tsconfig.json` u korenu | **ne postoje** |
| `npm` / `yarn` / `pnpm` korak u `.github/workflows/` | **0 pogodaka** (jedina pojava reči `node` je `-x node_modules` u `compileall` isključenju, `production-runtime.yml:55,158`) |
| `node` u repou uopšte | samo kao **sintaksni proveravač** u testovima: `node --check static/vindex.js` (`tests/test_frontend_undefined_globals.py:277`), `tests/test_word_addin_taskpane.py:76,88` |
| Kako se danas isporučuje frontend | `static/vindex.js` je 1,26 MB **ručno pisanog** ES5; `landing.html` je ručno pisan HTML sa inline `<style>`; `Dockerfile` nema nijedan frontend korak |

**Zaključak: sajt mora biti čist HTML/CSS/JS bez ijednog koraka izgradnje.**
Nema Tailwind-a, nema Sass-a, nema PostCSS-a, nema minifikacije. Ako se poželi
minifikacija, ona bi bila prvi build korak u istoriji repoa i zahtevala bi
odluku vlasnika, novi CI job i novu klasu kvarova („zaboravljeno je pokrenuti
build"). Ne preporučuje se.

Kompresija na žici ionako postoji: `app.add_middleware(GZipMiddleware,
minimum_size=1000)` (`api.py:959`) — svaka stranica preko 1 KB ide gzip-ovana.
Minifikacija bi preko gzip-a donela jednocifreni procenat.

---

# 2. RUTIRANJE — DIF-PLAN ZA `api.py`

**Ništa od ovoga nije primenjeno.** Ovo je specifikacija izmene.

## 2.1 Nove rute za stranice sajta

Umetnuti **posle** `api.py:1547` (posle `/terms`, gde su ostale javne stranice),
tako da sve javne HTML rute ostanu u jednom bloku:

```python
# ─── Sajt ─────────────────────────────────────────────────────────────────────
# Obrazac je identičan postojećim javnim stranicama (/security, /dpa, …):
# jedna ruta → jedan fajl u `site/` → FileResponse sa eksplicitnim Cache-Control.
# `site/` NIJE montiran (jedini mount-ovi su /static i /word_addin, api.py:817,826),
# pa svaka stranica ima TAČNO JEDAN javni URL — za razliku od static/security.html
# koji je dostupan i kao /security i kao /static/security.html.

_SITE_CACHE = "public, max-age=300"

def _site_page(ime: str):
    path = BASE_DIR / "site" / f"{ime}.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": _SITE_CACHE})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})

@app.get("/kako-radi")
def site_kako_radi():        return _site_page("kako-radi")

@app.get("/bezbednost")
def site_bezbednost():       return _site_page("bezbednost")

@app.get("/beta")
def site_beta():             return _site_page("beta")

@app.get("/kontakt")
def site_kontakt():          return _site_page("kontakt")

@app.get("/pravno")
def site_pravno():           return _site_page("pravno")

@app.get("/tehnologija")
def site_tehnologija():      return _site_page("tehnologija")

@app.get("/za-advokate")
def site_za_advokate():      return _site_page("za-advokate")

@app.get("/vizija")
def site_vizija():           return _site_page("vizija")
```

Napomene uz predlog:

- **Zašto samo `GET`, bez `HEAD`.** Postojeće stranice sadržaja (`/security`,
  `/dpa`, `/terms`, …) su isključivo `GET`. `HEAD` je dodat samo na `/` i
  `/health` (`api.py:1500-1501`, `1558-1559`) — tamo gde ga koriste monitori.
  Nove stranice ne treba da odstupaju od obrasca; ako se uvede spoljni monitor,
  on gađa `/health`.
- **Zašto `site_*` prefiks u imenima funkcija.** SlowAPI podrazumevani limit se
  vezuje za `modul.ime_funkcije` (`slowapi.extension.Limiter.__evaluate_limits`:
  `limit_scope = lim.scope or endpoint`, gde je `endpoint` puno ime funkcije).
  Različita imena → **odvojeni brojači po stranici**, što je ono što želimo.
- **`/bezbednost` vs postojeći `/security`.** `/security` servira postojeći
  whitepaper (`static/security.html`). Nova stranica `/bezbednost` je stranica
  **sajta** koja objašnjava i **linkuje** whitepaper. Dva različita dokumenta,
  dva URL-a, bez preklapanja. Alternativa (preimenovati `/security`) bi pokvarila
  linkove u `static/bezbednosni-list.html:78` i `static/ai-disclosure.html`.

## 2.2 Opciono — zajednički CSS sa automatskim `?v=` (Opcija B iz §1.4)

Ako se ide na zajednički `static/site.css`, umesto `_site_page` iznad:

```python
_SITE_HTML_CACHE: dict[str, bytes] = {}

def _serve_site_page(ime: str):
    """Stranica sajta iz `site/`, sa `?v=` prepisanim u commit SHA.

    Isti mehanizam kao `_load_index_html` (api.py:1484-1492), samo primenjen na
    stranice sajta. Bez njega `static/site.css` visi na `max-age=3600` +
    SW stale-while-revalidate, pa nov CSS ne stiže do vraćenog posetioca.
    """
    from fastapi.responses import Response
    kes = _SITE_HTML_CACHE.get(ime)
    if kes is None:
        path = BASE_DIR / "site" / f"{ime}.html"
        if not path.exists():
            return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})
        kes = _re.sub(r'\?v=\w+', f"?v={_GIT_HASH}",
                      path.read_text(encoding="utf-8")).encode("utf-8")
        _SITE_HTML_CACHE[ime] = kes
    return Response(content=kes, media_type="text/html",
                    headers={"Cache-Control": _SITE_CACHE})
```

Cena: stranice se učitavaju u memoriju pri prvom zahtevu i ostaju tamo do
restarta (ukupno < 500 KB). Izmena fajla na disku bez restarta se ne vidi — što
je već ponašanje `/app` (`api.py:1494`), pa nije nova klasa iznenađenja.

## 2.3 `/` — jedina ruta bez `Cache-Control`

Sadašnje stanje (`api.py:1500-1506`):

```python
@app.get("/")
@app.head("/")
def root():
    path = BASE_DIR / "landing.html"
    if path.exists():
        return FileResponse(path)
    return {"status": "ok", "servis": "Vindex AI"}
```

`FileResponse(path)` bez `headers=`. Middleware `security_headers`
(`api.py:1131-1142`) postavlja `Cache-Control` **samo** za putanje koje počinju
sa `/static/`. Rezultat: `/` nema politiku keširanja; oslanja se isključivo na
`ETag`/`Last-Modified` koje Starlette generiše.

**Predlog: `public, max-age=300`.**

Obrazloženje vrednosti — postojeći opseg u repou je `no-cache` (`/status`,
`/app`), `3600` (`/security`, `/dpa`, `/ai-disclosure`, `/bezbednosni-list`,
`/pricing`) i `86400` (`/privacy`, `/terms`). Početna nije ni jedno ni drugo:

- `86400` i `3600` su pogrešni jer HTML sajta **nema hash u imenu** i nema
  build korak. Jedina poluga protiv zastarelosti je HTTP keš. Sa `3600`,
  ispravka teksta u hero sekciji ne stiže do vraćenog posetioca do sat vremena,
  bez ijednog načina da se to ubrza.
- `no-cache` je nepotrebno strog za marketinšku stranicu i tera revalidaciju na
  svaku navigaciju.
- `300` znači: greška u tekstu se ispravlja i vidi u roku od pet minuta, a
  server i dalje ne dobija zahtev na svako otvaranje.

Ista vrednost (`_SITE_CACHE`) ide i na sve nove stranice — jedna politika za
ceo sajt, jedna konstanta.

## 2.4 Uklanjanje `/pricing`

Sadašnje stanje (`api.py:1550-1555`), ruta je javna, `include_in_schema=False`,
servira `pricing.html` (31 KB, 4 plana sa cenama). `CONTENT_MAP §6.2` je odlučio
da se uklanja.

**Ko linkuje `/pricing` — iscrpna pretraga:**

| Gde je traženo | Obrazac | Rezultat |
|---|---|---|
| `*.py`, `*.html`, `*.js`, `*.json`, `*.yml`, `*.yaml` u celom repou | `href="/pricing`, `/pricing"` | **2 pogotka, oba bezopasna** |
| — `api.py:1550` | definicija same rute | to je ono što se uklanja |
| — `pricing.html:9` | `<link rel="canonical" href="https://vindex-ai.com/pricing">` | u fajlu koji prestaje da se servira |
| `tests/` | `pricing` | **0 pogodaka na rutu.** Svi pogoci su `GET /api/plan/pricing-matrix` (`tests/test_business_groups.py:202-286`) i `tests/test_tier_config.py:7` — **druga ruta, drugi ruter (`routers/plans.py:118`), nema veze sa `/pricing`** |
| `static/vindex.js` | `pricing` | funkcija `pricing_kontakt(...)` (`:2304, 8107, 8156`) i `pricing-tiers-grid`/`pricing-groups-grid` (`:8052-8156`) — **sve unutar aplikacije**, ne linkuje rutu |
| `index.html` | `pricing` | `id="pricing-tiers-grid"` (`:254`), `id="pricing-groups-grid"` (`:267`) — DOM id-jevi u aplikaciji |
| podnožja postojećih pravnih stranica | `href="/` | `static/ai-disclosure.html:36-40,144-146`, `static/bezbednosni-list.html:78` — linkuju `/`, `/terms`, `/privacy`, `/dpa`, `/security`, `/ai-disclosure`. **Nijedno ne linkuje `/pricing`.** |

**Zaključak: `/pricing` je ostrvo. Nijedan link, nijedan test, nijedan CI job ga
ne dodiruje.** Uklanjanje je čisto brisanje 6 linija:

```python
# UKLONITI api.py:1550-1555 u celini
@app.get("/pricing", include_in_schema=False)
def pricing_page():
    path = BASE_DIR / "pricing.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})
```

Posle uklanjanja `/pricing` vraća **404 sa FastAPI podrazumevanim telom**
(`{"detail":"Not Found"}`), ne Vindex JSON oblik. To je isto ponašanje kao svaka
druga nepostojeća putanja — prihvatljivo, i ne traži dodatni kod.

**`pricing.html` se briše sa diska** u istom commit-u. Ako ostane, fajl je i
dalje u produkcionom image-u (`COPY . .`) ali **nije javno dostupan** — nije u
`static/`, pa ga nijedan mount ne servira. Provereno. Ostavljanje fajla je
prihvatljivo; brisanje je čistije i sprečava da ga neko za pola godine „vrati
jer već postoji".

## 2.5 `robots.txt` i `sitemap.xml`

**`robots.txt` postoji** kao inline odgovor (`api.py:2329-2334`):

```python
@app.get("/robots.txt")
def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /api/\n",
        media_type="text/plain",
    )
```

Test koji ga čuva: `tests/test_api_security.py:121-126` traži `"User-agent" in
r.text` i `"/api/" in r.text`. **Svaka predložena izmena mora zadržati oba
niza** — obe predložene verzije ispod ih zadržavaju.

**`sitemap.xml` ne postoji** — ni kao fajl (`sitemap.xml`, `static/sitemap.xml`
— ne postoje), ni kao ruta (0 pogodaka za `sitemap` u `*.py`).

Predlog izmene `robots.txt`:

```python
@app.get("/robots.txt")
def robots(request: Request):
    base = str(request.base_url).rstrip("/")
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /app\n"        # aplikacija iza prijave — nema šta da se indeksira
        "Disallow: /portal\n"     # klijentski portal, pristup tokenom
        "Disallow: /offline\n"    # servira isti index.html kao /app
        "Disallow: /word_addin/\n"
        f"Sitemap: {base}/sitemap.xml\n",
        media_type="text/plain",
    )
```

Predlog nove rute `sitemap.xml` (apsolutni URL-ovi se grade iz `request.base_url`
— **time se izbegava hardkodovanje domena**, koji još nije odlučen, v. R20 u
Fazi A: `vindex.rs` u `landing.html:1056,1095` vs `vindex-ai.com` u
`pricing.html:9`):

```python
@app.get("/sitemap.xml")
def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    putanje = ["/", "/kako-radi", "/bezbednost", "/beta", "/kontakt", "/pravno",
               "/tehnologija", "/za-advokate", "/vizija",
               "/security", "/dpa", "/ai-disclosure", "/bezbednosni-list",
               "/privacy", "/terms", "/status"]
    url = "".join(f"<url><loc>{base}{p}</loc></url>" for p in putanje)
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{url}</urlset>',
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )
```

**Ne rešava se ovde:** duplikat `/security` ↔ `/static/security.html` (§1.3).
Ispravno rešenje je `<link rel="canonical" href="/security">` **u samim
postojećim stranicama** u `static/`. To je izmena produkcionih fajlova i traži
odluku (v. poslednju sekciju). `Disallow: /static/` **nije** rešenje — blokirao
bi i CSS/JS, što šteti indeksiranju.

---

# 3. SERVICE WORKER — NAJVEĆI RIZIK, ALI UŽI NEGO ŠTO IZGLEDA

## 3.1 Šta SW tačno kešira i po kojoj strategiji

`static/sw.js`, `CACHE_NAME = "vindex-v123"` (`:4`), scope `/`
(`api.py:2466-2474`, header `Service-Worker-Allowed: /`).

| Šta | Strategija | Linija | Upisuje u keš? |
|---|---|---|---|
| `PRECACHE`: `/offline`, `supabase.min.js`, `manifest.json`, 2 ikone | precache pri `install` | `:6-12, 15-22` | da, pri instalaciji |
| Supabase domeni | ne dira se | `:39-44` | ne |
| `/api/`, `/strategija/`, `/billing/`, … (12 prefiksa) | network-first, fallback 503 JSON | `:47-74` | **ne** |
| `fonts.googleapis.com`, `fonts.gstatic.com`, cdnjs, jsdelivr, unpkg | **cache-first, bez isteka** | `:77-97` | **da** |
| **HTML navigacija (`mode === "navigate"`)** — dakle i `/` i svaka nova stranica sajta | **network-first, ali svaki uspešan odgovor se UPISUJE** | `:100-113` | **da** |
| ostali statički fajlovi (JS, CSS, slike) | stale-while-revalidate | `:116-129` | da |

Brisanje starog keša se dešava isključivo u `activate`, i to samo za ključeve
različite od trenutnog (`:24-30`):

```js
keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
```

**`CACHE_NAME` je jedini brisač koji postoji.**

## 3.2 Ko je uopšte pogođen — SW se registruje SAMO iz aplikacije

Ovo je nalaz koji sužava rizik i koji Faza A nije izričito izvela.

Registracija postoji na tačno jednom mestu — `static/vindex.js:16470-16472`:

```js
window.addEventListener('load', function() {
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
```

`static/vindex.js` učitava **samo `index.html` (`/app`)**. `landing.html` nema
nijednu referencu na `/static/` (potvrđeno u Fazi A §4.3 i ponovo ovde: grep
`serviceWorker` u `landing.html` → 0 pogodaka).

Posledica, po tipu posetioca:

| Posetilac | Ima SW? | Šta vidi kad zamenimo sajt |
|---|---|---|
| Nikad nije otvorio `/app` (svaki nov posetilac sajta) | **NE** | **Nov sajt odmah.** Nema keša, nema SW-a. |
| Otvorio je `/app` bar jednom (beta korisnici, osnivač, tester) | **DA**, scope `/` | Navigacija je **network-first** (`:100-113`) — na ispravnoj mreži dobija **nov** sajt odmah, a odgovor se upisuje preko starog unosa u kešu. Star sajt vidi **samo** ako mreža otkaže ili je toliko spora da `fetch` padne — tada `caches.match(event.request)` vraća keširanu staru verziju. |

**Koliko dugo star sajt može da opstane:** neograničeno, ali samo u offline /
mrežno-neuspešnom scenariju, i samo dok se `CACHE_NAME` ne promeni. Nakon bump-a
i prve uspešne aktivacije novog SW-a, ceo `vindex-v123` keš se briše i taj
scenario nestaje.

**Skriveniji problem od HTML-a: fontovi.** Google Fonts idu **cache-first bez
isteka** (`:77-97`). Za korisnika koji ima SW, promena skupa fontova (drugi
težinski rezovi, druga porodica) **neće se videti nikada** dok se `CACHE_NAME` ne
promeni. Ako novi sajt koristi drugačiji `?family=` string, on ide na novi URL i
biće preuzet — ali stari fajlovi ostaju u kešu zauvek. To je još jedan razlog za
bump, i argument za samostalno hostovanje fontova (§6.2).

## 3.3 Tačan postupak

Obavezno, u **istom commit-u** koji zamenjuje sajt:

1. **`static/sw.js:4`: `vindex-v123` → `vindex-v124`.**
   Ovo je jedini korak koji je bezuslovno obavezan. Bez njega: keširani stari
   `/`, keširani stari fontovi, keširani stari `static/site.css` ostaju kod
   svakog korisnika koji je ikada otvorio `/app`.

2. **NE dodavati stranice sajta u `PRECACHE` (`sw.js:6-12`).**
   Obrazloženje: `PRECACHE` se preuzima pri **svakoj** instalaciji SW-a, za
   **svakog** korisnika aplikacije. Dodavanje 9 marketinških stranica znači da
   svaki advokat koji otvori `/app` preuzme ceo marketinški sajt koji nikada
   neće otvoriti. Navigacioni handler (`:100-113`) ionako kešira stranicu pri
   prvoj poseti — funkcionalnost se ne dobija, trošak se dobija.
   `/offline` u `PRECACHE` ostaje jer je fallback za svaku neuspelu navigaciju.

3. **Razmotriti `/offline` fallback za posetioca sajta.**
   `sw.js:110-111`: kad navigacija padne i nema keširane verzije, vraća se
   `caches.match("/offline")` → `api.py:2483-2485` → `index.html`, tj. **ceo
   app shell aplikacije**. Posetilac koji je offline otvorio `/kako-radi` dobija
   ekran aplikacije. Nije regresija (postoji i danas), ali je vidljivo pogrešno
   na sajtu. Ispravka bi bila zasebna, mala offline stranica sajta — **zaseban
   zadatak, ne blokira isporuku.**

4. **Ne menjati strategije u `sw.js`.** Network-first za navigaciju je već
   ispravan izbor za sajt. Jedina izmena je broj u liniji 4.

## 3.4 `FRONTEND_ARTEFAKTI` — preporuka, bez izmene testa

`tests/test_wave11_release_identity.py:52`:

```python
FRONTEND_ARTEFAKTI = ("static/vindex.js", "index.html")
```

`_prekrsaj` (`:111`) radi **tačan presek putanja** (`set(izmenjeni) &
set(FRONTEND_ARTEFAKTI)`), ne glob i ne prefiks. Zato:

**`landing.html` danas NIJE praćen.** Commit koji zameni sajt i zaboravi bump
proći će zeleno — a SW keširа `/` (`sw.js:100-113`). To je rupa u pokrivenosti
koju je Faza A već imenovala (§6.4), i koju novi, višestranični sajt **širi**:
9 novih fajlova koji se keširaju, nijedan praćen.

**Preporuka (NE primenjena):**

```python
FRONTEND_ARTEFAKTI = (
    "static/vindex.js",
    "index.html",
    "landing.html",        # SW keširа `/` kao navigaciju (sw.js:100-113)
    "static/site.css",     # ako se ide na Opciju B iz §1.4
    "site/kako-radi.html",
    "site/bezbednost.html",
    "site/beta.html",
    "site/kontakt.html",
    "site/pravno.html",
    "site/tehnologija.html",
    "site/za-advokate.html",
    "site/vizija.html",
)
```

**Provereno da to ne razbija postojeće kontrole detektora** (to je bio pravi
rizik, jer se ovaj fajl oslanja na dva istorijska commit-a):

| Test | Zašto i dalje prolazi |
|---|---|
| `test_ng_detektor_hvata_stvarni_istorijski_propust` (`:202`) | commit `f87f9e45` dira `static/vindex.js`; proširenje liste može samo **dodati** stavke u `dirnuti`. Asercije `"vindex-v123" in problem` i `"static/vindex.js" in problem` ostaju tačne — `static/vindex.js` je i dalje u poruci. |
| `test_ng_detektor_ne_prijavljuje_uredan_bump` (`:226`) | commit `966e0e77` **jeste** podigao v122 → v123, pa `_prekrsaj` vraća `None` bez obzira koliko fajlova je u preseku. |
| `test_ng_backend_commit_ne_trazi_bump` (`:239`) | poziva `_prekrsaj` sa `{"routers/strategija.py", "tests/test_x.py"}` — presek je prazan i ostaje prazan. |
| `test_cache_name_odgovara_obrascu_vindex_v_broj` (`:140`) | ne dira listu. |

**Cena preporuke:** svaka buduća izmena teksta na sajtu tražiće bump
`CACHE_NAME` u istom commit-u. To je namerno — to je tačno stanje koje
sprečava da vraćeni korisnik vidi stari sajt. Alternativa (održavati listu
ručno pri svakoj novoj stranici) je krhka; ako se lista proširi, treba je
proširiti **odjednom sa svim stranicama**, jer polovična lista daje lažan
osećaj pokrivenosti.

**Nisam izmenio ovaj test.** Izmena testa je izmena postojećeg fajla i izlazi iz
mog opsega.

---

# 4. BETA FORMA — `POST /waitlist/prijava`

Izvor: `routers/waitlist.py`, registrovan u `api.py:648` i `api.py:745`.

## 4.1 Šta prima

`routers/waitlist.py:60-80`:

```python
class WaitlistPrijava(BaseModel):
    ime:     str
    email:   EmailStr
    firma:   str = ""
    telefon: str = ""
    poruka:  str = ""
```

| Polje | Obavezno | Validacija | Gde je definisana |
|---|---|---|---|
| `ime` | **DA** | `.strip()`, ne sme biti prazno, `len ≤ 120` | `:67-75` |
| `email` | **DA** | `EmailStr` (paket `email-validator>=2.1.0`, `requirements.txt:26`); na endpointu se dodatno radi `.strip().lower()` (`:149`) | `:63, 149` |
| `firma` | ne | `(v or "").strip()[:500]` — **tiho se seče**, ne baca grešku | `:77-80` |
| `telefon` | ne | isto | `:77-80` |
| `poruka` | ne | isto | `:77-80` |

**Dodatna polja se tiho ignorišu.** Pydantic v2 podrazumevano ponašanje je
`extra="ignore"`, a model ne postavlja `model_config`. Praktična posledica:
forma **sme** da pošalje honeypot polje — backend ga primi i baci. To znači da
honeypot mora biti proveren **na klijentu** (ne šalji zahtev ako je popunjeno),
jer backend na osnovu njega ne može da odbije. Radi bez ijedne izmene backenda.

## 4.2 Šta vraća

**Uspeh — uvek HTTP 200, tri različite poruke** (`:157-180`):

| Slučaj | Telo |
|---|---|
| nova prijava | `{"ok": true, "poruka": "Prijava primljena! Javićemo vam se čim otvorimo pristup."}` |
| email već na listi, `status != "active"` | `{"ok": true, "poruka": "Već ste na listi! Javićemo vam se uskoro."}` |
| email već na listi, `status == "active"` | `{"ok": true, "poruka": "Vaš nalog je već aktivan. Prijavite se!"}` |

Forma treba da **prikaže `poruka` iz odgovora**, a ne sopstveni fiksni tekst —
inače korisnik koji se već prijavio dobija poruku kao da je prvi put.

**Greške:**

| Situacija | Status | Telo | Jezik |
|---|---|---|---|
| nevalidan/prazan `ime`, nevalidan `email`, nedostaje polje | **422** | FastAPI podrazumevani `{"detail": [ … ]}` | **engleski** — nema `RequestValidationError` handlera (`api.py` registruje samo `Exception` na `:891` i `RateLimitExceeded` na `:575`) |
| prekoračen rate limit | **429** | `{"greska": "Previše zahteva. Sačekajte nekoliko sekundi i pokušajte ponovo."}` | srpski (`api.py:568-573`) |
| Supabase nedostupan / tabela `waitlist` ne postoji | **500** | JSON iz `global_exception_handler` (`api.py:891`) | srpski |

**Posledica za dizajn forme: 422 telo se NE SME prikazivati korisniku** — bio bi
engleski Pydantic ispis. Forma mora da validira na klijentu (`required`,
`type="email"`, `maxlength="120"`) i da za 422 prikaže sopstvenu srpsku poruku.

## 4.3 Rate limit i zaštita od bota

- **Nema `@limiter.limit()` dekoratora** na ruti — provereno, `routers/waitlist.py`
  ne uvozi `limiter`.
- Zato važi **podrazumevani limit iz `SlowAPIMiddleware`**
  (`app.add_middleware(SlowAPIMiddleware)`, `api.py:581`), a to je
  `_DEFAULT_LIMITS = ["60/hour"]` (`shared/rate.py:44`).
- Ključ je **prava IP adresa klijenta**: `_get_real_ip` čita krajnje levu
  vrednost iz `X-Forwarded-For` (`shared/rate.py:49-58`) — dakle iza Render
  proxy-ja se ne grupišu svi korisnici pod jednim identitetom.
- Opseg je **po ruti**, ne globalan po IP-u: `limit_scope = lim.scope or endpoint`
  gde je `endpoint` puno ime funkcije (`slowapi.extension.__evaluate_limits`).
  Dakle 60/h za `routers.waitlist.waitlist_prijava`, odvojeno od 60/h za `/`.
- Bez `REDIS_URL` limiter je čist in-memory (`shared/rate.py:88`), dakle
  **po gunicorn radniku** — stvarni limit je `60 × broj radnika`.
- **Statički fajlovi nisu limitirani**: `_check_request_limit` odustaje kad je
  ime handler funkcije prazno (`endpoint_func_name == ""`), a mount-ovane rute
  (`StaticFiles`) nemaju `.endpoint` atribut, pa `_find_route_handler` vraća
  `None`. Provereno u instaliranom `slowapi`. Sajt sa mnogo `/static/` resursa
  neće trošiti kvotu.

**Zaštite od bota nema nikakve drugačije od tog limita:** nema CAPTCHA-e, nema
honeypota, nema provere `Origin`/`Referer`, nema CSRF tokena, nema provere
`User-Agent`. Endpoint je javan i bez autentifikacije (`:143-147`, docstring to
izričito kaže).

## 4.4 Gde se podaci upisuju

- Supabase tabela `waitlist` (`:163-171`), preko `_get_supa()` iz `shared.deps`.
- Aplikacija se povezuje **service ključem**, koji zaobilazi RLS. Politika
  `USING (false)` (`:29`) znači da niko drugi ne čita tabelu.
- Kolone: `ime`, `email` (lowercase), `firma`, `telefon`, `poruka`,
  `status='pending'`, `created_at`.
- Unique indeks nad `lower(email)` (`:26`) + eksplicitna `ilike` provera
  duplikata pre insert-a (`:153-161`).
- **Email notifikacija osnivaču** ide SMTP-om u pozadinskom tasku (`:174`), i
  **tiho se preskače** ako `EMAIL_SMTP_HOST/USER/PASS` ili `WAITLIST_NOTIFY_EMAIL`
  nisu podešeni (`:91-93`, samo `logger.warning`). Korisnik u oba slučaja dobija
  isti 200.

## 4.5 Presuda

**DA — Beta forma sa sajta može da stoji na `POST /waitlist/prijava` bez ijedne
izmene backenda.**

Uslovi koje forma mora da ispuni, svi na strani frontenda:

1. `fetch('/waitlist/prijava', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({...})})` — **relativan URL**, isti origin. CSP `connect-src 'self'` (`api.py:1155`) to dozvoljava; CORS se ne primenjuje.
2. Šalje se **JSON**, ne `multipart/form-data` i ne `application/x-www-form-urlencoded` — endpoint prima Pydantic model iz tela.
3. Klijentska validacija za `ime` (obavezno, ≤120) i `email`, da se 422 nikad ne pojavi korisniku.
4. Prikazuje se `poruka` iz odgovora, ne fiksni tekst.
5. Obrada 429 posebnom porukom.
6. Honeypot polje se proverava na klijentu (backend ga ignoriše).
7. Bez `<form action="...">` sa nativnim submit-om — trebalo bi JS `preventDefault()`, jer nativni submit očekuje redirekciju, a endpoint vraća JSON.

**Šta ne postoji, a nije blokada za lansiranje** (svako od ovoga traži izmenu
backenda i zato je izlistano posebno): CAPTCHA/Turnstile, potvrda email adrese
(double opt-in), polje za saglasnost sa politikom privatnosti koje se **čuva**
(tabela nema kolonu za to — čekboks na formi je moguć, ali njegov trag nigde ne
ostaje), i strožiji limit od 60/h na samoj ruti.

---

# 5. TESTOVI I CI

## 5.1 Koji testovi bi pali — poimence

**Zamena sajta (`landing.html` → nov sadržaj) + uklanjanje `/pricing`:
nijedan test ne pada.** Provereno na tri načina:

| Provera | Rezultat |
|---|---|
| `grep -rn "landing" tests/` | 3 pogotka, **sva tri su reč „landing" u engleskim komentarima** o race condition-ima (`test_case_evolution.py:613`, `test_predmeti_close.py:130`, `test_singular_intelligence_002_fixes.py:249`). Nijedan ne čita `landing.html`. |
| `grep -rn "pricing" tests/` | svi pogoci su `GET /api/plan/pricing-matrix` (`test_business_groups.py:202-286`) i `test_tier_config.py:7` — **druga ruta, `routers/plans.py:118`** |
| `grep -rn 'client.get("/")' tests/` | **0 pogodaka.** Nijedan test ne gađa rutu `/` HTTP-om. |

Testovi koji **postoje i tiču se ovog posla, ali ne padaju od same zamene**:

| Test | Fajl : linija | Kada bi ipak pao |
|---|---|---|
| `test_frontend_izmena_u_HEAD_commitu_mora_podici_cache_name` | `tests/test_wave11_release_identity.py:159` | **ako isti commit dirne `index.html` ili `static/vindex.js` a ne podigne `CACHE_NAME`.** Zamena sajta sama po sebi ga ne budi (`landing.html` nije u `FRONTEND_ARTEFAKTI`). Ako se prihvati preporuka iz §3.4, budi ga **uvek** — što je i poenta. |
| `test_cache_name_odgovara_obrascu_vindex_v_broj` | `:140` | ako se `CACHE_NAME` preimenuje van obrasca `vindex-v<broj>`. Bump na `vindex-v124` je bezbedan. |
| `test_sw_cache_bumped` | `tests/test_iron_lawyer_frontend_fixes.py:177` | traži `>= 120`; bump naviše je bezbedan, **spuštanje broja bi ga oborilo** |
| `test_sw_cache_bumped_for_this_sprints_frontend_change` | `tests/test_lambda001_beta_readiness_fixes.py:435` | traži `>= 92`; isto |
| `test_build_identity` (`sw_cache`) | `tests/test_build_identity.py:213` | traži `startswith("vindex-v")` |
| `TestPublicPages::test_terms_contains_disclaimer` | `tests/test_api_security.py:99` | **`/terms` mora zadržati tačan niz `"ne predstavljaju pravni savet"`.** Ako se pravne stranice redizajniraju i ta rečenica preformuliše — pada. |
| `TestPublicPages::test_privacy_contains_gdpr_content` | `:96` | `/privacy` mora sadržati `privatnost` ili `privacy` |
| `TestPublicPages::test_privacy/terms_page_returns_200` | `:84-93` | ako se te dve rute diraju |
| `TestRobots::test_robots_txt` | `:121-126` | **`robots.txt` mora zadržati nizove `"User-agent"` i `"/api/"`.** Predlog iz §2.5 ih zadržava. |
| `TestSecurityHeaders::test_csp_present` / `test_x_frame_options` | `:44, 48` | mere se nad `/health`, ne nad sajtom; padaju samo ako se dira CSP middleware |

## 5.2 CI job-ovi koji dodiruju frontend

| Workflow | Job | Dodiruje sajt? |
|---|---|---|
| `tests.yml` | `pytest` (matrica 3.11 + 3.13), `pytest tests/ -q -rs` | posredno — kroz testove iz §5.1. **Nema nijedan gejt specifičan za sajt.** |
| `production-runtime.yml` | `compile-on-production-python` | ne — samo `python -m compileall` |
| `production-runtime.yml` | `import-and-test-on-production-python` | isto kao `tests.yml`, u `python:3.11-slim` |
| `production-runtime.yml` | `production-docker-build` | gradi image; `Dockerfile:17` je `COPY . .` bez `.dockerignore` (potvrđeno da fajl ne postoji), pa **`site/` i novi `landing.html` ulaze u image bez ijedne izmene konfiguracije** |
| `security.yml` | **`secret-scan` (gitleaks, blokirajući, `fetch-depth: 0`)** | **jedini job koji stvarno „čita" HTML sajta.** Pašće ako sadržaj liči na ključ (`eyJ…`, `sk-…`, API token). |
| `security.yml` | `sast-core` / `semgrep-core` (blokirajući) | ne — opseg je isključivo Python |
| `security.yml` | `dependency-scan` (pip-audit) | ne |
| — | **nigde `npm`/`node`/`yarn`** | potvrđuje §1.5 |

**Upozorenje o signalu:** `secret-scan` je **već crven** zbog nesupresovanog
istorijskog nalaza (iscureli OpenAI ključ iz prvog commita, `dc29b764`). Crven
CI se **ne sme** koristiti kao dokaz da sajt nešto lomi — mora se čitati koji job
i koji nalaz.

## 5.3 Predlog NOVIH testova (samo predlog — nijedan nije napisan)

Poređano po tome koliki kvar hvataju.

| # | Predlog | Šta hvata što danas niko ne hvata |
|---|---|---|
| T1 | `test_svaka_javna_stranica_vraca_200` — parametrizovano nad listom svih javnih ruta, asertuje `200` + `text/html` | Danas **nijedan test ne gađa `/` HTTP-om.** Ruta bi mogla da vraća 500 mesecima, a suite ostaje zelen. |
| T2 | `test_svaka_javna_stranica_ima_eksplicitan_cache_control` | Direktno zaključava nalaz R3 (`/` je jedina bez politike). Da je postojao, `/` ne bi godinu dana bio bez `Cache-Control`. |
| T3 | `test_nijedna_stranica_ne_sadrzi_zabranjenu_frazu` — `"Počni besplatno"`, `"Zakažite demo"`, `"Kontaktirajte prodaju"`, `"AI nikad ne presuđuje"`, `"zaštićeno na nivou baze"`, `"Vindex zna odakle zna"` kao samostalan naslov, i bilo koji broj zakona dok korpus nije proveren | `CONTENT_MAP §1, §5, §6.3` su odluke koje danas ne čuva ništa. Prva sledeća izmena teksta ih tiho poništava. |
| T4 | `test_nijedan_link_u_podnozju_nije_prazan` — nula `href="#"` i `href=""` u stranicama sajta | Faza A: 9 od 20 linkova u današnjem podnožju je `href="#"`. |
| T5 | `test_svaki_interni_link_pokazuje_na_registrovanu_rutu` — skupi sve `href="/..."` iz stranica sajta i uporedi sa `{r.path for r in app.routes}` | **Ovo bi samo po sebi uhvatilo i povratak `/pricing` linka i svaku štamparsku grešku u URL-u.** Najisplativiji test na listi. |
| T6 | `test_pricing_ruta_je_uklonjena` — `client.get("/pricing").status_code == 404` + nula pojava `"/pricing"` u stranicama sajta | Zaključava odluku iz `CONTENT_MAP §6.2` da se ne vrati „jer fajl već postoji". |
| T7 | `test_stranice_sajta_ne_ucitavaju_resurse_koje_CSP_blokira` — skenira `src=`/`href=`/`url(` za spoljne hostove van CSP dozvole | Dizajner nalepi YouTube `<iframe>` ili Unsplash sliku; CSP je **tiho** blokira, stranica izgleda polomljeno samo u pretraživaču, a CI je zelen. |
| T8 | proširenje `FRONTEND_ARTEFAKTI` (§3.4) — `CACHE_NAME` mora rasti kad se sajt promeni | Danas zamena sajta bez bump-a prolazi zeleno, a SW keširа `/`. |
| T9 | `test_nijedna_stranica_sajta_ne_sadrzi_zabranjenu_ikonu` — `⚔️🧠⚖️🎯⚡💡📊🚨` i sl. | Faza A §6.5: **nijedan test ne proverava ikone.** Zato `⚖` u `index.html:16` i `⚡🤖🗄️🔍⚙️` u `status.html:62` nikad nisu prijavljeni. Test treba **ograničiti na `site/`** — nad `index.html`/`status.html` bi pao odmah, i to je zatečeni dug koji se imenuje posebno, ne krišom kroz nov test. |
| T10 | `test_tokeni_sajta_prolaze_WCAG_AA` — isparsiraj CSS custom properties, izračunaj kontrast prema `#010308`, asertuj `>= 4.5:1` za tokene teksta | Deterministično je i hvata R16 (`--tx-3` na 2,44:1 nosi celo podnožje). |
| T11 | `test_svaka_stranica_ima_meta_description_i_canonical` | R8: `landing.html:6` je jedini `<meta name="description">` na `/`; nove stranice bi ga lako izgubile. Canonical dodatno gasi duplikat `/security` ↔ `/static/security.html`. |
| T12 | `test_beta_forma_salje_polja_koja_endpoint_prima` — izvuci `name=`/`id=` iz forme i uporedi sa poljima `WaitlistPrijava` | Hvata razlaz forme i modela pri budućem preimenovanju polja. |

---

# 6. PERFORMANSE I CSP

## 6.1 Kako se fontovi učitavaju danas

`landing.html:8-10`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
```

**Tri porodice, 11 rezova** na landingu:

| Porodica | Rezovi | Broj |
|---|---|---|
| Cormorant Garamond | 400, 600, 700, *400*, *600* | 5 |
| Plus Jakarta Sans | 400, 500, 600, 700 | 4 |
| JetBrains Mono | 400, 700 | 2 |

Aplikacija (`index.html:15`) učitava **još više** — dodaje Source Serif 4 i
dodatne težine (Cormorant 8 rezova, Jakarta 5, Mono 3, Source Serif 5 = **21
rez**).

**Šta to košta pri prvom učitavanju:**

1. **Dva dodatna porekla na kritičnoj putanji** — `fonts.googleapis.com` i
   `fonts.gstatic.com`. `preconnect` skraćuje DNS+TLS, ali ih ne uklanja.
2. **`<link rel="stylesheet">` sa trećeg porekla blokira renderovanje.**
   `display=swap` utiče samo na to da li se tekst crta pre nego što font stigne
   — **ne** čini CSS neblokirajućim. Dok taj zahtev ne završi, stranica se ne
   crta.
3. **Lančana zavisnost:** HTML → CSS sa Google-a → tek onda `.woff2` fajlovi sa
   `gstatic`-a. Dva puna kruga latencije pre nego što ijedno slovo dobije svoj
   font.
4. **Srpska latinica traži `latin-ext`** (`š ć č ž đ`). Google deli fajlove po
   `unicode-range`, pa se za većinu rezova preuzimaju **dva** fajla
   (`latin` + `latin-ext`) — realno **do ~20 `.woff2` zahteva** na landingu.
5. **SW ih kešira cache-first bez isteka** (`sw.js:77-97`) — v. §3.2.

## 6.2 Preporuka: samostalno hostovati fontove u `static/fonts/`

CSP već dozvoljava (`font-src 'self' …`), pa **nije potrebna nikakva izmena
bezbednosnog header-a.**

| Dobitak | Objašnjenje |
|---|---|
| dva porekla manje na kritičnoj putanji | nema DNS/TLS ka Google-u, nema lanca CSS→font |
| `@font-face` je inline u stranici | font počinje da se preuzima čim parser vidi `<style>`, bez međukoraka |
| kraj cache-first-zauvek ponašanju SW-a | fajlovi u `static/` idu kroz stale-while-revalidate i kroz `CACHE_NAME` |
| **privatnost — relevantno baš za ovaj proizvod** | Google Fonts sa Google-ovih servera znači da IP adresa svakog posetioca ide američkoj trećoj strani. Proizvod koji na `/dpa` i `/privacy` prodaje obradu podataka u EU okviru ne bi trebalo da to radi na naslovnoj strani. |
| licence to dozvoljavaju | Cormorant Garamond (OFL), Plus Jakarta Sans (OFL), JetBrains Mono (OFL) — samostalno hostovanje je izričito dozvoljeno |

Uz to: **smanjiti broj rezova.** `CONTENT_MAP §7` traži tačno tri stvari —
Cormorant sa italic `<em>`, `#010308`, i monospace za podatke. Za to je dovoljno
Cormorant 400/600/700 + italic 400, Mono 400/700, i sans 400/600 — **8 rezova
umesto 11**, i to samo `latin` + `latin-ext` podskupovi.

**Ako se ostane na Google Fonts** (npr. zbog brzine isporuke), obavezno je
uskladiti `?family=` string sa aplikacijom da bi keš bio deljen — inače
posetilac koji pređe sa sajta na `/app` preuzima drugi set fajlova.

## 6.3 CSP — tačan header

`api.py:1149-1161`, postavlja se u middleware-u na **svaki** odgovor:

```
default-src 'self';
script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com;
style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com fonts.googleapis.com;
font-src 'self' cdnjs.cloudflare.com fonts.gstatic.com data:;
img-src 'self' data: blob:;
connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com
            https://api.emailjs.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com
            https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com;
worker-src 'self' blob:;
frame-ancestors 'none';
report-uri /api/security/csp-report
```

**Potvrđeno: inline `<style>` i inline `<script>` su dozvoljeni** —
`style-src` i `script-src` oba sadrže `'unsafe-inline'`. Sajt ne mora da izmišlja
nonce mehanizam niti da izdvaja skripte u fajlove.

Ostali header-i (`api.py:1144-1148`): `Permissions-Policy: microphone=(self),
camera=(), geolocation=(), payment=()`, `X-Frame-Options: SAMEORIGIN`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy:
strict-origin-when-cross-origin`, `Strict-Transport-Security: max-age=31536000;
includeSubDomains`.

## 6.4 Šta CSP zabranjuje — dizajn ne sme da računa na ovo

| Zabranjeno | Direktiva | Šta konkretno ne sme na sajt |
|---|---|---|
| **spoljne slike** | `img-src 'self' data: blob:` — nijedan spoljni host | nema Unsplash/Cloudinary/S3; svaki snimak, logo, ilustracija i OG slika **mora** u `static/` |
| **spoljni `<iframe>`** | `frame-src` nije deklarisan → pada na `default-src 'self'` | **nema YouTube, Vimeo, Loom, Calendly, Typeform, Google Maps ugradnje.** Ako se poželi „zakažite razgovor" widget — blokiran je. |
| **spoljni `<video>`/`<audio>`** | `media-src` nije deklarisan → `default-src 'self'` | demo video mora biti self-hostovan `<video>` u `static/`, i troši propusni opseg servera |
| **spoljna analitika** | `connect-src` nema GA/Plausible/PostHog/Matomo; `script-src` nema njihove hostove | **merenje poseta nije moguće bez izmene CSP-a.** Jedina opcija bez izmene: sopstveni endpoint na istom poreklu. |
| **spoljni fontovi van Google/cdnjs** | `font-src 'self' cdnjs.cloudflare.com fonts.gstatic.com data:` | Adobe Fonts, Fontshare, Fontsource CDN — blokirani |
| **ugradnja Vindexa u tuđi sajt** | `frame-ancestors 'none'` | nema „embeduj naš demo" |

**Nedeklarisano, pa nije ograničeno:** `form-action` i `base-uri`. Nativni
`<form action="…">` bi tehnički smeo da šalje bilo gde. To nije potrebno sajtu
(forma ide `fetch`-om na isti origin) i pominje se samo da se ne bi slučajno
oslonilo na CSP kao na zaštitu koja tu ne postoji.

**Sukob header-a (zatečen, ne uvodi ga sajt):** `X-Frame-Options: SAMEORIGIN`
(`api.py:1145`) i `frame-ancestors 'none'` (`:1159`) su u koliziji. CSP je stroži
i pobeđuje u modernim pretraživačima. Stvarno ponašanje: **nikakvo uokvirivanje,
ni sa istog porekla.**

---

# 7. PLAN IZVOĐENJA

Redosled je izveden iz zavisnosti, ne iz prioriteta sadržaja. Faze nose oznake iz
`CONTENT_MAP §8`.

### Korak 0 — odluke pre pisanja ijedne linije (blokirajuće)
Domen (`vindex.rs` vs `vindex-ai.com`), izvor istine za tokene (landing vs
aplikacija), i da li se `landing.html` briše ili zadržava pod tim imenom.
**Bez ovoga se ne sme početi** — sve troje ulazi u svaku stranicu (canonical, OG,
tokeni) i naknadna promena znači prepisivanje svih devet fajlova.

### Korak 1 — dizajn sistem (Faza B)
`static/site.css`: tokeni izvedeni iz `landing.html:14-40` i `CONTENT_MAP §7`,
sa ispravkom `--tx-3` na vrednost koja prolazi AA. Bez ijedne stranice još.
Isporuka: jedan CSS fajl + kratak dokument šta je nasleđeno a šta ispravljeno.

### Korak 2 — jedna stranica kao dokaz obrasca (Faza D, deo)
Napisati **samo početnu**, `site/pocetna.html`, i **samo rutu za nju**. Pustiti
je lokalno. Ovim se proverava: da CSP ništa ne blokira, da GZip radi, da
`Cache-Control` stiže, da SVG dijagrami rade u oba pretraživača. **Ne isporučuje
se na produkciju.**

### Korak 3 — ostatak stranica (Faze D + E)
`kako-radi`, `bezbednost`, `beta`, `kontakt`, `pravno` (P0), zatim
`tehnologija`, `za-advokate`, `vizija` (P1). Svaka nasleđuje `static/site.css`;
nijedna ne uvodi sopstveni token.

### Korak 4 — veze i forma (Faza F)
Podnožje koje linkuje svih 6 pravnih stranica (`/privacy`, `/terms`, `/security`,
`/dpa`, `/ai-disclosure`, `/bezbednosni-list`), ulaz u aplikaciju (`/app`), i
Beta forma na `POST /waitlist/prijava` po pravilima iz §4.5.

### Korak 5 — izmene u `api.py` (jedan commit, traži saglasnost)
Sve odjednom, jer su međusobno zavisne:
- nove rute (§2.1), po potrebi `_serve_site_page` (§2.2);
- `Cache-Control` na `/` (§2.3);
- brisanje `/pricing` + `pricing.html` (§2.4);
- `robots.txt` + `sitemap.xml` (§2.5).

### Korak 6 — service worker (ISTI commit kao korak 5)
`static/sw.js:4` → `vindex-v124`. **Ne odvajati od koraka 5** — ako izmena sajta
i bump budu u različitim commit-ima, postoji prozor u kome je nov sajt živ a
stari keš i dalje važi.

### Korak 7 — testovi (Faza G)
T1, T2, T5, T6 kao minimum (§5.3) i, ako se prihvati, proširenje
`FRONTEND_ARTEFAKTI` (§3.4). **Pisati ih posle stranica, ne pre** — inače se
piše test za nagađanje.

### Korak 8 — provera tvrdnji pre nego što se kaže „gotovo"
`CONTENT_MAP §8`: truth audit tvrdnja-po-tvrdnja prema
`VINDEX_WEBSITE_CLAIMS_REGISTRY.md`. Nijedan broj (korpus zakona) ne ide na sajt
dok nije izmeren.

### Korak 9 — posle isporuke, zasebno
Kontradikcija koju sajt **ne rešava**: pre-auth ekran aplikacije
(`index.html:4166-4227`) i dalje govori drugu priču od nove Beta stranice
(R11 iz Faze A). Dok se to ne uskladi, šav je pomeren, ne uklonjen.

---

# 8. RIZICI

| # | Rizik | Verovatnoća | Šta se dešava | Kako se izbegava |
|---|---|---|---|---|
| B1 | **Zaboravljen `CACHE_NAME` bump** | **visoka** — nijedan test to danas ne traži za sajt (§3.4) | Korisnici koji su ikada otvorili `/app` drže star `/`, star `static/site.css` i stare fontove u kešu `vindex-v123`. Vidi se samo pri lošoj mreži, pa se **ne primećuje pri testiranju** i može trajati mesecima. | Bump u **istom** commit-u (Korak 6). Trajno: proširiti `FRONTEND_ARTEFAKTI` (§3.4). |
| B2 | **Devet kopija dizajn sistema se raziđe** | visoka, ako se ide na Opciju A (§1.4) | Ponavlja se R14 iz Faze A — sajt postaje osmi vizuelni sistem u proizvodu, pa i sam sebi nekonzistentan | Jedan `static/site.css` (Opcija B) + T10 (kontrast tokena) |
| B3 | **Zajednički CSS zastari kod posetioca** | srednja | `static/*.css` ima `max-age=3600` (`api.py:1139`) **i** SW stale-while-revalidate — nov HTML na starom CSS-u izgleda polomljeno | `?v=<commit>` kroz `_serve_site_page` (§2.2), koji reciklira postojeći mehanizam iz `api.py:1490` |
| B4 | **CSP tiho blokira resurs** | srednja — dizajner ne zna za CSP | Slika/iframe/analitika ne rade; greška je samo u konzoli pretraživača, CI je zelen, na produkciji se vidi tek kad neko pogleda | Pravila iz §6.4 unapred; test T7 |
| B5 | **`secret-scan` obori CI** | niska za sadržaj sajta | Blokirajući job pada; a **već je crven** zbog istorijskog nalaza (`dc29b764`) pa se lako pogrešno protumači | Nula ključeva u HTML-u; pre isporuke pročitati **koji** nalaz je crven, ne samo boju |
| B6 | **Broj zakona odštampan na sajtu** | srednja — brojevi „ulepšavaju" tekst | `landing.html:905` kaže „18 zakona", `index.html:4209` „847 zakona" — najmanje jedan je netačan. Netačan broj na javnom sajtu pravnog proizvoda je najgora moguća greška | `CONTENT_MAP §6.3`: **nijedan broj dok korpus nije izmeren.** Test T3. |
| B7 | **Podnožje puno `href="#"`** | srednja — današnji landing ima 9 takvih | Posetilac klikne „DPA" i ne desi se ništa. Za proizvod koji prodaje pouzdanost, to je najskuplji mogući detalj | T4 + T5 (svaki interni link mora pokazivati na registrovanu rutu) |
| B8 | **Waitlist prijave stižu, a niko ne zna** | **srednja, i nemerljiva spolja** | `_send_notification` se **tiho preskače** ako SMTP env nije podešen (`routers/waitlist.py:91-93`, samo `logger.warning`). Korisnik dobija 200, red uđe u bazu, osnivač ne dobija ništa. | Pre lansiranja potvrditi `EMAIL_SMTP_HOST/USER/PASS` i `WAITLIST_NOTIFY_EMAIL` u produkciji, i poslati **jednu pravu prijavu** kao proveru |
| B9 | **Bot puni `waitlist` tabelu** | niska-srednja | Jedina zaštita je 60/h po IP-u, in-memory po radniku (§4.3). Nema CAPTCHA-e ni honeypota na serveru. | Honeypot na klijentu (radi bez izmene backenda); ako postane problem — `@limiter.limit("5/hour")` na ruti, **izmena backenda** |
| B10 | **Zamena sajta pomera, ne uklanja kontradikciju** | **visoka — sigurno se dešava ako se ne planira** | Nov sajt kaže „zatvoreno testiranje", `/app` pre-auth i dalje kaže svoje (R11). Posetilac koji vidi obe površine dobija dve priče. | Korak 9 kao **planiran nastavak**, ne kao „videćemo" |
| B11 | **Duplikat URL `/x` ↔ `/static/x.html`** | postoji **danas**, ne uvodi ga sajt | Pretraživač indeksira obe verzije istih pravnih stranica | Nove stranice u `site/` (§1.3, ne ponavlja grešku) + `canonical` u postojećim stranicama (**izmena produkcionih fajlova → odluka**) |
| B12 | **`/offline` fallback pokazuje app shell posetiocu sajta** | niska (samo offline) | Posetilac bez mreže na `/kako-radi` dobija ekran aplikacije | Zaseban zadatak: mala offline stranica sajta (§3.3, tačka 3). Ne blokira. |
| B13 | **Uvođenje build alata „samo za minifikaciju"** | niska, ali skupa ako se desi | Prvi build korak u istoriji repoa; nova klasa kvarova („zaboravljen build"), novi CI job, novi `node_modules` | Ne raditi. GZip (`api.py:959`) već pokriva najveći deo dobitka. |

---

# 9. ŠTA NE SMEM DA URADIM BEZ ODLUKE

## 9.1 Izmene produkcionih fajlova koje plan ZAHTEVA, a ja ih nisam izvršio

Plan se **ne može izvesti** bez ove tri izmene. Sve su ovde napisane kao dif, ali
nijedna nije primenjena — mandat Faze B izričito zabranjuje izmenu produkcionih
fajlova.

| Fajl | Šta plan traži | Zašto je neizbežno |
|---|---|---|
| `api.py` | 8 novih ruta (§2.1), `Cache-Control` na `/` (§2.3), brisanje `/pricing` (§2.4), `robots.txt` + `sitemap.xml` (§2.5) | **FastAPI ne servira nijedan fajl bez rute.** `site/` nije montiran (i ne sme biti, §1.3), pa nova stranica bez rute ne postoji na internetu. Nema načina da se ovo zaobiđe. |
| `static/sw.js` | `CACHE_NAME` `vindex-v123` → `vindex-v124` (§3.3) | Jedini brisač keša koji postoji (`sw.js:24-30`). Bez toga rizik B1. |
| `landing.html` | zamena sadržaja (ili brisanje, ako se ide na `site/pocetna.html`) | To je fajl koji `api.py:1503` servira na `/`. |

Dodatno, **ako se prihvati preporuka iz §3.4**: `tests/test_wave11_release_identity.py:52`
(`FRONTEND_ARTEFAKTI`). Nisam ga menjao. Provera da preporuka ne razbija
postojeće kontrole detektora je u §3.4.

## 9.2 Odluke koje traže vlasnika

| # | Odluka | Zašto ne mogu ja | Šta blokira |
|---|---|---|---|
| V1 | **Domen: `vindex.rs` ili `vindex-ai.com`?** | poslovna odluka; oba su živa u kodu (`landing.html:1056,1095` vs `pricing.html:9`) | `canonical`, `og:url`, `sitemap.xml`, email adresa u podnožju. **Blokira Korak 0.** |
| V2 | **Izvor istine za tokene: landing (Plus Jakarta Sans, radiusi 6/14px) ili aplikacija (JetBrains Mono, 2/4px)?** | identitet proizvoda | ceo `static/site.css`. **Blokira Korak 1.** |
| V3 | **Briše se `landing.html` ili se zadržava pod tim imenom?** | utiče na to da li `root()` uopšte menja putanju | Korak 5, i da li stari sajt ostaje kao mrtav fajl u repou |
| V4 | **Uklanja se `/pricing` — potvrda.** `CONTENT_MAP §6.2` je odlučio; potvrda je vlasnikova jer je to signal o naplati | poslovna, ne tehnička | Korak 5. Tehnički je čisto: 0 linkova, 0 testova (§2.4). |
| V5 | **Registracija ili waitlist kao jedini CTA?** Ako waitlist — pre-auth ekran aplikacije (`index.html:4166-4227`) mora se uskladiti | backend podržava oba (`api.py:2491` registracija, `routers/waitlist.py:143` waitlist) | Korak 4 i Korak 9. Bez odluke sajt pomera kontradikciju umesto da je zatvori. |
| V6 | **Broj zakona u korpusu** — dok se ne izmeri, nijedan broj ne ide na sajt | traži merenje Pinecone/korpusa, ne čitanje repoa | sadržaj hero i „Šta radi danas" sekcija |
| V7 | **Samostalno hostovanje fontova?** (§6.2) | menja identitet učitavanja i dodaje ~8 fajlova u `static/`; ima i privatnosnu dimenziju za EU | Korak 1 |
| V8 | **Da li se `canonical` dodaje u postojeće `static/*.html` pravne stranice?** (§2.5, B11) | izmena 5 produkcionih fajlova radi SEO higijene | zaseban, mali zadatak |
| V9 | **Redizajn `status.html` i uklanjanje zabranjenih ikona iz `index.html:16` / `status.html:62`?** | zatečeni dug (R15); test T9 bi pao ako obuhvati te fajlove | opseg testa T9 |
| V10 | **Tekst saglasnosti / GDPR na Beta formi** — i činjenica da tabela `waitlist` **nema kolonu** za trag saglasnosti | pravna odluka + eventualna migracija baze | Korak 4 |
| V11 | **SMTP u produkciji za waitlist notifikacije** — potvrditi da su `EMAIL_SMTP_*` i `WAITLIST_NOTIFY_EMAIL` postavljeni | ne mogu videti produkciono okruženje | rizik B8; bez potvrde prijave nestaju u tišini |
| V12 | **Analitika.** CSP je zabranjuje u potpunosti (§6.4). Ako se želi merenje poseta, to je ili izmena CSP-a (slabi bezbednosnu poziciju) ili sopstveni endpoint na istom poreklu (novi backend kod). | bezbednosna + poslovna | ništa u Koracima 1-8; odluka pre lansiranja |

## 9.3 Odluke koje su moje (frontend arhitektura), i koje sam doneo ovde

Više fajlova umesto jednog (§1.2) · `site/` kao lokacija (§1.3) · zajednički
`static/site.css` umesto devet inline kopija (§1.4) · bez build alata (§1.5) ·
`GET` bez `HEAD` na novim rutama (§2.1) · `public, max-age=300` kao politika
keša sajta (§2.3) · `sitemap.xml` iz `request.base_url` umesto hardkodovanog
domena (§2.5) · **ne** dodavati stranice u `PRECACHE` (§3.3) · Beta forma kao
`fetch` + JSON + klijentska validacija + klijentski honeypot (§4.5) · redosled
koraka u §7.

---

*Kraj dokumenta. Nijedan produkcioni fajl nije menjan u Fazi B —
`api.py`, `landing.html`, `index.html`, `static/*` i `tests/*` su ostali
netaknuti. Sve izmene u ovom dokumentu su specifikacija, ne dif koji je
primenjen.*
