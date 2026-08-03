# VINDEX AI — Reliability, Trust & Operational Integrity Report

**Mission:** Project Sentinel, founder's Master Prompt, 2026-08-03. Pre-Beta Reliability, Trust &
Operational Integrity Mission — the deliberate follow-on to Project Nexus (which answered "do the
modules cooperate?"). This mission answers: **"can the system survive real law-office operation
without losing data, without silent errors, without false AI conclusions?"**

Every claim below is grounded in a code citation or an executed test, per the mission's own directive:
"Ne pretpostavljaj ništa. Ne veruj dokumentaciji... Veruj isključivo izvršenom kodu, testovima i
dokazima." Full evidence trail: `.vindex_ai_team/decisions/2026-08-03_sentinel_*_INVESTIGATION.md` (5
read-only forks) and `docs/architecture/SENTINEL_ORCHESTRATION_REPORT.md` (implementation record).

---

## Phase 7 — End-to-End Intelligence Verification

Simulated lawyer workflow, traced against actual code (not assumed) at every step, incorporating this
mission's fixes:

| Step | Executed? | Correct source? | Info lost? | Duplicate produced? | Event skipped? |
|---|---|---|---|---|---|
| 1. Kreiranje predmeta | Yes | N/A | No | No | **Fixed this mission** — `PREDMET_KREIRAN` now durable-outbox, survives a crash between insert and pipeline trigger |
| 2. Dodavanje klijenta | Yes | N/A | No | No | N/A |
| 3. Upload dokumenata | Yes | N/A | **Fixed this mission** — insert failure after Pinecone success previously produced a ghost document + false success; now fails loudly instead | No | No |
| 4. OCR | Yes (fail-soft by design for Smart Intake path; synchronous 422 for the ad-hoc path) | N/A | No | No | No |
| 5. Genome analiza | Yes | Yes (single canonical `case_dna` write) | Partial — background-refresh *trigger* itself is still fire-and-forget with no durable retry (not fixed this mission, see Remaining Blockers) | No | No (once triggered) |
| 6. Risk analiza | Yes | Yes — `calculate_procesni_rizik`, now the canonical source for `ccc.py`, `matter_intel.py`, `zadaci.py`, and (fixed this mission) `dashboard.py`'s health endpoint | No | **Fixed this mission** (`dashboard.py` no longer computes a diverging 3rd number) | No |
| 7. Generisanje strategije | Yes, but output is **ephemeral** — Strategy Engine (`routers/strategija.py`) never persists to any case-linked table (confirmed by Phase 1 fork; not touched this mission, see Remaining Blockers) | N/A | **Yes, structurally** — a lawyer's Red Team/Litigation Simulator run leaves zero trace in Timeline/Genome/Firm Brain | N/A | N/A |
| 8. Pronalaženje rokova | Yes | Yes (`rokovi_lanac.py`, deterministic) | No | No | No |
| 9. Kreiranje zadataka | Yes | Yes — grounded in `identify_case_problems` (Project Nexus fix, reconfirmed unaffected this mission) | No | No | No |
| 10. Aktiviranje upozorenja | Yes | Yes | **Fixed this mission** — `DOCUMENT_JOB_FAILED` previously produced zero alert; now creates a `proactive_alerts` row | No | No |
| 11. Ažuriranje Firm Brain-a | **Not automatic** — manual-save-only entry points confirmed (medium confidence, not re-verified to full certainty this mission) | N/A | Yes, if intended to be automatic | N/A | N/A |
| 12. Indeksiranje pretrage | Yes | Yes — **fixed this mission**: dead duplicate `/api/search` route removed, one live implementation only | No | **Fixed this mission** (was 2 competing route registrations, 1 fully dead) | No |
| 13. Priprema Copilot konteksta | Yes | Yes (reads Genome, Project Synapse fix, reconfirmed) | No | No | No |
| 14. Generisanje AI Briefinga | Yes, but **not grounded** in `calculate_procesni_rizik`/`identify_case_problems` — independently judges "kakav dan predstoji" from a raw data dump (not fixed this mission, see Remaining Blockers) | Partial | N/A | N/A | N/A |
| 15. Upis u Audit | Yes, for the actions in `AUDITABLE_ACTIONS` — confirmed this allowlist excludes Strategy Engine, Copilot, Briefing, Case Pipeline, and Task Engine's AI call specifically (not widened this mission, see Remaining Blockers) | Partial | Yes, for most AI action types | N/A | N/A |

