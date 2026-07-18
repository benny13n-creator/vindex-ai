# -*- coding: utf-8 -*-
"""
Tests for Case Genome Faza 1.1 (90-dnevni plan, 2026-07-18):
routers/case_dna.py's _emit_genome_event i services/event_bus.py's
EventType.GENOME_UPDATED durable-outbox round-trip.

Faza 1.1 namerno ne dodaje handler za GENOME_UPDATED (to je 1.2, Genome
Audit Trail — zaseban zadatak) — ovi testovi pokrivaju samo da event
insert radi i da dispatch_pending_events() prepoznaje novi tip bez greske,
ne šta se dešava kad neko na njega pretplati handler.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit", "is_", "in_", "lt", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_dna.py — _emit_genome_event
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_emit_genome_event_inserts_row_with_correct_payload():
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    genome = {"verzija": 3, "snaga_predmeta_procent": 62}
    await cd._emit_genome_event(supa, "predmet-1", "user-1", genome, "manual_refresh")

    supa.table.assert_called_once_with("events")
    chain.insert.assert_called_once()
    row = chain.insert.call_args[0][0]
    assert row["event_type"] == "GenomeUpdated"
    assert row["user_id"] == "user-1"
    assert row["predmet_id"] == "predmet-1"
    assert row["payload"] == {
        "verzija": 3,
        "snaga_predmeta_procent": 62,
        "trigger": "manual_refresh",
    }


@pytest.mark.anyio
async def test_emit_genome_event_uses_correct_trigger_label_per_caller():
    """1.1 checklist zahtev: trigger u payload-u, ne samo u audit metadata (1.2)."""
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    await cd._emit_genome_event(supa, "p", "u", {"verzija": 1}, "upload_trigger")
    assert chain.insert.call_args[0][0]["payload"]["trigger"] == "upload_trigger"


@pytest.mark.anyio
async def test_emit_genome_event_swallows_errors():
    from routers import case_dna as cd

    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))

    # ne sme da baci — greska u event-u ne sme da obori glavni zahtev
    await cd._emit_genome_event(supa, "predmet-1", "user-1", {"verzija": 1}, "upload_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# services/event_bus.py — EventType.GENOME_UPDATED durable-outbox round-trip
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_updated_event_type_value_is_stable():
    """Zaključava string vrednost — dispatch_pending_events radi EventType(raw_type),
    tipfeler u vrednosti bi tiho pretvorio svaki Genome event u 'unknown_type'."""
    from services.event_bus import EventType
    assert EventType.GENOME_UPDATED.value == "GenomeUpdated"


@pytest.mark.anyio
async def test_dispatch_pending_events_recognizes_genome_updated_with_no_handlers():
    """Faza 1.2 (audit trail) jos ne postoji — 0 handlera registrovanih za
    GENOME_UPDATED je OČEKIVANO stanje posle 1.1 samog. Dispatch i dalje mora
    da prepozna tip (ne sme da padne u 'nepoznat_tip' granu) i da markira red
    kao dispecovan."""
    from services import event_bus as eb

    row = {"id": "evt-genome-1", "event_type": "GenomeUpdated", "user_id": "u-1",
           "predmet_id": "p-1", "payload": {"verzija": 2, "trigger": "upload_trigger"},
           "dispatch_attempts": 0}

    marked = []
    def _table(name):
        chain = _make_chain([row] if name == "events" else [])
        def _capture(payload):
            marked.append(payload)
            return chain
        chain.update = MagicMock(side_effect=_capture)
        return chain
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.dispatch_pending_events()

    assert result["nepoznat_tip"] == 0
    assert result["dispecovano"] == 1
    assert any("dispatched_at" in m for m in marked)
