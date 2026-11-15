"""S08 proof against the disposable local PostgreSQL cluster."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from shared.audit_immutable import _compute_entry_hash

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
A, B, CASE, ROK, DOC, OTHER = (UUID(int=i) for i in range(1, 7))
GENESIS = "0" * 64


@pytest.fixture(scope="module")
def connect():
    pg = pytest.importorskip("psycopg")
    port = os.environ.get("S08_TEST_PG_PORT")
    if not port and (dsn := os.environ.get("VINDEX_PG_TEST_DSN")):
        settings = pg.conninfo.conninfo_to_dict(dsn)
        if settings.get("host") == "127.0.0.1" and settings.get("dbname") == "postgres":
            port = settings.get("port")
    if not port:
        pytest.skip("S08 requires a disposable loopback PostgreSQL cluster")
    args = dict(host="127.0.0.1", port=int(port), user="postgres", connect_timeout=5)
    name = "s08_" + uuid4().hex
    with pg.connect(**args, dbname="postgres", autocommit=True) as admin:
        admin.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon;
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE ROLE authenticated;
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
                    CREATE ROLE service_role BYPASSRLS;
                END IF;
            END;
            $$;
        """)
        admin.execute(f"CREATE DATABASE {name}")
        try:
            with pg.connect(**args, dbname=name, autocommit=True) as db:
                db.execute("""
                    CREATE SCHEMA auth;
                    CREATE SCHEMA storage;
                    CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean);
                    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid';
                    CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql AS 'SELECT current_user::text';
                    CREATE TABLE audit_log (id int);
                    CREATE TABLE predmet_dokumenti (
                        id uuid PRIMARY KEY, user_id uuid, predmet_id uuid, naziv_fajla text
                    );
                    CREATE TABLE predmet_hronologija (
                        id uuid PRIMARY KEY, user_id uuid, predmet_id uuid,
                        akter text, dokument_naziv text
                    );
                    CREATE TABLE predmet_dokazi (
                        dokument_id uuid REFERENCES predmet_dokumenti ON DELETE SET NULL,
                        user_id uuid, predmet_id uuid, deleted_at timestamptz,
                        izvor_tvrdnje text, nacin_pronalaska text
                    );
                """)
                db.execute("""
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role
                """)
                for number in (43, 73, 81, 90, 126, 137, 148):
                    migration, = MIGRATIONS.glob(f"{number:03d}_*.sql")
                    db.execute(migration.read_text(encoding="utf-8-sig"))
                db.execute("""
                    GRANT SELECT, INSERT ON audit_immutable TO service_role;
                    GRANT USAGE ON SEQUENCE audit_immutable_seq_seq TO service_role;
                    GRANT SELECT, UPDATE ON predmet_hronologija, predmet_dokumenti TO service_role;
                    GRANT SELECT ON events TO service_role;
                """)
            yield lambda **kwargs: pg.connect(**args, dbname=name, **kwargs)
        finally:
            admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def db(connect):
    with connect(autocommit=True) as conn:
        conn.execute("""
            TRUNCATE audit_immutable, events, predmet_dokazi, predmet_hronologija, predmet_dokumenti;
            SELECT setval('audit_immutable_seq_seq', 32);
        """)
        conn.execute("INSERT INTO predmet_dokumenti VALUES (%s,%s,%s,'source.pdf')", (DOC, A, CASE))
        conn.execute("""
            INSERT INTO predmet_hronologija (id,user_id,predmet_id,akter,dokument_naziv,dokument_id)
            VALUES (%s,%s,%s,'Genome (AI)','source.pdf',%s)
        """, (ROK, A, CASE, DOC))
        yield conn


def insert(conn, *, who=A, review=False, action="rok_potvrdjen"):
    head = conn.execute("SELECT entry_hash FROM audit_immutable ORDER BY seq DESC LIMIT 1").fetchone()
    prev = head[0] if head else GENESIS
    ts = datetime.now(timezone.utc).isoformat()
    entry = _compute_entry_hash(prev, str(who), action, ts, "rok", str(ROK))
    # Match the Python writer: metadata is transmitted as a JSON string.
    return conn.execute("""
        INSERT INTO audit_immutable
            (prev_hash, entry_hash, user_id, action, created_at, resource_type, resource_id, metadata)
        VALUES (%s,%s,%s,%s,%s,'rok',%s,to_jsonb(%s::text))
        RETURNING id
    """, (prev, entry, who, action, ts, str(ROK), json.dumps({"ponovni_pregled": review}))).fetchone()


