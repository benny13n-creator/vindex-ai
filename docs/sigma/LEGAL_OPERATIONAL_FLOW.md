# Legal Operational Flow — Program Sigma, Master Sprint 004 (2026-08-06)

Phase 6 deliverable: the lawyer must see DANAS (today) / ŠTO BLOKIRA PREDMET (blocking) / ŠTA ČEKA
(waiting) / ŠTA JE ZAVRŠENO (done) / ŠTA NEDOSTAJE (missing), each with a traceable origin.

## Confirmed this sprint: Workspace already covers 4 of 5 requested buckets

`GET /api/workspace` (`routers/workspace.py:164-238`) already returns 6 buckets:

| Mission's own requirement | Workspace's own bucket | Status |
|---|---|---|
| DANAS | `danas` | Covered |
| ŠTO BLOKIRA PREDMET | `kriticno` | Covered |
| ŠTA ČEKA | `na_cekanju` (+ `predstojece`) | Covered |
| ŠTA JE ZAVRŠENO | `zavrseno_nedavno` | Covered |
| ŠTA NEDOSTAJE | *(none dedicated)* | **Gap — see below** |
| *(no mission equivalent)* | `za_pregled` | Smart Intake document review queue — a legitimate 6th bucket, not one of the mission's own 5 |

**Provenance is already solid for the 4 covered buckets**: `_normalize_case_action`
(`routers/workspace.py:60-72`) includes an `"izvor": {"dokaz": ..., "izvor_dokumenti": ...}` field on every
item sourced from `case_actions` — a lawyer (or this document's own audit) can already trace any `danas`/
`kriticno`/`na_cekanju`/`zavrseno_nedavno` item back to its own originating rule and raw evidence.

## The one real gap: no dedicated ŠTA NEDOSTAJE bucket

Missing-evidence items today only appear INDIRECTLY, via `PRIBAVITI_DOKAZ` `case_actions` rows mixed into
the priority buckets (`kriticno`/`predstojece`) — there is no bucket surfacing `shared/gap_engine.py`'s own
broader Gap Engine output (Program Sigma Sprint 003) directly, including its `hipoteza: True` (GPT-advisory,
not yet backed by a deterministic `case_actions` row) findings.

## Why this was not added this sprint

Adding a 7th bucket correctly requires fetching Genome's own `case_dna` for every relevant case in a
lawyer's ENTIRE portfolio (Workspace is portfolio-wide, not per-case) and running `shared/gap_engine.py`'s
own aggregation across all of them, then filtering out anything already represented by an open
`PRIBAVITI_DOKAZ` action (to avoid literal double-showing the same fact in 2 buckets). This is a real new
query pattern with genuine performance implications for a live, every-page-load endpoint every lawyer hits
— not a mechanical addition, and not something to guess at without live-browser verification of load time
across a realistic portfolio size. Recorded as `SIGMA-019` in the Debt Register — the mechanism to build it
FROM (`shared/gap_engine.py::collect_case_gaps`) already exists; what's missing is the portfolio-wide
fetch/filter/dedup logic and a performance check, not a new detection algorithm.

## What IS already correct and needed no fix

Workspace's own read-only nature (it computes nothing itself, only reads `case_actions`/`zadaci`/review
jobs) means this sprint's 2 fixes (`case_intelligence.py`, `copilot.py`) had no Workspace-side counterpart
to touch — Workspace was never independently generating next-actions in the first place, only correctly
displaying what `case_actions` already decided.
