# -*- coding: utf-8 -*-
"""NS3-B: samostalna slika (.jpg/.jpeg/.png) se prihvata samo kad je SADRŽAJ zaista JPEG ili PNG.

Dokazan problem: extract_image je otvarao bilo koji Pillow format po sadržaju — CMYK TIFF od 2,2 MB preimenovan u .jpg
prošao je mimo JPEG zaštite memorije (+347 MiB). Upload rute su gledale samo ekstenziju/MIME koje šalje klijent.

Ugovor posle ispravke:
- extractor: sadržaj koji nije JPEG/PNG → DocumentSafetyLimitExceeded(poruka=PORUKA_NIJE_JPEG_PNG) PRE otvaranja slike
  (Image.open se i ne poziva) i pre ikakvog dekodiranja; drugi sloj: Image.open(formats=("JPEG", "PNG")).
- upload u predmet (api.py): 415 sa istom porukom, pre čuvanja originala i pre extract().
- Smart Intake upload: {"ok": False, "greska": poruka} odmah, bez čuvanja i bez posla.
- intake worker (ako ipak stigne do njega): terminalni neuspeh posle 1 pokušaja, poruka u last_error.
- Politika: JPEG sadržaj sa ekstenzijom .png (i obrnuto) se PRIHVATA — podržan sadržaj, podržana ekstenzija; dekoder i
  zaštita memorije biraju se po sadržaju, nikad po ekstenziji. MPO (više JPEG slika, telefoni) je JPEG i pokriva ga ista
  JPEG zaštita (Pillow dekodira samo prvu sliku, čije zaglavlje čita _jpeg_okvir).
"""
import io
import os
import sys
import types
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image, ImageFile
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import HTTPException, UploadFile

from uploaded_doc import extractor as X
from uploaded_doc.extractor import DocumentSafetyLimitExceeded, PORUKA_NIJE_JPEG_PNG


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── Sintetičke slike ────────────────────────────────────────────────────────────────────────────────────────────

def _slika(fmt: str, mode: str = "RGB", size=(64, 48), **kw) -> bytes:
    boja = {"CMYK": (0, 0, 0, 0), "L": 255, "P": 0, "I;16": 65535, "RGBA": (255, 255, 255, 255)}.get(mode, "white")
    b = io.BytesIO()
    Image.new(mode, size, boja).save(b, fmt, **kw)
    return b.getvalue()


def _mpo() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), "white").save(b, "MPO", save_all=True, append_images=[Image.new("RGB", (64, 48), "red")])
    return b.getvalue()


def _png_chunk(tip: bytes, data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + tip + data + zlib.crc32(tip + data).to_bytes(4, "big")


def _png_zaglavlje(w: int, h: int) -> bytes:
    """PNG koji deklariše w x h (8-bit siva), sa malim IDAT-om — samo zaglavlje, ništa se ne alocira."""
    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 0, 0, 0, 0])
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(b"\x00" * 16))
            + _png_chunk(b"IEND", b""))


def _seg(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def _jpeg_zaglavlje_progresivni(w: int, h: int) -> bytes:
    """Progresivni 4:4:4 RGB JPEG koji deklariše w x h — samo zaglavlje (SOI, SOF2, SOS)."""
    sof = bytes([8]) + h.to_bytes(2, "big") + w.to_bytes(2, "big") + bytes([3]) + b"".join(bytes([i + 1, 0x11, 0]) for i in range(3))
    sos = bytes([3]) + b"".join(bytes([i + 1, 0]) for i in range(3)) + bytes([0, 0, 0])
    return b"\xff\xd8" + _seg(0xC2, sof) + _seg(0xDA, sos) + b"\x00" * 64 + b"\xff\xd9"


NEPODRZANI = [
    pytest.param(lambda: _slika("TIFF", "CMYK", (300, 200)), "foto.jpg", id="tiff_cmyk_kao_jpg"),
    pytest.param(lambda: _slika("TIFF"), "foto.png", id="tiff_kao_png"),
    pytest.param(lambda: _slika("GIF", "P"), "foto.jpg", id="gif_kao_jpg"),
    pytest.param(lambda: _slika("BMP"), "foto.png", id="bmp_kao_png"),
    pytest.param(lambda: _slika("WEBP"), "foto.jpg", id="webp_kao_jpg"),
    pytest.param(lambda: _slika("WEBP"), "foto.jpeg", id="webp_kao_jpeg"),
    pytest.param(lambda: b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", "foto.jpg", id="pdf_kao_jpg"),
    pytest.param(lambda: os.urandom(4096).replace(b"\x89PNG", b"xxxx").replace(b"\xff\xd8\xff", b"xxx"),
                 "foto.png", id="nasumicni_bajtovi_kao_png"),
    pytest.param(lambda: b"", "foto.jpg", id="prazan"),
]


def _bez_otvaranja_i_dekodiranja(monkeypatch):
    """Svaki pokušaj otvaranja/dekodiranja/OCR-a je greška testa (ne tiho 'neuspešan OCR')."""
    monkeypatch.setattr(Image, "open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Image.open pre odbijanja")))
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    monkeypatch.setattr(X, "_ocr_image", lambda *a: (_ for _ in ()).throw(AssertionError("OCR pre odbijanja")))


