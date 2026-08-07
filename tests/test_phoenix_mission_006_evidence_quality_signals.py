# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 006 -- Evidence Quality Signals.
Closes LIVINGSYS-DEBT-009, -022.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "POST", "path": "/", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-009 — a genuine GPT classification failure was silently
# laundered into a plausible fake "ostalo" success, and reklasifikuj charged
# a credit before the background classification task even started.
# ═══════════════════════════════════════════════════════════════════════════

def test_klasifikuj_dokument_marks_genuine_failure():
    from routers.evidence import _klasifikuj_dokument

    with patch("openai.OpenAI", side_effect=Exception("API down")):
        result = _klasifikuj_dokument("dokument.pdf", "neki tekst")

    assert result["tip_dokaza"] == "ostalo"  # safe fallback value unchanged
    assert result["ai_tags"]["_klasifikacija_greska"] is True  # but now flagged


def test_klasifikuj_dokument_genuine_success_has_no_failure_flag():
    from routers.evidence import _klasifikuj_dokument

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "tip_dokaza": "ugovor", "pouzdanost": "visoka", "pravni_elementi": [],
        "ai_tags": {"stranke": []}, "kljucne_cinjenice": [],
    })))]

    with patch("openai.OpenAI", return_value=fake_client), \
         patch("routers.evidence._pozovi_evidence_api", return_value=fake_resp):
        result = _klasifikuj_dokument("ugovor.pdf", "tekst ugovora")

    assert result["tip_dokaza"] == "ugovor"
    assert "_klasifikacija_greska" not in result["ai_tags"]
    assert result["ai_tags"]["_klasifikacija_pouzdanost"] == "visoka"


@pytest.mark.anyio
async def test_reklasifikuj_skips_charge_on_genuine_failure():
    import routers.evidence as ev

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "pred-1"}]
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"naziv_fajla": "dok.pdf", "pinecone_namespace": "ns", "tekst_sadrzaj": "tekst"}
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(ev, "get_supa", return_value=supa), \
         patch.object(ev, "klasifikuj_i_sacuvaj", return_value={
             "tip_dokaza": "ostalo", "ai_tags": {"_klasifikacija_greska": True},
         }), \
         patch.object(ev, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        result = await ev.reklasifikuj(_req(), "pred-1", "dok-1", {"user_id": "u1"})

    mock_usage.consume.assert_not_awaited()
    assert result["ok"] is False


@pytest.mark.anyio
async def test_reklasifikuj_charges_on_genuine_success():
    import routers.evidence as ev

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "pred-1"}]
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"naziv_fajla": "dok.pdf", "pinecone_namespace": "ns", "tekst_sadrzaj": "tekst"}
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(ev, "get_supa", return_value=supa), \
         patch.object(ev, "klasifikuj_i_sacuvaj", return_value={
             "tip_dokaza": "ugovor", "ai_tags": {"_klasifikacija_pouzdanost": "visoka"},
         }), \
         patch.object(ev, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=99)
        result = await ev.reklasifikuj(_req(), "pred-1", "dok-1", {"user_id": "u1"})

    mock_usage.consume.assert_awaited_once()
    assert result["ok"] is True


def test_consequence_evidence_classify_logs_on_degraded_classification():
    src = open(os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py"), encoding="utf-8").read()
    marker = "async def _consequence_evidence_classify"
    block = src.split(marker, 1)[1][:5000]
    assert '_klas_rezultat.get("ai_tags", {}).get("_klasifikacija_greska")' in block
    assert "logger.warning(" in block


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-022 — evidence-type classification had no confidence gate.
# ═══════════════════════════════════════════════════════════════════════════

def test_klasifikuj_dokument_enum_guards_unrecognized_pouzdanost():
    from routers.evidence import _klasifikuj_dokument

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "tip_dokaza": "dopis", "pouzdanost": "SUPER_SIGURAN",  # out-of-schema poisoned value
        "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": [],
    })))]

    with patch("openai.OpenAI", return_value=fake_client), \
         patch("routers.evidence._pozovi_evidence_api", return_value=fake_resp):
        result = _klasifikuj_dokument("dopis.pdf", "tekst")

    # Fails safe to the least-confident bucket, same direction as every sibling
    # confidence-enum guard elsewhere in this engagement.
    assert result["ai_tags"]["_klasifikacija_pouzdanost"] == "niska"


def test_classify_system_prompt_asks_for_pouzdanost():
    from routers.evidence import _CLASSIFY_SYSTEM
    assert "pouzdanost" in _CLASSIFY_SYSTEM
    assert '"visoka" | "srednja" | "niska"' in _CLASSIFY_SYSTEM


def test_frontend_reklasifikuj_reads_real_response():
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "vindex.js"), encoding="utf-8").read()
    marker = "function evidence_reklasifikuj(dokId) {"
    block = src.split(marker, 1)[1][:900]
    assert "r.json()" in block
    assert "d.ok" in block
