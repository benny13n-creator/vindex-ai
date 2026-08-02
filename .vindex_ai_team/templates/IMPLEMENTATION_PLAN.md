# Implementation Plan — [Feature Name]

**Author (role):** Backend Engineering (and/or Frontend Engineering)
**Date:**
**Technical Design:** [link] **Security Review:** [link, if applicable] **Database Review:** [link, if applicable]

## Files to Change
Named specifically, with the pattern being followed cited (e.g., "ownership check per
`api.py:3220`'s existing pattern," "sanitization per `klijenti/router.py:149-154`'s existing
`field_validator` pattern").

## New `AUDITABLE_ACTIONS` Entries
If this feature performs a security-relevant action, the new action string(s) to add to
`shared/audit_immutable.py`'s hardcoded set — stated explicitly here so it isn't forgotten (this
exact omission has caused a silent, undetected bug three times in this project's history).

## Deviations From Approved Design
Any place this implementation differs from `TECHNICAL_DESIGN.md`, and why — flagged explicitly,
not silently absorbed into the diff.

## Test Plan
What QA Engineering will need to verify — cross-referenced against `PRODUCT_SPECIFICATION.md`'s
acceptance criteria, not just "the code runs."

## Rollback
How to revert this specific change if it ships broken.
