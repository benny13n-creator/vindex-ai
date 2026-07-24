# -*- coding: utf-8 -*-
"""
Regression tests — Faza 3: Unapređenje Drafting Engine-a (2026-07-24).

1. [IZVOR-n] mapiranje RAG dokumenata (routers/drafting.py::_izvori_kontekst).
2. Critique & Self-Correction pass (routers/drafting.py::_critique_and_refine_draft).
3. OBOGACIVANJE_PROMPTOVI (templates/podnesci.py) sadrže IZVOR-citiranje,
   stil i petitum pravila na SVIM tipovima podnesaka.
"""
import sys
import os
import json
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── [IZVOR-n] mapiranje ──────────────────────────────────────────────────────

def test_izvori_kontekst_oznacava_dokumente():
    from routers.drafting import _izvori_kontekst

    docs = ["Prvi zakonski tekst.", "Drugi zakonski tekst."]
    out = _izvori_kontekst(docs)
    assert "[IZVOR-1]\nPrvi zakonski tekst." in out
    assert "[IZVOR-2]\nDrugi zakonski tekst." in out


def test_izvori_kontekst_postuje_limit():
    from routers.drafting import _izvori_kontekst

    docs = [f"dokument {i}" for i in range(10)]
    out = _izvori_kontekst(docs, limit=4)
    assert "[IZVOR-4]" in out
    assert "[IZVOR-5]" not in out


def test_izvori_kontekst_prazna_lista():
    from routers.drafting import _izvori_kontekst

    assert _izvori_kontekst([]) == ""
    assert _izvori_kontekst(None) == ""


# ─── OBOGACIVANJE_PROMPTOVI dodaci ────────────────────────────────────────────

def test_svi_obogacivanje_promptovi_imaju_izvor_pravilo():
    from templates.podnesci import OBOGACIVANJE_PROMPTOVI, TIPOVI

    assert len(OBOGACIVANJE_PROMPTOVI) == len(TIPOVI)
    for tip, prompt in OBOGACIVANJE_PROMPTOVI.items():
        assert "[IZVOR-" in prompt, f"{tip}: nedostaje IZVOR-n pravilo"
        assert "VRHUNSKI ADVOKATSKI" in prompt, f"{tip}: nedostaje stil pravilo"
        assert "PETITUM" in prompt, f"{tip}: nedostaje petitum pravilo"


# ─── Critique & Self-Correction pass ──────────────────────────────────────────

def _fake_chat_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return resp


async def _run_critique(nacrt, kontekst="[IZVOR-1]\ntekst", tip="tuzba_naknada_stete"):
    from routers.drafting import _critique_and_refine_draft
    return await _critique_and_refine_draft(nacrt, kontekst, tip, "test-qid")


def test_critique_vraca_original_kad_nema_problema():
    import asyncio

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": False,
        "izmisljeni_navodi": [],
        "nedostaju_elementi": [],
        "ispravljen_tekst": "OVO SE NE SME KORISTITI",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        out = asyncio.run(_run_critique("ORIGINALNI NACRT"))

    assert out == "ORIGINALNI NACRT"


def test_critique_ispravlja_halucinaciju():
    import asyncio

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": True,
        "izmisljeni_navodi": ["izmišljen čl. 999 ZOO koji ne postoji u izvorima"],
        "nedostaju_elementi": [],
        "ispravljen_tekst": "ISPRAVLJEN NACRT BEZ HALUCINACIJE",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        out = asyncio.run(_run_critique("NACRT SA IZMIŠLJENIM ČL. 999"))

    assert out == "ISPRAVLJEN NACRT BEZ HALUCINACIJE"


def test_critique_dopunjava_nedostajuce_elemente():
    import asyncio

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": False,
        "izmisljeni_navodi": [],
        "nedostaju_elementi": ["nedostaje dokazni predlog"],
        "ispravljen_tekst": "NACRT SA DODATIM DOKAZNIM PREDLOGOM",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        out = asyncio.run(_run_critique("NACRT BEZ DOKAZNOG PREDLOGA"))

    assert out == "NACRT SA DODATIM DOKAZNIM PREDLOGOM"


def test_critique_fallback_na_original_ako_poziv_ne_uspe():
    """Ako critique poziv ne uspe (mrežna greška i sl.), MORA vratiti
    originalni nacrt umesto da baci izuzetak ili blokira odgovor."""
    import asyncio

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = Exception("mrežna greška")
        out = asyncio.run(_run_critique("ORIGINALNI NACRT"))

    assert out == "ORIGINALNI NACRT"


def test_critique_fallback_ako_nedostaje_ispravljen_tekst():
    """Ako model prijavi problem ali ne vrati ispravljen_tekst, ne sme
    vratiti prazan string -- mora pasti nazad na originalni nacrt."""
    import asyncio

    fake_resp = _fake_chat_response({
        "ima_izmisljenih_navoda": True,
        "izmisljeni_navodi": ["nešto sporno"],
        "nedostaju_elementi": [],
        "ispravljen_tekst": "",
    })
    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_resp
        out = asyncio.run(_run_critique("ORIGINALNI NACRT"))

    assert out == "ORIGINALNI NACRT"
