# -*- coding: utf-8 -*-
"""
NS2b TASK D — redosled audit upisa izvoza u odnosu na odgovor.

Ugovor koji se meri (vidi izvestaj):
  * static/security.html §14.2: "Svaki kompletan izvoz upisuje se u
    nepromenjivi audit log".
  * shared/audit_immutable.py::log_action: "Greska u audit-u NIKAD ne blokira
    glavni zahtev" -- pad upisa se guta i vraca None (best-effort NA NEUSPEH).
  * shared/bg.py: spawn NE cini posao trajnim; task umire sa procesom.

Dakle: neuspesan upis ne obara izvoz (vec mereno u test_c1_export_stages), ali
pokusaj upisa mora biti ZAVRSEN pre nego sto ijedan bajt arhive napusti
server. Sa `spawn` je upis tek zakazan kada odgovor krene; gasenje procesa
posle isporuke a pre upisa ostavlja isporucen izvoz bez zapisa.

Sve sinteticko: lazni Supabase iz test_n04, bez mreze.
"""
import asyncio
import logging
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_n04_case_export_integrity import (  # noqa: E402
    A, TABELE_IZVOZA, FakeSupa, _sadrzaj,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _spor_audit(audit, kasnjenje=0.05):
    async def _snimi(action, **kw):
        # Pravi log_action radi INSERT u niti (asyncio.to_thread): nikad nije
        # zavrsen u istom koraku petlje u kom je zakazan.
        await asyncio.sleep(kasnjenje)
        audit.append((action, kw))
        return "audit-id"
    return _snimi


async def _ubij_pozadinu():
    """Simulira tvrdo gasenje procesa (SIGKILL / OOM / istek grace roka):
    pozadinski taskovi se prekidaju bez drenaze."""
    import shared.bg as bg
    zadaci = list(bg._BG)
    for t in zadaci:
        t.cancel()
    if zadaci:
        await asyncio.gather(*zadaci, return_exceptions=True)


@pytest.mark.anyio
async def test_uspesan_izvoz_upis_zavrsen_pre_vracanja_odgovora():
    import routers.data_export as de

    audit = []
    with patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch("shared.audit_immutable.log_action", new=_spor_audit(audit)):
        resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        # bez cekanja: odgovor je u rukama servera, nijedan bajt jos nije poslat
        upisano_pri_odgovoru = [a for a, _ in audit]
        await _ubij_pozadinu()
    assert resp.status_code == 200
    assert upisano_pri_odgovoru == ["data_export"]


@pytest.mark.anyio
async def test_gasenje_procesa_posle_isporuke_ne_ostavlja_izvoz_bez_zapisa():
    """Klijent primi CEO ZIP, pa proces umre pre drenaze. Zapis mora postojati."""
    import routers.data_export as de

    audit = []
    with patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch("shared.audit_immutable.log_action", new=_spor_audit(audit)):
        resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        telo = b""
        async for deo in resp.body_iterator:
            telo += deo
        await _ubij_pozadinu()
    assert set(_sadrzaj(telo)) == {"README.txt", *TABELE_IZVOZA.values()}
    assert [a for a, _ in audit] == ["data_export"]


@pytest.mark.anyio
@pytest.mark.parametrize("scenario", ["pre_retrieval", "retrieval", "serialization"])
async def test_neuspeh_upis_zavrsen_pre_greske_klijentu(scenario):
    import routers.data_export as de
    from fastapi import HTTPException

    audit = []
    supa = FakeSupa(padovi={"rocista"}) if scenario == "retrieval" else FakeSupa()
    zakrpe = [patch("shared.audit_immutable.log_action", new=_spor_audit(audit))]
    if scenario == "pre_retrieval":
        zakrpe.append(patch.object(de, "_get_supa", side_effect=RuntimeError("x")))
    else:
        zakrpe.append(patch.object(de, "_get_supa", return_value=supa))
    if scenario == "serialization":
        zakrpe.append(patch.object(de.json, "dumps", side_effect=ValueError("x")))
    for z in zakrpe:
        z.start()
    try:
        with pytest.raises(HTTPException):
            await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        upisano = [(a, kw["metadata"]["stage"]) for a, kw in audit]
        await _ubij_pozadinu()
    finally:
        for z in reversed(zakrpe):
            z.stop()
    assert upisano == [("data_export_failed", scenario)]


@pytest.mark.anyio
async def test_audit_koji_baci_izuzetak_ne_obara_izvoz(caplog):
    """log_action po ugovoru ne baca; ako ipak baci (regresija), izvoz ostaje
    isporucen (ugovor: audit nikad ne blokira zahtev) a pad je vidljiv u logu."""
    import routers.data_export as de

    async def _baci(action, **kw):
        raise RuntimeError("TAJNA-NS2B-AUDIT")

    with caplog.at_level(logging.WARNING), \
         patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch("shared.audit_immutable.log_action", new=_baci):
        resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        telo = b""
        async for deo in resp.body_iterator:
            telo += deo
        for _ in range(5):
            await asyncio.sleep(0)
    assert resp.status_code == 200
    assert set(_sadrzaj(telo)) == {"README.txt", *TABELE_IZVOZA.values()}
    assert "data_export" in caplog.text and "RuntimeError" in caplog.text
    assert "TAJNA-NS2B-AUDIT" not in caplog.text


@pytest.mark.anyio
async def test_nedostupan_audit_sink_vidljiv_u_logu_izvoz_isporucen(caplog):
    """Best-effort na neuspeh (log_action ugovor): izvoz isporucen, a pad upisa
    je detektabilan samo kroz log upozorenje -- ne kroz odgovor."""
    import routers.data_export as de
    import shared.audit_immutable as ai

    with caplog.at_level(logging.WARNING), \
         patch.object(de, "_get_supa", return_value=FakeSupa()), \
         patch.object(ai, "_build_and_insert", side_effect=ConnectionError("down")):
        resp = await de.export_complete(user={"user_id": A, "email": "a@x.rs"})
        poruke_pri_odgovoru = caplog.text
        await _ubij_pozadinu()
    assert resp.status_code == 200
    assert "[AUDIT_IMMUTABLE]" in poruke_pri_odgovoru
