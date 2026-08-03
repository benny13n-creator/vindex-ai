# Lawyer Zero — Phase 1 Forensic Inspection

**Scope:** notifications/reminders, calendar, tasks, knowledge base, evidence, missing-document
detection, background jobs/cron, search visibility. Read-only — no code changed. Areas already
covered earlier the same session (Smart Intake pipeline, Case Pipeline, Event Bus, Case Genome,
search's document-table fix, the deadline-chain calculator's unsafe-auto-fire finding) are not
re-investigated here.

---

## 1. Notifications / Reminders — REAL, WORKING, but silently disconnected from AI-created deadlines

Two independent, both-real mechanisms exist:

- **In-app** (`routers/notifications.py`): `_generate_notifications()` (`:131-253`) scans
  `predmet_hronologija` for deadlines within 7 days and writes `notifications` rows. Triggered
  lazily — `GET /notifications` (`:256-317`) auto-refreshes only if >6h since last generation
  (`:293-294`, `asyncio.create_task`). **Pull-based**: a lawyer who doesn't open the app gets nothing.
- **Email, proactive** (`routers/email_notif.py::posalji_podsetnike`, `:229-...`): wired into the
  unified daily cron (`api.py:1502-1730`, external trigger via Render/cron-job.org at 07:00 UTC,
  confirmed live — `api.py:1713-1714` calls it). Scans `predmet_hronologija` for deadlines at 7/3/1
  days out, deduplicates via `email_notif_log`, sends real HTML email. **This is the actual
  "automatic reminder" mechanism the mission wants — and it already works.**

**The break, found by cross-referencing exact string values (not assumed):** `posalji_podsetnike`
filters `.eq("vaznost", "kritičan")` (`:278`, exact literal, with diacritics). What deadline-creating
code paths actually write to that column:

