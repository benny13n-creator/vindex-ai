# -*- coding: utf-8 -*-
"""
Unit tests for chunker_case_law.py (Phase 1.1).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chunker_case_law import (
    chunk_decision,
    chunk_section,
    count_tokens,
    extract_cited_articles,
    split_into_sections,
)


def test_section_splitting_with_markers():
    """
    Text with spaced-letter REŠENJE + OBRAZLOŽENJE markers must produce
    3 sections: HEADER, IZREKA, OBRAZLOŽENJE.
    """
    text = (
        "Republika Srbija\nVRHOVNI SUD\nKzz 1/2026\n01.01.2026.\n"
        "R E Š E NJ E\n"
        "ODBACUJE SE zahtev.\n"
        "O b r a z l o ž e nj e\n"
        "Zahtev je odbačen jer branilac nije naveo razloge."
    )
    sections = split_into_sections(text)
    names = [s[0] for s in sections]
    assert "HEADER" in names, f"Expected HEADER, got {names}"
    assert "IZREKA" in names, f"Expected IZREKA, got {names}"
    assert "OBRAZLOŽENJE" in names, f"Expected OBRAZLOŽENJE, got {names}"
    assert len(sections) == 3, f"Expected 3 sections, got {len(sections)}: {names}"


def test_section_splitting_presuda_marker():
    """
    P R E S U D U spaced-letter heading must also produce IZREKA section.
    """
    text = (
        "Republika Srbija\nVRHOVNI SUD\nRev 100/2026\n01.02.2026.\nU IME NARODA\n"
        "P R E S U D U\n"
        "ODBIJA SE revizija tuženog.\n"
        "O b r a z l o ž e nj e\n"
        "Revizija je odbijena zbog nedostatka osnova."
    )
    sections = split_into_sections(text)
    names = [s[0] for s in sections]
    assert "IZREKA" in names, f"Expected IZREKA, got {names}"
    assert "OBRAZLOŽENJE" in names, f"Expected OBRAZLOŽENJE, got {names}"


def test_section_splitting_no_markers():
    """
    Text without any known markers must produce a single BODY section.
    """
    text = "Ovo je tekst odluke bez zaglavlja sekcija."
    sections = split_into_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "BODY"
    assert sections[0][1] == text


def test_chunk_size_bounds():
    """
    Every chunk produced by chunk_section must be ≤ 800 tokens.
    """
    # Build a text that is definitely > 600 tokens
    sentence = "Vrhovni sud je utvrdio da je žalba neosnovana i odbio je isti zahtev. "
    long_text = sentence * 60  # roughly 1200–1500 tokens
    chunks = chunk_section("OBRAZLOŽENJE", long_text)
    assert len(chunks) >= 2, f"Expected multiple chunks for long text, got {len(chunks)}"
    for i, ch in enumerate(chunks):
        tc = count_tokens(ch)
        assert tc <= 800, f"Chunk {i} has {tc} tokens (> 800 limit): {ch[:80]!r}"
        assert tc >= 1, f"Chunk {i} is empty"


def test_cited_articles_extraction():
    """
    Various article reference forms must be extracted and deduplicated.
    """
    text = (
        "Prema članu 203 KZ, kao i čl. 210 i čl. 210 KZ, "
        "te saglasno članovima 200 ZKP, ovo je osnov."
    )
    result = extract_cited_articles(text)
    assert "203" in result, f"Expected 203 in {result}"
    assert "210" in result, f"Expected 210 in {result}"
    assert "200" in result, f"Expected 200 in {result}"
    # 210 appears twice in text but must be deduplicated
    assert result.count("210") == 1, f"Duplicate 210 in {result}"


def test_empty_decision_number_fallback():
    """
    When decision_number is empty (3 partial zastitaprava decisions),
    decision_id_fallback must be set to the decision_id, and every chunk
    must carry that fallback in its metadata.
    """
    decision_json = {
        "decision_id": "id_b4d6052a4905",
        "decision_number": "",
        "matter": "Zaštita prava",
        "court": "Vrhovni sud",
        "decision_date": "2026-01-29",
        "registrant": "",
        "source_url": "https://www.vrh.sud.rs/sr-lat/id-b4d6052a4905",
        "raw_text": (
            "Vrhovni sud, sudija Janković, odlučujući o žalbi predlagača. "
            "R E Š E NJ E\n"
            "ODBACUJE SE žalba.\n"
            "O b r a z l o ž e nj e\n"
            "Žalba je odbačena jer je nedozvoljena prema čl. 17 Zakona."
        ),
        "raw_text_length": 200,
        "scraped_at": "2026-05-10T11:00:00+00:00",
        "scraper_version": "1.0",
        "parse_warnings": ["MISSING: decision_number"],
    }
    result = chunk_decision(decision_json)
    assert result["decision_number"] == ""
    assert len(result["chunks"]) >= 1
    for chunk in result["chunks"]:
        assert chunk["metadata"]["decision_id_fallback"] == "id_b4d6052a4905", (
            f"Fallback not set: {chunk['metadata']['decision_id_fallback']}"
        )
        assert chunk["metadata"]["doc_type"] == "sudska_praksa"
