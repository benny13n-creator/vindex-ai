# VINDEX AI — INFORMACIONA ARHITEKTURA SAJTA (Faza B: DIZAJN)

**Odnos prema `VINDEX_WEBSITE_ARCHITECTURE.md`:** taj dokument opisuje *zatečeno
tehničko stanje* (rute, CSP, tokeni, kolizije, rizici zamene landinga); **ovaj**
dokument opisuje *kako se sajt strukturira* — koje stranice postoje, kojim redom
teku sekcije, kuda vode dugmad i kako se sve slaže na telefonu. Prvi je snimak
koda, drugi je odluka o sadržaju.

Obavezujući izvori: `VINDEX_WEBSITE_CLAIMS_REGISTRY.md` (jedini registar tvrdnji),
`VINDEX_WEBSITE_CAPABILITY_MAP.md`, `VINDEX_WEBSITE_CONTENT_MAP.md`,
`VINDEX_WEBSITE_ARCHITECTURE.md`.

**Nijedan produkcioni fajl nije menjan u ovoj fazi.**

Notacija tvrdnji: `[REG §4 · VERIFIED]` = red u §4 registra. Ovaj dokument
**ne uvodi nove tvrdnje** — samo raspoređuje postojeće. Sekcije bez tvrdnje
nose oznaku `OPISNA` i ne smeju sadržati nijednu proverljivu izjavu o proizvodu.

---

# 1. SITEMAP

## 1.1 Prihvaćene stranice — nove

| Ruta | Stranica | Prio |
|---|---|---|
| `/` | Početna | P0 |
| `/kako-radi` | Kako radi | P0 |
| `/bezbednost` | Bezbednost i poverenje | P0 |
| `/beta` | Beta i Founding Partner | P0 |
| `/sposobnosti` | Sposobnosti | P1 |
| `/za-advokate` | Za advokate | P1 |
| `/vizija` | Vizija | P1 |
| `/tehnologija` | Tehnologija | P2 |
| `/kontakt` | Kontakt | P0 — **blokirana**, v. §1.4 |

### `/` — Početna

- **Svrha:** u pet sekundi reći šta proizvod radi i zašto mu se sme verovati; u
  petnaest sekundi dovesti do Bete.
- **Publika:** advokat pojedinac ili mala kancelarija u Srbiji, koji sam snosi
  rizik greške u pravnom radu.
- **Primarna poruka:** „Odgovor sa navedenim propisom. Ili nikakav odgovor."
- **CTA:** primarni — „Prijavite se za zatvoreno testiranje".
- **Bez nje se gubi:** sve. Jedina ruta koju posetilac zna napamet.

### `/kako-radi` — Kako radi

- **Svrha:** pokazati da AI ne radi nad haosom nego nad **uređenim predmetom**, i
  da tok ima izlaz „ne znam".
- **Publika:** advokat koji je već zainteresovan i traži mehanizam, ne obećanje.
- **Primarna poruka:** četiri koraka — unos → uređen predmet → AI nad uređenim
  prikazom → navedeni izvor ili ćutanje.
- **CTA:** „Prijavite se za betu"; sekundarni „Vidite šta radi danas".
- **Bez nje se gubi:** jedini dokaz da je poruta sa početne mehanizam, a ne slogan.
  Početna ima 4 koraka u jednom redu — bez ove stranice nema mesta da se svaki
  korak potkrepi.

### `/bezbednost` — Bezbednost i poverenje

- **Svrha:** odgovoriti na advokatsku tajnu pre nego što posetilac pomisli na
  funkcije; i **objediniti sve što se danas zove „governance"**.
- **Publika:** oprezan kupac, i svako ko pita „gde idu podaci mojih klijenata".
- **Primarna poruka:** kapija oko AI-ja se zatvara kad ne radi; evidencija se ne
  može izmeniti; predmet A ne ulazi u predmet B — i nemamo nezavisnu reviziju.
- **CTA:** tercijarni — „Preuzmite bezbednosni list (PDF)".
- **Bez nje se gubi:** šest pravnih/bezbednosnih stranica ostaje bez ijednog
  ulaza sa sajta — tačno stanje koje danas postoji (`landing.html` ne linkuje
  nijednu).

### `/beta` — Beta i Founding Partner

- **Svrha:** jedina konverzija na sajtu.
- **Publika:** ubeđeni posetilac.
- **Primarna poruka:** zatvoreno testiranje, ograničen broj mesta, ne plaća se,
  nema roka koji obećavamo.
- **CTA:** forma → `POST /waitlist/prijava`.
- **Bez nje se gubi:** sajt bez sabirne tačke. Zatečeni `landing.html` **nema
  nijednu formu** — jedina konverzija je odlazak na `/app`.

### `/sposobnosti` — Sposobnosti

- **Svrha:** puna, poštena lista onoga što je danas na korisničkoj putanji.
- **Publika:** advokat koji je prošao poverenje i sada procenjuje vrednost.
- **Primarna poruka:** osam grupa poslova, sve `PRODUCTION`.
- **CTA:** „Prijavite se za betu".
- **Bez nje se gubi:** početna bi morala da nosi 56 stavki umesto 6 grupa, ili bi
  se 237 dokazanih sposobnosti prećutalo. Ovo je jedini vlasnik inventara.

### `/za-advokate` — Za advokate

- **Svrha:** prevesti sposobnosti u radni dan.
- **Publika:** advokat koji ne čita liste funkcija.
- **Primarna poruka:** četiri scenarija, u svakom i šta sistem **ne** radi.
- **CTA:** „Prijavite se za betu".
- **Bez nje se gubi:** most između „šta ima" i „šta meni znači". Sposobnosti
  nabrajaju, ovo pripoveda — vidi granicu vlasništva u §1.3.

### `/vizija` — Vizija

