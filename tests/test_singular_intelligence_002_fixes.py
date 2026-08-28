# -*- coding: utf-8 -*-
"""
Operation Singular Intelligence, Mission 002 -- regression coverage for the 8-team forensic pass
(each team read-only, investigating from zero). Each test proves a specific reproduced
contradiction is closed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
VINDEX_JS = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
# Fix 1 (Team 4 + Team 7, confirmed independently): "kljucan"/"info" missing
# from VAZNOST_TO_CANONICAL -- see test_omega_sprint006_canonical_attention.py
# for the exact-dict-literal proof. This file adds the behavioral proof.
# ═══════════════════════════════════════════════════════════════════════════

def test_kljucan_now_counts_as_critical_client_facing_deadline():
    from shared.attention_priority import VAZNOST_TO_CANONICAL, CRITICAL, INFORMATIONAL
    assert VAZNOST_TO_CANONICAL["kljucan"] == CRITICAL
    assert VAZNOST_TO_CANONICAL["info"] == INFORMATIONAL

    import routers.client_portal as cp
    assert "kljucan" in cp._KLIJENT_VAZNI_VAZNOST


# ═══════════════════════════════════════════════════════════════════════════
# Fix 2 (Team 7, Database Evidence Chains): 3 remaining calculate_procesni_rizik
# callers missing the deleted_at soft-delete filter (of 15+ total callers).
# Structural checks -- this repo's MagicMock-chain fixtures don't honor real
# .select()/.is_() filtering, established limitation throughout this engagement.
# ═══════════════════════════════════════════════════════════════════════════

def test_predmeti_dashboard_dokazi_query_excludes_soft_deleted():
    src = open(os.path.join(REPO_ROOT, "api.py"), encoding="utf-8").read()
    # TASK 004A: marker je LOKATOR bloka, ne predmet provere. TASK 004 je
    # `.select(...)` proširio sa `izvor_snage` (bez njega bi svaki red bio
    # neprocenjen); tvrdnja koju ovaj test štiti -- soft-delete filter -- je
    # nepromenjena i ovde se i dalje proverava nad istim blokom.
    marker = 'supa.table("predmet_dokazi")\n                .select("predmet_id,snaga,kategorija,izvor_snage")'
    block = src.split(marker, 1)[1][:200]
    assert 'is_("deleted_at", "null")' in block


def test_command_center_dokazi_query_excludes_soft_deleted():
    src = open(os.path.join(REPO_ROOT, "routers", "dashboard.py"), encoding="utf-8").read()
    # TASK 004A: isto kao gore — pomeren lokator, tvrdnja nepromenjena.
    marker = 'supa.table("predmet_dokazi")\n            .select("predmet_id,snaga,kategorija,izvor_snage")'
    block = src.split(marker, 1)[1][:200]
    assert 'is_("deleted_at", "null")' in block


def test_matter_health_score_dokazi_query_excludes_soft_deleted():
    src = open(os.path.join(REPO_ROOT, "routers", "dashboard.py"), encoding="utf-8").read()
    # TASK 004A: isto kao gore — pomeren lokator, tvrdnja nepromenjena.
    marker = 'supa.table("predmet_dokazi")\n            .select("snaga,kategorija,pravni_element,izvor_snage")'
    block = src.split(marker, 1)[1][:200]
    assert 'is_("deleted_at", "null")' in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 3 (Red Team Attack 1, reproduced): case_evolution.py's
# _consequence_case_intelligence_summary was missing tip_dokaza -- proven to
# compute "Srednji"/health=55 for identical data ccc.py/case_pipeline.py
# compute as "Nizak"/health=70 for, from the missing column alone.
# ═══════════════════════════════════════════════════════════════════════════

def test_case_intelligence_summary_selects_tip_dokaza():
    src = open(os.path.join(REPO_ROOT, "services", "case_evolution.py"), encoding="utf-8").read()
    assert 'supa.table("predmet_dokumenti").select("naziv_fajla,status,tip_dokaza").eq("predmet_id", predmet_id).execute()' in src


# ═══════════════════════════════════════════════════════════════════════════
# Fix 4 (Team 5, UI Terminology Sweep): CIO Command Center portfolio widget's
# "prosecna_snaga" (average case strength) still used the OLD 65/40 threshold
# for the same snaga_predmeta_procent field the Genome hero panel and Copilot
# were already aligned to 60/40 in Mission 001 -- a 60-64% average showed amber
# on Command Center's home page, green one click away in a case's own panel.
# ═══════════════════════════════════════════════════════════════════════════

def test_cio_portfolio_widget_strength_threshold_matches_genome_and_copilot():
    marker = "var snagaColor = (pg.prosecna_snaga||0)"
    block = VINDEX_JS.split(marker, 1)[1][:200]
    assert ">= 60" in block
    assert ">= 65" not in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 5 (Red Team Attack 4, reproduced): Health Index's "Snaga predmeta"
# component top-tier cutoff (70) disagreed with genome_validator.py's own
# canonical ">=75 -> jaka" boundary -- a 72% case scored the component's
# maximum 20/20 with zero alert, identical to a 100%/"jaka" case, while
# Genome's own page correctly showed "srednja" (medium) for the same number.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_health_index_strength_component_72_percent_no_longer_scores_maximum():
    """Direct reproduction of Red Team's Attack 4: a portfolio averaging 72% strength
    (genome_validator.py's own canonical formula would call this "srednja", not "jaka")
    must not receive the component's maximum score, which used to require only >=70."""
    from routers import health_index as hi

    preds = [{"id": "p1", "naziv": "P1", "status": "aktivan",
              "case_dna": {"snaga_predmeta_procent": 72}, "created_at": "2026-01-01", "tip": "opsti"}]

    def _chain(data):
        c = MagicMock()
        for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
                  'insert', 'update', 'delete', 'is_', 'in_', 'desc'):
            setattr(c, a, MagicMock(return_value=c))
        r = MagicMock(); r.data = data
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            return _chain(preds)
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    result = await hi._compute_health("u1", supa)
    cs_component = next(c for c in result["components"] if c["label"] == "Snaga predmeta")
    assert cs_component["score"] < 20  # no longer the maximum for a 72% ("srednja") average


