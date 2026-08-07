# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 010 -- Drafting RAG Grounding (CRITICAL).
Closes LIVINGSYS-DEBT-013: /api/nacrt's quick-draft path asked GPT to invent a
specific ZOO/ZR statute article number with zero RAG retrieval and zero
critique pass, embedded directly into real legal document text. Ports the
same RAG retrieval + critique-pass infrastructure the sibling /api/podnesak
path already had (routers/drafting.py::_izvori_kontekst /
_critique_and_refine_draft) into drafting/router.py::generate_draft.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json

import pytest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")


_FAKE_FIELDS_STETA = json.dumps({
    "tuzilac_ime": "Petar Petrović",
    "tuzeni_ime": "Marko Marković",
    "sud_naziv": "Osnovni sud u Beogradu",
    "opis_stete": "Saobraćajna nezgoda 01.03.2026.",
    "iznos_stete": "500000",
    "pravni_osnov_clan": "999",  # a plausible-looking but unconfirmed article number
    "dokazi": "Zapisnik policije, medicinska dokumentacija",
    "datum": "11.05.2026.",
    "mesto": "Beograd",
})


# ═══════════════════════════════════════════════════════════════════════════
# RAG retrieval now feeds the extraction step
# ═══════════════════════════════════════════════════════════════════════════

def test_generate_draft_calls_retrieve_documents_when_available():
    from drafting.router import generate_draft

    with patch("drafting.router._RAG_AVAILABLE", True), \
         patch("drafting.router.retrieve_documents", return_value=(["ZOO čl. 200: naknada nematerijalne štete."], {})) as mock_retrieve, \
         patch("drafting.router._call_openai", return_value=_FAKE_FIELDS_STETA):
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    mock_retrieve.assert_called_once()
    query_arg = mock_retrieve.call_args[0][0]
    assert "tuzba_naknada_stete" not in query_arg  # uses the human label, not the raw key
    assert "Petar tuži Marka" in query_arg


def test_generate_draft_survives_rag_retrieval_failure():
    """Fail-open: a RAG/network exception must not block draft generation, matching
    /api/podnesak's own established resilience pattern."""
    from drafting.router import generate_draft

    with patch("drafting.router._RAG_AVAILABLE", True), \
         patch("drafting.router.retrieve_documents", side_effect=Exception("pinecone down")), \
         patch("drafting.router._call_openai", return_value=_FAKE_FIELDS_STETA):
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    assert "Petar Petrović" in result["data"]


def test_generate_draft_skips_retrieval_when_rag_unavailable():
    from drafting.router import generate_draft

    with patch("drafting.router._RAG_AVAILABLE", False), \
         patch("drafting.router._call_openai", return_value=_FAKE_FIELDS_STETA) as mock_call:
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    # Extraction call's user prompt must not claim to carry RAG context when none was fetched.
    extraction_user_prompt = mock_call.call_args_list[0][0][1]
    assert "ZAKONSKI KONTEKST" not in extraction_user_prompt


# ═══════════════════════════════════════════════════════════════════════════
# Critique pass -- the actual anti-hallucination backstop. This is the
# original-scenario reproduction: an unconfirmed, specific statute article
# number reaching the final document text must be caught and neutralized.
# ═══════════════════════════════════════════════════════════════════════════

def test_generate_draft_critique_neutralizes_hallucinated_article_number():
    from drafting.router import generate_draft

    critique_response = json.dumps({
        "ima_izmisljenih_navoda": True,
        "izmisljeni_navodi": ["čl. 999 ZOO ne postoji -- izmišljen broj člana"],
        "nedostaju_elementi": [],
        "ispravljen_tekst": "ISPRAVLJEN NACRT -- pravni osnov naveden u skladu sa važećim propisima.",
    })

    with patch("drafting.router._RAG_AVAILABLE", False), \
         patch("drafting.router._call_openai", side_effect=[_FAKE_FIELDS_STETA, critique_response]):
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    assert "999" not in result["data"]
    assert "ISPRAVLJEN NACRT" in result["data"]
    assert result["critique_applied"] is True
    # tuzba_naknada_stete has compliance_tip=None -- no VINDEX COMPLIANCE block should
    # be appended, confirming the critique pass didn't disturb the (skipped) step 7.
    assert "VINDEX COMPLIANCE" not in result["data"]


def test_generate_draft_critique_leaves_clean_draft_unchanged():
    from drafting.router import generate_draft

    clean_critique = json.dumps({
        "ima_izmisljenih_navoda": False, "izmisljeni_navodi": [], "nedostaju_elementi": [],
        "ispravljen_tekst": "",
    })

    with patch("drafting.router._RAG_AVAILABLE", False), \
         patch("drafting.router._call_openai", side_effect=[_FAKE_FIELDS_STETA, clean_critique]):
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    assert "Petar Petrović" in result["data"]
    assert result["critique_applied"] is True


def test_generate_draft_critique_failure_still_returns_draft_with_applied_false():
    from drafting.router import generate_draft

    with patch("drafting.router._RAG_AVAILABLE", False), \
         patch("drafting.router._call_openai", side_effect=[_FAKE_FIELDS_STETA, Exception("critique llm down")]):
        result = generate_draft("tuzba_naknada_stete", "Petar tuži Marka za štetu")

    assert result["status"] == "success"
    assert "Petar Petrović" in result["data"]
    assert result["critique_applied"] is False


# ═══════════════════════════════════════════════════════════════════════════
# /api/nacrt response surfaces critique_applied (mirrors Mission 009's
# /api/podnesak disclosure, same field name)
# ═══════════════════════════════════════════════════════════════════════════

def test_normalizuj_rezultat_forwards_critique_applied():
    from routers.drafting import _normalizuj_rezultat

    resp = _normalizuj_rezultat({"status": "success", "data": "tekst", "critique_applied": False}, credits_remaining=5)
    assert resp["critique_applied"] is False
    assert resp["odgovor"] == "tekst"
    assert resp["credits_remaining"] == 5


def test_normalizuj_rezultat_omits_critique_applied_when_absent():
    """Regression: callers that don't set critique_applied (none currently do besides
    generate_draft) must not get a spurious key."""
    from routers.drafting import _normalizuj_rezultat

    resp = _normalizuj_rezultat({"status": "success", "data": "tekst"}, credits_remaining=5)
    assert "critique_applied" not in resp


# ═══════════════════════════════════════════════════════════════════════════
# Shared canonical grounding module -- both drafting surfaces use it
# ═══════════════════════════════════════════════════════════════════════════

def test_both_drafting_surfaces_import_the_same_critique_prompt():
    import routers.drafting as rd
    import drafting.router as dr
    from shared.drafting_grounding import CRITIQUE_SYSTEM

    assert rd._CRITIQUE_SYSTEM is CRITIQUE_SYSTEM
    assert dr.CRITIQUE_SYSTEM is CRITIQUE_SYSTEM


def test_both_drafting_surfaces_import_the_same_izvori_kontekst():
    import routers.drafting as rd
    import drafting.router as dr
    from shared.drafting_grounding import izvori_kontekst

    assert rd._izvori_kontekst is izvori_kontekst
    assert dr.izvori_kontekst is izvori_kontekst
