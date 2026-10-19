# -*- coding: utf-8 -*-
"""NS4 G1/G2 — `zabelezi_ishod_predmeta` (migracija 139) nad STVARNIM PostgreSQL-om.

Invarijanta: za svakog korisnika i vrstu spora, `case_patterns` = funkcija zabeleženih ishoda (`outcome_log`), ne
raniji snimak. Proverava se protiv nezavisnog SQL proročišta (`_PROROCISTE`, isto kao provera (b) u migraciji)
posle: konkurentnih pisaca, ispravki, promene vrste spora, pada usred transakcije, prekida veze pre commit-a,
tačne granice od 1000 i više od 1000 faktora. Plus: dozvole (anon/authenticated ne izvršavaju funkciju i ne
pišu tabele), vlasništvo (tuđ predmet), deduplikacija faktora.

Lokalni dokaz (VINDEX_PG_TEST_DSN, tests/ns4f_pg.py) — bez promenljive se preskače.
"""
import threading
import time
import uuid

import pytest

import tests.ns4f_pg as P

pytestmark = pytest.mark.usefixtures("_pg")

A = str(uuid.UUID(int=0xA))
B = str(uuid.UUID(int=0xB))

_PROROCISTE = """
WITH f AS (SELECT DISTINCT o.user_id, o.tip_spora, o.predmet_id, o.ishod, e.faktor
             FROM public.outcome_log o CROSS JOIN LATERAL unnest(o.presudni_faktori) WITH ORDINALITY e(faktor, n)
            WHERE e.n <= 10 AND e.faktor IS NOT NULL AND o.tip_spora <> ''),
     a AS (SELECT user_id, tip_spora, faktor, count(*) FILTER (WHERE ishod='pobeda') p,
                  count(*) FILTER (WHERE ishod='poraz') po, count(*) u FROM f GROUP BY 1,2,3)
SELECT count(*) FROM public.case_patterns c FULL JOIN a USING (user_id, tip_spora, faktor)
 WHERE (COALESCE(c.pobede,0), COALESCE(c.porazi,0), COALESCE(c.ukupno,0)) IS DISTINCT FROM
       (COALESCE(a.p,0), COALESCE(a.po,0), COALESCE(a.u,0))
"""


@pytest.fixture(scope="module")
def _dsn():
    P.potreban_pg()
    dsn = P.nova_baza()
    yield dsn
    P.obrisi_bazu(dsn)


@pytest.fixture
def _pg(_dsn):
    with _psy().connect(_dsn, autocommit=True) as c:
        c.execute("TRUNCATE public.outcome_log, public.case_patterns, public.predmeti")
        c.execute("DROP TRIGGER IF EXISTS pukni ON public.case_patterns")
    yield


def _psy():
    import psycopg
    return psycopg


@pytest.fixture
def db(_dsn):
    return _dsn


def _predmet(dsn, uid=A, tip="radni"):
    pid = str(uuid.uuid4())
    with _psy().connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.predmeti (id, user_id, tip, naziv) VALUES (%s, %s, %s, 'x')", (pid, uid, tip))
    return pid


def _ishod(dsn, pid, ishod, faktori, uid=A, conn=None):
    sql = ("SELECT public.zabelezi_ishod_predmeta(%s::uuid, %s::uuid, %s, %s::text[], NULL, NULL, '', '{}'::text[], '')")
    if conn is not None:
        return conn.execute(sql, (uid, pid, ishod, faktori)).fetchone()[0]
    with _psy().connect(dsn) as c:
        with c.transaction():
            c.execute("SET LOCAL ROLE service_role")
            c.execute("SET LOCAL lock_timeout = '20s'")       # zaglavljen test = pad, ne beskonačno čekanje
            return c.execute(sql, (uid, pid, ishod, faktori)).fetchone()[0]


def _zbir(dsn, tip, uid=A):
    with _psy().connect(dsn) as c:
        return {f: (p, po, u) for f, p, po, u in c.execute(
            "SELECT faktor, pobede, porazi, ukupno FROM public.case_patterns WHERE user_id=%s AND tip_spora=%s "
            "AND ukupno > 0", (uid, tip))}


def _odstupanja(dsn):
    with _psy().connect(dsn) as c:
        return c.execute(_PROROCISTE).fetchone()[0]


# ─── semantika ──────────────────────────────────────────────────────────────────────────────────────────────

