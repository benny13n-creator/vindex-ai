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
