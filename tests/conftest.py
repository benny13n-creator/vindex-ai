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

# CI-RED-001 (2026-08-08): the .env load above is best-effort — in CI there IS
# no .env file, and .github/workflows/tests.yml never supplied FOUNDER_EMAILS.
# shared/deps.py raises RuntimeError at IMPORT time when it is missing, so
# every test that imports it errored during collection and the "Test Suite"
# workflow had been failing on EVERY commit for the entire visible history
# (25+ runs). A permanently-red pipeline is a pipeline nobody reads — which is
# how the PROD-SYNTAX-001 outage shipped past it.
#
# setdefault, so a real value from .env or from the CI environment always wins;
# this only guarantees the suite is self-sufficient wherever it runs.
#
# The VALUE matters, not just its presence: 13 tests across
# test_business_groups / test_tier_config / test_feature_type /
# test_product_intelligence / test_ztc_conflict_check_autowiring assert
# founder-only behaviour using hard-coded addresses, and until now they were
# silently passing on whatever happened to be in the developer's own .env.
# Pinning the value here makes the suite deterministic and identical in CI,
# in a fresh clone, and on a laptop.
#
# (Follow-up worth doing separately: have those tests patch FOUNDER_EMAILS or
# _is_founder themselves instead of depending on ambient configuration. That
# is a 13-file change and is deliberately not bundled into a CI fix.)
os.environ.setdefault("FOUNDER_EMAILS", "benny13.n@gmail.com,founder@test.rs")
