# PINE-01 — Matrica identiteta Pinecone vektora + read-only inventar produkcije

Baseline: `dcbf3fd9`
Datum merenja: 2026-08-13
Metod: nezavisan AST sweep (`ast.walk` nad svakim `.py` u repou, bez `.git/__pycache__/node_modules/.venv/site/data/vindex_scraper_output`), plus read-only Pinecone (`describe_index_stats`, `Index.list`, `fetch` po ID-u) i read-only Supabase `SELECT`.

**Nula upisa, nula brisanja, nula re-ingesta. Nijedan produkcijski fajl, test ni migracija nisu izmenjeni.**

Interni ID-evi su skraćeni. Sadržaj dokumenata i imena fajlova nisu ispisani.

---

## 0. Verifikacija broja pisača

AST sweep je tražio SVAKI `Call` čiji je `func.attr`/`func.id` jedan od
`upsert | upsert_records | upsert_from_dataframe | delete | delete_all`, nad celim repoom.
Rezultat: **55 `upsert*` poziva, 0 parse grešaka**.

Od 55:
- 34 su Supabase (`.table(...).upsert(...)`) — nisu Pinecone,
- 2 su u testu (`tests/test_id01_vector_identity.py:338,339`, lažni indeks),
- **19 su fizička Pinecone upsert mesta.**

Broj 19 iz ID-02 je time **nezavisno potvrđen**. Oba ranije promašena pisača su u listi:
`routers/law_upload.py:92` (#4) i `interni_stavovi.py:89` (#17, koji `routers/interni.py` zove
preko aliasa `ingest_stav as _ingest_stav` — alias je razlog zašto ga je grep promašio; AST
sweep ga hvata na mestu fizičkog upsert-a, gde alias ne igra ulogu).

Kontrolni tekstualni grep (`upsert` bez `.table(`) nije našao nijedno dodatno mesto,
niti dinamički poziv (`getattr`, string ime metode).

`uploaded_doc/ingest.py:186` je JEDINO fizičko upsert mesto za sva 4 poziva `ingest_session`
(`api.py:5214`, `routers/dokument.py:305`, `routers/drafting.py:368`,
`routers/smart_intake.py:1413`) — ta 4 su pozivaoci, ne pisci, i ne broje se posebno.

---

## 1. Matrica — svih 19 pisača

Legenda: `—` = ne postoji u kodu. `n/a` = nije primenljivo.

### RUNTIME (7)

| # | fajl:linija | namespace (odakle) | tenant binding | predmet_id | identitet dokumenta | identitet sadržaja | chunk index | chunk schema | konstrukcija vector ID-a | metadata ključevi | delete putanja |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `uploaded_doc/ingest.py:186` | `namespace_override` ili `f"{namespace_prefix}{session_id}"` (:69). Svi produkcijski pozivaoci šalju `kancelarija_{id}`/`user_{id}` (`shared/kancelarija_utils.py:57-58`) osim `routers/dokument.py:305` koji koristi `tmp_` default | **DA** — `kancelarija_id` u `extra_metadata` (api.py:5219, smart_intake:1418, drafting:373); `owner_user_id` (dokument.py:311); `vx_scope` uvek (`vector_identity.py:159`) | **DA** kad ga pozivalac pošalje (`extra_metadata["predmet_id"]`, :114, :169) | `vx_verzija` = SHA-256 izvučenog TEKSTA + verzija ekstrakcije (`verzija_dokumenta`, `vector_identity.py:242`); fail-closed ako nije prosleđena (:142-145) i ako nije kanonskog oblika (:147) | **DA** — isto polje `vx_verzija`; jedini pisač koji ima identitet sadržaja u ID-u | **DA** — `chunk_index` (:156) i u ID-u | **DA** — `vx_chunk_schema` (`CHUNK_SCHEMA_VERSION=1`) | `canonical_vector_id(_scope, _verzija, chunk.chunk_index)` (:172) → `{scope}__{32heks}__k{n}_c{i}` | `session_id, source_filename, source_format, chunk_index, chunk_mode, article_label, text, token_count, expires_at` + `extra_metadata` + `vx_scope, vx_verzija, vx_chunk_schema, chunk_index, predmet_id[, vx_document_id]` | **DA, ali nepovezana** — `shared/vector_deletion.obrisi_vektore_dokumenta` (:198). Vidi §4: nijedan endpoint je ne zove |
| 2 | `routers/auto_discovery.py:212` | `red["namespace"]` iz `discovery_queue`, fallback `f"zakon_{zemlja}"` (:242) | — | — | `izvor_url` u metapodacima (:245) | **DA (delimično)** — ID je `sha256(chunk)[:32]`, ali per-chunk, ne per-dokument (:199) | **DA** — `chunk_index` (:205) | — | `f"discovery_{chunk_hash}"`, `chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()[:32]` (:199-200) | `**metapodaci, text, chunk_index` | — |
| 3 | `routers/batch_ingest.py:63` | parametar `namespace`, iz `IngestRequest.namespace` default `"sudska_praksa"` (:181), validiran protiv `ALLOWED_NAMESPACES` (:196) | — (admin-only ruta, `_require_admin` :40) | — | `decision_id` (:98) | — | **DA** — `chunk_index` (:97) i u ID-u | — | `f"{ascii_id}_c{i}"`, `ascii_id = decision_id.translate(_SRLATMAP)` (:88, :93) | `text, chunk_index, decision_id` + prosleđeni `metadata` | — |
| 4 | `routers/knowledge_base.py:105` | `f"kb_{uid}"` (:115) | **DA** — `user_id` u metapodacima (:113) **i** u namespace-u | **DA** — `predmet_id` (:112), može biti `""` | `beleska_id` (:108) | — | — (jedan vektor po belešci, bez chunk-ovanja) | — | `f"kb_{uid}_{beleska_id}"` (:107) | `beleska_id, naslov, sadrzaj, tagovi, predmet_id, user_id` | **DA** — `index.delete(ids=[f"kb_{uid}_{entry_id}"], namespace=f"kb_{uid}")` (:385-388), po ID-u, tačno |
| 5 | `routers/law_upload.py:92` | literal `"zakoni_rs"` (:92) | — (admin-only) | — | `doc_id` (:144) | — | **DA** — `chunk_index` (:143) i u ID-u | — | `f"{safe_id}_c{ci}"`, `safe_id = re.sub(r"[^A-Za-z0-9_]", "_", doc_id.translate(_SRLATMAP))[:60]` (:109, :137) | `text, naziv_zakona, broj_sl_glasnika, chunk_index, doc_id, source` | **NE** — `DELETE /api/admin/law/{doc_id}` (:273) je **soft delete** samo u `law_docs`; docstring to i kaže: „NE briše iz Pinecone" |
| 6 | `interni_stavovi.py:89` | `f"interni_stavovi_{user_id}"` (:59) | **DA** — `user_id` u metapodacima (:78) i u namespace-u | — | `naslov` (:79) — nije jedinstven | — | **DA** — `chunk_index` (:80) | — | `f"is_{user_id[:8]}_{i}_{uuid.uuid4().hex[:8]}"` (:76) — **NEDETERMINISTIČKI** | `user_id, naslov, chunk_index, text, tip` | **samo `delete_all`** nad celim namespace-om korisnika (:133) — briše SVE stavove, ne jedan |
| 7 | `drafting/playbook.py:94` | `f"playbook_{user_id}"` (:64) | **DA** — `user_id` u metapodacima (:83) i u namespace-u | — | `filename` (:84) — nije jedinstven | — | **DA** — `chunk_index` (:85) | — | `f"pb_{user_id}_{i}_{uuid.uuid4().hex[:8]}"` (:81) — **NEDETERMINISTIČKI** | `user_id, filename, chunk_index, text` | **samo `delete_all`** nad celim namespace-om korisnika (:131) |

