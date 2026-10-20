# -*- coding: utf-8 -*-
"""OCR001 — trka dva finalize procesa nad PRAVIM PostgreSQL-om (privremen klaster, nikad produkcija).

Dokazuje na stvarnom DDL-u (doslovno iz migracija 094, 095, 106 i predloga 138) ono na šta se oslanja
tests/test_ocr001_konkurentna_finalizacija.py:
  1. `claim_intake_finalize` (095) daje zauzeće drugom procesu kad je prvo starije od 120 s, a prvi proces to ne zna;
  2. SELECT-pa-INSERT dva procesa upisuje isti dokument dvaput — postojeći indeksi to ne sprečavaju za NULL segment,
     a (predmet_id, redni_broj) samo pomera drugi red na sledeći broj;
  3. indeks segmenta (094) se zaobilazi upisom bez kolone segmenta (stara „uža varijanta“);
  4. predlog 138 odbija drugi red atomski, i kad su dve transakcije istovremene;
  5. oblik greške 23505 je isti kao u emulaciji (ime indeksa u poruci).

Preskače se ako nema PostgreSQL binarnih fajlova (initdb/pg_ctl) ili paketa psycopg.
"""
import glob
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

KOREN = Path(__file__).resolve().parent.parent


def _bin():
    kandidati = [os.environ.get("VINDEX_PG_BIN", "")]
    kandidati += sorted(glob.glob("C:/Program Files/PostgreSQL/*/bin"), reverse=True)
    kandidati += sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)
    for d in kandidati:
        if d and (Path(d) / ("initdb.exe" if os.name == "nt" else "initdb")).exists():
            return Path(d)
    return None


def _slobodan_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _naredba(fajl, obrazac):
    tekst = (KOREN / fajl).read_text(encoding="utf-8")
    m = re.search(obrazac, tekst, re.S)
    assert m, (fajl, obrazac)
    return m.group(0)


def _predlog(oznaka):
    """Naredba iz predloga 138 između `-- [OZNAKA]` i sledeće oznake (komentari se odbacuju)."""
    tekst = (KOREN / "docs/v2-execution/OCR001_PREDLOG_MIGRACIJE_138.sql").read_text(encoding="utf-8")
    deo = tekst.split(f"-- [{oznaka}]", 1)[1].split("\n", 1)[1].split("-- [", 1)[0]   # bez ostatka linije oznake
    return "\n".join(l for l in deo.splitlines() if not l.lstrip().startswith("--")).strip()


