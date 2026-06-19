# -*- coding: utf-8 -*-
"""
Tests za routers/jobs.py — in-memory async job queue.

Pokriva:
  - create_job / get_job / update_job lifecycle
  - ownership check (drugi user ne vidi job)
  - TTL čišćenje
  - GET /api/jobs/{job_id} endpoint
  - run_in_background uspeh i greška
"""
import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

@pytest.fixture
def anyio_backend():
    return "asyncio"

from routers.jobs import (
    _jobs,
    create_job,
    get_job,
    update_job,
    run_in_background,
    poll_job,
    _cleanup,
    _JOB_TTL_S,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _user(uid: str = "user-abc"):
    return {"user_id": uid}


def _clear_jobs():
    _jobs.clear()


# ─── Unit: create_job ────────────────────────────────────────────────────────

def test_create_job_returns_id():
    _clear_jobs()
    jid = create_job("user-1", "analiza")
    assert jid in _jobs
    assert _jobs[jid]["tip"] == "analiza"
    assert _jobs[jid]["status"] == "pending"
    assert _jobs[jid]["user_id"] == "user-1"


def test_create_job_initial_result_none():
    _clear_jobs()
    jid = create_job("user-1", "test")
    j = _jobs[jid]
    assert j["result"] is None
    assert j["error"] is None


# ─── Unit: update_job ────────────────────────────────────────────────────────

def test_update_job_to_running():
    _clear_jobs()
    jid = create_job("user-1", "test")
    update_job(jid, "running")
    assert _jobs[jid]["status"] == "running"


def test_update_job_to_done_with_result():
    _clear_jobs()
    jid = create_job("user-1", "test")
    update_job(jid, "done", result={"analiza": "ok"})
    j = _jobs[jid]
    assert j["status"] == "done"
    assert j["result"] == {"analiza": "ok"}


def test_update_job_to_error():
    _clear_jobs()
    jid = create_job("user-1", "test")
    update_job(jid, "error", error="GPT timeout")
    j = _jobs[jid]
    assert j["status"] == "error"
    assert j["error"] == "GPT timeout"


def test_update_nonexistent_job_no_crash():
    """update_job na nepostojećem job_id ne sme da baci izuzetak."""
    update_job("nonexistent-id", "running")  # ne crasha


# ─── Unit: get_job ownership ──────────────────────────────────────────────────

def test_get_job_owner_ok():
    _clear_jobs()
    jid = create_job("user-A", "test")
    j = get_job(jid, "user-A")
    assert j is not None
    assert j["id"] == jid


def test_get_job_wrong_user_returns_none():
    _clear_jobs()
    jid = create_job("user-A", "test")
    j = get_job(jid, "user-B")
    assert j is None


def test_get_job_nonexistent_returns_none():
    _clear_jobs()
    j = get_job("fake-id", "user-A")
    assert j is None


# ─── Unit: TTL cleanup ───────────────────────────────────────────────────────

def test_cleanup_removes_stale_job():
    _clear_jobs()
    jid = create_job("user-1", "test")
    # Manuelno postavi created_at u prošlost
    _jobs[jid]["created_at"] = time.time() - _JOB_TTL_S - 1
    _cleanup()
    assert jid not in _jobs


def test_cleanup_keeps_fresh_job():
    _clear_jobs()
    jid = create_job("user-1", "test")
    _cleanup()
    assert jid in _jobs


# ─── Unit: run_in_background ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_run_in_background_success():
    _clear_jobs()
    jid = create_job("user-1", "test")

    async def _fake_fn():
        return {"ok": True}

    await run_in_background(jid, _fake_fn)
    j = _jobs[jid]
    assert j["status"] == "done"
    assert j["result"] == {"ok": True}
    assert j["error"] is None


@pytest.mark.anyio
async def test_run_in_background_error():
    _clear_jobs()
    jid = create_job("user-1", "test")

    async def _failing_fn():
        raise ValueError("Simulovana greška")

    await run_in_background(jid, _failing_fn)
    j = _jobs[jid]
    assert j["status"] == "error"
    assert "Simulovana greška" in j["error"]


# ─── Endpoint: GET /api/jobs/{job_id} ────────────────────────────────────────

@pytest.mark.anyio
async def test_poll_job_pending():
    _clear_jobs()
    jid = create_job("user-1", "analiza")
    result = await poll_job(jid, _user("user-1"))
    assert result["status"] == "pending"
    assert result["result"] is None
    assert result["error"] is None
    assert "elapsed_s" in result


@pytest.mark.anyio
async def test_poll_job_done_returns_result():
    _clear_jobs()
    jid = create_job("user-1", "analiza")
    update_job(jid, "done", result={"tekst": "analiza gotova"})
    result = await poll_job(jid, _user("user-1"))
    assert result["status"] == "done"
    assert result["result"] == {"tekst": "analiza gotova"}


@pytest.mark.anyio
async def test_poll_job_error_hides_result():
    _clear_jobs()
    jid = create_job("user-1", "analiza")
    update_job(jid, "error", error="GPT error")
    result = await poll_job(jid, _user("user-1"))
    assert result["status"] == "error"
    assert result["error"] == "GPT error"
    assert result["result"] is None


@pytest.mark.anyio
async def test_poll_job_not_found_raises_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await poll_job("nonexistent", _user("user-1"))
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_poll_job_wrong_user_raises_404():
    _clear_jobs()
    jid = create_job("user-A", "analiza")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await poll_job(jid, _user("user-B"))
    assert exc.value.status_code == 404
