# INGEST SECOND EYE — protivnička recenzija BETA-DATA-CONFIDENTIALITY-004

**Uloga:** nezavisni recenzent (second-eye). Zadatak nije potvrda, nego pokušaj obaranja.
**Baseline:** `942678f2`. Predmet recenzije: necommit-ovane izmene u `api.py`, `routers/smart_intake.py`, `uploaded_doc/ingest.py` + nov `tests/test_confidentiality_004_ingest.py`.
**Ograničenja poštovana:** nijedan produkcijski fajl ni test nije izmenjen; nema upisa u Pinecone ni Supabase; nema ispisa kredencijala. Mutacije su izvedene isključivo preko pytest plugin-a u scratchpad-u (`-p mut_writer` / `-p mut_gate`), bez diranja repo fajlova.

---

## VERDIKT

> „Vindex sada pouzdano razlikuje 'fajl je primljen' od 'fajl je stvarno ingestovan i spreman za AI pretragu'."

**OBORENO.** Tvrdnja ne stoji na tri nezavisna osnova, od kojih svaki sam za sebe dovoljan:

1. **Popravljene su 2 od 4 produkcijske putanje.** `routers/drafting.py` i `routers/dokument.py` i dalje ne proveravaju povratnu vrednost; `drafting.py` bezuslovno upisuje `status='indeksirano'`, a `dokument.py` i dalje nosi tačno onaj preširoki klasifikator `"storage" in ...` koji je ovaj sprint proglasio bugom.
2. **Razlika se nigde ne prikazuje korisniku, a UI je aktivno protivreči.** `static/vindex.js` nikad ne čita `dok.status`; indikator „vektorizovan" izvodi iz `pinecone_namespace`, koje se upisuje **bezuslovno** i kad indeksiranje nije uspelo.
3. **Nova kapija na pozivnom mestu (`ingest_je_potpun`) je strukturno mrtav kod** — nijedan produkcijski ulaz ne može da je obori.

Popravka **jeste** stvarna i **jeste** poboljšanje na jednom mestu: FS-002 kapija u `uploaded_doc/ingest.py:87-91` zatvara stvarnu rupu tihog `zip()` skraćivanja i to je dokazano mutacijom. Ali to je jedini deo koji stvarno radi.

---

## RANG-LISTA NALAZA

| # | Ozbiljnost | Nalaz | Dokaz |
|---|---|---|---|
| SE-01 | **HIGH** | 2 od 4 pozivaoca `ingest_session` ne proveravaju povratnu vrednost | `routers/drafting.py:356`, `routers/dokument.py:300` |
| SE-02 | **HIGH** | `drafting.py` bezuslovno upisuje `status='indeksirano'` | `routers/drafting.py:386` |
| SE-03 | **HIGH** | Popravka je nevidljiva korisniku; UI prikazuje neindeksiran dokument kao indeksiran | `static/vindex.js:12393-12416` vs `api.py:5278` |
| SE-04 | **HIGH** | `ingest_je_potpun` na pozivnom mestu je nedostižan kao detektor (mrtva grana) | `uploaded_doc/chunker.py:179` + `ingest.py:87-137` |
| SE-05 | **MEDIUM** | `dokument.py` i dalje nosi stari preširoki klasifikator `"storage" in ...` | `routers/dokument.py:313` |
| SE-06 | **MEDIUM** | Lažan uspeh korisniku na `/api/dokument/upload`: HTTP 200 + „0 odeljaka", sesija aktivna | `routers/dokument.py:316` → `static/vindex.js:9025,8983` |
| SE-07 | **MEDIUM** | Paralelni ingest writer-i imaju identičan `zip()` bug, nepopravljen | `drafting/playbook.py:73`, `interni_stavovi.py:66` |
| SE-08 | **MEDIUM** | `knowledge_base.py` guta svaki izuzetak ingesta, korisnik dobija uspeh | `routers/knowledge_base.py:102-123` |
| SE-09 | **MEDIUM** | `je_kvota_greska` ima novu klasu lažno-pozitivnih (`"429"` bilo gde, OpenAI rate-limit) | `uploaded_doc/ingest.py:181` |
| SE-10 | **LOW** | Nijedan test ne pokriva pozivna mesta — samo `uploaded_doc.ingest` sloj | `grep ingest_je_potpun tests/` |
| SE-11 | **LOW** | `smart_intake` nema `total_chunks==0` gard → prazan segment sad pada na `sacuvano` | `routers/smart_intake.py:1401` (nema gard, up. `api.py:5193`) |
| SE-12 | **LOW** | Tvrdnja izveštaja 003 o „43 dokumenta zbog Pinecone kvote" nije dokazana | `git show ff584d23:api.py:3863` |

