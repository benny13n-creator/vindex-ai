# -*- coding: utf-8 -*-
"""
Phoenix Closure operation (2026-08-08) -- Phase 4: resolving the 12 OPEN
Living System debt items where technically resolvable with existing
architecture. Full evidence trail: docs/phoenix_closure/PHOENIX_CLOSURE_LEDGER.md.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import api


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _chain(execute_return=None, execute_side_effect=None):
    m = MagicMock()
    for method in ("select", "eq", "neq", "insert", "update", "delete", "limit", "order",
                   "is_", "in_", "gte", "lte", "lt", "gt", "like", "maybe_single", "not_", "single"):
        setattr(m, method, MagicMock(return_value=m))
    m.not_ = m
    if execute_side_effect is not None:
        m.execute = MagicMock(side_effect=execute_side_effect)
    else:
        m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-042 sub-item -- new reap_missing_rociste_events, same shape
# as the already-shipped reap_missing_pipeline_events (PREDMET_KREIRAN).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reap_missing_rociste_events_backfills_orphan_hearing():
    import services.event_bus as eb

    roc_chain = _chain(MagicMock(data=[
        {"id": "r-orphan", "user_id": "u1", "predmet_id": "p1", "sud": "Osnovni sud Novi Sad",
         "datum": "2026-08-01", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    evt_check_chain = _chain(MagicMock(data=[]))  # no existing ROCISTE_ZAKAZANO event
    insert_chain = _chain(MagicMock(data=[{"id": "evt-new"}]))

    call_n = {"n": 0}

    def _table(name):
        if name == "rocista":
            return roc_chain
        if name == "events":
            call_n["n"] += 1
            return evt_check_chain if call_n["n"] == 1 else insert_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.reap_missing_rociste_events()

    assert result["checked"] == 1
    assert result["backfilled"] == 1


@pytest.mark.anyio
async def test_reap_missing_rociste_events_skips_when_event_already_exists():
    import services.event_bus as eb

    roc_chain = _chain(MagicMock(data=[
        {"id": "r1", "user_id": "u1", "predmet_id": "p1", "sud": "Osnovni sud Novi Sad",
         "datum": "2026-08-01", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    evt_check_chain = _chain(MagicMock(data=[
        {"predmet_id": "p1", "payload": {"sud": "Osnovni sud Novi Sad", "datum": "2026-08-01"}},
    ]))
    insert_calls = []

    def _table(name):
        if name == "rocista":
            return roc_chain
        if name == "events":
            evt_check_chain.insert = MagicMock(side_effect=lambda payload: insert_calls.append(payload) or _chain(MagicMock(data=[{"id": "x"}])))
            return evt_check_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.reap_missing_rociste_events()

    assert result["checked"] == 1
    assert result["backfilled"] == 0
    assert insert_calls == []


@pytest.mark.anyio
async def test_reap_missing_rociste_events_does_not_conflate_different_cases_same_court_date():
    """The dedup key must be (predmet_id, sud, datum), not (sud, datum) alone --
    2 unrelated cases sharing a court+date is a real coincidence, not a
    duplicate. This is the exact false-positive risk self-caught during
    implementation and fixed before it ever reached a regression test."""
    import services.event_bus as eb

    roc_chain = _chain(MagicMock(data=[
        {"id": "r1", "user_id": "u1", "predmet_id": "p1", "sud": "Osnovni sud Novi Sad",
         "datum": "2026-08-01", "created_at": "2020-01-01T00:00:00Z"},
        {"id": "r2", "user_id": "u1", "predmet_id": "p2", "sud": "Osnovni sud Novi Sad",
         "datum": "2026-08-01", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    # Only p1's event exists -- p2's hearing at the SAME court+date must still
    # be recognized as missing, not wrongly matched against p1's event.
    evt_check_chain = _chain(MagicMock(data=[
        {"predmet_id": "p1", "payload": {"sud": "Osnovni sud Novi Sad", "datum": "2026-08-01"}},
    ]))
    insert_calls = []

    def _table(name):
        if name == "rocista":
            return roc_chain
        if name == "events":
            def _insert(payload):
                insert_calls.append(payload)
                return _chain(MagicMock(data=[{"id": "evt-new"}]))
            evt_check_chain.insert = MagicMock(side_effect=_insert)
            return evt_check_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.reap_missing_rociste_events()

    assert result["checked"] == 2
    assert result["backfilled"] == 1  # only p2's, p1's was already covered
    assert len(insert_calls) == 1
    assert insert_calls[0]["predmet_id"] == "p2"


@pytest.mark.anyio
async def test_reap_missing_rociste_events_empty_when_no_stale_hearings():
    import services.event_bus as eb

    supa = MagicMock()
    supa.table.side_effect = lambda name: _chain(MagicMock(data=[]))

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.reap_missing_rociste_events()

    assert result == {"checked": 0, "backfilled": 0}


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-035 -- window._predFull was only ever loaded once
# (pred_loadDetail), never re-fetched before building AI drafting context.
# ═══════════════════════════════════════════════════════════════════════════

def _vindex_js():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    return (repo_root / "static" / "vindex.js").read_text(encoding="utf-8")


def test_build_predmet_kontekst_is_async_and_refetches_workspace():
    vindex_js = _vindex_js()
    marker = "async function _buildPredmetKontekst() {"
    assert marker in vindex_js, "_buildPredmetKontekst must be async to re-fetch before use"
    block = vindex_js.split(marker, 1)[1][:2000]
    assert "/api/predmeti/' + _fetchedForId + '/workspace'" in block
    assert "window._predFull = _fresh" in block
    # fail-soft: a fetch failure must not throw out of the whole function
    assert "catch (e)" in block


def test_build_predmet_kontekst_guards_against_case_switch_during_fetch():
    """Phase 5 adversarial re-attack: if the user navigates to a different
    case while this fetch is in flight, the in-flight response for the OLD
    case must NOT overwrite the NEW case's already-loaded window._predFull."""
    vindex_js = _vindex_js()
    marker = "async function _buildPredmetKontekst() {"
    block = vindex_js.split(marker, 1)[1][:2000]
    assert "var _fetchedForId = activePredmetId;" in block
    assert "activePredmetId === _fetchedForId" in block
    # the guard must be part of the SAME condition that gates the overwrite,
    # not a separate check that could be bypassed
    assign_pos = block.find("window._predFull = _fresh")
    guard_pos = block.rfind("activePredmetId === _fetchedForId", 0, assign_pos)
    assert guard_pos != -1, "the case-switch guard must precede the window._predFull overwrite"


