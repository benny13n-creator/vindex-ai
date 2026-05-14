# Pre-Phase 1 Hygiene Report

**Run date:** 2026-05-10
**Branch:** main
**HEAD before:** 52776fbd55ddc8216b4dcc9a3519629f09d34268
**HEAD after:** fb3a96b1... (3 commits stacked)

---

## Phase A — Discovery

### A.1 Pre-flight

- HEAD: `52776fbd55ddc8216b4dcc9a3519629f09d34268`
- Branch: `main` ✓
- `git status -sb`: `## main...origin/main` (no `[ahead]` / `[behind]` suffix) — local even with origin ✓
- Working tree: `.claude/scheduled_tasks.lock` modified (tracked, to-be-untracked); many `??` untracked diagnostic/benchmark artifacts — all outside scope.

### A.2 .gitignore

**Current .gitignore (full quote):**
```
vector_store/
__pycache__/
*.pyc
.env
vector_store.zip
nvector_store/
.claude/
```

**`.env.example` exists in tracked files** → add `!.env.example` negation so template stays trackable.

**Patterns to add (not already in .gitignore):**
```
# IDE / agent local state
.vscode/
.idea/

# Python build / cache
*.pyo
.pytest_cache/

# Virtualenvs
.venv/
venv/
env/

# Secrets / env (template exempted)
.env.local
.env.production
!.env.example

# Logs / runtime artifacts
*.log

# Diagnostic outputs
30q_*.txt
v3_diff.txt
```

Already present (not re-added): `__pycache__/`, `*.pyc`, `.env`, `.claude/`

**Tracked-but-should-be-ignored files (TRACKED_BUT_IGNORED):**

| File | Matching pattern |
|------|-----------------|
| `.claude/scheduled_tasks.lock` | `.claude/` (already in .gitignore, not yet untracked) |
| `.vscode/settings.json` | `.vscode/` (to be added) |
| `ingest_laws_run.log` | `*.log` (to be added) |
| `web3_integracija/logs/error.log` | `*.log` (to be added) |
| `30q_after_subquery_fix.txt` | `30q_*.txt` (to be added) |
| `30q_corrected_baseline.txt` | `30q_*.txt` (to be added) |

Commit 1: **12 pattern-lines to add + 1 negation, 6 files to untrack** — NOT a no-op.

### A.3 Dead code

**`multi_query_rag.py`** — exists at `app/services/multi_query_rag.py` (tracked).
First 20 lines:
```
# -*- coding: utf-8 -*-
"""
Vindex AI — Multi-Query RAG Pipeline  (v2 — targeted refactor)
===============================================================
Changes from v1:
  FIX-1  classify_query_intent() + intent-aware decompose_query()
  FIX-2  Per-query cap (4) instead of global hard cap; soft cap via reranker
  FIX-3  rerank_documents() uses combined_query (original | sub1 | sub2 …) + priority boost
  FIX-4  build_structured_context() never truncates mid-article
  FIX-5  No "minimum 3 sources" rule; coverage = "sufficient" | "partial"
  FIX-6  LegalDoc.priority_score + source hierarchy weighting in reranker
  FIX-7  analyze_documents() extracts rules/exceptions/conditions/conflicts
  FIX-8  JSON output adds "coverage" and "konflikti" fields
  FIX-9  Stability safeguards: <2 docs, single-law scope, conflict detection
"""
import asyncio
import json
import logging
import re
```

**`example_multi_rag.py`** — exists at root (UNTRACKED — not in git index).
First 20 lines:
```
"""
Test: multi-query RAG — verifies all v2 fixes produce multi-article output.

Expected from a healthy index:
  - korisceni_clanovi: ≥2 articles from ≥2 laws (ZKP + Ustav)
  - coverage: "sufficient"
  - konflikti: populated if ZKP / Ustav rights overlap
  - napomena: "—" or a short caveat

Usage:
    python example_multi_rag.py
"""
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
```

**Import grep results (excluding matches inside each file):**

For `multi_query_rag`:
```
./app/services/retrieve.py:397:# Ported from multi_query_rag.py so both pipelines share one implementation.
./app/services/retrieve.py:509:    Capped at 3 (vs 5 in multi_query_rag.py) to respect latency budget.
```
→ Both are **comments only** — no `import` or `from ... import` statements.

For `example_multi_rag`: no results outside the file itself.

**DEAD_CODE_IMPORT_REFS:** empty for both files.

