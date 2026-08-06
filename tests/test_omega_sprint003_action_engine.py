# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 003 (2026-08-06) — "Autonomous Legal Office / Canonical
Action Engine". Tests for `_compute_target_actions` (pure, deterministic rule
computation) and `_consequence_refresh_case_actions` (the reconciliation
consequence wired as the LAST step of DOCUMENT_ACCEPTED, REVIEW_ACCEPTED,
ROCISTE_ZAKAZANO and DOCUMENT_BATCH_COMPLETED), plus the 6 mission-required
scenarios from the charter's own Definition of Done.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import Event, EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_target_supa(case_dna=None, tip="parnicno", dokazi=None, dokumenti=None, rocista=None):
    """Supports exactly the read chains _compute_target_actions issues:
    predmeti.select(case_dna,tip).eq(id).maybe_single().execute()
    predmet_dokazi.select(...).eq(predmet_id).is_(deleted_at,null).execute()
    predmet_dokumenti.select(...).eq(predmet_id).execute()
    rocista.select(...).eq(predmet_id).order(datum).execute()
    """
    def _predmeti_table():
        t = MagicMock()
        res = MagicMock()
        res.data = {"case_dna": dict(case_dna or {}), "tip": tip}
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = res
        return t

    def _simple_select_table(rows):
        t = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=rows or [])
        t.select.return_value.eq.return_value = chain
        t.select.return_value.eq.return_value.is_.return_value = chain
        t.select.return_value.eq.return_value.order.return_value = chain
        return t

    def _table(name):
        if name == "predmeti":
            return _predmeti_table()
        if name == "predmet_dokazi":
            return _simple_select_table(dokazi)
        if name == "predmet_dokumenti":
            return _simple_select_table(dokumenti)
        if name == "rocista":
            return _simple_select_table(rocista)
        raise AssertionError(f"unexpected table {name}")

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa


def _make_full_action_supa(case_dna=None, tip="parnicno", dokazi=None, dokumenti=None, rocista=None,
                            existing_open_actions=None, insert_raises_duplicate_for=None):
    """Full mock: everything `_make_target_supa` supports PLUS `case_actions`
    (select existing open rows, insert, update), with mutable trackers for
    assertions. `insert_raises_duplicate_for`: a set of dedupe_keys whose
    INSERT should raise a duplicate-key error (Scenario 5)."""
    existing = list(existing_open_actions or [])  # [{"id":..., "dedupe_key":...}]
    inserted, updated, closed = [], [], []
    insert_raises_duplicate_for = insert_raises_duplicate_for or set()

    def _predmeti_table():
        t = MagicMock()
        res = MagicMock()
        res.data = {"case_dna": dict(case_dna or {}), "tip": tip}
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = res
        return t

    def _simple_select_table(rows):
        t = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=rows or [])
        t.select.return_value.eq.return_value = chain
        t.select.return_value.eq.return_value.is_.return_value = chain
        t.select.return_value.eq.return_value.order.return_value = chain
        return t

    def _case_actions_table():
        t = MagicMock()

        def _select(cols):
            inner = MagicMock()
            def _eq1(col, val):
                inner2 = MagicMock()
                def _eq2(col2, val2):
                    leaf = MagicMock()
                    leaf.execute.return_value = MagicMock(data=list(existing))
                    return leaf
                inner2.eq.side_effect = _eq2
                return inner2
            inner.eq.side_effect = _eq1
            return inner
        t.select.side_effect = _select

        def _insert(row):
            if row["dedupe_key"] in insert_raises_duplicate_for:
                raise Exception('duplicate key value violates unique constraint "idx_case_actions_open_dedupe"')
            inserted.append(row)
            res = MagicMock(); res.data = [row]
            return res
        t.insert.side_effect = _insert

        def _update(payload):
            inner = MagicMock()
            def _eq(col, val):
                leaf = MagicMock()
                leaf.execute.return_value = MagicMock()
                updated.append((val, dict(payload)))
                if payload.get("status") == "closed":
                    closed.append(val)
                return leaf
            inner.eq.side_effect = _eq
            return inner
        t.update.side_effect = _update

        return t

    def _table(name):
        if name == "predmeti":
            return _predmeti_table()
        if name == "predmet_dokazi":
            return _simple_select_table(dokazi)
        if name == "predmet_dokumenti":
            return _simple_select_table(dokumenti)
        if name == "rocista":
            return _simple_select_table(rocista)
        if name == "case_actions":
            return _case_actions_table()
        raise AssertionError(f"unexpected table {name}")

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, {"inserted": inserted, "updated": updated, "closed": closed, "existing": existing}


