# -*- coding: utf-8 -*-
"""
SEC-058 (Night Shift M-010, 2026-08-02): _verify_token logged the full
Supabase auth response -- including the user's email -- at INFO level on
every authenticated request, in two independent copies of the same function
(shared/deps.py and api.py). Removed; these tests confirm the PII no longer
appears in any log record for either copy.
"""
import sys, os
import logging
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _fake_get_user_resp(email="advokat@vindex.rs", uid="00000000-0000-0000-0000-000000000001"):
    user = MagicMock()
    user.id = uid
    user.email = email
    resp = MagicMock()
    resp.user = user
    # A realistic __str__/__repr__ so a str()-formatted log record would
    # actually contain the email if the old logging call were still present.
    resp.__str__ = lambda self: f"UserResponse(user=User(id='{uid}', email='{email}'))"
    return resp


def test_shared_deps_verify_token_does_not_log_email(caplog):
    from shared import deps

    mock_supa = MagicMock()
    mock_supa.auth.get_user.return_value = _fake_get_user_resp()

    with patch.object(deps, "_get_supa", return_value=mock_supa), \
         caplog.at_level(logging.DEBUG):
        result = deps._verify_token("fake-token")

    assert result["email"] == "advokat@vindex.rs"  # function still works correctly
    # Note: on the success path no log record is emitted at all any more (the
    # vulnerable line is gone, not replaced with a redacted one) -- so the
    # meaningful regression guard is the source-level check below, not this
    # loop alone (an empty caplog.records would make this loop vacuously
    # pass even if a future edit reintroduced the leak in a way caplog
    # didn't capture, e.g. print() instead of logger).
    for record in caplog.records:
        assert "advokat@vindex.rs" not in record.getMessage(), (
            "SEC-058 regression: the auth response (with email) must not appear in any log record"
        )


def test_api_verify_token_does_not_log_email(caplog):
    import api

    mock_supa = MagicMock()
    mock_supa.auth.get_user.return_value = _fake_get_user_resp()

    with patch.object(api, "_get_supa", return_value=mock_supa), \
         caplog.at_level(logging.DEBUG):
        result = api._verify_token("fake-token")

    assert result["email"] == "advokat@vindex.rs"
    for record in caplog.records:
        assert "advokat@vindex.rs" not in record.getMessage(), (
            "SEC-058 regression: the auth response (with email) must not appear in any log record"
        )


def _assert_no_logger_info_formats_raw_resp(src: str) -> None:
    """Real regression guard (the behavioral tests above are vacuous on the
    happy path, since no log call fires there at all any more): walk every
    `logger.info` line in _verify_token's source and reject any that pass
    the bare `resp` object (containing the user's email) as a format
    argument. Scoped to `logger.info` specifically -- that is what SEC-058
    named (a line hit on every single successful authentication, unlike the
    pre-existing `logger.warning(...resp)` fallback a few lines below, which
    only fires on the already-anomalous empty-user path and was
    deliberately left out of this fix's scope, not missed)."""
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped.startswith("logger.info"):
            continue
        assert ", resp)" not in stripped and ", resp,)" not in stripped, (
            f"a logger.info call still formats the raw auth response object (contains email): {stripped!r}"
        )


def test_shared_deps_verify_token_source_has_no_pii_log_call():
    import inspect
    from shared import deps
    _assert_no_logger_info_formats_raw_resp(inspect.getsource(deps._verify_token))


def test_api_verify_token_source_has_no_pii_log_call():
    import inspect
    import api
    _assert_no_logger_info_formats_raw_resp(inspect.getsource(api._verify_token))


def test_shared_deps_verify_token_empty_user_still_works(caplog):
    """The fallback path (resp.user falsy) is unchanged by this fix -- still
    logs a warning, just not the full response object's PII on the
    successful path above."""
    from shared import deps

    resp = MagicMock()
    resp.user = None
    mock_supa = MagicMock()
    mock_supa.auth.get_user.return_value = resp

    with patch.object(deps, "_get_supa", return_value=mock_supa):
        result = deps._verify_token("fake-token")

    assert result is None or result == {}
