# -*- coding: utf-8 -*-
"""
Sprint 6 — adversarial verification of AI subject context isolation.

ARCHITECTURAL FINDING THIS FILE RESTS ON
The canonical mechanism already exists: shared/ai_provenance.py holds two
contextvars (_request_ctx for user_id/correlation_id, _case_ctx for
predmet_id/document_id), set via set_request_context() and the case_context()
context manager. Sprint 6 said not to build a second mechanism if one exists.
One does, and this is it.

The binding is therefore DYNAMIC, not lexical. The provider call sits inside a
_pozovi_* helper in one module while the `with case_context(...)` sits at the
endpoint in another, so the call is never lexically inside the block. A static
AST metric measuring containment returns 0/83 and is simply the wrong instrument
for this architecture. Only runtime observation counts, which is what these
tests do: they drive the real mechanism and read what the provenance writer
would actually record.

THE INVARIANT UNDER TEST
A request for predmet A must never produce a record linked to predmet B.
A request from user A must never produce a record linked to user B.
Context from request A must never leak into request B.
"""
import asyncio
import contextvars
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _subject():
    """What the provenance writer would record for the current context."""
    from shared.ai_provenance import current_context
    ctx = current_context()
    return (ctx.get("user_id"), ctx.get("predmet_id"))


# -- A/B/C: the basic bindings --------------------------------------------

def test_subject_is_exactly_what_the_endpoint_declared():
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        assert _subject() == ("user-A", "predmet-A")


def test_same_user_different_predmet_does_not_bleed():
    """User A opens predmet A, then predmet B. The second must not inherit the
    first's subject."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        assert _subject() == ("user-A", "predmet-A")
    with case_context(predmet_id="predmet-B", module_name="m", operation_name="o"):
        assert _subject() == ("user-A", "predmet-B")


def test_the_case_subject_is_released_when_the_block_exits():
    """Otherwise a later AI call in the same request, one with no case at all,
    would be filed against whatever case happened to be open before it."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        pass
    assert _subject()[1] is None, "predmet_id must not survive its own block"


# -- D: concurrency, the one that actually matters ------------------------

@pytest.mark.anyio
async def test_two_concurrent_requests_never_see_each_others_subject():
    """The security invariant. Two lawyers, two firms, two cases, interleaved on
    one event loop in a single-process deployment."""
    from shared.ai_provenance import case_context, set_request_context

    seen = {"A": [], "B": []}

    async def _request(tag, user, predmet, delay):
        set_request_context(user_id=user)
        with case_context(predmet_id=predmet, module_name="m", operation_name="o"):
            for _ in range(5):
                await asyncio.sleep(delay)
                seen[tag].append(_subject())

    await asyncio.gather(
        _request("A", "user-A", "predmet-A", 0.001),
        _request("B", "user-B", "predmet-B", 0.0015),
    )

    assert set(seen["A"]) == {("user-A", "predmet-A")}, seen["A"]
    assert set(seen["B"]) == {("user-B", "predmet-B")}, seen["B"]


@pytest.mark.anyio
async def test_a_task_started_inside_a_case_block_keeps_that_subject():
    """asyncio.create_task copies the context at creation time, so a background
    continuation must carry the subject it was started under, not whatever is
    current when it eventually runs."""
    from shared.ai_provenance import case_context, set_request_context

    captured = []

    async def _later():
        await asyncio.sleep(0.01)
        captured.append(_subject())

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        t = asyncio.create_task(_later())

    set_request_context(user_id="user-B")
    with case_context(predmet_id="predmet-B", module_name="m", operation_name="o"):
        await t

    assert captured == [("user-A", "predmet-A")], (
        f"a task must keep the subject it was created under, got {captured}"
    )


# -- E: the thread boundary Sprint 2 fixed --------------------------------

def test_subject_crosses_a_thread_boundary_only_with_copy_context():
    """The RAG path's failure mode, established rather than assumed: a raw
    executor submit loses the subject entirely, and copy_context carries it.
    app/services/retrieve.py was fixed in Sprint 2 for exactly this."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
        with ThreadPoolExecutor(max_workers=2) as ex:
            raw = ex.submit(_subject).result()
            copied = ex.submit(contextvars.copy_context().run, _subject).result()

    assert raw == (None, None), "a raw submit loses the subject; this is the defect"
    assert copied == ("user-A", "predmet-A"), "copy_context must carry it"


def test_the_rag_path_uses_copy_context_for_its_provider_calls():
    """No regression on the Sprint 2 fix: the four RAG submits that make
    provider calls must still carry a copied context."""
    import inspect
    import app.services.retrieve as r

    src = inspect.getsource(r)
    for fn in ("_decomp_fn", "_prosiri_query_gpt_wrapper", "_semanticka_pretraga"):
        assert "submit(contextvars.copy_context().run, " + fn in src, fn


# -- G/H: absence must be recorded as absence, never invented -------------

def test_a_call_with_no_case_records_no_case():
    """The mission's rule: if predmet_id cannot be proven, the system must not
    invent one. An AI call outside any case must record predmet_id as absent."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(module_name="m", operation_name="o"):
        user_id, predmet_id = _subject()
    assert user_id == "user-A"
    assert predmet_id is None, "no case means no case: not a guess, not a leftover"


def test_an_explicit_none_predmet_does_not_inherit_an_outer_one():
    """Nested blocks: an inner operation that genuinely has no case must not
    silently be filed against the outer one."""
    from shared.ai_provenance import case_context, set_request_context

    set_request_context(user_id="user-A")
    with case_context(predmet_id="predmet-A", module_name="m", operation_name="outer"):
        with case_context(module_name="m", operation_name="inner"):
            inner = _subject()
    assert inner[1] is None, (
        "an inner block with no predmet_id must not inherit the outer one, got "
        + repr(inner)
    )


# -- L: the subject must survive the failure path -------------------------

@pytest.mark.anyio
async def test_the_subject_survives_a_provider_failure():
    """A failed AI call must leave a record carrying the SAME subject plus the
    error state. A provenance trail that only records successes cannot answer
    what happened when something went wrong."""
    from unittest.mock import MagicMock, patch

    import shared.ai_client as ac
    from shared import bg
    from shared.ai_provenance import case_context, set_request_context

    bg._BG.clear()
    seen = {}

    async def _capture(**kwargs):
        seen.update(kwargs)

    set_request_context(user_id="user-A")
    with patch("security.ai_forensics.log_provenance_from_wrapper", _capture):
        with case_context(predmet_id="predmet-A", module_name="m", operation_name="o"):
            ac._capture_chat_provenance(
                MagicMock(),
                {"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]},
                None, 11, error=RuntimeError("provider down"),
            )
        await bg.drain(timeout=2.0)

    assert seen.get("status") == "error"
    assert seen.get("user_id") == "user-A"
    assert seen.get("predmet_id") == "predmet-A", (
        "the failure record must carry the same subject as a success would"
    )
