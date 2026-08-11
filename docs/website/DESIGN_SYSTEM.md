# VINDEX AI — DIZAJN SISTEM SAJTA (Faza B)

Izvor istine za sve vizuelne odluke novog sajta.

**Nijedan produkcioni fajl nije menjan ovim dokumentom.** Ovo je specifikacija,
ne implementacija. `landing.html`, `index.html` i `static/*` ostaju netaknuti.

Nasleđuje merenja iz `VINDEX_WEBSITE_ARCHITECTURE.md` (Faza A, stanje `89996be`)
i vizuelna ograničenja iz `VINDEX_WEBSITE_CONTENT_MAP.md` §7.

Svaka vrednost ispod nosi oznaku porekla:

| Oznaka | Značenje |
|---|---|
| **NASLEĐENO** | postoji u kodu danas, prenosi se doslovno, sa lokacijom |
| **NASLEĐENO-IZABRANO** | postoji u **dva** sistema sa različitim vrednostima; jedna je izabrana, izbor je obrazložen |
| **NOVO** | ne postoji u kodu; uvodi se jer zatečeno stanje ne pokriva potrebu ili krši obavezujuće pravilo |
| **UKINUTO** | postoji u kodu, namerno se **ne** prenosi |

---

## 0. OPSEG

Ovaj sistem važi za **javni sajt**: `/`, i stranice iz `CONTENT_MAP.md` §3
(Kako radi, Bezbednost, Beta, Kontakt, Tehnologija, Za advokate, Vizija).

**Ne važi za:**

- `/app` (`index.html` + `static/vindex.css`) — aplikacija ostaje na svom sistemu.
- 6 pravnih stranica u belom „Georgia dokument" stilu (`privacy`, `terms`,
  `ai-disclosure`, `dpa`, `security`, `bezbednosni-list`). One su namerno
  print-orijentisane i pod testom (`tests/test_api_security.py:84-99`).
  Sajt ih **linkuje**, ne redizajnira.
- `/pricing` — po odluci iz `CONTENT_MAP.md` §6.2 ta ruta se uklanja.

---

## 1. PRINCIP NASLEĐIVANJA

Zatečeno stanje ima **sedam paralelnih vizuelnih sistema** (`ARCHITECTURE.md` R14).
Sajt ne sme postati osmi. Pravilo koje ovaj dokument primenjuje:

> Nasleđuje se **vrednost**, ne **ime**. Gde je ista vrednost postojala pod više
> imena, ostaje jedno ime. Gde je isto ime nosilo dve vrednosti, ime se povlači
> iz upotrebe na sajtu i uvodi se novo, nedvosmisleno.

---

## 2. IMENOVANJE TOKENA — REŠENJE KOLIZIJE

### 2.1 Problem

| Ime | `landing.html` | `static/vindex.css` |
|---|---|---|
| `--font-ui` | `Plus Jakarta Sans` (sans) — `:29` | `JetBrains Mono` (monospace) — `:2767` |
| `--r-sm` | `6px` — `:26` | `2px` — `:2770` |
| `--r-lg` | `14px` — `:27` | `4px` — `:2772` |
| `--tx-1/2/3` | `.92 / .55 / .30` — `:22-24` | `.88 / .52 / .28` — `:2745-2747` |

Isti akcenat `#00d4ff` živi pod **sedam** imena (`ARCHITECTURE.md` §1.4).

### 2.2 Odluka: prefiks `--vw-`

Sajt koristi **isključivo** tokene sa prefiksom `--vw-` (Vindex Website).
Nijedan token bez tog prefiksa se ne koristi i ne redefiniše.

**Zašto prefiks, a ne „izaberi pobednika":**