---

## ODGOVORI NA PITANJA MANDATA §8

### 5. Može li korisnik dobiti lažni uspeh na TREĆOJ putanji? — **NAJVAŽNIJE. DA.**

Svi produkcijski pozivaoci `ingest_session` u repou (test fajlovi izuzeti):

| # | Pozivalac | Proverava povratnu vrednost? | Ishod |
|---|---|---|---|
| 1 | `api.py:5204` (`POST /api/predmeti/{id}/upload`) | **DA** — `ingest_je_potpun(count, manifest.total_chunks)` na `:5227` | popravljeno (ali v. SE-04: grana nedostižna) |
| 2 | `routers/smart_intake.py:1401` (`_finalize_intake_job_core`) | **DA** — `:1420` | popravljeno (ali v. SE-04) |
| 3 | `routers/drafting.py:357` (`_promote_staged_draft_to_pinecone`) | **NE — povratna vrednost se uopšte ne dodeljuje** | **RUPA** |
| 4 | `routers/dokument.py:301` (`POST /api/dokument/upload`) | **NE — `count` se dodeljuje, ali se nikad ne poredi sa `manifest.total_chunks`** | **RUPA** |

**Pozivalac 3 — `routers/drafting.py`:**

```python
355:    try:
356:        await asyncio.to_thread(          # ← nema dodele; povratna vrednost se baca
357:            ingest_session, manifest, session_id,
...
370:    except Exception as pe:
371:        logger.warning("[STAGING_PROMOTE] Pinecone ingest neuspešan predmet=%s: %s", ...)
372:        return False
```

a zatim, bezuslovno:

```python
386:        "pinecone_namespace": owner_ns, "status": "indeksirano",
```

Ovo je **doslovno isti obrazac koji sprint tvrdi da je iskorenio**: uspeh se izvodi iz odsustva izuzetka, a `status='indeksirano'` je hard-kodovan literal, ne izvedena vrednost. Pozivalac 3 dodatno piše u `predmet_dokumenti` (`:402`) — istu tabelu, isti vokabular statusa — pa je nekonzistentnost unutar jedne tabele.

Ublažavajuće za pozivaoca 3: `promoted` (True/False) **jeste** izložen korisniku kao `indexed` u odgovoru (`routers/drafting.py:1295-1298`) i upisan u `staging_memory.pinecone_indexed`. To je jedina putanja u celom sistemu koja korisniku prijavljuje ishod indeksiranja. Ali `predmet_dokumenti.status` red koji ista funkcija upisuje je i dalje lažan.

**Pozivalac 4 — `routers/dokument.py`:**

```python
300:            count = await asyncio.to_thread(
301:                ingest_session, manifest, session_id, ttl_hours, ...
310:            )
311:        except Exception as e:
312:            _es = str(e)
313:            if "429" in _es or "storage" in _es.lower() or "Too Many" in _es:
314:                # Pinecone pun — nastavi bez RAG, tekst je ekstraktovan
315:                logger.warning("[UPLOAD] Pinecone storage pun, nastavljam bez indeksiranja: %s", _es[:120])
316:                count = 0
```

Dva odvojena problema:
- `count` se nikad ne poredi sa `manifest.total_chunks` (FS-001 nepopravljen ovde);
- linija `:313` je **doslovno stari klasifikator** koji je ovaj sprint proglasio bugom i zamenio u `api.py:5241` sa `je_kvota_greska`. Ista greška, ista datoteka-klasa, nedirnuta. (SE-05)

**Zaključak:** popravka je nepotpuna. To je nalaz, tačno kako je mandat predvideo.

---

### 1. Može li storage reći „uspeh" dok Pinecone nije uspeo? — **DA, i korisnik to ne može videti.**

**A) Baza je poštena. UI nije, i aktivno je protivreči.**

Popravka menja isključivo kolonu `predmet_dokumenti.status`. Repo-wide grep pokazuje da `static/vindex.js` **nijednom ne čita `dok.status`**. Jedini pogoci na `sacuvano` u `vindex.js` (`:11896`, `:22613`, `:22717`, `:22738`) su polje `d.sacuvano_u_predmet` iz `routers/rokovi_lanac.py` / `routers/ugovor_zastupanja.py` — potpuno nepovezano.

