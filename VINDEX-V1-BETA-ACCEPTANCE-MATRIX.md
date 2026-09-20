# VINDEX V1 — Beta Acceptance Matrix

Candidate SHA: `1296cb6988191f5f830174b2f0c650159b70ccac`
Production SHA: `1296cb6988191f5f830174b2f0c650159b70ccac`
Production identity: PROVEN (`/api/version`: `commit=1296cb69...`, `branch=main`, `identity_proven=true`)
Production health: PROVEN (`/health`: HTTP 200, `{"status":"ok","commit":"1296cb6",...}`)
Acceptance timestamp: 2026-09-20T18:00–18:50Z
Requirement sources: (1) no current `VINDEX-V1-EXECUTION-CONTRACT.md` exists on this branch (historical, not ported by design in the mainline re-integration — see prior session record); (2) `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md` (validated Bojan workflow, re-verified against current code, not trusted at face value — it is itself 7 weeks stale relative to this candidate); (3) `TASK8_FINAL_EVIDENCE_DOSSIER.md` (Case Evolution Spine sprint, 2026-09-10 — addresses the Bojan+Miroslav "event → consequence" canon directly, with live production evidence); (4) current production behavior for anything not documented elsewhere. No `B-01…B-13`/`M-01…M-07` requirement-ID scheme exists in the current repo — not assumed, not recreated.
Feature freeze: ACTIVE

**No historical requirement-ID scheme found current in the repo.** IDs below (`A1`, `B2`, …) are this matrix's own, not a resurrection of a prior numbering.

---

## Matrix

