"""Format uploaded-document passages for LLM context.

Each passage is labelled 'KORISNIKOV DOKUMENT' so the LLM can distinguish it
from zakon and sudska_praksa entries and the system prompt can instruct the
correct citation style.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DOC_LABEL = "KORISNIKOV DOKUMENT"


def format_doc_passage(match) -> str:
    """Format a single tmp_* namespace match for LLM context.

    Header: KORISNIKOV DOKUMENT [chunk_index, article_label, source_filename]
    Body: chunk text.
    """
    meta = match.metadata or {}
    chunk_index = meta.get("chunk_index", "?")
    article_label = meta.get("article_label", "")
    source_filename = meta.get("source_filename", "")

    header = f"{_DOC_LABEL} [{source_filename}"
    if article_label:
        header += f", {article_label}"
    header += f", chunk {chunk_index}]"

    text = (meta.get("text") or "").strip()
    body = f"{header}\n\n{text}"

    logger.debug(
        "[DOC_FMT] chunk_index=%s article=%s text_len=%d",
        chunk_index, article_label or "—", len(text),
    )
    return body


def format_doc_passages(passages: list[dict]) -> str:
    """Format a list of passage dicts (with 'formatted' key) for combined output."""
    parts = [p["formatted"] for p in passages if p.get("formatted")]
    return "\n\n---\n\n".join(parts)
