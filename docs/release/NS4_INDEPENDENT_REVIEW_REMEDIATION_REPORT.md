# NS4 — Ispravke po nezavisnom pregledu

**Predmet pregleda:** lokalni commit `2388df3398842ea7bb76f69ac894d5394fc0f9f0` (Night Sprint IV), osnova `cc8bd5485210f0a9ea67d6f725fc2060a2957b50`
**Grana:** `night/ns4-institutional-intelligence` (lokalna; na GitHub-u ne postoji)
**Datum:** 2026-10-19
**Klasifikacija:** **PARTIAL PASS — BLOCKERS REMAIN** (obrazloženje u §10)

Ništa nije pushovano, spojeno ni pušteno. Nema migracija, produkcionih operacija, pravih Pinecone upisa ni plaćenih poziva modela.

---

## 0. Početne provere

| Provera | Rezultat |
|---|---|
| Grana | `night/ns4-institutional-intelligence` |
| HEAD | `2388df3398842ea7bb76f69ac894d5394fc0f9f0` (očekivano) |
| `git status --porcelain` | prazno |
| Poreklo | `HEAD^` = `cc8bd548…`; `merge-base --is-ancestor cc8bd548 HEAD` = da |
| Remote | `git fetch origin main` → `cc8bd5485210…` (main se nije pomerio); grana na origin-u ne postoji |

Uslov za STOP nije ispunjen, pa je rad nastavljen.

---

## 1. R1 — promena SAMO vrste spora

**PROBLEM.** `routers/learning.py::zabeleži_ishod` je preračun `case_patterns` vezivao za `not isti_ishod`, gde `isti_ishod` = isti ishod i isti faktori. Kada advokat promeni samo `predmeti.tip` i pošalje isti ishod, `outcome_log` se upisuje sa novom vrstom spora (upsert), a preračun se preskače. Doprinos tada ostaje u staroj vrsti, a nova ga ne dobija.

**DOKAZ (RED na 2388df33).** `test_r1_promena_samo_vrste_spora_premesta_doprinos` → `AssertionError: doprinos ostao u staroj vrsti spora`.

**MINIMALNA ISPRAVKA** (`routers/learning.py:218-220`, `:258`):
- dodato je `ista_vrsta = bool(postojeci_ishod) and postojeci_ishod.get("tip_spora") == tip_spora`;
- preračun se radi kad je `not (isti_ishod and ista_vrsta)`. Preračun i dalje obuhvata obe vrste spora, novu i prethodnu (`_vrste`).

Bez promene ostaje ono što zavisi samo od `isti_ishod`: `recommendation_log`, generisanje lekcija i polje `ponovljen_ishod`. Promena vrste spora ne pokreće novi poziv modela.

**TEST.** Posle ispravke važi:
- `outcome_log` ima jedan red, sa `tip_spora="porodicni"`;
- stara vrsta nema doprinos;
- nova vrsta ima tačno `{"svedoci": (1,0,1), "vestacenje": (1,0,1)}`;
- nema duplih parova (vrsta, faktor).

Faktori su namerno poslati drugim redosledom, da se proveri da redosled ne utiče.

**NEGATIVNA KONTROLA.** Isto slanje bez ikakve promene ne dira `case_patterns` (`test_r1_kontrola_isto_slanje_ne_dira_obrasce`).

**MUTACIJA M1** (vraćeno `if not isti_ishod:`) → 1 failed.

---

## 2. R2 — istinitost stanja indeksa i retrieval

**PROBLEM.** Pravilo važenja `services/law_brain.vazece_overe` je tražilo samo `approved`, `is_lawyer_approved=True` i isti predmet, a ne i `pinecone_indexed=True`. Posle nepotpunog upisa ili pada usred upisa važi sledeće:
- deo delova (chunk-ova) može fizički postojati u Pinecone-u sa `origin=LAWYER_VERIFIED` i `parent_id` = staging id;
- staging red je `approved` sa `pinecone_indexed=False`.

Oba puta koja čitaju vektore kancelarije su te delove služila kao kompletan, overen izvor:
- RAG kancelarijska grana: `app/services/retrieve.py:2415` → `_vazece_overe_matcheva`;
- Law Brain pretraga: `services/law_brain.py:893` → `vazece_overe`.

