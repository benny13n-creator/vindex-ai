# Ownership Resolution Specification — Program Intake Sprint 006 (2026-08-05)

Defines every signal `shared/case_assimilation.py` uses to decide which case (`predmet`) and which client
(`klijent`) a document belongs to, and the combination rule that decides auto-assign vs. review-required vs.
create-new. Mirrors Sprint 005's `CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md` in shape and discipline —
the same conservatism mandate, applied to a new domain.

## 1. Case ownership signals

| Signal | Outcome when it fires alone |
|---|---|
| Explicit `predmet_id` supplied by the caller | **ATTACH** — a human choice is never second-guessed |
| Extracted case number exact-matches exactly ONE existing `predmeti.broj_predmeta` | **ATTACH** |
| Extracted case number exact-matches 2+ existing cases | **REVIEW REQUIRED** — never picks one; caller must retry with an explicit `predmet_id` |
| No case number extracted, or matches zero existing cases | **CREATE NEW** — the mission's own documented product promise ("upload a lawsuit, Vindex creates a case") stays intact; there is nothing ambiguous about creating a fresh case when nothing existing claims to already be it |
| 2+ documents in the SAME upload carry DIFFERENT extracted case numbers | **BLOCK THE WHOLE FINALIZE CALL** — real evidence of a mis-bundled multi-case upload; never silently assimilated under whichever document was read first |

`resolve_case_ownership()`'s implementation is deliberately a single exact-match query
(`predmeti.broj_predmeta = <normalized case number>`, scoped by `user_id`) — no fuzzy matching, no scoring.
Case numbers are the single most authoritative document-identity marker in Serbian court practice; a fuzzy
match here would reintroduce exactly the guessing risk the mission forbids.

## 2. Client ownership signals

| Signal | Outcome |
|---|---|
| Full name (ime + " " + prezime, or `firma` for a detected company) exact-matches exactly ONE existing `klijenti` row | **MATCH** |
| Full name matches 2+ existing clients (identical name, or same surname with a shared first name in the cheap prefilter) | **AMBIGUOUS** — never auto-linked; surfaced in the finalize response (`klijent_nesiguran`, `klijent_kandidati`) instead |
| No match | **CREATE NEW** — correctly typed (`fizicko_lice`/`pravno_lice`) and correctly split (`ime`/`prezime`, or `firma`) |

**The bug this replaces**: the pre-Sprint-006 query compared the full extracted name against `klijenti.ime`
(first-name-only), with `.limit(1)` and no disambiguation — a query that could essentially never match a
real two-word name correctly, and which silently picked an arbitrary row on the rare occasion it did
over-match. `resolve_client_ownership()` fetches candidates via a cheap first-name `ILIKE` prefilter, then
confirms the FULL name match in Python (comparing `ime + " " + prezime` against the extracted name) —
correctly excluding same-first-name-different-surname false matches, and correctly detecting genuine
same-full-name ambiguity (the mission's own named "two clients, same surname" edge case).

**Company detection**: a party name containing a whole-token Serbian/regional company-form suffix (`doo`,
`ad`, `dd`, `preduzeće`, etc. — internal dots stripped before comparison, so "d.o.o." and "DOO" both
normalize identically) is matched against `klijenti.firma` instead of being incorrectly split into
`ime`/`prezime`. A real bug was found and fixed during this sprint's own test-writing: an earlier
implementation replaced dots with spaces before tokenizing, which shattered "d.o.o." into meaningless
single-letter tokens ("d", "o", "o") that never matched anything — fixed to strip dots per-token instead of
using them as a word separator.

## 3. Multiple punomoćja / multiple attachments

A segment carrying no independent case-number/party-name signal of its own (the typical shape of an annexed
punomoćje) is registered under the SAME `predmet_id` the job's other documents already resolved — it does not
independently trigger a new-case or ambiguous-client outcome purely for lacking its own signal, mirroring
Sprint 005's own segmentation-layer precedent (`test_punomocje_attached_annex_does_not_auto_split_alone`) at
the ownership layer. If sibling documents in the same upload have CONFLICTING case-number signals, the
whole-upload block (§1, last row) fires instead — inheritance never applies across a genuine conflict.

## 4. Same document uploaded twice

Two distinct scenarios:
1. **Whole-file re-upload** — already handled by the existing `idempotency_key` at enqueue time (Sprint 002),
   out of this sprint's own scope.
2. **The same predmet_dokumenti insert being attempted twice for the same segment** — prevented at the
   database level by migration 094's `UNIQUE (source_intake_job_segment_id) WHERE ... IS NOT NULL` constraint
   (see `EVIDENCE_INTEGRITY_REPORT.md`). A segment-content-hash-based dedup across TWO DIFFERENT overall
   uploads (e.g. the same punomoćje re-scanned into two different bundles) is explicitly out of this sprint's
   bounded scope — recorded in the Architectural Debt Register, since no per-segment hash column exists yet
   to build it on.

## 5. Deliberately not built this sprint

- **Fuzzy/partial case-number matching** — exact match only, by design (see §1).
- **Automatic client merging** when an ambiguous match is later resolved by a human — the `klijent_kandidati`
  list is surfaced, but no UI/endpoint to pick one was built this sprint (backend-only bounded scope).
