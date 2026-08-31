# -*- coding: utf-8 -*-
"""B3 — OCR: DOKUMENT KOJI NIJE PROČITAN NE SME BITI PRIJAVLJEN KAO PROČITAN.

ŠTA OVAJ FAJL DOKAZUJE, A ŠTA NE
=================================
**NE dokazuje da OCR radi.** Za to je potreban `tesseract` binarni fajl +
`pytesseract` + `pdf2image` + `poppler`. `Dockerfile` ih instalira (linije 5–8),
ali u lokalnom okruženju ih NEMA — mereno: `shutil.which("tesseract") is None`.
Produkcioni podaci to potvrđuju: `intake_documents` 2/2 reda `ocr_used=False`.
**OCR nikada nije dokazano izvršen.**

**DOKAZUJE ono što je važnije za poverenje:** kada OCR ne može da se izvrši,
sistem to KAŽE umesto da tiho vrati prazan tekst kao uspeh. Skeniran dokument
bez čitljivog sloja daje `is_scanned=True`, `ocr_used=False`, `text=""` — nikad
`ocr_used=True` bez stvarnog OCR-a.

Test se sam prilagođava okruženju: gde alat postoji (Docker build), traži
STVARNI OCR; gde ga nema, traži pošteno priznanje.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uploaded_doc.extractor import extract_docx, extract_pdf  # noqa: E402


def _ocr_alat_dostupan() -> bool:
    """OCR traži i Python paket i SISTEMSKI binarni fajl. Nedostatak bilo kog
    znači da OCR ne može da se izvrši — `pip list` nije dokaz."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pdf2image  # noqa: F401
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return True


def _pdf_bez_tekstualnog_sloja() -> Path:
    """Jedna prazna strana = PDF bez ijednog čitljivog znaka.

    Namerno sintetički i bez ikakvog sadržaja — fixture ne sme nositi stvarne
    advokatske podatke."""
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    p = Path(tempfile.mkdtemp(prefix="b3_ocr_")) / "sken_bez_teksta.pdf"
    with open(p, "wb") as fh:
        w.write(fh)
    return p


def _docx_sa_tekstom(tekst: str) -> Path:
    import docx
    d = docx.Document()
    d.add_paragraph(tekst)
    p = Path(tempfile.mkdtemp(prefix="b3_txt_")) / "dokument_sa_tekstom.docx"
    d.save(str(p))
    return p


# ═══════════════════════════════════════════════════════════════════════════
# O3 — skeniran dokument + OCR nedostupan → NIKAD lažan uspeh
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(_ocr_alat_dostupan(),
                    reason="OCR alat postoji — ovaj slučaj meri ponašanje BEZ njega")
def test_o3_sken_bez_ocr_alata_ne_tvrdi_da_je_procitan():
    p = _pdf_bez_tekstualnog_sloja()
    try:
        text, is_scanned, ocr_used, pages, conf = extract_pdf(p)
    finally:
        p.unlink(missing_ok=True)

    assert ocr_used is False, "tvrdi da je OCR korišćen iako alat ne postoji"
    assert not (text or "").strip(), "vraća tekst koji nije mogao da pročita"
    assert is_scanned is True, "skeniran dokument nije označen kao skeniran"
    assert conf is None, "prijavljuje pouzdanost OCR-a koji se nije desio"


@pytest.mark.skipif(_ocr_alat_dostupan(),
                    reason="OCR alat postoji — ovaj slučaj meri ponašanje BEZ njega")
def test_o1_nedostatak_zavisnosti_je_vidljiv_a_ne_tih():
    """Nedostatak OCR-a se vidi u ISHODU (`is_scanned=True`, prazan tekst),
    a ne kao uredan prazan dokument."""
    p = _pdf_bez_tekstualnog_sloja()
    try:
        text, is_scanned, ocr_used, _, _ = extract_pdf(p)
    finally:
        p.unlink(missing_ok=True)
    assert (is_scanned, ocr_used, (text or "").strip()) == (True, False, ""), \
        "ishod ne razlikuje prazan dokument od nepročitanog dokumenta"


# ═══════════════════════════════════════════════════════════════════════════
# STVARNI OCR — izvršava se samo gde alat postoji (Docker build)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _ocr_alat_dostupan(),
                    reason="BLOCKED: nema tesseract/pytesseract/pdf2image/poppler")
def test_o2_stvarni_ocr_daje_tekst_i_tacan_status():
    """Jedini test koji zaista dokazuje da OCR RADI. Lokalno je BLOCKED."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1200, 300), "white")
    ImageDraw.Draw(img).text((40, 120), "ROK ZA ZALBU 15 DANA", fill="black")
    d = Path(tempfile.mkdtemp(prefix="b3_real_"))
    pdf = d / "sken.pdf"
    img.save(str(pdf), "PDF", resolution=200.0)
    try:
        text, is_scanned, ocr_used, pages, conf = extract_pdf(pdf)
    finally:
        pdf.unlink(missing_ok=True)

    assert ocr_used is True, "OCR alat postoji ali nije izvršen"
    assert (text or "").strip(), "OCR izvršen ali bez teksta"
    assert is_scanned is False, "uspešan OCR i dalje označava dokument kao nečitljiv"
    assert conf is not None and 0.0 <= conf <= 1.0, f"nevalidna pouzdanost: {conf}"


# ═══════════════════════════════════════════════════════════════════════════
# O4 — dokument sa tekstom ne sme nepotrebno tražiti OCR
# ═══════════════════════════════════════════════════════════════════════════

def test_o4_dokument_sa_tekstualnim_slojem_ne_koristi_ocr():
    p = _docx_sa_tekstom("Rok za žalbu je 15 dana od dostavljanja rešenja.")
    try:
        text, is_scanned, ocr_used, _, conf = extract_docx(p)
    finally:
        p.unlink(missing_ok=True)

    assert "Rok za žalbu" in text, "tekstualni sloj nije pročitan"
    assert ocr_used is False, "OCR pokrenut nad dokumentom koji ga ne treba"
    assert is_scanned is False
    assert conf is None


def test_ugovor_povratne_vrednosti_je_petorka():
    """Pozivaoci (`shared/intake_worker.py::_extract_text`) raspakuju tačno 5
    vrednosti; promena oblika bi tiho pokvarila ceo intake."""
    p = _docx_sa_tekstom("test")
    try:
        rez = extract_docx(p)
    finally:
        p.unlink(missing_ok=True)
    assert len(rez) == 5, f"ugovor ekstraktora promenjen: {len(rez)} vrednosti"
