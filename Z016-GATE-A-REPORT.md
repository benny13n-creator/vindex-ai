# GATE A — GLOBALNA LJUSKA + DANAS — IZVEŠTAJ

Datum: 2026-09-05 · Base: `f7464b45` (produkcija) · **HEAD: `46f842b8`**
Grana: `v2-gate-a` · Migracije: **0** · Push: **nije izvršen** · Legacy `/app`: **nedirnut**

---

## 1. NALAZ KOJI JE ODREDIO CEO EKRAN

Pre nego što sam napisao ijednu liniju Danas ekrana, pitao sam odakle dolaze
datirane obaveze. Odgovor je promenio arhitekturu.

Jedini agregat datiranih događaja je `/api/kalendar/pregled`. Za rokove izvedene
iz `predmet_hronologija` on vraća **samo** `{vaznost, dogadjaj}` — bez `id`, bez
`akter`, bez stanja odluke. Izmereno na produkciji, vlasnički nalog:

```
datum        događaj                          akter           stanje_odluke
2026-06-15   Rok za reklamaciju uređaja U-2   Genome (AI)     UNCONFIRMED
2026-09-15   Rociste zakazano                 Pipeline (AI)   UNCONFIRMED
2026-09-15   Rociste zakazano                 Pipeline (AI)   UNCONFIRMED
2026-09-15   Rociste zakazano                 Pipeline (AI)   UNCONFIRMED
```

**Sva četiri „kritična roka" na ovom nalogu su AI predlozi koje nijedan čovek
nije potvrdio.** Kalendar ih servira kao obične događaje sa `⚠️` i nikakvom
naznakom da su nepotvrđeni.

Da je Danas građen iz kalendara — a to je najkraći put — prva rečenica koju bi
Vindex rekao advokatu ujutru bila bi tvrdnja o kritičnom roku koju niko nije
proverio. To je tačno ona granica koju proizvod ne sme da pređe.

**Zato je izvor obaveza `/api/rokovi/kandidati`**, jedini endpoint koji nosi
`stanje_odluke`. Kalendar se koristi samo za dve stvari koje kandidati nemaju:
**ročišta** (druga tabela, drugi objekat) i **nazive predmeta**.

Kalendarski događaji tipa `rok_dokument`/`napomena` se **odbacuju** — to su isti
redovi koje kandidati već vraćaju. Bez tog filtera svaka obaveza bi se pojavila
dvaput, jednom bez stanja odluke.

## 2. JEDINA BACKEND IZMENA — I ZAŠTO JE BILA NUŽNA

`/api/rokovi/kandidati` je počinjao od **danas** (`gte(datum_iso, danas)`), pa
istekao rok kroz njega uopšte nije bio dohvatljiv. A istekao rok je prva
kategorija ekrana Danas.

Dodat je **opcioni** `od`. Bez njega ponašanje je bajt u bajt isto — test to
čuva, mutacija M11 ga obara.

Blokator je izmeren, ne pretpostavljen:

```
dana=7 bez `od`            -> 0 redova
dana=7 sa od=danas-90      -> 1 red   (rok istekao pre 82 dana, UNCONFIRMED)
```

Gornja granica se i dalje računa od **danas**, ne od `od`: `dana` znači „koliko
gledam unapred", pa pomeranje početka unazad ne sme tiho da produži pogled u
budućnost (mutacija M10). Neispravan datum je `422`, ne tiho gutanje (M12).

Nijedna druga backend ruta nije dirnuta. Migracija: **0**.

## 3. GLOBALNA LJUSKA

```
Vindex   Danas  Predmeti                    benny13.n@gmail.com   Nalog
```

| pravilo | kako je sprovedeno | dokaz |
|---|---|---|
| četiri prostora kao mentalni model | `domain/spaces.js` drži svih pet redom | test redosleda |
| neizgrađen prostor **ne postoji** | prikazuju se samo `danas` i `predmeti` | `Znanje/Kancelarija/Usklađenost` u DOM-u: **0** |
| nema onemogućenih stavki | — | onemogućenih: **0** |
| nema bočne trake | jedan red u crnoj sceni | — |
| nema globalne pretrage dok ne postoji | — | `input[type=search]` u ljusci: **0** |
| aktivan prostor: linija, ne ispuna | `::after` 2px oxblood + `aria-current="page"` | izmereno |

`spaces.js` namerno razdvaja **„nije izgrađeno"** (stanje proizvoda) od
**„nema pravo"** (stanje naloga). To su dve različite odluke i spajanje bi
značilo da se buduće pravo ne može razlikovati od buduće funkcije. Mutacije M8 i
M9 obaraju svaku od te dve ose zasebno.

Navigacija su prave `<a href>` veze: srednji klik i „otvori u novoj kartici"
rade nativno. Ruter presreće samo običan klik.

