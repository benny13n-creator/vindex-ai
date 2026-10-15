from __future__ import annotations

import logging
import math
import re
import threading
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _log_ocr_error(reason: str, filename: str) -> None:
    """CELINA 5 (2026-07-24): OCR greške su ranije postojale SAMO kao Python
    logger pozivi (nevidljivi bez pristupa server logovima) -- upisuje u
    security_events za admin telemetriju (GET /api/admin/security-overview).
    Sinhrono, best-effort — extract_pdf se već izvršava u asyncio.to_thread
    workeru pozivaoca, i greška ovde nikad ne sme prekinuti ekstrakciju."""
    try:
        from api import _get_supa
        _get_supa().table("security_events").insert({
            "event_type": "ocr_error",
            "details": {"reason": reason, "filename": filename[:200]},
        }).execute()
    except Exception as e:
        logger.debug("[OCR] security_events upis neuspešan (nije kritično): %s", e)

# ─── SEC-007 — zip-bomb / decompression-bomb guard ────────────────────────────
# .docx is a ZIP archive — python-docx unzips it fully into memory with no
# built-in limit. A small file on disk can decompress to gigabytes.
#
# Thresholds: the task's own illustrative example (ratio > 10:1) is not used
# literally here — ordinary legal documents (repetitive boilerplate clauses,
# tables) routinely compress well past 10:1 in DOCX's XML format, which would
# make a 10:1 ratio cap reject real documents, not just bombs. Real zip-bomb
# payloads compress at 100:1-1000:1+ (they're built from highly repetitive
# byte patterns specifically to maximize this). MAX_RATIO below is set
# higher than the task's example specifically to avoid false-positives on
# legitimate large contracts, while the absolute MAX_DECOMPRESSED_BYTES cap
# (matching the task's own 50MB figure) is the primary, unambiguous defense —
# no legitimate case-file DOCX needs to unzip to more than 50MB of raw XML.
MAX_DECOMPRESSED_BYTES = 50 * 1024 * 1024   # 50 MB — task's own stated cap
MAX_RATIO = 100                              # compressed:decompressed, per-entry
MAX_ZIP_ENTRIES = 2_000                      # sane upper bound for a .docx package


class DocumentSafetyLimitExceeded(Exception):
    """Raised when a .docx archive's declared decompressed size, per-entry
    compression ratio, or entry count exceeds a safety threshold — BEFORE
    python-docx ever attempts to actually decompress the archive."""

    def __init__(self, reason: str, poruka: Optional[str] = None):
        self.reason = reason
        # NS2b: poruka za korisnika (srpski, bez brojeva memorije); None = pozivalac koristi svoju opštu poruku.
        self.poruka = poruka
        super().__init__(f"Zip-bomb guard tripped: {reason}")


def _check_docx_zip_safety(path: Path) -> None:
    """
    Inspects the ZIP central directory (metadata only — does NOT decompress
    any entry) before python-docx is allowed to touch the file. Raises
    DocumentSafetyLimitExceeded if the archive's own declared sizes would blow past a
    safety threshold, so the actual decompression (the expensive, memory-
    exhausting part) never happens for a malicious file.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        # Not a valid zip at all — let python-docx's own error handling
        # produce the "corrupt file" message; not this guard's concern.
        return

    if len(infos) > MAX_ZIP_ENTRIES:
        raise DocumentSafetyLimitExceeded(f"{len(infos)} entries (max {MAX_ZIP_ENTRIES})")

    total_decompressed = 0
    for info in infos:
        total_decompressed += info.file_size
        if total_decompressed > MAX_DECOMPRESSED_BYTES:
            raise DocumentSafetyLimitExceeded(
                f"total decompressed size exceeds {MAX_DECOMPRESSED_BYTES} bytes"
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_RATIO:
                raise DocumentSafetyLimitExceeded(
                    f"entry {info.filename!r} ratio {ratio:.0f}:1 exceeds {MAX_RATIO}:1"
                )


# ─── SEC-007 — PDF page-count ceiling (SEC-027 companion) ────────────────────
# Not a decompression-ratio attack (PDF's per-stream FlateDecode compression
# isn't exposed as a simple pre-check the way a ZIP central directory is) —
# a much simpler, cheap defense-in-depth cap against page-count-explosion
# DoS, already recommended separately as SEC-027.
MAX_PDF_PAGES = 500

# ─── Mission 001 (Night Shift M-001, 2026-08-02) — image decompression-bomb
# guard, same reasoning as SEC-007's DOCX check: a small JPEG/PNG can declare
# pixel dimensions that decompress to gigabytes in memory. PIL exposes the
# declared size via .size BEFORE decoding pixel data, so this check runs
# before Image.load()/any OCR preprocessing touches the pixel buffer.
MAX_IMAGE_PIXELS = 40_000_000  # ~40MP — comfortably above any real phone/scanner photo (typical: 8-24MP)


def _ocr_image(img, ocr_lang: str) -> tuple[str, Optional[float]]:
    """Shared OCR call — used by both extract_pdf's scanned-page loop and
    extract_image, so the two never silently drift (same preprocessing, same
    language fallback, same timeout). Caller passes an already-opened PIL
    Image; this does not open/close files.

    Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-023): now returns
    (text, confidence) instead of a bare string. `pytesseract.image_to_data`
    (vs. the old image_to_string) gives per-word confidence (0-100, -1 for
    unrecognized) alongside line/paragraph position -- text is reconstructed
    by joining words within the same (block, paragraph, line) and joining
    lines with '\\n', preserving the same line-based structure
    image_to_string produced. confidence is the mean of all recognized
    (non -1) word confidences, normalized to 0.0-1.0; None if OCR produced
    no recognized words at all (mirrors the old "" return for that case)."""
    import pytesseract

    img = img.convert("L")
    from PIL import ImageEnhance, ImageFilter
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.MedianFilter(size=3))

    def _run(lang: str, timeout: int) -> tuple[str, Optional[float]]:
        data = pytesseract.image_to_data(img, lang=lang, timeout=timeout, output_type=pytesseract.Output.DICT)
        n = len(data.get("text", []))
        line_order: list[tuple] = []
        line_words: dict[tuple, list[str]] = {}
        confs: list[float] = []
        for i in range(n):
            word = (data["text"][i] or "").strip()
            if word:
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                if key not in line_words:
                    line_words[key] = []
                    line_order.append(key)
                line_words[key].append(word)
            try:
                conf_val = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if conf_val >= 0:
                confs.append(conf_val)
        text = "\n".join(" ".join(line_words[k]) for k in line_order).strip()
        confidence = (sum(confs) / len(confs) / 100.0) if confs else None
        return text, confidence

    try:
        return _run(ocr_lang, 45)
    except Exception:
        try:
            return _run("eng", 30)
        except Exception:
            return "", None


def _detect_ocr_lang() -> str:
    """Same Cyrillic/Latin/English fallback logic extract_pdf already used —
    factored out so extract_image doesn't duplicate it."""
    import pytesseract

    try:
        available_langs = pytesseract.get_languages(config="")
    except Exception:
        available_langs = []

    if "srp" in available_langs and "srp_latn" in available_langs:
        return "srp+srp_latn+eng"
    elif "srp_latn" in available_langs:
        return "srp_latn+eng"
    elif "srp" in available_langs:
        return "srp+eng"
    return "eng"


def _oslobodi_kes_rasterizacije() -> None:
    """N02 (OCR memorija): MuPDF čuva DEKODIRANE slike strana u globalnom kešu procesa (podrazumevano do 256 MiB)
    i NE oslobađa ih ni posle doc.close(). Svaka skenirana strana se ovde rasterizuje tačno jednom, pa keš nikad
    nije pogođen — izmereno: +~25 MiB RSS po A4 strani na 300 dpi, do ~256 MiB koji ostaju zauzeti posle obrade.
    Pražnjenje ne menja nijedan piksel (keš, ne podatak), pa ni OCR rezultat."""
    try:
        import fitz  # pymupdf
        fitz.TOOLS.store_shrink(100)
    except Exception:
        pass


# ─── N02 (Workstream B) — jedna strana u memoriji u celom procesu ─────────────────────────────────────────────────
# Smart Intake worker, finalizacija i otpremanja pozivaju extract() preko asyncio.to_thread u ISTOM procesu.
# Izmereno u produkcionoj slici pod 512 MiB (cgroup): uvezena aplikacija + uploaded_doc ~240 MiB; jedna A4 strana
# na 300 dpi (rasterizacija + Tesseract) ~370-420 MiB; DVA istovremena OCR-a (worker + finalizacija) su OOM ubila
# kontejner čak i za 1 stranu + 12 MP fotografiju. PyMuPDF uz to dokumentovano ne podržava rad iz više niti. Zato
# se svaki poziv MuPDF-a i OCR rasterizovane strane/slike odvija pod ovim zaključavanjem: u procesu je u svakom
# trenutku najviše jedna rasterizovana strana i jedan Tesseract. Zaključavanje se uzima po strani, ali
# threading.Lock NIJE pravedno: izmereno (CI), nit koja ga pusti obično ga odmah ponovo uzme, pa drugi dokument
# može da čeka da prvi završi ceo (latencija, ne memorija).
_RASTER_OCR_LOCK = threading.Lock()

# Najveći broj piksela slike koja ide u OCR (strana PDF-a posle rasterizacije ili samostalna fotografija).
# Izmereno (CI, produkciona slika, --memory=512m, uvezen api): vrh kontejnera raste ~10,7 MiB po megapikselu
# rastera (A4 8,7 MP → 359 MiB, A3 17,4 MP → 452 MiB, A2 34,8 MP → OOM; 40 MP fotografija → OOM). Granica je
# izabrana tako da vrh pri samoj granici ostane ispod ~430 MiB, tj. da web proces zadrži ≥ 80 MiB za
# istovremene zahteve. Strana iznad granice se NE odbija: rasterizuje se sa nižim dpi tako da stane u granicu
# (A4/Letter/Legal na 300 dpi su ispod granice i ostaju nepromenjeni); fotografija iznad granice se pre OCR-a
# smanjuje na granicu. Kvalitet je izmeren na sintetičkim dokumentima sa poznatim tekstom (N02 izveštaj).
MAX_OCR_PIXELS = 15_000_000
OCR_DPI = 300
MIN_DEKODIRANIH_PIKSELA = 2480 * 3508   # A4 na 300 dpi: JPEG se ne dekodira umanjeno ispod ovoga

