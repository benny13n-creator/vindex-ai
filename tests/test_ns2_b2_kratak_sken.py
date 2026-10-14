# -*- coding: utf-8 -*-
"""NS2 B2 — kratak skeniran dokument više ne gubi ispravno pročitan tekst (uploaded_doc/extractor.py).

Pre ispravke: skeniran PDF/fotografija bez tekstualnog sloja čiji OCR da ≤ 100 znakova vraćao je ("", True, False,
None, None) — tekst i granice strana su brisani čak i kad je OCR siguran (dostavnica, rešenje od jednog reda).
Sada: kratak OCR tekst se prihvata SAMO uz pouzdanost ≥ PRAG_POUZDANOSTI_OCR i ≥ 2 „pune“ reči (≥ 3 slova/cifre) koje
čine ≥ polovinu reči. Šum, prazna strana i nesiguran kratak tekst ostaju nepročitani kao i ranije.
Deo A (mock Tesseract) radi svuda; deo B koristi pravi Tesseract i preskače se bez njega."""
import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc import extractor  # noqa: E402
from uploaded_doc.extractor import _kratak_ocr_procitan, extract_image, extract_pdf  # noqa: E402

from tests.test_extractor_ocr import _build_fitz_mock, _fake_image_to_data  # noqa: E402


def _reader(n_strana, tekst=""):
    strane = []
    for _ in range(n_strana):
        p = MagicMock(); p.extract_text.return_value = tekst; strane.append(p)
    r = MagicMock(); r.pages = strane
    return r


def _pdf(tmp_path, ocr_strane, conf):
    dummy = tmp_path / "sken.pdf"; dummy.write_bytes(b"%PDF-1.4")
    mock_fitz, mock_tess, mock_img, mock_pil = _build_fitz_mock(ocr_strane, conf)
    with patch("pypdf.PdfReader", return_value=_reader(len(ocr_strane))), \
         patch.dict(sys.modules, {"fitz": mock_fitz, "pytesseract": mock_tess, "PIL": mock_pil, "PIL.Image": mock_img}), \
         patch.object(extractor, "_rasterizuj_stranu", return_value=MagicMock()), \
         patch.object(extractor, "_detect_ocr_lang", return_value="srp+srp_latn+eng"), \
         patch.object(extractor, "_log_ocr_error"):
        return extract_pdf(dummy)


# ─── A: pravilo (mock Tesseract) ─────────────────────────────────────────────────────────────────────────────────────

def test_kratak_pouzdan_sken_zadrzava_tekst_i_stranu(tmp_path):
    text, skeniran, ocr_used, strane, conf = _pdf(tmp_path, ["Rešenje broj P 123/2026"], 90.0)
    assert (text, skeniran, ocr_used, strane) == ("Rešenje broj P 123/2026", False, True, ["Rešenje broj P 123/2026"])
    assert conf == pytest.approx(0.90)


def test_kratak_nesiguran_sken_ostaje_neprocitan(tmp_path):
    """Isti tekst, ali pouzdanost ispod PRAG_POUZDANOSTI_OCR (šum je izmeren na 0,58–0,77) → kao ranije."""
    assert _pdf(tmp_path, ["Rešenje broj P 123/2026"], 70.0) == ("", True, False, None, None)


def test_kratak_sum_visoke_pouzdanosti_ostaje_neprocitan(tmp_path):
    """Šum koji OCR čita kao sitne znakove (izmereno: najviše 1 reč sa ≥ 3 slova/cifre) se ne prihvata."""
    assert _pdf(tmp_path, ["~ ' .. | ii a- Ab ,, ="], 80.0) == ("", True, False, None, None)
    assert _pdf(tmp_path, ["abc"], 95.0) == ("", True, False, None, None)


def test_prazan_sken_ostaje_neprocitan(tmp_path):
    assert _pdf(tmp_path, [""], 95.0) == ("", True, False, None, None)


def test_vise_kratkih_strana_cuva_granice(tmp_path):
    text, skeniran, ocr_used, strane, _ = _pdf(tmp_path, ["Dostavnica 12.10.2026.", "", "Potpis primaoca Marko"], 91.0)
    assert skeniran is False and ocr_used is True
    assert strane == ["Dostavnica 12.10.2026.", "", "Potpis primaoca Marko"]       # prazna strana ostaje na svom mestu
    assert text == "Dostavnica 12.10.2026.\n\nPotpis primaoca Marko"