def _rollback():
    tekst = (KOREN / "docs/v2-execution/OCR001_PREDLOG_MIGRACIJE_138.sql").read_text(encoding="utf-8")
    return re.search(r"DROP INDEX IF EXISTS public\.uq_predmet_dokumenti_posao_sadrzaj;",
                     tekst.split("-- [ROLLBACK]", 1)[1]).group(0)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    b = _bin()
    if b is None:
        pytest.skip("PostgreSQL binarni fajlovi nisu dostupni")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        # initdb odbija root (posao prod-runtime radi u kontejneru kao root); dokaz se izvršava u Test Suite 3.11/3.13.
        pytest.skip("initdb ne radi kao root — dokaz trke se izvršava u poslu bez root-a")
    d = tmp_path_factory.mktemp("pgtrka") / "data"
    port = _slobodan_port()
    subprocess.run([str(b / "initdb"), "-D", str(d), "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
                   check=True, capture_output=True)
    subprocess.run([str(b / "pg_ctl"), "-D", str(d), "-o", f"-p {port} -c listen_addresses=127.0.0.1",
                    "-l", str(d.parent / "log.txt"), "-w", "start"], check=True, timeout=60,
                   # Server nasleđuje deskriptore pg_ctl-a: sa cevima bi run() čekao zauvek (Windows).
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dsn = f"host=127.0.0.1 port={port} user=postgres dbname=postgres"
    try:
        yield dsn
    finally:
        subprocess.run([str(b / "pg_ctl"), "-D", str(d), "-m", "immediate", "-w", "stop"], timeout=60,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def baza(pg):
    """Svež skup tabela po testu: minimalne kolone + DOSLOVNI indeksi/funkcija iz migracija."""
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        c.execute("""
            CREATE TABLE public.intake_jobs (
                id uuid PRIMARY KEY, predmet_id uuid, finalizing_at timestamptz,
                assimilation_complete boolean NOT NULL DEFAULT false);
            CREATE TABLE public.intake_job_segments (id uuid PRIMARY KEY);
            CREATE TABLE public.predmet_dokumenti (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid, user_id uuid, redni_broj int,
                content_sha256 text, source_intake_job_id uuid REFERENCES public.intake_jobs(id),
                source_intake_job_segment_id uuid REFERENCES public.intake_job_segments(id));
        """)
        c.execute(_naredba("migrations/094_case_assimilation.sql",
                           r"CREATE UNIQUE INDEX IF NOT EXISTS uq_predmet_dokumenti_source_segment.*?;"))
        c.execute(_naredba("migrations/106_phoenix_predmet_dokumenti_redni_broj_unique.sql",
                           r"CREATE UNIQUE INDEX IF NOT EXISTS predmet_dokumenti_predmet_redni_unique.*?;"))
        c.execute(_naredba("migrations/095_intake_bulletproofing.sql",
                           r"CREATE OR REPLACE FUNCTION public\.claim_intake_finalize.*?\$\$;"))
    return pg


def _posao(dsn):
    jid, pid, uid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.intake_jobs (id) VALUES (%s)", (jid,))
    return jid, pid, uid


def _upisi(c, pid, uid, jid, redni, sadrzaj="v1abc", segment=None, sa_identitetom=True):
    if sa_identitetom:
        c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, user_id, redni_broj, content_sha256, "
                  "source_intake_job_id, source_intake_job_segment_id) VALUES (%s,%s,%s,%s,%s,%s)",
                  (pid, uid, redni, sadrzaj, jid, segment))
    else:   # „uža varijanta“ bez 094/095 kolona (stari pad na sledeću varijantu upisa)
        c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, user_id, redni_broj) VALUES (%s,%s,%s)",
                  (pid, uid, redni))


def _postoji(c, uid, sadrzaj="v1abc"):
    return c.execute("SELECT id FROM public.predmet_dokumenti WHERE user_id=%s AND content_sha256=%s",
                     (uid, sadrzaj)).fetchall()


def _redova(dsn, jid=None):
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT count(*) FROM public.predmet_dokumenti").fetchone()[0]


def test_zastarelo_zauzece_preuzima_drugi_proces_dok_prvi_jos_radi(baza):
    jid, _, _ = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as a, psycopg.connect(baza, autocommit=True) as b:
        red_a = a.execute("SELECT finalizing_at FROM public.claim_intake_finalize(%s)", (jid,)).fetchone()
        assert red_a is not None
        assert b.execute("SELECT * FROM public.claim_intake_finalize(%s)", (jid,)).fetchone() is None   # svež: 409
        # Kontrolisano vreme: zauzeće A je staro 121 s (isto kao da je proteklo 121 s).
        token_a = a.execute("UPDATE public.intake_jobs SET finalizing_at = finalizing_at - interval '121 seconds' "
                            "WHERE id=%s RETURNING finalizing_at", (jid,)).fetchone()[0]
        red_b = b.execute("SELECT finalizing_at FROM public.claim_intake_finalize(%s)", (jid,)).fetchone()
        assert red_b is not None and red_b[0] != token_a                     # B je preuzeo; A ne zna
        assert a.execute("UPDATE public.intake_jobs SET predmet_id = gen_random_uuid() WHERE id=%s AND finalizing_at=%s",
                         (jid, token_a)).rowcount == 0                          # samo CAS otkriva gubitak — kasno


def test_bez_138_select_pa_insert_dva_procesa_dva_reda_za_null_segment(baza):
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as a, psycopg.connect(baza, autocommit=True) as b:
        assert _postoji(a, uid) == [] and _postoji(b, uid) == []             # oba proverila: nema reda
        _upisi(a, pid, uid, jid, 1)
        with pytest.raises(psycopg.errors.UniqueViolation) as e:
            _upisi(b, pid, uid, jid, 1)                                      # isti redni broj
        poruka = str(e.value)
        assert 'duplicate key value violates unique constraint "predmet_dokumenti_predmet_redni_unique"' in poruka
        assert "redni" in poruka                                              # kod to prepoznaje i pokušava sledeći
        _upisi(b, pid, uid, jid, 2)                                          # … i upisuje ISTI dokument drugi put
    assert _redova(baza) == 2


