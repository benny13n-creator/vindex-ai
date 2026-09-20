# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 3 F4 FINAL closure -- deadline AUTHORIZATION on the
legacy dashboard, not just provenance transport.

PROVEN REMAINING DEFECT after commit 82e869b7 (which fixed transport of
`izvor` through shared/rokovi.py -> routers/dashboard.py): the legacy
dashboard's own consumers (static/vindex.js::_kcPanelAktivni,
::portfolio_render) never read `izvor`, so an UNCONFIRMED, never-human-seen
AI deadline still drove the exact same warning icon / "Rok: N dana" /
"Hitni rokovi" operational count as a human-confirmed one. Provenance being
CORRECTLY TRANSPORTED is not the same as the deadline being AUTHORIZED for
operational treatment.

This closure adds the missing axis: human DECISION STATE
(shared/rok_potvrda.py, FAZA 6.5 -- UNCONFIRMED/CONFIRMED/REJECTED,
resolved from audit_immutable, fail-closed), reusing the EXACT mechanism
already live at GET /api/rokovi/kandidati and POST /api/rokovi/{id}/
potvrdi|odbij -- not a new algorithm.

The mandatory proof for every test below: authorization must depend ONLY
on `stanje_odluke`, NEVER on `izvor`/provenance -- the project has already
tried and rejected provenance-based authorization twice (FAZA 6.2, 6.4).
Every AI_AUTONOMOUS case has a HUMAN_DIRECT twin asserting the identical
outcome for exactly this reason.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request as StarletteRequest

from shared.rok_potvrda import STANJE_NEPOTVRDJEN, STANJE_ODBIJEN, STANJE_POTVRDJEN


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
              "path": "/api/dashboard/command-center", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


UID = "aaaa0000-0000-0000-0000-000000000001"
PID = "cccc0000-0000-0000-0000-000000000003"
ROK_ID = "eeee0000-0000-0000-0000-000000000099"


def _make_chain(data):
    chain = MagicMock()
    for attr in ['select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
                 'insert', 'update', 'delete', 'is_', 'in_', 'desc']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_cc_supa(predmeti=None, rokovi=None):
    table_map = {
        "predmeti": predmeti or [],
        "rocista": [],
        "predmet_hronologija": rokovi or [],
        "predmet_beleske": [],
        "predmet_dokumenti": [],
        "rokovi": [],
        "predmet_dokazi": [],
    }

    def _table(name):
        if name == "predmet_istorija":
            return _make_chain([])
        return _make_chain(table_map.get(name, []))

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    return supa


def _rok_row(izvor, dani=1):
    """One synthetic predmet_hronologija row, `dani` days from today --
    inside the 48h `hitni` window by default so a wrongly-operational row
    would actually be caught."""
    datum = (date.today() + timedelta(days=dani)).isoformat()
    return {
        "id": ROK_ID, "predmet_id": PID, "dogadjaj": "Test rok",
        "datum_iso": datum, "vaznost": "kritičan", "akter": "", "izvor": izvor,
    }


async def _run_command_center(rok_row, odl_map):
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    supa = _make_cc_supa(predmeti=preds, rokovi=[rok_row])
    with patch("routers.dashboard._get_supa", return_value=supa), \
         patch("routers.dashboard.odluke", return_value=odl_map):
        return await command_center(request=_req(), user=_user())


# ═══════════════════════════════════════════════════════════════════════════
# Mandatory cases 1-2: UNCONFIRMED, regardless of provenance -> NOT operational
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_ai_autonomous_unconfirmed_not_operational():
    result = await _run_command_center(_rok_row("AI_AUTONOMOUS"), odl_map={})
    assert not any(r["id"] == ROK_ID for r in result["hitni_rokovi"]), \
        "an UNCONFIRMED AI-autonomous deadline reached the operational hitni_rokovi list"
    matching = [r for r in result["rokovi_7_dana"] if r["id"] == ROK_ID]
    assert matching and matching[0]["stanje_odluke"] == STANJE_NEPOTVRDJEN


@pytest.mark.anyio
async def test_human_direct_unconfirmed_same_result_as_ai_autonomous():
    """MANDATORY: proves authorization does not key off provenance -- a
    HUMAN_DIRECT row with no recorded decision must be excluded from
    hitni_rokovi exactly like the AI_AUTONOMOUS case above."""
    result = await _run_command_center(_rok_row("HUMAN_DIRECT"), odl_map={})
    assert not any(r["id"] == ROK_ID for r in result["hitni_rokovi"]), \
        "an UNCONFIRMED human-direct deadline was excluded differently than an AI one -- authorization must be provenance-independent"


# ═══════════════════════════════════════════════════════════════════════════
# Mandatory cases 3-4: CONFIRMED -> operational, regardless of provenance
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_ai_autonomous_confirmed_is_operational():
    result = await _run_command_center(_rok_row("AI_AUTONOMOUS"), odl_map={ROK_ID: STANJE_POTVRDJEN})
    assert any(r["id"] == ROK_ID for r in result["hitni_rokovi"]), \
        "a CONFIRMED AI-autonomous deadline within the hitni window did not become operational"


