# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 002 (2026-08-06) — Ownership & IDOR fixes.

Regression tests for 4 confirmed, code-proven ownership bypasses found by the
API Penetration Auditor fork (routers N-Z + api.py sweep):

1. smart_intake.py POST /entities/{entity_id}/correct — no ownership check at all;
   any authenticated user could correct another user's extracted entity.
2. api.py POST /predmeti/{predmet_id}/confirm-links — klijent_ids from the request
   body were linked to a predmet without verifying they belong to the caller, then
   read back with no user_id filter in get_predmet — a two-step cross-tenant PII leak.
3. zadaci.py DELETE /{zadatak_id} — the "admin" branch deleted by primary key alone,
   with no kancelarija_id scoping; any self-service firm admin could delete any
   other firm's task.
4. workflow.py POST /pokreni — template_id was fetched with no visibility filter,
   letting any firm read another firm's private workflow template content.

All tests run without live services — Supabase is fully mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-za-testove-128bit")

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_user(uid="00000000-0000-0000-0000-000000000001"):
    return {"user_id": uid, "email": "advokat@vindex.rs", "role": "advokat"}


def _fake_request(path="/api/x"):
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Fix #1: smart_intake.py correct_entity ownership check ──────────────────


@pytest.mark.anyio
async def test_correct_entity_rejects_foreign_entity():
    """User A must not be able to correct an entity belonging to User B's intake job."""
    from routers.smart_intake import correct_entity
    from fastapi import HTTPException

    def _table(name):
        t = MagicMock()
        if name == "extracted_entities":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "ent-1", "document_id": "doc-1",
            }
        elif name == "intake_documents":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "doc-1", "intake_job_id": "job-1",
            }
        elif name == "intake_jobs":
            # job-1 belongs to a DIFFERENT user -- the ownership-scoped query finds nothing.
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.smart_intake._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await correct_entity(
                "ent-1", _fake_request("/api/smart-intake/entities/ent-1/correct"),
                corrected_value="15.12.2026", reason=None, error_source=None,
                user=_fake_user(),
            )
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_correct_entity_succeeds_for_owner():
    """The legitimate owner of the underlying intake job can still correct their own entity."""
    from routers.smart_intake import correct_entity

    def _table(name):
        t = MagicMock()
        if name == "extracted_entities":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "ent-1", "document_id": "doc-1",
            }
        elif name == "intake_documents":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "doc-1", "intake_job_id": "job-1",
            }
        elif name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "job-1"}
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    fake_result = {"entity_id": "ent-1", "entity_type": "datum_rocista", "corrected_value": "15.12.2026"}
    async def _fake_correct(*a, **kw):
        return fake_result

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake.intake_documents.correct_entity", side_effect=_fake_correct) as mocked_correct, \
         patch("shared.audit_immutable.log_action", return_value=None):
        result = await correct_entity(
            "ent-1", _fake_request("/api/smart-intake/entities/ent-1/correct"),
            corrected_value="15.12.2026", reason=None, error_source=None,
            user=_fake_user(),
        )
    mocked_correct.assert_called_once()
    assert result == fake_result


# ─── Fix #2: api.py confirm-links klijent ownership check ────────────────────


@pytest.mark.anyio
async def test_confirm_links_rejects_foreign_klijent_id():
    """A klijent_id the caller does not own must be silently skipped, not linked."""
    from api import ConfirmLinksReq, predmet_confirm_links

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": "pred-001"}
        elif name == "klijenti":
            # Ownership-check query finds NONE of the requested ids -- both are foreign.
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
        elif name == "predmet_klijenti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            def _insert(payload):
                insert_calls.append(payload)
                i = MagicMock()
                i.execute.return_value.data = [payload]
                return i
            t.insert.side_effect = _insert
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    req = ConfirmLinksReq(klijent_ids=["kl-foreign"])

    with patch("api._get_supa", return_value=mock_supa), patch("api._audit", return_value=None):
        result = await predmet_confirm_links("pred-001", req, _fake_request("/api/predmeti/pred-001/confirm-links"), _fake_user())

    assert insert_calls == [], "a klijent_id not owned by the caller must never be linked"
    assert result["linked_klijenti"] == []


