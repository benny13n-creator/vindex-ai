# Legal Evaluation Corpus (LEC)

Formerly "golden_dataset" — renamed by the founder (2026-07-15) with a
specific reason: "Golden Dataset" sounds like something static you collect
once. This is a *product*, with versions (see [CHANGELOG.md](CHANGELOG.md),
currently `v1` — see [VERSION](VERSION)): LEC v1 → v2 → v3, each adding
documents, edge cases, annotations, and refined `correction_reason`/
`error_source` patterns. Real documents, manually verified ground truth,
measured against the actual production classification/extraction code —
not unit tests with synthetic fixtures. Unit tests prove the code runs.
This proves the AI is *accurate*, and gives every future change a number
to move.

**This directory ships empty on purpose.** Nothing in here was fabricated
to look like real accuracy data — that would defeat the entire point.
Founder's own framing: "Nemam ground truth, dakle nemam benchmark. To je
naučno ispravno." Populating this is the founder's own task, not
something the assistant can do for him.

See also [`evaluation/hall_of_shame/`](../hall_of_shame/README.md) — the
companion corpus of documents that spectacularly *broke* the system,
kept separate from this one because "hard but handled correctly" (goes
here) and "actually broke something" (goes there) answer different
questions.

## Sourcing advice (founder, 2026-07-15) — breadth over volume

Don't ask one office for 300 documents. Ask 3-5 offices for ~20 judgments +
20 lawsuits + 10 powers of attorney each (~150 documents total). Different
courts, writing styles, stamps, and scan equipment produce a far more
representative corpus than one office's internal consistency — and it's
exactly that diversity (not raw count) that this benchmark needs to be
trustworthy.

## Three datasets, not one

A single averaged accuracy number hides where the system actually
struggles. Three deliberately different collections, same annotation
format:

| Dataset | Folder | What it contains | What it isolates |
|---|---|---|---|
| **A — Clean Digital** | `documents/a_clean_digital/` | PDFs generated directly from Word — no scan involved | Parser/classification/extraction quality, with OCR noise removed as a variable |
| **B — Typical Serbian Reality** | `documents/b_typical_serbian/` | Scans, stamps, slightly crooked pages, photocopies, ordinary resolution | The full pipeline (OCR + classify + extract) on what actually arrives most days |
| **C — Nightmare** | `documents/c_nightmare/` | Deliberately hard: cropped pages, rotated scans, smudges, handwritten additions, mixed Cyrillic+Latin in one document, two judgments in one PDF, unsigned documents, poor contrast, an angled phone photo | The floor — what will genuinely show up, not what we'd prefer to show up |

`dataset` in each annotation is **derived automatically from which
subfolder the file is in** — don't type it by hand, put the file in the
right folder and the benchmark infers it from the path. One less thing to
get wrong while collecting under time pressure.

## Annotation format

One entry per document in `annotations.json`:

```json
{
  "dokumenti": [
    {
      "document_id": "presuda_001",
      "filename": "b_typical_serbian/presuda_001.pdf",
      "difficulty": "medium",
      "annotator": "MJ",
      "reviewed_by": "AK",
      "agreement": true,
      "error_source": null,
      "beleska": "Rok za žalbu pomenut u fusnoti, ne u glavnom tekstu — lako se previdi.",
      "expected": {
        "document_type": "judgment",
        "entities": {
          "case_number": "П 341/26",
          "judge": "Marija Kovačević",
          "plaintiff": "Petrović d.o.o.",
          "defendant": "Jovanović Grupa d.o.o.",
          "court": "Osnovni sud u Beogradu",
          "deadline": "15.11.2026",
          "amount": "48.200,00 RSD",
          "law_cited": "član 148 Zakona o parničnom postupku"
        }
      }
    }
  ]
}
```

### Fields, and why each one exists

- **`filename`** — path *relative to `documents/`*, including the dataset
  subfolder (`a_clean_digital/...`, `b_typical_serbian/...`,
  `c_nightmare/...`). This is how `dataset` gets derived — see above.
- **`difficulty`** — one of `easy` / `medium` / `hard` / `nightmare`. A
  *separate axis* from `dataset`: Dataset B can still contain an easy
  document, and a genuinely brutal edge case could technically live in A
  if the digital source itself is ambiguous. This is what lets a report
  say "Easy 99.8% / Medium 97.2% / Hard 91.4% / Nightmare 82.1%" instead
  of one flat average that hides where the system actually breaks.
- **`annotator` / `reviewed_by` / `agreement`** — two people should
  independently read a non-trivial fraction of this dataset. When they
  disagree (`agreement: false`), that document's mismatches are reported
  separately from AI errors — a disagreement between two lawyers about
  when a deadline actually falls means the *ground truth itself* is
  uncertain, not that the extraction was wrong. Founder's own words: "Ako
  se dva advokata ne slažu oko roka, onda AI možda nije pogrešio. Ground
  truth je pogrešan." Treating every mismatch as an AI failure when some
  are genuinely ambiguous ground truth would understate real accuracy.
