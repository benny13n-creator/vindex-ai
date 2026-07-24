# -*- coding: utf-8 -*-
"""
SEC-005 — Rate limiting verification sprint 2 (2026-07-24).

Kontekst (vidi docs/security/SEC005_RATE_LIMITING_REPORT.md za punu analizu):
prethodna SEC-005 faza (2026-07-23) rešila je Redis fail-open ponašanje,
ali ostavila 2 nezavisna, konkretna baga otkrivena tek kasnijom analizom:

  Nalaz A: api.py's slowapi Limiter je koristio `get_remote_address`
  (čita samo `request.client.host`) umesto `shared.rate._get_real_ip`
  (čita X-Forwarded-For) — iza Render-ovog edge proxy-ja (gunicorn+
  UvicornWorker, bez forwarded_allow_ips/ProxyHeadersMiddleware), to je
  značilo da IP-based limiting verovatno broji proxy-jev IP, ne klijentov.

  Nalaz B: `user_rate_limit_middleware` je čitao `request.state.user_id`,
  koji NIGDE u kodu nije bio postavljan (get_current_user ga vraća FastAPI
  ruti kao Depends rezultat, nikad ne piše u request.state, a i da piše —
  to bi se desilo unutar call_next(), POSLE ove provere). Ceo per-user
  rate limit + anomaly detection sloj se otkad je napisan nikad nije
  izvršio ni na jednom pravom zahtevu.

Ovaj fajl testira POPRAVKE oba nalaza + pokrivenost novododanih AI ruta,
odvojeno od tests/test_sec005_failopen_limiter.py (koji ostaje fokusiran
isključivo na Redis fail-open ponašanje).
"""
import os
import re
import time

import pytest
from jose import jwt as jose_jwt
from starlette.requests import Request

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "founder@example.com")

from shared.rate import _get_real_ip  # noqa: E402
import shared.deps as _deps  # noqa: E402


def _make_request(client_ip: str | None, path: str = "/x", forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "client": (client_ip, 12345) if client_ip else None,
        "query_string": b"",
    }
    return Request(scope)


def _make_jwt(sub: str, secret: str | None = None) -> str:
    """Potpisuje test JWT ISTIM ključem koji `shared.deps.SUPABASE_JWT_SECRET`
    stvarno koristi u ovom procesu -- `tests/conftest.py` učitava `.env` sa
    `override=False` PRE ovog fajla, pa ako `.env` već ima svoj
    SUPABASE_JWT_SECRET, naš `os.environ.setdefault(...)` ne pobeđuje i
    modul na kraju koristi vrednost iz `.env`, ne ovde hardkodovanu."""
    return jose_jwt.encode(
        {"sub": sub, "email": f"{sub}@example.com"},
        secret if secret is not None else _deps.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Nalaz A — _get_real_ip (X-Forwarded-For), i da ga api.py stvarno koristi
# ═══════════════════════════════════════════════════════════════════════════

class TestGetRealIpExtraction:
    def test_uses_leftmost_x_forwarded_for_value(self):
        """X-Forwarded-For: <client>, <proxy1>, <proxy2> -- klijent je levo."""
        req = _make_request(client_ip="10.0.0.5", forwarded="203.0.113.9, 10.0.0.1, 10.0.0.2")
        assert _get_real_ip(req) == "203.0.113.9"

    def test_single_value_x_forwarded_for(self):
        req = _make_request(client_ip="10.0.0.5", forwarded="203.0.113.9")
        assert _get_real_ip(req) == "203.0.113.9"

    def test_falls_back_to_client_host_without_header(self):
        """Bez X-Forwarded-For (npr. direktna konekcija, dev environment)."""
        req = _make_request(client_ip="127.0.0.1", forwarded=None)
        assert _get_real_ip(req) == "127.0.0.1"

    def test_falls_back_to_unknown_without_client_or_header(self):
        req = _make_request(client_ip=None, forwarded=None)
        assert _get_real_ip(req) == "unknown"

    def test_strips_whitespace_around_forwarded_value(self):
        req = _make_request(client_ip="10.0.0.5", forwarded="  203.0.113.9  , 10.0.0.1")
        assert _get_real_ip(req) == "203.0.113.9"


class TestApiPyUsesRealIp:
    """Strukturna provera da api.py's limiter vise ne koristi
    slowapi.util.get_remote_address (Nalaz A) -- isti obrazac kao
    postojeći tests/test_commit4_p0.py (source-adjacency check)."""

    @pytest.fixture(scope="class")
    def api_src(self):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "api.py").read_text(encoding="utf-8")

    def test_get_remote_address_not_imported(self, api_src):
        assert "from slowapi.util import get_remote_address" not in api_src, (
            "api.py i dalje uvozi slowapi.util.get_remote_address -- "
            "trebalo je zamenjeno sa shared.rate._get_real_ip (Nalaz A)"
        )
        assert "build_limiter(get_remote_address)" not in api_src

    def test_build_limiter_called_with_get_real_ip(self, api_src):
        assert "build_limiter(_get_real_ip)" in api_src

    def test_verify_token_local_imported(self, api_src):
        assert "verify_token_local" in api_src