def delete(conn, doc=DOC):
    return conn.execute("""
        SELECT invalidated FROM invalidate_dokument_and_ai_claims_and_emit_event(%s,%s,%s,%s)
    """, (doc, CASE, A, uuid4())).fetchone()


def race(observer, blocked_conn, operation, release):
    """Observe an actual PostgreSQL blocker before releasing the other session."""
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(operation, blocked_conn)
        try:
            until = time.monotonic() + 5
            while time.monotonic() < until:
                if pending.done():
                    pytest.fail(f"Operation finished before lock wait: {pending.exception()}")
                if observer.execute("SELECT pg_blocking_pids(%s)", (blocked_conn.info.backend_pid,)).fetchone()[0]:
                    break
                time.sleep(0.02)
            else:
                pytest.fail("No lock wait observed")
        finally:
            release()
        return pending.result(timeout=6)


def session(connect):
    return connect(options="-c role=service_role -c statement_timeout=8000 -c TimeZone=UTC")


def test_pre_migration_interleaving_reproduces_false_confirmation(db, connect):
    db.execute("ALTER TABLE audit_immutable DISABLE TRIGGER trg_s08_guard_rok_confirmation")
    try:
        assert db.execute("SELECT dokument_id FROM predmet_hronologija").fetchone() == (DOC,)
        with session(connect) as deleting:
            assert delete(deleting) == (True,)
        assert db.execute("SELECT dokument_id FROM predmet_hronologija").fetchone() == (None,)
        with session(connect) as confirming:
            assert insert(confirming)
    finally:
        db.execute("ALTER TABLE audit_immutable ENABLE TRIGGER trg_s08_guard_rok_confirmation")


@pytest.mark.parametrize("linked", [True, False])
def test_delete_wins(db, connect, linked):
    import psycopg
    if not linked:
        db.execute("UPDATE predmet_hronologija SET dokument_id = NULL")
    with session(connect) as deleting, session(connect) as confirming:
        assert delete(deleting) == (True,)
        with pytest.raises(psycopg.Error) as failure:
            race(db, confirming, insert, deleting.commit)
        assert failure.value.sqlstate == "P0802"
        confirming.rollback()
    assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)


@pytest.mark.parametrize("linked", [True, False])
def test_confirmation_wins_and_keeps_review_semantics(db, connect, linked):
    if not linked:
        db.execute("UPDATE predmet_hronologija SET dokument_id = NULL")
    with session(connect) as deleting, session(connect) as confirming:
        # Start DELETE's transaction first, then force it to wait for confirmation.
        deleting.execute("SELECT now()")
        insert(confirming)
        assert race(db, deleting, delete, confirming.commit) == (True,)
        deleting.commit()
    assert db.execute("""
        SELECT events.created_at > audit_immutable.created_at
        FROM events CROSS JOIN audit_immutable
    """).fetchone() == (True,)
    import psycopg
    with session(connect) as stale_first_request:
        with pytest.raises(psycopg.Error) as duplicate:
            insert(stale_first_request)
        assert duplicate.value.sqlstate == "P0801"
        stale_first_request.rollback()
    with session(connect) as confirming:
        insert(confirming, review=True)
    with session(connect) as confirming:
        with pytest.raises(psycopg.Error) as duplicate:
            insert(confirming, review=True)
        assert duplicate.value.sqlstate == "P0801"
        confirming.rollback()
    assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (2,)


