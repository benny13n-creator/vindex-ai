# Vindex AI — Predmet Ownership Authorization Pattern Recommendation

**Date:** 2026-07-23
**Status:** Architecture recommendation only. **No code changed by this document.** Per explicit instruction — analysis first, migration decision separately, implementation later.
**Trigger:** SEC-001 (`docs/security/SECURITY_GAP_REGISTER.md`, closed same day) was fixed by copying an existing correct pattern into two endpoints that were missing it. The founder's own framing of what that implies, kept verbatim because it's the right diagnosis: *"To znači da je problem bio human inconsistency risk. Ne samo coding bug."* Four independently-invented ways of answering the same question ("does this predmet belong to this user?") is not a stable state — it is SEC-001's actual root cause, and it will produce a SEC-001-v2 somewhere else unless the pattern itself is consolidated, not just the two instances that happened to be caught this time.

---

## 1. What the SEC-001 sweep actually found — precise survey, not an estimate

The full sweep (24 `{predmet_id}`-scoped mutation endpoints, `api.py` + all router files) surfaced **three genuinely distinct mechanisms answering the ownership question**, plus one mechanism that is often mistaken for a fourth but is actually a different question entirely. Precision matters here — conflating these would produce the wrong fix.

### Mechanism A — Inline `.eq("id", predmet_id).eq("user_id", uid)` chain
The most common pattern by count. Confirmed at:
- `api.py`: `get_predmet` (3161), `update_predmet` (3220), `update_kanban_faza` (3234), `predmet_confirm_links` (4853), and now `dodaj_belesku`/`sacuvaj_istoriju` (the SEC-001 fix itself).
- `routers/case_dna.py`: `refresh_case_dna` (686-691), `compare_docs` (853-854).
- `routers/case_pipeline.py`: `run_pipeline` (41-48).
- `routers/evidence.py`: `add_dokaz` (190-192), `reklasifikuj` (230-233).
- `routers/matter_intel.py`: `preflight_check` (422-426).
- `routers/predmeti_close.py`: `zatvori_predmet` (85-91).
- `routers/zadaci.py`: `ai_analiziraj_predmet` (470-474).
- `routers/zakon_monitoring.py`: `impact_analiza` (424-430).
- `services/legal_reasoning_engine.py`: `_fetch_predmet_and_genome` (added today, Phase 0 of the Legal Reasoning Engine — already following this pattern, for what it's worth).

**~15 independent, hand-written copies of the same three-line check.** Each one is currently correct. Each one is also an independent place SEC-001-v2 can happen the next time someone writes a new endpoint and doesn't happen to copy this exact snippet.

### Mechanism B — Named per-file helper functions
Three different files independently invented their own helper, each with a different name, signature, and error-handling convention:
- `routers/learning.py::_dohvati_predmet(supa, predmet_id, uid) -> dict` — raises `HTTPException(404)` internally, returns the row.
- `routers/saradnja.py::_proveri_vlasnistvo(supa, predmet_id, uid) -> dict` — same idea, different name, not verified whether its internal error-handling matches `_dohvati_predmet` exactly (out of scope for this survey, worth confirming before consolidating).
- `routers/case_intelligence.py::_gather_case_data(supa, predmet_id, user_id) -> dict` — does much more than ownership (fetches lessons/DNA/patterns/alerts/decisions in parallel), but the ownership check is bundled inside it as `predmet_row` with the identical `.eq("id",...).eq("user_id",...)` filter, and the caller checks `if not data["predmet"]: raise 404` itself rather than the helper raising.

**Three helpers, three names, at least one different error-handling convention, doing the same underlying query.** This is the clearest evidence for the founder's "human inconsistency risk" framing — not a missing check, but the same correct idea reimplemented independently three times, which is exactly the condition under which the fourth reimplementation (SEC-001's two endpoints) skipped it entirely.

### Mechanism C — Richer than ownership: owner-OR-collaborator
`routers/client_portal.py::generiši_portal_token` (216-244) checks direct ownership first, and if that fails, falls back to checking `predmet_saradnici` for a collaborator with the `"vodenje"` role. **This is not the same requirement as Mechanisms A/B** — it's a legitimately richer access model (the product has a real collaborator/sharing feature, `routers/saradnja.py`). Any consolidated pattern must not silently drop this case or force every predmet-scoped endpoint into a strict-owner-only model when some genuinely need "owner or authorized collaborator."

### Not a fourth ownership mechanism — `PermissionService.require(feature)`
Several endpoints combine an inline ownership check (Mechanism A) **with** `Depends(PermissionService.require("feature_key"))`. These answer **two different questions**, not one:
- `PermissionService.require` — *"is this user's subscription tier/addon/kill-switch state allowed to use this feature at all?"* (`shared/permissions.py:106-186`, reads `feature_registry`, has nothing to do with which specific `predmet_id` was requested).
- Mechanism A/B — *"does this specific `predmet_id` belong to this user?"*

