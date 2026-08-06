# GPT-5.1 Security Review — Program Tau, Master Sprint 001, Agent 4

**Date:** 2026-08-06
**Scope:** the OpenAI data-flow boundary specifically — not a general app security audit (see `docs/security/` for that). Phase 1 analysis only, no code changed.
**Method:** direct grep/read of the actual call sites and migrations, cross-checked against prior `docs/security/` findings where relevant. Every claim below cites file:line or is explicitly marked as unverifiable from code.

---

## 1. Data flow to OpenAI — what crosses the boundary

There is no per-call redaction/anonymization layer. Case content (document text, party names, case facts) goes to OpenAI **as assembled by each call site**, not masked. Confirmed via `shared/ai_client.py:87-110` (`_extract_user_text`) — this function exists to *hash* user-role content for provenance, not to *strip* it before sending; the actual `messages` payload reaches OpenAI unmodified. Representative call sites confirmed in prior session work: `routers/case_commander.py`'s `_dohvati_predmet_kontekst` assembles case documents/evidence/dokazi into the prompt context sent to GPT. No redaction step exists between context assembly and the `.create()` call in any file I sampled.

**This is not a new problem introduced by GPT-5.1** — it is the platform's existing, structural posture: legal case content is sent to OpenAI as part of normal operation, and the risk model already implicitly accepts this (`docs/security/SEC002_DATA_RETENTION_ANALYSIS.md` discusses retention of *derived* AI outputs like `commander_analize` but does not address OpenAI-side data handling of the *input* at all — this is a gap in the existing security documentation, not just in this review). Flagging as **relevant background for Agent 5/8**, not a new finding to fix in code.

## 2. Encryption

- **In transit:** standard `openai`/`AsyncOpenAI` SDK usage throughout (`shared/ai_client.py`) — no custom transport, so this rides the SDK's default TLS. No finding.
- **At rest — Supabase:** Postgres-at-rest encryption is a Supabase platform guarantee, **not verifiable from this codebase** — not a code finding either way.
- **At rest — `commander_analize`:** stores full GPT response text (`analiza text NOT NULL`, `migrations/057_active_orphaned_tables.sql:57-72`), not just a hash. RLS is present and correctly scoped: owner-only `SELECT`/`INSERT` (`migrations/057_active_orphaned_tables.sql:66-72`, `user_id::text = auth.uid()::text`). **No gap found** — same protection tier as other user-owned case data.
- **At rest — `ai_forensics`:** stores only SHA-256 hashes of prompts/responses (`system_prompt_hash`, `user_prompt_hash`, `output_hash` — `security/ai_forensics.py:154-217`), never raw text. RLS confirmed: owner-only `SELECT` (`migrations/043_security_bulletproof.sql:103-107`). This is a **deliberate, good design choice** — full audit coverage without a second copy of sensitive case content sitting in a forensics table.

## 3. Sensitive data exposure via logging

Checked for any `logger.*`/`print` call that dumps full prompt or completion text. **None found.** The one adjacent log line, `main.py:4065`, logs `len(user_content)` only, not content. `shared/ai_client.py`'s guard/provenance layer only ever handles hashes and lengths, never raw text, in its own log statements (`shared/ai_client.py:311-315`, `:332-336` log `risk_score`/`flags`/`caller`, not prompt text). **No finding.**

## 4. Audit coverage

This is the strongest part of the existing posture and should be explicitly preserved, not rebuilt, for GPT-5.1: `shared/ai_client.py::_patch_prompt_guard` (lines 268-389) monkey-patches `Completions.create`/`AsyncCompletions.create`/`Embeddings.create` **at the SDK class level**, before any router import. This means every one of the ~130 AI call sites in the repo is automatically covered — coverage does not depend on the call site's author remembering to instrument it (confirmed design intent, `shared/ai_client.py:15-24`, and confirmed as *actually* the sink in production: `security/ai_forensics.py:168-178` notes the older explicit-instrumentation path, `ForensicsRecord`, was "never actually wired into any of the ~130 AI call sites" and the class-level patch is what replaced it).

Each call captures: caller (`module_name`/`operation_name`), model, provider (`openai` vs `azure`), token counts, latency, system/user/output **hashes** (not raw text — see §2), correlation ID, and case/user/tenant context when available (`security/ai_forensics.py:246-276`). This is written to `ai_forensics`, RLS-protected per §2.

**One real gap, not a hypothetical one:** the hash-only design (deliberate per §2/§3) means this audit trail can prove *that* a call happened, with what model, and can verify integrity of a *known* prompt/response by re-hashing it — but it **cannot reconstruct the actual prompt or completion text after the fact** if that's ever needed (e.g., a client dispute over what GPT said, or a bar-association inquiry). `security/ai_forensics.py:7-9`'s own docstring claims "Potpuna rekonstrukcija svakog AI odgovora čak i godinama kasnije" (full reconstruction of any AI answer even years later) — **this claim is not accurate for the current hash-only implementation** and should be corrected or the design revisited (out of scope for this review to decide which; flagging for Agent 5/8).

## 5. Provider trust boundary

- **Azure OpenAI EU-routing option exists in code**: `shared/ai_client.py:36-84`, if `AZURE_OPENAI_KEY`/`AZURE_OPENAI_ENDPOINT` env vars are set, all calls transparently route to Azure OpenAI instead ("podaci ostaju u EU" per the module's own comment, line 7). **Whether this is actually active in the production environment is not verifiable from code** — it's an env var configuration matter.
- **OpenAI zero-data-retention / enterprise privacy settings**: grepped for `OPENAI_ORG`, `OPENAI_PROJECT`, `zero_data_retention`, `store=False`, `ZDR` — **zero references anywhere in the codebase.** This is not a code gap (ZDR is an organization/contract-level OpenAI setting, not something the SDK call itself typically configures per-request for chat completions), but it means there is **no code-level evidence of what OpenAI is contractually allowed to retain**, and no one should assume ZDR is active without confirming it out-of-band.

---

## Highest-severity finding

**Not a live vulnerability** — the architecture (SDK-level structural interception for both prompt-injection guarding and provenance logging, hash-only storage, correct RLS everywhere checked) is materially stronger than a typical greenfield integration, and this posture transfers to GPT-5.1 with zero code changes since the patch operates on the SDK class, not per-model logic.

The one finding worth carrying into Agent 5/8's roadmap: **`security/ai_forensics.py`'s own docstring overclaims "full reconstruction... even years later," but the actual implementation only stores hashes.** This is a documentation-accuracy gap that could matter in an actual legal/compliance dispute (someone reading that docstring and relying on it would be wrong). Recommend either (a) correcting the docstring to say "integrity verification," not "reconstruction," or (b) deciding — as a deliberate, evidence-first decision, not a GPT-5.1 side effect — whether full-text retention of prompts/completions is actually wanted for some subset of high-stakes calls. Not a blocker for GPT-5.1 adoption either way.
