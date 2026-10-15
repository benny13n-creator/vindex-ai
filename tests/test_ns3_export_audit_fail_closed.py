# -*- coding: utf-8 -*-
"""
NS3-C — obavezan audit izvoza, FAIL-CLOSED (GET /api/export/complete).

Ugovor (odluka osnivaca, static/security.html §14.2 se NE menja: „Svaki
kompletan izvoz upisuje se u nepromenjivi audit log (user_id, vreme, format)"):
ZIP se predaje odgovoru SAMO ako je (1) svaka tabela procitana, (2) arhiva
napravljena, (3) kanonski upis pokusan i (4) `log_action` vratio id upisanog
reda. None, izuzetak ili istek roka (ishod NEPOZNAT) -> 503, nijedan bajt
arhive. Zapis uspeha tvrdi samo `archive_generated`, nikad isporuku.

Sve sinteticko: lazni Supabase iz test_n04, bez mreze.
"""
import asyncio
import json
import logging
import os
import sys
import threading
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_n04_case_export_integrity import (  # noqa: E402
    A, B, TABELE_IZVOZA, FakeSupa, _sadrzaj,
)

EMAIL = "tajna.adresa.ns3@x.rs"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _audit_mok(audit, vrati="audit-id", kasnjenje=0.0, baci=None):
    async def _log(action, **kw):
        if kasnjenje:
            await asyncio.sleep(kasnjenje)
        audit.append((action, kw))
        if baci is not None:
            raise baci
        return vrati(action) if callable(vrati) else vrati
    return _log


async def _pozovi(supa, log, uid=A):
    """Vrati (('ok', resp, telo) | ('err', HTTPException))."""
    import routers.data_export as de
    from fastapi import HTTPException

    with patch.object(de, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=log):
        try:
            resp = await de.export_complete(user={"user_id": uid, "email": EMAIL})
        except HTTPException as exc:
            return ("err", exc)
        telo = b""
        async for deo in resp.body_iterator:
            telo += deo
        return ("ok", resp, telo)


def _odbijen_bez_arhive(rez):
    assert rez[0] == "err", "ZIP isporucen bez dokazanog audit upisa"
    exc = rez[1]
    assert exc.status_code == 503
    assert "nije poslat" in exc.detail
    # istinito: ne tvrdi da je upis uspeo ni da je izvoz poslat
    assert "upisan je" not in exc.detail and "uspe" not in exc.detail


# ── C1: uspeh samo uz uspesan kanonski upis ──────────────────────────────

@pytest.mark.anyio
async def test_kompletna_arhiva_i_uspesan_upis_daje_zip():
    audit = []
    rez = await _pozovi(FakeSupa(), _audit_mok(audit))
    assert rez[0] == "ok"
    _, resp, telo = rez
    assert resp.status_code == 200 and resp.media_type == "application/zip"
    assert set(_sadrzaj(telo)) == {"README.txt", *TABELE_IZVOZA.values()}
    assert [a for a, _ in audit] == ["data_export"]


@pytest.mark.anyio
async def test_pravi_log_action_sa_upisanim_redom_daje_zip_i_red_nosi_lanac():
    """Pravi log_action + pravi _build_and_insert; lazni PostgREST vraca upisan red."""
    import shared.audit_immutable as ai

    upisi = []

    class _Q:
        def __init__(self):
            self._ins = None

        def select(self, *a, **k):
            return self

        order = limit = select

        def insert(self, red):
            self._ins = red
            return self

        def execute(self):
            class R:
                pass
            r = R()
            if self._ins is None:
                r.data = [{"entry_hash": "a" * 64}]
            else:
                upisi.append(self._ins)
                r.data = [{**self._ins, "id": "11111111-1111-1111-1111-111111111111"}]
            return r

    class _Audit:
        def table(self, ime):
            assert ime == "audit_immutable"
            return _Q()

    import routers.data_export as de
    with patch("api._get_supa", return_value=_Audit()), \
         patch.object(de, "_get_supa", return_value=FakeSupa()):
        resp = await de.export_complete(user={"user_id": A, "email": EMAIL})
    assert resp.status_code == 200
    [red] = upisi
    assert red["action"] == "data_export" and red["user_id"] == A
    assert red["prev_hash"] == "a" * 64 and len(red["entry_hash"]) == 64
    meta = json.loads(red["metadata"])
    assert meta["stage"] == "archive_generated"
    assert meta["delivery"] == "not_verified_by_server"
    assert "email" not in meta and EMAIL not in red["metadata"]
    assert ai.AUDITABLE_ACTIONS >= {"data_export", "data_export_failed"}


# ── C2/C3: None, izuzetak, nepoznat ishod -> nema ZIP-a ──────────────────

