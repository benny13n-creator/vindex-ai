# VINDEX AI — VISUAL BLUEPRINT

Izvedeno iz postojećeg identiteta u `static/`, ne izmišljeno.

## ZATEČENO STANJE
`Cormorant Garamond` (serif, editorijalan) · `#010308` podloga · `#00d4ff` akcenat ·
`#e6edf3` tekst · `#4ade80` / `#f56565` statusi · oštri uglovi · bez gradijenata.

**Serif je prednost, ne slučajnost:** deluje institucionalno, što odgovara i advokatu i banci,
a udaljava od izgleda generičkog AI startapa.

## SISTEM

**Raspored:** jedna kolona, maksimalna širina sadržaja **~1100px**, teksta **~68 znakova**.
Vertikalni ritam u koracima od 8px; razmak između sekcija ≥ 96px (desktop) / 64px (mobilni).

**Tipografija**
| Uloga | Font | Veličina (desktop → mobilni) |
|---|---|---|
| H1 | Cormorant Garamond 600 | 56 → 34 |
| H2 | Cormorant Garamond 600 | 34 → 26 |
| Telo | sistemski sans | 18 → 17 |
| Sitno / napomena | sistemski sans | 15 |
Prored tela **1.65**. Najviše dve težine po fontu.

**Boja** — akcenat `#00d4ff` **samo** za: jedan CTA, oznake porekla, linije dijagrama.
Nikad kao pozadina velikog bloka. **Proveriti kontrast na `#010308` pre upotrebe za tekst.**

**Kartice** — bez senki i bez zaobljenja; razdvajanje tankom linijom `#1c2530` ili blagom
promenom podloge. Levi akcentni rub od 2px samo na sekciji poverenja.

**Dijagrami** — SVG, ručno pisan, bez biblioteke. Dva su potrebna:
1. tok predmeta (dokument → kontekst → AI → trag)
2. polje konteksta sa vidljivom oznakom `izvor: tuzba.pdf`

**Drugi dijagram je najvažniji vizuel na sajtu** — objašnjava diferencijator bez teksta.

**Pokret** — prelazi ≤200ms, samo `opacity` i `transform`. Bez parallaxa, bez brojača, bez
animacija pri skrolovanju. `prefers-reduced-motion` gasi sve.

**Prikazi proizvoda** — **SCREENSHOT REQUIRED**. Do tada dijagrami. Ne koristiti mockup ekrane
koji prikazuju nepostojeći interfejs.

## RESPONZIVNO
Tačke preloma 640 / 1024. Mobilni: jedna kolona, CTA pun po širini, navigacija bez hamburgera
(tri stavke staju). Dodirne mete ≥44px.

## IZBEGAVATI
Stock fotografije advokata · sjaj i gradijente · mozgove, kola, robote · animirane brojače ·
karusele · iskačuće prozore · tamne obrasce · više od jednog CTA po ekranu.