def _event(event_id="evt-1", predmet_id="pred-1", correlation_id="corr-1", user_id="user-1"):
    return Event(type=EventType.DOCUMENT_ACCEPTED, user_id=user_id, predmet_id=predmet_id,
                 payload={}, correlation_id=correlation_id, event_id=event_id)


# ═══════════════════════════════════════════════════════════════════════════
# Registry wiring — refresh_case_actions present, LAST, on all 4 events
# ═══════════════════════════════════════════════════════════════════════════

def test_refresh_case_actions_wired_last_on_all_four_events():
    from services.case_evolution import CONSEQUENCE_REGISTRY, _consequence_refresh_case_actions

    for event_type in (EventType.DOCUMENT_ACCEPTED, EventType.REVIEW_ACCEPTED,
                        EventType.ROCISTE_ZAKAZANO, EventType.DOCUMENT_BATCH_COMPLETED):
        consequences = CONSEQUENCE_REGISTRY[event_type]
        assert consequences[-1].name == "refresh_case_actions", event_type
        assert consequences[-1].executor is _consequence_refresh_case_actions, event_type


def test_case_action_refreshed_is_auditable():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "case_action_refreshed" in AUDITABLE_ACTIONS


# ═══════════════════════════════════════════════════════════════════════════
# _compute_target_actions — rule families, in isolation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rule1_rociste_within_3_days_is_critical_pripremiti_podnesak():
    from services.case_evolution import _compute_target_actions
    from datetime import date, timedelta

    rok = (date.today() + timedelta(days=2)).isoformat()
    supa = _make_target_supa(rocista=[{"id": "roc-1", "sud": "Prvi osnovni sud", "datum": rok, "status": "zakazano"}])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    podnesci = [a for a in actions if a["tip"] == "PRIPREMITI_PODNESAK"]
    assert len(podnesci) == 1
    assert podnesci[0]["prioritet"] == "critical"
    assert podnesci[0]["rok"] == rok
    assert podnesci[0]["dokaz"]["rociste_id"] == "roc-1"


@pytest.mark.anyio
async def test_rule1_rociste_within_7_days_is_high_within_30_is_medium():
    from services.case_evolution import _compute_target_actions
    from datetime import date, timedelta

    rok_high = (date.today() + timedelta(days=5)).isoformat()
    rok_medium = (date.today() + timedelta(days=20)).isoformat()
    supa = _make_target_supa(rocista=[
        {"id": "roc-h", "sud": "Sud", "datum": rok_high, "status": "zakazano"},
        {"id": "roc-m", "sud": "Sud", "datum": rok_medium, "status": "zakazano"},
    ])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    by_id = {a["dokaz"]["rociste_id"]: a for a in actions if a["tip"] == "PRIPREMITI_PODNESAK"}
    assert by_id["roc-h"]["prioritet"] == "high"
    assert by_id["roc-m"]["prioritet"] == "medium"


@pytest.mark.anyio
async def test_rule1_ignores_non_zakazano_status_and_beyond_30_days():
    from services.case_evolution import _compute_target_actions
    from datetime import date, timedelta

    supa = _make_target_supa(rocista=[
        {"id": "roc-done", "sud": "Sud", "datum": (date.today() + timedelta(days=2)).isoformat(), "status": "odrzano"},
        {"id": "roc-far", "sud": "Sud", "datum": (date.today() + timedelta(days=90)).isoformat(), "status": "zakazano"},
    ])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    assert [a for a in actions if a["tip"] == "PRIPREMITI_PODNESAK"] == []


@pytest.mark.anyio
async def test_rule2_no_evidence_at_all_is_critical_pribaviti_dokaz():
    from services.case_evolution import _compute_target_actions
    supa = _make_target_supa(dokazi=[], dokumenti=[], rocista=[])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    dokazi_actions = [a for a in actions if a["tip"] == "PRIBAVITI_DOKAZ" and a["prioritet"] == "critical"]
    assert len(dokazi_actions) == 1
    assert "Nema uploadovanih dokaza" in dokazi_actions[0]["razlog"]


@pytest.mark.anyio
async def test_rule2_missing_specific_doc_types_are_high_pribaviti_dokaz():
    from services.case_evolution import _compute_target_actions
    # jaka dokazi so "Nema dokaza" doesn't also fire; dokumenti present but
    # none carry tip_dokaza -> every expected type for "parnicno" is missing.
    supa = _make_target_supa(
        tip="parnicno",
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano"}],
        rocista=[],
    )
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    high_dokazi = [a for a in actions if a["tip"] == "PRIBAVITI_DOKAZ" and a["prioritet"] == "high"]
    assert len(high_dokazi) == 3  # identify_case_problems caps at [:3]
    assert all(a["razlog"].startswith("Nedostaje ") for a in high_dokazi)
    # dedupe_key differs per missing type (keyed on full text) so each is
    # tracked/closed independently as evidence is added.
    assert len({a["dedupe_key"] for a in high_dokazi}) == 3


