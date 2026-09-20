# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 4 Preflight B -- email reminder cron auth + failure
visibility.

PROVEN PRODUCTION DEFECT (2026-09-20): `.github/workflows/email-cron.yml`
sent `Authorization: Bearer ${{ secrets.CRON_TOKEN }}`, but
routers/email_notif.py::_require_cron_or_founder() only ever authorizes
(1) an `X-Cron-Key` header equal to production's CRON_SECRET, or (2) a
currently-valid FOUNDER Bearer JWT -- never an arbitrary Bearer token.
Confirmed via the GitHub Actions public API: 93 consecutive scheduled runs
all showed "success", which proved nothing, because the workflow's bare
`curl` had no status check -- curl exits 0 on ANY completed HTTP response
(401/403/500 included), only failing on a genuine connection error.

This test does not connect to any network or database -- it proves, from
the workflow file's own text, that: the correct header name is sent, no
`Authorization: Bearer` is used for this call, and the job actually fails
(non-zero exit) on a non-2xx response instead of reporting green
regardless of outcome. Whether the `CRON_TOKEN` GitHub secret's VALUE
equals production's `CRON_SECRET` is not provable by this session (no read
access to either secret store) -- flagged separately for founder
verification.
"""
import os
import re

WORKFLOW_PATH = os.path.join(
    os.path.dirname(__file__), "..", ".github", "workflows", "email-cron.yml",
)


def _read_workflow() -> str:
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _yaml_code_only(src: str) -> str:
    """Strip `# ...` comment lines -- this file's own comments explain the
    incident and necessarily quote the old broken header, which must not
    produce a false positive for the checks below."""
    return "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))


def test_workflow_file_exists():
    assert os.path.exists(WORKFLOW_PATH)


def test_sends_x_cron_key_not_authorization_bearer():
    src = _yaml_code_only(_read_workflow())
    assert "X-Cron-Key:" in src, "workflow no longer sends the X-Cron-Key header the endpoint actually requires"
    assert "Authorization: Bearer" not in src, "workflow reintroduced Bearer auth -- _require_cron_or_founder() never accepts an arbitrary Bearer token, only a founder JWT or X-Cron-Key"


def test_secret_reference_unchanged():
    """The fix corrects the header name, not the secret identity -- still
    CRON_TOKEN (GitHub) that must match CRON_SECRET (production env)."""
    src = _read_workflow()
    assert "secrets.CRON_TOKEN" in src


def test_job_fails_on_non_2xx_response():
    """A silent-success failure mode (93/93 'success' proving nothing) is
    the actual defect class here, independent of the header fix -- must
    not regress even if the header is later correct but this check is
    removed."""
    src = _read_workflow()
    assert "http_code" in src
    assert re.search(r"exit\s+1", src), "no non-zero exit path found for a failed HTTP response"
    # Must actually gate the exit on a real status check, not exit 1
    # unconditionally (which would make every run fail) or leave it
    # unreachable.
    assert re.search(r"if\s*\[.*http_code", src)


def test_no_secret_value_printed():
    """Scope/safety guard: the fix must not print the token itself, only
    the HTTP outcome."""
    src = _read_workflow()
    # The only permitted appearance of the secret is its reference, never
    # echoed/printed as a bare value.
    for line in src.splitlines():
        if "echo" in line or "::error::" in line:
            assert "CRON_TOKEN" not in line
            assert "secrets." not in line
