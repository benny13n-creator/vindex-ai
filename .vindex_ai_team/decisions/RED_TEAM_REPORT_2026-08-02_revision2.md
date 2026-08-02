# Red Team Report — Forensic Remediation Architecture Decision, **Revision 2**

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork agent — no authorship stake in
Revision 1 or Revision 2, and not the agent that produced the first pass)
**Date:** 2026-08-02
**Artifact under review:** `.vindex_ai_team/decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md` (Revision 2)
**Scope:** **Falsification-only re-check** of the 13 findings raised by the first Red Team pass
against Revision 1 (4 Critical, 5 High, 3 Medium, 1 Low). This is **not** a new full audit. No new
finding categories were hunted; anything noticed outside the list is quarantined in
"Incidental observations" and is explicitly non-blocking.

---

## VERDICT

# BLOCKING

**One HIGH finding remains open** (M-2, the dual `Limiter` instances — reproduced, and made *worse*
by a verifiably false code claim that Revision 2 introduces as its evidence). Per this project's
rule (BLOCKING requires ≥1 CRITICAL or HIGH still open), Revision 2 cannot be frozen.

**Scoreboard against the 13 prior findings:**

| Prior finding | Status | Severity if open |
|---|---|---|
| Critical 1 — Epic C wrongly coupled to Program 3 | **FULLY CLOSED** | — |
| Critical 2 — SEC-004 falsely claimed closed | **FULLY CLOSED** | — |
| Critical 3 — SEC-051 mis-binned into Program 1 | **FULLY CLOSED** | — |
| Critical 4 — delete path + SEC-045 silently dropped | **FULLY CLOSED** | — |
| High 1 — SEC-006 deferred instead of interim-fixed | **FULLY CLOSED** | — |
| High 2 — SEC-050 conflation | **FULLY CLOSED** | — |
| High 3 — Epic F: SEC-056 gating + SEC-057 false premise | **PARTIALLY CLOSED** | MEDIUM |
| High 4 — SEC-041 buried in Epic G | **FULLY CLOSED** | — |
| Medium 1 — additional missing items | **FULLY CLOSED** | — |
| Medium 2 — two `Limiter` instances | **REPRODUCED** | **HIGH** |
| Medium 3 — duplicated `_verify_token` | **FULLY CLOSED** | — |
| Low 1 — epic ordering/dependency note | **PARTIALLY CLOSED** (new mis-binding introduced) | LOW-MEDIUM |
| *(new, introduced by Revision 2)* — invented SEC-072 → FK dependency | **NEW** | MEDIUM |

Two of the three items still open are **new contradictions created by Revision 2's own fixes**, not
survivals of Revision 1 — the same failure mode as the Program 1 Revision 7→8 cycle.

---

## Per-item findings

### M-2 — Two independent `Limiter` instances — **REPRODUCED, escalated to HIGH**

**What Revision 2 now says** (Epic B, lines 108-114):
> "the codebase has **two independent `Limiter` instances with no shared counters** (audit's own
> cross-cutting note, already acknowledged in `shared/rate.py`'s docstring). Registering
> `SlowAPIMiddleware` against one instance's counters while decorated routes count against the
> other would repeat this epic's own stated standard failure... This epic's engineering task must
> explicitly verify or reconcile which `Limiter` instance the middleware binds to before considering
> SEC-011 closed."

**Original finding reproduced?** Yes. Two instances confirmed:
- `shared/rate.py:89` — `limiter = build_limiter(_get_real_ip)` (module-level singleton).
- `api.py:545-549` — `from shared.rate import ... build_limiter` → `limiter = build_limiter(_get_real_ip)` → `app.state.limiter = limiter`. **api.py builds its own second instance instead of importing the shared one.**
- `SlowAPIMiddleware` still never registered anywhere (grep over the whole repo returns only doc mentions).

**Can it still be bypassed / does the fix instruction actually resolve it? No — and the stated
diagnosis is factually wrong, in a way that would make the verification gate pass while the bug
ships.**

