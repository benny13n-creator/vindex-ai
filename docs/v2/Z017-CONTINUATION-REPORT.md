# VINDEX V2 — IZVEŠTAJ NASTAVKA (Z017 CONTINUATION)

**Grana:** `v2-gate-a` · **Opseg:** zatvaranje P1 reda, klasifikacija P2
**Cutover NIJE izvršen.** `/app` je netaknut, rollback postoji, rollout
populacija nije menjana. V2 stoji na `/app-v2` i čeka vlasničku ocenu.

---

## A. PARITET POSLOVNIH SPOSOBNOSTI

Kanonska metrika. Puna matrica: `docs/v2/CAPABILITY-MATRIX.md`.

| Prioritet | Ukupno | IMPLEMENTED | PARTIAL | BLOCKED | DEFERRED |
|---|---|---|---|---|---|
| **P0** | 46 | 40 | 1 | 5 | 0 |
| **P1** | 17 | **17** | 0 | 0 | 0 |
| **P2** | 48 | 0 | 0 | 0 | 48 |
| **Ukupno** | **111** | **57** | **1** | **5** | **48** |

Brojevi su samoprovereni parsiranjem redova same matrice (111 stavki, bez
duplikata, zbirovi se poklapaju sa deklarisanim).

### Zatvoreno u ovom nastavku (17 P1 sposobnosti)

| # | Sposobnost | Odredište |
|---|---|---|
| A7 | Uvoz predmeta iz dokumenta (Smart Intake) | `/predmeti/uvoz` |
| B12 | Brisanje predmeta | Dosije · Stanje |
| B13 | Komentari (spojeni u jedan tok napomena) | Dosije · Beleške |
| B16 | Naplata po predmetu | Dosije · Naplata |
| B26 | Zastarelost i procesni rokovi | `/znanje/rokovi` |
| D4 | Šabloni dokumenata | `/predmeti/sabloni` |
| D5 | Podnesak sudu | `/predmeti/podnesak` |
| D7 | Istraživanje u kontekstu predmeta | `/znanje?predmet=` |
| E4 | Izmena klijenta | `/klijent/<id>` |
| E11 | Arhiviranje klijenta | `/klijent/<id>` |
| F6 | Stanje naplate i nefakturisan rad | `/kancelarija/finansije` |
| F7 | Izveštaji (godišnji, po tipu) | `/kancelarija/finansije` |
| F8 | Tarife (AKS) | `/kancelarija/tarife` |
| H5 | Jutarnji brifing | `/danas/brifing` |
| H6 | Kalendar | `/danas/kalendar` |
| H7 | Obaveštenja | `/danas/obavestenja` |
| H9 | Plan i potrošnja | Kancelarija · Nalog |

**Nijedna nova stavka u globalnoj navigaciji.** Svih 17 živi unutar pet
postojećih prostora, kroz PROSTOR → OBJEKAT → RADNJA. Legacy sidebar stavka
nije uzeta kao dokaz da V2 treba novu destinaciju.

---

## B. POKRIVENOST BACKEND RUTA (odvojena metrika)

Mereno 2026-09-06 nad `v2/**/*.js` i `static/vindex.js`, sa normalizacijom
`{id}` segmenata:

```
legacy pozivi u vindex.js                  195
V2 backend putanje                          50   (27 na početku programa)
preklapanje                                 37   (16 na početku)
samo u V2                                   13
```

**Ovo NIJE paritet sposobnosti i nikada se tako ne predstavlja.** Jedna
sposobnost koristi više ruta; jedna generička ruta ne prenosi pet korisničkih
sposobnosti. Metod ne vidi putanje sastavljene u više koraka, pa je 50 **donja
granica**, ne tačan popis.

---

## C. TESTOVI I MUTACIJE

**366 Z017 test funkcija.** Svaka nova sposobnost ima domen testove i
mutacije. Zelen test se ne uzima kao dokaz dok mutacija ne pokaže da pada.

