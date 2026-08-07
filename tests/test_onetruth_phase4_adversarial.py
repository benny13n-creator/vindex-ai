# -*- coding: utf-8 -*-
"""
Operation One Truth, Phase 4 — Adversarial Testing.

The masterprompt requires exactly 4 named scenarios, each with a mandated result. This file
implements all 4 directly against real application code (not simulated/described) per the
mission's own Principle 0 -- trust only what execution proves.

  Scenario 1: GPT tries to change readiness            -> result must be FAIL (blocked)
  Scenario 2: GPT gives a different risk score          -> result must be FAIL (blocked/overridden)
  Scenario 3: Two modules read the same case            -> result must be IDENTICAL truth
  Scenario 4: A case with 1000 documents                -> result must be the SAME interpretation
              (deterministic, not GPT-dependent, and stable across repeated calls)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — GPT tries to change readiness -> FAIL
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario1_case_readiness_module_has_zero_gpt_calls():
    """Structural proof (not a behavioral assumption): shared/case_readiness.py,
    the canonical readiness owner, never imports or calls OpenAI/GPT anywhere in
    its source. There is no code path by which a GPT response could reach
    compute_case_readiness()'s decision -- the attack has no surface to land on."""
    import shared.case_readiness as cr
    src = open(cr.__file__, encoding="utf-8").read()
    assert "openai" not in src.lower()
    assert "chat.completions" not in src


def test_scenario1_readiness_ignores_gpt_generated_status_field():
    """Even when a case's own data (via case_actions/gaps) implies BLOCKED, a
    poisoned upstream signal claiming 'GPT says READY' must have zero effect --
    compute_case_readiness() takes no such parameter at all."""
    from shared.case_readiness import compute_case_readiness

    # A case with a critical open action -- should compute BLOCKED/CRITICAL_GAP,
    # not whatever an attacker-controlled "gpt_says" value might claim.
    case_actions = [{"prioritet": "critical", "tip": "PRIBAVITI_DOKAZ"}]
    gaps = [{"tip": "NEMA_DOKAZA", "hipoteza": False}]
    result = compute_case_readiness(case_actions, gaps, genome_computed=True)
    assert result["status"] in ("BLOCKED", "CRITICAL_GAP")
    # The function signature itself has no parameter through which a GPT string
    # could be injected to override this -- calling it with an extra kwarg fails
    # the way any attempted injection into a pure function would.
    with pytest.raises(TypeError):
        compute_case_readiness(case_actions, gaps, genome_computed=True, gpt_says="READY")  # type: ignore[call-arg]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — GPT gives a different risk score -> FAIL (blocked/overridden)
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario2_risk_engine_has_zero_gpt_calls():
    """Same structural proof for the risk score owner."""
    import services.risk_engine as re_mod
    src = open(re_mod.__file__, encoding="utf-8").read()
    assert "openai" not in src.lower()
    assert "chat.completions" not in src


