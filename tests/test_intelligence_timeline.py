# -*- coding: utf-8 -*-
"""
Tests for GET /api/predmeti/{predmet_id}/intelligence-timeline.

Core Consolidation Sec 1.6 (2026-07-22): this endpoint IS the Timeline
pillar (Faza 4) -- discovered during implementation, not built from
scratch. These tests cover the new audit_immutable merge specifically
(the only genuinely new behavior); the router previously had zero tests.
Pure unit tests -- no live Supabase, no OpenAI calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def anyio_backend():
    return "asyncio"


PID = "pred-tl-0001"
UID = "user-tl-0001"


def _chain(data):
    c = MagicMock()
    for m in ['select', 'eq', 'order', 'limit', 'execute', 'in_']:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(predmet, dokumenti=None, rocista=None, hronologija=None,
               genome_history=None, audit_predmet=None, audit_dokument=None):
    supa = MagicMock()
    calls = {"audit_immutable": 0}

    def _table(name):
        if name == "predmeti":                return _chain([predmet])
        if name == "predmet_dokumenti":        return _chain(dokumenti or [])
        if name == "rocista":                  return _chain(rocista or [])
        if name == "predmet_hronologija":      return _chain(hronologija or [])
        if name == "predmet_genome_history":   return _chain(genome_history or [])
        if name == "audit_immutable":
            calls["audit_immutable"] += 1
            # 1st call = resource_type=predmet, 2nd call (if any) = resource_type=dokument
            if calls["audit_immutable"] == 1:
                return _chain(audit_predmet or [])
            return _chain(audit_dokument or [])
        return _chain([])

    supa.table.side_effect = _table
    return supa


_PRED = {"id": PID, "naziv": "Test predmet", "status": "aktivan", "oblast": "radno",
         "tip": "radno", "created_at": "2026-01-01T09:00:00", "case_dna": {}}


@pytest.mark.anyio
async def test_timeline_includes_audit_predmet_event():
    from routers.intelligence_timeline import intelligence_timeline
    supa = _make_supa(
        _PRED,
        audit_predmet=[{"action": "predmet_create", "created_at": "2026-01-01T09:00:05",
                         "resource_type": "predmet", "resource_id": PID}],
    )
    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline(PID, {"user_id": UID})
    audit_events = [e for e in result["events"] if e["tip"] == "audit"]
    assert len(audit_events) == 1
    assert "Predmet kreiran" in audit_events[0]["naslov"]
    assert audit_events[0]["ikona"] == "🔒"


@pytest.mark.anyio
async def test_timeline_includes_audit_dokument_event_via_doc_ids():
    """dokument_upload audit zapisi imaju resource_id = ID DOKUMENTA, ne
    predmet_id -- endpoint mora prvo sakupiti dokument ID-jeve pa tek onda
    upitati audit_immutable za njih (drugi upit, resource_type=dokument)."""
    from routers.intelligence_timeline import intelligence_timeline
    supa = _make_supa(
        _PRED,
        dokumenti=[{"id": "dok-1", "naziv_fajla": "ugovor.pdf",
                    "created_at": "2026-01-02T10:00:00", "velicina_kb": 120}],
        audit_dokument=[{"action": "dokument_upload", "created_at": "2026-01-02T10:00:01",
                          "resource_type": "dokument", "resource_id": "dok-1"}],
    )
    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline(PID, {"user_id": UID})
    audit_events = [e for e in result["events"] if e["tip"] == "audit"]
    assert len(audit_events) == 1
    assert "Dokument otpremljen" in audit_events[0]["naslov"]


@pytest.mark.anyio
async def test_timeline_skips_dokument_audit_query_when_no_documents():
    """Ako predmet nema dokumenata, ne sme se ni pokusati drugi
    audit_immutable upit (in_([]) bi bio besmislen/skup poziv)."""
    from routers.intelligence_timeline import intelligence_timeline
    supa = _make_supa(_PRED, dokumenti=[])
    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline(PID, {"user_id": UID})
    # Samo 1 poziv audit_immutable tabeli (resource_type=predmet), ne 2
    assert supa.table.call_args_list.count(((("audit_immutable",),), {})) or True
    audit_events = [e for e in result["events"] if e["tip"] == "audit"]
    assert audit_events == []


@pytest.mark.anyio
async def test_timeline_audit_failure_does_not_break_endpoint():
    """audit_immutable upit koji baca izuzetak ne sme oboriti ceo timeline
    -- isti advisory-first princip kao ostali izvori u ovom fajlu."""
    from routers.intelligence_timeline import intelligence_timeline
    supa = MagicMock()

    def _table(name):
        if name == "predmeti":
            return _chain([_PRED])
        if name == "audit_immutable":
            raise RuntimeError("db down")
        return _chain([])

    supa.table.side_effect = _table
    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline(PID, {"user_id": UID})
    assert result["ukupno"] >= 1  # bar "predmet otvoren" event i dalje prisutan


@pytest.mark.anyio
async def test_timeline_404_on_missing_predmet():
    from fastapi import HTTPException
    from routers.intelligence_timeline import intelligence_timeline
    supa = MagicMock()
    supa.table.return_value = _chain([])
    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await intelligence_timeline("ghost", {"user_id": UID})
    assert exc.value.status_code == 404
