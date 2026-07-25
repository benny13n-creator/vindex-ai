# -*- coding: utf-8 -*-
"""
Regression/verification tests — routers/apr.py (APR autofill integration).

Context — two rounds this session:

  Round 1 (inspection, 2026-07-25): found the old scraper target
  (www.apr.gov.rs/registers/business-entities/search.aspx) returns HTTP
  200 with APR's own branded "HTTP 404" error page as the body. The old
  code's only failure signal was status_code != 200, so this was
  invisible to the circuit breaker -- every lookup silently returned
  "not found."

  Round 2 (fix, this file): routers/apr.py now (a) detects error-page
  content explicitly via _looks_like_error_page() and treats it as a
  service failure, not "not found"; (b) targets the real API found
  behind APR's new "Objedinjena pretraga" React app
  (pretraga.apr.gov.rs/api/search/PrivrednaDrustva/PretragaNaziva),
  confirmed live to be reCAPTCHA-protected -- EVERY automated call is
  rejected with HTTP 400 {"error": "reCAPTCHA verification failed"}
  regardless of parameters, confirmed live and reproducibly during this
  session; (c) falls back to the old URL on network-level failures
  (timeout/connect/SSL) only, not on explicit rejections a different URL
  wouldn't fix; (d) extracts a new `zastupnik` field.

  IMPORTANT: the reCAPTCHA wall means this integration still cannot
  return real company data via scripted HTTP calls today -- that is a
  deliberate anti-automation measure on APR's side, not a bug in this
  codebase, and is not something this project will build a bypass for.
  What round 2 fixes is CORRECTNESS OF FAILURE REPORTING (a real outage
  is now detected as an outage, not disguised as "company not found") and
  parser completeness (zastupnik) -- not restoring live data extraction,
  which requires either official APR API access or a human solving a
  CAPTCHA, neither achievable from a backend service.

Tests are split into three groups: parsing/detection logic (mocked, always
run), circuit breaker + fallback behavior (mocked, always run), and a live
canary against the real endpoint (skipped by default, honest either way).
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request as StarletteRequest  # noqa: E402

import routers.apr as apr  # noqa: E402


def _req(path="/api/apr/lookup/17162543") -> StarletteRequest:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": path,
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


# ─── Realistic HTML fixture, matching the table-cell format _parse_apr targets ──

_FIXTURE_HTML_FOUND = """
<html><body>
<table>
<tr><td>Naziv</td><td>TELEKOM SRBIJA AKCIONARSKO DRUŠTVO, BEOGRAD</td></tr>
<tr><td>PIB</td><td>100002887</td></tr>
<tr><td>Adresa sedišta</td><td>Takovska 2, Beograd (Stari Grad)</td></tr>
<tr><td>Status</td><td>Aktivan</td></tr>
<tr><td>Zastupnik</td><td>Vladimir Lučić</td></tr>
</table>
</body></html>
"""

_FIXTURE_HTML_NOT_FOUND = "<html><body><p>Nema rezultata za dati upit.</p></body></html>"

# The ACTUAL live response captured during this inspection (2026-07-25):
# HTTP 200, but APR's own branded error page, not search results.
_FIXTURE_HTML_APR_BRANDED_404 = """
<html xmlns="http://www.w3.org/1999/xhtml" >
<head><title>APR error page</title></head>
<body><table id="error"><tr><td class="h1"><h1>HTTP 404</h1></td></tr></table></body>
</html>
"""

# The ACTUAL live response captured from the new API endpoint (2026-07-25):
# HTTP 400 JSON, reCAPTCHA rejection -- reproduced consistently, regardless
# of query parameters sent.
_FIXTURE_JSON_RECAPTCHA_REJECTED = '{"title": "400 Bad Request", "message": {"error": "reCAPTCHA verification failed"}}'


def _reset_circuit():
    apr._circuit["consecutive_failures"] = 0
    apr._circuit["open_until"] = None
    apr._circuit["last_success_at"] = None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Parsing logic (mocked HTTP layer)
# ═══════════════════════════════════════════════════════════════════════════

def test_parse_apr_extracts_naziv_pib_adresa_status():
    result = {"naziv": "", "adresa": "", "pib": "", "status": "", "zastupnik": ""}
    apr._parse_apr(_FIXTURE_HTML_FOUND, result)
    assert result["naziv"] == "TELEKOM SRBIJA AKCIONARSKO DRUŠTVO, BEOGRAD"
    assert result["pib"] == "100002887"
    assert "Takovska" in result["adresa"]
    assert result["status"] == "Aktivan"


def test_parse_apr_extracts_zastupnik():
    """Task 3: zastupnik (zakonski zastupnik/direktor) extraction, tested
    against the reconstructed table-cell fixture -- NOT verified against
    real current APR output, since live access is reCAPTCHA-blocked (see
    module docstring)."""
    result = {"naziv": "", "adresa": "", "pib": "", "status": "", "zastupnik": ""}
    apr._parse_apr(_FIXTURE_HTML_FOUND, result)
    assert result["zastupnik"] == "Vladimir Lučić"


def test_parse_apr_zastupnik_json_variant():
    result = {"naziv": "", "adresa": "", "pib": "", "status": "", "zastupnik": ""}
    apr._parse_apr('{"zastupnik": "Ana Jovanović"}', result)
    assert result["zastupnik"] == "Ana Jovanović"


def test_parse_apr_pib_must_be_exactly_nine_digits():
    result = {"naziv": "", "adresa": "", "pib": "", "status": "", "zastupnik": ""}
    apr._parse_apr("<td>PIB</td><td>12345</td>", result)  # too short
    assert result["pib"] == ""


def test_parse_apr_leaves_fields_empty_when_not_found():
    result = {"naziv": "", "adresa": "", "pib": "", "status": "", "zastupnik": ""}
    apr._parse_apr(_FIXTURE_HTML_NOT_FOUND, result)
    assert result["naziv"] == ""
    assert result["pib"] == ""
    assert result["zastupnik"] == ""


# ─── Task 1: content sanity check (_looks_like_error_page) ─────────────────

def test_looks_like_error_page_detects_apr_branded_404():
    assert apr._looks_like_error_page(_FIXTURE_HTML_APR_BRANDED_404) is True


def test_looks_like_error_page_detects_recaptcha_rejection():
    assert apr._looks_like_error_page(_FIXTURE_JSON_RECAPTCHA_REJECTED) is True


def test_looks_like_error_page_does_not_false_positive_on_real_content():
    assert apr._looks_like_error_page(_FIXTURE_HTML_FOUND) is False
    assert apr._looks_like_error_page(_FIXTURE_HTML_NOT_FOUND) is False


def test_looks_like_error_page_handles_empty_input():
    assert apr._looks_like_error_page("") is False
    assert apr._looks_like_error_page(None) is False


def test_apr_lookup_success_via_mocked_http(monkeypatch):
    _reset_circuit()

    class _FakeResp:
        status_code = 200
        text = _FIXTURE_HTML_FOUND

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert result["greska"] is None
    assert result["naziv"] == "TELEKOM SRBIJA AKCIONARSKO DRUŠTVO, BEOGRAD"
    assert result["pib"] == "100002887"
    assert result["source"] == "APR"


def test_apr_lookup_not_found_sets_greska_without_raising(monkeypatch):
    _reset_circuit()

    class _FakeResp:
        status_code = 200
        text = _FIXTURE_HTML_NOT_FOUND

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        result = asyncio.run(apr._apr_lookup("99999999"))

    assert result["greska"] is not None
    assert "nije pronadjena" in result["greska"]


def test_apr_lookup_error_page_now_recorded_as_service_failure(monkeypatch):
    """Task 1 fix verification: APR's branded error page (HTTP 200, but
    not real search results -- the exact failure mode confirmed live
    during the original inspection) must now be detected explicitly and
    counted as a SERVICE failure (circuit breaker increments), not
    silently treated as "company not found" the way the old code did."""
    _reset_circuit()

    class _FakeResp:
        status_code = 200
        text = _FIXTURE_HTML_APR_BRANDED_404

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert result["greska"] is not None
    assert apr._circuit["consecutive_failures"] == 1  # FIXED: now counted as a real failure


def test_apr_lookup_recaptcha_rejection_recorded_as_service_failure(monkeypatch):
    """Same fix, for the OTHER confirmed live failure mode: the new API's
    reCAPTCHA rejection (HTTP 400 JSON)."""
    _reset_circuit()

    class _FakeResp:
        status_code = 400
        text = _FIXTURE_JSON_RECAPTCHA_REJECTED

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert result["greska"] is not None
    assert apr._circuit["consecutive_failures"] == 1


# ─── Task 2: fallback on network-level failure only ─────────────────────────

def test_network_failure_on_primary_falls_back_to_secondary_url():
    _reset_circuit()
    calls = []

    class _FakeRespOk:
        status_code = 200
        text = _FIXTURE_HTML_FOUND

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            calls.append(url)
            if url == apr._APR_SEARCH_PRIMARY:
                raise __import__("httpx").TimeoutException("timed out")
            return _FakeRespOk()

    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert calls == [apr._APR_SEARCH_PRIMARY, apr._APR_SEARCH_FALLBACK]
    assert result["naziv"] == "TELEKOM SRBIJA AKCIONARSKO DRUŠTVO, BEOGRAD"
    assert result["lookup_method"] == "html_search_fallback"


def test_explicit_rejection_does_not_trigger_fallback():
    """A reCAPTCHA-style explicit rejection is not a network problem --
    trying a different URL wouldn't fix it, so no fallback attempt should
    be made (and none of the fallback's own error handling should fire)."""
    _reset_circuit()
    calls = []

    class _FakeRespRejected:
        status_code = 400
        text = _FIXTURE_JSON_RECAPTCHA_REJECTED

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            calls.append(url)
            return _FakeRespRejected()

    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert calls == [apr._APR_SEARCH_PRIMARY]  # fallback URL never attempted
    assert result["greska"] is not None


def test_both_primary_and_fallback_network_failure_is_handled_cleanly():
    _reset_circuit()

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            raise __import__("httpx").ConnectError("connection refused")

    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _FakeClient()):
        result = asyncio.run(apr._apr_lookup("17162543"))

    assert result["greska"] is not None
    assert apr._circuit["consecutive_failures"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. Circuit breaker
# ═══════════════════════════════════════════════════════════════════════════

def test_circuit_opens_after_threshold_consecutive_failures():
    _reset_circuit()
    for _ in range(apr._CIRCUIT_THRESHOLD):
        apr._circuit_record(service_ok=False)
    assert apr._circuit_open_remaining() is not None


def test_circuit_closes_on_success():
    _reset_circuit()
    for _ in range(apr._CIRCUIT_THRESHOLD):
        apr._circuit_record(service_ok=False)
    assert apr._circuit_open_remaining() is not None
    apr._circuit_record(service_ok=True)
    assert apr._circuit_open_remaining() is None


def test_open_circuit_short_circuits_without_http_call():
    _reset_circuit()
    for _ in range(apr._CIRCUIT_THRESHOLD):
        apr._circuit_record(service_ok=False)

    with patch("httpx.AsyncClient") as mock_client_cls:
        result = asyncio.run(apr._apr_lookup("17162543"))

    mock_client_cls.assert_not_called()
    assert result["lookup_method"] == "circuit_open"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Endpoint-level validation
# ═══════════════════════════════════════════════════════════════════════════

def test_endpoint_rejects_non_eight_digit_maticni_broj():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(apr.apr_lookup("123", _req(), user={"user_id": "u1", "email": "a@b.com"}))
    assert exc_info.value.status_code == 422


def test_endpoint_strips_whitespace_and_dashes_before_validating():
    _reset_circuit()
    with patch.object(apr, "_apr_lookup", new=AsyncMock(return_value={"naziv": "X", "greska": None})), \
         patch.object(apr, "_log_apr_lookup", new=AsyncMock()):
        result = asyncio.run(apr.apr_lookup("1716 - 2543", _req(), user={"user_id": "u1", "email": "a@b.com"}))
    assert result["naziv"] == "X"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Live canary — the real external endpoint (network-dependent, honest)
# ═══════════════════════════════════════════════════════════════════════════

def _live_apr_lookup_available() -> tuple[bool, str]:
    """Best-effort connectivity probe -- returns (reachable, detail).
    Never raises; a network-level failure here just means the canary test
    below gets skipped instead of falsely failing CI for infrastructure
    outside this codebase's control."""
    try:
        result = asyncio.run(apr._apr_lookup("17162543"))  # Telekom Srbija a.d. — stable, well-known MB
        return True, str(result)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@pytest.mark.skipif(os.getenv("SKIP_LIVE_APR_TEST", "1") == "1",
                     reason="Live external network call — set SKIP_LIVE_APR_TEST=0 to run against the real APR site.")
def test_live_apr_endpoint_canary():
    """Honest signal of the live integration's ACTUAL current state, run
    manually (SKIP_LIVE_APR_TEST=0) -- never asserts success it can't
    verify. Two possible honest outcomes as of 2026-07-25:

    (a) BEST CASE, not expected today: real data comes back (naziv/pib
        populated) -- would mean APR lifted the reCAPTCHA gate or this
        session's discovered API contract guess was close enough. If this
        ever happens, the assertions below pass normally.

    (b) EXPECTED today: the new API rejects with reCAPTCHA (confirmed
        live and reproducible during this session, regardless of query
        parameters) -- this is a deliberate anti-automation measure on
        APR's side that this project will not attempt to bypass. The fix
        in this round means that outcome is now CORRECTLY classified as a
        service failure (greska set, circuit breaker incremented) instead
        of the old, worse failure mode (silently masqueraded as "company
        not found"). This test accepts EITHER honest outcome -- it only
        fails if the result is ambiguous (neither real data nor a
        recorded failure), which would mean something regressed."""
    reachable, detail = _live_apr_lookup_available()
    assert reachable, f"Network/connection failure calling live APR endpoint: {detail}"

    _reset_circuit()
    result = asyncio.run(apr._apr_lookup("17162543"))  # Telekom Srbija a.d.

    got_real_data = bool(result["naziv"]) and bool(result["pib"])
    correctly_classified_failure = bool(result["greska"]) and apr._circuit["consecutive_failures"] >= 1

    assert got_real_data or correctly_classified_failure, (
        "Live APR lookup returned neither real data NOR a recorded service "
        f"failure -- ambiguous outcome, likely a regression. Raw result: {result}, "
        f"circuit: {apr._circuit}"
    )
    if not got_real_data:
        print(f"\n[INFO] Live APR call still blocked as expected (reCAPTCHA or similar): {result['greska']}")
