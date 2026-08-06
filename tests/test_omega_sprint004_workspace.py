# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 004 (2026-08-06) — "Unified Legal Workspace". Tests
for `routers/workspace.py::get_workspace` — the canonical aggregation
endpoint over `case_actions` (Sprint 003), `zadaci` (status='ceka'), and
`intake_jobs` (status='awaiting_review'). Writes nothing; every assertion
here is about correct bucketing/sorting of already-existing data.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock

from routers.workspace import get_workspace


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(predmeti=None, case_actions=None, zadaci=None, intake_jobs=None, closed_actions=None, closed_zadaci=None):
    predmeti = predmeti or []
    case_actions = case_actions or []
    zadaci = zadaci or []
    intake_jobs = intake_jobs or []
    closed_actions = closed_actions or []
    closed_zadaci = closed_zadaci or []

    def _predmeti_table():
        t = MagicMock()
        t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=predmeti)
        return t

    def _case_actions_table():
        t = MagicMock()
        # open: .select().in_().eq("status","open").execute()
        open_chain = MagicMock()
        open_chain.execute.return_value = MagicMock(data=case_actions)
        # closed: .select().in_().eq("status","closed").gte().execute()
        closed_chain = MagicMock()
        closed_chain.execute.return_value = MagicMock(data=closed_actions)

        def _eq(col, val):
            if val == "open":
                return open_chain
            leaf = MagicMock()
            leaf.gte.return_value.execute.return_value = MagicMock(data=closed_actions)
            return leaf
        t.select.return_value.in_.return_value.eq.side_effect = _eq
        return t

    def _zadaci_table():
        t = MagicMock()

        def _eq_dodeljen(col, val):
            inner = MagicMock()

            def _eq_status(col2, val2):
                leaf = MagicMock()
                if val2 == "ceka":
                    leaf.execute.return_value = MagicMock(data=zadaci)
                elif val2 == "zavrseno":
                    leaf.gte.return_value.execute.return_value = MagicMock(data=closed_zadaci)
                return leaf
            inner.eq.side_effect = _eq_status
            return inner
        t.select.return_value.eq.side_effect = _eq_dodeljen
        return t

    def _intake_jobs_table():
        t = MagicMock()
        t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=intake_jobs)
        return t

    def _table(name):
        if name == "predmeti":
            return _predmeti_table()
        if name == "case_actions":
            return _case_actions_table()
        if name == "zadaci":
            return _zadaci_table()
        if name == "intake_jobs":
            return _intake_jobs_table()
        raise AssertionError(f"unexpected table {name}")

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa


class _Req:
    pass


def _user(uid="user-1"):
    return {"user_id": uid}


from unittest.mock import patch


@pytest.mark.anyio
async def test_empty_workspace_all_buckets_empty():
    supa = _make_supa(predmeti=[{"id": "pred-1", "naziv": "Predmet A"}])
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert result["danas"] == []
    assert result["kriticno"] == []
    assert result["predstojece"] == []
    assert result["za_pregled"] == []
    assert result["na_cekanju"] == []
    assert result["zavrseno_nedavno"] == []
    assert result["ukupno_aktivnih"] == 0
    assert result["predmeta_sa_akcijama"] == 0


@pytest.mark.anyio
async def test_critical_action_without_today_deadline_goes_to_kriticno():
    from datetime import date, timedelta
    far_rok = (date.today() + timedelta(days=20)).isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        case_actions=[{
            "id": "act-1", "predmet_id": "pred-1", "tip": "PRIBAVITI_DOKAZ",
            "razlog": "Nema dokaza", "prioritet": "critical", "rok": far_rok,
            "dokaz": {}, "izvor_dokumenti": [], "created_at": "2026-08-01T00:00:00Z",
        }],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["kriticno"]) == 1
    assert result["kriticno"][0]["id"] == "act-1"
    assert result["kriticno"][0]["predmet_naziv"] == "Predmet A"
    assert result["danas"] == []


