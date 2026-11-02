"""Real-PostgreSQL acceptance for the reviewed Word session contract.

The test-only DDL is in fixtures/word_sessions_postgres.sql. It is applied only
to a fresh database on a loopback PostgreSQL cluster that passes
scripts/test_db.py's fail-closed verification. It is not a migration.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

psycopg = pytest.importorskip("psycopg", reason="psycopg is required for real PostgreSQL acceptance")
from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SQL = ROOT / "tests" / "fixtures" / "word_sessions_postgres.sql"
TEST_DB_BOOTSTRAP = ROOT / "scripts" / "test_db.py"


@pytest.fixture(scope="module")
def pg_admin_dsn():
    """Accept only an explicitly configured DB proven test-only by the repo gate."""
    dsn = os.environ.get("VINDEX_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set VINDEX_TEST_PG_DSN to a verified disposable local PostgreSQL cluster")
    if not os.environ.get("VINDEX_TEST_PG_PORTS"):
        pytest.skip("set VINDEX_TEST_PG_PORTS so the disposable cluster port can be verified")
    try:
        checked = subprocess.run(
            [sys.executable, str(TEST_DB_BOOTSTRAP), "verify", "--dsn", dsn],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=os.environ.copy(),
        )
    except Exception:
        pytest.skip("the local PostgreSQL safety verifier could not run")
    if checked.returncode != 0:
        pytest.skip("VINDEX_TEST_PG_DSN did not pass the local PostgreSQL safety verifier")
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    if info.get("dbname") != "postgres":
        pytest.skip("VINDEX_TEST_PG_DSN must target the isolated cluster admin database postgres")
    return dsn


@pytest.fixture(scope="module")
def pg_dsn(pg_admin_dsn):
    """Create and remove a dedicated test database inside the verified throwaway cluster."""
    dbname = "vindex_word_sessions_" + uuid.uuid4().hex[:12]
    info = psycopg.conninfo.conninfo_to_dict(pg_admin_dsn)
    admin = psycopg.conninfo.make_conninfo(**{**info, "dbname": "postgres"})
    target = psycopg.conninfo.make_conninfo(**{**info, "dbname": dbname})
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    try:
        with psycopg.connect(target, autocommit=True) as conn:
            conn.execute(FIXTURE_SQL.read_text(encoding="utf-8"), prepare=False)
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (dbname,))
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname)))


_TABLE_COLUMNS = {
    "word_sessions": {
        "id", "user_id", "token_hash", "created_at", "expires_at", "revoked_at", "last_dispatch_claimed_at",
    },
    "profiles": {"id", "email", "full_name"},
    "korisnik_email_notif": {"user_id", "aktivan"},
}
_UUID_COLUMNS = {"id", "user_id"}
_TIMESTAMP_COLUMNS = {"created_at", "expires_at", "revoked_at", "last_dispatch_claimed_at"}


def _value_for_pg(table: str, column: str, value):
    if value is None:
        return None
    if column in _UUID_COLUMNS and isinstance(value, str):
        return uuid.UUID(value)
    if column in _TIMESTAMP_COLUMNS and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _json_row(row):
    return {
        key: value.isoformat() if isinstance(value, (datetime,)) else str(value) if isinstance(value, uuid.UUID) else value
        for key, value in row.items()
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _PgQuery:
    """Narrow PostgREST chain adapter backed by committed real PostgreSQL statements."""

    def __init__(self, client, table):
        if table not in _TABLE_COLUMNS:
            raise AssertionError(f"test adapter refuses unexpected table {table!r}")
        self.client = client
        self.table_name = table
        self.operation = "select"
        self.columns = None
        self.values = None
        self.filters = []
        self.single = False
        self.conflict = None

    def select(self, columns="*", **_kwargs):
        if self.operation == "select":
            self.columns = self._parse_columns(columns)
        else:
            self.columns = self._parse_columns(columns)
        return self

    def _parse_columns(self, columns):
        if columns == "*":
            return None
        names = [part.strip() for part in columns.split(",")]
        if not names or any(name not in _TABLE_COLUMNS[self.table_name] for name in names):
            raise AssertionError("test adapter received an unapproved column list")
        return names

    def eq(self, column, value):
        self._check_column(column)
        self.filters.append(("eq", column, value))
        return self

    def is_(self, column, value):
        self._check_column(column)
        self.filters.append(("is", column, value))
        return self

    def lt(self, column, value):
        self._check_column(column)
        self.filters.append(("lt", column, value))
        return self

    def maybe_single(self):
        self.single = True
        return self

    def insert(self, values):
        self.operation, self.values = "insert", values
        return self

    def update(self, values):
        self.operation, self.values = "update", values
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def upsert(self, values, on_conflict=None):
        self.operation, self.values, self.conflict = "upsert", values, on_conflict
        return self

    def _check_column(self, column):
        if column not in _TABLE_COLUMNS[self.table_name]:
            raise AssertionError(f"test adapter refuses unexpected column {column!r}")

    def _where(self):
        parts, params = [], []
        for operation, column, value in self.filters:
            ident = sql.Identifier(column)
            if operation == "eq":
                parts.append(sql.SQL("{}::text = %s").format(ident))
                params.append(str(value))
            elif operation == "is":
                if value == "null" or value is None:
                    parts.append(sql.SQL("{} IS NULL").format(ident))
                else:
                    parts.append(sql.SQL("{} IS NOT NULL").format(ident))
            else:
                parts.append(sql.SQL("{} < %s::timestamptz").format(ident))
                params.append(_value_for_pg(self.table_name, column, value))
        if not parts:
            return sql.SQL("TRUE"), params
        return sql.SQL(" AND ").join(parts), params

    def execute(self):
        with psycopg.connect(self.client.dsn, autocommit=True, row_factory=dict_row) as conn:
            conn.execute("SET ROLE service_role")
            table = sql.Identifier("public", self.table_name)
            where, params = self._where()
            if self.operation == "select":
                columns = self.columns or ["*"]
                selected = sql.SQL(", ").join(
                    sql.SQL("*") if column == "*" else sql.Identifier(column) for column in columns
                )
                rows = conn.execute(
                    sql.SQL("SELECT {} FROM {} WHERE {}").format(selected, table, where), params
                ).fetchall()
            elif self.operation in {"insert", "upsert"}:
                values = self.values or {}
                columns = list(values)
                if any(column not in _TABLE_COLUMNS[self.table_name] for column in columns):
                    raise AssertionError("test adapter received an unapproved insert column")
                column_sql = sql.SQL(", ").join(map(sql.Identifier, columns))
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
                query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(table, column_sql, placeholders)
                if self.operation == "upsert":
                    if self.conflict != "user_id" or "user_id" not in columns:
                        raise AssertionError("test adapter refuses unexpected upsert conflict target")
                    changes = [column for column in columns if column != "user_id"]
                    if changes:
                        updates = sql.SQL(", ").join(
                            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
                            for column in changes
                        )
                        query += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {}").format(
                            sql.Identifier("user_id"), updates
                        )
                    else:
                        query += sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(sql.Identifier("user_id"))
                rows = conn.execute(
                    query + sql.SQL(" RETURNING *"),
                    [_value_for_pg(self.table_name, column, values[column]) for column in columns],
                ).fetchall()
            elif self.operation == "update":
                values = self.values or {}
                columns = list(values)
                if any(column not in _TABLE_COLUMNS[self.table_name] for column in columns):
                    raise AssertionError("test adapter received an unapproved update column")
                assignments = sql.SQL(", ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(column)) for column in columns
                )
                returning = self.columns or ["*"]
                returned = sql.SQL(", ").join(
                    sql.SQL("*") if column == "*" else sql.Identifier(column) for column in returning
                )
                rows = conn.execute(
                    sql.SQL("UPDATE {} SET {} WHERE {} RETURNING {}").format(table, assignments, where, returned),
                    [_value_for_pg(self.table_name, column, values[column]) for column in columns] + params,
                ).fetchall()
            elif self.operation == "delete":
                rows = conn.execute(
                    sql.SQL("DELETE FROM {} WHERE {} RETURNING *").format(table, where), params
                ).fetchall()
            else:
                raise AssertionError("test adapter received an unsupported operation")

        data = [_json_row(row) for row in rows]
        if self.single:
            return _Result(data[0] if data else None)
        return _Result(data)


class _PgRpc:
    def __init__(self, client, name, params):
        self.client, self.name, self.params = client, name, params

    def execute(self):
        if self.name != "claim_word_session_provider_attempt":
            raise AssertionError("test adapter refuses unexpected RPC")
        p = self.params
        with psycopg.connect(self.client.dsn, autocommit=True) as conn:
            conn.execute("SET ROLE service_role")
            allowed = conn.execute(
                "SELECT public.claim_word_session_provider_attempt(%s::uuid,%s::uuid,%s::text)",
                (p["p_session_id"], p["p_user_id"], p["p_token_hash"]),
            ).fetchone()[0]
        with self.client._rpc_lock:
            self.client.rpc_results.append((dict(p), allowed))
        return _Result(allowed)


class _PgSupa:
    def __init__(self, dsn):
        self.dsn = dsn
        self.rpc_results = []
        self._rpc_lock = threading.Lock()

    def table(self, table):
        return _PgQuery(self, table)

    def rpc(self, name, params):
        return _PgRpc(self, name, params)


def _insert_user(dsn, user_id):
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("INSERT INTO auth.users (id) VALUES (%s) ON CONFLICT DO NOTHING", (uuid.UUID(user_id),))


def _seed_session(dsn, user_id, *, expired=False, revoked=False):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_id = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True) as conn:
        if expired:
            row = conn.execute(
                """INSERT INTO public.word_sessions
                     (id,user_id,token_hash,created_at,expires_at,revoked_at)
                   VALUES (%s,%s,%s,clock_timestamp()-interval '2 hours',
                           clock_timestamp()-interval '1 hour 1 second',
                           CASE WHEN %s THEN clock_timestamp() ELSE NULL END)
                   RETURNING id,user_id,token_hash,expires_at""",
                (uuid.UUID(session_id), uuid.UUID(user_id), token_hash, revoked),
            ).fetchone()
        else:
            row = conn.execute(
                """INSERT INTO public.word_sessions
                     (id,user_id,token_hash,created_at,expires_at,revoked_at)
                   VALUES (%s,%s,%s,clock_timestamp(),clock_timestamp()+interval '20 minutes',
                           CASE WHEN %s THEN clock_timestamp() ELSE NULL END)
                   RETURNING id,user_id,token_hash,expires_at""",
                (uuid.UUID(session_id), uuid.UUID(user_id), token_hash, revoked),
            ).fetchone()
    from routers.word_auth import WordSession

    return WordSession(
        session_id=str(row[0]),
        user_id=str(row[1]),
        token_hash=row[2],
        expires_at=row[3],
    )


async def _allow(*_args, **_kwargs):
    return None


def _auth_client(monkeypatch, db, user_id):
    from routers import word_auth
    import shared.deps

    monkeypatch.setattr(word_auth, "_get_supa", lambda: db)
    monkeypatch.setattr(shared.deps, "_get_supa", lambda: db)
    monkeypatch.setattr(word_auth, "_record_and_rate_limit", _allow)
    monkeypatch.setattr(word_auth, "_audit", _allow)

    async def confirm(_source_token):
        return user_id, {"exp": time.time() + 1800}

    monkeypatch.setattr(word_auth, "_confirm_source_identity", confirm)
    app = FastAPI()
    app.state.limiter = word_auth.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(word_auth.router)
    client_ip = f"10.77.0.{uuid.uuid4().int % 250 + 1}"
    return TestClient(app, base_url="https://vindex.test", client=(client_ip, 4321))


def _issue(client, *, spoofed_user_id=None):
    body = {"user_id": spoofed_user_id} if spoofed_user_id else {}
    return client.post(
        "/api/word/sessions",
        headers={"Authorization": "Bearer synthetic-source-token", "Origin": "https://vindex.test"},
        json=body,
    )


def _provider_response():
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-word-session-test",
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


def _run_provider(session, handler, *, max_retries=0):
    from openai import OpenAI
    from shared.word_session_dispatch import word_provider_session

    with OpenAI(
        api_key="test-only-not-a-credential",
        max_retries=max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), timeout=4),
    ) as provider:
        with word_provider_session(session):
            return provider.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "synthetic selected text"}],
            )


def test_word_session_issue_is_random_hash_only_and_uses_provider_identity(pg_dsn, monkeypatch):
    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    client = _auth_client(monkeypatch, db, user_id)
    spoofed_id = str(uuid.uuid4())

    response = _issue(client, spoofed_user_id=spoofed_id)

    assert response.status_code == 200, response.text
    issued = response.json()
    token = issued["session_token"]
    assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) >= 32
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        row = conn.execute(
            "SELECT user_id,token_hash,created_at,expires_at FROM public.word_sessions WHERE token_hash=%s",
            (token_hash,),
        ).fetchone()
    assert row is not None
    assert str(row[0]) == user_id
    assert str(row[0]) != spoofed_id
    assert row[1] == token_hash
    assert token not in {str(value) for value in row}
    assert row[2] < row[3] <= row[2] + timedelta(hours=1)
    assert len(token_hash) == 64 and token_hash == token_hash.lower()


def test_word_logout_revokes_only_the_current_session(pg_dsn, monkeypatch):
    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    client = _auth_client(monkeypatch, db, user_id)
    first = _issue(client)
    second = _issue(client)
    assert first.status_code == second.status_code == 200
    first_token = first.json()["session_token"]
    second_token = second.json()["session_token"]
    assert first_token != second_token

    logout = client.delete(
        "/api/word/sessions/current",
        headers={"Authorization": f"Bearer {first_token}", "Origin": "https://vindex.test"},
    )

    assert logout.status_code == 200, logout.text
    first_hash = hashlib.sha256(first_token.encode()).hexdigest()
    second_hash = hashlib.sha256(second_token.encode()).hexdigest()
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT token_hash,revoked_at FROM public.word_sessions WHERE user_id=%s",
            (uuid.UUID(user_id),),
        ).fetchall()
    state = {row[0]: row[1] for row in rows}
    assert state[first_hash] is not None
    assert state[second_hash] is None


def test_word_session_constraints_uniqueness_and_auth_delete_restrict(pg_dsn):
    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    session_id = str(uuid.uuid4())
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO public.word_sessions (id,user_id,token_hash,created_at,expires_at)
               VALUES (%s,%s,%s,clock_timestamp(),clock_timestamp()+interval '30 minutes')""",
            (uuid.UUID(session_id), uuid.UUID(user_id), token_hash),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                """INSERT INTO public.word_sessions (id,user_id,token_hash,created_at,expires_at)
                   VALUES (%s,%s,%s,clock_timestamp(),clock_timestamp()+interval '30 minutes')""",
                (uuid.uuid4(), uuid.UUID(user_id), token_hash),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """INSERT INTO public.word_sessions (user_id,token_hash,created_at,expires_at)
                   VALUES (%s,%s,clock_timestamp(),clock_timestamp()+interval '2 hours')""",
                (uuid.UUID(user_id), hashlib.sha256(secrets.token_bytes(32)).hexdigest()),
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """INSERT INTO public.word_sessions (user_id,token_hash,created_at,expires_at)
                   VALUES (%s,'NOT_A_HASH',clock_timestamp(),clock_timestamp()+interval '10 minutes')""",
                (uuid.UUID(user_id),),
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("DELETE FROM auth.users WHERE id=%s", (uuid.UUID(user_id),))
        conn.execute("DELETE FROM public.word_sessions WHERE id=%s", (uuid.UUID(session_id),))
        conn.execute("DELETE FROM auth.users WHERE id=%s", (uuid.UUID(user_id),))