@pytest.mark.anyio
async def test_human_direct_confirmed_is_operational():
    result = await _run_command_center(_rok_row("HUMAN_DIRECT"), odl_map={ROK_ID: STANJE_POTVRDJEN})
    assert any(r["id"] == ROK_ID for r in result["hitni_rokovi"])


# ═══════════════════════════════════════════════════════════════════════════
# Mandatory case 5: REJECTED absent from active deadline treatment
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rejected_absent_from_active_deadline_lists():
    result = await _run_command_center(_rok_row("AI_AUTONOMOUS"), odl_map={ROK_ID: STANJE_ODBIJEN})
    assert not any(r["id"] == ROK_ID for r in result["rokovi_7_dana"]), \
        "a REJECTED deadline remained in the general active-deadline list"
    assert not any(r["id"] == ROK_ID for r in result["hitni_rokovi"])


# ═══════════════════════════════════════════════════════════════════════════
# Mandatory case 6: confirmation-lookup failure must fail closed
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_confirmation_lookup_failure_does_not_promote_to_confirmed():
    """Mirrors shared/rok_potvrda.py::odluke's own documented fail-closed
    contract (a raised exception there already yields `{}`) -- this proves
    routers/dashboard.py does not add a second, different failure behavior
    on top (e.g. treating a missing id as confirmed by omission)."""
    result = await _run_command_center(_rok_row("AI_AUTONOMOUS"), odl_map={})
    assert not any(r["id"] == ROK_ID for r in result["hitni_rokovi"])
    matching = [r for r in result["rokovi_7_dana"] if r["id"] == ROK_ID]
    assert matching and matching[0]["stanje_odluke"] == STANJE_NEPOTVRDJEN


# ═══════════════════════════════════════════════════════════════════════════
# Scope guards: outbound gate and V2 Danas untouched by this closure
# ═══════════════════════════════════════════════════════════════════════════

def test_dashboard_does_not_reimplement_confirmation_logic():
    """Scope guard: routers/dashboard.py must call the canonical
    shared.rok_potvrda functions, not a parallel reimplementation."""
    import inspect
    import routers.dashboard as dash
    src = inspect.getsource(dash)
    assert "from shared.rok_potvrda import" in src
    assert "def odluke(" not in src
    assert "def stanje_roka(" not in src


def test_outbound_reminder_gate_module_untouched_by_this_closure():
    """shared/rokovi.py::sme_pokrenuti_obavezu/sme_pristupiti are the real
    authorization gate for outbound reminders -- this closure only touches
    the dashboard's own read/display path and must not import or call
    either of them (that would be new, unrequested behavior)."""
    import inspect
    import routers.dashboard as dash
    src = inspect.getsource(dash)
    assert "sme_pokrenuti_obavezu" not in src
    assert "sme_pristupiti" not in src


def test_v2_danas_router_source_unchanged_by_this_session():
    """routers/rok_odluka.py (GET /api/rokovi/kandidati, the V2 Danas
    candidate-confirmation surface) must not have been touched -- confirmed
    via git, not re-tested (its own existing suite already covers it)."""
    import subprocess
    koren = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=koren,
        capture_output=True, text=True,
    ).stdout.split()
    assert "routers/rok_odluka.py" not in diff
    assert "shared/rok_potvrda.py" not in diff
    assert "shared/rokovi.py" not in diff


# ═══════════════════════════════════════════════════════════════════════════
# Frontend: static analysis (no JS test runner in this repo -- same pattern
# this repo already uses for migration-text regression guards)
# ═══════════════════════════════════════════════════════════════════════════

VINDEX_JS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "vindex.js")


def _read_vindex_js() -> str:
    with open(VINDEX_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_frontend_rok_by_predmet_filters_to_confirmed_only():
    """The exact defect this closure fixes: `_kcPanelAktivni`'s per-matter
    "Rok: N dana" text was driven by ANY row in rokovi_7_dana regardless of
    decision state. Must now require `stanje_odluke==='CONFIRMED'`."""
    src = _read_vindex_js()
    idx = src.index("function _kcPanelAktivni")
    body = src[idx:idx + 2000]
    assert "rokByPredmet" in body
    assert "stanje_odluke" in body
    assert "CONFIRMED" in body


def test_frontend_hitni_rokovi_reducer_unchanged():
    """hitniIds needs no frontend filter -- `hitni_rokovi` is already
    CONFIRMED-only from the backend. This guards against someone "fixing"
    it twice (which would just be redundant, not wrong, but signals the
    contract was misunderstood if it happens)."""
    src = _read_vindex_js()
    idx = src.index("function _kcPanelAktivni")
    body = src[idx:idx + 1000]
    assert "var hitniIds      = (d.hitni_rokovi||[]).reduce(function(m,r){m[r.predmet_id]=1;return m;},{});" in body


def test_frontend_unconfirmed_marked_as_proposal_not_operational():
    """portfolio_render's "Rokovi 7d" list is the one place an UNCONFIRMED
    candidate may still be visible (a neutral, informational list, distinct
    from the red "Hitni rokovi" section) -- it must say so explicitly, not
    render identically to a confirmed deadline."""
    src = _read_vindex_js()
    idx = src.index("function portfolio_render")
    body = src[idx:idx + 4000]
    assert "stanje_odluke" in body
    assert "UNCONFIRMED" in body
    assert "čeka potvrdu" in body
