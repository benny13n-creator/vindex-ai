# -*- coding: utf-8 -*-
"""BA05 — migracija 144 i oba pisca kandidata roka nad PRAVIM PostgreSQL-om (privremen klaster iz
tests/test_ocr001_trka_postgres.py; nikad produkcija, samo sintetički podaci).

`predmet_hronologija` se gradi kao u produkciji: osnovne kolone + DOSLOVNE migracije 126, 127, 129, pa 144.
Pisci (`routers/case_dna._sync_rokovi_to_hronologija`, `routers/smart_intake._rok_iz_dokumenta`) idu kroz tanak
adapter Supabase lanca (`select/eq/in_/limit/insert`) nad psycopg — isti SQL ishodi koje vraća PostgREST (23505,
42703), bez lažne jedinstvenosti. Zaključavanje u procesu je namerno ISKLJUČENO u testovima trke: jedinstvenost
mora da drži baza (dva procesa).

Dokazuje: (1) 144 samo dodaje — zatečeni redovi bajt-po-bajt isti, ponovljiva, vraćanje radi; (2) isti ključ u
istom predmetu pada 23505, a različite obaveze, drugi predmet i NULL (zatečeni redovi) ne; CHECK oblika ključa;
(3) dva istovremena Genome osvežavanja i dva istovremena upisa Smart Intake-a za istu obavezu → jedan red;
(4) A/B1/B2 nad pravom bazom; (5) bez 144: rokovi se upisuju bez ključa, bez potiskivanja.
"""
import asyncio
import threading
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.rows import dict_row  # noqa: E402

import routers.case_dna as cd  # noqa: E402
import routers.smart_intake as si  # noqa: E402
import shared.rokovi as R  # noqa: E402
from tests import ns4f_pg  # noqa: E402
from tests.test_ocr001_trka_postgres import pg  # noqa: E402,F401  (privremen klaster)

KOREN = Path(__file__).resolve().parent.parent
M = {n: (KOREN / f"migrations/{n}").read_text(encoding="utf-8") for n in (
    "126_hronologija_dokument_id.sql", "127_hronologija_izvor_provenance.sql", "129_hronologija_vrsta_stanje.sql",
    "144_hronologija_obaveza_kljuc.sql")}
M144 = M["144_hronologija_obaveza_kljuc.sql"]
U = "00000000-0000-0000-0000-00000000000a"
DATUM = "2026-11-05"
TEKST_A = "RESENJE\nRok za izjavljivanje zalbe istice 05.11.2026. godine."
TEKST_B = "RESENJE\nRok za uplatu sudske takse istice 05.11.2026. godine."
TEKST_2 = "Rok za izjavljivanje zalbe istice 05.11.2026. godine.\nRok za uplatu sudske takse istice 05.11.2026. godine."


def _odustajanje():
    deo = M144.split("-- [ODUSTAJANJE]", 1)[1].split("\n", 1)[1]
    return "\n".join(l[3:] for l in deo.splitlines() if l.startswith("-- "))


@pytest.fixture
def klaster(request):
    """CI (posao produkcione slike, root): izolovan test klaster `VINDEX_PG_TEST_DSN` (scripts/test_db.py) — sveža
    baza po testu, obrisana posle. Lokalno: privremen klaster (`initdb`) iz tests/test_ocr001_trka_postgres.py."""
    admin = ns4f_pg.dsn_admin()
    if not admin:
        yield request.getfixturevalue("pg")
        return
    from urllib.parse import urlparse
    ime = "ba05_" + uuid.uuid4().hex[:12]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{ime}"')
    try:
        yield urlparse(admin)._replace(path="/" + ime).geturl()
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{ime}" WITH (FORCE)')


