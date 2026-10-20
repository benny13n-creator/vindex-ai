# -*- coding: utf-8 -*-
"""NS4 O3 — migracija 140 nad STVARNIM PostgreSQL-om: preuzimanje ponovnog upisa, rok, token, jedinstvenost
knjigovodstvenog reda nacrta i dozvole. Lokalni dokaz (VINDEX_PG_TEST_DSN) — bez promenljive se preskače."""
import threading
import uuid

import pytest

import tests.ns4f_pg as P

A, B = "uid-a", "uid-b"
PRAG, ISTEK = 0.85, 600


@pytest.fixture(scope="module")
def db():
    P.potreban_pg()
    dsn = P.nova_baza()
    yield dsn
    P.obrisi_bazu(dsn)


def _psy():
    import psycopg
    return psycopg


def _nacrt(db, user=A, status="approved", odobren=True, ocena=0.92, indeks=False):
    sid = str(uuid.uuid4())
    with _psy().connect(db, autocommit=True) as c:
        c.execute("INSERT INTO public.staging_memory (id, user_id, predmet_id, tip, naziv, tekst, confidence_score, "
                  "is_lawyer_approved, status, pinecone_indexed) VALUES (%s,%s,'p1','podnesak','N','t',%s,%s,%s,%s)",
                  (sid, user, ocena, odobren, status, indeks))
    return sid


def _preuzmi(db, sid, user=A, conn=None):
    sql = "SELECT id, promocija_token FROM public.preuzmi_ponovni_upis_nacrta(%s::uuid, %s::text, %s::numeric, %s::integer)"
    if conn is not None:
        return conn.execute(sql, (sid, user, PRAG, ISTEK)).fetchall()
    with _psy().connect(db) as c:
        with c.transaction():
            c.execute("SET LOCAL ROLE service_role")
            return c.execute(sql, (sid, user, PRAG, ISTEK)).fetchall()


def _zavrsi(db, sid, token, indeks):
    with _psy().connect(db) as c:
        with c.transaction():
            c.execute("SET LOCAL ROLE service_role")
            return c.execute("SELECT public.zavrsi_promociju_nacrta(%s::uuid, %s::uuid, %s)",
                             (sid, token, indeks)).fetchone()[0]


def _stanje(db, sid):
    with _psy().connect(db) as c:
        return c.execute("SELECT status, pinecone_indexed, promocija_token FROM public.staging_memory WHERE id=%s",
                         (sid,)).fetchone()


def test_podoban_nacrt_preuzima_tacno_jedan_od_istovremenih(db):
    sid = _nacrt(db)
    rez, kapija = [], threading.Barrier(6)

    def radnik():
        kapija.wait()
        rez.append(len(_preuzmi(db, sid)))
    niti = [threading.Thread(target=radnik) for _ in range(6)]
    for n in niti:
        n.start()
    for n in niti:
        n.join(20)
    assert sorted(rez) == [0, 0, 0, 0, 0, 1], "više od jednog aktivnog pokušaja za isti nacrt"


@pytest.mark.parametrize("kw", [dict(status="pending", odobren=False), dict(status="rejected", odobren=False),
                                dict(ocena=0.5), dict(indeks=True), dict(odobren=False)],
                         ids=["pending", "rejected", "ispod-praga", "vec-indeksiran", "bez-overe"])
def test_nepodoban_nacrt_se_ne_preuzima(db, kw):
    sid = _nacrt(db, **kw)
    assert _preuzmi(db, sid) == []
    assert _stanje(db, sid)[2] is None


def test_tudji_nacrt_se_ne_preuzima(db):
    assert _preuzmi(db, _nacrt(db, user=B), user=A) == []


