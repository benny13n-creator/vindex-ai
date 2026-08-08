# -*- coding: utf-8 -*-
"""
Tests for extract_image() — Mission 001 / Night Shift M-001 (2026-08-02).

pytesseract is not installed locally, same as tests/test_extractor_ocr.py — mocked via
sys.modules injection. PIL IS installed (extract_pdf's OCR branch already depends on it),
so these tests use real Pillow-generated images, only pytesseract is mocked.
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image

from uploaded_doc.extractor import extract, extract_image, DocumentSafetyLimitExceeded, MAX_IMAGE_PIXELS


def _make_real_image(path, size=(200, 100), color=(255, 255, 255)):
    img = Image.new("RGB", size, color=color)
    img.save(path)


def _fake_image_to_data(ocr_text: str, conf: float = 95.0) -> dict:
    """Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-023): _ocr_image now calls
    pytesseract.image_to_data (not image_to_string) to also get per-word
    confidence -- builds the same Output.DICT shape from a plain multi-line
    string, one line = one (block,par,line) group, all words at `conf`."""
    text_col, conf_col, block_col, par_col, line_col = [], [], [], [], []
    for line_idx, line in enumerate(ocr_text.split("\n")):
        for word in line.split():
            text_col.append(word)
            conf_col.append(conf)
            block_col.append(1)
            par_col.append(1)
            line_col.append(line_idx)
    return {"text": text_col, "conf": conf_col, "block_num": block_col, "par_num": par_col, "line_num": line_col}


def _mock_tesseract(ocr_text: str, conf: float = 95.0):
    m = MagicMock()
    m.get_languages.return_value = []  # → _detect_ocr_lang() falls back to "eng"
    m.image_to_string.return_value = ocr_text  # kept for any incidental caller, no longer used by _ocr_image
    m.image_to_data.return_value = _fake_image_to_data(ocr_text, conf)
    m.Output.DICT = "dict"
    return m


# ─── T1: successful OCR on a real JPEG ────────────────────────────────────────

def test_extract_image_jpeg_success(tmp_path):
    path = tmp_path / "served_decision.jpg"
    _make_real_image(path)

    ocr_result = (
        "Osnovni sud u Beogradu\n"
        "Presuda broj P-123/2026\n"
        "Rok za žalbu je 15 dana od dana prijema ove presude protiv tuženog."
    )
    assert len(ocr_result) > 100

    with patch.dict(sys.modules, {"pytesseract": _mock_tesseract(ocr_result)}):
        text, is_scanned, ocr_used, _pages, _conf = extract_image(path)

    assert is_scanned is False
    assert ocr_used is True
    assert "Presuda broj P-123/2026" in text


# ─── T2: successful OCR on a real PNG (both accepted image suffixes) ─────────

def test_extract_image_png_success(tmp_path):
    path = tmp_path / "screenshot.png"
    _make_real_image(path)

    ocr_result = "Ugovor o zakupu, član 4 — visina zakupnine i način plaćanja." * 3
    assert len(ocr_result) > 100

    with patch.dict(sys.modules, {"pytesseract": _mock_tesseract(ocr_result)}):
        text, is_scanned, ocr_used, _pages, _conf = extract_image(path)

    assert ocr_used is True
    assert "zakupnine" in text


# ─── T3: OCR returns too little text → treated as failed, same threshold as PDF ──

def test_extract_image_insufficient_text_treated_as_failed(tmp_path):
    path = tmp_path / "blurry.jpg"
    _make_real_image(path)

    with patch.dict(sys.modules, {"pytesseract": _mock_tesseract("abc")}):
        text, is_scanned, ocr_used, _pages, _conf = extract_image(path)

    assert is_scanned is True
    assert ocr_used is False
    assert text == ""


# ─── T4: corrupt/non-image file → fails cleanly, not an unhandled exception ──

def test_extract_image_corrupt_file_fails_cleanly(tmp_path):
    path = tmp_path / "not_really_an_image.jpg"
    path.write_bytes(b"this is not image data at all")

    text, is_scanned, ocr_used, _pages, _conf = extract_image(path)

    assert is_scanned is True
    assert ocr_used is False
    assert text == ""


# ─── T5: oversized image dimensions rejected before OCR runs (decompression-bomb guard) ──

def test_extract_image_rejects_oversized_dimensions(tmp_path, monkeypatch):
    path = tmp_path / "huge.png"
    _make_real_image(path, size=(10, 10))  # small file on disk

    # Patch Image.open's returned object's .size to simulate a declared
    # huge pixel count without actually allocating a huge image in the test.
    # extractor.py does `from PIL import Image` lazily inside the function,
    # so patching PIL.Image.open at the source is what's actually consulted.
    class _FakeImg:
        size = (10000, 10000)  # 100,000,000 pixels > MAX_IMAGE_PIXELS
        def verify(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_open(p):
        return _FakeImg()

    with patch("PIL.Image.open", _fake_open):
        try:
            extract_image(path)
            assert False, "expected DocumentSafetyLimitExceeded to propagate"
        except DocumentSafetyLimitExceeded as e:
            assert "10000x10000" in str(e) or "100000000" in str(e)


# ─── T6: extract() dispatches .jpg/.jpeg/.png to extract_image ──────────────

def test_extract_dispatches_image_suffixes(tmp_path):
    for suffix in (".jpg", ".jpeg", ".png"):
        path = tmp_path / f"doc{suffix}"
        _make_real_image(path)
        with patch.dict(sys.modules, {"pytesseract": _mock_tesseract("Član 5 ovog ugovora " * 10)}):
            text, is_scanned, ocr_used, _pages, _conf = extract(path)
        assert ocr_used is True, f"extract() must route {suffix} through OCR"
        assert "ugovora" in text
