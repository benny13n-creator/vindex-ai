# Top 20 Integration Breakpoints

**Mission:** Project Nexus, 2026-08-03. Every gap from `NEXUS_ICS_SCORE.md`'s connection ledger, plus
reliability/provenance findings that aren't graph edges but are real breakpoints in the intelligence
lifecycle (input→understanding→knowledge→reasoning→action→learning→memory). Ranked by severity ×
lawyer-facing impact. Items marked **RESOLVED** were fixed this mission; everything else is documented,
not guessed at, per the mission's own discipline.

---

1. **`routers/ccc.py`'s health_score silently diverged from the canonical formula under the identical
   field name** — RESOLVED this mission. Was the clearest Phase-5 violation found: two live endpoints,
   two possible numbers, same declared concept, for the same case.
2. **`routers/zadaci.py::ai_analiziraj_predmet` — a 5th independent, side-effect-producing missing-
   document detector, bypassing the platform's declared sole deterministic algorithm** — RESOLVED this
   mission. Highest-severity finding of the whole audit: this one WROTE real task rows from
   non-deterministic judgment.
3. **`HEALTH_SCORE_PROMENJEN` and `ROK_KRITICAN` — two fully-working proactive-alert handlers, never
   emitted by anything** — RESOLVED this mission (with a mandatory dedup guard, since the trigger point
   fires on every case-open).
4. **A silent, pre-existing date-math bug in `services/risk_engine.py`** — RESOLVED this mission
   (found as a prerequisite for fixing #3): naive-vs-aware datetime comparison silently zeroed out
   critical-hearing detection for any hearing stored as a plain date, the realistic shape for a
   production DATE column.
5. **A copy of the SAME date-math bug, independently duplicated in `routers/ccc.py`** — RESOLVED this
   mission (eliminated by having CCC call the canonical function instead of its own inline
   reimplementation, rather than patching the duplicate bug separately).
6. **`routers/ccc.py`'s document query never selected `tip_dokaza`** — RESOLVED this mission. A
   confirmed, live, silent bug: the "missing documents" smart-chip feature always showed every expected
   document type as missing, regardless of what was actually uploaded, because the SQL select string
   never requested the column the filtering logic needed.
7. **Case Genome refresh: a false "success" toast on genuine LLM failure** — RESOLVED this mission. The
   backend correctly returns an error marker (fail-soft, HTTP 200 with `{"greska": ...}`); the frontend
   never checked for it before choosing which toast to show.
8. **Smart Intake extracts judge/court/opponent entities but never writes them onto
   `predmeti.tuzilac`/`tuzeni`** — NOT resolved, reconfirmed from a prior mission (`WOW-003`). Blocks
   Judge & Court Profiler and Opponent Intelligence from ever auto-populating, even when the AI already
   has the answer. Small, well-scoped, still the single highest-value remaining opportunity.
9. **The Event Bus's one true in-process `emit()` call site (`PREDMET_KREIRAN`) has zero durability** —
   NOT resolved. If the process crashes between emit and handler completion, the entire Case Pipeline
   trigger is silently lost with no trace and no retry — unlike every other event type, which uses the
   durable outbox. Not fixed blind: making it durable risks double-firing the Case Pipeline unless
   `run_case_pipeline`'s idempotency is separately verified first (a real architecture question, not a
   quick patch).
10. **`DOCUMENT_JOB_FAILED` is emitted on every failed OCR/classification job, with zero handler** — NOT
    resolved. A failed document produces zero lawyer-facing or firm-facing signal today, even though
    durable proof it happened already exists. Needs new handler logic, one step past pure orchestration.
11. **`DOCUMENT_JOB_ENQUEUED`/`DOCUMENT_JOB_COMPLETED` — same shape as #10, lower urgency** (no
    user-facing consequence currently tied to their absence, unlike a silent failure).
12. **Outcome Intelligence and Judge/Court/Opponent Predictor never read Case Genome** — NOT resolved.
    Confirmed same gap Copilot and Firm Brain had (both fixed by a prior mission this engagement, same
    day) — well-precedented, low-risk future work, not attempted this mission due to more involved
    per-file prompt logic in each.
13. **No AI call site in the repository stores `model`, `prompt version`, or `output hash`** — NOT
    resolved, a uniform gap across all 6 audited call sites (Case Genome, AI Briefing, Smart Intake
    extraction/classification, AI Drafting, Evidence Vault). Every model name is hardcoded in Python
    source with no version tracking or output fingerprinting concept anywhere.
14. **Evidence Vault's `predmet_dokazi.snaga` ("strength") is hardcoded to `"srednja"` for every row** —
    NOT resolved. The one AI call site of the 6 audited where NO real confidence signal reaches storage
    at all, even though richer signal may exist upstream before being discarded.
15. **Two real anti-hallucination mechanisms exist (Quality Gate's citation-existence check, Legal
    Reasoning Engine's SOURCE-n/FACT-n constraint) but neither reaches Case Genome or the AI Briefing**
    — NOT resolved. Both of the highest-visibility AI outputs in the app trust GPT-4o's own output on
    prompt instruction alone, while two structurally-stronger guardrails sit unused for them.
16. **No rollback exists anywhere for multi-step database writes** (e.g., Smart Intake's finalize: 4
    independent try/except blocks, no transaction) — NOT resolved, a deliberate fail-soft tradeoff
    across the whole codebase, not an oversight specific to one flow. Partial failures are truthfully
    reported in API responses, but nothing retries or alerts on a mid-sequence failure.
17. **`knowledge_profiles` is a phantom data source inside the AI Briefing** — NOT resolved. Its only
    writer is confirmed dead code; the Briefing's `knowledge_profila` count is structurally always ~0
    for any real firm. Founder decision needed: build real extraction (new AI, out of scope) or retire
    it as an input.
18. **Memory Graph — confirmed still fully dead** — NOT resolved, unchanged across 3 missions now.
    Founder decision needed on data-population strategy before any UI is safe to build.
19. **Two competing client-CSV-import implementations, two competing WhatsApp-notification systems** —
    NOT resolved, unchanged from Operation Invisible Features / Beta Lockdown. Both are founder product
    decisions between existing alternatives, not engineering gaps.
20. **The daily cron (`api.py::cron_daily`) calls `_check_escalations()` twice** (Modules 1 and 5) — NOT
    resolved. Self-healing (the function's own status-transition makes the second call a no-op), so not
    user-facing, but confirmed dead/wasted work from an uncleaned copy-paste — the lowest-severity item
    on this list, included for completeness rather than urgency.

---

## Pattern across this list

Items 1, 4, 5, 6, and 7 (5 of the 7 RESOLVED items) were all found not by looking for bugs, but as a
direct consequence of verifying or connecting something else — a pattern now confirmed across the last
three missions of this engagement (Beta Lockdown's IDOR, Lawyer Day's photo-upload fix, Project
Synapse's date bug, and now this mission's cluster). Worth treating "connect X" as itself a reliable
bug-finding method for any future mission of this shape, not an incidental side effect.
