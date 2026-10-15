# -*- coding: utf-8 -*-
"""NS3-A (OCR, P0): memorija rasterizacije PDF strane procenjuje se PRE prve rasterizacije, bez dekodiranja slika.
Dokaz klase: običan CMYK JPEG od 30-35 MP preko cele A4 strane MuPDF dekodira u punoj veličini (+250 MiB) → OOM pod
512 MiB. Testovi koriste JPEG koji ima samo zaglavlje: provera ga čita, ali ga ništa ne sme dekodirati ni rasterizovati
(rasterizacija i OCR su zamenjeni greškom)."""
import io
import os
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from PIL import Image

from uploaded_doc import extractor as X
from uploaded_doc.extractor import DocumentSafetyLimitExceeded
from test_ns2b_ocr_jpeg_koeficijenti import SOI, _sof, _sos

fitz = pytest.importorskip("fitz")
m = fitz.mupdf
A4 = fitz.Rect(0, 0, 595, 842)
CMYK = [(1, 1)] * 4
RGB = [(1, 1)] * 3


def _zag(w, h, comps, progresivni=False) -> bytes:
    return SOI + _sof(0xC2 if progresivni else 0xC0, w, h, comps) + _sos(len(comps)) + bytes(16) + b"\xff\xd9"


def _sacuvaj(d, tmp_path, ime="d.pdf"):
    p = tmp_path / ime
    d.save(str(p)); d.close()
    return p


def _pdf_slika(tmp_path, data, rect=A4, ime="d.pdf"):
    d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(rect, stream=data)
    return _sacuvaj(d, tmp_path, ime)


def _pdf_sadrzaj(tmp_path, sadrzaj: bytes, resursi: str = "<<>>", ime="d.pdf"):
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    d.xref_set_key(pg.xref, "Resources", resursi)
    c = d.get_new_xref(); d.update_object(c, "<<>>"); d.update_stream(c, sadrzaj)
    d.xref_set_key(pg.xref, "Contents", f"{c} 0 R")
    return _sacuvaj(d, tmp_path, ime)


@pytest.fixture
def bez_rasterizacije(monkeypatch):
    monkeypatch.setattr(X, "_rasterizuj_stranu", lambda *a: (_ for _ in ()).throw(AssertionError("rasterizacija pre odbijanja")))
    monkeypatch.setattr(X, "_ocr_image", lambda *a: (_ for _ in ()).throw(AssertionError("OCR pre odbijanja")))
    monkeypatch.setattr(fitz.Page, "get_pixmap", lambda *a, **k: (_ for _ in ()).throw(AssertionError("get_pixmap pre odbijanja")))


@pytest.fixture
def lazan_ocr(monkeypatch):
    """Strana ide u OCR, ali se ne rasterizuje stvarno (JPEG ima samo zaglavlje)."""
    pozivi = []
    monkeypatch.setattr(X, "_rasterizuj_stranu", lambda strana: (pozivi.append(1), Image.new("L", (10, 10)))[1])
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: ("Pročitan tekst skenirane strane " * 5, 0.92))
    return pozivi


def _odbijen(p, poruka=None):
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert ei.value.poruka == (poruka or X.PORUKA_PREVELIK_JPEG_PDF)
    return ei.value.reason


# ── Model (MuPDF image.c / draw-device.c), ručno izračunato ──────────────────────────────────────────────────────

def test_cmyk_30_mp_a4_rucno_izracunata_procena(tmp_path):
    p = _pdf_slika(tmp_path, _zag(4606, 6513, CMYK))
    doc = fitz.open(str(p))
    bajtova, opis = X._procena_rastera_strane(doc, 0, 300)
    strana = 2480 * 3509                            # ceil(595 * 300/72) x ceil(842 * 300/72)
    slika = 4606 * 6513                             # 4606 >> 1 = 2303 < 2481 + 2 → bez umanjenja
    ocekivano = strana * 3 + slika * 4 + slika * 3 + 2480 * 3509 * 3     # raster + CMYK (keš) + RGB + umanjena
    # insert_image čuva odnos stranica: slika je na rasteru 2480 x ~3506 (ne 3509) → umanjena slika je za par redova manja
    assert ocekivano - 2480 * 3 * 4 <= bajtova <= ocekivano and opis.endswith("4606x6513x4")
    assert bajtova > X.MAX_PDF_RASTER_BAJTOVA


