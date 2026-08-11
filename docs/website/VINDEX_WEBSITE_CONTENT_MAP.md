# VINDEX AI — MAPA SADRŽAJA SAJTA

Sinteza tri Phase A dokumenta. Svaka sekcija ispod vezana je za tvrdnju iz
`VINDEX_WEBSITE_CLAIMS_REGISTRY.md` i sposobnost iz
`VINDEX_WEBSITE_CAPABILITY_MAP.md`. Vizuelna pravila iz
`VINDEX_WEBSITE_ARCHITECTURE.md`.

Stanje: `108dc48b`.

---

# 0. ŠTA JE DISCOVERY PROMENIO U ODNOSU NA RANIJI PLAN

Raniji plan (`VINDEX_AI_WEBSITE_CONTENT_MATRIX.md`, stanje `b29ffb6f`) i dalje
stoji u pozicioniranju. Tri stvari su se promenile i menjaju sadržaj:

**1. Poreklo odgovora je sada VIDLJIVO korisniku.** Commit `b984a039` je dodao
`_vxRenderIzvori` (`static/vindex.js:924-955`, element `index.html:4028`).
Korisnik vidi propise i članove na kojima odgovor počiva. Raniji plan je
pretpostavljao da to ne postoji i predviđao samo dijagram.

**2. Naslovna poruka mora biti uža nego „Vindex zna odakle zna".** Vidi se
**propis i član**, ne dokument i ne mesto u dokumentu, i ne može se kliknuti.
Sama ta rečenica obećava putanju do dokumenta koje nema.

**3. Postoje TRI žive javne površine sa suprotnim porukama.** To je nalaz koji
sajt mora da reši, a ne samo da ga zaobiđe — v. §6.

---

# 1. CENTRALNA PORUKA

Najjača dokaziva formulacija, i ona koju sajt koristi:

> **Odgovor sa navedenim propisom. Ili nikakav odgovor.**

Drugi deo je jači od prvog i skoro se ne koristi u ovoj kategoriji:
`main.py:3354-3362` — na niskoj pouzdanosti sistem **odbija da odgovori i model
uopšte ne poziva**. To je tvrdnja koju konkurencija po pravilu ne može da
izgovori, i potpuno je dokaziva.

Podnaslov, takođe dokaziv:

> Vindex vam kaže na kojim propisima počiva svaki odgovor — i ćuti kada pouzdan
> izvor ne postoji.

**Zabranjeno kao samostalna naslovna rečenica:** „Vindex zna odakle zna" —
obećava trag do dokumenta. Sme samo kao ideja **iznad** jedne od dve rečenice gore.

---

# 2. TRI DOKAZA KOJA NOSE SAJT

Izabrana iz `CAPABILITY_MAP` po kriterijumu: dokazano testom, živo na
korisničkoj putanji, i razumljivo advokatu bez objašnjavanja.

| # | Poruka za advokata | Mehanizam | Dokaz |
|---|---|---|---|
| **1** | Brojeve računa program. AI ih samo objašnjava. | `services/risk_engine.py` — nijedan AI izlaz ne sme biti jedini izvor rizika, statusa, roka ni spremnosti | 10+ test fajlova, 6+ rutera |
| **2** | Nacrt ne sme da izmisli član propisa. | izmišljen broj se zamenjuje oznakom `[proveriti relevantan član]` — **nikad drugim brojem** | `test_phoenix_mission_010_drafting_rag_grounding.py` |
| **3** | Predmet se sam ažurira — i to tačno jednom. | pad servera usred lanca **ne izaziva ponovni AI trošak** | `test_omega_sprint002_case_intelligence.py::test_scenario4_*` |

Treći je najneočekivaniji i najuverljiviji za nekoga ko plaća po upotrebi.

---

# 3. STRUKTURA SAJTA

Samo stranice sa dovoljno stvarnog materijala. Redosled na početnoj namerno
stavlja **poverenje pre nabrajanja funkcija** — kupac je pojedinac koji sam snosi
rizik greške u pravnom radu.

