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


DRAFT_MONTH = "2026-11"


@pytest.fixture
def drafting_db(db):
    with connect(db) as c:
        c.execute("""
            CREATE TABLE public.audit_log (id integer);
            CREATE TABLE public.user_credits (
                user_id uuid PRIMARY KEY,
                credits_remaining integer NOT NULL,
                mesecno_korisceno integer DEFAULT 0,
                mesec text,
                updated_at timestamptz DEFAULT now()
            );
            ALTER TABLE public.user_credits ENABLE ROW LEVEL SECURITY;
        """)
        c.execute("INSERT INTO predmeti (id,user_id) VALUES (%s,%s),(%s,%s)", (CASE_A, A, CASE_OTHER, B))
        c.execute("INSERT INTO user_credits (user_id,credits_remaining) VALUES (%s,5),(%s,5)", (A, B))
    for migration in (
        "043_security_bulletproof.sql", "064_feature_registry.sql",
        "107_beta_gate_credit_race_closure.sql", "108_atomic_usage_counters.sql", MIGRATION,
    ):
        P.primeni(db, migration)
    return db


def proposal(*, case=CASE_A, court_sources=()):
    red = {
        "id": str(uuid4()), "user_id": str(A), "predmet_id": str(case),
        "naziv": "Sintetički predlog", "tekst": TEXT, "confidence_score": 0.75,
        "quality_detail": {"predlog": {"sha256": FINGERPRINT}}, "mesec": DRAFT_MONTH,
    }
    if court_sources:
        red["sudski_izvori"] = [str(doc) for doc in court_sources]
    return red


def save_proposal(conn, red, *, sources=None, credits=1, role="service_role"):
    from psycopg.types.json import Jsonb

    P.kao(conn, role, red["user_id"])
    conn.execute("SET LOCAL statement_timeout = '5s'")
    return conn.execute(
        "SELECT public.mir03_sacuvaj_nacrt(%s,%s,%s)",
        (Jsonb(red), Jsonb(sources or {}), credits),
    ).fetchone()[0]


def drafting_state(dsn):
    with connect(dsn) as c:
        balance = c.execute(
            "SELECT credits_remaining,mesecno_korisceno,mesec FROM user_credits WHERE user_id=%s", (A,),
        ).fetchone()
        rows = c.execute(
            "SELECT id::text,user_id,predmet_id,tip,status,is_lawyer_approved,tekst FROM staging_memory",
        ).fetchall()
    return balance, rows


def expected_proposal(red):
    return (red["id"], str(A), str(CASE_A), "nacrt_iz_spisa", "pending", False, TEXT)


def add_draft_source(dsn, *, owner=A, kind=None):
    with connect(dsn) as c:
        return c.execute(
            """INSERT INTO predmet_dokumenti (predmet_id,user_id,tekst_sadrzaj,tip_dokaza)
               VALUES (%s,%s,%s,%s) RETURNING id""", (CASE_A, owner, TEXT, kind),
        ).fetchone()[0]


def test_save_draft_rpc_acl_and_duplicate_id_cannot_charge_again(drafting_db):
    from psycopg import errors

    red = proposal()
    signature = "public.mir03_sacuvaj_nacrt(jsonb,jsonb,integer)"
    with connect(drafting_db) as c:
        assert c.execute(
            "SELECT r, has_function_privilege(r,%s,'EXECUTE') "
            "FROM unnest(ARRAY['anon','authenticated','service_role']) AS roles(r)", (signature,),
        ).fetchall() == [("anon", False), ("authenticated", False), ("service_role", True)]
        assert c.execute(
            """SELECT p.prosecdef,p.proconfig,EXISTS (
                 SELECT 1 FROM aclexplode(p.proacl) acl WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'
               ) FROM pg_proc p WHERE p.oid=%s::regprocedure""", (signature,),
        ).fetchone() == (False, ['search_path=""'], False)
    for role in ("anon", "authenticated"):
        with pytest.raises(errors.InsufficientPrivilege), connect(drafting_db) as c:
            save_proposal(c, red, role=role)
    assert drafting_state(drafting_db) == ((5, 0, None), [])

    with connect(drafting_db) as c:
        assert save_proposal(c, red, credits=2) == 3
    with pytest.raises(errors.UniqueViolation), connect(drafting_db) as c:
        save_proposal(c, red, credits=2)
    assert drafting_state(drafting_db) == ((3, 1, DRAFT_MONTH), [expected_proposal(red)])


