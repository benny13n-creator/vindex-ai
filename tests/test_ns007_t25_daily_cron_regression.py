"""NS007 Task 25 — `/api/cron/daily` ostaje ponašanjem netaknut i odvojen od autonomnog rada.

Postojeći testovi dnevnog crona (test_cron_daily_dispatcher, test_cron_daily_failclosed_auth, test_background_agents,
test_wave4_preflight_b_email_cron_auth) prolaze nepromenjeni. Ovde:
  • dnevni dispečer ne poziva i ne pominje autonomni ciklus; i dalje poziva `run_background_agents` (Modul 10);
  • legacy registar dnevnog crona = tačno 2 agenta preporuka (agent trajnog rada nema `run`);
  • pun legacy prolaz agenata ne pravi nijedan autonomni rad;
  • autonomni ciklus radi bez ijednog heartbeat-a dnevnog crona (ne čita `chain_anchors`).
"""
import asyncio
import inspect

import pytest

import tests.ns007_fake as f7


def test_dnevni_dispecer_odvojen_od_autonomije():
    import api
    izvor = inspect.getsource(api.cron_daily)
    assert "run_background_agents" in izvor, "Modul 10 (legacy agenti) i dalje postoji"
    for zabranjeno in ("run_autonomy_cycle", "/api/cron/autonomy", "autonomy_work_items", "autonomy_cycles"):
        assert zabranjeno not in izvor, zabranjeno
    assert 'os.getenv("BRIEFING_CRON_SECRET"' in izvor, "autentifikacija dnevnog crona nepromenjena"


def test_legacy_registar_tacno_dva_agenta_preporuka():
    import workers.background_agents as ba
    assert set(ba._agent_registry()) == {"court_portal_watcher", "precedents_radar"}
    assert set(ba._work_agents()) == {"HEARING_PREP", "PRECEDENT_IMPACT"}


def test_legacy_prolaz_ne_pravi_autonomni_rad(monkeypatch):
    k, baza = f7.pripremi(monkeypatch, {"predmeti": [{"id": "aaaaaaaa-1111-4000-8000-00000000000a", "user_id": "uid-A",
                                                      "status": "aktivan", "naziv": "P", "case_dna": {}}],
                                        "kancelarija_clanovi": [], "usage_events": []})
    try:
        import workers.background_agents as ba
        r = asyncio.run(ba.run_background_agents("dnevni"))
        assert r["korisnika_obradjeno"] == 1
        assert baza.tabele.get("autonomy_work_items", []) == [] and baza.tabele.get("autonomy_cycles", []) == []
    finally:
        f7.ocisti()


def test_autonomni_ciklus_ne_cita_heartbeat_dnevnog_crona(monkeypatch):
    k, baza = f7.pripremi(monkeypatch, {"predmeti": [], "kancelarija_clanovi": []})
    try:
        import workers.background_agents as ba
        monkeypatch.setenv("AUTONOMY_CRON_SECRET", "t" * 40)
        r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": "t" * 40})
        assert r.json()["status"] == "COMPLETED"
        assert not [z for z in baza.dnevnik if z["tabela"] in ("chain_anchors", "cron_runs")]
    finally:
        f7.ocisti()
