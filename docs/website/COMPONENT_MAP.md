# VINDEX AI — MAPA KOMPONENATA SAJTA (Faza B)

Katalog svih komponenata novog sajta. Prati `DESIGN_SYSTEM.md`; svi tokeni
(`--vw-*`) su tamo definisani.

**Nijedan produkcioni fajl nije menjan ovim dokumentom.**

---

## 0. KAKO SE ČITA

Svaka komponenta ima isti okvir:

| Polje | Značenje |
|---|---|
| **Namena** | jedan zadatak koji komponenta rešava |
| **Status** | `POSTOJI` · `POSTOJI DELIMIČNO` · `NOVA` — sa tačnom lokacijom u kodu |
| **Anatomija** | delovi, redom |
| **Stanja** | pet stanja iz `DESIGN_SYSTEM.md` §8, ili razlog zašto neko ne postoji |
| **Responzivno** | ponašanje na `<640` / `640-1023` / `≥1024` |
| **Pristupačnost** | semantika, ARIA, tastatura, kontrast |
| **ŠTA NE RADI** | eksplicitne zabrane — najvažnije polje |

### Zbirni pregled

| # | Komponenta | Status | Gde postoji |
|---|---|---|---|
| 1 | Zaglavlje | **POSTOJI** | `landing.html:61-76, 753-766` |
| 2 | Navigacija — desktop | **POSTOJI, RAZBIJENA** | `landing.html:86-99, 757-759` |
| 3 | Navigacija — mobilna | **POSTOJI, NEUSKLAĐENA** | `landing.html:575-639, 769-783` |
| 4 | Hero | **POSTOJI DELIMIČNO** | `landing.html:165-296` |
| 5 | CTA dugme — primarno | **POSTOJI** | `landing.html:130-145` |
| 6 | CTA dugme — sekundarno | **POSTOJI** | `landing.html:146-160` |
| 7 | Kartica sposobnosti | **POSTOJI** | `landing.html:364-390` |
| 8 | Kartica dokaza | **NOVA** | najbliže `.zasto-card` `:429-436` |
| 9 | SVG dijagram toka | **NOVA** | 0 pojava u kodu |
| 10 | Sekcija poverenja | **NOVA** | sadržaj postoji, komponenta ne |
| 11 | Beta forma | **POSTOJI DELIMIČNO** | `index.html:4120-4163`, `routers/waitlist.py:143` |
| 12 | Founding Partner CTA | **NOVA** | — |
| 13 | FAQ akordeon | **POSTOJI DELIMIČNO** | `pricing.html:257-287, 640-705` |
| 14 | Podnožje | **POSTOJI, 9/20 LINKOVA MRTVO** | `landing.html:545-556, 1051-1098` |
| 15 | Oznaka statusa `✓`/`⚠` | **POSTOJI DELIMIČNO** | `vindex.css:9011-9027` |
| 16 | Blok podatka (mono) | **NOVA** | — |
| 17 | Oznaka sekcije (mono labela) | **POSTOJI** | `landing.html:120-129` |

**Ukupno 17.** Postoji u upotrebljivom obliku: **8** (1, 2, 3, 5, 6, 7, 14, 17).
Postoji delimično — mora se prepisati za sajt: **4** (4, 11, 13, 15).
Potpuno novo: **5** (8, 9, 10, 12, 16).

---

## 1. ZAGLAVLJE

**Namena.** Trajno prisutan identitet + jedan jedini put ka konverziji.

**Status: POSTOJI** — `landing.html:61-76` (CSS), `:753-766` (HTML).
Nasleđuje se struktura, menja se sadržaj navigacije i uklanja `backdrop-filter`.

**Anatomija.**
```
[ Preskoči na sadržaj ]  ← vidljiv samo na fokus, prvi u DOM-u
┌──────────────────────────────────────────────────────────────┐
│ Vindex AI            Kako radi  Bezbednost  Za advokate   [CTA] │
└──────────────────────────────────────────────────────────────┘
   ↑ --vw-font-brand      ↑ --vw-font-text        ↑ primarno dugme, mala varijanta
     <em>AI</em> u akcentu
```
- `position: sticky; top: 0; z-index: 100` — **NASLEĐENO** `:61-63`
- `background: var(--vw-bg)` — **puna, neprovidna**
- `border-bottom: 1px solid var(--vw-line)` — **NASLEĐENO** `:67`
- visina `64px` desktop / `56px` mobilni — **NASLEĐENO** `:73`
- `max-width: var(--vw-shell)`, `padding: 0 var(--vw-sp-5)`

**Stanja.** Nema sopstvenih. Zaglavlje je isto na vrhu i posle skrola —
**bez** promene visine, senke ili pozadine pri skrolu.

**Responzivno.**

| Opseg | Ponašanje |
|---|---|
| `<640` | logo levo, dugme fioke desno; linkovi u fioci; visina 56px, padding 20px |
| `640-1023` | isto kao mobilni |
| `≥1024` | horizontalna navigacija, CTA krajnje desno |

**Pristupačnost.**
- `<header>` + `<nav aria-label="Glavna navigacija">`
- Logo je `<a href="/">` sa `aria-label="Vindex AI, početna"` — `<em>` je vizuelni,
  ne semantički naglasak, pa čitač ne sme reći „naglašeno AI"
- Prvi element `<body>`: `<a class="skip" href="#sadrzaj">Preskoči na sadržaj</a>`,
  vidljiv na `:focus`
- Cilj sidra mora imati `scroll-margin-top: 80px` — inače lepljivo zaglavlje
  pokriva fokusirani element

**ŠTA NE RADI.**
- ⚠ **Ne koristi `backdrop-filter: blur(18px)`** (`landing.html:64-65`) ni
  poluprovidnu pozadinu `rgba(1,3,8,0.82)` (`:66`). Blur je `filter`, zabranjen
  u `DESIGN_SYSTEM.md` §9.1, a poluprovidna traka propušta tekst ispod i menja
  kontrast oznaka u nepredvidiv broj.
- Ne menja se pri skrolu — bez skupljanja, bez pojave senke.
- Ne sadrži pretragu, prekidač jezika ni prekidač teme.
- Ne sadrži više od **jednog** dugmeta. Dva CTA-a u zaglavlju znače da nijedan
  nije primarni.
- Ne sadrži logo kao sliku — logotip je **tekst** (identitetski element #1;
  vektorski logo ne postoji, `ARCHITECTURE.md` §7.2).

---

## 2. NAVIGACIJA — DESKTOP

**Namena.** Pristup ka 3-5 stranica koje nose poruku.

**Status: POSTOJI, ali je zatečena razbijena.**
`landing.html:86-99` (CSS), `:757-759` (HTML).

**Zatečeni defekt koji se mora zatvoriti** (`ARCHITECTURE.md` §2.3):
```html
<li><a href="#funkcije">Funkcije</a></li>
<li><a href="#funkcije">Web3</a></li>           <!-- isti cilj -->
<li><a href="#funkcije">Dokumentacija</a></li>  <!-- isti cilj, sekcija ne postoji -->
```
Tri stavke, **dva različita odredišta koja su zapravo jedno**. Dve stavke lažu.

**Anatomija.** `<ul>` sa 3-4 `<li>`; svaki `<a>` je `--vw-font-text`,
`0.9rem`, `--vw-text-2`.

**Stanja.**

| Stanje | Vrednost |
|---|---|
| hover | `color: var(--vw-text)`, `@media (hover: hover)` |
| focus-visible | `outline: 2px solid var(--vw-accent); outline-offset: 2px` |
| active (tekuća stranica) | `color: var(--vw-text)` + `aria-current="page"` + donja linija 1px u `--vw-accent` |
| disabled | ne postoji — nema isključenih linkova |
| loading | ne postoji |

