# Vindex AI — Trust Layer v1 Implementation Design Plan (2026-07-19)

**Uloga i ograničenje ovog dokumenta:** ovo je implementacioni DIZAJN
PLAN, ne implementacija. Nema koda. Ne menja arhitekturu. Ne dodaje
module. Direktan nastavak `VINDEX_TRUST_LAYER_ANALYSIS.md`, strukturiran
po founderovom masterprompt-u i tri-talasnom redosledu koji je sam
predložio (Faza 1→P0, Faza 2→P1, Faza 3→P2).

**Nepromenljiva pravila za sve stavke ispod (founderova, direktan
citat):**
1. Ne dodavati funkciju ako podatak već ne postoji.
2. Ne uvoditi source/citation ako backend nema pouzdanu vezu.
3. Nikad ne prikazivati AI kao autoritet.
4. Advokat ostaje finalni donosilac odluke.
5. Bolje bez izvora nego lažni izvor.
6. Evidence summary, ne reasoning trace — nikad "AI je razmatrao
   korak po korak...".

---

## Deo A — Analiza pre predloga

### A1. Smart Intake — gde postoje confidence score-ovi, gde se mogu prikazati

Tri odvojena confidence signala postoje u `shared/intake_documents.py` i
već stižu u frontend API odgovor (`routers/smart_intake.py:187-208`):

| Signal | Format | Stiže do frontenda već danas? | Stvarno mereno ili konstanta? |
|---|---|---|---|
| `entiteti[].confidence` (po entitetu) | 0.0-1.0 | **DA** — `routers/smart_intake.py:191`, `e.confidence` postoji u `_siRenderResult` objektu (`vindex.js:19634`), samo se ne prikazuje | Stvarno mereno (izlaz iz ekstrakcionog modela) |
| `dokument.tip_pouzdanost` (klasifikacija tipa dokumenta) | 0.0-1.0 | **DA** — `routers/smart_intake.py:200` | Stvarno mereno |
| `ocr_confidence` | 0.0-1.0 ili null | **NE stiže u ovaj odgovor** (nije u `dokument` dict-u, `routers/smart_intake.py:198-202`) | **NIJE stvarno mereno** — potvrđeno u kodu: `shared/intake_worker.py:165` postavlja `0.0` (heuristički put) ili `shared/intake_worker.py:181` postavlja **fiksnu konstantu 0.6** kad je OCR korišćen, sa komentarom u samom kodu koji to priznaje: "OCR bez eksplicitnog skora danas — konzervativna fiksna vrednost dok extractor ne vraća pravi confidence" |

**UX obrazac koji najmanje povećava kognitivno opterećenje:** postojeći
"Analiza dokumenta" blok u `_siRenderResult()` (`vindex.js:19643-19646`,
"Prepoznat tip dokumenta") već ima namensko mesto — dodavanje procenta
pored postojeće labele, i procenta pored svakog entiteta u već
postojećoj listi (`vindex.js:19648-19662`), ne dodaje NOVU sekciju,
samo obogaćuje POSTOJEĆI red teksta. Net-novih UI elemenata: nula,
samo dodat broj u postojeći red — isti obrazac kao P0-5 "šta uklanjamo"
disciplina iz prethodne UX runde.

### A2. Case Genome — koje tvrdnje već imaju dokaz, koje nemaju, šta može odmah postati explainable

Iz `_GENOME_SYSTEM` šeme (`routers/case_dna.py:38-115`), potvrđeno u
`VINDEX_TRUST_LAYER_ANALYSIS.md` Deo 2:

**Već imaju dokaz (dokument-nivo referenca u šemi):**
- `kontradikcije[].lokacija_1/lokacija_2` — traži "DOK-01 str.X ili opis"
- `dokazi_rang[].redni_broj` — povezuje ocenu sa `DOK-XX`

**Nemaju NIKAKAV dokaz u šemi (čist slobodan tekst):**
- `najslabija_tacka.rizik` / `.preporuka`
- `snaga_faktori[].opis`
- `strategija.*` (ceo blok)
- `nedostaje[].opis`, `zakljucak`, `upozorenja[]`

**Šta može ODMAH postati explainable, bez GPT/šema izmene (čist
frontend rad):** kontradikcije i dokazi_rang — podatak već postoji,
samo nije vizuelno istaknut kao "izvor". Sve ostalo zahteva prompt
izmenu (videti P1-3 ispod) jer podatak prosto ne postoji.