Lista dokumenata u predmetu izvodi indikator „vektorizovan" iz **`pinecone_namespace`**, ne iz `status`:

```javascript
12393:            var _ns = dok.pinecone_namespace || '';
12395:            var _hasNs = !!_ns;
...
12406:              + '<div class="vx-tl-dot' + (_hasNs ? ' is-done' : '') + '"></div>'
12411:              + '<i data-lucide="file-text" ... color:' + (_hasNs ? '#00d4ff' : 'rgba(255,255,255,0.35)') + ';"></i>'
12414:              + '<div class="vx-tl-title" style="' + (_hasNs ? '' : 'color:rgba(255,255,255,0.45);') + ...
12416:              + (_hasNs ? ' • klikni za analizu' : ' • <span ...>nije vektorizovan — re-upload</span>')
```

A obe „popravljene" putanje upisuju `pinecone_namespace` **bezuslovno**, nezavisno od `_pinecone_ok`:

```python
api.py:5278                    "pinecone_namespace":  _owner_ns,
api.py:5279                    "status":              "indeksirano" if _pinecone_ok else "sacuvano",
```
```python
routers/smart_intake.py:1435                "pinecone_namespace": _owner_ns,
routers/smart_intake.py:1436                "status":             "indeksirano" if pinecone_ok else "sacuvano",
```

**Posledica:** dokument sa `status='sacuvano'` (NIJE indeksiran) dobija ne-prazan `pinecone_namespace` → `_hasNs === true` → UI ga renderuje sa `is-done` tačkom, cyan ikonicom, punom svetlinom naslova i tekstom **„• klikni za analizu"** — piksel-identično potpuno indeksiranom dokumentu. UI ne samo da ne prikazuje razliku; on **tvrdi suprotno od baze**.

Ironija: `vindex.js:12399-12401` sadrži komentar iz Iron Lawyer Sprint 001 koji upozorava da je klasifikacioni status „bio nevidljiv ovde" i to popravlja za `tip_dokaza`. Isti propust je ponovljen za `status`.

**B) HTTP odgovor takođe ćuti.**

`api.py:5783-5805` vraća `session_id`, `filename`, `chunk_count`, `doc_type`, `procena`, `auto_analyzed`, `hronologija_count`, `metadata`, `predlozi_povezivanja`, `mozda_duplikat`, `original_preserved`. **Nijedno polje ne izveštava o indeksiranju.** `chunk_count` je `count`, koji na kvota-grani iznosi 0 — ali klijent ga ne interpretira kao neuspeh nigde.

Ovo je posebno teško opravdati jer je presedan u istoj `return` naredbi: `original_preserved` (`:5804`) je dodat u Final Beta Gate F7 **za tačno ovu klasu problema** — „advokat čiji original nije sačuvan video je identičan ekran uspeha kao onaj čiji jeste". Sprint 004 je reprodukovao tu grešku za indeksiranje umesto da primeni već postojeći obrazac.

**Ocena:** popravka je tačna u bazi, nevidljiva korisniku, i protivrečena od UI-ja. Za korisnika, „primljen" i „indeksiran" i dalje izgledaju identično.

---

### 2. Može li izuzetak i dalje biti progutan? — **DA, na tri mesta.**

| Mesto | Ponašanje | Ishod |
|---|---|---|
| `routers/knowledge_base.py:121-123` | `except Exception as e: _sentry_capture(e); logger.warning(...)` — **bez re-raise, funkcija vraća `None`** | beleška se snima u bazu, korisnik dobija uspeh, vektor nikad ne postoji. Nema statusa, nema signala. **Potpuno tiho.** (SE-08) |
| `routers/dokument.py:313-316` | kvota-grana guta i postavlja `count = 0` | HTTP 200 (v. Q6 niže) |
| `routers/drafting.py:370-372` | guta i vraća `False` | djelimično ublaženo: `False` stiže do korisnika kao `indexed: false` (`:1297`), ali `predmet_dokumenti` red se u tom slučaju uopšte ne kreira, pa nema ni lažnog reda |