## 4. DANAS

```
Danas   subota, 05.09.2026.

ISTEKLO
15.06.2026.   ROK  Rok za reklamaciju uređaja U-2: Gubitak prava na reklamaciju
pre 82 dana        DL-E2E-ADVERSARIAL — test identiteta roka · Nepotvrđeno · predložio sistem

NEDAVNO OTVORENI PREDMETI
… 5 stvarnih predmeta
```

| pravilo | mereno |
|---|---|
| brojeva koji nisu datum (KPI/score) | **0** |
| grafikona / `canvas` | **0** |
| kartica / mreže widgeta | **0** |
| klikabilnih stavki | **0** (svesno — §6 niže) |
| fatalnih grešaka u konzoli | **0** |
| API poziva pri učitavanju | 4: `plan/status`, `rokovi/kandidati`, `kalendar/pregled`, `predmeti` |

**Grupe** se prikazuju samo kad nisu prazne: `Isteklo` → `Danas` → `Sutra` →
`Narednih 7 dana`. Granice su testirane na −1 / 0 / 1 / 7 / 8 (mutacije M5, M6).

**Šta ne ulazi:** odbijen predlog (čovek se izjasnio, to više ne traži pažnju —
nije obrisan, samo nije ovde), i sve dalje od 7 dana. Nivo rizika sam po sebi
nije ulaznica.

**Ukrasni emoji se skida** sa serverskog naslova — emoji je prezentacija koju je
izabrao drugi sloj, ne podatak (mutacija M7).

**Nedavno otvoreni predmeti** se prikazuju **i kada obaveza ima**. Vlasnički
model ih dozvoljava „posebno kada nema obaveza" — dakle ne samo tada. Advokat
čija je jedina obaveza istekla pre 82 dana i dalje ima posao, a prazna donja
polovina ekrana nije ni odmor ni informacija. **Ovo je moja proizvodna procena i
tražim vašu potvrdu.**

Naziv je namerno „otvoreni", ne „korišćeni": registar je uređen po `created_at`,
pa je i naziv takav. Radije tačan naziv nego lepša nedokaziva tvrdnja.

## 5. DELIMIČAN PAD NIJE PRAZAN EKRAN

`Promise.allSettled`, ne `all`. Izmereno ubacivanjem kvara:

| kvar | ishod |
|---|---|
| kalendar pao (503) | upozorenje prikazano · **obaveza i dalje vidljiva** · **naziv predmeta povraćen iz registra** · oznaka „Nepotvrđeno" očuvana |
| kandidati pali (503) | upozorenje prikazano · ročišta bi se i dalje videla |
| **oba pala** | „Obaveze trenutno nisu dostupne · … **Ovo ne znači da obaveza nema.**" — stil greške, ne prazno |
| curi li backend tekst | **ne** (`503`, `detail`, naziv rute — ništa) |

Rezervni izvor naziva postoji zato što rok bez predmeta advokatu skoro ništa ne
znači. Jedan dodatni poziv **samo na putanji greške**.

## 6. SVESNO IZOSTAVLJENO

| stavka | zašto |
|---|---|
| **klik na stavku Danas** | klik mora voditi do najpreciznijeg konteksta (ročište → predmet → Rokovi → to ročište). Dosije ne postoji, a vođenje na vrh registra je tačno ono što vlasnički model zabranjuje. Mrtav klik je gori od izostanka. |
| **potvrdi / odbij** | upis sa pravnim posledicama; pripada kapiji *Rokovi i zadaci*. Ovde se stanje potvrde **saopštava**, ne menja. |
| **globalna pretraga** | kapija G |
| **Znanje, Kancelarija, Usklađenost** | kapije H, I i uslovna — ne prikazuju se ni kao onemogućene |

## 7. KONTEKST PREŽIVLJAVA PRELAZAK

```
Predmeti → pretraga „kalibracija" → 13 predmeta
   → Danas
      → Predmeti:  polje = "kalibracija"   brojač = 13 predmeta
ponovnih učitavanja dokumenta tokom svih prelazaka: 0
```

## 8. RUTIRANJE

| putanja | ishod |
|---|---|
| `/app-v2` | → `/app-v2/danas` (podrazumevano odredište) |
| `/app-v2/danas`, `/app-v2/predmeti` | deep link radi, aktivan prostor tačan |
| `/app-v2/znanje` (nije izgrađen) | → `/app-v2/danas` |
| `/app-v2/xyz` | → `/app-v2/danas` |

`<title>` prati prostor: „Danas · Vindex", „Predmeti · Vindex".

## 9. RESPONSIVE, PRISTUPAČNOST, FULL-BLEED

