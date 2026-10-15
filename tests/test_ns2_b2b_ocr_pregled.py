# -*- coding: utf-8 -*-
"""NS2 B2b — zatvaranje nalaza recenzije B2 (kratak skeniran dokument).

F2: entitet izvučen iz OCR teksta nikad nije iznad AUTO_ACCEPT_THRESHOLD (needs_review, finalize ne upisuje rok bez
    ljudske potvrde), a kratak OCR tekst dobija vidljiv opis „mašinski pročitano sa skena“ kroz postojeći opis
    nepouzdano pročitanog dela (`ocr_failed` sa opisom).
F3: pune reči kratkog OCR teksta broje se samo iz OCR-om pročitanih strana, ne iz zadržanog digitalnog sloja.
Praznine testova: kratka fotografija niske pouzdanosti; granica „pune reči“ = tačno 3 slova/cifre.
Samo sintetički podaci."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import intake_documents  # noqa: E402
from shared.intake_worker import IntakeWorker, OCR_PLAFON_POUZDANOSTI_ENTITETA, _ocr_entiteti_na_pregled  # noqa: E402
from uploaded_doc import extractor  # noqa: E402
from uploaded_doc.extractor import _kratak_ocr_procitan, extract_image, extract_pdf  # noqa: E402

from tests.test_extractor_ocr import _build_fitz_mock, _fake_image_to_data  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── F3: reči samo iz OCR strana ─────────────────────────────────────────────────────────────────────────────────────

def _pdf_po_stranama(tmp_path, digitalne, ocr_strane, conf):
    dummy = tmp_path / "mesovit.pdf"; dummy.write_bytes(b"%PDF-1.4")
    strane = []
    for t in digitalne:
        p = MagicMock(); p.extract_text.return_value = t; strane.append(p)
    r = MagicMock(); r.pages = strane
    mock_fitz, mock_tess, mock_img, mock_pil = _build_fitz_mock(ocr_strane, conf)
    with patch("pypdf.PdfReader", return_value=r), \
         patch.dict(sys.modules, {"fitz": mock_fitz, "pytesseract": mock_tess, "PIL": mock_pil, "PIL.Image": mock_img}), \
         patch.object(extractor, "_rasterizuj_stranu", return_value=MagicMock()), \
         patch.object(extractor, "_detect_ocr_lang", return_value="srp+srp_latn+eng"), \
         patch.object(extractor, "_log_ocr_error"):
        return extract_pdf(dummy)


def test_digitalne_reci_ne_dopunjuju_kratak_ocr_sum(tmp_path):
    """Strana 1 ima kratak digitalni sloj (zadržan, OCR001), strana 2 je sken čiji OCR da jednu „punu“ reč šuma uz
    visoku pouzdanost. Pre B2b su se reči digitalne strane brojale uz OCR pouzdanost → dokument „pročitan“."""
    text, skeniran, ocr_used, strane, conf = _pdf_po_stranama(
        tmp_path, ["Prilog uz dopis broj", ""], ["", "abc ~ ."], 95.0)
    assert skeniran is True                       # sken nije pouzdano pročitan → pregled, kao pre B2
    assert strane == ["Prilog uz dopis broj", "abc ~ ."] and "Prilog uz dopis broj" in text   # digitalni tekst ostaje


def test_kratka_ocr_strana_uz_digitalnu_i_dalje_procitana(tmp_path):
    text, skeniran, ocr_used, strane, _ = _pdf_po_stranama(
        tmp_path, ["Prilog uz dopis", ""], ["", "Rešenje broj P 123/2026"], 91.0)
    assert (skeniran, ocr_used) == (False, True)
    assert strane == ["Prilog uz dopis", "Rešenje broj P 123/2026"]


# ─── Praznine testova (preživeli mutanti recenzije) ──────────────────────────────────────────────────────────────────

def _slika(tmp_path, ocr_tekst, conf):
    from PIL import Image
    put = tmp_path / "foto.png"
    Image.new("RGB", (600, 400), "white").save(put)
    tess = MagicMock(); tess.Output.DICT = "dict"
    tess.image_to_data.return_value = _fake_image_to_data(ocr_tekst, conf)
    tess.get_languages.return_value = ["eng", "srp", "srp_latn"]
    with patch.dict(sys.modules, {"pytesseract": tess}), patch.object(extractor, "_log_ocr_error"):
        return extract_image(put)


def test_kratka_fotografija_niske_pouzdanosti_ostaje_neprocitana(tmp_path):
    """Isti kratak tekst kao prihvaćena fotografija, ali pouzdanost ispod praga → nepročitano (bez teksta)."""
    assert _slika(tmp_path, "Dostavnica primljena 12.10.2026.", 70.0) == ("", True, False, None, None)
    assert _slika(tmp_path, "Dostavnica primljena 12.10.2026.", 90.0)[:3] == ("Dostavnica primljena 12.10.2026.", False, True)


@pytest.mark.parametrize("tekst,ocekivano", [
    ("Dug 120", True),          # tačno 3 slova/cifre po reči su „pune“ reči
    ("ab cd ef", False),        # 2 slova/cifre nisu
    ("ab-cd 12.", False),       # interpunkcija se ne računa
])
def test_granica_pune_reci_tri_znaka(tekst, ocekivano):
    assert _kratak_ocr_procitan(tekst, 0.95) is ocekivano


# ─── F2: OCR entiteti nikad automatski prihvaćeni ────────────────────────────────────────────────────────────────────

_ENT = [
    {"entity_type": "case_number", "value": "P 123/2026", "confidence": 0.95, "extraction_method": "regex"},
    {"entity_type": "deadline", "value": "25.11.2026", "confidence": 0.95, "extraction_method": "regex"},
    {"entity_type": "court", "value": "Osnovni sud u Nišu", "confidence": 0.5, "extraction_method": "llm"},
    {"entity_type": "amount", "value": None, "confidence": 0.0, "extraction_method": "regex"},
]


def test_plafon_je_ispod_praga_automatskog_prihvatanja():
    assert OCR_PLAFON_POUZDANOSTI_ENTITETA < intake_documents.AUTO_ACCEPT_THRESHOLD


def test_ocr_entiteti_ispod_praga_digitalni_nepromenjeni():
    ocr = _ocr_entiteti_na_pregled(_ENT, True)
    assert all(e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD for e in ocr)
    assert [e["confidence"] for e in ocr][2:] == [0.5, 0.0]        # niža pouzdanost se ne podiže
    assert [e["value"] for e in ocr] == [e["value"] for e in _ENT]   # vrednosti se ne menjaju
    assert _ocr_entiteti_na_pregled(_ENT, False) == _ENT
    assert _ENT[0]["confidence"] == 0.95                               # ulaz nije mutiran


def test_rok_iz_kratkog_ocr_teksta_ide_na_pregled():
    """Pravi regex: tekst sa pogrešno pročitanim delom i dalje daje rok 0,95; posle plafona je ispod praga, pa ga
    finalize (`_dl_dovoljan`) ne upisuje bez potvrde advokata, a GET /jobs ga prikazuje kao needs_review."""
    from shared.intake_extract import extract_deadline
    vrednost, conf = extract_deadline("Rok za zalbu ističe 25.11.2026. дапа од dostave")
    assert vrednost and conf >= intake_documents.AUTO_ACCEPT_THRESHOLD
    [rok] = _ocr_entiteti_na_pregled([{"entity_type": "deadline", "value": vrednost, "confidence": conf,
                                       "extraction_method": "regex"}], True)
    assert rok["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD


def _job():
    return {"id": "job-1", "storage_path": "u1/abc", "original_filename": "sken.pdf", "mime_type": "application/pdf",
            "attempts": 0, "max_attempts": 5}


async def _obradi(tekst, ocr_used, conf, entiteti):
    w = IntakeWorker()
    with patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None, "entities": [], "review": None})), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=(tekst, False, ocr_used, None, conf)), \
         patch("uploaded_doc.extractor.upozorenje_jezika_ocr", return_value=None), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "decision", "confidence": 0.95, "method": "heuristic"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(return_value=[dict(e) for e in entiteti])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])) as ins, \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()) as rev, \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()):
        rezultat = await w._process(_job())
    return rezultat, ins.call_args[0][1], {c[0][2]: c[0][3] for c in rev.call_args_list}


_POUZDANI = [{"entity_type": "case_number", "value": "P 123/2026", "confidence": 0.95, "extraction_method": "regex"},
             {"entity_type": "deadline", "value": "25.11.2026", "confidence": 0.95, "extraction_method": "regex"}]


@pytest.mark.anyio
async def test_worker_kratak_ocr_polja_na_pregled_i_vidljivo_upozorenje():
    rezultat, upisani, pregled = await _obradi("Rešenje broj P 123/2026 rok 25.11.2026.", True, 0.92, _POUZDANI)
    assert rezultat is True
    assert all(e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD for e in upisani)
    assert set(pregled["low_confidence_extraction"]) == {"case_number", "deadline"}
    [opis] = pregled["ocr_failed"]
    assert "mašinski pročitan sa skena" in opis and "92 %" in opis


@pytest.mark.anyio
async def test_worker_dug_ocr_polja_na_pregled_bez_opisa_kratkog_teksta():
    dug = "Rešenje broj P 123/2026. " * 6
    rezultat, upisani, pregled = await _obradi(dug, True, 0.92, _POUZDANI)
    assert all(e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD for e in upisani)
    assert "ocr_failed" not in pregled and rezultat is True


@pytest.mark.anyio
async def test_worker_digitalan_tekst_nepromenjen():
    rezultat, upisani, pregled = await _obradi("Rešenje broj P 123/2026 rok 25.11.2026.", False, None, _POUZDANI)
    assert [e["confidence"] for e in upisani] == [0.95, 0.95]
    assert pregled == {} and rezultat is False


def test_opis_kratkog_ocr_samo_uz_ocr_i_kratak_tekst():
    with patch("uploaded_doc.extractor.upozorenje_jezika_ocr", return_value=None):
        f = IntakeWorker._nepotpuno_procitano
        assert f(Path("x.jpg"), None, True, 0.92, "Primljeno 12.10.2026.")
        assert f(Path("x.jpg"), None, True, 0.92, "x" * 100)               # granica: tačno 100 znakova je kratko
        assert f(Path("x.jpg"), None, True, 0.92, "x" * 101) == []
        assert f(Path("x.jpg"), None, False, None, "Primljeno 12.10.2026.") == []
        [nisko] = f(Path("x.jpg"), None, True, 0.60, "Primljeno 12.10.2026.")   # niska pouzdanost: postojeći opis
        assert "OCR pouzdanost 60 %" in nisko


@pytest.mark.anyio
async def test_worker_segmentiran_ocr_dokument_polja_na_pregled():
    """Isti plafon u grani sa 2+ segmenta (_process_segments)."""
    from tests.test_sprint005_segmentation_worker import _PAGE_1, _PAGE_2, _PAGE_3
    pages = [_PAGE_1, _PAGE_2, _PAGE_3]
    seg_rows = [{"id": "seg-A", "segment_index": 0, "status": "pending", "attempts": 0, "max_attempts": 2},
                {"id": "seg-B", "segment_index": 1, "status": "pending", "attempts": 0, "max_attempts": 2}]
    w = IntakeWorker()
    with patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None, "entities": [], "review": None})), \
         patch.object(w, "_download_and_decrypt", new=AsyncMock(return_value=b"bytes")), \
         patch.object(w, "_extract_text", return_value=("\n\n".join(pages), False, True, pages, 0.93)), \
         patch.object(w, "_nepotpuno_procitano", return_value=[]), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_segments.create_segments", new=AsyncMock(return_value=seg_rows)), \
         patch.object(w, "_classify", new=AsyncMock(return_value={"document_type": "lawsuit", "confidence": 0.95, "method": "heuristic"})), \
         patch.object(w, "_extract_entities", new=AsyncMock(side_effect=lambda t: [dict(e) for e in _POUZDANI])), \
         patch("shared.intake_documents.create_document", new=AsyncMock(side_effect=["doc-A", "doc-B"])), \
         patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])) as ins, \
         patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()), \
         patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_processing", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_completed", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_awaiting_review", new=AsyncMock()), \
         patch("shared.intake_segments.mark_segment_failed", new=AsyncMock()):
        rezultat = await w._process(_job())
    assert ins.await_count == 2 and rezultat is True
    for c in ins.call_args_list:
        assert all(e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD for e in c[0][1])
