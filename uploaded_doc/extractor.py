from __future__ import annotations

from pathlib import Path


def extract_pdf(path: Path) -> tuple[str, bool]:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    pages: list[str] = []
    total_chars = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
        total_chars += len(text)

    avg_chars = total_chars / max(len(reader.pages), 1)
    is_scanned = avg_chars < 50

    return "\n\n".join(pages), is_scanned


def extract_docx(path: Path) -> tuple[str, bool]:
    import docx as _docx

    doc = _docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs]
    return "\n".join(paragraphs), False


def extract_txt(path: Path) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8")
    return text, False


def extract(path: Path) -> tuple[str, bool]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".txt":
        return extract_txt(path)
    raise ValueError(f"Unsupported file format: {suffix!r}")
