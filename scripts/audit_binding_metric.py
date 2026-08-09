# -*- coding: utf-8 -*-
"""
Strict class-1 audit SUBJECT BINDING metric.

Counts, from the AST, how many provider call sites execute inside a
shared/ai_provenance.py::case_context(...) block that supplies a predmet_id or
document_id -- i.e. how many AI operations leave a provenance row whose SUBJECT
is known.

Deliberately strict, per the Sprint 6 thesis:
  * a generic correlation_id is NOT subject binding;
  * module_name/operation_name alone is NOT subject binding (the SDK patch
    already auto-fills module_name from the caller, so counting it would
    inflate the number without improving anything);
  * comments, docstrings and dead code do not count -- everything here comes
    from parsed syntax, never from a substring search. Three separate probes in
    this investigation were fooled by text before this rule was adopted.

WHY THIS DOES NOT MEASURE LEXICAL CONTAINMENT
The first version of this script did, and returned 0/83 -- which is not the
coverage, it is the wrong instrument. In this codebase the provider call sits
inside a _pozovi_* helper in one module while the `with case_context(...)` sits
at the endpoint in another, so the call is never lexically inside the block.
Binding here is DYNAMIC: the helper runs while the contextvar is set.

So what is counted instead is the thing that actually establishes the subject --
a case_context(...) call that supplies predmet_id or document_id. That is the
endpoint declaring, on the record, which case the AI operation belongs to.
Runtime proof that the declaration survives to the provenance writer lives in
tests/test_sprint6_subject_isolation.py, which drives the real mechanism.

Usage:  python scripts/audit_binding_metric.py [--list]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DIRS = ("routers", "shared", "services", "app", "klijenti", "uploaded_doc",
        "workers", "nacrti", "drafting", "analiza", "security")
EXTRA = ("api.py", "main.py", "strategija.py", "web3_compliance.py")

PROVIDER_ATTRS = {"create"}
PROVIDER_CHAINS = (
    ("chat", "completions", "create"),
    ("completions", "create"),
    ("embeddings", "create"),
    ("transcriptions", "create"),
    ("speech", "create"),
)


def _attr_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return tuple(reversed(parts))


def _is_provider_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in PROVIDER_ATTRS:
        return False
    chain = _attr_chain(node.func)
    return any(chain[-len(c):] == c for c in PROVIDER_CHAINS if len(chain) >= len(c))


def _binds_subject(withitem_call: ast.Call) -> bool:
    """A case_context(...) call counts only if it names a SUBJECT."""
    fn = withitem_call.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
    if "case_context" not in name and name not in ("_ai_case_ctx",):
        return False
    return any(kw.arg in ("predmet_id", "document_id") and kw.value is not None
               for kw in withitem_call.keywords)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.depth = 0          # nesting depth of subject-binding `with` blocks
        self.sites: list[tuple[str, int, bool]] = []

    def _visit_with(self, node):
        binding = any(
            isinstance(it.context_expr, ast.Call) and _binds_subject(it.context_expr)
            for it in node.items
        )
        if binding:
            self.depth += 1
        self.generic_visit(node)
        if binding:
            self.depth -= 1

    visit_With = _visit_with
    visit_AsyncWith = _visit_with

    def visit_Call(self, node):
        if _is_provider_call(node):
            self.sites.append((self.path, node.lineno, self.depth > 0))
        self.generic_visit(node)


def collect() -> list[tuple[str, int, bool]]:
    files: list[Path] = []
    for d in DIRS:
        p = ROOT / d
        if p.exists():
            files += [f for f in p.rglob("*.py") if "__pycache__" not in str(f)]
    files += [ROOT / f for f in EXTRA if (ROOT / f).exists()]

    out: list[tuple[str, int, bool]] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        v = _Visitor(str(f.relative_to(ROOT)).replace("\\", "/"))
        v.visit(tree)
        out += v.sites
    return out


def main() -> int:
    import ast as _ast

    files: list[Path] = []
    for d in DIRS:
        p = ROOT / d
        if p.exists():
            files += [f for f in p.rglob("*.py") if "__pycache__" not in str(f)]
    files += [ROOT / f for f in EXTRA if (ROOT / f).exists()]

    with_subject: list[tuple[str, int]] = []
    without_subject: list[tuple[str, int]] = []

    for f in files:
        try:
            tree = _ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        for n in _ast.walk(tree):
            if not isinstance(n, _ast.Call):
                continue
            fn = n.func
            name = fn.attr if isinstance(fn, _ast.Attribute) else getattr(fn, "id", "")
            if name not in ("case_context", "_ai_case_ctx"):
                continue
            if any(k.arg in ("predmet_id", "document_id") for k in n.keywords):
                with_subject.append((rel, n.lineno))
            else:
                without_subject.append((rel, n.lineno))

    sites = collect()
    total_calls = len(sites)
    modules = sorted({p for p, _ in with_subject})

    print(f"Provider call sites (AST):            {total_calls}")
    print(f"case_context(...) declarations:       {len(with_subject) + len(without_subject)}")
    print(f"  WITH subject (predmet/document):    {len(with_subject)}  across {len(modules)} modules")
    print(f"  WITHOUT subject (module/op only):   {len(without_subject)}")

    if "--list" in sys.argv:
        print("\nSUBJECT-DECLARING SITES:")
        for rel, line in sorted(with_subject):
            print(f"  {rel}:{line}")
        print("\nDECLARATIONS WITHOUT A SUBJECT:")
        for rel, line in sorted(without_subject):
            print(f"  {rel}:{line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
