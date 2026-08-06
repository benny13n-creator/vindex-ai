# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 004 (2026-08-06) — "Unified Legal Workspace", Phase 5:
proof that Document -> Case Evolution -> Genome -> Action Engine -> Workspace
is a single, automatic chain with NO manual refresh step and NO second data
source. Unlike Sprint 003's own tests (which mock supabase per-call, table by
table), this file uses ONE generic, stateful, in-memory fake Postgres table
shared between `services.case_evolution._consequence_refresh_case_actions`
(the write side, reused unchanged from Sprint 003) and
`routers.workspace.get_workspace` (the new read side, Sprint 004) — proving
a write through the ACTUAL production write path is immediately visible
through the ACTUAL production read path, with nothing in between.
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
# Generic in-memory fake Postgres — supports every chain shape both
# _consequence_refresh_case_actions and get_workspace actually issue,
# without hand-wiring a MagicMock per call site.
# ═══════════════════════════════════════════════════════════════════════════

class _FakeQuery:
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref          # the table's own persistent list
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    def is_(self, col, val):
        if val in ("null", None):
            self._filtered = [r for r in self._filtered if r.get(col) is None]
        return self

    def gte(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or "") >= val]
        return self

    def order(self, col, desc=False):
        self._filtered.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, _n):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        res = MagicMock()
        if self._op == "insert":
            new_row = dict(self._payload)
            new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
            new_row.setdefault("status", "open")
            self._rows_ref.append(new_row)
            res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _FakeSupa:
    """One shared fake DB: `tables[name]` is a real, persistent list of
    dicts mutated in place by inserts/updates — exactly what makes a write
    from one caller visible to a read from a completely different caller,
    the actual property this test exists to prove."""
    def __init__(self, tables: dict):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


def _event(event_id="evt-1", predmet_id="pred-1"):
    return Event(type=EventType.DOCUMENT_ACCEPTED, user_id="user-1", predmet_id=predmet_id,
                 payload={}, correlation_id="corr-1", event_id=event_id)


class _Req:
    pass


def _user():
    return {"user_id": "user-1"}


@pytest.mark.anyio
async def test_new_document_finding_flows_to_workspace_with_no_manual_refresh():
    """Scenario 1 (mission's own): new document -> Case Evolution -> Genome
    (already-refreshed by the time refresh_case_actions runs, per Sprint
    003's own sequential-consequence guarantee) -> Action Engine writes to
    case_actions -> Workspace's very next read shows it. No function is
    called between the two production calls to "sync" or "refresh" anything
    on the Workspace side."""
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno"}],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await _consequence_refresh_case_actions(_event())
    # Empty dokazi/dokumenti trips BOTH "Nema uploadovanih dokaza" (critical)
    # AND "Nedostaje X u spisu" for each of the 4 expected doc types capped
    # at 3 (high) -- 4 real, distinct, sourced findings, not 1.
    assert "created=4" in result

    with patch("routers.workspace._get_supa", return_value=fake):
        workspace = await get_workspace(_Req(), _user())

    assert workspace["ukupno_aktivnih"] == 4
    assert len(workspace["kriticno"]) == 1
    assert workspace["kriticno"][0]["predmet_naziv"] == "Predmet A"
    assert workspace["kriticno"][0]["tip"] == "PRIBAVITI_DOKAZ"
    assert len(workspace["predstojece"]) == 3
    assert all(a["tip"] == "PRIBAVITI_DOKAZ" for a in workspace["predstojece"])


