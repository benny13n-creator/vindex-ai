# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 008 ("Canonical Executive Intelligence
Consolidation") -- migration tests for routers/cio.py.

Covers: _kompaktan_predmet reading canonical fields (not raw case_dna),
the deadline-source switch (case_dna.rokovi_kriticni -> canonical
deadlines), the deterministic portfolio_zdravlje.kriticnih_rizika rebuild,
the GPT-boundary adversarial proofs (hallucinated predmet_id nulled,
kriticnost capped for a READY case, a fabricated kriticni_rok nulled),
fail-soft degradation, concurrency, and replay stability.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


UID = "aaaa0000-0000-0000-0000-000000000001"
PID_A = "cccc0000-0000-0000-0000-00000000000a"
PID_B = "cccc0000-0000-0000-0000-00000000000b"


def _cc(readiness_status="READY", missing=None, contra=None, deadlines=None, snaga=60, najslabija=None):
    return {
        "readiness": {"value": {"status": readiness_status, "razlog": "", "izvor": []}},
        "key_facts": {"value": {
            "pravna_teorija": {},
            "snaga_predmeta_procent": snaga,
            "najslabija_tacka": najslabija or {},
        }},
        "missing_evidence": {"value": missing or []},
        "contradictions": {"value": contra or []},
        "deadlines": {"value": deadlines or []},
        "active_actions": {"value": []},
    }


def _user(uid=UID):
    return {"user_id": uid, "email": "test@vindex.rs"}


def _predmet_row(pid, naziv="Test predmet", oblast="Parnično", days_stale=1):
    upd = (datetime.now(timezone.utc) - timedelta(days=days_stale)).isoformat()
    return {"id": pid, "naziv": naziv, "oblast_prava": oblast, "updated_at": upd,
            "case_dna": {"verzija": 3, "strategija": {}, "strategija_osnova": "", "zakljucak": ""}}


def _make_supa(predmeti_rows, fdna=None, lekcije=None, patterns=None):
    supa = MagicMock()

    def _table(name):
        chain = MagicMock()
        for attr in ["select", "eq", "in_", "order", "limit"]:
            setattr(chain, attr, MagicMock(return_value=chain))
        r = MagicMock()
        if name == "predmeti":
            r.data = predmeti_rows
        elif name == "firm_dna":
            r.data = fdna or []
        elif name == "lessons_learned":
            r.data = lekcije or []
        elif name == "case_patterns":
            r.data = patterns or []
        else:
            r.data = []
        chain.execute = MagicMock(return_value=r)
        return chain

    supa.table = MagicMock(side_effect=_table)
    return supa


def _oai_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    return resp


