# -*- coding: utf-8 -*-
"""
P1 hardening — charge-on-failure violations (second-order audit, 2026-08-08).

The canonical contract in this codebase is CHARGE-FOR-A-DELIVERED-RESULT, not
charge-for-an-attempt. Evidence, all pre-existing:
  routers/drafting.py:628-634   the unconditional charge was filed as a defect and gated
  api.py:5049-5060              total failure refunds; partial success intentionally does not
  routers/evidence.py:479-480   returns before charging, tells the user "kredit nije naplaćen"
  shared/usage.py               refund() exists solely as the compensating half

These pin the three highest-severity violations fixed in this pass.
"""
import ast
import inspect
import os
import sys

import pytest
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _real_request(path="/api/multi-agent/pipeline"):
    """slowapi's @limiter.limit rejects anything that is not a genuine
    starlette Request, so these handlers cannot be driven with a MagicMock."""
    from unittest.mock import MagicMock
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": path, "client": ("127.0.0.1", 1234),
        "app": MagicMock(), "state": MagicMock(),
    })


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── SOA2-006: conflict_check false "clear" — SAFETY, not just billing ───────

def test_conflict_check_cannot_report_clear_when_a_search_layer_failed():
    """All three search layers swallow exceptions into sloj_status[...]="greška"
    and simply contribute no hits. With every layer down, `konflikti` was empty
    for the same reason it is empty when there genuinely is no conflict — and
    the endpoint told the lawyer "Nije pronađen konflikt interesa. Možete
    prihvatiti klijenta."

    A database outage therefore produced a professional-ethics FALSE CLEAR on
    the one question the Kodeks makes the lawyer personally answerable for.
    "No evidence of a conflict" and "we could not look" must never render as
    the same answer."""
    import routers.conflict_check as cc

    src = inspect.getsource(cc)
    assert '_provera_potpuna' in src
    assert 'v == "greška"' in src, "must derive completeness from the layer statuses"

    # The clear branch must be reachable only when the check actually ran.
    clear_idx = src.index('final_status = "clear"')
    guard_idx = src.index("if not konflikti and not _provera_potpuna:")
    assert guard_idx < clear_idx, (
        "the incomplete-check branch must be evaluated BEFORE the clear branch"
    )


def test_conflict_check_does_not_charge_for_an_incomplete_check():
    import routers.conflict_check as cc

    src = inspect.getsource(cc)
    consume_idx = src.index('UsageService.consume(uid, user.get("email", ""), "conflict_check")')
    # Executable lines only, so the explanatory comment block cannot satisfy it.
    preceding = "\n".join(
        l for l in src[:consume_idx].splitlines() if not l.lstrip().startswith("#")
    )
    # The guard must be the statement immediately governing the charge — i.e.
    # the last executable line before it, modulo the `await ` it sits on.
    assert preceding.rstrip().endswith("if _provera_potpuna:\n        await"), (
        "the conflict_check charge must be gated on the check having actually run; "
        f"instead it is preceded by: ...{preceding.rstrip()[-160:]!r}"
    )


def test_conflict_check_exposes_completeness_to_the_caller():
    """The frontend and the lawyer must be able to tell the two cases apart."""
    import routers.conflict_check as cc

    src = inspect.getsource(cc)
    assert '"provera_potpuna": _provera_potpuna' in src
    assert '"slojevi_greska":  _slojevi_greska' in src


# ── SOA2-004: /api/dokument/pitanje charged for "the system is busy" ────────

def test_dokument_pitanje_does_not_charge_on_agent_error():
    """ask_agent never raises — a provider failure returns
    {"status":"error","message":"Sistem je trenutno zauzet..."}. The predicate
    was already computed three lines above the charge and used only to decide
    whether to write an audit row; the charge itself ran unconditionally."""
    import routers.dokument as dok

    src = inspect.getsource(dok.dokument_pitanje)
    err_gate = src.index('rezultat.get("status") == "error"')
    charge = src.index('UsageService.consume(user["user_id"]')
    assert err_gate < charge, "the error gate must precede the charge"
    between = src[err_gate:charge]
    assert "return rezultat" in between, "an errored result must return before charging"


# ── SOA2-001: multi_agent charged per agent ATTEMPTED, not delivered ────────

def test_multi_agent_charges_only_for_agents_that_succeeded():
    """_pozovi_agenta swallows every exception into {"greska": ...}, so
    gather() always succeeds and the charge used multiplier=n_needed — the
    number of agents attempted. With the provider down the lawyer paid 3
    credits for three empty answers, and this file has no refund path."""
    import routers.multi_agent as ma

    src = inspect.getsource(ma)
    executable = "\n".join(
        l for l in src.splitlines() if not l.lstrip().startswith("#")
    )
    assert "_uspesni = [r for r in rezultati" in executable
    assert 'not r.get("greska")' in executable
    assert "multiplier=len(_uspesni)" in executable, "must charge for delivered agents only"
    assert "multiplier=n_needed" not in executable, "the attempted-count charge must be gone"

    # And a total failure must charge nothing at all.
    idx = executable.index("_uspesni = [r for r in rezultati")
    tail = executable[idx:idx + 800]
    assert "if _uspesni:" in tail
    assert "else:" in tail


