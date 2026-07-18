# Vindex AI — Pilot Success Framework v1.0

Status: živ dokument, founder-ov operativni okvir za donošenje odluka tokom
beta/pilot faze (od 2026-07-19). Ne redefiniše arhitekturu — operacionalizuje
i konkretizuje pravila koja već postoje u `VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md`
(Rule A/B/C) i `project_strategic_direction` memoriji ("sledeći korak je
poslovni, ne tehnički"), sada primenjena specifično na pilot: koje faze,
koje metrike, kako se feedback triažira, šta znači "uspešan pilot".

Misija: pretvoriti Vindex AI iz tehnički napredne platforme u proizvod koji
advokati svakodnevno koriste, plaćaju i preporučuju. Od ovog trenutka razvoj
nije vođen idejama — vođen je dokazima.

---

## Hijerarhija prioriteta (filter za svaki zahtev)

1. **Pouzdanost** — da li sistem radi tačno? Ako ne, sve ostalo staje
   (pogrešna činjenica, halucinacija člana zakona, pogrešan datum, izgubljen
   dokument, pogrešno verzionisanje).
2. **Poverenje** — da li advokat može da objasni zašto je AI nešto
   zaključio? Ako ne može, funkcija nije spremna — treba audit/provenance/
   confidence/explanation.
3. **Brzina rada** — da li ovo štedi vreme, ne da li lepo izgleda.
4. **Automatizacija** — tek kad su prethodna tri zadovoljena.

## Rule A / Rule B / Rule C — ista pravila kao Bible, ovde primenjena na pilot

**Rule A (proizvod):** nova funkcionalnost počinje samo uz jedan od dokaza:
prijava iz pilota, LEC nalaz, Hall of Shame incident, telemetrija,
ponavljajući zahtev više korisnika. Bez dokaza → ide na "Future Ideas",
ne implementira se.

**Rule B (infrastruktura):** sme bez korisničkog zahteva samo ako
ispunjava sva četiri uslova — povećava pouzdanost, ne menja ponašanje
korisnika, mali rizik, pojednostavljuje budući razvoj (Event Bus, Audit
Trail, refactoring, testovi, versioning).

**Rule C (metrika):** ništa nije završeno dok nije merljivo — svaka
implementacija mora imati najmanje jednu pre/posle metriku uspeha.

**Evidence Matrix (v1.1, formalizovano 2026-07-19) — zamenjuje apstraktno
"dva nezavisna izvora" konkretnim bodovanjem:**

| Izvor | Bodovi |
|---|---|
| Pilot feedback | 1 |
| LEC nalaz | 1 |
| Hall of Shame incident | 1 |
| Telemetrija | 1 |
| Više kancelarija nezavisno traži isto | 2 |
| Kritičan bug | automatski prolazi (vidi Emergency Rule ispod) |

Funkcionalnost ide u razvoj tek sa **≥2 boda** iz tabele — kombinacija bilo
koja dva izvora, ili jedan izvor "više kancelarija" koji sam nosi 2 boda.
Primer: pilot kaže "nedostaje automatsko prepoznavanje rokova" (1 bod) +
telemetrija pokazuje 80% korisnika ručno dodaje rokove (1 bod) = 2 boda →
implementacija počinje.

Odbija se: ako nešto zvuči zanimljivo i tehnički je moguće, ali ne dostiže
2 boda.

**Emergency Rule — jedini izuzetak od Evidence Matrix-a:** kritičan blocker
prijavljen od strane pilot kancelarije ("bez ovoga ne možemo da radimo")
preskače matricu u potpunosti i ulazi odmah, bez čekanja na drugi izvor.
Ovo NIJE isto što i BUG oznaka iz triaže ispod (koja znači "postojeća
funkcija ne radi tačno") — Emergency Rule pokriva slučaj gde NEDOSTAJUĆA
funkcionalnost čini pilot kancelariju nesposobnom da uopšte koristi
proizvod za svoj tekući posao. Retko, namerno usko definisano — ne koristiti
za "bilo bi jako korisno da postoji X".

---

## Struktura pilota — tri faze

| Faza | Kancelarija | Cilj |
|---|---|---|
| 1 | 3 | Otkriti greške. Cilj NIJE prodaja. |
| 2 | 5 | Ponovljivost — ako svih 5 koristi istu funkciju, to postaje prioritet. |
| 3 | 10 | Merenje ROI. |

## Šta se meri, po modulu

- **Smart Intake** — vreme do gotovog predmeta, broj ručnih ispravki, broj
  neuspešnih ekstrakcija, prosečan confidence, Intake Quality Score.
- **Case Genome** — broj refresh-a, vreme generisanja, human override,
  require_review stopa, broj halucinacija, vreme provedeno u Genome prikazu.
- **Strategy** — koliko puta otvorena, koliko puta korišćena, koliko puta
  izmenjena.
- **Timeline** — koliko puta otvoren, koliko puta korišćen, koliko puta
  kliknuto na događaj.
- **CRM** — broj kreiranih predmeta, broj aktivnih klijenata, broj
  završenih predmeta.

**Trenutni status instrumentacije (proveriti pre nego što se pretpostavi
da nešto već postoji — ovaj odeljak treba osvežiti kad se pilot stvarno
pokrene):** Faza 1 (`GENOME_UPDATED` event + `audit_immutable` red) daje
broj refresh-a, verzija, i require_review stopu već danas. Faza 2.1
(`_compute_finalize_wait_s`, `_count_corrected_entities` u
`routers/smart_intake.py`, upisano u `usage_events`) daje deo Smart Intake
metrika (vreme do finalize-a, broj ispravki). Ostalo (Strategy/Timeline
open-rate, CRM agregati, Genome "vreme provedeno u prikazu") **nije
instrumentisano** — ne pretpostavljati da postoji, i ne graditi ga
preventivno bez konkretnog signala da je pilot fazi 1 ili 2 potreban.

## Triaža feedback-a — četiri oznake

| Oznaka | Značenje | Prioritet |
|---|---|---|
| BUG | Ne radi | Odmah |
| RELIABILITY | Radi, ali nije dovoljno tačno | Vrlo visok |
| UX | Radi, ali zbunjuje | Srednji |
| FEATURE | Nova ideja | Ne odmah — čeka potvrdu (Rule A, dva izvora) |

---

## Definicija uspešnog pilota

Pilot NIJE uspešan kad korisnici kažu "lepo izgleda". Uspešan je kad se
izmeri:

- ≥40% manje vremena za obradu predmeta
- ≥90% tačnih ekstrakcija ključnih činjenica
- <10% Genome "require_review" na stabilnim tipovima predmeta
- ≥70% predmeta u kojima je korišćen Case Genome
- ≥50% predmeta u kojima je otvorena Strategy analiza
- ≥80% korisnika koji žele da nastave nakon pilota

Cilj pilota NIJE dodavanje što više funkcija, impresioniranje investitora,
ili dokazivanje da AI može sve. Cilj JESTE dokazati tri stvari: pouzdanost
(tačni, proverljivi rezultati), produktivnost (brže uz očuvan kvalitet), i
navika korišćenja (advokat spontano otvara Vindex kao prvi alat).

## Završno pravilo

Najveća opasnost za Vindex AI nije nedostatak funkcionalnosti — nego
razvijanje funkcionalnosti koje niko nije tražio ili koje ne rešavaju
stvaran problem. Svaki naredni veliki modul treba da bude odgovor na
dokazanu potrebu iz pilota, LEC-a, ili telemetrije.