def test_pobeda_ispravka_u_poraz_i_ponovljeno_slanje(db):
    p = _predmet(db)
    _ishod(db, p, "pobeda", ["svedoci", "vestacenje"])
    assert _zbir(db, "radni") == {"svedoci": (1, 0, 1), "vestacenje": (1, 0, 1)}
    _ishod(db, p, "poraz", ["svedoci"])
    assert _zbir(db, "radni") == {"svedoci": (0, 1, 1)}, "ispravka je zadržala staru pobedu ili stari faktor"
    for _ in range(3):
        _ishod(db, p, "poraz", ["svedoci"])
    assert _zbir(db, "radni") == {"svedoci": (0, 1, 1)}, "ponovljen zahtev je uvećao zbir"
    assert _odstupanja(db) == 0


def test_promena_vrste_spora_premesta_doprinos_u_istoj_transakciji(db):
    p = _predmet(db, tip="radni")
    _ishod(db, p, "pobeda", ["svedoci"])
    with _psy().connect(db, autocommit=True) as c:
        c.execute("UPDATE public.predmeti SET tip='porodicni' WHERE id=%s", (p,))
    rez = _ishod(db, p, "pobeda", ["svedoci"])
    assert rez["prethodna_vrsta"] == "radni" and rez["tip_spora"] == "porodicni"
    assert _zbir(db, "radni") == {} and _zbir(db, "porodicni") == {"svedoci": (1, 0, 1)}
    assert _odstupanja(db) == 0


def test_faktori_dedup_prvih_deset_nula_faktora_nagodba(db):
    p1, p2, p3 = _predmet(db), _predmet(db), _predmet(db)
    _ishod(db, p1, "pobeda", ["a", "a", "b"])                        # ponovljen faktor u jednom ishodu = 1
    _ishod(db, p2, "nagodba", [f"f{i}" for i in range(12)])         # samo prvih 10
    rez = _ishod(db, p3, "poraz", [])                                # bez faktora
    assert rez["faktora"] == 0
    z = _zbir(db, "radni")
    assert z["a"] == (1, 0, 1) and "f10" not in z and "f11" not in z and z["f9"] == (0, 0, 1)
    assert _odstupanja(db) == 0


def test_tudj_predmet_odbijen_i_nista_nije_upisano(db):
    p = _predmet(db, uid=A)
    with pytest.raises(Exception) as e:
        _ishod(db, p, "pobeda", ["svedoci"], uid=B)
    assert "P0002" in str(getattr(e.value, "sqlstate", "")) or "nije pronađen" in str(e.value)
    with _psy().connect(db) as c:
        assert c.execute("SELECT count(*) FROM public.outcome_log").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM public.case_patterns").fetchone()[0] == 0


def test_ishod_drugog_korisnika_se_ne_prepisuje(db):
    p = _predmet(db, uid=A)
    _ishod(db, p, "pobeda", ["svedoci"], uid=A)
    with _psy().connect(db, autocommit=True) as c:          # predmet „prebačen" B-u, ishod ostao A-ov
        c.execute("UPDATE public.predmeti SET user_id=%s WHERE id=%s", (B, p))
    with pytest.raises(Exception) as e:
        _ishod(db, p, "poraz", ["svedoci"], uid=B)
    assert getattr(e.value, "sqlstate", "") == "42501"
    assert _zbir(db, "radni", uid=A) == {"svedoci": (1, 0, 1)} and _zbir(db, "radni", uid=B) == {}


# ─── atomičnost ─────────────────────────────────────────────────────────────────────────────────────────────

def test_izuzetak_usred_preracuna_vraca_i_ishod(db):
    p = _predmet(db)
    _ishod(db, p, "pobeda", ["svedoci"])
    with _psy().connect(db, autocommit=True) as c:
        c.execute("""CREATE OR REPLACE FUNCTION public._pukni() RETURNS trigger LANGUAGE plpgsql AS
                     $$ BEGIN IF NEW.faktor = 'PUKNI' THEN RAISE EXCEPTION 'simuliran pad'; END IF; RETURN NEW; END $$""")
        c.execute("CREATE TRIGGER pukni BEFORE INSERT OR UPDATE ON public.case_patterns "
                  "FOR EACH ROW EXECUTE FUNCTION public._pukni()")
    with pytest.raises(Exception):
        _ishod(db, p, "poraz", ["svedoci", "PUKNI"])
    with _psy().connect(db) as c:
        assert c.execute("SELECT ishod FROM public.outcome_log WHERE predmet_id=%s", (p,)).fetchone()[0] == "pobeda", \
            "ishod je upisan iako preračun nije — delimičan uspeh"
    assert _zbir(db, "radni") == {"svedoci": (1, 0, 1)} and _odstupanja(db) == 0


