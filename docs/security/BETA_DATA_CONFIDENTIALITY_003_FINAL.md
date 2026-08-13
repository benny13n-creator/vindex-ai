# BETA-DATA-CONFIDENTIALITY-003 — RAG ACL + DOCUMENT LIFECYCLE FORENSICS

# VERDICT

## 🔴 RED

**F-01 je zatvoren** — dokazano runtime-om, adversarialno i mutacijom.

**PINE-01 nije, i neće biti u ovom sprintu.** §8 mandata izričito nalaže STOP
pre implementacije brisanja ako ne postoji deterministička identifikacija
vektora. Ne postoji. Nisam je izmislio.

Sprint je usput izmerio nešto ozbiljnije od obe stavke: **Pinecone ingest je pao
za svih 43 klijentska dokumenta i nikad nije ponovljen.**

```
BASELINE:                690981cc  (radno stablo čisto na startu)
TEST COUNT:              5281 → 5299   (+18)
PRODUCTION FILES:        3 izmenjena (api.py, app/services/retrieve.py,
                                      + nov shared/rag_acl.py)
MIGRATIONS:              0
MUTACIJA PROD. PODATAKA: 0   (nijedan upis/brisanje u Pinecone ni Supabase)
```

---

# A. F-01 — ROOT CAUSE

`app/services/retrieve.py:1850` je pretraživao `kancelarija_{id}` namespace sa:

```python
{"type": {"$in": ["case_doc", "draft_final"]}}
```

— dakle **sve trajne dokumente cele kancelarije**, za svakog aktivnog člana.

Kanonska kapija za čitanje predmeta (`api.py:4163-4189`, `get_predmet`) propušta
po **tačno dva** osnova:

1. vlasnik — `predmeti.user_id == pozivalac` (`:4168`)
2. izričito delegiran — `predmet_delegiranja.na_user_id == pozivalac AND status='aktivno'` (`:4179`)

**Članstvo u kancelariji nije osnov.** Član koji na `GET /api/predmeti/{tuđi_id}`
dobija 404, ovom putanjom je dobijao **do 5 doslovnih pasusa** iz tog predmeta u
LLM kontekstu (`retrieve.py:2163`).

## Zašto je nastalo

Nije zaboravljeno nego **nedovršeno**. `shared/kancelarija_utils.py:44` u
sopstvenom docstringu kaže da `predmet_id` stoji u metapodacima vektora
*„za scoping unutar tog namespace-a"*. Mehanizam je ugrađen po dizajnu; filter
koji bi ga koristio nikad nije napisan. Metadata `predmet_id` postoji na sva tri
mesta upisa (`api.py:5209`, `drafting.py:359`, `smart_intake.py:1402`).

---

# B. F-01 — FIX

**`shared/rag_acl.py`** — jedini vlasnik odluke, tačno ogledalo `get_predmet`.

Tri odluke vredne obrazloženja:

**`predmet_saradnici` se namerno NE računa.** Tabela postoji
(`migrations/011_saradnja.sql:6`), puni je `saradnja.py:160`, čita je
`/api/saradnja/moji-predmeti`. Ali `get_predmet` je nikad ne konsultuje —
saradnik vidi naziv predmeta u listi, a sam predmet mu vraća 404. Uključiti je
ovde značilo bi **dati pristup koji kanonska kapija ne daje**. Ako proizvod to
želi, odluka se donosi u `get_predmet` pa se odrazi ovde. (Zasebna
nekonzistentnost proizvoda, prijavljena.)

**Sentinel je `None`, ne `{}`.** `retrieve.py:963` radi `if filter:` — prazan
dict **tiho uklanja filter** i pretražuje ceo namespace. To je tačan mehanizam
kojim bi se F-01 ponovo otvorio. Zato `None` znači „ne pretražuj namespace",
a ne „pretraži bez ograničenja".

**Granica za `$in`.** Advokat sa hiljadama predmeta je realan; Pinecone metadata
filter nije za liste proizvoljne dužine, a `_pretraga_ns` guta izuzetke — odbijen
filter bi izgledao kao „nema rezultata", tiho. Iznad 400 se sužava na trenutni
predmet, ili se namespace preskače. **Uže, nikad šire.**

## Šta fix NE menja

