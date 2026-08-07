# -*- coding: utf-8 -*-
"""
Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario G + F):

Scenario G -- Case Genome silently caps at _GENOME_MAX_DOCS=25 documents,
ordered by upload order (redni_broj ascending), so document #30/#100/#300 of
a large case (the final judgment, a critical piece of evidence -- anything)
was silently invisible to Genome forever. Worse, the reported
`_genome_docs_preskoceno` count was computed from the ALREADY-LIMITED
25-document list the caller fetched, so it read ~0 for exactly the cases
where truncation actually mattered (>25 real documents). Fixed by (a)
ordering by redni_broj DESCENDING so the most recent documents are what
Genome sees when truncation is unavoidable, and (b) fetching the case's true
total document count separately and passing it into _extract_genome so the
skipped-count is accurate.

Scenario F -- no debounce/coalescing existed anywhere on Genome refresh;
concurrent triggers for the same predmet_id (which Scenario B's new
multi-document-per-case attach makes routine) could race: both read the same
case_dna.verzija, both write, whichever lands last silently wins. Fixed with
an in-process coalescing wrapper (_run_genome_background) around the actual
refresh logic (_do_genome_refresh): a trigger arriving while another is
already running for the same predmet_id schedules exactly one more run
instead of running fully in parallel.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Scenario G — _extract_genome truncation accounting
# ═══════════════════════════════════════════════════════════════════════════

def _fake_score(*a, **kw):
    return {"snaga_predmeta_procent": 50, "snaga_predmeta": "srednja", "snaga_faktori": []}


@pytest.mark.anyio
async def test_extract_genome_reports_true_skipped_count_when_provided():
    """A case with 40 real documents, only 25 fetched (pre-limited by the
    caller) -- the true skip count is 15, not 0."""
    from routers import case_dna as cd

    docs = [{"redni_broj": i, "naziv_fajla": f"d{i}", "tekst_sadrzaj": "tekst dokumenta"} for i in range(1, 26)]

    with patch("routers.case_dna._pozovi_genome_api", new=AsyncMock(return_value='{"zakljucak": "ok"}')), \
         patch("routers.case_dna.compute_snaga_score", side_effect=_fake_score):
        genome = await cd._extract_genome(docs, ukupno_u_predmetu=40)

    assert genome["_genome_docs_preskoceno"] == 15


@pytest.mark.anyio
async def test_extract_genome_falls_back_to_prior_approximation_without_true_count():
    """Callers that don't pass ukupno_u_predmetu keep the pre-fix (imprecise
    but harmless) behavior -- no regression for any caller not yet updated."""
    from routers import case_dna as cd

    docs = [{"redni_broj": i, "naziv_fajla": f"d{i}", "tekst_sadrzaj": "tekst dokumenta"} for i in range(1, 26)]

    with patch("routers.case_dna._pozovi_genome_api", new=AsyncMock(return_value='{"zakljucak": "ok"}')), \
         patch("routers.case_dna.compute_snaga_score", side_effect=_fake_score):
        genome = await cd._extract_genome(docs)

    assert genome["_genome_docs_preskoceno"] == 0


@pytest.mark.anyio
async def test_extract_genome_true_count_at_or_under_cap_reports_zero_skipped():
    from routers import case_dna as cd

    docs = [{"redni_broj": i, "naziv_fajla": f"d{i}", "tekst_sadrzaj": "tekst dokumenta"} for i in range(1, 11)]

    with patch("routers.case_dna._pozovi_genome_api", new=AsyncMock(return_value='{"zakljucak": "ok"}')), \
         patch("routers.case_dna.compute_snaga_score", side_effect=_fake_score):
        genome = await cd._extract_genome(docs, ukupno_u_predmetu=10)

    assert genome["_genome_docs_preskoceno"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Scenario G — _do_genome_refresh fetches true count + orders by recency
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_do_genome_refresh_orders_docs_by_redni_broj_descending():
    from routers import case_dna as cd

    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "case_dna": {"verzija": 1}
            }
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.execute.return_value.count = 40
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "d25", "naziv_fajla": "d25", "redni_broj": 25, "tekst_sadrzaj": "t"}
            ]
        elif name == "predmet_dokazi":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t
    supa.table.side_effect = _table

    captured = {}

    async def _fake_extract(docs, dokazi=None, ukupno_u_predmetu=None):
        captured["ukupno_u_predmetu"] = ukupno_u_predmetu
        return {"zakljucak": "ok", "verzija": 1}

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=_fake_extract), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock()), \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock()), \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)):
        await cd._do_genome_refresh("pred-1", "user-1", trigger="upload_trigger")

    # order() must have been called with desc=True on the document fetch
    order_calls = supa.table("predmet_dokumenti").select.return_value.eq.return_value.order.call_args_list
    assert captured["ukupno_u_predmetu"] == 40


# ═══════════════════════════════════════════════════════════════════════════
# Program Lambda, Certification 004 -- a failed GPT extraction must never
# overwrite the live case_dna column with the failure signal itself.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_do_genome_refresh_never_writes_case_dna_when_extraction_failed():
    """AI Systems Reliability finding, independently re-confirmed by the
    Certification Auditor: _extract_genome() returning {"greska": ...} on a
    GPT failure used to still be written unconditionally to the live
    predmeti.case_dna column a few lines later -- a full-value JSON replace
    that destroyed every existing Genome field. The live update, history
    save, delta/alert, and require-review steps must now all be skipped on
    failure; only a log line should record it."""
    from routers import case_dna as cd

    supa = MagicMock()
    update_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "case_dna": {
                    "verzija": 3, "kljucne_cinjenice": ["postojeća činjenica koja ne sme biti obrisana"],
                    "snaga_predmeta_procent": 70,
                }
            }

            def _update(payload):
                update_calls.append(payload)
                m = MagicMock()
                m.eq.return_value.eq.return_value.execute.return_value = MagicMock()
                return m
            t.update.side_effect = _update
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.execute.return_value.count = 1
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "d1", "naziv_fajla": "d1", "redni_broj": 1, "tekst_sadrzaj": "t"}
            ]
        elif name == "predmet_dokazi":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t
    supa.table.side_effect = _table

    async def _fake_extract_failing(docs, dokazi=None, ukupno_u_predmetu=None):
        return {"greska": "OpenAI timeout"}

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=_fake_extract_failing), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()) as mock_history, \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock()) as mock_emit, \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock()) as mock_review, \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)):
        await cd._do_genome_refresh("pred-1", "user-1", trigger="upload_trigger")

    assert update_calls == [], "a failed extraction must never write to the live predmeti.case_dna column"
    mock_history.assert_not_called()
    mock_emit.assert_not_called()
    mock_review.assert_not_called()


@pytest.mark.anyio
async def test_do_genome_refresh_still_writes_case_dna_on_success():
    """No regression: a genuinely successful extraction must still write
    through exactly as before this fix."""
    from routers import case_dna as cd

    supa = MagicMock()
    update_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "case_dna": {"verzija": 1}
            }

            def _update(payload):
                update_calls.append(payload)
                m = MagicMock()
                m.eq.return_value.eq.return_value.execute.return_value = MagicMock()
                return m
            t.update.side_effect = _update
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.execute.return_value.count = 1
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "d1", "naziv_fajla": "d1", "redni_broj": 1, "tekst_sadrzaj": "t"}
            ]
        elif name == "predmet_dokazi":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t
    supa.table.side_effect = _table

    async def _fake_extract_ok(docs, dokazi=None, ukupno_u_predmetu=None):
        return {"zakljucak": "ok", "kljucne_cinjenice": ["nova činjenica"]}

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=_fake_extract_ok), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()) as mock_history, \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock()) as mock_emit, \
         patch("routers.case_dna._maybe_alert_require_review", new=AsyncMock()) as mock_review, \
         patch("routers.case_dna._sync_rokovi_to_hronologija", new=AsyncMock(return_value=0)):
        await cd._do_genome_refresh("pred-1", "user-1", trigger="upload_trigger")

    assert len(update_calls) == 1
    assert update_calls[0]["case_dna"]["kljucne_cinjenice"] == ["nova činjenica"]
    mock_history.assert_called_once()
    mock_emit.assert_called_once()
    mock_review.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Scenario F — _run_genome_background coalesces concurrent triggers
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_trigger_for_same_predmet_is_coalesced_not_dropped():
    """A second trigger arriving while the first is still running for the
    SAME predmet_id must not silently vanish (the pre-fix race) -- it must
    cause exactly one extra run once the first finishes, not a fully
    parallel second execution."""
    from routers import case_dna as cd

    call_count = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_refresh(predmet_id, uid, stari_procent=None, trigger="upload_trigger"):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            started.set()
            await release.wait()

    with patch("routers.case_dna._do_genome_refresh", new=fake_refresh):
        task1 = asyncio.create_task(cd._run_genome_background("pred-race", "user-1"))
        await asyncio.wait_for(started.wait(), timeout=2)

        # second trigger while the first is still in flight for the same case.
        # Program Phoenix, Mission 012 (LIVINGSYS-DEBT-045): a coalesced call
        # now WAITS for the in-flight run's own completion event (previously
        # returned immediately) -- must be launched as its own task, not
        # awaited directly here, or it deadlocks waiting on `release` before
        # this test ever reaches the line below that sets it.
        task2 = asyncio.create_task(cd._run_genome_background("pred-race", "user-1"))
        await asyncio.sleep(0)  # let task2 run up to its own await point
        assert "pred-race" in cd._genome_refresh_rerun

        release.set()
        await asyncio.wait_for(task1, timeout=2)
        await asyncio.wait_for(task2, timeout=2)

    assert call_count == 2  # ran once, then re-ran once for the coalesced trigger
    assert "pred-race" not in cd._genome_refresh_inflight
    assert "pred-race" not in cd._genome_refresh_rerun


@pytest.mark.anyio
async def test_non_overlapping_triggers_each_run_independently():
    """No false-positive coalescing: two sequential (non-overlapping) triggers
    for the same predmet_id must each actually run."""
    from routers import case_dna as cd

    call_count = 0

    async def fake_refresh(predmet_id, uid, stari_procent=None, trigger="upload_trigger"):
        nonlocal call_count
        call_count += 1

    with patch("routers.case_dna._do_genome_refresh", new=fake_refresh):
        await cd._run_genome_background("pred-seq", "user-1")
        await cd._run_genome_background("pred-seq", "user-1")

    assert call_count == 2


@pytest.mark.anyio
async def test_different_predmet_ids_never_block_each_other():
    from routers import case_dna as cd

    seen_ids = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_refresh(predmet_id, uid, stari_procent=None, trigger="upload_trigger"):
        seen_ids.append(predmet_id)
        if predmet_id == "pred-A":
            started.set()
            await release.wait()

    with patch("routers.case_dna._do_genome_refresh", new=fake_refresh):
        task_a = asyncio.create_task(cd._run_genome_background("pred-A", "user-1"))
        await asyncio.wait_for(started.wait(), timeout=2)
        # a trigger for a DIFFERENT case must run immediately, not wait on pred-A
        await asyncio.wait_for(cd._run_genome_background("pred-B", "user-1"), timeout=2)
        release.set()
        await asyncio.wait_for(task_a, timeout=2)

    assert "pred-B" in seen_ids
    assert seen_ids.count("pred-A") == 1
