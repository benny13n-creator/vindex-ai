# Classification Architecture Report — Program Intake Sprint 003 (2026-08-05)

**Charter**: "Canonical Document Understanding" — not "can the system read a document" (Sprints 001-002's
question) but "does the system understand what it read." No new OCR, no new LLM models, no Genome changes, no
new AI capabilities. Build one canonical document-understanding system that becomes the single source of
truth for the whole platform.

**Active team**: Chief Systems Architect, Legal Domain Expert, Evidence & Consistency Auditor, Reliability &
Failure Recovery Engineer, Code Quality/Refactoring Reviewer. All other roles STANDBY — narrower even than
Sprint 001/002's 5-agent pattern (no Security/Compliance/Performance/UX/Metrics/Strategy/Copilot/Search/
Dashboard/Firm Brain/Memory Graph/Alerts/Timeline/Decision Engine/Voice/Analytics/Documentation Review).

**Forbidden to implement**: Timeline, Deadlines, Tasks, Alerts, Genome extensions, Briefing, Copilot,
Decision Engine, Search, Firm Brain. Findings there are documented, not fixed.

**Mission's own success framing, repeated because it governs every decision below**: *"Ne optimizuj za broj
automatski klasifikovanih dokumenata. Optimizuj za tačnost i poverenje."* (Don't optimize for the count of
auto-classified documents. Optimize for accuracy and trust.)

## 0. Method

Three parallel read-only forensic forks: (A) repo-wide classification inventory + duplicate detection
(Chief Systems Architect + Code Quality/Refactoring Reviewer lens); (B) canonical legal taxonomy + confidence
model design (Legal Domain Expert + Evidence & Consistency Auditor lens); (C) review queue behavior audit +
edge case validation (Reliability & Failure Recovery Engineer lens). Full outputs: `.vindex_ai_team/
decisions/2026-08-05_intake_sprint003_fork_*.md`.

## 1. The central finding, in one sentence

