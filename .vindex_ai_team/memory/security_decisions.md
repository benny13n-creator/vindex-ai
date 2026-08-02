# Security Decisions — Institutional Record

**This file does not duplicate `docs/security/SECURITY_GAP_REGISTER.md`.** That file is the single
source of truth for all security findings (SEC-001 through SEC-073 as of 2026-08-02). This file
records *decisions about process and policy*, not individual findings.

## Decision: evidence-only, adversarial-review methodology is standing practice, not a one-time audit response
Established 2026-07-23, restated and applied consistently through the 2026-08-02 forensic audit:
every significant security claim must be backed by `file:line` evidence, not documentation; every
significant fix goes through independent (fresh-agent, non-fork) peer review before being trusted;
"tests pass" (Stage 7) and "confirmed correct in production" (Stage 8) are different claims, never
conflated. **Reference:** `docs/security/FINDING_LIFECYCLE.md`.

## Decision: `docs/security/PUBLIC_SECURITY_CLAIMS.md` is the sole source of truth for external claims
Any claim about Vindex AI's security posture made in customer-facing material (`SECURITY.md`,
`privacy.html`, `static/dpa.html`, sales material) must be checked against this document's List
A/List B split before publication. The 2026-08-02 forensic audit found `SECURITY.md` specifically
had drifted from this standard (SEC-063) while the internal `docs/security/` corpus had not — the
internal discipline is sound; the external-facing document needs periodic reconciliation against it.

## Decision: the Blueprint's Escalation-Only Invariant and Untrusted Provider Principle are project-wide, not Program-1-scoped
Both were elevated from Program 1-specific design choices to Blueprint-level principles (added
under Principle 1 and Goal 4/Principle 7 respectively) on 2026-08-02, specifically because the
founder judged them to be security rules of general application, not implementation details of one
feature. Any future feature combining a declarative policy floor with a risk/quality signal must
follow the same rule: the signal may only escalate the floor, never lower it.

## Decision: two live-severity findings from the forensic audit are standing action items until resolved
- SEC-037 (exposed OpenAI key in git history) — rotation is independent of any development
  timeline; this file does not consider it "handled" until the founder confirms rotation.
- SEC-038 (`profiles` table privilege-escalation exposure) — same standing until the founder
  confirms the live test result and the fix ships.
**Any new feature touching the `profiles` table's entitlement columns must check SEC-038's status
first** — do not build on top of an unresolved privilege-escalation surface.

## Decision: recurring bug class — "a control that looks live but silently isn't" — gets named, not just re-fixed each time
Occurred at least four times independently in this project's history (SEC-034's silently no-op'd
migrations, SEC-005's dead rate-limit middleware, the `/api/cron/daily` registration collision, and
the general `AUDITABLE_ACTIONS` unregistered-action silent-no-op risk named across multiple
findings). **Standing rule for this organization:** Backend Engineering must explicitly check, for
any new security-relevant action, whether the mechanism it relies on (an audit action string, a
cron registration, a middleware registration) actually fires — verified live or in a test, not
assumed from the code "looking correct."
