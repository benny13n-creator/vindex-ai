# -*- coding: utf-8 -*-
"""NS005 Gate B — OCR dokaz sa STVARNIM Tesseract-om (uploaded_doc/extractor.py, bez izmene proizvoda).

Matrica:
  A  digitalni PDF sa tekstualnim slojem  → tačan tekst, OCR se NE poziva
  B  skenirani PDF bez tekstualnog sloja, >100 smislenih srpskih latiničnih znakova
                                          → OCR pozvan, ocr_used=True, robustan podskup reči
  C  slika (PNG i JPEG)                   → OCR, koristan tekst
  D  nečitljiv ulaz (prazna strana, kratak sken ispod praga, oštećen fajl)
                                          → nikad lažan uspeh
  E  jezik: bez srpskog paketa → izričito `eng` (zapisuje se), tekst stvaran ali bez dijakritika;
     bez Tesseract binarnog fajla → prazan rezultat, ocr_used=False (nikad izmišljen tekst)

Fixture-i se prave u testu: krupan skalabilan font (Pillow `load_default(size=…)`) i tekst
duži od 100 znakova — stari nalaz (test tekst ~20 znakova, sitan bitmap font) je bio KVAR
FIXTURE-A, a prag od 100 znakova u proizvodu ostaje netaknut.

Okruženje: bez Tesseract-a test se PRESKAČE; sa `VINDEX_REQUIRE_OCR=1` (CI) nedostatak je PAD.
`VINDEX_OCR_REPORT=<putanja>` → JSON izveštaj (bez sadržaja dokumenata osim izmerenih brojeva/reči).
`VINDEX_EXPECT_SRP=1` (produkciona slika) → mora biti dostupan srp_latn.
"""
import io
import json
import os
import unicodedata

import pytest

_TRAZI = os.getenv("VINDEX_REQUIRE_OCR") == "1"


def _okruzenje():
    try:
        import fitz  # noqa: F401
        import pypdf  # noqa: F401
        import pytesseract
        from PIL import Image  # noqa: F401
        return str(pytesseract.get_tesseract_version())
    except Exception as e:   # binarni fajl ili paket nedostaje
        return "NEMA: " + type(e).__name__


_VERZIJA = _okruzenje()
if _VERZIJA.startswith("NEMA"):
    if _TRAZI:
        raise RuntimeError(f"VINDEX_REQUIRE_OCR=1, ali OCR okruženje nije potpuno ({_VERZIJA})")
    pytest.skip(f"OCR okruženje nije dostupno ({_VERZIJA}) — Gate B dokaz preskočen", allow_module_level=True)

from uploaded_doc import extractor  # noqa: E402

REDOVI = [
    "OSNOVNI SUD U BEOGRADU",
    "Tužilac: Marko Petrović iz Beograda",
    "Tuženi: Jovan Jovanović iz Novog Sada",
    "Predmet: naknada štete u iznosu od 250.000 dinara",
    "Ročište je zakazano za 15. novembar 2026. godine.",
]
RECI = ["osnovni", "sud", "beogradu", "tuzilac", "marko", "petrovic", "beograda", "tuzeni", "jovan",
        "jovanovic", "novog", "sada", "predmet", "naknada", "stete", "iznosu", "dinara", "rociste",
        "zakazano", "novembar", "godine"]
IZVESTAJ = {"tesseract": _VERZIJA}


def _norm(t):
    t = (t or "").replace("đ", "dj").replace("Đ", "Dj")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return t.lower()


def _pogodak(tekst):
    n = _norm(tekst)
    nadjene = [r for r in RECI if r in n]
    return len(nadjene) / len(RECI), nadjene


