# -*- coding: utf-8 -*-
"""
Vindex AI — Deployment Consistency Audit

Proverava da li je svaka migracija iz migrations/*.sql STVARNO primenjena na
aktivnu Supabase bazu — ne pretpostavlja, proverava direktnim upitima.

Kontekst: migracija 061 dokumentuje da se ovo tačno već jednom dogodilo
("5 kolona na profiles nikad nije kreirano" — is_pro/plan/trial_kraj/
onboarding_done/full_name su postojale u kodu i očekivane, ali NIKAD nisu bile
u bazi, tiho). Migracija 066 (digital_twin feature_registry red) je upravo
ovom sesijom otkrivena kao isti obrazac — napisana, ali nikad pokrenuta.
Ovaj alat postoji da se to ne otkriva ručno, jednom po incidentu.

Metod: za svaku migraciju, regex-parsira CREATE TABLE / ALTER TABLE ... ADD
COLUMN statements iz .sql fajla (DDL koji migracija TVRDI da je uradila), pa
za svaku izvedenu (tabela) ili (tabela, kolona) proveru pokuša SELECT preko
istog Supabase klijenta koji aplikacija koristi (shared/deps._get_supa()) —
PostgREST vraća prepoznatljiv kod za "tabela ne postoji" (PGRST205) i "kolona
ne postoji" (42703).

Ograničenja (namerno priznata, ne skrivena):
  - Ne parsira INSERT/UPDATE (seed podatke) kao generičku proveru — to je
    audit_dead_features.py-jev posao za feature_registry specifično.
  - Migracija bez ijedne CREATE TABLE/ALTER TABLE ADD COLUMN naredbe (npr.
    samo INSERT/UPDATE/CREATE POLICY/CREATE INDEX) je "UNVERIFIABLE" — alat
    to jasno kaže, ne tvrdi lažno da je OK.
  - Ako SVE DDL provere jedne migracije prođu, to je jak dokaz da je
    migracija pokrenuta — ali ne dokazuje da je SVAKA naredba u njoj uspela
    (npr. jedan UPDATE unutar iste migracije mogao je tiho da padne).

Upotreba:
    python scripts/audit_deployment_consistency.py

Exit kod: 1 ako postoji bar jedna NOT APPLIED migracija, inače 0.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(dotenv_path=ROOT / ".env")

CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(?:public\.)?(\w+)", re.IGNORECASE
)
ALTER_TABLE_BLOCK_RE = re.compile(
    r"ALTER TABLE\s+(?:public\.)?(\w+)\s+(.*?);", re.IGNORECASE | re.DOTALL
)
ADD_COLUMN_RE = re.compile(
    r"ADD COLUMN\s+(?:IF NOT EXISTS\s+)?(\w+)", re.IGNORECASE
)
LINE_COMMENT_RE = re.compile(r"--[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_sql_comments(sql: str) -> str:
    """Migration files describe past incidents in prose comments that can
    themselves contain SQL-looking text (e.g. migration 057 has a comment
    literally saying '-- CREATE TABLE IF NOT EXISTS bi to tiho preskocio' while
    describing a PAST bug) — without stripping comments first, the DDL regexes
    below would misparse that prose as a real statement."""
    sql = BLOCK_COMMENT_RE.sub(" ", sql)
    sql = LINE_COMMENT_RE.sub(" ", sql)
    return sql


def _parse_migration(path: Path) -> tuple[set[str], set[tuple[str, str]]]:
    """Returns (table_checks, column_checks) derived from a migration's DDL."""
    sql = _strip_sql_comments(path.read_text(encoding="utf-8", errors="replace"))

    tables = {m.group(1) for m in CREATE_TABLE_RE.finditer(sql)}

    columns: set[tuple[str, str]] = set()
    for m in ALTER_TABLE_BLOCK_RE.finditer(sql):
        table, body = m.group(1), m.group(2)
        if "ADD COLUMN" not in body.upper():
            continue
        for col_m in ADD_COLUMN_RE.finditer(body):
            columns.add((table, col_m.group(1)))

    return tables, columns


def _table_exists(supa, table: str) -> tuple[bool, str]:
    try:
        supa.table(table).select("*").limit(1).execute()
        return True, ""
    except Exception as exc:
        msg = str(exc)
        if "PGRST205" in msg or "Could not find the table" in msg:
            return False, "tabela ne postoji"
        # Any other error (RLS denial, etc.) means the table DOES exist —
        # only a "table not found" response means it doesn't.
        return True, ""


def _column_exists(supa, table: str, column: str) -> tuple[bool, str]:
    try:
        supa.table(table).select(column).limit(1).execute()
        return True, ""
    except Exception as exc:
        msg = str(exc)
        if "42703" in msg or "does not exist" in msg:
            return False, "kolona ne postoji"
        if "PGRST205" in msg or "Could not find the table" in msg:
            return False, "tabela ne postoji"
        return True, ""


def main() -> int:
    from shared.deps import _get_supa
    supa = _get_supa()

    files = sorted(ROOT.glob("migrations/*.sql"))

    applied: list[str] = []
    not_applied: list[tuple[str, list[str]]] = []
    unverifiable: list[str] = []

    # Cache table-existence results — many migrations touch the same table
    # (e.g. profiles, feature_registry), no need to re-query per migration.
    table_cache: dict[str, bool] = {}

    for f in files:
        tables, columns = _parse_migration(f)
        if not tables and not columns:
            unverifiable.append(f.name)
            continue

        missing: list[str] = []

        for t in sorted(tables):
            if t not in table_cache:
                ok, _ = _table_exists(supa, t)
                table_cache[t] = ok
            if not table_cache[t]:
                missing.append(f"tabela '{t}' ne postoji")

        for t, c in sorted(columns):
            if table_cache.get(t) is False:
                missing.append(f"kolona '{t}.{c}' ne postoji (tabela '{t}' ni sama ne postoji)")
                continue
            ok, reason = _column_exists(supa, t, c)
            if not ok:
                missing.append(f"kolona '{t}.{c}' ne postoji ({reason})")

        if missing:
            not_applied.append((f.name, missing))
        else:
            applied.append(f.name)

    print("=" * 78)
    print("DEPLOYMENT CONSISTENCY AUDIT")
    print("=" * 78)
    print(f"  Ukupno migracija:     {len(files)}")
    print(f"  APPLIED:              {len(applied)}")
    print(f"  NOT APPLIED:          {len(not_applied)}")
    print(f"  UNVERIFIABLE:         {len(unverifiable)}  (nema CREATE TABLE/ALTER...ADD COLUMN za proveru — samo seed/policy/index)")
    print()

    if not_applied:
        print("─" * 78)
        print("NOT APPLIED — migracija postoji u repou, ali baza ne odražava njen DDL:")
        print("─" * 78)
        for name, reasons in not_applied:
            print(f"  {name}")
            for r in reasons:
                print(f"      └─ {r}")
        print()

    if unverifiable:
        print("─" * 78)
        print("UNVERIFIABLE (proveri ručno ako je bitno — obično seed/policy/index):")
        print("─" * 78)
        for name in unverifiable:
            print(f"  {name}")
        print()

    if not_applied:
        print(f"[FAIL] {len(not_applied)} migracija nije primenjena na aktivnu bazu.")
        return 1

    print("[OK] Svaka migracija sa proverljivim DDL-om je primenjena na aktivnu bazu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
