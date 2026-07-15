# -*- coding: utf-8 -*-
"""
Tests for shared/intake_worker.py (Smart Intake Engine, Faza 0). Covers
tick lifecycle (claim/process/complete/fail), periodic reaping, heartbeat
recording, and graceful start/stop — the "not a temporary worker" bar the
founder explicitly set for Phase 0.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_tick_processes_claimed_job_and_completes():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-1", "attempts": 0, "max_attempts": 5}

    # _process() is the Phase 1A pipeline (classify/extract/persist) — this
    # test is about tick/queue lifecycle, not pipeline internals, so _process
    # itself is mocked (see tests/test_intake_worker_phase1a.py for pipeline
    # coverage).
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch.object(IntakeWorker, "_process", new=AsyncMock()), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()) as mock_complete, \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as mock_failed, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()) as mock_hb:
        did_work = await w._tick()

    assert did_work is True
    mock_complete.assert_awaited_once_with("job-1")
    mock_failed.assert_not_awaited()
    assert w.jobs_processed == 1
    assert w.jobs_failed == 0
    mock_hb.assert_awaited_once_with("test-worker", 1, 0)


@pytest.mark.anyio
async def test_tick_returns_false_and_still_heartbeats_when_no_job():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker")
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=None)), \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()) as mock_hb:
        did_work = await w._tick()

    assert did_work is False
    mock_hb.assert_awaited_once_with("test-worker", 0, 0)


@pytest.mark.anyio
async def test_tick_marks_failed_when_process_raises():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-2", "attempts": 1, "max_attempts": 5}

    async def _boom(self, job):
        raise RuntimeError("stage exploded")

    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch.object(IntakeWorker, "_process", _boom), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()) as mock_complete, \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as mock_failed, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        did_work = await w._tick()

    assert did_work is True
    mock_complete.assert_not_awaited()
    mock_failed.assert_awaited_once_with("job-2", "stage exploded", 1, 5)
    assert w.jobs_failed == 1
    assert w.jobs_processed == 0


@pytest.mark.anyio
async def test_tick_reaps_periodically_not_every_tick():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker", reap_every_n_ticks=3)
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=None)), \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()), \
         patch("shared.intake_worker.intake_queue.reap_stale_jobs", new=AsyncMock(return_value=0)) as mock_reap:
        await w._tick()  # tick 1
        await w._tick()  # tick 2
        mock_reap.assert_not_called()
        await w._tick()  # tick 3 -> reap fires
        mock_reap.assert_called_once_with(w.stale_after_s)


@pytest.mark.anyio
async def test_start_is_idempotent_no_duplicate_task():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker", poll_interval_s=0.01)
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=None)), \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        w.start()
        first_task = w._task
        w.start()  # second call must be a no-op
        assert w._task is first_task
        await w.stop(timeout_s=2.0)


@pytest.mark.anyio
async def test_stop_sets_shutdown_and_task_completes():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker", poll_interval_s=0.01)
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=None)), \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        w.start()
        await asyncio.sleep(0.05)  # let it tick at least once
        await w.stop(timeout_s=2.0)

    assert w._task is None
    assert w._shutdown.is_set()


def test_worker_id_default_format():
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker()
    assert ":" in w.worker_id  # hostname:pid:random shape, not empty/generic
