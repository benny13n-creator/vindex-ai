# -*- coding: utf-8 -*-
"""
N01 (2026-10-13) — AI provenance iz Smart Intake worker-a mora nositi vlasnika posla.

Produkcioni dokaz: obrada OCR prijema logovala je `[FORENSICS] provenance NIJE upisan`
sa `null value in column "user_id"` (SQLSTATE 23502). Uzrok: IntakeWorker je asyncio
task pokrenut iz startup hook-a (api.py), van svakog HTTP zahteva, pa
`shared/ai_provenance.current_context()` nema `user_id` kada AI omotač
(`shared/ai_client._capture_chat_provenance`) gradi zapis.

Ovi testovi idu kroz STVARNI patch-ovan OpenAI omotač (AsyncCompletions.create i
Completions.create) i STVARNI `log_provenance_from_wrapper`, sa lažnim Supabase
ponorom koji se ponaša kao kolona `ai_forensics.user_id UUID NOT NULL` (migracija 043).
"""
import os
import sys
import types
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import asyncio  # noqa: E402
import inspect  # noqa: E402
import logging  # noqa: E402
from contextlib import ExitStack  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from api import app  # noqa: E402,F401  -- bootstrap: _patch_openai_module()/_patch_prompt_guard()
from openai.resources.chat.completions.completions import AsyncCompletions, Completions  # noqa: E402

import shared.ai_client as ai_client  # noqa: E402
import shared.ai_provenance as ai_provenance  # noqa: E402

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_ctx():
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})
    yield
    ai_provenance._request_ctx.set({})
    ai_provenance._case_ctx.set({})


# ─── Lažni ponor: ponaša se kao ai_forensics.user_id UUID NOT NULL ─────────────

class _NotNullViolation(Exception):
    pass


class ForensicsSink:
    def __init__(self):
        self.rows: list[dict] = []
        self.rejected: list[tuple[str, dict]] = []

    def table(self, name):
        assert name == "ai_forensics"
        sink = self

        class _Chain:
            def insert(self, rec):
                self._rec = dict(rec)
                return self

            def execute(self):
                uid = self._rec.get("user_id")
                if uid is None:
                    sink.rejected.append(("23502", self._rec))
                    raise _NotNullViolation(
                        "{'code': '23502', 'message': 'null value in column \"user_id\" of relation "
                        "\"ai_forensics\" violates not-null constraint'}"
                    )
                try:
                    uuid.UUID(str(uid))
                except ValueError:
                    sink.rejected.append(("22P02", self._rec))
                    raise _NotNullViolation("{'code': '22P02', 'message': 'invalid input syntax for type uuid'}")
                sink.rows.append(self._rec)
                return MagicMock()

        return _Chain()


def _fake_response(text="AI odgovor"):
    msg = types.SimpleNamespace(content=text)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg)],
        usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="gpt-4o-mini",
    )


async def _fake_orig_acreate(self, *args, **kwargs):
    await asyncio.sleep(0.01)  # pravo prepuštanje petlje -> konkurentni poslovi se prepliću
    return _fake_response()


def _fake_orig_create(self, *args, **kwargs):
    return _fake_response()


def _marker(job_id: str, kind: str) -> str:
    return f"{kind}::{job_id}"


def _hash(job_id: str, kind: str) -> str:
    return ai_provenance.sha256_text(_marker(job_id, kind))