1. **"No shared counters" is FALSE in production.** `shared/rate.py:59-86` — `build_limiter()` passes
   the *same* `storage_uri=_REDIS_URL`, the *same* `key_func` (`_get_real_ip`), the *same* limit
   strings, and no `key_prefix`, to both instances. With `REDIS_URL` set (production), both
   instances write to the **same Redis keyspace with identical keys** — the counters *are* shared.
   They diverge only in in-memory mode (local dev / tests). Revision 2 cites `shared/rate.py`'s
   docstring as its evidence; that docstring (lines 61-67) actually says the opposite of what
   Revision 2 attributes to it: *"obe sad koriste isti `_get_real_ip` key_func i istu Redis+fail-open
   konfiguraciju, samo kroz dve odvojene instance."* Revision 2 inherited the wrong phrasing from
   the source audit's cross-cutting note and did not verify it.

2. **The real mechanism is registry divergence, not counter divergence — and it is unstated.**
   Verified directly against the installed `slowapi` source (`C:\Users\Benny\miniconda3\Lib\site-packages\slowapi`):
   - `middleware.py::_should_exempt` — *"there is a decorator for this route we let the decorator
     handle it: `if name in limiter._route_limits: return True`"*, where `limiter = app.state.limiter`.
   - `extension.py:664,704` — `.limit()` registers `name = f"{func.__module__}.{func.__name__}"`
     into **`self._route_limits`**, i.e. into whichever instance the decorator came from.
   - Every router decorates against `shared.rate.limiter` (`from shared.rate import limiter` in
     ~90 router files). `app.state.limiter` is **api.py's** instance. Its `_route_limits` therefore
     contains only api.py's own 29 decorated endpoints — **not** the 415 `@limiter.limit(...)`
     decorations in `routers/` + `klijenti/`.
   - Consequence: `_should_exempt` returns **False** for all 415 router routes. Control reaches
     `extension.py:609-628`, where `in_middleware=True` leaves `route_limits` empty →
     `combined_defaults = all([]) = True` → `all_limits += self._default_limits` = **`["60/hour"]`**.

**Concrete failure scenario.** An engineer reads Epic B, performs exactly the verification Epic B
asks for ("which instance's *counters* does the middleware bind to?"), confirms both instances point
at the same Redis, concludes the concern is resolved, and adds `app.add_middleware(SlowAPIMiddleware)`.
On deploy, the global default `60/hour` is applied *in addition to* every route's own decorated
limit, on all 415 router routes — including **125 routes decorated `30/minute` (= 1800/hour)**,
6 at `120/minute`, 2 at `100/minute`, 37 at `60/minute`. Every normally-active user is hard-throttled
to 60 requests/hour/IP across the entire product. api.py's own 29 routes are unaffected (they *are*
in `app.state.limiter._route_limits`), which makes the outage look partial and route-specific and
therefore harder to diagnose. The correct fix — collapse to **one** `Limiter` instance (`api.py`
imports `shared.rate.limiter` instead of calling `build_limiter` a second time) — appears nowhere in
Revision 2.

**Did the fix introduce a NEW contradiction?** Yes. Revision 2 elevated an unverified, false code
claim ("no shared counters") into the plan and attributed it to a source document that states the
opposite, then built a verification gate around that false mechanism.

**Residual risk / why HIGH, not MEDIUM.** The original was MEDIUM when it was merely an unnamed
omission. It is now HIGH because (a) the plan asserts a specific falsifiable code fact that is wrong,
(b) the gate it prescribes would be *satisfied* by an engineer who checks the thing the plan names,
and (c) the consequence of proceeding is a full-product availability regression, not a residual
security gap. SEC-011 is the audit's own #3 Phase-1 priority and is described there as "this single
line closes the widest live abuse surface in the report" — this is the item most likely to be
attempted first.

**Status: OPEN.**

---

### High 3 — Epic F: SEC-056 ungating and SEC-057 rescoping — **PARTIALLY CLOSED (MEDIUM residual)**

**SEC-056 ungated — accepted.** The argument (a 4th path into an already-encrypted corpus under the
same key adds no new key-rotation blast radius) is internally sound and contains no falsifiable code
claim. Nothing to break here.

**SEC-057's "search redesign" premise — CONFIRMED FALSE, Revision 2 is correct.** Verified
`routers/search.py:80-83`:
```
r  = (supa.table("uploaded_documents")
      ...
      .or_(f"naziv_fajla.ilike.%{q2}%,extracted_text.ilike.%{q2}%")
```
It reads `uploaded_documents.extracted_text`, a different table and column from
`predmet_dokumenti.tekst_sadrzaj`. The audit's own §Prioritization item 16 ("needs a
search-architecture decision first") is the thing that was wrong; Revision 2 correctly overturns it.
This is the strongest single correction in Revision 2. **Closed.**

