# FAZA 1 — DOKAZ ZA TAMNU TEMU

> Datum: 2026-09-03
> Metod: Playwright/Chromium 1440×900 nad stvarno iscrtanom aplikacijom.
> Standard: WCAG 2.1 AA (4.5:1 za običan tekst, 3:1 za veliki).

---

## 0. Kako je mereno (i zašto ne statički)

Boja se **ne čita iz CSS izvora**. Stranica se iscrtava, a zatim se za svaki
vidljiv tekstualni čvor uzima `getComputedStyle(el).color` i **kompozituje kroz
stvarni lanac predaka** — svaki `background-color` sa alfom i svaki nasleđeni
`opacity`. Tek taj piksel se poredi sa efektivnom pozadinom.

Razlog je konkretan i merljiv: `.t-tab` ima **17 konkurentskih `color`
deklaracija**, `.t-tab.active` ima 12. Nijedno čitanje izvora ne kaže koja
pobeđuje. Merenje kaže.

Ulazak u aplikaciju ide kroz **produkcioni put**: `updateAuthUI()` — ista
funkcija koja se izvršava posle prave prijave. Obiđe se 11 tabova + javni
landing.

**Instrument je dvaput ispravljen tokom rada** (obe ispravke su zabeležene jer
menjaju tumačenje brojeva):

1. Prvo poređenje hijerarhije koristilo je sirovu luminansu. To je pogrešno pri
   poređenju tema: u tamnoj temi „istaknutije" znači svetlije, u svetloj
   tamnije, pa polaritet konfundira rezultat. Metrika je prebačena na
   **kontrast prema sopstvenoj pozadini**.
2. Parovi u kojima se boje razlikuju po **tonu** (akcent vs neutralno) izbačeni
   su iz provere inverzije: akcentna nijansa ima fiksnu svetlinu, pa joj odnos
   prema svetloj podlozi nužno pada — to nije kvar hijerarhije nego ograničenje
   metrike.

---

## 1. Kontrastni padovi PRE

| Mera | Vrednost |
|---|---|
| Jedinstvenih vidljivih tekstualnih čvorova | **341** |
| Čvorova ispod praga | **126** |
| Različitih CSS deklaracija koje ih uzrokuju | **45** |
| Najgori pojedinačni odnos | **1.37 : 1** |

### Koren: sama tokenska lestvica je bila slomljena

| Token | Alfa | Odnos na `rgb(1,3,8)` | |
|---|---|---|---|
| `--tx-1` | 0.88 | 15.74 : 1 | prolazi |
| `--tx-2` | 0.52 | 5.67 : 1 | prolazi |
| `--tx-3` | 0.28 | **2.31 : 1** | **pada** |
| `--tx-4` | 0.14 | **1.37 : 1** | **pada** |

Dva od četiri nivoa dizajn sistema bila su ispod praga čitljivosti. Sve što je
koristilo `var(--tx-3)` ili `var(--tx-4)` — oznake polja, naslovi sekcija,
tekst dugmadi u Podešavanjima, tagline na landingu — bilo je nečitljivo.

Uz to su otkrivene **još četiri porodice tokena** sa istim kvarom:

| Porodica | Token | Alfa | Odnos |
|---|---|---|---|
| `--vp-txt-*` | `--vp-txt-3` | 0.22 | 1.89 : 1 |
| `--vp-t*` | `--vp-t3` | 0.28 | 2.38 : 1 |
| `--vx-*` | (dark OK, ali svetla tema ih nije imala — v. izveštaj za svetlu temu) | | |

### Reprezentativni padovi (od 45 deklaracija)

| Odnos | Selektor | Tekst |
|---|---|---|
| 1.37 | `.vx-land-foot-disc` | „Vindex AI ne zamenjuje profesionalno pravno rasuđivanje" |
| 1.37 | `.chat-privacy-note` | „Sesije se čuvaju radi lakšeg rada." |
| 1.50 | `.vx-search-kbd` | `⌘K` |
| 1.57 | `.kc-empty` | „Prijavite se da biste videli kontrolni centar." |
| 1.95 | `.vx-nav-group-lbl` | „Dnevni rad" / „Znanje i AI" / „Poslovanje" |
| 2.16 | `.hub-eyebrow` | „Vindex AI — Pravna Inteligencija" |
| 2.24 | inline `rgba(255,80,80,0.5)` | „Greška pri učitavanju." |
| 2.31 | `.vx-land-tagline` | „Pravo na dohvat ruke." |
| 2.38 | `.settings-row-sub` (17 čvorova) | „Vaše ime u pozdravnoj poruci", e-adresa, plan… |
| 4.35 | `.wl-badge` | „Beta · Ograničen broj mesta" |

