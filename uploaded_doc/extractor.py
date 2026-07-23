from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── SEC-007 — zip-bomb / decompression-bomb guard ────────────────────────────
# .docx is a ZIP archive — python-docx unzips it fully into memory with no
# built-in limit. A small file on disk can decompress to gigabytes.
#
# Thresholds: the task's own illustrative example (ratio > 10:1) is not used
# literally here — ordinary legal documents (repetitive boilerplate clauses,
# tables) routinely compress well past 10:1 in DOCX's XML format, which would
# make a 10:1 ratio cap reject real documents, not just bombs. Real zip-bomb
# payloads compress at 100:1-1000:1+ (they're built from highly repetitive
# byte patterns specifically to maximize this). MAX_RATIO below is set
# higher than the task's example specifically to avoid false-positives on
# legitimate large contracts, while the absolute MAX_DECOMPRESSED_BYTES cap
# (matching the task's own 50MB figure) is the primary, unambiguous defense —
# no legitimate case-file DOCX needs to unzip to more than 50MB of raw XML.
MAX_DECOMPRESSED_BYTES = 50 * 1024 * 1024   # 50 MB — task's own stated cap
MAX_RATIO = 100                              # compressed:decompressed, per-entry
MAX_ZIP_ENTRIES = 2_000                      # sane upper bound for a .docx package


class DocumentSafetyLimitExceeded(Exception):
    """Raised when a .docx archive's declared decompressed size, per-entry
    compression ratio, or entry count exceeds a safety threshold — BEFORE
    python-docx ever attempts to actually decompress the archive."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Zip-bomb guard tripped: {reason}")


def _check_docx_zip_safety(path: Path) -> None:
    """
    Inspects the ZIP central directory (metadata only — does NOT decompress
    any entry) before python-docx is allowed to touch the file. Raises
    DocumentSafetyLimitExceeded if the archive's own declared sizes would blow past a
    safety threshold, so the actual decompression (the expensive, memory-
    exhausting part) never happens for a malicious file.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        # Not a valid zip at all — let python-docx's own error handling
        # produce the "corrupt file" message; not this guard's concern.
        return

    if len(infos) > MAX_ZIP_ENTRIES:
        raise DocumentSafetyLimitExceeded(f"{len(infos)} entries (max {MAX_ZIP_ENTRIES})")

    total_decompressed = 0
    for info in infos:
        total_decompressed += info.file_size
        if total_decompressed > MAX_DECOMPRESSED_BYTES:
            raise DocumentSafetyLimitExceeded(
                f"total decompressed size exceeds {MAX_DECOMPRESSED_BYTES} bytes"
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_RATIO:
                raise DocumentSafetyLimitExceeded(
                    f"entry {info.filename!r} ratio {ratio:.0f}:1 exceeds {MAX_RATIO}:1"
                )


# ─── SEC-007 — PDF page-count ceiling (SEC-027 companion) ────────────────────
# Not a decompression-ratio attack (PDF's per-stream FlateDecode compression
# isn't exposed as a simple pre-check the way a ZIP central directory is) —
# a much simpler, cheap defense-in-depth cap against page-count-explosion
# DoS, already recommended separately as SEC-027.
MAX_PDF_PAGES = 500


def extract_pdf(path: Path) -> tuple[str, bool, bool]:
    """Return (text, is_scanned, ocr_used).

    is_scanned=True  → PDF had no readable text and OCR also failed.
    ocr_used=True    → text came from OCR (scanned PDF successfully processed).
    """
    import pypdf

    reader = pypdf.PdfReader(str(path))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise DocumentSafetyLimitExceeded(f"{len(reader.pages)} PDF pages (max {MAX_PDF_PAGES})")

    pages: list[str] = []
    total_chars = 0
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        pages.append(text)
        total_chars += len(text)

    avg_chars = total_chars / max(len(reader.pages), 1)
    # Threshold: <30 chars/stranica ili ukupno <80 = verovatno skenirani
    is_scanned = avg_chars < 30 or total_chars < 80

    if not is_scanned:
        return "\n\n".join(pages), False, False

    # OCR fallback for scanned/unreadable PDFs
    try:
        import io
        import fitz  # pymupdf
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        # Detect available Tesseract languages for Serbian support
        try:
            available_langs = pytesseract.get_languages(config="")
        except Exception:
            available_langs = []

        # Prefer Cyrillic (srp) + Latin (srp_latn) + English
        if "srp" in available_langs and "srp_latn" in available_langs:
            ocr_lang = "srp+srp_latn+eng"
        elif "srp_latn" in available_langs:
            ocr_lang = "srp_latn+eng"
        elif "srp" in available_langs:
            ocr_lang = "srp+eng"
        else:
            ocr_lang = "eng"

        logger.info("[OCR] Pokrenuti OCR za %s — jezik: %s", path.name, ocr_lang)

        doc = fitz.open(str(path))
        ocr_pages: list[str] = []
        for page_num, page in enumerate(doc):
            pixmap = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pixmap.tobytes("png")))
            img = img.convert("L")
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            try:
                page_text = pytesseract.image_to_string(img, lang=ocr_lang, timeout=45)
            except Exception:
                try:
                    page_text = pytesseract.image_to_string(img, lang="eng", timeout=30)
                except Exception as e2:
                    logger.warning("[OCR] Stranica %d neuspešna: %s", page_num + 1, e2)
                    page_text = ""
            ocr_pages.append(page_text.strip())

        ocr_text = "\n\n".join(p for p in ocr_pages if p)
        if len(ocr_text.strip()) > 100:
            logger.info("[OCR] Uspešno — %d karaktera iz %d stranica", len(ocr_text), len(ocr_pages))
            return ocr_text, False, True
        else:
            logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(ocr_text.strip()))
    except ImportError as ie:
        logger.warning("[OCR] Potrebni paketi nisu instalirani (%s) — skenirani PDF ne može biti obrađen", ie)
    except Exception as e:
        logger.error("[OCR] Neočekivana greška: %s", e)

    return "", True, False


def extract_docx(path: Path) -> tuple[str, bool, bool]:
    import docx as _docx
    from docx.oxml.ns import qn as _qn
    from docx.table import Table as _Table

    # SEC-007 — inspect the zip central directory BEFORE letting python-docx
    # actually decompress anything; raises DocumentSafetyLimitExceeded and
    # aborts here if the file would blow past the safety thresholds.
    _check_docx_zip_safety(path)

    doc = _docx.Document(str(path))
    parts: list[str] = []

    for block in doc.element.body:
        tag = block.tag
        if tag == _qn("w:p"):
            text = "".join(
                node.text for node in block.iter(_qn("w:t")) if node.text
            )
            if text.strip():
                parts.append(text)
        elif tag == _qn("w:tbl"):
            table = _Table(block, doc)
            for row in table.rows:
                row_text = "\t".join(cell.text for cell in row.cells)
                if row_text.strip():
                    parts.append(row_text)

    return "\n".join(parts), False, False


def extract_txt(path: Path) -> tuple[str, bool, bool]:
    text = path.read_text(encoding="utf-8")
    return text, False, False


def extract(path: Path) -> tuple[str, bool, bool]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".txt":
        return extract_txt(path)
    raise ValueError(f"Unsupported file format: {suffix!r}")
