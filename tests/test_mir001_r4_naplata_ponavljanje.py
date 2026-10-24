# -*- coding: utf-8 -*-
"""MIR001 FINAL RELEASE R4 (tačka 6–7) — dvostruka naplata nacrta iz spisa: mrežno ponavljanje vs dve izričite izrade.

Stvarna ruta `POST /api/agents/run` (savetnik `drafting` nad predmetom → AI RADNI PREDLOG na pregledu) kroz STVARNI
`IdempotencyMiddleware` (`shared/idempotency.py`, skladište `SupabaseSkladiste` nad lažnom bazom solo okruženja).
V2 (`VxApi.send`) šalje `Idempotency-Key` — jedan ključ po kliku; mrežno ponavljanje istog zahteva nosi ISTI ključ.
Mere: broj naplata (`UsageService.consume`), broj poziva modela i broj predloga na pregledu.
"""
import uuid

import pytest

from tests.test_mir001_c3b_usvajanje import _model
from tests.test_mir001_t06_nacrt_iz_spisa import _nacrti, nacrt, treba_ocr  # noqa: F401
from tests.test_mir001_t04_savetnik_spis import savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, solo  # noqa: F401

TELO = {"agent": "drafting", "task": "Sastavi podnesak tuzioca.", "predmet_id": None}


def _brojac(monkeypatch):
    from shared.usage import UsageService
    naplate = []

    async def _naplata(*a, **kw):
        naplate.append(a[2] if len(a) > 2 else kw.get("feature"))
    monkeypatch.setattr(UsageService, "consume", staticmethod(_naplata))
    return naplate


def _sacekaj_predlog(b, pid, n):
    """Upis predloga na pregled je pozadinski (`asyncio.create_task` posle odgovora) — sačekaj ga."""
    import time
    for _ in range(200):
        if len(_nacrti(b, pid)) >= n:
            return
        time.sleep(0.02)
    raise AssertionError("predlog nije upisan na pregled")


def _posalji(k, pid, kljuc=None):
    h = dict(A)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return k.post("/api/agents/run", json={**TELO, "predmet_id": pid}, headers=h)


