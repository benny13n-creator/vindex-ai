# AI Context Isolation — Program Lambda, Certification 003

**Agent**: AI Isolation Auditor — named in this sprint's own brief as the most important role. Task: prove
GPT never sees another user's/case's/firm's data, by tracing the actual literal prompt string sent to GPT
for every named module, not just the DB query that feeds it.

## Finding — FIXED: `shared/case_context.py::get_document_full_text()` ignored its own `uid` parameter

Document Visibility Engine, Layer 5 — the platform's own documented on-demand deep-retrieval safety net,
guaranteeing (per its own docstring) that "no relevant document is PERMANENTLY invisible" at 500-1000+
document scale. The function accepted a `uid: str` parameter but never referenced it in the query — filtered
only `.eq("id", dokument_id).eq("predmet_id", predmet_id)`, no `.eq("user_id", uid)`. The docstring's own
claim of being "RLS-scoped" is false: this backend uses the service-role Supabase client everywhere, which
bypasses RLS entirely (established fact since Certification 002's own `RLS_CERTIFICATION.md`).

**Not currently exploitable**: repo-wide grep (re-verified independently by Agent 8, including JS/TS/scripts/
any dynamic-dispatch path) confirmed zero call sites anywhere outside `shared/case_context.py`'s own
docstring and `tests/test_tau002_case_context.py`. Dormant — but a live latent gap sitting in exactly the
function the codebase's own scale-safety documentation points to, one wired-up endpoint away from a real
cross-tenant document-text leak.

**Fix**: added `.eq("user_id", uid)` to the query — the same pattern every other `predmet_dokumenti` query in
this file already uses where applicable. Zero behavior change to any live path (none exists). **Status:
FIXED.** Proof: `tests/test_tau002_case_context.py::test_get_document_full_text_rejects_foreign_owner` (new)
— a foreign owner gets `{"found": False}`, the legitimate owner still gets the real content; plus the
pre-existing `test_get_document_full_text_not_found_is_explicit_not_an_exception`/
`test_not_included_documents_are_retrievable_via_layer_5` re-verified unaffected (30/30 pass in that file).

## Everything else — CERTIFIED, re-verified fresh (not cited from prior sprints without re-checking)

| Module | What was traced | Evidence |
|---|---|---|
| `build_case_context()` | `predmeti` gate query scoped `user_id`+`id`; early-return before any unscoped-by-design sibling query is used | `case_context.py:156-157,368-369` |
| CIO daily cache | Keyed `(user_id, datum)` both read and write | `cio.py:447-448,487` |
| Case Commander morning cache | Keyed `(user_id, datum)` | `case_commander.py:906-907` |
| Morning Briefing cache | Keyed `(user_id, datum)` | `morning_briefing.py:1000-1001` |
| CIO portfolio loop | Every query scoped `.eq("user_id",uid)`; `_kompaktan_predmet()` pure per-case, no shared accumulator | `cio.py:240,263,272,281,300` |
| Court Predictor `opponent_intel`/`confidence_check` | Cross-portfolio queries scoped `.eq("user_id",uid)`, not global | `court_predictor.py:1206,1473` |
| Memory Graph ("Firm Brain") | Genuinely firm-scoped: `_get_firma_id()` derives `kancelarija_id` from the CALLER's own membership only | `memory_graph.py:55-76,170,180,237,332,342` |
| Digital Twin | Both `predmeti` ownership gates scoped, raise/return before use (re-verified again after the hoisting fix, see `TENANT_ISOLATION_REPORT.md`) | `digital_twin.py` |
| Strategy Simulator | Both `predmeti` queries scoped, raise before use — the cleanest pattern found in the whole review | `strategy_simulator.py:122-130,231-237` |
| Hearing CC | `_load_all_context`'s `predmet_klijenti→klijenti` join has no ownership filter (matches Certification 002's already-named debt) — but its one call site gates on `ctx["predmet"]` and raises 404 BEFORE `_build_prompt()` runs | `hearing_cc.py:197-199,364-373` |
| Copilot `_load_predmet_context`/analiza/plan handlers | Fetch-then-gate pattern (now hoisted, see `TENANT_ISOLATION_REPORT.md`) | `copilot.py` |
| `shared/ai_provenance.py` contextvars | Genuinely asyncio-Task-isolated, never mutates a shared default in place | `ai_provenance.py:56-57,72,94-107` |

No cross-case, cross-user, or cross-firm leakage found in any portfolio-wide loop. No stale-cache tenant bleed
in any of the module-level daily caches (all keyed by a full `(user_id, date)` pair). No accidental-merge bug
in any prompt-string assembly path examined.

## The one CRITICAL finding this sprint — belongs to the cache scope, cross-referenced here

The single most severe finding of this entire multi-week engagement — `main.py::ask_agent`'s response cache
leaking one firm's private institutional-memory/document content to a completely unrelated firm with zero
guessed identifiers — was found by the Cache & Session Isolation auditor (Agent 7), not this role, since it's
a caching-layer bug rather than a context-BUILDING bug (the context builders themselves, listed above, are
all correctly scoped; the leak was entirely in what got cached and served back afterward). Full detail in
`CACHE_ISOLATION_REPORT.md`. Noted here because it is, in the end, GPT-adjacent content reaching an
unauthorized tenant — exactly this role's own charter — even though the root cause sits one layer downstream
of prompt construction.
