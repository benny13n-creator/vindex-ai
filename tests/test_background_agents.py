# -*- coding: utf-8 -*-
"""
Regression tests — KORAK B: Autonomni "Background" Action Agenti (2026-07-24).

Pokriva:
  1. services/agent_tasks/court_portal_watcher.py — keyword detekcija
     odluke, rok kalkulacija (reuse routers/zastarelost.py), dedup preko
     agent_recommendations, best-effort nacrt (greška ne blokira preporuku),
     ownership (tuđi praceni_predmeti se preskaču).
  2. services/agent_tasks/precedents_radar.py — poređenje sa Case Genome-om,
     "neutralno" klasifikacija se odbacuje (bez preporuke), dedup po
     decision_number.
  3. workers/background_agents.py — org_key rezolucija (solo vs kancelarija),
     budžetski limit po organizaciji, AGENT_AUTONOMOUS_EXECUTION audit log,
     jedan agent koji baca ne obara ostatak run-a.
  4. routers/agent_notifications.py — lista samo sopstvenih preporuka,
     accept/reject ownership check, dupli resolve na već rešenoj preporuci.

Pure unit/integration tests -- no live Supabase, no OpenAI.
"""
import asyncio
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "neq", "in_", "is_", "gte", "lte", "order",
                   "limit", "insert", "update", "single", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    # .not_ is accessed as an attribute THEN called (q.not_.is_(...) /
    # q.not_.in_(...)) -- it must be a distinct mock whose own methods
    # return the chain `m`, not `m` itself (m.not_.is_(...) would
    # otherwise resolve to an unconfigured auto-mock, breaking the chain).
    not_mock = MagicMock()
    not_mock.is_ = MagicMock(return_value=m)
    not_mock.in_ = MagicMock(return_value=m)
    m.not_ = not_mock
    m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# 1. services/agent_tasks/court_portal_watcher.py
# ═══════════════════════════════════════════════════════════════════════════

def test_izgleda_kao_odluka_detects_keywords():
    import services.agent_tasks.court_portal_watcher as watcher
    assert watcher._IZGLEDA_KAO_ODLUKA_RE.search("Doneta je Presuda")
    assert watcher._IZGLEDA_KAO_ODLUKA_RE.search("Rešenje o troškovima postupka")
    assert not watcher._IZGLEDA_KAO_ODLUKA_RE.search("Ročište zakazano za 12.03.")


def test_tip_roka_za_predmet_krivicno_vs_gradjansko():
    import services.agent_tasks.court_portal_watcher as watcher
    assert watcher._tip_roka_za_predmet("Krivično pravo") == "zalba_kz"
    assert watcher._tip_roka_za_predmet("Radno pravo") == "zalba_zpp"
    assert watcher._tip_roka_za_predmet("") == "zalba_zpp"


def test_izracunaj_rok_zalba_zpp_is_15_radnih_dana_from_start():
    import services.agent_tasks.court_portal_watcher as watcher
    pocetak = date(2026, 8, 3)  # ponedeljak
    rok = watcher._izracunaj_rok("zalba_zpp", pocetak)
    assert rok is not None
    assert rok > pocetak
    assert (rok - pocetak).days >= 15  # radni dani >= kalendarski broj dana


def test_izracunaj_rok_unknown_tip_returns_none():
    import services.agent_tasks.court_portal_watcher as watcher
    assert watcher._izracunaj_rok("nepostojeci_tip", date.today()) is None


def test_run_creates_recommendation_with_rok_and_draft_for_decision_status():
    import services.agent_tasks.court_portal_watcher as watcher

    promene = [{
        "praceni_predmet_id": "pp1", "new_status": "Presuda", "status_tekst": "Doneta je Presuda",
        "status_datum": "2026-07-20", "created_at": "2026-07-24T08:00:00Z",
    }]
    pp_rows = [{"id": "pp1", "predmet_id": "pred1", "naziv": "Test predmet",
                "broj_predmeta": "P-1/26", "sud_naziv": "Prvi osnovni sud"}]
    pred_row = {"oblast_prava": "Građansko pravo"}

    log_chain = _chain(MagicMock(data=promene))
    pp_chain = _chain(MagicMock(data=pp_rows))
    pred_chain = _chain(MagicMock(data=pred_row))
    insert_chain = _chain(MagicMock(data=[{"id": "rec1"}]))

    def _table(name):
        return {
            "portal_status_log": log_chain,
            "praceni_predmeti": pp_chain,
            "predmeti": pred_chain,
            "agent_recommendations": insert_chain,
        }[name]

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(watcher, "_pripremi_nacrt", new=AsyncMock(return_value="Nacrt zalbe...")):
        result = asyncio.run(watcher.run("u1", supa))

    assert result == {"obradjeno": 1, "preporuke_kreirane": 1, "greske": 0}
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["agent_type"] == "court_portal_watcher"
    assert inserted["payload"]["izgleda_kao_odluka"] is True
    assert inserted["payload"]["nacrt_reakcije"] == "Nacrt zalbe..."
    assert inserted["payload"]["rok"]["tip_roka"] == "zalba_zpp"
    assert inserted["dedup_key"] == "portal:pp1:2026-07-20"