@pytest.mark.anyio
async def test_confirm_links_links_owned_klijent_id():
    """A klijent_id the caller genuinely owns must still link successfully (no regression)."""
    from api import ConfirmLinksReq, predmet_confirm_links

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": "pred-001"}
        elif name == "klijenti":
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [{"id": "kl-own"}]
        elif name == "predmet_klijenti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            def _insert(payload):
                insert_calls.append(payload)
                i = MagicMock()
                i.execute.return_value.data = [payload]
                return i
            t.insert.side_effect = _insert
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    req = ConfirmLinksReq(klijent_ids=["kl-own"])

    with patch("api._get_supa", return_value=mock_supa), patch("api._audit", return_value=None):
        result = await predmet_confirm_links("pred-001", req, _fake_request("/api/predmeti/pred-001/confirm-links"), _fake_user())

    assert insert_calls and insert_calls[0]["klijent_id"] == "kl-own"
    assert result["linked_klijenti"] == ["kl-own"]


# ─── Fix #3: zadaci.py obrisi_zadatak admin-branch kancelarija scoping ────────


@pytest.mark.anyio
async def test_obrisi_zadatak_admin_cannot_delete_foreign_firm_task():
    """A self-service firm admin must not be able to delete a task belonging to a different firm."""
    from routers.zadaci import obrisi_zadatak
    from fastapi import HTTPException

    delete_filters = []

    def _table(name):
        t = MagicMock()
        if name == "kancelarije":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "kanc-attacker"}
        elif name == "zadaci":
            d = MagicMock()

            def _eq(col, val):
                delete_filters.append((col, val))
                nxt = MagicMock()
                nxt.eq.side_effect = _eq
                nxt.execute.return_value.data = []  # no row matches this firm -> nothing deleted
                return nxt
            d.eq.side_effect = _eq
            t.delete.return_value = d
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.zadaci._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await obrisi_zadatak("zad-victim-firm", _fake_request("/api/zadaci/zad-victim-firm"), user=_fake_user())

    assert exc.value.status_code == 404
    assert ("kancelarija_id", "kanc-attacker") in delete_filters, (
        "the admin-branch delete must be scoped to the admin's OWN kancelarija_id, "
        "not just the primary key"
    )


@pytest.mark.anyio
async def test_obrisi_zadatak_admin_can_delete_own_firm_task():
    """No regression: a real firm admin can still delete a task inside their own firm."""
    from routers.zadaci import obrisi_zadatak

    def _table(name):
        t = MagicMock()
        if name == "kancelarije":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "kanc-own"}
        elif name == "zadaci":
            t.delete.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "zad-own-firm"}]
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.zadaci._get_supa", return_value=mock_supa):
        result = await obrisi_zadatak("zad-own-firm", _fake_request("/api/zadaci/zad-own-firm"), user=_fake_user())

    assert result == {"ok": True}


# ─── Fix #4: workflow.py pokreni template visibility check ───────────────────


@pytest.mark.anyio
async def test_pokreni_workflow_rejects_foreign_firm_template():
    """A firm must not be able to start a workflow using another firm's private template."""
    from routers.workflow import PokretanjeRequest, pokreni_workflow
    from fastapi import HTTPException

    def _table(name):
        t = MagicMock()
        if name == "kancelarije":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "kanc-attacker"}
        elif name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "pred-001"}
        elif name == "workflow_templates":
            # visibility-scoped query (system OR own firm) finds nothing for a foreign template
            t.select.return_value.eq.return_value.or_.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    payload = PokretanjeRequest(predmet_id="pred-001", template_id="tpl-foreign-firm")

    with patch("routers.workflow._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await pokreni_workflow(_fake_request("/api/workflow/pokreni"), payload, user=_fake_user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_pokreni_workflow_accepts_own_firm_template():
    """No regression: a firm can still start a workflow using its own template."""
    from routers.workflow import PokretanjeRequest, pokreni_workflow

    def _table(name):
        t = MagicMock()
        if name == "kancelarije":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "kanc-own"}
        elif name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "pred-001"}
        elif name == "workflow_templates":
            t.select.return_value.eq.return_value.or_.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "tpl-own", "naziv": "Standardni tok", "koraci": [{"naziv": "Korak 1", "rok_dana": 5}],
            }
        elif name == "workflow_instances":
            t.insert.return_value.execute.return_value.data = [{"id": "wf-001"}]
        elif name == "workflow_steps":
            t.insert.return_value.execute.return_value.data = [{"id": "step-001"}]
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    payload = PokretanjeRequest(predmet_id="pred-001", template_id="tpl-own")

    with patch("routers.workflow._get_supa", return_value=mock_supa):
        result = await pokreni_workflow(_fake_request("/api/workflow/pokreni"), payload, user=_fake_user())

    assert result["ok"] is True


