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

    return "\n".join(parts), False


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
