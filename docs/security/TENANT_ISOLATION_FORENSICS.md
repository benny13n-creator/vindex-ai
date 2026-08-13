# Tenant Isolation / Authorization Forensics

**Date:** 2026-08-13
**Scope:** Priority #3 — Authorization / Tenant Isolation.
**Method:** Static forensics only. **No production file was modified by this audit.** Every claim below carries `file:line`, verified by reading the code, not by inference from prior reports.
**Sweep coverage:** AST enumeration of every `@app.*` / `@router.*` route in the repo (297 routes accept a resource id), followed by line-by-line handler review of the 85 that showed no direct ownership evidence.

---

## 1. What "tenant" means in this application — proven, not assumed

There is **no `tenant_id` column anywhere in this codebase.** The word "tenant" maps onto **three separate, non-intersecting** concepts, and conflating them is the root cause of two of the three findings below.

### 1.1 Identity

Identity is the Supabase auth UUID, taken from the JWT `sub` claim. There are **two** auth entry points, not one:

| Mechanism | Location | Used by |
|---|---|---|
| `Depends(get_current_user)` | `shared/deps.py:284-329` (returns `{"user_id": sub, "email": …}`) | All `routers/*.py` files |
| `await _require_auth_async(authorization)` | `api.py:3742-3768` → `api.py:3692` (returns an object with `.id` / `.email`) | `api.py` endpoints (manual `Authorization` header parse) |
| `await _auth_from_request(request)` | `klijenti/router.py:1490-1505` (a third, file-local copy; adds `role`/`role_str` via `_enrich_user`) | `klijenti/router.py` only |

All three verify the JWT signature (`shared/deps.py:229-257` `_verify_token`: Supabase SDK first, then HS256/JWKS local verification), so a forged `sub` does not pass. Authentication is sound. **Authorization is where the gaps are.**

### 1.2 Boundary A — the real data boundary: `user_id` (one lawyer)

Every business table carries `user_id` as the owner column: `predmeti` (`supabase_setup.sql:300-311`), `klijenti`, `predmet_beleske`, `predmet_istorija`, `predmet_dokumenti`, `predmet_hronologija`, `billing_entries`, `user_knowledge`, `style_analize`, …

**This is the tenant boundary in practice.** A "tenant" in Vindex is *one individual lawyer's user_id*, not a firm.

### 1.3 Boundary B — the optional, weaker grouping: `kancelarija` (law firm)

- `kancelarije` (`migrations/018_kancelarija.sql:7-13`) — one row per firm, `admin_uid` UNIQUE (`:15`), so **one admin per firm and one firm per admin**.
- `kancelarija_clanovi` (`:29-42`) — membership; `status` normalized to `ACTIVE`/`INVITED`/`SUSPENDED`/`REMOVED` by `migrations/067_seat_lifecycle.sql:35-53`.
- Canonical resolver: `shared/kancelarija_utils.py:19-42` `get_kancelarija_id(supa, uid)` — admin row first, then ACTIVE member row, else `None` (solo lawyer).
- **A firm is NOT a data boundary on cases.** `predmeti` has no `kancelarija_id`. Firm-wide visibility is *synthesized at read time* by expanding member `user_id`s: `routers/kancelarija.py:689-694` does `.in_("user_id", clan_uids)`.
- Only a handful of tables are natively firm-scoped: `zadaci` (`migrations/045_firm_intelligence.sql:112-115`), `memory_entries`, `workflow_templates`.
- **Anyone can self-service create a firm and become its admin** — `POST /api/kancelarija/kreiraj` (`routers/kancelarija.py:216-243`), the only guards being "you are not already an admin" (`:227`) and "you are not already a member" (`:230`). This primitive already caused one confirmed privilege-escalation bug (`routers/zadaci.py:388-397`, fixed by Lambda Certification 002).

### 1.4 Boundary C — a **global, firm-less** role table (this is the CONF-008 root cause)

`user_roles` (`migrations/002_klijenti_crm.sql:10-17`):

```sql
CREATE TABLE IF NOT EXISTS user_roles (
    user_id  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    rola     TEXT NOT NULL DEFAULT 'advokat' CHECK (rola IN ('sekretarica','pripravnik','advokat','partner')),
    dodelio  UUID REFERENCES auth.users(id),
    ...
);
```

**There is no `kancelarija_id` column.** `rola` is a *platform-global* attribute of a user. It drives field-level masking and action gating in the klijenti CRM only (`klijenti/permissions.py:86-113`: `ROLE_FIELD_ACCESS`, `ACTION_MIN_ROLE`).

This is a **completely separate role system** from `kancelarija_clanovi.uloga` (`admin`/`partner`/`saradnik`/`citanje`, `migrations/018_kancelarija.sql:35-36`), which *is* firm-scoped. The two never intersect anywhere in the code. The word "partner" means two different things depending on which table you read.

### 1.5 The enforcement layer is Python, not RLS

`shared/deps.py:93` builds the Supabase client with `SUPABASE_SERVICE_KEY` → **service_role → RLS is bypassed on every API path.** Every `CREATE POLICY` in `supabase_setup.sql` / `migrations/*.sql` protects only the browser's direct anon-key access (`static/vindex.js:236,242`), never a FastAPI route.

**Consequence:** the sole isolation mechanism for API traffic is the hand-written `.eq("user_id", …)` filter in each handler. There is no second line of defence. A missing `.eq()` is a live hole, not a defence-in-depth gap.

