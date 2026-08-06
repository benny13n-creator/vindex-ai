# -*- coding: utf-8 -*-
"""
Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
Trigger Engine.

Regression guard for the schema-vs-code drift found this sprint:
migrations/009_notifications_analytics.sql originally declared
`notifications.prioritet CHECK (prioritet IN ('hitan','normalan','info'))`,
but routers/notifications.py::NOTIF_TIPOVI (the table every insert reads
its own priority from) has always used a DIFFERENT 5-value vocabulary
('urgent'/'high'/'normal'/'low'/'info') -- meaning most notification
types would have violated the DB CHECK constraint and silently failed to
insert. migrations/100_notifications_priority_alignment.sql fixes the
constraint. This test proves the two stay in sync going forward: every
value NOTIF_TIPOVI can possibly write must be inside the migration's own
allowed set, parsed directly from the migration file (not hand-copied),
so a future NOTIF_TIPOVI edit that adds a 6th vocabulary word would fail
this test instead of silently reintroducing the same drift.
"""
import re
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _migration_100_allowed_values() -> set[str]:
    path = os.path.join(ROOT, "migrations", "100_notifications_priority_alignment.sql")
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    # Parse the second (re-added) CHECK's own IN (...) list -- the first
    # DROP CONSTRAINT statement doesn't have one.
    m = re.search(r"ADD CONSTRAINT notifications_prioritet_check\s+CHECK \(prioritet IN \(([^)]+)\)\)", sql)
    assert m, "could not find the new CHECK constraint's own value list in migration 100"
    return {v.strip().strip("'") for v in m.group(1).split(",")}


def test_migration_100_allows_every_value_notif_tipovi_can_write():
    from routers.notifications import NOTIF_TIPOVI
    allowed = _migration_100_allowed_values()
    used = {info["priority"] for info in NOTIF_TIPOVI.values()}
    missing = used - allowed
    assert not missing, f"NOTIF_TIPOVI writes {missing!r}, not allowed by migration 100's own CHECK constraint"


def test_migration_100_allowed_values_match_canonical_notifications_vocabulary():
    """The migration's own allowed set should be exactly the canonical
    model's own NOTIFICATIONS_TO_CANONICAL key domain -- not a superset
    that quietly re-permits the old, now-dead 'hitan'/'normalan' words."""
    from shared.attention_priority import NOTIFICATIONS_TO_CANONICAL
    allowed = _migration_100_allowed_values()
    assert allowed == set(NOTIFICATIONS_TO_CANONICAL.keys())


def test_old_serbian_priority_words_are_no_longer_written_anywhere():
    """'hitan'/'normalan' (the OLD constraint's own values) must not be
    literal priority values anywhere in NOTIF_TIPOVI or the default —
    proving the drift is actually gone from the write side, not just
    permitted by a widened constraint."""
    from routers.notifications import NOTIF_TIPOVI
    used = {info["priority"] for info in NOTIF_TIPOVI.values()}
    assert "hitan" not in used
    assert "normalan" not in used
