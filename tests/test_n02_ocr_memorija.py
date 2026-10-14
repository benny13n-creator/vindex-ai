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
    # (Workstream B: i posle zatvaranja dokumenta — poslednje „prazni“.)
    assert dogadjaji == ["render", "prazni", "ocr"] * 3 + ["prazni"], dogadjaji


def test_merenje_necitljivih_strana_prazni_kes_posle_svake_strane(tmp_path, monkeypatch):
    p = tmp_path / "sken.pdf"
    _mali_sken(p, 3)
    dogadjaji = _dnevnik_rasterizacije(monkeypatch)
    necitljive = extractor.necitljive_strane_pdf(p, ["", "", ""])
    assert necitljive == [1, 2, 3]
    _svaki_render_ispraznjen_pre_sledeceg(dogadjaji, 3)


# ── N02 Workstream B: jedna strana u memoriji u celom procesu + granica piksela pre OCR-a ─────────────────────
# Izmereno (CI, produkciona slika, --memory=512m, uvezen api ~204 MiB): worker + finalizacija u dve niti istog
# procesa OOM-ubijaju kontejner i za 1 stranu + 12 MP fotografiju; A2 strana na 300 dpi, PDF fotografije sa stranom
# po pikselima i fotografija od 40 MP OOM-ubijaju ga i same. Testovi ne trebaju Tesseract (OCR je zamenjen).

import threading  # noqa: E402
import time  # noqa: E402

LAZNI_TEKST = "Tužilac Marko Petrović, Osnovni sud u Beogradu, ročište zakazano za novembar " * 2


class _Merac:
    """Broji koliko niti je ISTOVREMENO u MuPDF rasterizaciji ili OCR-u i da li je zaključavanje držano."""

    def __init__(self):
        self.aktivno = 0
        self.najvise = 0
        self.van_zakljucavanja = []
        self._l = threading.Lock()

    def udji(self, sta):
        if not extractor._RASTER_OCR_LOCK.locked():
            self.van_zakljucavanja.append(sta)
        with self._l:
            self.aktivno += 1
            self.najvise = max(self.najvise, self.aktivno)

    def izadji(self):
        with self._l:
            self.aktivno -= 1


def _meri(monkeypatch, ocr_sekundi=0.05, velicine=None):
    m = _Merac()
    pravi_render = fitz.Page.get_pixmap
    pravi_open = fitz.open

    def _render(self, *a, **k):
        m.udji("render")
        try:
            return pravi_render(self, *a, **k)
        finally:
            m.izadji()

    def _open(*a, **k):
        if not extractor._RASTER_OCR_LOCK.locked():
            m.van_zakljucavanja.append("open")
        return pravi_open(*a, **k)

    def _ocr(img, jezik):
        m.udji("ocr")
        try:
            if velicine is not None:
                velicine.append(img.size)
            time.sleep(ocr_sekundi)
            return LAZNI_TEKST, 0.9
        finally:
            m.izadji()

    monkeypatch.setattr(fitz.Page, "get_pixmap", _render)
    monkeypatch.setattr(fitz, "open", _open)
    monkeypatch.setattr(extractor, "_ocr_image", _ocr)
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "srp+srp_latn+eng")
    return m