**Responzivno.** `<1024px` — skriva se, zamenjuje je komponenta 3.
**Ista lista linkova**, isti redosled.

**Pristupačnost.**
- `<nav aria-label="Glavna navigacija">` + `<ul>`/`<li>` — čitač objavljuje broj
  stavki
- `aria-current="page"` na tekućoj
- Cilj dodira `≥44px` visine ispod 1024px

**ŠTA NE RADI.**
- ⚠ **Nijedna dva linka ne vode na isto odredište.** Ako se ne razlikuju, to je
  jedan link.
- Nema padajućih menija. Sajt ima 7-9 stranica.
- Nema linkova ka sekcijama koje ne postoje.
- Nema ikona pored stavki.
- Ne sadrži `Cenovnik` — ruta `/pricing` se uklanja (`CONTENT_MAP.md` §6.2).

---

## 3. NAVIGACIJA — MOBILNA (FIOKA)

**Namena.** Isti sadržaj kao desktop navigacija, na malom ekranu.

**Status: POSTOJI, ali NEUSKLAĐENA.** `landing.html:575-639` (CSS),
`:769-783` (HTML).

**Zatečeni defekt.** Desktop meni ima *Funkcije / Web3 / Dokumentacija*, fioka
ima *Funkcije / Kako radi / Zašto Vindex*. **Dva različita sajta na dve širine
istog ekrana.**

**Anatomija.**
```
[≡]  ← dugme, 44×44px, inline SVG (2 ili 3 linije, stroke-width 2)
 ↓ otvara
┌────────────────────────────┐
│ Vindex AI              [×] │
│ ────────────────────────── │  ← 1px --vw-line
│ Kako radi                  │
│ Bezbednost                 │
│ Za advokate                │
│ ────────────────────────── │
│ [ Prijavite se za testiranje ] │  ← primarno dugme, puna širina
└────────────────────────────┘
```
- `position: fixed; inset: 0` — puna površina, **NE** delimični panel
- `background: var(--vw-bg)` — **puna**, ne `blur(4px)` (`landing.html:582`)
- Animacija: samo `opacity` + `transform: translateY(-8px)`, `--vw-t-base`

**Stanja.**

| Stanje | Vrednost |
|---|---|
| zatvorena | `display: none` (ne samo `opacity: 0` — mora izaći iz reda fokusa) |
| otvorena | `display: flex`, `aria-expanded="true"` na dugmetu |
| hover stavke | `color: var(--vw-text)` |
| focus-visible | isti prsten |

**Responzivno.** Vidljiva `<1024px`. Na `≥1024px` dugme `[≡]` ima
`display: none` — i sama fioka takođe.

**Pristupačnost — ovo je najzahtevnija komponenta na sajtu.**
- Dugme: `<button aria-expanded="false" aria-controls="fioka">` +
  `aria-label="Otvori meni"` / `"Zatvori meni"`
- **Zamka fokusa (focus trap)**: `Tab` kruži unutar fioke dok je otvorena
- `Esc` zatvara i **vraća fokus na dugme `[≡]`**
- `<body>` dobija `overflow: hidden` dok je otvorena
- Prvi fokusirani element pri otvaranju: dugme za zatvaranje `[×]`
- Ako JS ne radi, fioka mora ostati zatvorena, a linkovi **dostupni u podnožju**

**ŠTA NE RADI.**
- ⚠ **Ne prikazuje drugačiji skup linkova od desktop navigacije.** Ista lista,
  isti redosled, ista imena.
- Ne koristi `backdrop-filter: blur(4px)` (`landing.html:582`) — §9.1.
- Ne kliza sa strane. Otvara se odozgo (`drawer-slide-down`, **NASLEĐENO**
  `:597-602`), jer je izvor gest dugme u zaglavlju.
- Nema podmenija.
- Ne ostaje u redu fokusa kad je zatvorena.

---

## 4. HERO

**Namena.** Jedna rečenica koja opravdava zašto posetilac ostaje, i jedna radnja.

**Status: POSTOJI DELIMIČNO.** `landing.html:165-296`. Levi (tekstualni) stub se
nasleđuje; desni (`.hero-sphere` `:225-296`) se **uklanja u celini** i zamenjuje
komponentom 9 — v. `DESIGN_SYSTEM.md` §12 B4.

**Anatomija.**
```
┌───────────────────────────────┬──────────────────────────┐
│ POČETNA                       │                          │
│  ↑ oznaka sekcije (komp. 17)  │   SVG dijagram toka      │
│                               │      (komponenta 9)      │
│ Odgovor sa navedenim          │                          │
│ propisom. Ili nikakav         │   pitanje → propisi →    │
│ odgovor.                      │      odgovor             │
│  ↑ H1, --vw-font-brand        │           ↓              │
│                               │        ili ćutanje       │
│ Vindex vam kaže na kojim      │                          │
│ propisima počiva svaki        │                          │
│ odgovor — i ćuti kada         │                          │
│ pouzdan izvor ne postoji.     │                          │
│  ↑ lead, max-width 520px      │                          │
│                               │                          │
│ [ Prijavite se ]  [ Bezb. list ] │                       │
│   primarno         sekundarno │                          │
└───────────────────────────────┴──────────────────────────┘
```

Raspored `1.1fr / 1fr`, `gap: var(--vw-sp-8)`, `padding: var(--vw-sp-9) 0`.

**Stanja.** Nema. Hero je statičan.

**Responzivno.**

| Opseg | Ponašanje |
|---|---|
| `<640` | jedna kolona; dijagram **ispod** teksta; H1 `2.4rem`; dugmad puna širina, jedno ispod drugog |
| `640-1023` | jedna kolona; dijagram ispod, centriran, `max-width: 480px` |
| `≥1024` | dve kolone |

**Pristupačnost.**
- Tačno jedan `<h1>` po stranici
- Prvo dugme je prvi element u redu fokusa posle navigacije
- H1 je stvarni tekst, nikad slika

**ŠTA NE RADI.**
- ⚠ **Ne sadrži lažan snimak ekrana ni mockup interfejsa.** Nijedan snimak
  proizvoda ne postoji (`ARCHITECTURE.md` §7.3 — plan traži tri, urađeno nula),
  a blueprint izričito zabranjuje mockup koji prikazuje nepostojeći interfejs.
- ⚠ **Ne sadrži brojeve o korpusu.** `landing.html:905` tvrdi „18 zakona RS",
  `index.html:4209` tvrdi „847 zakona Srbije" — najmanje jedan je netačan.
  Do provere korpusa **nijedan broj ne ide na sajt** (`CONTENT_MAP.md` §6.3).
  Ovo pada i na `.sphere-grid` brojeve `4+ / 0 / ∞ / 7` (`landing.html:281`).
- ⚠ **Ne koristi rečenicu „Vindex zna odakle zna" kao naslov.** Obećava trag do
  dokumenta koji ne postoji (`CONTENT_MAP.md` §1).
- Ne sadrži `assets/lady_justice.jpg` ni bilo koju alegorijsku fotografiju.
- Ne sadrži `<canvas>`, sferu, čestice ni animiranu pozadinu.
- Ne sadrži video — CSP `media-src` pada na `default-src 'self'`.
- Ne sadrži više od dva dugmeta.
- Ne sadrži logotipe klijenata — nema korisnika (`CONTENT_MAP.md` §5).

---

## 5. CTA DUGME — PRIMARNO

**Namena.** Jedna radnja po ekranu: prijava za zatvoreno testiranje.

