# Workflow Gaps

**Mission:** Operation Beta Lockdown, 2026-08-03. Every non-blocking friction point found across
tonight's operations, consolidated. None of these prevent a lawyer from completing a workflow — see
`docs/product/LAWYER_DAY_REPORT.md` for the full-day simulation that established this — but each is a
real, evidenced gap worth tracking. Classified P2 (workflow annoyance) or P3 (technical debt) per this
mission's own severity scale; P0/P1 items are covered in `BLOCKER_REPORT.md` instead.

| # | Gap | Severity | Evidence | Why not fixed tonight |
|---|---|---|---|---|
| 1 | No true batch upload on the reachable per-case upload path — 20 documents require 20 separate actions | P2 | `api.py:4138` accepts one `UploadFile`, not a list | Resolved for free once Smart Intake ships (`BLOCKER-2`); not worth a parallel narrower fix |
| 2 | No duplicate-file detection on the reachable upload path | P2 | Smart Intake has exact-hash dedup (`smart_intake.py:126`); `api.py:4133` has none | Same as above, plus genuinely small on its own — candidate for a future dedicated fix |
| 3 | No single "hearing-prep export package" | P2 | Confirmed absent in `routers/export.py`, `data_export.py`, `rocista.py`; every underlying piece (judge/opponent research, Genome, deadlines, drafts) already works | Pure aggregation UI, not urgent enough to build blind on the product's behalf |
| 4 | No account-wide audit/activity log viewer | P2/P3 | Confirmed absent in `vindex.js`; note: case-scoped audit visibility DOES exist via the Intelligence Timeline — narrower gap than first assumed | Small-medium new UI, no workflow currently blocked by its absence |
| 5 | Case archiving only reachable from the case LIST view, not case-detail | P2/P3 | `pred_bulkAkcija('arhiviranje')` wired only to the list's bulk-select bar | Trivial fix, but genuinely P2 per this mission's own severity definition — not implemented per the "only P0/P1" rule |
| 6 | Team comments (`predmet_komentari`) excluded from global search | P3 | No branch in `routers/search.py` for this table; confirmed NOT a duplicate of private notes (`beleske`) — distinct, intentional purposes per the UI's own copy | Small, but P3 |
| 7 | ~80% of the defined audit-action taxonomy never fires in production | P2/P3 | `shared/audit_immutable.py::AUDITABLE_ACTIONS` defines 24 types; only ~5-8 are ever actually triggered (see `BETA_LOCKDOWN_REPORT.md` for the full list) | Would require auditing many separate call sites across the codebase — a program of work, not a single fix |
| 8 | `predmet_create` not logged for the real-world case-creation path (`intake_kreiraj`) | P2 | Only `POST /api/predmeti` logs `predmet_create`; the CRM Intake Wizard's actual endpoint doesn't | Small in isolation, but part of the broader audit-coverage gap (#7) — worth fixing together, not piecemeal |
| 9 | AI Workspace mode/sub-panel selection is in-memory only — lost on page reload | P3 | `aiwsSetMode()` (`vindex.js:2323-2371`) sets a JS variable only, no `localStorage`/URL persistence | Cosmetic navigation-state loss, not a data-loss risk (draft text itself is DB-backed) |
| 10 | Case Genome content and Evidence Vault's richer fields not searchable | P3 | `routers/search.py`'s type list has no branch for `case_dna` or `predmet_dokazi` | Minor; the coarser `tip_dokaza` field IS searchable, covering the common case |
| 11 | Defense-in-depth soft spot: `_do_genome_refresh`'s background task doesn't hard-return on an ownership-check miss | P3 | `routers/case_dna.py` ~line 653 — not currently exploitable via any real call site (every caller already validates ownership before triggering it) | Hardening, not a live vulnerability — lower priority than BL-001 |

## Not a gap (confirmed correct, recorded to prevent re-discovery)

- Backup/data-safety status has no lawyer-facing UI — correctly N/A, an infra concern with no natural
  surface, not every workflow bullet needs one.
- `predmet_beleske` vs. `predmet_komentari` are NOT a duplicate needing unification — confirmed
  intentionally distinct (private notes vs. team comments) via the UI's own labeling.
- The Web3/Digital Asset Compliance Suite's gating behind a Settings flag is a deliberate, prior
  product decision, not an incompleteness.
