# -*- coding: utf-8 -*-
"""Tests for OCR fallback in extract_pdf (fitz + pytesseract).

fitz and pytesseract are not installed locally — tests inject mock modules
into sys.modules before the lazy imports inside extract_pdf fire.
"""
import sys
import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.extractor import extract_pdf


def _sparse_pypdf_reader():
    """Mock pypdf.PdfReader that returns empty page text (triggers OCR path)."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    reader = MagicMock()
    reader.pages = [mock_page]
    return reader


def _build_fitz_mock(ocr_pages: list[str]):
    """Return (mock_fitz_module, mock_tesseract_module, mock_pil_image_module).

    mock_fitz.open() returns a document whose pages produce pixmaps.
    mock_tesseract.image_to_string() cycles through ocr_pages values.
    """
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"\x89PNG\r\n\x1a\n"  # fake PNG bytes

    # Each page yields its own OCR text
    mock_fitz_pages = []
    for _ in ocr_pages:
        p = MagicMock()
        p.get_pixmap.return_value = mock_pixmap
        mock_fitz_pages.append(p)

    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter(mock_fitz_pages))
    mock_fitz = MagicMock()
    mock_fitz.open.return_value = mock_doc

    mock_tesseract = MagicMock()
    mock_tesseract.image_to_string.side_effect = ocr_pages

    mock_image_module = MagicMock()
    mock_image_module.open.return_value = MagicMock()
    mock_pil = MagicMock()
    mock_pil.Image = mock_image_module

    return mock_fitz, mock_tesseract, mock_image_module, mock_pil


# ─── T1: OCR success — returns text + is_scanned=False ───────────────────────

def test_ocr_success_returns_text_not_scanned(tmp_path):
    """Scanned PDF → OCR returns >100 chars → extract_pdf returns (text, False)."""
    dummy = tmp_path / "scan.pdf"
    dummy.write_bytes(b"%PDF-1.4")

    ocr_result = (
        "Član 1 Ugovorne strane\n"
        "Zaposlen pristaje na uslove rada u skladu sa Zakonom o radu.\n"
        "Poslodavac se obavezuje da isplati zaradu u roku od 15 dana."
    )
    assert len(ocr_result) > 100, "OCR result must be >100 chars for this test to be valid"

    mock_fitz, mock_tesseract, mock_image_module, mock_pil = _build_fitz_mock([ocr_result])

    with patch("pypdf.PdfReader", return_value=_sparse_pypdf_reader()), \
         patch.dict(sys.modules, {
             "fitz": mock_fitz,
             "pytesseract": mock_tesseract,
             "PIL": mock_pil,
             "PIL.Image": mock_image_module,
         }):
        text, is_scanned = extract_pdf(dummy)

    assert is_scanned is False, "Successful OCR must set is_scanned=False"
    assert "Član 1" in text
    assert "Ugovorne strane" in text


# ─── T2: OCR returns <100 chars → still unreadable → (empty, True) ───────────

def test_ocr_short_output_still_unreadable(tmp_path):
    """OCR returns <100 chars → not enough text → extract_pdf returns ('', True)."""
    dummy = tmp_path / "scan.pdf"
    dummy.write_bytes(b"%PDF-1.4")

    short_ocr = "abc"  # < 100 chars

    mock_fitz, mock_tesseract, mock_image_module, mock_pil = _build_fitz_mock([short_ocr])

    with patch("pypdf.PdfReader", return_value=_sparse_pypdf_reader()), \
         patch.dict(sys.modules, {
             "fitz": mock_fitz,
             "pytesseract": mock_tesseract,
             "PIL": mock_pil,
             "PIL.Image": mock_image_module,
         }):
        text, is_scanned = extract_pdf(dummy)

    assert is_scanned is True, "Short OCR output must still be flagged as unreadable"
    assert text == ""


# ─── T3: OCR library raises → silently falls through → ('', True) ────────────

def test_ocr_exception_falls_through(tmp_path):
    """If fitz raises during OCR, extract_pdf silently returns ('', True)."""
    dummy = tmp_path / "scan.pdf"
    dummy.write_bytes(b"%PDF-1.4")

    mock_fitz = MagicMock()
    mock_fitz.open.side_effect = RuntimeError("fitz init failed")
    mock_tesseract = MagicMock()
    mock_image_module = MagicMock()
    mock_pil = MagicMock()
    mock_pil.Image = mock_image_module

    with patch("pypdf.PdfReader", return_value=_sparse_pypdf_reader()), \
         patch.dict(sys.modules, {
             "fitz": mock_fitz,
             "pytesseract": mock_tesseract,
             "PIL": mock_pil,
             "PIL.Image": mock_image_module,
         }):
        text, is_scanned = extract_pdf(dummy)

    assert is_scanned is True
    assert text == ""


# ─── T4: Normal (non-scanned) PDF skips OCR entirely ─────────────────────────

def test_normal_pdf_skips_ocr(tmp_path):
    """PDF with >100 chars total must skip OCR and return pypdf text directly."""
    dummy = tmp_path / "normal.pdf"
    dummy.write_bytes(b"%PDF-1.4")

    page_text = "Zakon o radu, Član 162 — zaštita zaposlenih. " * 5  # >100 chars

    mock_page = MagicMock()
    mock_page.extract_text.return_value = page_text
    reader = MagicMock()
    reader.pages = [mock_page]

    # fitz should NOT be called
    mock_fitz = MagicMock()

    with patch("pypdf.PdfReader", return_value=reader), \
         patch.dict(sys.modules, {"fitz": mock_fitz}):
        text, is_scanned = extract_pdf(dummy)

    assert is_scanned is False
    assert "Zakon o radu" in text
    mock_fitz.open.assert_not_called()
