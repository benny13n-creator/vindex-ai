# Smart Intake Engine — Implementation Phase Plan

Tracking doc for implementation against the frozen architecture in
`docs/adr/`. See `docs/adr/README.md` for the decision index and
`docs/ENGINEERING_PRINCIPLES.md` for standing rules.

**Rule for this entire implementation:** if an ADR exists, implementation
follows it. A shortcut ("skip the review queue here," "write straight to
the table for just this endpoint") is not a local decision — it's either
disallowed, or it means the ADR itself needs a formal amendment first.
"Small deviations" during implementation are exactly how the durability and
review-queue guarantees this whole design exists to provide quietly stop
being true.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Foundations
**Goal: make upload reliable and durable. No AI behavior changes yet.**

- [x] Persistent Event Bus (outbox pattern) — `services/event_bus.py::dispatch_pending_events` + `DispatchLoop`, migration 073 (`events` table) — [ADR-0001](adr/0001-async-ingest-job-queue.md), design review §7/§26.4
- [x] Persistent Job Queue (`intake_jobs`, Postgres-backed, `claim_intake_job` RPC) — `shared/intake_queue.py` — [ADR-0002](adr/0002-postgres-job-queue.md)
- [x] Upload transaction — `enqueue_intake_job` RPC (job + audit + outbox event atomic, migration 073)
- [x] Retry mechanism (exponential backoff, dead-letter at max_attempts) — `shared/intake_queue.py::mark_job_failed` + `fail_intake_job` RPC (atomic)
- [x] Audit log (`intake_audit_log`, append-only) — `shared/intake_queue.py::write_audit`
- [x] Worker scheduling — `shared/intake_worker.py::IntakeWorker` (idempotent claim→process→complete/fail, graceful shutdown, periodic reaping of stale claimed jobs, heartbeat)
- [x] Periodic dispatch of outbox events — `services/event_bus.py::DispatchLoop`
- [x] Upload endpoint — `POST /api/smart-intake/documents` (`routers/smart_intake.py`) — **note:** originally specced as `/api/intake/documents` (ADR-0001); renamed after discovering `/api/intake/*` already belongs to the live CRM Intake Wizard (`routers/intake.py`, unrelated feature, same word). Formally amended in ADR-0001, not silently changed.
- [x] Operational observability — `GET /api/smart-intake/admin/health` (queue depth, oldest pending, failed/retrying, outbox backlog, dispatch latency, worker heartbeats) — `intake_queue_metrics` / `events_outbox_metrics` views
- [x] Restart-safety — `claimed_at` + `reap_stale_jobs()`: a job stuck in an in-progress status past a staleness threshold is requeued through the normal retry/dead-letter path, never permanently stuck
- [x] End-to-end restart-safety test (simulated crash mid-processing, confirm no lost events / effectively-once) — `tests/test_intake_e2e_restart.py`, drives the real production code (not a reimplementation) against an in-memory fake of the Postgres RPC surface. Honest limitation documented in the test's own docstring: this proves the orchestration logic, not the real Postgres row-locking guarantees — those need the live migration run to verify for real.

**Phase 0 — Definition of Done: met, verified live against production Supabase (2026-07-15).**

Migration 073 ran into three real bugs on first execution — found and
fixed via founder-run diagnostics, not guessed:
1. `CREATE POLICY` has no `IF NOT EXISTS` in Postgres (unlike `CREATE
   TABLE`) — any re-run of the file aborted on the first policy statement.
   Fixed with `DROP POLICY IF EXISTS` before each of the 5 policies.
2. `CREATE TABLE IF NOT EXISTS` doesn't add columns to a table that already
   exists — `intake_jobs` was created before `claimed_at` existed in the
   file, so it was silently missing. Fixed with an explicit `ALTER TABLE
   ADD COLUMN IF NOT EXISTS` (same pattern as migration 072).
3. `claim_intake_job` was the only one of 4 RPCs missing `SECURITY
   DEFINER` — its `UPDATE ... RETURNING` silently returned empty under RLS
   even though the write succeeded, making a successful claim look like
   "no job found." Found live: 11 test jobs stuck in `preprocessing`.

**Live verification performed** (direct against production Supabase, real
RPCs, real `IntakeWorker`, real `dispatch_pending_events` — not mocks):
- 5 consecutive enqueue→claim→complete cycles: 5/5 correct
- Full acceptance sequence (upload → 202-equivalent in 327ms → queue depth
  → autonomous worker claim → complete → audit trail → outbox → dispatch →
  heartbeat → queue depth back to 0): 10/10 steps passed
- Chaos/restart-safety test (upload → claim → simulated crash → reap →
  reclaim by a second worker → complete → dispatch): 11/11 checks passed,
  exactly one `DocumentJobCompleted` event despite the crash, zero events
  left undispatched, complete audit trail (`job_created` → `job_retry_
  scheduled` → `job_completed`)
- Performance baseline: 20 sequential uploads, enqueue latency 88–287ms
  (avg 110ms). Throughput measurement was inconclusive due to a counting
  artifact in the benchmark script itself, not re-run — noted honestly
  rather than reported with false confidence. Worth redoing properly
  before Phase 1A if throughput becomes a real question.
- Housekeeping: found and killed 3 orphaned local dev server processes
  left running from earlier in the session — one of them was actively
  racing the verification scripts for the same jobs, which is what
  originally made the SECURITY DEFINER bug look non-deterministic.

Migration `073_intake_foundations.sql` **run successfully** against
production Supabase. Includes the `intake-dokumenti` storage bucket
insert. See commits for this phase for exact file list and bug fixes.

**Not yet verified:** the actual HTTP layer (`POST /api/smart-intake/
documents` with real multipart upload + encryption + Storage write, `GET
/api/smart-intake/admin/health` with real founder auth) — all live testing
above went through the service layer directly (`shared/intake_queue.py`,
`shared/intake_worker.py`, `services/event_bus.py`), not through FastAPI
+ auth. Worth a real HTTP-level smoke test before Phase 1A ships.

## Phase 1A — Classify, Extract, Confidence Graph, Review Queue
**Founder's product Definition of Done (verbatim intent, not technical):**
upload one judgment → in under a minute see it classified, key data
extracted, deadline found, confidence clearly shown per field — and if
something is uncertain, see ONLY the uncertain fields (typically 1-2, not
20), fixable in ~10 seconds. Deliberately narrower than the original
design review's Phase 1: **no case-matching** (`predmet_id` stays NULL
through all of 1A) — founder's explicit scope cut, added later.

