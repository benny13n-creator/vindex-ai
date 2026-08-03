# -*- coding: utf-8 -*-
"""
Operation Lawyer Zero, LZ-003 (2026-08-03): extend global search to cover
tasks (zadaci) and evidence-type fields (predmet_dokumenti.tip_dokaza).

zadaci has no user_id column at all (only kreirao_uid/dodeljen_uid/
kancelarija_id, per migrations/045_firm_intelligence.sql) -- a real,
different scoping model from every other search branch. This file tests
that specifically and separately from tests/test_search.py's existing
6-type suite, because getting this scope wrong would be a real tenant/
firm-isolation bug, not just a missing feature.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock


def _zadaci_supa(rows_by_filter: dict):
    """Mock whose .or_(...) call records the exact filter string used, so
    the test can assert the query only matches the calling user's own
    kreirao_uid/dodeljen_uid -- never a bare table scan."""
    supa = MagicMock()
    calls = {"or_filter": None}

    def _table(name):
        t = MagicMock()
        if name == "zadaci":
            def _or(filter_str):
                calls["or_filter"] = filter_str
                inner = MagicMock()
                inner.ilike.return_value.limit.return_value.execute.return_value.data = rows_by_filter.get(filter_str, [])
                return inner
            t.select.return_value.or_.side_effect = _or
        return t

    supa.table.side_effect = _table
    return supa, calls


def test_search_zadaci_scopes_to_creator_or_assignee_only():
    """The one thing this test must prove: the query filter names THIS
    user's uid in both the creator and assignee slots -- never a bare
    'select all tasks' query, and never another user's id."""
    from routers.search import _search_zadaci

    uid = "uid-001"
    expected_filter = f"kreirao_uid.eq.{uid},dodeljen_uid.eq.{uid}"
    matching_row = {"id": "z-001", "naziv": "Pripremiti odgovor na tužbu",
                     "status": "otvoreno", "prioritet": "visoko",
                     "predmet_id": "p-001", "rok_datum": "2026-08-10"}
    supa, calls = _zadaci_supa({expected_filter: [matching_row]})

    res = _search_zadaci(supa, uid, "odgovor", 5)

    assert calls["or_filter"] == expected_filter, (
        "zadaci has no user_id column -- the query must scope on "
        "kreirao_uid OR dodeljen_uid for THIS user specifically, "
        "never a table-wide scan"
    )
    assert len(res) == 1
    assert res[0]["tip"] == "zadatak"
    assert res[0]["naziv"] == "Pripremiti odgovor na tužbu"
    assert res[0]["meta"]["predmet_id"] == "p-001"


def test_search_zadaci_does_not_leak_other_users_filter_shape():
    """A different user's search must produce a DIFFERENT filter string --
    proves the scoping is parameterized per-caller, not a hardcoded or
    accidentally-shared value."""
    from routers.search import _search_zadaci

    supa, calls = _zadaci_supa({})
    _search_zadaci(supa, "uid-999", "bilo šta", 5)

    assert "uid-999" in calls["or_filter"]
    assert "uid-001" not in calls["or_filter"]


def test_search_zadaci_empty_result_is_empty_list():
    from routers.search import _search_zadaci
    supa, _ = _zadaci_supa({})
    res = _search_zadaci(supa, "uid-001", "nepostojeci zadatak", 5)
    assert res == []


def test_search_dokumenti_or_filter_includes_tip_dokaza():
    """LZ-002 made tip_dokaza a real, correctly-populated field -- search
    must be able to match a document by its evidence type, not only by
    words literally present in its extracted text."""
    from routers.search import _search_dokumenti

    or_filters = []
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmet_dokumenti":
            def _or(filter_str):
                or_filters.append(filter_str)
                inner = MagicMock()
                inner.limit.return_value.execute.return_value.data = []
                return inner
            t.select.return_value.eq.return_value.or_.side_effect = _or
        return t

    supa.table.side_effect = _table
    _search_dokumenti(supa, "uid-001", "ugovor", 5)

    assert or_filters, "expected the dokumenti search to issue an .or_() filter"
    assert "tip_dokaza.ilike" in or_filters[0]
