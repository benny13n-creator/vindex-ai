# -*- coding: utf-8 -*-
"""Public AI and pre-upload disclosures must match implemented upload paths."""

import re
import os
from html import unescape
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _tekst(html: str) -> str:
    bez_nevidljivog = re.sub(r"<style.*?</style>|<script.*?</script>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", bez_nevidljivog)))


@pytest.fixture(scope="module")
def javne_stranice():
    # Application imports construct SDK clients; use a deliberately invalid
    # test-only value so this static-route test can never call a paid provider.
    previous_key = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "test-placeholder-not-a-provider-key"
    try:
        from api import app
    finally:
        if previous_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_key

    client = TestClient(app)
    routes = ("/ai-disclosure", "/bezbednost", "/privacy", "/security", "/bezbednosni-list")
    pages = {}
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        pages[route] = _tekst(response.text)
    return pages


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_ai_disclosure_opisuje_automatsku_obradu_i_uklanja_stare_apsolute(javne_stranice):
    text = javne_stranice["/ai-disclosure"]
    for phrase in (
        "GPT-4o-mini",
        "Dodavanje dokumenta u postojeći predmet",
        "Playbook",
        "prvih 3.000 znakova",
        "7.000 znakova",
        "originalni binarni fajl",
        "text-embedding-3-large",
        "Azure OpenAI",
        "VINDEX_COHERE_RERANK",
        "aktivnu produkcionu konfiguraciju",
    ):
        assert phrase.lower() in text.lower(), phrase

    for obsolete in (
        "za sve funkcije veštačke inteligencije",
        "nijedna automatska ai obrada se ne vrši",
        "ai obrada se aktivira isključivo eksplicitnom akcijom korisnika",
        "ne koristi alternativne ai provajdere",
        "max 30 dana, isključivo radi detekcije zloupotrebe",
        "samo ono što traži funkcija koju pokrenete",
    ):
        assert obsolete not in text.lower(), obsolete


def test_povezane_javne_stranice_ne_tvrde_da_su_svi_pozivi_openai_gpt4o(javne_stranice):
    obsolete = ("OpenAI API (GPT-4o)", "koristi se isključivo eksterni OpenAI model")
    for route, text in javne_stranice.items():
        for phrase in obsolete:
            assert phrase.lower() not in text.lower(), f"{route}: {phrase}"

    assert "otpremanje dokumenta može samo pokrenuti obradu" in javne_stranice["/bezbednost"].lower()
    assert "model spoljnog dobavljača (openai)" not in javne_stranice["/bezbednost"].lower()
    assert "GPT-4o-mini" in javne_stranice["/security"]
    assert "aktivna produkciona putanja, konkretni model i region nisu potvrđeni" in javne_stranice["/privacy"].lower()
    assert "AI upiti (OpenAI) Max 30 dana" not in javne_stranice["/privacy"]
    assert "OpenAI zadržava API podatke max 30 dana" not in javne_stranice["/security"]
    assert "OpenAI API pozivi 30 dana (OpenAI politika)" not in javne_stranice["/security"]
    assert "ne sam tekst" not in javne_stranice["/security"].lower()
    assert "nije potvrđeno" in javne_stranice["/security"].lower()
    assert "eu-west-1" in javne_stranice["/privacy"].lower()
    assert "region aktivnog pinecone indeksa nije potvrđen" in javne_stranice["/privacy"].lower()
    assert javne_stranice["/privacy"].lower().count("vindex ai forensics") == 1
    assert "produkciona render usluga i njen region nisu potvrđeni" in javne_stranice["/privacy"].lower()
    assert "180 dana" in javne_stranice["/ai-disclosure"].lower()
    whitepaper = javne_stranice["/security"].lower()
    for obsolete in (
        "poverljivo — samo za b2b klijente i revizore",
        "svaki api endpoint zahteva validan bearer jwt",
        "pristup je zaštićen dvofaktorskom autentifikacijom (2fa) na svim provajder portalima",
        "health check svakih 60 sekundi",
        "rollback u prethodnu verziju: <15 minuta",
        "supabase / aws kms (eu-central-1)",
        "planirano za q2 2027",
    ):
        assert obsolete not in whitepaper, obsolete
    assert "postoje i javne rute" in whitepaper
    assert "produkcioni postupak, rok i evidencija nisu potvrđeni" in whitepaper
    metodologija = javne_stranice["/bezbednosni-list"].lower()
    assert "produkciona konfiguracija" in metodologija
    assert "nije nezavisna bezbednosna revizija" in metodologija
    root = Path(__file__).resolve().parents[1]
    bezbednosni_list_html = (root / "static" / "bezbednosni-list.html").read_text(encoding="utf-8")
    assert "@media(max-width:480px)" in bezbednosni_list_html
    assert ".print-btn{position:static" in bezbednosni_list_html


