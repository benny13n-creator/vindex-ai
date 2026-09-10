# TASK 5 — Canonical AI case context freshness (investigated + fixed + live-verified)

Mandate: prove whether the AI actually sees newly-added facts, per the freshness gap flagged (but not tested) at the end of Task 0.

## Root cause (PROVEN, not a staleness/timing issue)

This is **not** an event-timing problem — Task 2 already proved the event pipeline fires within seconds. It is a **structural absence**: `/api/pitanje` (api.py:3592) never read `predmet_dokazi` (the facts table `add_dokaz` writes to) at all, at any freshness.

Traced the full context-injection code path in `pitanje()` (api.py:3592-3949) end to end:
- The only predmet-scoped context sources were `predmet_beleske` (notes) and `predmet_istorija` (past Q&A) — confirmed by reading the entire function body; zero references to `predmet_dokazi` or `case_actions` anywhere in it.
- The separate, richer `shared/case_context.py::build_case_context()` (used elsewhere, e.g. `routers/case_commander.py`) is never called by `/api/pitanje` at all.
- Even if it were called, it wouldn't have helped: its own `predmet_dokazi` query (`case_context.py` L229-234) selects only `id, snaga, kategorija, pravni_element, izvor_snage` — it never selects `tvrdnja` (the actual fact text). So a fact's existence is knowable there, its content is not.

**Two independent absences, same symptom**: a lawyer's manually-entered fact was invisible to `/api/pitanje` regardless of how the AI context assembly evolves, because the specific field carrying the fact's content was never queried by either path.

## Live proof (before fix)

Test predmet `93d8e165-281c-4717-bdfa-828dae879c6a` (same isolated test account used throughout this sprint). Added a fact with a distinctive, unmistakable token (a contractual penalty amount, `73492.17`, that cannot be guessed or hallucinated to match by coincidence):

1. `POST /api/evidence/predmeti/{id}/dokaz`: `"Ugovoreni ugovorni penal iznosi tačno 73492.17 RSD po danu kašnjenja, prema članu 7 ugovora."` → `200`, evidence written, Task 2's event fired (confirmed same mechanism as before).
2. Asked `/api/pitanje` (`predmet_id` set) "Koliki je ugovoreni penal po danu kašnjenja u ovom predmetu?" — twice, once immediately and once after a clean 90s+ wait (ruling out any residual timing effect): both times, `kontekst_predmeta: true` (context WAS injected — just not this fact) and the answer said the amount **"nije eksplicitno definisan u dostavljenim izvorima."**

## Fix

`api.py::pitanje()` — added a third context source alongside the existing `beleske_res`/`istorija_res` queries: `predmet_dokazi.select("tvrdnja, snaga, kategorija")` (own-tenant, non-deleted, capped at 20 most recent). Piped through the **exact same, already-proven security pipeline** used for beleske/istorija — no new trust boundary invented:
- Each fact individually quarantined via the existing `_ctx_bezbedan()` injection-guard check (same function, same threshold, same fail-closed-on-analysis-failure behavior).
- Surviving facts joined and wrapped with the same `zapakuj_nepoverljivo(..., IZVOR_BELESKA)` non-instructional packaging as beleske/istorija, under a new `"Utvrđene činjenice u predmetu:"` heading, appended to the same `delovi` list.
- Gate condition (`if beleske_tekst or istorija_tekst or dokazi_tekst`) and `_kontekst_ubacen`/log line extended to include the new source.

This reuses this codebase's own established T2/T3 authority-boundary discipline (documented extensively in the surrounding code as B-U-004-F3/F1) rather than inventing a new content channel — a manually-entered fact gets exactly the same non-instructional, quarantine-then-package treatment a note or chat-history line already gets.

## Live proof (after fix)

Server restarted with the fix loaded (`[EVENT_BUS] dispatch loop pokrenut` confirmed at startup). **Same predmet, same question, no new fact added** (proving the fix, not a fresh write):

`odgovor`: *"Ugovoreni ugovorni penal po danu kašnjenja iznosi **73492.17** RSD."* — exact match, `kontekst_predmeta: true`.

Clean before/after: same predmet, same fact, same question, only the code changed between the two runs.

## What was NOT done in this pass (honest scope disclosure)

- No adversarial injection test specifically targeting the new `dokazi_tekst` channel (e.g. a `tvrdnja` crafted to look like an instruction) — it reuses the same `_ctx_bezbedan`/`zapakuj_nepoverljivo` machinery already adversarially tested for beleske/istorija (per the B-U-004-F3 comments in the surrounding code), but this specific new call site was not independently re-attacked tonight.
- `predmet_dokazi` rows sourced from an uploaded document's own auto-classification (not just manual entry) were not separately verified — the fix reads the table generically, so it should apply equally, but this was not live-tested.
- The 20-row cap on how many facts are included is untested at scale (a case with 200+ recorded facts would silently truncate to the 20 most recent — reasonable default, not verified against a real large case).

## TASK 5 GATE DECISION

**PASS.** Root cause found (two independent structural absences, not a timing gap), fixed with a minimal, security-consistent change reusing existing trust-boundary infrastructure, and proven with a clean before/after live A/B test using an unmistakable fact token.

Local commit only. No push, no deploy.