Na **popravljenim** putanjama gutanje je kontrolisano i pošteno u bazi:
- `api.py:5233-5246` — kvota → `_pinecone_ok=False`; sve ostalo → `HTTPException(500)`, pa spoljni `except` na `:5320` čisti original iz storage-a i re-raise-uje. Ispravno.
- `smart_intake.py:1426-1428` — guta sve, ali postavlja `pinecone_ok=False`, pa red nosi `'sacuvano'`. Pošteno u bazi (nevidljivo u UI-ju, v. Q1).
- `api.py:5301-5302` — insert u `predmet_dokumenti` guta, ali `:5315-5319` diže 500 ako `_dok_id` nedostaje. Ispravno.

---

### 3. Može li ponovljeni ingest napraviti duplikate? — **DA. Kapija to čini neutralno-do-blago-bolje, ali otvara sekundarni put ka duplikatima.**

`uploaded_doc/chunker.py:157` — `chunk_id=str(uuid.uuid4())` pri svakom chunk-ovanju. Ponovni upload istog fajla daje potpuno nove ID-eve → Pinecone `upsert` ne prepisuje, nego dodaje. Test `test_i_ponovni_upload_ISTOG_fajla_pravi_duplikate_ID_01` (`:220-237`) ovo pošteno zaključava kao poznato stanje — dobra praksa.

**Nabolje:** FS-002 kapija stoji **pre** prvog `upsert`-a (`ingest.py:87`, pre `records` petlje na `:93`). Na neslaganje broja vektora sada se ne upisuje **nijedan** vektor umesto ranijih ~N djelimičnih orphan-a. Test `test_f_nijedan_vektor_nije_upisan_kad_se_neslaganje_otkrije` (`:142-148`) to i meri. **Strogo poboljšanje.**

**Nepromenjeno:** pad batch-a u sredini i dalje ostavlja prethodne batch-eve u Pinecone-u (`ingest.py:125-131` loguje pa re-raise-uje). Ranije je `index.upsert` izuzetak takođe propagirao izvan petlje (nije bilo try/except), pa je jedina promena log. Isti orphan, sada prebrojiv.

**Nagore (sekundarno):** na `api.py` putanji, raise iz batch-pada nije kvota → `HTTPException(500)` na `:5246` → spoljni `except` na `:5320` briše original iz storage-a → `predmet_dokumenti` red se **nikad ne kreira**. Rezultat: orphan vektori u Pinecone-u **bez ijednog DB reda koji na njih pokazuje**, tj. bez ikakvog načina da se pronađu i obrišu (`cleanup.py` briše samo `tmp_*`). Korisnik dobija poruku „pokušajte ponovo", ponovi upload, `uuid4` daje novi set ID-eva → duplikati se akumuliraju pri svakom pokušaju. Kapija ne uzrokuje ovo, ali politika „odbij i traži ponovni upload" bez dedup-a ga sistematizuje.

---

### 4. Može li djelimičan ingest i dalje izgledati kompletno? — **DA, na 4 putanje.**

1. `routers/drafting.py:386` — `status='indeksirano'` hard-kodovan (SE-02).
2. `routers/dokument.py` — `count` neproveren; kvota → HTTP 200 (SE-05, SE-06).
3. `drafting/playbook.py:73` i `interni_stavovi.py:66` — nezavisni writer-i sa identičnim `zip()` bugom (SE-07, v. Q10).
4. `routers/knowledge_base.py:105` — nezavisni writer, izuzetak progutan (SE-08).

Dodatno, na svim putanjama: čak i kad je baza poštena, **UI to ne prikazuje** (Q1), pa „izgleda kompletno" korisniku bez obzira na vrednost u koloni.

---

### 6. Može li pozadinski radnik zaobići proveru? — **NE. Nijedan pozadinski radnik ne ingestuje.**

Provereno: `shared/intake_worker.py`, `shared/intake_queue.py`, `services/agent_tasks/*` (`court_portal_watcher.py`, `precedents_radar.py`), `routers/intake.py`.

- Nijedan ne uvozi `uploaded_doc.ingest`, ni direktno ni tranzitivno. Zavisnost ide obrnuto: `routers/smart_intake.py:1266` uvozi worker singleton i koristi samo `_download_and_decrypt`.
- `intake_worker` / `intake_queue` **ne pišu u `predmet_dokumenti` uopšte** — samo `intake_documents`, `intake_job_segments`, `intake_review_queue`, `processing_outcomes`, `intake_jobs`.
- Sva 4 poziva `ingest_session` su unutar sinhronih HTTP handler-a.

