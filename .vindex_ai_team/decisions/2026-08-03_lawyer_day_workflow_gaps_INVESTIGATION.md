# Lawyer Day — Workflow Gaps Investigation (Operation Lawyer Day)

Read-only. All claims grounded in direct file reads; no code changed.

**One false alarm avoided, same class as a prior session's**: `static/vindex.js:7600` appeared via the
Read tool to contain `BASE_URL+'\api\nacrt'` (backslashes — a broken URL with a literal embedded
newline). Verified with a raw Python byte-level read before reporting: the actual bytes on disk are
`'/api/nacrt'`, correct forward slashes. This was a Read-tool rendering artifact, not a real bug — do
not re-report it.

---

## 1. Document drafting ("nacrti" AIWS mode)

**Verdict: fully reachable, real, end-to-end including export.**

`data-mode="nacrti"` pill (`index.html:2768`) → `aiwsSetMode('nacrti', ...)` shows the `nacrti` pane →
`stratPokreni`-adjacent shared `execQuery()` (`vindex.js:7566`) dispatches to one of two real backends
depending on document type (`_NACRT_API_TYPES`, `vindex.js:6178-6190`, dynamically extended from `GET
/api/nacrt/types`): simple documents (contracts, powers of attorney, appeals, demand letters — 12
pre-populated types) go to `/api/nacrt`; 8 litigation-document types (`tuzba_naknada_stete`,
`zalba_parnicna`, `predlog_izvrsenje`, `tuzba_radni_spor`, `tuzba_razvod`, `prigovor_platni_nalog`,
`krivicna_prijava`, `predlog_privremena_mera`) go to `/api/podnesak` — a structured extraction+RAG+
enrichment pipeline, per `vindex.js:6181-6184`'s own comment. Output is exportable:
`nacrtExportDocx()` (`vindex.js:21437`) posts the generated text to `POST /api/nacrti/export/docx` and
downloads a real `.docx` file. This is a genuinely complete Workflow 1/2 "generate draft → export" path.

## 2. Strategy generation ("strategija" AIWS mode)

**Verdict: fully reachable, real, does NOT use the shared exec-row (dedicated buttons instead — correct
design, not a bug).**

`_AIWS_EXEC_LBL` (`vindex.js:2322`) has no `strategija` key, which hides the shared `t-exec-row`/
`execQuery()` button for this mode — this looked like a possible gap at first glance but isn't: the
`aiws-mode-strategija` pane (`index.html:3015-3063`) has its own dedicated `strat-submit-btn` →
`stratPokreni()` (single-agent analysis) and `strat-ork-btn` → `stratOrkestratorPokreni()` (full
6-agent parallel analysis, "6 kredita"). Both real, both wired.

## 3. Judge history / court predictor

**Verdict: fully reachable — better than the mission's framing assumed. A dedicated "Litigation
Intelligence" AIWS mode exists, distinct from "strategija".**

`data-mode="litigation"` pill (`index.html:2771`, label "Litigation Intelligence") → `aiws-mode-
litigation` pane (`index.html:3065-3131`), PRO-gated, containing FOUR real sub-features, all wired to
dedicated buttons (not the shared exec-row):
- **Similar Cases** ("Slični predmeti" / "Law Firm Brain") — `litIntelBrainLoad()`.
- **Outcome Trends** ("Trend ishoda") — `litIntelOutcomeShow()`.
- **Judge & Court Profiler** ("Sudija i sud", `index.html:3102-3112`) — `strat-judge-sud`/`strat-judge-
  ime` inputs → `stratJudgeProfile()` (`vindex.js:3563`), "2 kredita".
- **Opponent Intelligence** ("Protivnička strana", `index.html:3115-3123`) — `strat-opponent-naziv`/
  `strat-opponent-adv` inputs → `stratOpponentIntel()` (`vindex.js:3599`), "2 kredita".