| viewport | prelivanje | papir jedinstven | crna jedinstvena | tekst <11px | meta <40px | greške |
|---|---|---|---|---|---|---|
| 1440×900 | ne | da | da | 0 | 0 | 0 |
| 1024×768 | ne | da | da | 0 | 0 | 0 |
| 390×844 | ne | da | da | 0 | 0 | 0 |
| 360×800 | ne | da | da | 0 | 0 | 0 |

```
kontrast     18 iscrtanih čvorova, 0 ispod praga; najniži koji prolazi 6,09:1
zum          125% / 150% / 200% — bez horizontalnog prelivanja
tastatura    Skip → Vindex → Danas → Predmeti → Nalog, svaki sa vidljivim prstenom
semantika    <nav aria-label>, <ul>/<li>, <h1>/<h2>, aria-current, aria-live
```

## 10. TESTOVI

```
tests/test_z016_gate_a.py     33 prošlo
+ Z015 skup                   51 prošlo
                              84 / 0
```

**Mutacije: 14 konstruisano, 14 ubijeno.** Među njima: kalendarski rokovi se ne
odbacuju (duplikat obaveze), nepotvrđen se tretira kao potvrđen, degradiran izvor
se prećutkuje, neizgrađen prostor se prikazuje, `od` menja i gornju granicu.

## 11. REGRESIJA

```
Z015 baseline (f7464b45)   15 palo · 7684 proslo · 179 presk. · 769 s
Gate A        (46f842b8)   15 palo · 7717 proslo · 179 presk. · 769 s
```

Masinska razlika skupova padova:

```
NOVO na Gate A : nijedan
NESTALO        : nijedan
proslo         : 7684 -> 7717 = +33   (tacno broj novih testova)
```

**Regresija: nijedna.** Svih 15 padova postoji i na produkcionom SHA i vec je
diferencijalno razreseno u Z014.3 (`ns003_protocol` i `rc_cold_start` su
artefakt sveze `git checkout` kopije; ostali padaju i na goloj produkciji).
Nijedan ne dodiruje `v2/` ni `routers/rok_odluka.py`.

---

## 12. COMMIT-OVI

```
f7464b45  (produkcija / base)
  └ fa31cde3  feat(rokovi): /api/rokovi/kandidati prihvata opcioni `od`
    └ 7772ecd0  feat(v2): Gate A -- globalna ljuska i Danas
      └ 46f842b8  test(v2): Gate A -- ljuska, prostori, Danas
```

## 13. DEPLOYMENT

**Push nije izvršen.** Vlasnički model nalaže STOP posle svake kapije radi
pregleda. Pre-push sažetak:

```
base SHA        f7464b45
range           f7464b45 .. 46f842b8   (3 commita)
migracije       0
legacy fajlova  0   (index.html, vindex.js, vindex.css, sw.js — nedirnuti)
backend         1 ruta, aditivno: `od` na /api/rokovi/kandidati
testovi         33 nova, 0 padova; mutacije 14/14
rollback        f7464b45
```

Možete ga videti bez push-a: `http://127.0.0.1:8021/app` (prijava) →
`http://127.0.0.1:8021/app-v2` — isti kod, stvarni backend, vaši podaci.

## 14. ODLUKE KOJE TRAŽE VAŠU REČ

1. **Nedavno otvoreni predmeti uz obaveze** — prikazujem ih uvek, ne samo kad je
   Danas prazan. Vlasnički model to dozvoljava; potvrdite ili ukinite.
2. **Prozor za istekle rokove je 90 dana.** Istekao rok ne prestaje da važi, ali
   Danas je ekran pažnje, ne arhiva. Vrednost je na jednom mestu i lako se menja.
3. **Četiri nepotvrđena AI roka na vašem nalogu.** Tri su za 15.09. Vindex ih
   sada prikazuje kao predloge — ali odluku o njima (potvrdi/odbij) niko još ne
   može doneti kroz V2. To je kapija *Rokovi i zadaci*.
4. **`/api/predmeti` sa `offset` van opsega i dalje vraća HTTP 500** — otvoren od
   Z015, nedirnut po pravilu „evidentiraj, ne popravljaj automatski".

## 15. VERDIKT

# 🟡 GATE A IMPLEMENTIRAN — CEKA VLASNIKOV PREGLED

Sve je izmereno i zeleno. Zuto je zato sto vlasnicki model nalaze STOP posle
svake kapije — a ne zato sto nesto nije zavrseno.

