# -*- coding: utf-8 -*-
"""
Regression tests — Founder Autopilot Agent (scripts/founder_agent/, 2026-07-24).

Pokriva:
  1. load_persona() učitava persona.json i sadrži očekivane ključeve.
  2. get_git_log() koristi 24h prozor, pada nazad na poslednjih N commit-a
     kad je prozor prazan (subprocess mock-ovan -- nema stvarnog git poziva).
  3. find_banned_phrase()/strip_banned_phrases() primenjuju persona.json
     pravilo o zabranjenim frazama, case-insensitive.
  4. generate_post() pokušava regenerisanje kad model prekrši pravilo, i
     sigurnosna mreža (strip_banned_phrases) garantuje da finalni tekst
     NIKAD ne sadrži zabranjenu frazu čak i ako model prekrši oba puta.
  5. write_draft() upisuje fajl bez rušenja; main() ne baca end-to-end sa
     mock-ovanim git logom i LLM pozivom.

Pure unit tests -- no live OpenAI, no real git subprocess calls.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")

import scripts.founder_agent.agent as agent  # noqa: E402


# ─── 1. persona.json ────────────────────────────────────────────────────────

def test_load_persona_reads_real_file_with_expected_keys():
    persona = agent.load_persona()
    assert persona["identity"] == "Osnivač & Glavni Arhitekta Vindex AI-ja"
    assert isinstance(persona["banned_words"], list)
    assert "Game-changer" in persona["banned_words"]
    assert "Ovu objavu je pripremio moj Founder AI Agent" in persona["signature"]
    assert isinstance(persona["key_focus_areas"], list)
    assert len(persona["key_focus_areas"]) >= 5


def test_load_persona_with_explicit_path(tmp_path):
    custom = tmp_path / "custom_persona.json"
    custom.write_text(json.dumps({"identity": "Test Persona", "banned_words": []}), encoding="utf-8")
    persona = agent.load_persona(custom)
    assert persona["identity"] == "Test Persona"


# ─── 2. git log ──────────────────────────────────────────────────────────────

def test_get_git_log_uses_24h_window_when_commits_exist():
    fake_result = MagicMock(returncode=0, stdout="abc123 | 2026-07-24 | feat: nesto novo\n", stderr="")
    with patch("subprocess.run", return_value=fake_result) as mock_run:
        log = agent.get_git_log(since_hours=24, fallback_n=15)

    assert "feat: nesto novo" in log
    call_args = mock_run.call_args[0][0]
    assert "--since" in call_args
    assert "24 hours ago" in call_args


def test_get_git_log_falls_back_when_24h_window_empty():
    empty_result = MagicMock(returncode=0, stdout="", stderr="")
    fallback_result = MagicMock(returncode=0, stdout="def456 | 2026-07-20 | fix: stariji commit\n", stderr="")

    with patch("subprocess.run", side_effect=[empty_result, fallback_result]) as mock_run:
        log = agent.get_git_log(since_hours=24, fallback_n=15)

    assert "fix: stariji commit" in log
    assert mock_run.call_count == 2
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "-15" in second_call_args


def test_get_git_log_never_raises_when_git_unavailable():
    with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
        log = agent.get_git_log()
    assert log == ""


def test_get_git_log_never_raises_on_timeout():
    import subprocess as sp
    with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="git", timeout=15)):
        log = agent.get_git_log()
    assert log == ""


# ─── 3. banned words ─────────────────────────────────────────────────────────

def test_find_banned_phrase_case_insensitive():
    banned = ["Game-changer", "Otključajte potencijal"]
    assert agent.find_banned_phrase("Ovo je pravi GAME-CHANGER za nas.", banned) == "Game-changer"
    assert agent.find_banned_phrase("Sasvim čist tehnički tekst.", banned) is None


def test_strip_banned_phrases_removes_all_occurrences():
    banned = ["Game-changer", "Predstavljamo vam"]
    tekst = "Predstavljamo vam pravi Game-changer alat. game-changer opet ovde."
    ocisceno = agent.strip_banned_phrases(tekst, banned)
    assert agent.find_banned_phrase(ocisceno, banned) is None


# ─── 4. generate_post — persona pravila + sigurnosna mreža ─────────────────

_TEST_PERSONA = {
    "identity": "Osnivač Test Kompanije",
    "tone_style": ["Direktan"],
    "banned_words": ["Game-changer", "Uzbudljive vesti"],
    "key_focus_areas": ["Testiranje"],
    "post_structure": {"hook": "H", "inzenjerska_prica": "I", "zakljucak_i_potpis": "Z"},
    "signature": "Potpis agenta.",
}


def test_generate_post_retries_once_when_banned_phrase_used():
    clean_response = "Čist tehnički tekst bez problema.\nPotpis agenta."
    dirty_response = "Ovo je pravi Game-changer trenutak!\nPotpis agenta."

    with patch.object(agent, "_pozovi_llm_api", side_effect=[dirty_response, clean_response]) as mock_llm:
        tekst = agent.generate_post("neki git log", _TEST_PERSONA)

    assert mock_llm.call_count == 2
    assert agent.find_banned_phrase(tekst, _TEST_PERSONA["banned_words"]) is None


def test_generate_post_safety_net_strips_phrase_even_if_both_attempts_fail():
    """Ako model PONOVO prekrši pravilo i posle regenerisanja, finalni tekst
    i dalje NE SME sadržati zabranjenu frazu -- ovo je hard garancija, ne
    best-effort."""
    dirty_response = "Uzbudljive vesti: novi Game-changer refaktoring.\nPotpis agenta."

    with patch.object(agent, "_pozovi_llm_api", side_effect=[dirty_response, dirty_response]) as mock_llm:
        tekst = agent.generate_post("neki git log", _TEST_PERSONA)

    assert mock_llm.call_count == 2
    assert agent.find_banned_phrase(tekst, _TEST_PERSONA["banned_words"]) is None


def test_generate_post_calls_llm_once_when_clean_on_first_try():
    clean_response = "Čist tehnički tekst.\nPotpis agenta."
    with patch.object(agent, "_pozovi_llm_api", return_value=clean_response) as mock_llm:
        tekst = agent.generate_post("neki git log", _TEST_PERSONA)

    assert mock_llm.call_count == 1
    assert tekst.strip() == clean_response.strip()


def test_build_system_prompt_includes_persona_fields():
    prompt = agent._build_system_prompt(_TEST_PERSONA)
    assert "Osnivač Test Kompanije" in prompt
    assert "Game-changer" in prompt  # navedeno kao ZABRANJENO, ne kao dozvoljeno
    assert "Potpis agenta." in prompt


# ─── 5. write_draft / main() end-to-end ─────────────────────────────────────

def test_write_draft_creates_file_and_parent_dir(tmp_path):
    out_path = tmp_path / "nested" / "latest_post.md"
    saved = agent.write_draft("Sadržaj objave.", out_path)
    assert saved == out_path
    assert out_path.read_text(encoding="utf-8").strip() == "Sadržaj objave."


def test_main_end_to_end_never_raises(tmp_path, capsys):
    fake_git_result = MagicMock(returncode=0, stdout="abc123 | 2026-07-24 | feat: test commit\n", stderr="")
    out_path = tmp_path / "latest_post.md"

    with patch("subprocess.run", return_value=fake_git_result), \
         patch.object(agent, "_pozovi_llm_api", return_value="Generisan tekst objave.\nPotpis agenta."), \
         patch("sys.argv", ["agent.py", "--out", str(out_path)]):
        agent.main()

    assert out_path.exists()
    captured = capsys.readouterr()
    assert "Generisan tekst objave." in captured.out


def test_main_exits_cleanly_when_no_git_history(capsys):
    empty_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=empty_result), \
         patch("sys.argv", ["agent.py"]):
        with pytest.raises(SystemExit) as exc_info:
            agent.main()

    assert exc_info.value.code == 1