**Jedini pisač `predmet_dokumenti` bez ikakve verifikacije je `routers/intake.py:314`** (`"status": "sacuvano"`, literal, bezuslovan) — ali to je HTTP handler wizard-a koji samo povezuje već otpremljen dokument i ne pokušava ingest. Vrednost je poštena, i taj red **nema `pinecone_namespace`**, pa ga UI ispravno prikazuje kao „nije vektorizovan — re-upload". Ova putanja je jedina koja se u UI-ju ponaša tačno.

---

### 7. Može li nova kapija oboriti nešto što je ranije radilo? — **Nije nađen legitiman slučaj. Kapija je bezbedna, ali menja režim otkaza.**

Traženo je stanje u kome `embed_documents` legitimno vraća manje vektora nego chunk-ova.

- Jedini pozivalac je `langchain_openai.OpenAIEmbeddings.embed_documents` (`ingest.py:29-36`). Njegov ugovor je 1:1 po ulaznom tekstu; interni `check_embedding_ctx_length` mehanizam predugačke tekstove deli i **usrednjava nazad**, pa i dalje vraća `len(texts)`. Prazan string OpenAI odbija **izuzetkom**, ne izostavljanjem.
- `manifest.total_chunks == len(manifest.chunks)` je invarijanta: `chunker.py:179` (`total_chunks=len(chunks)`), i grep potvrđuje da nijedno mesto ne mutira `manifest.chunks` niti `total_chunks` između `chunk_document` i `ingest_session`.

**Zaključak: nema poznatog legitimnog slučaja. Kapija ne obara ništa.**

**Ali menja režim otkaza:** ako se takav slučaj ikad pojavi (promena verzije langchain-a, drugi provajder, buduće batch-ovanje embedding-a), posledica više nije tihi djelimičan uspeh nego **potpun otkaz upload-a**: raise → nije kvota → `HTTPException(500)` (`api.py:5246`) → brisanje originala iz storage-a (`:5320-5335`) → korisnik gubi ceo upload. Trade-off je namerno izabran i ispravan po mandatu, ali ga treba znati.

---

### 8. Da li `ingest_je_potpun(0, 0) == False` obara neki legitiman tok? — **Delimično: jedna putanja menja ponašanje.**

| Putanja | Gard na prazan manifest | Efekat `(0,0) == False` |
|---|---|---|
| `api.py:5193` | `if manifest.total_chunks == 0: raise HTTPException(422)` | nedostižno |
| `routers/dokument.py:287` | `if manifest.total_chunks == 0: raise HTTPException(422, "Empty document")` | ne poziva `ingest_je_potpun` uopšte |
| `routers/drafting.py:349-350` | `if manifest.total_chunks == 0: return False` | ne poziva `ingest_je_potpun` uopšte |
| `routers/smart_intake.py:1401` | **NEMA GARD** | **dostižno** |

`smart_intake` nema `total_chunks == 0` proveru. Prazan ili samo-beli-znaci segment sada daje `ingest_session → 0`, `ingest_je_potpun(0, 0) → False`, `pinecone_ok = False`, `status = 'sacuvano'` (`:1436`) — gde je pre popravke bio `'indeksirano'`.

**Ocena:** promena je *poštenija* (prazan dokument stvarno nije indeksiran), pa nije lažan uspeh. Ali je nenajavljena promena ponašanja jedine putanje bez garda, i u `logger.error` (`:1421`) upisuje „nepotpun ingest" za dokument koji nije nepotpun nego prazan — bučan lažno-pozitivan alarm. (SE-11)

---

### 9. Da li testovi voze produkcijske funkcije? — **DA na nivou `uploaded_doc.ingest` — dokazano mutacijom. NE na nivou pozivnih mesta.**

Osnovni rezultat: `25 passed in 0.54s`.

**Mutacija A — produkcijski writer uklonjen** (`ingest_session` bez ijednog `index.upsert`, vraća `len(chunks)` kao da je upisao):

```
FAILED test_lazni_indeks_stvarno_belezi_upis
FAILED test_a_pun_uspeh_vraca_tacan_broj_i_stvarno_upisuje
FAILED test_f_pad_batcha_u_sredini_dize_gresku_a_ne_delimican_uspeh
3 failed, 22 passed
```

**Mutacija B — FS-002 kapija uklonjena** (vraćeno staro tiho `zip()` skraćivanje):

