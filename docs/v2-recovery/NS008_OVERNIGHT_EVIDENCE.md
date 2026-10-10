# NS008 — LAW BRAIN / INSTITUTIONAL INTELLIGENCE — OVERNIGHT EVIDENCE

Branch: `feature/vindex-v2-ns008-law-brain` (stacked on NS007 `deac5d99`).
Verified at start: main `99d2c6b9`, NS006 `dac1f6dd`, NS007 `deac5d99` — all match the directive.

Note: the pasted directive was truncated inside Task 32 ("serve deleted knowledge").
The rest of Task 32's checklist and the final report format were not received; the
NS006/NS007 report pattern is used for the final report.

Legend: **PROVEN** = read in code/schema at the cited line, or measured;
**INFERRED** = follows from proven facts but not executed; **UNKNOWN** = not provable from repo.

---

## TASK 0 — LAW BRAIN FORENSIC CENSUS (no product code)

### A. SOURCE-OF-TRUTH MATRIX

| Concept | Current owner (table) | Writer of record | Truth quality | Verdict |
|---|---|---|---|---|
| Matter outcome | `outcome_log` (037; `predmet_id UNIQUE`, `ishod CHECK pobeda/poraz/nagodba/odustajanje`, RLS own) | `POST /api/learning/outcome` (`routers/learning.py:127`) — lawyer-submitted, ownership via `_dohvati_predmet(.eq user_id)` | Human, one row per matter (PROVEN: UNIQUE + upsert `on_conflict=predmet_id`) | **Canonical outcome owner.** Only human source. |
| Matter outcome (shadow) | chronology text `predmet_hronologija.dogadjaj` "Ishod: …" + `predmeti.status` | many | Keyword inference (`routers/outcome_intel.py:95-137`) | **NOT truth.** Must never feed Law Brain. |
| Matter outcome (shadow 2) | `memory_graph_edges.ishod` (047) | `POST /api/memory-graph/dodaj-vezu` | Free text, no CHECK, not tied to `outcome_log` | NOT outcome truth; relation annotation only. |
| Matter terminal state | `predmeti.status` ∈ `TERMINALNI_STATUSI_PREDMETA = (zatvoren, arhiviran, odbijen)` (`shared/constants.py:28`) | `routers/predmeti_close.py` (2 writers, emit `MATTER_BECAME_TERMINAL`), `routers/learning.py:264` (no event), `api.py:5068` generic PATCH allows `status` (no event) | Correct field, incomplete event coverage | Owner = `predmeti`; event emission gap → Task 3. |
| Lawyer-verified work product | `staging_memory` (088) → Pinecone `kancelarija_{id}`/`user_{id}` with `origin=LAWYER_VERIFIED`, `origin_chain=[AI_GENERATED, LAWYER_VERIFIED]` + `predmet_dokumenti` row | `routers/drafting.py:289` (stage), `:1283` approve (atomic `pending→approved` claim), `:323` promote (only if `confidence_score ≥ 0.85`) | Human approval explicit (`is_lawyer_approved`, `approved_by`, `approved_at`) | **Canonical artifact owner.** `approved` ≠ indexed (`pinecone_indexed` separate). |
| Lessons | `lessons_learned` (038 + 039 `status_lekcije` predlog_ai/usvojena_praksa/odbijena/zastarela, `potvrdio`, `potvrdjeno_at`) | GPT `learning_engine.generate_lessons_learned` → `save_lessons` (`services/learning_engine.py:537`), human gate `PATCH /api/learning/lessons/{id}/potvrdi` (`routers/learning.py:1075`) | Default AI (`predlog_ai`); human confirmation exists | Owner OK; trust must be read from `status_lekcije`, legacy NULL → UNKNOWN_LEGACY. |
| Office memory notes | `memory_entries` (046 + 047 `confidence`, `izvor manual/auto/korekcija/benchmark`, `potvrde_count`, `potvrdjeno_od`, `expires_at`, `zastarela`) | `POST /api/firma-memorija/dodaj` (only live writer; always `izvor` default `manual`) | Human-authored statement (not verified fact) | HUMAN_MEMORY_NOTE; `izvor != manual` → not human. |
| Explicit relations | `memory_graph_edges` (047) | `POST /api/memory-graph/dodaj-vezu` (`routers/memory_graph.py:82`, CONF-011 predmet ownership) | Human-asserted edge, no causation | EXPLICIT_GRAPH_RELATION. |
| Judge / client / partner profiles | `judge_patterns`, `client_memory`, `partner_profiles` (046) | `routers/firm_memory.py:449/548` (human), partner profiles via style/corrections | Human-entered / derived | Out of Law Brain core tonight; office-scoped. |
| Corrections | `ai_corrections` (045, RLS owner-only) → `firm_style_profile` (office) | `POST /api/corrections/capture` (`routers/corrections.py:232`) | Human correction of AI text; classification by model | HUMAN_CORRECTION (raw row per user). |
| Firm DNA / patterns | `firm_dna` (038/039), `case_patterns` (037) | `learning_engine.extract_firm_dna` (GPT), outcome endpoint counter | AI-extracted / counters | AI_CANDIDATE (firm_dna); case_patterns = counters over human outcomes but non-idempotent (see G). |
| Professional Genome | `predmeti.case_dna` | Genome pipeline (GPT) | AI analysis | AI_WORK_PRODUCT; never outcome/lesson truth. |
| NS007 autonomous products | `autonomy_work_items.rezultat` (136, not applied) | `services/autonomy.py:161` | AI; ACCEPTED = reviewer found useful for this matter | AI_WORK_PRODUCT even when ACCEPTED. |
| Law / case law authority | Pinecone `zakoni_rs`/praksa namespaces, `ORIGIN_LAW`/`ORIGIN_COURT` | ingest | Authority | Separate from office experience — Law Brain is NOT legal authority. |

