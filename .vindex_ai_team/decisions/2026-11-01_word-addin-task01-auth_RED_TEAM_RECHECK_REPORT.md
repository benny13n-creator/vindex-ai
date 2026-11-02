# Red Team Re-review - Word Add-in Task 01 Authentication

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork review)
**Date:** 2026-11-01
**Scope:** Revised Task 01 auth design and current Word/auth/retrieval source. No files were edited; no tests, live auth, AI, production, or network services were used.

## Verdict

**BLOCKING** — two HIGH design gaps remain.

## RT-01 — Word framing policy is ambiguous and can remain blocked

**Severity:** HIGH

**Evidence:** `api.py:1238` sets `X-Frame-Options: SAMEORIGIN`, and `api.py:1242-1253` sets global CSP `frame-ancestors 'none'` on every response. `taskpane.html:20` and `commands.html:14` load Office.js from `appsforoffice.microsoft.com`; Word files are mounted at `api.py:844-849`.

**Failure scenario:** If a Word-scoped CSP is added as a second header, the global `frame-ancestors 'none'` still blocks Office. If it replaces the global CSP but X-Frame-Options remains, hosts enforcing it can still block the taskpane. Word auth also requires CSP `connect-src` to allow Supabase.

**Smallest correction:** For Word HTML entry responses, replace the global CSP with one effective Word-specific policy, remove X-Frame-Options only on those entry responses, preserve Supabase connections, allow the current Office.js source, and add only verified Office host origins. Keep unrelated routes unchanged.

**Acceptance:** Inspect effective headers on taskpane/commands/auth dialog; verify Office.js, Office framing, Supabase auth, and dialog flow in each claimed host; verify unrelated routes retain current policy. Inspect redirects/upstream responses for conflicting headers.

## RT-06 — A request-level claim does not cover retried provider dispatch

**Severity:** HIGH

**Evidence:** `services/ambient_analyzer.py:58-63` decorates the OpenAI request with `@llm_retry`. `shared/llm_retry.py:32-44` allows three attempts. `analyze_paragraph` runs the helper through `asyncio.to_thread` at `services/ambient_analyzer.py:195-199`. The RAG pipeline in `app/services/retrieve.py` also makes embeddings and reranking/chat calls, including worker-thread calls.

**Failure scenario:** A route-level session claim happens before analyzer start. The first provider request fails; the user logs out; an automatic retry or RAG provider call can still send the same legal text after revocation. Client abort does not stop a synchronous SDK request or hidden retry.

**Smallest correction:** Require an atomic live-session claim immediately before every outbound provider attempt in the Word pipeline, including embeddings/completions/reranking and each retry. Disable hidden SDK retries for Word calls and make revoked-session failure non-retryable.

**Acceptance:** Mock first-attempt failure, revoke before retry, and assert the retry and all later provider calls do not occur. Cover embedding and completion retries. A provider attempt whose claim wins before logout may finish, but its result never reaches the pane after logout.

## Corrections that held at design level

- **RT-02:** Revised design requires a Word-specific verifier, provider success, strict signed issuer/audience/subject/future-expiry validation, no fallback, and no unchanged call to the existing verifier helpers. It must also test wrong issuer/audience, absent/invalid expiry, provider outage, and exact `min(exp, now + max)`. Existing `verify_token_local` does not enforce all those requirements as-is.
- **RT-04:** Revised design requires a runtime Dialog Origin 1.1 capability check and fail-closed origin+nonce validation. Host compatibility remains unproven until real testing.
- **RT-05:** Word exchange avoids the shared failed-login logger that stores a token prefix. Tests must capture application, access, and audit logs.
- PR #66 overlap is avoided: no `shared/permissions.py` edit. Word routes must explicitly pass the session-derived user into `PermissionService.require(feature)`.

No source code has been implemented or changed. The design should be revised once more, then independently reviewed before Security and Database gates.