def test_refused_proposal_rolls_back_debit_month_and_insert(drafting_db):
    from psycopg import errors

    with connect(drafting_db) as c:
        c.execute("""
            CREATE FUNCTION public.synthetic_reject_proposal() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM public.user_credits
                    WHERE user_id=NEW.user_id::uuid AND credits_remaining=3
                      AND mesecno_korisceno=1 AND mesec='2026-11'
                ) THEN
                    RAISE EXCEPTION 'Synthetic test expected debit and monthly count before INSERT';
                END IF;
                RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='Synthetic stage refusal after debit';
            END;
            $$;
            CREATE TRIGGER synthetic_reject_proposal AFTER INSERT ON public.staging_memory
                FOR EACH ROW EXECUTE FUNCTION public.synthetic_reject_proposal();
        """)
    with pytest.raises(errors.CheckViolation, match="Synthetic stage refusal after debit"), connect(drafting_db) as c:
        save_proposal(c, proposal(), credits=2)
    assert drafting_state(drafting_db) == ((5, 0, None), [])


@pytest.mark.parametrize("first_commits", [True, False])
def test_separate_proposals_serialize_the_credit_gate(drafting_db, first_commits):
    with connect(drafting_db) as c:
        c.execute("UPDATE user_credits SET credits_remaining=1 WHERE user_id=%s", (A,))
    red1, red2 = proposal(), proposal()
    with connect(drafting_db) as first, connect(drafting_db) as second, ThreadPoolExecutor(1) as work:
        assert save_proposal(first, red1) == 0
        future = work.submit(save_proposal, second, red2)
        try:
            wait_for_real_lock(drafting_db, second.info.backend_pid, first.info.backend_pid)
        finally:
            if first_commits:
                first.commit()
            else:
                first.rollback()
        assert future.result(timeout=6) == (-1 if first_commits else 0)
    winner = red1 if first_commits else red2
    assert drafting_state(drafting_db) == ((0, 1, DRAFT_MONTH), [expected_proposal(winner)])


def test_withdrawal_wins_while_proposal_waits_on_source(drafting_db):
    from psycopg import Error

    doc = add_draft_source(drafting_db)
    with connect(drafting_db) as author, connect(drafting_db) as drafter, ThreadPoolExecutor(1) as work:
        P.kao(author, "service_role", str(A))
        author.execute("DELETE FROM predmet_dokumenti WHERE id=%s", (doc,))
        future = work.submit(save_proposal, drafter, proposal(), sources={str(doc): FINGERPRINT})
        try:
            wait_for_real_lock(drafting_db, drafter.info.backend_pid, author.info.backend_pid)
        finally:
            author.commit()
        with pytest.raises(Error) as exc:
            future.result(timeout=6)
        assert exc.value.sqlstate == "PT409"
        drafter.rollback()
    assert drafting_state(drafting_db) == ((5, 0, None), [])


def test_proposal_requires_owned_sources_and_latest_audited_court_kind(drafting_db):
    from json import dumps

    from psycopg import Error
    from psycopg.types.json import Jsonb

    doc = add_draft_source(drafting_db, kind="court_decision")
    foreign_doc = add_draft_source(drafting_db, owner=B)
    red = proposal(court_sources=(doc,))
    sources = {str(doc): FINGERPRINT}
    for invalid_red, invalid_sources in (
        (proposal(case=CASE_OTHER), {}), (proposal(), {str(foreign_doc): FINGERPRINT}), (red, sources),
    ):
        with pytest.raises(Error) as exc, connect(drafting_db) as c:
            save_proposal(c, invalid_red, sources=invalid_sources)
        assert exc.value.sqlstate == "PT409"
    assert drafting_state(drafting_db) == ((5, 0, None), [])

    audit_sql = """INSERT INTO audit_immutable
        (prev_hash,entry_hash,user_id,action,resource_type,resource_id,metadata)
        VALUES (%s,%s,%s,'dokument_vrsta_ispravljena','predmet_dokumenti',%s,%s)"""
    with connect(drafting_db) as c:
        # The real audit writer serializes metadata before inserting it into JSONB.
        c.execute(audit_sql, ("0" * 64, "1" * 64, A, str(doc), Jsonb(dumps({
            "novo": "court_decision", "predmet_id": str(CASE_A),
        }))))
    with connect(drafting_db) as c:
        assert save_proposal(c, red, sources=sources) == 4
    with connect(drafting_db) as c:
        c.execute("UPDATE predmet_dokumenti SET tip_dokaza='other' WHERE id=%s", (doc,))
    with pytest.raises(Error) as exc, connect(drafting_db) as c:
        save_proposal(c, proposal(court_sources=(doc,)), sources=sources)
    assert exc.value.sqlstate == "PT409"

    with connect(drafting_db) as c:
        c.execute("UPDATE predmet_dokumenti SET tip_dokaza='court_decision' WHERE id=%s", (doc,))
        c.execute(audit_sql, ("1" * 64, "2" * 64, A, str(doc), Jsonb({"novo": "other", "predmet_id": str(CASE_A)})))
    with pytest.raises(Error) as exc, connect(drafting_db) as c:
        save_proposal(c, proposal(court_sources=(doc,)), sources=sources)
    assert exc.value.sqlstate == "PT409"
    assert drafting_state(drafting_db) == ((4, 1, DRAFT_MONTH), [expected_proposal(red)])
