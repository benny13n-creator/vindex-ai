"""Javni AI disclosure: produkcione tvrdnje moraju pokriti Smart Intake bez posebnog klika."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_disclosure_nije_iskljucivo_klik_i_jedan_model():
    tekst = (ROOT / "static/ai-disclosure.html").read_text(encoding="utf-8")
    assert "AI obrada se aktivira isključivo eksplicitnom akcijom" not in tekst
    assert "GPT-4o</strong> putem zvaničnog OpenAI API servisa za sve funkcije" not in tekst
    assert "Smart Intake može pokrenuti automatsko" in tekst
    assert "GPT-4o-mini" in tekst


def test_privacy_ne_obecava_iskljucivo_rucnu_obradu():
    tekst = (ROOT / "privacy.html").read_text(encoding="utf-8")
    assert "samo radi funkcija koje korisnik pokrene" not in tekst
    assert "isključivo na tehničku obradu potrebnu za izvršenje funkcija koje korisnik eksplicitno pokrene" not in tekst
    assert "automatsku obradu nakon otpremanja" in tekst


def test_bezbednost_source_i_generated_isti_opis():
    izvor = (ROOT / "site/_izvor/bezbednost.html").read_text(encoding="utf-8")
    generisano = (ROOT / "site/bezbednost.html").read_text(encoding="utf-8")
    nova = "Obrada može početi i nakon otpremanja dokumenta."
    assert nova in izvor and nova in generisano
    assert "Samo ono što traži funkcija koju pokrenete." not in izvor
    assert "Samo ono što traži funkcija koju pokrenete." not in generisano
