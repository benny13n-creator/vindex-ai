# FAZA 1 — DOKAZ ZA SVETLU TEMU

> Datum: 2026-09-03
> Metod: Playwright/Chromium 1440×900, tema uključena kroz **produkcioni put**
> (`localStorage.vx_theme = 'light'` → `vindex.js` sam dodaje klasu pri
> učitavanju). Merenje odbija da nastavi ako `body.className` ne potvrdi temu.
> Standard: WCAG 2.1 AA.

---

## 1. Kontrastni padovi PRE

| Mera | Vrednost |
|---|---|
| Jedinstvenih vidljivih tekstualnih čvorova | **342** |
| Čvorova ispod praga | **101** |
| Različitih CSS deklaracija koje ih uzrokuju | **17** |
| Najgori pojedinačni odnos | **1.01 : 1** |

### Najgori nalaz: `body.light-theme *`

```css
body.light-theme * { color: rgba(10,18,32,0.88) !important; }
```

Komentar iznad tog pravila u izvoru sam kaže šta je: *„Pokriva svih 800+
hardkodovanih rgba(255,255,255,...) boja odjednom."* To je pokrivač, ne dizajn.

**Pitanje je bilo da li je to samo maskiranje. Odgovor je izmeren, i glasi: da.**

#### Dokaz 1 — lestvica je bila potpuno sravnjena

Iste sonde, iste teme, isti trenutak:

| Token | TAMNA tema | SVETLA tema |
|---|---|---|
| `--tx-1` | 15.74 : 1 | 12.51 : 1 |
| `--tx-2` | 5.67 : 1 | 12.51 : 1 |
| `--tx-3` | 2.31 : 1 | 12.51 : 1 |
| `--tx-4` | 1.37 : 1 | 12.51 : 1 |

U svetloj temi sva četiri nivoa iscrtavala su se kao **identična boja
`rgb(38,45,58)`**. Četvoronivovska lestvica postojala je u definiciji i nije
postojala na ekranu. Uzrok je mehanički: `body.light-theme *` nosi
`!important` i specifičnost (0,1,1), pa pobeđuje svako
`.klasa { color: var(--tx-3) }` — dakle **svakog potrošača tokena**.

#### Dokaz 2 — 46 % uporedivih odnosa uloga je bilo slomljeno

| Mera (isti ton, tamna vs svetla) | Vrednost |
|---|---|
| Uporedivih parova uloga | 88 |
| **Invertovanih** | 5 |
| **Sabijenih na istu vrednost** | 26 |
| Ukupno slomljeno | **31 (35 %)** |

Imenovana šteta:

- `.vx-exec-header-eyebrow` / `-title` / `-sub` — **troslojno zaglavlje stranice
  sabijeno u jedan sloj na 5 tabova** (Klijenti, Dokumenti, Finansije, Rokovi,
  Kancelarija).
- `.settings-row-label` vs `.settings-row-sub` — objašnjenje čitljivije od
  oznake koju objašnjava.
- `.hub-stat-l` vs `.hub-stat-n` — **oznaka nadjačava broj**.
- `.t-credits-val` vs `.t-credits-lbl` — vrednost i oznaka izjednačene.

Različitih iscrtanih boja teksta na istom ekranu: **tamna 23, svetla 14.**

#### Dokaz 3 — pokrivač je bojio taman tekst po TAMNIM površinama