**Verdict:** SAFE TO DELETE.

**Note:** `example_multi_rag.py` is NOT tracked in git (untracked). `git rm` cannot target it; deleted from disk directly with `rm`.

### A.4 B1 gap

**Audit logger module:** `app/services/audit_log.py`

`log_response` signature (`audit_log.py:59–70`):
```python
def log_response(
    *,
    endpoint: str,
    query_hash: str,
    tip: Optional[str] = None,
    confidence: Optional[str] = None,
    top_score: Optional[float] = None,
    top_article: Optional[str] = None,
    top_law: Optional[str] = None,
    response_text: str = "",
    latency_ms: int = 0,
) -> None:
```

**Template — `/api/pitanje` handler, `api.py:1028–1041`:**
```python
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_agent, req.pitanje, history)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/pitanje",
            query_hash=qh,
            tip=tip,
            confidence=rezultat.get("confidence"),
            top_score=rezultat.get("top_score"),
            top_article=rezultat.get("top_article"),
            top_law=rezultat.get("top_law"),
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
```

**Endpoint B1 table:**

| Endpoint | Handler file:line | Uses ask_agent? | Logs response? | Logger function |
|----------|-------------------|-----------------|----------------|-----------------|
| `POST /api/pitanje` | api.py:1018 | YES | YES | `_al.log_response` at :1031 |
| `POST /api/pitanje/stream` | api.py:1052 | YES | YES | `_al.log_response` at :1106, :1204, :1270 |
| `POST /api/nacrt` | api.py:1293 | NO (ask_nacrt) | YES | `_al.log_response` at :1304 |
| `POST /api/analiza` | api.py:1321 | NO (ask_analiza) | YES | `_al.log_response` at :1333 |
| `POST /api/bot/ask` | api.py:997 | YES | **NO** | — |
| `POST /api/sazmi` | api.py:1351 | NO (GPT-mini rephrase) | NO | N/A — no ask_agent result dict |
| `POST /api/feedback` | api.py:1387 | NO (Supabase insert) | NO | N/A — feedback store only |
| `POST /api/podnesak` | api.py:1413 | NO (doc drafting) | NO | N/A — no ask_agent result dict |

**B1_GAP_ENDPOINTS:** `/api/bot/ask` only — same `ask_agent`/`pokreni` pipeline as `/api/pitanje`; template applies directly. `/api/sazmi`, `/api/feedback`, `/api/podnesak` excluded: no `ask_agent` call, no compatible `rezultat` dict.

`tip=None` used in fix (no `klasifikuj_pitanje` call in `bot_ask` scope — per task rule, use `None` for unavailable fields).

**Fix line count:** 13 lines in `api.py` only — within 20-line limit ✓.

### A.5 Summary

```
Discovery complete:
- Commit 1 (.gitignore): 12 pattern-lines to add + 1 negation, 6 files to untrack — APPLY
- Commit 2 (dead code): SAFE TO DELETE — 0 live imports (2 comment refs only in retrieve.py)
                        Note: example_multi_rag.py is untracked → disk delete (not git rm)
- Commit 3 (B1 gap): 1 endpoint to fix (/api/bot/ask), template from api.py:1031
```

---

## Phase B — Commit 1: .gitignore

**Status: APPLIED**

**Files untracked (git rm --cached, all exit 0):**
- `.claude/scheduled_tasks.lock`
- `.vscode/settings.json`
- `ingest_laws_run.log`
- `web3_integracija/logs/error.log`
- `30q_after_subquery_fix.txt`
- `30q_corrected_baseline.txt`

**Staged diff confirmed:** `M .gitignore` + 6 `D` deletions from index.

**Commit SHA:** `7151f0e`
```
chore: tighten .gitignore and untrack local agent/IDE/log artifacts
7 files changed, 25 insertions(+), 3646 deletions(-)
```

---

## Phase C — Commit 2: Dead code

**Status: APPLIED**

**Paranoia recheck before commit:** same 2 comment refs only — confirmed no new imports.

**Files removed:**
- `app/services/multi_query_rag.py` — `git rm` (tracked, exit 0)
- `example_multi_rag.py` — disk `rm` (untracked, not in git index; `git rm` not applicable)

**Commit SHA:** `1d0a782`
```
chore: remove dead code (multi_query_rag, example_multi_rag) — confirmed zero imports
1 file changed, 644 deletions(-)
delete mode 100644 app/services/multi_query_rag.py
```

