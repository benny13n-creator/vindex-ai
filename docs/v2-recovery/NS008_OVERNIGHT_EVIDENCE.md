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

---

## TASK 3 — TERMINAL MATTER EVENT CLOSURE

- PROBLEM: NS006 debt "legacy status PATCH may not emit terminal matter event".
- EVIDENCE (fresh, PROVEN in code): `MATTER_BECAME_TERMINAL` is reached only from `routers/predmeti_close.py` (zatvori + bulk), and there only as a **direct in-process call** to `_consequence_refresh_case_actions` (no outbox row). Two writers set a terminal status with no event at all: `PATCH /api/predmeti/{id}` (`status` in its allow-list) and `POST /api/learning/outcome` (sets `zatvoren`). Autonomy: both NS007 planners and both executors already refuse terminal matters (`hearing_prep.py:82,370`, `precedents_radar.py:263,347`).
- FALSIFICATION: "closing via PATCH closes open actions" → before the fix, PATCH wrote the status and nothing reconciled actions until some other event for that matter arrived.
- DECISION: one durable emitter, `services/event_bus.emit_matter_terminal`. It emits only on a real transition (new status ∈ `TERMINALNI_STATUSI_PREDMETA` and previous ≠ new). The event id is deterministic: `uuid5(ns, predmet:status:updated_at-after-write)`, so a retry of the same transition is a no-op, while reopen→close produces a new event. It is wired into PATCH (previous status is read only when a terminal status is requested) and into the learning outcome closure. Fail-soft: an outbox failure is logged and does not undo the status change. `predmeti_close.py` is left as is (it already reconciles through the canonical function; smallest change).
- IMPLEMENTATION / FILES: `services/event_bus.py`, `api.py`, `routers/learning.py`, `tests/test_ns008_t3_terminal_event.py`.
- ROUTES: `PATCH /api/predmeti/{id}`, `POST /api/learning/outcome` (no response change).
- CHAIN (test `test_ceo_lanac_patch_do_autonomije`): active matter with a hearing tomorrow → open action + planner proposes HEARING_PREP → PATCH `zatvoren` → 1 `events` row with the deterministic id → real `dispatch_pending_events` → `refresh_case_actions: completed` → 0 open actions → planner: 0 candidates and the QUEUED item is in `ponisteni` → `law_brain.je_terminalan` = True and outcome = `OUTCOME_UNKNOWN`.
- TENANT RESULT: B's PATCH of A's matter → 404, no event.
- TESTS: 11 passed. Regression (70 files touching events/PATCH/learning): 1008 passed, 1 failed → `test_phoenix_mission_002…::test_learning_close_write_uses_neq_guard_and_audit_trail`, a source-text test with a 2000-char window. The emission was moved after the hronologija insert (same semantics), and the test now passes unmodified.
- MUTATION RESULT: 7/7 killed (no PATCH emission, same-status emits, random event id, no learning emission, emitter accepts non-terminal, outbox failure breaks PATCH, constant transition ref).
- KNOWN LIMITATIONS: two concurrent PATCHes from an active status could both read "aktivan" and emit two events with different ids. Harmless, since `refresh_case_actions` is a reconcile, but recorded. The close routes still reconcile in-process rather than through the outbox (pre-existing design, unchanged).
- NEXT GATE: Task 4.

---

## TASK 4 — LAWYER-VERIFIED ARTIFACTS

- PROBLEM: Law Brain needs exactly one trusted source of institutional work product, and approved must stay distinct from indexed.
- CURRENT OWNER: `staging_memory` (088) + `routers/drafting.py`.
- EVIDENCE (fresh, code):
  1. AI draft → `_stage_draft_for_review` (`drafting.py:245`): ownership check, 60 s retry dedupe, Quality Gate `evaluate_draft_quality` → insert `pending` with `confidence_score`.
  2. `POST /api/staging/{id}/approve` (`:1283`): owner-scoped, atomic `pending→approved` claim (`is_lawyer_approved`, `approved_by`, `approved_at`).
  3. Promotion only if `confidence_score ≥ 0.85` (`:320`) → `ingest_session` into `rag_owner_namespace` (`kancelarija_{id}` | `user_{id}`) with `origin=LAWYER_VERIFIED`, `origin_chain=[AI_GENERATED, LAWYER_VERIFIED]` → `pinecone_indexed` set from the real result.
  4. Office retrieval of that vector remains ACL-filtered by `predmet_id` (Task 0 D).
- FALSIFICATION: "approved = in the knowledge base" → false: below the threshold, `approved` with `pinecone_indexed=false` (test). "A high-quality AI draft is trusted" → false: score 0.99 without approval → AI_WORK_PRODUCT (test).
- DECISION / IMPLEMENTATION: `law_brain.artifact_item` + `ucitaj_artefakte` + `trusted()`. LAWYER_VERIFIED_ARTIFACT only when `status=approved AND is_lawyer_approved AND approved_at`. States: `APPROVED_INDEXED`, `APPROVED_NOT_INDEXED`, `PENDING_REVIEW`, `REJECTED` (DEPRECATED), `REJECTED_STILL_INDEXED` (DEPRECATED, exposes the revocation gap), and `INCONSISTENT` (any other combination → AI_WORK_PRODUCT). A row whose `user_id` ≠ matter owner or whose `predmet_id` ≠ matter is dropped. `source_ref` → staging id. The excerpt is bounded (never the full draft).
- FILES: `services/law_brain.py`, `tests/test_ns008_t4_artifacts.py`.
- ROUTES: none new. Real `/api/staging/{id}/approve|reject` are exercised, with Pinecone promotion replaced as in `test_beta_gate_staging_approve_race.py`.
- TRUST RESULT: trusted set = {approved+indexed, approved-not-indexed}. Pending, rejected, poisoned, and inconsistent are never trusted.
- TENANT RESULT: B's staging row is never returned for A's matter; A cannot approve B's draft (404, no promotion).
- TESTS: 11 passed.
- MUTATION RESULT: 9/9 killed.
- KNOWN LIMITATIONS: **PROVEN gap, not fixed here:** `POST /api/staging/{id}/reject` on an already-approved, indexed row sets `rejected` but leaves the Pinecone vector and the `predmet_dokumenti` row. Law Brain reports it as `REJECTED_STILL_INDEXED` (never trusted). Vector removal is Task 21.
- NEXT GATE: Task 5.