### BATCH / CLI (12)

| # | fajl:linija | namespace (odakle) | tenant | predmet_id | identitet dokumenta | identitet sadržaja | chunk index | chunk schema | konstrukcija vector ID-a | metadata ključevi | delete putanja |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | `ingest_glossary_vasp_casp.py:177` | `NAMESPACE = ""` (:19) — default | — | — | hardkodovano `zakon="ZDI"`, `parent_id="ZDI_56"`, `source="ZDI_2026_05_15_alias_glossary"` | — (nema `hashlib`) | samo kao literal `chunk_0` u ID-u | — | `CHUNK_ID = "ZDI::cl_56::alias_glossary::chunk_0"` (:18) — hardkodovana konstanta | `zakon, clan, stav, parent_id, parent_text, tekst_preview, doc_type, source, law, article, text` | **DA** — `index.delete(ids=[CHUNK_ID], namespace=NAMESPACE)` (:193), rollback po ID-u |
| 9 | `ingest_kz.py:129` | **nema `namespace=`** → Pinecone default `""` | — | — | `KZ_LAW_NAME="KZ"` (:37) → metadata `law` | — (MD5 hešira KOORDINATE, ne tekst) | `stav`/`clan` u metapodacima | — | `semantic_chunker.py:107-110`: `key = f"v2\|{zakon}\|{clan_num}\|{stav}"; return hashlib.md5(key.encode()).hexdigest()` | `zakon, clan, stav, parent_id, parent_text, tekst_preview, law, article, text` | **DA** — `index.delete(filter={"law": {"$eq": KZ_LAW_NAME}})` (:57), bez `namespace=` |
| 10 | `ingest_laws.py:297` | **nema `namespace=`** → default `""` | — | — | `law["name"]` iz `LAWS` tabele (:43-223) | — (isti MD5 koordinata) | `stav`/`clan` | — | isto `semantic_chunker.py:107-110` | isto kao #9 | **DA** — `index.delete(filter={"law": {"$eq": law_name}})` (:233), po law + `del_alts` (:241) |
| 11 | `ingest_misljenja.py:160` | `NAMESPACE = "misljenja"` (:45) | — | — | `broj`, `ministarstvo`, `url` u metapodacima (:112-121) — **ali ne u ID-u** | — | **DA** — `chunk_index` (:124, :139-140) | — | `vec_id = str(uuid.uuid4())` (:250) — **NEDETERMINISTIČKI** | `tip, ministarstvo, datum, broj, oblast, naziv, source, url, chunk_index, text` | **samo `delete_all`** nad celim `misljenja` (:221), iza `--force` |
| 12 | `ingest_short_15.py:154` | inline literal `''` (:154) | — | — | `law`, `zakon`, `article`, `parent_id`, `source="SHORT_BATCH_2026_05_17"` | — | `clan`/`stav` (`stav` hardkodovan 1) | — | lokalna kopija `_chunk_id` (:26-28), identičan MD5 koordinata | `zakon, clan, stav, parent_id, parent_text, tekst_preview, law, article, text, source` | **DA** — `idx.delete(ids=upserted_ids, namespace='')` (:181), rollback po ID-u |
| 13 | `scrape_zdi_mca.py:118` | `NAMESPACE = "web3_zdi_mca"` (:32) | — | — | `naslov`, `izvor`, `propis`; **URL scrape-a se NE upisuje** | — (MD5 hešira LABELU člana, ne tekst) | u ID-u kao `_chunk_{idx_c}`, **ne** u metapodacima | — | seed: `f"{item['id']}_chunk_{idx_c}"` (:165); ZDI: `f"zdi_{hashlib.md5(clan['clan'].encode()).hexdigest()[:8]}_chunk_{idx_c}"` (:188) | `tekst, naslov, izvor, tip, propis` | **—** nema `delete()` u fajlu |
| 14 | `diag_zpp_revizija.py:196` | inline literal `''` (:196) | — | — | `ZPP_LAW_NAME` (:20), `source="REVIZIJA_AUDIT_2026_05_17"` | — | `clan`/`stav` | — | treća kopija `_chunk_id` (:35-37), isti MD5 koordinata | `zakon, clan, stav, parent_id, parent_text, tekst_preview, law, article, text, source` | **—** nema `delete()`; na neslaganje broja samo štampa upozorenje (:213-214) |
| 15 | `scripts/ingest_bilten_to_pinecone.py:209` | `TARGET_NAMESPACE = "sudska_praksa"` (:44) | — | — | `decision_number`, `decision_id_fallback`, `court`, `source_url` (`chunker_case_law.py:287-293`) | — (nema `hashlib`) | **DA** — u ID-u `__chunk_{idx}` i u metapodacima `chunk_index`/`chunk_total` | **NE** — `chunker_version` postoji, ali samo na nivou odluke (`chunker_case_law.py:312`), nikad u chunk metapodacima | `_ascii_vector_id(c["chunk_id"])` (:203), gde `chunk_id = f"{decision_id}__chunk_{idx}"` (`chunker_case_law.py:279`); `_ascii_vector_id` lokalno :71-87 (latinica + ćirilica + razmak/kosa crta) | `doc_type, court, decision_number, decision_id_fallback, decision_date, matter, registrant, source_url, section, chunk_index, chunk_total, cited_articles_raw, cited_articles_normalized, text` | **—** nema `delete()`; ima read-only guard na default namespace (:115-127) |
| 16 | `scripts/ingest_carf_dac8.py:536` | `NAMESPACE = "carf_dac8"` (:44) | — | — | `izvor`, `propis`, `naslov` — sve hardkodovano | — (`hashlib` nije ni uvezen) | **NE** | — | `chunk["id"]` — ručno napisan literal po chunku, npr. `"carf_transakcije_kategorije_vodic"` (:449, upsert :518) | `naslov, izvor, propis, tip, tekst` | **—** nema `delete()` |
| 17 | `scripts/ingest_case_law.py:173` | parametar, ali `assert namespace == TARGET_NAMESPACE` (:169-172); `TARGET_NAMESPACE="sudska_praksa"` (:40) | — | — | isto kao #15 (`chunker_case_law`) | — | **DA** — `__chunk_{idx}` + `chunk_index`/`chunk_total` | **NE** | `_ascii_vector_id(c["chunk_id"])` (:327, :413, :584). **Ovde je `_ascii_vector_id` SLABIJI** (:77-79): samo `_SRLATMAP`, bez ćirilice i bez zamene razmaka/kose crte — piše u ISTI namespace kao #15 i #18 | isto kao #15 + `parent_text` (:102-110) | **DA — 2× `delete_all` nad CELIM `sudska_praksa`**: :347 (auto-rollback seed faze) i :542 (`--rollback` CLI). Briše i bilten (#15) i sudskapraksa.sud.rs (#18) vektore kao kolateralu |
| 18 | `scripts/ingest_sudskapraksa.py:342` | `TARGET_NAMESPACE = "sudska_praksa"` (:56) | — | — | `decision_number`, `court`, `source_url` ← `rec["url"]` (:133) | **postoji, ali ne stiže u Pinecone** — `hashlib.sha256(norm_text)` (:393-394) ide samo u lokalni `ingest_checkpoint.json` (:182), nije ni u ID-u (:334) ni u metapodacima (:417-423) | **DA** — `__chunk_{chunk_index}` + metadata | — | `_safe_id(chunk["chunk_id"])` (:334), gde je `chunk_id = f"sp_{odluka_id}__chunk_{chunk['chunk_index']}"` (:428) i `odluka_id = fp.stem` (:371). **Dvostruki `sp_` prefiks**: `chunker_case_law.py:279` je već proizveo `sp_...`, pa :428 to odbacuje i izvodi svoj. `_safe_id` (:81-91) je najstroži od tri sanitizera koji pišu u isti namespace | isto kao #15 + `tip_odluke, kljucne_reci, tip_suda, has_pdf` | **—** nema `delete()` |
| 19 | `scripts/ingest_web3_addendum.py:214` | `NAMESPACE = "web3_zdi_mca"` (:32) — **isti namespace kao #13** | — | — | `izvor`, `propis`, `naslov` — hardkodovano | — (`hashlib` uvezen :17, nikad korišćen) | **NE** — dva od pet ID-eva imaju kozmetički `_chunk_0` sufiks, tri nemaju; nema chunk-ovanja uopšte | — | `chunk["id"]` — ručno napisan literal, npr. `"zoo_cl552_chunk_0"` (:39, upsert :196) | `naslov, izvor, propis, tip, tekst` | **—** nema `delete()` |