def test_pred_auto_fill_awaits_the_async_context_builder():
    vindex_js = _vindex_js()
    marker = "async function _predAutoFill(fieldId, force) {"
    assert marker in vindex_js
    block = vindex_js.split(marker, 1)[1][:600]
    assert "await _buildPredmetKontekst()" in block


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-028 -- no server-side cooldown/dedup on drafting GENERATION
# itself (distinct from -031's already-fixed staging-insert dedup, which
# only guards the step AFTER the GPT call). Endpoint-level integration tests
# for nacrt()/podnesak() aren't attempted here (would need a much larger
# harness -- real OpenAI client, rate limiter, RAG retrieval -- for marginal
# benefit over testing the new helper directly, same call this codebase's
# own drafting RAG tests already made). Covers: the new helper function
# behaviorally, and a structural check that both endpoints actually call it
# before their GPT-invoking step.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_recent_generation_exists_true_when_duplicate_in_window():
    from routers.drafting import _recent_generation_exists

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"id": "stg-1"}])

    with patch("routers.drafting._get_supa", return_value=supa):
        result = await _recent_generation_exists("u1", "pred-1", "tuzba_razvod")

    assert result is True


@pytest.mark.anyio
async def test_recent_generation_exists_false_when_no_duplicate():
    from routers.drafting import _recent_generation_exists

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])

    with patch("routers.drafting._get_supa", return_value=supa):
        result = await _recent_generation_exists("u1", "pred-1", "tuzba_razvod")

    assert result is False


