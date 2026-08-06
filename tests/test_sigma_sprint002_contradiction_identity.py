# -*- coding: utf-8 -*-
"""
Program Sigma, Master Sprint 002 (2026-08-06) — "Autonomous Evidence & Timeline
Reconstruction Engine". Tests for shared/contradiction_identity.py and its two
consumers -- proves the real, previously-unknown bug this sprint found and fixed:
a Genome-extracted contradiction's identity (used both by
routers/case_dna.py::_compute_delta's own set-membership diff, and by
services/case_evolution.py's own Rule 3 RAZRESITI_KONTRADIKCIJU dedupe_key) was
anchored on the contradiction's free-text `opis` -- GPT-generated prose, re-worded
on every independent Genome refresh even for the IDENTICAL underlying
contradiction. This made case_actions' own reconcile loop flicker an open action
closed+reopened across refreshes, and made _compute_delta report false churn
(SIGMA-002, Sprint 001 Debt Register). Fixed: identity anchored on
(lokacija_1, lokacija_2) -- formulaic document+page citations Genome's own
extraction prompt already requires -- order-independent, opis-independent.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import Event, EventType  # noqa: F401 -- import order avoids a circular import (see services/event_bus.py::_register_defaults)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# shared/contradiction_identity.py — the shared function, in isolation
# ═══════════════════════════════════════════════════════════════════════════

def test_identity_ignores_opis_rewording_when_locations_present():
    from shared.contradiction_identity import contradiction_identity

    k1 = {"opis": "Datum uviđaja se razlikuje između podnesaka", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    k2 = {"opis": "Postoji neslaganje u datumu uviđaja", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    assert contradiction_identity(k1) == contradiction_identity(k2)


def test_identity_is_order_independent():
    from shared.contradiction_identity import contradiction_identity

    k1 = {"opis": "x", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    k2 = {"opis": "x", "lokacija_1": "DOK-03 str.1", "lokacija_2": "DOK-01 str.2"}
    assert contradiction_identity(k1) == contradiction_identity(k2)


def test_identity_differs_for_genuinely_different_locations():
    from shared.contradiction_identity import contradiction_identity

    k1 = {"opis": "x", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    k2 = {"opis": "x", "lokacija_1": "DOK-05 str.9", "lokacija_2": "DOK-06 str.1"}
    assert contradiction_identity(k1) != contradiction_identity(k2)


def test_identity_falls_back_to_opis_when_no_locations():
    from shared.contradiction_identity import contradiction_identity

    k1 = {"opis": "Neuobičajena kontradikcija bez citata", "lokacija_1": "", "lokacija_2": ""}
    k2 = {"opis": "Druga kontradikcija bez citata", "lokacija_1": "", "lokacija_2": ""}
    assert contradiction_identity(k1) != contradiction_identity(k2)
    assert contradiction_identity(k1) == (k1["opis"], "")


def test_dedupe_key_is_a_stable_24char_hex_string():
    from shared.contradiction_identity import contradiction_dedupe_key
    key = contradiction_dedupe_key({"opis": "x", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"})
    assert len(key) == 24
    assert all(c in "0123456789abcdef" for c in key)


def test_dedupe_key_matches_for_reworded_opis():
    from shared.contradiction_identity import contradiction_dedupe_key
    k1 = {"opis": "Datum uviđaja se razlikuje", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    k2 = {"opis": "Postoji neslaganje u datumu uviđaja između dokumenata", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"}
    assert contradiction_dedupe_key(k1) == contradiction_dedupe_key(k2)


# ═══════════════════════════════════════════════════════════════════════════
# services/case_evolution.py::_compute_target_actions — Rule 3 integration
# ═══════════════════════════════════════════════════════════════════════════

def _make_target_supa(case_dna=None, dokazi=None, dokumenti=None, rocista=None):
    """Minimal fake supa supporting exactly the read chains _compute_target_actions issues."""
    def _chain(data):
        c = MagicMock()
        for m in ['select', 'eq', 'is_', 'order', 'maybe_single']:
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            return _chain({"case_dna": case_dna or {}, "tip": "opsti"})
        if name == "predmet_dokazi":
            return _chain(dokazi or [])
        if name == "predmet_dokumenti":
            return _chain(dokumenti or [])
        if name == "rocista":
            return _chain(rocista or [])
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_rule3_dedupe_key_stable_across_reworded_refresh():
    """The actual bug: 2 separate Genome refreshes, SAME underlying
    contradiction (same locations), DIFFERENT GPT phrasing -- the resulting
    RAZRESITI_KONTRADIKCIJU action's own dedupe_key must be IDENTICAL, so
    the reconcile loop treats it as an update, never a close+reopen."""
    from services.case_evolution import _compute_target_actions

    case_dna_v1 = {"kontradikcije": [
        {"opis": "Datum uviđaja se razlikuje", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"},
    ]}
    case_dna_v2 = {"kontradikcije": [
        {"opis": "Postoji neslaganje u datumu uviđaja između podnesaka", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"},
    ]}

    supa1 = _make_target_supa(case_dna=case_dna_v1)
    with patch("services.case_evolution._get_supa", return_value=supa1):
        actions1 = await _compute_target_actions("pred-1")

    supa2 = _make_target_supa(case_dna=case_dna_v2)
    with patch("services.case_evolution._get_supa", return_value=supa2):
        actions2 = await _compute_target_actions("pred-1")

    key1 = next(a["dedupe_key"] for a in actions1 if a["tip"] == "RAZRESITI_KONTRADIKCIJU")
    key2 = next(a["dedupe_key"] for a in actions2 if a["tip"] == "RAZRESITI_KONTRADIKCIJU")
    assert key1 == key2


@pytest.mark.anyio
async def test_rule3_dedupe_key_differs_for_a_genuinely_new_contradiction():
    from services.case_evolution import _compute_target_actions

    case_dna = {"kontradikcije": [
        {"opis": "A", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"},
        {"opis": "B", "lokacija_1": "DOK-05 str.9", "lokacija_2": "DOK-06 str.1", "tezina": "vazna"},
    ]}
    supa = _make_target_supa(case_dna=case_dna)
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    keys = {a["dedupe_key"] for a in actions if a["tip"] == "RAZRESITI_KONTRADIKCIJU"}
    assert len(keys) == 2


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_dna.py::_compute_delta — SIGMA-002 closure
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_delta_no_false_churn_on_reworded_contradiction():
    """Direct proof SIGMA-002 is closed: the SAME underlying contradiction,
    reworded between 2 Genome versions, must report ZERO eliminated and
    ZERO new -- not a false '1 eliminated + 1 new' churn."""
    from routers.case_dna import _compute_delta

    old_g = {"kontradikcije": [
        {"opis": "Datum uviđaja se razlikuje", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"},
    ], "snaga_predmeta_procent": 50}
    new_g = {"kontradikcije": [
        {"opis": "Postoji neslaganje u datumu uviđaja između podnesaka", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1"},
    ], "snaga_predmeta_procent": 50}

    delta = _compute_delta(old_g, new_g)
    assert delta["kontr_eliminisane"] == 0
    assert delta["kontr_nove"] == 0


def test_compute_delta_still_detects_a_real_new_contradiction():
    """Negative control -- a genuinely NEW contradiction (different
    locations) must still be detected, the fix must not over-suppress."""
    from routers.case_dna import _compute_delta

    old_g = {"kontradikcije": [], "snaga_predmeta_procent": 50}
    new_g = {"kontradikcije": [
        {"opis": "Nova kontradikcija", "lokacija_1": "DOK-07 str.1", "lokacija_2": "DOK-08 str.4"},
    ], "snaga_predmeta_procent": 45}

    delta = _compute_delta(old_g, new_g)
    assert delta["kontr_eliminisane"] == 0
    assert delta["kontr_nove"] == 1


def test_compute_delta_detects_a_real_eliminated_contradiction():
    from routers.case_dna import _compute_delta

    old_g = {"kontradikcije": [
        {"opis": "Rešena kontradikcija", "lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-02 str.1"},
    ], "snaga_predmeta_procent": 40}
    new_g = {"kontradikcije": [], "snaga_predmeta_procent": 55}

    delta = _compute_delta(old_g, new_g)
    assert delta["kontr_eliminisane"] == 1
    assert delta["kontr_nove"] == 0
