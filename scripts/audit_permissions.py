# -*- coding: utf-8 -*-
"""
Vindex AI — Endpoint Coverage Audit (Faza 70.5)

Statička AST analiza svih FastAPI ruta u api.py, klijenti/router.py i
routers/*.py — bez uvoza aplikacije, bez konekcije na bazu/OpenAI/Pinecone.
Bezbedno se pokreće bilo gde, bilo kada, bez .env-a.

Svrha: da ne mora ručna provera da otkrije da je neki novi endpoint
zaboravljen bez PermissionService/UsageService gejta — tačno ono što se
dogodilo sa routers/region.py i routers/morning_briefing.py u Fazi 70.

Klasifikacija po endpointu:
  PERMISSION_GATED  — ima Depends(PermissionService.require("...")) na sebi
  ADMIN             — poziva _require_founder(...)/_is_founder(...) u telu
                       (founder-only administrativne rute, drugi mehanizam
                       zaštite od PermissionService, namerno odvojen)
  MISSING           — telo funkcije poziva AI (OpenAI/AsyncOpenAI klijent ili
                       .chat.completions.create) ali NEMA PermissionService
                       gejt niti founder proveru — STVARNI bezbednosni/
                       monetizacioni propust
  PUBLIC            — sve ostalo (CRUD/read-only/bez AI poziva) — legitimno
                       otvoreno, ne zahteva gejt

Napomena o preciznosti: heuristika za "poziva AI" prepoznaje direktnu upotrebu
OpenAI/AsyncOpenAI klijenta i .chat.completions.create — NE prepoznaje
indirektne wrapper funkcije definisane van ovog fajla (npr. main.py-jev
ask_agent() pozvan preko pokreni(...) helpera). Ti slučajevi se ručno
proveravaju kad se PUBLIC lista pregleda periodično — ovaj alat hvata
najčešći i najopasniji obrazac (direktan API poziv zaboravljen bez gejta),
ne tvrdi 100% pokrivenost.

Upotreba:
    python scripts/audit_permissions.py            # pun izveštaj
    python scripts/audit_permissions.py --ci        # samo exit kod, tiho osim MISSING liste

Exit kod: 1 ako postoji bar jedan MISSING endpoint, inače 0. Namenjen za
pre-deploy gate.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}
ROUTER_RECEIVERS = {"router", "app"}

# Endpoints deliberately NOT gated by PermissionService, with the reason on
# record. Every entry here must be justified — this is an explicit exception
# list, not a way to silence the audit. (method, full_path) -> reason.
KNOWN_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("GET", "/api/portal/predmet"): (
        "Klijentski portal — pristup kontrolisan vremenskim tokenom "
        "(secrets.token_urlsafe(32), routers/saradnja.py), ne korisničkom "
        "sesijom. Rate limit je defense-in-depth, ne primarna zaštita. "
        "Namerno bez tier/kredit gejta — portal klijent nema Vindex nalog."
    ),
}


def _dotted(node: ast.AST) -> str:
    """Renders an Attribute/Name/Call chain like a.b.c() as 'a.b.c'."""
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _router_prefix(tree: ast.Module) -> str:
    """Finds `router = APIRouter(prefix="...")` at module level, if any."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _dotted(node.value.func) != "APIRouter":
                continue
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return ""


def _route_decorator(func: ast.FunctionDef) -> tuple[str, str] | None:
    """Returns (method, path) if func has a @router.get/post/.../@app.get/... decorator."""
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        if not isinstance(dec.func, ast.Attribute):
            continue
        receiver = dec.func.value
        if not isinstance(receiver, ast.Name) or receiver.id not in ROUTER_RECEIVERS:
            continue
        method = dec.func.attr
        if method not in ROUTE_METHODS:
            continue
        if not dec.args or not isinstance(dec.args[0], ast.Constant):
            continue
        return method.upper(), dec.args[0].value
    return None


def _feature_key_from_require_call(call: ast.Call) -> str | None:
    """Given a Call node that IS a PermissionService.require(...) call, extracts
    its feature_key literal ("" if dynamic/non-literal)."""
    if call.args and isinstance(call.args[0], ast.Constant):
        return call.args[0].value
    return ""


def _permission_feature_key(func: ast.FunctionDef) -> str | None:
    """Detects PermissionService gating in TWO forms used across this codebase:

    1. Depends() form (the common case):
         user: dict = Depends(PermissionService.require("feature_key"))

    2. Manual-invocation form — used by endpoints that authenticate via a raw
       Authorization header instead of FastAPI's Depends() (multipart uploads,
       endpoints needing a non-dict user object first): the dependency callable
       is invoked directly against an already-built user dict, e.g.
         await PermissionService.require("feature_key")(user=_entitlement_user)
         user = await PermissionService.require("feature_key")(user)
       Both forms are equally valid gates — only the wiring mechanism differs.

    Returns the feature_key literal if found, "" if dynamic/non-literal,
    None if not gated at all."""
    all_defaults = list(func.args.defaults) + list(func.args.kw_defaults or [])
    for default in all_defaults:
        if default is None or not isinstance(default, ast.Call):
            continue
        if _dotted(default.func) != "Depends":
            continue
        if not default.args or not isinstance(default.args[0], ast.Call):
            continue
        inner = default.args[0]
        if _dotted(inner.func) == "PermissionService.require":
            return _feature_key_from_require_call(inner)

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        # node is the OUTER call: PermissionService.require("x")(...) — its
        # .func is itself the PermissionService.require("x") Call node.
        if not isinstance(node.func, ast.Call):
            continue
        if _dotted(node.func.func) == "PermissionService.require":
            return _feature_key_from_require_call(node.func)

    return None


