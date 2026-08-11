#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kanonski bootstrap za TEST PostgreSQL klastere (Vindex AI).

ZAŠTO OVAJ FAJL POSTOJI
───────────────────────
Oko 59 testova naplatnog sloja (`tests/test_beta_gate_credit_race_postgres.py`,
`tests/test_atomic_usage_counters_postgres.py`, `tests/test_wave9_migration_111.py`,
`tests/test_wave9_billing_invariant.py`) izvršavaju migracije DOSLOVNO nad pravim
PostgreSQL-om. Ako klaster ne radi, oni se TIHO preskaču preko
`pytest.mark.skipif` — suite ostaje zelen, a najvredniji dokazi o naplati
nestaju bez ijedne crvene linije.

Do sada je procedura postojala samo u ljudskoj memoriji i u jednom pasusu u
`docs/beta_war/P0_CLOSURE_LEDGER.md`. Klasteri žive u `%TEMP%` i ne preživljavaju
restart mašine. Ovaj skript je jedini kanonski put: podigni, proveri, pokreni,
ugasi.

ODNOS PREMA POSTOJEĆIM TESTOVIMA
────────────────────────────────
Ne uvodi se nov mehanizam otkrivanja baze. Koristi se ISTI koji testovi već
imaju (`tests/test_atomic_usage_counters_postgres.py:46-64`):

    1. $VINDEX_TEST_PG_DSN ako je postavljen
    2. host=127.0.0.1 port=55433 user=postgres dbname=postgres
    3. host=127.0.0.1 port=55432 user=postgres dbname=postgres
    4. host=127.0.0.1 port=5432  user=postgres dbname=postgres

Port 5432 je namerno IZUZET iz `ALLOWED_TEST_PORTS` (v. `_provera_porta`) —
na razvojnoj mašini je to podrazumevani, trajni PostgreSQL servis sa stvarnim
podacima, ne throwaway klaster. `verify` ga odbija.

PODKOMANDE
──────────
    python scripts/test_db.py up       — podigne klaster(e) ako ne rade (idempotentno)
    python scripts/test_db.py status   — prijavi da li rade i da li su TESTNI
    python scripts/test_db.py verify   — fail-closed dokaz da cilj NIJE produkcija
    python scripts/test_db.py down     — ugasi ih

BEZBEDNOST ISPISA
─────────────────
Skript NIKAD ne ispisuje lozinku ni pun connection string — ni u uspehu, ni u
grešci, ni u tekstu izuzetka iz drajvera. Svaki izlaz prolazi kroz `_scrub()`.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# ─── Izlazni kodovi ──────────────────────────────────────────────────────────
EXIT_OK = 0          # sve u redu
EXIT_FAIL = 1        # operacija/verifikacija nije uspela
EXIT_NO_TOOLS = 2    # initdb/pg_ctl nisu pronađeni
EXIT_NO_DRIVER = 3   # psycopg nije instaliran -> ne može se DOKAZATI ništa -> fail-closed

# Portovi kojima ovaj skript upravlja (`up`/`down` bez --port).
MANAGED_PORTS = (55432, 55433)

# Portovi koje `verify` prihvata kao testne. 55434 je rezervisan za
# `tests/test_wave10_test_db_bootstrap.py` da ne bi gasio klastere koje
# paralelni agenti koriste za regresiju.
DEFAULT_ALLOWED_PORTS = (55432, 55433, 55434)

# Jedini prihvatljivi hostovi. Klaster sme da radi sa `--auth=trust` ISKLJUČIVO
# zato što sluša na loopback-u: `-h 127.0.0.1` znači da nijedan paket sa mreže
# ne može ni da stigne do njega, pa "bez lozinke" ne znači "otvoren svima" nego
# "dostupan samo procesima na ovoj mašini". Da klaster sluša na 0.0.0.0,
# `--auth=trust` bi bio neprihvatljiv i `verify` bi ga morao odbiti.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

# Šeme koje Supabase (naša produkcija) uvek ima, a `initdb` klaster nikad.
# Namerno NISU uključene šeme koje testovi sami prave.
PROD_SCHEMAS = (
    "auth",
    "storage",
    "realtime",
    "graphql_public",
    "supabase_migrations",
    "vault",
    "pgbouncer",
)