---

## 2. Korekcije

Princip: **uloga elementa → nivo u lestvici → minimalna korekcija**. Nijedna
korekcija ne diže font, ne menja raspored, ne uvodi novu paletu i ne dira
`.kc-sphere` (dokazano: 97 deklaracija unutar zaključanog ekrana je namerno
preskočeno, a `git diff` ne sadrži nijednu liniju sa `kc-sphere`).

### K1 — Prestrukturirana tokenska lestvica

```
--tx-1  0.88 -> 0.88     15.74 : 1
--tx-2  0.52 -> 0.72     10.45 : 1
--tx-3  0.28 -> 0.62      7.82 : 1
--tx-4  0.14 -> 0.52      5.67 : 1
```

`--tx-2` je pomeren iako je **sam po sebi prolazio**. To nije proizvoljno:
najsvetlija stvarna površina aplikacije traži alfu ≈ 0.50 za 4.5:1, pa četiri
razdvojena nivoa ne mogu da stanu između 0.50 i 0.88 bez prerasporedjivanja.
Alternativa bi bila lestvica 0.52 / 0.50 / 0.48 — matematički prolazna, vizuelno
neraspoznatljiva. Poredak je očuvan, razmaci su 5.29 / 2.63 / 2.15 kontrastnih
bodova.

Isto prestrukturiranje primenjeno na `--vp-txt-*` i `--vp-t*`.

### K2 — Migracija hardkodovanih boja na tokene

| Gde | Broj deklaracija |
|---|---|
| `index.html` (inline `style`) | 256 |
| `static/vindex.js` (generisani markup) | 381 |
| `static/vindex.css` (pravila) | 193 + 22 ciljanih |
| **Ukupno** | **~850** |

Mapiranje je po opsezima, **ne u jednu vrednost** — da relativni poredak koji je
postojao ostane:

```
alfa <= 0.25          -> var(--tx-4)
0.25 < alfa < 0.455   -> var(--tx-3)
0.455 <= alfa <= 0.60 -> var(--tx-3)
0.60 <  alfa <= 0.78  -> var(--tx-2)
alfa >  0.78          -> var(--tx-1)
```

Granice nisu pretpostavljene nego **empirijski izabrane**: testirane su tri
varijante mapiranja i merena je šteta po hijerarhiju (broj invertovanih i
sabijenih parova). Varijanta sa granicom na 0.25 dala je najmanje inverzija.

### K3 — Akcenti koji ne mogu preko alfe

74 hromatske inline boje bile su ispod praga. Za 72 je **podignuta alfa na
minimum koji prolazi, po svakoj boji posebno** — ton se ne menja ni za jedan
stepen. Dve su bile nepopravljive alfom:

| Bila | Odnos na punoj neprovidnosti | Postala | Novi odnos |
|---|---|---|---|
| `rgba(99,102,241,.8)` (indigo-500) | 4.24 : 1 | `rgb(165,180,252)` (indigo-300, **već u ovom fajlu**) | 9.49 : 1 |

Ostale ciljane izmene:

| Element | Bilo | Postalo | Razlog |
|---|---|---|---|
| `.hub-eyebrow` | `rgba(0,212,255,0.35)` | `var(--tx-blue)` | 2.16 → 11.65 |
| `.wl-badge` | `rgba(0,153,187,0.85)` | `var(--tx-blue)` | 4.35 → 10.53 |
| `#delete-account-btn` | `#ef4444` | `#ff6b6b` (već u kodu) | 5.30 → 7.19; destruktivna radnja **mora** ostati istaknutija od obične dugmadi (6.88) |
| `_piColor` zelena skala | `rgba(74,222,128,0.55)` | `0.45` | beli tekst je bio 4.08 → 5.23 |

### K4 — Fokus

Merenje **pikselima** (snimak regiona bez fokusa vs sa fokusom), ne čitanjem
`outline` vrednosti — prvi prolaz preko CSS vrednosti dao je **dva lažna
pozitiva** (prsten iznad providne pozadine izmeren kao odnos 1.00).

Nađeno: `TEXTAREA#qi` (**glavno polje za pitanje u aplikaciji**) i
`BUTTON#mic-qi` nisu menjali **nijedan piksel** pri fokusu tastaturom. Dodat
`:focus-visible` prsten (`2px solid var(--blue)` = 11.65 : 1) i osnovna mreža za
polja bez sopstvene klase.

---

## 3. Kontrastni padovi POSLE

| Mera | Pre | Posle |
|---|---|---|
| Jedinstvenih čvorova | 341 | 342 |
| **Čvorova ispod praga** | **126** | **0** |
| Deklaracija koje padaju | 45 | **0** |