def test_concurrent_confirmation_and_hash_chain(db, connect):
    import psycopg
    with session(connect) as seed:
        insert(seed, action="predmet_view")
    with session(connect) as first, session(connect) as second:
        insert(first)
        with pytest.raises(psycopg.Error) as duplicate:
            race(db, second, insert, first.commit)
        assert duplicate.value.sqlstate == "P0801"
        second.rollback()
    rows = db.execute("""
        SELECT prev_hash, entry_hash, user_id, action, created_at, resource_type, resource_id
        FROM audit_immutable ORDER BY seq
    """).fetchall()
    assert [row[3] for row in rows] == ["predmet_view", "rok_potvrdjen"]
    previous = GENESIS
    for prev, entry, who, action, ts, resource, rid in rows:
        assert prev == previous
        assert entry == _compute_entry_hash(previous, str(who), action,
                                            ts.astimezone(timezone.utc).isoformat(), resource, rid)
        previous = entry
    with pytest.raises(psycopg.Error, match="UPDATE nije dozvoljen"):
        db.execute("UPDATE audit_immutable SET action = 'tampered'")


def test_confirmation_lock_timeout_leaves_no_audit_row(db, connect):
    import psycopg

    with session(connect) as holder, session(connect) as confirming:
        holder.execute("SELECT id FROM predmet_hronologija WHERE id = %s FOR UPDATE", (ROK,))
        confirming.execute("SET LOCAL lock_timeout = '100ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            insert(confirming)
        confirming.rollback()
        assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)
        holder.rollback()
        assert insert(confirming)
    assert db.execute("SELECT prev_hash FROM audit_immutable").fetchall() == [(GENESIS,)]


def test_same_name_and_tenant_scope(db, connect):
    import psycopg
    db.execute("INSERT INTO predmet_dokumenti VALUES (%s,%s,%s,'source.pdf')", (OTHER, A, CASE))
    with session(connect) as deleting:
        assert delete(deleting) == (True,)
    with session(connect) as confirming:
        with pytest.raises(psycopg.Error) as foreign:
            insert(confirming, who=B)
        assert foreign.value.sqlstate == "P0804"
        confirming.rollback()
        # Remaining same-name document gives unknown provenance.
        insert(confirming)
    assert db.execute("SELECT user_id FROM audit_immutable").fetchall() == [(A,)]


def test_hash_collision_with_unrelated_writer_retries_with_fresh_head(db, connect):
    import psycopg
    with session(connect) as unrelated, session(connect) as confirming:
        insert(unrelated, action="predmet_view")
        with pytest.raises(psycopg.errors.UniqueViolation):
            race(db, confirming, insert, unrelated.commit)
        confirming.rollback()
        insert(confirming)
    assert db.execute("""
        SELECT a.entry_hash = b.prev_hash FROM audit_immutable a CROSS JOIN audit_immutable b
        WHERE a.action = 'predmet_view' AND b.action = 'rok_potvrdjen'
    """).fetchone() == (True,)


def test_foreign_name_and_failed_source_read_fail_closed(db, connect):
    import psycopg
    with session(connect) as deleting:
        delete(deleting)
    db.execute("INSERT INTO predmet_dokumenti VALUES (%s,%s,%s,'source.pdf')", (OTHER, B, CASE))
    with session(connect) as confirming:
        with pytest.raises(psycopg.Error) as withdrawn:
            insert(confirming)
        assert withdrawn.value.sqlstate == "P0802"
        confirming.rollback()
    db.execute("REVOKE SELECT ON predmet_dokumenti FROM service_role")
    try:
        with session(connect) as confirming:
            with pytest.raises(psycopg.Error) as denied:
                insert(confirming)
            assert denied.value.sqlstate == "42501"
            confirming.rollback()
    finally:
        db.execute("GRANT SELECT ON predmet_dokumenti TO service_role")
    assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_public_insert_cannot_distinguish_owner_or_source(db, role):
    import psycopg
    delete(db)
    # Model Supabase default object grants. RLS on audit still has no INSERT policy.
    with db.transaction(force_rollback=True):
        db.execute(f"GRANT SELECT, INSERT ON audit_immutable TO {role}")
        db.execute(f"GRANT USAGE ON SEQUENCE audit_immutable_seq_seq TO {role}")
        db.execute(f"GRANT SELECT, UPDATE ON predmet_hronologija, predmet_dokumenti TO {role}")
        assert db.execute("""
            SELECT relrowsecurity, has_function_privilege(%s, 's08_guard_rok_confirmation()', 'EXECUTE')
            FROM pg_class WHERE oid = 'audit_immutable'::regclass
        """, (role,)).fetchone() == (True, False)
        db.execute(f"SET LOCAL ROLE {role}")
        assert db.execute("SELECT current_user").fetchone() == (role,)
        errors = []
        for owner, resource in ((A, str(ROK)), (B, str(ROK)), (A, "invalid-uuid")):
            with pytest.raises(psycopg.Error) as failure, db.transaction():
                db.execute("""
                    INSERT INTO audit_immutable
                        (prev_hash,entry_hash,user_id,action,resource_type,resource_id)
                    VALUES (%s,%s,%s,'rok_potvrdjen','rok',%s)
                """, (GENESIS, GENESIS, owner, resource))
            errors.append((failure.value.sqlstate, failure.value.diag.message_primary))
        assert errors[0] == errors[1] == errors[2]
        assert errors[0][0] == "42501"
        db.execute("RESET ROLE")
        assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)