This directly answers Workflow 4's "judge history" and "prior arguments"/"client history"-adjacent
needs as already-reachable, not a gap. Note: `case_intelligence.py`'s Briefing (item unrelated to this
census, already wired) also folds a "court predictor" signal into its one aggregated recommendation —
this Litigation Intelligence pane is the STANDALONE, deep-dive version of the same underlying capability
class, not a duplicate (different depth/purpose: one-line signal inside a synthesis vs. a dedicated
research tool).

## 4. Hearing-prep "export package"

**Verdict: does not exist as a single bundling feature. Confirmed by absence, not assumed.**

The Litigation Intelligence pane (item 3) ends with two cross-reference links (to legal research and to
full case-law search, `index.html:3127-3129`) — no export/bundle button anywhere in that pane. No
hearing-specific export was found in `routers/export.py`, `routers/data_export.py`, or `routers/
rocista.py`. A lawyer preparing for a hearing would need to: open Litigation Intelligence (judge/
opponent/similar-cases/trends), separately open Case Genome/AI Briefing (arguments/evidence/risk), check
Calendar (deadlines), and separately export any drafted documents via the DOCX/PDF export already
confirmed working (item 1/10) — four+ separate visits, no single "prepare for hearing" bundle. Real gap,
but note: bundling four already-reachable views into one export is a UI/aggregation feature, not
something blocked by any missing backend capability — everything it would draw from already works.

## 5. Duplicate-document detection on batch upload

**Verdict: exists, real, at the exact-content level — narrower than "detect near-duplicates" but a
genuine, working mechanism.**

`routers/smart_intake.py:126` computes `content_sha256 = hashlib.sha256(raw).hexdigest()` per uploaded
file, passed as `idempotency_key=f"{user_id}:{content_sha256}"` into `shared/intake_queue.py:41`'s
`enqueue_job()`, whose own docstring states: *"Idempotentna — isti idempotency_key vraća POSTOJEĆI
job_id, nikad duplikat"* ("idempotent — the same idempotency key returns the EXISTING job_id, never a
duplicate"). Confirmed via the underlying `enqueue_intake_job` RPC call (`intake_queue.py:56-63`).
**Scope limit, not a bug**: this is exact-byte-hash deduplication (the same file uploaded twice) — it
would not catch two different scans of the same physical document (different compression/DPI producing
different bytes but the same content). No content-similarity dedup was found or expected to exist.
Reachability caveat: like everything else in Smart Intake, this dedup logic is real but currently only
reachable via direct API call, not through any UI a lawyer uses (same root cause as the已-documented
frontend-entry-point gap).

## 6. Case archiving

**Verdict: reachable, but only via bulk multi-select from the case LIST view, not as a single button
inside the case-detail view specifically.**

`routers/predmeti_close.py:295`'s `akcija` field accepts `arhiviranje`/`aktiviranje`/`zatvaranje`
(archive/activate/close), confirmed real. Frontend: `pred_bulkAkcija('arhiviranje')`
(`vindex.js:10174-10184`) — triggered from a bulk-selection bar (`pred-bulk-bar`) that appears after a
lawyer checks one or more cases in the LIST view (`pred_toggleOznaci`), not from a dedicated button
while VIEWING a single case's detail panel. Functionally reachable (a lawyer can select exactly one case
and bulk-archive it), but requires going back to the list rather than acting from within the case
they're currently reading — a minor workflow friction, not a missing capability.

## 7. Lawyer-facing audit log view

**Verdict: does not exist. Confirmed by absence.**

Searched `vindex.js` for `/api/audit`: only two hits, both unrelated to an activity-log viewer —
`/api/audit/kalibracija` (`vindex.js:2626`, a calibration endpoint) and `/api/audit/sync`
(`vindex.js:21075`, a different sync mechanism). No UI renders `shared/audit_immutable.py`'s log (used
for GDPR erasure/export events) or any general account/case activity history for the lawyer to browse.
This is a real, if lower-urgency, gap — nothing in Workflow 5 strictly requires it, but "review your own
account activity" is a reasonable end-of-day expectation this mission's Workflow 5 gestures at
("Audit").

