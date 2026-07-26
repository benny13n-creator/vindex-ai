# -*- coding: utf-8 -*-
"""
Vindex AI — shared/vector_origin.py

Institutional Memory Architecture V2 (2026-07-26), STUB 2/3 — Origin &
Lineage + Memory Decay. Kanonske konstante i funkcije za:
  - origin: obavezno metadata polje na SVAKOM vektoru (v. ORIGIN_WEIGHTS)
  - freshness/decay: vremenska težina za "case_doc"/"draft_final" poreklo

Namerno odvojeno od app/services/retrieve.py (koji ga uvozi) da bi i
ingest-strana (api.py, routers/smart_intake.py, routers/drafting.py,
routers/dokument.py) mogla da uvozi iste konstante bez kružne zavisnosti na
retrieve.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# ─── STUB 2: Origin & Lineage ───────────────────────────────────────────────

ORIGIN_LAW              = "LAW"
ORIGIN_COURT            = "COURT"
ORIGIN_LAWYER_VERIFIED  = "LAWYER_VERIFIED"
ORIGIN_CLIENT_DOC       = "CLIENT_DOC"
ORIGIN_AI_GENERATED     = "AI_GENERATED"

# Težina po poreklu -- koristi se kao multiplikator u Final Score formuli
# (v. app/services/retrieve.py's _origin_i_freshness_score). AI_GENERATED je
# 0.00 NAMERNO: taj status ne bi trebalo NIKAD da se pojavi u
# kancelarija_{id}/user_{id} namespace-u (staging_memory sprečava to na
# ingest strani, v. routers/drafting.py's _stage_draft_for_review) -- ali
# ako bi greškom ipak dospeo tu, ova težina ga potpuno gasi u retrievalu
# kao odbrana-u-dubinu (defense in depth), ne samo oslanjanje na ingest gate.
ORIGIN_WEIGHTS: dict[str, float] = {
    ORIGIN_LAW: 1.0,
    ORIGIN_COURT: 1.0,
    ORIGIN_LAWYER_VERIFIED: 0.95,
    ORIGIN_CLIENT_DOC: 0.80,
    ORIGIN_AI_GENERATED: 0.00,
}

_ORIGIN_LABELS_SR: dict[str, str] = {
    ORIGIN_LAW: "Zvaničan zakon/uredba",
    ORIGIN_COURT: "Zvanična sudska praksa",
    ORIGIN_LAWYER_VERIFIED: "Odobren autorski tekst advokata",
    ORIGIN_CLIENT_DOC: "Dokaz/dokument iz predmeta",
    ORIGIN_AI_GENERATED: "Neoveren AI nacrt",
}


def origin_weight(origin: Optional[str]) -> float:
    """Nepoznato poreklo tretira se kao CLIENT_DOC (konzervativna, ne
    najviša, ne najniža težina) -- nikad ne baca grešku."""
    if not origin:
        return ORIGIN_WEIGHTS[ORIGIN_CLIENT_DOC]
    return ORIGIN_WEIGHTS.get(origin, ORIGIN_WEIGHTS[ORIGIN_CLIENT_DOC])


def origin_label(origin: Optional[str]) -> str:
    return _ORIGIN_LABELS_SR.get(origin or "", _ORIGIN_LABELS_SR[ORIGIN_CLIENT_DOC])


# ─── STUB 3: Memory Decay & Temporal Validity ───────────────────────────────

_DECAY_APPLIES_TO = {ORIGIN_CLIENT_DOC, ORIGIN_LAWYER_VERIFIED}
_DECAY_START_YEARS = 3.0     # godine posle kojih počinje penal
_DECAY_FULL_YEARS = 10.0     # godine posle kojih je penal maksimalan (floor)
_DECAY_FLOOR = 0.5           # najniža moguća freshness težina (nikad 0 -- stariji
                              # dokument i dalje može biti jedini relevantan izvor)


def freshness_weight(
    origin: Optional[str],
    created_at: Optional[str],
    golden_template: bool = False,
    valid_until: Optional[str] = None,
    status: Optional[str] = None,
) -> float:
    """Freshness Weight iz Final Score formule (Vector Similarity x Freshness
    Weight x Origin Weight, v. app/services/retrieve.py).

    - LAW/COURT: uvek 1.0 (zakon ne "zastareva" po starosti u ovom modelu --
      samo eksplicitnom izmenom/ukidanjem, što je zaseban, teži problem van
      dometa ove faze; v. valid_until/status ispod za DEPRECATED slučaj).
    - golden_template=True: uvek 1.0, bez obzira na starost (eksplicitno
      označen "Zlatni šablon" -- namerno izuzet od decay-a).
    - status == "DEPRECATED" ili prošao valid_until: teška kazna (0.1) --
      dokument i dalje MOŽE da se pojavi (nikad hard-exclude), ali gotovo
      nikad neće pobediti bilo šta važeće.
    - CLIENT_DOC/LAWYER_VERIFIED stariji od 3 godine: linearni decay od 1.0
      (na 3 god.) do _DECAY_FLOOR (na 10+ god.).
    """
    if status == "DEPRECATED":
        return 0.1
    if valid_until:
        try:
            _vu = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            if _vu < datetime.now(timezone.utc):
                return 0.1
        except (ValueError, TypeError):
            pass

    if golden_template:
        return 1.0
    if origin not in _DECAY_APPLIES_TO:
        return 1.0
    if not created_at:
        return 1.0

    try:
        _created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 1.0

    age_years = (datetime.now(timezone.utc) - _created).days / 365.25
    if age_years <= _DECAY_START_YEARS:
        return 1.0
    if age_years >= _DECAY_FULL_YEARS:
        return _DECAY_FLOOR

    span = _DECAY_FULL_YEARS - _DECAY_START_YEARS
    progress = (age_years - _DECAY_START_YEARS) / span
    return 1.0 - progress * (1.0 - _DECAY_FLOOR)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
