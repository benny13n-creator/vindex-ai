# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 008 -- Notification/Timeline/Calendar Display Consistency.
Closes LIVINGSYS-DEBT-050, LIVINGSYS-DEBT-051, LIVINGSYS-DEBT-053.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path

import pytest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
VINDEX_JS = (REPO_ROOT / "static" / "vindex.js").read_text(encoding="utf-8")


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def execute(self): return _FakeResult(self._data)


class _FakeSupa:
    def __init__(self, table_data):
        self._table_data = table_data

    def table(self, name):
        return _FakeQuery(self._table_data.get(name, []))


def _base_predmet(status="zatvoren"):
    return {
        "id": "p1", "naziv": "Test predmet", "status": status,
        "oblast": "gradjansko", "tip": "spor", "created_at": "2026-01-01T00:00:00",
        "case_dna": {},
    }


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-053 -- non-deadline narrative hronologija entries (case
# closure notes, hearing follow-ups) rendered on the Calendar tagged
# identically to a real filing deadline ("Rok").
# ═══════════════════════════════════════════════════════════════════════════

def test_klasifikuj_dogadjaj_case_closure_is_napomena():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Predmet zatvoren — Ishod: Pobeda") == "napomena"


def test_klasifikuj_dogadjaj_hearing_followup_is_napomena():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Follow-up ročište: dogovoren novi datum") == "napomena"


def test_klasifikuj_dogadjaj_ugovor_zastupanja_is_napomena():
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Ugovor o zastupanju zaključen — Klijent: Petar Petrović") == "napomena"


def test_klasifikuj_dogadjaj_zastarelost_unaffected():
    """Regression: the pre-existing zastarelost classification must not change."""
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Rok zastarelosti ističe za 30 dana") == "rok_zastarelost"


def test_klasifikuj_dogadjaj_real_deadline_stays_rok_dokument():
    """Regression: a genuine deadline (not one of the known narrative prefixes) must not be
    misclassified as a mere note."""
    from routers.kalendar import _klasifikuj_dogadjaj
    assert _klasifikuj_dogadjaj("Podnošenje tužbe sudu") == "rok_dokument"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-051 -- case closure rendered as 2 duplicate Timeline entries.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_intelligence_timeline_skips_synthesized_closure_when_hronologija_already_has_one():
    from routers.intelligence_timeline import intelligence_timeline

    table_data = {
        "predmeti": [_base_predmet("zatvoren")],
        "predmet_dokumenti": [],
        "rocista": [],
        "predmet_hronologija": [{
            "dogadjaj": "Predmet zatvoren — Ishod: Pobeda", "akter": "Advokat",
            "datum": "2026-02-01", "datum_iso": "2026-02-01", "vaznost": "kljucan",
        }],
        "predmet_genome_history": [],
        "audit_immutable": [],
    }
    supa = _FakeSupa(table_data)

    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline("p1", user={"user_id": "u1"})

    closure_events = [e for e in result["events"] if (e.get("naslov") or "").startswith("Predmet zatvoren")]
    assert len(closure_events) == 1
    assert not any(e["tip"] == "predmet_zatvoren" for e in result["events"])


@pytest.mark.anyio
async def test_intelligence_timeline_still_synthesizes_when_no_hronologija_closure_row():
    """Regression: status=='zatvoren' without a matching hronologija row must still get the
    synthesized entry (e.g. a case closed through a path that doesn't write one)."""
    from routers.intelligence_timeline import intelligence_timeline

    table_data = {
        "predmeti": [_base_predmet("zatvoren")],
        "predmet_dokumenti": [],
        "rocista": [],
        "predmet_hronologija": [],
        "predmet_genome_history": [],
        "audit_immutable": [],
    }
    supa = _FakeSupa(table_data)

    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline("p1", user={"user_id": "u1"})

    assert any(e["tip"] == "predmet_zatvoren" for e in result["events"])


@pytest.mark.anyio
async def test_intelligence_timeline_open_case_unaffected():
    """Regression: an open case never synthesizes a closure entry, matching pre-mission behavior."""
    from routers.intelligence_timeline import intelligence_timeline

    table_data = {
        "predmeti": [_base_predmet("aktivan")],
        "predmet_dokumenti": [],
        "rocista": [],
        "predmet_hronologija": [],
        "predmet_genome_history": [],
        "audit_immutable": [],
    }
    supa = _FakeSupa(table_data)

    with patch("routers.intelligence_timeline._get_supa", return_value=supa):
        result = await intelligence_timeline("p1", user={"user_id": "u1"})

    assert not any(e["tip"] == "predmet_zatvoren" for e in result["events"])


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-050 -- notification read-state was client-localStorage-only,
# never reconciled against the server's own procitano field (cross-device
# badge-count drift).
# ═══════════════════════════════════════════════════════════════════════════

def test_notif_load_merges_server_procitano_into_local_read_set():
    assert "async function notif_load() {" in VINDEX_JS
    body = VINDEX_JS.split("async function notif_load() {", 1)[1][:900]
    assert "if (n.procitano) _notifRead.add(n.id)" in body
    assert "localStorage.setItem('vx_notif_read'" in body