---

## 2. Razvrstavanje A / B / C

### A) Kanonski pisci — `shared/vector_identity.canonical_vector_id` preko `ingest_session` — **1**

| # | pisač |
|---|---|
| 1 | `uploaded_doc/ingest.py:186` |

To je jedini pisač u celom repou koji uvozi `shared/vector_identity`
(potvrđeno grepom: uvozi ga još samo `shared/vector_deletion.py:45`, koji je čitalac/brisač,
i 4 pozivaoca koji računaju `verzija_dokumenta` pre nego što je proslede `ingest_session`-u).

**Nijedan od preostalih 18 pisača ne uvozi `shared/vector_identity` niti `shared/vector_deletion`.**

### B) Legacy pisci — poznat ali nekanonski obrazac, ID je predvidiv — **15**

| # | pisač | obrazac ID-a | determinističan? |
|---|---|---|---|
| 2 | `routers/auto_discovery.py:212` | `discovery_{sha256(chunk)[:32]}` | da |
| 3 | `routers/batch_ingest.py:63` | `{ascii_decision_id}_c{i}` | da |
| 4 | `routers/knowledge_base.py:105` | `kb_{uid}_{beleska_id}` | da |
| 5 | `routers/law_upload.py:92` | `{safe_doc_id}_c{i}` | da |
| 8 | `ingest_glossary_vasp_casp.py:177` | hardkodovan literal | da |
| 9 | `ingest_kz.py:129` | `md5("v2\|{zakon}\|{clan}\|{stav}")` | da (ali sadržaj-slep) |
| 10 | `ingest_laws.py:297` | isto | da (sadržaj-slep) |
| 12 | `ingest_short_15.py:154` | isto (lokalna kopija) | da (sadržaj-slep) |
| 13 | `scrape_zdi_mca.py:118` | `{slug}_chunk_{i}` / `zdi_{md5(labela)[:8]}_chunk_{i}` | da (sadržaj-slep) |
| 14 | `diag_zpp_revizija.py:196` | isto (treća kopija) | da (sadržaj-slep) |
| 15 | `scripts/ingest_bilten_to_pinecone.py:209` | `{decision_id}__chunk_{i}` | da |
| 16 | `scripts/ingest_carf_dac8.py:536` | hardkodovan literal | da |
| 17 | `scripts/ingest_case_law.py:173` | `{decision_id}__chunk_{i}` | da |
| 18 | `scripts/ingest_sudskapraksa.py:342` | `sp_{stem}__chunk_{i}` | da |
| 19 | `scripts/ingest_web3_addendum.py:214` | hardkodovan literal | da |