# ═══════════════════════════════════════════════════════════════════════════
# Nalaz B — request.state.user_id sada radi, per-user limit blokira
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifyTokenLocal:
    """shared.deps.verify_token_local -- lokalna (bez Supabase SDK network
    poziva), potpisom-verifikovana JWT provera koju middleware sad koristi."""

    def test_valid_hs256_token_returns_sub(self):
        from shared.deps import verify_token_local
        token = _make_jwt(sub="user-abc-123")
        payload = verify_token_local(token)
        assert payload is not None
        assert payload["sub"] == "user-abc-123"

    def test_forged_signature_rejected(self):
        """Token potpisan POGREŠNIM ključem mora biti odbijen -- ovo je
        tačno zaštita protiv Sybil-stil zaobilaženja (opcija (a) iz analize,
        namerno NE korišćena bez verifikacije potpisa)."""
        from shared.deps import verify_token_local
        forged = _make_jwt(sub="attacker-controlled-sub", secret="totally-wrong-secret-not-matching-env")
        assert verify_token_local(forged) is None

    def test_empty_token_returns_none(self):
        from shared.deps import verify_token_local
        assert verify_token_local("") is None

    def test_garbage_token_returns_none(self):
        from shared.deps import verify_token_local
        assert verify_token_local("not.a.jwt") is None


class TestUserRateLimitMiddlewareIntegration:
    """Integracioni test preko prave FastAPI app -- dokazuje da ceo lanac
    (Authorization header -> verify_token_local -> request.state.user_id ->
    _check_user_rate_limit) sada stvarno radi, ne samo izolovane funkcije.

    Koristi nepostojeću /api/ putanju namerno: user_rate_limit_middleware
    proverava limit PRE call_next (pre rutiranja), pa i zahtev ka nepostojećoj
    ruti prolazi kroz proveru -- 404 posle znači "prošao je rate check",
    429 znači "middleware ga je blokirao". Ovo izoluje test od slowapi's
    IP-based decorator-a (koji se uopšte ne primenjuje bez postojeće rute).
    """

    def test_valid_token_blocked_after_configured_limit(self, monkeypatch):
        import api
        from fastapi.testclient import TestClient

        monkeypatch.setattr(api, "_USER_API_LIMIT", 3)
        monkeypatch.setattr(api, "_USER_RATE", {})

        token = _make_jwt(sub=f"sec005-test-user-{time.time_ns()}")
        client = TestClient(api.app)
        headers = {"Authorization": f"Bearer {token}"}

        statuses = [
            client.get("/api/__sec005_nonexistent_test_path__", headers=headers).status_code
            for _ in range(5)
        ]

        assert statuses[:3] == [404, 404, 404], (
            f"Prva 3 zahteva (unutar limita od 3) trebalo je da prođu do rutiranja "
            f"(404 = nema takve rute, ali PROŠAO je rate check): {statuses}"
        )
        assert statuses[3] == 429, f"4. zahtev trebalo je da bude blokiran: {statuses}"
        assert statuses[4] == 429, f"5. zahtev trebalo je da bude blokiran: {statuses}"

    def test_request_without_token_is_not_rate_limited_by_user_layer(self, monkeypatch):
        """Bez Authorization header-a, uid ostaje None -- user-level sloj
        ne blokira (anonimni zahtevi se oslanjaju na IP-based slowapi sloj,
        ne na ovaj)."""
        import api
        from fastapi.testclient import TestClient

        monkeypatch.setattr(api, "_USER_API_LIMIT", 1)
        monkeypatch.setattr(api, "_USER_RATE", {})

        client = TestClient(api.app)
        statuses = [
            client.get("/api/__sec005_nonexistent_test_path_anon__").status_code
            for _ in range(3)
        ]
        assert all(s == 404 for s in statuses), (
            f"Bez tokena, user-level limiter ne treba da blokira nijedan zahtev: {statuses}"
        )

    def test_invalid_token_treated_as_anonymous_not_500(self, monkeypatch):
        """Nevalidan/istekao token ne sme da obori middleware -- fail-safe
        na 'nema user-level limit', ne na grešku servera."""
        import api
        from fastapi.testclient import TestClient

        monkeypatch.setattr(api, "_USER_API_LIMIT", 1)
        monkeypatch.setattr(api, "_USER_RATE", {})

        client = TestClient(api.app)
        r = client.get(
            "/api/__sec005_nonexistent_test_path_badtoken__",
            headers={"Authorization": "Bearer garbage.not.valid"},
        )
        assert r.status_code == 404  # ne 500, ne 429 -- tretiran kao anoniman


