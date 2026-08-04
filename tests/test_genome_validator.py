# -*- coding: utf-8 -*-
"""
Tests for Case Genome Faza 1.3 (90-dnevni plan, 2026-07-18) i Reliability
Patch v2 (2026-07-18, posle CASE_GENOME_REALITY_VALIDATION_REPORT.md):
shared/genome_validator.py — advisory, non-blocking, deterministic
verification layer PLUS compute_snaga_score() backend scoring. Nula GPT
poziva, nula I/O — svi testovi su cisti unit testovi bez mock-ovanja
baze/mreze.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.genome_validator import (
    verify_genome, compute_snaga_score, validate_dok_reference,
    validate_graph_edge_references, validate_predmet_reference,
)


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


# ═══════════════════════════════════════════════════════════════════════════
# v2 — compute_snaga_score (Reliability Patch, 2026-07-18)
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_snaga_score_baseline_with_no_faktori():
    result = compute_snaga_score({})
    assert result["snaga_predmeta_procent"] == 50  # baseline, neto=0
    assert result["snaga_predmeta"] == "srednja"


def test_compute_snaga_score_derives_from_faktori_sum():
    genome = {"snaga_faktori": [{"uticaj": "+20"}, {"uticaj": "+15"}, {"uticaj": "-5"}]}
    result = compute_snaga_score(genome)
    assert result["snaga_predmeta_procent"] == 80  # 50 + 30
    assert result["snaga_predmeta"] == "jaka"  # >= 75


def test_compute_snaga_score_weak_case_gets_slaba():
    genome = {"snaga_faktori": [{"uticaj": "-10"}, {"uticaj": "-10"}]}
    result = compute_snaga_score(genome)
    assert result["snaga_predmeta_procent"] == 30  # 50 - 20
    assert result["snaga_predmeta"] == "slaba"  # < 35


def test_compute_snaga_score_clamps_to_0_100():
    genome_high = {"snaga_faktori": [{"uticaj": "+500"}]}
    assert compute_snaga_score(genome_high)["snaga_predmeta_procent"] == 100
    genome_low = {"snaga_faktori": [{"uticaj": "-500"}]}
    assert compute_snaga_score(genome_low)["snaga_predmeta_procent"] == 0


def test_compute_snaga_score_low_completeness_adds_visible_penalty_factor():
    genome = {"snaga_faktori": [{"faktor": "Pisani dokazi", "uticaj": "+20"}],
              "genome_kompletnost": "niska"}
    result = compute_snaga_score(genome)
    # 50 + 20 - 15 (kompletnost penal) = 55
    assert result["snaga_predmeta_procent"] == 55
    # penal mora biti VIDLJIV u vracenim faktorima, ne skriveno podesavanje
    assert any("kompletnost" in f.get("faktor", "").lower() for f in result["snaga_faktori"])


def test_compute_snaga_score_different_faktori_give_different_scores():
    """Direktan test zahteva iz Reliability Patch instrukcije: 'slicni slucajevi
    ne smeju automatski dobiti identican skor'."""
    slab = compute_snaga_score({"snaga_faktori": [{"uticaj": "-15"}, {"uticaj": "-10"}]})
    jak = compute_snaga_score({"snaga_faktori": [{"uticaj": "+20"}, {"uticaj": "+15"}]})
    assert slab["snaga_predmeta_procent"] != jak["snaga_predmeta_procent"]
    assert slab["snaga_predmeta"] != jak["snaga_predmeta"]


def test_compute_snaga_score_never_raises_on_malformed_input():
    result = compute_snaga_score({"snaga_faktori": "nije lista", "genome_kompletnost": 12345})
    assert 0 <= result["snaga_predmeta_procent"] <= 100


# ═══════════════════════════════════════════════════════════════════════════
# v2 — _validate_clan_brojevi / Legal Citation Verification v2
# ═══════════════════════════════════════════════════════════════════════════

