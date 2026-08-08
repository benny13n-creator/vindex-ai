# Phoenix Closure — Ledger

**Date**: 2026-08-08
**Scope**: the 20 items left non-FIXED by Program Phoenix's Final Certificate — 8 PARTIALLY FIXED
(`-003, -011, -012, -022, -036, -038, -041, -046`) and 12 OPEN (`-005, -014, -020, -023, -025,
-026, -028, -030, -035, -039, -042, -049`).

**Method**: every item below was re-investigated against CURRENT code (not the register's prior
prose) before any disposition was assigned. Several items previously classified as blocked turn
out to have existing idempotency keys, existing admin tooling, or existing-but-hardcoded values
that make them technically resolvable now — this is disclosed explicitly per item, not silently
folded into "fixed."

---

## PARTIALLY FIXED items (8)

### `-003` — CIO 40-case portfolio cap + ordering

- **Original**: `LAWYER_DAY_SIMULATION.md`. CIO's portfolio report caps at 40 active cases.
- **Already fixed** (Mission 014): `ukupno_u_bazi`/`truncated` disclosure.
- **Current state**: `routers/cio.py:265` — `.order("updated_at", desc=False).limit(40)`: fetches
  the 40 **least-recently-updated** (stalest) cases, not most-recent or highest-risk.
- **Disposition: B — PRODUCT DECISION.** Cap size is a genuine query-cost tradeoff. Ordering is a
  separate, real question — "stalest-first" is a surprising default, but changing it (to
  recency-first? risk-first?) is itself a choice about which biased subset to show, not an
  objective bug fix. Not invented here.
- **Verification method (once decided)**: would need a new regression test asserting the chosen
  order field.

### `-011` — Case Evolution consequence duplicate-on-reclaim (3 remaining executors)

- **Original**: `MULTI_DAY_SIMULATION.md`. Already fixed for `timeline_entry` (Mission 007, recent-
  window dedup). 3 sibling executors in `services/case_evolution.py` still lack the same guard.
- **`genome_refresh`** (`case_evolution.py:239-279`): calls `_run_genome_background`, which (via
  `_do_genome_refresh`, `routers/case_dna.py:768`) writes exactly one `predmet_genome_history` row
  per successful refresh with a `trigger_event` column already carrying the caller's trigger
  string (`case_dna.py:511-529`). **Disposition: A — TECHNICALLY RESOLVABLE.** Query
  `predmet_genome_history` for `(predmet_id, trigger_event=trigger)` within
  `_CONSEQUENCE_STALE_PENDING_SECONDS`; if found, skip the recompute and return that row's known
  verzija instead of re-triggering a 2nd (non-deterministic, GPT-costly) refresh. No migration —
  reuses an existing column. The register's original "needs a schema-level snapshot" framing
  predates this column being confirmed usable this way.
- **`review_confirmation_audit`/`review_rejection_audit`** (`case_evolution.py:358-410`): both call
  `shared/audit_immutable.py::log_action`, an append-only hash-chained insert with `action` +
  `resource_id` columns already present. **Disposition: A.** A duplicate append within the reclaim
  window is safe to skip (skipping never touches prior hash-chain entries — only a decision not to
  append a redundant one). Add the same recent-window check (`action`, `resource_id`, recent
  `created_at`) before calling `log_action`.
- **`case_intelligence_summary`** (`case_evolution.py:546-664`): the inserted row already carries
  `"event_id": event.event_id` (line 631) — the EXACT durable event that produced it.
  **Disposition: A.** Check `case_intelligence_summaries` for an existing row with this precise
  `event_id` before inserting; return its `id` if found. More precise than a time-window heuristic,
  and needs no migration — the register's "needs a UNIQUE migration" framing is superseded by this
  exact-match check being sufficient at the application level (same TOCTOU caveat already accepted
  throughout Phoenix for human-retry-triggered, not high-frequency, paths).

### `-012` — cooldown_seconds near-universal absence + TOCTOU

- **Original**: `CHAOS_RESULTS.md`. TOCTOU sub-item already FIXED (Mission 012, atomic conditional
  claim). Remainder: ~57 of ~60 `feature_registry` rows have no `cooldown_seconds` value.
