# -*- coding: utf-8 -*-
"""
Vindex AI — shared/gap_engine.py

Program Sigma, Master Sprint 003 (2026-08-06) — "Legal Gap & Missing Evidence Engine".

ONE canonical aggregation point for every "nedostaje" (gap/missing) finding this platform
already computes. This module is NOT a new detector — it is a normalizer over 3
already-existing, already-canonical sources, satisfying Phase 2's own explicit rule
("nije dozvoljeno pravljenje paralelnih algoritama") by construction: nothing here
decides whether something is missing; it only reshapes an already-computed decision
into one record shape every consumer should read instead of re-deriving its own list.

## The 3 sources this module normalizes, and why no 4th was invented

1. `services/risk_engine.py::identify_case_problems` — the platform's own established
   deterministic "what's wrong with this case" algorithm (Core Consolidation,
   2026-07-22). Code-computed, not GPT — its own findings are HIGH confidence by
   construction (a literal comparison against `EXPECTED_DOCS`/deadline counts, not an
   inference).
2. `case_dna.nedostaje[]` — Genome's own GPT-extracted, case-specific missing-evidence
   list (`routers/case_dna.py`'s own extraction prompt). GPT-advisory — normalized here
   as a HYPOTHESIS, never asserted as fact (Phase 2's own "Bez GPT tvrdnji bez dokaza"
   rule).
3. `case_dna.kontradikcije[]` — Genome's own contradictions, identity-anchored via
   `shared/contradiction_identity.py` (Program Sigma, Master Sprint 002) so the SAME
   underlying contradiction produces the SAME Gap record across refreshes.

## What this module explicitly does NOT do

Does not call GPT. Does not compute a 4th, independent "missing" signal. Does not
replace `case_actions` (the canonical STATEFUL action-tracking table, migration 099) —
a Gap record is a read-time descriptive view; `case_actions` remains the one table with
persisted status/lifecycle for the subset of gaps that are actionable
(`PRIBAVITI_DOKAZ`/`RAZRESITI_KONTRADIKCIJU`). Where a Gap's own `tip` maps onto an
existing `case_actions.tip` value, the SAME value is reused (see `GAP_TIP_*` below) —
one vocabulary, not two.
"""
from __future__ import annotations

from shared.contradiction_identity import contradiction_dedupe_key, normalize_tezina

# ─── Canonical gap types — reuses case_actions' own vocabulary where a 1:1 mapping
# exists (migrations/099_case_actions.sql), extended only for gap types
# case_actions does not currently track at all (Genome's own holistic nedostaje[]).
GAP_TIP_NEMA_DOKAZA        = "NEMA_DOKAZA"          # maps to case_actions.PRIBAVITI_DOKAZ
GAP_TIP_NEDOSTAJE_DOKUMENT = "NEDOSTAJE_DOKUMENT"   # maps to case_actions.PRIBAVITI_DOKAZ
GAP_TIP_PREDSTOJECI_ROKOVI = "PREDSTOJECI_ROKOVI"   # maps to case_actions.PLANIRATI_ROKOVE
GAP_TIP_DOKAZI_SLABI       = "DOKAZI_SLABI"         # maps to case_actions.OJACATI_DOKAZE
GAP_TIP_KRITICAN_ROK       = "KRITICAN_ROK"         # maps to case_actions.PRIPREMITI_PODNESAK
GAP_TIP_KONTRADIKCIJA      = "KONTRADIKCIJA"        # maps to case_actions.RAZRESITI_KONTRADIKCIJU
GAP_TIP_GENOME_NEDOSTAJE   = "GENOME_NEDOSTAJE"     # holistic GPT finding, no case_actions equivalent today

_HITNOST_TO_POUZDANOST = {"kriticno": "visoka", "vazno": "srednja", "pozeljno": "niska"}
_HITNOST_TO_PLAN = {"kriticno": "visoka", "vazno": "srednja", "pozeljno": "niska"}


