# BETA-DATA-ID-01 — FINAL REPORT & IDENTITY DECISION

# VERDICT

## 🟡 YELLOW

Deterministički identitet je uspostavljen i dokazan. **`PINE-01` je odblokiran**
za dokumente ubuduće.

Nije GREEN iz jednog razloga koji se ne da zaobići: **veza dokument → vektor je
u produkciji 100% prekinuta u oba smera** (izmereno), a identitet važi samo za
ono što se ingestuje **od sada**. Za 43 postojeća dokumenta i 30 postojećih
orphan vektora ovaj sprint ne menja ništa — i ne sme, jer bi to bila izmena
produkcionih podataka.

```
BASELINE:               82450875   (radno stablo čisto na startu)
COMMIT:                 v. git log
FILES CHANGED:          shared/vector_identity.py (nov), uploaded_doc/ingest.py,
                        routers/drafting.py, routers/law_upload.py
MIGRATIONS:             0   — identitet ne traži nijednu novu kolonu
PROD DATA MUTATIONS:    0
```

---

# IDENTITY MODEL

```
vector_id = {scope}__{verzija}__k{chunk_schema}_c{chunk_index}
```

| Nivo | Vrednost | Odakle |
|---|---|---|
| **document_id** | `predmet_dokumenti.id` — **NIJE u ID-u vektora**, v. dole | postoji, ali tek POSLE upsert-a |
| **scope** | `predmet_id`, inače `session_id` | poznat PRE upsert-a |
| **version_id** | `manifest.source_sha256` (32 heks znaka) | postoji |
| **chunk_id** | `chunk_index` + `chunk_schema` | postoji |
| **tenant** | `predmet_id` u metapodacima + namespace vlasnika | postoji |

## WHY — zašto `predmet_id`, a ne `document_id`

Forenzika je izmerila da **sva tri pisača koja prave DB red rade upsert PRE
insert-a** (`api.py:5205→5290`, `smart_intake.py:1401→1508`,
`drafting.py:357→414`). `document_id` u trenutku upsert-a **ne postoji**.

Dve mogućnosti: promeniti redosled, ili graditi identitet iz onoga što je već
poznato. Izabrana je druga — jer je `predmet_id` + `content_sha256` dovoljan za
sve što misija traži, a promena redosleda upisa na tri najprometnije putanje
nosi rizik koji ništa ne kupuje.

`vx_document_id` postoji kao **opciono** polje u `metapodaci_identiteta()` za
pisače koji ID dobiju ranije.

## ALTERNATIVES CONSIDERED

| Opcija | Zašto odbijena |
|---|---|
| `uuid4` (postojeće) | nije deterministički — cela misija postoji zbog toga |
| samo `hash(sadržaj)` | **dva tenanta sa istim fajlom dobili bi ISTE ID-eve** i prepisali se međusobno. RULE 12. |
| `document_id + chunk_index` | `document_id` ne postoji u trenutku upsert-a; uz to ne razlikuje verzije |
| nova kolona `vector_ids` | traži migraciju; §16 zabranjuje migraciju bez dokazane potrebe — a potrebe nema |
| promena redosleda upisa | rizik na tri najprometnije putanje, bez dobitka |

## SECURITY CONSEQUENCES

**Heš NIJE autorizacija (RULE 4).** `verzija` služi identitetu i integritetu.
Kapija ostaje `api.py::get_predmet` (vlasnik ili aktivna delegacija) i
`shared/rag_acl.py`. Poklapanje heša između dva korisnika **ne spaja** njihove
podatke, jer im se `scope` razlikuje — dokazano testom.

**Pristup nije proširen (RULE 5).** Nijedan ACL nije dirnut; `predmet_saradnici`
i dalje ne daje pristup.

## GDPR CONSEQUENCES

`Index.list(prefix=prefiks_dokumenta(predmet_id, sha))` vraća **tačno** chunk-ove
jedne verzije jednog dokumenta → `delete(ids=[...])` postaje precizan. Do sada je
najuži izvodljiv zahvat bio **ceo predmet**.

To odblokira `PINE-01` — **ali samo za dokumente ingestovane od sada.**

## RETRY CONSEQUENCES

Ponovni ingest istog fajla daje **iste ID-eve** → `upsert` prepisuje umesto da
duplira. Dokazano: `INGEST #1` → 5 vektora, `INGEST #2` → i dalje 5, ne 10.

---

# PROOF

| Svojstvo | Dokaz |
|---|---|
| isti ulaz → isti ID | + isti ID iz **drugog procesa** (`subprocess`) |
| ponovni ingest → idempotentan | broj vektora se ne menja |
| delimičan embedding → blokiran | 0 upsert poziva |
| cross-tenant → odvojen | isti fajl, dva predmeta → različiti ID-evi |
| cross-document → izolovan | prefiks pogađa 3, ostavlja 6 |
| promena verzije → nov identitet | obe verzije opstaju (RULE 9) |
| promena chunking šeme → nov identitet | `k1` ≠ `k2` |
| bez identiteta → nema upisa | `NedovoljanIdentitet`, 0 poziva |

