# -*- coding: utf-8 -*-
"""
PROD-SYNTAX-001 — production runs a DIFFERENT Python than local development.

    Dockerfile:      FROM python:3.11-slim
    runtime.txt:     3.11
    local dev:       3.13

On 2026-08-08 production went fully down -- gunicorn workers exited 3 in a
crash loop, no HTTP port ever opened -- because
`routers/hearing_cc.py` contained:

    f"...{("\\n" + case_context_blok + "\\n...") if case_context_blok else ""}"

A backslash inside an f-string EXPRESSION is a SyntaxError on Python 3.11 and
only became legal in 3.12 (PEP 701). Local Python 3.13 parsed it happily, the
entire 3,500-test suite passed, the code was committed, pushed and deployed --
and the application could not even be IMPORTED in production.

No test could have caught this, because every test ran on the local
interpreter. The gap was never the test coverage; it was that nothing
compared local syntax against the deployment target's grammar.

These tests close that gap. They are intentionally cheap and run on every
suite execution.

NOTE ON `ast.parse(feature_version=...)`: it does NOT catch this. CPython's
f-string tokenizer changed in 3.12 and `feature_version` does not restrict it
(verified -- it reported 0 problems on the file that was actively crashing
production). Detection therefore walks the AST and inspects the SOURCE TEXT of
each f-string expression.
"""
import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_SKIP_DIRS = (
    "/.venv/", "/venv/", "/node_modules/", "/data/", "/.git/",
    "vindex_scraper_output/", "/build/", "/dist/",
)


def _project_py_files():
    for p in sorted(REPO_ROOT.rglob("*.py")):
        s = str(p).replace("\\", "/")
        if any(x in s for x in _SKIP_DIRS):
            continue
        yield p


def _fstring_exprs_with_backslash(src: str):
    """Every f-string expression whose SOURCE TEXT contains a backslash.
    Illegal on Python <= 3.11."""
    found = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return found  # a hard syntax error is caught by the other test
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for value in node.values:
            if not isinstance(value, ast.FormattedValue):
                continue
            seg = ast.get_source_segment(src, value.value)
            if seg and "\\" in seg:
                found.append((value.value.lineno, seg[:100].replace("\n", " ")))
    return found


def test_deployment_target_python_version_is_known():
    """If the deployment target changes, these tests must be revisited rather
    than silently guarding the wrong version."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.11" in dockerfile, (
        "Dockerfile no longer pins python:3.11 -- update this module's target version"
    )
    runtime = (REPO_ROOT / "runtime.txt")
    if runtime.exists():
        assert runtime.read_text(encoding="utf-8").strip().startswith("3.11")


def test_no_backslash_inside_fstring_expressions():
    """The exact defect that took production down. Legal on 3.12+, fatal on 3.11."""
    offenders = []
    for path in _project_py_files():
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, snippet in _fstring_exprs_with_backslash(src):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} -> {snippet}")

    assert offenders == [], (
        "Backslash inside an f-string expression is a SyntaxError on Python 3.11 "
        "(production), even though local Python 3.12+ accepts it. Hoist the "
        "expression into a variable above the f-string.\n  "
        + "\n  ".join(offenders)
    )


def test_every_module_parses():
    """Baseline: a plain syntax error anywhere means production cannot import."""
    broken = []
    for path in _project_py_files():
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            broken.append(f"{path.relative_to(REPO_ROOT)}:{exc.lineno} {exc.msg}")
    assert broken == [], "syntax errors present:\n  " + "\n  ".join(broken)


def test_no_pep695_type_parameter_syntax():
    """`def f[T](...)` / `class C[T]` / `type X = ...` are 3.12+ only and would
    fail to parse on 3.11 exactly like the f-string defect did."""
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+\w+\s*\[", re.M)
    type_alias = re.compile(r"^\s*type\s+\w+\s*=", re.M)
    offenders = []
    for path in _project_py_files():
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in list(pat.finditer(src)) + list(type_alias.finditer(src)):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{src[:m.start()].count(chr(10)) + 1}")
    assert offenders == [], (
        "PEP 695 type-parameter syntax is Python 3.12+ only; production is 3.11:\n  "
        + "\n  ".join(offenders)
    )


def test_ci_runs_a_real_production_runtime_gate():
    """The structural fix for PROD-SYNTAX-001.

    The heuristics in this module can only catch patterns someone thought to
    encode. The actual guarantee is a CI job that executes on the real
    production interpreter. This asserts that job exists and still targets
    the production image — if someone deletes it or downgrades it to
    setup-python, this fails."""
    wf = REPO_ROOT / ".github" / "workflows" / "production-runtime.yml"
    assert wf.exists(), "production-runtime.yml CI workflow is missing"
    text = wf.read_text(encoding="utf-8")

    assert text.count("container: python:3.11-slim") >= 2, (
        "the compile and import gates must run INSIDE python:3.11-slim, "
        "not on a setup-python toolchain"
    )
    assert "compileall" in text, "must byte-compile the tree on the production interpreter"
    assert "import api" in text, "must prove api:app actually imports, not merely compiles"
    assert "docker build" in text, "must also build the real production Dockerfile"
    assert "py311_incident_canary" in text, (
        "the gate must self-test against the historical incident"
    )


def test_ci_main_suite_runs_on_production_python():
    """The main pytest job must include 3.11. It ran only 3.13 when the
    incident shipped."""
    wf = (REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert '"3.11"' in wf, "the test matrix must include production's Python 3.11"


def test_incident_canary_still_contains_the_defect():
    """The canary is only useful while it still reproduces the defect. Guards
    against someone 'cleaning up' the fixture and silently neutering the CI
    gate that depends on it."""
    canary = REPO_ROOT / "tests" / "fixtures" / "py311_incident_canary.txt"
    assert canary.exists(), "CI's production-runtime gate depends on this fixture"
    text = canary.read_text(encoding="utf-8")
    assert 'f"""' in text, "canary must contain an f-string"
    assert '{("\\n" + case_context_blok' in text, (
        "canary no longer contains a backslash inside an f-string expression — "
        "it would compile on Python 3.11 and the CI gate would pass vacuously"
    )
    assert canary.suffix == ".txt", (
        "must stay .txt so compileall and the AST scanner skip it"
    )


def test_hearing_cc_cross_exam_prompt_is_hoisted():
    """Regression pin on the specific site that caused the outage."""
    src = (REPO_ROOT / "routers" / "hearing_cc.py").read_text(encoding="utf-8")
    # Comment-stripped: the explanatory note above the fix legitimately quotes
    # the old broken line, and must not trip its own regression test.
    executable = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "_ctx_prompt_blok" in executable
    assert '{("\\n" + case_context_blok' not in executable, (
        "the inline backslash f-string expression is back -- this exact line "
        "crash-looped production on 2026-08-08"
    )
