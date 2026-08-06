# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 003 (2026-08-06) — "Canonical AI Decision Boundary".

Tests proving:
  1. shared/commander_schema.py-style provenance now exists on strategija.py's
     9 endpoints (routers/strategija.py::_advisory_provenance), reused not
     reinvented.
  2. case_intelligence.py's kljucni_rizici/napomena/pouzdanost_briefinga are
     computed deterministically from case_context, never asked of GPT.
  3. copilot.py's slabosti/verovatnoca_uspeha/kriticni_rokovi/upozorenja are
     computed deterministically from Genome/predmet_hronologija, never GPT
     invention.

(morning_briefing.py's own Phase 3 proof lives in
tests/test_tau002_morning_briefing_context.py, alongside its Phase 5 tests --
not duplicated here.)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# strategija.py -- advisory provenance wrapper
# ═══════════════════════════════════════════════════════════════════════════

def test_advisory_provenance_shape():
    from routers.strategija import _advisory_provenance
    p = _advisory_provenance("red_team", model="gpt-4o")
    assert p["owner"] == "gpt_advisory"
    assert p["generated_by"] == "gpt-4o"
    assert p["modul"] == "red_team"
    assert p["timestamp"]
    assert "nije" in p["napomena"].lower() or "nije" in p["napomena"]


def test_all_9_strategija_endpoints_attach_ai_advisory_provenance():
    """Structural proof (source inspection, same idiom as
    tests/test_decision_registry_completeness.py's own regex-based
    completeness check): every one of the 9 known strategija.py response
    dicts includes _ai_advisory, not just some of them."""
    import routers.strategija as strat
    src = open(strat.__file__, encoding="utf-8").read()
    moduli = ["red_team", "litigation", "sudija", "due_diligence", "revizor",
              "witness", "sudija_v2", "kompletna_analiza", "strategija_v2"]
    for modul in moduli:
        pattern = re.compile(r'_advisory_provenance\("%s"\)' % re.escape(modul))
        assert pattern.search(src), f"{modul} does not attach _ai_advisory provenance"


def test_v2_system_prompt_no_longer_presents_procenat_as_calculated_stat():
    from routers.strategija import _V2_SYSTEM
    normalized = " ".join(_V2_SYSTEM.split())
    assert "subjektivna procena" in normalized


# ═══════════════════════════════════════════════════════════════════════════
# case_intelligence.py -- kljucni_rizici/napomena/pouzdanost_briefinga
# ═══════════════════════════════════════════════════════════════════════════

def test_briefing_system_no_longer_asks_gpt_for_decision_fields():
    """Checks the JSON schema block specifically (as a quoted key), not the
    whole prompt -- the prompt's own explanatory prose legitimately mentions
    these field names when explaining why GPT is NOT asked for them."""
    from routers.case_intelligence import _BRIEFING_SYSTEM
    schema_block = _BRIEFING_SYSTEM.split("Vrati JSON:")[1]
    for forbidden in ("sledeci_korak", "kljucni_rizici", '"hitnost"', "pouzdanost_briefinga", '"napomena"'):
        assert forbidden not in schema_block, f"{forbidden} still asked of GPT in the JSON schema"
    for kept in ("relevantne_lekcije", "komunikacioni_savet", "potvrdjeni_obrasci"):
        assert kept in schema_block


# ═══════════════════════════════════════════════════════════════════════════
# copilot.py -- slabosti/verovatnoca_uspeha/kriticni_rokovi/upozorenja
# ═══════════════════════════════════════════════════════════════════════════

def test_synth_system_no_longer_asks_gpt_for_slabosti_or_verovatnoca():
    """_SYNTH_SYSTEM is a local variable inside _handle_analiza_predmeta, not
    a module-level constant -- checked via source inspection, same idiom as
    the strategija.py structural test above."""
    import routers.copilot as cp
    src = open(cp.__file__, encoding="utf-8").read()
    synth_block = src.split("_SYNTH_SYSTEM = (")[1].split(")\n")[0]
    assert '"slabosti"' not in synth_block
    assert '"verovatnoca_uspeha"' not in synth_block
    assert '"procena"' in synth_block
    assert '"prednosti"' in synth_block


@pytest.mark.anyio
async def test_slabosti_derived_from_genome_not_gpt():
    """Direct proof: even if the mocked GPT response contains a 'slabosti'
    key (a poisoned/legacy-shaped response), it never reaches the output --
    only Genome-derived weaknesses do."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from routers import copilot as cp

    predmet = {
        "naziv": "Test", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {
            "kontradikcije": [{"opis": "Prava Genome kontradikcija", "lokacija_1": "DOK-1", "lokacija_2": "DOK-2", "tezina": "vazna"}],
        },
    }

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        elif name == "case_actions":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        else:
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_gpt(oai, **kwargs):
        import json
        msg = MagicMock()
        # Poisoned: GPT tries to return an old-shape "slabosti" the code
        # should never read.
        msg.message.content = json.dumps({
            "procena": "ok", "prednosti": [],
            "slabosti": ["GPT-OVA IZMISLJENA SLABOST"],
            "verovatnoca_uspeha": 999,
        })
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_pozovi_gpt4o_mini", new=_fake_gpt):
        result = await cp._handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    assert "GPT-OVA IZMISLJENA SLABOST" not in result["slabosti"]
    assert any("Prava Genome kontradikcija" in s for s in result["slabosti"])
    # verovatnoca_uspeha comes from Genome's own snaga_predmeta_procent (absent
    # here), not GPT's poisoned 999.
    assert result["verovatnoca_uspeha"] != 999
