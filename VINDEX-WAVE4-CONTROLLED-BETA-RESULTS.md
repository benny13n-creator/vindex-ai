# VINDEX Wave 4 — Controlled Real-User Beta Results

Behavioral acceptance SHA: `1296cb6988191f5f830174b2f0c650159b70ccac`
Current production SHA (before this session's preflight fix deploys): `daf2a7015dbf8c9e268409e13587dfb260cdd8fa`
Production health: PROVEN (`/health` 200/ok on `daf2a70`, this session)
Feature freeze: ACTIVE
Bojan source: `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md` — TRACEABLE (re-verified against current code this session where relevant, not trusted at face value; it is itself 7 weeks stale)
Miroslav source: no dedicated requirements document or `M-01…M-07` numbering exists anywhere in the current repository (grepped exhaustively) — **SOURCE_UNKNOWN** for detailed numbering. One traceable canon claim found in `TASK8_FINAL_EVIDENCE_DOSSIER.md` (2026-09-10): "Bojan+Miroslav canon's core claim — Vindex should provide continuous case understanding (event → state-change → consequence → next-action)" — already validated and fixed per that dossier's own live evidence, and unaffected by any commit since (Wave 2/3 never touched `routers/evidence.py::add_dokaz` or `api.py`'s `/api/pitanje` context wiring).
Session started: 2026-09-20T~19:00Z

---

## Phase 0 — Requirement Source Lock