---

# CALL-SITE COVERAGE

```
fizičkih Pinecone upsert mesta:  9
kroz kanonski `ingest_session`:  6   → svi pokriveni identitetom
van njega:                       3
```

| Van kanonskog | Stanje |
|---|---|
| `knowledge_base.py:105` | **već deterministički** (`kb_{uid}_{id}`), jedini sa preciznim delete-om |
| `auto_discovery.py:199` | **već deterministički** (`discovery_{sha256}`); founder-only, javni korpus |
| `batch_ingest.py:63` | generički helper; founder-only, javni korpus |

`law_upload.py` je **popravljen** — v. dole.

---

# MUTATION RESULTS

| # | Mutacija | Očekivano | Stvarno |
|---|---|---|---|
| A | nasumičan ID nazad | pad | **5 pada** |
| B | uklonjeno vezivanje za dokument (`scope`) | pad | **5 pada** |
| C | uklonjeno vezivanje za tenanta | pad | **prvo 0 → test popravljen → 2 pada** |
| D | uklonjena verzija | pad | **4 pada** |
| E | dozvoljen delimičan `zip` | pad | **3 pada** |
| F | uspeh bez rezultata ingesta | pad | **9 pada** |
| G | uklonjen ACL filter | pad | **6 pada** |
| UI | vraćen `!!pinecone_namespace` | pad | **3 pada (Playwright)** |
| REG | vraćen prazan `source_sha256` | pad | **1 pada** |

## Mutacija C je bila jedini stvarni nalaz nad sopstvenim testovima

Prvo **nije oborila ništa**. Uzrok: `predmet_id` u metapodatke stiže i kroz
`extra_metadata`, pa je provera bila slepa za to KOJIM putem binding nestane.
Po §14 je popravljen **test**, ne proglašena mutacija bezopasnom: novi test meri
posledicu — prolazi li upisan vektor kroz **pravi** ACL filter iz
`shared/rag_acl.py`. Uklonjeno iz oba izvora → 2 pada.

---

# ADVERSARIAL RESULTS (§13)

| # | Scenario | Ishod |
|---|---|---|
| 1 | isti fajl dva puta | **PASS** — idempotentno |
| 2 | isti fajl kroz drugi endpoint | **PASS** — scope se razlikuje, ne prepisuje |
| 3 | retry posle timeout-a | **PASS** — isti ID-evi |
| 4 | retry posle delimičnog embeddinga | **PASS** — ništa nije upisano, pa nema šta da se popravlja |
| 5 | izmenjen dokument | **PASS** — nova verzija |
| 6 | nova verzija istog dokumenta | **PASS** — obe opstaju |
| 7 | isti sadržaj drugog klijenta | **PASS** — različit scope |
| 8 | isti sadržaj drugog tenanta | **PASS** |
| 9 | ručno promenjen `chunk_index` | **PASS** — drugi ID |
| 10 | promenjena chunking verzija | **PASS** — `k1` ≠ `k2` |
| 11 | vektor bez DB reda | **UNKNOWN** — detekcija moguća ubuduće, alat ne postoji |
| 12 | dokument bez vektora | **UNKNOWN** — isto |
| 13 | obrisan dokument + stari vektor | **PASS** — nedohvatljiv preko `rag_acl` (003) |
| 14 | neautorizovan retrieval | **PASS** — nedirnuto iz 003 |
| 15 | neautorizovano brisanje | **N/P** — brisanje ne postoji (PINE-01) |

---

# NALAZ INVENTARA KOJI JE OBORIO MOJU IMPLEMENTACIJU

Forenzički inventar je našao **regresiju koju je uveo ovaj sprint**:

`routers/drafting.py:344` prosleđuje `"source_sha256": ""`. Fail-closed kapija
(RULE 6) na to diže `NedovoljanIdentitet`, a `drafting.py` taj izuzetak **guta**
i vraća `False` — pa bi **svaka promocija odobrenog nacrta tiho prestala da
radi**, bez ijedne poruke.

Popravka nije bila da se kapija olabavi, nego da nacrt dobije stvarnu verziju:
heš sopstvenog teksta. Pokriveno testom koji **vozi pravu funkciju**
(`_promote_staged_draft_to_pinecone`), ne njen izvor.

## Ispravka netačne tvrdnje u mom kodu

Prva verzija `shared/vector_identity.py` je tvrdila da obrazac „već radi u
produkciji — `law_upload.py:126`". **Netačno**: `law_docs` ima **0 redova**, a
ID-evi u `zakoni_rs` su md5 iz `semantic_chunker.py:107`.

Stvarni dokazani naslednik je `{stabilni_id_izvora}__chunk_{index}`, izmeren na
**407.795 živih vektora** u `sudska_praksa`. Docstring je ispravljen.

## Sedmi pisač koji nijedan raniji sprint nije prijavio

`routers/law_upload.py:120` je radio `except Exception: continue` nad
embedding-om — preskoči ceo batch i nastavi. Zakon je završavao u indeksu **sa
rupama**, a funkcija vraćala broj kao da je sve prošlo. Zamenjeno `raise`-om +
provera dužine.