| provera | ishod |
|---|---|
| podrazumevano odrediste je Danas | ✓ |
| cetiri prostora kao model, prikazani samo izgradjeni | ✓ 0 onemogucenih |
| Danas: 0 KPI, 0 grafikona, 0 kartica | ✓ |
| stavka ulazi samo sa datumom | ✓ |
| nepotvrdjen AI predlog je obelezen kao takav | ✓ **glavni nalaz** |
| ista obaveza se ne pojavljuje dvaput | ✓ |
| delimican pad != prazan ekran | ✓ 3 scenarija |
| kontekst prezivljava prelazak | ✓ |
| bez mrtvih kontrola | ✓ 0 klikabilnih stavki |
| full-bleed 4/4 · kontrast 18/18 · zum 200% | ✓ |
| legacy `/app` dirnut | **ne** — 0 fajlova |
| migracija | **0** |
| regresija | **nijedna** |
| testovi | 84 / 0 · mutacije 14/14 |

Sledeca kapija (B — Predmeti prekalibrisan unutar odobrene ljuske) **ne pocinje**
dok ne vidite ovu.

---

# DODATAK — Z016.1 · CANON RECONCILIATION

HEAD: `500dcd33` · Push: **nije izvršen** · Migracije: **0** · Legacy `/app`: **0 fajlova**

## §16 · ADVERSARIAL TABELA (pre koda)

| # | ISSUE | CURRENT | CANON | RISK | MINIMAL CHANGE |
|---|---|---|---|---|---|
| 1 | date-only admission | samo datum | datum **ILI** odluka, klase razdvojene | odluke koje čekaju ne stižu do advokata | dve klase: `OBAVEZA` / `ZA PROVERU` |
| 2 | nepotvrđeni AI rokovi | u „Isteklo", crvena oznaka | predlog ne sme delovati hitnije od obaveze | AI predlog bio najhitnija stvar na ekranu | zasebna sekcija ispod, mirnija gramatika |
| 3 | nedavni predmeti | stalni blok | fallback | Danas postaje početni portal | samo kad nema ni obaveza ni provera |
| 4 | 90 dana | proizvodna odluka | starost nije poslovno značenje | UI bi tvrdio potpunost | tehnički opseg dohvatanja, dokumentovan |

## §8 · FORENZIKA STANJA U BACKENDU

```
predmet_hronologija kolone:
  akter · created_at · datum · datum_iso · dogadjaj · dokument_id
  dokument_naziv · id · izvor · predmet_id · user_id · vaznost

resen / zavrsen / status / izvrsen / zatvoren / obrisan   ->  NIJEDNE NEMA

_klasifikuj_dogadjaj:  catch-all `return "rok_dokument"`
  -> „Kraj zaposlenja tuzioca kod tuzenog" izlazi kao ROK

cela tabela, sve kancelarije:  55 redova
  izvor:  Counter({'LEGACY_UNKNOWN': 55})
  audit_immutable resource_type='rok':  0 redova

posledica pogadjanja:
  unazad  90 dana ->  1 red,  1 predlog
  unazad 180 dana -> 10 redova, 2 predloga
  unazad 365 dana -> 47 redova, 2 predloga   <- 45 istorijskih cinjenica
```

**Nijedan rok nigde u proizvodu nikad nije potvrđen ni odbijen.** Klasa
„potvrđena obaveza" je danas prazna po podacima, ne po implementaciji.

## IZMENA

Fail-closed: red ulazi u „Za proveru" samo ako `izvor` to **dokazuje**.
Allow-lista `IZVOR_DOKAZUJE_PREDLOG` je namerno prazna. `akter` je slobodan
tekst i pogađanje po njemu obara test.

## MERENO U PREGLEDAČU

```
STVARNI PODACI   obaveza 0 · za proveru 0
                 „Nema obaveza koje trenutno traže postupanje." + 5 nedavnih predmeta
SA OBAVEZOM      NAREDNIH 7 DANA — ROČIŠTE 07.09. 09:30 · ROK 08.09.
                 nedavni blok: 0
```

## REGRESIJA

```
Gate A  (2f592620)   15 palo · 7717 prošlo
Z016.1  (500dcd33)   15 palo · 7719 prošlo

NOVO: nijedan · NESTALO: nijedan · +2 = tačno novi testovi
```

Testovi: 35/35.

## VERDIKT

# 🔴 GATE A BLOKIRAN — KONKRETNA KONTRADIKCIJA U PODATKOVNOM UGOVORU

Kod je spreman i bezbedan. Deploy nije izvršen jer bi vam dao prazan Danas, a
§23 traži da ocenite baš razliku potvrđeno/nepotvrđeno — koja se na stvarnim
podacima ne može prikazati bez pogađanja.

**Odblokira jedna odluka:** koja je kanonska oznaka da je red predlog roka.
(a) backend upisuje `izvor` koji to razlikuje → dodajem vrednost u allow-listu;
(b) odobrite privremenu heuristiku (`akter` sadrži `(AI)`);
(c) Danas ostaje bez klase B do kapije F i deployuje se takav.

**Gate B blokatori:** `/api/predmeti` `offset` van opsega → HTTP 500;
nedostatak vrste i rešenosti u `predmet_hronologija`.
