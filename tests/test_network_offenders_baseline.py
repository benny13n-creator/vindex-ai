# -*- coding: utf-8 -*-
"""
Keeps tests/network_offenders_baseline.txt honest.

A baseline that is never checked becomes a list of tests nobody has any more,
and then it silently re-permits whatever happens to be renamed into one of
those slots. These two tests make the file self-maintaining: entries must
correspond to real tests, and the count may not grow without someone editing
this number on purpose.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "tests" / "network_offenders_baseline.txt"

# Recorded 2026-08-08. This number must only ever go DOWN. Lowering it is the
# whole point; raising it means a new test started calling a paid API for real.
MAX_ALLOWED = 53


def _entries():
    return [
        ln.strip() for ln in BASELINE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def test_baseline_has_not_grown():
    n = len(_entries())
    assert n <= MAX_ALLOWED, (
        f"{n} tests now call a paid API for real, up from {MAX_ALLOWED}. "
        "Mock the client in the new test instead of adding it to the baseline."
    )


def test_every_baseline_entry_still_exists():
    """Stale entries are worse than useless -- they keep a hole open for a test
    that no longer exists, and would silently cover any future test that lands
    on the same node id."""
    entries = _entries()
    assert entries, "the baseline should not be empty while offenders remain"

    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    ).stdout
    collected = {ln.strip().replace("\\", "/") for ln in out.splitlines() if "::" in ln}

    missing = [e for e in entries if e not in collected]
    assert not missing, (
        "these baseline entries no longer name a real test — delete them:\n  "
        + "\n  ".join(missing)
    )
