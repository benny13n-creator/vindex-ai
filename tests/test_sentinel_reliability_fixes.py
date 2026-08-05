# -*- coding: utf-8 -*-
"""
Project Sentinel (2026-08-03) — regression tests for reliability fixes.

Covers:
1. api.py::kreiraj_predmet now writes PREDMET_KREIRAN durably (events table
   insert) instead of the old in-process-only emit() -- a crash between the
   predmeti insert and the old fire-and-forget asyncio.create_task completing
   used to silently and permanently drop the entire Case Pipeline for that
   case (Sentinel Phase 2, event_bus_hardening investigation, Finding 1).
2. api.py::predmet_upload_auto_analyze no longer returns a false HTTP 200
   "success" (auto_analyzed=true + a full AI legal analysis) for a document
   whose predmet_dokumenti row failed to insert (Sentinel Phase 3,
   failure_recovery investigation, §8 -- the single most concretely proven
   finding of that investigation).
3. services/event_bus.py::on_document_job_failed -- DocumentJobFailed used
   to dispatch and be silently discarded (zero subscribers); a permanently
   failed OCR/intake job now produces a real proactive_alerts row.

Mirrors tests/test_sec001_predmet_ownership.py's api.py auth-mocking pattern
and tests/test_lawyerday_predmet_upload_images.py's upload-pipeline mocking
pattern.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import types
import json as _json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import UploadFile

import api


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user(uid: str = "user-0000-0000-0000-000000000001", email: str = "advokat@vindex.rs"):
    return types.SimpleNamespace(id=uid, email=email)


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "insert", "execute", "single", "order", "limit", "is_", "gte", "or_"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock()
    r.data = data
    c.execute = MagicMock(return_value=r)
    return c


# ═══════════════════════════════════════════════════════════════════════════
# 1. kreiraj_predmet — PREDMET_KREIRAN durable outbox insert
# ═══════════════════════════════════════════════════════════════════════════

def _req_json(body: dict, path: str = "/api/predmeti"):
    body_bytes = _json.dumps(body).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


@pytest.mark.anyio
async def test_kreiraj_predmet_writes_predmet_kreiran_to_durable_outbox():
    events_insert_calls = []

    def _table(name):
        if name == "predmeti":
            return _chain([{"id": "novi-predmet-1", "naziv": "Test predmet", "status": "aktivan"}])
        if name == "events":
            chain = MagicMock()

            def _insert(payload):
                events_insert_calls.append(payload)
                return chain
            chain.insert = MagicMock(side_effect=_insert)
            r = MagicMock(); r.data = [{"id": "evt-1"}]
            chain.execute = MagicMock(return_value=r)
            return chain
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    req = _req_json({"naziv": "Test predmet", "tip": "parnicno"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        result = await api.kreiraj_predmet(req, "Bearer fake-token")

    assert result["predmet"]["id"] == "novi-predmet-1"
    assert len(events_insert_calls) == 1
    payload = events_insert_calls[0]
    assert payload["event_type"] == "predmet_kreiran"
    assert payload["predmet_id"] == "novi-predmet-1"
    assert payload["user_id"] == "user-1"


@pytest.mark.anyio
async def test_kreiraj_predmet_still_succeeds_if_durable_event_insert_fails():
    """Same guarantee the old emit()-based code had: a failure emitting the
    pipeline trigger must never fail the predmet-creation response itself."""
    def _table(name):
        if name == "predmeti":
            return _chain([{"id": "novi-predmet-2", "naziv": "Test", "status": "aktivan"}])
        if name == "events":
            chain = MagicMock()
            chain.insert = MagicMock(side_effect=Exception("DB down"))
            return chain
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    req = _req_json({"naziv": "Test predmet", "tip": "opsti"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        result = await api.kreiraj_predmet(req, "Bearer fake-token")

    assert result["predmet"]["id"] == "novi-predmet-2"


# ═══════════════════════════════════════════════════════════════════════════
# 2. predmet_upload_auto_analyze — no false success on predmet_dokumenti
#    insert failure
# ═══════════════════════════════════════════════════════════════════════════

def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-1/upload", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _upload_file(filename: str, content_type: str, content: bytes = b"fake bytes for test") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


async def _fake_permission_dependency(user=None):
    return user


def _supa_upload_insert_fails(predmet_id: str = "pred-1"):
    """predmeti ownership check succeeds; predmet_dokumenti SELECT (redni_broj
    lookup) succeeds with empty data; predmet_dokumenti INSERT always raises,
    simulating a DB failure right after Pinecone ingestion already succeeded."""
    def _table(name):
        if name == "predmeti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.single.return_value = c
            r = MagicMock(); r.data = {"id": predmet_id, "naziv": "Test predmet", "tip": "opsti"}
            c.execute = MagicMock(return_value=r)
            return c
        if name == "predmet_dokumenti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.order.return_value = c
            c.limit.return_value = c
            sel_r = MagicMock(); sel_r.data = []
            c.execute = MagicMock(return_value=sel_r)  # only reached via select() chain
            insert_chain = MagicMock()
            insert_chain.execute = MagicMock(side_effect=Exception("predmet_dokumenti insert down"))
            c.insert = MagicMock(return_value=insert_chain)
            return c
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_upload_raises_honest_error_when_document_insert_fails_after_pinecone_success():
    supa = _supa_upload_insert_fails()

    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_fake_permission_dependency), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False, None)), \
         patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1):
        with pytest.raises(Exception) as exc_info:
            await api.predmet_upload_auto_analyze(
                "pred-1", _fake_request(),
                _upload_file("tuzba.pdf", "application/pdf"),
                authorization="Bearer test-token",
            )

    assert getattr(exc_info.value, "status_code", None) == 500


# ═══════════════════════════════════════════════════════════════════════════
# 3. on_document_job_failed — DocumentJobFailed no longer silently discarded
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_on_document_job_failed_creates_proactive_alert():
    from services.event_bus import Event, EventType, on_document_job_failed

    alert_inserts = []

    def _table(name):
        if name == "intake_jobs":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.limit.return_value = c
            r = MagicMock()
            r.data = [{
                "uploaded_by": "user-1", "predmet_id": "pred-1",
                "storage_path": "uploads/tuzba.pdf", "last_error": "OCR service unavailable",
            }]
            c.execute = MagicMock(return_value=r)
            return c
        if name == "proactive_alerts":
            chain = MagicMock()

            def _insert(payload):
                alert_inserts.append(payload)
                return chain
            chain.insert = MagicMock(side_effect=_insert)
            r = MagicMock(); r.data = [{"id": "alert-1"}]
            chain.execute = MagicMock(return_value=r)
            return chain
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    event = Event(type=EventType.DOCUMENT_JOB_FAILED, user_id="", predmet_id=None,
                  payload={"intake_job_id": "job-1", "attempts": 5, "error": "OCR service unavailable"})

    with patch("shared.deps._get_supa", return_value=supa):
        await on_document_job_failed(event)

    assert len(alert_inserts) == 1
    alert = alert_inserts[0]
    assert alert["user_id"] == "user-1"
    assert alert["predmet_id"] == "pred-1"
    assert "tuzba.pdf" in alert["naslov"]
    assert alert["urgentnost"] == "visoka"


@pytest.mark.anyio
async def test_on_document_job_failed_skips_alert_when_job_owner_unresolvable():
    """Defensive: if intake_jobs has no matching row (or no uploaded_by), we
    must not crash and must not insert an alert with a null user_id (NOT NULL
    column) -- log-and-skip is the only safe behavior."""
    from services.event_bus import Event, EventType, on_document_job_failed

    def _table(name):
        if name == "intake_jobs":
            return _chain([])
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    event = Event(type=EventType.DOCUMENT_JOB_FAILED, user_id="", predmet_id=None,
                  payload={"intake_job_id": "job-missing"})

    with patch("shared.deps._get_supa", return_value=supa):
        await on_document_job_failed(event)  # must not raise

    proactive_table = supa.table("proactive_alerts")
    proactive_table.insert.assert_not_called()


def test_document_job_failed_is_registered_in_event_bus_defaults():
    from services.event_bus import bus, EventType, on_document_job_failed
    assert on_document_job_failed in bus._handlers[EventType.DOCUMENT_JOB_FAILED]
