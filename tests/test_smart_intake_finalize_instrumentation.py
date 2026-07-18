# -*- coding: utf-8 -*-
"""
Tests for Faza 2.1 (90-dnevni plan, 2026-07-18): Smart Intake finalize
instrumentation. Rule B — meri da li advokat menja izvucene podatke pre
finalize-a ili samo potvrdjuje, ne pretpostavlja odgovor. Ne menja UX/API,
samo dodaje metriku u vec postojeci _track_event poziv.

Cisti unit testovi za dve izdvojene funkcije — nema mock-ovanja
baze/mreze/endpoint-a, namerno (ceo finalize_intake_job je veliki endpoint
sa mnogo nezavisnih koraka van obima ove instrumentacije).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone

from routers.smart_intake import _compute_finalize_wait_s, _count_corrected_entities


# ═══════════════════════════════════════════════════════════════════════════
# _compute_finalize_wait_s
# ═══════════════════════════════════════════════════════════════════════════

def test_finalize_wait_s_computes_elapsed_seconds():
    completed = (datetime.now(timezone.utc) - timedelta(seconds=42)).isoformat()
    wait_s = _compute_finalize_wait_s({"completed_at": completed})
    assert wait_s is not None
    assert 40 <= wait_s <= 45  # dozvoljena mala tolerancija za trajanje testa


def test_finalize_wait_s_none_when_completed_at_missing():
    """Odsustvo podatka NIJE isto sto i trenutna finalizacija — mora biti
    None, ne 0."""
    assert _compute_finalize_wait_s({}) is None
    assert _compute_finalize_wait_s({"completed_at": None}) is None


def test_finalize_wait_s_handles_z_suffix_timestamp():
    """Supabase cesto vraca ISO timestamp sa 'Z' sufiksom umesto '+00:00'."""
    completed = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    wait_s = _compute_finalize_wait_s({"completed_at": completed})
    assert wait_s is not None
    assert 8 <= wait_s <= 15


def test_finalize_wait_s_never_raises_on_malformed_timestamp():
    assert _compute_finalize_wait_s({"completed_at": "nije datum"}) is None
    assert _compute_finalize_wait_s({"completed_at": 12345}) is None


# ═══════════════════════════════════════════════════════════════════════════
# _count_corrected_entities
# ═══════════════════════════════════════════════════════════════════════════

def test_count_corrected_entities_counts_only_actual_changes():
    entities = [
        {"entity_type": "judge", "value": "Marija Kovačević", "corrected_value": None},
        {"entity_type": "plaintiff", "value": "Petrović", "corrected_value": "Petrović d.o.o."},
        {"entity_type": "court", "value": "Osnovni sud", "corrected_value": "Osnovni sud"},  # ista vrednost, ne racuna se
    ]
    assert _count_corrected_entities(entities) == 1


def test_count_corrected_entities_zero_when_nothing_corrected():
    entities = [{"entity_type": "judge", "value": "X", "corrected_value": None}]
    assert _count_corrected_entities(entities) == 0


def test_count_corrected_entities_empty_list():
    assert _count_corrected_entities([]) == 0


def test_count_corrected_entities_ignores_reviewed_without_correction():
    """reviewed=True ali corrected_value prazan znaci 'pogledao, potvrdio
    kako jeste' — ne racuna se kao izmena."""
    entities = [{"entity_type": "amount", "value": "1000 RSD", "corrected_value": "", "reviewed": True}]
    assert _count_corrected_entities(entities) == 0
