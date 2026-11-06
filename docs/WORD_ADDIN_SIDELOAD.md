# Vindex AI — Word Add-in local testing and sideload

Status as of 2026-11-02: the Word-specific authentication flow, explicit selected-text analysis, optional selected-matter context, conservative source-identity presentation, and lawyer-controlled rewrite proposal/apply boundary are implemented with deterministic tests. The code uses a same-origin Vindex sign-in dialog, a pane-local opaque session, exact-origin callback checks, legacy-token cleanup, server-side expiry/revocation, and matter access checked through the canonical Vindex ACL.

**Real Microsoft Word authentication or rewrite/apply has not been run. Do not use this build with real user credentials yet.** The word_sessions table migration is not present because PR #66 reserves migration 146, and the Word frame-ancestor allowlist is intentionally fail-closed until exact host origins are verified. AI analysis and rewrite fail closed until PR #66 is merged and its budget middleware contract is verified.

## Local HTTPS server

The existing development script is:

    python scripts/run_word_addin_dev.py

It serves the FastAPI app and Word assets over local HTTPS. The Word entry pages deny framing unless WORD_ADDIN_FRAME_ANCESTORS contains an explicit, verified HTTPS origin list. Do not add guessed Office origins. Confirm the actual parent origin for the intended Word host before configuring it.

The authentication endpoint also requires the session registry table. Until its reviewed migration is resolved and applied by an authorized operator, session issuance fails closed.

## Windows Word development sideload

The `manifest.xml` file is for local development only. It points to localhost and has a placeholder GUID. Completing sign-in is not currently supported in that configuration because the storage migration and host allowlist are pending.

The existing Word Desktop sideload route is:

1. Word → **Insert** → **Add-ins** → **My Add-ins** → **Upload My Add-in**.
2. Select `integrations/word_addin/manifest.xml`.
3. Open the **Home** tab, then the **Vindex AI** ribbon group.

No installation or live Word validation has been performed for this implementation. The locally installed Windows Word version is 16.0.20326.20232. Word for Mac and Word on the web are NOT_RUN.

## Current taskpane behavior

- Sign-in uses the existing Vindex identity in a same-origin Office dialog. There is no pasted-token field.
- The Add-in removes the legacy token key from localStorage and Office roaming settings before showing its login state; it fails closed if that cleanup cannot be confirmed.
- The short-lived opaque Word session is held in memory. Logout clears local access immediately and requests server revocation. The server stores only the session-token hash.
- Session expiry is enforced by the server and reflected in the taskpane.
- Analysis is an explicit action on the current Word selection. It sends only that selection, limited to 4,000 Unicode code points; empty or oversized selections are rejected. The taskpane does not analyze on typing or upload the whole document.
- The taskpane loads only matter labels returned by the canonical owner/active-delegate ACL. Choosing no matter keeps retrieval on public law and case-law sources and does not search the caller's private document namespace.
- If the user selects a matter, the API rechecks that matter against the canonical ACL. The retrieval layer rechecks the authenticated request context and filters the private document namespace to exactly the selected matter, even when the user can access other matters.
- Changing the matter clears displayed results, aborts the pane request where supported, and invalidates any late response. Matter IDs are held only in pane memory and never grant access by themselves.
- Law citations are matched against structured Vindex law/article metadata; case citations are matched against retrieved decision numbers and, when the citation names a court, the structured court. A match confirms only that the cited identity corresponds to a retrieved record. The taskpane shows the recorded title, identifier, excerpt, locator, and source URL only when that URL exists as a credential-free HTTPS value in source metadata.
- Vindex does not provide dependable law-version/currentness metadata through this retrieval path. Version status therefore stays unknown unless the retrieved record explicitly says it is deprecated or has an expired `valid_until`; case decision dates are shown as decision dates, not law effective dates.
- Even when the source identity matches, legal relevance, claim support, source completeness, and legal correctness remain unverified. Mismatched citations remain visibly unverified, and an explicit retrieval failure is shown as unavailable. Source text and citations are rendered with `textContent`; they are not treated as HTML or instructions.
- A lawyer may explicitly request a selected-text formulation proposal. The backend returns a review-only proposal using the shared Vindex drafting client; it does not write to Word, a Vindex matter, or an approved draft. The taskpane shows the original and proposal separately and requires a second, explicit **Primeni predlog** action.
- Apply re-reads the current selection through Office.js and requires the same text, story, and Word character offsets captured before generation. It rejects changed or moved selections, concurrent duplicate applies, non-main-body stories, tables, content controls, fields, footnotes/endnotes, tracked revisions, numbering, multiline selections, mixed formatting, and hosts without the required `WordApi 1.5` plus `WordApiDesktop 1.4` APIs. It uses Word's native `Range.insertText(..., Replace)` operation so the host's normal Undo command remains available.
- The rewrite feature is intentionally fail-closed on unsupported structure/formatting. Node contract tests exercise these rejections and ensure a successful mock apply touches only the requested range. Actual Word mutation, formatting preservation, and Undo behavior remain NOT_RUN until a real host session is available.

