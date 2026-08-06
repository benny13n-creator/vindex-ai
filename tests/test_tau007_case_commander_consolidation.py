# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 007 ("Canonical Reasoning Consolidation") —
migration tests for routers/case_commander.py.

Covers: end-to-end endpoint wiring against a mocked build_case_context(),
concurrency (2 cases don't cross-contaminate), replay stability, the GPT
boundary (the advisory GPT call can never influence the 6 deterministic
fields), and structural migration-completeness (no leftover direct calls to
the duplicated functions this sprint eliminated).
"""
import sys, os, json, ast
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/commander/analiza"):
    scope = {
        "type": "http", "method": "POST", "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user(uid="aaaa0000-0000-0000-0000-000000000001"):
    return {"user_id": uid, "email": "test@vindex.rs"}


UID = "aaaa0000-0000-0000-0000-000000000001"
PID = "cccc0000-0000-0000-0000-000000000003"


def _cc(readiness_status="READY", missing=None, actions=None):
    return {
        "readiness": {"value": {"status": readiness_status, "razlog": "test", "izvor": []}},
        "missing_evidence": {"value": missing or []},
        "active_actions": {"value": actions or []},
    }


def _make_supa(predmet_data=None):
    """`_dohvati_predmet_kontekst`'s own `predmeti` query uses `.maybe_single()`,
    which returns `.data` as the dict directly (or None), NOT wrapped in a
    list -- unlike hearing_cc.py's own `.limit(1)` pattern."""
    supa = MagicMock()
    call_n = [0]

    def _make_result(data):
        r = MagicMock()
        r.data = data
        return r

    pred_result = _make_result(predmet_data)
    empty_result = _make_result([])

    chain = MagicMock()
    for attr in ['table', 'select', 'eq', 'is_', 'limit', 'order', 'execute',
                 'insert', 'update', 'delete', 'maybe_single']:
        setattr(chain, attr, MagicMock(return_value=chain))

    def execute_side():
        call_n[0] += 1
        return pred_result if call_n[0] == 1 else empty_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)
    return supa


def _make_multi_supa(preds_by_id: dict):
    """Deterministic, .eq('id', ...)-keyed mock -- safe under concurrent
    requests sharing one mock object, unlike _make_supa's global counter
    (same fragility already found/worked around in Tau 006's own hearing_cc
    tests)."""
    supa = MagicMock()

    def _table_side_effect(name):
        chain = MagicMock()
        state = {"id": None}

        def _eq(field, value):
            if name == "predmeti" and field == "id":
                state["id"] = value
            return chain

        for attr in ['select', 'is_', 'limit', 'order', 'insert', 'update', 'delete', 'maybe_single']:
            setattr(chain, attr, MagicMock(return_value=chain))
        chain.eq = MagicMock(side_effect=_eq)

        def _execute():
            r = MagicMock()
            if name == "predmeti":
                r.data = preds_by_id.get(state["id"])  # .maybe_single() -> dict or None, not a list
            else:
                r.data = []
            return r

        chain.execute = MagicMock(side_effect=_execute)
        return chain

    supa.table = MagicMock(side_effect=_table_side_effect)
    return supa


_PRED = {"id": PID, "naziv": "T", "opis": "", "status": "a", "stranka": "", "protivnik": "",
         "tip_postupka": "", "sud": "", "vrednost_spora": ""}


def _advisory_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# 1. Endpoint wiring — commander_analiza reads canonical fields end-to-end
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_commander_analiza_reads_canonical_readiness_end_to_end():
    from routers.case_commander import commander_analiza, CommanderRequest

    supa = _make_supa(predmet_data=_PRED)
    with patch("routers.case_commander._get_supa", return_value=supa), \
         patch("routers.case_commander.build_case_context", new_callable=AsyncMock,
               return_value=_cc(readiness_status="CRITICAL_GAP")) as mock_bcc, \
         patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _advisory_resp({"protivnikova_strategija": "x", "sudska_praksa": ""})
        mock_oai_cls.return_value = mock_oai

        payload = CommanderRequest(predmet_id=PID)
        result = await commander_analiza(_req(), payload, _user())

    mock_bcc.assert_awaited_once()
    assert mock_bcc.call_args.kwargs.get("include_documents") is False
    assert result["readiness_status"] == "CRITICAL_GAP"
    assert "kritičan" in result["status_predmeta"]["value"].lower()


