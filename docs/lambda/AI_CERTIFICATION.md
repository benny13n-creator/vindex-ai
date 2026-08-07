# AI_CERTIFICATION — Program Lambda, Certification 008

Covers Team 6 (AI Governance). 23 GPT call sites inspected. Mandate: for every AI output a lawyer might
trust as fact, can the model currently fabricate a fact, change a priority/risk number, invent a citation,
or silently alter a stored value with no downstream check catching it before the lawyer acts on it?

## Finding — fixed this sprint

**`services/ambient_analyzer.py`** (the Word/browser live-typing copilot) suggested legal citations
(`clan_zakona`/`sudska_praksa`) to a lawyer while drafting, guarded only by a system-prompt instruction
("nikad ne izmišljaj broj člana van dobijenog konteksta") — never verified in code against the RAG context
actually sent. Fixed via a new `_izvor_potkrepljen` grounding check: every numeric citation token in a
suggestion's `izvor` field must actually appear in the RAG text the model was given, or the suggestion is
dropped before it reaches the lawyer's document. Deliberately number-based, not full-string matching — GPT
legitimately paraphrases a law's name ("ZR čl. 179" for context reading "Zakon o radu, čl. 179"), and an
exact-substring requirement would reject correctly-grounded citations as readily as fabricated ones. The
number is the concrete, checkable, hallucination-prone part the system prompt itself names.
`upozorenje`-type suggestions (flagging a problem in the paragraph itself) are exempt — they're not a legal
citation and don't need RAG grounding per the prompt's own design.

## 2 prior debt-register claims found stale, corrected

- **`SENT-005`** ("copilot.py chat has NO grounding/citation check at all") — this is no longer accurate.
  `main.py::ask_agent` has a real hard-refusal guard: if a user cites "Član N" and it's not in the corpus,
  GPT is never called and a refusal is returned instead, with confidence-banding gating low-confidence
  answers before generation. The real remaining gap narrows to `_handle_analiza_predmeta`/
  `_handle_plan_predmeta`'s free-text fields only.
- **`NEX-007`** ("Genome/Briefing trust GPT-4o on prompt instruction alone") — also stale. Both now compute
  their canonical numbers deterministically, and Genome has its own `genome_validator.py::verify_genome()`
  grounding layer wired into the UI. The real remaining gap is narrower: a `"require_review"` verdict never
  blocks the write — a flagged-as-suspect Genome still saves and displays, gated only by a UI badge a lawyer
  could ignore.

## Re-confirmed still open, unchanged

- `PROGBETA-003` (Strategy Engine/Genome citation verification — the same unfixed-citation-check pattern
  this sprint's ambient_analyzer.py fix closes, but at Strategy Engine/Genome's own call sites).
- `PROGBETA-005` (`_handle_akcija_rok`/`_handle_akcija_beleska` GPT date-extraction writes straight to
  `predmet_hronologija` with no confirmation step).

## Verified sound, no new issue found

`shared/ai_client.py`'s provenance-capture interception layer (model/prompt-hash/tokens/latency/output-hash)
captures 100% of AI calls structurally, even on failure. Error handling across the 23 inspected call sites
does not systemically substitute a fabricated value into a canonical field on OpenAI failure — the one real
failure-path gap found this sprint (credit not refunded on `/api/pitanje` error) is a billing-correctness
issue, covered in `RELIABILITY_CERTIFICATION.md`, not an AI-governance one.

**Verdict**: 1 new AI governance gap found and fixed this sprint (ambient copilot citation grounding), out
of 23 call sites checked. 2 stale debt-register claims corrected to reflect genuinely-improved current code
— the platform's AI safety posture is materially better than 2 prior tracked items described, though 2
narrower real gaps remain in each area, both already tracked, neither newly discovered.
