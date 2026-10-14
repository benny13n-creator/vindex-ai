# -*- coding: utf-8 -*-
"""NS2 B1 — OCR pod produkcionim startom (gunicorn, jedan radnik, 512 MiB).

Izmereno (CI, produkciona slika, `gunicorn ... -c gunicorn.conf.py`, cgroup 512 MiB):
  * par worker + finalizacija OOM-ubija radnika iako se rasterizacija/OCR nikad ne preklapaju — druga nit je za to
    vreme obrađivala SVOJ dokument van _RASTER_OCR_LOCK (pypdf, otvoren MuPDF dokument, međurezultati);
  * glibc posle prvog OCR posla zadržava oslobođene velike bafere (pomeren prag mmap-a): radnik 196 → 313 MiB, u
    gunicorn-u pod HTTP opterećenjem do ~390 MiB, pa sledeći dokument OOM-ubija radnika. Fiksan prag 1 MiB: bez toga.
Ugovori ispod ne traže Tesseract (OCR poziv je zamenjen).
"""
import gc
import io
import os
import sys
import threading
import time
import weakref

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

fitz = pytest.importorskip("fitz")
Image = pytest.importorskip("PIL.Image")
pypdf = pytest.importorskip("pypdf")

from uploaded_doc import extractor  # noqa: E402

TEKST = "Tužilac Marko Petrović, Osnovni sud u Beogradu, ročište zakazano za novembar " * 2


def _sken(putanja, strana=3):
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


def _slika(putanja):
    from PIL import ImageDraw
    img = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(img).rectangle((60, 80, 300, 160), fill="black")
    img.save(str(putanja), "PNG")


class _Dnevnik:
    """Beleži (nit, događaj) za svaki korak obrade dokumenta, uključujući korake VAN _RASTER_OCR_LOCK."""

    def __init__(self):
        self.d = []
        self._l = threading.Lock()

    def upisi(self, sta):
        with self._l:
            self.d.append((threading.current_thread().name, sta))

    def blokovi(self):
        """Niz niti po redu rada, uzastopni događaji iste niti spojeni: [A, B] = jedan dokument pa drugi."""
        out = []
        for nit, _ in self.d:
            if not out or out[-1] != nit:
                out.append(nit)
        return out


def _instrumentisi(monkeypatch, dn, kasnjenje=0.15):
    pravi_reader = pypdf.PdfReader
    pravi_render = fitz.Page.get_pixmap
    pravi_open = Image.open

    def _reader(*a, **k):
        dn.upisi("pypdf+")
        time.sleep(kasnjenje)           # parsiranje PDF-a: VAN _RASTER_OCR_LOCK
        r = pravi_reader(*a, **k)
        dn.upisi("pypdf-")
        return r

    def _render(self, *a, **k):
        dn.upisi("render")
        time.sleep(0.03)
        return pravi_render(self, *a, **k)

    def _open(fp, *a, **k):
        if isinstance(fp, (str, os.PathLike)):
            dn.upisi("slika+")
            time.sleep(kasnjenje / 3)
        return pravi_open(fp, *a, **k)

    def _ocr(img, jezik):
        dn.upisi("ocr")
        time.sleep(0.05)
        return TEKST, 0.9

    monkeypatch.setattr(pypdf, "PdfReader", _reader)
    monkeypatch.setattr(fitz.Page, "get_pixmap", _render)
    monkeypatch.setattr(Image, "open", _open)
    monkeypatch.setattr(extractor, "_ocr_image", _ocr)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")


def _u_dve_niti(prvi, drugi):
    greske = []

    def _omot(fn):
        def _r():
            try:
                fn()
            except Exception as e:  # pragma: no cover — prijavljuje se ispod
                greske.append(e)
        return _r

    a = threading.Thread(target=_omot(prvi), name="A")
    b = threading.Thread(target=_omot(drugi), name="B")
    a.start()
    time.sleep(0.05)                    # B kreće dok je A usred SVOG dokumenta
    b.start()
    a.join(60)
    b.join(60)
    assert not greske, greske


@pytest.mark.parametrize("drugi", ["sken", "slika", "necitljive"])
def test_ceo_dokument_se_obradjuje_jedan_za_drugim_u_procesu(tmp_path, monkeypatch, drugi):
    """Worker (skeniran PDF) i finalizacija/otpremanje (drugi PDF, fotografija ili merenje nečitljivih strana) u dve
    niti kao asyncio.to_thread: drugi dokument ne počinje NIŠTA (ni pypdf, ni otvaranje slike, ni MuPDF) dok prvi
    nije gotov. Ranije je samo rasterizacija/OCR bila pod zaključavanjem, pa je druga nit paralelno parsirala svoj
    dokument — to je u 512 MiB OOM-ubijalo radnika."""
    a, b, foto = tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "f.png"
    _sken(a, 3)
    _sken(b, 2)
    _slika(foto)
    dn = _Dnevnik()
    _instrumentisi(monkeypatch, dn)
    druga_obrada = {
        "sken": lambda: extractor.extract(b),
        "slika": lambda: extractor.extract(foto),
        "necitljive": lambda: extractor.necitljive_strane_pdf(b, ["", ""]),
    }[drugi]
    _u_dve_niti(lambda: extractor.extract(a), druga_obrada)
    assert {n for n, _ in dn.d} == {"A", "B"}, dn.d
    assert dn.blokovi() == ["A", "B"], f"dokumenti su se preplitali: {dn.d}"
    assert not extractor._DOKUMENT_LOCK.locked()


