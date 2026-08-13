# Pinecone Data Boundary — Forenzički nalaz

**Prioritet #4 — CRITICAL FORENSICS**
Datum: 2026-08-13 · Metod: čitanje koda + izmereni izlaz (`describe_index_stats()`, lokalno merenje chunkera)
Nijedan produkcijski fajl nije menjan. Nijedan upis/brisanje u Pinecone nije izvršen. Nijedan tuđi dokument nije pretraživan ni ispisan.

---

## 0. Sažetak za odlučivanje

| Pitanje | Odgovor | Dokaz |
|---|---|---|
| Da li je **cross-tenant** (između različitih kancelarija/korisnika) retrieval moguć? | **NE** — kroz nijednu proverenu putanju | §2, §3 |
| Da li je **cross-user unutar iste kancelarije** moguć? | **DA — po dizajnu, i širi je od SQL granice** | F-01 |
| Da li su zakoni i klijentski dokumenti u istom namespace-u? | **NE** — fizički odvojeni, izmereno | §1 |
| Da li Pinecone dobija plaintext klijentskog dokumenta? | **DA**, po chunk-u; ceo dokument je rekonstruisan spajanjem | §4, F-07 |
| Postoji li delete path za klijentske dokumente? | **NE** za trajne (`kancelarija_*`/`user_*`/`pred_*`). DA samo za `tmp_*`, `kb_*`, `interni_stavovi_*`, `playbook_*` | F-03 |
| Tvrdnja prethodnog sprinta „pun tekst dokumenta, do 40.000 znakova po vektoru" | **NETAČNA u brojci** — izmereno max 1.637 znakova po vektoru; 40.000 nikad ne veže | F-07 |

---

## 1. Izmereno stanje indeksa (jedini indeks: `vindex-ai`, dim 3072)

`describe_index_stats()`, izvršeno 2026-08-13, samo agregat (identifikatori zakriveni):

```
dimension: 3072 | total_vector_count: 434217 | namespace_count: 11

SCHEME                                   | namespaces | vectors
sudska_praksa                            |     1 | 407795
zakoni_rs                                |     1 |  25822
web3_zdi_mca                             |     1 |    479
misljenja                                |     1 |     74
pred_<REDACTED>                          |     6 |     30
carf_dac8                                |     1 |     17
```

Zaključci koji slede direktno iz merenja:

