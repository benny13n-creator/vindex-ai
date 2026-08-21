# BETA-DEL-001 — FORENSIC REMEDIATION REPORT

**Datum:** 2026-08-21 · **Baseline:** `27cb670` · **ADR:** `BETA-DEL-001_ARCHITECTURE_DECISION.md`

---

## VERDICT

🟡 **BLOCKED**

Remedijacija je **implementirana i deterministički dokazana**: 29 novih testova,
**6/6 mutacija ubijeno**, puna regresija bez ijednog novog pada.

🟡 a ne 🟢 iz jednog razloga: **migracija 114 nije pokrenuta**, pa živi E2E dokaz
ne postoji. Do tada je brisanje fail-closed (`PERMANENT_FAILURE`, ništa se ne
dira) — bezbedno, ali brisanje ne radi.

---

## ŠTA JE PROMENJENO

| Fajl | Promena |
|---|---|
| `migrations/114_predmet_tombstone.sql` | **nova** — `brisanje_zapoceto TIMESTAMPTZ` + delimičan indeks |
| `shared/predmet_deletion.py` | redosled (vektori 4 → 6), tombstone korak, `PARTIAL_FAILURE` → `RETRYABLE`/`PERMANENT`, brisanje dece `events` |
| `shared/rag_acl.py` | jedan filter u `dozvoljeni_predmeti` |
| `api.py` | razdvojene poruke + `retry_moguc`, isključenje iz 4 read putanje |
| `tests/test_beta_del_001_deletion_integrity.py` | **nov**, 29 testova |
| `tests/test_p15_predmet_deletion.py` | testovi 8–10 prepisani (OLD/NEW/WHY), dvojnik proširen |
| `tests/test_p15_t3_integritet.py` | matrica ishoda proširena novim ishodima |

**Nedirano:** B4-M2 · guard · prompt governance · tenant izolacija · B1 ·
`vector_deletion.py` karantin · `billing_entries` RESTRICT · FK 096/098/099 ·
COST/RATIO/SEC/B3 nalazi.

---

## NOVI TOK

```
1. autorizacija      2. postojanje      3. blokade (billing_entries)
4. TOMBSTONE         ← prvi upis; bez njega se STAJE, ništa se ne dira
5. DB redovi         ← deca `events(id)` PRE `events`
6. VEKTORI           ← nepovratno, ali predmet je već nevidljiv
7. `predmeti` red    → DELETED
```

Korenska ispravka: politika je modelovala samo **odlazne** FK
(tabela → `predmeti`). `case_evolution_consequences` visi o `events(id)`
(`NOT NULL`, bez `ON DELETE`) i **nema `predmet_id`**, pa je bila nedohvatljiva
jedinom predikatu. Sada se briše preko `event_id IN (…)`, **pre** `events`.
**Šema nije menjana.**

---

## FAILURE INJECTION — REZULTATI

| Injekcija | Stanje pre | Ishod | Vektori | Tombstone | `predmeti` red | Oporavak |
|---|---|---|---|---|---|---|
| `events` FK pad | aktivan + dokument | `RETRYABLE_FAILURE` | **nedirani** | upisan | ostaje | retry napreduje |
| `case_evolution_consequences` FK pad | isto | `RETRYABLE_FAILURE` | **nedirani** | upisan | ostaje | retry napreduje |
| `zadaci` DB izuzetak | isto | `RETRYABLE_FAILURE` | **nedirani** | upisan | ostaje | retry napreduje |
| Pinecone izuzetak | isto | `RETRYABLE_FAILURE` | NEUSPEH | upisan | **ostaje** | retry napreduje |
| indeks nedostupan | isto | `RETRYABLE_FAILURE` | NEUSPEH | upisan | ostaje | retry |
| tombstone nemoguć (bez migracije) | isto | `PERMANENT_FAILURE` | **nedirani** | **ne** | ostaje | ništa nije dirano |
| `billing_entries` blokada | isto | `BLOCKED` | nedirani | **ne** | ostaje | n/a |
| tuđi tenant / bez prava | isto | `ALREADY_ABSENT`/`REFUSED` | nedirani | **ne** | ostaje | n/a |
| retry posle `ALREADY_ABSENT` vektora | tombstonovan | `DELETED` | idempotentno | — | obrisan | — |

**Ni u jednom scenariju ne postoji stanje „vidljiv predmet + obrisani vektori".**

---

## MUTATION TESTING — 6/6 UBIJENO

