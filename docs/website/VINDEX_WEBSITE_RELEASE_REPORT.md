# VINDEX AI — WEBSITE, IZVEŠTAJ O ISPORUCI (Phase C)

---

# IMPLEMENTED

Devet stranica javnog sajta, jedan CSS temelj, 128 testova.

| Ruta | Fajl | Šta nosi |
|---|---|---|
| `/` | `site/index.html` | hero · problem · kako radi · zašto verujete · izvori · šta radi danas · stanje |
| `/kako-radi` | `site/kako-radi.html` | razrada četiri koraka + dva dijagrama |
| `/sposobnosti` | `site/sposobnosti.html` | šest celina, sa granicama svake |
| `/za-advokate` | `site/za-advokate.html` | scenariji radnog dana |
| `/bezbednost` | `site/bezbednost.html` | lanac od šest karika + javna sekcija „šta nemamo" |
| `/vizija` | `site/vizija.html` | DANAS / VIZIJA, strogo odvojeno |
| `/tehnologija` | `site/tehnologija.html` | slojevi arhitekture, bez buzzworda |
| `/beta` | `site/beta.html` | prijava + Founding Partner |
| `/kontakt` | `site/kontakt.html` | forma, bez pravnog identiteta |

Plus: `/sitemap.xml` (domen iz `request.base_url`, ne hardkodovan),
`robots.txt` dopunjen `Sitemap:` linijom.

**Uklonjeno:** `landing.html` i `pricing.html` — oba fizički obrisana, ne
sakrivena. Ruta `/pricing` vraća **404**.

---

# VERIFIED

## Truth coverage

**Svaka rečenica na sajtu postoji u `CONTENT_TRUTH_MAP.md`.** Provereno po
stranici, automatski, poređenjem sa kolonom „JAVNA FORMULACIJA":

| Stranica | Tvrdnji | Iz truth mape |
|---|---|---|
| kako-radi | 34 | **100%** |
| sposobnosti | 52 | **100%** |
| za-advokate | 34 | **100%** |
| bezbednost | 31 | **100%** |
| vizija | 22 | **100%** |
| tehnologija | 26 | **100%** |

## Claims — namerno izostavljeno

Nijedan broj korpusa (18 / 847 zakona — najmanje jedan netačan, nijedan nije
proveren) · nijedan procenat tačnosti · nijedna ušteda vremena · nijedan broj
korisnika · nijedna preporuka · nijedan logotip klijenta · nijedna cena · nijedan
snimak proizvoda · nijedan broj mesta u beti · nijedan rok za prijave.

Tri formulacije koje zvuče tačno a nisu, i zato ih nema:

| Zabranjeno | Zašto |
|---|---|
| „AI nikad ne presuđuje" | ograničenje verdikta postoji **samo** u orkestratoru strategije, ne i na tri samostalne rute |
| „zaštićeno na nivou baze" | izolacija je ručni filter u kodu; aplikacija se povezuje service ključem koji RLS zaobilazi |
| „potvrda je poslata na mejl" | SMTP se tiho preskače ako env nije podešen — korisnik dobija `200` i kad nijedan mejl nije otišao |

---

# ROUTES

Sve provereno **uživo** kroz `TestClient`, ne čitanjem koda:

```
200  /              public, max-age=300      200  /privacy          max-age=86400
200  /kako-radi     public, max-age=300      200  /terms            max-age=86400
200  /sposobnosti   public, max-age=300      200  /security         max-age=3600
200  /za-advokate   public, max-age=300      200  /dpa              max-age=3600
200  /bezbednost    public, max-age=300      200  /ai-disclosure    max-age=3600
200  /vizija        public, max-age=300      200  /bezbednosni-list max-age=3600
200  /tehnologija   public, max-age=300      200  /status           no-cache
200  /beta          public, max-age=300      200  /sitemap.xml      max-age=3600
200  /kontakt       public, max-age=300      200  /static/site.css  max-age=3600
404  /pricing  ← uklonjen
```

`/` je ranije bio **jedina ruta bez `Cache-Control`**. Sada ga ima.

---

# APPLICATION SAFETY

| Provereno | Ishod |
|---|---|
| Puna regresija | **4946 passed / 1 skipped / 0 failed** *(baseline 4818)* |
| `/api/*` rute | netaknute — nijedna izmena van sekcije za sajt |
| Autentifikacija | netaknuta |
| AI governance, naplata, Case Genome, šema baze | **nedirano** |
| `static/` mount | `site/` **nije** montiran — izbegnut obrazac dvostrukog serviranja |
| Docker | `COPY . .` bez `.dockerignore` → `site/` ulazi u image bez izmene konfiguracije |
| Service worker | `vindex-v123` → **`vindex-v124`** u istom commitu; jedini brisač keša koji postoji |

---

# TESTS

`tests/test_website_public.py` — **128 testova**, svi mere **odgovor servera**,
ne fajl na disku. Stranica koja postoji u `site/` a nije zakačena na rutu je
nevidljiva korisniku, i test koji čita fajl to ne bi primetio.

## Mutacije — tri, sve diskriminišu

