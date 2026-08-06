# -*- coding: utf-8 -*-
"""
Program Lambda, Master Sprint 001 ("Full Beta Readiness Certification") —
proof tests for every "safe to fix now" finding this sprint's own forensic
audits surfaced and fixed. Each test proves the SPECIFIC problem found, not
a general regression check.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-za-testove-128bit")

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# SEC-011 — SlowAPIMiddleware was never registered
# ═══════════════════════════════════════════════════════════════════════════

def test_slowapi_middleware_is_registered_on_app():
    """SEC-011: shared/rate.py's own default_limits=['60/hour'] floor was
    very likely non-enforcing for any route without an explicit
    @limiter.limit() decorator, because SlowAPIMiddleware -- the piece that
    actually ENFORCES app.state.limiter's own default_limits -- was never
    added via app.add_middleware(). Proves the fix: the middleware is now
    present on the real app instance, not just imported."""
    from dotenv import load_dotenv
    load_dotenv()
    import api
    from slowapi.middleware import SlowAPIMiddleware

    middleware_classes = [m.cls for m in api.app.user_middleware]
    assert SlowAPIMiddleware in middleware_classes


def test_app_state_limiter_still_set():
    """Negative control: confirm the pre-existing limiter wiring (app.state.limiter,
    the RateLimitExceeded handler) is unaffected by adding the middleware --
    this fix is additive, not a replacement."""
    from dotenv import load_dotenv
    load_dotenv()
    import api
    assert api.app.state.limiter is api.limiter


# ═══════════════════════════════════════════════════════════════════════════
# Reliability Audit — routers/strategy_simulator.py was the one GPT-calling
# file in the whole repo missing @llm_retry
# ═══════════════════════════════════════════════════════════════════════════

def test_strategy_simulator_pozovi_gpt_survives_one_transient_error():
    """Proves the fix, not just that a decorator is present: a transient
    OpenAI error (RateLimitError) on the first attempt must now be silently
    retried and the call must succeed on the 2nd attempt -- the exact
    behavior every other GPT-calling file in this repo already has."""
    from unittest.mock import MagicMock, patch
    import openai
    from routers.strategy_simulator import _pozovi_gpt

    ok_msg = MagicMock()
    ok_msg.content = '{"ok": true}'
    ok_choice = MagicMock(message=ok_msg)
    ok_resp = MagicMock(choices=[ok_choice])

    rate_limit_error = openai.RateLimitError(
        message="rate limited", response=MagicMock(status_code=429), body=None,
    )

    with patch("openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [rate_limit_error, ok_resp]
        mock_cls.return_value = mock_client

        result = _pozovi_gpt([{"role": "user", "content": "x"}])

    assert result == {"ok": True}
    assert mock_client.chat.completions.create.call_count == 2


def test_strategy_simulator_pozovi_gpt_has_retry_wrapper():
    """Structural confirmation: _pozovi_gpt is now wrapped by tenacity's own
    retry machinery (the same @llm_retry every other GPT-calling file uses),
    not just coincidentally succeeding in the test above."""
    from routers.strategy_simulator import _pozovi_gpt
    assert hasattr(_pozovi_gpt, "retry")


# ═══════════════════════════════════════════════════════════════════════════
# Architecture Auditor — client_portal.py's own "false success" upload bug
# ═══════════════════════════════════════════════════════════════════════════

import io
import time as _time
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _portal_req():
    scope = {
        "type": "http", "method": "POST", "headers": [],
        "query_string": b"", "path": "/api/client-portal/dokument",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_upload_file(content: bytes = b"%PDF-1.4 fake pdf content", filename: str = "dokaz.pdf", content_type: str = "application/pdf"):
    from fastapi import UploadFile
    f = UploadFile(filename=filename, file=io.BytesIO(content))
    f.headers = {"content-type": content_type}
    return f


def _portal_supa(insert_should_fail: bool, bucket_remove_should_fail: bool = False):
    """Minimal supa mock covering exactly client_portal_upload's own call
    sequence: token-active check, storage upload, DB insert (fails or not),
    and (on failure) a compensating storage remove()."""
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "client_portal_tokens":
            tok_result = MagicMock()
            tok_result.data = {"id": "tok-1", "is_active": True}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = tok_result
        elif name == "client_portal_uploads":
            if insert_should_fail:
                t.insert.return_value.execute.side_effect = Exception("db insert failed")
            else:
                ins_result = MagicMock()
                ins_result.data = [{"id": "upload-1"}]
                t.insert.return_value.execute.return_value = ins_result
        return t

    supa.table.side_effect = _table

    bucket = MagicMock()
    bucket.upload.return_value = None
    if bucket_remove_should_fail:
        bucket.remove.side_effect = Exception("storage remove also failed")
    else:
        bucket.remove.return_value = None
    supa.storage.from_.return_value = bucket
    return supa, bucket


@pytest.mark.anyio
async def test_portal_upload_db_failure_compensates_and_returns_honest_error():
    """Proves the fix: when the client_portal_uploads DB insert fails AFTER
    the storage upload already succeeded, the endpoint must (a) NOT return
    ok:True/"uspešno dostavljen" (the old false-success bug), (b) raise a
    clean HTTPException instead, and (c) call bucket.remove() to clean up
    the orphaned blob -- the same compensating pattern smart_intake.py
    already uses for the identical race."""
    from fastapi import HTTPException
    from routers.client_portal import client_portal_upload, _generiši_token

    supa, bucket = _portal_supa(insert_should_fail=True)
    token = _generiši_token("pred-1", "advokat-1", int(_time.time()) + 3600)

    with patch("routers.client_portal._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await client_portal_upload(
                request=_portal_req(),
                fajl=_fake_upload_file(),
                napomena=None,
                x_portal_token=token,
            )

    assert exc.value.status_code == 500
    bucket.remove.assert_called_once()


@pytest.mark.anyio
async def test_portal_upload_compensating_delete_failure_still_returns_honest_error():
    """Double-failure case (matching smart_intake.py's own best-effort
    handling): even if the compensating bucket.remove() ALSO fails, the
    endpoint must still raise (not silently fall through to a false
    success) -- the cleanup is best-effort, the honesty of the response is
    not optional."""
    from fastapi import HTTPException
    from routers.client_portal import client_portal_upload, _generiši_token

    supa, bucket = _portal_supa(insert_should_fail=True, bucket_remove_should_fail=True)
    token = _generiši_token("pred-1", "advokat-1", int(_time.time()) + 3600)

    with patch("routers.client_portal._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await client_portal_upload(
                request=_portal_req(),
                fajl=_fake_upload_file(),
                napomena=None,
                x_portal_token=token,
            )

    assert exc.value.status_code == 500


@pytest.mark.anyio
async def test_portal_upload_success_path_unaffected():
    """Negative control: the fix must not touch the happy path -- a
    successful DB insert still returns ok:True and never calls
    bucket.remove()."""
    from routers.client_portal import client_portal_upload, _generiši_token

    supa, bucket = _portal_supa(insert_should_fail=False)
    token = _generiši_token("pred-1", "advokat-1", int(_time.time()) + 3600)

    with patch("routers.client_portal._get_supa", return_value=supa), \
         patch("routers.client_portal._notify_advokat_upload_bg", new_callable=AsyncMock):
        result = await client_portal_upload(
            request=_portal_req(),
            fajl=_fake_upload_file(),
            napomena=None,
            x_portal_token=token,
        )

    assert result["ok"] is True
    assert result["upload_id"] == "upload-1"
    bucket.remove.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# AI Reasoning Auditor — digital_twin.py's own ungrounded probability claims
# ═══════════════════════════════════════════════════════════════════════════

def _twin_req():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/twin/simulacija", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _twin_user(uid="uid-1"):
    return {"user_id": uid, "email": "advokat@vindex.rs"}


def _twin_supa(predmet_id="pred-1"):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            r = MagicMock()
            r.data = [{"id": predmet_id, "naziv": "Test predmet", "tip": "parnica",
                       "status": "aktivan", "rizik": "srednji", "opis": "opis", "created_at": "2026-01-01"}]
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = r
        elif name == "twin_simulacije":
            r = MagicMock(); r.data = [{"id": "sim-1"}]
            t.insert.return_value.execute.return_value = r
        else:
            r = MagicMock(); r.data = []
            chain = t.select.return_value.eq.return_value
            chain.order.return_value.execute.return_value = r
            chain.order.return_value.limit.return_value.execute.return_value = r
            chain.execute.return_value = r
        return t

    supa.table.side_effect = _table
    return supa


def _twin_cc(readiness_status="READY"):
    return {"readiness": {"value": {"status": readiness_status, "razlog": "test", "izvor": []}}}


def _twin_oai_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(message=msg)
    resp = MagicMock(choices=[choice])
    return resp


import json


@pytest.mark.anyio
async def test_digital_twin_simulacija_caps_optimistic_scenario_when_critical_gap():
    """Adversarial: GPT claims a 90% optimistic-scenario probability for a
    case whose own canonical readiness is CRITICAL_GAP -- must be capped,
    same mechanism proven for court_predictor.py/hearing_cc.py."""
    from routers.digital_twin import kreiraj_simulaciju, SimulacijaRequest

    poisoned = {
        "scenariji": [
            {"naziv": "Optimisticki", "verovatnoca": 90, "opis": "x", "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 6},
            {"naziv": "Realni", "verovatnoca": 60, "opis": "x", "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 12},
            {"naziv": "Pesimisticki", "verovatnoca": 10, "opis": "x", "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 24},
        ],
        "kljucne_tacke": [], "optimalna_strategija": "x",
    }

    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, return_value=_twin_cc(readiness_status="CRITICAL_GAP")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(poisoned)
        mock_oai_cls.return_value = mock_oai

        result = await kreiraj_simulaciju(
            SimulacijaRequest(predmet_id="pred-1"), _twin_req(), _twin_user(),
        )

    caps = {s["naziv"]: s["verovatnoca"] for s in result["scenariji"]}
    assert caps["Optimisticki"] == 50
    assert caps["Realni"] == 50
    assert caps["Pesimisticki"] == 10  # already under the cap, untouched


@pytest.mark.anyio
async def test_digital_twin_simulacija_no_cap_when_ready():
    from routers.digital_twin import kreiraj_simulaciju, SimulacijaRequest

    payload = {
        "scenariji": [
            {"naziv": "Optimisticki", "verovatnoca": 90, "opis": "x", "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 6},
        ],
        "kljucne_tacke": [], "optimalna_strategija": "x",
    }

    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, return_value=_twin_cc(readiness_status="READY")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(payload)
        mock_oai_cls.return_value = mock_oai

        result = await kreiraj_simulaciju(
            SimulacijaRequest(predmet_id="pred-1"), _twin_req(), _twin_user(),
        )

    assert result["scenariji"][0]["verovatnoca"] == 90


@pytest.mark.anyio
async def test_digital_twin_sta_ako_caps_nova_verovatnoca_when_blocked():
    from routers.digital_twin import sta_ako_analiza, StaAkoRequest

    poisoned = {"uticaj": "x", "nova_verovatnoca_uspeha": 95, "preporucene_akcije": []}

    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, return_value=_twin_cc(readiness_status="BLOCKED")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(poisoned)
        mock_oai_cls.return_value = mock_oai

        result = await sta_ako_analiza(
            StaAkoRequest(predmet_id="pred-1", hipoteza="Sta ako se pojavi novi dokaz"), _twin_req(), _twin_user(),
        )

    assert result["nova_verovatnoca_uspeha"] == 65


@pytest.mark.anyio
async def test_digital_twin_degrades_gracefully_without_case_context():
    """build_case_context() failing must not break either endpoint --
    fail-soft, same discipline as every other Tau/Lambda migration."""
    from routers.digital_twin import kreiraj_simulaciju, SimulacijaRequest

    payload = {
        "scenariji": [{"naziv": "Optimisticki", "verovatnoca": 90, "opis": "x", "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 6}],
        "kljucne_tacke": [], "optimalna_strategija": "x",
    }

    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, side_effect=Exception("db down")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(payload)
        mock_oai_cls.return_value = mock_oai

        result = await kreiraj_simulaciju(
            SimulacijaRequest(predmet_id="pred-1"), _twin_req(), _twin_user(),
        )

    assert result["scenariji"][0]["verovatnoca"] == 90  # uncapped, no context available


# ═══════════════════════════════════════════════════════════════════════════
# UX/Product Auditor — the 2 top-bar "new case" buttons had near-identical
# tooltip promises (both claimed automatic extraction from a document)
# ═══════════════════════════════════════════════════════════════════════════

def test_new_case_buttons_have_distinct_not_near_duplicate_tooltips():
    """Both buttons previously promised near-identical 'automatic extraction
    from a document' language with nothing explaining which to prefer -- a
    real first-action confusion risk for a new beta lawyer. Proves the fix:
    the 2 tooltip strings are no longer near-duplicates of each other."""
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    html = open(os.path.join(repo_root, "index.html"), encoding="utf-8").read()

    idx_novi = html.index('onclick="intakeOtvori()" title="')
    title_novi = html[idx_novi:html.index('"', idx_novi + len('onclick="intakeOtvori()" title="'))]

    idx_iz_dok = html.index('onclick="siOtvori()" title="')
    title_iz_dok = html[idx_iz_dok:html.index('"', idx_iz_dok + len('onclick="siOtvori()" title="'))]

    # Neither tooltip is empty, and they no longer share the same core claim
    # (the old bug: both said some variant of "automatski prepoznaje/popunjava").
    assert title_novi and title_iz_dok
    assert title_novi != title_iz_dok
    # The old shared phrase that made both buttons read as doing the same thing.
    shared_old_phrase = "automatski"
    novi_has_it = shared_old_phrase in title_novi.lower()
    iz_dok_has_it = shared_old_phrase in title_iz_dok.lower()
    # Not BOTH may lead with the identical "automatic" framing as their own
    # first distinguishing claim -- at least one must frame itself
    # differently (manual/guided vs. fastest/document-first).
    assert not (novi_has_it and iz_dok_has_it and "vodič" not in title_novi.lower() and "najbrži" not in title_iz_dok.lower())


def test_sw_cache_bumped_for_this_sprints_frontend_change():
    """Project-standing rule: static/sw.js's own CACHE_NAME must grow on
    every frontend deploy, or users silently keep the old, confusing
    tooltip text cached."""
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    sw = open(os.path.join(repo_root, "static", "sw.js"), encoding="utf-8").read()
    import re
    m = re.search(r'CACHE_NAME\s*=\s*"vindex-v(\d+)"', sw)
    assert m is not None
    assert int(m.group(1)) >= 92
