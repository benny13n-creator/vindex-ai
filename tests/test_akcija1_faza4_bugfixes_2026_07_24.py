# -*- coding: utf-8 -*-
"""
Regression tests — Faza 4, AKCIJA 1: Hitne popravke u obradi dokumenata (2026-07-24).

1. routers/evidence_graph.py::_izgradj_kontekst — key-mismatch bug
   (d.get("tekst")/d.get("izvod") umesto stvarne kolone "tekst_sadrzaj").
2. routers/evidence.py::reklasifikuj — slao prazan string umesto teksta.
3. shared/intake_extract.py — [:4000] amputacija zamenjena _kljucne_sekcije
   (head+tail) pristupom + novi regex extract_court.
4. routers/dokument.py — log poruka usklađena sa stvarnim ponašanjem
   (nema pravog multi-pass-a).
"""
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── 1. evidence_graph.py key-mismatch fix ────────────────────────────────────

def test_izgradj_kontekst_koristi_tekst_sadrzaj_kolonu():
    from routers.evidence_graph import _izgradj_kontekst

    predmet = {"naziv": "Test predmet"}
    dokumenti = [{
        "naziv_fajla": "ugovor.pdf",
        "tip_dokaza": "ugovor",
        "tekst_sadrzaj": "Ovo je stvaran sadržaj ugovora o zakupu nepokretnosti.",
    }]
    out = _izgradj_kontekst(predmet, dokumenti, [], [])
    assert "Ovo je stvaran sadržaj ugovora" in out


def test_izgradj_kontekst_i_dalje_radi_bez_teksta():
    from routers.evidence_graph import _izgradj_kontekst

    predmet = {"naziv": "Test predmet"}
    dokumenti = [{"naziv_fajla": "prazan.pdf", "tip_dokaza": "ostalo"}]
    out = _izgradj_kontekst(predmet, dokumenti, [], [])
    assert "prazan.pdf" in out  # ne puca kad nema teksta


# ─── 2. evidence.py reklasifikuj fix ──────────────────────────────────────────

def _fake_request():
    from starlette.requests import Request as StarletteRequest
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": "/api/evidence/predmeti/predmet-1/reklasifikuj/dok-1",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def test_reklasifikuj_selektuje_tekst_sadrzaj_kolonu():
    """Regresioni test za bug: select nije ni tražio 'tekst_sadrzaj', pa je
    reklasifikacija uvek slala prazan string. Proverava da endpoint sada
    (a) selektuje tekst_sadrzaj i (b) prosleđuje ga klasifikuj_i_sacuvaj-u,
    ne prazan string."""
    import asyncio
    from routers import evidence as ev

    supa = MagicMock()
    predmeti_table = MagicMock()
    predmeti_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "predmet-1"}]
    )
    dokumenti_table = MagicMock()
    dokumenti_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"naziv_fajla": "ugovor.pdf", "pinecone_namespace": "ns1", "tekst_sadrzaj": "Stvaran tekst dokumenta."}]
    )

    def _table(name):
        return predmeti_table if name == "predmeti" else dokumenti_table
    supa.table = MagicMock(side_effect=_table)

    select_calls = []
    orig_select = dokumenti_table.select
    def _tracking_select(cols):
        select_calls.append(cols)
        return orig_select(cols)
    dokumenti_table.select = MagicMock(side_effect=_tracking_select)

    captured = {}
    def _fake_klasifikuj(predmet_id, dok_id, naziv, tekst, user_id):
        captured["tekst"] = tekst

    request = _fake_request()
    user = {"user_id": "user-1", "email": "test@test.com"}

    async def _run():
        with patch("routers.evidence.get_supa", return_value=supa), \
             patch("routers.evidence.klasifikuj_i_sacuvaj", side_effect=_fake_klasifikuj), \
             patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=99):
            result = await ev.reklasifikuj(request, "predmet-1", "dok-1", user=user)
            # reklasifikuj pokreće klasifikaciju preko asyncio.create_task
            # (fire-and-forget) -- mora dobiti šansu da se izvrši PRE nego
            # što se event loop zatvori, inače se task nikad ne pokrene.
            await asyncio.sleep(0.05)
            return result

    asyncio.run(_run())

    assert any("tekst_sadrzaj" in c for c in select_calls), "select mora tražiti tekst_sadrzaj kolonu"
    assert captured.get("tekst") == "Stvaran tekst dokumenta.", "mora proslediti stvaran tekst, ne prazan string"


# ─── 3. intake_extract.py hybrid regex + key-sections fix ────────────────────

def test_extract_court_prepoznaje_sud_sa_gradom():
    from shared.intake_extract import extract_court
    value, confidence = extract_court("Predmet se vodi pred Osnovnim sudom. Osnovni sud u Beogradu doneo je presudu.")
    assert value == "Osnovni sud u Beogradu"
    assert confidence == 0.9


def test_extract_court_prepoznaje_nacionalni_sud_bez_grada():
    from shared.intake_extract import extract_court
    value, confidence = extract_court("Vrhovni kasacioni sud odbio je reviziju kao neosnovanu.")
    assert value == "Vrhovni kasacioni sud"
    assert confidence == 0.9


def test_extract_court_ne_hvata_lazne_pozitive():
    """IGNORECASE je namerno ograničen na tip suda + 'sud u' -- naziv grada
    i dalje mora početi velikim slovom, inače bi svaka reč posle 'sud u'
    (npr. običan glagol) mogla biti pogrešno pročitana kao grad."""
    from shared.intake_extract import extract_court
    value, confidence = extract_court("Osnovni sud u ovom trenutku nije dostupan.")
    assert value is None
    assert confidence == 0.0


