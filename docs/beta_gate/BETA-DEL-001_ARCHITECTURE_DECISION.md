# BETA-DEL-001 — ARCHITECTURE DECISION RECORD

**Datum:** 2026-08-21 · **Baseline:** `27cb670` · **Status:** ODLUČENO, pre implementacije

---

## 1. POSTOJEĆI DELETION GRAPH

`api.py:6119` → `shared/predmet_deletion.py::obrisi_predmet`

```
1. autorizacija            (_sme_predmet)
2. postojanje              (_predmet_postoji)
3. blokade                 (billing_entries, FK RESTRICT)
4. VEKTORI  ← NEPOVRATNO, PRVI DESTRUKTIVNI KORAK
5. 36 tabela  .delete().eq("predmet_id", …)
6. predmeti red            (CASCADE čisti svojih 16)
```

Svaki `.delete()` je zaseban PostgREST poziv — **nijedna višeiskazna
transakcija ne postoji**. Pinecone je izvan svake DB transakcije.

**Dokazani kvar (3/3):** korak 4 uspe, korak 5 padne na `events`, korak 6 se ne
izvrši → **živ predmet sa obrisanim vektorima**, uz poruku „operacija se može
ponoviti" koja je neistinita.

---

## 2. NOVI DELETION GRAPH

```
1. autorizacija            (nepromenjeno)
2. postojanje              (nepromenjeno)
3. blokade                 (billing_entries — nepromenjeno)
4. TOMBSTONE               ← NOVO; prvi upis, potpuno povratan
5. DB zavisnosti           ← deca sa dolaznim FK PRE roditelja
6. VEKTORI                 ← NEPOVRATNO, ali tek POSLE tombstone-a
7. predmeti red            → DELETED
```

**Jedina promena redosleda koja zatvara blocker:** vektori se pomeraju sa
pozicije 4 na poziciju 6, **iza** tombstone-a i iza svih DB brisanja.

### Zašto ovo eliminiše ORPHAN VEKTOR rizik zbog kog je originalni redosled i
### postojao

Originalni docstring (`:30`) tvrdi: *„vektori pre redova — zaostao vektor uz
obrisan red je curenje"*. To važi **samo ako predmet nestane**. U novom modelu,
u trenutku brisanja vektora predmet **i dalje postoji**, ali je u stanju
`DELETING` i **isključen iz `dozvoljeni_predmeti`** — pa ga RAG ne može
dohvatiti. Ako brisanje vektora padne, vektori ostaju uz **tombstonovan**
predmet koji nije dohvatljiv, i retry ih dokrajči.

Curenje je time nemoguće u oba smera.

---

## 3. STATE MACHINE

Minimalna — dva persistirana stanja i odsustvo reda:

```
ACTIVE     brisanje_zapoceto IS NULL
   │  DELETE
   ▼
DELETING   brisanje_zapoceto IS NOT NULL      ← persistirano, vidljivo sistemu
   │  svi koraci uspeli
   ▼
DELETED    reda nema
```

`DELETING` pokriva i „u toku" i „palo, ponovljivo" — razlika nije u bazi nego u
odgovoru API-ja. Uvođenje trećeg stanja `FAILED` ne bi dodalo nijedan invariant,
a dodalo bi migraciju i grananje.

---

## 4. ZAŠTO NOVA KOLONA, A NE POSTOJEĆI `status`

`predmeti.status` postoji, sve 22 produkcione vrednosti su `'aktivan'`, i nema
`CHECK` ograničenja. Mandat preferira postojeći mehanizam — **odbijeno, sa
razlogom.**

`status` je **poslovno** polje korisnika (`aktivan` / `arhiviran` / …). Upis
`'brisanje_u_toku'` bi kod **neuspelog** brisanja **trajno prepisao** korisnikovu
poslovnu vrednost. To je gubitak podatka — tačno klasa greške koju ovaj sprint
postoji da spreči. Očuvanje stare vrednosti tražilo bi drugu kolonu, čime
prednost nestaje.

Uz to: **samo 9 od 76** `SELECT`-ova nad `predmeti` uopšte filtrira `status`, pa
ponovna upotreba ne bi donela ni automatsko isključivanje.

**Odluka:** `brisanje_zapoceto TIMESTAMPTZ NULL` — aditivno, jednonamensko, bez
rizika po `CHECK` i bez dodira poslovne semantike.

---

## 5. TABELE KOJE BRISANJE DODIRUJE

| Grupa | Broj | Ko briše |
|---|---|---|
| FK `CASCADE` ka `predmeti` | 16 | baza, pri koraku 7 |
| FK `SET NULL` | 4 | baza (namerna odluka šeme) |
| FK `RESTRICT` (`billing_entries`) | 1 | **niko** — blokada, korak 3 |
| bez FK ka `predmeti` (`TABELE_BEZ_FK`) | 36 | aplikacija, korak 5 |
| **dolazna FK deca (novo)** | **1** | **aplikacija, korak 5, PRE `events`** |

---

## 6. DOLAZNE FK ZAVISNOSTI

