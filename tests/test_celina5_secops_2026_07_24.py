# -*- coding: utf-8 -*-
"""
Regression tests — Celina 5: SecOps, Operational Readiness & Observability
(2026-07-24).

1. Task 1 (Security Telemetry): SEC-017 ("login_failed" bio definisan u
   AUDITABLE_ACTIONS ali nikad pozivan -- auth se dešava client-side preko
   Supabase, backend vidi samo bearer token na sledećem zahtevu) je zatvoren
   za posmatrljivu polovinu: get_current_user (shared/deps.py) sad upisuje
   login_failed na oba 401 puta (nedostaje token / token nevažeći-istekao).
   OCR greške (uploaded_doc/extractor.py) i RAG/Pinecone greške
   (app/services/retrieve.py) su ranije postojale samo kao logger pozivi
   (nevidljive bez pristupa server logovima) -- sad upisuju u
   security_events za GET /api/admin/security-overview telemetriju.
2. Task 3 (Backup Verification Drill): scripts/verify_backup_restore.py
   potpisuje izveštaj HMAC-SHA256-om (kanonski JSON, sort_keys=True) --
   test dokazuje sign/verify roundtrip I da izmena posle potpisivanja
   pada na proveri (tamper detection).
3. Audit chain incident (v. docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md):
   drill-ov PRVI živi pokreta protiv produkcije otkrio je da je
   verify_chain_integrity() prijavljivao lažnu "MODIFIKACIJA DETEKTOVANA"
   na seq=17 zbog toga što Postgres/PostgREST otkida nule na kraju
   mikrosekundnog dela created_at-a pri serijalizaciji u tekst, dok je
   log_action() u trenutku upisa heš-ovao pun 6-cifreni Python
   isoformat() string (_normalize_ts_for_hash ispravlja ovo). Nakon te
   ispravke, otkriven je i STVARAN (ali ne-zlonameran) prekid na seq=32:
   TOCTOU trka između dva konkurentna upisa u razmaku od 2.6ms, oba su
   pročitala isti "poslednji hash" pre nego što je ijedan upisan.
   _KNOWN_EXPLAINED_BREAKS dokumentuje TAČNO taj jedan slučaj tako da
   verify_chain_integrity() nastavi proveru posle njega (bez ovoga bi
   alat bio TRAJNO slep za sve nakon seq=32) -- svaki DRUGI, neobjašnjen
   prekid i dalje tvrdo zaustavlja proveru. migracije/081 + retry petlja
   u _build_and_insert() sprečavaju da se ista trka ikad ponovi.

Sve fire-and-forget telemetrijske funkcije MORAJU biti best-effort: greška
u upisu u security_events/audit_immutable ne sme nikad da prekine glavni
tok (401 odgovor, OCR ekstrakciju, RAG pretragu) -- svaki blok ispod ima
i "never raises" test za to.

Pure unit tests -- no live Supabase, no OpenAI.
"""
import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from starlette.requests import Request as StarletteRequest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _req(path: str = "/api/x") -> StarletteRequest:
    """Real starlette Request -- @limiter.limit radi isinstance(request, Request)
    proveru i čita request.client za rate-limit ključ (isti obrazac kao
    tests/test_sec001_predmet_ownership.py)."""
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": "GET", "path": path,
        "headers": [], "query_string": b"", "app": MagicMock(),
        "state": MagicMock(), "client": ("203.0.113.5", 443),
    }
    return StarletteRequest(scope=scope, receive=receive)


# ─── 1a. login_failed audit telemetrija (SEC-017, observable half) ─────────

def test_log_login_failed_calls_audit_log_action_with_reason_and_ip():
    import shared.deps as deps

    with patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        asyncio.run(deps._log_login_failed("no_credentials", _req()))

    mock_log.assert_awaited_once()
    args, kwargs = mock_log.call_args
    assert args[0] == "login_failed"
    assert kwargs["ip"] == "203.0.113.5"
    assert kwargs["metadata"]["reason"] == "no_credentials"


def test_log_login_failed_never_raises_when_audit_log_fails():
    import shared.deps as deps

    with patch("shared.audit_immutable.log_action", new=AsyncMock(side_effect=RuntimeError("db down"))):
        asyncio.run(deps._log_login_failed("no_credentials", _req()))  # must not raise


def test_get_current_user_missing_credentials_schedules_login_failed():
    import shared.deps as deps
    from fastapi import HTTPException

    with patch.object(deps.asyncio, "create_task") as mock_create_task:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(deps.get_current_user(_req(), None))
        assert exc_info.value.status_code == 401
    mock_create_task.assert_called_once()


