# BETA-DATA-CONFIDENTIALITY-004 — INGEST INTEGRITY FORENSICS & REPAIR

# VERDICT

## 🟡 YELLOW

Lažni uspeh je zatvoren na **svim šest** pisaca ingesta, uz mutation dokaz.
Ali nije GREEN, iz dva razloga koja ne krijem:

1. **UI popravka (SE-03) nema izvršni test.** Menjao sam `static/vindex.js` da
   čita `status` umesto `pinecone_namespace`; to je dokazano čitanjem koda i
   `node --check`, **ne Playwright-om**. Po sopstvenom pravilu ovog projekta
   („izvor/CSS/onclick ništa ne dokazuju"), to nije dokaz.
2. **Uzrok za 43 dokumenta ostaje UNKNOWN** — i to je ispravka izveštaja 003,
   ne detalj.

```
BASELINE:              942678f2  (radno stablo čisto na startu)
TEST COUNT:            5299 → 5326   (+27)
PRODUCTION FILES:      7  (api.py, uploaded_doc/ingest.py, routers/smart_intake.py,
                          routers/drafting.py, routers/dokument.py,
                          drafting/playbook.py, interni_stavovi.py)
                       + static/vindex.js, static/sw.js (CACHE_NAME v133→v134)
MIGRATIONS:            0
PROD DATA MUTATED:     0
```

---

# 1. ROOT CAUSE

Izveštaj 003 je tvrdio jedan uzrok. **Našao sam tri, i nijedan nije bio kvota.**

## FS-001 — uspeh se pretpostavljao, ne dokazivao

`ingest_session()` vraća broj **stvarno upisanih** vektora.
**Nijedan pozivalac ga nikad nije proverio.** `_pinecone_ok` je ostajao `True`
samo zato što izuzetak nije podignut.

## FS-002 — `zip()` je tiho skraćivao

```python
for chunk, vec in zip(manifest.chunks, vectors_raw):
```

`zip` staje na kraćoj sekvenci. Delimičan odgovor embedding provajdera →
upsert-uje se podskup, `len(records)` vrati taj manji broj, i **niko ne
primeti**. Delimičan ingest prijavljen kao potpun.

## FS-003 — klasifikator kvote je bio prešireok

```python
if "429" in _pe_str or "storage" in _pe_str.lower() or "Too Many" in _pe_str:
```

Svaka greška čija poruka sadrži „storage" — **uključujući greške Supabase
Storage-a i poruke koje pominju `storage_path`** — tiho je postajala „kvota",
pa je dokument završavao kao `sacuvano` umesto da podigne grešku.

---

# 2. INGEST STATE MACHINE (stvarna, ne izmišljena)

```
PRIMLJEN ──► ekstrakcija/OCR ──► chunking ──► embedding ──► upsert ──► DB upis
                    │                │            │           │
                    ▼                ▼            ▼           ▼
                  (raise)     total_chunks=0   neslaganje   kvota
                    │          → 422           → raise      → 'sacuvano'
                    │                                       inače → raise 500
                    ▼
                 500 / 422
```

Vokabular statusa u bazi **već postoji i tačan je**:

| status | značenje |
|---|---|
| `na_cekanju` | DB default — red napravljen, ništa nije potvrđeno |
| `sacuvano` | **primljen i sačuvan, NIJE pretraživ** |
| `indeksirano` | **stvarno u indeksu, u celosti** |

Problem nikad nije bio nedostatak vokabulara nego to što ga niko nije popunjavao
na osnovu dokaza. **Nisam pravio paralelni status sistem** (§4).

---

# 3. NALAZ O 43 DOKUMENTA — **UNKNOWN, i to je ispravka izveštaja 003**

003 tvrdi: *„status='sacuvano' je vrednost koju je kod postavljao isključivo na
Pinecone quota grešku."*

**Ta tvrdnja ne stoji.** Istorijski predikat (`ff584d23:api.py:3864`) je
disjunkcija tri tokena, ne dokaz kvote. Iz `sacuvano` sledi samo da je podignut
izuzetak čija poruka sadrži „429", „storage" ili „Too Many" — a to obuhvata i
greške koje sa Pinecone kvotom nemaju veze.

Protivnički pregled je dodao jači argument:

> **OpenAI 429 na `embed_documents` objašnjava izmereno „PRESEK: 0" bolje** od
> Pinecone kvote — jer embedding pada **pre ijednog upserta**, pa nijedan vektor
> ne nastane. Pinecone kvota bi tipično ostavila delimičan trag.

Uz to, 003 sam navodi 6 `pred_*` namespace-ova sa 30 vektora, što protivreči
„43/43 palo iz istog razloga".

**Opservacija stoji (43 dokumenta bez vektora). Pripisani uzrok ne stoji.**
Ovaj sprint je taj klasifikator zamenio **upravo zato što je prešireok da bi se
iz njega izvodio uzrok** — pa ne mogu istim klasifikatorom braniti zaključak.

---

# 4. FALSE-SUCCESS PATHS — SVIH ŠEST

Protivnički pregled je oborio moju prvu verziju popravke: pokrio sam **2 od 4**
pozivaoca. Vratio sam se na uzrok, kako §8 nalaže.

| # | Pisac | Pre | Posle |
|---|---|---|---|
| 1 | `api.py:5204` | `count` se ne proverava | `ingest_je_potpun` |
| 2 | `smart_intake.py:1401` | isto, + hvata SVE izuzetke | `ingest_je_potpun` |
| 3 | `drafting.py:357` | **povratna vrednost se ni ne dodeljuje**, `status` hard-kodovan literal `"indeksirano"` | provera + uslovni status |
| 4 | `dokument.py:301` | `count` se dodeljuje, nikad poredi; **stari klasifikator** | provera + `je_kvota_greska` |
| 5 | `interni_stavovi.py:66` | isti `zip()` bug, skraćen broj **vraćen korisniku** | kapija pre upisa |
| 6 | `drafting/playbook.py:72` | isto | kapija pre upisa |

---

# 5. IMPLEMENTED FIX

Kanonski, jedan vlasnik — `uploaded_doc/ingest.py`:

- `ingest_je_potpun(upisano, ocekivano)` — fail-closed; `(0,0)` je **False**,
  jer dokument bez ijednog chunk-a nije „uspešno indeksiran u celosti".
- `je_kvota_greska(exc)` — sužen skup poruka.
- kapija protiv `zip` skraćivanja, **pre prvog upisa**.
- batch petlja loguje koliko je upisano pre pada — bez toga se orphan vektori
  ne mogu ni prebrojati.

## SE-03 — popravka koju korisnik ne vidi nije popravka

`static/vindex.js` nikad nije čitao `dok.status`. Indikator „vektorizovan" se
izvodio iz `pinecone_namespace`, **koji se upisuje bezuslovno** — pa se dokument
sa `sacuvano` renderovao piksel-identično indeksiranom: zelena tačka, cyan
ikonica, „• klikni za analizu".

Izmenjeno na `dok.status === 'indeksirano'`. `sw.js` `CACHE_NAME` v133 → v134.

---

# 6. MUTATION RESULTS

| Mutacija | Ishod |
|---|---|
| uklonjena kapija protiv `zip` skraćivanja | **2 pada** |
| `ingest_je_potpun` uvek `True` | **9 pada** |
| vraćen preširok klasifikator (`"storage"`) | **2 pada** |
| vraćeno | 27/27 prolazi |

---

# 7. RETRY / IDEMPOTENCY

| Slučaj | Ponašanje |
|---|---|
| ponovni ingest **istog manifesta** | **idempotentan** — `chunk_id` stabilan unutar manifesta, upsert prepisuje |
| ponovni upload **istog fajla** | **pravi duplikate** — `chunker.py:157` daje nov `uuid4` po chunk-ovanju |
| retry posle neuspeha | **ne postoji** — nijedan mehanizam ne pokušava ponovo |

Test `test_i_ponovni_upload_ISTOG_fajla_pravi_duplikate_ID_01` **zaključava
ID-01 kao poznato stanje**: ako neko uvede determinističku šemu, taj test pada
i to je ispravan signal da ga treba obrisati.

**ID-01 nije rešen** (§6 to izričito zabranjuje). Potrebno:
`{document_id}_c{chunk_index}` — obrazac koji u repou već radi
(`knowledge_base.py:106`, `law_upload.py:126`).

---

# 8. AUTHORIZATION REGRESSION — ČISTO

```
tests/test_confidentiality_001.py + 002 + 003:  44 passed
```

F-01 kapija je i dalje fail-closed. Pozadinski radnici **ne ingestuju uopšte**,
pa nemaju čime da je zaobiđu.

---

# 9. ADVERSARIAL FINDINGS

Protivnički pregled je **oborio** prvu verziju. Nalazi i ishodi:

| ID | Nalaz | Ishod |
|---|---|---|
| SE-01 | `drafting.py` ne proverava, status je literal | **POPRAVLJENO** |
| SE-02 | `dokument.py` ne poredi + stari klasifikator | **POPRAVLJENO** |
| SE-03 | UI izvodi stanje iz `pinecone_namespace` | **POPRAVLJENO, bez izvršnog testa** |
| SE-04 | `ingest_je_potpun` je na pozivnom mestu nedostižan | **TAČNO — v. dole** |
| SE-05 | `playbook.py` + `interni_stavovi.py` isti `zip` bug | **POPRAVLJENO** |
| SE-06 | `knowledge_base.py:121` guta svaki izuzetak ingesta | **OTVORENO** |
| SE-07 | `smart_intake` nema `total_chunks==0` gard | **OTVORENO** |

## SE-04 zaslužuje pošten odgovor, ne odbranu

Recenzent je u pravu: pošto `ingest_session` posle FS-002 kapije **uvek** vraća
tačno `total_chunks` kad ne digne izuzetak, `ingest_je_potpun` na pozivnom mestu
danas **ne može da opali**. Sva stvarna zaštita dolazi iz `raise`-a.

Zadržavam ga svesno, kao bravu nad ugovorom: ako neko sutra promeni
`ingest_session` da vraća delimičan broj umesto da diže izuzetak, kapija hvata
promenu. Ali **neću ga predstavljati kao glavni mehanizam** — nije.

---

# 10. REMAINING RISKS

- **SE-03 bez Playwright dokaza** — jedina tvrdnja u ovom izveštaju koja počiva
  na čitanju koda.
- **43 dokumenta i dalje nisu indeksirana.** Ovaj sprint sprečava da se to
  ponovi i čini vidljivim; **ne popravlja postojeće stanje** (to bi bila izmena
  produkcionih podataka, zabranjena).
- **Nema retry mehanizma.** Dokument koji padne ostaje `sacuvano` zauvek.
- **`je_kvota_greska` hvata „429" bilo gde** — OpenAI rate-limit se klasifikuje
  kao kapacitetni problem. Svesno: oba slučaja vode u `sacuvano`, što je
  **istinito stanje**, a alternativa (500) bi izgubila dokument uz orphan blob.
  Ključno je da više nije nevidljivo.
- **SE-06 / SE-07** otvoreni, imenovani.

---

# 11. DEFERRED

`PINE-01`, `CONF-002`, `ID-01`, `STORAGE-RLS` — svi izvan opsega po mandatu.

---

# 12. EXACT NEXT BLOCKER

**ID-01 — deterministička identifikacija vektora.**

Bez nje ne može ni brisanje (`PINE-01`), ni pouzdan re-ingest, ni orphan
detekcija. Sada je i **jedini preostali blokator za retry**: ponovni pokušaj nad
istim fajlom danas duplira vektore umesto da ih zameni.

---

# ZAVRŠNA REČ

Pitanje sprinta je bilo može li Vindex razlikovati „fajl je primljen" od
„fajl je stvarno ingestovan".

**U bazi — sada da, na svih šest pisaca, sa mutation dokazom.**
**U UI-ju — sada verovatno da, ali to nisam dokazao izvršno.**
**Za 43 postojeća dokumenta — ne, i uzrok im ostaje nepoznat.**

Ono što se sme reći bez ograde: ranije je dokument koji nikad nije stigao u
indeks izgledao advokatu identično kao indeksiran, na četiri različite putanje.
Sada ne izgleda.