@pytest.mark.parametrize("w,h,l2", [(4960, 7016, 0), (4962, 7020, 0), (4970, 7030, 1), (5317, 7523, 1), (9940, 14060, 2)])
def test_faktor_umanjenja_kao_mupdf(w, h, l2):
    s = {"w": w, "h": h, "tip": "FZ_IMAGE_JPEG", "dekodirana": False, "n": 3, "alfa": False, "indeksirana": False,
         "baza_n": 0, "matte": False, "okvir": None, "dx": 595 * 300 / 72, "dy": 842 * 300 / 72, "stek": 0}
    kes, _ = X._mupdf_bajtovi_slike(s, 2480 * 3509)
    f = 1 << l2
    assert kes == -(-w // f) * -(-h // f) * 3


def test_jpx_i_indeksirana_bez_umanjenja():
    s = {"w": 4000, "h": 4000, "tip": "FZ_IMAGE_JPX", "dekodirana": False, "n": 3, "alfa": False, "indeksirana": False,
         "baza_n": 0, "matte": False, "okvir": None, "dx": 500.0, "dy": 500.0, "stek": 0}
    kes, prolazno = X._mupdf_bajtovi_slike(s, 2480 * 3509)
    assert kes == 4000 * 4000 * 3 and prolazno >= 4000 * 4000 * 3 * 4      # OpenJPEG: int32 po uzorku
    s.update(tip="FZ_IMAGE_FLATE", indeksirana=True, n=1, baza_n=3)
    kes, prolazno = X._mupdf_bajtovi_slike(s, 2480 * 3509)
    assert kes == 4000 * 4000 * 3 and prolazno >= 4000 * 4000


# ── Klase iz zadatka: odbijeno pre rasterizacije / prihvaćeno ─────────────────────────────────────────────────────

@pytest.mark.parametrize("w,h", [(4606, 6513), (4944, 6997)])          # obični CMYK 30 i 34,6 MP
def test_obican_cmyk_30_35_mp_odbijen_pre_rasterizacije(tmp_path, bez_rasterizacije, w, h):
    assert "strana 1" in _odbijen(_pdf_slika(tmp_path, _zag(w, h, CMYK)))


def test_cmyk_40_mp_i_sken_300_dpi_prihvaceni(tmp_path, lazan_ocr):
    for ime, data in (("c40.pdf", _zag(5317, 7523, CMYK)), ("sken.pdf", _zag(2480, 3508, RGB)),
                      ("siv600.pdf", _zag(4960, 7016, [(1, 1)]))):
        tekst, skeniran, ocr, strane, conf = X.extract(_pdf_slika(tmp_path, data, ime=ime))
        assert ocr is True and skeniran is False and len(strane) == 1 and conf == pytest.approx(0.92)


def test_progresivni_40_mp_odbijen(tmp_path, bez_rasterizacije):
    _odbijen(_pdf_slika(tmp_path, _zag(5317, 7523, RGB, progresivni=True)))


@pytest.mark.parametrize("filtri,kodiraj", [
    ("[/ASCIIHexDecode /DCTDecode]", lambda b: b.hex().encode() + b">"),
    ("[/FlateDecode /DCTDecode]", zlib.compress),
])
def test_lanci_filtera_ne_zaobilaze_proveru(tmp_path, bez_rasterizacije, filtri, kodiraj):
    data = _zag(4606, 6513, CMYK)
    d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(A4, stream=data)
    x = pg.get_images(full=True)[0][0]
    d.update_stream(x, kodiraj(data), compress=False); d.xref_set_key(x, "Filter", filtri)
    _odbijen(_sacuvaj(d, tmp_path))


def test_flate_slika_bez_jpeg_a_se_racuna(tmp_path, bez_rasterizacije):
    """Pregled Task B: Flate (ne-DCT) CMYK 7000x5700 → +434 MiB. Veličina je u rečniku slike, bez dekodiranja."""
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    x = d.get_new_xref()
    d.update_object(x, "<</Type/XObject/Subtype/Image/Width 7000/Height 5700/BitsPerComponent 8/ColorSpace/DeviceCMYK/Filter/FlateDecode>>")
    d.update_stream(x, zlib.compress(bytes(7000 * 5700 * 4), 9), compress=False)
    d.xref_set_key(pg.xref, "Resources", f"<</XObject<</I0 {x} 0 R>>>>")
    c = d.get_new_xref(); d.update_object(c, "<<>>"); d.update_stream(c, b"q 595 0 0 842 0 0 cm /I0 Do Q")
    d.xref_set_key(pg.xref, "Contents", f"{c} 0 R")
    assert "7000x5700x4" in _odbijen(_sacuvaj(d, tmp_path))


def test_vise_slika_na_strani_se_sabira(tmp_path, bez_rasterizacije, lazan_ocr):
    jedna = _pdf_slika(tmp_path, _zag(3759, 5320, CMYK), ime="jedna.pdf")     # CMYK 20 MP: 183 MiB
    doc = fitz.open(str(jedna))
    b1, _ = X._procena_rastera_strane(doc, 0, 300)
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    pg.insert_image(A4, stream=_zag(3759, 5320, CMYK)); pg.insert_image(A4, stream=_zag(3759, 5321, CMYK))
    dve = _sacuvaj(d, tmp_path, "dve.pdf")
    b2, _ = X._procena_rastera_strane(fitz.open(str(dve)), 0, 300)
    assert b2 >= b1 + 3759 * 5320 * 4                # dekodirane slike strane ostaju u kešu MuPDF-a do kraja strane


def test_meka_maska_i_sablonska_maska_ulaze_u_procenu(tmp_path):
    bez = _pdf_slika(tmp_path, _zag(3000, 4000, RGB), ime="bez.pdf")
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    pg.insert_image(A4, stream=_zag(3000, 4000, RGB), mask=_zag(3000, 4000, [(1, 1)]))
    sa = _sacuvaj(d, tmp_path, "sa.pdf")
    b_bez, _ = X._procena_rastera_strane(fitz.open(str(bez)), 0, 300)
    b_sa, _ = X._procena_rastera_strane(fitz.open(str(sa)), 0, 300)
    assert b_sa >= b_bez + 3000 * 4000 + 2480 * 3509 * X._SLOJ_MASKE_BAJTOVA_PO_PIKSELU
    st = _pdf_sadrzaj(tmp_path, b"0 g q 595 0 0 842 0 0 cm /S0 Do Q", ime="st.pdf")
    doc = fitz.open(str(st)); x = doc.get_new_xref()
    doc.update_object(x, "<</Type/XObject/Subtype/Image/Width 9920/Height 14032/BitsPerComponent 1/ImageMask true/Filter/FlateDecode>>")
    doc.update_stream(x, zlib.compress(bytes(9920 // 8 * 14032)), compress=False)
    doc.xref_set_key(doc[0].xref, "Resources", f"<</XObject<</S0 {x} 0 R>>>>")
    b, opis = X._procena_rastera_strane(doc, 0, 300)
    assert "9920x14032x1" in opis and b >= 2480 * 3509 * 3 + 4960 * 7016   # šablon se umanjuje u toku (1/2)


def test_maska_drzi_sloj_i_dok_traje_dekodiranje(tmp_path):
    """Progresivni JPEG pod mekom maskom: koeficijenti i sloj maske postoje istovremeno."""
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    pg.insert_image(A4, stream=_zag(3000, 4000, RGB, progresivni=True), mask=_zag(3000, 4000, [(1, 1)]))
    b, _ = X._procena_rastera_strane(fitz.open(str(_sacuvaj(d, tmp_path))), 0, 300)
    koef = X._jpeg_bajtova_koeficijenata(3000, 4000, RGB)
    assert b >= 2480 * 3509 * 3 + 3000 * 4000 * 4 + koef + 2480 * 3509 * X._SLOJ_MASKE_BAJTOVA_PO_PIKSELU


def test_velika_strana_bez_slika_pil_faza():
    """Strana A2 (raster smanjen na MAX_OCR_PIXELS): vrh je posle MuPDF-a — PNG + PIL RGB + siva (8 B po pikselu)."""
    d = fitz.open(); d.new_page(width=1191, height=1684)
    dpi = X._dpi_strane(1191, 1684)
    pw, ph = X._strana_px(d[0], dpi)
    assert X._procena_rastera_strane(d, 0, dpi)[0] == pw * ph * 8


def test_slika_u_ugnezdenoj_formi_i_anotaciji(tmp_path, bez_rasterizacije):
    d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(A4, stream=_zag(4606, 6513, CMYK))
    xi = pg.get_images(full=True)[0][0]
    unutra = d.get_new_xref()
    d.update_object(unutra, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Resources<</XObject<</Im0 {xi} 0 R>>>>>>")
    d.update_stream(unutra, b"q 595 0 0 842 0 0 cm /Im0 Do Q")
    spolja = d.get_new_xref()
    d.update_object(spolja, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Resources<</XObject<</F1 {unutra} 0 R>>>>>>")
    d.update_stream(spolja, b"/F1 Do")
    d.xref_set_key(pg.xref, "Resources", f"<</XObject<</F0 {spolja} 0 R>>>>")
    for cx in pg.get_contents():
        d.update_stream(cx, b"/F0 Do")
    _odbijen(_sacuvaj(d, tmp_path, "forma.pdf"))
    d = fitz.open(); pg = d.new_page(width=595, height=842); pg.insert_image(A4, stream=_zag(4606, 6513, CMYK))
    xi = pg.get_images(full=True)[0][0]
    for cx in pg.get_contents():
        d.update_stream(cx, b"")
    a = pg.add_rect_annot(fitz.Rect(10, 10, 100, 100))
    f = d.get_new_xref()
    d.update_object(f, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Resources<</XObject<</Im0 {xi} 0 R>>>>>>")
    d.update_stream(f, b"q 595 0 0 842 0 0 cm /Im0 Do Q")
    d.xref_set_key(a.xref, "AP", f"<</N {f} 0 R>>"); d.xref_set_key(a.xref, "Rect", "[0 0 595 842]")
    p = tmp_path / "anot.pdf"; d.save(str(p), garbage=0); d.close()
    _odbijen(p)


# ── Umetnute slike (BI … ID … EI): MuPDF ih dekodira već pri čitanju sadržaja ──────────────────────────────────────

_ZAG30 = _zag(4606, 6513, CMYK)


@pytest.mark.parametrize("sadrzaj", [
    b"q 595 0 0 842 0 0 cm BI /W 4606 /H 6513 /CS /CMYK /BPC 8 /F /DCT ID\n" + _ZAG30 + b"\nEI Q",
    b"q 595 0 0 842 0 0 cm 0BI/W 4606/H 6513/CS/CMYK/BPC 8/F/D#43T ID " + _ZAG30 + b" EI Q",       # broj uz BI, #xx u imenu
    b"BI % komentar ID\n /W 4606 /DP << /K (x ID y) >> /H 6513 /CS /DeviceCMYK /BPC 8 /F [/DCTDecode] ID\n" + _ZAG30 + b"\nEI",
    b"BI /W 4606 /H 6513 /CS /CMYK /BPC 8 /F /DCT >>\n" + _ZAG30 + b"\nEI",                        # rečnik završen sa >>
    b"BI\x00/Width 4606 /Height 6513 /ColorSpace /DeviceCMYK /BitsPerComponent 8 ID\n" + bytes(64) + b"\nEI",   # sirova
])
def test_velika_umetnuta_slika_odbijena_pre_interpretera(tmp_path, bez_rasterizacije, monkeypatch, sadrzaj):
    monkeypatch.setattr(m, "fz_run_page", lambda *a: (_ for _ in ()).throw(AssertionError("interpreter pre odbijanja")))
    assert "umetnuta" in _odbijen(_pdf_sadrzaj(tmp_path, sadrzaj))


def test_umetnuta_slika_preko_granice_dela_toka(tmp_path, bez_rasterizacije, monkeypatch):
    monkeypatch.setattr(X, "_DELIC_TOKA", 64)       # BI, rečnik i zaglavlje razbijeni na više delova
    sadrzaj = b" " * 61 + b"BI /W 4606 /H 6513 /CS /CMYK /BPC 8 /F /DCT ID\n" + _ZAG30 + b"\nEI"
    assert "umetnuta" in _odbijen(_pdf_sadrzaj(tmp_path, sadrzaj))


def test_bi_u_tekstu_i_mala_umetnuta_slika_ne_smetaju(tmp_path, lazan_ocr):
    logo = io.BytesIO(); Image.new("RGB", (40, 20), "red").save(logo, "JPEG")
    sadrzaj = (b"BT /F1 12 Tf 50 700 Td (Predmet BI 2026 ID x) Tj ET "
               b"q 100 0 0 50 400 700 cm BI /W 40 /H 20 /CS /RGB /BPC 8 /F /DCT ID\n" + logo.getvalue() + b"\nEI Q")
    p = _pdf_sadrzaj(tmp_path, sadrzaj, "<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>")
    assert X.extract(p)[2] is True and lazan_ocr == [1]


def test_umetnuta_slika_sa_indirektnom_dimenzijom_nije_proverljiva(tmp_path, bez_rasterizacije):
    reason = _odbijen(_pdf_sadrzaj(tmp_path, b"BI /W 5 0 R /H 10 /CS /G ID\n" + bytes(64) + b"\nEI"), X.PORUKA_PDF_NEPROVERLJIV)
    assert "bezbednost nije utvr" in reason


def test_umetnuti_jpeg_iza_nepoznatog_filtera_nije_proverljiv(tmp_path, bez_rasterizacije):
    _odbijen(_pdf_sadrzaj(tmp_path, b"BI /W 10 /H 10 /CS /RGB /F [/LZW /DCT] ID\n" + bytes(64) + b"\nEI"),
             X.PORUKA_PDF_NEPROVERLJIV)


# ── Provera ne dekodira i ne puni keš; ponovljena obrada; PDF koji MuPDF ne čita kao PDF ─────────────────────────

def test_provera_ne_dekodira_i_ne_puni_kes(tmp_path):
    """Dekodirana slika ostaje u kešu MuPDF-a (RSS procesa); provera ga ne puni, a crtanje (kontrola) ga puni."""
    psutil = pytest.importorskip("psutil")
    b = io.BytesIO(); Image.new("RGB", (3000, 4000), "white").save(b, "JPEG", quality=90)
    p = _pdf_slika(tmp_path, b.getvalue())
    doc = fitz.open(str(p))
    fitz.TOOLS.store_shrink(100)
    proc = psutil.Process()
    r0 = proc.memory_info().rss
    X._odbij_pdf_preveliki_raster(doc, [0])
    r1 = proc.memory_info().rss
    pix = doc[0].get_pixmap(dpi=300)
    del pix
    r2 = proc.memory_info().rss
    assert r1 - r0 < 8 << 20 and r2 - r1 > 30 << 20     # slika 3000x4000x3 = 34 MiB u kešu tek posle crtanja
    fitz.TOOLS.store_shrink(100)


def test_ponovna_obrada_posle_odbijanja(tmp_path, lazan_ocr):
    los = _pdf_slika(tmp_path, _zag(4606, 6513, CMYK), ime="los.pdf")
    dobar = _pdf_slika(tmp_path, _zag(2480, 3508, RGB), ime="dobar.pdf")
    for _ in range(3):
        with pytest.raises(DocumentSafetyLimitExceeded):
            X.extract(los)
        assert X.extract(dobar)[2] is True
    assert not X._DOKUMENT_LOCK.locked() and not X._RASTER_OCR_LOCK.locked()
    assert lazan_ocr == [1, 1, 1]


def test_tiff_sa_dodatim_pdf_om_odbijen(tmp_path, bez_rasterizacije):
    """Pregled Task B: MuPDF bira format po sadržaju i otvara ga kao TIFF (i uz filetype="pdf") — PDF putanja ga ne prima."""
    # (mali TIFF MuPDF ipak otvara kao PDF — tada važi provera PDF strane; ovde je TIFF dovoljno velik da „pobedi“)
    b = io.BytesIO(); Image.new("CMYK", (2000, 1500)).save(b, "TIFF", compression="tiff_lzw")
    d = fitz.open(); d.new_page(); pdf = d.tobytes(); d.close()
    p = tmp_path / "poli.pdf"; p.write_bytes(b.getvalue() + pdf)
    _odbijen(p, X.PORUKA_NIJE_PDF)


def test_digitalan_pdf_se_ne_proverava_ni_ne_odbija(tmp_path, bez_rasterizacije, monkeypatch):
    monkeypatch.setattr(X, "_odbij_pdf_preveliki_raster", lambda *a, **k: (_ for _ in ()).throw(AssertionError("provera")))
    d = fitz.open()
    for k in range(3):
        pg = d.new_page(width=595, height=842)
        pg.insert_text((50, 72), f"Strana {k + 1}: digitalni podnesak sa dovoljno teksta za tekstualni sloj.", fontsize=11)
        if k == 1:
            pg.insert_image(fitz.Rect(300, 400, 500, 700), stream=_zag(4606, 6513, CMYK))
    tekst, skeniran, ocr, strane, conf = X.extract(_sacuvaj(d, tmp_path))
    assert (skeniran, ocr, len(strane), conf) == (False, False, 3, None) and "Strana 2" in tekst


def test_necitljive_strane_proverava_na_svom_dpi(tmp_path, monkeypatch):
    """Uzorak potpunosti (50 dpi) se proverava na 50 dpi: CMYK 30 MP se tada umanjuje 1/8 i nije opasan."""
    p = _pdf_slika(tmp_path, _zag(4606, 6513, CMYK))
    dpi = []
    pravo = X._procena_rastera_strane
    monkeypatch.setattr(X, "_procena_rastera_strane", lambda doc, i, d: (dpi.append(d), pravo(doc, i, d))[1])
    monkeypatch.setattr(fitz.Page, "get_pixmap", lambda self, *a, **k: type("P", (), {"samples": bytes([255]) * 100})())
    assert X.necitljive_strane_pdf(p, [""]) == [] and dpi == [50]