def test_prekid_procesa_pre_commit_ne_ostavlja_nista(db):
    p = _predmet(db)
    c = _psy().connect(db)
    c.execute("SET ROLE service_role")
    _ishod(db, p, "pobeda", ["svedoci"], conn=c)       # u otvorenoj transakciji
    c.close()                                           # „pad procesa" — bez commit-a
    with _psy().connect(db) as k:
        assert k.execute("SELECT count(*) FROM public.outcome_log").fetchone()[0] == 0
    assert _zbir(db, "radni") == {} and _odstupanja(db) == 0


# ─── konkurentnost ──────────────────────────────────────────────────────────────────────────────────────────

def test_g1_drugi_pisac_ceka_i_vidi_prvi_upis(db):
    """G1: dva RAZLIČITA ishoda istog korisnika istovremeno. Ranije je zastareo preračun prepisivao (1,1,2)."""
    p1, p2 = _predmet(db), _predmet(db)
    t1 = _psy().connect(db)
    t1.execute("SET ROLE service_role")
    _ishod(db, p1, "pobeda", ["svedoci"], conn=t1)       # drži bravu korisnika, nije commit-ovan
    gotovo = {}

    def drugi():
        try:
            gotovo["rez"] = _ishod(db, p2, "poraz", ["svedoci"])
        except Exception as e:
            gotovo["greska"] = repr(e)
    nit = threading.Thread(target=drugi, daemon=True)
    nit.start()
    try:
        time.sleep(0.6)
        with _psy().connect(db) as k:
            ceka = k.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted").fetchone()[0]
        assert ceka == 1 and "rez" not in gotovo, "drugi pisac nije čekao bravu korisnika"
        t1.commit()
    finally:
        t1.close()                                       # bez commit-a = rollback; drugi pisac nikad ne visi
    nit.join(30)
    assert "rez" in gotovo
    assert _zbir(db, "radni") == {"svedoci": (1, 1, 2)} and _odstupanja(db) == 0


def test_mnogo_istovremenih_pisaca_ispravki_i_promena_vrste(db):
    predmeti = [_predmet(db, tip=("radni" if i % 2 else "porodicni")) for i in range(12)]
    greske = []

    def radnik(i):
        try:
            for k in range(6):
                p = predmeti[(i + k) % len(predmeti)]
                if k == 3:
                    with _psy().connect(db, autocommit=True) as c:
                        c.execute("UPDATE public.predmeti SET tip = CASE WHEN tip='radni' THEN 'porodicni' "
                                  "ELSE 'radni' END WHERE id=%s", (p,))
                _ishod(db, p, ("pobeda", "poraz", "nagodba")[(i + k) % 3], [f"f{(i + k) % 5}", f"f{k % 3}"])
        except Exception as e:                           # deadlock ili bilo koja greška = pad testa
            greske.append(repr(e))
    niti = [threading.Thread(target=radnik, args=(i,)) for i in range(8)]
    for n in niti:
        n.start()
    for n in niti:
        n.join(60)
    assert greske == []
    assert _odstupanja(db) == 0, "zbir se razilazi od zabeleženih ishoda posle konkurentnih upisa"


def test_dve_vrste_spora_unakrsno_bez_zastoja(db):
    """Dva zahteva menjaju vrstu spora u suprotnim smerovima (radni↔porodicni) — obe vrste u istoj transakciji."""
    p1, p2 = _predmet(db, tip="radni"), _predmet(db, tip="porodicni")
    _ishod(db, p1, "pobeda", ["x"])
    _ishod(db, p2, "poraz", ["x"])
    with _psy().connect(db, autocommit=True) as c:
        c.execute("UPDATE public.predmeti SET tip='porodicni' WHERE id=%s", (p1,))
        c.execute("UPDATE public.predmeti SET tip='radni' WHERE id=%s", (p2,))
    greske = []

    def posalji(p, i):
        try:
            _ishod(db, p, i, ["x"])
        except Exception as e:
            greske.append(repr(e))
    niti = [threading.Thread(target=posalji, args=a) for a in ((p1, "pobeda"), (p2, "poraz"))]
    for n in niti:
        n.start()
    for n in niti:
        n.join(20)
    assert greske == []
    assert _zbir(db, "radni") == {"x": (0, 1, 1)} and _zbir(db, "porodicni") == {"x": (1, 0, 1)}
    assert _odstupanja(db) == 0


