# -*- coding: utf-8 -*-
"""
Migration drift detector — compares what migrations/ DECLARES against what the
production schema ACTUALLY has.

WHY THIS EXISTS
───────────────
On 2026-08-09 migration 109 aborted with:

    ERROR: 42P01: relation "public.discovered_bilteni" does not exist

That table is created by migrations/017_scraper_state.sql. It had never been
applied to this database, and nobody knew — the repository's migration list and
the live schema had silently diverged, with no way to notice short of a
migration crashing into the gap.

Everything downstream of that assumption is affected: a "fix" that lives only in
an unapplied migration is not a fix, and a coverage number computed from
migration files is fiction if the objects are not there.

WHAT IT CHECKS
──────────────
FUNCTIONS. Parses every CREATE [OR REPLACE] FUNCTION out of migrations/ with its
exact parameter names, then probes each through PostgREST using those names plus
a deliberately invalid value, so the call aborts at argument casting BEFORE the
function body runs. Nothing is executed and nothing is written.

  22P02 / 42883 / 22003 / 22007  -> resolved, so the function EXISTS
  PGRST202                       -> could not resolve, so it is MISSING

TABLES. Reads the PostgREST OpenAPI document, which lists every exposed table
and column, and checks the tables that migrations create.

WHY THE PARAMETER NAMES MATTER
──────────────────────────────
Three times during this investigation a probe reported a function MISSING that
was in fact present, because it guessed the parameter names. PostgREST resolves
an RPC by exact named arguments; a wrong or incomplete set returns PGRST202,
which is indistinguishable from "no such function". Every probe here therefore
uses the names parsed out of the migration itself, and the run includes a
negative control so a broken probe cannot report a clean schema.

READ-ONLY. No INSERT/UPDATE/DELETE/DDL, and no function body is ever entered.
Usage:  python scripts/migration_drift_check.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Values chosen so the cast fails for every scalar type we pass them to.
_BAD = "VINDEX-DRIFT-PROBE-NOT-VALID"

_RESOLVED_CODES = {"22P02", "42883", "22003", "22007", "23514", "23502", "23503"}


def _parse_functions(migrations_dir: Path) -> dict[str, tuple[str, list[str]]]:
    """name -> (migration file, [parameter names])."""
    out: dict[str, tuple[str, list[str]]] = {}
    pat = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-z_0-9]+)\s*\((.*?)\)\s*RETURNS",
        re.I | re.S,
    )
    for f in sorted(migrations_dir.glob("*.sql")):
        text = _strip_sql_comments(f.read_text(encoding="utf-8", errors="replace"))
        for name, args in pat.findall(text):
            params = re.findall(r"\b(p_[a-z_0-9]+)", args)
            if params:                      # later definition wins, as in SQL
                out[name] = (f.name, params)
    return out


def _strip_sql_comments(text: str) -> str:
    """Removes -- line comments before parsing.

    Without this the parser reports table names like IF, bi and iznad, because
    several migrations DISCUSS "CREATE TABLE IF NOT EXISTS" in a comment and the
    regex happily matches the next word. A drift detector that invents four
    fictional tables is not one anybody will read twice.
    """
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in text.splitlines())


def _parse_tables(migrations_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    pat = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z_0-9]*)\s*\(", re.I)
    for f in sorted(migrations_dir.glob("*.sql")):
        text = _strip_sql_comments(f.read_text(encoding="utf-8", errors="replace"))
        for name in pat.findall(text):
            out.setdefault(name, f.name)
    return out


def main() -> int:
    import httpx
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY nisu postavljeni — prekidam.")
        return 2

    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    functions = _parse_functions(ROOT / "migrations")
    tables = _parse_tables(ROOT / "migrations")

    missing_fn: list[tuple[str, str]] = []
    present_fn = 0
    unknown_fn: list[tuple[str, str, str]] = []

    with httpx.Client(timeout=30) as client:
        # Negative control FIRST. If an invented name does not report missing,
        # the probe is broken and a clean result would be meaningless.
        ctrl = client.post(f"{url}/rest/v1/rpc/vindex_drift_control_xyz",
                           headers=headers, json={"p_x": _BAD})
        ctrl_code = (ctrl.json() or {}).get("code") if ctrl.headers.get(
            "content-type", "").startswith("application/json") else None
        if ctrl_code != "PGRST202":
            print(f"KONTROLA PALA: izmišljena funkcija je vratila {ctrl_code!r}, "
                  f"očekivano PGRST202. Proba nije pouzdana — prekidam.")
            return 2

        for name, (src, params) in sorted(functions.items()):
            payload = {p: _BAD for p in params}
            r = client.post(f"{url}/rest/v1/rpc/{name}", headers=headers, json=payload)
            try:
                body = r.json()
            except Exception:
                body = {}
            code = body.get("code") if isinstance(body, dict) else None

            if code in _RESOLVED_CODES or r.status_code == 200:
                present_fn += 1
            elif code == "PGRST202":
                missing_fn.append((name, src))
            else:
                unknown_fn.append((name, src, str(code)))

        spec = client.get(f"{url}/rest/v1/", headers=headers).json()

    exposed = set((spec.get("definitions") or spec.get("components", {}).get("schemas", {})).keys())
    missing_tbl = sorted((t, src) for t, src in tables.items() if t not in exposed)

    print(f"Funkcija u migracijama: {len(functions)} | prisutno: {present_fn} | "
          f"nedostaje: {len(missing_fn)} | neodređeno: {len(unknown_fn)}")
    print(f"Tabela u migracijama:   {len(tables)} | izloženo preko PostgREST-a: "
          f"{len(tables) - len(missing_tbl)} | nije izloženo: {len(missing_tbl)}")

    if missing_fn:
        print("\nNEDOSTAJUĆE FUNKCIJE (migracija deklariše, baza nema):")
        for name, src in missing_fn:
            print(f"  {name:32} {src}")

    if unknown_fn:
        print("\nNEODREĐENO (proba nije dala jasan odgovor — proveriti ručno):")
        for name, src, code in unknown_fn:
            print(f"  {name:32} {src:44} code={code}")

    if missing_tbl:
        print("\nTABELE KOJE POSTGREST NE IZLAŽE:")
        print("  Napomena: tabela može postojati a ne biti izložena (nije u API šemi),")
        print("  pa ovo nije dokaz odsustva — samo lista koju treba pogledati.")
        for name, src in missing_tbl:
            print(f"  {name:32} {src}")

    return 1 if missing_fn else 0


if __name__ == "__main__":
    raise SystemExit(main())