1. **Zakoni (`zakoni_rs`) i klijentski dokumenti (`pred_*`) NISU u istom namespace-u.** Rizik „RAG nad zakonima vraća tuđi klijentski dokument" **ne postoji na nivou podataka** — Pinecone query je namespace-scoped, a `_pretraga_zakoni`/`_direktan_fetch_clana` uvek prosleđuju `namespace=_ZAKONI_NS` (`app/services/retrieve.py:901,916,1020`).
2. **`__default__` namespace više nema vektora.** Zbir prikazanih namespace-ova (407795+25822+479+74+30+17) = 434.217 = `total_vector_count`. Istorijski nalaz „7589 vektora pogrešnog zakona u `__default__`" je time zatvoren na nivou podataka. Napomena: `ingest_laws.py:297` i dalje upsertuje **bez** `namespace=` (dakle u `__default__`) — ponovno pokretanje te skripte danas ponovo bi napravilo nevidljive vektore. Skripta nije deo servisa.
3. **Ne postoji nijedan `kancelarija_*` ni `user_*` namespace.** To je aktuelna („vlasnik znanja") šema uvedena 2026-07-26. U produkcionom indeksu nema nijednog vektora po toj šemi — dakle od te izmene nijedan predmet-dokument nije završio u Pinecone-u (ili nije bilo upload-a). Kod je živ i puniće se pri sledećem upload-u.
4. **Ne postoji nijedan `tmp_*` namespace u trenutku merenja** — TTL/cleanup rade.
5. `firm_<hex>` (šema iz `migrations/045_firm_intelligence.sql:29`) **ne postoji u indeksu** — v. F-09.

---

## 2. Popis namespace šema i granica

| Šema | Ko upisuje | Ko čita | Granica izolacije | Filter pri čitanju |
|---|---|---|---|---|
| `zakoni_rs` | `routers/law_upload.py:92` (FOUNDER-only, `_require_admin:41-44`) | svi | javni sadržaj | `{"law"/"clan"/"zakon"}` opciono |
| `sudska_praksa`, `misljenja` | `routers/batch_ingest.py:63` (FOUNDER-only + `ALLOWED_NAMESPACES:28`) | svi | javni sadržaj | opciono |
| `web3_zdi_mca`, `carf_dac8` | `scripts/*`, `web3_compliance.py` | svi | javni sadržaj | — |
| `tmp_<uuid4>` | `uploaded_doc/ingest.py:68,101` preko `routers/dokument.py:300` | vlasnik | **namespace + `owner_user_id` metadata provera** (`routers/dokument.py:200-214`) | nema (namespace je granica) |
| `pred_<uuid4>` (legacy, do 2026-07-26) | ranije `api.py`, više se ne piše | — | provera POKVARENA, fail-closed (F-02) | — |
| `kancelarija_<kancelarija_id>` / `user_<user_id>` (aktuelno) | `api.py:5154`, `routers/smart_intake.py:1402`, `routers/drafting.py:358` | svi ACTIVE članovi kancelarije | **namespace = kancelarija ili solo korisnik** | `{"type": {"$in": ["case_doc","draft_final"]}}` (`retrieve.py:1851`) |
| `kb_<user_id>` | `routers/knowledge_base.py:105-119` | isti korisnik | namespace | nema |
| `interni_stavovi_<user_id>` | `interni_stavovi.py:81` | isti korisnik | namespace | nema |
| `playbook_<user_id>` | `drafting/playbook.py:86` | isti korisnik | namespace | nema |

**Izolacija je kroz namespace, ne kroz metadata filter.** To je arhitektonski ispravan izbor (Pinecone garantuje da query nikad ne prelazi granicu namespace-a), pod uslovom da ime namespace-a nikad ne dolazi od klijenta — v. §3.

---

## 3. Da li klijent može da bira namespace? (ključno pitanje za cross-tenant)

Provereno je svako mesto gde ime namespace-a ulazi u query:

| Ulaz | Poreklo imena | Nalaz |
|---|---|---|
| `retrieve_documents(kancelarija_namespace=...)` | `api.py:5018-5020` → `rag_owner_namespace(user.id, await get_kancelarija_id(supa, user.id))` | **server-derived iz autentifikovanog `user.id`** — klijent ga ne dodiruje |
| `retrieve_documents(extra_namespaces=[...])` iz `/api/dokument/pitanje` | `routers/dokument.py:463` → `[f"{ns_prefix}{body.session_id}"]` | `ns_prefix` je whitelist (`:418-419`, samo `tmp_`/`pred_`); `session_id` prolazi `_verify_pred_namespace_ownership` (`:421`) |
| `retrieve_documents(extra_namespaces=[...])` iz `/api/pitanje` i `/api/pitanje/stream` | `api.py:3360-3361`, `3493-3494` → `_get_firma_namespace(user["user_id"])` iz baze | server-derived; v. F-09 |
| `routers/praksa.py:429`, `api.py:4671` | hardkodirana lista `("sudska_praksa","upravna_praksa")` | ok |
| `routers/auto_discovery.py:458` (`namespace: str = Form(...)`) | **klijent bira ime namespace-a** | ali `Depends(_require_discovery_admin)` (`:88-96`) → samo founder. **Write-only** putanja, ne read |
| `routers/batch_ingest.py` | klijent bira, ali `ALLOWED_NAMESPACES={"sudska_praksa","misljenja"}` + founder | ok |

**Zaključak: nema putanje kojom neprivilegovani korisnik može da natera sistem da čita namespace drugog vlasnika.** Cross-tenant retrieval **nije moguć**.

`rag_owner_namespace` (`shared/kancelarija_utils.py:45-58`) pri grešci u `get_kancelarija_id` (`:41-42` vraća `None` na svaki izuzetak) pada na `user_{uid}` — dakle **u restriktivniji**, ne u širi namespace. Fail-safe smer je ispravan (posledica je gubitak vidljivosti unutar firme, ne curenje).

---

## 4. DATA FLOW: DOCUMENT → OCR → CHUNK → EMBEDDING → PINECONE

Referentna putanja: `POST /api/predmeti/{predmet_id}/dokument` (`api.py:4990-5330`, „Pipeline A"). Smart Intake (`routers/smart_intake.py`) i Drafting promote (`routers/drafting.py:325-416`) koriste isti `ingest_session`.

### Korak 1 — DOCUMENT (upload)
| | |
|---|---|
| DATA | Sirov PDF/DOCX (≤10 MB, `api.py:5027`; 25 MB na `/api/dokument/upload`, `routers/dokument.py:34`) |
| DESTINATION | Supabase Storage bucket `intake-dokumenti`, ključ `{user_id}/{predmet_id}/{uuid}.{ext}` (`api.py:5048-5056`) |
| RETENTION | Trajno. `services/retention_service.py:14-18` eksplicitno izuzima predmete/klijente/dokumente („zakonska obaveza advokata") |
| ENCRYPTION | **AES-GCM pre upload-a** (`routers/smart_intake.py:95-105`, ključ iz `security/crypto._get_field_key`) |
| TENANT BOUNDARY | Ključ sadrži `user_id`; vlasništvo predmeta provereno na `api.py:5008` (`.eq("user_id", user.id)`) |
| DELETE PATH | Samo kompenzujuće brisanje pri neuspehu obrade (`api.py:5249-5265`). Nema korisničkog brisanja |
| AUDIT | `log_action("dokument_upload", ...)` (`api.py:5271-5279`) |

### Korak 2 — OCR / ekstrakcija teksta
| | |
|---|---|
| DATA | Plaintext dokumenta u RAM-u; privremeni fajl na disku (`api.py:5077-5079`) |
| DESTINATION | `tempfile.NamedTemporaryFile`, obrisan u `finally` (`api.py:5096-5099`) |
| RETENTION | Trajanje zahteva |
| ENCRYPTION | **Nema** — plaintext na disku dok traje ekstrakcija |
| TENANT BOUNDARY | Proces-lokalno |
| DELETE PATH | `tmp_path.unlink()` u `finally` |
| AUDIT | `[OCR]` log linija (`api.py:5104-5105`) — bez sadržaja |

### Korak 3 — CHUNK
| | |
|---|---|
| DATA | `UploadedDocChunk` objekti (`uploaded_doc/chunker.py:151-170`) |
| DESTINATION | RAM |
| RETENTION | Trajanje zahteva |
| ENCRYPTION | — |
| TENANT BOUNDARY | — |
| DELETE PATH | GC |
| AUDIT | — |
| **Izmereno** | `TARGET_TOKENS=600`, `MAX_CHUNK_TOKENS=800` (`chunker.py:21-23`). Empirijski max: **1.570 znakova (recursive) / 1.637 znakova (article-aware)**, max 599/598 tokena |

### Korak 4 — EMBEDDING
| | |
|---|---|
| DATA | Plaintext svakog chunk-a → **OpenAI** (`text-embedding-3-large`, `uploaded_doc/ingest.py:29-36,75`) |
| DESTINATION | OpenAI API (treća strana, van EU po defaultu) |
| RETENTION | Po OpenAI politici — **nije verifikovano u kodu** |
| ENCRYPTION | TLS u tranzitu |
| TENANT BOUNDARY | Nema — svi korisnici dele isti API ključ |
| DELETE PATH | Nijedan iz aplikacije |
| AUDIT | Nema per-chunk zapisa |

### Korak 5 — PINECONE
| | |
|---|---|
| DATA | Vektor + **metadata sa plaintext-om chunk-a** (v. §5) |
| DESTINATION | Indeks `vindex-ai`, namespace `kancelarija_{id}` ili `user_{uid}` (`api.py:5154`) |
| RETENTION | **NEOGRANIČENO.** `expires_at` je prazan string kad god `namespace_override` postoji (`uploaded_doc/ingest.py:69`), a `cleanup_expired` gleda samo `tmp_*` (`uploaded_doc/cleanup.py:38-42`) |
| ENCRYPTION | **Nema application-level enkripcije.** Original u Storage-u je AES-GCM, njegov plaintext u Pinecone-u **nije** — asimetrija |
| TENANT BOUNDARY | Namespace (kancelarija ili solo korisnik) + `filter={"type": {"$in": ["case_doc","draft_final"]}}` pri čitanju (`retrieve.py:1851`) |
| DELETE PATH | **NE POSTOJI** (F-03) |
| AUDIT | Upis: `[INGEST]` log (`ingest.py:102-105`) + `log_action("dokument_upload")`. Čitanje: **nije auditovano** osim `log_action("dokument_pitanje")` (`routers/dokument.py:466-470`); RAG čitanja unutar `ask_agent` nemaju zapis |

---

## 5. Tačan sadržaj metadata (PII inventar)

Iz `uploaded_doc/ingest.py:80-92` — svaki vektor:

```python
{
  "session_id":      session_id,                 # uuid4 hex
  "source_filename": manifest.source_filename,   # PII: originalno ime fajla
  "source_format":   "pdf" | "docx",
  "chunk_index":     int,
  "chunk_mode":      "article_aware" | "recursive" | ...,
  "article_label":   str,
  "text":            chunk.text[:40_000],        # PLAINTEXT (izmereno ≤1.637 zn.)
  "token_count":     int,
  "expires_at":      "" за trajne / ISO za tmp_
}
```
plus `extra_metadata` po putanji:

| Putanja | Dodatna metadata | PII |
|---|---|---|
| `api.py:5155-5166` (predmet upload) | `predmet_id`, `kancelarija_id`, `type="case_doc"`, `origin`, `parent_id`, `origin_chain`, `created_at`, `golden_template` | `predmet_id`, `kancelarija_id` |
| `routers/smart_intake.py:1403-1413` | isto | isto |
| `routers/drafting.py:359-368` | isto + `type="draft_final"`, `parent_id=staging_row["id"]` | isto |
| `routers/dokument.py:309` (ad-hoc tmp_) | `origin`, **`owner_user_id`** | `owner_user_id` |
| `routers/knowledge_base.py:109-116` | `beleska_id`, `naslov`, `sadrzaj[:1000]`, `tagovi`, `predmet_id`, **`user_id`** | naslov + sadržaj beleške + `user_id` |
| `interni_stavovi.py:70-76` | **`user_id`**, `naslov`, `text`, `tip` | isto |
| `routers/law_upload.py:128-135` | `text`, `naziv_zakona`, `broj_sl_glasnika`, `doc_id`, `source` | javni sadržaj |

**Zaključak PII:** ime fajla, `user_id`/`owner_user_id`, `predmet_id`, `kancelarija_id` i **pun tekst chunk-a** su u Pinecone metadata. Ime klijenta nije eksplicitno polje, ali se rutinski nalazi *unutar* `text` (ugovori, tužbe, presude).

---

## 6. Nalazi

### F-01 — RAG granica je ŠIRA od SQL granice unutar kancelarije · **HIGH**
`retrieve.py:1847-1852` pretražuje ceo `kancelarija_{id}` namespace za **svakog** ACTIVE člana firme, sa filterom samo po `type`, **bez `predmet_id` i bez `user_id` filtera**. Komentar na `:2124-2130` to eksplicitno potvrđuje: rezultati iz drugih predmeta se „NE filtriraju napolje", samo dobijaju niži skor.

Ali SQL granica je uža: pristup predmetu je vlasnik (`api.py:5008`: `.eq("user_id", user.id)`) **plus eksplicitno pozvani saradnici** (`predmet_saradnici`, `routers/saradnja.py:9-21`). Član kancelarije koji **nije** pozvan na predmet X ne može da otvori X kroz API — ali njegovo bilo koje AI pitanje može da mu vrati **doslovan tekst** dokumenata iz predmeta X kroz RAG kontekst (`format_doc_passage`, `app/services/doc_formatter.py:20-58`, vraća `header + pun tekst chunk-a`).

To je namerna „institucionalna memorija", ali je **de facto proširenje prava pristupa koje advokat nije odobrio po predmetu** i koje nijedan UI ne saopštava. Za advokatsku kancelariju sa Kineskim zidom (sukob interesa između klijenata iste firme) ovo je materijalan problem.
Trenutno je izloženost **0 vektora** (§1, nema `kancelarija_*` namespace-a), ali putanja je živa za sledeći upload.

**Najmanja izmena koja čuva funkcionalnost:** dodati `predmet_id ∈ (predmeti korisnika ∪ predmeti gde je saradnik)` u postojeći `filter` na `retrieve.py:1851`, ili uvesti eksplicitan per-kancelarija opt-in flag. Filter mehanizam već postoji i već se koristi — ne traži novu arhitekturu.

### F-02 — `pred_*` ownership provera je logički pokvarena · **MEDIUM** (fail-closed)
`routers/dokument.py:191-198` proverava vlasništvo tako što traži `predmeti.id == session_id`. Ali `pred_` namespace je istorijski `pred_{generate_session_id()}` — **uuid4 hex, a ne `predmeti.id`** (dokaz: commit `606f3a29`, „ingest_session dobija namespace_prefix param", `pinecone_namespace: f"pred_{session_id}"`; frontend to čita nazad iz kolone i skida prefiks: `static/vindex.js:12439` `_docSessionId = _rNs.replace(/^pred_/,'')`).

Posledica: provera **nikad ne prolazi**, ni za pravog vlasnika → `404` za svaki `pred_` dokument. Bezbednosno je to fail-closed (dobro), funkcionalno je mrtvo: 6 namespace-ova / 30 vektora klijentskog plaintext-a je nedostupno i istovremeno neobrisivo.
Dodatno, `static/vindex.js:20203` posle novog upload-a postavlja `_docNamespacePrefix='pred_'` iako backend od 2026-07-26 piše u `kancelarija_*`/`user_*` — dakle „Pitanje o dokumentu" nad predmet-dokumentom cilja namespace koji uopšte ne postoji.

### F-03 — Ne postoji delete path za trajne klijentske vektore · **HIGH**
- `uploaded_doc/cleanup.py:38-42` briše **isključivo** `tmp_*`.
- `services/retention_service.py:102-119` poziva baš taj `cleanup_expired` — dakle retention servis **ne pokriva** `kancelarija_*`, `user_*`, `pred_*`.
- `routers/gdpr.py:201-254` (`DELETE /api/gdpr/account`) anonimizuje samo `profiles` i `korisnik_email_notif`; **nijedan Pinecone poziv**. Odgovor korisniku to i priznaje (`:250-253`).
- Nema `@router.delete` ni za predmet ni za `predmet_dokumenti` — dokument se u aplikaciji ne može obrisati uopšte (exhaustive grep, §Metod).
- `routers/law_upload.py:262-280` je izričito soft delete: *„NE briše iz Pinecone"*.

Postojeći delete path-ovi (za kontrast): `interni_stavovi.py:125`, `drafting/playbook.py:123`, `routers/knowledge_base.py:385` (`delete(ids=...)`).

**Efekat:** „pravo na zaborav" (GDPR čl. 17 / ZZPL čl. 26) je tehnički nesprovodivo nad Pinecone kopijom klijentskog plaintext-a. Ovo je najveći usklađenost-rizik u ovom izveštaju.

### F-04 — Re-index pravi duplikate · **MEDIUM**
`uploaded_doc/chunker.py:157`: `chunk_id=str(uuid.uuid4())`, a `ingest.py:94` koristi baš to kao Pinecone `id`. ID je **nedeterministički** → ponovni upload istog dokumenta upsertuje **potpuno nov set vektora**, stari ostaje (i nema ga ko obrisati, F-03). RAG onda vraća isti pasus više puta i troši top_k budžet.
Dedup po sadržaju postoji **samo informativno** na DB nivou (`api.py:5130-5139`, `_mozda_duplikat`, eksplicitno „Non-blocking, informational only").
Kontrast: `routers/law_upload.py:126` (`f"{safe_id}_c{ci}"`), `routers/batch_ingest.py:93`, `scripts/ingest_case_law.py` koriste **determinističke** ID-jeve — obrazac već postoji u repou.

### F-05 — Orphan vektori pri neuspeloj ingestiji · **MEDIUM** (poznat, evidentiran)
Redosled je: Pinecone upsert (`api.py:5152-5167`) **pa** DB upis (`:5219-5229`). Ako DB upis padne, kod diže `HTTPException` (`:5244-5248`) i briše enkriptovani blob iz Storage-a (`:5250-5259`), **ali Pinecone vektor ostaje** — priznato u komentaru na `:5240-5243` („Pinecone vektor ostaje ... deferred, INTAKE-001-shape"). Nema rollback-a niti kompenzujućeg `index.delete`.
Isto važi za `routers/smart_intake.py:1400-1417` (Pinecone greška je non-fatal, obrada se nastavlja).

### F-06 — Plaintext u Pinecone-u nije aplikativno enkriptovan, original jeste · **MEDIUM**
Isti bajtovi prolaze kroz dva sistema sa dva režima: original → AES-GCM (`routers/smart_intake.py:95-105`), njegov tekst → Pinecone metadata u čistom obliku (`ingest.py:87`). Pinecone vendor-side enkripcija at rest se ne može potvrditi iz koda i nije pod kontrolom aplikacije. Ovo je nedosledna primena istog kontrole-standarda nad istim podatkom.

### F-07 — Tvrdnja „40.000 znakova po vektoru" je netačna · **INFO / ispravka prethodnog sprinta**
`_TEXT_TRUNCATE = 40_000` (`ingest.py:12,79`) **postoji**, ali **nikad ne veže**: chunker tvrdo ograničava svaki chunk na `MAX_CHUNK_TOKENS=800` (`chunker.py:23,101-120`).
Izmereno (lokalno, `chunk_document` nad sintetičkim tekstom):
```
recursive : chunks=232  max_char=1570  max_tok=599
article   : chunks=108  max_char=1637  max_tok=598
_TEXT_TRUNCATE = 40000 -> binds? False
```
**Tačna formulacija nalaza:** nijedan pojedinačan vektor ne sadrži pun dokument; **ali skup svih vektora jednog dokumenta sadrži njegov pun plaintext, i sistem ga zaista sklapa nazad** — `routers/dokument.py:130-145` (`top_k=1000`, sortiranje po `chunk_index`, `"\n\n".join(texts)`). Dakle „Pinecone drži pun tekst dokumenta trajno" **stoji**; „do 40.000 znakova po vektoru" **ne stoji**.

### F-08 — Zašto plaintext uopšte mora biti tamo (i koja je minimalna izloženost)
Tekst iz metadata se čita nazad na 3 mesta:
1. `app/services/doc_formatter.py:53-56` — pasus koji ide u LLM kontekst. **Neophodno** za RAG.
2. `routers/dokument.py:123-167` `_fetch_session_tekst` — rekonstrukcija **celog** dokumenta za `/analiza`, `/rokovi`, `/klasifikuj-sesija`.
3. `routers/praksa.py:413-449`, `retrieve.py:2653-2716` — javna sudska praksa, nije klijentski podatak.

Za putanju (2) plaintext u Pinecone-u je **redundantan**: isti tekst već postoji u `predmet_dokumenti.tekst_sadrzaj` (do 100.000 znakova, `api.py:5179,5219`) i u enkriptovanom originalu u Storage-u.
**Najmanja izloženost koja čuva funkcionalnost:** zadržati `text` u metadata samo za retrieval-pasus (putanja 1), a putanje (2) preusmeriti na `predmet_dokumenti.tekst_sadrzaj` po `predmet_id` — čime Pinecone prestaje da bude sistem iz kojeg se ceo dokument može rekonstruisati. Alternativa (jača, veći zahvat): u metadata čuvati samo `document_id + chunk_index`, a tekst pasusa dohvatati iz baze posle rangiranja.

### F-09 — `firm_<hex>` namespace se čita, a nikad se ne piše · **LOW** (mrtav kanal)
`api.py:3360-3361` i `3493-3494` na **glavnoj** putanji pitanja prosleđuju `_get_firma_namespace(uid)` kao `extra_namespaces`. Ta vrednost je `kancelarije.pinecone_namespace` = `firm_<16 hex>` (`migrations/045_firm_intelligence.sql:29`).
Nijedan `upsert` u repou ne cilja `firm_*` (proveren svaki `namespace=` argument), i u indeksu takvog namespace-a nema (§1). Čita se **bez ikakvog metadata filtera** (`retrieve.py:963-966`).
Dodatno: `routers/kancelarija.py:234-238` pri kreiranju firme **ne postavlja** `pinecone_namespace`, a nijedan endpoint ga ne ažurira → za sve firme kreirane posle migracije 045 vrednost je `NULL` → `_get_firma_namespace` vraća `None`. Kolona je `UNIQUE`, dakle ni teoretski se ne može podesiti na tuđi namespace kroz duplikat. Bezbednosno bezopasno, ali je to **treća paralelna namespace šema** uz `kancelarija_*` i `pred_*` — direktna kontradikcija principu „1 koncept = 1 vlasnik".

### F-10 — `/test-pinecone` ispisuje sirovu metadata · **LOW**
`api.py:2374-2403`: query **bez `namespace=`** (dakle `__default__`, koji je prazan) i vraća `first_match_metadata` u celosti, uključujući `text`. Gejtovano `ADMIN_DEBUG_KEY`-jem. Danas bezopasno jer je `__default__` prazan; postane opasno ako neka skripta ponovo napuni default namespace (v. §1 tačka 2).

---

## 7. Metod i granice ovog nalaza

Izvršeno:
- `describe_index_stats()` nad produkcionim `PINECONE_HOST` iz `.env` (read-only; nijedan `query`, `upsert`, `delete`).
- Lokalno merenje `uploaded_doc.chunker.chunk_document` nad sintetičkim tekstom (bez mreže).
- Statičko čitanje svakog `namespace=` argumenta, svakog `index.query(`/`upsert(`/`delete(` poziva u repou (van `tests/` i `scripts/`), i svih ulaznih tačaka koje prosleđuju ime namespace-a.
- `git log -S` za utvrđivanje porekla `pred_` šeme.

Nije izvršeno / ne tvrdi se:
- Nije pretraživan nijedan tuđi namespace niti ispisan ijedan stvarni klijentski dokument.
- Pinecone vendor-side enkripcija at rest i OpenAI retention nisu verifikovani — to su ugovorne, ne kodne činjenice.
- RLS politike Supabase-a nisu deo ovog nalaza (odvojen prioritet).
- Merenje §1 je snimak stanja 2026-08-13; odsustvo `kancelarija_*` namespace-a znači „nema vektora danas", ne „kod ne radi".

## 8. Preporučeni redosled (bez ovlašćenja za implementaciju)

1. **F-03** — delete path za Pinecone vezan za brisanje predmeta/dokumenta i za GDPR erasure. Bez ovoga je „pravo na zaborav" nesprovodivo.
2. **F-01** — suziti `filter` na `retrieve.py:1851` na predmete kojima korisnik stvarno ima pristup (ili eksplicitan opt-in kancelarije).
3. **F-04** — deterministički vector ID (`{document_id}_c{chunk_index}`), obrazac već postoji u `law_upload.py`/`batch_ingest.py`.
4. **F-02** — ili popraviti `pred_` proveru (mapirati preko `predmet_dokumenti.pinecone_namespace`), ili migrirati/obrisati tih 30 legacy vektora.
5. **F-08** — skinuti rekonstrukciju celog dokumenta sa Pinecone-a na `predmet_dokumenti.tekst_sadrzaj`.
6. **F-05** — kompenzujuće `index.delete(ids=...)` u `except` bloku (traži F-04 determinističke ID-jeve da bi uopšte bilo izvodljivo).
7. **F-09/F-10** — ukloniti mrtav `firm_*` kanal i sirov metadata ispis.
