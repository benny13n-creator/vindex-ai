# -*- coding: utf-8 -*-
"""
Vindex AI — Dead Feature Detector (Faza 70.6)

Poredi feature_key vrednosti referencirane u kodu (PermissionService.require(...),
UsageService.consume(...)/.refund(...)) sa redovima koji STVARNO postoje u
feature_registry tabeli (živa baza — Admin Feature Console menja bazu direktno,
bez novih migracija, pa migracioni fajlovi NISU pouzdan izvor istine za ovo).

Dva pravca:
  ORPHAN  — kod referencira feature_key koji ne postoji u registru.
            PermissionService.require()/UsageService.consume() bi bacili
            RuntimeError na prvi poziv (shared/feature_registry.py:get_policy).
            FATAL — build/deploy mora da padne.
  DEAD    — registar ima feature_key koji kod nigde ne referencira.
            Nije opasno (samo neiskorišćen red), ali je čišćenje. WARNING,
            ne blokira.

Upotreba:
    python scripts/audit_dead_features.py

Exit kod: 1 ako postoji bar jedan ORPHAN, inače 0.
"""
from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(dotenv_path=ROOT / ".env")

# feature_key referenced dynamically (not a string literal) at these call sites —
# static analysis can't resolve them, so they're excluded from the ORPHAN check
# by design rather than silently mis-flagged. Every entry needs a reason.
DYNAMIC_CALL_SITES: set[str] = set()


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _collect_code_feature_keys(path: Path) -> tuple[set[str], list[str]]:
    """Returns (feature_keys_found, dynamic_call_descriptions)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        print(f"[SKIP] {path}: parse error — {e}", file=sys.stderr)
        return set(), []

    keys: set[str] = set()
    dynamic: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Only match the .require(...)/.consume(...)/.refund(...) call itself —
        # NOT the outer invocation when PermissionService.require("x") is called
        # manually as `PermissionService.require("x")(user=...)`. _dotted()
        # unwraps through Call nodes, so without this guard the outer wrapper
        # call would also dotted-match and (having no positional args of its
        # own — the literal lives one level down) get misreported as dynamic.
        if not isinstance(node.func, ast.Attribute):
            continue
        dotted = _dotted(node.func)

        if dotted == "PermissionService.require":
            if node.args and isinstance(node.args[0], ast.Constant):
                keys.add(node.args[0].value)
            else:
                dynamic.append(f"{path.relative_to(ROOT)}:{node.lineno} PermissionService.require(<dynamic>)")

        elif dotted in ("UsageService.consume", "UsageService.refund"):
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                keys.add(node.args[2].value)
            else:
                dynamic.append(f"{path.relative_to(ROOT)}:{node.lineno} {dotted}(<dynamic feature arg>)")

    return keys, dynamic


async def _fetch_registry_keys() -> set[str]:
    from shared.feature_registry import get_all_policies
    policies = await get_all_policies()
    return {p["feature_key"] for p in policies}


def main() -> int:
    files = [ROOT / "api.py", ROOT / "klijenti" / "router.py"]
    files += sorted((ROOT / "routers").glob("*.py"))

    code_keys: set[str] = set()
    dynamic_calls: list[str] = []
    for f in files:
        if f.exists():
            keys, dyn = _collect_code_feature_keys(f)
            code_keys |= keys
            dynamic_calls += dyn

    try:
        registry_keys = asyncio.run(_fetch_registry_keys())
    except Exception as exc:
        print(f"[ERROR] Ne mogu da učitam feature_registry iz baze: {exc}", file=sys.stderr)
        print("        Proveri SUPABASE_URL/SUPABASE_SERVICE_KEY u .env — ovaj alat mora", file=sys.stderr)
        print("        da čita PRAVU bazu (Admin Console menja bazu direktno, ne migracije).", file=sys.stderr)
        return 2

    if not registry_keys:
        print("[ERROR] feature_registry tabela je prazna ili nedostupna — migracija 064 pokrenuta?", file=sys.stderr)
        return 2

    orphans = sorted(code_keys - registry_keys)
    dead = sorted(registry_keys - code_keys)

    print("=" * 78)
    print("DEAD FEATURE DETECTOR")
    print("=" * 78)
    print(f"  feature_key u kodu:      {len(code_keys)}")
    print(f"  feature_key u registru:  {len(registry_keys)}")
    print(f"  ORPHAN (kod → nema u registru):  {len(orphans)}")
    print(f"  DEAD   (registar → nema u kodu): {len(dead)}")
    print()

    if dynamic_calls:
        print("─" * 78)
        print("Dinamički pozivi (feature_key nije string literal — proveri ručno):")
        print("─" * 78)
        for d in dynamic_calls:
            print(f"  {d}")
        print()

    if orphans:
        print("─" * 78)
        print("ORPHAN — kod referencira feature_key koji NE postoji u feature_registry:")
        print("        (PermissionService/UsageService bi bacili RuntimeError na prvi poziv)")
        print("─" * 78)
        for key in orphans:
            print(f"  {key}")
        print()

    if dead:
        print("─" * 78)
        print("DEAD — feature_registry redovi koje kod nigde ne referencira (razmotri brisanje):")
        print("─" * 78)
        for key in dead:
            print(f"  {key}")
        print()

    if orphans:
        print(f"[FAIL] {len(orphans)} orphan feature_key(eva). Deploy mora da padne dok se ne reši.")
        return 1

    print("[OK] Svaki feature_key iz koda postoji u feature_registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
