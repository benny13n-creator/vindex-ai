# Duplicate Classification Report — Program Intake Sprint 003 (2026-08-05)

Phase 6 requirement: prove no contradictory classifications can coexist for the same document (same hash,
content, OCR, metadata). Full evidence: `.vindex_ai_team/decisions/
2026-08-05_intake_sprint003_fork_classification_inventory_duplicates.md` (Fork A, §Phase 6).

Three distinct, precisely separated findings — not one blurred claim.

## (a) The classifier race produces an unpredictable single value, not a stored contradiction — but a sharper, worse defect sits next to it

`predmet_dokumenti.tip_dokaza` is a plain `TEXT` column with no CHECK constraint; Postgres single-row
`UPDATE`s are atomic, so at any instant there is exactly ONE value in that column for a given row. The
already-known classifier race (`intake_worker.py` → `smart_intake.py` finalize → the async `evidence.py`
overwrite) makes the FINAL value non-deterministic, but does **not** produce two contradictory values stored
simultaneously in the same field. This is a confirmed distinction, not an assumption: a reader querying
`tip_dokaza` mid-race sees either the pre- or post-value, never a mix.

**However — the losing write is not actually discarded, and this is where a real, confirmed, user-visible
contradiction lives.** `intake_documents.document_type` (Pipeline B's English-vocab staging value) is never
deleted at finalize — the only deletion path (`delete_partial_document`) is exclusive to Sprint 001's
crash-recovery guard, not the normal finalize flow. Consequence: `GET /api/smart-intake/jobs/{job_id}` remains
callable indefinitely after finalize and returns this frozen, pre-overwrite value — and this is not a
theoretical endpoint, it's the exact one Smart Intake's own review screen already polls, rendered through the
frontend's own hardcoded English→Serbian translation map (`_SI_DOC_TYPE_LABELS`). `evidence.py`'s 9-type
taxonomy does not contain the same label set — a document a lawyer saw as "žalba" during Smart Intake review
can, after finalize, show as "podnesak" in Evidence Vault. **Two different, human-visible, Serbian-language
labels for the same physical document, held simultaneously and indefinitely in two different tables, reachable
via two different live endpoints, with zero reconciliation code anywhere.**

**Fixed this sprint** (narrow, honest disclosure rather than a fragile reconciliation): `GET /jobs/{job_id}`
now flags `tip_moze_biti_zastareo: true` with an explanatory note once the job has been finalized, rather than
silently presenting the frozen value as current. A full fix (showing the actual current `predmet_dokumenti.
tip_dokaza` value at this endpoint) is blocked on `INTAKE-003`'s missing `intake_job_id` FK — no reliable join
exists from `intake_jobs`/`intake_documents` back to the specific `predmet_dokumenti` row without one, and
building a fragile filename/order-based heuristic match was rejected as introducing the same category of
unreliable-matching risk already flagged elsewhere (Pinecone chunk-to-document attribution, Sprint 002).

## (b) Same document uploaded twice — no consistency check exists anywhere, confirmed by exhaustive grep

`source_sha256` is computed at 3 sites (`api.py`, `smart_intake.py`, `dokument.py`) but grepping every
occurrence in the repo finds **zero** query sites that read it back for comparison. No code anywhere compares
two `predmet_dokumenti` rows' `tip_dokaza` values for agreement, even when their `source_sha256` values are
identical. If the same physical file is uploaded twice — through Pipeline A twice, through Pipeline A once and
Smart Intake once, or once into a case and once into Klijenti Trezor with a manually-typed different type —
the system has no concept that these are "the same document." This extends Sprint 002's upload-deduplication
finding into the classification domain specifically.

**Not fixed this sprint.** Building real cross-row classification-consistency checking is a genuine new
capability (a reconciliation pass, likely a background job comparing rows sharing a `source_sha256`), not a
bounded patch — tracked as `INTAKE-010`. No evidence either way of this having caused an actual production
data contradiction (out of this sprint's scope to query live rows) — this is a structural-gap finding, not an
observed incident.

## (c) Re-running `/reklasifikuj` twice — two separable questions

**(i) Concurrency defect — confirmed, code-level, model-independent.** `reklasifikuj` launches its
classification via an unawaited `asyncio.create_task` and returns immediately, with no per-document lock or
idempotency guard. Two rapid calls against the same document (double-click, two tabs, a retried slow request)
launch two concurrent background tasks, each independently calling the classifier and unconditionally
`UPDATE`-ing `tip_dokaza` with no compare-and-swap — whichever call's `UPDATE` lands last silently wins. The
exact same race shape as the already-fixed intake-finalize race (Sprint 002), self-inflicted by the very
action meant to fix a bad classification.

**Not fixed this sprint** — lower frequency/severity than Sprint 002's finalize race (an admin/manual action,
not an automated high-frequency path); a proper fix needs the same atomic-claim pattern Sprint 002 already
proved (`claim_intake_finalize`), which is a real, bounded implementation but was deprioritized behind this
sprint's higher-severity classification-review-required fix. Tracked as `INTAKE-009`.

**(ii) Model-nondeterminism — genuinely unverified, not a code bug.** `evidence.py`'s canonical classifier
(the one `/reklasifikuj` re-runs) and the newly-found `api.py::_call_metapodaci` both use `temperature=0`
(deterministic intent); `intake_classify.py`'s LLM-fallback path (`0.1`) and `dokument.py`'s classifier
(`0.2`) are non-deterministic by explicit design choice, not oversight. Whether `temperature=0` produces
bit-for-bit-identical GPT output across calls was not empirically tested (out of a read-only investigation's
means, and industry-documented as reducing but not mathematically guaranteeing repeatability due to
upstream batching/routing outside this codebase's control). Correctly left unverified rather than assumed
either way.

## Summary table

| Finding | Verdict | Status |
|---|---|---|
| Classifier race produces a stored contradiction (2 values in 1 field) | **Disproven** — atomic single-row updates, only the *final* value is unpredictable | N/A, not a defect |
| Superseded staging value survives indefinitely, shown to lawyer as if current | **Confirmed defect** | **Fixed this sprint** (staleness disclosure) |
| Same-hash duplicate uploads never cross-checked for classification agreement | **Confirmed structural gap** | Deferred, `INTAKE-010` |
| `/reklasifikuj` concurrency (no lock, double-click races itself) | **Confirmed defect**, code-level | Deferred, `INTAKE-009` |
| `/reklasifikuj` model-nondeterminism at `temperature=0` | **Genuinely unverified** | Not applicable — correctly left unverified |
