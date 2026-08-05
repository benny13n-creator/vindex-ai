# Review Queue Specification — Program Intake Sprint 003 (2026-08-05)

Phase 5 requirement: if confidence is insufficient, never classify — always route to Review Required.
Mission principle: every document ends in exactly one of two states — Canonically Classified, or Review
Required. A third state (silently guessed) must not exist. Full evidence: `.vindex_ai_team/decisions/
2026-08-05_intake_sprint003_fork_review_queue_edge_cases.md` (Fork C).

## 1. Current state per classifier (before this sprint's fix)

| Classifier | Confidence field? | Escape hatch? | On uncertainty, did |
|---|---|---|---|
| `shared/intake_classify.py` (Pipeline B) | Yes, real (heuristic 0.85 fixed / LLM self-reported) | Yes — `AUTO_ACCEPT_THRESHOLD=0.90` → `intake_review_queue` | Correctly routed to review |
| `routers/evidence.py::_klasifikuj_dokument` (Pipeline A's only classifier; Pipeline C's stage-2 overwrite) | No | No | Silently returned `"ostalo"` on error; **on Pipeline C, unconditionally overwrote Pipeline B's confidence-gated value regardless of confidence or review status** |
| `api.py::_detect_doc_type` (ephemeral) | No — no numeric confidence anywhere in this function | No | Always returned one of 3 fixed buckets; wrong guess silently picked the wrong AI analysis template |
| `routers/dokument.py::_klasifikuj_dokaz` (ephemeral) | `snaga_dokaza` exists but describes evidentiary STRENGTH, not classification confidence — a conflated, not a missing, field | No | Silently returned `"ostalo"`/`"niska"` on error |

**Only 1 of 4 real classifiers had a working escape hatch.** Worse: that one working escape hatch's signal
never survived past a single narrow endpoint (§2), and was actively defeated by a second classifier on the
one pipeline that carries documents through to the permanent case record (§3 — this sprint's headline fix).

## 2. Where the review-queue signal was visible (before this sprint)

Repo-wide grep for `intake_review_queue` (excluding docs/migrations/tests) hit exactly one production read
site: `GET /api/smart-intake/jobs/{job_id}` (`routers/smart_intake.py::intake_job_status`). No case-file view,
no `predmet_dokumenti` list/detail endpoint, and no frontend code outside Smart Intake's own job-status
screen ever queried this table. A document flagged for review and never revisited on that specific screen had
its review flag effectively invisible for the rest of its life in the system.

## 3. The sprint's headline finding, and the fix

**Finding**: Pipeline C's finalize (`routers/smart_intake.py::finalize_intake_job`) fetched the review data
(`result["review"]`) but never inspected it (`document`/`entities` were unpacked; `review` was discarded).
Worse: after writing Pipeline B's `document_type` into `predmet_dokumenti.tip_dokaza`, an **unconditional**
background task (`_evidence_classify_bg`, added "Operation Lawyer Zero LZ-002" for a legitimate different
purpose — vocabulary correction so `EXPECTED_DOCS` matching works) immediately overwrote that same column via
`routers/evidence.py::klasifikuj_i_sacuvaj` — a classifier with **no confidence field at all** — regardless
of whether the original classification was low-confidence or its review-queue entry was ever resolved. The
one place in the whole system that correctly said "I'm not sure" had that signal structurally erased before
a lawyer could ever act on it.

**Fix implemented this sprint** (`routers/smart_intake.py`, tested — `tests/
test_sprint003_classification_review_required.py`):
1. `result["review"]` is now inspected. `classification_uncertain = "document_type" in
   (review.get("low_confidence_fields") or [])`.
2. When `classification_uncertain` is true, the confidence-blind `_evidence_classify_bg` overwrite is **not
   scheduled** — Pipeline B's own (uncertain) classification is left in place rather than silently replaced
   by an equally unfounded but more-confident-looking second guess.
3. When `classification_uncertain` is false (the common case), the overwrite still runs exactly as before —
   LZ-002's legitimate vocabulary-correction purpose is preserved for every confidently-classified document.
4. The finalize HTTP response now **always** includes `klasifikacija_nesigurna` (bool) and `nesigurna_polja`
   (list) — making Review Required a visible state at the one moment a lawyer is actually looking at this
   document, instead of buried in an endpoint nobody revisits.
5. `GET /jobs/{job_id}` (`intake_job_status`) now flags `tip_moze_biti_zastareo: true` with an explanatory
   `napomena` once a job has been finalized (`predmet_id` is set) — since (per `INTAKE-003`, unchanged) there
   is no reliable join back to the specific `predmet_dokumenti` row to show the current canonical value
   directly, this endpoint now honestly discloses staleness and points the caller at the case file, rather
   than silently presenting a possibly-superseded value as current truth (Fork A's confirmed defect: this
   exact value, with its own hardcoded frontend translation map, was shown to the lawyer during Smart Intake's
   review step, permanently disagreeing with the Serbian value later shown in Evidence Vault).

## 4. What is honestly NOT fixed by this narrow pass

- **Pipeline A and the 2 ephemeral classifiers still have zero escape hatch.** This sprint's fix only
  protects Pipeline C's finalize flow, the one place Pipeline B's real confidence signal was being destroyed.
  Giving Pipeline A's classifier (`evidence.py`, its only classifier) a genuine confidence-gated review path
  is a larger change — it would need the full Confidence Specification (`CONFIDENCE_SPECIFICATION.md`)
  actually implemented, not just consumed. Tracked as `INTAKE-008`.
- **The uncertainty signal is not durably persisted on `predmet_dokumenti` itself.** The fix surfaces
  `klasifikacija_nesigurna` in the finalize HTTP response (the one moment a lawyer is definitely looking) but
  does not add a new column to make this state queryable later from the case file — that would require a
  migration, and `predmet_dokumenti.status`/`tip_dokaza` were both checked and rejected as reuse candidates
  (overloading either would recreate the exact "one field, two meanings" collision this sprint's taxonomy
  work (§3.2 of `CANONICAL_DOCUMENT_TAXONOMY.md`) was careful to avoid elsewhere). Tracked as `INTAKE-008`.
- **The other 3 non-Pipeline-B classifiers' silent-default-to-`"ostalo"` behavior is unchanged** — a real
  instance of the forbidden third state, but rewiring them to escape-hatch correctly requires the full
  taxonomy adoption (`CANONICAL_DOCUMENT_TAXONOMY.md` §6), not a bounded patch.

## 5. Success-criteria self-check

- Every document has confidence → **Not yet true platform-wide** — only Pipeline B's classifier computes one.
- Every document has a classification reason → **Not yet true platform-wide** — same gap.
- No document auto-misclassified when confidence is low → **True for the one path that had confidence data
  and was being defeated (Pipeline C finalize's overwrite) — fixed this sprint.** Not true for paths that
  never had confidence data to begin with (deferred, `INTAKE-008`).
- Review queue works as the sole alternative → **True where it existed and was reachable (Pipeline B) — now
  also true where its signal was previously being erased downstream (Pipeline C finalize) — fixed this
  sprint.** Not true where no review queue exists at all (Pipeline A, the 2 ephemeral classifiers).

This sprint closes honestly as: **the one place a real confidence signal existed and was being silently
destroyed is fixed and regression-tested; extending confidence-gated review to the classifiers that never had
it at all is correctly out of this sprint's bounded scope and tracked for a future pass.**