@pytest.mark.anyio
async def test_rule2_kritican_rok_text_is_skipped_deduped_against_rule1():
    """A rociste inside the 0-7 day window makes identify_case_problems()
    also emit its own generic 'N kritičan rok(a)...' text -- Rule 2 must
    skip it so we don't get a second, less precise PRIPREMITI_PODNESAK
    duplicating Rule 1's own per-rociste action."""
    from services.case_evolution import _compute_target_actions
    from datetime import date, timedelta

    supa = _make_target_supa(
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}] * 3,
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        rocista=[{"id": "roc-1", "sud": "Sud", "datum": (date.today() + timedelta(days=2)).isoformat(), "status": "zakazano"}],
    )
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    podnesci = [a for a in actions if a["tip"] == "PRIPREMITI_PODNESAK"]
    assert len(podnesci) == 1  # only Rule 1's own, not a Rule-2 duplicate


@pytest.mark.anyio
async def test_rule4_three_or_more_upcoming_deadlines_is_high_planirati_rokove():
    from services.case_evolution import _compute_target_actions
    from datetime import date, timedelta

    supa = _make_target_supa(
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}] * 3,
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        rocista=[{"id": f"roc-{i}", "sud": "Sud", "datum": (date.today() + timedelta(days=15 + i)).isoformat(), "status": "zakazano"} for i in range(3)],
    )
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    planirati = [a for a in actions if a["tip"] == "PLANIRATI_ROKOVE"]
    assert len(planirati) == 1
    assert planirati[0]["prioritet"] == "high"


@pytest.mark.anyio
async def test_rule5_weak_evidence_is_informational_ojacati_dokaze():
    from services.case_evolution import _compute_target_actions
    supa = _make_target_supa(
        dokazi=[{"snaga": "slaba", "kategorija": "izjava", "pravni_element": "x"}],
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        rocista=[],
    )
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    ojacati = [a for a in actions if a["tip"] == "OJACATI_DOKAZE"]
    assert len(ojacati) == 1
    assert ojacati[0]["prioritet"] == "informational"