def test_run_creates_recommendation_without_draft_when_generation_fails():
    """Best-effort nacrt: LLM greška ne sme da spreči kreiranje preporuke."""
    import services.agent_tasks.court_portal_watcher as watcher

    promene = [{
        "praceni_predmet_id": "pp1", "status_tekst": "Doneto je Rešenje",
        "status_datum": "2026-07-20", "created_at": "2026-07-24T08:00:00Z",
    }]
    pp_rows = [{"id": "pp1", "predmet_id": "pred1", "naziv": "X", "broj_predmeta": "1", "sud_naziv": "Sud"}]

    log_chain = _chain(MagicMock(data=promene))
    pp_chain = _chain(MagicMock(data=pp_rows))
    pred_chain = _chain(MagicMock(data={"oblast_prava": ""}))
    insert_chain = _chain(MagicMock(data=[{"id": "rec1"}]))
    supa = MagicMock()
    supa.table.side_effect = lambda n: {
        "portal_status_log": log_chain, "praceni_predmeti": pp_chain,
        "predmeti": pred_chain, "agent_recommendations": insert_chain,
    }[n]

    with patch.object(watcher, "_pripremi_nacrt", new=AsyncMock(return_value=None)):
        result = asyncio.run(watcher.run("u1", supa))

    assert result["preporuke_kreirane"] == 1
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["payload"]["nacrt_reakcije"] is None


def test_run_skips_praceni_predmet_not_owned_by_user():
    """Ownership: promena čiji praceni_predmet_id ne pripada ovom
    korisniku (eq('user_id', user_id) filter u upitu vraća prazno) se
    tiho preskače, ne kreira preporuku."""
    import services.agent_tasks.court_portal_watcher as watcher

    promene = [{"praceni_predmet_id": "tudje_pp", "status_tekst": "Presuda",
                "status_datum": "2026-07-20", "created_at": "2026-07-24T08:00:00Z"}]
    log_chain = _chain(MagicMock(data=promene))
    pp_chain = _chain(MagicMock(data=[]))  # eq(user_id=...) je isfiltrirao sve -- ništa ne pripada
    supa = MagicMock()
    supa.table.side_effect = lambda n: {"portal_status_log": log_chain, "praceni_predmeti": pp_chain}.get(n, MagicMock())

    result = asyncio.run(watcher.run("u1", supa))
    assert result == {"obradjeno": 1, "preporuke_kreirane": 0, "greske": 0}


def test_run_duplicate_key_is_not_counted_as_error():
    import services.agent_tasks.court_portal_watcher as watcher

    promene = [{"praceni_predmet_id": "pp1", "status_tekst": "Ročište zakazano",
                "status_datum": "2026-07-20", "created_at": "2026-07-24T08:00:00Z"}]
    pp_rows = [{"id": "pp1", "predmet_id": "pred1", "naziv": "X", "broj_predmeta": "1", "sud_naziv": "Sud"}]
    log_chain = _chain(MagicMock(data=promene))
    pp_chain = _chain(MagicMock(data=pp_rows))
    pred_chain = _chain(MagicMock(data={"oblast_prava": ""}))

    insert_chain = MagicMock()
    for m in ("select", "eq", "insert"):
        setattr(insert_chain, m, MagicMock(return_value=insert_chain))
    insert_chain.execute = MagicMock(side_effect=Exception('duplicate key value violates unique constraint 23505'))

    supa = MagicMock()
    supa.table.side_effect = lambda n: {
        "portal_status_log": log_chain, "praceni_predmeti": pp_chain,
        "predmeti": pred_chain, "agent_recommendations": insert_chain,
    }[n]

    result = asyncio.run(watcher.run("u1", supa))
    assert result == {"obradjeno": 1, "preporuke_kreirane": 0, "greske": 0}


