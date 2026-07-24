# -*- coding: utf-8 -*-
"""
Regression tests — Celina 2: Court Predictor & Case Commander
(Risk Analysis & Case DNA) (2026-07-24).

1. routers/court_predictor.py:
   - RAG izolacija ispravljena: retrieve_sudska_praksa (Celina 1 re-rank)
     umesto direktnih _pretraga_praksa/_ugradi_query poziva.
   - prediktuj_ishod/battle_report sada stvarno pretražuju sudsku praksu
     (pre ovoga: sistemski prompt je TVRDIO da koristi praksu, a nikad nije).
   - prediktuj_ishod ima strukturiran JSON izlaz (procenat_min/max) umesto
     samo slobodnog teksta.
   - Bug fix: meta.get("tekst")/.page_content (nepostojeći ključ/atribut) →
     meta.get("text")/parent_text -- 3 mesta su ranije UVEK slala prazan
     tekst modelu uprkos "uspešnom" RAG pozivu.
   - @llm_retry dodat na svih 7 direktnih OpenAI poziva.
2. routers/case_dna.py:
   - _extract_genome: docs[:8] + tekst[:4500] → budžetirano uzorkovanje
     (do 25 dokumenata, do 60000 ukupno znakova), sa transparentnim
     _genome_docs_preskoceno brojačem.
   - @llm_retry na _extract_genome i compare_docs OpenAI pozivima.
3. routers/case_commander.py:
   - _formatiraj_kontekst: dokumenti sada uključuju STVARAN sadržaj
     (tekst_sadrzaj), ne samo naziv fajla -- ranije je Case Commander bio
     potpuno slep na sadržaj dokumenata.
   - @llm_retry + fail-soft try/except na sva 4 OpenAI poziva.
"""
import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _fake_chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


# ─── 1a. court_predictor.py: RAG dereferencing bug fix ────────────────────

def test_argument_reputation_koristi_retrieve_sudska_praksa_ne_niskonivoovski():
    """court_predictor.py mora koristiti javni retrieve_sudska_praksa
    (Celina 1 re-rank), ne direktne _pretraga_praksa/_ugradi_query pozive."""
    import routers.court_predictor as cp
    assert hasattr(cp, "retrieve_sudska_praksa")
    assert not hasattr(cp, "_pretraga_praksa")
    assert not hasattr(cp, "_ugradi_query")


def test_rag_praksa_blok_koristi_ispravan_metadata_kljuc():
    """Regresioni test za otkriveni bug: meta.get('tekst') (pogrešan ključ)
    i .page_content (ne postoji na Pinecone match objektima) su ranije UVEK
    davali prazan tekst. Mora čitati meta['text']."""
    from routers.court_predictor import _rag_praksa_blok

    mock_match = MagicMock()
    mock_match.metadata = {"court": "Osnovni sud", "decision_number": "P 1/2025", "text": "Stvaran tekst odluke o otkaznom roku."}
    del mock_match.page_content  # simulira pravi Pinecone match objekat (nema .page_content)

    with patch("routers.court_predictor.retrieve_sudska_praksa", return_value=[mock_match]):
        blok = _rag_praksa_blok("otkazni rok", 5)

    assert "Stvaran tekst odluke o otkaznom roku." in blok


def test_rag_praksa_blok_prazno_kad_rag_nedostupan():
    from routers.court_predictor import _rag_praksa_blok
    with patch("routers.court_predictor._RAG_AVAILABLE", False):
        assert _rag_praksa_blok("test", 5) == ""


def test_rag_praksa_blok_fail_soft_na_gresku():
    from routers.court_predictor import _rag_praksa_blok
    with patch("routers.court_predictor.retrieve_sudska_praksa", side_effect=Exception("boom")):
        assert _rag_praksa_blok("test", 5) == ""


# ─── 1b. court_predictor.py: llm_retry na svih 7 poziva ───────────────────

def _assert_retries_then_succeeds(fn, *args):
    from openai import RateLimitError
    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"ok": true}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = fn(client, *args)

    assert calls["n"] == 3
    return out


def test_predictor_api_retry():
    from routers.court_predictor import _pozovi_predictor_api
    _assert_retries_then_succeeds(_pozovi_predictor_api, "prompt")


def test_battle_report_api_retry():
    from routers.court_predictor import _pozovi_battle_report_api
    _assert_retries_then_succeeds(_pozovi_battle_report_api, "prompt")


def test_hearing_prep_api_retry():
    from routers.court_predictor import _pozovi_hearing_prep_api
    _assert_retries_then_succeeds(_pozovi_hearing_prep_api, "prompt")