**Status: POSTOJI** — `.btn-filled`, `landing.html:130-145`.

**Anatomija.**
```
background:     var(--vw-accent);      /* NASLEĐENO */
color:          var(--vw-accent-ink);  /* NASLEĐENO — 11,65:1 */
font-family:    var(--vw-font-text);
font-weight:    600;                   /* landing ima 700 */
letter-spacing: 0.01em;                /* NASLEĐENO */
padding:        14px 28px;             /* NASLEĐENO */
border:         none;
border-radius:  var(--vw-radius);      /* 2px, ne nasleđenih 6px */
min-height:     44px;
```

Varijante veličine (**NASLEĐENO**): `nav` `9px 22px` / `0.85rem` — uz obavezan
`min-height: 44px` ispod 1024px; `hero` `16px 40px` / `1.05rem` (`.cta-btn` `:535`).

**Stanja.**

| Stanje | Vrednost | Poreklo |
|---|---|---|
| hover | `opacity: 0.88` | **NASLEĐENO** `:143` |
| focus-visible | `outline: 2px solid var(--vw-accent); outline-offset: 2px` | **NOVO** |
| active | `opacity: 0.72` | **NOVO** |
| disabled | `background: transparent; color: var(--vw-text-disabled); border: 1px solid var(--vw-line)` | **NOVO** |
| loading | tekst → `Šalje se…`, `aria-busy="true"`, `disabled` | **NOVO** |

**Responzivno.** `<640px` — `width: 100%`. `≥640px` — širina po sadržaju.

**Pristupačnost.**
- `<a>` ako navigira, `<button>` ako pokreće radnju. Nikad `<div onclick>`.
- Tekst mora sam po sebi imati smisao izvan konteksta („Prijavite se za
  zatvoreno testiranje", ne „Klikni ovde")
- `outline-offset: 2px` — prsten iste boje kao pozadina dugmeta bio bi nevidljiv
  bez razmaka

**ŠTA NE RADI.**
- ⚠ Ne koristi `transform: translateY(-1px)` na hover (`landing.html:144`) — bez
  senke, pomeranje izgleda kao greška u rasporedu.
- ⚠ Ne koristi `box-shadow: 0 4px 24px rgba(0,212,255,0.35)` — mobilni sticky CTA
  (`landing.html:650-661`) ga danas ima; to je glow.
- ⚠ Ne piše „Počnite besplatno", „Zakažite demo" ni „Kontaktirajte prodaju" —
  izričito zabranjeno (`CONTENT_MAP.md` §4).
- Ne vodi na `/app#register` uz obećanje samouslužne registracije dok `/app`
  pre-auth ekran kaže „Zatražite rani pristup" (`ARCHITECTURE.md` §0, R11).
- Nema ikone, strelice ni `→` unutar teksta.
- Nema više od jednog primarnog dugmeta u vidnom polju.

---

## 6. CTA DUGME — SEKUNDARNO

**Namena.** Druga radnja koja ne konkuriše prvoj: preuzimanje bezbednosnog lista.

**Status: POSTOJI** — `.btn-outline`, `landing.html:146-160`.

**Anatomija.** Identična geometrija kao primarno; razlika je samo u boji:
```
background:    transparent;
color:         var(--vw-text);
border:        1px solid var(--vw-line-2);
border-radius: var(--vw-radius);
```

**Stanja.**

| Stanje | Vrednost | Poreklo |
|---|---|---|
| hover | `border-color: var(--vw-line-accent)` + `background: var(--vw-accent-soft)` | **NASLEĐENO** `:157-159` |
| focus-visible | isti prsten | **NOVO** |
| active | `opacity: 0.72` | **NOVO** |
| disabled | isto kao primarno | **NOVO** |
| loading | ne postoji — sekundarno dugme nikad ne šalje formu | — |

**Responzivno.** Isto kao primarno.

**Pristupačnost.** Za preuzimanje PDF-a (`static/Vindex-AI-Bezbednosni-List.pdf`,
95 KB, **postoji**): tekst mora sadržati format i veličinu —
`Preuzmite bezbednosni list (PDF, 95 KB)`.

**ŠTA NE RADI.**
- Ne izgleda kao primarno. Ako se boje razlikuju samo u nijansi, hijerarhija ne
  postoji.
- ⚠ Ne koristi punu pozadinu ni akcentnu boju teksta.
- Ne stoji samo — sekundarno dugme uvek prati primarno.

---

## 7. KARTICA SPOSOBNOSTI

**Namena.** Jedna od 6 grupa iz „Šta radi danas" (`CONTENT_MAP.md` §4, sekcija 5).

**Status: POSTOJI** — `.fn-card` `landing.html:373-378` unutar `.fn-grid`
`:364-372`. **Ovo je najbolji zatečeni obrazac na landingu i nasleđuje se
doslovno.**

**Anatomija — obrazac linijske mreže.**
```
.fn-grid {
  display: grid;
  gap: 1px;                        /* landing ima 2px */
  background: var(--vw-line);      /* gap postaje linija */
  overflow: hidden;
}
.fn-card {
  background: var(--vw-bg);        /* NE surface — mreža nosi kontrast */
  padding: var(--vw-sp-5);
  border: none;                    /* linije dolaze iz gap-a */
  border-radius: 0;
}
```
Zašto je ovo dobro: nema dupliranih ivica na spojevima ćelija, linije su
neprekinute, a ćelija koja se proteže preko cele širine (`.fn-full` `:379`,
`grid-column: 1 / -1`) se uklapa bez izuzetka u CSS-u.

Sadržaj ćelije, redom:
```
DOKUMENTI                      ← oznaka, komponenta 17
Analiza i izvlačenje podataka  ← H3, --vw-font-brand
Iz otpremljenog dokumenta …    ← telo, --vw-text-2, max 44ch
✓ RADI DANAS                   ← oznaka statusa, komponenta 15
```

**Stanja.**

| Stanje | Vrednost |
|---|---|
| hover | `background: var(--vw-surface)` — **NASLEĐENO-IZMENJENO**, landing koristi `rgba(0,212,255,0.04)` |
| focus-visible | samo ako je kartica link; tada prsten na celoj ćeliji |
| active / disabled / loading | ne postoje — kartica je statična |

**Responzivno.** `<640` — 1 kolona · `640-1023` — 2 kolone · `≥1024` — 3 kolone.
`gap: 1px` na svim širinama.

**Pristupačnost.**
- `<ul>` / `<li>` ako je lista sposobnosti — čitač objavljuje „6 stavki"
- H3 unutar ćelije mora biti stvarni `<h3>`, ne stilizovan `<div>`
- Ako je cela kartica klikabilna: `<a>` obavija sadržaj, `:focus-visible` prsten
  ide na ćeliju, i **nema** zasebnog „Saznaj više" linka unutra (dupli tab-stop)

**ŠTA NE RADI.**
- ⚠ **Nema ikonu.** Ni emoji, ni SVG piktogram. `.zasto-ico` (`landing.html:186`,
  10px radius) se ne prenosi. Vizuelnu razliku nose oznaka i naslov.
- ⚠ **Ne opisuje ništa što nije `PRODUCTION`** u capability mapi
  (`CONTENT_MAP.md` §4). Ako je u izradi, ide u komponentu 15 sa `⚠`, ne ovde.
- Ne sadrži brojeve („40+ funkcija", „847 zakona").
- Ne sadrži cenu ni plan.
- Ne sadrži senku ni podignut hover.

---

## 8. KARTICA DOKAZA (tvrdnja + izvor)