def test_zakljucavanje_dokumenta_se_pusta_i_kad_dokument_padne(tmp_path):
    """Prevelika slika (DocumentSafetyLimitExceeded) i oštećen PDF ne smeju da ostave zaključan proces."""
    velika = tmp_path / "v.png"
    Image.new("L", (8000, 6000), "white").save(str(velika), "PNG")      # 48 MP > MAX_IMAGE_PIXELS
    with pytest.raises(extractor.DocumentSafetyLimitExceeded):
        extractor.extract(velika)
    assert not extractor._DOKUMENT_LOCK.locked()
    los = tmp_path / "x.pdf"
    los.write_bytes(b"%PDF-1.4 nije pdf")
    with pytest.raises(Exception):
        extractor.extract(los)
    assert not extractor._DOKUMENT_LOCK.locked()
    assert extractor.necitljive_strane_pdf(los, [""]) is None
    assert not extractor._DOKUMENT_LOCK.locked()


def test_pypdf_citac_nije_ziv_dok_traje_ocr(tmp_path, monkeypatch):
    """pypdf objekti (sa učitanim tokovima slika strana) se oslobađaju pre OCR-a skeniranog PDF-a."""
    sken = tmp_path / "s.pdf"
    _sken(sken, 2)
    pravi_reader = pypdf.PdfReader
    citaci = []

    def _reader(*a, **k):
        r = pravi_reader(*a, **k)
        citaci.append(weakref.ref(r))
        return r

    zivi_tokom_ocr = []

    def _ocr(img, jezik):
        gc.collect()
        zivi_tokom_ocr.append(sum(1 for c in citaci if c() is not None))
        return TEKST, 0.9

    monkeypatch.setattr(pypdf, "PdfReader", _reader)
    monkeypatch.setattr(extractor, "_ocr_image", _ocr)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "eng")
    _, _, ocr_used, strane, _ = extractor.extract_pdf(sken)
    assert ocr_used and len(strane) == 2
    assert zivi_tokom_ocr == [0, 0], zivi_tokom_ocr


class _LaznaLibc:
    def __init__(self):
        self.pozivi = []

    def mallopt(self, param, vrednost):
        self.pozivi.append((param, vrednost))
        return 1


def test_prag_mmap_se_postavlja_jednom_pre_prvog_dokumenta(tmp_path, monkeypatch):
    """glibc: M_MMAP_THRESHOLD (-3) = 1 MiB, tačno jednom, PRE nego što obrada prvog dokumenta počne."""
    import ctypes
    libc = _LaznaLibc()
    redosled = []
    monkeypatch.setattr(ctypes, "CDLL", lambda ime: (redosled.append("mallopt"), libc)[1])
    monkeypatch.setattr(extractor, "_mmap_prag", None)
    monkeypatch.setattr(extractor, "_malloc_trim", extractor._malloc_trim)   # lažna libc nema malloc_trim
    pravi_reader = pypdf.PdfReader
    monkeypatch.setattr(pypdf, "PdfReader", lambda *a, **k: (redosled.append("pypdf"), pravi_reader(*a, **k))[1])
    monkeypatch.setattr(extractor, "_ocr_image", lambda img, j: (TEKST, 0.9))
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "eng")
    sken, foto = tmp_path / "s.pdf", tmp_path / "f.png"
    _sken(sken, 1)
    _slika(foto)
    extractor.extract(sken)
    extractor.extract(foto)
    extractor.necitljive_strane_pdf(sken, [""])
    assert libc.pozivi == [(-3, 1 << 20)], libc.pozivi
    assert redosled[:2] == ["mallopt", "pypdf"], redosled
    assert extractor._mmap_prag is True


def test_prag_mmap_van_glibc_je_bez_dejstva(monkeypatch):
    import ctypes

    def _nema(ime):
        raise OSError("nema libc.so.6")

    monkeypatch.setattr(ctypes, "CDLL", _nema)
    monkeypatch.setattr(extractor, "_mmap_prag", None)
    extractor._ogranici_zadrzavanje_memorije()
    extractor._ogranici_zadrzavanje_memorije()
    assert extractor._mmap_prag is False
