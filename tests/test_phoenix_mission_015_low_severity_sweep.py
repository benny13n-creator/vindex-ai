# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 015 -- Low-Severity Debt Sweep.
Closes LIVINGSYS-DEBT-018, -019, -024, -029, -031, -032, plus 2 items from the
consolidated -056 through -063 bucket (Timeline + Health Index silent-failure
disclosure). See docs/phoenix/mission-015/ for the full reconstruction and
disposition of every item in scope, including those explicitly deferred.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequestImport

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequestImport(scope=scope, receive=receive)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-018 -- notifications frontend read fields the backend never
# sent (datum/predmet_naziv always empty).
# ═══════════════════════════════════════════════════════════════════════════

def test_notif_helpers_present_and_used_instead_of_missing_fields():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    assert "function _notifDatumBadge(n) {" in vindex_js
    assert "function _notifPredmetNaziv(n) {" in vindex_js
    assert "_notifDatumBadge(n)" in vindex_js
    assert "_notifPredmetNaziv(n)" in vindex_js
    # Regression: the old direct (always-empty) field reads must be gone from
    # the render call sites, not just supplemented.
    assert "escHtml((n.datum||'').slice(5))" not in vindex_js


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-019 -- CIO's zero-case empty-state message worded for the
# wrong empty state.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_cio_report_zero_cases_gets_distinct_message_from_zero_genome():
    from routers import cio as cio_mod

    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            def _select(*a, **k):
                inner = MagicMock()
                for attr in ["eq", "in_", "order", "limit"]:
                    setattr(inner, attr, MagicMock(return_value=inner))
                def _execute():
                    r = MagicMock()
                    if k.get("count") == "exact":
                        r.data = []
                        r.count = 0
                    else:
                        r.data = []
                    return r
                inner.execute = MagicMock(side_effect=_execute)
                return inner
            t.select = MagicMock(side_effect=_select)
        else:
            t.select.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return t

    supa.table.side_effect = _table

    with patch("openai.AsyncOpenAI"):
        result = await cio_mod._generiši_cio_izvestaj("u1", supa)

    assert "Nemate aktivnih predmeta" in result["cio_preporuka"]
    assert "Generišite Genome" not in result["cio_preporuka"]


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-024 -- Digital Twin's readiness cap silently disabled itself
# when build_case_context() threw, leaving an uncapped probability reachable.
# ═══════════════════════════════════════════════════════════════════════════

def _twin_req():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/twin/simulacija", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequestImport(scope=scope)


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


def _twin_oai_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(message=msg)
    resp = MagicMock(choices=[choice])
    return resp


