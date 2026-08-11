# -*- coding: utf-8 -*-
"""
Verifikacija migracije 111 na produkciji — SAMO ČITANJE.

ŠTA RADI
────────
Izvršava tri verifikaciona SELECT-a iz zaglavlja
`migrations/111_phantom_ai_charges.sql` i za svaku tačku ispisuje PASS ili
FAIL, sa konkretnim redovima kad nešto ne valja.

  1. Grupa A — 'confidence_audit', 'conflict_check', 'da_wallet_risk_assessment'
     moraju imati krediti=0, chargeable=false, ai_model prazan;
     'confidence_audit' uz to minimum_plan='basic' i cooldown_seconds>=5.

  2. KONTROLA — deljeni ključevi 'case_commander' i 'zastarelost_guardian'
     MORAJU ostati naplativi (krediti>0, chargeable=true). Oni su isti
     feature_key za AI i ne-AI endpointe; krediti=0 tamo bi poklonio stvarnu
     GPT potrošnju. Ako su ovde 0, neko je proširio migraciju.

  3. KONTROLA — namerno besplatne poslovne odluke ('morning_briefing',
     'voice', 'sudska_praksa') ostaju chargeable=true. `chargeable=false`
     znači „nema AI poziv uopšte" (migracija 070:29-34), a ne „trenutno
     besplatno po ceni".

Ne izvršava nijedan UPDATE/INSERT/DELETE. Konekcija se otvara u režimu
samo-za-čitanje (`default_transaction_read_only=on`), pa bi i greška u kodu
pukla umesto da nešto promeni.

KAKO SE POKREĆE
───────────────
    set SUPABASE_DB_URL=...        (Windows CMD)
    $env:SUPABASE_DB_URL = '...'   (PowerShell)
    export SUPABASE_DB_URL='...'   (bash)

    python scripts/verify_migration_111.py

Prihvata i `DATABASE_URL`. Connection string se NIKAD ne ispisuje — ni u
poruci o grešci; ispisuje se samo ime env promenljive iz koje je pročitan.

IZLAZNI KODOVI
──────────────
    0 — sve tri tačke PASS
    1 — bar jedna tačka FAIL
    2 — nedostaje psycopg ili env promenljiva, ili konekcija nije uspela
"""
from __future__ import annotations

import os
import sys

_ENV_KANDIDATI = ("SUPABASE_DB_URL", "DATABASE_URL")

_GRUPA_A = ("confidence_audit", "conflict_check", "da_wallet_risk_assessment")
_DELJENI = ("case_commander", "zastarelost_guardian")
_BESPLATNI = ("morning_briefing", "voice", "sudska_praksa")

_KOLONE = (
    "feature_key, krediti, chargeable, ai_model, minimum_plan, "
    "cooldown_seconds, updated_by"
)