## 8. Backup / data-safety status visible to a lawyer

**Verdict: does not exist — and this is correctly N/A, not a gap.** Searched `vindex.js` for
"backup"/"rezervn": the only hits are unrelated (the word "BACKUP" used as a UI label for a legal
strategy's contingency plan field, `vindex.js:17527-17528` — nothing about data backups). No backend
backup-status endpoint was found either. This is legitimately an infra concern with no natural
lawyer-facing surface — not every Workflow 5 bullet needs its own UI element.

## 9. Notes — "beleske" vs "komentari": two live systems, not a dead duplicate

**Verdict: BOTH are reachable and wired. This is the mission's "two systems, same problem" pattern, but
verify before assuming — they may serve different purposes, not confirmed as true duplicates in the
time available.**

- `predmet_beleske` ("beleske") — read via `GET /api/predmeti/{id}/beleske` (`vindex.js:19409`),
  rendered into `pred-beleske-list` (`vindex.js:12092-12097`). Also a first-class citizen of the global
  search system (`_cmdkVrste` includes `'beleske'`, `vindex.js:12954`, with its own type mapping in
  `_CMDK_ORDER`/`_CMDK_TIP_MAP`).
- `predmet_komentari` ("komentari") — read via `GET /predmeti/{id}/komentari`, posted via `POST
  /predmeti/{id}/komentari`, deleted via `DELETE /komentari/{id}` (`vindex.js:4495-4536`). **Notably
  NOT included in the global search system's type list** — an asymmetry worth flagging.

**Current winner (by integration depth): `beleske`** — reaches global search, has its own case-detail
list rendering. **Current loser (by that same measure): `komentari`** — has full CRUD but is invisible
to search. Not independently confirmed whether these serve genuinely different purposes (e.g., private
working notes vs. team-visible comments) or are accidentally-duplicated free-text annotation — this
distinction matters for whether "unify" even applies, and wasn't resolvable from static analysis alone
in the time available. Recommend a direct UI-level check (open a real case, see if both "Notes" and
"Comments" sections appear side by side with similar-looking inputs) before deciding.

## 10. First-draft export

**Verdict: fully reachable — see item 1.** `nacrtExportDocx()` (`vindex.js:21437`) → `POST /api/nacrti/
export/docx` → real `.docx` download. Cross-checked against the previously-confirmed `routers/
export.py` DOCX/PDF capabilities — this is a separate, dedicated drafting-export endpoint
(`/api/nacrti/export/docx`), not reusing `routers/export.py` directly, but functionally equivalent in
outcome (a lawyer gets a real, downloadable document). Not flagged as a duplicate since it's export of
a DIFFERENT artifact (a freshly-generated draft) than what `routers/export.py`/`routers/data_export.py`
export (case records, GDPR data).

---

## Summary table

| # | Area | Verdict |
|---|---|---|
| 1 | Draft generation (nacrti) | Fully reachable, exportable |
| 2 | Strategy generation | Fully reachable (dedicated buttons, not the shared exec row — correct by design) |
| 3 | Judge/opponent/case history | Fully reachable — dedicated "Litigation Intelligence" mode, richer than expected |
| 4 | Hearing-prep export bundle | Does not exist — real gap, but purely an aggregation UI, every underlying piece already works |
| 5 | Duplicate-upload detection | Exists, exact-hash level — reachable only via API (Smart Intake's known frontend gap) |
| 6 | Case archiving | Reachable, bulk-from-list only — minor friction, not missing |
| 7 | Lawyer-facing audit log | Does not exist — real, lower-urgency gap |
| 8 | Backup status UI | Does not exist — correctly not applicable |
| 9 | Notes vs. Comments | Both live; asymmetric search integration; duplicate-vs-distinct-purpose not resolved, needs a live UI check |
| 10 | Draft export format | Fully reachable, real DOCX download |

All items above are findings only — no implementation attempted, per this investigation's read-only
scope.
