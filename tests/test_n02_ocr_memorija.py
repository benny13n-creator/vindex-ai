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


# ── Ostala dva mesta rasterizacije (nalaz nezavisnog recenzenta: pokriven je bio samo extract_pdf) ──────────
# Ugovor: posle SVAKE rasterizovane strane keš se prazni pre sledeće — inače dugačak mešovit/skeniran PDF
# ponovo gomila dekodirane strane u procesu. Meri se redosled događaja (render → pražnjenje), ne RSS: brzo i
# bez Tesseract-a. Mehanizam pražnjenja (store_shrink stvarno oslobađa memoriju) dokazuje test iznad.

def _mali_sken(putanja, strana=3):
    from PIL import ImageDraw
    doc = fitz.open()
    for i in range(strana):
        img = Image.new("RGB", (400, 560), "white")
        ImageDraw.Draw(img).rectangle((40 + i * 10, 40, 360, 200), fill="black")
        b = io.BytesIO()
        img.save(b, "PNG")
        s = doc.new_page(width=595, height=842)
        s.insert_image(s.rect, stream=b.getvalue())
    doc.save(str(putanja))
    doc.close()


def _dnevnik_rasterizacije(monkeypatch):
    dogadjaji = []
    pravi = fitz.Page.get_pixmap

    def _render(self, *a, **k):
        dogadjaji.append("render")
        return pravi(self, *a, **k)

    monkeypatch.setattr(fitz.Page, "get_pixmap", _render)
    monkeypatch.setattr(extractor, "_oslobodi_kes_rasterizacije", lambda: dogadjaji.append("prazni"))
    return dogadjaji


def _svaki_render_ispraznjen_pre_sledeceg(dogadjaji, broj):
    assert dogadjaji.count("render") == broj, dogadjaji
    for i, d in enumerate(dogadjaji):
        if d == "render":
            sledeci = next((x for x in dogadjaji[i + 1:] if x in ("render", "prazni")), None)
            assert sledeci == "prazni", f"strana rasterizovana bez pražnjenja keša pre sledeće: {dogadjaji}"


def test_ocr_strana_mesovitog_pdf_prazni_kes_posle_svake_strane(tmp_path, monkeypatch):
    p = tmp_path / "mesovit.pdf"
    _mali_sken(p, 3)
    dogadjaji = _dnevnik_rasterizacije(monkeypatch)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "eng")

    def _lazni_ocr(img, jezik):
        dogadjaji.append("ocr")
        return "tekst strane", 0.9

    monkeypatch.setattr(extractor, "_ocr_image", _lazni_ocr)
    dopuna, confs = extractor._ocr_strane_pdf(p, [0, 1, 2])
    assert sorted(dopuna) == [0, 1, 2] and confs == [0.9] * 3
    _svaki_render_ispraznjen_pre_sledeceg(dogadjaji, 3)
    # Pražnjenje ide PRE OCR-a: dekodirana strana ne sme da čeka u kešu dok traje spori Tesseract.
    assert dogadjaji == ["render", "prazni", "ocr"] * 3, dogadjaji


def test_merenje_necitljivih_strana_prazni_kes_posle_svake_strane(tmp_path, monkeypatch):
    p = tmp_path / "sken.pdf"
    _mali_sken(p, 3)
    dogadjaji = _dnevnik_rasterizacije(monkeypatch)
    necitljive = extractor.necitljive_strane_pdf(p, ["", "", ""])
    assert necitljive == [1, 2, 3]
    _svaki_render_ispraznjen_pre_sledeceg(dogadjaji, 3)