def _pripremi_izlaz() -> None:
    """Windows konzola podrazumevano koristi cp1252 i puca na 'č'/'š'.

    Bez ovoga skripta završi UnicodeEncodeError-om i izlaznim kodom 1 —
    što bi vlasnik pročitao kao FAIL migracije, a nije. Preusmerava stdout i
    stderr na UTF-8 sa zamenom neprikazivih znakova, pa poruka uvek stigne.
    """
    for tok in (sys.stdout, sys.stderr):
        try:
            tok.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ispisi(oznaka: str, ok: bool, poruka: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {oznaka}" + (f" — {poruka}" if poruka else ""))


def _redovi(conn, kljucevi):
    """Vraća {feature_key: dict} za tražene ključeve."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_KOLONE} FROM public.feature_registry "
            "WHERE feature_key = ANY(%s) ORDER BY feature_key",
            (list(kljucevi),),
        )
        imena = [d.name for d in cur.description]
        return {r[0]: dict(zip(imena, r)) for r in cur.fetchall()}


def _tacka_1(conn) -> bool:
    redovi = _redovi(conn, _GRUPA_A)
    problemi: list[str] = []

    for kljuc in _GRUPA_A:
        red = redovi.get(kljuc)
        if red is None:
            problemi.append(f"{kljuc}: reda nema u feature_registry")
            continue
        if red["krediti"] != 0:
            problemi.append(f"{kljuc}: krediti={red['krediti']}, očekivano 0")
        if red["chargeable"] is not False:
            problemi.append(f"{kljuc}: chargeable={red['chargeable']}, očekivano false")
        if red["ai_model"] is not None:
            problemi.append(
                f"{kljuc}: ai_model={red['ai_model']!r} — Registry i dalje tvrdi model "
                "za funkciju bez AI poziva"
            )

    ca = redovi.get("confidence_audit")
    if ca is not None:
        if ca["minimum_plan"] != "basic":
            problemi.append(
                f"confidence_audit: minimum_plan={ca['minimum_plan']!r}, očekivano 'basic' "
                "— basic korisnik i dalje dobija 403 pri otvaranju Podešavanja"
            )
        if ca["cooldown_seconds"] is None or ca["cooldown_seconds"] < 5:
            problemi.append(
                f"confidence_audit: cooldown_seconds={ca['cooldown_seconds']}, očekivano >= 5"
            )

    ok = not problemi
    _ispisi("1 · Grupa A — naplata bez AI poziva uklonjena", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        for kljuc in _GRUPA_A:
            r = redovi[kljuc]
            print(
                f"         {kljuc}: krediti={r['krediti']} chargeable={r['chargeable']} "
                f"ai_model={r['ai_model']} minimum_plan={r['minimum_plan']} "
                f"cooldown={r['cooldown_seconds']} updated_by={r['updated_by']}"
            )
    return ok


def _tacka_2(conn) -> bool:
    redovi = _redovi(conn, _DELJENI)
    problemi: list[str] = []

    for kljuc in _DELJENI:
        red = redovi.get(kljuc)
        if red is None:
            problemi.append(f"{kljuc}: reda nema u feature_registry")
            continue
        if not red["krediti"] or red["krediti"] <= 0:
            problemi.append(
                f"{kljuc}: krediti={red['krediti']} — deljeni ključ je obesnaplaćen, "
                "stvarna GPT potrošnja se sada poklanja"
            )
        if red["chargeable"] is not True:
            problemi.append(f"{kljuc}: chargeable={red['chargeable']}, očekivano true")
        if red["updated_by"] == "migration_111_phantom_ai_charges":
            problemi.append(
                f"{kljuc}: updated_by pokazuje da ga je migracija 111 dirnula — "
                "IN lista je proširena preko dogovorenog obima"
            )

    ok = not problemi
    _ispisi("2 · KONTROLA — deljeni ključevi ostaju naplativi", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        for kljuc in _DELJENI:
            r = redovi[kljuc]
            print(f"         {kljuc}: krediti={r['krediti']} chargeable={r['chargeable']}")
    return ok


def _tacka_3(conn) -> bool:
    redovi = _redovi(conn, _BESPLATNI)
    problemi: list[str] = []

    for kljuc in _BESPLATNI:
        red = redovi.get(kljuc)
        if red is None:
            problemi.append(f"{kljuc}: reda nema u feature_registry")
            continue
        if red["chargeable"] is not True:
            problemi.append(
                f"{kljuc}: chargeable={red['chargeable']} — namerno besplatna poslovna "
                "odluka je pretvorena u 'nema AI poziv'"
            )

    ok = not problemi
    _ispisi("3 · KONTROLA — namerno besplatne odluke netaknute", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        for kljuc in _BESPLATNI:
            r = redovi[kljuc]
            print(f"         {kljuc}: krediti={r['krediti']} chargeable={r['chargeable']}")
    return ok


def main() -> int:
    _pripremi_izlaz()
    try:
        import psycopg
    except ImportError:
        print(
            "GREŠKA: psycopg nije instaliran. Instaliraj sa:\n"
            "    pip install \"psycopg[binary]\"\n"
            "pa ponovo pokreni ovu skriptu.",
            file=sys.stderr,
        )
        return 2

    dsn = None
    izvor = None
    for ime in _ENV_KANDIDATI:
        vrednost = os.environ.get(ime)
        if vrednost:
            dsn, izvor = vrednost, ime
            break

    if not dsn:
        print(
            "GREŠKA: nije postavljena nijedna od promenljivih okruženja "
            f"{' / '.join(_ENV_KANDIDATI)}.\n"
            "Primer (PowerShell):  $env:SUPABASE_DB_URL = '<connection string>'\n"
            "Skripta connection string nikad ne ispisuje.",
            file=sys.stderr,
        )
        return 2

    print(f"Verifikacija migracije 111 — konekcija iz ${izvor} (vrednost se ne ispisuje).")
    print("Režim: samo čitanje. Nijedan red se ne menja.\n")

    try:
        # `default_transaction_read_only=on` je pojas i tregeri: čak i da se u
        # kod uvuče UPDATE, server bi ga odbio umesto da ga izvrši.
        conn = psycopg.connect(
            dsn,
            connect_timeout=10,
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )
    except Exception as exc:
        # Namerno se ispisuje samo TIP greške — tekst psycopg izuzetka može da
        # sadrži host i korisničko ime iz connection string-a.
        print(
            f"GREŠKA: konekcija na bazu nije uspela ({type(exc).__name__}). "
            f"Proveri vrednost ${izvor}, mrežni pristup i da li je baza dostupna.",
            file=sys.stderr,
        )
        return 2

    try:
        rezultati = []
        for provera in (_tacka_1, _tacka_2, _tacka_3):
            if rezultati:
                print()
            rezultati.append(provera(conn))
    finally:
        conn.close()

    print()
    if all(rezultati):
        print("REZULTAT: PASS — migracija 111 je primenjena tačno u dogovorenom obimu.")
        return 0

    print(
        "REZULTAT: FAIL — vidi tačke označene sa [FAIL] iznad.\n"
        "Ako je tačka 2 pala, migracija je proširena na deljene ključeve i stvarna GPT\n"
        "potrošnja se poklanja — to je skuplja greška od one koja se ispravljala."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
