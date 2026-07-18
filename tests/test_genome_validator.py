# -*- coding: utf-8 -*-
"""
Tests for Case Genome Faza 1.3 (90-dnevni plan, 2026-07-18):
shared/genome_validator.py — advisory, non-blocking, deterministic
verification layer. Nula GPT poziva, nula I/O — svi testovi su cisti
unit testovi bez mock-ovanja baze/mreze.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.genome_validator import verify_genome


def _docs(*nazivi_i_brojevi):
    """Pomocna: [(naziv, redni_broj), ...] -> lista docs dict-ova."""
    return [{"naziv_fajla": n, "redni_broj": rb} for n, rb in nazivi_i_brojevi]


# ═══════════════════════════════════════════════════════════════════════════
# dokazi_rang — provenance protiv stvarnih dokumenata
# ═══════════════════════════════════════════════════════════════════════════

def test_dokazi_rang_flags_nonexistent_document():
    genome = {"dokazi_rang": [{"naziv": "ugovor.pdf", "snaga_score": 80, "zvezdice": 4}]}
    docs = _docs(("racun.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["odluka"] == "require_review"
    assert any("ugovor.pdf" in f["razlog"] for f in result["hard_flags"])


def test_dokazi_rang_passes_when_document_exists():
    genome = {"dokazi_rang": [{"naziv": "ugovor.pdf", "snaga_score": 80, "zvezdice": 4}]}
    docs = _docs(("ugovor.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["odluka"] == "approve"
    assert result["hard_flags"] == []


def test_dokazi_rang_match_is_case_insensitive():
    genome = {"dokazi_rang": [{"naziv": "UGOVOR.PDF", "snaga_score": 80, "zvezdice": 4}]}
    docs = _docs(("ugovor.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["hard_flags"] == []


# ═══════════════════════════════════════════════════════════════════════════
# kontradikcije — DOK-XX reference moraju biti stvarne
# ═══════════════════════════════════════════════════════════════════════════

def test_kontradikcije_flags_nonexistent_dok_reference():
    genome = {"kontradikcije": [{"opis": "sukob", "lokacija_1": "DOK-05 str.2", "lokacija_2": "DOK-01"}]}
    docs = _docs(("a.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["odluka"] == "require_review"
    assert any("DOK-05" in f["razlog"] for f in result["hard_flags"])
    # DOK-01 postoji, ne sme biti flagovan
    assert not any("DOK-01" in f["razlog"] for f in result["hard_flags"])


def test_kontradikcije_passes_when_all_dok_refs_exist():
    genome = {"kontradikcije": [{"opis": "sukob", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02"}]}
    docs = _docs(("a.pdf", 1), ("b.pdf", 2))
    result = verify_genome(genome, docs)
    assert result["hard_flags"] == []


def test_kontradikcije_ignores_non_dok_locations():
    """lokacija moze biti slobodan opis, ne uvek DOK-XX — ne flaguje se ako nema pattern."""
    genome = {"kontradikcije": [{"opis": "sukob", "lokacija_1": "usmeni iskaz svedoka", "lokacija_2": "DOK-01"}]}
    docs = _docs(("a.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["hard_flags"] == []


# ═══════════════════════════════════════════════════════════════════════════
# relevantni_zakoni — soft check, reuse analiza/validator.py
# ═══════════════════════════════════════════════════════════════════════════

def test_relevantni_zakoni_flags_unknown_law_as_soft():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["Zakon o izmisljenim stvarima"]}}
    result = verify_genome(genome, [])
    assert result["odluka"] == "approve_with_warning"
    assert result["hard_flags"] == []
    assert any("izmisljenim" in f["stavka"] for f in result["soft_flags"])


def test_relevantni_zakoni_passes_known_law():
    # Napomena: _POZNATI_ZAKONI u analiza/validator.py meša kratke akronime
    # velikim slovima ("ZOO", "ZPP") sa lowercase stem-frazama ("zakon o rad").
    # validate_law_refs poredi protiv .lower() ulaza, pa akronimi (case-sensitive
    # 'in' provera) nikad ne mogu da se poklope — pre-postojeca mana u fajlu koji
    # se ovde samo reuse-uje, ne popravlja (van obima Faze 1.3). Zato test koristi
    # stem-frazu koja stvarno prolazi kroz postojecu logiku, ne akronim.
    genome = {"pravna_teorija": {"relevantni_zakoni": ["Zakon o radu čl. 179"]}}
    result = verify_genome(genome, [])
    assert result["odluka"] == "approve"
    assert result["soft_flags"] == []


def test_relevantni_zakoni_empty_list_is_noop():
    genome = {"pravna_teorija": {"relevantni_zakoni": []}}
    result = verify_genome(genome, [])
    assert result["odluka"] == "approve"


# ═══════════════════════════════════════════════════════════════════════════
# snaga konzistentnost — interna logika, ne provenance
# ═══════════════════════════════════════════════════════════════════════════

def test_snaga_procent_contradicts_negative_faktori_is_hard_flag():
    genome = {
        "snaga_predmeta_procent": 80,
        "snaga_faktori": [{"faktor": "x", "uticaj": "-30"}, {"faktor": "y", "uticaj": "-20"}],
    }
    result = verify_genome(genome, [])
    assert result["odluka"] == "require_review"
    assert any("snaga_predmeta_procent" in f["polje"] for f in result["hard_flags"])


def test_snaga_procent_low_contradicts_positive_faktori_is_hard_flag():
    genome = {
        "snaga_predmeta_procent": 20,
        "snaga_faktori": [{"faktor": "x", "uticaj": "+40"}],
    }
    result = verify_genome(genome, [])
    assert result["odluka"] == "require_review"


def test_snaga_procent_consistent_with_faktori_passes():
    genome = {
        "snaga_predmeta_procent": 80,
        "snaga_faktori": [{"faktor": "x", "uticaj": "+30"}, {"faktor": "y", "uticaj": "-5"}],
    }
    result = verify_genome(genome, [])
    assert result["hard_flags"] == []


def test_zvezdice_mismatch_is_soft_flag():
    genome = {"dokazi_rang": [{"naziv": "a.pdf", "snaga_score": 90, "zvezdice": 1}]}
    docs = _docs(("a.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["odluka"] == "approve_with_warning"
    assert any("zvezdice" in f["polje"] for f in result["soft_flags"])


def test_zvezdice_matching_formula_passes():
    genome = {"dokazi_rang": [{"naziv": "a.pdf", "snaga_score": 90, "zvezdice": 5}]}  # round(90/20)=5
    docs = _docs(("a.pdf", 1))
    result = verify_genome(genome, docs)
    assert result["soft_flags"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Agregacija/odluka + otpornost na greske
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_genome_approves_with_no_flags():
    result = verify_genome({}, [])
    assert result["odluka"] == "approve"
    assert result["hard_flags"] == []
    assert result["soft_flags"] == []


def test_hard_flag_wins_over_soft_flag_in_decision():
    genome = {
        "dokazi_rang": [{"naziv": "nepostojeci.pdf", "snaga_score": 90, "zvezdice": 1}],  # hard + soft (zvezdice mismatch)
        "pravna_teorija": {"relevantni_zakoni": ["Nepoznat zakon xyz"]},  # soft
    }
    result = verify_genome(genome, [])
    assert result["odluka"] == "require_review"
    assert len(result["hard_flags"]) >= 1
    assert len(result["soft_flags"]) >= 1


def test_never_raises_on_malformed_genome():
    malformed = {
        "dokazi_rang": "ovo nije lista",
        "kontradikcije": [{"lokacija_1": None, "lokacija_2": 12345}],
        "snaga_predmeta_procent": "nije broj",
        "snaga_faktori": "takodje nije lista",
        "pravna_teorija": "nije dict",
    }
    result = verify_genome(malformed, None)  # docs=None takodje
    assert result["odluka"] in ("approve", "approve_with_warning", "require_review")


def test_reports_latency_as_nonnegative_number():
    result = verify_genome({"dokazi_rang": []}, [])
    assert isinstance(result["provereno_u_ms"], (int, float))
    assert result["provereno_u_ms"] >= 0