def _strana_sa_tekstom(redovi, velicina=20):
    """PDF strana sa PRAVIM tekstualnim slojem. Font: ugrađeni URW Helvetica iz PyMuPDF-a (ima
    č ć š ž đ — Pillow-ov ugrađeni font ih NEMA i crta prazne kvadrate koje OCR čita kao „X“,
    što je bio kvar prvog fixture-a). Isti font postoji i u produkcionoj slici (PyMuPDF je zavisnost)."""
    import fitz
    doc = fitz.open()
    strana = doc.new_page(width=595, height=842)
    tw = fitz.TextWriter(strana.rect)
    font = fitz.Font("helv")
    for i, red in enumerate(redovi):
        tw.append((50, 80 + i * 34), red, font=font, fontsize=velicina)
    tw.write_text(strana)
    return doc


def _slika(redovi, dpi=200):
    """Skenirana strana = rasterizovan PDF bez ikakvog tekstualnog sloja u rezultatu."""
    from PIL import Image
    doc = _strana_sa_tekstom(redovi)
    pix = doc[0].get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    doc.close()
    return img


def _sken_pdf(putanja, img):
    import fitz
    b = io.BytesIO()
    img.save(b, format="PNG")
    doc = fitz.open()
    strana = doc.new_page(width=595, height=842)
    strana.insert_image(fitz.Rect(20, 20, 575, 314), stream=b.getvalue())
    doc.save(str(putanja))
    doc.close()


@pytest.fixture(scope="module", autouse=True)
def _izvestaj():
    yield
    putanja = os.getenv("VINDEX_OCR_REPORT")
    if putanja:
        with open(putanja, "w", encoding="utf-8") as f:
            json.dump(IZVESTAJ, f, ensure_ascii=False, indent=1)


@pytest.fixture
def spijun(monkeypatch):
    pozivi = []
    pravi = extractor._ocr_image

    def _ocr(img, jezik):
        pozivi.append(jezik)
        return pravi(img, jezik)
    monkeypatch.setattr(extractor, "_ocr_image", _ocr)
    return pozivi


def test_jezik_okruzenja_je_zapisan():
    import pytesseract
    jezici = sorted(pytesseract.get_languages(config=""))
    izabran = extractor._detect_ocr_lang()
    IZVESTAJ["jezici"], IZVESTAJ["izabran_jezik"] = jezici, izabran
    assert "eng" in izabran
    if os.getenv("VINDEX_EXPECT_SRP") == "1":
        assert "srp_latn" in izabran, (jezici, izabran)


def test_A_digitalni_pdf_bez_ocr(tmp_path, spijun):
    p = tmp_path / "digitalni.pdf"
    doc = _strana_sa_tekstom(REDOVI)
    doc.save(str(p))
    doc.close()
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    udeo, _ = _pogodak(text)
    IZVESTAJ["A_digitalni_pdf"] = {"ocr_pozvan": len(spijun), "ocr_used": ocr_used, "znakova": len(text), "udeo_reci": round(udeo, 2)}
    assert spijun == [] and ocr_used is False and skeniran is False and conf is None
    assert "Marko Petrović" in text and "Ročište" in text and udeo == 1.0, text[:300]


def test_B_skenirani_pdf_ocr(tmp_path, spijun):
    p = tmp_path / "skeniran.pdf"
    _sken_pdf(p, _slika(REDOVI))
    import pypdf
    assert "".join((s.extract_text() or "") for s in pypdf.PdfReader(str(p)).pages).strip() == ""   # nema tekstualnog sloja
    assert len("\n".join(REDOVI)) > 100
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    udeo, nadjene = _pogodak(text)
    IZVESTAJ["B_skenirani_pdf"] = {"ocr_pozvan": len(spijun), "jezik": spijun[:1], "ocr_used": ocr_used, "znakova": len(text.strip()),
                                   "udeo_reci": round(udeo, 2), "nadjene": nadjene, "conf": round(conf, 2) if conf is not None else None}
    assert len(spijun) >= 1 and ocr_used is True and skeniran is False
    assert len(text.strip()) > 100 and udeo >= 0.8, (udeo, text[:300])
    assert conf is not None and 0.0 < conf <= 1.0
    dijakritici = sorted({c for c in text if c in "čćšžđČĆŠŽĐ"})
    IZVESTAJ["B_skenirani_pdf"]["dijakritici"] = dijakritici
    if "srp_latn" in (spijun[0] if spijun else ""):
        # Sa srpskim latiničnim paketom OCR mora da vrati i č/ć/š/ž, ne samo osnovna slova.
        assert {"ć", "š", "ž"} <= set(dijakritici), dijakritici


