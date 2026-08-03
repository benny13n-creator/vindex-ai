# Architecture Decision — BC-001/BC-002: Smart Intake + Draft Staging UI

**Mission:** Operation Beta Closure (BETA-006), 2026-08-03.

---

## Decision 1: Additive entry point, not a replacement

Smart Intake's new panel is reached via two NEW buttons ("+ Iz dokumenta", "Otpremi dokumenta") placed
next to the existing "+ Novi predmet"/"Otvori novi predmet" buttons that open the older, name-first CRM
Intake Wizard. The older wizard is untouched — same function (`intakeOtvori()`), same modal, same
5-step flow. **Rejected alternative**: repointing the existing wizard's Step 3 (optional single-file
upload) to call Smart Intake instead. Rejected because that step serves a genuinely different use case
(a supplementary attachment to a description-first flow, one file, PDF/DOCX only) from Smart Intake's
document-first model (the documents ARE the case, multiple files, includes images) — conflating them
would have required redesigning the existing wizard's Step 3 semantics, violating "do not redesign."

## Decision 2: Reuse `.intake-*` CSS classes verbatim

The new panel (`#si-overlay`) uses the exact same class names as the existing Intake Wizard
(`.intake-overlay`, `.intake-panel`, `.intake-upload-zone`, `.intake-field`, `.intake-back-btn`,
`.intake-next-btn`, `.intake-step-dot`) rather than introducing new CSS. This was verified safe before
use: these classes are referenced generically (never scoped to a specific element ID), so a second,
independently-IDed panel can reuse them without collision. Result: the new panel is visually
indistinguishable in style from existing UI — "respect current design system" achieved by literal reuse,
not by matching a style guide from scratch.

## Decision 3: Sequenced finalize calls, client-linking fields sent once

`FinalizeReq` accepts `klijent_strana`/`klijent_ime_override` on every call, and the backend's
client-linking step runs unconditionally (both on case-creation and on attach-to-existing calls) — this
was read directly from `routers/smart_intake.py` before writing the UI, not assumed. If the new UI sent
these fields on every finalize call in a multi-document batch, each additional document would trigger a
redundant find-or-create-client + `predmet_klijenti` insert (no uniqueness constraint visible on that
insert), risking duplicate client-link rows. **Decision**: the UI includes `klijent_strana`/
`klijent_ime_override` only on the FIRST finalize call (the one without `predmet_id`, which creates the
case); every subsequent call in the same batch sends only `predmet_id`. This was verified as correct by
reading the exact backend code path, not by testing against a live instance (no live DB access in this
environment) — the reasoning is recorded here specifically so a future session doesn't "simplify" this
back to sending the fields every time without knowing why that would be wrong.

## Decision 4: Adaptive polling interval, not a fixed one

`GET /api/smart-intake/jobs/{id}` is rate-limited to 60/minute per user (confirmed via
`@limiter.limit("60/minute")` on the endpoint). A fixed short poll interval (e.g., every 2 seconds)
would exceed this limit for any batch beyond ~2 files sustained over a minute — a real risk given the
Beta Critical Path's own "20 new scanned documents arrive" scenario. **Decision**: poll interval scales
with the number of still-active jobs (`Math.max(4000, activeCount * 1200)` ms), converging to fast
polling as fewer jobs remain. This is a client-side defensive measure, not a backend change — no
`smart_intake.py` code was touched.

## Decision 5: Draft-approval UI states the confidence-threshold nuance honestly

`POST /api/staging/{id}/approve` only promotes a draft into the searchable case record
(`predmet_dokumenti`) if `confidence_score >= 0.85` at approval time — verified by reading
`_promote_staged_draft_to_pinecone`'s exact gating logic directly, which also corrected an imprecise
claim from this same engagement's earlier `HIDDEN_FEATURES_REPORT.md` update (which described the
promotion as unconditional). **Decision**: the new UI surfaces the backend's own returned message
verbatim (which already states this nuance in Serbian) rather than showing a generic "Approved" success
state that would misrepresent what actually happened for a low-confidence draft.

## Decision 6: Draft-approval UI scope kept deliberately minimal

No polling, no wizard, no multi-step flow — a list plus two buttons, auto-loaded when a case opens (same
hook as the existing Matter Intelligence auto-load). This matches Priority 2's explicit instruction
("build only the minimum production-ready UI") and reflects a real difference from Smart Intake: staged
drafts are already fully processed by the time a lawyer would look for them (no async job to track),
so a review list is structurally sufficient — building anything more elaborate would have been scope
creep against the mission's own stated priority ordering.

---

## What was NOT decided (correctly left open)

Whether the older upload paths should eventually be deprecated in favor of Smart Intake becoming the
sole document-intake entry point. Tonight's build is additive specifically to avoid pre-empting that
future product decision — see `docs/product/UPDATED_BLOCKER_REPORT.md`.
