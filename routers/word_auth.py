"""Word Add-in authentication and pane-scoped session lifecycle.

This module deliberately does not use the generic bearer verifier or any AI
provider. The opaque session table is provisioned by a separately reviewed
migration; database errors therefore fail closed until that migration exists.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import jwk as jose_jwk
from jose import jwt as jose_jwt

from shared.deps import SUPABASE_URL, _get_supa
from shared.rate import limiter

logger = logging.getLogger("vindex.word_auth")
router = APIRouter(prefix="/api/word", tags=["word-auth"])

_ALLOWED_JWT_ALGORITHMS = frozenset({"ES256", "RS256"})
_JWKS_TTL_SECONDS = 3600
_JWKS_LOCK = threading.Lock()
_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_WORD_AI_PATHS = frozenset({"/api/word/analyze", "/api/word/rewrite"})
_MAX_SOURCE_TOKEN_CHARS = 8192
_MAX_WORD_TOKEN_CHARS = 256
_WORD_SESSION_MAX_SECONDS = 3600


@dataclass(frozen=True)
class WordSession:
    session_id: str
    user_id: str
    token_hash: str
    expires_at: datetime


def _get_jwks_keys() -> list[dict[str, Any]]:
    """Fetch current Supabase signing keys with bounded timeout and no fallback."""
    now = time.monotonic()
    with _JWKS_LOCK:
        if (
            isinstance(_JWKS_CACHE.get("keys"), list)
            and now - float(_JWKS_CACHE.get("fetched_at", 0.0)) < _JWKS_TTL_SECONDS
        ):
            return _JWKS_CACHE["keys"]

        if not SUPABASE_URL:
            raise ValueError("signing_keys_unavailable")
        url = SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read(128 * 1024 + 1)
            if len(body) > 128 * 1024:
                raise ValueError("signing_keys_unavailable")
            payload = json.loads(body)
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list) or not keys:
            raise ValueError("signing_keys_unavailable")
        _JWKS_CACHE["keys"] = keys
        _JWKS_CACHE["fetched_at"] = now
        return keys


def _verify_source_jwt(token: str, provider_user_id: str, now: float | None = None) -> dict[str, Any]:
    """Verify signature, key ID, issuer, audience, subject, and expiry strictly."""
    if not isinstance(token, str) or not token or len(token) > _MAX_SOURCE_TOKEN_CHARS:
        raise ValueError("invalid_token")
    header = jose_jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    key_id = header.get("kid")
    if algorithm not in _ALLOWED_JWT_ALGORITHMS or not isinstance(key_id, str) or not key_id:
        raise ValueError("invalid_signing_header")

    matches = [
        key for key in _get_jwks_keys()
        if isinstance(key, dict)
        and key.get("kid") == key_id
        and key.get("alg", algorithm) == algorithm
        and key.get("use", "sig") == "sig"
        and (not key.get("key_ops") or "verify" in key.get("key_ops", []))
        and key.get("kty") == ("EC" if algorithm == "ES256" else "RSA")
    ]
    if len(matches) != 1:
        raise ValueError("signing_key_mismatch")
    key = jose_jwk.construct(matches[0])
    claims = jose_jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        options={"verify_aud": False, "verify_iss": False, "verify_exp": False},
    )

    expected_issuer = SUPABASE_URL.rstrip("/") + "/auth/v1"
    subject = claims.get("sub")
    audience = claims.get("aud")
    expiry = claims.get("exp")
    current_time = time.time() if now is None else now
    if claims.get("iss") != expected_issuer:
        raise ValueError("invalid_issuer")
    if audience != "authenticated" or claims.get("role") != "authenticated":
        raise ValueError("invalid_audience")
    if not isinstance(subject, str) or not subject or subject != provider_user_id:
        raise ValueError("invalid_subject")
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or expiry <= current_time:
        raise ValueError("invalid_expiry")
    return claims


def _word_server_client_key(request: Request) -> str:
    """Use the socket peer for pre-auth limits; never trust a caller-supplied XFF."""
    client = request.client
    return client.host if client and isinstance(client.host, str) and client.host else "unknown"

def _require_word_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    expected = str(request.base_url).rstrip("/")
    if not origin or origin != expected:
        raise HTTPException(status_code=403, detail="Word zahtev nije dozvoljen.")
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise HTTPException(status_code=403, detail="Word zahtev nije dozvoljen.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Word zahtev nije dozvoljen.")

def _bearer_from_request(request: Request, *, maximum: int) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, separator, value = header.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    token = value.strip()
    if not token or len(token) > maximum or any(ch.isspace() for ch in token):
        return None
    return token


async def _audit(action: str, *, user_id: str | None, session_id: str | None, reason: str, request: Request) -> None:
    try:
        from shared.audit_immutable import log_action

        await log_action(
            action,
            user_id=user_id,
            resource_type="word_session",
            resource_id=session_id,
            ip=request.client.host if request.client else None,
            metadata={"channel": "word", "reason": reason},
            correlation_id=request.headers.get("X-Correlation-ID"),
        )
    except Exception:
        # Audit logging is secret-free and best effort in the existing contract.
        logger.warning("[WORD_AUTH] audit_write_failed action=%s", action)


async def _record_and_rate_limit(request: Request, user_id: str, path: str) -> None:
    """Reuse the established account bucket and anomaly controls after identity validation."""
    try:
        import api as api_module

        client_ip = request.client.host if request.client else ""
        is_ai = path in _WORD_AI_PATHS
        api_module._anomaly_record(user_id, path, client_ip, is_ai)
        if not await api_module._check_user_rate_limit(user_id, path):
            raise HTTPException(status_code=429, detail="Previše zahteva. Pokušajte kasnije.")
        if is_ai:
            signal = await api_module._anomaly_check(user_id, client_ip or None)
            if signal.is_anomaly:
                raise HTTPException(
                    status_code=429,
                    detail="Neobičan obrazac aktivnosti. Pokušajte kasnije.",
                    headers={"X-RateLimit-Reason": "anomaly_detected"},
                )
    except HTTPException:
        raise
    except Exception:
        logger.warning("[WORD_AUTH] account_rate_guard_unavailable")
        raise HTTPException(status_code=503, detail="Word sesija trenutno nije dostupna.")


def _row_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


async def require_word_session(request: Request) -> WordSession:
    token = _bearer_from_request(request, maximum=_MAX_WORD_TOKEN_CHARS)
    if token is None:
        raise HTTPException(status_code=401, detail="Word sesija nije važeća.")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _load() -> Any:
        return (
            _get_supa()
            .table("word_sessions")
            .select("id,user_id,token_hash,expires_at,revoked_at")
            .eq("token_hash", token_hash)
            .maybe_single()
            .execute()
        )

    try:
        result = await asyncio.to_thread(_load)
    except Exception:
        logger.warning("[WORD_AUTH] session_lookup_failed")
        raise HTTPException(status_code=503, detail="Word sesija trenutno nije dostupna.")

    row = getattr(result, "data", None) if result is not None else None
    expiry = _row_expiry(row.get("expires_at")) if isinstance(row, dict) else None
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not isinstance(row.get("user_id"), str)
        or not hmac.compare_digest(str(row.get("token_hash", "")), token_hash)
        or row.get("revoked_at") is not None
        or expiry is None
        or expiry.timestamp() <= time.time()
    ):
        raise HTTPException(status_code=401, detail="Word sesija je istekla ili opozvana.")

    session = WordSession(
        session_id=row["id"],
        user_id=row["user_id"],
        token_hash=token_hash,
        expires_at=expiry,
    )
    request.state.user_id = session.user_id
    request.state.word_session = session
    await _record_and_rate_limit(request, session.user_id, request.url.path)
    return session


async def ensure_word_session_active(session: WordSession) -> None:
    """Recheck the same Word row before returning results from dispatched work."""
    def _load() -> Any:
        return (
            _get_supa()
            .table("word_sessions")
            .select("id,user_id,token_hash,expires_at,revoked_at")
            .eq("id", session.session_id)
            .eq("user_id", session.user_id)
            .eq("token_hash", session.token_hash)
            .maybe_single()
            .execute()
        )

    try:
        result = await asyncio.to_thread(_load)
    except Exception:
        logger.warning("[WORD_AUTH] result_session_recheck_failed")
        raise HTTPException(status_code=503, detail="Word sesija trenutno nije dostupna.")

    row = getattr(result, "data", None) if result is not None else None
    expiry = _row_expiry(row.get("expires_at")) if isinstance(row, dict) else None
    if (
        not isinstance(row, dict)
        or row.get("id") != session.session_id
        or row.get("user_id") != session.user_id
        or not hmac.compare_digest(str(row.get("token_hash", "")), session.token_hash)
        or row.get("revoked_at") is not None
        or expiry is None
        or expiry.timestamp() <= time.time()
    ):
        raise HTTPException(status_code=401, detail="Word sesija je istekla ili opozvana.")


async def _confirm_source_identity(token: str) -> tuple[str, dict[str, Any]]:
    """Require provider confirmation, then independently verify exact signed claims."""
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(lambda: _get_supa().auth.get_user(token)),
            timeout=8,
        )
    except Exception:
        raise ValueError("provider_unavailable")
    provider_user = getattr(response, "user", None) if response is not None else None
    provider_user_id = getattr(provider_user, "id", None)
    if not isinstance(provider_user_id, str) or not provider_user_id:
        raise ValueError("provider_rejected")
    claims = await asyncio.wait_for(
        asyncio.to_thread(_verify_source_jwt, token, provider_user_id),
        timeout=4,
    )
    return provider_user_id, claims


@router.post("/sessions")
@limiter.limit("5/minute", key_func=_word_server_client_key)
async def exchange_word_session(request: Request, response: Response):
    _require_word_origin(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    source_token = _bearer_from_request(request, maximum=_MAX_SOURCE_TOKEN_CHARS)
    if source_token is None:
        await _audit("login_failed", user_id=None, session_id=None, reason="missing_or_malformed", request=request)
        raise HTTPException(status_code=401, detail="Prijava nije uspela. Prijavite se ponovo.")

    try:
        user_id, claims = await _confirm_source_identity(source_token)
    except Exception:
        await _audit("login_failed", user_id=None, session_id=None, reason="identity_verification_failed", request=request)
        raise HTTPException(status_code=401, detail="Prijava nije uspela. Prijavite se ponovo.")

    await _record_and_rate_limit(request, user_id, request.url.path)
    now = time.time()
    source_expiry = claims["exp"]
    expires_at = datetime.fromtimestamp(min(float(source_expiry), now + _WORD_SESSION_MAX_SECONDS), timezone.utc)
    if expires_at.timestamp() <= now:
        await _audit("login_failed", user_id=user_id, session_id=None, reason="expired_source_session", request=request)
        raise HTTPException(status_code=401, detail="Prijava nije uspela. Prijavite se ponovo.")

    raw_session_token = secrets.token_urlsafe(32)
    session_id = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()
    row = {
        "id": session_id,
        "user_id": user_id,
        "token_hash": token_hash,
        "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    def _insert() -> None:
        _get_supa().table("word_sessions").insert(row).execute()

    try:
        await asyncio.to_thread(_insert)
    except Exception:
        logger.warning("[WORD_AUTH] session_issue_failed")
        await _audit("login_failed", user_id=user_id, session_id=None, reason="session_store_unavailable", request=request)
        raise HTTPException(status_code=503, detail="Word prijava trenutno nije dostupna.")

    await _audit("login_success", user_id=user_id, session_id=session_id, reason="session_issued", request=request)
    return {"session_token": raw_session_token, "expires_at": expires_at.isoformat()}


@router.delete("/sessions/current")
@limiter.limit("30/minute", key_func=_word_server_client_key)
async def revoke_current_word_session(
    request: Request,
    response: Response,
    session: WordSession = Depends(require_word_session),
):
    _require_word_origin(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    revoked_at = datetime.now(timezone.utc).isoformat()

    def _revoke() -> Any:
        return (
            _get_supa()
            .table("word_sessions")
            .update({"revoked_at": revoked_at})
            .eq("id", session.session_id)
            .eq("user_id", session.user_id)
            .eq("token_hash", session.token_hash)
            .is_("revoked_at", "null")
            .execute()
        )

    try:
        result = await asyncio.to_thread(_revoke)
    except Exception:
        logger.warning("[WORD_AUTH] session_revoke_failed")
        raise HTTPException(status_code=503, detail="Odjavljivanje sa servera nije potvrđeno.")

    changed = getattr(result, "data", None) if result is not None else None
    if not changed:
        raise HTTPException(status_code=503, detail="Odjavljivanje sa servera nije potvrđeno.")

    await _audit(
        "logout",
        user_id=session.user_id,
        session_id=session.session_id,
        reason="user_logout",
        request=request,
    )
    return {"revoked": True}
