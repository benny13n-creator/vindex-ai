# -*- coding: utf-8 -*-
"""Deterministic tests for the Word-specific session boundary."""
import asyncio
import base64
import hashlib
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from itertools import count

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request

from routers import word_auth

_CLIENT_IDS = count(1)


def _test_app_client():
    app = FastAPI()
    app.state.limiter = word_auth.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(word_auth.router)
    remote_ip = "127.0.0.%d" % next(_CLIENT_IDS)
    return TestClient(app, base_url="https://vindex.test", client=(remote_ip, 50000))


def _origin_headers(token=None, origin="https://vindex.test"):
    headers = {"Origin": origin}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    return headers


def _auth_claims(user_id="user-123", expiry=None):
    return {
        "iss": "https://auth.test/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "sub": user_id,
        "iat": int(time.time()) - 10,
        "exp": int(expiry or time.time() + 1800),
    }


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _ec_key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(public_numbers.x.to_bytes(32, "big")),
        "y": _b64url(public_numbers.y.to_bytes(32, "big")),
        "alg": "ES256",
        "use": "sig",
        "key_ops": ["verify"],
        "kid": "unit-key",
    }
    return private_pem, jwk


def _sign_claims(private_pem, claims, kid="unit-key", algorithm="ES256"):
    return jose_jwt.encode(claims, private_pem, algorithm=algorithm, headers={"kid": kid})


def test_source_jwt_requires_signature_exact_key_and_server_identity(monkeypatch):
    private_pem, jwk = _ec_key_pair()
    monkeypatch.setattr(word_auth, "SUPABASE_URL", "https://auth.test")
    monkeypatch.setattr(word_auth, "_get_jwks_keys", lambda: [jwk])
    token = _sign_claims(private_pem, _auth_claims())
    claims = word_auth._verify_source_jwt(token, "user-123")
    assert claims["sub"] == "user-123"
    with pytest.raises(Exception):
        word_auth._verify_source_jwt(token, "different-user")


@pytest.mark.parametrize(
    "updates",
    [
        {"iss": "https://attacker.test/auth/v1"},
        {"aud": "service_role"},
        {"role": "service_role"},
        {"exp": int(time.time()) - 1},
    ],
)
def test_source_jwt_rejects_invalid_identity_and_claims(monkeypatch, updates):
    private_pem, jwk = _ec_key_pair()
    monkeypatch.setattr(word_auth, "SUPABASE_URL", "https://auth.test")
    monkeypatch.setattr(word_auth, "_get_jwks_keys", lambda: [jwk])
    claims = _auth_claims()
    claims.update(updates)
    token = _sign_claims(private_pem, claims)
    with pytest.raises(Exception):
        word_auth._verify_source_jwt(token, "user-123")


def test_source_jwt_rejects_unknown_key_and_hmac_algorithm(monkeypatch):
    private_pem, jwk = _ec_key_pair()
    monkeypatch.setattr(word_auth, "SUPABASE_URL", "https://auth.test")
    monkeypatch.setattr(word_auth, "_get_jwks_keys", lambda: [jwk])
    token = _sign_claims(private_pem, _auth_claims(), kid="unknown")
    with pytest.raises(ValueError):
        word_auth._verify_source_jwt(token, "user-123")
    hmac_token = jose_jwt.encode(_auth_claims(), "test-only-secret", algorithm="HS256")
    with pytest.raises(ValueError):
        word_auth._verify_source_jwt(hmac_token, "user-123")


def test_source_jwt_rejects_signature_from_another_key(monkeypatch):
    trusted_pem, jwk = _ec_key_pair()
    other_pem, _ = _ec_key_pair()
    monkeypatch.setattr(word_auth, "SUPABASE_URL", "https://auth.test")
    monkeypatch.setattr(word_auth, "_get_jwks_keys", lambda: [jwk])
    token = _sign_claims(other_pem, _auth_claims())
    with pytest.raises(Exception):
        word_auth._verify_source_jwt(token, "user-123")


class _InsertTable:
    def __init__(self, row_sink, fail=False):
        self.row_sink = row_sink
        self.fail = fail

    def insert(self, row):
        self.row_sink.append(dict(row))
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("storage unavailable")
        return SimpleNamespace(data=[])


class _InsertClient:
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail

    def table(self, name):
        assert name == "word_sessions"
        return _InsertTable(self.rows, self.fail)


@pytest.fixture
def auth_mocks(monkeypatch):
    async def confirm(token):
        assert token == "source.jwt.signature"
        return "server-user-1", {"exp": int(time.time()) + 1200}

    async def allow_rate(*args, **kwargs):
        return None

    async def audit(*args, **kwargs):
        return "audit-id"

    monkeypatch.setattr(word_auth, "_confirm_source_identity", confirm)
    monkeypatch.setattr(word_auth, "_record_and_rate_limit", allow_rate)
    monkeypatch.setattr(word_auth, "_audit", audit)