@pytest.mark.parametrize("format_", ["PNG", "JPEG"])
def test_C_slika_ocr(tmp_path, spijun, format_):
    p = tmp_path / ("sken." + ("png" if format_ == "PNG" else "jpg"))
    _slika(REDOVI).save(p, format=format_, quality=90) if format_ == "JPEG" else _slika(REDOVI).save(p, format=format_)
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    udeo, _ = _pogodak(text)
    IZVESTAJ[f"C_slika_{format_}"] = {"ocr_pozvan": len(spijun), "ocr_used": ocr_used, "znakova": len(text), "udeo_reci": round(udeo, 2)}
    assert len(spijun) == 1 and ocr_used is True and skeniran is False and udeo >= 0.8, (udeo, text[:300])


def test_D_necitljivo_nikad_lazan_uspeh(tmp_path):
    from PIL import Image
    rez = {}
    prazna = tmp_path / "prazna.png"
    Image.new("RGB", (1200, 800), "white").save(prazna)
    rez["prazna_slika"] = extractor.extract(prazna)
    kratak = tmp_path / "kratak.pdf"
    _sken_pdf(kratak, _slika(["Strana 1"]))
    rez["kratak_sken_ispod_praga"] = extractor.extract(kratak)
    ostecen = tmp_path / "ostecen.png"
    ostecen.write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(512))
    rez["ostecena_slika"] = extractor.extract(ostecen)
    IZVESTAJ["D_necitljivo"] = {k: {"znakova": len(v[0]), "skeniran": v[1], "ocr_used": v[2]} for k, v in rez.items()}
    for ime, (text, skeniran, ocr_used, strane, conf) in rez.items():
        assert text == "" and skeniran is True and ocr_used is False and conf is None, ime
    losi = tmp_path / "ostecen.pdf"
    losi.write_bytes(b"%PDF-1.4\n" + os.urandom(256))
    try:
        r = extractor.extract(losi)
    except Exception as e:     # izuzetak je pošten ishod; uspeh nije
        IZVESTAJ["D_necitljivo"]["ostecen_pdf"] = "izuzetak: " + type(e).__name__
    else:
        IZVESTAJ["D_necitljivo"]["ostecen_pdf"] = {"znakova": len(r[0]), "ocr_used": r[2]}
        assert r[0] == "" and r[2] is False


def test_E_bez_srpskog_paketa_izricito_eng(tmp_path, spijun, monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    p = tmp_path / "sken.png"
    _slika(REDOVI).save(p)
    text, skeniran, ocr_used, strane, conf = extractor.extract(p)
    udeo, _ = _pogodak(text)
    IZVESTAJ["E_bez_srpskog"] = {"jezik": spijun, "ocr_used": ocr_used, "udeo_reci_bez_dijakritika": round(udeo, 2),
                                 "dijakritici_u_tekstu": any(c in text for c in "čćšžđČĆŠŽĐ")}
    assert spijun == ["eng"]
    assert ocr_used is True and udeo >= 0.7, (udeo, text[:300])


def test_E_bez_tesseract_programa_nema_izmisljenog_teksta(tmp_path, monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", str(tmp_path / "nema-tesseract"))
    slika = tmp_path / "sken.png"
    _slika(REDOVI).save(slika)
    pdf = tmp_path / "sken.pdf"
    _sken_pdf(pdf, _slika(REDOVI))
    r1, r2 = extractor.extract(slika), extractor.extract(pdf)
    IZVESTAJ["E_bez_tesseract"] = {"slika": {"znakova": len(r1[0]), "ocr_used": r1[2]}, "pdf": {"znakova": len(r2[0]), "ocr_used": r2[2]}}
    for text, skeniran, ocr_used, strane, conf in (r1, r2):
        assert text == "" and skeniran is True and ocr_used is False and conf is None