**Namena.** Nosi tri dokaza iz `CONTENT_MAP.md` §2. Ovo je **najvažnija
komponenta na sajtu** — jedina koja pretvara tvrdnju u proverljivu tvrdnju.

**Status: NOVA.** Najbliže postojeće je `.zasto-card` (`landing.html:429-436`),
ali ona nema mesto za izvor — nosi samo tvrdnju. Razlika nije stilska nego
strukturna, pa se gradi ispočetka.

**Anatomija — tri obavezna sloja, redom.**
```
┌──────────────────────────────────────────────┐
│ DOKAZ 01                                     │ ← oznaka, --vw-font-data
│                                              │
│ Brojeve računa program.                      │ ← tvrdnja, H3, --vw-font-brand
│ AI ih samo objašnjava.                       │
│                                              │
│ Nijedan AI izlaz ne sme biti jedini izvor    │ ← mehanizam, telo, --vw-text-2
│ rizika, statusa, roka ni spremnosti.         │
│ ──────────────────────────────────────────── │ ← 1px --vw-line
│ ✓  DOKAZ   services/risk_engine.py           │ ← izvor, --vw-font-data, 0.8rem
│            10+ test fajlova, 6+ rutera       │
└──────────────────────────────────────────────┘
border: 1px solid var(--vw-line-accent);   /* NASLEĐENO od .zasto-card */
border-radius: var(--vw-radius);
padding: var(--vw-sp-5);
```

**Podnožje izvora je obavezno.** Kartica dokaza bez izvora je kartica sposobnosti
i mora se preimenovati. To je jedino strukturno pravilo koje se u Fazi G
proverava automatski.

**Stanja.**

| Stanje | Vrednost |
|---|---|
| hover | `border-color: var(--vw-accent)` — bez pomeranja i bez promene pozadine |
| focus-visible | samo ako izvor vodi negde |
| active / disabled / loading | ne postoje |

**Responzivno.** `<640` — 1 kolona, `padding: var(--vw-sp-4)` ·
`640-1023` — 1 kolona (kartice su tekstualno guste) · `≥1024` — 3 u redu.

**Pristupačnost.**
- Znak `✓` je dekorativan uz tekstualnu oznaku `DOKAZ` — `aria-hidden="true"`
- Ime fajla u izvoru je `<code>` unutar `--vw-font-data`
- Kontrast podnožja: `--vw-text-2` na `--vw-bg` = **7,03 : 1**. Izvor se
  **nikad** ne prigušuje ispod tog nivoa — on je poenta kartice.

**ŠTA NE RADI.**
- ⚠ **Nema ikonu.** Ni emoji, ni piktogram, ni brojčani „badge" u krugu.
- ⚠ **Ne sme postojati bez izvora.** Tvrdnja bez podnožja izvora se ne
  objavljuje.
- ⚠ **Ne tvrdi ništa što nije u `CLAIMS_REGISTRY.md`.** Nema procenta tačnosti
  ni uštede vremena — nikad nisu mereni (`CONTENT_MAP.md` §5).
- ⚠ **Ne piše „AI nikad ne presuđuje"** — ograničenje verdikta postoji samo u
  orkestratoru strategije, ne na tri samostalne rute (`CONTENT_MAP.md` §5).
- ⚠ **Ne piše „zaštićeno na nivou baze"** — izolacija počiva na 541 ručnom
  filteru u kodu. Dozvoljena formulacija: *„razdvojeno po nalogu, pokriveno
  testovima"*.
- Ne sadrži citat, preporuku ni ime osobe — nema korisnika.
- Izvor nije klikabilan link ka GitHubu — repo je javan, ali sajt ne poziva na
  čitanje koda.

---

## 9. SVG DIJAGRAM TOKA

**Namena.** Zamena za snimke proizvoda kojih nema. Nosi centralnu poruku u
heroju i četiri koraka u sekciji „Kako radi".

**Status: NOVA.** Nula pojava u kodu. Landing ima samo dekorativni
`.hero-sphere` (`:225-296`), koji nije dijagram i uklanja se.

**Zašto dijagram, a ne snimak** (`ARCHITECTURE.md` §7.4) — tri nezavisna razloga:
1. Snimci ne postoje: plan traži tri (`context.png`, `provenance.png`,
   `deadline.png`), urađeno **nula**.
2. Ne mogu se napraviti — sintetički demo predmet ne postoji, a stvarni podaci
   su zabranjeni.
3. Najvažniji (`provenance.png`) je **tehnički nemoguć danas** — prikaz izvora u
   tom obliku nije uključen u UI.

**Anatomija.**
```
inline <svg viewBox="0 0 720 240" role="img" aria-labelledby="dijagram-naslov dijagram-opis">
  <title id="dijagram-naslov">…</title>
  <desc  id="dijagram-opis">…</desc>
  …
</svg>
```
- Sve linije: `stroke="currentColor"`, `stroke-width="1"`, `fill="none"`
- Boje **isključivo** preko `currentColor` i `var(--vw-*)` — nikad hardkodirano
- Sav tekst u dijagramu je `<text>` sa `font-family: var(--vw-font-data)`,
  veličina `12` (ne manje)
- Uglovi pravougaonika: `rx="2"` (`--vw-radius`)
- Grananje „ili ćutanje" iscrtava se **isprekidanom linijom**
  (`stroke-dasharray="3 3"`) u `--vw-warn` — to je jedino mesto gde je isprekidana
  linija dozvoljena, jer označava putanju koja se **ne** dešava

**Stanja.** Nema. Dijagram je statičan i neinteraktivan.

**Responzivno.**

| Opseg | Ponašanje |
|---|---|
| `<640` | vertikalna varijanta — **zaseban `<svg>`**, ne skalirani horizontalni |
| `640-1023` | vertikalna ili 2×2, `max-width: 480px` |
| `≥1024` | horizontalni tok, `width: 100%; height: auto` |

Prebacivanje ide preko dva `<svg>`-a i CSS `display`, ne preko `viewBox`
manipulacije. **Nikad** `overflow-x: auto` na heroju — dijagram koji se skroluje
u heroju ne prenosi poruku.

**Pristupačnost.**
- `role="img"` + `<title>` + `<desc>` + `aria-labelledby`
- **Tekstualni ekvivalent ispod dijagrama, uvek vidljiv** — ne `alt`, ne
  `sr-only`. Poruka je previše važna da zavisi od SVG podrške.
- Tekst u SVG-u je `<text>`, nikad putanja/kriva — mora se pretražiti `Ctrl+F`
- Kontrast svake linije prema `--vw-bg` mora biti `≥3:1` (SC 1.4.11):
  `--vw-accent` 11,65 · `--vw-text-2` 7,03 · `--vw-warn` 11,07 — svi prolaze.
  `--vw-line` (1,10 : 1) se **ne** koristi za linije dijagrama.

**ŠTA NE RADI.**
- ⚠ **Ne prikazuje interfejs.** Nema prozora, nema tab-ova, nema dugmadi, nema
  lažnog kursora. Dijagram je apstraktan tok, i to mora biti očigledno na prvi
  pogled — inače je mockup nepostojećeg ekrana.
- ⚠ **Ne tvrdi da prikazuje postojeći ekran** ni u naslovu ni u opisu.
- Nije `<img src="…">` — CSP `img-src 'self' data: blob:` bi to dozvolio sa
  istog origina, ali eksterni SVG gubi `currentColor` i tokene.
- Nema animacije: nema `<animate>`, nema `stroke-dasharray` animacije crtanja.
- Nema gradijenata (`<linearGradient>`, `<radialGradient>`) ni filtera
  (`<filter>`, `feGaussianBlur`) — to su glow i gradijent drugim sredstvima.