**But the replacement reader-site list is wrong in a way that matters for an
encrypt-on-write/decrypt-on-read migration.** Revision 2 claims *"13+ reader sites across 9 files:
`case_dna.py` (×5), `evidence.py`, `evidence_graph.py` (×2), `multi_agent.py`, `case_commander.py`,
`zakon_monitoring.py`, `drafting.py`, `smart_intake.py`, `api.py:4828-4843`."* Grepped
`tekst_sadrzaj` across all `*.py`:

- **Two of the nine "reader" files are WRITE sites, not readers:**
  - `routers/drafting.py:307` — `"redni_broj": next_rn, "tekst_sadrzaj": tekst[:100_000],` (INSERT)
  - `routers/smart_intake.py:578-579` — `{**_dok_row_base, ..., "tekst_sadrzaj": text[:100_000]}` (INSERT)
- **A third write site is omitted entirely:** `api.py:4299` —
  `.table("predmet_dokumenti").insert({**_row, "tekst_sadrzaj": _tekst_preview})`. Revision 2 lists
  `api.py:4828-4843` (which *is* a read) but not this.
- **A real reader is missing:** `scripts/genome_bootstrap_sample.py:77,97` selects and reads
  `tekst_sadrzaj`. It would silently start emitting ciphertext after the migration.
- `case_dna.py` is "×5" but has **4** distinct read sites (241, 615/620, 745/750, 920/939).

Actual shape: **~12 read sites across 8 files, plus 3 write sites across 3 files.**

**Concrete failure scenario.** A migration engineer scoping SEC-057 from Revision 2's list believes
there are **zero** write sites requiring `encrypt_field()` — the three that exist are labelled as
reads. `api.py:4299`, `drafting.py:307` and `smart_intake.py:578` continue writing plaintext into a
column the read path now attempts to decrypt, producing a mixed plaintext/ciphertext column and
either decrypt exceptions or silent empty-document behaviour on newly-uploaded matters — the exact
"looks migrated, isn't" class the audit is about.

**Did the fix introduce a NEW contradiction?** Yes, a bounded one: Revision 2 replaced a false
premise ("search redesign") with an inaccurate inventory.

**Residual risk / severity: MEDIUM.** The item is explicitly scoped as `SEC-057 (design)`, so the
inventory is expected to be re-derived during design; the false premise that would have mis-sized
the whole epic is genuinely gone. Not blocking on its own.

**Status: PARTIALLY CLOSED.**

---

### L-1 (successor) — Epic G dependency notes — **PARTIALLY CLOSED, new mis-binding introduced (LOW-MEDIUM)**

Revision 2 added two explicit dependency notes to Epic G. One is correct, one attaches to the wrong
half of a finding Revision 2 itself had just split.

- **SEC-069-comparison → Epic B: CORRECT.** Gap Register (`FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md:924`)
  states verbatim: *"Timing side-channel, needs SEC-011 fixed first to matter."* ✓
- **SEC-014 → "SEC-050 (exception-leak)": WRONG HALF.** Revision 2, Epic G:
  *"**SEC-014** — Depends on SEC-050 (**exception-leak**) and the SEC-036 residual shipping first."*
  The audit's actual sentence (`:600-602`) is:
  > "`api.py:1097`. Combined with **SEC-050's audit gap** and the free-text sanitization gaps in §10,
  > a single missed escape becomes unmitigated stored XSS..."

  "SEC-050's audit gap" is the **audit-coverage** half — the audit's own §SEC-050 (widened) heading
  at `:545` is *"Audit logging covers ~4 path prefixes out of ~596 routes"*. That half is the one
  Revision 2 routed to **Epic H**, not Epic G. Revision 2 created the split and then bound the
  dependency to the wrong side of its own split.

**Concrete failure scenario.** Epic G ships SEC-050's exception-leak cleanup and SEC-036's sanitizer
gaps, declares SEC-014's precondition met, and migrates CSP off `unsafe-inline` — while the audit
gap that made the *combination* dangerous (no reconstructable record of who read/exported which
client's documents, `shared/audit.py:15` — `_AUDIT_PATHS = {"/api/predmeti","/api/klijenti","/api/billing","/api/firm"}`,
confirmed 4 prefixes) remains untouched in Epic H with no scheduling link.

