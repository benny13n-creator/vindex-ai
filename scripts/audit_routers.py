# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/audit_routers.py

Otkriva rutere koji su registrovani u api.py (app.include_router) ali ih
NISTA u repou ne poziva — ni static/vindex.js (frontend fetch), ni ostatak
backenda (cross-router import/poziv). Ovo je tacno klasa buga koja je
otkrivena za routers/vindex_memory.py 2026-07-16: registrovan, ziv u
feature_registry/cenovniku, nula stvarnih poziva.

Metod je heuristican (poredjenje statickih prefiksa putanje kao substring),
ne garantovan dokaz. Poznati lazni pozitivi:
  - Webhook/cron endpointi koje poziva SPOLJNI sistem (Stripe, cron job,
    Supabase trigger) — nas repo nema poziv jer pozivalac nije nas kod.
    Skripta ih oznacava kao 'MOZDA SPOLJNI' na osnovu putanje, ne kao 'MRTAV'.
  - Rute pozvane iz frontenda sa dinamicki sastavljenim putanjama koje
    skripta ne prepoznaje (redak slucaj — vecina fetch() poziva u vindex.js
    koristi string concat sa prepoznatljivim prefiksom).

Pokreni: python scripts/audit_routers.py
Izlaz: lista modula bez i jednog pronadjenog pozivaoca, plus 'mozda spoljni'.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_PY = ROOT / "api.py"
STATIC_DIR = ROOT / "static"

EXTERNAL_TRIGGER_HINTS = (
    "webhook", "cron", "stripe", "callback", "notify-external", "/health",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def find_registered_routers(api_src: str) -> dict[str, str]:
    """Vrati {router_var_name: module_path} za svaki app.include_router(X) gde
    postoji odgovarajuci 'from <module_path> import router as X' import."""
    imports = dict(re.findall(
        r"^from\s+([\w.]+)\s+import\s+router\s+as\s+(\w+)\s*$",
        api_src, flags=re.MULTILINE,
    ))
    module_by_var = {var: mod for mod, var in imports.items()}

    included_vars = re.findall(r"app\.include_router\(\s*(\w+)", api_src)

    result = {}
    for var in included_vars:
        mod = module_by_var.get(var)
        if mod:
            result[var] = mod
    return result


def module_file(mod: str) -> Path | None:
    rel = mod.replace(".", "/") + ".py"
    p = ROOT / rel
    return p if p.exists() else None


def extract_routes(src: str) -> list[str]:
    """Vrati listu punih putanja (prefix + route path) definisanih u modulu."""
    prefix_m = re.search(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']*)["\']', src)
    prefix = prefix_m.group(1) if prefix_m else ""

    routes = []
    for m in re.finditer(
        r'@router\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', src
    ):
        routes.append(prefix + m.group(1))
    return routes


def static_prefix(route: str) -> str:
    """Deo putanje pre prvog {param} — string na koji je razumno greppovati."""
    idx = route.find("{")
    base = route[:idx] if idx != -1 else route
    return base.rstrip("/")


def main() -> int:
    api_src = _read(API_PY)
    routers = find_registered_routers(api_src)

    frontend_src = _read(STATIC_DIR / "vindex.js") if (STATIC_DIR / "vindex.js").exists() else ""

    py_files = [p for p in ROOT.rglob("*.py")
                if "site-packages" not in str(p) and "__pycache__" not in str(p)
                and "/tests/" not in str(p).replace("\\", "/")]
    py_blobs = {}
    for p in py_files:
        try:
            py_blobs[p] = _read(p)
        except Exception:
            pass

    unused = []
    maybe_external = []
    used = []

    for var, mod in sorted(routers.items()):
        mf = module_file(mod)
        if mf is None:
            continue
        src = _read(mf)
        routes = extract_routes(src)
        if not routes:
            continue

        callers = set()
        looks_external = False
        for route in routes:
            needle = static_prefix(route)
            if not needle or len(needle) < 4:
                continue
            if any(hint in needle.lower() for hint in EXTERNAL_TRIGGER_HINTS):
                looks_external = True
            if needle in frontend_src:
                callers.add("frontend:static/vindex.js")
            for p, blob in py_blobs.items():
                if p == mf:
                    continue
                if needle in blob:
                    callers.add(f"backend:{p.relative_to(ROOT)}")

        if callers:
            used.append((mod, sorted(callers)))
        elif looks_external:
            maybe_external.append((mod, routes))
        else:
            unused.append((mod, routes))

    print(f"Provereno {len(routers)} registrovanih rutera.\n")

    if unused:
        print("=== MRTVI (registrovan, nula poziva u repou) ===")
        for mod, routes in unused:
            print(f"  {mod}")
            for r in routes[:5]:
                print(f"      {r}")
        print()
    else:
        print("=== Nema pronadjenih mrtvih rutera ===\n")

    if maybe_external:
        print("=== MOZDA SPOLJNI (webhook/cron/health — nema internog poziva, ali putanja to i ne ocekuje) ===")
        for mod, routes in maybe_external:
            print(f"  {mod}: {routes[0]}")
        print()

    print(f"Zivi (pronadjen bar 1 pozivalac): {len(used)}")

    return 1 if unused else 0


if __name__ == "__main__":
    sys.exit(main())
