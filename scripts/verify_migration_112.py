# -*- coding: utf-8 -*-
"""
Verifikacija migracije 112 na produkciji — SAMO ČITANJE.

ŠTA RADI
────────
Proverava da je `migrations/112_feature_usage_provenance.sql` stvarno primenjena
nad bazom na koju pokazuje connection string iz okruženja, i za svaku tačku
ispisuje PASS ili FAIL sa konkretnim razlogom.

  1. KOLONE — `feature_usage_log` mora imati `predmet_id` (uuid) i
     `correlation_id` (text), OBE NULLABLE. Tip nije kozmetika: `predmet_id` je
     `uuid` jer je `public.predmeti.id` UUID (supabase_setup.sql:301) — kolona
     tipa `text` bi tiho onemogućila JOIN. NULLABLE je uslov bezbednosti:
     `NOT NULL` bi zahtevao prepis cele tabele naplate pod ACCESS EXCLUSIVE
     bravom i oborio bi svaki upis bez konteksta.

  2. INDEKSI — `feature_usage_log_correlation_idx` i
     `feature_usage_log_predmet_idx`. Bez njih forenzički upit („šta se desilo
     u okviru jednog zahteva") postaje sekvencijalno čitanje cele tabele
     naplate. Oba su parcijalna (`WHERE ... IS NOT NULL`), jer svi redovi pre
     migracije imaju NULL.

  3. KONTROLA — na te dve kolone NE SME postojati FOREIGN KEY. Zaglavlje
     migracije 112 to izričito obrazlaže: FK sa CASCADE bi BRISAO istoriju
     naplate kad se predmet obriše, RESTRICT bi onemogućio brisanje predmeta, a
     SET NULL bi tiho pojeo dokaz. Ako se FK ovde pojavi, neko je „popravio"
     migraciju u pogrešnom smeru i finansijski trag je ugrožen.

  4. KONTROLA — naplatne kolone `feature_usage_log` iz migracije 065 moraju
     biti netaknute (`krediti_potroseni`, `user_id`, `feature_key`,
     `created_at`). 112 je čisto aditivna; ako je nešto od ovoga nestalo ili
     promenilo tip, primenjena je neka druga verzija fajla.

Ne izvršava nijedan UPDATE/INSERT/DELETE. Konekcija se otvara u režimu
samo-za-čitanje (`default_transaction_read_only=on`), pa bi i greška u kodu
pukla umesto da nešto promeni.

KAKO SE POKREĆE
───────────────
    set SUPABASE_DB_URL=...        (Windows CMD)
    $env:SUPABASE_DB_URL = '...'   (PowerShell)
    export SUPABASE_DB_URL='...'   (bash)

    python scripts/verify_migration_112.py

Prihvata i `DATABASE_URL`. Connection string se NIKAD ne ispisuje — ni u
poruci o grešci; ispisuje se samo ime env promenljive iz koje je pročitan.

IZLAZNI KODOVI
──────────────
    0 — sve tačke PASS
    1 — bar jedna tačka FAIL
    2 — nedostaje psycopg ili env promenljiva, ili konekcija nije uspela
"""
from __future__ import annotations

import os
import sys

_ENV_KANDIDATI = ("SUPABASE_DB_URL", "DATABASE_URL")

_TABELA = "feature_usage_log"

# (ime_kolone, očekivan `information_schema.columns.data_type`)
_NOVE_KOLONE = (
    ("predmet_id", "uuid"),
    ("correlation_id", "text"),
)

_INDEKSI = (
    ("feature_usage_log_correlation_idx", "correlation_id"),
    ("feature_usage_log_predmet_idx", "predmet_id"),
)

# Kolone iz migracije 065 koje 112 ne sme da dirne.
_KOLONE_065 = (
    ("user_id", "uuid"),
    ("feature_key", "text"),
    ("krediti_potroseni", "numeric"),
    ("created_at", "timestamp with time zone"),
)


