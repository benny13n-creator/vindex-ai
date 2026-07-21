# CONTRACT 01 — Production Verification (D3/D9 closure)

**Date:** 2026-07-21
**Environment:** Production (`https://czsxymueizfqrbbgqqob.supabase.co`), real OpenAI API calls, no mocks.
**Commit under test:** `8f54f54` (D3 fix — `api.py::kreiraj_predmet` emits `PredmetKreiran`), verified by test harness at `5bcc226` (`scripts/contract01_e2e_verify.py`, extended + encoding fix).
**Purpose:** Close G-001/G-002 from `Open` (code exists) to `Verified` (proven end-to-end against production) — see `VINDEX_OPERATIONAL_GAP_REGISTER.md` and `VINDEX_OPERATING_SYSTEM_CONTRACTS.md` CONTRACT 01.

---

## Input

Real API calls, no direct DB writes, no simulated events — same path a lawyer's browser takes:

1. `POST /api/predmeti` — `naziv: "[E2E CONTRACT01] Test predmet 2026-07-21"`, `opis` containing a real minimal case (parties, event date, legal basis, evidence, deadline, risk — see `scripts/contract01_e2e_verify.py::CASE` for full text), `tip: "radni_spor"`.
2. `POST /api/predmeti/{id}/upload` — one `.docx`, a short wage-dispute complaint (`tuzba.docx`, 5 paragraphs, real Serbian legal text, not placeholder content).

Run twice in immediate succession (first run hit the console-encoding bug described below; second run is the clean reference run). Both produced identical PASS/FAIL results.

## Output

| Field | Run 1 | Run 2 (reference) |
|---|---|---|
| `predmet_id` | `b3f7eae5-3910-4c22-a898-b662c36cd30c` | `87b76dc2-c029-4825-95de-6df78a746940` |
| Genome version | 1 | 1 |
| Genome verification decision | `approve_with_warning` | `approve_with_warning` |
| `GenomeUpdated` event dispatched | yes | yes |
| `audit_immutable` row (`genome_refresh`) | yes | yes |
| Total elapsed | 36.2s | 32.0s |

Pipeline step detail (run 2, `predmet_istorija` `[Pipeline]` summary row):

```
5 uspesno / 3 preskoceno / 0 neuspesno (od 8)
  - analiza_dokumenata:  SKIPPED — Nema uploadovanih dokumenata (ocekivano: cita se drugi izvor, ne ovaj upload)
  - auto_linking:        SKIPPED — Nema povezanih klijenata (ocekivano: nema klijenta u testu)
  - ekstrakcija_rokova:  SUCCESS — 1 rok(a) dodat(o)
  - kalendar:            SUCCESS — Kalendar sadrži rokove predmeta
  - strategija:          SUCCESS — Inicijalna strategija generisana
  - hcc:                 SKIPPED — Nema zakazanih ročišta u narednih 90 dana (ocekivano: test ne kreira 'rocista' red)
  - risk_snapshot:       SUCCESS — Rizik: srednji
  - copilot_preporuka:   SUCCESS — Inicijalni savet generisan
```

Two `[E2E CONTRACT01] Test predmet 2026-07-21` cases now exist in production, clearly labeled and filterable, kept as regression cases per existing policy (same as the `47dc4817...` case from 2026-07-19).

## Assertions

| # | Assertion | Result |
|---|---|---|
| 1 | Classification automatic (`predmet_dokumenti` populated) | PASS |
| 2 | Evidence Vault write automatic (`predmet_dokazi` rows exist) | PASS |
| 3 | Case Genome regeneration automatic (`case_dna` with version) | PASS |
| 4 | `PredmetKreiran` event fired (inferred from #5 — in-memory publish, not written to the durable outbox, so pipeline execution is the only externally observable proof; see script docstring) | PASS |
| 5 | `run_case_pipeline()` actually ran for the standard `POST /api/predmeti` path (D9) | PASS |
| 6 | Audit row for `predmet_create`/`dokument_upload` (D22) | **FAIL — known, unrelated to D3/D9, not attempted by this change** |
| 7 | Pipeline AI output non-trivial (at least one of `ekstrakcija_rokova`/`strategija`/`hcc`/`risk_snapshot` actually succeeded, not just "pipeline ran") | PASS (3 of 4 succeeded: `ekstrakcija_rokova`, `strategija`, `risk_snapshot`) |

## Result

**D3 and D9 verified end-to-end in production.** `G-001` and `G-002` move from "Closed (code)" to "Closed + Verified" — see coverage update below.

**One incident during verification, non-blocking:** the first run crashed the test harness's own diagnostic print with `UnicodeEncodeError` (Windows console defaults to `cp1252`; pipeline messages contain Serbian diacritics). This happened *after* all substantive checks had already printed and all production writes had already completed — a test-harness display bug, not a system bug. Fixed in `commit 5bcc226` (`sys.stdout.reconfigure(encoding="utf-8")`), confirmed fixed by the clean second run above. Classified per the founder's requested triage order: **test bug**, not pipeline/event/AI/config.

**Known, intentionally out-of-scope gap:** check 6 (D22, audit trail for case/document creation) still fails — this was never claimed as fixed by the D3/D9 change and remains a separate, tracked, open item.