| ID | User | Source | Exact user outcome | Beta critical | Current evidence | Status |
|---|---|---|---|---|---|---|
| REQ-B1 | Bojan | `BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`, target workflow (header) | Novi klijent → Kreiranje predmeta → Upload dokumenata → OCR + ekstrakcija → Automatsko popunjavanje predmeta → Generisanje hronologije → Identifikacija rokova → Kreiranje obaveza → AI pregled predmeta, as ONE usable session | Yes | Individual stages independently proven in code (this doc's own Phase 1 table) and in Wave 2/3 evidence; never proven as one continuous real-user session | TRACEABLE, untested end-to-end by a real user |
| REQ-B2 | Bojan (founder's own words, line 72 of the gap analysis) | Same doc | "propose a structured obligation (naziv/datum/prioritet) from deadline language found... for lawyer confirmation" | Yes | Resolved this session (Preflight A) — satisfied by `shared/rok_potvrda.py` (UNCONFIRMED→CONFIRMED/REJECTED) + F4-fixed dashboard + already-gated `notifications.py` (`INV-2`) + already-gated reminder path (`sme_pokrenuti_obavezu`). No `case_actions` row required — the confirmed deadline itself, together with those surfaces, IS the obligation. | TRACEABLE, PROVEN via code (see Preflight A below); real-user confirmation still required |
| REQ-B3 | Bojan | Same doc, Phase 1 row "Document upload — images/scanned photos" | A photographed served document (explicitly named by the doc as "an extremely common way evidence actually arrives") can be uploaded | Conditionally — only if Bojan's actual practice includes this | At time of the 2026-08-02 audit: ❌, no image upload path on either endpoint. Not re-verified this session (out of the 3 named preflights' scope) | TRACEABLE but STALE — must be re-confirmed live if Bojan's session includes a photographed document |
| REQ-M1 | Miroslav | `TASK8_FINAL_EVIDENCE_DOSSIER.md` | Continuous case understanding: a manually-entered fact reaches the Consequence Engine (`case_actions`) and becomes visible to `/api/pitanje` | Yes | Live-proven 2026-09-10 (`case_actions` 0→2 in 5s; AI answer changed from "not defined" to the correct fact after the fix). Code paths unchanged since. | TRACEABLE, code-proven; not re-proven by a real user this session |
| — | Miroslav | (any numbered `M-01…M-07` scheme) | — | — | Not found anywhere in the current repository | SOURCE_UNKNOWN — does not block Wave 4 per this mission's own rule |

"VINDEX — CANONICAL OPERATING RULES" is this mission's own stated operating philosophy (Legal Operating System, beta readiness priority), not a separate repository document — no literal file by that name exists.

---

## Phase 1 — Three Known-Gap Preflights

### Preflight A — Confirmed document deadline → actionable obligation

**Resolution: NOT_REQUIRED (case_action bridge).** `services/case_evolution.py::_compute_target_actions` Rule 1 is confirmed sourced only from `rocista` (grepped — zero reference to `rok_potvrda`/`CONFIRMED`/`sme_pokrenuti_obavezu`), exactly as the mission stated. But `routers/notifications.py::_generate_notifications` independently reads `predmet_hronologija` (document-extracted deadlines) and is **already correctly gated**: `for r in _filtriraj_izvrsive(_sirovi, _potvrdjeni_ids(...))`, imported directly from `shared.rokovi.filtriraj_izvrsive` / `shared.rok_potvrda.potvrdjeni_ids` — the canonical gate, not a reimplementation — with an explicit in-code comment "INV-2: nepotvrdjen AI rok ne proizvodi notifikaciju." Combined with F4 (dashboard) and the pre-existing `sme_pokrenuti_obavezu` reminder gate, a CONFIRMED document deadline already reaches three real surfaces (dashboard, bell-icon notification, reminder eligibility) without needing a `case_actions` row. Bojan's own traceable requirement (REQ-B2) describes an obligation with `naziv/datum/prioritet` fields and a confirm step — exactly what the deadline row + `rok_potvrda` already provide. **Zero code change made for this preflight.**

### Preflight B — Email reminder reality

**Resolution: P1 found and fixed this session.** GitHub Actions public API (`api.github.com/repos/.../actions/workflows/299323738/runs`) confirmed the scheduled workflow ran 93/93 times "success," including 5 consecutive most-recent days — but `.github/workflows/email-cron.yml` sent `Authorization: Bearer ${{ secrets.CRON_TOKEN }}` while `routers/email_notif.py::_require_cron_or_founder()` only accepts `X-Cron-Key` or a valid founder JWT. The bare `curl` had no status check, so every likely-403 response still reported green. **Fixed:** commit `eea19093` — header corrected to `X-Cron-Key`, job now fails loudly (non-zero exit + `::error::`) on any non-2xx. 5 focused tests, mutation-tested. **Not yet deployed** (see Founder actions below — needs explicit push/deploy authorization this session did not receive).

Live-tested this session with the disposable Wave 2/3 test account (no entitlement gate on any `/email-notif/*` endpoint):
- `POST /email-notif/profil` (activate) → `200 {"ok":true,"aktivan":true}` — a normal user CAN self-activate.
- `POST /email-notif/test` → `200 {"ok":true,"poslato_na":"..."}` — SMTP send succeeds server-side (proves `EMAIL_SMTP_HOST` is configured and the send call completes without exception). **Cannot** independently prove real inbox delivery — the disposable account's email domain is not a real, checkable mailbox. This is why Phase 3 step 10 requires Bojan's own inbox.
- Test profile deactivated afterward (`DELETE /email-notif/profil` → `200`).

**Not independently provable by this session:** whether the `CRON_TOKEN` GitHub secret's value equals production's `CRON_SECRET` env var. Flagged for founder verification.

### Preflight C — Miroslav source

**Resolution: SOURCE_UNKNOWN for detailed numbering, does not block Wave 4.** Exhaustive repo grep for "Miroslav" found only two mentions: `TASK8_FINAL_EVIDENCE_DOSSIER.md` (the canon claim, REQ-M1 above) and an unrelated first-name in a test-data fixture (`scripts/test_crm_scale.py`). No `M-01…M-07` document exists. Per this mission's own instruction, Phase 4 proceeds using only REQ-M1 plus any direct Miroslav input gathered during the real-user session.

---

## Phase 2 — Workflow Results

| ID | User | Source | Workflow | Expected user outcome | System result | User result | Status | Severity | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| W4-PF-A | — | REQ-B2 | Deadline→obligation bridge | Confirmed deadline is treated as an obligation somewhere real | Code-proven: dashboard (F4) + notifications (INV-2) + reminder gate, no case_actions needed | N/A — code preflight | REAL_USER_PROVEN (code) | — | This doc, Preflight A |
| W4-PF-B | — | Preflight B | Email cron scheduler | Daily reminder job actually authenticates and sends | Was returning likely-403 silently for 93 runs; header + failure-visibility fixed | N/A — code preflight | FAIL_P1 → fix committed, **deploy pending founder authorization** | P1 (until deployed+reverified) | Commit `eea19093`, GH Actions API run history |
| W4-PF-C | — | Preflight C | Miroslav source discovery | Locate traceable requirements or confirm absence | No numbered doc found; one canon claim found and already validated | N/A | NOT_APPLICABLE (informational) | — | This doc, Preflight C |
| W4-B-1 | Bojan | REQ-B1 | Full intake→matter→document→deadline→confirm→reminder session | Bojan completes the workflow unaided | Not run — requires Bojan's real account/session | NOT_RUN | NOT_RUN | — | See Action Pack below |
| W4-B-2 | Bojan | REQ-B2 | Deadline confirm/reject via UI | Bojan can tell proposed vs. confirmed, confirms correctly | Not run | NOT_RUN | NOT_RUN | — | See Action Pack |
| W4-B-3 | Bojan | Preflight B | Test email + real reminder delivery | Real inbox receipt | Not run — requires Bojan's real inbox | NOT_RUN | NOT_RUN | — | See Action Pack |
| W4-M-1 | Miroslav | REQ-M1 | Manual fact → AI sees it | Miroslav confirms newly added fact is reflected | Not run — requires Miroslav's real session | NOT_RUN | NOT_RUN | — | See Action Pack |

Rows W4-B-1…3 and W4-M-1 cannot be closed by this session: per the mission's own Human-Access Rule, synthetic automation may not substitute for the real Bojan/Miroslav sessions. See the consolidated action pack below.

---

## Current status

**Zero staff/DB workarounds used.** All live checks this session used the app's own normal authenticated API paths with a disposable, non-entitled test account (created in an earlier session), cleaned up after each use.

**Open P1:** 1 — email cron auth (Preflight B), fix committed (`eea19093`), not yet deployed pending founder push/deploy authorization (not granted in this mission's text, unlike prior Wave 2/3 missions which explicitly granted it).

**Open P0:** 0

Wave 4 is **NOT CLOSED** — real Bojan and Miroslav sessions have not occurred. See the action pack.
