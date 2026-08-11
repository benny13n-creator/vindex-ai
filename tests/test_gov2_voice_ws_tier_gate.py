# -*- coding: utf-8 -*-
"""
Governance Wave 2 — WebSocket glasovni kanal proverava tarifu.

NALAZ

`voice` je `minimum_plan='professional'` (`migrations/064_feature_registry.sql:136`).
Sve tri HTTP glasovne rute (`routers/voice.py:401,467,515`) idu kroz
`PermissionService.require("voice")`, pa `basic` korisnik dobija 403.

WebSocket ne prolazi kroz FastAPI `Depends`, pa `PermissionService.require`
tamo nikad nije opalio. `_authenticate` (`routers/voice_realtime.py:64-82`)
proveravao je kill-switch i `status`, ali NE `minimum_plan`.

Posledica: korisnik na `basic` tarifi — a to je podrazumevana tarifa svake nove
registracije (`migrations/063_entitlement_system.sql:30`; `api.py:2498` ne
postavlja `subscription_type`, pa važi DEFAULT) — imao je pun pristup realtime
kanalu koji mu je na HTTP-u zatvoren.

ZAŠTO JE BAŠ TAJ KANAL NAJGORI ZA OVU RUPU

Realtime kanal nosi izgovoreni privilegovani razgovor advokata sa klijentom, i
jedini je AI put u sistemu bez ijednog `ai_forensics` ili `audit_immutable`
reda. Otvoren je bio kanal sa najviše sadržaja i najmanje traga.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_POLITIKA = {
    "feature_key": "voice", "aktivno": True, "status": "ACTIVE",
    "minimum_plan": "professional", "addon": None, "krediti": 0,
}


def _ws():
    w = MagicMock()
    w.query_params = {"token": "tok"}
    w.close = AsyncMock()
    return w


async def _autentifikuj(tarifa: str, *, founder: bool = False, profil_pada: bool = False):
    import routers.voice_realtime as vr

    profil = {"subscription_type": tarifa, "addons": [], "subscription_expires_at": None}
    ensure = AsyncMock(side_effect=RuntimeError("baza")) if profil_pada else AsyncMock(return_value=profil)

    w = _ws()
    with patch.object(vr, "_verify_token", return_value={"sub": "u1", "email": "a@test.rs"}), \
         patch.object(vr, "get_policy", new=AsyncMock(return_value=dict(_POLITIKA))), \
         patch.object(vr, "_is_founder", return_value=founder), \
         patch("shared.permissions._ensure_profile", new=ensure):
        rezultat = await vr._authenticate(w)
    return rezultat, w


# ─── 1. TARIFNA GRANICA ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_basic_korisnik_ne_moze_otvoriti_realtime_kanal():
    """Srž nalaza. Isti feature, isti korisnik, dva kanala — isti odgovor."""
    rezultat, w = await _autentifikuj("basic")
    assert rezultat is None, "basic korisnik je pušten u realtime glasovni kanal"
    w.close.assert_awaited()
    razlog = w.close.await_args.kwargs.get("reason", "")
    assert "Professional" in razlog, f"razlog odbijanja ne pominje tarifu: {razlog!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("tarifa", ["professional", "enterprise"])
async def test_ng_ovlascene_tarife_prolaze(tarifa):
    """Negativna kontrola.

    Bez ovoga bi `test_a` prolazio i da kapija odbija SVE — što bi značilo da
    ne meri tarifu nego da je kanal ugašen.
    """
    rezultat, w = await _autentifikuj(tarifa)
    assert rezultat is not None, f"{tarifa} je odbijen iako zadovoljava minimum_plan"
    assert rezultat["user_id"] == "u1"
    w.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_b_founder_zadrzava_izuzetak():
    """Founder prolazi tarifu i na HTTP putanji (`permissions.py:159-163`).

    Kapija ne sme biti stroža od postojećeg modela — to bi bila nova politika,
    ne popravka propusta.
    """
    rezultat, _ = await _autentifikuj("basic", founder=True)
    assert rezultat is not None


# ─── 2. FAIL-CLOSED ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_c_greska_pri_citanju_profila_ZATVARA_kanal():
    """Najvažnija odluka u ovoj popravci.

    `except Exception: pass` ovde bi značio da pad baze otvara glasovni kanal
    svima. Za privilegovani sadržaj to nije prihvatljiv kompromis — pa je
    ponašanje fail-closed, za razliku od nekih drugih fail-soft putanja u
    sistemu.
    """
    rezultat, w = await _autentifikuj("professional", profil_pada=True)
    assert rezultat is None, (
        "greška pri čitanju profila je PROPUSTILA korisnika — fail-open na "
        "kanalu koji nosi privilegovani razgovor"
    )
    w.close.assert_awaited()


# ─── 3. KILL-SWITCH I DALJE IMA PREDNOST ────────────────────────────────────

@pytest.mark.asyncio
async def test_d_kill_switch_ostaje_iznad_tarife():
    """Redosled provera: `aktivno=false` mora blokirati i foundera i professional.

    Da je tarifna provera stavljena ispred kill-switcha, gašenje voice-a za
    betu ne bi važilo za naloge koji zadovoljavaju tarifu.
    """
    import routers.voice_realtime as vr

    ugaseno = dict(_POLITIKA, aktivno=False)
    w = _ws()
    with patch.object(vr, "_verify_token", return_value={"sub": "u1", "email": "f@test.rs"}), \
         patch.object(vr, "get_policy", new=AsyncMock(return_value=ugaseno)), \
         patch.object(vr, "_is_founder", return_value=True), \
         patch("shared.permissions._ensure_profile", new=AsyncMock(return_value={"subscription_type": "enterprise"})):
        rezultat = await vr._authenticate(w)
    assert rezultat is None
    assert "onemogućen" in w.close.await_args.kwargs.get("reason", "")


# ─── 4. PARITET SA HTTP PUTANJOM ────────────────────────────────────────────

def test_e_ws_koristi_iste_helpere_kao_http():
    """Ne nova logika — ponovna upotreba `shared/permissions.py`.

    Da WS ima sopstveno poređenje tarifa, dve putanje bi se s vremenom
    razišle. Ovo zaključava da obe čitaju isti `_TIER_ORDER`.
    """
    izvor = open(os.path.join(_KOREN, "routers", "voice_realtime.py"), encoding="utf-8").read()
    for helper in ("_ensure_profile", "_tier_satisfies", "effective_tier"):
        assert helper in izvor, f"WS ne koristi {helper} iz shared/permissions.py"
    assert 'policy.get("minimum_plan")' in izvor, "WS ne čita minimum_plan iz registry-ja"
