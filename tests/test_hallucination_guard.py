# -*- coding: utf-8 -*-
"""
Hallucination guard tests — Fix 1 (hard refusal) + Fix 2 (system prompt)

Fix 1: When a query explicitly cites a specific article and that article
       is absent from the Pinecone corpus, ask_agent must return the
       HALLUCINATION_REFUSAL_TEXT verbatim without calling the LLM.

Fix 2: HALLUCINATION_REFUSAL_TEXT must be present in SYSTEM_PROMPT_DEFINICIJA.
"""

import sys
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.retrieve import ekstrakcija_clana

# test_doc_pitanje_api.py (d < h alphabetically) installs a mock main via
# sys.modules.setdefault() before this file is collected. Stash that mock,
# import the real module to capture references, then restore the mock so that
# test_doc_pitanje_api's test functions can still use sys.modules["main"].
_stashed_mock = sys.modules.pop("main", None)
import main as _real_main
ask_agent = _real_main.ask_agent
del sys.modules["main"]
if _stashed_mock is not None:
    sys.modules["main"] = _stashed_mock


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 1: ekstrakcija_clana — 8 pattern detection tests (4 formats × 2 laws)
# ═══════════════════════════════════════════════════════════════════════════

class TestEkstrakcijaClanaBehavior:
    """Pattern detection: 4 formats × 2 laws = 8 cases."""

    # ── ZOO (zakon o obligacionim odnosima) ───────────────────────────────

    def test_format1_clan_then_code_zoo(self):
        assert ekstrakcija_clana("čl. 175 ZOO") == ("Član 175", "zakon o obligacionim odnosima")

    def test_format2_code_then_clan_zoo(self):
        assert ekstrakcija_clana("ZOO čl. 175") == ("Član 175", "zakon o obligacionim odnosima")

    def test_format3_clan_then_fullname_zoo(self):
        assert ekstrakcija_clana("čl. 175 zakon o obligacionim odnosima") == (
            "Član 175", "zakon o obligacionim odnosima"
        )

    def test_format4_fullname_then_clan_zoo(self):
        assert ekstrakcija_clana("zakon o obligacionim odnosima čl. 175") == (
            "Član 175", "zakon o obligacionim odnosima"
        )

    # ── ZR (zakon o radu) ─────────────────────────────────────────────────

    def test_format1_clan_then_code_zr(self):
        assert ekstrakcija_clana("čl. 27 ZR") == ("Član 27", "zakon o radu")

    def test_format2_code_then_clan_zr(self):
        assert ekstrakcija_clana("ZR čl. 27") == ("Član 27", "zakon o radu")

    def test_format3_clan_then_fullname_zr(self):
        assert ekstrakcija_clana("čl. 27 zakon o radu") == ("Član 27", "zakon o radu")

    def test_format4_fullname_then_clan_zr(self):
        assert ekstrakcija_clana("zakon o radu čl. 27") == ("Član 27", "zakon o radu")

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_no_article_reference_returns_none(self):
        assert ekstrakcija_clana("šta je naknada štete po ZOO") == (None, None)

    def test_plain_question_no_article(self):
        assert ekstrakcija_clana("kako se razvodi brak") == (None, None)


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 2: Hard refusal behavior in ask_agent (Fix 1)
# ═══════════════════════════════════════════════════════════════════════════

def _make_retrieve_meta(confidence: str = "HIGH") -> tuple:
    docs = ["Zakon o obligacionim odnosima, Član 200: Svako ko drugome prouzrokuje štetu dužan je da je naknadi." * 2]
    meta = {
        "confidence": confidence,
        "top_score": 0.71,
        "top_article": "Član 200",
        "top_law": "zakon o obligacionim odnosima",
        "doc_passages": [],
        "praksa_matches": [],
    }
    return docs, meta


