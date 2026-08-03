# Blocker Report — Smart Intake has no frontend entry point

**Mission:** Operation Autonomous Law Office (BETA-002), 2026-08-03.
**Status:** BLOCKED — founder-level product decision required. No code changed by this finding.

---

## Problem

The founder's "Zero-Touch Case" mission success criterion is: *"A lawyer uploads documents and the
platform automatically transforms them into an organized legal case requiring minimal additional
administrative work."*

This cannot be true today, for a reason no amount of backend wiring can fix: **a lawyer cannot reach
Smart Intake from the product at all.**

## Evidence

Exhaustive search of every frontend file in the repo (`static/*.js`, all root `*.html` — no other
frontend framework present) for `smart-intake` / `smart_intake` / `SmartIntake`, case-insensitive:
**zero matches.**

What the UI actually calls for document upload (`static/vindex.js`):
- `/api/dokument/upload` (lines 8874, 20378) — the older, session-based Q&A upload. Per
  `routers/smart_intake.py`'s own header comment, this is a deliberately separate, synchronous
  feature (a lawyer asks questions about a document in the same flow) — not a rough draft of Smart
  Intake, a genuinely different tool.
- `/api/predmeti/{id}/upload` (line 19402) — the older per-case upload path. Writes the
  `"[Auto-analiza]"` `predmet_istorija` marker that `services/case_pipeline.py` step 1 checks
  (confirmed during Operation Lawyer Zero's LZ-002).

Neither calls `POST /api/smart-intake/documents` or `POST /api/smart-intake/jobs/{id}/finalize`.

**Consequence:** every fix this session and last (LZ-001's reminder vocabulary, LZ-002's Evidence
Vault auto-classification, tonight's Scenario B/G/F/5 fixes below) improved the *quality* of a
pipeline that improves a case the moment a lawyer's document reaches it — but the product has no
button, page, or flow that sends a document there. All of it is reachable today only via a direct
API call (Postman, a test, a script), never through the app a lawyer actually uses.

## Why this is a founder decision, not an engineering task

This is not a "connect existing, don't rebuild" wiring fix (Rule Zero territory) — the Smart Intake
*backend* is real and working end to end (upload → OCR → classify → extract → finalize → case). What
is missing is net-new **frontend surface**: an upload screen, an async job/review UI (Smart Intake's
own contract is 202-plus-background-processing, which the two existing upload paths' synchronous UX
doesn't have a pattern for), and a finalize/confirm step. Building that blind risks two things this
project has explicit standing rules about:

1. **UI style** (`feedback_no_generic_ui_bloomberg_style` memory) — this codebase has a deliberately
   non-generic, specific design language; a new multi-screen flow built overnight without founder
   review is exactly the kind of thing that rule exists to prevent.
2. **Product direction** — deciding whether Smart Intake *replaces* the two existing upload paths,
   *coexists* alongside them as a third option, or becomes the primary path with the others
   deprecated, is a real product decision with rollout and (possibly) data-migration implications,
   not a technical one this mission can resolve alone.

## Options (not chosen, for the founder)

1. **New, dedicated Smart Intake UI flow** — a fresh upload screen + async status view + finalize
   confirmation, positioned as the primary "start a new case" entry point. Largest scope, cleanest
   long-term outcome, most consistent with tonight's "Zero-Touch Case" framing.
2. **Repoint the existing `/api/predmeti/{id}/upload` button** to call Smart Intake's endpoints
   instead, keeping the existing UI chrome. Smaller frontend diff, but the finalize/review step (Smart
   Intake's async job model expects the lawyer to see extracted entities before committing) has no
   home in that flow today — would need at least a lightweight review modal, not zero new UI.
3. **Do nothing yet; document the gap and let the founder decide priority.** (This report.)

## Recommendation

Do not guess at UI. Bring this to the founder as the top-priority follow-on mission — it is the
single highest-leverage piece of work available (every other fix this session and last is inert
until this exists), but it's also the first mission this operation has found that is fundamentally a
*design* decision (which flow, what screens, how much of the existing two paths survive) rather than
an *investigation* one.

## Everything already done that becomes valuable the moment this ships

LZ-001 (reminders), LZ-002 (Evidence Vault auto-classification), tonight's Scenario B fix (batch
uploads → one case, not N), Scenario G fix (Genome no longer silently drops documents past #25),
Scenario F fix (concurrent Genome refreshes no longer race), and Scenario 5 fix (automatic
conflict-check on document-first case creation) all activate the instant a lawyer can reach Smart
Intake — none of them require further backend work to pay off.

## Risk of proceeding without this decision

Building UI overnight, unreviewed, for a founder who has an explicit, named design language
(`feedback_no_generic_ui_bloomberg_style`) and has not been asked which of the three options above he
wants, risks producing work that gets thrown away — the opposite of "reduce manual work for a
lawyer," since founder time spent reviewing and rejecting an unwanted UI is itself manual work created,
not removed.

---

## Mission Board disposition

New entry `ZTC-000` added to `MISSION_BOARD.md` as `NEEDS_SCOPING` / founder decision required, listed
as the top-priority open item — everything else on the board is now downstream of this one.
