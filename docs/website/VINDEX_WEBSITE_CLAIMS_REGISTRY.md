# VINDEX AI — REGISTAR JAVNIH TVRDNJI (RE-VERIFIKACIJA)

Stanje: `108dc48b` (Wave 11, BASELINE FROZEN).
Metod: čitanje koda i testova na trenutnom HEAD-u. **Aplikacija nije pokretana, produkciona
baza nije dodirnuta, nijedan produkcioni fajl nije menjan.**

Ovaj dokument **zamenjuje** `VINDEX_AI_PUBLIC_CLAIMS.md` (stanje `b29ffb6f`) i §13–15
`VINDEX_AI_FINAL_WEBSITE_READINESS.md` (stanje `a171189f`) kao obavezujući izvor za sajt.

Legenda statusa:
`VERIFIED` — dokazano kodom i testom · `PARTIALLY_VERIFIED` — dokazano uz imenovanu ogradu ·
`EXPERIMENTAL` — radi, ali nije stabilna funkcija · `ROADMAP` — nije implementirano ·
`UNVERIFIED` — nije moglo da se proveri · `FALSE` — provereno netačno.

**Pravilo:** `UNVERIFIED` i `FALSE` se ne pojavljuju na sajtu ni u kom obliku.
`PARTIALLY_VERIFIED` sme **samo** uz ogradu doslovno prepisanu iz kolone „Sme na sajt".

---

# 1. PROMENE U ODNOSU NA `b29ffb6f` / `a171189f`

## 1.1 Postalo dokazivo (nije bilo ranije)

| Šta | Gde je promena |
|---|---|
| **Korisnik VIDI pravne izvore ispod AI odgovora** | `b984a039 feat(ui): expose legal sources in answer provenance` — dodao `_vxRenderIzvori` u `static/vindex.js:924-955`, CSS `static/vindex.css:9636-9679`. Do tada su jedine dve reference u `vindex.js` element **skrivale**. Ovo obara nalaz „UI-MISSING" iz `a171189f` §6 i „UI — prikazuje li? NE" iz `FINAL_PROVENANCE_CLOSURE.md` §4–8. |
| **Nepromenljiva evidencija je DOKAZANA, ne samo deklarisana** | Do Wave 11 tvrdnja „upisan red se ne može obrisati" počivala je isključivo na tome što `.sql` fajl postoji u repou — migracija 043 nije bila ni u jednom lancu koji se izvršava. Sada `tests/test_rc_migration_gate.py:394-465` izvršava 043 nad pravim PostgreSQL-om i meri triger. |
| **Kad governance kapija ne radi, AI se ne izvršava** | `shared/ai_client.py:131-177` — otrovna brana nad 4 `openai` konstruktora. U `b29ffb6f` je „startup policy" bila **owner action**, tj. nezatvorena. |
| **Svaki OpenAI chat poziv prolazi kroz jednu kapiju** | `shared/ai_client.py:781-782` (patch nad SDK klasama) + `security/response_firewall.py` na izlazu. `tests/test_rc_cold_start.py` meri da svih 8 SDK metoda nosi `_vindex_guarded` u svežem procesu. |
| **Podaci jednog predmeta ne ulaze u analizu drugog — na izvoru** | `shared/case_context.py` — do Wave 11 je od 7 upita samo onaj nad `predmeti` nosio `.eq("user_id", uid)`; tuđi nazivi fajlova, datumi ročišta i tekst komentara su se stvarno dovlačili. Sada se ostalih 6 upita **ne konstruiše** bez potvrđenog vlasništva. |
| **Poreklo konteksta je vidljivo korisniku (kompletna analiza)** | `static/vindex.js:3814-3827` — prikazuje da li je analiza rađena nad praćenim predmetom ili samo nad nalepljenim tekstom. `_ai_advisory` se do tada nije renderovao nigde. |
| **Rokovi se izvlače automatski, ne ručno** | `api.py:3549-3572` (durable outbox → `on_predmet_kreiran`), `routers/intake.py:431-437`, `:896-901`. |

## 1.2 Prestalo da važi / mora se preformulisati