```
FAILED test_f_nijedan_vektor_nije_upisan_kad_se_neslaganje_otkrije
FAILED test_f_embedding_vratio_manje_vektora_dize_gresku
2 failed, 23 passed
```

**Zaključak:** testovi NE rekonstruišu granu. `_LazniIndeks` stvarno beleži upis, kontrolni test `test_lazni_indeks_stvarno_belezi_upis` (`:244-251`) ispravno štiti od mock-a koji ništa ne meri, i **testovi bi pali kad se produkcijski writer ukloni**. Ovo je kvalitetan, mutacijom-verifikovan test sloj.

**Ali — nedostatak pokrivenosti (SE-10):**

Test fajl uvozi isključivo `uploaded_doc.ingest` i `uploaded_doc.schema` (`:51-56`). **Nikad ne uvozi `api.py`, `smart_intake.py`, `drafting.py` ni `dokument.py`.** `grep -rn "ingest_je_potpun\|je_kvota_greska" tests/` daje pogotke **samo u ovom fajlu**.

Posledica: FS-001 — tj. celo integraciono ponašanje popravke — je **netestirano**. Nijedan test ne tvrdi da `api.py` poziva `ingest_je_potpun`, nijedan ne proverava koja vrednost `status`-a završi u `predmet_dokumenti`, i **nijedan test ne bi pao zbog toga što `drafting.py` i `dokument.py` proveru uopšte nemaju**. Testovi `test_h_*` (`:195-205`) pozivaju `ingest_je_potpun` ručno sastavljenim brojevima koje produkcija ne može proizvesti (v. Q4/SE-04).

---

### 10. Postoji li legacy putanja koja zaobilazi novu logiku? — **DA, četiri produkcijske.**

Direktni `index.upsert` mimo `ingest_session`, u produkcijskom kodu (skripte u `scripts/` izuzete):

| Fajl:linija | Namespace | Problem |
|---|---|---|
| `drafting/playbook.py:73,86` | `playbook_{user_id}` | `zip(chunks, vectors_raw)` **bez ikakve kapije** — identičan FS-002 bug. Vraća `len(records)`. Pozivalac `routers/drafting.py:558` vraća korisniku `{"chunks_ingested": count}` — skraćen broj prijavljen kao uspeh. |
| `interni_stavovi.py:66,81` | `interni_stavovi_{user_id}` | isto. Pozivalac `routers/interni.py:37-39` vraća `{"vektori": count}`. |
| `routers/knowledge_base.py:105` | `kb_{uid}` | jedan vektor, ali **ceo blok u `try/except` koji guta** (`:121-123`). Beleška se snima, korisnik dobija uspeh, vektor može ne postojati. |
| `routers/law_upload.py:92`, `routers/batch_ingest.py:63`, `routers/auto_discovery.py:212` | `zakoni_rs` i sl. | korpus zakona, ne klijentski dokumenti — van opsega tvrdnje, ali van kapije. |

**`drafting/playbook.py` i `interni_stavovi.py` su najozbiljniji (SE-07):** to su korisničke „baze znanja" koje ulaze u RAG, sa doslovno istim `zip()` obrascem koji je FS-002 proglasio rupom, i sa istim „vrati `len(records)` kao dokaz uspeha" ugovorom. Sprint ih nije ni pomenuo.

---

## SE-04 — DETALJNO: kapija na pozivnom mestu je mrtav kod

