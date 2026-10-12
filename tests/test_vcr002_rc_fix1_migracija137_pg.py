# -*- coding: utf-8 -*-
"""VCR002 Release Closure — FIX 1: migracija 137 nad PRAVIM PostgreSQL-om (izolovan lokalni klaster, `VX_TEST_PG_DSN`).

Dokazuje sam SQL, ne model: jedna transakcija (povlačenje AI tvrdnji + brisanje reda + SourceInvalidated), rollback
pri grešci, vlasništvo unutar funkcije, ponovni poziv bez izmena, EXECUTE samo za service_role, i konkurentan upis
tvrdnje koja navodi dokument ne promakne (FOR UPDATE nad redom dokumenta). Šema tabela je minimalna, ali sa istim
tipovima i FK pravilom kao 016 / 073 (+ correlation_id), 117 i 135. Bez DSN-a testovi se preskaču.
"""
import threading
import time
import uuid

import pytest

from tests.ns007_pg import migracija, sveza_baza, zahteva_pg

pytestmark = zahteva_pg

_SEMA = """
CREATE TABLE public.predmet_dokumenti (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  user_id uuid NOT NULL, naziv_fajla text);
CREATE TABLE public.predmet_dokazi (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  dokument_id uuid REFERENCES public.predmet_dokumenti(id) ON DELETE SET NULL, user_id uuid NOT NULL,
  tvrdnja text NOT NULL, created_at timestamptz DEFAULT now(), deleted_at timestamptz,
  nacin_pronalaska text, izvor_tvrdnje text);
CREATE TABLE public.events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_type text NOT NULL, user_id text, predmet_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  dispatched_at timestamptz, dispatch_attempts integer NOT NULL DEFAULT 0, last_error text, correlation_id text);
"""

A, B = str(uuid.uuid4()), str(uuid.uuid4())


@pytest.fixture
def baza():
    import psycopg
    with sveza_baza() as dsn:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(_SEMA)
            c.execute(migracija("137"))
        yield dsn


def _pripremi(c):
    pid = c.execute("INSERT INTO predmeti (user_id, naziv) VALUES (%s, 'P 4711/2026') RETURNING id", (A,)).fetchone()[0]
    dok = c.execute("INSERT INTO predmet_dokumenti (predmet_id, user_id, naziv_fajla) VALUES (%s,%s,'Zapisnik.pdf') RETURNING id",
                    (pid, A)).fetchone()[0]
    drugi = c.execute("INSERT INTO predmet_dokumenti (predmet_id, user_id, naziv_fajla) VALUES (%s,%s,'Tuzba.pdf') RETURNING id",
                      (pid, A)).fetchone()[0]

    def t(tekst, dokument, izvor, nacin, obrisana=False):
        return str(c.execute(
            "INSERT INTO predmet_dokazi (predmet_id, dokument_id, user_id, tvrdnja, izvor_tvrdnje, nacin_pronalaska, deleted_at) "
            "VALUES (%s,%s,%s,%s,%s,%s, CASE WHEN %s THEN now() - interval '1 day' END) RETURNING id",
            (pid, dokument, A, tekst, izvor, nacin, obrisana)).fetchone()[0])
    ids = {
        "ai": t("Rok ističe 26.10.2026.", dok, "ai_klasifikacija", "egzaktan"),
        "ai_nije_nadjena": t("Model: sud je naložio izjašnjenje.", dok, "ai_klasifikacija", "nije_pronadjen"),
        "legacy_nadjena": t("Ročište je održano.", dok, None, "normalizovan"),
        "legacy_nepoznata": t("Nepoznat autor.", dok, None, "nije_pronadjen"),
        "advokat": t("Advokat: tuženi je usmeno priznao dug.", dok, "covek", None),
        "drugi_dokument": t("Rešenje uručeno 17.03.2025.", drugi, "ai_klasifikacija", "egzaktan"),
        "vec_povucena": t("Stara AI tvrdnja.", dok, "ai_klasifikacija", "egzaktan", True),
    }
    return str(pid), str(dok), ids


def _pozovi(c, pid, dok, uid=A, uloga="service_role", event_id=None):
    c.execute(f"SET ROLE {uloga}")
    try:
        return c.execute(
            "SELECT invalidated, tvrdnje_povucene FROM public.invalidate_dokument_and_ai_claims_and_emit_event(%s,%s,%s,%s,%s)",
            (dok, pid, uid, event_id or str(uuid.uuid4()), "corr-1")).fetchone()
    finally:
        c.execute("RESET ROLE")