| Stara tvrdnja | Šta je otkriveno |
|---|---|
| „Svako polje konteksta predmeta nosi oznaku **iz kog dokumenta** potiče" | Netačno. `source` je **tabela ili modul** (`"predmeti"`, `"services/risk_engine.py::calculate_procesni_rizik"`). Samo 2 od 16 polja (`relevant_documents`, `document_summaries`, `shared/case_context.py:606,619`) nose `dokument_id`. |
| „Prepoznavanje rokova **iz teksta dokumenata**" (uz `case_pipeline._step_ekstrakcija_rokova`) | Taj korak čita `predmeti.opis`, **ne dokumente** (`services/case_pipeline.py:310-312`). Rokove iz dokumenata izvlači drugi, deterministički mehanizam (`uploaded_doc/deadline_parser.py`). Dva mehanizma su bila spojena u jednu tvrdnju. |
| „Original dokumenta se čuva" (soft-delete `deleted_at`) | `deleted_at` postoji na `predmet_dokazi`, **ne na `predmet_dokumenti`**. Original opstaje zato što endpoint za brisanje dokumenta ne postoji (`shared/audit_immutable.py:68-71`), a ne zbog soft-delete mehanizma. Upload originala u Storage je best-effort. |
| „Sadržaj upita i odgovora ne upisuje se u evidenciju" (dokaz: `ai_fabric._audit`) | Dokaz je bio na putu **koji nijedan produkcioni poziv ne koristi** (0 od 85). Tvrdnja i dalje važi, ali dokaz mora biti drugi: `shared/ai_client.py:445-449` upisuje isključivo SHA-256 otiske. |
| „Nepromenljiva evidencija: SHA-256 lanac, **UNIQUE(prev_hash)**, triger" | Triger je dokazan. `UNIQUE(prev_hash)` je **parcijalan indeks** (`migrations/081...sql:33-35`, `WHERE seq > 32`) i **nijedan test ga ne izvršava nad bazom** — produkcija već ima poznat fork na `seq=31/32`. Deo o `UNIQUE(prev_hash)` se **izbacuje** iz javne tvrdnje. |
| „Sloj za rad sa više dobavljača AI modela" | Ograda i dalje važi **u punom obimu**, sada i brojčano: **0 produkcionih poziva kroz `ai_fabric`, 85 direktnih `chat.completions.create` u 62 fajla**. Jedina referenca van modula i testova je string `"ai_fabric_call"` u allowlisti. |

---

# 2. BLOKATOR 2 — STREAMING POREKLO: **POTVRĐENO — TOK NE NOSI POREKLO, ALI GA UI NE KORISTI**

Stvarna lokacija (stara `api.py:3128` više ne važi): **`api.py:3220` `@app.post("/api/pitanje/stream")`**,
generator `api.py:3300-3405`.

**Nalaz 1 — tok šalje samo tekst.** Jedina tri `yield`-a u telu su:
`api.py:3334` (`data: <tekst chunk>`), `:3352` (`data: [DONE]`), `:3353` (`data: [CREDITS:N]`).
Generator **ne poziva `normalizuj_rezultat`** i **ne emituje** `izvori`, `confidence`,
`confidence_detail`, `top_law` ni `top_article`. Objekat `rezultat` te podatke ima — oni se
jednostavno nikad ne serijalizuju.

**Nalaz 2 — frontend ne koristi streaming.** `static/vindex.js:7579`:
`var eps = { q: BASE_URL+'/api/pitanje', n:_nEndpoint, a: BASE_URL+'/api/analiza' };`
Pretraga za `pitanje/stream` u `static/` i u svim `.html` fajlovima daje **nula pogodaka**.
Klijent zove ne-streaming `/api/pitanje` i prima ceo JSON.

**Posledica za sajt:** nema aktivne štete danas. **Ali je to skrivena mina:** ko god sutra
prebaci ćaskanje na streaming radi boljeg osećaja brzine, **tiho gubi ceo prikaz izvora**, a
nijedan test to ne bi uhvatio. Ako sajt obeća „vidite odakle je odgovor", ta obaveza mora biti
zapisana i uz streaming endpoint.

---

# 3. BLOKATOR 3 — SADRŽAJ `izvori`: **ZATVOREN — POLJE JE POPUNJENO, PRIKAZANO, ALI PLITKO**

## 3.1 Šta tačno popunjava `izvori`

`app/services/retrieve.py:822-840` — `_build_izvori(matches)`:

```
izvori.append({"zakon": meta.get("law"), "clan": meta.get("article"),
                "score": round(float(m.score), 4)})
```

- Ulaz su **rerankovani Pinecone pogoci nad korpusom zakona**, ne dokumenti kancelarije.
- Najviše **5** stavki, deduplikovano po `zakon|clan`, stavka bez `zakon` se odbacuje.
- Sastavljeno u `retrieve.py:2212`, prosleđeno kroz `retrieval_meta`.

## 3.2 Pod kojim uslovima stiže do korisnika

| Grana | `izvori` u odgovoru | Dokaz |
|---|---|---|
| HIGH confidence | DA | `main.py:3613` |
| MEDIUM confidence | DA | `main.py:3504` |
| **LOW confidence** | **NE — ključ se uopšte ne vraća** | `main.py:3354-3362`, `:3375-3381` |
| Prazan retrieval | prazna lista | `app/services/retrieve.py:1823` |
| `/api/pitanje` | prosleđuje | `api.py:1438-1439` (`if rezultat.get("izvori")`) |
| `/api/analiza`, `/api/nacrt`, `/api/podnesak` | **NE** — drugi normalizator, bez `izvori` | `routers/drafting.py:202-227`, `:692` |
| `/api/pitanje/stream` | **NE** | v. §2 |

## 3.3 Da li objekat identifikuje DOKUMENT i LOKACIJU u njemu

**NE.** Identifikuje **naziv propisa i član** (`zakon`, `clan`). Ne nosi:
identifikator dokumenta, broj strane, offset u tekstu, ni URL ka propisu.