### A3. Verification — kako prikazati šta je provereno, kako prikazati ograničenja

`shared/genome_validator.py`'s `verify_genome()` interno radi TAČNO 5
odvojenih provera, svaka sa jasnom kategorijom (potvrđeno u kodu):

1. `_validate_dokazi_rang` — da li referencirani dokazi postoje
2. `_validate_kontradikcije_lokacije` — da li lokacije kontradikcija
   postoje među dokumentima
3. `_validate_relevantni_zakoni` — da li navedeni zakoni postoje u
   poznatoj listi (soft provera)
4. `_validate_snaga_konzistentnost` — da li se procenat slaže sa
   faktorima
5. `_validate_clan_brojevi` — da li brojevi članova zakona deluju
   realno

Trenutni frontend prikaz (`vindex.js`, "AI Provera" red) sažima svih 5 u
JEDAN DA/NE rezultat (`ver.odluka`) plus ravnu listu `hard_flags`+
`soft_flags` bez kategorije. **Kategorizacija po ovih tačno 5 provera je
već implicitno u backend kodu (koja funkcija je generisala koji flag) —
samo nije prenesena do frontenda kao grupa.** Ovo je ključan nalaz za
P0/P1 predlog ispod: grupisanje po kategoriji je NIZAK effort jer
kategorija već postoji u kodu, samo treba da putuje kroz payload.

**Kako prikazati ograničenja (bez lažnog utiska potpunosti):** svaka od
5 provera je binarna "izvršena/nije" po prirodi funkcije (ili se
izvrši i vrati rezultat, ili baci exception i biva tiho preskočena —
`verify_genome()` dokumentovano "Known Reliability Risk", videti
`KNOWN_RELIABILITY_RISKS.md`). Trust Layer prikaz MORA razlikovati
"provereno, nema problema" od "nije provereno" — trenutno to ne radi
(oba izgledaju kao "odluka: approve"). Ovo je već zapisano kao otvoren
rizik, van obima ove implementacione runde (zahteva backend izmenu
`verify_genome()` povratne vrednosti, ne samo frontend).

---

## Deo B — TRUST LAYER v1 predlog

### P0 — Smart Intake Confidence Exposure (obavezno, Faza 1)

#### P0.1 — Entity-level confidence brojevi vidljivi

- **Problem:** `⚠` binarna ikonica ne razlikuje 89% od 45% pouzdanosti
  — advokat ne zna KOLIKO da sumnja.
- **Podatak:** `entiteti[].confidence` (0.0-1.0).
- **Backend lokacija:** NEMA IZMENE — `routers/smart_intake.py:191`
  već vraća polje.
- **Frontend lokacija:** `_siRenderResult()` (`vindex.js:19648-19662`)
  — dodati `Math.round(e.confidence*100)+'%'` pored svakog entiteta,
  pored ili umesto `⚠`.
- **Rizik:** Nizak — čist prikaz postojećeg izmerenog broja.
- **Procena vremena:** 2-3 sata.
- **Kako meri uspeh:** Rule C — pratiti da li se broj ručnih ispravki
  entiteta menja kad advokat vidi tačan procenat naspram trenutnog
  binarnog stanja (hipoteza: manje nepotrebnih provera na visoko-
  pouzdanim poljima, više pažnje na stvarno niska).

#### P0.2 — Klasifikacija dokumenta confidence vidljiva

- **Problem:** Advokat ne zna da li je sistem siguran u prepoznat tip
  dokumenta (npr. "Tužba") ili je pogodio nasumično.
- **Podatak:** `dokument.tip_pouzdanost` (0.0-1.0).
- **Backend lokacija:** NEMA IZMENE — `routers/smart_intake.py:200`.
- **Frontend lokacija:** `_siRenderResult()` (`vindex.js:19643-19646`),
  isti blok kao P0.1, raditi zajedno.
- **Rizik:** Nizak.
- **Procena vremena:** 1 sat (dodatak na P0.1).
- **Kako meri uspeh:** isto kao P0.1, praćeno za tip-dokumenta polje
  specifično.

#### P0.3 — OCR confidence: NE prikazivati u v1, eksplicitna odluka

