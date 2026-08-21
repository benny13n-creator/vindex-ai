# B4-M2 / NALAZ 2 — FORENSIC REMEDIATION REPORT

**Datum:** 2026-08-21 · **Baseline:** `ed02b29f` · **Prethodni izveštaj:** `B4M2_FACT_INTEGRITY.md`

---

## VERDIKT

🟡 **BLOCKED**

NALAZ 2 je **zatvoren i dokazan** na nivou koda, mutacija i diferencijalnog
merenja. Verdikt nije 🟢 isključivo zbog jedne stavke iz Definition of Done:
**živo E2E merenje NS002 scenarija A i J nije izvedeno** — ono traži naplativ
LLM, ingestovan dokument i stanje tenanta, što ovaj sprint ne može da izvede.

Umesto njega priložen je **jači deterministički dokaz za istu tvrdnju**:
`status`, `blocked` i `data` su **bajt-identični** pre i posle izmene na svim
merenim putevima, pa ishod scenarija J ne može da se promeni — ni nabolje ni
nagore.

---

## BASELINE

| | |
|---|---|
| HEAD pre izmene | `ed02b29f` |
| worktree | čist, bez tuđih izmena |
| NS002 (determinističke enkodacije A/J) | 27 passed |
| 4 karakterizaciona testa | 4 passed (tvrde kvar) |
| pun suite | 6215 passed / 8 failed / 2 skipped |

---

## KOREKCIJA RANIJEG NALAZA: 18 IZLAZA, NE 24

Prethodni izveštaj je naveo **24** korisnička izlaza. Tačan broj je **18**.

Uzrok razlike je moja greška u prvom skriptu: ispisivao je jedan red po paru
*(return iskaz × kandidat dict-dodela)*. `return rezultat` postoji na **3**
mesta, a `rezultat` se dodeljuje dict-literalom takođe na **3** mesta → 3×3 = 9
redova umesto 3, dakle **+6 fantomskih**. 18 + 6 = 24.

**Broj „13 bez kanala" je bio TAČAN** — svih 6 fantoma je bilo u koloni „nosi
kanal", pa naduvavanje nije doticalo nalaz.

---

## ROOT CAUSE

Kanal `cinjenice_iz_dokumenta` bio je dodat izlazima koji vraćaju **odgovor**
(HIGH, jedan LOW), ali ne i izlazima koji vraćaju **odbijanje ili blokadu** —
dakle tačno onima koji se izvršavaju kad pravni deo padne. To je situacija zbog
koje je B4 i otvoren: advokat dobija „nema direktnog člana u bazi" bez ijednog
traga o tome šta njegov dokument kaže.

Nije bilo jedinstvenog pravila o tome ko nosi kanal, pa su nastali **sestrinski
izlazi sa različitim ugovorom** — `r3714` (LOW, nosi) i `r3751` (LOW kad je
filtriran kontekst prazan, ne nosi).

---

## MAPA 18 IZLAZA