| Dete | FK | ON DELETE | `predmet_id` | Bilo u politici |
|---|---|---|---|---|
| `case_evolution_consequences` | → `events(id)` **NOT NULL** | **nema → NO ACTION** | **NE** | **NE** |
| `case_intelligence_summaries` | → `events(id)` | nema | NE | da (prazna) |
| `case_actions` | → `events(id)` | nema | NE | da (prazna) |

Samo `case_evolution_consequences` je **NOT NULL** i **nedohvatljiv** preko
`predmet_id` — to je jedini stvarni blokator. Briše se preko:

```
event_id ∈ { events.id | events.predmet_id = <predmet> }
```

`case_intelligence_summaries` i `case_actions` su već u listi i njihove FK su
`NULLABLE`; ostaju kako jesu. **FK-ovi 096/098/099 se NE menjaju.**

---

## 7. PINECONE BOUNDARY

Pinecone ostaje **van** svake DB transakcije — to se ne može promeniti i ne
pokušava se. Umesto atomičnosti, koristi se **redosled**: nepovratna operacija
je poslednja destruktivna, i izvršava se tek kad je predmet već nevidljiv.

---

## 8. RETRY SEMANTICS

Ponovljeni `DELETE` nad `DELETING` predmetom:

* korak 4 je idempotentan — tombstone se prepisuje istom semantikom
* korak 5 je idempotentan — `DELETE … WHERE` nad već praznim skupom
* korak 6 je idempotentan — `ALREADY_ABSENT` je uspeh (`vector_deletion.py:74`)
* korak 7 briše red

**Retry napreduje ili čisto odbija. Nikad ne pravi novo nekonzistentno stanje.**

---

## 9. FAILURE SEMANTICS I API UGOVOR

| Ishod | HTTP | Značenje | Šta je dirano |
|---|---|---|---|
| `DELETED` | 200 | sve uklonjeno | sve |
| `ALREADY_ABSENT` | 404 | nema predmeta | ništa |
| `REFUSED` | 403 | nema prava | ništa |
| `BLOCKED` | 409 | `billing_entries` | **ništa** |
| **`PERMANENT_FAILURE`** | **409** | tombstone se **ne može** upisati | **ništa** |
| **`RETRYABLE_FAILURE`** | **409** | tombstone upisan, korak pao | predmet je `DELETING` |

`PARTIAL_FAILURE` se **ukida kao generički ishod**. Poruka „operacija se može
ponoviti" sme da postoji **isključivo** uz `RETRYABLE_FAILURE`.

---

## 10. READ / RETRIEVAL EXCLUSION

| Površina | Mehanizam |
|---|---|
| RAG retrieval (uklj. B4-M2 dokumentarne činjenice) | `shared/rag_acl.dozvoljeni_predmeti` — **jedno usko grlo**, jedan filter |
| lista predmeta | `GET /api/predmeti` — filter |
| pojedinačan predmet | `GET /api/predmeti/{id}` — 404 |

**B4-M2 logika se ne dira.** Isključenje se dešava uzvodno, na ACL nivou: ako
predmet nije u `dozvoljeni_predmeti`, njegovi vektori ne ulaze u kontekst, pa
`cinjenice_iz_dokumenta` prirodno ostaje prazan. Nijedna linija
`_dokumentarne_cinjenice`, guard-a ni prompt governance-a se ne menja.

---

## 11. MIGRATION IMPACT

Jedna aditivna migracija:

```
ALTER TABLE public.predmeti ADD COLUMN IF NOT EXISTS brisanje_zapoceto TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ... ON public.predmeti (user_id) WHERE brisanje_zapoceto IS NOT NULL;
```

Idempotentna, nedestruktivna. Rollback = `DROP COLUMN` (gubi se samo tombstone).

**Migration tracking ne postoji** — status se dokazuje isključivo sondom šeme.
Zato kod **ne sme pretpostaviti** da je kolona prisutna: ako upis tombstone-a
padne, ishod je `PERMANENT_FAILURE` i **ništa se ne dira**. To je fail-closed i
čini deploy bezbednim u oba redosleda (kod pre migracije ili obrnuto).

---

## 12. ZAŠTO JE OVO DOVOLJNO ZA BETU

Zatvara jedini dokazani RED blocker uz:

* **0 izmena** B4-M2, guard-a, prompt governance-a, tenant izolacije, B1
* **0 izmena** FK šeme (096/098/099 netaknuti)
* **1** aditivnu kolonu
* **1** promenu redosleda (vektori 4 → 6)
* **1** novi korak brisanja (`case_evolution_consequences`)
* **1** filter u ACL usko grlo

Invariant koji se time garantuje:

> **Nijedan predmet ne može biti istovremeno vidljiv korisniku i lišen svojih
> vektora.** U trenutku kad vektori nestanu, predmet je već `DELETING` i
> isključen iz svih read putanja.

Model D (outbox + pomiritelj) rešava i orphan vektore nastale van brisanja —
to nije uzrok ovog blockera i ne ulazi u beta opseg.