### B. WRITER MATRIX (Law-Brain-relevant)

| Table | Writers (file:line) | Ownership check | Idempotency | Notes |
|---|---|---|---|---|
| `outcome_log` | `routers/learning.py:153` upsert | `_dohvati_predmet` `.eq(user_id)` (PROVEN :110) | upsert on `predmet_id` (logical) | Second writer `services/learning_engine.py:97 log_outcome` has **0 callers** (PROVEN grep) and maps invalid ishod → `u_toku`, which violates CHECK → would fail silently. Dead code. |
| `case_patterns` | `routers/learning.py:186-220` | uid-scoped | **NOT idempotent** — replaying `/outcome` increments counters again (PROVEN: read-then-update +1 per call) | Toxic counter (G2). |
| `predmeti.status` → terminal | `predmeti_close.py:118`, `:395` (emit event); `learning.py:264` (no event); `api.py:5068` PATCH `status` allowed (no event) | owner | guarded `.neq(status)` in close/learning | Task 3 gap confirmed in code. |
| `lessons_learned` | `learning_engine.py:553` insert (GPT output, `status_lekcije` from dict default `predlog_ai`); `learning.py:1140` confirm/reject; `learning_engine.py:892` decay auto-stale | owner | none (insert per call → duplicates on regenerate) | `POST /predmeti/{id}/lessons` regenerates → duplicate candidate lessons. |
| `memory_entries` | `firm_memory.py:197` insert; `:110` **GET-side UPDATE** (`_apply_trust` marks `zastarela` on read); `:659` soft delete; `:760` confirm | predmet/klijent entity ownership (CONF-011); delete/confirm scoped to office only | none | Any office member can deactivate a colleague's note (office-scoped DELETE). GET mutates state. |
| `memory_graph_edges` | `memory_graph.py:114` | predmet ownership if `predmet_id` given | none | free-text `ishod`. |
| `staging_memory` | `drafting.py:289` stage; `:1318` approve claim; `:1349` indexed flag; `:1377` reject | owner (`user_id`) | approve is atomic `status=pending` claim | **reject has no status guard**: an approved+indexed row can be set `rejected` while its Pinecone vector + `predmet_dokumenti` row remain (revocation gap → Task 21). |
| `ai_corrections` | `corrections.py:288` | predmet ownership | none | raw texts are per-user rows. |
| `autonomy_work_items` | `services/autonomy.py` | service, per user | NS007 claim/lease | ACCEPTED is not promotion. |

