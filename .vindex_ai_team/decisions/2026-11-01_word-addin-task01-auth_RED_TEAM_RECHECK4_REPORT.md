# Red Team Re-review 4 — Word Add-in Task 01 Authentication

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork review)
**Date:** 2026-11-01
**Verdict:** FREEZE READY at the design gate

## Scope and result

The reviewer used the explicit Vindex checkout at C:/Users/Benny/Vindex-Codex-Independent, read the operating protocol, review gates, latest Task-01 product/technical/architecture/UX documents, prior Red Team reports, and relevant auth, rate-limit, middleware, permission, CSP, and Word prototype source. It made no edits, ran no tests, used no live auth or AI, and made no network calls.

No remaining Critical or High findings were found among the requested issues. This is a design verdict only; no Word API route or implementation exists to verify yet.

## RT-08 closure

The latest Product Specification criterion 6 and Technical Design section 2 require:
- an exact /api/word/ segment carveout that skips only bearer parsing and continues through call_next, retaining SlowAPI IP/route limits;
- general account policy after provider identity verification for session issuance and after Word-session validation for session management/non-AI operations;
- the existing AI user bucket plus anomaly record/check for analysis/rewrite before analyzer/provider work;
- explicit route operation classes and a server-derived account identity shared across sessions and IPs;
- protected Word API routes to require an opaque Word session; and
- ordinary auth handling for paths such as /api/wordsmith.

Source confirms the current issue in api.py:1064-1109 and 1148-1207; there are no Word API routes yet. Product Spec criterion 12 includes rate-policy and boundary tests. This closes RT-08 at design level only.

## Other requested checks

- CSP/XFO: Technical Design requires one Word-specific effective CSP for /word_addin entry responses, scoped X-Frame-Options removal, and verified host origins/response chains. Actual host support remains unverified.
- Provider retries: Each embedding, completion, reranking, or application retry requires a fresh live-session claim; hidden SDK retries are disabled, and results are suppressed after logout.
- Dialog callback: Dialog Origin 1.1 capability, exact origin and nonce checks, and fail-closed behavior are specified; host compatibility remains unverified.
- Token logging: Word failure logs exclude token material. Legacy shared auth still logs prefixes, so implementation tests must cover all Word exchange/protected-path logs.
- PR #66 overlap: Design avoids editing shared/permissions.py and requires explicit server-verified identity to PermissionService.

## Medium conditional deployment caveat

The account-rate and anomaly counters are process-local (api.py:1064-1065; security/anomaly_detection.py). gunicorn.conf.py defaults to one worker, but WEB_CONCURRENCY or replicas can change that. Cross-worker account-wide enforcement is UNKNOWN until deployment values are verified. The smallest safe condition is to prove a single worker for a controlled pilot or obtain approval for a shared counter before enabling multiworker scaling. This is not a Critical/High design blocker under the repository default.

The reviewer did not recheck remote PR #66 status; its status/head in the execution-state record remains the earlier Task-00 observation and should be reverified before implementation integration.