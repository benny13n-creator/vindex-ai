# Current State — Workflow Fragmentation

**Mission:** Operation Beta Lockdown's Third Objective, 2026-08-03: whenever multiple implementations
solve the same problem, document current/alternative implementation, evidence, advantages,
disadvantages, migration risk, and a recommendation — without merging automatically. Both cases below
were first found during Operation Invisible Features and are reconfirmed unchanged here.

---

## 1. Client CSV/XLSX import

**Current implementation (live)**: `klijenti/router.py:1435`'s `POST /klijenti/import-csv` — a
one-shot import with fixed expected columns, no preview step, no confirmation before committing.
Reachable from the UI (`static/vindex.js:4946`).

**Alternative implementation (dead)**: `routers/import_klijenti.py` — a 3-step flow: download a
template → upload + preview with column-mapping → execute only after explicit lawyer confirmation.
Zero frontend callers.

**Evidence**: both fully coded, both real. The live one is simpler and faster for a lawyer with a
correctly-formatted file; the dead one is safer for a lawyer with an unfamiliar or inconsistently
formatted export from another system (a very common real scenario — client lists exported from a prior
practice-management tool, an accountant's spreadsheet, etc.).

**Advantages of the live (current) implementation**: fewer steps, faster for the common case.

**Disadvantages of the live implementation**: a column-mapping mismatch fails silently or imports data
into the wrong fields, with no preview to catch it before committing — for bulk client data, an
incorrect import could misattribute contact information across a lawyer's client base.

**Advantages of the dead (alternative) implementation**: preview-before-commit eliminates the exact
failure mode above; explicit column mapping handles files that don't match the expected format exactly.

**Disadvantages of the alternative implementation**: more clicks for the common case where the file is
already correctly formatted.

**Migration risk**: replacing the live flow outright would change existing lawyer muscle memory (if any
lawyers have already used it) and requires frontend work either way (adding a preview step to the
current flow, or building UI for the safer flow). Offering both as separate "quick import" / "guided
import" options avoids a hard replacement but adds UI surface and a duplicate-maintenance burden.

**Recommendation**: not made unilaterally, per this mission's own rule. The evidence favors the safer
flow becoming primary given bulk client data is exactly the kind of import where a silent mapping error
has real downstream cost (wrong contact info reaching wrong clients) — but whether to replace, augment,
or retire the alternative is a founder call (`BLOCKER-4`).

---

## 2. WhatsApp notification delivery

**Current implementation (live)**: `routers/sms.py` — a single `whatsapp: bool` flag on the SMS
delivery profile (`vindex.js:2836`/`:2858` → `POST /sms/telefon`), read to route messages via
WhatsApp-formatted numbers through the same underlying Twilio integration (`sms.py:201-202,285-287`).

**Alternative implementation (dead)**: `routers/whatsapp_notif.py` — a dedicated subscription system
with its own tables (`whatsapp_pretplate`, `whatsapp_send_log`) and granular per-notification-type
preferences (deadline reminders, daily briefing, etc., independently toggleable). Zero frontend callers.

**Evidence**: both real, both built on the same Twilio integration underneath. The live system answers
"WhatsApp or SMS?" as a single yes/no; the dead system additionally answers "which specific
notification types via WhatsApp?"

**Advantages of the live (current) implementation**: simple, already covers the core lawyer need
(choose a delivery channel), no evidence of demand for finer control found in this investigation.

**Disadvantages of the live implementation**: cannot let a lawyer choose (for example) deadline
reminders via WhatsApp but the daily briefing via SMS — an all-or-nothing choice.

**Advantages of the alternative (dead) implementation**: finer control, if a real lawyer ever wants it.

**Disadvantages of the alternative implementation**: more complex data model (2 extra tables) and UI
surface for a granularity level with no evidenced demand.

**Migration risk**: low either way — this is additive granularity, not a behavior change to existing
messages. Retiring the dead system removes code with no live users; reconnecting it adds a settings
panel with no confirmed lawyer request behind it.

**Recommendation**: not made unilaterally. The evidence leans toward retiring the dead system as
unnecessary complexity rather than reconnecting it, since the live system already satisfies the core
need with less code to maintain — but confirming there's truly no demand for per-type granularity
before deleting anything built is the founder's call (`BLOCKER-5`).