def _body_flags(func: ast.FunctionDef) -> tuple[bool, bool, bool]:
    """Walks the whole function body (including nested defs, e.g. SSE generators)
    for: uses_usage_service, calls_ai, is_founder_only."""
    uses_usage = calls_ai = is_admin = False
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted == "UsageService.consume":
                uses_usage = True
            if dotted.endswith("chat.completions.create"):
                calls_ai = True
            if dotted in ("OpenAI", "AsyncOpenAI"):
                calls_ai = True
            if dotted in ("_require_founder", "_is_founder"):
                is_admin = True
    return uses_usage, calls_ai, is_admin


def _scan_file(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        print(f"[SKIP] {path}: parse error — {e}", file=sys.stderr)
        return []

    prefix = _router_prefix(tree)
    results = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) and not isinstance(node, ast.FunctionDef):
            continue
        route = _route_decorator(node)
        if route is None:
            continue
        method, route_path = route
        full_path = (prefix or "") + route_path

        feature_key = _permission_feature_key(node)
        uses_usage, calls_ai, is_admin = _body_flags(node)

        exception_reason = KNOWN_EXCEPTIONS.get((method, full_path))

        if feature_key is not None:
            bucket = "PERMISSION_GATED"
        elif exception_reason:
            bucket = "EXCEPTION"
        elif is_admin:
            bucket = "ADMIN"
        elif calls_ai:
            bucket = "MISSING"
        else:
            bucket = "PUBLIC"

        results.append({
            "file": str(path.relative_to(ROOT)),
            "line": node.lineno,
            "method": method,
            "path": full_path,
            "func": node.name,
            "bucket": bucket,
            "feature_key": feature_key or None,
            "uses_usage_service": uses_usage,
            "exception_reason": exception_reason,
        })

    return results


def main() -> int:
    quiet = "--ci" in sys.argv

    files = [ROOT / "api.py", ROOT / "klijenti" / "router.py"]
    files += sorted((ROOT / "routers").glob("*.py"))

    all_results: list[dict] = []
    for f in files:
        if f.exists():
            all_results.extend(_scan_file(f))

    buckets: dict[str, list[dict]] = {"PERMISSION_GATED": [], "ADMIN": [], "MISSING": [], "PUBLIC": [], "EXCEPTION": []}
    for r in all_results:
        buckets[r["bucket"]].append(r)

    gated_with_usage = sum(1 for r in buckets["PERMISSION_GATED"] if r["uses_usage_service"])
    gated_without_usage = [r for r in buckets["PERMISSION_GATED"] if not r["uses_usage_service"]]

    if not quiet:
        print("=" * 78)
        print("ENDPOINT COVERAGE AUDIT")
        print("=" * 78)
        print(f"  Ukupno endpointa:        {len(all_results)}")
        print(f"  PermissionService:       {len(buckets['PERMISSION_GATED'])}")
        print(f"    └─ + UsageService:     {gated_with_usage}")
        print(f"    └─ bez UsageService:   {len(gated_without_usage)}  (validno ako je krediti=0, npr. read-only CRUD funkcije)")
        print(f"  Admin (founder-only):    {len(buckets['ADMIN'])}")
        print(f"  Public (bez AI poziva):  {len(buckets['PUBLIC'])}")
        print(f"  Exception (na spisku):   {len(buckets['EXCEPTION'])}")
        print(f"  MISSING (AI bez gejta):  {len(buckets['MISSING'])}")
        print()

    if buckets["EXCEPTION"] and not quiet:
        print("─" * 78)
        print("EXCEPTION — namerno bez gejta, razlog na spisku (KNOWN_EXCEPTIONS):")
        print("─" * 78)
        for r in buckets["EXCEPTION"]:
            print(f"  {r['method']:6s} {r['path']:45s} {r['file']}:{r['line']} ({r['func']})")
            print(f"         └─ {r['exception_reason']}")
        print()

    if buckets["MISSING"]:
        print("─" * 78)
        print("MISSING PERMISSION — poziva AI bez PermissionService gejta:")
        print("─" * 78)
        for r in buckets["MISSING"]:
            print(f"  {r['method']:6s} {r['path']:45s} {r['file']}:{r['line']} ({r['func']})")
        print()

    dynamic_gated = [r for r in buckets["PERMISSION_GATED"] if r["feature_key"] == ""]
    if dynamic_gated and not quiet:
        print("─" * 78)
        print("Dinamički feature_key (nije string literal — proveri ručno):")
        print("─" * 78)
        for r in dynamic_gated:
            print(f"  {r['method']:6s} {r['path']:45s} {r['file']}:{r['line']} ({r['func']})")
        print()

    if buckets["MISSING"]:
        print(f"[FAIL] {len(buckets['MISSING'])} endpoint(a) poziva AI bez gejta. Ne sme u produkciju bez provere.")
        return 1

    if not quiet:
        print("[OK] Nema endpointa koji poziva AI bez PermissionService gejta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
