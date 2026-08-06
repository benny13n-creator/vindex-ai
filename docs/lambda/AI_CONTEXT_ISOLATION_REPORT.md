# AI Context Isolation Report — Program Lambda, Certification 002

## Question

Does any context-assembly code path — canonical (`build_case_context()`) or bespoke — ever let one user's
`predmet_id`/`klijent_id` cause ANOTHER user's case data, documents, Genome, contradictions, deadlines, or
clients to be fetched and fed to GPT?

## Canonical path: re-confirmed safe for the 5th+ consecutive sprint

`shared/case_context.py::build_case_context(predmet_id, uid, supa, ...)` is the single canonical context
source used by `case_commander.py`, `court_predictor.py`, `hearing_cc.py`, `cio.py`, `digital_twin.py`
(migrated across Tau 005-008 and Lambda 001). `_fetch_raw()` — the function every one of these calls
transitively — scopes the `predmeti` fetch by `.eq("id", predmet_id).eq("user_id", uid)`; a foreign
`predmet_id` returns `raw["predmet"] = None`, and `build_case_context` returns
`{"error": "predmet_not_found", ...}` rather than any real content. Every downstream field
(`readiness`/`missing_evidence`/`contradictions`/`deadlines`/`key_facts`/`relevant_documents`) is derived
from that same uid-scoped fetch — there is no code path in this function where a foreign case's real content
reaches the returned dict, let alone a GPT prompt. This was independently re-verified this sprint (not
assumed from prior sprints) while fixing `court_predictor.py`'s 7 insert sites (`IDOR_MATRIX.md` #15-21),
which rely on exactly this behavior via the file's own `_dohvati_case_context_ako_postoji()` wrapper.

## One real leak found and fixed this sprint

**`routers/multi_agent.py::run_agent` — billing agent + deadline agent context blocks**
(`IDOR_MATRIX.md` #7/#8). Unlike the canonical `build_case_context()` path, this file assembles its own
bespoke context per agent type. The main `predmet_ctx` block correctly re-verified ownership
(`.eq("id", req.predmet_id).eq("user_id", uid)`) before injecting case identity/documents/Genome into the
GPT prompt — but two SIBLING blocks, `billing_ctx` (real invoice line items, `billing_entries` table) and
`rokovi_ctx` (real hearing schedule, `rocista` table), queried by `predmet_id` alone, **unconditional on
whether the ownership check above actually succeeded**. A caller supplying a foreign `predmet_id` with
`agent: "billing"` or `agent: "deadline"` would have that foreign case's real billing/deadline data injected
into the GPT prompt and summarized back in the response — a genuine cross-tenant AI-context leak, not a
theoretical one. **Fixed**: both blocks now gated on a `predmet_verifikovan` flag set only when the
ownership check truly passed.

## GPT boundary re-confirmed, not re-litigated

Every deterministic-cap mechanism this program has built across 5 modules (Court Predictor, Hearing CC, CIO,
Digital Twin, ×2 shapes) continues to reuse the exact same `{CRITICAL_GAP: 50, BLOCKED: 65}` thresholds from
`shared/case_readiness.py` — confirmed unchanged this sprint. GPT is never given write access to
readiness/priority/risk scores in any module touched this sprint; the fixes made here are all about which
DATA reaches the prompt, not about what GPT is allowed to conclude from it.

## Known, pre-existing, not-fixed-this-sprint gap

`routers/dokument.py`'s Pinecone session-based document Q&A (`/pitanje`, `/analiza`, `/rokovi`,
`/klasifikuj-sesija`) is the one place in the app where a document's actual text reaches a GPT call with
**zero `user_id` binding** — isolation is 100% "the `session_id` is an unguessable UUID," not authentication.
This is `SEC-039` (already tracked, High severity, opened 2026-08-02), independently re-confirmed this
sprint by both the Storage Auditor and this report. Not re-opened as a new Lambda finding — see
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`.

## Verdict

- **Canonical context path (`build_case_context`)**: CERTIFIED, 5th consecutive sprint of independent
  verification, zero leak found.
- **`multi_agent.py` billing/deadline context**: FIXED this sprint, regression coverage via a new dedicated
  test file, `tests/test_lambda002_multi_agent_context_leak.py` (4 tests — 2 prove the leak is closed by
  inspecting the actual prompt string sent to GPT, 2 prove the legitimate-owner path is unaffected; see
  `REGRESSION_TEST_REPORT.md`).
- **`dokument.py` session-based Q&A**: ARCHITECTURAL DEBT, pre-existing (`SEC-039`), re-confirmed not fixed.
- No other GPT-calling module examined this sprint (`copilot.py`'s various intent handlers, `court_predictor.py`,
  `digital_twin.py`) was found to inject foreign-case content into a prompt.
