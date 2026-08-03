# Cognitive Islands Report

**Mission:** Project Synapse, 2026-08-03. Per the founder's Phase 4 rule: any AI/intelligence module
producing knowledge consumed nowhere is a defect. Every orphaned output below is either **connected**
(this mission) or **explicitly documented** (for a future mission/founder decision) — none are left
silently unaddressed.

---

## Islands CONNECTED this mission

### 1. `HEALTH_SCORE_PROMENJEN` — handler existed, never emitted
**Was**: `services/event_bus.py::on_health_score_promenjen` — a complete, working handler that creates
a proactive alert when a case's health score drops below 30 — had zero emit sites anywhere in the
repository, despite `routers/matter_intel.py::get_matter_intel` computing this exact score on every
case-open. **Now**: connected via a new, dedup-guarded background task
(`_maybe_emit_health_and_deadline_events`). Verified with 3 tests, one specifically proving the
mandatory dedup guard (no repeat alert on repeated case-opens while the score stays low).

### 2. `ROK_KRITICAN` — handler existed, never emitted
**Was**: same shape as #1 — a working "critical deadline" alert handler, never triggered. **Now**:
connected from the same Matter Intelligence computation point, using the actual critical-hearing rows
(court name + date) rather than just a count. Required a small, additive extension to
`services/risk_engine.py::calculate_procesni_rizik` (returning the actual rows, not only a count) —
purely additive, verified backward-compatible with existing callers.

**Bug found and fixed while connecting this island**: the date-comparison logic computing which
hearings count as "critical" had a real, pre-existing defect — it compared a timezone-naive datetime
(built from a plain `YYYY-MM-DD` date string) against a timezone-aware `now`, which raises `TypeError`
in Python, silently swallowed by a bare `except: pass`. Every hearing whose `datum` arrived as a plain
10-character date (the realistic shape for a Postgres DATE column) was silently excluded from both
`predstojeći_rokovi` and `kriticni_rokovi` — meaning this signal was very likely always computing as
empty/zero for real production data, not just for the specific island being connected here. Fixed by
comparing calendar dates instead of full datetimes (also more semantically correct — a hearing date has
no meaningful sub-day precision for a day-count check). This is the second time this multi-night
engagement has found that "connecting an island" first requires fixing a pre-existing bug in the
signal the island was supposed to carry — worth treating as a standing expectation for future
propagation work, not a coincidence.