| Sposobnost | Testova | Mutacija | Preživelih |
|---|---|---|---|
| H6 Kalendar | 22 | 11 | 0 |
| B13 Napomene + ugovor komentara | 23 | 9 | 0 |
| B16 Naplata predmeta | 22 (+2 SIDRA) | 2 | 0 |
| B26 Rokovi | 22 | 13 | 0 |
| F6/F7/F8 Finansije i tarife | 23 | 17 | 0 |
| D5 Podnesak | 15 | 9 | 0 |
| D4 Šabloni + ugovor čuvanja | 22 | 15 | 0 |
| H5 Brifing | 16 | 11 | 0 |
| H7/H9 Obaveštenja i plan | 21 | 12 | 0 |
| D7 Kontekst predmeta | 5 | 5 | 0 |
| A7 Uvoz | 22 | 19 | 0 |
| **Ukupno** | **366 (Z017)** | **123** | **0** |

**Mutacije koje su prvo PREŽIVELE i šta je iz toga sledilo** — ovo je jedini
deo koji pokazuje da mutacije nisu ukras:

1. `jeRazresen` u kalendaru — filter se nije mogao pobiti jer se računa iz
   istog `stanjeZapisa` kao i uslov pored njega. **Nije ojačan test nego
   uklonjen nedostižan kod**: odbrana koja ne može da opali laže čitaoca.
2. Isto u `delovi()` (brifing): filter praznih delova nije dostižan
   (`[^*]+` traži bar jedan znak). Uklonjen.
3. `nedostaciRacuna` — prazan datum je prolazio kroz poruku o OBLIKU. Test
   ojačan da razlikuje „unesite datum" od „ispravite oblik": dve različite
   greške traže dve različite radnje.
4. `nedostaciIznosa` — `1e5` i `0x10` su konačni brojevi i prolazili bi bez
   regexa. Test ojačan naučnom notacijom i hex unosom (nastaje nalepljivanjem
   iz tabele).
5. `idZaOznacavanje` — guard je bio nedostižan kroz put kojim ga test poziva.
   Test pozvan nad CELIM spiskom, ne nad već filtriranim.
6. `/notifications` lažni uspeh — nije postojao nijedan test backend grane.
   **Dodat test**, ne ojačan postojeći.

**Napomena o snazi dokaza (D7):** mutacije M4–M5 na backendu ubijene su
statičkom proverom veze, ne testom. Pravi dokaz za taj ugovor su **tri živa
poziva** (`True` / `False` / `None`). To se ovde kaže, a ne prećutkuje.

---

## D. PUTANJE (šest obaveznih)

Mereno kao TOK, ne kao ekrani. Korak je uspešan samo ako je posle njega
vidljiv dokaz na ekranu — ne ako je poziv vratio 200.

| # | Putanja | Koraka | Ishod |
|---|---|---|---|
| 1 | Vlasnikov dan (Danas → Kalendar → Brifing → Obaveštenja) | 4/4 | prošla |
| 2 | Nov predmet (registar → obrazac → Dosije, 6 celina) | 4/4 | prošla |
| 3 | Pravno istraživanje (opšte → rokovi → u kontekstu predmeta) | 3/3 | prošla |
| 4 | Izrada akta (akt → podnesak → šabloni) | 3/3 | prošla |
| 5 | Kancelarija (nalog+plan → finansije → tarife) | 4/4 | prošla |
| 6 | Mobilni tok, 15 ekrana na 390px | 15/15 | prošla |

**0 konzolnih grešaka** kroz sve putanje.
**Smoke:** svih 21 V2 ekrana montirano, 0 runtime grešaka.

---

## E. VIZUELNI DOKAZ

**55 snimaka**, 11 ekrana × 5 širina (1920 / 1440 / 1024 / 390 / 360):
`C:\Users\Benny\AppData\Local\Temp\claude\vizuelno`

Mereno nad STVARNO izračunatim stilovima, ne nad izvorom:

| Provera | Rezultat |
|---|---|
| Cijan / plavi AI ton | **0** pojava na 55 ekrana |
| Senke (glow) | **0** |
| Zaobljenja > 4px | **0** |
| Globus / KPI sfera / legacy sidebar / kartice | **0 / 0 / 0 / 0** |
| Horizontalni preliv | **0** na svih 5 širina |
| Najmanji font | **11.0px** (pod, nigde ispod) |
| Širina sadržaja | 1440 max na 1920 — sadržaj drži meru za čitanje |
| Fontovi | Source Sans 3, Source Serif 4, JetBrains Mono |

„Times New Roman" na 24 elementa proveren: sve su `<html>`, `<head>`,
`<meta>`, `<title>` — nerenderovani elementi. **Nijedan vidljiv tekst.**