_malloc_trim = None


def _vrati_memoriju_sistemu() -> None:
    """N02: posle svake OCR-ovane strane/slike vraća operativnom sistemu memoriju koju je glibc zadržao.
    Izmereno pod 512 MiB: dve niti (worker + finalizacija) i POD zaključavanjem su OOM-ubile kontejner na dva
    skena od 10 strana — svaka nit ima sopstvenu glibc malloc arenu koja posle velikih bafera strane (raster, PNG,
    PIL kopije) zadržava oslobođenu memoriju, pa proces raste po niti (Python RSS 410 → 475 MiB). malloc_trim(0)
    je samo glibc (Linux, produkciona slika); drugde (Windows, macOS, musl) je bez dejstva."""
    global _malloc_trim
    if _malloc_trim is False:
        return
    try:
        if _malloc_trim is None:
            import ctypes
            _malloc_trim = ctypes.CDLL("libc.so.6").malloc_trim
        _malloc_trim(0)
    except Exception:
        _malloc_trim = False


# NS2 B1 (gunicorn, 512 MiB): glibc podrazumevano POMERA prag mmap-a naviše čim se oslobodi veliki bafer (do 32 MiB),
# pa se sledeći baferi strane/slike (raster, PNG, PIL blokovi) uzimaju iz heap-a i posle oslobađanja OSTAJU u procesu —
# malloc_trim ih ne vraća (izmereno: 196 → 313 MiB posle prvog OCR posla, ~46 MiB „slobodnog“ heap-a ostaje; posle
# više poslova u gunicorn radniku do ~390 MiB, pa sledeći dokument OOM-ubija radnika). Fiksan prag od 1 MiB: svaki
# bafer ≥ 1 MiB je zaseban mmap i vraća se sistemu odmah pri oslobađanju (izmereno: 313 → 267 MiB, bez rasta).
# Pikseli i OCR se ne menjaju (alokator, ne podatak). Samo glibc (Linux, produkciona slika); drugde bez dejstva.
_M_MMAP_THRESHOLD = -3
PRAG_MMAP_BAJTOVA = 1 << 20
_mmap_prag = None


def _ogranici_zadrzavanje_memorije() -> None:
    global _mmap_prag
    if _mmap_prag is not None:
        return
    try:
        import ctypes
        _mmap_prag = bool(ctypes.CDLL("libc.so.6").mallopt(_M_MMAP_THRESHOLD, PRAG_MMAP_BAJTOVA))
    except Exception:
        _mmap_prag = False


# NS2 B1: _RASTER_OCR_LOCK serijalizuje samo rasterizaciju i Tesseract, ali NE ostatak obrade dokumenta: dok jedna nit
# dekodira veliku sliku (progresivni JPEG od 40 MP: +~270 MiB), druga je istovremeno parsirala svoj PDF (pypdf),
# držala otvoren MuPDF dokument i svoje međurezultate — izmereno pod gunicorn-om i 512 MiB: par worker + finalizacija
# OOM-ubija radnika iako se OCR nikad ne preklapa. Zato je CEO PDF/slika dokument jedan za drugim u procesu (worker,
# finalizacija, otpremanja, napušteni zahtevi). Važi za JEDAN proces: više gunicorn radnika ovo ne pokriva.
_DOKUMENT_LOCK = threading.Lock()


def _jedan_dokument_u_procesu(fn):
    import functools

    @functools.wraps(fn)
    def omotac(*args, **kwargs):
        _ogranici_zadrzavanje_memorije()
        with _DOKUMENT_LOCK:
            return fn(*args, **kwargs)
    return omotac


# NS3-A: MuPDF bira format po SADRŽAJU, ne po ekstenziji: TIFF sa dodatim malim PDF-om i ekstenzijom .pdf prolazi
# pypdf, a MuPDF ga otvara kao TIFF (is_pdf=False, i uz filetype="pdf") i dekodira celu sliku mimo provere rastera PDF
# strane (pregled Task B: +434 MiB). PDF putanja zato prihvata samo ono što MuPDF zaista čita kao PDF.
PORUKA_NIJE_PDF = "Fajl nije ispravan PDF dokument. Sačuvajte ga ponovo kao PDF, pa pokušajte ponovo."


def _otvori_pdf(fitz, path: Path):
    """fitz.open za PDF putanju; DocumentSafetyLimitExceeded ako MuPDF fajl ne čita kao PDF. Poziva se pod _RASTER_OCR_LOCK."""
    doc = fitz.open(str(path))
    if not doc.is_pdf:
        doc.close()
        logger.warning("[OCR] Odbijeno — %s se ne otvara kao PDF", path.name)
        raise DocumentSafetyLimitExceeded("PDF putanja: MuPDF fajl ne otvara kao PDF", poruka=PORUKA_NIJE_PDF)
    return doc


def _dpi_strane(sirina_pt: float, visina_pt: float) -> int:
    """dpi rasterizacije strane: 300, osim ako bi raster prešao MAX_OCR_PIXELS — tada najveći dpi koji staje."""
    pikseli = (sirina_pt * OCR_DPI / 72.0) * (visina_pt * OCR_DPI / 72.0)
    if pikseli <= MAX_OCR_PIXELS:
        return OCR_DPI
    return max(1, int(OCR_DPI * math.sqrt(MAX_OCR_PIXELS / pikseli)))


def _zatvori_dokument(doc) -> None:
    """Zatvara MuPDF dokument i odmah vraća ono što je on držao (keš + glibc). Izmereno: bez ovoga posle
    PDF-a sa velikom ugrađenom slikom (97 MP, Flate) sledeći OCR u drugoj niti počinje ~90 MiB više.
    Pozivalac drži _RASTER_OCR_LOCK."""
    doc.close()
    _oslobodi_kes_rasterizacije()
    _vrati_memoriju_sistemu()


def _rasterizuj_stranu(strana):
    """PIL slika strane za OCR, u granici MAX_OCR_PIXELS. Pozivalac drži _RASTER_OCR_LOCK."""
    import io
    from PIL import Image

    sirina, visina = float(strana.rect.width), float(strana.rect.height)
    dpi = _dpi_strane(sirina, visina)
    if dpi != OCR_DPI:
        logger.info("[OCR] Strana %.0fx%.0f pt rasterizovana na %d dpi (granica %d piksela)",
                    sirina, visina, dpi, MAX_OCR_PIXELS)
    pixmap = strana.get_pixmap(dpi=dpi)
    izvor = Image.open(io.BytesIO(pixmap.tobytes("png")))
    del pixmap
    _oslobodi_kes_rasterizacije()
    # Ista konverzija koju _ocr_image ionako radi prvo (piksel-identično), ali se RGB original (3 bajta/piksel)
    # više ne drži u procesu dok traje Tesseract — tada je zbir procesa i Tesseract-a najveći.
    img = izvor.convert("L")
    izvor.close()
    return img


# ─── NS2b — JPEG koji libjpeg mora celog da drži u memoriji (koeficijenti cele slike) ──────────────────────────────
# Progresivni JPEG (i sekvencijalni čiji prvi prolaz ne nosi sve komponente) libjpeg dekodira tek pošto pročita SVE
# prolaze, pa za svaku komponentu drži sve DCT koeficijente slike: blok 8x8 = 64 x 2 bajta. Taj bafer zavisi samo od
# zaglavlja (dimenzije, komponente, faktori uzorkovanja) — NE od draft/umanjenja i ne od izlazne veličine. Izmereno
# (NS2b, produkciona slika, gunicorn, 512 MiB): 40 MP progresivni 4:4:4 (229 MiB koeficijenata) dostiže 494–496 MiB.
# Običan (sekvencijalan, jedan prolaz) JPEG se dekodira red po red i ovo se na njega ne odnosi. Provera čita samo
# markere do prvog SOS (ništa se ne dekodira) i radi isto za samostalnu fotografiju i JPEG ugrađen u PDF.
# Fotografija: ista provera pokriva i OBIČAN JPEG čiji je dekodiran raster prevelik. _jpeg_procena_dekodiranja računa iz
# zaglavlja najveću istovremenu memoriju koju extract_image/_u_granici_ocr zaista traže: dekodiran izlaz u veličini koju
# draft izabere (1/1, 1/2, 1/4, 1/8, ne ispod MIN_DEKODIRANIH_PIKSELA; Pillow: L = 1 B, RGB/CMYK = 4 B po pikselu) plus
# najveće od: koeficijenti cele slike (dok traje dekodiranje), konverzija u sivu (L → kopija, RGB → L, CMYK → RGB → L =
# 4 + 1 B), umanjenje (među-slika + rezultat). Izmereno (NS2b, 54 sintetička JPEG-a 10–48 MP, sve vrste): procena se
# poklapa sa vrhom procesa na ±1 MiB. Primer: običan CMYK od 30 MP se dekodira u punoj veličini (draft ne sme ispod
# A4/300 dpi) → 257 MiB → OOM pod 512 MiB; CMYK od 40 MP se umanjuje na 1/2 → 86 MiB.
# Prag: najveća procena izmerena kao bezbedna pod produkcionom topologijom (gunicorn, WEB_CONCURRENCY=1, 512 MiB):
# progresivni 4:4:4 od 22,3 MP, procena 148 MiB → vrh kontejnera 404–409 MiB sam, 436–437 MiB uz istovremen sken od 10
# strana (≥ 75 MiB rezerve, isti razred kao već primljeni CMYK/PNG od 40 MP i sken od 10 strana).
# JPEG u PDF-u: MuPDF uz koeficijente drži i ceo tok i raster strane (96 MiB koeficijenata → 440, 127 MiB → 486, uz
# sken 502) — tu se koeficijenti računaju u procenu rastera strane (NS3-A, v. _odbij_pdf_preveliki_raster).
_JPEG_SOF = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC9, 0xCA, 0xCB})        # okviri koje libjpeg(-turbo) dekodira
_JPEG_SOF_HIJERARHIJSKI = frozenset({0xC5, 0xC6, 0xC7, 0xCD, 0xCE, 0xCF})  # libjpeg ih odbija pre ikakve alokacije
_JPEG_SOF_PROGRESIVNI = frozenset({0xC2, 0xCA})
MAX_JPEG_DEKODIRANJA_BAJTOVA = 150 * 1024 * 1024
PORUKA_PREVELIK_JPEG = (
    "Fotografija je sačuvana u formatu koji zahteva previše memorije za obradu (npr. progresivni ili CMYK JPEG "
    "visoke rezolucije). Sačuvajte je ponovo kao običan JPEG ili smanjite rezoluciju, pa pokušajte ponovo."
)
PORUKA_PREVELIK_JPEG_PDF = (
    "Dokument sadrži sliku čija obrada zahteva previše memorije (slika veoma visoke rezolucije, npr. CMYK ili "
    "progresivni JPEG). Sačuvajte dokument ponovo sa slikama manje rezolucije (npr. 300 dpi), pa pokušajte ponovo."
)