### 3. Duplicated case-strength reasoning — Copilot and Firm Brain now read Case Genome
**Was**: a full audit confirmed **four independent GPT-based case-strength/pattern-synthesis code
paths** existed (Case Genome, the AI Briefing, Copilot's `_handle_analiza_predmeta`, and — via a
different lens — Firm Brain's own case-context construction), with only the AI Briefing reading any of
the others' output. Copilot's case analysis and Firm Brain's similar-case search each independently
re-derived case context from raw rows, blind to a richer, already-computed Genome sitting one column
away for the same case. **Now**: both read `predmeti.case_dna` (when it exists and has no error) and
fold a compact summary into their own existing prompt context — purely additive, no restructuring of
either handler's control flow or output shape. Verified with 5 tests across both files, including
explicit backward-compatibility tests for cases with no Genome yet.

---

## Islands DOCUMENTED, not connected (founder decision or future mission required)

### 4. `DOCUMENT_JOB_ENQUEUED` / `DOCUMENT_JOB_COMPLETED` / `DOCUMENT_JOB_FAILED` — emitted, zero handlers
These fire via the durable-outbox pattern on every Smart Intake upload — the events genuinely happen
and are durably recorded — but no handler is registered for any of the three. `DOCUMENT_JOB_FAILED` is
the most consequential: a failed OCR/classification job today produces zero lawyer-facing or
firm-facing signal, even though proof it happened already exists in the `events` table. **Not fixed
this mission**: unlike items 1-3, this requires writing a genuinely NEW handler (deciding what a
"processing failed" notification should say and to whom), not just wiring an existing one — a small
step past this mission's "prefer orchestration over new code" charter. Flagged as a well-scoped,
low-risk future mission, not guessed at here.

### 5. `knowledge_profiles` — a phantom data source inside the AI Briefing
The Briefing's own `_gather_case_data` reads this table as one of 8 sources; its only writer
(`routers/knowledge_transfer.py`) is confirmed dead code (Operation Invisible Features). This means the
Briefing's `knowledge_profila`/`komunikacioni_profil_dostupan` counts are, in practice, always ~0 for
any real firm — not a bug in the Briefing itself, but a data source that looks real in the code and
structurally cannot produce signal today. **Not fixed this mission**: two real options exist (build a
real extraction pipeline for this table — new AI work, explicitly out of this mission's "do not build
new AI features" charter — or wire the existing dead `knowledge_transfer.py` router's manual-entry UI,
a smaller frontend task closer to this engagement's Beta Closure precedent). Which to pursue is a
founder call, not guessed at here.

### 6. Judge/Court Profiler and Opponent Intelligence — real data, no zero-cost path to auto-populate
Smart Intake already extracts `judge`/`court`/`plaintiff`/`defendant` entities during document
processing, but `finalize_intake_job`'s `predmeti` insert never writes them onto the case's own
`tuzilac`/`tuzeni` columns (confirmed absent, `predmeti.tuzilac`/`tuzeni` columns exist and are used
elsewhere by the CRM wizard's conflict-check). This means Judge & Court Profiler and Opponent
Intelligence still require the lawyer to type a name manually, even when the AI already extracted it in
most cases — first flagged last mission (`WOW-003`), reconfirmed this mission with the same verdict:
a real, small backend change (write already-extracted entities onto existing empty columns), but one
this mission's compose-only charter for its OTHER fixes didn't extend to attempting blind alongside
everything else — kept as its own clearly-scoped future item rather than rushed in.

### 7. Outcome Intelligence and Judge/Court Profiler still don't read Case Genome
Item 3 above connected Copilot and Firm Brain to Genome. Outcome Intelligence and the Judge/Court/
Opponent predictor router were confirmed to have the identical gap (zero references to `case_dna`) but
were NOT fixed this mission — each has its own, more involved prompt-construction logic (statistical
win/loss synthesis, judge-specific tendency analysis) where blending in Genome context safely needs
more careful per-file review than the two fixed this mission. Flagged as the direct continuation of
this mission's own pattern, not a new finding — a future mission repeating exactly the Copilot/Firm
Brain approach on these two files is low-risk and well-precedented.

### 8. Web3/Digital Asset Compliance — confirmed sealed, correctly not an island
Included here only to state explicitly per the mission's own rule ("every orphaned output must be
connected or explicitly documented"): this module's outputs are deliberately not part of the core-legal
reasoning graph, by prior product decision. Confirmed via code (zero references to `predmet_id`/
`case_dna`), not assumed. No action needed or recommended.

### 9. Memory Graph — confirmed still fully dead, unchanged
No new evidence this mission beyond what Operation Invisible Features already established: real query
logic, zero frontend, zero data-writer beyond its own equally-dead manual-entry endpoint. Still
requires a founder decision on data-population strategy before any UI is safe to build — unchanged
recommendation from 2 missions ago.

---

## Summary

| # | Island | Status |
|---|---|---|
| 1 | `HEALTH_SCORE_PROMENJEN` unemitted | **Connected** |
| 2 | `ROK_KRITICAN` unemitted (+ a real date-math bug found underneath it) | **Connected + bug fixed** |
| 3 | Copilot / Firm Brain never read Case Genome | **Connected** |
| 4 | `DOCUMENT_JOB_*` events, zero handlers | Documented — needs a new handler, future mission |
| 5 | `knowledge_profiles` phantom data source | Documented — founder decision needed |
| 6 | Judge/Opponent entities never written to `predmeti` | Documented — small future backend task |
| 7 | Outcome Intelligence / Judge-Court Profiler still don't read Genome | Documented — same pattern as #3, future mission |
| 8 | Web3 sealed module | Documented — confirmed correct, not a defect |
| 9 | Memory Graph | Documented — unchanged, founder decision needed |
