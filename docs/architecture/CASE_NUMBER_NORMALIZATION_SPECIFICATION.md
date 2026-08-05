# Case Number Normalization Specification — Program Intake Sprint 007 (2026-08-05)

Mission requirement (Debt 3): a single case number can be entered as "P 123/25", "P-123/25", "P123/25",
"P-123-25", or "P 123 - 25" — formatting must never produce different results. One canonical format; every
input must pass through it.

## The canonical form

`{PREFIX}{NUMBER}/{YEAR}` — prefix upper-cased, no separator between prefix and number, always a forward
slash before the year. Example: `P123/25`.

## The parser

`shared/case_assimilation.py::normalize_case_number()` parses a case number into its 3 semantic parts —
court-type prefix (1-3 letters, Cyrillic or Latin, either case), the main docket number (1-6 digits), and the
year (2-4 digits) — via a single regex tolerant of every punctuation/spacing convention observed in practice:

```
^\s*([А-Яа-яЂЖЉЊЋЏђжљњћџA-Za-zČĆĐŠŽčćđšž]{1,3})\s*[.\-]?\s*(\d{1,6})\s*[/\-]\s*(\d{2,4})\s*$
```

- Prefix/number separator: nothing, a space, a dot, or a dash (`P123`, `P 123`, `P.123`, `P-123` all parse
  identically).
- Number/year separator: a forward slash or a dash, optionally surrounded by spaces (`123/25`, `123-25`,
  `123 / 25`, `123 - 25` all parse identically).
- The prefix's case is normalized (uppercased); the digits are never modified.

## Why this specific design

**Exact structural parsing, not fuzzy string matching.** A case number has exactly 3 meaningful parts; once
they're correctly identified, reassembling them canonically is unambiguous and lossless. Fuzzy matching
(edit-distance, token similarity) was deliberately rejected — it would risk conflating two genuinely different
case numbers that happen to look similar, which is a worse failure mode than under-normalizing (this sprint's
governing conservatism principle, carried over from Sprint 006).

**Character set broader than the extraction-layer regexes.** `shared/intake_extract.py`'s own
`_CASE_NUMBER_RE` and `shared/intake_segment.py`'s own copy are classification/extraction-layer code —
explicitly forbidden to touch this sprint. This specification's own parser is a genuinely different piece of
code serving a different purpose (canonicalizing an already-extracted OR manually-entered string, not finding
one inside a wall of document text), so it is not bound by those regexes' own character-set coverage. A real
gap was found during this sprint's own test-writing: the original character class only covered uppercase
Cyrillic, so a mixed-case two-letter prefix like "Пж" or "Гж" (uppercase first letter, lowercase second —
exactly the shape Serbian court abbreviations actually use) would not parse at all, silently falling back to
the whitespace-collapsed (non-canonical) form. Fixed by extending the Cyrillic range to both cases.

**Unparseable input never force-fit, never silently discarded.** An input that doesn't match the expected
3-part shape falls back to a whitespace-collapsed (but otherwise unmodified) form — distinct from "no case
number" (which returns `None`), and guaranteed never to collide with any correctly-parsed canonical form
(since a canonical form always matches the exact `PREFIX+NUMBER/YEAR` shape, and a fallback string that failed
to parse by definition does not). This means an unparseable case number still gets its own stable, comparable
identity — two identical unparseable inputs still compare equal to each other — without ever being
mis-canonicalized into a shape that misrepresents it.

## Verification: 30+ representations, one identity

`tests/test_sprint007_bulletproof_intake.py::test_thirty_plus_case_number_variants_resolve_to_one_canonical_identity`
generates the full cross-product of 2 prefix-casing variants × 5 prefix/number separator variants × 6
number/year separator variants (60 total combinations) and asserts every single one normalizes to exactly
`"P123/25"`. A second test, `test_case_number_normalization_mission_named_examples`, checks the exact 5
representations the mission's own charter names verbatim. A third,
`test_case_number_normalization_cyrillic_two_letter_prefix`, proves the mixed-case Cyrillic fix above. A
fourth, `test_case_number_normalization_unparseable_input_falls_back_safely`, proves the fallback behavior.

## Where this is used

`shared/case_assimilation.py::resolve_case_ownership()` normalizes both the extracted case number AND every
comparison against `predmeti.broj_predmeta` through this one function — there is exactly one place in the
codebase that decides what a case number canonically looks like; every caller (Ownership Resolution, the
multi-case-bundle conflict check in `finalize_intake_job`, the `predmeti.broj_predmeta` write at case-creation
time) goes through it, never re-implementing normalization inline.
