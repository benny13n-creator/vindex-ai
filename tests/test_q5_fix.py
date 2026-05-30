# -*- coding: utf-8 -*-
"""
Commit 5/N: Q5/Q4 JSON parse stability — 6 regression tests.

T1 — _PARNICA_TRIGGERS contains 8 new terms
T2 — klasifikuj_pitanje("Šta se dešava sa zalogom u slučaju stečaja dužnika?") → PARNICA
T3 — klasifikuj_pitanje("Razlika između jemstva i bankarske garancije po ZOO") → PARNICA
T4 — klasifikuj_pitanje("Kako funkcioniše hipoteka kod prinudne naplate") → PARNICA
T5 — _JSON_SCHEMA_DEFINICIJA string fields contain FLAT STRING description
T6 — DEFINICIJA max_tokens == 2500
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


# ─── T1: _PARNICA_TRIGGERS contains all 8 new terms ──────────────────────────

_EXPECTED_NEW_TERMS = [
    "zalog",
    "zaloga",
    "stečaj",
    "stecaj",
    "hipoteka",
    "jemstv",       # root form — matches jemstvo, jemstva, etc.
    "garancij",     # root form — matches garancija, garancije, etc.
    "bankars",      # root form — matches bankarska, bankarske, etc.
]


def test_t1_parnica_triggers_new_terms():
    """All 8 new terms must be present in _PARNICA_TRIGGERS."""
    missing = [t for t in _EXPECTED_NEW_TERMS if t not in _m._PARNICA_TRIGGERS]
    assert not missing, f"T1 FAIL: missing from _PARNICA_TRIGGERS: {missing}"


# ─── T2: Q5 query → PARNICA ───────────────────────────────────────────────────

def test_t2_q5_query_is_parnica():
    """Q5 'zalog + stečaj' query must classify as PARNICA (not DEFINICIJA)."""
    tip = _m.klasifikuj_pitanje("Šta se dešava sa zalogom u slučaju stečaja dužnika?")
    assert tip == "PARNICA", \
        f"T2 FAIL: expected PARNICA, got {tip!r} for Q5 query"


# ─── T3: Q4 query → PARNICA ───────────────────────────────────────────────────

def test_t3_q4_query_is_parnica():
    """Q4 'jemstvo + bankarska garancija' query must classify as PARNICA."""
    tip = _m.klasifikuj_pitanje("Razlika između jemstva i bankarske garancije po ZOO")
    assert tip == "PARNICA", \
        f"T3 FAIL: expected PARNICA, got {tip!r} for Q4 query"


# ─── T4: hipoteka query → PARNICA ─────────────────────────────────────────────

def test_t4_hipoteka_query_is_parnica():
    """'hipoteka + prinudna naplata' query must classify as PARNICA."""
    tip = _m.klasifikuj_pitanje("Kako funkcioniše hipoteka kod prinudne naplate")
    assert tip == "PARNICA", \
        f"T4 FAIL: expected PARNICA, got {tip!r} for hipoteka query"


# ─── T5: _JSON_SCHEMA_DEFINICIJA string fields have FLAT STRING description ───

_FIELDS_REQUIRING_FLAT_STRING = [
    "hijerarhija_izvora",
    "pravni_zakljucak",
    "pravna_definicija",
    "citat_zakona",
    "pravni_osnov",
    "prakticni_primer",
]


def test_t5_schema_flat_string_descriptions():
    """6 string fields in _JSON_SCHEMA_DEFINICIJA must have 'FLAT STRING' in description."""
    props = (
        _m._JSON_SCHEMA_DEFINICIJA
        ["json_schema"]["schema"]["properties"]
    )
    missing = []
    for field in _FIELDS_REQUIRING_FLAT_STRING:
        desc = props.get(field, {}).get("description", "")
        if "FLAT STRING" not in desc:
            missing.append(field)
    assert not missing, \
        f"T5 FAIL: missing FLAT STRING description in: {missing}"


# ─── T6: DEFINICIJA max_tokens == 2500 ────────────────────────────────────────

def test_t6_definicija_max_tokens():
    """_prompt_map DEFINICIJA entry must use max_tokens=2500."""
    # We need to reach the _prompt_map inside ask_agent — it's a local dict.
    # Read it from source instead.
    src_path = os.path.join(os.path.dirname(__file__), "..", "main.py")
    src = open(src_path, encoding="utf-8").read()

    # Find the _prompt_map DEFINICIJA tuple (not _JSON_SCHEMA_MAP which has same key)
    # Pattern: "DEFINICIJA": (SYSTEM_PROMPT_DEFINICIJA, ...
    idx = src.find('"DEFINICIJA": (SYSTEM_PROMPT_DEFINICIJA')
    assert idx != -1, "T6: DEFINICIJA prompt_map entry not found in main.py"

    snippet = src[idx: idx + 120]
    assert "2500" in snippet, \
        f"T6 FAIL: DEFINICIJA max_tokens is not 2500. snippet: {snippet}"
