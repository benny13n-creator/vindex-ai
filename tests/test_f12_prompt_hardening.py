# -*- coding: utf-8 -*-
"""
F12 system-prompt hardening — static checks (no live API needed).

T1 — offchain_zavisnosti has embedded placeholder comment (IZMENA A)
T2 — anonimnost_ucesnika has embedded constraint comment (IZMENA B)
T3 — pravni_rizici has lock-period example comment (IZMENA C)
T4 — removed abstract blocks are gone (IZMENA D)
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


def test_t1_offchain_embedded_default():
    assert "nikad prazan niz []" in PROMPT
    assert "Nema identifikovanih eksplicitnih off-chain zavisnosti u dostavljenom kodu" in PROMPT
    assert "frontend, deployment proces" in PROMPT


def test_t2_anonymity_embedded_constraint():
    assert "obrazlozenje MORA završiti rečenicom" in PROMPT
    assert "strukturna karakteristika blockchain tehnologije" in PROMPT
    assert "AML/KYC analizu na nivou platforme/posrednika" in PROMPT


def test_t3_lock_period_risk_example():
    assert "Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim okolnostima." in PROMPT
    assert "lock period" in PROMPT
    assert "kompromitacije ključa" in PROMPT


def test_t4_removed_abstract_blocks():
    assert "OBAVEZNA PROVERA RIZIKA" not in PROMPT
    assert "INSTRUKCIJE ZA SPECIFIČNA POLJA" not in PROMPT
    assert "Jednostrana izmena parametara" not in PROMPT
