# -*- coding: utf-8 -*-
"""
F12 system-prompt hardening — static checks (no live API needed).

T1 — OBAVEZNA PROVERA RIZIKA block present (categories a-e + minimum rule)
T2 — offchain_zavisnosti placeholder instruction present
T3 — anonimnost_ucesnika structural-characteristic note present
"""

import sys, os

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_stashed = sys.modules.pop("api", None)
import api as _api
del sys.modules["api"]
if _stashed is not None:
    sys.modules["api"] = _stashed

PROMPT = _api._SC_SYSTEM_PROMPT


def test_t1_mandatory_risk_categories():
    assert "OBAVEZNA PROVERA RIZIKA" in PROMPT
    assert "Jednostrana izmena parametara" in PROMPT
    assert "Odsustvo emergency/pause mehanizma" in PROMPT
    assert "Odsustvo procedure za povra" in PROMPT
    assert "Centralizovana kontrola nad sredstvima" in PROMPT
    assert "Nejasno definisana odgovornost" in PROMPT
    assert "najmanje 2-3 stavke u pravni_rizici" in PROMPT


def test_t2_offchain_placeholder():
    assert "NIKADA ne sme biti prazan niz []" in PROMPT
    assert "Nema identifikovanih eksplicitnih off-chain zavisnosti" in PROMPT
    assert "frontend, deployment proces" in PROMPT


def test_t3_anonymity_structural_note():
    assert "STRUKTURNA KARAKTERISTIKA SVIH blockchain ugovora" in PROMPT
    assert "AML/KYC analizu na nivou platforme/posrednika" in PROMPT
