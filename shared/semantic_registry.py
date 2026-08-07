# -*- coding: utf-8 -*-
"""
Vindex AI — shared/semantic_registry.py

Operation Singular Intelligence, Mission 001 (2026-08-07) — "The Semantic Truth Layer".

This is NOT a new intelligence/scoring engine (explicitly forbidden by this mission's own Core
Rules 1-3). It is a machine-readable index of `docs/singular/TRUTH_CONTRACT.md` — for each
canonical concept, which module owns it, what raw string values it may take, what older/renamed
field names are known aliases of it, and where its definition lives. Nothing here computes
anything; every function is a pure lookup.

Purpose: let code (and tests) ask "who owns Risk?" or "is 'SREDNJI' a valid value for Web3's
skor_nivo?" without re-deriving the answer from scattered comments across a dozen files, and let a
future engineer discover a NEW independent computation of an already-owned concept mechanically
(register it here, and any code path producing an un-registered value for an owned concept is a
Truth Contract violation by definition).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConceptOwnership:
    concept: str
    owner: str                      # "module.py::function_name"
    input_description: str
    output_shape: str
    allowed_values: tuple[str, ...] | None  # None = numeric/unstructured, not an enum
    forbidden: str                  # what MUST NOT happen for this concept
    deprecated_aliases: tuple[str, ...] = field(default_factory=tuple)
    truth_contract_ref: str = ""    # section anchor in docs/singular/TRUTH_CONTRACT.md


# ─── Registry ──────────────────────────────────────────────────────────────────

RISK = ConceptOwnership(
    concept="risk",
    owner="services/risk_engine.py::calculate_procesni_rizik",
    input_description="predmet_dokazi (soft-delete-filtered), predmet_dokumenti, rocista, case type, expected-document schedule",
    output_shape='{"nivo": str, "health_score": int, "nedostajuci_dokazi": list, "predstojeći_rokovi": int, "kriticni_rocista": list}',
    allowed_values=("Nizak", "Srednji", "Visok"),
    forbidden="Any other module independently computing case risk. GPT may never author this value. "
              "Callers MUST use a deleted_at-filtered evidence set (violated once by routers/zadaci.py, fixed Mission 001).",
    deprecated_aliases=("predmeti.rizik (manual note, NOT this concept)", 'predmet_istorija "[Rizik]" cache (historical snapshot only)'),
    truth_contract_ref="#risk",
)

READINESS = ConceptOwnership(
    concept="readiness",
    owner="shared/case_readiness.py::compute_case_readiness",
    input_description="case_actions (open rows only), Gap Engine hypothesis-only findings",
    output_shape='{"status": str, "razlog": str, "izvor": list}',
    allowed_values=("READY", "PARTIALLY_READY", "BLOCKED", "CRITICAL_GAP", "UNKNOWN"),
    forbidden="GPT may never author this value (no injectable parameter exists). No other module may "
              "independently classify case readiness.",
    deprecated_aliases=(),
    truth_contract_ref="#readiness",
)

STRENGTH = ConceptOwnership(
    concept="strength",
    owner="shared/genome_validator.py::compute_snaga_score",
    input_description="case_dna.snaga_faktori (Genome-extracted)",
    output_shape='{"snaga_predmeta_procent": int, "snaga_predmeta": str, "snaga_faktori": list}',
    allowed_values=("jaka", "srednja", "slaba"),
    forbidden="GPT's own raw snaga_predmeta_procent self-report may never be trusted directly. "
              "MUST NOT be displayed using Risk's vocabulary ('rizik') -- these are different concepts "
              "(violated once by the Genome hero panel, fixed Mission 001, static/vindex.js).",
    deprecated_aliases=(),
    truth_contract_ref="#strength",
)

PRIORITY = ConceptOwnership(
    concept="priority",
    owner="case_actions.prioritet (migration 099, DB-enforced enum)",
    input_description="services/case_evolution.py::_compute_target_actions (sole writer)",
    output_shape="case_actions row; translated for display via shared/attention_priority.py",
    allowed_values=("critical", "high", "medium", "low", "informational"),
    forbidden="Any module computing its own priority/urgency classification instead of reading "
              "case_actions.prioritet through the canonical translator.",
    deprecated_aliases=("routers/copilot.py::_handle_predlozi's own scheme (SINGULAR-DEBT-001)",
                          "routers/zastarelost.py's own thresholds (SINGULAR-DEBT-004)"),
    truth_contract_ref="#priority--urgency",
)

RECOMMENDATION = ConceptOwnership(
    concept="recommendation",
    owner="shared/case_readiness.py::top_open_action",
    input_description="case_actions' own already-canonical priority-ordered open rows",
    output_shape='{"tip": str, "prioritet": str, "razlog": str, "rok": str|None, "dedupe_key": str}',
    allowed_values=None,
    forbidden="A GPT narrative presenting itself as 'what to do today' without either (a) being "
              "unconditionally overwritten from this function's output before reaching the UI, or "
              "(b) carrying an explicit, visible disclosure that it is an independent AI suggestion.",
    deprecated_aliases=("health_index.py::_compute_chief_partner (disclosed, not consolidated, Mission 001)",
                          "routers/cio.py's cio_preporuka (disclosed, not consolidated, Mission 001)",
                          "services/case_pipeline.py::_step_copilot_preporuka (SINGULAR-DEBT-001)"),
    truth_contract_ref="#recommendation-what-should-the-lawyer-do--new-in-this-contract",
)

HEALTH_FIRM = ConceptOwnership(
    concept="health (firm-wide)",
    owner="routers/health_index.py::_compute_health",
    input_description="portfolio risk/strength/billing/activity, deterministic weighted sum",
    output_shape='{"score": int, "grade": str, "components": list, "iz_kesa": bool, "generated_at": str}',
    allowed_values=None,
    forbidden="A 3rd independently-computed 'firm health' meaning. A cached response MUST disclose "
              "iz_kesa/generated_at (violated once, fixed Mission 001).",
    deprecated_aliases=("web3_compliance.py's Documentation Health Score (unrelated concept, naming collision only)",),
    truth_contract_ref="#health",
)

HEALTH_PER_CASE = ConceptOwnership(
    concept="health (per-case)",
    owner="services/risk_engine.py::calculate_procesni_rizik (health_score field)",
    input_description="same as RISK",
    output_shape="int 0-100, inverse of risk",
    allowed_values=None,
    forbidden="A 2nd independently-computed per-case health number.",
    deprecated_aliases=(),
    truth_contract_ref="#health",
)

CONFIDENCE = ConceptOwnership(
    concept="confidence",
    owner=None,  # legitimately ~16 distinct mechanisms, no single owner -- see Truth Contract
    input_description="varies per mechanism (RAG grounding, completeness proxy, self-declared analysis confidence, calibration bands, ...)",
    output_shape="varies",
    allowed_values=("visoka", "srednja", "niska"),  # the Serbian 3-tier vocabulary most mechanisms share
    forbidden="A GPT self-declared confidence value reaching lawyer UI without enum-validation against "
              "its documented value set, fail-safe toward the least confident bucket for unrecognized input.",
    deprecated_aliases=(),
    truth_contract_ref="#confidence",
)

WEB3_COMPLIANCE_SCORES = ConceptOwnership(
    concept="web3_compliance_score",
    owner="web3_compliance.py::mica_readiness_score_sync / zdi_license_checker_sync / aml_kyc_auditor_sync / documentation_health_score_sync",
    input_description="user-submitted project/policy/documentation description",
    output_shape='{"ukupni_skor"|"ukupna_uskladenost": int 0-100, "skor_nivo"|"uskladenost_nivo"|"rizik_nivo": str}',
    allowed_values=("NIZAK", "SREDNJI", "VISOK"),
    forbidden="Raw GPT JSON reaching lawyer/client UI without server-side clamp (0-100) and enum "
              "validation (fail-safe direction depends on scale: risk scales fail safe to VISOK, "
              "goodness/compliance scales fail safe to NIZAK -- see web3_compliance.py::_guard_web3_score). "
              "Violated for all 4 scores, fixed Mission 001.",
    deprecated_aliases=(),
    truth_contract_ref="",  # regulatory-compliance domain, documented in SEMANTIC_MAP.md not TRUTH_CONTRACT.md's case-vocabulary sections
)


ALL_CONCEPTS: tuple[ConceptOwnership, ...] = (
    RISK, READINESS, STRENGTH, PRIORITY, RECOMMENDATION, HEALTH_FIRM, HEALTH_PER_CASE,
    CONFIDENCE, WEB3_COMPLIANCE_SCORES,
)


def get_owner(concept_name: str) -> ConceptOwnership | None:
    """Pure lookup -- returns the ConceptOwnership record for a concept name, or None."""
    for c in ALL_CONCEPTS:
        if c.concept == concept_name:
            return c
    return None


def is_valid_value(concept_name: str, value: str) -> bool:
    """Pure lookup -- True if `value` is in the concept's documented allowed_values, or if the
    concept has no fixed enum (allowed_values=None, e.g. numeric scores)."""
    c = get_owner(concept_name)
    if c is None or c.allowed_values is None:
        return True
    return value in c.allowed_values