def test_word_session_rls_and_rpc_are_server_only(pg_dsn):
    db = _PgSupa(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        assert conn.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid='public.word_sessions'::regclass"
        ).fetchone()[0] is True
        assert conn.execute(
            "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='word_sessions'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT has_table_privilege('anon','public.word_sessions','SELECT')"
        ).fetchone()[0] is False
        assert conn.execute(
            "SELECT has_table_privilege('authenticated','public.word_sessions','SELECT')"
        ).fetchone()[0] is False
        assert conn.execute(
            "SELECT has_table_privilege('service_role','public.word_sessions','SELECT')"
        ).fetchone()[0] is True
        assert conn.execute(
            "SELECT has_function_privilege('anon','public.claim_word_session_provider_attempt(uuid,uuid,text)','EXECUTE')"
        ).fetchone()[0] is False
        assert conn.execute(
            "SELECT has_function_privilege('authenticated','public.claim_word_session_provider_attempt(uuid,uuid,text)','EXECUTE')"
        ).fetchone()[0] is False

        conn.execute("SET ROLE anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM public.word_sessions")
        conn.execute("RESET ROLE")
        conn.execute("SET ROLE authenticated")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT public.claim_word_session_provider_attempt(gen_random_uuid(),gen_random_uuid(),'x')")
        conn.execute("RESET ROLE")

    # The same function is callable through the server-only adapter.
    result = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": str(uuid.uuid4()),
        "p_user_id": str(uuid.uuid4()),
        "p_token_hash": "0" * 64,
    }).execute()
    assert result.data is False