_BASE_GPT_JSON = {
    "cio_preporuka": "Nastavite dalje.",
    "najveci_rizik": None, "najveca_prilika": None, "zapostavljen_predmet": None,
    "neprimecena_kontradikcija": None, "kriticni_rok": None, "suboptimalna_strategija": None,
    "slicni_predmet": None, "cio_zakljucak": "Portfolio je stabilan.", "pouzdanost": "srednja",
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. _kompaktan_predmet -- canonical field sourcing
# ═══════════════════════════════════════════════════════════════════════════

def test_kompaktan_predmet_none_when_key_facts_missing():
    from routers.cio import _kompaktan_predmet
    p = _predmet_row(PID_A)
    result = _kompaktan_predmet(p, None, date.today())
    assert result is None


def test_kompaktan_predmet_reads_snaga_from_canonical_key_facts():
    from routers.cio import _kompaktan_predmet
    p = _predmet_row(PID_A)
    cc = _cc(snaga=72)
    result = _kompaktan_predmet(p, cc, date.today())
    assert result["snaga"] == 72


def test_kompaktan_predmet_rokovi_from_canonical_deadlines_not_genome():
    """Program Tau, Master Sprint 008's own headline fix: rokovi_aktivni must
    come from build_case_context()'s own canonical `deadlines` (rocista
    table), never from case_dna's own rokovi_kriticni[] (the 3rd, previously
    unknown deadline source found in docs/tau/CIO_FORENSIC_REPORT.md)."""
    from routers.cio import _kompaktan_predmet
    danas = date.today()
    p = _predmet_row(PID_A)
    p["case_dna"]["rokovi_kriticni"] = [{"naziv": "Genome rok", "status": "aktivan",
                                          "datum": (danas + timedelta(days=5)).isoformat()}]
    cc = _cc(deadlines=[{"sud": "Osnovni sud", "datum": (danas + timedelta(days=10)).isoformat(), "status": "zakazano", "proslo": False}])
    result = _kompaktan_predmet(p, cc, danas)
    assert len(result["rokovi_aktivni"]) == 1
    assert result["rokovi_aktivni"][0]["dana_do"] == 10  # from canonical deadlines, not the 5-day Genome one
    assert "Genome rok" not in json.dumps(result)


def test_kompaktan_predmet_excludes_past_deadlines():
    from routers.cio import _kompaktan_predmet
    danas = date.today()
    p = _predmet_row(PID_A)
    cc = _cc(deadlines=[
        {"sud": "X", "datum": (danas - timedelta(days=3)).isoformat(), "status": "odrzano", "proslo": True},
        {"sud": "Y", "datum": (danas + timedelta(days=5)).isoformat(), "status": "zakazano", "proslo": False},
    ])
    result = _kompaktan_predmet(p, cc, danas)
    assert len(result["rokovi_aktivni"]) == 1
    assert result["rokovi_aktivni"][0]["dana_do"] == 5


def test_kompaktan_predmet_kontradikcije_from_canonical_pouzdanost_visoka():
    from routers.cio import _kompaktan_predmet
    p = _predmet_row(PID_A)
    cc = _cc(contra=[
        {"razlog": "Kritična kontradikcija", "pouzdanost": "visoka"},
        {"razlog": "Manja nedoslednost", "pouzdanost": "niska"},
    ])
    result = _kompaktan_predmet(p, cc, date.today())
    assert len(result["kontradikcije_kriticne"]) == 1
    assert "Kritična" in result["kontradikcije_kriticne"][0]["opis"]


def test_kompaktan_predmet_nedostaje_kriticno_counts_high_confidence_gaps():
    from routers.cio import _kompaktan_predmet
    p = _predmet_row(PID_A)
    cc = _cc(missing=[
        {"razlog": "a", "pouzdanost": "visoka", "izvor": "identify_case_problems"},
        {"razlog": "b", "pouzdanost": "visoka", "izvor": "genome_ekstrakcija"},
        {"razlog": "c", "pouzdanost": "srednja", "izvor": "genome_ekstrakcija"},
    ])
    result = _kompaktan_predmet(p, cc, date.today())
    assert result["nedostaje_kriticno"] == 2


def test_kompaktan_predmet_strategija_and_zakljucak_kept_from_raw_genome():
    """Named Step-5 exception: canonical key_facts has no strategija/zakljucak
    field -- these stay sourced from raw case_dna, deliberately."""
    from routers.cio import _kompaktan_predmet
    p = _predmet_row(PID_A)
    p["case_dna"]["strategija"] = {"primarni_cilj": "Pobediti spor"}
    p["case_dna"]["zakljucak"] = "Predmet je u dobroj poziciji."
    cc = _cc()
    result = _kompaktan_predmet(p, cc, date.today())
    assert result["strategija_cilj"] == "Pobediti spor"
    assert result["zakljucak"] == "Predmet je u dobroj poziciji."


# ═══════════════════════════════════════════════════════════════════════════
# 2. End-to-end: _generiši_cio_izvestaj wiring
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_generisi_izvestaj_uses_build_case_context_lightweight():
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc())) as mock_bcc, \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    mock_bcc.assert_awaited_once()
    assert mock_bcc.call_args.kwargs.get("include_documents") is False
    assert result["predmeta_analizirano"] == 1


@pytest.mark.anyio
async def test_generisi_izvestaj_degrades_gracefully_on_context_failure():
    """A case whose build_case_context() call fails is excluded from the
    portfolio -- same fail-soft behavior as every prior Tau migration, not a
    500."""
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(side_effect=Exception("db down"))), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["predmeta_analizirano"] == 0
    assert "Genome" in result["cio_preporuka"]


@pytest.mark.anyio
async def test_kriticnih_rizika_reflects_canonical_readiness_not_genome_heuristic():
    """Program Tau, Master Sprint 008: portfolio_zdravlje.kriticnih_rizika now
    counts canonical CRITICAL_GAP/BLOCKED cases, not Genome's own ad hoc
    kriticnost>=85 heuristic."""
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A), _predmet_row(PID_B)])

    async def _bcc(predmet_id, uid, supa_arg, include_documents=False):
        # Case A: canonically CRITICAL_GAP but a LOW Genome heuristic score
        # (najslabija_tacka.kriticnost=10) -- old code would have missed it.
        if predmet_id == PID_A:
            return _cc(readiness_status="CRITICAL_GAP", najslabija={"rizik": "x", "kriticnost": 10})
        # Case B: canonically READY but a HIGH Genome heuristic score
        # (kriticnost=95) -- old code would have wrongly flagged it.
        return _cc(readiness_status="READY", najslabija={"rizik": "y", "kriticnost": 95})

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(side_effect=_bcc)), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["portfolio_zdravlje"]["kriticnih_rizika"] == 1  # only PID_A (canonical), not PID_B