def test_indeks_segmenta_094_odbija_ali_uza_varijanta_ga_zaobilazi(baza):
    jid, pid, uid = _posao(baza)
    seg = uuid.uuid4()
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute("INSERT INTO public.intake_job_segments (id) VALUES (%s)", (seg,))
        _upisi(c, pid, uid, jid, 1, segment=seg)
        with pytest.raises(psycopg.errors.UniqueViolation) as e:
            _upisi(c, pid, uid, jid, 2, segment=seg)
        assert 'unique constraint "uq_predmet_dokumenti_source_segment"' in str(e.value)
        assert "redni" not in str(e.value)
        _upisi(c, pid, uid, jid, 2, sa_identitetom=False)                    # stari pad: prolazi bez identiteta
    assert _redova(baza) == 2


def test_predlog_138_odbija_drugi_red_atomski_i_kod_istovremenih_transakcija(baza):
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute(_predlog("PROVERA")).fetchall() == []
        c.execute(_predlog("PRIMENA"))
        potvrda = c.execute(_predlog("POTVRDA")).fetchall()
        assert len(potvrda) == 1 and potvrda[0][1] is True and potvrda[0][2] is True
    ishod = {}
    with psycopg.connect(baza) as a:
        _upisi(a, pid, uid, jid, 1)                                          # A: upisano, NIJE commit-ovano

        def _b():
            try:
                with psycopg.connect(baza, autocommit=True) as b:
                    _upisi(b, pid, uid, jid, 2)                              # drugi redni broj; isti posao + sadržaj
                ishod["b"] = "upisano"
            except psycopg.errors.UniqueViolation as e:
                ishod["b"] = str(e)
        t = threading.Thread(target=_b)
        t.start()
        time.sleep(0.5)
        assert t.is_alive(), "B je morao da čeka A-ovu transakciju na jedinstvenom indeksu"
        a.commit()
        t.join(10)
    assert 'unique constraint "uq_predmet_dokumenti_posao_sadrzaj"' in ishod["b"], ishod
    assert "Key (source_intake_job_id, content_sha256)=" in ishod["b"]
    assert _redova(baza) == 1


def test_predlog_138_ne_dira_rucno_otpremanje_ni_druge_poslove(baza):
    """api.py (ručno otpremanje) svesno dozvoljava isti sadržaj dvaput u istom predmetu: source_intake_job_id NULL."""
    jid, pid, uid = _posao(baza)
    jid2, _, _ = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(_predlog("PRIMENA"))
        for redni in (1, 2):
            c.execute("INSERT INTO public.predmet_dokumenti (predmet_id, user_id, redni_broj, content_sha256) "
                      "VALUES (%s,%s,%s,'v1abc')", (pid, uid, redni))
        _upisi(c, pid, uid, jid, 3)
        _upisi(c, pid, uid, jid2, 4)                                         # drugi posao, isti sadržaj: van opsega
    assert _redova(baza) == 4


def test_provera_iz_predloga_nalazi_postojece_duplikate_i_indeks_tada_ne_nastaje(baza):
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        _upisi(c, pid, uid, jid, 1)
        _upisi(c, pid, uid, jid, 2)                                          # duplikat nastao pre ispravke
        nadjeno = c.execute(_predlog("PROVERA")).fetchall()
        assert len(nadjeno) == 1 and nadjeno[0][2] == 2
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute(_predlog("PRIMENA"))
        assert c.execute(_predlog("POTVRDA")).fetchall() == []


# Prethodna verzija provere (grupisala i po predmet_id) — negativna kontrola za ispravku preflight-a.
STARA_PROVERA = """SELECT source_intake_job_id, content_sha256, predmet_id, count(*) FROM public.predmet_dokumenti
WHERE source_intake_job_id IS NOT NULL AND content_sha256 IS NOT NULL
GROUP BY source_intake_job_id, content_sha256, predmet_id HAVING count(*) > 1"""