@pytest.mark.anyio
async def test_new_contradiction_produces_a_new_workspace_action():
    """Scenario 2: a new contradiction appears in case_dna.kontradikcije ->
    the next refresh creates a RAZRESITI_KONTRADIKCIJU action -> Workspace
    shows it immediately."""
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A",
                       "case_dna": {"kontradikcije": [
                           {"opis": "Datumi se ne poklapaju", "lokacija_1": "DOK-01 str.1",
                            "lokacija_2": "DOK-02 str.3", "tezina": "kriticna"},
                       ]}, "tip": "parnicno"}],
        "predmet_dokazi": [{"predmet_id": "pred-1", "snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        "predmet_dokumenti": [{"predmet_id": "pred-1", "naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t}
                               for t in ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    with patch("routers.workspace._get_supa", return_value=fake):
        workspace = await get_workspace(_Req(), _user())

    assert len(workspace["kriticno"]) == 1
    assert workspace["kriticno"][0]["tip"] == "RAZRESITI_KONTRADIKCIJU"
    assert workspace["kriticno"][0]["izvor"]["dokaz"]["lokacija_1"] == "DOK-01 str.1"


@pytest.mark.anyio
async def test_deadline_extended_moves_action_from_critical_to_predstojece_in_workspace():
    """Scenario 3: a rociste moves from inside the critical window to a
    later date -> a SECOND refresh (same fact, same dedupe_key) updates the
    SAME row -> Workspace reads the new bucket on its very next call, no
    separate cache to invalidate."""
    from datetime import date, timedelta
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    near_rok = (date.today() + timedelta(days=2)).isoformat()
    far_rok = (date.today() + timedelta(days=20)).isoformat()

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno"}],
        "predmet_dokazi": [{"predmet_id": "pred-1", "snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"}],
        "predmet_dokumenti": [{"predmet_id": "pred-1", "naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t}
                               for t in ("sudska_odluka", "podnesak", "ugovor", "dopis")],
        "rocista": [{"id": "roc-1", "predmet_id": "pred-1", "sud": "Sud", "datum": near_rok, "status": "zakazano"}],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event(event_id="evt-1"))

    with patch("routers.workspace._get_supa", return_value=fake):
        before = await get_workspace(_Req(), _user())
    assert len(before["kriticno"]) == 1
    assert before["predstojece"] == []

    # The hearing gets rescheduled further out.
    fake.tables["rocista"][0]["datum"] = far_rok

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await _consequence_refresh_case_actions(_event(event_id="evt-2"))
    assert "updated=1" in result and "created=0" in result

    with patch("routers.workspace._get_supa", return_value=fake):
        after = await get_workspace(_Req(), _user())
    assert after["kriticno"] == []
    assert len(after["predstojece"]) == 1
    assert len(fake.tables["case_actions"]) == 1  # same row, not a duplicate


@pytest.mark.anyio
async def test_resolved_action_disappears_from_active_workspace_and_appears_in_completed():
    """Scenario 4: the underlying fact resolves (evidence added) -> the
    action closes -> Workspace's active buckets no longer show it, and it
    appears in "zavrseno_nedavno" instead (proving Completed reflects a
    REAL closed_at, not the un-castable "now()" string literal this
    function used before this sprint's own fix)."""
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno"}],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event(event_id="evt-1"))

    with patch("routers.workspace._get_supa", return_value=fake):
        before = await get_workspace(_Req(), _user())
    assert len(before["kriticno"]) == 1  # + 3 in predstojece (missing doc types), same "no docs at all" root cause
    assert len(before["predstojece"]) == 3

    # Evidence is added -- the "no evidence at all" AND "missing doc type"
    # facts no longer hold.
    fake.tables["predmet_dokazi"].append({"predmet_id": "pred-1", "snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"})
    fake.tables["predmet_dokumenti"].extend(
        {"predmet_id": "pred-1", "naziv_fajla": "d.pdf", "status": "indeksirano", "tip_dokaza": t}
        for t in ("sudska_odluka", "podnesak", "ugovor", "dopis")
    )

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await _consequence_refresh_case_actions(_event(event_id="evt-2"))
    assert "closed=4" in result  # all 4 prior findings resolved together

    assert len(fake.tables["case_actions"]) == 4
    for row in fake.tables["case_actions"]:
        assert row["status"] == "closed"
        assert row["closed_at"] and row["closed_at"] != "now()"  # a real ISO timestamp, not the raw literal

    with patch("routers.workspace._get_supa", return_value=fake):
        after = await get_workspace(_Req(), _user())
    assert after["kriticno"] == []
    assert after["predstojece"] == []
    assert after["ukupno_aktivnih"] == 0
    assert len(after["zavrseno_nedavno"]) == 4
    assert all(item["vrsta"] == "case_action" for item in after["zavrseno_nedavno"])


@pytest.mark.anyio
async def test_restart_produces_identical_workspace_output():
    """Scenario 5: re-running the exact same production chain against
    unchanged facts (simulating a process restart) produces byte-identical
    Workspace bucket contents -- no drift, no duplication."""
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno"}],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event(event_id="evt-1"))
    with patch("routers.workspace._get_supa", return_value=fake):
        first = await get_workspace(_Req(), _user())

    # "restart" -- same event handler re-invoked (e.g. an outbox retry),
    # facts completely unchanged.
    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event(event_id="evt-2"))
    with patch("routers.workspace._get_supa", return_value=fake):
        second = await get_workspace(_Req(), _user())

    assert len(fake.tables["case_actions"]) == 4  # no duplicate rows (1 critical + 3 high, not re-created)
    assert [a["id"] for a in first["kriticno"]] == [a["id"] for a in second["kriticno"]]
    assert [a["id"] for a in first["predstojece"]] == [a["id"] for a in second["predstojece"]]
    assert first["ukupno_aktivnih"] == second["ukupno_aktivnih"] == 4