@pytest.mark.parametrize("guard", [False, True], ids=["baseline", "s08"])
def test_failed_head_read_cannot_append_second_genesis(db, connect, monkeypatch, guard):
    """Real writer and DB error. Each call models a separate Data API transaction."""
    from types import SimpleNamespace
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-only")
    import api
    from shared.audit_immutable import log_action_sync

    db.execute("ALTER SEQUENCE audit_immutable_seq_seq RESTART WITH 1")
    for _ in range(32):
        insert(db, action="predmet_view")
    head = db.execute("SELECT entry_hash FROM audit_immutable WHERE seq=32").fetchone()[0]

    class DataApi:
        fail_head = True

        def table(self, name):
            assert name == "audit_immutable"
            return self

        def select(self, columns):
            assert columns == "entry_hash"
            self.record = None
            return self

        def order(self, column, *, desc):
            assert column == "seq" and desc
            return self

        def limit(self, number):
            assert number == 1
            return self

        def insert(self, record):
            self.record = record
            return self

        def execute(self):
            with session(connect) as conn:
                if self.record is None:
                    if self.fail_head:
                        conn.execute("SELECT 1/0")
                    rows = conn.execute("SELECT entry_hash FROM audit_immutable ORDER BY seq DESC LIMIT 1")
                    return SimpleNamespace(data=[{"entry_hash": row[0]} for row in rows])
                row = conn.execute("""
                    INSERT INTO audit_immutable
                        (prev_hash,entry_hash,user_id,action,resource_type,resource_id,metadata,created_at,correlation_id)
                    VALUES (%(prev_hash)s,%(entry_hash)s,%(user_id)s,%(action)s,%(resource_type)s,
                            %(resource_id)s,to_jsonb(%(metadata)s::text),%(created_at)s,%(correlation_id)s)
                    RETURNING id
                """, self.record).fetchone()
                return SimpleNamespace(data=[{"id": row[0]}])

    adapter = DataApi()
    monkeypatch.setattr(api, "_get_supa", lambda: adapter)
    if not guard:
        db.execute("ALTER TABLE audit_immutable DISABLE TRIGGER trg_s08_guard_rok_confirmation")
    try:
        assert log_action_sync("rok_potvrdjen", str(A), "rok", str(ROK)) is None
        assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (32,)
        adapter.fail_head = False
        assert log_action_sync("rok_potvrdjen", str(A), "rok", str(ROK))
        assert db.execute("SELECT seq,prev_hash FROM audit_immutable ORDER BY seq DESC LIMIT 1").fetchone() == (33, head)
    finally:
        if not guard:
            db.execute("ALTER TABLE audit_immutable ENABLE TRIGGER trg_s08_guard_rok_confirmation")


def test_foreign_linked_document_does_not_authorize_confirmation(db, connect):
    import psycopg
    db.execute("UPDATE predmet_dokumenti SET user_id = %s WHERE id = %s", (B, DOC))
    with session(connect) as confirming:
        with pytest.raises(psycopg.Error) as failure, confirming.transaction():
            insert(confirming)
        assert failure.value.sqlstate == "P0804"
        assert confirming.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)


def test_s08_trigger_functions_have_no_api_execute_grants(db):
    assert db.execute("""
        SELECT r.rolname, p.proname
        FROM pg_roles r CROSS JOIN pg_proc p
        WHERE r.rolname IN ('anon', 'authenticated', 'service_role')
          AND p.oid IN ('public.s08_guard_rok_confirmation()'::regprocedure,
                        'public.s08_stamp_document_invalidation()'::regprocedure)
          AND has_function_privilege(r.oid, p.oid, 'EXECUTE')
    """).fetchall() == []


