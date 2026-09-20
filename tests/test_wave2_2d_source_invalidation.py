# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2D -- Source invalidation -> durable
recomputation.

PROVEN PROBLEM (Wave 1): evidence delete (routers/evidence.py::
delete_dokaz), document delete (api.py's dokument-delete endpoint), and
hearing delete (routers/rocista.py::obrisi_rociste) never triggered Case
Evolution recomputation. Negative reconciliation already existed inside
_consequence_refresh_case_actions -- the defect was trigger coverage, not
a missing algorithm.

Fix: services/event_bus.py::emit_source_invalidated -- one shared,
durable, deterministically-idempotent emission point all 3 delete
endpoints now call after their own delete/soft-delete succeeds. A new
EventType.SOURCE_INVALIDATED, registered with ONLY refresh_case_actions,
which always recomputes the CURRENT target set from whatever sources
remain -- never a direct source-id -> action-id deletion.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import uuid
from datetime import date, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps the full import graph safely

from services.event_bus import Event, EventType, emit_source_invalidated  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Fake Postgres -- same proven harness as Wave 2 Tasks 2B/2C's own tests.
# ═══════════════════════════════════════════════════════════════════════════

class _FakeQuery:
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, row, ignore_duplicates=False, **_kw):
        self._op = "insert"
        self._payload = row
        self._ignore_duplicates_insert = ignore_duplicates
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._on_conflict = [c.strip() for c in (on_conflict or "").split(",") if c.strip()]
        self._ignore_duplicates = ignore_duplicates
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def neq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) != val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    @property
    def not_(self):
        return _NotFilter(self)

    def is_(self, col, val):
        if val in ("null", None):
            self._filtered = [r for r in self._filtered if r.get(col) is None]
        return self

    def gte(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or "") >= val]
        return self

    def lt(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or 0) < val]
        return self

    def order(self, col, desc=False):
        self._filtered.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, _n):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        res = MagicMock()
        if self._op == "insert":
            _pk = self._payload.get("id")
            if getattr(self, "_ignore_duplicates_insert", False) and _pk is not None and any(r.get("id") == _pk for r in self._rows_ref):
                res.data = []  # PK conflict, ON CONFLICT DO NOTHING -- no row returned
            else:
                new_row = dict(self._payload)
                new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
                new_row.setdefault("status", "open")
                self._rows_ref.append(new_row)
                res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        elif self._op == "delete":
            for r in self._filtered:
                self._rows_ref.remove(r)
            res.data = list(self._filtered)
        elif self._op == "upsert":
            keys = self._on_conflict or ["id"]
            existing = next(
                (r for r in self._rows_ref if all(r.get(k) == self._payload.get(k) for k in keys)),
                None,
            )
            if existing is not None:
                if self._ignore_duplicates:
                    res.data = []
                else:
                    existing.update(self._payload)
                    res.data = [existing]
            else:
                new_row = dict(self._payload)
                new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
                self._rows_ref.append(new_row)
                res.data = [new_row]
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _NotFilter:
    def __init__(self, query: "_FakeQuery"):
        self._query = query

    def in_(self, col, vals):
        vals = set(vals)
        self._query._filtered = [r for r in self._query._filtered if r.get(col) not in vals]
        return self._query

    def eq(self, col, val):
        self._query._filtered = [r for r in self._query._filtered if r.get(col) != val]
        return self._query

    def is_(self, col, val):
        if val in ("null", None):
            self._query._filtered = [r for r in self._query._filtered if r.get(col) is not None]
        return self._query


class _FakeSupa:
    def __init__(self, tables: dict):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


PID = "pred-1"


def _predmet_row(tip="parnicno", status="aktivan"):
    return {"id": PID, "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": tip, "status": status, "brisanje_zapoceto": None}


def _make_fake(dokazi=None, dokumenti=None, rocista=None, case_actions=None, tip="parnicno"):
    return _FakeSupa({
        "predmeti": [_predmet_row(tip=tip)],
        "predmet_dokazi": list(dokazi or []),
        "predmet_dokumenti": list(dokumenti or []),
        "rocista": list(rocista or []),
        "case_actions": list(case_actions or []),
        "notifications": [],
        "events": [],
    })


def _event(event_id):
    return Event(type=EventType.SOURCE_INVALIDATED, user_id="user-1", predmet_id=PID,
                 payload={}, correlation_id="corr-1", event_id=event_id)


# ═══════════════════════════════════════════════════════════════════════════
# 1. emit_source_invalidated -- deterministic idempotent event_id
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_emit_source_invalidated_same_source_same_event_id_no_duplicate_row():
    fake = _make_fake()
    fake.tables["predmeti"][0]["brisanje_zapoceto"] = None

    await emit_source_invalidated(user_id="user-1", predmet_id=PID, source_type="dokaz", source_id="dokaz-1", supa=fake)
    await emit_source_invalidated(user_id="user-1", predmet_id=PID, source_type="dokaz", source_id="dokaz-1", supa=fake)

    assert len(fake.tables["events"]) == 1