### C) Nepoznati / nebezbedni — ID se **ne može predvideti** — **3**

| # | pisač | ID | posledica |
|---|---|---|---|
| 6 | `interni_stavovi.py:89` | `is_{uid[:8]}_{i}_{uuid4().hex[:8]}` | ponovni ingest **duplira**; brisanje jednog stava nemoguće → jedini izlaz je `delete_all` nad korisnikovim namespace-om (:133) |
| 7 | `drafting/playbook.py:94` | `pb_{uid}_{i}_{uuid4().hex[:8]}` | isto (:131) |
| 11 | `ingest_misljenja.py:160` | `str(uuid.uuid4())` | ponovni ingest duplira ceo korpus; jedini izlaz `delete_all` nad `misljenja` (:221) |

**Podela: A = 1, B = 15, C = 3. Ukupno 19.**

---

## 3. Pisači koji proizvode ID VAN kanonskog ugovora

Kanonski ugovor = `{scope}__{32 heks}__k{n}_c{index}` sa `vx_scope`/`vx_verzija`/`vx_chunk_schema`
u metapodacima (`shared/vector_identity.py:131-146`, `:148-176`).

**18 od 19 pisača proizvodi ID van tog ugovora** — svi osim `uploaded_doc/ingest.py:186`.

Poimence, po tipu odstupanja:

**(a) ID bez ikakvog identiteta sadržaja — 17 pisača** (svi osim #1; #2 je jedini granični slučaj:
hešira sadržaj, ali po chunk-u, ne po dokumentu, pa promena teksta ne pravi novu *verziju dokumenta*
nego novi *nepovezan* vektor uz zadržan stari).

**(b) ID koji se ne može predvideti (uuid4) — 3 pisača**: #6 `interni_stavovi.py:89`,
#7 `drafting/playbook.py:94`, #11 `ingest_misljenja.py:160`.

**(c) ID deterministički, ali slep na sadržaj (heš koordinata, ne teksta) — 6 pisača**:
#9, #10, #12, #13, #14 (MD5 nad `v2|{zakon}|{clan}|{stav}` odn. nad labelom člana).
Tekst zakona može da se promeni u celosti, a svi ID-evi ostaju identični. `ingest_laws.py`
i `ingest_kz.py` to kompenzuju filter-delete-om pre upisa (:233, :57); #12, #13, #14 nemaju
nikakvu kompenzaciju.

**(d) Bez tenant bindinga u metapodacima — 14 pisača**: svi osim #1, #4, #6, #7.
Za korpuse (zakoni, praksa) to je tačno po dizajnu. Za #2 (`auto_discovery`) i #3 (`batch_ingest`)
to znači da vektor ne nosi ni pokazatelj ko ga je uneo — obe su admin rute, pa nije
poverljivost, ali jeste rupa u revizibilnosti.

**(e) Bez `chunk_index` bilo gde — 4 pisača**: #8, #13 (samo u ID-u), #16, #19.

