# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 014 -- CIO Portfolio Truncation Disclosure.
Closes LIVINGSYS-DEBT-003 (CRITICAL) via the disclosure-only sub-fix: the
40-case cap and its oldest-first ordering are UNCHANGED (both require a
founder decision -- perf tradeoff at scale, and which cases should represent
a truncated portfolio -- neither attempted here); this mission closes the
"presented as the true total with zero signal it's truncated" gap.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

UID = "aaaa0000-0000-0000-0000-000000000001"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _predmet_row(pid, days_stale=1):
    upd = (datetime.now(timezone.utc) - timedelta(days=days_stale)).isoformat()
    return {"id": pid, "naziv": "Test predmet", "oblast_prava": "Parnično", "updated_at": upd,
            "case_dna": {"verzija": 3, "strategija": {}, "strategija_osnova": "", "zakljucak": ""}}


def _oai_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    return resp


_BASE_GPT_JSON = {
    "cio_preporuka": "Nastavite dalje.",
    "najveci_rizik": None, "najveca_prilika": None, "zapostavljen_predmet": None,
    "neprimecena_kontradikcija": None, "kriticni_rok": None, "suboptimalna_strategija": None,
    "slicni_predmet": None, "cio_zakljucak": "Portfolio je stabilan.", "pouzdanost": "srednja",
}


def _make_supa_with_count(predmeti_rows, total_count, count_raises=False, pred_raises=False):
    """Distinguishes the new count-only query (select("id", count="exact")) from
    the main select by inspecting the call kwargs -- the pre-existing _make_supa
    helper in test_tau008_cio_consolidation.py can't do this (it returns the
    same response object regardless of select() args), which is exactly why a
    dedicated helper is needed to actually prove the disclosure logic."""
    supa = MagicMock()

    def _table(name):
        chain = MagicMock()

        def _select(*args, **kwargs):
            inner = MagicMock()
            for attr in ["eq", "in_", "order", "limit"]:
                setattr(inner, attr, MagicMock(return_value=inner))

            def _execute():
                if name == "predmeti" and kwargs.get("count") == "exact":
                    if count_raises:
                        raise Exception("count query boom")
                    r = MagicMock()
                    r.data = predmeti_rows[:1]
                    r.count = total_count
                    return r
                if name == "predmeti":
                    if pred_raises:
                        raise Exception("pred query boom")
                    r = MagicMock()
                    r.data = predmeti_rows
                    r.count = None
                    return r
                r = MagicMock()
                r.data = []
                return r
            inner.execute = MagicMock(side_effect=_execute)
            return inner
        chain.select = MagicMock(side_effect=_select)
        return chain

    supa.table = MagicMock(side_effect=_table)
    return supa


@pytest.mark.anyio
async def test_cio_report_discloses_no_truncation_when_under_cap():
    from routers import cio as cio_mod

    supa = _make_supa_with_count([_predmet_row("p1")], total_count=1)

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value={
        "readiness": {"value": {"status": "READY", "razlog": "", "izvor": []}},
        "key_facts": {"value": {"pravna_teorija": {}, "snaga_predmeta_procent": 60, "najslabija_tacka": {}}},
        "missing_evidence": {"value": []}, "contradictions": {"value": []},
        "deadlines": {"value": []}, "active_actions": {"value": []},
    })), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["portfolio_zdravlje"]["truncated"] is False
    assert result["portfolio_zdravlje"]["ukupno_u_bazi"] == 1


@pytest.mark.anyio
async def test_cio_report_discloses_truncation_when_over_cap():
    """Original-scenario reproduction: more active cases exist than the 40-case
    cap returns -- the report must disclose this, not silently present the
    capped sample as the whole portfolio."""
    from routers import cio as cio_mod

    supa = _make_supa_with_count([_predmet_row("p1")], total_count=57)

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value={
        "readiness": {"value": {"status": "READY", "razlog": "", "izvor": []}},
        "key_facts": {"value": {"pravna_teorija": {}, "snaga_predmeta_procent": 60, "najslabija_tacka": {}}},
        "missing_evidence": {"value": []}, "contradictions": {"value": []},
        "deadlines": {"value": []}, "active_actions": {"value": []},
    })), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["portfolio_zdravlje"]["truncated"] is True
    assert result["portfolio_zdravlje"]["ukupno_u_bazi"] == 57
    assert result["portfolio_zdravlje"]["ukupno_aktivnih"] == 1


@pytest.mark.anyio
async def test_cio_report_count_query_failure_fails_soft():
    """The count query is a disclosure nice-to-have, not core data -- its own
    failure must not take down the whole report."""
    from routers import cio as cio_mod

    supa = _make_supa_with_count([_predmet_row("p1")], total_count=57, count_raises=True)

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value={
        "readiness": {"value": {"status": "READY", "razlog": "", "izvor": []}},
        "key_facts": {"value": {"pravna_teorija": {}, "snaga_predmeta_procent": 60, "najslabija_tacka": {}}},
        "missing_evidence": {"value": []}, "contradictions": {"value": []},
        "deadlines": {"value": []}, "active_actions": {"value": []},
    })), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["predmeta_analizirano"] == 1
    assert result["portfolio_zdravlje"]["truncated"] is False  # unknown -- fails safe, not blind


@pytest.mark.anyio
async def test_cio_report_pred_query_failure_still_propagates():
    """Regression guard: the CORE predmeti fetch must keep its original
    fail-hard behavior -- a real DB error here must still raise (becoming the
    caller's existing 500), never be silently reinterpreted as '0 active
    cases' the way count_r's own failure now safely is."""
    from routers import cio as cio_mod

    supa = _make_supa_with_count([_predmet_row("p1")], total_count=1, pred_raises=True)

    with pytest.raises(Exception, match="pred query boom"):
        await cio_mod._generiši_cio_izvestaj(UID, supa)


@pytest.mark.anyio
async def test_empty_portfolio_path_also_discloses_truncation():
    """The early-return 'no portfolio with a Genome model' branch must also
    carry the disclosure fields, not just the main return path."""
    from routers import cio as cio_mod

    # 1 predmet fetched but with no case_dna -> _kompaktan_predmet excludes it,
    # portfolio ends up empty, triggering the early-return branch.
    row = _predmet_row("p1")
    row["case_dna"] = None
    supa = _make_supa_with_count([row], total_count=12)

    with patch("openai.AsyncOpenAI"):
        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["predmeta_analizirano"] == 0
    assert result["portfolio_zdravlje"]["ukupno_u_bazi"] == 12
    assert result["portfolio_zdravlje"]["truncated"] is True


def test_frontend_discloses_truncation_in_cio_widget():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    assert "if (pg.truncated)" in vindex_js
    assert "pg.ukupno_u_bazi" in vindex_js