**Mapa veze** (proverena u kodu, ne pretpostavljena):

| Karika | Gde | Ponašanje |
|---|---|---|
| Jedini proizvođač `LAWYER_VERIFIED` vektora | `routers/drafting.py::_promote_staged_draft_to_pinecone` (grep `ORIGIN_LAWYER_VERIFIED`: jedino mesto upisa) | vraća `True` samo ako je `ingest_je_potpun(upisano, total_chunks)` |
| Upis stanja | `routers/drafting.py:1439` | `pinecone_indexed = promoted`, uvek posle pokušaja promocije (tako je od uvođenja u `2577eb31`, 2026-07-26) |
| Čitaoci namespace-a kancelarije | `retrieve.py` (`_kanc_future`) i `law_brain.pretrazi_znanje_kancelarije` | oba filtriraju `LAWYER_VERIFIED` kroz `vazece_overe`. Treći poziv `_pretraga_ns` (`api.py:5663`) čita samo `sudska_praksa`/`upravna_praksa` |
| Law Brain „verified_artifacts“ | `services/law_brain.artifact_item` | čita `staging_memory`, ne Pinecone. Već razlikuje `APPROVED_INDEXED` i `APPROVED_NOT_INDEXED`; nije menjano |

**MINIMALNA ISPRAVKA.**
- `services/law_brain.py:844-864`: `vazece_overe` čita i `pinecone_indexed` i traži `pinecone_indexed is True`. Strogo `True`: string `"true"` i nedostajuća vrednost ne važe.
- `routers/drafting.py:1446-1453`: poruka više ne tvrdi „nacrt nije pretraživ“, jer deo delova možda fizički postoji. Sada kaže ono što sistem zna: upis „nije potvrđen kao potpun“, pa se nacrt „ne koristi kao overen izvor u znanju kancelarije“.
- Ista poruka je u V2 ekranu `frontend-v2-ng/src/nacrt-predmeta.js:126`.

Nema retry-ja, migracije ni novog toka.

**Kompatibilnost sa drugim putevima indeksiranja.** Konflikt nije nađen. Jedini proizvođač ovih vektora uvek upisuje `pinecone_indexed`, a `True` samo za potpun upis. Uslov STOP za ovu stavku zato nije ispunjen. Granice koje ostaju:

- **Pad upisa stanja posle uspešnog upisa.** Ako `update({"pinecone_indexed": True})` (`drafting.py:1439`) padne posle uspešnog ingest-a, ruta vraća 500, a vektori postoje sa `pinecone_indexed=False`. Sa novim pravilom se ne serviraju (fail-closed, uži skup). Ranije su se servirali.
- **Stari redovi.** Za staging redove promovisane pre provere potpunosti ingest-a (BETA-DATA-CONFIDENTIALITY-004 / SE-01), `pinecone_indexed=True` je mogao biti upisan i za nepotpun upis. Ovo pravilo te redove ne može da otkrije. Provera traži read-only SQL nad produkcijom i nije rađena.
- **Kratak prozor posle odobrenja.** Između kraja ingest-a i upisa `pinecone_indexed=True` vektori se ne serviraju. To je uži skup, nikad širi.

**TESTOVI** (`tests/test_ns4r_nezavisni_pregled.py`):
- tabela pravila sa 7 slučajeva: indeksiran ✓, nepotpun ✗, bez podatka ✗, string `"true"` ✗, odbijen ✗, na čekanju ✗, overa pozajmljena drugom predmetu ✗;
- kroz stvarnu rutu `POST /api/staging/{id}/approve` i stvaran `retrieve_documents` (ACL iz stvarnog `shared/rag_acl`):
  - nepotpun upis i izuzetak posle dela upisa → `indexed=False`, `INDEKSIRANJE_NIJE_USPELO`, red `(approved, True, False)`, vektor se NE servira;
  - poruka ne tvrdi „nije pretraživ“ i ne tvrdi „dodat u bazu znanja“;
  - **pozitivno:** potpun upis → vlasnik dobija overen nacrt;
  - **autorizacija:** kolega iz iste kancelarije bez delegiranja ne dobija nacrt (stvaran ACL), a overa pozajmljena drugom predmetu se odbacuje;
  - neodobren nacrt ne važi, čak ni sa `pinecone_indexed=True`;
  - greška baze → fail-closed (ništa se ne servira).

