# -*- coding: utf-8 -*-
"""Migracija 142 nad PRAVIM PostgreSQL-om (privremen klaster iz tests/test_ocr001_trka_postgres.py, nikad produkcija,
nikad stvarni podaci). Stari `email_notif_log` se pravi DOSLOVNO iz 021 + 022 i puni sintetičkom istorijom.

Dokazuje: (1) migracija samo dodaje — stara istorija bajt-po-bajt ista; (2) ponovna primena je bezbedna, i posle
delimične primene; (3) ključ po događaju: različiti događaji istog predmeta/datuma i isti događaj u drugoj svrsi ili
na drugom datumu prolaze, isti ključ pada 23505 — i u dve istovremene transakcije; (4) uslovno ponavljanje
`neuspeh → rezervisano` dobija samo jedan proces; (5) CHECK ograničenja; (6) rollback briše samo nove tabele, a
ponovna primena posle njega radi. Preskače se bez PostgreSQL binarnih fajlova ili paketa psycopg."""
import re
import threading
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from tests.test_ocr001_trka_postgres import pg  # noqa: E402,F401  (privremen klaster)

KOREN = Path(__file__).resolve().parent.parent
M142 = (KOREN / "migrations/142_email_podsetnik_dogadjaj.sql").read_text(encoding="utf-8")


def _bez_komentara(sql):
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


def _odustajanje():
    """Zaštićen blok [ODUSTAJANJE] iz komentara migracije (bez `-- `)."""
    deo = M142.split("-- [ODUSTAJANJE]", 1)[1].split("\n", 1)[1]
    return "\n".join(re.sub(r"^--\s?", "", l) for l in deo.splitlines() if l.startswith("--"))