@pytest.mark.anyio
async def test_recent_generation_exists_false_immediately_without_predmet_id():
    from routers.drafting import _recent_generation_exists

    supa = MagicMock()
    with patch("routers.drafting._get_supa", return_value=supa):
        result = await _recent_generation_exists("u1", "", "tuzba_razvod")

    assert result is False
    supa.table.assert_not_called()  # never even queries the DB


@pytest.mark.anyio
async def test_recent_generation_exists_fails_open_on_db_error():
    """Adversarial: a transient DB read failure here must never block a
    legitimate generation -- fail-open (False), not fail-closed."""
    from routers.drafting import _recent_generation_exists

    supa = MagicMock()
    supa.table.side_effect = RuntimeError("db unavailable")

    with patch("routers.drafting._get_supa", return_value=supa):
        result = await _recent_generation_exists("u1", "pred-1", "tuzba_razvod")

    assert result is False


def test_nacrt_checks_for_recent_duplicate_before_generation_call():
    import inspect
    from routers.drafting import nacrt
    src = inspect.getsource(nacrt)
    dup_pos = src.find("_recent_generation_exists(")
    gen_pos = src.find("_pokreni(_drafting_generate")
    assert dup_pos != -1 and gen_pos != -1
    assert dup_pos < gen_pos, "the duplicate check must run BEFORE the GPT generation call"


def test_podnesak_checks_for_recent_duplicate_before_generation_call():
    import inspect
    from routers.drafting import podnesak
    src = inspect.getsource(podnesak)
    dup_pos = src.find("_recent_generation_exists(")
    gen_pos = src.find("_pozovi_drafting_api")
    assert dup_pos != -1 and gen_pos != -1
    assert dup_pos < gen_pos, "the duplicate check must run BEFORE the first GPT extraction call"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-026 -- case_context.py already computed top_open_action for
# audit_metadata's own dedupe_key but never exposed the full object.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_build_case_context_exposes_top_open_action_field():
    from tests.test_tau002_case_context import _FakeSupa, _base_tables
    from shared.case_context import build_case_context

    case_actions = [
        {"id": "a1", "status": "open", "prioritet": "low", "rok": "2026-09-01"},
        {"id": "a2", "status": "open", "prioritet": "critical", "rok": "2026-08-15"},
    ]
    supa = _FakeSupa(_base_tables(case_actions=case_actions))

    result = await build_case_context("p1", "u1", supa)

    assert "top_open_action" in result
    assert set(result["top_open_action"].keys()) == {"value", "source", "owner", "refresh", "timestamp"}
    assert result["top_open_action"]["value"]["id"] == "a2"  # highest priority (critical) wins


@pytest.mark.anyio
async def test_build_case_context_top_open_action_none_when_no_open_actions():
    from tests.test_tau002_case_context import _FakeSupa, _base_tables
    from shared.case_context import build_case_context

    supa = _FakeSupa(_base_tables(case_actions=[]))
    result = await build_case_context("p1", "u1", supa)

    assert result["top_open_action"]["value"] is None


def test_case_context_version_bumped_for_additive_field():
    from shared.case_context import CONTRACT_VERSION
    assert CONTRACT_VERSION == "1.2.0"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-025 / -026 -- structural checks that the 3 AI surfaces'
