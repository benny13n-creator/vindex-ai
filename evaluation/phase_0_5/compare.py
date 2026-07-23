# -*- coding: utf-8 -*-
"""
evaluation/phase_0_5/compare.py — reveals blind labels AFTER scoring and
aggregates Genome-vs-LRE results across the dataset.

Reads outputs/blinded/{predmet_id}.json (must have score_sheet filled in
by the lawyer) + outputs/keys/{predmet_id}.json (the real A/B mapping,
written by run.py, never shown to the lawyer before this point) and
produces an aggregate comparison.

This is where "which one is better" becomes answerable -- run.py and the
scoring step both stay blind by design.

Usage:
    python evaluation/phase_0_5/compare.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.phase_0_5.metrics import METRICS, METRIC_KEYS  # noqa: E402

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
BLINDED_DIR = OUTPUTS_DIR / "blinded"
KEYS_DIR = OUTPUTS_DIR / "keys"

_LOWER_IS_BETTER = {"propusteni_elementi", "lazni_zakljucci"}


def _load_case(predmet_id: str) -> tuple[dict, dict] | None:
    blinded_path = BLINDED_DIR / f"{predmet_id}.json"
    key_path = KEYS_DIR / f"{predmet_id}.json"
    if not blinded_path.exists() or not key_path.exists():
        return None
    blinded = json.loads(blinded_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    return blinded, key


def _is_scored(score_sheet: dict) -> bool:
    if not score_sheet or not score_sheet.get("scored_at"):
        return False
    for label in ("A", "B"):
        if any(v is None for v in score_sheet["scores"][label].values()):
            return False
    return True


def reveal_and_aggregate() -> dict:
    """Returns per-source (genome/lre) aggregate scores + how often each
    metric favored which source + how often the analysis changed the
    lawyer's reasoning (the founder's added metric, tracked separately --
    it's the most direct value signal, not just another averaged number)."""
    per_source_totals: dict[str, dict[str, list]] = {"genome": {k: [] for k in METRIC_KEYS}, "lre": {k: [] for k in METRIC_KEYS}}
    preferred_counts = {"genome": 0, "lre": 0, "tie": 0}
    changed_reasoning_counts = {"genome": 0, "lre": 0}
    scored_cases = 0
    unscored_cases = []

    if not BLINDED_DIR.exists():
        return {"error": "Nema outputs/blinded/ -- pokreni run.py prvo."}

    for blinded_path in sorted(BLINDED_DIR.glob("*.json")):
        predmet_id = blinded_path.stem
        loaded = _load_case(predmet_id)
        if not loaded:
            continue
        blinded, key = loaded
        score_sheet = blinded.get("score_sheet") or {}
        if not _is_scored(score_sheet):
            unscored_cases.append(predmet_id)
            continue

        scored_cases += 1
        label_to_source = key["label_to_source"]  # {"A": "genome"|"lre", "B": ...}

        for label, source in label_to_source.items():
            scores = score_sheet["scores"][label]
            for metric_key in METRIC_KEYS:
                val = scores.get(metric_key)
                if metric_key == "promenilo_odluku_advokata":
                    # bool is a subclass of int in Python -- isinstance(True, int)
                    # is True, so this MUST be checked before the generic
                    # numeric branch below, or True/False silently gets
                    # averaged as 1/0 into per_source_totals instead of
                    # counted here. (Caught by test_compare_reveals_and_
                    # aggregates_correctly during Phase 0.5 framework build.)
                    if val is True:
                        changed_reasoning_counts[source] += 1
                elif isinstance(val, (int, float)):
                    per_source_totals[source][metric_key].append(val)

        preferred = score_sheet.get("preferred_label")
        if preferred in label_to_source:
            preferred_counts[label_to_source[preferred]] += 1
        elif preferred == "tie":
            preferred_counts["tie"] += 1

    def _avg(vals: list) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    metric_summary = {}
    for m in METRICS:
        key = m["key"]
        if key == "promenilo_odluku_advokata":
            continue  # tracked separately below, boolean not averaged
        g_avg = _avg(per_source_totals["genome"][key])
        l_avg = _avg(per_source_totals["lre"][key])
        lower_better = key in _LOWER_IS_BETTER
        winner = None
        if g_avg is not None and l_avg is not None and g_avg != l_avg:
            winner = ("genome" if g_avg < l_avg else "lre") if lower_better else ("genome" if g_avg > l_avg else "lre")
        metric_summary[key] = {"label": m["label"], "genome_avg": g_avg, "lre_avg": l_avg,
                                "lower_is_better": lower_better, "winner": winner}

    return {
        "scored_cases": scored_cases,
        "unscored_cases": unscored_cases,
        "metrics": metric_summary,
        "preferred_for_drafting": preferred_counts,
        "changed_lawyer_reasoning": changed_reasoning_counts,
        "gate_verdict": _gate_verdict(metric_summary, scored_cases),
    }


def _gate_verdict(metric_summary: dict, scored_cases: int) -> str:
    """Binding gate per LEGAL_REASONING_ARCHITECTURE.md Phase 0.5: 'if LRE
    does not beat Genome on real cases, Phase 1 does not happen.' This
    function states the mechanical read of the numbers -- it is a signal
    for the founder's decision, not a decision made automatically."""
    if scored_cases == 0:
        return "NEDOVOLJNO PODATAKA -- nijedan predmet nije ocenjen."
    lre_wins = sum(1 for v in metric_summary.values() if v["winner"] == "lre")
    genome_wins = sum(1 for v in metric_summary.values() if v["winner"] == "genome")
    total = len(metric_summary)
    if lre_wins > genome_wins:
        return f"LRE vodi na {lre_wins}/{total} metrika -- kandidat za Phase 1, ali odluka je founderova, ne automatska."
    if genome_wins > lre_wins:
        return f"Genome vodi na {genome_wins}/{total} metrika -- Phase 1 se NE preporucuje na osnovu ovih podataka."
    return "Nerešeno -- potrebno više predmeta ili founderova kvalitativna procena."


if __name__ == "__main__":
    result = reveal_and_aggregate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
