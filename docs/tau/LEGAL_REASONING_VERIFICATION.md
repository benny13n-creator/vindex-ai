# Legal Reasoning Verification — Program Tau, Master Sprint 004, Phase 4

**Question for every GPT legal analysis surface**: does a real Evidence → Reasoning → Conclusion chain
exist (a conclusion traceable to specific, reference-checked evidence), or does the conclusion float free?
Per the mission's own rule: no chain on something presented as more than advisory opinion is a **bug**, not
an AI limitation. Analysis only — no code changed by this task.

## 1. `services/legal_reasoning_engine.py` — VERIFIED CHAIN (the reference implementation)

Every `claim` the engine produces requires ≥1 `FACT-n` (from `predmet_dokazi`, real Evidence Vault rows)
and ≥1 `SOURCE-n` (from `retrieve.py`'s own identity-based `_build_izvori()`, never free text) —
enforced **twice**: once in the prompt's own "STROGA PRAVILA" (`legal_reasoning_engine.py:60`), and again in
code (`generate_reasoning_graph`, line 331-332: `if not chain_facts or not chain_norms or not chain.get("claim"): continue`
— any chain missing either is silently dropped before it's ever written). `model_certainty` (GPT's own
self-report) is capped at 15% weight in the final confidence score (`compute_confidence`, line 233-255) —
`evidence_coverage`/`retrieval_agreement`/`precedent_support` (all computed, not GPT-reported) carry the
other 85%, specifically so "a confident-sounding hallucination cannot dominate the score" (module's own
comment, line 241-242).

**Caveat, not a defect in the pattern itself**: this module is deliberately unwired — no automatic trigger,
no downstream consumer reads it yet (Phase 0's own binding constraint, `legal_reasoning_engine.py:17-18`).
It is the platform's strongest grounding pattern, sitting unused.

## 2. `routers/case_dna.py`'s Genome extraction — SPLIT: VERIFIED CHAIN for `kontradikcije`, NO CHAIN for `najslabija_tacka`/`snaga_predmeta_procent`

- **`kontradikcije[].lokacija_1`/`lokacija_2`**: the prompt requires a `DOK-XX` reference or an explicit
  empty field ("NIKAD ne nagađaj ili izmišljaj lokaciju," `case_dna.py:143-146`), and
  `shared/genome_validator.py::_validate_kontradikcije_lokacije` (line 102-123) hard-flags any `DOK-XX`
  reference that doesn't match a real document's `redni_broj` — called from `verify_genome()`, confirmed
  wired at `case_dna.py:753` and `:904` (both `_extract_genome`-family call sites, not orphaned).
  **VERIFIED CHAIN.**
- **`najslabija_tacka` (rizik/kriticnost/preporuka) and `snaga_predmeta_procent`**: the prompt asks for
  these as a holistic judgment (`case_dna.py:106-110, 132-136`) with **no citation requirement at all** —
  no `DOK-XX` reference, no evidence pointer, and `shared/genome_validator.py` has no validator for either
  field. Both are then treated as **canonical Genome fact** platform-wide (Core Consolidation: "Case Genome
  je jedini vlasnik istine o predmetu") — `case_intelligence.py`, `copilot.py`, and `shared/case_context.py`
  all read `snaga_predmeta_procent`/`najslabija_tacka` as established truth, not as an unlabeled opinion.
  **NO CHAIN, and this is the single most serious finding in this report**: a number/claim with zero
  evidence pointer is being consumed downstream as if it were as reliable as `kontradikcije` (which IS
  grounded). Per the mission's own rule, this is a bug, not a limitation.

## 3. `routers/evidence_graph.py`'s `OSPORAVA` edges — VERIFIED CHAIN

`validate_graph_edge_references(graf.get("nodes"), graf.get("edges"))` (`evidence_graph.py:250-251`) is
called on every generated graph, hard-flagging any edge referencing a node that doesn't exist in the real,
retrieved node set. Confirmed wired, not orphaned (this is the live code path for `POST` graph generation).
**VERIFIED CHAIN.**

## 4. `routers/case_commander.py`'s `protivnikova_strategija`/`sudska_praksa` — correctly labeled, no chain required

Both fields are wrapped in `gpt_advisory_field()` (`case_commander.py:375-376, 389-390`) — `shared/
commander_schema.py`'s own schema, `evidence=None` always, `source="gpt_advisory"`. This is the CORRECT
outcome for a field with no canonical equivalent: not a "NO CHAIN bug," because nothing here claims to be
more than opinion — the response shape itself says so structurally, per Sigma Sprint 005. **No fix needed.**

## 5. `routers/court_predictor.py`'s `procenat_min`/`procenat_max` — NO CHAIN

The prompt (`_PREDICTOR_SYSTEM`, `court_predictor.py:58-83`) instructs GPT to rely on retrieved sudska
praksa "ako je pronađena" and to say so explicitly if none was found (line 69-70) — but the JSON schema it
must return (line 72-81) has **no field for which specific precedent(s) informed the percentage**, no
`SOURCE-n`-style citation requirement, and the retrieved `decision_number` (line 123, from the same
retrieval call) is never linked back to `procenat_min`/`procenat_max` in the returned payload
(`court_predictor.py:213-214` returns the numbers with no accompanying citation list). A lawyer reading
"55-70%" has no way to know which of the retrieved cases, if any, actually drove that number, or whether
GPT used them at all versus "opšte pravno znanje" as the prompt's own fallback path allows. **NO CHAIN** —
also cross-references the pre-existing 5-way win-probability fragmentation (`PROGBETA-001`,
`docs/architecture/DECISION_REGISTRY.md`), which this finding doesn't re-litigate, but does sharpen: even
picking one canonical generator among the 5 wouldn't fix this specific gap unless that generator also
started citing its own sources.

---

## Tally

**VERIFIED CHAIN**: 3 of 5 surfaces (`legal_reasoning_engine.py`, Genome's `kontradikcije`,
`evidence_graph.py`'s `OSPORAVA` edges — plus `case_commander.py`'s advisory fields, which need no chain
by correct design).
**NO CHAIN**: 2 of 5 (Genome's `najslabija_tacka`/`snaga_predmeta_procent`; `court_predictor.py`'s
win-probability).
**CITED BUT UNVERIFIED**: none found — every surface that cites anything either verifies the citation
(reference-existence check) or cites nothing at all.

**Most serious finding**: Genome's `najslabija_tacka`/`snaga_predmeta_procent` — because Genome is
platform-wide canonical truth (Core Consolidation), this ungrounded pair is consumed downstream by
`case_intelligence.py`, `copilot.py`, and `shared/case_context.py` with the same trust level as the
correctly-grounded `kontradikcije` field, and nothing in the current architecture distinguishes them.

## Fix recommendations (reuse existing mechanisms, per this mission's own "no parallel systems" rule)

1. **Genome's `najslabija_tacka`/`snaga_predmeta_procent`**: require the prompt to name which
   `snaga_faktori[]` entries (already required, min 3, `case_dna.py:136`) or which `DOK-XX` document most
   directly supports the `najslabija_tacka.rizik` claim, then extend
   `shared/genome_validator.py::_validate_kontradikcije_lokacije`'s own pattern (same function shape, same
   `DOK-XX` regex, same hard-flag mechanism) to a new `_validate_najslabija_tacka_lokacija` check — do not
   invent a new validation framework, mirror the existing one field-for-field.
2. **`court_predictor.py`'s win-probability**: add a `koriscena_praksa: [str]` field to `_PREDICTOR_SYSTEM`'s
   own schema listing which `decision_number`(s) from the retrieved set informed the estimate (empty list
   if none used/available, matching the prompt's own existing "ako NIJE dostavljena" fallback language),
   then reference-check it against the retrieved set the same way `validate_dok_reference` checks a
   `DOK-XX` claim against a known-real set — same shape, new field, not a new mechanism.

**UPDATE (Phase 9, same sprint)**: Fix #1 (`najslabija_tacka`) implemented exactly as recommended above —
`routers/case_dna.py`'s extraction schema now has a `najslabija_tacka.lokacija` field (same `DOK-XX str.Y`
convention as `kontradikcije`, empty string if the weakness is holistic and legitimately has no single
grounding document), and `shared/genome_validator.py::_validate_najslabija_tacka_lokacija` (new function,
mirrors `_validate_kontradikcije_lokacije` field-for-field) hard-flags any invented `DOK-XX` reference, wired
into `verify_genome()`'s existing check list. 4 new tests in `tests/test_genome_validator.py`, 51/51 passing,
zero regressions. `snaga_predmeta_procent` was NOT re-touched — it already has a real, separate, wired-in
internal-consistency check (`_validate_snaga_konzistentnost`, flags if the percent contradicts the net
direction of its own `snaga_faktori`) that this report's own first pass under-credited; that check is
about internal consistency, not external grounding, but is a real, active mechanism, not "zero validation."

Fix #2 (`court_predictor.py`) is NOT implemented this sprint — named as `TAU-011` in
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` instead. It touches a live, heavily-used, paid endpoint
family (7 endpoints) already flagged in this same sprint's Phase 1 for a separate, larger issue (`predmet_id`
never used to fetch real case context, see `GPT_CONTEXT_MAP.md`) — bundling a citation-grounding fix into
that same file mid-diagnosis of a bigger problem risked under-scoping both. Deferred to whichever future
sprint takes on `court_predictor.py`'s own dedicated consolidation.
