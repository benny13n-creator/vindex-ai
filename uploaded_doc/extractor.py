from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pdf(path: Path) -> tuple[str, bool, bool]:
    """Return (text, is_scanned, ocr_used).

    is_scanned=True  → PDF had no readable text and OCR also failed.
    ocr_used=True    → text came from OCR (scanned PDF successfully processed).
    """
    import pypdf

    reader = pypdf.PdfReader(str(path))
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