# ─── G2: veličina ───────────────────────────────────────────────────────────────────────────────────────────

def _masovno(db, broj_predmeta, faktora_po, zastareli_redovi):
    with _psy().connect(db, autocommit=True) as c:
        ids = [str(uuid.uuid4()) for _ in range(broj_predmeta)]
        with c.cursor() as cur:
            cur.executemany("INSERT INTO public.predmeti (id, user_id, tip, naziv) VALUES (%s,%s,'radni','x')",
                            [(i, A) for i in ids])
            cur.executemany("INSERT INTO public.outcome_log (predmet_id, user_id, ishod, presudni_faktori, tip_spora) "
                            "VALUES (%s,%s,'pobeda',%s,'radni')",
                            [(i, A, [f"g{n * faktora_po + j:05d}" for j in range(faktora_po)]) for n, i in enumerate(ids)])
            cur.executemany("INSERT INTO public.case_patterns (user_id, tip_spora, faktor, pobede, porazi, ukupno) "
                            "VALUES (%s,'radni',%s,9,9,18)", [(A, f"g{n:05d}") for n in range(zastareli_redovi)])
    return ids


@pytest.mark.parametrize("broj_predmeta,zastarelih", [(100, 1000), (130, 1300)])
def test_g2_tacno_i_vise_od_hiljadu_faktora_bez_skracivanja(db, broj_predmeta, zastarelih):
    """100×10 = tačno 1000 faktora (granica PostgREST max-rows) i 130×10 = 1300; svi postojeći redovi zastareli."""
    ids = _masovno(db, broj_predmeta, 10, zastarelih)
    _ishod(db, ids[0], "poraz", [f"g{j:05d}" for j in range(10)])
    z = _zbir(db, "radni")
    assert len(z) == broj_predmeta * 10
    assert all(v == ((0, 1, 1) if k < "g00010" else (1, 0, 1)) for k, v in z.items())
    assert _odstupanja(db) == 0


# ─── dozvole ────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("uloga", ["anon", "authenticated"])
def test_korisnik_ne_izvrsava_funkciju_i_ne_pise_tabele(db, uloga):
    p = _predmet(db)
    for sql, args in [
        ("SELECT public.zabelezi_ishod_predmeta(%s::uuid, %s::uuid, 'pobeda', '{x}', NULL, NULL, '', '{}', '')", (A, p)),
        ("INSERT INTO public.outcome_log (predmet_id, user_id, ishod, tip_spora) VALUES (%s, %s, 'pobeda', 'radni')", (p, A)),
        ("INSERT INTO public.case_patterns (user_id, tip_spora, faktor, pobede) VALUES (%s, 'radni', 'x', 99)", (A,)),
    ]:
        with _psy().connect(db) as c:
            with pytest.raises(Exception) as e:
                with c.transaction():
                    P.kao(c, uloga, A)
                    c.execute(sql, args)
            assert getattr(e.value, "sqlstate", "") == "42501", (uloga, sql, e.value)


def test_vlasnik_i_dalje_cita_svoj_zbir_tudji_ne(db):
    p = _predmet(db)
    _ishod(db, p, "pobeda", ["svedoci"])
    with _psy().connect(db) as c:
        with c.transaction():
            P.kao(c, "authenticated", A)
            assert c.execute("SELECT count(*) FROM public.case_patterns").fetchone()[0] == 1
        with c.transaction():
            P.kao(c, "authenticated", B)
            assert c.execute("SELECT count(*) FROM public.case_patterns").fetchone()[0] == 0


def test_migracija_139_ponovljiva(db):
    P.primeni(db, "139_ns4_atomski_ishod_predmeta.sql")
    p = _predmet(db)
    _ishod(db, p, "pobeda", ["svedoci"])
    assert _zbir(db, "radni") == {"svedoci": (1, 0, 1)}


@pytest.mark.parametrize("uloga,ocekivano", [("anon", False), ("authenticated", False), ("service_role", True)])
def test_pravo_izvrsavanja_funkcije_direktno(db, uloga, ocekivano):
    """Nezavisno od drugog sloja (oduzet upis u tabele): samo backend sme da IZVRŠI funkciju."""
    with _psy().connect(db) as c:
        assert c.execute("SELECT has_function_privilege(%s, 'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],"
                         "integer,numeric,text,text[],text)', 'EXECUTE')", (uloga,)).fetchone()[0] is ocekivano