Ovo je nalaz koji recenzija smatra najvažnijim posle SE-01/SE-03, jer podriva sam narativ popravke („uspeh se dokazuje, ne pretpostavlja").

Lanac invarijanti:

1. `uploaded_doc/chunker.py:179` — `total_chunks=len(chunks)`. **Uvek jednako.**
2. Grep potvrđuje: nijedno mesto ne mutira `manifest.chunks` niti `total_chunks` između `chunk_document` i `ingest_session`.
3. Nova FS-002 kapija (`ingest.py:87-91`) garantuje `len(vectors_raw) == len(manifest.chunks)`, inače raise.
4. `records` ima tačno jedan unos po `zip` paru → `len(records) == len(manifest.chunks)`.
5. Batch petlja (`ingest.py:121-132`) je **sve-ili-raise**: `_upisano` se uvećava tek posle uspešnog `upsert`-a, a svaki pad radi `raise`.

**Iz 1-5 sledi:** `ingest_session` na **svakoj** putanji koja ne diže izuzetak vraća tačno `manifest.total_chunks`.

**Dakle** `ingest_je_potpun(count, manifest.total_chunks)` je `True` uvek kad izuzetka nema, a kad izuzetka ima do provere se nikad ne stigne. Jedina dostižna `False` vrednost je `(0, 0)` — koju `api.py:5193` unapred eliminiše sa 422, a `smart_intake` dostiže samo za prazan segment (v. Q8).

**Praktična posledica:** grane `api.py:5227-5232` i `smart_intake.py:1420-1425` su, na današnjem kodu, **nedostižne kao detektori otkaza**. Sva stvarna zaštita dolazi iz FS-002 `raise`-a, koji je u `ingest.py`. Popravka radi — ali ne mehanizmom koji izveštaj sprinta navodi kao glavni.

To ih ne čini štetnim (legitimna su tripwire/defense-in-depth kapija protiv budućih regresija, i tako ih treba dokumentovati). Čini ih pogrešno predstavljenim: rečenica „nijedan pozivalac ga nikad nije proverio" implicira da provera sada hvata realne otkaze. Ne hvata nijedan.

---

## PROVERA TVRDNJE IZVEŠTAJA 003 — „43 dokumenta zbog Pinecone kvote"

**Tvrdnja** (`docs/security/BETA_DATA_CONFIDENTIALITY_003_FINAL.md:215-219`):

> „Svih 43 dokumenata ima `status='sacuvano'`. Verzija koda živa u periodu njihovog nastanka (`ff584d23:api.py:3857`) postavlja tu vrednost **isključivo** na Pinecone 429/quota grešku.
> **Pinecone ingest je pao za svih 43 klijentska dokumenta i nikad nije ponovljen.**"

**Istorijski kod, verifikovan direktno** (`git show ff584d23:api.py`, linije 3857-3870):

```python
3857:    _pinecone_ok = True
3858:    try:
3859:        count = await asyncio.to_thread(
3860:            ingest_session, manifest, session_id, namespace_prefix="pred_"
3861:        )
3862:    except Exception as _pe:
3863:        _pe_str = str(_pe)
3864:        if "429" in _pe_str or "storage" in _pe_str.lower() or "Too Many" in _pe_str:
3865:            logger.warning("[P1.1] Pinecone storage pun — dokument se cuva bez RAG indeksiranja: %s", ...)
3866:            _pinecone_ok = False
3867:            count = 0
3868:        else:
3869:            raise HTTPException(status_code=500, detail=...)
```

Uveden commit-om `6150795a` („fix(upload): graceful Pinecone 429", 2026-07-01).

**Nalaz: reč „isključivo" je netačna. Predikat je disjunkcija tri nezavisna tokena, od kojih nijedan ne dokazuje Pinecone kvotu.**

Alternativni uzroci koji proizvode identično stanje (`status='sacuvano'`, 0 vektora):

| Alternativa | Kako pogađa predikat | Zašto je verodostojna |
|---|---|---|
| **OpenAI rate limit na `embed_documents`** | `"429"` i `"Too Many"` | `_get_embeddings_client().embed_documents(texts)` (`ingest.py:75`) je **unutar istog `try`** i izvršava se **pre** ijednog `index.upsert`. Otkaz ovde ostavlja **tačno 0 vektora** — što se poklapa sa izmerenim „PRESEK: 0" bolje nego kvota na Pinecone strani, koja tipično pada tek na nekom batch-u i ostavlja djelimičan upis. |
| **Bilo koja greška sa rečju „storage"** | `"storage" in _pe_str.lower()` | Ovo nije spekulacija — **sam sprint 004 to navodi kao razlog izmene** (`ingest.py:165-168`, `api.py:5235-5239`): „presiroko: svaka greska cija poruka sadrzi 'storage'... tiho je postajala 'kvota'". |
| **Bilo koja greška sa nizom `429` bilo gde u poruci** | `"429" in _pe_str` | request-id, vector-id, veličina u bajtovima, host/port. Podniz, ne HTTP status. |

**Metodološka kontradikcija između dva izveštaja:** sprint 004 menja klasifikator **zato što je bio preširok da bi se iz njega izvodio uzrok**. Izveštaj 003 svoj centralni zaključak (`INGEST-01`, RED, `:300`) izvodi **iz tog istog preširokog klasifikatora**, tretirajući ga kao pouzdan indikator uzroka. Oba ne mogu biti tačna.

**Dodatna nekonzistentnost unutar 003:** izveštaj u istom bloku (`:206-209`) navodi `Pinecone pred_* namespaces: 6 (30 vektora)`. Ako je „ingest pao za svih 43", tih 6 `pred_*` namespace-ova sa 30 vektora moralo je nastati nekim putem koji izveštaj ne objašnjava — a `pred_` prefiks je koristila isključivo ova ista upload putanja (`namespace_prefix="pred_"`, `ff584d23:api.py:3860`). Postojanje uspešnih `pred_*` upisa protivreči tvrdnji o 43/43 otkazu istog koda.

**Ocena: UNKNOWN.**
- **Opservacija stoji:** 43 reda sa `status='sacuvano'` i 0 preseka sa Pinecone-om je izmereno stanje i ostaje ozbiljan nalaz.
- **Pripisani uzrok ne stoji kao dokazan:** „Pinecone storage kvota" je jedna od najmanje tri hipoteze konzistentne sa istim kodom i istim podacima; OpenAI 429 na embedding koraku objašnjava „tačno 0 vektora" bar jednako dobro.
- Razrešenje zahteva `SUPABASE_DB_URL` (nedostupno ovoj recenziji po mandatu i po `MEMORY.md`, gde stoji kao otvoreno od Black Swan-a) da bi se pročitali `created_at` timestamp-ovi tih 43 redova i uporedili sa istorijom `PINECONE_HOST` / veličinom indeksa. Do tada se uzrok ne sme navoditi kao utvrđen.

**Preporuka:** u izveštaju 003 zameniti „postavlja tu vrednost isključivo na Pinecone 429/quota grešku" sa „postavlja tu vrednost na bilo koji izuzetak čija poruka sadrži `429`, `Too Many` ili `storage`", i degradirati `INGEST-01` sa „Pinecone ingest je pao" na „ingest je pao iz neutvrđenog razloga".

---

## ŠTA JE OVA POPRAVKA STVARNO POSTIGLA

Radi poštenja prema autoru — nije sve loše:

1. **FS-002 kapija (`ingest.py:87-91`) je stvarna popravka stvarne rupe.** Tiho `zip()` skraćivanje je bilo dokaziv put ka djelimičnom ingestu prijavljenom kao potpun. Kapija stoji pre prvog upisa, pa ne ostavlja ni orphan-e. Mutacija B potvrđuje da je testovima pokrivena.
2. **`je_kvota_greska` je uže od `"storage" in ...`** i to je nedvosmisleno poboljšanje — na dve od četiri putanje.
3. **Test fajl je mutacijom-otporan** na sloju koji pokriva. To je iznad proseka za ovaj repo i vredi zadržati kao obrazac.
4. **Batch-log (`ingest.py:126-130`)** čini orphan vektore prvi put prebrojivim.

Problem nije kvalitet izvedenog rada, nego **opseg**: popravljena je biblioteka i dve od četiri putanje koje je zovu, a korisnički vidljiv sloj — jedini na kome se tvrdnja iz naslova može oboriti ili potvrditi — nije dodirnut.

---

## MINIMALNI SKUP ZA OBARANJE VERDIKTA

Da bi tvrdnja stajala, potrebno je (redom po povratu):

1. **SE-03** — `vindex.js:12393` da čita `dok.status`, ili `pinecone_namespace` da se upisuje samo kad `_pinecone_ok` (`api.py:5278`, `smart_intake.py:1435`). Bez ovoga ništa ostalo se korisniku ne vidi.
2. **SE-01/SE-02** — `drafting.py:386` da izvede `status` iz provere umesto literala; `dokument.py:300` da poredi `count` sa `manifest.total_chunks`.
3. **SE-05** — `dokument.py:313` da koristi `je_kvota_greska`.
4. **SE-10** — bar jedan test koji tvrdi da `predmet_dokumenti.status == 'sacuvano'` kad ingest padne, po putanji (4 testa).
5. **SE-07** — kapija dužine u `drafting/playbook.py:73` i `interni_stavovi.py:66`.

Stavke 1-3 su male i lokalizovane. Stavka 1 je jedina koja stvarno menja šta korisnik vidi.

---

*Recenzija izvedena bez izmene ijednog produkcijskog fajla ili testa. Mutacije: pytest plugin-ovi u scratchpad-u, `-p mut_writer` / `-p mut_gate`.*