def test_clan_broj_absurdno_visok_je_hard_flag():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["ZOO čl. 9999"]}}
    result = verify_genome(genome, [])
    assert result["odluka"] == "require_review"
    assert any("9999" in f["razlog"] for f in result["hard_flags"])


def test_clan_broj_normalan_ne_flaguje_kao_hard():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["ZOO čl. 262"]}}
    result = verify_genome(genome, [])
    assert all("navodi član" not in f["razlog"] for f in result["hard_flags"])


def test_clan_broj_ustav_ima_niziu_granicu_od_obicnog_zakona():
    # 300 je van opsega za Ustav (max ~250) ali unutar opsega za obican zakon (max 1200)
    ustav = verify_genome({"pravna_teorija": {"relevantni_zakoni": ["Ustav čl. 300"]}}, [])
    zakon = verify_genome({"pravna_teorija": {"relevantni_zakoni": ["ZOO čl. 300"]}}, [])
    assert any("300" in f["razlog"] for f in ustav["hard_flags"])
    assert not any("navodi član 300" in f["razlog"] for f in zakon["hard_flags"])


def test_clan_broj_sa_stavom_dodaje_soft_napomenu():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["Zakon o radu čl. 179 stav 2"]}}
    result = verify_genome(genome, [])
    assert any("stav" in f["razlog"].lower() for f in result["soft_flags"])


# ═══════════════════════════════════════════════════════════════════════════
# Program Beta (2026-08-04) — validate_dok_reference (Compare's evidence check)
# ═══════════════════════════════════════════════════════════════════════════

def test_validate_dok_reference_flags_dok_outside_known_set():
    flags = validate_dok_reference("DOK-05 je jaci dokaz jer sadrzi original ugovor.", {1, 2})
    assert len(flags) == 1
    assert "DOK-05" in flags[0]["razlog"]


def test_validate_dok_reference_passes_known_dok():
    flags = validate_dok_reference("DOK-01 je jaci dokaz.", {1, 2})
    assert flags == []


def test_validate_dok_reference_no_dok_pattern_is_not_flagged():
    """'ravnopravni' ili slobodan opis bez DOK-XX obrasca nije greska."""
    flags = validate_dok_reference("Dokumenti su ravnopravni po dokaznoj snazi.", {1, 2})
    assert flags == []


def test_validate_dok_reference_empty_text_is_noop():
    assert validate_dok_reference("", {1, 2}) == []
    assert validate_dok_reference(None, {1, 2}) == []


def test_validate_dok_reference_non_string_input_is_noop_not_typeerror():
    """Olympus Faza 10 (2026-08-04, Backend Reliability nalaz): response_format=
    json_object garantuje samo validan JSON objekat na vrhu, ne tip svakog polja
    -- non-string ulaz (GPT vratio listu/dict/int umesto stringa) se tiho
    ignorise, ne baca TypeError."""
    assert validate_dok_reference(["DOK-05"], {1, 2}) == []
    assert validate_dok_reference({"x": "DOK-05"}, {1, 2}) == []
    assert validate_dok_reference(42, {1, 2}) == []


def test_validate_dok_reference_custom_polje_naziv():
    """Program Beta (2026-08-04, prosireno posle AI Grounding nalaza): funkcija
    se sada poziva i za kontradikcije/razlike_kljucne stavke, ne samo
    koji_je_jaci_dokaz -- polje ime u flag-u mora odraziti pravo poreklo."""
    flags = validate_dok_reference("DOK-99 pominje nesto necuveno.", {1, 2}, polje="kontradikcije")
    assert len(flags) == 1
    assert flags[0]["polje"] == "kontradikcije"


def test_clan_broj_bez_clana_ne_baca_ni_ne_flaguje():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["Zakon o radu"]}}
    result = verify_genome(genome, [])
    assert result["odluka"] in ("approve", "approve_with_warning")


def test_clan_broj_nula_ili_negativan_je_hard_flag():
    genome = {"pravna_teorija": {"relevantni_zakoni": ["ZOO čl. 0"]}}
    result = verify_genome(genome, [])
    assert any("0" in f["stavka"] for f in result["hard_flags"])


