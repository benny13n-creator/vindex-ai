# -*- coding: utf-8 -*-
"""
Vindex AI — Case Law Chunker (Phase 1.1)

Converts VKS decision JSON (Phase 1.0 scraper output) into token-bounded chunks
with section-aware splitting.  Output is namespace-agnostic — Phase 1.2 ingest
assigns namespace ``sudska_praksa`` in Pinecone.

Public API:
    chunk_decision(decision_json)   -> chunked decision dict
    chunk_corpus(raw_dir, out_dir)  -> summary stats dict
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import tiktoken

_log = logging.getLogger(__name__)
_enc = tiktoken.get_encoding("cl100k_base")

CHUNKER_VERSION = "1.0"
TARGET_TOKENS = 600
OVERLAP_TOKENS = 50

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------
# Patterns listed in priority order; first match at each offset wins.
# VKS decisions use spaced-letter headings (e.g. "R E Š E NJ E").
_SECTION_MARKERS: list[tuple[re.Pattern, str]] = [
    # Spaced-letter resolutions (REŠENJE / PRESUDA) → IZREKA
    (re.compile(r"^R\s+E\s+Š\s+E\s+NJ\s+E\s*$", re.MULTILINE), "IZREKA"),
    (re.compile(r"^P\s+R\s+E\s+S\s+U\s+D\s+U\s*$", re.MULTILINE), "IZREKA"),
    # Spaced-letter reasoning block → OBRAZLOŽENJE
    (re.compile(r"^O\s+b\s+r\s+a\s+z\s+l\s+o\s+ž\s+e\s+nj\s+e\s*$", re.MULTILINE), "OBRAZLOŽENJE"),
    # Plain-text fallbacks (some decisions use non-spaced variants)
    (re.compile(r"^REŠENJE\s*$", re.MULTILINE), "IZREKA"),
    (re.compile(r"^PRESUDA\s*$", re.MULTILINE), "IZREKA"),
    (re.compile(r"^IZREKA\s*:?\s*$", re.MULTILINE), "IZREKA"),
    (re.compile(r"^OBRAZLOŽENJE\s*:?\s*$", re.MULTILINE), "OBRAZLOŽENJE"),
    (re.compile(r"^Iz\s+obrazloženja\s*:?\s*$", re.MULTILINE), "IZ_OBRAZLOZENJA"),
]

# ---------------------------------------------------------------------------
# Article extraction regexes (captures the number only; law context deferred)
# ---------------------------------------------------------------------------
# Covers all Serbian inflected forms of "član": član, člana, članu, čl. etc.
_ARTICLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bčlan\w*\s+(\d+[a-zšćčžđ]?)", re.IGNORECASE),
    re.compile(r"\bčl\.\s*(\d+[a-zšćčžđ]?)", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Split decision text at known section markers.

    Returns list of (section_name, section_text).
    Text before the first marker → 'HEADER'.
    If no markers found → single [('BODY', full_text)].
    """
    hits: list[tuple[int, str, int]] = []
    for pattern, name in _SECTION_MARKERS:
        for m in pattern.finditer(text):
            hits.append((m.start(), name, m.end() - m.start()))

    if not hits:
        return [("BODY", text.strip())]

    # Sort by position and deduplicate overlapping matches (keep first)
    hits.sort(key=lambda x: x[0])
    deduped: list[tuple[int, str, int]] = []
    last_end = -1
    for pos, name, length in hits:
        if pos >= last_end:
            deduped.append((pos, name, length))
            last_end = pos + length

    sections: list[tuple[str, str]] = []

    header_text = text[: deduped[0][0]].strip()
    if header_text:
        sections.append(("HEADER", header_text))

    for i, (pos, name, length) in enumerate(deduped):
        start = pos + length
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append((name, section_text))

    return sections if sections else [("BODY", text.strip())]


