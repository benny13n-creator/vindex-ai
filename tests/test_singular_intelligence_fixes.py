# -*- coding: utf-8 -*-
"""
Operation Singular Intelligence, Mission 001 -- regression coverage for the 6-team forensic pass
(docs/singular/). Each test proves a specific semantic-fragmentation defect this mission found is
closed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
VINDEX_JS = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# Fix 1 (Red Team Attack 1, reproduced): routers/zadaci.py::ai_analiziraj_predmet's
# predmet_dokazi query was the only calculate_procesni_rizik caller missing the
# deleted_at soft-delete filter every sibling caller has -- proven divergence:
# identical case data gave "Visok"/health=20 on Matter Intel/CCC vs "Srednji"/
# health=55 here, from a soft-deleted evidence row still being counted.
# ═══════════════════════════════════════════════════════════════════════════

def test_zadaci_dokazi_query_excludes_soft_deleted():
    src = open(os.path.join(REPO_ROOT, "routers", "zadaci.py"), encoding="utf-8").read()
    block = src.split('supa.table("predmet_dokazi")', 1)[1][:250]
    assert 'is_("deleted_at", "null")' in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 2 (Red Team Attack 3, reproduced): the firm-wide Health Index widget cached
# its full verdict for 1h with no staleness disclosure to the frontend -- a stale
# "everything's fine" could win over a live "urgent" recomputation silently.
# Now threads iz_kesa/generated_at, matching cio.py's own established pattern.
# ═══════════════════════════════════════════════════════════════════════════

def _hi_chain(data):
    c = MagicMock()
    for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
              'insert', 'update', 'delete', 'is_', 'in_', 'desc'):
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


@pytest.mark.anyio
async def test_health_index_fresh_response_marked_not_cached():
    from routers import health_index as hi
    hi._CACHE.clear()

    def _table(name):
        return _hi_chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.health_index._get_supa", return_value=supa), \
         patch("routers.health_index.UsageService.consume", new=AsyncMock()):
        result = await hi.get_health_index(force=False, user={"user_id": "u-hi-1", "email": "x@vindex.rs"})

    assert result["iz_kesa"] is False
    assert "generated_at" in result


@pytest.mark.anyio
async def test_health_index_cache_hit_discloses_staleness():
    from routers import health_index as hi
    hi._CACHE.clear()

    def _table(name):
        return _hi_chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.health_index._get_supa", return_value=supa), \
         patch("routers.health_index.UsageService.consume", new=AsyncMock()):
        first = await hi.get_health_index(force=False, user={"user_id": "u-hi-2", "email": "x@vindex.rs"})
        assert first["iz_kesa"] is False
        second = await hi.get_health_index(force=False, user={"user_id": "u-hi-2", "email": "x@vindex.rs"})

    # Second call within the TTL must be explicitly disclosed as cached, not silently
    # served as if freshly computed.
    assert second["iz_kesa"] is True
    assert second["generated_at"] == first["generated_at"]


def test_health_index_frontend_renders_cached_indicator():
    marker = "Zdravlje kancelarije danas"
    block = VINDEX_JS.split(marker, 1)[1][:200]
    assert "d.iz_kesa" in block
    assert "keširano" in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 3 (AI Boundary Team B, new flagship finding): web3_compliance.py's 4 PRO
# client-facing due-diligence scores had zero server-side clamp/enum guard, and
# the frontend silently renders any unrecognized level string as the LOWEST-risk
# bucket -- a compliance feature that could invert its own risk signal.
# ═══════════════════════════════════════════════════════════════════════════

def _web3_resp(content: str):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


def test_mica_readiness_score_clamps_poisoned_response():
    import json as _json
    import web3_compliance as w3

    poisoned = _json.dumps({"ukupni_skor": 9999, "skor_nivo": "APSOLUTNO SPREMNO!!!", "kategorije": {}})
    with patch("web3_compliance._pozovi_web3_api", return_value=_web3_resp(poisoned)):
        result = w3.mica_readiness_score_sync("neki projekat", "sk-test")

    assert result["score_data"]["ukupni_skor"] == 100
    assert result["score_data"]["skor_nivo"] == "NIZAK"  # goodness scale: unrecognized fails safe LOW, never "spremno"


def test_zdi_license_checker_fails_safe_to_visok_risk_on_poisoned_response():
    import json as _json
    import web3_compliance as w3

    poisoned = _json.dumps({"rizik_nivo": "NEMA RIZIKA UOPSTE", "dozvola_potrebna": False,
                             "nadlezni_organ": "NBS", "klasifikacija_imovine": "virtualna_valuta"})
    with patch("web3_compliance._pozovi_web3_api", return_value=_web3_resp(poisoned)):
        result = w3.zdi_license_checker_sync("neka aktivnost", "sk-test")

    # risk scale: unrecognized must fail safe to VISOK, never silently downgrade to low/no risk
    assert result["license_data"]["rizik_nivo"] == "VISOK"


def test_aml_kyc_auditor_clamps_poisoned_response():
    import json as _json
    import web3_compliance as w3

    poisoned = _json.dumps({"ukupna_uskladenost": -500, "uskladenost_nivo": "POTPUNO USKLADJENO", "kategorije": {}})
    with patch("web3_compliance._pozovi_web3_api", return_value=_web3_resp(poisoned)):
        result = w3.aml_kyc_auditor_sync("neka politika", "sk-test")

    assert result["audit_data"]["ukupna_uskladenost"] == 0
    assert result["audit_data"]["uskladenost_nivo"] == "NIZAK"


def test_documentation_health_score_clamps_poisoned_response():
    import json as _json
    import web3_compliance as w3

    poisoned = _json.dumps({"ukupni_skor": 500, "skor_nivo": "SAVRSENO", "kategorije": {}})
    with patch("web3_compliance._pozovi_web3_api", return_value=_web3_resp(poisoned)):
        result = w3.documentation_health_score_sync("neki opis", "sk-test")

    assert result["health_data"]["ukupni_skor"] == 100
    assert result["health_data"]["skor_nivo"] == "NIZAK"


# ═══════════════════════════════════════════════════════════════════════════
# Fix 4 (Frontend Truth Team, sharpened DEBT-002): the Genome hero panel and
# Copilot's "Verovatnoća uspeha" render the SAME snaga_predmeta_procent field
# (aliased since Program Tau Sprint 003) but disagreed on threshold (65 vs 60)
# AND used opposite framing (risk vs success) for the identical number -- a
# 62% case showed green "success" in Copilot and orange "risk" one click away.
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_hero_panel_no_longer_uses_risk_vocabulary_for_strength_score():
    marker = "var _sumProcent = dna.snaga_predmeta_procent;"
    block = VINDEX_JS.split(marker, 1)[1][:500]
    assert "Visok rizik" not in block
    assert "Srednji rizik" not in block
    assert "'Slaba pozicija'" in block
    assert "'Srednja pozicija'" in block


def test_genome_hero_panel_threshold_matches_copilot():
    marker = "var _sumProcent = dna.snaga_predmeta_procent;"
    block = VINDEX_JS.split(marker, 1)[1][:500]
    assert "_sumProcent >= 60" in block   # was 65, now matches Copilot's vc>=60 boundary
    assert "_sumProcent >= 65" not in block


def test_genome_detail_bar_threshold_matches_copilot():
    marker = "// ── Snaga predmeta — progress bar sa historijom"
    block = VINDEX_JS.split(marker, 1)[1][:400]
    assert "procent >= 60" in block
    assert "procent >= 65" not in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 5 (Database Reality Team, real live bug): the manual Genome-refresh
# endpoint's response was built from the NEW genome dict + a "regenerisan"
# success message UNCONDITIONALLY, even when the predmeti.case_dna UPDATE
# itself failed -- a lawyer would see new data and a success toast, then
# reload to find the old genome with no error ever surfaced.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_refresh_case_dna_body_honestly_reports_failed_save():
    from routers import case_dna as cd

    stari_genome = {"snaga_predmeta_procent": 40, "verzija": 3}
    novi_genome = {"snaga_predmeta_procent": 70, "verzija": 4, "snaga_faktori": []}

    def _chain_select(data):
        c = MagicMock()
        for m in ("select", "eq", "order", "limit", "maybe_single"):
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data; r.count = len(data) if isinstance(data, list) else None
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            sel = _chain_select({"id": "p1", "naziv": "X", "case_dna": stari_genome})
            t.select.return_value = sel
            upd = MagicMock()
            upd.eq.return_value.eq.return_value.execute = MagicMock(side_effect=RuntimeError("DB write failed"))
            t.update.return_value = upd
            return t
        if name == "predmet_dokumenti":
            return _chain_select([{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
                                    "tekst_sadrzaj": "sadrzaj", "velicina_kb": 5, "pravni_elementi": []}])
        return _chain_select([])

    supa = MagicMock()
    supa.table.side_effect = _table

    req = MagicMock()

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value=dict(novi_genome))), \
         patch("routers.case_dna.upisi_v2_opazanje", new=AsyncMock(return_value={
             "kandidata": 0, "odbijeno": 0, "kompletno": True,
             "observation_version": 1, "ishodi": [], "odbijeni": []})), \
         patch("routers.case_dna._fetch_dokazi_kontekst", new=AsyncMock(return_value=[])), \
         patch("routers.case_dna.verify_genome", return_value={"odluka": "ok"}), \
         patch("routers.case_dna._compute_analiza_osnov", new=AsyncMock(return_value={})), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna.UsageService.consume", new=AsyncMock(return_value=None)):
        result = await cd._refresh_case_dna_body("p1", req, {"user_id": "u1", "email": "x@vindex.rs"})

    # Must NOT claim the new genome was saved -- must reflect what's actually still in the DB.
    assert result["case_dna_persisted"] is False
    assert result["case_dna"] == stari_genome
    assert result["verzija"] == 3
    assert "NIJE sačuvan" in result["poruka"]


@pytest.mark.anyio
async def test_refresh_case_dna_body_reports_success_when_save_succeeds():
    from routers import case_dna as cd

    stari_genome = {"snaga_predmeta_procent": 40, "verzija": 3}
    novi_genome = {"snaga_predmeta_procent": 70, "verzija": 4, "snaga_faktori": []}

    def _chain_select(data):
        c = MagicMock()
        for m in ("select", "eq", "order", "limit", "maybe_single"):
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data; r.count = len(data) if isinstance(data, list) else None
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            sel = _chain_select({"id": "p1", "naziv": "X", "case_dna": stari_genome})
            t.select.return_value = sel
            upd = MagicMock()
            upd.eq.return_value.eq.return_value.execute = MagicMock(return_value=MagicMock(data=[{"id": "p1"}]))
            t.update.return_value = upd
            return t
        if name == "predmet_dokumenti":
            return _chain_select([{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
                                    "tekst_sadrzaj": "sadrzaj", "velicina_kb": 5, "pravni_elementi": []}])
        return _chain_select([])

    supa = MagicMock()
    supa.table.side_effect = _table

    req = MagicMock()

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value=dict(novi_genome))), \
         patch("routers.case_dna.upisi_v2_opazanje", new=AsyncMock(return_value={
             "kandidata": 0, "odbijeno": 0, "kompletno": True,
             "observation_version": 1, "ishodi": [], "odbijeni": []})), \
         patch("routers.case_dna._fetch_dokazi_kontekst", new=AsyncMock(return_value=[])), \
         patch("routers.case_dna.verify_genome", return_value={"odluka": "ok"}), \
         patch("routers.case_dna._compute_analiza_osnov", new=AsyncMock(return_value={})), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna.UsageService.consume", new=AsyncMock(return_value=None)):
        result = await cd._refresh_case_dna_body("p1", req, {"user_id": "u1", "email": "x@vindex.rs"})

    assert result["case_dna_persisted"] is True
    assert result["verzija"] == 4
    assert "regenerisan" in result["poruka"]


# ═══════════════════════════════════════════════════════════════════════════
# Final Beta Gate F2 (HIGH): the manual refresh endpoint used to lack the
# same "greska in genome -> don't touch the live column" guard the
# background path already has -- a GPT extraction failure would still get
# written over the good, existing Genome (full-column REPLACE), while still
# claiming case_dna_persisted: true with a success message.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_refresh_case_dna_body_does_not_overwrite_good_genome_on_extraction_failure():
    from routers import case_dna as cd

    stari_genome = {"snaga_predmeta_procent": 40, "verzija": 3, "kljucne_cinjenice": ["real fact"]}
    failed_genome = {"greska": "OpenAI timeout"}

    def _chain_select(data):
        c = MagicMock()
        for m in ("select", "eq", "order", "limit", "maybe_single"):
            setattr(c, m, MagicMock(return_value=c))
        r = MagicMock(); r.data = data; r.count = len(data) if isinstance(data, list) else None
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            sel = _chain_select({"id": "p1", "naziv": "X", "case_dna": stari_genome})
            t.select.return_value = sel
            upd = MagicMock()
            # If the fix regresses and the endpoint tries to write anyway,
            # this raises so the test fails loudly instead of silently
            # accepting a destructive write.
            upd.eq.return_value.eq.return_value.execute = MagicMock(
                side_effect=AssertionError("must not write over case_dna on extraction failure")
            )
            t.update.return_value = upd
            return t
        if name == "predmet_dokumenti":
            return _chain_select([{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
                                    "tekst_sadrzaj": "sadrzaj", "velicina_kb": 5, "pravni_elementi": []}])
        return _chain_select([])

    supa = MagicMock()
    supa.table.side_effect = _table

    req = MagicMock()

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value=dict(failed_genome))), \
         patch("routers.case_dna._fetch_dokazi_kontekst", new=AsyncMock(return_value=[])), \
         patch("routers.case_dna.verify_genome", return_value={"odluka": "ok"}), \
         patch("routers.case_dna._compute_analiza_osnov", new=AsyncMock(return_value={})), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock(return_value=None)), \
         patch("routers.case_dna.UsageService.consume", new=AsyncMock(return_value=None)) as mock_consume:
        result = await cd._refresh_case_dna_body("p1", req, {"user_id": "u1", "email": "x@vindex.rs"})

    assert result["case_dna_persisted"] is False
    assert result["case_dna"] == stari_genome
    assert result["verzija"] == 3
    assert "AI ekstrakciji" in result["poruka"]
    mock_consume.assert_not_called(), "must not charge a credit for a failed extraction"


# ═══════════════════════════════════════════════════════════════════════════
# Fix 6 (Red Team Attack 4, reproduced): dna.tip_spora has never existed in the
# Genome schema -- the real field is pravna_teorija.pravni_identitet. Confirmed
# via git history to have been wrong since the first Case Genome commit.
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_refresh_toast_no_longer_reads_ghost_field():
    marker = "if (dna.greska) {"
    block = VINDEX_JS.split(marker, 1)[1][:1500]
    assert "var tip = dna.tip_spora" not in block
    assert "var tip = (dna.pravna_teorija && dna.pravna_teorija.pravni_identitet) || '';" in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 7 (Semantic Mapping Team finding): Court Predictor's stats panel
# unconditionally showed "Preporuke prihvaćeno: 0 · Odbijeno: 0" forever, for
# every user -- recommendation_log has a confirmed dead insert path, so these
# numbers can never currently be real. Now hidden until real data could exist,
# matching the sibling Confidence Audit panel's own "no data yet" discipline.
# ═══════════════════════════════════════════════════════════════════════════

def test_learning_stats_hides_recommendation_outcome_line_when_always_zero():
    marker = "async function learningStatsLoad() {"
    block = VINDEX_JS.split(marker, 1)[1][:2500]
    assert "_prihOdb > 0" in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 8 (Semantic Mapping Team, mission headline finding): Command Center
# stacks 3 independently-computed "what should I do today" answers on one
# screen -- Workspace (canonical), Chief Partner Directive (GPT, never reads
# case_actions), CIO's Preporuka za danas (GPT, never reads case_actions,
# cio.py's own code comment admits this was a deliberate, disclosed scope
# decision). Full consolidation deferred (SINGULAR-DEBT-001) -- this mission
# adds the disclosure mitigation so a lawyer can at least see these are
# independent AI suggestions, not the platform's single canonical answer.
# ═══════════════════════════════════════════════════════════════════════════

def test_chief_partner_directive_discloses_independence_from_workspace():
    marker = "Chief Partner — Direktiva za danas</div>';"
    block = VINDEX_JS.split(marker, 1)[1][:800]
    assert "nezavisan od Workspace" in block


def test_cio_preporuka_discloses_independence_from_workspace():
    marker = "PREPORUKA ZA DANAS</div>';"
    block = VINDEX_JS.split(marker, 1)[1][:400]
    assert "nezavisan od Workspace" in block


# ═══════════════════════════════════════════════════════════════════════════
# shared/semantic_registry.py — the Phase 3 canonical registry deliverable.
# Pure lookups only, per this mission's own Core Rule 1/2 (no new intelligence,
# no new scoring engine) -- these tests prove it stays that way.
# ═══════════════════════════════════════════════════════════════════════════

def test_semantic_registry_is_pure_lookups_no_computation():
    import inspect
    import shared.semantic_registry as sr
    # every public function must be a simple lookup -- no arithmetic, no GPT calls, no DB I/O
    src = inspect.getsource(sr)
    assert "openai" not in src.lower()
    assert "supabase" not in src.lower()
    assert ".table(" not in src


def test_semantic_registry_get_owner_matches_truth_contract():
    from shared.semantic_registry import get_owner
    risk = get_owner("risk")
    assert risk.owner == "services/risk_engine.py::calculate_procesni_rizik"
    assert risk.allowed_values == ("Nizak", "Srednji", "Visok")

    readiness = get_owner("readiness")
    assert readiness.owner == "shared/case_readiness.py::compute_case_readiness"
    assert "CRITICAL_GAP" in readiness.allowed_values

    assert get_owner("nonexistent_concept") is None


def test_semantic_registry_is_valid_value():
    from shared.semantic_registry import is_valid_value
    assert is_valid_value("risk", "Visok") is True
    assert is_valid_value("risk", "EXTREMAN") is False
    assert is_valid_value("readiness", "CRITICAL_GAP") is True
    # a concept with no fixed enum (allowed_values=None) accepts anything
    assert is_valid_value("recommendation", "bilo šta") is True


def test_web3_well_formed_responses_pass_through_unchanged():
    import json as _json
    import web3_compliance as w3

    well_formed = _json.dumps({"ukupni_skor": 62, "skor_nivo": "SREDNJI", "kategorije": {}})
    with patch("web3_compliance._pozovi_web3_api", return_value=_web3_resp(well_formed)):
        result = w3.mica_readiness_score_sync("x", "sk-test")
    assert result["score_data"]["ukupni_skor"] == 62
    assert result["score_data"]["skor_nivo"] == "SREDNJI"