def test_provera_koristi_kljuc_indeksa_isti_posao_i_sadrzaj_u_dva_predmeta(baza):
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        _upisi(c, pid, uid, jid, 1)
        _upisi(c, uuid.uuid4(), uid, jid, 1)                                 # isti posao + sadržaj, drugi predmet
        assert c.execute(STARA_PROVERA).fetchall() == []                     # stara provera: „bezbedno“ — pogrešno
        nadjeno = c.execute(_predlog("PROVERA")).fetchall()
        assert len(nadjeno) == 1 and nadjeno[0][2] == 2 and len(nadjeno[0][3]) == 2
        with pytest.raises(psycopg.errors.UniqueViolation):                  # i indeks zaista tada ne nastaje
            c.execute(_predlog("PRIMENA"))


def test_provera_i_indeks_su_isti_skup_redova(baza):
    """Tekstualno: kolone GROUP BY i WHERE provere su tačno kolone i WHERE indeksa."""
    provera, primena = _predlog("PROVERA"), _predlog("PRIMENA")
    grupa = re.search(r"GROUP BY (.*?)\s+HAVING", provera, re.S).group(1).replace(" ", "")
    kljuc = re.search(r"\((.*?)\)\s+WHERE", primena, re.S).group(1).replace(" ", "")
    assert grupa == kljuc == "source_intake_job_id,content_sha256"
    uslov = lambda s: re.search(r"WHERE (.*?)(?:GROUP BY|;|$)", s, re.S).group(1).split()   # noqa: E731
    assert uslov(provera) == uslov(primena.split("public.predmet_dokumenti", 1)[1])


def test_138_ne_hvata_red_bez_identiteta_zato_kod_ne_sme_da_ga_upise(baza):
    """RIZIK A: stara „uža varijanta“ upisa (posle isteka veze) ostavlja red sa NULL identitetom. Indeks 138 ga ne
    vidi: sledeći upis istog dokumenta sa identitetom PROLAZI — dva reda istog dokumenta i sa indeksom."""
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(_predlog("PRIMENA"))
        _upisi(c, pid, uid, jid, 1, sa_identitetom=False)
        assert _postoji(c, uid) == []                                        # provera duplikata ga ne nalazi
        _upisi(c, pid, uid, jid, 2)
    assert _redova(baza) == 2


def test_izveden_identitet_predmeta_drugi_upis_istog_posla_pada_atomski(baza):
    """RIZIK B: dva procesa (ili ponovni pokušaj) otvaraju predmet za ISTI posao sa identitetom izvedenim iz posla.
    PRIMARY KEY odbija drugi upis i kad su transakcije istovremene; poruka nosi 23505 koju kod prepoznaje."""
    import routers.smart_intake as si
    jid = str(uuid.uuid4())
    pid = si._id_predmeta_posla(jid)
    assert pid == si._id_predmeta_posla(jid) and pid != si._id_predmeta_posla(str(uuid.uuid4()))
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute("CREATE TABLE public.predmeti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, naziv text)")
    ishod = {}
    with psycopg.connect(baza) as a:
        a.execute("INSERT INTO public.predmeti (id, user_id, naziv) VALUES (%s, %s, 'A')", (pid, uuid.uuid4()))

        def _b():
            try:
                with psycopg.connect(baza, autocommit=True) as b:
                    b.execute("INSERT INTO public.predmeti (id, user_id, naziv) VALUES (%s, %s, 'B')", (pid, uuid.uuid4()))
                ishod["b"] = "upisano"
            except psycopg.errors.UniqueViolation as e:
                ishod["b"] = (e.sqlstate, str(e))
        t = threading.Thread(target=_b)
        t.start()
        time.sleep(0.5)
        assert t.is_alive(), "B je morao da čeka A-ovu transakciju na primarnom ključu"
        a.commit()
        t.join(10)
    assert ishod["b"][0] == "23505" and 'duplicate key value violates unique constraint "predmeti_pkey"' in ishod["b"][1]
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute("SELECT count(*), min(naziv) FROM public.predmeti").fetchone() == (1, "A")


def test_rollback_iz_predloga_uklanja_samo_indeks(baza):
    jid, pid, uid = _posao(baza)
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(_predlog("PRIMENA"))
        _upisi(c, pid, uid, jid, 1)
        c.execute(_rollback())
        assert c.execute(_predlog("POTVRDA")).fetchall() == []
    assert _redova(baza) == 1