**MUTACIJA M2** (uklonjen uslov `pinecone_indexed`) → 5 failed. **M7** (vraćena stara poruka) → 1 failed.

---

## 3. R3 — stvarna veličina uzorka sličnih predmeta

**PROBLEM.** Ruta je modelu davala prvih 8 znakova id-a i po njima vezivala odgovor:
```python
predmet_by_prefix = {p["id"][:8]: p for p in sa_ishodom}
```
Predmeti sa istim prefiksom su se slivali u jedan, pa je JEDAN predmet brojan kao više predmeta.

Postojeći test `test_uzorak_prikazan_i_bez_tvrdnje_o_uzroku` je imao sva četiri predmeta sa prefiksom `aaaaaaaa`. Prolazio je sa `uzorak == 4`, iako su sve četiri stavke bile isti predmet.

**REPRODUKCIJA (RED na 2388df33).** `test_r3_isti_prefiks_ne_umnozava_jedan_predmet`: četiri predmeta sa istim prefiksom daju ids `[x, x, x, x]` i `uzorak=4`.

**MINIMALNA ISPRAVKA** (`routers/learning.py:561-566`, `:575`, `:605`, `:612-628`). Algoritam sličnosti je isti i model je isti; menja se samo identitet:
- model dobija i vraća PUN `predmet_id`, a rezerva bez modela koristi pun id;
- vezivanje ide po punom id-u. Stari oblik `predmet_id_prefix` prihvata se samo kada je prefiks JEDINSTVEN među kandidatima, a dvosmislen ili nepoznat identitet se odbacuje;
- isti predmet se broji jednom (`vidjeni`);
- `uzorak = len(result)` je zato broj jedinstvenih prikazanih predmeta;
- `_MIN_UZORAK = 3`, `NEDOVOLJNO_PODATAKA` i napomena o nepouzdanosti su nepromenjeni.

**TESTOVI.**
- **Isti prefiks:** nijedna stavka i `NEDOVOLJNO_PODATAKA`. Proizvoljno pripisivanje jednom predmetu nije dozvoljeno.
- **Četiri različita identiteta:** prvih 8 znakova se razlikuje. Prompt sadrži pun id svakog predmeta, `uzorak=4`, `OPIS_ISTORIJE`.
- **Model vrati isti predmet 4 puta:** `uzorak=1`.
- **Nepoznat id i prazan prefiks:** nema stavki, `uzorak=0`.
- **Postojeći NS4 test** sada koristi četiri međusobno različita identiteta (i u prvih 8 znakova) i dodatno proverava da su 4 stavke 4 različita predmeta.

**MUTACIJE.**
- M3 (prefiks bez provere jedinstvenosti) → 1 failed;
- M4 (bez deduplikacije) → 1 failed;
- M8 (model opet dobija 8 znakova) → 1 failed.

Napomena: prva verzija testova **nije** hvatala M3 i M8. Pooštrene su (provera da je rezultat prazan za dvosmislen prefiks i provera sadržaja prompta), pa su mutacije ponovljene. Oba stanja su u `mutacije.log` dokaza: konačno 8/8 uhvaćeno.

---

## 4. R4 — nedostupan izvor nije prazna istorija

**PROBLEM.** U `GET /api/learning/slicni-predmeti/{id}`:
- greška čitanja `predmeti` vraćala je `_bez_uporedivih()`, odnosno „Nema zatvorenih predmeta sa zabeleženim ishodom“ (`NEDOVOLJNO_PODATAKA`);
- greška čitanja `outcome_log` davala je `outcomes_map = {}`, sa istim ishodom.

Pad baze je tako predstavljan kao dokaz da istorija ne postoji.

**MINIMALNA ISPRAVKA** (`routers/learning.py:496-497`, `:533-536`, `:551-553`). Oba čitanja na grešku vraćaju `HTTP 503` sa porukom „Istorija ishoda kancelarije trenutno nije dostupna — ovo NIJE potvrda da sličnih predmeta nema.“. Isti obrazac 503 već postoji u istom fajlu za čitanje `outcome_log` pri upisu ishoda. Ruta nema pozivaoca u UI-ju (grep `slicni-predmeti` u frontendu: nema pogodaka), pa se nijedan ekran ne menja.