**Nađeno i popravljeno merenjem:** dodirne mete na telefonu bile su 23px
(naziv predmeta, ime klijenta, naziv spisa). Prst pogađa površinu, ne slova.
Popravljeno u `@media (pointer: coarse)`; gustina na širokom ekranu
nepromenjena (red na 1440px i dalje 56px).

---

## F. BEZBEDNOST I ISTINITOST PODATAKA

### Provera sukoba interesa (owner-locked invarijanta)

Zatvorena i u novom toku: **A7 uvoz predmeta iz dokumenta**. Finalizovanje
ZAKAZUJE proveru; rezultat stiže kasnije. Ekran nikada ne piše „nema sukoba".

| Stanje | Šta ekran kaže |
|---|---|
| `COI_PENDING` | „Provera je zakazana… odsustvo upozorenja NE znači da sukoba nema" |
| `COI_FAILED` | **glasna ograda**: „NIJE zakazana i niko je neće izvršiti — pokrenite je ručno" |
| `COI_NOT_APPLICABLE` | „nije pokrenuta jer ime stranke nije bilo poznato" |
| nepoznato | tretira se kao NE-zakazana (fail-closed) |

### Osam kvarova nađenih merenjem ugovora, ne čitanjem koda

| Kvar | Posledica pre popravke |
|---|---|
| `komentari.order("created_at")` | **GET 500 za svakog korisnika**: komentar se upisivao, nikad čitao |
| `doc-templates/sacuvaj` gađao `tekst`+`tip` | **čuvanje dokumenta nikad nije radilo** |
| `obrisi_belesku` bez zero-row guarda | `{"ok": true}` za nepostojeću belešku |
| `/notifications` prazan niz na grešci | pala pretraga = „nemate obaveštenja" |
| `/api/pitanje` ćutke preskakao kontekst | opšti odgovor izgledao kao odgovor o predmetu |
| tipovi podneska samo u validatoru | frontend bi nudio tip koji server odbija |
| ukrasna ikonica u `sadrzaj` | emoji bi završio U BAZI |
| `new Date("2026-02-31")` nije NaN | nepostojeći datum stizao do servera kao 422 |

Sve popravke su minimalne, unazad kompatibilne i praćene testom + mutacijom.

### Prezentacioni sloj ne izmišlja poslovnu istinu

