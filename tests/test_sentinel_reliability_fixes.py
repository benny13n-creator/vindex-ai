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
from fastapi import HTTPException, UploadFile

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


def _predmeti_chain_with_insert(row: dict):
    """Program Lambda, Certification 004: kreiraj_predmet now does a
    recent-duplicate SELECT (must find nothing) before the INSERT (must
    return the new row) -- unlike plain _chain(), this distinguishes the
    two so the dup-check doesn't see the insert's own future result."""
    c = MagicMock()
    for m in ["select", "eq", "gte", "limit"]:
        setattr(c, m, MagicMock(return_value=c))
    empty = MagicMock(); empty.data = []
    c.execute = MagicMock(return_value=empty)

    def _insert(_payload):
        ic = MagicMock()
        r = MagicMock(); r.data = [row]
        ic.execute = MagicMock(return_value=r)
        return ic
    c.insert = MagicMock(side_effect=_insert)
    return c


@pytest.mark.anyio
async def test_kreiraj_predmet_writes_predmet_kreiran_to_durable_outbox():
    events_insert_calls = []

    def _table(name):
        if name == "predmeti":
            return _predmeti_chain_with_insert({"id": "novi-predmet-1", "naziv": "Test predmet", "status": "aktivan"})
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
            return _predmeti_chain_with_insert({"id": "novi-predmet-2", "naziv": "Test", "status": "aktivan"})
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


@pytest.mark.anyio
async def test_kreiraj_predmet_rejects_near_duplicate_submission():
    """Program Lambda, Certification 004: a double-click / near-simultaneous
    resubmit with the same naziv must be rejected with a clean 409, not
    create a second predmet."""
    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [
                {"id": "pred-original", "created_at": "2026-08-06T12:00:00+00:00"}
            ]
            return t
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    req = _req_json({"naziv": "Test predmet", "tip": "opsti"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        with pytest.raises(HTTPException) as exc:
            await api.kreiraj_predmet(req, "Bearer fake-token")

    assert exc.value.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# update_predmet — optimistic-concurrency guard (Certification 004)
# ═══════════════════════════════════════════════════════════════════════════

def _update_chain(matches: bool, row_exists: bool = True):
    """update(...).eq(...).eq(...)[.eq("updated_at", ...)].execute() --
    `matches` controls whether the final .execute() reports a row was
    actually updated (real Postgres UPDATE...WHERE behavior: 0 rows back
    when a precondition doesn't match the row's current state). Also
    models the SEPARATE .select(...).maybe_single() existence-check
    query the fix's own 404-vs-409 disambiguation added (Phase 6
    adversarial re-attack finding): `row_exists` controls THAT query's
    own result, independent of `matches`."""
    c = MagicMock()
    for m in ["update", "eq"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock()
    r.data = [{"id": "pred-1"}] if matches else []
    c.execute = MagicMock(return_value=r)

    exist_chain = MagicMock()
    exist_chain.eq.return_value = exist_chain
    exist_chain.maybe_single.return_value = exist_chain
    exist_r = MagicMock()
    exist_r.data = {"id": "pred-1"} if row_exists else None
    exist_chain.execute = MagicMock(return_value=exist_r)
    c.select = MagicMock(return_value=exist_chain)
    return c


@pytest.mark.anyio
async def test_update_predmet_without_if_updated_at_behaves_exactly_as_before():
    """No regression: a caller not sending if_updated_at gets the exact
    prior unconditional-update behavior (opt-in only, no breakage for
    existing frontends)."""
    supa = MagicMock()
    supa.table = MagicMock(return_value=_update_chain(matches=True))

    req = _req_json({"naziv": "Novi naziv"}, path="/api/predmeti/pred-1")
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        result = await api.update_predmet("pred-1", req, "Bearer fake-token")

    # Program Phoenix, Mission 002: update_predmet now also returns the row's new updated_at
    # (used by static/vindex.js::_predInlineEdit to keep its own if_updated_at precondition
    # fresh for the NEXT edit -- LIVINGSYS-DEBT-007) -- additive, "ok": True is unchanged.
    assert result == {"ok": True, "updated_at": None}  # mock's row has no updated_at column


@pytest.mark.anyio
async def test_update_predmet_with_matching_if_updated_at_succeeds():
    supa = MagicMock()
    supa.table = MagicMock(return_value=_update_chain(matches=True))

    req = _req_json({"naziv": "Novi naziv", "if_updated_at": "2026-08-06T10:00:00+00:00"}, path="/api/predmeti/pred-1")
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        result = await api.update_predmet("pred-1", req, "Bearer fake-token")

    assert result == {"ok": True, "updated_at": None}  # mock's row has no updated_at column


@pytest.mark.anyio
async def test_update_predmet_with_stale_if_updated_at_rejects_with_409():
    """The core fix: a client editing a stale copy (its own if_updated_at
    no longer matches the row's current updated_at, e.g. because another
    tab already saved a change) must get a clean 409, not silently
    clobber the newer data. (The row genuinely exists, per row_exists=True
    default -- this is the disambiguation follow-up query's own OTHER
    branch, see the paired 404 test below.)"""
    supa = MagicMock()
    supa.table = MagicMock(return_value=_update_chain(matches=False, row_exists=True))

    req = _req_json({"naziv": "Stale naziv", "if_updated_at": "2026-08-06T09:00:00+00:00"}, path="/api/predmeti/pred-1")
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        with pytest.raises(HTTPException) as exc:
            await api.update_predmet("pred-1", req, "Bearer fake-token")

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_update_predmet_with_nonexistent_predmet_rejects_with_404_not_409():
    """Phase 6 adversarial re-attack finding: the original fix conflated
    "0 rows updated because of a stale if_updated_at" with "0 rows updated
    because predmet_id doesn't exist / isn't owned by this caller" -- the
    latter must return 404 ('not found'), not the misleading 409 ('someone
    else changed it') the first version of this fix would have returned."""
    supa = MagicMock()
    supa.table = MagicMock(return_value=_update_chain(matches=False, row_exists=False))

    req = _req_json({"naziv": "X", "if_updated_at": "2026-08-06T09:00:00+00:00"}, path="/api/predmeti/pred-nonexistent")
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user("user-1")):
        with pytest.raises(HTTPException) as exc:
            await api.update_predmet("pred-nonexistent", req, "Bearer fake-token")

    assert exc.value.status_code == 404


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
         patch("uploaded_doc.extractor.extract", return_value=("Sadržaj dokumenta.", False, False, None, None)), \
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