**TESTOVI.**
- `test_r4_greska_citanja_nije_prazna_istorija[predmeti|outcome_log]` → 503;
- kontrola `test_r4_kontrola_prazna_istorija_je_uspesno_procitana`: uspešno pročitana prazna istorija daje `NEDOVOLJNO_PODATAKA` i `uzorak=0`, ne 503.

**MUTACIJE.** M5 (predmeti → prazno) → 1 failed; M6 (outcome_log → prazno) → 1 failed.

---

## 5. Granice preračuna `case_patterns` (dokaz, bez ispravke)

`_preracunaj_obrasce` (`routers/learning.py:113-150`) čita stranice `outcome_log`, računa u memoriji i zatim pojedinačno ažurira ili ubacuje redove. To su zasebni PostgREST pozivi, bez transakcije i bez zaključavanja.

**Ne tvrdim da je preračun linearizovan ni atomski. Nije.**

Svojstva su zabeležena kao strogi xfail u `tests/test_ns4r_granice_dokaz.py`. Ako svojstvo jednog dana postane tačno, test postaje XPASS i pada. `--runxfail` potvrđuje da padaju iz opisanog razloga, a ne zbog greške u test okruženju.

| # | Dokaz | Posledica | Zašto ne sada |
|---|---|---|---|
| **G1** | Preračun koji je pročitao `outcome_log` PRE tuđeg upisa, a piše POSLE tuđeg preračuna, prepisuje tačan zbir `{"svedoci": (1,1,2)}` zastarelim `(1,0,1)` | Do sledećeg upisa ishoda iste (korisnik, vrsta spora) `case_patterns` je netačan. Te brojeve čitaju `court_predictor` (kalibracija), `case_intelligence`, `benchmarking` i `cio`. Samoisceljujuće je, ali bez roka | Linearizacija traži zaključavanje ili atomsku operaciju u bazi |
| **G2** | Postojeći faktori se čitaju bez straničenja (`learning.py:142`). Iznad PostgREST `max-rows` (prod. podrazumevano 1000; u testu model cap=5) deo redova se ne vidi. INSERT tada pada na `UNIQUE(user_id, tip_spora, faktor)` (037), a preračun se prekida usred petlje (non-fatal). Faktori posle tog mesta ostaju zastareli (`f05–f07: (9,9,18)`) | Netačni brojevi za deo faktora. **Duplikata nema** (UNIQUE u šemi). Realno tek kad jedan korisnik u jednoj vrsti spora ima >1000 različitih faktora. `presudni_faktori` se ne validira prema `_FAKTORI_LABELS`, pa je skup otvoren | Straničenje bi rešilo samo G2, ne i G1. Zato je predlog jedan i zajednički |

**Najmanji predlog za posebnu odluku osnivača** (migracija; NIJE implementirano):
- SQL funkcija `preracunaj_case_patterns(p_user uuid, p_tip text)`, `SECURITY DEFINER`, izvršava je samo `service_role`;
- u jednoj transakciji: `pg_advisory_xact_lock(hashtext(p_user::text || ':' || p_tip))`, zatim `INSERT … SELECT` agregata iz `outcome_log` sa `ON CONFLICT (user_id, tip_spora, faktor) DO UPDATE`, i nuliranje faktora kojih više nema;
- backend zove `supa.rpc(...)` umesto petlje.

Time se uklanjaju i G1 i G2. Do odluke važi sadašnje ponašanje: non-fatal i samoisceljujuće pri sledećem upisu.

---

## 6. Izmenjeni postojeći testovi (i zašto to nije „popravka da bi prošlo“)