def test_health_index_strength_component_thresholds_match_genome_validator():
    src = open(os.path.join(REPO_ROOT, "routers", "health_index.py"), encoding="utf-8").read()
    marker = "if not snage:"
    block = src.split(marker, 1)[1][:400]
    assert "avg >= 75" in block
    assert "avg >= 35" in block
    assert "avg >= 70" not in block
    assert "avg >= 40" not in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 6 (Team 5): Digital Twin's "Nova verovatnoća uspeha" (what-if simulator)
# rendered flat blue with no threshold coloring, unlike every sibling surface.
# ═══════════════════════════════════════════════════════════════════════════

def test_digital_twin_sta_ako_probability_now_color_coded():
    marker = "d.nova_verovatnoca_uspeha != null"
    block = VINDEX_JS.split(marker, 1)[1][:250]
    assert "#93c5fd" not in block
    assert ">=60?" in block or ">= 60 ?" in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 7 (Team 1, flagged as "worth Red Team probing", confirmed unfixed):
# client_twin.py's "pouzdanost" was GPT self-declared with no enum-guard,
# unlike every sibling confidence field already validated in this engagement.
# ═══════════════════════════════════════════════════════════════════════════

def test_client_twin_pouzdanost_is_enum_validated():
    src = open(os.path.join(REPO_ROOT, "routers", "client_twin.py"), encoding="utf-8").read()
    marker = "profil = json.loads(resp.choices[0].message.content)"
    block = src.split(marker, 1)[1][:900]
    assert 'profil["pouzdanost"] = "niska"' in block
    assert 'not in ("visoka", "srednja", "niska")' in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 8 (Team 8, Cross-Module Concurrency, REPRODUCED via isolated simulation):
# case_actions' UPDATE/CLOSE paths in _consequence_refresh_case_actions had no
# protection against a stale write overwriting a fresher concurrent write's
# decision -- a real lost-update on the platform's single source of truth.
# This is a real, stateful behavioral proof (not a structural/text check): a
# fake case_actions table that actually evaluates WHERE-clause conditions
# against current row state, simulating the exact interleaving Team 8 found.
# ═══════════════════════════════════════════════════════════════════════════