**Severity: LOW-MEDIUM.** Sequencing-only; the CSP fix is not made *worse* by shipping early, and
both halves are tracked. Non-blocking.

**Status: PARTIALLY CLOSED.**

---

### NEW (introduced by Revision 2) — invented SEC-072 → FK-retype dependency — **MEDIUM**

Epic C, SEC-059 row: *"the FK retype depends on Epic E's orphan-row purge (SEC-072) landing first,
per the audit's own 'needs a live orphan-row check first' note."* SEC-033 row repeats the gate.

The audit (`:641`) says: **"Complexity: Medium per table (needs a live orphan-row **check** first)."**
A *check* is not a *purge*, and SEC-072 is a different thing entirely — `:446` "Soft-deleted client
records, including encrypted national ID numbers, are never purged". Purging soft-deleted `klijenti`
rows does not by itself guarantee `klijenti.user_id` contains no values unresolvable in `auth.users`
(the actual FK precondition). Revision 2 converted a one-line data check into a hard cross-epic gate
behind a Medium GDPR item, on a misreading of its own citation.

**Mitigating:** the *exploit-closing* half of SEC-059 (the `VINDEX_POLJA` whitelist) is explicitly
ungated in the same row — verified this is the part that matters, see below — so no live risk is
delayed. Revision 2 also raises this itself as Open Question 2, which is honest disclosure, but the
dependency is nonetheless written into the plan tables as established fact.

**Severity: MEDIUM.** Schedule-inflation on a defense-in-depth item, not a security regression.
Non-blocking.

**Status: OPEN (new).**

---

### Critical 1 — Epic C decoupled from Program 3 — **FULLY CLOSED**

Every code claim Revision 2 makes to justify the decoupling was independently re-verified. All hold:

| Claim | Verified |
|---|---|
| SEC-039 is scoped by a Pinecone `session_id` with no owning table | ✓ `uploaded_doc/session.py:35` — `def validate_session(session_id: str, namespace_prefix: str = "tmp_") -> bool`. No `user_id` parameter; the only checks are namespace existence (Pinecone query) and a `expires_at` metadata TTL (`:56-59`). Nothing DB-backed to own the session. |
| SEC-040 needs a 3-table join on `entity_id` | ✓ `shared/intake_documents.py:191` reads `extracted_entities` by `id` with no owner filter, `:197-201` updates it, and `:205` then resolves `intake_documents.intake_job_id` from `entity["document_id"]` — the chain `extracted_entities → intake_documents → intake_jobs.uploaded_by` is real and is exactly the shape Revision 2 prescribes. |
| SEC-059 is mass assignment on an INSERT, not an ownership check | ✓ `routers/import_klijenti.py:199` seeds `klijent = {"user_id": uid}`, then `:200-213` iterates **client-supplied** `payload.mapiranje` and does `klijent[vindex_polje] = val` with **no whitelist at this site** — so a mapping of any CSV column to `"user_id"` overwrites the seeded value before `.insert()` at `:195`. The `VINDEX_POLJA` membership test at `:57` lives only in the mapping-*suggestion* path. |
| Revision 2's proposed fix (`if vindex_polje not in VINDEX_POLJA: continue`) is sufficient | ✓ `routers/import_klijenti.py:32-35` — `VINDEX_POLJA` = `ime, prezime, naziv_kompanije, email, telefon, pib, adresa, grad, tip_klijenta`. `user_id` is not in it. The whitelist genuinely closes the exploit. |

Program 3 is now correctly framed as a parallel `predmet_id`-shaped track (matching
`AUTHORIZATION_PATTERN_RECOMMENDATION.md` §1's ~15 inline + 3 helper survey), neither gating nor
satisfying Epic C. **Nothing left to break here.**

---

### Critical 2 — SEC-004 honestly restated — **FULLY CLOSED**

`AUTHORIZATION_PATTERN_RECOMMENDATION.md` §5 (`:89-91`) verified verbatim:
> "…but it does not remove the underlying architectural fact named in SEC-004 (`SUPABASE_SERVICE_KEY`
> bypasses RLS entirely, so **some** application-layer check is still the only real boundary for
> every table)… it does not make the boundary self-enforcing the way real RLS would if the backend
> used a non-service-role connection. Both are worth doing; they are not substitutes for each other."

