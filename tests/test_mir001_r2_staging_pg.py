# -*- coding: utf-8 -*-
"""MIR001 FINAL RELEASE GATES, TASK-R2 — direktan Data API upis u `staging_memory`, nad STVARNIM PostgreSQL-om.

Dve baze sa istim podacima: BEZ i SA migracijom 141 (obe sa 088 i 140). Uloge kao PostgREST (`SET LOCAL ROLE` +
`request.jwt.claim.sub`); backend kao `service_role` (BYPASSRLS, kao `shared/deps._get_supa`).

Dokazuje se:
  • PRE 141: korisnik A svojim JWT-om direktno odobrava svoj dokument za sud, ubacuje već odobren red, menja
    poreklo, briše zapis i radi TRUNCATE — rupa (politika `FOR ALL`, prava `authenticated`).
  • POSLE 141 (osnivačevih 8 slučajeva): A ne odobrava, ne ubacuje odobren red, ne menja kontrolne kolone, ne briše,
    ne radi TRUNCATE; B ne vidi i ne menja A-ov red; `anon` nema nikakvo pravo; backend (`service_role`) i dalje radi
    tačno ono što rute rade — uslovno usvajanje/odobrenje po statusu + tekstu + reviziji (`quality_detail->>…`),
    odbijanje, novu verziju bez nasleđenog odobrenja, RPC ponovnog upisa iz 140; paralelni uslovni upisi prolaze
    tačno jednom (stvarna brava reda).
Lokalni dokaz (VINDEX_PG_TEST_DSN, izolovan klaster) — bez promenljive se preskače; NIKAD produkcija.
"""
import json
import threading
import uuid

import pytest

import tests.ns4f_pg as P

A, B = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))
PRED_A = str(uuid.uuid4())
PREDLOG, DOK = str(uuid.uuid4()), str(uuid.uuid4())


def _psy():
    import psycopg
    return psycopg


def _napuni(dsn):
    with _psy().connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.staging_memory (id, user_id, predmet_id, tip, naziv, tekst, quality_detail) "
                  "VALUES (%s,%s,%s,'nacrt_iz_spisa','AI radni predlog','PREDLOG',%s)",
                  (PREDLOG, A, PRED_A, json.dumps({"predlog": {"verzija_ugovora": 2, "sha256": "x"}})))
        c.execute("INSERT INTO public.staging_memory (id, user_id, predmet_id, tip, naziv, tekst, quality_detail) "
                  "VALUES (%s,%s,%s,'dokument_za_sud','Dokument za sud — verzija 1','Usvojen tekst.',%s)",
                  (DOK, A, PRED_A, json.dumps({"usvajanje": {"predlog_id": PREDLOG, "verzija": 1, "odobreno": None},
                                               "usvajanje_rev": 3})))


@pytest.fixture(scope="module")
def _baze_modula():
    P.potreban_pg()
    pre, posle = P.nova_baza(sa_ns4=True), P.nova_baza(sa_ns4=True)
    P.primeni(posle, "141_staging_memory_bez_direktnog_upisa.sql")
    yield pre, posle
    for d in (pre, posle):
        P.obrisi_bazu(d)


@pytest.fixture
def baze(_baze_modula):
    """Isto početno stanje pre SVAKOG testa: test_5/test_7 (backend) namerno odobravaju i menjaju redove, a CI meša
    redosled (pytest-randomly) — bez ovoga tvrdnje o nepromenjenom redu zavise od redosleda, ne od 141."""
    for d in _baze_modula:
        with _psy().connect(d, autocommit=True) as c:
            c.execute("DELETE FROM public.staging_memory")
        _napuni(d)
    return _baze_modula


def _kao(dsn, uloga, sub, sql, params=()):
    """Izvrši SQL kao uloga (PostgREST); vraća ('OK', broj redova / redovi) ili ('ODBIJENO', sqlstate)."""
    with _psy().connect(dsn) as c:
        try:
            with c.transaction():
                if uloga == "service_role":
                    c.execute("SET LOCAL ROLE service_role")
                else:
                    P.kao(c, uloga, sub)
                cur = c.execute(sql, params)
                return ("OK", cur.fetchall() if cur.description else cur.rowcount)
        except _psy().errors.InsufficientPrivilege as e:
            return ("ODBIJENO", e.sqlstate)