| Fajl | Izmena | Opravdanje | Kontrola |
|---|---|---|---|
| `tests/test_ns4_t3_slicni_predmeti_iskreno.py` | Id-evi međusobno različiti i u prvih 8 znakova; lažni model vraća pun `predmet_id`; dodata provera 4 različita predmeta | Stari test je prolazio sa lažnim uzorkom (tačno nalaz pregleda); novi ugovor prompta je pun id | Pada na 2388df33 (stari kod ne čita `predmet_id`) — očekivano |
| `tests/test_ns4_t6_vazece_overe.py` | `s-ok` dobija `pinecone_indexed: True`; dodat slučaj `s-nepotpun` (✗) | Overen vektor postoji samo posle promocije, a ona uvek upisuje `pinecone_indexed` | `s-nepotpun` pada na 2388df33 (RED) |
| `tests/test_ns008_t10_office_knowledge.py` | Tri odobrena reda (`s-ok`, `s-ok2`, `s-B`) dobijaju `pinecone_indexed: True`. Odbijen red je nepromenjen | Fake baza podrazumeva `pinecone_indexed=False` (DEFAULT iz 088), pa je fixture opisivao vektore u indeksu čiji red tvrdi „nije indeksirano“. To stanje je nemoguće za uspešnu promociju | **Prolazi i na 2388df33** (6/6). Izmena sama po sebi ne menja ishod, dakle ništa ne maskira |

Asertacije nijednog postojećeg testa nisu oslabljene.

---

## 7. Dokazi

**RED na 2388df33** (radna kopija pre izmena, `red_na_2388df33.log`): novi testovi daju 12 failed i 11 passed. Prošli su pozitivne i kontrolne provere, plus tabelarni slučajevi koje je i staro pravilo ispravno odbijalo.

**Kontrola na izdvojenoj kopiji starog koda** (`git archive 2388df33`, novi i izmenjeni testovi; `kontrola_stari_kod.log`): 15 failed, 28 passed.
- 12 iz novog fajla;
- 2 iz T3 (novi ugovor punog id-a);
- 1 iz T6 (`s-nepotpun`);
- T10: 6/6 passed.

**GREEN na grani.**
- novi testovi: 23/23 passed;
- dokaz granica: 2 xfailed (strogi).

**Mutacije** (izdvojena kopija, binarno vraćanje i `cmp` posle svake; `mutacije.log`):

| Mutacija | Fajl | Rezultat |
|---|---|---|
| M1 bez provere vrste spora | learning.py | 1 failed — uhvaćena |
| M2 pravilo bez `pinecone_indexed` | law_brain.py | 5 failed — uhvaćena |
| M3 prefiks bez provere jedinstvenosti | learning.py | 1 failed — uhvaćena (posle pooštravanja testa) |
| M4 bez deduplikacije | learning.py | 1 failed — uhvaćena |
| M5 greška `predmeti` = prazno | learning.py | 1 failed — uhvaćena |
| M6 greška `outcome_log` = prazno | learning.py | 1 failed — uhvaćena |
| M7 stara poruka o nepretraživosti | drafting.py | 1 failed — uhvaćena |
| M8 model dobija 8 znakova | learning.py | 1 failed — uhvaćena (posle pooštravanja testa) |

**Ciljni regresioni skup** (`ciljni_grana.log`): 40 fajlova iz `ns4_targets.txt` (NS008, RH001, poverljivost, kancelarija, staging trka…), svi `test_ns4_*`, novi fajl, `test_bu004_injection_chunk_quarantine` i `test_z017_registar_offset`, sa fiksnim redosledom (`-p no:randomly`).
- Prvi prolaz: 3 failed, sva tri u T10 (fixture, §6).
- Posle ispravke fixture-a: **648 passed, 1 xfailed** (strogi xfail `client_memory` iz NS4).

**Pun skup testova:** §8.

**Statičke provere.** `py_compile` (3 modula i 5 test fajlova) i uvoz modula prolaze. `node --check frontend-v2-ng/src/nacrt-predmeta.js` i `git diff --check` su čisti.

---

## 8. Pun skup testova i poređenje sa osnovom

Ista komanda kao u NS4: `python -m pytest -q -p no:randomly tests/test_*.py`.

| Run | Rezultat |
|---|---|
| Osnova `cc8bd548` (NS4, `ns4_full_base.log`) | 16 failed, 11227 passed, 227 skipped, 2 xfailed |
| NS4 `2388df33` (`ns4_full_branch2.log`) | 16 failed, 11281 passed, 227 skipped, 3 xfailed |
| **Ova grana** (`full_grana_ns4r.log`) | **16 failed, 11305 passed, 227 skipped, 5 xfailed** (23:26) |