Dokumenti kancelarije koji su ušli u kontekst putuju odvojenim poljem `doc_passages`
(`retrieve.py:2221`), koje **nikad ne izlazi iz backend-a** — `normalizuj_rezultat` ga ne
prosleđuje. Isto važi za `match_breakdown` („zašto ti je ovaj izvor prikazan",
`retrieve.py:2225`): jedino mesto gde napušta proces je dijagnostički endpoint
`api.py:2915`, ne korisnički odgovor.

## 3.4 Da li frontend to prikazuje — **DA**

| Karika | Dokaz |
|---|---|
| DOM element | `index.html:4028` — `<div id="rag-source-info" class="vx-izvori" style="display:none;">` |
| Funkcija prikaza | `static/vindex.js:924-955` — `_vxRenderIzvori(d)`; resetuje se na svaki odgovor, iscrtava `<h3>Pravni izvori</h3>` + listu, i postavlja `el.style.display = ''` |
| Poziv | `static/vindex.js:7760` — posle obe grane iscrtavanja odgovora |
| Redosled | `_renderRagConfidence(d)` (`:7688`) skriva element, `_vxRenderIzvori(d)` (`:7760`) ga ponovo prikazuje kad ima šta. Sakrivač ide **pre** prikazivača — nema poništavanja. |
| CSS | `static/vindex.css:9636-9679` — potpuno stilizovano, **nigde `display:none`** |
| Pouzdanost | `static/vindex.js:6704-6712` — `VISOKA / SREDNJA / NISKA` u „hero" kartici na vrhu odgovora |