def _gap(tip: str, izvor: str, razlog: str, pouzdanost: str,
         ocekivano: str, pronadjeno: str, zasto: str, hipoteza: bool) -> dict:
    """The one canonical Gap record shape — every field Phase 2 requires."""
    return {
        "tip": tip,
        "izvor": izvor,
        "razlog": razlog,
        "pouzdanost": pouzdanost,
        "ocekivano": ocekivano,
        "pronadjeno": pronadjeno,
        "zasto": zasto,
        "hipoteza": hipoteza,  # True = GPT-advisory, never asserted as fact; False = deterministically true
    }


def classify_case_problem(text: str) -> str | None:
    """THE one classification cascade over identify_case_problems' own output
    strings, mapping free text to a canonical GAP_TIP_* constant, or None if
    the text matches none of the known patterns. Program Sigma, Master
    Sprint 003 (2026-08-06): extracted from a cascade that previously
    existed, duplicated, in TWO places -- this function AND
    services/case_evolution.py::_compute_target_actions' own Rule 2 each had
    their own independent if/elif chain over the same identify_case_problems
    text. Found by this sprint's own self-review (the same "no parallel
    algorithms" principle this sprint's mission statement demands, applied to
    code THIS sprint itself wrote) -- Rule 2 now calls this function too, see
    its own comment in case_evolution.py. Returns None (not a guessed
    fallback tip) for anything unrecognized -- identify_case_problems' own
    output today is always one of the 5 patterns below, but a caller should
    decide for itself how to handle a hypothetical future 6th pattern, not
    have this shared classifier silently pick one for it."""
    if "kritičan rok" in text:
        return GAP_TIP_KRITICAN_ROK
    if text.startswith("Nema uploadovanih dokaza"):
        return GAP_TIP_NEMA_DOKAZA
    if text.startswith("Nedostaje "):
        return GAP_TIP_NEDOSTAJE_DOKUMENT
    if "predstojećih rokova" in text:
        return GAP_TIP_PREDSTOJECI_ROKOVI
    if text.startswith("Dokazi slabe snage"):
        return GAP_TIP_DOKAZI_SLABI
    return None


def gaps_from_case_problems(problemi: list[dict]) -> list[dict]:
    """Normalizes services/risk_engine.py::identify_case_problems' own output.
    Deterministic source -> hipoteza=False (these are literally true by
    construction, not an inference). Unrecognized problem text (see
    classify_case_problem's own None case) still surfaces as a generic
    NEDOSTAJE_DOKUMENT gap here -- unlike case_actions' own Rule 2, this
    module's whole purpose is "never silently drop a finding," so an
    unrecognized-but-real problem string is shown with its own generic type
    rather than vanishing, the opposite default from Rule 2's own (correct,
    unchanged) silent-skip."""
    _OZBILJNOST_TO_POUZDANOST = {"kritican": "visoka", "vazan": "visoka", "info": "srednja"}
    out = []
    for p in problemi or []:
        text = p.get("problem") or ""
        if not text:
            continue
        tip = classify_case_problem(text) or GAP_TIP_NEDOSTAJE_DOKUMENT
        out.append(_gap(
            tip=tip, izvor="identify_case_problems", razlog=text,
            pouzdanost=_OZBILJNOST_TO_POUZDANOST.get(p.get("ozbiljnost"), "srednja"),
            ocekivano=text, pronadjeno="", zasto="Deterministički izračunato iz stanja spisa (EXPECTED_DOCS/rokovi/dokazi).",
            hipoteza=False,
        ))
    return out


def gaps_from_genome_nedostaje(case_dna: dict | None) -> list[dict]:
    """Normalizes case_dna.nedostaje[] -- Genome's own GPT-extracted, holistic
    missing-evidence list. GPT-advisory -> hipoteza=True always."""
    if not case_dna or case_dna.get("greska"):
        return []
    out = []
    for n in (case_dna.get("nedostaje") or []):
        dokument = (n.get("dokument") or "").strip()
        opis = (n.get("opis") or "").strip()
        if not dokument and not opis:
            continue
        hitnost = n.get("hitnost")
        out.append(_gap(
            tip=GAP_TIP_GENOME_NEDOSTAJE, izvor="genome_ekstrakcija",
            razlog=opis or dokument,
            pouzdanost=_HITNOST_TO_POUZDANOST.get(hitnost, "srednja"),
            ocekivano=dokument or opis, pronadjeno="",
            zasto="Genome procenjuje da bi ovaj dokument/dokaz ojačao predmet, na osnovu celokupnog dosijea.",
            hipoteza=True,
        ))
    return out