| Source | `vaznost` value written |
|---|---|
| Smart Intake finalize (`smart_intake.py:514`) — the AI-extraction path | `"važan"` |
| `intake_kreiraj` (`intake.py:216`) — the primary AI-assisted creation path | `"bitan"` |
| Template path (`intake.py`'s 7 hardcoded templates) | mixed: `"kritičan"`, `"važan"`, `"informativan"` |
| Deadline-chain calculator (`rokovi_lanac.py`) | **different vocabulary entirely, no diacritics**: `"kritican"`, `"vazno"`, `"info"` |

**Consequence: every AI-extracted deadline (Smart Intake, the primary `intake_kreiraj` flow) can
never trigger the email reminder — the cron's filter never matches `"važan"` or `"bitan"`.** Only
deadlines from the hardcoded template path that happen to use the exact string `"kritičan"`
actually get emailed. This is confirmed, not inferred — exact string comparison against exact
literal values found in each source file. `api.py:5449` independently treats `["kritičan","bitan"]`
as a recognized pairing elsewhere in the codebase, suggesting the fix direction: broaden the cron's
filter (and/or normalize `rokovi_lanac.py`'s non-diacritic vocabulary), not narrow the writers.

**This is the single highest-value "connect, don't rebuild" candidate found in this inspection.**

## 2. Calendar — REAL, WORKING, automatically connected

`routers/kalendar.py::_aggr_events` (`:45-...`) aggregates `rocista` (hearings) + `predmet_hronologija`
directly by date-range query — no separate manual calendar entry required. Any deadline written to
`predmet_hronologija` (by any path) is automatically calendar-visible. No vocabulary filter found
here (unlike the email cron) — confirmed working as designed, no wiring gap.

## 3. Tasks — REAL, separate system, zero automatic creation from anything

`routers/zadaci.py` — a genuine team task-assignment system (`zadaci` table): partner assigns to a
team member, status tracking (`otvoreno→u_toku→zavrseno`), its own dashboard. Repo-wide grep for
`table("zadaci")` found exactly 2 writers: `routers/zadaci.py` itself (manual creation) and
`routers/onboarding.py` (a demo/seed task). **Confirmed: nothing in Case Genome, Case Pipeline, or
the risk engine (§6) creates a `zadaci` row automatically.** A real candidate for connecting Genome's
`nedostaje` field or the risk engine's `nedostajuci_dokazi` output into an actual trackable task,
rather than text a lawyer has to read and manually act on.

## 4. Knowledge Base — confirmed separate by design, not a wiring gap

`routers/knowledge_base.py` — a personal notes/reference tool (`user_knowledge` table, own Pinecone
namespace `kb_{user_id}`). Explicitly "lična baza znanja" (personal knowledge base) — stores a
lawyer's own notes and legal positions, not case document content. This is a different *purpose*
from case-document search, not an accidentally-disconnected duplicate — no wiring recommended here.

## 5. Evidence — a SECOND, independent classification system, not automatically triggered

`routers/evidence.py` ("Evidence Vault") runs its own LLM classification (`_CLASSIFY_SYSTEM`,
`:26-55`) producing `tip_dokaza` (evidence type: sudska_odluka/podnesak/ugovor/dopis/
medicinska_dokumentacija/finansijska_dokumentacija/javna_isprava/vestacki_nalaz/ostalo),
`pravni_elementi` (legal elements), `ai_tags` (parties/dates/amounts/court/reference), and
`kljucne_cinjenice` (key facts) — richer and legally-specific, genuinely different in kind from
Smart Intake's coarser `shared/intake_classify.py` document-type classifier (lawsuit/response/
appeal/judgment/etc.).

**Confirmed NOT auto-triggered on upload.** Its only entry point beyond direct creation is
`POST /predmeti/{predmet_id}/reklasifikuj/{dok_id}` (`:327`) — a manual, per-document action. Case
Pipeline's own step 1 (`services/case_pipeline.py::_step_analiza_dokumenata`, `:159-193`) only
*checks* whether analysis already happened (via a `predmet_istorija` marker) — if not, it returns
`FAILED` with the note *"biće analizirani pri otvaranju"* (will be analyzed when opened), i.e. it
defers to some later, lazy, on-view trigger rather than running Evidence Vault's classification
itself. **This is a duplicate-logic-adjacent finding (Rule Zero relevant): two classification
systems exist for a similar purpose, and the richer one is the one left disconnected.**

## 6. Missing-document detection — TWO independent mechanisms, one deterministic and blocked by §5

- **Case Genome's `nedostaje` field** (LLM-derived, confirmed reachable earlier this session).
- **`services/risk_engine.py::identify_case_problems`** (`routers/matter_intel.py:5-8`'s own
  docstring: *"jedini algoritam za 'sledeću akciju' u celoj platformi"* — the only "next action"
  algorithm platform-wide, a Core Consolidation decision). This one is **deterministic, not
  LLM-derived**: compares an `_EXPECTED_DOCS` table (expected document types per case type) against
  `postojeci_tipovi = {d.get("tip_dokaza") for d in dokumenti if d.get("tip_dokaza")}`
  (`matter_intel.py:266-268`) — **it depends entirely on `tip_dokaza` being set, which only happens
  via Evidence Vault classification (§5), confirmed not auto-triggered.** For a freshly-uploaded,
  not-yet-lazily-classified document, this detector has no signal and will misreport it as one of the
  "missing" expected types. **This closes the loop with §5: wiring Evidence Vault classification to
  fire automatically on document ingestion would feed both Case Genome's evidence ranking AND this
  deterministic missing-document detector — one fix, two systems fed.**

## 7. Background jobs / cron — more infrastructure than assumed, already live

`POST /api/cron/daily` (`api.py:1502-1730+`) is a real, externally-triggered (Render/cron-job.org,
07:00 UTC), authenticated (`BRIEFING_CRON_SECRET`) unified daily job, confirmed calling, in order:
`portal_monitoring.cron_proveri`, `routers/workflow.py::_check_escalations`,
`email_notif.posalji_podsetnike` (§1), `email_notif.onboarding_cron`, and (weekly)
`email_notif.posalji_nedeljni_sazetak`. This is genuinely more than Smart Intake's own queue —
confirmed live, not dead code. Not independently investigated further (out of this pass's time
budget): `_check_escalations`'s actual logic, or whether `portal_monitoring.cron_proveri` overlaps
with anything else found here.

## 8. Search visibility — confirmed blind spots

`routers/search.py`'s `_VALID_VRSTE` (`:25`) = `{predmeti, klijenti, dokumenti, billing, hronologija,
beleske}`. Confirmed by direct grep: **no query against `zadaci` (tasks, §3) or `predmet_dokazi`
(evidence-specific records, §5) exists anywhere in `search.py`.** A lawyer searching globally cannot
find a task by its name, nor evidence by its `tip_dokaza`/`pravni_elementi`/`kljucne_cinjenice` — only
by whatever also happens to appear in the underlying document's plain text (already covered via
`predmet_dokumenti.tekst_sadrzaj`, fixed earlier this session).

---

## Dead code / duplicate logic found (Rule Zero relevant)

1. **Two independent document classification systems** (§5): `shared/intake_classify.py` (Smart
   Intake, coarse document-type) and `routers/evidence.py`'s `_CLASSIFY_SYSTEM` (Evidence Vault,
   richer legal classification). Not necessarily wrong to have both (they produce different-shaped
   output for different consumers), but worth a scoped question in the map: should Evidence Vault's
   classification *replace* the coarse one for the AI-analysis-consuming paths, or do both need to
   keep running independently — this inspection did not resolve that, flagging for the map/founder.
2. **Vocabulary fragmentation on `vaznost`** (§1): at least 3 distinct spelling/value sets across
   `smart_intake.py`, `intake.py`, and `rokovi_lanac.py` for what should be one shared enum of
   deadline-importance values. Not literally duplicate code, but the same defect *shape* as
   `predmet_klijenti`'s `user_id` bug from earlier tonight — divergent conventions for the same
   concept, silently breaking a downstream consumer.

No other dead/duplicate code found in the areas investigated — `zadaci`, `kalendar`, `knowledge_base`
each appear to be single, coherent implementations with no shadow system.