### 1.6 There is no "superadmin" role — only `FOUNDER_EMAILS`

The only privileged tier is env-driven: `FOUNDER_EMAILS` (`shared/deps.py:34-43`), checked by `_is_founder` (`:60-61`). Admin routes gate on it directly (`routers/law_upload.py:41-44`, `routers/admin_dashboard.py:37-39`, `routers/product_intelligence.py:103-107`, `routers/analytics.py:349-350`). `user_roles` has no admin/superadmin value.

---

## 2. Verdicts on the three reported findings

### CONF-008 — `PUT /api/users/{target_user_id}/role` — **CONFIRMED, and worse than reported**

**Code** (`klijenti/router.py:1195-1216`, verified verbatim):

```python
@router.put("/api/users/{target_user_id}/role")
async def set_user_role(target_user_id: str, request: Request, rola: str = "advokat"):
    user = await _auth_from_request(request)                     # :1202  authN only
    if user["role"] < Role.PARTNER:                              # :1203  global role check
        raise HTTPException(403, "Samo partner može menjati role korisnika.")
    if rola not in ROLE_STR:                                     # :1205  value validation
        raise HTTPException(422, ...)
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("user_roles").upsert({                # :1210  UNCONDITIONAL WRITE
            "user_id": target_user_id,
            "rola":    rola,
        }, on_conflict="user_id").execute()
    )
    return {"status": "postavljeno", "user_id": target_user_id, "rola": rola}
```

The endpoint is live: `klijenti_router` is registered at `api.py:585`.

Following the CEO code path end to end:

