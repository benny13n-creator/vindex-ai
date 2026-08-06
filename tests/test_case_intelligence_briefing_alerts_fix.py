# -*- coding: utf-8 -*-
"""
Program Gamma (2026-08-04) -- routers/case_intelligence.py::_gather_case_data
selected columns that do not exist on proactive_alerts (tekst_alerta/
tip_alerta/hitnost -- real schema is tip/naslov/opis/urgentnost, per
migrations/036_decision_log.sql:40-51). This is the same class of mistake
already found-and-fixed once on case_dna.py (2026-07-18), unfixed here, and
reachable from a live UI button since Mission IF-002 (2026-08-03). The
enclosing asyncio.gather had no return_exceptions=True, so this almost
certainly 500'd POST /predmeti/{id}/briefing on every call. Found
independently by 2 Program Gamma domain forks (Genome/Evidence/Compare and
Risk/Task/Dashboard/Alerts).

These tests prove: (1) the query now uses real column names, (2) a failing
sub-query degrades gracefully instead of 500ing the whole endpoint (negative
control against the exact pre-fix shape), (3) alert text renders correctly
using the real field names.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/intelligence/predmeti/predmet-1/briefing", "app": MagicMock(), "state": MagicMock(),
             "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _resp(content: str):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


def _chain(data=None, raise_exc=None):
    c = MagicMock()
    for attr in ["select", "eq", "in_", "order", "limit", "maybe_single", "insert"]:
        setattr(c, attr, MagicMock(return_value=c))
    if raise_exc is not None:
        c.execute = MagicMock(side_effect=raise_exc)
    else:
        c.execute = MagicMock(return_value=MagicMock(data=data))
    return c


def _make_supa(alerts_data=None, alerts_raises=None):
    predmeti_chain = _chain(data={"naziv": "Test predmet", "tip": "parnica", "status": "aktivan",
                                    "oblast_prava": "", "opis": "", "klijent_id": None, "case_dna": {}})
    empty_list_chain = _chain(data=[])
    alerts_chain = _chain(data=alerts_data, raise_exc=alerts_raises)
    decision_log_chain = _chain(data=[])

    tables = {
        "predmeti": predmeti_chain,
        "lessons_learned": empty_list_chain,
        "firm_dna": empty_list_chain,
        "case_patterns": empty_list_chain,
        "proactive_alerts": alerts_chain,
        "decision_log": decision_log_chain,
    }
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda name: tables.get(name, empty_list_chain))
    return supa


@pytest.mark.anyio
async def test_briefing_query_uses_real_alert_columns_not_stale_ones():
    """proactive_alerts .select() must request tip/opis/urgentnost, never the
    nonexistent tekst_alerta/tip_alerta/hitnost."""
    from routers import case_intelligence as ci

    supa = _make_supa(alerts_data=[{"tip": "rok", "opis": "Rok istice za 2 dana", "urgentnost": "visoka"}])

    with patch.object(ci, "_get_supa", return_value=supa), \
         patch.object(ci, "_pozovi_briefing_api", new=AsyncMock(return_value=_resp(json.dumps({
             "sledeci_korak": "Podneti odgovor na tuzbu", "hitnost": "ovu_nedelju", "razlog": "x",
             "pouzdanost_briefinga": "SREDNJA",
         })))), \
         patch.object(ci.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await ci.case_intelligence_briefing(
            _req(), "predmet-1", user={"user_id": "u1", "email": "a@b.com"},
        )

    alerts_chain = supa.table("proactive_alerts")
    select_call_args = alerts_chain.select.call_args[0][0]
    assert "tekst_alerta" not in select_call_args
    assert "tip_alerta" not in select_call_args
    assert "hitnost" not in select_call_args
    assert "opis" in select_call_args and "urgentnost" in select_call_args
    assert result["izvori"]["alertova"] == 1


@pytest.mark.anyio
async def test_briefing_survives_alerts_subquery_failure_instead_of_500():
    """Negative control against the exact pre-fix shape: if the alerts
    sub-query throws (e.g. a schema mismatch, reproducing the original bug),
    the endpoint must degrade (empty alerts) rather than propagate a 500."""
    from routers import case_intelligence as ci

    supa = _make_supa(alerts_raises=Exception('column "proactive_alerts.hitnost" does not exist'))

    with patch.object(ci, "_get_supa", return_value=supa), \
         patch.object(ci, "_pozovi_briefing_api", new=AsyncMock(return_value=_resp(json.dumps({
             "sledeci_korak": "Podneti odgovor na tuzbu", "hitnost": "ovu_nedelju", "razlog": "x",
             "pouzdanost_briefinga": "SREDNJA",
         })))), \
         patch.object(ci.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await ci.case_intelligence_briefing(
            _req(), "predmet-1", user={"user_id": "u1", "email": "a@b.com"},
        )

    # Degraded, not crashed -- alerts section is empty, everything else still works.
    assert result["izvori"]["alertova"] == 0
    assert result["briefing"]["sledeci_korak"] == "Podneti odgovor na tuzbu"


@pytest.mark.anyio
async def test_briefing_context_text_renders_real_alert_fields():
    """_build_context_text must read opis/urgentnost, not the old field names
    (which would silently render as empty strings/'?' even on a successful
    query if the render-side field names were left stale)."""
    from routers import case_intelligence as ci

    data = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "oblast_prava": "", "case_dna": {}},
        "lekcije": [], "firm_dna": [], "case_patterns": [],
        "alertovi": [{"tip": "rok", "opis": "Rok istice za 2 dana", "urgentnost": "visoka"}],
        "odluke": [], "komunikacioni_profil": {}, "knowledge_profili": [],
    }
    text = ci._build_context_text(data)
    assert "visoka" in text
    assert "Rok istice za 2 dana" in text
    assert "?" not in text.split("AKTIVNI ALERTOVI:")[1].split("\n")[1]


def test_context_text_includes_documents_evidence_actions_deadlines_program_tau_002():
    """Program Tau, Master Sprint 002 (2026-08-06): CONTEXT_BUILDER_REGISTRY.md
    found this briefing had ZERO access to predmet_dokumenti/predmet_dokazi/
    case_actions/rocista. Proves the fix: when build_case_context()'s own
    output is present under data['case_context'], its documents/evidence/
    open-actions/deadlines now render into the GPT-facing text."""
    from routers import case_intelligence as ci

    data = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "oblast_prava": "", "case_dna": {}},
        "lekcije": [], "firm_dna": [], "case_patterns": [],
        "alertovi": [], "odluke": [], "komunikacioni_profil": {}, "knowledge_profili": [],
        "case_context": {
            "relevant_documents": {"value": {
                "included": [{"dokument_id": "d1", "naziv": "ugovor.pdf", "excerpt": "Član 1. Predaja u posed."}],
                "not_included_but_retrievable": [], "total_documents": 1,
            }},
            "evidence_graph": {"value": {"ukupno_dokaza": 3, "po_kategoriji": {"pisani_dokaz": {"broj": 3}}}},
            "active_actions": {"value": [{"prioritet": "high", "razlog": "Pribaviti ugovor", "rok": "2026-09-01"}]},
            "deadlines": {"value": [{"sud": "Osnovni sud", "datum": "2026-09-15", "status": "zakazano"}]},
        },
    }
    text = ci._build_context_text(data)
    assert "ugovor.pdf" in text
    assert "Član 1. Predaja u posed." in text
    assert "3 ukupno" in text
    assert "Pribaviti ugovor" in text
    assert "Osnovni sud" in text


def test_context_text_omits_new_sections_when_case_context_missing():
    """Backward compatibility: no crash, no empty section headers, when
    data['case_context'] is absent (e.g. build_case_context() itself failed
    and was degraded to {} by _gather_case_data's own fail-soft handling)."""
    from routers import case_intelligence as ci

    data = {
        "predmet": {"naziv": "Test", "tip": "parnica", "status": "aktivan", "oblast_prava": "", "case_dna": {}},
        "lekcije": [], "firm_dna": [], "case_patterns": [],
        "alertovi": [], "odluke": [], "komunikacioni_profil": {}, "knowledge_profili": [],
    }
    text = ci._build_context_text(data)
    assert "DOKUMENTI U DOSIJEU" not in text
    assert "DOKAZI:" not in text
    assert "OTVORENE AKCIJE" not in text
