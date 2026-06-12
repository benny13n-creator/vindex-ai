# -*- coding: utf-8 -*-
"""
Sloj 3 (backend) — Validation + Post-processing pipeline

1. parse_llm_response()       — strip fences, json.loads, 1 retry
2. validate_clause_excerpts() — excerpt substring provera
3. validate_clause_refs()     — clause_ref postoji u segmentima
4. compute_executive_summary() — backend risk score formula
5. validate_law_refs()        — soft check poznatih zakona

Hallucination Firewall: failed → finding se premešta u low_confidence_findings,
nikad se ne briše u tišini.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Optional

from analiza.segmenter import SegmentedDocument

logger = logging.getLogger(__name__)

# ─── Poznati zakoni iz Pinecone korpusa ──────────────────────────────────────

_POZNATI_ZAKONI = frozenset({
    "ZR", "ZOO", "ZPP", "ZPDG", "ZZPL", "USTAV", "ZN", "PZ",
    "ZSPNFT", "ZDI", "KZ", "ZKP", "ZIO", "ZOS", "ZVP", "ZGZ",
    # Stem matching: kratim na koren koji pokriva i nominativ i genitiv i instrumental
    "zakon o rad",           # zakon/zakona/zakonom o radu
    "zakon o obligacion",    # zakon o obligacionim odnosima
    "zakon o parnic",        # zakon o parničnom postupku
    "zakon o porezima",      # zakon o porezima na dohodak
    "zakon o zastit",        # zakon o zaštiti podataka
    "zakon o zas",           # variante
    "ustav repub",           # ustav republike srbije
    "porodic",               # porodični zakon
    "zakon o nasled",        # zakon o nasleđivanju
    "zakon o digital",       # zakon o digitalnoj imovini
    "zakon o sprec",         # zakon o sprečavanju pranja
    "zakon o izvrs",         # zakon o izvršenju i obezbeđenju
    "zakon o obezbed",
    "zakon o obligacionim prav",
    "zakon o radu",
    "zakona o radu",         # genitiv
    "zakonom o radu",        # instrumental
})

# ─── Severity score mapa (Sloj 3) ────────────────────────────────────────────

_SEVERITY_SCORES: dict[str, int] = {
    "nizak":    20,
    "srednji":  50,
    "visok":    80,
    "kritican": 100,
    "kritičan": 100,
}

_SEVERITY_WEIGHTS: dict[str, float] = {
    "nizak":    0.2,
    "srednji":  0.5,
    "visok":    0.8,
    "kritican": 1.0,
    "kritičan": 1.0,
}


# ─── 1. parse_llm_response ───────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    # Strip ``` fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    # Strip preambula pre prve {
    brace = raw.find("{")
    if brace > 0:
        raw = raw[brace:]
    return raw.strip()


def _extract_legacy_text(raw: str) -> str:
    """Pokušava da izvuče plain-text analizu iz sirovog LLM odgovora ako JSON parse ne uspe."""
    return raw.strip()[:3000]


def parse_llm_response(
    raw_text: str,
    retry_fn=None,   # callable() → str za drugi pokušaj
) -> tuple[dict, bool]:
    """
    Parsira LLM odgovor u dict.

    Returns:
        (parsed_dict, is_fallback) — is_fallback=True ako je JSON parse podbacio.
    """
    cleaned = _strip_fences(raw_text)
    try:
        return json.loads(cleaned), False
    except json.JSONDecodeError:
        logger.warning("[VALIDATOR] JSON parse fail na prvom pokušaju, len=%d", len(cleaned))

    # Jedan retry
    if retry_fn is not None:
        try:
            raw2 = retry_fn()
            cleaned2 = _strip_fences(raw2)
            return json.loads(cleaned2), False
        except (json.JSONDecodeError, Exception) as e:
            logger.error("[VALIDATOR] JSON parse fail i na drugom pokušaju: %s", e)

    # Fallback — vraća strukturu sa legacy_text
    fallback = {
        "document_type": "ostalo",
        "executive_summary": None,
        "findings": [],
        "missing_clauses": [],
        "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [],
        "low_confidence_findings": [],
        "legacy_text": _extract_legacy_text(raw_text),
        "_parse_error": True,
    }
    return fallback, True


# ─── Normalizacija za substring matching ─────────────────────────────────────

def _normalize_ws(s: str) -> str:
    """Normalizuje whitespace i Unicode za substring matching."""
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()


# ─── 2. validate_clause_excerpts ─────────────────────────────────────────────

def validate_clause_excerpts(parsed: dict, segmented_doc: SegmentedDocument) -> dict:
    """
    Za svaki finding proverava da li clause_excerpt postoji kao substring
    u full_text dokumenta (case-insensitive, whitespace-normalized).
    Nevalidni → premesti u low_confidence_findings.
    """
    findings = parsed.get("findings", [])
    low_conf = parsed.get("low_confidence_findings", [])
    full_norm = _normalize_ws(segmented_doc.full_text)

    valid_findings = []
    for f in findings:
        excerpt = (f.get("clause_excerpt") or "").strip()
        if not excerpt:
            valid_findings.append(f)
            continue

        excerpt_norm = _normalize_ws(excerpt)
        # Strip trailing ellipsis (GPT often appends "..." to indicate truncation)
        excerpt_norm = re.sub(r'\.{2,}$|…$', '', excerpt_norm).rstrip()
        # Uzmi samo prvih 100 znakova za matching (da se ne kaznjavaju legitimni dugi citati)
        excerpt_short = excerpt_norm[:100]

        if excerpt_short and excerpt_short not in full_norm:
            logger.warning(
                "[VALIDATOR] excerpt_not_found: finding_id=%s excerpt=%r",
                f.get("id"), excerpt[:60]
            )
            low_conf.append({
                "raw_observation": f.get("finding", ""),
                "confidence": f.get("confidence", 0),
                "reason_excluded": "excerpt_not_found_in_source",
                "original_finding": f,
            })
        else:
            valid_findings.append(f)

    parsed["findings"] = valid_findings
    parsed["low_confidence_findings"] = low_conf
    return parsed


# ─── 3. validate_clause_refs ─────────────────────────────────────────────────

def validate_clause_refs(parsed: dict, segmented_doc: SegmentedDocument) -> dict:
    """
    Proverava da clause_ref postoji u segmentima.
    None/null je OK. Nepostojeći ID → low_confidence_findings.
    """
    segment_ids = {s.id for s in segmented_doc.segments if s.start_offset >= 0}
    findings = parsed.get("findings", [])
    low_conf = parsed.get("low_confidence_findings", [])

    valid_findings = []
    for f in findings:
        ref = f.get("clause_ref")
        if ref is None or ref in segment_ids:
            valid_findings.append(f)
        elif ref and ref not in segment_ids:
            # Soft: probaj case-insensitive match
            ref_lower = ref.lower()
            if any(sid.lower() == ref_lower for sid in segment_ids):
                valid_findings.append(f)
            else:
                logger.warning("[VALIDATOR] invalid clause_ref: %r (id=%s)", ref, f.get("id"))
                low_conf.append({
                    "raw_observation": f.get("finding", ""),
                    "confidence": f.get("confidence", 0),
                    "reason_excluded": f"invalid_clause_ref:{ref}",
                    "original_finding": f,
                })
        else:
            valid_findings.append(f)

    parsed["findings"] = valid_findings
    parsed["low_confidence_findings"] = low_conf
    return parsed


# ─── 4. compute_executive_summary ────────────────────────────────────────────

def compute_executive_summary(parsed: dict) -> dict:
    """
    Sloj 10 — Executive Summary se računa backend-om, ne traži se od LLM.

    Formula za overall_risk_score:
      weighted_avg(severity_scores, weights) capped at 100
      weights: kritican=1.0, visok=0.8, srednji=0.5, nizak=0.2
    """
    findings = parsed.get("findings", [])
    missing  = parsed.get("missing_clauses", [])
    fin_exp  = parsed.get("financial_exposure", {}) or {}
    litig    = parsed.get("litigation_readiness", {}) or {}

    # Mapiranje severity → score
    for f in findings:
        sev = (f.get("severity") or "").lower()
        f["severity_score"] = _SEVERITY_SCORES.get(sev, 20)

    # Weighted avg risk score
    overall_score = 0
    if findings:
        total_weight = sum(_SEVERITY_WEIGHTS.get((f.get("severity") or "").lower(), 0.2) for f in findings)
        if total_weight > 0:
            weighted_sum = sum(
                f["severity_score"] * _SEVERITY_WEIGHTS.get((f.get("severity") or "").lower(), 0.2)
                for f in findings
            )
            overall_score = min(100, round(weighted_sum / total_weight))

    # Counts
    critical_count = sum(1 for f in findings if (f.get("severity") or "").lower() in ("kritican", "kritičan"))
    high_count     = sum(1 for f in findings if (f.get("severity") or "").lower() == "visok")
    missing_count  = len(missing)

    proc_issues = (
        len(litig.get("procedural_defects", []))
        + len(litig.get("deadline_risks", []))
        + len(litig.get("evidence_gaps", []))
    )

    fin_exposure = fin_exp.get("max_total_exposure_rsd")

    # Risk label
    if overall_score >= 70:
        risk_label = "kritican" if critical_count >= 2 else "visok"
    elif overall_score >= 40:
        risk_label = "srednji"
    else:
        risk_label = "nizak"

    summary = {
        "overall_risk_score":      overall_score,
        "risk_label":              risk_label,
        "critical_count":          critical_count,
        "high_count":              high_count,
        "missing_clauses_count":   missing_count,
        "procedural_issues_count": proc_issues,
        "financial_exposure_rsd":  fin_exposure,
        "recommendations_count":   len(findings) + missing_count,
    }
    parsed["executive_summary"] = summary
    return parsed


# ─── 5. validate_law_refs ────────────────────────────────────────────────────

def validate_law_refs(parsed: dict) -> dict:
    """
    Soft check: law_ref koji nije u poznatoj listi se flaguje sa
    unverified_law_ref=True. Ne uklanjamo finding.
    """
    findings = parsed.get("findings", [])
    for f in findings:
        law_ref = (f.get("law_ref") or "").strip()
        if not law_ref:
            continue
        law_lower = law_ref.lower()
        known = any(k in law_lower for k in _POZNATI_ZAKONI)
        if not known:
            f["unverified_law_ref"] = True
            logger.warning("[VALIDATOR] unverified_law_ref: %r (finding id=%s)", law_ref, f.get("id"))
        else:
            f["unverified_law_ref"] = False

    parsed["findings"] = findings
    return parsed


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_validation_pipeline(
    raw_llm: str,
    segmented_doc: SegmentedDocument,
    retry_fn=None,
) -> dict:
    """
    Pokreće ceo validation pipeline.
    Uvek vraća validan dict — nikad ne baca izuzetak na caller.
    """
    parsed, is_fallback = parse_llm_response(raw_llm, retry_fn)

    if is_fallback:
        logger.error("[VALIDATOR] Returning fallback response (parse error)")
        return parsed

    try:
        parsed = validate_clause_excerpts(parsed, segmented_doc)
    except Exception as e:
        logger.error("[VALIDATOR] validate_clause_excerpts error: %s", e)

    try:
        parsed = validate_clause_refs(parsed, segmented_doc)
    except Exception as e:
        logger.error("[VALIDATOR] validate_clause_refs error: %s", e)

    try:
        parsed = compute_executive_summary(parsed)
    except Exception as e:
        logger.error("[VALIDATOR] compute_executive_summary error: %s", e)

    try:
        parsed = validate_law_refs(parsed)
    except Exception as e:
        logger.error("[VALIDATOR] validate_law_refs error: %s", e)

    # Osiguraj da low_confidence_findings uvek postoji
    if "low_confidence_findings" not in parsed:
        parsed["low_confidence_findings"] = []

    return parsed
