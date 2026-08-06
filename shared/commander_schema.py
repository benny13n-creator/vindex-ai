# -*- coding: utf-8 -*-
"""
Vindex AI — shared/commander_schema.py

Program Sigma, Master Sprint 005 (2026-08-06) — "Case Commander Consolidation &
Operational Brain Unification". Phase 3's own required deliverable:
CASE_COMMANDER_RESPONSE_SCHEMA — one shape every piece of information
`routers/case_commander.py` returns must carry, so "nijedan AI odgovor ne sme
postojati bez porekla" (no AI answer may exist without provenance) is enforced
structurally, not by convention.

Every field: {value, source, evidence, confidence, generated_by, timestamp}.

- `source`: which system decided this — "case_actions" | "gap_engine" |
  "case_readiness" | "identify_case_problems" | "rocista" | "gpt_advisory".
  "gpt_advisory" is the ONLY GPT-attributed source this schema allows for a
  FINDING (as opposed to an explanation) — see gpt_boundary_field() below.
- `evidence`: the traceable origin — a `case_actions.dedupe_key`, a Gap
  record's own `dedupe_key`, a `rocista.id`, or None only when `source` is
  itself "gpt_advisory" (an unconfirmed hypothesis, by definition has no
  deterministic evidence yet).
- `confidence`: "visoka" | "srednja" | "niska" — mirrors
  shared/gap_engine.py's own vocabulary, not a GPT-invented percentage
  (Program Sigma Sprint 004's own Phase 5 rule, "prioritet ne sme biti GPT
  broj", extended here to confidence).
- `generated_by`: "deterministic" for anything computed without an LLM call,
  or the exact model name ("gpt-4o"/"gpt-4o-mini") when GPT produced it.
- `timestamp`: ISO-8601, when THIS field was computed (not request time in
  general — lets a caller tell a stale cached field from a fresh one).
"""
from __future__ import annotations

from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_field(value, source: str, evidence=None, confidence: str = "visoka") -> dict:
    """A field sourced from a deterministic, already-canonical system --
    case_actions, gap_engine, case_readiness, identify_case_problems, rocista.
    `generated_by` is always "deterministic" -- no LLM call produced this
    value, only formatted/read it."""
    return {
        "value": value,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
        "generated_by": "deterministic",
        "timestamp": _now_iso(),
    }


def gpt_advisory_field(value, model: str, confidence: str = "niska") -> dict:
    """A field that is GENUINELY GPT-only -- no canonical system computes
    this today (e.g. 'what will opposing counsel likely do', or a
    cross-document contradiction no deterministic system checks for).
    `source` is always "gpt_advisory" and `evidence` is always None --
    marking, structurally, that this is a hypothesis, never a fact (Program
    Sigma Sprint 003's own "hipoteza, ne činjenica" rule, applied here to
    Case Commander). Per this sprint's own Phase 4 (GPT Boundary Policy),
    this function must NEVER be used for an action/priority/readiness-status
    field -- only for genuinely-advisory narrative content."""
    return {
        "value": value,
        "source": "gpt_advisory",
        "evidence": None,
        "confidence": confidence,
        "generated_by": model,
        "timestamp": _now_iso(),
    }


def gpt_explanation_field(value, model: str, of_source: str, of_evidence=None) -> dict:
    """A field where GPT explained/summarized/rephrased an ALREADY-canonical
    fact (Phase 4's own "GPT može: objasniti, sažeti, preformulisati").
    `source`/`evidence` point at the ORIGINAL canonical fact GPT was
    explaining, not at GPT itself -- the explanation doesn't change what's
    true, only how it's phrased. `generated_by` records that GPT did the
    phrasing, so a caller can still tell "this exact wording came from an
    LLM call" apart from a purely templated string."""
    return {
        "value": value,
        "source": of_source,
        "evidence": of_evidence,
        "confidence": "visoka",
        "generated_by": model,
        "timestamp": _now_iso(),
    }
