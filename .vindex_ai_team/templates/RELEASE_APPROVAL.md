# Release Approval — [Feature Name]

**Author (role):** Release Governance
**Date:**

## Gate Checklist

- [ ] Product approved — `decisions/PRODUCT_SPECIFICATION.md`: [link]
- [ ] Architecture approved (if applicable) — `decisions/ARCHITECTURE_DECISION.md`: [link] / N/A, reason: ______
- [ ] Security approved — `decisions/SECURITY_REVIEW.md`: [link], no open CRITICAL/HIGH, or founder
      acceptance recorded at: [link]
- [ ] Red Team did not block — `decisions/RED_TEAM_REPORT.md`: [link], verdict: ______
- [ ] AI Design reviewed (if applicable) — `decisions/AI_DESIGN_REVIEW.md`: [link] / N/A
- [ ] Database reviewed (if applicable) — `decisions/DATABASE_REVIEW.md`: [link] / N/A, migration
      staged for founder execution, NOT auto-run
- [ ] Tests passing — `decisions/QA_REPORT.md`: [link], verdict: PASS
- [ ] Documentation updated — specifically checked against `docs/security/PUBLIC_SECURITY_CLAIMS.md`
      and `SECURITY.md` for any claim this change affects
- [ ] Rollback path stated and understood
- [ ] Frontend cache-version bump confirmed (if frontend change)

## Overrides
Any gate above marked "N/A" or bypassed by explicit founder override — stated here, with the
founder's written reasoning, not a verbal aside.

## Verdict
**APPROVED FOR RELEASE** / **BLOCKED** — pending: [specific unmet gate].