- **Problem:** Ne postoji stvaran problem za rešavanje — ovo je
  eksplicitna ISKLJUČENOST, ne implementaciona stavka.
- **Podatak:** `ocr_confidence` je HARDKODOVANA KONSTANTA (0.0 ili
  0.6), ne izmerena vrednost — potvrđeno u `shared/intake_worker.py:
  165,181`, sa komentarom u samom kodu koji to priznaje.
- **Backend lokacija:** N/A dok extraktor ne počne da vraća pravi
  confidence po dokumentu.
- **Frontend lokacija:** N/A.
- **Rizik:** VISOK ako se implementira sada — prikazivanje fiksne
  konstante kao "OCR: 60%" bi izgledalo kao izmerena preciznost, a nije.
  Ovo je tačno scenario koji Pravilo 5 ("bolje bez izvora nego lažni
  izvor") zabranjuje.
- **Procena vremena:** 0 (ne raditi sada). Preduslov za buduću verziju:
  OCR extraktor mora vraćati stvaran per-dokument confidence — poseban,
  veći zadatak, van ovog plana.
- **Kako meri uspeh:** N/A.

#### P0.4 — Sažet status red za ceo dokument ("Potrebna provera")

- **Problem:** Nema jednog sabranog signala na vrhu — advokat mora
  skrolovati kroz svaki entitet da vidi da li nešto treba pažnju.
- **Podatak:** `potrebna_provera.razlog` / `.polja` — VEĆ u API
  odgovoru (`routers/smart_intake.py:204-207`), izvedeno iz postojećih
  polja, ne novi backend poziv.
- **Backend lokacija:** NEMA IZMENE.
- **Frontend lokacija:** `_siRenderResult()`, dodati summary red na
  vrhu, pre liste entiteta.
- **Rizik:** Nizak.
- **Procena vremena:** 1 sat.
- **Kako meri uspeh:** kvalitativno — beta feedback da li advokat
  brže identifikuje dokumente koji traže pažnju.

**P0 ukupna procena: ~5-6 sati rada, nula backend izmena za P0.1/P0.2/
P0.4, P0.3 eksplicitno isključen iz obima.**

---

### P1 — Genome Evidence Visibility (Faza 2, oprezniji pristup)

#### P1.1 — Kontradikcije "Osnov" — istaknutiji prikaz postojećeg podatka

- **Problem:** `lokacija_1/lokacija_2` već postoji ali je sitno
  prikazan, lako se previdi kao izvor.
- **Podatak:** već postoji (`routers/case_dna.py:72`).
- **Backend lokacija:** NEMA IZMENE za prikaz. Opciona sitna izmena
  STROGIH PRAVILA u `_GENOME_SYSTEM` — eksplicitno dodati: "Ako tačna
  lokacija (dokument+strana) nije jasna iz teksta, ostavi `opis`
  granu praznu — ne izmišljaj stranu." (1 rečenica, nulti arhitektonski
  rizik, samo pojačava postojeće "STROGA PRAVILA: nikad ne izmišljaj".)
- **Frontend lokacija:** `_caseDnaRender`, kontradikcije sekcija —
  dodati eksplicitnu labelu "Osnov:" ispred `[DOK-01↔DOK-02]` teksta.
- **Rizik:** Nizak za prikaz; nulti za prompt pojačanje (dodavanje
  "ne izmišljaj" pravila nikad ne povećava rizik).
- **Procena vremena:** ~2 sata.
- **Kako meri uspeh:** Rule C — brojati % kontradikcija sa konkretnom
  DOK-XX str.Y lokacijom naspram generičkog opisa, pre/posle prompt
  pojačanja, na regresionom skupu (6 sintetičkih predmeta već postoje).

#### P1.2 — Dokazi rang "DOK-XX" — istaknutiji prikaz postojećeg podatka

- **Problem:** isti obrazac kao P1.1, za `dokazi_rang`.
- **Podatak:** već postoji (`routers/case_dna.py:90`).
- **Backend lokacija:** NEMA IZMENE.
- **Frontend lokacija:** `_caseDnaRender`, "RANGIRANA EVIDENCIJA" sekcija
  — preurediti "DOK-07" iz sitnog prefiksa u eksplicitan "Osnov:" red.
