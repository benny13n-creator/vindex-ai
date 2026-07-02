# -*- coding: utf-8 -*-
"""
Audit logging middleware — beleži svaki API poziv sa user_id i resursom.
"""
import logging
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("vindex.audit")

_SKIP_PATHS = {"/healthz", "/metrics", "/favicon.ico", "/static"}
_AUDIT_PATHS = {"/api/predmeti", "/api/klijenti", "/api/billing", "/api/firm"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = round((time.monotonic() - start) * 1000)

        path = request.url.path
        if any(path.startswith(p) for p in _AUDIT_PATHS):
            uid  = getattr(request.state, "user_id", None)
            meth = request.method
            status = response.status_code
            ip   = request.client.host if request.client else "?"
            logger.info("[AUDIT] %s %s uid=%s status=%s ip=%s ms=%d",
                        meth, path, uid or "anon", status, ip, elapsed)

            if status >= 400:
                logger.warning("[AUDIT-ERR] %s %s uid=%s status=%s",
                               meth, path, uid or "anon", status)

        return response
