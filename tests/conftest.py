# -*- coding: utf-8 -*-
"""
Shared pytest configuration.

Sets FIELD_ENCRYPTION_KEY before any module is imported so that
validate_field_encryption_key() (called at api.py import time) does not
call sys.exit(1) and kill the pytest collection process.

setdefault: does NOT overwrite the key if it is already present in the
environment (e.g. on Render or when a developer has it in .env).
"""
import base64
import os
import secrets

# Load .env so that FOUNDER_EMAILS and other vars are available when
# shared/deps.py is imported directly (e.g. by routers.web3 tests).
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
except ImportError:
    pass

os.environ.setdefault(
    "FIELD_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)
