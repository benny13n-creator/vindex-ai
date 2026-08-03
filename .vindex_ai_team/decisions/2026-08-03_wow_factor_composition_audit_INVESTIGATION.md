# Wow Factor — Composition Audit Investigation

Read-only. All claims grounded in direct file reads this session; no code changed.

---

## 1. `routers/case_intelligence.py` — exact current state (confirmed accurate, one gap noted)

`_gather_case_data` (lines 82-187) runs 6 queries in parallel (`predmeti`, `lessons_learned`,
`firm_dna`, `case_patterns`, `proactive_alerts`, `decision_log`) plus 2 sequential lookups
(`client_twin_profili` by `klijent_id`, `knowledge_profiles` filtered by `oblast_prava`) — 8 total data
sources, matching prior description exactly. `_build_context_text` (190-313) formats all of this,
including a rich Case Genome section (pravna_teorija/snaga/najslabija_tacka/strategija/finansije/
nedostaje/heatmap/kontradikcije/upozorenja/zakljucak), into one text blob fed to GPT-4o.

**Endpoint**: `POST /api/intelligence/predmeti/{predmet_id}/briefing` (no request body beyond the path
param) → `{predmet_id, predmet_naziv, briefing: {sledeci_korak, razlog, kljucni_rizici[],
relevantne_lekcije[], komunikacioni_savet, potvrdjeni_obrasci[], hitnost, pouzdanost_briefinga,
napomena}, izvori: {lekcije_analizirano, firm_dna_obrazaca, alertova, odluka_na_predmetu,
knowledge_profila, komunikacioni_profil_dostupan}}`. Confirmed **not yet touched** by Litigation
Intelligence, missing-document detection (`matter_intel`), or Case Precedents/Outcome Intel data — all
four are separate, uncomposed capabilities as previously believed.

**Gap NOT previously named**: `case_intelligence_briefing` gates on `PermissionService.require("case_intelligence")` (line 320) — a feature-flag/tier check — while `get_poslednji_briefing` (the GET, line 388) only requires plain `get_current_user`. Not a security issue (GET only reads what a POST already wrote), but worth knowing before composing: any new POST-triggering composition must pass through the same tier gate.

## 2. Judge/Opponent/Precedent/Outcome endpoints — exact contracts

| Capability | Frontend call | Backend | Request | Response (key fields) | Needs manual input? |
|---|---|---|---|---|---|
| Judge & Court Profiler | `stratJudgeProfile()` (`vindex.js:3563`) | `POST /api/predictor/judge-profile` | `{sud, ime_sudije, tip_postupka}` | `{sud, sudija, ukupno_odluka_analizirano, pouzdanost_profila, profil: {tendencije[], preferirani_argumenti[], ...}}` | **Yes** — `sud` is required, free-text |
| Opponent Intelligence | `stratOpponentIntel()` (`:3599`) | `POST /api/predictor/opponent-intel` | `{protivnik_naziv, protivnicki_adv, tip_postupka}` | `{protivnik, advokatska_kancelarija, pouzdanost, analiza: {stopa_nagodbi, poznati_stil, taktike[], ...}}` | **Yes** — `protivnik_naziv` required, free-text |
| Similar Cases ("Law Firm Brain") | `litIntelBrainLoad()` (`:18276`) | `GET /api/precedenti/predmeti/{predmet_id}` | none (path only) | `{analiza (text), ukupno_slicnih, tip}` | **No** — already scoped by case, zero extra params |
| Outcome Trends | `litIntelOutcomeShow()` (`:18305`) | `GET /api/outcome-intel/predmeti/{predmet_id}` | none (path only) | `{analiza (text), ukupno_predmeta, zatvoreni, avg_vrednost}` | **No** — same, zero extra params |

**Composition implication**: Similar Cases and Outcome Trends are trivially foldable into any per-case
aggregation (Briefing, or a post-upload summary) — same `predmet_id`, no new form/parameters, no PRO
gate found on these two specifically (only the judge/opponent ones show a `currentUserIsPro` client-side
gate, `vindex.js:3569`/`:3605` — not independently verified server-side this pass). Judge/Opponent
profiling is NOT trivially foldable without solving a real data problem, next:

**Real gap found, not previously documented**: Smart Intake's `finalize_intake_job` extracts
`judge`/`court`/`plaintiff`/`defendant` as entities (confirmed `ENTITY_TYPES` in
`shared/intake_extract.py`), but its `predmeti` insert (grepped `routers/smart_intake.py` directly)
writes only `user_id, naziv, opis, tip, status` — **`tuzilac`/`tuzeni`/`sud`/`sudija`-equivalent columns
are never populated on the case row**, even though `predmeti.tuzilac`/`predmeti.tuzeni` exist as real
columns elsewhere (confirmed used by `routers/intake.py`'s conflict-check, lines 434/528-530). This
means auto-populating Judge/Opponent Intelligence from a Smart-Intake-created case cannot simply read
`predmeti.tuzilac` today — that field is empty for every Smart-Intake case. The extracted values DO
exist, but only in `extracted_entities`/`intake_documents` keyed by `job_id`, not surfaced onto the
`predmeti` row itself. Composing "auto-run opponent intel after upload" would need either (a) a small
backend addition writing `tuzilac`/`tuzeni` onto the `predmeti` row at finalize time (using entities
already extracted — a "connect existing data, populate an existing empty column" change, low risk), or
(b) reading `extracted_entities` directly at composition time. Flagging precisely so this isn't
discovered mid-build.

## 3. `services/risk_engine.py::identify_case_problems` — confirmed exact shape

`GET /api/matter-intel/predmeti/{predmet_id}` (`routers/matter_intel.py:43`), no extra params. Returns
(among other fields) `otkriveni_problemi` (line 94) = `identify_case_problems(_rizik, tip)`'s output:
`list[{"problem": str, "ozbiljnost": "kritican"|"vazan"|"info"}]` (confirmed at
`services/risk_engine.py:150-151`'s own docstring and the function body). Empty list = no problems
found. This is precisely one-line-summarizable and requires zero manual input — directly usable in a
composed "magic moment" summary (e.g., "Nedostaje X u spisu" per missing-document finding).

## 4. Smart Intake finalize — confirmed current exact behavior

`finalize_intake_job` (`routers/smart_intake.py`) returns its HTTP response (line 763:
`{ok, predmet_id, naziv, klijent_dodat, rok_dodat, dokument_povezan}`) **before** `_genome_bg` (line
694, `await asyncio.sleep(3)` then calls `_run_genome_background`) or `_evidence_classify_bg` (line 726)
have necessarily completed — both are `asyncio.create_task`'d fire-and-forget, confirmed unchanged from
prior sessions' understanding. **No status field in the finalize response indicates whether Genome/
Evidence are done.** The frontend has no way to know completion except polling elsewhere.

**Confirmed polling target**: `GET /api/predmeti/{predmet_id}/case-dna` (`routers/case_dna.py`,
confirmed earlier this session's own code, re-verified present) → `{predmet_id, predmet_naziv, case_dna,
ima_dna: bool(genome and not genome.get("greska"))}`. A frontend can poll this after finalize and use
`ima_dna` flipping `true` (with a `verzija` bump) as the completion signal. No dedicated
"is-genome-ready" endpoint exists beyond this — reusing the existing read endpoint IS the correct
"connect existing" approach, not a gap.

## 5. Broader sweep — no additional high-value pair found beyond what's already named

Searched for other "two systems, same purpose" pairs beyond the already-known CSV-import and WhatsApp
duplicates (Operation Invisible Features, unchanged): none found this pass. The four composable
per-case AI syntheses (Briefing, Judge/Opponent, Precedents, Outcome Trends) plus the deterministic
Matter Intelligence problems list are the real, concrete composition opportunity — confirmed precisely
above, not a new duplicate-logic finding. Global search's 7 types remain independently correct and
don't overlap with any of the above (different data, different purpose).

## 6. Spot-check — nothing changed, no corruption found

- `agent-notifications`/`agent_notifications`: 0 matches in `vindex.js` — still dead, consistent with
  Operation Invisible Features' census.
- `hygiene`: 0 matches — `knowledge_hygiene` still dead.
- `precedenti`/`outcome-intel`/`predictor/judge-profile`/`predictor/opponent-intel`: 11 combined
  references in `vindex.js` — confirmed genuinely wired, not dead.
- `node --check static/vindex.js`: passes cleanly — the Smart Intake UI built last mission is
  syntactically intact, no corruption.

---

## Summary — what's safely composable tonight, ranked by cost

| Composition | Cost | Blocker |
|---|---|---|
| Fold Similar Cases (`/api/precedenti/predmeti/{id}`) + Outcome Trends (`/api/outcome-intel/predmeti/{id}`) into the existing Briefing's data-gathering and prompt | Low — both already scoped by `predmet_id`, zero new params, purely additive to `_gather_case_data`/`_build_context_text`/`_BRIEFING_SYSTEM` | None found |
| Fold `identify_case_problems`'s deterministic findings into the Briefing context | Low — already one-call, one-line-per-finding | None found |
| Post-upload "magic moment" summary after Smart Intake finalize (doc type + missing docs + risk one-liner + similar-case note) | Low-medium — needs the Genome-readiness poll (item 4) since Genome isn't done when finalize returns; Matter Intel/Precedents/Outcome Intel are all independently callable immediately | Timing: must wait for or gracefully handle Genome not being ready yet |
| Auto-populate Judge/Opponent Intelligence from a freshly created case | Medium — real data gap: `tuzilac`/`tuzeni` never written by Smart Intake's finalize despite being extracted | Needs either a small backend write-through or a client-side read of `extracted_entities` — not zero-cost, flagged precisely rather than assumed free |