def _kao_greska(dsn, uloga, sub, sql, params=()):
    """SQLSTATE greške (bilo koje) ili None — za RLS odbijanje INSERT-a (42501 „new row violates row-level security")."""
    with _psy().connect(dsn) as c:
        try:
            with c.transaction():
                P.kao(c, uloga, sub)
                c.execute(sql, params)
                return None
        except _psy().Error as e:
            return e.sqlstate


def _red(dsn, sid):
    with _psy().connect(dsn, autocommit=True) as c:
        return c.execute("SELECT status, is_lawyer_approved, approved_by, quality_detail, tekst, user_id "
                         "FROM public.staging_memory WHERE id = %s", (sid,)).fetchone()


ODOBRI = ("UPDATE public.staging_memory SET status='approved', is_lawyer_approved=true, approved_by=%s, approved_at=now(),"
          " quality_detail = jsonb_set(quality_detail, '{usvajanje,odobreno}', '{\"sha256\":\"lazno\"}') WHERE id=%s")
UBACI_ODOBREN = ("INSERT INTO public.staging_memory (user_id, predmet_id, tip, naziv, tekst, status, is_lawyer_approved,"
                 " approved_by, quality_detail) VALUES (%s,%s,'dokument_za_sud','Lazni','Podmetnut tekst','approved',"
                 " true, %s, '{\"usvajanje\": {\"odobreno\": {\"sha256\": \"lazno\"}}}')")


# ── PRE 141: rupa postoji (da test ima zube) ─────────────────────────────────────────────────────────────────────
def test_pre_141_vlasnik_direktno_odobrava_i_podmece(baze):
    pre, _ = baze
    assert _kao(pre, "authenticated", A, ODOBRI, (A, DOK)) == ("OK", 1)
    assert _red(pre, DOK)[0] == "approved"
    assert _kao(pre, "authenticated", A, UBACI_ODOBREN, (A, PRED_A, A)) == ("OK", 1)
    assert _kao(pre, "authenticated", A, "UPDATE public.staging_memory SET predmet_id='tudji' WHERE id=%s", (PREDLOG,)) == ("OK", 1)
    assert _kao(pre, "authenticated", A, "TRUNCATE public.staging_memory")[0] == "OK"


# ── POSLE 141: osnivačevih 8 slučajeva ────────────────────────────────────────────────────────────────────────────
def test_1_vlasnik_ne_moze_direktno_da_odobri(baze):
    _, posle = baze
    assert _kao(posle, "authenticated", A, ODOBRI, (A, DOK)) == ("ODBIJENO", "42501")
    st, odobren, by, qd, _, _ = _red(posle, DOK)
    assert st == "pending" and odobren is False and by is None and qd["usvajanje"]["odobreno"] is None


