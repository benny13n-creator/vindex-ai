from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from time import monotonic, sleep
from uuid import uuid4

import pytest

from tests import ns4f_pg as P

MIGRATION = "149_mir03_approval_source_fence.sql"
A, B, CASE_A, CASE_OTHER = (uuid4() for _ in range(4))
TEXT = "Суд прихвата предлог.\r\nŽalba nije podneta."
FINGERPRINT = sha256(TEXT.encode("utf-8")).hexdigest()


@pytest.fixture
def db():
    P.potreban_pg()
    dsn = P.nova_baza(sa_ns4=False)
    P.primeni(dsn, "141_staging_memory_bez_direktnog_upisa.sql")
    try:
        yield dsn
    finally:
        P.obrisi_bazu(dsn)


@pytest.fixture
def fence(db):
    P.primeni(db, MIGRATION)
    return db


def connect(dsn):
    return P._psycopg().connect(dsn, connect_timeout=3)


def seed(dsn, *, vlasnik=A, predmet=CASE_A, tip="dokument_za_sud"):
    from psycopg.types.json import Jsonb

    with connect(dsn) as c:
        doc = c.execute(
            "INSERT INTO predmet_dokumenti (predmet_id,user_id,tekst_sadrzaj) VALUES (%s,%s,%s) RETURNING id",
            (predmet, vlasnik, TEXT),
        ).fetchone()[0]
        proposal = c.execute(
            """INSERT INTO staging_memory (predmet_id,user_id,tip,tekst,quality_detail)
               VALUES (%s,%s,'nacrt_iz_spisa','Predlog',%s) RETURNING id""",
            (str(CASE_A), str(A), Jsonb({"predlog": {"sha256": FINGERPRINT}})),
        ).fetchone()[0]
        draft = c.execute(
            """INSERT INTO staging_memory (predmet_id,user_id,tip,tekst,quality_detail)
               VALUES (%s,%s,%s,'Nacrt',%s) RETURNING id""",
            (str(CASE_A), str(A), tip, Jsonb({"usvajanje": {
                "predlog_id": str(proposal), "predlog_sha256": FINGERPRINT,
            }})),
        ).fetchone()[0]
    return doc, draft


def approve(conn, draft, fingerprints, role="service_role"):
    from psycopg.types.json import Jsonb

    P.kao(conn, role, str(A))
    conn.execute("SET LOCAL statement_timeout = '5s'")
    detail = {}
    if fingerprints is not None:
        detail["sha256_izvori"] = fingerprints
    return conn.execute(
        """UPDATE staging_memory SET status='approved',
           quality_detail=jsonb_set(quality_detail,'{usvajanje,odobreno}',%s)
           WHERE id=%s AND status='pending' RETURNING id""",
        (Jsonb(detail), draft),
    ).fetchone()


def status(dsn, draft):
    with connect(dsn) as c:
        return c.execute("SELECT status FROM staging_memory WHERE id=%s", (draft,)).fetchone()[0]


def test_red_frozen_database_writes_approval_after_source_deletion(db):
    doc, draft = seed(db)
    with connect(db) as c:
        c.execute("DELETE FROM predmet_dokumenti WHERE id=%s", (doc,))
    with connect(db) as c:
        assert approve(c, draft, {str(doc): FINGERPRINT}) == (draft,)
    assert status(db, draft) == "approved"


def test_locks_no_new_grants_and_wrong_or_unversioned_sources_fail(fence):
    from psycopg import Error

    with connect(fence) as c:
        acl = c.execute(
            "SELECT r, has_function_privilege(r,'public.proveri_izvore_pri_odobrenju_dokumenta_za_sud()', 'EXECUTE'),"
            "has_table_privilege(r,'public.staging_memory','UPDATE') "
            "FROM unnest(ARRAY['anon','authenticated','service_role']) AS a(r)"
        ).fetchall()
        assert acl == [("anon", False, False), ("authenticated", False, False), ("service_role", False, True)]
        assert c.execute(
            "SELECT prosecdef, proconfig FROM pg_proc WHERE oid = "
            "'public.proveri_izvore_pri_odobrenju_dokumenta_za_sud()'::regprocedure"
        ).fetchone() == (False, ['search_path=""'])

    for owner, matter, expected in [(B, CASE_A, FINGERPRINT), (A, CASE_OTHER, FINGERPRINT),
                                    (A, CASE_A, "0" * 64), (A, CASE_A, None)]:
        doc, draft = seed(fence, vlasnik=owner, predmet=matter)
        with pytest.raises(Error) as exc, connect(fence) as c:
            approve(c, draft, {str(doc): expected} if expected else None)
        assert exc.value.sqlstate == "PT409"
        assert status(fence, draft) == "pending"

    # Migration 141 restricts direct Data API roles. Even with test-only
    # accidental access, the trigger fails before reading any source.
    doc, draft = seed(fence)
    for role in ("anon", "authenticated"):
        with pytest.raises(Error) as exc, connect(fence) as c:
            approve(c, draft, {str(doc): FINGERPRINT}, role)
        assert exc.value.sqlstate == "42501"
    with pytest.raises(Error) as exc, connect(fence) as c:
        c.execute("GRANT SELECT,UPDATE ON staging_memory TO authenticated")
        c.execute("CREATE POLICY synthetic_wrong_grant ON staging_memory FOR UPDATE TO authenticated USING (true)")
        approve(c, draft, {str(doc): FINGERPRINT}, "authenticated")
    assert exc.value.sqlstate == "42501" and exc.value.diag.message_primary == "Odobrenje nije dozvoljeno."
    assert status(fence, draft) == "pending"


