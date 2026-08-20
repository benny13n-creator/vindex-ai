# -*- coding: utf-8 -*-
"""
scripts/export_rls_policies.py

Izvozi TRENUTNO STANJE Row Level Security politika iz produkcione Supabase
baze u version-controlled SQL fajl (migrations/rls_current_snapshot.sql).

ZAŠTO OVAJ SKRIPT POSTOJI:
  RLS politike se danas menjaju isključivo ručno u Supabase Dashboard-u i
  nigde nisu zapisane u repo-u. To znači da su "javne tvrdnje" u
  static/security.html i privacy.html o RLS izolaciji podataka trenutno
  NEPROVERLJIVE van same produkcije — ako neko slučajno izmeni ili obriše
  policy, repo i dalje "izgleda ispravno". Ovaj skript to zatvara: čini RLS
  stanje čitljivim u Git diff-u i reproduktivnim na novom environment-u.

READ-ONLY: ovaj skript ništa ne menja u bazi. Samo čita pg_policies/pg_class
i piše SQL snapshot na disk. Za primenu izmena i dalje važi postojeće
pravilo: migracije SQL uvek pokreće korisnik ručno u Supabase Dashboard-u,
nikad ovaj skript.

PREDUSLOVI (nisu deo osnovnog requirements.txt — namerno, jer je ovo
jednokratni/periodični ops alat, ne runtime zavisnost aplikacije):
  pip install psycopg2-binary

POVEZIVANJE:
  Treba direktna Postgres connection string (RAZLIČITA od SUPABASE_SERVICE_KEY
  koji koristi ostatak aplikacije preko PostgREST-a).
  Nabavlja se: Supabase Dashboard -> Project Settings -> Database
               -> Connection string -> URI (Session pooler ili Direct connection)
  Postavi je kao env var pre pokretanja (NE upisivati trajno u .env bez potrebe,
  ili je upisati i držati van git-a kao i ostale tajne):
    export SUPABASE_DB_URL="postgresql://postgres.xxxx:PASSWORD@...supabase.com:5432/postgres"

POKRETANJE:
    python scripts/export_rls_policies.py

IZLAZ:
    migrations/rls_current_snapshot.sql  — prepisan pri svakom pokretanju.
    Commit-uj promene normalno; git diff pokazuje TAČNO šta se promenilo
    u RLS politikama od poslednjeg snapshot-a.

PREPORUKA: pokretati periodično (npr. mesečno, ili pre svakog security/DPA
audita) i uključiti u release checklist.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "migrations" / "rls_current_snapshot.sql"

_HEADER = """-- =============================================================================
-- AUTO-GENERISANO — scripts/export_rls_policies.py
-- Snapshot RLS politika direktno iz produkcione baze. NE MENJATI RUČNO.
-- Da ažuriraš: pokreni ponovo scripts/export_rls_policies.py.
--
-- Generisano: {ts}
-- Izvor:      pg_catalog (pg_class, pg_policies), schema='public'
--
-- Svrha: ovaj fajl je izvor istine za tvrdnju u static/security.html §4 i
-- privacy.html ("Row Level Security izoluje podatke po korisniku"). Ako se
-- ovaj fajl promeni (git diff), tu tvrdnju treba ponovo proveriti pre
-- sledećeg objavljivanja dokumentacije. Vidi SECURITY_CLAIMS_TRACEABILITY.md.
-- =============================================================================

"""

_TABLES_SQL = """
SELECT n.nspname AS schema,
       c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
ORDER BY c.relname;
"""

_POLICIES_SQL = """
SELECT schemaname, tablename, policyname, permissive, roles, cmd,
       qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
"""


def _fmt_roles(roles) -> str:
    if not roles:
        return "PUBLIC"
    if isinstance(roles, str):
        roles = roles.strip("{}").split(",")
    return ", ".join(r.strip() for r in roles if r.strip())


def export_snapshot(conn_str: str) -> str:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(conn_str)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_TABLES_SQL)
            tables = cur.fetchall()

            cur.execute(_POLICIES_SQL)
            policies = cur.fetchall()
    finally:
        conn.close()

    lines = [_HEADER.format(ts=datetime.now(timezone.utc).isoformat())]

    lines.append("-- ─── Tabele i RLS status ─────────────────────────────────────────────────\n")
    tables_with_rls = 0
    tables_without_rls = []
    for t in tables:
        if t["rls_enabled"]:
            tables_with_rls += 1
            force = " FORCE ROW LEVEL SECURITY;" if t["rls_forced"] else ""
            lines.append(f'ALTER TABLE public.{t["table_name"]} ENABLE ROW LEVEL SECURITY;')
            if force:
                lines.append(f'ALTER TABLE public.{t["table_name"]}{force}')
        else:
            tables_without_rls.append(t["table_name"])
    lines.append("")

    if tables_without_rls:
        lines.append("-- ⚠ TABELE BEZ RLS (proveri da li je namerno — npr. lookup/reference tabele):")
        for name in tables_without_rls:
            lines.append(f"--   public.{name}")
        lines.append("")

    lines.append("-- ─── Politike ────────────────────────────────────────────────────────────\n")
    by_table: dict[str, list] = {}
    for p in policies:
        by_table.setdefault(p["tablename"], []).append(p)

    for table_name in sorted(by_table):
        lines.append(f"-- {table_name}")
        for p in by_table[table_name]:
            kind = "AS PERMISSIVE" if p["permissive"] == "PERMISSIVE" else "AS RESTRICTIVE"
            roles = _fmt_roles(p["roles"])
            cmd = p["cmd"] or "ALL"
            stmt = f'CREATE POLICY "{p["policyname"]}" ON public.{table_name}\n  {kind} FOR {cmd} TO {roles}'
            if p["qual"]:
                stmt += f'\n  USING ({p["qual"]})'
            if p["with_check"]:
                stmt += f'\n  WITH CHECK ({p["with_check"]})'
            stmt += ";"
            lines.append(stmt)
        lines.append("")

    lines.append(
        f"-- ─── Rezime: {tables_with_rls} tabela sa RLS, {len(tables_without_rls)} bez RLS, "
        f"{len(policies)} politika ukupno.\n"
    )

    return "\n".join(lines)


def main() -> None:
    conn_str = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not conn_str:
        print(
            "BLOCKER: SUPABASE_DB_URL nije postavljen.\n"
            "Nabavi connection string: Supabase Dashboard -> Project Settings -> Database\n"
            "  -> Connection string -> URI\n"
            'Zatim: export SUPABASE_DB_URL="postgresql://...")\n'
        )
        sys.exit(1)

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("BLOCKER: psycopg2 nije instaliran.\n  pip install psycopg2-binary")
        sys.exit(1)

    sql = export_snapshot(conn_str)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(sql, encoding="utf-8")
    print(f"[RLS EXPORT] Snapshot upisan: {OUT_PATH}")
    print("[RLS EXPORT] Pregledaj 'git diff' da vidiš šta se promenilo od poslednjeg snapshot-a.")


if __name__ == "__main__":
    main()
