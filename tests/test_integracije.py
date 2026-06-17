# -*- coding: utf-8 -*-
"""
Phase 5.5 — API za spoljne integracije (Clio, iManage)
Tests for routers/integracije.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
import api

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_KEY    = "vndx_testkey12345"
CLIO_SECRET  = "clio-secret-abc"
IM_SECRET    = "imanage-secret-xyz"
FAKE_USER_ID = "uid-api-user"

FAKE_KEY_ROW = {
    "id":                   "key-001",
    "user_id":              FAKE_USER_ID,
    "aktivan":              True,
    "naziv":                "Test Key",
    "broj_poziva":          5,
    "poslednje_koriscenje": None,
}

FAKE_RETRIEVE_DOCS = (
    [
        "Zakon o obligacionim odnosima čl. 189 — naknada štete...",
        "ZOO čl. 190 — materijalna i nematerijalna šteta...",
    ],
    {
        "confidence": "HIGH",
        "top_score":  0.88,
        "top_article": "čl. 189",
        "top_law":     "ZOO",
    },
)

FAKE_PREDMETI = [
    {"id": "p-001", "naziv": "Predmet A", "tip": "gradjansko", "status": "aktivan"},
    {"id": "p-002", "naziv": "Predmet B", "tip": "krivicno",   "status": "zatvoren"},
]


# ─── Supabase mock ────────────────────────────────────────────────────────────

def _make_supa(key_row=None, predmeti=None, key_limit=False):
    supa = MagicMock()

    def _table(name):
        tbl = MagicMock()
        sel = MagicMock()

        if name == "api_kljucevi":
            row = key_row or FAKE_KEY_ROW
            if key_limit:
                row = {**row, "broj_poziva": 9999}
            sel.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[row])
            tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif name == "predmeti":
            preds = predmeti or FAKE_PREDMETI
            sel.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=preds)
            tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-pred", "naziv": "Novi predmet"}])

        tbl.select.return_value = sel
        return tbl

    supa.table.side_effect = _table
    return supa


def _clio_signature(body: bytes) -> str:
    sig = hmac.new(CLIO_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ─── Client factories ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    api.app.dependency_overrides.clear()


@pytest.fixture
def client():
    supa = _make_supa()
    with patch("routers.integracije._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=True)


@pytest.fixture
def client_no_key():
    supa = _make_supa(key_row=None)

    def _table_no_key(name):
        tbl = MagicMock()
        sel = MagicMock()
        if name == "api_kljucevi":
            sel.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tbl.select.return_value = sel
        return tbl

    supa.table.side_effect = _table_no_key
    with patch("routers.integracije._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=False)


@pytest.fixture
def client_limited():
    supa = _make_supa(key_limit=True)
    with patch("routers.integracije._get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /v1/health
# ═══════════════════════════════════════════════════════════════════════════════

def test_health_200(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0"
    assert "timestamp" in data


def test_health_no_auth_required(client):
    # Health check is public — should return 200 without any key
    r = client.get("/v1/health")
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/analyze
# ═══════════════════════════════════════════════════════════════════════════════

def test_analyze_success(client):
    with patch("routers.integracije._retrieve", return_value=FAKE_RETRIEVE_DOCS), \
         patch("routers.integracije._gpt_analyze", return_value="Prema ZOO čl. 189, oštećeni ima pravo na naknadu."):
        r = client.post("/v1/analyze",
                        json={"pitanje": "Koje su moje obaveze prema ugovoru?"},
                        headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 200
    data = r.json()
    assert "odgovor" in data
    assert data["confidence"] == "HIGH"
    assert "pitanje" in data
    assert "napomena" in data


def test_analyze_no_key_401():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/v1/analyze", json={"pitanje": "Koji je rok zastarelosti?"})
    assert r.status_code == 401


def test_analyze_invalid_key_401(client_no_key):
    r = client_no_key.post(
        "/v1/analyze",
        json={"pitanje": "Koji je rok zastarelosti?"},
        headers={"X-Vindex-Key": "vndx_wrongkey"},
    )
    assert r.status_code == 401


def test_analyze_rate_limit_exceeded_429(client_limited):
    with patch("routers.integracije._retrieve", return_value=FAKE_RETRIEVE_DOCS), \
         patch("routers.integracije._gpt_analyze", return_value="odgovor"):
        r = client_limited.post(
            "/v1/analyze",
            json={"pitanje": "Koji je rok zastarelosti za obligacije?"},
            headers={"X-Vindex-Key": VALID_KEY},
        )
    assert r.status_code == 429


def test_analyze_low_confidence(client):
    low_meta = ([], {"confidence": "LOW", "top_score": 0.15})
    with patch("routers.integracije._retrieve", return_value=low_meta):
        r = client.post("/v1/analyze",
                        json={"pitanje": "Nešto potpuno van baze zakona?"},
                        headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 200
    assert r.json()["confidence"] == "LOW"


def test_analyze_pitanje_too_short(client):
    r = client.post("/v1/analyze",
                    json={"pitanje": "ab"},
                    headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 422


def test_analyze_bearer_token(client):
    with patch("routers.integracije._retrieve", return_value=FAKE_RETRIEVE_DOCS), \
         patch("routers.integracije._gpt_analyze", return_value="Odgovor."):
        r = client.post("/v1/analyze",
                        json={"pitanje": "Koji je rok zastarelosti za ugovore?"},
                        headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# GET /v1/predmeti
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_predmeti_success(client):
    r = client.get("/v1/predmeti", headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 200
    data = r.json()
    assert "predmeti" in data
    assert isinstance(data["predmeti"], list)
    assert "total" in data


def test_get_predmeti_no_key_401():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.get("/v1/predmeti")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/predmeti
# ═══════════════════════════════════════════════════════════════════════════════

def test_create_predmet_success(client):
    r = client.post("/v1/predmeti",
                    json={"naziv": "Novi predmet iz Clio", "tip": "gradjansko"},
                    headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 201
    data = r.json()
    assert "predmet" in data
    assert data["status"] == "kreiran"


def test_create_predmet_no_key_401():
    c = TestClient(api.app, raise_server_exceptions=False)
    r = c.post("/v1/predmeti", json={"naziv": "Test"})
    assert r.status_code == 401


def test_create_predmet_missing_naziv_422(client):
    r = client.post("/v1/predmeti",
                    json={"tip": "gradjansko"},
                    headers={"X-Vindex-Key": VALID_KEY})
    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/webhook/clio
# ═══════════════════════════════════════════════════════════════════════════════

def test_webhook_clio_success(client):
    body = json.dumps({
        "matter":          {"display_number": "2024/001", "description": "Porodični spor"},
        "vindex_user_id":  FAKE_USER_ID,
    }).encode()
    sig = _clio_signature(body)

    with patch.dict(os.environ, {"CLIO_WEBHOOK_SECRET": CLIO_SECRET,
                                  "CLIO_DEFAULT_USER_ID": ""}):
        r = client.post("/v1/webhook/clio",
                        content=body,
                        headers={"X-Clio-Signature": sig,
                                 "Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook_clio_invalid_sig(client):
    body = json.dumps({"matter": {"description": "Test"}}).encode()
    with patch.dict(os.environ, {"CLIO_WEBHOOK_SECRET": CLIO_SECRET}):
        r = client.post("/v1/webhook/clio",
                        content=body,
                        headers={"X-Clio-Signature": "sha256=wrongsig",
                                 "Content-Type": "application/json"})
    assert r.status_code == 401


def test_webhook_clio_not_configured():
    c = TestClient(api.app, raise_server_exceptions=False)
    with patch.dict(os.environ, {"CLIO_WEBHOOK_SECRET": ""}):
        r = c.post("/v1/webhook/clio", json={"matter": {}})
    assert r.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/webhook/imanage
# ═══════════════════════════════════════════════════════════════════════════════

def test_webhook_imanage_success(client):
    payload = {"event_type": "document.created", "document": {"name": "ugovor.pdf", "id": "doc-001"}}
    with patch.dict(os.environ, {"IMANAGE_WEBHOOK_SECRET": IM_SECRET}):
        r = client.post("/v1/webhook/imanage",
                        json=payload,
                        headers={"X-IManage-Token": IM_SECRET})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "primljeno"
    assert data["dokument"] == "ugovor.pdf"


def test_webhook_imanage_invalid_token(client):
    with patch.dict(os.environ, {"IMANAGE_WEBHOOK_SECRET": IM_SECRET}):
        r = client.post("/v1/webhook/imanage",
                        json={"event_type": "document.created"},
                        headers={"X-IManage-Token": "wrong-token"})
    assert r.status_code == 401


def test_webhook_imanage_not_configured():
    c = TestClient(api.app, raise_server_exceptions=False)
    with patch.dict(os.environ, {"IMANAGE_WEBHOOK_SECRET": ""}):
        r = c.post("/v1/webhook/imanage", json={"event_type": "test"})
    assert r.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: helper functions
# ═══════════════════════════════════════════════════════════════════════════════

from routers.integracije import _verify_clio_signature, _verify_imanage_token, _run_analyze_sync


def test_verify_clio_signature_valid():
    body = b'{"test": "data"}'
    sig = hmac.new(CLIO_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_clio_signature(body, f"sha256={sig}", CLIO_SECRET) is True


def test_verify_clio_signature_invalid():
    body = b'{"test": "data"}'
    assert _verify_clio_signature(body, "sha256=invalidsig", CLIO_SECRET) is False


def test_verify_clio_signature_missing_prefix():
    body = b'{"test": "data"}'
    assert _verify_clio_signature(body, "invalidsig", CLIO_SECRET) is False


def test_verify_imanage_token_valid():
    assert _verify_imanage_token(IM_SECRET, IM_SECRET) is True


def test_verify_imanage_token_invalid():
    assert _verify_imanage_token("wrong", IM_SECRET) is False


def test_run_analyze_sync_high():
    with patch("routers.integracije._retrieve", return_value=FAKE_RETRIEVE_DOCS), \
         patch("routers.integracije._gpt_analyze", return_value="Pravni odgovor."):
        result = _run_analyze_sync("Koji je rok zastarelosti?")
    assert result["confidence"] == "HIGH"
    assert result["odgovor"] == "Pravni odgovor."


def test_run_analyze_sync_low_no_gpt():
    gpt_mock = MagicMock()
    low = ([], {"confidence": "LOW", "top_score": 0.1})
    with patch("routers.integracije._retrieve", return_value=low), \
         patch("routers.integracije._gpt_analyze", gpt_mock):
        result = _run_analyze_sync("Pitanje van baze")
    gpt_mock.assert_not_called()
    assert result["confidence"] == "LOW"