- **Rizik:** Nizak.
- **Procena vremena:** ~1-2 sata.
- **Kako meri uspeh:** kvalitativno — beta feedback, da li advokat
  sam prepoznaje DOK-XX kao izvor bez dodatnog objašnjenja.

#### P1.3 — "Najslabija tačka" i "Snaga faktori" dobijaju `osnov` polje — VIŠI RIZIK, zahteva regresiono testiranje

- **Problem:** trenutno nula osnova u šemi — tačan primer koji je
  founder naveo ("Zastarelost potraživanja" bez ičega iza).
- **Podatak:** NE POSTOJI — mora se DODATI u `_GENOME_SYSTEM` šemu.
  Founderov predlog implementacije (direktan citat principa): `osnov`
  ne sme biti nov nezavisan citat (rizik izmišljanja), nego kratka
  SAMO-REFERENCA na polja koja GPT već generiše u ISTOM odgovoru
  (`datumi_kljucni`, `pravna_teorija.relevantni_zakoni`,
  `rokovi_kriticni`) — npr. `"osnov": ["poslednja uplata 12.03.2022 (iz
  datumi_kljucni)", "ZOO čl. 371 (iz relevantni_zakoni)"]`. Ovo smanjuje
  rizik jer GPT ne izmišlja NOVU činjenicu, nego ukrštа sa onim što je
  već committed u istom pozivu.
- **Backend lokacija:** `_GENOME_SYSTEM` šema, `najslabija_tacka` i
  `snaga_faktori[]` objekti (`routers/case_dna.py:77-80,93-97`) —
  dodati `osnov` polje sa eksplicitnim STROGIM PRAVILOM: "osnov: 2-4
  kratke reference na POSTOJEĆE stavke iz OVOG istog odgovora
  (datumi_kljucni, relevantni_zakoni, rokovi_kriticni). NIKAD ne
  navoditi stranu dokumenta ako nije eksplicitno pomenuta u tekstu.
  Prazna lista je ispravan odgovor ako osnov nije jasan — NIKAD ne
  nagađaj."
- **Frontend lokacija:** `_caseDnaRender`, "NAJSLABIJA TAČKA" i "ZAŠTO
  X%" sekcije — dodati "Osnov:" listu ispod postojećeg teksta, SAMO
  ako `osnov` nije prazan (ako je prazan, ne prikazivati ništa — isti
  princip kao `_verifikacija` odsustva).
- **Rizik:** **Srednji — jedino mesto u celom v1 planu gde GPT dobija
  NOV generativni zadatak**, ne samo re-prikaz postojećeg. Realan
  rizik izmišljanja ako STROGO PRAVILO ne bude dovoljno jako, čak i uz
  self-referencu tehniku. Mora proći isti proces kao Genome Verification
  Layer u Fazi 1.3: dizajn beleška → implementacija → testiranje na
  regresionom skupu (6 sintetičkih predmeta, `genome_synthetic_cases.py`)
  → poređenje pre/posle PRE puštanja na prave korisnike.
- **Procena vremena:** ~1 dan (prompt izmena + regresiono testiranje +
  frontend render), veće od P0/P1.1/P1.2 zbog testiranja koje princip
  zahteva.
- **Kako meri uspeh:** Rule C, obavezno — ručna provera na regresionom
  skupu: da li se ijedan `osnov` unos odnosi na nešto što STVARNO NE
  postoji u ulaznim dokumentima tog test predmeta (halucinacija-test),
  pre/posle. Ako se nađe makar jedan slučaj izmišljanja, stavka se ne
  pušta dok se prompt ne pooštri dalje.

**P1 ukupna procena: ~4-5 sati za P1.1/P1.2 (nizak rizik), +1 dan za
P1.3 (srednji rizik, zahteva regresiono testiranje). Preporuka: P1.1 i
P1.2 mogu ići odmah posle P0; P1.3 čeka da se P0/P1.1/P1.2 dokažu prvo,
po istoj disciplini faznog zaustavljanja korišćenoj kroz ceo projekat.**

---

### P2 — "Kako AI razmišlja" — evidence summary format (Faza 3)

**Eksplicitna negativna specifikacija, ne implementaciona stavka:**
nijedna stavka u ovom ili budućem Trust Layer radu ne sme dodati
reasoning-trace tekst tipa "AI je razmatrao A, B, C..." — Pravilo 6.
Ovo se upisuje ovde kao trajna ograda za dizajn, ne kao P0/P1/P2 red sa
effort/rizikom.