# ── SOA2-A1: frontend must not silently re-POST a charged request ───────────

def _vindex_js():
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "static" / "vindex.js").read_text(encoding="utf-8")


def test_frontend_does_not_auto_retry_charged_posts():
    """execQuery posts to /api/pitanje, /api/nacrt, /api/podnesak, /api/analiza
    — all of which charge credits, none of which has an idempotency key. It
    auto-retried the identical body up to twice on 502/503 or a non-JSON body,
    so one lawyer action could be billed up to three times.

    A 502 does not mean the backend stopped: gunicorn's worker timeout (120s)
    and graceful_timeout (30s) both surface as 502 while the request has
    already been charged."""
    js = _vindex_js()
    body = js.split("async function execQuery(", 1)[1][:14000]

    assert "_attempt++" not in body, (
        "execQuery must not auto-retry — every endpoint it posts to charges credits"
    )
    assert "r.status === 502 || r.status === 503" in body, "the 502/503 branch must still be handled"
    assert "naplaćeni dvaput" in body or "naplaćen" in body, (
        "the user must be told the request may already have been charged"
    )


def test_frontend_still_handles_the_non_retry_status_codes():
    """No regression: 401/402/403/429 handling must survive the retry removal."""
    js = _vindex_js()
    body = js.split("async function execQuery(", 1)[1][:14000]
    for marker in ("r.status === 401", "r.status === 402", "r.status === 403", "r.status === 429"):
        assert marker in body, f"{marker} handling lost"
    assert "showPaywall()" in body, "402 must still open the paywall"


# ── P1-A2: /multi-agent/pipeline discarded already-paid steps ───────────────

@pytest.mark.anyio
async def test_pipeline_returns_paid_steps_when_a_later_step_is_rejected():
    """run_agent() charges as each step runs. The handler's `except
    HTTPException: raise` therefore threw away finished, already-billed steps
    whenever step 2+ hit a 402/429 — the lawyer paid for step 1 and received
    nothing at all. Charged-and-delivered-nothing is the one outcome this
    codebase refunds for everywhere else."""
    from fastapi import HTTPException
    from unittest.mock import AsyncMock, MagicMock, patch
    import routers.multi_agent as ma

    calls = {"n": 0}

    async def _fake_run_agent(inner_req, request, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"odgovor": "Analiza prvog koraka.", "rag_korišćen": False}
        raise HTTPException(status_code=402, detail={"code": "NO_CREDITS"})

    body = ma.PipelineReq(opis="Spor oko ugovora", pipeline=["intake", "research"], predmet_id=None)
    user = {"user_id": "u1", "email": "a@b.rs"}

    with patch.object(ma, "run_agent", new=_fake_run_agent), \
         patch.object(ma, "_get_supa", return_value=MagicMock()):
        out = await ma.run_pipeline(body, _real_request(), user)

    # The paid step survives.
    assert out["koraci"] == 2
    assert out["rezultati"][0]["output"] == "Analiza prvog koraka."
    assert not out["rezultati"][0].get("greska")

    # And the caller can still see it was cut short, and why.
    assert out["kompletan"] is False
    assert out["prekid"]["status"] == 402
    assert out["prekid"]["korak"] == 2


@pytest.mark.anyio
async def test_pipeline_still_raises_when_the_first_step_is_rejected():
    """No regression: nothing has been charged yet at step 1, so propagating
    the 402 is correct — an empty 200 would hide the paywall from the client."""
    from fastapi import HTTPException
    from unittest.mock import MagicMock, patch
    import routers.multi_agent as ma

    async def _always_402(inner_req, request, user):
        raise HTTPException(status_code=402, detail={"code": "NO_CREDITS"})

    body = ma.PipelineReq(opis="Spor", pipeline=["intake", "research"], predmet_id=None)

    with patch.object(ma, "run_agent", new=_always_402), \
         patch.object(ma, "_get_supa", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await ma.run_pipeline(body, _real_request(), {"user_id": "u1", "email": "a@b.rs"})

    assert exc.value.status_code == 402


@pytest.mark.anyio
async def test_pipeline_kompletan_is_false_when_the_last_step_fails():
    """`kompletan` must not be derived from the step COUNT alone: a failure on
    the final step still produces len(results) == len(pipeline)."""
    from unittest.mock import MagicMock, patch
    import routers.multi_agent as ma

    calls = {"n": 0}

    async def _fail_last(inner_req, request, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"odgovor": "ok", "rag_korišćen": False}
        raise RuntimeError("provider down")

    body = ma.PipelineReq(opis="Spor", pipeline=["intake", "research"], predmet_id=None)

    with patch.object(ma, "run_agent", new=_fail_last), \
         patch.object(ma, "_get_supa", return_value=MagicMock()), \
         patch.object(ma, "_sentry_capture", MagicMock()):
        out = await ma.run_pipeline(body, _real_request(), {"user_id": "u1", "email": "a@b.rs"})

    assert len(out["rezultati"]) == len(body.pipeline)
    assert out["kompletan"] is False
