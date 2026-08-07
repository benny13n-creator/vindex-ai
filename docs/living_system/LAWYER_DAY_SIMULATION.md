# Operation Living System — Day 1: The Golden Path

4 read-only agents simulated a senior lawyer's full working day, each tracing real code (not
theorizing). This document is the consolidated findings ledger for Day 1. Disposition key:
**FIXED** (this mission, see `FIX_LOG.md`) / **DEBT** (deferred, reasoning in
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`) / **CONFIRMED CLEAN** (attacked, found sound).

## Morning: login → Workspace → Command Center → Morning Briefing → notifications → calendar

| Finding | Severity | Disposition |
|---|---|---|
| Health Index shows a contradictory amber "75/100 · B+" + billing warning on a brand-new user's very first login, while Workspace correctly says "everything under control" — happens to every new signup, guaranteed | HIGH | DEBT (`LIVINGSYS-DEBT-004`) |
| Notifications frontend reads `datum`/`predmet_naziv` fields the backend never sends (date badge and case-name sub-line always empty) | LOW | DEBT (`LIVINGSYS-DEBT-018`) |
| Two independent systems (`notifications.py`, `case_evolution.py`) can both notify for the same underlying deadline, worded differently | MEDIUM | Pre-existing, already self-documented debt — re-confirmed, not new |
| CIO's zero-case empty-state message is worded for the wrong empty state (implies cases exist but lack Genome, when the user has zero cases) | LOW | DEBT (`LIVINGSYS-DEBT-019`) |
| Migration 100 (notification priority CHECK widening) dependency unverified — cannot confirm from repo whether applied to production | FLAG | Same outstanding `SUPABASE_DB_URL` request, 7th consecutive mission |
| Auth (`shared/deps.py`), `GET /api/workspace`, Command Center's live risk computation, `shared/case_readiness.py`/`attention_priority.py`'s shared vocabulary, Case Commander's GPT boundary, Morning Briefing, Court calendar, CIO's disclosure/validation guards | — | **CONFIRMED CLEAN** |

## New documents arrive: upload → OCR → Smart Intake → evidence classification → Genome refresh

| Finding | Severity | Disposition |
|---|---|---|
| Zero duplicate-content detection on the main "add document to case" endpoint (Pipeline A) — re-uploading the same file creates a second row, duplicate Pinecone vectors, and double-bills the AI quota | HIGH | DEBT (`LIVINGSYS-DEBT-020`) |
| Unvalidated GPT chronology extraction feeds directly into the urgent-deadline notification system with no human-review gate; one malformed date can silently drop an entire batch | HIGH | DEBT (`LIVINGSYS-DEBT-021`) |
| Evidence type (`tip_dokaza`) classification has zero confidence gate, unlike Smart Intake's own document-type classifier | MEDIUM | DEBT (`LIVINGSYS-DEBT-022`) |
| No OCR quality/confidence signal — a garbled-but-nonempty scan is indistinguishable from a clean extraction | LOW | DEBT (`LIVINGSYS-DEBT-023`) |
| Smart Intake's own duplicate handling (idempotency key + content-hash check), Genome read consistently live everywhere, event chain to Genome refresh, in-process refresh coalescing, upload-time file validation, total-OCR-failure handling | — | **CONFIRMED CLEAN** |

## Urgent client call: Copilot → Case Commander → Digital Twin → Court Predictor, back to back

| Finding | Severity | Disposition |
|---|---|---|
| Copilot's `verovatnoca_uspeha` was never capped by `CAP_BY_READINESS` — a case with canonical CRITICAL_GAP could show Copilot's field at Genome's own uncapped % while Court Predictor/Digital Twin were structurally capped for the same case | HIGH | **FIXED** (Fix L1) |
| Battle Report's embedded outcome percentages (free-text markdown) are completely unguarded — same file as the correctly-capped `prediktuj_ishod`, but this sibling endpoint's percentages can freely contradict it | HIGH | DEBT (`LIVINGSYS-DEBT-001`) |
| Digital Twin's readiness cap silently disables itself if `build_case_context()` throws, diverging from Case Commander's honest "not enough data" degradation for the same outage | MEDIUM | DEBT (`LIVINGSYS-DEBT-024`) |
| Disclosure labeling is inconsistent across the 4 AI surfaces — only Case Commander carries full field-level provenance | MEDIUM | DEBT (`LIVINGSYS-DEBT-025`) |
| Digital Twin's and Court Predictor's recommended actions are never cross-checked against `case_actions`/`top_open_action` (mechanism gap, no concrete reproduced contradiction) | LOW-MEDIUM | DEBT (`LIVINGSYS-DEBT-026`) |
| Case Commander's canonical-context reuse, 3 of Court Predictor's 7 endpoints' guard coverage, Digital Twin's main-path readiness cap | — | **CONFIRMED CLEAN** |

## Afternoon: draft → email → bill → credit deduction → partner review → task completion → session end

| Finding | Severity | Disposition |
|---|---|---|
| `/api/nacrt` charges a credit even when draft generation completely fails (GPT timeout/error never raises, credit charged unconditionally) | HIGH FINANCIAL | DEBT (`LIVINGSYS-DEBT-002`) |
| `/api/podnesak` always charges even when every internal AI step silently degrades to placeholder text | MEDIUM FINANCIAL | DEBT (`LIVINGSYS-DEBT-027`) |
| No server-side cooldown/dedup for drafting — only client-side, single-tab double-click protection | LOW-MEDIUM FINANCIAL | DEBT (`LIVINGSYS-DEBT-028`, part of the broader cooldown gap, see `CHAOS_RESULTS.md`) |
| Workspace "Today" board's `zadaci` filter only surfaces tasks in `status="ceka"` — an `otvoreno`/`u_toku` task due today is invisible on the canonical daily board | MEDIUM | DEBT (`LIVINGSYS-DEBT-029`) |
| Zero autosave and zero unload-warning anywhere in the frontend — a typed case description lost on accidental tab close | MEDIUM | DEBT (`LIVINGSYS-DEBT-030`) |
| Invoice numbering/double-billing protection, invoice-number display consistency, cross-user partner-review staleness, task-completion propagation, timer race protection, `/api/analiza`'s correct success-gated charging | — | **CONFIRMED CLEAN** |

## Summary

Day 1 alone surfaced 1 fixed HIGH finding (Copilot readiness cap) plus 17 deferred findings
spanning HIGH-financial (drafting credit-on-failure), HIGH-trust (Health Index false alarm,
document dedup, unvalidated GPT chronology), and MEDIUM/LOW polish gaps — alongside a substantial
confirmed-clean list proving most of the golden path already reflects 15+ prior missions' work.