@pytest.mark.anyio
async def test_twin_simulacija_caps_conservatively_on_case_context_exception():
    """Original-scenario reproduction: build_case_context() raises -- the
    response must fail toward the conservative CRITICAL_GAP cap (50), not
    toward zero cap at all."""
    from routers.digital_twin import kreiraj_simulaciju, SimulacijaRequest

    payload = {
        "scenariji": [{"naziv": "Optimisticki", "verovatnoca": 90, "opis": "x",
                        "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 6}],
        "kljucne_tacke": [], "optimalna_strategija": "x",
    }
    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, side_effect=Exception("db down")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(payload)
        mock_oai_cls.return_value = mock_oai
        result = await kreiraj_simulaciju(SimulacijaRequest(predmet_id="pred-1"), _twin_req(), _twin_user())

    assert result["scenariji"][0]["verovatnoca"] == 50


@pytest.mark.anyio
async def test_twin_sta_ako_caps_conservatively_on_case_context_exception():
    from routers.digital_twin import sta_ako_analiza, StaAkoRequest

    payload = {"uticaj": "x", "nova_verovatnoca_uspeha": 95, "preporucene_akcije": []}
    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, side_effect=Exception("db down")), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(payload)
        mock_oai_cls.return_value = mock_oai
        result = await sta_ako_analiza(
            StaAkoRequest(predmet_id="pred-1", hipoteza="Sta ako"), _twin_req(), _twin_user(),
        )

    assert result["nova_verovatnoca_uspeha"] == 50


@pytest.mark.anyio
async def test_twin_simulacija_still_uses_real_status_cap_when_context_available():
    """Regression: normal (non-exception) path unaffected -- still uses the
    case's OWN readiness status, not the conservative fallback."""
    from routers.digital_twin import kreiraj_simulaciju, SimulacijaRequest

    payload = {
        "scenariji": [{"naziv": "Optimisticki", "verovatnoca": 90, "opis": "x",
                        "kljucni_rizici": [], "preporucene_akcije": [], "procenjeno_trajanje_meseci": 6}],
        "kljucne_tacke": [], "optimalna_strategija": "x",
    }
    cc = {"readiness": {"value": {"status": "BLOCKED", "razlog": "test", "izvor": []}}}
    with patch("routers.digital_twin._get_supa", return_value=_twin_supa()), \
         patch("routers.digital_twin.build_case_context", new_callable=AsyncMock, return_value=cc), \
         patch("routers.digital_twin.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _twin_oai_resp(payload)
        mock_oai_cls.return_value = mock_oai
        result = await kreiraj_simulaciju(SimulacijaRequest(predmet_id="pred-1"), _twin_req(), _twin_user())

    assert result["scenariji"][0]["verovatnoca"] == 65  # BLOCKED's own cap, not CRITICAL_GAP's


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-029 -- Workspace "Today" board's zadaci filter only surfaced
# status="ceka", hiding "otvoreno"/"u_toku" tasks due today.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_fetch_waiting_zadaci_includes_otvoreno_and_u_toku_not_just_ceka():
    from routers.workspace import _fetch_waiting_zadaci

    captured = {}

    def _table(name):
        assert name == "zadaci"
        t = MagicMock()
        def _select(*a, **k):
            inner = MagicMock()
            def _eq(col, val):
                captured.setdefault("eq", []).append((col, val))
                return inner
            def _not_in(col, vals):
                captured["not_in"] = (col, vals)
                return inner
            inner.eq = _eq
            inner.not_ = MagicMock(in_=_not_in)
            inner.execute = MagicMock(return_value=MagicMock(data=[
                {"id": "z1", "status": "otvoreno"}, {"id": "z2", "status": "u_toku"}, {"id": "z3", "status": "ceka"},
            ]))
            return inner
        t.select = MagicMock(side_effect=_select)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    result = await _fetch_waiting_zadaci(supa, "u1")

    assert captured["not_in"] == ("status", ["zavrseno", "otkazano"])
    assert len(result) == 3


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-031 -- no idempotency guard on staging_memory insert for
# drafting retries (double-click/network-retry duplicated the review queue).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_stage_draft_skips_duplicate_within_retry_window():
    """Original-scenario reproduction: 2 near-simultaneous stage attempts for
    the same (user, predmet, tip) -- only the first inserts."""
    import routers.drafting as dr

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"id": "p1"})
        elif name == "staging_memory":
            def _select(*a, **k):
                inner = MagicMock()
                for attr in ["eq", "gte", "limit"]:
                    setattr(inner, attr, MagicMock(return_value=inner))
                inner.execute = MagicMock(return_value=MagicMock(data=[{"id": "existing-staging-row"}]))
                return inner
            t.select = MagicMock(side_effect=_select)
            def _insert(row):
                insert_calls.append(row)
                m = MagicMock(); m.execute.return_value = MagicMock(data=[{"id": "new-row"}])
                return m
            t.insert = MagicMock(side_effect=_insert)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(dr, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await dr._stage_draft_for_review({"user_id": "u1"}, "p1", "tuzba", "Tuzba", "tekst nacrta")

    assert insert_calls == []


@pytest.mark.anyio
async def test_stage_draft_inserts_when_no_recent_duplicate():
    """Regression: the normal (first attempt) path still inserts exactly once."""
    import routers.drafting as dr

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"id": "p1"})
        elif name == "staging_memory":
            def _select(*a, **k):
                inner = MagicMock()
                for attr in ["eq", "gte", "limit"]:
                    setattr(inner, attr, MagicMock(return_value=inner))
                inner.execute = MagicMock(return_value=MagicMock(data=[]))
                return inner
            t.select = MagicMock(side_effect=_select)
            def _insert(row):
                insert_calls.append(row)
                m = MagicMock(); m.execute.return_value = MagicMock(data=[{"id": "new-row"}])
                return m
            t.insert = MagicMock(side_effect=_insert)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(dr, "_get_supa", return_value=supa), \
         patch("services.quality_gate.evaluate_draft_quality", new=AsyncMock(return_value={"confidence_score": 0.5, "detail": {}})), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await dr._stage_draft_for_review({"user_id": "u1"}, "p1", "tuzba", "Tuzba", "tekst nacrta")

    assert len(insert_calls) == 1


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-032 -- Service Worker's offline:true flag was dead code.
# ═══════════════════════════════════════════════════════════════════════════

