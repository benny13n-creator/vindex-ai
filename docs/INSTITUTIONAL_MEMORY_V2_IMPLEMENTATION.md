# Vindex AI — Institutional Memory Architecture V2 (2026-07-26)

**Status:** Implementirano i testirano (pytest izveštaj na kraju). Migracija
088 (`staging_memory`) čeka founderovo ručno pokretanje u Supabase SQL
Editor-u (standardna konvencija ove sesije — v. `[[feedback_migrations]]`).

Ovaj dokument opisuje 5 stubova iz master prompt-a, TAČNO šta je
implementirano, i **gde su napravljeni pošteni, dokumentovani kompromisi**
umesto da se nešto forsira da "izgleda" gotovo kad nije.

---

## STUB 1 — Quality Gate & Staging Memory

**Problem koji se rešava:** raniji tok (Institutional Learning & RAG Audit,
2026-07-25) je AI-generisan nacrt indeksirao DIREKTNO u produkcioni
`kancelarija_{id}` namespace čim je `predmet_id` prosleđen — bez ikakve
ljudske provere. To je tačno "toksično učenje" rizik: AI koji uči (i
buduće nacrte bazira) na sopstvenim, neproverenim, potencijalno pogrešnim
ranijim nacrtima.

**Implementacija:**
- `migrations/088_staging_memory.sql` — nova tabela `staging_memory`
  (user_id, kancelarija_id, predmet_id, tip, naziv, tekst,
  confidence_score, quality_detail jsonb, is_lawyer_approved,
  approved_by/approved_at, status, pinecone_indexed). RLS: korisnik vidi
  samo svoje, service_role neograničeno.
- `services/quality_gate.py` — `evaluate_draft_quality(tekst, tip)`:
  - **Validnost citata**: NIJE puna LRE (`services/legal_reasoning_engine.py`)
    integracija — LRE je case/genome-specifičan reasoning-graph generator
    (zahteva `predmet_id` + facts + genome), ne generički "proveri citate u
    proizvoljnom tekstu" alat. Umesto forsiranog nefit-a, ponovo su
    iskorišćeni već postojeći, dokazani helperi iz `app/services/
    retrieve.py` (`_direktan_fetch_clana`) da se svaki "Član N"/"čl. N"
    citat proveri protiv stvarno indeksiranog zakonskog korpusa. Ovo je
    **poštena, lakša provera** (stvarno postoji u bazi, ne halucinacija),
    transparentno nazvana `citation_score`, ne predstavljena kao nešto šire.
  - **Formalna kompletnost**: heuristika ključnih reči (sud, stranke,
    pravni osnov) — dokumentovano kao takva, ne kao NLP klasifikator.
  - `confidence_score = 0.6 × citation_score + 0.4 × completeness_score`.
- `routers/drafting.py`:
  - `_index_finalized_draft` (stara, direktna) **UKLONJENA**, zamenjena
    `_stage_draft_for_review` — piše SAMO u `staging_memory`, nikad ne
    dodiruje Pinecone.
  - `POST /api/staging/{id}/approve` — advokat eksplicitno odobrava.
    `is_lawyer_approved=True` je **NUŽAN, ali NE DOVOLJAN** uslov — Pinecone
    promocija se dešava SAMO ako je i `confidence_score >= 0.85`. Ako je
    odobreno ali skor nizak, endpoint to jasno vraća korisniku
    (`indexed: false` + objašnjenje), ne tiho ćuti.
  - `POST /api/staging/{id}/reject` — trajno odbija, nikad ne indeksira.
  - `GET /api/staging/predmet/{id}` — lista nacrta na čekanju za predmet.

---

## STUB 2 — Origin & Lineage

- `shared/vector_origin.py` — kanonske konstante: `ORIGIN_LAW`,
  `ORIGIN_COURT`, `ORIGIN_LAWYER_VERIFIED`, `ORIGIN_CLIENT_DOC`,
  `ORIGIN_AI_GENERATED`, sa tačnim težinama iz specifikacije (1.0/1.0/0.95/
  0.80/0.00).