@pytest.mark.anyio
async def test_500_documents_one_case_workspace_shows_only_what_matters():
    """Scenario 6: a 500-document batch (simulated as its already-settled
    end state -- a case with rich evidence/deadlines) must not flood the
    Workspace with noise: low/informational-priority findings stay out of
    every active bucket, only critical/high/medium (and today's items)
    surface."""
    from datetime import date, timedelta
    from services.case_evolution import _consequence_refresh_case_actions
    from routers.workspace import get_workspace

    # Rich case: strong evidence (no "weak evidence"/"no evidence" noise),
    # full expected-doc coverage (no "missing doc" noise), but 1 genuinely
    # critical deadline and 1 real contradiction -- exactly what SHOULD
    # surface out of "500 documents" worth of processed material.
    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Veliki predmet",
                       "case_dna": {"kontradikcije": [
                           {"opis": "Vazna nepodudarnost", "lokacija_1": "DOK-10 str.2",
                            "lokacija_2": "DOK-88 str.4", "tezina": "vazna"},
                       ]}, "tip": "parnicno"}],
        "predmet_dokazi": [{"predmet_id": "pred-1", "snaga": "jaka", "kategorija": "pisani", "pravni_element": "x"} for _ in range(20)],
        "predmet_dokumenti": [{"predmet_id": "pred-1", "naziv_fajla": f"d{i}.pdf", "status": "indeksirano", "tip_dokaza": t}
                               for i, t in enumerate(("sudska_odluka", "podnesak", "ugovor", "dopis") * 10)],
        "rocista": [{"id": "roc-1", "predmet_id": "pred-1", "sud": "Sud", "datum": (date.today() + timedelta(days=1)).isoformat(), "status": "zakazano"}],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await _consequence_refresh_case_actions(_event())

    with patch("routers.workspace._get_supa", return_value=fake):
        workspace = await get_workspace(_Req(), _user())

    # Exactly the 2 real signals -- the critical deadline (due tomorrow,
    # so not literally "today") and the 1 real contradiction -- nothing
    # manufactured from the sheer document volume.
    assert workspace["ukupno_aktivnih"] == 2
    tipovi = {a["tip"] for a in workspace["kriticno"] + workspace["predstojece"] + workspace["danas"]}
    assert tipovi == {"PRIPREMITI_PODNESAK", "RAZRESITI_KONTRADIKCIJU"}
