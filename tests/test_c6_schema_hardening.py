# -*- coding: utf-8 -*-
"""
Commit 6/N: PARNICA/COMPLIANCE/PORESKI schema hardening — 5 regression tests.

T1 — _JSON_SCHEMA_PARNICA pravni_osnov description contains "KRATKA REFERENCA"
T2 — _JSON_SCHEMA_PARNICA all string fields (except status fields) have FLAT STRING marker
T3 — _JSON_SCHEMA_COMPLIANCE pravni_osnov description has length guidance
T4 — _JSON_SCHEMA_PORESKI pravni_osnov description has length guidance
T5 — SYSTEM_PROMPT_PARNICA contains pravni_osnov reference rule block
"""

import sys
import os
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_stashed_main = sys.modules.pop("main", None)
import main as _m
del sys.modules["main"]
if _stashed_main is not None:
    sys.modules["main"] = _stashed_main


# ─── T1: PARNICA pravni_osnov has KRATKA REFERENCA ───────────────────────────

def test_t1_parnica_pravni_osnov_kratka_referenca():
    """pravni_osnov in PARNICA schema must have 'KRATKA REFERENCA' in description."""
    props = _m._JSON_SCHEMA_PARNICA["json_schema"]["schema"]["properties"]
    desc = props.get("pravni_osnov", {}).get("description", "")
    assert "KRATKA REFERENCA" in desc, \
        f"T1 FAIL: pravni_osnov missing 'KRATKA REFERENCA'. Got: {desc!r}"


# ─── T2: PARNICA all substantive string fields have FLAT STRING ──────────────

_PARNICA_FLAT_STRING_FIELDS = [
    "hijerarhija_izvora",
    "pravni_zakljucak",
    "analiza_stete",
    "citat_zakona",
    "pravni_osnov",
    "rizici_i_izuzeci",
    "kada_ne_vazi",
    "procesni_koraci",
    "kljucno_pitanje",
    "potrebne_informacije",
    "izvor",
]


def test_t2_parnica_string_fields_flat_string():
    """All substantive string fields in PARNICA schema must have 'FLAT STRING' in description."""
    props = _m._JSON_SCHEMA_PARNICA["json_schema"]["schema"]["properties"]
    missing = []
    for field in _PARNICA_FLAT_STRING_FIELDS:
        desc = props.get(field, {}).get("description", "")
        if "FLAT STRING" not in desc and "KRATKA REFERENCA" not in desc:
            missing.append(field)
    assert not missing, \
        f"T2 FAIL: missing FLAT STRING / KRATKA REFERENCA description: {missing}"


# ─── T3: COMPLIANCE pravni_osnov has length guidance ─────────────────────────

def test_t3_compliance_pravni_osnov_guidance():
    """pravni_osnov in COMPLIANCE schema must have length/format guidance."""
    props = _m._JSON_SCHEMA_COMPLIANCE["json_schema"]["schema"]["properties"]
    desc = props.get("pravni_osnov", {}).get("description", "")
    assert "KRATKA REFERENCA" in desc or "200" in desc, \
        f"T3 FAIL: COMPLIANCE pravni_osnov missing length guidance. Got: {desc!r}"


# ─── T4: PORESKI pravni_osnov has length guidance ────────────────────────────

def test_t4_poreski_pravni_osnov_guidance():
    """pravni_osnov in PORESKI schema must have length/format guidance."""
    props = _m._JSON_SCHEMA_PORESKI["json_schema"]["schema"]["properties"]
    desc = props.get("pravni_osnov", {}).get("description", "")
    assert "KRATKA REFERENCA" in desc or "200" in desc, \
        f"T4 FAIL: PORESKI pravni_osnov missing length guidance. Got: {desc!r}"


# ─── T5: SYSTEM_PROMPT_PARNICA contains pravni_osnov rule block ───────────────

def test_t5_parnica_prompt_reference_rule():
    """SYSTEM_PROMPT_PARNICA must contain the pravni_osnov reference rule block."""
    prompt = _m.SYSTEM_PROMPT_PARNICA
    assert "PRAVILO O REFERENCAMA" in prompt, \
        "T5 FAIL: SYSTEM_PROMPT_PARNICA missing '🔒 PRAVILO O REFERENCAMA' block"
    assert "dugačku listu Sl. glasnik" in prompt or "dugačke liste amandman" in prompt, \
        "T5 FAIL: SYSTEM_PROMPT_PARNICA missing Sl. glasnik list prohibition"