def test_get_current_user_invalid_token_schedules_login_failed():
    import shared.deps as deps
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token.value")

    with patch.object(deps, "_verify_token", return_value=None), \
         patch.object(deps.asyncio, "create_task") as mock_create_task:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(deps.get_current_user(_req(), creds))
        assert exc_info.value.status_code == 401
    mock_create_task.assert_called_once()


# ─── 1b. OCR greška telemetrija ─────────────────────────────────────────────

def test_log_ocr_error_writes_security_events_row():
    import uploaded_doc.extractor as extractor

    mock_supa = MagicMock()
    with patch("api._get_supa", return_value=mock_supa):
        extractor._log_ocr_error("insufficient_text", "ugovor.pdf")

    mock_supa.table.assert_called_with("security_events")
    inserted = mock_supa.table.return_value.insert.call_args[0][0]
    assert inserted["event_type"] == "ocr_error"
    assert inserted["details"]["reason"] == "insufficient_text"
    assert inserted["details"]["filename"] == "ugovor.pdf"


def test_log_ocr_error_never_raises_when_db_unavailable():
    import uploaded_doc.extractor as extractor

    with patch("api._get_supa", side_effect=RuntimeError("no db")):
        extractor._log_ocr_error("unexpected_error", "x.pdf")  # must not raise


# ─── 1c. RAG/Pinecone greška telemetrija ────────────────────────────────────

def test_log_rag_error_writes_security_events_row():
    import app.services.retrieve as retrieve

    mock_supa = MagicMock()
    with patch("api._get_supa", return_value=mock_supa):
        retrieve._log_rag_error("PineconeApiException", retrieve._ZAKONI_NS, "timeout after 30s")

    inserted = mock_supa.table.return_value.insert.call_args[0][0]
    assert inserted["event_type"] == "rag_error"
    assert inserted["details"]["namespace"] == "zakoni_rs"
    assert inserted["details"]["reason"] == "PineconeApiException"


def test_log_rag_error_never_raises_when_db_unavailable():
    import app.services.retrieve as retrieve

    with patch("api._get_supa", side_effect=RuntimeError("no db")):
        retrieve._log_rag_error("PineconeApiException", retrieve._PRAKSA_NS, "x")  # must not raise


# ─── 1d. Admin security-overview / security-events (drill-down) ───────────

def test_security_overview_reports_all_telemetry_event_types():
    import routers.admin_dashboard as admin_dashboard

    mock_supa = MagicMock()
    mock_table = MagicMock()
    mock_supa.table.return_value = mock_table
    for m in ("select", "limit", "eq", "gte", "maybe_single"):
        setattr(mock_table, m, MagicMock(return_value=mock_table))
    mock_table.execute = MagicMock(return_value=MagicMock(count=2, data=[]))

    founder_user = {"email": "test@test.com", "user_id": "u1"}

    with patch.object(admin_dashboard, "_get_supa", return_value=mock_supa), \
         patch.object(admin_dashboard, "_is_founder", return_value=True), \
         patch("shared.audit_immutable.verify_chain_integrity", new=AsyncMock(return_value={"ok": True})):
        result = asyncio.run(admin_dashboard.security_overview.__wrapped__(_req(), founder_user))

    assert "security_events_by_type_24h" in result
    for et in admin_dashboard._TELEMETRY_EVENT_TYPES:
        assert et in result["security_events_by_type_24h"]
    assert "login_failed" in admin_dashboard._TELEMETRY_EVENT_TYPES
    assert "ocr_error" in admin_dashboard._TELEMETRY_EVENT_TYPES
    assert "rag_error" in admin_dashboard._TELEMETRY_EVENT_TYPES
    assert result["audit_chain_integrity"] == {"ok": True}


