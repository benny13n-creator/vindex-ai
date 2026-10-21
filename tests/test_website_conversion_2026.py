# -*- coding: utf-8 -*-
"""Website conversion + prijava problema: ciljane release regresije."""
from pathlib import Path
import re

KOREN = Path(__file__).resolve().parents[1]


def tekst(putanja):
    return (KOREN / putanja).read_text(encoding="utf-8")


def test_nav_i_rani_pristup_umesto_javnog_roadmapa():
    for naziv in ("index", "kako-radi", "funkcionalnosti", "za-advokate", "bezbednost", "beta"):
        html = tekst(f"site/{naziv}.html")
        assert 'href="/razvoj"' not in html
        assert 'href="/beta"' in html
    assert "Prijavi se za rani pristup" in tekst("site/index.html")
    assert "Prijavi se za rani pristup" in tekst("site/beta.html")
    assert 'class="plan"' not in tekst("site/razvoj.html")


def test_siri_segmenti_su_oznaceni_kao_potencijalni():
    html = tekst("site/index.html")
    for segment in ("Notari", "Osiguravajuća", "Banke", "Računovodstvo", "compliance"):
        assert segment in html
    assert "potencijalne oblasti primene" in html
    assert "regulatornim zahtevima" in html


def test_bezbednost_ne_iznosi_neosnovanu_superiornost():
    html = tekst("site/bezbednost.html")
    for dobavljac in ("Supabase", "Render", "Pinecone", "OpenAI", "ChatGPT"):
        assert dobavljac in html
    assert "ne dokaz da je Vindex bezbedniji" in html
    assert "Izvoz" in html


def test_ikonica_povratne_informacije_u_v2():
    html = tekst("frontend-v2-ng/index.html")
    assert 'id="vx-prijava-otvori"' in html
    assert 'id="vx-prijava-tekst"' in html
    assert '/api/support/poruka' in html
    assert 'window.VxApi.send' in html
    assert 'window.VxSesija.token()' in html
    assert "ishodNepoznat" in html


def test_support_nije_lazni_uspeh_bez_smtp(monkeypatch):
    from routers import support
    monkeypatch.setattr(support, "_SMTP_HOST", "")
    assert support._send_support_email("korisnik@example.com", "tehnicko", "Dovoljno dug opis problema") is False
    kod = tekst("routers/support.py")
    assert 'if not poslato:' in kod
    assert 'status_code=503' in kod


def test_podaci_pravopis_i_pravila_poverljivosti():
    # Srpski standardni nominativ množine od 'podatak' je 'podaci', ne 'podatci'.
    assert "Podaci" in tekst("site/_izvor/index.html")
    assert "Nemojte unositi poverljive podatke klijenata" in tekst("frontend-v2-ng/index.html")
