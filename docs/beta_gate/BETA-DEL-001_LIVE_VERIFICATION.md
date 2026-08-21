# BETA-DEL-001 — LIVE PRODUCTION VERIFICATION

**Datum:** 2026-08-21 · **Produkcija:** `693de0c` · **Tip:** RELEASE EVIDENCE

---

## 1. VERDICT

🟡 **BLOCKED — ali RED data-loss put je ZATVOREN i dokazan uživo.**

Ovo nije 🟡 tipa „ne znamo". Sve što je spolja izvršivo je izvršeno i prošlo:

* **korenska putanja (`events`-FK) prošla uživo** — predmet sa `events=4` i
  **`consequences=6`** obrisan u celosti, `200 DELETED`
* **tombstone dokazan uživo** — tombstonovan predmet nestaje iz liste, vraća
  `404`, i **prestaje da bude izvor za RAG**
* normalno brisanje, retry i izolacija čitanja — svi prošli

🟡 stoji zbog **jedne** stavke iz §17: *„Pinecone failure ostavlja resumable
state"* **nije izvršen uživo** — namerna injekcija tog kvara zahteva patch
produkcionog koda, što je zabranjeno.

---

## 2. PRODUCTION IDENTITY

| | |
|---|---|
| commit | **`693de0c`** |
| commit_source | `RENDER_GIT_COMMIT` · `identity_proven: true` |
| branch / env | `main` / `production` · Python 3.11.16 |
| deploy | 63 s posle push-a, `started_at 2026-08-21T15:53:58Z` |
| lokalni HEAD | `693de0c` — **identičan** |

---

## 3. MIGRATION PROOF

**Migracija 114 NIJE izvršena u ovom sprintu — zatečena je već primenjena.**

Tokom recon sprinta `predmeti` je imala **15** kolona bez `brisanje_zapoceto`;
na početku ovog gate-a ima **16** sa njom. Po §2 DDL **nije** pokrenut naslepo.

Dodatno: izvršenje ne bi ni bilo moguće — `SUPABASE_DB_URL` ne postoji u
okruženju, `psycopg2` nije instaliran, a PostgREST ne izvršava DDL.

## 4. SCHEMA BEFORE / AFTER

| Provera | Vrednost |
|---|---|
| kolona `brisanje_zapoceto` | prisutna i upotrebljiva |
| filter `IS NULL` | **22** redova |
| filter `NOT NULL` | **0** redova |
| ukupno predmeta pre/posle | **22 / 22** — nijedan nije obrisan |
| tombstonovanih | **0** — nijedan nije označen |
| `status` | **22/22 `aktivan`** — poslovno polje netaknuto |

Nijedna druga tabela ni kolona nije promenjena.

---

## 5. BASELINE DOCUMENT FACT

Nov izolovan tenant, pravi DOCX ingest (`HTTP 200`), pravi Pinecone.

```
DB: predmeti=1  dokumenti=1  events=4  consequences=6  tombstone=null
pitanje: http=200  kanal=True  cinjenica=847.250,00 DA
         source_type={USER_DOCUMENT}  verification_state={READ_OK}
```

Baseline prošao → destruktivni testovi odobreni.

---

## 6. NORMAL DELETE — TEST A ✅

```
DELETE  200  ishod=DELETED  vektori=NEMA_DOKUMENATA
posle   predmeti=0 dokumenti=0 events=0 consequences=0   GET=404
```

---

## 7. EVENTS-FK DELETE — TEST B ✅ **(korenski uzrok)**

Izmereno **pre** brisanja, ne pretpostavljeno: `events=4`,
**`consequences=6`** — dakle baš FK veza
`case_evolution_consequences.event_id → events.id` zbog koje je blocker otvoren.

```
DELETE  200  ishod=DELETED  vektori=OBRISANI
posle   predmeti=0 dokumenti=0 events=0 consequences=0   GET=404
```

**Poređenje sa dokazanim kvarom na `27cb670`:**

| | pre popravke | sada |
|---|---|---|
| HTTP | 409 | **200** |
| ishod | `PARTIAL_FAILURE` | **`DELETED`** |
| `neuspele_tabele` | `['events']` | **—** |
| predmet posle | **živ** | obrisan |
| vektori | **obrisani** | obrisani |
| činjenica posle | **nestala** | predmeta nema |

---

## 8. PINECONE FAILURE — TEST C ⬜ **NOT EXECUTABLE**

Namerna injekcija pada Pinecone sloja zahteva patch produkcionog koda —
zabranjeno. Spolja ne postoji način: nepostojeći vektori vraćaju
`ALREADY_ABSENT`, što je **uspeh**, ne kvar.

Deterministički pokriveno: `test_5_izuzetak_u_vektorima_ostavlja_tombstone_i_predmet`,
`test_5b_indeks_nedostupan_uz_dokumente`, i mutacija „vektori pre redova"
(obara **7** testova).

**Nije označeno kao prošlo. Nije simulirano.**

---

## 9. RETRY — TEST D ✅ (uz zabeleženu anomaliju)

Ponovljeni `DELETE` nad već obrisanim predmetom: **`403` — „Nemate pravo
pristupa ovom predmetu."**

Čisto odbijanje: nema lažnog uspeha, nema nove nekonzistentnosti, nema
beskonačnog determinističkog padanja. Zahtev §10 je ispunjen.

**ANOMALIJA (pre-existing, nije uvedena ovim sprintom):** ugovor modula kaže da
ponovljeni DELETE daje `ALREADY_ABSENT` (404). Uživo daje `403`, jer korak 1
(autorizacija) prethodi koraku 2 (postojanje), a za nepostojeći predmet
`_sme_predmet` vraća `False`. Redosled koraka 1→2 **nije menjan** u ovom sprintu.