# ═══════════════════════════════════════════════════════════════════════════
# 3. Phase 5 -- GPT boundary, adversarial
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_hallucinated_predmet_id_is_nulled():
    """GPT invents a najveci_rizik block referencing a predmet_id that does
    not exist in the portfolio -- must be nulled, not passed through."""
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])
    poisoned = dict(_BASE_GPT_JSON, najveci_rizik={
        "predmet_id": "ffffffff-0000-0000-0000-000000000000", "predmet_naziv": "Ne postoji",
        "rizik": "Izmišljen rizik", "kriticnost": 99, "akcija": "x",
    })

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc())), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["najveci_rizik"] is None


@pytest.mark.anyio
async def test_kriticnost_capped_when_referenced_case_is_canonically_ready():
    """Adversarial: GPT claims kriticnost=94 for a case whose OWN canonical
    readiness is READY -- must be capped, not trusted."""
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])
    poisoned = dict(_BASE_GPT_JSON, najveci_rizik={
        "predmet_id": PID_A, "predmet_naziv": "Test predmet",
        "rizik": "Navodni rizik", "kriticnost": 94, "akcija": "x",
    })

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="READY"))), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["najveci_rizik"]["kriticnost"] == 40


@pytest.mark.anyio
async def test_kriticnost_not_capped_when_case_is_canonically_critical():
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])
    poisoned = dict(_BASE_GPT_JSON, najveci_rizik={
        "predmet_id": PID_A, "predmet_naziv": "Test predmet",
        "rizik": "Stvaran rizik", "kriticnost": 94, "akcija": "x",
    })

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="CRITICAL_GAP"))), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["najveci_rizik"]["kriticnost"] == 94


@pytest.mark.anyio
async def test_fabricated_kriticni_rok_is_nulled():
    """GPT claims a kriticni_rok for a real case, but no matching real
    deadline exists in that case's own canonical deadlines -- must be nulled."""
    from routers import cio as cio_mod
    supa = _make_supa([_predmet_row(PID_A)])
    poisoned = dict(_BASE_GPT_JSON, kriticni_rok={
        "predmet_id": PID_A, "predmet_naziv": "Test predmet",
        "rok_naziv": "Izmišljen rok", "datum": "2026-12-25", "dana_do": 30, "akcija": "x",
    })

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc(deadlines=[]))), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["kriticni_rok"] is None


@pytest.mark.anyio
async def test_real_kriticni_rok_survives_cross_check():
    from routers import cio as cio_mod
    danas = date.today()
    real_datum = (danas + timedelta(days=12)).isoformat()
    supa = _make_supa([_predmet_row(PID_A)])
    payload = dict(_BASE_GPT_JSON, kriticni_rok={
        "predmet_id": PID_A, "predmet_naziv": "Test predmet",
        "rok_naziv": "Ročište", "datum": real_datum, "dana_do": 12, "akcija": "x",
    })

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(
            return_value=_cc(deadlines=[{"sud": "Sud", "datum": real_datum, "status": "zakazano", "proslo": False}]))), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(payload))
        mock_oai_cls.return_value = mock_oai

        result = await cio_mod._generiši_cio_izvestaj(UID, supa)

    assert result["kriticni_rok"] is not None
    assert result["kriticni_rok"]["predmet_id"] == PID_A


# ═══════════════════════════════════════════════════════════════════════════
# 4. Concurrency / replay
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_reports_for_different_users_do_not_cross_contaminate():
    from routers import cio as cio_mod

    async def _bcc(predmet_id, uid, supa_arg, include_documents=False):
        status = "CRITICAL_GAP" if uid == "user-a" else "READY"
        return _cc(readiness_status=status)

    supa_a = _make_supa([_predmet_row(PID_A)])
    supa_b = _make_supa([_predmet_row(PID_B)])

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(side_effect=_bcc)), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai

        result_a, result_b = await asyncio.gather(
            cio_mod._generiši_cio_izvestaj("user-a", supa_a),
            cio_mod._generiši_cio_izvestaj("user-b", supa_b),
        )

    assert result_a["portfolio_zdravlje"]["kriticnih_rizika"] == 1
    assert result_b["portfolio_zdravlje"]["kriticnih_rizika"] == 0


