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


# Institutional Memory Architecture V2 (2026-07-26), STUB 4 — Explainable
# Retrieval / hijerarhija izvora. Prepended u kontekst (v.
# app/services/retrieve.py) kad god su prisutni kancelarija_{id}/user_{id}
# rezultati (KORISNIKOV DOKUMENT pasusi) pored zakona/prakse -- LLM mora
# eksplicitno znati da prethodno iskustvo kancelarije NIJE isti nivo dokaza
# kao zakon/sudska praksa, pogotovo za NOVI predmet.
ORIGIN_HIERARCHY_INSTRUCTIONS = (
    "HIJERARHIJA IZVORA (obavezno poštovati pri odgovaranju):\n"
    "  PRIMAT 1 — Zvaničan zakon/Ustav: jedini neoboriv izvor pravnog osnova.\n"
    "  PRIMAT 2 — Zvanična sudska praksa: jak, ali ne apsolutan autoritet — "
    "  citiraj kao presedan, ne kao zakonsku normu.\n"
    "  PRIMAT 3 — Prethodno iskustvo kancelarije (pasusi označeni "
    "'KORISNIKOV DOKUMENT'): koristi ISKLJUČIVO kao stilski/stručni "
    "  orijentir (kako je kancelarija ranije formulisala sličnu situaciju) — "
    "  NIKAD kao neoborivu činjenicu ili pravni osnov za NOVI predmet, čak "
    "  ni kada dolazi iz ranijeg predmeta iste kancelarije."
)