def test_dispatch_claim_matches_session_user_hash_and_database_expiry(pg_dsn):
    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    live = _seed_session(pg_dsn, user_id)
    expired = _seed_session(pg_dsn, user_id, expired=True)

    good = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": live.session_id,
        "p_user_id": live.user_id,
        "p_token_hash": live.token_hash,
    }).execute()
    wrong_user = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": live.session_id,
        "p_user_id": str(uuid.uuid4()),
        "p_token_hash": live.token_hash,
    }).execute()
    wrong_hash = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": live.session_id,
        "p_user_id": live.user_id,
        "p_token_hash": "f" * 64,
    }).execute()
    wrong_session = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": str(uuid.uuid4()),
        "p_user_id": live.user_id,
        "p_token_hash": live.token_hash,
    }).execute()
    expired_result = db.rpc("claim_word_session_provider_attempt", {
        "p_session_id": expired.session_id,
        "p_user_id": expired.user_id,
        "p_token_hash": expired.token_hash,
    }).execute()

    assert good.data is True
    assert wrong_user.data is wrong_hash.data is wrong_session.data is expired_result.data is False
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        claimed_at = conn.execute(
            "SELECT last_dispatch_claimed_at FROM public.word_sessions WHERE id=%s",
            (uuid.UUID(live.session_id),),
        ).fetchone()[0]
    assert claimed_at is not None


