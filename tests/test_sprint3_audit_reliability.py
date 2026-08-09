# -*- coding: utf-8 -*-
"""
Sprint 3 — the AI audit trail was written through unreferenced tasks.

The intended Sprint 3 was "raise audit link coverage to >=95%". Measuring first
changed the plan, and the measurement is worth stating because it is the whole
justification for what this file tests instead.

Measured on this tree (2026-08-09): 87 provider call sites across 61 files; 19
of those 61 files use case_context; the `_pozovi_*` helper shape exists in 56 of
61. A decorator over that helper shape therefore looked like the one-edit fix --
until you notice that a decorator there cannot supply `predmet_id`, which is the
binding constraint and which only exists at the endpoint.

Then a larger problem surfaced underneath: shared/ai_client.py dispatched EVERY
provenance row with a bare loop.create_task(coro), and security/ai_forensics.py
did the same for _persist. So the AI audit trail itself was written through the
exact pattern S1-1 exists to remove -- no strong reference, no observed failure.

That inverts the priority. Adding case linkage to 50 endpoints raises a number
that is conditional on rows nobody is holding actually being written. Making the
writer reliable is worth more than making the metric larger, and it is three
edits rather than fifty.
"""
import ast
import asyncio
import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean_registry():
    from shared import bg
    bg._BG.clear()
    yield
    bg._BG.clear()


def _real_create_task_calls(path: str) -> int:
    """Counts genuine `*.create_task(...)` calls from the AST.

    Not a substring count: both files now carry comments that quote the old
    call shape while explaining why it was removed, and a text search is fooled
    by them -- as it was, twice, during Sprint 2.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    return sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_task"
    )


# ── the writers themselves ─────────────────────────────────────────────────

def test_provenance_writer_no_longer_uses_an_unreferenced_task():
    """shared/ai_client.py dispatched every provenance row -- for all 87
    provider call sites, success and failure alike -- with a bare
    loop.create_task(coro). The row could be collected before it was written and
    any failure inside log_provenance_from_wrapper was never observed."""
    assert _real_create_task_calls("shared/ai_client.py") == 0


def test_forensics_writer_no_longer_uses_an_unreferenced_task():
    """security/ai_forensics.py::__aexit__ persisted the completed AI call the
    same way."""
    assert _real_create_task_calls("security/ai_forensics.py") == 0


@pytest.mark.anyio
async def test_a_provenance_row_is_registered_while_it_is_being_written():
    """The point of the change, driven rather than asserted from source: the
    dispatch must land in the registry so drain() can wait for it and a failure
    is logged instead of lost."""
    import shared.ai_client as ac
    from shared import bg

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_write(**_kwargs):
        started.set()
        await release.wait()

    fake_self = MagicMock()
    with patch("security.ai_forensics.log_provenance_from_wrapper", _slow_write):
        ac._capture_chat_provenance(
            fake_self,
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]},
            None, 12, error=RuntimeError("provider down"),
        )
        await started.wait()
        assert bg.pending_count() == 1, (
            "the provenance write must be registered, or drain() cannot wait for it"
        )
        release.set()
        await asyncio.sleep(0)

    await bg.drain(timeout=2.0)
    assert bg.pending_count() == 0


@pytest.mark.anyio
async def test_a_failing_provenance_write_is_logged_not_lost(caplog):
    """Before: an exception inside the provenance write surfaced at best as an
    'exception was never retrieved' warning at GC time. An audit trail whose
    write failures are invisible is not an audit trail."""
    import logging
    import shared.ai_client as ac
    from shared import bg

    async def _boom(**_kwargs):
        raise RuntimeError("forensics table unreachable")

    fake_self = MagicMock()
    with caplog.at_level(logging.ERROR, logger="vindex.bg"), \
         patch("security.ai_forensics.log_provenance_from_wrapper", _boom):
        ac._capture_chat_provenance(
            fake_self,
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]},
            None, 5,
        )
        await bg.drain(timeout=2.0)

    assert any("ai_provenance:write" in r.getMessage() for r in caplog.records), (
        "a failed provenance write must name itself in the log"
    )


# ── no regression in what the record contains ──────────────────────────────

@pytest.mark.anyio
async def test_the_failure_path_still_records_status_error():
    """Worth pinning: the failure path already carried status='error' and
    error_message centrally, for every call site. That is the part that was
    already right, and the change above must not disturb it."""
    import shared.ai_client as ac

    seen = {}

    async def _capture(**kwargs):
        seen.update(kwargs)

    fake_self = MagicMock()
    with patch("security.ai_forensics.log_provenance_from_wrapper", _capture):
        ac._capture_chat_provenance(
            fake_self,
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "pitanje"}]},
            None, 42, error=ValueError("boom"),
        )
        from shared import bg
        await bg.drain(timeout=2.0)

    assert seen.get("status") == "error"
    assert "boom" in (seen.get("error_message") or "")
    assert seen.get("latency_ms") == 42


@pytest.mark.anyio
async def test_success_path_still_records_status_success():
    import shared.ai_client as ac

    seen = {}

    async def _capture(**kwargs):
        seen.update(kwargs)

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "odgovor"
    resp.model = "gpt-4o"
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    fake_self = MagicMock()
    with patch("security.ai_forensics.log_provenance_from_wrapper", _capture):
        ac._capture_chat_provenance(
            fake_self,
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "pitanje"}]},
            resp, 7,
        )
        from shared import bg
        await bg.drain(timeout=2.0)

    assert seen.get("status") == "success"
    assert seen.get("error_message") is None
