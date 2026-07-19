# Vindex AI — Trust Layer Analysis (2026-07-19)

Ovo je ANALIZA, ne implementacija — po founderovom eksplicitnom zahtevu
posle `SENIOR_PARTNER_BUYER_SIMULATION_REPORT.md`. Odgovara na 5
postavljenih pitanja isključivo čitanjem stvarnog koda (backend system
prompt-ovi, DB šeme, frontend render funkcije) — svaka tvrdnja ispod je
citirana na file:line, ništa nije pretpostavljeno. Implementacija ide u
poseban krug tek posle pregleda ovog dokumenta.

---

## 1. Gde danas postoji dokaz porekla informacije?

| Mesto | Šta postoji | Nivo provenijencije |
|---|---|---|
| `kontradikcije[].lokacija_1/lokacija_2` (Case Genome) | GPT prompt eksplicitno traži `"DOK-01 str.X ili opis"` (`routers/case_dna.py:72`), frontend renderuje kao inline tekst `[DOK-01↔DOK-02]` (`vindex.js`, kontradikcije sekcija) | **Najbolji postojeći slučaj** — dokument + strana, ali kao tekst, ne klik |
| `dokazi_rang[].redni_broj` (Case Genome) | Povezuje ocenu dokaza sa `DOK-XX` identifikatorom dokumenta (`routers/case_dna.py:90`), prikazano kao "DOK-07" prefiks u frontendu | Dokument-nivo, bez strane; tekst, ne link |
| RAG badge kod pojedinačnog AI agenta | `'📚 izvori iz baze'` sa tooltip-om "Odgovor koristi izvore iz pravne baze Vindex-a" (`vindex.js:18118`, iz ranijeg UX audita) | Postoji SAMO za `agent_run` (single-agent poziv), ne za `agent_run_parallel` niti bilo koji drugi modul |
| Strategy moduli (red_team, litigation, sudija, due_diligence) | Backend poziva `_fetch_praksa_ctx()`/`_fetch_zakon_ctx()` — stvarno RAG dohvatanje iz Pinecone PRE generisanja (`routers/strategija.py:69,93,116,132-144`) | Retrieval postoji, ali NIJE verifikovano da li generisan tekst eksplicitno cituje KOJI dohvaćeni pasus je korišćen za koju tvrdnju — zahteva proveru `analiza/` modula van obima ove analize |
| Smart Intake — confidence po entitetu | `entity_confidence` (dict, 0-1 float po tipu entiteta), `classification_confidence`, `ocr_confidence` (`shared/intake_documents.py:37-56,99-131`) | **Postoji kao BROJ u bazi**, ali frontend prikazuje samo binarni `⚠` ako je `needs_review=true` (`vindex.js:19653-19657`) — sam broj se **nikad ne prikazuje** |
| Court Predictor "Proveri pouzdanost predikcije" | Zaseban PLAĆEN poziv (1 kredit), `/api/predictor/confidence-check` (`vindex.js:3339-3461`) | Postoji, ali je opt-in i naplaćen — nije podrazumevan deo rezultata |
| "Confidence Audit" kalibracija (Podešavanja/Settings) | Prikazuje `X% tačno (Y/Z)` po bandu pouzdanosti (`vindex.js:2522-2549`) | Postoji, ali je AGREGATNO (istorijska tačnost sistema), ne PO-PREDMETU |

**Zaključak pitanja 1:** provenijencija postoji fragmentarno, na najmanje
4 nezavisna mesta, sa različitim formatima (tekst-citat, broj-u-bazi,
plaćen-poziv, agregatna-statistika). Nijedno od njih nije deo
jedinstvenog, doslednog "trust" sistema — svako je rešeno posebno, kad
je ta funkcija građena.

---

## 2. Gde AI tvrdi nešto bez vidljivog izvora?

Direktno iz `_GENOME_SYSTEM` šeme (`routers/case_dna.py:38-115`) — polja
BEZ ikakvog document/page reference field-a u šemi:

- `snaga_faktori[].opis` — "Zašto ovaj faktor doprinosi/slabi predmet" —
  slobodan tekst, nema `dokument_id` ni `lokacija` polje.
