# -*- coding: utf-8 -*-
"""OSB003 Task 7 — nov solo korisnik BEZ ijednog predmeta: /api/workspace mora poštovati ugovor isključene autonomije.

Nađeno u browser testu (frontend-v2-ng/tests/live-solo-tok-e2e.mjs): bez predmeta `_fetch_prepared_work` nije ni
pitao bazu, pa je stanje bilo „OK" i pre migracije 136 — Danas je novom korisniku prikazivao blok „Vindex je
pripremio" (reklama za isključenu autonomiju). Ugovor (NS007/ONS001): tabela ne postoji → NIJE_UKLJUCENO.
"""
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401

PGRST205 = '{"code": "PGRST205", "message": "Could not find the table public.%s in the schema cache"}'


def test_bez_predmeta_pre_136_je_nije_ukljuceno(solo):
    k, b = solo
    b.greske["autonomy_work_items"] = Exception(PGRST205 % "autonomy_work_items")
    w = k.get("/api/workspace", headers=A)
    assert w.status_code == 200
    assert w.json()["vindex_je_pripremio_stanje"] == "NIJE_UKLJUCENO" and w.json()["vindex_je_pripremio"] == []


def test_bez_predmeta_posle_136_je_ok_i_prazno(solo):
    k, b = solo
    b.tabele["autonomy_work_items"] = [{"id": "w-B", "user_id": "uid-B", "predmet_id": "x", "status": "READY_FOR_REVIEW"}]
    w = k.get("/api/workspace", headers=A)
    assert w.json()["vindex_je_pripremio_stanje"] == "OK" and w.json()["vindex_je_pripremio"] == []


def test_druga_greska_baze_bez_predmeta_nije_prikrivena(solo):
    k, b = solo
    b.greske["autonomy_work_items"] = Exception('{"code": "57014", "message": "statement timeout"}')
    w = k.get("/api/workspace", headers=A)
    assert w.json()["vindex_je_pripremio_stanje"] == "NIJE_PROCITANO"


def test_sa_predmetom_pre_136_i_dalje_nije_ukljuceno(solo):
    k, b = solo
    b.greske["autonomy_work_items"] = Exception(PGRST205 % "autonomy_work_items")
    assert k.post("/api/predmeti", json={"naziv": "Prvi predmet"}, headers=A).status_code == 200
    assert k.get("/api/workspace", headers=A).json()["vindex_je_pripremio_stanje"] == "NIJE_UKLJUCENO"