Treating these as one of "four ownership patterns" (a natural read from the outside) would be a mistake worth correcting explicitly: they are orthogonal and both are needed together on most routes. The consolidation this document recommends is about Mechanisms A/B (and preserving C where it's genuinely required) — **not** about touching `PermissionService`.

---

## 2. Recommended pattern

**One FastAPI dependency, one canonical implementation, living in `shared/deps.py`** (the natural home — it already defines `get_current_user`, which this composes with):

```
async def verify_predmet_ownership(
    predmet_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Returns the predmet row if it belongs to the caller, else raises 404."""
    ...
```

Router-file endpoints adopt this by adding `predmet: dict = Depends(verify_predmet_ownership)` to their signature — FastAPI resolves `predmet_id` from the path automatically, the same way `Depends(get_current_user)` already works today. This directly replaces Mechanism A's ~15 duplicated inline copies and Mechanism B's 2-3 divergent helpers with one implementation that can be unit-tested once (mirroring `tests/test_sec001_predmet_ownership.py`'s approach) instead of trusted-by-inspection at every call site.

**`api.py`'s specific complication:** `api.py`'s endpoints do not use the `Depends(get_current_user)` idiom at all — they extract auth manually via `_require_auth(authorization: str = Header(None))`, a different foundational pattern from every router file. A pure `Depends()`-based dependency cannot be dropped into `api.py`'s existing endpoints without first migrating them to the router-style auth pattern (a separate, larger, higher-risk change not in scope here). Recommended split:
- A **raw, framework-agnostic core function** — `async def _verify_predmet_ownership_raw(supa, predmet_id: str, user_id: str) -> dict` (raises `HTTPException(404)`, returns the row) — this is the actual logic, and both styles can call it.
- The **`Depends()`-compatible wrapper** for router files is a thin adapter around the raw function.
- `api.py`'s manually-authenticated endpoints call the raw function directly with their already-resolved `user.id` — no FastAPI dependency-injection migration required, but they stop hand-writing the query.

**Mechanism C (owner-or-collaborator) gets its own, explicitly separate dependency** — e.g. `verify_predmet_access(predmet_id, user, required_role: str | None = None)` — built by composing the base ownership check with a fallback collaborator lookup, not by adding an optional flag to the ownership function that silently changes its meaning. Endpoints that only need strict ownership should not be able to accidentally opt into the looser collaborator-inclusive check by a misused parameter.

---

## 3. Middleware vs. dependency — dependency, not middleware

**Verdict: dependency. Middleware is the wrong tool here, for a specific reason, not just convention.**

Starlette/FastAPI middleware executes at the ASGI layer, before FastAPI's routing has bound typed path parameters — a middleware would have to regex-parse `predmet_id`/`klijent_id`/`dokument_id` out of the raw URL string itself, per route, to know which resource type and which ID it's looking at. That is strictly more fragile than what caused SEC-001 in the first place (a route-specific detail silently omitted), not less — a middleware regex that doesn't match a new route shape would silently skip the check with no error, whereas a missing `Depends()` on a new endpoint is at least a visible, reviewable omission in a diff. Dependencies are also the idiomatic, already-used-in-this-codebase mechanism (`PermissionService.require`, `get_current_user` are both already dependencies) — this recommendation is consistent with the codebase's own existing architecture, not a new paradigm.

---

## 4. Migration candidates (survey only — not proposing to touch these now)

Every Mechanism-A/B call site listed in §1 is a migration candidate once the canonical dependency exists — replacing 3-6 lines of hand-written query with one `Depends()` parameter, and deleting `_dohvati_predmet`/`_proveri_vlasnistvo` in favor of the shared version. `_gather_case_data` keeps its own function (it does much more than ownership) but should call the shared raw-ownership function internally instead of hand-rolling its own `predmeti` query.

**Not proposed for migration in this pass:** `client_portal.py`'s owner-or-collaborator check (Mechanism C) — correct as a distinct, richer requirement, should get its own dependency built alongside the base one, not folded into it.

**Explicitly out of scope for this document:** `klijent_id`/`dokument_id`-scoped endpoints were not swept (SEC-001's own scope was `predmet_id` specifically). The same reasoning almost certainly applies there too — worth its own, separate sweep before assuming the same consolidation plan transfers cleanly, rather than assuming it does.

---

## 5. What this does not solve

This pattern reduces *how many places the same mistake can independently happen* from ~18 (15 inline + 3 helpers) to effectively 1 canonical implementation — but it does not remove the underlying architectural fact named in SEC-004 (`SUPABASE_SERVICE_KEY` bypasses RLS entirely, so **some** application-layer check is still the only real boundary for every table). A consolidated dependency makes it far cheaper to *get right* and far easier to *verify* (one function to unit-test, one place to add a regression test per resource type) — it does not make the boundary self-enforcing the way real RLS would if the backend used a non-service-role connection. Both are worth doing; they are not substitutes for each other.

---

## Recommendation summary

1. Build `verify_predmet_ownership` (dependency) + `_verify_predmet_ownership_raw` (core function) once, in `shared/deps.py`.
2. Build `verify_predmet_access` (owner-or-collaborator) separately, composing the base function.
3. Migrate the ~15 inline call sites and 2-3 named helpers to the shared implementation, one file at a time, each with its own before/after regression test — same discipline as SEC-001's own fix, not a single sweeping refactor commit.
4. Do not use middleware.
5. Treat `klijent_id`/`dokument_id` as a separate, future sweep — do not assume this document's findings transfer without checking.

**This document does not authorize step 3.** Per the founder's explicit instruction, this is analysis only — the next message should say whether to proceed to SEC-002 now (as indicated) or return to this migration afterward.
