# Red Team Report - Word Add-in Task 01 Authentication

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork review)
**Date:** 2026-11-01
**Scope:** Draft Task 01 design and cited source. No source edits, live services, AI, or production systems were used.

## Verdict

**BLOCKING** — three HIGH findings affect authentication availability, token validation, and logout behavior; two MEDIUM findings affect origin handling and credential logging.

## RT-01 — The current CSP prevents the Office authentication flow from starting

**Severity:** HIGH

**Evidence:** `integrations/word_addin/taskpane.html:18-21` loads Office.js from `appsforoffice.microsoft.com`. `api.py:1224-1227` applies security headers globally; `api.py:1242-1253` omits that source and sets `frame-ancestors 'none'`. Word assets are mounted at `api.py:844-849`. `docs/security/EXTERNAL_DATA_INVENTORY.md:87-89` records the policy conflict. Microsoft documents Office dialog behavior in [Office dialog API guidance](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/dialog-api-in-office-add-ins).

**Failure scenario:** The host blocks Office.js and Office web framing, preventing the taskpane dialog login flow.

**Smallest correction:** Add Word-path-scoped CSP for Office.js and only required Office host framing origins; leave global CSP unchanged.

**Acceptance:** Header tests cover taskpane/commands/dialog; Office.js and dialog work on each claimed host; unrelated routes retain current CSP.

## RT-02 — Existing verifier cannot establish source-token expiry or revocation guarantees

**Severity:** HIGH

**Evidence:** `shared/deps.py:259-275` falls through to local JWT validation after Supabase `get_user` exceptions. Provider success returns identity, not claims (`shared/deps.py:263-267`); its dependency returns only user ID/email (`shared/deps.py:342-384`). `api.py` has a separate verifier/dependency (`213-279, 333-352`). `PermissionService` imports shared auth at `shared/permissions.py:54-55`.

**Failure scenario:** Exchange via shared auth could mint a Word session for a revoked/provider-rejected but locally signed token, and lacks verified expiry for a server-side cap.

**Smallest correction:** Route-specific verifier returns provider-confirmed identity and server-verified claims/expiry, rejects provider rejection/outage, and never falls back. Do not accept client expiry or change web login.

**Acceptance:** Valid session expiry is `min(source exp, now + max lifetime)`; missing/expired/malformed/revoked/unverifiable gets no row; provider rejection/outage with a signed token fails closed; web behavior unchanged.

## RT-03 — Logout does not stop requests that already passed authentication

**Severity:** HIGH

**Evidence:** `taskpane.html:256-260` clears local token and stops watcher. `adapter.js:67-69` only clears storage; it aborts prior analysis only when another analysis starts (`105-108`), and watcher stop only clears a timer/handler (`182-193`). Results can still render at `taskpane.html:262-274, 287-295`. Ambient auth precedes analysis with no revocation check before dispatch (`routers/copilot_ambient.py:59-82`).

**Failure scenario:** Logout after authentication may leave provider work running and allow stale response rendering.

**Smallest correction:** Abort all pane requests and suppress stale callbacks; add a server dispatch claim against a live session. Define claimed work as non-recallable and discard its response after logout.

**Acceptance:** Synchronized logout-before-claim prevents analysis/provider call; claim-before-logout may finish remotely but never renders/applies; later requests fail. Watcher shutdown suppresses stale results.

## RT-04 — Dialog origin lacks a fail-closed rule on older hosts

**Severity:** MEDIUM

**Evidence:** The design required origin validation but did not define clients without Dialog Origin 1.1; manifest declares no requirement set. Microsoft documents that `DialogMessageReceived.origin` may be undefined without Dialog Origin 1.1 in [Office.Dialog reference](https://learn.microsoft.com/en-us/javascript/api/office/office.dialog?view=word-js-preview).

**Smallest correction:** Require Dialog Origin 1.1; bind a one-time nonce; compare complete expected origin; reject missing/mismatched origin.

**Acceptance:** Missing/wrong origin or nonce creates no session; each supported host supplies expected origin and completes sign-in.

## RT-05 — Failed authentication can log a token prefix

**Severity:** MEDIUM

**Evidence:** The draft prohibits credentials in logs, but `shared/deps.py:324-339` records a token prefix in failure metadata; lines 353-356 pass the first 12 token characters.

**Smallest correction:** Word exchange must avoid that logging path and record reason/correlation only.

**Acceptance:** Captured application/access/audit logs for malformed and rejected exchange contain no token or prefix.

## Non-blocking observations

- The proposed modification to `shared/permissions.py` conflicts with active PR #66 and is unnecessary. A Word route can invoke `await PermissionService.require("copilot_ambient")(server_verified_user)`, sharing entitlement logic. PR #66 is open/Draft at `eb695ae8b14e96faae164196d67011d4c32f8701` and includes that shared file.
- Expand acceptance tests to include all token, provider, origin, leakage, and synchronized logout cases.
- Outside this auth review: existing prototype stores pasted tokens; global logout signs out all sessions; ambient usage is charged after provider execution; selection reads paragraph text rather than exact selected text; analyzer retrieval does not scope by `predmet_id`; citation matching is superficial; watcher uses selection-change events; manifest is development-only. These remain for later sequential tasks and are not re-audited here.

## What held up

Random opaque sessions, hash-only server storage, per-request revocation/expiry lookup, fail-closed issuance on DB errors, and per-pane logout are reasonable design choices if implemented as specified. No implementation exists yet to verify them.