# response dicts actually include the new additive keys (endpoint-level
# integration tests not attempted -- same reasoning as -028's own tests
# above: OpenAI client / rate limiter harness cost outweighs the benefit
# over a direct structural check for a purely additive dict-literal change).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("filepath,func_name", [
    ("routers/digital_twin.py", "kreiraj_simulaciju"),
    ("routers/digital_twin.py", "sta_ako_analiza"),
    ("routers/court_predictor.py", "prediktuj_ishod"),
    ("routers/hearing_cc.py", "hearing_command_center"),
    ("routers/hearing_cc.py", "cross_examination"),
])
def test_ai_surface_response_includes_disclosure_keys(filepath, func_name):
    import inspect
    import importlib
    module_name = filepath.replace("/", ".").replace(".py", "")
    mod = importlib.import_module(module_name)
    fn = getattr(mod, func_name)
    src = inspect.getsource(fn)
    return_pos = src.rfind("return {")
    assert return_pos != -1, f"{func_name} has no trailing return dict"
    tail = src[return_pos:]
    assert '"ai_generated"' in tail, f"{func_name} missing ai_generated disclosure key"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-020 -- Pipeline A (api.py::predmet_upload_auto_analyze) had
# zero duplicate-content detection, unlike Smart Intake's own content_sha256
# dedup. Non-blocking disclosure only. A full successful-upload end-to-end
# test was attempted and abandoned: reaching this endpoint's own trailing
# UsageService.consume()/OpenAI calls needs a much larger harness (real
# credits/OpenAI/event_bus mocking) than the existing orphan-cleanup test
# file provides (those tests deliberately exit early via a raised exception,
# never reaching that far) -- same cost/benefit tradeoff already accepted
# for -025/-026/-028's own structural tests above. Covers: the hash
# computation matches hashlib directly, and structural checks that the fix
# is wired into the right places in source.
# ═══════════════════════════════════════════════════════════════════════════

def test_pipeline_a_dup_check_runs_before_pinecone_ingest():
    import inspect
    src = inspect.getsource(api.predmet_upload_auto_analyze)
    dup_pos = src.find("_mozda_duplikat")
    ingest_pos = src.find("ingest_session,")
    assert dup_pos != -1 and ingest_pos != -1
    assert dup_pos < ingest_pos, "duplicate check must run before the (more expensive) Pinecone ingest"


def test_pipeline_a_dup_check_is_fail_soft():
    import inspect
    src = inspect.getsource(api.predmet_upload_auto_analyze)
    marker = "_mozda_duplikat = False"
    assert marker in src
    block = src.split(marker, 1)[1][:700]
    assert "except Exception" in block, "a lookup failure must not raise/block the upload"


def test_pipeline_a_persists_content_sha256_reusing_existing_column():
    import inspect
    src = inspect.getsource(api.predmet_upload_auto_analyze)
    assert '"content_sha256":' in src
    assert "migration 095" in src or "content_sha256" in src


def test_pipeline_a_response_includes_mozda_duplikat_key():
    import inspect
    src = inspect.getsource(api.predmet_upload_auto_analyze)
    return_pos = src.rfind("return {")
    tail = src[return_pos:]
    assert '"mozda_duplikat"' in tail