1. **Auth dependency:** `_auth_from_request` (`klijenti/router.py:1490-1505`) — JWT verify + `_enrich_user` → `_get_role` (`:48-70`).
2. **Is target ever compared to the caller's office?** **No.** `target_user_id` appears exactly three times in the handler (`:1197`, `:1211`, `:1216`) and never in a query alongside `kancelarija_id`, `kancelarija_clanovi`, or the caller's `user_id`. Grep confirms `user_roles` is written from exactly one place in the entire repo — this line (`klijenti/router.py:1210`).
3. **What is written:** an unconditional `upsert` keyed on `user_id`, setting `rola`. Note `dodelio` (the migration's own "who assigned this" audit column, `migrations/002_klijenti_crm.sql:13`) is **never populated**.

**Why the guard is not a tenant check.** `Role.PARTNER` comes from `user_roles.rola`, which is global (§1.4). "Caller is a partner" therefore means "caller is a partner *of the platform*", not "of a firm". The check answers the wrong question by construction — there is no firm in the data model at that point.

**Aggravating factors found during this audit (not in the original report):**

| # | Fact | Evidence |
|---|---|---|
| a | **Zero audit record.** `user_role_change` is a *declared* auditable action but has **zero call sites** in the entire repo. Sibling endpoints in the same file do log (e.g. `arhiviraj_klijent`, `klijenti/router.py:1183-1187`). | `shared/audit_immutable.py:89`; repo-wide grep for `user_role_change` returns only that declaration |
| b | **No rate limit.** Unlike essentially every other mutating route, `set_user_role` carries no `@limiter.limit(...)`. | `klijenti/router.py:1195-1196` (compare `routers/kancelarija.py:561`, `routers/zadaci.py:142`) |
| c | **User-enumeration oracle.** `user_roles.user_id` is `REFERENCES auth.users(id)`. A *valid but foreign* UUID → `200 OK`; a *nonexistent* UUID → FK violation → uncaught exception → `500`. There is no `try/except` around `:1209-1214`. Combined with (b), this is an unmetered oracle for "does this account exist". | `migrations/002_klijenti_crm.sql:11`; `klijenti/router.py:1209-1214` |
| d | **Contrast: the firm-scoped sibling does it correctly.** `PUT /api/kancelarija/uloga/{clan_id}` requires firm-admin **and** re-queries the member row with `.eq("kancelarija_id", firma["id"])`, 404 otherwise. | `routers/kancelarija.py:560-587`, specifically `:572-582` |

**Expected behaviour for superadmin/founder — is it defined?** **No. It is implicit and accidental.** There is no founder branch in `set_user_role`. Founders merely reach it because `_get_role` short-circuits `_is_founder(email) → Role.PARTNER` before touching the DB (`klijenti/router.py:62-63`). Two consequences fall out of that short-circuit rather than out of any design decision:
- A founder can never be demoted through this endpoint (the DB row is ignored for founders) — correct by accident, not by intent.
- A **non-founder** partner has exactly the same power over the whole platform as a founder, which is certainly not intended.

---

### CONF-009 — `POST /api/zadaci/kreiraj` → cross-tenant task injection — **CONFIRMED, and the real exploit is broader than reported**

**Write end — confirmed** (`routers/zadaci.py:141-183`):

```python
firma = await _get_firma_info(supa, uid)          # :155  caller's OWN firm
kancelarija_id = firma.get("kancelarija_id")      # :156
...
supa.table("zadaci").insert({                     # :168
    "kancelarija_id": kancelarija_id,             # :169  attacker's firm
    "predmet_id":     payload.predmet_id,         # :170  ← NEVER VERIFIED
    "kreirao_uid":    uid,                        # :171
    "dodeljen_uid":   payload.dodeljen_uid,       # :172  ← NEVER VERIFIED
    "naziv":          payload.naziv,              # :173  attacker-controlled text
    ...
})
```

Both `predmet_id` and `dodeljen_uid` come straight off `ZadatakRequest` (`routers/zadaci.py:60-67`) and reach the insert with no ownership or membership check. The original report named `predmet_id`; **`dodeljen_uid` is the more dangerous of the two and was not reported.**

**Read end — two separate paths, one confirmed and one conditional:**

| Path | Location | Status |
|---|---|---|
| `GET /api/workspace` — the canonical daily board | `routers/workspace.py:129-136`: `.select("id,naziv,opis,prioritet,status,rok_datum,predmet_id,kreirao_uid,created_at").eq("dodeljen_uid", uid)` — **no `kancelarija_id` scope** | **CONFIRMED.** Any authenticated user can push an arbitrary-title, arbitrary-body, arbitrary-deadline task onto **any victim's** primary work surface by setting `dodeljen_uid` to the victim's UUID. |
| Notification amplifier | `routers/zadaci.py:185-188` → `_posalji_notifikaciju` (`:124-136`) → `shared/proactive_alerts.py::create_proactive_alert` | **CONFIRMED.** The victim also receives a `proactive_alerts` row titled `f"Novi zadatak: {naziv[:60]}"` with attacker-chosen text. `ZadatakRequest.naziv`/`opis` carry **no** `sanitize_user_input` validator, unlike siblings (`routers/rocista.py:345-351`, `routers/komentari.py:25-28`). |
| `GET /api/zadaci/moji` with `predmeti(naziv)` embed | `routers/zadaci.py:214-217`: `.select("*, predmeti(naziv)").eq("dodeljen_uid", uid)` | **CONDITIONAL — must be settled against the live DB.** The code clearly intends to return the case name. PostgREST resource embedding requires a declared FK, and `zadaci.predmet_id` is declared as bare `predmet_id UUID` with **no `REFERENCES`** (`migrations/045_firm_intelligence.sql:114`); no later migration adds one. As written in the repo, this call would fail `PGRST200` and 500 out. If the deployed database has the FK (added out-of-band), the leak is live exactly as reported. **Recommended probe: `SELECT conname FROM pg_constraint WHERE conrelid = 'zadaci'::regclass AND contype = 'f';`** |

**The reported chain (attacker plants victim's `predmet_id`, then reads the name back via `/moji`) therefore rests on an FK that does not exist in the repo. The chain that does not depend on any FK — injection into the victim's Workspace board and notification feed — is confirmed and is the higher-severity one.**

Two further observations:
- `zadaci` RLS (`migrations/045_firm_intelligence.sql:133-141`) still matches `status = 'aktivan'`, a value that migration 067 renamed to `ACTIVE` — the policy is stale. Immaterial for API traffic (service_role bypasses RLS, §1.5) but it means the browser-side defence is also dead.
- `PATCH /api/zadaci/{id}/status` (`:314`), `PATCH /{id}/dodeli` (`:363`) and `DELETE /{id}` (`:388-397`) *are* correctly scoped. The create path is the only unscoped one in the file — and the file's own regression test asserts the opposite (see §5).

---

### CONF-010 — `predmet_istorija` writes without ownership — **CONFIRMED at both sites; the read at `api.py:4154` is an amplifier, not an independent hole**

| Site | Verdict | Evidence |
|---|---|---|
| `POST /api/pitanje` (`api.py:3259-3261`) → insert at `api.py:3378-3384` | **CONFIRMED.** `predmet_id` arrives from the request body (`PitanjeReq.predmet_id`, `api.py:1201`), is normalized at `api.py:3316`, and is inserted with no ownership check. Note the asymmetry: the *context read* a few lines earlier (`api.py:3339-3340`) **does** filter `.eq("user_id", user["user_id"])`, so the author was thinking about isolation on the read and forgot it on the write. | `api.py:3376-3386` |
| `POST /api/procena` (`api.py:4751-4753`) → insert at `api.py:4895-4901` | **CONFIRMED.** Same shape: `predmet_id` from `body.get("predmet_id")` (`api.py:4768`); the context read at `api.py:4774` filters `.eq("user_id", user.id)`, the write at `:4896` does not. | `api.py:4892-4902` |
| `api.py:4372` — "the correct one" | **CONFIRMED CORRECT.** `POST /api/predmeti/{predmet_id}/istorija` verifies before inserting. This is the canonical pattern (§4). | `api.py:4366-4382` |
| `api.py:4154` — read without `user_id` filter | **NOT an independent hole.** `GET /api/predmeti/{predmet_id}` gates the parent row at `api.py:4129` (`.eq("id",…).eq("user_id", user.id)`) with an intentional delegated-access fallback (`api.py:4140-4149`), and 404s at `:4150` before any child query runs. The six child reads at `:4153-4158` (`predmet_beleske`, `predmet_istorija`, `predmet_dokumenti`, `predmet_hronologija`, `predmet_komentari`, `predmet_klijenti`) are gate-first-then-fan-out — the same deliberate design documented in `shared/case_context.py:115-190`. | `api.py:4124-4159` |

**Exploit shape (integrity, not confidentiality).** The attacker's row is stamped with the *attacker's* `user_id` (`api.py:3380`, `:4897`), so the attacker cannot read it back. The victim can: `api.py:4154` returns all `predmet_istorija` rows for the case regardless of `user_id`. The result is **attacker-authored Q&A text appearing inside the victim's case file, rendered as the victim's own AI history** — content injection into a legal record, plus unbounded row growth on a foreign case. It does *not* poison the victim's future AI context, because the context loader at `api.py:3340` filters by `user_id`.

---

## 3. Repo-wide sweep — every route with a missing ownership check

Method: AST enumeration of all `@app.*`/`@router.*` handlers (297 accept a resource id) → automated ownership-evidence scoring → **line-by-line manual review of all 85 low-evidence handlers**, including every helper they call.

### 3.1 CONFIRMED — no ownership check on an attacker-supplied resource id

Ranked by what the attacker actually gains.

| # | Method | Path | File:line | Param | Ownership check? | What the attacker gets |
|---|---|---|---|---|---|---|
| 1 | PUT | `/api/users/{target_user_id}/role` | `klijenti/router.py:1195` (write `:1210`) | `target_user_id` (path) | **None.** Only a global `role < PARTNER` gate (`:1203`) | **Platform-wide privilege change.** A partner of any firm sets *any* user's global role: promote an accomplice to `partner` (unlocks `access_confidential`, `view_audit_log`, `soft_delete_client` — `klijenti/permissions.py:94-103`) or demote a rival to `sekretarica`, locking them out of their own CONFIDENTIAL client fields (`:89-91`). No audit, no rate limit, plus a user-existence oracle. |
| 2 | POST | `/api/zadaci/kreiraj` | `routers/zadaci.py:141` (write `:168-178`) | `dodeljen_uid`, `predmet_id` (body) | **None for either** | **Cross-tenant write into a victim's primary UI.** Arbitrary task (title/body/priority/deadline, unsanitized) lands on any victim's canonical Workspace board (`routers/workspace.py:129-136`) plus a `proactive_alerts` notification. Optionally bound to one of the victim's real `predmet_id`s so it renders under a genuine case. Case-name read-back via the `predmeti(naziv)` embed (`:215`) is FK-conditional — see CONF-009. |
| 3 | POST | `/api/pitanje` | `api.py:3259` (write `:3378`) | `predmet_id` (body) | **None on the write path** (the sibling read at `:3339-3340` *is* scoped) | Attacker-authored Q&A injected into a victim's `predmet_istorija`; surfaces verbatim in the victim's case view (`api.py:4154`). |
| 4 | POST | `/api/procena` | `api.py:4751` (write `:4895`) | `predmet_id` (body) | **None on the write path** (the sibling read at `:4774` *is* scoped) | Same as #3, with a full GPT-4o legal assessment as the payload. |
| 5 | POST<br>PATCH | `/billing/recurring`<br>`/billing/recurring/{template_id}` | `routers/recurring.py:90` (write `:110-113`)<br>`routers/recurring.py:182` (write `:204-208`) | `klijent_id`, `predmet_id` (body) | **None for either id.** The PATCH *does* verify the template itself (`:192-201`) but then writes the new `klijent_id`/`predmet_id` unvalidated | Reaches a **money table**. Dangling cross-tenant FKs are copied into real `fakture` rows by `_build_faktura_row` (`:73-86`, invoked at `:317`). No victim data returns (all `fakture` reads are `user_id`-scoped), so this is billing-integrity damage, not disclosure. |
| 6 | POST | `/api/memory-graph/dodaj-vezu` | `routers/memory_graph.py:82` (write `:105-119`) | `from_id`, `to_id`, `predmet_id` (body) | **None for any of the three** — only enum validation of `from_type`/`to_type`/`relacija` (`:93-98`) | Intra-firm. Attacker-controlled `from_naziv`/`to_naziv`/`kontekst`/`ishod` plus a victim's `predmet_id` are written into the firm-shared knowledge graph and then injected verbatim into LLM prompts read by **every colleague in the same kancelarija** (`:233-239`, `:342-347`). The sibling `/preporuka/{predmet_id}` in the same file does it correctly (`:305`). |
| 7 | POST | `/api/firma-memorija/dodaj` | `routers/firm_memory.py:157` (write `:188`) | `entity_id` (body, free-form) | **None** — value-list validation only (`:172-177`) | Intra-firm, not cross-tenant: arbitrary "institutional memory" text attached to any UUID (incl. `entity_type: "predmet"`), which then feeds the AI prompt context of **other members of the same kancelarija** (`api.py:1343-1354`, `routers/firm_memory.py:284-288`). Every read is `.eq("kancelarija_id", …)`, so blast radius stops at the firm boundary. |
| 8 | POST | `/api/style/analiziraj` | `routers/style_checker.py:179` (write `:225`) | `predmet_id` (body) | **None** | Write-pollution only. Row is stamped with the attacker's `user_id` (`:224`) and both readers filter on it (`:267`, `:289`) — no read-back, no leak. Contaminates per-case style analytics. |
| 9 | POST | `/api/knowledge/save` | `routers/knowledge_base.py:159` (write `:183`) | `predmet_id` (body) | **None** | Cosmetic. Stored in `user_knowledge` and in Pinecone metadata (`:198`); all reads are `user_id`- or `kb_{uid}`-namespace-scoped (`:230`, `:276`, `:324`). The attacker can only mislabel their own note. |
| 10 | POST | `/api/portal/prati` | `routers/portal_monitoring.py:259` (write `:271-279`) | `predmet_id` (body) | **None** | Cosmetic. Self-scoped upsert on `(user_id, predmet_id)`; every reader filters `user_id` (`:297`, `:396`, `:484`, `services/agent_tasks/court_portal_watcher.py:141`) and the cron matches on the attacker's own `broj_predmeta`/`sud_naziv`, never joining `predmeti`. |

**No confirmed cross-tenant *read* leak was found.** Every route that returns another tenant's data in an HTTP response was already gated. Findings #2-#10 are all **write-side** — the class of bug the existing audits under-weighted because "nothing leaks back to the attacker" reads as "not a security issue". Three of them (#2, #6, #7) are read back **by the victim or their colleagues**, and one (#5) lands in financial records.

### 3.2 Reviewed and cleared (selected — the ones that looked most dangerous)

| Route | File:line | Why it is safe |
|---|---|---|
| `POST /copilot/chat` (all 11 intents) | `routers/copilot.py:1422`, gate at `:1442` | `_load_predmet_context` hard-gates (`:210-233`), **and** every write intent re-checks: `:801-805` (rok), `:870-874` (beleška), `:931-935` (klijent link), `:1252-1257` (billing). |
| `POST /api/enterprise/predmet/delegiraj` | `routers/enterprise.py:220` | Case ownership `:229-241`; delegation *target* must be in the caller's own firm `:248-255`. This is the only sanctioned cross-user read grant (consumed at `api.py:4140-4147`). |
| `POST /billing/entries`, `/timer/start`, `/faktura` | `routers/billing.py:224`, `:394`, `:598-611` | Canonical pre-check; cross-case entry mixing explicitly rejected at `:609-611`. |
| `POST /api/smart-intake/jobs/*` | `routers/smart_intake.py:270`, `:385`, `:474`, `:815`, `:1031` | Every job gated on `.eq("uploaded_by", uid)`; supplied `predmet_id` gated on `.eq("user_id", uid)`. |
| `GET /api/portal/predmet`, `POST /api/client-portal/dokument` | `api.py:2586-2604`; `routers/client_portal.py:107-126`, `:538-548` | Ids are read *out of* a 256-bit token / HMAC-SHA256-signed payload, never off the request. |
| `PATCH /api/workflow/step/{step_id}/zavrsi` | `routers/workflow.py:371-378` | Creator OR assignee OR same `kancelarija_id`, 403 otherwise. |
| `POST /api/agents/pipeline` | `routers/multi_agent.py:854` → `run_agent` `:432-434`, `:591`, `:618` | Forwards to `run_agent`, which verifies `.eq("id",…).eq("user_id", uid)` and gates the billing/deadline sub-reads on `predmet_verifikovan`. The earlier `/run` fix does cover `/pipeline`. |
| `POST /api/rociste/followup`, `POST /api/rokovi/lanac` | `routers/rocista.py:373-382`; `routers/rokovi_lanac.py:410-419` | Canonical check before every insert. |
| `routers/saradnja.py` (all 7 routes) | `:141`→`:93-104`, `:204`, `:257`, `:316`, `:381`, `:429`, `:482` | Full-file sweep, no gaps. The deliberately unscoped `predmeti` read at `:333-338` is fed only by ids from `predmet_saradnici` filtered on `saradnik_user_id`; rows land there only via `dodaj_saradnika`, which calls `_proveri_vlasnistvo` first. Sanctioned sharing, not a bypass. |
| `routers/komentari.py`, `evidence.py`, `evidence_graph.py`, `kalendar.py`, `rocista.py`, `dokument.py` | full-file sweep | No gaps. `dokument.py` uses `_verify_pred_namespace_ownership` (`:170-214`), fail-closed. |
| `GET /briefing/today-focus`, `/portfolio/dashboard`, `/api/profitabilnost/pregled`, `/api/inbox`, `/api/dashboard/command-center` | `morning_briefing.py:1094-1231`; `portfolio.py:47-65`; `profitabilnost.py:236`; `inbox.py:72-100`; `dashboard.py:77-169` | Accept no resource id at all; every query is `.eq("user_id", uid)`. Flagged by the automated pass because `predmet_id` appears in *response construction*. |
| All `/api/admin/*`, `/admin/pi/*`, `POST /api/admin/law/*` | `routers/admin_dashboard.py:37-39`, `routers/product_intelligence.py:103-107`, `routers/law_upload.py:41-44`, `routers/batch_ingest.py:41-47`, `routers/analytics.py:349-350` | Founder-email gated. Cross-tenant by design; vertical, not horizontal — out of scope for this audit. |
| `POST /email-notif/*` | `routers/email_notif.py:84-99` | `X-Cron-Key` / founder gate. Iterates all users by design. |

### 3.3 Defence-in-depth notes (not findings — no exploit path today)

1. `POST /api/rociste/cross-exam` (`routers/hearing_cc.py:505`) has no explicit 404 gate; it is safe only because its single DB path runs through `build_case_context(…, uid, …)` (`shared/case_context.py:169-172`). One refactor away from being a leak, and it silently charges a credit for a foreign id (`:591`).
2. `predmet_klijenti` has no `user_id` column, so several joins query it by `predmet_id`/`klijent_id` alone (`klijenti/router.py:667-672`, `routers/analytics.py:218-222`, `routers/conflict_check.py:245-249`). Safe today only because every *insert* path into that table now verifies both sides. That is an invariant nothing enforces.
3. `routers/batch_ingest.py:261-265` reads `ingest_jobs` by `job_id` with no owner filter — harmless while founder-only, but it hard-codes the assumption that admin is a single person.
4. `zadaci` RLS policy (`migrations/045_firm_intelligence.sql:133-141`) matches the pre-067 status value `'aktivan'` and is therefore dead.
5. `POST /v1/webhook/clio` (`routers/integracije.py:275`) performs an **arbitrary-tenant `predmeti` insert** using `vindex_user_id` taken from the webhook body (`:301`, insert `:307-313`). It is unreachable by an authenticated tenant — gated on an HMAC-SHA256 over the raw body with `CLIO_WEBHOOK_SECRET`, constant-time compared (`:283-290` → `:175-181`), 503 if unconfigured. But nothing verifies that `vindex_user_id` belongs to a user who actually connected Clio, so any holder of that one platform-wide shared secret gets a cross-tenant write primitive. Already tracked as `LAMBDA-OWN-001` (`docs/lambda/IDOR_MATRIX.md`, row 30); re-confirmed unchanged, not re-opened.
6. `POST /api/portal/cron-proveri` (`routers/portal_monitoring.py:540`) carries both `Depends(get_current_user)` (`:544`) and an `X-Cron-Secret`-or-founder check (`:552-555`), so a header-only cron caller must additionally present a JWT. Functional wart, not a hole.

---

## 4. Canonical ownership pattern — the one to apply everywhere

The correct implementation already exists in the codebase. `api.py:4370-4374`:

```python
# Verify BEFORE the id is used in any read or write.
pred = _get_supa().table("predmeti").select("id") \
    .eq("id", predmet_id).eq("user_id", user.id).single().execute()
if not pred.data:
    raise HTTPException(status_code=404, detail="Predmet nije pronađen")
```

Its four load-bearing properties:

1. **Gate first, fan out second.** The ownership query runs *alone*, before any sibling query, and 404s before them. `shared/case_context.py:115-190` documents why: child tables such as `case_actions` have no `user_id` column at all, so the parent gate is the *only* thing protecting them.
2. **404, never 403.** A case owned by someone else must be indistinguishable from a case that does not exist — otherwise the endpoint is an existence oracle. Compare CONF-008's 200-vs-500 split, which *is* one.
3. **No founder/admin bypass.** Ownership is a data boundary, orthogonal to `_is_founder` and to `PermissionService.require(feature)` (which answers a different question — subscription tier, not data ownership; see `docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` §1).
4. **Applies to writes exactly as to reads.** Findings #2-#10 are all writes. "The attacker can't read it back" is not a defence when the *victim* can.

**Firm-scoped variant**, when the resource lives on `kancelarija_id` rather than `user_id` — `routers/kancelarija.py:571-582` is the reference:

```python
firma = _require_firma_admin(supa, uid)          # caller must be admin of a firm
row = supa.table("kancelarija_clanovi").select("id, email, status") \
    .eq("id", clan_id).eq("kancelarija_id", firma["id"]).maybe_single().execute()
if not row.data:
    raise HTTPException(404, "Član nije pronađen u vašoj firmi.")
```

**Assigning work to a person** (the missing check in CONF-009): the target must be an ACTIVE member of the caller's own firm — the same query `_get_firma_info` already runs at `routers/zadaci.py:103-110`.

`docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` (2026-07-23) already proposed consolidating this into a single `Depends(verify_predmet_ownership)` in `shared/deps.py`. It was never implemented. Findings #2 through #10 are exactly the "SEC-001-v2" that document predicted, in nine places.

---

## 5. ACTOR × TARGET × ACTION matrix

### 5.1 `PUT /api/users/{target_user_id}/role` — `klijenti/router.py:1195`

Legend: **ACTUAL** = behaviour proven from the code at the cited lines. **EXPECTED** = what a correct, tenant-aware implementation must do.

| # | ACTOR | TARGET | ACTION | ACTUAL (proven) | EXPECTED | Gap |
|---|---|---|---|---|---|---|
| 1 | Partner, firm A | User in firm A | set `rola=partner` | `200` — upsert `:1210` | `200` | — |
| 2 | Partner, firm A | **User in firm B** | set `rola=partner` | **`200` — succeeds.** No firm comparison anywhere in `:1195-1216` | `403`/`404` | **CONF-008 core** |
| 3 | Partner, firm A | **User in firm B** | set `rola=sekretarica` | **`200` — succeeds.** Victim loses `access_confidential` / `download_document` on **their own** clients (`klijenti/permissions.py:89-90`, `:101-102`) | `403`/`404` | **CONF-008, destructive direction** |
| 4 | Partner, firm A | **Solo lawyer, no firm** | any role | **`200`.** `user_roles` has no firm column, so "no firm" is not even a distinguishable state | `403`/`404` | **CONF-008** |
| 5 | Partner, firm A | Nonexistent UUID | any role | **`500`** — FK violation on `user_roles.user_id` (`migrations/002_klijenti_crm.sql:11`), uncaught (`:1209-1214` has no `try`) | `404`, identical to a foreign target | **Existence oracle** (§2 CONF-008 (c)) |
| 6 | Partner | **Self** | set `rola=sekretarica` | **`200`.** Irreversible self-demotion — the actor can no longer pass `:1203` | Explicit policy: block, or require a second partner | **Undefined behaviour** |
| 7 | **Founder** | Any user | any role | `200`. Founder passes `:1203` only because `_get_role` short-circuits at `klijenti/router.py:62-63` | Same, but *explicitly*, and audited | **Implicit, not designed** |
| 8 | Partner, firm A | **Founder** | set `rola=sekretarica` | Row is written, but **no effect** — `_get_role` returns `PARTNER` for founders before reading the DB (`:62-63`) | No effect, by design | Correct **by accident** |
| 9 | `advokat` (default role) | Anyone | any role | `403` at `:1203`. This is the one boundary that holds — `DEFAULT_ROLE = Role.ADVOKAT` (2) `< PARTNER` (3) (`klijenti/permissions.py:42`) | `403` | — |
| 10 | `sekretarica` / `pripravnik` | Anyone | any role | `403` at `:1203` | `403` | — |
| 11 | Unauthenticated | Anyone | any role | `401` at `klijenti/router.py:1496`/`:1500` | `401` | — |
| 12 | Partner, firm A | **SUSPENDED/REMOVED member of firm A** | any role | **`200`.** `user_roles` is independent of `kancelarija_clanovi`; a removed member keeps their global role forever, and there is no code path that clears it on removal (`routers/kancelarija.py:520-557`, `shared/seats.py:143-160`) | Role revoked on seat removal | **Orphaned privilege** |
| 13 | Actor whose own `user_roles` read **errors** | Anyone | any role | `403` — `_get_role` fails closed to `Role.SEKRETARICA` on exception (`klijenti/router.py:68-70`, LAMBDA003 fix) | `403` | — Correct |

**Reading of row 12:** the two role systems being disconnected means firm offboarding does not revoke platform role. That is a second-order consequence of §1.4 and is not covered by any existing finding.

### 5.2 `POST /api/zadaci/kreiraj` — `routers/zadaci.py:141`

| # | ACTOR | TARGET | ACTION | ACTUAL (proven) | EXPECTED |
|---|---|---|---|---|---|
| 1 | Member, firm A | own `predmet_id`, `dodeljen_uid` = colleague in firm A | create | `200`, correct | `200` |
| 2 | Member, firm A | **`predmet_id` of firm B** | create | **`200`.** Inserted verbatim `:170`; row lands under firm A's `kancelarija_id` (`:169`) | `404` |
| 3 | Member, firm A | **`dodeljen_uid` = user in firm B** | create | **`200`.** Task appears on the victim's Workspace board (`routers/workspace.py:132`) + `proactive_alerts` row (`routers/zadaci.py:185-188`) | `403`/`404` |
| 4 | Member, firm A | nonexistent `predmet_id` | create | `200` — no FK on `zadaci.predmet_id` (`migrations/045_firm_intelligence.sql:114`) | `404` |
| 5 | Member, firm A | nonexistent `dodeljen_uid` | create | `200`; notification insert fails silently downstream | `404` |
| 6 | Solo lawyer (no firm) | any `dodeljen_uid` | create | **`200` with `kancelarija_id = NULL`** (`:156`, `:169`) — the row escapes `/api/zadaci/tim`'s firm filter (`:262`) entirely but still reaches the victim via `dodeljen_uid` | `403`/`404` |
| 7 | Self-created firm admin | any target | create | `200`. Firm creation is self-service (`routers/kancelarija.py:216-243`) — being "an admin" is not a trust signal | `403`/`404` |
| 8 | Unauthenticated | any | create | `401` (`Depends(get_current_user)`, `:146`) | `401` |

### 5.3 `predmet_istorija` writes — `api.py:3378` (`/api/pitanje`) and `api.py:4895` (`/api/procena`)

| # | ACTOR | TARGET | ACTION | ACTUAL (proven) | EXPECTED |
|---|---|---|---|---|---|
| 1 | User A | own `predmet_id` | write history | `200`, correct | `200` |
| 2 | User A | **User B's `predmet_id`** | write history | **`200`.** Row inserted with `user_id = A` (`api.py:3380` / `:4897`); visible to B at `api.py:4154` | `404` |
| 3 | User A | User B's `predmet_id` | **read** it back | **Blocked** — `get_predmet` gates at `api.py:4129` | `404` |
| 4 | User A | nonexistent `predmet_id` | write history | `200` silently — the insert is wrapped in a bare `except` that only logs (`api.py:3385-3386`, `:4902-4903`) | `404` |
| 5 | User A | User B's `predmet_id`, **context read** | read notes/history | **Blocked** — `.eq("user_id", …)` at `api.py:3339-3340` and `:4774` | empty |
| 6 | Founder | User B's `predmet_id` | write history | **`200`.** No ownership check exists to bypass | `404` — ownership must be founder-independent (`tests/test_sec001_predmet_ownership.py:156` already asserts this principle for the sibling endpoint) |
| 7 | Same, via the **correct** endpoint `POST /api/predmeti/{id}/istorija` | User B's `predmet_id` | write history | **`404`** at `api.py:4373-4374` | `404` — reference behaviour |

Row 7 against row 2 is the whole finding: **three endpoints write the same table; one checks, two do not.**

---

## 6. Why the existing test suite did not catch any of this

375 test files exist, including 16 with `idor`/`ownership`/`isolation`/`tenant` in the name. They missed all ten findings for three structural reasons.

### 6.1 The tests encode the *sweep's own blind spot* as an assertion

`tests/test_sec001_predmet_ownership.py:14-20` states, in the file's own docstring:

> *"Full sweep performed before this fix (per founder's explicit request): every other `{predmet_id}`-scoped mutation across `api.py` and all router files already applies the same ownership check… `dodaj_belesku` and `sacuvaj_istoriju` were the only two exceptions."*

That sweep enumerated **`{predmet_id}`-scoped** routes — i.e. routes with `predmet_id` **in the URL path**. `/api/pitanje` and `/api/procena` take `predmet_id` from the **JSON body** and write the **same table** (`predmet_istorija`) as the endpoint being fixed. They were structurally invisible to the sweep's own selection criterion, and the test file — scoped to exactly the two named functions (`:128`, `:175`) — cannot reach them. The documentation of the sweep became the reason nobody re-ran it.

### 6.2 A test that asserts the bug is isolated, in the very file that contains a second instance

`tests/test_beta_lockdown_zadaci_predmet_idor.py` covers `GET /api/zadaci/predmet/{predmet_id}` and states at `:16-19`:

> *"This is an isolated omission, not a systemic issue: every comparable `{predmet_id}`-scoped endpoint in the SAME file … already does exactly this ownership check."*

`POST /api/zadaci/kreiraj` is in that same file, twelve lines above the tested `_get_firma_info` helper, and checks neither `predmet_id` nor `dodeljen_uid`. Again the criterion was "`{predmet_id}` in the path"; `kreiraj` takes it in the body. The claim is asserted in prose and never tested.

### 6.3 The test shape can only catch read-leaks

Every ownership test in the suite follows the same pattern: mock `predmeti` to return `None` for a foreign id, call the handler, assert `HTTPException(404)` (e.g. `tests/test_beta_lockdown_zadaci_predmet_idor.py:47-56`). That shape presumes the handler *queries* `predmeti`. Nine of the ten findings here are handlers that **never query `predmeti` at all** — there is no mock for the test to trip. A write-side test has to assert on what reached `.insert()`, and no test in the suite does that.

### 6.4 Direct coverage check

| Route | Any test? |
|---|---|
| `PUT /api/users/{target_user_id}/role` | **None.** Repo-wide grep for `set_user_role` / `target_user_id` in `tests/` returns zero hits. `tests/test_lambda003_klijenti_role_fail_closed.py` tests `_get_role`'s *fail-closed on DB error* behaviour only — the opposite end of the same file. |
| `POST /api/zadaci/kreiraj` | **None** for authorization. |
| `POST /api/pitanje` / `POST /api/procena` — `predmet_istorija` write | **None.** |
| `POST /billing/recurring`, `PATCH /billing/recurring/{id}` | **None.** |
| `POST /api/memory-graph/dodaj-vezu`, `/api/firma-memorija/dodaj`, `/api/style/analiziraj`, `/api/knowledge/save`, `/api/portal/prati` | **None.** |

---

## 7. Open items requiring a live-database probe (cannot be settled statically)

1. **`zadaci.predmet_id` FK.** Determines whether CONF-009's `predmeti(naziv)` read-back (`routers/zadaci.py:215`) is live or dead:
   `SELECT conname, confrelid::regclass FROM pg_constraint WHERE conrelid = 'zadaci'::regclass AND contype = 'f';`
2. **`kancelarija_clanovi.status` vocabulary.** Confirms migration 067 actually ran, which every firm-membership check depends on (`shared/kancelarija_utils.py:36`, `routers/zadaci.py:106`, `routers/kancelarija.py:77`):
   `SELECT DISTINCT status FROM kancelarija_clanovi;`
3. **Existing `user_roles` rows.** Establishes whether CONF-008 has already been exercised — and how many non-founder partners exist:
   `SELECT rola, count(*), count(dodelio) AS with_assigner FROM user_roles GROUP BY rola;`
   (`dodelio` should be 0 across the board — `klijenti/router.py:1210` never writes it. A non-zero count would mean a second writer exists outside this repo.)
4. **Orphan `predmet_istorija` rows** — rows whose `user_id` differs from the owning case's `user_id` are direct evidence of CONF-010 having been exercised:
   `SELECT count(*) FROM predmet_istorija i JOIN predmeti p ON p.id = i.predmet_id WHERE i.user_id <> p.user_id;`
5. **Orphan `zadaci` rows** — same for CONF-009:
   `SELECT count(*) FROM zadaci z JOIN predmeti p ON p.id = z.predmet_id WHERE p.user_id <> z.kreirao_uid;`

---

## 8. Summary

| Item | Verdict |
|---|---|
| CONF-008 | **CONFIRMED**, plus 4 aggravating factors not in the original report (no audit, no rate limit, existence oracle, orphaned privilege after seat removal) |
| CONF-009 | **CONFIRMED**, with a broader and more severe vector than reported (`dodeljen_uid` → victim's Workspace board + notifications); the specific `predmeti(naziv)` read-back is FK-conditional and needs a DB probe |
| CONF-010 | **CONFIRMED at both write sites** (`api.py:3378`, `api.py:4895`); `api.py:4372` confirmed as the canonical pattern; `api.py:4154` is an amplifier, **not** an independent hole |
| New findings not in the original report | **8** — `routers/recurring.py:110-113` and `:204-208`, `routers/memory_graph.py:105-119`, `routers/firm_memory.py:188`, `routers/style_checker.py:225`, `routers/knowledge_base.py:183`, `routers/portal_monitoring.py:271-279`, and `dodeljen_uid` at `routers/zadaci.py:172` |
| Cross-tenant **read** leaks | **0 found** across 297 routes |
| Cross-tenant **write** holes | **10** (table §3.1) |
| Root cause | Ownership is re-implemented by hand at ~20 call sites with no shared primitive. Every prior sweep selected on "**id in the URL path**" — and **9 of the 10** findings take their id from the **request body**, where no sweep ever looked. `PUT /api/users/{id}/role` is the tenth: its id *is* in the path, but the resource is a *user*, and no sweep ever modelled "user" as an owned resource. |
