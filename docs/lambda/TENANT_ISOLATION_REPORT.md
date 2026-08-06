# Tenant Isolation Report — Program Lambda, Certification 003

Combines Agent 3 (Horizontal Privilege Escalation) and Agent 4 (Vertical Privilege Escalation), both
independently re-verified by Agent 8 (Adversarial Certification).

## Horizontal — attack as User A reaching User B's data

**Result: 0 confirmed VULNERABLE.** Every named feature examined fresh (Workspace, Case Genome, Morning
Briefing, CIO, Digital Twin, Strategy Simulator, Notifications, Hearings/Ročišta, Copilot's orchestrated
intents) came back CERTIFIED SAFE with a concrete attack scenario tried and a file:line ownership gate
verified for each. Full per-feature table in `ATTACK_MATRIX.md`.

**Finding — FIXED: concurrent unscoped fetch before ownership check completes.** A systemic pattern found
identically in 3 files: `routers/case_commander.py::_dohvati_predmet_kontekst`, `routers/digital_twin.py::
_dohvati_kontekst_predmeta`, `routers/copilot.py::_handle_analiza_predmeta`/`_handle_plan_predmeta`. The
ownership-scoped `predmeti` query ran **inside** the same `asyncio.gather()` as 3-4 sibling queries (document
text, notes, timeline) instead of before them — every caller already discarded the sibling data on a 404/
not-found before it reached a response or GPT prompt (confirmed via independent re-trace by Agent 8, not
upgraded to an active leak), but a foreign tenant's full document text/notes transited process memory on
every guessed `predmet_id`, "one bad refactor away from an actual leak."

**Fix**: the ownership query now runs first, alone; siblings only fire once ownership is confirmed — same
shape `routers/strategy_simulator.py`'s helpers already used correctly. Applied to all 3 files, with careful
preservation of each file's own exception-handling shape (`digital_twin.py`/`case_commander.py` use
`.maybe_single()`/list-based checks that don't raise on 0 rows; `copilot.py`'s two handlers use `.single()`,
which DOES raise on 0 rows, so the hoisted query there is wrapped in its own `try/except` to preserve the
original graceful-degradation behavior — a real regression risk caught and corrected during implementation,
not assumed safe). **Status: FIXED.** Proof: `tests/test_lambda003_hoisted_ownership_checks.py` (6 tests) —
proves sibling tables are never queried when ownership fails, and still fire correctly for a real owner, in
all 3 files.

## Vertical — User → Firm Admin → Founder → System

**Result: 0 confirmed VULNERABLE.** No hidden admin path, no role confusion, no cached permissions, no JWT
role-claim trust, no delayed revocation-on-removal, no service-role escalation reachable by a normal request
— each checked with fresh source evidence, not cited from prior sprints. Full detail and the 2 NEEDS-DEEPER-
LOOK/debt items (auth fallback revocation gap, "admin" definitional drift) are in `AUTHORIZATION_FORENSICS.md`
since they're enforcement-mechanism findings, not endpoint findings.

One prior confirmed vertical bug (`zadaci.py`'s admin-delete branch, fixed in Certification 002) was used as
the template attack shape for this sprint's own sweep — re-verified still fixed, not re-broken; every other
`is_admin`-gated branch in the codebase was checked against the same scrutiny and found correctly scoped to
the ADMIN'S OWN firm (`routers/kancelarija.py::promeni_ulogu` double-scopes correctly, `routers/
admin_dashboard.py`'s ~17 routes are 100% covered by `_require_founder`, `routers/portal_monitoring.py`'s
cron-secret path still requires real authentication, not just secret knowledge).

## Adversarial re-verification summary (Agent 8)

Both the horizontal hoisting finding and every vertical CERTIFIED claim were independently re-traced with
Agent 8's own file:line evidence, not repetition of the original agents' citations. Zero refutations, zero
narrowings — the horizontal finding's "not currently exploitable" claim specifically survived a dedicated
attempt to find an already-live leak path in `digital_twin.py`, traced line by line including the caller's
own exception handling.