- **`error_source`** *(optional, second round of feedback, 2026-07-15)* —
  when a document is hard to annotate or the annotators disagree, note
  *where the difficulty actually comes from*: one of `ocr`, `parser`,
  `regex`, `heuristics`, `llm`, `ground_truth`, `human_annotation`,
  `unknown`. Example: two advocates disagreeing on a deadline reading →
  `error_source: "ground_truth"`, because the source of the problem isn't
  the AI at all. This is the annotation-side twin of the production
  `error_source` field (see below) — same taxonomy, same reason for
  existing: six months from now, "where should I actually spend time" is
  a very different question from "is accuracy up or down."
- **`beleska`** *(optional)* — why this document is hard, or why a
  particular value is the correct one when it isn't obvious. This is
  annotation-time context, not the same thing as a production correction
  reason (see below) — it explains the *ground truth*, not a specific
  extraction failure.

Rules for filling in `expected.entities`:
- **Only include a field if the document actually contains it.** A power
  of attorney has no `deadline` — omit the key entirely (or set it to
  `null`), don't guess. The benchmark only scores a field where ground
  truth says it should be found; it never penalizes a correctly-empty
  extraction.
- `document_type` must be one of the 13 values in
  `shared/intake_classify.py::DOCUMENT_TYPES`.
- Values should be the *canonical* form a human would consider correct —
  the benchmark normalizes whitespace/case before comparing, so exact
  formatting quirks don't matter, but the substance must be right.

## Running the benchmark

```
python scripts/intake_accuracy_benchmark.py
```

Reads every annotated document, runs it through the real
`shared.intake_classify.classify()` and `shared.intake_extract.
extract_all_entities()` — the exact same functions production uses, not a
reimplementation — and compares against `annotations.json`. Reports:

- Overall and per-entity-type accuracy (as before)
- **Broken down by `dataset`** (A/B/C) — is the pipeline actually degrading
  on real-world scan quality, or holding up?
- **Broken down by `difficulty`** — Easy/Medium/Hard/Nightmare accuracy
  separately, not one blended number
- **Disagreement documents flagged separately** — mismatches on
  `agreement: false` documents are reported but excluded from the headline
  accuracy number, since the ground truth itself is contested there
- **Stability** (see below) — not just "is accuracy up or down," but "did
  any single entity type quietly collapse while the average looked fine"

Appends to `docs/accuracy_history.json`, tagged with the LEC `VERSION` at
run time, so every future run shows the delta against the last one
(`git log -p docs/accuracy_history.json` is the accuracy changelog).

## Stability KPI

Founder's point (2026-07-15): overall accuracy moving from 96.8% to 96.7%
is noise. `deadline` accuracy moving from 98% to 84% is not — and a
blended average will hide exactly that. The benchmark computes, per run,
the single largest per-entity-type accuracy drop versus the previous
recorded run, and surfaces it explicitly (`stabilnost.najveci_pad`) rather
than only reporting the headline number moving a fraction of a point.
A large single-entity drop between two LEC versions is a stronger signal
to investigate than a small headline movement — and via `error_source`
(production or annotation), a regression can usually be traced to a
specific layer (OCR / parser / regex / heuristics / LLM / ground truth)
before touching any AI code.

## Production correction reason & error source (related, different mechanism)

When a lawyer corrects a low-confidence field in the live product
(`POST /api/smart-intake/entities/{id}/correct`), they can *optionally*
supply a `reason` and an `error_source` — captured into
`intake_processing_outcomes` alongside `user_corrected`/
`fields_corrected`. That's a different signal from `beleska`/`error_source`
above: it's "why did production get this specific instance wrong,"
accumulated at real usage scale, not annotation-time context on a curated
benchmark set. Both matter; neither replaces the other. The shared
taxonomy (`ocr` / `parser` / `regex` / `heuristics` / `llm` /
`ground_truth` / `human_annotation` / `unknown`) is deliberate: six months
of production `error_source` data answers "where do I actually spend
engineering time" — maybe it's not the AI, maybe it's OCR, maybe it's the
regex, maybe it's the annotation process itself.

## What this does NOT replace

The founder's live KPI targets (OCR success rate, review-fields-per-
document, correction rate, LLM fallback %, processing latency) are
measured continuously from real production usage via
`GET /api/smart-intake/admin/accuracy` — that's operational telemetry, not
ground-truth accuracy. This benchmark is the other half: does the system
actually get the *right* answer, not just a confident one.