**The platform has 5 independent AI document classifiers (not 4, as prior sessions tracked), only 1 of which
has a genuine confidence-gated escape hatch — and even that one classifier's correctly-flagged uncertainty was
being silently erased by a second, confidence-blind classifier before a lawyer could ever see it.** Full
detail: `CLASSIFICATION_INVENTORY.md` (the 5 classifiers), `REVIEW_QUEUE_SPECIFICATION.md` (the erasure
mechanism and this sprint's fix).

## 2. What this sprint designed (not yet fully adopted in code)

- **`CANONICAL_DOCUMENT_TAXONOMY.md`**: 10 parent categories, reconciling all 4 existing AI-classifier
  vocabularies + the founder's own starting example, with a full mapping table and every edge-case judgment
  call explicitly justified (not hand-waved) — including a genuine correction to a pre-existing defect in
  `intake_classify.py`'s own `enforcement` keyword list (conflates a party petition with a court order).
- **`CONFIDENCE_SPECIFICATION.md`**: a `baseline + Σ(deterministic factors) → clamp` confidence model, the
  platform's 4th confirmed instance of `CONFIDENCE_MODEL_SPECIFICATION.md`'s already-proven pattern, closing
  `EVIDENCE_CHAIN_REGISTRY.md` row #5 (previously **Broken**) with a concrete design. Explicitly rejects
  trusting raw LLM self-reported confidence anywhere.

Both are genuinely large designs whose full adoption (a schema migration widening the CHECK constraint,
rewiring 5 classifiers to one canonical engine) is correctly out of this sprint's bounded-implementation scope
— see `CANONICAL_DOCUMENT_TAXONOMY.md` §6 for the handoff path. This mirrors Sprint 001/002's own established
discipline: design the destination precisely, implement only what's safely bounded now, defer the rest with
named reasoning.

## 3. What this sprint fixed (bounded, tested, zero regressions)

Both fixes target the single sharpest, most severe finding across all 3 forks — Fork C's headline finding that
the platform's forbidden "third state" (silently guessed) was reasserting itself inside the *one* pipeline
that was supposed to prevent it:

1. **Pipeline C finalize no longer lets a confidence-blind classifier silently overwrite an already-flagged-
   uncertain classification.** `result["review"]` (previously fetched, never read) now gates whether the
   `_evidence_classify_bg` vocabulary-correction task runs. When Pipeline B's `document_type` was below
   `AUTO_ACCEPT_THRESHOLD`, that task is skipped — Pipeline B's own honest, low-confidence value survives
   instead of being replaced by an equally unfounded but more-confident-looking second guess. The finalize
   response now always includes `klasifikacija_nesigurna`/`nesigurna_polja`, making Review Required a visible
   state at the moment a lawyer is actually looking, not buried in an endpoint nobody revisits.
2. **`GET /jobs/{job_id}` no longer silently presents a stale, contradictory classification as current.**
   Fork A confirmed a live, permanent, two-different-Serbian-labels defect: this endpoint kept serving
   Pipeline B's pre-overwrite English-vocab value indefinitely after finalize, and the frontend's own
   hardcoded translation map showed it to the lawyer during Smart Intake's review step — permanently
   disagreeing with the real value later shown in Evidence Vault. The endpoint now flags `tip_moze_biti_
   zastareo: true` with an explanatory note once finalized, rather than presenting a possibly-superseded
   value as ground truth. A full reconciliation (showing the actual current value) is blocked on the missing
   `intake_job_id` FK (`INTAKE-003`, unchanged) — honest disclosure was chosen over a fragile matching
   heuristic.

Both fixes are regression-tested: `tests/test_sprint003_classification_review_required.py` (5 new tests) plus
updates to 3 pre-existing finalize test files whose hand-rolled `job_result` mocks needed a `"review"` key to
match the real function's contract. Full suite: 2517 passed, 1 skipped, 0 failed (was 2512 going in).

## 4. What this sprint deliberately deferred (with reasoning)

- **`INTAKE-008`**: full confidence-gated review queue for Pipeline A and the 2 ephemeral classifiers (which
  never had one at all). Requires the full Confidence Specification actually implemented, not just consumed —
  a genuinely large change, correctly out of this sprint's bounded scope.
- **`INTAKE-009`**: `/reklasifikuj`'s concurrency defect (no lock, a double-click races itself). Real,
  code-level, model-independent — but lower frequency (an admin/manual action) than Sprint 002's finalize race
  was, and the proper fix (an atomic claim, mirroring `claim_intake_finalize`) was deprioritized behind this
  sprint's higher-severity finding.
- **`INTAKE-010`**: no cross-row classification-consistency check exists for same-hash duplicate uploads.
  `source_sha256` is computed at 3 sites, queried back at zero. A real reconciliation capability, not a
  bounded patch.
- **`INTAKE-011`**: Phase 7's edge-case findings (full detail below, §5) — rotation detection, multi-document/
  combined-"spis" PDF handling, OCR-confidence-to-classification-confidence decoupling. Explicitly OCR-adjacent
  (the mission says "ne rešavati OCR, dokazati ponašanje" — prove behavior, don't fix OCR) — documented, not
  implemented.
- **Not re-litigated, correctly unchanged**: `INTAKE-003` (the missing `predmet_dokumenti`↔`intake_jobs` FK,
  the root cause blocking a full fix to finding #1 above) — already correctly deferred by Sprint 001 as a
  founder/product schema decision.

## 5. Phase 7 — Edge Case Validation summary

Full detail and code citations: `.vindex_ai_team/decisions/2026-08-05_intake_sprint003_fork_review_queue_edge_cases.md`
§Phase 7. Legend: **CONFIRMED DEFECT** (confident-looking wrong answer, no escape hatch, provable from static
code) · **CONFIRMED ACCEPTABLE DEGRADATION** (already degrades honestly) · **GENUINELY UNKNOWN** (needs a
real-file test, not answerable from code alone).

| Scenario | Verdict |
|---|---|
| Scanned judgment: OCR confidence → classification confidence | **CONFIRMED DEFECT** — `ocr_confidence` is a hardcoded `0.6` constant, not a real measurement; never fed into the classifier at all |
| Badly-scanned/noisy document | **MIXED** — no pre-classification quality gate exists (confirmed); the LLM's actual behavior on garbled input is genuinely unknown |
| Rotated-page scan | **CONFIRMED DEFECT** — zero rotation/orientation detection anywhere in the extractor |
| Multi-document combined PDF (lawsuit + exhibits) | **CONFIRMED DEFECT, most concretely provable** — every classifier reads only the head of the whole-file concatenated text; no document-boundary concept anywhere in the data model |
| Incomplete document (missing pages) | **CONFIRMED ACCEPTABLE DEGRADATION for classification** (head-only reading is unaffected); a real but out-of-scope gap for extraction completeness |
| Blank pages mixed into a scan | **SPLIT** — OCR path filters gracefully (acceptable); born-digital page-count-average calc can misfire into unneeded OCR (narrow confirmed defect) |
| Handwritten notes on printed document | **CONFIRMED DEFECT** — no mixed-content awareness; same fake-constant confidence issue as the OCR-confidence finding |
| "Combined spis" (Serbian-practice case-file bundle) | **CONFIRMED DEFECT** — identical mechanism to the multi-document PDF finding, Serbian-practice framing |

**Not fixed this sprint, by explicit charter instruction** — "Ne rešavati OCR" — these are documented as
`INTAKE-011` for whichever future sprint is scoped to touch OCR/extraction quality.

## 6. Mission closure self-check

- One canonical classification method exists → **Designed** (`CANONICAL_DOCUMENT_TAXONOMY.md`), **not yet
  adopted** — 5 classifiers still run independently in production. Honestly reported as designed-not-
  implemented, matching this session's established discipline for distinguishing the two.
- No competing classifications → Not yet true — the classifier race (`ALPHA-003`) is unchanged this sprint;
  only the sharper, silent-overwrite-of-an-already-uncertain-value defect within it is fixed.
- Every document has confidence → Not yet true platform-wide — only 1 of 5 classifiers computes one.
- Every document has a classification reason → Not yet true platform-wide — same gap.
- No document auto-misclassified when confidence is low → **True for the one path that had confidence data
  and was being defeated — fixed this sprint.** Not true where no confidence data ever existed.
- Review queue works as the sole alternative → **True where it existed and reachable, now also true where
  its signal was being erased downstream — fixed this sprint.**
- All tests pass without regressions → **True** — 2517 passed, 1 skipped, 0 failed.

This sprint closes honestly as: **the taxonomy and confidence model are fully designed and ready to adopt; the
single most severe active defect (an already-correct uncertainty signal being silently destroyed) is fixed and
regression-tested; full platform-wide adoption of one canonical classifier is deliberately deferred as the
large, multi-fix undertaking it genuinely is, not attempted piecemeal in a way that would risk introducing new
inconsistency while claiming to remove it.**
