# Hall of Shame

Founder's instruction (2026-07-15), before the first real law offices go
live on Smart Intake: keep a dedicated, permanent record of every document
that **spectacularly broke** the system — not the ordinary "confidence was
78%, review queue caught it, ten-second fix" case that [`evaluation/lec/`](../lec/README.md)
already measures, but the cases where something went badly wrong. Founder's
reasoning: "Najvredniji dokument nije prosečan. Najvredniji je onaj koji je
sistem potpuno pogrešno razumeo." A year from now, this folder — not the
average accuracy number — is what actually determines whether Vindex is
trustworthy on the real long tail of Serbian legal paperwork.

## What qualifies

Add an incident when a document caused any of:

- A **wrong deadline** that was auto-accepted (confidence ≥90%) instead of
  routed to review — the worst possible failure mode, since the lawyer had
  no reason to double-check it.
- A **total OCR failure** on a document a human could read fine.
- **More than 5 manual corrections** on a single document — a strong
  signal something structural broke (wrong document type, garbled text,
  layout the extractor doesn't handle), not just one noisy field.
- Any other failure the founder judges "spectacular" even if it doesn't
  fit the three patterns above — this list guides, it doesn't gate.

This is **not** where routine low-confidence extractions go. Those are
exactly what the review queue and `evaluation/lec/` are for. This folder is
for the failures that would embarrass the product if a lawyer hit them
unprepared.

## What does NOT qualify

- A document correctly routed to review because confidence was genuinely
  low — that's the system working as designed, not a Hall of Shame entry.
- A single field correction under the 5-correction threshold with an
  ordinary `error_source` (see below) — log it via `correction_reason` in
  production instead; it doesn't need a dedicated incident record.

## Ships empty on purpose

Same discipline as `evaluation/lec/` — nothing here is fabricated. This
folder only gets entries from real production incidents or real testing
that turned up a genuine failure, never synthetic "what if" examples.

## Structure

```
evaluation/hall_of_shame/
  README.md          — this file
  incidents.json      — one entry per incident (schema below)
  documents/           — the actual document that caused each incident
```

## Incident schema (`incidents.json`)

```json
{
  "incidenti": [
    {
      "incident_id": "hos_001",
      "document_ref": "documents/presuda_pogresan_rok.pdf",
      "sta_se_desilo": "Rok za žalbu auto-prihvaćen na 03.06.2026 (datum presude), umesto stvarnog roka 15.11.2026 — advokat nije dobio review upozorenje.",
      "error_source": "parser",
      "broj_rucnih_ispravki": 1,
      "auto_prihvaceno": true,
      "uticaj_na_rok": true,
      "datum": "2026-07-20",
      "dodao": "AK",
      "resenje": "deadline_parser.py _kategorija() prosiren Cirilicnim obrascima + istekao=False tiebreaker — vidi commit 022abb3."
    }
  ]
}
```

Fields:
- **`error_source`** — same taxonomy as production `intake_processing_outcomes.error_source`
  and `evaluation/lec/` annotations: `ocr` / `parser` / `regex` /
  `heuristics` / `llm` / `ground_truth` / `human_annotation` / `unknown`.
  One shared vocabulary across all three places this concept appears —
  that's what makes it possible to answer "where do I actually spend the
  next month of engineering time" from real data instead of intuition.
- **`auto_prihvaceno`** — was this wrong value auto-accepted (≥90%
  confidence) rather than caught by the review queue? This is the single
  most dangerous failure mode — the confidence threshold itself failed,
  not just the extraction.
- **`broj_rucnih_ispravki`** — how many fields the lawyer ended up
  correcting on this one document.
- **`resenje`** *(optional, fill in once fixed)* — what was actually
  changed to fix it, with a commit reference if applicable. Turns this
  file into a living record of what Smart Intake has already survived.

## Relationship to `evaluation/lec/`

Two different questions:
- `evaluation/lec/` — "how accurate is the system, on average and by
  difficulty tier, across a representative sample?"
- `evaluation/hall_of_shame/` — "what are the specific ways it has
  actually failed badly, and did we fix them?"

A Hall of Shame document is a strong candidate for later addition to
`evaluation/lec/` (usually in `c_nightmare/`) once the underlying bug is
fixed — the fix should be provable against the exact document that broke
it, not just against a new synthetic example.
