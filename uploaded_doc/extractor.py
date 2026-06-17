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
    is_scanned = avg_chars < 50 or total_chars < 100

    if not is_scanned:
        return "\n\n".join(pages), False, False

    # OCR fallback for scanned/unreadable PDFs
    try:
        import io
        import fitz  # pymupdf
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        doc = fitz.open(str(path))
        ocr_pages: list[str] = []
        for page in doc:
            pixmap = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pixmap.tobytes("png")))
            img = img.convert("L")
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            try:
                page_text = pytesseract.image_to_string(img, lang="srp_latn+eng", timeout=30)
            except Exception:
                page_text = pytesseract.image_to_string(img, lang="eng", timeout=30)
            ocr_pages.append(page_text.strip())

        ocr_text = "\n\n".join(ocr_pages)
        if len(ocr_text.strip()) > 100:
            return ocr_text, False, True
    except Exception:
        pass

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
