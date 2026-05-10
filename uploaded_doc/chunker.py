from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import tiktoken

from .schema import ChunkingManifest, UploadedDocChunk

_ENC = tiktoken.get_encoding("cl100k_base")

ARTICLE_REGEX = re.compile(
    r"^\s*(Član|Člana|Članu|Članom|Tačka)\s+(\d+[a-zA-Z]?(\.\d+)?)\.?",
    re.MULTILINE | re.IGNORECASE,
)
ARTICLE_DENSITY_THRESHOLD = 3
TARGET_TOKENS = 600
OVERLAP_TOKENS = 100
MAX_CHUNK_TOKENS = 800


def _count(text: str) -> int:
    return len(_ENC.encode(text))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _percentile(values: list[int], p: int) -> int:
    if not values:
        return 0
    sorted_v = sorted(values)
    idx = max(0, int(len(sorted_v) * p / 100) - 1)
    return sorted_v[idx]


def _chunk_article_aware(text: str, matches: list[re.Match]) -> list[tuple[str, str]]:
    """Return list of (text, article_label)."""
    segments: list[tuple[str, str]] = []
    starts = [m.start() for m in matches]
    labels = [m.group(0).strip() for m in matches]

    # Preamble before first article
    if starts[0] > 0:
        preamble = text[: starts[0]].strip()
        if preamble:
            segments.append((preamble, ""))

    for i, (start, label) in enumerate(zip(starts, labels)):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        segment = text[start:end].strip()
        if segment:
            segments.append((segment, label))

    return segments


def _split_recursive(text: str, target: int, overlap: int) -> list[str]:
    """Split text into chunks of ~target tokens with overlap."""
    tokens = _ENC.encode(text)
    if len(tokens) <= target:
        return [text]

    chunks: list[str] = []
    pos = 0
    while pos < len(tokens):
        end = min(pos + target, len(tokens))
        chunk_tokens = tokens[pos:end]
        chunk_text = _ENC.decode(chunk_tokens)

        # Try to break at paragraph, then newline, then sentence boundary
        if end < len(tokens):
            decoded_full = _ENC.decode(tokens[pos : end + 50])
            for sep in ("\n\n", "\n", ". "):
                idx = decoded_full.rfind(sep, 0, len(chunk_text))
                if idx > len(chunk_text) // 2:
                    chunk_text = decoded_full[:idx + len(sep)].strip()
                    break

        chunks.append(chunk_text)
        # Advance by (target - overlap), re-encode to find token position
        advance_tokens = max(1, target - overlap)
        pos += advance_tokens

    return chunks


def _chunk_recursive(text: str) -> list[tuple[str, str]]:
    """Return list of (text, label='')."""
    parts = _split_recursive(text, TARGET_TOKENS, OVERLAP_TOKENS)
    return [(p, "") for p in parts if p.strip()]


def _enforce_max_tokens(
    segments: list[tuple[str, str]],
) -> tuple[list[tuple[str, str, str]], bool]:
    """
    Enforce MAX_CHUNK_TOKENS. Returns (segments_with_mode, had_oversized).
    Each item is (text, article_label, chunk_mode).
    """
    result: list[tuple[str, str, str]] = []
    had_oversized = False
    for text, label in segments:
        mode = "article_aware" if label else "recursive"
        if _count(text) > MAX_CHUNK_TOKENS:
            had_oversized = True
            sub_parts = _split_recursive(text, TARGET_TOKENS, OVERLAP_TOKENS)
            for sub in sub_parts:
                if sub.strip():
                    result.append((sub, label, mode))
        else:
            result.append((text, label, mode))
    return result, had_oversized


def chunk_document(
    text: str,
    source_meta: dict,
) -> ChunkingManifest:
    source_filename = source_meta["source_filename"]
    source_format = source_meta["source_format"]
    source_sha256 = source_meta["source_sha256"]
    is_scanned = source_meta.get("is_scanned", False)
    session_id = source_meta.get("session_id", "__local__")

    matches = list(ARTICLE_REGEX.finditer(text))
    if len(matches) >= ARTICLE_DENSITY_THRESHOLD:
        raw_segments = _chunk_article_aware(text, matches)
        base_mode: Literal["article_aware", "recursive"] = "article_aware"
    else:
        raw_segments = _chunk_recursive(text)
        base_mode = "recursive"

    final_segments, had_oversized = _enforce_max_tokens(raw_segments)
    if had_oversized:
        chunk_mode_used: Literal["article_aware", "recursive", "mixed"] = "mixed"
    else:
        chunk_mode_used = base_mode

    now = datetime.now(tz=timezone.utc)
    chunks: list[UploadedDocChunk] = []
    article_labels_seen: list[str] = []

    for idx, (chunk_text, article_label, chunk_mode) in enumerate(final_segments):
        if article_label and article_label not in article_labels_seen:
            article_labels_seen.append(article_label)
        tc = _count(chunk_text)
        chunks.append(
            UploadedDocChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=session_id,
                source_filename=source_filename,
                source_format=source_format,  # type: ignore[arg-type]
                source_sha256=source_sha256,
                chunk_index=idx,
                chunk_mode=chunk_mode,  # type: ignore[arg-type]
                article_label=article_label or None,
                text=chunk_text,
                token_count=tc,
                char_count=len(chunk_text),
                created_at=now,
            )
        )

    token_counts = [c.token_count for c in chunks]

    return ChunkingManifest(
        source_filename=source_filename,
        source_format=source_format,
        source_sha256=source_sha256,
        is_scanned=is_scanned,
        total_chunks=len(chunks),
        chunk_mode_used=chunk_mode_used,
        article_labels_detected=article_labels_seen,
        token_p10=_percentile(token_counts, 10),
        token_p50=_percentile(token_counts, 50),
        token_p90=_percentile(token_counts, 90),
        chunks=chunks,
    )
