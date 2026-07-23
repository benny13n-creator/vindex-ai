# -*- coding: utf-8 -*-
"""
evaluation/phase_0_5/metrics.py — scoring schema for Reality Calibration.

docs/architecture/LEGAL_REASONING_ARCHITECTURE.md, Phase 0.5 (founder,
2026-07-23). This module defines WHAT gets measured and the blind-label
mechanism. It does not run anything itself.

Method (founder's exact words, preserved): the question is not "is it
nicely written" — it's whether LRE's Reasoning Graph is a materially
better model of the case than Genome's existing argumenti_za/
argumenti_protiv/kontradikcije fields, judged against real cases and an
experienced lawyer's own read (the gold standard).

7 metrics — the founder's original 6, plus one added in the same review:
"Did LRE change the lawyer's reasoning?" (their words: "to je pravi dokaz
vrednosti" — the most direct proof of practical value, more important
than "is it better" in the abstract).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

METRICS: list[dict] = [
    {"key": "tacne_kljucne_cinjenice", "label": "Tačno identifikovane ključne činjenice",
     "scale": "count_or_1_5"},
    {"key": "tacne_kontradikcije", "label": "Tačno identifikovane kontradikcije",
     "scale": "count_or_1_5"},
    {"key": "pravilno_povezani_dokazi", "label": "Pravilno povezani dokazi",
     "scale": "count_or_1_5"},
    {"key": "propusteni_elementi", "label": "Propušteni bitni elementi",
     "scale": "count_lower_is_better"},
    {"key": "lazni_zakljucci", "label": "Lažni zaključci",
     "scale": "count_lower_is_better"},
    {"key": "korisnost_za_podnesak", "label": "Korisnost za izradu podneska",
     "scale": "1_5"},
    {"key": "promenilo_odluku_advokata", "label": "Da li je ova analiza promenila advokatovo rezonovanje o predmetu?",
     "scale": "boolean_plus_note"},
]

METRIC_KEYS = [m["key"] for m in METRICS]


@dataclass
class BlindAssignment:
    """Which real source (genome/lre) maps to which blind label (A/B) for
    one case — kept in a SEPARATE key file from what the lawyer sees, per
    the founder's explicit blind-A/B requirement (2026-07-23): 'To
    eliminiše confirmation bias.' Revealed only by compare.py, only after
    scores are recorded."""
    predmet_id: str
    label_to_source: dict[str, str]  # {"A": "genome", "B": "lre"} or reversed

    def to_dict(self) -> dict:
        return {"predmet_id": self.predmet_id, "label_to_source": self.label_to_source}


def assign_blind_labels(predmet_id: str, seed: int | None = None) -> BlindAssignment:
    """Randomly decides whether Genome or LRE is 'Analysis A' for this
    case. Uses SystemRandom (true randomness) by default — NOT seeded
    from predmet_id, per founder review (2026-07-23): deriving the
    assignment from the case id is itself a pattern an evaluator could,
    in principle, learn or guess across many cases ("da nijedan evaluator
    ne moze intuitivno da pogodi obrazac"). The mapping is persisted to
    the key file (run.py) the moment it's generated — it does not need to
    be reproducible from predmet_id alone, and deliberately isn't.

    An explicit `seed` is still accepted for tests (determinism there is
    a test-quality concern, not a blind-design concern — nothing in a
    unit test is being evaluated by a lawyer)."""
    rng = random.SystemRandom() if seed is None else random.Random(seed)
    sources = ["genome", "lre"]
    rng.shuffle(sources)
    return BlindAssignment(predmet_id=predmet_id, label_to_source={"A": sources[0], "B": sources[1]})


def empty_score_sheet(predmet_id: str) -> dict:
    """Template the lawyer fills in, per label (A/B), never per source name
    — the whole point of the blind design."""
    return {
        "predmet_id": predmet_id,
        "scored_at": None,
        "scores": {
            label: {m["key"]: None for m in METRICS}
            for label in ("A", "B")
        },
        "preferred_label": None,  # "A" | "B" | "tie" — which would the lawyer trust more for drafting
        "notes": {"A": "", "B": ""},
    }