# Role koje Supabase uvek ima, a `initdb` klaster nikad.
# PAŽNJA: `anon`, `authenticated` i `service_role` NISU ovde — postojeći testovi
# ih sami kreiraju na test klasteru (test_beta_gate_credit_race_postgres.py:111),
# pa bi kao marker davali lažno pozitivan rezultat.
PROD_ROLES = (
    "supabase_admin",
    "supabase_auth_admin",
    "supabase_storage_admin",
    "supabase_read_only_user",
    "authenticator",
)


# ═════════════════════════════════════════════════════════════════════════════
# Redakcija ispisa
# ═════════════════════════════════════════════════════════════════════════════
# Doslovni stringovi koje treba maskirati gde god se pojave (pun DSN, lozinka).
_TAJNE: list[str] = []

_RE_PASSWORD_KV = re.compile(r"(?i)\bpassword\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)")
_RE_URL_CRED = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s@]*@")


def _zapamti_tajnu(dsn: str) -> None:
    """Registruje pun DSN i lozinku iz njega kao stringove koje `_scrub` briše.

    Radi se doslovna zamena podstringa jer je ona jedina pouzdana: poruke
    izuzetaka iz libpq umeju da ugrade delove DSN-a u nepredvidljivom obliku.
    """
    if not dsn:
        return
    if dsn not in _TAJNE:
        _TAJNE.append(dsn)
    m = _RE_PASSWORD_KV.search(dsn)
    if m:
        vrednost = m.group(0).split("=", 1)[1].strip().strip("'\"")
        if vrednost and vrednost not in _TAJNE:
            _TAJNE.append(vrednost)
    m = re.search(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s@]*:([^/\s@]+)@", dsn)
    if m and m.group(1) not in _TAJNE:
        _TAJNE.append(m.group(1))


def _scrub(tekst: object) -> str:
    """Uklanja lozinke i pune connection string-ove iz bilo kog teksta."""
    s = str(tekst)
    for tajna in _TAJNE:
        if tajna:
            s = s.replace(tajna, "<REDIGOVANO>")
    s = _RE_PASSWORD_KV.sub("password=<REDIGOVANO>", s)
    s = _RE_URL_CRED.sub(r"\1<REDIGOVANO>@", s)
    return s


def _utf8_izlaz() -> None:
    """Windows konzola podrazumeva cp1252 i puca na 'đ', 'ć', '✓'.

    Bez ovoga `status` i `verify` završavaju UnicodeEncodeError trace-om umesto
    izveštajem — tačno onaj tihi otkaz koji ovaj skript treba da spreči.
    """
    for tok in (sys.stdout, sys.stderr):
        try:
            tok.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def emit(*delovi: object) -> None:
    """Jedini dozvoljeni izlaz skripte — sve prolazi kroz redakciju."""
    tekst = _scrub(" ".join(str(d) for d in delovi))
    try:
        print(tekst)
    except UnicodeEncodeError:
        # Krajnji fallback ako se tok ne da rekonfigurisati (npr. egzotičan
        # pipe): bolje osiromašen ispis nego prekinuta komanda.
        kodiranje = getattr(sys.stdout, "encoding", None) or "ascii"
        print(tekst.encode(kodiranje, errors="replace").decode(kodiranje, errors="replace"))


def _sazetak(host: str, port: object, dbname: str) -> str:
    """Kratak, bezbedan opis cilja. Nikad lozinka, nikad pun DSN."""
    return f"{host}:{port}/{dbname or '?'}"