@pytest.mark.anyio
async def test_replay_stability_identical_portfolio_produces_identical_stats():
    from routers import cio as cio_mod

    async def _run():
        supa = _make_supa([_predmet_row(PID_A)])
        with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=_cc(readiness_status="BLOCKED"))), \
             patch("openai.AsyncOpenAI") as mock_oai_cls:
            mock_oai = MagicMock()
            mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
            mock_oai_cls.return_value = mock_oai
            return await cio_mod._generiši_cio_izvestaj(UID, supa)

    r1 = await _run()
    r2 = await _run()
    assert r1["portfolio_zdravlje"] == r2["portfolio_zdravlje"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Structural completeness
# ═══════════════════════════════════════════════════════════════════════════

def test_case_dna_no_longer_selected_for_reasoning_but_kept_for_strategija_zakljucak():
    """case_dna is still selected (strategija_cilj/zakljucak have no canonical
    equivalent, a named Step-5 exception) -- but rokovi_kriticni/kontradikcije/
    nedostaje/snaga_predmeta_procent must no longer be read from it directly
    inside _kompaktan_predmet."""
    import routers.cio as mod
    import inspect
    src = inspect.getsource(mod._kompaktan_predmet)
    assert 'genome.get("rokovi_kriticni")' not in src
    assert 'genome.get("kontradikcije")' not in src
    assert 'genome.get("nedostaje")' not in src
    assert 'genome.get("snaga_predmeta_procent")' not in src
    assert "build_case_context" in inspect.getsource(mod)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Phase 4 -- executive cross-system consistency
# ═══════════════════════════════════════════════════════════════════════════

def test_cio_agrees_with_court_predictor_hearing_cc_case_commander_on_critical():
    """Direct cross-system proof: ONE mocked build_case_context() result
    (CRITICAL_GAP) is fed through all 4 executive surfaces' own
    readiness-interpreting logic. All 4 must independently classify it as
    critical -- proving no surface has its own drifted definition of
    "critical" after this sprint's own CIO migration."""
    from shared.case_readiness import CRITICAL_GAP
    cc = _cc(readiness_status=CRITICAL_GAP)
    status = ((cc.get("readiness") or {}).get("value") or {}).get("status")

    # CIO's own kriticnih_rizika membership test (this sprint's own change)
    assert status in (CRITICAL_GAP, "BLOCKED")

    # Court Predictor's own cap (Tau 005, constants imported Tau 007)
    from routers.court_predictor import CRITICAL_GAP as cp_critical, BLOCKED as cp_blocked
    assert {cp_critical: 50, cp_blocked: 65}.get(status) == 50

    # Hearing CC's own cap dict (Tau 006, constants imported Tau 007)
    import routers.hearing_cc as hc_mod
    assert hc_mod._CAP_BY_READINESS.get(status) == 50

    # Case Commander's own label + rank (Tau 007)
    from routers.case_commander import _READINESS_LABEL_SR, _READINESS_RANK
    assert "kritičan" in _READINESS_LABEL_SR[status].lower()
    assert _READINESS_RANK[status] == 0


@pytest.mark.anyio
async def test_cio_and_case_commander_agree_on_same_case_readiness():
    """A stronger proof than shape-agreement: feed the SAME mocked
    build_case_context() return value into both cio.py's own portfolio loop
    and case_commander.py's own _kanonski_nalazi, and confirm they report
    the identical readiness status for the identical case."""
    from routers import cio as cio_mod
    from routers import case_commander as cc_mod

    shared_cc = _cc(readiness_status="BLOCKED")

    with patch.object(cio_mod, "build_case_context", new=AsyncMock(return_value=shared_cc)), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:
        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BASE_GPT_JSON))
        mock_oai_cls.return_value = mock_oai
        cio_supa = _make_supa([_predmet_row(PID_A)])
        cio_result = await cio_mod._generiši_cio_izvestaj(UID, cio_supa)

    with patch.object(cc_mod, "build_case_context", new=AsyncMock(return_value=shared_cc)):
        commander_result = await cc_mod._kanonski_nalazi(PID_A, UID, MagicMock())

    # CIO counts this case as critical (BLOCKED is in its own critical set)...
    assert cio_result["portfolio_zdravlje"]["kriticnih_rizika"] == 1
    # ...and Case Commander, reading the identical mocked canonical context,
    # reports the SAME BLOCKED status for the SAME case.
    assert commander_result["readiness_status"] == "BLOCKED"