def test_session_exchange_stores_hash_only_and_uses_bounded_expiry(monkeypatch, auth_mocks):
    rows = []
    monkeypatch.setattr(word_auth, "_get_supa", lambda: _InsertClient(rows))
    with _test_app_client() as client:
        response = client.post(
            "/api/word/sessions",
            headers=_origin_headers("source.jwt.signature"),
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    session_token = body["session_token"]
    assert len(session_token) == 43
    assert rows[0]["user_id"] == "server-user-1"
    assert rows[0]["token_hash"] == hashlib.sha256(session_token.encode()).hexdigest()
    assert session_token not in rows[0].values()
    assert "source.jwt.signature" not in rows[0].values()
    expires_at = datetime.fromisoformat(body["expires_at"])
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 0 < remaining <= 1200


def test_session_exchange_rejects_invalid_origin_before_identity_lookup(monkeypatch, auth_mocks):
    called = False

    async def should_not_run(token):
        nonlocal called
        called = True
        raise AssertionError("identity lookup should not run")

    monkeypatch.setattr(word_auth, "_confirm_source_identity", should_not_run)
    with _test_app_client() as client:
        response = client.post(
            "/api/word/sessions",
            headers=_origin_headers("source.jwt.signature", "https://evil.test"),
        )
    assert response.status_code == 403
    assert called is False


def test_session_exchange_requires_origin_and_bearer(auth_mocks):
    with _test_app_client() as client:
        no_origin = client.post("/api/word/sessions", headers={"Authorization": "Bearer source.jwt.signature"})
        no_bearer = client.post("/api/word/sessions", headers=_origin_headers())
    assert no_origin.status_code == 403
    assert no_bearer.status_code == 401


def test_session_exchange_fails_closed_when_session_store_is_unavailable(monkeypatch, auth_mocks, caplog):
    rows = []
    monkeypatch.setattr(word_auth, "_get_supa", lambda: _InsertClient(rows, fail=True))
    with _test_app_client() as client:
        response = client.post(
            "/api/word/sessions",
            headers=_origin_headers("source.jwt.signature"),
        )
    assert response.status_code == 503
    assert "source.jwt.signature" not in caplog.text
    assert "session_token" not in response.text


class _SelectTable:
    def __init__(self, row=None, fail=False):
        self.row = row
        self.fail = fail
        self.filters = {}

    def select(self, columns):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("lookup unavailable")
        return SimpleNamespace(data=self.row)


class _SelectClient:
    def __init__(self, row=None, fail=False):
        self.query = _SelectTable(row=row, fail=fail)

    def table(self, name):
        assert name == "word_sessions"
        return self.query


def _session_request(token=None, extra_headers=()):
    headers = list(extra_headers)
    if token is not None:
        headers.append((b"authorization", ("Bearer " + token).encode()))
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/word/analyze",
        "raw_path": b"/api/word/analyze",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("vindex.test", 443),
    })


def test_word_session_uses_stored_identity_not_client_claims(monkeypatch):
    token = "opaque-session-token"
    row = {
        "id": "session-1",
        "user_id": "trusted-user",
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "revoked_at": None,
    }
    db = _SelectClient(row)
    monkeypatch.setattr(word_auth, "_get_supa", lambda: db)

    async def allow_rate(*args, **kwargs):
        return None

    monkeypatch.setattr(word_auth, "_record_and_rate_limit", allow_rate)
    request = _session_request(token, [(b"x-user-id", b"attacker-user")])
    session = asyncio.run(word_auth.require_word_session(request))
    assert session.user_id == "trusted-user"
    assert request.state.user_id == "trusted-user"
    assert db.query.filters == {"token_hash": row["token_hash"]}


@pytest.mark.parametrize(
    "row",
    [
        None,
        {
            "id": "s",
            "user_id": "u",
            "token_hash": "wrong-hash",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "revoked_at": None,
        },
        {
            "id": "s",
            "user_id": "u",
            "token_hash": "PLACEHOLDER",
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "revoked_at": None,
        },
        {
            "id": "s",
            "user_id": "u",
            "token_hash": "PLACEHOLDER",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "revoked_at": "2026-11-02T10:00:00+00:00",
        },
    ],
)
def test_word_session_rejects_missing_expired_revoked_or_mismatched_row(monkeypatch, row):
    token = "opaque-session-token"
    if row is not None and row["token_hash"] == "PLACEHOLDER":
        row = dict(row, token_hash=hashlib.sha256(token.encode()).hexdigest())
    monkeypatch.setattr(word_auth, "_get_supa", lambda: _SelectClient(row))

    async def allow_rate(*args, **kwargs):
        return None

    monkeypatch.setattr(word_auth, "_record_and_rate_limit", allow_rate)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(word_auth.require_word_session(_session_request(token)))
    assert caught.value.status_code == 401


