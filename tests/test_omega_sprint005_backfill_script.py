# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 005 (2026-08-06). Tests for
scripts/backfill_case_actions.py -- the OMEGA-014 fix (pre-Sprint-003
cases have zero case_actions rows until their next real event).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# services.event_bus must be imported before services.case_evolution in a
# fresh process, or the reverse triggers a circular-import ImportError
# (case_evolution imports event_bus at module level; event_bus's own
# EventBus() construction imports case_evolution.handle_case_changed back)
# -- this file is the first thing in the whole suite that reaches
# services.case_evolution only via a string-target unittest.mock.patch(),
# which doesn't pre-import it in dependency order the way a normal
# `from services.case_evolution import X` does everywhere else in this
# repo's own test suite. Same fragility, not introduced here.
import services.event_bus  # noqa: F401


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_backfill_calls_reconciliation_once_per_predmet():
    from scripts.backfill_case_actions import _main

    supa = MagicMock()
    supa.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "pred-1", "user_id": "user-1", "naziv": "A"},
              {"id": "pred-2", "user_id": "user-1", "naziv": "B"}]
    )

    calls = []
    async def _fake_refresh(event):
        calls.append(event.predmet_id)
        return "created=1 updated=0 closed=0"

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._consequence_refresh_case_actions", new=_fake_refresh):
        await _main(dry_run=False, only_user_id=None)

    assert calls == ["pred-1", "pred-2"]


@pytest.mark.anyio
async def test_backfill_dry_run_calls_nothing():
    from scripts.backfill_case_actions import _main

    supa = MagicMock()
    supa.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "pred-1", "user_id": "user-1", "naziv": "A"}]
    )

    fake_refresh = AsyncMock()
    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._consequence_refresh_case_actions", new=fake_refresh):
        await _main(dry_run=True, only_user_id=None)

    fake_refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_backfill_filters_by_user_id():
    from scripts.backfill_case_actions import _main

    supa = MagicMock()
    eq_chain = MagicMock()
    eq_chain.execute.return_value = MagicMock(data=[{"id": "pred-1", "user_id": "user-1", "naziv": "A"}])
    supa.table.return_value.select.return_value.eq.return_value = eq_chain

    fake_refresh = AsyncMock(return_value="created=0 updated=0 closed=0")
    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._consequence_refresh_case_actions", new=fake_refresh):
        await _main(dry_run=False, only_user_id="user-1")

    supa.table.return_value.select.return_value.eq.assert_called_with("user_id", "user-1")
    fake_refresh.assert_awaited_once()


@pytest.mark.anyio
async def test_backfill_continues_after_one_predmet_errors():
    from scripts.backfill_case_actions import _main

    supa = MagicMock()
    supa.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "pred-1", "user_id": "user-1", "naziv": "A"},
              {"id": "pred-2", "user_id": "user-1", "naziv": "B"}]
    )

    calls = []
    async def _fake_refresh(event):
        calls.append(event.predmet_id)
        if event.predmet_id == "pred-1":
            raise RuntimeError("db unavailable")
        return "created=1 updated=0 closed=0"

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.case_evolution._consequence_refresh_case_actions", new=_fake_refresh):
        await _main(dry_run=False, only_user_id=None)  # must not raise

    assert calls == ["pred-1", "pred-2"]  # pred-2 still processed despite pred-1's error