- Nema brojeva o korpusu.

---

## 10. SEKCIJA POVERENJA / GOVERNANCE

**Namena.** Jedina sekcija koja odgovara na pitanje „šta se dešava sa podacima
mog klijenta" — i vodi ka 6 pravnih stranica koje `landing.html` **danas ne
linkuje nijednom**.

**Status: NOVA.** Sadržaj postoji (`security.html`, `dpa.html`,
`ai-disclosure.html`, `bezbednosni-list.html`, `privacy.html`, `terms.html`),
komponenta ne postoji.

**Anatomija.**
```
BEZBEDNOST I OBAVEZE                       ← oznaka sekcije

Šta radimo sa podacima vašeg klijenta      ← H2

┌─────────────┬─────────────┬─────────────┐  ← linijska mreža (obrazac komp. 7)
│ RAZDVAJANJE │ OBRADA      │ AI          │
│ Razdvojeno  │ Ugovor o    │ Koji model, │
│ po nalogu,  │ obradi …    │ šta se      │
│ pokriveno   │             │ šalje …     │
│ testovima   │             │             │
│ → Bezb. list│ → DPA       │ → AI disc.  │
└─────────────┴─────────────┴─────────────┘

┌──────────────────────────────────────────┐
│ ⚠  ŠTA NEMAMO                            │  ← blok ograničenja, --vw-warn ivica
│    Nema nezavisne bezbednosne revizije    │
│    ni sertifikata.                        │
└──────────────────────────────────────────┘

[ Preuzmite bezbednosni list (PDF, 95 KB) ]   ← sekundarno dugme
```

**Blok „ŠTA NEMAMO" je obavezan deo komponente, ne opcioni dodatak.**
`CONTENT_MAP.md` §5: „Ovo nije sekcija stida nego diferencijator — konkurencija
ovo ne piše."

**Stanja.** Kao komponenta 7.

**Responzivno.** `<640` — 1 kolona · `640-1023` — 2 · `≥1024` — 3.
Blok ograničenja je uvek pune širine.

**Pristupačnost.**
- Linkovi ka pravnim stranicama su stvarni `<a href="/dpa">`, nikad `href="#"`
- `⚠` je `aria-hidden="true"` uz vidljivu tekstualnu oznaku `ŠTA NEMAMO`
- Blok ograničenja **nije** `role="alert"` — nije hitno obaveštenje nego stalan
  sadržaj

**ŠTA NE RADI.**
- ⚠ **Ne prikazuje sertifikacione znakove** (ISO, SOC 2, GDPR pečat). Nema
  nezavisne revizije ni sertifikata.
- ⚠ **Ne piše „zaštićeno na nivou baze" / „RLS"** — aplikacija se povezuje
  service ključem koji RLS zaobilazi. Dozvoljeno: *„razdvojeno po nalogu,
  pokriveno testovima"*.
- ⚠ **Ne obećava SLA ni procenat dostupnosti** — `/status` prikazuje samo status
  i latenciju, uptime procenat se nigde ne meri.
- ⚠ **Nema `href="#"`.** Ako odredište ne postoji, link se ne prikazuje.
- Nema katanaca, štitova ni emoji.

---

## 11. BETA FORMA

**Namena.** Jedina sabirna tačka sajta.

**Status: POSTOJI DELIMIČNO — i to je najveći strukturni nalaz ove mape.**

| Sloj | Gde je danas | Za sajt |
|---|---|---|
| Backend | `routers/waitlist.py:143` `POST /waitlist/prijava` — **javan, bez autentifikacije**, registrovan u `api.py:745` | **spreman, koristi se kakav jeste** |
| Tabela | `waitlist` (`ime`, `email`, `firma`, `telefon`, `poruka`, `status`, `created_at`) | spremna |
| Frontend | **samo u aplikaciji** — `index.html:4120-4163` (`.wl-*`), otvara se preko `wl_open()` (`:4187`) | **mora se napisati za sajt** |
| Landing | `landing.html` nema **nijednu** formu i **nijedan `<input>`** | — |

**Anatomija.**
```
┌────────────────────────────────────────┐  max-width: var(--vw-form) = 560px
│ Ime i prezime *                        │
│ [                                    ] │
│ Email adresa *                         │
│ [                                    ] │
│ Kancelarija / firma                    │
│ [                                    ] │
│ Šta vas najviše zanima?                │
│ [                                    ] │
│                                        │
│ [ Prijavite se za zatvoreno testiranje ] │
│                                        │
│ Podaci se koriste isključivo za …      │  ← --vw-text-2, 0.875rem
│ Politika privatnosti · Uslovi          │  ← obavezni linkovi
└────────────────────────────────────────┘
```

Polje:
```
background:    var(--vw-surface);
border:        1px solid var(--vw-line-input);   /* 3,22:1 — SC 1.4.11 */
border-radius: var(--vw-radius);
padding:       12px 14px;
font-family:   var(--vw-font-text);
font-size:     16px;                             /* nikad manje — iOS zumira */
color:         var(--vw-text);
min-height:    44px;
```

**Stanja — svih pet, i sva su NOVA.**

| Stanje | Vrednost |
|---|---|
| default | `border-color: var(--vw-line-input)` |
| hover | `border-color: var(--vw-text-2)` |
| focus-visible | `outline: 2px solid var(--vw-accent); outline-offset: 2px` |
| greška | `border-color: var(--vw-warn)` + poruka ispod polja, u `--vw-warn`, sa `⚠` |
| disabled (u toku slanja) | `color: var(--vw-text-disabled)`, `cursor: not-allowed` |
| loading | dugme → `Šalje se…`, `aria-busy="true"`, sva polja `disabled` |
| uspeh | forma se zamenjuje porukom uspeha sa `✓` |

**Responzivno.** Uvek jedna kolona. Polja uvek puna širina. `max-width: 560px`,
centrirano. Bez „ime | prezime" u dva stupca ni na desktopu — `.wl-row` obrazac
iz aplikacije (`index.html:4142`) se **ne** prenosi.

**Pristupačnost — najstroža na sajtu.**
- `<form>`, `<label for="…">` za **svako** polje. Nikad `placeholder` umesto
  labele.
- `placeholder` je primer, ne uputstvo. Nasleđeni primeri iz `index.html:4145,
  4149` (`marko@kancelarija.rs`, `+381 60 123 4567`) su dobri i prenose se.