1. Danas nema stvarne kaskadne kolizije — `landing.html` ne učitava `vindex.css`
   (`ARCHITECTURE.md` §5, „0 KB JS zavisnosti / inline `<style>`"), a `/app` je
   zaseban dokument. Kolizija je **autorska**, ne runtime.
2. Ako bi sajt „pobedio" tako što redefiniše `--r-sm` na 2px, svaki budući
   inženjer koji taj naziv vidi mora da pogodi u kom je fajlu. Prefiks uklanja
   pitanje.
3. Prefiks omogućava da se aplikacija migrira kasnije, svojim tempom, bez
   koordinacije sa sajtom. Ovo je jedini deo Faze B koji **ne stvara dug** u
   `vindex.css`.

Ime `--font-ui` se na sajtu **ne koristi uopšte** — otrovano je (v. §4.1).

---

## 3. BOJE

### 3.1 Podloge i površine

| Token | Vrednost | Poreklo | Kontrast prema `--vw-bg` | Uloga |
|---|---|---|---|---|
| `--vw-bg` | `#010308` | **NASLEĐENO** — `landing.html:14` `--void`, `vindex.css:2729` `--void`, `:8778` `--vx-bg-primary` | — | Jedina podloga celog sajta. Identitetski element #2. |
| `--vw-surface` | `#0a1220` | **NASLEĐENO** — `vindex.css:1754` `--surface`, `:8779` `--vx-bg-secondary` | 1,10 : 1 | Podignuta površina: kartice, polja forme, akordeon panel |
| `--vw-surface-2` | `#0d1117` | **NASLEĐENO** — `vindex.css:8780` `--vx-bg-elevated`, `:8743` `--vx-panel-bg` | 1,09 : 1 | Drugi sloj: aktivno stanje kartice, otvoreni akordeon |

**Napomena o 1,10 : 1.** Površina se ne razlikuje kontrastom nego **linijom**
(§6). To je namerno — Bloomberg pristup razdvaja slojeve ivicom, ne svetlinom.

`--vw-surface` i `--vw-surface-2` su vizuelno skoro identični. Koriste se
**hijerarhijski, ne dekorativno**: `--vw-surface-2` samo tamo gde su dva panela
jedan u drugom.

### 3.2 Ivice i linije

| Token | Vrednost | Poreklo | Kontrast prema `--vw-bg` | Uloga |
|---|---|---|---|---|
| `--vw-line` | `rgba(255,255,255,0.06)` | **NASLEĐENO** — `landing.html:17` `--bd-1`, `vindex.css:1770` `--bd-1` | 1,10 : 1 | Dekorativne podele: razdelnik sekcije, `gap`-linije mreže |
| `--vw-line-2` | `rgba(255,255,255,0.10)` | **NASLEĐENO** — `landing.html:18` `--bd-2`, `vindex.css:1771` `--bd-2` | 1,21 : 1 | Ivica kartice, ivica sekundarnog dugmeta |
| `--vw-line-input` | `#54606f` | **NOVO** | **3,22 : 1** | **Isključivo ivica polja forme i kontrola.** |
| `--vw-line-accent` | `rgba(0,212,255,0.20)` | **NASLEĐENO** — `landing.html:19` `--bd-teal` | — | Naglašena ivica: kartica dokaza, aktivno stanje |

**Zašto `--vw-line-input` postoji.** WCAG 2.1 SC 1.4.11 (Non-text Contrast) traži
**3:1** za granice komponenata koje korisnik mora da identifikuje. Nasleđena
ivica polja (`vindex.css:8763` `--vx-input-border: rgba(255,255,255,0.10)`) daje
**1,21 : 1** — polje forme je praktično nevidljivo. `--vw-line` i `--vw-line-2`
smeju ostati slabi jer su **dekorativni**; ivica polja ne sme.

Beta forma je jedina konverziona tačka sajta. Nevidljivo polje je nevidljiva
konverzija.

### 3.3 Tekst — i rešenje `--tx-3`

Sve boje teksta su **puni heksadecimalni zapis**, ne `rgba` sa alfom.

| Token | Vrednost | Poreklo | Na `--vw-bg` | Na `--vw-surface` | Uloga |
|---|---|---|---|---|---|
| `--vw-text` | `#e6edf3` | **NASLEĐENO** — `vindex.css`, 35 pojava; `ARCHITECTURE.md` §1.1 | **17,46 : 1** ✓ AAA | 15,86 : 1 ✓ AAA | Naslovi, telo teksta |
| `--vw-text-2` | `#8b98a8` | **NOVO** (zamena za `--tx-2`) | **7,03 : 1** ✓ AAA | 6,39 : 1 ✓ AA | Sekundarni tekst, opisi, oznake, podnožje |
| `--vw-text-disabled` | `#6f7d8f` | **NOVO** | **4,92 : 1** ✓ AA | 4,47 : 1 ✓ AA | Isključeno stanje kontrole |

### `--tx-3` je UKINUT

**Nalaz:** `--tx-3` = `rgba(255,255,255,0.30)` na `#010308` daje **2,44 : 1**
(mereno u Fazi A) — pada AA za tekst (prag 4,5). Nosio je ceo podnožje:
`.footer-brand-body` (`landing.html:551`), `.footer-col-title` (`:552`),
`.footer-bottom` (`:556`), `.cen-note` (`:522`).

**Rešenje nije „posvetliti `--tx-3`". Rešenje je ukloniti treći nivo teksta.**

Sajt ima **dva** nivoa teksta, ne tri. Sve što je bilo na `--tx-3` prelazi na
`--vw-text-2` (7,03 : 1), a hijerarhiju koju je nosila providnost preuzimaju
tri druga sredstva:

| Nekadašnja uloga `--tx-3` | Nova mehanika |
|---|---|
| „ovo je manje važno" | **manja veličina** (0,78rem umesto 0,9rem) |
| „ovo je oznaka, ne rečenica" | **`--vw-font-data`** + uppercase + `letter-spacing: 0.16em` |
| „ovo je podnožje" | **razdelna linija** `--vw-line` + veći razmak iznad |

Ovo je usklađeno sa obavezujućim pravilom „monospace za oznake": Bloomberg ne
utišava oznake providnošću, on ih menja **familijom**. Providnost je bila
zamena za tipografiju.

`--vw-text-disabled` na **4,92 : 1** je jedini izuzetak niže od AAA, i namerno:
isključeno stanje mora izgledati isključeno, a 4,92 i dalje prolazi AA.

**Zabranjeno:** bilo koji tekst ispod **4,5 : 1**. Bez izuzetka, uključujući
`© MMXXVI` red u podnožju.

### 3.4 Akcenat

| Token | Vrednost | Poreklo | Kontrast | Uloga |
|---|---|---|---|---|
| `--vw-accent` | `#00d4ff` | **NASLEĐENO** — `landing.html:15` `--teal`; u aplikaciji pod 7 imena | **11,65 : 1** na `--vw-bg` ✓ AAA · 10,59 : 1 na `--vw-surface` ✓ AAA | `<em>` u logotipu, oznake sekcija, fokus prsten, primarno dugme |
| `--vw-accent-ink` | `#010308` | **NASLEĐENO** — `landing.html:130-145` `.btn-filled { color:#010308 }` | 11,65 : 1 na akcentu ✓ AAA | Tekst **na** akcentu (popunjeno dugme) |
| `--vw-accent-soft` | `rgba(0,212,255,0.08)` | **NASLEĐENO** — `landing.html:16` `--teal-lo` | — | Hover podloga sekundarnog dugmeta |

**Zatvoren rizik.** `VINDEX_AI_WEBSITE_IMPLEMENTATION_RISKS.md:20` je tvrdio da
je `#00d4ff` na `#010308` „granični slučaj za WCAG AA". Izmereno u Fazi A i
nezavisno potvrđeno ovde: **11,65 : 1**, prolazi i AAA. Rizik je neosnovan.

**Politika akcenta.** `#00d4ff` **nije** na listi tri identitetska elementa
(`ARCHITECTURE.md` §9) — najgeneričniji je deo identiteta. Zato se koristi
**štedljivo**: cilj je da na bilo kom ekranu bude vidljivo najviše
**tri** akcentovana elementa. Akcenat naglašava, ne dekoriše.

**UKINUTO:** `--teal-md` (`rgba(0,212,255,0.16)`), `--teal-hi`
(`rgba(0,212,255,0.35)`), `--vx-accent-glow`, `--vx-accent-glow-soft`,
`--vp-accent`. Sve su hover-nijanse ili glow tokeni; §7 zabranjuje glow, a §8
definiše hover bez njih.

### 3.5 Statusi

Samo dva, i to **funkcionalna** — nikad dekorativna.

| Token | Vrednost | Poreklo | Kontrast na `--vw-bg` | Uloga |
|---|---|---|---|---|
| `--vw-ok` | `#4ade80` | **NASLEĐENO** — `landing.html:475`, `vindex.css:2205` `--color-success`, `:8749` `--vx-success` | **11,84 : 1** ✓ AAA | Znak `✓` — „ovo radi danas" |
| `--vw-warn` | `#f0b429` | **NASLEĐENO-IZABRANO** — `vindex.css:8751` `--vx-warning` | **11,07 : 1** ✓ AAA | Znak `⚠` — „ovo ne radi / u izradi" |

**Zašto `#f0b429`, a ne `#f56565` / `#f87171`.** Blueprint navodi `#f56565` kao
„status greške", ali sajt **nema stanje greške** — nema aplikacije koja pada.
Ima samo poštenu podelu na „radi danas" i „ne radi / u izradi"
(`CONTENT_MAP.md` §5). Crvena bi tu bila laž: to što izvori nisu klikabilni
nije kvar, nego trenutna granica. Narandžasto-žuta `#f0b429` (11,07 : 1) tačno
prenosi „ograničenje", a usput izbegava jedinu nasleđenu boju koja pada AAA
(`#f56565` = 6,81 : 1).

`--vw-warn` se koristi i za obavezno pravno upozorenje („nije pravni savet").

**UKINUTO na sajtu:** `--gold #c9a84c`, `--emerald #10b981`, `--danger #ef4444`,
`#f56565`, `#f87171`, `#fbbf24`, `#fb923c`, ljubičasti sistem `#8b5cf6` /
`#a78bfa` / `#c4b5fd` (`landing.html:489-520`, mrtav CSS iz uklonjenog
cenovnika — v. R9), `#2563eb`, `#1d4ed8`, `#89c8ff`, `#0099bb`.
**Četiri različita „plava" akcenta** iz `ARCHITECTURE.md` §3.1 svode se na jedan.

### 3.6 Metoda merenja — i jedno neslaganje sa Fazom A

Sve vrednosti u ovom dokumentu su računate po WCAG 2.1 formuli za relativnu
luminanciju (sRGB linearizacija, `(L1+0.05)/(L2+0.05)`).

**Puni heksadecimalni zapisi se poklapaju sa Fazom A do druge decimale:**
`#00d4ff` 11,65 · `#e6edf3` 17,46 · `#4ade80` 11,84 · `#f56565` 6,81.

**Kod `rgba` vrednosti postoji odstupanje u drugoj decimali:** Faza A daje
`rgba(255,255,255,0.55)` = 6,14 i `0.30` = 2,44; ovde ista formula daje 6,26 i
2,50. Razlog je redosled kompozitovanja (sRGB prostor vs linearni prostor pre
merenja).

**Ovo je razlog više za §3.3.** Kontrast `rgba` teksta **zavisi od toga šta je
iza njega** i od metode merenja — nije determinističan. Puni hex jeste. Zato sve
boje teksta na sajtu imaju pun hex, i njihove izmerene vrednosti se ne mogu
pomeriti podlogom.

Zaključak ne zavisi od te decimale: `--tx-3` pada AA i po jednoj i po drugoj
metodi (2,44 ili 2,50, prag je 4,5).

---

## 4. TIPOGRAFIJA

### 4.1 ODLUKA O `--font-ui`

**Kolizija:** landing = `Plus Jakarta Sans` (sans), aplikacija = `JetBrains Mono`
(monospace). Dijametralno.

**Odluka: ime `--font-ui` se povlači. Sajt ima tri imenovana toka teksta, i
proza je sans.**

| Nova uloga | Vrednost | Poreklo |
|---|---|---|
| `--vw-font-brand` | `'Cormorant Garamond', Georgia, serif` | **NASLEĐENO** — `landing.html:28`, `vindex.css:2766` |
| `--vw-font-text` | `'Plus Jakarta Sans', system-ui, -apple-system, sans-serif` | **NASLEĐENO-IZABRANO** — `landing.html:29`; u aplikaciji preživljava u `vindex.css:2786` (`#tab-h`) |
| `--vw-font-data` | `'JetBrains Mono', 'SF Mono', 'Fira Code', monospace` | **NASLEĐENO** — `landing.html:30`, `vindex.css:2767-2768` |

**Obrazloženje — četiri razloga, poređana po težini:**

**1. Obavezujuće pravilo kaže „monospace za brojeve/podatke/oznake", ne „za
prozu".** To je definicija uloge, ne globalna zamena familije. `--vw-font-data`
je ispunjava doslovno i strože nego danas.

**2. Sajt i aplikacija imaju suprotan tekstualni profil.** Aplikacija prikazuje
kratke, tabelarne, brojčane niske u gustim panelima — monospace tu **pomaže**
poravnanju. Sajt mora da nosi duge proze koje su same po sebi diferencijator:
sekcija „šta ne radi" (8 tvrdnji), granice iz `CONTENT_MAP.md` §5, tekst o
poverenju. Monospace na 16px/1,6 kroz pasus od 70 znakova je merljivo sporiji
za čitanje i ruši ciljanu dužinu reda.

**3. Presedan već postoji u kodu, i to na najosetljivijem ekranu.** Aplikacija
je sama izuzela svoj „ljudski" ekran: `vindex.css:2786`
`#tab-h { --font-ui: 'Plus Jakarta Sans' … }`, uz komentar „zaključan ekran".
Tim izuzetkom je aplikacija već priznala da monospace nije univerzalan. Sajt je
u celini taj slučaj.

**4. Publika je advokat, ne trader.** Bloomberg estetika se prenosi **strukturom
i podacima**, ne time što se ugovorna proza slaže mašinskim slovima.

**Šta ovo NE znači.** Identitetski element #3 („monospace za svaki podatak,
oznaku i brojku") ostaje **nepromenjen i pojačan**. Vidi §4.5 — pravilo je
obavezujuće i proverljivo.

**Ovo je odstupanje od aplikacije i traži potvrdu vlasnika — v. §12, B1.**

### 4.2 Učitavanje fontova

Jedan `<link>` sa `preconnect`, kao danas (`landing.html:8-10`).
CSP dozvoljava: `style-src fonts.googleapis.com`, `font-src fonts.gstatic.com`
(`api.py:1149-1161`).

| Familija | Težine za sajt | Promena u odnosu na danas |
|---|---|---|
| Cormorant Garamond | 400, 600, 700 + italic 400, 600 | isto kao `landing.html` |
| Plus Jakarta Sans | 400, 500, 600 | **manje** — 700 se izbacuje (naslovi su serif) |
| JetBrains Mono | 400, 500 | **manje** — 700 se izbacuje (oznake nose tracking, ne težinu) |

**UKINUTO:** `Source Serif 4` — učitava se u `index.html:15` a **nigde se ne
referencira** (`ARCHITECTURE.md` §1.4). Ne prenosi se.

**Obavezno:** `font-display: swap` na svakom `<link>` upitu (`&display=swap`).
Bez toga tekst je nevidljiv dok se font ne preuzme, a Service Worker
(`sw.js:77-97`) fontove kešira **cache-first bez isteka** — pa je prvi utisak
trajno oštećen kod posetioca koji su već bili na sajtu.

**Upozorenje ⚠ za Fazu G:** `sw.js:77-97` znači da promena skupa fontova
**neće** biti vidljiva postojećim posetiocima dok `CACHE_NAME` (`sw.js:4`) ne
poraste. Isto pravilo pokriva i zamenu landinga (`ARCHITECTURE.md` R1).

### 4.3 Skala — desktop (≥ 1024px)

| Nivo | Familija | Veličina | Težina | Prored | Tracking | Poreklo |
|---|---|---|---|---|---|---|
| **H1** | brand | `clamp(3rem, 4.5vw, 5rem)` | 700 | 1,05 | `-0.02em` | **NASLEĐENO** — `landing.html:187-192` |
| **H2** | brand | `clamp(2.2rem, 3.5vw, 3.4rem)` | 700 | 1,10 | `-0.02em` | **NASLEĐENO** — `landing.html:308, 358, 423, 453` |
| **H3** | brand | `1.4rem` | 600 | 1,25 | `-0.01em` | **NOVO** — landing nema H3 |
| **Lead** | text | `1.05rem` | 400 | 1,72 | 0 | **NASLEĐENO** — `landing.html:196-199` (`.hero-p`) |
| **Telo** | text | `1rem` (16px) | 400 | 1,60 | 0 | **NASLEĐENO** — `landing.html:40-41` |
| **Sitno** | text | `0.875rem` | 400 | 1,55 | 0 | **NOVO** |
| **Oznaka** | data | `0.68rem` | 500 | 1,20 | `0.16em`, uppercase | **NASLEĐENO-IZMENJENO** — `landing.html:120-129` je `0.65rem`/700/`0.18em` |
| **Podatak** | data | `0.875rem` | 400 | 1,45 | `0` | **NOVO** |
| **Broj (istaknut)** | data | `1.6rem` | 400 | 1,10 | `-0.01em` | **NOVO** |

**Zašto je oznaka izmenjena sa 0,65rem/700/0,18em na 0,68rem/500/0,16em.**
0,65rem = 10,4px. Uppercase monospace na 10,4px sa težinom 700 na tamnoj podlozi
proizvodi optičko zamućenje (halation) — teško je čitljiv, a nosi navigacionu
funkciju („koja je ovo sekcija"). 0,68rem = 10,9px sa težinom 500 je čitljiviji
uz identičan vizuelni utisak. Tracking sa 0,18em na 0,16em jer JetBrains Mono
već ima šire razmake od proporcionalnog fonta.

Ovo je **korekcija čitljivosti**, ne promena identiteta — familija, uppercase,
tracking i boja ostaju.

### 4.4 Skala — mobilni (< 640px)

`clamp()` u H1/H2 već rešava skaliranje. Dodatna pravila:

| Nivo | Mobilna vrednost | Napomena |
|---|---|---|
| H1 | donja granica `clamp` = `3rem` (48px) | **spustiti na `2.4rem`** — 48px na 360px širine daje 2-3 reči po redu |
| H2 | donja granica `clamp` = `2.2rem` | zadržati |
| H3 | `1.25rem` | |
| Lead | `1rem` / prored 1,65 | |
| Telo | `1rem` (16px) — **nikad ispod** | ispod 16px iOS Safari zumira polja forme |
| Oznaka | `0.68rem` — **ne smanjivati** | već je na granici |

**Obavezno:** `-webkit-text-size-adjust: 100%` na `html`.

### 4.5 Pravila upotrebe familija — obavezujuća i proverljiva

**`--vw-font-brand` (Cormorant Garamond) — SAMO:**
logotip `Vindex <em>AI</em>` · H1 · H2 · H3 · naslov kartice.
**Nikad** za telo teksta, oznake, brojeve, dugmad, polja forme.

**`--vw-font-text` (Plus Jakarta Sans) — SAMO:**
pasusi · stavke liste · tekst dugmeta · tekst polja forme · pitanja i odgovori u
FAQ-u · rečenice u podnožju.

**`--vw-font-data` (JetBrains Mono) — OBAVEZNO za sve od navedenog:**

| Šta | Primer |
|---|---|
| svaki broj koji nešto meri | `4`, `01/02/03`, `12.604` |
| oznaka sekcije | `KAKO RADI` |
| oznaka statusa | `RADI DANAS`, `U IZRADI` |
| oznaka kartice | `DOKAZ 02` |
| naslov kolone u podnožju | `PROIZVOD` |
| brojevi koraka | `01` |
| naziv fajla, rute, propisa u tehničkom kontekstu | `POST /waitlist/prijava` |
| datum, verzija, `© MMXXVI` | |
| tekst unutar bloka podatka | v. `COMPONENT_MAP.md` §15 |

**Provera za Fazu G:** nijedan `<span>`, `<td>` ili `<dd>` čiji je sadržaj
isključivo cifra, datum ili verzija ne sme naslediti `--vw-font-text`.

### 4.6 Dužina reda

| Kontekst | Maksimum | Poreklo |
|---|---|---|
| Pasus proze | **68ch** (~640px na 16px) | **NOVO** — landing nema pravilo |
| Lead ispod H1 | `520px` | **NASLEĐENO** — `landing.html:198` |
| H1 / H2 | **18 reči** ili `14ch`-po-redu meko | **NOVO** |
| Tekst u kartici | `44ch` | **NOVO** |
| Blok podatka (mono) | `80ch`, dalje horizontalni skrol | **NOVO** |

Prozni tekst se **ne** rasteže na punih 1200px kontejnera. Kontejner je za
raspored; `--vw-measure: 68ch` je za čitanje.

---

## 5. RAZMAK

### 5.1 Skala — osnova 8px

**NASLEĐENO** iz `vindex.css:1751-1754` (8pt mreža aplikacije), prošireno naviše
za potrebe sekcija sajta.

| Token | Vrednost | Poreklo | Tipična upotreba |
|---|---|---|---|
| `--vw-sp-1` | `4px` | NASLEĐENO (`--sp-h`) | razmak ikone i teksta |
| `--vw-sp-2` | `8px` | NASLEĐENO (`--sp-1`) | unutar oznake |
| `--vw-sp-3` | `16px` | NASLEĐENO (`--sp-2`) | razmak pasusa |
| `--vw-sp-4` | `24px` | NASLEĐENO (`--sp-3`) | padding kartice (mobilni) |
| `--vw-sp-5` | `32px` | NASLEĐENO (`--sp-4`) | padding kartice (desktop), `gap` mreže |
| `--vw-sp-6` | `48px` | NASLEĐENO (`--sp-6`) | naslov → sadržaj |
| `--vw-sp-7` | `64px` | NASLEĐENO (`--sp-8`) | padding sekcije (mobilni) |
| `--vw-sp-8` | `96px` | **NOVO** | padding sekcije (desktop) |
| `--vw-sp-9` | `128px` | **NOVO** | padding CTA sekcije (desktop) |

**UKINUTO:** `--sp-5: 40px` — 40px između 32 i 48 je razlika koju niko ne vidi,
a nudi pogrešan izbor. Devet koraka je maksimum.
**UKINUTO:** `--vx-space-1..7` (`vindex.css:8788`, `3/6/8/10/14/18/24px`) — gusta
skala za panele aplikacije, nema svrhu na sajtu.

### 5.2 Vertikalni ritam sekcija

| Kontekst | Desktop (≥1024) | Tablet (640-1023) | Mobilni (<640) | Poreklo |
|---|---|---|---|---|
| Standardna sekcija | `96px 0` | `64px 0` | `48px 0` | **NASLEĐENO-ZAOKRUŽENO** — landing ima `100 / 80 / 64` (`:302, :671, :698`) |
| CTA sekcija | `128px 0` | `96px 0` | `64px 0` | **NASLEĐENO-ZAOKRUŽENO** — landing `120 / 72` (`:526, :699`) |
| Prva sekcija posle heroja | `96px 0` | `64px 0` | `48px 0` | isto |

**Zašto 96, a ne nasleđenih 100.** 100 nije umnožak 8 — jedina vrednost u
landingu koja ispada iz mreže. Razlika 100→96 je 4px i vizuelno neprimetna;
korist je da svaki razmak na sajtu ima ime u skali.

### 5.3 Unutrašnji razmak

| Element | Desktop | Mobilni | Poreklo |
|---|---|---|---|
| Kartica | `32px` | `24px` | **NASLEĐENO-ZAOKRUŽENO** — `36px 32px` → `24px 20px` (`:328, :710`) |
| Kontejner (bočno) | `32px` | `20px` | **NASLEĐENO** — `landing.html:118, 677` |
| `gap` mreže | `32px` | `24px` | **NASLEĐENO** — `landing.html:324` |
| `gap` linijske mreže | `1px` | `1px` | **NASLEĐENO-IZMENJENO** — landing koristi `2px` (`:367`); 1px daje pravu hairline |
| Visina zaglavlja | `64px` | `56px` | **NASLEĐENO** — `landing.html:73` |

### 5.4 Širine

| Token | Vrednost | Poreklo |
|---|---|---|
| `--vw-shell` | `1200px` | **NASLEĐENO-IZABRANO** — landing nav `1280px` (`:72`), `pricing.html` `1160px`; 1200 je umnožak 8 i sredina |
| `--vw-measure` | `68ch` | **NOVO** — v. §4.6 |
| `--vw-form` | `560px` | **NOVO** — Beta forma |

---

## 6. IVICE I RADIUS

### 6.1 Radius — jedna vrednost

| Token | Vrednost | Poreklo |
|---|---|---|
| `--vw-radius` | **`2px`** | **NASLEĐENO-IZABRANO** — `vindex.css:2770` `--r-sm: 2px`; landing ima `6px` |

**Jedan token. Nema `sm` / `md` / `lg`.**

**Obrazloženje.** Kolizija je `6px` (landing) vs `2px` (aplikacija). Bira se 2px
iz tri razloga:

1. **Obavezujuća odluka vlasnika je „oštri uglovi".** Landing je jedini deo
   proizvoda koji je krši; aplikacija je poštuje u 84,8% slučajeva
   (`ARCHITECTURE.md` §1.7). Bira se strana koja poštuje pravilo.
2. **Sajt je uvod u aplikaciju.** Ako `/` ima meke uglove a `/app` oštre,
   prelazak izgleda kao odlazak na drugi proizvod.
3. **Dve vrednosti radiusa su jedna previše.** Aplikacija ima `2/3/4px` — tri
   nijanse zaobljenja koje niko ne razlikuje. Sajt ima jednu, i time je
   proverljiva.

**Eksplicitni `0` — bez radiusa uopšte:**
razdelnici sekcija · ćelije linijske mreže (`.fn-grid` obrazac) · redovi tabele ·
podnožje · zaglavlje.

**ZABRANJENO:**
- `border-radius: 999px` / pilule — `landing.html` ih ima; oblik pilule je
  suprotan „oštrim uglovima". Oznaka statusa je pravougaonik (v.
  `COMPONENT_MAP.md` §14).
- `border-radius: 50%` — nema krugova. **UKINUTO:** `.hero-sphere`
  (`landing.html:225-246`), 340px krug sa radijalnim gradijentom.
- `--vx-card-radius: 10px` (`vindex.css:8762`) i `--vx-modal-radius: 12px`
  (`:8746`) — mrtvi tokeni iz pre-Bloomberg faze, 0 upotreba.
- `--vx-input-radius: 7px` (`vindex.css:8765`).
- `landing.html:186` `.zasto-ico` `10px`.

### 6.2 Ivice

**Uvek `1px solid`.** Nikad 2px, nikad `dashed`, nikad `double`.

| Kontekst | Vrednost |
|---|---|
| Kartica, panel | `1px solid var(--vw-line-2)` |
| Razdelnik sekcije | `1px solid var(--vw-line)` |
| Polje forme, kontrola | `1px solid var(--vw-line-input)` |
| Naglašeni element | `1px solid var(--vw-line-accent)` |
| Aktivno / izabrano | `1px solid var(--vw-accent)` |

**Obrazac linijske mreže — NASLEĐENO i zadržano.** `landing.html:364-372`
(`.fn-grid`): `display:grid; gap:1px; background:var(--vw-line);
overflow:hidden` — ćelije su podloge, a `gap` postaje linija. Rezultat su
neprekinute linije bez dupliranih ivica na spojevima. Ovo je najbolji zatečeni
obrazac na celom landingu i prenosi se doslovno (uz `gap` 2px → 1px).

---

## 7. SENKE

## POLITIKA: NEMA IH.

`box-shadow` je zabranjen na celom sajtu. Nula deklaracija.

Ovo je direktna posledica obavezujućeg pravila „bez glow-a i gradijenata", koje
se danas krši na obe strane (`ARCHITECTURE.md` §1.1):

| Prekršaj | Lokacija |
|---|---|
| `box-shadow: 0 0 80px…160px` teal glow | `landing.html`, `.cen-card.pro` (`:497`) |
| `box-shadow: 0 4px 24px rgba(0,212,255,0.35)` | `landing.html:650-661` (mobilni sticky CTA) |
| `sphere-breathe` — animirana `box-shadow` | `landing.html:241-246` |
| 10 cyan glow senki + 2 glow tokena | `static/vindex.css` |
| 27 gradijenata | `static/vindex.css` |
| 4 gradijenta | `landing.html` |

**Čime se zamenjuje razdvajanje slojeva** — poređano po prioritetu:

1. **Linija.** `1px solid var(--vw-line-2)`. Ovo je primarno sredstvo.
2. **Razmak.** `--vw-sp-6` i naviše. Dva bloka razdvojena sa 48px ne traže ivicu.
3. **Promena podloge.** `--vw-bg` → `--vw-surface` (1,10 : 1). Suptilno, i
   dovoljno kad je uz liniju.
4. **Promena familije.** Prelazak na `--vw-font-data` menja teksturu bloka jače
   od bilo koje senke.

**Dozvoljena su tačno dva izuzetka, i nijedan nije `box-shadow`:**

- **Fokus prsten** — `outline`, ne `box-shadow` (v. §8.2).
- **Maska preliva mobilne sticky trake** — `linear-gradient` u `mask-image`
  svojstvu, radi sprečavanja tvrdog reza teksta ispod trake. To je maska, ne
  pozadinski gradijent. Ako se sticky traka ne implementira, i taj izuzetak
  otpada.

**Gradijenti kao `background` su zabranjeni bez izuzetka.**

---

## 8. STANJA

Svaka interaktivna komponenta mora imati definisanih **pet** stanja. Zatečeno
stanje ima samo `:hover` (`ARCHITECTURE.md` §2.1: „`:focus` — 0 deklaracija;
`:disabled` — ne postoji; `:active` — ne postoji"; `focus-visible` u
`vindex.css` — **0 pojava**, provereno).

### 8.1 Hover

| Komponenta | Promena | Poreklo |
|---|---|---|
| Primarno dugme | `opacity: 0.88` | **NASLEĐENO** — `landing.html:143` |
| Sekundarno dugme | `border-color: var(--vw-line-accent)` + `background: var(--vw-accent-soft)` | **NASLEĐENO** — `landing.html:157-159` |
| Kartica | `border-color: var(--vw-line-accent)` | **NASLEĐENO-IZMENJENO** — landing menja i pozadinu |
| Link u tekstu | `border-bottom-color: var(--vw-accent)` | **NOVO** |
| Red podnožja | `color: var(--vw-text)` | **NOVO** |

**UKINUTO:** `transform: translateY(-1px)` na dugmadima (`landing.html:144`) i
`translateY(-3px)` na karticama (`:334`). Podizanje elementa pod kursorom je
skeuomorfizam koji podrazumeva senku ispod — a senki nema. Bez senke, pomeranje
izgleda kao greška u rasporedu.

**Obavezno:** svaki hover mora biti u `@media (hover: hover)`. Na dodirnim
ekranima `:hover` ostaje „zaglavljen" posle dodira.

### 8.2 Focus — OBAVEZNO, i potpuno NOVO

```
:focus-visible {
  outline: 2px solid var(--vw-accent);
  outline-offset: 2px;
  border-radius: var(--vw-radius);
}
```

**Ovo je najveći pristupačnosni dug koji sajt zatvara.**

`landing.html:46` sadrži `button { outline: none; }` **bez ikakve zamene**.
Rezultat: sajt je danas nenavigabilan tastaturom — korisnik ne vidi gde je.
Pretraga u `static/vindex.css`: `focus-visible` = **0 pojava**. Problem nije
lokalan za landing, već za ceo frontend.

Zahtevi:

- `outline: none` bez zamene je **zabranjen**. Ako se podrazumevani prsten
  uklanja, u istom bloku mora stajati `:focus-visible` pravilo.
- Kontrast prstena: `#00d4ff` na `#010308` = **11,65 : 1**, daleko iznad praga
  od 3:1 (SC 1.4.11) i iznad novog praga za fokus (SC 2.4.11, WCAG 2.2).
- `outline-offset: 2px` — prsten ne sme dodirivati ivicu elementa; na tamnoj
  podlozi se stapa sa `--vw-line-2`.
- `:focus-visible`, ne `:focus` — miš ne aktivira prsten, tastatura da.
- **`:focus` fallback** za pretraživače bez podrške: identično pravilo pod
  `:focus`, pa `:focus:not(:focus-visible) { outline: none }`.
- **Preskoči na sadržaj.** Prvi element u `<body>`: link „Preskoči na sadržaj"
  ka `#sadrzaj`, vidljiv **samo** na fokus. Sajt ima lepljivo zaglavlje —
  bez ovog linka korisnik tastature prolazi kroz navigaciju na svakoj stranici.
- **`scroll-margin-top: 80px`** na svakom cilju sidra. Lepljivo zaglavlje
  (64px) inače pokriva fokusirani element posle skoka na `#sidro`.

### 8.3 Active

`opacity: 0.72`, bez `transform`. Trajanje `--vw-t-fast`.

### 8.4 Disabled

```
opacity: 1;                      /* NE koristiti opacity za disabled */
color: var(--vw-text-disabled);  /* 4,92 : 1 — i dalje čitljivo */
border-color: var(--vw-line);
background: transparent;
cursor: not-allowed;
```
+ atribut `aria-disabled="true"` uz `disabled`.

**Zašto ne `opacity: 0.5`.** To je najčešći način da se disabled tekst spusti
ispod praga kontrasta. Isključena kontrola mora ostati čitljiva — korisnik mora
znati **šta** je isključeno. Tačno ta greška je i proizvela `--tx-3` problem.

### 8.5 Loading

Jedino stanje sa animacijom, i jedino mesto gde je „skeleton" dozvoljen.

- **Dugme u toku slanja:** tekst se menja u `Šalje se…`, dugme dobija
  `aria-busy="true"` i `disabled`. **Bez vrteški.** Kružni spinner je krug
  (§6.1) i beskonačna rotacija (§9).
- **Nema skeleton ekrana na sajtu.** Sajt je statički HTML — nema šta da čeka.
  Jedini asinhroni deo je slanje Beta forme.
- **Rezultat slanja** se objavljuje kroz `aria-live="polite"` region (v.
  `COMPONENT_MAP.md` §10).

---

## 9. ANIMACIJE

### 9.1 Šta sme

| Svojstvo | Dozvoljeno |
|---|---|
| `opacity` | ✓ |
| `transform` (`translate`, `scale`) | ✓ |
| `outline-color`, `border-color`, `color`, `background-color` | ✓ — samo pri prelazu stanja, `--vw-t-fast` |
| `max-height` | ✓ — **jedini izuzetak**, samo za FAQ akordeon |
| `width`, `height`, `top`, `left`, `margin`, `padding` | ⚠ zabranjeno — izaziva reflow |
| `box-shadow`, `filter`, `backdrop-filter` | ⚠ zabranjeno — §7 |

### 9.2 Trajanja

| Token | Vrednost | Poreklo | Upotreba |
|---|---|---|---|
| `--vw-t-fast` | `150ms` | **NASLEĐENO** — `vindex.css:8796` `--vx-transition-fast`; `landing.html` `0.15s` (6 mesta) | hover, focus, active |
| `--vw-t-base` | `200ms` | **NASLEĐENO** — `vindex.css:8797`; `landing.html` `0.2s` | kartice, otvaranje akordeona |
| `--vw-ease` | `cubic-bezier(0.4, 0, 0.2, 1)` | **NASLEĐENO** — `vindex.css:8795` `--vx-ease` | sve |

**UKINUTO:** `--t-slow: 0.35s`. Ništa na sajtu ne sme trajati duže od 200ms.
Takođe rešava zatečeni defekt: `--t-fast/base/slow` je definisan **dva puta** u
`vindex.css` (`:2213` i `:2774`), sa različitim vrednostima; prvi je mrtav kod.

### 9.3 Šta je UKINUTO — i zašto

| Ukinuto | Lokacija | Razlog |
|---|---|---|
| `sphere-breathe`, `4s ease-in-out infinite` | `landing.html:241-246` | animira `box-shadow` (§7), beskonačna je (§9.4), i to je glow |
| Pozadinski particle canvas, `requestAnimationFrame` | `landing.html:1104-1145` | beskonačna petlja, crta preko cele `innerWidth × innerHeight` na svakom frejmu |
| Hero constellation canvas, `requestAnimationFrame` | `landing.html:1148-1207` | isto + `O(n²)` petlja preko 60 čestica (`:1133`) |
| `html { scroll-behavior: smooth }` | `landing.html:35` | ostaje, ali **mora** biti gejtovano `prefers-reduced-motion` |

**Dve `rAF` petlje nemaju nijedan gejt** — ni `IntersectionObserver`, ni
`visibilitychange`, ni `prefers-reduced-motion`. Rade i kad je kartica u
pozadini. Na mobilnom je to stalan trošak baterije na marketinškoj stranici.

**Pravilo:** sajt ne sadrži nijednu beskonačnu animaciju i nijedan `<canvas>`.
Ako neka buduća animacija koristi `rAF`, mora imati sva tri gejta.

### 9.4 `prefers-reduced-motion` — OBAVEZNO

Zatečeno: `landing.html` **0 blokova**, `index.html` **0 blokova**
(`ARCHITECTURE.md` §1.8). Blueprint to izričito traži.

```
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Blok ide **na kraj** stilova, da nadjača sve. `scroll-behavior: auto` u istom
bloku poništava `landing.html:35`.

### 9.5 Ulazne animacije

**Zabranjene.** Nema „fade-in on scroll", nema staggered reveal-a.

Sajt tvrdi da je pouzdan i predvidiv. Sadržaj koji se pojavljuje pri skrolu je
suprotna poruka, ne radi bez JS-a, i lomi `Ctrl+F`.

---

## 10. TAČKE PRELOMA

### 10.1 Odluka

| Ime | Vrednost | Poreklo |
|---|---|---|
| `sm` | `640px` | **NASLEĐENO-IZABRANO** — primarni breakpoint aplikacije (39 pojava u `vindex.css`); traži ga i blueprint |
| `lg` | `1024px` | **NASLEĐENO** — `landing.html:664` |

**Dve tačke. Ne tri.**

**Zašto 640, a ne nasleđenih 768.** Landing koristi `768`, aplikacija `640`
(39 puta). Blueprint traži `640/1024`. Dve od tri instance pokazuju na 640, a
768 je jedini razlog zbog kojeg mobilni izgled landinga počinje ranije nego u
aplikaciji. Odabir 640 usklađuje sajt sa `/app` i sa blueprintom.

**Zašto 480 otpada.** `landing.html:728` uvodi treću tačku koja menja samo
padding kontejnera 20px→18px. Razlika od 2px ne opravdava treći raspored.

**Zašto se 14 breakpoint-a aplikacije ne nasleđuje.** `vindex.css` ima 14
različitih `max-width` vrednosti u 82 media upita (`ARCHITECTURE.md` §1.9). To
je dug, ne sistem.

### 10.2 Pravila

| Opseg | Raspored |
|---|---|
| `< 640px` | jedna kolona, sve pune širine; navigacija = fioka; padding sekcije 48px |
| `640-1023px` | dve kolone za mreže kartica; navigacija = fioka; padding 64px |
| `≥ 1024px` | pun raspored (3-4 kolone); navigacija = horizontalna; padding 96px |

**Autorski smer: `min-width` (mobile-first).**
Zatečena oba sistema su desktop-first — `min-width` se ne pojavljuje nijednom
(`ARCHITECTURE.md` §1.9). Ovo je odstupanje, v. §12 B3.

**Zabranjeno:** horizontalni skrol na `<body>` ni na jednoj širini od 320px
naviše. Široki sadržaj (tabele, blokovi podataka, SVG dijagrami) skroluje
**unutar sopstvenog** `overflow-x: auto` kontejnera.

**Cilj dodira:** minimum `44×44px` za svaku kontrolu ispod 1024px (SC 2.5.8).
Danas: `.lp-nav-cta` ima `padding: 9px 22px` na `0.85rem` — visina ~31px, ispod
praga.

---

## 11. KOMPLETAN TOKEN BLOK

Za direktno ubacivanje u inline `<style>`. **Ovo nije primenjeno ni u jednom
fajlu** — specifikacija za Fazu D.

```css
:root {
  /* ── PODLOGE ─────────────────────────────────────────── */
  --vw-bg:              #010308;   /* NASLEĐENO  · identitet #2 */
  --vw-surface:         #0a1220;   /* NASLEĐENO  · 1,10:1 */
  --vw-surface-2:       #0d1117;   /* NASLEĐENO  · 1,09:1 */

  /* ── LINIJE ──────────────────────────────────────────── */
  --vw-line:            rgba(255,255,255,0.06);  /* NASLEĐENO */
  --vw-line-2:          rgba(255,255,255,0.10);  /* NASLEĐENO */
  --vw-line-input:      #54606f;                 /* NOVO · 3,22:1 · SC 1.4.11 */
  --vw-line-accent:     rgba(0,212,255,0.20);    /* NASLEĐENO */

  /* ── TEKST ── pun hex, ne rgba (v. §3.6) ─────────────── */
  --vw-text:            #e6edf3;   /* NASLEĐENO · 17,46:1 AAA */
  --vw-text-2:          #8b98a8;   /* NOVO      ·  7,03:1 AAA · zamena za --tx-2/--tx-3 */
  --vw-text-disabled:   #6f7d8f;   /* NOVO      ·  4,92:1 AA  */

  /* ── AKCENAT ─────────────────────────────────────────── */
  --vw-accent:          #00d4ff;   /* NASLEĐENO · 11,65:1 AAA */
  --vw-accent-ink:      #010308;   /* NASLEĐENO · tekst NA akcentu */
  --vw-accent-soft:     rgba(0,212,255,0.08);    /* NASLEĐENO */

  /* ── STATUS ── samo funkcionalno ─────────────────────── */
  --vw-ok:              #4ade80;   /* NASLEĐENO · 11,84:1 AAA · znak ✓ */
  --vw-warn:            #f0b429;   /* NASLEĐENO · 11,07:1 AAA · znak ⚠ */

  /* ── TIPOGRAFIJA ── `--font-ui` je namerno odsutan ───── */
  --vw-font-brand: 'Cormorant Garamond', Georgia, serif;
  --vw-font-text:  'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  --vw-font-data:  'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;

  /* ── RAZMAK ── osnova 8 ──────────────────────────────── */
  --vw-sp-1: 4px;   --vw-sp-2: 8px;   --vw-sp-3: 16px;
  --vw-sp-4: 24px;  --vw-sp-5: 32px;  --vw-sp-6: 48px;
  --vw-sp-7: 64px;  --vw-sp-8: 96px;  --vw-sp-9: 128px;

  /* ── ŠIRINE ──────────────────────────────────────────── */
  --vw-shell:    1200px;
  --vw-measure:  68ch;
  --vw-form:     560px;

  /* ── OBLIK ── jedna vrednost ─────────────────────────── */
  --vw-radius:   2px;

  /* ── KRETANJE ────────────────────────────────────────── */
  --vw-ease:     cubic-bezier(0.4, 0, 0.2, 1);
  --vw-t-fast:   150ms;
  --vw-t-base:   200ms;

  /* ── SENKE ── namerno ne postoje. Vidi §7. ───────────── */
}
```

**Šta u ovom bloku NE postoji, i to je namerno:**
`--font-ui` · `--r-sm` / `--r-md` / `--r-lg` · `--tx-1` / `--tx-2` / `--tx-3` /
`--tx-4` · bilo kakav `--shadow-*` ili `--glow-*` · `--t-slow` · sedmo ime za
`#00d4ff`.

---

## 12. PREDLOZI ODSTUPANJA

Odvojeno, po zahtevu. **Ništa iz ove sekcije nije utopljeno u sistem gore bez
oznake.**

### DEO A — odstupanja koja SLEDE iz obavezujućih pravila vlasnika

Ne traže odobrenje. Navedena su radi potpune vidljivosti šta se u odnosu na
`landing.html` menja.

| # | Odstupanje | Zatečeno | Obavezujuće pravilo |
|---|---|---|---|
| A1 | radius `6px`/`14px` → `2px` | `landing.html:26-27` | „oštri uglovi" |
| A2 | pilule `999px` i krugovi `50%` uklonjeni | `.hero-sphere`, badge-evi | „oštri uglovi" |
| A3 | sve glow senke uklonjene | `0 0 80px…160px`, `0 4px 24px` | „bez glow-a" |
| A4 | svi gradijenti kao pozadina uklonjeni | 4 u landingu | „bez gradijenata" |
| A5 | `sphere-breathe` 4s animacija uklonjena | `:241-246` | glow + beskonačna animacija |
| A6 | dva pozadinska `<canvas>`-a uklonjena | `:1104-1207` | beskonačna animacija bez gejta |
| A7 | `--tx-3` uklonjen kao boja teksta | `:24`, 2,44 : 1 | `CONTENT_MAP.md` §7 |
| A8 | `assets/lady_justice.jpg` se ne koristi | — | izričita zabrana |
| A9 | nema emoji ikona; `✓` i `⚠` jedini znaci | `status.html` ih ima 5 | zabrana generičkih ikona |
| A10 | `prefers-reduced-motion` blok obavezan | 0 blokova danas | blueprint |
| A11 | `:focus-visible` obavezan; `outline:none` bez zamene zabranjen | `landing.html:46` | pristupačnost |

### DEO B — odstupanja koja TRAŽE ODOBRENJE VLASNIKA

Ovo su prave dizajnerske odluke, ne primena pravila. Svaka može biti odbijena
bez rušenja ostatka sistema.

---

**B1 · Proza sajta je sans (`Plus Jakarta Sans`), a ne monospace kao u
aplikaciji.** ⚠ **NAJVAŽNIJA ODLUKA U DOKUMENTU**

*Zatečeno:* `vindex.css:2767` — `--font-ui` je JetBrains Mono; telo aplikacije
je monospace.
*Predlog:* sajt zadržava monospace za **svaki podatak, oznaku i broj** (identitet
#3, pojačan i proverljiv — §4.5), ali pasusi su sans.
*Obrazloženje:* v. §4.1 — četiri razloga, uključujući presedan `vindex.css:2786`
gde je aplikacija sama izuzela svoj „ljudski" ekran.
*Ako se odbije:* sve iz §4.5 ostaje; `--vw-font-text` se izjednačava sa
`--vw-font-data`; `--vw-measure` mora pasti sa 68ch na ~58ch jer je monospace
širi; H1/H2 ostaju serif. Sistem ne puca — postaje gušći i teži za duge sekcije
poštenja.

---

**B2 · Sajt nema nijednu svetlu sekciju.**

*Zatečeno:* `landing.html:300-343` — sekcija „Kako radi" je na `#eef3f9`, sa
sopstvenom paletom (`#0d1117` tekst, `#0099bb` akcenat, `#4a5568` telo, `#fff`
kartice, i **jedine senke na celom landingu**).
*Predlog:* ceo sajt ostaje na `#010308`.
*Obrazloženje:* ta sekcija je uvela **peti** akcenat (`#0099bb`) i drugu paletu
teksta, a identitetski element #2 je upravo `#010308`. Ritam sekcija je ionako
rešen linijama i razmakom (§7), ne tonskim skokom. Zadržavanje bi značilo
održavanje dve palete za jednu stranicu.
*Ako se odbije:* svetla varijanta traži sopstveni token blok
(`--vw-bg-light: #eef3f9`, `--vw-text-light`, `--vw-accent-light`) sa iznova
izmerenim kontrastima — otprilike 8 novih tokena.

---

**B3 · Autorski smer je `min-width` (mobile-first).**

*Zatečeno:* oba sistema su desktop-first; `min-width` se ne pojavljuje nijednom.
*Predlog:* novi sajt piše se mobile-first.
*Obrazloženje:* odluka je nevidljiva korisniku i ne dira identitet, ali menja
podrazumevano stanje: bez `@media` bloka dobija se mobilni izgled, ne polomljeni
desktop. Kod advokata je mobilni prvi dodir sa sajtom.
*Ako se odbije:* nema vizuelne posledice, samo autorske.

---

**B4 · Hero sfera se ne zamenjuje sličnim ukrasom, nego SVG dijagramom toka.**

*Zatečeno:* `.hero-sphere` (`:225-296`) — 340px krug, radijalni gradijent, 4s
„disanje", `.sphere-grid` sa mono brojevima `4+ / 0 / ∞ / 7`.
*Predlog:* na to mesto ide **SVG dijagram toka** iz `CONTENT_MAP.md` §4
(pitanje → propisi → odgovor **ili** ćutanje).
*Obrazloženje:* sfera je pao pod A2/A3/A5 (krug + gradijent + glow + beskonačna
animacija) — ne može se „popraviti", samo ukloniti. Ostavljanje praznine tu bi
oslabilo hero. Dijagram je jedina dozvoljena zamena: nema snimaka proizvoda
(`ARCHITECTURE.md` §7.4), a blueprint izričito predviđa dijagram umesto snimka.
Uz to nosi **centralnu poruku**, dok je sfera nosila brojeve koji su sami po sebi
sporni (`4+ / ∞` naspram `18 zakona` vs `847 zakona`, `CONTENT_MAP.md` §6.3).
*Ako se odbije:* jedina druga opcija bez snimka je čist tipografski hero (H1 +
lead + dva dugmeta, bez desne kolone).

---

**B5 · Boje teksta su puni hex, ne `rgba` sa alfom.**

*Zatečeno:* oba sistema koriste `rgba(255,255,255, α)` za sva tri nivoa teksta.
*Predlog:* `#e6edf3` / `#8b98a8` / `#6f7d8f`.
*Obrazloženje:* kontrast `rgba` teksta zavisi od podloge iza njega, pa ista
promenljiva daje različit rezultat na `--vw-bg` i na `--vw-surface`. To je i
mehanizam kojim je `--tx-3` prošao neprimećen. Sa punim hex vrednostima
kontrast je fiksan i **proverljiv automatskim testom** u Fazi G.
*Napomena:* `--vw-text-2 #8b98a8` ima blagi hladan ton (plavkasto-siv), ne čisto
siv — usklađen sa `#010308` koji je takođe plavkast.
*Ako se odbije:* `--vw-text-2` postaje `rgba(255,255,255,0.62)` (7,82 : 1 na
`--vw-bg`, ali ~7,1 na `--vw-surface`).

---

**B6 · Boja upozorenja je `#f0b429`, a ne `#f56565`.**

*Zatečeno:* blueprint navodi `#f56565` kao status greške; `vindex.css` koristi
`#f87171` i `#f0b429` paralelno.
*Predlog:* `#f0b429` za `⚠`, crvena se na sajtu **ne koristi uopšte**.
*Obrazloženje:* v. §3.5. Sajt nema stanje greške — ima ograničenja. Uz to je
`#f56565` jedina nasleđena boja koja pada AAA (6,81 : 1).
*Ako se odbije:* `#f87171` (7,46 : 1) je bolji izbor od `#f56565`.

---

**B7 · Oznaka sekcije: `0.68rem` / težina 500 / tracking `0.16em`.**

*Zatečeno:* `landing.html:120-129` — `0.65rem` / 700 / `0.18em`.
*Predlog:* v. §4.3.
*Obrazloženje:* 10,4px uppercase monospace težine 700 na `#010308` proizvodi
optičko zamućenje. Familija, uppercase, tracking i boja se **ne menjaju** —
menjaju se samo dva broja radi čitljivosti.
*Ako se odbije:* zadržati `0.65rem`/700/`0.18em`, ali oznake **ne** koristiti kao
jedini navigacioni orijentir u sekciji.

---

## 13. ŠTA OVAJ DOKUMENT NE POKRIVA

Da ne bi bilo tumačenja ćutanjem:

- **Sadržaj i tekst** — u `VINDEX_WEBSITE_CONTENT_MAP.md`.
- **Informaciona arhitektura i rute** — Faza C.
- **Redizajn 6 pravnih stranica** — izvan opsega (§0). Njihov beli „Georgia"
  sistem ostaje; `tests/test_api_security.py:84-99` traži rečenicu „ne
  predstavljaju pravni savet" u `/privacy` i `/terms`.
- **Redizajn `status.html`** — otvoreno pitanje vlasnika (`ARCHITECTURE.md` §10,
  pitanje 5). Sadrži 5 zabranjenih emoji i peti akcenat `#89c8ff`. Sistem gore
  je dovoljan da se uradi kad se odluči.
- **Logo u vektorskom obliku** — ne postoji (`ARCHITECTURE.md` §7.2). Logotip je
  i dalje **tekst** `Vindex <em>AI</em>` u `--vw-font-brand`. To je identitetski
  element #1 i ne traži SVG.
- **OG slika, favicon, `manifest.json`** — Faza G. Napomena: `manifest.json:59-73`
  deklariše dva snimka koji ne postoje.
- **`CACHE_NAME` bump** (`static/sw.js:4`) — Faza G, obavezno pri zameni
  landinga (`ARCHITECTURE.md` R1).

---

*Kraj dokumenta. Nijedan produkcioni fajl nije menjan.*