# ---------------------------------------------------------------------------
# Sentence-level splitting within a section
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """
    Split text into paragraph/sentence-level units for token budgeting.
    Primary split: newlines.  Secondary: '. ' within long paragraphs.
    """
    sentences: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if count_tokens(para) > 400:
            # Split long paragraph at sentence boundaries
            parts = re.split(r"(?<=\.) ", para)
            for part in parts:
                part = part.strip()
                if part:
                    sentences.append(part)
        else:
            sentences.append(para)
    return sentences


# ---------------------------------------------------------------------------
# Chunk a single section
# ---------------------------------------------------------------------------

def chunk_section(
    section_name: str,
    section_text: str,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """
    Split a section's text into token-bounded chunks with overlap.
    Chunks are sentence-aware; hard splits only as a last resort.
    """
    if not section_text.strip():
        return []

    if count_tokens(section_text) <= target_tokens:
        return [section_text]

    sentences = _split_sentences(section_text)
    if not sentences:
        sentences = [section_text]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_count = 0
    overlap_prefix = ""
    overlap_count = 0

    for sent in sentences:
        sent_count = count_tokens(sent)

        if current_count + sent_count > target_tokens and current_parts:
            chunk_text = " ".join(current_parts).strip()
            chunks.append(chunk_text)

            # Compute overlap tail from emitted chunk
            enc_ids = _enc.encode(chunk_text)
            if len(enc_ids) > overlap_tokens:
                overlap_prefix = _enc.decode(enc_ids[-overlap_tokens:])
                overlap_count = overlap_tokens
            else:
                overlap_prefix = chunk_text
                overlap_count = len(enc_ids)

            if overlap_prefix:
                current_parts = [overlap_prefix, sent]
                current_count = overlap_count + sent_count
            else:
                current_parts = [sent]
                current_count = sent_count
        else:
            current_parts.append(sent)
            current_count += sent_count

    if current_parts:
        chunk_text = " ".join(current_parts).strip()
        if chunk_text:
            chunks.append(chunk_text)

    # Hard-split any chunk that exceeds 800 tokens (failsafe for no-boundary text)
    final: list[str] = []
    for ch in chunks:
        if count_tokens(ch) > 800:
            enc_ids = _enc.encode(ch)
            pos = 0
            while pos < len(enc_ids):
                piece = _enc.decode(enc_ids[pos: pos + target_tokens]).strip()
                if piece:
                    final.append(piece)
                pos += target_tokens - overlap_tokens
        else:
            final.append(ch)

    return [c for c in final if c.strip()]


# ---------------------------------------------------------------------------
# Article extraction
# ---------------------------------------------------------------------------

def extract_cited_articles(text: str) -> list[str]:
    """
    Extract article numbers mentioned in the decision text.
    Returns a deduplicated, sorted list of raw article number strings
    (e.g. ["200", "203", "485"]).

    Law context is NOT inferred here — normalization (e.g. "KZ/203") is
    deferred to Phase 1.3 where retrieval context is available.
    """
    found: set[str] = set()
    for pat in _ARTICLE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(1).lower())

    def _sort_key(s: str) -> tuple[int, str]:
        digits = re.sub(r"[^0-9]", "", s)
        return (int(digits) if digits else 0, s)

    return sorted(found, key=_sort_key)


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def chunk_decision(decision_json: dict) -> dict:
    """
    Convert a Phase 1.0 decision JSON into a chunked decision dict.

    Input:  decision JSON with keys: decision_id, decision_number, matter,
            court, decision_date, registrant, source_url, raw_text.
    Output: chunked decision dict (schema defined in Phase 1.1 spec B.4).
    """
    decision_id: str = decision_json["decision_id"]
    decision_number: str = decision_json.get("decision_number", "")
    matter: str = decision_json["matter"]
    court: str = decision_json["court"]
    decision_date: str = decision_json.get("decision_date", "")
    registrant: str = decision_json.get("registrant", "")
    source_url: str = decision_json.get("source_url", "")
    raw_text: str = decision_json.get("raw_text", "")

    # For the 3 partials in zastitaprava where decision_number is empty
    decision_id_fallback: str | None = decision_id if not decision_number else None

    raw_token_count = count_tokens(raw_text)
    cited = extract_cited_articles(raw_text)
    sections = split_into_sections(raw_text)

    flat_chunks: list[tuple[str, str]] = []
    for section_name, section_text in sections:
        for text_piece in chunk_section(section_name, section_text):
            flat_chunks.append((section_name, text_piece))

    chunk_total = len(flat_chunks)
    now = datetime.now(timezone.utc).isoformat()

    chunks_out: list[dict] = []
    for idx, (section_name, text_piece) in enumerate(flat_chunks):
        chunks_out.append({
            "chunk_id": f"{decision_id}__chunk_{idx}",
            "section": section_name,
            "chunk_index": idx,
            "chunk_total": chunk_total,
            "text": text_piece,
            "token_count": count_tokens(text_piece),
            "metadata": {
                "doc_type": "sudska_praksa",
                "court": court,
                "decision_number": decision_number,
                "decision_id_fallback": decision_id_fallback,
                "decision_date": decision_date,
                "matter": matter,
                "registrant": registrant,
                "source_url": source_url,
                "section": section_name,
                "chunk_index": idx,
                "chunk_total": chunk_total,
                "cited_articles_raw": cited,
                # Law context not available at chunk time; deferred to Phase 1.3
                "cited_articles_normalized": [],
            },
        })

    return {
        "decision_id": decision_id,
        "decision_number": decision_number,
        "matter": matter,
        "court": court,
        "decision_date": decision_date,
        "registrant": registrant,
        "source_url": source_url,
        "chunked_at": now,
        "chunker_version": CHUNKER_VERSION,
        "chunk_count": chunk_total,
        "raw_text_length": len(raw_text),
        "raw_token_count": raw_token_count,
        "chunks": chunks_out,
    }