@pytest.mark.anyio
async def test_log_action_vraca_none_nema_zipa():
    audit = []
    rez = await _pozovi(FakeSupa(), _audit_mok(audit, vrati=None))
    _odbijen_bez_arhive(rez)
    # brz neuspeh: pokusan istinit zapis o odbijenom izvozu
    assert [a for a, _ in audit] == ["data_export", "data_export_failed"]
    m = audit[1][1]["metadata"]
    assert m["stage"] == "audit_unproven" and m["reason"] == "not_persisted"
    assert m["archive_sent"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("vrednost", ["", True, 1, {"id": "x"}])
async def test_ne_string_ili_prazan_id_nije_dokaz(vrednost):
    rez = await _pozovi(FakeSupa(), _audit_mok([], vrati=vrednost))
    _odbijen_bez_arhive(rez)


@pytest.mark.anyio
async def test_log_action_baca_nema_zipa(caplog):
    audit = []
    with caplog.at_level(logging.DEBUG):
        rez = await _pozovi(FakeSupa(), _audit_mok(audit, baci=RuntimeError("TAJNA-NS3")))
    _odbijen_bez_arhive(rez)
    assert "TAJNA-NS3" not in caplog.text and EMAIL not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.anyio
async def test_istek_roka_ishod_nepoznat_nema_zipa(caplog):
    import routers.data_export as de

    audit = []
    with caplog.at_level(logging.DEBUG), patch.object(de, "_AUDIT_TIMEOUT_S", 0.05):
        rez = await _pozovi(FakeSupa(), _audit_mok(audit, kasnjenje=1.0))
    _odbijen_bez_arhive(rez)
    # posle isteka nema drugog cekanja na isti sink
    assert audit == []
    assert "timeout" in caplog.text and EMAIL not in caplog.text


@pytest.mark.anyio
async def test_istek_roka_sa_pravim_log_action_nit_koja_visi_nema_zipa():
    """asyncio.to_thread se ne moze prekinuti: nit visi u INSERT-u, ruta posle
    roka odbija izvoz (ishod nepoznat). Nit se zatim pusti."""
    import routers.data_export as de
    import shared.audit_immutable as ai

    pusti = threading.Event()

    def _visi(*a, **k):
        pusti.wait(5)
        return "kasni-id"

    try:
        with patch.object(ai, "_build_and_insert", side_effect=_visi), \
             patch.object(de, "_AUDIT_TIMEOUT_S", 0.1), \
             patch.object(de, "_get_supa", return_value=FakeSupa()):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                await de.export_complete(user={"user_id": A, "email": EMAIL})
    finally:
        pusti.set()
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_nedostupan_db_audit_sink_nema_zipa():
    import routers.data_export as de
    import shared.audit_immutable as ai
    from fastapi import HTTPException

    with patch.object(ai, "_build_and_insert", side_effect=ConnectionError("down")), \
         patch.object(de, "_get_supa", return_value=FakeSupa()):
        with pytest.raises(HTTPException) as exc:
            await de.export_complete(user={"user_id": A, "email": EMAIL})
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_akcija_van_auditable_actions_nije_uspeh():
    """log_action tiho vraca None za neregistrovanu akciju -- to nije dokaz."""
    import routers.data_export as de
    import shared.audit_immutable as ai
    from fastapi import HTTPException

    with patch.object(ai, "AUDITABLE_ACTIONS", ai.AUDITABLE_ACTIONS - {"data_export"}), \
         patch.object(ai, "_build_and_insert", return_value="id"), \
         patch.object(de, "_get_supa", return_value=FakeSupa()):
        with pytest.raises(HTTPException) as exc:
            await de.export_complete(user={"user_id": A, "email": EMAIL})
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_postgrest_bez_vracenog_reda_nije_uspeh():
    """_build_and_insert: prazan `result.data` -> None -> nema ZIP-a."""
    import routers.data_export as de
    from fastapi import HTTPException

    class _Q:
        def select(self, *a, **k):
            return self
        order = limit = insert = select

        def execute(self):
            class R:
                data = []
            return R()

    class _Audit:
        def table(self, _ime):
            return _Q()

    with patch("api._get_supa", return_value=_Audit()), \
         patch.object(de, "_get_supa", return_value=FakeSupa()):
        with pytest.raises(HTTPException) as exc:
            await de.export_complete(user={"user_id": A, "email": EMAIL})
    assert exc.value.status_code == 503


# ── C4: nepotpun izvoz i serijalizacija (postojece greske, bez ZIP-a) ────

@pytest.mark.anyio
async def test_nepotpuno_citanje_postojeca_greska_bez_zipa_i_bez_uspeha():
    audit = []
    rez = await _pozovi(FakeSupa(padovi={"rocista"}), _audit_mok(audit))
    assert rez[0] == "err" and rez[1].status_code == 503
    assert "nije kompletan" in rez[1].detail
    assert [a for a, _ in audit] == ["data_export_failed"]


@pytest.mark.anyio
async def test_pad_serijalizacije_bez_zipa():
    import routers.data_export as de

    audit = []
    with patch.object(de.json, "dumps", side_effect=ValueError("x")):
        rez = await _pozovi(FakeSupa(), _audit_mok(audit))
    assert rez[0] == "err" and rez[1].status_code == 500
    assert [(a, kw["metadata"]["stage"]) for a, kw in audit] == [("data_export_failed", "serialization")]


# ── C6: posle uspesnog upisa prekid odgovora; ponovljen zahtev ───────────

@pytest.mark.anyio
async def test_uspesan_upis_pa_prekinut_odgovor_zapis_ne_tvrdi_isporuku():
    import routers.data_export as de

    audit = []
    with patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch("shared.audit_immutable.log_action", new=_audit_mok(audit)):
        resp = await de.export_complete(user={"user_id": A, "email": EMAIL})
        upisano_pre_tela = [a for a, _ in audit]
        it = resp.body_iterator
        await it.__anext__()          # klijent primi deo...
        await it.aclose()             # ...pa veza pukne
    assert upisano_pre_tela == ["data_export"]
    [(_, kw)] = audit
    m = kw["metadata"]
    assert m["stage"] == "archive_generated"
    assert m["delivery"] == "not_verified_by_server"
    assert not {"delivered", "downloaded", "completed", "archive_sent"} & set(m)


@pytest.mark.anyio
async def test_ponovljen_zahtev_svaki_ima_svoj_upis():
    audit = []
    r1 = await _pozovi(FakeSupa(), _audit_mok(audit))
    r2 = await _pozovi(FakeSupa(), _audit_mok(audit))
    assert r1[0] == r2[0] == "ok"
    assert [a for a, _ in audit] == ["data_export", "data_export"]


@pytest.mark.anyio
async def test_ponovljen_zahtev_posle_neuspeha_upisa_uspeva_kad_sink_proradi():
    audit = []
    r1 = await _pozovi(FakeSupa(), _audit_mok(audit, vrati=None))
    r2 = await _pozovi(FakeSupa(), _audit_mok(audit))
    _odbijen_bez_arhive(r1)
    assert r2[0] == "ok"


# ── C5: neprijavljen zahtev i tudji podaci ───────────────────────────────

def _app():
    from fastapi import FastAPI
    import routers.data_export as de
    app = FastAPI()
    app.include_router(de.router)
    return app


def test_neprijavljen_zahtev_401_bez_citanja_i_bez_audita():
    from fastapi.testclient import TestClient
    import routers.data_export as de
    import shared.deps as deps

    supa = FakeSupa()
    audit = []

    async def _tiho(*a, **k):
        return None

    with patch.object(de, "_get_supa", return_value=supa), \
         patch.object(deps, "_log_login_failed", new=_tiho), \
         patch("shared.audit_immutable.log_action", new=_audit_mok(audit)):
        with TestClient(_app()) as c:
            r = c.get("/api/export/complete")
    assert r.status_code == 401
    assert r.headers.get("content-type", "").startswith("application/json")
    assert supa.citanja == [] and audit == []


def test_tudji_podaci_nisu_u_izvozu_filter_na_svakoj_tabeli():
    from fastapi.testclient import TestClient
    import routers.data_export as de
    from shared.deps import get_current_user

    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": A, "email": EMAIL}
    supa = FakeSupa()
    audit = []
    with patch.object(de, "_get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=_audit_mok(audit)):
        with TestClient(app) as c:
            r = c.get(f"/api/export/complete?user_id={B}", headers={"X-User-Id": B})
    assert r.status_code == 200
    for ime, bajtovi in _sadrzaj(r.content).items():
        assert b"TAJNA-B" not in bajtovi and B.encode() not in bajtovi, ime
    procitane = {t for t, _ in supa.citanja}
    assert procitane == set(TABELE_IZVOZA)
    for tabela, filteri in supa.citanja:
        assert ("user_id", A) in filteri, tabela
    assert [kw["user_id"] for _, kw in audit] == [A]


# ── C7: nema nepotrebnog PII u novom zapisu ──────────────────────────────

@pytest.mark.anyio
async def test_novi_zapis_uspeha_bez_e_poste():
    audit = []
    rez = await _pozovi(FakeSupa(), _audit_mok(audit))
    assert rez[0] == "ok"
    [(_, kw)] = audit
    assert kw["user_id"] == A
    assert "email" not in kw["metadata"]
    assert EMAIL not in json.dumps(kw, default=str)
    # README u arhivi (korisnikov sopstveni podatak) i dalje nosi e-postu
    assert EMAIL.encode() in _sadrzaj(rez[2])["README.txt"]
