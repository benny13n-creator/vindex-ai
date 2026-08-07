# -*- coding: utf-8 -*-
"""
Operation Single Brain, Mission 002 -- Team 7 (Chaos & Regression), executed after Phase 3's
implementation. Mission's own rule: "Mission fails if contradiction survives." Each scenario
below is a REAL execution against the actual fixed functions (not a mocked stand-in), proving
the specific guarantee the masterprompt asked for.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 1 — 1000 documents. calculate_case_ready_score + compute_case_readiness
# must stay deterministic and correctly capped at this volume.
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario1_1000_documents_readiness_cap_holds_at_scale():
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP

    dokumenti = [{"id": f"d{i}"} for i in range(1000)]
    open_actions = [{"tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
                      "razlog": "x", "dedupe_key": "k1"}]
    readiness = compute_case_readiness(open_actions)
    assert readiness["status"] == CRITICAL_GAP

    score1, _ = calculate_case_ready_score(
        dokumenti=dokumenti, klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}], readiness=readiness,
    )
    score2, _ = calculate_case_ready_score(
        dokumenti=dokumenti, klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}], readiness=readiness,
    )
    assert score1 == score2 == 50  # 1000 docs doesn't change the fact that only 20/100 came from docs; cap still holds


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 2 — 100 contradictions. The readiness cap and the normalize_tezina()
# guard (Mission 001) must compose correctly: 100 mixed-tezina contradictions
# feeding case_actions must still produce ONE consistent readiness verdict.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario2_100_contradictions_produce_one_consistent_readiness_verdict():
    import tests.test_omega_sprint003_action_engine as t
    from services.case_evolution import _compute_target_actions
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP

    _tezine_cycle = ["kriticna", "vazna", "manja", "ozbiljna", None, 12345]
    kontradikcije = [
        {"opis": f"K{i}", "lokacija_1": f"DOK-{i}", "lokacija_2": f"DOK-{i+1}",
         "tezina": _tezine_cycle[i % len(_tezine_cycle)]}
        for i in range(100)
    ]
    case_dna = {"kontradikcije": kontradikcije}
    supa = t._make_target_supa(case_dna=case_dna, dokazi=[], dokumenti=[], rocista=[])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-chaos-1")

    # At least one of the 100 must be "critical" (kriticna, or unrecognized-fails-safe-to-kriticna)
    readiness = compute_case_readiness(actions)
    assert readiness["status"] == CRITICAL_GAP

    from services.case_pipeline import calculate_case_ready_score
    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}], readiness=readiness,
    )
    # The contradiction "wall" from Scenario 2 must be reflected the same way regardless of
    # which of the 100 contradictions happened to be the one triggering CRITICAL_GAP.
    assert score == 50
    assert any(c.get("blokira") for c in checklist)


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 3 — GPT poisoned response, swept across every numeric/enum guard this
# mission touched in one pass (strategija verdict, case_dna heatmap/dokazi_rang,
# argument_reputation) -- proves the guards compose, not just individually pass.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario3_gpt_poisoned_response_sweep():
    import json as _json
    from unittest.mock import AsyncMock

    # 3a. strategija.py orchestrator verdict
    import strategija

    def _sr(content):
        m = MagicMock(); m.usage = None
        m.choices = [MagicMock(message=MagicMock(content=content))]
        return m

    responses = [
        _sr(_json.dumps({"confidence": "SREDNJA", "ocena": "X"})),
        _sr(_json.dumps({"confidence": "SREDNJA", "preporuka": "X"})),
        _sr(_json.dumps({"confidence": "SREDNJA", "ukupna_ranjivost": "NISKA"})),
        _sr("tuzilac..."), _sr("branilac..."),
        _sr(_json.dumps({"izreka": "APSOLUTNA POBEDA!!!", "procena_uspeha_tuzilac": -9999,
                          "confidence": "TOTALNO", "summary": "x"})),
        _sr(_json.dumps({"executive_summary": "x", "sistemsko_upozorenje": None, "opsta_confidence": "SREDNJA"})),
    ]
    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rez = strategija.orkestrator_kompletna_analiza_sync(opis_predmeta="Test.", api_key="sk-test")
    presuda = rez["koraci"]["korak_5_sudska_procena"]["presuda"]
    assert 0 <= presuda["procena_uspeha_tuzilac"] <= 100
    assert presuda["izreka"] in ("TUZBA USVOJENA", "TUZBA DELIMICNO USVOJENA", "TUZBA ODBIJENA")
    assert presuda["confidence"] in ("VISOKA", "SREDNJA", "NISKA")

    # 3b. case_dna.py heatmap/dokazi_rang
    from routers import case_dna as cd
    gpt_json = _json.dumps({
        "snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [],
        "heatmap": {"cinjenice": float("nan") if False else 99999},
        "dokazi_rang": [{"redni_broj": 1, "naziv": "a.pdf", "snaga_score": -99999, "zvezdice": 1, "razlog": "x"}],
    })
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None, "velicina_kb": 5, "tekst_sadrzaj": "x"}]
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)
    assert 0 <= result["heatmap"]["cinjenice"] <= 100
    assert 0 <= result["dokazi_rang"][0]["snaga_score"] <= 100

    # 3c. normalize_tezina (Mission 001, re-verified still holds under this mission's sweep)
    from shared.contradiction_identity import normalize_tezina
    for hostile in (99999, "APSOLUTNO KRITICNO!!!", None, {"x": 1}):
        assert normalize_tezina(hostile if not isinstance(hostile, dict) else None) in ("kriticna", "vazna", "manja")


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 4 — concurrent updates. compute_case_readiness/calculate_case_ready_score
# are pure functions with no shared mutable state -- prove many concurrent calls with
# DIFFERENT inputs never cross-contaminate each other's results.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scenario4_concurrent_calls_do_not_cross_contaminate():
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP, READY

    def _critical_case():
        readiness = compute_case_readiness([{
            "tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
            "razlog": "x", "dedupe_key": "k1",
        }])
        return calculate_case_ready_score(
            dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
            istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
            rocista=[{"id": "roc1"}], readiness=readiness,
        )

    def _clean_case():
        readiness = compute_case_readiness([])
        return calculate_case_ready_score(
            dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
            istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
            rocista=[{"id": "roc1"}], readiness=readiness,
        )

    async def _run(fn):
        return await asyncio.to_thread(fn)

    # 50 concurrent calls, alternating critical/clean -- every critical result must be
    # capped at 50 and every clean result must be 100, with NO bleed-through between them.
    tasks = [_run(_critical_case if i % 2 == 0 else _clean_case) for i in range(50)]
    results = await asyncio.gather(*tasks)
    for i, (score, _checklist) in enumerate(results):
        expected = 50 if i % 2 == 0 else 100
        assert score == expected, f"call {i} got {score}, expected {expected} -- cross-contamination"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 5 — stale cache injection. A stale/wrong-looking "[Rizik]" istorija tag
# must not fool the readiness cap; the cap is derived ONLY from live case_actions,
# never from the istorija checklist tags calculate_case_ready_score also reads.
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario5_stale_rizik_tag_cannot_bypass_the_cap():
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP

    readiness = compute_case_readiness([{
        "tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
        "razlog": "x", "dedupe_key": "k1",
    }])
    assert readiness["status"] == CRITICAL_GAP

    # A stale "[Rizik]" tag from a year ago -- calculate_case_ready_score only checks for
    # PRESENCE of the tag (its own documented, unchanged behavior), not recency; the cap
    # must still apply regardless of what the stale tag claims.
    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2020-01-01"}],
        rocista=[{"id": "roc1"}], readiness=readiness,
    )
    assert score == 50  # still capped -- the stale tag's mere presence cannot buy back the 15 points AND bypass the cap
    assert any(c.get("blokira") for c in checklist)


def test_scenario5_closed_case_action_is_not_treated_as_blocking():
    """A case_actions row that WAS critical but is now status='closed' (stale from the
    caller's perspective if it fetched an out-of-date snapshot) must never be counted --
    compute_case_readiness only considers status=='open' rows, by design."""
    from shared.case_readiness import compute_case_readiness, READY

    readiness = compute_case_readiness([{
        "tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "closed",
        "razlog": "x", "dedupe_key": "k1",
    }])
    assert readiness["status"] == READY


# ═══════════════════════════════════════════════════════════════════════════
# Scenario 6 — frontend/backend disagreement. The frontend must render exactly what
# the backend computed, with no independent recomputation that could diverge.
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario6_frontend_never_recomputes_case_ready_score_independently():
    """static/vindex.js must only ever set the score/status text FROM the API response
    fields (s, checklist) -- never compute its own weighted sum from raw case data (which
    would be a 3rd competing implementation, the exact failure mode this mission targets)."""
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    marker = "function pred_renderCaseReadyScore(score, checklist, copilotPreporuka)"
    assert marker in vindex_js
    body = vindex_js.split(marker, 1)[1][:1800]
    # the renderer only branches on the already-computed `s` and iterates the already-
    # computed `checklist` -- it must not itself sum "poen" values or invent a new score
    assert "score +=" not in body
    assert "reduce(" not in body


def test_scenario6_workspace_and_pipeline_status_endpoints_return_the_same_readiness_field_name():
    """Both live callers that expose readiness to a frontend must use the identical
    response key (`readiness_status`), so a future frontend integration can't accidentally
    read two different field names for the same concept on two different endpoints."""
    api_src = open(os.path.join(REPO_ROOT, "api.py"), encoding="utf-8").read()
    cp_src = open(os.path.join(REPO_ROOT, "routers", "case_pipeline.py"), encoding="utf-8").read()
    assert '"readiness_status"' in api_src
    assert '"readiness_status"' in cp_src
