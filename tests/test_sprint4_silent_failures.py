# -*- coding: utf-8 -*-
"""
Sprint 4 — silent failures that returned a success-shaped value.

The scan counted 220 of these. This sprint takes the four where the swallowed
value is then presented to a lawyer as a fact, rather than merely losing a log
line. Behavioural throughout.
"""
import asyncio
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── S4-1: an unparsable subscription expiry was invisible ──────────────────

def test_unparsable_expiry_is_reported_at_error_level(caplog):
    """Direction deliberately unchanged: an unparsable value is OUR corrupt
    data, and locking a paying lawyer out of their own case file mid-case is
    worse than a lapsed legacy account keeping Professional for a while.

    The defect was visibility -- logger.warning in a system with no alerting is
    a message nobody reads. It must now be findable."""
    from shared.permissions import _is_expired

    with caplog.at_level(logging.ERROR, logger="vindex.permissions"):
        result = _is_expired("not-a-date-at-all")

    assert result is False, "direction unchanged: do not lock out a paying user"
    assert caplog.records, "the corruption must be visible at ERROR"
    assert "NEPARSIV" in caplog.records[-1].getMessage()


def test_expiry_logic_itself_still_works():
    """No regression on the part that was always right."""
    from datetime import datetime, timedelta, timezone
    from shared.permissions import _is_expired

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    assert _is_expired(past) is True
    assert _is_expired(future) is False
    assert _is_expired(None) is False


# ── S4-3: a retrieval outage was rendered as a claim about the law ─────────

def test_retrieval_failure_is_distinguishable_from_not_found():
    """_direktan_fetch_clana returned [] both when an article genuinely is not
    in the corpus and when Pinecone was unreachable."""
    from app.services.retrieve import RetrievalUnavailable
    import app.services.retrieve as r

    with patch.object(r, "_ugradi_query", side_effect=RuntimeError("pinecone down")):
        # default: unchanged for the ~15 existing callers
        assert r._direktan_fetch_clana("Član 5", "zoo") == []
        # opt-in: the caller that makes a legal claim can tell the difference
        with pytest.raises(RetrievalUnavailable):
            r._direktan_fetch_clana("Član 5", "zoo", raise_on_error=True)


@pytest.mark.anyio
async def test_quality_gate_does_not_call_a_citation_invented_when_it_could_not_check():
    """_verify_citation returning False renders as citations_verified: 0, which
    reads as 'the AI invented these articles'. That is a serious accusation to
    make because Pinecone was briefly unreachable."""
    from app.services.retrieve import RetrievalUnavailable
    import services.quality_gate as qg

    with patch("app.services.retrieve._direktan_fetch_clana",
               side_effect=RetrievalUnavailable("pinecone down")):
        with pytest.raises(RetrievalUnavailable):
            await qg._verify_citation("142")


@pytest.mark.anyio
async def test_quality_gate_still_returns_false_for_a_genuinely_absent_article():
    """No regression: a real 'not in corpus' must still be reported as such."""
    import services.quality_gate as qg

    with patch("app.services.retrieve._direktan_fetch_clana", return_value=[]):
        assert await qg._verify_citation("999999") is False


# ── S4-4: an incomplete GDPR export shipped as complete ───────────────────

@pytest.mark.anyio
async def test_export_refuses_to_ship_a_partial_archive():
    """_fetch swallowed every read error into [], and the endpoint shipped the
    ZIP regardless -- so the data subject received an export MISSING ENTIRE
    TABLES, labelled by its own README as a complete ZZPL čl. 36 / GDPR čl. 20
    portability export. Completeness is the whole point of the right."""
    from fastapi import HTTPException
    import routers.data_export as de

    supa = MagicMock()
    supa.table.side_effect = RuntimeError("db unreachable")

    with patch.object(de, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await de.export_complete(user={"user_id": "u1", "email": "a@b.rs"})

    assert exc.value.status_code == 503
    assert "NEPOTPUN" in exc.value.detail.upper() or "nije kompletan" in exc.value.detail


@pytest.mark.anyio
async def test_export_still_succeeds_when_every_table_reads():
    """No regression: a healthy export must still be produced."""
    import routers.data_export as de

    async def _noop_log(*a, **k):
        return None

    ok = MagicMock()
    ok.data = [{"id": "1"}]
    chain = MagicMock()
    chain.select.return_value.eq.return_value.order.return_value.execute.return_value = ok
    supa = MagicMock()
    supa.table.return_value = chain

    with patch.object(de, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=_noop_log):
        resp = await de.export_complete(user={"user_id": "u1", "email": "a@b.rs"})

    assert resp.media_type == "application/zip"
