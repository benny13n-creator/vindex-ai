# Canonical Segmentation Signal Specification — Program Intake Sprint 005 (2026-08-05)

Defines every signal `shared/intake_segment.py::segment_document()` uses to detect a document boundary, why
each was chosen (never an arbitrary rule — every signal maps to a legal-domain reason a lawyer would
recognize), its false-positive risk, and the combination rule that decides auto-split vs. route-to-review vs.
keep-as-one.

## 1. Signal vocabulary

| Signal (`kind`) | Strength | What it detects | Legal-domain rationale |
|---|---|---|---|
| `heading_keyword` | strong | A new act-type title (ТУЖБА, ПРЕСУДА, РЕШЕЊЕ, ЖАЛБА, ПУНОМОЋЈЕ, ПРИГОВОР, ОДГОВОР НА ТУЖБУ, ЗАХТЕВ, ПРЕДЛОГ — Cyrillic and Latin) appears isolated near the top of a page, differing from the previous page's heading. | Every one of these words names a distinct kind of legal act; a lawyer opening a bundled PDF identifies a new document by its title first. |
| `case_number_change` | strong | A Serbian court case number (`П. бр. 1234/24`, `Гж 567/23`, etc.) found isolated near the top of a page, differing from the previous page's case number. | A case number is the single most authoritative document-identity marker in Serbian court practice — different number means a different proceeding/filing. |
| `page_counter_reset` | corroborating | A "Strana X od Y" / "Page X of Y" footer's own page-1 counter resets or goes backward relative to the previous page. | Each individually-produced/printed document restarts its own internal pagination; a reset is strong circumstantial evidence of a new physical document starting, but common enough on its own (a scan artifact, a re-numbered attachment) to only corroborate, not confirm alone. |
| `blank_separator` | corroborating | A near-blank physical page (fax cover sheet, staple divider) immediately precedes non-blank content. | Common practice when physically stapling separate originals together; corroborating only, since a blank page can also just be a printing artifact inside one document. |

**Isolation discipline (why these don't false-positive on ordinary prose)**: `heading_keyword` and
`case_number_change` only fire on one of the first 5 non-empty lines of a page's head (`_PAGE_HEAD_CHARS=400`),
and only on a short, standalone line — not a keyword or number cited inline within running prose. This is what
correctly keeps a rešenje's own "Pouka o pravnom leku: ... dozvoljena je žalba ..." footer (which legitimately
contains the word "žalba" in a full sentence) from being misread as a new žalba document starting, and keeps
an appellate court's own "Odlučujući po žalbi ... zavedenoj pod Gž 45/24 ..." from being misread as citing its
own new identity rather than quoting the lower court's.

**Word-boundary matching, not substring containment** (a real bug found and fixed during this sprint's own
integration testing, see `tests/test_intake_segment.py::test_inflected_form_of_heading_keyword_does_not_falsely_trigger_split`):
Serbian is heavily inflected, so an ordinary continuation sentence like *"...u prilog zahtevu."* contains
"zahtevu" (dative case of "zahtev"), which a naive substring check (`kw in line`) would misread as the heading
keyword "ZAHTEV" itself appearing. `_find_heading_keyword` matches on a regex word boundary (`\bKW\b`), not
plain containment, specifically to prevent this class of false positive.

## 2. Combination rule (the conservatism mandate, made concrete)

The mission's own explicit, highest-priority rule: never split incorrectly when there isn't enough evidence. A
wrongly-split filing is worse than one correctly-unsplit bundle. This table is the literal implementation of
that asymmetry:

| Evidence at a page boundary | Outcome |
|---|---|
| 2+ strong signals agree | **AUTO-SPLIT** |
| 1 strong + 1+ corroborating | **AUTO-SPLIT** |
| Exactly 1 strong, alone | **ROUTE TO REVIEW** (`segmentation_uncertain`) |
| 2+ corroborating, no strong | **ROUTE TO REVIEW** (`segmentation_uncertain`) |
| 1 lone corroborating | **KEEP AS ONE** (too thin to even escalate) |
| Nothing fires | **KEEP AS ONE** |

Implemented as two small, deliberately separate pure functions over the same detected signals:
`segment_document()` returns only CONFIRMED cuts (the two AUTO-SPLIT rows); `uncertain_boundaries()` returns
only the two ROUTE-TO-REVIEW rows. The pure boundary decision ("what IS a separate document") and the
escalation decision ("what MIGHT be, needing a human") are kept as two questions, not folded into one function
that tries to answer both.

**Caller behavior** (`shared/intake_worker.py`): when a boundary is confirmed, the document splits and each
resulting segment enters classification independently. When a boundary is merely uncertain, the document
stays whole AND a `intake_review_queue` entry with reason `segmentation_uncertain` is created — the engine
never silently does nothing on real-but-thin evidence; a human is always asked to confirm the conservative
default was right.

## 3. Reason vocabulary (fixed, not free text)

Mirrors `intake_review_queue.reason`'s own exactly-N-value discipline (Sprint 004). `Segment.reason` is one of:
- `single_document` — no signals fired (the ordinary case).
- `heading_keyword` / `case_number_change` / `page_counter_reset` / `blank_separator` — exactly one signal kind
  justified the cut.
- `combined_signals` — 2+ different signal kinds justified the cut together.

## 4. Confidence (deterministic, not learned)

`Segment.confidence` is derived directly from which rung of the combination table confirmed the cut — the
only two combinations that can ever reach a confirmed segment:
- 2+ strong signals → `0.95`
- 1 strong + 1+ corroborating → `0.85`
- No signals (the single-document/degenerate case) → `1.0` (full confidence nothing needed splitting)

## 5. Mandatory edge cases validated against this specification

Full results: `SEGMENTATION_EDGE_CASE_VALIDATION_REPORT.md`. Every named false-positive scenario from the
mission's own Phase 7 list has a dedicated passing test in `tests/test_intake_segment.py`.