| ID | Journey | Requirement | V1 Critical | Status | Severity if failed | Evidence Type | Evidence Reference | Notes |
|---|---|---|---|---|---|---|---|---|
| A1 | Access | Unauthenticated protected access fails | Yes | PROVEN | — | LIVE | `GET /api/predmeti/{id}` no auth header → `401 {"detail":"Unauthorized"}`, this session | |
| A2 | Access | Authenticated user can access own data | Yes | PROVEN | — | LIVE | Same endpoint, valid Bearer token → `200`, this session | |
| A3 | Access | User A cannot read User B matter | Yes | PROVEN | — | DETERMINISTIC_TEST | `tests/test_beta_lockdown_zadaci_predmet_idor.py::test_non_owner_cannot_read_another_firms_case_tasks`; `tests/test_confidentiality_002_tenant.py::test_conf009_tudji_predmet_id_je_odbijen` | |
| A4 | Access | User A cannot mutate User B matter | Yes | PROVEN | — | DETERMINISTIC_TEST | `tests/test_sec001_predmet_ownership.py::test_user_a_cannot_inject_note_into_user_b_predmet`, `::test_founder_status_does_not_bypass_ownership_check` | founder status explicitly proven not to bypass |
| A5 | Access | service-role-only DB surfaces unavailable to anon/authenticated | Yes | PROVEN | — | PRODUCTION_CATALOG | `migrations/133_fix_source_invalidation_rpc_uuid_contract.sql` REVOKE/GRANT; production catalog verified anon=false/authenticated=false/service_role=true prior to this session (accepted per this mission's own authoritative starting state) | |
| A6 | Access | No endpoint trusts caller-supplied ownership over server-side identity | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `routers/evidence.py:432` (`uid = user["user_id"]`, `Depends(require_user)`), `routers/rocista.py:469`, `api.py:6890` — all `Depends(get_current_user)`; RPC WHERE clauses (migration 133) re-enforce server-side | |
| B1 | Client→Matter | Create client | Yes | PROVEN | — | LIVE | `POST /klijenti` → `200`, client `49bfbb3a-23b3-4a5d-8c45-d48312da1949`, this session | |
| B2 | Client→Matter | Create matter | Yes | PROVEN | — | LIVE | `POST /api/predmeti` → `200`, matter `7b564559-629b-4baf-a135-87b960a194d0`, earlier this session | |
| B3 | Client→Matter | Open matter detail | Yes | PROVEN | — | LIVE | `GET /api/predmeti/{id}` → `200`, full detail incl. istorija, this session | |
| B4 | Client→Matter | Matter visible in navigation/workspace | Yes | PROVEN | — | LIVE | `GET /api/predmeti` → `200`, `count=1`, correctly scoped to owner, this session | |
| B5 | Client→Matter | Edit matter metadata without corrupting ownership/state | Yes | PROVEN | — | LIVE | `PATCH /api/predmeti/{id}` → `200`, `updated_at` bumped, `user_id` unchanged, this session | |
| C1 | Document intake | Basic-tier gate is a correct entitlement gate, not a broken workflow | Yes | PROVEN | — | LIVE + SOURCE_CONTRACT | `POST /api/predmeti/{id}/upload` on Basic → `403 "...Professional tarifu ili višu..."`, this session; `migrations/064_feature_registry.sql:107`, `071_business_groups.sql:105-106` seed `predmet_upload_ai`/`document_analysis` as `professional` tier | Distinguishes EXPECTED_ENTITLEMENT_GATE from BROKEN_WORKFLOW correctly |
| C2 | Document intake | Upload accepted / processing terminal state is truthful, for an entitled account | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `api.py:5669-5720` (`predmet_upload_auto_analyze`) returns `{session_id, filename, procena}` synchronously — terminal success/failure in the same HTTP response, no async gap to silently vanish into | No Professional-tier account available this session to re-run live; code path unambiguous |
| C3 | Document intake | Delete does not leave confidential vector state retrievable | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `api.py:6883` (`predmet_dokument_obrisi`): `shared/vector_deletion.py::obrisi_vektore_dokumenta` is a hard blocking precondition — any non-success outcome raises `409` **before** the DB row or storage is touched (`api.py:6928-6944`); relational delete only proceeds after vector deletion is confirmed | Fail-closed ordering, read in full this session |
| C4 | Document intake | Deleted document's derived context (AI prompt traces) does not keep leaking | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | Same endpoint also deletes `predmet_istorija` rows tagged `[Auto-analiza]`/`[Metapodaci]` (fixes the historical NS001/FAZA2 leak); `tests/test_ns001_faza2_brisanje_dokumenta.py` | |
| D1 | Manual evidence | Add evidence | Yes | PROVEN | — | LIVE | `POST /api/evidence/predmeti/{id}/dokaz` → `200`, dokaz `4447c7c8-...`, this session | |
| D2 | Manual evidence | Evidence belongs to correct user/matter | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | Ownership predicate inside migration 133's `invalidate_dokaz_and_emit_event` WHERE clause + route-level `user_id` filter | |
| D3 | Manual evidence | Case Evolution receives the fact | Yes | PROVEN | — | LIVE (prior session) | `TASK8_FINAL_EVIDENCE_DOSSIER.md`: `add_dokaz` → `NEW_EVIDENCE_REGISTERED` → `case_actions` 0→2 within 5s, correlation-ID matched; code path unchanged since (migration 133 only touched `delete_dokaz`) | |
| D4 | Manual evidence | Delete/invalidation works | Yes | PROVEN | — | LIVE | `DELETE /api/evidence/predmeti/{id}/dokaz/{id}` → `200 {"ok":true}`, this session, post migration-133 fix | This is the exact defect this Wave's own fix closed |
| D5 | Manual evidence | Deleted evidence cannot remain silently authoritative downstream | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | Atomic soft-delete + `SourceInvalidated` event in one transaction (migration 133); `SOURCE_INVALIDATED` wired in `CONSEQUENCE_REGISTRY` → `refresh_case_actions` (Wave 2, unchanged) | |
| E1 | Hearing lifecycle | Create hearing | Yes | PROVEN | — | LIVE | `POST /api/rocista` → `200`, hearing `45255654-...`, this session | |
| E2 | Hearing lifecycle | Reschedule | Yes | PROVEN | — | LIVE | `PATCH /api/rocista/{id}` → `200`, `datum` changed, this session | |
| E3 | Hearing lifecycle | Action updates without duplicate open work | Yes | PROVEN | — | LIVE | Same `case_actions` row (`816753be-...`) updated in place across reschedule; `open_hearing`-equivalent count stayed 1 across 4 polls, this session | |
| E4 | Hearing lifecycle | Delete invalidates downstream hearing-derived work | Yes | PROVEN | — | PRODUCTION_CATALOG (not re-derived this pass) | Per this mission's own accepted starting state ("hearing invalidation: production RPC/runtime PASS... hearing action closure PASS"); code unchanged since `e496120d` — anti-loop rule applies, not re-tested | |
| E5 | Hearing lifecycle | Document-less matter does not dead-letter | Yes | PROVEN | — | LIVE | Hearing scheduled on a 0-document matter, async worker processed within ~5s (well under 180s bound), no `DEAD_LETTER` marker, this session | |
| F1 | Deadlines | Outbound/notification tier: unconfirmed AI deadline cannot trigger a reminder | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `shared/rokovi.py:513-575` (`sme_pokrenuti_obavezu`), sole authorization is explicit `potvrda`; wired into all 7 outbound call sites (`email_notif.py`, `sms.py`, `viber.py`, `whatsapp_notif.py`, `notifications.py`, `morning_briefing.py`, `integrations.py`) | Two prior failed gating attempts (FAZA 6.2/6.4) documented in-file; current design deliberately rejects `izvor`/`akter`/`vaznost` as authorization |
| F2 | Deadlines | LLM instructed never to invent a deadline | Yes | PROVEN | — | SOURCE_CONTRACT | `routers/intake.py:70` (`"NE izmišljaj datume"`); `/api/intake/ekstrakcija` is proposal-only, no DB write | |
| F3 | Deadlines | Document-extracted deadline requires confidence gate before becoming operational | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `shared/intake_documents.py:23` (`AUTO_ACCEPT_THRESHOLD = 0.90`); below threshold explicitly withheld (`routers/smart_intake.py:1343-1347`) | |
| F4 | Deadlines | Dashboard display distinguishes AI-autonomous (never human-seen) deadlines from confirmed ones, and only CONFIRMED deadlines are treated as operational | Yes | PROVEN | — | LIVE + DETERMINISTIC_TEST | Two-part fix. Part 1 (commit `82e869b7`): `izvor` (provenance) transport fixed through `shared/rokovi.py` -> `routers/dashboard.py`. Part 2, final closure (commit `1296cb69`): transport alone did not authorize anything — `routers/dashboard.py` now resolves human decision state (`shared/rok_potvrda.py`, the same `odluke()`/`stanje_roka()` already live at `/api/rokovi/kandidati`) once per request, excludes REJECTED from `rokovi_7_dana` entirely, and restricts `hitni_rokovi` to CONFIRMED rows; `static/vindex.js::_kcPanelAktivni`'s "Rok: N dana" text now requires `stanje_odluke==='CONFIRMED'`. Production canary (synthetic Smart Intake upload, matter `2bd1937e-ab13-4f93-ac95-83271681e592`, rok `fa37cea0-6c5c-4b2f-bdee-2728ef0500c3`, `izvor=AI_AUTONOMOUS`): before confirmation — API showed `stanje_odluke=UNCONFIRMED`, absent from `hitni_rokovi` despite a 2-day-out date within the 48h window; deployed `static/vindex.js` verified byte-identical (CRLF-normalized diff) to the committed fix, containing the exact `stanje_odluke==='CONFIRMED'` filter — `POST /api/rokovi/{id}/potvrdi` → `stanje_odluke=CONFIRMED`, reload → row entered `hitni_rokovi` — `POST /api/rokovi/{id}/odbij` → `stanje_odluke=REJECTED`, reload → absent from both `rokovi_7_dana` and `hitni_rokovi`. Full UNCONFIRMED→CONFIRMED→REJECTED transition proven live. 12 new focused tests (mutation-tested) + 635/635 full consumer-sweep regression. Canary matters closed via the normal product path. | Closed this session, production-verified |
| G1 | AI matter context | Correct matter/document/evidence context reaches the AI | Yes | PROVEN | — | LIVE (prior session) | `TASK8_FINAL_EVIDENCE_DOSSIER.md`: `predmet_dokazi.tvrdnja` wired into `/api/pitanje`'s context pipeline; live-proven a distinctive fact became answerable | |
| G2 | AI matter context | No cross-user/cross-firm RAG leakage | Yes | PROVEN | — | DETERMINISTIC_TEST | `tests/test_confidentiality_003_rag_acl.py` — 15 tests incl. `test_f01_druga_kancelarija_nikad_ne_curi`, `test_f01_filter_nikad_nije_prazan_dict` (fail-closed, filter never empty), `test_acl_pad_predmeta_dize_izuzetak_a_ne_tiho_prazno` (ACL failure raises, doesn't silently narrow to nothing) | |
| G3 | AI matter context | Stale/deleted source does not remain silently authoritative to the AI | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | Wave 2 `SOURCE_INVALIDATED` consequence chain (unchanged by this session's fixes except the RPC contract itself, which is what makes invalidation actually fire now) | |
| G4 | AI matter context | Missing context represented honestly, not fabricated | Yes | PROVEN | — | LIVE (prior session) | `TASK8_FINAL_EVIDENCE_DOSSIER.md`: pre-fix, AI correctly said "not defined in the provided sources" rather than fabricating | |
| H1 | Legal research | Sources returned actually exist | Yes | PROVEN | — | SOURCE_CONTRACT | `app/services/retrieve.py:891-918` — real Pinecone `index.query()`, citations built only from real match metadata | |
| H2 | Legal research | Citation traceable to displayed source | Yes | PROVEN | — | DETERMINISTIC_TEST | `main.py:734-811` (`_proveri_halucinaciju`) — every cited `Član N` verified present in actual retrieved context, else blocked; `tests/test_hallucination_guard.py` (20), `tests/test_guard_v2.py` (8) | Applied to every string field of the parsed LLM response, not a fixed subset (BLACKSWAN-AI-004) |
| H3 | Legal research | Missing/unverified authority distinguished from verified | Yes | PROVEN | — | SOURCE_CONTRACT | `retrieve.py:774-780` (HIGH/MEDIUM/LOW confidence); honest "not found" answers explicitly exempted from the hallucination guard (`main.py:749-757`) | |
| H4 | Legal research | No fabricated legal source presented as authoritative | Yes | PROVEN | — | DETERMINISTIC_TEST | Same as H2; case-law citations get identical treatment (`main.py:3212-3224`) | |
| H5 | Legal research | Source/retrieval failure surfaced honestly | Yes | PROVEN | — | SOURCE_CONTRACT | `retrieve.py:1017-1032` `RetrievalUnavailable` — explicitly fixes a prior bug where a Pinecone outage was presented as a legal fact; every failure logged to `security_events` | |
| I1 | Case actions/workspace | Actionable state matches canonical matter state | Yes | PROVEN | — | LIVE | `GET /api/case-actions/predmeti/{id}` matched real matter state repeatedly, this session | |
| I2 | Case actions/workspace | Stale source removal reconciles actions | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `tests/test_wave2_2d_source_invalidation.py` (unchanged code, migration 133 only fixed the RPC's SQL types) | |
| I3 | Case actions/workspace | Duplicate actionable work not created by retry/reschedule | Yes | PROVEN | — | LIVE | Hearing reschedule this session: same action id, `open_hearing_actions` stayed 1 | |
| I4 | Case actions/workspace | Closed/terminal matter cannot retain/resurrect open work | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `tests/test_wave2_2b_terminal_matter_invariant.py` (8 tests, unchanged code) | |
| I5 | Case actions/workspace | Workspace does not silently hide critical processing failure | Yes | PROVEN | — | DEPLOY_EQUIVALENCE + PRODUCTION_CATALOG | `migrations/130_events_outbox_dead_letter_metrics.sql` (dead-letter view, live in production) | |
| J1 | Drafting | Feature is real, current V1 scope | No | PROVEN | — | SOURCE_CONTRACT | `routers/drafting.py:636,876,731,786`, Professional-tier gated | Not blocking either way — informational |
| J2 | Drafting | Ownership/context boundary enforced before generation | No | PROVEN | — | DEPLOY_EQUIVALENCE | `routers/drafting.py:648-660` — ownership check moved BEFORE generation (fixes historical S6C-1 forged-audit-trail bug) | |
| J3 | Drafting | Output clearly marked as a draft, not authoritative filed content | No | **FAIL** | P3 | DEPLOY_EQUIVALENCE | No explicit `is_draft`/disclaimer text found in response payload — only the Serbian function name ("nacrt") signals it | Non-blocking: no confidentiality/correctness risk, UX-labeling gap only |
| K1 | Terminal lifecycle | Terminal status has one coherent meaning | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `shared/constants.py::TERMINALNI_STATUSI_PREDMETA`, used consistently across `routers/case_actions.py`, `routers/dashboard.py` | |
| K2 | Terminal lifecycle | Canonical reconciliation closes open system work | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `tests/test_wave2_2b_terminal_matter_invariant.py::test_zatvori_predmet_reconciles_via_canonical_function_not_direct_write` | |
| K3 | Terminal lifecycle | Delayed/replayed events cannot reopen a closed matter | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `::test_race_delayed_event_after_closure_creates_no_open_action`, `::test_replay_after_closure_does_not_resurrect_action` | |
| K4 | Terminal lifecycle | Notifications suppressed for terminal-matter work | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `::test_race_delayed_event_after_closure_fires_no_notification` | |
| K5 | Terminal lifecycle | Reopening behavior not silently invented | Yes | NOT_APPLICABLE | — | SOURCE_CONTRACT | No "reopen matter" endpoint exists anywhere in the current codebase (grepped `api.py`/`routers/`) — nothing to silently invent | |
| L1 | Delete/Confidentiality | Evidence: soft-delete + domain invalidation honored | Yes | PROVEN | — | LIVE | D4/D5 above | |
| L2 | Delete/Confidentiality | Document: vector delete fail-closed + relational + domain invalidation honored | Yes | PROVEN | — | DEPLOY_EQUIVALENCE + PRODUCTION_CATALOG | C3 above; RPC-level per mission's accepted starting state | |
| L3 | Delete/Confidentiality | Hearing: relational delete + domain invalidation honored | Yes | PROVEN | — | PRODUCTION_CATALOG (not re-derived) | Per accepted starting state; code unchanged | |
| M1 | History/Audit | Canonical transitions have traceable history | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `shared/audit_immutable.py::log_action`, `case_action_refreshed` in `AUDITABLE_ACTIONS` | |
| M2 | History/Audit | Audit lineage records concrete object references, not just counts | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | `tests/test_wave2_2e_deterministic_lineage.py::test_multi_event_lineage_addressable_without_timestamp_guessing` | |
| M3 | History/Audit | Dead-letter distinguishable from success | Yes | PROVEN | — | DEPLOY_EQUIVALENCE + PRODUCTION_CATALOG | `migrations/130_events_outbox_dead_letter_metrics.sql`, live in production | |
| M4 | History/Audit | Application failure does not silently look like empty success | Yes | PROVEN | — | DEPLOY_EQUIVALENCE | Migration-133 RPCs: either both mutation+event commit, or `invalidated=false`/404 — no partial/false-success state | |
| M5 | History/Audit | Immutable/audit records remain append-only | Yes | PROVEN | — | SOURCE_CONTRACT | `shared/audit_immutable.py` hash-chains each row (`entry_hash`/`prev_hash`, `_get_last_hash`) | |

---

## Summary

**OPEN P0:**
0

**OPEN P1:**
0

**BLOCKED V1-CRITICAL:**
0

**SOURCE_AMBIGUOUS V1-CRITICAL:**
0

**NON-BLOCKING P2/P3:**
1 — J3 (drafting output lacks an explicit "this is a draft" marker; UX-labeling only)

---

## WAVE 3 — CLOSED
## V1 TECHNICAL BETA ACCEPTANCE — PASS
## READY FOR CONTROLLED BETA
