# GPT-5.1 Cost & Performance Analysis — Program Tau, Master Sprint 001, Agent 6

**Scope**: cost/latency posture of the ~130 existing OpenAI call sites, as a basis for deciding
where a GPT-5.1 upgrade is justified vs. where the current cheaper/faster model should stay.
Analysis only — no code changed.

---

## 1. Model tiering already exists — this is not a blank slate

`routers/case_commander.py:373` makes the tiering decision explicit and readable:

```python
model = "gpt-4o" if payload.tip_analize in ("kompletna", "rizici") else "gpt-4o-mini"
```

That single line is the clearest evidence in the codebase that a "use the stronger model only when
the task actually needs it" principle is already established practice, not something Tau has to
invent. The same two-tier pattern (`gpt-4o` vs. `gpt-4o-mini`) repeats structurally across the
whole codebase — a full grep of `model="gpt-...` across `routers/`, `services/`, `shared/`,
`api.py`, `main.py`, `strategija.py`, `web3_compliance.py` found **zero** call sites using any
model other than `gpt-4o` or `gpt-4o-mini`. No `gpt-4`, no `gpt-3.5-turbo`, no `o1`/`o3` reasoning
models are actually wired in anywhere, despite `shared/cost.py:23-28`'s pricing table having
legacy entries for `gpt-4` and `gpt-3.5-turbo` — those two are dead pricing data, not live models.

Rough split by call-site count (same grep, ~150 matches across ~60 files): `gpt-4o-mini` is used
for classification/extraction/quick-check-style calls (`shared/intake_classify.py:98`,
`shared/intake_extract.py:211`, `routers/copilot.py` — 6 of its own call sites are `-mini`,
`services/case_pipeline.py` — all 3 of its calls are `-mini`), while `gpt-4o` is reserved for
synthesis/drafting/multi-step-reasoning calls (`services/legal_reasoning_engine.py:178`,
`strategija.py` — 10 of 11 calls, `court_predictor.py` — 5 of 6 calls, `drafting/router.py:55`).
This is a real, load-bearing pattern — a GPT-5.1 rollout should extend it, not flatten it.

**`shared/cost.py:23-28`'s pricing table has no GPT-5.1 entry.** `estimate_cost()` falls back to
`gpt-4o` pricing (`shared/cost.py:51`) for any unrecognized model string — meaning if GPT-5.1 were
wired in today without a pricing-table update, `api_costs` rows would silently under- or
over-report actual spend using stale GPT-4o rates rather than erroring. This is a required Phase 4
change regardless of rollout scope (see §5).

## 2. Prompt size — estimated, not measured, basis stated per site

I could not run the app to get real token counts; the estimates below are derived from reading the
actual string-concatenation code that builds each prompt, not guessed.

- **`services/legal_reasoning_engine.py:150-167`** (`_build_reasoning_prompt`-equivalent): bounded
  by construction — `context_docs[:4]` each truncated `.strip()[:500]` (`line 158`), plus fact/source
  lists that scale with Evidence Vault size but are short per-item lines. Estimated prompt ceiling:
  low thousands of tokens. This is a **deliberately context-engineered** call site, not an
  unbounded dump — relevant cross-reference for Agent 3.
- **`routers/court_predictor.py`**: 6 call sites, `max_tokens` capped at 1000-2000 per call
  (`lines 96, 291, 434, 607, 783, 931`), and 3 of them re-feed a previous result truncated to
  `[:8000]` chars (`lines 361, 717, 866, 1025`) into the next call — an **~8KB (~2000-token)
  hard ceiling per hop**, explicit and grep-verifiable, not estimated.
- **`api.py:4524-4556`**: three back-to-back GPT calls in the same code region with `max_tokens`
  ranging 600-1500 and timeouts 25-60s — flagged for Agent 3 to determine what feeds them, since
  from a cost lens alone, three sequential calls in one request path is the kind of place a
  GPT-5.1 swap would multiply both cost and latency 3x if applied uniformly.

No call site was found that appears to send full raw document text at multi-document scale without
some form of truncation or pre-summarization — but I did not exhaustively read every one of the
~60 files with GPT calls, so this is a directional finding, not a completeness claim. Agent 3
(context engineering) owns the authoritative version of this question.

## 3. Sync (user-waiting) vs. async (background) split

