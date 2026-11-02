"""Deterministic Word logout/provider-dispatch race and retry contracts."""
import hashlib
import threading
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from routers import word_auth, word_copilot
from routers.word_auth import WordSession
from shared import word_session_dispatch


def _budget_context():
    try:
        from shared import ai_budget
    except ImportError:
        return nullcontext()
    return ai_budget.operacija(
        "trusted-user", "lawyer@example.test", "copilot_ambient",
        founder=True, izvor="test:word-dispatch",
    )


def _silence_provider_provenance(monkeypatch):
    # These tests use only synthetic HTTP transports; prevent the normal audit
    # hook from making an external database write for the mocked provider call.
    from shared import ai_client

    monkeypatch.setattr(ai_client, "_capture_chat_provenance", lambda *args, **kwargs: None)


class _SessionDB:
    def __init__(self, token_hash, strategy):
        self.lock = threading.Lock()
        self.row = {
            "id": "session-race",
            "user_id": "trusted-user",
            "token_hash": token_hash,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "revoked_at": None,
        }
        self.strategy = strategy
        self.claim_started = threading.Event()
        self.claim_committed = threading.Event()
        self.allow_claim_return = threading.Event()
        self.claims = 0

    def table(self, name):
        assert name == "word_sessions"
        return _SessionTable(self)

    def rpc(self, name, params):
        assert name == "claim_word_session_provider_attempt"
        assert params == {
            "p_session_id": "session-race",
            "p_user_id": "trusted-user",
            "p_token_hash": self.row["token_hash"],
        }
        return _Claim(self)


class _SessionTable:
    def __init__(self, db):
        self.db = db
        self.filters = {}
        self.null_filters = {}
        self.operation = "select"
        self.values = None

    def select(self, _columns):
        if self.operation != "update":
            self.operation = "select"
        return self

    def update(self, values):
        self.operation = "update"
        self.values = values
        return self

    def eq(self, name, value):
        self.filters[name] = value
        return self

    def is_(self, name, value):
        self.null_filters[name] = value
        return self

    def maybe_single(self):
        return self

    def execute(self):
        with self.db.lock:
            matches = all(self.db.row.get(key) == value for key, value in self.filters.items())
            if not matches:
                return SimpleNamespace(data=None if self.operation == "select" else [])
            if self.operation == "update":
                if any(self.db.row.get(key) is not None for key in self.null_filters):
                    return SimpleNamespace(data=[])
                self.db.row.update(self.values or {})
                return SimpleNamespace(data=[{"id": self.db.row["id"]}])
            return SimpleNamespace(data=dict(self.db.row))


class _Claim:
    def __init__(self, db):
        self.db = db

    def execute(self):
        db = self.db
        db.claims += 1
        db.claim_started.set()
        if db.strategy == "revoke_first":
            assert db.allow_claim_return.wait(5), "test did not release claim barrier"
            with db.lock:
                allowed = db.row["revoked_at"] is None
        else:
            with db.lock:
                allowed = db.row["revoked_at"] is None
            if allowed:
                # This event models the committed transaction boundary.
                db.claim_committed.set()
                assert db.allow_claim_return.wait(5), "test did not release dispatch barrier"
        return SimpleNamespace(data=allowed)


def _app(monkeypatch, db, token, settled):
    app = FastAPI()
    app.state.limiter = word_copilot.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(word_auth.router)
    app.include_router(word_copilot.router)
    session = WordSession(
        session_id="session-race",
        user_id="trusted-user",
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    async def trusted_word_user(request: Request):
        request.state.word_session = session
        return {"user_id": "trusted-user", "email": "lawyer@example.test"}

    async def settle(*args):
        settled.append(args)
        return 1

    async def allow(*args, **kwargs):
        return None

    monkeypatch.setattr(word_auth, "_get_supa", lambda: db)
    monkeypatch.setattr(word_auth, "_record_and_rate_limit", allow)
    monkeypatch.setattr(word_auth, "_audit", allow)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    monkeypatch.setattr(word_copilot, "_require_word_ai_budget_operation", lambda *args: None)
    monkeypatch.setattr(word_copilot, "ensure_word_session_active", word_auth.ensure_word_session_active)
    monkeypatch.setattr(word_copilot, "UsageService", SimpleNamespace(consume=settle))
    app.dependency_overrides[word_copilot.require_word_analysis_user] = trusted_word_user
    return app


@pytest.mark.parametrize(
    ("strategy", "expected_provider_calls", "expected_settlements", "expected_status"),
    [
        ("revoke_first", 0, 0, 401),
        ("claim_first", 1, 1, 401),
    ],
)
def test_logout_dispatch_race_is_atomic_and_fails_closed(
    monkeypatch, strategy, expected_provider_calls, expected_settlements, expected_status
):
    _silence_provider_provenance(monkeypatch)
    token = "synthetic-word-session-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = _SessionDB(token_hash, strategy)
    settled = []
    provider_calls = []
    app = _app(monkeypatch, db, token, settled)

    def provider_handler(_request):
        provider_calls.append(1)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-synthetic",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "synthetic"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    async def analyzer(text, user_id):
        assert text == "Synthetic selected sentence."
        assert user_id == "trusted-user"
        from openai import OpenAI

        with _budget_context():
            with OpenAI(
                api_key="test-only-not-a-credential",
                max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(provider_handler)),
            ) as provider:
                provider.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "synthetic text"}],
                )
        return {"sugestije": [], "trajanje_ms": 1}

    monkeypatch.setattr("services.ambient_analyzer.analyze_selected_text", analyzer)
    request_client = TestClient(app, base_url="https://vindex.test")
    logout_client = TestClient(app, base_url="https://vindex.test")
    response_holder = []

    def submit_analysis():
        response_holder.append(
            request_client.post(
                "/api/word/analyze",
                json={"text": "Synthetic selected sentence."},
            )
        )

    request_thread = threading.Thread(target=submit_analysis, daemon=True)
    request_thread.start()
    assert db.claim_started.wait(5), "analysis did not reach the dispatch claim"
    if strategy == "claim_first":
        assert db.claim_committed.wait(5), "claim was not committed before provider dispatch"

    logout = logout_client.delete(
        "/api/word/sessions/current",
        headers={"Authorization": f"Bearer {token}", "Origin": "https://vindex.test"},
    )
    assert logout.status_code == 200, logout.text
    assert db.row["revoked_at"] is not None
    db.allow_claim_return.set()
    request_thread.join(5)
    assert not request_thread.is_alive(), "analysis did not finish after releasing the barrier"

    assert len(response_holder) == 1
    assert response_holder[0].status_code == expected_status
    assert len(provider_calls) == expected_provider_calls
    assert len(settled) == expected_settlements
    assert db.claims == 1