def _stateful_case_actions_supa(initial_row):
    """A fake `case_actions` table that ACTUALLY evaluates .eq() conditions against
    the row's current mutable state (unlike this repo's usual MagicMock passthrough
    fixtures) -- required to prove an optimistic-concurrency guard actually rejects
    a stale write, not just that the code calls .eq() with the right arguments."""
    rows = {initial_row["id"]: dict(initial_row)}

    class _UpdateBuilder:
        def __init__(self, payload):
            self.payload = payload
            self.filters = {}

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def execute(self):
            matched = []
            for rid, row in rows.items():
                if all(row.get(k) == v for k, v in self.filters.items()):
                    matched.append(rid)
            for rid in matched:
                rows[rid].update(self.payload)
            res = MagicMock()
            res.data = [rows[rid] for rid in matched]
            return res

    def _table(name):
        assert name == "case_actions"
        t = MagicMock()

        def _select(cols):
            sel = MagicMock()
            def _eq1(col, val):
                inner = MagicMock()
                def _eq2(col2, val2):
                    leaf = MagicMock()
                    open_rows = [r for r in rows.values() if r.get("predmet_id") == val and r.get("status") == val2]
                    leaf.execute.return_value = MagicMock(data=[
                        {"id": r["id"], "dedupe_key": r["dedupe_key"], "updated_at": r["updated_at"]} for r in open_rows
                    ])
                    return leaf
                inner.eq.side_effect = _eq2
                return inner
            sel.eq.side_effect = _eq1
            return sel
        t.select.side_effect = _select
        t.update.side_effect = lambda payload: _UpdateBuilder(payload)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, rows


@pytest.mark.anyio
async def test_case_actions_stale_close_cannot_overwrite_fresher_concurrent_update():
    """Direct reproduction of Team 8's finding: EventA's snapshot says the row is open
    with updated_at=T0 and EventA's own (stale) computation wants to CLOSE it. Before
    EventA's write reaches the DB, a concurrent EventB already UPDATEd the same row
    (bumping updated_at to T1) because EventB's fresher computation says it should stay
    open. EventA's CLOSE must now fail to match (0 rows) instead of silently closing
    a row a more recent computation just said should remain open."""
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_refresh_case_actions

    row = {"id": "row1", "predmet_id": "pred-1", "dedupe_key": "dk-critical",
           "status": "open", "updated_at": "T0", "tip": "PRIBAVITI_DOKAZ"}
    supa, rows = _stateful_case_actions_supa(row)

    # Simulate EventB's concurrent UPDATE landing between EventA's snapshot read and
    # EventA's own write -- the row is still open, but its updated_at has moved on.
    rows["row1"]["updated_at"] = "T1"

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={}, correlation_id="corr-a", event_id="evt-a")

    # EventA's own (stale) computation: target set no longer includes dk-critical ->
    # wants to CLOSE it. But its snapshot of `updated_at` (captured via the real SELECT
    # inside _consequence_refresh_case_actions, which will read the CURRENT T1 value,
    # not a pre-captured T0) -- to genuinely test the race, patch the snapshot read to
    # return the STALE T0 value while the table's real state has already moved to T1.
    stale_snapshot = [{"id": "row1", "dedupe_key": "dk-critical", "updated_at": "T0"}]

    async def _fake_target_actions(pid):
        return []  # EventA's target set omits dk-critical -> wants to close it

    with patch("services.case_evolution._compute_target_actions", new=_fake_target_actions), \
         patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        # Directly exercise the CLOSE path with the stale snapshot by monkeypatching the
        # existing_res read to return it, isolating exactly the race window in question.
        import services.case_evolution as ce
        orig_to_thread = ce.asyncio.to_thread
        call_count = {"n": 0}

        async def _patched_to_thread(fn, *a, **k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First to_thread call in the function is the existing-rows snapshot read.
                res = MagicMock()
                res.data = stale_snapshot
                return res
            return await orig_to_thread(fn, *a, **k)

        with patch.object(ce.asyncio, "to_thread", new=_patched_to_thread):
            await _consequence_refresh_case_actions(event)

    # The row must still be open with EventB's fresher data intact -- EventA's stale
    # CLOSE (guarded by .eq("updated_at","T0")) must have matched zero rows against the
    # table's real T1 state.
    assert rows["row1"]["status"] == "open"
    assert rows["row1"]["updated_at"] == "T1"


def test_case_actions_close_and_update_both_guard_on_status_open():
    src = open(os.path.join(REPO_ROOT, "services", "case_evolution.py"), encoding="utf-8").read()
    marker = 'async def _consequence_refresh_case_actions'
    block = src.split(marker, 1)[1]
    assert '.eq("id", _existing["id"]).eq("status", "open")' in block or \
           '.eq("id", aid).eq("status", "open")' in block or \
           'eq("status", "open").execute()' in block
    assert '_close_query = _close_query.eq("updated_at", _snapshot_updated_at)' in block


# ═══════════════════════════════════════════════════════════════════════════
# Fix 9 (3 teams + Red Team Attack 3, REPRODUCED): matter_intel.py::preflight_check's
# GPT-generated status answers a different question than shared/case_readiness.py's
# canonical 5-state model by design (docs/sigma/CASE_READINESS_MODEL.md) -- but the
# reproduced harm was that a case with canonical CRITICAL_GAP could get back
# "spreman" with ZERO mention of it. Now preflight_check always cross-references the
# canonical readiness deterministically when it's CRITICAL_GAP/BLOCKED, regardless of
# what the GPT itself said.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_preflight_forces_canonical_critical_gap_cross_reference():
    """Direct reproduction of Red Team Attack 3: canonical readiness says CRITICAL_GAP
    for this case, but the GPT-generated preflight response says "spreman" (ready) with
    an empty kriticna_upozorenja list -- the lawyer must still see the canonical signal."""
    import json
    from starlette.requests import Request as StarletteRequest
    import routers.matter_intel as mi

    def _req():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        scope = {"type": "http", "method": "POST", "path": "/", "headers": [],
                  "query_string": b"", "app": MagicMock(), "state": MagicMock(),
                  "client": ("127.0.0.1", 1234)}
        return StarletteRequest(scope=scope, receive=receive)

    def _chain(data):
        c = MagicMock()
        for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
                  'insert', 'update', 'delete', 'is_', 'in_', 'desc'):
            setattr(c, a, MagicMock(return_value=c))
        r = MagicMock(); r.data = data
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            return _chain([{"id": "p1", "naziv": "X", "tip": "opsti", "status": "aktivan",
                             "tuzeni": "", "tuzilac": "", "opis": "", "sud": ""}])
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "status": "spreman", "score": 88, "kategorije": [], "kriticna_upozorenja": [],
        "preporuke": [], "procena_rizika": "test",
    })))]

    canonical_cc = {
        "readiness": {"value": {"status": "CRITICAL_GAP", "razlog": "Nedostaje ključni dokaz.", "izvor": ["dk-1"]}},
    }

    class Body:
        tip_radnje = "podnesak"
        datum_radnje = "2026-08-10"
        opis_radnje = ""

    with patch.object(mi, "_get_supa", return_value=supa), \
         patch.object(mi, "_pozovi_matter_intel_api", return_value=fake_resp), \
         patch.object(mi, "build_case_context", new=AsyncMock(return_value=canonical_cc)), \
         patch.object(mi, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=None)
        result = await mi.preflight_check("p1", Body(), _req(), {"user_id": "u1", "email": "a@b.com"})

    assert result["status"] == "spreman"  # the action-specific answer is left alone
    assert any("CRITICAL_GAP" in w for w in result["kriticna_upozorenja"])


