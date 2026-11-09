"""Isolated PostgreSQL proof for the court-draft approval audit transaction."""

from uuid import uuid4

import pytest

from shared.audit_immutable import _compute_entry_hash, _normalize_ts_for_hash
from tests.test_s08_postgres_concurrency import (
    A, B, CASE, GENESIS, MIGRATIONS, connect, db, insert, race, session,
)

ACTION = "dokument_za_sud_odobren"


@pytest.fixture
def staging(db):
    migration, = MIGRATIONS.glob("088_*.sql")
    db.execute(migration.read_text(encoding="utf-8"))
    db.execute("GRANT SELECT, UPDATE ON staging_memory TO service_role")
    try:
        yield db
    finally:
        db.execute("DROP TABLE staging_memory")
        db.execute("DROP FUNCTION IF EXISTS public.mir03_upisi_audit_odobrenja()")


@pytest.fixture
def atomic(staging):
    migration, = MIGRATIONS.glob("150_*.sql")
    staging.execute(migration.read_text(encoding="utf-8"))
    return staging


def new_draft(db):
    draft_id = uuid4()
    db.execute(
        "INSERT INTO staging_memory (id,user_id,predmet_id,tip,tekst) VALUES (%s,%s,%s,'dokument_za_sud','sinteticki')",
        (draft_id, str(A), str(CASE)),
    )
    return draft_id


def approve(conn, draft_id, *, who=A):
    return conn.execute(
        """UPDATE staging_memory SET status='approved', approved_by=%s,
           is_lawyer_approved=true, approved_at=clock_timestamp()
           WHERE id=%s AND status='pending' RETURNING id""",
        (str(who), draft_id),
    ).fetchone()


def test_without_transactional_audit_approval_has_no_audit_row(staging, connect):
    draft = new_draft(staging)
    with session(connect) as writer:
        assert approve(writer, draft) == (draft,)
    assert staging.execute("SELECT status FROM staging_memory WHERE id=%s", (draft,)).fetchone() == ("approved",)
    assert staging.execute("SELECT count(*) FROM audit_immutable WHERE action=%s", (ACTION,)).fetchone() == (0,)


def test_genesis_and_idempotent_approval_use_canonical_hash(atomic, connect):
    draft = new_draft(atomic)
    with session(connect) as writer:
        assert approve(writer, draft) == (draft,)
        assert approve(writer, draft) is None
    rows = atomic.execute(
        """SELECT prev_hash,entry_hash,to_jsonb(created_at)#>>'{}',user_id,resource_type,resource_id
           FROM audit_immutable WHERE action=%s""", (ACTION,),
    ).fetchall()
    assert len(rows) == 1
    prev_hash, entry_hash, stamp, uid, resource_type, resource_id = rows[0]
    assert prev_hash == GENESIS and (uid, resource_type, resource_id) == (A, "staging", str(draft))
    assert entry_hash == _compute_entry_hash(prev_hash, str(A), ACTION, _normalize_ts_for_hash(stamp),
                                             "staging", str(draft))


def test_audit_head_read_denial_rolls_back_approval(atomic, connect):
    from psycopg import errors

    draft = new_draft(atomic)
    atomic.execute("REVOKE SELECT ON audit_immutable FROM service_role")
    try:
        with pytest.raises(errors.InsufficientPrivilege), session(connect) as writer:
            approve(writer, draft)
    finally:
        atomic.execute("GRANT SELECT ON audit_immutable TO service_role")
    assert atomic.execute("SELECT status FROM staging_memory WHERE id=%s", (draft,)).fetchone() == ("pending",)
    assert atomic.execute("SELECT count(*) FROM audit_immutable WHERE action=%s", (ACTION,)).fetchone() == (0,)


def test_mismatched_actor_is_denied_before_audit(atomic, connect):
    from psycopg import errors

    draft = new_draft(atomic)
    with pytest.raises(errors.InsufficientPrivilege), session(connect) as writer:
        approve(writer, draft, who=B)
    assert atomic.execute("SELECT status FROM staging_memory WHERE id=%s", (draft,)).fetchone() == ("pending",)
    assert atomic.execute("SELECT count(*) FROM audit_immutable WHERE action=%s", (ACTION,)).fetchone() == (0,)


def test_competing_existing_writer_retries_and_links_approval(atomic, connect):
    draft = new_draft(atomic)
    with session(connect) as prior, session(connect) as writer:
        insert(prior, action="predmet_view")
        result = race(atomic, writer, lambda conn: approve(conn, draft), prior.commit)
        assert result == (draft,)
    rows = atomic.execute(
        """SELECT prev_hash,entry_hash,action,to_jsonb(created_at)#>>'{}',user_id,resource_type,resource_id
           FROM audit_immutable ORDER BY seq""",
    ).fetchall()
    assert [row[2] for row in rows] == ["predmet_view", ACTION]
    prev = GENESIS
    for prev_hash, entry, action, stamp, user_id, kind, resource_id in rows:
        assert prev_hash == prev
        assert entry == _compute_entry_hash(prev, str(user_id), action, _normalize_ts_for_hash(stamp), kind, resource_id)
        prev = entry
