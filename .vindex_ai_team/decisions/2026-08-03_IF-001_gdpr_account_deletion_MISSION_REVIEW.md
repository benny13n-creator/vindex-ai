# Mission Review — IF-001: Self-service GDPR account deletion

**Mission Board entry:** `MISSION_BOARD.md`, IF-001.
**Executed by:** Operation Invisible Features (BETA-003), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The finding
`DELETE /api/gdpr/account` (`routers/gdpr.py`) is real, working, and safe: anonymizes the profile's
email/name, deactivates email notifications, writes to the immutable audit log, and refuses to run
against a founder account. It had zero frontend callers.

The evidence for priority came from an unexpected place: `static/bezbednosni-list.html:60` — the
**public** security whitepaper page — explicitly states *"Zahtev za brisanje naloga... se izvršava
odmah po odobrenju... Samouslužno dugme za ovu radnju je u pripremi; do tada zahtev ide putem email
verifikacije"* ("a self-service button for this is in preparation; until then, the request goes via
email"). This is a published compliance document making a forward-looking promise to real users —
wiring the already-working endpoint to a real button fulfills an existing public commitment, not a
speculative nice-to-have.

### What was checked before assuming this was the right fix
The census initially flagged `/api/gdpr/export` (data export) as equally dead alongside account
deletion. Before wiring both, checked the Settings tab directly and found an **existing, working**
"Export podataka" button (`index.html:3396-3402`, `exportSviPodaci()` → `/api/export/complete`) that
already does a richer export (8 tables including documents metadata, notes, hearings, chronology —
`routers/data_export.py`) than `/api/gdpr/export`'s narrower 5-field JSON. Wiring the GDPR router's
export endpoint on top would have shipped a genuine duplicate for no lawyer benefit — same "verify
before connecting" discipline this whole engagement has applied throughout. **Only account deletion
needed a new button; export did not.**

### Design choice: confirmation UX
Account deletion is irreversible. Matched this codebase's existing convention for irreversible
destructive actions (plain `confirm()` with explicit "Ova akcija je nepovratna" wording, as used
elsewhere for document/comment/hearing deletion — `vindex.js:13211`, `:4355`, `:4432`) rather than the
lighter `_vxConfirm()` helper used for reversible actions. The confirmation text explicitly states what
happens (email/name anonymized) and what doesn't (predmeti/klijenti/dokumenti retained per Zakon o
advokaturi) — matching the backend's own returned message, so the lawyer isn't surprised either way.

---

## Implementation
`index.html` — new "Brisanje naloga" row in the existing Podešavanja → Nalog settings section.
`static/vindex.js` — new `obrisiNalogSelfService()` function: confirm → `DELETE /api/gdpr/account` →
on success, toast + `doLogout()` (the account is anonymized, no reason to stay authenticated) → on
failure, toast with the error, button re-enabled.
`static/sw.js` — `CACHE_NAME` bumped (`vindex-v87` → `vindex-v88`) per this project's standing rule
that frontend changes require a service-worker cache bump or users won't see them.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer wants to exercise their GDPR right to erasure on their
own Vindex account (not their clients' data -- their own account).
Before: no self-service option existed; the published security whitepaper
told them to email privacy@vindex.ai and wait.
After: Settings -> "Brisanje naloga" -> confirm -> account anonymized
immediately, same guarantee the backend already provided, now actually
reachable.

Manually verified: node --check static/vindex.js (syntax valid); backend
endpoint unchanged, existing tests/test_gdpr_delete.py (backend-only)
unaffected.
```

### Regression suite
No backend code changed — full suite re-run as this mission's Phase 7 requirement: 2306 passed, 1
skipped, 0 failed (unchanged from before this mission). Frontend has no automated test harness in this
repo (vanilla JS, no build step) — verified via `node --check` for syntax validity; not live-tested in
a browser this session (no browser available in this environment).

### Rollback strategy
Pure frontend addition (one HTML row, one JS function). No backend change, no schema change. Revert
by removing the new button/function; the underlying endpoint is untouched either way.

---

## Lessons Learned
The census's two GDPR findings looked identical at a glance ("both dead, both need a button") — they
weren't. One was a genuine gap with public evidence of a promised fix; the other was a working
duplicate of a better, already-shipped feature. Worth the reminder this session keeps producing: verify
each finding individually before acting on a list, even when items look superficially the same.

## Founder Summary
A lawyer can now delete/anonymize their own Vindex account from Settings — the backend already did
this safely; it just had no button. This directly fulfills a promise already made in the public
security whitepaper. Data export was checked and found to already have a better button live elsewhere
— not touched, to avoid shipping a duplicate.