def test_word_session_rejects_missing_token_and_database_failure(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        asyncio.run(word_auth.require_word_session(_session_request()))
    assert missing.value.status_code == 401

    monkeypatch.setattr(word_auth, "_get_supa", lambda: _SelectClient(fail=True))
    with pytest.raises(HTTPException) as failed:
        asyncio.run(word_auth.require_word_session(_session_request("opaque-session-token")))
    assert failed.value.status_code == 503


def test_word_origin_accepts_exact_https_origin_only():
    request = _session_request(extra_headers=[(b"origin", b"https://vindex.test")])
    word_auth._require_word_origin(request)
    for origin in (None, "https://evil.test", "http://vindex.test", "https://vindex.test/path"):
        headers = [] if origin is None else [(b"origin", origin.encode())]
        with pytest.raises(HTTPException) as caught:
            word_auth._require_word_origin(_session_request(extra_headers=headers))
        assert caught.value.status_code == 403
def test_provider_identity_is_checked_before_source_jwt_trust(monkeypatch):
    class FakeAuth:
        def get_user(self, token):
            assert token == "source.jwt.signature"
            return SimpleNamespace(user=SimpleNamespace(id="provider-user"))

    class FakeSupa:
        auth = FakeAuth()

    verified = []

    def verify(token, provider_user_id):
        verified.append((token, provider_user_id))
        return {"sub": provider_user_id, "exp": int(time.time()) + 60}

    monkeypatch.setattr(word_auth, "_get_supa", lambda: FakeSupa())
    monkeypatch.setattr(word_auth, "_verify_source_jwt", verify)
    user_id, claims = asyncio.run(word_auth._confirm_source_identity("source.jwt.signature"))
    assert user_id == "provider-user"
    assert claims["sub"] == user_id
    assert verified == [("source.jwt.signature", "provider-user")]


class _UpdateTable:
    def __init__(self):
        self.filters = {}
        self.null_filters = {}
        self.update_values = None

    def update(self, values):
        self.update_values = dict(values)
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def is_(self, key, value):
        self.null_filters[key] = value
        return self

    def select(self, columns):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": self.filters.get("id")}])


class _RevokeClient:
    def __init__(self, row):
        self.select_table = _SelectTable(row=row)
        self.update_table = _UpdateTable()
        self.calls = 0

    def table(self, name):
        assert name == "word_sessions"
        self.calls += 1
        return self.select_table if self.calls == 1 else self.update_table


def test_logout_revokes_only_current_word_session(monkeypatch):
    token = "opaque-session-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = {
        "id": "session-to-revoke",
        "user_id": "session-owner",
        "token_hash": token_hash,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "revoked_at": None,
    }
    db = _RevokeClient(row)
    audit_events = []

    async def allow_rate(*args, **kwargs):
        return None

    async def audit(action, **kwargs):
        audit_events.append((action, kwargs))
        return "audit-id"

    monkeypatch.setattr(word_auth, "_get_supa", lambda: db)
    monkeypatch.setattr(word_auth, "_record_and_rate_limit", allow_rate)
    monkeypatch.setattr(word_auth, "_audit", audit)

    with _test_app_client() as client:
        response = client.delete(
            "/api/word/sessions/current",
            headers=_origin_headers(token),
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"revoked": True}
    assert db.update_table.update_values and "revoked_at" in db.update_table.update_values
    assert db.update_table.filters == {
        "id": "session-to-revoke",
        "user_id": "session-owner",
        "token_hash": token_hash,
    }
    assert db.update_table.null_filters == {"revoked_at": "null"}
    assert audit_events[0][0] == "logout"
def test_word_pre_auth_rate_key_ignores_spoofed_forwarded_for():
    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/word/sessions",
        "raw_path": b"/api/word/sessions",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", b"203.0.113.8")],
        "client": ("10.20.30.40", 50000),
        "server": ("vindex.test", 443),
    })
    assert word_auth._word_server_client_key(request) == "10.20.30.40"
def test_session_exchange_fails_closed_on_provider_authentication_failure(monkeypatch, auth_mocks, caplog):
    rows = []
    monkeypatch.setattr(word_auth, "_get_supa", lambda: _InsertClient(rows, fail=True))

    async def reject_provider(token):
        raise RuntimeError("private provider error detail")

    monkeypatch.setattr(word_auth, "_confirm_source_identity", reject_provider)
    with _test_app_client() as client:
        response = client.post(
            "/api/word/sessions",
            headers=_origin_headers("source.jwt.signature"),
        )
    assert response.status_code == 401
    assert rows == []
    assert "source.jwt.signature" not in caplog.text
    assert "private provider error detail" not in response.text