- „nije očitano" ≠ 0 (brifing, kad izvor nije pročitan)
- „provera zakazana" ≠ „nema sukoba" (uvoz)
- „nefakturisano" ≠ „klijent duguje" (finansije — tri odvojena iznosa)
- „—" sa servera ≠ naziv predmeta (nefakturisan rad)
- odsutan iznos ≠ 0 RSD · odsutno stanje ≠ „nije potvrđeno"
- istekla pretplata se ne prikazuje kao „važi do"
- granica koja nije objavljena ≠ „neograničeno"
- prazan zbir se ne prikazuje (0 RSD × 4 se čita kao „klijent ne duguje ništa")

### Semantika grešaka

400 / 401 / 403 / 404 / 409 / 422 / 429 / 500 / 502 / 503 — svaka ima svoju
rečenicu. 429 nije „aplikacija je pala" nego granica; 403 nije generička
greška nego granica plana; 409 pri brisanju znači da predmet I DALJE POSTOJI.

### Naplativi pozivi u testovima

Svi UI testovi presreću naplative rute. Namerno je izvršeno **4 prava poziva
ukupno**: 3 za merenje `kontekst_predmeta` ugovora i 1 za brifing — jer se ti
ugovori drugačije ne mogu dokazati. Zapisano je koliko je presretnuto u
svakom pokretanju.

---

## G. REGRESIJA

**Metodološka ispravka nađena u ovom nastavku:** `pytest-randomly` je
instaliran i meša redosled na SVAKOM pokretanju. Poređenje skupova padova
između pokretanja bez zaključanog semena **nije validno** — što je i
proizvelo lažni signal (jedan test se pojavljivao i nestajao). Sve poređenje
od tada koristi `--randomly-seed=20260906`.

Dokaz da nijedan pad nije uveden — pokrenuto na PRETHODNOM commit-u
(`56e8b2dc`, pre ovog nastavka) sa ISTIM semenom:

```
baseline 56e8b2dc   16 padova · 7905 prolazi
posle nastavka      16 padova · 8102 prolazi
razlika u SKUPU     nema — identičan skup, stavku po stavku
```

**+197 novih prolazećih testova, 0 novih padova.**

**Jedno pokretanje je dalo 17 i to se ovde ne prećutkuje.** Trajalo je 28
minuta umesto 13 jer je mašina bila opterećena paralelnim poslom (moja
greška u raspoređivanju, ista klasa kao ranije „vizuelni prolaz izgladnjen
regresijom"). Sedamnaesti pad je bio `goto` timeout Playwright-a ka
SOPSTVENOM lokalnom test serveru u `test_false_success_crossdoc_playwright`.
Taj test prolazi izolovano (4/4) i CSS pravilo ne može da izazove timeout
navigacije. Ponovljeno čisto, bez ijednog paralelnog posla: **ponovo 16,
identičan skup.** Merodavno je čisto pokretanje; sporno je zabeleženo.

Svih 16 padova je zatečeno stanje: registracija (5), COI intake konvergencija
(3), faza1 pristupačnost nad LEGACY ekranima (4), rc cold start (2),
ns003 protokol (1), blackswan thread-safety (1, redosled-zavisan — pada i na
baseline-u sa istim semenom).

---

## H. ŠTA JOŠ NIJE URAĐENO — TAČNO, BEZ „50+"

### BLOCKED (5) — jedan isti blokator

`G1` regulatorna provera · `G2` pretraga propisa o dig. imovini ·
`G3` analiza whitepaper-a · `G4` AML/KYC · `G5` analiza pametnog ugovora.

Ekran bi prikazao regulatorni zaključak, a ruta **ne vraća izvor** kojim se on
dokazuje. Ograda je privremeni fail-closed mehanizam, ne konačna arhitektura.
**Traži izmenu backenda, ne frontenda.** Nijedan izvor nije izmišljen i
ograda nije uklonjena.

### PARTIAL (1)

`F3` tim kancelarije. Prikaz je potpun (firma, članovi, uloge, stanje bez
firme). **Jaz: upravljanje timom** — `pozovi` / `suspenduj` / `reaktiviraj` /
`ukloni` / `napusti` / `naziv` / `mesta` / `istorija` (8 ruta). Odloženo jer
vlasnikov nalog vraća `no_firma`: ulazni uslov nije ispunjen.

### DEFERRED (48) — svih 48 P2, svaka sa razlogom

| Razlog | Broj |
|---|---|
| AI zaključak bez ugovora o provenijenciji | 14 |
| Nije u vlasnikovom redu izvršenja | 15 |
| Isti blokator kao G1–G5 | 4 |
| Drugi prikaz već prenete sposobnosti | 4 |
| Izvedeni pokazatelj — meri se posle upotrebe | 4 |
| Ulazni uslov nije ispunjen / dokazano mrtvo | 3 |
| Tvrdnja o pravu traži provenijenciju | 2 |
| Nema backend rute | 2 |

Popis po stavci je u matrici. Svaka stavka je u tačno jednom redu; zbir 48.
**Nijedna sposobnost nije nestala iz matrice.**

---

## OCENA

🟡 **FUNKCIONALNO KOMPLETNO — OSTAJU SAMO EKSPLICITNI P2 ODLOŽENI ELEMENTI**

Obrazloženje zašto nije 🟢:

- **P1 je 17/17.** P0 je 40/46 IMPLEMENTED.
- Ali **5 P0 sposobnosti (G1–G5) su BLOCKED**, i to je dokazana
  protivrečnost ugovora, ne odložena odluka. Dok backend ne vraća
  provenijenciju za regulatorni zaključak, uslov §14.2 nije ispunjen.
- **F3 je PARTIAL** sa imenovanim jazom.

Ne prikazujem ovo kao 🟢 jer bi to značilo da je P0 zatvoren u celosti — nije.
Ne prikazujem kao 🔴 jer nijedan blokator ne sprečava vlasnikovu ocenu
proizvoda: svih 21 ekrana radi, svih šest putanja prolazi, regresija je bez
ijednog novog pada.

**Procenat preklapanja ruta nije i neće biti korišćen kao ocena.**

---

## CUTOVER

**NIJE IZVRŠEN i neće biti bez vlasnikove odluke.**

- `/app` nije preusmeren
- legacy nije obrisan
- rollback postoji
- rollout populacija nije menjana
- V2 stoji na `/app-v2` za vlasničku ocenu