- [x] OCR — reuses existing `uploaded_doc/extractor.py` as-is (no deskew/
      perspective-correction added yet — deliberately deferred until real
      usage shows OCR quality is actually the bottleneck, matching the
      founder's "real usage over more engineering" principle for this phase)
- [x] Classification — `shared/intake_classify.py`, hybrid: Cyrillic+Latin
      keyword heuristics first (12-type taxonomy), LLM fallback only when
      heuristic finds nothing — [ADR-0003](adr/0003-hybrid-extraction.md) pattern
- [x] Metadata extraction — `shared/intake_extract.py`: `case_number`/
      `amount` regex (Serbian formats, Cyrillic+Latin), `deadline` reuses
      existing `uploaded_doc/deadline_parser.py` (not reimplemented),
      `judge`/`plaintiff`/`defendant`/`court`/`law_cited` via one LLM call
- [x] Confidence Graph — `extracted_entities` table (migration 074), every
      field independently scored — [ADR-0005](adr/0005-confidence-graph.md)
- [x] Review Queue — `intake_review_queue`, `low_confidence_fields` lists
      ONLY the specific uncertain field names, not "review this document"
- [x] Processing outcomes capture — founder's explicit request,
      `intake_processing_outcomes` (migration 074): document_type,
      ocr_confidence, entity_confidence, user_corrected, fields_corrected,
      processing_time_ms, written after every document and every correction
- [x] 10-second correction flow — `POST /api/smart-intake/entities/{id}/
      correct`: original value never deleted, `corrected_value` added,
      writes a fresh `intake_processing_outcomes` row with
      `user_corrected=true` (the tuning data founder asked for)
- [x] Results view — `GET /api/smart-intake/jobs/{id}` returns document
      type + every entity with confidence + exactly which fields (if any)
      need review, in one call
- [ ] Folders as views — [ADR-0004](adr/0004-folders-as-views.md) — not in this narrower 1A scope, deferred to when case-matching returns

**Real bug found and fixed via live testing** (not caught by unit tests,
since it required a real bilingual Cyrillic/Latin legal text): a test
judgment ("П 341/26", judge/court/parties/amount/deadline all present)
initially extracted `deadline = 03.06.2026` (the judgment's own date)
instead of `15.11.2026` (the actual appeal deadline). Root cause was two
layers deep in the reused `deadline_parser.py`: (1) its category keyword
matching (`_kategorija`) was Latin-only, so Cyrillic "жалба" never matched
"zalba" and silently fell back to "ostalo"; (2) even after fixing that, the
100-char context window meant both dates in a short paragraph could share
the same category, so a same-category first-match still picked the wrong
one. Fixed with a second signal: prefer a category-matched deadline that
also has `istekao=False` (not already expired) — the operative deadline is
essentially always in the future relative to the judgment's own date.
Regression tests added (`test_extract_deadline_cyrillic_zalba_category_
recognized`, `test_extract_deadline_prefers_legally_significant_date_
over_first_mentioned`).

**Live-verified** (real OpenAI calls, realistic Cyrillic judgment text,
not a unit-test fixture): classification correct (`judgment`, heuristic,
0.85, 0ms — no LLM call needed), all 8 Confidence Graph entities extracted
correctly (case number, amount, deadline, judge, plaintiff, defendant,
court, law_cited), only `law_cited` below the 90% auto-accept threshold —
matching the founder's "1-2 uncertain fields, not 20" bar. Classification+
extraction: ~3.9s total (dominated by one LLM call for the 5 free-text
fields).

**Not yet live-verified:** the full pipeline through real encrypted
Storage + `IntakeWorker._process()` end-to-end (only the classify/extract
logic itself was live-tested directly; the storage download/decrypt/OCR
path is unit-tested with mocks but not run against a real uploaded file
yet), and the HTTP layer (`POST /api/smart-intake/documents` → poll →
correct) with real auth.

## Validation Sprint (not "Phase 1B" — deliberately, founder's framing)
**Goal: prove the existing functionality saves real time, not add more of
it.** Founder's read on the situation, 2026-07-15: "pre nekoliko nedelja
rizik projekta bio je 'da li arhitektura može da izdrži?' Danas je rizik
postao: 'koliko precizno sistem razume pravne dokumente u stvarnom radu
advokata?'" — infrastructure risk is mostly retired; domain-accuracy risk
is now the real one. No new AI functionality until real usage data says
where it's actually needed (explicitly NOT Case Memory/Lineage/Semantic
Dedup yet — "ako ih sada implementiraš, optimizovaćeš pretpostavke, ne
stvarno ponašanje korisnika").

**Founder's KPI targets** (measured two different ways — see below):

| KPI | Target | Measured by |
|---|---|---|
| OCR uspešnost na digitalnim PDF | >98% | Office Accuracy Dashboard (live) |
| Tačnost broja predmeta | >99% | Accuracy Benchmark (ground truth) |
| Tačnost rokova | >95% | Accuracy Benchmark (ground truth) |
| Prosečan broj review polja | <2 po dokumentu | Office Accuracy Dashboard (live) |
| Prosečno vreme ispravke | <10s | Office Accuracy Dashboard (live, approximate) |
| LLM fallback | <15% dokumenata | Office Accuracy Dashboard (live) |
| Upload → rezultat | <30s | Office Accuracy Dashboard (live, worker time only — doesn't include queue wait or HTTP round-trip) |

- [x] **Accuracy Benchmark harness** — `scripts/intake_accuracy_benchmark.py`,
      runs the real production `classify()`/`extract_all_entities()` (not a
      reimplementation) against `evaluation/lec/` (Legal Evaluation Corpus —
      renamed from `golden_dataset/`, see below), reports per-entity-type
      accuracy, appends to `docs/accuracy_history.json` so every future run
      shows the delta against the last (`git log -p` on that file is the
      accuracy changelog founder asked for). `evaluation/lec/` ships
      **empty on purpose** — populating it with real documents plus
      hand-verified ground truth is the founder's own task, not something
      that can be fabricated and still mean anything. See
      `evaluation/lec/README.md` for the annotation format.
- [x] **Office Accuracy Dashboard** — `GET /api/smart-intake/admin/
      accuracy` (`shared/intake_accuracy.py`), computed live from existing
      `intake_processing_outcomes`/`intake_review_queue`/`extracted_
      entities` — no new migration needed. Honest empty-state below a
      5-document sample size (same discipline as Revenue Intelligence),
      not a number that looks precise before it means anything. Explicitly
      NOT the same claim as the benchmark: this measures operational
      behavior (confidence, corrections, LLM usage, timing), not accuracy
      against ground truth — a confident wrong answer and an honest "not
      sure" both show up differently here than in the benchmark.
- [ ] Per-office breakdown (`kancelarija_id` filter) — plumbing exists in
      `get_office_accuracy_kpis(kancelarija_id=...)` but `intake_jobs.
      kancelarija_id` isn't populated anywhere yet (design review §26.9,
      same known gap noted since Phase 0's upload endpoint) — deferred
      until office-scoped review queues are actually built.
- [ ] Populate `evaluation/lec/` with real documents + run the benchmark —
      **founder's task**, not something to build further from here.

**Golden Dataset v2 (same day, second round of ML-practice feedback):**
one flat dataset with one blended accuracy number hides where the system
actually breaks. Refined before any real documents exist, so the harness
is right from the first real run instead of needing a rework later:

- **Three collections, not one** — `documents/a_clean_digital/` (Word→PDF,
  isolates parser/classification quality from OCR noise),
  `documents/b_typical_serbian/` (scans, stamps, ordinary resolution —
  what actually arrives most days), `documents/c_nightmare/` (deliberately
  hard: cropped/rotated/smudged/handwritten/mixed-script/two-judgments-in-
  one-PDF/phone-photo — the real floor, not the polite case). `dataset` is
  **derived from the subfolder a file lives in**, never typed by hand —
  one less thing to get wrong while collecting under time pressure.
- **`difficulty` field** (easy/medium/hard/nightmare) — a separate axis
  from `dataset` (a Dataset B document can still be easy). Benchmark now
  reports accuracy broken down by both dataset and difficulty tier, not
  one flat average.
- **`annotator`/`reviewed_by`/`agreement`** — founder's insight: "ako se
  dva advokata ne slažu oko roka, onda AI možda nije pogrešio, ground
  truth je pogrešan." Documents with `agreement: false` are reported
  separately, excluded from the headline accuracy number — a disagreement
  between annotators means the ground truth itself is contested, not that
  the extraction failed.
- **`beleska`** (optional) — why a document/value is hard, for dataset
  curation context.
- **`correction_reason`** (migration 074, amended before first run —
  `intake_processing_outcomes.correction_reason`, optional) — when a
  lawyer corrects a field in production, they can now optionally say
  *why* ("datum presude nije rok za žalbu"), not just *what* changed.
  Deliberately optional — a required field would turn the "10-second fix"
  into a form, which would undo Phase 1A's own Definition of Done.

See `evaluation/lec/README.md` for the full annotation schema.

**LEC v1 — Legal Evaluation Corpus rename + Error Source + Stability + Hall
of Shame (same day, third round of founder feedback — evaluation-process
reframe, not a design revision):** Founder's framing: "Više ne gradiš AI
proizvod. Gradiš AI evaluacioni sistem" — and that deserves a name that
signals a versioned product, not a static file.

- **Renamed `golden_dataset/` → `evaluation/lec/`** (git history preserved
  via `git mv`), with `VERSION` (currently `v1`) and `CHANGELOG.md` —
  future meaningful batches of documents/annotations/schema changes are
  LEC v2, v3, etc., recorded there.
- **`error_source`** (optional, both sides) — categorical classification
  of *which layer* is actually at fault: `ocr` / `parser` / `regex` /
  `heuristics` / `llm` / `ground_truth` / `human_annotation` / `unknown`.
  Added to `intake_processing_outcomes` (migration 074, amended before
  first run — same CHECK-constraint taxonomy as the annotation-side
  field) and to the LEC annotation schema for disagreement documents.
  Founder's reasoning: `correction_reason` free text answers "what was
  wrong"; `error_source` answers "where do I actually spend engineering
  time" in an aggregatable way once real volume exists — might be OCR,
  might be the regex, might not be the AI at all.
- **Stability KPI** — `scripts/intake_accuracy_benchmark.py::_stability()`
  computes the single largest per-entity accuracy drop against the
  previous recorded run, surfaced separately from the headline number.
  Founder's point: 96.8% → 96.7% is noise; `deadline` 98% → 84% is a real
  regression a blended average would hide.
- **`evaluation/hall_of_shame/`** — new companion corpus (`README.md` +
  `incidents.json`, ships empty) for documents that didn't just score
  low-confidence but *broke* the system: wrong deadline auto-accepted,
  total OCR failure, >5 manual corrections on one document. Different
  question from LEC ("how accurate on average") — this is "what are the
  specific failures, and did we fix them."
- **Sourcing advice captured in `evaluation/lec/README.md`**: ask 3-5
  offices for ~20 judgments + 20 lawsuits + 10 powers of attorney each
  (~150 total) rather than one office for 300 — diversity of court/style/
  scan quality matters more than raw volume for a trustworthy benchmark.

Still zero new AI functionality — schema, harness, and process only, per
the founder's standing instruction.

## Phase 2 — Living Case
**Goal: case state becomes visible and historical.**

- [ ] `case_dimension_type` lookup table — [ADR-0011](adr/0011-case-dimension-type-as-entity.md)
- [ ] `CaseDimensionChanged` event + `case_dimension_history` — [ADR-0009](adr/0009-configuration-vs-knowledge-state.md), [ADR-0010](adr/0010-case-dimension-changed-envelope.md)
- [ ] Health / Confidence / Completeness projections — [ADR-0015](adr/0015-target-state-scoped.md) (target-state for these two first)
- [ ] State Diff Engine — [ADR-0012](adr/0012-state-diff-debounce.md)
- [ ] Case Evolution UI — [ADR-0013](adr/0013-case-evolution-no-analytics-table.md)

## Phase 3 — Intelligence
**Goal: the harder, higher-payoff signals.**

- [ ] Semantic Deduplication — [ADR-0008](adr/0008-semantic-dedup-entity-overlap.md)
- [ ] Document Lineage — [ADR-0014](adr/0014-document-lineage-confidence-gated.md)
- [ ] Case Memory — [ADR-0006](adr/0006-case-memory-deterministic.md)

## Phase 4 — Automation
**Goal: intake reaches into the rest of the platform.**

- [ ] Reactive fan-out wiring: Case DNA, Health Index, Zastarelost Guardian, Strategija, Profitabilnost AI, Client Twin, Knowledge Graph each subscribe to `DocumentIngested` — design review §7, §26.11
- [ ] Deadline propagation (auto-reminder)
- [ ] Client Twin update trigger
- [ ] Profitability update trigger

## Phase 5 — Optimization

- [ ] Mobile capture surface
- [ ] Windows folder watcher / email adapter
- [ ] Only after real usage data exists: revisit Intent Engine — [ADR-0016](adr/0016-intent-engine-deferred.md) (deferred, not scheduled)

---

*Deferred, not scoped into any phase:* Versioned Facts —
[ADR-0007](adr/0007-versioned-facts-deferred.md).

*Every new AI-driven action added anywhere in this plan gets classified
against [ADR-0017](adr/0017-automation-safety-levels.md) before it ships.*