def test_logout_committed_before_dispatch_produces_no_provider_attempt(pg_dsn, monkeypatch):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    session = _seed_session(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute("UPDATE public.word_sessions SET revoked_at=clock_timestamp() WHERE id=%s", (uuid.UUID(session.session_id),))

    provider_calls = []
    def handler(_request):
        provider_calls.append(1)
        return _provider_response()

    with pytest.raises(Exception) as exc:
        _run_provider(session, handler)
    assert word_session_dispatch.word_session_dispatch_denial(exc.value) is not None
    assert provider_calls == []
    assert db.rpc_results[-1][1] is False


@pytest.mark.parametrize("invalid_kind", ["wrong_user", "wrong_session", "wrong_hash", "expired"])
def test_invalid_or_expired_session_never_reaches_provider(pg_dsn, monkeypatch, invalid_kind):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    live = _seed_session(pg_dsn, user_id)
    if invalid_kind == "wrong_user":
        session = replace(live, user_id=str(uuid.uuid4()))
    elif invalid_kind == "wrong_session":
        session = replace(live, session_id=str(uuid.uuid4()))
    elif invalid_kind == "wrong_hash":
        session = replace(live, token_hash="f" * 64)
    else:
        session = _seed_session(pg_dsn, user_id, expired=True)

    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    provider_calls = []

    def handler(_request):
        provider_calls.append(1)
        return _provider_response()

    with pytest.raises(Exception) as exc:
        _run_provider(session, handler)
    assert word_session_dispatch.word_session_dispatch_denial(exc.value) is not None
    assert provider_calls == []
    assert [allowed for _params, allowed in db.rpc_results] == [False]


def test_claim_commits_before_provider_and_authorizes_only_that_attempt(pg_dsn, monkeypatch):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    session = _seed_session(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    provider_calls = []
    revocation_committed = []

    def handler(_request):
        provider_calls.append(1)
        # A distinct connection must acquire the same row lock while the
        # provider is running. Success proves the RPC transaction committed.
        with psycopg.connect(pg_dsn, autocommit=True) as conn:
            conn.execute("SET lock_timeout='1000ms'")
            revocation_committed.append(conn.execute(
                "UPDATE public.word_sessions SET revoked_at=clock_timestamp() WHERE id=%s RETURNING id",
                (uuid.UUID(session.session_id),),
            ).fetchone() is not None)
        return _provider_response()

    result = _run_provider(session, handler)
    assert result.choices[0].message.content == "synthetic"
    assert provider_calls == [1]
    assert revocation_committed == [True]
    assert [allowed for _params, allowed in db.rpc_results] == [True]


def test_revocation_before_sdk_retry_denies_retry(pg_dsn, monkeypatch):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    session = _seed_session(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    provider_calls = []

    def handler(_request):
        provider_calls.append(1)
        with psycopg.connect(pg_dsn, autocommit=True) as conn:
            conn.execute("UPDATE public.word_sessions SET revoked_at=clock_timestamp() WHERE id=%s", (uuid.UUID(session.session_id),))
        return httpx.Response(503, json={"error": "synthetic retry trigger"})

    from shared.word_session_dispatch import WordSessionDispatchDenied
    with pytest.raises(Exception) as exc:
        _run_provider(session, handler, max_retries=1)
    assert word_session_dispatch.word_session_dispatch_denial(exc.value) is not None
    assert provider_calls == [1]
    assert [allowed for _params, allowed in db.rpc_results] == [True, False]


def test_database_outage_denies_dispatch_before_transport(pg_dsn, monkeypatch):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    session = _seed_session(pg_dsn, user_id)
    monkeypatch.setattr("shared.deps._get_supa", lambda: (_ for _ in ()).throw(RuntimeError("synthetic DB outage")))
    provider_calls = []

    def handler(_request):
        provider_calls.append(1)
        return _provider_response()

    with pytest.raises(Exception) as exc:
        _run_provider(session, handler)
    assert word_session_dispatch.word_session_dispatch_denial(exc.value) is not None
    assert provider_calls == []


def test_two_simultaneous_word_requests_claim_separately_without_holding_provider_lock(pg_dsn, monkeypatch):
    from shared import word_session_dispatch

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    session = _seed_session(pg_dsn, user_id)
    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    provider_barrier = threading.Barrier(2)
    provider_calls = []
    calls_lock = threading.Lock()

    def worker(_index):
        def handler(_request):
            with calls_lock:
                provider_calls.append(1)
            provider_barrier.wait(timeout=5)
            return _provider_response()
        result = _run_provider(session, handler)
        return result.choices[0].message.content

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, (1, 2)))

    assert results == ["synthetic", "synthetic"]
    assert provider_calls == [1, 1]
    assert [allowed for _params, allowed in db.rpc_results] == [True, True]


def test_expired_session_cleanup_keeps_unexpired_revoked_rows_and_reports_failure(pg_dsn, monkeypatch):
    from services import retention_service

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    expired = _seed_session(pg_dsn, user_id, expired=True)
    retained = _seed_session(pg_dsn, user_id, revoked=True)
    db = _PgSupa(pg_dsn)
    monkeypatch.setattr("shared.deps._get_supa", lambda: db)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        expired_before = conn.execute(
            "SELECT count(*) FROM public.word_sessions WHERE expires_at < clock_timestamp()"
        ).fetchone()[0]

    result = asyncio.run(retention_service._cleanup_word_sessions())

    assert result["status"] == "ok"
    assert result["obrisano"] == expired_before
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        rows = conn.execute("SELECT id FROM public.word_sessions WHERE user_id=%s", (uuid.UUID(user_id),)).fetchall()
    assert [str(row[0]) for row in rows] == [retained.session_id]
    assert expired.session_id not in {str(row[0]) for row in rows}
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        assert conn.execute(
            "SELECT count(*) FROM public.word_sessions WHERE expires_at < clock_timestamp()"
        ).fetchone()[0] == 0

    class BrokenSupa:
        def table(self, _name):
            raise RuntimeError("synthetic database failure")

    monkeypatch.setattr("shared.deps._get_supa", lambda: BrokenSupa())
    failed = asyncio.run(retention_service._cleanup_word_sessions())
    assert failed["status"] == "greska"
    assert failed["greska"] == "RuntimeError"


def test_gdpr_soft_erasure_revokes_all_sessions_before_profile_update(pg_dsn, monkeypatch):
    from routers import gdpr
    import shared.audit_immutable
    import shared.bg

    target_user, other_user = str(uuid.uuid4()), str(uuid.uuid4())
    _insert_user(pg_dsn, target_user)
    _insert_user(pg_dsn, other_user)
    first = _seed_session(pg_dsn, target_user)
    second = _seed_session(pg_dsn, target_user)
    other = _seed_session(pg_dsn, other_user)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO public.profiles (id,email,full_name) VALUES (%s,%s,%s)",
            (uuid.UUID(target_user), "erasure@example.test", "Test User"),
        )

    db = _PgSupa(pg_dsn)
    monkeypatch.setattr(gdpr, "_get_supa", lambda: db)
    async def fake_audit(*_args, **_kwargs):
        return None
    monkeypatch.setattr(shared.audit_immutable, "log_action", fake_audit)
    monkeypatch.setattr(shared.bg, "spawn", lambda coroutine: coroutine.close())
    app = FastAPI()
    app.state.limiter = gdpr.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(gdpr.router)

    async def current_user():
        return {"user_id": target_user, "email": "erasure@example.test"}
    app.dependency_overrides[gdpr.get_current_user] = current_user
    client_ip = f"10.88.0.{uuid.uuid4().int % 250 + 1}"
    with TestClient(app, base_url="https://vindex.test", client=(client_ip, 4321)) as client:
        response = client.delete("/api/gdpr/account", headers={"Authorization": "Bearer synthetic"})

    assert response.status_code == 200, response.text
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        state = dict(conn.execute(
            "SELECT id,revoked_at FROM public.word_sessions WHERE id = ANY(%s)",
            ([uuid.UUID(first.session_id), uuid.UUID(second.session_id), uuid.UUID(other.session_id)],),
        ).fetchall())
        profile = conn.execute("SELECT email FROM public.profiles WHERE id=%s", (uuid.UUID(target_user),)).fetchone()[0]
    assert state[uuid.UUID(first.session_id)] is not None
    assert state[uuid.UUID(second.session_id)] is not None
    assert state[uuid.UUID(other.session_id)] is None
    assert profile.startswith("deleted_")