def _ocr_uspeva(monkeypatch, pozivi=None):
    monkeypatch.setattr(X, "_detect_ocr_lang", lambda: "eng")
    monkeypatch.setattr(X, "_ocr_image", lambda img, lang: ((pozivi.append(img.size) if pozivi is not None else None)
                                                             or ("tekst dokumenta " * 20, 0.9)))


# ── Extractor ──────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("napravi, ime", NEPODRZANI)
def test_nepodrzan_sadrzaj_odbijen_pre_otvaranja_i_dekodiranja(monkeypatch, tmp_path, napravi, ime):
    p = tmp_path / ime
    p.write_bytes(napravi())
    _bez_otvaranja_i_dekodiranja(monkeypatch)
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)                    # kroz isti dispečer po ekstenziji kao sve rute
    assert ei.value.poruka == PORUKA_NIJE_JPEG_PNG


@pytest.mark.parametrize("napravi, ime", NEPODRZANI[:5])
def test_drugi_sloj_pillow_ne_bira_drugi_format_ni_bez_provere_potpisa(monkeypatch, tmp_path, napravi, ime):
    """Ako bi provera potpisa nestala, Image.open(formats=JPEG/PNG) i dalje ne sme da otvori/dekodira TIFF/GIF/BMP/WebP."""
    p = tmp_path / ime
    p.write_bytes(napravi())
    monkeypatch.setattr(X, "_odbij_sliku_koja_nije_jpeg_png", lambda path: None)
    otvoreni = []                       # extract_image guta izuzetke → beleži se svako otvaranje/dekodiranje, ne samo raise
    pravi_open = Image.open

    def _open(fp, mode="r", formats=None):
        img = pravi_open(fp, mode, formats)
        otvoreni.append(img.format)
        return img

    monkeypatch.setattr(Image, "open", _open)
    monkeypatch.setattr(ImageFile.ImageFile, "load",
                        lambda self: otvoreni.append("DEKODIRANJE") or (_ for _ in ()).throw(AssertionError("dekodiranje")))
    monkeypatch.setattr(X, "_ocr_image", lambda *a: otvoreni.append("OCR") or ("tekst " * 40, 0.9))
    text, is_scanned, ocr_used, _, _ = X.extract_image(p)
    assert (text, is_scanned, ocr_used) == ("", True, False)
    assert otvoreni == []


def test_tiff_cmyk_kao_jpg_bez_provere_bio_bi_dekodiran(monkeypatch, tmp_path):
    """Kontrola: bez obe zaštite (stari kod) TIFF se zaista dekodira — test iznad meri nešto stvarno."""
    p = tmp_path / "foto.jpg"
    p.write_bytes(_slika("TIFF", "CMYK", (300, 200)))
    with Image.open(p) as img:
        assert img.format == "TIFF"
        img.load()


