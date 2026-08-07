# UI_TRUTH_MAP.md — Operation Singular Intelligence, Mission 001, Team D

Trace of every visible risk/readiness/strength/probability/confidence metric across every lawyer/
client-facing screen, re-verified against current code.

## Confirmed genuinely unified (no action needed)

Three of four case-workspace risk surfaces — Cockpit badge, Matter Intelligence bar, Command Center —
are confirmed unified onto `services/risk_engine.py::calculate_procesni_rizik` via `api.py`'s
`predmet_workspace`/`_deterministic_risk`. `index.html` even contains an explicit `display:none` with a
code comment stating a duplicate badge (`mi-rizik`) was deliberately hidden to avoid "visuelno
dupliranje" — direct evidence this exact discipline was already applied once, correctly, by a prior team.

## Confirmed still open (re-verified with current line numbers)

**`SINGLEBRAIN2-DEBT-002`**: Case Genome hero panel (`static/vindex.js:17206-17211`, repeated at
`:17322-17334`) labels a case "Visok rizik"/"Srednji rizik"/"Povoljna pozicija" from
`snaga_predmeta_procent` (strength), not `risk_engine.py`'s risk. Unchanged in substance from Mission
002's finding.

**`SINGLEBRAIN2-DEBT-004`**: confidence fragmentation, 15+ distinct render sites confirmed, if anything
larger than previously counted (RAG grounding, Genome completeness badge, Court Predictor/Digital
Twin/Hearing CC verdicts, document-extraction confidence, entity Confidence Graph, AI briefing
`pouzdanost_briefinga`, decision-replay's dead echo).

## New this mission — the sharpened version of DEBT-002

Since Program Tau Sprint 003 (2026-08-06, `routers/copilot.py:524`), Copilot's `verovatnoca_uspeha` was
deliberately changed to literally alias `genome.snaga_predmeta_procent` — the SAME field the Genome hero
panel reads. A good fix for "two different numbers." But the two render sites disagree on **threshold**
(Copilot: ≥60 green / Genome: ≥65 green) and **framing** (Copilot: "Verovatnoća uspeha," success-framed /
Genome: "Srednji rizik"/"Visok rizik," danger-framed) for the identical shared number.

**Reproducible scenario**: a case with `snaga_predmeta_procent = 62`. Copilot chat shows green
"Verovatnoća uspeha: 62%". The Genome/AI Analiza subtab, one click away, same session, shows orange
"Srednji rizik" for the same 62. Same case, same number, opposite color and opposite meaning. Fixed
this mission (§ Fix 4) — a UI-only threshold/framing alignment, no backend change, since the number
itself was already correctly unified.

## Confirmed clean (checked, not previously verified explicitly)

PDF exports (no risk/score/confidence text on case exports; Web3/dossier exports are a different product
domain, not overlapping vocabulary), email/SMS/Viber notifications (deadline reminders only, no
numerics), client portal (no numeric risk/strength/confidence exposed to clients), mobile view (same DOM/
JS as desktop, no separate code path).

## Not in scope for this pass, noted for completeness

CIO portfolio's `jakih`/`slabih` counts use the same 65/40 strength thresholds as the Genome hero panel —
internally consistent with Genome, a 3rd framing surface but not a same-session same-glance conflict like
the Copilot/Genome pair above.