# ═════════════════════════════════════════════════════════════════════════════
# Pronalaženje PostgreSQL alata
# ═════════════════════════════════════════════════════════════════════════════
def pronadji_pg_bin() -> Path | None:
    """Vraća direktorijum sa `initdb`/`pg_ctl`, ili None.

    Redosled: $VINDEX_PG_BIN -> PATH -> standardna Windows instalacija
    (najviša verzija).
    """
    env_bin = os.getenv("VINDEX_PG_BIN")
    if env_bin and (Path(env_bin) / _exe("pg_ctl")).exists():
        return Path(env_bin)

    nadjen = shutil.which("pg_ctl")
    if nadjen:
        return Path(nadjen).parent

    kandidati: list[tuple[int, Path]] = []
    for koren in (r"C:\Program Files\PostgreSQL", r"C:\Program Files (x86)\PostgreSQL"):
        p = Path(koren)
        if not p.is_dir():
            continue
        for verzija in p.iterdir():
            bin_dir = verzija / "bin"
            if (bin_dir / _exe("pg_ctl")).exists():
                try:
                    redosled = int(re.sub(r"\D", "", verzija.name) or 0)
                except ValueError:
                    redosled = 0
                kandidati.append((redosled, bin_dir))
    if kandidati:
        return sorted(kandidati)[-1][1]
    return None


def _exe(ime: str) -> str:
    return f"{ime}.exe" if os.name == "nt" else ime


def _datadir(port: int) -> Path:
    """Data direktorijum klastera — UVEK u sistemskom temp-u, NIKAD u repou.

    Isto ime koje već koriste ručno napravljeni klasteri iz
    `docs/beta_war/P0_CLOSURE_LEDGER.md`, pa je `up` idempotentan i nad njima.
    """
    return Path(tempfile.gettempdir()) / f"vindex_pg_{port}"


def _logfile(port: int) -> Path:
    return Path(tempfile.gettempdir()) / f"vindex_pg_{port}.log"


