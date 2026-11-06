# UX Specification - Word Add-in Task 01: Secure Authentication

**Author (role):** UX/UI Experience Architect
**Date:** 2026-11-01
**Product Specification:** 2026-11-01_word-addin-task01-auth_PRODUCT_SPECIFICATION.md
**Status:** Revised draft

## User Journey

Open the pane; see that sign-in uses the existing Vindex account; choose Sign in; authenticate in a same-origin Office dialog; return to the pane and see account and expiry; sign out to disable actions immediately, clear results, and close this pane's session; receive confirmation or an unconfirmed-revocation message.

## Components

Signed-out state with Sign in and no token/password field in the pane; same-origin login dialog; signed-in account/expiry and Sign out; plain-language failures without provider/database jargon or credential fragments.

## Information Hierarchy

Authentication first, then authorized actions. Later tasks must tell lawyers what document text will be sent before any explicit operation. Logout clears the pane and prevents stale results. Explain that an already-dispatched provider attempt cannot be recalled; never claim remote processing stopped if it may still be finishing.

## Visual Identity and Accessibility

Preserve graphite, cyan/blue, existing typography, and sharp Vx-style controls. Use visible labels, keyboard operation, focus visibility, accessible live status, and plain-language failures. No dashboard.

## Persona Cross-Check

Reviewed current lawyer/partner simulation reports in architecture documentation. They emphasize the existing Word-centered workflow and reveal no conflicting sign-in/session expectation. This does not establish pilot usability.

## Deployment Note

No service-worker bump is planned because `/word_addin` is outside `/static`; verify registration and cache behavior before release.
