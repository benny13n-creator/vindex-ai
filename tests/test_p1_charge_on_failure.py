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

    # BETA-P1-COLUMN-DRIFT-007 (2026-08-14): this used to assert the literal
    # source text `v == "greška"`. That pinned the MECHANISM, not the contract,
    # and it blocked a strictly safer implementation: completeness is now
    # derived from `v != "ok"`, so ANY non-ok layer state (not just the one
    # spelling enumerated here) degrades the check. Fail-closed by
    # construction instead of by enumeration.
    #
    # Replaced with the behaviour the docstring actually describes: a downed
    # layer must never render as "clear". Driven through the real handler.
    import asyncio
    from unittest.mock import MagicMock, patch

    class _LayerDown:
        def table(self, name):
            q = MagicMock()
            if name == "klijenti":
                q.select.return_value.eq.return_value.execute.side_effect = \
                    RuntimeError("database outage")
            else:
                q.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return q

    async def _no_charge(*a, **k):
        return None

    with patch.object(cc, "_get_supa", return_value=_LayerDown()), \
         patch.object(cc.UsageService, "consume", new=_no_charge):
        r = asyncio.run(cc.check_conflict(
            cc.ConflictReq(ime_prezime="Petar Petrović"),
            {"user_id": "u1", "email": "a@a.rs"}))

    assert r["provera_potpuna"] is False, "a downed layer was reported as a complete check"
    assert r["status"] != "clear", "a downed layer rendered as 'no conflict found'"
    assert "klijenti" in r["slojevi_greska"]

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


# ── P1-A: idempotency / double-charge ──────────────────────────────────────

def test_job_dedupe_returns_the_running_job_instead_of_starting_a_second():
    """/kompletna-analiza answers 202 instantly and charges 6 credits from
    inside the background task once the work finishes. A double-click or any
    client retry of that 202 started a SECOND full analysis and billed a second
    6 credits for one lawyer action."""
    import routers.jobs as jobs
    jobs._jobs.clear()

    jid1, reused1 = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")
    jid2, reused2 = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")

    assert reused1 is False and reused2 is True
    assert jid1 == jid2, "an identical in-flight request must not start a second job"
    assert len(jobs._jobs) == 1


def test_job_dedupe_does_not_suppress_a_genuinely_different_request():
    """The key is the request content. A different analysis must always run."""
    import routers.jobs as jobs
    jobs._jobs.clear()

    jid1, _ = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")
    jid2, reused = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="different")

    assert reused is False
    assert jid1 != jid2


def test_job_dedupe_is_scoped_to_one_user():
    import routers.jobs as jobs
    jobs._jobs.clear()

    jid1, _ = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")
    jid2, reused = jobs.create_job_deduped("u2", "kompletna_analiza", dedupe_key="abc")

    assert reused is False, "one lawyer's request must never be served another's job"
    assert jid1 != jid2


def test_job_dedupe_releases_once_the_job_finished():
    """Dedupe covers an in-flight duplicate, not "never run this again". Once
    the analysis is delivered, asking for it a second time is a real request."""
    import routers.jobs as jobs
    jobs._jobs.clear()

    jid1, _ = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")
    jobs.update_job(jid1, "done", result={"ok": True})

    jid2, reused = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="abc")
    assert reused is False and jid2 != jid1


def test_create_job_without_a_key_never_dedupes():
    """No regression for the callers that pass no key (outcome_intel, batch)."""
    import routers.jobs as jobs
    jobs._jobs.clear()

    a = jobs.create_job("u1", "outcome_intel")
    b = jobs.create_job("u1", "outcome_intel")
    assert a != b and isinstance(a, str)


@pytest.mark.anyio
async def test_pipeline_idempotency_key_replays_without_charging_again():
    """Every pipeline step charges as it runs, so re-submitting after a timeout
    or a dropped connection bills the completed steps a second time."""
    from unittest.mock import MagicMock, patch
    import routers.multi_agent as ma
    ma._PIPELINE_RESULTS.clear()

    calls = {"n": 0}

    async def _count_calls(inner_req, request, user):
        calls["n"] += 1
        return {"odgovor": f"korak {calls['n']}", "rag_korišćen": False}

    body = ma.PipelineReq(opis="Spor", pipeline=["intake", "research"],
                          predmet_id=None, idempotency_key="req-42")
    user = {"user_id": "u1", "email": "a@b.rs"}

    with patch.object(ma, "run_agent", new=_count_calls), \
         patch.object(ma, "_get_supa", return_value=MagicMock()):
        first  = await ma.run_pipeline(body, _real_request(), user)
        second = await ma.run_pipeline(body, _real_request(), user)

    assert calls["n"] == 2, "the retry must not re-run (and re-charge) any agent"
    assert first["rezultati"] == second["rezultati"]
    assert first["iz_kesa"] is False and second["iz_kesa"] is True


