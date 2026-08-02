# AI Design Review — [Feature Name]

**Author (role):** AI System Architect
**Date:**

## Provider & Payload
Exactly which provider(s) (OpenAI / Pinecone / others), exactly what payload (not "the question" —
the full assembled prompt including any retrieved context). Cross-check
`docs/security/PUBLIC_SECURITY_CLAIMS.md` and the subprocessor disclosure list — does this
introduce an undisclosed subprocessor (the SEC-051 failure mode)?

## Necessity Check
Is this genuinely necessary AI usage, or would a deterministic computation do? Per this project's
Deterministic Intelligence Framework: the LLM proposes, the backend computes the numbers.

## Chokepoint Coverage
Does this call path go through the existing prompt-injection guard
(`shared/ai_client.py::_patch_prompt_guard`, chat-completions only as of the last audit), or a
surface not yet covered (embeddings/audio/Realtime — see
`docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` §1.1)? State explicitly, do not
assume coverage.

## PII Handling
Does this call path route case-document text or party information? If so, does it call
`main.py::_skini_pii` (or its eventual Program 1 Classification-stage successor)? Note: the Case
Genome/Legal Reasoning Engine path currently does NOT (SEC-006, confirmed open) — do not assume
parity with that path.

## Duplication Check
Does this duplicate Case Genome's or the Legal Reasoning Engine's job? Per
`docs/architecture/VINDEX_CORE_CONSOLIDATION.md`.

## Cost & Abuse Surface
Rate limiting, input size bound, credit/usage metering (`UsageService`) — stated explicitly, not
assumed present.

## Hallucination / Wrong-Output Risk
What downstream system could treat a wrong AI output as ground truth? What's the evaluation plan
(LEC-based or otherwise)?

## Verdict
APPROVED / APPROVED WITH CONDITIONS / BLOCKED.