---

## TASK 5 — CLOSED-MATTER PROFILE (derived, no new truth)

- PROBLEM: similarity and history need a structured view of past matters that separates fact, human outcome, and AI analysis.
- EVIDENCE: all inputs already exist with a single owner each: `predmeti` (tip, oblast, status, `case_dna` Genome), `outcome_log`, `predmet_dokazi.kategorija` (CHECK 016), `rocista.sud`, `predmet_issues.status` + `predmet_contradictions.relation_type/tezina/state` (119), and `staging_memory`.
- DECISION: **no migration 137.** Measured: `ucitaj_profile` makes exactly **6 queries** for 1 matter and for 61 matters (one `in_` per source; test `test_broj_upita_ne_raste_sa_brojem_predmeta`). The existing owners therefore already give a stable, bounded read, and materializing would only create a second copy to keep in sync. Task 22 re-measures at 1/100/1000.
- IMPLEMENTATION: `law_brain.matter_profile` (pure) + `ucitaj_profile` (batched). Sections:
  - `cinjenice` SOURCE_CASE_FACT: tip/oblast/status/courts/evidence counts by category/hearing count.
  - `ljudski_ishod` from Task 2.
  - `ai_analiza` AI_WORK_PRODUCT: Genome version only, live issue counts by status, open/review contradiction counts by type/severity.
  - `overeni_artefakti` (trusted only).
  - `nepoznato` (explicit list).
  - `poreklo` lineage: derivation_version `lb-profile-1`, genome_verzija, outcome_ref, outcome_updated_at — fully regenerable.
  - Excluded: claim text, issue labels, document text, Genome scores.
  - Rows whose `user_id` ≠ matter owner are dropped. Deleted evidence, merged issues, and resolved contradictions are not counted.
- FILES: `services/law_brain.py`, `tests/test_ns008_t5_profile.py`.
- TRUST RESULT: AI analysis always labelled AI_WORK_PRODUCT; a pending AI draft never appears among verified artifacts.
- TENANT RESULT: a forged B row on A's matter is not counted.
- TESTS: 6 passed. MUTATION RESULT: 8/8 killed (deleted evidence counted, foreign rows, resolved contradictions, AI draft as verified, N+1 queries, raw Genome leak, merged issues alive, unknown outcome not flagged).
- KNOWN LIMITATIONS: `predmeti.oblast` is not created by any migration in the repo, yet legacy `precedenti.py` selects it and the PATCH allow-list writes it. Its production existence is UNKNOWN from migrations, so the Task 11 loader must tolerate a missing column (fallback select).
- NEXT GATE: Task 6.

---

## TASK 6 — EXPLAINABLE SAFE MATTER SIMILARITY

