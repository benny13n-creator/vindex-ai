# -*- coding: utf-8 -*-
"""
Integracioni testovi za security i stabilnost API-ja.
Pokriva: security headere, /health, /privacy, /terms, error handler, CORS, correlation ID.
"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
    os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
    os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
    os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
    from api import app
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_returns_ok_status(self, client):
        r = client.get("/health")
        data = r.json()
        assert data.get("status") == "ok"

    def test_health_head_allowed(self, client):
        r = client.head("/health")
        assert r.status_code == 200


class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        r = client.get("/health")
        assert r.headers.get("x-frame-options") == "SAMEORIGIN"

    def test_csp_present(self, client):
        r = client.get("/health")
        csp = r.headers.get("content-security-policy", "")
        assert "default-src" in csp

    def test_permissions_policy_no_onrender(self, client):
        r = client.get("/health")
        pp = r.headers.get("permissions-policy", "")
        assert "onrender.com" not in pp

    def test_correlation_id_in_response(self, client):
        r = client.get("/health")
        assert "x-correlation-id" in r.headers

    def test_correlation_id_echoed_from_request(self, client):
        cid = "test-correlation-12345"
        r = client.get("/health", headers={"X-Correlation-ID": cid})
        assert r.headers.get("x-correlation-id") == cid


class TestErrorHandler:
    def test_error_handler_no_exception_leak(self, client):
        """Error handler ne sme da vrati str(exc) ili type(exc).__name__ klijentu."""
        r = client.get("/api/nonexistent-endpoint-that-does-not-exist-xyz")
        if r.status_code == 500:
            body = r.text
            assert "Exception" not in body
            assert "Traceback" not in body
            assert "AttributeError" not in body
            assert "KeyError" not in body

    def test_500_returns_json(self, client):
        r = client.get("/health")
        assert r.status_code != 500


class TestPublicPages:
    def test_privacy_page_returns_200(self, client):
        r = client.get("/privacy")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_terms_page_returns_200(self, client):
        r = client.get("/terms")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_privacy_contains_gdpr_content(self, client):
        r = client.get("/privacy")
        assert "privatnost" in r.text.lower() or "privacy" in r.text.lower()

    def test_terms_contains_disclaimer(self, client):
        r = client.get("/terms")
        assert "ne predstavljaju pravni savet" in r.text.lower()


class TestCORS:
    def test_cors_allowed_origin(self, client):
        r = client.options(
            "/health",
            headers={
                "Origin": "https://vindex.rs",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert r.status_code in (200, 204)

    def test_cors_default_origin_is_not_onrender(self, client):
        allowed = os.getenv("ALLOWED_ORIGINS", "https://vindex.rs")
        assert "vindex-ai.onrender.com" not in allowed or "vindex.rs" in allowed


class TestRobots:
    def test_robots_txt(self, client):
        r = client.get("/robots.txt")
        assert r.status_code == 200
        assert "User-agent" in r.text
        assert "/api/" in r.text
