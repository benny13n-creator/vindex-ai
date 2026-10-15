# NS3-C independent adversarial review (review-c) — commit 6e3d64a3 (base da345f26)

VERDICT: GO WITH NOTES. I found no path that serves the ZIP without a proven audit insert.

Worktree: C:/vindex-ns3/review-c (detached at 6e3d64a3, kept). routers/data_export.py was restored byte-for-byte after the mutations (sha256 matched).
Tests: the 6 export-related files (c1_export_stages, n04, n05_tenant_negative, ns2b, ns3, sprint4) gave 109 passed (`-p no:randomly`, OPENAI_API_KEY=x). This matches the author's count.
My mutations: 12 defined, 10 applied, 10 killed. Two did not apply (M6, the LF variant of the email mutation, because the file uses CRLF; and M10). The 10 applied:
  - any truthy result counts as success: killed
  - `is not None` counts as success: killed
  - the 503 raise is removed: killed
  - a timeout counts as success: killed
  - the audit_unproven record is skipped: killed
  - email is put back into the success metadata: killed
  - wait_for gets no timeout: killed
  - an exception counts as success: killed
  - delivery is reported as "delivered": killed
  - the error message lies ("je poslat"): killed

## Findings (by severity)
1. MEDIUM, UNKNOWN (precondition for availability). Exports now depend on the audit sink actually working in production. The fallback for missing correlation_id and the UNIQUE(prev_hash) contention with 5 retries are both on the critical path. If audit_immutable inserts fail in production today, every export now returns 503, where before they succeeded. Before merging, run one aggregate count of recent `audit_immutable` rows with action in (data_export, data_export_failed) to check that the sink works.
2. LOW-MED, INFERRED (from code; no test exists). On timeout the export is refused but the audit row can still be written later. data_export.py:185-186 and :266-270: `asyncio.to_thread` keeps running after `wait_for` gives up, so `_build_and_insert` can still write a `data_export` row (stage=archive_generated). The user got 503 and the ZIP was discarded. On timeout the code deliberately skips the `data_export_failed` attempt, so nothing in the log explains that the export was refused. The record does not claim delivery ("not_verified_by_server"), so it is truthful but misleading. No duplicate row results: a retry happens only on 23505, which means the earlier insert did not land. Same class of issue: if the INSERT commits but the response is lost (e.g. ConnectionError), the result is 503 plus both a data_export row and a data_export_failed row (reason=ConnectionError).
3. LOW, INFERRED. Timing and the leaked thread. Worst case for audit: 15 s for success, then up to 15 s for the audit_unproven record, about 30 s in total. Add the data fetch on top: `_fetch` calls `.execute()` synchronously inside an async function, which blocks the event loop (pre-existing). The total stays under gunicorn `timeout = 120` (gunicorn.conf.py:13) unless the fetch itself is very slow. After a timeout, the leaked thread is limited by postgrest/httpx timeouts, up to 5×(select+insert). /api/export/complete has no rate limiter (unlike /api/gdpr/export at 5/minute), so repeated clicks can pile up threads in the to_thread pool. This is pre-existing and residual.
4. LOW, PROVEN. The user never sees the 503 detail text. static/vindex.js:830 throws 'HTTP 503', and _friendlyErr maps it to a generic "Radnja nije uspela..."; v2/features/kancelarija/view.js:187 shows "Izvoz nije uspeo. Pokušajte ponovo." Both messages are truthful and promise no success, but the Serbian "audit nije potvrđen" message is invisible to users. The founder's contract is still met.
5. LOW, RESIDUAL, out of scope. `GET /api/gdpr/export` (routers/gdpr.py:153-197) is registered (api.py:766). Its docstring says "Vraća sve podatke korisnika" and it returns JSON (profile, predmeti, billing, the last 200 usage_events) with NO audit at all. It is a narrower duplicate, not the ZIP and not titled "complete export", and has no UI caller (vindex.js:856). It still claims portability of all data with no audit trail. Recommend a follow-up: retire it or route it through the same gate.
6. LOW, RESIDUAL, PROVEN. Exception text reaches a log. shared/audit_immutable.py:296 logs `%s` of the exception at warning level (str(e) from PostgREST). The new metadata has no PII (format/stage/delivery; reason is a class name, "timeout" or "not_persisted"), so the risk is low. The router's own log lines contain only the action and the reason (data_export.py:195), and the tests assert that the email is absent.

## Questions answered
(1) Fully materialized before the audit: PROVEN. The ZipFile `with` block closes at :220-228 and the audit call is at :258. Any failed audit leads to `buf.close()` and a raise. StreamingResponse iterates an in-memory BytesIO, so nothing can fail after the check apart from transport. No other return path exists.
(2) A truthy return implies an INSERT happened: PROVEN by code and schema.
  - `_build_and_insert` returns `result.data[0]["id"]`.
  - id is a UUID PK (migrations/043:17), so it is a JSON string and the `isinstance(str)` check is correct, not over-strict.
  - No `returning=minimal` exists anywhere in the repo.
  - The client uses the service key (api.py:160-171).
  - Empty data gives None and then 503 (test_postgrest_bez_vracenog_reda).
  - data_export and data_export_failed are both in AUDITABLE_ACTIONS (audit_immutable.py:93,97). Removing data_export from it gives 503 (tested).
(3) See findings 2 and 3. The user sees a generic error after up to about 30 s of audit wait.
(4) Only /api/export/complete serves the complete ZIP. Callers are the legacy vindex.js:827 and V2 kancelarija/view.js:181, and both go through the same route. /api/gdpr/export: see finding 5. The other "export" routes (docx, pdf, ics, csv, hearing brief) are per-object and not full-data exports.
(5) Isolation and unauthenticated access: PROVEN by test.
  - Depends(get_current_user) returns 401 with no data read and no audit.
  - Every table is filtered with `.eq("user_id", uid)` from the JWT.
  - The n05 tenant-negative tests pass.
(6) PII: there is no email in the new success or failure metadata (mutation M6b killed). The README inside the ZIP still contains the user's own email, which is expected.
(7) Mock fidelity: OK. The router imports `log_action` inside the function at call time, so `patch("shared.audit_immutable.log_action")` takes effect. Several tests run the REAL `log_action` with `_build_and_insert` or `api._get_supa` faked (timeout with a hanging thread, ConnectionError, an empty postgrest result, AUDITABLE_ACTIONS removal), so the mocks are not hollow.

Nothing was committed or pushed. Mutation script: scratchpad/ns3/export-fc/mut_c.py