def _png(putanja, sirina, visina, fmt="PNG"):
    from PIL import ImageDraw
    img = Image.new("RGB", (sirina, visina), "white")
    ImageDraw.Draw(img).rectangle((sirina // 10, visina // 10, sirina // 2, visina // 5), fill="black")
    img.save(str(putanja), fmt)


def test_worker_i_finalizacija_u_dve_niti_nikad_ne_rasterizuju_ni_ocr_istovremeno(tmp_path, monkeypatch):
    """Worker (skeniran PDF + merenje nečitljivih strana) i finalizacija (mešovit PDF) + otpremanje fotografije,
    svako u svojoj niti kao asyncio.to_thread: u procesu je u svakom trenutku najviše jedna strana u rasterizaciji
    ili OCR-u, i svaki poziv MuPDF-a/OCR-a je pod zaključavanjem."""
    sken1, sken2, mesovit, foto = tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "m.pdf", tmp_path / "f.png"
    _mali_sken(sken1, 4)
    _mali_sken(sken2, 4)
    d = fitz.open()
    s = d.new_page(width=595, height=842)
    s.insert_text((50, 80), "Digitalna strana sa dovoljno teksta za tekstualni sloj " * 3, fontsize=8)
    d.insert_pdf(fitz.open(str(sken2)))
    d.save(str(mesovit))
    d.close()
    _png(foto, 800, 1000)
    m = _meri(monkeypatch)
    greske = []

    def _worker():
        try:
            text, _, ocr_used, strane, _ = extractor.extract(sken1)
            assert ocr_used and len(strane) == 4
            extractor.necitljive_strane_pdf(sken1, ["", "", "", ""])
        except Exception as e:  # pragma: no cover — prijavljuje se ispod
            greske.append(e)

    def _finalizacija():
        try:
            extractor.extract(mesovit)
            extractor.extract(foto)
        except Exception as e:  # pragma: no cover
            greske.append(e)

    niti = [threading.Thread(target=_worker), threading.Thread(target=_finalizacija)]
    [n.start() for n in niti]
    [n.join(60) for n in niti]
    assert not greske, greske
    assert m.najvise == 1, f"{m.najvise} istovremene rasterizacije/OCR-a u istom procesu"
    assert not m.van_zakljucavanja, f"MuPDF/OCR van zaključavanja: {sorted(set(m.van_zakljucavanja))}"


def test_dpi_strane_a4_ostaje_300_a_veca_strana_staje_u_granicu():
    assert extractor._dpi_strane(595, 842) == 300           # A4
    assert extractor._dpi_strane(612, 1008) == 300          # Legal
    for w, h in ((1191, 1684), (2384, 3370), (3024, 4032), (14400, 14400)):   # A2, A0, fotografija po pikselima, max
        dpi = extractor._dpi_strane(w, h)
        assert dpi < 300
        assert (w * dpi / 72) * (h * dpi / 72) <= extractor.MAX_OCR_PIXELS


def test_granica_piksela_je_izmerena_a_ulazna_granica_slike_nepromenjena():
    # A4 na 300 dpi (8,7 MP) mora ostati ispod granice — inače bi se menjao kvalitet svakog običnog skena.
    assert extractor.MAX_OCR_PIXELS >= 2480 * 3508
    # Izmereno pod 512 MiB: A3 (17,4 MP) → 452 MiB vrha, A2 (34,8 MP) → OOM. Granica ostavlja ≥ 80 MiB za web proces.
    assert extractor.MAX_OCR_PIXELS <= 15_000_000
    # Dokumentovana ulazna sposobnost (fotografija do 40 MP) se ne smanjuje ovom izmenom.
    assert extractor.MAX_IMAGE_PIXELS == 40_000_000


def test_strana_fotografije_po_pikselima_se_rasterizuje_u_granici(tmp_path, monkeypatch):
    """PDF iz fotografije sa stranom zadatom u pikselima (3024x4032 pt): na 300 dpi bi to bilo 211 MP (OOM pod
    512 MiB). Sada ide u OCR u granici, a obična A4 strana istog dokumenta ostaje na punih 300 dpi."""
    p = tmp_path / "foto.pdf"
    d = fitz.open()
    b = io.BytesIO()
    Image.new("RGB", (302, 403), "white").save(b, "PNG")
    s = d.new_page(width=3024, height=4032)
    s.insert_image(s.rect, stream=b.getvalue())
    s = d.new_page(width=595, height=842)
    s.insert_image(s.rect, stream=b.getvalue())
    d.save(str(p))
    d.close()
    velicine = []
    _meri(monkeypatch, ocr_sekundi=0, velicine=velicine)
    text, skeniran, ocr_used, strane, _ = extractor.extract_pdf(p)
    assert ocr_used is True and len(strane) == 2
    (w1, h1), (w2, h2) = velicine
    assert w1 * h1 <= extractor.MAX_OCR_PIXELS * 1.01, (w1, h1)
    assert w1 * h1 >= extractor.MAX_OCR_PIXELS * 0.9, "strana ne sme biti umanjena više nego što granica traži"
    assert (w2, h2) in ((2480, 3508), (2480, 3509)), (w2, h2)


def test_fotografija_iznad_granice_se_smanjuje_pre_ocr_a_ispod_granice_netaknuta(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_OCR_PIXELS", 1_000_000)
    velika, mala = tmp_path / "velika.jpg", tmp_path / "mala.png"
    _png(velika, 2000, 1500, "JPEG")     # 3 MP > 1 MP
    _png(mala, 800, 1000)                # 0,8 MP
    velicine = []
    _meri(monkeypatch, ocr_sekundi=0, velicine=velicine)
    t1, s1, o1, _, _ = extractor.extract_image(velika)
    t2, s2, o2, _, _ = extractor.extract_image(mala)
    assert o1 and o2 and not s1 and not s2
    (w1, h1), (w2, h2) = velicine
    assert w1 * h1 <= 1_000_000 and w1 * h1 >= 900_000, (w1, h1)
    assert abs(w1 / h1 - 2000 / 1500) < 0.01, "odnos stranica mora ostati isti"
    assert (w2, h2) == (800, 1000)


def test_posle_svake_ocr_strane_i_slike_memorija_se_vraca_sistemu(tmp_path, monkeypatch):
    """Izmereno: bez vraćanja glibc memorije dve niti pod zaključavanjem i dalje OOM-ubiju kontejner (svaka nit
    zadržava svoju malloc arenu). Ugovor: posle SVAKOG OCR-a (skenirana strana, dopunjena strana mešovitog PDF-a,
    fotografija) sledi vraćanje memorije, pre sledeće strane."""
    sken, foto = tmp_path / "s.pdf", tmp_path / "f.png"
    _mali_sken(sken, 3)
    _png(foto, 400, 500)
    dogadjaji = []
    monkeypatch.setattr(extractor, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(extractor, "_ocr_image", lambda img, j: (dogadjaji.append("ocr"), (LAZNI_TEKST, 0.9))[1])
    monkeypatch.setattr(extractor, "_vrati_memoriju_sistemu", lambda: dogadjaji.append("vrati"))
    extractor.extract_pdf(sken)
    extractor._ocr_strane_pdf(sken, [0, 1])
    extractor.extract_image(foto)
    # PDF: posle svake strane + posle zatvaranja dokumenta; fotografija: posle OCR-a.
    assert dogadjaji == ["ocr", "vrati"] * 3 + ["vrati"] + ["ocr", "vrati"] * 2 + ["vrati"] + ["ocr", "vrati"], dogadjaji


def test_vracanje_memorije_van_glibc_je_bez_dejstva():
    extractor._vrati_memoriju_sistemu()     # Windows/macOS/musl: nema libc.so.6 → tiho bez dejstva, nikad izuzetak
    extractor._vrati_memoriju_sistemu()
