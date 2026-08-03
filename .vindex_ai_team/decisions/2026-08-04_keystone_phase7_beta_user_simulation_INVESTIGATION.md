# Mission Keystone — Phase 7: Beta User Simulation (Read-Only Investigation)

**Date:** 2026-08-04. **Method:** traced actual frontend (`static/vindex.js`, 23,021 lines — no separate
`templates/*.html`, the SPA is a single file) against the backend endpoints it calls, for the 7-step
scenario in the mission brief. No code changes made.

---

## Step-by-step: what a non-technical lawyer would actually see

**1. Login → create predmet.** Standard form, PATCH/POST with try/catch → `showToast(...)` on failure
with a specific message ("Veza sa serverom nije uspela. Proverite internet i pokušajte ponovo."). No
issues found.

**2. Upload a document.** Two different upload paths exist with materially different UX:
- **Classic single-doc upload** (`pred_upload_doc`, `static/vindex.js:19570`): synchronous — the
  fetch awaits the full analysis result. Specific error messages for 415/422 (scanned PDF), 413 (too
  large), generic `r.status` for other 4xx/5xx, and a distinct network-error message. Good.
- **Smart Intake batch upload** (`siUploadAndProceed` / `_siPollJobs`, `static/vindex.js:21023-21121`):
  async job-queue based. Per-file status badges (`_SI_STATUS_LABELS`), a `failed` status shows the
  actual `last_error` text inline (`static/vindex.js:21069-21070`). Polling interval is adaptive
  (`Math.max(4000, activeJobs*1200)`, respecting the 60/min rate limit) and **never gives up** — it
  keeps polling as long as a job is active, so a genuinely slow job won't falsely look abandoned.

**3. Request AI analysis (Genome).** After upload, the backend regenerates Case Genome in the
background (`api.py`'s `_genome_bg`, fire-and-forget, no completion signal to the frontend by design —
comment at `static/vindex.js:19523-19531`). The frontend compensates with `_genomeBackgroundWatch`
(`static/vindex.js:19532-19568`): polls `/api/predmeti/{id}/case-dna` every 15s up to 90s (6 attempts),
swaps in a busy-hint message, and auto-renders the new Genome the moment its `verzija` changes.
**Finding GEN-1** (see below) — what happens if it doesn't finish in 90s.

**4. Get an AI response.** Genome's render (`_caseDnaRender`, `static/vindex.js:17383+`) is genuinely
well-built for trust: a "PREGLED" (overview) summary up front, an explicit "✓ AI provera: nema
upozorenja" / "⚠ AI provera: N upozorenja" self-verification line (`static/vindex.js:17450-17467`,
sourced from a real verification layer, not decorative), and an "AI ograničenja" section listing what
the AI does NOT have evidence for (`static/vindex.js:17469-17481`, sourced from existing
`dna._analiza_osnov`/`dna.nedostaje` fields — zero new AI calls). Copilot chat (`pred_copilotSubmit`,
`static/vindex.js:11779-11820`) shows a distinct "Obrađujem…" placeholder, removes it on both success
and failure, and surfaces `d.detail` or an HTTP status on error, or a network-specific message on
`catch`. This is materially better instrumented for lawyer trust than a typical SaaS chat widget.

**5. Edit data (correct a detail, add a note).** Two different edit surfaces:
- **Notes** (`pred_dodajBelesku`, `static/vindex.js:19504-19516`): POST, reloads detail on success,
  `showToast('Greška pri čuvanju beleške.', 'err')` on failure. Fine — a note is not a case-fact edit,
  correctly does not touch Genome.
- **Inline field edit** (`_predInlineEdit`, `static/vindex.js:11824-11890`, covers `tip`/`rizik`/`naziv`
  and likely other predmet fields): PATCH on blur/Enter, a green "Sačuvano ✓" flash on success,
  `showToast('Greška pri čuvanju.','error')` on failure. **Finding GEN-2** (see below) — editing `tip`
  (case type/legal area) or `rizik` (risk level) does **not** trigger Genome/Strategy regeneration or
  any staleness flag, even though these are exactly the fields a Genome analysis would have been
  computed from.