### C. READER MATRIX

| Reader | Reads | GPT | Credit | Problems |
|---|---|---|---|---|
| `GET /api/precedenti/predmeti/{id}` (`routers/precedenti.py:47`) | own `predmeti` same `tip` / `oblast`, `predmet_istorija`, `predmet_hronologija` | yes (gpt-4o-mini) | yes | Closed-status query `q` built at :73 and **never used** → "similar closed matters" include ACTIVE matters; hronologija read :109 without `user_id` filter (ids come from own matters, so INFERRED not a leak); N+1 queries; system prompt asks GPT to estimate "koliko sličnih predmeta je dobijeno" from data that contains no outcome. |
| `GET /api/outcome-intel/predmeti/{id}` (`routers/outcome_intel.py:49`) | own matters same `tip`, hronologija keywords, status, document counts, billing | yes | yes | Never reads `outcome_log`; "nagodba"/"poravnanje" → pobeda; `win_rate %` even on n=1; GPT asked for factor percentages ("85% pobeda") it cannot compute; fallback text prints win rate. |
| `GET /api/learning/slicni-predmeti/{id}` (`learning.py:431`) | `outcome_log` + GPT | yes | — | Uses human outcomes but GPT-synthesised similarity. |
| `GET /api/learning/performance-report`, `/impact-report` | `outcome_log`, `case_patterns` | yes (:690) | — | percentages over small n. |
| `GET /api/firma-memorija/*` | `memory_entries` office-wide | no | no | GET mutates (`_apply_trust`). |
| `api.py:1445` AI context | `memory_entries` office, `confidence ≥ 0.5`, not stale | feeds GPT prompt | — | Notes become prompt context without "statement, not fact" framing (INFERRED). |
| `GET /api/memory-graph/upit`, `/preporuka/{id}` | edges office-wide | yes — both call AsyncOpenAI (PROVEN `memory_graph.py:249,357`) | — | "ishod" edges presented as recommendation input. |
| `retrieve_documents` office branch (`app/services/retrieve.py:2062`) | `kancelarija_{id}` / `user_{id}` with ACL filter `shared/rag_acl.filter_za_namespace_vlasnika(dozvoljeni_predmeti, ["case_doc","draft_final"])` | downstream | — | Correct: filtered by authorized `predmet_id`s; `AI_GENERATED` excluded; freshness/origin weights. |
| Morning briefing / CIO / case_intelligence | `lessons_learned.status_lekcije` | varies | — | Readers exist that already respect `usvojena_praksa` (`learning_engine.py:950`). |

### D. TENANT / OFFICE SCOPE MATRIX

| Source | Scope key | RLS | Server filter | Cross-user visibility |
|---|---|---|---|---|
| `predmeti` raw matter | `user_id` | own | own | **Only owner + active `predmet_delegiranja` (`status='aktivno'`)** — canonical ACL `shared/rag_acl.dozvoljeni_predmeti` (mirror of `api.py::get_predmet`), fail-closed. |
| `outcome_log`, `lessons_learned`, `case_patterns`, `firm_dna`, `recommendation_log`, `counterfactual_log` | `user_id` | own | own | none. Not office-shared at all today. |
| `staging_memory` | `user_id` (+ `kancelarija_id` informational) | own + service_role | own | none for the row; promoted vector lives in office namespace but is retrievable only for authorized `predmet_id`s (D-row below). |
| Pinecone `kancelarija_{id}` | office namespace + `predmet_id` metadata | n/a | ACL `$in` authorized predmeti; >400 → narrowed to current | Same office does **not** grant retrieval of a colleague's matter vectors (PROVEN `rag_acl.py:54-150`). |
| `memory_entries`, `memory_graph_edges`, `judge_patterns`, `client_memory`, `partner_profiles` | `kancelarija_id` | 046/047 policies check `kancelarija_clanovi.status = 'aktivan'` | server filters `kancelarija_id` from `get_kancelarija_id_sync` which checks `status='ACTIVE'` | **Explicit office-sharing path**: a human deliberately writes a note/edge into office memory. Content (incl. `entity_name`, `from_naziv` = possibly matter name) is visible to all office members. RLS vocabulary mismatch (`aktivan` vs canonical `ACTIVE` in `shared/seats.py`) means user-JWT reads would see nothing; server uses service role, so effective scope = server filter (INFERRED). |
| `ai_corrections` | `user_id`, `kancelarija_id` | owner SELECT | `/stats` aggregates per office | raw texts not exposed cross-user by reviewed routes (INFERRED). |
| Removed member | `kancelarija_clanovi.status != ACTIVE` | — | `get_kancelarija_id_sync` returns None → narrows to `user_{uid}` | fail-narrow (PROVEN docstring + query). |

