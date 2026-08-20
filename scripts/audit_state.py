# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/audit_state.py

Generise STATE_AUDIT.md sa cinjenicama proverenim naspram zivog sistema
(Supabase + kod), ne naspram memorije ili narativa. Postoji zato sto je
interni referentni dokument od 2026-07-15 vec sledeceg dana imao tri
zastarele tvrdnje (migracija 074 "nije pokrenuta" — bila je; Case Genome
"ne azurira se sam" — azurira se od 2026-07-01; pricing mismatch — vec
ispravljen) — sve tri su bile proverljive kodom/bazom, ne pretpostavkom.

Dve provere:
  1. MIGRACIJE — za svaki migrations/*.sql fajl:
       a) CREATE TABLE IF NOT EXISTS public.<ime> — postoji li tabela live.
       b) ALTER TABLE public.<ime> ADD COLUMN IF NOT EXISTS <kolona> —
          postoji li kolona live na toj tabeli.
     Migracija bez i jednog od ova dva obrasca (cisto UPDATE/DELETE/DROP)
     se preskace — nema sta da se proveri iz ovog ugla.
     Otkriveno ovim tacnim mehanizmom 2026-07-16: migracija 016 nikad
     nije primenjena (ni CREATE TABLE ni ALTER TABLE deo) — Evidence Vault
     klasifikacija je bila kompletno mrtva otkad je uvedena, cutke je
     gutao gresku u try/except na svakom uploadu dokumenta.
  2. RUTERI — ponovo koristi scripts/audit_routers.py logiku da prijavi
     registrovane-ali-nepozvane module.

Pokreni: python scripts/audit_state.py
Zahteva .env sa SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (ili _SERVICE_KEY).
Izlaz: STATE_AUDIT.md u root-u + exit 1 ako je bar jedna migracija
nepotpuna ili bar jedan ruter mrtav.
"""
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"

sys.path.insert(0, str(ROOT / "scripts"))


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def audit_migrations() -> tuple[list[dict], list[str]]:
    """Vrati (rezultati, greske). Svaki rezultat: {file, tables: {name: bool}}."""
    _load_env()
    try:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"]
        supa = create_client(url, key)
    except Exception as e:
        return [], [f"Supabase konekcija neuspesna — preskacem proveru migracija: {e}"]

    table_re = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+public\.(\w+)", re.IGNORECASE
    )
    column_re = re.compile(
        r"ALTER TABLE\s+public\.(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)", re.IGNORECASE
    )

    _table_exists_cache: dict[str, bool] = {}
    _column_exists_cache: dict[tuple[str, str], bool] = {}

    def table_exists(name: str) -> bool:
        if name in _table_exists_cache:
            return _table_exists_cache[name]
        try:
            supa.table(name).select("*", count="exact").limit(0).execute()
            _table_exists_cache[name] = True
        except Exception:
            _table_exists_cache[name] = False
        return _table_exists_cache[name]

    def column_exists(table: str, column: str) -> bool:
        key = (table, column)
        if key in _column_exists_cache:
            return _column_exists_cache[key]
        if not table_exists(table):
            # tabela ne postoji uopste — kolona pitanje je moot, ne dupliraj gresku
            _column_exists_cache[key] = True
            return True
        try:
            supa.table(table).select(column).limit(0).execute()
            _column_exists_cache[key] = True
        except Exception:
            _column_exists_cache[key] = False
        return _column_exists_cache[key]

    results = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        src = path.read_text(encoding="utf-8", errors="ignore")
        table_names = sorted(set(table_re.findall(src)))
        columns = sorted(set(column_re.findall(src)))
        if not table_names and not columns:
            continue
        tables = {name: table_exists(name) for name in table_names}
        cols = {f"{t}.{c}": column_exists(t, c) for t, c in columns}
        results.append({"file": path.name, "tables": tables, "columns": cols})

    return results, []


def audit_routers() -> tuple[list[str], list[str], int]:
    import audit_routers as ar
    api_src = ar._read(ar.API_PY)
    routers = ar.find_registered_routers(api_src)
    frontend_src = ar._read(ar.STATIC_DIR / "vindex.js") if (ar.STATIC_DIR / "vindex.js").exists() else ""

    py_files = [p for p in ROOT.rglob("*.py")
                if "site-packages" not in str(p) and "__pycache__" not in str(p)
                and "/tests/" not in str(p).replace("\\", "/")]
    py_blobs = {p: ar._read(p) for p in py_files}

    dead, maybe_ext = [], []
    for var, mod in sorted(routers.items()):
        mf = ar.module_file(mod)
        if mf is None:
            continue
        src = ar._read(mf)
        routes = ar.extract_routes(src)
        if not routes:
            continue
        found = False
        looks_external = False
        for route in routes:
            needle = ar.static_prefix(route)
            if not needle or len(needle) < 4:
                continue
            if any(h in needle.lower() for h in ar.EXTERNAL_TRIGGER_HINTS):
                looks_external = True
            if needle in frontend_src:
                found = True
                break
            if any(needle in blob for p, blob in py_blobs.items() if p != mf):
                found = True
                break
        if not found:
            (maybe_ext if looks_external else dead).append(mod)

    return dead, maybe_ext, len(routers)


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mig_results, mig_errors = audit_migrations()
    dead_routers, maybe_external, total_routers = audit_routers()

    def is_complete(r: dict) -> bool:
        return all(r["tables"].values()) and all(r["columns"].values())

    incomplete = [r for r in mig_results if not is_complete(r)]

    lines = []
    lines.append("# STATE_AUDIT.md — automatski generisano, ne rucno pisano")
    lines.append("")
    lines.append(f"Generisano: {now} — pokretanjem `python scripts/audit_state.py`.")
    lines.append("Ovo NIJE narativ. Svaka linija ispod je provera naspram zive baze ili koda,")
    lines.append("ne pretpostavka o tome sta bi trebalo da bude live.")
    lines.append("")
    lines.append("## Migracije — CREATE TABLE naspram zive baze")
    lines.append("")
    if mig_errors:
        for e in mig_errors:
            lines.append(f"- GRESKA: {e}")
    elif not incomplete:
        lines.append(f"Svih {len(mig_results)} proverljivih migracija (CREATE TABLE / ADD COLUMN) je potpuno primenjeno live.")
    else:
        lines.append(f"{len(incomplete)}/{len(mig_results)} migracija ima bar jednu tabelu koja NIJE live:")
        lines.append("")
        for r in incomplete:
            missing_tables = [t for t, ok in r["tables"].items() if not ok]
            missing_cols = [c for c, ok in r["columns"].items() if not ok]
            missing = missing_tables + missing_cols
            lines.append(f"- `{r['file']}` — nedostaje: {', '.join(missing)}")
    lines.append("")
    lines.append("## Ruteri — registrovan naspram stvarno pozvan")
    lines.append("")
    lines.append(f"Provereno {total_routers} registrovanih rutera (api.py `include_router`).")
    lines.append("")
    if dead_routers:
        lines.append(f"**{len(dead_routers)} registrovan(a) bez i jednog pronadjenog pozivaoca** "
                      "(heuristika — vidi scripts/audit_routers.py za detalje/ogranicenja):")
        lines.append("")
        for mod in dead_routers:
            lines.append(f"- `{mod}`")
    else:
        lines.append("Nema pronadjenih rutera bez pozivaoca.")
    lines.append("")
    if maybe_external:
        lines.append(f"Moguce spoljni (webhook/cron, ne ocekuju interni poziv): "
                      f"{', '.join('`' + m + '`' for m in maybe_external)}")
        lines.append("")

    out_path = ROOT / "STATE_AUDIT.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Napisano: {out_path}")
    print(f"Migracije nepotpune: {len(incomplete)}/{len(mig_results)}")
    print(f"Ruteri bez pozivaoca: {len(dead_routers)}/{total_routers}")

    return 1 if (incomplete or dead_routers) else 0


if __name__ == "__main__":
    sys.exit(main())