class TestHardRefusal:

    def test_missing_article_returns_refusal_text(self):
        """Član 175 ZOO absent from corpus → HALLUCINATION_REFUSAL_TEXT returned."""
        docs, meta = _make_retrieve_meta("HIGH")

        with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
             patch.object(_real_main, "ekstrakcija_clana",
                          return_value=("Član 175", "zakon o obligacionim odnosima")), \
             patch.object(_real_main, "_direktan_fetch_clana", return_value=[]) as mock_fetch, \
             patch.object(_real_main, "_pozovi_openai") as mock_llm:

            result = ask_agent("Šta kaže Član 175 ZOO?")

        assert result["status"] == "success"
        assert result["data"] == _real_main.HALLUCINATION_REFUSAL_TEXT
        assert result["confidence"] == "LOW"
        mock_llm.assert_not_called()

    def test_missing_article_high_number_zr(self):
        """Član 9999 ZR not in corpus → hard refusal, LLM not called."""
        docs, meta = _make_retrieve_meta("HIGH")
        meta["top_law"] = "zakon o radu"

        with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
             patch.object(_real_main, "ekstrakcija_clana",
                          return_value=("Član 9999", "zakon o radu")), \
             patch.object(_real_main, "_direktan_fetch_clana", return_value=[]), \
             patch.object(_real_main, "_pozovi_openai") as mock_llm:

            result = ask_agent("Šta kaže Član 9999 ZR?")

        assert result["data"] == _real_main.HALLUCINATION_REFUSAL_TEXT
        mock_llm.assert_not_called()

    def test_existing_article_not_refused(self):
        """When _direktan_fetch_clana returns a match, normal LLM flow continues."""
        docs, meta = _make_retrieve_meta("HIGH")
        fake_match = MagicMock()
        fake_match.metadata = {"law": "zakon o obligacionim odnosima", "article": "Član 154",
                               "text": "Svako ko drugome prouzrokuje štetu dužan je da je naknadi."}
        fake_match.id = "zoo-clan-154"
        fake_match.score = 0.85

        with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
             patch.object(_real_main, "ekstrakcija_clana",
                          return_value=("Član 154", "zakon o obligacionim odnosima")), \
             patch.object(_real_main, "_direktan_fetch_clana", return_value=[fake_match]), \
             patch.object(_real_main, "_pozovi_openai",
                          return_value="Prema ZOO čl. 154, svako ko prouzrokuje štetu dužan je naknadi.") as mock_llm, \
             patch.object(_real_main, "_proveri_halucinaciju", return_value=(True, "")), \
             patch.object(_real_main, "_verifikuj_pravne_greske", return_value=(True, "")):

            result = ask_agent("Šta kaže Član 154 ZOO?")

        assert result["data"] != _real_main.HALLUCINATION_REFUSAL_TEXT
        mock_llm.assert_called()

    def test_no_article_reference_skips_guard(self):
        """Query without explicit article cite skips guard entirely and proceeds normally."""
        docs, meta = _make_retrieve_meta("HIGH")

        with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
             patch.object(_real_main, "ekstrakcija_clana", return_value=(None, None)), \
             patch.object(_real_main, "_direktan_fetch_clana") as mock_fetch, \
             patch.object(_real_main, "_pozovi_openai",
                          return_value="Naknada štete regulisana je ZOO.") as mock_llm, \
             patch.object(_real_main, "_proveri_halucinaciju", return_value=(True, "")), \
             patch.object(_real_main, "_verifikuj_pravne_greske", return_value=(True, "")):

            result = ask_agent("Šta je naknada štete?")

        mock_fetch.assert_not_called()
        assert result["data"] != _real_main.HALLUCINATION_REFUSAL_TEXT


# ═══════════════════════════════════════════════════════════════════════════
# SEKCIJA 3: Fix 2 — system prompt hardening
# ═══════════════════════════════════════════════════════════════════════════

class TestSystemPromptHardening:

    def test_refusal_text_in_definicija_prompt(self):
        """HALLUCINATION_REFUSAL_TEXT must be appended to SYSTEM_PROMPT_DEFINICIJA."""
        assert _real_main.HALLUCINATION_REFUSAL_TEXT in _real_main.SYSTEM_PROMPT_DEFINICIJA

    def test_refusal_text_not_empty(self):
        assert len(_real_main.HALLUCINATION_REFUSAL_TEXT) > 50
