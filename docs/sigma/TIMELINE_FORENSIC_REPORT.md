# Timeline Forensic Report — Program Sigma, Master Sprint 002 (2026-08-06)

Phase 6 (cross-subsystem state agreement) and Phase 7 (forensic certification — assume the timeline is
wrong, try to prove it) deliverable.

## Phase 6 — Do Genome/Strategy/Case Actions/Workspace/Dashboard/Timeline always agree?

**For the deterministic chain (Genome, Timeline, Case Actions, Workspace, Notifications), yes — by
construction, already proven by this whole engagement's prior sprints, re-confirmed unchanged this
sprint.** `handle_case_changed` runs `genome_refresh → timeline_entry → refresh_case_actions →
project_notifications` sequentially for a single event, each step reading the freshly-updated state of the
step before it (Program Omega Sprint 003/Final Sprint 007's own established guarantee). `GET /api/workspace`
reads `case_actions` directly (the canonical target-set output of that chain) — never a separately-computed
copy. Dashboard reads `predmet_hronologija` directly (a different table, a different fact space — see
`TIMELINE_REGISTRY.md`) — not disagreement, but a genuinely different question ("what deadlines exist" vs.
"what needs action"), already established as intentional in prior sprints.

**This sprint's own contradiction-identity fix directly improves cross-subsystem agreement**: before the
fix, Genome's own delta computation and `case_actions`' own Rule 3 could each independently misjudge
whether a contradiction was "the same as before" — meaning the SAME underlying fact could appear
resolved-per-Genome-delta but still-open-per-case_actions (or vice versa) purely due to GPT phrasing
variance, not a real disagreement about the case. Both now share one identity function — this specific
disagreement mode is closed.

**Strategy remains the one subsystem that can go genuinely stale relative to the others** — it is
on-demand (`routers/strategija.py`) or one-shot-at-creation (`case_pipeline.py::_step_strategija`, wired
this sprint's own prior — Master Sprint 001), never auto-refreshed when new documents arrive. A case whose
Genome/Timeline/Case Actions have all moved on could still show a Strategy assessment written against an
earlier, thinner document set. This is a known, previously-documented product characteristic (Strategy is
explicitly a point-in-time analysis a lawyer re-triggers, not a continuously-live view), not a bug this
sprint discovered — restated here because Phase 6 explicitly asks the question.

## Phase 7 — Forensic certification: trying to break the timeline

### Attempt 1: lost events?
No loss mechanism found. All 15 `predmet_hronologija` writers perform a plain `insert`, never conditional
on a prior row's existence, never behind a check that could silently no-op. A crash between a writer's own
business logic completing and the `predmet_hronologija` insert executing would lose that ONE entry (not
retried, no durable-outbox wrapping this specific write) — but this is true of a wide range of
non-idempotent single-table writes across the codebase generally, not a NEW timeline-specific finding; the
CANONICAL writer (`_consequence_timeline_entry`, via `handle_case_changed`) IS crash-safe (per-event
idempotency ledger, proven by this engagement's own existing crash-recovery test suite) — the 14 OTHER
writers are ordinary synchronous inserts inside their own endpoints, with the same crash exposure as any
other single non-transactional write in the platform, not a Timeline-specific defect.

### Attempt 2: wrong order?
`predmet_hronologija` rows carry both a DB-generated insert order and an explicit `datum`/`datum_iso` — every
reader this sprint traced (`intelligence_timeline.py`, `dashboard.py`) sorts by the explicit date field, not
insertion order, so a document processed out of chronological order (the mission's own "Upload dokumenata
van redosleda" extreme test) produces a timeline entry that sorts correctly by its own `datum_iso` regardless
of WHEN it was uploaded. **This structurally handles out-of-order upload correctly for dated entries.**
`_consequence_timeline_entry`'s own narrative entries (no `datum_iso`) sort by insertion order among
themselves — appropriate, since a narrative log genuinely IS ordered by when the system processed it, not a
retroactive date.

### Attempt 3: duplicate events?
Confirmed, not new this sprint: no dedup mechanism on `predmet_hronologija` at all (`TIMELINE_REGISTRY.md`).
A retried upload, a re-processed document, or 2 of the 15 writers independently detecting the "same"
deadline from different angles (e.g. a contract's own signing date AND a Genome-extracted date for the same
event) CAN produce 2 rows. This is the SAME class of gap `SIGMA-004` (Sprint 001) already named for
client/case-number/document-content matching — extended here to timeline entries specifically. Not fixed
this sprint (same reasoning: needs a per-writer identity design, a real schema decision, not a mechanical
fix) — folded into `SIGMA-004`'s own scope rather than creating a duplicate debt item.

### Attempt 4: vanished evidence? — found and fixed, more severe than first assessed

Initial pass found `routers/evidence.py::delete_dokaz` (`DELETE /predmeti/{predmet_id}/dokaz/{dokaz_id}`)
DOES set `predmet_dokazi.deleted_at` — but wrote the literal string `"now()"` (with parentheses), not a
value Postgres's timestamptz input parser recognizes (only the bare word `now`, no parens, is a documented
special value) — the SAME bug class Program Omega Sprint 004 already found and fixed for
`case_actions.closed_at`. Every call to this endpoint either rejected the update outright or stored an
unusable value. **Fixed this sprint** — a real computed ISO-8601 timestamp, matching the established
Sprint 004 pattern exactly.

**A second, more consequential instance of the identical bug found in the same pass**:
`routers/evidence.py::klasifikuj_i_sacuvaj` — the CANONICAL evidence-classification function, called on
every single document processed — wrote `predmet_dokumenti.klasifikovan_at` the same broken way. **Fixed.**

**A third instance, the most severe, found by tracing every other `klasifikovan_at` write repo-wide**:
`routers/smart_intake.py`'s own document-insert variant-fallback loop (a 6-variant progressive-degradation
ladder, designed to drop OPTIONAL columns one migration-group at a time if an older schema is still in
place) had the SAME broken literal baked into its 3 RICHEST variants — meaning if the literal genuinely
breaks the insert (as Postgres's documented timestamp parsing behavior indicates), the loop's own broad
`except Exception` would silently treat a VALUE bug as if it were a "migration not applied" degradation,
falling all the way through to a variant carrying neither `tip_dokaza` nor `tekst_sadrzaj` at all — for
EVERY Smart-Intake-uploaded document. **Fixed.**

**Why this wasn't caught by this engagement's own extensive prior test suite**: every existing test in this
repo mocks Supabase with `MagicMock`, which accepts any value unconditionally — none of them talk to a real
Postgres instance capable of rejecting an invalid `timestamptz` literal, a scope boundary this whole
engagement has repeatedly and honestly stated (no live-database integration testing exists in this dev
environment). This is exactly the class of bug that scope boundary predicts will slip through; found here
by direct code/SQL-semantics reading, not by a test failure.

**7 more instances of the identical literal found outside this sprint's own Evidence/Timeline scope**
(`routers/client_twin.py`, `routers/knowledge_base.py`, `routers/knowledge_hygiene.py`,
`routers/knowledge_transfer.py`, `routers/sef.py`, `services/knowledge_hygiene.py`) — deliberately NOT
fixed this sprint (unrelated features, recorded as `SIGMA-011`, recommending a dedicated small cleanup
sprint rather than scope-creeping this one).

**Tests**: `tests/test_sigma_sprint002_timestamp_literal_bugs.py` — 3 tests. The 2 direct fixes
(`delete_dokaz`, `klasifikuj_i_sacuvaj`) are proven at the value level (`datetime.fromisoformat` on the
actual payload sent to the mocked `.update()` call). The `smart_intake.py` fix is proven by source
inspection (the literal string is confirmed absent) rather than a full functional reproduction — a full
`_finalize_intake_job_core` mock would not itself validate Postgres-level timestamp semantics either (same
mocking limitation), so a source-level regression guard is the honest, proportionate proof available
without live infrastructure.

### Attempt 5: breaks between evidence and events?
**Confirmed, the most significant Phase 7 finding**: no FK from `predmet_dokazi` to `predmet_hronologija`
exists anywhere (`EVIDENCE_GRAPH_SPECIFICATION.md`'s own finding (c)) — every evidence item is structurally
disconnected from the timeline. A lawyer cannot query "show me the evidence for THIS specific timeline
event" — only "show me all evidence for this case" and "show me the whole timeline for this case"
separately, with no code-enforced link between the two views. This is real and significant, but — per this
sprint's own founding principle — building the link requires new extraction/matching logic that doesn't
exist anywhere to reuse, not a wiring connection. Recorded as `SIGMA-007` (already introduced in
`EVIDENCE_GRAPH_SPECIFICATION.md`), reiterated here as the standout Phase 7 finding.

## Certification verdict

Per the mission's own rule ("ako postoji makar jedan [problem], Sprint nije završen"): this sprint is
**honestly not fully certified**. Real gaps remain — no timeline dedup (`SIGMA-004`, extended), no
evidence-to-timeline linkage (`SIGMA-007`), no revision/supersede semantics for timeline entries
(`SIGMA-009`), no SUPERSEDED-vs-UNKNOWN distinction for resolved contradictions (`SIGMA-010`). What this
sprint DID close: 4 genuinely live, previously-unknown functional bugs — the contradiction-identity flicker
(one shared, tested, reusable fix across both consumers), and 3 instances of an invalid `"now()"` literal
timestamp (evidence soft-delete, evidence classification, and Smart Intake's own document-insert fallback
ladder, the most consequential of the 3) — each fixed and tested, none left as documentation-only findings.
A precise, evidence-based map of exactly what remains is recorded, so a future sprint does not need to
re-discover any of it from scratch.