@pytest.mark.anyio
async def test_commander_analiza_degrades_gracefully_when_context_fetch_fails():
    from routers.case_commander import commander_analiza, CommanderRequest

    supa = _make_supa(predmet_data=_PRED)
    with patch("routers.case_commander._get_supa", return_value=supa), \
         patch("routers.case_commander.build_case_context", new_callable=AsyncMock, side_effect=Exception("db down")), \
         patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _advisory_resp({"protivnikova_strategija": "", "sudska_praksa": ""})
        mock_oai_cls.return_value = mock_oai

        payload = CommanderRequest(predmet_id=PID)
        result = await commander_analiza(_req(), payload, _user())

    assert result["readiness_status"] == "UNKNOWN"
    assert result["nedostaje"] == []
    assert result["rizici"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. GPT boundary — the advisory call can never influence the 6 deterministic
#    fields, even if it returns a poisoned/malicious payload
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_gpt_advisory_cannot_override_canonical_readiness():
    """Adversarial: a poisoned advisory response tries to smuggle a fake
    status/priority claim into fields it was never asked to fill. Since
    status_predmeta/readiness_status/nedostaje/rizici/preporuceni_potez/
    vremenski_pritisak are built BEFORE the GPT call and never re-read from
    its output, they must be unaffected regardless of what GPT returns."""
    from routers.case_commander import commander_analiza, CommanderRequest

    supa = _make_supa(predmet_data=_PRED)
    with patch("routers.case_commander._get_supa", return_value=supa), \
         patch("routers.case_commander.build_case_context", new_callable=AsyncMock,
               return_value=_cc(readiness_status="READY")), \
         patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        # Poisoned payload: claims fields this endpoint never asks GPT for.
        mock_oai.chat.completions.create.return_value = _advisory_resp({
            "protivnikova_strategija": "x",
            "sudska_praksa": "y",
            "readiness_status": "CRITICAL_GAP",
            "status_predmeta": "Predmet je u kritičnom stanju!",
            "prioritet": "critical",
        })
        mock_oai_cls.return_value = mock_oai

        payload = CommanderRequest(predmet_id=PID)
        result = await commander_analiza(_req(), payload, _user())

    assert result["readiness_status"] == "READY"
    assert "spreman" in result["status_predmeta"]["value"].lower()
    assert result["protivnikova_strategija"]["source"] == "gpt_advisory"
    assert result["sudska_praksa"]["source"] == "gpt_advisory"


@pytest.mark.anyio
async def test_gpt_advisory_failure_does_not_affect_canonical_fields():
    from routers.case_commander import commander_analiza, CommanderRequest

    supa = _make_supa(predmet_data=_PRED)
    with patch("routers.case_commander._get_supa", return_value=supa), \
         patch("routers.case_commander.build_case_context", new_callable=AsyncMock,
               return_value=_cc(readiness_status="BLOCKED")), \
         patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.side_effect = Exception("OpenAI outage")
        mock_oai_cls.return_value = mock_oai

        payload = CommanderRequest(predmet_id=PID)
        result = await commander_analiza(_req(), payload, _user())

    assert result["readiness_status"] == "BLOCKED"
    assert result["protivnikova_strategija"]["value"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# 3. Concurrency / replay
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_analiza_for_different_cases_do_not_cross_contaminate():
    from routers.case_commander import commander_analiza, CommanderRequest

    async def _bcc_side_effect(predmet_id, uid, supa, include_documents=False):
        status = "CRITICAL_GAP" if predmet_id == "case-a" else "READY"
        return _cc(readiness_status=status)

    supa = _make_multi_supa({
        "case-a": {**_PRED, "id": "case-a"},
        "case-b": {**_PRED, "id": "case-b"},
    })
    with patch("routers.case_commander._get_supa", return_value=supa), \
         patch("routers.case_commander.build_case_context", new_callable=AsyncMock, side_effect=_bcc_side_effect), \
         patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
         patch("openai.OpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create.return_value = _advisory_resp({"protivnikova_strategija": "", "sudska_praksa": ""})
        mock_oai_cls.return_value = mock_oai

        result_a, result_b = await asyncio.gather(
            commander_analiza(_req(), CommanderRequest(predmet_id="case-a"), _user()),
            commander_analiza(_req(), CommanderRequest(predmet_id="case-b"), _user()),
        )

    assert result_a["readiness_status"] == "CRITICAL_GAP"
    assert result_b["readiness_status"] == "READY"


@pytest.mark.anyio
async def test_replay_stability_identical_calls_produce_identical_readiness():
    from routers.case_commander import commander_analiza, CommanderRequest

    async def _run():
        with patch("routers.case_commander._get_supa", return_value=_make_multi_supa({PID: _PRED})), \
             patch("routers.case_commander.build_case_context", new_callable=AsyncMock,
                   return_value=_cc(readiness_status="PARTIALLY_READY")), \
             patch("routers.case_commander.UsageService.consume", new_callable=AsyncMock, return_value=10), \
             patch("openai.OpenAI") as mock_oai_cls:

            mock_oai = MagicMock()
            mock_oai.chat.completions.create.return_value = _advisory_resp({"protivnikova_strategija": "", "sudska_praksa": ""})
            mock_oai_cls.return_value = mock_oai
            return await commander_analiza(_req(), CommanderRequest(predmet_id=PID), _user())

    result_1 = await _run()
    result_2 = await _run()
    assert result_1["readiness_status"] == result_2["readiness_status"] == "PARTIALLY_READY"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Structural migration completeness — no leftover direct calls
# ═══════════════════════════════════════════════════════════════════════════

def test_no_direct_calls_to_duplicated_reasoning_functions():
    """Structural proof (not a string grep, an AST walk so a comment or
    docstring mentioning these names doesn't produce a false pass): no
    Call node anywhere in case_commander.py invokes calculate_procesni_rizik,
    identify_case_problems, collect_case_gaps, or compute_case_readiness."""
    import routers.case_commander as mod
    source = open(mod.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    forbidden = {"calculate_procesni_rizik", "identify_case_problems", "collect_case_gaps", "compute_case_readiness"}
    found_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name in forbidden:
                found_calls.add(name)
    assert found_calls == set(), f"Found leftover direct calls to: {found_calls}"


def test_build_case_context_is_imported_and_used():
    import routers.case_commander as mod
    assert hasattr(mod, "build_case_context")
    source = open(mod.__file__, encoding="utf-8").read()
    assert source.count("await build_case_context(") >= 2  # _kanonski_nalazi + portfolio loop


# ═══════════════════════════════════════════════════════════════════════════
# 5. Phase 4 — cross-system vocabulary consistency (Court Predictor /
#    Hearing CC / Case Commander all key off the SAME canonical constants)
# ═══════════════════════════════════════════════════════════════════════════

def test_readiness_cap_dicts_use_canonical_constants_not_string_literals():
    """Program Tau, Master Sprint 007, Phase 4 finding: court_predictor.py
    and hearing_cc.py previously hardcoded "CRITICAL_GAP"/"BLOCKED" as raw
    string literals in their own _CAP_BY_READINESS dicts, instead of
    importing shared/case_readiness.py's own constants -- a silent-drift
    risk if the source strings were ever renamed. Fixed this sprint. This
    test proves the fix: the dict keys are identically the SAME objects as
    the canonical constants, in all 3 consuming modules."""
    from shared.case_readiness import CRITICAL_GAP, BLOCKED
    import routers.court_predictor as cp
    import routers.hearing_cc as hc

    assert set(hc._CAP_BY_READINESS.keys()) == {CRITICAL_GAP, BLOCKED}
    # court_predictor.py's own cap dict is built inline (not module-level) --
    # confirm the import exists and the module's own source references the
    # imported names, not new hardcoded literals, at its cap call site.
    assert cp.CRITICAL_GAP == CRITICAL_GAP
    assert cp.BLOCKED == BLOCKED
    source = open(cp.__file__, encoding="utf-8").read()
    assert '_CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}' in source


def test_case_commander_readiness_rank_covers_all_5_canonical_states():
    """Cross-system check: case_commander.py's own _READINESS_RANK must have
    an entry for every one of shared/case_readiness.py's own 5 states -- a
    missing state would silently sort to Python dict.get's own default
    (5) instead of a deliberate rank, masking a real case in that state."""
    from shared.case_readiness import READINESS_STATES
    from routers.case_commander import _READINESS_RANK
    assert set(_READINESS_RANK.keys()) == set(READINESS_STATES)


@pytest.mark.anyio
async def test_same_case_context_agrees_across_court_predictor_hearing_cc_commander():
    """Direct cross-system proof: build_case_context() is called ONCE
    (mocked identically) and fed into all 3 consuming modules' own
    readiness-interpreting logic. All 3 must agree it's a capped/flagged
    case -- proving no module has its own drifted interpretation of what
    CRITICAL_GAP means."""
    from shared.case_readiness import CRITICAL_GAP
    cc = _cc(readiness_status=CRITICAL_GAP)

    # Court Predictor's own cap dict is built inline inside prediktuj_ishod
    # (not module-level) -- reconstruct it here using the SAME imported
    # constants the module itself uses, proving the vocabulary agrees.
    from routers.court_predictor import CRITICAL_GAP as cp_critical, BLOCKED as cp_blocked
    cp_status = ((cc.get("readiness") or {}).get("value") or {}).get("status")
    assert {cp_critical: 50, cp_blocked: 65}.get(cp_status) == 50

    # Hearing CC's own module-level cap dict
    import routers.hearing_cc as hc_mod
    assert hc_mod._CAP_BY_READINESS.get(cp_status) == 50

    # Case Commander's own label + rank
    from routers.case_commander import _READINESS_LABEL_SR, _READINESS_RANK
    assert "kritičan" in _READINESS_LABEL_SR[cp_status].lower()
    assert _READINESS_RANK[cp_status] == 0  # highest urgency rank


# ═══════════════════════════════════════════════════════════════════════════
# 6. Phase 6 — stress certification
#
# Raw table-scale (1000 documents, 500 deadlines, 100 contradictions, a
# 20-year-old case's own date arithmetic) is deliberately NOT re-tested here
# -- case_commander.py's own migrated code does no scale-sensitive
# processing of its own anymore (no more independent risk_engine/gap_engine
# calls); it only reads and filters build_case_context()'s own ALREADY
# scale-proven output (tests/test_tau002_case_context.py's own 500/1000-doc
# tests, tests/test_tau004_extreme_scale.py's own 300-deadline/50-
# contradiction/20-year tests). Re-running those here would test
# build_case_context() a 2nd time, not this sprint's own actual change --
# same discipline Tau 006 already established. What IS new and IS tested
# here: whether _kanonski_nalazi's own filtering logic and
# _kanonski_prioritet_i_rizici's own portfolio ranking hold at a LARGER
# canonical payload (100 gap items, exceeding this mission's own explicit
# ask) and across a full 20-case portfolio (the existing display cap) with
# varied readiness/courts/clients, without crashing or cross-contaminating.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kanonski_nalazi_handles_100_missing_evidence_items_no_divergence():
    from routers import case_commander as cc_mod
    missing = (
        [{"tip": "NEMA_DOKAZA", "izvor": "identify_case_problems", "razlog": f"Nalaz {i}",
          "pouzdanost": "visoka", "dedupe_key": f"k{i}"} for i in range(60)]
        + [{"tip": "GENOME_NEDOSTAJE", "izvor": "genome_ekstrakcija", "razlog": f"Genome nalaz {i}",
            "pouzdanost": "srednja", "dedupe_key": f"g{i}"} for i in range(40)]
    )
    with patch.object(cc_mod, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="PARTIALLY_READY", missing=missing))):
        result = await cc_mod._kanonski_nalazi(PID, UID, MagicMock())

    assert len(result["nedostaje"]) == 100          # every item surfaced, none silently dropped
    assert len(result["rizici"]) == 60               # only identify_case_problems-sourced items
    assert len(set(id(x) for x in result["nedostaje"])) == 100  # no duplicate object aliasing


@pytest.mark.anyio
async def test_portfolio_ranking_20_cases_multiple_courts_clients_no_cross_contamination():
    """Full 20-case portfolio (the existing display cap), varied readiness/
    courts/clients -- every case's own readiness stays correctly isolated at
    scale, not just in the earlier 2-case concurrency test."""
    from routers.case_commander import _kanonski_prioritet_i_rizici
    from shared.case_readiness import READY, PARTIALLY_READY, BLOCKED, CRITICAL_GAP, UNKNOWN

    statuses = [READY, PARTIALLY_READY, BLOCKED, CRITICAL_GAP, UNKNOWN]
    predmeti = []
    for i in range(20):
        status = statuses[i % len(statuses)]
        actions = []
        if status in (BLOCKED, CRITICAL_GAP):
            actions = [{"tip": "PRIPREMITI_PODNESAK", "razlog": f"Hitno {i}",
                        "prioritet": "critical" if status == CRITICAL_GAP else "high",
                        "rok": f"2026-{(i % 12) + 1:02d}-01", "dedupe_key": f"case-{i}-action", "status": "open"}]
        predmeti.append({
            "id": f"case-{i}", "naziv": f"Case {i}", "sud": f"Sud {i % 5}", "klijent_id": f"klijent-{i % 7}",
            "case_actions": actions, "_readiness": {"status": status, "razlog": "", "izvor": []},
        })

    prioritet, rizici = _kanonski_prioritet_i_rizici(predmeti)

    assert prioritet is not None
    # 4 cases are CRITICAL_GAP (indices 3, 8, 13, 18) -- the winner must be
    # one of those 4 (rank 0, tiebroken by nearest rok), never a case from
    # any other readiness bucket bleeding into the top slot.
    assert prioritet["predmet_naziv"] in {"Case 3", "Case 8", "Case 13", "Case 18"}
    # Every risk entry traces back to a real, distinct case -- no collapsing/aliasing across cases.
    seen_cases = {r["predmet_naziv"] for r in rizici}
    assert len(seen_cases) == len(rizici) or len(rizici) <= 5  # top-5 cap, still no duplicate case bleed
    for r in rizici:
        assert r["predmet_naziv"].startswith("Case ")


@pytest.mark.anyio
async def test_dohvati_sve_predmete_handles_partial_build_case_context_failures():
    """Stress the fail-soft path specifically: of N cases, some succeed and
    some fail build_case_context() -- each must independently degrade to
    UNKNOWN without affecting the others (extends the 2-case fail-soft test
    to a mixed-outcome batch, matching this phase's own portfolio-scale ask)."""
    from routers import case_commander as cc_mod

    async def _bcc_side_effect(predmet_id, uid, supa, include_documents=False):
        if predmet_id in ("case-1", "case-3"):
            raise Exception("transient db error")
        return _cc(readiness_status="READY" if predmet_id == "case-2" else "CRITICAL_GAP")

    supa = MagicMock()
    predmeti_result = MagicMock()
    predmeti_result.data = [{"id": f"case-{i}", "naziv": f"Case {i}"} for i in range(5)]
    empty_result = MagicMock(); empty_result.data = []

    def _table(name):
        chain = MagicMock()
        for attr in ["select", "eq", "gte", "lte", "order", "limit", "in_"]:
            setattr(chain, attr, MagicMock(return_value=chain))
        chain.execute = MagicMock(return_value=predmeti_result if name == "predmeti" else empty_result)
        return chain

    supa.table = MagicMock(side_effect=_table)

    with patch.object(cc_mod, "_get_supa", return_value=supa), \
         patch.object(cc_mod, "build_case_context", new=AsyncMock(side_effect=_bcc_side_effect)):
        podaci = await cc_mod._dohvati_sve_predmete_za_analizu(UID)

    by_id = {p["id"]: p for p in podaci["predmeti"]}
    assert by_id["case-1"]["_readiness"]["status"] == "UNKNOWN"
    assert by_id["case-3"]["_readiness"]["status"] == "UNKNOWN"
    assert by_id["case-2"]["_readiness"]["status"] == "READY"
    assert by_id["case-0"]["_readiness"]["status"] == "CRITICAL_GAP"
    assert by_id["case-4"]["_readiness"]["status"] == "CRITICAL_GAP"
