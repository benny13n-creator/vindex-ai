"""Fail-closed per-attempt authorization for Word provider HTTP requests.

The Word session table migration is intentionally separate. The database RPC
contract is implemented by that migration; until it exists, Word provider
requests are denied rather than dispatched without an atomic session claim.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("vindex.word_session_dispatch")


class WordSessionDispatchDenied(RuntimeError):
    """The live Word session could not authorize this one provider attempt."""


_CURRENT_SESSION: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "vindex_word_provider_session", default=None
)
_HOOK_INSTALLED = False


def claim_word_session_provider_attempt(session: Any) -> None:
    """Atomically claim exactly one provider attempt through the reviewed DB RPC.

    The RPC must update the live session row only when id, user, hash, revocation,
    and database-clock expiry predicates match, and commit before returning true.
    """
    try:
        from shared.deps import _get_supa

        result = _get_supa().rpc(
            "claim_word_session_provider_attempt",
            {
                "p_session_id": session.session_id,
                "p_user_id": session.user_id,
                "p_token_hash": session.token_hash,
            },
        ).execute()
    except Exception as exc:
        logger.warning("[WORD_DISPATCH] claim_unavailable error=%s", type(exc).__name__)
        raise WordSessionDispatchDenied("word_session_dispatch_unavailable") from None

    if getattr(result, "data", None) is not True:
        raise WordSessionDispatchDenied("word_session_revoked_or_expired")


def _claim_current_provider_attempt() -> None:
    session = _CURRENT_SESSION.get()
    if session is not None:
        claim_word_session_provider_attempt(session)


def install_word_session_dispatch_hook() -> bool:
    """Install an idempotent OpenAI SDK attempt hook, inert outside Word context.

    `SyncAPIClient._build_request` and its async sibling are called once per SDK
    HTTP attempt, including retries. In api.py, PR #66's budget counter is
    installed before routers import; this Word wrapper then claims the session
    before delegating to that counter and immediately before the SDK sends.
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return True
    try:
        from openai._base_client import AsyncAPIClient, SyncAPIClient

        for client_class in (SyncAPIClient, AsyncAPIClient):
            original = client_class._build_request
            if getattr(original, "_vindex_word_session_guard", False):
                continue

            def _guarded_build_request(self, options, *, retries_taken=0, _original=original):
                _claim_current_provider_attempt()
                return _original(self, options, retries_taken=retries_taken)

            _guarded_build_request._vindex_word_session_guard = True
            client_class._build_request = _guarded_build_request

        _HOOK_INSTALLED = True
    except Exception as exc:
        logger.error("[WORD_DISPATCH] hook_install_failed error=%s", type(exc).__name__)
        return False
    return True


def word_session_dispatch_hook_installed() -> bool:
    return _HOOK_INSTALLED


@contextmanager
def word_provider_session(session: Any) -> Iterator[None]:
    if not word_session_dispatch_hook_installed():
        raise WordSessionDispatchDenied("word_session_dispatch_hook_unavailable")
    for name in ("session_id", "user_id", "token_hash"):
        value = getattr(session, name, None)
        if not isinstance(value, str) or not value:
            raise WordSessionDispatchDenied("word_session_context_invalid")
    token = _CURRENT_SESSION.set(session)
    try:
        yield
    finally:
        _CURRENT_SESSION.reset(token)


def word_provider_dispatch_active() -> bool:
    return _CURRENT_SESSION.get() is not None


def word_session_dispatch_denial(error: BaseException) -> WordSessionDispatchDenied | None:
    """Find a fail-closed claim denial wrapped by an SDK connection exception."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, WordSessionDispatchDenied):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


install_word_session_dispatch_hook()
