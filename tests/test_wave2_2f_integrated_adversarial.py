# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2F -- Integrated adversarial closure.

Not a new feature. Most of the required scenario matrix is already
covered, with real evidence, by Tasks 2A-2E's own test files:

  DUPLICATE EVENT            tests/test_wave2_2d_source_invalidation.py
                              (deterministic event_id -> one row)
  PROCESSING RETRY            tests/test_wave2_2c_..., test_wave2_2e_...
  PROCESSING FAILURE          tests/test_wave2_2a_dead_letter_observability.py
  DOCUMENT-LESS HEARING       tests/test_wave2_2c_document_less_hearing.py
  SOURCE INVALIDATION         tests/test_wave2_2d_source_invalidation.py
  MULTIPLE-SUPPORT INVALID.   tests/test_wave2_2d_source_invalidation.py
  TERMINAL MATTER RACE/REPLAY tests/test_wave2_2b_terminal_matter_invariant.py
  MATTER ISOLATION            tests/test_wave2_2d_source_invalidation.py
  ACTIVE-MATTER REGRESSION    tests/test_wave2_2b_..., test_wave2_2c_...
  CONCURRENT PROCESSING       tests/test_wave2_2e_deterministic_lineage.py
                              (concurrent-create-loser, lost-close-race)

This file adds ONLY the scenarios not yet directly exercised: a
genuinely healthy matter producing zero unjustified action (NO
CONSEQUENCE), and a stale/delayed event proven unable to resurrect state
a newer deletion already invalidated (STALE SOURCE) -- plus one explicit
cross-tenant isolation check for SOURCE_INVALIDATED specifically (2D's
own isolation tests covered MATTER_BECAME_TERMINAL's HTTP layer; this
one exercises the consequence layer directly).

AI CONTEXT REGRESSION and DEADLINE CONFIRMATION REGRESSION are NOT
re-implemented here per this task's own instruction ("run the existing
dedicated gate tests only, do not redesign") -- run directly:
  pytest tests/test_faza62_ai_observation_gate.py tests/test_faza62_gate_e2e_paths.py \
         tests/test_faza621_provenance_boundary.py tests/test_faza64_provenance_contract.py \
         tests/test_faza642_authorization_boundary.py tests/test_faza643_confirmation_disclosure.py \
         tests/test_faza65_confirmation_disclosure_impl.py tests/test_faza661_rollout_compatibility.py
  -> 325 passed (deadline confirmation gate, untouched by Wave 2)
  pytest tests/test_tau002_case_context.py tests/test_tau002_morning_briefing_context.py \
         tests/test_ai_fabric_contract.py tests/test_mission_ledger_correlation.py \
         tests/test_mission_atlas_ai_provenance.py
  -> 91 passed (manual evidence / AI context path, untouched by Wave 2)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

from datetime import date, timedelta

import pytest
from unittest.mock import MagicMock, patch

from api import app  # noqa: E402,F401

from services.event_bus import Event, EventType  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeQuery:
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref
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

    def neq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) != val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    @property
    def not_(self):
        return _NotFilter(self)

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


class _NotFilter:
    def __init__(self, query):
        self._query = query

    def in_(self, col, vals):
        vals = set(vals)
        self._query._filtered = [r for r in self._query._filtered if r.get(col) not in vals]
        return self._query

    def eq(self, col, val):
        self._query._filtered = [r for r in self._query._filtered if r.get(col) != val]
        return self._query


class _FakeSupa:
    def __init__(self, tables):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


PID = "pred-1"


def _predmet_row(status="aktivan"):
    return {"id": PID, "user_id": "user-1", "naziv": "Zdrav predmet", "case_dna": {}, "tip": "parnicno", "status": status}


def _event(event_id, predmet_id=PID, event_type=EventType.SOURCE_INVALIDATED):
    return Event(type=event_type, user_id="user-1", predmet_id=predmet_id,
                 payload={}, correlation_id="corr-1", event_id=event_id)