@pytest.fixture
def baza(klaster):
    pg = klaster
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        c.execute("""
            CREATE TABLE public.predmet_dokumenti (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL, user_id uuid,
                naziv_fajla text, tekst_sadrzaj text, content_sha256 text, source_intake_job_id uuid);
            CREATE TABLE public.predmet_hronologija (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL, user_id uuid,
                dogadjaj text, datum text, datum_iso date, vaznost text, akter text, dokument_naziv text,
                created_at timestamptz NOT NULL DEFAULT now());
            -- zatečeni redovi (pre 126/127/129/144)
            INSERT INTO public.predmet_hronologija (predmet_id, user_id, dogadjaj, datum, datum_iso, vaznost, akter, dokument_naziv)
            VALUES ('11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-00000000000a', 'Stari rok', '2026-11-05',
                    '2026-11-05', 'važan', 'Smart Intake', 'scan.pdf'),
                   ('11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-00000000000a', 'Stari rok', '2026-11-05',
                    '2026-11-05', 'važan', 'Smart Intake', 'scan.pdf');
        """)
        for n in ("126_hronologija_dokument_id.sql", "127_hronologija_izvor_provenance.sql", "129_hronologija_vrsta_stanje.sql"):
            c.execute(M[n])
    R._resetuj_sondu()
    yield pg
    R._resetuj_sondu()


class _Rez:
    def __init__(self, data):
        self.data = data


class _Upit:
    def __init__(self, sp, t):
        self.sp, self.t, self.kol, self.uslovi, self.n, self.red = sp, t, "*", [], None, None

    def select(self, kol="*", **_):
        self.kol = kol
        return self

    def eq(self, k, v):
        self.uslovi.append((f"{k} = %s", v))
        return self

    def in_(self, k, v):
        self.uslovi.append((f"{k}::text = ANY(%s)", [str(x) for x in v]))
        return self

    def limit(self, n):
        self.n = n
        return self

    def insert(self, red):
        self.red = red
        return self

    def execute(self):
        with psycopg.connect(self.sp.dsn, autocommit=True, row_factory=dict_row) as c:
            if self.red is not None:
                self.sp.pre_upisa(self.t, self.red)
                kol = list(self.red)
                rows = c.execute(f"INSERT INTO public.{self.t} ({', '.join(kol)}) VALUES ({', '.join(['%s'] * len(kol))}) "
                                 "RETURNING *", [self.red[k] for k in kol]).fetchall()
            else:
                gde = " AND ".join(u for u, _ in self.uslovi) or "true"
                sql = f"SELECT {self.kol} FROM public.{self.t} WHERE {gde}" + (f" LIMIT {self.n}" if self.n else "")
                rows = c.execute(sql, [v for _, v in self.uslovi]).fetchall()
        # PostgREST vraća JSON: uuid/datum kao tekst
        return _Rez([{k: (v if v is None or isinstance(v, (bool, int, str)) else str(v)) for k, v in r.items()} for r in rows])


class Supa:
    """Tanak Supabase lanac nad psycopg (samo ono što dva pisca koriste)."""
    def __init__(self, dsn):
        self.dsn = dsn

    def table(self, t):
        return _Upit(self, t)

    def pre_upisa(self, tabela, red):
        pass