- `najslabija_tacka.rizik` / `.preporuka` — potpuno slobodan tekst, **ovo
  je tačno primer koji je founder naveo** ("Zastarelost potraživanja" bez
  ikakvog osnova u šemi).
- `strategija.primarni_cilj` / `.rezervni_plan` / `.scenariji[]` — čisto
  generisan strateški tekst, nula reference na izvorni dokument.
- `nedostaje[].opis` — slobodan tekst objašnjenja.
- `zakljucak` — slobodan sažetak.
- `upozorenja[]` — slobodna lista.
- `pravna_teorija.*` (osnov_odgovornosti, uzrocna_veza, visina_stete) —
  slobodan tekst bez citata.
- Svi Strategy moduli (`red_team`, `litigation`, `sudija`, `revizor`,
  `witness`, `sudija_v2`, `court_predictor`) — rezultat je slobodno
  formatiran tekst (`stratFormatirajRezultat`, samo bold/sekcije/boje,
  nema strukture za citat).
- `genome_validator.py`'s `hard_flags`/`soft_flags[].razlog` — ironično,
  Verification Layer SAM ima objašnjenje ("zašto je ovo flagovano") ali
  ni ono ne cituje TAČNU stranu/red teksta koji je proverovan, samo
  opisuje logičku proveru.

**Zaključak pitanja 2:** izuzev `kontradikcije` i `dokazi_rang`
(delimično), SVAKO polje u Case Genome-u koje nosi stvarnu pravnu
procenu (najslabija tačka, strategija, zaključak) nema nijedan
mehanizam za trag nazad do izvora. Ovo je tačno gde bi Trust Layer
najviše promenio psihologiju.

---

## 3. Koje procene imaju confidence?

| Signal | Format | Gde | Vidljivo korisniku? |
|---|---|---|---|
| `snaga_predmeta_procent` | 0-100 (sada backend-računat, Reliability Patch) | Case Genome | Da, prominentno |
| `dokazi_rang[].snaga_score` / `zvezdice` | 0-100 / 1-5 | Case Genome | Da |
| `genome_kompletnost` | visoka/srednja/niska (kategorijsko) | Case Genome | Da |
| `_verifikacija.odluka` | approve/approve_with_warning/require_review | Case Genome | Da (od P0-1 fix-a) |
| `najslabija_tacka.kriticnost` | 0-100 | Case Genome | Da |
| `heatmap.*` (6 dimenzija) | 0-100 po dimenziji | Case Genome | Da |
| `classification_confidence` | 0.0-1.0 float | Smart Intake (DB) | **NE** — samo binarni ⚠ |
| `entity_confidence` (po entitetu) | 0.0-1.0 float | Smart Intake (DB) | **NE** — samo binarni ⚠ |
| `ocr_confidence` | 0.0-1.0 float ili null | Smart Intake (DB) | **NE**, nema referenci u frontendu uopšte |
| Court Predictor "nivo_pouzdanosti" | kategorijsko + tekst | Predictor rezultat | Da, ali samo posle plaćenog dodatnog poziva |
| Judge Profile "pouzdanost_profila" | tekst | Predictor modul | Da |
| Confidence Audit band tačnost | % (agregatno, ne po predmetu) | Podešavanja | Da |

**Zaključak pitanja 3:** Case Genome ima BOGAT skup confidence signala,
već vidljivih. Smart Intake ima BOGAT skup confidence signala, potpuno
NEVIDLJIVIH kao brojevi. Ovo je asimetrija vredna napomene — najbolja
postojeća infrastruktura (Smart Intake, numerička, po-entitetu) je
najmanje iskorišćena u UI-ju.

---

## 4. Koje module možemo učiniti proverljivim bez velikog refaktora?

Rangirano po effort/postojeća-infrastruktura odnosu — **ne predlažem
implementaciju, samo procenjujem izvodljivost**:

### Nizak effort (podaci već postoje, samo nedostaje prikaz)