Revision 2's quotation is accurate, and the text elided by its `...` (the "far cheaper to get right /
far easier to verify" sentence) *strengthens* rather than softens the point — no quote-mining.
SEC-004 is now marked "tracked, not closed" both in Epic C's prose and in the reconciliation table.
**I tried to find a place where Revision 2 still implicitly counts SEC-004 as remediated and could
not.**

---

### Critical 3 — SEC-051 moved out of the Program 1 epic — **FULLY CLOSED**

- Program 1 spec re-verified against the **current** file: `grep -i '\bcohere\b'` over
  `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` returns **zero** matches. (A naive
  substring grep returns one hit at `:125` — the word *"coherence"* in a scorecard line. That is the
  only reason a careless check might report a false positive; the vendor is genuinely absent.)
- Cohere is a separate client outside any OpenAI chokepoint: `app/services/retrieve.py:33-36`
  (`import cohere as _cohere_lib`), `:508-517` (`_get_cohere()` → `_cohere_lib.Client(api_key)`),
  `:1214-1234` (`_cohere_rerank`, `co.rerank(` at `:1230`). Revision 2's line citation (1229-1234)
  is accurate.
- Revision 2's "Trivial — clean existing fallback" claim **verified true**: `:1219-1221` —
  `co = _get_cohere(); if not co: return _gpt_rerank(query, matches, k)`, with `_gpt_rerank` a real,
  complete GPT-4o-mini reranker at `:1148-1209`. Unsetting `COHERE_API_KEY` alone disables the
  subprocessor with a working fallback. The complexity estimate holds.
- Documentation targets exist as named: `static/dpa.html` ✓ and `privacy.html` at repo root ✓ —
  note Revision 2 writes them with *different* path prefixes, which is correct, not sloppy.

---

### Critical 4 — silently dropped items restored — **FULLY CLOSED**

- **Matter/document delete path** restored in Epic E, and §15's own text verified (`:857-859`):
  *"**Minimum set to unlock medium firms:** SEC-054 (matter-scoped retrieval filter, Low), **a real
  matter/document delete path (Medium)**, completed subprocessor annex (Low), SEC-052 fixed with
  fail-loud behavior (Low)."* Corroborated at `:413` — *"✗ No delete endpoint; blob orphaned on
  client soft-delete."*
- **SEC-045** (malware scanning, Medium-High, unauthenticated `client-portal` path) restored in
  Epic E and correctly kept distinct from SEC-045-admin (Epic G). Both appear separately in the
  reconciliation table.

---

### High 1 — SEC-006 interim fix — **FULLY CLOSED**

- The target gap is real: `grep _skini_pii` across the repo returns **zero** hits in
  `routers/case_dna.py` or `services/legal_reasoning_engine.py`, matching the audit's `:369`
  *"Zero `_skini_pii` calls… confirmed by grep."* The function exists and is reusable today
  (`main.py:1036`), already called at 4+ sites.
- Revision 2's forward-compatibility quote from the Program 1 spec is **textually accurate**:
  *"`_skini_pii`'s numeric-identifier detection becomes one input into a broader classification, not
  a separate preceding stage — PII tags are an *output* of Classification, not a thing checked
  before it."* So "wiring it in now is not throwaway work" holds.
- One citation nit, non-material: Revision 2 attributes this to the spec's **§5**. It is actually
  the **§3** stage-mapping table, row **"1. Classification"**. Row "5. Transformation" is a
  *different* row (which says `_skini_pii` gets *extended to cover names/addresses*, closing SEC-006
  as a byproduct). The quoted words are real and the argument is unaffected. Recorded as incidental.

---

### High 2 — SEC-050 split — **FULLY CLOSED**

The source audit genuinely carries two different findings under one ID, confirmed:
- `:545` — "### SEC-050 (widened) — Audit logging covers ~4 path prefixes out of ~596 routes"
  (verified in code: `shared/audit.py:15` `_AUDIT_PATHS = {"/api/predmeti","/api/klijenti","/api/billing","/api/firm"}`
  and `:19` `_DB_AUDIT_PATHS` with `_DB_AUDIT_METHODS = {"DELETE","PUT","PATCH"}`).
- `:660` — "### SEC-050 — Internal exception text returned to clients on 66+ handlers".

The Gap Register row (`:912`) only carries the exception-leak half, which is precisely how Revision 1
lost the other one. Revision 2 tracks both separately (G and H) and both appear as distinct rows in
the reconciliation table. **Closed** — with the caveat that SEC-014's dependency was then bound to
the wrong half (see L-1 above).

