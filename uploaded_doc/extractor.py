from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _log_ocr_error(reason: str, filename: str) -> None:
    """CELINA 5 (2026-07-24): OCR greške su ranije postojale SAMO kao Python
    logger pozivi (nevidljivi bez pristupa server logovima) -- upisuje u
    security_events za admin telemetriju (GET /api/admin/security-overview).
    Sinhrono, best-effort — extract_pdf se već izvršava u asyncio.to_thread
    workeru pozivaoca, i greška ovde nikad ne sme prekinuti ekstrakciju."""
    try:
        from api import _get_supa
        _get_supa().table("security_events").insert({
            "event_type": "ocr_error",
            "details": {"reason": reason, "filename": filename[:200]},
        }).execute()
    except Exception as e:
        logger.debug("[OCR] security_events upis neuspešan (nije kritično): %s", e)

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

# ─── Mission 001 (Night Shift M-001, 2026-08-02) — image decompression-bomb
# guard, same reasoning as SEC-007's DOCX check: a small JPEG/PNG can declare
# pixel dimensions that decompress to gigabytes in memory. PIL exposes the
# declared size via .size BEFORE decoding pixel data, so this check runs
# before Image.load()/any OCR preprocessing touches the pixel buffer.
MAX_IMAGE_PIXELS = 40_000_000  # ~40MP — comfortably above any real phone/scanner photo (typical: 8-24MP)


def _ocr_image(img, ocr_lang: str) -> str:
    """Shared OCR call — used by both extract_pdf's scanned-page loop and
    extract_image, so the two never silently drift (same preprocessing, same
    language fallback, same timeout). Caller passes an already-opened PIL
    Image; this does not open/close files."""
    import pytesseract

    img = img.convert("L")
    from PIL import ImageEnhance, ImageFilter
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    try:
        return pytesseract.image_to_string(img, lang=ocr_lang, timeout=45).strip()
    except Exception:
        try:
            return pytesseract.image_to_string(img, lang="eng", timeout=30).strip()
        except Exception:
            return ""


def _detect_ocr_lang() -> str:
    """Same Cyrillic/Latin/English fallback logic extract_pdf already used —
    factored out so extract_image doesn't duplicate it."""
    import pytesseract

    try:
        available_langs = pytesseract.get_languages(config="")
    except Exception:
        available_langs = []

    if "srp" in available_langs and "srp_latn" in available_langs:
        return "srp+srp_latn+eng"
    elif "srp_latn" in available_langs:
        return "srp_latn+eng"
    elif "srp" in available_langs:
        return "srp+eng"
    return "eng"


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
        from PIL import Image

        ocr_lang = _detect_ocr_lang()
        logger.info("[OCR] Pokrenuti OCR za %s — jezik: %s", path.name, ocr_lang)

        doc = fitz.open(str(path))
        ocr_pages: list[str] = []
        for page_num, page in enumerate(doc):
            pixmap = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pixmap.tobytes("png")))
            page_text = _ocr_image(img, ocr_lang)
            if not page_text:
                logger.warning("[OCR] Stranica %d neuspešna", page_num + 1)
            ocr_pages.append(page_text)

        ocr_text = "\n\n".join(p for p in ocr_pages if p)
        if len(ocr_text.strip()) > 100:
            logger.info("[OCR] Uspešno — %d karaktera iz %d stranica", len(ocr_text), len(ocr_pages))
            return ocr_text, False, True
        else:
            logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(ocr_text.strip()))
            _log_ocr_error("insufficient_text", path.name)
    except ImportError as ie:
        logger.warning("[OCR] Potrebni paketi nisu instalirani (%s) — skenirani PDF ne može biti obrađen", ie)
        _log_ocr_error("missing_dependencies", path.name)
    except Exception as e:
        logger.error("[OCR] Neočekivana greška: %s", e)
        _log_ocr_error("unexpected_error", path.name)

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


# Suffixes extract_image() handles — a photographed/scanned document with no
# separate PDF wrapper (Mission 001 / Night Shift M-001, 2026-08-02: the
# single most-requested real intake case — a client photographs a served
# document and sends the photo directly).
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def extract_image(path: Path) -> tuple[str, bool, bool]:
    """Return (text, is_scanned, ocr_used) for a standalone photographed/
    scanned image — same return contract as extract_pdf, so callers (the
    intake worker, api.py's auto-analyze upload) don't need to special-case
    images. Every image goes through OCR (there is no "has a text layer"
    case the way a born-digital PDF has); is_scanned=True only means OCR
    itself failed to extract meaningful text, matching extract_pdf's own
    <100-chars-total threshold exactly, so downstream code (the intake
    worker's is_scanned branch, the review-queue routing) treats a failed
    image OCR identically to a failed PDF OCR."""
    from PIL import Image

    try:
        with Image.open(path) as probe:
            probe.verify()
        # verify() invalidates the image object for further use (Pillow's own
        # documented behavior) -- reopen for the actual pixel-dimension check
        # and OCR pass below.
        with Image.open(path) as img:
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise DocumentSafetyLimitExceeded(
                    f"image is {width}x{height} ({width * height} pixels, max {MAX_IMAGE_PIXELS})"
                )
    except DocumentSafetyLimitExceeded:
        raise
    except Exception as e:
        logger.warning("[OCR] Nevalidna slika %s: %s", path.name, e)
        _log_ocr_error("invalid_image", path.name)
        return "", True, False

    try:
        ocr_lang = _detect_ocr_lang()
        logger.info("[OCR] Pokrenuti OCR za %s — jezik: %s", path.name, ocr_lang)
        with Image.open(path) as img:
            text = _ocr_image(img, ocr_lang)
    except ImportError as ie:
        logger.warning("[OCR] Potrebni paketi nisu instalirani (%s) — slika ne može biti obrađena", ie)
        _log_ocr_error("missing_dependencies", path.name)
        return "", True, False
    except Exception as e:
        logger.error("[OCR] Neočekivana greška: %s", e)
        _log_ocr_error("unexpected_error", path.name)
        return "", True, False

    if len(text) > 100:
        logger.info("[OCR] Uspešno — %d karaktera", len(text))
        return text, False, True

    logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(text))
    _log_ocr_error("insufficient_text", path.name)
    return "", True, False


def extract(path: Path) -> tuple[str, bool, bool]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".txt":
        return extract_txt(path)
    if suffix in IMAGE_SUFFIXES:
        return extract_image(path)
    raise ValueError(f"Unsupported file format: {suffix!r}")
