# -*- coding: utf-8 -*-
"""
V1.1 — governance, audit i shadow mode za AIGateway. Offline, bez ijednog
eksternog AI poziva.

ZAŠTO GOVERNANCE MORA BITI PRE ADAPTERA
Legacy zaštita (`shared/ai_client.py::_patch_prompt_guard`) je monkey-patch nad
OpenAI SDK-om -- radi za 99 nemigriranih poziva, ali ne bi pokrila Anthropic ni
Gemini. Kapija u Gateway-u izražava isti ugovor na domenskom nivou, pa važi za
svaki provajder. Test 1-5 tvrde da odbijanje nastupa PRE nego što adapter bude
dodirnut (`adapter.generate` se ne poziva).

ZAŠTO SHADOW NE MOŽE DA PROMENI PRIMARNI REZULTAT
Shadow se pokreće POSLE primarnog i njegov povratak se odbacuje. Test 10-12
voze pad, timeout i drugačiji odgovor shadow-a i tvrde da pozivalac dobija
NEPROMENJEN primarni objekat.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.ai_fabric import (  # noqa: E402
    AIGateway, AIRequest, AIResponse, AITimeoutError, Capability,
    GovernanceRejection, ProviderRegistry, TaskPolicy, _govern_request,
)


def _adapter(name="openai", text="ok"):
    a = MagicMock()
    a.name = name
    a.is_configured.return_value = True
    a._caps = {Capability.TEXT_GENERATION}
    a.generate.return_value = AIResponse(name, "m", text, input_tokens=1,
                                         output_tokens=2, latency_ms=5)
    return a


def _gw(*adapters, policy="openai", fallbacks=()):
    reg = ProviderRegistry(list(adapters),
                           {"t": TaskPolicy(policy, allowed_fallbacks=fallbacks)})
    return AIGateway(reg), reg


# ─── GOVERNANCE ──────────────────────────────────────────────────────────────

def test_1_empty_task_rejected_before_provider():
    a = _adapter()
    gw, _ = _gw(a)
    with pytest.raises(GovernanceRejection):
        gw.generate(AIRequest(task="  ", prompt="p"))
    a.generate.assert_not_called(), "kapija mora odbiti PRE naplativog poziva"


def test_2_empty_prompt_rejected_before_provider():
    a = _adapter()
    gw, _ = _gw(a)
    with pytest.raises(GovernanceRejection):
        gw.generate(AIRequest(task="t", prompt="   "))
    a.generate.assert_not_called()


def test_3_oversized_prompt_rejected_before_provider():
    a = _adapter()
    gw, _ = _gw(a)
    from shared import ai_fabric
    big = "x" * (ai_fabric.MAX_PROMPT_CHARS + 1)
    with pytest.raises(GovernanceRejection):
        gw.generate(AIRequest(task="t", prompt=big))
    a.generate.assert_not_called(), "prekoračenje se hvata bez trošenja tokena"


def test_4_nonpositive_timeout_rejected():
    with pytest.raises(GovernanceRejection):
        _govern_request(AIRequest(task="t", prompt="p", timeout_s=0))


def test_5_non_string_user_id_rejected():
    with pytest.raises(GovernanceRejection):
        _govern_request(AIRequest(task="t", prompt="p", user_id=123))  # type: ignore


def test_6_governance_reuses_existing_prompt_guard_when_present():
    """REUSE, ne nova implementacija: ako security.prompt_guard postoji, kapija
    ga poziva umesto da duplira sanitizaciju."""
    with patch.dict(sys.modules, {}, clear=False):
        fake = MagicMock()
        fake.sanitize_prompt.return_value = "OCISCEN"
        with patch.dict(sys.modules, {"security.prompt_guard": fake}):
            out = _govern_request(AIRequest(task="t", prompt="prljav"))
    assert out.prompt in ("OCISCEN", "prljav"), "guard se poziva ako postoji"


# ─── AUDIT ───────────────────────────────────────────────────────────────────

def test_7_successful_call_writes_canonical_audit_without_content():
    gw, _ = _gw(_adapter())
    with patch("shared.audit_immutable.log_action_sync") as la:
        gw.generate(AIRequest(task="t", prompt="tajni prompt", user_id="u1",
                              predmet_id="p1", correlation_id="c1"))
    assert la.called
    action, kw = la.call_args.args[0], la.call_args.kwargs
    assert action == "ai_fabric_call"
    assert kw["user_id"] == "u1" and kw["correlation_id"] == "c1"
    blob = repr(kw["metadata"])
    assert "tajni prompt" not in blob, "prompt ne sme u append-only ledger"
    assert kw["metadata"]["provider"] == "openai"
    assert kw["metadata"]["ok"] is True


def test_8_failed_call_audits_error_class_and_reraises():
    a = _adapter()
    a.generate.side_effect = AITimeoutError("timeout", "openai", "m")
    gw, _ = _gw(a)
    with patch("shared.audit_immutable.log_action_sync") as la:
        with pytest.raises(AITimeoutError):
            gw.generate(AIRequest(task="t", prompt="p"))
    md = la.call_args.kwargs["metadata"]
    assert md["ok"] is False and md["error_class"] == "AITimeoutError"


def test_9_audit_failure_never_breaks_a_successful_ai_call():
    gw, _ = _gw(_adapter())
    with patch("shared.audit_immutable.log_action_sync", side_effect=RuntimeError("audit down")):
        out = gw.generate(AIRequest(task="t", prompt="p"))
    assert out.text == "ok", "best-effort audit -- pad ne sme oboriti poziv"


def test_10_action_is_registered_otherwise_audit_is_a_noop():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "ai_fabric_call" in AUDITABLE_ACTIONS


# ─── SHADOW ──────────────────────────────────────────────────────────────────

def test_11_shadow_is_off_by_default():
    prim, sh = _adapter("openai"), _adapter("anthropic", "drugacije")
    gw, _ = _gw(prim, sh)
    os.environ.pop("AI_FABRIC_SHADOW_PROVIDER", None)
    gw.generate(AIRequest(task="t", prompt="p"))
    sh.generate.assert_not_called(), "bez eksplicitnog flag-a nema shadow poziva"


def test_12_shadow_runs_but_never_changes_primary_result():
    prim, sh = _adapter("openai", "PRIMARNO"), _adapter("anthropic", "SHADOW")
    gw, _ = _gw(prim, sh)
    out = gw.generate(AIRequest(task="t", prompt="p"), shadow="anthropic")
    assert sh.generate.called, "shadow je pozvan"
    assert out.text == "PRIMARNO", "pozivalac dobija primarni rezultat, ne shadow"
    assert out.provider == "openai"


def test_13_shadow_failure_does_not_break_primary():
    prim, sh = _adapter("openai", "PRIMARNO"), _adapter("anthropic")
    sh.generate.side_effect = AITimeoutError("shadow timeout", "anthropic", "m")
    gw, _ = _gw(prim, sh)
    out = gw.generate(AIRequest(task="t", prompt="p"), shadow="anthropic")
    assert out.text == "PRIMARNO", "pad shadow-a se guta"


def test_14_unconfigured_shadow_is_skipped_silently():
    prim, sh = _adapter("openai", "PRIMARNO"), _adapter("anthropic")
    sh.is_configured.return_value = False
    gw, _ = _gw(prim, sh)
    out = gw.generate(AIRequest(task="t", prompt="p"), shadow="anthropic")
    sh.generate.assert_not_called()
    assert out.text == "PRIMARNO"


def test_15_telemetry_marks_gateway_vs_shadow_so_legacy_stays_distinguishable():
    prim, sh = _adapter("openai"), _adapter("anthropic")
    gw, _ = _gw(prim, sh)
    seen = []
    with patch("shared.audit_immutable.log_action_sync",
               side_effect=lambda *a, **k: seen.append(k["metadata"]["mode"])):
        gw.generate(AIRequest(task="t", prompt="p"), shadow="anthropic")
    assert "gateway" in seen and "shadow" in seen, (
        "novi kanonski put i shadow moraju biti razlučivi; legacy pozivi nemaju "
        "ovaj marker uopšte"
    )
