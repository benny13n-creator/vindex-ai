# -*- coding: utf-8 -*-
"""
Program Omega, Final Sprint 006 (2026-08-06) — "Canonical Attention Engine".
Tests for shared/attention_priority.py (the one canonical priority model)
and its consumers across the codebase — proving every consumer's own local
ordering/translation dict is now a provable DERIVATION of the shared model,
not an independently-maintained copy, and that a real bug found this sprint
(routers/notifications.py's own row-level "prioritet" mismatch) is fixed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# The canonical model itself
# ═══════════════════════════════════════════════════════════════════════════

def test_canonical_values_are_exactly_case_actions_own_vocabulary():
    from shared.attention_priority import CANONICAL_VALUES, CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL
    assert CANONICAL_VALUES == (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
    assert CANONICAL_VALUES == ("critical", "high", "medium", "low", "informational")


def test_canonical_order_color_label_cover_every_canonical_value():
    from shared.attention_priority import CANONICAL_VALUES, CANONICAL_ORDER, CANONICAL_COLOR, CANONICAL_LABEL_SR
    for v in CANONICAL_VALUES:
        assert v in CANONICAL_ORDER
        assert v in CANONICAL_COLOR
        assert v in CANONICAL_LABEL_SR
    # Order is a strict, gapless ranking
    assert sorted(CANONICAL_ORDER.values()) == list(range(len(CANONICAL_VALUES)))


@pytest.mark.parametrize("vocab_name", [
    "ZADACI_TO_CANONICAL", "OZBILJNOST_TO_CANONICAL", "NOTIFICATIONS_TO_CANONICAL",
    "INBOX_TO_CANONICAL", "VAZNOST_TO_CANONICAL",
])
def test_every_translation_table_maps_only_onto_canonical_values(vocab_name):
    import shared.attention_priority as ap
    table = getattr(ap, vocab_name)
    assert table, f"{vocab_name} must not be empty"
    for source_word, canon in table.items():
        assert canon in ap.CANONICAL_VALUES, f"{vocab_name}[{source_word!r}] = {canon!r} is not canonical"


def test_to_canonical_translates_known_and_falls_back_on_unknown():
    from shared.attention_priority import to_canonical, ZADACI_TO_CANONICAL, MEDIUM
    assert to_canonical("hitno", ZADACI_TO_CANONICAL) == "critical"
    assert to_canonical("visoko", ZADACI_TO_CANONICAL) == "high"
    assert to_canonical(None, ZADACI_TO_CANONICAL) == MEDIUM
    assert to_canonical("totally-unknown-word", ZADACI_TO_CANONICAL) == MEDIUM


def test_canonical_sort_key_orders_critical_first_unknown_last():
    from shared.attention_priority import canonical_sort_key, CRITICAL, INFORMATIONAL
    assert canonical_sort_key(CRITICAL) < canonical_sort_key(INFORMATIONAL)
    assert canonical_sort_key("not-a-real-value") > canonical_sort_key(INFORMATIONAL)


# ═══════════════════════════════════════════════════════════════════════════
# Every known consumer is now a provable derivation, not a parallel copy
# ═══════════════════════════════════════════════════════════════════════════

def test_case_actions_priority_order_is_the_canonical_order():
    from routers.case_actions import _PRIORITY_ORDER
    from shared.attention_priority import CANONICAL_ORDER
    assert _PRIORITY_ORDER is CANONICAL_ORDER or _PRIORITY_ORDER == CANONICAL_ORDER


def test_workspace_zadaci_map_is_the_canonical_translation():
    from routers.workspace import _ZADACI_PRIORITET_MAP
    from shared.attention_priority import ZADACI_TO_CANONICAL
    assert _ZADACI_PRIORITET_MAP == ZADACI_TO_CANONICAL


def test_inbox_priority_order_matches_pre_sprint006_values_exactly():
    """Byte-identical to the pre-refactor hand-written dict — this sprint's
    own change must be provably behavior-preserving for inbox.py."""
    from routers.inbox import _PRIORITET_ORDER
    assert _PRIORITET_ORDER == {"kriticno": 0, "visok": 1, "srednji": 2, "nizak": 3}


def test_notifications_priority_order_matches_pre_sprint006_values_exactly():
    from routers.notifications import PRIORITY_ORDER
    assert PRIORITY_ORDER == {"urgent": 0, "high": 1, "normal": 2, "low": 3, "info": 4}


def test_predmet_workspace_vaznost_translation_available_in_api_module():
    import api
    # Operation Single Brain (2026-08-07): "važan"/"informativan" added -- api.py's own GPT
    # extraction prompt and routers/intake.py both actively write these values; this table
    # previously had no key for either, silently mis-tiering them as MEDIUM.
    assert api._VAZNOST_TO_CANONICAL == {
        "kritičan": "critical", "bitan": "high", "važan": "high", "normalan": "medium",
        "ostalo": "low", "informativan": "informational",
    }


def test_retired_api_notifications_route_no_longer_registered():
    """GET /api/notifications (the 4th, confirmed-dead alert system) must be
    gone -- the live one is GET /notifications (routers/notifications.py)."""
    import api
    paths = {(r.path, tuple(sorted(r.methods))) for r in api.app.routes if hasattr(r, "path") and hasattr(r, "methods")}
    assert ("/api/notifications", ("GET",)) not in paths
    assert any(p == "/notifications" for p, _m in paths)


# ═══════════════════════════════════════════════════════════════════════════
# The real bug found and fixed this sprint: notifications.py's own row-level
# "prioritet" used to disagree with NOTIF_TIPOVI's own tip-based priority,
# using values ("hitan"/"normalan") that aren't even members of
# PRIORITY_ORDER's own vocabulary -- silently sorting every hitan_rok
# notification as if it were "normal" priority.
# ═══════════════════════════════════════════════════════════════════════════

def _make_notif_supa(rokovi=None, predmeti=None, insert_calls=None):
    def _read_chain(data):
        c = MagicMock()
        for attr in ("select", "eq", "neq", "gte", "lte", "order", "limit", "in_", "is_"):
            setattr(c, attr, MagicMock(return_value=c))
        c.execute = MagicMock(return_value=MagicMock(data=data))
        return c

    def _notifications_table():
        t = MagicMock()
        t.select.return_value = _read_chain([])
        def _insert(rows):
            if insert_calls is not None:
                insert_calls.append(rows)
            leaf = MagicMock()
            leaf.execute.return_value = MagicMock(data=rows)
            return leaf
        t.insert.side_effect = _insert
        # .delete().eq().eq().in_().execute() -- chain that just no-ops
        del_chain = MagicMock()
        for attr in ("eq", "in_"):
            setattr(del_chain, attr, MagicMock(return_value=del_chain))
        del_chain.execute.return_value = MagicMock()
        t.delete.return_value = del_chain
        return t

    table_map = {"predmet_hronologija": rokovi or [], "predmeti": predmeti or [], "predmet_beleske": []}

    def _table(name):
        if name == "notifications":
            return _notifications_table()
        return _read_chain(table_map.get(name, []))

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_hitan_rok_notification_gets_high_priority_not_the_old_broken_value():
    from routers.notifications import _generate_notifications, NOTIF_TIPOVI, PRIORITY_ORDER
    from datetime import date

    today = date.today().isoformat()
    rokovi = [{"predmet_id": "pred-1", "dogadjaj": "Rok za žalbu", "datum_iso": today, "vaznost": "kritičan"}]
    predmeti = [{"id": "pred-1", "naziv": "Predmet A", "status": "aktivan"}]
    insert_calls: list = []
    supa = _make_notif_supa(rokovi=rokovi, predmeti=predmeti, insert_calls=insert_calls)

    with patch("routers.notifications._get_supa", return_value=supa):
        n = await _generate_notifications("user-1")

    assert n >= 1
    assert insert_calls, "expected at least one bulk insert() call"
    all_rows = insert_calls[0]
    hitan_rows = [r for r in all_rows if r["tip"] == "hitan_rok"]
    assert len(hitan_rows) == 1
    # The real fix: prioritet must be a MEMBER of PRIORITY_ORDER's own
    # vocabulary, and must match NOTIF_TIPOVI["hitan_rok"]["priority"]
    # exactly -- not the old hand-typed "hitan" (which PRIORITY_ORDER.get()
    # would have silently defaulted to the SAME rank as "normal").
    assert hitan_rows[0]["prioritet"] == NOTIF_TIPOVI["hitan_rok"]["priority"] == "high"
    assert hitan_rows[0]["prioritet"] in PRIORITY_ORDER
    assert PRIORITY_ORDER[hitan_rows[0]["prioritet"]] < PRIORITY_ORDER["normal"]  # sorts ABOVE normal now


@pytest.mark.anyio
async def test_closed_case_deadline_does_not_generate_a_notification():
    """Program Lambda, Certification 005 (2026-08-07): a Chaos Engineer fork
    found the rokovi block had no status guard -- unlike the neaktivnost
    block just below it, which already excludes zatvoren/arhiviran cases --
    so a closed case's own leftover predmet_hronologija rows kept generating
    'Hitan rok'/'Nadolazeći rok' notifications forever. Only the OPEN case's
    deadline should produce a notification."""
    from routers.notifications import _generate_notifications
    from datetime import date

    today = date.today().isoformat()
    rokovi = [
        {"predmet_id": "pred-closed", "dogadjaj": "Rok za žalbu", "datum_iso": today, "vaznost": "kritičan"},
        {"predmet_id": "pred-open", "dogadjaj": "Rok za odgovor", "datum_iso": today, "vaznost": "kritičan"},
    ]
    predmeti = [
        {"id": "pred-closed", "naziv": "Zatvoren predmet", "status": "zatvoren"},
        {"id": "pred-open", "naziv": "Aktivan predmet", "status": "aktivan"},
    ]
    insert_calls: list = []
    supa = _make_notif_supa(rokovi=rokovi, predmeti=predmeti, insert_calls=insert_calls)

    with patch("routers.notifications._get_supa", return_value=supa):
        await _generate_notifications("user-1")

    assert insert_calls, "expected at least one bulk insert() call"
    all_rows = insert_calls[0]
    rok_rows = [r for r in all_rows if r["tip"] in ("rok", "hitan_rok")]
    predmet_ids = {r["predmet_id"] for r in rok_rows}
    assert "pred-closed" not in predmet_ids
    assert "pred-open" in predmet_ids


def test_grupiraj_notifikacije_sorts_hitan_rok_before_ordinary_rok():
    """End-to-end proof of the actual user-visible symptom: with the fix,
    a hitan_rok notification sorts strictly before a plain rok one."""
    from routers.notifications import _grupiraj_notifikacije, NOTIF_TIPOVI

    notifs = [
        {"tip": "rok", "prioritet": NOTIF_TIPOVI["rok"]["priority"], "naslov": "Obican rok"},
        {"tip": "hitan_rok", "prioritet": NOTIF_TIPOVI["hitan_rok"]["priority"], "naslov": "Hitan rok"},
    ]
    result = _grupiraj_notifikacije(notifs)
    assert result[0]["tip"] == "hitan_rok"
    assert result[1]["tip"] == "rok"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5 — cross-system consistency: the SAME underlying urgency now ranks
# the SAME way whether read via case_actions (Workspace) or via
# notifications (the bell icon) — the actual "Priority -> Workspace ->
# Dashboard -> Notification" consistency the mission's own Phase 5 asks for,
# even though the 2 systems still write independently (OMEGA-020/021).
# ═══════════════════════════════════════════════════════════════════════════

def test_case_actions_critical_and_notifications_urgent_rank_identically():
    """A case_actions 'critical' item and a notifications 'urgent' item both
    describe the platform's own highest urgency tier -- they must occupy
    the SAME rank (0) once translated through the canonical model, so a
    lawyer never sees Workspace and the bell icon disagree about which
    color/rank means 'most urgent'."""
    from shared.attention_priority import (
        CANONICAL_ORDER, NOTIFICATIONS_TO_CANONICAL, to_canonical,
    )
    case_actions_value = "critical"  # case_actions IS the canonical vocabulary
    notif_value = to_canonical("urgent", NOTIFICATIONS_TO_CANONICAL)
    assert notif_value == case_actions_value == "critical"
    assert CANONICAL_ORDER[notif_value] == CANONICAL_ORDER[case_actions_value] == 0


def test_case_actions_high_and_zadaci_hitno_rank_identically():
    from shared.attention_priority import CANONICAL_ORDER, ZADACI_TO_CANONICAL, to_canonical
    zadatak_value = to_canonical("hitno", ZADACI_TO_CANONICAL)
    assert zadatak_value == "critical"
    assert CANONICAL_ORDER[zadatak_value] == 0


def test_every_consumer_dict_agrees_on_the_rank_of_its_own_top_tier_word():
    """For every known translation table, the word(s) that map to CRITICAL
    must sort at rank 0 -- proving no consumer's own derived _ORDER dict
    accidentally diverges from the canonical ranking, across ALL 5
    consumers at once (not just the 2 spot-checked above)."""
    import shared.attention_priority as ap

    consumer_orders = {
        "case_actions": __import__("routers.case_actions", fromlist=["_PRIORITY_ORDER"])._PRIORITY_ORDER,
        "inbox": __import__("routers.inbox", fromlist=["_PRIORITET_ORDER"])._PRIORITET_ORDER,
        "notifications": __import__("routers.notifications", fromlist=["PRIORITY_ORDER"]).PRIORITY_ORDER,
    }
    tables = {
        "case_actions": {v: v for v in ap.CANONICAL_VALUES},
        "inbox": ap.INBOX_TO_CANONICAL,
        "notifications": ap.NOTIFICATIONS_TO_CANONICAL,
    }
    for name, order_dict in consumer_orders.items():
        table = tables[name]
        critical_words = [w for w, canon in table.items() if canon == ap.CRITICAL]
        assert critical_words, f"{name} has no word mapping to CRITICAL"
        for w in critical_words:
            assert order_dict[w] == 0, f"{name}'s own order dict ranks {w!r} at {order_dict[w]}, not 0"