| ID | return | status / blocked | prov. PRE | prov. POSLE | guard granica |
|---|---|---|---|---|---|
| E1 | r3487 | error / — | NE | **NE** *(pre retrieval-a)* | ne |
| E2 | r3514 | error / — | NE | **NE** *(retrieval pao)* | ne |
| E3 | r3579 | error / False | DA | DA | ne |
| E4 | r3655 | error / False | NE | **DA** | **da** |
| E5 | r3672 | success / True | NE | **DA** | **da** |
| E6 | r3714 | error / False | DA | DA | ne |
| E7 | r3738 | success / — | DA | DA | ne |
| E8 | r3751 | success / — | NE | **DA** | ne |
| E9 | r3853 | error / — | NE | **NE** *(„Sistem zauzet")* | ne |
| E10 | r3863 | success / True | NE | **DA** | **da** |
| E11 | r3874 | success / True | NE | **DA** | **da** |
| E12 | r3908 | success / — | DA | DA | ne |
| E13 | r3941 | error / — | NE | **NE** *(„Sistem zauzet")* | ne |
| E14 | r4000 | error / — | NE | **NE** *(„Sistem zauzet")* | ne |
| E15 | r4011 | success / True | NE | **DA** | **da** |
| E16 | r4022 | success / True | NE | **DA** | **da** |
| E17 | r4047 | success / — | DA | DA | ne |
| E18 | r4052 | error / — | NE | **NE** *(`docs` nije vezan)* | ne |

*(brojevi redova su iz `ed02b29f`; posle izmene su pomereni)*

**Bez kanala: 13 → 6.** Svih 6 preostalih ima dokazan razlog:

* **E1, E2** — `docs` još ne postoji (`docs` se vezuje na r3511). Izmišljanje
  provenance-a bilo bi gore od ćutanja.
* **E9, E13, E14** — „Sistem je trenutno zauzet. Pokušajte ponovo." Sistem ne
  tvrdi ništa o dokumentu; korisnik ponavlja pokušaj.
* **E18** — spoljni `except Exception`. `docs` tamo **nije garantovano vezan**
  (izuzetak može nastati i pre retrieval-a), pa bi poziv mogao da digne
  `UnboundLocalError` i pretvori grešku u pad.

---

## PRAVILO (INVARIANT 11)

Upisano u docstring `_dokumentarne_cinjenice`, da razlika među sestrinskim
izlazima ne bi ponovo nastala:

> Svaki izlaz koji korisniku isporučuje **odgovor ili odbijanje** na postavljeno
> pitanje nosi kanal. **Prolazni infrastrukturni kvar** i **izlaz pre
> retrieval-a** ga ne nose.

---

## REMEDIATION

Sedam izlaza dobija jedan isti aditivni red:

```python
"cinjenice_iz_dokumenta": _dokumentarne_cinjenice(docs, _izvori_neuspeh),
```

Primenjeno **AST-om** (granice dict-a određene parserom), ne tekstualnim
pogađanjem. Nije uveden nijedan novi sloj apstrakcije — poziv je inline, isto
kao na tri izlaza koji su kanal već nosili. Inline je i **nužno**: `docs` se
proširuje na r3683 (injekcija člana), pa bi prethodno izračunata vrednost bila
zastarela.

**Dodavanje je čisto aditivno:** ne dira control flow, ne menja `data`,
`status` ni `blocked`.

---

## GUARD IMPACT

| Provera | Rezultat |
|---|---|
| `status` promenjen | **ne** (8/8 puteva) |
| `blocked` promenjen | **ne** (8/8 puteva) |
| `data` promenjen | **ne** — sha256 bajt-identičan (8/8) |
| guard odluka promenjena | **ne** |
| blokiran odgovor postao odgovor | **ne** |
| tekst dobio novu tvrdnju | **ne** — `data` je identičan i kad dokument postoji i kad ne postoji |

Guard nije pomeran, uklanjan, zaobilažen; nijedan prag nije spuštan; nijedna
klasifikacija nije menjana; prompt governance nije diran.

---

## PROVENANCE INTEGRITY

| Invariant | Dokaz |
|---|---|
| **A** — svaka vrednost potiče iz dokumenta | vrednost izvodi `_dokumentarne_cinjenice` iz `docs`, parsira samo header koji je sistem sam napisao |
| **A** — ništa se ne izmišlja | bez dokumenta kanal je **`[]`**, ne izmišljena činjenica (mereno na sva 3 blokirana puta) |
| **B** — zakon ne postaje dokumentarna činjenica | mutacija „ukloni proveru labele" **obara 12 testova** |
| **C** — provenance ne menja guard odluku | `blocked` identičan, 8/8 |
| **D** — blokirano ostaje blokirano | `data` bajt-identičan, 8/8 |
| **F** — API ugovor kompatibilan | polje je već postojalo uslovno (`is not None`); sada je prisutno češće, nijedan ključ nije uklonjen ni preimenovan |

---

## ADVERSARIAL REZULTATI

| Scenario | Rezultat |
|---|---|
| datum / rok / iznos / subjekt / broj predmeta / činjenična tvrdnja | svi prežive doslovno |
| legal conflict — dokument 500.000,00 vs zakon 50.000,00 | u kanalu je **samo** 500.000,00 |
| datum conflict — dokument 14.03.2026 vs zakon 01.01.1978 | u kanalu je **samo** 14.03.2026 |
| P-1234/26 (dokument) vs P-9999/99 (zakon) | u kanalu je **samo** P-1234/26 |
| isti fakt kroz `filtrirani==[]`, pravnu grešku i guard block | preživljava na sva tri |
| bez dokumenta, na blokiranom putu | `[]` |

---

## NS002 SCENARIO A

**Živo merenje: NIJE IZVEDENO.** Scenario A je ručno E2E merenje (10 pokušaja,
pravi model, pravi Pinecone, ingestovan dokument), ne automatizovan test.

Izvedena zamena: deterministička enkodacija u
`tests/test_ns002_document_fact_authority.py` — **27 passed**, identično
baseline-u.

## NS002 SCENARIO J

**Živo merenje: NIJE IZVEDENO** (isti razlog).

Izvedeni dokaz da J **ne može** da degradira: `data`, `status` i `blocked` su
bajt-identični pre i posle izmene na svim merenim putevima, uključujući guard
granicu. Scenario J meri **tekst odgovora**; tekst je nepromenjen, pa je ishod
nepromenjen.

`test_2_cinjenica_iz_dokumenta_prezivljava_blokadu` — deterministička
J-invarijanta na guard granici — **prolazi**.

> **Napomena bez ulepšavanja:** zatvaranje NALAZA 2 **ne popravlja** J na nivou
> teksta. J je i pre bio 1/10 i takav ostaje. Ova izmena čini činjenicu
> dostupnom u **odvojenom strukturisanom kanalu** koji UI prikazuje zasebno.
> Da li je to dovoljno za advokata je proizvodna odluka, ne inženjerska.

---

## KARAKTERIZACIONI TESTOVI

Tri `# KVAR` testa nosila su izričitu uputu: *„kad se blokator zatvori MORAJU
pasti i tada se ZAMENJUJU dokazom pokrivenosti — ne brišu se."*

Posle izmene **pala su tačno ta tri**, a kontrolni test je ostao zelen. Sekcija
je zatim zamenjena dokazom pokrivenosti, sa `OLD / NEW / WHY` zaglavljem po
NS002B presedanu. Nijedna asercija nije oslabljena — nove su **strože** (svaka
tvrdi i `blocked`, i odsustvo vrednosti iz zakona, i nepromenjen tekst).

---

## MUTACIJE — 4/4 UBIJENO

| Mutacija | Ishod |
|---|---|
| kanal skinut sa svih izlaza koji ga nose | 6 failed |
| kanal skinut **samo** sa „pravna greška" | 2 failed |
| provera labele uklonjena (zakon ulazi u kanal) | **12 failed** |
| pad izvora više ne gasi kanal | 1 failed |

Druga mutacija je bitna: dokazuje pokrivenost **po izlazu**, ne samo zbirno.
`main.py` posle svake vraćen bajt-identično (`sha256` 80b57dd9…).

### Mutacija koja je PRVO PREŽIVELA — i zašto

Mutacija „zakon ulazi u kanal dokumenta" je u prvom prolazu **prošla
neprimećeno**. Uzrok nije bio proizvod nego moj fixture: zakonski pasus je bio
**jednolinijski**, pa je `telo` posle `partition("\n")` bilo prazno i pasus je
ispadao i bez provere labele. Stvarni pasus iz `_formatiraj_match` je
**višelinijski** (`ZAKON:\nČLAN:\n\nCITABILNI TEKST:`). Kad je fixture učinjen
vernim, ista mutacija obara 12 testova.

Bez tog koraka INVARIANT B ne bi bio meren, a paket bi bio zelen bez pokrića.

---

## REGRESSION TESTOVI

```
tests/test_b4m2_fact_integrity.py           49 passed   (34 -> 49)
  sekcije 1-3  integritet navoda (NALAZ 1)  30
  sekcija 4    NALAZ 2 + API granica        19
NS002 + NS002B                              27 passed  (= baseline)
B4 + B4-M2 subset                          100 passed
guard / halucinacija / blokada subset      275 passed
```

Uključen je i test **API granice na blokiranom putu** — mesto na kome su
`izvori_neuspeh` i `cinjenice_iz_dokumenta` već jednom umrli, pa je popravka
postojala u agentu i u `vindex.js`, a klijent je nikad nije video.

---

## PUN SUITE

| | passed | failed | skipped |
|---|---|---|---|
| baseline `ed02b29f` | 6215 | 8 | 2 |
| posle izmene | **6230** | 8 | 2 |

`6230 = 6215 + 15` — tačno broj novih testova. Lista padova je **identična**
baseline-u (`diff` = prazan): 8 `[trio]` varijanti koje padaju jer **`trio`
nije instaliran**, pa se parametri ne preskaču nego pucaju. Pre-existing, ista
klasa kao PRG-001 env gap. Zavisnosti nisu dirane.

---

## CACHE DISCIPLINA

Svi probe-ovi i testovi u ovom sprintu vođeni su sa isključenim L1+L2 kešom
(`_supa_cache_get` / `_supa_cache_set` patch-ovani, `M._CACHE.clear()`).
**Nijedan red nije upisan u produkcionu `ai_cache` tabelu u ovom sprintu.**

Incident iz prethodnog sprinta (ključ `83e7f5cf7bae9fe681391ff9367bdd79`) je
tada identifikovan, obrisan i provereno je ostalo 0 redova.

---

## FAJLOVI

```
main.py                              +47 / -2   (7 aditivnih polja + INVARIANT 11)
tests/test_b4m2_fact_integrity.py    sekcija 4 zamenjena, +API granica
docs/beta_gate/B4M2_NALAZ2_REMEDIATION.md   (nov)
```

Nula izmena u: `_dokumentarni_citat`, `ORIGIN_HIERARCHY_INSTRUCTIONS`, stream
ruti, RLS, auth, enkripciji, šemi, migracijama, zavisnostima, UI/UX.

---

## PREOSTALI RIZICI

1. **Živo A/J merenje nije izvedeno** (dokazano nemoguće u ovom okruženju).
   Jedina neispunjena stavka DoD-a.
2. **Scenario J ostaje 1/10 na nivou teksta.** NALAZ 2 to ne popravlja i ne
   tvrdi da popravlja.
3. **E9/E13/E14/E18 nemaju kanal.** Odluka je obrazložena, ali nije dokazano da
   je za korisnika bez posledica — **NOT PROVEN**, ne „bezbedno".
4. NALAZ 3 (`_dokumentarni_citat`), NALAZ 4 (`ORIGIN_HIERARCHY_INSTRUCTIONS`),
   NALAZ 5 (stream) — netaknuti, van opsega.
5. 8 pre-existing `[trio]` padova; okruženje, ne proizvod.

---

## SLEDEĆA AKCIJA

**Izvesti živo E2E merenje scenarija A i J** na deploy-ovanom kodu (10 pokušaja
svaki, isti dokument i ista pitanja kao NS002) i uporediti sa `A = 10/10`,
`J = 1/10`. To je jedina stavka koja deli ovaj nalaz od 🟢 VERIFIED.
