# -*- coding: utf-8 -*-
"""
Vindex AI — shared/contradiction_identity.py

Program Sigma, Master Sprint 002 (2026-08-06) — "Autonomous Evidence & Timeline
Reconstruction Engine". ONE canonical stable-identity function for a Genome-extracted
contradiction (`case_dna.kontradikcije[]` item), used by BOTH consumers that need to
recognize "is this the SAME contradiction as before" across independent Genome
refreshes — `routers/case_dna.py::_compute_delta` and
`services/case_evolution.py::_compute_target_actions`'s own Rule 3
(`RAZRESITI_KONTRADIKCIJU`). One shared function, not two independent patches — this
sprint's own founding principle ("nije dozvoljeno pravljenje paralelnih algoritama").

## The bug this closes

Both consumers previously derived identity (a `set()` membership key in `_compute_delta`,
a `case_actions.dedupe_key` in Rule 3) from the contradiction's own free-text `opis` field
— GPT-generated prose describing what the contradiction IS, re-extracted fresh on every
Genome refresh (not a diff of the model's own prior output). Any rephrasing of the
IDENTICAL underlying contradiction between 2 refreshes produced a different `opis` string,
which:
  - made `_compute_delta` report a false "1 eliminated + 1 new" churn (SIGMA-002, Sprint 001
    Architectural Debt Register), and
  - made Rule 3's own reconcile loop (`_consequence_refresh_case_actions`) see the old
    `dedupe_key` as gone (closes that `RAZRESITI_KONTRADIKCIJU` action) and the new
    `dedupe_key` as new (creates a fresh one) — a LIVE functional bug, not just an alert-
    accuracy gap: the SAME open action would flicker closed+reopened across every Genome
    refresh, confirmed by direct code reading this sprint (`services/case_evolution.py`'s
    own `_stable_key("kontradikcija", opis, loc1, loc2)` — `opis` was part of the hash).

## The fix

Genome's own extraction prompt ALREADY REQUIRES every contradiction to carry a
`lokacija_1`/`lokacija_2` source citation (`routers/case_dna.py`'s own extraction prompt,
"DOK-XX str.Y" format) — formulaic document+page references, not free prose. As long as the
SAME 2 source locations are still in conflict, these citations are stable across refreshes
even when GPT phrases the surrounding `opis` differently. Identity is therefore anchored on
`(lokacija_1, lokacija_2)` (order-independent — GPT is not guaranteed to always cite them in
the same order), falling back to `opis` only when NEITHER location is present (a defensive
edge case Genome's own prompt is not supposed to produce, but not assumed impossible).

This does NOT touch the GPT extraction prompt/contract at all — only how the ALREADY-
extracted fields are used for downstream identity matching. Safe, deterministic, no live
model-behavior change.
"""
from __future__ import annotations

import hashlib


def contradiction_identity(k: dict) -> tuple[str, str]:
    """Returns a stable, order-independent (a, b) identity tuple for one
    `case_dna.kontradikcije[]` item. Two dicts describing the same underlying
    contradiction (same 2 source locations) produce the same tuple, regardless of
    how differently `opis` is worded between calls."""
    loc1 = (k.get("lokacija_1") or "").strip()
    loc2 = (k.get("lokacija_2") or "").strip()
    if loc1 or loc2:
        return tuple(sorted((loc1, loc2)))
    # Defensive fallback -- Genome's own prompt requires locations, but never
    # assume upstream data is always well-formed. Falls back to the free-text
    # opis (the pre-fix behavior) only for this edge case, not the common path.
    return ((k.get("opis") or "").strip(), "")


def contradiction_dedupe_key(k: dict) -> str:
    """The `case_actions.dedupe_key` for a RAZRESITI_KONTRADIKCIJU action --
    same identity as `contradiction_identity`, hashed to match every other
    `_stable_key`-derived dedupe_key's own 24-char hex shape
    (services/case_evolution.py)."""
    a, b = contradiction_identity(k)
    return hashlib.sha256(f"kontradikcija|{a}|{b}".encode("utf-8")).hexdigest()[:24]


_VALID_TEZINE = ("kriticna", "vazna", "manja")


def normalize_tezina(raw) -> str:
    """Operation Single Brain (2026-08-07), AI Boundary gap #1-2: `tezina` is a raw
    GPT classification (Genome's extraction prompt asks for exactly "kriticna|vazna|
    manja") that TWO independent consumers each mapped onward with their own silent
    "unrecognized -> middle bucket" default (`services/case_evolution.py`'s Rule 3 ->
    case_actions.prioritet, `shared/gap_engine.py` -> Gap.pouzdanost) -- neither
    validated the raw string was actually one of the 3 values GPT was asked for before
    trusting it. A GPT paraphrase or synonym for "kriticna" (e.g. "ozbiljna",
    "vrlo vazna") would silently fall through BOTH mappings to the neutral/medium
    bucket, keeping a genuinely critical contradiction out of BLOCKED readiness
    (shared/case_readiness.py requires prioritet=="high" for that path) and out of
    the "visoka" confidence gap bucket -- invisibly, not loudly.

    One canonical normalizer, used by every consumer: unrecognized input is treated
    as "kriticna" (the most conservative bucket, not the middle one) -- for a legal
    risk signal, under-flagging is the worse failure mode than over-flagging.

    Also tolerates a non-string `raw` (Phase 4 adversarial testing found `(raw or "").
    strip()` crashes outright if GPT's JSON ever puts a bare number/bool/list where a
    string was asked for -- not hypothetical for un-schema-enforced JSON output)."""
    if not isinstance(raw, str):
        return "kriticna"
    t = raw.strip().lower()
    return t if t in _VALID_TEZINE else "kriticna"