Pretraga preko više predmeta („Institutional Learning", 2026-07-26) **ostaje**.
Menja se samo skup: umesto svih predmeta u kancelariji, oni koje pozivalac
stvarno sme da vidi. **Za solo advokata se ne menja ništa** — namespace je
`user_{id}`, svi predmeti su njegovi.

---

# C. RAG AUTHORIZATION MATRIX

|  | ISTI TENANT | DRUGI TENANT |
|---|---|---|
| **isti predmet** | **ALLOW** | DENY |
| **drugi predmet, autorizovan** (vlasnik ili aktivna delegacija) | **ALLOW** — izričito pravilo proizvoda | DENY |
| **drugi predmet, neautorizovan** | **DENY** ← ovo je bilo ALLOW | DENY |
| **obrisan predmet** | DENY | DENY |
| **obrisan dokument** | DENY (kroz predmet) | DENY |

`?` iz mandata je popunjen merenjem `get_predmet`, ne pretpostavkom.

---

# D. RETRIEVAL CALL SITES

AST sweep: **106 read call-site-ova, 34 produkcijskih.**

- **14 javnih korpusa** (`zakoni_rs`, `sudska_praksa`, `upravna_praksa`,
  `misljenja`, web3/CARF-DAC8) — hardkodirani, bez tenanta po dizajnu.
- **9 privatnih namespace-ova** — jedino mesto gde se ACL meri.
- **11 samo-statistika.**

**Putanja sa tenant ali BEZ predmet autorizacije nad klijentskim podacima:
tačno jedna — F-01.** Ostalih 7 kandidata pregledano i odbačeno (per-user
namespace-ovi gde je tenant jedini subjekt, ili javni korpusi).

## Strukturni rizici imenovani, ne popravljeni

| Rizik | Nalaz |
|---|---|
| `validate_session` (`session.py:47`) | **nema sopstvenu autorizaciju**; sva 3 poziva su bezbedna samo zato što pozivaoci pre njega zovu `_verify_pred_namespace_ownership`. Disciplina pozivaoca, ne svojstvo funkcije. |
| `retrieve.py:963` `if filter:` | `{}`/`None` tiho uklanjaju filter. Moj kod ne može da proizvede `{}`, ali obrazac ostaje. |
| `/test-pinecone` (`api.py:2416`) | upit bez namespace-a nad `__default__`, vraća celu metadatu prvog pogotka. Gejtovan `X-Admin-Key`, fail-closed bez env-a. `__default__` je **izmereno prazan**. |
| `static/vindex.js:15662` | `ns.replace(/^(pred_|tmp_)/,'')` ne skida `kancelarija_` prefiks → „Analiza dokumenta" iz kartice predmeta **ne radi** za dokumente posle 2026-07-26. Fail-closed. Van opsega. |

---

# E. PINE-01 — ROOT CAUSE

| Putanja brisanja | Storage | DB | **Pinecone** |
|---|---|---|---|
| **Dokument** | — | — | **ENDPOINT NE POSTOJI** |
| **Predmet** | — | — | **ENDPOINT NE POSTOJI** |
| Klijent | preživi | soft | **preživi** — ime/JMBG kao **plaintext** u `text` metadata, dok su DB kolone šifrovane |
| **GDPR nalog** (`gdpr.py:201`) | **preživi** | samo `profiles.email/full_name` | **preživi** |
| Beleška znanja | — | hard | briše se (`kb_{uid}_{id}`) |
| Playbook / interni stavovi | — | — | `delete_all` po namespace-u |
| Retention cron | — | 3 tabele | **samo istekli `tmp_*`** |

`shared/audit_immutable.py:58-72` sam beleži da su `predmet_delete` i
`dokument_delete` *rezervisani* unosi **bez ijednog pozivaoca**.

---

# F. VECTOR IDENTIFIER MODEL — **NE POSTOJI**

Ovo je kapija koja zaustavlja §9.

- `uploaded_doc/chunker.py:157` → `chunk_id = str(uuid.uuid4())`, i
  `ingest.py:94` koristi baš to kao Pinecone `id`. **Goli uuid4, nigde zapisan.**
- `document_id` (`predmet_dokumenti.id`) nastaje **posle** upsert-a i **nije ni
  u jednoj metadata**.
- `predmet_dokumenti` **nema kolonu za ID-eve vektora** — 0 pogodaka za
  `vector_ids|pinecone_ids` u svim migracijama.
- Jedini per-dokument ključ, `session_id`, **više se ne upisuje**: Sprint 001 je
  prenamenio `storage_path` (`api.py:5247`). **Regresija uvedena popravkom** —
  pre nje se gubio original, posle nje identifikacija.

**Zato brisanje NIJE implementirano.** Mandat §8: *„Do NOT invent deletion based
on text matching. Do NOT delete by similarity."* Najuži izvodljiv filter danas
je `{"predmet_id": X}` = **ceo predmet**, ne dokument.

Preduslov za §9 je ID šema `{document_id}_c{chunk_index}` — obrazac koji u ovom
repou **već postoji** (`knowledge_base.py:106`, `law_upload.py:126`) i radi.

Indeks je **serverless** (`vindex-ai`, aws/us-east-1, dim 3072, `pinecone==8.1.1`).
Podrška za `delete(filter=)` na serverless-u je **UNKNOWN** — merenje bi tražilo
write poziv, koji je zabranjen. `Index.list(prefix=...)` + `delete(ids=[...])`
jeste podržan, ali je danas beskorisan jer su ID-evi slučajni.

---

# G. DELETE LIFECYCLE — ŠTA JESTE ZATVORENO

Brisanje **nije** implementirano, ali jedno svojstvo dolazi besplatno iz načina
na koji je F-01 zatvoren, i zaključano je testovima:

> **Autorizacija se izvodi iz TRENUTNOG stanja baze, ne iz metapodataka vektora.**
> Zato brisanje predmeta iz baze čini njegove vektore **nedohvatljivim** — i pre
> nego što ijedan vektor bude obrisan.

To zatvara napad *„obrisan dokument je i dalje pretraživ"* (§10.1-2) i ispunjava
§13 (*„prefer authorization derived from canonical current state"*).

**To NIJE brisanje i NE zadovoljava GDPR čl. 17.** Podatak i dalje postoji kod
Pinecone-a. Razlika je između *nedostupnog* i *obrisanog*, i mora se reći tako.

---

# H. PARTIAL FAILURE — **NIJEDAN MEHANIZAM NE POSTOJI**

Nema outbox-a, retry-ja, reconciliation posla ni `needs_cleanup` zastavice.

- Pinecone uspeo + DB pao → 500, blob se briše, **vektori ostaju zauvek**
  (kod to priznaje na `api.py:5232-5243`).
- Pinecone pao na kvoti + DB uspeo → `status='sacuvano'`, dokument nevidljiv
  RAG-u, **bez ijednog signala korisniku**.
- `knowledge_delete` vraća `{"ok": true}` i kad Pinecone brisanje padne.

---

# I. ORPHAN BEHAVIOR — IZMERENO, 100% RAZILAŽENJE U OBA SMERA

```
DB predmet_dokumenti:              43 reda, 43 distinct pred_* namespace-a
Pinecone pred_* namespaces:         6  (30 vektora)
PRESEK:                             0
Orphan A (DB bez vektora):         43  (100%)
Orphan B (vektori bez DB reda):     6  (100%, 30 vektora)
kancelarija_* / user_* namespaces:  0  (0 vektora)
```

## Najozbiljniji nalaz sprinta, a niko ga nije tražio

**Svih 43 dokumenata ima `status='sacuvano'`.** Verzija koda živa u periodu
njihovog nastanka (`ff584d23:api.py:3857`) postavlja tu vrednost **isključivo**
na Pinecone 429/quota grešku.

> **Pinecone ingest je pao za svih 43 klijentska dokumenta i nikad nije ponovljen.**
> Sav RAG nad klijentskim dokumentima danas radi iz `tekst_sadrzaj` kolone.

To objašnjava i zašto je izmerena izloženost F-01 bila 0: nije bilo šta da
procuri. Rupa je bila stvarna i živa **od prvog uspešnog upload-a**.

30 vektora u 6 `pred_*` namespace-ova je istovremeno **nedostupno**
(`_verify_pred_namespace_ownership` traži `predmeti.id == session_id`; izmereno
**0/6**) i **neobrisivo** (`cleanup.py:38` gleda samo `tmp_*`).

**Alat za orphan detekciju ne postoji**, a za tip B pri sadašnjoj ID šemi
**nije ni moguć**.

---

# J. ADVERSARIAL RESULTS

| Pitanje iz §17 | Odgovor |
|---|---|
| Mogu li dobiti chunk iz drugog predmeta? | **NE** — mereno nad stvarnim vraćenim kontekstom |
| Mogu li dohvatiti obrisan dokument? | **NE** — ACL iz trenutnog stanja |
| Vektor posle DB brisanja? | **NE dohvatljiv** (ali **NIJE obrisan**) |
| Fallback putanja? | **NE** — `praksa.py:212` isti filter, isti javni ns |
| Pozadinski radnik zaobilazi ACL? | **NE** — nijedan ne prosleđuje `kancelarija_namespace` |
| Prazan filter vraća sve? | **NE** — `None` preskače namespace; `{}` se ne može proizvesti |
| Namespace nadjačava autorizaciju? | **NE** — ime nikad ne dolazi od korisnika |
| Retry zaobilazi proveru? | **NE** — 0 retry-ja koji šire obim |
| Cross-tenant? | **NE** |

---

# K. MUTATION RESULTS

```
vraćen stari filter {"type": ...}  →  4 od 18 testova PADA
                                      uključujući test curenja tuđeg teksta
vraćeno                            →  18/18 prolazi
```

Preostalih 14 su ACL-izvor, fail-closed i kontrola nad alatom — ne mere filter.

**Zašto je mutacija ovde uopšte značila nešto:** postojeći
`test_institutional_rag_upgrade.py` gradi `mock_index` čiji `query()`
**ignoriše `filter`**. Takav test prolazi i sa kapijom i bez nje. `_LazniIndeks`
u novom fajlu stvarno primenjuje `$in` semantiku — i diže grešku na svaki
operator koji ne razume, da nikad ne prođe tiho.

---

# L. REGRESSION

```
novi security testovi:     18 passed
institutional RAG suite:   35 passed
full suite:                5299 passed / 2 skipped / 0 failed
no:randomly ✓   seed=11 ✓
```

**4 postojeća testa su pala i to je bio dokaz, ne problem** — zvali su retrieval
bez ikakve autorizacije, pa ih je fail-closed grana preskočila. Ažurirani su da
**izjave** autorizaciju; mere i dalje isto (rangiranje, vremensko opadanje,
labelovanje). Nijedan nije oslabljen.

---

# M. REMAINING UNKNOWN

| Stavka | Zašto nedokazivo |
|---|---|
| `delete(filter=)` na serverless indeksu | merenje traži **write** poziv — zabranjeno |
| Poreklo 30 orphan vektora | traži čitanje njihove metadata, tj. sadržaja klijentskih dokumenata |
| Cena 2 dodatna DB upita u 4-sekundnom `wait_for` budžetu (`api.py:5443`) | nije mereno pod opterećenjem |
| RLS na `storage.objects` | prenet iz -002, nepromenjen |

---

# N. REMAINING RED / YELLOW

| ID | Nalaz | Nivo |
|---|---|---|
| **PINE-01** | brisanje ne postoji; GDPR čl. 17 nesprovodiv nad Pinecone kopijom | **RED** |
| **INGEST-01** | Pinecone ingest pao za 43/43 dokumenta, bez signala korisniku | **RED** |
| **ID-01** | nema determinističke identifikacije vektora — preduslov za sve gore | **RED** |
| **CONF-002** | portal čuva nešifrovano (iz -002, van opsega ovog sprinta) | **RED** |
| PF-01 | nema mehanizma za delimičan neuspeh | YELLOW |
| ORPH-01 | nema alata za orphan detekciju | YELLOW |
| SAR-01 | `predmet_saradnici` se puni ali ne daje pristup | YELLOW |
| JS-01 | „Analiza dokumenta" ne radi za dokumente posle 2026-07-26 | YELLOW |

---

# O. BETA IMPACT

| Putanja | Ocena |
|---|---|
| RAG nad sopstvenim predmetima | **SAFE FOR BETA** |
| RAG preko predmeta iste kancelarije | **SAFE FOR BETA** — sada po ACL-u, dokazano |
| RAG cross-tenant | **SAFE FOR BETA** |
| Dohvat obrisanog predmeta kroz RAG | **SAFE FOR BETA** |
| Pretraga javnih korpusa | **SAFE FOR BETA** |
| **Brisanje dokumenta / predmeta** | **NOT SAFE** — endpoint ne postoji |
| **GDPR brisanje naloga** | **NOT SAFE** — Storage i Pinecone preživljavaju |
| **Ingest dokumenta u Pinecone** | **NOT SAFE** — 43/43 pao, tiho |
| Orphan stanje | **NOT SAFE** — 100% razilaženje, bez detekcije |

---

# NEXT PRIORITY

1. **INGEST-01** — pre svega ostalog. Nema smisla graditi brisanje nad
   pipeline-om koji ne upisuje. Uz to: korisnik danas ne dobija nikakav signal
   da mu dokument nije indeksiran.
2. **ID-01** — deterministička ID šema `{document_id}_c{chunk_index}`, obrazac
   koji u repou već radi. Bez nje §9 ne sme da počne.
3. **PINE-01** — brisanje, tek posle 1 i 2.
4. **CONF-002** — enkripcija portala (iz -002).

---

# ZAVRŠNA REČ

Traženi cilj je bio dvostruk: da bude tehnički nemoguće da korisnik jednog
predmeta kroz RAG dobije poverljiv sadržaj drugog, i da brisanje dokumenta
stvarno ukloni njegovu pretraživu reprezentaciju.

**Prvi deo je ispunjen i dokazan.** Drugi nije — i nije mogao biti, jer sistem
danas ne ume da kaže koji vektori pripadaju kom dokumentu. To se ne popravlja
brisanjem po sličnosti; popravlja se identifikacijom, pa tek onda brisanjem.

Usput se pokazalo da je pitanje trenutno teorijsko iz najgoreg mogućeg razloga:
**klijentski dokumenti uopšte i ne stižu do Pinecone-a.**