- **Poštena napomena o obimu**: `origin` metadata polje je dodato na SVE
  NOVE vektore idući napred (`api.py` upload, `routers/smart_intake.py`,
  `routers/dokument.py` ad-hoc analiza, `routers/drafting.py` promovisani
  nacrti). **Postojeći statični zakonski/praksa korpus (milioni već
  indeksiranih vektora u `_ZAKONI_NS`/`_PRAKSA_NS`) NIJE retroaktivno
  re-embed-ovan** — to bi bio veliki, skup, zaseban poduhvat koji zahteva
  eksplicitnu founderovu odluku (cena/vreme), van dometa ove sesije.
  Umesto toga, origin težina za taj korpus se primenjuje **strukturno u
  `retrieve.py`** (matches iz `_ZAKONI_NS` odnosno `_PRAKSA_NS` se tretiraju
  kao LAW/COURT po tome KOJI namespace ih je vratio, ne po metadata polju
  koje ti stari vektori nemaju) — isti efekat, bez potrebe za re-ingest-om.
- `parent_id` + `origin_chain`: kad se staging nacrt promoviše u Pinecone
  (`routers/drafting.py::_promote_staged_draft_to_pinecone`), `parent_id`
  = `staging_memory.id`, `origin_chain = ["AI_GENERATED", "LAWYER_VERIFIED"]`
  — čuva trag da je tekst NASTAO kao AI generisan pre nego što je postao
  ljudski-overen, čime se sprečava da se u budućnosti tretira kao "izvorni
  advokatski rad od nule" (anti AI-to-AI degeneracija).
- **Defense-in-depth u `retrieve.py`**: čak i ako bi `AI_GENERATED`-origin
  vektor greškom dospeo u `kancelarija_{id}` namespace (staging gate to
  sprečava na ingest strani), retrieval ga EKSPLICITNO isključuje iz
  rezultata (ne samo nizak skor — potpuno izbačen). Testirano
  (`test_ai_generated_origin_never_surfaces_even_if_present`).

---

## STUB 3 — Memory Decay & Temporal Validity

- Svaki novi vektor (case_doc/draft_final) nosi `created_at` (ISO),
  `golden_template` (bool), i opciono `valid_until`/`status`.
- `valid_from_law_version` polje **postoji u shemi** (spremno za upis) ali
  **se aktivno ne popunjava niti proverava** u ovoj implementaciji — to bi
  zahtevalo poseban "zakon-verzija" registar (praćenje kada je svaki zakon
  poslednji put menjan) koji danas ne postoji nigde u kodu. Dodavanje
  praznog/neaktivnog polja bez tog registra bi bilo kozmetičko, ne funkcionalno
  — zato je ovde jasno označeno kao OTVORENO, ne lažno predstavljeno kao rešeno.
- `shared/vector_origin.py::freshness_weight()` — Final Score formula:
  ```
  Final Score = Vector Similarity × Freshness Weight × Origin Weight
  ```
  - LAW/COURT: freshness uvek 1.0 (zakon ne "zastareva" po starosti u ovom
    modelu, samo eksplicitnim ukidanjem — v. DEPRECATED ispod).
  - `golden_template=True`: uvek 1.0, bez obzira na starost.
  - `status="DEPRECATED"` ili prošao `valid_until`: teška kazna (0.1) —
    dokument može i dalje da se pojavi (nikad hard-exclude), ali gotovo
    nikad ne pobeđuje nešto važeće.
  - CLIENT_DOC/LAWYER_VERIFIED stariji od 3 godine: linearni decay od 1.0
    (na 3g.) do poda 0.5 (na 10+ g.) — nikad ne ide na 0, stariji dokument
    i dalje MOŽE biti jedini relevantan izvor.
- Testirano: `test_deprecated_document_ranks_below_fresh_valid_one` —
  dva matcha sa IDENTIČNIM sirovim Pinecone skorom, jedan DEPRECATED, jedan
  svež — svež pobeđuje, dokazuje da decay stvarno menja rangiranje, ne samo
  metapodatke.

---

## STUB 4 — Explainable Retrieval