| Mutacija | Padova |
|---|---|
| vektori vraćeni **pre** brisanja redova (stari redosled) | **7** |
| tombstone uklonjen | 2 |
| deca `events` se ne brišu | 3 |
| stara jedinstvena retry poruka | 2 |
| `DELETING` predmet ponovo u retrieval-u | 1 |
| filter liste uklonjen | 1 |

---

## REGRESSION

| | passed | failed | skipped |
|---|---|---|---|
| BEFORE (`27cb670`) | 6267 | 8 | 2 |
| AFTER | **6298** | 8 | 2 |

**NEW:** +31 test (29 nov paket + 2 iz proširene matrice ishoda)
**REMOVED:** 0 · **FAILED:** ista lista (8 × `[trio]`, paket nije instaliran)
**Lista padova identična baseline-u — 0 novih.**

### Incident tokom sprinta

Prvi pun prolaz dao je **6 novih padova**. Uzrok: filter sam ubacio **u lanac**
PostgREST poziva, a šest postojećih testova tvrdi tačan oblik tog lanca
(`chain.range.assert_called_once_with(0, 199)`).

**Testovi nisu oslabljeni.** Promenjen je moj pristup: provera se radi **nad
rezultatom** (`_je_u_brisanju`), ne nad upitom. Semantika ista, lanci netaknuti,
površina manja — i otpala je potreba za sondom kolone.

---

## API UGOVOR

| Ishod | HTTP | `retry_moguc` | Poruka |
|---|---|---|---|
| `DELETED` | 200 | — | uspeh |
| `ALREADY_ABSENT` | 404 | — | nema predmeta |
| `REFUSED` | 403 | — | nema prava |
| `BLOCKED` | 409 | — | ništa nije promenjeno |
| `PERMANENT_FAILURE` | 409 | **false** | „ponavljanje neće pomoći" |
| `RETRYABLE_FAILURE` | 409 | **true** | „označen za brisanje… ponovite" |

Stara poruka „operacija se može ponoviti" više **ne može** da se pojavi uz
neuspeh koji je trajan.

---

## READ EXCLUSION

`GET /api/predmeti` · oba dashboard upita · `GET /api/predmeti/{id}` → **404** ·
`dozvoljeni_predmeti` → van RAG-a.

B4-M2 nije diran: isključenje je **uzvodno**, na ACL nivou. Ako predmet nije
dozvoljen, njegovi vektori ne ulaze u kontekst i `cinjenice_iz_dokumenta`
prirodno ostaje prazan.

---

## LIVE E2E

**NIJE IZVEDEN.** Migracija 114 nije pokrenuta. Bez nje `_upisi_tombstone` pada
→ `PERMANENT_FAILURE` → ništa se ne dira. To je namerno fail-closed i čini
deploy bezbednim u oba redosleda, ali znači da živog dokaza nema.

---

## DEFINITION OF DONE

| Stavka | Status |
|---|---|
| nema više LIVE + VECTORS GONE | **DETERMINISTIČKI DOKAZANO** (mutacija obara 7 testova) |
| Pinecone se ne briše pre poznatih DB blockera | DOKAZANO |
| tombstone persistiran | DOKAZANO (kod + migracija) · **živo NOT VERIFIED** |
| `DELETING` nije retrievable | DOKAZANO |
| retry idempotentan | DOKAZANO |
| retryable/permanent semantika tačna | DOKAZANO |
| failure injection prolazi | 9/9 |
| mutacije padaju kako treba | 6/6 |
| legacy brisanje prolazi | DOKAZANO |
| cross-tenant fail-closed | DOKAZANO |
| B4-M2 zelen | DOKAZANO (0 izmena, regresija čista) |
| guard nepromenjen | DOKAZANO |
| regresija bez novih padova | DOKAZANO |
| **migracija proverena na stvarnoj šemi** | ⬜ **NIJE POKRENUTA** |
| **production identity posle deploy-a** | ⬜ |
| **live E2E brisanje** | ⬜ |

---

## SLEDEĆI KORAK

1. **Pokreni `migrations/114_predmet_tombstone.sql`.**
2. Javi — proveravam sondom da je kolona stvarno prisutna.
3. Push + deploy, pa **3 nezavisna živa pokušaja**, od kojih bar jedan sa
   prirodnim `events`-FK scenarijem.
4. Tek tada BETA-DEL-001 sme da dobije 🟢.
