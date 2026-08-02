# Security Review — [Feature/Change Name]

**Author (role):** Security & Privacy Architect
**Date:**
**Existing Gap Register check:** does this relate to an existing SEC-XXX finding? [link, or "none found"]

## Security Impact Assessment

| Dimension | Applicable? | Assessment |
|---|---|---|
| Authentication | | |
| Authorization / tenant isolation | | |
| Encryption (at rest / in transit / field-level) | | |
| Audit coverage (new `AUDITABLE_ACTIONS` entry needed?) | | |
| AI provider data exposure (which provider, what payload, exactly) | | |
| GDPR/ZZPL (new PII category, deletion, retention, export impact) | | |
| Data residency | | |
| Secrets handling | | |
| Rate limiting / abuse surface | | |

## Blueprint Capability Traceability
Which of the 10 capabilities in `docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md` §1.9
does this feature relate to? A security-relevant feature with no traceable capability is itself a
finding, per the Blueprint's own governing rule.

## Findings
Severity CRITICAL/HIGH/MEDIUM/LOW, each with evidence, concrete abuse scenario, business impact,
remediation, complexity — same fields the Gap Register uses. Any CRITICAL/HIGH gets a new SEC-ID
and is added to `docs/security/SECURITY_GAP_REGISTER.md` directly.

## Public Claims Impact
Does this feature change what can be claimed in `docs/security/PUBLIC_SECURITY_CLAIMS.md` (moves
something from List B to List A, or introduces a new List B risk)? State explicitly.

## Verdict
APPROVED / APPROVED WITH CONDITIONS / BLOCKED — pending [specific finding IDs].