def test_run_never_raises_when_db_unavailable():
    import services.agent_tasks.court_portal_watcher as watcher
    supa = MagicMock()
    supa.table.side_effect = RuntimeError("no db")
    result = asyncio.run(watcher.run("u1", supa))
    assert result["greske"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. services/agent_tasks/precedents_radar.py
# ═══════════════════════════════════════════════════════════════════════════

def test_pravna_pozicija_iz_genoma_none_when_empty():
    import services.agent_tasks.precedents_radar as radar
    assert radar._pravna_pozicija_iz_genoma({}, "Radno pravo") is None
    assert radar._pravna_pozicija_iz_genoma({"greska": True}, "Radno pravo") is None


def test_pravna_pozicija_iz_genoma_builds_text():
    import services.agent_tasks.precedents_radar as radar
    genome = {"pravna_teorija": {"sustina_spora": "Nezakonit otkaz", "osnov_odgovornosti": "Čl. 179 ZR"}}
    pozicija = radar._pravna_pozicija_iz_genoma(genome, "Radno pravo")
    assert "Nezakonit otkaz" in pozicija
    assert "Radno pravo" in pozicija


def test_run_skips_predmet_without_case_dna():
    import services.agent_tasks.precedents_radar as radar
    pred_chain = _chain(MagicMock(data=[{"id": "p1", "naziv": "X", "oblast_prava": "Radno pravo", "case_dna": {}}]))
    supa = MagicMock()
    supa.table.side_effect = lambda n: {"predmeti": pred_chain}.get(n, MagicMock())

    result = asyncio.run(radar.run("u1", supa))
    assert result == {"predmeta_skenirano": 0, "preporuke_kreirane": 0, "greske": 0}


def test_run_creates_recommendation_when_odnos_is_supportive_or_challenging():
    import services.agent_tasks.precedents_radar as radar

    genome = {"pravna_teorija": {"sustina_spora": "Nezakonit otkaz ugovora o radu"}}
    pred_chain = _chain(MagicMock(data=[{"id": "p1", "naziv": "Petrović", "oblast_prava": "Radno pravo", "case_dna": genome}]))
    insert_chain = _chain(MagicMock(data=[{"id": "rec1"}]))
    supa = MagicMock()
    supa.table.side_effect = lambda n: {"predmeti": pred_chain, "agent_recommendations": insert_chain}[n]

    fake_odluke = [{"decision_number": "Rev 123/2026", "court": "VKS", "date": "2026-07-01",
                     "matter": "otkaz", "text": "Sud je zauzeo stav...", "score": 0.9}]

    with patch("app.services.retrieve.retrieve_sudska_praksa", return_value=["raw_match"]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=fake_odluke), \
         patch.object(radar, "_klasifikuj", new=AsyncMock(return_value={"odnos": "osporava", "obrazlozenje": "..."})):
        result = asyncio.run(radar.run("u1", supa))

    assert result["predmeta_skenirano"] == 1
    assert result["preporuke_kreirane"] == 1
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["agent_type"] == "precedents_radar"
    assert inserted["payload"]["odnos"] == "osporava"
    assert inserted["dedup_key"] == "precedent:p1:Rev 123/2026"


def test_run_skips_neutral_classification():
    import services.agent_tasks.precedents_radar as radar

    genome = {"pravna_teorija": {"sustina_spora": "Nezakonit otkaz"}}
    pred_chain = _chain(MagicMock(data=[{"id": "p1", "naziv": "X", "oblast_prava": "Radno pravo", "case_dna": genome}]))
    insert_chain = _chain(MagicMock(data=[{"id": "rec1"}]))
    supa = MagicMock()
    supa.table.side_effect = lambda n: {"predmeti": pred_chain, "agent_recommendations": insert_chain}[n]

    fake_odluke = [{"decision_number": "Rev 1/26", "court": "VKS", "date": "2026-01-01",
                     "matter": "", "text": "Nepovezan tekst.", "score": 0.5}]

    with patch("app.services.retrieve.retrieve_sudska_praksa", return_value=["raw"]), \
         patch("app.services.retrieve.process_praksa_chunks", return_value=fake_odluke), \
         patch.object(radar, "_klasifikuj", new=AsyncMock(return_value={"odnos": "neutralno", "obrazlozenje": ""})):
        result = asyncio.run(radar.run("u1", supa))

    assert result["preporuke_kreirane"] == 0
    insert_chain.insert.assert_not_called()


def test_run_never_raises_when_rag_search_fails():
    import services.agent_tasks.precedents_radar as radar
    genome = {"pravna_teorija": {"sustina_spora": "X"}}
    pred_chain = _chain(MagicMock(data=[{"id": "p1", "naziv": "X", "oblast_prava": "Radno pravo", "case_dna": genome}]))
    supa = MagicMock()
    supa.table.side_effect = lambda n: {"predmeti": pred_chain}.get(n, MagicMock())

    with patch("app.services.retrieve.retrieve_sudska_praksa", side_effect=RuntimeError("pinecone down")):
        result = asyncio.run(radar.run("u1", supa))

    assert result["greske"] == 1
    assert result["preporuke_kreirane"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. workers/background_agents.py
# ═══════════════════════════════════════════════════════════════════════════

def test_resolve_orgs_batched_solo_when_no_kancelarija_membership():
    """NIGHTLY REPAIR (2026-07-24), Faza 3 item 11: _resolve_orgs_batched
    replaces the old per-user _org_key_and_members loop with 2 total
    queries for ALL users, not 1-2 per user."""
    import workers.background_agents as wba
    membership_chain = _chain(MagicMock(data=[]))  # no membership rows for anyone
    supa = MagicMock()
    supa.table.return_value = membership_chain

    result = asyncio.run(wba._resolve_orgs_batched(["u1"], supa))
    assert result["u1"] == ("solo:u1", ["u1"])


def test_resolve_orgs_batched_groups_kancelarija_members_in_two_queries():
    import workers.background_agents as wba
    membership_chain = _chain(MagicMock(data=[{"clan_id": "u1", "kancelarija_id": "firm1"}]))
    all_members_chain = _chain(MagicMock(data=[
        {"clan_id": "u1", "kancelarija_id": "firm1"},
        {"clan_id": "u2", "kancelarija_id": "firm1"},
    ]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return membership_chain if call_count["n"] == 1 else all_members_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    result = asyncio.run(wba._resolve_orgs_batched(["u1"], supa))
    org_key, members = result["u1"]
    assert org_key == "kancelarija:firm1"
    assert set(members) == {"u1", "u2"}
    # Tačno 2 upita ukupno za rezoluciju organizacija, bez obzira na broj korisnika.
    assert call_count["n"] == 2


def test_resolve_orgs_batched_mixed_solo_and_team_users_in_one_pass():
    import workers.background_agents as wba
    membership_chain = _chain(MagicMock(data=[{"clan_id": "u1", "kancelarija_id": "firm1"}]))
    all_members_chain = _chain(MagicMock(data=[{"clan_id": "u1", "kancelarija_id": "firm1"}]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return membership_chain if call_count["n"] == 1 else all_members_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    result = asyncio.run(wba._resolve_orgs_batched(["u1", "u2solo"], supa))
    assert result["u1"][0] == "kancelarija:firm1"
    assert result["u2solo"] == ("solo:u2solo", ["u2solo"])


def test_budget_used_by_org_groups_by_org_and_agent_type():
    import workers.background_agents as wba
    usage_chain = _chain(MagicMock(data=[
        {"user_id": "u1", "action": "court_portal_watcher"},
        {"user_id": "u1", "action": "court_portal_watcher"},
        {"user_id": "u2", "action": "precedents_radar"},  # u2 is in the same org as u1
        {"user_id": "u3", "action": "court_portal_watcher"},  # different org
    ]))
    supa = MagicMock()
    supa.table.return_value = usage_chain

    org_to_members = {"kancelarija:firm1": ["u1", "u2"], "solo:u3": ["u3"]}
    used = asyncio.run(wba._budget_used_by_org(org_to_members, supa))

    assert used["kancelarija:firm1"]["court_portal_watcher"] == 2
    assert used["kancelarija:firm1"]["precedents_radar"] == 1
    assert used["solo:u3"]["court_portal_watcher"] == 1


def test_budget_exhausted_skips_agent_execution():
    import workers.background_agents as wba

    with patch.object(wba, "_get_active_user_ids", new=AsyncMock(return_value=["u1"])), \
         patch.object(wba, "_resolve_orgs_batched", new=AsyncMock(return_value={"u1": ("solo:u1", ["u1"])})), \
         patch.object(wba, "_budget_used_by_org", new=AsyncMock(return_value={"solo:u1": {"court_portal_watcher": 999}})), \
         patch.object(wba, "_agent_registry", return_value={"court_portal_watcher": AsyncMock()}), \
         patch("shared.deps._get_supa", return_value=MagicMock()):
        result = asyncio.run(wba.run_background_agents("run1"))

    assert result["org_budzet_iscrpljen"] == 1
    assert result["po_agentu"]["court_portal_watcher"]["izvrsenja"] == 0


def test_run_background_agents_logs_audit_and_usage_on_success():
    import workers.background_agents as wba

    fake_agent = AsyncMock(return_value={"obradjeno": 2, "preporuke_kreirane": 1, "greske": 0})
    audit_calls = []

    async def _fake_log_action(action, **kwargs):
        audit_calls.append((action, kwargs))

    with patch.object(wba, "_get_active_user_ids", new=AsyncMock(return_value=["u1"])), \
         patch.object(wba, "_resolve_orgs_batched", new=AsyncMock(return_value={"u1": ("solo:u1", ["u1"])})), \
         patch.object(wba, "_budget_used_by_org", new=AsyncMock(return_value={"solo:u1": {}})), \
         patch.object(wba, "_agent_registry", return_value={"court_portal_watcher": fake_agent}), \
         patch("shared.deps._get_supa", return_value=MagicMock()), \
         patch("shared.audit_immutable.log_action", new=_fake_log_action):
        result = asyncio.run(wba.run_background_agents("run1"))

    assert result["po_agentu"]["court_portal_watcher"]["izvrsenja"] == 1
    assert result["po_agentu"]["court_portal_watcher"]["preporuke_kreirane"] == 1
    assert len(audit_calls) == 1
    assert audit_calls[0][0] == "AGENT_AUTONOMOUS_EXECUTION"
    assert audit_calls[0][1]["resource_id"] == "court_portal_watcher"


def test_one_agent_failure_does_not_block_others_or_other_users():
    import workers.background_agents as wba

    failing_agent = AsyncMock(side_effect=RuntimeError("boom"))
    ok_agent = AsyncMock(return_value={"obradjeno": 1, "preporuke_kreirane": 1, "greske": 0})

    with patch.object(wba, "_get_active_user_ids", new=AsyncMock(return_value=["u1", "u2"])), \
         patch.object(wba, "_resolve_orgs_batched", new=AsyncMock(return_value={
             "u1": ("solo:u1", ["u1"]), "u2": ("solo:u2", ["u2"]),
         })), \
         patch.object(wba, "_budget_used_by_org", new=AsyncMock(return_value={"solo:u1": {}, "solo:u2": {}})), \
         patch.object(wba, "_agent_registry", return_value={"failing": failing_agent, "ok": ok_agent}), \
         patch("shared.deps._get_supa", return_value=MagicMock()), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = asyncio.run(wba.run_background_agents("run1"))

    assert result["korisnika_obradjeno"] == 2
    assert result["po_agentu"]["failing"]["greske"] == 2  # oba korisnika
    assert result["po_agentu"]["ok"]["izvrsenja"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# 4. routers/agent_notifications.py
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    from api import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


def _auth_headers():
    return {"Authorization": "Bearer faketoken"}


def test_lista_preporuka_only_own(client):
    rows = [{"id": "r1", "user_id": "u1", "status": "pending", "naslov": "X"}]
    with patch("shared.deps._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.agent_notifications._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data=rows))
        r = client.get("/api/agent-notifications", headers=_auth_headers())

    assert r.status_code == 200
    body = r.json()
    assert body["ukupno"] == 1
    call_kwargs = mock_supa.return_value.table.return_value.eq.call_args_list
    assert any(c.args == ("user_id", "u1") for c in call_kwargs)


def test_lista_preporuka_invalid_status_rejected(client):
    with patch("shared.deps._verify_token", return_value={"sub": "u1", "email": "a@b.com"}):
        r = client.get("/api/agent-notifications?status=nepostojeci", headers=_auth_headers())
    assert r.status_code == 400


def test_accept_rejects_when_not_owned_or_missing(client):
    with patch("shared.deps._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.agent_notifications._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data=None))
        r = client.post("/api/agent-notifications/does-not-exist/accept", headers=_auth_headers())

    assert r.status_code == 404


def test_accept_rejects_already_resolved(client):
    with patch("shared.deps._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.agent_notifications._get_supa") as mock_supa:
        mock_supa.return_value.table.return_value = _chain(MagicMock(data={"id": "r1", "status": "accepted"}))
        r = client.post("/api/agent-notifications/r1/accept", headers=_auth_headers())

    assert r.status_code == 409


def test_accept_success_updates_status(client):
    select_chain = _chain(MagicMock(data={"id": "r1", "status": "pending"}))
    update_chain = _chain(MagicMock(data=[{"id": "r1", "status": "accepted"}]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else update_chain

    with patch("shared.deps._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.agent_notifications._get_supa") as mock_supa:
        mock_supa.return_value.table.side_effect = _table
        r = client.post("/api/agent-notifications/r1/accept", headers=_auth_headers())

    assert r.status_code == 200
    assert r.json()["ok"] is True
    updated_fields = update_chain.update.call_args[0][0]
    assert updated_fields["status"] == "accepted"