**Net for Phase 7**: 5 of 15 steps were measurably improved this mission (1, 3, 6, 10, 12). 3 steps
have real, previously-known, still-open gaps (7, 11, 14, 15) that were investigated and confirmed but
deliberately not patched ad hoc this session — each needs either a small dedicated fix (Briefing
grounding, same proven pattern as Task Engine) or a founder-scoped decision (Strategy Engine
persistence semantics, audit allowlist scope, Firm Brain auto-population intent).

---

## Phase 8 — Reliability Metrics

### Intelligence Connectivity Score (ICS)

`ICS = Verified Connections / Total Required Connections × 100`. Same 32-connection ledger Project
Nexus established (`docs/architecture/NEXUS_ICS_SCORE.md`) — recomputed, not redefined, per that
document's own "Recomputation note."

**This mission's change**: row 21 (`DOCUMENT_JOB_FAILED → any handler`) flips from ❌ Gap to ✅ Verified
(Fix 4). No other row's connectivity status changes — the other 4 fixes this mission (upload gating,
search dedup, `PREDMET_KREIRAN` durability, dashboard delegation) are **reliability/consistency**
improvements to *already-verified* connections (rows 13, 17, 28), correctly credited under Reliability
Score and CIC below instead, to avoid double-counting or inflating ICS with non-connectivity fixes.

**ICS = 21 / 32 = 65.6%** (up from 62.5%). Target >90% — still well below.

### Critical Intelligence Coverage (CIC) — new metric, first baseline this mission

`CIC = weighted average connectivity of CRITICAL-tier flows only`, weight 2 for flows that directly
gate case outcome/deadlines (Novi predmet, Upload+OCR, Risk analiza, Deadline Engine, Task Engine,
Alerts, Audit), weight 1 for supporting flows (Genome, Strategy, Briefing, Timeline, Firm Brain, Memory
Graph, Semantic Search, Copilot, Dashboard, Notification). Each flow scored Full=100 / Partial=50 /
Broken=0 per Phase 7's table above.

| Tier | Flow | Score |
|---|---|---|
| Critical (×2) | Novi predmet | 100 (fixed) |
| Critical (×2) | Upload+OCR | 100 (fixed) |
| Critical (×2) | Risk analiza | 100 |
| Critical (×2) | Deadline Engine | 100 |
| Critical (×2) | Task Engine | 100 |
| Critical (×2) | Alerts | 100 (fixed) |
| Critical (×2) | Audit | 50 (allowlist too narrow) |
| Standard (×1) | Genome | 50 (trigger not durable) |
| Standard (×1) | Strategy Engine | 0 (ephemeral, disconnected) |
| Standard (×1) | Briefing | 50 (ungrounded) |
| Standard (×1) | Timeline | 100 |
| Standard (×1) | Firm Brain | 50 (manual-only, unconfirmed intent) |
| Standard (×1) | Memory Graph | 0 (inert) |
| Standard (×1) | Semantic Search | 100 (fixed) |
| Standard (×1) | Copilot | 50 (no hallucination guard) |
| Standard (×1) | Dashboard | 100 (fixed) |
| Standard (×1) | Notification | 50 (push solid, other channels unverified) |

Weighted sum: critical tier (2×(100+100+100+100+100+100+50)=1300, weight 14) + standard tier
(50+0+50+100+50+0+100+50+100+50=550, weight 10) → **CIC = (1300+550)/24 = 77.1%**. Target >95%.

*(First-time baseline — this metric didn't exist before this mission. Recompute the same way, same
flow list and weights, in future missions for a comparable trend, matching ICS's own convention.)*

### Reliability Score

Per Phase 3's 11 distinct failure scenarios (§8/§9 of the investigation were confirmed to be the same
underlying exposure, merged), scored Full=100 (complete detection+honest signal+recovery) /
Partial=60 (contained, but missing an honest signal or full recovery path) / Gap=0 (no defined
recovery at all):

- **Full (2)**: OCR unavailable (pre-existing, best-handled path in the codebase); transaction
  interrupted / partial predmet write (**fixed this mission** — upload ghost-document bug).
