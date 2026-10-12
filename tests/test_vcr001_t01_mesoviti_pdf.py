# -*- coding: utf-8 -*-
"""VCR001 T01 — mešovit PDF (digitalna strana + skenirana strana bez tekstualnog sloja).

Ranije: prosek znakova po strani prelazio prag → OCR se nije pokretao → tekst skenirane strane se tiho gubio.
Lokalno (bez Tesseract-a): `_ocr_image` je zamenjen; PDF, renderovanje strana (PyMuPDF) i odluka su stvarni.
Pravi OCR za isti slučaj: tests/test_ns005_b_ocr.py::test_F_mesoviti_pdf (izvršava se u produkcionoj slici u CI-ju).
"""
import fitz
import pytest

from uploaded_doc import extractor

DIGITALNO = ["PODNESAK — TUŽBA RADI NAKNADE ŠTETE", "Tužilac Marko Petrović iz Beograda podnosi tužbu protiv",
             "tuženog Jovana Jovanovića iz Novog Sada zbog naknade materijalne štete."]


def _pdf(putanja, strane):
    """strane: lista 'tekst' (digitalni sloj) ili 'slika' (strana sa samo rasterskom slikom, bez teksta) ili 'prazna'."""
    doc = fitz.open()
    for vrsta in strane:
        s = doc.new_page(width=595, height=842)
        if vrsta == "tekst":
            tw = fitz.TextWriter(s.rect)
            for i, red in enumerate(DIGITALNO):
                tw.append((50, 80 + i * 30), red, font=fitz.Font("helv"), fontsize=14)
            tw.write_text(s)
        elif vrsta == "slika":
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 200), False)
            pix.clear_with(200)
            s.insert_image(fitz.Rect(40, 40, 440, 240), pixmap=pix)
    doc.save(str(putanja))
    doc.close()


@pytest.fixture
def ocr(monkeypatch):
    pozivi = []

    def _ocr(img, jezik):
        pozivi.append(img.size)
        return ("PRILOG: Rešenje Osnovnog suda u Beogradu, poslovni broj P 4321/2026", 0.91)
    monkeypatch.setattr(extractor, "_ocr_image", _ocr)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    return pozivi


def test_mesovit_pdf_skenirana_strana_dobija_tekst(tmp_path, ocr):
    p = tmp_path / "mesovit.pdf"
    _pdf(p, ["tekst", "slika"])
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    assert len(ocr) == 1                                   # OCR samo za stranu bez teksta
    assert "Marko Petrović" in strane[0] and "P 4321/2026" in strane[1]
    assert "P 4321/2026" in text and "naknade" in text
    assert ocr_used is True and skeniran is False and conf == pytest.approx(0.91)


def test_potpuno_digitalan_pdf_ne_poziva_ocr(tmp_path, ocr):
    p = tmp_path / "digitalan.pdf"
    _pdf(p, ["tekst", "tekst"])
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    assert ocr == [] and ocr_used is False and conf is None and len(strane) == 2


def test_neuspeh_ocr_ostavlja_stranu_praznom_bez_izmisljanja(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "_ocr_image", lambda img, j: ("", None))
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "eng")
    p = tmp_path / "mesovit_necitljiv.pdf"
    _pdf(p, ["tekst", "slika"])
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    assert strane[1] == "" and ocr_used is False and conf is None
    assert "Marko Petrović" in text


def test_okruzenje_bez_ocr_ne_ruši_digitalni_deo(tmp_path, monkeypatch):
    def _pada(*a, **k):
        raise RuntimeError("tesseract nije instaliran")
    monkeypatch.setattr(extractor, "_detect_ocr_lang", _pada)
    p = tmp_path / "mesovit_bez_ocr.pdf"
    _pdf(p, ["tekst", "slika"])
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    assert "Marko Petrović" in text and strane[1] == "" and ocr_used is False
