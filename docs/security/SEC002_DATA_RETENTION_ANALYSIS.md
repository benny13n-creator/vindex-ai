# SEC-002 — Data Retention Analysis

**Date:** 2026-07-23
**Status:** Analysis only. No code changed by this document. Legal conclusions are explicitly not made here — every retention question is marked `REQUIRES LEGAL CONFIRMATION`, not answered.
**Trigger:** Founder review of SEC-002 (`docs/security/SECURITY_GAP_REGISTER.md`) correctly reframed it: this is not a bug like SEC-001 ("someone can access another user's data" — no ambiguity). It's a policy question with a technical implementation gap: *"Šta tačno znači brisanje naloga kada korisnik ima profesionalnu obavezu čuvanja dokumentacije?"* Different tables carry different legal regimes; there is no single correct answer of "delete everything" or "keep everything."

---

## 0. A new, more urgent finding discovered while building this matrix — read this first

Investigating what "account deletion" *could* mean technically (beyond what the current GDPR endpoint does) surfaced something more dangerous than the misleading message. **Confirmed by direct schema inspection**, not assumed:

`profiles`, `predmeti`, `klijenti`, `fakture`, `billing_entries`, `tarife`, `rocista`, `predmet_dokazi`, and roughly 30 other tables are all defined with **`user_id UUID ... REFERENCES auth.users(id) ON DELETE CASCADE`** (and `predmeti`'s own children — `predmet_dokumenti`, `predmet_hronologija`, `predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `predmet_klijenti`, `rocista`, `predmet_health_log` — cascade a second time from `predmeti(id) ON DELETE CASCADE`).

**What this means concretely:** the application's own `DELETE /api/gdpr/account` endpoint never touches `auth.users` — it only updates `profiles`. But if anyone ever deletes a user directly at the Supabase Auth layer (Supabase dashboard "Delete user" button, Supabase Admin API, a cleanup script, an offboarding script for a departed employee's test account) — a natural, easy, one-click action that has nothing to do with this GDPR feature — **the cascade silently and irrevocably deletes every case record, every client record, every invoice and billing entry, everything**, with zero anonymization, zero review, zero retention of anything that might be legally required to survive. This is the functional opposite problem from the GDPR endpoint's current behavior (which under-deletes and overclaims), and it is arguably the more dangerous of the two: it can happen by accident, via a route nobody is currently monitoring or gating, and it is not reversible.