---

## Phase D — Commit 3: B1 fix

**Status: APPLIED**

**Endpoint fixed:** `/api/bot/ask` (`api.py:997`)

**Insertion point:** `api.py:1011` — before `return normalizuj_rezultat(rezultat)`, after `pokreni()` call.

**Diff (13 lines, 1 file):**
```diff
     try:
+        t0 = _time.monotonic()
         rezultat = await pokreni(ask_agent, req.pitanje, None)
+        latency_ms = int((_time.monotonic() - t0) * 1000)
+        _al.log_response(
+            endpoint="/api/bot/ask",
+            query_hash=qh,
+            tip=None,
+            confidence=rezultat.get("confidence"),
+            top_score=rezultat.get("top_score"),
+            top_article=rezultat.get("top_article"),
+            top_law=rezultat.get("top_law"),
+            response_text=rezultat.get("data", ""),
+            latency_ms=latency_ms,
+        )
         return normalizuj_rezultat(rezultat)
```

**Commit SHA:** `fb3a96b`
```
fix(b1): wire response audit logger into /api/bot/ask
1 file changed, 13 insertions(+)
```

---

## Phase E — Verification

**Git log (post-commits):**
```
fb3a96b fix(b1): wire response audit logger into /api/bot/ask
1d0a782 chore: remove dead code (multi_query_rag, example_multi_rag) — confirmed zero imports
7151f0e chore: tighten .gitignore and untrack local agent/IDE/log artifacts
52776fb docs: P0.4 production deploy report (push + deploy + smoke test 3/3 PASS)
```

**30Q result:** **19✅ / 11⚠️ / 0❌**

| Q# | Status | Band | Top-1 article | Time (s) |
|----|--------|------|---------------|----------|
| Q01 | ✅ | HIGH | Član 210 | 23.4 |
| Q02 | ⚠️ | MEDIUM | Član 204 | 22.4 |
| Q03 | ✅ | HIGH | Član 379 | 24.2 |
| Q04 | ⚠️ | MEDIUM | Član 365 | 16.4 |
| Q05 | ✅ | HIGH | Član 208 | 21.3 |
| Q06 | ✅ | HIGH | Član 67 | 16.0 |
| Q07 | ⚠️ | MEDIUM | Član 512 | 20.3 |
| Q08 | ✅ | HIGH | Član 194 | 22.6 |
| Q09 | ✅ | HIGH | Član 19 | 13.8 |
| Q10 | ✅ | HIGH | Član 246a | 17.3 |
| Q11 | ✅ | HIGH | Član 200 | 35.1 |
| Q12 | ✅ | HIGH | Član 371 | 18.8 |
| Q13 | ✅ | HIGH | Član 124 | 14.9 |
| Q14 | ✅ | LOW | Član 69 | 8.5 |
| Q15 | ⚠️ | MEDIUM | Član 348 | 12.1 |
| Q16 | ✅ | HIGH | Član 189 | 16.6 |
| Q17 | ⚠️ | MEDIUM | Član 179 | 14.2 |
| Q18 | ⚠️ | MEDIUM | Član 21 | 13.6 |
| Q19 | ✅ | HIGH | Član 115 | 18.9 |
| Q20 | ⚠️ | MEDIUM | Član 36 | 12.3 |
| Q21 | ✅ | HIGH | Član 40 | 12.5 |
| Q22 | ✅ | HIGH | Član 160 | 16.7 |
| Q23 | ✅ | HIGH | Član 171 | 11.0 |
| Q24 | ✅ | HIGH | Član 311 | 12.8 |
| Q25 | ⚠️ | MEDIUM | Član 8 | 13.9 |
| Q26 | ✅ | HIGH | Član 446 | 11.5 |
| Q27 | ⚠️ | MEDIUM | Član 420 | 20.9 |
| Q28 | ✅ | HIGH | Član 2 | 13.6 |
| Q29 | ⚠️ | MEDIUM | Član 2 | 11.9 |
| Q30 | ⚠️ | MEDIUM | Član 231 | 12.6 |

**Comparison against b96d128 baseline (19✅/11⚠️/0❌):**