def test_openai_sdk_retry_claims_again_after_logout(monkeypatch):
    _silence_provider_provenance(monkeypatch)

    class _RPC:
        def __init__(self):
            self.calls = 0

        def execute(self):
            self.calls += 1
            return SimpleNamespace(data=self.calls == 1)

    rpc = _RPC()
    monkeypatch.setattr("shared.deps._get_supa", lambda: SimpleNamespace(rpc=lambda *_: rpc))
    provider_calls = []

    def provider_handler(_request):
        provider_calls.append(1)
        return httpx.Response(503, json={"error": "temporary"})

    session = WordSession(
        session_id="session-retry",
        user_id="trusted-user",
        token_hash="synthetic-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    from openai import OpenAI

    client = OpenAI(
        api_key="test-only-not-a-credential",
        max_retries=1,
        http_client=httpx.Client(transport=httpx.MockTransport(provider_handler)),
    )
    with _budget_context():
        with word_session_dispatch.word_provider_session(session):
            with pytest.raises(Exception) as error:
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "synthetic text"}],
                )

    assert word_session_dispatch.word_session_dispatch_denial(error.value) is not None
    assert rpc.calls == 2
    assert provider_calls == [1]
    client.close()


def test_word_dispatch_hook_reinstalls_after_openai_method_reset(monkeypatch):
    """A budget-guard teardown may restore the SDK methods; Word must reattach before dispatch."""
    _silence_provider_provenance(monkeypatch)

    import httpx
    from openai import OpenAI
    from contextlib import nullcontext
    from openai._base_client import AsyncAPIClient, SyncAPIClient
    from shared import ai_client

    try:
        from shared import ai_budget
    except ImportError:
        ai_budget = None

    def unwrapped(client_class):
        saved = getattr(ai_client, "_orig_build_request", {}).get(client_class)
        if saved is not None:
            return saved
        method = client_class._build_request
        seen = set()
        while id(method) not in seen:
            seen.add(id(method))
            if getattr(method, "_vindex_word_session_guard", False):
                method = method.__kwdefaults__["_original"]
                continue
            if getattr(method, "_vindex_guarded", False):
                originals = [
                    cell.cell_contents
                    for cell in (getattr(method, "__closure__", None) or ())
                    if callable(cell.cell_contents)
                ]
                if len(originals) == 1:
                    method = originals[0]
                    continue
            break
        return method

    sync_original = unwrapped(SyncAPIClient)
    async_original = unwrapped(AsyncAPIClient)
    monkeypatch.setattr(SyncAPIClient, "_build_request", sync_original)
    monkeypatch.setattr(AsyncAPIClient, "_build_request", async_original)
    assert not word_session_dispatch.word_session_dispatch_hook_installed()

    class _DB:
        claims = 0

        def rpc(self, name, params):
            assert name == "claim_word_session_provider_attempt"
            assert params["p_session_id"] == "session-reinstall"
            return SimpleNamespace(execute=lambda: self._claim())

        def _claim(self):
            self.claims += 1
            return SimpleNamespace(data=True)

    db = _DB()
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    session = WordSession(
        session_id="session-reinstall",
        user_id="trusted-user",
        token_hash="synthetic-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    provider_calls = []

    def provider_handler(request):
        provider_calls.append(request.url.path)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl-reinstall",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "synthetic"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    budget_context = (
        ai_budget.operacija(
            "trusted-user", "lawyer@example.test", "copilot_ambient",
            founder=True, izvor="test:word-hook-reinstall",
        )
        if ai_budget is not None
        else nullcontext()
    )
    with OpenAI(
        api_key="test-only-not-a-credential",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(provider_handler)),
    ) as provider:
        with budget_context as budget_operation:
            assert word_session_dispatch.install_word_session_dispatch_hook()
            installed_sync = SyncAPIClient._build_request
            assert word_session_dispatch.install_word_session_dispatch_hook()
            assert SyncAPIClient._build_request is installed_sync
            with word_session_dispatch.word_provider_session(session):
                provider.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "synthetic text"}],
                )

    assert db.claims == 1
    assert provider_calls == ["/v1/chat/completions"]