**Namerno izostavljeno, i to je pošteno:** `score` se ne prikazuje (`vindex.js:918-920`:
„broj pored citata sugeriše preciznost koju sistem ne meri"), i citat **nije klikabilan**
(`:922-923`: „deep-link ka propisu ne postoji u contractu, pa bi klikabilan citat obećavao
putanju koje nema").

## 3.5 Ishod za centralnu poruku sajta

Korisnik **danas vidi**, ispod odgovora, listu do pet stavki oblika
**„Zakon o radu · Član 179"**, i oznaku pouzdanosti **VISOKA/SREDNJA/NISKA**.

Ne vidi: link ka tekstu propisa · dokument iz svog spisa na kome odgovor počiva · lokaciju u
dokumentu · obrazloženje zašto je baš taj izvor izabran.

**Nijedan automatizovan test ne pokriva `_vxRenderIzvori`.** Dokaz je čitanje koda i CSS-a,
ne izvršavanje. Za snimak ekrana potrebna je jedna živa provera.

---

# 4. ODOBRENE TVRDNJE — `VERIFIED`

| Tvrdnja | Dokaz (fajl:linija) | Test | Status | Sme na sajt |
|---|---|---|---|---|
| „Ispod svakog pravnog odgovora Vindex navodi propise i članove na kojima odgovor počiva." | `app/services/retrieve.py:822-840`, `main.py:3504,3613`, `api.py:1438-1439`, `static/vindex.js:924-955`, `index.html:4028`, `static/vindex.css:9636` | UI deo nije pokriven testom; backend deo: `tests/test_celina1_praksa_rag_2026_07_24.py:45` | VERIFIED | DA — doslovno ovako, bez „klikom do izvora" |
| „Uz svaki odgovor stoji oznaka pouzdanosti pronađenih izvora — visoka, srednja ili niska." | `app/services/retrieve.py:2218`, `static/vindex.js:6692`, `:6704-6712` | `tests/test_celina1_praksa_rag_2026_07_24.py:45` | VERIFIED | DA |
| „Kada sistem nema pouzdan izvor, odbija da odgovori umesto da nagađa." | `main.py:3354-3362` (`_format_low_response`, bez LLM poziva), `main.py:3139-3149` | pokriveno RAG confidence testovima | VERIFIED | DA — ovo je najjača poštena tvrdnja koju proizvod ima |
| „Radnje u sistemu upisuju se u evidenciju koju ni administrator ne može naknadno izmeniti ni obrisati." | `migrations/043_security_bulletproof.sql:33-52` (`BEFORE UPDATE OR DELETE`, `SECURITY DEFINER`, `RAISE EXCEPTION`) | `tests/test_rc_migration_gate.py:399::test_G0_update_reda_audita_dize_izuzetak`, `:414::test_G0_delete_reda_audita_dize_izuzetak`, `:453::test_G0_trigger_je_stvarno_iz_migracije_043`, `:428` (negativna kontrola) | VERIFIED | DA — bez pominjanja `UNIQUE(prev_hash)` |
| „Zapisi u evidenciji su ulančani kriptografskim otiskom — izmena jednog zapisa raskida lanac." | `shared/audit_immutable.py:30` (`_GENESIS_HASH`), `:366-381`, `verify_chain_integrity` | `tests/test_celina5_secops_2026_07_24.py:300-304` (verifikacija lanca) | VERIFIED | DA |
| „Kada bezbednosna kapija oko AI-ja ne može da se podigne, AI poziv se ne izvršava — sistem se zatvara, ne propušta." | `shared/ai_client.py:131-177` (otrovna brana nad 4 `openai` konstruktora), `:640-644` | `tests/test_wave9_governance.py:138::test_c1_b_sinhroni_klijent_se_NE_MOZE_konstruisati`, `:155`, `:164`, `:181`, `:219` (pozitivna kontrola) | VERIFIED | DA |
| „Odgovor modela prolazi kroz izlaznu proveru pre nego što stigne do korisnika; greška u samoj proveri obara poziv." | `security/response_firewall.py`, poziv iz `shared/ai_client.py` | `tests/test_gov3_response_firewall.py:90::test_b_pokvaren_odgovor_NE_STIZE_do_pozivaoca`, `:141::test_e_greska_u_samoj_proveri_ZATVARA`, `:159` (negativna kontrola) | VERIFIED | DA |
| „Podaci jednog predmeta ne mogu ući u analizu drugog — provera vlasništva se izvršava pre nego što se ijedan upit nad podacima uopšte pošalje." | `shared/case_context.py:170-190` (upit nad `predmeti` sa `.eq("user_id", uid)` i rani izlaz) pre `gather`-a ostalih 6 upita na `:226` | `tests/test_wave11_context_isolation.py:206::test_tudji_predmet_ne_izvrsava_nijedan_upit_nad_podacima`, `:252::test_vlasnik_dobija_bajt_identican_rezultat`, `:332`, `:341`, `:350` (tri negativne kontrole) | VERIFIED | DA |
| „Svaka izmena ili brisanje zapisa proverava vlasništvo unutar same naredbe nad bazom, ne u odvojenoj proveri pre nje." | `routers/evidence.py:437-441` (`.eq("id", …).eq("user_id", uid)` unutar `update`) | `tests/test_v44_delete_dokaz_guard.py:126::test_4_owner_predicate_is_inside_the_update`, `:117` | VERIFIED | DA |
| „Prava unutar kancelarije razdvojena su po ulogama; radnja bez ovlašćenja se odbija." | `routers/kancelarija.py:84-88` (`_require_firma_admin` → HTTP 403), pozvano na 8 mesta | `tests/test_kancelarija_seats.py:143::test_pozovi_non_admin_gets_403` | VERIFIED | DA |
| „Za svaki AI poziv beleži se koji je model korišćen, koliko je trajao i pod kojim identifikatorom zahteva — bez ijednog per-poziv ožičenja." | `shared/ai_client.py:409-465` (`_capture_chat_provenance`), `:781-782` (patch na SDK klasama), `security/ai_forensics.py:207-311`, `migrations/043...sql:80` | `tests/test_mission_atlas_ai_provenance.py`, `tests/test_wave11_guard_and_provenance.py:164::test_g1_a_spijun_nad_analizatorom_je_STVARNO_pozvan` | VERIFIED | DA |
| „Tekst vašeg pitanja i tekst odgovora se ne upisuju u tu evidenciju — čuva se samo kriptografski otisak." | `shared/ai_client.py:445-449` (`sha256_text` za system/user/output), `shared/ai_fabric.py:645-654` | `tests/test_ai_fabric_governance.py:130::test_7_successful_call_writes_canonical_audit_without_content` (`assert "tajni prompt" not in blob`) | VERIFIED | DA |
| „Ubacivanje naloga u pitanje (prompt injection) blokira se pre nego što tekst napusti sistem — i pre naplate." | `api.py:3084-3088` (`/api/pitanje`), `api.py:3269-3291` (streaming) | `tests/test_wave11_guard_and_provenance.py:188::test_g1_b_blokiran_tekst_NE_STIZE_do_provajdera`, `:239::test_g1_c2_kad_analizatora_NEMA_poziv_je_ODBIJEN_a_ne_propusten` | VERIFIED | DA |
| „Unos više dokumenata odjednom, prepoznavanje teksta sa skeniranih dokumenata i automatska klasifikacija." | `routers/smart_intake.py:108` (batch, 202 + job_id), `:1280` (OCR), `shared/intake_classify.py` | `tests/test_omega_sprint001_batch_intake.py:72,107,132`; `tests/test_extractor_ocr.py:79,110,135,163`; `tests/test_intake_classify.py:15-92` | VERIFIED | DA — bez ijedne tvrdnje o **kvalitetu** OCR-a |
| „Semantička pretraga po sadržaju propisa, sudske prakse i mišljenja — ne po ključnoj reči." | `app/services/retrieve.py:891-960` (`_semanticka_pretraga`, `index.query`) | `tests/test_doc_retrieval.py:47,75,123` | VERIFIED | DA — **ne** vezivati za globalnu pretragu u aplikaciji (v. §7) |
| „Rokovi se iz dokumenata prepoznaju automatski pri unosu, bez posebne komande." | `shared/intake_extract.py:113` → `uploaded_doc/deadline_parser.py::ekstrahuj_rokove`; automatsko pokretanje: `api.py:3549-3572`, `routers/intake.py:431-437`, `:896-901` | `tests/test_deadline_parser.py`, `tests/test_intake_extract.py`, `tests/test_phase36_rokovi.py` | VERIFIED | DA — bez tvrdnje da nijedan rok neće promaći |
| „Vindex razlikuje analizu izgrađenu nad vašim praćenim predmetom od analize nad tekstom koji ste nalepili — i to vam kaže." | `routers/strategija.py:107-153` (`_advisory_provenance`), `static/vindex.js:3814-3827` | `tests/test_tau003_decision_boundary.py:45::test_all_9_strategija_endpoints_attach_ai_advisory_provenance`, `tests/test_rc_beta_flows.py:500,543,611,647` | VERIFIED | DA — uz napomenu da se prikazuje u kompletnoj analizi |
| „Testovi se izvršavaju nad svakom izmenom, na istoj verziji Pythona koju koristi produkcija." | `.github/workflows/tests.yml:2-8`, `:18-22` (matrica 3.11 + 3.13), `.github/workflows/production-runtime.yml` | ceo `tests/` direktorijum | VERIFIED | DA — **bez navođenja broja testova kao prodajnog argumenta** |
| „Više nezavisnih automatskih bezbednosnih provera pri svakoj izmeni koda." | `.github/workflows/security.yml` — gitleaks (`:73`), bandit (`:91`), pip-audit (`:126`), semgrep (`:139`) | isti workflow | VERIFIED | DA — **isključivo „unutrašnjih"**; nikad implicirati reviziju treće strane |
| „Model je komponenta koju platforma koristi, a ne sam proizvod." | `shared/ai_client.py:781-782` (kapija je vlasništvo platforme, ne pozivnog mesta), `security/response_firewall.py` | `tests/test_rc_cold_start.py` | VERIFIED | DA |

---

# 5. USLOVNE TVRDNJE — `PARTIALLY_VERIFIED`

Ograda u koloni „Sme na sajt" je **obavezna i doslovna**. Bez nje se tvrdnja ne koristi.

| Tvrdnja | Dokaz (fajl:linija) | Test | Status | Sme na sajt |
|---|---|---|---|---|
| „Svako polje konteksta predmeta nosi oznaku odakle potiče, ko ga računa i kada je osveženo." | `shared/case_context.py:102-112` (`context_field`), 16 poziva na `:511-625` | `tests/test_tau002_case_context.py:133::test_context_field_shape`, `tests/test_p0d_case_context_integrity.py:141::test_d_poreklo_je_razlucivo` | PARTIALLY_VERIFIED | DA, uz ogradu: **„oznaka pokazuje sistemski izvor podatka (tabelu ili modul koji ga računa), a ne pojedinačan dokument — osim za izvode iz dokumenata, koji nose i identifikator dokumenta"** |
| „Za svaki AI poziv beleži se i u okviru kog predmeta je pokrenut." | `shared/ai_client.py:456` (`predmet_id=ctx.get("predmet_id")`), `security/ai_forensics.py:227,284` | `tests/test_wave11_guard_and_provenance.py:603::test_g2_ng_svih_devet_naplatnih_poziva_nosi_predmet_id` | PARTIALLY_VERIFIED | DA, uz ogradu: **„vezivanje za predmet zavisi od proširenja šeme (migracija 089) — bez njega se upisuje uži skup polja"**. Ako proširenje nije potvrđeno na produkciji, tvrdnja se **izostavlja**. |
| „Original dokumenta se čuva." | `routers/evidence.py:438` (`deleted_at` na `predmet_dokazi`), `shared/audit_immutable.py:68-71` | `tests/test_intake_original_file_storage.py` | PARTIALLY_VERIFIED | DA, uz ogradu: **„dokumenti se ne brišu — u proizvodu ne postoji radnja brisanja dokumenta"**. Ne opisivati kao „soft-delete garanciju". |
| „Uočavanje protivrečnosti između dokumenata." | `routers/cross_doc.py:253,295`, `shared/gap_engine.py:151`, `shared/contradiction_identity.py` | `tests/test_cross_doc.py` (12), `tests/test_sprint6_phase3_cross_doc.py:89,158,202` | PARTIALLY_VERIFIED | DA, uz ogradu: **„mehanizam postoji; kvalitet nije meren nad stvarnim predmetima"** — `evaluation/phase_0_5/PHASE_0_5_DECISION.md` je i dalje `TEMPLATE — no data collected yet` |
| „Izrada nacrta podnesaka." | `routers/drafting.py:646,673,713` | `tests/test_phoenix_mission_010_drafting_rag_grounding.py` | PARTIALLY_VERIFIED | DA, uz ogradu: **„nacrt je polazna tačka, ne gotov podnesak"** |
| „Procena rizika predmeta." | `services/risk_engine.py::calculate_procesni_rizik`, `shared/case_context.py:600-605` | `tests/test_p0d_case_context_integrity.py` | PARTIALLY_VERIFIED | DA, uz ogradu: **„pomoć u proceni, ne pravni savet"** |
| „Svaki AI poziv prolazi kroz jednu kapiju." | `shared/ai_client.py:781-782` | `tests/test_rc_cold_start.py` (svih 8 SDK metoda nosi `_vindex_guarded`), `tests/test_gov2_runtime_interception.py` | PARTIALLY_VERIFIED | DA, uz ogradu: **„važi za tekstualne pozive modela; glasovni kanal i ponovno rangiranje rezultata su imenovani izuzeci koji ne prolaze kroz tu kapiju"** |
| „Sloj za rad sa više dobavljača AI modela." | `shared/ai_fabric.py:285-452` (adapteri), `_govern_request` | `tests/test_ai_fabric_governance.py` (15), `tests/test_ai_fabric_contract.py` | PARTIALLY_VERIFIED | Samo u „Vision", uz ogradu doslovno: **„implementirano; nijedna funkcija još ne ide kroz taj sloj"** (0 od 85 produkcionih poziva) |
| „Nepromenljiva evidencija se proverava automatski." | `tests/test_rc_migration_gate.py:386-465` | isti | PARTIALLY_VERIFIED | **NE koristiti reč „stalno"/„u CI-ju"**: `.github/workflows/tests.yml` nema PostgreSQL servis, pa se ti testovi u CI-ju **preskaču**; dokaz se izvršava lokalno. Bezbedna formulacija: „provereno izvršavanjem migracije nad pravom bazom podataka" |

---

# 6. `EXPERIMENTAL` — postoji, ali ne kao stabilna funkcija

| Tvrdnja | Dokaz (fajl:linija) | Test | Status | Sme na sajt |
|---|---|---|---|---|
| Glasovni rad sa predmetom | `services/voice_orchestrator.py`, `routers/voice_realtime.py:64-70,117-127` | `tests/test_wave9_voice_isolation.py` (11) | EXPERIMENTAL | **NE** — sam Wave 9 kaže „voice je van bete"; sadržaj razgovora ne prolazi izlaznu kapiju |
| Objašnjenje zašto je izvor izabran (`match_breakdown`) | `app/services/retrieve.py:843-870`, izlaz samo na dijagnostičkom `api.py:2915` | `tests/test_institutional_memory_v2.py:463,482` | EXPERIMENTAL | **NE** — nikad ne stiže do korisnika |
| Poreklo po polju u dnevnom brifingu (`_ai_provenance`) | `routers/case_intelligence.py:528-535` | — | EXPERIMENTAL | **NE** — nije renderovano nigde u frontendu (0 pogodaka u `static/vindex.js` i `index.html`) |
| Simulacija suđenja / „AI Sudija" / „Red Team" | `routers/strategija.py:270-540` | `tests/test_tau003_decision_boundary.py` | EXPERIMENTAL | Samo kao **„alati za preispitivanje sopstvenog predmeta"**. Nikad kao predviđanje ishoda ni verovatnoća. |

---

# 7. `ROADMAP` — samo u „Vision" sekciji, nikad kao postojeća funkcija

| Tvrdnja | Dokaz (fajl:linija) | Test | Status | Sme na sajt |
|---|---|---|---|---|
| Rad sa više dobavljača AI modela u produkciji | `shared/ai_fabric.py` postoji, **0 pozivalaca** | `tests/test_ai_fabric_governance.py` | ROADMAP | Samo „Vision", uz ogradu iz §5 |
| Klik iz citata do teksta propisa | ne postoji — `static/vindex.js:922-923` izričito objašnjava zašto | — | ROADMAP | Samo „Vision" |
| Korisnički ekran nepromenljive evidencije | ne postoji nijedan endpoint ni ekran | — | ROADMAP | Samo „Vision"; na sajtu se objašnjava **dijagramom, ne snimkom ekrana** |
| Samouslužna kupovina pretplate | `static/vindex.js:124` — `var STRIPE_URL = '';` | — | ROADMAP | **NE** — v. §9 |
| Objašnjenje zašto je baš taj izvor izabran, korisniku | `match_breakdown` postoji, ne izlazi | `tests/test_institutional_memory_v2.py:463` | ROADMAP | Samo „Vision" |

---

# 8. `UNVERIFIED` / `FALSE` — ne pojavljuju se nigde

| Tvrdnja | Dokaz (fajl:linija) | Test | Status | Sme na sajt |
|---|---|---|---|---|
| „Vindex zna iz kog dokumenta i sa koje strane potiče odgovor" | `_build_izvori` nosi samo `zakon`/`clan`; `doc_passages` nikad ne izlazi (`api.py:1418-1446`) | — | FALSE | NE |
| „Klikom stižete do izvora" | `static/vindex.js:922-923`, `.vx-izvori` nema hover ni kursor | — | FALSE | NE |
| „Koristimo GPT, Claude i Gemini" | `requirements.txt` sadrži samo `openai==2.29.0`; `anthropic`/`google-generativeai` nisu zavisnosti | `tests/test_wave9_provider_isolation.py:101::test_a_izmereno_paket_nije_produkcijska_zavisnost` | FALSE | NE |
| „Automatski bira najbolji model" / „unakrsna provera između modela" | ruter postoji u `ai_fabric`, 0 produkcionih pozivalaca | — | FALSE | NE |
| „Vindex ima sopstveni AI model" | nijedan trening ni model artefakt u repou | — | FALSE | NE |
| „Nikad više propuštenih rokova" | garancija ishoda; recall ekstrakcije nikad meren | — | FALSE | NE |
| „Simulacija sudskog postupka i verovatnoće ishoda" | nijedna tačnost izmerena; `routers/strategija.py:136-138` sam kaže „subjektivna GPT procena, ne izračunata statistika" | — | FALSE | NE |
| Bilo koji procenat tačnosti AI-ja | nijedno merenje ne postoji; `evaluation/phase_0_5/outputs/` je prazan | — | UNVERIFIED | NE |
| „Štedi X sati / X% vremena" | nema merenja | — | UNVERIFIED | NE |
| Bilo šta o brzini, latenciji ili kvalitetu OCR-a | `shared/intake_accuracy.py` računa `ocr_uspesnost`, ali nijedan objavljen rezultat ne postoji | — | UNVERIFIED | NE |
| „GDPR usklađeni" / „sertifikovani" | mehanizmi postoje, nezavisne potvrde nema | — | UNVERIFIED | NE |
| „Vaši podaci se ne koriste za treniranje" | zavisi od ugovora sa dobavljačem — nije provereno u repou | — | UNVERIFIED | NE |
| „Potpuno bezbedno" / „100% sigurno" | neodrživo po definiciji | — | FALSE | NE |
| „Eliminiše ljudsku grešku" | suprotno pozicioniranju proizvoda | — | FALSE | NE |
| Korisnici, klijenti, partneri, preporuke, logotipi | ne postoje | — | FALSE | NE |
| Cena, plan, „15 upita besplatno" kao trajna ponuda | `static/vindex.js:124` `STRIPE_URL=''`; `api.py:356` `BESPLATNI_KREDITI = 15` se dodeljuje **jednom** i nema obnove | — | UNVERIFIED | NE — v. §9 |
| „Analiza iskaza svedoka i procena verodostojnosti" | `routers/strategija.py:496`; nijedna validacija | — | UNVERIFIED | NE (i dalje stoji na `landing.html:948`) |
| Kontakt i pravni identitet firme (PIB, matični broj, adresa) | nema ih ni u `landing.html`, ni u `terms.html`, ni u `privacy.html` | — | UNVERIFIED | NE dok se ne utvrde |

---

# 9. ŠTA MORAMO POŠTENO REĆI DA NE RADIMO

Ovo su stvari koje korisnik **razumno pretpostavlja da rade**, a ne rade. Sajt mora imati
odgovor na svaku — u „Vision" sekciji, u FAQ-u ili kao ogradu uz odgovarajuću tvrdnju.

### Poreklo odgovora
1. **Citat nije klikabilan.** Nema linka ka tekstu propisa. Vidite „Zakon o radu · Član 179",
   ali do samog člana morate sami.
2. **Izvor ne pokazuje na vaš dokument.** Kada odgovor koristi dokumente iz vašeg spisa, ti
   dokumenti se **ne pojavljuju** u listi izvora. Lista pokriva isključivo propise i praksu.
3. **Nema lokacije u dokumentu** — ni strane, ni pasusa, ni citiranog isečka sa pozicijom.
4. **Izvori se prikazuju samo kod pravnog istraživanja.** Analiza dokumenata (`/api/analiza`)
   i izrada nacrta (`/api/nacrt`, `/api/podnesak`) **ne vraćaju listu izvora**.
5. **Kada je pouzdanost niska, izvora nema uopšte** — sistem odbija odgovor. To je namerno,
   ali korisnik to mora znati unapred da ne bi mislio da je nešto otkazalo.
6. **Nema objašnjenja zašto je baš taj izvor izabran.** Mehanizam postoji u backend-u i ne
   izlazi iz njega.

### Evidencija i kontrola
7. **Ne postoji ekran nepromenljive evidencije.** Mehanizam je dokazan, korisnički prikaz ne
   postoji. Na sajtu se objašnjava dijagramom — **snimak nepostojećeg ekrana se ne pravi ni
   kao „ilustracija"**.
8. **Poreklo po polju u dnevnom brifingu se ne prikazuje** iako ga backend računa.
9. **Ne postoji radnja brisanja dokumenta.** To je danas i razlog zašto se original čuva.

### AI i njegove granice
10. **Nijedan broj koji AI vrati nije izračunata statistika.** Procenat uspeha, procena
    verodostojnosti iskaza, verovatnoća ishoda — sve su subjektivne procene modela. Sam kod
    to kaže korisniku (`routers/strategija.py:136-138`), i sajt to ne sme ublažiti.
11. **Tačnost nije merena ni za jednu funkciju.** Okvir za merenje postoji od 2026-07-23 i
    nikad nije pokrenut (`evaluation/phase_0_5/PHASE_0_5_DECISION.md`: „TEMPLATE — no data
    collected yet").
12. **Jedan dobavljač modela, ne tri.** Višedobavljački sloj je napisan i testiran, ali nijedan
    produkcioni poziv ne ide kroz njega.
13. **Glasovni kanal ne prolazi kroz izlaznu bezbednosnu proveru** i nije deo bete.

### Proizvod i komercijala
14. **Pretplata se ne može kupiti u proizvodu.** `STRIPE_URL` je prazan; tarifa se menja
    ručnim zahvatom nad bazom.
15. **15 besplatnih upita se dodeljuje jednom i ne obnavlja se.** Nema mesečnog resetovanja.
16. **Nema nijednog korisnika, klijenta ni pilota** čije se iskustvo sme prikazati.
17. **Pravni identitet firme nije zapisan nigde u repozitorijumu**, a kontakt adrese na
    postojećim javnim stranama koriste domen `vindex.ai` dok se produkcija vrti na `vindex.rs`.
    Pre objave ovo mora biti usaglašeno.

---

# 10. ZABRANJENE FORMULACIJE

Nasleđene iz `VINDEX_AI_PUBLIC_CLAIMS.md` i proširene nalazima ove re-verifikacije.

| Zabranjeno | Zašto |
|---|---|
| bilo koji procenat tačnosti AI-ja | nikad izmeren; okvir za merenje je prazan šablon |
| „štedi X sati" / „X% brže" | nema merenja |
| „koristimo GPT, Claude i Gemini" | produkcija koristi **jednog** dobavljača; ostali SDK-ovi nisu ni instalirani |
| „automatski bira najbolji model" | nije u upotrebi (0 od 85 poziva) |
| „unakrsna provera između modela" | postoji samo ugovor, bez izvršavanja |
| „Vindex ima sopstveni AI model" | netačno |
| „GDPR usklađeni" / „sertifikovani" / „revidirano" | mehanizmi postoje, nezavisne potvrde nema |
| „potpuno bezbedno" / „100% sigurno" / „neprobojno" | neodrživo |
| „vaši podaci se ne koriste za treniranje" | zavisi od ugovora sa dobavljačem — neprovereno |
| „eliminiše ljudsku grešku" | suprotno pozicioniranju |
| „nikad više propuštenih rokova" | garancija ishoda |
| „verovatnoća ishoda" / „predviđa presudu" / „simulira sud" | nijedna tačnost izmerena; kod sam to naziva subjektivnom procenom |
| „procena verodostojnosti iskaza" | nikad validirano |
| korisnici, klijenti, partneri, preporuke, logotipi | ne postoje |
| bilo šta o kvalitetu OCR-a | nije mereno nad stvarnim dokumentima |
| bilo šta o brzini / latenciji | nije mereno |
| pominjanje cene ili plana | ne postoji način da se plati; više neusaglašenih varijanti |
| **„kliknite do izvora" / „izvor na jedan klik"** | **NOVO** — citat nije klikabilan i deep-link ne postoji |
| **„vidite iz kog dokumenta i sa koje strane"** | **NOVO** — `izvori` nosi samo naziv propisa i član |
| **„svaki odgovor navodi izvore"** | **NOVO** — ne važi za analizu dokumenata i nacrte, ni za niske pouzdanosti |
| **„pravni operativni sistem" / „operativni sistem"** | ništa se ne pokreće na Vindexu; kategorija je neodrživa |
| **„počni besplatno" kao samouslužni tok** | proizvod je pre-beta; preporučeni CTA je zatvoreno testiranje |
| **„svi testovi prolaze" / „zelena bezbednosna provera"** | scan tajni je namerno crven zbog ključa iz prvog commita; PostgreSQL testovi se u CI-ju preskaču |
| **„revizorski trag koji možete pregledati"** | korisnički ekran evidencije ne postoji |

---

# 11. ZAKLJUČAK — DA LI „VINDEX ZNA ODAKLE ZNA" STOJI

**Stoji, ali uže nego što je poruka do sada podrazumevala.**

Ono što je dokazivo danas, u ovom redosledu snage:

1. **Kad ne zna, kaže da ne zna** — i ne poziva model. (`main.py:3354-3362`) To je najjača
   i najređa tvrdnja u kategoriji, i najmanje se koristi.
2. **Uz svaki pravni odgovor stoje propisi i članovi na kojima počiva, i oznaka pouzdanosti** —
   i korisnik ih zaista vidi. (`static/vindex.js:924-955`, `:6704-6712`)
3. **Svaki AI poziv ostavlja trag koji se ne može izbrisati, bez čuvanja sadržaja.**
4. **Kad kapija oko AI-ja ne radi, AI se ne izvršava.**
5. **Predmet A ne ulazi u predmet B — provereno pre nego što ijedan upit ode u bazu.**

Ono što **nije** dokazivo: da korisnik može da dođe **do dokumenta i mesta u njemu**.

**Preporučena formulacija centralne poruke** (svaka reč ima dokaz iznad):

> **Vindex vam kaže na kojim propisima počiva svaki odgovor — i odbija da odgovori kada
> pouzdan izvor ne postoji.**

Alternativa ako je potreban kraći oblik:

> **Odgovor sa navedenim propisom. Ili nikakav odgovor.**

Formulacija „Vindex zna odakle zna" sme da ostane kao **naslovna ideja**, pod uslovom da je
prva rečenica ispod nje jedna od dve gornje. Sama, bez toga, ona obećava putanju do dokumenta
koja ne postoji.