# ═══════════════════════════════════════════════════════════════════════════
# NO CONSEQUENCE -- a genuinely healthy matter produces zero unjustified
# action, proving the system doesn't invent busywork.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_healthy_matter_with_all_expected_docs_produces_no_open_action():
    from services.case_evolution import _consequence_refresh_case_actions
    from shared.constants import EXPECTED_DOCS

    # Every expected doc type for "parnicno" present, strong evidence for
    # every legal element, no upcoming hearings -- nothing SHOULD be flagged.
    tipovi = EXPECTED_DOCS["parnicno"]
    dokumenti = [
        {"id": f"doc-{i}", "predmet_id": PID, "naziv_fajla": f"{t}.pdf", "status": "obradjen", "tip_dokaza": t}
        for i, t in enumerate(tipovi)
    ]
    fake = _FakeSupa({
        "predmeti": [_predmet_row()],
        "predmet_dokazi": [
            {"id": "dz-1", "predmet_id": PID, "snaga": "jaka", "kategorija": "direktan",
             "pravni_element": "uzrocna_veza", "izvor_snage": "sudska_praksa"},
        ],
        "predmet_dokumenti": dokumenti,
        "rocista": [],
        "case_actions": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event("evt-healthy"))

    open_actions = [r for r in fake.tables["case_actions"] if r.get("status") == "open"]
    assert open_actions == [], f"healthy matter unexpectedly produced actions: {open_actions}"
    assert result == "created=0 updated=0 closed=0"


# ═══════════════════════════════════════════════════════════════════════════
# STALE SOURCE -- a delayed/stale event cannot resurrect state a newer
# deletion already invalidated. Proves recomputation-from-current-truth,
# not trust in whatever the event itself assumed at emission time.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_stale_delayed_event_cannot_beat_a_newer_deletion():
    """Timeline: rociste exists -> DOCUMENT_ACCEPTED (E_old) queued for
    this matter, but its dispatch is delayed -- rociste gets deleted
    (SOURCE_INVALIDATED already processed, action closed) -- E_old FINALLY
    dispatches. E_old must NOT recreate the deadline action: it re-reads
    CURRENT rocista (empty), not whatever was true when it was queued."""
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _FakeSupa({
        "predmeti": [_predmet_row()],
        "predmet_dokazi": [], "predmet_dokumenti": [],
        "rocista": [{"id": "roc-1", "predmet_id": PID, "sud": "Osnovni sud",
                     "datum": (date.today() + timedelta(days=5)).isoformat(), "status": "zakazano"}],
        "case_actions": [],
    })

    # A fresher SOURCE_INVALIDATED already ran (rociste deleted + reconciled).
    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-fresh-delete"))
    fake.tables["rocista"] = []  # the deletion itself
    with patch("services.case_evolution._get_supa", return_value=fake):
        closure = await _consequence_refresh_case_actions(_event("evt-fresh-delete-reconcile"))
    assert "closed=1" in closure
    assert [r for r in fake.tables["case_actions"] if r["status"] == "open" and r["tip"] == "PRIPREMITI_PODNESAK"] == []

    # The STALE, delayed DOCUMENT_ACCEPTED (queued back when the hearing
    # still existed) finally dispatches now.
    with patch("services.case_evolution._get_supa", return_value=fake):
        stale_result = await _consequence_refresh_case_actions(_event("evt-stale-old", event_type=EventType.DOCUMENT_ACCEPTED))

    hearing_actions_after = [r for r in fake.tables["case_actions"] if r["status"] == "open" and r["tip"] == "PRIPREMITI_PODNESAK"]
    assert hearing_actions_after == [], "a stale event resurrected a deadline action a newer deletion had already closed"


# ═══════════════════════════════════════════════════════════════════════════
# TENANT ISOLATION at the consequence layer -- SOURCE_INVALIDATED carrying
# one predmet_id never touches another user's matter, even if somehow
# mis-routed (defense in depth beyond the HTTP-layer ownership filters
# Task 2D already proved).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_source_invalidated_predmet_id_scoping_is_exact_not_prefix_or_fuzzy():
    from services.case_evolution import _consequence_refresh_case_actions

    victim_action = {
        "id": "ca-victim", "predmet_id": "pred-1-ARCHIVED-COPY", "tip": "PRIBAVITI_DOKAZ",
        "status": "open", "dedupe_key": "k-victim", "razlog": "x", "prioritet": "high", "rok": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _FakeSupa({
        "predmeti": [_predmet_row(), {"id": "pred-1-ARCHIVED-COPY", "user_id": "user-2", "naziv": "B", "case_dna": {}, "tip": "parnicno", "status": "aktivan"}],
        "predmet_dokazi": [], "predmet_dokumenti": [], "rocista": [],
        "case_actions": [victim_action],
    })

    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event("evt-scope-check", predmet_id=PID))

    victim_after = next(r for r in fake.tables["case_actions"] if r["id"] == "ca-victim")
    assert victim_after["status"] == "open"