def test_gdpr_session_store_failure_prevents_profile_anonymization(pg_dsn, monkeypatch):
    from routers import gdpr

    user_id = str(uuid.uuid4())
    _insert_user(pg_dsn, user_id)
    _seed_session(pg_dsn, user_id)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO public.profiles (id,email,full_name) VALUES (%s,%s,%s)",
            (uuid.UUID(user_id), "failure@example.test", "Failure User"),
        )
    db = _PgSupa(pg_dsn)

    class FailWordSessionQuery:
        def update(self, _values):
            return self
        def eq(self, *_args):
            return self
        def is_(self, *_args):
            return self
        def execute(self):
            raise RuntimeError("synthetic session database failure")

    class FailWordSessionSupa:
        def table(self, table):
            return FailWordSessionQuery() if table == "word_sessions" else db.table(table)

    import shared.audit_immutable
    import shared.bg
    monkeypatch.setattr(gdpr, "_get_supa", lambda: FailWordSessionSupa())
    async def fake_audit(*_args, **_kwargs):
        return None
    monkeypatch.setattr(shared.audit_immutable, "log_action", fake_audit)
    monkeypatch.setattr(shared.bg, "spawn", lambda coroutine: coroutine.close())
    app = FastAPI()
    app.state.limiter = gdpr.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(gdpr.router)

    async def current_user():
        return {"user_id": user_id, "email": "failure@example.test"}
    app.dependency_overrides[gdpr.get_current_user] = current_user
    client_ip = f"10.89.0.{uuid.uuid4().int % 250 + 1}"
    with TestClient(app, base_url="https://vindex.test", client=(client_ip, 4321)) as client:
        response = client.delete("/api/gdpr/account", headers={"Authorization": "Bearer synthetic"})

    assert response.status_code == 503, response.text
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        email = conn.execute("SELECT email FROM public.profiles WHERE id=%s", (uuid.UUID(user_id),)).fetchone()[0]
    assert email == "failure@example.test"
