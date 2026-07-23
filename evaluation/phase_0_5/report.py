# -*- coding: utf-8 -*-
"""
evaluation/phase_0_5/report.py — human-readable rendering of compare.py's
aggregate output. Reusable for future evaluations (LRE v2, Precedent
Engine, Draft Engine, Adversarial Review) -- this is why compare.py
returns structured data rather than printing directly: this module (or a
future replacement) is the only thing that should change per-evaluation.

Usage:
    python evaluation/phase_0_5/report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.phase_0_5.compare import reveal_and_aggregate  # noqa: E402


def render(result: dict) -> str:
    if "error" in result:
        return result["error"]

    lines = []
    lines.append("=" * 70)
    lines.append("PHASE 0.5 — REALITY CALIBRATION — Genome vs. LRE")
    lines.append("=" * 70)
    lines.append(f"Ocenjeno predmeta: {result['scored_cases']}")
    if result["unscored_cases"]:
        lines.append(f"Neocenjeno (preskočeno): {len(result['unscored_cases'])} — {', '.join(result['unscored_cases'][:5])}"
                      + (" ..." if len(result["unscored_cases"]) > 5 else ""))
    lines.append("")
    lines.append(f"{'Metrika':<45} {'Genome':>10} {'LRE':>10} {'Pobednik':>10}")
    lines.append("-" * 76)
    for key, m in result["metrics"].items():
        g = "—" if m["genome_avg"] is None else f"{m['genome_avg']:.2f}"
        l = "—" if m["lre_avg"] is None else f"{m['lre_avg']:.2f}"
        w = m["winner"] or "—"
        arrow = " (niže=bolje)" if m["lower_is_better"] else ""
        lines.append(f"{m['label'][:43]+arrow:<45} {g:>10} {l:>10} {w:>10}")
    lines.append("")

    changed = result["changed_lawyer_reasoning"]
    lines.append(f"Promenilo advokatovo rezonovanje — Genome: {changed.get('genome', 0)}x, LRE: {changed.get('lre', 0)}x")
    pref = result["preferred_for_drafting"]
    lines.append(f"Preferencija za izradu podneska — Genome: {pref.get('genome', 0)}, LRE: {pref.get('lre', 0)}, Nerešeno: {pref.get('tie', 0)}")
    lines.append("")
    lines.append(f"VERDIKT (mehanicko čitanje brojeva, ne automatska odluka): {result['gate_verdict']}")
    lines.append("=" * 70)
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(reveal_and_aggregate()))