def test_unrelated_approval_and_approval_without_dependencies(fence):
    doc, draft = seed(fence)
    _, other = seed(fence, tip="odgovor_na_tuzbu")
    _, human_only = seed(fence)
    with connect(fence) as c:
        assert approve(c, draft, {str(doc): FINGERPRINT}) == (draft,)
        assert approve(c, other, None) == (other,)
        assert approve(c, human_only, {}) == (human_only,)
        assert approve(c, draft, {str(doc): FINGERPRINT}) is None


def wait_for_real_lock(dsn, blocked, blocker):
    end = monotonic() + 3
    with connect(dsn) as observer:
        while monotonic() < end:
            if blocker in observer.execute("SELECT pg_blocking_pids(%s)", (blocked,)).fetchone()[0]:
                return
            sleep(0.02)
    pytest.fail("Druga PostgreSQL sesija nije čekala očekivanu bravu.")


@pytest.mark.parametrize("operation", ["DELETE FROM predmet_dokumenti WHERE id=%s",
                                        "UPDATE predmet_dokumenti SET tekst_sadrzaj='izmenjen' WHERE id=%s"])
def test_withdrawal_or_edit_wins_while_approval_waits(fence, operation):
    from psycopg import Error

    doc, draft = seed(fence)
    with connect(fence) as author, connect(fence) as approver, ThreadPoolExecutor(1) as work:
        P.kao(author, "service_role", str(A))
        author.execute(operation, (doc,))
        fut = work.submit(approve, approver, draft, {str(doc): FINGERPRINT})
        try:
            wait_for_real_lock(fence, approver.info.backend_pid, author.info.backend_pid)
        finally:
            author.commit()
        with pytest.raises(Error) as exc:
            fut.result(timeout=6)
        assert exc.value.sqlstate == "PT409"
        approver.rollback()
    assert status(fence, draft) == "pending"


def test_approval_wins_then_source_can_be_deleted(fence):
    doc, draft = seed(fence)
    with connect(fence) as approver, connect(fence) as author, ThreadPoolExecutor(1) as work:
        assert approve(approver, draft, {str(doc): FINGERPRINT}) == (draft,)
        P.kao(author, "service_role", str(A))
        author.execute("SET LOCAL statement_timeout = '5s'")
        future = work.submit(author.execute, "DELETE FROM predmet_dokumenti WHERE id=%s", (doc,))
        try:
            wait_for_real_lock(fence, author.info.backend_pid, approver.info.backend_pid)
        finally:
            approver.commit()
        assert future.result(timeout=6).rowcount == 1
    assert status(fence, draft) == "approved"
    with connect(fence) as c:
        assert c.execute("SELECT 1 FROM predmet_dokumenti WHERE id=%s", (doc,)).fetchone() is None


def test_rejection_wins_while_approval_waits_on_proposal(fence):
    from psycopg import Error

    doc, draft = seed(fence)
    with connect(fence) as author, connect(fence) as approver, ThreadPoolExecutor(1) as work:
        P.kao(author, "service_role", str(A))
        author.execute("""UPDATE staging_memory SET status='rejected' WHERE id=(
                        SELECT (quality_detail #>> '{usvajanje,predlog_id}')::uuid FROM staging_memory WHERE id=%s)""",
                       (draft,))
        fut = work.submit(approve, approver, draft, {str(doc): FINGERPRINT})
        try:
            wait_for_real_lock(fence, approver.info.backend_pid, author.info.backend_pid)
        finally:
            author.commit()
        with pytest.raises(Error) as exc:
            fut.result(timeout=6)
        assert exc.value.sqlstate == "PT409"
        approver.rollback()
    assert status(fence, draft) == "pending"