def _jpeg_sledeci_marker(f) -> Optional[int]:
    """Kao libjpeg next_marker: preskače bajtove do 0xFF i FF punjenje; FF00 nije marker. None = kraj toka."""
    while True:
        b = f.read(1)
        if not b:
            return None
        if b != b"\xff":
            continue
        while b == b"\xff":
            b = f.read(1)
        if not b:
            return None
        if b != b"\x00":
            return b[0]


def _jpeg_bajtova_koeficijenata(sirina: int, visina: int, komponente: list[tuple[int, int]]) -> int:
    """Veličina bafera koeficijenata cele slike kako ga libjpeg alocira (jdcoefct.c, jinit_d_coef_controller):
    po komponenti ceil(blokova po širini, h) x ceil(blokova po visini, v) blokova od 64 x 2 bajta."""
    hmax = max(h for h, _ in komponente)
    vmax = max(v for _, v in komponente)
    ukupno = 0
    for h, v in komponente:
        sir_blokova = -(-sirina * h // (hmax * 8))
        vis_blokova = -(-visina * v // (vmax * 8))
        ukupno += (-(-sir_blokova // h) * h) * (-(-vis_blokova // v) * v) * 128
    return ukupno


def _jpeg_okvir(f) -> Optional[dict]:
    """Zaglavlje JPEG toka (binarni fajl-objekat, od početka) do prvog SOS. None = nije JPEG ili ga libjpeg ionako
    odbija pre dekodiranja (nema SOI/SOF/SOS, dupli SOF, hijerarhijski okvir, prazna slika, loše uzorkovanje).
    `koeficijenti` = bajtovi koeficijenata cele slike kad ih libjpeg drži (više prolaza), inače 0."""
    if f.read(2) != b"\xff\xd8":
        return None
    okvir = None
    while True:
        m = _jpeg_sledeci_marker(f)
        if m is None or m in (0xD8, 0xD9):
            return None
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            continue                                    # samostalni markeri, bez dužine
        duzina = f.read(2)
        if len(duzina) < 2:
            return None
        # libjpeg/Pillow dužinu 0 ili 1 tretiraju kao prazan segment i nastavljaju (pregled A F1) -- isto i ovde
        n = max(0, int.from_bytes(duzina, "big") - 2)
        if m in _JPEG_SOF_HIJERARHIJSKI:
            return None
        if m in _JPEG_SOF:
            if okvir is not None:
                return None
            d = f.read(n)
            if len(d) < 6 or len(d) < 6 + 3 * d[5]:
                return None
            visina, sirina, nf = int.from_bytes(d[1:3], "big"), int.from_bytes(d[3:5], "big"), d[5]
            komponente = [(d[6 + 3 * i + 1] >> 4, d[6 + 3 * i + 1] & 15) for i in range(nf)]
            if not (sirina and visina and nf) or any(not (1 <= h <= 4 and 1 <= v <= 4) for h, v in komponente):
                return None
            okvir = {"sirina": sirina, "visina": visina, "komponente": komponente, "progresivni": m in _JPEG_SOF_PROGRESIVNI}
            continue
        if m == 0xDA:
            if okvir is None:
                return None
            d = f.read(1)
            if not d:
                return None
            # libjpeg (jdinput.c): ceo bafer kad je progresivan ILI prvi prolaz ne nosi sve komponente
            okvir["vise_prolaza"] = okvir["progresivni"] or d[0] < len(okvir["komponente"])
            okvir["koeficijenti"] = (_jpeg_bajtova_koeficijenata(okvir["sirina"], okvir["visina"], okvir["komponente"])
                                     if okvir["vise_prolaza"] else 0)
            return okvir
        f.seek(n, 1)


_PILLOW_BAJTOVA_PO_PIKSELU = {1: 1, 3: 4, 4: 4}     # L; RGB (YCbCr); CMYK/YCCK — Pillow čuva RGB/CMYK sa 4 B po pikselu


def _jpeg_procena_dekodiranja(okvir: dict) -> int:
    """Najveća istovremena memorija (bajtovi) dekodiranja fotografije putem extract_image → _u_granici_ocr, iz zaglavlja.
    Odražava taj put korak po korak (v. komentar iznad MAX_JPEG_DEKODIRANJA_BAJTOVA); menja se zajedno sa njim."""
    w, h = okvir["sirina"], okvir["visina"]
    nf = len(okvir["komponente"])
    if nf not in _PILLOW_BAJTOVA_PO_PIKSELU:
        return okvir["koeficijenti"]            # Pillow takav JPEG ne otvara; ostaje samo bafer koeficijenata
    px = w * h
    bpp = _PILLOW_BAJTOVA_PO_PIKSELU[nf]
    umanjenje = 0
    if px <= MAX_OCR_PIXELS:
        izlaz = px                              # bez draft-a: dekodira se u izvornom režimu, pa convert("L")
    else:
        kd = math.sqrt(min(1.0, MIN_DEKODIRANIH_PIKSELA / px))
        cilj_w, cilj_h = max(1, math.ceil(w * kd)), max(1, math.ceil(h * kd))
        k = min(w // cilj_w, h // cilj_h)
        s = next(s for s in (8, 4, 2, 1) if k >= s)     # Pillow JpegImageFile.draft: najveći DCT faktor ≤ k
        izlaz_w, izlaz_h = -(-w // s), -(-h // s)
        izlaz = izlaz_w * izlaz_h
        if nf == 3:
            bpp = 1                             # draft("L") menja RGB u L već u dekoderu; CMYK ostaje CMYK
        if izlaz > MAX_OCR_PIXELS:              # siva + LANCZOS (među-slika nova širina x stara visina) + rezultat
            ko = math.sqrt(MAX_OCR_PIXELS / px)
            nw, nh = max(1, int(w * ko)), max(1, int(h * ko))
            umanjenje = izlaz + nw * izlaz_h + nw * nh
    konverzija = izlaz * (5 if nf == 4 else 1)  # L → kopija; RGB → L; CMYK → RGB (4 B) → L (1 B)
    return izlaz * bpp + max(okvir["koeficijenti"], konverzija, umanjenje)


def _odbij_jpeg_preveliki_bafer(okvir: Optional[dict], opis: str, granica: int, poruka: str,
                                procena=lambda o: o["koeficijenti"]) -> None:
    """DocumentSafetyLimitExceeded ako je `procena(okvir)` (podrazumevano: bafer koeficijenata) veća od `granica`
    bajtova. Poziva se PRE svakog dekodiranja. Loguju se samo dimenzije i veličine."""
    if okvir is None:
        return
    bajtova = procena(okvir)
    if bajtova <= granica:
        return
    uzorkovanje = ",".join(f"{h}x{v}" for h, v in okvir["komponente"])
    razlog = (f"{opis}: JPEG {okvir['sirina']}x{okvir['visina']}, uzorkovanje {uzorkovanje}, "
              f"progresivni={okvir['progresivni']}, koeficijenti {okvir['koeficijenti'] >> 20} MiB, "
              f"procena {bajtova >> 20} MiB (max {granica >> 20} MiB)")
    logger.warning("[OCR] Odbijeno pre dekodiranja — %s", razlog)
    raise DocumentSafetyLimitExceeded(razlog, poruka=poruka)


# ─── NS3-A — memorija rasterizacije strane PDF-a, procenjena PRE prve rasterizacije ───────────────────────────────
# Prva opasna alokacija je MuPDF-ovo dekodiranje ugrađene slike unutar page.get_pixmap (draw-device.c
# fz_draw_fill_image → image.c fz_get_pixmap_from_image): slika se umanjuje samo 2^k puta, gde je k najveći za koji
# umanjena slika ostaje ≥ veličine slike na rasteru strane + 2 px. JPEG se umanjuje već u dekoderu (do 1/8), ostali
# tokovi (Flate, LZW, Fax, JBIG2...) red po red, a JPX i indeksirane slike tek posle punog dekodiranja. Dekodirana
# slika ostaje u kešu MuPDF-a dok se strana ne iscrta; slika sa više od 3 komponente (CMYK) se PRE umanjenja
# pretvara u RGB (još 3 B po pikselu), a umanjenje pravi među-sliku i sliku veličine rastera. Primer (izmereno,
# NS2b/NS3): običan CMYK JPEG od 30 MP preko cele A4 strane na 300 dpi dekodira se u punoj veličini (4606/2 < 2481)
# → 114 MiB CMYK + 86 MiB RGB → OOM pod 512 MiB; CMYK od 40 MP se dekodira na 1/2 → 38 + 29 MiB i prolazi.
# Provera zato pušta stranu kroz MuPDF interpreter sa uređajem koji samo BELEŽI svaku sliku koju bi crtač iscrtao
# (XObject, ugnežđene forme, maske, šabloni, Type3, anotacije — isti fz_run_page i ista matrica kao get_pixmap), a
# ne dekodira ništa: interpreter učitava samo kompresovan tok. Izuzetak su UMETNUTE slike (BI … ID … EI) koje MuPDF
# dekodira u punoj veličini već pri čitanju sadržaja — zato se tokovi sadržaja strane pre toga pretražuju bez
# interpretera (u delovima od 64 KiB) i njihovo puno dekodiranje ulazi u procenu.
# Procena strane = raster strane + zbir dekodiranih slika (keš) + najveća prolazna alokacija (CMYK→RGB i umanjenje,
# koeficijenti progresivnog JPEG-a, radna memorija JPX dekodera, puno dekodiranje umetnute slike). Lokalno izmereno
# (MuPDF 1.28, A4/300 dpi): procena je ≥ stvarnog prirasta rastera i najviše ~25 MiB iznad njega.
MAX_PDF_RASTER_BAJTOVA = 150 * 1024 * 1024
PORUKA_PDF_NEPROVERLJIV = (
    "Dokument nije bilo moguće bezbedno proveriti pre obrade (neuobičajen zapis slike u PDF-u). Sačuvajte ili "
    "odštampajte dokument ponovo kao PDF, pa pokušajte ponovo."
)
_JPX_BAJTOVA_PO_UZORKU = 4          # OpenJPEG dekodira u int32 po uzorku, MuPDF zatim pravi sliku od 1 B po uzorku
_TOKOVNI_TIPOVI = frozenset({"FZ_IMAGE_RAW", "FZ_IMAGE_FAX", "FZ_IMAGE_FLATE", "FZ_IMAGE_LZW", "FZ_IMAGE_RLD",
                             "FZ_IMAGE_BROTLI", "FZ_IMAGE_JBIG2", "FZ_IMAGE_JPEG"})
_snimac_slika = None


class _NeproverljivPdf(Exception):
    """Provera nije mogla da utvrdi veličinu slike (neuobičajen zapis) — tada se ne pretpostavlja da je bezbedna."""


def _klasa_snimaca_slika():
    """Uređaj (mupdf.FzDevice2) koji beleži slike koje bi crtač iscrtao — bez dekodiranja. Klasa se pravi jednom."""
    global _snimac_slika
    if _snimac_slika is not None:
        return _snimac_slika
    import io
    import pymupdf
    m = pymupdf.mupdf
    tipovi = {getattr(m, ime): ime for ime in _TOKOVNI_TIPOVI | {"FZ_IMAGE_JPX", "FZ_IMAGE_UNKNOWN"} if hasattr(m, ime)}

    class _SnimacSlika(m.FzDevice2):
        def __init__(self):
            super().__init__()
            self.use_virtual_fill_image()
            self.use_virtual_fill_image_mask()
            self.use_virtual_clip_image_mask()
            self.slike: list[dict] = []

        def _zabelezi(self, slika, ctm, maska: bool) -> None:
            cb = m.ll_fz_compressed_image_buffer(slika)
            tip = tipovi.get(cb.params.type, "?") if cb else None
            cs = None if maska else slika.colorspace
            indeksirana = bool(cs and m.ll_fz_colorspace_is_indexed(cs))
            okvir = None
            if tip == "FZ_IMAGE_JPEG" and cb.buffer:        # samo zaglavlje, iz kompresovanog toka (bez kopije)
                tok = m.fz_buffer_storage_memoryview(m.FzBuffer(m.ll_fz_keep_buffer(cb.buffer)))
                okvir = _jpeg_okvir(io.BytesIO(tok))
            self.slike.append({
                "w": int(slika.w), "h": int(slika.h), "tip": tip, "dekodirana": bool(slika.decoded),
                "n": 1 if maska else int(slika.n), "alfa": bool(cs is None or slika.use_colorkey),
                "indeksirana": indeksirana,
                "baza_n": m.ll_fz_colorspace_n(m.ll_fz_base_colorspace(cs)) if indeksirana else 0,
                "matte": bool(slika.use_colorkey and slika.mask), "okvir": okvir,
                "dx": math.hypot(ctm.a, ctm.b), "dy": math.hypot(ctm.c, ctm.d),
            })

        def fill_image(self, ctx, slika, ctm, alpha, color_params):
            self._zabelezi(slika, ctm, False)

        def fill_image_mask(self, ctx, slika, ctm, cs, boja, alpha, color_params):
            self._zabelezi(slika, ctm, True)

        def clip_image_mask(self, ctx, slika, ctm, scissor):
            self._zabelezi(slika, ctm, True)

    _snimac_slika = _SnimacSlika
    return _snimac_slika


def _mupdf_bajtovi_slike(s: dict, strana_px: int) -> tuple[int, int]:
    """(bajtova dekodirane slike koja ostaje u kešu, najveća prolazna alokacija) za jedno iscrtavanje, kako ih pravi
    MuPDF 1.2x (image.c fz_get_pixmap_from_image / compressed_image_get_pixmap, draw-device.c fz_draw_fill_image)."""
    w, h = s["w"], s["h"]
    if w <= 0 or h <= 0:
        return 0, 0
    dx, dy = int(s["dx"]) + 1, int(s["dy"]) + 1     # veličina na rasteru (+1: gridfit) → nikad veći faktor od MuPDF-a
    l2 = 0
    if not s["matte"]:
        while (w >> (l2 + 1)) >= min(dx, w) + 2 and (h >> (l2 + 1)) >= min(dy, h) + 2 and l2 < 6:
            l2 += 1
    n = s["n"] + (1 if s["alfa"] else 0)
    prolazno = 0
    if s["dekodirana"]:
        tw, th, kes = w, h, 0                       # već dekodirana pri učitavanju (ne dolazi iz PDF toka)
    elif s["tip"] in _TOKOVNI_TIPOVI and not s["indeksirana"]:
        f = 1 << l2
        tw, th = -(-w // f), -(-h // f)             # umanjuje dekoder ili tok red po red
        kes = tw * th * n
    else:                                           # JPX, indeksirana, nepoznat tip: puno dekodiranje, pa umanjenje
        tw, th = w, h
        if s["indeksirana"]:
            n = s["baza_n"] + (1 if s["alfa"] else 0)
            prolazno = w * h                        # indeksi pre pretvaranja u osnovni prostor boja
        kes = w * h * n
        if s["tip"] == "FZ_IMAGE_JPX":
            prolazno = w * h * s["n"] * _JPX_BAJTOVA_PO_UZORKU
    if s["okvir"] is not None:
        prolazno = max(prolazno, s["okvir"]["koeficijenti"])    # progresivni JPEG: koeficijenti cele slike
    px = tw * th
    umanjuje = s["dx"] < tw and s["dy"] < th
    raster = min(min(dx, tw) * min(dy, th), strana_px) * 3 if umanjuje else 0
    if s["n"] > 3 and not s["indeksirana"]:
        posle = px * 3 + raster                     # pretvaranje u RGB pre umanjenja, pa umanjena slika
    else:
        posle = 2 * raster if umanjuje else px * 3  # među-slika + umanjena; ili pretvaranje boja posle
    return kes, max(prolazno, posle)


def _tokovi_sadrzaja_strane(strana_obj) -> list[int]:
    """Brojevi objekata tokova sadržaja koje MuPDF interpretira za stranu: sadržaj, forme (ugnežđene), šabloni,
    meke maske ExtGState-a, Type3 glifovi, izgled anotacija. Šira lista je bezbedna (više provere), uža nije."""
    import pymupdf
    m = pymupdf.mupdf
    ime = m.pdf_new_name
    vidjeni: set[int] = set()
    tokovi: list[int] = []

    def vrednosti(d):
        return [m.pdf_dict_get_val(d, i) for i in range(m.pdf_dict_len(d))] if m.pdf_is_dict(d) else []

    def tok(o, dubina=0):
        if dubina > 64:
            raise _NeproverljivPdf("preduboko ugnežđen sadržaj strane")
        if m.pdf_is_stream(o):
            num = m.pdf_to_num(o)
            if num and num not in vidjeni:
                vidjeni.add(num)
                tokovi.append(num)
                resursi(m.pdf_dict_get(o, ime("Resources")), dubina + 1)
        elif m.pdf_is_array(o):
            for i in range(m.pdf_array_len(o)):
                tok(m.pdf_array_get(o, i), dubina + 1)
        elif m.pdf_is_dict(o):                      # /AP /N sa stanjima, /CharProcs
            for v in vrednosti(o):
                tok(v, dubina + 1)

    def resursi(res, dubina):
        if not m.pdf_is_dict(res):
            return
        for v in vrednosti(m.pdf_dict_get(res, ime("XObject"))) + vrednosti(m.pdf_dict_get(res, ime("Pattern"))):
            if m.pdf_is_stream(v) and not m.pdf_name_eq(m.pdf_dict_get(v, ime("Subtype")), ime("Image")):
                tok(v, dubina)
        for gs in vrednosti(m.pdf_dict_get(res, ime("ExtGState"))):
            sm = m.pdf_dict_get(gs, ime("SMask"))
            if m.pdf_is_dict(sm):
                tok(m.pdf_dict_get(sm, ime("G")), dubina)
        for font in vrednosti(m.pdf_dict_get(res, ime("Font"))):
            if m.pdf_name_eq(m.pdf_dict_get(font, ime("Subtype")), ime("Type3")):
                tok(m.pdf_dict_get(font, ime("CharProcs")), dubina)
                resursi(m.pdf_dict_get(font, ime("Resources")), dubina + 1)

    tok(m.pdf_dict_get(strana_obj, ime("Contents")))
    resursi(m.pdf_dict_get_inheritable(strana_obj, ime("Resources")), 0)
    annots = m.pdf_dict_get(strana_obj, ime("Annots"))
    for i in range(m.pdf_array_len(annots) if m.pdf_is_array(annots) else 0):
        tok(m.pdf_dict_get(m.pdf_dict_get(m.pdf_array_get(annots, i), ime("AP")), ime("N")))
    return tokovi


# PDF lekser (pdf-lex.c): beline i graničnici. "BI" se traži kao bilo koje pojavljivanje iza kog sledi belina,
# graničnik ili kraj (i u nizu znakova, imenu, posle broja): šire od MuPDF-a, nikad uže.
_PDF_BELINE = b"\x00\t\n\x0c\r "
_PDF_GRANICNICI = b"()<>[]{}/%"
_BI = re.compile(rb"BI(?=[\x00\t\n\x0c\r ()<>\[\]{}/%])")
_DELIC_TOKA = 65536
MAX_UMETNUTI_RECNIK_BAJTOVA = 1 << 20           # rečnik umetnute slike duži od ovoga se ne prihvata kao bezbedan
MAX_UMETNUTO_ZAGLAVLJE_BAJTOVA = 256 * 1024     # koliko podataka posle ID se čita za zaglavlje umetnutog JPEG-a
_UMETNUTI_PROSTORI = {b"G": 1, b"DeviceGray": 1, b"CalGray": 1, b"RGB": 3, b"DeviceRGB": 3, b"CalRGB": 3,
                      b"CMYK": 4, b"DeviceCMYK": 4}


class _TokSadrzaja:
    """Tok sadržaja kroz MuPDF filtere, čitan u delovima; drži samo ono što pretraga još nije prešla."""

    def __init__(self, pdf, num: int):
        import pymupdf
        self._m = pymupdf.mupdf
        self._stm = self._m.pdf_open_stream_number(pdf, num)
        self._buf = self._m.fz_new_buffer(_DELIC_TOKA)
        self.b = b""
        self.o = 0                                  # apsolutni položaj b[0]
        self.kraj = False

    def dopuni(self) -> bool:
        if self.kraj:
            return False
        k = self._m.ll_fz_read(self._stm.m_internal, self._buf.m_internal.data, _DELIC_TOKA)
        if not k:
            self.kraj = True
            return False
        self.b += self._m.raw_to_python_bytes(self._buf.m_internal.data, k)
        return True

    def bajt(self, poz: int) -> Optional[int]:
        while poz - self.o >= len(self.b):
            if not self.dopuni():
                return None
        return self.b[poz - self.o]

    def kriska(self, poz: int, n: int) -> bytes:
        while poz + n - self.o > len(self.b) and self.dopuni():
            pass
        return self.b[poz - self.o:poz - self.o + n]

    def odseci(self, poz: int) -> None:
        if poz > self.o:
            self.b = self.b[poz - self.o:]
            self.o = poz


class _Lekser:
    """Tokeni kao pdf_lex (dovoljno za rečnik umetnute slike: imena sa #xx, brojevi, nizovi znakova, nizovi, rečnici,
    ključne reči). Čita najviše MAX_UMETNUTI_RECNIK_BAJTOVA od početka."""

    def __init__(self, tok: _TokSadrzaja, poz: int):
        self.t, self.poz, self.granica = tok, poz, poz + MAX_UMETNUTI_RECNIK_BAJTOVA

    def _c(self) -> Optional[int]:
        if self.poz >= self.granica:
            raise _NeproverljivPdf("umetnuta slika: rečnik predug")
        c = self.t.bajt(self.poz)
        if c is not None:
            self.poz += 1
        return c

    def _rec(self, prvi: bytes = b"") -> bytes:
        s = bytearray(prvi)
        while True:
            c = self.t.bajt(self.poz)
            if c is None or c in _PDF_BELINE or c in _PDF_GRANICNICI:
                return bytes(s)
            self.poz += 1
            if c == 0x23:                           # '#xx' u imenu
                a, b = self.t.bajt(self.poz), self.t.bajt(self.poz + 1)
                if a is not None and b is not None and bytes([a, b]).isalnum():
                    try:
                        s.append(int(bytes([a, b]), 16))
                        self.poz += 2
                        continue
                    except ValueError:
                        pass
            s.append(c)

    def token(self) -> tuple[str, object]:
        while True:
            c = self._c()
            if c is None:
                return "EOF", None
            if c in _PDF_BELINE:
                continue
            if c == 0x25:                           # komentar do kraja reda
                while (c := self._c()) is not None and c not in (0x0A, 0x0D):
                    pass
                continue
            if c == 0x2F:
                return "NAME", self._rec()
            if c == 0x28:                           # (niz znakova) sa ugnežđenim zagradama i \ izlazom
                dubina = 1
                while dubina:
                    c = self._c()
                    if c is None:
                        return "EOF", None
                    if c == 0x5C:
                        self._c()
                    elif c == 0x28:
                        dubina += 1
                    elif c == 0x29:
                        dubina -= 1
                return "STRING", None
            if c == 0x3C:
                if self.t.bajt(self.poz) == 0x3C:
                    self.poz += 1
                    return "OPEN_DICT", None
                while (c := self._c()) is not None and c != 0x3E:
                    pass
                return "STRING", None
            if c == 0x3E:
                if self.t.bajt(self.poz) == 0x3E:
                    self.poz += 1
                    return "CLOSE_DICT", None
                return "ERROR", None
            if c == 0x29:
                return "ERROR", None
            if c in b"[]{}":
                return {0x5B: "OPEN_ARRAY", 0x5D: "CLOSE_ARRAY"}.get(c, "BRACE"), None
            rec = self._rec(bytes([c]))
            if c in b"+-.0123456789":
                broj = re.match(rb"[+-]?(\d+\.?\d*|\.\d*)", rec)
                tekst = broj.group(0) if broj else b""
                self.poz -= len(rec) - len(tekst)   # pdf_lex: broj se završava na prvom znaku koji nije broj
                if not tekst or tekst in (b"+", b"-", b"."):
                    return ("INT", 0) if tekst else ("KEYWORD", rec)
                return ("REAL", float(tekst)) if b"." in tekst else ("INT", int(tekst))
            return {b"true": ("TRUE", True), b"false": ("FALSE", False), b"null": ("NULL", None),
                    b"R": ("R", None)}.get(rec, ("KEYWORD", rec))


def _umetnuti_recnik(lx: _Lekser) -> Optional[dict]:
    """pdf_parse_dict za BI: vrednosti po ključu ili None ako bi MuPDF prijavio grešku (slika se tada ne učitava).
    Indirektan objekat → ("R", a, b)."""
    d: dict = {}
    tip, v = lx.token()
    while True:
        if tip == "CLOSE_DICT" or (tip == "KEYWORD" and v == b"ID"):
            return d
        if tip != "NAME":
            return None
        kljuc = v
        tip, v = lx.token()
        if tip in ("OPEN_ARRAY", "OPEN_DICT"):
            d[kljuc] = (_umetnuti_niz if tip == "OPEN_ARRAY" else _umetnuti_recnik)(lx)
            if d[kljuc] is None:
                return None                         # MuPDF baca grešku za ceo rečnik
        elif tip in ("NAME", "REAL", "STRING", "TRUE", "FALSE", "NULL"):
            d[kljuc] = (tip, v)
        elif tip == "INT":
            a = v
            tip, v = lx.token()
            if tip in ("CLOSE_DICT", "NAME") or (tip == "KEYWORD" and v == b"ID"):
                d[kljuc] = ("INT", a)
                continue                            # goto skip: ovaj token je sledeći ključ / kraj
            if tip == "INT":
                b = v
                tip, v = lx.token()
                if tip == "R":
                    d[kljuc] = ("R", a, b)
                    tip, v = lx.token()
                    continue
            d[kljuc] = ("NULL", None)
        elif tip == "EOF":
            return None
        else:
            d[kljuc] = ("NULL", None)
        tip, v = lx.token()


def _umetnuti_niz(lx: _Lekser) -> Optional[list]:
    niz: list = []
    while True:
        tip, v = lx.token()
        if tip == "EOF":
            return None
        if tip == "CLOSE_ARRAY":
            return niz
        if tip in ("OPEN_ARRAY", "OPEN_DICT"):
            v = (_umetnuti_niz if tip == "OPEN_ARRAY" else _umetnuti_recnik)(lx)
            if v is None:
                return None
            niz.append(v)
        else:
            niz.append((tip, v))


def _umetnuta_slika_bajtova(d: dict, tok: _TokSadrzaja, podaci: int) -> tuple[int, int]:
    """(puno dekodiranje, koeficijenti JPEG-a) umetnute slike kako je učitava pdf_load_image_imp (bez umanjenja)."""
    import io
    import zlib

    def vrednost(*kljucevi):
        for k in kljucevi:
            if k in d:
                return d[k]
        return None

    def ceo(*kljucevi) -> int:
        v = vrednost(*kljucevi)
        if v is None or not isinstance(v, tuple):
            return 0
        if v[0] == "R":
            raise _NeproverljivPdf("umetnuta slika: vrednost je indirektan objekat")
        return int(v[1]) if v[0] in ("INT", "REAL") else 0

    w, h = ceo(b"W", b"Width"), ceo(b"H", b"Height")
    if w <= 0 or h <= 0:
        return 0, 0                                 # MuPDF: "image width is zero" — ništa se ne dekodira
    maska = vrednost(b"IM", b"ImageMask") == ("TRUE", True)
    cs = vrednost(b"CS", b"ColorSpace")
    if maska or cs is None:
        n = 1
    elif isinstance(cs, tuple) and cs[0] == "NAME" and cs[1] in _UMETNUTI_PROSTORI:
        n = _UMETNUTI_PROSTORI[cs[1]]
    elif isinstance(cs, tuple) and cs[0] == "R":
        raise _NeproverljivPdf("umetnuta slika: prostor boja je indirektan objekat")
    else:
        n = 32                                      # indeksiran, imenovan resurs, DeviceN: najgori slučaj
    alfa = 1 if maska or isinstance(vrednost(b"Mask"), list) else 0
    f = vrednost(b"F", b"Filter")
    filtri = [x[1] for x in (f if isinstance(f, list) else [f]) if isinstance(x, tuple) and x[0] == "NAME"]
    koef = 0
    if filtri and filtri[-1] in (b"DCT", b"DCTDecode"):
        sirovo = tok.kriska(podaci, MAX_UMETNUTO_ZAGLAVLJE_BAJTOVA)
        pre = filtri[:-1]
        try:
            if not pre:
                zaglavlje = sirovo
            elif pre in ([b"AHx"], [b"ASCIIHexDecode"]):
                hexa = re.sub(rb"[^0-9A-Fa-f]", b"", sirovo.split(b">")[0])
                zaglavlje = bytes.fromhex(hexa[: len(hexa) // 2 * 2].decode())
            elif pre in ([b"Fl"], [b"FlateDecode"]):
                zaglavlje = zlib.decompressobj().decompress(sirovo, MAX_UMETNUTO_ZAGLAVLJE_BAJTOVA)
            else:
                raise ValueError("lanac filtera")
        except Exception:
            raise _NeproverljivPdf(f"umetnuta slika: JPEG iza filtera {'+'.join(x.decode('latin-1') for x in filtri)}")
        okvir = _jpeg_okvir(io.BytesIO(zaglavlje))
        if okvir is None and len(sirovo) >= MAX_UMETNUTO_ZAGLAVLJE_BAJTOVA:
            raise _NeproverljivPdf("umetnuta slika: zaglavlje JPEG-a nije pročitano")
        if okvir is not None:
            koef = okvir["koeficijenti"]
    return w * h * (n + alfa), koef


def _umetnute_slike(pdf, num: int) -> list[tuple[int, int]]:
    """(puno dekodiranje, koeficijenti JPEG-a) za svaku umetnutu sliku (BI … ID) u toku sadržaja `num`. Tok se čita
    kroz MuPDF filtere u delovima (bez interpretera, bez dekodiranja slika). Svako "BI" se proverava, i u nizu znakova
    ili binarnim podacima slike: lažno pronađena slika najviše poveća procenu, propuštena bi bila opasna."""
    tok = _TokSadrzaja(pdf, num)
    rezultat: list[tuple[int, int]] = []
    poz = 0
    while True:
        m_bi = _BI.search(tok.b, poz - tok.o)
        if m_bi is None:
            poz = max(poz, tok.o + len(tok.b) - 2)  # "BI" preko granice dela ostaje za sledeći krug
            tok.odseci(poz)
            if not tok.dopuni():
                return rezultat
            continue
        pocetak = tok.o + m_bi.start()
        lx = _Lekser(tok, pocetak + 2)
        d = _umetnuti_recnik(lx)
        if d is not None:
            podaci = lx.poz + 1                     # jedna belina posle ID (ili posle >>), \r\n kao jedna
            if tok.bajt(lx.poz) == 0x0D and tok.bajt(lx.poz + 1) == 0x0A:
                podaci += 1
            rezultat.append(_umetnuta_slika_bajtova(d, tok, podaci))
        poz = pocetak + 2
        tok.odseci(poz)


def _strana_px(strana, dpi: int) -> tuple[int, int]:
    return (math.ceil(float(strana.rect.width) * dpi / 72.0), math.ceil(float(strana.rect.height) * dpi / 72.0))


def _procena_rastera_strane(doc, i: int, dpi: int) -> tuple[int, str]:
    """(procena memorije u bajtovima, opis najveće slike) za rasterizaciju strane `i` na `dpi` — bez dekodiranja."""
    import pymupdf
    m = pymupdf.mupdf
    strana = doc[i]
    pw, ph = _strana_px(strana, dpi)
    strana_px = pw * ph
    strana_b = strana_px * 3
    umetnute: list[tuple[int, int]] = []
    pdf = m.pdf_specifics(doc.this)
    if pdf.m_internal:
        for num in _tokovi_sadrzaja_strane(m.pdf_page_from_fz_page(strana.this).obj()):
            try:
                umetnute.extend(_umetnute_slike(pdf, num))
            except _NeproverljivPdf:
                raise
            except Exception as exc:                # tok koji MuPDF ne može da pročita ne može ni da interpretira
                logger.info("[OCR] Tok sadržaja %d strane %d nije pročitan: %s", num, i + 1, type(exc).__name__)
    prolazno_umetnute = max((d + k for d, k in umetnute), default=0)
    if strana_b + prolazno_umetnute > MAX_PDF_RASTER_BAJTOVA:   # interpreter bi je dekodirao već pri popisu
        return strana_b + prolazno_umetnute, f"umetnuta slika ({len(umetnute)} na strani)"
    snimac = _klasa_snimaca_slika()()
    z = dpi / 72.0
    try:
        m.fz_run_page(strana.this, snimac, m.FzMatrix(z, 0, 0, z, 0, 0), m.FzCookie())
        m.fz_close_device(snimac)
    except Exception as exc:                        # crtač staje na istom mestu; računa se ono što bi stigao da iscrta
        logger.info("[OCR] Slike strane %d delimično popisane: %s", i + 1, type(exc).__name__)
    kes, prolazno, najveca, najveca_b = 0, prolazno_umetnute, "", -1
    for s in snimac.slike:
        k, p = _mupdf_bajtovi_slike(s, strana_px)
        kes += k
        prolazno = max(prolazno, p)
        if k + p > najveca_b:
            najveca, najveca_b = f"{s['tip']} {s['w']}x{s['h']}x{s['n']}", k + p
    return strana_b + kes + prolazno, najveca


def _odbij_pdf_preveliki_raster(doc, indeksi, dpi_strane=None) -> None:
    """NS3-A: DocumentSafetyLimitExceeded ako bi rasterizacija neke od zadatih strana (na dpi koji će zaista biti
    korišćen) prešla MAX_PDF_RASTER_BAJTOVA — PRE prve rasterizacije, bez dekodiranja ijedne slike iz PDF toka i bez
    punjenja keša MuPDF-a. Pozivalac drži _RASTER_OCR_LOCK. Loguju se samo dimenzije i veličine."""
    for i in indeksi:
        strana = doc[i]
        dpi = dpi_strane(strana) if dpi_strane else _dpi_strane(float(strana.rect.width), float(strana.rect.height))
        try:
            bajtova, opis = _procena_rastera_strane(doc, i, dpi)
        except _NeproverljivPdf as exc:
            razlog = f"PDF strana {i + 1}: {exc} — nije analizirano jer bezbednost nije utvrđena"
            logger.warning("[OCR] Odbijeno pre rasterizacije — %s", razlog)
            raise DocumentSafetyLimitExceeded(razlog, poruka=PORUKA_PDF_NEPROVERLJIV)
        if bajtova > MAX_PDF_RASTER_BAJTOVA:
            razlog = (f"PDF strana {i + 1} na {dpi} dpi: {opis}, procena {bajtova >> 20} MiB "
                      f"(max {MAX_PDF_RASTER_BAJTOVA >> 20} MiB)")
            logger.warning("[OCR] Odbijeno pre rasterizacije — %s", razlog)
            raise DocumentSafetyLimitExceeded(razlog, poruka=PORUKA_PREVELIK_JPEG_PDF)


def _u_granici_ocr(img):
    """Samostalna fotografija iznad MAX_OCR_PIXELS se pre OCR-a smanjuje na granicu (siva skala, LANCZOS); ispod
    granice se vraća ista, nepromenjena slika. Ulazna granica MAX_IMAGE_PIXELS (40 MP) ostaje ista: fotografija do
    40 MP se i dalje prima i čita, samo se OCR ne radi na rasteru koji pod 512 MiB ubija proces."""
    from PIL import Image

    sirina, visina = img.size
    if sirina * visina <= MAX_OCR_PIXELS:
        return img
    k = math.sqrt(MAX_OCR_PIXELS / (sirina * visina))
    cilj = (max(1, int(sirina * k)), max(1, int(visina * k)))
    logger.info("[OCR] Slika %dx%d smanjena na %dx%d pre OCR-a (granica %d piksela)", sirina, visina, *cilj, MAX_OCR_PIXELS)
    # JPEG: dekodira odmah u sivoj skali i, kad može, već umanjeno (DCT 1/2, 1/4, 1/8) — ali nikad ispod
    # MIN_DEKODIRANIH_PIKSELA (A4 na 300 dpi, referentni kvalitet skena). Izmereno (Windows, 40 MP): CMYK JPEG
    # +344 → +86 MiB, običan JPEG +115 → +20 MiB pre OCR-a. Ostali formati (PNG): bez dejstva.
    kd = math.sqrt(min(1.0, MIN_DEKODIRANIH_PIKSELA / (sirina * visina)))
    img.draft("L", (max(1, math.ceil(sirina * kd)), max(1, math.ceil(visina * kd))))
    siva = img.convert("L")
    if siva.size[0] * siva.size[1] <= MAX_OCR_PIXELS:
        return siva                     # dekoder je već umanjio ispod granice (i ne ispod MIN_DEKODIRANIH_PIKSELA)
    manja = siva.resize(cilj, Image.Resampling.LANCZOS)
    if siva is not img:
        siva.close()
    return manja


def _ocr_strane_pdf(path: Path, indeksi: list[int]) -> tuple[dict[int, str], list[float]]:
    """OCR samo zadatih strana PDF-a (0-indeksirano). Vraća ({indeks: tekst} za strane sa prepoznatim tekstom,
    listu pouzdanosti). Bilo koja greška okruženja (nema pymupdf/tesseract) → ({}, []) — isto kao ranije."""
    try:
        import fitz  # pymupdf

        ocr_lang = _detect_ocr_lang()
        with _RASTER_OCR_LOCK:
            doc = _otvori_pdf(fitz, path)
        dopuna: dict[int, str] = {}
        confs: list[float] = []
        try:
            with _RASTER_OCR_LOCK:
                _odbij_pdf_preveliki_raster(doc, indeksi)     # NS3-A: pre prve rasterizacije
            for i in indeksi:
                with _RASTER_OCR_LOCK:
                    img = _rasterizuj_stranu(doc[i])
                    tekst, conf = _ocr_image(img, ocr_lang)
                    del img
                    _vrati_memoriju_sistemu()
                if tekst and tekst.strip():
                    dopuna[i] = tekst
                    if conf is not None:
                        confs.append(conf)
        finally:
            with _RASTER_OCR_LOCK:
                _zatvori_dokument(doc)
        if dopuna:
            logger.info("[OCR] Mešovit PDF %s — OCR dopunio %d/%d strana bez teksta", path.name, len(dopuna), len(indeksi))
        return dopuna, confs
    except DocumentSafetyLimitExceeded:
        raise
    except Exception as exc:
        logger.warning("[OCR] OCR strana bez teksta nije izvršen za %s: %s", path.name, exc)
        return {}, []


@_jedan_dokument_u_procesu
def extract_pdf(path: Path) -> tuple[str, bool, bool, Optional[list[str]], Optional[float]]:
    """Return (text, is_scanned, ocr_used, pages, ocr_confidence).

    is_scanned=True  → PDF had no readable text and OCR also failed.
    ocr_used=True    → text came from OCR (scanned PDF successfully processed).
    ocr_confidence   → None when OCR wasn't used; a real 0.0-1.0 mean word-
                       confidence when it was (Phoenix Closure, LIVINGSYS-DEBT-023).

    Program Intake Sprint 005 (2026-08-05) -- `pages` is the 4th element,
    a per-page `list[str]` (1-indexed position = list index + 1), None only
    when no usable page-level text exists at all (OCR totally failed).
    Both code paths below already built this list internally before this
    sprint -- it was computed and then discarded at the `"\n\n".join(...)`
    return (Sprint 005 Fork A, `.vindex_ai_team/decisions/
    2026-08-05_intake_sprint005_fork_segmentation_audit.md` §1) purely
    because no caller needed page boundaries before Canonical Document
    Segmentation existed. Deliberately kept UNFILTERED (including
    zero-length pages) for the OCR path, unlike the old `ocr_text` join
    which dropped empty pages -- callers doing segmentation need an
    accurate page COUNT and POSITION (a blank-page separator is itself one
    of the segmentation signals, `shared/intake_segment.py`), which the old
    filtered join structurally could not provide."""
    import pypdf

    reader = pypdf.PdfReader(str(path))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise DocumentSafetyLimitExceeded(f"{len(reader.pages)} PDF pages (max {MAX_PDF_PAGES})")

    pages: list[str] = []
    total_chars = 0
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        pages.append(text)
        total_chars += len(text)

    avg_chars = total_chars / max(len(reader.pages), 1)
    page = None     # NS2 B1 pregled: promenljiva petlje drži poslednju pypdf stranu (i čitač) živim tokom OCR mešovitog PDF-a
    del reader      # NS2 B1: pypdf objekti (i učitani tokovi slika) se ne drže dok traje OCR
    # Threshold: <30 chars/stranica ili ukupno <80 = verovatno skenirani
    is_scanned = avg_chars < 30 or total_chars < 80

    if not is_scanned:
        # VCR001 T01: MEŠOVIT PDF (npr. digitalni podnesak + skeniran prilog). Prosek po strani prelazi prag, pa
        # se OCR ranije nije pokretao, a tekst skenirane strane se TIHO gubio (strana ostaje "", dokument „pročitan“).
        # Sada se OCR pokreće samo za strane bez tekstualnog sloja (< 30 znakova); potpuno digitalan PDF i dalje
        # ne poziva OCR. Neuspeh OCR-a ostavlja stranu praznom — nikad izmišljen tekst.
        kratke = [i for i, t in enumerate(pages) if len(t) < 30]
        dopuna, confs = _ocr_strane_pdf(path, kratke) if kratke else ({}, [])
        if not dopuna:
            return "\n\n".join(pages), False, False, pages, None
        for i, t in dopuna.items():
            pages[i] = t
        return "\n\n".join(pages), False, True, pages, ((sum(confs) / len(confs)) if confs else None)

    # OCR fallback for scanned/unreadable PDFs
    try:
        import fitz  # pymupdf

        ocr_lang = _detect_ocr_lang()
        logger.info("[OCR] Pokrenuti OCR za %s — jezik: %s", path.name, ocr_lang)

        with _RASTER_OCR_LOCK:
            doc = _otvori_pdf(fitz, path)
            strane_doc = iter(doc)
        ocr_pages: list[str] = []
        ocr_confs: list[float] = []
        ocr_strana = 0
        try:
            with _RASTER_OCR_LOCK:
                _odbij_pdf_preveliki_raster(doc, range(len(doc)))     # NS3-A: pre prve rasterizacije
            ocr_rezultati = []
            while True:
                with _RASTER_OCR_LOCK:      # učitavanje strane je takođe poziv MuPDF-a
                    page = next(strane_doc, None)
                    if page is None:
                        break
                    try:
                        img = _rasterizuj_stranu(page)
                    finally:
                        del page        # MuPDF objekat strane se oslobađa pod zaključavanjem i kad render padne
                    ocr_rezultati.append(_ocr_image(img, ocr_lang))
                    del img
                    _vrati_memoriju_sistemu()
        finally:
            with _RASTER_OCR_LOCK:
                _zatvori_dokument(doc)
        for page_num, (page_text, page_conf) in enumerate(ocr_rezultati):
            # OCR001: kratak, ali ISPRAVAN digitalni tekst (npr. dostavnica od tri reda, < 80 znakova) više se ne
            # zamenjuje kraćim ili praznim OCR rezultatom iste strane — digitalni sloj je tačniji od OCR-a.
            if len((page_text or "").strip()) <= len(pages[page_num]):
                ocr_pages.append(pages[page_num])
                continue
            if not page_text:
                logger.warning("[OCR] Stranica %d neuspešna", page_num + 1)
            ocr_pages.append(page_text)
            ocr_strana += 1
            if page_conf is not None:
                ocr_confs.append(page_conf)
        # Phoenix Closure (LIVINGSYS-DEBT-023): mean confidence across pages
        # that actually recognized at least one word -- a page that failed
        # OCR entirely (page_conf=None) correctly doesn't drag the average
        # down as if it were a genuinely low-confidence recognition.
        ocr_confidence = (sum(ocr_confs) / len(ocr_confs)) if ocr_confs else None

        ocr_text = "\n\n".join(p for p in ocr_pages if p)
        # NS2 B2b (F3): pune reči se broje samo iz OCR-om pročitanih strana; zadržane digitalne strane (OCR001) ne smeju
        # da dopune broj reči kojima se meri pouzdanost samo OCR strana.
        samo_ocr = "\n".join(o for o, d in zip(ocr_pages, pages) if o != d)
        if ocr_strana and (len(ocr_text.strip()) > 100 or _kratak_ocr_procitan(samo_ocr, ocr_confidence)):
            logger.info("[OCR] Uspešno — %d karaktera iz %d stranica", len(ocr_text), len(ocr_pages))
            return ocr_text, False, True, ocr_pages, ocr_confidence
        if total_chars > 0:
            # OCR001: OCR nije dodao dovoljno. Dokument OSTAJE označen kao nepročitan (is_scanned=True → pregled, kao
            # i ranije), ali se digitalni tekst (dopunjen stranama koje je OCR ipak pročitao) više ne briše.
            return ocr_text, True, bool(ocr_strana), ocr_pages, ocr_confidence if ocr_strana else None
        logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(ocr_text.strip()))
        _log_ocr_error("insufficient_text", path.name)
    except DocumentSafetyLimitExceeded:
        raise
    except ImportError as ie:
        logger.warning("[OCR] Potrebni paketi nisu instalirani (%s) — skenirani PDF ne može biti obrađen", ie)
        _log_ocr_error("missing_dependencies", path.name)
    except Exception as e:
        logger.error("[OCR] Neočekivana greška: %s", e)
        _log_ocr_error("unexpected_error", path.name)

    if total_chars > 0:
        # OCR001: OCR nedostupan ili pao — dokument ostaje označen kao nepročitan (is_scanned=True), ali digitalni tekst
        # koji PDF stvarno ima se ne odbacuje (ranije: "", pa prikačen dokument nije imao nijedan znak teksta).
        return "\n\n".join(pages), True, False, pages, None
    return "", True, False, None, None


# OCR001 — potpunost strana. Strana sa manje od 30 znakova teksta (isti prag kao odluka o OCR-u iznad) koja ipak ima
# vidljiv sadržaj nije pročitana: OCR nije uspeo, istekao je ili je dao prazan rezultat. Prazna strana (razdelnik)
# nema sadržaja i nije greška. Udeo tamnih piksela meri se na 50 dpi u sivoj skali (bez OCR-a, ~ms po strani).
PRAG_KRATKE_STRANE = 30
PRAG_VIDLJIVOG_SADRZAJA = 0.005     # 0,5 % tamnih piksela: prazna/skenirana bela strana je ispod, red teksta je iznad
# Prosečna pouzdanost reči OCR-a ispod koje se tekst skeniranih strana ne predstavlja kao pouzdano pročitan. Izmereno u
# produkcionoj slici (OCR001, CI): ispravno čitanje 0,88–0,96; ćirilica engleskim modelom 0,40–0,62 (CER 71–80 %).
PRAG_POUZDANOSTI_OCR = 0.75


# NS2 B2 — KRATAK skeniran dokument (dostavnica, pečat „overeno“, rešenje od jednog reda). Pravilo „> 100 znakova“
# je ispravno pročitan tekst od 15–99 znakova potpuno brisalo ("", strane None, „OCR nije uspeo“). Izmereno
# (sintetički skenovi, produkcioni OCR poziv, NS2 B2): pravi kratak tekst od 15–40 znakova, i posle umanjenja,
# zamućenja i JPEG q30, ima pouzdanost 0,85–0,93 i ≥ 2 reči sa ≥ 3 slova/cifre koje čine ≥ polovinu reči; šum
# (potezi, lukovi, tačke) koji OCR pretvori u ≤ 100 znakova ima pouzdanost 0,58–0,77 i najviše 1 takvu reč. Kratak OCR
# tekst se zato prihvata kao pročitan SAMO kad prođe oba uslova; inače ostaje nepročitan kao i ranije (bez teksta,
# na pregled advokata). Tekst duži od 100 znakova ovo pravilo ne dira.
MIN_PUNIH_RECI_KRATKOG_OCR = 2


def _kratak_ocr_procitan(tekst: str, pouzdanost: Optional[float]) -> bool:
    """Da li je OCR tekst od ≤ 100 znakova dovoljno pouzdan da se ne odbaci (v. komentar iznad)."""
    if pouzdanost is None or pouzdanost < PRAG_POUZDANOSTI_OCR:
        return False
    reci = (tekst or "").split()
    pune = [r for r in reci if sum(c.isalnum() for c in r) >= 3]
    return len(pune) >= MIN_PUNIH_RECI_KRATKOG_OCR and 2 * len(pune) >= len(reci)


def _dpi_uzorka_potpunosti(strana) -> int:
    return min(50, _dpi_strane(float(strana.rect.width), float(strana.rect.height)))


@_jedan_dokument_u_procesu
def necitljive_strane_pdf(path: Path, pages: list[str]) -> Optional[list[int]]:
    """Strane (1-indeksirano) bez pročitanog teksta, a sa vidljivim sadržajem. None = nije moguće izmeriti (PDF se
    ne može rasterizovati); pozivalac tada NE tvrdi ni da je strana pročitana ni da nije."""
    kandidati = [i for i, t in enumerate(pages or []) if len((t or "").strip()) < PRAG_KRATKE_STRANE]
    if not kandidati:
        return []
    try:
        import fitz  # pymupdf
        with _RASTER_OCR_LOCK:      # N02: MuPDF samo iz jedne niti u isto vreme (50 dpi, ~ms po strani)
            doc = _otvori_pdf(fitz, path)
            try:
                if len(doc) != len(pages):
                    return None
                # NS3-A: preveliki raster → nemerljivo (None), bez dekodiranja; isti dpi kao uzorak ispod
                _odbij_pdf_preveliki_raster(doc, kandidati, _dpi_uzorka_potpunosti)
                necitljive = []
                for i in kandidati:
                    strana = doc[i]
                    dpi = _dpi_uzorka_potpunosti(strana)
                    uzorak = strana.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY).samples
                    _oslobodi_kes_rasterizacije()
                    tamnih = len(uzorak) - len(uzorak.translate(None, bytes(range(128))))
                    if uzorak and tamnih / len(uzorak) >= PRAG_VIDLJIVOG_SADRZAJA:
                        necitljive.append(i + 1)
                return necitljive
            finally:
                _zatvori_dokument(doc)
    except Exception as exc:
        logger.warning("[OCR] potpunost strana nije izmerena za %s: %s", path.name, type(exc).__name__)
        return None


def upozorenje_jezika_ocr() -> Optional[str]:
    """OCR001 (B2): bez srpskih paketa `_detect_ocr_lang` tiho pada na engleski model. Tekst pročitan tako ne sme da
    izgleda kao pouzdano pročitan srpski dokument; pozivalac ovu poruku prikazuje uz dokument. None = oba paketa tu."""
    try:
        jezici = _detect_ocr_lang().split("+")
    except Exception:
        return "OCR jezici nisu provereni — tekst nije pročitan srpskim jezičkim modelom."
    nedostaju = [ime for kod, ime in (("srp", "ćirilica"), ("srp_latn", "latinica")) if kod not in jezici]
    if not nedostaju:
        return None
    return "OCR bez srpskog jezičkog paketa (" + ", ".join(nedostaju) + ") — tekst je možda netačno pročitan."


def extract_docx(path: Path) -> tuple[str, bool, bool, Optional[list[str]], Optional[float]]:
    import docx as _docx
    from docx.oxml.ns import qn as _qn
    from docx.table import Table as _Table

    # SEC-007 — inspect the zip central directory BEFORE letting python-docx
    # actually decompress anything; raises DocumentSafetyLimitExceeded and
    # aborts here if the file would blow past the safety thresholds.
    _check_docx_zip_safety(path)

    doc = _docx.Document(str(path))
    parts: list[str] = []

    for block in doc.element.body:
        tag = block.tag
        if tag == _qn("w:p"):
            text = "".join(
                node.text for node in block.iter(_qn("w:t")) if node.text
            )
            if text.strip():
                parts.append(text)
        elif tag == _qn("w:tbl"):
            table = _Table(block, doc)
            for row in table.rows:
                row_text = "\t".join(cell.text for cell in row.cells)
                if row_text.strip():
                    parts.append(row_text)

    # Program Intake Sprint 005: DOCX (OOXML) has no first-class "page"
    # object in the document model at all -- pagination is a rendering-time
    # computation (font metrics, page size, margins), not stored data the
    # way a PDF stores discrete page objects (Fork A, confirmed). `pages`
    # is genuinely None here, not an oversight -- there is nothing to
    # return. Segmentation for DOCX is out of this sprint's scope (see
    # CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md).
    # ocr_confidence is None -- no OCR involved, the concept doesn't apply
    # (Phoenix Closure, LIVINGSYS-DEBT-023).
    return "\n".join(parts), False, False, None, None


def extract_txt(path: Path) -> tuple[str, bool, bool, Optional[list[str]], Optional[float]]:
    text = path.read_text(encoding="utf-8")
    return text, False, False, None, None


# Suffixes extract_image() handles — a photographed/scanned document with no
# separate PDF wrapper (Mission 001 / Night Shift M-001, 2026-08-02: the
# single most-requested real intake case — a client photographs a served
# document and sends the photo directly).
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


@_jedan_dokument_u_procesu
def extract_image(path: Path) -> tuple[str, bool, bool, Optional[list[str]], Optional[float]]:
    """Return (text, is_scanned, ocr_used, pages, ocr_confidence) for a standalone
    photographed/scanned image — same return contract as extract_pdf, so
    callers (the intake worker, api.py's auto-analyze upload) don't need to
    special-case images. Every image goes through OCR (there is no "has a
    text layer" case the way a born-digital PDF has); is_scanned=True only
    means OCR itself failed to extract meaningful text, matching
    extract_pdf's own <100-chars-total threshold exactly, so downstream
    code (the intake worker's is_scanned branch, the review-queue routing)
    treats a failed image OCR identically to a failed PDF OCR.

    Program Intake Sprint 005: `pages` is always None here -- a single
    photographed page is inherently one page, by construction (Fork A:
    "no multi-page ambiguity possible here"), so there is no list to
    return, not a limitation to work around."""
    from PIL import Image

    try:
        with Image.open(path) as probe:
            probe.verify()
        # verify() invalidates the image object for further use (Pillow's own
        # documented behavior) -- reopen for the actual pixel-dimension check
        # and OCR pass below.
        with Image.open(path) as img:
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise DocumentSafetyLimitExceeded(
                    f"image is {width}x{height} ({width * height} pixels, max {MAX_IMAGE_PIXELS})"
                )
        # NS2b: po SADRŽAJU (ne po ekstenziji), pre ikakvog dekodiranja piksela.
        with open(path, "rb") as tok:
            _odbij_jpeg_preveliki_bafer(_jpeg_okvir(tok), "slika", MAX_JPEG_DEKODIRANJA_BAJTOVA, PORUKA_PREVELIK_JPEG,
                                        procena=_jpeg_procena_dekodiranja)
    except DocumentSafetyLimitExceeded:
        raise
    except Exception as e:
        logger.warning("[OCR] Nevalidna slika %s: %s", path.name, e)
        _log_ocr_error("invalid_image", path.name)
        return "", True, False, None, None

    try:
        ocr_lang = _detect_ocr_lang()
        logger.info("[OCR] Pokrenuti OCR za %s — jezik: %s", path.name, ocr_lang)
        with _RASTER_OCR_LOCK, Image.open(path) as izvor:
            img = _u_granici_ocr(izvor)
            if img is izvor:
                img = izvor.convert("L")    # piksel-identično konverziji u _ocr_image; original se ne drži tokom OCR-a
            izvor.close()                   # pun dekodiran original se oslobađa pre OCR-a
            text, confidence = _ocr_image(img, ocr_lang)
            del img
            _vrati_memoriju_sistemu()
    except ImportError as ie:
        logger.warning("[OCR] Potrebni paketi nisu instalirani (%s) — slika ne može biti obrađena", ie)
        _log_ocr_error("missing_dependencies", path.name)
        return "", True, False, None, None
    except Exception as e:
        logger.error("[OCR] Neočekivana greška: %s", e)
        _log_ocr_error("unexpected_error", path.name)
        return "", True, False, None, None

    if len(text) > 100 or _kratak_ocr_procitan(text, confidence):
        logger.info("[OCR] Uspešno — %d karaktera", len(text))
        return text, False, True, None, confidence

    logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(text))
    _log_ocr_error("insufficient_text", path.name)
    return "", True, False, None, None


def extract(path: Path) -> tuple[str, bool, bool, Optional[list[str]], Optional[float]]:
    """Return (text, is_scanned, ocr_used, pages, ocr_confidence).

    Program Intake Sprint 005 (2026-08-05): added `pages` as a 4th element
    to this shared contract (all 4 call sites -- api.py, routers/dokument.py,
    shared/intake_worker.py, routers/smart_intake.py -- destructure this
    tuple identically, confirmed by repo-wide grep, Fork A). Only Pipeline
    B's worker (shared/intake_worker.py) currently acts on `pages` (feeds
    it to shared/intake_segment.py's canonical segmentation engine); the
    other 3 call sites accept and ignore it, a deliberate, bounded scope
    decision -- see CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md.

    Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-023): added `ocr_confidence`
    as a 5th element -- None for non-OCR paths (has a real text layer, DOCX,
    TXT) or a total OCR failure; a real 0.0-1.0 mean word-confidence when OCR
    ran and recognized at least one word. Same "every call site destructures
    identically, only intake_worker.py currently acts on it" shape as
    `pages` above -- the other 3 call sites accept and ignore it."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".txt":
        return extract_txt(path)
    if suffix in IMAGE_SUFFIXES:
        return extract_image(path)
    raise ValueError(f"Unsupported file format: {suffix!r}")