- `required` + `aria-required="true"`; zvezdica `*` mora imati tekstualno
  objašnjenje („Polja sa `*` su obavezna")
- `autocomplete="name" / "email" / "organization" / "tel"`
- `type="email"`, `type="tel"` — ispravna tastatura na mobilnom
- **`aria-live="polite"` region** za rezultat slanja. Bez njega korisnik čitača
  ne sazna da je forma poslata.
- Poruka greške vezana preko `aria-describedby`, i fokus se pomera na prvo
  neispravno polje
- Validacija na `submit`, ne na `input` — validacija u toku kucanja prijavljuje
  grešku pre nego što je korisnik završio

**ŠTA NE RADI.**
- ⚠ **Ne traži lozinku i ne kreira nalog.** Ovo je waitlist, ne registracija.
  Zatečena kontradikcija (`/` prodaje samouslužnu registraciju, `/app` zatvorenu
  betu — `ARCHITECTURE.md` §0, R11) rešava se time što sajt zauzima **jednu**
  stranu: zatvoreno testiranje.
- ⚠ **Ne traži podatke o klijentu, predmetu ni bilo šta poverljivo.** Četiri
  polja, od kojih dva obavezna.
- ⚠ **Ne šalje ništa trećoj strani.** CSP `connect-src` ne dozvoljava spoljne
  hostove za ovu namenu; forma ide na `self`.
- ⚠ **Ne sadrži CAPTCHA.** Svaki poznati provajder traži eksterni skript ili
  iframe — `frame-src` pada na `default-src 'self'`. Ako zaštita zatreba, rešava
  se serverski (rate limit) ili honeypot poljem.
- ⚠ **Nema analitike ni piksela za praćenje konverzije** — `connect-src` nema
  nijedan analitički host.
- Nema polja „broj advokata", „prihod", „veličina firme" — to je kvalifikacija
  prodaje, a prodaje nema.
- Ne prikazuje „Već ste na listi!" kao grešku — backend to vraća kao uspeh
  (`waitlist.py`), i sajt to poštuje.

---

## 12. FOUNDING PARTNER CTA

**Namena.** Poslednja sekcija početne. Iskrena ponuda za zatvoreno testiranje.

**Status: NOVA.** Postoji samo prazna ljuštura `.cta-*` (`landing.html:526-539,
1043-1046`) sa velikim logotipom (`.cta-logo`, `clamp(3rem, 6vw, 6rem)`).
Ta tipografska ideja se nasleđuje, sadržaj je nov.

**Anatomija.**
```
──────────────────────────────────────────  ← 1px --vw-line, puna širina

              Vindex AI                     ← --vw-font-brand, clamp(3rem,6vw,6rem)
                                              <em>AI</em> u --vw-accent

     Tražimo mali broj advokata koji će
     raditi sa nama pre javnog otvaranja.

     ┌───────────────────────────────┐
     │ ⚠  STANJE                     │      ← blok poštenja
     │    Pred zatvoreno testiranje.  │
     │    Nema korisnika. Nema        │
     │    merenih rezultata.          │
     └───────────────────────────────┘

     [ Prijavite se ]   [ Bezbednosni list ]

padding: var(--vw-sp-9) 0;
```

**Stanja.** Nema sopstvenih; dugmad nose svoja.

**Responzivno.** Uvek centrirano, jedna kolona.
`<640` — `padding: var(--vw-sp-7) 0`, logotip na donjoj granici `clamp`, dugmad
puna širina, jedno ispod drugog.

**Pristupačnost.**
- Logotip je ovde **dekorativan** (isti tekst je već `<h1>`/zaglavlje) — nosi
  `aria-hidden="true"`, a stvarni naslov sekcije je `<h2>` iznad ili
  `class="sr-only"`
- `⚠` je `aria-hidden` uz vidljivu oznaku `STANJE`

**ŠTA NE RADI.**
- ⚠ **Ne stvara lažnu oskudicu.** Bez „Ostalo još 3 mesta", bez odbrojavanja,
  bez „Ponuda ističe". Pre-auth ekran danas piše „Beta · Ograničen broj mesta"
  (`index.html:4187`) — broj nije nigde definisan.
- ⚠ **Ne pominje cenu, popust ni „doživotni pristup".** Nijedan plan se ne može
  kupiti: `STRIPE_URL = ''` (`static/vindex.js:124`).
- ⚠ **Ne izostavlja blok poštenja.** „Nema korisnika, nema merenih rezultata" je
  deo ponude, ne fusnota.
- Nema brojača prijavljenih.
- Nema glow-a ni gradijenta — `.cen-card.pro` (`landing.html:497`) sa duplim
  `0 0 60px` / `0 0 120px` je mrtav CSS i ne prenosi se.

---

## 13. FAQ (AKORDEON)

**Namena.** Pitanja koja bi inače postala email.

**Status: POSTOJI DELIMIČNO — i postojeća implementacija se NE prenosi.**
`pricing.html:257-287` (CSS), `:640-705` (HTML, 7 stavki).

Tri razloga zbog kojih se prepisuje:

1. **`pricing.html` se uklanja** (`CONTENT_MAP.md` §6.2), a sa njim i sav njegov
   sadržaj FAQ-a — 7 pitanja o trialu, popustima i limitima koji se ne mogu
   naplatiti.
2. **Nije pristupačan.** `<div class="faq-q" onclick="faqToggle(this)">` — `div`
   sa `onclick`: nema `<button>`, nema `aria-expanded`, nema pristupa
   tastaturom.
3. **`max-height: 250px`** (`:285`) — odgovor duži od 250px se **tiho seče**.

**Anatomija.**
```
┌────────────────────────────────────────────┐
│ Da li Vindex daje pravni savet?        [+] │  ← <button>, --vw-font-text, 1rem
├────────────────────────────────────────────┤  ← 1px --vw-line
│ Ne. Procena rizika je pomoć u proceni …    │  ← panel, --vw-text-2
└────────────────────────────────────────────┘
```
- Označivač: `+` / `−` u `--vw-font-data` — **ne** rotirajuća strelica `›`
  (`pricing.html:286` rotira za 90°; rotacija je `transform`, dozvoljena, ali
  `+`/`−` je jednoznačno bez oslonca na orijentaciju)
- Prelaz: `max-height` + `opacity`, `--vw-t-base`. `max-height` je jedini
  izuzetak od pravila „samo `opacity`/`transform`" (`DESIGN_SYSTEM.md` §9.1) i
  postoji samo ovde.

**Stanja.**

| Stanje | Vrednost |
|---|---|
| zatvoren | `aria-expanded="false"`, panel `hidden` |
| otvoren | `aria-expanded="true"`, oznaka `−` |
| hover | `background: var(--vw-surface)` |
| focus-visible | prsten na celom redu pitanja |
| disabled / loading | ne postoje |

**Responzivno.** Uvek jedna kolona, puna širina do `var(--vw-measure)`.
Pitanje `<640px` prelama se u dva reda; oznaka `[+]` ostaje poravnata uz vrh.

**Pristupačnost.**
- Pitanje je `<button type="button" aria-expanded aria-controls="…">` unutar
  `<h3>` — nikad `<div onclick>`
- Panel: `<div id="…" role="region" aria-labelledby="…">`
- `Enter` i `Space` otvaraju
- **Bez JS-a**: `<details>`/`<summary>` kao osnova, ili svi paneli otvoreni. FAQ
  koji bez JS-a ne pokazuje odgovore je nevidljiv i pretraživačima.
- **Nema `max-height` u fiksnim pikselima** koji seče sadržaj

**ŠTA NE RADI.**
- ⚠ **Ne odgovara na pitanja o ceni.** Nema cenovnika.
- ⚠ **Ne seče odgovor.** Ako je odgovor duži od tri rečenice, to je zasebna
  stranica, ne FAQ stavka.
- ⚠ **Ne postoji ako ima manje od četiri pitanja.** Ispod toga su to pasusi.
- Ne otvara više panela odjednom bez potrebe — nije `radio` ponašanje, ali
  podrazumevano stanje je „sve zatvoreno" osim prvog.
- Nema ikona pored pitanja.

---

## 14. PODNOŽJE

**Namena.** Karta sajta + jedine veze ka 6 pravnih stranica.

**Status: POSTOJI, ali je 9 od 20 linkova mrtvo.**
`landing.html:545-556` (CSS), `:1051-1098` (HTML).

**Zatečeni defekti** (`ARCHITECTURE.md` §2.4):
- **9 od 20 linkova je `href="#"`**: Zakoni RS, Sudska praksa, Web3 MiCA,
  Dokumentacija, Arhitektura, Bezbednost, API, O nama, Kontakt
- Preostalih 10 vodi na `#funkcije` — jedan isti anchor
- **Nula linkova ka pravnim stranicama.** „Bezbednost" je `href="#"`, iako
  `/security` postoji i javan je
- Ceo podnožje je na `--tx-3` = **2,44 : 1** — pada AA

**Anatomija.**
```
──────────────────────────────────────────────────  ← 1px --vw-line
Vindex AI                PROIZVOD    OBAVEZE    PRAVNO
                                                        ← naslovi kolona:
Pravni operativni        Kako radi   Bezbednost Privatnost
sistem za advokate       Za advok.   AI izjava  Uslovi
u Srbiji.                Tehnolog.   DPA        Status
                                     Bezb. list
──────────────────────────────────────────────────  ← 1px --vw-line
© MMXXVI · Vindex AI                       vindex.rs
  ↑ --vw-font-data, 0.8rem, --vw-text-2
```
- Mreža `1.6fr 1fr 1fr 1fr` — **NASLEĐENO** `:545` (5 kolona → 4, jer se
  „Protokol" i „Baza" gase; njihovi linkovi su bili `href="#"`)
- Naslovi kolona: komponenta 17
- `© MMXXVI` rimskim brojevima — **NASLEĐENO** `:1093-1096`, zadržava se

**Stanja.** Link: hover `color: var(--vw-text)`; focus-visible prsten.

**Responzivno.** `<640` — kolone jedna ispod druge, brend blok prvi, donji red
prelama se u dva · `640-1023` — 2×2 · `≥1024` — 4 u redu.

**Pristupačnost.**
- `<footer>` + `<nav aria-label="Podnožje">` po koloni, sa `<h2 class="sr-only">`
  ili stvarnim naslovom kolone
- **Sav tekst na `--vw-text-2` (7,03 : 1).** `--tx-3` je ukinut
  (`DESIGN_SYSTEM.md` §3.3) — hijerarhiju kolona nose veličina i familija, ne
  providnost.
- Linkovi u koloni su `<ul>`/`<li>`

**ŠTA NE RADI.**
- ⚠ **Nema nijedan `href="#"`.** Ako stranica ne postoji, link se ne prikazuje.
  Prazan link je gora poruka od izostavljene stavke.
- ⚠ **Ne izostavlja nijednu pravnu stranicu.** Svih 6 mora biti linkovano:
  `/privacy`, `/terms`, `/ai-disclosure`, `/dpa`, `/security`,
  `/bezbednosni-list`. Uz njih `/status`.
- ⚠ **Ne linkuje `/pricing`** — ruta se uklanja.
- ⚠ **Ne koristi boju teksta ispod 4,5 : 1.**
- Nema ikona društvenih mreža — nijedan nalog nije naveden u kodu, a ikone bi
  bile piktogrami.
- Nema newsletter forme — jedna sabirna tačka po sajtu (komponenta 11).
- Nema izbora jezika — sajt je samo na srpskom.
- **Otvoreno pitanje ⚠:** domen u donjem redu. U kodu su dva: `vindex.rs`
  (`landing.html:1056, 1095`) i `vindex-ai.com` (`pricing.html` canonical).
  Podnožje ne sme navesti domen dok se ne odluči (`ARCHITECTURE.md` §10, p. 4).

---

## 15. OZNAKA STATUSA (`✓` / `⚠`)

**Namena.** Jedno od dva stanja tvrdnje: **radi danas** ili **ne radi / u
izradi**. Nosi celu sekciju poštenja iz `CONTENT_MAP.md` §5.

**Status: POSTOJI DELIMIČNO.** `.vx-badge` + varijante `vindex.css:9011-9027`
— ali u aplikaciji, sa `--vx-*` tokenima i drugom geometrijom. Ispravan
presedan upotrebe znakova `✓`/`⚠` postoji u `bezbednosni-list.html` (CSS
`content`) i `dpa.html:95`.

**Anatomija.**
```
✓ RADI DANAS          ⚠ U IZRADI          ⚠ NE RADI

display:        inline-flex;
gap:            var(--vw-sp-2);
font-family:    var(--vw-font-data);
font-size:      0.68rem;
letter-spacing: 0.16em;
text-transform: uppercase;
padding:        4px 8px;
border-radius:  var(--vw-radius);       /* 2px — pravougaonik, ne pilula */
border:         1px solid currentColor;
background:     transparent;
```

| Varijanta | Znak | Boja | Kontrast na `--vw-bg` |
|---|---|---|---|
| radi | `✓` | `--vw-ok` `#4ade80` | 11,84 : 1 |
| u izradi / ne radi | `⚠` | `--vw-warn` `#f0b429` | 11,07 : 1 |
| neutralno | — | `--vw-text-2` `#8b98a8` | 7,03 : 1 |

**Stanja.** Nema — oznaka je statična.

**Responzivno.** Ista na svim širinama. Ne skraćuje se i ne pretvara u sam znak
bez teksta.

**Pristupačnost.**
- **Znak je `aria-hidden="true"`; tekst nosi značenje.** `✓` bez reči „RADI
  DANAS" je nemo za čitač ekrana i nejasno za dihromate.
- Nikad **samo boja**: znak + tekst + boja, uvek sva tri
- `border: 1px solid currentColor` daje granicu kontrasta `≥3:1` (SC 1.4.11) bez
  zasebnog tokena

**ŠTA NE RADI.**
- ⚠ **Ne koristi nijedan znak osim `✓` i `⚠`.** Zabranjeni su
  ⚔️🧠⚖️🎯⚡💡📊🚨 i svaki drugi emoji. Najgori zatečeni prekršilac je
  `static/status.html:46, 62, 96` (`⚖️⚡🤖🗄️🔍⚙️`); drugi je favicon aplikacije
  `index.html:16` (`⚖` u SVG data URI). **Nijedan test to danas ne hvata**
  (`ARCHITECTURE.md` §6.5) — Faza G mora dodati proveru.
- ⚠ **Nije pilula.** `border-radius: 999px` je zabranjen.
- ⚠ **Nema tačkicu / „status dot".** Krug je zabranjen, a boja bez teksta ne
  prenosi značenje.
- Nema popunjenu pozadinu u boji — `vindex.css:9024-9027` koristi
  `rgba(74,222,128,0.10)` popune; na sajtu je pozadina prozirna, boja je u tekstu
  i ivici.
- Nema treću boju (crvenu). Sajt nema stanje greške
  (`DESIGN_SYSTEM.md` §3.5).
- Ne stoji sama — uvek je uz tvrdnju koju kvalifikuje.

---

## 16. BLOK PODATKA / KODA (monospace)

**Namena.** Doslovan prikaz putanje, rute, imena fajla, ili strukturiranog izlaza
— tamo gde bi parafraza oslabila dokaz.

**Status: NOVA.** Landing ima samo oznake u monospace-u
(`.step-num` `:335`, `.fn-card-tag` `:380`) — labele, ne blokove.

**Anatomija.**
```
┌────────────────────────────────────────────┐
│ services/risk_engine.py                    │  ← --vw-font-data, 0.875rem
│                                            │
│ Nijedan AI izlaz ne sme biti jedini izvor  │
│ rizika, statusa, roka ni spremnosti.       │
└────────────────────────────────────────────┘
background:    var(--vw-surface);
border:        1px solid var(--vw-line-2);
border-left:   1px solid var(--vw-accent);   /* jedina naglašena strana */
border-radius: var(--vw-radius);
padding:       var(--vw-sp-4);
font-family:   var(--vw-font-data);
font-size:     0.875rem;
line-height:   1.45;
overflow-x:    auto;
max-width:     80ch;
```

Inline varijanta (`<code>` u rečenici): `--vw-font-data`, `0.9em`,
`color: var(--vw-accent)`, bez pozadine i bez ivice.

**Stanja.** Nema. **Bez „kopiraj" dugmeta** — nema šta da se kopira i pokrene.

**Responzivno.** `<640` — `font-size: 0.8rem`, `padding: var(--vw-sp-3)`,
horizontalni skrol unutar bloka. **`<body>` nikad ne skroluje horizontalno**
(`DESIGN_SYSTEM.md` §10.2).

**Pristupačnost.**
- `<pre><code>` za blok, `<code>` za inline
- Ako blok skroluje horizontalno, mora biti fokusabilan (`tabindex="0"`) sa
  `role="region"` i `aria-label` — inače korisnik tastature ne može doći do
  odsečenog sadržaja
- Kontrast: `--vw-text` na `--vw-surface` = 15,86 : 1
- Inline `<code>` u akcentu: 10,59 : 1 na `--vw-surface`

**ŠTA NE RADI.**
- ⚠ **Ne prikazuje ništa što liči na ključ, token ili kredencijal.**
  `security.yml` `secret-scan` (gitleaks) je **blokirajući** i pada na sve nalik
  `eyJ…` ili API tokenu (`ARCHITECTURE.md` R4). Sajt ne prikazuje `curl` primere
  sa zaglavljima autorizacije.
- ⚠ **Ne prikazuje podatke klijenata ni stvarne predmete** — ni izmišljene koji
  liče na stvarne.
- ⚠ **Ne prikazuje izvorni kod aplikacije.** Blok nosi **ime** mehanizma i
  njegovu tvrdnju, ne implementaciju.
- Nema isticanja sintakse (syntax highlighting) — to bi tražilo dodatnu paletu.
- Nema brojeva linija.
- Nije skrolabilan vertikalno — ako ne staje u ~8 redova, ne ide na sajt.

---

## 17. OZNAKA SEKCIJE (mono labela)

**Namena.** Orijentir „gde sam" na dugoj stranici. Najčešće korišćena komponenta
i najjasniji nosilac identitetskog elementa #3.

**Status: POSTOJI** — `.section-label` `landing.html:120-129`. Ista ideja se
ponavlja u `.hero-eyebrow` (`:175-184`, `0.16em`) i `.fn-card-tag`
(`:380-390`, `0.56rem`). **Tri varijante se spajaju u jednu.**

**Anatomija.**
```
KAKO RADI
──────────
font-family:    var(--vw-font-data);
font-size:      0.68rem;
font-weight:    500;
letter-spacing: 0.16em;
text-transform: uppercase;
color:          var(--vw-accent);
margin-bottom:  var(--vw-sp-3);
```

Varijanta „prigušena" (naslov kolone u podnožju, oznaka kartice):
`color: var(--vw-text-2)` — **7,03 : 1**, nikad `--tx-3`.

**Odstupanje od zatečenog:** landing ima `0.65rem` / težina 700 / `0.18em`.
Obrazloženje u `DESIGN_SYSTEM.md` §12 B7 — 10,4px uppercase monospace težine 700
na `#010308` proizvodi optičko zamućenje.

**Stanja.** Nema — oznaka nije interaktivna.

**Responzivno.** Ista na svim širinama. **Ne smanjuje se ispod `0.68rem`.**

**Pristupačnost.**
- **Nije zamena za naslov.** Ako sekcija treba naslov, ima `<h2>`; oznaka je
  `<p>` ili `<span>` iznad njega.
- `letter-spacing` na uppercase tekstu neki čitači ekrana slovkaju — ako se to
  potvrdi, tekst ostaje malim slovima u DOM-u a `text-transform: uppercase` radi
  vizuelnu transformaciju. **Ovo je preporučeni obrazac.**
- Kontrast: `--vw-accent` 11,65 : 1 · prigušena varijanta 7,03 : 1

**ŠTA NE RADI.**
- ⚠ **Nije `<h2>` ni `<h3>`.** Oznaka koja je semantički naslov razbija strukturu
  dokumenta — čitač bi objavio „KAKO RADI" pa odmah „Kako radi", dvaput.
- ⚠ **Nema ikonu, tačku, crticu ni strelicu ispred.**
- Nema pozadinu i nema ivicu — razlikuje se familijom, veličinom i trackingom.
  Sa ivicom bi postala oznaka statusa (komponenta 15), a to je druga stvar.
- Ne koristi se dvaput u istoj sekciji.

---

## 18. ŠTA OVA MAPA NAMERNO NEMA

Komponente koje bi se očekivale na sajtu, i razlog zašto ne postoje:

| Komponenta | Zašto ne |
|---|---|
| Tabela cena / prekidač mesečno-godišnje | Nijedan plan se ne može kupiti: `STRIPE_URL = ''`. `/pricing` se uklanja. `.cen-*` blok (`landing.html:449-522`, ~75 linija) je mrtav CSS. |
| Karusel preporuka / logotipi klijenata | Nema korisnika, nema preporuka. |
| Galerija snimaka proizvoda / lightbox | Nula snimaka postoji, i ne mogu se napraviti (`ARCHITECTURE.md` §7.3-7.4). |
| Ugrađen video / demo | CSP: `frame-src` i `media-src` padaju na `default-src 'self'`. Self-hostovan video traži sintetički predmet koji ne postoji. |
| Blog / lista članaka | `CONTENT_MAP.md` §3: ne praviti sada. |
| Prekidač svetle/tamne teme | Sajt ima jednu podlogu (`DESIGN_SYSTEM.md` §12 B2). |
| Traka kolačića | Sajt nema analitiku ni kolačiće za praćenje. Traka bez razloga je šum. |
| Chat / widget podrške | Traži eksterni skript i eksterni `connect-src`. |
| Brojači („1.200 advokata") | Nema korisnika. |
| Prekidač jezika | Sajt je samo na srpskom. |
| Pretraga po sajtu | 7-9 stranica. |
| Vrteška / spinner | Krug (§6.1) + beskonačna animacija (§9.3). Loading stanje je tekstualno. |
| „Nazad na vrh" dugme | Plutajuće dugme bez sadržaja; `Home` taster i skrol rade isto. |

---

## 19. VEZA SA FAZOM G — šta se automatski proverava

Lista proverljivih pravila iz ove mape, za regresione testove:

| # | Pravilo | Izvor |
|---|---|---|
| 1 | Nula `href="#"` u novom sajtu | komp. 10, 14 |
| 2 | Svih 6 pravnih stranica linkovano iz podnožja | komp. 14 |
| 3 | Nula emoji van `✓` i `⚠` | komp. 15 |
| 4 | Nula `box-shadow` deklaracija | `DESIGN_SYSTEM.md` §7 |
| 5 | Nula `linear-gradient` / `radial-gradient` kao `background` | §7 |
| 6 | Nula `border-radius` > 2px | §6.1 |
| 7 | Postoji `@media (prefers-reduced-motion: reduce)` blok | §9.4 |
| 8 | Postoji `:focus-visible` pravilo; nema `outline: none` bez zamene | §8.2 |
| 9 | Svaki `<input>` ima `<label for>` | komp. 11 |
| 10 | Nula `<canvas>` i nula `requestAnimationFrame` | §9.3 |
| 11 | Nula referenci na `assets/lady_justice.jpg` | §12 A8 |
| 12 | Nula brojeva o veličini korpusa zakona | komp. 4 |
| 13 | Nijedna kartica dokaza bez podnožja izvora | komp. 8 |
| 14 | `CACHE_NAME` (`static/sw.js:4`) porastao u istom commitu | `ARCHITECTURE.md` R1 |

---

*Kraj dokumenta. Nijedan produkcioni fajl nije menjan.*