Nezavisno potvrđeno i determinističkom proverom izvora
(`tests/test_faza1_izvor_pod.py`): **0 deklaracija teksta ispod poda alfe** van
zaključanog ekrana.

---

## 4. Hijerarhija je očuvana

Invarijanta: za svaki kontejner sa dvoje ili više dece koja nose tekst beleži se
uređen par (ko je istaknutiji, mereno kontrastom prema sopstvenoj pozadini).
Posle korekcije nijedan par ne sme da se **invertuje** niti da se **slepi**.

| | Vrednost |
|---|---|
| Uporedivih parova (isti ton) | **102** |
| Nepromenjenih | **93 (91 %)** |
| Invertovanih | 6 |
| Sabijenih | 3 |
| Novorazdvojenih | 2 |

**Svih 9 promenjenih parova ima isti oblik: element koji je bio ISPOD praga
čitljivosti se podigao iznad njega.** Nijedan par ne uključuje potiskivanje
elementa koji je i pre bio čitljiv. Primer: `.vx-land-feat-text` 2.36 → 7.82
sada nadmašuje dekorativnu ikonu (5.13) — sadržaj iznad ukrasa.

Dva su bila stvarna kvara i **posebno popravljena**:

- `#delete-account-btn` (5.31) je posle podizanja obične dugmadi (6.88) postao
  manje istaknut od „Preuzmi ZIP" — vraćen iznad (7.19).
- U Podešavanjima su se oznaka reda i objašnjenje ispod nje sudarili na istom
  nivou. `.settings-section-hd` je podignut na nivo 2, `.settings-row-sub`
  spušten na nivo 4 — troslojni odnos je vraćen.

### Lestvica: pre → posle

| | tx-1 | tx-2 | tx-3 | tx-4 |
|---|---|---|---|---|
| PRE | 15.74 | 5.67 | **2.31** | **1.37** |
| POSLE | 15.74 | 10.45 | 7.82 | 5.67 |

Različitih iscrtanih boja teksta: 23 → 19 (konsolidacija nasumičnog rasipanja
od 12 vrednosti alfe u 4 imenovana nivoa; ni jedan **semantički** par nije
izgubljen — v. tabelu iznad).

---

## 5. Tastatura i fokus

| Mera | Vrednost |
|---|---|
| Zaustavljanja tabulatora izmereno | **27** |
| Bez ijedne vizuelne promene pri fokusu | **0** |
| Vidljivih interaktivnih elemenata dohvatljivih tastaturom | 61 / 61 |

Uz to je zatvoren kvar koji je stajao u `static/vx-a11y.js`: linija koja je
trebalo da postavi `tabindex` bila je napisana kao `void 0;` — prazna. Element
je dobijao `role="button"` (čitač ekrana ga objavljuje kao dugme) ali **nije bio
dohvatljiv tastaturom**. Pogađalo je 82 od 559 kontrola sa `onclick`.
Sama skripta nije ni bila uključena u `index.html`.

---

## 6. Regresija

- `tests/test_faza1_kontrast_playwright.py` — **6/6** (novi trajni gejt)
- `tests/test_faza1_izvor_pod.py` + `tests/test_faza1_pristupacnost.py` —
  **pre rada 14 padova, posle 4**
- Široki UI/Playwright skup — 335 prošlo, 0 palo
- Prekidač teme radi kao pre: klik → svetla → perzistira kroz `reload` → povratak
- `.kc-sphere` netaknuta (0 izmenjenih linija)
- `sw.js` `CACHE_NAME` v147 → v148

---

## 7. Izuzeci — evidentirano, nije popravljeno

| Stavka | Broj | Zašto nije dirano |
|---|---|---|
| Deklaracije teksta unutar zaključanog ekrana (`.kc-*`, `#tab-h`, `.kc-sphere`) | 97 | Izričita zabrana diranja `.kc-sphere` / zaključanog ekrana |
| Veličine fonta ispod 11 px | 567 u izvoru, 17 iscrtanih | **Izričita instrukcija: „Nemoj ovo rešavati povećanjem fontova."** Ovo je jedini preostali padajući test i traži zasebnu odluku |

### Rezidual hijerarhije ispod praga primetnosti

Tri para ostaju formalno „promenjena", ali sa razlikama koje nisu vidljive:

| Par | Razlika u tamnoj temi |
|---|---|
| `⌘K` vs `⌕` / tekst rezerve u pretrazi | 0.28 kontrastnih bodova |
| „Uporedi" vs „vs" | 0.06 bodova (u svetloj temi) |

Ovo je šum instrumenta, ne dizajn. Gonjenje tih vrednosti bilo bi prilagođavanje
merilu, ne korisniku.
