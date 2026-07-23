# -*- coding: utf-8 -*-
"""
Tests for services/legal_reasoning_engine.py and routers/legal_reasoning.py
— Legal Reasoning Engine, Phase 0.

Pure unit tests — no live Supabase, no OpenAI/retrieval calls (both mocked).
Phase 0 binding constraints tested explicitly: no prose output, requires
Genome to exist, uses only given FACT-n/SOURCE-n ids (no invention),
weighted confidence formula matches the founder's exact weights.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

@pytest.fixture
def anyio_backend():
    return "asyncio"


PID = "pred-lre-0001"
UID = "user-lre-0001"


# ═══════════════════════════════════════════════════════════════════════════
# compute_confidence — the weighted formula (Sec 10a), founder's exact weights
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_confidence_exact_weights():
    from services.legal_reasoning_engine import compute_confidence
    result = compute_confidence(
        evidence_coverage=1.0, retrieval_agreement=1.0,
        precedent_support=1.0, model_certainty=1.0,
    )
    assert result["confidence_total"] == 1.0  # 0.35+0.30+0.20+0.15 = 1.0


def test_compute_confidence_model_certainty_capped_at_15_percent():
    """A maximally 'confident-sounding' GPT claim (model_certainty=1.0) with
    ZERO deterministic backing must not score high — this is the whole
    point of the formula (founder: 'GPT kaže 91% nema nikakvu vrednost')."""
    from services.legal_reasoning_engine import compute_confidence
    result = compute_confidence(
        evidence_coverage=0.0, retrieval_agreement=0.0,
        precedent_support=0.0, model_certainty=1.0,
    )
    assert result["confidence_total"] == 0.15


def test_compute_confidence_zero_when_all_zero():
    from services.legal_reasoning_engine import compute_confidence
    result = compute_confidence(0.0, 0.0, 0.0, 0.0)
    assert result["confidence_total"] == 0.0


def test_compute_confidence_returns_all_components_not_just_total():
    """Formula must stay auditable/re-weightable -- every component stored
    separately, not collapsed (Sec 10a)."""
    from services.legal_reasoning_engine import compute_confidence
    result = compute_confidence(0.5, 0.6, 0.7, 0.8)
    assert set(result.keys()) == {
        "evidence_coverage", "retrieval_agreement", "precedent_support",
        "model_certainty", "confidence_total",
    }


# ═══════════════════════════════════════════════════════════════════════════
# _retrieval_agreement / _precedent_support — deterministic helper checks
# ═══════════════════════════════════════════════════════════════════════════

def test_retrieval_agreement_uses_own_retrieval_score():
    """Identity-based (fixed 2026-07-23, founder review): agreement is the
    average retrieval score of the SPECIFIC citations used, not a text
    overlap guess. Every citation reaching this function is already
    guaranteed real (generate_reasoning_graph drops unknown SOURCE-n
    refs before this is called) -- this answers 'how strongly', not
    'was it retrieved'."""
    from services.legal_reasoning_engine import _retrieval_agreement
    cited = [{"zakon": "ZOO", "clan": "154", "score": 0.9}, {"zakon": "ZPP", "clan": "195", "score": 0.7}]
    assert _retrieval_agreement(cited) == 0.8


def test_retrieval_agreement_clamps_scores_to_0_1():
    from services.legal_reasoning_engine import _retrieval_agreement
    cited = [{"zakon": "X", "clan": "1", "score": 1.5}, {"zakon": "Y", "clan": "2", "score": -0.3}]
    assert _retrieval_agreement(cited) == 0.5  # clamp(1.5)=1.0, clamp(-0.3)=0.0 -> avg 0.5


def test_retrieval_agreement_empty_citations_is_zero():
    from services.legal_reasoning_engine import _retrieval_agreement
    assert _retrieval_agreement([]) == 0.0


def test_izvori_from_meta_reads_retrieve_py_structured_list():
    """retrieve.py already builds this (_build_izvori) -- LRE must reuse
    it, not reimplement retrieval verification."""
    from services.legal_reasoning_engine import _izvori_from_meta
    meta = {"izvori": [{"zakon": "ZOR", "clan": "179", "score": 0.85}]}
    assert _izvori_from_meta(meta) == [{"zakon": "ZOR", "clan": "179", "score": 0.85}]
    assert _izvori_from_meta({}) == []


def test_precedent_support_averages_praksa_scores():
    from services.legal_reasoning_engine import _precedent_support
    meta = {"praksa_matches": [{"score": 0.8}, {"score": 0.6}]}
    assert _precedent_support(meta) == 0.7


def test_precedent_support_no_matches_is_zero():
    from services.legal_reasoning_engine import _precedent_support
    assert _precedent_support({}) == 0.0
    assert _precedent_support({"praksa_matches": []}) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# _build_reasoning_prompt — no free text generation instructions leak in
# ═══════════════════════════════════════════════════════════════════════════

def test_build_reasoning_prompt_includes_facts_and_identity_based_sources():
    from services.legal_reasoning_engine import _build_reasoning_prompt
    genome = {"pravna_teorija": {"pravni_identitet": "Radni spor — otkaz bez razloga"}}
    facts = [{"tvrdnja": "Tuženi je otkazao ugovor bez upozorenja", "pravni_element": "uzročna veza"}]
    izvori = [{"zakon": "Zakon o radu", "clan": "179", "score": 0.8}]
    prompt = _build_reasoning_prompt(genome, facts, izvori, context_docs=[])
    assert "FACT-1" in prompt
    assert "Tuženi je otkazao ugovor" in prompt
    assert "SOURCE-1" in prompt
    assert "Zakon o radu" in prompt and "179" in prompt
    assert "Radni spor" in prompt


def test_build_reasoning_prompt_sources_are_identity_not_raw_text():
    """Regression guard for the exact bug the founder flagged: SOURCE-n
    must be built from structured izvori (zakon+clan), never from raw
    retrieved text chunks."""
    from services.legal_reasoning_engine import _build_reasoning_prompt
    izvori = [{"zakon": "ZOO", "clan": "154", "score": 0.9}]
    context_docs = ["Ovo je dugačak isečak teksta koji NE sme postati citatni identitet."]
    prompt = _build_reasoning_prompt({}, [], izvori, context_docs)
    assert "SOURCE-1: ZOO čl. 154" in prompt
    assert "dugačak isečak" not in prompt.split("SOURCE-1")[1].split("PRAVNI KONTEKST")[0]


def test_build_reasoning_prompt_handles_empty_facts_and_sources():
    from services.legal_reasoning_engine import _build_reasoning_prompt
    prompt = _build_reasoning_prompt({}, [], [], [])
    assert "nema cinjenica" in prompt
    assert "nema pronadjenih izvora" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# generate_reasoning_graph — orchestrator, Phase 0 binding constraints
# ═══════════════════════════════════════════════════════════════════════════

def _chain(data):
    c = MagicMock()
    for m in ['select', 'eq', 'is_', 'limit', 'order', 'execute', 'insert', 'update', 'maybe_single']:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


@pytest.mark.anyio
async def test_generate_requires_genome_to_exist():
    """Sec 1 (founder): 'Genome opisuje, LRE zaključuje' -- LRE cannot run
    without Genome facts to reason over. This is not optional."""
    from services.legal_reasoning_engine import generate_reasoning_graph
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return _chain({"id": PID, "naziv": "Test", "case_dna": None})
        return _chain([])
    supa.table.side_effect = _table
    with patch("shared.deps._get_supa", return_value=supa):
        result = await generate_reasoning_graph(PID, UID)
    assert "greska" in result
    assert "graph_id" not in result
    assert "Genome" in result["greska"]


@pytest.mark.anyio
async def test_generate_returns_no_prose_only_structured_data():
    """Founder's binding Phase 0 condition: no user-facing text. The return
    payload must contain only ids/counts/labels-as-data, never a narrative
    sentence describing the case."""
    from services.legal_reasoning_engine import generate_reasoning_graph

    genome = {
        "verzija": 1,
        "pravna_teorija": {"pravni_identitet": "Radni spor", "osnov_odgovornosti": "ZOR čl. 179"},
    }
    predmet_row = {"id": PID, "naziv": "Test predmet", "case_dna": genome}
    fact_row = {"id": "dokaz-1", "tvrdnja": "Tuženi je otkazao ugovor bez upozorenja",
                "kategorija": "cinjenica", "pravni_element": "uzročna veza", "dokument_id": "dok-1"}

    def _table(name):
        if name == "predmeti":
            return _chain(predmet_row)
        if name == "predmet_dokazi":
            return _chain([fact_row])
        if name == "reasoning_graph":
            c = _chain([])
            insert_result = MagicMock(); insert_result.data = [{"id": "graph-1"}]
            c.insert = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=insert_result)))
            c.update = MagicMock(return_value=c)
            return c
        if name == "reasoning_nodes":
            c = MagicMock()
            node_result = MagicMock(); node_result.data = [{"id": "node-1"}]
            c.insert = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=node_result)))
            return c
        if name in ("reasoning_edges", "reasoning_evidence", "reasoning_sources", "reasoning_confidence"):
            c = MagicMock()
            c.insert = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=MagicMock(data=[]))))
            return c
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    gpt_response = {"chains": [{
        "legal_element": "Uzročna veza",
        "facts": ["FACT-1"],
        "norms": ["SOURCE-1"],
        "claim": "Otkaz je nezakonit",
        "model_certainty": 0.6,
    }]}

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.legal_reasoning_engine._call_reasoning_gpt", new=AsyncMock(return_value=gpt_response)), \
         patch("services.legal_reasoning_engine._fetch_legal_sources", new=AsyncMock(return_value=(
             ["Član 179 Zakona o radu propisuje razloge za otkaz."],
             {"izvori": [{"zakon": "Zakon o radu", "clan": "179", "score": 0.8}]},
         ))):
        result = await generate_reasoning_graph(PID, UID)

    assert "greska" not in result or not result.get("greska")
    assert result["graph_id"] == "graph-1"
    assert result["verzija"] == 1
    assert result["nodes_created"]["Claim"] == 1
    assert result["nodes_created"]["Fact"] == 1
    assert result["nodes_created"]["LegalElement"] == 1
    assert result["nodes_created"]["Norm"] == 1
    # No prose: every string value in the top-level result is either an id,
    # a status word, or reused verbatim from an input label -- not a
    # GPT-authored explanatory sentence assembled by this function itself.
    assert "poruka" not in result
    assert "sazetak" not in result
    assert "objasnjenje" not in result


@pytest.mark.anyio
async def test_generate_skips_chains_missing_facts_or_norms():
    """A chain GPT returns without >=1 fact AND >=1 norm is dropped, not
    silently accepted -- enforced in code, not just by the prompt."""
    from services.legal_reasoning_engine import generate_reasoning_graph

    genome = {"verzija": 1, "pravna_teorija": {"pravni_identitet": "Test"}}
    predmet_row = {"id": PID, "naziv": "Test predmet", "case_dna": genome}

    def _table(name):
        if name == "predmeti":
            return _chain(predmet_row)
        if name == "predmet_dokazi":
            return _chain([])
        if name == "reasoning_graph":
            c = _chain([])
            insert_result = MagicMock(); insert_result.data = [{"id": "graph-1"}]
            c.insert = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=insert_result)))
            c.update = MagicMock(return_value=c)
            return c
        return MagicMock()

    supa = MagicMock()
    supa.table.side_effect = _table

    gpt_response = {"chains": [{
        "legal_element": "Nešto",
        "facts": [],  # no facts -- must be dropped
        "norms": ["SOURCE-1"],
        "claim": "Nepotvrdjen zakljucak",
        "model_certainty": 0.9,
    }]}

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("services.legal_reasoning_engine._call_reasoning_gpt", new=AsyncMock(return_value=gpt_response)), \
         patch("services.legal_reasoning_engine._fetch_legal_sources", new=AsyncMock(return_value=([], {}))):
        result = await generate_reasoning_graph(PID, UID)

    assert result["nodes_created"]["Claim"] == 0
    assert result["edges_created"] == 0


@pytest.mark.anyio
async def test_generate_predmet_not_found():
    from services.legal_reasoning_engine import generate_reasoning_graph
    supa = MagicMock()
    supa.table.return_value = _chain([])
    with patch("shared.deps._get_supa", return_value=supa):
        result = await generate_reasoning_graph("ghost-id", UID)
    assert "greska" in result


# ═══════════════════════════════════════════════════════════════════════════
# Router — 404 on missing graph, structured response shape
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_router_get_404_when_no_graph_exists():
    from fastapi import HTTPException
    from routers.legal_reasoning import reasoning_graph_get
    supa = MagicMock()
    supa.table.return_value = _chain([])
    with patch("routers.legal_reasoning._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await reasoning_graph_get(PID, {"user_id": UID})
    assert exc.value.status_code == 404


def test_reasoning_graph_generated_in_auditable_actions():
    """New audit action must actually be registered, or log_action() silently
    no-ops (shared/audit_immutable.py's own guard)."""
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "reasoning_graph_generated" in AUDITABLE_ACTIONS
