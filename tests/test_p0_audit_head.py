"""Audit writer contract through the real PostgREST client, without network I/O."""
import asyncio
import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from postgrest import SyncPostgrestClient

from shared import audit_immutable as audit

HEAD = "a" * 64
NEXT_HEAD = "b" * 64
GENESIS = "0" * 64


@pytest.fixture(params=["async", "sync"])
def writer(request, monkeypatch):
    def use_transport(handler):
        client = httpx.Client(base_url="https://audit.invalid", transport=httpx.MockTransport(handler))
        monkeypatch.setitem(sys.modules, "api", SimpleNamespace(
            _get_supa=lambda: SyncPostgrestClient("https://audit.invalid", http_client=client)
        ))
        request.addfinalizer(client.close)

        def write():
            args = {"user_id": "user-a", "resource_type": "predmet", "resource_id": "case-a",
                    "correlation_id": "test-audit-head"}
            if request.param == "async":
                return asyncio.run(audit.log_action("predmet_view", **args))
            return audit.log_action_sync("predmet_view", **args)

        return write

    return use_transport


@pytest.mark.parametrize("status,data", [
    (503, {"code": "PGRST001", "message": "database unavailable", "details": None, "hint": None}),
    (200, None),
    (200, b"null"),
    (200, {}),
    (200, [{}]),
    (200, [{"entry_hash": None}]),
    (200, [{"entry_hash": "bad-hash"}]),
    (200, [{"entry_hash": HEAD}, {"entry_hash": NEXT_HEAD}]),
], ids=["read-failure", "empty-body", "json-null", "object", "missing-hash", "null-hash", "invalid-hash", "extra-rows"])
def test_failed_or_incomplete_head_never_appends_then_recovers(writer, status, data):
    responses = iter([(status, data), (200, [{"entry_hash": HEAD}])])
    inserts = []

    def transport(request):
        if request.method == "GET":
            assert request.url.params["select"] == "entry_hash"
            assert request.url.params["order"] == "seq.desc"
            assert request.url.params["limit"] == "1"
            if request.headers.get("prefer") == "count=exact":
                return httpx.Response(200, content=b"")
            response_status, response_data = next(responses)
            if isinstance(response_data, bytes):
                return httpx.Response(response_status, content=response_data)
            return httpx.Response(response_status, json=response_data)
        inserts.append(json.loads(request.content))
        return httpx.Response(201, json=[{"id": "inserted"}])

    write = writer(transport)
    first = write()
    assert inserts == [], inserts
    assert first is None
    assert write() == "inserted"
    assert [record["prev_hash"] for record in inserts] == [HEAD]


def test_successful_empty_head_allows_genesis(writer):
    def transport(request):
        if request.method == "GET":
            if request.headers.get("prefer") == "count=exact":
                return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})
            return httpx.Response(200, json=[])
        assert json.loads(request.content)["prev_hash"] == GENESIS
        return httpx.Response(201, json=[{"id": "genesis"}])

    assert writer(transport)() == "genesis"


def test_unique_collision_retries_from_fresh_head(writer):
    heads = iter([HEAD, NEXT_HEAD])
    attempts = []

    def transport(request):
        if request.method == "GET":
            return httpx.Response(200, json=[{"entry_hash": next(heads)}])
        attempts.append(json.loads(request.content)["prev_hash"])
        if len(attempts) == 1:
            return httpx.Response(409, json={"code": "23505", "message": "duplicate key", "details": None, "hint": None})
        return httpx.Response(201, json=[{"id": "retried"}])

    assert writer(transport)() == "retried"
    assert attempts == [HEAD, NEXT_HEAD]