def test_dugacak_tekst_ne_zavisi_od_novog_pravila(tmp_path):
    """> 100 znakova: ponašanje nepromenjeno i pri niskoj pouzdanosti (to ostaje signal za pregled u workeru)."""
    dug = "Član 1 Ugovorne strane\nZaposlen pristaje na uslove rada u skladu sa Zakonom o radu i ugovorom o radu."
    assert len(dug) > 100
    text, skeniran, ocr_used, _, conf = _pdf(tmp_path, [dug], 60.0)
    assert (text, skeniran, ocr_used) == (dug, False, True) and conf == pytest.approx(0.60)


@pytest.mark.parametrize("tekst,conf,ocekivano", [
    ("Opomena 55/2026", 0.75, True),            # tačno na pragu pouzdanosti
    ("Opomena 55/2026", 0.7499, False),
    ("Overeno 3.9.2026.", 0.92, True),          # cifre se računaju kao pune reči
    ("Opomena", 0.95, False),                   # jedna puna reč nije dovoljna
    ("Opomena 55/2026 a b c", 0.95, False),     # pune reči nisu ≥ polovina
    ("Opomena 55/2026 a b", 0.95, True),        # tačno polovina
    ("Решење број П 456/2026", 0.9, True),      # ćirilica
    ("Rešenje broj", None, False),
])
def test_pravilo_kratkog_ocr(tekst, conf, ocekivano):
    assert _kratak_ocr_procitan(tekst, conf) is ocekivano


def test_slika_kratak_pouzdan_i_sum(tmp_path):
    from PIL import Image
    put = tmp_path / "foto.png"
    Image.new("RGB", (600, 400), "white").save(put)
    for ocr_tekst, conf, ocekivano in (("Dostavnica primljena 12.10.2026.", 90.0, ("Dostavnica primljena 12.10.2026.", False, True)),
                                       ("~ ' .. | ii", 80.0, ("", True, False))):
        tess = MagicMock(); tess.Output.DICT = "dict"
        tess.image_to_data.return_value = _fake_image_to_data(ocr_tekst, conf)
        tess.get_languages.return_value = ["eng", "srp", "srp_latn"]
        with patch.dict(sys.modules, {"pytesseract": tess}), patch.object(extractor, "_log_ocr_error"):
            text, skeniran, ocr_used, strane, c = extract_image(put)
        assert (text, skeniran, ocr_used) == ocekivano and strane is None


# ─── B: pravi Tesseract (sintetički sken) ────────────────────────────────────────────────────────────────────────────

def _tesseract():
    try:
        import fitz  # noqa: F401
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _tesseract() and os.getenv("VINDEX_REQUIRE_OCR") != "1", reason="Tesseract nije dostupan")
def test_pravi_ocr_kratak_sken_i_sum(tmp_path):
    import fitz
    from PIL import Image, ImageDraw, ImageFilter
    import random

    def sken(redovi, sum_=0):
        d = fitz.open(); p = d.new_page(width=595, height=842)
        tw = fitz.TextWriter(p.rect)
        for i, r in enumerate(redovi):
            tw.append((50, 60 + i * 19), r, font=fitz.Font("helv"), fontsize=11)
        tw.write_text(p)
        pix = p.get_pixmap(dpi=300); img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples); d.close()
        rnd = random.Random(4); dr = ImageDraw.Draw(img)
        for _ in range(sum_):
            x, y = rnd.randint(0, img.width - 40), rnd.randint(0, img.height - 40)
            dr.line([(x, y), (x + rnd.randint(-30, 30), y + rnd.randint(-30, 30))], fill=(20, 20, 20), width=rnd.randint(2, 5))
        return img.filter(ImageFilter.GaussianBlur(0.6))

    def pdf(ime, slike):
        put = tmp_path / ime; d = fitz.open()
        for img in slike:
            b = io.BytesIO(); img.save(b, "JPEG", quality=80)
            d.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=b.getvalue())
        d.save(str(put)); d.close()
        return put

    text, skeniran, ocr_used, strane, conf = extractor.extract(pdf("kratak.pdf", [sken(["Dostavnica: primljeno 12.10.2026. Potpis"]), sken([])]))
    assert skeniran is False and ocr_used is True and conf is not None and conf >= extractor.PRAG_POUZDANOSTI_OCR
    assert strane is not None and len(strane) == 2 and strane[1] == ""
    assert "12.10.2026" in text and 30 <= len(text) <= 60

    prazan = extractor.extract(pdf("prazan.pdf", [sken([])]))
    assert prazan == ("", True, False, None, None)
    sum_ = extractor.extract(pdf("sum.pdf", [sken([], sum_=150)]))
    assert sum_[1] is True or len(sum_[0]) > 100, sum_[:3]      # kratak šum nikad nije „pročitan“
