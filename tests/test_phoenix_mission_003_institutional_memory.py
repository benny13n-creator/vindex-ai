# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 003 -- Institutional Memory & Canonical Registry Cleanup.
Closes LIVINGSYS-DEBT-008, -052, -017, -055.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-008 — firm_memory.py's .order("vaznost") sorted alphabetically
# ascending (LOW before HIGH importance) at all 5 call sites.
# ═══════════════════════════════════════════════════════════════════════════

def test_firm_memory_all_vaznost_orderings_are_descending():
    src = open(os.path.join(REPO_ROOT, "routers", "firm_memory.py"), encoding="utf-8").read()
    # Strip lines that are pure comments so the explanatory header comment (which itself
    # mentions the old/new call shape as prose) doesn't get counted as real code.
    code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    import re
    matches = re.findall(r'\.order\("vaznost"[^)]*\)', code)
    assert len(matches) == 5  # exactly 5 real call sites, per the mission's own reproduction
    for m in matches:
        assert "desc=True" in m, f"found an ascending vaznost order: {m}"


@pytest.mark.anyio
async def test_kontekst_za_ai_returns_high_importance_memories_first():
    """Direct behavioral proof for the AI-context endpoint specifically (the debt item's own
    flagship example -- text injected directly into the GPT system prompt). Uses a stateful
    fake that actually sorts by the requested order, unlike the repo's usual MagicMock
    passthrough fixtures -- needed to prove desc=True actually changes output order."""
    from routers import firm_memory as fm

    rows = [
        {"tip": "klijent_preferenca", "sadrzaj": "Niska vaznost fakt", "vaznost": "niska"},
        {"tip": "sudija_obrazac", "sadrzaj": "Visoka vaznost fakt", "vaznost": "visoka"},
        {"tip": "partner_odbijanje", "sadrzaj": "Normalna vaznost fakt", "vaznost": "normalna"},
    ]

    class _Query:
        def __init__(self, data):
            self._data = data
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def order(self, col, desc=False):
            self._data = sorted(self._data, key=lambda r: r.get(col, ""), reverse=desc)
            return self
        def limit(self, n):
            self._data = self._data[:n]
            return self
        def execute(self):
            r = MagicMock(); r.data = self._data
            return r

    def _table(name):
        if name == "memory_entries":
            return _Query(list(rows))
        if name == "kancelarije":
            r = MagicMock(); r.data = {"id": "kanc-1"}
            q = MagicMock(); q.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = r
            return q
        return _Query([])

    supa = MagicMock()
    supa.table.side_effect = _table

    from starlette.requests import Request as StarletteRequest

    def _req():
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [],
                  "query_string": b"", "app": MagicMock(), "state": MagicMock(),
                  "client": ("127.0.0.1", 1234)}
        return StarletteRequest(scope=scope)

    with patch.object(fm, "_get_supa", return_value=supa):
        result = await fm.kontekst_za_ai(_req(), {"user_id": "u1"}, sudija_ime="Petrović")

    assert result["memorije_count"] == 3
    # The first fact line under the sudija section must be the HIGH-importance one.
    joined = "\n".join(result["kontekst"]) if isinstance(result["kontekst"], list) else result["kontekst"]
    visoka_idx = joined.find("Visoka vaznost fakt")
    niska_idx = joined.find("Niska vaznost fakt")
    assert visoka_idx != -1 and niska_idx != -1
    assert visoka_idx < niska_idx


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-052 — memory_graph.py had a byte-identical duplicate of
# shared/kancelarija_utils.py::get_kancelarija_id.
# ═══════════════════════════════════════════════════════════════════════════

def test_memory_graph_reuses_canonical_kancelarija_helper():
    import routers.memory_graph as mg
    from shared.kancelarija_utils import get_kancelarija_id
    assert mg._get_firma_id is get_kancelarija_id


def test_memory_graph_has_no_local_duplicate_definition():
    src = open(os.path.join(REPO_ROOT, "routers", "memory_graph.py"), encoding="utf-8").read()
    assert 'async def _get_firma_id(supa, uid' not in src


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-017 — shared/semantic_registry.py had no entry for "Probability".
# ═══════════════════════════════════════════════════════════════════════════

def test_semantic_registry_has_probability_concept():
    from shared.semantic_registry import get_owner, is_valid_value, PROBABILITY, ALL_CONCEPTS
    assert PROBABILITY in ALL_CONCEPTS
    owner = get_owner("probability")
    assert owner is not None
    assert owner is PROBABILITY
    # Numeric/unstructured concept -- any value should be considered structurally valid
    # (the registry's own convention for allowed_values=None, e.g. HEALTH_FIRM/RECOMMENDATION).
    assert is_valid_value("probability", "anything") is True


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-055 — bare except in calculate_procesni_rizik's hearing-date
# loop silently dropped malformed-date hearings with no signal.
# ═══════════════════════════════════════════════════════════════════════════

def test_risk_engine_logs_malformed_hearing_date(caplog):
    import logging
    from services.risk_engine import calculate_procesni_rizik

    caplog.set_level(logging.WARNING, logger="vindex.risk_engine")
    rocista = [{"id": "r-bad", "datum": "not-a-date", "status": "zakazano"}]

    result = calculate_procesni_rizik(
        dokazi=[], dokumenti=[], rocista=rocista, tip_predmeta="opsti", expected_docs={"ostalo": []},
    )

    assert result is not None  # behavior unchanged -- still returns a valid result
    assert any("nevalidnim datumom" in r.message for r in caplog.records)
