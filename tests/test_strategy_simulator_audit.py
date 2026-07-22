# -*- coding: utf-8 -*-
"""
G-033 (D28, VINDEX_OPERATIONAL_GAP_REGISTER.md) — routers/strategy_simulator.py
had zero log_action/audit_immutable calls, and no way to trace which Genome
version informed a given simulation result. This adds a completion-time audit
entry (reusing the already-whitelisted 'ai_analiza_complete' action) and a
genome_verzija field carried on the result itself.

Founder's explicit review criteria (2026-07-22), one test per question:
1. genome_verzija reflects the SNAPSHOT actually used, not a fresh re-query --
   test_genome_verzija_matches_snapshot_used_for_simulation.
2. Audit exists only after a SUCCESSFUL simulation, not on failure --
   test_no_audit_on_gpt_failure.
3. Implementation is purely passive (no behavior change) -- every test here
   asserts the pre-existing response shape is untouched apart from the new
   additive genome_verzija key.
4. sledeci_potez never fetches Genome, so it must NOT fabricate a
   genome_verzija -- test_sledeci_potez_audit_has_no_genome_verzija.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    """slowapi's @limiter.limit decorator does isinstance(request, Request) --
    a plain MagicMock() fails that check, spec'ing against Request passes it."""
    return MagicMock(spec=Request)


def _chain(execute_return):
    """execute_return: either a single MagicMock(data=...) or a list of them
    (consumed in call order for chains hit more than once)."""
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit",
                 "is_", "in_", "lt", "single", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    if isinstance(execute_return, list):
        chain.execute = MagicMock(side_effect=execute_return)
    else:
        chain.execute = MagicMock(return_value=execute_return)
    return chain


_PREDMET_ROW = {"id": "predmet-1", "naziv": "Test predmet", "tip": "radni_spor",
                "opis": "opis", "status": "aktivan", "stranke": []}

_GENOME_ANALIZA = {
    "slabosti": ["nedostatak svedoka"],
    "protivnikovi_odgovori": [{"potez": "osporiti visinu", "verovatnoca": "srednja", "kako_kontrirati": "dodatni dokazi"}],
    "kontra_strategija": "priprema dodatnih dokaza",
    "zabrane": ["ne priznavati krivicu"],
    "rizik_score": 6,
}


async def _run_nova_partija(genome_row, log_action_mock, predmet_row=None):
    from routers import strategy_simulator as ss
    from pydantic import BaseModel

    predmeti_chain = _chain([
        MagicMock(data=[predmet_row or _PREDMET_ROW]),   # _dohvati_predmet
        MagicMock(data=genome_row),                       # genome fetch (.single())
    ])
    partije_chain = _chain(MagicMock(data=None))

    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return predmeti_chain
        if name == "simulator_partije":
            return partije_chain
        return _chain(MagicMock(data=None))
    supa.table = MagicMock(side_effect=_table)

    req = ss.NovaPartijaRequest(predmet_id="predmet-1", moja_strategija="x" * 25)
    user = {"user_id": "user-1", "email": "test@test.com"}

    with patch.object(ss, "_get_supa", return_value=supa), \
         patch.object(ss, "_audit", new=AsyncMock()), \
         patch.object(ss, "_pozovi_gpt", return_value=dict(_GENOME_ANALIZA)), \
         patch.object(ss, "log_action", new=log_action_mock), \
         patch.object(ss.UsageService, "consume", new=AsyncMock(return_value=10)):
        result = await ss.nova_partija(req, _fake_request(), user)

    return result


@pytest.mark.anyio
async def test_genome_verzija_matches_snapshot_used_for_simulation():
    """Criteria 1 + 4 (True case): genome_verzija in both the audit call and
    the response must equal the version of the Genome that was actually
    fetched and sent to GPT for this specific simulation."""
    log_action_mock = AsyncMock()
    genome_row = {"case_dna": {"verzija": 17, "pravna_teorija": {}, "snaga_predmeta_procent": 70}}

    result = await _run_nova_partija(genome_row, log_action_mock)

    assert result["genome_verzija"] == 17

    log_action_mock.assert_called_once()
    _, kwargs = log_action_mock.call_args
    assert kwargs["metadata"]["genome_verzija"] == 17
    assert kwargs["resource_type"] == "simulator_partija"
    assert kwargs["metadata"]["predmet_id"] == "predmet-1"