The focused local auth and analysis suite is:

    python -B -m pytest -p no:cacheprovider -q tests/test_word_addin_taskpane.py tests/test_word_addin_auth.py tests/test_word_addin_security_headers.py tests/test_word_addin_analysis.py tests/test_confidentiality_003_rag_acl.py tests/test_beta_del_001_deletion_integrity.py tests/test_ns008_t19_acl_matrix.py tests/test_ns008_t21_revocation.py tests/test_br003_retrieval_namespace.py tests/test_vcr001_t04_kontekst_predmeta.py

This suite uses deterministic local mocks. It is not real Word, Supabase, or production validation.

## Controlled release-candidate manifest

`integrations/word_addin/manifest.release.xml` is a separate, controlled distribution candidate. It has its own GUID, no localhost or development URLs, and same-origin `https://vindex.rs/word_addin/` taskpane, command, and icon resources. The API mounts the matching local asset directory at `/word_addin`. The old `/podrska` link did not correspond to an application route in this checkout; the candidate uses the existing `/app` route as its support entry point. These checks prove repository routing and local asset existence only. The live host, TLS, and deployed asset reachability have not been tested.

The candidate uses the `Document` host and `DesktopFormFactor`. Microsoft's manifest documentation describes `DesktopFormFactor` as applying to Office on the web, Windows, and Mac, but this describes the manifest surface and is not proof of Vindex host compatibility ([manifest reference](https://learn.microsoft.com/en-us/javascript/api/manifest/desktopformfactor?view=word-js-preview)). The Word rewrite action checks `WordApi 1.5` and `WordApiDesktop 1.4`. Microsoft describes `WordApiDesktop` as desktop-only for Windows and Mac; therefore this implementation deliberately disables rewrite on Word for the web ([WordApiDesktop 1.4](https://learn.microsoft.com/en-us/javascript/api/requirement-sets/word/word-api-desktop-1-4-requirement-set?view=word-js-preview)).

| Host | Observed host version | Auth requirement checks | Rewrite requirement checks | Vindex host validation |
|---|---|---|---|---|
| Word for Windows | 16.0.20326.20232 is installed; add-in was not run | `DialogApi 1.2`, `DialogOrigin 1.1` | `WordApi 1.5`, `WordApiDesktop 1.4` | `NOT_RUN` |
| Word for Mac | Not available for inspection | `DialogApi 1.2`, `DialogOrigin 1.1` | `WordApi 1.5`, `WordApiDesktop 1.4` | `NOT_RUN` |
| Word on the web | Host version not captured | `DialogApi 1.2`, `DialogOrigin 1.1` | Disabled by the desktop-only `WordApiDesktop 1.4` requirement | `NOT_RUN` |

The taskpane and selected-text analysis have not been exercised on any real Word host. Word selection code currently has no manifest requirement declaration; runtime support is unverified. Authentication support and dialog-origin behavior are also `NOT_RUN` on all hosts. Do not advertise host support based on mocked Office.js tests.

### Controlled installation procedure

The release candidate is pinned to the canonical `https://vindex.rs` origin. No staging origin is configured or verified, so this manifest must not be installed for testing while it could reach production. Before any host test, the founder/operator must provide and approve a non-production origin, prepare a separate environment-specific manifest for it, verify the deployed static assets and API, resolve the reviewed Word session migration, configure only verified frame ancestors, and verify PR #66's centralized AI budget contract. Do not alter live authentication configuration or deploy as part of this task.

Once those gates are satisfied, use an isolated Office test tenant and synthetic legal documents. On Windows, sideload the approved staging manifest through Word → **Insert** → **Add-ins** → **My Add-ins** → **Upload My Add-in**. For Mac and web, use the organization's controlled test-tenant deployment process; no installation flow has been verified here. Capture the host version and verify login, selected-text submission, source display, approved rewrite, surrounding text, Undo, and logout. Remove the test deployment after evidence is collected.

This is not an AppSource package or public rollout. Neither manifest has been installed, and `https://vindex.rs` was not reached over the network. The repository tests check XML well-formedness, distinct IDs, same-origin HTTPS URLs, local file mapping, and resource references; they are not Microsoft's online manifest validator.