def test_security_overview_rejects_non_founder():
    import routers.admin_dashboard as admin_dashboard
    from fastapi import HTTPException

    non_founder = {"email": "nobody@example.com", "user_id": "u2"}
    with patch.object(admin_dashboard, "_is_founder", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(admin_dashboard.security_overview.__wrapped__(_req(), non_founder))
    assert exc_info.value.status_code == 403


def test_security_events_list_filters_by_event_type():
    import routers.admin_dashboard as admin_dashboard

    mock_supa = MagicMock()
    mock_table = MagicMock()
    mock_supa.table.return_value = mock_table
    for m in ("select", "order", "limit", "eq"):
        setattr(mock_table, m, MagicMock(return_value=mock_table))
    mock_table.execute = MagicMock(return_value=MagicMock(data=[{"event_type": "ocr_error"}]))

    founder_user = {"email": "test@test.com", "user_id": "u1"}

    with patch.object(admin_dashboard, "_get_supa", return_value=mock_supa), \
         patch.object(admin_dashboard, "_is_founder", return_value=True):
        result = asyncio.run(
            admin_dashboard.security_events_list.__wrapped__(
                _req(), founder_user, event_type="ocr_error", limit=10
            )
        )
    mock_table.eq.assert_called_with("event_type", "ocr_error")
    assert result["ukupno"] == 1


# ─── 1e. Audit chain hash-integrity bugs (found via live smoke test) ──────

def test_normalize_ts_for_hash_pads_stripped_trailing_zeros():
    import shared.audit_immutable as audit

    assert audit._normalize_ts_for_hash("2026-07-18T21:00:19.99092+00:00") == "2026-07-18T21:00:19.990920+00:00"
    assert audit._normalize_ts_for_hash("2026-07-18T21:01:01.55478+00:00") == "2026-07-18T21:01:01.554780+00:00"
    assert audit._normalize_ts_for_hash("2026-07-18T20:59:47.257745+00:00") == "2026-07-18T20:59:47.257745+00:00"
    assert audit._normalize_ts_for_hash("2026-07-18T21:00:00+00:00") == "2026-07-18T21:00:00+00:00"


def _chain_row(seq, prev_hash, user_id, action, ts, rtype, rid):
    import shared.audit_immutable as audit
    entry_hash = audit._compute_entry_hash(prev_hash, user_id, action, ts, rtype, rid)
    return {
        "seq": seq, "prev_hash": prev_hash, "entry_hash": entry_hash,
        "user_id": user_id, "action": action, "created_at": ts,
        "resource_type": rtype, "resource_id": rid,
    }, entry_hash


def _mock_select_supa(rows):
    mock_supa = MagicMock()
    mock_query = MagicMock()
    mock_supa.table.return_value = mock_query
    for m in ("select", "order", "limit"):
        setattr(mock_query, m, MagicMock(return_value=mock_query))
    mock_query.execute = MagicMock(return_value=MagicMock(data=rows))
    return mock_supa


def test_verify_chain_recognizes_known_explained_break_and_keeps_checking():
    """seq=32 in production was a real TOCTOU fork (docs/security/
    AUDIT_CHAIN_INCIDENT_2026-07-24.md), not tampering. Without the
    allowlist, verify_chain_integrity() would hard-stop there forever and
    never check anything written after it again."""
    import shared.audit_immutable as audit

    row1, h1 = _chain_row(1, audit._GENESIS_HASH, "u1", "login_failed", "2026-01-01T00:00:00.000001+00:00", "session", "r1")
    row2, h2 = _chain_row(2, h1, "u1", "login_failed", "2026-01-01T00:00:01.000001+00:00", "session", "r2")
    # seq=3 forks: reuses seq=1's hash as prev_hash instead of seq=2's (simulates the race)
    row3, h3 = _chain_row(3, h1, "u1", "login_failed", "2026-01-01T00:00:02.000001+00:00", "session", "r3")
    # seq=4 continues linearly from the fork at seq=3
    row4, _ = _chain_row(4, h3, "u1", "login_failed", "2026-01-01T00:00:03.000001+00:00", "session", "r4")

    with patch.object(audit, "_KNOWN_EXPLAINED_BREAKS", {3: "test fixture — simulated race"}), \
         patch("api._get_supa", return_value=_mock_select_supa([row1, row2, row3, row4])):
        result = audit._verify_chain_sync(limit=1000)

    assert result["ok"] is True
    assert result["known_breaks"] == [3]
    assert result["broken_at_seq"] is None
    assert result["checked"] == 4


def test_verify_chain_still_hard_fails_on_unexplained_break():
    import shared.audit_immutable as audit

    row1, h1 = _chain_row(1, audit._GENESIS_HASH, "u1", "login_failed", "2026-01-01T00:00:00.000001+00:00", "session", "r1")
    # seq=2 has a bogus prev_hash that is NOT in _KNOWN_EXPLAINED_BREAKS
    row2 = {
        "seq": 2, "prev_hash": "0" * 64, "entry_hash": "1" * 64, "user_id": "u1",
        "action": "login_failed", "created_at": "2026-01-01T00:00:01.000001+00:00",
        "resource_type": "session", "resource_id": "r2",
    }

    with patch.object(audit, "_KNOWN_EXPLAINED_BREAKS", {}), \
         patch("api._get_supa", return_value=_mock_select_supa([row1, row2])):
        result = audit._verify_chain_sync(limit=1000)

    assert result["ok"] is False
    assert result["broken_at_seq"] == 2


def test_build_and_insert_retries_on_prev_hash_unique_violation():
    """Migracija 081 dodaje UNIQUE(prev_hash) za seq>32 -- kad dva
    konkurentna upisa udare u isti prev_hash, gubitnik mora da ponovi sa
    svežim prev_hash-om umesto da propagira grešku ka pozivaocu."""
    import shared.audit_immutable as audit

    mock_supa = MagicMock()
    mock_query = MagicMock()
    mock_supa.table.return_value = mock_query
    for m in ("select", "order", "limit", "insert"):
        setattr(mock_query, m, MagicMock(return_value=mock_query))

    unique_violation = Exception(
        'duplicate key value violates unique constraint "audit_immutable_prev_hash_unique" 23505'
    )
    select_result = MagicMock(data=[{"entry_hash": "a" * 64}])
    insert_success = MagicMock(data=[{"id": "row-2"}])
    mock_query.execute = MagicMock(side_effect=[select_result, unique_violation, select_result, insert_success])

    with patch("api._get_supa", return_value=mock_supa):
        result_id = audit._build_and_insert("login_failed", "u1", "session", "r1", None, {})

    assert result_id == "row-2"
    assert mock_query.execute.call_count == 4


def test_build_and_insert_does_not_retry_on_unrelated_errors():
    import shared.audit_immutable as audit

    mock_supa = MagicMock()
    mock_query = MagicMock()
    mock_supa.table.return_value = mock_query
    for m in ("select", "order", "limit", "insert"):
        setattr(mock_query, m, MagicMock(return_value=mock_query))

    select_result = MagicMock(data=[{"entry_hash": "a" * 64}])
    mock_query.execute = MagicMock(side_effect=[select_result, RuntimeError("connection reset")])

    with patch("api._get_supa", return_value=mock_supa):
        with pytest.raises(RuntimeError):
            audit._build_and_insert("login_failed", "u1", "session", "r1", None, {})

    assert mock_query.execute.call_count == 2


# ─── 2. Backup verification report signing (HMAC-SHA256, tamper detection) ─

def test_backup_report_signature_roundtrip(tmp_path):
    import scripts.verify_backup_restore as vbr

    payload = {"generated_at": "2026-07-24T00:00:00Z", "checks": [{"name": "connectivity", "ok": True}]}
    signature, key_source = vbr._sign_report(payload)

    report = dict(payload)
    report["signature"] = signature
    report["signature_key_source"] = key_source
    report_path = tmp_path / "backup_restore_verification.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    assert vbr.verify_report_signature(str(report_path)) is True


def test_backup_report_signature_detects_tampering(tmp_path):
    import scripts.verify_backup_restore as vbr

    payload = {"generated_at": "2026-07-24T00:00:00Z", "checks": [{"name": "connectivity", "ok": True}]}
    signature, key_source = vbr._sign_report(payload)

    report = dict(payload)
    report["signature"] = signature
    report["signature_key_source"] = key_source
    report["checks"][0]["ok"] = False  # tamper AFTER signing
    report_path = tmp_path / "tampered.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    assert vbr.verify_report_signature(str(report_path)) is False


def test_backup_report_signature_is_deterministic_regardless_of_key_order():
    import scripts.verify_backup_restore as vbr

    payload_a = {"a": 1, "b": 2}
    payload_b = {"b": 2, "a": 1}
    sig_a, _ = vbr._sign_report(payload_a)
    sig_b, _ = vbr._sign_report(payload_b)
    assert sig_a == sig_b


def test_backup_report_all_reserved_fields_must_be_signed_before_saving(tmp_path):
    """Regression for a real bug found by main()'s first live run: it used
    to add signature_algorithm to report_body AFTER calling _sign_report(),
    so the field was saved to disk but never part of what was hashed --
    verify_report_signature() then always failed on a freshly-generated,
    untampered report. Any reserved/metadata field must be present in the
    payload BEFORE _sign_report() is called, not added after."""
    import scripts.verify_backup_restore as vbr

    payload = {"generated_at": "2026-07-24T00:00:00Z", "signature_algorithm": "HMAC-SHA256"}
    signature, key_source = vbr._sign_report(payload)

    report = dict(payload)
    report["signature"] = signature
    report["signature_key_source"] = key_source
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    assert vbr.verify_report_signature(str(report_path)) is True