- PROBLEM: legacy similarity was "same tip" + GPT, included active matters, and had no explanation.
- EVIDENCE: the canonical raw-matter authorization is `shared/rag_acl.dozvoljeni_predmeti` (owner + active `predmet_delegiranja`), the same one office Pinecone retrieval uses. No office-membership path grants raw matter access.
- FALSIFICATION:
  - "same office = may see colleague's closed matters": false. Required adversarial test: A and B in the same office (both `ACTIVE` members). B's response is **byte-identical** with and without A's closed matters existing: no name, client, Genome, outcome, id, or count (`pretrazeno_zavrsenih` counts only B's authorized matters).
  - "outcome influences ranking": false. The score is identical for pobeda/poraz/no outcome (test).
- DECISION / IMPLEMENTATION: `law_brain.slicni_predmeti(supa, uid, predmet_id)`:
  - The current matter must be in the ACL; otherwise `NOT_AUTHORIZED`.
  - Candidates = ACL ∩ terminal status ∩ not tombstoned, newest first, capped at `MAX_KANDIDATA=1000`.
  - Profiles come from Task 5. `similarity(profile, profile)` reads only facts and contradiction types.
  - Named-dimension points: tip 3, oblast 2, same court 1, shared evidence categories 1 each (≤3), shared contradiction types 1 each (≤3). Minimum 2 points.
  - Every match carries `razlozi[]` and a Serbian sentence `zasto`. The outcome is attached **after** matching (human outcome only).
  - Notice: "Bodovi … nisu procena šanse za uspeh." No `%` anywhere (test). No model call, read-only (test: only `select`).
  - `ucitaj_predmete` falls back to narrower columns **only** on a missing-column error (`oblast` UNKNOWN in production), and every `in_` read is chunked at 200 ids.
- FILES: `services/law_brain.py`, `tests/test_ns008_t6_similarity.py`.
- TENANT RESULT: same-office leak test passes; B asking about A's current matter → `NOT_AUTHORIZED`; active delegation → visible (`sopstveni: false`); revoked delegation → invisible.
- NEW FINDING (pre-existing, outside Law Brain): `rag_acl.dozvoljeni_predmeti` filters `brisanje_zapoceto` only on the **owner** branch. A delegated matter that is being deleted stays in the delegate's ACL, and therefore in the delegate's office-namespace RAG filter. Law Brain filters the tombstone itself (test `test_delegiran_predmet_u_brisanju_nije_kandidat`). The shared ACL fix is recorded for Task 21.
- TESTS: 12 passed. MUTATION RESULT: 7/7 killed. S6 (tombstone filter) and S7 (non-column error swallowed) initially SURVIVED → added the delegated-tombstone test and loader error tests → killed.
- KNOWN LIMITATIONS: dimensions are coarse (no fact-pattern text similarity, by design: no model, no raw facts copied). Candidates beyond the 1000 newest terminal matters are not scanned (Task 22).
- NEXT GATE: Task 7.

---

## TASK 7 — LESSONS LEARNED TRUST GATE

- FRESH ANSWERS:
  - AI-generated? **Yes**: `learning_engine.generate_lessons_learned` (GPT, JSON). Callers: the outcome route (opt-in) and `POST /api/learning/predmeti/{id}/lessons`.
  - Can a lawyer confirm/reject? **Yes**: `PATCH /api/learning/lessons/{id}/potvrdi` (owner-scoped).
  - Does the schema record confirmation? **Yes** (039): `status_lekcije` predlog_ai/usvojena_praksa/odbijena/zastarela, `potvrdio`, `potvrdjeno_at`.
  - Does code distinguish candidate vs confirmed? Partly: `cio.py` reads only `usvojena_praksa`, while `case_intelligence.py`/`knowledge_hygiene` read both.
- DECISION: reuse the existing schema. **No migration.**
- IMPLEMENTATION:
  - `law_brain.lesson_item` / `ucitaj_lekcije` / `lekcije_kao_smernice`. Mapping:
    - `predlog_ai` → CANDIDATE / AI_CANDIDATE_LESSON.
    - `usvojena_praksa` **with** `potvrdio` and `potvrdjeno_at` → CONFIRMED / LAWYER_VERIFIED_ARTIFACT (lineage AI_GENERATED→LAWYER_CONFIRMED).
    - `odbijena` → REJECTED / DEPRECATED.
    - `zastarela` or `zastarela=true` → STALE.
    - NULL status (pre-039), or "usvojena" without proof of who confirmed → UNKNOWN_LEGACY.
  - Only CONFIRMED and non-deprecated lessons are guidance.
  - Hardening: `learning_engine.save_lessons` now always writes `predlog_ai`. Before, it accepted `status_lekcije` from the lesson dict, so any future caller could write a lesson as already adopted. The confirm route was added to `ZASTICENE_RUTE`.
- FILES: `services/law_brain.py`, `services/learning_engine.py`, `shared/idempotency.py`, `tests/test_ns008_t7_lessons.py`.
- ROUTES: `PATCH /api/learning/lessons/{id}/potvrdi` (now durable-idempotent with a key).
- TRUST RESULT: a candidate is never guidance; the required mutation "CANDIDATE treated as confirmed" (L1) is killed.
- TENANT RESULT: B's lessons are never read for A; A cannot confirm or reject B's lesson (404).
- TESTS: 8 passed. Regression (38 files: lessons/learning_engine/idempotency): 318 passed, 81 skipped.
- MUTATION RESULT: 9/9 killed.
- NEW FINDING (legacy, not fixed): `routers/case_intelligence.py:124` and `services/knowledge_hygiene.py:49,267` select `sadrzaj` from `lessons_learned`. No migration defines that column (the text column is `lecija`, 038), so those reads would fail with 42703 in a schema built from the repo (production schema UNKNOWN). Law Brain reads `lecija`.
- KNOWN LIMITATIONS: lessons are per-user (`user_id`), so a "team" view does not exist (legacy claim H). The "partner" confirmation is really the owner's confirmation.
- NEXT GATE: Task 8.

---

## TASK 8 — HUMAN MEMORY + MEMORY GRAPH NORMALIZATION

- PROBLEM: office notes and graph edges are rendered and fed to AI as if they were facts. Legacy GET mutates state.
- EVIDENCE: Task 0 B/D/G.
  - `routers/firm_memory._apply_trust` writes `zastarela=true` during GET (PROVEN `firm_memory.py:110`).
  - `memory_graph_edges.ishod` is free text.
  - Notes and edges about a `predmet` or `klijent` are office-wide in legacy reads, so a colleague can read A's private matter name and client through them (`/api/firma-memorija/sve`, `/api/memory-graph/upit`).
- DECISION: `firm_memory` and `memory_graph` are preserved untouched. Law Brain's own read (`law_brain.ucitaj_memoriju`) normalizes:
  - `izvor` manual → HUMAN_MEMORY_NOTE; korekcija → HUMAN_CORRECTION; auto/benchmark → AI_CANDIDATE_LESSON; NULL → UNKNOWN_LEGACY.
  - Every note carries "Beleška kolege … nije proverena činjenica". Content is verbatim, never generalized ("uvek"). `potvrde_count` is shown as a number.
  - Validity is **computed** from `expires_at` against an explicit `today` (no expiry → UNKNOWN). Nothing is written on read.
  - Edges → EXPLICIT_GRAPH_RELATION with `uzrocnost: false`, notice "Ne dokazuje da je argument uzrokovao ishod", and the edge's `ishod` exposed only as `upisano_uz_vezu` (never `outcome_ref`, never counted).
  - Confidentiality boundary: office-shared entity types are sudija/firma/partner. A note or edge tied to a **predmet** requires the viewer in `rag_acl.dozvoljeni_predmeti`; one tied to a **klijent** requires the viewer to own that `klijenti` row. Office = canonical `get_kancelarija_id_sync` (`ACTIVE` only), so a removed member gets nothing.
- FILES: `services/law_brain.py`, `tests/test_ns008_t8_memory.py`.
- TENANT RESULT:
  - B (same office) sees the judge note and the general edge, but not A's matter/client notes or the matter edge (no name, id, client, or "pobeda" in the payload).
  - Active delegation opens the matter note/edge to B, while the client note stays A's.
  - C (removed) → nothing. D (other office) → only K2 notes.
- TESTS: 7 passed. MUTATION RESULT: 9/9 killed (matter note without ACL, client note without ownership, matter edge without ACL, auto as human, expiry ignored, GET-side write, removed member sees, causation true, inactive notes).
- KNOWN LIMITATIONS: legacy `/api/firma-memorija/*` and `/api/memory-graph/*` keep their office-wide behaviour and their GET-side write (directive: preserve, do not retire). The leak path through those legacy routes is recorded for founder review, not changed tonight. `judge_patterns`/`client_memory`/`partner_profiles` are not surfaced by Law Brain.
- NEXT GATE: Task 9.

---

## TASK 9 — OUTCOME PATTERNS WITHOUT PREDICTION

- PROBLEM: legacy `outcome_intel` produced a win-rate % from inferred outcomes, with GPT-invented factor percentages.
- DECISION: legacy stays (directive). The new `law_brain.descriptive_outcomes(profiles)` is a pure function over Task 5 profiles of relevant authorized matters (Task 6 results):
  - Only `HUMAN_CONFIRMED_OUTCOME` in state RECORDED is counted.
  - Reopened-matter outcomes and unknown outcomes are reported separately and never counted.
  - Output: `relevantnih`, `sa_ljudskim_ishodom`, `bez_ishoda`, `ponovo_otvoreni`, `po_ishodu`, `faktori[{faktor, broj, od}]` (denominator = recorded outcomes), `uzorak`, `mali_uzorak` (< 5), and deterministic Serbian sentences, e.g. "Zabeleženi ishodi: 2 pobeda, 1 poraz, 1 nagodba." / "Faktor „svedoci" izričito zabeležen u 3 od 4 ishoda." / "Veličina uzorka: 4."
  - Notice: "Nije predviđanje ishoda ovog predmeta." No `%`, no "šansa/verovatno/win rate", no model call.
- FILES: `services/law_brain.py`, `tests/test_ns008_t9_outcome_patterns.py`.
- TESTS: 7 passed (all NS008 so far: see commit). MUTATION RESULT: 6/6 killed (reopened counted, outcome without human item, percentage instead of denominator, denominator = all relevant, small-sample flag off, sample size hidden).
- KNOWN LIMITATIONS: factor keys are shown raw (as stored by the legacy form, e.g. `pisana_komunikacija`); the UI maps labels.
- NEXT GATE: Task 10.

---

## TASK 10 — VERIFIED OFFICE KNOWLEDGE RETRIEVAL

- PROBLEM: the office namespace mixes lawyer-verified drafts, client documents, and legacy vectors with no origin. Raw Pinecone score must never read as legal correctness.
- EVIDENCE: promotion metadata (`drafting.py:371-380`): `type=draft_final`, `origin=LAWYER_VERIFIED`, `parent_id=<staging id>`, `origin_chain`, `created_at`, `golden_template`. Retrieval infrastructure already exists: `rag_owner_namespace`, `rag_acl.filter_za_namespace_vlasnika`, `_ugradi_query`, `_pretraga_ns` (which raises instead of returning an empty list, B4).
- DECISION / IMPLEMENTATION: `law_brain.pretrazi_znanje_kancelarije(supa, uid, upit, today=, predmet_id=None)` — the same namespace and the same ACL filter, so there is no second vector layer.
  - Classes: LAWYER_VERIFIED → LAWYER_VERIFIED_ARTIFACT (source_ref = staging row). CLIENT_DOC / case_doc → SOURCE_CASE_FACT. Missing origin → UNKNOWN_LEGACY. AI_GENERATED is dropped.
  - Ranking: **trust tier first**, then deprecated last, then text similarity. A 0.99 legacy vector cannot outrank a 0.70 verified one (test).
  - **Read-time revocation:** a verified vector is returned only while its staging parent is still `approved` + `is_lawyer_approved`; a verified vector without a parent is dropped. This closes the Task 4 `REJECTED_STILL_INDEXED` exposure for this read path.
  - Defense in depth: matches whose `predmet_id` is outside the ACL are dropped even if the filter were lost.
  - Each result explains: `slicnost_teksta` labelled "retrieval sličnost teksta, nije pravna tačnost", `poreklo`, `verifikovao`, `vrsta`, `sveze` (existing `freshness_weight`, golden template honoured), `moze_biti_zastarelo` (true unless validity is CURRENT and freshness is 1.0), `lineage`/`origin_chain`, plus the notice "Iskustvo kancelarije nije pravni izvor".
  - Law and case law are not part of this result (external authority).
  - An empty query makes no embedding call. A Pinecone failure propagates (caller → DEGRADED).
- FILES: `services/law_brain.py`, `tests/test_ns008_t10_office_knowledge.py`.
- TENANT RESULT: B in the same office → filter `$in=[PB]` and only B's vector. A broken filter returns everything → defense still yields only B's vector. A focus on A's matter → NOT_AUTHORIZED with no Pinecone call.
- TESTS: 6 passed. One real defect was found while writing tests and fixed before commit: an origin-less legacy vector was flagged "not stale" despite UNKNOWN validity.
- MUTATION RESULT: 9/9 killed.
- COST: one embedding per explicit query (Task 26). Not used by the basic GET context (Task 11).
- NEXT GATE: Task 11.

---

## TASK 11 — CANONICAL LAW BRAIN READ API

- DECISION: new narrow router `routers/law_brain.py`. No existing route can honestly own the contract: `precedenti` and `outcome_intel` call GPT and charge credits. All logic is in `law_brain.kontekst_predmeta`.
- ROUTE: `GET /api/law-brain/predmeti/{predmet_id}` (auth `get_current_user`, 60/min).
  - Sections: `similar_cases`, `verified_artifacts` (current + similar authorized matters, trusted only, plus a pending count for this matter), `confirmed_lessons` (guidance only, plus candidate and unknown-origin counts), `relevant_human_memory` (office notes/edges that are general or tied to this matter), `descriptive_outcomes`, and `data_quality` (unavailable sources, genome present, closed matters scanned, similar with human outcome, lessons awaiting confirmation or of unknown origin).
  - Every section has `state`.
- FAILED SOURCE ≠ EMPTY: each section is computed independently, and an exception → `DEGRADED` (test: `lessons_learned` down → that section DEGRADED, others OK, `data_quality.nedostupni_izvori=["confirmed_lessons"]`). A similarity failure also degrades outcomes, which are derived from it.
- AUTHORIZATION:
  - ACL failure → 503 (never an empty 200).
  - A foreign, nonexistent, malformed, or tombstoned matter (including a delegated tombstoned one) → **byte-identical 404**.
  - `NOT_AUTHORIZED` remains a section state in the service contract (e.g. an unauthorized focus in office search). At route level, a foreign matter is a 404 so that no existence signal leaks.
- NO model (OpenAI constructor patched to fail, test passes), NO credit (`UsageService.consume` never called), NO writes (only `select` in the DB journal). The internal `_profili` are never serialized.
- FILES: `services/law_brain.py`, `routers/law_brain.py`, `api.py` (router registration), `tests/test_ns008_t11_api.py`.
- TENANT RESULT: B (same office) gets only B's context; A's matter name, artifact, lesson, and outcome are absent; the office judge note is present (general entity).
- TESTS: 9 passed. Route/security inventory suites (22 files): 661 passed, 2 failed — `test_ca_trust_boundary::test_M19…` and `test_product_intelligence::test_require_admin_allows_founder`, **both in the NS007 baseline failure list** (`scratchpad/ns007/base_names.txt`), so they are not NS008-attributable.
- MUTATION RESULT: 8/8 killed. A7 (tombstone check) initially SURVIVED, because the owner path of `rag_acl` already filters it; added a delegated-tombstone test → killed.
- NEXT GATE: Task 12.

---

## TASK 12 — EXPLICIT GROUNDED LAW BRAIN SYNTHESIS

- ROUTE: `POST /api/law-brain/predmeti/{id}/sinteza` (10/min).
  - Entitlement and price come from the **existing** feature `precedenti` ("Law Firm Brain", migration 064, plan professional, 1 credit) via `PermissionService.require` (kill switch, rollout, plan). No new registry row, no migration.
  - Durable idempotency: added to `ZASTICENE_RUTE`.
- MODULE: `services/law_brain_sinteza.py`, kept separate from `services/law_brain.py` so the read layer stays provably model-free (Task 1 test `test_modul_ne_uvozi_model` still passes; `law_brain.py` contains 0 "openai").
- FLOW:
  1. `kontekst_predmeta` (authorized, Task 11).
  2. `reference_za_sintezu` → numbered R1..Rn with trust class + source_ref. Similar matter → SOURCE_CASE_FACT. Its outcome → HUMAN_CONFIRMED_OUTCOME (only if RECORDED, never reopened). Verified artifacts / confirmed lessons → LAWYER_VERIFIED_ARTIFACT. Notes → their class. Computed statistics → SOURCE_CASE_FACT "Izračunato u kodu".
  3. **No trusted basis** (no similar matter, outcome, verified artifact, or confirmed lesson; notes alone are not enough) → `NEMA_OSNOVA`, no model call, no credit.
  4. Model (gpt-4o-mini, temp 0, JSON, `case_context` provenance).
  5. `proveri_sintezu` drops a claim for: invented or missing ref (including mixed valid+invented), kind not matching the source class (e.g. "ishod" citing a note), forbidden content (`%`, procenat, šansa, verovatno, predviđ, član N, zakon, ustav, sudska praksa, uvek, nikad), or any number not present in the cited references. Claims are dropped, never "repaired".
  6. Output: accepted `tvrdnje[{tekst, vrsta, refs, source_refs}]`, `odbaceno`, `razlozi_odbacivanja`, `reference`, notice "Nije pravni savet ni procena ishoda. Iskustvo kancelarije nije pravni izvor."
- CREDIT: charged once, after a successful model call. Model failure or invalid JSON → 503, no credit. The 5xx body is masked by the existing global disclosure boundary in `api.py` (deliberate; test asserts the status only).
- REPLAY: 2 physical POSTs with the same key → 1 model execution, 1 credit, byte-identical response (test).
- FILES: `services/law_brain_sinteza.py`, `routers/law_brain.py`, `shared/idempotency.py`, `tests/test_ns008_t12_synthesis.py`.
- TENANT RESULT: B's synthesis prompt for B's matter contains none of A's matter name, artifact, lesson, or outcome. A foreign matter → 404 with no model call.
- TESTS: 11 passed. Opening the context (GET) → 0 model calls, 0 credits (test).
- MUTATION RESULT: 9/9 killed. Y1 (mixed invented ref) and Y9 (reopened outcome offered as confirmed) initially SURVIVED → added pure-function tests → killed.
- KNOWN LIMITATIONS: the synthesis result is not persisted (no table). The "one logical result" guarantee is per Idempotency-Key, and a new click is a new, separately charged synthesis by design.
- NEXT GATE: Task 13.

---

## TASK 13 — V2 ZNANJE: LAW BRAIN

- DECISION: no new sidebar item. A new section **„Iskustvo kancelarije"** inside the existing Znanje view (after the NS005 sections Sudska praksa / Interni stavovi), rendered by the new module `frontend-v2-ng/src/law-brain.js` (`VxLawBrain.znanje`). It is loaded through the existing build-token rewrite (`<script src="src/law-brain.js">` → `/v2/app/@<token>/src/law-brain.js`, `api.py::_v2_ng_primarni_html`).
- BACKEND: `GET /api/law-brain/znanje` → `law_brain.pregled_znanja`. Sections, each with a state:
  - `iskustvo`: authorized terminal matters grouped by tip + `descriptive_outcomes` per group.
  - `verifikovani_radovi`: trusted artifacts + authorized matter name.
  - `potvrdjene_lekcije`: guidance only + candidate/rejected/unknown counts.
  - `memorija_kancelarije`: Task 8 boundary.
  - `data_quality`.
- UI CONCEPTS: Raniji predmeti po vrsti (Iskustvo), Verifikovani radovi, Potvrđene lekcije, Memorija kancelarije, plus an explicit three-layer explanation (zakon i sudska praksa = external authority / znanje kancelarije = experience, not a legal source / AI analiza = always labelled).
  - Every item carries a trust label: Ishod uneo advokat / Overio advokat / Beleška kolege — nije proverena činjenica / Veza … ne dokazuje uzrok / Predlog AI — nepotvrđeno / Poreklo nepoznato. STALE is flagged.
  - Candidate lessons appear only as a count waiting for confirmation.
  - The filter is local (no request).
  - No tiles, gamification, animation, or "AI learns" copy.
- COST: opening Znanje = exactly 1 GET `/api/law-brain/znanje`, 0 POST, 0 model, 0 credit (Playwright request log + backend test).
- STATES: section DEGRADED → "Nije dostupno — izvor nije pročitan. Ovo ne znači da podataka nema." A whole-request 503 → error text "…ne znači da ga nema" with the content hidden. EMPTY → honest empty text (e.g. B: "Još nema završenih predmeta koje možete da vidite").
- FILES: `services/law_brain.py`, `routers/law_brain.py`, `frontend-v2-ng/src/law-brain.js`, `frontend-v2-ng/index.html`, `frontend-v2-ng/src/app.css`, `frontend-v2-ng/src/app.js`, `frontend-v2-ng/package.json` (`verify:live-law-brain`), `tests/ns008_ui_fixture.py` (real route responses), `frontend-v2-ng/tests/live-law-brain.mjs`, `tests/test_ns008_t13_znanje_api.py`.
- TESTS:
  - Playwright `live-law-brain` 19/19 (real backend responses, A/B, degraded, 503, 390px + 1440px light, duplicate IDs = 0, no external requests, no console errors).
  - Backend 4 passed.
  - Existing `live-znanje` (NS005) 33/33 unchanged.
  - Found while building the fixture and fixed: Serbian plural in descriptive sentences ("1 relevantnih ranijih predmet" → "1 relevantan raniji predmet"; 2–4 / 5+ forms; new parametrized test).
- MUTATION RESULT: 4/4 killed (DEGRADED shown as empty, note without its trust label, filter that sends a request, candidate lessons shown as guidance).
- NEXT GATE: Task 14.

---

## TASK 14 — MATTER CONTEXT: "ISKUSTVO KANCELARIJE"

- DECISION: no new primary tab. A secondary section `#lbp-blok` inside the existing Matter → Analiza body, placed after the Genome content and outside `#an-sadrzaj`, so it loads independently even when the Genome read fails. It is rendered by `VxLawBrain.predmet` and wired as a composite in `app.js`; `analizaPredmeta` delegates `postavi/aktiviraj/ocisti` to both the NS006 Genome analysis and the Law Brain section.
- CONTENT:
  - Similar prior authorized matters, each with its "Sličan jer: …" reason and human outcome (or "Ishod nije zabeležen"). A delegated colleague matter is marked.
  - Verified internal work, confirmed lessons, descriptive outcome history with a small-sample note, and office notes (labelled).
  - With no trusted knowledge: "Za ovaj predmet kancelarija još nema proverenog iskustva." No padding prose.
- SYNTHESIS: only through the explicit button "Analiziraj iskustvo kancelarije" (one POST via `VxApi.send` with Idempotency-Key).
  - Claims render with their kind label and "AI sinteza · izvori: R…".
  - The dropped count and the "nije pravni savet" notice are shown.
  - `NEMA_OSNOVA` → honest message.
  - 503 → "Analiza nije izvršena. Kredit nije potrošen." (route contract: 503 only before any charge).
  - Any other 5xx or interrupted request → "Ishod analize nije poznat. Ne pokrećite je ponovo…" (no false promise).
- COST: opening Analiza = 1 GET `/api/law-brain/predmeti/{id}`, 0 POST (Playwright request log).
- NS006 REGRESSION ADJUSTMENT (explicit, scoped): `frontend-v2-ng/tests/live-analiza.mjs` asserted that opening Analiza calls only the Genome routes. Its allow-list now also admits **GET** `/api/law-brain/predmeti/{id}` (a read; no model, no credit). Any non-GET to `/api/law-brain/*` on open still fails the test. Result: 43/43.
- FILES: `frontend-v2-ng/src/law-brain.js`, `frontend-v2-ng/index.html`, `frontend-v2-ng/src/app.js`, `frontend-v2-ng/tests/live-law-brain.mjs`, `frontend-v2-ng/tests/live-analiza.mjs`.
- TESTS: `live-law-brain` 33/33 (Znanje 19 + matter 14: A context, B honest empty without A's data, B synthesis without basis, degraded notes, 503, 500, 390px light, duplicate IDs). `live-analiza` 43/43.
- DEFECT FOUND AND FIXED BEFORE COMMIT: the UI read the HTTP status from the wrong field (`greska.status` instead of `r.status`), so a 503 was shown as "ishod nepoznat".
- MUTATION RESULT: 5/5 killed (hidden model call on open, no honest-empty message, DEGRADED as empty, claims shown without sources, 503 reported as unknown).
- NEXT GATE: Task 15.

---

## TASK 15 — FINAL ARTIFACT PROMOTION (human-reviewed learning loop)

- PROBLEM: NS007 ACCEPTED products must never become institutional knowledge silently, yet a lawyer needs a path to keep good work.
- DECISION: an explicit, separate action that goes **through the existing `staging_memory` workflow**:
  - `POST /api/law-brain/rad/{work_id}/predlozi-znanje` (durable-idempotent, 20/min) → `services/law_brain_promocija.predlozi_kao_znanje`.
  - Requirements: the item is owned by the caller, its status is **ACCEPTED** (READY/REJECTED → 409), the matter ownership is re-checked, and it has content.
  - Effect: deterministic text extraction (title, summary, every `tekst` field) → existing Quality Gate → **one** staging row (`tip=pripremljen_rad`, `pending`, `quality_detail.izvor_rad_id` = lineage back to the work item). A repeat request returns the same staging row.
  - The module **never** writes Pinecone and never sets `is_lawyer_approved`. Verification still requires the existing `POST /api/staging/{id}/approve`, plus the ≥0.85 threshold for indexing.
- UI: in the NS007 "Pripremljeni rad" detail, a section **„Znanje kancelarije"** appears **only for ACCEPTED** items (also right after accepting), with the copy "Prihvaćen rad nije automatski znanje kancelarije…" and the button "Predloži kao znanje kancelarije". Messages: pending review / already proposed / unknown outcome (no duplicate on retry) / 409.
- REQUIRED TESTS:
  - READY → absent from trusted brain, and promotion refused (409).
  - ACCEPTED (seeded and via the real accept route) → still absent, 0 staging rows.
  - Explicit promotion → staging `pending` = AI_WORK_PRODUCT / PENDING_REVIEW (not trusted), 0 Pinecone calls.
  - Lawyer approval via the real route → LAWYER_VERIFIED_ARTIFACT / APPROVED_INDEXED, lineage AI_GENERATED→LAWYER_VERIFIED.
- FILES: `services/law_brain_promocija.py`, `routers/law_brain.py`, `shared/idempotency.py`, `tests/ns008_fake.py` (staging DEFAULTs from 088), `tests/test_ns008_t15_promotion.py`, `frontend-v2-ng/src/pripremljeno.js`, `frontend-v2-ng/index.html`, `tests/ns008_ui_fixture.py`, `frontend-v2-ng/tests/live-law-brain.mjs`.
- TESTS: backend 7 passed. Playwright `live-law-brain` 37/37 (+4 promotion checks, real route responses). NS007 `live-pripremljeno` 51/51 unchanged.
- MUTATION RESULT: 6/6 killed (READY promotable, proposal pre-approved, direct Pinecone promotion, no dedupe, foreign work item, accept auto-proposes).
- NEXT GATE: Task 16.

---

## TASK 16 — CORRECTIONS AS INSTITUTIONAL LEARNING

- EVIDENCE (fresh): ADR-0006 ("Case Memory is a deterministic lookup") specifies an office-scoped `entity_corrections` table with lookup-and-boost. **Neither the table, nor a migration, nor any code exists** (repo-wide grep: only the ADR and ADR-0017 mention it). The existing explicit correction contract (`POST /api/smart-intake/entities/{id}/correct` → `extracted_entities.corrected_value` + `intake_processing_outcomes.user_corrected` + audit `entity_corrected`) stays locked to a single document, so the same OCR mistake recurs in the next one. `intake_jobs.kancelarija_id` is written as `None` at enqueue (`smart_intake.py:206`). Integration is therefore missing, and this task commits it.
- DECISION (no migration, no model): `services/law_brain_ispravke.py` derives a deterministic office lookup at read time **from the existing contract only**:
  - Office = canonical `get_kancelarija_id_sync` + ACTIVE members + admin; solo = own corrections only.
  - Their intake jobs → documents → corrected entities, **only `judge`/`court`** (institutional name normalizations). Party names, amounts, deadlines, and case numbers are matter facts and never transfer.
  - An ambiguous original (several distinct corrections) → no suggestion.
  - Matching uses a normalized key (diacritics/case/spacing; đ→dj→d). Corrections are compared by exact text, so "Petrovic" → "Petrović" counts as a real correction (a defect found during testing and fixed before commit).
- INTEGRATION: `GET /api/smart-intake/jobs/{id}` adds `predlog_ispravke` to matching **unreviewed** entities (first document and every segmented document) as `{vrednost, trust_class: HUMAN_CORRECTION, broj_ispravki, kada, razlog}`, with the lineage text "Advokat iz vaše kancelarije ispravio je „X“ u „Y“ (02.09.2026.). Proverite pre potvrde." The date comes from audit `entity_corrected`; without it the text says "datum nije zabeležen".
  - The extracted value is **not** changed; the lawyer still confirms through the existing correct route.
  - A lookup failure → `predlozi_ispravki_stanje: DEGRADED`, and the job view still works.
  - No matter name, document, or client is exposed: the lineage contains only the string the user already sees and its corrected spelling.
- FILES: `services/law_brain_ispravke.py`, `routers/smart_intake.py`, `tests/test_ns008_t16_corrections.py`.
- TENANT RESULT:
  - Office A colleague → suggestion.
  - Office B (same raw value) → none.
  - A removed member's corrections no longer contribute.
  - B's own new correction does not reach office A.
- TESTS: 8 passed. Smart Intake regression (46 files): 761 passed, 9 skipped.
- MUTATION RESULT: 7/7 killed (no office scope, party names transferred, ambiguous → suggestion, automatic overwrite, inactive members, diacritic correction discarded, lookup failure breaks the job view).
- KNOWN LIMITATIONS: suggestions are not yet rendered in the V2 intake review UI (backend contract only). The lookup scans the newest 300 office intake jobs (bounded). ADR-0006's admin review/revoke route (`/api/admin/intake/corrections`) also does not exist; revoking = re-correcting the source entity.
- NEXT GATE: Task 17.

---

## TASK 17 — KNOWLEDGE VALIDITY / STALENESS

- EVIDENCE: existing validity primitives:
  - `memory_entries.expires_at/zastarela`
  - `lessons_learned.zastarela/status_lekcije` (+ `check_knowledge_decay`, knowledge hygiene)
  - vector `valid_until/status DEPRECATED/golden_template` + `freshness_weight`
  - `outcome_log` (historical fact)
  
  There is **no reliable legal-change signal tied to a cited article**: `law_docs` (020) is only an ingestion log of uploaded law files (status pending/running/done/failed/obrisan), with no version or validity mapping.
- SELF-FALSIFICATION (defect in my own Tasks 4/7, fixed here): approved artifacts and confirmed lessons were reported `CURRENT` with no positive validity signal. That is false freshness: approval proves the lawyer verified the work **then**, not that it is legally current now.
- DECISION / IMPLEMENTATION:
  - `CURRENT` only with a positive signal: memory `expires_at` in the future, vector `valid_until`/golden template, or the human outcome of a terminal matter (historical fact). Approved artifact / confirmed lesson without validity data → `UNKNOWN` (still `trusted`, since trust ≠ currency). Rejected → `DEPRECATED`; flagged stale or expired → `STALE`.
  - `law_brain.pravna_aktuelnost(text)` adds `pravna_aktuelnost: UNKNOWN` to every artifact and lesson, plus `poziva_se_na_propis` (regex: "član N", "čl. N", "Zakon o …", "Sl. glasnik") with the note "Poziva se na propise — proverite da li su u međuvremenu izmenjeni." Nothing is rewritten, and nothing is marked stale without a signal.
  - UI: the note renders on Znanje/Analiza items (Playwright: the verified artifact citing "članu 154 ZOO" shows the note, and the word "aktuelan/važeći" is never claimed).
- NOT BUILT (directive): a national law-version registry. Required future work: an article-level validity source; once it exists, `pravna_aktuelnost` is the single switch point.
- FILES: `services/law_brain.py`, `frontend-v2-ng/src/law-brain.js`, `tests/test_ns008_t17_validity.py`, `tests/test_ns008_t4_artifacts.py` / `tests/test_ns008_t7_lessons.py` (expectations corrected to UNKNOWN), `tests/test_ns008_t11_api.py` (fixture artifact cites a law), `frontend-v2-ng/tests/live-law-brain.mjs`.
- INCIDENT (tooling, fixed): a shell heredoc turned `\b` into a literal backspace byte inside the regex, so the pattern could never match, and `\n` in a JS regex into a real newline. The tests caught both, both were fixed via scratch scripts, and a control-character scan of all 39 branch-changed files is now clean.
- TESTS: 8 passed (all NS008 backend: 151 passed). Playwright `live-law-brain` 38/38.
- MUTATION RESULT: 5/5 killed (approved = CURRENT, confirmed lesson = CURRENT, legal currency asserted, no citation detection, memory expiry ignored).
- NEXT GATE: Task 18.

---

## TASK 18 — NS007 AUTONOMY CONSUMES LAW BRAIN — **SKIPPED (by design)**

- RULE: "If safe integration is not clean: SKIP Task 18. Do not contaminate stable autonomy architecture."
- EVIDENCE (why not clean):
  1. NS007 work-item validity is version-gated: `dedupe_key = HEARING_PREP:<rociste>:<verzija_rocista>:g<genome verzija>`, and the executor refuses stale items when the hearing version or `source_version` (Genome) changed (`hearing_prep.py:153-154, 360, 376`). Law Brain references (verified artifacts, confirmed lessons, human outcomes) have **no version in that key**.
  2. A product prepared with an office artifact would therefore stay READY/ACCEPTED after that artifact is rejected or revoked (Task 21) or its lesson is rejected. There is no SUPERSEDED path for brain changes, which is exactly the "learn a false lesson once and repeat it" failure.
  3. Fixing that requires changing NS007's planner dedupe key, `source_version` semantics, `_poznati_idjevi` reference validation, the prompt contract, and the review UI's reference rendering (a new reference type). That touches all of NS007's stable lifecycle.
- WHAT EXISTS INSTEAD (safe path): the lawyer gets office experience next to the matter (Task 14), with the explicit grounded synthesis (Task 12) on demand.
- DESIGN FOR A FUTURE SPRINT (not implemented):
  - Add a `law_brain_fingerprint` (sorted ids + states of the ≤5 trusted references used) to `source_refs`, and include it in the dedupe key.
  - The planner recomputes it, so a change → SUPERSEDED + replan.
  - Validation accepts `lb:<kind>:<id>` refs only from that exact set.
  - Only HUMAN_CONFIRMED_OUTCOME and LAWYER_VERIFIED_ARTIFACT, authorized via `rag_acl` for `item.user_id`. No extra model call (deterministic Task 11 read).
- COMMIT: none (no code change).
- NEXT GATE: Task 19.