1. **Smart Intake confidence brojevi.** `entity_confidence`,
   `classification_confidence` su već u DB i već stižu u API odgovoru
   koji frontend prima (`e.confidence` postoji na entitetu — potvrđeno
   `shared/intake_documents.py:71`). Frontend samo treba da prikaže broj
   umesto (ili pored) `⚠` ikonice. **Ovo je doslovno prikaz postojećeg
   polja, ista kategorija posla kao P0-1 Genome Verification fix.**
2. **Kontradikcije "izvor" postaje klikabilan.** `lokacija_1/lokacija_2`
   tekst već postoji (`DOK-01 str.X`) — pretvaranje u klikabilan link ka
   dokumentu zahteva samo parsiranje `DOK-XX` prefiksa i postojeći
   dokument-viewer poziv (ako postoji — nije verifikovano u ovoj
   analizi da li dokument-viewer sa preciznim skrolom do strane X
   postoji; ako ne, ovo prelazi u "srednji effort").
3. **Dokazi rang "DOK-XX" postaje klikabilan.** Isti obrazac kao #2.

### Srednji effort (zahteva prompt izmenu, ne arhitekturu)

4. **`najslabija_tacka` i `snaga_faktori[].opis` dobijaju
   `izvor_dokument`/`izvor_lokacija` polje.** GPT već dobija dokumente
   označene `DOK-XX` u promptu (`_extract_genome`, `routers/case_dna.py:
   164-171`) — model TEHNIČKI već ima informaciju da cituje izvor za
   SVAKO polje, samo mu šema to trenutno ne traži. Dodavanje
   `"izvor": "DOK-XX str.Y"` polja u `_GENOME_SYSTEM` šemu za
   `najslabija_tacka` i svaki `snaga_faktori[]` je izmena promptu +
   validatora + frontend rendera — nije arhitektonska promena, ali
   zahteva testiranje da model dosledno popunjava novo polje (rizik od
   izmišljanja lokacije ako dokument stvarno ne sadrži jasan citat —
   mora se dodati STROGO PRAVILO da polje ostaje prazno ako izvor nije
   jasan, ne izmišljati).
5. **Agregatna "Pouzdanost: X%" za ceo Genome.** Trenutno ne postoji kao
   jedan broj — mogao bi se IZVESTI (ne izmisliti novi GPT poziv) iz
   već postojećih signala: `genome_kompletnost` + broj `_verifikacija`
   flagova + prisustvo/odsustvo `nedostaje[]` kritičnih stavki. Ovo bi
   bio deterministički izračun (isti obrazac kao `compute_snaga_score`
   iz Reliability Patch-a — Track 3 princip), ne nova AI procena.

### Visok effort / van obima ove analize

6. **Strategy moduli sa strukturiranim citatima.** Zahteva izmenu
   svakog od 7+ modula (`analiza/` folder, nije pregledan u ovoj
   analizi) da vraća strukturiran JSON sa citatima umesto slobodnog
   teksta — veća izmena po modulu, van "bez refaktora" praga koji je
   founder postavio.
7. **RAG badge za sve module, ne samo `agent_run`.** Zahteva da
   `agent_run_parallel` i Strategy pipeline prenose koji Pinecone
   rezultati su korišćeni do frontenda — srednji-do-veći effort jer
   trenutno taj podatak verovatno postoji na backendu (`_praksa_context`)
   ali se ne vraća u response-u korisniku eksplicitno.

---

## 5. Kako izgleda prvi ekran koji advokat vidi nakon analize?

Trenutno stanje (posle P0/P0.1-0.3 fix-ova iz prethodne dve runde):

1. Predmet se otvori → Case Genome panel se automatski prikazuje
   (`_caseDnaRender`, nema dodatnog klika).
2. **PREGLED** blok na vrhu (dodato u prethodnoj rundi): Status
   (Povoljna pozicija/Srednji rizik/Visok rizik), Najveća snaga,
   Najveća slabost, Sledeća akcija — 4 reda teksta.
3. **AI Provera** red (jedan red, uvek vidljiv, van collapsible dela):
   "✓ AI provera: nema upozorenja" ili "⚠ AI provera: N upozorenja
   (prikaži)" — sa tooltip-om "AI je analizirao predmet i proverio
   sopstvenu procenu."