def _make_worker(jobs: list[dict]):
    """IntakeWorker sa STVARNIM _tick()/_process(), spoljni I/O zamenjen. Klasifikacija ide
    kroz async OpenAI omotač na event loop-u; ekstrakcija ide kroz SINHRONI omotač unutar
    asyncio.to_thread (granica niti koju kod stvarno koristi)."""
    from shared.intake_worker import IntakeWorker

    w = IntakeWorker()
    async def _classify(text):
        jid = text
        await AsyncCompletions.create(
            types.SimpleNamespace(_client=types.SimpleNamespace()),
            model="gpt-4o-mini", messages=[{"role": "user", "content": _marker(jid, "classify")}],
        )
        return {"document_type": "lawsuit", "confidence": 0.95, "method": "llm"}

    async def _extract_entities(text):
        jid = text

        def _sync_call():
            Completions.create(
                types.SimpleNamespace(_client=types.SimpleNamespace()),
                model="gpt-4o-mini", messages=[{"role": "user", "content": _marker(jid, "extract")}],
            )
        await asyncio.to_thread(_sync_call)
        return []

    queue = list(jobs)

    async def _claim(*_a, **_k):
        return queue.pop(0) if queue else None

    w._classify = _classify
    w._extract_entities = _extract_entities
    # Tekst dokumenta = id posla (storage_path = id), da bi svaki AI poziv nosio otisak SVOG
    # posla (hash, ne sadržaj) i pod konkurentnim izvršavanjem.
    w._download_and_decrypt = AsyncMock(side_effect=lambda storage_path: storage_path.encode())
    w._extract_text = lambda path: (path.read_bytes().decode(), False, False, None, None)

    stack = ExitStack()
    stack.enter_context(patch("shared.intake_worker.intake_queue.claim_next_job", new=_claim))
    stack.enter_context(patch("shared.intake_worker.intake_queue.mark_job_completed", new=AsyncMock()))
    stack.enter_context(patch("shared.intake_worker.intake_queue.mark_job_awaiting_review", new=AsyncMock()))
    stack.enter_context(patch("shared.intake_worker.intake_queue.mark_job_failed", new=AsyncMock()))
    stack.enter_context(patch("shared.intake_worker.intake_queue.record_heartbeat", new=AsyncMock()))
    stack.enter_context(patch("shared.intake_worker.intake_segments.get_segments_for_job", new=AsyncMock(return_value=[])))
    stack.enter_context(patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value={"document": None, "entities": [], "review": None})))
    stack.enter_context(patch("shared.intake_documents.create_document", new=AsyncMock(return_value="doc-1")))
    stack.enter_context(patch("shared.intake_documents.insert_entities", new=AsyncMock(return_value=[])))
    stack.enter_context(patch("shared.intake_documents.create_review_queue_entry", new=AsyncMock()))
    stack.enter_context(patch("shared.intake_documents.write_processing_outcome", new=AsyncMock()))
    stack.enter_context(patch.object(ai_client, "_orig_acreate", new=_fake_orig_acreate))
    stack.enter_context(patch.object(ai_client, "_orig_create", new=_fake_orig_create))

    return w, stack


def _job(job_id, uploaded_by, **extra):
    return {"id": job_id, "storage_path": job_id, "original_filename": "a.txt", "mime_type": "text/plain",
            "attempts": 0, "max_attempts": 5, "uploaded_by": uploaded_by, **extra}


async def _drain():
    from shared.bg import drain
    await drain(timeout=5)


def _rows_by_hash(sink):
    return {r.get("user_prompt_hash"): r for r in sink.rows}


# ─── (1) + (7) jedan posao -> red sa tačnim vlasnikom, bez 23502 ───────────────

@pytest.mark.anyio
async def test_intake_job_ai_calls_write_provenance_attributed_to_job_owner(caplog):
    sink = ForensicsSink()
    w, stack = _make_worker([_job("job-a", USER_A)])
    with stack, patch("api._get_supa", return_value=sink), caplog.at_level(logging.ERROR):
        assert await w._tick() is True
        await _drain()

    assert sink.rejected == [], f"23502/odbijen upis: {[c for c, _ in sink.rejected]}"
    rows = _rows_by_hash(sink)
    assert rows[_hash("job-a", "classify")]["user_id"] == USER_A   # async omotač, event loop
    assert rows[_hash("job-a", "extract")]["user_id"] == USER_A    # sync omotač, asyncio.to_thread
    assert "provenance NIJE upisan" not in caplog.text
    assert "23502" not in caplog.text


# ─── (2) A i B sekvencijalno i konkurentno, bez curenja ───────────────────────