POZITIVNI = [
    pytest.param(lambda: _slika("JPEG"), "foto.jpg", id="jpeg_jpg"),
    pytest.param(lambda: _slika("JPEG"), "foto.jpeg", id="jpeg_jpeg"),
    pytest.param(lambda: _slika("PNG"), "foto.png", id="png_png"),
    pytest.param(lambda: _slika("JPEG", "CMYK"), "cmyk.jpg", id="jpeg_cmyk"),
    pytest.param(lambda: _slika("JPEG", "L"), "siva.jpg", id="jpeg_siva"),
    pytest.param(lambda: _slika("JPEG", progressive=True), "prog.jpg", id="jpeg_progresivni_mali"),
    pytest.param(lambda: _slika("JPEG", icc_profile=b"\x00" * 128), "icc.jpg", id="jpeg_sa_icc_profilom"),
    pytest.param(lambda: _slika("PNG", "P"), "paleta.png", id="png_paleta"),
    pytest.param(lambda: _slika("PNG", "RGBA"), "alfa.png", id="png_rgba"),
    pytest.param(lambda: _slika("PNG", "I;16"), "16bit.png", id="png_16bit_siva"),
    pytest.param(lambda: _slika("PNG", "L"), "siva.png", id="png_siva"),
    pytest.param(_mpo, "telefon.jpg", id="mpo_telefon"),
    # Politika: podržan sadržaj sa drugom podržanom ekstenzijom se prihvata (namerno) — odlučuje sadržaj.
    pytest.param(lambda: _slika("JPEG"), "foto.png", id="jpeg_sadrzaj_ekstenzija_png"),
    pytest.param(lambda: _slika("PNG"), "foto.jpg", id="png_sadrzaj_ekstenzija_jpg"),
]


@pytest.mark.parametrize("napravi, ime", POZITIVNI)
def test_pravi_jpeg_png_prolaze_do_ocr(monkeypatch, tmp_path, napravi, ime):
    p = tmp_path / ime
    p.write_bytes(napravi())
    pozivi = []
    _ocr_uspeva(monkeypatch, pozivi)
    text, is_scanned, ocr_used, _, conf = X.extract(p)
    assert is_scanned is False and ocr_used is True and text and conf == 0.9
    assert pozivi == [(64, 48)]


def test_mpo_je_jpeg_i_pokriva_ga_jpeg_zastita(monkeypatch, tmp_path):
    data = _mpo()
    with Image.open(io.BytesIO(data), formats=X.FORMATI_SLIKE) as img:
        assert img.format == "MPO" and img.n_frames == 2        # stvarno MPO, otvoren JPEG fabrikom
    okvir = X._jpeg_okvir(io.BytesIO(data))
    assert okvir and (okvir["sirina"], okvir["visina"]) == (64, 48)
    monkeypatch.setattr(X, "MAX_JPEG_DEKODIRANJA_BAJTOVA", X._jpeg_procena_dekodiranja(okvir) - 1)
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    p = tmp_path / "telefon.jpg"
    p.write_bytes(data)
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract_image(p)
    assert ei.value.poruka == X.PORUKA_PREVELIK_JPEG


def test_preveliki_pravi_jpeg_i_dalje_odbija_jpeg_zastita_sa_stvarnim_pragom(monkeypatch, tmp_path):
    data = _jpeg_zaglavlje_progresivni(6000, 6000)               # 36 MP < MAX_IMAGE_PIXELS, koeficijenti ~216 MiB
    okvir = X._jpeg_okvir(io.BytesIO(data))
    assert X._jpeg_procena_dekodiranja(okvir) > X.MAX_JPEG_DEKODIRANJA_BAJTOVA
    assert 6000 * 6000 <= X.MAX_IMAGE_PIXELS
    p = tmp_path / "veliki.jpeg"
    p.write_bytes(data)
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert ei.value.poruka == X.PORUKA_PREVELIK_JPEG


def test_png_iznad_granice_piksela_odbijen_pre_dekodiranja_stvarna_granica(monkeypatch, tmp_path):
    p = tmp_path / "bomba.png"
    p.write_bytes(_png_zaglavlje(8000, 6000))                    # 48 MP > 40 MP, fajl < 100 B
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    with pytest.raises(DocumentSafetyLimitExceeded) as ei:
        X.extract(p)
    assert "8000x6000" in ei.value.reason


def test_png_tacno_na_granici_piksela_prihvacen_jedan_preko_odbijen(monkeypatch, tmp_path):
    p = tmp_path / "granica.png"
    p.write_bytes(_slika("PNG", size=(64, 48)))
    _ocr_uspeva(monkeypatch)
    monkeypatch.setattr(X, "MAX_IMAGE_PIXELS", 64 * 48)
    assert X.extract(p)[2] is True
    monkeypatch.setattr(X, "MAX_IMAGE_PIXELS", 64 * 48 - 1)
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    with pytest.raises(DocumentSafetyLimitExceeded):
        X.extract(p)


