# -*- coding: utf-8 -*-
"""
Project Synapse (2026-08-03): a full cognitive audit found
routers/copilot.py::_handle_analiza_predmeta was a 4th independent
case-strength-synthesis path (alongside Case Genome, the AI Briefing, and
Matter Intelligence) -- it never read predmeti.case_dna (the Case Genome
analysis already computed for the same case in most real cases), so its own
GPT call re-derived similar conclusions from scratch, blind to a richer
analysis sitting one column away. Fixed by folding a compact Case Genome
summary into the same context string this handler already builds -- purely
additive, no restructuring of the function's control flow.

Pure unit tests -- no live Supabase, no OpenAI.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(predmet: dict):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "predmet_beleske":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        elif name == "predmet_hronologija":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_istorija":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa.table.side_effect = _table
    return supa


_FAKE_LLM_RESULT = {
    "procena": "Umerena šansa za uspeh.",
    "prednosti": [], "slabosti": [], "nedostaju": [],
    "sledeci_korak": {"opis": "Proveriti dokaze", "rok": "", "prioritet": "normalan"},
    "verovatnoca_uspeha": 55,
}


def _fake_gpt_response():
    msg = MagicMock()
    msg.message.content = json.dumps(_FAKE_LLM_RESULT)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


@pytest.mark.anyio
async def test_genome_summary_included_in_context_when_present():
    """The core fix: when case_dna exists, the GPT context string must
    include a Case Genome section built from it."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {
        "naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {
            "pravna_teorija": {"sustina_spora": "Nezakonit otkaz bez obrazloženja"},
            "snaga_predmeta_procent": 72,
            "snaga_predmeta": "Jaka",
            "najslabija_tacka": {"rizik": "Nema pisanog upozorenja pre otkaza"},
            "nedostaje": [{"dokument": "Rešenje o otkazu"}],
        },
    }
    supa = _make_supa(predmet)

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_capture_gpt):
        result = await _handle_analiza_predmeta("Kakve su nam šanse?", "pred-1", "user-1")

    assert result["tip"] == "ANALIZA_PREDMETA"
    user_ctx = captured["messages"][1]["content"]
    assert "CASE GENOME" in user_ctx
    assert "72%" in user_ctx
    assert "Nezakonit otkaz bez obrazloženja" in user_ctx
    assert "Nema pisanog upozorenja pre otkaza" in user_ctx
    assert "Rešenje o otkazu" in user_ctx


@pytest.mark.anyio
async def test_no_genome_section_when_case_dna_missing():
    """Backward compatibility: a case with no Genome yet (the realistic
    common case, per this audit's own finding that most consumers never
    populate it) must behave exactly as before -- no crash, no empty
    'CASE GENOME' section injected."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}
    supa = _make_supa(predmet)

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_capture_gpt):
        result = await _handle_analiza_predmeta("Kakve su nam šanse?", "pred-1", "user-1")

    assert result["tip"] == "ANALIZA_PREDMETA"
    user_ctx = captured["messages"][1]["content"]
    assert "CASE GENOME" not in user_ctx


@pytest.mark.anyio
async def test_no_genome_section_when_case_dna_has_error():
    """A Genome that failed to generate (greska set) must not be surfaced
    as if it were real signal."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan",
               "case_dna": {"greska": "OpenAI timeout"}}
    supa = _make_supa(predmet)

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_capture_gpt):
        await _handle_analiza_predmeta("Kakve su nam šanse?", "pred-1", "user-1")

    user_ctx = captured["messages"][1]["content"]
    assert "CASE GENOME" not in user_ctx


@pytest.mark.anyio
async def test_document_content_reaches_prompt_program_tau_002():
    """Program Tau, Master Sprint 002 (2026-08-06): CONTEXT_BUILDER_REGISTRY.md
    found this handler's own document query selected `naziv_fajla,status`
    ONLY -- GPT knew a document existed but never saw a word of its content.
    Proves the fix: real excerpted text, not just a filename, now reaches the
    GPT-facing context string."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "predmet_beleske":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {"id": "d1", "naziv_fajla": "ugovor.pdf", "created_at": "2026-08-01T00:00:00Z",
                 "tekst_sadrzaj": "Član 1. Zakupodavac se obavezuje da preda nepokretnost u posed.",
                 "status": "obradjen", "redni_broj": 1},
            ]
        elif name == "predmet_hronologija":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_istorija":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response()

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_capture_gpt):
        await _handle_analiza_predmeta("Kakve su nam šanse?", "pred-1", "user-1")

    user_ctx = captured["messages"][1]["content"]
    assert "ugovor.pdf" in user_ctx
    assert "Zakupodavac se obavezuje da preda nepokretnost u posed" in user_ctx
