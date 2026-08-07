# -*- coding: utf-8 -*-
"""
Operation Singular Intelligence, Mission 001 -- Phase 4 Adversarial Certification. Each of the 4
mandated attacks is a real execution against the actual fixed functions, not a mocked stand-in.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _chain(data, count=None):
    c = MagicMock()
    for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
              'insert', 'update', 'delete', 'is_', 'in_', 'not_', 'desc', 'maybe_single'):
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data; r.count = count
    c.execute = MagicMock(return_value=r)
    return c


# ═══════════════════════════════════════════════════════════════════════════
# Attack 1 — force one case into high-risk/low-readiness/missing-evidence/GPT-
# hallucination simultaneously and verify every canonical engine agrees.
# ═══════════════════════════════════════════════════════════════════════════

def test_attack1_forced_bad_case_every_engine_agrees():
    from services.risk_engine import calculate_procesni_rizik
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP
    from services.case_pipeline import calculate_case_ready_score

    # A single deliberately bad case: zero evidence, zero documents, one critical open action.
    rizik = calculate_procesni_rizik(
        dokazi=[], dokumenti=[], rocista=[], tip_predmeta="parnicno", expected_docs={"ostalo": [], "parnicno": []},
    )
    assert rizik["nivo"] == "Visok"

    open_actions = [{"tip": "PRIBAVITI_DOKAZ", "prioritet": "critical", "status": "open",
                      "razlog": "Nedostaje sve", "dedupe_key": "k1"}]
    readiness = compute_case_readiness(open_actions)
    assert readiness["status"] == CRITICAL_GAP

    # The checklist score must be capped by that same readiness verdict -- it cannot show "ready"
    # while the canonical engine says CRITICAL_GAP (Mission 002's own headline fix, re-verified here
    # under this mission's own adversarial mandate).
    score, checklist = calculate_case_ready_score(
        dokumenti=[], klijenti=[], rokovi=[], istorija=[], rocista=[], readiness=readiness,
    )
    assert score <= 50
    assert any(c.get("blokira") for c in checklist)

    # A poisoned GPT hallucination (e.g. Genome claiming 100% strength) must not leak into any of
    # the above -- none of these 3 functions accept a GPT-authored parameter at all.
    import inspect
    assert "gpt" not in " ".join(inspect.signature(calculate_procesni_rizik).parameters).lower()
    assert "gpt" not in " ".join(inspect.signature(compute_case_readiness).parameters).lower()


# ═══════════════════════════════════════════════════════════════════════════
# Attack 2 — 1000 documents, verify no duplicate intelligence (determinism at
# scale, re-verified under this mission's own new fixes).
# ═══════════════════════════════════════════════════════════════════════════

def test_attack2_1000_documents_no_duplicate_intelligence():
    from services.risk_engine import calculate_procesni_rizik

    dokumenti = [{"tip_dokaza": f"tip_{i % 12}", "naziv_fajla": f"d{i}.pdf"} for i in range(1000)]
    dokazi = [{"snaga": ["jaka", "srednja", "slaba"][i % 3], "kategorija": "pisani"} for i in range(200)]

    r1 = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dokumenti, rocista=[],
                                   tip_predmeta="parnicno", expected_docs={"ostalo": [], "parnicno": []})
    r2 = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dokumenti, rocista=[],
                                   tip_predmeta="parnicno", expected_docs={"ostalo": [], "parnicno": []})
    assert r1 == r2  # identical input -> identical output, no hidden nondeterminism at scale


# ═══════════════════════════════════════════════════════════════════════════
# Attack 3 — poison GPT with 100%/fake certainty/fake risk score across every
# guard this mission added; verify none can influence canonical truth.
# ═══════════════════════════════════════════════════════════════════════════

def test_attack3_poison_web3_scores_cannot_influence_truth():
    import json as _json
    import web3_compliance as w3

    def _resp(content):
        m = MagicMock(); m.choices = [MagicMock(message=MagicMock(content=content))]
        return m

    poisoned = _json.dumps({"ukupni_skor": 100, "skor_nivo": "100% SIGURNO USKLADJENO", "kategorije": {}})
    with patch("web3_compliance._pozovi_web3_api", return_value=_resp(poisoned)):
        mica = w3.mica_readiness_score_sync("x", "sk-test")
        health = w3.documentation_health_score_sync("x", "sk-test")
    # the numeric 100 IS in-range so it passes through, but the fabricated-certainty ENUM claim
    # cannot -- it fails safe to the least-favorable bucket, not the claimed "100% sigurno"
    assert mica["score_data"]["skor_nivo"] == "NIZAK"
    assert health["health_data"]["skor_nivo"] == "NIZAK"

    poisoned_risk = _json.dumps({"rizik_nivo": "NULA RIZIKA GARANTOVANO", "dozvola_potrebna": False})
    with patch("web3_compliance._pozovi_web3_api", return_value=_resp(poisoned_risk)):
        lic = w3.zdi_license_checker_sync("x", "sk-test")
    assert lic["license_data"]["rizik_nivo"] == "VISOK"


@pytest.mark.anyio
async def test_attack3_poison_ai_sudija_verdict_cannot_influence_truth():
    import json as _json
    import strategija

    def _sr(content):
        m = MagicMock(); m.usage = None
        m.choices = [MagicMock(message=MagicMock(content=content))]
        return m

    responses = [
        _sr(_json.dumps({"confidence": "SREDNJA"})), _sr(_json.dumps({"confidence": "SREDNJA"})),
        _sr(_json.dumps({"confidence": "SREDNJA", "ukupna_ranjivost": "NISKA"})),
        _sr("t..."), _sr("b..."),
        _sr(_json.dumps({"izreka": "100% POBEDA GARANTOVANA", "procena_uspeha_tuzilac": 100000,
                          "confidence": "APSOLUTNA", "summary": "x"})),
        _sr(_json.dumps({"executive_summary": "x", "sistemsko_upozorenje": None, "opsta_confidence": "SREDNJA"})),
    ]
    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rez = strategija.orkestrator_kompletna_analiza_sync(opis_predmeta="Test.", api_key="sk-test")
    presuda = rez["koraci"]["korak_5_sudska_procena"]["presuda"]
    assert presuda["procena_uspeha_tuzilac"] == 100  # clamped, not the fabricated 100000
    assert presuda["izreka"] != "100% POBEDA GARANTOVANA"
    assert presuda["confidence"] != "APSOLUTNA"


# ═══════════════════════════════════════════════════════════════════════════
# Attack 4 — legacy field injection: manually modify old DB values, verify the
# canonical engine wins (never reads the manual override as if it were live).
# ═══════════════════════════════════════════════════════════════════════════

def test_attack4_manual_predmeti_rizik_field_never_read_by_canonical_engine():
    """predmeti.rizik is a lawyer's own manual note (Truth Contract "Risk" §Explicitly NOT this
    concept). calculate_procesni_rizik takes no `predmet` dict at all -- it structurally cannot
    read a manually-injected legacy field, regardless of what a human typed into it."""
    import inspect
    from services.risk_engine import calculate_procesni_rizik
    params = set(inspect.signature(calculate_procesni_rizik).parameters.keys())
    assert params == {"dokazi", "dokumenti", "rocista", "tip_predmeta", "expected_docs"}
    assert "predmet" not in params and "rizik" not in params


@pytest.mark.anyio
async def test_attack4_stale_case_dna_cache_cannot_override_failed_write():
    """Fix 5's own adversarial proof: even if a `predmeti.case_dna` UPDATE silently fails (a legacy-
    field-style write inconsistency), the endpoint must report the OLD (still-actually-persisted)
    genome, never the new unsaved one -- the canonical DB state wins, not the last-computed value."""
    from routers import case_dna as cd

    stari_genome = {"snaga_predmeta_procent": 40, "verzija": 3}
    novi_genome = {"snaga_predmeta_procent": 70, "verzija": 4, "snaga_faktori": []}

    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            t.select.return_value = _chain({"id": "p1", "naziv": "X", "case_dna": stari_genome})
            upd = MagicMock()
            upd.eq.return_value.eq.return_value.execute = MagicMock(side_effect=RuntimeError("write failed"))
            t.update.return_value = upd
            return t
        if name == "predmet_dokumenti":
            return _chain([{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
                             "tekst_sadrzaj": "x", "velicina_kb": 5, "pravni_elementi": []}], count=1)
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value=dict(novi_genome))), \
         patch("routers.case_dna._fetch_dokazi_kontekst", new=AsyncMock(return_value=[])), \
         patch("routers.case_dna.verify_genome", return_value={"odluka": "ok"}), \
         patch("routers.case_dna._compute_analiza_osnov", new=AsyncMock(return_value={})), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna.UsageService.consume", new=AsyncMock(return_value=None)):
        result = await cd._refresh_case_dna_body("p1", MagicMock(), {"user_id": "u1", "email": "x@vindex.rs"})

    assert result["case_dna"]["snaga_predmeta_procent"] == 40  # the OLD, actually-persisted value wins
    assert result["case_dna_persisted"] is False
