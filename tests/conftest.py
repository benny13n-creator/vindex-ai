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

os.environ.setdefault(
    "FIELD_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)