### E. TRUST / PROVENANCE MATRIX (mapping to locked trust classes)

| Source state | Law Brain trust class |
|---|---|
| `outcome_log` row (human POST) | HUMAN_CONFIRMED_OUTCOME |
| closed matter, no `outcome_log` | outcome = UNKNOWN (never inferred) |
| chronology "pobeda"/status keywords | not a source (ignored) |
| `memory_graph_edges.ishod` | part of EXPLICIT_GRAPH_RELATION, never outcome |
| `staging_memory` `approved` + `is_lawyer_approved` + `pinecone_indexed` | LAWYER_VERIFIED_ARTIFACT (indexed) |
| `staging_memory` `approved`, not indexed (confidence < 0.85) | LAWYER_VERIFIED_ARTIFACT with exact state `APPROVED_NOT_INDEXED` |
| `staging_memory` pending / rejected | AI_WORK_PRODUCT (untrusted) |
| `memory_entries` `izvor=manual` | HUMAN_MEMORY_NOTE (statement, not fact) |
| `memory_entries` `izvor=korekcija` | HUMAN_CORRECTION-derived note |
| `memory_entries` `izvor=auto/benchmark` | AI_CANDIDATE_LESSON |
| `memory_graph_edges` | EXPLICIT_GRAPH_RELATION (no causation) |
| `ai_corrections` | HUMAN_CORRECTION |
| `lessons_learned.status_lekcije=usvojena_praksa` with `potvrdio` | confirmed lesson (human gate passed) |
| `lessons_learned.status_lekcije=predlog_ai` | AI_CANDIDATE_LESSON |
| `lessons_learned.status_lekcije IS NULL` (pre-039 rows) | UNKNOWN_LEGACY |
| `lessons_learned` odbijena / zastarela | REJECTED / STALE — never served as current |
| `predmeti` metadata (tip, oblast, sud, dates) | SOURCE_CASE_FACT |
| `case_dna` Genome, `firm_dna`, GPT summaries | AI_WORK_PRODUCT / AI_CANDIDATE_LESSON |
| NS007 `autonomy_work_items` READY/ACCEPTED | AI_WORK_PRODUCT (ACCEPTED ≠ LAWYER_VERIFIED_ARTIFACT) |

### F. DUPLICATION MATRIX

| Duplicate | Members | Risk |
|---|---|---|
| Outcome truth | `outcome_log` vs `outcome_intel` keyword inference vs `memory_graph_edges.ishod` vs `predmeti.status` (uspesno/neuspesno legacy) | Three non-human "outcome" readings disagree with the one human truth. |
| Outcome writer | `routers/learning.py` vs `services/learning_engine.log_outcome` (dead) | Dead path with weaker validation could be revived. |
| Similar matters | `precedenti` (same tip, GPT), `learning/slicni-predmeti` (GPT over outcomes), `memory_graph/preporuka` | Three "similar matter" engines; none explainable. Law Brain must replace the read contract, not add a fourth GPT engine. |
| Lessons vs firm DNA vs memory notes | `lessons_learned`, `firm_dna`, `memory_entries(tip=obrazac)` | Same "pattern" can exist thrice with different trust. |
| Kancelarija resolution | `shared/kancelarija_utils.get_kancelarija_id_sync` (canonical); NS-level copies previously removed | OK — single resolver. Membership status vocabulary `ACTIVE` vs `aktivan` duplicated in RLS. |