- Spisak 16 ID-eva padova je **identičan** osnovi (`ids_ns4r.txt` = `ids_base.txt`, `diff` prazan): **0 novih padova**.
- +24 passed u odnosu na 2388df33: 23 nova testa i 1 novi tabelarni slučaj u T6.
- +2 xfailed: strogi xfail G1 i G2 (§5).

---

## 9. Promenjeni fajlovi (u odnosu na 2388df33)

| Status | Fajl | Šta |
|---|---|---|
| M | `routers/learning.py` | R1 (vrsta spora), R3 (pun identitet, deduplikacija), R4 (503 umesto „prazno“) |
| M | `services/law_brain.py` | R2: `vazece_overe` traži `pinecone_indexed is True` |
| M | `routers/drafting.py` | R2: poruka bez tvrdnje „nije pretraživ“ |
| M | `frontend-v2-ng/src/nacrt-predmeta.js` | R2: ista poruka u V2 |
| M | `tests/test_ns4_t3_slicni_predmeti_iskreno.py` | različiti identiteti (§6) |
| M | `tests/test_ns4_t6_vazece_overe.py` | `pinecone_indexed` + slučaj `s-nepotpun` (§6) |
| M | `tests/test_ns008_t10_office_knowledge.py` | realan fixture odobrenih redova (§6) |
| A | `tests/test_ns4r_nezavisni_pregled.py` | 23 testa R1–R4 |
| A | `tests/test_ns4r_granice_dokaz.py` | 2 stroga xfail G1/G2 |
| A | `docs/release/NS4_INDEPENDENT_REVIEW_REMEDIATION_REPORT.md` | ovaj izveštaj |

Tačan spisak sa punim SHA je u `changed_files.txt` paketa (`git diff --name-status 2388df33 HEAD`).

---

## 10. Preostali blokeri i ograničenja (bez skrivanja)

Četiri nalaza pregleda (R1–R4) su lokalno zatvorena, a zadatak 5 je dokumentovan. Klasifikacija je ipak **PARTIAL PASS — BLOCKERS REMAIN**, jer i dalje važi sledeće:

1. **O3 (iz NS4) — oporavak neuspele promocije ne postoji.** Posle R2 nepotpun nacrt se više ne servira kao overen izvor, ali ostaje trajno neiskorišćen dok se ručno ne ponovi upis. Rešenje traži `promotion_state` i migraciju.
2. **O2 (iz NS4) — `client_memory` bez vlasnika.** Kolega iz kancelarije vidi profil tuđeg klijenta (strogi xfail). Ovde namerno nije dirano.
3. **O1 (iz NS4) — RLS politike sa `aktivan`.** Zatvorene su i danas bez efekta; naivna zamena bi proširila pristup. Ovde namerno nije dirano.
4. **G1 i G2 (§5).** Preračun `case_patterns` nije atomski. Rešenje je SQL funkcija, tj. migracija koja čeka odluku.
5. **Stari produkcioni redovi (§2).** Nepotpuni upisi iz perioda pre provere potpunosti ingest-a mogu imati `pinecone_indexed=True`. Nije provereno, jer traži read-only upit nad produkcijom.
6. **Ugovor sa modelom (R3).** Pravi model sada mora da vrati pun `predmet_id`. Ako vrati samo prefiks, stavka važi samo kad je prefiks jedinstven, a inače se odbacuje (fail-closed: manje stavki, nikad lažnih). Ponašanje pravog modela nije mereno; mreža je u testovima blokirana.
7. **Granica dokaza.** Sve je lokalno: baza u memoriji, lažni Pinecone i lažni model. Ništa nije izvršeno nad produkcijom, a produkcijske tabele učenja su prazne.
8. **Poznati pad zavisan od redosleda** (`test_ns008_t21_revocation::test_deaktivirana_beleska_nestaje` posle staging testova) postoji i na čistoj osnovi i nije iz ovog rada.

Ništa od ovoga ne čini platformu „production-ready“, niti je ovo beta GO.