def test_rok_napustenog_pokusaja_i_token_zastarelog_radnika(db):
    sid = _nacrt(db)
    [(_, t1)] = _preuzmi(db, sid)
    assert _preuzmi(db, sid) == [], "drugi pokušaj pre isteka roka"
    with _psy().connect(db, autocommit=True) as c:          # „pad procesa": rok je istekao
        c.execute("UPDATE public.staging_memory SET promocija_preuzeta_at = now() - interval '1 hour' WHERE id=%s", (sid,))
    [(_, t2)] = _preuzmi(db, sid)
    assert t2 != t1
    assert _zavrsi(db, sid, t1, True) is False, "zastareo radnik je zatvorio tuđi pokušaj"
    assert _stanje(db, sid) == ("approved", False, t2)
    assert _zavrsi(db, sid, t2, True) is True
    assert _stanje(db, sid) == ("approved", True, None)


def test_odbijanje_tokom_pokusaja_ne_daje_indeksiran(db):
    sid = _nacrt(db)
    [(_, t)] = _preuzmi(db, sid)
    with _psy().connect(db, autocommit=True) as c:
        c.execute("UPDATE public.staging_memory SET status='rejected', is_lawyer_approved=false WHERE id=%s", (sid,))
    assert _zavrsi(db, sid, t, True) is False
    assert _stanje(db, sid) == ("rejected", False, None)


def test_neuspeh_cisti_token_i_ostavlja_podobnim(db):
    sid = _nacrt(db)
    [(_, t)] = _preuzmi(db, sid)
    assert _zavrsi(db, sid, t, False) is False
    assert _stanje(db, sid) == ("approved", False, None)
    assert len(_preuzmi(db, sid)) == 1


def test_jedinstven_knjigovodstveni_red_nacrta(db):
    with _psy().connect(db, autocommit=True) as c:
        p = str(uuid.uuid4())
        c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, storage_path, redni_broj) VALUES (%s, %s, 1)",
                  (p, "draft/staging/x1"))
        with pytest.raises(Exception) as e:
            c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, storage_path, redni_broj) VALUES (%s, %s, 2)",
                      (p, "draft/staging/x1"))
        assert getattr(e.value, "sqlstate", "") == "23505"
        for i in (3, 4):                              # stari oblik `draft/<session>` se ne dira
            c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, storage_path, redni_broj) VALUES (%s, %s, %s)",
                      (p, "draft/sess-ista", i))


@pytest.mark.parametrize("uloga", ["anon", "authenticated"])
def test_korisnik_ne_izvrsava_funkcije(db, uloga):
    sid = _nacrt(db)
    for sql in ("SELECT * FROM public.preuzmi_ponovni_upis_nacrta(%s::uuid, 'uid-a', 0, 60)",
                "SELECT public.zavrsi_promociju_nacrta(%s::uuid, gen_random_uuid(), true)"):
        with _psy().connect(db) as c:
            with pytest.raises(Exception) as e:
                with c.transaction():
                    P.kao(c, uloga, str(uuid.UUID(int=1)))
                    c.execute(sql, (sid,))
            assert getattr(e.value, "sqlstate", "") == "42501"


def test_migracija_140_ponovljiva_i_postojeci_redovi_netaknuti(db):
    sid = _nacrt(db, indeks=True)
    P.primeni(db, "140_ns4_oporavak_promocije_nacrta.sql")
    P.primeni(db, "138_ns4_memorija_bez_direktnog_pristupa.sql")
    assert _stanje(db, sid) == ("approved", True, None)


@pytest.mark.parametrize("uloga,ocekivano", [("anon", False), ("authenticated", False), ("service_role", True)])
@pytest.mark.parametrize("fn", ["public.preuzmi_ponovni_upis_nacrta(uuid,text,numeric,integer)",
                                "public.zavrsi_promociju_nacrta(uuid,uuid,boolean)"])
def test_pravo_izvrsavanja_direktno(db, uloga, ocekivano, fn):
    with _psy().connect(db) as c:
        assert c.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (uloga, fn)).fetchone()[0] is ocekivano