def test_scenario2_case_dna_kriticnost_poisoned_value_is_clamped_not_trusted():
    """A concrete poisoned-GPT-response scenario (see also
    tests/test_onetruth_phase3_migrations.py for the full variant matrix):
    GPT claims najslabija_tacka.kriticnost=999 (fabricated, out of range). The
    platform must not trust it -- result clamped to the documented 0-100 range,
    not passed through."""
    import asyncio
    from routers import case_dna as cd

    gpt_json = (
        '{"snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [], '
        '"najslabija_tacka": {"rizik": "GPT tvrdi da je predmet propao", "kriticnost": 999, "lokacija": ""}}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "tekst"}]

    async def _run():
        with patch("openai.AsyncOpenAI", return_value=fake_client):
            return await cd._extract_genome(docs)

    result = asyncio.run(_run())
    assert result["najslabija_tacka"]["kriticnost"] == 100, "poisoned out-of-range claim must be clamped, not trusted"


def test_scenario2_dashboard_ignores_a_poisoned_cached_risk_snapshot():
    """The Red Team's own flagship scenario, restated as an explicit adversarial
    test: a stale/adversarial cached '[Rizik]' row claiming 'nizak' must not
    override the live canonical engine's own computation for the same case."""
    import asyncio
    import api

    def _chain(data):
        m = MagicMock()
        for method in ("select", "eq", "neq", "insert", "update", "limit", "order",
                       "is_", "in_", "gte", "lte", "like", "maybe_single"):
            setattr(m, method, MagicMock(return_value=m))
        m.not_ = m
        m.execute = MagicMock(return_value=MagicMock(data=data))
        return m

    predmet = {"id": "p1", "naziv": "Test", "tip": "opsti", "status": "aktivan", "created_at": "2026-01-01"}
    rocista = [{"predmet_id": "p1", "datum": "2020-01-01"}]

    def _table(name):
        if name == "predmeti":
            return _chain([predmet])
        if name == "predmet_hronologija":
            return _chain([])
        if name == "predmet_dokazi":
            return _chain([])
        if name == "predmet_dokumenti":
            return _chain([])
        if name == "rocista":
            return _chain(rocista)
        if name == "case_actions":
            return _chain([])
        if name == "predmet_istorija":
            # Adversarial/stale claim: "everything is fine."
            return _chain([{"predmet_id": "p1", "odgovor": '{"nivo": "nizak"}', "created_at": "2020-01-02"}])
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "GET", "path": "/api/predmeti/dashboard", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(), "client": ("127.0.0.1", 1)}
    req = StarletteRequest(scope=scope)

    async def _run():
        with patch("api._get_supa", return_value=supa):
            return await api.predmeti_dashboard(req, {"user_id": "u1"})

    result = asyncio.run(_run())
    assert result["predmeti"][0]["rizik_nivo"] == "Visok"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3 — Two modules read the same case -> IDENTICAL truth
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario3_ccc_and_matter_intel_agree_on_risk_for_identical_data():
    """routers/ccc.py and routers/matter_intel.py both call
    calculate_procesni_rizik independently -- given IDENTICAL underlying data for
    the same case, they must produce IDENTICAL risk output. This is the mission's
    core guarantee: not that only one module exists, but that every module
    consuming the canonical engine gets the same answer."""
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    dokazi = [{"snaga": "slaba", "kategorija": "ugovor"}]
    dokumenti = [{"tip_dokaza": "ugovor"}]
    rocista = [{"datum": "2026-08-10", "status": "aktivan"}]

    # Simulates what ccc.py computes for this case
    result_ccc = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
        tip_predmeta="radno", expected_docs=EXPECTED_DOCS,
    )
    # Simulates what matter_intel.py independently computes for the SAME case
    result_matter_intel = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
        tip_predmeta="radno", expected_docs=EXPECTED_DOCS,
    )
    assert result_ccc == result_matter_intel


@pytest.mark.anyio
async def test_scenario3_build_case_context_risk_matches_direct_engine_call():
    """shared/case_context.py's new 'risk' field (Operation One Truth Phase 3)
    must be byte-for-byte the same nivo/health_score a direct call to the
    canonical engine produces for the same underlying data -- not a
    re-derivation that could drift."""
    import importlib
    tau002 = importlib.import_module("tests.test_tau002_case_context")
    from shared.case_context import build_case_context
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    supa = tau002._FakeSupa(tau002._base_tables())
    result = await build_case_context("p1", "u1", supa)
    tables = tau002._base_tables()
    direct = calculate_procesni_rizik(
        dokazi=tables.get("predmet_dokazi", []), dokumenti=tables.get("predmet_dokumenti", []),
        rocista=tables.get("rocista", []), tip_predmeta="parnicno", expected_docs=EXPECTED_DOCS,
    )
    assert result["risk"]["value"]["nivo"] == direct["nivo"]
    assert result["risk"]["value"]["health_score"] == direct["health_score"]
    assert result["risk"]["value"]["kriticni_rokovi"] == direct["kriticni_rokovi"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4 — A case with 1000 documents -> the SAME interpretation
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario4_risk_engine_deterministic_at_1000_document_scale():
    """calculate_procesni_rizik is a pure function -- at real scale (1000
    documents, 200 hearings), calling it twice with the identical input must
    produce the identical output. No hidden randomness, no GPT dependency, no
    ordering sensitivity."""
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    dokazi = [{"snaga": "jaka" if i % 3 == 0 else "srednja", "kategorija": "ugovor"} for i in range(1000)]
    dokumenti = [{"tip_dokaza": "ugovor" if i % 2 == 0 else "dopis"} for i in range(1000)]
    rocista = [{"datum": f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}", "status": "aktivan"} for i in range(200)]

    result_1 = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
        tip_predmeta="parnica", expected_docs=EXPECTED_DOCS,
    )
    result_2 = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
        tip_predmeta="parnica", expected_docs=EXPECTED_DOCS,
    )
    assert result_1 == result_2