### G. "TOXIC LEARNING" PATHS

1. **Keyword → win.** `outcome_intel._klasifikuj_ishod`: "nagodba"/"poravnanje" = pobeda; "Predmet zatvoren (ishod zabeležen: poraz)" contains no win keyword but a "Ishod:" line written elsewhere can flip it. Output is a percentage on any n ≥ 1.
2. **Counter replay.** `/api/learning/outcome` replay (double-click, retry) re-increments `case_patterns` pobede/porazi — counts drift from `outcome_log` (one row per matter).
3. **GPT asked to invent statistics.** `_BRAIN_SYSTEM` item 5 and `_OUTCOME_SYSTEM` request percentages the model cannot derive from provided data.
4. **AI lesson regeneration.** `POST /predmeti/{id}/lessons` inserts new `predlog_ai` rows each call — repetition amplifies the same unverified claim (frequency ≠ truth).
5. **Similarity includes active matters** (unused closed filter) → "office experience" drawn from unfinished matters.
6. **Memory note → AI prompt as fact.** `api.py:1445` feeds office notes with `confidence ≥ 0.5` into generation context; notes are statements by one person.
7. **Confirmation inflation.** `memory_entries` confirm: 3 confirmations add +0.2 confidence; confirmation also clears `zastarela` — an expired note can be "refreshed" with no content check (human action, acceptable but must be shown as such).
8. **Reject after approve keeps the vector.** `staging_reject` with no status guard leaves a promoted LAWYER_VERIFIED vector in the office namespace while the source says `rejected` → deleted/revoked knowledge still served.
9. **GET-side state mutation.** Reading `/api/firma-memorija/*` writes `zastarela=true`; a read path changing trust state.

### H. LEGACY CLAIMS THAT ARE TOO STRONG

| Claim (where) | Reality |
|---|---|
| "Law Firm Brain … pronalazi slične **zatvorene** predmete … vraća … ishode" (`precedenti.py:3-6`) | Closed filter unused; no outcome data read; ishodi come from GPT. |
| "U 82% uspešnih radnih sporova postojala je pisana komunikacija" (`outcome_intel.py:7`) | No document-type data is read (only per-matter counts); percentages are model-generated. |
| "Čestitamo! Iskustvo sa ovim predmetom sada pomaže budućim analizama." (`learning.py:295`) | Only true for readers of `outcome_log`; `precedenti`/`outcome_intel` never read it. |
| "Potvrđena lekcija … postaje vidljiva **timu**" (`learning.py:1085,1126`) | `lessons_learned` RLS and reads are per-`user_id`; nothing shares it with the team. |
| "Partner kancelarije potvrđuje" (`learning.py:1084`) | No partner role check; the lesson owner confirms their own AI lesson. Still a human gate, but not a partner gate. |
| "Institucijska memorija kancelarije — ostaje i kada senior partner ode" (038 comment) | Lessons are owned by the departing user's `user_id`. |
| "AI sistem registruje ovo odbijanje i uči iz njega" (`learning.py:1136`) | Rejection only flags the row; no learning consumer found (INFERRED from grep of readers). |

### REQUIRED FALSIFICATIONS