def test_sw_no_longer_sets_dead_offline_flag():
    sw_js = open(os.path.join(REPO_ROOT, "static", "sw.js"), encoding="utf-8").read()
    assert "offline: true" not in sw_js
    assert '"Nema internet konekcije."' in sw_js  # the actually-used field stays


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-056-063 (category: Timeline per-source silent failure)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_intelligence_timeline_discloses_degraded_source():
    """Original-scenario reproduction: the rocista query fails -- the response
    must disclose it, not render an indistinguishable-from-empty Timeline."""
    from routers import intelligence_timeline as itl

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "p1", "naziv": "Test", "status": "aktivan", "oblast": "x", "tip": "y",
                       "created_at": "2026-01-01T00:00:00", "case_dna": {}}]
            )
        elif name == "rocista":
            raise Exception("rocista query boom")
        else:
            chain = MagicMock()
            for attr in ["eq", "order", "in_"]:
                setattr(chain, attr, MagicMock(return_value=chain))
            chain.execute = MagicMock(return_value=MagicMock(data=[]))
            t.select = MagicMock(return_value=chain)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(itl, "_get_supa", return_value=supa):
        result = await itl.intelligence_timeline("p1", user={"user_id": "u1"})

    assert "rocista" in result["degraded_sources"]


@pytest.mark.anyio
async def test_intelligence_timeline_no_degraded_sources_on_full_success():
    """Regression: normal (all-succeed) path reports an empty degraded_sources
    list, matching the pre-mission response shape plus the new field."""
    from routers import intelligence_timeline as itl

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "p1", "naziv": "Test", "status": "aktivan", "oblast": "x", "tip": "y",
                       "created_at": "2026-01-01T00:00:00", "case_dna": {}}]
            )
        else:
            chain = MagicMock()
            for attr in ["eq", "order", "in_"]:
                setattr(chain, attr, MagicMock(return_value=chain))
            chain.execute = MagicMock(return_value=MagicMock(data=[]))
            t.select = MagicMock(return_value=chain)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(itl, "_get_supa", return_value=supa):
        result = await itl.intelligence_timeline("p1", user={"user_id": "u1"})

    assert result["degraded_sources"] == []


def test_timeline_frontend_shows_degraded_warning():
    vindex_js = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    assert "d.degraded_sources" in vindex_js


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-056-063 (category: Health Index weak-signals silent failure)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_weak_signals_discloses_degraded_ishod_query():
    """Original-scenario reproduction: the outcome (ishod) query fails -- the
    'bad pattern by case type' signal must not silently report 0% forever;
    a disclosure signal takes its place."""
    from routers.health_index import _compute_weak_signals

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            closed = [{"id": f"p{i}", "naziv": "x", "tip": "parnica", "oblast": "x",
                       "status": "zatvoren", "case_dna": {}, "created_at": "2026-01-01"} for i in range(9)]
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=closed)
        elif name == "predmet_hronologija":
            chain = MagicMock()
            for attr in ["in_", "eq", "ilike", "order"]:
                setattr(chain, attr, MagicMock(return_value=chain))
            chain.execute = MagicMock(side_effect=Exception("hronologija query boom"))
            t.select = MagicMock(return_value=chain)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    result = await _compute_weak_signals("u1", supa)

    assert any("nije dostupna" in s["tekst"] for s in result)


@pytest.mark.anyio
async def test_weak_signals_no_disclosure_when_ishod_query_succeeds():
    """Regression: the normal (successful) path never shows the disclosure
    signal."""
    from routers.health_index import _compute_weak_signals

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            closed = [{"id": f"p{i}", "naziv": "x", "tip": "parnica", "oblast": "x",
                       "status": "zatvoren", "case_dna": {}, "created_at": "2026-01-01"} for i in range(9)]
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=closed)
        elif name == "predmet_hronologija":
            chain = MagicMock()
            for attr in ["in_", "eq", "ilike", "order"]:
                setattr(chain, attr, MagicMock(return_value=chain))
            chain.execute = MagicMock(return_value=MagicMock(data=[]))
            t.select = MagicMock(return_value=chain)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    result = await _compute_weak_signals("u1", supa)

    assert not any("nije dostupna" in s["tekst"] for s in result)
