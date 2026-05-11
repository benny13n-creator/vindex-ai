# -*- coding: utf-8 -*-
"""Unit tests for detect_doc_type (Phase 2.5 Patch 1).

Uses importlib.util to load main.py directly from disk, bypassing sys.modules
entirely — avoids conflicts with other test files that mock sys.modules["main"].
"""

import sys
import os
import importlib.util
import pathlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

# Load main.py under a private name to avoid sys.modules["main"] conflicts
_main_path = pathlib.Path(__file__).parent.parent.parent / "main.py"
_spec = importlib.util.spec_from_file_location("_main_p25_test", _main_path)
_main_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

detect_doc_type = _main_mod.detect_doc_type
DOC_TYPE_CONSTRAINTS = _main_mod.DOC_TYPE_CONSTRAINTS


# ─── ugovor_o_radu variants ───────────────────────────────────────────────────

def test_ugovor_o_radu_explicit_header():
    """Direct 'UGOVOR O RADU' phrase triggers employment contract."""
    passages = ["UGOVOR O RADU br. 123/2024 zaključen između Poslodavca i Zaposlenog."]
    assert detect_doc_type(passages) == "ugovor_o_radu"


def test_ugovor_o_radu_keyword_pair():
    """ZAPOSLENI + POSLODAVAC keyword pair triggers employment contract."""
    passages = [
        "Zaposleni se obavezuje da obavlja poslove na poziciji programera.",
        "Poslodavac isplaćuje zaradu jednom mesečno.",
    ]
    assert detect_doc_type(passages) == "ugovor_o_radu"


def test_ugovor_o_radu_mixed_case():
    """Detection is case-insensitive (text is uppercased internally)."""
    passages = ["Poslodavac Firma d.o.o. angažuje zaposleni Petar Petrović."]
    assert detect_doc_type(passages) == "ugovor_o_radu"


# ─── ugovor_o_zakupu ─────────────────────────────────────────────────────────

def test_ugovor_o_zakupu_explicit():
    """UGOVOR O ZAKUPU triggers lease contract."""
    passages = ["UGOVOR O ZAKUPU STANA zaključen između Zakupodavca i Zakupca."]
    assert detect_doc_type(passages) == "ugovor_o_zakupu"


def test_ugovor_o_zakupu_keyword_pair():
    """ZAKUPODAVAC + ZAKUPAC pair triggers lease contract."""
    passages = ["Zakupodavac iznajmljuje stan. Zakupac plaća kiriju mesečno."]
    assert detect_doc_type(passages) == "ugovor_o_zakupu"


# ─── ugovor_o_kupoprodaji ─────────────────────────────────────────────────────

def test_ugovor_o_kupoprodaji_explicit():
    """UGOVOR O KUPOPRODAJI triggers sale contract."""
    passages = ["UGOVOR O KUPOPRODAJI NEPOKRETNOSTI zaključen između Prodavca i Kupca."]
    assert detect_doc_type(passages) == "ugovor_o_kupoprodaji"


# ─── Unknown / edge cases ─────────────────────────────────────────────────────

def test_empty_passages_returns_none():
    """Empty list returns None — fail-open."""
    assert detect_doc_type([]) is None


def test_unrelated_text_returns_none():
    """Random unrelated text returns None."""
    passages = ["Faktura br. 001/2024 za isporučenu robu."]
    assert detect_doc_type(passages) is None


def test_single_short_passage_handled():
    """Single very short passage doesn't crash and returns None if no match."""
    assert detect_doc_type(["OK"]) is None


# ─── DOC_TYPE_CONSTRAINTS sanity ─────────────────────────────────────────────

def test_doc_type_constraints_keys_match():
    """Every key returned by detect_doc_type has an entry in DOC_TYPE_CONSTRAINTS."""
    known_types = ["ugovor_o_radu", "ugovor_o_zakupu", "ugovor_o_kupoprodaji"]
    for t in known_types:
        assert t in DOC_TYPE_CONSTRAINTS, f"Missing constraint for {t}"
        assert len(DOC_TYPE_CONSTRAINTS[t]) > 20


def test_ugovor_o_radu_constraint_forbids_zdi():
    """Employment contract constraint must mention ZDI prohibition."""
    constraint = DOC_TYPE_CONSTRAINTS["ugovor_o_radu"]
    assert "digitalnoj imovini" in constraint.lower() or "ZDI" in constraint


# ─── Fix-2.5a: ZR 53 annual cap in constraint (Q3 fix) ──────────────────────

def test_ugovor_o_radu_constraint_has_250h_annual_cap():
    """Employment contract constraint must state ZR 53 annual 250h cap."""
    constraint = DOC_TYPE_CONSTRAINTS["ugovor_o_radu"]
    assert "250" in constraint, "Annual prekovremeni cap (250h/god) must appear in constraint"


def test_ugovor_o_radu_constraint_mentions_all_three_zr53_limits():
    """Constraint must reference all three ZR 53 limits: weekly, monthly, annual."""
    constraint = DOC_TYPE_CONSTRAINTS["ugovor_o_radu"]
    assert "8h" in constraint or "8 h" in constraint or "nedeljn" in constraint.lower()
    assert "32h" in constraint or "32 h" in constraint or "mesečn" in constraint.lower()
    assert "250h" in constraint or "250 h" in constraint or "godišnj" in constraint.lower()


# ─── Fix-2.5b: DOC_CONTEXT_ADDENDUM radnih vs kalendarskih (Q4 fix) ─────────

def test_addendum_contains_unit_normalization_rule():
    """_DOC_CONTEXT_ADDENDUM must contain instruction about radnih vs kalendarskih dana."""
    addendum = _main_mod._DOC_CONTEXT_ADDENDUM
    # Check for the key normalization fact
    assert "radni" in addendum.lower() or "RADNIM" in addendum
    assert "kalendarski" in addendum.lower() or "kalendarsk" in addendum.lower()


def test_addendum_states_15_radnih_greater_than_8():
    """Example in addendum must show 15 radnih dana > 8 (correct direction)."""
    addendum = _main_mod._DOC_CONTEXT_ADDENDUM
    # The correct example must be present (TAČNO direction)
    assert "15 (radnih dana) > 8" in addendum or "15 radnih dana > 8" in addendum
