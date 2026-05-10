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
