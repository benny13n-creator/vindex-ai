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


# ── Outbound network guard ──────────────────────────────────────────────────
# CI-RED-003 was a test that mocked the database but not the LLM client, so it
# issued a real, BILLED gpt-4o request on every run. It was green locally only
# because the developer's .env holds a live key, and it 401'd in CI. A sweep
# then found ten more tests with the identical shape, all in the RAG pipeline:
# Pinecone/embeddings/Cohere mocked, the OpenAI chat client not. They were
# invisible because those call sites fail soft -- the test passes, after a real
# network round-trip.
#
# Reviewing for this defect one test at a time does not hold. Deny it instead:
# the suite may talk to localhost (the real-PostgreSQL credit proofs need it)
# and nothing else. A test that reaches for the internet now fails loudly and
# names itself, instead of quietly spending money.
#
# Escape hatch: VINDEX_TEST_ALLOW_NETWORK=1 for a deliberate live-integration run.
import socket as _socket

#
# SCOPE: paid-inference hosts only, deliberately. A guard on ALL outbound
# traffic fails 123 tests -- almost all of them fail-soft DNS lookups against
# the fake Supabase host, which cost nothing, resolve instantly and are a
# tidiness problem, not a defect. Rewriting those tonight would be churn, and a
# guard that forces 123 rewrites gets switched off instead of obeyed. This one
# blocks exactly what costs money and makes results nondeterministic.
#
# HOOK POINT: getaddrinfo, not socket.connect. connect() is handed an already-
# resolved (ip, port) tuple, so a hostname test there matches nothing and the
# guard silently does nothing at all -- which is precisely how the first version
# of this block reported a fully green suite while the tests it was written to
# catch kept calling out. getaddrinfo still sees the hostname.
# The canary in tests/test_network_guard.py exists so that failure mode cannot
# happen quietly again.
if os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1":
    _BILLED_HOSTS = (
        "openai.com", "anthropic.com", "pinecone.io", "cohere.ai", "cohere.com",
        "voyageai.com", "googleapis.com", "azure.com",
    )
    _real_getaddrinfo = _socket.getaddrinfo

    class NetworkAccessBlocked(BaseException):
        """Deliberately a BaseException, not an Exception.

        Every offender found so far sits behind a fail-soft `except Exception`
        (and behind @llm_retry, which treats connection errors as retryable and
        backs off between attempts). An Exception here is swallowed: the test
        still passes, having burned three retry cycles reaching for the network
        -- which is exactly how these stayed invisible. As a BaseException it
        propagates through the fail-soft handlers and fails the test by name.
        """

    # Known offenders, recorded once so the guard can block everything else.
    # See tests/network_offenders_baseline.txt for why this exists and what it
    # costs. The list may shrink; anything not on it fails immediately.
    _BASELINE_PATH = os.path.join(os.path.dirname(__file__), "network_offenders_baseline.txt")
    try:
        with open(_BASELINE_PATH, encoding="utf-8") as _f:
            _ALLOWED_NODEIDS = {
                ln.strip() for ln in _f
                if ln.strip() and not ln.lstrip().startswith("#")
            }
    except OSError:
        _ALLOWED_NODEIDS = set()

    _CURRENT_NODEID = {"id": None}

    def pytest_runtest_setup(item):
        _CURRENT_NODEID["id"] = item.nodeid.replace("\\", "/")

    def _guarded_getaddrinfo(host, *a, **k):
        if isinstance(host, (bytes, bytearray)):
            host = host.decode("ascii", "ignore")
        if (
            isinstance(host, str)
            and any(host.endswith(h) for h in _BILLED_HOSTS)
            and _CURRENT_NODEID["id"] not in _ALLOWED_NODEIDS
        ):
            raise NetworkAccessBlocked(
                f"Test attempted a real call to the paid API at {host!r}. "
                "Mock the client instead — this is billed to the account whose key "
                "is in the environment, and makes the test nondeterministic. Set "
                "VINDEX_TEST_ALLOW_NETWORK=1 only for a deliberate live-integration run."
            )
        return _real_getaddrinfo(host, *a, **k)

    _socket.getaddrinfo = _guarded_getaddrinfo