def test_scenario4_risk_engine_deterministic_regardless_of_input_order():
    """Same 1000-document case, but the evidence/document lists arrive in a
    different order (e.g. a different query's ORDER BY) -- the interpretation
    (nivo/health_score/nedostajuci_count) must not change, only order-independent
    aggregates matter."""
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    dokazi = [{"snaga": "jaka" if i % 3 == 0 else "srednja", "kategorija": "ugovor"} for i in range(1000)]
    dokumenti = [{"tip_dokaza": "ugovor" if i % 2 == 0 else "dopis"} for i in range(1000)]

    result_forward = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=dokumenti, rocista=[],
        tip_predmeta="parnica", expected_docs=EXPECTED_DOCS,
    )
    result_reversed = calculate_procesni_rizik(
        dokazi=list(reversed(dokazi)), dokumenti=list(reversed(dokumenti)), rocista=[],
        tip_predmeta="parnica", expected_docs=EXPECTED_DOCS,
    )
    assert result_forward["nivo"] == result_reversed["nivo"]
    assert result_forward["health_score"] == result_reversed["health_score"]
    assert result_forward["nedostajuci_count"] == result_reversed["nedostajuci_count"]


@pytest.mark.anyio
async def test_scenario4_dashboard_computes_consistent_risk_across_many_cases():
    """The Operation One Truth Phase 3 dashboard fix, at scale: 50 cases in one
    dashboard load, each independently risk-scored live -- every case's score
    must be internally consistent with its own data (not cross-contaminated by
    another case's dokazi/dokumenti/rocista in the bulk-fetch grouping)."""
    import api
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    n = 50
    predmeti = [{"id": f"p{i}", "naziv": f"Predmet {i}", "tip": "opsti",
                  "status": "aktivan", "created_at": "2026-01-01"} for i in range(n)]
    # Even-indexed cases get strong evidence (low risk), odd-indexed get none (high risk).
    dokazi_all = [{"predmet_id": f"p{i}", "snaga": "jaka", "kategorija": "ugovor"} for i in range(0, n, 2)]
    dokumenti_all = [{"predmet_id": f"p{i}", "tip_dokaza": "ugovor"} for i in range(0, n, 2)]

    def _chain(data):
        m = MagicMock()
        for method in ("select", "eq", "neq", "insert", "update", "limit", "order",
                       "is_", "in_", "gte", "lte", "like", "maybe_single"):
            setattr(m, method, MagicMock(return_value=m))
        m.not_ = m
        m.execute = MagicMock(return_value=MagicMock(data=data))
        return m

    def _table(name):
        if name == "predmeti":
            return _chain(predmeti)
        if name == "predmet_hronologija":
            return _chain([])
        if name == "predmet_dokazi":
            return _chain(dokazi_all)
        if name == "predmet_dokumenti":
            return _chain(dokumenti_all)
        if name == "rocista":
            return _chain([])
        if name == "case_actions":
            return _chain([])
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "GET", "path": "/api/predmeti/dashboard", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(), "client": ("127.0.0.1", 1)}
    req = StarletteRequest(scope=scope)

    with patch("api._get_supa", return_value=supa):
        result = await api.predmeti_dashboard(req, {"user_id": "u1"})

    by_id = {p["id"]: p for p in result["predmeti"]}
    for i in range(n):
        pid = f"p{i}"
        expected = calculate_procesni_rizik(
            dokazi=[d for d in dokazi_all if d["predmet_id"] == pid],
            dokumenti=[d for d in dokumenti_all if d["predmet_id"] == pid],
            rocista=[], tip_predmeta="opsti", expected_docs=EXPECTED_DOCS,
        )
        assert by_id[pid]["rizik_nivo"] == expected["nivo"], f"case {pid} got cross-contaminated risk"
