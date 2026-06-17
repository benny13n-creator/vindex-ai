# -*- coding: utf-8 -*-
"""Tests for PDF empty/garbage text detection in extract_pdf."""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from uploaded_doc.extractor import extract_pdf


def _mock_reader(pages_text: list[str]):
    """Return a mock pypdf.PdfReader with given per-page texts."""
    reader = MagicMock()
    mock_pages = []
    for t in pages_text:
        page = MagicMock()
        page.extract_text.return_value = t
        mock_pages.append(page)
    reader.pages = mock_pages
    return reader


def test_empty_pdf_flagged_as_scanned(tmp_path):
    """PDF where every page returns '' → total_chars=0 → is_scanned=True."""
    dummy = tmp_path / "empty.pdf"
    dummy.write_bytes(b"%PDF-1.4")
    with patch("pypdf.PdfReader", return_value=_mock_reader(["", ""])):
        text, is_scanned, _ = extract_pdf(dummy)
    assert is_scanned is True, "Empty PDF must be flagged as unreadable"
    assert text.strip() == ""


def test_near_empty_pdf_flagged_as_scanned(tmp_path):
    """PDF with only 99 total chars → below total_chars < 100 threshold → is_scanned=True."""
    dummy = tmp_path / "sparse.pdf"
    dummy.write_bytes(b"%PDF-1.4")
    # 99 chars across 3 pages — avg=33 < 50, AND total < 100
    with patch("pypdf.PdfReader", return_value=_mock_reader(["aaa " * 8, "bbb", ""])):
        text, is_scanned, _ = extract_pdf(dummy)
    assert is_scanned is True


def test_single_page_with_100_chars_not_scanned(tmp_path):
    """PDF with exactly 100 chars on 1 page → avg=100 >= 50, total >= 100 → is_scanned=False."""
    dummy = tmp_path / "ok.pdf"
    dummy.write_bytes(b"%PDF-1.4")
    page_text = "a" * 100
    with patch("pypdf.PdfReader", return_value=_mock_reader([page_text])):
        text, is_scanned, _ = extract_pdf(dummy)
    assert is_scanned is False, "100-char page must not be flagged as scanned"
    assert page_text in text


def test_whitespace_only_pdf_flagged_as_scanned(tmp_path):
    """PDF where pages return only whitespace → strip → total_chars=0 → is_scanned=True."""
    dummy = tmp_path / "whitespace.pdf"
    dummy.write_bytes(b"%PDF-1.4")
    with patch("pypdf.PdfReader", return_value=_mock_reader(["   \n\t  ", "  "])):
        text, is_scanned, _ = extract_pdf(dummy)
    assert is_scanned is True, "Whitespace-only PDF must be flagged as unreadable"


def test_normal_pdf_not_scanned(tmp_path):
    """PDF with ample text per page → is_scanned=False."""
    dummy = tmp_path / "normal.pdf"
    dummy.write_bytes(b"%PDF-1.4")
    page_text = "Zakon o radu, Član 162 — " * 20  # ~500 chars
    with patch("pypdf.PdfReader", return_value=_mock_reader([page_text, page_text])):
        text, is_scanned, _ = extract_pdf(dummy)
    assert is_scanned is False
    assert "Zakon o radu" in text
