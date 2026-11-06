# -*- coding: utf-8 -*-
"""Response policy tests for the Word entry points."""
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-no-network"}):
    import api


def test_word_entry_csp_fails_closed_when_host_allowlist_is_missing(monkeypatch):
    monkeypatch.delenv("WORD_ADDIN_FRAME_ANCESTORS", raising=False)
    client = TestClient(api.app)
    response = client.get("/word_addin/taskpane.html")
    assert response.status_code == 200
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self' https://appsforoffice.microsoft.com" in csp
    assert "unsafe-inline" not in csp.split("script-src", 1)[1].split(";", 1)[0]
    assert "unsafe-eval" not in csp


def test_word_entry_csp_accepts_only_configured_https_ancestors(monkeypatch):
    monkeypatch.setenv("WORD_ADDIN_FRAME_ANCESTORS", "https://word-client.example.test")
    monkeypatch.setenv("SUPABASE_URL", "https://auth.example.test")
    client = TestClient(api.app)
    response = client.get("/word_addin/auth.html")
    assert response.status_code == 200
    assert "x-frame-options" not in response.headers
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors https://word-client.example.test" in csp
    assert "connect-src 'self' https://auth.example.test;" in csp
    assert "https://*.supabase.co" not in csp


def test_invalid_word_ancestor_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("WORD_ADDIN_FRAME_ANCESTORS", "https://*.example.test")
    client = TestClient(api.app)
    response = client.get("/word_addin/commands.html")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]