# ═══════════════════════════════════════════════════════════════════════════
# Pokrivenost — sve novododane AI/enterprise rute imaju @limiter.limit
# ═══════════════════════════════════════════════════════════════════════════

class TestNewlyProtectedRoutesHaveLimiter:
    """Strukturna provera (izvorni kod, ne runtime) da svaka ruta u
    routers/*.py fajlovima identifikovanim u SEC-005 analizi (Sekcija 3 —
    AI rute bez ijedne zaštite) sada ima @limiter.limit dekorator neposredno
    uz @router.<method>(...) liniju."""

    TARGET_FILES = [
        "style_checker.py", "knowledge_transfer.py", "matter_intel.py",
        "evidence.py", "case_intelligence.py", "decision_replay.py",
        "client_twin.py", "cio.py", "outcome_intel.py", "precedenti.py",
        "enterprise.py",
    ]

    @pytest.fixture(scope="class")
    def routers_dir(self):
        from pathlib import Path
        return Path(__file__).resolve().parent.parent / "routers"

    def test_every_route_in_target_files_has_adjacent_limiter(self, routers_dir):
        failures = []
        for fname in self.TARGET_FILES:
            text = (routers_dir / fname).read_text(encoding="utf-8")
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if re.match(r"\s*@router\.(get|post|put|delete|patch)\(", line):
                    # @limiter.limit mora biti tacno na liniji ispod (obrazac
                    # koji je ovaj sprint koristio svuda) ili tacno iznad.
                    neighbors = lines[max(0, i - 1): i + 2]
                    if not any("@limiter.limit(" in n for n in neighbors):
                        failures.append(f"{fname}:{i+1}: {line.strip()}")
        assert not failures, (
            "Sledeće rute nemaju @limiter.limit neposredno uz sebe:\n" + "\n".join(failures)
        )

    def test_target_files_import_limiter(self, routers_dir):
        missing = []
        for fname in self.TARGET_FILES:
            text = (routers_dir / fname).read_text(encoding="utf-8")
            if "from shared.rate import limiter" not in text:
                missing.append(fname)
        assert not missing, f"Fajlovi bez 'from shared.rate import limiter' importa: {missing}"

    def test_target_files_import_request_type(self, routers_dir):
        missing = []
        for fname in self.TARGET_FILES:
            text = (routers_dir / fname).read_text(encoding="utf-8")
            if "Request" not in text.split("from shared.rate import limiter")[0] and \
               "from fastapi import" in text:
                # Request mora biti negde uvezen iz fastapi (bilo gde u fajlu)
                if not re.search(r"from fastapi import[^\n]*\bRequest\b", text):
                    missing.append(fname)
        assert not missing, f"Fajlovi bez Request importa iz fastapi: {missing}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
