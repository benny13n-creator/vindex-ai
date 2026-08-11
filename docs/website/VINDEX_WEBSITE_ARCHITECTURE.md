# VINDEX AI — ARHITEKTURA SAJTA (Faza A: DISCOVERY)

Izvedeno iz koda na `HEAD` = `89996be`. **Nijedan produkcioni fajl nije menjan.**
Sve vrednosti su citirane iz koda sa lokacijom. Gde koda nema, piše `NE POSTOJI`.

Ovaj dokument opisuje **zatečeno stanje**. Predlozi su odvojeni u zasebne blokove
označene sa `PREDLOG` i nisu deo zatečenog identiteta.

---

## 0. NALAZ NA VRHU — POSTOJE TRI LANDING-A, NE JEDAN

| # | Površina | Fajl | Ruta | Poruka | CTA |
|---|---|---|---|---|---|
| 1 | Javni landing | `landing.html` | `/` | „Pravni operativni sistem" | „Počni besplatno — 15 upita bez kartice" → `/app#register` |
| 2 | Pre-auth ekran aplikacije | `index.html:4166-4227` (`.vx-land-*`) | `/app` | „Pravni Operativni Sistem — Republika Srbija" | **„Zatražite rani pristup"** (waitlist) + „Beta · Ograničen broj mesta" |
| 3 | Cenovnik | `pricing.html` | `/pricing` | 4 plana sa cenama | „Otvoriti nalog" → `/app` |

**Ovo je najveći zatečeni problem i on nije vizuelni, nego logički.**
Dugme „Počni besplatno" na `/` vodi na `/app#register`, a tamo korisnika dočekuje
ekran koji kaže **„Zatražite rani pristup — Ograničen broj mesta"**. Jedna površina
prodaje samouslužnu registraciju, druga zatvorenu betu. Obe su žive istovremeno.

Uz to, `/pricing` je i dalje javna ruta (`api.py:1550`) i servira `pricing.html` sa
konkretnim cenama, iako je sekcija cenovnika iz `landing.html` uklonjena upravo zato
što te cene nisu naplative (`landing.html:1000-1038`, commit `3381d59f`).
**Uklonjena je sekcija, nije uklonjena ruta.**

Kontradiktorni brojevi u istom proizvodu:

| Tvrdnja | Lokacija | Vrednost |
|---|---|---|
| broj zakona | `landing.html:905` | **18 zakona RS** |
| broj zakona | `index.html:4209` | **847 zakona Srbije** |
| sudske odluke | `landing.html:909, 987` | 12.604 |

---

## 1. DIZAJN SISTEM

### 1.1 Provera tokena iz blueprint-a

`docs/website/VINDEX_AI_WEBSITE_VISUAL_BLUEPRINT.md:6-7` tvrdi zatečeno stanje:
`Cormorant Garamond` · `#010308` · `#00d4ff` · `#e6edf3` · `#4ade80` / `#f56565`.

| Token iz blueprint-a | Postoji u `landing.html` | Postoji u aplikaciji | Presuda |
|---|---|---|---|
| `Cormorant Garamond` | DA — `landing.html:28` `--font-brand` | DA — `vindex.css:2766` `--font-brand` | **POTVRĐEN** |
| `#010308` podloga | DA — `landing.html:14` `--void`, 7 pojava | DA — `vindex.css:2731` `--void`, `:8778` `--vx-bg-primary` | **POTVRĐEN** |
| `#00d4ff` akcenat | DA — `landing.html:15` `--teal` | DA — pod **7 imena** (v. 1.4) | **POTVRĐEN, ali fragmentisan** |
| `#e6edf3` tekst | **NE — 0 pojava** | DA — 35× u `vindex.css`, 18× u `index.html` | **RAZLIKA** |
| `#4ade80` uspeh | DA — `landing.html:475` | DA — `vindex.css:2205` `--color-success`, `:8749` `--vx-success` | **POTVRĐEN** |
| `#f56565` greška | **NE — 0 pojava** | DA — 24× u `vindex.css` | **RAZLIKA** |
| „oštri uglovi" | **NE** — `--r-sm:6px`, `--r-lg:14px` | DA — `--r-sm:2px`, `--r-lg:4px`; 84,8% svih radiusa ≤4px | **RAZLIKA — landing krši pravilo** |
| „bez gradijenata" | **NE** — 4 gradijenta u landingu | **NE** — 27 gradijenata u `vindex.css` | **KRŠI SE NA OBE STRANE** |
| „bez glow-a" | **NE** — `box-shadow: 0 0 80px…160px` | **NE** — 10 cyan glow senki + 2 glow **tokena** | **KRŠI SE NA OBE STRANE** |

**Zaključak:** blueprint je opisivao **aplikaciju** (`static/vindex.css`), a ne
`landing.html`. `#e6edf3` i `#f56565` u landingu ne postoje. Obrnuto, `--r-sm/--r-lg`
i `--font-ui` u landingu imaju **druge vrednosti pod istim imenima** nego u aplikaciji.

### 1.2 Kolizije imena tokena — isti naziv, različita vrednost

Ovo su pravi nalazi, ne stilske razlike. Ako se sajt gradi „nasleđivanjem tokena",
mora se odlučiti **koji** od dva sistema je izvor istine.

| Token | `landing.html` | `static/vindex.css` | Razlika |
|---|---|---|---|
| `--font-ui` | `'Plus Jakarta Sans', system-ui, sans-serif` (:29) | `'JetBrains Mono','SF Mono','Fira Code', monospace` (:2767) | **sans vs monospace** — dijametralno |
| `--r-sm` | `6px` (:26) | `2px` (:2770) | 3× |
| `--r-lg` | `14px` (:27) | `4px` (:2772) | 3,5× |
| `--tx-1` | `rgba(255,255,255,0.92)` (:22) | `rgba(255,255,255,0.88)` (:2745) | mala, ali stvarna |
| `--tx-2` | `0.55` (:23) | `0.52` (:2746) | mala |
| `--tx-3` | `0.30` (:24) | `0.28` (:2747) | mala |
| akcenat | `--teal` (:15) | `--blue` / `--accent` / `--vx-accent` / `--vp` … | isti hex, 7 imena |
| `--t-fast/base/slow` | ne postoji | **dva puta** u istom fajlu: `vindex.css:2213` `.12/.22/.38s` vs `:2774` `.10/.20/.35s` | kaskada bira `:2774`, `:2213` je mrtav |

### 1.3 Tokeni `landing.html` — doslovno

`landing.html:13-31`

| Token | Vrednost | Uloga u kodu |
|---|---|---|
| `--void` | `#010308` | `body` podloga (:37), boja teksta na teal dugmadima |
| `--teal` | `#00d4ff` | jedini akcenat |
| `--teal-lo` | `rgba(0,212,255,0.08)` | hover pozadina outline dugmeta |
| `--teal-md` | `rgba(0,212,255,0.16)` | hover `.zasto-card` |
| `--teal-hi` | `rgba(0,212,255,0.35)` | hover ivica `.zasto-card` |
| `--bd-1` | `rgba(255,255,255,0.06)` | osnovna ivica, `fn-grid` razmak |
| `--bd-2` | `rgba(255,255,255,0.10)` | ivica dugmadi |
| `--bd-teal` | `rgba(0,212,255,0.20)` | akcentna ivica |
| `--tx-1` | `rgba(255,255,255,0.92)` | osnovni tekst |
| `--tx-2` | `rgba(255,255,255,0.55)` | sekundarni tekst |
| `--tx-3` | `rgba(255,255,255,0.30)` | tercijarni tekst |
| `--tx-4` | `rgba(255,255,255,0.14)` | **MRTAV — 0 upotreba** |
| `--r-sm` | `6px` | dugmad, badge-evi |
| `--r-lg` | `14px` | kartice |
| `--font-brand` | `'Cormorant Garamond', Georgia, serif` | logo, svi H1/H2, cene |
| `--font-ui` | `'Plus Jakarta Sans', system-ui, sans-serif` | telo |
| `--font-mono` | `'JetBrains Mono', monospace` | oznake sekcija, brojevi, footer |