def test_arg_reputation_api_retry():
    from routers.court_predictor import _pozovi_arg_reputation_api
    _assert_retries_then_succeeds(_pozovi_arg_reputation_api, "prompt")


def test_judge_profile_api_retry():
    from routers.court_predictor import _pozovi_judge_profile_api
    _assert_retries_then_succeeds(_pozovi_judge_profile_api, "prompt")


def test_opponent_intel_api_retry():
    from routers.court_predictor import _pozovi_opponent_intel_api
    _assert_retries_then_succeeds(_pozovi_opponent_intel_api, "prompt")


def test_confidence_api_retry():
    from routers.court_predictor import _pozovi_confidence_api
    _assert_retries_then_succeeds(_pozovi_confidence_api, "prompt")


def test_predictor_api_ne_ponavlja_bad_request():
    from routers.court_predictor import _pozovi_predictor_api
    from openai import BadRequestError
    import pytest

    calls = {"n": 0}
    def _side_effect(*a, **kw):
        calls["n"] += 1
        raise BadRequestError("bad", response=MagicMock(status_code=400, headers={}), body=None)

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        with pytest.raises(BadRequestError):
            _pozovi_predictor_api(client, "prompt")
    assert calls["n"] == 1


# ─── 2a. case_dna.py: _extract_genome budžetiranje ────────────────────────

def _fake_dok(rn, tekst, naziv=None):
    return {"redni_broj": rn, "naziv_fajla": naziv or f"dok{rn}.pdf", "tekst_sadrzaj": tekst}


def test_extract_genome_ne_ignorise_dokumente_iznad_stare_granice_od_8():
    """Ključni regresioni test: stari docs[:8] je za predmet sa >8
    dokumenata TIHO ignorisao ostatak. Sada mora obraditi više od 8."""
    from routers.case_dna import _extract_genome

    docs = [_fake_dok(i, "Kratak sadržaj dokumenta " * 5) for i in range(1, 16)]  # 15 dokumenata

    async def fake_pozovi(client, combined, n):
        return json.dumps({"pravna_teorija": {}, "snaga_faktori": [], "_broj_dok": n})

    with patch("routers.case_dna._pozovi_genome_api", side_effect=fake_pozovi), \
         patch("openai.AsyncOpenAI"):
        result = asyncio.run(_extract_genome(docs))

    assert result["_genome_docs_count"] > 8, "mora obraditi više od starih 8 dokumenata"
    assert result["_genome_docs_count"] == 15


def test_extract_genome_transparentno_prijavljuje_preskocene_dokumente():
    """Kad predmet ima više dokumenata nego što budžet dozvoljava, mora
    eksplicitno prijaviti koliko je preskočeno (ne tiho izostaviti)."""
    from routers.case_dna import _extract_genome, _GENOME_MAX_DOCS

    docs = [_fake_dok(i, "X" * 3000) for i in range(1, _GENOME_MAX_DOCS + 10)]  # više od max

    async def fake_pozovi(client, combined, n):
        return json.dumps({"pravna_teorija": {}, "snaga_faktori": []})

    with patch("routers.case_dna._pozovi_genome_api", side_effect=fake_pozovi), \
         patch("openai.AsyncOpenAI"):
        result = asyncio.run(_extract_genome(docs))

    assert result["_genome_docs_preskoceno"] > 0


def test_extract_genome_mali_predmet_nista_ne_preskace():
    from routers.case_dna import _extract_genome

    docs = [_fake_dok(1, "Kratak dokument."), _fake_dok(2, "Drugi kratak dokument.")]

    async def fake_pozovi(client, combined, n):
        return json.dumps({"pravna_teorija": {}, "snaga_faktori": []})

    with patch("routers.case_dna._pozovi_genome_api", side_effect=fake_pozovi), \
         patch("openai.AsyncOpenAI"):
        result = asyncio.run(_extract_genome(docs))

    assert result["_genome_docs_count"] == 2
    assert result["_genome_docs_preskoceno"] == 0


def test_extract_genome_prazna_lista_dokumenata():
    from routers.case_dna import _extract_genome
    result = asyncio.run(_extract_genome([]))
    assert result == {}


def test_extract_genome_bez_teksta_vraca_gresku():
    from routers.case_dna import _extract_genome
    docs = [{"redni_broj": 1, "naziv_fajla": "prazan.pdf", "tekst_sadrzaj": ""}]
    result = asyncio.run(_extract_genome(docs))
    assert "greska" in result


# ─── 2b. case_dna.py: retry ────────────────────────────────────────────────