# ═══════════════════════════════════════════════════════════════════════════
# Program Gamma (2026-08-04) — validate_graph_edge_references (Evidence Graph)
# ═══════════════════════════════════════════════════════════════════════════

def test_validate_graph_edge_references_flags_unknown_node():
    nodes = [{"id": "lice_01"}, {"id": "dok_ugovor"}]
    edges = [{"izvor": "lice_01", "cilj": "dok_nepostojeci", "tip_veze": "OSPORAVA"}]
    flags = validate_graph_edge_references(nodes, edges)
    assert len(flags) == 1
    assert "dok_nepostojeci" in flags[0]["razlog"]


def test_validate_graph_edge_references_passes_known_nodes():
    nodes = [{"id": "lice_01"}, {"id": "dok_ugovor"}]
    edges = [{"izvor": "lice_01", "cilj": "dok_ugovor", "tip_veze": "POMINJE"}]
    assert validate_graph_edge_references(nodes, edges) == []


def test_validate_graph_edge_references_empty_is_noop():
    assert validate_graph_edge_references([], []) == []
    assert validate_graph_edge_references(None, None) == []


def test_validate_graph_edge_references_malformed_input_never_raises():
    # nodes kao string ne baca izuzetak -- poznati_id ostaje prazan skup (fail-soft),
    # edge sa izvor/cilj koji nisu stringovi se i dalje bezbedno obradjuje.
    result = validate_graph_edge_references("nije lista", [{"izvor": 1, "cilj": 2}])
    assert isinstance(result, list)
    assert validate_graph_edge_references([{"id": "a"}], ["nije dict"]) == []


# ═══════════════════════════════════════════════════════════════════════════
# Program Gamma (2026-08-04) — validate_predmet_reference (Case Commander)
# ═══════════════════════════════════════════════════════════════════════════

def test_validate_predmet_reference_flags_unknown_prefix():
    poznati = {"11112222": "Predmet A", "33334444": "Predmet B"}
    flags = validate_predmet_reference("abcd1234", poznati)
    assert len(flags) == 1
    assert "abcd1234" in flags[0]["razlog"]
    assert flags[0]["polje"] == "predmet_id_prefix"


def test_validate_predmet_reference_passes_known_prefix_no_naziv_given():
    poznati = {"11112222": "Predmet A", "33334444": "Predmet B"}
    assert validate_predmet_reference("11112222", poznati) == []


def test_validate_predmet_reference_empty_is_noop():
    poznati = {"11112222": "Predmet A"}
    assert validate_predmet_reference("", poznati) == []
    assert validate_predmet_reference(None, poznati) == []


def test_validate_predmet_reference_flags_misattributed_naziv():
    """Olympus Faza 10 (2026-08-04, Evidence Integrity nalaz): REALAN prefiks
    ali POGRESAN naziv (GPT pomesao dva predmeta u istom portfoliju) mora
    biti uhvacen -- ne samo puko postojanje prefiksa."""
    poznati = {"11112222": "Petrović protiv Marković d.o.o.", "33334444": "Jovanović nasledstvo"}
    flags = validate_predmet_reference("11112222", poznati, predmet_naziv="Jovanović nasledstvo")
    assert len(flags) == 1
    assert flags[0]["polje"] == "predmet_naziv"
    assert "Jovanović nasledstvo" in flags[0]["razlog"]
    assert "Petrović protiv Marković" in flags[0]["razlog"]


def test_validate_predmet_reference_passes_matching_naziv_fuzzy():
    """Fuzzy (substring, case-insensitive) match -- manja parafraza naziva nije greska."""
    poznati = {"11112222": "Petrović protiv Marković d.o.o."}
    assert validate_predmet_reference("11112222", poznati, predmet_naziv="petrović protiv marković") == []


def test_validate_predmet_reference_no_naziv_check_when_naziv_not_given():
    poznati = {"11112222": "Petrović protiv Marković d.o.o."}
    assert validate_predmet_reference("11112222", poznati, predmet_naziv=None) == []
