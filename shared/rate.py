# -*- coding: utf-8 -*-
"""
Shared SlowAPI rate limiter — singleton importovan od api.py i svih router modula.
"""
from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """Čita pravi IP klijenta iza Render/Cloudflare proxy-ja.
    X-Forwarded-For: <client>, <proxy1>, <proxy2>
    Uzimamo samo prvu vrednost (leftmost = klijent).
    Fallback: request.client.host (direktna konekcija).
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip, default_limits=["60/hour"])