# ═══════════════════════════════════════════════════════════════════════════
# Fix 10 (Team 1, REPRODUCED): retrieve.py's `confidence` (get_confidence_level,
# top-match-only) and `confidence_detail.nivo` (_calculate_confidence, a composite of
# similarity+result-count+query-specificity) are both exposed raw in the same API
# response (api.py:1410-1413, main.py:3440/3549) and can disagree sharply -- one
# excellent top match with few total results can be confidence="HIGH" while
# confidence_detail.nivo="veoma nisko" for the SAME query. Fixed by always attaching
# the canonical top-match label alongside the composite score.
# ═══════════════════════════════════════════════════════════════════════════

def test_retrieve_confidence_detail_carries_canonical_top_score_label():
    from app.services.retrieve import _calculate_confidence, get_confidence_level

    # A single excellent match (top_score=0.9 -> canonical HIGH) with few total results
    # and a short query -- exactly the divergent case Team 1 reproduced.
    detail = _calculate_confidence(top_score=0.9, n_results=1, query="alimentacija")
    assert detail["nivo"] in ("veoma nisko", "nisko")  # composite score stays low, unchanged
    assert detail["top_score_confidence"] == get_confidence_level(0.9) == "HIGH"


# ═══════════════════════════════════════════════════════════════════════════
# Fix 11 (Team 8, REPRODUCED same bug class as Fix 8): _consequence_evidence_classify
# had no idempotency guard -- a retried/redelivered NEW_EVIDENCE_REGISTERED event for a
# document already classified would call klasifikuj_i_sacuvaj again, appending a second,
# duplicate set of predmet_dokazi rows for the exact same facts.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_evidence_classify_skips_when_already_classified_retry_safe():
    """A redelivered event for a dokument_id whose klasifikovan_at is already set must
    NOT call klasifikuj_i_sacuvaj again (which would insert duplicate predmet_dokazi rows)."""
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_evidence_classify

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "naziv_fajla": "d.pdf", "tekst_sadrzaj": "tekst...", "klasifikovan_at": "2026-08-05T00:00:00Z",
    }
    event = Event(type=EventType.NEW_EVIDENCE_REGISTERED, user_id="user-1", predmet_id="pred-1",
                  payload={"dokument_id": "dok-1"}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.evidence.klasifikuj_i_sacuvaj") as mock_classify:
        result = await _consequence_evidence_classify(event)

    assert result == "skipped_already_classified"
    mock_classify.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Fix 12 (Team 8, REPRODUCED): cio_daily's cache-check-then-generate-then-charge
# sequence was not atomic -- two near-simultaneous /daily calls for the same user
# could both pass the cache-miss check and both call UsageService.consume, a real
# double-charge for one dashboard load. Fixed with a 2-step DB claim reusing the
# table's own existing UNIQUE(user_id, datum) constraint.
# ═══════════════════════════════════════════════════════════════════════════

def _stateful_cio_izvestaj_supa():
    """Fake `cio_dnevni_izvestaj` table that actually evaluates WHERE clauses
    (including .lt on created_at) against mutable row state and enforces the
    real UNIQUE(user_id, datum) constraint on insert -- needed to prove the
    claim step genuinely blocks a concurrent second claim, not just that the
    code calls the right methods."""
    rows: dict = {}  # (user_id, datum) -> row dict

    class _Builder:
        def __init__(self, kind, payload=None):
            self.kind = kind
            self.payload = payload
            self.filters = {}
            self.lt_filters = {}

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def lt(self, col, val):
            self.lt_filters[col] = val
            return self

        def single(self):
            return self

        def execute(self):
            res = MagicMock()
            if self.kind == "select":
                # Both concurrent callers' initial cache-read happen BEFORE either one's
                # claim write lands (the real race window) -- always report "no cache yet"
                # here so both calls reach the claim step below, which is what this test
                # is actually proving is race-safe.
                res.data = None
                return res
            if self.kind == "insert":
                key = (self.payload["user_id"], self.payload["datum"])
                if key in rows:
                    raise Exception('duplicate key value violates unique constraint "cio_dnevni_izvestaj_user_id_datum_key"')
                row = dict(self.payload)
                row.setdefault("created_at", __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc).isoformat())  # simulates DB's DEFAULT now()
                rows[key] = row
                res.data = [rows[key]]
                return res
            if self.kind == "update":
                key = (self.filters.get("user_id"), self.filters.get("datum"))
                row = rows.get(key)
                matched = row is not None and all(
                    row.get(k, "") < v for k, v in self.lt_filters.items()
                )
                if matched:
                    rows[key].update(self.payload)
                    res.data = [rows[key]]
                else:
                    res.data = []
                return res
            res.data = None
            return res

    def _table(name):
        assert name == "cio_dnevni_izvestaj"
        t = MagicMock()
        t.select.side_effect = lambda cols: _Builder("select")
        t.insert.side_effect = lambda payload: _Builder("insert", payload)
        t.update.side_effect = lambda payload: _Builder("update", payload)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, rows


