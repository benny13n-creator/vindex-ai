# AI Failure Report — Program Lambda, Certification 004

**Agent**: AI Systems Reliability Engineer, with fixes implemented by the coordinator and adversarially
re-attacked in Phase 6.

## Finding 1 — CRITICAL, FIXED: Case Genome refresh destroyed live data on ANY GPT failure

**The single most severe finding of this sprint.** `routers/case_dna.py::_do_genome_refresh`:
`_extract_genome` correctly catches every GPT failure mode (timeout, malformed JSON, empty response) into a
clean `{"greska": str(exc)}` signal, never raising. But the caller wrote that signal **unconditionally** to
the live `predmeti.case_dna` column — a full-value JSON replace, not a merge — destroying every existing
Genome field (`kljucne_cinjenice`, `snaga_predmeta_procent`, `kontradikcije`, `nedostaje`, deadlines,
everything) for every downstream consumer (Court Predictor, Digital Twin, CIO, Copilot, `build_case_context()`)
until the next successful refresh. The version number was even incremented on failure. A transient OpenAI
hiccup left a case **less usable after a failed refresh than before it** — the direct opposite of this
mission's own Scenario 3 requirement ("case remains usable, no fake completion").

**Fix**: all steps after the existing-but-too-narrow verification guard (write, history save, event emit,
delta/alert, require-review) now share one unified early-return on failure — nothing about the live case is
touched, only a clear log line records the failure. **Phase 6 adversarial re-attack** found one low-probability
edge case in the guard itself (`genome.get("greska")` truthiness vs. key presence — an exception with an
empty message string would slip through) and it was closed at zero cost (`"greska" in genome`).

**Status: FIXED.** Proof: `tests/test_ztc_genome_scale_and_race.py` (2 new tests: failure never writes/never
calls history-save/emit/review; success still writes exactly as before), `tests/test_case_dna_events.py`
(1 pre-existing test corrected to assert the stronger, complete guarantee — it previously only checked
verification was skipped while the destructive write/emit still went through, which was itself the exact gap
this fix closes).

## Finding 2 — FIXED: Map-Reduce contract analysis silently presented partial failure as completeness

`main.py`'s Map-Reduce orchestration (`_map_analiziraj_batch`/`_ask_analiza_v2_map_reduce`/`_reduce_analiza`):
a batch that raised during MAP was substituted with an empty-but-valid-shaped result, indistinguishable from
a batch that genuinely found nothing risky. A lawyer reviewing a contract analysis had no signal a segment
was silently dropped.

**Fix**: `_map_analiziraj_batch` (which never raises, by its own design) now returns an internal `_batch_failed`
marker on its own caught exception; the caller collects failed indices into `partial_failure`/`failed_batches`
fields surfaced in the final report. **Phase 6 adversarial re-attack** confirmed multiple simultaneous
failures are all captured correctly (unique index per batch, no collision), and confirmed the `ordered[idx]
is None` fallback path is structurally unreachable dead code (not a live gap) — `as_completed` yields every
submitted future exactly once, every branch assigns `ordered[idx]` unconditionally.

**Note on this fix's own implementation history**: the coordinator's FIRST attempt targeted the wrong swallow
point (the outer `except Exception` in `_ask_analiza_v2_map_reduce`, which can never actually fire since
`_map_analiziraj_batch` never raises by design) — caught immediately by the coordinator's own new regression
test failing, corrected before being reported as done.

**Status: FIXED.** Proof: `tests/test_akcija2_faza4_2026_07_24.py` (2 tests extended — the existing
"one batch fails" test now asserts `partial_failure is True`/`len(failed_batches)==1`; the existing clean-run
test now asserts `partial_failure is False`/`failed_batches==[]`).

## Finding 3 — named as debt, not fixed: zero explicit timeout across ~63 OpenAI client sites

Repo-wide grep confirms no file passes `timeout=` to `OpenAI()`/`AsyncOpenAI()` construction or any individual
`.create()` call. SDK default (`openai==2.29.0`): up to 10 minutes per attempt, plus the SDK's own internal
`max_retries=2` sitting underneath `shared/llm_retry.py`'s own 3 application-level attempts — a materially
longer and less predictable worst-case latency than the retry decorator's own "max 3 attempts" framing
implies.

**Why not fixed this sprint**: choosing a single blanket timeout value across ~63 heterogeneous call sites
(a quick classification call vs. a large Map-Reduce synthesis call have very different realistic latency
needs) without production latency-distribution data is exactly the "guessing a number" pattern this
engagement has repeatedly and correctly refused to do (`LAMBDA-001`'s own precedent for the Supabase client
timeout). Named in `LAMBDA004_HANDOVER.md` as the highest-leverage next step for a dedicated follow-up sprint,
not guessed at here.

## Everything else — CERTIFIED, with fresh evidence

- `shared/llm_retry.py::llm_retry` — correctly retries only transient error types, `reraise=True`, never
  silently swallows a final failure. Confirmed still present on `strategy_simulator.py::_pozovi_gpt` (the one
  file historically found missing it, fixed in Lambda 001).
- The deterministic-cap GPT-boundary pattern (Court Predictor, Hearing CC, Digital Twin, CIO) — re-verified
  fresh: JSON parse failure, GPT unavailability after retry exhaustion, and any other exception are all caught
  by an outer handler producing an honest error response, never a fake success. Credit consumption happens
  only after successful parse — no billing-on-failure.
- `shared/genome_validator.py::validate_predmet_reference` — re-confirmed present, rejects a hallucinated case
  reference not in the caller's own pre-scoped known set.