| Q# | Baseline status | Hygiene status | Baseline band | Hygiene band | Match |
|----|----------------|----------------|---------------|--------------|-------|
| Q01 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q02 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q03 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q04 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q05 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q06 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q07 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q08 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q09 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q10 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q11 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q12 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q13 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q14 | ✅ | ✅ | LOW | LOW | ✓ |
| Q15 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q16 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q17 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q18 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q19 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q20 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q21 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q22 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q23 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q24 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q25 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q26 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q27 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q28 | ✅ | ✅ | HIGH | HIGH | ✓ |
| Q29 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |
| Q30 | ⚠️ | ⚠️ | MEDIUM | MEDIUM | ✓ |

**Divergent questions:** none — 30/30 match.

Match against b96d128 baseline (19/11/0): **YES**
Status determinism: **YES**
Band determinism: **YES**
**Verdict: PROCEED TO PUSH**

---

## Phase F — Push and smoke

**Push:** SUCCESS
**Push timestamp:** 2026-05-10T10:38:xx UTC (range: 52776fb..fb3a96b)

**Render deploy:**
| Poll | Time (UTC) | Result | Consecutive |
|------|-----------|--------|-------------|
| 1 | 10:39:28 | READ TIMEOUT — server restarting | reset |
| 2 | 10:39:48 | HTTP 200 | 1/3 |
| 3 | 10:40:03 | HTTP 200 | 2/3 |
| 4 | 10:40:18 | HTTP 200 — LIVE | 3/3 |

**Wall time to live:** ~75 seconds

**Smoke test** (endpoint: `POST /api/bot/ask` with BOT_API_KEY — `/api/pitanje` requires Supabase JWT unavailable from this environment; same `ask_agent` pipeline):

| Q# | Question | Expected | HTTP | Latency | Citation | Low phrasing | Disclaimer | Pass |
|----|----------|----------|------|---------|----------|--------------|------------|------|
| Q01 | Koja je kazna za osnovnu krađu? | citation + disclaimer | 200 | 350ms | TRUE ✓ | N/A | TRUE ✓ | ✅ |
| Q14 | Da li imam pravo na regres od osiguravajućeg društva? | low phrasing + disclaimer | 200 | 302ms | N/A | TRUE ✓ | TRUE ✓ | ✅ |

Q14 low-confidence indicator: `[!] STATUSNA POTVRDA: Opšta pravna logika — nema direktnog člana u bazi za ovo pitanje.`

**Smoke: 2/2 PASS**

---

## Final Verdict

| Item | Result |
|------|--------|
| Commit 1 (.gitignore + untrack) | **APPLIED** — SHA 7151f0e |
| Commit 2 (dead code deletion) | **APPLIED** — SHA 1d0a782 |
| Commit 3 (B1 /api/bot/ask fix) | **APPLIED** — SHA fb3a96b |
| 30Q baseline preserved (19✅/11⚠️/0❌) | **YES** — 30/30 match |
| Status determinism vs baseline | **YES** |
| Band determinism vs baseline | **YES** |
| Push | **SUCCESS** |
| Production live | **YES** (~75s) |
| Smoke 2/2 PASS | **YES** |
| **Pre-Phase 1 hygiene COMPLETE** | **YES** |

---

## Notes

**example_multi_rag.py untracked:** This file was never committed to git, so `git rm` was inapplicable. It was deleted from disk with `rm`. The intent of Commit 2 (remove dead code) is fully satisfied.

**B1 gap scope:** `/api/sazmi`, `/api/feedback`, and `/api/podnesak` do not use `ask_agent` and have no compatible `rezultat` dict — the B1 audit logger pattern (`confidence`, `top_score`, `top_article`, `top_law` from `ask_agent` return) is not applicable to them. These endpoints are out of B1 scope.

**`tip=None` in bot_ask:** `klasifikuj_pitanje` is not called in `/api/bot/ask` (no user classification needed for bot pipeline). `tip=None` per task rule: use `None` for fields unavailable in the endpoint's scope.

**Q11 latency spike:** Q11 (nasilje u porodici, ZOO Član 200) took 35.1s — slower than baseline (~20s). Not a regression; occasional LLM latency variance. Benchmark still completed cleanly.

**Cache hits on smoke:** Both smoke test calls returned in ~300ms (cache hits from the 30Q benchmark run ~2 minutes earlier). Expected behavior.

**`.claude/scheduled_tasks.lock` history:** The file remains in git history (prior commits). It no longer appears as a tracked file after `git rm --cached`. Running `git rm --cached` emits `rm '.claude/scheduled_tasks.lock'` in the commit diff — this is correct behavior (removes from index, keeps on disk).