@pytest.mark.anyio
async def test_pipeline_without_a_key_behaves_exactly_as_before():
    """Opt-in on purpose: the server cannot tell an accidental retry from a
    lawyer deliberately re-running the same analysis, and guessing wrong there
    silently withholds work someone asked for."""
    from unittest.mock import MagicMock, patch
    import routers.multi_agent as ma
    ma._PIPELINE_RESULTS.clear()

    calls = {"n": 0}

    async def _count_calls(inner_req, request, user):
        calls["n"] += 1
        return {"odgovor": "ok", "rag_korišćen": False}

    body = ma.PipelineReq(opis="Spor", pipeline=["intake"], predmet_id=None)
    user = {"user_id": "u1", "email": "a@b.rs"}

    with patch.object(ma, "run_agent", new=_count_calls), \
         patch.object(ma, "_get_supa", return_value=MagicMock()):
        await ma.run_pipeline(body, _real_request(), user)
        await ma.run_pipeline(body, _real_request(), user)

    assert calls["n"] == 2, "without a key both runs must execute"


@pytest.mark.anyio
async def test_pipeline_replays_an_interrupted_run_too():
    """Those steps were charged. A retry must not pay for them twice just
    because the pipeline stopped early."""
    from fastapi import HTTPException
    from unittest.mock import MagicMock, patch
    import routers.multi_agent as ma
    ma._PIPELINE_RESULTS.clear()

    calls = {"n": 0}

    async def _fail_second(inner_req, request, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"odgovor": "prvi korak", "rag_korišćen": False}
        raise HTTPException(status_code=402, detail={"code": "NO_CREDITS"})

    body = ma.PipelineReq(opis="Spor", pipeline=["intake", "research"],
                          predmet_id=None, idempotency_key="req-99")
    user = {"user_id": "u1", "email": "a@b.rs"}

    with patch.object(ma, "run_agent", new=_fail_second), \
         patch.object(ma, "_get_supa", return_value=MagicMock()):
        first  = await ma.run_pipeline(body, _real_request(), user)
        second = await ma.run_pipeline(body, _real_request(), user)

    assert calls["n"] == 2, "the interrupted run must not be re-executed"
    assert second["iz_kesa"] is True
    assert second["kompletan"] is False
    assert second["prekid"]["status"] == 402


@pytest.mark.anyio
async def test_kompletna_analiza_double_submit_schedules_the_work_once():
    """Wiring test, not a helper test. create_job_deduped returning `reused`
    only helps if the endpoint acts on it -- scheduling the background task on
    a reuse would run (and charge) the analysis twice while both callers polled
    the same job id, which is worse than no dedupe at all."""
    from unittest.mock import MagicMock, patch
    import routers.jobs as jobs
    import routers.strategija as st
    jobs._jobs.clear()

    body = st.OrkestratorRequest(opis_predmeta="A" * 120)
    user = {"user_id": "u1", "email": "a@b.rs"}
    bt = MagicMock()

    # Wave 6: ruta sada radi pre-flight proveru bilansa PRE nego što pokrene 8
    # GPT-4o poziva. Ovi testovi mere DEDUPE i ožičenje, ne kredite — dovoljan
    # bilans je preduslov, ne predmet merenja. Dodavanje preduslova nije
    # slabljenje testa; bez njega bi merili 402 umesto dedupe-a.
    with patch.object(st, "_audit", new=lambda *a, **k: _noop()), \
         patch("shared.deps._get_credits", return_value=999), \
         patch.object(st, "_audit_strategija_durably", MagicMock()):
        r1 = await st.post_kompletna_analiza(body, _real_request("/strategija/kompletna-analiza"), bt, user)
        r2 = await st.post_kompletna_analiza(body, _real_request("/strategija/kompletna-analiza"), bt, user)

    import json
    j1 = json.loads(r1.body); j2 = json.loads(r2.body)
    assert j1["job_id"] == j2["job_id"], "the duplicate submit must join the running job"
    assert j1["vec_u_toku"] is False and j2["vec_u_toku"] is True
    assert bt.add_task.call_count == 1, (
        "the analysis must be scheduled once — scheduling it twice charges twice"
    )


async def _noop():
    return None


@pytest.mark.anyio
async def test_kompletna_analiza_different_input_still_runs():
    from unittest.mock import MagicMock, patch
    import routers.jobs as jobs
    import routers.strategija as st
    jobs._jobs.clear()

    user = {"user_id": "u1", "email": "a@b.rs"}
    bt = MagicMock()

    # Wave 6: ruta sada radi pre-flight proveru bilansa PRE nego što pokrene 8
    # GPT-4o poziva. Ovi testovi mere DEDUPE i ožičenje, ne kredite — dovoljan
    # bilans je preduslov, ne predmet merenja. Dodavanje preduslova nije
    # slabljenje testa; bez njega bi merili 402 umesto dedupe-a.
    with patch.object(st, "_audit", new=lambda *a, **k: _noop()), \
         patch("shared.deps._get_credits", return_value=999), \
         patch.object(st, "_audit_strategija_durably", MagicMock()):
        await st.post_kompletna_analiza(
            st.OrkestratorRequest(opis_predmeta="A" * 120),
            _real_request("/strategija/kompletna-analiza"), bt, user)
        await st.post_kompletna_analiza(
            st.OrkestratorRequest(opis_predmeta="B" * 120),
            _real_request("/strategija/kompletna-analiza"), bt, user)

    assert bt.add_task.call_count == 2, "a genuinely different analysis must never be suppressed"