@pytest.fixture
def baza(pg):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        c.execute("DO $$ BEGIN CREATE ROLE service_role; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
        c.execute("CREATE SCHEMA IF NOT EXISTS auth; CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid "
                  "LANGUAGE sql AS $$ SELECT NULL::uuid $$;")
        c.execute((KOREN / "migrations/021_email_notif.sql").read_text(encoding="utf-8"))
        c.execute("ALTER TABLE email_notif_log ALTER COLUMN predmet_id DROP NOT NULL;")          # 022
        for i, (pid, datum, prag) in enumerate([("p-1", "2026-11-03", 1), ("p-1", "2026-11-05", 3),
                                                 ("p-2", "2026-11-09", 7), (None, "2026-11-02", 0)]):
            c.execute("INSERT INTO email_notif_log (user_id, predmet_id, datum_roka, dana_pre, poslato_at) "
                      "VALUES ('u-1', %s, %s, %s, '2026-11-02T08:05:00Z')", (pid, datum, prag))
    return pg


def _stari(c):
    return c.execute("SELECT id, user_id, predmet_id, datum_roka, dana_pre, poslato_at FROM email_notif_log "
                     "ORDER BY datum_roka, dana_pre").fetchall()


def _red(c, **k):
    r = {"user_id": "u-1", "predmet_id": "p-1", "tip": "rok", "dogadjaj_id": "r1", "datum_dogadjaja": "2026-11-03",
         "svrha": "prag_1", **k}
    c.execute("INSERT INTO email_podsetnik_dogadjaj (user_id, predmet_id, tip, dogadjaj_id, datum_dogadjaja, svrha) "
              "VALUES (%(user_id)s, %(predmet_id)s, %(tip)s, %(dogadjaj_id)s, %(datum_dogadjaja)s, %(svrha)s)", r)


def test_migracija_samo_dodaje_istorija_netaknuta_i_ponovljiva(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        pre = _stari(c)
        c.execute(M142)
        c.execute(M142)                                                        # ponovna primena
        assert _stari(c) == pre and len(pre) == 4
        assert c.execute("SELECT count(*) FROM email_podsetnik_dogadjaj").fetchone()[0] == 0   # istorija se NE prepisuje
        stari_kljuc = c.execute("SELECT count(*) FROM pg_constraint WHERE conrelid='email_notif_log'::regclass "
                                "AND contype='u'").fetchone()[0]
        assert stari_kljuc == 1                                                # stari UNIQUE ostaje za stari kod
        prava = {r[0] for r in c.execute("SELECT privilege_type FROM information_schema.role_table_grants WHERE "
                                         "table_name='email_podsetnik_dogadjaj' AND grantee='service_role'")}
        assert prava == {"SELECT", "INSERT", "UPDATE"}
        prava_p = {r[0] for r in c.execute("SELECT privilege_type FROM information_schema.role_table_grants WHERE "
                                           "table_name='email_podsetnik_pokretanje' AND grantee='service_role'")}
        assert prava_p == {"SELECT", "INSERT"}
        assert c.execute("SELECT relrowsecurity FROM pg_class WHERE relname='email_podsetnik_dogadjaj'").fetchone()[0]


def test_posle_delimicne_primene_ponovna_primena_zavrsava(baza):
    prvi = _bez_komentara(M142).split(";")[0] + ";"                            # samo CREATE TABLE dogadjaj
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(prvi)
        c.execute(M142)
        assert c.execute("SELECT to_regclass('public.email_podsetnik_pokretanje')").fetchone()[0] is not None


def test_kljuc_po_dogadjaju(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
        _red(c)
        _red(c, tip="rociste", dogadjaj_id="h1")                               # drugi događaj, isti predmet/datum/prag
        _red(c, dogadjaj_id="r2")                                              # drugi rok istog predmeta i datuma
        _red(c, svrha="kasni")                                                 # isti događaj, druga svrha
        _red(c, datum_dogadjaja="2026-11-05")                                  # pomeren datum = nova pojava
        _red(c, user_id="u-2")                                                 # drugi korisnik, isti tekst ključa
        with pytest.raises(psycopg.errors.UniqueViolation) as e:
            _red(c)
        assert "email_podsetnik_dogadjaj_kljuc" in str(e.value)
        assert c.execute("SELECT count(*) FROM email_podsetnik_dogadjaj").fetchone()[0] == 6


@pytest.mark.parametrize("kolona,vrednost", [("svrha", "prag_2"), ("tip", "zadatak"), ("stanje", "isporuceno"),
                                             ("pokusaja", 0)])
def test_check_ogranicenja(baza, kolona, vrednost):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(f"INSERT INTO email_podsetnik_dogadjaj (user_id, predmet_id, tip, dogadjaj_id, datum_dogadjaja, "
                      f"svrha, {kolona if kolona in ('stanje', 'pokusaja') else 'stanje'}) VALUES ('u-1','p-1',"
                      f"{repr(vrednost) if kolona == 'tip' else repr('rok')},'r1','2026-11-03',"
                      f"{repr(vrednost) if kolona == 'svrha' else repr('prag_1')},"
                      f"{repr(vrednost) if kolona in ('stanje', 'pokusaja') else repr('rezervisano')})")


def test_istovremena_rezervacija_istog_dogadjaja_dobija_samo_jedan(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
    a = psycopg.connect(baza)
    b = psycopg.connect(baza)
    ishod = {}
    try:
        _red(a)                                                                # A: nekomitovano
        def _b():
            try:
                _red(b)
                b.commit()
                ishod["b"] = "ok"
            except psycopg.errors.UniqueViolation:
                b.rollback()
                ishod["b"] = "23505"
        t = threading.Thread(target=_b)
        t.start()
        t.join(1.0)
        assert t.is_alive(), "B je morao da čeka A-ovu transakciju na jedinstvenom ključu"
        a.commit()
        t.join(10)
    finally:
        a.close()
        b.close()
    assert ishod["b"] == "23505"


def test_uslovno_ponavljanje_dobija_samo_jedan_proces(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
        rid = str(uuid.uuid4())
        c.execute("INSERT INTO email_podsetnik_dogadjaj (id, user_id, predmet_id, tip, dogadjaj_id, datum_dogadjaja, "
                  "svrha, stanje) VALUES (%s,'u-1','p-1','rok','r1','2026-11-03','prag_1','neuspeh')", (rid,))
    a = psycopg.connect(baza)
    b = psycopg.connect(baza)
    upit = ("UPDATE email_podsetnik_dogadjaj SET stanje='rezervisano', pokusaja=2 "
            "WHERE id=%s AND stanje='neuspeh' AND pokusaja=1")
    ishod = {}
    try:
        ishod["a"] = a.execute(upit, (rid,)).rowcount                         # A drži red
        t = threading.Thread(target=lambda: ishod.__setitem__("b", b.execute(upit, (rid,)).rowcount) or b.commit())
        t.start()
        t.join(1.0)
        a.commit()
        t.join(10)
    finally:
        a.close()
        b.close()
    assert (ishod["a"], ishod["b"]) == (1, 0)


def test_odustajanje_odbija_brisanje_cim_postoji_zapis(baza):
    """Nedestruktivno: sa ijednim zapisom blok baca grešku i NIŠTA ne briše."""
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
        _red(c)
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(_odustajanje())
        assert c.execute("SELECT count(*) FROM email_podsetnik_dogadjaj").fetchone()[0] == 1
        assert c.execute("SELECT to_regclass('public.email_podsetnik_pokretanje')").fetchone()[0] is not None


def test_odustajanje_bez_zapisa_brise_samo_nove_tabele_i_ponovna_primena_radi(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        pre = _stari(c)
        c.execute(M142)
        c.execute(_odustajanje())
        assert c.execute("SELECT to_regclass('public.email_podsetnik_dogadjaj')").fetchone()[0] is None
        assert _stari(c) == pre
        c.execute(M142)
        _red(c)
        assert c.execute("SELECT count(*) FROM email_podsetnik_dogadjaj").fetchone()[0] == 1


def test_odustajanje_ceka_istovremeni_upis_i_tada_odbija(baza):
    """Revizija S2-N F5: nekomitovan upis rezervacije u toku — blok čeka zaključavanje, vidi komitovan red i odbija."""
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M142)
    app = psycopg.connect(baza)
    ishod = {}
    try:
        _red(app)                                                              # aplikacija: nekomitovano
        def _operater():
            with psycopg.connect(baza, autocommit=True) as o:
                try:
                    o.execute(_odustajanje())
                    ishod["op"] = "obrisano"
                except psycopg.errors.RaiseException:
                    ishod["op"] = "odbijeno"
        t = threading.Thread(target=_operater)
        t.start()
        t.join(1.0)
        assert t.is_alive(), "blok je morao da čeka zaključavanje"
        app.commit()
        t.join(15)
    finally:
        app.close()
    assert ishod["op"] == "odbijeno"
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM email_podsetnik_dogadjaj").fetchone()[0] == 1