@pytest.mark.anyio
async def test_no_genome_verzija_when_genome_absent():
    """genome_verzija must be None (not a fabricated default like 1) when no
    Genome exists for the predmet."""
    log_action_mock = AsyncMock()
    genome_row = {"case_dna": None}

    result = await _run_nova_partija(genome_row, log_action_mock)

    assert result["genome_verzija"] is None
    _, kwargs = log_action_mock.call_args
    assert kwargs["metadata"]["genome_verzija"] is None


@pytest.mark.anyio
async def test_response_shape_unchanged_apart_from_genome_verzija():
    """Criterion 3 (passivity): existing response fields must be untouched --
    only the new additive genome_verzija key is new."""
    log_action_mock = AsyncMock()
    genome_row = {"case_dna": {"verzija": 3}}

    result = await _run_nova_partija(genome_row, log_action_mock)

    assert result["analiza"]["slabosti"] == _GENOME_ANALIZA["slabosti"]
    assert result["analiza"]["kontra_strategija"] == _GENOME_ANALIZA["kontra_strategija"]
    assert result["analiza"]["rizik_score"] == _GENOME_ANALIZA["rizik_score"]
    assert result["credits_remaining"] == 10
    assert "partija_id" in result


@pytest.mark.anyio
async def test_no_audit_on_gpt_failure():
    """Criterion 2: no audit entry for a failed/interrupted simulation."""
    from routers import strategy_simulator as ss
    from fastapi import HTTPException

    predmeti_chain = _chain(MagicMock(data=[_PREDMET_ROW]))
    supa = MagicMock()
    supa.table = MagicMock(return_value=predmeti_chain)

    req = ss.NovaPartijaRequest(predmet_id="predmet-1", moja_strategija="x" * 25)
    user = {"user_id": "user-1", "email": "test@test.com"}
    log_action_mock = AsyncMock()

    def _boom(messages):
        raise RuntimeError("OpenAI down")

    with patch.object(ss, "_get_supa", return_value=supa), \
         patch.object(ss, "_audit", new=AsyncMock()), \
         patch.object(ss, "_pozovi_gpt", side_effect=_boom), \
         patch.object(ss, "log_action", new=log_action_mock), \
         patch.object(ss.UsageService, "consume", new=AsyncMock(return_value=10)):
        with pytest.raises(HTTPException):
            await ss.nova_partija(req, _fake_request(), user)

    log_action_mock.assert_not_called()


@pytest.mark.anyio
async def test_sledeci_potez_audit_has_no_genome_verzija():
    """Criterion 4: sledeci_potez never reads Genome, so its audit entry must
    NOT contain a fabricated genome_verzija key."""
    from routers import strategy_simulator as ss

    partija_row = {"id": "partija-1", "predmet_id": "predmet-1", "user_id": "user-1",
                   "istorija": '[{"redni_broj": 1, "tip": "nova_partija", "analiza": {}, "moja_strategija": "x"}]',
                   "status": "aktivna"}
    partije_chain = _chain(MagicMock(data=[partija_row]))
    supa = MagicMock()
    supa.table = MagicMock(return_value=partije_chain)

    req = ss.SledeciPotezRequest(partija_id="partija-1", novi_potez="y" * 15)
    user = {"user_id": "user-1", "email": "test@test.com"}
    log_action_mock = AsyncMock()

    with patch.object(ss, "_get_supa", return_value=supa), \
         patch.object(ss, "_audit", new=AsyncMock()), \
         patch.object(ss, "_pozovi_gpt", return_value=dict(_GENOME_ANALIZA)), \
         patch.object(ss, "log_action", new=log_action_mock), \
         patch.object(ss.UsageService, "consume", new=AsyncMock(return_value=9)):
        await ss.sledeci_potez(req, _fake_request(), user)

    log_action_mock.assert_called_once()
    _, kwargs = log_action_mock.call_args
    assert "genome_verzija" not in kwargs["metadata"]
    assert kwargs["metadata"]["trigger"] == "sledeci_potez"