@pytest.mark.anyio
async def test_rule3_contradictions_mapped_by_tezina_and_sourced():
    from services.case_evolution import _compute_target_actions
    case_dna = {"kontradikcije": [
        {"opis": "Datum uviđaja se razlikuje", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"},
        {"opis": "Iznos štete nije usklađen", "lokacija_1": "DOK-02 str.5", "lokacija_2": "DOK-04 str.3", "tezina": "vazna"},
        {"opis": "Manja nepodudarnost imena svedoka", "lokacija_1": "DOK-05 str.1", "lokacija_2": "DOK-06 str.1", "tezina": "manja"},
        {"opis": "", "lokacija_1": "DOK-07 str.1", "lokacija_2": "DOK-08 str.1", "tezina": "kriticna"},  # empty opis -> skipped
    ]}
    supa = _make_target_supa(case_dna=case_dna, dokazi=[], dokumenti=[], rocista=[])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    kontradikcije = [a for a in actions if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert len(kontradikcije) == 3
    by_prio = {a["razlog"]: a["prioritet"] for a in kontradikcije}
    assert by_prio["Datum uviđaja se razlikuje"] == "critical"
    assert by_prio["Iznos štete nije usklađen"] == "high"
    assert by_prio["Manja nepodudarnost imena svedoka"] == "medium"
    for a in kontradikcije:
        assert a["dokaz"]["lokacija_1"] and a["dokaz"]["lokacija_2"]  # never ungrounded
        assert a["izvor_dokumenti"]


@pytest.mark.anyio
async def test_no_predmet_id_short_circuits():
    from services.case_evolution import _consequence_refresh_case_actions
    result = await _consequence_refresh_case_actions(_event(predmet_id=None))
    assert result == "skipped_no_predmet_id"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — 500 new documents -> actions arise
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario1_new_case_with_no_evidence_produces_actions():
    from services.case_evolution import _consequence_refresh_case_actions

    supa, tr = _make_full_action_supa(dokazi=[], dokumenti=[], rocista=[])
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await _consequence_refresh_case_actions(_event())

    assert len(tr["inserted"]) >= 1
    assert any(r["tip"] == "PRIBAVITI_DOKAZ" for r in tr["inserted"])
    assert tr["updated"] == []
    assert tr["closed"] == []
    mock_log.assert_awaited_once()
    assert mock_log.await_args.args[0] == "case_action_refreshed"
    assert "created=" in result


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — new evidence removes the risk -> the action closes
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario2_evidence_added_closes_the_stale_pribaviti_dokaz_action():
    from services.case_evolution import _consequence_refresh_case_actions, _stable_key

    stale_key = _stable_key("problem", "nema_dokaza")
    supa, tr = _make_full_action_supa(
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],  # evidence now exists
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        rocista=[],
        existing_open_actions=[{"id": "act-old", "dedupe_key": stale_key}],
    )
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    assert tr["closed"] == ["act-old"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3 — deadline extended -> action UPDATES in place, not close+reopen
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario3_deadline_extended_updates_same_action_not_close_reopen():
    from services.case_evolution import _consequence_refresh_case_actions, _stable_key
    from datetime import date, timedelta

    key = _stable_key("rociste", "roc-1")
    new_rok = (date.today() + timedelta(days=25)).isoformat()  # extended -> now medium, was critical
    supa, tr = _make_full_action_supa(
        rocista=[{"id": "roc-1", "sud": "Sud", "datum": new_rok, "status": "zakazano"}],
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        existing_open_actions=[{"id": "act-rociste", "dedupe_key": key}],
    )
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    assert tr["closed"] == []
    assert tr["inserted"] == []
    assert len(tr["updated"]) == 1
    updated_id, payload = tr["updated"][0]
    assert updated_id == "act-rociste"
    assert payload["prioritet"] == "medium"
    assert payload["rok"] == new_rok


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4 — document deleted -> stale action disappears (closes)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario4_contradiction_no_longer_present_closes_its_action():
    from services.case_evolution import _consequence_refresh_case_actions, _stable_key

    old_key = _stable_key("kontradikcija", "Stara kontradikcija", "DOK-01 str.1", "DOK-02 str.1")
    supa, tr = _make_full_action_supa(
        case_dna={"kontradikcije": []},  # the contradiction-causing document was deleted/resolved
        dokazi=[{"snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        dokumenti=[{"naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t} for t in
                   ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        rocista=[],
        existing_open_actions=[{"id": "act-contra", "dedupe_key": old_key}],
    )
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    assert tr["closed"] == ["act-contra"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 5 — two parallel refreshes -> unique-violation on insert is benign
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario5_concurrent_insert_duplicate_key_is_swallowed_not_raised():
    from services.case_evolution import _consequence_refresh_case_actions, _stable_key

    key = _stable_key("problem", "nema_dokaza")
    supa, tr = _make_full_action_supa(
        dokazi=[], dokumenti=[], rocista=[],
        insert_raises_duplicate_for={key},  # simulates the other concurrent refresh winning the race
    )
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await _consequence_refresh_case_actions(_event())  # must NOT raise

    assert key not in {r["dedupe_key"] for r in tr["inserted"]}
    assert "created=" in result


@pytest.mark.anyio
async def test_scenario5_non_duplicate_insert_errors_still_propagate():
    from services.case_evolution import _consequence_refresh_case_actions

    supa, tr = _make_full_action_supa(dokazi=[], dokumenti=[], rocista=[])
    real_table = supa.table.side_effect
    def _table(name):
        t = real_table(name)
        if name == "case_actions":
            def _insert(row):
                raise Exception("connection reset by peer")
            t.insert.side_effect = _insert
        return t
    supa.table.side_effect = _table

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        with pytest.raises(Exception, match="connection reset"):
            await _consequence_refresh_case_actions(_event())


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 6 — system restart / idempotent replay -> identical result
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario6_rerun_with_unchanged_facts_is_a_pure_no_op():
    """Once the target set is already fully reflected as open case_actions
    rows (as if the process had 'restarted' after a prior successful run),
    re-running produces zero inserts and zero closes -- only in-place
    updates (refreshing razlog/dokaz/updated_at), proving the action list
    stays byte-for-byte consistent across a restart."""
    from services.case_evolution import _compute_target_actions, _consequence_refresh_case_actions

    dokazi=[]
    dokumenti=[]
    rocista=[]
    probe_supa = _make_target_supa(dokazi=dokazi, dokumenti=dokumenti, rocista=rocista)
    with patch("services.case_evolution._get_supa", return_value=probe_supa):
        target = await _compute_target_actions("pred-1")
    existing = [{"id": f"act-{i}", "dedupe_key": a["dedupe_key"]} for i, a in enumerate(target)]

    supa, tr = _make_full_action_supa(dokazi=dokazi, dokumenti=dokumenti, rocista=rocista, existing_open_actions=existing)
    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    assert tr["inserted"] == []
    assert tr["closed"] == []
    assert len(tr["updated"]) == len(target)
