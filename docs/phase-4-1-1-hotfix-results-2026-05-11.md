# Phase 4.1.1 Hotfix Results — 2026-05-11

## Summary

10 bugs in the drafting module fixed, 22 new unit tests added. All 145 tests pass. 30Q baseline unchanged (19/8/2). Pushed to main as commit `f645947`.

---

## Bugs Fixed

| # | Area | Bug | Fix |
|---|------|-----|-----|
| 1 | router.py | `_popuni_sablon` replaced intentional empty strings (`""`) with `[POPUNITI]` — broke `bonus_clan`, `napomena_clan` | Only absent keys get `[POPUNITI]`; present `""` passes through unchanged |
| 2 | compliance.py | ZR čl. 51 (max 40h/week) not checked | Added `_proveri_radno_vreme()` + `ZR_RADNO_VREME_MAX_H = 40` |
| 3 | templates.py | LLM ignored 13-digit JMBG in input | Added explicit JMBG instruction to `_EKSTRAKCIONI_BAZA` |
| 4 | router.py | `[DATUM]`, `[MESTO]`, `[RADNO VREME]` appeared when LLM omitted fields | `apply_defaults(fields, vrsta)` + `DEFAULTS_REGISTRY` fills sensible values |
| 5 | router.py | LLM returns `"15.01.2025."` with trailing period → double period in template | `normalize_date(s)` strips trailing period; `_normalize_date_fields()` applies to all date keys |
| 6 | templates.py | ZR amendments missing `86/2019` and `157/2020` | `ZR_AMENDMENTS` constant now includes the full list through `157/2020` |
| 7 | templates.py | Inconsistent ZR citation style across templates | All templates use `ZR_FULL_REFERENCE` (first mention) and `ZR_SHORT_REFERENCE` (subsequent) constants |
| 8 | templates.py | Punomoćje grammar: noun phrase after infinitive verb slot | Changed to `"preduzme sledeće radnje: {PREDMET_PUNOMOCJA}"` |
| 9 | templates.py / router.py | Sporazumni raskid ignored original contract date | Added `{ORIGINAL_UGOVOR_CLAN}` placeholder + `datum_zakljucenja_originalnog_ugovora` extraction + conditional clause builder in `_pripremi_sporazum_fields` |
| 10 | templates.py / router.py | `poslodavac_pib_clan` missing MB and zastupnik | `_pripremi_ugovor_fields` now builds `poslodavac_pib_clan` from PIB+MB with `, ` separator, plus separate `poslodavac_zastupnik_clan` |

---

## Test Results

```
145 passed, 2 warnings in 5.09s
```

- 123 existing tests: all pass (no regressions)
- 22 new tests covering all 10 bugs

### New tests by bug

| Bug | Test(s) |
|-----|---------|
| 1 | `test_bonus_clan_empty_string_not_popuniti`, `test_napomena_clan_empty_string_not_popuniti`, `test_popuni_sablon_absent_key_gets_popuniti` |
| 2 | `test_radno_vreme_45h_krsi`, `test_radno_vreme_40h_ok`, `test_radno_vreme_35h_ok` |
| 3 | `test_jmbg_hint_in_base_prompt` |
| 4 | `test_apply_defaults_datum_fills`, `test_apply_defaults_radno_vreme_fills`, `test_apply_defaults_preserves_explicit` |
| 5 | `test_normalize_date_trailing_period`, `test_normalize_date_no_trailing_period_unchanged`, `test_normalize_date_strips_whitespace` |
| 6 | `test_zr_amendments_includes_86_2019`, `test_zr_amendments_includes_157_2020` |
| 8 | `test_punomocje_grammar_preduzme` |
| 9 | `test_sporazumni_raskid_original_ugovor_present`, `test_sporazumni_raskid_original_ugovor_absent_empty` |
| 10 | `test_poslodavac_pib_mb_with_separator`, `test_poslodavac_no_pib_no_separator`, `test_poslodavac_zastupnik_filled`, `test_poslodavac_zastupnik_absent_empty` |

---

## 30Q Baseline

| Threshold | Count |
|-----------|-------|
| ✅ pass (≥0.65) | 19 |
| ⚠️ warn (0.52–0.65) | 8 |
| ❌ fail (<0.52) | 2 (Q14, Q30 — pre-existing) |

No regressions vs Phase 4.1 baseline. Changes do not touch `retrieve.py`, `detect_doc_type`, or any Phase 2.5 artifacts.

---

## Files Changed

- `drafting/compliance.py` — added `_proveri_radno_vreme()`, `ZR_RADNO_VREME_MAX_H`
- `drafting/templates.py` — full rewrite: ZR constants, 5 templates with sentinel pattern, strengthened extraction prompts
- `drafting/router.py` — full rewrite: `normalize_date`, `apply_defaults`, `DEFAULTS_REGISTRY`, fixed `_popuni_sablon`, updated `_pripremi_ugovor_fields` and `_pripremi_sporazum_fields`
- `tests/unit/test_drafting.py` — 22 new tests in Section 7
