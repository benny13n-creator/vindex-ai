from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    session_id: str
    chunk_count: int
    chunk_mode_used: str
    article_labels_detected: list[str]
    expires_at: str       # ISO UTC string
    ttl_seconds: int
    ocr_used: bool = False
    ocr_warning: str = ""


class CleanupResponse(BaseModel):
    namespaces_deleted: int
    chunks_deleted: int
    namespaces_inspected: int
