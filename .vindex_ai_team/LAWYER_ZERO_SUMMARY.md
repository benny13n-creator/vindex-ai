# LAWYER_ZERO_SUMMARY.md

**Mission:** Operation Lawyer Zero (BETA-001), 2026-08-03. Founder's Master Prompt.
**Mode:** all commits local only, per explicit instruction — nothing pushed.
**Final state:** full test suite — **2289 passed, 1 skipped, 0 failed** (270s runtime).

---

## Completed missions

| # | Mission | Outcome |
|---|---|---|
| Phase 1 | Repository-wide forensic inspection (notifications, calendar, tasks, knowledge base, evidence, missing-document detection, background jobs, search visibility) | **DONE**, read-only. Found the two highest-value findings of the whole mission: a real, already-scheduled email reminder cron that has never fired for an AI-extracted deadline, and the platform's sole deterministic missing-document algorithm starved of a real signal for every Smart-Intake-ingested document. |
| Phase 2 | `docs/product/LAWYER_AUTOMATION_MAP.md` | **DONE.** Every workflow step from the founder's own human-workflow description mapped to current implementation status, with effort/risk/value/reuse-% per row, grounded in file:line evidence. |
| LZ-001 | Fix `vaznost` vocabulary mismatch so AI-extracted deadlines trigger the automatic email reminder | **DONE.** Investigating before implementing found the vocabulary problem is bigger than scoped (≥6 distinct values, not 2-3) and that `api.py` already has logic depending on one of the "wrong" values (`"bitan"`) being real. Fixed only the safe subset (broadened the cron's read-side filter, touched zero writers); flagged the full unification as `LZ-005`. |
| LZ-002 | Auto-trigger Evidence Vault classification on document ingestion | **DONE.** Root cause turned out different from the original framing: Smart Intake was already writing `tip_dokaza`, using the wrong classifier's vocabulary — the missing-document detector's comparison could never match. Investigated wiring into Case Pipeline step 1 (as Phase 1 suggested) and found that step checks an unrelated marker from a third, different feature — redirected to the correct fix: call the existing `klasifikuj_i_sacuvaj` as a background task on Smart Intake finalize. |
| LZ-003 | Extend global search to cover tasks + evidence type | **DONE.** Found `zadaci` has no `user_id` column at all (only `kreirao_uid`/`dodeljen_uid`/`kancelarija_id`) — copying the other 6 search branches' pattern verbatim would have been a tenant-isolation bug. Scoped to the provably-safe subset. |

**Not attempted, explicitly, with reasons** (postponed per the master prompt's own instruction, not
silently dropped):
- **LZ-004** (convert AI "missing document" findings into `zadaci` tasks) — needs a founder-level
  decision (auto-create silently vs. propose-then-confirm), the same class of question `M-005` raised
  the prior night for deadline chains. Marked `NEEDS_SCOPING`, not guessed.
- **LZ-005** (full `predmet_hronologija.vaznost` vocabulary unification across every writer and
  reader) — real, found during LZ-001, deliberately deferred pending a full reader audit this
  session's remaining time didn't safely allow.
- **Multi-event chronology extraction** (`M-004`) — unchanged from the prior night's assessment; still
  genuinely large, new NLP design work, not a "connect existing components" task.

---

## Connected components (Rule Zero — what was wired, not built)

| Existing, working component | Was disconnected from | Now connected to |
|---|---|---|
| `email_notif.py::posalji_podsetnike` (daily cron, real SMTP send, real dedup) | Every AI-extraction deadline-writing path | Broadened read filter — zero new sending logic |
| `routers/evidence.py::klasifikuj_i_sacuvaj` (real LLM classifier, already used by the manual `/reklasifikuj` action) | Document ingestion (Smart Intake finalize) | Now fires automatically as a background task, exact same function, same call pattern |
| `routers/search.py`'s existing 6-type search pattern | Tasks (`zadaci`), evidence type (`tip_dokaza`) | Extended to 7 types, safely re-scoped for `zadaci`'s different schema |

No new systems were built. Every fix tonight was a connection, a filter broadening, or a background
task added — consistent with Rule Zero and the founder's own quality principle ("impress me by making
lawyers work less tomorrow morning," not with new architecture).

## New capabilities
None, strictly speaking — and that is the point of tonight's work. Every fix made an *existing,
already-built* capability actually reach the case data the AI pipeline actually produces.

## Beta blockers removed
3 sub-capability gaps closed within already-tracked Beta Critical Path scenarios (see `METRICS.md`
for the precise, non-inflated accounting): automatic deadline reminders now fire for AI-extracted
deadlines; the missing-document detector now has a real signal for AI-ingested documents; global
search now covers tasks and evidence type.

## Remaining blockers
- `LZ-004` — needs founder product/risk decision before it's a safe mission.
- `LZ-005` — needs a full reader audit of `predmet_hronologija.vaznost` before any writer can safely
  change.
- Everything already tracked as `NEEDS_SCOPING` from the prior night (`M-004`, `M-007`, `M-008`,
  `M-011`) is unchanged — not reassessed this run, no new evidence gathered for them.

## Engineering debt discovered
- **`predmet_hronologija.vaznost`**: at least 6 distinct spellings/values across 3 writers, a DB
  `CHECK` constraint that may or may not be enforced live (unverifiable from this environment — no
  live DB connection available), and at least 2 readers already compensating for the inconsistency in
  different, incompatible ways.
- **Three genuinely separate "analyze this document" mechanisms** now confirmed to coexist:
  `shared/intake_classify.py` (coarse document type), `routers/evidence.py` (rich legal
  classification), and `api.py`'s older upload path's free-text "procena" (assessment) written to
  `predmet_istorija` with an `"[Auto-analiza]"` marker that `services/case_pipeline.py`'s step 1
  actually checks — a real, if minor, source of confusion for anyone reading that step's name and
  assuming it means Evidence Vault classification status (it does not).
- **Duplicated `_verify_token`-adjacent classification writes**: Smart Intake's finalize inserts
  `tip_dokaza` once with the wrong vocabulary (as a side effect of an unrelated document-linking
  step), then LZ-002's new background task overwrites it correctly a moment later — functionally
  fine (fail-soft, eventually consistent) but worth noting as a slightly awkward two-step write
  rather than a single correct one, if this code is revisited.

## Repository health
2289 passed, 1 skipped, 0 failed, full suite. 3 commits this run (LZ-001, LZ-002, LZ-003), each
scoped to exactly one mission. No schema/migration changes. No new third-party dependencies.

## Lawyer Experience Review (Phase 5)

Walking the workflow as a lawyer would, focused on what changed tonight specifically — the founder's
own measure ("how many clicks did the lawyer save," not "how much code did we write"):

- **Before tonight**: a lawyer whose client's deadline was extracted automatically by Smart Intake or
  the primary AI-assisted case-creation flow would receive **zero automatic email reminders**, ever —
  the entire "automatic reminder" promise silently didn't apply to the deadlines the AI pipeline
  itself creates. The lawyer had to notice the deadline manually in the chronology view, with no
  proactive nudge. **After tonight**: the same 7/3/1-day-out email reminders that already worked for
  template-created deadlines now work identically for AI-extracted ones. Zero new lawyer action
  required — this is a pure removal of a silent gap, not a new step for the lawyer to learn.
- **Before tonight**: the platform's own "what's missing from this case" feature had no real signal
  for any document uploaded through Smart Intake — a lawyer opening a case's risk/next-action view
  could be shown an inaccurate "missing" list for a case with a document already sitting right there,
  unclassified. **After tonight**: correctly classified in the background, no lawyer action required.
- **Before tonight**: finding a task required opening the tasks screen specifically; finding a
  document by its legal type (not exact wording) wasn't possible via search at all. **After tonight**:
  one search box covers 7 types instead of 6, removing one specific "open another screen" step for
  two of the ten manual actions the founder's own workflow description named.

**Not changed tonight, named explicitly rather than left implicit**: uploading, renaming, and
connecting files (already mostly automatic per the prior night's work); manually entering chronology
beyond one deadline per document (still manual for anything beyond the single extracted date — this
is `M-004`, correctly not attempted blind); manually creating tasks from AI findings (this exists as
`LZ-004`, pending a founder decision).

## Recommended next mission
**Bring `LZ-004`'s and `LZ-005`'s open questions to the founder directly** — both are the kind of
question this mission's own discipline says shouldn't be guessed at. Engineering-wise, the next
eligible `TODO` on the board per priority is `M-009` (Workflow Regression Tests), unchanged from the
prior night's recommendation and still not started.

## Time saved for lawyers
Not independently measured this run (no production usage data available in this environment) —
stated qualitatively per the Lawyer Experience Review above: the two `LZ-001`/`LZ-002` fixes remove
silent failures a lawyer would otherwise never know to look for (a missing reminder, an inaccurate
missing-document list), rather than removing a click from a workflow the lawyer consciously performs.
This is a meaningfully different kind of value than "fewer clicks" and is named as such rather than
forced into a clicks-saved number that would be invented, not measured.

## Estimated Beta Readiness
Net positive, same category as the prior night's assessment: reliability and trustworthiness of
already-built automation, not new capability. The two highest-value fixes (`LZ-001`, `LZ-002`) both
close *silent* failures — the kind a lawyer using the beta would never report as a bug, because
nothing looked broken, it just quietly never worked. Closing silent failures before a beta cohort
encounters them is precisely the kind of work most likely to prevent an early user's first
impression being "the AI stuff doesn't seem to do much," when the underlying features were real all
along.
