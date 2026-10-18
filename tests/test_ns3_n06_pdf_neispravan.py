# -*- coding: utf-8 -*-
"""NS3-N06 — fajl sa `.pdf` ekstenzijom koji pypdf ne može da pročita je deterministički odbijen, ne „privremena greška“.

Ugovor već postoji (NS3-A / NS2b): sadržaj koji nije PDF → `DocumentSafetyLimitExceeded(poruka=PORUKA_NIJE_PDF)`,
a Smart Intake worker takav posao odmah završava kao trajno neuspešan (bez ponovnih pokušaja), sa porukom za
advokata. Pre ispravke je to važilo samo kad fajl prođe pypdf, a MuPDF ga ne čita kao PDF. Kad pypdf odmah padne
(HTML/tekst preimenovan u .pdf, odsečen ili oštećen PDF), izuzetak je išao generičkim putem: posao se ponavljao do
`max_attempts` (eksponencijalni backoff, ~7,5 min „u obradi“) i završavao sa sirovim tekstom pypdf-a
(„Stream has ended unexpectedly“). Isti ulaz uvek daje isti pad — ponavljanje ništa ne menja.

Stvarni `uploaded_doc.extractor.extract` i stvarni `IntakeWorker._tick`; sinteticki fajlovi."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uploaded_doc.extractor import PORUKA_NIJE_PDF, DocumentSafetyLimitExceeded, extract

NEISPRAVNI = {
    "html_kao_pdf": b"<html><body>nije pdf</body></html>",
    "samo_zaglavlje": b"%PDF-1.4\n%%EOF",
    "odseceno": b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
    "tekst": "Ugovor o zakupu — tekst, ne PDF".encode("utf-8"),
}


def _digitalni_pdf() -> bytes:
    fitz = pytest.importorskip("fitz")
    d = fitz.open()
    for i in range(2):
        d.new_page().insert_text((72, 72), f"Tuzba radi naknade stete, strana {i + 1}. " * 4)
    return d.tobytes()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize("ime", list(NEISPRAVNI))
def test_neispravan_pdf_je_deterministicko_odbijanje_sa_porukom(tmp_path, ime):
    f = tmp_path / f"{ime}.pdf"
    f.write_bytes(NEISPRAVNI[ime])
    with pytest.raises(DocumentSafetyLimitExceeded) as e:
        extract(f)
    assert e.value.poruka == PORUKA_NIJE_PDF


def test_ispravan_digitalni_pdf_i_dalje_daje_tekst(tmp_path):
    f = tmp_path / "ok.pdf"
    f.write_bytes(_digitalni_pdf())
    text, is_scanned, ocr_used, pages, _ = extract(f)
    assert not is_scanned and not ocr_used and len(pages) == 2 and "Tuzba radi naknade stete" in text


async def _tick(sadrzaj, ime="tuzba.pdf"):
    from shared.intake_worker import IntakeWorker
    w = IntakeWorker(worker_id="test-worker")
    job = {"id": "job-pdf", "attempts": 0, "max_attempts": 5, "storage_path": "u/x",
           "original_filename": ime, "mime_type": "application/pdf", "uploaded_by": "user-1"}
    with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
         patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
         patch("shared.intake_worker.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None})), \
         patch("shared.intake_worker.intake_documents.create_document", new=AsyncMock()) as m_doc, \
         patch.object(IntakeWorker, "_download_and_decrypt", new=AsyncMock(return_value=sadrzaj)), \
         patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()) as m_ok, \
         patch("shared.intake_worker.intake_queue.mark_job_awaiting_review", new=AsyncMock()) as m_rev, \
         patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as m_fail, \
         patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
        assert await w._tick() is True
    return m_fail, m_ok, m_rev, m_doc


@pytest.mark.anyio
@pytest.mark.parametrize("ime", list(NEISPRAVNI))
async def test_worker_neispravan_pdf_terminalno_odmah_bez_ponavljanja(ime):
    m_fail, m_ok, m_rev, m_doc = await _tick(NEISPRAVNI[ime])
    m_fail.assert_awaited_once_with("job-pdf", PORUKA_NIJE_PDF, 0, 1)    # attempts+1 == max → dead-letter odmah
    m_ok.assert_not_awaited()
    m_rev.assert_not_awaited()
    m_doc.assert_not_awaited()                                           # nema lažnog dokumenta ni „OCR uspeha“


@pytest.mark.anyio
async def test_worker_privremena_greska_i_dalje_ide_na_ponavljanje():
    """Kontrola: pad PRE ekstrakcije (npr. preuzimanje iz storage-a) ostaje privremen — retry put nepromenjen."""
    from shared.intake_worker import IntakeWorker
    with patch.object(IntakeWorker, "_download_and_decrypt", new=AsyncMock(side_effect=ConnectionError("storage 503"))):
        w = IntakeWorker(worker_id="test-worker")
        job = {"id": "job-x", "attempts": 1, "max_attempts": 5, "storage_path": "u/x",
               "original_filename": "tuzba.pdf", "mime_type": "application/pdf", "uploaded_by": "user-1"}
        with patch("shared.intake_worker.intake_queue.claim_next_job", new=AsyncMock(return_value=job)), \
             patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])), \
             patch("shared.intake_worker.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None})), \
             patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()) as m_fail, \
             patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()):
            await w._tick()
    m_fail.assert_awaited_once_with("job-x", "storage 503", 1, 5)