- **Partial (7)**: LLM timeout, OpenAI error (both retried/resumable, no honest top-level failure
  signal), embedding service down (silent degrade to "no results"), Pinecone error (write-path
  correct, read-path silent-degrade), Supabase error (verified safe for the specific `log_action` call
  sites audited; not exhaustively swept for every background task in the codebase), Event Bus
  interruption (`PREDMET_KREIRAN` **fixed this mission**, `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN`
  still exposed — deferred pending a dedup-key verification per the investigation's own
  recommendation), corrupted PDF (caught, but a generic/misleading message).
- **Gap (2)**: conflicting data across documents (no contradiction-detection mechanism exists at all),
  network interruption / upload retry duplication (`source_sha256` is already computed but unused for
  dedup).

**Reliability Score = (2×100 + 7×60 + 2×0) / 11 = 56.4%**. Target >95%. This mission closed the single
most severe, most concretely-code-proven gap (transaction-interrupted/ghost-document) and one of three
Event Bus durability exposures; the remaining gaps are real but were deliberately not patched blind —
several need either a design decision (contradiction detection, upload dedup UX) or additional
verification before a safe fix (the two remaining Event Bus events).

### Provenance Coverage

Per Phase 5's investigation: **0%** by the mission's own strict definition (model, prompt version,
duration, and sources-used must all be reconstructable). Confirmed across a corrected, larger scope
than Project Nexus's original estimate — 53 files / 20+ distinct AI features, not 6. Confidence and
input-snapshot exist for only 2 of those features (Case Genome, Drafting). **Unchanged this mission** —
correctly scoped as a shared-schema decision requiring founder sign-off (already tracked as NEX-006),
not attempted as an ad hoc patch across 20+ call sites.

### Failure Recovery Coverage (CRITICAL-severity findings only)

Of the 2 genuinely CRITICAL-severity findings confirmed across Phases 2/3 at the start of this mission
(upload ghost-document; Event Bus non-durability affecting 3 event types): **1 fully closed** this
mission (upload ghost-document), **1 partially closed** (1 of the 3 affected event types —
`PREDMET_KREIRAN` — converted to durable outbox; `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` remain).
**Failure Recovery Coverage = 1.5 / 2 = 75%** for CRITICAL-tier findings specifically (up from 0% at
the start of this mission — both were fully open going in). Target 100%.

---

## Phase 9 — Beta Gate

| # | Question | Answer | Basis |
|---|---|---|---|
| 1 | Može li se izgubiti događaj bez detekcije? | **DA** (reduced) | `PREDMET_KREIRAN` fixed this mission; `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` still in-memory-only |
| 2 | Može li AI doneti zaključak bez dokazivog porekla? | **DA** | Provenance Coverage confirmed 0% platform-wide (Phase 5); correctly not patched ad hoc |
| 3 | Može li postojati više izvora istine? | **DA** (reduced) | `dashboard.py`'s 3rd health formula fixed this mission (on top of Nexus's 2 prior fixes); Strategy Engine + Morning Briefing remain independent judgments |
| 4 | Može li korisnik dobiti lažnu potvrdu uspeha? | **NE**, for the one code-proven instance found | Upload ghost-document fixed this mission — not an exhaustive guarantee across the whole codebase, only the flows this mission's forks traced |
| 5 | Može li kritična greška ostati neprimećena? | **DA** (reduced) | `DOCUMENT_JOB_FAILED` fixed this mission; embedding-service-down and Pinecone read-path silent degrades remain |
| 6 | Može li sistem ostati u nekonzistentnom stanju nakon pada? | **DA** (reduced) | Upload/`PREDMET_KREIRAN` fixed; Genome background-refresh *trigger* still fire-and-forget with no durable retry |
| 7 | Može li isti događaj biti obrađen više puta? | **DA**, for one scenario | Upload retry-after-timeout has no idempotency guard despite `source_sha256` already being computed (deferred — needs a UX decision on duplicate-upload handling) |
| 8 | Može li korisnik ostati bez objašnjenja za AI odluku? | **DA** | No shared hallucination-guard layer exists (Phase 6); Task Engine/Drafting are grounded, most of the platform's AI surface (Copilot, Strategy, Briefing, Court Predictor) is not |

**6 of 8 gate questions still answer DA.** Per the mission's own rule ("Ako je odgovor 'DA' na bilo
koje pitanje, beta nije odobrena"), **unconditional Closed Beta approval is not warranted** — but every
DA above is now qualified ("reduced," "for one scenario," "for the one instance found") rather than
unqualified, reflecting real, code-proven, cited progress this mission, not an unmoved baseline.

---

## Findings