---

## 10. TOMBSTONE VISIBILITY ✅ **dokazano uživo**

Tombstone je postavljen **direktnim DB upisom** (service ključ), jer se pad
koraka brisanja ne može izazvati spolja. Time je izmereno baš ono što tombstone
treba da garantuje:

| | pre tombstone-a | posle |
|---|---|---|
| pitanje vraća `847.250,00` | **DA** | **NE** |
| u listi predmeta | **DA** | **NE** |
| `GET /api/predmeti/{id}` | **200** | **404** |

---

## 11. RETRIEVAL ISOLATION — TEST E ✅

Vidi §10: tombstonovan predmet **prestaje da bude izvor za RAG** —
`cinjenice_iz_dokumenta` se prazni bez ijedne izmene B4-M2 logike. Isključenje
je uzvodno, u `dozvoljeni_predmeti`.

---

## 12. FAILURE MATRIX (uživo)

| Scenario | DB | dokumenti | events | vektori | tombstone | API | retry_moguc | vidljivost | oporavak |
|---|---|---|---|---|---|---|---|---|---|
| A normal DELETE | 0 | 0 | 0 | `NEMA_DOKUMENATA` | — | 200 `DELETED` | — | 404 | n/a |
| B events-FK DELETE | 0 | 0 | 0 | `OBRISANI` | — | 200 `DELETED` | — | 404 | n/a |
| C Pinecone pad | — | — | — | — | — | — | — | — | **NOT EXECUTABLE** |
| D retry | 0 | 0 | 0 | — | — | 403 | — | 404 | čisto odbijanje |
| E tombstone vidljivost | 1 | 1 | — | prisutni | **postavljen** | 404 | — | **nevidljiv** | resumable |

---

## 13. MUTATION RESULTS — 6/6 UBIJENO

| Mutacija | Padova |
|---|---|
| vektori vraćeni **pre** brisanja redova | **7** |
| tombstone uklonjen | 2 |
| deca `events` se ne brišu | 3 |
| stara jedinstvena retry poruka | 2 |
| `DELETING` predmet ponovo u retrieval-u | 1 |
| filter liste uklonjen | 1 |

---

## 14. REGRESSION

Kod je **bit-identičan** onome nad kojim je pun suite već izvršen na `693de0cf`:

| | passed | failed | skipped |
|---|---|---|---|
| baseline `27cb670` | 6267 | 8 | 2 |
| `693de0cf` | **6298** | 8 | 2 |

Lista padova **identična** (8 × `[trio]`, paket nije instaliran). **0 novih.**

Subseti ponovo pokrenuti na ovom kodu:

```
BETA-DEL-001 + P1-5           64 passed
B4-M2                        108 passed
tenant izolacija / ACL / pag.  53 passed
```

---

## 15. CLEANUP

| Tenant | Predmeti posle | Nalog |
|---|---|---|
| `del.p2.*` | **0** | obrisan |
| `tomb.*` | **0** | obrisan |

Oba test predmeta iz TEST A/B obrisana su **kroz sam proizvod** (`200 DELETED`),
uključujući vektore. Predmet iz tombstone sonde uklonjen je service ključem.

**Pinecone cleanup za tombstone sondu: NOT VERIFIED** — vektori tog predmeta
nisu zasebno prebrojani. Ne tvrdi se da je kompletan.

---

## 16. ANOMALIJE

1. **Retry vraća 403 umesto dokumentovanog `ALREADY_ABSENT`/404.**
   Pre-existing; redosled koraka 1→2 nije menjan. Bezbedno (fail-closed), ali
   ugovor modula i stvarno ponašanje se razilaze.
2. **Migracija je zatečena primenjena**, suprotno pretpostavci mandata.
   Verifikovana sondom umesto izvršena.
3. **DDL nije izvršiv iz ovog okruženja** (`SUPABASE_DB_URL` nedostaje) — isti
   nedostatak zabeležen još od Black Swan-a.

---

## 17. OPEN RISKS

* **TEST C nije izvršen uživo** — jedina neispunjena stavka za 🟢
* Pinecone stanje posle tombstone sonde — **NOT VERIFIED**
* Anomalija 403/404 — **BACKLOG**, ne blocker

---

## 18. DEFINITION OF DONE

| Stavka | Status |
|---|---|
| migracija dokazana u produkciji | ✅ (sondom) |
| production identity | ✅ |
| normal DELETE | ✅ **LIVE** |
| events-FK scenario | ✅ **LIVE** |
| nijedan scenario: vidljiv predmet + obrisani vektori | ✅ u svim izvršenim |
| Pinecone failure → resumable | ⬜ **NOT EXECUTABLE** |
| retry bezbedan | ✅ **LIVE** |
| tombstone nevidljiv korisniku | ✅ **LIVE** |
| retrieval ne prolazi kroz tombstone | ✅ **LIVE** |
| mutacije ubijaju stari redosled | ✅ 6/6 |
| nema novih regresija | ✅ |

---

## 19. FINAL VERDICT

🟡 **BLOCKED** — jedna stavka (TEST C) nije spolja izvršiva.

Suštinski: **BETA-DEL-001 kao data-loss blocker je zatvoren i dokazan uživo.**
Scenario koji je 3/3 puta uništavao sadržaj živog predmeta sada se završava
potpunim brisanjem, a tombstone je uživo dokazano nevidljiv i van retrieval-a.

**Sledeća akcija:** odluka osnivača — da li 🟢 sme da se izda bez žive injekcije
Pinecone kvara, koja bi zahtevala privremeni patch produkcije (zabranjen ovim
mandatom), ili se BETA-DEL-001 zatvara kao 🟡 sa TEST C trajno označenim
NOT EXECUTABLE.