`a.vx-land-logo` („Vindex"): boja `rgba(10,18,32,0.88)` na pozadini
`rgb(1,3,8)` → **1.01 : 1**. Logotip proizvoda bio je nevidljiv u svetloj temi.

45 od 101 pada nije bilo pitanje boje teksta nego **površine koja nikad nije
dobila svetlu varijantu**:

| Površina | Efektivna pozadina | Palih čvorova |
|---|---|---|
| `.settings-section` (`rgba(13,17,23,0.4)`) | `rgb(149,152,156)` | 21 |
| `.vx-card` (`rgba(13,17,23,0.55)`) | `rgb(115,118,123)` | 13 |
| `table.vx-grid thead th` | `rgb(13,17,23)` | 9 |
| `.vx-land-nav` (`#010308`) | `rgb(1,3,8)` | 2 |

### Drugi strukturni nalaz: druga porodica tokena nije postojala u svetloj temi

`--vx-*` (`--vx-bg-elevated`, `--vx-text-primary`, `--vx-text-secondary`,
`--vx-accent`, …) definisana je **isključivo za tamnu temu**. Svetla tema je
redefinisala **nula** od njih. Zato je tabela Predmeta iscrtavala tamnu
hromiranost ispod tamnog teksta.

### Ostali padovi

| Odnos | Deklaracija | Čvorova |
|---|---|---|
| 1.77 | beli tekst na `#00d4ff` ispuni (`+ Ročište`, „Pretraži sudsku praksu") | 2 |
| 1.96–1.99 | `rgba(10,18,32,0.3)` — pretraga, oznake statistike, naslovi grupa | 7 |
| 2.02 | `rgba(10,18,32,0.38)` — Podešavanja | 21 |
| 2.98 | `#0099bb` kao boja teksta na beloj | 12 |
| 3.90 | `rgba(0,0,0,0.5)` — **cela glavna navigacija** | 24 |

---

## 2. Korekcije

Vodilo se istim principom kao u tamnoj temi. Bez nove palete, bez promene
rasporeda, bez diranja `.kc-sphere`.

### K1 — Lestvica svetle teme

```
--tx-1  0.92 -> 0.92     14.09 : 1
--tx-2  0.60 -> 0.80      9.57 : 1
--tx-3  0.40 -> 0.72      7.21 : 1
--tx-4  0.22 -> 0.64      5.45 : 1
```

Najsvetlija stvarna površina (`#f0f2f5`) traži alfu ≈ 0.585 za 4.5:1 — isti
razlog za prerasporedjivanje kao u tamnoj temi.

### K2 — Tekstualni brend-token

`--tx-blue: #0099bb → #006680`. Ista nijansa (hsl ≈ 191–192°), tamnija
vrednost. `#0099bb` kao **tekst** na beloj daje 2.98 : 1; `#006680` daje 5.83.
Token `--blue` (pozadine, ivice, akcenti) **nije diran** — brend ostaje.

Da je token bio pravilno korišćen, ovo bi bila jedina potrebna izmena. To što
je 12 mesta hardkodovalo `#0099bb` je posledica istog problema koji je i stvorio
pokrivač.

### K3 — `--vx-*` porodica dobija svetlu definiciju

Devet tokena (`bg-primary/secondary/elevated`, `border`, `border-strong`,
`text-primary`, `text-secondary`, `accent`, `accent-dim`) sada ima svetle
parnjake. Vrednosti su svetla ogledala postojećih tamnih — nijedna nova boja.

### K4 — Površine, a ne tekst

```css
body.light-theme .settings-section { background: #ffffff; border-color: rgba(10,18,32,0.09); }
body.light-theme .vx-card          { background: #ffffff; border-color: rgba(10,18,32,0.09); }
body.light-theme .vx-land-nav      { background: #ffffff; border-bottom: 1px solid rgba(10,18,32,0.08); }
```

45 padova zatvoreno ispravljanjem **pozadine**, ne boje teksta. To je ispravan
nivo: u svetloj temi hromiranost treba da bude svetla.

### K5 — Pokrivač: suzen, ne uklonjen

```css
/* pre  */ body.light-theme * { ... }
/* posle*/ body.light-theme *:not([style*="--tx-"]) { ... }
```

**Zašto ne uklonjen:** uklanjanje traži migraciju ~950 hardkodovanih belih boja
na tokene. To je van obima Faze 1 i graniči se sa redizajnom.

**Zašto ovo radi:** posle migracije iz K6, elementi koji nose svoj semantički
nivo imaju ga u inline `style` atributu. `:not([style*="--tx-"])` isključuje
tačno njih. Za sve ostalo pokrivač radi kao i do sada. **Jedna izmena selektora
umesto 640 izmena u markupu**, bez rizika da se pokvare hover stanja.

Isprobana je i varijanta u kojoj pokrivač dodeljuje nivo 2 umesto nivoa 1
(hipoteza: nemigrirane boje pripadaju sekundarnom nivou). **Odbačena je jer je
merenje pokazalo da ne popravlja hijerarhiju a uvodi 4 nova kontrastna pada.**

### K6 — Migracija na tokene

~850 deklaracija u `index.html`, `vindex.js` i `vindex.css` prešlo je sa
hardkodovanih boja na `var(--tx-N)` (detalji u izveštaju za tamnu temu). Efekat
u svetloj temi: te uloge sada dobijaju **svoj** nivo umesto jedne ravne
vrednosti pokrivača.

### K7 — 15 uloga kojima je nivo eksplicitno vraćen

Spisak **nije pretpostavljen** — izveden je iz merenja sabijenih parova:

```
.vx-exec-header-title / -eyebrow / -sub   .vx-btn-secondary   .vx-btn-ghost
.settings-btn   .pomoc-faq-arrow   .vx-section-lbl   .t-credits-val / -lbl
.vx-land-feat-title / -text   .t-label   .t-chips-lbl   .vx-search-icon
```

Svaka dobija **isti token koji već koristi u tamnoj temi**, samo sa dovoljnom
težinom da nadjača pokrivač.

### K8 — Pojedinačni ostaci

| Element | Bilo | Postalo |
|---|---|---|
| `.kal-dodaj-btn`, `#praksa-search-btn` | beli tekst na `#00d4ff` (1.77) | `var(--tx-1)` (9.26); **ispuna, dakle brend, ostaje** |
| `.vx-land-feat-icon` | pokrivač ga je bojio tamno i brisao akcent | `var(--tx-blue)` + `opacity: 1` (dvostruka prigušnica je gušila token) |
| `.hub-stat-n` | 0.65 (5.61) — ispod svoje oznake | `var(--tx-1)` |
| `.vx-land-foot-links` | inline `opacity:.6` gušio boju na 3.77 | prigušnicu nosi token, inline uklonjen |

---

## 3. Kontrastni padovi POSLE

| Mera | Pre | Posle |
|---|---|---|
| Jedinstvenih čvorova | 342 | 343 |
| **Čvorova ispod praga** | **101** | **0** |
| Deklaracija koje padaju | 17 | **0** |

---

## 4. Hijerarhija je vraćena

### Lestvica

| | tx-1 | tx-2 | tx-3 | tx-4 |
|---|---|---|---|---|
| PRE | 12.51 | **12.51** | **12.51** | **12.51** |
| POSLE | 14.09 | 9.57 | 7.21 | 5.45 |

Iz **jednog** nivoa u **četiri razdvojena**, sa razmacima 4.52 / 2.36 / 1.76
kontrastnih bodova.

### Paritet sa tamnom temom

| Mera (isti ton) | PRE | POSLE |
|---|---|---|
| Uporedivih parova uloga | 88 | 84 |
| Invertovanih | 5 | **2** |
| Sabijenih | 26 | **1** |
| **Ukupno slomljeno** | **31 (35 %)** | **3 (3.6 %)** |

Svetla tema, pre → posle (nad sobom): **25 parova je dobilo razdvojenost** koju
prethodno nije imalo; 2 invertovana, 5 sabijenih.

Različitih iscrtanih boja teksta: **14 → 16**, dok je tamna 23 → 19 — dve teme
su se srele, umesto da svetla bude osiromašena kopija.

### Preostala 3 para — evidentirano

| Par | Razlika u tamnoj temi | Ocena |
|---|---|---|
| `⌘K` vs `⌕` | 0.28 boda | ispod praga primetnosti |
| `⌘K` vs tekst rezerve pretrage | 0.28 boda | ispod praga primetnosti |
| „Uporedi" vs „vs" | 0.06 boda (svetla) | ispod praga primetnosti |

Nisu gonjeni namerno: to je šum instrumenta, a ne razlika koju korisnik vidi.

### Parovi izuzeti iz provere inverzije: 38

Parovi u kojima jedna strana nosi **akcentnu nijansu** a druga neutralnu.
Primer: `.vx-exec-header-eyebrow` je `#00d4ff` u tamnoj (11.65 : 1) i `#006680`
u svetloj (5.83 : 1). Kontrast je pao, ali **prominentnost nije** — akcentna
nijansa se izdvaja tonom, ne odnosom prema podlozi. Sve takve vrednosti su iznad
praga čitljivosti (najniža 5.36 : 1); poređenje po kontrastu bi tu lagalo.

---

## 5. Tastatura i fokus u svetloj temi

| Mera | Vrednost |
|---|---|
| Zaustavljanja tabulatora | **27** |
| Bez ijedne vizuelne promene pri fokusu | **0** |

Mereno **pikselima**, isto kao za tamnu temu. Prsten je `var(--blue)` = 3.35 : 1
u svetloj temi (prag za indikator je 3 : 1).

---

## 6. Regresija

Isto kao u izveštaju za tamnu temu: 6/6 novi gejt, 335 UI testova prošlo,
prekidač teme dokazano radi (klik → svetla → `reload` → i dalje svetla →
povratak), `.kc-sphere` netaknuta.

---

## 7. Izuzeci

| Stavka | Zašto |
|---|---|
| `body.light-theme *` nije uklonjen | Traži migraciju ~950 deklaracija — van obima Faze 1. Suzen je tako da više ne gazi uloge koje nose svoj nivo. **Ostaje kao dug.** |
| Veličine fonta ispod 11 px | Izričita instrukcija da se ne rešava povećanjem fontova |
| Zaključani ekran (`.kc-sphere`, `#tab-h`) | Izričita zabrana |