- `app/services/retrieve.py::_build_match_breakdown()` — nova funkcija,
  vraćena u `retrieval_meta["match_breakdown"]` (lista, jedan unos po
  izvoru — zakon/praksa/kancelarija pasus):
  - `matched_by_law_article` — npr. `"ZOO — Član 172"` za zakon, ili
    `article_label` za kancelarijski pasus, `None` za praksu.
  - `matched_by_fact_pattern` — procenat, aproksimiran iz vektor-sličnosti
    skora (`round(score * 100, 1)`). **Poštena napomena**: ovo NIJE
    zaseban "fact pattern matching" model — pipeline danas nema odvojen
    signal za "poklapanje činjenica" nasuprot "poklapanje teksta uopšte",
    pa se koristi najbliža postojeća proxy-vrednost, jasno tako
    dokumentovana u kodu.
  - `matched_by_court` — naziv suda za praksa izvore.
  - `origin_label` — čitljiv srpski naziv porekla (v. `vector_origin.py`).
- `app/services/doc_formatter.py::ORIGIN_HIERARCHY_INSTRUCTIONS` — tekst
  hijerarhije (PRIMAT 1 zakon → PRIMAT 2 praksa → PRIMAT 3 kancelarijsko
  iskustvo, samo stilski/stručni izvor) — automatski se ubacuje na POČETAK
  `docs` konteksta SAMO kad su stvarno prisutni kancelarijski pasusi (nema
  svrhe kad je kontekst čist zakon/praksa).

---

## STUB 5 — Refaktorisanje i Testiranje

- `routers/drafting.py`, `routers/dokument.py`, `app/services/retrieve.py`
  ažurirani (v. gore). `routers/smart_intake.py` i `api.py` (upload
  endpoint) takođe ažurirani sa istim origin/lineage/decay metadata poljima
  (bili su deo prethodne implementacije, sad prošireni).
- `tests/test_institutional_memory_v2.py` — **21 nov test**:
  - Quality Gate: verifikovan/neverifikovan citat menja `confidence_score`,
    formalna kompletnost, neutralnost kad nema citata.
  - `vector_origin.py`: težine tačno po specifikaciji, LAW/COURT bez
    decay-a, golden template izuzetak, DEPRECATED/`valid_until` kazna.
  - **Staging gate**: generisanje nacrta NIKAD ne poziva `ingest_session`
    (samo `staging_memory` insert) — glavni regresioni test za STUB 1.
  - **Approval gate**: odobren nacrt sa `confidence_score >= 0.85` dobija
    `origin=LAWYER_VERIFIED` + `parent_id`/`origin_chain` lineage i biva
    indeksiran; odobrenje SA niskim skorom NE promoviše (testirano preko
    stvarnog HTTP endpointa, `TestClient`); odbijanje nikad ne dodiruje
    Pinecone.
  - **Time-decay ranking**: DEPRECATED dokument gubi od svežeg validnog
    uprkos identičnom sirovom skoru; AI_GENERATED poreklo se potpuno
    isključuje iz retrievala i kad bi greškom dospelo tamo (defense in
    depth).
  - **Match breakdown**: prisutan u svakom odgovoru, ispravno oblikovan po
    tipu izvora.
- Pun pytest suite pokrenut posle svih izmena — rezultat u nastavku.

---

## Otvoreno / Poznati kompromisi (transparentno, ne skriveno)

1. **Postojeći zakon/praksa korpus nije re-embed-ovan** sa `origin`
   metadata poljem — origin težina se primenjuje strukturno po namespace-u
   u `retrieve.py`, funkcionalno ekvivalentno, ali vredi znati da vektori u
   `_ZAKONI_NS`/`_PRAKSA_NS` sami po sebi nemaju `origin` polje upisano.
2. **`valid_from_law_version` nije aktivno iskorišćen** — polje postoji u
   shemi, ali bez "zakon-verzija" registra (poseban poduhvat) ne postoji
   šta da se uporedi. Nije lažno predstavljeno kao rešeno.
3. **Citation validity u Quality Gate-u je "postoji u bazi" provera**, ne
   duboka LRE pravna analiza — namerna, dokumentovana odluka (v. STUB 1).
4. **`matched_by_fact_pattern` je aproksimacija** preko vektor-skora, ne
   zaseban model — dokumentovano u kodu i ovde.
5. **Migracija 088 čeka ručno pokretanje** — dok se ne pokrene,
   `staging_memory` tabela ne postoji u produkciji, pa će
   `_stage_draft_for_review` neuspešno (ali bezbedno, non-fatal, logovano)
   pokušati insert. Preporuka: pokrenuti migraciju PRE prvog korišćenja
   `/api/nacrt` ili `/api/podnesak` sa `predmet_id` poljem.