def chunk_corpus(raw_dir: Path, output_dir: Path) -> dict:
    """
    Process all decisions in raw_dir/<matter_slug>/*.json.
    Write chunked output to output_dir/<matter_slug>/<decision_id>.json.
    Returns summary stats dict.
    """
    matter_slugs = ["krivicna", "gradjanska", "upravna", "zastitaprava"]
    error_log = output_dir.parent / "chunked_errors.txt"
    error_log.unlink(missing_ok=True)

    total_decisions = 0
    total_chunks = 0
    total_errors = 0
    by_matter: dict[str, dict] = {}

    for slug in matter_slugs:
        src_dir = raw_dir / slug
        dst_dir = output_dir / slug
        dst_dir.mkdir(parents=True, exist_ok=True)

        decision_files = sorted(src_dir.glob("*.json"))
        matter_decisions = 0
        matter_chunks = 0
        chunk_counts: list[int] = []

        for df in decision_files:
            try:
                decision_json = json.loads(df.read_text(encoding="utf-8"))
                result = chunk_decision(decision_json)
                (dst_dir / df.name).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                n = result["chunk_count"]
                matter_decisions += 1
                matter_chunks += n
                chunk_counts.append(n)
                _log.info("[%s] %s → %d chunks", slug, result["decision_id"], n)
            except Exception as exc:
                total_errors += 1
                _log.error("[%s] ERROR %s: %s", slug, df.stem, exc)
                with error_log.open("a", encoding="utf-8") as ef:
                    ef.write(f"{slug}/{df.stem}: {exc}\n")

        avg = matter_chunks / matter_decisions if matter_decisions else 0.0
        by_matter[slug] = {
            "decisions": matter_decisions,
            "chunks": matter_chunks,
            "avg": round(avg, 2),
            "min": min(chunk_counts) if chunk_counts else 0,
            "max": max(chunk_counts) if chunk_counts else 0,
        }
        total_decisions += matter_decisions
        total_chunks += matter_chunks

    return {
        "total_decisions": total_decisions,
        "total_chunks": total_chunks,
        "errors": total_errors,
        "by_matter": by_matter,
    }
