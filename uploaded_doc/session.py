from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


def generate_session_id() -> str:
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_expires(iso: str) -> datetime:
    # Accept both Z-suffix and +00:00
    iso_clean = iso.replace("Z", "+00:00")
    return datetime.fromisoformat(iso_clean)


def is_expired(expires_at_iso: str) -> bool:
    return parse_expires(expires_at_iso) <= datetime.now(tz=timezone.utc)


def ttl_seconds_remaining(expires_at_iso: str) -> int:
    delta = parse_expires(expires_at_iso) - datetime.now(tz=timezone.utc)
    return max(0, int(delta.total_seconds()))


def expires_at_iso(ttl_hours: int) -> str:
    dt = datetime.now(tz=timezone.utc) + timedelta(hours=ttl_hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_session(session_id: str, namespace_prefix: str = "tmp_") -> bool:
    """Return True if <prefix><session_id> namespace exists and has at least one valid vector.
    pred_* namespaces never expire; tmp_* namespaces check expires_at metadata."""
    import os
    try:
        from pinecone import Pinecone
        api_key = os.environ["PINECONE_API_KEY"]
        host = os.environ.get("PINECONE_HOST", "")
        pc = Pinecone(api_key=api_key)
        index = pc.Index(host=host) if host else pc.Index(pc.list_indexes()[0].name)

        namespace = f"{namespace_prefix}{session_id}"
        result = index.query(
            vector=[0.1] * 3072,
            top_k=1,
            namespace=namespace,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        if not matches:
            return False
        if namespace_prefix == "tmp_":
            expires_at = (matches[0].metadata or {}).get("expires_at", "")
            if expires_at and is_expired(expires_at):
                return False
        return True
    except Exception:
        return False
