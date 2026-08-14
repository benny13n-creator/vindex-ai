# -*- coding: utf-8 -*-
"""
Operation Living System -- regression coverage for the coordinator's own fix cycle.
Each test proves a specific reproduced, real-world lawyer-facing scenario is closed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-za-testove-128bit")

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Fix L1 (Wave 1, "AI reasoning chain" team, REPRODUCED): Copilot's
# verovatnoca_uspeha was never capped by CAP_BY_READINESS, unlike its 3 sibling
# success-probability fields in digital_twin.py/court_predictor.py/hearing_cc.py --
# a case with an open critical case_actions row (canonical readiness=CRITICAL_GAP)
# could show Copilot's field at Genome's own uncapped percentage while every other
# AI surface for the same case was structurally capped at 50.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_copilot_verovatnoca_uspeha_capped_by_canonical_readiness():
    from routers import copilot as cp

    predmet = {
        "naziv": "Test", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {"snaga_predmeta_procent": 85},
    }
    open_critical_action = [{"razlog": "Nedostaje ključni dokaz", "prioritet": "critical", "rok": None, "status": "open"}]

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        elif name == "case_actions":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = open_critical_action
        else:
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_gpt(oai, **kwargs):
        import json
        msg = MagicMock()
        msg.message.content = json.dumps({"procena": "ok", "prednosti": [], "nedostaju": []})
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_pozovi_gpt4o_mini", new=_fake_gpt):
        result = await cp._handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    # Genome's own uncapped number was 85; canonical readiness=CRITICAL_GAP caps at 50.
    assert result["verovatnoca_uspeha"] == 50


@pytest.mark.anyio
async def test_copilot_verovatnoca_uspeha_uncapped_when_readiness_clean():
    from routers import copilot as cp

    predmet = {
        "naziv": "Test", "opis": "Opis", "tip": "radno", "status": "aktivan",
        "case_dna": {"snaga_predmeta_procent": 85},
    }

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        elif name == "case_actions":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        else:
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_gpt(oai, **kwargs):
        import json
        msg = MagicMock()
        msg.message.content = json.dumps({"procena": "ok", "prednosti": [], "nedostaju": []})
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_pozovi_gpt4o_mini", new=_fake_gpt):
        result = await cp._handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    # Zero open actions -> readiness=READY -> no cap applies, Genome's own number stands.
    assert result["verovatnoca_uspeha"] == 85


# ═══════════════════════════════════════════════════════════════════════════
# Fix L2 (Wave 3, "Portfolio Scale" team, REPRODUCED CRITICAL): the daily email
# reminder cron never filtered by predmeti.status -- a deadline belonging to an
# archived/closed case was emailed to the lawyer exactly like an active one. This
# is a proactive push straight to the inbox, unlike a dashboard the lawyer opens
# by choice -- the single most trust-damaging instance of the archived-case-leak
# bug class this mission found.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_email_reminder_skips_deadline_on_archived_case():
    from routers.email_notif import posalji_podsetnike
    from starlette.requests import Request as StarletteRequest
    from datetime import date, timedelta

    def _req():
        scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
                  "path": "/email-notif/send-reminders", "app": MagicMock(), "state": MagicMock()}
        return StarletteRequest(scope=scope)

    target_iso = (date.today() + timedelta(days=7)).isoformat()

    def _table(name):
        t = MagicMock()
        if name == "korisnik_email_notif":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": "uid-001", "aktivan": True, "dan_7": True, "dan_3": False, "dan_1": False}
            ]
        elif name == "profiles":
            t.select.return_value.execute.return_value.data = [{"id": "uid-001", "email": "advokat@vindex.rs"}]
        elif name == "predmeti":
            # The only case this user has is ARCHIVED -- the active-ids set must be empty.
            t.select.return_value.eq.return_value.not_.in_.return_value.execute.return_value.data = []
        elif name == "email_notif_log":
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmet_hronologija":
            t.select.return_value.eq.return_value.in_.return_value.eq.return_value.execute.return_value.data = [
                {"dogadjaj": "Rok za žalbu", "datum_iso": target_iso, "predmet_id": "pred-archived"}
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.email_notif._get_supa", return_value=supa), \
         patch("routers.email_notif._smtp_send") as mock_send:
        result = await posalji_podsetnike(_req(), {"user_id": "cron", "email": "cron@vindex.rs", "role": "cron"})

    assert result["poslato"] == 0
    mock_send.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Fix L3 (Wave 5, Billing Red Team, REPRODUCED HIGH): billing_entry_update/delete
# checked `obracunato` in a separate read from the write -- a concurrent
# faktura_create() could mark the entry invoiced in between, and the update/delete
# would still succeed, silently corrupting an amount already frozen into an
# invoice total. Now the actual write re-asserts obracunato=False.
# ═══════════════════════════════════════════════════════════════════════════

def _billing_req():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "PATCH", "path": "/", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


@pytest.mark.anyio
async def test_billing_entry_update_rejects_when_invoiced_between_read_and_write():
    from routers import billing as bl

    class Body:
        opis = "izmenjen opis"
        bodovi = None
        sati = None
        iznos_rsd = None
        datum = None

    def _table(name):
        t = MagicMock()
        if name == "billing_entries":
            # Pre-check read says NOT yet invoiced...
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"obracunato": False}
            # ...but the actual write's own obracunato=False guard now matches ZERO rows,
            # simulating a concurrent faktura_create() that invoiced it in between.
            t.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(bl, "_get_supa", return_value=supa):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await bl.billing_entry_update("entry-1", Body(), _billing_req(), {"user_id": "u1"})

    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_billing_entry_delete_rejects_when_invoiced_between_read_and_write():
    from routers import billing as bl

    def _table(name):
        t = MagicMock()
        if name == "billing_entries":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"obracunato": False}
            t.delete.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(bl, "_get_supa", return_value=supa):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await bl.billing_entry_delete("entry-1", _billing_req(), {"user_id": "u1"})

    assert exc_info.value.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# Fix L4 (Wave 5, Copilot Red Team, REPRODUCED HIGH): _handle_akcija_rok's prompt
# asked GPT for "kritičan|bitan|normalan", but predmet_hronologija.vaznost's real
# CHECK constraint only allows ('kritičan','važan','informativan') -- 2 of 3
# possible GPT outputs, and the code's own literal fallback, always violated the
# constraint and threw on insert. A guaranteed break, not a rare race.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_akcija_rok_normalizes_out_of_schema_vaznost_before_insert():
    from routers import copilot as cp
    import json

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"id": "pred-1"}
        elif name == "predmet_hronologija":
            def _insert(row):
                insert_calls.append(row)
                m = MagicMock()
                m.execute.return_value = MagicMock()
                return m
            t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_gpt(oai, **kwargs):
        msg = MagicMock()
        # Poisoned/legacy-shaped GPT response using the OLD, DB-incompatible vocabulary.
        msg.message.content = json.dumps({"dogadjaj": "Priprema podneska", "datum_iso": "2026-09-01", "vaznost": "bitan"})
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    with patch.object(cp, "_get_supa", return_value=supa), \
         patch.object(cp, "_pozovi_gpt4o_mini", new=_fake_gpt), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await cp._handle_akcija_rok("Dodaj rok za pripremu do 1. septembra", "pred-1", "user-1")

    assert result.get("uspeh") is not False
    assert len(insert_calls) == 1
    assert insert_calls[0]["vaznost"] in ("kritičan", "važan", "informativan")


# ═══════════════════════════════════════════════════════════════════════════
# Fix L5 (Wave 5, Client Portal Red Team, REPRODUCED HIGH): a collaborator (role
# "vodenje", not the case owner) generating a client portal token had the token
# and DB row built with the COLLABORATOR's own uid, not the real owner's -- but
# _verifikuj_token/client_portal_view look the case up by the real owner's
# user_id, so the link always 404'd for the client (false success: ok:True
# returned, email sent claiming success) and the real owner had no visibility
# or revoke power over it (their own list/delete endpoints are owner-scoped).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_collaborator_generated_token_uses_real_owner_uid():
    from routers.client_portal import generiši_portal_token, GeneriišiTokenReq, _verifikuj_token
    from starlette.requests import Request as StarletteRequest

    def _req():
        scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
                  "path": "/api/client-portal/token", "app": MagicMock(), "state": MagicMock()}
        return StarletteRequest(scope=scope)

    predmet_id = "pred-shared-1"
    owner_uid = "uid-owner-real"
    collaborator_uid = "uid-collaborator"
    inserted = {}

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            sel = MagicMock()
            def _eq_id(col, val):
                inner = MagicMock()
                def _eq_user(col2, val2):
                    leaf = MagicMock()
                    # Only the REAL owner's user_id matches this case.
                    leaf.execute.return_value.data = (
                        [{"id": predmet_id, "naziv": "Test predmet", "status": "aktivan"}]
                        if val2 == owner_uid else []
                    )
                    return leaf
                inner.eq.side_effect = _eq_user
                return inner
            sel.eq.side_effect = _eq_id
            t.select.return_value = sel
        elif name == "predmet_saradnici":
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "owner_user_id": owner_uid, "uloga": "vodenje"
            }
        elif name == "client_portal_tokens":
            def _insert(row):
                inserted.update(row)
                m = MagicMock()
                m.execute.return_value.data = [{"id": "token-row-1"}]
                return m
            t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.client_portal._get_supa", return_value=supa):
        result = await generiši_portal_token(
            predmet_id, GeneriišiTokenReq(valjanost_dana=30), _req(), {"user_id": collaborator_uid}
        )

    assert result["ok"] is True
    assert inserted["user_id"] == owner_uid  # not the collaborator
    # The generated token must actually verify to the real owner, not the collaborator.
    verified_predmet_id, advokat_uid = _verifikuj_token(result["token"])
    assert verified_predmet_id == predmet_id
    assert advokat_uid == owner_uid


# ═══════════════════════════════════════════════════════════════════════════
# Fix L6 (Wave 5, Genome Red Team, REPRODUCED HIGH): the backend already detects a
# post-GPT DB-write failure (case_dna_persisted:false + honest old genome), but
# the frontend's _voice_refresh_case_dna never read that field -- a save that
# silently failed still showed the green "ažurirana" success toast.
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_refresh_toast_checks_case_dna_persisted_flag():
    VJS = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()
    marker = "async function _voice_refresh_case_dna(predmetId) {"
    block = VJS.split(marker, 1)[1][:3500]
    assert "data.case_dna_persisted === false" in block
    idx_check = block.index("data.case_dna_persisted === false")
    idx_success_toast = block.index("Procena predmeta ažurirana")
    assert idx_check < idx_success_toast  # the failure check must run BEFORE the success toast


# ═══════════════════════════════════════════════════════════════════════════
# Fix L7 (Wave 3, Portfolio Scale team, REPRODUCED HIGH): Command Center's
# "today's hearings" / "next 7 days" / "<48h urgent" panels never filtered by
# predmeti.status -- a hearing/deadline for an archived/closed case rendered on
# the app's actual home tab exactly like an active one, while the risk
# computation a few sections later in the SAME endpoint correctly excludes them.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_command_center_excludes_hearings_and_deadlines_for_archived_case():
    import importlib
    import sys as _sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    test_dashboard = importlib.import_module("test_dashboard")
    from routers import dashboard as dash

    active_id = test_dashboard.PID
    archived_id = test_dashboard.PID2

    predmeti = [
        {"id": active_id, "naziv": "Aktivan predmet", "tip": "opsti", "status": "aktivan", "updated_at": "2026-01-01"},
        {"id": archived_id, "naziv": "Arhiviran predmet", "tip": "opsti", "status": "zatvoren", "updated_at": "2026-01-01"},
    ]
    rocista = [
        {"id": "r1", "predmet_id": active_id, "sud": "Sud1", "datum": "2026-08-07", "vreme": "10:00", "status": "zakazano"},
        {"id": "r2", "predmet_id": archived_id, "sud": "Sud2", "datum": "2026-08-07", "vreme": "11:00", "status": "zakazano"},
    ]
    # BETA-DEADLINE-DOMAIN-001 (2026-08-14): fixture prebacen sa nepostojece
    # tabele `rokovi` na kanonskog vlasnika `predmet_hronologija`. Invarijanta
    # koju test cuva -- rok arhiviranog predmeta ne sme na pocetni ekran --
    # nije promenjena; promenjen je izvor iz kog rok dolazi.
    from datetime import date as _d, timedelta as _t
    _sutra = (_d.today() + _t(days=1)).isoformat()
    hronologija = [
        {"id": "h1", "predmet_id": active_id, "dogadjaj": "Rok A",
         "datum_iso": _sutra, "vaznost": "kritičan", "akter": ""},
        {"id": "h2", "predmet_id": archived_id, "dogadjaj": "Rok B",
         "datum_iso": _sutra, "vaznost": "kritičan", "akter": ""},
    ]

    supa = test_dashboard._make_cc_supa(predmeti=predmeti, rocista=rocista, rokovi=hronologija)

    with patch.object(dash, "_get_supa", return_value=supa):
        result = await dash.command_center(test_dashboard._req(), test_dashboard._user())

    assert all(r["predmet_id"] != archived_id for r in result["danasnja_rocista"])
    assert any(r["predmet_id"] == active_id for r in result["danasnja_rocista"])
    assert all(r["predmet_id"] != archived_id for r in result["rokovi_7_dana"])
    assert any(r["predmet_id"] == active_id for r in result["rokovi_7_dana"])
