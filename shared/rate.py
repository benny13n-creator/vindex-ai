# -*- coding: utf-8 -*-
"""
Shared SlowAPI rate limiter — singleton importovan od api.py i svih router modula.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/hour"])