**6. Create a task/deadline.** Not traced in this pass (out of the specific file-budget for this fork —
flagged as not independently re-verified here; Task Engine's backend reliability was already covered by
Project Phoenix's Recovery Matrix).

**7. Return "the next day."** Genome's version badge (`v{verzija}`, `static/vindex.js:17498`) is the
only per-session staleness signal exposed to the user — it's a bare number with no timestamp
("v3" vs. "generated 2 hours ago" / "generated yesterage"). A lawyer has no way to tell, at a glance,
*when* the currently-displayed Genome/Strategy conclusion was actually produced relative to today's new
information, only that some version N exists. Nightly cron-driven `proactive_alerts` (Project Phoenix's
own recent reliability fix) are the mechanism by which the lawyer would learn about anything that
happened overnight — not independently re-traced on the frontend side this pass (out of scope: this
fork covered the frontend consumption of Genome/Copilot/upload only, not the Alerts panel's own render
path).

---

## Findings

### Wrong status shown
**None found this pass.** Both upload paths (classic + Smart Intake) have accurate, distinct status
states with no observed drift between backend state and displayed state.

### Lost data
**None found this pass.** Every write path traced (`pred_dodajBelesku`, `_predInlineEdit`, uploads) has
an explicit success/failure branch; none silently discards a failed write without a toast/message.

### Inexplicable errors
**Minor, not severe.** A few generic fallback messages exist (`'Radnja nije uspela. Pokušajte ponovo.'`
at several `kanc*` — office/firm-settings — call sites, `static/vindex.js:3168/3180/3193`), but these
are office-administration flows, not the core case-work golden path, and they're still specific enough
("action failed, try again") rather than a raw stack trace. **No raw exception text or unhandled 500
without a message was found reaching the user** in any of the traced call sites.

### Stale AI answers — **GEN-1: Silent give-up after 90s, no error state** (Medium)
`_genomeBackgroundWatch` (`static/vindex.js:19532-19568`): if Genome regeneration hasn't produced a new
`verzija` within 6×15s = 90 seconds, the poller simply stops and reverts the hint text to the default
("Obično traje 15–20 sekundi…") with **no indication that anything went wrong or timed out**. A lawyer
who uploaded a large/slow document would see the busy message quietly disappear and the *old* Genome
version still displayed, with nothing telling them "this didn't finish — click refresh" vs. "this is
already up to date." The code comment (`static/vindex.js:19523-19531`) documents this as a deliberate
"lightweight" tradeoff (reuses an existing hint element, no new component), and manual refresh does
still work — so this is a real but bounded trust gap, not a data-loss or false-success bug: the lawyer
is never told the analysis succeeded when it didn't, they're just left with ambiguity if it's slow.

### Stale AI answers — **GEN-2: Editing case-defining fields doesn't invalidate/re-flag Genome or Strategy** (Medium-High)
`_predInlineEdit` (`static/vindex.js:11824-11890`) lets a lawyer correct `tip` (legal area) or `rizik`
(risk level) inline, with a satisfying "Sačuvano ✓" flash — but neither the PATCH success path nor
`_caseDnaRender` does anything to flag that the currently-displayed Genome/Strategy output (computed
from the *old* `tip`/`rizik`) may now be based on outdated inputs. Genome only refreshes its version on
a new document upload (`pred_upload_doc` → `_genomeBackgroundWatch`), never on a metadata correction.
A lawyer who fixes a misclassified case type would see the correction save instantly, but the AI
analysis panel right below it would keep showing conclusions computed under the old classification with
no visual distinction from a fresh one. This is the most concrete "stale AI answer, presented as
current" gap found in this pass — worth a beta-gate risk-register entry even though it's a UX/trust gap
rather than a data-integrity bug (nothing is corrupted; the display is just not marked stale).

### Conflicting information
**Not confirmed either way this pass.** Did not find a case where Genome, Strategy Engine, Copilot, and
the Dashboard actively display contradictory numeric/textual conclusions about the same case
side-by-side in the same view — but GEN-2 above creates the *precondition* for exactly this (an
edited case fact + an unrefreshed Genome could produce a Copilot answer, grounded in fresh context, that
disagrees with the still-displayed old Genome summary). Flagging as a plausible but unconfirmed risk
rather than a proven finding.

### Areas not independently re-verified this pass (explicitly out of this fork's time/file budget)
- Task/deadline creation UI (step 6).
- Dashboard's day-after view and the Alerts panel's own render path (step 7, beyond confirming that
  `proactive_alerts` is the intended mechanism per Project Phoenix's own recent work).
- Whether `naziv` (case name) or other inline-editable fields beyond `tip`/`rizik` share the same GEN-2
  gap — inspected the mechanism (all fields funnel through the same `_predInlineEdit`/PATCH path, so the
  gap almost certainly generalizes), but did not enumerate every field individually.

---

## Overall impression

The single most user-trust-relevant issue is **GEN-2**: a lawyer can correct a case-defining fact and
get an instant, satisfying "Sačuvano ✓" confirmation, while the AI analysis directly below it silently
continues presenting conclusions computed from the fact *before* the correction, with no staleness
marker distinguishing "current" from "outdated." This is exactly the shape of problem a non-technical
user would not notice on their own (nothing *looks* broken — the correction saved, the analysis is
still there) but would erode trust the moment they later realize the AI's recommendation didn't account
for something they told the system days ago.

Set against that, the flow is otherwise **substantially better instrumented for lawyer trust than a
typical SaaS product at this stage**: specific (not generic) error messages at nearly every traced call
site, an async job system with per-file status and real error text, a background-regeneration watcher
that (mostly) succeeds silently and correctly, and — notably — Genome's own built-in "AI provera"
self-verification line and "AI ograničenja" (what the AI doesn't have evidence for) section, which is
precisely the kind of honest-uncertainty signal Phase 5's AI Quality Validation is looking for, already
present and wired to real data rather than decorative. A lawyer would likely find the day-to-day
experience surprisingly transparent, with GEN-2 being the one concrete gap between "looks fine" and
"is actually current."
