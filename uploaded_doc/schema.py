from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class UploadedDocChunk(BaseModel):
    chunk_id: str
    session_id: str
    source_filename: str
    source_format: Literal["pdf", "docx", "txt"]
    source_sha256: str
    chunk_index: int
    chunk_mode: Literal["article_aware", "recursive"]
    article_label: Optional[str]
    text: str
    token_count: int
    char_count: int
    created_at: datetime


class ChunkingManifest(BaseModel):
    source_filename: str
    source_format: str
    source_sha256: str
    is_scanned: bool
    total_chunks: int
    chunk_mode_used: Literal["article_aware", "recursive", "mixed"]
    article_labels_detected: list[str]
    token_p10: int
    token_p50: int
    token_p90: int
    chunks: list[UploadedDocChunk]