**Nedeklarisane boje van tokena** (hardkodirane u `landing.html`):
`#eef3f9` (:300 svetla sekcija „Kako radi"), `#0d1117` (:301 tekst na svetlom),
`#0099bb` (:306, :340 akcenat na svetlom), `#4a5568` (:316 telo na svetlom),
`#fff` (:328 kartica), `#4ade80` (:475), `#139,92,246` ljubičasta (:489, :503, :509,
:520 — „firma" plan, ostatak uklonjenog cenovnika), `#a78bfa`, `#c4b5fd`.

### 1.4 Fragmentacija tokena u aplikaciji

`static/vindex.css` ima **8 `:root` blokova** + `body.light-theme`, u pet paralelnih
namespace-a za iste pojmove:

| Blok | Linija | Namespace | Status |
|---|---|---|---|
| spacing 8pt | 1751 | `--sp-*` | živ |
| emerald | 2011 | `--emerald*` | dupliran u :2200 |
| „FAZA 1" | 2200 | `--surface-*`, `--border-*`, `--color-*` | delom nadjačan |
| **„v3" (glavni)** | **2727** | `--void/--blue/--tx-*/--bd-*/--s*/--r-*/--font-*` | **autoritativan za paletu i fontove** |
| ikonice | 4740 | `--icon-*` | živ |
| „PREMIUM" | 8201 | `--vp-accent*` | delom nadjačan |
| „PREMIUM 2.0" | 8526 | `--vp`, `--accent` | delom nadjačan |
| **„vx" (najnoviji)** | **8741** | `--vx-*` | **autoritativan za komponente** |
| light tema | 6383 | override `--void`→`#f0f4f8`, `--blue`→`#0099bb` | živ |

Isti cyan `#00d4ff` je definisan pod **7 imena**: `--blue`, `--tx-blue`,
`--icon-nav-active`, `--vp-accent`, `--vp`, `--accent`, `--vx-accent`.

Dodatni defekti u tom sloju:
- `var(--font-serif)` se koristi 3× (`vindex.css:40, :70, :883`), ali **nikad nije definisan** → browser default serif.
- `Source Serif 4` se učitava sa Google Fonts (`index.html:15`) ali se **nigde ne referencira** u CSS-u.
- Mrtvi zaobljeni tokeni: `--vx-card-radius: 10px` (:8762) i `--vx-modal-radius: 12px` (:8746) — **0 upotreba**, ostaci pre-Bloomberg faze.
- `var(--vx-radius-sm, 8px)` — fallback od 8px na 4 mesta (:4654, :8695, :9425, :9481); token JESTE definisan (2px) pa se fallback nikad ne aktivira, ali kod čitaocu laže o nameri.

### 1.5 Tipografija

**Landing** (`landing.html:8-10`) — Google Fonts, jedan `<link>` sa `preconnect`:

| Font | Težine | Uloga |
|---|---|---|
| Cormorant Garamond | 400, 600, 700 + italic 400, 600 | `--font-brand` — logo, H1, H2, nazivi kartica |
| Plus Jakarta Sans | 400, 500, 600, 700 | `--font-ui` — telo |
| JetBrains Mono | 400, 700 | `--font-mono` — oznake, brojevi, footer bottom |

**Aplikacija** (`index.html:15`) — isti CDN, ali **četiri** familije: Cormorant Garamond
(300-700 + italic), Plus Jakarta Sans (300-700), JetBrains Mono (300-500), **Source Serif 4**
(neupotrebljen). `@font-face`: **0** u oba fajla — nema self-hostovanih fontova.

Kritična razlika: u aplikaciji je **`--font-ui` = JetBrains Mono**, tj. telo teksta je
monospace (Bloomberg/Palantir pristup). U landingu je `--font-ui` = Plus Jakarta Sans.
Izuzetak u aplikaciji: `#tab-h { --font-ui: 'Plus Jakarta Sans' … }` (`vindex.css:2786`)
— zaključani dashboard namerno ostaje sans.

Skala u landingu (`clamp` za sve naslove):

| Element | Deklaracija | Lokacija |
|---|---|---|
| `.hero-h1` | `clamp(3rem, 4.5vw, 5rem)` / 700 / `line-height:1.05` / `letter-spacing:-0.02em` | :187-192 |
| H2 (svi) | `clamp(2.2rem, 3.5vw, 3.4rem)` / 700 / `-0.02em` | :308, :358, :423, :453 |
| `.cta-logo` | `clamp(3rem, 6vw, 6rem)` / 700 / `-0.03em` | :531 |
| telo | `16px` / `line-height:1.6` | :40-41 |
| `.hero-p` | `1.05rem` / `1.72` / `max-width:520px` | :196-199 |
| `.section-label` | `0.65rem` mono / 700 / `letter-spacing:0.18em` / uppercase | :120-129 |

### 1.6 Razmaci

Landing **nema token skalu razmaka.** Sve je hardkodirano. Izvedena skala:

| Namena | Vrednost | Lokacija |
|---|---|---|
| padding sekcije (desktop) | `100px 0` | :302, :355, :415, :450 |
| padding sekcije (≤1024px) | `80px 0` | :671-672 |
| padding sekcije (≤768px) | `64px 0` | :698 |
| CTA sekcija | `120px 0` → `72px` | :526, :699 |
| padding kartice | `36px 32px` → `28px 24px` → `24px 20px` | :328, :703, :710 |
| container padding | `0 32px` → `0 20px` → `0 18px` | :118, :677, :729 |
| gap grid-a | `32px` / `24px` / `20px` / `2px` (fn-grid) | :324, :428, :477, :367 |
| visina nav-a | `64px` | :73 |

Aplikacija ima pravu skalu: `vindex.css:1751` `--sp-h:4px … --sp-8:64px` (8pt grid) i
`vindex.css:8788` `--vx-space-1:3px … --vx-space-7:24px` (gušća, za panele).

### 1.7 Ivice i radiusi

| Sistem | Skala | Poštuje „oštre uglove"? |
|---|---|---|
| `landing.html` | `6px` (`--r-sm`), `14px` (`--r-lg`), `10px` (`.zasto-ico`), `999px` (pill) | **NE** |
| `static/vindex.css` | `2px` (209×), `3px` (79×), `4px` (62×), `0` (19×), `50%` (51×) | **DA — 84,8% ≤ 4px** |

Jedini pravi prekršaji u aplikaciji: `vindex.css:981` (10px), `:988` (8px), `:1000` (8px),
`:1002` (7px), `:1058` (6px) — legacy blok, i `--vx-input-radius: 7px` (2 upotrebe).

Ivice u landingu su isključivo `1px solid` u tri jačine (`--bd-1`, `--bd-2`, `--bd-teal`);
senki nema osim na svetloj sekciji i „pro" kartici cenovnika.

### 1.8 Animacije i trajanja

**Landing:**

| Šta | Trajanje | Lokacija |
|---|---|---|
| hover linkova/dugmadi | `0.15s` | :97, :109, :141, :157, :554, :624 |
| hover kartica / pozadine | `0.2s` | :332, :377, :434, :471 |
| `drawer-slide-down` | `0.22s ease` | :597-602 |
| `sphere-breathe` (box-shadow) | **`4s ease-in-out infinite`** | :241-246 |
| pozadinski particle canvas | `requestAnimationFrame`, **beskonačno** | :1104-1145 |
| hero constellation canvas | `requestAnimationFrame`, **beskonačno** | :1148-1207 |
| `html { scroll-behavior: smooth }` | — | :35 |

**Aplikacija:** 228 `transition`, 52 `animation`, 38 `@keyframes`.
Dominantna trajanja: `0.15s` (91×), `0.2s` (77×), `0.12s` (22×), `0.18s` (16×).
Tokeni: `--t-fast/base/slow` = `0.10s/0.20s/0.35s`; `--vx-transition-*` = `150/200/250ms`
sa `cubic-bezier(0.4,0,0.2,1)`.

**NALAZ — `prefers-reduced-motion`:**

| Fajl | Broj `prefers-reduced-motion` blokova |
|---|---|
| `landing.html` | **0** |
| `index.html` | **0** |
| `static/vindex.css` | 2 |

Landing ima **dve trajne `requestAnimationFrame` petlje** koje se nikad ne zaustavljaju
(nema `IntersectionObserver`, nema `visibilitychange`, nema `reduced-motion` gejta).
Blueprint (`VISUAL_BLUEPRINT.md:38-39`) izričito traži da `prefers-reduced-motion` gasi sve.
**Ovo zatečeni landing ne ispunjava.** Pozadinski canvas takođe crta preko cele
`innerWidth × innerHeight` površine na svakom frejmu, uključujući O(n²) petlju
preko 60 čestica (`:1133`) — trošak baterije na mobilnom je stalan.

### 1.9 Tačke preloma

| Fajl | Breakpoints |
|---|---|
| `landing.html` | **1024 / 768 / 480** (`:664`, `:675`, `:728`) — tri, čisto |
| `static/vindex.css` | **14 različitih** max-width vrednosti u 82 media query-ja; primarni `640px` (39×), zatim 768 (7×), 600 (5×), 480 (4×), 900 (4×), 375, 540, 720, 560, 520, 420, 1024, 980, 700 |
| `index.html` | **0** |

Blueprint traži `640 / 1024`. **Landing koristi 768, ne 640** — sudar sa aplikacijom
čiji je primarni breakpoint 640. Nijedan `min-width` nigde: sve je desktop-first.

### 1.10 Kontrast (izmereno, WCAG 2.1 relativna luminancija)

| Kombinacija | Odnos | AA tekst (4.5) | AAA (7.0) |
|---|---|---|---|
| `#00d4ff` na `#010308` | **11,65 : 1** | prolazi | **prolazi** |
| `#010308` na `#00d4ff` (dugme) | 11,65 : 1 | prolazi | prolazi |
| `#e6edf3` na `#010308` | 17,46 : 1 | prolazi | prolazi |
| `#4ade80` na `#010308` | 11,84 : 1 | prolazi | prolazi |
| `#f56565` na `#010308` | 6,81 : 1 | prolazi | pada |
| `--tx-2` `rgba(255,255,255,0.55)` na `--void` | 6,14 : 1 | prolazi | pada |
| **`--tx-3` `rgba(255,255,255,0.30)` na `--void`** | **2,44 : 1** | **PADA** | pada |

**Dva nalaza:**

1. `VINDEX_AI_WEBSITE_IMPLEMENTATION_RISKS.md:20` navodi kontrast `#00d4ff` na `#010308`
   kao „granični slučaj za WCAG AA, meriti pre upotrebe". **Izmereno: 11,65 : 1 — nije
   granični, prolazi i AAA.** Taj rizik se može zatvoriti.
2. Pravi problem je `--tx-3` na **2,44 : 1** — pada AA. Koristi se u
   `.footer-brand-body` (:551), `.footer-col-title` (:552), `.footer-bottom` (:556),
   `.cen-note` (:522), `.cen-toggle-lbl` (:459), `.cen-plan` / `.cen-price span` /
   `.cen-price-sub` (:497-500). To je ceo footer.

---

## 2. KOMPONENTE

Sve komponente ispod **postoje u kodu**. Citirani su selektori i lokacije.

### 2.1 Dugmad

| Klasa | Lokacija | Definicija | Hover |
|---|---|---|---|
| `.btn-filled` | `landing.html:130-145` | `background:var(--teal)`, `color:#010308`, `padding:14px 28px`, `radius:6px`, `font-weight:700`, `letter-spacing:0.01em` | `opacity:0.88; transform:translateY(-1px)` (`0.15s`) |
| `.btn-outline` | `:146-160` | transparent, `color:var(--tx-1)`, `border:1px solid var(--bd-2)`, isti padding/radius | `border-color:var(--bd-teal); background:var(--teal-lo)` |
| `.lp-nav-cta` | `:100-112` | mala varijanta filled, `padding:9px 22px`, `0.85rem` | isto kao filled |
| `.cta-btn` | `:535` | modifikator: `1.05rem`, `padding:16px 40px` | — |
| `.cen-btn` | `:510-521` | outline, `width:100%`, `margin-top:auto` | teal ivica |
| `.mobile-drawer-cta` | `:627-639` | filled, pun po širini, `padding:15px` | — |
| `.mobile-sticky-cta a` | `:650-661` | filled + `box-shadow:0 4px 24px rgba(0,212,255,0.35)` | — |

Aplikacija ima paralelan, **nekompatibilan** set: `.vx-btn` + `.vx-btn-primary /
-secondary / -ghost / -danger / -new` (`vindex.css`, oko :8832 „4 kanoničke klase"),
sa radiusom 2px umesto 6px.

**Stanja:** `:hover` postoji svuda. **`:focus` / `:focus-visible` — 0 deklaracija u
`landing.html`.** `button { outline: none; }` (:46) **uklanja i podrazumevani fokus
prsten bez zamene** — landing je nenavigabilan tastaturom bez vidljivog fokusa.
`:disabled` — ne postoji. `:active` — ne postoji.

### 2.2 Kartice

| Klasa | Lokacija | Karakteristike |
|---|---|---|
| `.kako-step` | `:326-334` | **svetla**: `#fff` na `#eef3f9`, `radius:14px`, `border:1px rgba(0,0,0,0.06)`, `box-shadow:0 2px 12px rgba(0,0,0,0.05)`; hover → `0 8px 32px rgba(0,153,187,0.12)` + `translateY(-3px)` |
| `.fn-card` | `:373-378` | **tamna**: `rgba(255,255,255,0.018)`, bez radiusa (nasleđuje od `.fn-grid`), hover → `rgba(0,212,255,0.04)` |
| `.fn-grid` | `:364-372` | trik: `gap:2px` + `background:var(--bd-1)` + `overflow:hidden` → linije umesto ivica |
| `.fn-full` | `:379` | `grid-column: 1 / -1` |
| `.zasto-card` | `:429-436` | `border:1px var(--bd-teal)`, `background:var(--teal-lo)`, `radius:14px`; hover → `--teal-md` + `--teal-hi` |
| `.cen-card` | `:478-503` | tri varijante: `.free` (`opacity:0.75`), `.pro` (teal ivica + **dupli glow** `0 0 60px` / `0 0 120px`), `.firma` (ljubičasta `#8b5cf6`) — **CSS živ, HTML uklonjen** |

### 2.3 Navigacija

`landing.html:753-766` (`.lp-header` / `.lp-nav`)

- `position: sticky; top:0; z-index:100` (:61-63)
- `backdrop-filter: blur(18px)` + `-webkit-` prefiks (:64-65)
- `background: rgba(1,3,8,0.82)` (:66) — poluprovidna, ne `--void`
- `border-bottom: 1px solid var(--bd-1)` (:67)
- `height: 64px`, `max-width: 1280px`, `padding: 0 32px` (:70-76)
- logo `.lp-logo` — `--font-brand` 700, `1.55rem`, sa `<em>` u teal (:78-85)

**Nalaz — navigacija je razbijena:** tri stavke, **dve vode na isti anchor**:

```
<li><a href="#funkcije">Funkcije</a></li>
<li><a href="#funkcije">Web3</a></li>          ← isti cilj
<li><a href="#funkcije">Dokumentacija</a></li> ← isti cilj, sekcija ne postoji
```
(`landing.html:757-759`)

Mobilni drawer (`:769-783`) ima **drugačiji** skup linkova: Funkcije / Kako radi /
Zašto Vindex. Desktop i mobilni meni se ne poklapaju.

### 2.4 Footer

`landing.html:1051-1098` — grid `1.6fr 1fr 1fr 1fr 1fr` (:545), 5 kolona:
brend · Proizvod · Baza · Protokol · Vindex.

**Nalaz — 9 od 20 linkova je `href="#"`** (mrtvi): Zakoni RS, Sudska praksa, Web3 MiCA,
Dokumentacija, Arhitektura, Bezbednost, API, O nama, Kontakt.
Preostalih 10 vode na `#funkcije`.

**Nalaz — nula linkova ka pravnim stranicama.** `landing.html` ne linkuje
`/privacy`, `/terms`, `/dpa`, `/ai-disclosure`, `/security`, `/status`, `/bezbednosni-list`
ni `/pricing`. Stavka „Bezbednost" u footeru je `href="#"`, iako `/security` postoji.

`.footer-bottom` (:1093-1096) — `--font-mono`, `0.75rem`, `© MMXXVI · Vindex AI`
(rimski brojevi) i `vindex.rs`.

### 2.5 Forme

**`landing.html` nema nijednu formu.** Nema `<form>`, `<input>` (osim skrivenog
checkbox-a u mrtvom cenovnik-toggle-u `:462`), nema `<textarea>`, nema polja za kontakt
ni za waitlist. **Nula sabirnih tačaka** — jedina konverzija je odlazak na `/app`.

Waitlist forma postoji, ali **samo u aplikaciji**: `index.html:4155-4163` (`wl-success-*`)
+ `index.html:4187` `onclick="wl_open()"`, backend `routers/waitlist.py:143`
`POST /waitlist/prijava` (bez autentifikacije, registrovan u `api.py:745`).

### 2.6 Ostale komponente

| Komponenta | Lokacija | Napomena |
|---|---|---|
| `.section-label` | `:120-129` | mono, uppercase, `0.18em` tracking, teal |
| `.hero-eyebrow` | `:175-184` | ista ideja, `0.16em` |
| `.fn-card-tag` | `:380-390` | ista ideja, `0.56rem`, `opacity:0.75` |
| `.step-num` | `:335-343` | mono, `01/02/03` |
| `.fn-sub-item` | `:402-411` | red sa `›` ili `—` strelicom u teal |
| `.hero-sphere` | `:225-246` | 340px krug, `border-radius:50%`, radial gradient, **4s breathe animacija** |
| `.sphere-grid` | `:247-296` | 2×2 mreža sa mono brojevima `4+ / 0 / ∞ / 7` |
| `.mobile-drawer` | `:575-639` | fiksni overlay, `blur(4px)`, slide-down `0.22s` |
| `.mobile-sticky-cta` | `:642-661` | vidljiv samo ≤768px, `linear-gradient` maska |

### 2.7 Ikonografija

`landing.html` koristi **isključivo inline SVG** sa `stroke="currentColor"`,
`stroke-width="1.5"` (dekorativne) ili `2` (UI kontrole), `viewBox="0 0 24 24"`.
Lucide-stil, bez biblioteke. **Nula emoji u landingu.**

Ali u ostatku frontenda zabranjene ikone POSTOJE:

| Ikona | Lokacija | Kontekst |
|---|---|---|
| `⚖` (`%E2%9A%96`) | **`index.html:16`** | **favicon aplikacije**, ugrađen u SVG data URI |
| `⚖` (`&#x2696;`) | `index.html:4197` | ikona kartice „Predmeti" na pre-auth ekranu |
| `⚖️` | `static/status.html:46` | logo status stranice |
| `⚡` `🤖` `🗄️` `🔍` | `static/status.html:62` | ikone komponenti sistema |
| `⚙️` | `static/status.html:96` | fallback ikona |

`static/status.html` je **najgori prekršilac** pravila o generičkim ikonama.
Dozvoljeni `✓` i `⚠` se koriste ispravno u `bezbednosni-list.html` (CSS `content`),
`dpa.html:95` i `pricing.html`.

---

## 3. POSTOJEĆE JAVNE STRANICE

Osam stranica van aplikacije. **Nijedna ne koristi `static/vindex.css`, nijedna nema
`:root` blok, nijedna ne učitava Google Fonts.** Sve su 100% inline `<style>`.

| Stranica | Fajl | Ruta | Svrha | Podloga / tekst / akcenat | Font | Nasleđujemo? |
|---|---|---|---|---|---|---|
| Politika privatnosti | `privacy.html` | `/privacy` | ZZPL/GDPR obaveze, prava lica, rokovi čuvanja | `#fff` / `#1a1a2e` / `#2563eb` | Georgia | **DA — pravna obaveza** |
| Uslovi korišćenja | `terms.html` | `/terms` | ugovorne strane, ograničenje odgovornosti za AI | `#fff` / `#1a1a2e` / `#2563eb` | Georgia | **DA — pravna obaveza** |
| AI Disclosure | `static/ai-disclosure.html` | `/ai-disclosure` | koji model, šta se šalje, opt-out | `#fff` / `#1a1a2e` / `#2563eb` | Georgia | **DA** |
| DPA | `static/dpa.html` | `/dpa` | ugovor o obradi podataka, aneksi, potpis | `#fff` / `#1a1a2e` / `#1d4ed8` | Georgia | **DA — B2B blokator bez njega** |
| Security whitepaper | `static/security.html` | `/security` | 15 sekcija tehničke bezbednosti za revizore | `#fff` / `#1a1a2e` / `#2563eb` | Georgia | **DA** |
| Bezbednosni list | `static/bezbednosni-list.html` | `/bezbednosni-list` | A4 one-pager, tri stuba zaštite advokatske tajne | `#fff` / `#1a1a2e` / `#2563eb` | Georgia, `11px`/`1.38` | **DA** |
| Status servisa | `static/status.html` | `/status` | živi status komponenti + incidenti | `#0a0c10` / `#e2e8f0` / **`#89c8ff`** | `-apple-system` sans | **DA, ali traži redizajn** |
| Cenovnik | `pricing.html` | `/pricing` | 4 plana + tabela + FAQ | `#060e1a` / `#e2e8f0` / `#00d4ff` | `-apple-system` sans | **NE — v. §8** |

### 3.1 Tri odvojena vizuelna sistema

1. **Beli „Georgia dokument"** — 6 stranica (privacy, terms, ai-disclosure, dpa,
   security, bezbednosni-list). Namerno print-orijentisan; `max-width: 780px` na `body`,
   radius 6-8px, akcenat `#2563eb` (osim dpa: `#1d4ed8`).
2. **Tamni sistemski panel** — `status.html`. `max-width: 680px`, radius 9-12px,
   akcenat `#89c8ff`.
3. **Tamni marketing** — `pricing.html`. `max-width: 1160px`, radiusi 11/12/14/20/22px,
   akcenat `#00d4ff` + ljubičasti gradijent `#7c3aed` koji ne postoji nigde drugde.

**Četiri različita „plava" akcenta:** `#2563eb` (4×), `#1d4ed8` (dpa), `#89c8ff` (status),
`#00d4ff` (pricing + landing + app).

### 3.2 Međusobno povezivanje

| Stranica | Ima `<nav>` | Ima `<footer>` sa linkovima | Linkuje ka |
|---|---|---|---|
| `privacy.html` | DA | DA | `/`, `/terms`, `/privacy`, `/ai-disclosure`, `/dpa` |
| `terms.html` | DA | DA | isto |
| `ai-disclosure.html` | DA | DA | isto |
| `bezbednosni-list.html` | ne | DA | `/security`, `/dpa`, `/privacy`, `/ai-disclosure` |
| `security.html` | ne | footer bez linkova | `/status` i `/dpa` samo kao **plain tekst**, ne `<a>` |
| `status.html` | ne | footer bez linkova | **nula `href` na celoj stranici** |
| `pricing.html` | DA (3 linka) | **nema footer uopšte** | `/`, `/app` |
| `landing.html` | DA | DA | **nijedna od gornjih** |

**Nalaz:** pravne stranice čine povezan klaster (`privacy` ↔ `terms` ↔ `ai-disclosure`
↔ `dpa`), a komercijalne (`landing`, `pricing`) su potpuno odvojene. Veza postoji samo
u jednom smeru — pravne stranice linkuju `/`, ali `/` ne linkuje nijednu od njih.
Pre-auth ekran aplikacije (`index.html:4223-4226`) linkuje samo `/privacy` i `/terms`.

### 3.3 `status.html` — jedina dinamička

`static/status.html:83`: `var r = await fetch('/api/status/public');` — poziva se odmah
i `setInterval(load, 60000)`. Backend: `routers/status_page.py` (`GET /api/status/public`,
bez autentifikacije). Čita `d.status`, `d.checked_at`, `d.components[]` (`naziv`,
`status`, `ms`) i `d.incidents[]`. **Nema uptime procenta** — samo status badge i
latencija u ms. Boje statusa: `#4ade80` / `#fbbf24` / `#f87171` / `#fb923c`.

---

## 4. RUTIRANJE

### 4.1 Javne HTML rute

| Ruta | Metod | Fajl koji se servira | `Cache-Control` | Lokacija | Javno |
|---|---|---|---|---|---|
| `/` | GET, HEAD | `landing.html` | **NIJEDAN — nije postavljen** | `api.py:1500-1506` | javno |
| `/privacy` | GET | `privacy.html` | `public, max-age=86400` | `api.py:1509-1514` | javno |
| `/terms` | GET | `terms.html` | `public, max-age=86400` | `api.py:1542-1547` | javno |
| `/status` | GET | `static/status.html` | `no-cache` | `api.py:1516-1519` | javno |
| `/security` | GET | `static/security.html` | `public, max-age=3600` | `api.py:1521-1524` | javno |
| `/dpa` | GET | `static/dpa.html` | `public, max-age=3600` | `api.py:1526-1529` | javno |
| `/ai-disclosure` | GET | `static/ai-disclosure.html` | `public, max-age=3600` | `api.py:1531-1534` | javno |
| `/bezbednosni-list` | GET | `static/bezbednosni-list.html` | `public, max-age=3600` | `api.py:1536-1539` | javno |
| `/pricing` | GET | `pricing.html` | `public, max-age=3600` | `api.py:1550-1555` | javno, `include_in_schema=False` |
| `/app` | GET | `index.html` (iz memorije) | `no-cache, no-store, must-revalidate` + `Pragma`, `Expires:0`, `X-Build` | `api.py:2354-2356` → `:2337-2351` | **javno servira HTML** |
| `/offline` | GET | `index.html` (isto) | isto | `api.py:2483-2485` | javno |
| `/portal` | GET | `client_portal.html` | `no-cache` | `api.py:2359-2365` | javno, pristup preko tokena |
| `/sw.js` | GET | `static/sw.js` | `no-cache, no-store, must-revalidate` + `Service-Worker-Allowed: /` | `api.py:2466-2474` | javno |
| `/manifest.json` | GET | `static/manifest.json` | (nasleđuje middleware) | `api.py:2477-2480` | javno |
| `/robots.txt` | GET | inline `PlainTextResponse` | — | `api.py:2329-2334` | javno |
| `/health` | GET, HEAD | JSON | — | `api.py:1558-1574` | javno |
| `/api/version` | GET, HEAD | JSON, **namerno javno** | — | `api.py:1577+` | javno |
| `/api/status/public` | GET | JSON | — | `routers/status_page.py` | javno |
| `/waitlist/prijava` | POST | JSON | — | `routers/waitlist.py:143` | **javno, bez auth** |

**Ukupno 12 javnih HTML stranica** (`/`, `/privacy`, `/terms`, `/status`, `/security`,
`/dpa`, `/ai-disclosure`, `/bezbednosni-list`, `/pricing`, `/app`, `/offline`, `/portal`).

**NALAZ — `/` je jedina ruta bez `Cache-Control`.** `api.py:1505` je
`return FileResponse(path)` bez `headers=`. Middleware `security_headers`
(`api.py:1136-1142`) postavlja `Cache-Control` **samo** za putanje koje počinju sa
`/static/`. Rezultat: `/` se oslanja isključivo na `ETag`/`Last-Modified` koje
Starlette generiše, dok svaka druga javna stranica ima eksplicitnu politiku.

**NALAZ — dijagnostičke rute su javne:** `GET /test-pinecone` (`api.py:2232`) i
`GET /test-zdi` (`api.py:2264`) nemaju `include_in_schema=False` niti auth. Nisu
relevantne za sajt, ali su vidljive u `/docs` i indeksibilne.

**NALAZ — `robots.txt` nema `Sitemap:`** (`api.py:2331-2333`):
`User-agent: *\nAllow: /\nDisallow: /api/\n`. Sve javne stranice su dozvoljene za
indeksiranje, ali nema mape sajta.

### 4.2 Statički fajlovi

`api.py:814-817`:
```python
if os.path.exists(BASE_DIR / "static"):
    app.mount("/static", _StaticFiles(directory=str(BASE_DIR / "static")), name="static")
```

**Ceo `static/` direktorijum je javno dostupan bez autentifikacije.** To uključuje:
`vindex.js` (1,26 MB — kompletna logika aplikacije), `vindex.css` (477 KB),
`vindex.js.bak` (876 KB — **stara verzija, netrekovana, i dalje servirana**),
`supabase.min.js`, sve `.html` pravne stranice, ikone, i
`Vindex-AI-Bezbednosni-List.pdf`.

Drugi mount: `api.py:826-831` → `/word_addin` iz `integrations/word_addin`.

### 4.3 Cache-busting

`api.py:1484-1495` — `index.html` se učita jednom pri startu, i **regex
`_re.sub(r'\?v=\w+', f"?v={_GIT_HASH}", content)`** prepiše svaki `?v=` parametar u
kratki commit SHA. `_GIT_HASH` dolazi iz `shared/build_info.py` (bez `git` binarnog
fajla, jer `python:3.11-slim` ga nema); kad SHA nije razrešen, prefiks je `nover-`.

**`landing.html` NE prolazi kroz taj mehanizam** — `api.py:1503-1505` čita fajl sa
diska pri svakom zahtevu i ne dira sadržaj. Zato landing danas nema nijednu
`/static/` referencu; ako je novi sajt uvede, verzionisanje mora biti ručno.

---

## 5. GRANICA SAJT / APLIKACIJA

```
                        ISTI FastAPI PROCES, ISTI ORIGIN, ISTI CSP
   ┌────────────────────────────────────┬────────────────────────────────────┐
   │            SAJT                    │           APLIKACIJA               │
   ├────────────────────────────────────┼────────────────────────────────────┤
   │ /            landing.html          │ /app        index.html             │
   │ /privacy     privacy.html          │ /offline    index.html             │
   │ /terms       terms.html            │ /portal     client_portal.html     │
   │ /status      static/status.html    │                                    │
   │ /security    static/security.html  │ + /static/vindex.js  (1,26 MB)     │
   │ /dpa         static/dpa.html       │ + /static/vindex.css (477 KB)      │
   │ /ai-disclosure                     │ + /static/supabase.min.js          │
   │ /bezbednosni-list                  │ + 6 CDN skripti                    │
   │ /pricing     pricing.html          │                                    │
   ├────────────────────────────────────┼────────────────────────────────────┤
   │ 0 KB JS zavisnosti                 │ ~2 MB JS/CSS                       │
   │ inline <style> + inline <script>   │ eksterni CSS/JS sa ?v=SHA          │
   │ nema auth                          │ auth je KLIJENTSKI, ne serverski   │
   │ nema Supabase                      │ Supabase createClient u vindex.js  │
   └────────────────────────────────────┴────────────────────────────────────┘
                                    ↑
                    Service Worker (scope "/") pokriva OBE strane
```

### 5.1 Gde tačno prestaje sajt

Granica je **ruta `/app`**, i ona je isključivo **frontend granica** — ne postoji
serverska zaštita.

`api.py:2354-2356` servira `index.html` **svakome**, bez ikakve provere:

```python
@app.get("/app")
def serve_html():
    return _serve_index_html()
```

Zaštita se dešava tek u pretraživaču: `index.html:4166` sadrži `<div id="vx-landing">`
— pre-auth ekran koji se prikazuje dok Supabase sesija ne postoji. Podaci su zaštićeni
na nivou API-ja (JWT + RLS), ne na nivou HTML-a.

**Posledica za sajt:** `/app` nije „iza logina" u smislu koji bi projektant sajta
očekivao. To je javna HTML stranica od 422 KB koja sadrži i marketing sadržaj
(`vx-land-*`) i celu aplikaciju. Svaka odluka o sajtu koja pretpostavlja
„sajt = javno, /app = privatno" je pogrešna.

### 5.2 Prijava

| Šta | Gde | Vrednost |
|---|---|---|
| SDK | `index.html:31` | `<script src="/static/supabase.min.js?v=2">` (self-hostovan, 204 KB) |
| URL projekta | `static/vindex.js:235` | `SUPABASE_URL = 'https://czsxymueizfqrbbgqqob.supabase.co'` |
| Ključ | `static/vindex.js:236` | `SUPABASE_ANON_KEY = '…'` |
| **Tip ključa** | — | **`publishable`** (novi format, prefiks `sb_publishab…`), **NE** legacy anon JWT (`eyJ…`), **NE** `service_role` |
| Inicijalizacija | `static/vindex.js:241-242` | `_supa = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)` |
| Registracija | `api.py:2491+` (`RegisterReq`) | dodeljuje `BESPLATNI_KREDITI = 15` (`api.py:356`) jednom, bez obnove |
| Otvaranje modala | `index.html:4169, 4188` | `openModal()` |
| Waitlist | `index.html:4187` `wl_open()` | → `POST /waitlist/prijava` (`routers/waitlist.py:143`) |

Provereno: nijedan privilegovan ključ (`service_role`, `sb_secret_`, `eyJ…`) nije
u frontendu. Ime promenljive `SUPABASE_ANON_KEY` je zavaravajuće — ključ nije anon JWT
— ali sam ključ je namenjen izlaganju u pretraživaču.

---

## 6. OGRANIČENJA

### 6.1 Content Security Policy

`api.py:1149-1161`, postavlja se u middleware-u na **svaki** odgovor:

```
default-src  'self';
script-src   'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com;
style-src    'self' 'unsafe-inline' cdnjs.cloudflare.com fonts.googleapis.com;
font-src     'self' cdnjs.cloudflare.com fonts.gstatic.com data:;
img-src      'self' data: blob:;
connect-src  'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com
             https://api.emailjs.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com
             https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com;
worker-src   'self' blob:;
frame-ancestors 'none';
report-uri   /api/security/csp-report
```

**Šta sajt SME:**

| Sme | Zašto |
|---|---|
| inline `<style>` | `style-src 'unsafe-inline'` |
| inline `<script>` | `script-src 'unsafe-inline'` |
| Google Fonts CSS + fajlovi | `style-src fonts.googleapis.com` + `font-src fonts.gstatic.com` |
| slike sa istog origina, `data:`, `blob:` | `img-src 'self' data: blob:` |
| inline SVG | pokriveno `img-src`/dokumentom |
| Service Worker | `worker-src 'self' blob:` |

**Šta sajt NE SME — ovo su tvrde granice:**

| Ne sme | Posledica za sajt |
|---|---|
| **eksterne slike** (`img-src` nema nijedan spoljni host) | svaki screenshot, logo, OG slika mora biti **self-hostovan** u `static/` |
| **eksterni `<iframe>`** — `frame-src` nije deklarisan → pada na `default-src 'self'` | **nema YouTube / Vimeo / Loom ugradnje**; demo video mora biti self-hostovan `<video>` |
| **eksterni `<video>`/`<audio>`** — `media-src` nije deklarisan → `default-src 'self'` | video ide u `static/` i troši propusni opseg servera |
| **eksterna analitika** (`connect-src` nema GA/Plausible/PostHog) | merenje poseta zahteva izmenu CSP-a ili self-hostovan endpoint |
| **eksterni fontovi van Google/cdnjs** | Adobe Fonts, Fontshare, itd. — blokirani |
| **ugradnja Vindexa u tuđi sajt** | `frame-ancestors 'none'` |

**Nalaz — konflikt header-a:** `X-Frame-Options: SAMEORIGIN` (`api.py:1145`) i
`frame-ancestors 'none'` (`api.py:1159`) su u koliziji. CSP je stroži i pobeđuje u
modernim pretraživačima; `X-Frame-Options` važi samo u starijim. Stvarno ponašanje:
**nikakvo uokvirivanje, ni sa istog origina.**

### 6.2 Ostali security header-i

`api.py:1144-1148`:

| Header | Vrednost |
|---|---|
| `Permissions-Policy` | `microphone=(self), camera=(), geolocation=(), payment=()` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |

### 6.3 Service Worker

`static/sw.js`, `CACHE_NAME = "vindex-v123"` (`sw.js:4`), servira se sa **root scope-a**
(`api.py:2466-2474`, `Service-Worker-Allowed: /`).

**Scope `/` pokriva i sajt, ne samo aplikaciju.**

| Tip zahteva | Strategija | Linija |
|---|---|---|
| Supabase domeni | preskače se, browser rukuje | `sw.js:39-44` |
| `/api/`, `/strategija/`, `/billing/`, … (12 prefiksa) | network-first + 503 JSON fallback | `:47-74` |
| Google Fonts, cdnjs, jsdelivr, unpkg | **cache-first** | `:77-97` |
| **HTML navigacija (`mode === "navigate"`)** | **network-first, ali svaki uspešan odgovor se UPISUJE u keš** | `:100-113` |
| ostali statički fajlovi | stale-while-revalidate | `:116-129` |

**Šta to znači za novi sajt:**

1. `/` je `mode: "navigate"` → **novi `landing.html` će biti keširan u
   `vindex-v123`** čim ga posetilac učita. Fallback pri offline stanju vraća keširanu
   verziju, pa zastareo landing može opstati.
2. Google Fonts idu **cache-first bez isteka** — promena skupa fontova neće se videti
   kod postojećih posetilaca dok se `CACHE_NAME` ne promeni.
3. `PRECACHE` (`sw.js:6-12`) je `/offline`, `supabase.min.js`, `manifest.json`, dve ikone.
   **`/` i `landing.html` nisu u precache listi** — keširaju se tek pri poseti.
4. Stari kešovi se brišu tek u `activate` (`:24-30`), i to samo oni čiji ključ nije
   jednak trenutnom `CACHE_NAME`. **Bump `CACHE_NAME` je jedini mehanizam invalidacije.**

### 6.4 Pravilo `CACHE_NAME`

`tests/test_wave11_release_identity.py:52`:

```python
FRONTEND_ARTEFAKTI = ("static/vindex.js", "index.html")
```

`:111` (`_prekrsaj`): `dirnuti = sorted(set(izmenjeni) & set(FRONTEND_ARTEFAKTI))` —
**tačan presek putanja**, ne glob, ne prefiks.

Test `test_frontend_izmena_u_HEAD_commitu_mora_podici_cache_name` (`:159`) radi nad
`git diff HEAD~1 HEAD` i traži: ako je commit dirnuo `static/vindex.js` ili
`index.html`, mora u **istom commitu** podići `CACHE_NAME`.

**`landing.html` NIJE u toj listi.** Zamena landinga sama po sebi ne aktivira pravilo.
Ali čim isti commit dirne `index.html` ili `static/vindex.js`, bump postaje obavezan.

**Ovo je nedostatak pokrivenosti, ne prednost.** SW keš navigacije (`sw.js:100-113`)
keširа `/`, pa novi landing jeste podložan zastarelosti — a jedini test koji bi to
uhvatio ga ne prati.

### 6.5 Testovi koji čuvaju frontend

**Ni jedan test u repou ne čita, ne parsira i ne pogađa `landing.html`.**
Verifikovano: jedina referenca na `landing.html` u praćenom Python/JS/YAML kodu je
`api.py:1503`, plus `build_new_ui.py:1785` (generator starog UI-ja, nije u CI).

`pytest.ini` → `testpaths = tests`; CI (`tests.yml`) pokreće `pytest tests/ -q -rs`
na Python 3.11 i 3.13. Root `test_*.py` fajlovi **nisu** u CI.

| Test | Fajl : linija | Šta asertuje | Pada pri zameni landinga? |
|---|---|---|---|
| `test_frontend_izmena_u_HEAD_commitu_mora_podici_cache_name` | `tests/test_wave11_release_identity.py:159` | `assert problem is None` nad presekom `("static/vindex.js","index.html")` | **MOŽDA** — samo ako isti commit dirne i te fajlove |
| `test_cache_name_odgovara_obrascu_vindex_v_broj` | `tests/test_wave11_release_identity.py:140` | regex `vindex-v(\d+)`, `int(m.group(1)) > 0` | NE |
| `test_ng_detektor_hvata_stvarni_istorijski_propust` | `tests/test_wave11_release_identity.py:203` | nad commit-om `f87f9e45`, `assert "vindex-v123" in problem` | NE |
| `test_ng_detektor_ne_prijavljuje_uredan_bump` | `tests/test_wave11_release_identity.py:220` | commit `966e0e77` | NE |
| `test_sw_cache_bumped` | `tests/test_iron_lawyer_frontend_fixes.py:177` | `int(m.group(1)) >= 120` | NE |
| `test_sw_cache_bumped_for_this_sprints_frontend_change` | `tests/test_lambda001_beta_readiness_fixes.py:435` | `int(m.group(1)) >= 92` | NE |
| `test_build_identity` (`sw_cache`) | `tests/test_build_identity.py:213` | `val.startswith("vindex-v")` | NE |
| `test_sw_no_longer_sets_dead_offline_flag` | `tests/test_phoenix_mission_015_low_severity_sweep.py:341` | `"offline: true" not in sw_js` | NE |
| `TestSecurityHeaders::test_csp_present` | `tests/test_api_security.py:48` | `"default-src" in csp`, nad **`/health`** | NE |
| `TestSecurityHeaders::test_x_frame_options` | `tests/test_api_security.py:44` | `== "SAMEORIGIN"`, nad `/health` | NE |
| `TestPublicPages` | `tests/test_api_security.py:84-99` | `/privacy` i `/terms`: `200`, `text/html`, `"ne predstavljaju pravni savet" in r.text.lower()` | NE — ali **blokira redizajn tih dveju stranica bez te rečenice** |
| `TestRobots::test_robots_txt` | `tests/test_api_security.py:121` | `"User-agent" in r.text`, `"/api/" in r.text` | NE |
| `test_vindex_js_is_syntactically_valid` | `tests/test_iron_lawyer_frontend_fixes.py:23` | `node --check static/vindex.js`, `returncode == 0` | NE |
| razne `index.html` asercije | `tests/test_iron_lawyer_frontend_fixes.py:123,129,135,156` | npr. `assert 'id="nav-search-btn"' not in INDEX_HTML` | NE |
| `test_frontend_undefined_globals` | `tests/test_frontend_undefined_globals.py:184` | skenira `index.html` + `vindex.js`, **ne `landing.html`** | NE |
| `test_router_registration` | `tests/test_router_registration.py:27` | `assert not memory_paths` | NE |

**Nijedan test ne pogađa rutu `/` HTTP-om.** Pretraga `client.get("/")` u `tests/` →
nula pogodaka; svi `"path": "/"` su ASGI `scope` dict-ovi za unit-testove middleware-a.

**Nijedan test ne proverava zabranjene ikone/emoji u HTML-u.** Grep za
`emoji|generic icon|lucide|feather|data-icon` u `tests/` → nula relevantnih pogodaka.
Zato `⚖` u `index.html:16` i `⚡🤖🗄️🔍⚙️` u `status.html:62` nikad nisu prijavljeni.

### 6.6 CI gejtovi

| Workflow | Job | Relevantnost za sajt |
|---|---|---|
| `tests.yml` | `pytest` (3.11 + 3.13) | sve gore; nema landing gejta |
| `production-runtime.yml` | `compile-on-production-python`, `import-and-test`, `production-docker-build` | samo Python; `Dockerfile:17` je `COPY . .` pa novi landing ulazi u image bez provere |
| `security.yml` | **`secret-scan` (gitleaks, BLOKIRAJUĆI)** | jedini koji „vidi" `landing.html` — pašće ako novi landing sadrži nešto što liči na ključ (`eyJ…`, API token) |
| `security.yml` | `sast-core` / `semgrep-core` (blokirajući) | scope je isključivo Python (`api.py main.py routers/ shared/ security/ services/ app/`) |
| `security.yml` | `dependency-scan` (pip-audit, blokirajući) | nevezano |

Napomena: `secret-scan` je **već crven** zbog nesupresovanog istorijskog nalaza
(iscureli OpenAI ključ iz prvog commita) — to nije posledica sajta, ali znači da se
crveni CI ne sme koristiti kao signal.

---

## 7. VIZUELNI MATERIJAL

### 7.1 Šta postoji

| Fajl | Veličina | Šta je | Upotrebljivo za sajt |
|---|---|---|---|
| `static/icon-192-v3.png` | 4,4 KB | PWA ikona 192px | **DA** — jedini živi logotip |
| `static/icon-512-v3.png` | 14 KB | PWA ikona 512px | **DA** |
| `static/icon-192.png`, `icon-512.png`, `icon-192-v2.png`, `icon-512-v2.png` | 27-87 KB | starije verzije | ne — `manifest.json` koristi `-v3` |
| `assets/lady_justice.jpg` | 189 KB | fotografija „boginja pravde" | **NE** — stock alegorija, direktno na listi zabrana (`VISUAL_BLUEPRINT.md:49`) |
| `screenshot_login.png` (root) | 313 KB | snimak **ekrana za prijavu**, 2026-06-08 | **NE** — prijava, ne proizvod; 2 meseca star |
| `badge_output.png` (root) | 33 KB | test artefakt badge komponente | ne |
| `integrations/word_addin/icon-16/32/80.png` | male | ikone Word add-ina | ne |
| `static/Vindex-AI-Bezbednosni-List.pdf` | 95 KB | PDF bezbednosnog lista | **DA** — postoji za preuzimanje |
| `Vindex_AI_Roadmap.pdf`, `Vindex_AI_Skripta.pdf` (root) | 78 / 113 KB | interni dokumenti | ne — nisu za javnost |

### 7.2 Šta NE postoji

| Nedostaje | Posledica |
|---|---|
| **Nijedan snimak proizvoda** | v. 7.3 |
| **Logo u vektorskom obliku (SVG)** | jedini logo je PNG rasterska ikona; „logotip" na sajtu je **tekst** `Vindex <em>AI</em>` u Cormorant Garamond-u (`landing.html:755`) |
| **OG slika** | nema `og:image` nigde |
| **Favicon za landing** | `landing.html` nema `rel="icon"` — 0 pojava |
| **`og:` / `twitter:` meta tagovi** | 0 pojava u `landing.html`; deljenje linka na LinkedIn/Twitter daje prazan pregled |
| **`rel="canonical"`** | 0 pojava u `landing.html` (`pricing.html` ga ima, pokazuje na `vindex-ai.com` — **drugi domen** nego `vindex.rs` u footeru) |
| **`<link rel="manifest">` u landingu** | 0 pojava |
| **`Sitemap:` u robots.txt** | `api.py:2331-2333` |
| **`static/screenshot-desktop.png` i `static/screenshot-mobile.png`** | **`manifest.json:59-73` ih deklariše, a fajlovi ne postoje** → PWA install prompt na Androidu ne prikazuje snimke |

### 7.3 `VINDEX_AI_SCREENSHOT_PLAN.md` — koliko je urađeno

Plan traži tri snimka. **Urađeno: nula.**

| Snimak | Traženo | Status |
|---|---|---|
| `context.png` | prikaz predmeta: naziv, stranke, ≥3 činjenice, ≥1 rok, lista dokumenata | **NE POSTOJI** |
| `provenance.png` ← plan ga zove najvažnijim | AI odgovor sa `rag-source-info` oznakom izvora | **NE POSTOJI.** Uslov iz plana („potvrditi vidljivost, P0 stavka 1") nikad nije zatvoren — `FINAL_WEBSITE_READINESS.md:17` beleži stanje `API-AVAILABLE / UI-MISSING` |
| `deadline.png` | rok izvučen iz dokumenta sa vezom ka izvoru | **NE POSTOJI** |
| Hero vizuel | preporuka: isečak `provenance.png` | **NE POSTOJI** |
| Hod kroz proizvod (video, P1) | traži sintetički predmet | **NE POSTOJI** — sintetički predmet ne postoji (`RISKS.md`, blokator 5) |

Preduslov iz plana — „svi se snimaju **isključivo** nad sintetičkim predmetom" — takođe
nije ispunjen: sintetički demo predmet ne postoji u repou.

### 7.4 Ključno ograničenje

**Sajt danas ne može da pokaže nijednu sliku proizvoda.**

Tri nezavisna razloga:

1. Snimci ne postoje (7.3).
2. Ne mogu se napraviti bez sintetičkog predmeta — jer plan zabranjuje stvarne i
   „stvarnima slične" podatke (`SCREENSHOT_PLAN.md:61`).
3. Najvažniji snimak (`provenance.png`) je **tehnički nemoguć danas** — prikaz izvora
   u UI-ju nije uključen (`FINAL_WEBSITE_READINESS.md:17, 74`).

Blueprint predviđa taj scenario (`VISUAL_BLUEPRINT.md:41-42`): **dijagrami umesto snimaka**,
uz izričitu zabranu mockup ekrana koji prikazuju nepostojeći interfejs. CSP to dozvoljava
bez izuzetka — inline SVG prolazi kroz `img-src 'self' data:`.

---

## 8. RIZICI PRI ZAMENI `landing.html`

Poređano po tome koliko brzo puca i koliko boli.

### 8.1 Puca odmah — tehnički

| # | Rizik | Mehanizam | Ublažavanje |
|---|---|---|---|
| R1 | **Service Worker servira stari landing** | `sw.js:100-113` keširа svaki uspešan `navigate` odgovor u `vindex-v123`. Posetilac koji je video stari `/` dobija ga iz keša kad je mreža spora ili nedostupna. Bump `CACHE_NAME` je jedini brisač (`sw.js:24-30`). | Podići `CACHE_NAME` u `static/sw.js:4` u istom commit-u kao zamenu landinga — **iako to nijedan test ne traži** (`FRONTEND_ARTEFAKTI` ne sadrži `landing.html`) |
| R2 | **Novi landing nema cache-busting** | `api.py:1503-1505` čita fajl direktno; `?v=` rewrite (`api.py:1490`) važi **samo** za `index.html` | Ako novi landing linkuje `/static/*`, verziju upisati ručno; ili ostati na inline CSS/JS kao sada |
| R3 | **`/` je jedina ruta bez `Cache-Control`** | `api.py:1505` `FileResponse(path)` bez `headers=`; middleware pokriva samo `/static/` | Nije regresija zamene, ali je zatečeni propust koji zamena čini vidljivim |
| R4 | **`secret-scan` (gitleaks, blokirajući)** | `security.yml`, `fetch-depth: 0` — pašće ako novi landing sadrži bilo šta nalik ključu | Ne stavljati Supabase/API ključeve u landing (trenutni landing je čist: 0 pogodaka za `eyJ`/`supabase`/`apikey`) |
| R5 | **CSP tiho blokira eksterne resurse** | `img-src 'self' data: blob:` — bez izuzetka; `frame-src` nedeklarisan | Sve slike i video self-hostovati u `static/`; nema YouTube ugradnje |

### 8.2 Ne puca, ali gubi se — sadržaj i veze

| # | Rizik | Šta se konkretno gubi |
|---|---|---|
| R6 | **Gubitak jedinog ulaza u `/app`** | Svih 5 `href="/app#register"` (`:761, 781, 787, 799, 1046`) je u landingu. Ako novi landing nema ekvivalent, jedini put u aplikaciju je da korisnik zna URL. |
| R7 | **Gubitak sidra `#funkcije`, `#kako`, `#zasto`** | 12 internih linkova zavisi od njih. Ako neko negde deli duboki link — puca tiho. |
| R8 | **Gubitak jedinog `<meta name="description">`** | `landing.html:6` je jedini opis za pretraživače na `/`. |
| R9 | **Mrtvi CSS ostaje ako se nasleđuje fajl** | `.cen-*` blok (`:449-522`, ~75 linija) je živ CSS za HTML koji je uklonjen commit-om `3381d59f`. Ljubičasti `#8b5cf6` sistem postoji **samo** ovde. Kopiranje CSS-a „za svaki slučaj" prenosi i to. |

### 8.3 Ostaje razbijeno posle zamene — zatečeni dugovi

Ovo zamena landinga **ne rešava**, i ako se ne adresira, novi sajt nasleđuje probleme.

| # | Problem | Lokacija | Zašto je važno |
|---|---|---|---|
| R10 | **`/pricing` je i dalje javan sa cenama** | `api.py:1550-1555` → `pricing.html` | Cenovnik je uklonjen iz landinga jer planovi nisu naplativi (`landing.html:1000-1038`). Ruta je preživela. Nov sajt bez cena + živa `/pricing` sa 4 plana = ista kontradikcija, samo skrivenija. |
| R11 | **Pre-auth ekran aplikacije protivreči landingu** | `index.html:4166-4227` | Landing: „Počni besplatno". `/app`: „Zatražite rani pristup — Ograničen broj mesta". Zamena landinga bez izmene `/app` samo pomera šav. |
| R12 | **Kontradiktorni brojevi** | `landing.html:905` „18 zakona" vs `index.html:4209` „847 zakona" | Bilo koji broj na novom sajtu mora se uskladiti sa pre-auth ekranom. |
| R13 | **Pravne stranice ostaju orfani** | `landing.html` ne linkuje nijednu | 6 pravnih stranica, 0 linkova sa `/`. GDPR/DPA vidljivost zavisi od toga da posetilac pogodi URL. |
| R14 | **Sedam vizuelnih sistema u proizvodu** | v. §1.4 i §3.1 | Landing (Jakarta/6-14px) · aplikacija (JetBrains Mono/2-4px) · beli Georgia dokument · tamni status panel · tamni pricing · `--vp-*` · `--vx-*`. Nov landing dodaje osmi ako se ne odluči koji je izvor istine. |
| R15 | **Zabranjene ikone u aplikaciji** | `index.html:16` (favicon `⚖`), `index.html:4197` (`⚖`), `status.html:46, 62, 96` (`⚖️⚡🤖🗄️🔍⚙️`) | Landing je čist. Favicon aplikacije nije. Nijedan test to ne hvata (§6.5). |
| R16 | **`--tx-3` pada WCAG AA** | `landing.html:24`, kontrast 2,44 : 1 | Ceo footer je ispod praga. Ako se paleta nasledi, nasleđuje se i propust. |
| R17 | **Nema `prefers-reduced-motion`** | `landing.html` — 0 blokova, 2 beskonačne `rAF` petlje | Blueprint to izričito traži (`VISUAL_BLUEPRINT.md:39`). |
| R18 | **`button { outline: none }` bez zamene** | `landing.html:46` | Nema `:focus-visible` nigde → nevidljiv fokus na tastaturi. |
| R19 | **`manifest.json` deklariše nepostojeće snimke** | `static/manifest.json:59-73` | `screenshot-desktop.png` / `screenshot-mobile.png` ne postoje. |
| R20 | **Dva domena u opticaju** | `landing.html:1056, 1095` `vindex.rs` vs `pricing.html` canonical `https://vindex-ai.com/pricing` | Kanonički domen nije odlučen. |
| R21 | **`static/vindex.js.bak` je javno servirana** | `api.py:817` mount + `static/vindex.js.bak` (876 KB) | Stara verzija cele aplikacije dostupna bez auth. Nije rizik zamene, ali je javno vidljiv artefakt na sajtu koji se predstavlja kao bezbedan. |

### 8.4 Šta NE puca — provereno

- Ruta `/` radi automatski: `api.py:1503-1505` proverava samo `path.exists()`.
  Nema hardkodovanog hash-a, veličine ni provere sadržaja.
- Nijedan test se ne mora menjati.
- `Dockerfile:17` je `COPY . .` — novi fajl ulazi u image bez konfiguracije.
- SW `PRECACHE` (`sw.js:6-12`) ne sadrži `/` ni `landing.html`.
- `shared/build_info.py` ne čita `landing.html`.

---

## 9. TRI ELEMENTA KOJA ČINE DA VINDEX IZGLEDA KAO VINDEX

Izvedeno iz onoga što je konzistentno prisutno u **oba** sistema (landing i aplikacija),
a čije bi uklanjanje odmah promenilo identitet.

**1. Cormorant Garamond kao brend font, sa italic `<em>` u akcentu.**
Nije samo font — to je obrazac: `Vindex <em>AI</em>` gde je `<em>` u italicu i u
`#00d4ff`. Ponavlja se u nav logu (`landing.html:755, 85`), CTA logu (`:1043, 532`),
footer brendu (`:1055, 550`), mobilnom draweru (`:773, 610`), pre-auth ekranu
aplikacije (`index.html:4168, 4178`). Serif na tamnoj podlozi je jedina stvar koja
Vindex odmah odvaja od generičkog AI startapa.

**2. `#010308` — podloga koja je skoro crna, ali nije crna.**
Ne `#000`, ne `#0a0a0a`. Vrlo tamna plavo-crna. Sedam pojava u landingu, `--void` u
aplikaciji (`vindex.css:2731`), `--vx-bg-primary` (`:8778`). Sve što se na njoj crta —
ivice na 6% belog, tekst na 92% belog — kalibrisano je za tu tačnu vrednost.

**3. Monospace za sve što je podatak, oznaka ili brojka.**
`--font-mono` (JetBrains Mono) nosi: oznake sekcija sa `letter-spacing: 0.18em`
uppercase (`:120-129`), brojeve koraka `01/02/03` (`:335`), brojeve u sferi (`:281`),
oznake kartica (`:380`), naslove kolona u footeru (`:552`), `© MMXXVI` red (`:556`).
U aplikaciji je to dovedeno do kraja — `--font-ui` je **sam** JetBrains Mono
(`vindex.css:2767`), 86 upotreba `--font-mono`. To je Bloomberg poteza: podatak se
piše mašinskim slovima, nikad proporcionalnim.

**Napomena:** teal `#00d4ff` je namerno **nije** na ovoj listi. Cyan akcenat na tamnoj
podlozi je najgeneričniji deo identiteta — koristi ga svaki drugi tech proizvod.
Ono što Vindex čini prepoznatljivim je **serif + skoro-crna + monospace podaci**;
teal je samo pojačivač.

---

## 10. OTVORENA PITANJA ZA VLASNIKA

Nastala iz koda, ne iz pretpostavki. Nijedno se ne može zatvoriti čitanjem repoa.

1. **Koji je izvor istine za tokene** — landing (`Plus Jakarta Sans`, `6/14px`) ili
   aplikacija (`JetBrains Mono`, `2/4px`)? Sajt mora izabrati jedan; danas su oba živa
   pod istim imenima promenljivih.
2. **Registracija ili waitlist?** `/` kaže jedno, `/app` drugo. Backend podržava oba
   (`api.py:2491` registracija, `routers/waitlist.py:143` waitlist).
3. **Šta sa `/pricing`?** Ruta je javna, sekcija je uklonjena. Ostaje, gasi se, ili se
   usklađuje?
4. **`vindex.rs` ili `vindex-ai.com`?** Oba su u kodu.
5. **Da li se `status.html` redizajnira?** Jedina živa dinamička stranica, i jedina sa
   zabranjenim ikonama.
6. **Da li se pravi sintetički predmet?** Bez njega nema nijednog snimka proizvoda,
   pa hero ostaje na dijagramu — trajno, ne privremeno.

---

*Kraj dokumenta. Nijedan produkcioni fajl nije menjan u ovoj fazi.*
