# Storage Security Report — Program Lambda, Certification 002

## Scope

Every `.storage.from_(`, `create_signed_url`, `.upload(`, `.download(`, `.remove(` call site in the repo —
confirmed via full-repo grep to be a complete set of 3 buckets (`intake-dokumenti`, `klijent-dokumenti`,
`portal-uploads`) and 21 distinct upload/download/preview/delete/signed-URL code paths across
`api.py`, `klijenti/router.py`, `routers/smart_intake.py`, `routers/client_portal.py`,
`shared/intake_worker.py`, `routers/cross_doc.py`, `routers/drafting.py`.

## Result: 19 SAFE, 2 NEEDS-DEEPER-LOOK, **0 VULNERABLE**

Despite adversarial effort against every real upload/download/preview/delete/signed-URL path, no exploitable
Storage ownership bypass was found. Every one of the 3 real buckets consistently combines an unguessable
(`uuid4`) storage key with an explicit DB-row ownership check before any signed URL is minted or bytes are
streamed — the correct pattern given that Storage RLS cannot be relied on (service-role key bypasses it, and
no bucket policy exists in the repo at all, see `RLS_CERTIFICATION.md`).

| Path | What | Ownership check | Verdict |
|---|---|---|---|
| `api.py:4082` upload | Encrypt+upload original to `intake-dokumenti`, key `{uid}/{predmet_id}/{uuid4}{suffix}` | `predmeti.eq(id,..).eq(user_id,..)` before upload | SAFE |
| `api.py:4325` orphan-cleanup delete | Removes blob just uploaded in same request on downstream failure | Path is a local variable, never attacker-supplied | SAFE |
| `api.py:4892` preview | Returns extracted text, not raw blob | `.eq(id,dok_id).eq(predmet_id,..).eq(user_id,..)` | SAFE |
| `klijenti/router.py:706` upload | To `klijent-dokumenti`, key = unguessable encrypted-blob uuid4 | `_verify_owns_klijent()` | SAFE |
| `klijenti/router.py:806` list | Metadata only, no storage_key leaked | `_verify_owns_klijent()` | SAFE |
| `klijenti/router.py:825` download | Decrypt+stream, watermark, audit log | `_verify_owns_klijent()` + `.eq(id,..).eq(klijent_id,..)` | SAFE (note: no delete endpoint exists for this table at all — zero attack surface, but also no purge capability) |
| `smart_intake.py:108` upload | To `intake-dokumenti`, key `{user_id}/{uuid4}` | Per-user-namespaced + unguessable | SAFE |
| `smart_intake.py:257` job status | No blob served | `.eq(id,job_id).eq(uploaded_by,..)` | SAFE |
| `shared/intake_worker.py:464` download+decrypt | Background OCR/classification | Not attacker-reachable — `storage_path` comes from the queue job row, never an HTTP request | SAFE |
| `smart_intake.py:501` correct_entity | — | **Confirmed VULNERABLE by a sibling fork this same sprint, fixed, re-verified present** (see `IDOR_MATRIX.md` #23) | SAFE (post-fix) |
| `client_portal.py:203` mint token | HMAC-SHA256, binds `predmet_id:user_id:exp` | Predmet ownership (or saradnik "vodenje" role) verified before minting | SAFE |
| `client_portal.py:364` client view | — | `predmet_id`/`advokat_uid` parsed exclusively from the verified token, never from request params | SAFE — client cannot substitute a foreign predmet_id |
| `client_portal.py:493` client upload | To `portal-uploads`, key `{advokat_uid}/{predmet_id}/{uuid4}_{name}` | Same token-only binding | SAFE |
| `client_portal.py:637` list uploads + signed URL | 3600s TTL | Predmet ownership + `.eq(advokat_user_id,..)`; URL generated fresh per request, never cached | SAFE |
| `client_portal.py:706` mark reviewed | — | `.eq(id,..).eq(advokat_user_id,..)` | SAFE |
| `client_portal.py:729` delete upload | Blob then DB row | `.eq(advokat_user_id,..)`; storage key is unique-per-upload, no shared-blob risk | SAFE |
| `client_portal.py:778` client confirms review | — | Token-derived predmet_id only | SAFE |
| `routers/dokument.py` (upload/pitanje/analiza/rokovi/klasifikuj-sesija) | Ephemeral Pinecone `tmp_`/`pred_` namespace, `uuid4().hex` session_id, no DB row | **No ownership check exists at all** — isolation relies 100% on UUID unguessability | NEEDS-DEEPER-LOOK — same as pre-existing tracked `SEC-039` |
| `routers/intake.py:230` CRM wizard doc-link | Links a client-supplied `session_id` to a new predmet | No verification the session_id was created by this same user (same root cause as above) | NEEDS-DEEPER-LOOK, low severity, same root cause |
| `routers/cross_doc.py` compare-docs | Fetches by `dokument_ids` | `.eq(predmet_id,..).eq(user_id,..)` combined filter | SAFE |
| `routers/drafting.py:313` | Writes a `session/{id}` label, not a real bucket path | No storage exposure | N/A |

## Cross-cutting checks (mission's 5 explicit points)

1. **Predictable paths** — none found. Every real bucket key is `uuid4`-based, most also namespaced by
   `user_id`/`advokat_uid`. No sequential ids or raw filenames used anywhere as a storage key.
2. **"Know the path = get the file"** — not found for any of the 3 real buckets. Every download/preview path
   re-verifies ownership via a scoped DB lookup before generating a signed URL or streaming bytes, even
   though the service-role key would let the code skip that check and still succeed at the storage layer.
3. **Delete/overwrite cross-row blob risk** — none. Every storage key is unique per upload, so no two DB rows
   ever reference the same blob.
4. **Signed URL expiry/replay** — only one signed-URL path exists (`client_portal.py`, 3600s TTL), never
   cached or reused across requests/users, regenerated fresh every call. The platform has no case-delete
   endpoint (only close/archive), so the "URL survives case deletion" scenario in the mission brief is
   structurally not reachable today.
5. **`client_portal.py` token scope** — verified directly: `predmet_id`/`advokat_uid` are parsed exclusively
   from the HMAC-verified token in every client-facing endpoint. None accept `predmet_id` as a separate
   request parameter that could override the token's own value.

## Found, not an ownership bug: GDPR orphan-blob gap

Right-to-erasure/archival flows (`routers/gdpr.py`, `routers/data_export.py`, `klijenti/router.py`'s
retention/archive logic) never call `.storage.remove()` — encrypted originals persist in all 3 buckets
forever after a DB row is deleted/archived. Nobody else gets access as a result (not an ownership bug), but
it is a real compliance gap for a legal-data product. Worth a ticket, tracked separately from this
certification's own scope.