@pytest.mark.anyio
async def test_action_due_today_goes_to_danas_regardless_of_priority():
    from datetime import date
    today = date.today().isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        case_actions=[{
            "id": "act-1", "predmet_id": "pred-1", "tip": "PRIPREMITI_PODNESAK",
            "razlog": "Rocište danas", "prioritet": "medium", "rok": today,
            "dokaz": {}, "izvor_dokumenti": [], "created_at": "2026-08-01T00:00:00Z",
        }],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["danas"]) == 1
    assert result["kriticno"] == []
    assert result["predstojece"] == []


@pytest.mark.anyio
async def test_high_and_medium_priority_without_today_deadline_go_to_predstojece():
    from datetime import date, timedelta
    rok = (date.today() + timedelta(days=10)).isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        case_actions=[
            {"id": "act-h", "predmet_id": "pred-1", "tip": "PLANIRATI_ROKOVE", "razlog": "x",
             "prioritet": "high", "rok": rok, "dokaz": {}, "izvor_dokumenti": [], "created_at": "2026-08-01T00:00:00Z"},
            {"id": "act-m", "predmet_id": "pred-1", "tip": "RAZRESITI_KONTRADIKCIJU", "razlog": "y",
             "prioritet": "medium", "rok": None, "dokaz": {}, "izvor_dokumenti": [], "created_at": "2026-08-01T00:00:00Z"},
        ],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert {a["id"] for a in result["predstojece"]} == {"act-h", "act-m"}
    # critical-before-medium ordering within the bucket
    assert result["predstojece"][0]["id"] == "act-h"


@pytest.mark.anyio
async def test_low_and_informational_actions_are_excluded_from_every_bucket():
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        case_actions=[
            {"id": "act-low", "predmet_id": "pred-1", "tip": "OJACATI_DOKAZE", "razlog": "z",
             "prioritet": "informational", "rok": None, "dokaz": {}, "izvor_dokumenti": [], "created_at": "x"},
        ],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert result["danas"] == [] and result["kriticno"] == [] and result["predstojece"] == []
    assert result["ukupno_aktivnih"] == 0


@pytest.mark.anyio
async def test_awaiting_review_job_appears_in_za_pregled_with_high_priority():
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        intake_jobs=[{"id": "job-1", "predmet_id": "pred-1", "original_filename": "ugovor.pdf",
                       "status": "awaiting_review", "created_at": "2026-08-01T00:00:00Z"}],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["za_pregled"]) == 1
    assert result["za_pregled"][0]["prioritet"] == "high"
    assert result["za_pregled"][0]["vrsta"] == "review"
    assert "ugovor.pdf" in result["za_pregled"][0]["naslov"]


@pytest.mark.anyio
async def test_zadatak_ceka_not_due_today_goes_to_na_cekanju_with_translated_priority():
    from datetime import date, timedelta
    rok = (date.today() + timedelta(days=5)).isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        zadaci=[{"id": "z-1", "naziv": "Čeka odgovor suda", "opis": "", "prioritet": "visoko",
                  "status": "ceka", "rok_datum": rok, "predmet_id": "pred-1",
                  "kreirao_uid": "user-1", "created_at": "2026-08-01T00:00:00Z"}],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["na_cekanju"]) == 1
    assert result["na_cekanju"][0]["prioritet"] == "high"  # translated from "visoko"
    assert result["na_cekanju"][0]["vrsta"] == "zadatak"
    assert result["danas"] == []


@pytest.mark.anyio
async def test_zadatak_ceka_due_today_goes_to_danas_not_na_cekanju():
    from datetime import date
    today = date.today().isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        zadaci=[{"id": "z-1", "naziv": "Rok danas", "opis": "", "prioritet": "hitno",
                  "status": "ceka", "rok_datum": today, "predmet_id": "pred-1",
                  "kreirao_uid": "user-1", "created_at": "2026-08-01T00:00:00Z"}],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["danas"]) == 1
    assert result["danas"][0]["vrsta"] == "zadatak"
    assert result["na_cekanju"] == []