class _NulaZakljucavanje:
    """Dva PROCESA: zaključavanje u procesu ne postoji između njih — jedinstvenost mora da drži baza."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _dokument(dsn, pid, naziv, tekst):
    from shared.vector_identity import verzija_dokumenta
    with psycopg.connect(dsn, autocommit=True) as c:
        return str(c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, user_id, naziv_fajla, tekst_sadrzaj, content_sha256) "
                             "VALUES (%s, %s, %s, %s, %s) RETURNING id", (pid, U, naziv, tekst, verzija_dokumenta(tekst))).fetchone()[0])


def _redovi(dsn, pid):
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as c:
        return c.execute("SELECT id::text, dogadjaj, datum_iso::text, akter, dokument_id::text, obaveza_kljuc "
                         "FROM public.predmet_hronologija WHERE predmet_id = %s ORDER BY created_at, id", (pid,)).fetchall()


def _rok(naziv, did, opis="x"):
    return {"naziv": naziv, "datum": DATUM, "opis": opis, "status": "aktivan", "dokument_id": did}


def _genome(sp, pid, *rokovi):
    return asyncio.run(cd._sync_rokovi_to_hronologija(sp, pid, U, {"rokovi_kriticni": list(rokovi)}))


# ── (1)(2) šema ───────────────────────────────────────────────────────────────────────────────────────────────

def test_144_samo_dodaje_ponovljiva_i_vracanje(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        pre = c.execute("SELECT * FROM public.predmet_hronologija ORDER BY id").fetchall()
        c.execute(M144)
        c.execute(M144)
        posle = c.execute("SELECT * FROM public.predmet_hronologija ORDER BY id").fetchall()
        assert [r + (None,) for r in pre] == posle and len(pre) == 2          # isti redovi + NULL ključ
        assert c.execute("SELECT indexdef FROM pg_indexes WHERE indexname='uq_hronologija_obaveza_kljuc'").fetchone()[0] \
            .endswith("(predmet_id, obaveza_kljuc) WHERE (obaveza_kljuc IS NOT NULL)")
        c.execute(_odustajanje())
        assert c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='predmet_hronologija' "
                         "AND column_name='obaveza_kljuc'").fetchone()[0] == 0
        assert c.execute("SELECT * FROM public.predmet_hronologija ORDER BY id").fetchall() == pre
        c.execute(M144)


def test_144_jedinstvenost_po_predmetu_null_i_oblik(baza):
    p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
    k1, k2 = R.kljuc_obaveze("h", DATUM, "a"), R.kljuc_obaveze("h", DATUM, "b")
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
        ins = ("INSERT INTO public.predmet_hronologija (predmet_id, dogadjaj, datum_iso, izvor, obaveza_kljuc) "
               "VALUES (%s, 'r', %s, 'AI_AUTONOMOUS', %s)")
        for pid, k in ((p1, k1), (p1, k2), (p2, k1), (p1, None), (p1, None)):
            c.execute(ins, (pid, DATUM, k))
        with pytest.raises(psycopg.errors.UniqueViolation) as e:
            c.execute(ins, (p1, DATUM, k1))
        assert R.je_sukob_kljuca(e.value)
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(ins, (p1, DATUM, "Rok za zalbu"))                       # naslov/tekst nikad nije ključ


# ── (3) dva procesa, ista obaveza ─────────────────────────────────────────────────────────────────────────────

def _istovremeno(sp, fn_a, fn_b):
    """Oba pisca pročitaju stanje, pa tek onda upisuju (barijera pred INSERT-om) — najgori redosled trke."""
    bar = threading.Barrier(2, timeout=20)
    sp.pre_upisa = lambda t, red: bar.wait() if t == "predmet_hronologija" else None
    out, greske = [None, None], []

    def radi(i, fn):
        try:
            out[i] = fn()
        except BaseException as exc:          # noqa: BLE001
            greske.append(exc)
    ts = [threading.Thread(target=radi, args=(0, fn_a)), threading.Thread(target=radi, args=(1, fn_b))]
    [t.start() for t in ts]
    [t.join(30) for t in ts]
    sp.pre_upisa = lambda t, red: None
    assert not greske, greske
    return out


def test_dva_genome_osvezavanja_istovremeno_jedna_obaveza(baza, monkeypatch):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    monkeypatch.setattr(R, "zakljucavanje_kandidata", lambda pid: _NulaZakljucavanje())
    sp, pid = Supa(baza), str(uuid.uuid4())
    did = _dokument(baza, pid, "scan.pdf", TEKST_A)
    out = _istovremeno(sp, lambda: _genome(sp, pid, _rok("Rok za zalbu", did, "a")),
                       lambda: _genome(sp, pid, _rok("Žalbeni rok", did, "b")))
    assert sorted(out) == [0, 1]
    [r] = _redovi(baza, pid)
    assert r["dokument_id"] == did and r["obaveza_kljuc"]


def test_dva_smart_intake_upisa_istovremeno_jedna_obaveza(baza, monkeypatch):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    sp, pid = Supa(baza), str(uuid.uuid4())
    kljuc = R.kljuc_obaveze("hes-sadrzaja", DATUM, "rok za izjavljivanje zalbe istice")

    def upis():
        return asyncio.run(si._rok_iz_dokumenta(
            sp, predmet_id=pid, uid=U, job={"original_filename": "scan.pdf"}, job_id="j", value_map={"deadline": "05.11.2026"},
            meta_map={"deadline": {"confidence": 0.95, "potvrdio_covek": False}}, tip_labela="rešenje", vec_upisano=set(),
            kljuc=kljuc))
    out = _istovremeno(sp, upis, upis)
    assert sorted(x["dodat"] for x in out) == [False, True] and {x["razlog"] for x in out} == {None, "vec_postoji"}
    [r] = _redovi(baza, pid)
    assert r["obaveza_kljuc"] == kljuc and r["akter"] == "Smart Intake"


# ── (4) A / B1 / B2 nad pravom bazom ──────────────────────────────────────────────────────────────────────────

def test_A_B1_B2_nad_pravom_bazom(baza):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    sp = Supa(baza)
    # A: dva dokumenta istog imena i datuma (Genome-only putanja; SI putanja: tests/test_ba05_identitet_obaveze.py)
    pa = str(uuid.uuid4())
    d1, d2 = _dokument(baza, pa, "scan.pdf", TEKST_A), _dokument(baza, pa, "scan.pdf", TEKST_B)
    _genome(sp, pa, _rok("Rok za zalbu", d1), _rok("Rok za taksu", d2))
    assert sorted(r["dokument_id"] for r in _redovi(baza, pa)) == sorted([d1, d2])
    # B1: dve parafraze A, dokument dokazuje A i B istog dana
    pb = str(uuid.uuid4())
    d = _dokument(baza, pb, "sken.pdf", TEKST_2)
    _genome(sp, pb, _rok("Rok za zalbu", d, "a"), _rok("Zalbeni rok", d, "b"))
    r = _redovi(baza, pb)
    assert len(r) == 2 and len({x["obaveza_kljuc"] for x in r}) == 2
    assert sum("zalbe" in x["dogadjaj"] for x in r) == 1 and sum("takse" in x["dogadjaj"] for x in r) == 1
    # B2: A pa B u sledećem osvežavanju
    pc = str(uuid.uuid4())
    d = _dokument(baza, pc, "sken.pdf", TEKST_2)
    _genome(sp, pc, _rok("Rok za zalbu", d))
    _genome(sp, pc, _rok("Rok za takse", d))
    _genome(sp, pc, _rok("Žalba ponovo", d))
    assert len(_redovi(baza, pc)) == 2


TEKST_SUBJ_PRE = ("RESENJE\nZa tužioca rok za uplatu sudske takse ističe 05.11.2026.\n"
                  "Za tuženog rok za uplatu sudske takse ističe 05.11.2026.")
TEKST_SUBJ_POSLE = ("RESENJE\nRok za uplatu sudske takse ističe 05.11.2026. za tužioca.\n"
                    "Rok za uplatu sudske takse ističe 05.11.2026. za tuženog.")
TEKST_PONOVLJENO = "RESENJE\nRok za uplatu sudske takse ističe 05.11.2026.\nRok za uplatu sudske takse ističe 05.11.2026."


def test_kolizija_izvora_dva_subjekta_nad_pravom_bazom(baza, monkeypatch):
    """Isti dokument, ista vrsta i datum, različit subjekat (pre ili posle datuma) → dve obaveze, i u trci dva
    osvežavanja bez zaključavanja u procesu; ista obaveza ponovljena u dokumentu → jedna."""
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    monkeypatch.setattr(R, "zakljucavanje_kandidata", lambda pid: _NulaZakljucavanje())
    sp = Supa(baza)
    for tekst, subj in ((TEKST_SUBJ_PRE, ("Za tužioca", "Za tuženog")), (TEKST_SUBJ_POSLE, ("za tužioca", "za tuženog"))):
        pid = str(uuid.uuid4())
        d = _dokument(baza, pid, "resenje.pdf", tekst)
        _istovremeno(sp, lambda: _genome(sp, pid, _rok("Uplata takse", d, "a")),
                     lambda: _genome(sp, pid, _rok("Sudska taksa", d, "b")))
        _genome(sp, pid, _rok("Taksa ponovo", d))
        r = _redovi(baza, pid)
        assert len(r) == 2 and len({x["obaveza_kljuc"] for x in r}) == 2 and None not in {x["obaveza_kljuc"] for x in r}, r
        assert all(sum(s in x["dogadjaj"] for x in r) == 1 for s in subj), [x["dogadjaj"] for x in r]
    pid = str(uuid.uuid4())
    d = _dokument(baza, pid, "resenje.pdf", TEKST_PONOVLJENO)
    _genome(sp, pid, _rok("Uplata takse", d, "a"), _rok("Sudska taksa", d, "b"))
    assert len(_redovi(baza, pid)) == 1


TEKST_TROSKOVI = "RESENJE\nRok za zalbu na troskove istice 05.11.2026. godine."
TEKST_TAKSA = "RESENJE\nRok za uplatu dodatne sudske takse istice 05.11.2026. godine."


def _uskladi(sp, pid, *ids):
    return asyncio.run(R.uskladi_rokove_iz_izvora(sp, pid, U, dokument_ids=list(ids)))


def test_rokovi_iz_izvora_nad_pravom_bazom_trka_dva_procesa(baza, monkeypatch):
    """P7714: dva `scan.pdf`, isti datum; Genome navodi samo A. Dva procesa istovremeno usklađuju izvor (bez
    zaključavanja u procesu, barijera pred INSERT-om) → B tačno jednom; ponovljeno usklađivanje ništa ne dodaje."""
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    monkeypatch.setattr(R, "zakljucavanje_kandidata", lambda pid: _NulaZakljucavanje())
    sp, pid = Supa(baza), str(uuid.uuid4())
    da, db = _dokument(baza, pid, "scan.pdf", TEKST_TROSKOVI), _dokument(baza, pid, "scan.pdf", TEKST_TAKSA)
    assert _genome(sp, pid, _rok("Rok za žalbu na troškove", da)) == 1
    out = _istovremeno(sp, lambda: _uskladi(sp, pid, da, db), lambda: _uskladi(sp, pid, da, db))
    assert sorted(len(o["kreirano"]) for o in out) == [0, 1], out
    r = _redovi(baza, pid)
    assert sorted(x["dokument_id"] for x in r) == sorted([da, db]) and len({x["obaveza_kljuc"] for x in r}) == 2
    assert all(x["obaveza_kljuc"] for x in r)
    ishod = _uskladi(sp, pid, da, db)
    assert ishod["kreirano"] == [] and len(ishod["postoji"]) == 2 and len(_redovi(baza, pid)) == 2
    assert _genome(sp, pid) == 0 and len(_redovi(baza, pid)) == 2                # Genome bez rokova ništa ne briše


def test_rokovi_iz_izvora_i_genome_istovremeno_ista_obaveza_jedan_red(baza, monkeypatch):
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(M144)
    monkeypatch.setattr(R, "zakljucavanje_kandidata", lambda pid: _NulaZakljucavanje())
    sp, pid = Supa(baza), str(uuid.uuid4())
    d = _dokument(baza, pid, "scan.pdf", TEKST_TAKSA)
    _istovremeno(sp, lambda: _uskladi(sp, pid, d), lambda: _genome(sp, pid, _rok("Dodatna taksa", d)))
    [r] = _redovi(baza, pid)
    assert r["dokument_id"] == d and r["obaveza_kljuc"]


# ── (5) kod pre migracije ─────────────────────────────────────────────────────────────────────────────────────

def test_bez_144_upis_bez_kljuca_i_bez_potiskivanja(baza):
    sp, pid = Supa(baza), str(uuid.uuid4())
    d = _dokument(baza, pid, "sken.pdf", TEKST_2)
    assert _genome(sp, pid, _rok("Rok za zalbu", d)) == 2                     # obe dokazane obaveze, sa citatom
    assert _genome(sp, pid, _rok("Rok za takse", d)) == 0                     # citat iz izvora se ne ponavlja
    assert _genome(sp, pid, _rok("Žalbeni rok", d)) == 0                      # parafraza ne pravi nov red
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM public.predmet_hronologija WHERE predmet_id = %s", (pid,)).fetchone()[0] == 2