---

### High 4 — SEC-041 promoted out of Epic G — **FULLY CLOSED**

- Severity claim verified: Gap Register `:906` — `| SEC-041 | High | Global role assignment, no
  tenant bound | Cross-firm privilege manipulation | Medium (requires PARTNER role) | Add
  firm-boundary check | Medium |`. Revision 2's "HIGH severity, Medium complexity" matches exactly;
  Revision 1's "Low/Trivial" bin was wrong.
- Code claim verified: `klijenti/router.py:1107-1127` — `set_user_role` checks only
  `user["role"] < Role.PARTNER`, then `supa.table("user_roles").upsert({"user_id": target_user_id,
  "rola": rola}, on_conflict="user_id")`. No firm/tenant column is read or written anywhere; all
  three `user_roles` read sites (`klijenti/permissions.py:138`, `klijenti/router.py:53`) filter on
  `user_id` alone. Revision 2's fix (add `kancelarija_id`, require active membership of the caller's
  firm) is the right shape.
- Now in Epic C with an explicit "moved here from Epic G's 'whenever convenient' batch" note.

---

### M-1 — additional missing items — **FULLY CLOSED**

I reconciled Revision 2's Full Reconciliation Table line-by-line against the audit's Gap Register
(`:894-940`, 44 rows) and its narrative sections. **All 44 Gap Register IDs are present and mapped**
(004, 006, 011, 014, 024, 026, 033, 037-038, 039-046, 045-admin, 048, 050, 051-073, 069-search,
069-comparison). Five narrative-only items are additionally captured (SEC-010, SEC-032,
SEC-036-residual, SEC-044, SEC-047), plus four structural items in Epic H. I could not find an
audit-named finding that is absent. The "none deferred" claim (Open Question 3) holds.

Two spot-checks of Revision 2's *new* claims, both accurate:
- SEC-036 residual — sanitizer genuinely absent from all six named files: `grep -c html_sanitize`
  returns **0** for `routers/zadaci.py`, `kancelarija.py`, `firm_memory.py`, `learning.py`,
  `evidence.py`, `knowledge_base.py`; the 9 files that *do* import
  `security.html_sanitize` are a disjoint set (`dokument.py`, `drafting.py`, `enterprise.py`,
  `komentari.py`, `portal_monitoring.py`, `rocista.py`, `support.py`, `shared/voice_tools.py`, `api.py`).
- Epic H's Supabase Auth config export — matches the audit's own AUTH-1 recommendation verbatim
  (`:94-95`: *"…into a version-controlled snapshot (mirroring the pattern
  `scripts/export_rls_policies.py` already establishes for RLS) and assert it in CI"*), and
  `scripts/export_rls_policies.py` does exist.

---

### M-3 — duplicated `_verify_token` — **FULLY CLOSED**

- Two independent copies confirmed: `api.py:203` and `shared/deps.py:216`. They are genuinely
  divergent, not copy-paste twins: `api.py` carries an inline hardcoded ES256 JWK
  (`api.py:245-250`) plus a live-JWKS self-healing fallback (`_verify_via_live_jwks`, `api.py:277`)
  and a 1h JWKS cache (`:273-274`); `shared/deps.py` delegates to a separately-extracted
  `verify_token_local` (`:161-213`). Different JWKS-fallback *and* different logging, exactly as the
  audit's cross-cutting note (`:993`) states.
- **Epic A's SEC-058 line numbers are correct in both files** — I checked each:
  `shared/deps.py:229` → `logger.info("SDK get_user resp: %s", resp)`; `api.py:216` → the identical
  line. Revision 2's "fix both files" scoping is now right; Revision 1's single-file scoping would
  have left a live leak on every request through `api.py`'s auth path.
- Epic H separately tracks the structural dedup and correctly cross-references it as the reason
  Epic A must touch two files.

---

## Incidental observations (explicitly NON-BLOCKING — outside the re-check scope)

These are recorded only because I tripped over them while verifying the items above. **None of them
factor into the verdict**, and none was arrived at by hunting for new problem categories.

1. **SEC-058's "2 log lines" may be 4.** Both `_verify_token` copies also carry
   `logger.warning("SDK get_user: resp.user prazan — %s", resp)` (`api.py:222`, `shared/deps.py:235`)
   — same full-`resp` dump, at WARNING. Lower PII value (the empty-user branch), and Revision 2
   faithfully inherits the audit's own "delete 2 log lines" scoping, so this is an *audit* scoping
   question, not a Revision 2 defect.