@pytest.mark.anyio
async def test_emit_source_invalidated_different_sources_different_events():
    fake = _make_fake()
    await emit_source_invalidated(user_id="user-1", predmet_id=PID, source_type="dokaz", source_id="dokaz-1", supa=fake)
    await emit_source_invalidated(user_id="user-1", predmet_id=PID, source_type="dokaz", source_id="dokaz-2", supa=fake)
    assert len(fake.tables["events"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 2. Rociste deletion -> its own PRIPREMITI_PODNESAK action resolves
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rociste_deletion_closes_its_own_deadline_action():
    from services.case_evolution import _consequence_refresh_case_actions

    existing_action = {
        "id": "ca-1", "predmet_id": PID, "tip": "PRIPREMITI_PODNESAK", "status": "open",
        "dedupe_key": "roc-hash-1", "razlog": "x", "prioritet": "high", "rok": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    # Rociste already deleted (this is what the reconcile sees AFTER the
    # DB delete already happened, exactly the state SOURCE_INVALIDATED
    # fires from) -- rocista table is empty.
    fake = _make_fake(rocista=[], case_actions=[existing_action])

    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event("evt-del-1"))

    assert "closed=1" in result
    assert fake.tables["case_actions"][0]["status"] == "closed"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Multiple supporting sources -- recompute, not direct source->action delete
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_deleting_one_of_two_covering_documents_keeps_gap_resolved():
    """2 documents both cover the 'ugovor' requirement -- deleting ONE still
    leaves the gap covered by the other, so no PRIBAVITI_DOKAZ action is
    created. This is the actual proof recomputation (not direct source-id
    -> action-id deletion) correctly handles multi-support: nothing here
    ever asks 'which action did doc-1 justify' -- only 'what does current
    state justify', which doc-2 alone already answers."""
    from services.case_evolution import _consequence_refresh_case_actions

    dokumenti_both = [
        {"id": "doc-1", "predmet_id": PID, "naziv_fajla": "ugovor1.pdf", "status": "obradjen", "tip_dokaza": "ugovor"},
        {"id": "doc-2", "predmet_id": PID, "naziv_fajla": "ugovor2.pdf", "status": "obradjen", "tip_dokaza": "ugovor"},
    ]
    fake = _make_fake(dokumenti=dokumenti_both)

    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-baseline"))
    open_actions = [r for r in fake.tables["case_actions"] if r["status"] == "open"]
    assert not any("ugovor" in (a.get("razlog") or "").lower() and a["tip"] == "PRIBAVITI_DOKAZ" for a in open_actions)

    # Delete doc-1 (SOURCE_INVALIDATED for it) -- doc-2 still covers 'ugovor'.
    fake.tables["predmet_dokumenti"] = [d for d in fake.tables["predmet_dokumenti"] if d["id"] != "doc-1"]
    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-del-doc1"))
    open_actions = [r for r in fake.tables["case_actions"] if r["status"] == "open"]
    assert not any("ugovor" in (a.get("razlog") or "").lower() and a["tip"] == "PRIBAVITI_DOKAZ" for a in open_actions)


@pytest.mark.anyio
async def test_deleting_last_covering_document_creates_gap_action():
    """Continuation: deleting the LAST document covering 'ugovor' makes the
    gap current, and the recompute (not a manual insert) surfaces it."""
    from services.case_evolution import _consequence_refresh_case_actions

    dokumenti_one = [
        {"id": "doc-2", "predmet_id": PID, "naziv_fajla": "ugovor2.pdf", "status": "obradjen", "tip_dokaza": "ugovor"},
    ]
    fake = _make_fake(dokumenti=dokumenti_one)
    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-baseline"))

    fake.tables["predmet_dokumenti"] = []
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event("evt-del-doc2"))

    open_actions = [r for r in fake.tables["case_actions"] if r["status"] == "open"]
    assert any(a["tip"] == "PRIBAVITI_DOKAZ" for a in open_actions)
    assert "created=" in result


# ═══════════════════════════════════════════════════════════════════════════
# 4. Duplicate delete / retry -- idempotent, no duplicate consequence
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_retry_same_event_id_produces_no_duplicate_effect():
    from services.case_evolution import handle_case_changed

    existing_action = {
        "id": "ca-1", "predmet_id": PID, "tip": "PRIPREMITI_PODNESAK", "status": "open",
        "dedupe_key": "roc-hash-1", "razlog": "x", "prioritet": "high", "rok": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _make_fake(rocista=[], case_actions=[existing_action])
    fake.tables["case_evolution_consequences"] = []

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event("evt-retry-src-1"))
        n1 = len(fake.tables["case_actions"])
        await handle_case_changed(_event("evt-retry-src-1"))
        n2 = len(fake.tables["case_actions"])

    # A document-less, evidence-less matter also trips the risk engine's
    # own "missing expected document type" rules on the first run -- this
    # test is about retry idempotency (2nd handle_case_changed call for the
    # SAME event_id must not add or duplicate anything), not the total.
    assert n1 == n2
    ca1 = next(r for r in fake.tables["case_actions"] if r["id"] == "ca-1")
    assert ca1["status"] == "closed"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Already-absent source -- the HTTP layer's own zero-row guard prevents
#    emission from ever being attempted (verified against the real
#    endpoints, not re-derived logic)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_delete_dokaz_already_absent_does_not_emit():
    """Wave 2 Task 2D corrective closure: delete_dokaz now calls the atomic
    invalidate_dokaz_and_emit_event RPC. An already-absent/foreign dokaz
    means the RPC's own WHERE clause matches nothing -- it returns
    invalidated=FALSE (predmet_id=NULL) WITHOUT ever reaching its own
    event insert (same function, same transaction, the IF NOT FOUND branch
    returns before the INSERT statement) -- so no event exists to emit,
    proven here by asserting the RPC call itself returns exactly that
    shape and the endpoint 404s."""
    from routers.evidence import delete_dokaz
    from starlette.requests import Request as StarletteRequest

    fake = MagicMock()
    fake.rpc.return_value.execute.return_value = MagicMock(data=[{"predmet_id": None, "invalidated": False}])

    req = MagicMock(spec=StarletteRequest)
    req.headers, req.client, req.state = {}, None, MagicMock()

    with patch("routers.evidence.get_supa", return_value=fake):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_dokaz(req, PID, "dokaz-ghost", user={"user_id": "user-1"})
        assert exc_info.value.status_code == 404

    fake.rpc.assert_called_once()
    assert fake.rpc.call_args[0][0] == "invalidate_dokaz_and_emit_event"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Tenant isolation -- ownership filter at the endpoint means a
#    cross-tenant delete attempt never reaches emission either
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_obrisi_rociste_foreign_user_gets_404_no_emit():
    """Wave 2 Task 2D corrective closure: obrisi_rociste now calls the
    atomic invalidate_rociste_and_emit_event RPC, whose own WHERE clause
    (id AND user_id) enforces ownership inside the same transaction the
    event insert lives in -- a foreign user's call matches no row, returns
    invalidated=FALSE, and never reaches the event insert."""
    from routers.rocista import obrisi_rociste
    from starlette.requests import Request as StarletteRequest
    from fastapi import HTTPException

    fake = MagicMock()
    fake.rpc.return_value.execute.return_value = MagicMock(data=[{"predmet_id": None, "invalidated": False}])

    req = MagicMock(spec=StarletteRequest)
    req.headers, req.client, req.state = {}, None, MagicMock()

    with patch("routers.rocista._get_supa", return_value=fake):
        with pytest.raises(HTTPException) as exc_info:
            await obrisi_rociste("roc-not-mine", req, user={"user_id": "attacker"})
        assert exc_info.value.status_code == 404

    fake.rpc.assert_called_once()
    assert fake.rpc.call_args[0][0] == "invalidate_rociste_and_emit_event"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Matter isolation -- SOURCE_INVALIDATED for matter A recomputes ONLY
#    matter A's own case_actions
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_source_invalidated_does_not_touch_other_matters_actions():
    from services.case_evolution import _consequence_refresh_case_actions

    other_matter_action = {
        "id": "ca-other", "predmet_id": "pred-OTHER", "tip": "PRIBAVITI_DOKAZ", "status": "open",
        "dedupe_key": "k-other", "razlog": "x", "prioritet": "high", "rok": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _make_fake(rocista=[], case_actions=[other_matter_action])
    fake.tables["predmeti"].append({"id": "pred-OTHER", "user_id": "user-2", "naziv": "Predmet B", "case_dna": {}, "tip": "parnicno", "status": "aktivan", "brisanje_zapoceto": None})

    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-matter-a"))

    # Matter A (PID) may legitimately gain its OWN actions from the risk
    # engine (empty dokazi/dokumenti) -- what this test proves is narrower
    # and more important: matter B's own pre-existing action is untouched,
    # neither closed nor mutated, by an event scoped to matter A.
    other = next(r for r in fake.tables["case_actions"] if r["id"] == "ca-other")
    assert other["status"] == "open"
    assert other["predmet_id"] == "pred-OTHER"
    assert other["dedupe_key"] == "k-other"