@treba_ocr
def test_mrezno_ponavljanje_istog_kljuca_naplacuje_jednom(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    naplate = _brojac(monkeypatch)
    kljuc = str(uuid.uuid4())
    r1 = _posalji(k, pid, kljuc)
    assert r1.status_code == 200, r1.text
    _sacekaj_predlog(b, pid, 1)
    r2 = _posalji(k, pid, kljuc)          # isti zahtev ponovo (Chromium posle prekida HTTP/2 sesije)
    assert r2.status_code == 200 and r2.headers.get("idempotent-replayed") == "true", (r2.status_code, r2.text[:200])
    assert r2.json()["odgovor"] == r1.json()["odgovor"]
    assert naplate == ["multi_agent"], naplate               # JEDNA naplata
    assert len(snimljeno) == 1                               # jedan poziv modela
    assert len(_nacrti(b, pid)) == 1                         # jedan predlog na pregledu


@treba_ocr
def test_isti_kljuc_drugo_telo_ne_izvrsava_i_ne_naplacuje(nacrt, monkeypatch):
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    naplate = _brojac(monkeypatch)
    kljuc = str(uuid.uuid4())
    assert _posalji(k, pid, kljuc).status_code == 200
    h = {**A, "Idempotency-Key": kljuc}
    r = k.post("/api/agents/run", json={**TELO, "predmet_id": pid, "task": "Drugi zadatak."}, headers=h)
    assert r.status_code == 409 and "IDEMPOTENCY_CONFLICT" in r.text
    assert naplate == ["multi_agent"] and len(snimljeno) == 1 and len(_nacrti(b, pid)) == 1


@treba_ocr
@pytest.mark.parametrize("kljuc", [True, False], ids=["V2_novi_kljuc", "bez_kljuca"])
def test_drugi_klik_u_prozoru_ponavljanja_ne_zove_model_i_ne_naplacuje(nacrt, monkeypatch, kljuc):
    """Pre R4: drugi klik (novi ključ ili klijent bez ključa) u 30 s → model + naplata, a predlog tiho odbačen kao
    duplikat (`_stage_draft_for_review`) — naplaćeno bez predloga na pregledu. Posle R4: 409 PRE modela i naplate."""
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    naplate = _brojac(monkeypatch)
    assert _posalji(k, pid, str(uuid.uuid4()) if kljuc else None).status_code == 200
    _sacekaj_predlog(b, pid, 1)
    r = _posalji(k, pid, str(uuid.uuid4()) if kljuc else None)
    assert r.status_code == 409 and "Ništa nije pokrenuto ni naplaćeno" in r.json()["detail"], r.text[:300]
    assert naplate == ["multi_agent"] and len(snimljeno) == 1 and len(_nacrti(b, pid)) == 1


@treba_ocr
def test_dve_izricite_izrade_van_prozora_su_dve_naplate_i_dva_predloga(nacrt, monkeypatch):
    """Dve izričite izrade (posle prozora ponavljanja) = dva poziva modela = dve naplate = DVA predloga na pregledu —
    svaka naplata ima svoj predlog (ugovor, ne dvostruka naplata)."""
    import routers.drafting as DR
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    naplate = _brojac(monkeypatch)
    assert _posalji(k, pid, str(uuid.uuid4())).status_code == 200
    _sacekaj_predlog(b, pid, 1)
    monkeypatch.setattr(DR, "_STAGING_RETRY_WINDOW_SECONDS", 0)     # prozor je prošao
    assert _posalji(k, pid, str(uuid.uuid4())).status_code == 200
    _sacekaj_predlog(b, pid, 2)
    assert naplate == ["multi_agent", "multi_agent"] and len(snimljeno) == 2 and len(_nacrti(b, pid)) == 2


@treba_ocr
def test_trka_drugi_klik_pre_upisa_prvog_predloga_ne_gubi_naplacen_predlog(nacrt, monkeypatch):
    """Drugi klik stigne PRE nego što je prvi predlog upisan (pozadinski upis) — provera pre izrade ga ne vidi. Tada su
    to dve naplaćene izrade i MORAJU biti dva predloga na pregledu (pre R4: drugi je tiho odbačen kao duplikat)."""
    import routers.drafting as DR
    k, b, pid, doks, snimljeno = nacrt
    _model(monkeypatch, snimljeno)
    naplate = _brojac(monkeypatch)

    async def _ne_vidi(*a, **kw):
        return False
    monkeypatch.setattr(DR, "_recent_generation_exists", _ne_vidi)
    assert _posalji(k, pid, str(uuid.uuid4())).status_code == 200
    _sacekaj_predlog(b, pid, 1)
    assert _posalji(k, pid, str(uuid.uuid4())).status_code == 200
    _sacekaj_predlog(b, pid, 2)
    assert naplate == ["multi_agent", "multi_agent"] and len(snimljeno) == 2 and len(_nacrti(b, pid)) == 2


@treba_ocr
def test_neuspela_izrada_nije_naplacena_pa_ponovni_pokusaj_nije_dupla_naplata(nacrt, monkeypatch):
    """502 (odgovor modela nije razdvojiv) ne naplaćuje; sledeći klik je prva naplata."""
    import routers.multi_agent as MA
    k, b, pid, doks, snimljeno = nacrt
    naplate = _brojac(monkeypatch)
    pravi = MA._pozovi_nacrt_api

    def _los(client, system, user_msg):
        snimljeno.append(1)
        import types
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content="nije JSON"), finish_reason="stop")])
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", _los)
    r = _posalji(k, pid, str(uuid.uuid4()))
    assert r.status_code == 502 and naplate == [] and _nacrti(b, pid) == []
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", pravi)
    _model(monkeypatch, snimljeno)
    assert _posalji(k, pid, str(uuid.uuid4())).status_code == 200
    _sacekaj_predlog(b, pid, 1)
    assert naplate == ["multi_agent"] and len(_nacrti(b, pid)) == 1