@pytest.mark.anyio
async def test_sequential_jobs_of_two_owners_each_attributed_and_context_reset():
    sink = ForensicsSink()
    w, stack = _make_worker([_job("job-a", USER_A), _job("job-b", USER_B)])
    with stack, patch("api._get_supa", return_value=sink):
        await w._tick()
        assert ai_provenance.current_context().get("user_id") is None  # nema curenja posle posla
        await w._tick()
        assert ai_provenance.current_context().get("user_id") is None
        await _drain()

    rows = _rows_by_hash(sink)
    assert sink.rejected == []
    for kind in ("classify", "extract"):
        assert rows[_hash("job-a", kind)]["user_id"] == USER_A
        assert rows[_hash("job-b", kind)]["user_id"] == USER_B
    # različiti poslovi ne dele correlation_id
    assert rows[_hash("job-a", "classify")]["correlation_id"] != rows[_hash("job-b", "classify")]["correlation_id"]


@pytest.mark.anyio
async def test_concurrent_jobs_of_two_owners_do_not_bleed():
    sink = ForensicsSink()
    jobs = []
    for i in range(6):
        jobs.append(_job(f"job-a{i}", USER_A))
        jobs.append(_job(f"job-b{i}", USER_B))
    w, stack = _make_worker(jobs)
    with stack, patch("api._get_supa", return_value=sink):
        await asyncio.gather(*(w._tick() for _ in range(len(jobs))))
        await _drain()

    assert sink.rejected == []
    rows = _rows_by_hash(sink)
    assert len(rows) == 2 * len(jobs)
    for j in jobs:
        for kind in ("classify", "extract"):
            assert rows[_hash(j["id"], kind)]["user_id"] == j["uploaded_by"], (j["id"], kind)


# ─── (4) + (6) nema identiteta / falsifikovan identitet ───────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("owner", [None, "", "nije-uuid", "' OR 1=1 --"])
async def test_job_without_valid_owner_never_produces_attributed_row(owner, caplog):
    """Posle posla korisnika A dolazi posao bez validnog vlasnika: A se NE sme preneti,
    niti se izmišlja servisni korisnik. Rezultat: vidljivo odbijen upis + glasan log."""
    sink = ForensicsSink()
    w, stack = _make_worker([_job("job-a", USER_A), _job("job-x", owner)])
    with stack, patch("api._get_supa", return_value=sink), caplog.at_level(logging.ERROR):
        await w._tick()
        await w._tick()
        await _drain()

    rows = _rows_by_hash(sink)
    assert _hash("job-x", "classify") not in rows
    assert _hash("job-x", "extract") not in rows
    rejected_x = [r for code, r in sink.rejected if r.get("user_prompt_hash") in (_hash("job-x", "classify"), _hash("job-x", "extract"))]
    assert len(rejected_x) == 2 and all(r.get("user_id") is None for r in rejected_x)
    assert "nema validnog vlasnika" in caplog.text
    assert "provenance NIJE upisan" in caplog.text
    assert rows[_hash("job-a", "classify")]["user_id"] == USER_A


@pytest.mark.anyio
async def test_forged_identity_fields_on_job_and_ambient_context_are_ignored():
    """Jedini izvor je serverski `uploaded_by`. Polja koja liče na identitet (user_id,
    metadata) i ambijentalni kontekst postavljen na B ne smeju pobediti; ambijentalni
    kontekst se vraća posle posla."""
    sink = ForensicsSink()
    forged = _job("job-a", USER_A, user_id=USER_B, metadata={"user_id": USER_B})
    w, stack = _make_worker([forged])
    ai_provenance.set_request_context(user_id=USER_B, correlation_id="ambient")
    with stack, patch("api._get_supa", return_value=sink):
        await w._tick()
        await _drain()
    assert ai_provenance.current_context().get("user_id") == USER_B
    assert ai_provenance.current_context().get("correlation_id") == "ambient"

    rows = _rows_by_hash(sink)
    assert rows[_hash("job-a", "classify")]["user_id"] == USER_A
    assert rows[_hash("job-a", "extract")]["user_id"] == USER_A
    assert all(r["user_id"] != USER_B for r in sink.rows)


