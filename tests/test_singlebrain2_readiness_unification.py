# -*- coding: utf-8 -*-
"""
Operation Single Brain, Mission 002 -- regression coverage for the Case Readiness
unification fix. See docs/singlebrain/READINESS_AUTHORITY_SPEC.md for the CANONICAL_OWNER
contract this implements.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_request(path="/api/predmeti/p1/pipeline/status"):
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": path, "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
VINDEX_JS = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# Team 2's flagship reproduction: a full checklist (100/100 "spreman") on a case
# where the canonical readiness engine has already found a blocking CRITICAL_GAP.
# Before this fix: calculate_case_ready_score had no way to know about the gap.
# ═══════════════════════════════════════════════════════════════════════════

def test_case_ready_score_capped_when_canonical_readiness_is_critical_gap():
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP

    istorija = [
        {"pitanje": "[Strategija Pipeline] Inicijalna procena"},
        {"pitanje": "[Rizik] 2026-08-07"},
    ]
    open_actions = [{
        "tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
        "razlog": "Nedostaje ugovor o zakupu overen kod notara", "dedupe_key": "k1",
    }]
    readiness = compute_case_readiness(open_actions)
    assert readiness["status"] == CRITICAL_GAP  # sanity check on the canonical engine itself

    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=istorija, rocista=[{"id": "roc1"}],
        readiness=readiness,
    )
    assert score == 50  # CAP_BY_READINESS[CRITICAL_GAP], not the uncapped 100
    blocking_items = [c for c in checklist if c.get("blokira")]
    assert len(blocking_items) == 1
    assert "CRITICAL_GAP" in blocking_items[0]["stavka"]
    assert "notara" in blocking_items[0]["stavka"]  # the actual razlog is surfaced, not just the enum


def test_case_ready_score_capped_when_canonical_readiness_is_blocked():
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, BLOCKED

    open_actions = [{
        "tip": "RAZRESITI_KONTRADIKCIJU", "prioritet": "high", "status": "open",
        "razlog": "Kontradikcija u datumima nije razrešena", "dedupe_key": "k2",
    }]
    readiness = compute_case_readiness(open_actions)
    assert readiness["status"] == BLOCKED

    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}],
        readiness=readiness,
    )
    assert score == 65  # CAP_BY_READINESS[BLOCKED]


def test_case_ready_score_not_capped_when_readiness_is_ready():
    """A clean case (no open actions, no gaps) must NOT be artificially capped --
    this is the direct anti-regression check against over-correction."""
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness, READY

    readiness = compute_case_readiness([])
    assert readiness["status"] == READY

    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}],
        readiness=readiness,
    )
    assert score == 100
    assert not any(c.get("blokira") for c in checklist)


def test_case_ready_score_backward_compatible_with_no_readiness_argument():
    """Every pre-existing caller/test that doesn't pass `readiness` must see byte-identical
    behavior to before this mission -- additive change, not a breaking signature change."""
    from services.case_pipeline import calculate_case_ready_score
    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}],
        rocista=[{"id": "roc1"}],
    )
    assert score == 100
    assert len(checklist) == 6  # no extra blocking item appended


def test_case_ready_score_not_capped_when_checklist_already_below_cap():
    """A partially-set-up case whose checklist score is already lower than the cap must not
    be artificially RAISED or otherwise altered by the presence of a CRITICAL_GAP."""
    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness

    readiness = compute_case_readiness([{
        "tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
        "razlog": "x", "dedupe_key": "k3",
    }])
    score, checklist = calculate_case_ready_score(
        dokumenti=[], klijenti=[{"klijent_id": "k1"}], rokovi=[{"id": "r1"}],
        istorija=[], rocista=[],
        readiness=readiness,
    )
    assert score == 35  # 20 + 15, already below the 50 cap -- untouched
    # still surfaced for transparency even when it didn't need to cap anything numerically
    assert any(c.get("blokira") for c in checklist)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint-level wiring: all 3 real callers now fetch case_actions and pass readiness.
# ═══════════════════════════════════════════════════════════════════════════

def test_workspace_endpoint_fetches_case_actions_for_readiness():
    src = open(os.path.join(REPO_ROOT, "api.py"), encoding="utf-8").read()
    marker = 'supa.table("case_actions").select("prioritet,tip,status,razlog,dedupe_key")'
    assert marker in src
    assert "readiness=_ws_readiness" in src
    assert '"readiness_status":   (_ws_readiness or {}).get("status")' in src


def test_pipeline_status_endpoint_fetches_case_actions_for_readiness():
    src = open(os.path.join(REPO_ROOT, "routers", "case_pipeline.py"), encoding="utf-8").read()
    assert 'supa.table("case_actions")' in src
    assert "readiness=_readiness" in src
    assert '"readiness_status": _readiness.get("status")' in src


def test_run_case_pipeline_fetches_case_actions_for_readiness():
    src = open(os.path.join(REPO_ROOT, "services", "case_pipeline.py"), encoding="utf-8").read()
    assert 'supa.table("case_actions")' in src
    assert "readiness=_readiness" in src


@pytest.mark.anyio
async def test_pipeline_status_endpoint_execution_returns_capped_score():
    from routers.case_pipeline import pipeline_status

    def _chain(data):
        c = MagicMock()
        for m in ("select", "eq", "execute"):
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            return _chain([{"id": "p1"}])
        if name == "predmet_dokumenti":
            return _chain([{"id": "d1"}])
        if name == "predmet_klijenti":
            return _chain([{"klijent_id": "k1"}])
        if name == "predmet_hronologija":
            return _chain([{"id": "r1"}])
        if name == "predmet_istorija":
            return _chain([{"pitanje": "[Strategija Pipeline] x"}, {"pitanje": "[Rizik] 2026-08-07"}])
        if name == "rocista":
            return _chain([{"id": "roc1"}])
        if name == "case_actions":
            return _chain([{"tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
                             "razlog": "Nedostaje dokaz", "dedupe_key": "k1"}])
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    user = {"user_id": "u1", "email": "x@vindex.rs"}

    with patch("routers.case_pipeline._get_supa", return_value=supa):
        result = await pipeline_status(predmet_id="p1", request=_fake_request(), user=user)

    assert result["case_ready_score"] == 50
    assert result["readiness_status"] == "CRITICAL_GAP"
    assert any(c.get("blokira") for c in result["checklist"])


# ═══════════════════════════════════════════════════════════════════════════
# Frontend: the blocking checklist item must render distinctly (warning color/icon),
# not blend into ordinary unchecked items.
# ═══════════════════════════════════════════════════════════════════════════

def test_frontend_renders_blocking_checklist_item_as_warning():
    marker = "var clEl = document.getElementById('pred-crs-checklist');"
    block = VINDEX_JS.split(marker, 1)[1][:900]
    assert "it.blokira" in block
    assert "'⚠'" in block


# ═══════════════════════════════════════════════════════════════════════════
# SINGLEBRAIN-DEBT-002 closure: argument_reputation gains the readiness-tier cap
# already applied to its sibling prediktuj_ishod in the same file.
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Team 3's most serious finding: strategija.py's F10 "AI Sudija" verdict step
# (orkestrator_kompletna_analiza_sync) had zero server-side clamp/validation on
# procena_uspeha_tuzilac/izreka/confidence -- a poisoned GPT response was proven
# to reach the real, UI-wired /api/strategija/kompletna-analiza response unmodified.
# ═══════════════════════════════════════════════════════════════════════════

def _strat_resp(content: str):
    m = MagicMock()
    m.usage = None
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


def test_orkestrator_clamps_poisoned_ai_sudija_verdict():
    import json as _json
    import strategija

    responses = [
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "ocena": "SPREMAN ZA UPOTREBU"})),   # korak1 revizor
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "preporuka": "PREGOVARATI"})),        # korak2 due diligence
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "ukupna_ranjivost": "NISKA"})),       # korak4 red team
        _strat_resp("Argumenti tuzioca..."),                                                     # korak5: tuzilac (text)
        _strat_resp("Argumenti branioca..."),                                                    # korak5: branilac (text)
        _strat_resp(_json.dumps({                                                                # korak5: presuda -- POISONED
            "izreka": "TUZBA SIGURNO USVOJENA STOPOSTOTNO",
            "procena_uspeha_tuzilac": 9999,
            "confidence": "APSOLUTNO SIGURNO",
            "summary": "test",
        })),
        _strat_resp(_json.dumps({                                                                # korak6 synthesis
            "executive_summary": "test", "sistemsko_upozorenje": None, "opsta_confidence": "SREDNJA",
        })),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    presuda = rezultat["koraci"]["korak_5_sudska_procena"]["presuda"]
    assert presuda["procena_uspeha_tuzilac"] == 100  # clamped, not the poisoned 9999
    assert presuda["izreka"] in ("TUZBA USVOJENA", "TUZBA DELIMICNO USVOJENA", "TUZBA ODBIJENA")
    assert presuda["confidence"] in ("VISOKA", "SREDNJA", "NISKA")


def test_orkestrator_leaves_well_formed_verdict_unchanged():
    import json as _json
    import strategija

    responses = [
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "ocena": "SPREMAN ZA UPOTREBU"})),
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "preporuka": "PREGOVARATI"})),
        _strat_resp(_json.dumps({"confidence": "SREDNJA", "ukupna_ranjivost": "NISKA"})),
        _strat_resp("Argumenti tuzioca..."),
        _strat_resp("Argumenti branioca..."),
        _strat_resp(_json.dumps({
            "izreka": "TUZBA ODBIJENA", "procena_uspeha_tuzilac": 42, "confidence": "SREDNJA", "summary": "test",
        })),
        _strat_resp(_json.dumps({
            "executive_summary": "test", "sistemsko_upozorenje": None, "opsta_confidence": "SREDNJA",
        })),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    presuda = rezultat["koraci"]["korak_5_sudska_procena"]["presuda"]
    assert presuda["procena_uspeha_tuzilac"] == 42
    assert presuda["izreka"] == "TUZBA ODBIJENA"
    assert presuda["confidence"] == "SREDNJA"


# ═══════════════════════════════════════════════════════════════════════════
# Team 3 finding #2: case_dna.py's heatmap/dokazi_rang[].snaga_score sub-fields
# were never clamped -- only the headline snaga_predmeta_procent/kriticnost/
# genome_kompletnost fields got this discipline in prior missions.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_extract_genome_clamps_poisoned_heatmap_and_dokazi_rang():
    from routers import case_dna as cd
    from unittest.mock import AsyncMock
    import json as _json

    gpt_json = _json.dumps({
        "snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": [],
        "heatmap": {"cinjenice": 9999, "dokazi": -50, "praksa": 74, "vestaci": "not-a-number", "rizici": 78, "rokovi": 60},
        "dokazi_rang": [
            {"redni_broj": 1, "naziv": "a.pdf", "snaga_score": 9999, "zvezdice": 5, "razlog": "x"},
            {"redni_broj": 2, "naziv": "b.pdf", "snaga_score": -30, "zvezdice": 1, "razlog": "y"},
        ],
    })
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "neki tekst dokumenta"}]
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)

    assert result["heatmap"]["cinjenice"] == 100
    assert result["heatmap"]["dokazi"] == 0
    assert result["heatmap"]["vestaci"] == 0  # non-numeric fails safe to 0, not left raw
    assert result["heatmap"]["praksa"] == 74  # well-formed values pass through unchanged
    assert result["dokazi_rang"][0]["snaga_score"] == 100
    assert result["dokazi_rang"][1]["snaga_score"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Team 6 finding: ccc.py's hearing query had `.limit(10)` while matter_intel.py's
# equivalent query (feeding the SAME calculate_procesni_rizik call) was unbounded --
# structural check, since this repo's MagicMock-chain test fixtures don't actually
# apply `.limit()` to their canned data (same limitation noted throughout this
# mission for column-projection/filter checks -- an execution test here couldn't
# distinguish old from new behavior).
# ═══════════════════════════════════════════════════════════════════════════

def test_ccc_hearing_query_no_longer_limited():
    src = open(os.path.join(REPO_ROOT, "routers", "ccc.py"), encoding="utf-8").read()
    marker = 'supa.table("rocista").select('
    block = src.split(marker, 1)[1][:300]
    assert ".limit(10)" not in block
    assert ".order(\"datum\").execute()" in block


def test_argument_reputation_has_readiness_tier_cap():
    src = open(os.path.join(REPO_ROOT, "routers", "court_predictor.py"), encoding="utf-8").read()
    marker = 'rezultat["ukupna_snaga"] = max(0, min(100, _ukupna))'
    block = src.split(marker, 1)[1][:1400]
    assert "SINGLEBRAIN-DEBT-002" in block
    assert "_cap = CAP_BY_READINESS.get(_readiness_status)" in block
    assert '_a["uspesnost_procena"] = _cap' in block
    assert 'rezultat["ukupna_snaga"] = _cap' in block
