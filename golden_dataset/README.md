# Smart Intake Golden Dataset

This is the benchmark the founder asked for in the Validation Sprint
(2026-07-15): real documents, manually verified ground truth, measured
against the actual production classification/extraction code — not unit
tests with synthetic fixtures. Unit tests prove the code runs. This proves
the AI is *accurate*, and gives every future change a number to move.

**This directory ships empty on purpose.** Nothing in here was fabricated
to look like real accuracy data — that would defeat the entire point.
Populate it with real (anonymized where needed) documents from actual
practice, per the founder's target: ~100 judgments, ~100 lawsuits, ~100
powers of attorney to start.

## Structure

```
golden_dataset/
  documents/
    presuda_001.pdf
    presuda_002.pdf
    tuzba_001.pdf
    ...
  annotations.json
```

## Annotation format

One entry per document in `annotations.json`:

```json
{
  "dokumenti": [
    {
      "document_id": "presuda_001",
      "filename": "presuda_001.pdf",
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

Reads every document in `documents/`, runs it through the real
`shared.intake_classify.classify()` and `shared.intake_extract.
extract_all_entities()` — the exact same functions production uses, not a
reimplementation — and compares against `annotations.json`. Prints
per-entity-type accuracy, and appends the result to
`docs/accuracy_history.json` so every future run shows the delta against
the last one (`git log -p docs/accuracy_history.json` is the accuracy
changelog).

## What this does NOT replace

The founder's live KPI targets (OCR success rate, review-fields-per-
document, correction rate, LLM fallback %, processing latency) are
measured continuously from real production usage via
`GET /api/smart-intake/admin/accuracy` — that's operational telemetry from
`intake_processing_outcomes`, not ground-truth accuracy. This benchmark is
the other half: does the system actually get the *right* answer, not just
a confident one.