@pytest.mark.anyio
async def test_failed_job_still_resets_context():
    """Posao koji baci izuzetak u obradi ne sme ostaviti identitet za sledeći posao."""
    sink = ForensicsSink()
    w, stack = _make_worker([_job("job-a", USER_A), _job("job-x", None)])
    calls = {"n": 0}
    with stack, patch("api._get_supa", return_value=sink):
        orig = w._process

        async def _boom_first(job):
            calls["n"] += 1
            if calls["n"] == 1:
                assert ai_provenance.current_context().get("user_id") == USER_A
                raise RuntimeError("OCR pukao")
            return await orig(job)
        w._process = _boom_first
        await w._tick()
        assert ai_provenance.current_context().get("user_id") is None
        await w._tick()
        await _drain()
    assert all(r["user_id"] != USER_A for r in sink.rows)


# ─── (3) granice niti / falsifikovanje alternativnih hipoteza ─────────────────

@pytest.mark.anyio
async def test_hypothesis_thread_boundary_asyncio_to_thread_preserves_context():
    """FALSIFIKUJE 'izgubljeno na granici niti': asyncio.to_thread kopira contextvars."""
    with ai_provenance.scoped_request_context(user_id=USER_A):
        seen = await asyncio.to_thread(lambda: ai_provenance.current_context().get("user_id"))
    assert seen == USER_A


@pytest.mark.anyio
async def test_hypothesis_wrapper_and_insert_carry_user_id_when_context_present():
    """FALSIFIKUJE 'omotač čita pogrešno' i 'izgubljeno pre upisa': sa postavljenim
    kontekstom, isti omotač + isti log_provenance_from_wrapper upisuju user_id."""
    sink = ForensicsSink()
    with patch.object(ai_client, "_orig_acreate", new=_fake_orig_acreate), \
         patch("api._get_supa", return_value=sink):
        with ai_provenance.scoped_request_context(user_id=USER_A):
            await AsyncCompletions.create(
                types.SimpleNamespace(_client=types.SimpleNamespace()),
                model="gpt-4o-mini", messages=[{"role": "user", "content": "h"}],
            )
        await _drain()
    assert [r["user_id"] for r in sink.rows] == [USER_A]


@pytest.mark.anyio
async def test_hypothesis_background_task_without_identity_reproduces_23502(caplog):
    """DOKAZUJE 'nikad inicijalizovano': AI poziv iz pozadinskog taska (kao worker iz
    startup hook-a) bez ikakvog konteksta -> tačno 23502 oblik iz produkcije."""
    sink = ForensicsSink()

    async def _bg():
        await AsyncCompletions.create(
            types.SimpleNamespace(_client=types.SimpleNamespace()),
            model="gpt-4o-mini", messages=[{"role": "user", "content": "h"}],
        )

    with patch.object(ai_client, "_orig_acreate", new=_fake_orig_acreate), \
         patch("api._get_supa", return_value=sink), caplog.at_level(logging.ERROR):
        await asyncio.create_task(_bg())
        await _drain()
    assert sink.rows == []
    assert [c for c, _ in sink.rejected] == ["23502"]
    assert "provenance NIJE upisan" in caplog.text and "23502" in caplog.text


def test_scoped_request_context_restores_previous_value():
    ai_provenance.set_request_context(user_id=USER_B, correlation_id="c-b")
    with ai_provenance.scoped_request_context(user_id=USER_A) as cid:
        assert ai_provenance.current_context()["user_id"] == USER_A
        assert cid != "c-b"
    assert ai_provenance.current_context()["user_id"] == USER_B
    with ai_provenance.scoped_request_context(user_id=None):
        assert ai_provenance.current_context()["user_id"] is None  # izričito None, ne nasleđeno
    assert ai_provenance.current_context()["user_id"] == USER_B


# ─── (6) upload: vlasnik posla dolazi iz JWT-a, ne iz klijentskog tela ────────

def test_upload_endpoint_takes_no_client_identity_and_enqueues_authenticated_user():
    from routers.smart_intake import upload_intake_documents
    params = set(inspect.signature(upload_intake_documents).parameters)
    assert params == {"request", "files", "user"}
    src = inspect.getsource(upload_intake_documents)
    assert 'uploaded_by=user["user_id"]' in src