**(f) `chunk_schema` verzija — postoji kod tačno 1 pisača (#1).**

**(g) Tri različita sanitizera ID-a pišu u JEDAN namespace `sudska_praksa`**:
`ingest_bilten_to_pinecone.py:71-87`, `ingest_case_law.py:77-79`, `ingest_sudskapraksa.py:81-91`.
Isti `chunk_id` sa razmakom ili ćirilicom daje TRI različita vektor ID-a zavisno od toga koji
skript ga unese. To je latentan izvor duplikata unutar najvećeg namespace-a.

---

## 4. Brisanje — stanje putanja

| putanja | opseg | povezana sa rutom? |
|---|---|---|
| `shared/vector_deletion.obrisi_vektore_dokumenta` (:198) | tačno jedan dokument, po `prefiks_dokumenta` | **NE** — grep za `obrisi_vektore_dokumenta` daje SAMO definiciju (`shared/vector_deletion.py:126`) i `tests/test_pine01_vector_deletion.py`. **Nijedan router, nijedan endpoint, nijedan background job je ne poziva.** Kanonsko brisanje postoji kao modul, ali je nedostupno iz aplikacije |
| `routers/knowledge_base.py:385` | jedan vektor, po ID-u | DA (`DELETE /api/knowledge/{entry_id}`) |
| `interni_stavovi.py:133`, `drafting/playbook.py:131` | `delete_all` nad celim korisničkim namespace-om | DA (`routers/interni.py:51`, `routers/drafting.py:593`) |
| `uploaded_doc/cleanup.py:90` | `delete_all`, **samo `tmp_*`** (:38-42), samo ako je `expires_at` prošao (:76-88) | DA (background task na svakom upload-u) |
| `routers/law_upload.py:273` | soft delete u `law_docs`, **ne dira Pinecone** | DA |
| CLI `delete_all` (#11 `misljenja`, #17 `sudska_praksa` ×2) | ceo namespace | n/a (CLI) |

**Izmereno na produkcijskim podacima**: svih 43 redova `predmet_dokumenti` ima
`content_sha256` **prazan** (dužina 0 za svih 43). `obrisi_vektore_dokumenta` bi za svaki
od njih vratio `REFUSED / "dokument nema content_sha256"` (`shared/vector_deletion.py:160-162`).
Dakle i da je putanja povezana, danas bi bila primenljiva na **0 od 43** dokumenta.
GDPR čl. 17 nad Pinecone kopijom je time i dalje tehnički nesprovodiv, sada iz dva razloga.

---

## 5. FAZA 7 — read-only inventar produkcije

Izvor: `describe_index_stats()` + `Index.list()` (samo ID-evi) + `fetch()` po ID-u.
Index host iz `PINECONE_HOST`. Merenje: 2026-08-13.

### 5.1 Ukupno i raspodela

**Ukupno vektora: 434.217. Broj namespace-ova: 11. Dimenzija: 3072.**

| namespace | vektora | udeo |
|---|---:|---:|
| `sudska_praksa` | 407.795 | 93,92 % |
| `zakoni_rs` | 25.822 | 5,95 % |
| `web3_zdi_mca` | 479 | 0,11 % |
| `misljenja` | 74 | 0,017 % |
| `carf_dac8` | 17 | 0,004 % |
| `pred_17d3edb4…` | 5 | |
| `pred_c41b9afc…` | 5 | |
| `pred_c326f5bb…` | 5 | |
| `pred_dfe8d288…` | 5 | |
| `pred_26904a63…` | 5 | |
| `pred_7d7e8e14…` | 5 | |
| **6× `pred_*` ukupno** | **30** | 0,007 % |

**Namespace-ovi koji NE POSTOJE u produkciji**, iako ih kod piše:
`kancelarija_{id}`, `user_{id}` (pisač #1 preko `api.py:5215`, `smart_intake.py:1414`,
`drafting.py:368`), `tmp_*` (#1 preko `dokument.py:305`), `kb_{uid}` (#4),
`interni_stavovi_{uid}` (#6), `playbook_{uid}` (#7), `zakon_rs` (#2). Nula vektora u svima.
Nema ni `__default__` namespace-a — pisači #9, #10, #12, #14 (`namespace=''`) danas nemaju
nijedan živ vektor.

### 5.2 Klasifikacija ID-eva

Uzorci: `sudska_praksa` i `zakoni_rs` su **UZORAK od 3.000 ID-eva** (0,74 % odn. 11,62 %
namespace-a); svi ostali namespace-ovi su izlistani **U CELOSTI**.
Metapodaci: uzorak od najviše 200 vektora po namespace-u (`fetch`).

| namespace | pregledano | uzorak? | kanonski `{scope}__{32heks}__k{n}_c{i}` | legacy `__chunk_N` | goli MD5-32 | uuid4 | ostalo (slug) |
|---|---:|---|---:|---:|---:|---:|---:|
| `sudska_praksa` | 3.000 / 407.795 | **UZORAK 0,74 %** | **0** | 3.000 | 0 | 0 | 0 |
| `zakoni_rs` | 3.000 / 25.822 | **UZORAK 11,62 %** | **0** | 0 | 3.000 | 0 | 0 |
| `web3_zdi_mca` | 479 / 479 | pun | **0** | 0 | 0 | 0 | 479 |
| `misljenja` | 74 / 74 | pun | **0** | 0 | 0 | **74** | 0 |
| `carf_dac8` | 17 / 17 | pun | **0** | 0 | 0 | 0 | 17 |
| 6× `pred_*` | 30 / 30 | pun | **0** | 0 | 0 | **30** | 0 |

**Broj vektora sa kanonskim ID-em: 0 u svakom pregledanom uzorku i u svakom potpuno
izlistanom namespace-u.** Kanonski ugovor (ID-01/ID-02) je uveden posle poslednjeg
produkcijskog ingesta i **nema nijednu živu instancu**.

Ekstrapolacija na cele uzorkovane namespace-ove nije dokaz i ovde se ne tvrdi;
tvrdi se izmereno: 0 / 6.600 pregledanih ID-eva u ta dva namespace-a.

**Legacy ID-evi (predvidiv obrazac): 3.000 (uzorak `sudska_praksa`) + 3.000 (uzorak
`zakoni_rs`) + 479 + 17 = 6.496 pregledanih; svi pregledani ID-evi u ta 4 namespace-a
su legacy.** Puni broj za dva uzorkovana namespace-a = UNKNOWN bez potpunog listanja.

**Nepredvidivi (uuid4) ID-evi: 104, izmereno u celosti** — 74 u `misljenja` + 30 u `pred_*`.

Primenom klasifikatora koji sam kod definiše
(`shared/vector_deletion.klasifikuj_orphan`, :230-245):
- `KANONSKI` = 0
- `LEGACY_POZNAT` = samo `__chunk_N` obrazac → uzorak `sudska_praksa` (3.000/3.000)
- `ORPHAN_UNIDENTIFIABLE` = uzorak `zakoni_rs` (3.000/3.000, goli MD5 nema `__`),
  `web3_zdi_mca` (479/479), `carf_dac8` (17/17), `misljenja` (74/74), `pred_*` (30/30)
  → **najmanje 3.600 izmereno, a po strukturi obrasca ceo `zakoni_rs` (25.822),
  `web3_zdi_mca` (479), `carf_dac8` (17), `misljenja` (74) i `pred_*` (30) = 26.422**

### 5.3 Nedostajuća polja (uzorak metapodataka)

| namespace | uzorak | bez tenant bindinga | bez `predmet_id` | bez identiteta dokumenta (`vx_verzija`/`vx_document_id`) | bez `chunk_index` | bez `chunk_schema` |
|---|---:|---:|---:|---:|---:|---:|
| `sudska_praksa` | 200 | 200 | 200 | 200 | 0 | 200 |
| `zakoni_rs` | 200 | 200 | 200 | 200 | **200** | 200 |
| `web3_zdi_mca` | 200 | 200 | 200 | 200 | **200** | 200 |
| `misljenja` | 74 | 74 | 74 | 74 | 0 | 74 |
| `carf_dac8` | 17 | 17 | 17 | 17 | **17** | 17 |
| 6× `pred_*` | 30 | **30** | **30** | **30** | 0 | 30 |

**Zbirno, po uzorcima: 0 vektora u produkciji ima tenant binding, 0 ima `predmet_id`,
0 ima identitet dokumenta, 0 ima `chunk_schema`.** Za 5 od 11 namespace-ova
nedostaje i `chunk_index`.

### 5.4 Obrnuti orphan — DB pokazuje na nepostojeće vektore

`predmet_dokumenti`: **43 reda**. Svih 43 ima `pinecone_namespace` oblika `pred_<32heks>`.
**Nijedan od tih 43 namespace-ova ne postoji u Pinecone-u** (presek sa 11 živih = 0).

Dakle: 43 dokumenta u bazi tvrde da imaju Pinecone kopiju koja ne postoji, a 30 vektora u
Pinecone-u nema red u bazi. To su dva **disjunktna** skupa — nema preklapanja ni po jednom
polju (vidi §6).

Ublažavajuća činjenica: sva 43 reda imaju `status = 'sacuvano'`, **nijedan nema
`'indeksirano'`**. Aplikacija dakle ne tvrdi da su pretraživi. To je tačan zapis stanja.

---

## 6. FAZA 1 — klasifikacija 30 orphan vektora

### 6.1 Tačni namespace-ovi i sadržina

| # | namespace | vektora | ID-evi | `session_id` u metapodacima |
|---|---|---:|---|---|
| O1 | `pred_17d3edb4c74847109a58bd23b1385dcc` | 5 | 5× uuid4 (`141ae06e…`, `1e832e44…`, `ad8e6c09…`, `d69f89c1…`, `f331aac4…`) | `17d3edb4…` (= sufiks namespace-a) |
| O2 | `pred_c41b9afc28c04349ba98fd515a23626f` | 5 | 5× uuid4 (`0fa3d6ce…`, `40234462…`, `62d65887…`, `6605105e…`, `69f256fc…`) | `c41b9afc…` |
| O3 | `pred_c326f5bbddbd4a578c6fc534b6fec981` | 5 | 5× uuid4 (`149f9efe…`, `456796bc…`, `4aea9862…`, `92583523…`, `df643187…`) | `c326f5bb…` |
| O4 | `pred_dfe8d28812144d80a19b58ca76ca95d8` | 5 | 5× uuid4 (`36ce2377…`, `80d95446…`, `9f194cc1…`, `a58deeae…`, `c0ae8912…`) | `dfe8d288…` |
| O5 | `pred_26904a63c3134f708c55f2f913fa40b6` | 5 | 5× uuid4 (`39a6a847…`, `756f4bf6…`, `82e8d3b1…`, `9559df61…`, `d9eb0f7b…`) | `26904a63…` |
| O6 | `pred_7d7e8e141e0a45f3995a3b6d0bdb7c21` | 5 | 5× uuid4 (`0f92db17…`, `15a9f2ac…`, `50dbdf1f…`, `6552885e…`, `a2183625…`) | `7d7e8e14…` |

Svih 6 nose **isti dokument**: `chunk_index` 0–4 sa identičnim dužinama teksta
(1344 / 1435 / 1186 / 1226 / 19 znakova) i identičnim `token_count` (575 / 585 / 486 / 507 / 7)
u svih šest. Isti PDF je uploadovan šest puta.

### 6.2 Koji metapodaci POSTOJE (identično u svih 30 vektora)

`article_label`, `chunk_index`, `chunk_mode`, `expires_at`, `session_id`,
`source_filename`, `source_format`, `text`, `token_count`

Vrednosti koje nisu sadržaj: `chunk_mode = "recursive"`, `source_format = "pdf"`,
`expires_at = ""` (prazno), `article_label = ""` (prazno), `chunk_index` = 0..4,
`session_id` = sufiks namespace-a.

### 6.3 Šta NEDOSTAJE za deterministički ID

Kanonski ID zahteva `scope` + `verzija` + `chunk_index` + `chunk_schema`
(`shared/vector_identity.py:131-146`).

| element | status | dokaz |
|---|---|---|
| `scope` (= `predmet_id`, inače `session_id`) | **NEDOSTAJE** — nema `predmet_id`, nema `vx_scope`. `session_id` postoji, ali nije `predmet_id` | 30/30 bez `predmet_id` |
| `verzija` (SHA-256 izvučenog teksta) | **NEDOSTAJE** — nema `vx_verzija`, nema `content_sha256`, nema `source_sha256` | 30/30 |
| `chunk_index` | **postoji** (0–4) | 30/30 |
| `chunk_schema` | **NEDOSTAJE** — nema `vx_chunk_schema` | 30/30 |
| tenant (`user_id`/`owner_user_id`/`kancelarija_id`) | **NEDOSTAJE** — nijedno polje | 30/30 |

### 6.4 Zašto se ID **ne može bezbedno rekonstruisati**

Tri nezavisna razloga, svaki dovoljan sam za sebe:

1. **`scope` je nepoznat i neizvodiv.** Kanonski `scope` je `predmet_id`. Nijedan od 30
   vektora ga nema, a `session_id` **nije** `predmet_id`: `generate_session_id()` je
   `uuid.uuid4().hex` (`uploaded_doc/session.py:7`) — 32 heks znaka bez crtica — dok je
   `predmeti.id` UUID sa crticama, 36 znakova (izmereno: `00a56895-4436-4a3d-a05e-…`).
   Dva različita prostora ID-eva. Presek 6 `session_id`-eva sa svih 19 `predmeti.id`:
   **0**; i sa crticama i bez njih (`0` u oba slučaja).

2. **`verzija` se ne može izračunati iz onoga što je u Pinecone-u.**
   `verzija_dokumenta(tekst)` (`vector_identity.py:242-248`) hešira **ceo izvučeni tekst**.
   U Pinecone-u su samo chunk-ovi, koji se **preklapaju** (`OVERLAP_TOKENS = 100`,
   dokumentovano u `uploaded_doc/ingest.py:135-139`, sa merenjem 31.600 → 36.428 znakova).
   Spajanje chunk-ova daje **duži tekst od originala**, pa drugačiji heš. Uz to je `text`
   u metapodacima skraćen na `_TEXT_TRUNCATE = 40_000` (`ingest.py:12, :151`). Rekonstrukcija
   originalnog teksta je nemoguća, dakle i verzije.

3. **`chunk_schema` nije zabeležen.** Vektori su nastali pre uvođenja
   `CHUNK_SCHEMA_VERSION`. Pretpostaviti `k1` značilo bi tvrditi da je tadašnji
   chunker identičan današnjem — to nijedan podatak ne dokazuje.

Zaključak: klasifikacija po sopstvenom klasifikatoru koda
(`shared/vector_deletion.klasifikuj_orphan`) je **`ORPHAN_UNIDENTIFIABLE` za svih 30**
(nema `vx_scope`/`vx_verzija`; ID nema `__`; nije `__chunk_`; ne počinje `kb_`/`discovery_`).
Po pravilu tog istog modula (:233-235) to je **konačna klasifikacija, ne međukorak ka
brisanju** — karantin je ispravan ishod.

### 6.5 Postoji li IJEDAN način da se povežu sa DB dokumentom bez nagađanja

**Ne. Sve kandidat-veze su izmerene i sve su prazne:**

| kandidat-veza | rezultat | merenje |
|---|---|---|
| `session_id` → `predmeti.id` | **0 poklapanja** od 19 predmeta | direktno i sa uklonjenim crticama |
| `pred_<session_id>` → `predmet_dokumenti.pinecone_namespace` | **0 poklapanja** od 43 reda | svih 43 pokazuje na druge `pred_*` namespace-ove |
| `content_sha256` → bilo šta | **nemoguće** — orphani nemaju heš, a svih 43 redova `predmet_dokumenti` ima **prazan** `content_sha256` (dužina 0 za svih 43). Obe strane su prazne |
| `source_filename` → `predmet_dokumenti.naziv_fajla` | **0 poklapanja** | i da ih ima, bilo bi nagađanje: među 43 reda ima samo 19 različitih naziva fajlova (najčešći se ponavlja 4×), pa ime fajla ni ne identifikuje dokument |
| `storage_path` (`session/{session_id}`) | ne pomaže — `session_id` u toj koloni je iz `generate_session_id()` novog upload-a, a nijedan od 43 ne odgovara nijednom od 6 |

Nema nijedne preostale kolone koja bi mogla nositi vezu. **Veza ne postoji.**

Poreklo (dokazano iz koda, ne iz pretpostavke): ovi vektori su nastali starim oblikom
`uploaded_doc/ingest.py` koji je kao Pinecone `id` koristio `chunk.chunk_id`, a to je
`str(uuid.uuid4())` iz `uploaded_doc/chunker.py:157` — ta linija **i danas postoji**, samo
je `ingest.py` više ne koristi za ID (:172 sada zove `canonical_vector_id`). Namespace je
nastao default granom `f"{namespace_prefix}{session_id}"` (:69) sa `namespace_prefix='pred_'`.
Grep za `namespace_prefix=` u celom repou (van testova) daje **nula produkcijskih pozivalaca** —
jedini pogodak je docstring `ingest.py:51`. Taj pisač u tom obliku više ne postoji.

---

## 7. KLJUČNO PITANJE — jesu li 30 orphan vektora danas dohvatljivi kroz autorizovani RAG?

### ODGOVOR: **NE. Nijedan od 30 nije dohvatljiv.**

Iscrpna enumeracija svih Pinecone read call-site-ova urađena je AST sweep-om
(`.query` / `.fetch` / `.list` / `.search*` sa `namespace=`/`vector=`/`top_k=`).
Van dijagnostičkih skripti i testova, **postoji tačno 5 putanja koje mogu da pogode
`pred_*` namespace**. Svaka je proverena:

#### Putanja 1 — `POST /api/dokument/pitanje` → `retrieve_documents(extra_namespaces=[...])`

`routers/dokument.py:435-439` prihvata `namespace_prefix ∈ {"tmp_", "pred_"}`, pa zove
`_verify_pred_namespace_ownership(body.session_id, "pred_", uid)` (:439), koje na
`routers/dokument.py:191-198` radi:

```python
r = supa.table("predmeti").select("id").eq("id", session_id).eq("user_id", uid).limit(1).execute()
if not (r.data or []):
    raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
```

`session_id` bi ovde morao biti `predmeti.id`. Orphani su `uuid4().hex` (32 znaka, bez crtica);
`predmeti.id` je UUID sa crticama (36 znakova). **Izmereno: presek 6 orphan `session_id`-eva
sa svih 19 `predmeti.id` = 0.** Grana uvek diže 404, PRE `validate_session` (:441) i PRE
`ask_agent(..., [f"{ns_prefix}{session_id}"])` (:478-482). **BLOKIRANO.**

Ovo je jedini produkcijski pozivalac `extra_namespaces` — grep za `extra_namespaces` van
testova i `diag_*` skripti daje samo `routers/dokument.py:481` i definiciju u
`app/services/retrieve.py:1766`.

#### Putanja 2 — `POST /api/dokument/klasifikuj-sesija`

`routers/dokument.py:596-601` isto prihvata `pred_`, pa zove isti
`_verify_pred_namespace_ownership(session_id, namespace_prefix, uid)` (:601) pre
`_fetch_session_tekst` (:603). **Isti 404. BLOKIRANO.**

#### Putanja 3 — `GET /api/predmeti/{predmet_id}/dokumenti/{dok_id}` (`api.py:5985-5990`)

Ovo je **druga** `pred_` putanja i ona **nema** poziv `_verify_pred_namespace_ownership`:

```python
if not tekst:
    ns = d.get("pinecone_namespace") or ""
    if ns:
        ns_prefix = "pred_" if ns.startswith("pred_") else "tmp_"
        session_id = ns.removeprefix("tmp_").removeprefix("pred_")
        tekst = await asyncio.to_thread(_fetch_session_tekst, session_id, ns_prefix)
```

Autorizacija ovde je red u bazi: `.eq("id", dok_id).eq("predmet_id", predmet_id).eq("user_id", uid)`
(`api.py:5946-5952`). To **jeste** ispravna kapija — namespace se ne uzima iz zahteva nego iz
reda koji je prošao proveru vlasništva. Ali putanja može doći samo do onog `pred_*` namespace-a
koji je zapisan u nekom redu `predmet_dokumenti`.

**Dve nezavisne merene barijere:**
1. **0 od 43 reda** ima `pinecone_namespace` jednak ijednom od 6 orphan namespace-ova.
2. **0 od 43 reda** ima prazan `tekst_sadrzaj` — uslov `if not tekst:` (`api.py:5985`) je
   danas neistinit za svaki red, pa se Pinecone fallback ne izvršava uopšte.

**BLOKIRANO, dvostruko.**

#### Putanja 4 — `POST /api/dokument/analiza` i `POST /api/dokument/rokovi`

`routers/dokument.py:538` i `:628` zovu `_verify_pred_namespace_ownership(..., "tmp_", ...)`
sa **hardkodovanim** `"tmp_"`, a `_fetch_session_tekst(body.session_id)` koristi default
`namespace_prefix="tmp_"` (:123). Ne postoji ulaz koji bi ove rute naveo na `pred_`.
Uz to je cross-prefix fallback uklonjen (:147-164) — ako deklarisani namespace vrati prazno,
vraća se prazno, bez pokušaja drugog prefiksa. **BLOKIRANO (nema `pred_` grane).**

#### Putanja 5 — `kancelarija_namespace` u `retrieve_documents`

`app/services/retrieve.py:1860-1873`. Vrednost dolazi isključivo iz `api.py:5473`
(`kancelarija_namespace=_owner_ns`), a `_owner_ns = _rag_ns(user.id, _kancelarija_id)`
(`api.py:5072`) → `shared/kancelarija_utils.py:57-58` vraća `f"kancelarija_{id}"` ili
`f"user_{id}"`. **Nikad `pred_*`.** BLOKIRANO strukturno.

#### Pozadinski poslovi

`uploaded_doc/cleanup.py:38-42` filtrira **isključivo** `ns.startswith(_TMP_NS_PREFIX)`
(`"tmp_"`, `ingest.py:13`). `pred_*` nikad ne ulazi ni u inspekciju. (Posledica: ovih 30
vektora nema nikakav mehanizam isteka — `expires_at` im je prazan, a i da nije, cleanup ih
ne gleda.) `services/retention_service.py:108` samo delegira istoj funkciji.
`routers/admin_dashboard.py:366` upisuje `pinecone_capacity_snapshots` iz
`describe_index_stats()` — samo brojevi po namespace-u, nikad sadržaj vektora.

#### Glasovna putanja

Grep za `ask_agent(` van testova i `diag_*`/`run_test_*` skripti: jedini produkcijski
pozivalac sa namespace argumentom je `routers/dokument.py:478`. `shared/voice_tools.py` se ne
pojavljuje ni u jednom Pinecone read call-site-u iz AST sweep-a. Nema glasovne putanje do
`pred_*`.

### Zaključak, sa tačnim mehanizmom i mestom u kodu

30 orphan vektora je nedohvatljivo kroz **svaku** postojeću autorizovanu putanju.
Presudni mehanizam je jedan i strukturan:

> `routers/dokument.py:194` — `supa.table("predmeti").select("id").eq("id", session_id).eq("user_id", uid)`
> poredi `uuid4().hex` (32 heks, bez crtica — `uploaded_doc/session.py:7`) sa `predmeti.id`
> (UUID sa crticama, 36 znakova). Ta dva prostora ID-eva se ne mogu poklopiti.
> Izmereno: 0 poklapanja od 19 predmeta. Rezultat je bezuslovni HTTP 404 na
> `routers/dokument.py:197`.

Rezervni mehanizam, za jedinu putanju koja tu proveru ne prolazi
(`api.py:5985-5990`): namespace ne dolazi iz zahteva nego iz reda `predmet_dokumenti`
koji je prošao `.eq("user_id", uid)`, a **0 od 43 reda** pokazuje na ijedan od 6 orphan
namespace-ova, i **0 od 43** ima prazan `tekst_sadrzaj` koji bi tu granu uopšte pokrenuo.

**Nema nijednog CRITICAL nalaza po ovom pitanju.** Vektori su izolovani, ali NISU nedostupni
za čitanje preko Pinecone API ključa — što znači da su i dalje **podaci klijenta koji postoje
van svake evidencije i van svakog mehanizma brisanja**. To ostaje otvorena stavka
(retencija / GDPR čl. 17), ne stavka poverljivosti kroz aplikaciju.

---

## 8. Sažetak izmerenih brojeva

| stavka | vrednost | uzorak? |
|---|---:|---|
| fizičkih Pinecone pisača | 19 | pun AST sweep, 0 parse grešaka |
| grupa A (kanonski) | 1 | |
| grupa B (legacy, predvidiv ID) | 15 | |
| grupa C (nepredvidiv ID) | 3 | |
| pisača van kanonskog ugovora | 18 | |
| ukupno vektora | 434.217 | pun `describe_index_stats` |
| namespace-ova | 11 | pun |
| vektora sa kanonskim ID-em | **0 / 6.600 pregledanih** | uzorak za 2 najveća ns |
| uuid4 (nepredvidiv) ID | 104 | pun (74 `misljenja` + 30 `pred_*`) |
| orphan vektora (bez reda u bazi) | 30 | pun |
| vektora bez tenant bindinga | 721 / 721 pregledanih | uzorak ≤200 po ns |
| vektora bez `predmet_id` | 721 / 721 | isto |
| vektora bez identiteta dokumenta | 721 / 721 | isto |
| vektora bez `chunk_index` | 417 / 721 | isto |
| vektora bez `chunk_schema` | 721 / 721 | isto |
| redova `predmet_dokumenti` | 43 | pun |
| redova koji pokazuju na nepostojeći namespace | 43 / 43 | pun |
| redova sa praznim `content_sha256` | 43 / 43 | pun |
| redova sa `status='indeksirano'` | 0 / 43 | pun |
| predmeta u bazi | 19 | pun |
| poklapanja orphan `session_id` ↔ `predmeti.id` | 0 | pun |
