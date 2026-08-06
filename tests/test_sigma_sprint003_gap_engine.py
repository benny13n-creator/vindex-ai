# -*- coding: utf-8 -*-
"""
Program Sigma, Master Sprint 003 (2026-08-06) — "Legal Gap & Missing Evidence
Engine". Tests for shared/gap_engine.py (the new canonical normalizer over
identify_case_problems/Genome nedostaje/Genome kontradikcije) and its 2
integration points in routers/copilot.py -- proves the real, previously-
unknown bug this sprint found: Genome's own case_dna.nedostaje[] (the
platform's own canonical, holistic missing-evidence list) had 2 fully
independent competitors inside routers/copilot.py, each generating its own
GPT-derived "what's missing" list, one of them (_handle_plan_predmeta) with
ZERO Genome awareness at all. Fixed: both now read Genome's own list via
shared/gap_engine.py instead of re-deriving.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, patch

from services.event_bus import Event, EventType  # noqa: F401 -- import order avoids a circular import (see services/event_bus.py::_register_defaults)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# shared/gap_engine.py — normalizers, in isolation
# ═══════════════════════════════════════════════════════════════════════════

def test_gaps_from_case_problems_deterministic_not_hypothesis():
    from shared.gap_engine import gaps_from_case_problems, GAP_TIP_NEMA_DOKAZA

    problemi = [{"problem": "Nema uploadovanih dokaza za radni predmet", "ozbiljnost": "kritican"}]
    gaps = gaps_from_case_problems(problemi)
    assert len(gaps) == 1
    assert gaps[0]["tip"] == GAP_TIP_NEMA_DOKAZA
    assert gaps[0]["hipoteza"] is False
    assert gaps[0]["pouzdanost"] == "visoka"
    assert gaps[0]["izvor"] == "identify_case_problems"


def test_classify_case_problem_returns_none_for_unrecognized_text():
    """Program Sigma, Master Sprint 003: the shared classifier must NOT
    guess a fallback type for text it doesn't recognize -- case_actions'
    own Rule 2 (services/case_evolution.py) relies on None meaning
    'silently skip, exactly as before this sprint's own refactor'."""
    from shared.gap_engine import classify_case_problem
    assert classify_case_problem("Neki potpuno nepoznat tekst problema") is None


def test_case_actions_rule2_and_gap_engine_share_one_classifier():
    """The self-found duplication this sprint fixed: services/case_evolution.py's
    own Rule 2 must import and use shared/gap_engine.py::classify_case_problem,
    not its own independent if/elif cascade."""
    import inspect
    import services.case_evolution as ce
    source = inspect.getsource(ce)
    assert "from shared.gap_engine import classify_case_problem" in source
    assert "classify_case_problem(text)" in source


def test_gaps_from_case_problems_maps_every_known_shape():
    from shared.gap_engine import gaps_from_case_problems
    problemi = [
        {"problem": "2 kritičan rok(a) u narednih 7 dana", "ozbiljnost": "kritican"},
        {"problem": "Nedostaje dostavnica u spisu", "ozbiljnost": "vazan"},
        {"problem": "4 predstojećih rokova u narednih 30 dana — nije prioritizovano", "ozbiljnost": "vazan"},
        {"problem": "Dokazi slabe snage — nedostaje veštačenje ili dodatni svedoci", "ozbiljnost": "info"},
    ]
    gaps = gaps_from_case_problems(problemi)
    tips = [g["tip"] for g in gaps]
    assert tips == ["KRITICAN_ROK", "NEDOSTAJE_DOKUMENT", "PREDSTOJECI_ROKOVI", "DOKAZI_SLABI"]
    assert all(g["hipoteza"] is False for g in gaps)


def test_gaps_from_genome_nedostaje_is_always_a_hypothesis():
    from shared.gap_engine import gaps_from_genome_nedostaje, GAP_TIP_GENOME_NEDOSTAJE

    case_dna = {"nedostaje": [{"dokument": "Rešenje o otkazu", "hitnost": "kriticno", "opis": "Nedostaje rešenje"}]}
    gaps = gaps_from_genome_nedostaje(case_dna)
    assert len(gaps) == 1
    assert gaps[0]["tip"] == GAP_TIP_GENOME_NEDOSTAJE
    assert gaps[0]["hipoteza"] is True
    assert gaps[0]["pouzdanost"] == "visoka"  # kriticno -> visoka
    assert gaps[0]["ocekivano"] == "Rešenje o otkazu"


def test_gaps_from_genome_nedostaje_empty_on_error_or_missing():
    from shared.gap_engine import gaps_from_genome_nedostaje
    assert gaps_from_genome_nedostaje(None) == []
    assert gaps_from_genome_nedostaje({"greska": "timeout"}) == []
    assert gaps_from_genome_nedostaje({}) == []