@pytest.mark.anyio
async def test_cio_daily_concurrent_calls_charge_only_once():
    """Direct reproduction of Team 8's finding: two near-simultaneous /daily calls for
    the same user, same day, with no existing cache row -- only ONE may charge credits."""
    import routers.cio as cio
    from starlette.requests import Request as StarletteRequest

    def _req():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [],
                  "query_string": b"", "app": MagicMock(), "state": MagicMock(),
                  "client": ("127.0.0.1", 1234)}
        return StarletteRequest(scope=scope, receive=receive)

    supa, rows = _stateful_cio_izvestaj_supa()
    user = {"user_id": "u1", "email": "a@b.com"}

    with patch.object(cio, "_get_supa", return_value=supa), \
         patch.object(cio, "_generiši_cio_izvestaj", new=AsyncMock(return_value={"predmeta_analizirano": 5})), \
         patch.object(cio, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        # Sequential calls simulate the SAME race outcome as concurrent ones would once
        # the first request's claim has landed (the actual DB-level exclusion the fix
        # relies on doesn't care about wall-clock overlap, only write order) -- this is
        # the same "prove the guard rejects a second writer" pattern used for Fix 8.
        await cio.cio_daily(_req(), user)
        await cio.cio_daily(_req(), user)

    assert mock_usage.consume.await_count == 1