---

# STATUS SEMANTICS (§10) — ZATVORENO IZVRŠNO

Sprint 004 je ovo popravio ali dokazao samo čitanjem koda, i zato završio kao
YELLOW. Sada postoji **Playwright** test koji vozi pravu `pred_loadDetail` sa
presretnutim mrežnim odgovorom: dva dokumenta identična u svemu osim `status`,
**oba sa popunjenim `pinecone_namespace`**.

Prva verzija testa je poredila ceo HTML i **prolazila je i pod mutacijom** — jer
se kartice ionako razlikuju po nazivu fajla. Zaoštrena na sam indikator (klasa
tačke + izračunata boja ikonice). Sada sva tri testa padaju kad se vrati
`!!pinecone_namespace`.

---

# ORPHAN DETECTION (§11) — STRATEGIJA, NE IMPLEMENTACIJA

Sada je moguća, jer je ID izvodiv iz stanja baze:

```
za svaki red u predmet_dokumenti:
    prefiks = prefiks_dokumenta(predmet_id, content_sha256)
    Index.list(prefix=prefiks, namespace=pinecone_namespace)
    → prazno  = dokument bez vektora   (orphan tip A)

za svaki vektor:
    vx_scope + vx_verzija → traži red u predmet_dokumenti
    → nema reda = vektor bez dokumenta (orphan tip B)
```

**Uslov koji još nije ispunjen:** `content_sha256` je popunjen na **0 od 43**
reda, a računa se na **dva različita ulaza** — `api.py:5164` heširа bajtove
fajla, `smart_intake.py:1341` heširа tekst. Isti PDF kroz dva pipeline-a daje
dva različita heša. Dok se to ne ujednači, tip A detekcija radi samo za
dokumente ingestovane od sada.

---

# OPEN FINDINGS

| ID | Nalaz | Nivo |
|---|---|---|
| **G-08** | veza dokument → vektor je u produkciji **100% prekinuta u oba smera**: 43 reda / 0 vektora, 6 namespace-ova / 0 redova | **RED** |
| **G-06** | brisanje vektora dokumenta ne postoji; `routers/gdpr.py` ima **0** referenci na Pinecone → GDPR čl. 17 neizvodljiv postojećim kodom | **RED** |
| **ID-02** | `content_sha256` se računa na dva različita ulaza (bajtovi vs tekst) i popunjen je na 0/43 reda | **HIGH** |
| **G-09** | `dokument.py:191` poredi `predmeti.id == session_id`; izmereno 0/6 i 0/43 poklapanja → grana uvek 404, komentar na `:452` je činjenično netačan | **HIGH** |
| **G-11** | 43/43 živa dokumenta su `sacuvano`; **nijedan** `indeksirano` | **HIGH** |
| **INT-01** | `routers/intake.py:318` piše u **nepostojeću kolonu** `session_id` → svaki insert baca 42703 i tiho pada na fallback | MEDIUM |
| **AD-01** | `auto_discovery.py:197` `continue` na prazne embeddinge — tihi delimičan ingest, founder-only javni korpus | MEDIUM |

---

# NEXT BLOCKER

## Je li `PINE-01` odblokiran? **DELIMIČNO.**

**Odblokiran** za dokumente ingestovane **od sada**: prefiks izdvaja tačno jednu
verziju jednog dokumenta, `Index.list(prefix=)` + `delete(ids=)` je podržan i na
serverless indeksu.

**Nije odblokiran** za postojeće podatke, iz dva razloga koja se moraju rešiti
pre nego što se GDPR brisanje sme obećati:

1. **43 postojeća dokumenta nemaju nijedan vektor**, a 30 postojećih vektora
   nema nijedan dokument. Za njih identitet ne postoji retroaktivno i ne može
   se izvesti — jedini put je re-ingest, što je izmena produkcionih podataka.
2. **`content_sha256` je prazan na 43/43 reda** i računa se nedosledno. Bez
   njega se prefiks ne može rekonstruisati iz baze ni za buduće brisanje po
   zahtevu korisnika.

**Sledeći sprint mora biti ID-02** (ujednačiti i popuniti `content_sha256`), pa
tek onda `PINE-01`.

---

# ZAVRŠNA REČ

Tri principa iz §19 misije:

| Princip | Stanje |
|---|---|
| „ne možemo obrisati ono što ne možemo identifikovati" | **mereno svojstvo** — za nove dokumente |
| „ne možemo zaštititi ono što ne možemo vezati za vlasnika" | **mereno svojstvo** — `scope` u ID-u i ACL filteru |
| „ne možemo tvrditi da je ingest uspešan bez dokaza šta je upisano" | **mereno svojstvo** — od sprinta 004, sada i sa identitetom |

Ali najteži problem nije ID. Identitet je **preduslov**, ne rešenje: u
produkciji danas ne postoji nijedan vektor klijentskog dokumenta koji bi se
mogao obrisati, jer nijedan nikad nije ni upisan.