def test_postgrest_confirmation_role_and_error_contract(db):
    """Run against a real gateway when S08_POSTGREST_BIN is provided."""
    import socket
    import subprocess

    import httpx
    import jwt
    from psycopg import sql

    executable = os.environ.get("S08_POSTGREST_BIN")
    if not executable:
        pytest.skip("S08_POSTGREST_BIN must point to a local PostgREST binary")
    login = "s08_gateway_" + uuid4().hex
    authenticator = sql.Identifier(login)
    secret = uuid4().hex + uuid4().hex
    with socket.socket() as address:
        address.bind(("127.0.0.1", 0))
        port = address.getsockname()[1]
    db.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(authenticator))
    try:
        db.execute(sql.SQL("GRANT anon, authenticated, service_role TO {}").format(authenticator))
        db.execute("""
            GRANT SELECT, INSERT ON audit_immutable TO anon, authenticated;
            GRANT USAGE ON SEQUENCE audit_immutable_seq_seq TO anon, authenticated;
        """)
        settings = {
            "PGRST_DB_URI": f"postgresql://{login}@127.0.0.1:{db.info.port}/{db.info.dbname}",
            "PGRST_DB_SCHEMAS": "public",
            "PGRST_DB_ANON_ROLE": "anon",
            "PGRST_JWT_SECRET": secret,
            "PGRST_SERVER_HOST": "127.0.0.1",
            "PGRST_SERVER_PORT": str(port),
        }
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PGRST_")}
        with subprocess.Popen([executable], env=env | settings) as server:
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                    for _ in range(100):
                        try:
                            if client.get("/").is_success:
                                break
                        except httpx.ConnectError:
                            pass
                        assert server.poll() is None, "PostgREST exited during startup"
                        time.sleep(0.05)
                    else:
                        pytest.fail("PostgREST did not start")

                    def confirm(role, owner, resource=str(ROK)):
                        headers = {}
                        if role != "anon":
                            token = jwt.encode({"role": role, "sub": str(A)}, secret, algorithm="HS256")
                            headers["Authorization"] = f"Bearer {token}"
                        timestamp = datetime.now(timezone.utc).isoformat()
                        return client.post("/audit_immutable", headers=headers, json={
                            "action": "rok_potvrdjen", "resource_type": "rok", "resource_id": resource,
                            "user_id": str(owner), "prev_hash": GENESIS, "created_at": timestamp,
                            "entry_hash": _compute_entry_hash(GENESIS, str(owner), "rok_potvrdjen",
                                                              timestamp, "rok", resource),
                        })

                    for role, status in (("anon", 401), ("authenticated", 403)):
                        replies = [confirm(role, owner, resource) for owner, resource in
                                   ((A, str(ROK)), (B, str(ROK)), (A, "invalid-uuid"))]
                        assert all(r.status_code == status and r.json() == replies[0].json() for r in replies)
                        assert replies[0].json()["code"] == "42501"
                    assert confirm("service_role", B).json()["code"] == "P0804"
                    assert delete(db) == (True,)
                    assert confirm("service_role", A).json()["code"] == "P0802"
                    assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (0,)
                    db.execute("INSERT INTO predmet_dokumenti VALUES (%s,%s,%s,'source.pdf')", (DOC, A, CASE))
                    db.execute("UPDATE predmet_hronologija SET dokument_id = %s WHERE id = %s", (DOC, ROK))
                    assert confirm("service_role", A).status_code == 201
                    assert confirm("service_role", A).json()["code"] == "P0801"
                    assert db.execute("SELECT count(*) FROM audit_immutable").fetchone() == (1,)
            finally:
                server.terminate()
    finally:
        db.execute("""
            REVOKE SELECT, INSERT ON audit_immutable FROM anon, authenticated;
            REVOKE USAGE ON SEQUENCE audit_immutable_seq_seq FROM anon, authenticated;
        """)
        db.execute(sql.SQL("DROP ROLE {}").format(authenticator))