**This is tracked below as SEC-031** (new, continuing the Gap Register's numbering) — **CRITICAL**, evidence-based, `REQUIRES LEGAL CONFIRMATION` only on the *retention duration* question, not on whether the risk itself is real (it is, confirmed by schema).

---

## 1. Data Retention Matrix — Tier 1 (core personal / legal / financial data)

Full 8-column treatment for the tables directly implicated by SEC-002 and SEC-031.

### `profiles`
1. **Fields with personal data:** `email`, `full_name`.
2. **Owner:** the Vindex account holder (the lawyer/firm using the platform) — the data subject IS the Vindex customer here, not a third party.
3. **Purpose:** account identification, login, communication.
4. **Technically possible to delete/anonymize:** Yes — already implemented (`gdpr_delete_account` does this today).
5. **Retention may be required:** `REQUIRES LEGAL CONFIRMATION` — general account records may have their own minimum retention under Serbian consumer-contract or accounting rules, `NOT VERIFIED` from this repo.
6. **Current deletion behavior:** Anonymized (`email`→`deleted_{uid}@deleted.vindex.rs`, `full_name`→`"Obrisani korisnik"`). Row itself is never removed from `auth.users`, so SEC-031's cascade risk does not currently trigger via this endpoint.
7. **Recommended policy:** Current behavior is reasonable for this table specifically. No change recommended here.

### `klijenti` (client/party records)
1. **Fields with personal data:** `ime`, `prezime`, `firma`, `email`, `telefon`, `adresa`, `jmbg_mb` (**legacy plaintext**, SEC-018, never dropped), `jmbg_encrypted`/`broj_pasosa_encrypted`/`pib_encrypted` (AES-256-GCM), `napomena` (free text, may contain further PII).
2. **Owner:** the lawyer's client or a third party named in a matter (opposing party, witness) — **the data subject here is very often NOT the Vindex account holder**, which is a materially different situation from `profiles`.
3. **Purpose:** case representation, contact, billing.
4. **Technically possible:** Partially — the table already has `deleted_at` (soft-delete) and `pravni_osnov_obrade` (legal basis enum: `ugovor`/`zakonska_obaveza`/`legitimni_interes`/`saglasnost`) plus `saglasnost_datum` (consent date) columns (migration 002) — **more retention infrastructure already exists here than the GDPR endpoint currently uses.**
5. **Retention may be required:** `REQUIRES LEGAL CONFIRMATION` — this is very likely where Serbian advokatska profesionalna obaveza čuvanja spisa (professional obligation to retain case files) applies most directly, since client records are part of the case file. **Do not assume either direction.**
6. **Current deletion behavior:** None — `gdpr_delete_account` never touches this table at all, regardless of whether the deleted account is the sole owner of any `klijenti` rows.
7. **Recommended policy:** `REQUIRES LEGAL CONFIRMATION` before any change. The existing `deleted_at`/`pravni_osnov_obrade` columns suggest someone already anticipated this need — worth checking whether any endpoint currently sets `deleted_at` at all (`NOT VERIFIED` in this pass) before building something new.

### `predmeti` (+ `case_dna` jsonb column — the Case Genome)
1. **Fields with personal data:** `naziv`, `opis` (free text, commonly contains party names/facts), `case_dna` jsonb (extensive structured extraction: party names, addresses, financial detail, "argumenti_za/protiv", narrative — see `routers/case_dna.py`'s schema).
2. **Owner:** the lawyer (account holder) owns the record; the *content* frequently concerns third parties (clients, opposing parties).
3. **Purpose:** the core work product of the platform — the legal matter itself.
4. **Technically possible:** Yes, technically — but this is precisely the professional-record-retention question. **`REQUIRES LEGAL CONFIRMATION`, not a technical question.**
5. **Retention may be required:** `REQUIRES LEGAL CONFIRMATION` — this is the single highest-stakes retention question in the whole matrix.
6. **Current deletion behavior:** None via the GDPR endpoint (confirmed, SEC-002's original finding). **Full destruction via SEC-031's cascade if `auth.users` row is ever hard-deleted.**
7. **Recommended policy:** `REQUIRES LEGAL CONFIRMATION`. Whatever the answer, `SEC-031`'s uncontrolled cascade path must be closed regardless — even if the true policy turns out to be "yes, delete predmeti on account closure," that should be a deliberate, application-level, audited action, not an automatic side effect of an unrelated Auth-layer action.

### `predmet_dokumenti`, `predmet_dokazi`, `predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `predmet_hronologija`
1. **Fields with personal data:** document text/extracted content, evidence claims (`tvrdnja`), notes, Q&A history, timeline events — all case-content-adjacent, same character as `predmeti` above.
2. **Owner:** same as `predmeti` — the case, not a single individual.
3. **Purpose:** case work product.
4. **Technically possible:** Yes technically (all `ON DELETE CASCADE` from `predmeti`).
5. **Retention may be required:** `REQUIRES LEGAL CONFIRMATION`, same question as `predmeti` — these are the same "case file" for retention purposes, should get the same answer, not six separate ones.
6. **Current deletion behavior:** None via GDPR endpoint. Cascades automatically if the parent `predmeti` row is ever deleted (SEC-031 risk, one level removed).
7. **Recommended policy:** Bundle with `predmeti`'s policy decision — do not solve these six tables independently of the parent record they belong to.

### `predmet_genome_history` + `reasoning_graph`/`reasoning_nodes`/`reasoning_edges`/`reasoning_evidence`/`reasoning_sources`/`reasoning_confidence`
1. **Fields with personal data:** derived/AI-generated analysis of the above — versioned Genome snapshots, and (new, Phase 0, added same day as this audit) the Legal Reasoning Engine's structured claims/facts/citations.
2. **Owner:** derived from `predmeti`, same retention question inherited.
3. **Purpose:** AI-analysis audit trail and (for `reasoning_*`) the not-yet-shipped Legal Reasoning Engine's output.
4. **Technically possible:** Yes.
5. **Retention may be required:** Likely follows whatever is decided for `predmeti`/case content generally — these are *interpretations of* case content, not independent records, `REQUIRES LEGAL CONFIRMATION` on whether derived/AI analysis has different retention treatment than source records (some jurisdictions treat them differently).
6. **Current deletion behavior:** None via GDPR endpoint; cascades with `predmeti` (SEC-031).
7. **Recommended policy:** Bundle with `predmeti`.

### `fakture`, `billing_entries`, `tarife`
1. **Fields with personal data:** `klijent_naziv`, `klijent_adresa`, `klijent_pib` (invoice header fields — plaintext, not encrypted, unlike `klijenti.pib_encrypted`), line-item descriptions, amounts.
2. **Owner:** the firm's own financial/tax records, naming a client.
3. **Purpose:** billing, tax compliance.
4. **Technically possible:** Yes technically.
5. **Retention may be required:** `REQUIRES LEGAL CONFIRMATION`, but this is the one row in this matrix where an informed guess is reasonable to flag (not conclude): tax/accounting record retention periods are typically statutory and long (commonly 5-10 years in many jurisdictions) — **this is exactly the kind of table where SEC-031's uncontrolled cascade is most obviously dangerous**, since destroying tax records is a distinct legal problem from GDPR entirely.
6. **Current deletion behavior:** None via GDPR endpoint. **Full cascade destruction under SEC-031.**
7. **Recommended policy:** `REQUIRES LEGAL CONFIRMATION` on exact duration; strong recommendation regardless of that answer to close SEC-031 for this table specifically as a priority, given the asymmetric downside (destroyed tax records vs. a slightly-delayed GDPR response).

**Separately worth noting:** `fakture.klijent_pib` stores PIB in **plaintext**, unlike `klijenti.pib_encrypted` — the same identifier is encrypted in one table and not in another. Flagging as a new, small finding (call it **SEC-032**, LOW-MEDIUM) for the Gap Register — not part of SEC-002's scope, noted so it isn't lost.

### `audit_immutable`
1. **Fields with personal data:** `ip_hash` (hashed, not plaintext), `metadata` (jsonb, contents vary by action — `REQUIRES` a closer look at what specific actions put in `metadata`, `NOT VERIFIED` exhaustively in this pass).
2. **Owner:** Vindex (security/compliance record), incidentally about a user.
3. **Purpose:** tamper-evident security audit trail (GDPR Art. 32 cited in the module's own docstring).
4. **Technically possible to delete:** **No** — by design, the DB-level trigger (`protect_audit_immutable()`) blocks all `UPDATE`/`DELETE`, including from `service_role`. This is deliberate and correct for its purpose.
5. **Retention may be required:** The mechanism's own purpose (proving what happened, when) is undermined by deleting it — this table is a case where **not** deleting is very likely the compliant answer, `REQUIRES LEGAL CONFIRMATION` only on exact duration/format if a data subject specifically objects to their audit trail, which is a narrower question than blanket erasure.
6. **Current deletion behavior:** Cannot be deleted by any current code path (confirmed, this is a strength, not a gap).
7. **Recommended policy:** Leave as-is. If GDPR erasure of audit-trail entries is ever specifically required by legal counsel, that needs a deliberate, separate mechanism (e.g., pseudonymizing `user_id` while preserving the tamper-evident chain) — not a general "delete everything" sweep touching this table.

---

## 2. Data Retention Matrix — Tier 2 (grouped, appropriately brief)

Full per-table treatment for every one of the ~100 tables in this schema would repeat the same handful of patterns; grouped here by shape, with the pattern named once.

**Communication/notification tables** (`korisnik_email_notif`, `email_log`, `email_notif_log`, `whatsapp_pretplate`, `whatsapp_send_log`, `korisnik_viber_profil`, `notification_log`, `onboarding_email_log`, `push_subscriptions`): contain contact identifiers (email/phone) and delivery logs. Owner = account holder. `REQUIRES LEGAL CONFIRMATION` on retention, but these are lower-stakes than case/financial content — likely safe to actually delete on account closure (no professional-retention argument applies to "did we send this reminder email"), `NOT VERIFIED` as a legal conclusion, just a lower-risk category to prioritize once Tier 1 is resolved.

**Session/access tables** (`aktivne_sesije`, `client_portal_tokens`, `api_kljucevi`, `privremeni_pristup`, `predmet_delegiranja`): access-control state, not case content. Likely safe to delete on account closure — `REQUIRES LEGAL CONFIRMATION` for completeness, but no obvious retention argument here either.

**AI-generated analysis tables** (`commander_analize`, `evidence_grafovi`, `predictor_analize`, `hearing_briefovi`, `twin_simulacije`, `simulator_partije`, `user_knowledge`, `extracted_entities`, `intake_documents`, `intake_review_queue`, `intake_processing_outcomes`, `discovery_queue`, `smart_contract_analyses`): same shape as `predmet_genome_history` above — derived from case content, should inherit whatever policy is decided for `predmeti`, not be resolved independently.

**Firm/organization tables** (`kancelarije`, `kancelarija_clanovi`, `predmet_saradnici`): multi-user firm structures — deleting one member's account raises a *different* question (does the firm's shared data survive one member leaving?) than a solo account closing. `REQUIRES LEGAL CONFIRMATION` and likely `REQUIRES PRODUCT-POLICY DECISION` (not just legal) — a departing associate's account closing should almost certainly NOT delete the firm's case data, which points toward `predmeti`-level ownership possibly needing a firm-level concept, not just `user_id`, longer-term.

**Usage/billing-adjacent internal tables** (`usage_events`, `api_costs`, `feature_usage`, `feature_usage_log`): Vindex's own operational telemetry, not client-facing legal content. Low retention stakes, likely safe to delete or aggregate-and-delete.

---

## 3. Explicitly excluded — no personal data found

`feature_registry`, `feature_registry_audit`, `feature_dependencies`, `tier_config`, `tier_config_audit`, `business_groups`, `business_groups_audit`, `cron_runs`, `pinecone_capacity_snapshots`, `apr_lookup_log`, `status_incidents`, `kancelarija_seat_audit`, `law_docs`, `ratio_decidendi` (legal corpus reference data, not personal), `tos_acceptances` (contains a `user_id` + timestamp, borderline — included here since it's evidentiary of consent, not itself personal data beyond the FK). These are system/configuration/reference tables — reviewed, not analyzed line-by-line since none carry personal data warranting a retention decision.

---

## 4. Minimum safe code fix — proposed, not yet applied

Per the founder's own draft wording (kept, only lightly tightened for precision):

**Before (currently live, false as written):**
> "Vaš nalog je anonimizovan. Lični podaci su obrisani iz profila. Predmeti i dokumenti ostaju u sistemu u anonimizovanom obliku zbog zakonskih obaveza čuvanja."

**Proposed after:**
> "Vaš korisnički nalog je anonimizovan — email i ime uklonjeni su iz profila. Predmeti, dokumenti i druge poslovne evidencije mogu biti zadržani radi ispunjenja zakonskih, profesionalnih ili poreskih obaveza čuvanja podataka; ne anonimizuju se automatski ovim postupkom."

This is truthful for both possible answers to the open legal question — it doesn't assert data IS retained for a specific legal reason (which would itself need confirmation) or that it IS anonymized (which is false today either way). It states plainly what the endpoint actually does. **Zero data changes, zero risk, closes the false-claim problem immediately regardless of how the retention policy question is eventually resolved.** Recommend applying this as its own, isolated, immediately-actionable fix, separate from the larger retention-policy work above — same "smallest correct fix now, larger architecture later" discipline used for SEC-001.

---

## 5. Future Data Retention Architecture — proposal, not a commitment

A durable answer to "how long do we keep X, who can see it, what happens when an account closes" needs to be a first-class, queryable concept, not implicit in scattered `ON DELETE CASCADE` clauses that nobody audited end-to-end until this document. Proposed shape:

1. **A retention policy table** (e.g., `data_retention_policy`), one row per table or table-category, columns matching this document's matrix (owner type, purpose, legal basis, minimum retention period if any, deletion behavior on account closure) — turning this document from a one-time analysis into a living, queryable record. Legal-confirmed values only; unconfirmed rows stay explicitly marked pending.
2. **Close SEC-031 specifically, independent of the broader policy question**: `auth.users` should not have `ON DELETE CASCADE` wired directly to case/financial content for any table where the retention answer is unresolved. The safer default while `REQUIRES LEGAL CONFIRMATION` items remain open is `ON DELETE RESTRICT` or `SET NULL` (forcing a deliberate, application-level, audited process instead of a silent cascade) — this is itself a small, mechanical schema change once agreed, not a large project.
3. **A single, audited account-closure workflow** that consults the retention policy table per resource type, rather than the current single hard-coded `gdpr_delete_account` function making one blanket decision for every table.
4. **Firm-level ownership as a real concept** (flagged in §2) if multi-attorney accounts are a genuine product direction — a departing associate's account closure needs a different answer than a solo practitioner's.

**This section is a direction, not a design ready to build.** It follows from this document's findings but is explicitly out of scope to start without its own review, per the same discipline used throughout this project's architecture work this cycle (framework first, explicit go before implementation).

---

## Summary for the founder

- **SEC-002** (the false message) has a safe, zero-risk fix ready now (§4) — recommend applying it immediately, independent of the retention-policy question.
- **SEC-031** (new, this document) — the `ON DELETE CASCADE` chain from `auth.users` through nearly the entire schema — is a real, live, evidence-based CRITICAL risk that could destroy case and tax records irreversibly via a normal-looking admin action, with no relationship to the GDPR feature at all. This deserves attention at least as urgent as SEC-002 itself.
- **The actual retention-duration questions** (how long must `predmeti`/`klijenti`/`fakture` be kept) are legal questions this document deliberately does not answer — every instance is marked `REQUIRES LEGAL CONFIRMATION`, and answering them is the necessary next step before any table-level deletion behavior is built.