# ─── Fix #5: billing.py entry/timer predmet ownership check ──────────────────
# Same sweep also found billing_entry_create/timer_start/billing_po_klijentu
# accepted a client-supplied predmet_id with no ownership check at all (a
# cross-tenant billing-data-injection path). timer_start's happy/409/race
# paths already have dedicated coverage in test_billing_timer_race.py; this
# covers the specific rejection this fix adds, for both write endpoints.


@pytest.mark.anyio
async def test_billing_entry_create_rejects_foreign_predmet():
    from routers.billing import EntryReq, billing_entry_create
    from fastapi import HTTPException

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    body = EntryReq(predmet_id="pred-foreign", opis="Sastanak", tip="tarifa", iznos_rsd=1000)

    with patch("routers.billing._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await billing_entry_create(body, _fake_request("/api/billing/entries"), user=_fake_user())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_billing_timer_start_rejects_foreign_predmet():
    from routers.billing import TimerStartReq, timer_start
    from fastapi import HTTPException

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    body = TimerStartReq(predmet_id="pred-foreign")

    with patch("routers.billing._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await timer_start(body, _fake_request("/api/billing/timer/start"), user=_fake_user())

    assert exc.value.status_code == 404


# ─── Fix #6: copilot.py povezi_klijenta predmet ownership check ──────────────


def _mock_gpt_response(content: dict):
    import json
    choice = MagicMock()
    choice.message.content = json.dumps(content)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.anyio
async def test_povezi_klijenta_rejects_foreign_predmet():
    from unittest.mock import AsyncMock
    from routers.copilot import _handle_akcija_povezi_klijenta

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table

    with patch("routers.copilot._get_supa", return_value=mock_supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(
             return_value=_mock_gpt_response({"ime_klijenta": "Ana Jović", "uloga": "stranka"})
         )):
        result = await _handle_akcija_povezi_klijenta("poveži Anu Jović", "pred-foreign", "uid-attacker")

    assert result["uspeh"] is False
    assert "nije pronađen" in result["odgovor"]


# ─── Fix #7: intake.py predmet_klijenti insert klijent ownership check ───────


@pytest.mark.anyio
async def test_intake_kreiraj_skips_linking_foreign_klijent():
    """A klijent_id the caller does not own must be silently skipped when
    creating a case via the intake wizard, not linked to the new predmet."""
    from unittest.mock import AsyncMock
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-new", "user_id": _fake_user()["user_id"]}]
            # Program Lambda, Certification 004: recent-duplicate check before insert.
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
        elif name == "klijenti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        elif name == "predmet_klijenti":
            def _insert(payload):
                insert_calls.append(payload)
                i = MagicMock()
                i.execute.return_value.data = [payload]
                return i
            t.insert.side_effect = _insert
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    body = IntakeKreirajReq(naziv="Test predmet", klijent_id="kl-foreign")

    def _capture_create_task(coro, *a, **kw):
        coro.close()
        return MagicMock()

    with patch("routers.intake._get_supa", return_value=mock_supa), \
         patch("asyncio.create_task", side_effect=_capture_create_task), \
         patch("services.case_pipeline.run_case_pipeline", new=AsyncMock()):
        await intake_kreiraj(body, _fake_request("/api/intake/kreiraj"), user=_fake_user())

    assert insert_calls == [], "a klijent_id not owned by the caller must never be linked"