def _pripremi_izlaz() -> None:
    """Windows konzola podrazumevano koristi cp1252 i puca na 'č'/'š'.

    Bez ovoga skripta završi UnicodeEncodeError-om i izlaznim kodom 1 — što bi
    vlasnik pročitao kao FAIL migracije, a nije.
    """
    for tok in (sys.stdout, sys.stderr):
        try:
            tok.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ispisi(oznaka: str, ok: bool, poruka: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {oznaka}" + (f" — {poruka}" if poruka else ""))


def _kolone(conn) -> dict:
    """Vraća {ime_kolone: (data_type, is_nullable)} za `feature_usage_log`."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (_TABELA,),
        )
        return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def _tacka_1(conn) -> bool:
    kolone = _kolone(conn)
    problemi: list[str] = []

    if not kolone:
        problemi.append(
            f"tabela public.{_TABELA} ne postoji ili je nedostupna — "
            "migracija 065 nije pokrenuta, pa 112 nije ni mogla da prođe"
        )
    else:
        for ime, ocekivan_tip in _NOVE_KOLONE:
            nadjeno = kolone.get(ime)
            if nadjeno is None:
                problemi.append(
                    f"{ime}: kolona ne postoji — migracija 112 NIJE primenjena na ovoj bazi"
                )
                continue
            tip, nullable = nadjeno
            if tip != ocekivan_tip:
                problemi.append(
                    f"{ime}: tip je {tip!r}, očekivano {ocekivan_tip!r} — "
                    "spajanje sa ai_forensics/predmeti neće raditi"
                )
            if nullable != "YES":
                problemi.append(
                    f"{ime}: kolona je NOT NULL, mora biti NULLABLE — svaki upis "
                    "naplate bez konteksta bi bio odbijen"
                )

    ok = not problemi
    _ispisi("1 · Kolone provenance postoje, tačnog tipa i NULLABLE", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        for ime, _ in _NOVE_KOLONE:
            tip, nullable = kolone[ime]
            print(f"         {ime}: tip={tip} nullable={nullable}")
    return ok


def _tacka_2(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = %s",
            (_TABELA,),
        )
        nadjeni = {r[0]: r[1] for r in cur.fetchall()}

    problemi: list[str] = []
    for ime, kolona in _INDEKSI:
        definicija = nadjeni.get(ime)
        if definicija is None:
            problemi.append(
                f"{ime}: indeks ne postoji — forenzički upit po {kolona} bi bio "
                "sekvencijalno čitanje cele tabele naplate"
            )
            continue
        if kolona not in definicija:
            problemi.append(f"{ime}: indeks ne pokriva kolonu {kolona}")
        if "WHERE" not in definicija.upper():
            problemi.append(
                f"{ime}: indeks nije parcijalan (nedostaje WHERE ... IS NOT NULL) — "
                "indeksira i sve NULL redove upisane pre migracije"
            )

    ok = not problemi
    _ispisi("2 · Indeksi koje migracija 112 deklariše", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        for ime, _ in _INDEKSI:
            print(f"         {ime}: postoji, parcijalan")
    return ok


def _tacka_3(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT con.conname, att.attname
              FROM pg_constraint con
              JOIN pg_class    cls ON cls.oid = con.conrelid
              JOIN pg_namespace ns ON ns.oid = cls.relnamespace
              JOIN unnest(con.conkey) AS k(attnum) ON true
              JOIN pg_attribute att
                ON att.attrelid = cls.oid AND att.attnum = k.attnum
             WHERE ns.nspname = 'public'
               AND cls.relname = %s
               AND con.contype = 'f'
               AND att.attname = ANY(%s)
            """,
            (_TABELA, [ime for ime, _ in _NOVE_KOLONE]),
        )
        nadjeno = cur.fetchall()

    problemi = [
        f"{attname}: postoji FOREIGN KEY {conname!r} — zaglavlje migracije 112 "
        "izričito zabranjuje FK ovde: brisanje predmeta ne sme da briše, blokira "
        "ni da tiho prazni istoriju naplate"
        for conname, attname in nadjeno
    ]

    ok = not problemi
    _ispisi("3 · KONTROLA — nema FOREIGN KEY na provenance kolonama", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        print("         predmet_id i correlation_id su bez FK, kako migracija nalaže")
    return ok


def _tacka_4(conn) -> bool:
    kolone = _kolone(conn)
    problemi: list[str] = []

    for ime, ocekivan_tip in _KOLONE_065:
        nadjeno = kolone.get(ime)
        if nadjeno is None:
            problemi.append(
                f"{ime}: kolona iz migracije 065 je nestala — 112 je aditivna i "
                "ne sme ništa da ukloni"
            )
            continue
        if nadjeno[0] != ocekivan_tip:
            problemi.append(
                f"{ime}: tip je {nadjeno[0]!r}, očekivano {ocekivan_tip!r} — "
                "naplatna semantika je promenjena"
            )

    ok = not problemi
    _ispisi("4 · KONTROLA — naplatne kolone iz 065 su netaknute", ok)
    for p in problemi:
        print(f"         {p}")
    if ok:
        print("         user_id, feature_key, krediti_potroseni, created_at — nepromenjeni")
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

    print(f"Verifikacija migracije 112 — konekcija iz ${izvor} (vrednost se ne ispisuje).")
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
        for provera in (_tacka_1, _tacka_2, _tacka_3, _tacka_4):
            if rezultati:
                print()
            rezultati.append(provera(conn))
    finally:
        conn.close()

    print()
    if all(rezultati):
        print("REZULTAT: PASS — migracija 112 je primenjena tačno u dogovorenom obimu.")
        return 0

    print(
        "REZULTAT: FAIL — vidi tačke označene sa [FAIL] iznad.\n"
        "Ako je pala tačka 1, migracija 112 nije pokrenuta na ovoj bazi: naplata se\n"
        "i dalje beleži bez konteksta i lanac naplata → predmet se ne može dokazati."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
