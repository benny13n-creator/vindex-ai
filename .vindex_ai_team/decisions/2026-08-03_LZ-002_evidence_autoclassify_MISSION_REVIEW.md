# Mission Review — LZ-002: Auto-trigger Evidence Vault classification

**Mission Board entry:** `MISSION_BOARD.md`, LZ-002, priority 2.
**Executed by:** Operation Lawyer Zero (founder's Master Prompt, BETA-001), 2026-08-03.
**Status:** DONE — **root cause turned out different from, and more valuable than, the original framing.**

---

## Architecture Decision

### Root cause — Smart Intake was already writing the field, with the wrong vocabulary
The Phase 1 inspection framed this as "Evidence Vault's classifier is never auto-triggered." Investigating
before implementing found something more specific and more valuable to fix: `routers/smart_intake.py`'s
finalize path **already writes `tip_dokaza`** on document insert (`:598`), using
`shared/intake_classify.py`'s own coarse document-type classifier (`"lawsuit"`, `"judgment"`,
`"appeal"`, etc.). But `services/risk_engine.py`'s deterministic missing-document detector
(`routers/matter_intel.py`, the platform's sole "next action" algorithm per Core Consolidation)
compares `tip_dokaza` against `shared/constants.py::EXPECTED_DOCS` — keyed on **Evidence Vault's**
vocabulary (`"sudska_odluka"`, `"podnesak"`, `"ugovor"`, etc.). **The field was already being
populated automatically — with values that could never match the comparison reading it.** This is
the exact same defect shape as LZ-001's `vaznost` finding, one field over: two independently-correct
subsystems using different words for the same concept.

### Alternatives considered
- **Just remap Smart Intake's coarse `doc_type` string to Evidence Vault's vocabulary.** Rejected —
  would fix `tip_dokaza` alone, but skip `pravni_elementi`, `ai_tags`, `kljucne_cinjenice` →
  `predmet_dokazi` (the richer enrichment Case Genome's evidence ranking benefits from), leaving
  most of Evidence Vault's value still unrealized.
- **Wire into `services/case_pipeline.py`'s step 1** (`_step_analiza_dokumenata`), as the Phase 1
  inspection suggested. **Investigated and rejected as conceptually wrong**: that step's own
  success/failure marker checks `predmet_istorija` for a `"[Auto-analiza]"` entry — traced to
  `api.py:4564`, a **third, unrelated** feature (the older upload path's free-text case "procena"),
  not Evidence Vault classification at all. Wiring Evidence Vault status into that step would have
  conflated two unrelated systems rather than connecting the right two.
- **Chosen: call `routers/evidence.py::klasifikuj_i_sacuvaj` directly** — an already-built,
  already-correct, already-manually-triggered function (via `/reklasifikuj`) — as a background task
  right after Smart Intake links a new document. Its own `UPDATE` statement correctly overwrites the
  coarse `tip_dokaza` value with the right one and adds the missing enrichment fields. Zero new
  classification logic; the exact `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))`
  pattern already used by `reklasifikuj` is reused verbatim.

### A deliberate design choice, stated explicitly
The auto-trigger does **not** call `UsageService.consume(...)`, unlike the manual `/reklasifikuj`
endpoint. This is a system-initiated background enrichment step, not a lawyer-initiated action —
charging a credit for something the lawyer never explicitly asked for again risked a billing surprise
with no corresponding founder decision authorizing it. Flagged here rather than decided silently.

**Real cost worth naming**: this adds one additional LLM call (GPT-4o-mini) per ingested document,
automatically. Smart Intake's own coarse classifier already makes one such call per document, so this
is not a new *category* of cost, but it does double the LLM-call count per document. Not blocking —
consistent with this whole mission's philosophy — but should be visible if a future cost review happens.

### Security / dependency / workflow review
No schema change, no new dependency. Traced end to end: document linked → background task scheduled
→ `klasifikuj_i_sacuvaj` runs (already-hardened, fail-soft, two independent try/except blocks per its
own 2026-07-19 reliability fix) → `predmet_dokumenti.tip_dokaza`/`pravni_elementi`/`ai_tags` updated,
`predmet_dokazi` rows inserted. Failure of this background task cannot affect the already-returned
finalize response (confirmed by test).

---

## Implementation
`routers/smart_intake.py` — added a background task (`_evidence_classify_bg`) inside
`finalize_intake_job`, scheduled alongside the existing Genome-refresh background task, calling the
existing `klasifikuj_i_sacuvaj` function with the newly-linked document's ID and extracted text.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer uploads a scanned judgment via Smart Intake.
1. Document is OCR'd, classified (coarse), extracted, linked into predmet_dokumenti
   (unchanged, already worked) -- tip_dokaza gets a coarse, wrong-vocabulary
   placeholder value as a side effect of that existing step.
2. In the background, Evidence Vault's real classifier now runs automatically
   (new): tip_dokaza is corrected to the right vocabulary, pravni_elementi/
   ai_tags/kljucne_cinjenice are populated, predmet_dokazi rows are created.
3. The platform's sole deterministic missing-document detector
   (services/risk_engine.py via routers/matter_intel.py) can now actually
   see this document's real type and compare it against what's expected
   for the case type -- previously it could not, for any Smart-Intake-
   ingested document.
4. If this background step fails for any reason, the case and document
   the lawyer already sees are unaffected.

PASS -- tests/test_lz002_evidence_autoclassify.py, both scenarios
(successful classification with exact-argument verification; failure
isolated from the already-returned response).
```

### Regression suite
2 new tests, both passing (one asserts an exact call signature, not just
"was called"). 28/28 across the broader `smart_intake`/`evidence` regression sweep, zero regressions.

### Rollback strategy
Pure application code, one background task added, no schema/migration. Revert to restore (broken)
prior behavior — `tip_dokaza` reverts to being populated with the non-matching coarse vocabulary only.

---

## Lessons Learned
Second time this session a "wire up a disconnected system" mission turned out to be, on inspection,
"a field is already being populated automatically — with the wrong vocabulary" (LZ-001: `vaznost`;
LZ-002: `tip_dokaza`). Worth naming as a pattern for future missions in this family: before assuming a
downstream consumer has *no* signal, check whether it has the *wrong* signal — that's a different,
often cheaper fix (call the right existing function) than building a new trigger from scratch.

## Founder Summary
Fixed the platform's sole deterministic missing-document detector, which was silently blind for every
document ingested through the primary AI-driven upload path — not because nothing ran, but because
the field it reads was already being populated by the wrong classifier's vocabulary. Reused the
existing, already-correct Evidence Vault classifier exactly as its own manual trigger already calls
it; no new classification logic. Deliberately does not consume a billing credit for this automatic
step — flagged as a design choice, not decided silently. One real cost trade-off named explicitly:
one additional LLM call per document, going forward. 2 new tests, zero regressions.