def test_2_vlasnik_ne_moze_da_podmetne_odobren_red(baze):
    _, posle = baze
    assert _kao(posle, "authenticated", A, UBACI_ODOBREN, (A, PRED_A, A)) == ("ODBIJENO", "42501")
    with _psy().connect(posle, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM public.staging_memory WHERE naziv='Lazni'").fetchone()[0] == 0


@pytest.mark.parametrize("sql", [
    "UPDATE public.staging_memory SET status='rejected' WHERE id=%s",
    "UPDATE public.staging_memory SET is_lawyer_approved=true WHERE id=%s",
    "UPDATE public.staging_memory SET approved_by='neko' WHERE id=%s",
    "UPDATE public.staging_memory SET quality_detail='{}' WHERE id=%s",
    "UPDATE public.staging_memory SET tekst='Izmenjeno mimo rute' WHERE id=%s",
    "UPDATE public.staging_memory SET predmet_id='tudji' WHERE id=%s",
    "UPDATE public.staging_memory SET tip='nacrt' WHERE id=%s",
    "UPDATE public.staging_memory SET pinecone_indexed=true WHERE id=%s",
    "DELETE FROM public.staging_memory WHERE id=%s",
])
def test_3_vlasnik_ne_menja_kontrolne_ni_bilo_koje_kolone_i_ne_brise(baze, sql):
    _, posle = baze
    assert _kao(posle, "authenticated", A, sql, (DOK,)) == ("ODBIJENO", "42501")
    assert _red(posle, DOK)[0] == "pending" and _red(posle, DOK)[4] == "Usvojen tekst."


def test_3b_truncate_i_ostala_prava_oduzeta(baze):
    _, posle = baze
    for uloga in ("authenticated", "anon"):
        assert _kao(posle, uloga, A, "TRUNCATE public.staging_memory") == ("ODBIJENO", "42501")
    with _psy().connect(posle, autocommit=True) as c:
        prava = c.execute("SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema="
                          "'public' AND table_name='staging_memory' AND grantee IN ('anon','authenticated','PUBLIC')").fetchall()
        politike = c.execute("SELECT policyname, cmd FROM pg_policies WHERE tablename='staging_memory' ORDER BY 1").fetchall()
    assert prava == []
    assert politike == [("staging_memory_service_role", "ALL"), ("staging_memory_sopstveni_citanje", "SELECT")]
    # GATE-R2 N4: i kolonska prava (role_table_grants ih ne prikazuje) i svako pravo nad tabelom
    with _psy().connect(posle, autocommit=True) as c:
        for uloga in ("anon", "authenticated"):
            for pravo in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                assert c.execute("SELECT has_table_privilege(%s, 'public.staging_memory', %s)", (uloga, pravo)).fetchone()[0] is False
            assert c.execute("SELECT has_any_column_privilege(%s, 'public.staging_memory', 'SELECT,INSERT,UPDATE,REFERENCES')",
                             (uloga,)).fetchone()[0] is False
        assert c.execute("SELECT has_table_privilege('service_role', 'public.staging_memory', 'INSERT,UPDATE,DELETE,SELECT')").fetchone()[0]


def test_3c_kolonsko_pravo_dato_pre_migracije_nestaje(baze):
    """REVOKE ALL nad tabelom oduzima i ranije data KOLONSKA prava (npr. GRANT UPDATE(status) TO authenticated)."""
    P.potreban_pg()
    d = P.nova_baza(sa_ns4=True)
    try:
        with _psy().connect(d, autocommit=True) as c:
            c.execute("GRANT UPDATE (status, is_lawyer_approved) ON public.staging_memory TO authenticated")
            c.execute("GRANT INSERT (user_id) ON public.staging_memory TO PUBLIC")
        P.primeni(d, "141_staging_memory_bez_direktnog_upisa.sql")
        P.primeni(d, "141_staging_memory_bez_direktnog_upisa.sql")          # idempotentno
        with _psy().connect(d, autocommit=True) as c:
            assert c.execute("SELECT has_any_column_privilege('authenticated', 'public.staging_memory', 'INSERT,UPDATE')").fetchone()[0] is False
            assert c.execute("SELECT count(*) FROM pg_attribute WHERE attrelid='public.staging_memory'::regclass "
                             "AND attacl IS NOT NULL").fetchone()[0] == 0
    finally:
        P.obrisi_bazu(d)


def test_4b_usnula_politika_citanja_cuva_izolaciju_ako_se_select_vrati(baze):
    """GATE-R2 N5: ako bi se SELECT ikad vratio `authenticated`, politika iz 141 daje samo sopstvene redove (B ne vidi
    A-ov red), a upis i dalje ne prolazi (nema politike za INSERT/UPDATE/DELETE)."""
    P.potreban_pg()
    d = P.nova_baza(sa_ns4=True)
    try:
        P.primeni(d, "141_staging_memory_bez_direktnog_upisa.sql")
        _napuni(d)
        with _psy().connect(d, autocommit=True) as c:
            c.execute("GRANT ALL ON public.staging_memory TO authenticated")           # npr. buduće podrazumevano pravo
        assert _kao(d, "authenticated", B, "SELECT id FROM public.staging_memory") == ("OK", [])
        assert len(_kao(d, "authenticated", A, "SELECT id FROM public.staging_memory")[1]) == 2
        assert _kao(d, "authenticated", A, ODOBRI, (A, DOK)) == ("OK", 0)                # UPDATE: 0 redova (nema politike)
        r = _kao_greska(d, "authenticated", A, UBACI_ODOBREN, (A, PRED_A, A))
        assert r == "42501"                                                              # INSERT: RLS ga odbija
        assert _kao(d, "authenticated", A, "DELETE FROM public.staging_memory WHERE id=%s", (DOK,)) == ("OK", 0)
        assert _red(d, DOK)[0] == "pending"
    finally:
        P.obrisi_bazu(d)


def test_4_drugi_korisnik_ne_vidi_i_ne_menja(baze):
    _, posle = baze
    for sql in ("SELECT id FROM public.staging_memory WHERE id=%s", "UPDATE public.staging_memory SET status='approved' WHERE id=%s",
                "DELETE FROM public.staging_memory WHERE id=%s"):
        assert _kao(posle, "authenticated", B, sql, (DOK,)) == ("ODBIJENO", "42501")
    # ni vlasnik više ne čita direktno (frontend tabelu ne čita; sve ide kroz /api/staging/*)
    assert _kao(posle, "authenticated", A, "SELECT id FROM public.staging_memory WHERE id=%s", (DOK,)) == ("ODBIJENO", "42501")


def test_5_backend_usvajanje_odobrenje_i_odbijanje_rade(baze):
    """Isti uslovni upisi koje rade rute (`_uslovno_azuriraj_dokument`, `_odobri_dokument_za_sud`, reject) — kao
    PostgREST filter `quality_detail->>usvajanje_rev = '3'`, `status = 'pending'`, `tekst = …`."""
    _, posle = baze
    usvoji = ("UPDATE public.staging_memory SET tekst = tekst || E'\\n\\nNova stavka.', quality_detail = jsonb_set("
              "quality_detail, '{usvajanje_rev}', to_jsonb((quality_detail->>'usvajanje_rev')::int + 1)) WHERE id=%s"
              " AND user_id=%s AND status='pending' AND tekst=%s AND quality_detail->>'usvajanje_rev' = %s RETURNING id")
    assert _kao(posle, "service_role", None, usvoji, (DOK, A, "Usvojen tekst.", "3"))[1] == [(uuid.UUID(DOK),)]
    # zastarela revizija → 0 redova (ruta: 409)
    assert _kao(posle, "service_role", None, usvoji, (DOK, A, "Usvojen tekst.\n\nNova stavka.", "3"))[1] == []
    odobri = ("UPDATE public.staging_memory SET status='approved', is_lawyer_approved=true, approved_by=%s, approved_at=now()"
              " WHERE id=%s AND user_id=%s AND status='pending' AND tekst=%s AND quality_detail->>'usvajanje_rev' = %s RETURNING id")
    assert _kao(posle, "service_role", None, odobri, (A, DOK, A, "Usvojen tekst.\n\nNova stavka.", "4"))[1] == [(uuid.UUID(DOK),)]
    assert _red(posle, DOK)[:3] == ("approved", True, A)
    # odbijanje predloga (reject) — backend
    assert _kao(posle, "service_role", None, "UPDATE public.staging_memory SET status='rejected', is_lawyer_approved=false "
                "WHERE id=%s", (PREDLOG,)) == ("OK", 1)
    # RPC ponovnog upisa iz 140 i dalje izvršava backend (dokument za sud ga ruta odbija pre poziva — T06/C3b)
    r = _kao(posle, "service_role", None, "SELECT count(*) FROM public.preuzmi_ponovni_upis_nacrta(%s::uuid, %s, 0.85, 600)",
             (str(uuid.uuid4()), A))
    assert r[0] == "OK"


def test_6_nova_verzija_ne_nasledjuje_odobrenje_a_korisnik_ga_ne_moze_dodeliti(baze):
    _, posle = baze
    v2 = str(uuid.uuid4())
    nova = ("INSERT INTO public.staging_memory (id, user_id, predmet_id, tip, naziv, tekst, quality_detail) VALUES "
            "(%s,%s,%s,'dokument_za_sud','Dokument za sud — verzija 2','Usvojen tekst.',%s)")
    assert _kao(posle, "service_role", None, nova, (v2, A, PRED_A, json.dumps({"usvajanje": {"verzija": 2, "odobreno": None},
                                                                              "usvajanje_rev": 0})))[0] == "OK"
    st, odobren, by, qd, _, _ = _red(posle, v2)
    assert (st, odobren, by, qd["usvajanje"]["odobreno"]) == ("pending", False, None, None)   # podrazumevano iz 088
    assert _kao(posle, "authenticated", A, ODOBRI, (A, v2)) == ("ODBIJENO", "42501")


def test_7_paralelni_uslovni_upisi_prolaze_tacno_jednom(baze):
    """Stvarna brava reda: dva istovremena uslovna upisa nad ISTOM revizijom — tačno jedan prolazi (drugi posle čekanja
    ponovo proverava uslov nad novom verzijom reda i ne nalazi ga). Ponovljen zahtev (retry) sa starom revizijom = 0."""
    _, posle = baze
    sid = str(uuid.uuid4())
    with _psy().connect(posle, autocommit=True) as c:
        c.execute("INSERT INTO public.staging_memory (id, user_id, predmet_id, tip, tekst, quality_detail) VALUES "
                  "(%s,%s,%s,'dokument_za_sud','T',%s)", (sid, A, PRED_A, json.dumps({"usvajanje_rev": 7})))
    upis = ("UPDATE public.staging_memory SET quality_detail = jsonb_set(quality_detail, '{usvajanje_rev}', '8') WHERE id=%s"
            " AND status='pending' AND quality_detail->>'usvajanje_rev' = '7'")
    rez, kren = [], threading.Barrier(2)
    c1 = _psy().connect(posle)
    c1.execute("SET ROLE service_role")
    assert c1.execute(upis, (sid,)).rowcount == 1          # T1 drži bravu (nije commitovano)

    def _t2():
        with _psy().connect(posle) as c2:
            c2.execute("SET ROLE service_role")
            kren.wait()
            rez.append(c2.execute(upis, (sid,)).rowcount)  # čeka T1, pa ponovo proverava uslov
            c2.commit()
    t = threading.Thread(target=_t2)
    t.start()
    kren.wait()
    # GATE-R2 N6: dokaz da T2 ZAISTA čeka bravu reda koju drži T1 (ne samo redosled)
    import time
    ceka = False
    with _psy().connect(posle, autocommit=True) as nadzor:
        for _ in range(100):
            ceka = nadzor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND "
                                  "wait_event_type = 'Lock' AND query LIKE 'UPDATE public.staging_memory%%'").fetchone()[0] == 1
            if ceka:
                break
            time.sleep(0.05)
    assert ceka, "T2 nije čekao bravu"
    c1.commit()
    c1.close()
    t.join(10)
    assert rez == [0]
    assert _kao(posle, "service_role", None, upis, (sid,)) == ("OK", 0)          # retry sa starom revizijom


@pytest.mark.parametrize("sql", ["SELECT id FROM public.staging_memory", "INSERT INTO public.staging_memory (user_id, predmet_id,"
                                 " tip, tekst) VALUES ('x','y','z','t')", "UPDATE public.staging_memory SET status='approved'",
                                 "DELETE FROM public.staging_memory", "TRUNCATE public.staging_memory"])
def test_8_anon_nema_nikakvo_pravo(baze, sql):
    _, posle = baze
    assert _kao(posle, "anon", None, sql) == ("ODBIJENO", "42501")
