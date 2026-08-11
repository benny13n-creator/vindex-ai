# VINDEX AI — VIZUELNI STORYBOARD

Sekcija po sekcija: cilj, poruka, vizuel, interakcija, dokaz, responzivno.

Sinteza Phase B dokumenata. Tekst tvrdnji dolazi iz `CONTENT_TRUTH_MAP.md`,
tokeni iz `DESIGN_SYSTEM.md`, komponente iz `COMPONENT_MAP.md`, struktura iz
`WEBSITE_ARCHITECTURE.md`.

---

# PRAVILA KOJA VAŽE ZA SVAKU SEKCIJU

| | |
|---|---|
| **Podloga** | `#010308` na celom sajtu. Nijedna svetla sekcija *(odstupanje B2)* |
| **Razdvajanje** | linija `1px` + razmak. **Nula senki, nula gradijenata** |
| **Radius** | `2px`, jedna vrednost. Bez pilula i krugova |
| **Ikone** | nema ih. Samo `✓` i `⚠` (`⚠` je amber `#f0b429`, ne crvena) |
| **Brojevi i oznake** | uvek `--vw-font-data` (JetBrains Mono) |
| **Pokret** | ≤200ms, samo `opacity`/`transform`, `prefers-reduced-motion` gasi sve |
| **Snimci proizvoda** | **nema ih**. Svaki vizuel je SVG dijagram i tako je označen |
| **Akcenat** | najviše **tri** akcentovana elementa po ekranu |

---

# POČETNA

## 1 · HERO

**Cilj** — posetilac za 5 sekundi zna u koju kategoriju proizvod spada.

**Poruka**
> # Odgovor sa navedenim propisom. Ili nikakav odgovor.
> Kada postavite pravno pitanje, Vindex vam kaže na kojim propisima počiva
> odgovor — i ćuti kada pouzdan izvor ne postoji.

**Vizuel** — SVG dijagram toka, **ne** sfera iz zatečenog landinga *(odstupanje
B4: sfera krši četiri pravila odjednom — krug, gradijent, glow, beskonačna
animacija; ne može se popraviti, samo zameniti)*.

```
    PITANJE
       │
       ├─ pouzdan izvor  ──▶  ODGOVOR  +  ZR čl. 179
       │                                 ZOO čl. 262
       │
       └─ nema izvora    ──▶  ✓ nema odgovora
                                model nije pozvan
```

Desna grana je **poenta dijagrama**, ne fusnota. Crta se istom debljinom linije
kao leva.

**Interakcija** — nema. Dijagram je statičan SVG; ulazna animacija je jedan
`opacity` prelaz od 160ms.

**Dokaz** — `main.py:3354-3362` (odbijanje pre poziva modelu) ·
`static/vindex.js:924-955` `_vxRenderIzvori` (prikaz propisa i članova).

**Responzivno** — desktop: naslov levo, dijagram desno. Mobilni: dijagram ispod
naslova, grane se slažu vertikalno, tekst grana ostaje monospace na 13px. CTA pun
po širini.

---

## 2 · PROBLEM

**Cilj** — prepoznavanje. Advokat treba da pomisli „ovo je moj utorak".

**Poruka** — tri rečenice, bez ijedne statistike:
- Kontekst predmeta živi u glavi, ne u sistemu.
- Rokovi su u tekstu dokumenta, ne u kalendaru.
- Provera tuđeg rada znači ponovno čitanje svega.

**Vizuel** — **nema ga.** Sekcija je namerno gola: tri rečenice, mnogo praznog
prostora, tipografija nosi sve. Slika bi je oslabila.

**Dokaz** — `OPISNO`. Ovo su tvrdnje o poslu advokata, ne o proizvodu, i tako su
označene u `CONTENT_TRUTH_MAP.md`.

**Responzivno** — jedna kolona na svim širinama. Nikad tri kartice.

---

## 3 · KAKO RADI

**Cilj** — učiniti mehanizam opipljivim bez tehničkog rečnika.

**Poruka** — četiri koraka:
`unos dokumenata` → `uređen predmet` → `AI nad uređenim prikazom` → `navedeni izvor`

**Vizuel** — horizontalni SVG tok. Svaki korak je pravougaonik `2px` radiusa sa
linijom `1px`; strelice su linije, ne trouglovi sa gradijentom.

Ispod svakog koraka jedna rečenica u `--vw-font-text`, a naziv koraka u
`--vw-font-data` uppercase sa tracking-om.

**Interakcija** — hover na korak povećava kontrast njegove ivice. Bez modala,
bez tooltip-a, bez skrol-animacija.

**Dokaz** — `routers/intake.py` · `shared/case_context.py` ·
`shared/ai_provenance.py`.

**Responzivno** — desktop horizontalno. **Tablet i mobilni: vertikalno**, strelice
rotiraju za 90°. Ne horizontalni skrol — korisnik mora videti sva četiri koraka
odjednom, to je poenta.

---

## 4 · ZAŠTO VERUJETI *(iznad nabrajanja funkcija — namerno)*

**Cilj** — ukloniti blokator pre nego što se pojavi.

**Poruka** — tri dokaza, svaki kao kartica:

| # | Tvrdnja | Mehanizam |
|---|---|---|
| 1 | **Brojeve računa program. AI ih samo objašnjava.** | nijedan AI izlaz nije jedini izvor rizika, statusa ni roka |
| 2 | **Nacrt ne sme da izmisli član propisa.** | izmišljen broj se zamenjuje oznakom `[proveriti relevantan član]` — nikad drugim brojem |
| 3 | **Evidencija se ne može izmeniti ni obrisati.** | dokazano izvršavanjem nad pravom bazom, ne deklaracijom |