def test_gaps_from_contradictions_carries_stable_dedupe_key():
    """Reuses Sprint 002's own contradiction identity -- 2 refreshes with
    reworded opis but the same locations must produce the same dedupe_key."""
    from shared.gap_engine import gaps_from_contradictions

    k1 = {"opis": "Datum se razlikuje", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"}
    k2 = {"opis": "Postoji neslaganje u datumu", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1", "tezina": "kriticna"}
    gaps1 = gaps_from_contradictions({"kontradikcije": [k1]})
    gaps2 = gaps_from_contradictions({"kontradikcije": [k2]})
    assert gaps1[0]["dedupe_key"] == gaps2[0]["dedupe_key"]
    assert gaps1[0]["hipoteza"] is True


def test_collect_case_gaps_aggregates_all_three_sources():
    from shared.gap_engine import collect_case_gaps

    problemi = [{"problem": "Nema uploadovanih dokaza za predmet", "ozbiljnost": "kritican"}]
    case_dna = {
        "nedostaje": [{"dokument": "Aneks ugovora", "hitnost": "vazno"}],
        "kontradikcije": [{"opis": "x", "lokacija_1": "DOK-1", "lokacija_2": "DOK-2", "tezina": "vazna"}],
    }
    gaps = collect_case_gaps(problemi, case_dna)
    assert len(gaps) == 3
    tips = {g["tip"] for g in gaps}
    assert tips == {"NEMA_DOKAZA", "GENOME_NEDOSTAJE", "KONTRADIKCIJA"}


def test_missing_evidence_labels_sorted_by_urgency_and_limited():
    from shared.gap_engine import missing_evidence_labels
    case_dna = {"nedostaje": [
        {"dokument": "C", "hitnost": "pozeljno"},
        {"dokument": "A", "hitnost": "kriticno"},
        {"dokument": "B", "hitnost": "vazno"},
        {"dokument": "D", "hitnost": "kriticno"},
    ]}
    labels = missing_evidence_labels(case_dna, limit=3)
    assert labels == ["A", "D", "B"]


def test_missing_evidence_plan_items_translates_hitnost_vocabulary():
    from shared.gap_engine import missing_evidence_plan_items
    case_dna = {"nedostaje": [{"dokument": "X", "hitnost": "kriticno"}]}
    items = missing_evidence_plan_items(case_dna, limit=6)
    assert items == [{"stavka": "X", "hitnost": "visoka"}]


# ═══════════════════════════════════════════════════════════════════════════
# routers/copilot.py — the 2 fixed handlers, proving the actual bug is closed
# ═══════════════════════════════════════════════════════════════════════════

def _make_supa(predmet: dict):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        else:
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        return t

    supa.table.side_effect = _table
    return supa


def _fake_gpt_response(payload: dict):
    msg = MagicMock()
    msg.message.content = json.dumps(payload)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


@pytest.mark.anyio
async def test_analiza_predmeta_uses_genome_nedostaje_not_the_independent_gpt_list():
    """The actual bug: GPT's own independently-generated 'nedostaju' must be
    IGNORED in favor of Genome's own canonical list when Genome exists."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {
        "naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {"nedostaje": [{"dokument": "Rešenje o otkazu", "hitnost": "kriticno"}]},
    }
    supa = _make_supa(predmet)
    gpt_payload = {
        "procena": "x", "prednosti": [], "slabosti": [],
        "nedostaju": ["Nešto sasvim drugo GPT je izmislio"],  # must be ignored
        "sledeci_korak": {}, "verovatnoca_uspeha": 50,
    }

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call):
        result = await _handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    assert result["nedostaju"] == ["Rešenje o otkazu"]


@pytest.mark.anyio
async def test_analiza_predmeta_falls_back_to_gpt_when_no_genome():
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}
    supa = _make_supa(predmet)
    gpt_payload = {
        "procena": "x", "prednosti": [], "slabosti": [],
        "nedostaju": ["GPT-ova sopstvena procena bez Genome-a"],
        "sledeci_korak": {}, "verovatnoca_uspeha": 50,
    }

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call):
        result = await _handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    assert result["nedostaju"] == ["GPT-ova sopstvena procena bez Genome-a"]


@pytest.mark.anyio
async def test_plan_predmeta_now_reads_genome_it_previously_never_fetched():
    """The more severe of the 2 bugs: _handle_plan_predmeta's own select
    never included case_dna at all -- this test proves it now does, and that
    its own 'nedostaje' is sourced from Genome, not the GPT's own guess."""
    from routers.copilot import _handle_plan_predmeta

    predmet = {
        "naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {"nedostaje": [{"dokument": "Aneks ugovora", "hitnost": "vazno"}]},
    }
    supa = _make_supa(predmet)
    gpt_payload = {
        "cilj": "x", "faze": [], "kriticni_rokovi": [],
        "nedostaje": [{"stavka": "GPT-ova sopstvena, Genome-slepa procena", "hitnost": "visoka"}],
        "upozorenja": [],
    }

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call), \
         patch("app.services.retrieve.retrieve_sudska_praksa", return_value=[]):
        result = await _handle_plan_predmeta("Plan?", "pred-1", "user-1")

    assert result["nedostaje"] == [{"stavka": "Aneks ugovora", "hitnost": "srednja"}]


@pytest.mark.anyio
async def test_plan_predmeta_falls_back_to_gpt_when_no_genome():
    from routers.copilot import _handle_plan_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}
    supa = _make_supa(predmet)
    gpt_payload = {
        "cilj": "x", "faze": [], "kriticni_rokovi": [],
        "nedostaje": [{"stavka": "GPT bez Genome-a", "hitnost": "visoka"}],
        "upozorenja": [],
    }

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call), \
         patch("app.services.retrieve.retrieve_sudska_praksa", return_value=[]):
        result = await _handle_plan_predmeta("Plan?", "pred-1", "user-1")

    assert result["nedostaje"] == [{"stavka": "GPT bez Genome-a", "hitnost": "visoka"}]