2. **SEC-063 has a reconciliation-table mapping but no action row.** The table maps `SEC-063 | G`,
   but Epic G's body never lists it — it appears only parenthetically inside SEC-044's row ("same
   class as SEC-063, batch together"). Given SEC-063 is Medium-High and is the audit's own
   "fix this documentation item first," an explicit row would be safer.
3. **The audit's own SEC-011 route counts look stale.** The Gap Register says "132 routes fully
   unrated" and `docs/PRODUCTION_READINESS_REPORT_2026-07-25.md:63` says "29 od ~573 ruta". Actual
   count today: **415** `@limiter.limit(...)` decorations in `routers/` + `klijenti/`, plus 29 in
   `api.py`. Coverage has grown substantially since those documents were written. This does not
   reduce SEC-011 (the middleware is still unregistered) but it very much *increases* the blast
   radius of the M-2 finding above.
4. **`shared/rate.py:47-56` `_get_real_ip` is SEC-048 itself** — it takes the leftmost
   `X-Forwarded-For` value, which is the spoofable one. Epic B already schedules this correctly and
   correctly insists it ship with SEC-011; noted only to confirm the pairing is grounded in the
   actual code.
5. **Program 1 spec citation drift** — Revision 2's "§5" for the `_skini_pii` quote is really §3's
   stage table, row 1. Quote itself is verbatim-accurate.

---

## What held up under adversarial review

Stated plainly, because most of Revision 2 did hold:

- **All four Critical findings are genuinely closed**, not reworded. In each case I re-derived the
  underlying code fact from scratch rather than accepting Revision 2's account, and in each case
  Revision 2's version matched the code: `validate_session`'s missing `user_id`, the 3-table intake
  join, the CSV mass-assignment loop and the whitelist that would actually stop it, the
  `AUTHORIZATION_PATTERN_RECOMMENDATION.md` §5 verbatim quote, the total absence of Cohere from the
  Program 1 spec (including surviving the "coherence" false-positive trap), and §15's explicit
  naming of the delete path.
- **The single best correction in Revision 2 is SEC-057's rescoping.** I specifically tried to break
  it — the audit's own Prioritization section asserts SEC-057 "needs a search-architecture decision
  first," so Revision 1 was faithfully following the source document. Revision 2 overrules the source
  audit on verified code evidence (`routers/search.py:80-83` reads a different table entirely), and
  it is right to do so. That is the plan catching an error in the artifact it was derived from.
- **SEC-041's promotion and SEC-050's split are both correct and both were non-obvious** — the
  SEC-050 collision in particular is only visible if you read the audit's narrative sections rather
  than its Gap Register, which is exactly the reading discipline Revision 1 lacked.
- **The reconciliation table works.** I attempted to find a 45th finding it dropped and could not.
  Its existence is what made this pass's completeness check cheap and conclusive.
- **Epic A's SEC-058 line numbers survived a line-level check in both files** — the class of detail
  most likely to be confabulated in a rewrite, and it was right.

The three items that remain open share one signature, and it is worth naming: **every one of them is
a place where Revision 2 accepted a claim from a *source document* (the forensic audit's cross-cutting
note, its SEC-014 sentence, its SEC-033 complexity note) without re-deriving it from code — which is
the identical root cause the audit itself diagnoses.** Revision 2 verified the Red Team's claims
rigorously and its own inherited claims not at all.

## Required to clear BLOCKING

1. **M-2 only.** Epic B must (a) drop the false "no shared counters" claim, (b) state the real
   mechanism — `SlowAPIMiddleware._should_exempt` reads `app.state.limiter._route_limits`, which on
   api.py's instance does not contain any of the 415 router-decorated endpoints, so the `60/hour`
   default would be applied *on top of* every router route's own limit — and (c) prescribe the actual
   fix: collapse to a single `Limiter` (have `api.py` import `shared.rate.limiter` rather than call
   `build_limiter` a second time) **before** `add_middleware(SlowAPIMiddleware)`, with a
   post-registration verification that no route is subject to two limits.

Items High-3, L-1 and the new SEC-072 dependency are Medium/Low and, on this project's rule, would
leave the document at **CONDITIONAL** rather than BLOCKING once M-2 is addressed.
