# Legal Knowledge Flow — Program Sigma, Master Sprint 001 (2026-08-06)

Phase 6 deliverable: verify that when a new document changes the meaning of, or undermines, prior
documents, Genome actually knows — and that contradictions and missing evidence are registered, not just
theoretically detectable.

## How Genome actually detects change

Genome's contradiction/missing-evidence detection is **GPT-driven per-call, re-extracted fresh from the
full document corpus on every refresh** (`routers/case_dna.py:293-312`, `_pozovi_genome_api`). There is no
structured "document A contradicts document B" graph edge stored anywhere; `kontradikcije[].opis` is free
text, grounded by citing `lokacija_1`/`lokacija_2` ("DOK-XX str.Y", per the extraction prompt at line 142)
but not a persisted, queryable link.

**A real, deterministic diff layer sits on top of this** (`_compute_delta`, `routers/case_dna.py:315-347`):
compares the OLD Genome's `kontradikcije`/`nedostaje`/`snaga_predmeta_procent`/`najslabija_tacka.kriticnost`/
`strategija.primarni_cilj` against the NEW ones, producing `kontr_eliminisane`/`kontr_nove`/`nedostaje_delta`
counts and a human-readable alert (`_delta_alert_text`, lines 350-388), gated by significance
(`_delta_significant`, lines 391-402). This is genuine, code-verifiable "Genome must know" behavior — a new
document that changes the case's own risk profile or contradiction set produces a real, computed delta, not
a hand-waved claim.

## A real precision gap, found this sprint

The contradiction diff (`routers/case_dna.py:323-324`) matches contradictions by `(opis)[:60]`
**string-prefix set membership**, not any stable identity. If GPT phrases the semantically-identical
contradiction even slightly differently between two refresh calls — a realistic risk for a model
re-deriving the full corpus from scratch each time, not diffing its own prior output — `_compute_delta`
would report it as 1 eliminated + 1 new contradiction: a false churn signal, not a real change.

This directly bears on the mission's own mandatory scenario: **"Dodati dokument koji ruši prethodnu
tvrdnju → Kontradikcija registrovana."** The registration mechanism exists and is code-verifiable — a new
document DOES trigger a fresh Genome extraction that CAN surface a new contradiction. Its accuracy (whether
the SAME underlying contradiction is correctly recognized as "already known" across calls, vs. wrongly
churned) is bounded by GPT phrasing consistency, not purely deterministic. Not fixed this sprint — replacing
the prefix-match with a more robust identity (e.g. embedding similarity, or a stable per-contradiction ID
the model itself must echo back) is a real algorithm change to a live, GPT-facing extraction contract, out
of a certification sprint's own safe scope. Recorded as `SIGMA-002`.

## No structural fact deduplication in Genome's own storage

Because each refresh is a full fresh extraction, a `kontradikcije`/`nedostaje` item that was already true in
the OLD genome and remains true is reported *identically* in the NEW genome, not merged or referenced — the
delta layer computes set differences specifically to avoid double-ALERTING on it, but the underlying
`case_dna` row itself is a point-in-time snapshot, replaced wholesale on each refresh, not an accumulating
deduplicated fact ledger. This is a reasonable design (the alternative — incrementally patching a
structured fact graph — is a materially larger architecture, not a bug fix) but is stated here explicitly
so "Genome knows" is not overclaimed as "Genome maintains a persistent knowledge graph." It maintains a
current-state snapshot plus a computed diff against the immediately-prior snapshot — sufficient for the
mission's own stated scenarios (a new document changing/undermining a prior claim IS detected and DOES
surface as a delta), not a general multi-hop reasoning graph.

## Missing evidence registration

`case_dna.nedostaje[]` (Genome's own missing-evidence list) is GPT-advisory, embedded in the same
extraction — re-derived fresh each call, same mechanics and same precision caveat as contradictions above.
`_compute_delta`'s own `nedostaje_delta` (a simple count difference, not a per-item identity match) is
correspondingly coarser than the contradiction diff, not finer — a swap of one missing document for a
different one nets to `nedostaje_delta = 0`, correctly not alerting on a non-event, but also not
distinguishing "the SAME gap persists" from "a different gap replaced it." Named, not fixed — same reasoning
as `SIGMA-002` (a GPT-prompt/extraction-contract change, out of this sprint's safe scope).
