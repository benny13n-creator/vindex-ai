# -*- coding: utf-8 -*-
"""
Tests for IntakeWorker._guess_suffix — Mission 001 / Night Shift M-001 (2026-08-02).

This is the piece that decides which extension a downloaded blob gets before
uploaded_doc.extractor.extract() dispatches on it. Before this mission, an image
job would fall through every branch and default to ".pdf" -- pypdf would then
fail to parse the JPEG bytes as a PDF, identically on every retry attempt
(not a transient failure), so the job would exhaust its retries and land in
mark_job_failed with a confusing error that has nothing to do with the real
cause (unsupported format never reaching the right extractor).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.intake_worker import IntakeWorker


def test_guess_suffix_from_jpg_filename():
    assert IntakeWorker._guess_suffix("presuda.jpg", None) == ".jpg"


def test_guess_suffix_from_jpeg_filename():
    assert IntakeWorker._guess_suffix("presuda.JPEG", None) == ".jpeg"


def test_guess_suffix_from_png_filename():
    assert IntakeWorker._guess_suffix("skenirano.png", None) == ".png"


def test_guess_suffix_from_jpeg_mime_when_filename_missing():
    """Matches the documented real scenario: the original_filename/mime_type
    write is best-effort (routers/smart_intake.py) and can fail non-fatally,
    leaving only the mime_type the storage layer captured."""
    assert IntakeWorker._guess_suffix(None, "image/jpeg") == ".jpg"


def test_guess_suffix_from_png_mime_when_filename_missing():
    assert IntakeWorker._guess_suffix(None, "image/png") == ".png"


def test_guess_suffix_still_defaults_to_pdf_for_unknown():
    """Unchanged existing behavior — must not regress."""
    assert IntakeWorker._guess_suffix(None, None) == ".pdf"
    assert IntakeWorker._guess_suffix("mystery.xyz", "application/x-mystery") == ".pdf"


def test_guess_suffix_existing_pdf_docx_txt_unaffected():
    """Unchanged existing behavior — must not regress."""
    assert IntakeWorker._guess_suffix("ugovor.pdf", None) == ".pdf"
    assert IntakeWorker._guess_suffix("ugovor.docx", None) == ".docx"
    assert IntakeWorker._guess_suffix("beleska.txt", None) == ".txt"
