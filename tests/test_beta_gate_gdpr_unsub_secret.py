# -*- coding: utf-8 -*-
"""
Final Beta Gate — F14 (LOW): routers/gdpr.py's unsubscribe HMAC secret used
to fall back to a literal, source-visible string ("vindex-unsub-key") when
both UNSUBSCRIBE_SECRET and SUPABASE_JWT_SECRET were unset. Now generates a
random per-process secret instead and logs CRITICAL, so a misconfigured
deployment is loud, not silently using a fixed fallback anyone reading the
repo could forge tokens against.

Deliberately does NOT reload routers.gdpr (importlib.reload) to get at the
fallback logic -- an earlier version of this test did, and reloading the
module re-runs every @limiter.limit(...) decorator in it, which re-registers
rate-limit rules against slowapi's shared, process-global state and was
observed to make tests/test_gdpr_delete.py's own rate-limited DELETE
/api/gdpr/account tests spuriously 429 later in the same test session. The
resolution logic is factored into routers.gdpr._resolve_unsub_secret(), a
pure function callable directly with monkeypatched env vars.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_module_source_no_longer_uses_hardcoded_fallback_string_as_code():
    """The literal may still appear in an explanatory comment (this fix's own
    docstring references it) -- what must be gone is its use AS A VALUE."""
    import routers.gdpr as gdpr_mod
    src_path = gdpr_mod.__file__
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert 'os.getenv("SUPABASE_JWT_SECRET", "vindex-unsub-key")' not in src
    assert 'getenv("SUPABASE_JWT_SECRET", "vindex-unsub-key")' not in src


def test_secret_falls_back_to_random_bytes_when_both_env_vars_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    from routers.gdpr import _resolve_unsub_secret
    secret = _resolve_unsub_secret()

    assert isinstance(secret, bytes)
    assert len(secret) == 32
    assert secret != b"vindex-unsub-key"


def test_secret_is_different_each_time_env_vars_are_unset(monkeypatch):
    """Proves it's genuinely random, not a disguised fixed fallback."""
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    from routers.gdpr import _resolve_unsub_secret
    assert _resolve_unsub_secret() != _resolve_unsub_secret()


def test_secret_uses_unsubscribe_secret_env_var_when_present(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "a-real-secret-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "should-not-be-used")

    from routers.gdpr import _resolve_unsub_secret
    assert _resolve_unsub_secret() == b"a-real-secret-value"


def test_secret_falls_back_to_jwt_secret_when_unsub_secret_absent(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "the-jwt-secret")

    from routers.gdpr import _resolve_unsub_secret
    assert _resolve_unsub_secret() == b"the-jwt-secret"
