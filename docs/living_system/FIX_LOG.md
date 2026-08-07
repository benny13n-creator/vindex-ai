# Operation Living System — Fix Log

7 fixes, each following the mission's own mandatory lifecycle: DISCOVER → REPRODUCE →
ROOT CAUSE → FIX → NEW REGRESSION TEST → RERUN THE ORIGINAL SCENARIO → confirmed closed before
moving to the next. All tests in `tests/test_living_system_fixes.py` (16 tests total, 9 covering
these 7 fixes — Fix L3 has 2 tests, one per endpoint). Every fix reuses an existing canonical
function, constant, or DB constraint — no new algorithm was invented.

---

### Fix L1 — Copilot's `verovatnoca_uspeha` uncapped by canonical readiness

- **Found by**: Wave 1, "AI reasoning chain" team.
- **Reproduction**: a case with an open `case_actions` row at `prioritet="critical"` (canonical
  `readiness=CRITICAL_GAP`, capped at 50 by `shared/case_readiness.py::CAP_BY_READINESS`
  everywhere else) could still show Copilot's `verovatnoca_uspeha` at Genome's own uncapped
  `snaga_predmeta_procent` — e.g. 82% next to Court Predictor's structurally-capped 50% for the
  identical case, same session.
- **Root cause**: `routers/copilot.py::_handle_analiza_predmeta` never imported or applied
  `CAP_BY_READINESS`, unlike its 3 sibling success-probability fields in `digital_twin.py`/
  `court_predictor.py`/`hearing_cc.py`.
- **Fix**: `routers/copilot.py` — after computing `_verovatnoca_uspeha` from Genome, reuses the
  already-fetched `_oa_r` (case_actions rows) to call `compute_case_readiness()` and applies
  `CAP_BY_READINESS`. No new query.
- **Tests**: `test_copilot_verovatnoca_uspeha_capped_by_canonical_readiness`,
  `test_copilot_verovatnoca_uspeha_uncapped_when_readiness_clean`.
- **Rerun proof**: capped case now returns exactly 50 (not 85); clean-readiness case still
  returns 85 uncapped — the cap only fires when it should.

---

### Fix L2 — Email cron reminders fire for archived/closed cases

- **Found by**: Wave 3, "Portfolio Scale" team. Rated CRITICAL.
- **Reproduction**: a deadline belonging to an archived/closed case was emailed to the lawyer
  exactly like an active one — an unsolicited, proactive push to the inbox, not a dashboard the
  lawyer chooses to open.
- **Root cause**: `routers/email_notif.py::posalji_podsetnike`'s `predmet_hronologija` query
  filtered only by `user_id`/`vaznost`/`datum_iso` — never joined or filtered against
  `predmeti.status`.
- **Fix**: fetch the user's active `predmet_id`s once per user (same 3-value exclusion set
  `routers/dashboard.py` already uses: `zatvoren`/`arhiviran`/`odbijen`), filter the deadline rows
  against that set before sending.
- **Test**: `test_email_reminder_skips_deadline_on_archived_case`, plus fixture updates to 3
  pre-existing tests (`test_lz001_reminder_vocabulary.py`) that now correctly mock the new query.
- **Rerun proof**: an archived case's deadline row no longer triggers `_smtp_send`; `poslato==0`.

---

### Fix L3 — Billing entry update/delete TOCTOU on `obracunato`

- **Found by**: Wave 5, Billing Red Team. Rated HIGH.
- **Reproduction**: `PATCH`/`DELETE /billing/entries/{id}` read `obracunato` in one query and
  acted in a separate one — a concurrent `faktura_create()` could mark the entry invoiced in
  between, and the edit/delete would still succeed, silently corrupting an amount already frozen
  into an invoice total (and, for delete, vanishing from `billing_entries` while the invoice's
  frozen total still counted it).
- **Root cause**: the immutability check and the write were 2 separate round trips with no
  atomic guard on the write itself — `faktura_create()`'s own conflicting update already uses
  `.eq("obracunato", False)` as its race-breaker; this pattern was never applied to its two
  sibling endpoints.
- **Fix**: both `billing_entry_update` and `billing_entry_delete` now add
  `.eq("obracunato", False)` to the actual `UPDATE`/`DELETE` call, and raise `409` if 0 rows
  matched (meaning a concurrent invoice won the race).
- **Tests**: `test_billing_entry_update_rejects_when_invoiced_between_read_and_write`,
  `test_billing_entry_delete_rejects_when_invoiced_between_read_and_write`.
- **Rerun proof**: with the pre-check read simulated as "not yet invoiced" but the actual write
  matching zero rows (simulating the race), both endpoints now raise `409` instead of silently
  succeeding.

---

### Fix L4 — Copilot deadline extraction's `vaznost` vocabulary mismatch

- **Found by**: Wave 5, Copilot Red Team. Rated HIGH.
- **Reproduction**: `_handle_akcija_rok`'s GPT prompt asked for `"kritičan|bitan|normalan"`, but
  `predmet_hronologija.vaznost`'s real DB `CHECK` constraint only allows
  `('kritičan','važan','informativan')`. 2 of the 3 possible GPT outputs — and the code's own
  literal fallback (`"bitan"`) — always violated the constraint and threw on insert. This was a
  guaranteed, not rare, failure for any deadline not phrased as critical.