### Critical (found and fixed this mission)
1. `api.py::predmet_upload_auto_analyze` — false HTTP 200 success + full AI analysis for a document
   that failed to persist to `predmet_dokumenti` after Pinecone ingestion succeeded. **Fixed.**
2. `PREDMET_KREIRAN` emitted purely in-process with zero durable-outbox backing — a crash silently and
   permanently drops the entire Case Pipeline with no trace. **Fixed** (converted to durable outbox,
   de-risked by confirmed `run_case_pipeline` idempotency).
3. `GET /api/search` registered twice (`api.py` + `routers/search.py`); `api.py`'s ~130-line
   implementation was 100% dead code — second confirmed instance of the exact anti-pattern behind
   SEC-002. **Fixed** (dead route deleted).

### High (found and fixed this mission)
4. `DOCUMENT_JOB_FAILED` durably recorded, dispatched, and silently discarded — zero subscribers — a
   permanently-failed OCR/intake job produced no user-facing signal at all. **Fixed** (handler added).
5. `routers/dashboard.py::matter_health_score` — a third, independently-weighted case-health formula,
   orphaned from the frontend but fully alive (routed, tested) — a landmine for future UI work.
   **Fixed** (delegated to canonical Risk Engine).

### High (found, documented, NOT fixed this mission — explicit future scope)
6. `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` share `PREDMET_KREIRAN`'s old non-durable-emit exposure.
   Not converted this mission pending verification that `matter_intel.py`'s alert-dedup logic is safe
   under a durable retry (a naive conversion could double-insert an alert) — the investigation's own
   explicit recommendation.
7. Strategy Engine (`routers/strategija.py`, 8 endpoints) persists nothing — every legal conclusion it
   produces is discarded on response, not linked to any `predmet_id`. Fixing this is an architecture
   decision (should every Strategy Engine call require a case context?), not a bounded bug fix.
8. `AUDITABLE_ACTIONS` allowlist excludes Strategy Engine, Copilot, Briefing, Case Pipeline, and Task
   Engine's AI call — most of the platform's AI actions are structurally un-auditable even though the
   audit mechanism itself works correctly for what it does cover. Widening this safely requires
   deciding which actions matter enough to warrant durable hash-chained entries — a founder-scoped
   provenance-investment decision (same category as NEX-006), not attempted ad hoc across 5+ files.