@pytest.mark.parametrize("ime, data", [
    ("ostecen.jpg", b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + os.urandom(64)),
    ("ostecen.png", b"\x89PNG\r\n\x1a\n" + os.urandom(64)),
    ("odsecen.jpg", _slika("JPEG", size=(400, 300))[:300]),
    ("odsecen.png", _slika("PNG", size=(400, 300))[:60]),
])
def test_osteceno_ili_odseceno_cist_neuspeh_bez_laznog_uspeha(monkeypatch, tmp_path, ime, data):
    p = tmp_path / ime
    p.write_bytes(data)
    _ocr_uspeva(monkeypatch)                                     # OCR bi "uspeo" kad bi bio pozvan
    text, is_scanned, ocr_used, _, _ = X.extract(p)
    assert (text, is_scanned, ocr_used) == ("", True, False)


# ── Upload u predmet (api.py::predmet_upload_auto_analyze) ───────────────────────────────────────────────────────

def _api_zahtev():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/predmeti/pred-1/upload", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


class _DosaoDoExtract(Exception):
    pass


async def _api_upload(ime: str, mime: str, data: bytes):
    import api
    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "pred-1", "naziv": "Test", "tip": "opsti"}

    async def _dozvola(user=None):
        return user

    with patch("api._require_auth", return_value=types.SimpleNamespace(id="user-1", email="a@vindex.rs")), \
         patch("api._get_supa", return_value=supa), \
         patch("api.PermissionService.require", return_value=_dozvola), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("routers.smart_intake._encrypt", return_value=b"ENC"), \
         patch("uploaded_doc.extractor.extract", side_effect=_DosaoDoExtract()) as m_extract:
        try:
            await api.predmet_upload_auto_analyze(
                "pred-1", _api_zahtev(),
                UploadFile(filename=ime, file=io.BytesIO(data), headers=Headers({"content-type": mime})),
                authorization="Bearer t")
        except (HTTPException, _DosaoDoExtract) as e:
            return e, m_extract, supa.storage.from_.return_value.upload
    raise AssertionError("ruta nije ni odbila ni stigla do extract()")


@pytest.mark.anyio
@pytest.mark.parametrize("napravi, ime, mime", [
    (lambda: _slika("TIFF", "CMYK", (300, 200)), "foto.jpg", "image/jpeg"),
    (lambda: _slika("TIFF"), "foto.png", "image/png"),
    (lambda: _slika("GIF", "P"), "foto.jpg", "image/jpeg"),
    (lambda: _slika("BMP"), "foto.png", "image/png"),
    (lambda: _slika("WEBP"), "foto.jpg", "image/jpeg"),
    (lambda: b"%PDF-1.4\n%%EOF\n", "foto.jpg", "application/pdf"),       # MIME tvrdi PDF, ekstenzija sliku
    (lambda: os.urandom(512).replace(b"\x89PNG", b"xxxx").replace(b"\xff\xd8\xff", b"xxx"), "foto.png", "image/png"),
])
async def test_api_upload_nepodrzan_sadrzaj_415_pre_cuvanja_i_obrade(napravi, ime, mime):
    e, m_extract, m_upload = await _api_upload(ime, mime, napravi())
    assert isinstance(e, HTTPException) and e.status_code == 415 and e.detail == PORUKA_NIJE_JPEG_PNG
    m_extract.assert_not_called()
    m_upload.assert_not_called()                                  # original se ne čuva


@pytest.mark.anyio
@pytest.mark.parametrize("napravi, ime, mime", [
    (lambda: _slika("JPEG"), "foto.jpg", "image/jpeg"),
    (lambda: _slika("JPEG"), "foto.jpeg", "image/jpeg"),
    (lambda: _slika("PNG"), "foto.png", "image/png"),
    (lambda: _slika("JPEG"), "foto.jpg", "image/png"),                   # MIME u sukobu sa sadržajem: odlučuje sadržaj
    (lambda: _slika("JPEG"), "foto.png", "image/png"),                   # politika: JPEG sadržaj sa .png se prihvata
    (_mpo, "telefon.jpg", "image/jpeg"),
    (lambda: b"%PDF-1.4\n%%EOF\n", "tuzba.pdf", "application/pdf"),     # PDF put netaknut
])
async def test_api_upload_pravi_sadrzaj_stize_do_extract(napravi, ime, mime):
    e, m_extract, _ = await _api_upload(ime, mime, napravi())
    assert isinstance(e, _DosaoDoExtract)
    m_extract.assert_called_once()