- **Root cause**: Copilot independently invented a 3rd deadline-importance vocabulary that was
  never reconciled against the schema (contrast `api.py`'s own extraction prompt, which correctly
  uses the real 3-value enum).
- **Fix**: prompt now asks for the real vocabulary; the insert additionally enum-validates the
  result (fail-safe to `"informativan"`, the conservative bucket) in case GPT still drifts.
- **Test**: `test_akcija_rok_normalizes_out_of_schema_vaznost_before_insert` (poisoned GPT
  response using the old vocabulary; asserts the DB write is still schema-valid).
- **Rerun proof**: a poisoned `"bitan"` response no longer reaches the insert unmodified;
  `insert_calls[0]["vaznost"]` is always one of the 3 valid values.

---

### Fix L5 — Client Portal collaborator-generated tokens use the wrong `user_id`

- **Found by**: Wave 5, Client Portal Red Team. Rated HIGH.
- **Reproduction**: a collaborator (role `"vodenje"`, not the case owner) generating a client
  portal link had the token and DB row built with their own `uid`, not the real owner's — the
  token was HMAC-valid but the case lookup (keyed by the real owner's `user_id`) always 404'd for
  the client. The endpoint still reported `ok:True` and, if an email was given, actually emailed
  the client a link that would never work. The real owner's own token-list/revoke endpoints
  (scoped to their own `user_id`) never saw or could revoke it.
- **Root cause**: the collaborator-ownership-fallback branch resolved `owner_uid` but never used
  it for the token payload or the DB insert — both kept using the original `uid`.
- **Fix**: `owner_uid` (defaulting to `uid` on the primary ownership path) is now used
  consistently for both `_generiši_token(...)` and the `client_portal_tokens` insert.
- **Test**: `test_collaborator_generated_token_uses_real_owner_uid` — asserts the inserted row's
  `user_id` is the owner, and that the generated token verifies back to the owner's `user_id`.
- **Rerun proof**: a collaborator-generated token now verifies to `owner_uid`, matching what
  `client_portal_view`'s lookup actually queries against.

---

### Fix L6 — Genome frontend discards a real save-failure signal

- **Found by**: Wave 5, Genome Red Team. Rated HIGH.
- **Reproduction**: when a Genome re-extraction succeeds but the subsequent DB write fails, the
  backend already (correctly, per a prior mission's fix) returns the old genome with
  `case_dna_persisted:false` and an explanatory `poruka`. The frontend's only caller
  (`_voice_refresh_case_dna`) never read either field — it only checked `dna.greska` (a
  *different* failure mode) — so a silently-failed save still showed the green "Procena ažurirana"
  success toast built from the unchanged old genome.
- **Root cause**: the frontend's success/failure branching was incomplete relative to the
  backend's own documented failure signal.
- **Fix**: `static/vindex.js::_voice_refresh_case_dna` now checks
  `data.case_dna_persisted === false` immediately after the existing `dna.greska` check, showing
  an error toast with the backend's own `poruka` instead of the success toast.
- **Test**: `test_genome_refresh_toast_checks_case_dna_persisted_flag` (structural — asserts the
  check exists and runs before the success-toast code path).
- **Rerun proof**: the failure-signal check is confirmed present and correctly ordered before the
  success toast in the compiled frontend bundle.

---

### Fix L7 — Command Center leaks archived-case hearings/deadlines onto the home tab

- **Found by**: Wave 3, "Portfolio Scale" team. Rated HIGH.
- **Reproduction**: `routers/dashboard.py::command_center`'s "today's hearings"/"next 7
  days"/"<48h urgent" panels never filtered by `predmeti.status` — a hearing/deadline belonging
  to an archived/closed case rendered on the app's actual home tab exactly like an active one,
  while the risk computation a few sections later in the SAME endpoint correctly excludes them
  (via the already-computed `aktivni` list).
- **Root cause**: 2 of the endpoint's list-comprehensions (`danasnja_rocista`, `rokovi_7`) were
  never intersected with the `aktivni_ids` set the endpoint already computes for its risk
  section.
- **Fix**: both comprehensions now filter on `r.get("predmet_id") in aktivni_ids`, reusing the
  already-computed active-case set — no new query.
- **Test**: `test_command_center_excludes_hearings_and_deadlines_for_archived_case` (reuses
  `test_dashboard.py`'s own fixture helpers; asserts an archived case's hearing/deadline is
  excluded while an active case's own hearing/deadline is retained).
- **Rerun proof**: with one active and one archived case each carrying a hearing and a deadline
  for the same date, only the active case's entries appear in `danasnja_rocista`/`rokovi_7_dana`.

---

## Regression discipline

Each fix was verified against its own directly-relevant pre-existing test suite before writing
its new test (zero regressions in every case), and the full suite was run twice more after all 7
fixes landed (see `REGRESSION_PROOF.md`). One pre-existing test
(`test_sw_cache_bumped`) was intentionally updated in step with the `static/sw.js` cache-version
bump (`vindex-v98` → `vindex-v99`, required because Fix L6 touched `vindex.js`) — a correct,
expected companion edit, not a silently-tolerated regression.