def test_kljucne_sekcije_kratak_tekst_ostaje_neizmenjen():
    from shared.intake_extract import _kljucne_sekcije
    kratak = "Kratak dokument od par rečenica."
    assert _kljucne_sekcije(kratak) == kratak


def test_kljucne_sekcije_dugacak_tekst_zadrzava_pocetak_i_kraj():
    from shared.intake_extract import _kljucne_sekcije
    # Marker mora biti unutar poslednjih _LLM_TAIL_CHARS (3000) znakova da bi
    # test stvarno proveravao "tail" deo, ne "isečeni srednji deo".
    dug_tekst = ("ZAGLAVLJE SUDA " * 500) + (" ODLUKA " * 400) + "POTPIS SUDIJE: Marko Marković"
    out = _kljucne_sekcije(dug_tekst)
    assert "ZAGLAVLJE SUDA" in out
    assert "POTPIS SUDIJE: Marko Marković" in out
    assert len(out) < len(dug_tekst)


def test_extract_all_entities_preferira_regex_court_nad_llm():
    """Kad regex nadje sud, mora biti korišćen umesto LLM-ovog 'court' polja
    (deterministički pouzdaniji), sa extraction_method='regex'."""
    import asyncio
    from shared import intake_extract as ie

    tekst = "Osnovni sud u Novom Sadu, predmet P 12/2025."

    async def _fake_free_text(text):
        return {
            "judge": (None, 0.0),
            "plaintiff": (None, 0.0),
            "defendant": (None, 0.0),
            "court": ("nešto sasvim drugo od LLM-a", 0.4),
            "law_cited": (None, 0.0),
        }

    with patch.object(ie, "extract_free_text_entities", side_effect=_fake_free_text):
        entities = asyncio.run(ie.extract_all_entities(tekst))

    court_entity = next(e for e in entities if e["entity_type"] == "court")
    assert court_entity["value"] == "Osnovni sud u Novom Sadu"
    assert court_entity["extraction_method"] == "regex"


def test_extract_all_entities_koristi_llm_court_kad_regex_ne_nadje():
    import asyncio
    from shared import intake_extract as ie

    tekst = "Dokument ne pominje sud eksplicitno u prepoznatljivom formatu."

    async def _fake_free_text(text):
        return {
            "judge": (None, 0.0),
            "plaintiff": (None, 0.0),
            "defendant": (None, 0.0),
            "court": ("Neki sud iz LLM konteksta", 0.55),
            "law_cited": (None, 0.0),
        }

    with patch.object(ie, "extract_free_text_entities", side_effect=_fake_free_text):
        entities = asyncio.run(ie.extract_all_entities(tekst))

    court_entity = next(e for e in entities if e["entity_type"] == "court")
    assert court_entity["value"] == "Neki sud iz LLM konteksta"
    assert court_entity["extraction_method"] == "llm"


def test_extract_free_text_entities_salje_kljucne_sekcije_ne_samo_pocetak():
    """Regresioni test za glavni bug: LLM poziv ranije nije video kraj
    dokumenta uopšte (samo [:4000]). Sada mora dobiti i deo sa kraja."""
    import asyncio
    import json
    from shared import intake_extract as ie

    # Marker mora biti unutar poslednjih _LLM_TAIL_CHARS (3000) znakova.
    dug_tekst = ("UVOD " * 2000) + (" ZAKLJUCAK " * 1500) + "POTPIS SUDIJE: Ana Anić"
    assert len(dug_tekst) > 20000  # dovoljno dug da bi stari [:4000] propustio potpis

    captured_user_content = {}

    class _FakeResp:
        class choices:
            pass

    def _make_response(content):
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    async def _fake_create(model, messages, temperature, max_tokens, response_format):
        captured_user_content["value"] = messages[1]["content"]
        return _make_response(json.dumps({
            "judge": {"value": "Ana Anić", "confidence": 0.9},
            "plaintiff": {"value": None, "confidence": 0.0},
            "defendant": {"value": None, "confidence": 0.0},
            "court": {"value": None, "confidence": 0.0},
            "law_cited": {"value": None, "confidence": 0.0},
        }))

    fake_client = MagicMock()
    fake_client.chat.completions.create = _fake_create

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = asyncio.run(ie.extract_free_text_entities(dug_tekst))

    assert "POTPIS SUDIJE: Ana Anić" in captured_user_content["value"], (
        "LLM mora videti kraj dokumenta (potpisni blok), ne samo prvih 4000 znakova"
    )
    assert result["judge"] == ("Ana Anić", 0.9)


# ─── 4. dokument.py log message fix ───────────────────────────────────────────

def test_dokument_py_log_poruka_ne_tvrdi_lazan_multi_pass():
    """Regresioni test za zavaravajuću log poruku: kod za dokumente >12000
    znakova radi TAČNO JEDAN GPT-4o poziv (main.py::ask_analiza_v2), ne
    multi-pass. Poruka na tom mestu više ne sme tvrditi suprotno."""
    import inspect
    import routers.dokument as dokument_mod

    source = inspect.getsource(dokument_mod.dokument_analiza)
    assert "primena multi-pass pristupa" not in source, (
        "log poruka i dalje tvrdi 'multi-pass' iako kod radi samo jedan GPT-4o poziv"
    )
    assert "nije stvaran multi-pass" in source, (
        "ispravljena poruka mora eksplicitno reći da nije stvaran multi-pass"
    )