def _pokreni(argv: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """subprocess sa eksplicitnim UTF-8 i BEZ pipe-ova.

    Dva razloga, oba naučena na ovoj mašini:

    1. Na Windows-u `text=True` podrazumeva cp1252 i lomi srpska slova u
       porukama PostgreSQL-a.

    2. `capture_output=True` (pipe) se ZAGLAVI na `pg_ctl start`. `pg_ctl`
       pokrene `postgres` kao dugoživeći proces koji NASLEDI iste pipe-ove i
       drži ih otvorene dok server radi. `subprocess.run` čeka EOF na tim
       pipe-ovima, pa se komanda nikad ne vrati iako je klaster odavno
       podignut. Zato se izlaz hvata u PRIVREMENI FAJL — fajl handle se
       zatvara odmah i ne blokira čitanje.
    """
    with tempfile.TemporaryFile(mode="w+b") as izlaz:
        try:
            kod = subprocess.run(argv, stdout=izlaz, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            izlaz.seek(0)
            tekst = izlaz.read().decode("utf-8", errors="replace")
            return subprocess.CompletedProcess(argv, 124, tekst, f"timeout nakon {timeout}s")
        izlaz.seek(0)
        tekst = izlaz.read().decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(argv, kod, tekst, "")


# ═════════════════════════════════════════════════════════════════════════════
# Otkrivanje servera — ISTI mehanizam koji testovi već koriste
# ═════════════════════════════════════════════════════════════════════════════
def kandidat_dsn_ovi() -> list[str]:
    env = os.getenv("VINDEX_TEST_PG_DSN")
    if env:
        return [env]
    return [
        "host=127.0.0.1 port=55433 user=postgres dbname=postgres",
        "host=127.0.0.1 port=55432 user=postgres dbname=postgres",
        "host=127.0.0.1 port=5432 user=postgres dbname=postgres",
    ]


def port_slusa(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> bool:
    """TCP proba — radi i bez psycopg i bez pg_ctl."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def dozvoljeni_portovi() -> set[int]:
    env = os.getenv("VINDEX_TEST_PG_PORTS", "").strip()
    if env:
        out = set()
        for deo in env.split(","):
            deo = deo.strip()
            if deo.isdigit():
                out.add(int(deo))
        if out:
            return out
    return set(DEFAULT_ALLOWED_PORTS)


# ═════════════════════════════════════════════════════════════════════════════
# VERIFY — fail-closed dokaz da cilj nije produkcija
# ═════════════════════════════════════════════════════════════════════════════
# Svaka provera vraća (prosla: bool, poruka: str). Redosled je bitan:
# STATIČKE provere (host, port) idu PRE povezivanja, da skript nikad ne otvori
# konekciju ka nečemu što nije dokazano lokalno.


def _provera_hosta(info: dict) -> tuple[bool, str]:
    """K1 — host mora biti loopback.

    Prva linija odbrane: produkcija je `db.<ref>.supabase.co`, dakle udaljeni
    host. Ako `host` uopšte nije naveden, libpq bi pao na podrazumevanu
    vrednost — to je pretpostavka, ne dokaz, pa se odbija (fail-closed).
    """
    host = (info.get("host") or "").strip()
    if not host:
        return False, "K1 host: DSN ne navodi host eksplicitno — ne može se dokazati da je lokalan"
    if host.lower() not in LOOPBACK_HOSTS:
        return False, f"K1 host: '{host}' nije loopback (dozvoljeno: 127.0.0.1, localhost, ::1)"
    return True, f"K1 host: {host} (loopback)"


def _provera_porta(info: dict) -> tuple[bool, str]:
    """K2 — port mora biti iz skupa testnih portova.

    Podrazumevani 5432 je NAMERNO odbijen: na razvojnoj mašini je to trajni
    PostgreSQL servis sa stvarnim podacima. Loopback host sam po sebi ne znači
    "throwaway".
    """
    dozvoljeni = dozvoljeni_portovi()
    raw = str(info.get("port") or "").strip()
    if not raw.isdigit():
        return False, "K2 port: DSN ne navodi port eksplicitno — ne može se dokazati da je testni"
    port = int(raw)
    if port not in dozvoljeni:
        return False, (
            f"K2 port: {port} nije testni port "
            f"(dozvoljeni: {sorted(dozvoljeni)}; proširiti preko $VINDEX_TEST_PG_PORTS)"
        )
    return True, f"K2 port: {port} (testni)"


def _provera_imena_baze(info: dict) -> tuple[bool, str]:
    """K3 — ime baze mora biti `postgres` (admin baza throwaway klastera) ili
    `vindex_*` (baze koje testovi sami prave i brišu).

    Produkciona Supabase baza se takođe zove `postgres`, pa ovaj kriterijum SAM
    ne dokazuje ništa — on samo isključuje očigledno pogrešne mete. Nosivi
    dokaz daju K5-K7.
    """
    dbname = (info.get("dbname") or "").strip()
    if not dbname:
        return False, "K3 baza: DSN ne navodi dbname"
    if dbname != "postgres" and not dbname.startswith("vindex_"):
        return False, f"K3 baza: '{dbname}' nije ni `postgres` ni `vindex_*`"
    return True, f"K3 baza: {dbname}"


# Lista statičkih provera. Mutacija (uklanjanje `_provera_hosta`) mora da obori
# `tests/test_wave10_test_db_bootstrap.py::test_verify_odbija_udaljeni_host`.
STATICKE_PROVERE = (_provera_hosta, _provera_porta, _provera_imena_baze)


def _zive_provere(conn) -> list[tuple[bool, str]]:
    """K4-K7 — provere nad samim serverom, ne nad tekstom DSN-a.

    Postoje zato što se DSN može slagati a meta ipak biti produkcija: SSH tunel
    može da izloži produkciju na 127.0.0.1:55432 i tada K1-K3 prolaze. K4-K7
    pitaju server šta je.
    """
    rez: list[tuple[bool, str]] = []

    # K4 — server potvrđuje da je konekcija loopback (ne veruje se DSN-u).
    try:
        # `host()` a ne `::text` — cast tipa `inet` vraća "127.0.0.1/32"
        # (sa maskom), pa bi poređenje sa skupom loopback adresa uvek palo.
        red = conn.execute("SELECT host(inet_server_addr()), current_setting('port')").fetchone()
        adresa, srv_port = red[0], red[1]
    except Exception as e:  # pragma: no cover - zavisi od servera
        rez.append((False, f"K4 server: adresa nije očitana ({type(e).__name__})"))
        return rez

    if not adresa:
        rez.append((False, "K4 server: inet_server_addr() je NULL — konekcija nije dokazano loopback"))
    elif adresa not in {"127.0.0.1", "::1"}:
        rez.append((False, f"K4 server: server sluša na {adresa}, nije loopback"))
    else:
        rez.append((True, f"K4 server: inet_server_addr()={adresa}"))

    dozvoljeni = dozvoljeni_portovi()
    if str(srv_port).isdigit() and int(srv_port) in dozvoljeni:
        rez.append((True, f"K5 stvarni port servera: {srv_port}"))
    else:
        rez.append((False, f"K5 stvarni port servera: {srv_port} nije testni port"))

    # K6 — data direktorijum mora biti u sistemskom temp-u.
    # Najjači pojedinačni marker: throwaway klaster po definiciji živi u temp-u.
    # Na Supabase-u ovaj upit puca (uloga nije superuser) -> fail-closed.
    try:
        datadir = conn.execute("SELECT current_setting('data_directory')").fetchone()[0]
    except Exception as e:
        rez.append((
            False,
            f"K6 data_directory: nije očitljiv ({type(e).__name__}) — "
            "na produkciji uloga nije superuser, pa se testnost ne može dokazati",
        ))
    else:
        temp_koren = Path(tempfile.gettempdir()).resolve()
        try:
            Path(datadir).resolve().relative_to(temp_koren)
        except Exception:
            rez.append((False, "K6 data_directory: klaster NIJE u sistemskom temp direktorijumu"))
        else:
            rez.append((True, "K6 data_directory: u sistemskom temp direktorijumu"))

    # K7 — odsustvo produkcionih (Supabase) markera.
    try:
        seme = [r[0] for r in conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (list(PROD_SCHEMAS),)
        ).fetchall()]
        role = [r[0] for r in conn.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(PROD_ROLES),)
        ).fetchall()]
    except Exception as e:
        rez.append((False, f"K7 markeri: upit nije uspeo ({type(e).__name__}) — fail-closed"))
    else:
        if seme or role:
            rez.append((False, f"K7 markeri: pronađeni PRODUKCIONI markeri — šeme={seme} role={role}"))
        else:
            rez.append((True, "K7 markeri: nema Supabase šema ni uloga"))

    return rez


def komanda_verify(args) -> int:
    dsn_ovi = [args.dsn] if getattr(args, "dsn", None) else kandidat_dsn_ovi()

    try:
        import psycopg
    except ImportError:
        emit("GREŠKA: psycopg nije instaliran — testnost baze se ne može DOKAZATI.")
        emit("        Fail-closed: verifikacija se odbija.")
        return EXIT_NO_DRIVER

    poslednji_razlog = "nijedan kandidat nije zadovoljio kriterijume"

    for dsn in dsn_ovi:
        _zapamti_tajnu(dsn)
        try:
            info = psycopg.conninfo.conninfo_to_dict(dsn)
        except Exception as e:
            emit(f"  ✖ DSN se ne može parsirati ({type(e).__name__}) — odbijen")
            poslednji_razlog = "DSN se ne može parsirati"
            continue

        meta = _sazetak(info.get("host") or "?", info.get("port") or "?", info.get("dbname") or "")
        emit(f"Kandidat: {meta}")

        pao = False
        for provera in STATICKE_PROVERE:
            ok, poruka = provera(info)
            emit(f"  {'✓' if ok else '✖'} {poruka}")
            if not ok:
                pao = True
        if pao:
            poslednji_razlog = f"statičke provere odbile {meta}"
            emit("  → odbijen pre povezivanja (fail-closed)")
            continue

        try:
            with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
                rezultati = _zive_provere(conn)
        except Exception as e:
            emit(f"  ✖ povezivanje nije uspelo ({type(e).__name__}): {_scrub(e)}")
            poslednji_razlog = f"povezivanje nije uspelo za {meta}"
            continue

        for ok, poruka in rezultati:
            emit(f"  {'✓' if ok else '✖'} {poruka}")
        if all(ok for ok, _ in rezultati):
            emit(f"VERIFIKOVANO: {meta} je TEST baza (7/7 kriterijuma).")
            return EXIT_OK
        poslednji_razlog = f"žive provere odbile {meta}"
        emit("  → odbijen (fail-closed)")

    emit(f"ODBIJENO: nijedna dostupna baza nije dokazano testna — {poslednji_razlog}.")
    emit("NIKAD ne uperavati test suite u produkcionu bazu.")
    return EXIT_FAIL


# ═════════════════════════════════════════════════════════════════════════════
# UP / DOWN / STATUS
# ═════════════════════════════════════════════════════════════════════════════
def _zahtevaj_alate() -> Path | None:
    bin_dir = pronadji_pg_bin()
    if bin_dir is None:
        emit("GREŠKA: `initdb`/`pg_ctl` nisu pronađeni.")
        emit("        Traženo u: $VINDEX_PG_BIN, PATH, C:\\Program Files\\PostgreSQL\\*\\bin")
        emit("        Instalirati PostgreSQL ili postaviti $VINDEX_PG_BIN na `bin` direktorijum.")
        return None
    return bin_dir


def komanda_up(args) -> int:
    portovi = args.port or list(MANAGED_PORTS)
    bin_dir = _zahtevaj_alate()
    if bin_dir is None:
        return EXIT_NO_TOOLS

    initdb = bin_dir / _exe("initdb")
    pg_ctl = bin_dir / _exe("pg_ctl")
    greske = 0

    for port in portovi:
        datadir = _datadir(port)

        # IDEMPOTENTNOST 1: već radi -> ne diraj ništa, ne briši podatke.
        if port_slusa(port):
            emit(f"[{port}] već radi — preskočeno (idempotentno)")
            continue

        # IDEMPOTENTNOST 2: data dir postoji -> samo start, NIKAD ponovni initdb.
        if not (datadir / "PG_VERSION").exists():
            if datadir.exists() and any(datadir.iterdir()):
                emit(f"[{port}] GREŠKA: {datadir.name} postoji ali nije validan klaster — ručna intervencija")
                greske += 1
                continue
            datadir.mkdir(parents=True, exist_ok=True)
            emit(f"[{port}] initdb u sistemskom temp-u…")
            # --auth=trust je prihvatljiv ISKLJUČIVO jer klaster sluša na
            # 127.0.0.1 (v. `-h 127.0.0.1` niže): bez lozinke, ali i bez ijednog
            # mrežnog puta do servera. Nikad ne koristiti ovo za klaster koji
            # sluša na 0.0.0.0.
            r = _pokreni([str(initdb), "-D", str(datadir), "-U", "postgres",
                          "--auth=trust", "--encoding=UTF8"])
            if r.returncode != 0:
                emit(f"[{port}] initdb NIJE uspeo (kod {r.returncode}):")
                emit(_scrub((r.stderr or r.stdout or "").strip()[:800]))
                emit(f"[{port}] napomena: initdb odbija da radi iz elevirane (Administrator) sesije")
                greske += 1
                continue

        emit(f"[{port}] start…")
        r = _pokreni([str(pg_ctl), "-D", str(datadir),
                      "-o", f"-p {port} -h 127.0.0.1",
                      "-l", str(_logfile(port)), "start"])
        if r.returncode != 0 and not port_slusa(port):
            emit(f"[{port}] start NIJE uspeo (kod {r.returncode}):")
            emit(_scrub((r.stderr or r.stdout or "").strip()[:800]))
            greske += 1
            continue
        emit(f"[{port}] radi")

    return EXIT_OK if greske == 0 else EXIT_FAIL


def komanda_down(args) -> int:
    portovi = args.port or list(MANAGED_PORTS)
    bin_dir = _zahtevaj_alate()
    if bin_dir is None:
        return EXIT_NO_TOOLS
    pg_ctl = bin_dir / _exe("pg_ctl")
    greske = 0

    for port in portovi:
        datadir = _datadir(port)
        if not (datadir / "PG_VERSION").exists():
            emit(f"[{port}] nema klastera u temp-u — ništa za gašenje")
            continue
        if not port_slusa(port):
            emit(f"[{port}] već ugašen")
            continue
        r = _pokreni([str(pg_ctl), "-D", str(datadir), "-m", "fast", "stop"])
        if r.returncode != 0 and port_slusa(port):
            emit(f"[{port}] gašenje NIJE uspelo (kod {r.returncode}):")
            emit(_scrub((r.stderr or r.stdout or "").strip()[:400]))
            greske += 1
            continue
        emit(f"[{port}] ugašen")

    if args.purge:
        for port in portovi:
            datadir = _datadir(port)
            if port_slusa(port):
                emit(f"[{port}] --purge preskočen: klaster i dalje radi")
                continue
            if datadir.exists():
                shutil.rmtree(datadir, ignore_errors=True)
                emit(f"[{port}] data direktorijum obrisan")

    return EXIT_OK if greske == 0 else EXIT_FAIL


def komanda_status(args) -> int:
    portovi = args.port or list(MANAGED_PORTS)
    bin_dir = pronadji_pg_bin()
    emit(f"PostgreSQL alati: {'pronađeni' if bin_dir else 'NISU PRONAĐENI'}")
    emit(f"Data direktorijumi: {Path(tempfile.gettempdir()) / 'vindex_pg_<port>'}")

    env_dsn = os.getenv("VINDEX_TEST_PG_DSN")
    emit(f"$VINDEX_TEST_PG_DSN: {'postavljen (testovi ga koriste umesto auto-otkrivanja)' if env_dsn else 'nije postavljen (auto-otkrivanje)'}")
    emit("")

    try:
        import psycopg  # noqa: F401
        ima_drajver = True
    except ImportError:
        ima_drajver = False
        emit("UPOZORENJE: psycopg nije instaliran — testnost se ne može proveriti,")
        emit("            a PG testovi naplate će se TIHO preskočiti.")

    bilo_ugasenih = False
    for port in portovi:
        datadir = _datadir(port)
        radi = port_slusa(port)
        ima_dir = (datadir / "PG_VERSION").exists()
        if not radi:
            bilo_ugasenih = True
            emit(f"[{port}] NE RADI  (data dir: {'postoji' if ima_dir else 'ne postoji'})")
            continue

        oznaka = "?"
        if ima_drajver:
            klasa = argparse.Namespace(
                dsn=f"host=127.0.0.1 port={port} user=postgres dbname=postgres"
            )
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                kod = komanda_verify(klasa)
            oznaka = "TESTNA" if kod == EXIT_OK else "NIJE DOKAZANO TESTNA"
        emit(f"[{port}] RADI     — {oznaka}")

    if bilo_ugasenih:
        emit("")
        emit("Neki klaster ne radi. Testovi naplate nad pravom bazom biće TIHO PRESKOČENI")
        emit("(pytest.mark.skipif) — suite ostaje zelen, a dokaz nestaje. Pokrenuti:")
        emit("    python scripts/test_db.py up")
    return EXIT_OK


# ═════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    _utf8_izlaz()
    p = argparse.ArgumentParser(
        prog="test_db.py",
        description="Kanonski bootstrap za TEST PostgreSQL klastere (Vindex AI).",
    )
    sub = p.add_subparsers(dest="komanda", required=True)

    def _dodaj_port(sp):
        sp.add_argument("--port", type=int, action="append",
                        help=f"port klastera (podrazumevano: {list(MANAGED_PORTS)})")

    sp_up = sub.add_parser("up", help="podigni klaster(e) ako ne rade (idempotentno)")
    _dodaj_port(sp_up)
    sp_up.set_defaults(func=komanda_up)

    sp_down = sub.add_parser("down", help="ugasi klaster(e)")
    _dodaj_port(sp_down)
    sp_down.add_argument("--purge", action="store_true",
                         help="obriši i data direktorijum nakon gašenja")
    sp_down.set_defaults(func=komanda_down)

    sp_st = sub.add_parser("status", help="da li rade i da li su testni")
    _dodaj_port(sp_st)
    sp_st.set_defaults(func=komanda_status)

    sp_v = sub.add_parser("verify", help="fail-closed dokaz da cilj NIJE produkcija")
    sp_v.add_argument("--dsn", help="eksplicitan DSN (podrazumevano: isto otkrivanje kao testovi)")
    sp_v.set_defaults(func=komanda_verify)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
