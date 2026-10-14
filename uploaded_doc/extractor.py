from __future__ import annotations

import logging
import math
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

    def __init__(self, reason: str):
        self.reason = reason
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
# Izmereno u produkcionoj slici pod 512 MiB (cgroup): uvezena aplikacija ~204 MiB; jedna A4 strana na 300 dpi
# (rasterizacija + Tesseract) ~360-380 MiB; DVA istovremena OCR-a (worker + finalizacija) su OOM ubila kontejner
# čak i za 1 stranu + 12 MP fotografiju. PyMuPDF uz to dokumentovano ne podržava rad iz više niti. Zato se svaki
# poziv MuPDF-a i OCR rasterizovane strane/slike odvija pod ovim zaključavanjem: u procesu je u svakom trenutku
# najviše jedna rasterizovana strana i jedan Tesseract. Zaključavanje je po strani (ne po dokumentu), pa dugačak
# dokument ne blokira drugi dokument do kraja — naizmenično napreduju stranu po stranu.
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
    img.draft("L", (sirina, visina))    # JPEG: dekodira odmah u sivoj skali (1 bajt/piksel); ostali formati: bez dejstva
    siva = img.convert("L")
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
            doc = fitz.open(str(path))
        dopuna: dict[int, str] = {}
        confs: list[float] = []
        try:
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
    except Exception as exc:
        logger.warning("[OCR] OCR strana bez teksta nije izvršen za %s: %s", path.name, exc)
        return {}, []


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
            doc = fitz.open(str(path))
            strane_doc = iter(doc)
        ocr_pages: list[str] = []
        ocr_confs: list[float] = []
        ocr_strana = 0
        try:
            ocr_rezultati = []
            while True:
                with _RASTER_OCR_LOCK:      # učitavanje strane je takođe poziv MuPDF-a
                    page = next(strane_doc, None)
                    if page is None:
                        break
                    img = _rasterizuj_stranu(page)
                    del page
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
        if ocr_strana and len(ocr_text.strip()) > 100:
            logger.info("[OCR] Uspešno — %d karaktera iz %d stranica", len(ocr_text), len(ocr_pages))
            return ocr_text, False, True, ocr_pages, ocr_confidence
        if total_chars > 0:
            # OCR001: OCR nije dodao dovoljno. Dokument OSTAJE označen kao nepročitan (is_scanned=True → pregled, kao
            # i ranije), ali se digitalni tekst (dopunjen stranama koje je OCR ipak pročitao) više ne briše.
            return ocr_text, True, bool(ocr_strana), ocr_pages, ocr_confidence if ocr_strana else None
        logger.warning("[OCR] OCR dao premalo teksta (%d chars)", len(ocr_text.strip()))
        _log_ocr_error("insufficient_text", path.name)
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


def necitljive_strane_pdf(path: Path, pages: list[str]) -> Optional[list[int]]:
    """Strane (1-indeksirano) bez pročitanog teksta, a sa vidljivim sadržajem. None = nije moguće izmeriti (PDF se
    ne može rasterizovati); pozivalac tada NE tvrdi ni da je strana pročitana ni da nije."""
    kandidati = [i for i, t in enumerate(pages or []) if len((t or "").strip()) < PRAG_KRATKE_STRANE]
    if not kandidati:
        return []
    try:
        import fitz  # pymupdf
        with _RASTER_OCR_LOCK:      # N02: MuPDF samo iz jedne niti u isto vreme (50 dpi, ~ms po strani)
            doc = fitz.open(str(path))
            try:
                if len(doc) != len(pages):
                    return None
                necitljive = []
                for i in kandidati:
                    strana = doc[i]
                    dpi = min(50, _dpi_strane(float(strana.rect.width), float(strana.rect.height)))
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

    if len(text) > 100:
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