**Confirmed synchronous/user-facing** (request handler directly awaits the GPT call before
responding, tight timeouts 20-60s): `routers/court_predictor.py` (`timeout=25.0` on all 6 calls),
`routers/case_commander.py` (`commander_analiza`, `_ADVISORY_SYSTEM` path), `routers/copilot.py`,
`api.py:4524/4534/4556` (`timeout=60.0`/`35.0`/`25.0`).

**Confirmed background/cron/event-driven**: `routers/morning_briefing.py` — `POST
/api/briefing/cron` (`line 431-432`, docstring at `line 434` states "Poziva se iz eksternog cron
servisa svako jutro u 8:00") and `POST /api/briefing/nightly-intelligence` (`line 697`); this
whole file's GPT calls run on a schedule, not in front of a waiting user, so they can absorb
materially higher latency than the court_predictor/case_commander family without any UX cost.
`services/agent_tasks/precedents_radar.py` — named and structured as a scheduled agent task, not a
request handler.

This split matters directly for a GPT-5.1 rollout: reasoning-heavy models trade latency for
quality, so the morning_briefing/precedents_radar family is a structurally safer place to trial
higher latency than the court_predictor/case_commander family, independent of what Agent 3/5 say
about reasoning-quality fit.

## 4. Caching and batching

**No prompt/completion caching exists.** Grep for `lru_cache|redis|Redis` across the repo found
Redis used exclusively for rate limiting (`api.py:532-545`, `shared/rate.py` — SEC-005 fail-open
limiter) — there is no cache keyed on prompt hash, no `functools.lru_cache` wrapping any
`_pozovi_openai`-style function, no response cache table. Every identical or near-identical GPT
call re-executes in full, at full cost, every time.

**No OpenAI Batch API usage.** Grep for `batches.create`/`batch_api`/`.batches.` found zero matches
anywhere in the codebase. `routers/morning_briefing.py:432`'s own cron handler (which iterates
"svim korisnicima" — all users) is architecturally the single best existing candidate for Batch
API adoption (24h SLA is fine for an 06:00 UTC daily job that itself has hours of runway), but this
is a Phase 4+ candidate, not something Tau needs to build now — flagged, not implemented.

## 5. Recommendation: where GPT-5.1 is justified vs. where it isn't

**Justified (genuine multi-step reasoning over already-canonical facts, current model already the
"strong" tier)**: `services/legal_reasoning_engine.py` (Phase 0 Legal Reasoning Engine — its own
system prompt already constrains it to cite only provided `SOURCE-n` identifiers, i.e. it's already
built for exactly the "reasoning layer over deterministic facts" role Program Tau's mission
describes); `strategija.py`'s synthesis calls (10 of 11 already `gpt-4o`); `routers/court_predictor.py`
IF Agent 5/7 confirm output quality genuinely improves (cost tolerance exists — 6 calls at
1000-2000 `max_tokens` each is not a hot loop).

**Not justified — keep on a cheap/fast model or, per Sigma Sprint 005 precedent, on no model at
all**: every `gpt-4o-mini` classification/extraction call site (`shared/intake_classify.py`,
`shared/intake_extract.py`, `services/case_pipeline.py`'s 3 calls, `routers/copilot.py`'s 6 `-mini`
calls) — these are pattern-matching/extraction tasks where a reasoning model buys nothing but
latency and cost. `routers/case_commander.py`'s `commander_quick_check` and `commander_checklist`
are the strongest possible version of this argument: Sigma Sprint 005 already removed their GPT
calls entirely (zero GPT calls today) because the task turned out to need zero intelligence, only
canonical reads — the generalizable lesson for Tau is that "which model" is sometimes the wrong
question; "should this call a model at all" comes first, and Sigma 005 already answered that for 2
of the historical 8 Case Commander surfaces.

**Uniform swap risk, stated plainly**: if GPT-5.1 replaced `gpt-4o`/`gpt-4o-mini` everywhere
mechanically, the two biggest concrete risks visible from this analysis are (a) `api_costs`
under/over-reporting silently via the missing pricing-table entry (§1), and (b) the tight
20-25s timeouts on the synchronous court_predictor/copilot/case_commander family — if GPT-5.1's
real-world reasoning latency exceeds those budgets even some of the time, users see request
timeouts on paths that work reliably today. Neither risk requires a full audit to fix, but both
must be addressed in Phase 4 for whatever scope is actually approved.
