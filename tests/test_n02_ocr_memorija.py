# -*- coding: utf-8 -*-
"""N02 — OCR memorija: rasterizacija skeniranog PDF-a ne sme da ostavi dekodirane slike strana u MuPDF kešu.

Izmereno (N02): MuPDF čuva dekodiranu sliku svake rasterizovane strane u globalnom kešu procesa (do ~256 MiB) i ne
oslobađa je ni posle doc.close(); 10-stranični sken je držao ~256 MiB posle obrade. Test ne treba Tesseract:
OCR poziv je zamenjen, meri se samo ono što ostane u procesu POSLE extract_pdf (ne sadržaj dokumenta).
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

fitz = pytest.importorskip("fitz")
Image = pytest.importorskip("PIL.Image")

from uploaded_doc import extractor  # noqa: E402

STRANA = 12   # 12 x ~25 MiB dekodiranih RGB slika (A4, 300 dpi) — iznad podrazumevanog limita keša od 256 MiB


def _rss_mib():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        pass
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except (OSError, ValueError, AttributeError):
        pytest.skip("RSS procesa nije merljiv u ovom okruženju")


def _skeniran_pdf(putanja):
    """Sken bez tekstualnog sloja: svaka strana je ZASEBNA A4 slika (300 dpi), da je MuPDF ne bi delio između strana."""
    from PIL import ImageDraw
    doc = fitz.open()
    for i in range(STRANA):
        img = Image.new("RGB", (2480, 3508), "white")
        ImageDraw.Draw(img).rectangle((100 + i * 50, 200, 400 + i * 50, 260), fill="black")
        b = io.BytesIO()
        img.save(b, "JPEG", quality=60)
        strana = doc.new_page(width=595, height=842)
        strana.insert_image(strana.rect, stream=b.getvalue())
    doc.save(str(putanja))
    doc.close()


def test_rasterizacija_ne_ostavlja_dekodirane_strane_u_procesu(tmp_path, monkeypatch):
    p = tmp_path / "sken.pdf"
    _skeniran_pdf(p)
    obradjene = []

    def _lazni_ocr(img, jezik):
        obradjene.append(img.size)
        return "Tužilac Marko Petrović, Osnovni sud u Beogradu, ročište zakazano za novembar " * 2, 0.9

    monkeypatch.setattr(extractor, "_ocr_image", _lazni_ocr)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    extractor._oslobodi_kes_rasterizacije()
    pre = _rss_mib()
    text, skeniran, ocr_used, strane, _ = extractor.extract_pdf(p)
    zadrzano = _rss_mib() - pre

    # Svaka strana obrađena, na punih 300 dpi (ugovor kvaliteta nepromenjen).
    assert obradjene == [(2480, 3509)] * STRANA or obradjene == [(2480, 3508)] * STRANA, obradjene
    assert ocr_used is True and skeniran is False and len(strane) == STRANA
    # Bez pražnjenja keša proces ovde zadržava ~250 MiB; sa njim ~0. Prag je široko između.
    assert zadrzano < 100, f"posle extract_pdf proces zadržava {zadrzano:.0f} MiB dekodiranih strana"