# ── Smart Intake upload (routers/smart_intake.py::upload_intake_documents) ───────────────────────────────────────

async def _si_upload(fajlovi):
    from routers.smart_intake import upload_intake_documents
    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
    enqueue = AsyncMock(return_value="job-1")
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/smart-intake/documents", "app": MagicMock(), "state": MagicMock()}
    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake._encrypt", return_value=b"ENC"), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=enqueue):
        res = await upload_intake_documents(
            StarletteRequest(scope=scope),
            [UploadFile(filename=i, file=io.BytesIO(d), headers=Headers({"content-type": m})) for i, d, m in fajlovi],
            {"user_id": "00000000-0000-0000-0000-000000000001", "email": "a@vindex.rs"},
        )
    return {r["filename"]: r for r in res["rezultati"]}, enqueue, supa.storage.from_.return_value.upload


@pytest.mark.anyio
async def test_smart_intake_nepodrzan_sadrzaj_odbijen_odmah_bez_posla_i_cuvanja():
    po_imenu, enqueue, upload = await _si_upload([
        ("tiff.jpg", _slika("TIFF", "CMYK", (300, 200)), "image/jpeg"),
        ("gif.png", _slika("GIF", "P"), "image/png"),
        ("webp.jpeg", _slika("WEBP"), "image/jpeg"),
        ("pdf.png", b"%PDF-1.4\n%%EOF\n", "application/pdf"),
    ])
    for r in po_imenu.values():
        assert r["ok"] is False and r["greska"] == PORUKA_NIJE_JPEG_PNG
    enqueue.assert_not_awaited()
    upload.assert_not_called()


@pytest.mark.anyio
async def test_smart_intake_pravi_jpeg_png_i_pdf_prihvaceni_u_mesovitom_batch_u():
    po_imenu, enqueue, upload = await _si_upload([
        ("a.jpg", _slika("JPEG"), "image/jpeg"),
        ("b.jpeg", _slika("JPEG"), "application/octet-stream"),
        ("c.png", _slika("PNG"), "image/png"),
        ("d.png", _slika("JPEG"), "image/png"),
        ("e.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"),
        ("tiff.jpg", _slika("TIFF"), "image/jpeg"),
    ])
    assert [n for n, r in po_imenu.items() if r["ok"]] == ["a.jpg", "b.jpeg", "c.png", "d.png", "e.pdf"]
    assert po_imenu["tiff.jpg"]["ok"] is False
    assert enqueue.await_count == 5 and upload.call_count == 5


# ── Intake worker: ako nepodržan sadržaj ipak stigne do posla — terminalno, bez ponovnih pokušaja ─────────────────

@pytest.mark.anyio
async def test_worker_nepodrzan_sadrzaj_terminalan_neuspeh_sa_tacnom_porukom(monkeypatch):
    from shared.intake_worker import IntakeWorker

    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: (_ for _ in ()).throw(AssertionError("dekodiranje")))
    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-tiff", "attempts": 0, "max_attempts": 5, "storage_path": "u/x",
           "original_filename": "foto.jpg", "mime_type": "image/jpeg", "uploaded_by": "user-1"}
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None})), \
         patch("shared.intake_worker.intake_documents.create_document", new=AsyncMock()) as m_doc, \
         patch.object(IntakeWorker, "_download_and_decrypt", new=AsyncMock(return_value=_slika("TIFF", "CMYK", (300, 200)))), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()) as m_ok, \
         patch("shared.intake_worker.intake_queue.mark_job_awaiting_review", new=AsyncMock()) as m_rev, \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as m_fail, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        assert await w._tick() is True
    m_fail.assert_awaited_once_with("job-tiff", PORUKA_NIJE_JPEG_PNG, 0, 1)    # attempts+1 == max → dead-letter
    m_ok.assert_not_awaited()
    m_rev.assert_not_awaited()
    m_doc.assert_not_awaited()                                                  # nema lažnog dokumenta/OCR uspeha


def test_dokument_ruta_ne_prima_slike():
    """routers/dokument.py nije ruta za samostalne slike (samo PDF/DOCX) — ne može da zaobiđe proveru."""
    from routers import dokument
    assert not (set(dokument._ALLOWED_SUFFIXES) & set(X.IMAGE_SUFFIXES))
