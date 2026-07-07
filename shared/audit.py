# -*- coding: utf-8 -*-
"""
Audit logging middleware — beleži svaki API poziv sa user_id i resursom.
Kritične akcije se takođe upisuju u Supabase audit_log tabelu.
"""
import asyncio
import logging
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("vindex.audit")

_SKIP_PATHS = {"/healthz", "/metrics", "/favicon.ico", "/static", "/api/security/csp-report"}
_AUDIT_PATHS = {"/api/predmeti", "/api/klijenti", "/api/billing", "/api/firm"}

# Akcije koje se upisuju i u Supabase (ne samo logger)
_DB_AUDIT_METHODS = {"DELETE", "PUT", "PATCH"}
_DB_AUDIT_PATHS   = {"/api/predmeti", "/api/klijenti", "/api/billing", "/api/gdpr"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = round((time.monotonic() - start) * 1000)

        path = request.url.path
        meth = request.method
        status = response.status_code

        # Skip non-audit paths
        if any(path.startswith(p) for p in _SKIP_PATHS):
            return response

        if any(path.startswith(p) for p in _AUDIT_PATHS):
            uid = getattr(request.state, "user_id", None)
            ip  = request.client.host if request.client else "?"

            logger.info("[AUDIT] %s %s uid=%s status=%s ip=%s ms=%d",
                        meth, path, uid or "anon", status, ip, elapsed)

            if status >= 400:
                logger.warning("[AUDIT-ERR] %s %s uid=%s status=%s",
                               meth, path, uid or "anon", status)

            # Upis u Supabase za destruktivne operacije (DELETE, PUT, PATCH)
            if meth in _DB_AUDIT_METHODS and uid and any(path.startswith(p) for p in _DB_AUDIT_PATHS):
                asyncio.create_task(_db_audit(uid, meth, path, status, ip))

        return response


async def _db_audit(user_id: str, method: str, path: str, status: int, ip: str) -> None:
    """Upisuje audit zapis u Supabase audit_log tabelu. Fire-and-forget."""
    try:
        import hashlib
        from api import _get_supa
        supa = _get_supa()

        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16] if ip and ip != "?" else None
        akcija = f"{method}:{path.split('/')[-1] or path}"[:50]

        await asyncio.to_thread(
            lambda: supa.table("audit_log").insert({
                "user_id":    user_id,
                "akcija":     akcija,
                "q_hash":     None,
                "ip_hash":    ip_hash,
            }).execute()
        )
    except Exception as e:
        logger.debug("[AUDIT] db upis greška (nije kritično): %s", e)