def test_genome_api_retry_na_rate_limit():
    from routers.case_dna import _pozovi_genome_api
    from openai import RateLimitError

    calls = {"n": 0}
    async def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"ok": true}')

    fake_client = MagicMock()
    fake_client.chat.completions.create = _side_effect

    out = asyncio.run(_pozovi_genome_api(fake_client, "combined text", 3))
    assert out == '{"ok": true}'
    assert calls["n"] == 2


def test_compare_api_retry_na_rate_limit():
    from routers.case_dna import _pozovi_compare_api
    from openai import RateLimitError

    calls = {"n": 0}
    async def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"razlike_kljucne": []}')

    fake_client = MagicMock()
    fake_client.chat.completions.create = _side_effect

    out = asyncio.run(_pozovi_compare_api(fake_client, "doc a", "doc b"))
    assert out == '{"razlike_kljucne": []}'
    assert calls["n"] == 2


# ─── 3a. case_commander.py: dokumenti sada nose sadržaj ───────────────────

def test_formatiraj_kontekst_ukljucuje_sadrzaj_dokumenata():
    """Ključni regresioni test: Case Commander je ranije video SAMO naziv
    fajla, nikad sadržaj -- potpuna slepa tačka za 'Chief of Staff' alat."""
    from routers.case_commander import _formatiraj_kontekst

    ctx = {
        "predmet": {"naziv": "Test predmet"},
        "rokovi": [],
        "dokumenta": [{"naziv_fajla": "ugovor.pdf", "tekst_sadrzaj": "Ugovorna kazna iznosi 500.000 RSD."}],
        "komentari": [],
    }
    out = _formatiraj_kontekst(ctx)
    assert "Ugovorna kazna iznosi 500.000 RSD." in out
    assert "ugovor.pdf" in out


def test_formatiraj_kontekst_dokument_bez_teksta_ne_puca():
    from routers.case_commander import _formatiraj_kontekst

    ctx = {
        "predmet": {"naziv": "Test predmet"},
        "rokovi": [],
        "dokumenta": [{"naziv_fajla": "sken.pdf", "tekst_sadrzaj": None}],
        "komentari": [],
    }
    out = _formatiraj_kontekst(ctx)
    assert "sken.pdf" in out


def test_formatiraj_kontekst_postuje_ukupan_budzet_preko_dokumenata():
    """Više dokumenata sa dugim tekstom ne sme prekoračiti total budžet --
    kasniji dokumenti moraju biti označeni kao izostavljeni, ne tiho odsečeni
    bez traga."""
    from routers.case_commander import _formatiraj_kontekst, _KONTEKST_DOK_MAX_TOTAL_CHARS

    dokumenta = [
        {"naziv_fajla": f"dok{i}.pdf", "tekst_sadrzaj": "Y" * 3000}
        for i in range(10)
    ]
    ctx = {"predmet": {"naziv": "Test"}, "rokovi": [], "dokumenta": dokumenta, "komentari": []}
    out = _formatiraj_kontekst(ctx)

    total_y = out.count("Y")
    assert total_y <= _KONTEKST_DOK_MAX_TOTAL_CHARS
    assert "budžeta" in out or "dostignut" in out.lower() or "nije prikazan" in out


# ─── 3b. case_commander.py: retry + fail-soft ─────────────────────────────

def test_commander_api_retry_na_rate_limit():
    from routers.case_commander import _pozovi_commander_api
    from openai import RateLimitError

    calls = {"n": 0}
    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response("odgovor")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = _pozovi_commander_api(client, "gpt-4o-mini", [{"role": "user", "content": "x"}], 300, 0.3)

    assert out == "odgovor"
    assert calls["n"] == 2


def test_cross_case_api_retry_na_rate_limit():
    from routers.case_commander import _pozovi_cross_case_api
    from openai import RateLimitError

    calls = {"n": 0}
    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rl", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"nalazi": []}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        client = MockOAI()
        out = _pozovi_cross_case_api(client, "prompt")

    assert out == '{"nalazi": []}'
    assert calls["n"] == 2


def test_cross_case_analiza_fail_soft_na_potpun_neuspeh():
    """Ako GPT poziv potpuno propadne (posle svih retry pokušaja), jutarnji
    brifing mora vratiti validnu strukturu sa greska=True, ne 500."""
    from routers.case_commander import _cross_case_analiza

    podaci = {
        "predmeti": [{
            "id": "abc12345", "naziv": "Test predmet", "opis": "opis",
            "tip_postupka": "gradjansko", "protivnik": "X", "sud": "Y",
            "rokovi": [], "dokumenti": [], "komentari": [],
        }],
    }

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = Exception("trajna greška")
        result = asyncio.run(_cross_case_analiza(podaci, "Advokat"))

    assert result["nalazeni"] is False
    assert result.get("greska") is True
    assert result["statistike"]["aktivnih"] == 1