1. **"precedenti already is Law Brain" — FALSE.** Same-`tip`/`oblast` lookup over own matters (incl. active, :73 filter unused), GPT narrative, no outcome source, no trust classes, no validity, charges a credit. Boundary: it does correctly restrict to the caller's own `user_id`.
2. **"outcome_intel already has canonical outcome truth" — FALSE.** It never reads `outcome_log`; outcome = keyword/status inference; win-rate % without denominator discipline. Boundary: its counts of matters per `tip` are real.
3. **"firm_memory statements are all human-confirmed facts" — FALSE.** They are human-*authored statements* (`izvor=manual` default; schema allows `auto/benchmark/korekcija`), confirmation is optional (`potvrde_count` default 1 = author), expiry is computed on read. Boundary: every live insert today is human (only writer `/dodaj`), so HUMAN_MEMORY_NOTE is correct for `izvor=manual` — as a note, not as a fact.
4. **"accepted autonomous work is safe institutional knowledge" — FALSE.** NS007 ACCEPTED is a review disposition on `autonomy_work_items`; it never enters `staging_memory`, never gets `is_lawyer_approved`, never reaches Pinecone. It stays AI_WORK_PRODUCT until explicitly promoted through staging (Task 15).
5. **"same office means all raw matters may be shared" — FALSE.** Canonical ACL (`shared/rag_acl.dozvoljeni_predmeti`) = owner + active delegation only; office Pinecone retrieval is filtered by that ACL. Boundary: office memory tables (`memory_entries`, `memory_graph_edges`, judge/client profiles) ARE office-wide by design — they are the existing explicit office-sharing path, and any matter name a human typed into them is visible to colleagues.
6. **"lessons_learned are all verified lessons" — FALSE.** Default `status_lekcije='predlog_ai'` (039), generated by GPT; only rows with `usvojena_praksa` + `potvrdio` passed a human gate; pre-039 rows have NULL status → UNKNOWN_LEGACY.

### DECISION (architecture for Tasks 1–23)

- Law Brain = read/trust/synthesis layer in `services/law_brain.py` over: `outcome_log`, `staging_memory`, `lessons_learned`, `memory_entries`, `memory_graph_edges`, `ai_corrections`, `predmeti` (+ `case_dna` labelled AI), using `shared/rag_acl.dozvoljeni_predmeti` as the only raw-matter authorization.
- No new truth tables. Migration 137 only if Task 5 measurement proves the live read cannot be bounded.
- Legacy `precedenti` / `outcome_intel` are not modified tonight (directive) and are never read by Law Brain.

### KNOWN LIMITATIONS (Task 0)
- Production row counts / NULL-status distribution of `lessons_learned` and `memory_entries.izvor` are UNKNOWN (no production DB access by design).
- Whether production RLS policies were later amended to `ACTIVE` is UNKNOWN from migrations alone (server uses service role either way).

COMMIT: (this commit) `docs: map canonical Law Brain sources`
NEXT GATE: Task 1 — canonical contract.

---

## TASK 1 — CANONICAL LAW BRAIN CONTRACT

- PROBLEM: no shared vocabulary for trust/validity/scope; each legacy reader invents its own ("win", "usvojena praksa", "confidence 0.6").
- CURRENT OWNER: none (contract did not exist).
- EVIDENCE: Task 0 matrices E/F.
- FALSIFICATION: "a caller can mark AI content as human-verified" → impossible: `human_verified` is a derived property of `trust_class`; passing it is a `TypeError` (test). "validity defaults to CURRENT" → no: without validity data → `UNKNOWN`.
- DECISION: pure module `services/law_brain.py` (no DB, no model, no clock). Readers in later tasks normalise source rows into `LawBrainItem`.
- IMPLEMENTATION: locked `TRUST_CLASSES` (9), `HUMAN_CLASSES` (5; excludes SOURCE_CASE_FACT and UNKNOWN_LEGACY), `AI_CLASSES`; `VALIDITY_STATES` CURRENT/STALE/DEPRECATED/UNKNOWN; `SECTION_STATES` OK/EMPTY/UNKNOWN/DEGRADED/NOT_AUTHORIZED; scopes USER/OFFICE; frozen dataclass `LawBrainItem` (stable id `<kind>:<source_id>`, `source_ref`, lineage, `outcome_ref` mandatory for HUMAN_CONFIRMED_OUTCOME, exact `state`, bounded single-line excerpt ≤400); `validity_from(today=...)` with mandatory explicit `today`; `order_items` deterministic multi-pass stable sort; `AUTHORITY_NOTICE` ("Iskustvo kancelarije nije pravni izvor…").
- FILES: `services/law_brain.py`, `tests/test_ns008_t1_contract.py`.
- ROUTES: none.
- TRUST RESULT: AI / UNKNOWN_LEGACY / SOURCE_CASE_FACT never `human_verified`; DEPRECATED human item not `trusted`.
- TENANT RESULT: n/a (no I/O).
- TESTS: 16 passed.
- MUTATION RESULT: 8/8 killed (SOURCE_CASE_FACT as human, trusted ignores DEPRECATED, no-data→CURRENT, outcome without ref, unbounded excerpt, expired not stale, unknown class accepted, ordering without validity).
- KNOWN LIMITATIONS: none for the contract itself.
- NEXT GATE: Task 2.

