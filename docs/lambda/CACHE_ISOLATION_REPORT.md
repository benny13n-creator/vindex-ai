# Cache Isolation Report — Program Lambda, Certification 003

**Agent**: Cache & Session Isolation. Largely new ground — no prior sprint did a dedicated, exhaustive cache
sweep. Every `functools.lru_cache`, module-level dict, and DB-backed cache in the codebase was found and its
key composition checked for a tenant component.

## Finding — FIXED, CRITICAL: `main.py::ask_agent`'s response cache leaked one firm's private content to a completely unrelated firm

**The single most severe finding of this entire multi-week engagement.** Every other IDOR/isolation bug found
across Lambda 001/002/003 required the attacker to know or guess a specific victim resource identifier. This
one required nothing — just asking an ordinary, everyday-sounding legal question.

### Mechanism

`_cache_kljuc()` (`main.py:188-192`, unchanged by this fix) = `md5(normalized question text)`. **Zero
user/firm/namespace component.** Two-tier cache: an in-process `_CACHE` dict shared across every request the
process handles, plus a Supabase `ai_cache` table queried only by that same tenant-blind key.

`ask_agent(pitanje, history, extra_namespaces, memory_context)` — `extra_namespaces` carries a firm's own
private Pinecone institutional-memory namespace; `memory_context` carries a firm's institutional memory
injected directly into the system prompt. Both are populated **automatically, server-side, for every ordinary
question** any firm with institutional memory configured asks (`api.py:2925-2929`, the standard `/pitanje`
endpoint — not a special upload-only path), with no `predmet_id` required.

**The bug — read/write gate asymmetry**: the READ gate checked `not history and not extra_namespaces` (2 of
3 private sources). All 3 WRITE gates (LOW/MEDIUM/HIGH confidence paths) checked only `not history` (1 of 3).
**`memory_context` was never checked on either side.** So:

1. Firm X asks an everyday question, no `history`. Their firm's private namespace/memory content shapes
   GPT's answer (merged into the retrieval `docs` list with no provenance tag preventing use in synthesis —
   `app/services/retrieve.py:1929`, confirmed). Confidence lands MEDIUM/HIGH (the common case).
2. The write gate fires (`not history` alone was true), caching Firm X's privately-influenced answer under a
   key derived only from the normalized question text.
3. Firm Y, unrelated, later asks a plain generic question with no `history` and no `extra_namespaces` of
   their own. The READ gate passes (`not history and not extra_namespaces` — both true for Firm Y). Firm Y
   receives Firm X's cached answer verbatim, `from_cache: True`. **Firm Y's own `memory_context` is never
   consulted** — the function returns before that code path is ever reached.

### Adversarial re-verification (Agent 8) — the claim survived the hardest scrutiny in the sprint

Every sub-claim was independently re-read character-by-character, not cited from the original report:
- `_cache_kljuc()` computed from the raw `pitanje` parameter only — confirmed no tenant-augmentation happens
  before the key is computed (this would have refuted the whole finding; it doesn't).
- Read gate confirmed to never check `memory_context` — **this makes the exposure broader than the original
  write-up emphasized**: even with `extra_namespaces=None`, a read can still serve a poisoned cache entry
  whenever `memory_context` alone was the differentiator on write.
- All 3 write gates confirmed to never reference `extra_namespaces`/`memory_context`, for LOW/MEDIUM/HIGH —
  MEDIUM/HIGH cache the actual GPT-generated answer text, not a placeholder.
- `api.py:2925-2929` confirmed as the ordinary endpoint, not a special path.
- `_CACHE` confirmed a bare shared module-level dict, `ai_cache` confirmed queried with no user/firm column.

**Verdict: CONFIRMED IN FULL, severity not reduced — precision increased.**

### Fix

All 4 gates (1 read, 3 write) now require `not history and not extra_namespaces and not memory_context`
together — the cache is fully disabled whenever ANY private-context source participates, and behaves exactly
as before for genuinely generic questions (all three absent). Minimal, no new architecture, no cache
redesign — the safest correct fix given the cache's own key has no tenant dimension to add safely without a
larger redesign.

**Status: FIXED.** Proof: `tests/test_lambda003_ask_agent_cache_isolation.py` (8 tests) — each of the 3
private-context sources independently proven to disable both read and write; a genuinely generic question
proven to still cache/read normally (no regression to the cache's own legitimate purpose); a structural guard
documenting why the cache key has no tenant component, so a future "fix" can't accidentally loosen the gates
back to history-only.

## Everything else checked — CERTIFIED or explicitly flagged

| Mechanism | Cache key | Verdict |
|---|---|---|
| JWKS signing-key cache (`api.py:272-299`) | fixed key `"keys"`, 1h TTL | CERTIFIED — public verification keys, not tenant data |
| `predmet_workspace` aggregation | N/A — no caching, fresh fetch every call | CERTIFIED |
| Morning Briefing daily generation | N/A — always regenerates | CERTIFIED |
| `briefing_istorija` history read | `.eq("user_id", uid)` | CERTIFIED |
| `today_focus` 5-min briefing cache | `.eq("user_id", uid).eq("datum", today)` | CERTIFIED |
| Redis (`shared/rate.py`) | slowapi's own IP/route rate-limit keys | CERTIFIED — zero other Redis usage anywhere in the repo |
| `ratio_decidendi` cache (`praksa.py`) | `decision_number`, no user scope | CERTIFIED — caches PUBLIC jurisprudence, correctly global |
| `conversations` chat-history table (browser, anon key) | client-generated `session_id` | **NEEDS LIVE VERIFICATION** — repo-wide grep finds zero `CREATE TABLE`/policy source for this table; the RLS policy Certification 002 cited as "the sole guard" cannot be confirmed to exist from source alone. Re-confirmed still open, not newly found. |
| `routers/dokument.py` ephemeral session Q&A | `session_id`, no owner binding | Pre-existing, already tracked (`SEC-039`) — not re-reported |

Cache poisoning via error/partial-state: no additional instance found. `_cache_set` is only ever called
explicitly after a full successful result is constructed; no code path caches an exception or partial object.