def gaps_from_contradictions(case_dna: dict | None) -> list[dict]:
    """Normalizes case_dna.kontradikcije[] using the stable, GPT-phrasing-
    independent identity from Program Sigma Sprint 002. GPT-advisory ->
    hipoteza=True."""
    if not case_dna or case_dna.get("greska"):
        return []
    _TEZINA_TO_POUZDANOST = {"kriticna": "visoka", "vazna": "srednja", "manja": "niska"}
    out = []
    for k in (case_dna.get("kontradikcije") or []):
        opis = (k.get("opis") or "").strip()
        if not opis:
            continue
        loc1 = k.get("lokacija_1") or ""
        loc2 = k.get("lokacija_2") or ""
        out.append(_gap(
            tip=GAP_TIP_KONTRADIKCIJA, izvor="genome_kontradikcije", razlog=opis,
            # Operation Single Brain (2026-08-07): normalize_tezina() validates the raw
            # GPT value the same way services/case_evolution.py's Rule 3 now does -- one
            # canonical enum check, not two independently lenient defaults (see
            # shared/contradiction_identity.py).
            pouzdanost=_TEZINA_TO_POUZDANOST[normalize_tezina(k.get("tezina"))],
            ocekivano="Usaglašene činjenice između dokumenata",
            pronadjeno=f"{loc1} vs {loc2}".strip(" vs") or "izvor nije citiran",
            zasto=f"Kontradikcija između {loc1 or '?'} i {loc2 or '?'}.",
            hipoteza=True,
        ))
        out[-1]["dedupe_key"] = contradiction_dedupe_key(k)
    return out


def collect_case_gaps(problemi: list[dict] | None, case_dna: dict | None) -> list[dict]:
    """THE canonical entry point — every gap this platform currently knows how
    to compute, for one case, normalized into one shape. Callers pass
    already-fetched `problemi` (identify_case_problems' own output) and
    `case_dna` (Genome) -- this function computes nothing new, it only
    aggregates."""
    return (
        gaps_from_case_problems(problemi)
        + gaps_from_genome_nedostaje(case_dna)
        + gaps_from_contradictions(case_dna)
    )


# ─── Consumer-facing helpers — thin, display-shape-specific projections over
# gaps_from_genome_nedostaje, so callers stop independently re-deriving their
# own "missing items" list via a 2nd/3rd GPT call. ─────────────────────────

def missing_evidence_labels(case_dna: dict | None, limit: int = 4) -> list[str]:
    """Plain-string display labels for Genome's own nedostaje[], sorted by
    urgency (kriticno first). Used by routers/copilot.py::_handle_analiza_predmeta
    in place of that handler's own previously-independent GPT-derived list."""
    order = {"kriticno": 0, "vazno": 1, "pozeljno": 2}
    items = sorted(
        (case_dna.get("nedostaje") or []) if case_dna and not case_dna.get("greska") else [],
        key=lambda n: order.get(n.get("hitnost"), 3),
    )
    labels = []
    for n in items[:limit]:
        label = (n.get("dokument") or n.get("opis") or "").strip()
        if label:
            labels.append(label)
    return labels


def missing_evidence_plan_items(case_dna: dict | None, limit: int = 6) -> list[dict]:
    """{"stavka": str, "hitnost": "visoka|srednja|niska"} shaped items from
    Genome's own nedostaje[], for routers/copilot.py::_handle_plan_predmeta in
    place of that handler's own previously-independent (and previously
    Genome-blind) GPT-derived list."""
    order = {"kriticno": 0, "vazno": 1, "pozeljno": 2}
    items = sorted(
        (case_dna.get("nedostaje") or []) if case_dna and not case_dna.get("greska") else [],
        key=lambda n: order.get(n.get("hitnost"), 3),
    )
    out = []
    for n in items[:limit]:
        stavka = (n.get("dokument") or n.get("opis") or "").strip()
        if stavka:
            out.append({"stavka": stavka, "hitnost": _HITNOST_TO_PLAN.get(n.get("hitnost"), "srednja")})
    return out