@pytest.mark.anyio
async def test_recently_closed_action_and_task_appear_in_zavrseno_nedavno():
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "Predmet A"}],
        closed_actions=[{"id": "act-closed", "predmet_id": "pred-1", "tip": "PRIBAVITI_DOKAZ",
                          "razlog": "Rešeno", "prioritet": "critical", "rok": None,
                          "dokaz": {}, "izvor_dokumenti": [], "closed_at": "2026-08-05T00:00:00Z"}],
        closed_zadaci=[{"id": "z-done", "naziv": "Gotovo", "opis": "", "prioritet": "normalan",
                         "status": "zavrseno", "rok_datum": None, "predmet_id": "pred-1",
                         "kreirao_uid": "user-1", "zavrseno_u": "2026-08-05T00:00:00Z"}],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert len(result["zavrseno_nedavno"]) == 2
    kinds = {item["vrsta"] for item in result["zavrseno_nedavno"]}
    assert kinds == {"case_action", "zadatak"}
    # closed items never count toward the active-work totals
    assert result["ukupno_aktivnih"] == 0


@pytest.mark.anyio
async def test_predmeta_sa_akcijama_counts_unique_cases_with_active_items_only():
    from datetime import date, timedelta
    rok = (date.today() + timedelta(days=10)).isoformat()
    supa = _make_supa(
        predmeti=[{"id": "pred-1", "naziv": "A"}, {"id": "pred-2", "naziv": "B"}],
        case_actions=[
            {"id": "a1", "predmet_id": "pred-1", "tip": "PRIBAVITI_DOKAZ", "razlog": "x",
             "prioritet": "critical", "rok": rok, "dokaz": {}, "izvor_dokumenti": [], "created_at": "x"},
            {"id": "a2", "predmet_id": "pred-1", "tip": "PLANIRATI_ROKOVE", "razlog": "y",
             "prioritet": "high", "rok": rok, "dokaz": {}, "izvor_dokumenti": [], "created_at": "x"},
        ],
    )
    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert result["predmeta_sa_akcijama"] == 1  # both actions are the same case
    assert result["ukupno_aktivnih"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# Program Lambda, Certification 004 (2026-08-06) -- get_workspace's own
# primary asyncio.gather() had no return_exceptions=True, unlike this same
# file's own _fetch_recently_completed gather. A transient failure in ONE
# of the 3 sub-fetches raised unhandled, taking down the whole board even
# when the other two would have succeeded.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_workspace_survives_one_sub_fetch_failing():
    """A transient failure in _fetch_open_actions alone must not crash the
    whole endpoint -- the other 2 buckets (waiting zadaci, review jobs)
    must still come through."""
    from unittest.mock import AsyncMock
    supa = _make_supa(predmeti=[{"id": "pred-1", "naziv": "A"}])

    async def _boom(*a, **kw):
        raise RuntimeError("transient DB hiccup")

    with patch("routers.workspace._get_supa", return_value=supa), \
         patch("routers.workspace._fetch_open_actions", new=_boom):
        result = await get_workspace(_Req(), _user())

    # Must not raise -- endpoint returns a real (partial) response.
    assert result["ukupno_aktivnih"] == 0  # the failed bucket contributes nothing, not an error
    assert "danas" in result and "kriticno" in result  # response shape intact


@pytest.mark.anyio
async def test_get_workspace_all_buckets_ok_when_no_sub_fetch_fails():
    """No regression: with nothing failing, the endpoint behaves exactly
    as before this fix."""
    supa = _make_supa(predmeti=[{"id": "pred-1", "naziv": "A"}])

    with patch("routers.workspace._get_supa", return_value=supa):
        result = await get_workspace(_Req(), _user())

    assert result["ukupno_aktivnih"] == 0
    assert result["predmeta_sa_akcijama"] == 0
