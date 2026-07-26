"""Format uploaded-document passages for LLM context.

Each passage is labelled 'KORISNIKOV DOKUMENT' so the LLM can distinguish it
from zakon and sudska_praksa entries and the system prompt can instruct the
correct citation style.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DOC_LABEL = "KORISNIKOV DOKUMENT"
_DOC_LABEL_SAME_CASE = "KORISNIKOV DOKUMENT (OVAJ PREDMET)"
_DOC_LABEL_OTHER_CASE = "KORISNIKOV DOKUMENT (RANIJI PREDMET IZ KANCELARIJE)"


def format_doc_passage(match, same_case: Optional[bool] = None) -> str:
    """Format a single Pinecone match for LLM context.

    Header: <LABEL> [chunk_index, article_label, source_filename]
    Body: chunk text.

    same_case (Institutional Learning & RAG Audit, 2026-07-26 #2/#3):
      - None  (default, ad-hoc tmp_* document analysis) -> generic label,
        identical to prior behavior.
      - True  -> passage je iz TRENUTNOG predmeta.
      - False -> passage je iz DRUGOG predmeta iste kancelarije/korisnika --
        LLM mora znati da ovo NIJE trenutni predmet pre nego što citira
        činjenice iz njega.
    """
    meta = match.metadata or {}
    chunk_index = meta.get("chunk_index", "?")
    article_label = meta.get("article_label", "")
    source_filename = meta.get("source_filename", "")

    if same_case is True:
        label = _DOC_LABEL_SAME_CASE
    elif same_case is False:
        label = _DOC_LABEL_OTHER_CASE
    else:
        label = _DOC_LABEL

    header = f"{label} [{source_filename}"
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
