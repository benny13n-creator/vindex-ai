# -*- coding: utf-8 -*-
"""BA04/BA08 — migracija 145 i identitet unosa hronologije po događaju, nad PRAVIM PostgreSQL-om.

Isti izolovan klaster i tanak psycopg lanac kao tests/test_ba05_migracija_144_postgres.py. Dokazuje: 145 samo dodaje,
ponovljiva je i ima vraćanje; dva različita događaja istog vidljivog teksta → dva reda; isti događaj ponovljen posle
upisa → jedan red; trka dva procesa (barijera pred INSERT-om) istog događaja → jedan red, različitih → dva; zatečeni
redovi netaknuti; bez 145 → ponašanje kao do sada.
"""
import asyncio
import uuid
from unittest.mock import patch

import pytest

psycopg = pytest.importorskip("psycopg")

from services.event_bus import Event, EventType  # noqa: E402  (pre case_evolution — redosled kao u aplikaciji)
import services.case_evolution as ce  # noqa: E402
from tests.test_ba05_migracija_144_postgres import (KOREN, U, Supa, _Upit, _istovremeno, baza,  # noqa: E402,F401
                                                    klaster)
from tests.test_ocr001_trka_postgres import pg  # noqa: E402,F401  (privremen klaster)

M145 = (KOREN / "migrations/145_hronologija_dogadjaj_event_id.sql").read_text(encoding="utf-8")


def _odustajanje():
    deo = M145.split("-- [ODUSTAJANJE]", 1)[1].split("\n", 1)[1]
    return "\n".join(l[3:] for l in deo.splitlines() if l.startswith("-- "))


class _UpitGte(_Upit):
    def gte(self, k, v):
        self.uslovi.append((f"{k} >= %s", v))
        return self


class SupaGte(Supa):
    def table(self, t):
        return _UpitGte(self, t)


def _prihvatanje(pid, eid=None):
    return Event(type=EventType.DOCUMENT_ACCEPTED, user_id=U, predmet_id=pid, payload={"dokumenti": ["scan.pdf"]},
                 event_id=eid or str(uuid.uuid4()))


def _unos(sp, ev):
    with patch.object(ce, "_get_supa", return_value=sp):
        return asyncio.run(ce._consequence_timeline_entry(ev))


def _redovi(dsn, pid):
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT id::text, dogadjaj, user_id::text, dogadjaj_event_id::text FROM public.predmet_hronologija "
                         "WHERE predmet_id = %s ORDER BY created_at, id", (pid,)).fetchall()


def _primeni(dsn):
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(M145)


def test_145_samo_dodaje_ponovljiva_i_vracanje(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        pre = c.execute("SELECT count(*), count(DISTINCT dogadjaj) FROM public.predmet_hronologija").fetchone()
        c.execute(M145)
        c.execute(M145)                                                          # ponovljiva
        kol = c.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'predmet_hronologija' "
                        "AND column_name = 'dogadjaj_event_id'").fetchone()
        assert kol == ("uuid",)
        assert c.execute("SELECT count(*), count(DISTINCT dogadjaj) FROM public.predmet_hronologija").fetchone() == pre
        assert c.execute("SELECT count(*) FROM public.predmet_hronologija WHERE dogadjaj_event_id IS NOT NULL").fetchone() == (0,)
        c.execute(_odustajanje())
        assert c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'predmet_hronologija' "
                         "AND column_name = 'dogadjaj_event_id'").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM public.predmet_hronologija").fetchone() == (pre[0],)


def test_T17_dva_dogadjaja_istog_teksta_dva_reda_a_isti_ponovljen_jedan(baza):
    _primeni(baza)
    sp, pid = SupaGte(baza), str(uuid.uuid4())
    e1, e2 = _prihvatanje(pid), _prihvatanje(pid)
    id1, id2 = _unos(sp, e1), _unos(sp, e2)
    assert id1 != id2
    assert _unos(sp, e1) == id1                                                  # pad posle upisa → ponovna obrada
    r = _redovi(baza, pid)
    assert [x[1] for x in r] == ["Dokument prihvaćen — scan.pdf"] * 2 and {x[3] for x in r} == {e1.event_id, e2.event_id}
    assert {x[2] for x in r} == {U}


def test_T18_trka_dva_procesa_isti_dogadjaj_jedan_red_razliciti_dva(baza):
    _primeni(baza)
    sp, pid = SupaGte(baza), str(uuid.uuid4())
    ev = _prihvatanje(pid)
    a, b = _istovremeno(sp, lambda: _unos(sp, ev), lambda: _unos(sp, ev))
    assert a == b and len(_redovi(baza, pid)) == 1
    pid2 = str(uuid.uuid4())
    e1, e2 = _prihvatanje(pid2), _prihvatanje(pid2)
    a, b = _istovremeno(sp, lambda: _unos(sp, e1), lambda: _unos(sp, e2))
    assert a != b and len(_redovi(baza, pid2)) == 2


class _UpitPadPosleUpisa(_UpitGte):
    """INSERT se izvrši i potvrdi u bazi, a odgovor se izgubi (pad procesa/veze POSLE commit-a)."""
    def execute(self):
        rez = super().execute()
        if self.red is not None and self.t == "predmet_hronologija" and self.sp.pad_posle_upisa:
            self.sp.pad_posle_upisa = False
            raise ConnectionError("veza pukla posle upisa (test)")
        return rez


class SupaPad(SupaGte):
    pad_posle_upisa = True

    def table(self, t):
        return _UpitPadPosleUpisa(self, t)


def test_pad_posle_potvrdjenog_upisa_ponovni_pokusaj_bez_duplikata(baza):
    _primeni(baza)
    sp, pid = SupaPad(baza), str(uuid.uuid4())
    ev = _prihvatanje(pid)
    with pytest.raises(ConnectionError):
        _unos(sp, ev)                                                            # red JESTE upisan, posledica pada
    [(rid, _, _, eid)] = _redovi(baza, pid)
    assert eid == ev.event_id
    assert _unos(sp, ev) == rid                                                  # ponovni pokušaj nalazi isti red
    assert _unos(sp, _prihvatanje(pid)) != rid and len(_redovi(baza, pid)) == 2  # drugi događaj, isto ime → nov red


def test_zateceni_redovi_netaknuti(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        pre = c.execute("SELECT id, dogadjaj, datum_iso, akter FROM public.predmet_hronologija ORDER BY id").fetchall()
    _primeni(baza)
    sp = SupaGte(baza)
    _unos(sp, _prihvatanje("11111111-1111-1111-1111-111111111111"))
    with psycopg.connect(baza, autocommit=True) as c:
        posle = c.execute("SELECT id, dogadjaj, datum_iso, akter FROM public.predmet_hronologija "
                          "WHERE dogadjaj_event_id IS NULL ORDER BY id").fetchall()
    assert posle == pre


def test_bez_145_radi_kao_do_sada(baza):
    sp, pid = SupaGte(baza), str(uuid.uuid4())
    ev = _prihvatanje(pid)
    id1 = _unos(sp, ev)
    assert _unos(sp, ev) == id1
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM public.predmet_hronologija WHERE predmet_id = %s", (pid,)).fetchone() == (1,)
