# -*- coding: utf-8 -*-
"""NS2b (OCR, P0): JPEG za koji bi libjpeg morao da drži koeficijente cele slike (progresivni ili sekvencijalni sa
više prolaza) odbija se PRE dekodiranja kad procena dekodiranja (MAX_JPEG_DEKODIRANJA_BAJTOVA) ili, u PDF-u, bafer prelazi prag — po sadržaju, ne po
ekstenziji; isto za JPEG ugrađen u PDF. Običan (jedan prolaz) JPEG se nikad ne odbija po ovom pravilu.
Odbijanje je DocumentSafetyLimitExceeded sa porukom za korisnika; intake worker ga završava bez ponovnih pokušaja."""
import io
import math
import os
import sys
import types
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from unittest.mock import AsyncMock, patch
from PIL import Image, ImageFile

from uploaded_doc import extractor as X
from uploaded_doc.extractor import DocumentSafetyLimitExceeded


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _jpeg(size=(320, 480), mode="RGB", **kw) -> bytes:
    img = Image.new(mode, size, "white" if mode != "CMYK" else (0, 0, 0, 0))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=90, **kw)
    return b.getvalue()


def _okvir(data: bytes):
    return X._jpeg_okvir(io.BytesIO(data))


def _seg(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def _sof(marker: int, w: int, h: int, comps) -> bytes:
    p = bytes([8]) + h.to_bytes(2, "big") + w.to_bytes(2, "big") + bytes([len(comps)])
    for i, (hs, vs) in enumerate(comps):
        p += bytes([i + 1, (hs << 4) | vs, 0])
    return _seg(marker, p)


def _sos(ns: int) -> bytes:
    p = bytes([ns]) + b"".join(bytes([i + 1, 0]) for i in range(ns)) + bytes([0, 63, 0])
    return _seg(0xDA, p)


SOI = b"\xff\xd8"


# ── Računica bafera (libjpeg jdcoefct.c) ────────────────────────────────────────────────────────────────────────

def test_racunica_rucno_izracunat_primer():
    # 17x17, 4:2:0: Y 4x4 blokova (zaokruženo na h=v=2), Cb/Cr po 2x2 → 24 bloka x 128 B
    assert X._jpeg_bajtova_koeficijenata(17, 17, [(2, 2), (1, 1), (1, 1)]) == 24 * 128
    # izmereni 40 MP fixture (5317x7523): 4:4:4 = 3 x 665x941 blokova
    assert X._jpeg_bajtova_koeficijenata(5317, 7523, [(1, 1)] * 3) == 3 * 665 * 941 * 128 == 240293760
    assert X._jpeg_bajtova_koeficijenata(5317, 7523, [(2, 2), (1, 1), (1, 1)]) == (666 * 942 + 2 * 333 * 471) * 128


@pytest.mark.parametrize("sub,faktori", [(0, [(1, 1)] * 3), (1, [(2, 1), (1, 1), (1, 1)]), (2, [(2, 2), (1, 1), (1, 1)])])
def test_uzorkovanje_iz_zaglavlja(sub, faktori):
    o = _okvir(_jpeg(progressive=True, subsampling=sub))
    assert o["komponente"] == faktori and o["progresivni"] and o["vise_prolaza"]
    assert o["koeficijenti"] == X._jpeg_bajtova_koeficijenata(320, 480, faktori)


def test_obican_jpeg_nema_bafer_cele_slike():
    for kw in ({}, {"subsampling": 0}, {"subsampling": 2}):
        o = _okvir(_jpeg(**kw))
        assert o["progresivni"] is False and o["vise_prolaza"] is False and o["koeficijenti"] == 0
    assert _okvir(_jpeg(mode="L"))["koeficijenti"] == 0
    assert _okvir(_jpeg(mode="CMYK"))["koeficijenti"] == 0


def test_siva_i_cmyk_progresivni():
    assert _okvir(_jpeg(mode="L", progressive=True))["koeficijenti"] == X._jpeg_bajtova_koeficijenata(320, 480, [(1, 1)])
    o = _okvir(_jpeg(mode="CMYK", progressive=True))
    assert len(o["komponente"]) == 4 and o["koeficijenti"] == X._jpeg_bajtova_koeficijenata(320, 480, [(1, 1)] * 4)


def test_sekvencijalni_sa_vise_prolaza_je_ceo_bafer():
    """Ne oslanja se na zastavicu progresivnosti: SOF0 čiji prvi SOS nosi 1 od 3 komponente → ceo bafer."""
    o = _okvir(SOI + _sof(0xC0, 4000, 6000, [(1, 1)] * 3) + _sos(1))
    assert o["progresivni"] is False and o["vise_prolaza"] is True
    assert o["koeficijenti"] == X._jpeg_bajtova_koeficijenata(4000, 6000, [(1, 1)] * 3)
    assert _okvir(SOI + _sof(0xC0, 4000, 6000, [(1, 1)] * 3) + _sos(3))["koeficijenti"] == 0
    # aritmetički progresivni (SOF10) i aritmetički sekvencijalni sa više prolaza (SOF9)
    assert _okvir(SOI + _sof(0xCA, 100, 100, [(1, 1)]) + _sos(1))["vise_prolaza"] is True
    assert _okvir(SOI + _sof(0xC9, 100, 100, [(1, 1)] * 3) + _sos(2))["vise_prolaza"] is True


def test_parser_preskace_segmente_smece_i_punjenje():
    app = _seg(0xE1, b"Exif\x00\x00" + b"\xff\xd9" * 50)      # FF D9 unutar APP podataka nije marker
    com = _seg(0xFE, b"x" * 1000)
    data = SOI + app + b"\x00\x12junk" + com + b"\xff\xff\xff" + _sof(0xC2, 5000, 7000, [(1, 1)] * 3) + _sos(3)
    o = _okvir(data)
    assert o is not None and o["sirina"] == 5000 and o["visina"] == 7000 and o["vise_prolaza"]


@pytest.mark.parametrize("prazan", [b"\xff\xfe\x00\x00", b"\xff\xfe\x00\x01", b"\xff\xef\x00\x00"])
def test_segment_duzine_0_ili_1_ne_zaobilazi_proveru(prazan):
    """Pregled A F1: libjpeg i Pillow segment dužine 0/1 čitaju kao prazan i dekodiraju dalje -- parser ne sme da odustane."""
    o = _okvir(SOI + prazan + _sof(0xC2, 7744, 5164, [(1, 1)] * 3) + _sos(3))
    assert o is not None and o["vise_prolaza"]
    assert o["koeficijenti"] == X._jpeg_bajtova_koeficijenata(7744, 5164, [(1, 1)] * 3)
    pravi = _jpeg(progressive=True)
    umetnut = pravi[:2] + prazan + pravi[2:]
    with Image.open(io.BytesIO(umetnut)) as im:
        im.load()                                       # Pillow zaista dekodira takav fajl
    assert _okvir(umetnut)["koeficijenti"] == _okvir(pravi)["koeficijenti"] > 0


@pytest.mark.parametrize("data", [
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,                                       # nije JPEG
    SOI + _sof(0xC2, 100, 100, [(1, 1)]),                                       # nema SOS
    SOI + _sos(1),                                                              # SOS pre SOF
    SOI + _sof(0xC2, 100, 100, [(1, 1)]) + _sof(0xC2, 100, 100, [(1, 1)]) + _sos(1),   # dupli SOF (libjpeg greška)
    SOI + _sof(0xC6, 100, 100, [(1, 1)]) + _sos(1),                             # hijerarhijski (libjpeg odbija)
    SOI + _sof(0xC2, 100, 0, [(1, 1)]) + _sos(1),                               # visina 0 / DNL (libjpeg odbija)
    SOI + _sof(0xC2, 100, 100, [(5, 1)]) + _sos(1),                             # nevažeće uzorkovanje
    SOI + b"\xff\xd9",                                                          # EOI pre slike
    SOI + b"\xff\xe1\x00",                                                      # skraćeno
])
def test_parser_ne_tvrdi_nista_kad_libjpeg_ionako_odbija(data):
    assert _okvir(data) is None


def test_zaglavlje_se_cita_bez_dekodiranja(monkeypatch, tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(_jpeg(progressive=True))
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    with open(p, "rb") as f:
        assert X._jpeg_okvir(f)["vise_prolaza"]


# ── extract_image: odbijanje pre dekodiranja, po sadržaju ───────────────────────────────────────────────────────

def _bez_dekodiranja(monkeypatch):
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje pre odbijanja")))
    monkeypatch.setattr(X, "_ocr_image", lambda *a: (_ for _ in ()).throw(AssertionError("OCR pre odbijanja")))


@pytest.mark.parametrize("ime", ["foto.jpg", "foto.jpeg", "foto.png"])
def test_slika_iznad_praga_odbijena_pre_dekodiranja_bez_obzira_na_ekstenziju(monkeypatch, tmp_path, ime):
    data = _jpeg(progressive=True, subsampling=0)
    p = tmp_path / ime
    p.write_bytes(data)
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", X._jpeg_procena_dekodiranja(_okvir(data)) - 1)
    _bez_dekodiranja(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert ei.value.poruka == X.PORUKA_PREVELIK_JPEG
    assert not any(c.isdigit() for c in ei.value.poruka) and "MiB" not in ei.value.poruka
    assert p.read_bytes() == data      # original netaknut


def test_obican_cmyk_iznad_praga_odbijen_pre_dekodiranja(monkeypatch, tmp_path):
    """Isti uslov pokriva i OBIČAN (jedan prolaz) JPEG kad je dekodiran raster prevelik (CMYK: 4 + 4 + 1 B po pikselu)."""
    data = _jpeg(mode="CMYK")
    p = tmp_path / "c.jpg"
    p.write_bytes(data)
    assert _okvir(data)["koeficijenti"] == 0
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", X._jpeg_procena_dekodiranja(_okvir(data)) - 1)
    _bez_dekodiranja(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded):
        X.extract(p)


def test_prag_granica_tacno_na_pragu_prihvaceno(monkeypatch, tmp_path):
    data = _jpeg(progressive=True, subsampling=0)
    p = tmp_path / "a.jpg"
    p.write_bytes(data)
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", X._jpeg_procena_dekodiranja(_okvir(data)))
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    pozvan = []
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: (pozvan.append(img.size) or ("tekst " * 40, 0.9)))
    tekst, skeniran, ocr, _, _ = X.extract(p)
    assert pozvan == [(320, 480)] and ocr is True and skeniran is False


def test_png_sa_ekstenzijom_jpg_nije_pogodjen(monkeypatch, tmp_path):
    p = tmp_path / "a.jpg"
    b = io.BytesIO(); Image.new("L", (100, 100), 255).save(b, "PNG"); p.write_bytes(b.getvalue())
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", 0)
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: ("tekst " * 40, 0.9))
    assert X.extract(p)[2] is True


# ── Procena dekodiranja: korak po korak kao extract_image → _u_granici_ocr ────────────────────────────────────────

def _ok(w, h, nf, koef=0):
    return {"sirina": w, "visina": h, "komponente": [(1, 1)] * nf, "koeficijenti": koef}


@pytest.mark.parametrize("nf,bpp_ukupno", [(1, 1 + 1), (3, 4 + 1), (4, 4 + 4 + 1)])
def test_procena_bez_draft_bajtova_po_pikselu_po_rezimu(nf, bpp_ukupno):
    """≤ MAX_OCR_PIXELS: dekodira se u izvornom režimu Pillow-a (L 1 B, RGB/CMYK 4 B), pa convert("L")."""
    assert X._jpeg_procena_dekodiranja(_ok(2000, 3000, nf)) == 2000 * 3000 * bpp_ukupno


def test_procena_draft_skala_i_pod():
    # 30 MP: umanjenje 1/2 bi palo ispod MIN_DEKODIRANIH_PIKSELA → dekodira se pun CMYK (9 B/piksel)
    w, h = 4606, 6513
    assert X._jpeg_procena_dekodiranja(_ok(w, h, 4)) == w * h * 9
    # 40 MP: 1/2 je dozvoljeno (≥ A4 na 300 dpi) → izlaz ceil(w/2) x ceil(h/2), 9 B/piksel
    w, h = 5317, 7523
    assert X._jpeg_procena_dekodiranja(_ok(w, h, 4)) == 2659 * 3762 * 9
    # RGB 30 MP: draft u L (1 B), siva kopija (1 B), umanjenje na MAX_OCR_PIXELS: među-slika + rezultat
    w, h = 4606, 6513
    k = math.sqrt(X.MAX_OCR_PIXELS / (w * h)); nw, nh = int(w * k), int(h * k)
    assert X._jpeg_procena_dekodiranja(_ok(w, h, 3)) == w * h + (w * h + nw * h + nw * nh)


def test_procena_prati_pod_dekodiranja(monkeypatch):
    w, h = 4606, 6513
    monkeypatch.setattr(X, "MIN_DEKODIRANIH_PIKSELA", 1_000_000)        # niži pod → dozvoljeno 1/4
    assert X._jpeg_procena_dekodiranja(_ok(w, h, 4)) == (-(-w // 4)) * (-(-h // 4)) * 9


def test_procena_koeficijenti_samo_dok_traje_dekodiranje():
    o = _ok(5317, 7523, 3, koef=240293760)
    assert X._jpeg_procena_dekodiranja(o) == 2659 * 3762 + 240293760


def test_podrazumevani_prag_izmerene_klase():
    """Izmerene klase (NS2b): odbijeni CMYK 20–34,8 MP i progresivni 4:4:4 40 MP; primljeni CMYK 40 MP, progresivni
    4:2:0 40 MP, progresivni 4:4:4 tik ispod starog praga (22,3 MP), telefon 12 MP, običan RGB do 40 MP."""
    T = X.MAX_JPEG_DEKODIRANJA_BAJTOVA
    P = X._jpeg_procena_dekodiranja
    koef = X._jpeg_bajtova_koeficijenata
    assert T == 150 << 20
    assert P(_ok(5317, 7523, 3, koef(5317, 7523, [(1, 1)] * 3))) > T
    assert P({"sirina": 5317, "visina": 7523, "komponente": [(2, 2), (1, 1), (1, 1)],
              "koeficijenti": koef(5317, 7523, [(2, 2), (1, 1), (1, 1)])}) <= T
    assert P(_ok(3974, 5622, 3, koef(3974, 5622, [(1, 1)] * 3))) <= T              # 22,3 MP progresivni 4:4:4
    for mp in (20, 25, 30, 34.6):
        h = int(math.sqrt(mp * 1e6 * 842 / 595)); w = int(mp * 1e6 / h)
        assert P(_ok(w, h, 4)) > T, mp
    assert P(_ok(5317, 7523, 4)) <= T
    assert P(_ok(3000, 4000, 3)) <= T


def test_obican_rgb_i_siv_jpeg_nikad_ne_prelazi_prag():
    """Svaki običan (jedan prolaz) RGB/sivi JPEG do ulazne granice od 40 MP ostaje ispod praga — proverava se cela
    rešetka veličina, uključujući granicu umanjenja (34,8 MP) i najgore razmere stranica."""
    T = X.MAX_JPEG_DEKODIRANJA_BAJTOVA
    for odnos in (1.0, 842 / 595, 2.0, 4.0):
        for mp10 in range(5, 401):
            px = mp10 * 100_000
            h = int(math.sqrt(px * odnos)); w = max(1, px // h)
            for nf in (1, 3):
                assert X._jpeg_procena_dekodiranja(_ok(w, h, nf)) <= T, (w, h, nf)


# ── PDF: ugrađen JPEG proverava se pre rasterizacije ───────────────────────────────────────────────────────────

fitz = pytest.importorskip("fitz")


def _pdf(tmp_path, strane, flate=False, ime="d.pdf"):
    """strane: lista ('tekst', str) ili ('jpeg', bytes)."""
    d = fitz.open()
    for vrsta, sadrzaj in strane:
        pg = d.new_page(width=595, height=842)
        if vrsta == "tekst":
            pg.insert_text((50, 72), sadrzaj, fontsize=11)
        else:
            pg.insert_image(pg.rect, stream=sadrzaj)
            if flate:
                x = pg.get_images(full=True)[0][0]
                d.update_stream(x, zlib.compress(sadrzaj), compress=False)
                d.xref_set_key(x, "Filter", "[/FlateDecode /DCTDecode]")
    p = tmp_path / ime
    d.save(str(p)); d.close()
    return p


def _bez_rasterizacije(monkeypatch):
    monkeypatch.setattr(X, "_rasterizuj_stranu", lambda *a: (_ for _ in ()).throw(AssertionError("rasterizacija pre odbijanja")))
    monkeypatch.setattr(X, "_ocr_image", lambda *a: (_ for _ in ()).throw(AssertionError("OCR pre odbijanja")))


@pytest.mark.parametrize("flate", [False, True])
def test_skeniran_pdf_sa_opasnim_jpeg_odbijen_pre_rasterizacije(monkeypatch, tmp_path, flate):
    data = _jpeg(progressive=True, subsampling=0)
    p = _pdf(tmp_path, [("jpeg", data)], flate=flate)
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", _okvir(data)["koeficijenti"] - 1)
    _bez_rasterizacije(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert ei.value.poruka == X.PORUKA_PREVELIK_JPEG_PDF and "strana 1" in ei.value.reason


def test_mesovit_pdf_proverava_samo_strane_koje_ce_ici_u_ocr(monkeypatch, tmp_path):
    data = _jpeg(progressive=True, subsampling=0)
    tekst = "Ovo je digitalna strana sa dovoljno teksta da se ne salje u OCR. " * 3
    p = _pdf(tmp_path, [("tekst", tekst), ("jpeg", data)])
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", _okvir(data)["koeficijenti"] - 1)
    _bez_rasterizacije(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert "strana 2" in ei.value.reason


def test_digitalan_pdf_bez_rasterizacije_nije_odbijen(monkeypatch, tmp_path):
    """Opasna slika na strani SA tekstom: strana se ne rasterizuje, pa nema ni odbijanja."""
    data = _jpeg(progressive=True, subsampling=0)
    tekst = "Digitalna strana sa slikom i dovoljno teksta za tekstualni sloj dokumenta. " * 3
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    pg.insert_image(fitz.Rect(300, 500, 500, 800), stream=data); pg.insert_text((50, 72), tekst[:90], fontsize=9)
    pg.insert_text((50, 100), tekst[90:180], fontsize=9)
    p = tmp_path / "dig.pdf"; d.save(str(p)); d.close()
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", 0)
    _bez_rasterizacije(monkeypatch)
    tekst_out, skeniran, ocr, strane, _ = X.extract(p)
    assert skeniran is False and ocr is False and len(strane) == 1


def test_pdf_sa_obicnim_jpeg_nije_odbijen(monkeypatch, tmp_path):
    """Običan JPEG u PDF-u: bafer koeficijenata je 0, pa se ovim pravilom ne odbija (raster još nije pokriven)."""
    p = _pdf(tmp_path, [("jpeg", _jpeg(subsampling=0))])
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", 0)
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: ("tekst " * 40, 0.9))
    assert X.extract(p)[2] is True


def test_provera_pdf_ne_cita_smestaj_slike(monkeypatch, tmp_path):
    """NS2b F2: page.get_image_rects/get_image_info dekodira slike strane — provera ih ne sme pozivati."""
    data = _jpeg(progressive=True, subsampling=0)
    p = _pdf(tmp_path, [("jpeg", data)])
    for ime in ("get_image_rects", "get_image_info", "get_image_bbox", "get_text", "get_textpage"):
        monkeypatch.setattr(fitz.Page, ime, lambda *a, **k: (_ for _ in ()).throw(AssertionError("dekodiranje u proveri")))
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", _okvir(data)["koeficijenti"] - 1)
    _bez_rasterizacije(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded):
        X.extract(p)


def test_necitljive_strane_ne_rasterizuje_opasan_jpeg(monkeypatch, tmp_path):
    data = _jpeg(progressive=True, subsampling=0)
    p = _pdf(tmp_path, [("jpeg", data)])
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", 0)
    pravo = fitz.Page.get_pixmap
    pozivi = []
    monkeypatch.setattr(fitz.Page, "get_pixmap", lambda self, *a, **k: (pozivi.append(1), pravo(self, *a, **k))[1])
    assert X.necitljive_strane_pdf(p, [""]) is None
    assert pozivi == []
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", 128 << 20)
    assert X.necitljive_strane_pdf(p, [""]) == [] and pozivi == [1]     # ispod praga: meri se kao i ranije


def test_podrazumevani_prag_pdf_nizi_od_praga_slike():
    """Izmereno: JPEG u PDF-u nosi ~70 MiB više od iste fotografije (MuPDF tok + raster strane)."""
    assert X.MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA == 64 << 20 and X.MAX_JPEG_DEKODIRANJA_BAJTOVA == 150 << 20
    assert X._jpeg_bajtova_koeficijenata(3720, 5262, [(1, 1)] * 3) > X.MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA   # 20 MP 4:4:4
    assert X._jpeg_bajtova_koeficijenata(3720, 5262, [(2, 2), (1, 1), (1, 1)]) <= X.MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA


def test_pragovi_slike_i_pdf_su_odvojeni(monkeypatch, tmp_path):
    data = _jpeg(progressive=True, subsampling=0)
    p = _pdf(tmp_path, [("jpeg", data)])
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", 0)            # prag slike ne važi za PDF
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: ("tekst " * 40, 0.9))
    assert X.extract(p)[2] is True
    foto = tmp_path / "f.jpg"
    foto.write_bytes(data)
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", 150 << 20)
    monkeypatch.setattr(X, "MAX_JPEG_KOEFICIJENATA_PDF_BAJTOVA", 0)      # prag PDF-a ne važi za fotografiju
    assert X.extract(foto)[2] is True


# ── Pozivaoci: intake worker bez ponovnih pokušaja, upload 413 sa porukom ────────────────────────────────────────

@pytest.mark.anyio
async def test_worker_odbijanje_je_terminalno_bez_ponovnih_pokusaja():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-9", "attempts": 0, "max_attempts": 5}

    async def _odbij(self, job):
        raise DocumentSafetyLimitExceeded("slika: JPEG 5317x7523 ...", poruka=X.PORUKA_PREVELIK_JPEG)

    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch.object(IntakeWorker, "_process", _odbij), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()) as mock_complete, \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as mock_failed, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        assert await w._tick() is True

    mock_complete.assert_not_awaited()
    # attempts+1 >= max_attempts → mark_job_failed odmah piše dead-letter ('failed'), bez next_retry_at
    mock_failed.assert_awaited_once_with("job-9", X.PORUKA_PREVELIK_JPEG, 0, 1)


@pytest.mark.anyio
async def test_mark_job_failed_sa_terminalnim_argumentima_ne_zakazuje_ponovni_pokusaj():
    from shared import intake_queue

    pozivi = []

    class _Supa:
        def rpc(self, ime, params):
            pozivi.append((ime, params))
            return types.SimpleNamespace(execute=lambda: None)

    with patch.object(intake_queue, "_get_supa", return_value=_Supa()):
        await intake_queue.mark_job_failed("job-9", X.PORUKA_PREVELIK_JPEG, 0, 1)
    (ime, params), = pozivi
    assert ime == "fail_intake_job" and params["p_new_attempts"] == 1 and params["p_max_attempts"] == 1
    assert params["p_next_retry_at"] is None and params["p_error"] == X.PORUKA_PREVELIK_JPEG


@pytest.mark.anyio
async def test_worker_ostale_greske_i_dalje_idu_kroz_retry():
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-3", "attempts": 2, "max_attempts": 5}

    async def _boom(self, job):
        raise RuntimeError("prolazna greska")

    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch.object(IntakeWorker, "_process", _boom), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()), \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as mock_failed, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        await w._tick()
    mock_failed.assert_awaited_once_with("job-3", "prolazna greska", 2, 5)


@pytest.mark.anyio
async def test_upload_u_predmet_vraca_413_sa_porukom_za_korisnika():
    from fastapi import HTTPException
    import test_sprint002_pipeline_a_orphan_cleanup as base

    supa = base._supa_upload_succeeds()
    patches = base._base_patches(supa, extract_side_effect=DocumentSafetyLimitExceeded("slika: ...", poruka=X.PORUKA_PREVELIK_JPEG))
    with pytest.raises(HTTPException) as ei:
        await base._run_with_patches(patches, filename="foto.jpg", content_type="image/jpeg")
    assert ei.value.status_code == 413 and ei.value.detail == X.PORUKA_PREVELIK_JPEG


@pytest.mark.anyio
async def test_upload_u_predmet_ostala_ogranicenja_zadrzavaju_staru_poruku():
    from fastapi import HTTPException
    import test_sprint002_pipeline_a_orphan_cleanup as base

    supa = base._supa_upload_succeeds()
    patches = base._base_patches(supa, extract_side_effect=DocumentSafetyLimitExceeded("zip bomb ratio"))
    with pytest.raises(HTTPException) as ei:
        await base._run_with_patches(patches, filename="tuzba.docx")
    assert ei.value.status_code == 413 and "bezbednosni limit" in ei.value.detail
