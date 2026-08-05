# -*- coding: utf-8 -*-
"""
Program Intake Sprint 002 (2026-08-05) — regression tests for Pipeline A
(api.py::predmet_upload_auto_analyze) orphan-blob compensating cleanup.

Sprint 001 added best-effort original-file preservation to Storage. Sprint
002 Fork A found this created a WIDER orphan-blob exposure than the
already-known INTAKE-002: 5 distinct downstream raise sites (safety-limit,
unreadable-scan, empty-text, Pinecone failure, Sentinel hard-fail) could all
leave the just-uploaded encrypted blob permanently orphaned in
intake-dokumenti, with zero tracking infrastructure of any kind (worse than
Pipeline B's INTAKE-002, which at least has a job row).

Fix: the entire OCR->Pinecone->DB stretch is wrapped in a try/except that,
on ANY exception, best-effort deletes the just-uploaded blob before
re-raising the SAME exception unchanged (same status code, same detail) —
compensating cleanup, not a different response to the client.

Mirrors tests/test_intake_original_file_storage.py's mocking pattern.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import HTTPException, UploadFile

import api
from uploaded_doc.extractor import DocumentSafetyLimitExceeded


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user(uid: str = "user-0000-0000-0000-000000000001", email: str = "advokat@vindex.rs"):
    return types.SimpleNamespace(id=uid, email=email)


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "insert", "execute", "single", "order", "limit", "is_", "gte", "or_"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock()
    r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-1/upload", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _upload_file(filename: str, content_type: str, content: bytes = b"fake bytes for test") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers=Headers({"content-type": content_type}))


async def _fake_permission_dependency(user=None):
    return user


def _supa_upload_succeeds(predmet_id: str = "pred-1", insert_fails: bool = False):
    """predmeti ownership check succeeds; predmet_dokumenti SELECT (redni_broj
    lookup) succeeds empty; predmet_dokumenti INSERT either succeeds or
    always raises (Sentinel hard-fail scenario); storage.from_(...).upload
    succeeds, storage.from_(...).remove is a plain trackable MagicMock."""
    def _table(name):
        if name == "predmeti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.single.return_value = c
            r = MagicMock(); r.data = {"id": predmet_id, "naziv": "Test predmet", "tip": "opsti"}
            c.execute = MagicMock(return_value=r)
            return c
        if name == "predmet_dokumenti":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.order.return_value = c
            c.limit.return_value = c
            sel_r = MagicMock(); sel_r.data = []
            c.execute = MagicMock(return_value=sel_r)
            if insert_fails:
                insert_chain = MagicMock()
                insert_chain.execute = MagicMock(side_effect=Exception("predmet_dokumenti insert down"))
                c.insert = MagicMock(return_value=insert_chain)
            else:
                def _capture_insert(payload):
                    ic = MagicMock()
                    r = MagicMock(); r.data = [dict(payload, id="dok-1")]
                    ic.execute = MagicMock(return_value=r)
                    return ic
                c.insert = MagicMock(side_effect=_capture_insert)
            return c
        return _chain([])

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)
    supa.storage.from_.return_value.upload.return_value = None
    supa.storage.from_.return_value.remove = MagicMock(return_value=None)
    return supa


def _base_patches(supa, extract_return=None, extract_side_effect=None, ingest_side_effect=None):
    patches = [
        patch("api._require_auth", return_value=_fake_user("user-42")),
        patch("api._get_supa", return_value=supa),
        patch("api.PermissionService.require", return_value=_fake_permission_dependency),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED-BLOB"),
    ]
    if extract_side_effect is not None:
        patches.append(patch("uploaded_doc.extractor.extract", side_effect=extract_side_effect))
    else:
        patches.append(patch("uploaded_doc.extractor.extract", return_value=extract_return))
    patches.append(patch("uploaded_doc.chunker.chunk_document", return_value=types.SimpleNamespace(total_chunks=1)))
    if ingest_side_effect is not None:
        patches.append(patch("uploaded_doc.ingest.ingest_session", side_effect=ingest_side_effect))
    else:
        patches.append(patch("uploaded_doc.ingest.ingest_session", return_value=1))
    return patches


async def _run_with_patches(patches, **upload_kwargs):
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(),
            _upload_file(upload_kwargs.get("filename", "tuzba.pdf"), "application/pdf",
                         content=upload_kwargs.get("content", b"original raw pdf bytes")),
            authorization="Bearer test-token",
        )


@pytest.mark.anyio
async def test_pinecone_failure_after_successful_storage_write_deletes_orphan_blob():
    supa = _supa_upload_succeeds()
    patches = _base_patches(
        supa, extract_return=("Sadržaj dokumenta.", False, False),
        ingest_side_effect=Exception("pinecone totally unreachable"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _run_with_patches(patches)

    assert exc_info.value.status_code == 500
    supa.storage.from_.return_value.upload.assert_called_once()
    supa.storage.from_.return_value.remove.assert_called_once()
    removed_keys = supa.storage.from_.return_value.remove.call_args[0][0]
    assert len(removed_keys) == 1
    assert removed_keys[0].startswith("user-42/pred-1/")


@pytest.mark.anyio
async def test_predmet_dokumenti_insert_failure_deletes_orphan_blob():
    """The Project Sentinel hard-fail path: Pinecone succeeds, DB insert
    fails entirely -- this is the exact defect shape Sprint 002 Fork A §A3
    already knew about (ghost vector, deferred INTAKE-001-shape), but the
    ORIGINAL FILE blob is a separate artifact this fix DOES clean up."""
    supa = _supa_upload_succeeds(insert_fails=True)
    patches = _base_patches(supa, extract_return=("Sadržaj dokumenta.", False, False))

    with pytest.raises(HTTPException) as exc_info:
        await _run_with_patches(patches)

    assert exc_info.value.status_code == 500
    supa.storage.from_.return_value.remove.assert_called_once()


@pytest.mark.anyio
async def test_safety_limit_exceeded_deletes_orphan_blob():
    supa = _supa_upload_succeeds()
    patches = _base_patches(supa, extract_side_effect=DocumentSafetyLimitExceeded("zip bomb ratio"))

    with pytest.raises(HTTPException) as exc_info:
        await _run_with_patches(patches, filename="tuzba.docx")

    assert exc_info.value.status_code == 413
    supa.storage.from_.return_value.remove.assert_called_once()


@pytest.mark.anyio
async def test_empty_text_deletes_orphan_blob():
    supa = _supa_upload_succeeds()
    patches = _base_patches(supa, extract_return=("   ", False, False))

    with pytest.raises(HTTPException) as exc_info:
        await _run_with_patches(patches)

    assert exc_info.value.status_code == 422
    supa.storage.from_.return_value.remove.assert_called_once()


@pytest.mark.anyio
async def test_successful_upload_never_triggers_cleanup():
    """The happy path must never call remove() -- the file is meant to
    stay, that's the whole point of Sprint 001's fix."""
    supa = _supa_upload_succeeds()
    patches = _base_patches(supa, extract_return=("Sadržaj dokumenta.", False, False))
    patches += [
        patch("openai.OpenAI", return_value=MagicMock(chat=MagicMock(completions=MagicMock(
            create=MagicMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))]))
        )))),
        patch("api.UsageService.consume", new=AsyncMock()),
    ]

    await _run_with_patches(patches)

    supa.storage.from_.return_value.remove.assert_not_called()


@pytest.mark.anyio
async def test_cleanup_failure_does_not_mask_the_original_error():
    """If the compensating delete itself throws, the client must still see
    the SAME original error (status code and detail unchanged) -- cleanup
    failure is logged, never surfaces as a different or crashing response."""
    supa = _supa_upload_succeeds()
    supa.storage.from_.return_value.remove = MagicMock(side_effect=Exception("bucket unreachable"))
    patches = _base_patches(
        supa, extract_return=("Sadržaj dokumenta.", False, False),
        ingest_side_effect=Exception("pinecone totally unreachable"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _run_with_patches(patches)

    assert exc_info.value.status_code == 500
    assert "Greška pri obradi dokumenta" in exc_info.value.detail