---

## TASK 2 — CANONICAL OUTCOME TRUTH

- PROBLEM: legacy readers infer outcomes from status/chronology; the only human writer allowed replays to inflate counters and re-run GPT lessons.
- CURRENT OWNER: `outcome_log` (037), writer `POST /api/learning/outcome`.
- EVIDENCE (fresh):
  - who writes: only `routers/learning.py` upsert (`services/learning_engine.log_outcome` = 0 callers; would write `u_toku`, rejected by CHECK).
  - one matter = one outcome: `predmet_id UNIQUE` + upsert `on_conflict=predmet_id` → PROVEN (fake emulates the UNIQUE; test: 2 submissions → 1 row).
  - ownership: `_dohvati_predmet(.eq user_id)` before any write → B on A's matter = 404, no row (test).
  - divergence: outcome upsert first, closure second (closure failure is non-fatal) → outcome can exist on an active matter; also a matter can be reopened after the outcome. Law Brain therefore exposes `RECORDED_MATTER_REOPENED` with validity `STALE`, never `CURRENT`.
  - office scope: `outcome_log` is `user_id`-only (RLS own). No office sharing exists → nothing to leak; Law Brain reads it only for ACL-authorized matters and re-checks `row.user_id == predmet.user_id`.
- FALSIFICATION: "closed matter = win/loss" → test `status=zatvoren` + chronology "Ishod: pobeda", no outcome_log → `OUTCOME_UNKNOWN`. Legacy `status=uspesno` → not an outcome (`NOT_TERMINAL`).
- DECISION / IMPLEMENTATION:
  - `services/law_brain.py`: `ISHODI` (= CHECK 037), `outcome_view(predmet, row)` → RECORDED / OUTCOME_UNKNOWN / NOT_TERMINAL / RECORDED_MATTER_REOPENED; `ucitaj_ishode(supa, authorized_predmeti)` raises on DB error (caller → DEGRADED), drops rows whose owner ≠ matter owner or whose `ishod` is outside the CHECK set.
  - `routers/learning.py`: reads the existing outcome first (DB failure → 503, matter not closed); identical resubmission → no `case_patterns` increment, no `recommendation_log` rewrite, no GPT lessons (`ponovljen_ishod: true`); a corrected outcome updates the row but legacy counters are not re-incremented.
  - `shared/idempotency.py`: `POST /api/learning/outcome` added to `ZASTICENE_RUTE` (same key → route runs once, stored response).
  - Legacy `outcome_intel` untouched (directive); Law Brain never reads it.
- FILES: `services/law_brain.py`, `routers/learning.py`, `shared/idempotency.py`, `tests/ns008_fake.py`, `tests/test_ns008_t2_outcomes.py`.
- ROUTES: `POST /api/learning/outcome` (behaviour: replay-safe; new field `ponovljen_ishod`).
- TRUST RESULT: only `outcome_log` rows → `HUMAN_CONFIRMED_OUTCOME` with `outcome_ref`.
- TENANT RESULT: foreign write 404; forged foreign-owner row ignored by loader.
- TESTS: 13 passed; related existing suites (39 files: learning/idempotency) 396 passed, 81 skipped.
- MUTATION RESULT: 9/9 killed (T2-9 "GPT lessons on replay" initially SURVIVED → added `test_ponovljen_ishod_ne_pokrece_ponovo_gpt_lekcije` → killed).
- KNOWN LIMITATIONS: a corrected outcome (pobeda→poraz) leaves legacy `case_patterns` counters reflecting the first submission (legacy table; Law Brain does not read it). Legacy `static/vindex.js` sends no Idempotency-Key — covered by the logical replay guard, not by the durable store.
- NEXT GATE: Task 3.