def test_sve_upload_ulazne_tacke_imaju_obavestenje_pre_izbora_fajla():
    root = Path(__file__).resolve().parents[1]
    html = (root / "index.html").read_text(encoding="utf-8")
    for element_id in (
        "pred-upload-input", "intake-file-input", "si-file-input",
        "doc-upload-input", "playbook-file-input", "law-pdf-input",
    ):
        offset = html.find(f'id="{element_id}"')
        assert offset >= 0, element_id
        nearby = html[max(0, offset - 1800):offset]
        assert "ai-upload-disclosure" in nearby, f"{element_id}: notice must precede file selection"
        assert 'href="/ai-disclosure"' in nearby, f"{element_id}: missing AI Disclosure link"
        assert 'href="/privacy"' in nearby, f"{element_id}: missing Privacy Policy link"

    v2 = (root / "frontend-v2-ng" / "index.html").read_text(encoding="utf-8")
    for element_id in ("nd-fajlovi", "pd-fajlovi"):
        offset = v2.find(f'id="{element_id}"')
        assert offset >= 0, element_id
        nearby = v2[max(0, offset - 1800):offset]
        assert "Otpremanje pokreće automatsku obradu" in nearby
        assert 'href="/ai-disclosure"' in nearby
        assert 'href="/privacy"' in nearby


def test_smart_intake_notice_does_not_hardcode_provider_or_model():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend-v2-ng" / "index.html").read_text(encoding="utf-8")
    notices = [
        html[max(0, html.find(f'id="{element_id}"') - 1800):html.find(f'id="{element_id}"')]
        for element_id in ("nd-fajlovi", "pd-fajlovi")
    ]
    assert all("spoljnom AI servisu" in notice for notice in notices)
    assert all("GPT-4o-mini" not in notice for notice in notices)


def test_app_privacy_panels_do_not_repeat_unverified_absolute_claims():
    root = Path(__file__).resolve().parents[1]
    text = _tekst((root / "index.html").read_text(encoding="utf-8")).lower()
    for obsolete in (
        "azure eu",
        "zero-persistence protokol",
        "podaci ostaju u eu",
        "14 dana bez kreditne kartice",
        "nijedan dokument se ne čuva posle analize",
        "openai gpt-4o putem zvaničnog openai api servisa za sve ai funkcije",
        "scc: ✓",
        "frankfurt, nemačka (aws eu-central-1)",
        "backup: dnevni automatski backup sa 30-dnevnim rokom čuvanja",
        "niko iz tima vindex ai nema pristup sadržaju vaših predmeta",
    ):
        assert obsolete not in text, obsolete

    assert "otpremanje može automatski pokrenuti" in text
    assert "aktivna produkciona putanja" in text
    assert "AI obrada dokumenata putem OpenAI API-ja" not in text


def test_sitemap_documents_have_unique_canonicals_and_app_is_not_indexed():
    root = Path(__file__).resolve().parents[1]
    expected = {
        "privacy.html": "https://vindex.rs/privacy",
        "terms.html": "https://vindex.rs/terms",
        "static/ai-disclosure.html": "https://vindex.rs/ai-disclosure",
        "static/security.html": "https://vindex.rs/security",
        "static/bezbednosni-list.html": "https://vindex.rs/bezbednosni-list",
        "static/dpa.html": "https://vindex.rs/dpa",
    }
    for relative, canonical in expected.items():
        html = (root / relative).read_text(encoding="utf-8")
        assert f'<link rel="canonical" href="{canonical}">' in html, relative
        assert '<meta name="description" content=' in html, relative
        assert '<meta property="og:url" content=' in html, relative

    for relative in ("index.html", "frontend-v2-ng/index.html"):
        html = (root / relative).read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex, nofollow">' in html, relative


@pytest.mark.anyio
async def test_smart_intake_classifier_sends_gpt4o_mini_only_after_heuristic_miss():
    from shared import intake_classify as classifier

    text = "Obaveštenje bez naslova pravnog dokumenta. " + ("x" * 3200)
    assert classifier.classify_heuristic(text) is None
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='{"document_type":"other","confidence":0.4}'))]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await classifier.classify(text)

    assert result["method"] == "llm"
    call = client.chat.completions.create.await_args.kwargs
    assert call["model"] == "gpt-4o-mini"
    assert call["messages"][1]["content"] == text[:3000]


@pytest.mark.anyio
async def test_smart_intake_free_text_extraction_sends_model_excerpt():
    from shared import intake_extract as extractor

    text = "A" * 4000 + "SREDNJI DEO DOKUMENTA" + "B" * 3000
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='{}'))]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with patch("openai.AsyncOpenAI", return_value=client):
        await extractor.extract_free_text_entities(text)

    call = client.chat.completions.create.await_args.kwargs
    excerpt = call["messages"][1]["content"]
    assert call["model"] == "gpt-4o-mini"
    assert excerpt == extractor._kljucne_sekcije(text)
    assert excerpt.startswith(text[:4000])
    assert excerpt.endswith(text[-3000:])
    assert "SREDNJI DEO DOKUMENTA" not in excerpt
