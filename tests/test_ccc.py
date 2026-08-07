# -*- coding: utf-8 -*-
"""
Tests for GET /api/ccc/predmeti/{predmet_id} — Case Command Center.
All tests run without live Supabase (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


UID = "aaaa0000-0000-0000-0000-000000000001"
PID = "pred-ccc-0001"


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','gte','lte','like','order','limit','execute',
              'insert','update','delete','is_','in_','desc']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(predmet, dokazi=None, dokumenti=None, rokovi=None, billing=None, hron=None, klijenti=None):
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return _make_chain([predmet])
        if name == "predmet_dokazi":
            return _make_chain(dokazi or [])
        if name == "predmet_dokumenti":
            return _make_chain(dokumenti or [])
        if name == "rocista":
            return _make_chain(rokovi or [])
        if name == "billing_entries":
            return _make_chain(billing or [])
        if name == "predmet_hronologija":
            return _make_chain(hron or [])
        if name == "predmet_klijenti":
            return _make_chain(klijenti or [])
        return _make_chain([])
    supa.table.side_effect = _table
    return supa


_PREDMET = {
    "id": PID, "naziv": "Nezakonit otkaz", "tip": "radno",
    "status": "aktivan", "tuzilac": "Petar Petrović", "tuzeni": "Firma doo",
    "oblast": None, "rizik": None, "vrednost_spora": 500000, "opis": None, "created_at": "2026-01-01",
}

# ── T1: osnovna struktura odgovora ────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_response_structure():
    from routers.ccc import get_ccc
    supa = _make_supa(_PREDMET)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert "predmet" in result
    assert "dok_stats" in result
    assert "rokovi" in result
    assert "billing" in result
    assert "health_score" in result
    assert "nedostajuci" in result
    assert "kritican_rok" in result
    assert result["predmet"]["naziv"] == "Nezakonit otkaz"


# ── T2: dokazi statistika ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_dok_stats_counts():
    from routers.ccc import get_ccc
    dokazi = [
        {"snaga": "jaka",   "kategorija": "ugovor"},
        {"snaga": "jaka",   "kategorija": "dopis"},
        {"snaga": "srednja","kategorija": "podnesak"},
        {"snaga": "slaba",  "kategorija": "vestacki_nalaz"},
    ]
    supa = _make_supa(_PREDMET, dokazi=dokazi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    ds = result["dok_stats"]
    assert ds["jaka"]   == 2
    assert ds["srednja"]== 1
    assert ds["slaba"]  == 1
    assert ds["ukupno"] == 4


# ── T3: billing agregacija ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_billing_aggregation():
    from routers.ccc import get_ccc
    billing = [
        {"iznos": 10000, "obracunato": True},
        {"iznos": 5000,  "obracunato": False},
        {"iznos": 3000,  "obracunato": False},
    ]
    supa = _make_supa(_PREDMET, billing=billing)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    b = result["billing"]
    assert b["uneseno"]     == 18000
    assert b["naplaceno"]   == 10000
    assert b["nenaplaceno"] == 8000


# ── T4: kritičan rok (≤7 dana) se detektuje ──────────────────────────────────

@pytest.mark.anyio
async def test_ccc_kritican_rok_detected():
    from routers.ccc import get_ccc
    sutra = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    rokovi = [{"id": "r1", "naziv": "Rok za odgovor", "sud": "Osnovni sud", "datum": sutra, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is not None
    assert result["kritican_rok"]["naziv"] == "Rok za odgovor"
    assert result["kritican_rok"]["dana_ostalo"] <= 7


# ── T5: nema kritičnog roka kad je rok daleko ─────────────────────────────────

@pytest.mark.anyio
async def test_ccc_no_kritican_rok_when_far():
    from routers.ccc import get_ccc
    daleko = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    rokovi = [{"id": "r2", "naziv": "Rok za žalbu", "sud": "Osnovni sud", "datum": daleko, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is None


# ── T6: nedostajući dokumenti za radno pravo ─────────────────────────────────

@pytest.mark.anyio
async def test_ccc_nedostajuci_radno():
    from routers.ccc import get_ccc
    # Radno: očekuje ugovor, dopis, finansijska_dokumentacija, sudska_odluka
    # Uploadujemo samo ugovor → ostala 3 nedostaju
    dokumenti = [{"tip_dokaza": "ugovor"}]
    supa = _make_supa(_PREDMET, dokumenti=dokumenti)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    nedo = result["nedostajuci"]
    assert "ugovor" not in nedo
    assert "dopis" in nedo
    assert len(nedo) == 3


# ── T6b: Project Nexus (2026-08-03) regression guard — the actual production
# bug (T6 above cannot catch this: _make_chain's mock returns whatever data
# was configured regardless of what fields .select() actually requested, so
# it was structurally blind to a missing column in the real select string).
# This asserts on the SELECT CALL ITSELF, not just the mocked return data.

@pytest.mark.anyio
async def test_ccc_documents_select_includes_tip_dokaza():
    """Was previously "id,naziv_fajla,status" -- missing tip_dokaza entirely,
    meaning Supabase would never actually return it for a real query,
    silently making "nedostajuci" always the full expected-docs list
    regardless of what was really uploaded. Fixed by adding the column to
    the select string; this test guards against it being removed again."""
    from routers.ccc import get_ccc

    # _make_supa's side_effect builds a FRESH chain on every call.table(name)
    # invocation -- calling supa.table("predmet_dokumenti") again after
    # get_ccc returns would inspect an unrelated, never-called chain. Spy on
    # the real call site instead: wrap supa.table itself and record the exact
    # chain handed back the first time "predmet_dokumenti" is requested, so
    # its .select.call_args reflects what the production code actually sent.
    supa = _make_supa(_PREDMET)
    real_table = supa.table.side_effect
    captured = {}

    def _spy_table(name):
        chain = real_table(name)
        if name == "predmet_dokumenti" and "chain" not in captured:
            captured["chain"] = chain
        return chain

    supa.table.side_effect = _spy_table

    with patch("routers.ccc._get_supa", return_value=supa):
        await get_ccc(PID, _user())

    select_call_args = captured["chain"].select.call_args
    assert select_call_args is not None
    selected_fields = select_call_args[0][0]
    assert "tip_dokaza" in selected_fields


# ── T7: health_score pad pri kritičnim rokovima ───────────────────────────────
# Project Nexus (2026-08-03): _compute_health (a duplicate reimplementation
# of Matter Intelligence's canonical formula, with a hardcoded
# nedostajuci_count=0 that silently diverged from the real health_score
# under the identical field name) was removed -- get_ccc now calls
# services/risk_engine.py::calculate_procesni_rizik directly, the same
# function routers/matter_intel.py uses, eliminating the duplicate. These
# tests now exercise that behavior through get_ccc's real response instead
# of importing a function that no longer exists.

@pytest.mark.anyio
async def test_ccc_health_score_drops_with_critical_deadline():
    from routers.ccc import get_ccc
    dokazi = [{"snaga": "jaka", "kategorija": "ugovor"}, {"snaga": "srednja", "kategorija": "dopis"}]

    supa_bez = _make_supa(_PREDMET, dokazi=dokazi, rokovi=[])
    with patch("routers.ccc._get_supa", return_value=supa_bez):
        result_bez = await get_ccc(PID, _user())

    sutra = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    rokovi_kriticni = [
        {"id": f"r{i}", "naziv": "Ročište", "sud": "Sud", "datum": sutra, "status": "aktivan"}
        for i in range(4)
    ]
    supa_sa = _make_supa(_PREDMET, dokazi=dokazi, rokovi=rokovi_kriticni)
    with patch("routers.ccc._get_supa", return_value=supa_sa):
        result_sa = await get_ccc(PID, _user())

    assert result_sa["health_score"] < result_bez["health_score"]


# ── T8: health_score je uvek u [0, 100] ───────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_health_score_bounds():
    from routers.ccc import get_ccc

    supa_low = _make_supa(_PREDMET, dokazi=[{"snaga": "slaba", "kategorija": "x"}] * 10)
    with patch("routers.ccc._get_supa", return_value=supa_low):
        result_low = await get_ccc(PID, _user())
    assert 0 <= result_low["health_score"] <= 100

    supa_high = _make_supa(_PREDMET, dokazi=[{"snaga": "jaka", "kategorija": "x"}] * 10)
    with patch("routers.ccc._get_supa", return_value=supa_high):
        result_high = await get_ccc(PID, _user())
    assert 0 <= result_high["health_score"] <= 100


# ── T9: health_score matches Matter Intelligence's canonical formula exactly
# (the whole point of removing the duplicate) ────────────────────────────────

@pytest.mark.anyio
async def test_ccc_health_score_matches_canonical_risk_engine():
    from routers.ccc import get_ccc
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    dokazi = [{"snaga": "srednja", "kategorija": "ugovor"}]
    dokumenti = [{"tip_dokaza": "ugovor"}]
    rokovi = []

    supa = _make_supa(_PREDMET, dokazi=dokazi, dokumenti=dokumenti, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())

    expected = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=rokovi,
        tip_predmeta="radno", expected_docs=EXPECTED_DOCS,
    )
    assert result["health_score"] == expected["health_score"]
    assert result["nedostajuci"] == expected["nedostajuci_dokazi"]


# ── T10: Operation One Truth (2026-08-07) — plain 10-char DATE strings (the
# realistic Postgres DATE column shape) must be counted correctly, not silently
# dropped by a naive-vs-aware TypeError. T4 above uses a full aware isoformat()
# string, which never exercised the broken len(ds)==10 branch. ─────────────

@pytest.mark.anyio
async def test_ccc_kritican_rok_detected_plain_date_string():
    from routers.ccc import get_ccc
    plain_date = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()  # "YYYY-MM-DD", no time/tz
    assert len(plain_date) == 10
    rokovi = [{"id": "r10", "naziv": "Rok za odgovor", "sud": "Osnovni sud", "datum": plain_date, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is not None
    assert result["kritican_rok"]["naziv"] == "Rok za odgovor"
    assert result["predstojeći"] >= 1


@pytest.mark.anyio
async def test_ccc_predstojeci_and_kritican_rok_sourced_from_canonical_engine():
    """predstojeći/kritican_rok must equal calculate_procesni_rizik's own output,
    not a second, independently-derived count -- the exact defect Operation One
    Truth's forensic pass found (canonical values computed, then discarded)."""
    from routers.ccc import get_ccc
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    plain_date = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    rokovi = [{"id": "r11", "naziv": "Ročište", "sud": "Osnovni sud", "datum": plain_date, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())

    expected = calculate_procesni_rizik(
        dokazi=[], dokumenti=[], rocista=rokovi,
        tip_predmeta="radno", expected_docs=EXPECTED_DOCS,
    )
    assert result["predstojeći"] == expected["predstojeći_rokovi"]
    assert result["kritican_rok"]["id"] in {r.get("id") for r in expected["kriticni_rocista"]}


@pytest.mark.anyio
async def test_ccc_overdue_hearing_surfaces_as_kritican_rok():
    """BLACKSWAN-CRIT-002 established an overdue hearing is MORE urgent than one
    still upcoming -- CCC's own kritican_rok selection must reflect that, not just
    the canonical engine's aggregate count."""
    from routers.ccc import get_ccc
    overdue_date = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    rokovi = [{"id": "r12", "naziv": "Propušteno ročište", "sud": "Osnovni sud", "datum": overdue_date, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is not None
    assert result["kritican_rok"]["naziv"] == "Propušteno ročište"
    assert result["kritican_rok"]["dana_ostalo"] < 0


# ── T9: 404 kad predmet nije vlasništvo korisnika ────────────────────────────

@pytest.mark.anyio
async def test_ccc_404_wrong_user():
    from fastapi import HTTPException
    from routers.ccc import get_ccc
    supa = MagicMock()
    supa.table.return_value = _make_chain([])  # prazno = 404
    with patch("routers.ccc._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await get_ccc("nonexistent-id", _user())
    assert exc.value.status_code == 404