#### P2.1 — Standardizovan "Zaključak / Na osnovu / Sigurnost" prikaz

- **Problem:** trenutni prikaz najslabije tačke i faktora snage je
  linearan tekst — nema vizuelnu strukturu koja razdvaja ZAKLJUČAK od
  OSNOVA od POUZDANOSTI, kako founder traži.
- **Podatak:**
  - ZAKLJUČAK — već postoji (`najslabija_tacka.rizik`, `snaga_faktori[].
    faktor`).
  - NA OSNOVU — dolazi iz P1.3 `osnov` polja (zavisan od te stavke).
  - SIGURNOST — **predlog: koristiti POSTOJEĆI `genome_kompletnost`
    (visoka/srednja/niska) kao globalnu oznaku pouzdanosti za CEO
    Genome**, ne granularnu po-tvrdnji vrednost. Ovo je pošteno (ne
    izmišlja preciznost koja ne postoji) i zahteva nula novih GPT
    poziva.
- **Backend lokacija:** NEMA IZMENE ako se koristi globalna
  `genome_kompletnost` opcija (preporučeno za v1). Granularna po-tvrdnji
  verzija bi zahtevala novo GPT polje po stavci — isti rizik profil kao
  P1.3, NE preporučuje se u v1.
- **Frontend lokacija:** `_caseDnaRender`, restrukturirati "NAJSLABIJA
  TAČKA" i pojedinačne "ZAŠTO X%" redove u 3-red format (Zaključak /
  Na osnovu — ako postoji iz P1.3 / Sigurnost — iz globalnog
  `genome_kompletnost`).
- **Rizik:** Nizak za globalnu verziju (preporučena); srednji ako se
  ide na granularnu (ne preporučuje se sada).
- **Procena vremena:** ~4-6 sati (frontend restrukturiranje, zavisi od
  toga da li P1.3 već postoji).
- **Kako meri uspeh:** kvalitativno, Silent Test signal — da li advokat
  prirodno razume "Sigurnost: Srednja" bez potrebe da pita šta znači
  (isti "prvih 5 sekundi" test korišćen u prethodnoj UX rundi).

**P2 ukupna procena: ~4-6 sati, zavisno od P1.3 statusa. Čisto frontend
restrukturiranje ako se ide na preporučenu (globalnu) Sigurnost opciju.**

---

## Deo C — Redosled i ukupna procena

| Talas | Sadržaj | Effort | Rizik | Preduslov |
|---|---|---|---|---|
| P0 | Smart Intake confidence (4 stavke, P0.3 isključen) | ~5-6h | Nizak | Nijedan |
| P1.1-1.2 | Genome kontradikcije/dokazi izvor isticanje | ~4-5h | Nizak | Nijedan |
| P1.3 | Najslabija tačka/faktori "osnov" polje | ~1 dan | Srednji | Regresioni skup testiranje PRE puštanja |
| P2.1 | Zaključak/Na osnovu/Sigurnost format | ~4-6h | Nizak (globalna verzija) | P1.3 za pun "Na osnovu" sadržaj, može ići i bez njega (prazan "Na osnovu") |

**Ukupno: ~2-3 dana rada za ceo Trust Layer v1**, od čega je P1.3 jedina
stavka koja zahteva punu Fazu-1.3-stila disciplinu (dizajn → test →
poređenje pre/posle na regresionom skupu → tek onda puštanje).

**Nijedna stavka ne dodaje novi AI model, novog agenta, graf bazu, niti
autonomiju.** Sve P0 i P1.1/P1.2/P2.1(globalna) stavke su čist prikaz
podataka koji već postoje. Jedina stavka koja traži GPT da uradi nešto
novo (P1.3) je eksplicitno dizajnirana da minimizuje rizik
(samo-referenca na već generisane podatke, ne novi nezavisan citat) i
nosi sopstveni test-pre-puštanje zahtev.

Ovaj plan ne uključuje implementaciju. Sledeći korak, ako se odobri, je
poseban krug — verovatno u istom redosledu (P0 prvo, samostalno
testiran/pušten, P1.1-1.2 drugo, P1.3+P2.1 treće, sa regresionim
testom kao gejtom pre P1.3).