| Mutacija | Ishod |
|---|---|
| vraćena tvrdnja „Počni besplatno — 15 upita" u hero | `test_nema_zabranjenih_tvrdnji[/]` **PAO** |
| vraćena ruta `/pricing` | `test_pricing_ruta_vise_ne_postoji` **PAO** |
| canonical promenjen na `vindex-ai.com` | `test_canonical_je_vindex_rs[/beta]` **PAO** |

## Greška u sopstvenim testovima, uhvaćena i popravljena

Prva verzija merila je **sirov odgovor** i prijavila tri lažna pada: `/kontakt`
„sadrži" matični broj — u komentaru koji objašnjava da ga namerno **nema**;
`/beta` „obećava" potvrdu mejlom — u komentaru koji tu formulaciju **zabranjuje**.
Četvrti pad: `cena` kao podniz pogađa **pro`cena`t**.

Popravljeno uvođenjem `_vidljivi_tekst()` (uklanja komentare, `<script>`,
`<style>`) i granicom reči. **Test je popravljen, stranice nisu** — isti razred
greške (test meri komentar umesto koda) uhvaćen je u ovom repou već tri puta.

---

# STATUS PO STAVKAMA

| | |
|---|---|
| **Beta CTA** | jedini primarni poziv na akciju; forma staje na postojeći `POST /waitlist/prijava` **bez ijedne izmene backenda** |
| **Founding Partner** | sekcija na `/beta`, bez druge forme, bez cene, bez broja mesta, bez roka. Javna podsekcija „Šta ne obećavamo". |
| **Pricing** | **OFF.** Ruta obrisana, fajl obrisan, nijedna stranica je ne linkuje |
| **Pravni identitet** | Vindex AI nema registrovano pravno lice → nema PIB-a, adrese, matičnog broja ni „d.o.o." Test to čuva. Podnožje i `/kontakt` rade bez njih. |
| **SMTP** | stranica **ne obećava** mejl. Prikazuje se isključivo `poruka` iz odgovora servera, doslovno |
| **SEO** | title · description · canonical (`https://vindex.rs`) · OpenGraph · Twitter · robots · sitemap |
| **Pristupačnost** | jedan `<h1>` po stranici · preskok na sadržaj · vidljiv `:focus-visible` (nasleđeni sistem ga nema nigde) · `aria-current` · svaki SVG ima `<title>` · dodirne mete ≥44px · `prefers-reduced-motion` gasi sve |
| **Responzivno** | prelomi 640 / 1024; mobilna navigacija nosi **identičan** skup stavki kao desktop |
| **Performanse** | nula eksternih slika · nula iframe-ova · nula video zapisa · nula biblioteka · svi vizuali su inline SVG · jedan CSS fajl · bez build alata |

---

# KNOWN LIMITATIONS

Nisu nedostaci izrade nego stanje proizvoda. Sajt ih **javno navodi**, ne krije.

| # | Ograničenje | Posledica za sajt |
|---|---|---|
| 1 | **Nema nijednog snimka proizvoda** | svi vizuali su SVG dijagrami sa `<figcaption>` da su konceptualni prikaz |
| 2 | **Broj zakona u korpusu nije proveren** (18 vs 847) | nijedan broj korpusa ne ide na sajt |
| 3 | **SMTP može biti tiho preskočen** | vlasnik mora proveriti produkciono okruženje pre nego što beta krene, inače prijave stižu u bazu a niko ne dobija obaveštenje |
| 4 | **Kontakt i Beta dele istu tabelu** `waitlist` | razlikuje ih samo prefiks `[KONTAKT]` / `[BETA]` u polju `poruka` |
| 5 | **Tabela `waitlist` nema kolonu za saglasnost** | saglasnost stoji kao tekst, ne čuva se |
| 6 | **`/tehnologija` je najtanja stranica** | 7 od 23 reda su njeni; ostalo su preformulacije. Arhitektura je i označila kao P2 |
| 7 | **Adrese e-pošte na postojećim pravnim stranicama koriste `vindex.ai`** | kanonski domen je `vindex.rs`; nesklad nije rešavan jer dira pravne strane pod testom |

## Šest ispravki za `CONTENT_TRUTH_MAP.md`

Nađene pri implementaciji, **nisu upisane** (dokument je iz Phase B):

1. red 49 — „i to pre naplate" tačno je samo za stream rutu
2. red 50 — postoji i treći izuzetak: embeddings nemaju ni ulazni guard ni izlazni filter
3. red 52 — fail-closed ima rezidualnu rupu: ako i sama instalacija brane padne, granica ostaje otvorena
4. red 54 — `retrieval_query` se upisuje kao **sirov tekst**, jedini neheširani u zapisu porekla
5. red 74/81 — filtera je **648**, ne 541
6. `/tehnologija` je bila siroče u podnožju početne — ispravljeno

---

# STANJE

```
HEAD pre:     faa4192e
Baseline:     4818 passed / 1 skipped / 0 failed
Final:        4946 passed / 1 skipped / 0 failed   (+128)
Produkcioni fajlovi izmenjeni: api.py, static/sw.js
Obrisano:     landing.html, pricing.html
Novo:         site/ (9 stranica), static/site.css, tests/test_website_public.py
Worktree:     CLEAN
```

**Jedna stvar blokira lansiranje, i nije tehnička:** provera da je SMTP podešen
na produkciji. Bez toga Beta prijave stižu u bazu, a vi ne dobijate nijedno
obaveštenje.