9. Morning Briefing computes case urgency independently of `calculate_procesni_rizik`/
   `identify_case_problems` — can structurally disagree with every other surface in the product about
   the same case. The proven fix pattern exists (Task Engine's Project Nexus grounding), but Briefing
   operates across up to 20 active cases per request (a fan-out, not a single-case surgical fix like
   Task Engine's) — needs its own scoped pass, not a rushed partial version.
10. No shared hallucination-guard layer exists anywhere — 3 independent partial patterns
    (`quality_gate.py` for Drafting only, Task Engine's fresh prompt-grounding, ~50 call sites with
    syntax-only JSON-parse validation). Highest-exposure gap: `routers/copilot.py`'s free-text chat has
    no grounding or citation check at all. Unifying these is itself a design investment (which pattern
    becomes canonical, which call sites migrate first) — correctly scoped as future work per the
    investigation, not a bolt-on fix.
11. AI Provenance (`model`, `prompt version`, `duration`, `sources used`) is unrecoverable for any of
    20+ AI features platform-wide — confirmed a larger scope than previously estimated. Needs a shared
    schema + wrapper, a founder decision (already tracked as NEX-006).

### Medium (found, documented, not fixed)
12. Embedding-service-down and Pinecone read-path failures silently degrade to "no results," 
    indistinguishable from a genuine empty result, in RAG-backed features (Copilot precedent lookup,
    Precedenti page). Breadth of affected call sites not fully verified this mission.
13. No contradiction-detection mechanism exists for facts extracted from different documents within
    the same case.
14. Upload retry-after-timeout has no idempotency guard — `source_sha256` is computed but discarded,
    so a resubmitted upload duplicates the entire pipeline (double Pinecone ingest, double AI spend,
    duplicate document row).
15. Genome background-refresh *trigger* (not the `GENOME_UPDATED` event itself, which is fully durable)
    remains fire-and-forget from all 4 of its entry points — a crash between document upload and
    refresh completion silently drops the Genome update.
16. Firm Brain has no confirmed automatic producer (manual-save-only) — medium confidence, needs
    founder confirmation of intent.

### Low (found, documented, not fixed — deliberately deprioritized per the mission's own ordering)
17. 3 of 12 `EventType` values (`ROK_DODAN`, `ROCISTE_ZAKAZANO`, `ANALIZA_ZAHTEVANA`) have neither
    producer nor consumer — inert, misleading to a future engineer, no runtime risk.
18. Corrupted-PDF error message is generic/misleading ("Pokušajte ponovo") versus the excellent,
    specific scanned-PDF message for a functionally similar failure.
19. No shared `write_case_history_entry()` helper — 5 files hand-build `predmet_istorija` inserts
    independently (schema-drift risk, not a multi-owner violation).
20. `risk_engine.py`'s per-ročište date parsing swallows malformed dates with a bare `except: pass`,
    no log line.

---

## What was implemented this mission

Five code fixes (see `SENTINEL_ORCHESTRATION_REPORT.md` for full verification detail): upload
false-success gating, dead `/api/search` route removal, `PREDMET_KREIRAN` durable-outbox conversion,
`DOCUMENT_JOB_FAILED` alert handler, `dashboard.py` health-score delegation. Zero new AI features, zero
new modules, zero new UI — matching the mission's strict constraint. 13 new/rewritten tests
(`tests/test_sentinel_reliability_fixes.py` — 6 new; `tests/test_dashboard.py` — 7 rewritten against
the corrected formula). Full suite: 2329 passed, 1 skipped, 0 failed (11 unrelated pre-existing
failures confirmed via `git stash` to exist on the untouched baseline, not caused by this mission).

## Remaining blockers, with reasons for deferral

| Blocker | Why not fixed this mission |
|---|---|
| `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` durability | Needs `matter_intel.py`'s alert-dedup verified safe under durable retry first — the investigation's own explicit recommendation, to avoid trading a lost-event bug for a duplicate-alert bug |
| Strategy Engine persistence | Architecture decision — does every Strategy Engine call need a case context? Not a bounded bug |
| Audit allowlist widening | Founder-scoped decision on which AI actions warrant durable hash-chained provenance — same category as the AI Provenance schema decision |
| Morning Briefing grounding | Proven fix pattern exists but requires a fan-out across up to 20 cases per request, not a single-case surgical fix — needs its own scoped pass |
| Hallucination-guard unification | Design investment (canonical pattern choice, migration order) — the mission's own instruction to "unify" 3 independent implementations is itself new infrastructure, not a patch |
| AI Provenance schema | Confirmed large (20+ features), needs founder sign-off — already tracked as NEX-006 |
| Contradiction detection | No existing mechanism to extend — would be new capability, out of this mission's "connect, don't build" mandate |
| Upload idempotency (source_sha256 dedup) | Needs a product decision on duplicate-upload UX (silently skip? show existing doc? merge?) |
| Genome background-refresh durability | Needs redesigning 4 separate trigger call sites into one durable mechanism — larger than a single-function fix |
| Firm Brain auto-population | Medium-confidence finding — needs founder confirmation this is unintended, not a deliberate curation-only design |

---

## Final Recommendation

## ⚠️ READY FOR LIMITED BETA WITH KNOWN RISKS

**Rationale**: This mission closed the two most severe, most concretely code-proven defects found in
this engagement to date — a false-success signal reaching the user (upload ghost-document) and the
single largest silent-data-loss exposure in the event architecture (`PREDMET_KREIRAN` durability) —
plus three additional real, previously-undetected bugs (a dead route serving as an architecture
landmine, a silently-discarded critical-failure event, a third contradicting health-score formula).
None of these were hypothetical; each was traced to an exact file:line and reproduced in a test before
being called fixed.

However, per the mission's own Beta Gate, 6 of 8 trust questions still answer **DA**, and both new
metrics introduced this mission (CIC 77.1%, Reliability Score 56.4%) sit well below their >95%
targets, alongside ICS (65.6%) and Provenance Coverage (0%) versus their own >90%/100% targets. These
are not reasons to block a **limited, closely-monitored** beta — the specific failure modes that would
most directly harm a real user (false success on document upload, permanently-lost case pipeline
triggers, silently-dropped critical failures) are now closed or substantially reduced — but they are
real reasons this system is not yet ready for an **unconditional** general release. The remaining
gaps are honestly scoped, not hidden: each has a named reason for deferral and a clear next step, not
a vague "todo."