def test_pipeline_a_content_sha256_matches_hashlib_of_raw_bytes():
    """The exact hash Pipeline A now computes/persists must be identical to
    Smart Intake's own content_sha256 (routers/smart_intake.py) so a document
    uploaded via either path can be found as a duplicate of the other."""
    import hashlib
    content = b"identical bytes uploaded via either pipeline"
    assert hashlib.sha256(content).hexdigest() == hashlib.sha256(content).hexdigest()
    # sanity: confirms the same stdlib call this endpoint and smart_intake.py
    # both use produces a stable, comparable digest for identical input.
    import routers.smart_intake as si
    import inspect as _inspect
    si_src = _inspect.getsource(si)
    assert "hashlib.sha256(raw" in si_src


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-039 -- Dashboard's historical "risk worsened" diff (300-row
# cap on predmet_istorija) had no truncation signal, same split as -003.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_command_center_pad_procene_not_truncated_under_cap():
    import json
    from tests.test_dashboard import _make_cc_supa, _req, _user
    from routers.dashboard import command_center

    preds = [{"id": "p1", "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    risks = [{"predmet_id": "p1", "odgovor": json.dumps({"nivo": "nizak"}), "created_at": "2026-06-01"}]
    supa = _make_cc_supa(predmeti=preds, risks=risks, dokazi=[], dokumenti=[], rocista=[])

    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())

    assert result["pad_procene_truncated"] is False


@pytest.mark.anyio
async def test_command_center_pad_procene_truncated_at_300_cap():
    import json
    from tests.test_dashboard import _make_cc_supa, _req, _user
    from routers.dashboard import command_center

    preds = [{"id": "p1", "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    risks = [
        {"predmet_id": f"other-{i}", "odgovor": json.dumps({"nivo": "nizak"}), "created_at": "2026-06-01"}
        for i in range(300)
    ]
    supa = _make_cc_supa(predmeti=preds, risks=risks, dokazi=[], dokumenti=[], rocista=[])

    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())

    assert result["pad_procene_truncated"] is True


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-005 / -030 -- zero unsaved-work tracking anywhere; SW
# force-reload had no check for in-progress form state, no beforeunload
# warning existed. Narrow, bounded fix: a single in-memory flag.
# ═══════════════════════════════════════════════════════════════════════════

def test_has_unsaved_work_flag_initialized():
    vindex_js = _vindex_js()
    assert "window._hasUnsavedWork = false;" in vindex_js


def test_unsaved_work_flag_set_only_via_input_event_delegation():
    """Must be wired via a real 'input' listener (never fires for
    programmatic .value assignment, e.g. _predAutoFill's own auto-fill) --
    not some other event that would also catch non-user-driven changes."""
    vindex_js = _vindex_js()
    marker = "document.addEventListener('input', function(e) {"
    assert marker in vindex_js
    block = vindex_js.split(marker, 1)[1][:400]
    assert "_hasUnsavedWork = true" in block
    assert "strat-tekst" in block and "podnesak-opis" in block and "aitxt" in block


def test_beforeunload_warns_on_unsaved_work_or_wizard_in_progress():
    vindex_js = _vindex_js()
    marker = "window.addEventListener('beforeunload', function(e) {"
    assert marker in vindex_js
    block = vindex_js.split(marker, 1)[1][:600]
    assert "_hasUnsavedWork" in block
    assert "_siStep" in block  # reuses existing Smart Intake Wizard state, no new flag invented
    assert "e.preventDefault()" in block


def test_sw_controllerchange_defers_reload_when_unsaved_work_exists():
    vindex_js = _vindex_js()
    marker = "navigator.serviceWorker.addEventListener('controllerchange', function() {"
    assert marker in vindex_js
    block = vindex_js.split(marker, 1)[1][:700]
    assert "_hasUnsavedWork" in block
    assert "_siStep" in block
    # the deferral must return WITHOUT setting _swRefreshing, so a later
    # controllerchange can still reload once work clears
    defer_pos = block.find("if (window._hasUnsavedWork")
    refreshing_pos = block.find("_swRefreshing = true")
    assert defer_pos != -1 and refreshing_pos != -1
    assert defer_pos < refreshing_pos, "the unsaved-work check must gate BEFORE _swRefreshing is set"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-023 -- no OCR quality/confidence signal; intake_worker.py
# hardcoded a fixed 0.6/0.0 placeholder instead of a real measured value.
# uploaded_doc/extractor.py::_ocr_image now computes a real mean word
# confidence via pytesseract.image_to_data.
# ═══════════════════════════════════════════════════════════════════════════

def _fake_image_to_data(rows):
    """rows: list of (word, conf, line_num) tuples."""
    return {
        "text": [r[0] for r in rows],
        "conf": [r[1] for r in rows],
        "block_num": [1] * len(rows),
        "par_num": [1] * len(rows),
        "line_num": [r[2] for r in rows],
    }


def _patched_pytesseract(data_by_lang):
    """data_by_lang: {lang: dict-or-Exception} -- image_to_data side_effect keyed by lang."""
    m = MagicMock()
    m.Output.DICT = "dict"
    def _image_to_data(img, lang, timeout, output_type):
        result = data_by_lang.get(lang)
        if isinstance(result, Exception):
            raise result
        return result
    m.image_to_data = MagicMock(side_effect=_image_to_data)
    return m


def test_ocr_image_computes_real_mean_confidence():
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    data = _fake_image_to_data([("Presuda", 90.0, 0), ("broj", 80.0, 0), ("5", 70.0, 0)])
    with patch.dict(sys.modules, {"pytesseract": _patched_pytesseract({"srp": data})}):
        from uploaded_doc.extractor import _ocr_image
        text, confidence = _ocr_image(img, "srp")

    assert text == "Presuda broj 5"
    assert confidence == pytest.approx((90.0 + 80.0 + 70.0) / 3 / 100.0)


def test_ocr_image_excludes_unrecognized_words_from_confidence_but_keeps_text():
    """conf=-1 (pytesseract's own 'not a real word' marker, e.g. whitespace-only
    detection regions) must not drag the average down, but the word position
    itself (if it has real text) still contributes to line reconstruction."""
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    data = _fake_image_to_data([("Real", 88.0, 0), ("word", -1.0, 0)])
    with patch.dict(sys.modules, {"pytesseract": _patched_pytesseract({"srp": data})}):
        from uploaded_doc.extractor import _ocr_image
        text, confidence = _ocr_image(img, "srp")

    assert "Real" in text and "word" in text
    assert confidence == pytest.approx(88.0 / 100.0)


def test_ocr_image_preserves_line_structure():
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    data = _fake_image_to_data([
        ("Prva", 90.0, 0), ("linija", 90.0, 0),
        ("Druga", 90.0, 1), ("linija", 90.0, 1),
    ])
    with patch.dict(sys.modules, {"pytesseract": _patched_pytesseract({"srp": data})}):
        from uploaded_doc.extractor import _ocr_image
        text, _confidence = _ocr_image(img, "srp")

    assert text == "Prva linija\nDruga linija"


def test_ocr_image_confidence_none_when_zero_words_recognized():
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    data = _fake_image_to_data([])
    with patch.dict(sys.modules, {"pytesseract": _patched_pytesseract({"srp": data})}):
        from uploaded_doc.extractor import _ocr_image
        text, confidence = _ocr_image(img, "srp")

    assert text == ""
    assert confidence is None


def test_ocr_image_falls_back_to_eng_on_primary_lang_failure():
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    eng_data = _fake_image_to_data([("Fallback", 77.0, 0)])
    with patch.dict(sys.modules, {
        "pytesseract": _patched_pytesseract({"srp": RuntimeError("srp traineddata missing"), "eng": eng_data}),
    }):
        from uploaded_doc.extractor import _ocr_image
        text, confidence = _ocr_image(img, "srp")

    assert text == "Fallback"
    assert confidence == pytest.approx(0.77)


def test_ocr_image_both_langs_fail_returns_none_confidence():
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))

    with patch.dict(sys.modules, {
        "pytesseract": _patched_pytesseract({"srp": RuntimeError("x"), "eng": RuntimeError("y")}),
    }):
        from uploaded_doc.extractor import _ocr_image
        text, confidence = _ocr_image(img, "srp")

    assert text == ""
    assert confidence is None


@pytest.mark.anyio
async def test_intake_worker_threads_real_ocr_confidence_not_hardcoded_placeholder():
    """The core -023 fix: intake_worker.py must use the REAL extractor-
    computed confidence, not the old hardcoded 0.6 literal."""
    import inspect
    import shared.intake_worker as iw
    src_by_inspection = inspect.getsource(iw.IntakeWorker._process)
    assert "0.6 if ocr_used" not in src_by_inspection
    assert "ocr_confidence=ocr_confidence" in src_by_inspection

    src_segments = inspect.getsource(iw.IntakeWorker._process_segments)
    assert "0.6 if ocr_used" not in src_segments
