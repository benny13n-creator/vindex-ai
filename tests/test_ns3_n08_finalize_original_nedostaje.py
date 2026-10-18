# -*- coding: utf-8 -*-
"""NS3-N08 — finalize kada originalni fajl posla nije dostupan (storage/dekripcija pada).

Ugovor (OCR001 + Program Intake Sprint 006): predmet ostaje, ali odgovor NE SME da tvrdi prikačivanje —
`ok` je True samo za potvrđeno potpuno prikačivanje, a `dokumenti` kaže ishod po dokumentu. Do sada nijedan
test nije izvršavao baš ovu granu (`_download_and_decrypt` pada unutar finalize-a, fail-soft na nivou posla).

Stvarni `finalize_intake_job`; baza i spoljne zavisnosti iz harness-a `tests/test_n03_deadline_gates.py`."""
import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

from routers.smart_intake import FinalizeReq
from tests.test_n03_deadline_gates import _UID, _dok, _ent, _req, _supa


async def _finalize(supa, documents, preuzimanje):
    """Kao `test_n03_deadline_gates._finalize`, ali `_download_and_decrypt` je zadat (tamo je uvek uspeh)."""
    from routers.smart_intake import finalize_intake_job
    zakrpe = (
        patch("routers.smart_intake._get_supa", return_value=supa),
        patch("shared.intake_segments._get_supa", return_value=supa),
        patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=documents)),
        patch("shared.intake_worker.worker._download_and_decrypt", new=preuzimanje),
        patch("uploaded_doc.extractor.extract", return_value=("tekst", False, False, None, None)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-001"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2025-03-27T00:00:00Z"),
        patch("routers.smart_intake.intake_queue.claim_finalize",
              new=AsyncMock(return_value={"id": "job-1", "finalizing_at": "2025-03-27T00:00:00+00:00"})),
        patch("services.event_bus.emit_durable", new=AsyncMock()),
        patch("shared.audit_immutable.log_action", new=AsyncMock(return_value=None)),
    )
    with contextlib.ExitStack() as stek:
        for z in zakrpe:
            stek.enter_context(z)
        return await finalize_intake_job("job-1", _req(), FinalizeReq(), {"user_id": _UID, "email": "a@primer.test"})


def _pokreni(preuzimanje):
    supa = _supa()
    dokumenti_upisani = []
    _orig = supa.table.side_effect

    def _table(ime):
        t = _orig(ime)
        if ime == "predmet_dokumenti":
            _ins = t.insert

            def _belezi(red):
                dokumenti_upisani.append(red)
                return _ins(red)
            t.insert = _belezi
        return t
    supa.table.side_effect = _table
    rez = asyncio.run(_finalize(supa, [_dok([_ent("deadline", None, 0.0)], tip="lawsuit")], preuzimanje))
    return rez, dokumenti_upisani


def test_original_nedostupan_nije_prikacen_dokument():
    rez, upisani = _pokreni(AsyncMock(side_effect=FileNotFoundError("storage: object not found")))
    assert rez["ok"] is False, "odgovor tvrdi prikačivanje bez originala"
    assert rez["dokument_povezan"] is False and rez["dokumenata_povezano"] == 0
    assert [d["povezan"] for d in rez["dokumenti"]] == [False]
    assert upisani == [], "dokument bez teksta upisan u predmet"
    assert rez["predmet_id"] == "pred-001"                                  # predmet ostaje (postojeći ugovor)


def test_dekripcija_pada_isto():
    rez, upisani = _pokreni(AsyncMock(side_effect=ValueError("InvalidTag")))
    assert rez["ok"] is False and rez["dokumenata_povezano"] == 0 and upisani == []


def test_kontrola_original_dostupan_dokument_prikacen():
    rez, upisani = _pokreni(AsyncMock(return_value=b"raw"))
    assert rez["ok"] is True and rez["dokument_povezan"] is True and rez["dokumenata_povezano"] == 1
    assert len(upisani) == 1
