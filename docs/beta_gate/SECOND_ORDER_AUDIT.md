# Final Beta Gate — Phase 9: Second-Order Audit

Fresh, independent review of all 18 Phase 8 fixes against the mandated
second-order questions: duplicate business logic, new truth sources,
security regressions, changed API contracts, new races, performance
regressions, new migrations, stale tests, weakened validation, accidental
GPT authority, frontend/backend divergence.

## Verdict: no new regressions. Four items require explicit disclosure — none block certification, but must not be silently omitted from the final GO/NO-GO record.

### 1. F5's real fix depends on a founder-run migration — NOT YET LIVE

`migrations/smart_contract_analyses.sql`'s `deduct_n_credits` was edited in
the repo (WHERE guard added) but, per this engagement's standing rule,
**not applied to the live database by the agent**. The Python-side fix
(`shared/deps.py::_deduct_n_credits`) is backward compatible either way —
it correctly propagates whatever the RPC returns — but the actual
balance-floor race is **only closed once the founder runs the migration**.
Until then, the live RPC still floors at 0 unconditionally and the race
described in F5 remains exploitable in production, even though the code
fix is complete and tested against the *new* RPC contract. This must be a
named, explicit action item in the Phase 11 certificate, not implied.

### 2. F1 doubles Pinecone query cost for tmp_ document Q&A

`_verify_pred_namespace_ownership`'s new tmp_ branch issues its own
Pinecone `query()` call (top_k=1) before `validate_session` issues a
second one. Before this fix, tmp_ Q&A made exactly one Pinecone call;
now it makes two. This is a real, measurable latency/cost increase, not a
correctness issue — and it brings tmp_'s cost profile in line with what
pred_ namespaces have always paid (pred_'s ownership check was a DB query
+ validate_session's own Pinecone query, i.e. also two round-trips).
Framed as intentional consistency, not a regression, but worth knowing if
document-Q&A latency is ever profiled.

### 3. F16 incidentally fixes a second, previously-undiscovered latent bug

The original `staging_approve` wrote ALL fields (approval + `pinecone_indexed`)
in one UPDATE, positioned AFTER promotion. If the process crashed between a
successful Pinecone promotion and that single write, the row stayed
`status='pending'` forever even though the vectors were already live in
Pinecone — a second, silent inconsistency beyond the double-submit race
this mission set out to fix. The claim-first restructuring (approval fields
written BEFORE promotion, `pinecone_indexed` written after) closes this as
a side effect: a crash after promotion now leaves `status='approved',
pinecone_indexed=false` — recoverable and inspectable, not silently stuck.
Not a regression; a bonus fix, noted here so it isn't miscredited later.

### 4. F2's key-presence fix closes the same edge case Phoenix Closure's Phase 6 already fixed on the sibling function

The background Genome refresh path (`_run_genome_background`) was hardened
in an earlier mission to check `"greska" in genome` (key presence) instead
of `genome.get("greska")` (truthiness) after Phase 6 adversarial testing
found an exception with an empty `str(exc)` could bypass a truthiness check.
The manual refresh path this mission fixed (F2) had the OLD truthiness
check before this fix — meaning it was ALSO exposed to that exact same
edge case, undiscovered until now. F2's fix uses key-presence from the
start, closing both the primary finding (writing a failed extraction over
good data) and this narrower edge case in one change.

## Standard second-order checklist — all fixes

| Question | Finding |
|---|---|
| Duplicate business logic introduced? | No — every fix reused an existing pattern (F17/F26 reused `if_updated_at`/`emit_durable` idioms already proven elsewhere; F27 reused the exact `aktivni_ids` filter `posalji_podsetnike` already had). |
| New truth source created? | No — F11's `platform_risk_nivo` is explicitly a disclosed reference value, not a new canonical source; F4/F20's new fields are all purely additive disclosure, never consumed as authority elsewhere. |
| Security regression? | No — F1/F5 both *tighten* existing gaps; no fix loosens an existing check. |
| API contract changed in a breaking way? | No — F17's `if_updated_at` is opt-in; F21's new endpoint is additive; F1's ownership check changes only the *failure* path for previously-unverified tmp_ requests (see cost item above). |
| New race introduced? | No — F16 and F17 both *add* concurrency guards; F26's new event emission uses the same durable-outbox idempotency machinery already proven for hearing creation. |
| Performance regression? | Only F1 (see item 2 above) — bounded and intentional. |
| New migration required? | Only F5 (already drafted, not yet applied — see item 1). |
| Stale tests left behind? | None found — every test touching changed behavior was updated with an explicit, behavior-matching assertion; full suite re-run 3 times during Phase 8 (3423 → 3442 passing, 0 failed each time) plus the 2 independent Phase 10 runs below. |
| Weakened validation? | No — F5, F1, F11 all *add* validation (balance guard, ownership check, enum guard) where none existed. |
| Accidental GPT authority? | No — F11 explicitly avoids letting GPT's `risk_breakdown.overall` silently override or get silently overridden by the canonical value; both are shown, disclosed as independent. |
| Frontend/backend divergence? | No — every new backend field (F4, F7, F20) got a matching frontend consumer in the same commit; F21's new `ids` field is consumed by the one function that needed it (`notif_click`). |