| Strana | Prio | Postoji materijal? |
|---|---|---|
| **Početna** | P0 | da |
| **Kako radi** | P0 | da — 4 koraka, svi dokazani |
| **Bezbednost** | P0 | da — postoje `security.html`, DPA, AI disclosure, bezbednosni list |
| **Beta** *(ne „Cenovnik")* | P0 | da — waitlist već postoji (`POST /waitlist/prijava`) |
| **Kontakt** | P0 | najviše 3 polja |
| **Pravno** | P0 | 6 postojećih stranica koje landing danas **ne linkuje** |
| **Tehnologija** | P1 | da, ali bez nabrajanja buzzworda |
| **Za advokate** | P1 | scenariji radnog dana |
| **Vizija** | P1 | jasno odvojeno TODAY / BUILDING / VISION |
| ~~Cenovnik~~ | — | **NE** — v. §6.2 |
| ~~O nama / Blog / FAQ / Industrije~~ | — | **NE praviti sada** |

---

# 4. POČETNA — SEKCIJE

| # | Sekcija | Poruka | Tvrdnja iz registra | Vizuel |
|---|---|---|---|---|
| 1 | **Hero** | „Odgovor sa navedenim propisom. Ili nikakav odgovor." | odbijanje na niskoj pouzdanosti · prikaz izvora | SVG dijagram: pitanje → propisi → odgovor / ili ćutanje |
| 2 | **Problem** | Kontekst se gubi. Rokovi su u tekstu, ne u kalendaru. Provera traži ponovno čitanje. | opis, **bez ijedne statistike** | bez slike |
| 3 | **Kako radi** | 4 koraka: unos → uređen predmet → AI nad uređenim prikazom → navedeni izvor | intake · `case_context` · `ai_provenance` | horizontalni SVG tok |
| 4 | **Zašto verovati** *(iznad funkcija)* | Brojeve računa program · nacrt ne izmišlja član · evidencija se ne može izmeniti | tri dokaza iz §2 | tri kartice, bez ikona |
| 5 | **Šta radi danas** | 6 grupa, ne lista od 40 stavki | samo `PRODUCTION` iz capability mape | tekstualne grupe |
| 6 | **Za koga** | Advokatura je prva primena i sredina za proveru | strateška, ne funkcionalna | jedan red |
| 7 | **Stanje** | Pred zatvoreno testiranje. Nema korisnika. | pošteno | bez slike |

**Primarni CTA:** „Prijavite se za zatvoreno testiranje" — jedini iskren u ovoj fazi.
**Sekundarni:** „Preuzmite bezbednosni list" — dokument već postoji.
**Zabranjeno:** „Počnite besplatno" · „Zakažite demo" · „Kontaktirajte prodaju".

---

# 5. ŠTA SAJT MORA POŠTENO REĆI DA NE RADI

Ovo nije sekcija stida nego diferencijator — konkurencija ovo ne piše.

- Izvori pokazuju **propis i član**, ne dokument i ne mesto u njemu. Ne može se kliknuti.
- Za analizu dokumenata i za nacrte **izvori se ne prikazuju uopšte**.
- Nema korisnika, nema preporuka, nema mernih rezultata.
- Ne tvrdimo procenat tačnosti — nikad nije meren.
- Ne tvrdimo uštedu vremena — nikad nije merena.
- Nema nezavisne bezbednosne revizije ni sertifikata.
- Nacrt je **polazna tačka, ne gotov podnesak**.
- Procena rizika je **pomoć u proceni, ne pravni savet**.

## Dve ograde koje su izašle iz capability mape i moraju se poštovati

**Ne sme se reći „AI nikad ne presuđuje".** Ograničenje AI verdikta postoji samo
u orkestratoru strategije, ne i na tri samostalne rute.

**Ne sme se reći „zaštićeno na nivou baze".** Izolacija počiva na **541 ručnom
filteru u kodu**; aplikacija se povezuje service ključem koji RLS zaobilazi.
Dozvoljena formulacija: *„razdvojeno po nalogu, pokriveno testovima"*.

---

# 6. NALAZI KOJE SAJT MORA DA ZATVORI

Nisu stilski. To su **žive javne kontradikcije**.

## 6.1 Tri površine, tri različite ponude

| Površina | Šta danas govori |
|---|---|
| `/` (`landing.html`) | „Počni besplatno — 15 upita bez kartice" → `/app#register` |
| `/app` pre-auth (`index.html:4166-4227`) | „Zatražite rani pristup — Beta, ograničen broj mesta" |
| `/pricing` (`pricing.html`, 31 KB) | 4 plana sa cenama |

Posetilac koji otvori dve od tri dobija dve različite priče o tome šta proizvod
jeste i da li se plaća.

## 6.2 `/pricing` je preživeo P0-F — i **javan je danas**

P0-F je uklonio sekciju `cenovnik` iz `landing.html` (potvrđeno na produkciji,
Wave 5), ali **samostalna ruta `/pricing` nije uklonjena** (`api.py:1550`).

Razlozi zbog kojih je cenovnik uklonjen važe i za nju, doslovno
(`landing.html:1000-1033`): nijedan plan se ne može kupiti — `STRIPE_URL = ''`
(`static/vindex.js:124`); krediti se ne obnavljaju (15 se dodeli jednom pri
registraciji); reklamirane funkcije su gejtovane strože nego što su prodavane
(403); obećani SLA se nigde ne meri.

**Odluka: `/pricing` se uklanja zajedno sa zamenom landinga.** Vraća se tek kad
postoji način da se plati.

## 6.3 Kontradiktorni brojevi na javnim površinama

`landing.html` tvrdi **„18 zakona RS"**, pre-auth ekran **„847 zakona Srbije"**.
Najmanje jedan je netačan. Do provere korpusa — **nijedan broj ne ide na sajt**.

## 6.4 Pravne stranice postoje, ali niko do njih ne stiže

Postoji 6 pravnih/bezbednosnih stranica. `landing.html` **ne linkuje nijednu**,
a 9 od 20 linkova u podnožju je `href="#"`. Novi footer ih sve linkuje.

---

# 7. VIZUELNA OGRANIČENJA KOJA SADRŽAJ MORA DA POŠTUJE

Iz `VINDEX_WEBSITE_ARCHITECTURE.md`:

- **Nema nijednog snimka proizvoda.** Postoji samo `screenshot_login.png` (ekran
  za prijavu). Zato sadržaj mora da stoji na **SVG dijagramima**, ne na
  snimcima — i ne sme tvrditi da dijagram prikazuje postojeći interfejs.
- **CSP zabranjuje** eksterne slike, iframe-ove, video i analitiku. Sve
  self-hostovano. Inline `<style>`/`<script>` su dozvoljeni.
- **`assets/lady_justice.jpg` je zabranjen** — stock alegorija.
- **Zabranjene generičke ikone** (⚔️🧠⚖️🎯⚡💡📊🚨). Dozvoljeni `✓` i `⚠`.
- `--tx-3` ima kontrast **2,44:1** — pada AA, a nosi podnožje. Novi sajt ga ne
  koristi za tekst.
- `#00d4ff` na `#010308` je **11,65:1** — prolazi AAA. Raniji strah je bio netačan.
- `static/sw.js` kešira `/` — `CACHE_NAME` mora porasti pri zameni landinga.

## Tri elementa koja čine da Vindex izgleda kao Vindex

1. **Cormorant Garamond sa italic `<em>` u akcentu** — obrazac `Vindex <em>AI</em>`.
2. **`#010308`** — skoro crna, ali plava, ne `#000`.
3. **Monospace za svaki podatak, oznaku i brojku.**

Teal `#00d4ff` namerno **nije** na listi — to je najgeneričniji deo identiteta.

---

# 8. REDOSLED IZRADE

| Faza | Sadržaj |
|---|---|
| **B** | Dizajn sistem izveden iz postojećih tokena; dokumentovati šta se nasleđuje |
| **C** | Informaciona arhitektura iz §3 |
| **D** | Početna — postaje vizuelna osnova za ostalo |
| **E** | Kako radi · Bezbednost · Tehnologija · Za advokate · Vizija |
| **F** | CTA, waitlist, kontakt, linkovi ka aplikaciji, uklanjanje `/pricing` |
| **G** | Responzivno, pristupačnost, SEO, performanse, `CACHE_NAME`, regresija |

**Truth audit i claim-by-claim verifikacija idu pre nego što se kaže da je gotovo.**
