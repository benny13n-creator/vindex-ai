# Known Risks — Institutional Record

Standing, accepted, or not-yet-resolved risks this organization should already know about before
proposing a feature that would interact with them. Cross-referenced to
`docs/security/SECURITY_GAP_REGISTER.md`'s SEC-IDs where applicable — this file states *why a risk
matters for future design decisions*, the register states the evidence.

## SEC-004 — RLS is not the enforcement mechanism for any application traffic
**Standing architectural fact**, not a bug awaiting a quick fix. The single Supabase client used
everywhere is built with the service-role key; all 148 tables' RLS policies are inert for API
traffic. **Design implication:** any new feature's tenant isolation depends entirely on correct,
explicit `.eq("user_id", ...)`-style filtering in application code — there is no database backstop.
This is exactly the root cause of SEC-001, SEC-039, SEC-040, and SEC-059, found independently at
different times. **Do not design a new feature assuming RLS provides isolation** — it does not, for
any code path this backend's service-role client touches.

## SEC-054 — No cross-matter (ethical wall) isolation in AI retrieval within a firm
A firm member's AI query can retrieve document chunks from any matter in the firm's shared Pinecone
namespace, filtered only by document type, not by matter. **Design implication:** any new feature
that expands AI retrieval scope (a new RAG-backed capability, a new cross-document analysis
feature) inherits this risk unless it explicitly adds matter-scoping. This is the single
disqualifying finding for medium+ firm and court/government deployment (forensic audit §15) — a
new feature should not make this worse, and ideally should be designed to make closing it easier,
not harder.

## SEC-038 — `profiles` table entitlement columns, pending resolution
Do not build any new feature that reads `profiles.is_pro`/`subscription_type`/`addons` as a trust
signal without first confirming this finding's live-test result and fix status (see
`current_state.md`).

## Pattern-level risk: narrow, inconsistent application of correct patterns
Not a single finding — the forensic audit's own cross-cutting diagnosis. This codebase has multiple
instances of "one implementation does X correctly, a structurally identical one doesn't repeat it"
(encryption coverage, sanitization coverage, `hmac.compare_digest` usage, SELECT-only+RPC table
locking). **Design implication for every future feature:** when implementing something that
resembles an existing pattern, explicitly verify the existing pattern is being followed exactly,
not approximately — approximate repetition is how this class of finding keeps recurring.

## `AUDITABLE_ACTIONS` silent no-op
`shared/audit_immutable.py::log_action()` silently no-ops (no exception, no log above debug level)
for any action string not in its hardcoded allow-list. **Design implication:** any new
security-relevant action needs its string added to that set explicitly — verified, not assumed —
before relying on it for audit coverage.

## Template for new entries
```
## [SEC-ID or name] — [one-line risk]
[Standing fact or current status.] **Design implication:** [what a future feature must account for].
```
