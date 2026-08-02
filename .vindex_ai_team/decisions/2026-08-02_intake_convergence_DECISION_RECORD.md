# Intake Convergence Decision Record

**Author (role):** AI CTO / Chief Architect (Solution Architect input folded in)
**Date:** 2026-08-02
**Status:** Investigation complete. **Recommendation: do not merge `routers/intake.py` and
`routers/smart_intake.py` at the code/API level.** Converge at the UX layer only, if at all.
**Trigger:** the Bojan Workflow Gap Analysis (2026-08-02) flagged these as "two parallel,
unconverged intake systems" and recommended convergence as a Sprint 1 item. The founder correctly
paused that recommendation and asked the prior question first: *"Zašto postoje dva intake sistema?
Postoje samo tri mogućnosti: istorijski razlog, različiti use-case-ovi, ili nepotpuna migracija. Ako
je treće, spajanje ima smisla. Ako je drugo, možeš napraviti regresiju."*

---

## Answer: option 2 — different use cases. This is documented in the code itself, not inferred.

Both files carry their own history explaining exactly why the other exists. This is not a guess —
it's transcribed from `docs/adr/0001-async-ingest-job-queue.md` and `routers/smart_intake.py`'s own
header comment (`:10-25`).

**`routers/intake.py` — the CRM Intake Wizard.** Pre-existing, in production before Smart Intake was
built. Its job: **open a new matter** — a lawyer types a short problem description, AI proposes a
structured case (type, parties, deadlines, required documents), the lawyer confirms, and the system
also runs a conflict-of-interest check, offers pre-built case-type templates with pre-seeded
chronologies, and can set up billing in the same call. It accepts *references* to already-uploaded
documents (`dokumenti: List[DokumentIntakeRef]`) but does not itself do OCR, classification, or
extraction — it is a **case-creation** tool, not a **document-processing** tool.

**`routers/smart_intake.py` — the Smart Intake Engine.** Built later (ADR-0001, 2026-07-15),
purpose-built for a different problem: **a lawyer's morning inbox** — a batch of scanned documents
with no case attached yet — needs OCR, classification, entity extraction, and (via its finalize
endpoint) automatic case creation *from the documents themselves*. ADR-0001's own text records that
the original spec wanted the path `/api/intake/documents`, and during implementation it was
discovered that `/api/intake/*` was already fully owned by the CRM wizard — "same word, unrelated
feature" — so the route was formally renamed to `/api/smart-intake/*` **as a documented ADR
amendment**, not a silent workaround. The two were never intended to be the same system; the naming
collision was a coincidence the team caught and corrected before shipping, not evidence of overlap.

**A third, even narrower system exists and should not be confused with either:**
`/api/dokument/upload`, described in ADR-0001's own Context section as *"efemerni session-based Q&A
upload — sinhron po dizajnu"* — a single document a lawyer wants to ask immediate questions about,
deliberately synchronous because the user is waiting on it in the same interaction. Not a case-
creation tool, not a batch tool.

## Why merging would very likely cause a regression (the founder's own named risk, confirmed real)

Each system has capabilities the other does not, and neither is a strict subset of the other:

| Capability | `intake.py` (CRM Wizard) | `smart_intake.py` (Smart Intake Engine) |
|---|---|---|
| Conflict-of-interest check | ✅ (`/api/intake/conflict-check`) | ❌ |
| Pre-built case-type templates with seeded chronology | ✅ (7 templates) | ❌ |
| Billing setup in the same call | ✅ | ❌ |
| Bulk CSV import (many cases at once, from a spreadsheet) | ✅ | ❌ |
| Batch document upload (many files, async, one job per file) | ❌ (accepts refs only) | ✅ (ADR-0001's whole reason to exist) |
| OCR / classification / entity extraction | ❌ | ✅ |
| Case auto-created *from* document content | ❌ | ✅ |

Merging these into one pipeline would require either (a) bolting the CRM wizard's
conflict-check/templates/billing logic onto the async, job-queue-based Smart Intake flow — a large,
unscoped rewrite with no clear async equivalent for a synchronous conflict-check response the
current UI presumably expects inline — or (b) bolting Smart Intake's OCR/classification/extraction
pipeline into the synchronous CRM wizard request — which ADR-0001 explicitly rejected as a design
("holding a connection open for the minutes a 14-file batch would take is not viable"). Either
direction breaks a real, working capability to gain a code-organization convenience. This is exactly
the founder's named risk (*"različiti use-case-ovi... možeš napraviti regresiju tako što ćeš ukinuti
nešto što rešava poseban slučaj"*), and it is not hypothetical — every "CRM-only" capability in the
table above is real, tested, working code today.

## What the Bojan Gap Analysis got right, and what it missed

Right: a lawyer's actual day-to-day experience of "starting a new matter" today genuinely does
depend on which entry point they use — an inconsistency worth fixing. Missed: it read this as
evidence of incomplete convergence between duplicate systems, when the systems aren't duplicates —
they're two different starting conditions (*"I have a description"* vs. *"I have documents"*) for a
similar eventual goal (*a well-populated case in the system*).

## Recommendation

**Do not merge the two backends.** Instead, converge at the **UX entry-point layer only**: a single
"New Case" action in the product that asks (explicitly, or infers from what the lawyer does first —
starts typing vs. starts dragging files) which flow applies, and routes to the correct existing
backend — `intake.py` if the lawyer is describing a matter, `smart_intake.py` if the lawyer is
dropping documents. This gives the lawyer one mental model ("I start a new case here") without
requiring either backend to lose a capability the other doesn't have. This is a **UX/routing task**,
Small-to-Medium complexity, not a backend convergence project — re-scope accordingly rather than
carrying "unify the two intake systems" forward as a Sprint item in its original framing.

**One real, smaller gap worth fixing regardless of this decision:** `routers/intake.py`'s
`dokumenti: List[DokumentIntakeRef]` mechanism (attaching pre-uploaded documents to a
description-first case) and `smart_intake.py`'s document pipeline are not connected — a document
uploaded via Smart Intake's async pipeline cannot currently be referenced from the CRM wizard's
`kreiraj` call, or the reverse hasn't been verified. This is a narrow integration point, not a
merge, and should be scoped as its own small item if a lawyer's real workflow needs to start a case
by description *and* attach a document that's mid-OCR-processing in the same session — worth
confirming this actual need exists before building it.