4. "Detaljna analiza →" toggle, podrazumevano zatvoren.
5. Iza toggle-a: 9+ sekcija (Snaga predmeta bar, ZAŠTO X%, Heat Map,
   Rangirana evidencija, Najslabija tačka, Plan postupanja, Šta
   nedostaje, Stranke, Kontradikcije, Upozorenja, Preporučeni sledeći
   koraci, Zaključak, Pouzdanost+Izvori).

**Ono što advokat NE vidi na ovom prvom ekranu, a founderov predlog
traži:** brojčanu "Pouzdanost: X%" agregatnu ocenu (postoji samo
kategorijsko `genome_kompletnost` i `_verifikacija.odluka`, ne jedinstven
procenat); objašnjenje ŠTA je tačno provereno (samo DA/NE + lista
flagova, ne strukturiran prikaz po kategoriji kao u founderovom mockup-u
— "Činjenice: 18 pronađenih, 18 povezano"); "Zašto nije 100%?" — ne
postoji ekvivalent ovog pitanja nigde u trenutnom prikazu.

**Ono što VEĆ postoji i blizu je founderovoj viziji:** struktura
PREGLED+toggle je već postavljena kao mesto gde bi se prošireni
Verification prikaz prirodno uklopio — ne bi zahtevalo novu poziciju u
layout-u, samo bogatiji sadržaj unutar već postojećeg AI Provera reda/
bloka.

---

## Sinteza — odgovor na "šta je izvodljivo BEZ velikog refaktora"

Founderova tri predloga, mapirana na gornju analizu:

1. **"VERIFIKACIJA ANALIZE" strukturirani prikaz (Činjenice/Dokazi/
   Pravne reference/Rizici sa brojevima + Pouzdanost %)** — DELIMIČNO
   izvodljivo bez refaktora. `_verifikacija` već ima `hard_flags`/
   `soft_flags` koji se MOGU kategorisati (svaka provera već zna da li
   je o dokazima, kontradikcijama, ili zakonskim referencama — videti
   `genome_validator.py`'s 5 podprovera: dokazi_rang, kontradikcije,
   relevantni_zakoni, snaga_konzistentnost, clan_brojevi). Grupisanje
   postojećih flagova po ovih 5 kategorija je NIZAK effort. Sama
   "Pouzdanost: 82%" brojka zahteva novi deterministički izračun
   (stavka #5 gore) — SREDNJI effort, ali ne nova arhitektura.

2. **Case Genome "klik → poreklo zaključka" (Dokument/Strana/Pravilo)**
   — DELIMIČNO izvodljivo. Za `najslabija_tacka` i `snaga_faktori`
   zahteva prompt izmenu (stavka #4 gore, SREDNJI effort). Za
   `kontradikcije`/`dokazi_rang` podaci VEĆ POSTOJE (stavka #2-3, NIZAK
   effort) — ovo bi bio najbrži, najjeftiniji dokaz koncepta pre nego
   što se širi na ostatak Genome-a.

3. **"Pilot Trust Mode" iskren status ekran** — ovo NIJE tehničko
   pitanje uopšte, nego pitanje SADRŽAJA/POZICIONIRANJA (broj
   analiziranih test predmeta, ciljni broj, poziv na povratnu
   informaciju). Tehnički trivijalno (statičan/poluautomatski tekst
   blok), ali zahteva founderovu odluku o TAČNIM brojkama koje se
   prikazuju (koliko test predmeta stvarno postoji — LEC populacija je
   po ranijoj evidenciji projekta i dalje prazna, `project_smart_intake_
   architecture` — ovaj ekran ne sme tvrditi brojku koja ne postoji).

**Najjeftiniji, najbrži prvi dokaz koncepta ako se ide u implementaciju
(nije odluka, samo zapažanje):** kombinacija stavki 1-2-3 iz "Nizak
effort" liste (Smart Intake confidence brojevi vidljivi, kontradikcije
i dokazi_rang klikabilni) bi dala opipljiv, vidljiv pomak u
proverljivosti bez ijedne izmene GPT prompta — čisto prikaz podataka
koji već postoje u bazi.
