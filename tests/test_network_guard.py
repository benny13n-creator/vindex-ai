# -*- coding: utf-8 -*-
"""
Canary for the paid-API network guard in tests/conftest.py.

The guard's first version hooked socket.connect and matched on hostname. But
connect() receives an already-resolved (ip, port) tuple, so the hostname test
matched nothing and the guard did precisely nothing -- while reporting a fully
green suite, including the very tests it was written to catch. A guard that
cannot be observed failing is indistinguishable from no guard at all.

These tests observe it.
"""
import os
import socket

import pytest

_ENABLED = os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1"


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
def test_guard_blocks_a_paid_api_host():
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo("api.openai.com", 443)
    assert type(exc.value).__name__ == "NetworkAccessBlocked", (
        f"the guard did not fire — got {type(exc.value).__name__}"
    )


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
def test_guard_is_not_an_ordinary_exception():
    """Every offender found sits behind a fail-soft `except Exception` and
    behind @llm_retry. An Exception here is swallowed and the test still
    passes, having merely wasted three retry cycles reaching for the network.
    The guard must be a BaseException or it does not surface anything."""
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo("api.openai.com", 443)
    assert not isinstance(exc.value, Exception), (
        "an Exception is swallowed by the fail-soft handlers this guard exists to defeat"
    )


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
@pytest.mark.parametrize("host", ["api.pinecone.io", "api.anthropic.com", "api.cohere.ai"])
def test_guard_covers_the_other_billed_providers(host):
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(host, 443)
    assert type(exc.value).__name__ == "NetworkAccessBlocked"


def test_guard_leaves_localhost_alone():
    """The real-PostgreSQL credit proofs connect to 127.0.0.1 and must not be
    caught in the blast radius."""
    assert socket.getaddrinfo("127.0.0.1", 5432)


def test_guard_leaves_unrelated_hosts_alone():
    """Scoped to paid inference APIs on purpose — see the conftest comment.
    A guard that fails 123 tests gets switched off instead of obeyed."""
    try:
        socket.getaddrinfo("fake.supabase.co", 443)
    except BaseException as exc:  # DNS failure is fine; being BLOCKED is not
        assert type(exc).__name__ != "NetworkAccessBlocked", (
            "the guard must not extend to non-billed hosts"
        )