- **Svrha:** jedno mesto na kome piše **šta danas ne radi**, i šta je namera.
- **Publika:** posetilac koji sumnja da je nešto prećutano.
- **Primarna poruka:** DANAS · U IZRADI · VIZIJA — tri odvojena bloka, bez rokova.
- **CTA:** „Prijavite se za betu".
- **Bez nje se gubi:** 17 stavki iz registra §9 („šta moramo pošteno reći da ne
  radimo") nemaju vlasnika i razlivaju se po celom sajtu ili nestaju.

### `/tehnologija` — Tehnologija

- **Svrha:** za onoga ko pita „koji model" i „šta ako izmisli".
- **Publika:** tehnički pismen advokat; savetnik koga advokat pita za mišljenje.
- **Primarna poruka:** model je komponenta, ne proizvod; brojeve računa program.
- **CTA:** „Prijavite se za betu".
- **Bez nje se gubi:** najmanje. **Ovo je jedina stranica koja sme da otpadne iz
  prvog talasa** ako rokovi stisnu — njen sadržaj je najuže preklopljen sa
  `/bezbednost` i `/kako-radi`.

### `/kontakt` — Kontakt

- **Svrha:** kanal koji nije prijava za betu.
- **Publika:** novinar, potencijalni partner, pravno pitanje o obradi podataka.
- **Primarna poruka:** tri polja i pravni identitet firme.
- **CTA:** slanje poruke.
- **Bez nje se gubi:** DPA i Politika privatnosti upućuju na rukovaoca podataka
  koga nigde nije moguće kontaktirati.
- **Status: BLOKIRANA** — v. §1.4.

## 1.2 Prihvaćene stranice — postojeće, ostaju nepromenjene

Ove stranice **nisu deo redizajna**. Sajt ih samo linkuje.

| Ruta | Fajl | Zašto ostaje |
|---|---|---|
| `/privacy` | `privacy.html` | pravna obaveza |
| `/terms` | `terms.html` | pravna obaveza |
| `/ai-disclosure` | `static/ai-disclosure.html` | koji model, šta se šalje |
| `/dpa` | `static/dpa.html` | B2B blokator bez njega |
| `/security` | `static/security.html` | 15 sekcija za revizore |
| `/bezbednosni-list` | `static/bezbednosni-list.html` | A4 one-pager |
| `/status` | `static/status.html` | jedina živa dinamička stranica |

**Upozorenje za implementaciju:** `tests/test_api_security.py:84-99` traži da
`/privacy` i `/terms` sadrže rečenicu „ne predstavljaju pravni savet". Svaka
izmena tih dveju stranica mora je zadržati.

**`/status`** ostaje funkcionalno netaknut, ali nosi zabranjene ikone
(`⚖️⚡🤖🗄️🔍⚙️`, `status.html:46,62,96`). Čišćenje ikona je zaseban zadatak, ne
uslov za sajt.

## 1.3 Granica vlasništva — da se tri stranice ne preklope

Pravilo „1 koncept = 1 vlasnik = 1 istina" primenjeno na najveći rizik ovog
sitemapa:

| Koncept | Vlasnik | Ostali smeju |
|---|---|---|
| **inventar sposobnosti** (šta postoji) | `/sposobnosti` | linkovati, nikad prepisivati listu |
| **radni scenariji** (šta to meni znači) | `/za-advokate` | linkovati |
| **mehanizam toka** (kako podatak putuje) | `/kako-radi` | linkovati |
| **zaštita i evidencija** | `/bezbednost` | linkovati |
| **model i deterministički deo** | `/tehnologija` | linkovati |
| **šta ne radi** | `/vizija` | ponoviti **samo** ogradu uz konkretnu tvrdnju |

Poslednji red je jedini dozvoljeni izuzetak: ograda iz registra mora stajati uz
tvrdnju **gde god se tvrdnja pojavi**, jer je registar traži doslovno.

## 1.4 Odbijene stranice

| Odbijeno | Razlog |
|---|---|
| **Kancelarijsko znanje** | Nema materijala. `CAPABILITY_MAP` §„Kod koji postoji ali nije ožičen": Institucionalno učenje (14 od 15 ruta neožičeno), Firm Memory (11 ruta, 0 poziva), Knowledge Transfer (8, 0), Knowledge Hygiene (7, 0), Lična baza znanja (5, 0 poziva i 0 testova), Memory Graph (4, 0). Jedina `PRODUCTION` stavka je „pisanje u stilu kancelarije na osnovu ranijih podnesaka" — **jedna crtica**. Cela stranica bi bila reklamiranje neožičenog koda. |
| **Governance** | Nije odbijeno kao sadržaj nego kao **zasebna stranica**. Sve tvrdnje koje bi je nosile (kapija nad AI-jem, izlazni filter, poreklo poziva, jedinstvena kapija dozvola, unutrašnje provere pri svakoj izmeni) već su vlasništvo `/bezbednost`. Druga stranica bi ih morala prepisati → dva vlasnika za jedan koncept. Uz to: korisnički ekran evidencije **ne postoji** (`ROADMAP`), pa governance nema nijednu sopstvenu površinu. **Postaje sekcija na `/bezbednost`.** Dodatno, reč je engleska; sajt je na srpskom. |
| **Founding Partner (zasebna stranica)** | Odbijeno kao stranica, prihvaćeno kao **sekcija `/beta#founding-partner`**, **bez sopstvene forme**. Razlog: u kodu ne postoji nijedan mehanizam koji Founding Partnera razlikuje od obične prijave — `waitlist.status` ima tačno tri vrednosti (`pending`/`contacted`/`active`, `routers/waitlist.py:23`), cene nema (`STRIPE_URL=''`), roka nema, SLA se nigde ne meri. **Founding Partner nije izbor u obrascu nego ishod razgovora**, pa nema šta da se zabeleži. Paralelni dokument `FOUNDING_PARTNER.md` §5 dolazi do istog zaključka nezavisno („jedna forma, ne dve — dve odvojene forme bi stvorile utisak dva proizvoda i dva nivoa pristupa koja ne postoje"), a §11.4 izričito ostavlja izbor stranica/sekcija otvorenim i ne vodi ga kao blokator. |
| **FAQ** | `CONTENT_MAP` §3 izričito: „NE praviti sada". Sadržaj koji bi ga popunio je lista „šta ne radi" — a ona ima vlasnika (`/vizija`) i inline ograde. FAQ bi bio treći vlasnik istog sadržaja. |
| **Cenovnik** | Odluka doneta. Uz to se **uklanja ruta `/pricing`** (`api.py:1550-1555`) — v. §7. |
| **O nama / Blog / Industrije / Engleska verzija / Preporuke** | v. §7. |

## 1.5 Šta se uklanja

| Ruta | Radnja | Razlog |
|---|---|---|
| `/pricing` | uklanja se ruta i `pricing.html` | Nijedan plan se ne može kupiti (`static/vindex.js:124` `STRIPE_URL=''`), krediti se ne obnavljaju, reklamirane funkcije su gejtovane strože nego što su prodavane, SLA se ne meri. Sekcija je već uklonjena iz landinga; ruta je preživela. Nov sajt bez cena + živa `/pricing` = ista kontradikcija, samo skrivenija. |

---

# 2. NAVIGACIJA

## 2.1 Glavna navigacija — 5 stavki + prijava + jedno dugme

```
Vindex AI      Kako radi   Sposobnosti   Bezbednost   Za advokate   Vizija      Prijava   [ Prijavite se za betu ]
```

| Element | Vodi na | Tip |
|---|---|---|
| logo `Vindex <em>AI</em>` | `/` | tekstualni logo (vektorski logo ne postoji) |
| Kako radi | `/kako-radi` | link |
| Sposobnosti | `/sposobnosti` | link |
| Bezbednost | `/bezbednost` | link |
| Za advokate | `/za-advokate` | link |
| Vizija | `/vizija` | link |
| **Prijava** | `/app` | **tekstualni link, nikad dugme** |
| Prijavite se za betu | `/beta` | jedino dugme u navigaciji |

**Zašto pet, a ne osam.** Traka je `max-width:1280px`, visina `64px`, logo levo,
dva elementa desno. Pet srednjih stavki + „Prijava" + dugme staje bez lomljenja
na 1280px i bez hamburgera do 768px. `Tehnologija` i `Kontakt` idu **samo u
podnožje** — obe su ciljane, niko ih ne traži u traci.

**Zašto je „Prijava" tekst, a ne dugme.** Dva dugmeta jedno pored drugog
poništavaju primarni CTA. Postojeći korisnik zna gde ide; novi ne sme da bira
između dva jednako glasna poziva.

**Zašto `/app`, a ne `/app#register`.** Zatečeni landing ima pet linkova ka
`/app#register` (`landing.html:761,781,787,799,1046`) koji guraju samouslužnu
registraciju, dok pre-auth ekran te iste aplikacije kaže „Zatražite rani pristup
— ograničen broj mesta" (`index.html:4166-4227`). Sajt koji govori Beta mora
voditi na `/app`, ne na `#register`. Time se zatvara i zatečena kontradikcija
između `/` i `/app`.

**Mobilni meni (`≤768px`):** hamburger → drawer sa **identičnim** skupom stavki,
istim redosledom, plus „Prijava" i CTA. Zatečeni landing ovde greši — desktop
meni ima Funkcije/Web3/Dokumentacija, drawer ima Funkcije/Kako radi/Zašto Vindex
(`landing.html:757-759` vs `:769-783`). Dva različita menija su dve različite
mape sajta.

## 2.2 Podnožje — pet kolona, nula mrtvih linkova

**Tvrdo pravilo: `href="#"` ne postoji nigde na sajtu.** Zatečeno stanje je 9 od
20 linkova u podnožju mrtvo, a nula linkova ka pravnim stranicama.

| Kolona | Stavke |
|---|---|
| **Brend** (1.6fr) | logo · jedna rečenica · red stanja: „Pred zatvoreno testiranje." |
| **Proizvod** | Kako radi `/kako-radi` · Sposobnosti `/sposobnosti` · Za advokate `/za-advokate` · Tehnologija `/tehnologija` · Vizija `/vizija` |
| **Poverenje** | Bezbednost i poverenje `/bezbednost` · Bezbednosni list `/bezbednosni-list` · Bezbednosni list (PDF) `/static/Vindex-AI-Bezbednosni-List.pdf` · Tehnički opis bezbednosti `/security` · Status servisa `/status` |
| **Pravno** | Politika privatnosti `/privacy` · Uslovi korišćenja `/terms` · Obaveštenje o upotrebi AI `/ai-disclosure` · Ugovor o obradi podataka `/dpa` |
| **Pristup** | Prijavite se za betu `/beta` · Prijava `/app` · Kontakt `/kontakt` |

Svih **šest** pravnih/bezbednosnih stranica je linkovano: `/privacy`, `/terms`,
`/ai-disclosure`, `/dpa`, `/security`, `/bezbednosni-list` — plus `/status` kao
sedma.

Dno podnožja: `© MMXXVI · Vindex AI` i domen — **domen je blokiran dok se ne
odluči** (`vindex.rs` u landingu, `vindex-ai.com` u canonical-u `pricing.html`,
`vindex.ai` u adresama e-pošte na pravnim stranicama).

**Kontrast:** podnožje se **ne sme** crtati u `--tx-3` (`rgba(255,255,255,0.30)`
= 2,44:1, pada WCAG AA). Minimum je `--tx-2` (6,14:1). Zatečeni landing crta ceo
footer u `--tx-3`.

## 2.3 Gde je ulaz u aplikaciju

Na tačno dva mesta, oba vode na `/app`:

1. **„Prijava"** u glavnoj navigaciji — na svakoj stranici, gore desno.
2. **„Prijava"** u koloni „Pristup" u podnožju.

Plus jedno uslovno mesto: uspešno stanje Beta forme, **samo** kada server vrati
poruku „Vaš nalog je već aktivan. Prijavite se!" — tada se uz poruku prikazuje
link ka `/app` (v. §4.2).

Granica sajt/aplikacija je isključivo vizuelna: `api.py:2354-2356` servira
`index.html` svakome, bez provere. Sajt to ne sme predstavljati kao „zaključan
deo".

---

# 3. STRUKTURA SVAKE STRANICE

## 3.1 `/` — Početna

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Hero** | Izgovara centralnu poruku i odmah nudi Betu. | `[REG §4 · „Kada sistem nema pouzdan izvor, odbija da odgovori umesto da nagađa." VERIFIED]` + `[REG §4 · „Ispod svakog pravnog odgovora Vindex navodi propise i članove…" VERIFIED]` |
| 2 | **Problem** | Imenuje tri poznata bola: kontekst se gubi, rokovi žive u tekstu a ne u kalendaru, provera traži ponovno čitanje. | **OPISNA** — nijedna statistika, nijedan procenat, nijedan broj |
| 3 | **Kako radi** | Četiri koraka u jednom redu, svaki jedna rečenica; vodi na `/kako-radi`. | `[REG §4 · unos više dokumenata, OCR, klasifikacija · VERIFIED]` · `[REG §5 · polje konteksta nosi oznaku porekla · PARTIALLY_VERIFIED + obavezna ograda]` · `[REG §4 · izvori i pouzdanost · VERIFIED]` |
| 4 | **Zašto verovati** | Tri kartice, **iznad** nabrajanja funkcija. | (1) `[CAPABILITY_MAP §Najjače · brojeve računa program]` uz ogradu „brojevi koje vidite računa program", nikad „AI ne presuđuje" · (2) `[REG §5 · izrada nacrta · PARTIALLY_VERIFIED]` + `drafting_grounding` zamena izmišljenog broja oznakom `[proveriti relevantan član]` · (3) `[REG §4 · nepromenljiva evidencija · VERIFIED]`, bez `UNIQUE(prev_hash)` |
| 5 | **Šta radi danas** | Šest grupa poslova, ne lista od 40 stavki; vodi na `/sposobnosti`. | samo `PRODUCTION` iz `CAPABILITY_MAP §Sposobnosti koje sme da prikaže sajt` — grupe: Prijem i obrada spisa · Vođenje predmeta · AI analiza · Izrada nacrta · Pretraga · Kancelarija |
| 6 | **Za koga** | Jedan red: advokatura je prva primena i sredina za proveru. | **OPISNA / strateška** |
| 7 | **Stanje** | Pred zatvoreno testiranje. Nema korisnika. Nema merenja tačnosti. Nema nezavisne revizije. | **OPISNA** — poštena, i namerno pre CTA-a |
| 8 | **Zaključni CTA** | Ponavlja primarni poziv i nudi bezbednosni list kao alternativu. | — |

Sekcija 8 je dodata na sedam iz `CONTENT_MAP §4`; bez nje primarni CTA postoji
samo u heroju, pa posetilac koji je skrolovao do dna nema šta da klikne.

**Grupe 7 i 8 iz `CAPABILITY_MAP` (Strategija, Platforma) se na početnoj
izostavljaju:** Strategija zahteva ogradu koja se ne može ispisati u kartici,
Platforma pripada `/bezbednost`. Obe su na `/sposobnosti`.

**Vizuel:** hero nosi SVG dijagram `pitanje → propisi → odgovor` sa granom
`ili ćutanje`. Sekcija 3 nosi horizontalni SVG tok. Nijedan snimak proizvoda ne
postoji i nijedan mockup nepostojećeg ekrana se ne crta.

## 3.2 `/kako-radi`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Uvod** | Jedna rečenica: AI ne radi nad haosom, nego nad uređenim predmetom. | **OPISNA** |
| 2 | **01 · Unos spisa** | Ceo folder odjednom, OCR skeniranog, prepoznavanje vrste podneska i dokaza. | `[REG §4 · „Unos više dokumenata odjednom, prepoznavanje teksta sa skeniranih dokumenata i automatska klasifikacija." VERIFIED]` — **bez ijedne tvrdnje o kvalitetu OCR-a** |
| 3 | **02 · Uređen predmet** | Isti opis predmeta za sve module; svako polje nosi oznaku porekla; rokovi se izvlače bez komande. | `[REG §5 · PARTIALLY_VERIFIED]` **obavezna ograda doslovno:** „oznaka pokazuje sistemski izvor podatka (tabelu ili modul koji ga računa), a ne pojedinačan dokument — osim za izvode iz dokumenata, koji nose i identifikator dokumenta" · `[REG §4 · „Rokovi se iz dokumenata prepoznaju automatski pri unosu…" VERIFIED]` bez tvrdnje da nijedan rok neće promaći |
| 4 | **03 · AI nad uređenim prikazom** | Svaki poziv kroz jednu kapiju; ulazni filter pre naplate; izlazni filter pre korisnika; kad kapija ne radi — poziv se ne izvršava. | `[REG §4 · jedna kapija · VERIFIED]` · `[REG §4 · izlazna provera · VERIFIED]` · `[REG §4 · prompt injection pre naplate · VERIFIED]` · `[REG §5 · „Svaki AI poziv prolazi kroz jednu kapiju." PARTIALLY_VERIFIED]` **ograda doslovno:** „važi za tekstualne pozive modela; glasovni kanal i ponovno rangiranje rezultata su imenovani izuzeci koji ne prolaze kroz tu kapiju" |
| 5 | **04 · Navedeni izvor — ili ćutanje** | Propis i član ispod odgovora, oznaka pouzdanosti; na niskoj pouzdanosti odgovora nema i model se ne poziva. | `[REG §4 · navođenje propisa i članova · VERIFIED]` · `[REG §4 · oznaka pouzdanosti VISOKA/SREDNJA/NISKA · VERIFIED]` · `[REG §4 · odbijanje na niskoj pouzdanosti · VERIFIED]` |
| 6 | **Šta ovaj tok ne radi** | Šest stavki, doslovno iz registra. | `[REG §9 · Poreklo odgovora, 1-6]`: citat nije klikabilan · izvor ne pokazuje na vaš dokument · nema strane ni pasusa · izvori se prikazuju samo kod pravnog istraživanja, ne kod analize dokumenata i nacrta · kod niske pouzdanosti izvora nema uopšte · nema objašnjenja zašto je baš taj izvor izabran |
| 7 | **CTA** | Beta; sekundarno `/sposobnosti`. | — |

## 3.3 `/bezbednost`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Uvod** | Kaže šta tvrdimo i, odmah, šta ne tvrdimo. | **OPISNA** |
| 2 | **Kapija oko AI-ja** | Kad se zaštita ne podigne, AI poziv se ne izvršava — sistem se zatvara, ne propušta. Odgovor prolazi izlaznu proveru; greška u samoj proveri obara poziv. | `[REG §4 · zatvaranje pri neuspeloj kapiji · VERIFIED]` · `[REG §4 · izlazna provera · VERIFIED]` |
| 3 | **Evidencija koja se ne može izmeniti** | Baza fizički odbija izmenu i brisanje reda evidencije; zapisi su ulančani otiskom. | `[REG §4 · „…ni administrator ne može naknadno izmeniti ni obrisati." VERIFIED]` **bez pominjanja `UNIQUE(prev_hash)`** · `[REG §4 · hash lanac · VERIFIED]` · **zabranjeno:** „revizorski trag koji možete pregledati" — korisnički ekran ne postoji |
| 4 | **Šta se u evidenciju ne upisuje** | Tekst pitanja i odgovora se ne čuva — samo kriptografski otisak. | `[REG §4 · SHA-256 otisci · VERIFIED]` |
| 5 | **Predmet A ne ulazi u predmet B** | Provera vlasništva pre nego što ijedan upit ode u bazu; provera vlasništva unutar same naredbe izmene. | `[REG §4 · provera pre upita · VERIFIED]` · `[REG §4 · vlasništvo unutar naredbe · VERIFIED]` — **obavezna formulacija „razdvojeno po nalogu, pokriveno testovima"; zabranjeno „zaštićeno na nivou baze"** (izolacija počiva na ručnim filterima u kodu, aplikacija se povezuje ključem koji RLS zaobilazi) |
| 6 | **Prava unutar kancelarije** | Uloge razdvojene, radnja bez ovlašćenja se odbija. | `[REG §4 · RBAC 403 · VERIFIED]` |
| 7 | **Trag svakog AI poziva** | Model, trajanje, identifikator zahteva — bez ožičenja po pozivu. | `[REG §4 · provenance · VERIFIED]` · `[REG §5 · vezivanje za predmet · PARTIALLY_VERIFIED]` **ograda doslovno:** „vezivanje za predmet zavisi od proširenja šeme (migracija 089) — bez njega se upisuje uži skup polja"; **ako proširenje nije potvrđeno na produkciji — cela stavka se izostavlja** |
| 8 | **Provere pri svakoj izmeni koda** | Testovi na istoj verziji Pythona koju koristi produkcija; više nezavisnih **unutrašnjih** bezbednosnih provera. | `[REG §4 · CI testovi · VERIFIED]` bez broja testova kao prodajnog argumenta · `[REG §4 · security scans · VERIFIED]` **isključivo „unutrašnjih"; nikad implicirati reviziju treće strane**; zabranjeno „svi testovi prolaze" |
| 9 | **Šta nemamo** | Nezavisna revizija — ne. Sertifikat — ne. Potvrda GDPR usklađenosti — ne. Izmerena tačnost — ne. „Potpuno bezbedno" — nikad. | `[REG §8 · UNVERIFIED lista]` — sekcija postoji **da bi te tvrdnje ostale nemoguće** |
| 10 | **Dokumenta** | Šest linkova + PDF. | `/bezbednosni-list` · PDF · `/security` · `/dpa` · `/privacy` · `/terms` · `/ai-disclosure` · `/status` |
| 11 | **CTA** | Tercijarni: „Preuzmite bezbednosni list (PDF)". Sekundarni: Beta. | — |

## 3.4 `/sposobnosti`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Uvod** | Pravilo: ovde je samo ono do čega korisnik danas stvarno dolazi u aplikaciji. | **OPISNA** |
| 2-9 | **Osam grupa** | Prijem i obrada spisa · Vođenje predmeta · AI analiza · Strategija · Izrada nacrta · Pretraga · Kancelarija · Platforma. | doslovno `[CAPABILITY_MAP §Sposobnosti koje sme da prikaže sajt]`, samo `PRODUCTION` |
| — | *ograda uz „Strategija"* | | `[REG §6 · EXPERIMENTAL]` — **isključivo kao „alati za preispitivanje sopstvenog predmeta"; nikad kao predviđanje ishoda ni verovatnoća** |
| — | *ograda uz „Izrada nacrta"* | | `[REG §5 · PARTIALLY_VERIFIED]` **doslovno:** „nacrt je polazna tačka, ne gotov podnesak" |
| — | *ograda uz „AI analiza"* | | `[REG §5 · procena rizika · PARTIALLY_VERIFIED]` **doslovno:** „pomoć u proceni, ne pravni savet" |
| — | *ograda uz „Pretraga"* | | `[REG §4 · semantička pretraga · VERIFIED]` — **ne vezivati za globalnu pretragu u aplikaciji** |
| 10 | **Šta nije uključeno** | Glasovni rad je van bete. Nema ekrana evidencije. Nema brisanja dokumenta. | `[REG §6 · glas EXPERIMENTAL]` · `[REG §9 · 7, 9]` |
| 11 | **CTA** | Beta. | — |

**Zabranjeno na ovoj stranici:** ijedan broj korpusa. Zatečeno stanje su dve
međusobno protivrečne vrednosti u istom proizvodu — „18 zakona RS"
(`landing.html:905`) i „847 zakona Srbije" (`index.html:4209`). Najmanje jedna
je netačna. Do provere korpusa nijedan broj ne ide na sajt.

## 3.5 `/za-advokate`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Uvod** | Četiri trenutka radnog dana, ne četiri funkcije. | **OPISNA** |
| 2 | **Nov spis u petak popodne** | Ceo folder ide odjednom; skenirano se pročita; rokovi se pojave bez komande; ujutru sve stoji u dnevnom pregledu. | `[REG §4 · batch + OCR + klasifikacija · VERIFIED]` · `[REG §4 · rokovi automatski · VERIFIED]` — **bez „nikad više propuštenih rokova"** |
| 3 | **Provera pitanja pre podneska** | Odgovor sa propisom i članom i oznakom pouzdanosti — ili, kad pouzdanog izvora nema, bez odgovora. | `[REG §4 · izvori · VERIFIED]` · `[REG §4 · pouzdanost · VERIFIED]` · `[REG §4 · odbijanje · VERIFIED]` |
| 4 | **Prvi nacrt** | Svaki citat nosi oznaku izvora; izmišljen broj člana se zamenjuje oznakom za proveru, nikad drugim brojem; svaki nacrt nosi napomenu da ga advokat mora pregledati. | `[REG §5 · nacrt · PARTIALLY_VERIFIED]` **ograda doslovno:** „nacrt je polazna tačka, ne gotov podnesak" |
| 5 | **Preispitivanje sopstvenog predmeta** | Napad na sopstveni predmet iz uloge protivnika. | `[REG §6 · EXPERIMENTAL]` — **isključivo „alati za preispitivanje sopstvenog predmeta"** |
| 6 | **Šta ovo ne zamenjuje** | Ne zamenjuje advokata, ne daje pravni savet, ne predviđa ishod. | `[REG §10 · zabranjene formulacije]` |
| 7 | **CTA** | Beta. | — |

## 3.6 `/tehnologija`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Model je komponenta, ne proizvod** | Kapija je vlasništvo platforme, ne pozivnog mesta. | `[REG §4 · VERIFIED]` |
| 2 | **Brojeve računa program** | Rizik, status, rok i spremnost računa deterministički kod; AI ih objašnjava. | `[CAPABILITY_MAP §Najjače 1]` **ograda:** „brojevi koje vidite računa program"; **zabranjeno „AI nikad ne presuđuje"** — ograničenje verdikta ne postoji na tri samostalne strategijske rute |
| 3 | **Pretraga po smislu** | Semantička pretraga nad propisima, praksom i mišljenjima, ne po ključnoj reči. | `[REG §4 · VERIFIED]` — ne vezivati za globalnu pretragu u aplikaciji |
| 4 | **Jedan dobavljač, ne tri** | Otvoreno: koristi se jedan dobavljač modela. Sloj za više dobavljača postoji i nije u upotrebi. | `[REG §7 · ROADMAP]` **ograda doslovno:** „implementirano; nijedna funkcija još ne ide kroz taj sloj" · **zabranjeno „koristimo GPT, Claude i Gemini", „automatski bira najbolji model", „unakrsna provera između modela"** |
| 5 | **Testovi na svakoj izmeni** | Ista verzija Pythona kao produkcija. | `[REG §4 · VERIFIED]` — bez broja testova, bez „svi testovi prolaze" |
| 6 | **CTA** | Beta. | — |

## 3.7 `/vizija`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Uvod** | Pravilo stranice: ništa ovde nije obećanje sa rokom. | **OPISNA** |
| 2 | **DANAS** | Tri rečenice i link na `/sposobnosti`. **Ne prepisuje inventar.** | pokazivač, ne tvrdnja |
| 3 | **U IZRADI** | Ono što radi uz imenovanu ogradu: uočavanje protivrečnosti između dokumenata, poreklo po polju, čuvanje originala. | `[REG §5 · PARTIALLY_VERIFIED]`, svaka sa svojom doslovnom ogradom — npr. protivrečnosti: „mehanizam postoji; kvalitet nije meren nad stvarnim predmetima" |
| 4 | **VIZIJA** | Četiri stavke, objašnjene **dijagramom, nikad snimkom nepostojećeg ekrana**. | `[REG §7 · ROADMAP]`: klik iz citata do teksta propisa · korisnički ekran nepromenljive evidencije · objašnjenje zašto je baš taj izvor izabran · rad sa više dobavljača modela |
| 5 | **Šta danas ne radi** | Konsolidovana lista, u četiri bloka. | `[REG §9]` — Poreklo odgovora (6) · Evidencija i kontrola (3) · AI i njegove granice (4) · Proizvod (2 od 4; stavke 16 i 17 su interne) |
| 6 | **CTA** | Beta. | — |

Stavka `[REG §7 · samouslužna kupovina pretplate]` **se ne pojavljuje ni ovde** —
registar je označava sa „NE", ne sa „samo Vizija".

## 3.8 `/beta`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
Struktura prati `FOUNDING_PARTNER.md` §9, spojenu u jednu stranicu sa jednom formom.

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Hero** | Šta beta jeste: zatvoreno testiranje, ne plaća se, nema roka koji obećavamo. | **OPISNA** — **bez konkretnog broja mesta**; veštačka oskudica je laž |
| 2 | **Zašto uopšte postoji** | Nemamo nijednog korisnika i tražimo prve — otvoreno. | **OPISNA** |
| 3 | **Founding Partner** (`#founding-partner`) | Šta program jeste: ograničen broj advokata koji rade na stvarnim predmetima i čije primedbe stižu direktno onome ko odlučuje. | `FOUNDING_PARTNER.md` §2-3 — sme „stižu direktno", **ne sme** „biće implementirane" |
| 4 | **Šta ne obećavamo** | Nema cene, popusta, doživotnog pristupa, zaključane cene, roka, SLA, ni tvrdnje o drugim učesnicima. **Sekcija je javna namerno.** | `FOUNDING_PARTNER.md` §4 · `[REG §9 · 14, 15]` · `[REG §10 · pominjanje cene ili plana]` |
| 5 | **Kome je namenjen** | Advokatu koji vodi predmete i spreman je da javi šta ne valja. | **OPISNA** |
| 6 | **Forma — jedna, za oba** | Četiri polja, dva obavezna. | v. §4.2 |
| 7 | **Poverenje pre slanja** | Kratki linkovi: Bezbednost · Politika privatnosti · Ugovor o obradi podataka. | — |

**Ton (`FOUNDING_PARTNER.md` §10):** bez odbrojavanja i „ostalo je još X mesta";
bez laskanja; prvo lice jednine — proizvod gradi jedna osoba, a „mi" je prva
stvar koju iskusan kupac prepozna kao lažnu.

## 3.9 `/kontakt`

| # | Sekcija | Šta radi | Tvrdnja |
|---|---|---|---|
| 1 | **Forma** | Tri polja: ime, e-pošta, poruka. | v. §4.4 |
| 2 | **Pravni identitet** | Naziv, PIB, matični broj, adresa, adresa e-pošte. | **BLOKIRANO** — `[REG §8]`: pravni identitet firme nije zapisan nigde u repozitorijumu, a adrese na postojećim javnim stranama koriste `vindex.ai` dok produkcija radi na `vindex.rs`. **Stranica se ne objavljuje dok osnivač ne dostavi ove podatke.** |
| 3 | **Linkovi** | Pravne stranice. | — |

---

# 4. CTA FLOW

## 4.1 Hijerarhija

| Nivo | Poziv | Vodi na | Površine |
|---|---|---|---|
| **Primarni** | Prijavite se za zatvoreno testiranje | `/beta` | dugme u navigaciji (svaka stranica) · hero početne · dno svake stranice |
| **Sekundarni** | Prijavite interesovanje *(Founding Partner)* | `/beta#founding-partner` | blok na `/beta` · jedan red u zaključnom CTA-u početne. Namerno **nije** „Postanite Founding Partner" — to bi impliciralo da je prijava dovoljna; ovo je razgovor, ne registracija (`FOUNDING_PARTNER.md` §5). |
| **Tercijarni A** | Preuzmite bezbednosni list (PDF) | `/static/Vindex-AI-Bezbednosni-List.pdf` | `/bezbednost` sekcija 11 · zaključni CTA početne · podnožje |
| **Tercijarni B** | Prijava (postojeći korisnik) | `/app` | navigacija · podnožje · uspešno stanje forme kada je nalog već aktivan |

**Zabranjeno kao CTA:** „Počnite besplatno" · „Zakažite demo" ·
„Kontaktirajte prodaju" · „15 upita bez kartice".

## 4.2 Beta forma — projektovana oko stvarnog endpointa

`POST /waitlist/prijava` (`routers/waitlist.py:143`), registrovan u
`api.py:745`, **bez autentifikacije**.

### Šta endpoint prima — model `WaitlistPrijava` (`waitlist.py:60-80`)

| Polje | Tip | Obavezno | Ograničenje | Polje u formi |
|---|---|---|---|---|
| `ime` | `str` | **da** | trimuje se; prazno → greška; `>120` znakova → greška | „Ime i prezime" — `required`, `maxlength=120` |
| `email` | `EmailStr` | **da** | validacija formata na serveru | „E-pošta" — `type=email`, `required`, `inputmode=email` |
| `firma` | `str` | ne (`""`) | trimuje se i **seče na 500** | „Kancelarija i grad (opciono)" — `maxlength=500` |
| `telefon` | `str` | ne (`""`) | isto | **ne koristi se** — v. ispod |
| `poruka` | `str` | ne (`""`) | isto | „Na kakvim predmetima biste ga koristili? (opciono)" — `maxlength=500` |

**Četiri polja, dva obavezna.** Forma šalje četiri ključa; `telefon` se ne šalje
i endpoint mu dodeljuje `""`.

**Zašto se `telefon` izostavlja iako endpoint može da ga primi:** u fazi bez
ijednog korisnika polje za telefon se čita kao najava prodajnog poziva i skuplje
je nego što vredi (isti zaključak nezavisno u `FOUNDING_PARTNER.md` §6). Isto
važi za veličinu kancelarije, vrstu prakse i „kako ste čuli za nas" —
kvalifikacija se dešava u razgovoru, ne u obrascu.

### Šta endpoint vraća

| Situacija | HTTP | Telo | Šta forma prikazuje |
|---|---|---|---|
| nova prijava | 200 | `{"ok":true,"poruka":"Prijava primljena! Javićemo vam se čim otvorimo pristup."}` | `poruka` sa servera, doslovno |
| e-pošta već na listi | 200 | `{"ok":true,"poruka":"Već ste na listi! Javićemo vam se uskoro."}` | `poruka` sa servera, doslovno |
| e-pošta ima nalog (`status="active"`) | 200 | `{"ok":true,"poruka":"Vaš nalog je već aktivan. Prijavite se!"}` | `poruka` **+ link ka `/app`** |
| neispravan unos | **422** | FastAPI `{"detail":[…]}` — **nema ključa `poruka`** | sopstvena poruka iz `detail[0].msg`, uz fokus na polje |
| prekoračen limit | **429** | JSON iz `_json_rate_limit_handler` (`api.py:568`) | „Previše pokušaja. Pokušajte kasnije." |
| pad baze | **500** | oko `insert`-a nema `try/except` (`waitlist.py:163-171`) | opšta greška + `mailto` alternativa |

**Pravilo:** poruku o uspehu piše server, ne forma. Tri poruke nose različito
značenje i treća zahteva drugačiji sledeći korak.

### Šta forma NE sme da traži

Utvrđeno čitanjem koda, ne pretpostavkom:

1. **Nijedno polje van pet gore.** `WaitlistPrijava` ne podiže `extra="forbid"`,
   pa je Pydantic podrazumevano **tiho odbacuje**. Polje „vrsta prakse",
   „veličina kancelarije" ili čekboks „Founding Partner" bi se poslalo, vratilo
   `200 OK`, i **nestalo bez traga**. Osnivač bi u `GET /waitlist/admin/lista`
   video red koji se ni po čemu ne razlikuje.
2. **Nijedan čekboks saglasnosti se ne čuva.** U tabeli `waitlist` nema kolone za
   pristanak. Saglasnost stoji kao **tekst iznad dugmeta** („Slanjem prijave
   prihvatate Politiku privatnosti") sa linkom ka `/privacy`. Čuvani čekboks bi
   tražio izmenu šeme — nije predmet ove faze.

### Kako se razlikuju dva toka na jednom endpointu

Founding Partner **nema sopstvenu formu i nema sopstveni prefiks** — nije izbor u
obrascu nego ishod razgovora, pa nema šta da se zabeleži. Razlikuju se samo dva
toka, a jedini nosilac razlike bez izmene produkcionog koda je `poruka`:

| Forma | Prefiks u `poruka` | Preostali budžet |
|---|---|---|
| Prijava za betu (`/beta`) | `[BETA]` | 494 znaka |
| Kontakt (`/kontakt`) | `[KONTAKT]` | 491 znak |

Polje `poruka` se seče na **500 znakova ukupno**, uključujući prefiks — brojač
znakova u formi mora računati prefiks, inače korisnikov tekst tiho gubi kraj.

## 4.3 Šta se dešava posle slanja

Bez preusmeravanja. Forma se zamenjuje stanjem uspeha **na istom mestu**:

1. Poruka sa servera, doslovno.
2. Jedna rečenica šta sledi: **„Javljam se lično. Nema automatskih poruka."**
   Istinita je (onboarding automatika ne postoji) i postavlja tačno očekivanje.
   **Zabranjeno:** „odgovaramo u roku od 24 sata" — to je SLA koji niko ne meri.
3. Jedan sledeći korak — **„Preuzmite bezbednosni list (PDF)"**, jer je to jedina
   stvar koju posetilac može odmah da dobije. Kada je poruka „Vaš nalog je već
   aktivan", sledeći korak je umesto toga **„Prijavite se" → `/app`**.

Preusmeravanje na stranicu zahvalnosti se ne pravi: gubi kontekst, a analitike
koja bi ga opravdala nema (CSP ne dozvoljava eksternu analitiku).

## 4.4 Kontakt forma

Isti endpoint, tri polja (`ime`, `email`, `poruka` sa prefiksom `[KONTAKT]`);
`firma` i `telefon` se ne šalju. Ovo je jedini razlog zbog kog je `/kontakt`
uopšte izvodljiv bez izmene backenda — model `WaitlistPrijava` traži samo `ime` i
`email`, a `poruka` prima do 500 znakova.

**Posledica koja se mora prijaviti osnivaču:** kontakt poruke ulaze u istu tabelu
`waitlist` i istu admin listu kao prijave za betu. Jedina razlika je prefiks u
`poruka`. Kad se pojavi pravi kontakt kanal, ovo se razdvaja.

---

# 5. KORISNIČKO PUTOVANJE

## 5.1 Advokat koji prvi put čuje za Vindex → prijava za Betu

| Korak | Gde je | Šta se dešava |
|---|---|---|
| 0 | dolazak na `/` | hero: „Odgovor sa navedenim propisom. Ili nikakav odgovor." |
| 1 | `/` §2-4 | Problem ga prepozna; „Zašto verovati" odgovara na „šta ako izmisli" **pre** nego što je pitao |
| 2 | `/` §5 | „Šta radi danas" — traži svoj posao u šest grupa |
| 3 | `/` §7 | „Stanje" — sazna da nema korisnika i da tačnost nije merena, **pre** nego što klikne |
| 4 | klik CTA | → `/beta` |
| 5 | `/beta` §6 | četiri polja, dva obavezna |
| 6 | slanje | stanje uspeha na mestu forme + bezbednosni list kao sledeći korak |

**Klikova: 2** (CTA + Slanje) ako veruje heroju. **Realno 3-4** — većina svrati
na `/kako-radi` ili `/sposobnosti` pre `/beta`.

**Gde odustaje:**
- **Hero, prvih pet sekundi** — ako druga rečenica ne kaže šta proizvod radi. Ovo
  je najskuplja tačka i nosi je jedna rečenica.
- **§5 „Šta radi danas"** — ako ne vidi svoju vrstu prakse. Zato šest grupa, a ne
  četrdeset stavki: lista se skenira, grupa se prepozna.
- **§7 „Stanje"** — deo posetilaca odustane ovde. To je namerno; alternativa je da
  odustanu posle prijave, kada ih je skuplje izgubiti.
- **Svako polje preko četiri** — telefon, veličina kancelarije, vrsta prakse i
  padajuće liste čitaju se kao kvalifikacija pred prodajni poziv. Zato ih nema;
  v. §4.2.
- **Posle slanja** — ako stanje uspeha nema sledeći korak, poseta se završava na
  praznom ekranu.

## 5.2 Oprezan kupac koji prvo proverava bezbednost → bezbednosni list

| Korak | Gde je | Šta se dešava |
|---|---|---|
| 0 | `/` ili bilo koja stranica | ne čita hero — traži „Bezbednost" u navigaciji |
| 1 | klik „Bezbednost" | → `/bezbednost` |
| 2 | §2-8 | mehanizmi, svaki sa ogradom |
| 3 | §9 „Šta nemamo" | nezavisne revizije nema — **rečeno pre nego što pita** |
| 4 | §10-11 | klik „Preuzmite bezbednosni list (PDF)" |

**Klikova: 2.** Sa bilo koje stranice preko podnožja (kolona „Poverenje") —
**1 klik**, jer podnožje linkuje i PDF direktno.

**Gde odustaje:**
- **Prva sekcija `/bezbednost`** — ako počne superlativom. Ovaj profil traži
  ograde; „potpuno bezbedno" ga tera, ne privlači.
- **§9 na pogrešnom mestu** — ako „nemamo nezavisnu reviziju" dođe kao iznenađenje
  na dnu posle osam sekcija hvale, čita se kao skrivanje. Zato je uvod (§1) već
  najavljuje.
- **DPA iza forme** — `/dpa` mora biti dostupan bez ijednog polja. Za B2B kupca
  to je blokator.
- **Ovaj put mora raditi bez JavaScript-a.** Nijedan korak nije forma; sve su
  obični `<a>` linkovi.

## 5.3 Postojeći korisnik → aplikacija

| Korak | Gde je | Šta se dešava |
|---|---|---|
| 0 | bilo koja stranica sajta | „Prijava" gore desno, tekstualni link |
| 1 | klik | → `/app` |
| 2 | `/app` | pre-auth ekran (`index.html:4166`) dok Supabase sesija ne postoji |
| 3 | klik „Prijava" na tom ekranu | `openModal()` → unos podataka |

**Klikova do `/app`: 1. Do modala: 2.**

**Gde odustaje:**
- **Ako je „Prijava" stilizovana kao dugme** — meša se sa Beta CTA-om i postojeći
  korisnik klikne pogrešno. Zato tekst, ne dugme.
- **Učitavanje `/app`** — 422 KB HTML plus oko 2 MB JS/CSS. Na mobilnoj mreži je
  to primetna pauza, a sajt je do tada bio trenutan. Ovo se ovom fazom **ne
  rešava**; samo se ne pogoršava time što bi „Prijava" vodila kroz međustranicu.
- **Service Worker** — `sw.js` ima scope `/` i keširа svaku uspešnu HTML
  navigaciju. Posetilac koji je video stari `/` može ga dobiti iz keša.
  **`CACHE_NAME` (`static/sw.js:4`) mora porasti u istom commit-u kao zamena
  landinga**, iako to nijedan test ne traži (`FRONTEND_ARTEFAKTI` ne sadrži
  `landing.html`).

---

# 6. MOBILNA STRUKTURA

Tačke preloma: **480 / 768 / 1024**. Nasleđuju se iz `landing.html` (`:664`,
`:675`, `:728`), koji je u tome interno dosledan. Aplikacija koristi 640 kao
primarni, ali sajt **ne deli nijedan CSS fajl sa aplikacijom** — usklađivanje na
640 ne bi donelo ništa, a 768 je ispravna granica za navigaciju od pet stavki.

| Sekcija | ≥1024 | 768-1024 | ≤768 | ≤480 |
|---|---|---|---|---|
| **Navigacija** | 5 stavki + Prijava + dugme | isto, uži razmaci | **hamburger** → drawer sa **identičnim** stavkama | isto |
| **Lepljivi CTA** | — | — | traka pri dnu: „Prijavite se za betu" | isto, **bez glow senke** |
| **Hero — tekst** | H1 + podnaslov + 2 dugmeta u redu | isto | dugmad **jedno ispod drugog**, puna širina | isto, H1 na donjoj granici `clamp` |
| **Hero — SVG dijagram** | vodoravno, pored teksta | vodoravno, ispod teksta | **rotira se u uspravni tok**, ne skroluje se | isto, grana „ili ćutanje" ostaje vidljiva |
| **Kako radi (4 koraka)** | 4 kolone, vodoravna spojnica | 2×2 | 1 kolona, spojnica rotirana za 90° | isto |
| **Zašto verovati (3 kartice)** | 3 kolone | 3 kolone | 1 kolona | 1 kolona |
| **Šta radi danas (6 grupa)** | 3×2 | 2×3 | 1 kolona | `<details>`, prva otvorena |
| **Sposobnosti (8 grupa × ~7 stavki)** | 2 kolone | 2 kolone | 1 kolona | **`<details>` po grupi, sve zatvorene osim prve** |
| **Tabele (Vizija, poređenja)** | pune | pune | **prelamaju se u složene parove naziv/vrednost** | isto |
| **Duge liste ograda** | pune | pune | pune — **nikad se ne sklanjaju** | pune |
| **Forme** | 1 kolona, 480px | isto | puna širina, `font-size:16px` (sprečava zumiranje na iOS-u) | isto |
| **Podnožje** | 5 kolona (`1.6fr 1fr 1fr 1fr 1fr`) | 3 kolone | 2 kolone | 1 kolona |
| **Podnožje — Pravno i Poverenje** | vidljivo | vidljivo | **vidljivo, nikad u `<details>`** | isto |

**Tvrda pravila:**

1. **Vodoravni skrol je dozvoljen na tačno jednom mestu — ni na jednom.** Nijedna
   sekcija ne postaje vodoravni skrol. Dijagram koji se mora skrolovati da bi se
   razumeo nije dijagram. Tabele se prelamaju, ne skroluju.
2. **Sekcije „Šta ne radi", „Šta nemamo" i sve ograde ostaju vidljive na
   telefonu.** Sklanjanje ograde u akordeon na malom ekranu je skrivanje ograde.
3. **Dekorativni canvas se ne prenosi.** Zatečeni landing ima dve trajne
   `requestAnimationFrame` petlje bez zaustavljanja, bez `IntersectionObserver`-a
   i bez `prefers-reduced-motion` gejta, uz `O(n²)` petlju preko 60 čestica —
   stalan trošak baterije. Novi sajt ih nema.
4. **`prefers-reduced-motion: reduce` gasi svaku animaciju.** Zatečeno stanje: 0
   blokova u `landing.html`, 0 u `index.html`.
5. **`:focus-visible` mora postojati.** `landing.html:46` ima
   `button { outline: none; }` bez zamene — sajt je danas nenavigabilan
   tastaturom bez vidljivog fokusa.
6. **Cilj dodira minimum 44×44px** za svaku stavku drawer-a i svako dugme forme.

---

# 7. ŠTA NAMERNO NE PRAVIMO

| Ne pravimo | Razlog |
|---|---|
| **Cenovnik** | Nijedan plan se ne može kupiti — `STRIPE_URL` je prazan; besplatni krediti se dodeljuju jednom i ne obnavljaju; SLA se nigde ne meri. Uz to se **uklanja ruta `/pricing`**, koja je preživela uklanjanje sekcije i danas je javna. |
| **Blog** | Nema šta da se objavi što nije već tvrdnja iz registra. Blog bez ritma je mrtav ugao koji stari brže od proizvoda i postaje drugi izvor tvrdnji van registra. |
| **„O nama"** | Pravni identitet firme nije zapisan nigde u repozitorijumu — ni u `landing.html`, ni u `terms.html`, ni u `privacy.html`. Stranica bi morala biti izmišljena. Ono malo što je istinito staje u jedan red podnožja. |
| **Industrije / vertikale** | Nema nijednog korisnika, pa ni jedne prakse za koju bi se tvrdilo da je pokrivena bolje od druge. Advokatura je jedina primena. |
| **Engleska verzija** | Proizvod pokriva propise Republike Srbije. Engleski sajt privlači posetioce kojima proizvod ne služi, i udvostručuje površinu na kojoj tvrdnja može da odluta od registra. |
| **Preporuke korisnika, logotipi, studije slučaja** | Nema nijednog korisnika, klijenta ni pilota. Registar ih vodi kao `FALSE`. |
| **FAQ** | Sadržaj bi bio lista „šta ne radi", a ona ima vlasnika (`/vizija`) i inline ograde. Treći vlasnik istog sadržaja je fragmentacija. |
| **Kancelarijsko znanje (stranica)** | 49 ruta u šest modula bez ijednog poziva iz frontenda. |
| **Governance (zasebna stranica)** | Sve tvrdnje već pripadaju `/bezbednost`; sopstvene korisničke površine nema. |
| **Snimci proizvoda i mockup ekrani** | Nijedan snimak proizvoda ne postoji; najvažniji (`provenance.png`) ne može se napraviti bez sintetičkog predmeta, koji ne postoji. Mockup ekrana koji ne postoji je zabranjen izričito. Sve stoji na SVG dijagramima. |
| **Demo video / „Zakažite demo"** | CSP nema `frame-src` ni `media-src` → nema YouTube ni Vimeo ugradnje; self-hostovan video troši propusni opseg servera. Uz to nema šta da se snimi. |
| **Bilo koji broj korpusa** | „18 zakona RS" i „847 zakona Srbije" žive istovremeno u istom proizvodu. Najmanje jedan je netačan. |
| **Bilo koji procenat, mera vremena ili brzine** | Nikad izmereno; okvir za merenje je prazan šablon od 2026-07-23. |
| **Analitika posete** | CSP `connect-src` ne dozvoljava GA/Plausible/PostHog. Merenje bi tražilo izmenu bezbednosne politike zbog marketinga — pogrešna zamena na sajtu koji prodaje poverenje. |
| **Bilten / newsletter** | Druga sabirna tačka pored Bete deli pažnju i ne postoji kanal koji bi je opsluživao. |
| **Ćaskanje uživo / chat widget** | Eksterni widget je nemoguć po CSP-u, a sopstveni ne postoji. |

---

# 8. BLOKATORI ZA IMPLEMENTACIJU

Nijedan se ne može zatvoriti čitanjem koda.

| # | Blokator | Koga zaustavlja |
|---|---|---|
| B1 | **Pravni identitet firme** (naziv, PIB, matični broj, adresa) nije nigde zapisan | `/kontakt` §2 — stranica se ne objavljuje bez toga |
| B2 | **Kanonički domen** — `vindex.rs` · `vindex-ai.com` · `vindex.ai` su svi u kodu | podnožje svake stranice, adresa e-pošte, `rel=canonical`, `og:` oznake |
| B3 | ~~Sadržaj ponude za Founding Partner~~ — **ZATVORENO**. `FOUNDING_PARTNER.md` daje sadržaj koji ne traži nijednu poslovnu odluku: javna formulacija je „Uslovi za Founding Partnere biće definisani pre nego što se otvori komercijalni model. Dogovaraju se direktno, ne preko cenovnika." Konkretni uslovi ostaju `ODLUKA VLASNIKA` i **ne pominju se**, što stranicu ne blokira. | — |
| B4 | **Migracija 089 na produkciji** — ako nije potvrđena, tvrdnja o vezivanju AI poziva za predmet se **izostavlja** | `/bezbednost` §7 |
| B5 | **SMTP promenljive na produkciji** — ako nedostaju, obaveštenje o prijavi se tiho preskače (`waitlist.py:91-93`) i osnivač saznaje za prijave samo ručnom proverom admin liste | ceo tok Bete |

---

# 9. TEHNIČKE OBAVEZE PRI IMPLEMENTACIJI

Izvedeno iz `VINDEX_WEBSITE_ARCHITECTURE.md` §8; ovde samo ono što informaciona
arhitektura direktno dodiruje.

1. **`CACHE_NAME` u `static/sw.js:4` mora porasti** u istom commit-u kao zamena
   landinga. Nijedan test to ne traži, a Service Worker keširа `/`.
2. **Svi linkovi ka `/app` idu na `/app`, nijedan na `/app#register`.**
3. **`href="#"` ne postoji nigde.** Svaki link vodi na postojeću rutu.
4. **Nijedna slika sa spoljnog hosta.** `img-src 'self' data: blob:`.
5. **`--tx-3` se ne koristi za tekst** (2,44:1, pada AA).
6. **PDF bezbednosnog lista** (`static/Vindex-AI-Bezbednosni-List.pdf`, 94 KB)
   **danas nije linkovan ni sa jedne stranice** — pretraga po `.html`, `.js` i
   `.py` daje nula referenci. Novi sajt ga linkuje sa `download`.
7. **Nijedan ključ ni niska nalik ključu u HTML-u** — `secret-scan` je blokirajući
   i već crven zbog istorijskog nalaza, pa se crven CI ne sme koristiti kao signal.
8. **`landing.html` ne prolazi kroz `?v=` prepisivanje** (`api.py:1503-1505`
   čita fajl direktno). Ostati na inline `<style>`/`<script>` ili verzionisati ručno.
9. **`robots.txt` nema `Sitemap:`** (`api.py:2331-2333`) — sa devet novih stranica
   to postaje propust, a ne sitnica.

---

*Kraj dokumenta. Nijedan produkcioni fajl nije menjan.*
