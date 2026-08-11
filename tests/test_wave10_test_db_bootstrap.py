# -*- coding: utf-8 -*-
"""
Wave 10 — `scripts/test_db.py` (kanonski bootstrap test baze).

ŠTA SE OVDE MERI
────────────────
Ne postojanje skripte nego njeno PONAŠANJE. Svaki test pokreće skriptu kao
STVARAN podproces i gleda izlazni kod i izlaz, jer je to tačno ono što
operater/CI vidi.

ZAŠTO JE OVO VREDNO TESTIRATI
─────────────────────────────
~59 testova naplatnog sloja se TIHO preskače (`pytest.mark.skipif`) kad test
klaster ne radi. Suite ostaje zelen, a najvredniji dokazi o naplati nestaju bez
ijedne crvene linije. `scripts/test_db.py` je jedini kanonski put do tog
klastera — ako on tiho otkaže ili, gore, prihvati produkcionu bazu kao testnu,
posledice su ozbiljnije od običnog crvenog testa.

IZOLACIJA OD PARALELNOG RADA
────────────────────────────
Testovi koji zahtevaju gašenje/podizanje klastera koriste ISKLJUČIVO port
55434. Klasteri na 55432 i 55433 se NIKAD ne diraju — njih koriste postojeći
testovi naplate i paralelni agenti za regresiju. `test_teardown_ne_moze_da_gasi_deljene_klastere`
to i dokazuje, umesto da se oslanja na disciplinu.

NIKAD se ne koristi stvarni produkcioni connection string. Sve „produkcione"
mete su izmišljene i nepostojeće.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKRIPTA = REPO_ROOT / "scripts" / "test_db.py"

# Port rezervisan za ove testove. Namerno van `MANAGED_PORTS`.
TEST_PORT = 55434
DELJENI_PORTOVI = (55432, 55433)

# Izmišljena produkciona meta. Host ne postoji, lozinka je izmišljena.
# Služi da dokaže da `verify` odbija PRE nego što uopšte pokuša povezivanje.
LAZNA_LOZINKA = "IzmisljenaLozinkaKojaNeSmeDaSePojaviUIzlazu"
LAZNI_PROD_DSN = (
    f"postgresql://postgres.izmisljenref:{LAZNA_LOZINKA}"
    "@db.izmisljen-projekat.supabase.co:5432/postgres?sslmode=require"
)


# ─── Učitavanje skripte kao modula (za mutacionu stražu) ─────────────────────
def _ucitaj_modul():
    spec = importlib.util.spec_from_file_location("vindex_test_db", SKRIPTA)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


tdb = _ucitaj_modul()


# ─── Pokretanje skripte kao podprocesa ───────────────────────────────────────
def pokreni(*argv, env_dodatak=None, timeout=240):
    """Pokreće `python scripts/test_db.py <argv>` i vraća CompletedProcess.

    `encoding="utf-8"` je obavezan: bez njega Windows koristi cp1252 i lomi
    srpska slova u izlazu, pa asserti nad porukama postaju nepouzdani.
    """
    env = dict(os.environ)
    # Podrazumevano se uklanja, da nasleđeni DSN iz okruženja ne bi tiho
    # promenio metu testa.
    env.pop("VINDEX_TEST_PG_DSN", None)
    if env_dodatak:
        env.update(env_dodatak)
    return subprocess.run(
        [sys.executable, str(SKRIPTA), *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="module")
def test_klaster():
    """Podiže izolovan klaster na 55434 i gasi ga (sa brisanjem) na kraju.

    Ako `up` ne uspe (npr. nema PostgreSQL alata), testovi koji zavise od
    stvarnog klastera se preskaču sa jasnim razlogom — preskakanje je činjenica
    o okruženju, nikad način da se izbegne tvrdnja koja pada.
    """
    r = pokreni("up", "--port", str(TEST_PORT))
    if r.returncode != 0:
        pytest.skip(f"klaster na {TEST_PORT} nije podignut (kod {r.returncode})")
    yield TEST_PORT
    pokreni("down", "--port", str(TEST_PORT), "--purge")


# ═══════════════════════════════════════════════════════════════════════════
# VERIFY — fail-closed
# ═══════════════════════════════════════════════════════════════════════════
def test_verify_odbija_produkcioni_dsn():
    """Meri: `verify` nad DSN-om produkcionog oblika mora imati NENULTI kod.

    Ovo je ključna tvrdnja celog fajla. Ako ovo padne, moguće je uperiti test
    suite u produkcionu bazu, a `verify` bi to odobrio.
    """
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": LAZNI_PROD_DSN})
    assert r.returncode != 0, (
        "verify je PRIHVATIO produkcioni DSN — fail-closed je probijen.\n"
        f"stdout: {r.stdout}"
    )
    assert "ODBIJENO" in r.stdout


def test_verify_odbija_udaljeni_host_i_na_testnom_portu():
    """Meri: udaljeni host se odbija čak i kad je port testni.

    Scenario: SSH tunel ili pogrešno podešen `$VINDEX_TEST_PG_DSN` koji
    produkciju izloži pod testnim portom. Port sam po sebi nije dokaz.
    """
    dsn = f"host=db.izmisljen-projekat.supabase.co port={TEST_PORT} user=postgres dbname=postgres"
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": dsn})
    assert r.returncode != 0
    assert "K1 host" in r.stdout


def test_verify_odbija_podrazumevani_port_5432():
    """Meri: 127.0.0.1:5432 se odbija iako je loopback.

    Na razvojnoj mašini je 5432 trajni PostgreSQL servis sa stvarnim podacima,
    a ne throwaway klaster. Postojeći testovi ga imaju kao poslednji fallback,
    pa `verify` mora eksplicitno da ga odbije.
    """
    dsn = "host=127.0.0.1 port=5432 user=postgres dbname=postgres"
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": dsn})
    assert r.returncode != 0
    assert "K2 port" in r.stdout


def test_verify_odbija_dsn_bez_eksplicitnog_hosta():
    """Meri: izostavljen host se ne popunjava pretpostavkom.

    libpq bi pao na podrazumevanu vrednost; pretpostavka nije dokaz, pa
    fail-closed nalaže odbijanje.
    """
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": "dbname=postgres port=55432"})
    assert r.returncode != 0
    assert "K1 host" in r.stdout


def test_verify_prihvata_lokalni_test_klaster(test_klaster):
    """Meri: nad stvarnim lokalnim test klasterom `verify` vraća 0.

    Bez ovoga bi `verify` mogao biti trivijalno „siguran" tako što odbija sve.
    """
    dsn = f"host=127.0.0.1 port={test_klaster} user=postgres dbname=postgres"
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": dsn})
    assert r.returncode == 0, f"verify je odbio pravi test klaster:\n{r.stdout}"
    assert "VERIFIKOVANO" in r.stdout


# ═══════════════════════════════════════════════════════════════════════════
# Redakcija ispisa
# ═══════════════════════════════════════════════════════════════════════════
def test_ne_ispisuje_lozinku_ni_pun_dsn():
    """Meri: ni stdout ni stderr ne sadrže lozinku ni pun connection string.

    Izlaz skripte završava u CI logovima i u izveštajima — jednom procureo,
    zauvek procureo.
    """
    r = pokreni("verify", env_dodatak={"VINDEX_TEST_PG_DSN": LAZNI_PROD_DSN})
    spojeno = r.stdout + r.stderr
    assert LAZNA_LOZINKA not in spojeno, "LOZINKA je procurela u izlaz skripte"
    assert LAZNI_PROD_DSN not in spojeno, "PUN DSN je procureo u izlaz skripte"
    assert "sslmode=require" not in spojeno


def test_status_ne_ispisuje_lozinku(test_klaster):
    """Isto, ali za `status` — i on parsira DSN-ove."""
    r = pokreni("status", "--port", str(test_klaster),
                env_dodatak={"VINDEX_TEST_PG_DSN": LAZNI_PROD_DSN})
    spojeno = r.stdout + r.stderr
    assert LAZNA_LOZINKA not in spojeno
    assert LAZNI_PROD_DSN not in spojeno


# ═══════════════════════════════════════════════════════════════════════════
# STATUS / UP — ponašanje
# ═══════════════════════════════════════════════════════════════════════════
def test_status_ugasenog_porta_ne_puca():
    """Meri: `status` nad portom bez klastera jasno kaže „NE RADI" i ne puca.

    Port 55439 se namerno ne koristi ni za jedan klaster.
    """
    r = pokreni("status", "--port", "55439")
    assert r.returncode == 0, f"status je pukao:\n{r.stdout}\n{r.stderr}"
    assert "NE RADI" in r.stdout
    assert "Traceback" not in r.stdout + r.stderr


def test_status_upozorava_na_tihi_skip():
    """Meri: kad klaster ne radi, `status` eksplicitno kaže da će se testovi
    naplate TIHO preskočiti. To je cela poenta ovog alata."""
    r = pokreni("status", "--port", "55439")
    assert "PRESKO" in r.stdout.upper()
    assert "test_db.py up" in r.stdout


def test_up_dvaput_zaredom_je_idempotentno(test_klaster):
    """Meri: drugi `up` nad već pokrenutim klasterom ne puca i ne briše podatke.

    Dokaz o očuvanju podataka je stvaran: u klaster se upiše marker tabela,
    pa se `up` pokrene ponovo, pa se marker traži nazad.
    """
    psycopg = pytest.importorskip("psycopg")
    dsn = f"host=127.0.0.1 port={test_klaster} user=postgres dbname=postgres"

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS public.vindex_marker_idempotencije")
        c.execute("CREATE TABLE public.vindex_marker_idempotencije (i int)")
        c.execute("INSERT INTO public.vindex_marker_idempotencije VALUES (42)")

    prvi = pokreni("up", "--port", str(test_klaster))
    drugi = pokreni("up", "--port", str(test_klaster))
    assert prvi.returncode == 0, prvi.stdout
    assert drugi.returncode == 0, drugi.stdout

    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            red = c.execute("SELECT i FROM public.vindex_marker_idempotencije").fetchone()
        assert red is not None and red[0] == 42, "`up` je uništio postojeće podatke"
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("DROP TABLE IF EXISTS public.vindex_marker_idempotencije")


def test_up_prijavljuje_da_klaster_vec_radi(test_klaster):
    """Meri: `up` nad pokrenutim klasterom to i KAŽE, ne ćuti."""
    r = pokreni("up", "--port", str(test_klaster))
    assert r.returncode == 0
    assert "idempotentno" in r.stdout or "već radi" in r.stdout


# ═══════════════════════════════════════════════════════════════════════════
# Izolacija od paralelnog rada
# ═══════════════════════════════════════════════════════════════════════════
def test_teardown_ne_moze_da_gasi_deljene_klastere():
    """Meri: port koji ovi testovi gase NIJE među deljenim klasterima.

    Bez ove provere, promena `TEST_PORT` na 55432 bi u teardown-u ugasila
    klaster koji koriste testovi naplate — i njih tiho preskočila.
    """
    assert TEST_PORT not in DELJENI_PORTOVI
    assert TEST_PORT not in tdb.MANAGED_PORTS, (
        "TEST_PORT je u MANAGED_PORTS — `down` bez --port bi ga zahvatio"
    )


def test_deljeni_klasteri_i_dalje_rade():
    """Meri: 55432 i 55433 su i dalje živi posle ovog modula.

    Ako ovaj test padne, ovi testovi su oborili tuđu regresionu infrastrukturu.
    """
    zivi = [p for p in DELJENI_PORTOVI if tdb.port_slusa(p)]
    if not zivi:
        pytest.skip("deljeni klasteri nisu bili podignuti ni pre ovog modula")
    assert len(zivi) == len(DELJENI_PORTOVI), (
        f"deljeni klaster je ugašen tokom ovog modula — žive samo {zivi}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# MUTACIONA STRAŽA
# ═══════════════════════════════════════════════════════════════════════════
def test_provera_hosta_je_nosiva():
    """Meri: `_provera_hosta` je JEDINA koja odbija udaljeni host na testnom
    portu — dakle njeno uklanjanje stvarno probija kapiju.

    Zašto se meri statički sloj a ne izlazni kod: `verify` odbija udaljeni host
    PRE povezivanja, pa bi test nad izlaznim kodom prolazio i onda kad host
    provere nema (odbio bi ga neuspeh povezivanja, a ne provera). To bi bio
    lažan dokaz. Ovde se meri baš kapija.

    Ako se `_provera_hosta` ukloni iz `STATICKE_PROVERE`, kapija prihvata
    produkcionu metu i ovaj test pada.
    """
    psycopg = pytest.importorskip("psycopg")
    dsn = f"host=db.izmisljen-projekat.supabase.co port={TEST_PORT} user=postgres dbname=postgres"
    info = psycopg.conninfo.conninfo_to_dict(dsn)

    rezultati = {p.__name__: p(info)[0] for p in tdb.STATICKE_PROVERE}

    assert "_provera_hosta" in rezultati, (
        "provera hosta je uklonjena iz STATICKE_PROVERE — udaljeni host na "
        "testnom portu bi prošao statičku kapiju"
    )
    assert rezultati["_provera_hosta"] is False, "provera hosta ne odbija udaljeni host"
    odbijaju = [ime for ime, ok in rezultati.items() if not ok]
    assert odbijaju == ["_provera_hosta"], (
        f"očekivano je da SAMO provera hosta odbija ovu metu, odbijaju: {odbijaju}"
    )


def test_produkcioni_markeri_ne_hvataju_test_uloge():
    """Meri: `PROD_ROLES` ne sadrži uloge koje postojeći testovi sami kreiraju.

    `test_beta_gate_credit_race_postgres.py:111` kreira `anon`,
    `authenticated` i `service_role` na TEST klasteru. Da su one markeri
    produkcije, `verify` bi počeo da odbija ispravan test klaster čim se ti
    testovi jednom pokrenu — lažno pozitivno, i to odloženo u vremenu.
    """
    for uloga in ("anon", "authenticated", "service_role"):
        assert uloga not in tdb.PROD_ROLES, (
            f"'{uloga}' je marker produkcije, a testovi je sami prave na test klasteru"
        )