- **Current state**: `routers/admin_dashboard.py:411-529` — a founder-gated Admin Feature Console
  (`PATCH /feature-registry/{feature_key}`) ALREADY supports setting `cooldown_seconds` per feature
  live, no migration, no deploy, cache-invalidated immediately.
- **Disposition: B — PRODUCT DECISION, corrected framing.** The register's "requires a migration"
  characterization is factually superseded — no schema change is needed at all. What remains is
  genuinely a **business judgment call per feature** (how long should each of ~57 different
  features' cooldown be — these are not interchangeable), which this operation has no authority to
  invent, exercised through infrastructure that already exists. This is a correction to the
  register, not a new fix.

### `-022` — Evidence classification confidence gate (review-queue UX)

- **Original**: `CHAOS_RESULTS.md`. Confidence gate itself fixed (Mission 006,
  `ai_tags["_klasifikacija_pouzdanost"]` enum-guarded). Remainder: no accept/reject review-queue UX
  for low-confidence classifications.
- **Current state**: `static/vindex.js:18230-18242` already renders a "Reklasifikuj" button per
  document — the ACTION already exists. `ai_tags["_klasifikacija_pouzdanost"]` is computed and
  persisted (`routers/evidence.py:99-103`) but never rendered anywhere in the frontend — a lawyer
  has no visual signal for which documents deserve a second look.
- **Disposition: A — TECHNICALLY RESOLVABLE (narrower than full parity with Smart Intake).** Add a
  ⚠ badge next to `tip_dokaza` when `ai_tags._klasifikacija_pouzdanost === 'niska'`. This doesn't
  build a full accept/reject workflow (that remains a bigger, separate product decision if ever
  wanted) — it makes the ALREADY-COMPUTED signal visible next to the ALREADY-EXISTING action
  button, closing the practical "lawyer has no way to know" gap.

### `-036` — Archived-case data hygiene (orphaned `case_actions` rows)

- **Original**: `LAWYER_DAY_SIMULATION.md`. Visibility fixed (Mission 001). Remainder: closing a
  case never closes its `case_actions` rows in the DB.
- **Current state**: `routers/predmeti_close.py::zatvori_predmet` (~lines 90-213) updates
  `predmeti.status`, writes a `predmet_hronologija` audit row, fires a benchmark contribution — but
  never touches `case_actions`.
- **Disposition: A — TECHNICALLY RESOLVABLE.** Add a best-effort bulk
  `case_actions.status='closed'` update for the closed predmet's open rows, alongside the existing
  hronologija insert (same non-blocking try/except pattern already used there). Reuses the existing
  `status` column `workspace.py` already reads. Also apply to the archiving path if it's a separate
  code branch.

### `-038` — `_aggr_events` (kalendar) cap/degradation disclosure

- **Original**: `LAWYER_DAY_SIMULATION.md`. Archived-case leak fixed (Mission 001). Remainder:
  200-row cap with no truncation signal, `return_exceptions=True` with no degraded flag.
- **Current state**: `routers/kalendar.py::_aggr_events` (~lines 54-150) — both `rocista` and
  `predmet_hronologija` queries `.limit(200)`, no truncation signal; `return_exceptions=True`
  (~line 79) swallows a real exception with no `degraded` flag in `kalendar_pregled`'s response
  (~lines 176-181).
- **Disposition: A — TECHNICALLY RESOLVABLE.** Mechanically identical to the pattern already
  proven twice (Mission 014's CIO `truncated`, Mission 015's Timeline `degraded_sources`): add
  `count="exact"` queries for the truncation signal, a `degraded_sources` list for the exception
  case.

### `-041` — Upload timeout (remaining sites) + progress indicator

- **Original**: `LAWYER_DAY_SIMULATION.md`. App-level timeout fixed for the primary upload flow
  (Mission 013, `_fetchWithTimeout`, 90s `AbortController`).
- **Current state**: `static/vindex.js` has 9 total `FormData()` upload call sites (lines 4041,
  4664, 5294, 8598, 13289, 14705, 19517, 20506, 21011) — only 19517 (`pred_upload_doc`) uses
  `_fetchWithTimeout`. The other 8 are raw `fetch()`, no timeout.
- **Disposition: A — TECHNICALLY RESOLVABLE (timeout half).** Mechanical swap to the existing
  helper at each of the 8 remaining sites. **Progress-indicator half stays B/deferred** — a real
  visual progress bar (`XMLHttpRequest.upload.onprogress`) is a UI feature needing design
  investment beyond this operation's bounded-fix mandate; not attempted.

### `-046` — CIO `/daily` pays GPT cost before losing the claim race

- **Original**: `CHAOS_RESULTS.md`. `/run` fixed with a 2-step claim (Mission 012). `/daily`'s own
  residual: every concurrent requester still pays the GPT compute cost before the claim check.
- **Current state**: `routers/cio.py::cio_daily` (~lines 506-622) — `_generiši_cio_izvestaj` (GPT
  call, ~line 585) runs unconditionally, even for the branch that ultimately loses the claim
  (~lines 591-599). The existing comment there frames this as intentional (a losing request still
  gets a real report, not an error).
- **Disposition: A — TECHNICALLY RESOLVABLE, implemented conservatively.** Mission 012 already
  built a bounded-timeout `asyncio.Event`-based coalescing primitive for exactly this
  "wait for the in-flight winner instead of doing redundant expensive work" shape
  (`case_dna.py::_genome_refresh_done_event`, `_GENOME_COALESCE_WAIT_TIMEOUT`). Reusing the same
  pattern for `/daily`: a losing claim attempt waits (bounded) for the winner's write and returns
  its report instead of generating its own — a strict improvement (same guarantee of "always get a
  real report," without the redundant GPT cost), not a UX regression, with the existing timeout
  fallback preserving pre-fix behavior if the wait ever times out.

---

## OPEN items (12)

### `-005` / `-030` — SW force-reload / zero unsaved-work warning (tracked together, same root cause)

- **Current state**: `static/vindex.js:15964-15969` — `controllerchange` handler unconditionally
  reloads. Zero existing dirty-tracking anywhere in the file (confirmed by exhaustive grep).
- **Disposition: A — TECHNICALLY RESOLVABLE, narrowly scoped.** A single `window._hasUnsavedWork`
  flag + a `beforeunload` listener + a check inside the `controllerchange` handler (defer reload if
  flag true) needs no persistence and no new architecture. Scoped ONLY to the 2 flows the original
  finding named (Intake Wizard, drafting textarea) — not "any form sitewide," which would be scope
  creep beyond the reproduced finding.

### `-014` — Extraction prompts' `""` defeats `[FIELD — POPUNITI]` placeholder fallback

- **Current state**: `drafting/router.py:187-211` (`_popuni_sablon`). Line 190-191's own docstring
  states current behavior is INTENTIONAL: an empty string is treated as valid, not replaced.
- **Disposition: C — INFRASTRUCTURE/DESIGN DEPENDENCY, confirmed genuinely blocked.** Flipping the
  empty-string handling globally risks turning every GPT-correctly-blank field (fields that
  genuinely don't apply to a given case) into an ugly, incorrect placeholder — across ~12 templates
  simultaneously. Distinguishing "genuinely missing" from "correctly blank" per field cannot be
  inferred from this one function; it requires the same per-template/per-field classification pass
  the register originally named. Not attempted — this would be inventing an unsafe blanket
  behavior change to close a debt item, which this operation explicitly forbids.

### `-020` — No duplicate-content detection on Pipeline A's main upload endpoint

- **Current state**: `api.py:4399` (`predmet_upload_auto_analyze`). A content hash is ALREADY
  computed: `api.py:4536` — `"source_sha256": hashlib.sha256(raw).hexdigest()`, persisted into
  `predmet_dokumenti` at insert (~line 4614/4616).
- **Disposition: A — TECHNICALLY RESOLVABLE.** Query `predmet_dokumenti` for an existing
  `source_sha256` match (scoped to `user_id`) before/alongside the insert; add a non-blocking
  `"mozda_duplikat": true` field to the response — purely informational, zero upload-behavior
  change, no product decision invented (mirrors the disclosure-not-block pattern already used
  repeatedly this program).

### `-023` — No OCR quality/confidence signal

- **Current state**: `requirements.txt` confirms `pytesseract` already a dependency.
  `uploaded_doc/extractor.py::_ocr_image` (~line 104) uses `image_to_string` only (bare text, no
  confidence). Separately, `shared/intake_worker.py` (lines 233, 286, 399) ALREADY threads an
  `ocr_confidence` parameter through to `shared/intake_documents.py`'s persisted `intake_documents`
  table (line 39/50/99/154) — but every call site hardcodes it to a fixed `0.6`/`0.0` placeholder,
  with an explicit existing comment disclosing this as a known limitation ("OCR bez eksplicitnog
  skora danas — konzervativna fiksna vrednost dok extractor ne vraća pravi confidence").
- **Disposition: A — TECHNICALLY RESOLVABLE, scoped to the Smart Intake pipeline.** Switch
  `_ocr_image` to `pytesseract.image_to_data`, compute a real mean word-confidence score, thread
  the real value through `extract_pdf`/`extract_image`'s return shape into `intake_worker.py`'s
  existing `ocr_confidence` parameter, replacing the hardcoded placeholders. No migration — the
  persistence column already exists. Aggregation strategy (mean word confidence, excluding
  unrecognized/-1 words) is an engineering default, not a business decision, consistent with how
  every other Phoenix mission has picked its own bounded constants (30s windows, 15s timeouts,
  etc.) without founder sign-off. Pipeline A's (`routers/dokument.py`/`api.py`) separate OCR path
  has no equivalent persisted confidence column — left out of scope, named as a future extension.

### `-025` — Disclosure-label inconsistency across the 4 AI surfaces

- **Current state**: `shared/commander_schema.py` confirmed genuinely bespoke (90 lines,
  `{value, source, evidence, confidence, generated_by, timestamp}`) — full retrofit onto 3
  unrelated endpoints remains correctly out of bounded-fix scope (Mission 015's own finding
  stands). Digital Twin's/Court Predictor's/hearing_cc's response shapes are flat dicts with zero
  provenance metadata at all — not even a minimal marker.
- **Disposition: A — TECHNICALLY RESOLVABLE, narrow version only.** Add ONE additive top-level key
  (`"ai_generated": true`) to each of the 3 endpoints' existing response shape — zero existing key
  touched, zero contract break, does not achieve full Case Commander parity but closes the binary
  "can a user tell this is AI-advisory at all" gap.

### `-026` — Digital Twin/Court Predictor recommendations never cross-checked against `case_actions`

- **Current state**: `shared/case_context.py:414` already computes
  `top_action = top_open_action(raw["case_actions"])` for every `build_case_context()` call, but
  only exposes a derived `top_action_dedupe_key` inside `audit_metadata` (line 558) — the full
  object is computed and then thrown away before reaching the response. Digital Twin/Court
  Predictor already fetch `case_context` for their own readiness-cap logic.
- **Disposition: A — TECHNICALLY RESOLVABLE, disclosure-only (not reconciliation).** Add a
  `"top_open_action"` key to `case_context.py`'s own return dict (additive, same pattern as its
  sibling fields). Digital Twin/Court Predictor surface it as read-only informational context next
  to their own AI-generated recommendation — a human can see both and judge for themself; this does
  NOT invent the reconciliation mechanism the register correctly said would be unsafe to guess at.

### `-028` — No server-side cooldown/dedup on drafting GENERATION itself

- **Current state**: `nacrt()`/`podnesak()` (`routers/drafting.py:557`, `:715`) route through
  `UsageService.consume`, genuinely blocked on `-012`'s unseeded `cooldown_seconds` for THAT
  mechanism. But `-028`'s actual concern (wasting an expensive GPT call on a user-triggered retry)
  is a SEPARATE gap `-012` doesn't touch: `_stage_draft_for_review` (same file) already added a
  recent-duplicate check against `staging_memory` (`-031`, Mission 015) — but only AFTER the GPT
  call, guarding just the staging insert.
- **Disposition: A — TECHNICALLY RESOLVABLE, reclassified.** Move the identical recent-duplicate
  check to the TOP of `nacrt()`/`podnesak()`, before the GPT call fires — reusing the existing
  `staging_memory` table (no migration), scoped identically to `-031` (only when `predmet_id` is
  set; the case-less/ad-hoc path is intentionally left alone). This is independent of `-012`'s
  migration-blocked cooldown mechanism.

### `-035` — Stale `window._predFull` client snapshot flows into AI-drafted text

- **Current state**: `static/vindex.js:9397-9448` (`_buildPredmetKontekst`) reads
  `window._predFull` synchronously into `_predAutoFill` (~9451-9465), which populates an EDITABLE
  textarea the user reviews before submitting — not a silent invisible pass-through (lower real
  risk than the original framing implied, though still a real data-quality gap).
- **Disposition: A — TECHNICALLY RESOLVABLE, no product decision needed.** Re-fetch fresh
  predmet+stranke data via the existing GET endpoint before building the context string, instead of
  trusting a possibly-stale in-memory snapshot. Unlike `-007`'s genuine conflict-UX decision, "use
  fresh data for a field about to feed a legal-document generator" has no real tradeoff to weigh —
  it is simply the correct behavior.

### `-039` — Dashboard's historical risk-diff can lose coverage at scale (300-row cap)

- **Current state**: `routers/dashboard.py:96` — `.limit(300)` on the `predmet_istorija` query
  feeding `pad_procene` (built ~lines 293-311, returned ~line 379).
- **Disposition: A — TECHNICALLY RESOLVABLE, same split as `-003`.** Add a sibling
  `"pad_procene_truncated": bool` disclosure field — purely additive, the cap itself (a genuine
  cost tradeoff) stays untouched and remains the founder's call, exactly mirroring how `-003` was
  split by Mission 014.

### `-042` — 7 of 8 Case-Evolution event types have no reaper for a lost outbox insert

- **Current state**: `services/event_bus.py::reap_missing_pipeline_events` (~lines 828-889)
  detects a missing `PREDMET_KREIRAN` event via a simple 1:1 comparison (a `predmeti` row exists
  with no matching event). `ROCISTE_ZAKAZANO` has the identical 1:1 shape (a `rocista` row exists
  vs. an event exists) and can reuse the SAME template as a new, small, single-purpose function.
  The other 6 event types (document/review-level) are conditional on a sub-entity action, requiring
  a materially different, per-type-different query shape each.
- **Disposition: SPLIT.** `ROCISTE_ZAKAZANO` sub-item: **A — TECHNICALLY RESOLVABLE** (one bounded
  new function following the proven template). Remaining 6 types: **C — INFRASTRUCTURE/DESIGN
  DEPENDENCY**, confirmed genuinely needing per-type detection design — not attempted, consistent
  with the register's original assessment for those 6.

### `-049` — Memory Graph + Firm Memory unreachable (zero UI entry points)

- **Current state**: `routers/memory_graph.py` (4 routes) and `routers/firm_memory.py` (11 routes)
  registered and healthy. Zero references anywhere in `static/vindex.js` (exhaustive grep).
- **Disposition: B — CONFIRMED PRODUCT DECISION, nothing to fix.** No broken code exists — this is
  purely an absent frontend for a real backend. Build UI vs. formally retire the backend remains
  the founder's call; not invented here.

---

## Summary table (Phase 1 classification)

| ID | Disposition | Technically resolvable this operation? |
|---|---|---|
| `-003` | B | No — cap+ordering both founder decisions |
| `-011` (3 sub-items) | A | Yes — all 3 |
| `-012` | B (reframed, not infra) | No — but register's "needs migration" corrected to "needs founder data entry via existing tool" |
| `-022` | A | Yes — disclosure badge |
| `-036` | A | Yes — bulk close on case close |
| `-038` | A | Yes — disclosure fields |
| `-041` | A (timeout half) / B (progress-bar half) | Partially — 8 sites get timeout, progress bar deferred |
| `-046` | A | Yes — bounded coalescing wait |
| `-005`/`-030` | A | Yes — narrow flag + beforeunload |
| `-014` | C | No — genuinely needs per-field/per-template work |
| `-020` | A | Yes — disclosure field, reuse existing hash |
| `-023` | A | Yes — scoped to Smart Intake pipeline |
| `-025` | A (narrow) | Yes — additive disclosure key |
| `-026` | A (disclosure-only) | Yes — surface existing computed value |
| `-028` | A | Yes — reuse `-031`'s idiom earlier |
| `-035` | A | Yes — re-fetch instead of trust snapshot |
| `-039` | A | Yes — disclosure field |
| `-042` | A (1/7) + C (6/7) | Partially — `ROCISTE_ZAKAZANO` only |
| `-049` | B | No — confirmed product-scope, no code to fix |

**14 of 20 items are fully technically resolvable this operation; 2 more are partially resolvable
(`-041`, `-042`); 4 remain correctly blocked on a founder decision or genuine per-item design work
(`-003`, `-012`, `-014`, `-049`) — none invented, none force-closed.**