**Vizuel** — tri kartice po `.fn-grid` obrascu iz zatečenog landinga (`gap` +
pozadina = linije). **Bez ikona.** Svaka kartica nosi u podnožju putanju do
dokaza u `--vw-font-data`, sitno.

**Interakcija** — nema. Kartice nisu klikabilne; nemaju gde da vode.

**Dokaz** — `services/risk_engine.py` ·
`test_phoenix_mission_010_drafting_rag_grounding.py` ·
`test_rc_migration_gate.py:399/414/453`.

**Responzivno** — 3 kolone → 1 kolona ispod 900px. Redosled se ne menja.

---

## 5 · ŠTA RADI DANAS

**Cilj** — obim, bez liste od 237 stavki.

**Poruka** — šest grupa, svaka jedan naslov + dve rečenice. Bez nabrajanja alata.

**Vizuel** — dvokolonska tekstualna mreža razdvojena linijama. Nema kartica,
nema ikona, nema brojeva.

**Dokaz** — samo `PRODUCTION` sposobnosti iz `VINDEX_WEBSITE_CAPABILITY_MAP.md`.

**Responzivno** — 2 kolone → 1.

---

## 6 · ZA KOGA

**Cilj** — fokus bez zaključavanja u jednu delatnost.

**Poruka** — jedan pasus: advokatura je prva primena i sredina u kojoj se
proizvod proverava.

**Vizuel** — nema.

---

## 7 · STANJE *(poštenje kao pozicija)*

**Cilj** — pretvoriti odsustvo korisnika iz slabosti u signal.

**Poruka**
> Vindex još nema korisnike. Tražimo prve.
> Nema preporuka, nema izmerene tačnosti, nema podataka o brzini — jer ništa od
> toga nije mereno.

**Vizuel** — nema. Okvir sa levom akcentnom linijom `2px`, jedini takav na sajtu.

**Interakcija** — CTA „Prijavite se za betu".

**Responzivno** — pun po širini, CTA ispod.

---

# `/bezbednost`

## Mehanizmi

Lanac kao SVG, isti jezik kao „Kako radi":

```
ZAHTEV ─▶ ULAZNA KAPIJA ─▶ PROVAJDER ─▶ PROVERA ODGOVORA ─▶ POREKLO ─▶ EVIDENCIJA
```

Svaki članak nosi jednu rečenicu i putanju do koda u monospace.

## Šta nemamo — **javna sekcija**

Doslovno, sa `⚠` u amber boji:
- ⚠ Nema nezavisne bezbednosne revizije ni sertifikata.
- ⚠ Izvori navode propis i član — ne vode do dokumenta iz spisa i ne mogu se kliknuti.
- ⚠ Analiza dokumenata i nacrti ne vraćaju spisak izvora.
- ⚠ Razdvajanje po nalogu je pokriveno testovima, **ne** oslonjeno na bazu.

> Ova sekcija je najvredniji deo stranice. U kategoriji u kojoj svi tvrde
> „bank-level security", spisak onoga što ne tvrdite je jedini razlog da vam se
> veruje za ostalo.

---

# `/beta`

**Forma — četiri polja, dva obavezna:** ime · e-pošta · kancelarija *(opciono)* ·
kratka poruka *(opciono)*.

**Ograničenja koja oblikuju dizajn** *(iz `FRONTEND_INTEGRATION_PLAN.md`)*:
- endpoint uvek vraća `200` sa **tri različite poruke** → forma prikazuje
  `poruka` iz odgovora, nikad fiksan tekst
- `422` telo je engleski Pydantic ispis → **validacija na klijentu**, server
  poruka za 422 se nikad ne prikazuje
- ivica polja mora biti `--vw-line-input` (3,22:1) — nasleđena je 1,21:1, dakle
  polje je praktično nevidljivo, a ovo je jedina konverziona tačka sajta

**Founding Partner** — sekcija na istoj stranici, **bez druge forme**. CTA vodi
na istu formu. Sadrži javnu sekciju „Šta ne obećavamo".

---

# RESPONZIVNO — PRAVILA KOJA VAŽE SVUDA

| Prelom | Ponašanje |
|---|---|
| **≥1024px** | dve/tri kolone gde je predviđeno; dijagrami horizontalni |
| **640–1024px** | sve na jednu kolonu; dijagrami se okreću vertikalno |
| **<640px** | navigacija u drawer sa **identičnim** skupom stavki kao desktop *(zatečeni landing tu ima dva različita menija)*; CTA pun po širini; dodirne mete ≥44px |

**Ništa se ne sakriva na mobilnom.** Ako sekcija nije vredna mobilnog, nije
vredna ni desktopa.

---

# PERFORMANSE

- Fontovi: **samostalno hostovani** *(odluka vlasnika — v. `DEFERRED_FINDINGS.md`)*.
  Google Fonts danas idu kroz service worker cache-first bez isteka, pa promena
  fonta korisniku aplikacije nikad ne stigne do bump-a keša.
- Sve slike su inline SVG — nema mrežnih zahteva, nema layout shift-a.
- CSS: jedan `static/site.css`, ne devet inline kopija.
- Bez build alata — repo ga nema i ovaj sajt ga ne uvodi.