def _stanje(c, dok):
    tvrdnje = {str(r[0]): (r[1], str(r[2]) if r[2] else None) for r in
               c.execute("SELECT id, deleted_at, dokument_id FROM predmet_dokazi").fetchall()}
    postoji = c.execute("SELECT count(*) FROM predmet_dokumenti WHERE id=%s", (dok,)).fetchone()[0] == 1
    dogadjaji = c.execute("SELECT payload FROM events WHERE event_type='SourceInvalidated'").fetchall()
    return tvrdnje, postoji, [d[0] for d in dogadjaji]


def test_jedna_transakcija_povlaci_samo_ai_tvrdnje_tog_dokumenta(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, dok, ids = _pripremi(c)
        pre = _stanje(c, dok)[0]
        assert _pozovi(c, pid, dok) == (True, 3)
        tvrdnje, postoji, dog = _stanje(c, dok)
    assert not postoji
    for k in ("ai", "ai_nije_nadjena", "legacy_nadjena"):
        assert tvrdnje[ids[k]][0] is not None, k                        # povučene
    for k in ("legacy_nepoznata", "advokat", "drugi_dokument"):
        assert tvrdnje[ids[k]][0] is None, k                            # nisu dirane
    assert tvrdnje[ids["vec_povucena"]][0] == pre[ids["vec_povucena"]][0]   # raniji trenutak povlačenja sačuvan
    assert tvrdnje[ids["advokat"]][1] is None                           # FK ON DELETE SET NULL (016) i dalje važi
    assert tvrdnje[ids["drugi_dokument"]][1] is not None
    assert len(dog) == 1 and dog[0]["source_id"] == dok and dog[0]["tvrdnje_povucene"] == 3


def test_greska_u_transakciji_ne_ostavlja_nista(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, dok, ids = _pripremi(c)
        pre = _stanje(c, dok)
        c.execute("CREATE FUNCTION pukni() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'events nedostupan'; END $$;"
                  "CREATE TRIGGER t BEFORE INSERT ON public.events FOR EACH ROW EXECUTE FUNCTION pukni();")
        with pytest.raises(psycopg.errors.RaiseException):
            _pozovi(c, pid, dok)
        c.execute("RESET ROLE")
        assert _stanje(c, dok) == pre                                   # ni povlačenje, ni brisanje, ni događaj
        c.execute("DROP TRIGGER t ON public.events")
        assert _pozovi(c, pid, dok) == (True, 3)                        # ponovni pokušaj završava posao


def test_tudji_korisnik_ne_dira_nista_i_ponovni_poziv_je_bez_izmena(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, dok, ids = _pripremi(c)
        pre = _stanje(c, dok)
        assert _pozovi(c, pid, dok, uid=B) == (False, 0)
        assert _stanje(c, dok) == pre
        assert _pozovi(c, pid, dok) == (True, 3)
        posle = _stanje(c, dok)
        assert _pozovi(c, pid, dok) == (False, 0)                       # ponovni poziv posle uspeha
        assert _stanje(c, dok) == posle


def test_execute_samo_service_role(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, dok, ids = _pripremi(c)
        for uloga in ("anon", "authenticated"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                _pozovi(c, pid, dok, uloga=uloga)
            c.execute("RESET ROLE")
        assert _stanje(c, dok)[1]
        assert _pozovi(c, pid, dok)[0] is True


def test_konkurentan_upis_tvrdnje_ne_promakne(baza):
    """Druga sesija upisuje AI tvrdnju koja navodi dokument (FK uzima KEY SHARE) i još nije potvrdila. Funkcija mora da
    čeka (FOR UPDATE), pa da povuče i tu tvrdnju — inače bi ostala aktivna i bez izvora."""
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, dok, ids = _pripremi(c)
    s1 = psycopg.connect(baza)
    s1.execute("INSERT INTO predmet_dokazi (predmet_id, dokument_id, user_id, tvrdnja, izvor_tvrdnje, nacin_pronalaska) "
               "VALUES (%s,%s,%s,'Kasna AI tvrdnja.','ai_klasifikacija','egzaktan')", (pid, dok, A))
    rez = {}

    def _brisi():
        with psycopg.connect(baza, autocommit=True) as c2:
            rez["out"] = _pozovi(c2, pid, dok)
    nit = threading.Thread(target=_brisi)
    nit.start()
    time.sleep(1.0)
    assert nit.is_alive(), "funkcija nije čekala na nepotvrđen upis tvrdnje"
    s1.commit()
    s1.close()
    nit.join(10)
    assert rez["out"] == (True, 4)
    with psycopg.connect(baza, autocommit=True) as c:
        aktivne = c.execute("SELECT tvrdnja FROM predmet_dokazi WHERE deleted_at IS NULL AND izvor_tvrdnje='ai_klasifikacija'"
                            ).fetchall()
    assert [a[0] for a in aktivne] == ["Rešenje uručeno 17.03.2025."]
